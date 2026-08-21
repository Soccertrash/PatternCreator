"""Gitter - rechtwinkliges oder schiefwinkliges Linienraster."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.pattern_doc import Param, T_ANGLE, T_LENGTH

from ._util import lattice_cells, snap_period
from .base import GenContext, Generator


class GridGenerator(Generator):
    id = "grid"
    tiling = True
    label = "Gitter"
    description = ("Rechtwinkliges Linienraster mit getrennten Abständen in X und Y. "
                   "Über den Scharenwinkel wird daraus ein schiefwinkliges Raster.")
    icon = "M3 8h18M3 16h18M8 3v18M16 3v18"
    presets = {
        "fein": {"spacingX": 0.3, "spacingY": 0.3},
        "mittel": {"spacingX": 0.8, "spacingY": 0.8},
        "grob": {"spacingX": 2.0, "spacingY": 2.0},
    }

    params = [
        Param("spacingX", "Abstand X", T_LENGTH, 0.8, min=0.02, max=50.0, step=0.05,
              help="Senkrechter Abstand der senkrechten Linienschar."),
        Param("spacingY", "Abstand Y", T_LENGTH, 0.8, min=0.02, max=50.0, step=0.05,
              help="Senkrechter Abstand der waagerechten Linienschar."),
        Param("skew", "Scharenwinkel", T_ANGLE, 90.0, min=15.0, max=165.0, step=1.0,
              help="90° = rechtwinklig; andere Werte ergeben ein schiefes Raster."),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        sx = float(params["spacingX"])
        sy = float(params["spacingY"])
        theta = math.radians(max(15.0, min(165.0, float(params["skew"]))))
        s = math.sin(theta)
        # In x wiederholt sich das Gitter nach ``e1.x`` - unabhaengig vom
        # Scharenwinkel, weil ``e2`` eine y-Komponente hat und deshalb in keiner
        # ganzzahligen Kombination eine reine x-Verschiebung ergibt.
        e1x = sx / s
        origin = (0.0, 0.0)
        if ctx.periodic:
            e1x = snap_period(e1x, ctx.period_x)
            origin = (ctx.bbox[0], 0.0)
        e1 = (e1x, 0.0)
        e2 = (sy / s * math.cos(theta), sy / s * s)
        cells = lattice_cells(ctx.bbox, e1, e2, origin=origin,
                              margin=max(sx, sy) * 2)
        return [ir.path(c, closed=True, role=ir.ROLE_REGION) for c in cells]
