"""Container (Rahmenformen) und zentrales Clipping.

Die Generatoren fuellen immer nur das Bounding-Rechteck. Das Beschneiden gegen
die tatsaechliche Form uebernimmt der Container - dadurch braucht kein Generator
Container-Wissen.

Alle Formen sind konvex, deshalb genuegt Halbebenen-Clipping (``core/clip.py``).
Der *gezeichnete* Umriss ist dagegen echte Geometrie (Kreis, Ellipse, Bogen),
keine Polygon-Naeherung.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from . import clip as clipmod
from . import ir
from .geom import (circle_points, ellipse_points, inset_polygon, point_in_polygon,
                   regular_polygon, rounded_rect_points)

Point = Tuple[float, float]

CIRCLE_SEGMENTS = 96


class Container:
    """Basisklasse. Lokale Koordinaten: Mittelpunkt bei (0, 0)."""

    shape = "rect"

    def bounding_rect(self) -> Tuple[float, float, float, float]:
        raise NotImplementedError

    def clip_polygon(self) -> List[Point]:
        """Konvexe Polygon-Naeherung - nur fuers Clipping."""
        raise NotImplementedError

    def face_outline(self) -> object:
        """Aussenkontur als **ein** Element (fuer die zusammenhaengende Flaeche).

        ``outline()`` darf mehrteilig sein (abgerundetes Rechteck = Kanten +
        Boegen); die Flaechenlogik in ``core/build.py`` braucht dagegen genau
        eine geschlossene Kurve.
        """
        return ir.path(self.clip_polygon(), closed=True, layer=ir.LAYER_BORDER,
                       role=ir.ROLE_FACE)

    def shrunk(self, delta: float) -> "Container":
        """Gleiche Form, um ``delta`` nach innen versetzt (Rahmenbreite)."""
        if delta <= 1e-9:
            return self
        pts = inset_polygon(self.clip_polygon(), delta)
        if not pts or len(pts) < 3:
            return self
        return CustomContainer(pts)

    def outline(self) -> List[object]:
        """Exakte IR-Geometrie des Umrisses."""
        raise NotImplementedError

    # -- gemeinsame Logik -------------------------------------------------
    def contains(self, p: Point) -> bool:
        return point_in_polygon(p, self.clip_polygon())

    def radius_hint(self) -> float:
        x0, y0, x1, y1 = self.bounding_rect()
        return 0.5 * math.hypot(x1 - x0, y1 - y0)

    def clip_path(self, points: Sequence[Point], closed: bool) -> List[List[Point]]:
        poly = self.clip_polygon()
        if closed:
            res = clipmod.clip_polygon(points, poly)
            return [res] if len(res) >= 3 else []
        return clipmod.clip_polyline(points, poly, closed=False)

    def fully_inside(self, points: Sequence[Point]) -> bool:
        planes = clipmod.half_planes(self.clip_polygon())
        for p in points:
            for a, b, c in planes:
                if a * p[0] + b * p[1] + c > 1e-9:
                    return False
        return True


class RectContainer(Container):
    shape = "rect"

    def __init__(self, width: float, height: float, corner_radius: float = 0.0):
        self.width = float(width)
        self.height = float(height)
        self.corner_radius = max(0.0, float(corner_radius))

    def bounding_rect(self):
        return (-self.width / 2, -self.height / 2, self.width / 2, self.height / 2)

    def clip_polygon(self):
        return rounded_rect_points(0.0, 0.0, self.width, self.height, self.corner_radius)

    def face_outline(self):
        return ir.path(self.clip_polygon(), closed=True, layer=ir.LAYER_BORDER,
                       role=ir.ROLE_FACE)

    def shrunk(self, delta):
        if delta <= 1e-9:
            return self
        w = self.width - 2 * delta
        h = self.height - 2 * delta
        if w <= 1e-6 or h <= 1e-6:
            return self
        return RectContainer(w, h, max(0.0, self.corner_radius - delta))

    def outline(self):
        hw, hh = self.width / 2, self.height / 2
        r = min(self.corner_radius, hw - 1e-6, hh - 1e-6)
        if r <= 1e-9:
            return [ir.path([(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)],
                            closed=True, layer=ir.LAYER_BORDER, role=ir.ROLE_EDGE)]
        els: List[object] = []
        # Vier gerade Kanten
        els.append(ir.path([(-hw + r, -hh), (hw - r, -hh)], layer=ir.LAYER_BORDER))
        els.append(ir.path([(hw, -hh + r), (hw, hh - r)], layer=ir.LAYER_BORDER))
        els.append(ir.path([(hw - r, hh), (-hw + r, hh)], layer=ir.LAYER_BORDER))
        els.append(ir.path([(-hw, hh - r), (-hw, -hh + r)], layer=ir.LAYER_BORDER))
        # Vier echte Eckbogen
        for cx, cy, a0 in ((hw - r, -hh + r, -math.pi / 2), (hw - r, hh - r, 0.0),
                           (-hw + r, hh - r, math.pi / 2), (-hw + r, -hh + r, math.pi)):
            els.append(ir.Arc((cx, cy), r, a0, a0 + math.pi / 2, layer=ir.LAYER_BORDER))
        return els


class CircleContainer(Container):
    shape = "circle"

    def __init__(self, diameter: float):
        self.radius = float(diameter) / 2.0

    def bounding_rect(self):
        r = self.radius
        return (-r, -r, r, r)

    def clip_polygon(self):
        # Innen-Naeherung leicht vergroessern, damit Randelemente nicht verschwinden
        return circle_points((0.0, 0.0), self.radius / math.cos(math.pi / CIRCLE_SEGMENTS),
                             CIRCLE_SEGMENTS)

    def outline(self):
        return [ir.Circle((0.0, 0.0), self.radius, role=ir.ROLE_EDGE, layer=ir.LAYER_BORDER)]

    def face_outline(self):
        return ir.Circle((0.0, 0.0), self.radius, role=ir.ROLE_FACE,
                         layer=ir.LAYER_BORDER)

    def shrunk(self, delta):
        if delta <= 1e-9 or self.radius - delta <= 1e-6:
            return self
        return CircleContainer((self.radius - delta) * 2.0)


class EllipseContainer(Container):
    shape = "ellipse"

    def __init__(self, width: float, height: float):
        self.rx = float(width) / 2.0
        self.ry = float(height) / 2.0

    def bounding_rect(self):
        return (-self.rx, -self.ry, self.rx, self.ry)

    def clip_polygon(self):
        f = 1.0 / math.cos(math.pi / CIRCLE_SEGMENTS)
        return ellipse_points((0.0, 0.0), self.rx * f, self.ry * f, CIRCLE_SEGMENTS)

    def outline(self):
        return [ir.Ellipse((0.0, 0.0), self.rx, self.ry, 0.0, layer=ir.LAYER_BORDER)]

    def face_outline(self):
        return ir.Ellipse((0.0, 0.0), self.rx, self.ry, 0.0, role=ir.ROLE_FACE,
                          layer=ir.LAYER_BORDER)

    def shrunk(self, delta):
        if delta <= 1e-9 or min(self.rx, self.ry) - delta <= 1e-6:
            return self
        return EllipseContainer((self.rx - delta) * 2.0, (self.ry - delta) * 2.0)


class PolygonContainer(Container):
    shape = "polygon"

    def __init__(self, diameter: float, sides: int):
        self.radius = float(diameter) / 2.0
        self.sides = max(3, min(12, int(sides)))

    def bounding_rect(self):
        pts = self.clip_polygon()
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def clip_polygon(self):
        return regular_polygon((0.0, 0.0), self.radius, self.sides, math.pi / 2)

    def outline(self):
        return [ir.path(self.clip_polygon(), closed=True, layer=ir.LAYER_BORDER,
                        role=ir.ROLE_EDGE)]

    def shrunk(self, delta):
        # Abstand Mittelpunkt->Kante ist der Inkreis: r_i = R * cos(pi/n)
        if delta <= 1e-9:
            return self
        r = self.radius - delta / math.cos(math.pi / self.sides)
        if r <= 1e-6:
            return self
        return PolygonContainer(r * 2.0, self.sides)


class CustomContainer(Container):
    """Container aus einer abgetasteten Profil-/Flaechenkontur (Phase 6).

    Kann konkav sein; Clipping erfolgt dann konservativ ueber Punkt-in-Polygon
    plus Halbebenen der konvexen Huelle.
    """

    shape = "custom"

    def __init__(self, points: Sequence[Point]):
        self.points = [(float(x), float(y)) for x, y in points]

    def bounding_rect(self):
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def clip_polygon(self):
        return self.points

    def outline(self):
        return [ir.path(self.points, closed=True, layer=ir.LAYER_BORDER, role=ir.ROLE_EDGE)]


SHAPES = ("rect", "square", "circle", "ellipse", "polygon")


def make_container(cfg: dict) -> Container:
    """Container aus dem ``container``-Abschnitt eines PatternDoc bauen."""
    shape = cfg.get("shape", "rect")
    if shape == "square":
        side = float(cfg.get("width", 10.0))
        return RectContainer(side, side, float(cfg.get("cornerRadius", 0.0)))
    if shape == "circle":
        return CircleContainer(float(cfg.get("diameter", 8.0)))
    if shape == "ellipse":
        return EllipseContainer(float(cfg.get("width", 10.0)), float(cfg.get("height", 6.0)))
    if shape == "polygon":
        return PolygonContainer(float(cfg.get("diameter", 8.0)), int(cfg.get("sides", 6)))
    return RectContainer(float(cfg.get("width", 10.0)), float(cfg.get("height", 6.0)),
                         float(cfg.get("cornerRadius", 0.0)))
