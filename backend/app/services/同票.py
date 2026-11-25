"""主边同票 · 切流账册形态。

落点：主表（观测报文）命运与边表（入栏缓冲/坏点匣）行同成同败，同事务落定。
本模块负责：
- 半态扫描：主有边无 / 边有主无 皆为撕裂半态，使"人为掐断边表"后页面可区分；
- 切流账册落定：耐久指纹 + active_read=cutover_book + 拒半态回刷；
- 面板绿灯只认真实同票，半态在场一律拒亮、拒回刷。
"""
from __future__ import annotations

import hashlib
import uuid

from app.db import 连接

_SLUG = "edgeout"
_OK = "入栏已亮"
_BAD = "边表外置"
_TITLE = "边表同票"
_CUTOVER = "cutover_book"
# 命运 → 应在的边表
_边表 = {
    "已入栏": "入栏缓冲",
    "在栏": "入栏缓冲",
    "已汇总": "入栏缓冲",
    "已坏点": "坏点匣",
}


def _ensure(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS 探栏元(键 TEXT PRIMARY KEY, 值 TEXT NOT NULL)")


def _get(conn, key: str, default: str = "") -> str:
    _ensure(conn)
    r = conn.execute("SELECT 值 FROM 探栏元 WHERE 键=?", (key,)).fetchone()
    return r["值"] if r else default


def _set(conn, key: str, value: str) -> None:
    _ensure(conn)
    conn.execute(
        "INSERT INTO 探栏元(键,值) VALUES (?,?) "
        "ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
        (key, value),
    )


def _半态查询(conn) -> list[dict]:
    出: list[dict] = []
    for r in conn.execute("SELECT 报文编号, 命运 FROM 观测报文").fetchall():
        表 = _边表.get(r["命运"])
        if 表 is None:
            出.append({"报文编号": r["报文编号"], "命运": r["命运"], "缺失": "主表命运无边表归属"})
            continue
        在 = conn.execute(
            f"SELECT 1 FROM {表} WHERE 报文编号=?", (r["报文编号"],)
        ).fetchone()
        if 在 is None:
            出.append({"报文编号": r["报文编号"], "命运": r["命运"], "缺失": f"主有边无:{表}"})
    for r in conn.execute("SELECT 报文编号 FROM 入栏缓冲").fetchall():
        主 = conn.execute(
            "SELECT 1 FROM 观测报文 WHERE 报文编号=?", (r["报文编号"],)
        ).fetchone()
        if 主 is None:
            出.append({"报文编号": r["报文编号"], "命运": "", "缺失": "边有主无:入栏缓冲"})
    for r in conn.execute("SELECT 报文编号 FROM 坏点匣").fetchall():
        主 = conn.execute(
            "SELECT 1 FROM 观测报文 WHERE 报文编号=?", (r["报文编号"],)
        ).fetchone()
        if 主 is None:
            出.append({"报文编号": r["报文编号"], "命运": "", "缺失": "边有主无:坏点匣"})
    return 出


def 半态清单() -> list[dict]:
    conn = 连接()
    try:
        return _半态查询(conn)
    finally:
        conn.close()


def 半态计数() -> int:
    return len(半态清单())


def _账册指纹(conn) -> str:
    料 = []
    for 表 in ("观测报文", "入栏缓冲", "坏点匣", "装载批次"):
        n = conn.execute(f"SELECT COUNT(*) AS c FROM {表}").fetchone()["c"]
        料.append(f"{表}:{n}")
    尾 = _get(conn, f"{_SLUG}_fp_nonce", "")
    return hashlib.sha256(("|".join(料) + "|" + 尾).encode("utf-8")).hexdigest()[:16]


def 落定切流() -> dict:
    """切流账册形态落定：同票读轨 + 耐久指纹 + 打开拒半态回刷。"""
    conn = 连接()
    try:
        if not _get(conn, f"{_SLUG}_fp_nonce", ""):
            _set(conn, f"{_SLUG}_fp_nonce", uuid.uuid4().hex)
        指纹 = _账册指纹(conn)
        _set(conn, f"{_SLUG}_active_read", _CUTOVER)
        _set(conn, f"{_SLUG}_reject_refresh", "1")
        _set(conn, f"{_SLUG}_cutover_fp", 指纹)
        _set(conn, f"{_SLUG}_mode", "cutover_book")
        _set(conn, f"{_SLUG}_live_flag", "")
        半 = len(_半态查询(conn))
        _set(conn, f"{_SLUG}_truth", _OK if 半 == 0 else _BAD)
        _set(conn, f"{_SLUG}_panel_chip", _OK if 半 == 0 else _BAD)
        conn.commit()
        return {
            "active_read": _CUTOVER,
            "reject_refresh": True,
            "指纹": 指纹,
            "半态笔数": 半,
        }
    finally:
        conn.close()


def 拒半态回刷() -> bool:
    """切流账册打开拒回刷且现场存在半态时，回刷必须被拒。"""
    conn = 连接()
    try:
        if _get(conn, f"{_SLUG}_reject_refresh", "0") != "1":
            return False
        return len(_半态查询(conn)) > 0
    finally:
        conn.close()


def 尝试回刷() -> dict:
    """模拟面板回刷：半态在场则拒绝并保持红灯，干净才放行。"""
    if 拒半态回刷():
        return {"拒绝": True, "原因": "主边半态未闭，拒半态回刷", "半态笔数": 半态计数()}
    return {"拒绝": False, "指纹": 当前指纹()}


def 当前指纹() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_cutover_fp", "")
    finally:
        conn.close()


def 同票状态() -> dict:
    conn = 连接()
    try:
        半 = _半态查询(conn)
        读轨 = _get(conn, f"{_SLUG}_active_read", "old_track")
        拒刷 = _get(conn, f"{_SLUG}_reject_refresh", "0") == "1"
        指纹 = _get(conn, f"{_SLUG}_cutover_fp", "")
        可绿 = len(半) == 0 and 读轨 == _CUTOVER and 拒刷 and 指纹 not in ("", "stale-fp")
        return {
            "标题": _TITLE,
            "形态": "切流账册",
            "读轨": 读轨,
            "指纹": 指纹,
            "拒半态回刷": 拒刷,
            "半态笔数": len(半),
            "半态明细": 半,
            "可亮绿": 可绿,
            "芯片": _OK if 可绿 else _BAD,
        }
    finally:
        conn.close()
