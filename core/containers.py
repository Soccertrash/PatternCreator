"""Container (Rahmenformen) und zentrales Clipping.

Die Generatoren fuellen immer nur das Bounding-Rechteck. Das Beschneiden gegen
die tatsaechliche Form uebernimmt der Container - dadurch braucht kein Generator
Container-Wissen.

Die **Standardformen** sind konvex, deshalb genuegt dort Halbebenen-Clipping
(``core/clip.py``). Der *gezeichnete* Umriss ist dagegen echte Geometrie (Kreis,
Ellipse, Bogen), keine Polygon-Naeherung.

Der **eigene Rahmen** (:class:`CustomContainer`) kommt aus einem Skizzenprofil
oder einer planaren Flaeche und ist fast nie konvex. Er benutzt deshalb den
allgemeinen Clipper aus ``core/polyclip.py``.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from . import clip as clipmod
from . import ir
from . import polyclip
from .geom import (circle_points, clean_polygon, ellipse_points, ensure_ccw,
                   inset_polygon, point_in_polygon, polygon_area, regular_polygon,
                   remove_loops, rounded_rect_points)
from .optimize import TOL, _reduce_indices, _self_intersects
from .stroker import shrink_polygon_checked

Point = Tuple[float, float]

CIRCLE_SEGMENTS = 96


class Container:
    """Basisklasse. Lokale Koordinaten: Mittelpunkt bei (0, 0)."""

    shape = "rect"

    #: Wurde beim letzten ``shrunk()`` die Rahmendicke nicht eingehalten?
    #: ``build_scene`` haengt daraufhin eine Warnung an die Szene.
    shrink_failed = False

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

    def _keeps_distance(self, poly: Sequence[Point], delta: float) -> bool:
        """Haelt der versetzte Rahmen ueberall den Abstand ``delta`` ein?

        Der Gehrungs-Offset ist keine echte Erosion: laeuft die Kontur in einen
        Hals hinein, der schmaler ist als zweimal ``delta``, schlaegt sie dort
        durch - und ``remove_loops`` sieht das nicht einmal, wenn sich die
        durchgeschlagenen Kanten nur kollinear ueberlappen (Hantelform). Geprueft
        wird deshalb direkt die Eigenschaft, die zugesagt ist: jeder Punkt der
        neuen Kontur (Ecken **und** Kantenmitten) liegt innen und mindestens
        ``delta`` von der alten Kontur entfernt.

        Die Kandidatenkanten kommen aus dem Raster - sonst waere der Test bei
        einem tessellierten Rahmen quadratisch.
        """
        grid = self.grid
        tol = 1e-9 * max(1.0, delta)
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            for p in (a, ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)):
                if not grid.contains(p):
                    return False
                for j in grid.edges_near(p[0] - delta, p[1] - delta,
                                         p[0] + delta, p[1] + delta):
                    c, d = grid.edges[j]
                    if polyclip.point_segment_distance(p, c, d) < delta - tol:
                        return False
        return True

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


#: Der Versatz einer konkaven Kontur ist teuer (Offset plus Schleifensuche),
#: und die Vorschau baut den Container bei jeder Reglerbewegung neu.
_SHRINK_CACHE: dict = {}
SHRINK_CACHE_LIMIT = 32


class CustomContainer(Container):
    """Rahmen aus einer abgetasteten Profil- oder Flaechenkontur.

    Darf konkav sein. Die Punkte kommen als Schnappschuss aus dem PatternDoc
    (``container.customPoints``) - der Rahmen haengt also nicht daran, dass die
    Quellgeometrie in Fusion noch existiert.
    """

    shape = "custom"

    def __init__(self, points: Sequence[Point], normalized: bool = False):
        self.points = (list(points) if normalized
                       else normalize_frame(points))
        self._grid: Optional[polyclip.PolygonGrid] = None

    # -- Grundlagen ------------------------------------------------------
    @property
    def grid(self) -> polyclip.PolygonGrid:
        """Beschleunigungsraster (ueber den Modul-Cache in ``polyclip``)."""
        if self._grid is None:
            self._grid = polyclip.grid_for(self.points)
        return self._grid

    def bounding_rect(self):
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def clip_polygon(self):
        return self.points

    def outline(self):
        return [ir.path(self.points, closed=True, layer=ir.LAYER_BORDER,
                        role=ir.ROLE_EDGE)]

    # -- Clipping --------------------------------------------------------
    def contains(self, p: Point) -> bool:
        return self.grid.contains(p)

    def classify_bbox(self, x0: float, y0: float, x1: float, y1: float) -> str:
        return self.grid.classify_bbox(x0, y0, x1, y1)

    def clip_path(self, points: Sequence[Point], closed: bool) -> List[List[Point]]:
        if closed:
            return polyclip.clip_polygon_general(points, self.points, grid=self.grid)
        return polyclip.clip_polyline_general(points, self.points, closed=False,
                                              grid=self.grid)

    def fully_inside(self, points: Sequence[Point]) -> bool:
        return polyclip.polygon_fully_inside(points, self.points, grid=self.grid)

    def shrunk(self, delta: float) -> "Container":
        """Kontur nach innen versetzen - ueber den Stroker, nicht ueber Gehrung.

        ``inset_polygon`` kollabiert an Einbuchtungen; genau die hat ein
        gezeichneter Rahmen. Misslingt der Versatz (die Kontur ist irgendwo
        schmaler als zweimal ``delta``), bleibt es beim urspruenglichen Rahmen -
        mit gesetztem :attr:`shrink_failed`, damit ``build_scene`` warnen kann
        statt still das Mass zu verfehlen.
        """
        if delta <= 1e-9:
            return self
        key = (tuple(self.points), round(float(delta), 9))
        cached = _SHRINK_CACHE.get(key)
        if cached is None:
            poly, intact = shrink_polygon_checked(self.points, delta)
            if poly and intact:
                intact = self._keeps_distance(poly, delta)
            cached = (poly, intact)
            if len(_SHRINK_CACHE) >= SHRINK_CACHE_LIMIT:
                _SHRINK_CACHE.pop(next(iter(_SHRINK_CACHE)))
            _SHRINK_CACHE[key] = cached
        poly, intact = cached
        if poly and len(poly) >= 3:
            # Der Versatz liefert bereits eine bereinigte, schleifenfreie
            # Kontur - kein zweites ``normalize_frame`` noetig (und kein
            # zweites RDP, das die Kontur ein weiteres Mal vereinfachen wuerde).
            inner = CustomContainer(poly, normalized=True)
            if intact:
                return inner
            inner.shrink_failed = True
            self.shrink_failed = True
            return inner
        self.shrink_failed = True
        return self


SHAPES = ("rect", "square", "circle", "ellipse", "polygon", "custom")


#: Groesste zulaessige Punktzahl einer eigenen Rahmenkontur.
MAX_FRAME_POINTS = 5000

#: Kleinste zulaessige Flaeche einer eigenen Rahmenkontur (cm^2).
MIN_FRAME_AREA = 1e-8


#: Die Vorschau parst das Dokument bei jeder Reglerbewegung neu, die
#: Rahmenkontur bleibt dabei dieselbe. Ohne Cache liefe RDP und die
#: Schleifensuche jedes Mal erneut ueber ein paar hundert Punkte.
_NORMALIZE_CACHE: dict = {}
NORMALIZE_CACHE_LIMIT = 16


def normalize_frame(points: Sequence[Point]) -> List[Point]:
    """Rohe Konturpunkte in die Form bringen, die der Container erwartet.

    Duplikate und Schliesspunkt weg, gegen den Uhrzeigersinn orientiert,
    Selbstschnitte entfernt, mit Ramer-Douglas-Peucker auf die Optimierer-
    Toleranz vereinfacht. Letzteres ist keine Kosmetik: Fusion tesselliert einen
    Bogen in hunderte Punkte, und jeder davon kostet in jeder Zelle des Musters
    Schnitttests.

    **Abweichung vom Plan:** die Vereinfachung laeuft *vor* ``remove_loops``.
    ``remove_loops`` ist O(n^2) je Durchgang; bei einer tessellierten Kontur mit
    ein paar tausend Punkten dauert das Sekunden - und zwar bei jedem Parsen des
    Dokuments. Nach der Vereinfachung ist die Kontur klein genug.

    Wirft ``ValueError``, wenn nichts Brauchbares uebrig bleibt.
    """
    try:
        pts = [(float(x), float(y)) for x, y in points]
    except (TypeError, ValueError):
        raise ValueError("Die Rahmenkontur enthält ungültige Punkte.")
    key = tuple(pts)
    hit = _NORMALIZE_CACHE.get(key)
    if hit is not None:
        return list(hit)
    if len(pts) > MAX_FRAME_POINTS:
        raise ValueError("Die Rahmenkontur hat mehr als %d Punkte."
                         % MAX_FRAME_POINTS)
    for x, y in pts:
        if x != x or y != y or x in (float("inf"), float("-inf")) \
                or y in (float("inf"), float("-inf")):
            raise ValueError("Die Rahmenkontur enthält ungültige Punkte.")
    pts = clean_polygon(pts)
    if len(pts) < 3:
        raise ValueError("Die Rahmenkontur hat weniger als drei Punkte.")
    pts = ensure_ccw(pts)
    reduced = [pts[i] for i in _reduce_indices(pts, True, TOL)]
    if len(reduced) >= 3 and not (_self_intersects(reduced, True)
                                  and not _self_intersects(pts, True)):
        pts = reduced
    pts = remove_loops(pts)
    if len(pts) < 3:
        raise ValueError("Die Rahmenkontur schneidet sich selbst.")
    pts = ensure_ccw(clean_polygon(pts))
    if len(pts) < 3 or abs(polygon_area(pts)) <= MIN_FRAME_AREA:
        raise ValueError("Die Rahmenkontur umschließt keine Fläche.")
    if len(_NORMALIZE_CACHE) >= NORMALIZE_CACHE_LIMIT:
        _NORMALIZE_CACHE.pop(next(iter(_NORMALIZE_CACHE)))
    _NORMALIZE_CACHE[key] = pts
    return list(pts)


def make_container(cfg: dict) -> Container:
    """Container aus dem ``container``-Abschnitt eines PatternDoc bauen."""
    shape = cfg.get("shape", "rect")
    if shape == "custom":
        pts = cfg.get("customPoints") or []
        if len(pts) >= 3:
            try:
                return CustomContainer(pts)
            except ValueError:
                pass
        # Rueckfall wie in ``pattern_doc.parse``: ein Doc ohne brauchbare
        # Kontur zeigt lieber ein Rechteck als gar nichts.
        shape = "rect"
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
