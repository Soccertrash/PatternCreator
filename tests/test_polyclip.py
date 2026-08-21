"""Allgemeiner Polygon-Clipper (``core/polyclip.py``).

Der wichtigste Test ist der **Regressionsanker**: gegen einen rechteckigen
Rahmen muss der allgemeine Clipper dasselbe liefern wie der konvexe aus
``core/clip.py`` - sonst waere jede Standardform in Gefahr.
"""

import math
import random

import pytest

from core import clip as clipmod
from core import polyclip
from core.geom import polygon_area
from core.optimize import _self_intersects

RECT = [(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]
L_SHAPE = [(0.0, 0.0), (6.0, 0.0), (6.0, 2.0), (2.0, 2.0), (2.0, 6.0), (0.0, 6.0)]
U_SHAPE = [(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (4.0, 6.0), (4.0, 2.0),
           (2.0, 2.0), (2.0, 6.0), (0.0, 6.0)]


def star(center=(0.0, 0.0), r_out=5.0, r_in=2.0, points=8):
    pts = []
    for i in range(2 * points):
        r = r_out if i % 2 == 0 else r_in
        a = math.pi * i / points
        pts.append((center[0] + r * math.cos(a), center[1] + r * math.sin(a)))
    return pts


def comb(teeth=5, width=10.0, height=6.0, tooth=2.0):
    """Kamm: schmale Zaehne, dazwischen tiefe Schlitze."""
    pts = [(0.0, 0.0), (width, 0.0)]
    step = width / (2.0 * teeth - 1)
    x = width
    for i in range(2 * teeth - 1):
        top = height if i % 2 == 0 else height - tooth
        pts.append((x, top))
        x -= step
        pts.append((x, top))
    pts.append((0.0, height))
    return pts


def random_convex_cell(rnd):
    pts = [(rnd.uniform(-7, 7), rnd.uniform(-5, 5)) for _ in range(8)]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    from core.geom import convex_hull
    hull = convex_hull(pts)
    return hull if len(hull) >= 3 else [(cx, cy), (cx + 1, cy), (cx, cy + 1)]


def random_concave_cell(rnd):
    """Sternfoermiges Polygon mit stark schwankendem Radius."""
    cx, cy = rnd.uniform(-4, 4), rnd.uniform(-3, 3)
    n = rnd.randint(5, 9)
    return [(cx + rnd.uniform(0.6, 4.0) * math.cos(2 * math.pi * i / n),
             cy + rnd.uniform(0.6, 4.0) * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def same_ring(a, b, tol=1e-9):
    """Gleicher Ring bis auf den Startpunkt (beide CCW)."""
    from core.geom import ensure_ccw
    a = polyclip._dedupe(ensure_ccw(polyclip._prep(a)))
    b = polyclip._dedupe(ensure_ccw(polyclip._prep(b)))
    if len(a) != len(b):
        return False
    for shift in range(len(a)):
        if all(abs(a[(shift + i) % len(a)][0] - b[i][0]) <= tol
               and abs(a[(shift + i) % len(a)][1] - b[i][1]) <= tol
               for i in range(len(b))):
            return True
    return False


# ---------------------------------------------------------- Regressionsanker

def test_rect_frame_matches_the_convex_clipper_for_random_cells():
    """50 Zellen, rechteckiger Rahmen: gleiche Flaeche wie Sutherland-Hodgman.

    Bei Zellen, die der Rahmen in genau ein Stueck schneidet, muss sogar der
    Ring selbst uebereinstimmen. Zerfaellt eine konkave Zelle dagegen in mehrere
    Stuecke, liefert Sutherland-Hodgman einen einzigen, entarteten Ring mit
    Null-Breite-Verbindungen - genau deshalb gibt es dieses Modul. Die Flaeche
    stimmt auch dann.
    """
    rnd = random.Random(20260821)
    checked_rings = 0
    for i in range(50):
        cell = random_convex_cell(rnd) if i % 2 == 0 else random_concave_cell(rnd)
        mine = polyclip.clip_polygon_general(cell, RECT)
        ref = clipmod.clip_polygon(cell, RECT)
        area_ref = abs(polygon_area(ref)) if len(ref) >= 3 else 0.0
        area_mine = sum(abs(polygon_area(p)) for p in mine)
        assert area_mine == pytest.approx(area_ref, abs=1e-9), i
        if len(mine) == 1 and area_ref > 1e-9:
            assert same_ring(mine[0], ref), i
            checked_rings += 1
    assert checked_rings >= 45, "zu wenige Ringe direkt vergleichbar"


def test_rect_frame_matches_the_convex_polyline_clipper():
    rnd = random.Random(4711)
    for _ in range(50):
        pts = [(rnd.uniform(-9, 9), rnd.uniform(-6, 6)) for _ in range(4)]
        mine = polyclip.clip_polyline_general(pts, RECT, closed=False)
        ref = clipmod.clip_polyline(pts, RECT, closed=False)
        assert len(mine) == len(ref)
        for m, r in zip(mine, ref):
            assert len(m) == len(r)
            for pm, pr in zip(m, r):
                assert pm[0] == pytest.approx(pr[0], abs=1e-9)
                assert pm[1] == pytest.approx(pr[1], abs=1e-9)


# ------------------------------------------------------------ Konkave Rahmen

def test_u_shape_splits_a_cell_into_two_pieces():
    cell = [(1.0, 3.0), (5.0, 3.0), (5.0, 4.0), (1.0, 4.0)]
    pieces = polyclip.clip_polygon_general(cell, U_SHAPE)
    assert len(pieces) == 2
    assert sorted(round(abs(polygon_area(p)), 6) for p in pieces) == [1.0, 1.0]


def test_l_shape_clips_away_the_missing_quadrant():
    cell = [(1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)]
    pieces = polyclip.clip_polygon_general(cell, L_SHAPE)
    total = sum(abs(polygon_area(p)) for p in pieces)
    assert total == pytest.approx(1.0 * 4.0 + 4.0 * 1.0 - 1.0, abs=1e-9)


@pytest.mark.parametrize("frame", [star(), comb(), L_SHAPE, U_SHAPE])
def test_pieces_are_simple_and_fit_into_the_frame(frame):
    rnd = random.Random(99)
    frame_area = abs(polygon_area(frame))
    for _ in range(30):
        cell = random_concave_cell(rnd)
        cell = [(p[0] + 3.0, p[1] + 3.0) for p in cell]
        pieces = polyclip.clip_polygon_general(cell, frame)
        total = sum(abs(polygon_area(p)) for p in pieces)
        assert total <= min(abs(polygon_area(cell)), frame_area) + 1e-9
        for piece in pieces:
            assert len(piece) >= 3
            assert not _self_intersects(piece, True)
            assert polygon_area(piece) > 0        # CCW


def test_concave_cell_against_concave_frame():
    """Puzzle-Teil mit Nasen gegen die U-Form."""
    nub = [(1.0, 2.5), (2.5, 2.5), (2.5, 3.2), (3.0, 3.2), (3.0, 2.5),
           (5.0, 2.5), (5.0, 4.5), (1.0, 4.5)]
    pieces = polyclip.clip_polygon_general(nub, U_SHAPE)
    assert pieces
    total = sum(abs(polygon_area(p)) for p in pieces)
    assert total < abs(polygon_area(nub))
    for piece in pieces:
        assert not _self_intersects(piece, True)


def test_cell_completely_inside_keeps_its_exact_area():
    cell = [(0.5, 3.0), (1.5, 3.0), (1.5, 5.0), (0.5, 5.0)]
    pieces = polyclip.clip_polygon_general(cell, U_SHAPE)
    assert len(pieces) == 1
    assert abs(polygon_area(pieces[0])) == pytest.approx(2.0, abs=1e-12)


# ---------------------------------------------------------- Degenerationen

def test_cell_edge_exactly_on_the_frame_edge():
    frame = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    cell = [(1.0, 0.0), (3.0, 0.0), (3.0, 1.0), (1.0, 1.0)]
    pieces = polyclip.clip_polygon_general(cell, frame)
    assert len(pieces) == 1
    assert abs(polygon_area(pieces[0])) == pytest.approx(2.0, abs=1e-12)


def test_cell_corner_on_the_frame_edge():
    frame = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    cell = [(2.0, 0.0), (3.0, 1.0), (2.0, 2.0), (1.0, 1.0)]
    pieces = polyclip.clip_polygon_general(cell, frame)
    assert len(pieces) == 1
    assert abs(polygon_area(pieces[0])) == pytest.approx(2.0, abs=1e-9)


def test_cell_touching_the_frame_in_a_single_point_is_empty():
    frame = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    cell = [(4.0, 4.0), (8.0, 4.0), (8.0, 8.0), (4.0, 8.0)]
    assert polyclip.clip_polygon_general(cell, frame) == []


def test_cell_sharing_only_an_edge_is_empty():
    frame = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    cell = [(4.0, 0.0), (8.0, 0.0), (8.0, 4.0), (4.0, 4.0)]
    assert polyclip.clip_polygon_general(cell, frame) == []


def test_cell_enclosing_the_frame_yields_the_frame():
    pieces = polyclip.clip_polygon_general(
        [(-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0)], U_SHAPE)
    assert len(pieces) == 1
    assert abs(polygon_area(pieces[0])) == pytest.approx(abs(polygon_area(U_SHAPE)),
                                                        abs=1e-9)


def test_cell_identical_to_the_frame_yields_the_cell():
    pieces = polyclip.clip_polygon_general(U_SHAPE, U_SHAPE)
    assert len(pieces) == 1
    assert same_ring(pieces[0], U_SHAPE)


def test_collinear_overlap_is_reported_with_both_endpoints():
    hits = polyclip.segment_intersections((0.0, 0.0), (4.0, 0.0),
                                          (1.0, 0.0), (3.0, 0.0))
    assert len(hits) == 2
    assert [round(t, 9) for t, _ in hits] == [0.25, 0.75]


def test_touching_segments_count_as_intersections():
    hits = polyclip.segment_intersections((0.0, 0.0), (2.0, 0.0),
                                          (1.0, 0.0), (1.0, 2.0))
    assert hits == [(0.5, 0.0)]


def test_point_on_boundary_uses_the_tolerance():
    sq = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    assert polyclip.point_on_boundary((2.0, 0.0), sq)
    assert polyclip.point_on_boundary((2.0, 1e-9), sq)
    assert not polyclip.point_on_boundary((2.0, 0.5), sq)


# ---------------------------------------------------------------- Polylinien

def test_polyline_through_a_notch_comes_back_in_two_pieces():
    pieces = polyclip.clip_polyline_general([(-1.0, 3.0), (7.0, 3.0)], U_SHAPE)
    assert len(pieces) == 2
    assert pieces[0][0] == pytest.approx((0.0, 3.0))
    assert pieces[1][-1] == pytest.approx((6.0, 3.0))


def test_polyline_outside_the_frame_disappears():
    assert polyclip.clip_polyline_general([(20.0, 20.0), (30.0, 30.0)], U_SHAPE) == []


def test_closed_polyline_is_treated_as_a_ring():
    ring = [(1.0, 3.0), (5.0, 3.0), (5.0, 4.0), (1.0, 4.0)]
    pieces = polyclip.clip_polyline_general(ring, U_SHAPE, closed=True)
    assert len(pieces) >= 2
    for piece in pieces:
        for p in piece:
            assert polyclip.grid_for(U_SHAPE).inside_or_on(p)


# --------------------------------------------------------- fully_inside / Raster

def test_polygon_fully_inside_sees_the_notch():
    inside = [(0.5, 3.0), (1.5, 3.0), (1.5, 5.0), (0.5, 5.0)]
    across = [(1.0, 3.0), (5.0, 3.0), (5.0, 4.0), (1.0, 4.0)]
    assert polyclip.polygon_fully_inside(inside, U_SHAPE)
    assert not polyclip.polygon_fully_inside(across, U_SHAPE)


def test_polygon_touching_the_frame_from_inside_counts_as_inside():
    frame = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    assert polyclip.polygon_fully_inside([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)], frame)


def test_grid_classifies_boxes():
    grid = polyclip.grid_for(U_SHAPE)
    assert grid.classify_bbox(0.2, 0.2, 1.0, 1.0) == "inside"
    assert grid.classify_bbox(2.5, 3.0, 3.5, 4.0) == "outside"
    assert grid.classify_bbox(1.0, 1.0, 5.0, 5.0) == "mixed"
    assert grid.classify_bbox(100.0, 100.0, 101.0, 101.0) == "outside"


def test_grid_is_cached_per_point_sequence():
    a = polyclip.grid_for(U_SHAPE)
    b = polyclip.grid_for(list(U_SHAPE))
    assert a is b


# ------------------------------------------------------------- Determinismus

def test_two_identical_calls_give_identical_results():
    cell = [(1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)]
    first = polyclip.clip_polygon_general(cell, star())
    second = polyclip.clip_polygon_general(cell, star())
    assert first == second
    assert (polyclip.clip_polyline_general(cell, star(), closed=True)
            == polyclip.clip_polyline_general(cell, star(), closed=True))
