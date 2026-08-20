"""Linien -> geschlossene Streifen ("Stroking").

Im Flaechenmodus wird jede Kurve zu einem geschlossenen, extrudierbaren Profil:

* **offene** Polylinie -> ein Ring (linke Seite vorwaerts, rechte Seite rueckwaerts,
  flache Endkappen)
* **geschlossene** Polylinie -> zwei Ringe (aussen + innen); Fusion erkennt den
  Zwischenraum als Profil

Die Versaetze entstehen ueber Winkelhalbierende mit Gehrungsbegrenzung
(``miter_limit``); zu spitze Ecken werden abgeschraegt (Bevel), damit keine
selbstschneidenden Profile entstehen.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .geom import EPS, add, dist, length, mul, normalize, polygon_area, sub

Point = Tuple[float, float]

MITER_LIMIT = 4.0


def _clean(pts: Sequence[Point], closed: bool, tol: float = 1e-9) -> List[Point]:
    out: List[Point] = []
    for p in pts:
        if not out or dist(out[-1], p) > tol:
            out.append(p)
    if closed and len(out) > 2 and dist(out[0], out[-1]) <= tol:
        out.pop()
    return out


def _normals(pts: Sequence[Point], closed: bool) -> List[Point]:
    """Einheits-Normalen (links der Laufrichtung) je Segment."""
    n = len(pts)
    segs = n if closed else n - 1
    out: List[Point] = []
    for i in range(segs):
        d = normalize(sub(pts[(i + 1) % n], pts[i]))
        out.append((-d[1], d[0]))
    return out


def offset_polyline(pts: Sequence[Point], offsets: Sequence[float], closed: bool,
                    miter_limit: float = MITER_LIMIT) -> List[Point]:
    """Polylinie um ``offsets[i]`` (positiv = nach links) versetzen."""
    n = len(pts)
    if n < 2:
        return list(pts)
    normals = _normals(pts, closed)
    out: List[Point] = []
    for i in range(n):
        d = offsets[i] if i < len(offsets) else offsets[-1]
        if closed:
            n_prev = normals[(i - 1) % len(normals)]
            n_next = normals[i % len(normals)]
        else:
            if i == 0:
                out.append(add(pts[0], mul(normals[0], d)))
                continue
            if i == n - 1:
                out.append(add(pts[-1], mul(normals[-1], d)))
                continue
            n_prev = normals[i - 1]
            n_next = normals[i]
        m = add(n_prev, n_next)
        lm = length(m)
        if lm < 2.0 / miter_limit:      # Gehrung waere zu lang -> Bevel
            out.append(add(pts[i], mul(n_prev, d)))
            out.append(add(pts[i], mul(n_next, d)))
        else:
            out.append(add(pts[i], mul(m, 2.0 * d / (lm * lm))))
    return out


def _widths(pts: Sequence[Point], width, ) -> List[float]:
    if isinstance(width, (int, float)):
        return [float(width)] * len(pts)
    w = list(width)
    if len(w) < len(pts):
        w += [w[-1]] * (len(pts) - len(w))
    return [float(v) for v in w[:len(pts)]]


def stroke_open(pts: Sequence[Point], width, miter_limit: float = MITER_LIMIT
                ) -> Optional[List[Point]]:
    """Offene Polylinie -> ein geschlossenes Polygon (Streifen mit flachen Kappen)."""
    p = _clean(pts, closed=False)
    if len(p) < 2:
        return None
    w = _widths(p, width)
    left = offset_polyline(p, [+v / 2.0 for v in w], closed=False, miter_limit=miter_limit)
    right = offset_polyline(p, [-v / 2.0 for v in w], closed=False, miter_limit=miter_limit)
    ring = left + list(reversed(right))
    ring = _clean(ring, closed=True)
    if len(ring) < 3 or abs(polygon_area(ring)) < 1e-10:
        return None
    return ring


def stroke_closed(pts: Sequence[Point], width, miter_limit: float = MITER_LIMIT
                  ) -> List[List[Point]]:
    """Geschlossene Polylinie -> Aussen- und Innenring (Kreisring-Profil)."""
    p = _clean(pts, closed=True)
    if len(p) < 3:
        return []
    if polygon_area(p) < 0:
        p = list(reversed(p))
    w = _widths(p, width)
    outer = offset_polyline(p, [-v / 2.0 for v in w], closed=True, miter_limit=miter_limit)
    inner = offset_polyline(p, [+v / 2.0 for v in w], closed=True, miter_limit=miter_limit)
    rings: List[List[Point]] = []
    outer = _clean(outer, closed=True)
    inner = _clean(inner, closed=True)
    if len(outer) >= 3 and abs(polygon_area(outer)) > 1e-10:
        rings.append(outer)
    # Innenring nur, wenn er nicht kollabiert ist (Dicke >= Zellgroesse)
    if (len(inner) >= 3 and abs(polygon_area(inner)) > 1e-10
            and polygon_area(inner) * polygon_area(p) > 0
            and abs(polygon_area(inner)) < abs(polygon_area(p))):
        rings.append(inner)
    return rings


def stroke(pts: Sequence[Point], closed: bool, width,
           miter_limit: float = MITER_LIMIT) -> List[List[Point]]:
    """Einheitlicher Einstieg: liefert immer geschlossene Ringe."""
    if closed:
        return stroke_closed(pts, width, miter_limit)
    ring = stroke_open(pts, width, miter_limit)
    return [ring] if ring else []


def stroke_segments(segments: Sequence[Tuple[Point, Point]], width: float
                    ) -> List[List[Point]]:
    """Einzelsegmente (z. B. deduplizierte Zellkanten) zu Rechteck-Profilen."""
    out: List[List[Point]] = []
    for a, b in segments:
        if dist(a, b) < EPS:
            continue
        ring = stroke_open([a, b], width)
        if ring:
            out.append(ring)
    return out
