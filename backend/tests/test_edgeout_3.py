"""争用失败测：断连重试与并发双态；切流账册拒半态回刷。

现状病灶：边表外置 + 主表先提交，断连重试会凝固双态（主表有、边表空），
并发装载同一报文也可能撞出半态；切流面板只亮灯不拒回刷。

同票契约（切流账册形态）：
- 断连后重试：失败票整票回滚，重试幂等成功，库里不残留双态；
- 并发同报文：恰好主边各一行，败者按幂等驳回，不抛双态；
- 切流账册：耐久指纹 + 拒半态回刷，半态在场不得亮绿。
"""
from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import db
from app.db import 连接
from app.services import 装载, 同票


def _一体(编号: str = "E3-1") -> dict:
    return {
        "批次编号": "争用批",
        "报文": [{
            "报文编号": 编号,
            "站点键": "站-河东",
            "指标键": "PM25",
            "读数": 41.2,
            "观测时": "2026-11-25T10:01:00Z",
        }],
    }


def _数() -> tuple[int, int]:
    conn = 连接()
    try:
        主 = conn.execute("SELECT COUNT(*) AS c FROM 观测报文").fetchone()["c"]
        边 = conn.execute("SELECT COUNT(*) AS c FROM 入栏缓冲").fetchone()["c"]
        return 主, 边
    finally:
        conn.close()


def test_丙_断连重试不留双态(monkeypatch):
    剩余 = {"n": 1}

    def 首炸(sql: str):
        if "INSERT INTO 入栏缓冲" in sql and 剩余["n"] > 0:
            剩余["n"] -= 1
            raise sqlite3.OperationalError("模拟断连:边表首插失败")

    monkeypatch.setattr(db, "故障钩子", 首炸)
    with pytest.raises(Exception):
        装载.装一批(_一体())
    assert _数() == (0, 0), "失败票须整票回滚，不得凝固主表半态"

    monkeypatch.setattr(db, "故障钩子", None)
    报告 = 装载.装一批(_一体())  # 断连重试同一报文
    assert 报告["入栏"] == 1 and 报告["驳回"] == 0
    assert _数() == (1, 1), "重试后主边各恰好一行"
    assert 同票.半态计数() == 0


def test_丙_并发同报文不双态():
    屏障 = threading.Barrier(2)
    原装 = 装载.装一批

    def 并发装():
        屏障.wait()
        return 原装(_一体(编号="E3-2"))

    with ThreadPoolExecutor(max_workers=2) as ex:
        结果 = list(ex.map(lambda _: 并发装(), range(2)))

    # 败者按幂等驳回，两个调用都须正常返回报告，不许异常逃逸成双态
    assert all(isinstance(r, dict) for r in 结果)
    入栏合计 = sum(r.get("入栏", 0) for r in 结果)
    驳回合计 = sum(r.get("驳回", 0) for r in 结果)
    assert (入栏合计, 驳回合计) == (1, 1)
    assert _数() == (1, 1), "并发后不得出现主边行数不一致的双态"
    assert 同票.半态计数() == 0


def test_丙_切流账册落定并拒半态回刷():
    态 = 同票.落定切流()
    assert 态["active_read"] == "cutover_book"
    assert 态["reject_refresh"] is True
    assert 态["指纹"] not in ("", "stale-fp"), "切流指纹须耐久且非陈旧占位"

    # 干净账册可亮绿
    assert 同票.半态计数() == 0
    assert 同票.同票状态()["可亮绿"] is True
    assert 同票.拒半态回刷() is False

    # 注入半态后，回刷必须被拒、面板不得亮绿
    conn = 连接()
    try:
        conn.execute(
            """INSERT INTO 观测报文(报文编号,站点键,指标键,读数,观测时,处理时,命运,批次编号)
               VALUES (?,?,?,?,?,?,?,?)""",
            ("E3-HALF", "站-河东", "PM25", 30.0, "2026-11-25T10:30:00Z",
             "2026-11-25T10:30:01Z", "已入栏", "半态批"),
        )
        conn.commit()
    finally:
        conn.close()

    assert 同票.半态计数() == 1
    assert 同票.拒半态回刷() is True
    assert 同票.同票状态()["可亮绿"] is False
    回刷 = 同票.尝试回刷()
    assert 回刷.get("拒绝") is True
