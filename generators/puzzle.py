"""Puzzle - Raster mit klassischen Puzzle-Nasen an jeder Innenkante."""

from __future__ import annotations

import math

from typing import Any, Dict, List, Tuple

from core import ir
from core.pattern_doc import Param, T_FLOAT, T_INT, T_PERCENT

from ._util import bezier
from .base import GenContext, Generator

Point = Tuple[float, float]

#: Stuetzpunkte je Kurvenabschnitt. Wenige reichen fuer eine glatte Kontur,
#: viele treiben die Zahl der Skizzenlinien hoch (jeder Punkt = eine Linie).
_SAMPLES = 6

#: Verhaeltnis Kopfbreite zu Halsbreite - der Kopf muss breiter sein als der Hals,
#: sonst greifen die Teile nicht ineinander und es sieht nicht nach Puzzle aus.
_HEAD_FACTOR = 1.75

#: Wo der Hals den Kopfkreis beruehrt (Winkel am Kopfmittelpunkt). 205 Grad liegt
#: unten links - von dort laeuft der Bogen ueber den Scheitel nach unten rechts.
_TANGENT_ANGLE = math.radians(205.0)

#: Tiefe des Unterschnitts am Nasenfuss in Einheiten der Halsbreite - die
#: charakteristische kleine S-Kurve, mit der die Kontur in den Hals einschwenkt.
_UNDERCUT = 0.35


class PuzzleGenerator(Generator):
    id = "puzzle"
    tiling = True
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
        Param("tabSize", "Nasengröße", T_PERCENT, 28.0, min=2.0, max=45.0, step=1.0,
              help="Gesamthöhe der Nase (Hals + Kopf) in Prozent der Kantenlänge. "
                   "Zu kleine Werte werden auf die Kopfgröße angehoben."),
        Param("neckWidth", "Halsbreite", T_PERCENT, 18.0, min=6.0, max=40.0, step=1.0,
              help="Breite des Nasenhalses in Prozent der Kantenlänge. Der Kopf "
                   "ist ein Kreis und rund 1,75-mal so breit."),
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
        """Eine Kante als Polylinie - aussen gerade, innen mit klassischer Nase.

        Der Kopf ist ein **echter Kreis** (Radius = halbe Kopfbreite); der Hals
        laeuft tangential in ihn hinein, damit es keinen Knick gibt. Alle Masse
        sind Bruchteile der Kantenlaenge.
        """
        if not inner:
            return [a, b]
        ux, uy = b[0] - a[0], b[1] - a[1]
        length = (ux * ux + uy * uy) ** 0.5
        if length < 1e-9:
            return [a, b]
        ux, uy = ux / length, uy / length
        nx, ny = -uy, ux

        direction = 1.0 if rnd.random() < 0.5 else -1.0
        half_neck = max(0.015, neck / 2.0 * (1.0 + jitter * (rnd.random() - 0.5) * 0.8))
        half_head = half_neck * _HEAD_FACTOR
        height = tab * (1.0 + jitter * (rnd.random() - 0.5) * 1.2)
        # Unter dieser Hoehe bliebe vom Hals nichts uebrig
        height = max(height, half_head * 1.55)

        foot = half_neck + half_head * 0.55
        centre = 0.5 + jitter * (rnd.random() - 0.5) * 0.14
        centre = max(foot + 0.02, min(1.0 - foot - 0.02, centre))

        def m(x: float, y: float) -> Point:
            """Normierte Kantenkoordinaten (beide in Kantenlaengen) -> Skizze."""
            px, py = x * length, y * direction * length
            return (a[0] + ux * px + nx * py, a[1] + uy * px + ny * py)

        cy = height - half_head                      # Mittelpunkt des Kopfkreises
        ct, st = math.cos(_TANGENT_ANGLE), math.sin(_TANGENT_ANGLE)
        tangent = (centre + half_head * ct, cy + half_head * st)
        # Laufrichtung auf dem Kreis im Beruehrpunkt (Bogen laeuft ueber den Scheitel)
        tdir = (st, -ct)

        # Hals: vom Fuss tangential in den Kopfkreis
        p0 = (centre - foot, 0.0)
        p1 = (p0[0] + half_neck * 0.7, -_UNDERCUT * half_neck)
        reach = (cy + half_head * st) * 0.75
        p2 = (tangent[0] - tdir[0] * reach, tangent[1] - tdir[1] * reach)

        pts: List[Point] = [a, m(*p0)]
        pts.extend(bezier(m(*p0), m(*p1), m(*p2), m(*tangent),
                          samples=_SAMPLES)[1:])

        # Kopf: echter Kreisbogen vom Beruehrpunkt ueber den Scheitel
        a0 = _TANGENT_ANGLE
        a1 = math.pi - _TANGENT_ANGLE                # spiegelbildlich, ueber 90 Grad
        steps = max(6, _SAMPLES * 2)
        for k in range(1, steps + 1):
            ang = a0 + (a1 - a0) * k / steps
            pts.append(m(centre + half_head * math.cos(ang),
                         cy + half_head * math.sin(ang)))

        # Hals der Gegenseite: gespiegelte Kurve rueckwaerts
        def mir(p):
            return (2 * centre - p[0], p[1])

        pts.extend(bezier(m(*mir(tangent)), m(*mir(p2)), m(*mir(p1)), m(*mir(p0)),
                          samples=_SAMPLES)[1:])
        pts.append(b)
        return pts
