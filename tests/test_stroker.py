"""Stroker: Linien -> geschlossene, extrudierbare Profile."""

import math
from unittest import mock

import pytest

import core.stroker as stroker
from core.geom import bbox, polygon_area
from core.stroker import offset_polyline, stroke, stroke_closed, stroke_open


def _self_intersects(poly):
    """Naive O(n²)-Pruefung auf Selbstschnitt (nur fuer kleine Testpolygone)."""
    n = len(poly)

    def seg(i):
        return poly[i], poly[(i + 1) % n]

    def inter(a, b, c, d):
        def cr(o, p, q):
            return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
        d1, d2 = cr(c, d, a), cr(c, d, b)
        d3, d4 = cr(a, b, c), cr(a, b, d)
        return ((d1 > 1e-12) != (d2 > 1e-12)) and ((d3 > 1e-12) != (d4 > 1e-12))

    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            a, b = seg(i)
            c, d = seg(j)
            if inter(a, b, c, d):
                return True
    return False


def test_open_line_becomes_closed_rectangle():
    ring = stroke_open([(0.0, 0.0), (4.0, 0.0)], 0.2)
    assert ring is not None
    assert len(ring) == 4
    assert abs(polygon_area(ring)) == pytest.approx(4.0 * 0.2, rel=1e-6)


def test_stroke_width_scales_the_area():
    thin = stroke_open([(0.0, 0.0), (3.0, 0.0)], 0.1)
    thick = stroke_open([(0.0, 0.0), (3.0, 0.0)], 0.4)
    assert abs(polygon_area(thick)) == pytest.approx(4 * abs(polygon_area(thin)), rel=1e-6)


def test_corner_uses_a_mitre_and_stays_simple():
    ring = stroke_open([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)], 0.2)
    assert ring is not None
    assert not _self_intersects(ring)
    assert abs(polygon_area(ring)) > 0


def test_sharp_corner_falls_back_to_a_bevel():
    """Bei sehr spitzem Winkel darf keine unendlich lange Gehrung entstehen."""
    pts = [(0.0, 0.0), (2.0, 0.0), (0.02, 0.05)]
    ring = stroke_open(pts, 0.2)
    assert ring is not None
    x0, y0, x1, y1 = bbox(ring)
    assert (x1 - x0) < 6.0 and (y1 - y0) < 6.0


def test_closed_path_yields_outer_and_inner_ring():
    square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    rings = stroke_closed(square, 0.2)
    assert len(rings) == 2
    outer, inner = rings
    assert abs(polygon_area(outer)) > abs(polygon_area(inner))
    assert abs(polygon_area(outer)) == pytest.approx(2.2 * 2.2, rel=1e-6)
    assert abs(polygon_area(inner)) == pytest.approx(1.8 * 1.8, rel=1e-6)


def test_closed_path_drops_inner_ring_when_thickness_exceeds_cell():
    square = [(0.0, 0.0), (0.2, 0.0), (0.2, 0.2), (0.0, 0.2)]
    rings = stroke_closed(square, 1.0)
    assert len(rings) == 1                    # Innenring kollabiert -> Vollprofil


def test_variable_width_is_honoured_per_vertex():
    pts = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    ring = stroke_open(pts, [0.1, 0.4, 0.1])
    ys = [y for _x, y in ring]
    assert max(ys) == pytest.approx(0.2, abs=1e-9)
    assert min(ys) == pytest.approx(-0.2, abs=1e-9)


def test_stroke_dispatches_on_closed_flag():
    assert len(stroke([(0.0, 0.0), (1.0, 0.0)], False, 0.1)) == 1
    assert len(stroke([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], True, 0.05)) == 2


def test_degenerate_input_is_ignored():
    assert stroke_open([(1.0, 1.0)], 0.1) is None
    assert stroke_open([(1.0, 1.0), (1.0, 1.0)], 0.1) is None
    assert stroke_closed([(0.0, 0.0), (1.0, 0.0)], 0.1) == []


def test_offset_polyline_keeps_distance():
    pts = [(0.0, 0.0), (5.0, 0.0)]
    up = offset_polyline(pts, [0.5, 0.5], closed=False)
    assert all(y == pytest.approx(0.5) for _x, y in up)


# ------------------------------------------------- Schleifen im Versatz

def unguarded():
    """Der Stroker ohne ``remove_loops`` - der Stand vor dem Fix."""
    return mock.patch.object(stroker, "remove_loops", lambda pts, **kw: list(pts))


def clipped_circle(radius, cut, segments=48):
    """Kreis, an der Geraden ``y = cut`` beschnitten - die Sehne schließt ihn.

    Genau diese Kontur liefert das Clipping an der Rahmenkante: ein
    angeschnittener Phyllotaxis-Kreis. An den beiden Sehnenenden trifft die
    Sehne so flach auf den Bogen, dass der Gehrungs-Versatz dort eine Schleife
    anlegt.
    """
    arc = [(radius * math.cos(2 * math.pi * i / segments),
            radius * math.sin(2 * math.pi * i / segments))
           for i in range(segments)]
    x = math.sqrt(max(0.0, radius * radius - cut * cut))
    return [(-x, cut)] + [p for p in arc if p[1] <= cut] + [(x, cut)]


#: Ein Streifen, der zweimal dicht an sich selbst vorbeiläuft: der Versatz
#: überschlägt sich in der engen Kehre.
DOUBLE_HAIRPIN = [(0.0, 0.0), (1.0, 0.0), (1.0, 0.05), (0.5, 0.05),
                  (0.5, 0.1), (1.5, 0.1)]


def test_the_unguarded_stroker_really_would_loop():
    """Gegenprobe: ohne ``remove_loops`` schneiden sich diese Profile."""
    with unguarded():
        assert _self_intersects(stroke_open(DOUBLE_HAIRPIN, 0.1))
        assert all(_self_intersects(r)
                   for r in stroke_closed(clipped_circle(0.1, 0.095), 0.08))


def test_an_open_stroke_never_self_intersects():
    ring = stroke_open(DOUBLE_HAIRPIN, 0.1)
    assert ring is not None
    assert not _self_intersects(ring)


def test_a_clipped_circle_strokes_into_clean_rings():
    """Der häufigste Fall aus der Praxis: Motiv an der Rahmenkante angeschnitten."""
    rings = stroke_closed(clipped_circle(0.1, 0.095), 0.08)
    assert len(rings) == 2
    assert all(not _self_intersects(r) for r in rings)
    assert abs(polygon_area(rings[0])) > abs(polygon_area(rings[1]))


def test_removing_a_loop_keeps_the_larger_side():
    """Die Schleife ist der Fehler - der Streifen selbst muss stehen bleiben."""
    with unguarded():
        raw = stroke_open(DOUBLE_HAIRPIN, 0.1)
    ring = stroke_open(DOUBLE_HAIRPIN, 0.1)
    assert 0.0 < abs(polygon_area(ring)) < abs(polygon_area(raw))
    x0, y0, x1, y1 = bbox(ring)
    # Flache Endkappen: der Streifen reicht genau so weit wie die Mittellinie,
    # quer dazu um die halbe Breite.
    assert (x0, y0, x1, y1) == pytest.approx((0.0, -0.05, 1.5, 0.15), abs=1e-9)


def test_a_simple_ring_is_untouched_by_the_loop_removal():
    """Ohne Selbstschnitt darf sich kein Punkt bewegen (Schraffur, Stege)."""
    pts = [(0.0, 0.0), (3.0, 0.0), (3.0, 2.0)]
    with unguarded():
        raw = stroke_open(pts, 0.2)
    assert stroke_open(pts, 0.2) == raw
    square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    with unguarded():
        raw_rings = stroke_closed(square, 0.2)
    assert stroke_closed(square, 0.2) == raw_rings
