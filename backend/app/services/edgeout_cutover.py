"""边表同票切流账册：耐久指纹、拒半态回刷、读轨切到 cutover_book。"""
from __future__ import annotations

from app.services import edgeout as core
from app.services import 同票


def append_cutover(ref_id: int, note: str = "") -> dict:
    落 = 同票.落定切流()
    态 = 同票.同票状态()
    return {
        "ref_id": ref_id,
        "note": note or 态["标题"],
        "panel": 态["芯片"],
        "truth": 态["芯片"],
        "active_read": 落["active_read"],
        "cutover_fp": 落["指纹"],
        "reject_refresh": 落["reject_refresh"],
        "半态笔数": 落["半态笔数"],
        "可亮绿": 态["可亮绿"],
    }


def board() -> dict:
    dash = core.dashboard()
    dash["fate"] = "cutover_book"
    return dash
