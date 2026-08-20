"""Wellen - Reihen von Sinuskurven als gefittete Splines."""

from __future__ import annotations

import math
from typing import Any, Dict, List

from core import ir
from core.pattern_doc import Param, T_ANGLE, T_FLOAT, T_LENGTH

from .base import GenContext, Generator


class WavesGenerator(Generator):
    id = "waves"
    label = "Wellen"
    description = ("Parallele Wellenlinien mit einstellbarer Wellenlänge, Amplitude "
                   "und Phasenversatz je Zeile.")
    icon = "M3 7c3-4 6 4 9 0s6-4 9 0M3 13c3-4 6 4 9 0s6-4 9 0M3 19c3-4 6 4 9 0s6-4 9 0"
    fill_targets = ("webs",)
    presets = {
        "fein": {"wavelength": 1.0, "amplitude": 0.2, "lineSpacing": 0.3},
        "mittel": {"wavelength": 2.5, "amplitude": 0.5, "lineSpacing": 0.7},
        "grob": {"wavelength": 5.0, "amplitude": 1.0, "lineSpacing": 1.5},
    }

    params = [
        Param("wavelength", "Wellenlänge", T_LENGTH, 2.5, min=0.1, max=100.0, step=0.1),
        Param("amplitude", "Amplitude", T_LENGTH, 0.5, min=0.0, max=50.0, step=0.05),
        Param("lineSpacing", "Linienabstand", T_LENGTH, 0.7, min=0.03, max=20.0, step=0.05),
        Param("phaseShift", "Phasenversatz je Zeile", T_ANGLE, 45.0, min=-180.0, max=180.0,
              step=5.0),
        Param("jitter", "Unruhe", T_FLOAT, 0.0, min=0.0, max=1.0, step=0.05,
              help="Zufällige Abweichung von Amplitude und Phase je Zeile."),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        wl = max(1e-4, float(params["wavelength"]))
        amp = float(params["amplitude"])
        spacing = max(1e-4, float(params["lineSpacing"]))
        shift = math.radians(float(params["phaseShift"]))
        jitter = float(params.get("jitter", 0.0))
        rnd = ctx.rnd

        x0, y0, x1, y1 = ctx.expanded(max(amp, spacing))
        samples_per_wave = 8
        step = wl / samples_per_wave
        rows = int((y1 - y0) / spacing) + 1
        out: List[Any] = []
        for i in range(rows):
            y = y0 + i * spacing
            a = amp * (1.0 + jitter * (rnd.random() - 0.5) * 1.5)
            phase = shift * i + jitter * rnd.random() * 2 * math.pi
            pts = []
            n = int((x1 - x0) / step) + 2
            for k in range(n + 1):
                x = x0 + k * step
                pts.append((x, y + a * math.sin(2 * math.pi * x / wl + phase)))
            out.append(ir.Path(points=pts, curve="spline", role=ir.ROLE_EDGE))
        return out
