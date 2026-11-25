"""失败测甲：装载假绿。

现状病灶：边表事务外置——主表（观测报文）先 commit，边表（入栏缓冲/坏点匣）
在事务外插入。人为掐断边表插入后，主表残留、报告/页面仍可亮成功，账实撕裂。

同票契约：主表命运与边表行同成同败，边表失败则整票回滚，主表零残留、
不写装载批次、不亮成功。
"""
from __future__ import annotations

import sqlite3

import pytest

from app import db
from app.db import 连接
from app.services import 装载, 同票


def _一体(编号: str = "E1-1") -> dict:
    return {
        "批次编号": "边断甲",
        "报文": [{
            "报文编号": 编号,
            "站点键": "站-河东",
            "指标键": "PM25",
            "读数": 22.5,
            "观测时": "2026-11-25T08:01:00Z",
        }],
    }


@pytest.fixture()
def 边表断连(monkeypatch):
    """注入边表插入失败：模拟提交主表后断连。"""
    def 钩(sql: str):
        if "INSERT INTO 入栏缓冲" in sql or "INSERT INTO 坏点匣" in sql:
            raise sqlite3.OperationalError("模拟断连:边表插入失败")

    monkeypatch.setattr(db, "故障钩子", 钩)
    yield
    monkeypatch.setattr(db, "故障钩子", None)


def _库里数() -> tuple[int, int, int]:
    conn = 连接()
    try:
        主 = conn.execute("SELECT COUNT(*) AS c FROM 观测报文").fetchone()["c"]
        边 = conn.execute("SELECT COUNT(*) AS c FROM 入栏缓冲").fetchone()["c"]
        批 = conn.execute("SELECT COUNT(*) AS c FROM 装载批次").fetchone()["c"]
        return 主, 边, 批
    finally:
        conn.close()


def test_甲_边表断连主表同票回滚不得亮成功(边表断连):
    # 断连必须向上抛，调用方不得收到成功报告
    with pytest.raises(Exception):
        装载.装一批(_一体())

    主, 边, 批 = _库里数()
    # 同成同败：主表不得残留"已装载/已入栏"半态行，批次不得落账
    assert 主 == 0, f"主表残留半态行 {主} 行，边表 {边} 行：假绿"
    assert 边 == 0
    assert 批 == 0, "失败装载不得写装载批次成功账"
    assert 同票.半态计数() == 0


def test_甲_正常装载主边齐全才可绿():
    报告 = 装载.装一批(_一体(编号="E1-2"))
    assert 报告["入栏"] == 1
    assert 报告.get("同票") in (None, "主边同票")  # 成功票须可标识同票
    conn = 连接()
    try:
        主 = conn.execute(
            "SELECT 命运 FROM 观测报文 WHERE 报文编号=?", ("E1-2",)
        ).fetchone()
        边 = conn.execute(
            "SELECT 1 FROM 入栏缓冲 WHERE 报文编号=?", ("E1-2",)
        ).fetchone()
    finally:
        conn.close()
    assert 主 is not None and 主["命运"] == "已入栏"
    assert 边 is not None, "主表已入栏则边表必须同行"
    assert 同票.半态计数() == 0
