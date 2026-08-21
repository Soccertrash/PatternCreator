"""Rauten - zwei Linienscharen mit Winkel ±α."""

from __future__ import annotations

from typing import Any, Dict, List

from core import ir
from core.pattern_doc import Param, T_LENGTH

from ._util import lattice_cells, snap_period
from .base import GenContext, Generator


class RhombusGenerator(Generator):
    id = "rhombus"
    tiling = True
    label = "Rauten"
    description = ("Rautenraster aus zwei Linienscharen mit Winkel ±α. "
                   "Breite und Höhe der Raute bestimmen den Winkel.")
    icon = "M12 3 21 12 12 21 3 12Z"
    presets = {
        "fein": {"width": 0.6, "height": 1.0},
        "mittel": {"width": 1.2, "height": 2.0},
        "grob": {"width": 2.4, "height": 4.0},
    }

    params = [
        Param("width", "Rautenbreite", T_LENGTH, 1.2, min=0.05, max=50.0, step=0.05,
              help="Waagerechte Diagonale der Raute."),
        Param("height", "Rautenhöhe", T_LENGTH, 2.0, min=0.05, max=50.0, step=0.05,
              help="Senkrechte Diagonale der Raute."),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        w = float(params["width"])
        h = float(params["height"])
        origin = (0.0, 0.0)
        if ctx.periodic:
            # ``e1 + e2 = (w, 0)``: das Raster wiederholt sich in x nach genau
            # einer Rautenbreite.
            w = snap_period(w, ctx.period_x)
            origin = (ctx.bbox[0], 0.0)
        e1 = (w / 2.0, h / 2.0)
        e2 = (w / 2.0, -h / 2.0)
        cells = lattice_cells(ctx.bbox, e1, e2, origin=origin, margin=max(w, h))
        return [ir.path(c, closed=True, role=ir.ROLE_REGION) for c in cells]
