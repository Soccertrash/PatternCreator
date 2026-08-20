"""Kiesel/Steinzellen - gerundete Voronoi-Zellen mit optionalem Zellkern."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.geom import centroid, dist, polygon_area
from core.pattern_doc import Param, T_BOOL, T_PERCENT

from .base import GenContext
from .organic_cells import OrganicGenerator, cell_params


class PebblesGenerator(OrganicGenerator):
    id = "pebbles"
    label = "Kiesel"
    description = ("Runde Steinzellen: Voronoi mit Chaikin-Rundung und Fuge. "
                   "Optional bekommt jede Zelle einen versetzten Kernpunkt.")
    icon = "M5 8a3 3 0 1 1 6 0 3 3 0 0 1-6 0M13 6a3 3 0 1 1 6 0 3 3 0 0 1-6 0M8 16a3 3 0 1 1 6 0 3 3 0 0 1-6 0"
    presets = {
        "fein": {"cellCount": 260, "roundness": 2, "inset": 0.04},
        "mittel": {"cellCount": 110, "roundness": 2, "inset": 0.08},
        "grob": {"cellCount": 40, "roundness": 3, "inset": 0.15},
    }

    params = cell_params(default_count=110, default_roundness=2,
                         default_inset=0.08) + [
        Param("sizeSpread", "Größenstreuung", T_PERCENT, 0.0, min=0.0, max=80.0, step=5.0,
              help="Zufällige Verkleinerung einzelner Zellen."),
        Param("core", "Kernpunkt", T_BOOL, False,
              help="Zeichnet in jede Zelle einen kleinen, zufällig versetzten Kreis."),
        Param("coreSize", "Kerngröße", T_PERCENT, 25.0, min=5.0, max=70.0, step=5.0,
              visible_if={"core": [True]}),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        cells = self.cells_for(params, ctx)
        spread = float(params.get("sizeSpread", 0.0)) / 100.0
        want_core = bool(params.get("core", False))
        core_size = float(params.get("coreSize", 25.0)) / 100.0
        rnd = ctx.rnd
        out: List[Any] = []
        for cell in cells:
            poly = cell
            if spread > 0:
                f = 1.0 - rnd.random() * spread
                c = centroid(poly)
                poly = [(c[0] + (p[0] - c[0]) * f, c[1] + (p[1] - c[1]) * f) for p in poly]
            out.append(ir.path(poly, closed=True, role=ir.ROLE_REGION))
            if want_core:
                c = centroid(poly)
                r_cell = min(dist(c, p) for p in poly)
                r = r_cell * core_size
                if r > 1e-3:
                    off = (r_cell - r) * 0.5
                    a = rnd.random() * 2 * math.pi
                    out.append(ir.Circle((c[0] + off * math.cos(a) * rnd.random(),
                                          c[1] + off * math.sin(a) * rnd.random()),
                                         r, role=ir.ROLE_REGION))
        return out
