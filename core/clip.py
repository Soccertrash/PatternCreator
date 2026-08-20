"""Clipping gegen konvexe Bereiche.

Alle Container-Formen aus ``core/containers.py`` sind konvex (Rechteck mit
Eckenradius, Kreis, Ellipse, regelmaessiges Vieleck), ebenso die rotierte
Text-Knockout-Box. Deshalb genuegt Halbebenen-Clipping:

* geschlossene Polygone -> Sutherland-Hodgman
* offene Polylinien     -> segmentweiser Parameter-Schnitt, zusammenhaengende
  Stuecke werden wieder zu Polylinien verkettet
* ``subtract`` liefert den Teil **ausserhalb** des konvexen Bereichs (Knockout)
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .geom import EPS, ensure_ccw, lerp, point_in_polygon

Point = Tuple[float, float]


def half_planes(poly: Sequence[Point]) -> List[Tuple[float, float, float]]:
    """Konvexes Polygon -> Liste von Halbebenen ``(a, b, c)`` mit ``a*x+b*y+c <= 0`` innen."""
    pts = ensure_ccw(poly)
    n = len(pts)
    planes: List[Tuple[float, float, float]] = []
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) < EPS and abs(dy) < EPS:
            continue
        # Innen liegt links der Kante (CCW) -> Aussennormale ist (dy, -dx)
        a, b = dy, -dx
        c = -(a * x0 + b * y0)
        planes.append((a, b, c))
    return planes


def _signed(plane: Tuple[float, float, float], p: Point) -> float:
    return plane[0] * p[0] + plane[1] * p[1] + plane[2]


def clip_polygon(poly: Sequence[Point], clip: Sequence[Point]) -> List[Point]:
    """Sutherland-Hodgman: geschlossenes Polygon gegen konvexen Bereich."""
    out = list(poly)
    for plane in half_planes(clip):
        if not out:
            return []
        inp = out
        out = []
        n = len(inp)
        for i in range(n):
            cur = inp[i]
            nxt = inp[(i + 1) % n]
            dc = _signed(plane, cur)
            dn = _signed(plane, nxt)
            if dc <= 0:
                out.append(cur)
            if (dc < 0 < dn) or (dn < 0 < dc):
                t = dc / (dc - dn)
                out.append(lerp(cur, nxt, t))
    return out


def clip_segment(a: Point, b: Point, planes: Sequence[Tuple[float, float, float]]
                 ) -> Optional[Tuple[Point, Point]]:
    """Segment gegen konvexen Bereich (Cyrus-Beck)."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for pa, pb, pc in planes:
        denom = pa * dx + pb * dy
        num = pa * a[0] + pb * a[1] + pc
        if abs(denom) < EPS:
            if num > 0:
                return None
            continue
        t = -num / denom
        if denom > 0:
            if t < t1:
                t1 = t
        else:
            if t > t0:
                t0 = t
        if t0 > t1:
            return None
    return (lerp(a, b, t0), lerp(a, b, t1))


def clip_polyline(pts: Sequence[Point], clip: Sequence[Point], closed: bool = False
                  ) -> List[List[Point]]:
    """Offene (oder als Linienzug behandelte geschlossene) Polylinie beschneiden."""
    planes = half_planes(clip)
    src = list(pts) + ([pts[0]] if closed and len(pts) > 2 else [])
    pieces: List[List[Point]] = []
    current: List[Point] = []
    for i in range(len(src) - 1):
        seg = clip_segment(src[i], src[i + 1], planes)
        if seg is None:
            if len(current) > 1:
                pieces.append(current)
            current = []
            continue
        s, e = seg
        if not current:
            current = [s, e]
        else:
            if _close(current[-1], s):
                current.append(e)
            else:
                if len(current) > 1:
                    pieces.append(current)
                current = [s, e]
    if len(current) > 1:
        pieces.append(current)
    return [_dedupe_consecutive(p) for p in pieces if len(p) > 1]


def subtract_polyline(pts: Sequence[Point], clip: Sequence[Point], closed: bool = False
                      ) -> List[List[Point]]:
    """Teile der Polylinie **ausserhalb** des konvexen Bereichs (Knockout)."""
    planes = half_planes(clip)
    src = list(pts) + ([pts[0]] if closed and len(pts) > 2 else [])
    pieces: List[List[Point]] = []
    current: List[Point] = []

    def flush() -> None:
        nonlocal current
        if len(current) > 1:
            pieces.append(current)
        current = []

    def extend(seg: Tuple[Point, Point]) -> None:
        nonlocal current
        a, b = seg
        if _close(a, b):
            return
        if not current:
            current = [a, b]
        elif _close(current[-1], a):
            current.append(b)
        else:
            flush()
            current = [a, b]

    for i in range(len(src) - 1):
        a, b = src[i], src[i + 1]
        inside = clip_segment(a, b, planes)
        if inside is None or _close(inside[0], inside[1]):
            extend((a, b))        # komplett draussen (oder nur beruehrend)
            continue
        s, e = inside
        if not _close(a, s):
            extend((a, s))
        flush()                   # das Innenstueck unterbricht den Linienzug
        if not _close(e, b):
            extend((e, b))
    flush()
    return [_dedupe_consecutive(p) for p in pieces if len(p) > 1]


def polygon_intersects(poly: Sequence[Point], clip: Sequence[Point]) -> bool:
    """Grobtest: beruehrt/schneidet ``poly`` den konvexen Bereich ``clip``?"""
    planes = half_planes(clip)
    for p in poly:
        if all(_signed(pl, p) <= 1e-9 for pl in planes):
            return True
    for p in clip:
        if point_in_polygon(p, poly):
            return True
    n = len(poly)
    for i in range(n):
        if clip_segment(poly[i], poly[(i + 1) % n], planes) is not None:
            return True
    return False


def _close(a: Point, b: Point, tol: float = 1e-9) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _dedupe_consecutive(pts: Sequence[Point], tol: float = 1e-9) -> List[Point]:
    out: List[Point] = []
    for p in pts:
        if not out or not _close(out[-1], p, tol):
            out.append(p)
    return out
