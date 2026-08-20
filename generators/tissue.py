"""Zellgewebe - längliche Zellen in Reihen (Mikroskopie-Optik)."""

from __future__ import annotations

from typing import Any, Dict, List

from core import ir
from core.pattern_doc import Param, T_FLOAT

from .base import GenContext
from .organic_cells import OrganicGenerator, cell_params


class TissueGenerator(OrganicGenerator):
    id = "tissue"
    label = "Zellgewebe"
    description = ("Geschichtete, in X gestreckte Zellen in Reihen - die typische "
                   "Optik pflanzlicher Gewebeschnitte.")
    icon = "M3 6h18M3 12h18M3 18h18M7 6v6M13 6v6M9 12v6M16 12v6"
    presets = {
        "fein": {"cellCount": 320, "rows": 14, "anisotropy": 2.5, "roundness": 2},
        "mittel": {"cellCount": 160, "rows": 8, "anisotropy": 2.5, "roundness": 2},
        "grob": {"cellCount": 60, "rows": 4, "anisotropy": 3.0, "roundness": 3},
    }

    params = cell_params(default_count=160, with_rows=True, default_roundness=2) + [
        Param("rowJitter", "Unruhe", T_FLOAT, 0.7, min=0.0, max=1.5, step=0.05,
              help="Streuung der Zellen innerhalb ihrer Reihe."),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        from .organic_cells import build_cells
        cells = build_cells(
            ctx,
            count=int(params.get("cellCount", 160)),
            relax=int(params.get("relax", 1)),
            anisotropy=float(params.get("anisotropy", 2.5)),
            rows=int(params.get("rows", 8)),
            smooth=int(params.get("roundness", 2)),
            inset=float(params.get("inset", 0.0)),
            jitter=float(params.get("rowJitter", 0.7)),
        )
        return [ir.path(c, closed=True, role=ir.ROLE_REGION) for c in cells]
