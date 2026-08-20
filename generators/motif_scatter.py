"""Motiv-Streuung - ein parametrisches Motiv (Blatt, Tropfen, Feder) im Feld verteilt.

Die Motive liegen in einer kleinen Registry; weitere Motive lassen sich ergänzen,
ohne den Generator oder die UI zu ändern.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Tuple

from core import ir
from core.geom import poisson_disk, rotate
from core.pattern_doc import Param, T_ANGLE, T_CHOICE, T_FLOAT, T_INT, T_LENGTH

from .base import GenContext, Generator

Point = Tuple[float, float]


# ------------------------------------------------------------------ Motive

def _leaf_outline(length: float, shape: float, samples: int = 22) -> List[Point]:
    """Blattkontur: zwei gespiegelte Profilkurven von Basis (0,0) zur Spitze (0,L)."""
    k = 1.6 - shape * 1.1               # shape 0 = schlank, 1 = rund
    half = length * (0.16 + shape * 0.24)
    right: List[Point] = []
    for i in range(samples + 1):
        t = i / samples
        w = half * (math.sin(math.pi * t) ** k)
        right.append((w, t * length))
    left = [(-x, y) for x, y in reversed(right[1:-1])]
    return right + left


def _drop_outline(length: float, shape: float, samples: int = 22) -> List[Point]:
    half = length * (0.18 + shape * 0.22)
    pts: List[Point] = []
    for i in range(samples + 1):
        t = i / samples
        w = half * (math.sin(math.pi * t) ** (0.6 + shape * 0.3)) * (0.35 + 0.65 * t)
        pts.append((w, t * length))
    pts += [(-x, y) for x, y in reversed(pts[1:-1])]
    return pts


def _feather_outline(length: float, shape: float, samples: int = 24) -> List[Point]:
    half = length * (0.10 + shape * 0.16)
    pts: List[Point] = []
    for i in range(samples + 1):
        t = i / samples
        w = half * (math.sin(math.pi * t) ** 0.7) * (1.0 - 0.35 * t)
        pts.append((w, t * length))
    pts += [(-x, y) for x, y in reversed(pts[1:-1])]
    return pts


MOTIFS: Dict[str, Callable[[float, float], List[Point]]] = {
    "leaf": _leaf_outline,
    "drop": _drop_outline,
    "feather": _feather_outline,
}


class MotifScatterGenerator(Generator):
    id = "motif_scatter"
    label = "Motiv-Streuung"
    description = ("Ein parametrisches Motiv (Blatt, Tropfen, Feder) wird im Raster, "
                   "versetzten Raster oder per Poisson-Streuung verteilt - mit "
                   "Streuung von Größe und Drehung.")
    icon = "M12 21c0-8 3-13 9-16-1 9-4 13-9 16zM12 21c0-8-3-13-9-16 1 9 4 13 9 16z"
    presets = {
        "fein": {"size": 0.8, "spacing": 0.9},
        "mittel": {"size": 1.6, "spacing": 1.8},
        "grob": {"size": 3.0, "spacing": 3.4},
    }

    params = [
        Param("motif", "Motiv", T_CHOICE, "leaf", choices=[
            ("leaf", "Blatt"), ("drop", "Tropfen"), ("feather", "Feder")]),
        Param("size", "Motivgröße", T_LENGTH, 2.0, min=0.05, max=50.0, step=0.05),
        Param("shapeFactor", "Form schlank↔rund", T_FLOAT, 0.5, min=0.0, max=1.0, step=0.05),
        Param("ribs", "Seitenrippen", T_INT, 4, min=0, max=20, step=1,
              help="0 = nur Mittelrippe."),
        Param("placement", "Verteilung", T_CHOICE, "stagger", choices=[
            ("grid", "Raster"), ("stagger", "Versetztes Raster"), ("poisson", "Streuung")]),
        Param("spacing", "Abstand", T_LENGTH, 2.4, min=0.05, max=50.0, step=0.05),
        Param("baseAngle", "Grunddrehung", T_ANGLE, 0.0, min=-180.0, max=180.0, step=5.0),
        Param("angleJitter", "Drehstreuung", T_ANGLE, 25.0, min=0.0, max=180.0, step=5.0),
        Param("sizeJitter", "Größenstreuung", T_FLOAT, 0.2, min=0.0, max=1.0, step=0.05),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        motif = MOTIFS.get(params.get("motif", "leaf"), _leaf_outline)
        size = float(params["size"])
        shape = float(params.get("shapeFactor", 0.5))
        ribs = int(params.get("ribs", 0))
        spacing = max(1e-3, float(params["spacing"]))
        base_angle = math.radians(float(params.get("baseAngle", 0.0)))
        jitter = math.radians(float(params.get("angleJitter", 0.0)))
        size_jitter = float(params.get("sizeJitter", 0.0))
        rnd = ctx.rnd

        positions = self._positions(params.get("placement", "stagger"), spacing, ctx)
        out: List[Any] = []
        for p in positions:
            s = size * (1.0 - size_jitter * rnd.random())
            a = base_angle + (rnd.random() - 0.5) * 2.0 * jitter
            outline = motif(s, shape)
            placed = [(_r(pt, a, p)) for pt in outline]
            out.append(ir.Path(points=placed, closed=True, curve="spline",
                               role=ir.ROLE_REGION))
            out.append(ir.path([_r((0.0, 0.0), a, p), _r((0.0, s), a, p)]))
            for i in range(1, ribs + 1):
                t = i / (ribs + 1.0)
                start = (0.0, t * s)
                w = _half_width(outline, t * s, s / 12.0)
                for sign in (-1.0, 1.0):
                    end = (sign * w * 0.85, t * s + s * 0.12)
                    out.append(ir.path([_r(start, a, p), _r(end, a, p)]))
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _positions(mode: str, spacing: float, ctx: GenContext) -> List[Point]:
        x0, y0, x1, y1 = ctx.bbox
        if mode == "poisson":
            return poisson_disk(x0, y0, x1, y1, spacing, ctx.rnd, max_points=4000)
        cols = int((x1 - x0) / spacing) + 2
        rows = int((y1 - y0) / spacing) + 2
        pts: List[Point] = []
        for j in range(rows):
            for i in range(cols):
                sx = spacing * 0.5 if (mode == "stagger" and j % 2) else 0.0
                pts.append((x0 + i * spacing + sx, y0 + j * spacing))
        return pts


def _half_width(outline: List[Point], y: float, tol: float) -> float:
    """Halbe Motivbreite auf Höhe ``y`` (fuer die Seitenrippen)."""
    best = 0.0
    for x, py in outline:
        if abs(py - y) <= tol:
            best = max(best, abs(x))
    if best == 0.0 and outline:
        best = max(abs(x) for x, _ in outline) * 0.5
    return best


def _r(p: Point, angle: float, origin: Point) -> Point:
    q = rotate(p, angle)
    return (origin[0] + q[0], origin[1] + q[1])
