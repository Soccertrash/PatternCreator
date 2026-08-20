"""Spiralen - logarithmische Spiralen (Farnwedel-Optik)."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.geom import poisson_disk
from core.pattern_doc import Param, T_CHOICE, T_FLOAT, T_INT, T_LENGTH

from .base import GenContext, Generator


class SpiralsGenerator(Generator):
    id = "spirals"
    label = "Spiralen"
    description = ("Logarithmische Spiralen r = a·e^(b·θ), im Container gestreut. "
                   "Drehrichtung wahlweise gemischt.")
    icon = "M14 12a2 2 0 1 0-2 2 4 4 0 0 0 4-4 6 6 0 0 0-6-6 8 8 0 0 0-8 8"
    fill_targets = ("webs",)
    presets = {
        "fein": {"count": 24, "turns": 2.5, "startRadius": 0.15},
        "mittel": {"count": 10, "turns": 2.0, "startRadius": 0.3},
        "grob": {"count": 4, "turns": 1.5, "startRadius": 0.6},
    }

    params = [
        Param("count", "Spiralanzahl", T_INT, 10, min=1, max=300, step=1),
        Param("turns", "Windungen", T_FLOAT, 2.0, min=0.25, max=8.0, step=0.25),
        Param("startRadius", "Startradius", T_LENGTH, 0.3, min=0.01, max=20.0, step=0.02),
        Param("growth", "Wachstum b", T_FLOAT, 0.22, min=0.02, max=1.0, step=0.02,
              help="Je größer, desto schneller öffnet sich die Spirale."),
        Param("sizeSpread", "Größenstreuung", T_FLOAT, 0.4, min=0.0, max=1.0, step=0.05),
        Param("handedness", "Drehrichtung", T_CHOICE, "mixed", choices=[
            ("ccw", "Linksdrehend"), ("cw", "Rechtsdrehend"), ("mixed", "Gemischt")]),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        count = int(params["count"])
        turns = float(params["turns"])
        a0 = float(params["startRadius"])
        b = float(params["growth"])
        spread = float(params.get("sizeSpread", 0.0))
        hand = params.get("handedness", "mixed")
        rnd = ctx.rnd

        x0, y0, x1, y1 = ctx.bbox
        area = max(1e-6, (x1 - x0) * (y1 - y0))
        radius = math.sqrt(area / max(1, count)) * 0.75
        centers = poisson_disk(x0, y0, x1, y1, radius, rnd, max_points=count * 4)
        rnd.shuffle(centers)
        if len(centers) < count:
            centers += [(x0 + rnd.random() * (x1 - x0), y0 + rnd.random() * (y1 - y0))
                        for _ in range(count - len(centers))]
        centers = centers[:count]

        out: List[Any] = []
        steps = max(8, int(turns * 16))
        for c in centers:
            scale = 1.0 - spread * rnd.random()
            sign = 1.0 if hand == "ccw" else (-1.0 if hand == "cw"
                                              else (1.0 if rnd.random() < 0.5 else -1.0))
            rot = rnd.random() * 2 * math.pi
            pts = []
            for i in range(steps + 1):
                th = 2 * math.pi * turns * i / steps
                r = a0 * scale * math.exp(b * th)
                ang = rot + sign * th
                pts.append((c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)))
            out.append(ir.Path(points=pts, curve="spline", role=ir.ROLE_EDGE))
        return out
