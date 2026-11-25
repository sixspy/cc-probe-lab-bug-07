"""失败测乙：校验/贯验假绿。

现状病灶：贯验只对 已汇总缓冲 与 汇总账报文数，半态主表（主表已入栏、
边表零行）不进任何核对，页面照亮"对齐"。

同票契约：半态主表必须可被区分，贯验把半态计入撕裂，拒绝把半态当对齐绿；
主边齐全的正常链路仍须对齐。
"""
from __future__ import annotations

from app.db import 连接
from app.services import 夹具, 装载, 结栏, 贯验, 同票


def _塞半态主表(编号: str = "HALF-2-1") -> None:
    """人为制造主表已入栏、边表零行的半态（外置边表失败后的凝固态）。"""
    conn = 连接()
    try:
        conn.execute(
            """INSERT INTO 观测报文(报文编号,站点键,指标键,读数,观测时,处理时,命运,批次编号)
               VALUES (?,?,?,?,?,?,?,?)""",
            (编号, "站-河东", "PM25", 33.0, "2026-11-25T09:01:00Z",
             "2026-11-25T09:01:01Z", "已入栏", "半态批"),
        )
        conn.commit()
    finally:
        conn.close()


def test_乙_半态主表不得被贯验当对齐绿():
    _塞半态主表()
    # 半态须可被同票扫描区分出来
    assert 同票.半态计数() == 1
    半态 = 同票.半态清单()
    assert any(r["报文编号"] == "HALF-2-1" for r in 半态)

    snap = 贯验.只读快照()
    assert snap["是否对齐"] is False, "半态主表在栏却无边表行，快照不得判对齐"
    assert snap.get("半态笔数", 0) >= 1

    落账 = 贯验.跑一次()
    assert 落账["是否对齐"] is False, "贯验落账不得把半态写成对齐绿"
    assert "撕裂" in 落账["说明"] or "半态" in 落账["说明"]


def test_乙_齐全链路贯验仍对齐():
    装载.装一批(夹具.读取("入栏成汇总样例"))
    结栏.结当前栏()
    assert 同票.半态计数() == 0
    落账 = 贯验.跑一次()
    assert 落账["是否对齐"] is True
    assert 落账.get("半态笔数", 0) == 0


def test_乙_坏点边表也须同票可核():
    # 坏点走坏点匣边表，同样不得留无主/无边的半态
    装载.装一批(夹具.读取("坏点样例"))
    conn = 连接()
    try:
        主 = conn.execute(
            "SELECT 命运 FROM 观测报文 WHERE 报文编号=?", ("P-bad-1",)
        ).fetchone()
        边 = conn.execute(
            "SELECT 1 FROM 坏点匣 WHERE 报文编号=?", ("P-bad-1",)
        ).fetchone()
    finally:
        conn.close()
    assert 主["命运"] == "已坏点" and 边 is not None
    assert 同票.半态计数() == 0
