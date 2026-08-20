"""Puzzle - Raster mit klassischen Puzzle-Nasen an jeder Innenkante."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core import ir
from core.pattern_doc import Param, T_FLOAT, T_INT, T_PERCENT

from ._util import bezier
from .base import GenContext, Generator

Point = Tuple[float, float]

# Normalisierte Nasenkontur: x entlang der Kante (0..1), y quer (Spitze = 1.0)
_LEAD_IN = 0.35
_TAB = [
    # (c1, c2, p) je kubischem Bezier-Abschnitt
    ((0.42, 0.00), (0.32, 0.43), (0.42, 0.52)),
    ((0.30, 1.00), (0.70, 1.00), (0.58, 0.52)),
    ((0.68, 0.43), (0.58, 0.00), (0.65, 0.00)),
]


class PuzzleGenerator(Generator):
    id = "puzzle"
    label = "Puzzle"
    description = ("Puzzleteile im Raster X×Y. Jede Innenkante bekommt eine Nase, "
                   "deren Richtung der Seed bestimmt. Im Flächenmodus ist jedes Teil "
                   "ein geschlossenes, extrudierbares Profil.")
    icon = ("M4 4h6a2 2 0 1 1 4 0h6v6a2 2 0 1 0 0 4v6h-6a2 2 0 1 0-4 0H4v-6a2 2 0 1 1 0-4z")
    presets = {
        "fein": {"countX": 9, "countY": 6},
        "mittel": {"countX": 5, "countY": 4},
        "grob": {"countX": 3, "countY": 2},
    }

    params = [
        Param("countX", "Teile X", T_INT, 5, min=1, max=60, step=1),
        Param("countY", "Teile Y", T_INT, 4, min=1, max=60, step=1),
        Param("tabSize", "Nasengröße", T_PERCENT, 22.0, min=2.0, max=45.0, step=1.0,
              help="Höhe der Nase in Prozent der Kantenlänge."),
        Param("neckWidth", "Halsbreite", T_PERCENT, 16.0, min=6.0, max=40.0, step=1.0,
              help="Breite des Nasenhalses in Prozent der Kantenlänge."),
        Param("shapeJitter", "Formstreuung", T_FLOAT, 0.15, min=0.0, max=1.0, step=0.05,
              help="Zufällige Variation von Nasengröße und -position."),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        nx = max(1, int(params["countX"]))
        ny = max(1, int(params["countY"]))
        tab = float(params["tabSize"]) / 100.0
        neck = float(params["neckWidth"]) / 100.0
        jitter = float(params.get("shapeJitter", 0.0))
        rnd = ctx.rnd

        x0, y0, x1, y1 = ctx.bbox
        dx = (x1 - x0) / nx
        dy = (y1 - y0) / ny

        def node(i: int, j: int) -> Point:
            return (x0 + i * dx, y0 + j * dy)

        h_edges: Dict[Tuple[int, int], List[Point]] = {}
        v_edges: Dict[Tuple[int, int], List[Point]] = {}
        for j in range(ny + 1):
            for i in range(nx):
                inner = 0 < j < ny
                h_edges[(i, j)] = self._edge(node(i, j), node(i + 1, j), inner,
                                             tab, neck, jitter, rnd)
        for i in range(nx + 1):
            for j in range(ny):
                inner = 0 < i < nx
                v_edges[(i, j)] = self._edge(node(i, j), node(i, j + 1), inner,
                                             tab, neck, jitter, rnd)

        out: List[Any] = []
        for j in range(ny):
            for i in range(nx):
                ring: List[Point] = list(h_edges[(i, j)])
                ring += v_edges[(i + 1, j)][1:]
                ring += list(reversed(h_edges[(i, j + 1)]))[1:]
                ring += list(reversed(v_edges[(i, j)]))[1:-1]
                out.append(ir.path(ring, closed=True, role=ir.ROLE_REGION))
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _edge(a: Point, b: Point, inner: bool, tab: float, neck: float,
              jitter: float, rnd) -> List[Point]:
        if not inner:
            return [a, b]
        ux, uy = b[0] - a[0], b[1] - a[1]
        length = (ux * ux + uy * uy) ** 0.5
        if length < 1e-9:
            return [a, b]
        ux, uy = ux / length, uy / length
        nx, ny = -uy, ux
        direction = 1.0 if rnd.random() < 0.5 else -1.0
        size = tab * (1.0 + jitter * (rnd.random() - 0.5) * 1.2)
        k = max(0.5, min(2.5, neck / 0.16))
        shift = jitter * (rnd.random() - 0.5) * 0.12

        def m(p: Tuple[float, float]) -> Point:
            x = 0.5 + (p[0] - 0.5) * k + shift
            x = max(0.02, min(0.98, x))
            y = p[1] * size * direction
            return (a[0] + ux * x * length + nx * y * length,
                    a[1] + uy * x * length + ny * y * length)

        lead = max(0.02, min(0.48, 0.5 - (0.5 - _LEAD_IN) * k + shift))
        pts: List[Point] = [a, m((lead, 0.0))]
        cur = (lead, 0.0)
        for c1, c2, p in _TAB:
            pts.extend(bezier(m(cur), m(c1), m(c2), m(p), samples=8)[1:])
            pts.append(m(p))
            cur = p
        pts.append(b)
        return pts
