"""Wabe - lückenloses Sechseckraster."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.geom import regular_polygon
from core.pattern_doc import Param, T_CHOICE, T_LENGTH

from ._util import hex_centers
from .base import GenContext, Generator


class HoneycombGenerator(Generator):
    id = "honeycomb"
    tiling = True
    label = "Wabe"
    description = ("Lückenloses Sechseckraster. Im Flächenmodus lassen sich wahlweise "
                   "die Stege (Wände) oder die Zellen extrudieren.")
    icon = "M9 3h6l3 5.2-3 5.2H9L6 8.2z"
    presets = {
        "fein": {"cellSize": 0.4},
        "mittel": {"cellSize": 0.8},
        "grob": {"cellSize": 2.0},
    }

    params = [
        Param("cellSize", "Zellweite", T_LENGTH, 0.8, min=0.05, max=50.0, step=0.05,
              help="Schlüsselweite der Wabe (Abstand gegenüberliegender Flächen)."),
        Param("orientation", "Ausrichtung", T_CHOICE, "flat", choices=[
            ("flat", "Fläche oben"), ("pointy", "Spitze oben")]),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        size = float(params["cellSize"])
        flat_top = params.get("orientation", "flat") == "flat"
        r = size / math.sqrt(3.0)
        rotation = 0.0 if flat_top else math.pi / 6.0
        out: List[Any] = []
        for c in hex_centers(ctx.bbox, size, flat_top, margin=size):
            out.append(ir.path(regular_polygon(c, r, 6, rotation),
                               closed=True, role=ir.ROLE_REGION))
        return out
