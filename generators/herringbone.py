"""Fischgrät / Palmwedel - Rippen, die im Winkel auf Mittelachsen zulaufen."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.pattern_doc import Param, T_ANGLE, T_BOOL, T_FLOAT, T_INT, T_LENGTH

from .base import GenContext, Generator


class HerringboneGenerator(Generator):
    id = "herringbone"
    label = "Fischgrät"
    description = ("Rippen laufen beidseitig im Winkel auf eine Mittelachse zu. "
                   "Eine Achse ergibt einen Palmwedel, mehrere ein Fischgrät-Feld.")
    icon = "M12 3v18M12 6 6 3M12 6l6-3M12 11 6 8M12 11l6-3M12 16l-6-3M12 16l6-3"
    fill_targets = ("webs",)
    presets = {
        "fein": {"ribSpacing": 0.25, "ribLength": 1.0},
        "mittel": {"ribSpacing": 0.5, "ribLength": 1.8},
        "grob": {"ribSpacing": 1.0, "ribLength": 3.0},
    }

    params = [
        Param("axisCount", "Mittelachsen", T_INT, 1, min=1, max=40, step=1,
              help="1 = Palmwedel, mehr = Fischgrät-Feld."),
        Param("ribSpacing", "Rippenabstand", T_LENGTH, 0.5, min=0.03, max=20.0, step=0.05),
        Param("ribAngle", "Rippenwinkel", T_ANGLE, 40.0, min=5.0, max=85.0, step=1.0,
              help="Winkel der Rippen gegen die Achse."),
        Param("ribLength", "Rippenlänge", T_LENGTH, 1.8, min=0.05, max=50.0, step=0.05),
        Param("curvature", "Krümmung", T_FLOAT, 0.15, min=0.0, max=1.0, step=0.05,
              help="0 = gerade Rippen, > 0 = leicht gebogen."),
        Param("drawAxis", "Achse zeichnen", T_BOOL, True),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        axes = max(1, int(params["axisCount"]))
        spacing = float(params["ribSpacing"])
        angle = math.radians(float(params["ribAngle"]))
        rib_len = float(params["ribLength"])
        curve = float(params.get("curvature", 0.0))
        draw_axis = bool(params.get("drawAxis", True))

        x0, y0, x1, y1 = ctx.bbox
        out: List[Any] = []
        step = (x1 - x0) / axes
        for k in range(axes):
            ax = x0 + step * (k + 0.5)
            if draw_axis:
                out.append(ir.path([(ax, y0), (ax, y1)]))
            n = int((y1 - y0) / spacing) + 1
            for i in range(n):
                y = y0 + i * spacing
                for side in (-1.0, 1.0):
                    out.append(self._rib((ax, y), side, angle, rib_len, curve))
        return out

    @staticmethod
    def _rib(base, side: float, angle: float, length: float, curve: float):
        dx = side * math.sin(angle)
        dy = math.cos(angle)
        end = (base[0] + dx * length, base[1] + dy * length)
        if curve <= 1e-6:
            return ir.path([base, end])
        mid = ((base[0] + end[0]) / 2.0, (base[1] + end[1]) / 2.0)
        nx, ny = -dy, dx
        bow = curve * length * 0.25
        ctrl = (mid[0] + nx * bow * side, mid[1] + ny * bow * side)
        return ir.Path(points=[base, ctrl, end], curve="spline", role=ir.ROLE_EDGE)
