"""Schuppen - versetzte Reihen überlappender Bögen."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.pattern_doc import Param, T_LENGTH, T_PERCENT

from .base import GenContext, Generator


class ScalesGenerator(Generator):
    id = "scales"
    label = "Schuppen"
    description = ("Fischschuppen: versetzte Reihen aus überlappenden Kreisbögen. "
                   "Die Überlappung bestimmt, wie dicht die Reihen liegen.")
    icon = "M3 9a4.5 4.5 0 0 1 9 0 4.5 4.5 0 0 1 9 0M3 17a4.5 4.5 0 0 1 9 0 4.5 4.5 0 0 1 9 0"
    fill_targets = ("webs",)
    presets = {
        "fein": {"scaleWidth": 0.6, "overlap": 40.0},
        "mittel": {"scaleWidth": 1.4, "overlap": 40.0},
        "grob": {"scaleWidth": 3.0, "overlap": 50.0},
    }

    params = [
        Param("scaleWidth", "Schuppenbreite", T_LENGTH, 2.0, min=0.05, max=50.0, step=0.05),
        Param("overlap", "Überlappung", T_PERCENT, 40.0, min=0.0, max=80.0, step=5.0,
              help="Wie weit eine Reihe in die darunter liegende ragt."),
        Param("rowOffset", "Reihenversatz", T_PERCENT, 50.0, min=0.0, max=100.0, step=5.0),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        w = max(1e-4, float(params["scaleWidth"]))
        overlap = float(params["overlap"]) / 100.0
        offset = float(params["rowOffset"]) / 100.0

        r = w / 2.0
        row_h = max(1e-4, r * (1.0 - overlap))
        x0, y0, x1, y1 = ctx.expanded(w)
        rows = int((y1 - y0) / row_h) + 1
        cols = int((x1 - x0) / w) + 2
        out: List[Any] = []
        for j in range(rows + 1):
            cy = y0 + j * row_h
            shift = (j % 2) * offset * w
            for i in range(-1, cols):
                cx = x0 + i * w + shift
                out.append(ir.Arc((cx, cy), r, 0.0, math.pi, role=ir.ROLE_EDGE))
        return out
