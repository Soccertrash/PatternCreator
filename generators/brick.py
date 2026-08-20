"""Mauer - Ziegelverband mit Fuge und Reihenversatz."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.pattern_doc import Param, T_CHOICE, T_FLOAT, T_LENGTH

from .base import GenContext, Generator


class BrickGenerator(Generator):
    id = "brick"
    tiling = True
    label = "Mauer"
    description = ("Ziegelverband mit einstellbarer Fugenbreite und Reihenversatz "
                   "(Läuferverband 1/2, Drittelverband 1/3 oder frei).")
    icon = "M3 6h18M3 12h18M3 18h18M10 6v6M16 12v6M10 18v3M16 3v3"
    own_gap = True
    presets = {
        "fein": {"brickWidth": 1.0, "brickHeight": 0.4, "jointWidth": 0.06},
        "mittel": {"brickWidth": 2.0, "brickHeight": 0.8, "jointWidth": 0.12},
        "grob": {"brickWidth": 4.0, "brickHeight": 1.6, "jointWidth": 0.25},
    }

    params = [
        Param("brickWidth", "Ziegelbreite", T_LENGTH, 2.0, min=0.1, max=50.0, step=0.05),
        Param("brickHeight", "Ziegelhöhe", T_LENGTH, 0.8, min=0.05, max=50.0, step=0.05),
        Param("jointWidth", "Fugenbreite", T_LENGTH, 0.12, min=0.0, max=5.0, step=0.01,
              help="Abstand zwischen den Ziegeln. 0 = fugenlos."),
        Param("bond", "Verband", T_CHOICE, "half", choices=[
            ("half", "Läufer 1/2"), ("third", "Drittel 1/3"), ("free", "Frei"),
            ("stack", "Ohne Versatz")]),
        Param("offsetFraction", "Versatz", T_FLOAT, 0.25, min=0.0, max=1.0, step=0.01,
              visible_if={"bond": ["free"]},
              help="Anteil der Ziegelbreite, um den jede Reihe versetzt wird."),
    ]

    def gap(self, params):
        # Jeder Ziegel ist um joint/2 verkleinert -> Abstand = jointWidth
        return max(0.0, float(params.get("jointWidth", 0.0)))

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        bw = float(params["brickWidth"])
        bh = float(params["brickHeight"])
        joint = max(0.0, float(params["jointWidth"]))
        bond = params.get("bond", "half")
        frac = {"half": 0.5, "third": 1.0 / 3.0, "stack": 0.0}.get(
            bond, float(params.get("offsetFraction", 0.25)))

        x0, y0, x1, y1 = ctx.expanded(max(bw, bh))
        rows = int(math.ceil((y1 - y0) / bh)) + 2
        cols = int(math.ceil((x1 - x0) / bw)) + 2
        half = joint / 2.0
        out: List[Any] = []
        for j in range(rows):
            by = y0 + j * bh
            shift = ((j * frac) % 1.0) * bw
            for i in range(-1, cols):
                bx = x0 + i * bw + shift
                ax0, ay0 = bx + half, by + half
                ax1, ay1 = bx + bw - half, by + bh - half
                if ax1 - ax0 <= 1e-6 or ay1 - ay0 <= 1e-6:
                    continue
                if ax1 < x0 or ax0 > x1 or ay1 < y0 or ay0 > y1:
                    continue
                out.append(ir.path([(ax0, ay0), (ax1, ay0), (ax1, ay1), (ax0, ay1)],
                                   closed=True, role=ir.ROLE_REGION))
        return out
