"""Phyllotaxis - Sonnenblumenanordnung nach dem Vogel-Modell."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.geom import regular_polygon
from core.pattern_doc import Param, T_CHOICE, T_FLOAT, T_INT, T_LENGTH

from .base import GenContext, Generator

GOLDEN_ANGLE = math.radians(137.508)


class PhyllotaxisGenerator(Generator):
    id = "phyllotaxis"
    label = "Phyllotaxis"
    description = ("Elemente im Goldenen Winkel (137,508°) mit r = c·√n - die "
                   "Spiralanordnung von Sonnenblumenkernen.")
    icon = "M12 12m-9 0a9 9 0 1 0 18 0 9 9 0 1 0-18 0M12 12l4-6M12 12l-6-3M12 12l3 7"
    presets = {
        "fein": {"count": 600, "scale": 0.16, "elementSize": 0.1},
        "mittel": {"count": 250, "scale": 0.25, "elementSize": 0.16},
        "grob": {"count": 90, "scale": 0.4, "elementSize": 0.28},
    }

    params = [
        Param("count", "Elementanzahl", T_INT, 250, min=5, max=2000, step=5),
        Param("scale", "Skalierung c", T_LENGTH, 0.25, min=0.01, max=10.0, step=0.01,
              help="Radius = c · √n; bestimmt die Dichte der Anordnung."),
        Param("elementSize", "Elementgröße", T_LENGTH, 0.16, min=0.01, max=10.0, step=0.01),
        Param("shape", "Elementform", T_CHOICE, "circle", choices=[
            ("circle", "Kreis"), ("hexagon", "Sechseck"), ("drop", "Tropfen")]),
        Param("growth", "Größenverlauf", T_FLOAT, 0.5, min=-1.0, max=2.0, step=0.05,
              help="0 = konstant, > 0 = außen größer, < 0 = außen kleiner."),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        count = int(params["count"])
        c = float(params["scale"])
        size = float(params["elementSize"])
        shape = params.get("shape", "circle")
        growth = float(params.get("growth", 0.0))
        cx, cy = ctx.center

        out: List[Any] = []
        for n in range(1, count + 1):
            r = c * math.sqrt(n)
            a = n * GOLDEN_ANGLE
            p = (cx + r * math.cos(a), cy + r * math.sin(a))
            f = 1.0 + growth * (math.sqrt(n) / math.sqrt(count) - 0.5) * 2.0
            s = max(1e-4, size * f)
            if shape == "circle":
                out.append(ir.Circle(p, s / 2.0, role=ir.ROLE_REGION))
            elif shape == "hexagon":
                out.append(ir.path(regular_polygon(p, s / 2.0, 6, a), closed=True,
                                   role=ir.ROLE_REGION))
            else:
                out.append(ir.path(_drop(p, s / 2.0, a), closed=True, role=ir.ROLE_REGION))
        return out


def _drop(center, r: float, angle: float, segments: int = 16):
    """Tropfenform: Kreis mit einer nach außen gezogenen Spitze."""
    pts = []
    for i in range(segments):
        t = 2 * math.pi * i / segments
        rad = r * (0.65 + 0.35 * math.cos(t)) * (1.0 + 0.55 * math.cos(t))
        rad = max(r * 0.12, rad)
        pts.append((center[0] + rad * math.cos(t + angle),
                    center[1] + rad * math.sin(t + angle)))
    return pts
