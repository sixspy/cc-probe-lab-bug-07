"""边表同票读轨审计。"""
from __future__ import annotations

from app.services import edgeout as core
from app.services import edgeout_cutover as cutover
from app.services import edgeout_dualwrite as dual


def audit_summary() -> dict:
    return {
        "title": "边表同票审计",
        "core": core.dashboard(),
        "cutover": cutover.board(),
        "dualwrite": dual.dual_board(),
        "half": core.half_fix_display(),
    }
