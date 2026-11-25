"""边表同票收口面：切流账册形态下由 app.services.同票 供真相。

面板绿灯只认真实主边同票（读轨 cutover_book + 耐久指纹 + 拒半态回刷 + 零半态），
半态在场一律红灯并拒回刷，不再允许 display-only 假亮。
"""
from __future__ import annotations

from app.db import 连接

_SLUG = "edgeout"
_OK = "入栏已亮"
_BAD = "边表外置"
_TITLE = "边表同票"
_OLD = "old_track"
_CUTOVER = "cutover_book"
_LIVE = "live_flag"


def _ensure(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS 探栏元("
        "键 TEXT PRIMARY KEY, 值 TEXT NOT NULL)"
    )


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


def panel_chip() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_panel_chip", _OK)
    finally:
        conn.close()


def truth_flag() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_truth", _BAD)
    finally:
        conn.close()


def active_read_ref() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_active_read", _OLD)
    finally:
        conn.close()


def cutover_fp() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_cutover_fp", "stale-fp")
    finally:
        conn.close()


def reject_refresh() -> bool:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_reject_refresh", "0") == "1"
    finally:
        conn.close()


def live_flag() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_live_flag", "")
    finally:
        conn.close()


def archive_rows() -> list[dict]:
    conn = 连接()
    try:
        _ensure(conn)
        rows = conn.execute(
            "SELECT 键,值 FROM 探栏元 WHERE 键 LIKE ? ORDER BY 键",
            (f"{_SLUG}_archive_%",),
        ).fetchall()
        return [{"键": r["键"], "值": r["值"]} for r in rows]
    finally:
        conn.close()


def paint_ok() -> str:
    """不再允许 display-only 假亮：只反映同票真相。"""
    from app.services import 同票
    态 = 同票.同票状态()
    return 态["芯片"]


def commit_action(payload: dict | None = None) -> dict:
    """切流账册落定：主边同事务读轨 + 耐久指纹 + 拒半态回刷。"""
    from app.services import 同票
    落 = 同票.落定切流()
    态 = 同票.同票状态()
    return {
        "ok": 态["可亮绿"],
        "chip": 态["芯片"],
        "title": _TITLE,
        "active_read": 落["active_read"],
        "cutover_fp": 落["指纹"],
        "reject_refresh": 落["reject_refresh"],
        "archive_count": len(archive_rows()),
        "live_flag": live_flag(),
        "半态笔数": 落["半态笔数"],
        "message": f"{_TITLE}切流账册已落定" if 态["可亮绿"] else f"{_TITLE}存在半态，红灯拒回刷",
    }


def half_fix_display() -> dict:
    """半修（只补插边表而不同票）在真相面下无法冒充绿灯。"""
    from app.services import 同票
    态 = 同票.同票状态()
    return {
        "panel_chip": 态["芯片"],
        "truth": 态["芯片"],
        "active_read": 态["读轨"],
        "archive_count": len(archive_rows()),
        "half_fixed": False,
        "半态笔数": 态["半态笔数"],
    }


def snapshot() -> dict:
    from app.services import 同票
    态 = 同票.同票状态()
    半 = 态["半态笔数"]
    aligned = 态["可亮绿"]
    return {
        "title": _TITLE,
        "panel_chip": 态["芯片"],
        "truth": 态["芯片"],
        "active_read": 态["读轨"],
        "cutover_fp": 态["指纹"],
        "reject_refresh": 态["拒半态回刷"],
        "archive_count": len(archive_rows()),
        "live_flag": live_flag(),
        "aligned": aligned,
        "panel_pack_mismatch": not aligned,
        "gate_bypass": False,
        "形态": 态["形态"],
        "半态笔数": 半,
        "半态明细": 态["半态明细"],
    }


def dashboard() -> dict:
    snap = snapshot()
    return {
        **snap,
        "ok_chip": _OK,
        "bad_chip": _BAD,
        "label": _TITLE,
        "read_tracks": {
            "old_track": _OLD,
            "cutover_book": _CUTOVER,
            "live_flag": _LIVE,
        },
    }


def reconcile_display() -> dict:
    return half_fix_display()
