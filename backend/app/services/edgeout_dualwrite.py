"""边表同票双写两轨（未选用形态）。

落点已择定为切流账册：主边同事务落定。双写面只保留只读镜像，
不写 archive、不翻 live_flag、不改 active_read，避免用镜像芯片冒充绿灯。
"""
from __future__ import annotations

from app.services import edgeout as core
from app.services import 同票

_SLUG = "edgeout"
_TITLE = "边表同票"
_OK = "入栏已亮"


def apply_dualwrite(note: str = "") -> dict:
    # 双写两轨未启用：仅记笔记，不翻转任何读轨/灯态
    态 = 同票.同票状态()
    return {
        "dual_chip": 态["芯片"],
        "truth": 态["芯片"],
        "active_read": 态["读轨"],
        "archive_count": len(core.archive_rows()),
        "live_flag": core.live_flag(),
        "note": note or "双写两轨未选用，现行形态=切流账册",
    }


def dual_board() -> dict:
    dash = core.dashboard()
    return {
        "dual_chip": dash["panel_chip"],
        "truth": dash["truth"],
        "active_read": dash["active_read"],
        "archive": core.archive_rows(),
        "live_flag": core.live_flag(),
        "dash": dash,
        "fate": "dualwrite_unselected",
        "panel_pack_mismatch": not dash["aligned"],
        "title": f"{_TITLE}双写面（未选用）",
    }
