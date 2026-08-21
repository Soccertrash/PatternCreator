"""Geometrie-Helfer: Deduplizierung, Verkettung, Glättung, Inset."""

import math

import pytest

from core import geom
from core.geom import (chaikin, chain_segments, dedupe_segments, inset_polygon,
                       remove_loops,
                       poisson_disk, polygon_area, polygon_segments, resample,
                       snap_segments)

SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def test_shared_edges_are_deduplicated():
    left = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    right = [(1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0)]
    segs = polygon_segments(left) + polygon_segments(right)
    assert len(segs) == 8
    assert len(dedupe_segments(segs)) == 7        # gemeinsame Kante nur einmal


def test_dedupe_is_direction_independent():
    segs = [((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (0.0, 0.0))]
    assert len(dedupe_segments(segs)) == 1


def test_snap_segments_merges_floating_point_noise():
    a = [((0.0, 0.0), (1.0, 0.0))]
    b = [((1.0 + 1e-12, 0.0), (0.0, 0.0))]
    assert len(snap_segments(a + b)) == 1


def test_chain_segments_builds_one_ring_from_a_square():
    chains = chain_segments(snap_segments(polygon_segments(SQUARE)))
    assert len(chains) == 1
    pts, closed = chains[0]
    assert closed
    assert len(pts) == 4


def test_chain_segments_splits_at_junctions():
    """Ein T-Stueck ergibt drei Ketten (Knoten mit Grad 3 beendet die Kette)."""
    segs = [((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (2.0, 0.0)),
            ((1.0, 0.0), (1.0, 1.0))]
    chains = chain_segments(snap_segments(segs))
    assert len(chains) == 3
    assert all(not closed for _pts, closed in chains)


def test_chaikin_rounds_corners_and_keeps_area_similar():
    rounded = chaikin(SQUARE, 2, closed=True)
    assert len(rounded) > len(SQUARE)
    assert abs(polygon_area(rounded)) < abs(polygon_area(SQUARE))
    assert abs(polygon_area(rounded)) > 0.7 * abs(polygon_area(SQUARE))


def test_inset_polygon_shrinks_and_collapses_when_too_large():
    smaller = inset_polygon(SQUARE, 0.2)
    assert abs(polygon_area(smaller)) == pytest.approx(0.36, rel=1e-6)
    assert inset_polygon(SQUARE, 0.7) is None


def test_resample_produces_even_spacing():
    pts = resample([(0.0, 0.0), (1.0, 0.0)], 0.25)
    assert len(pts) == 5
    for i in range(len(pts) - 1):
        assert pts[i + 1][0] - pts[i][0] == pytest.approx(0.25)


def test_poisson_disk_respects_minimum_distance_and_is_deterministic():
    import random
    a = poisson_disk(0, 0, 5, 5, 0.5, random.Random(7))
    b = poisson_disk(0, 0, 5, 5, 0.5, random.Random(7))
    assert a == b
    assert len(a) > 20
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            assert math.hypot(a[i][0] - a[j][0], a[i][1] - a[j][1]) >= 0.5 - 1e-9


def test_remove_loops_drops_the_smaller_loop():
    """Der Gehrungs-Offset legt an engen Einbuchtungen eine Schleife an."""
    bowtie = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (3.0, 4.0), (3.0, -1.0), (0.0, 4.0)]
    cleaned = remove_loops(bowtie)
    assert len(cleaned) >= 3
    for i in range(len(cleaned)):
        a, b = cleaned[i], cleaned[(i + 1) % len(cleaned)]
        for j in range(i + 2, len(cleaned)):
            if i == 0 and j == len(cleaned) - 1:
                continue
            c, d = cleaned[j], cleaned[(j + 1) % len(cleaned)]
            assert not _crosses(a, b, c, d)


def test_remove_loops_keeps_a_clean_polygon_untouched():
    square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    assert remove_loops(square) == square


def _crosses(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) > 0) != (o(a, b, d) > 0) and (o(c, d, a) > 0) != (o(c, d, b) > 0)


# ------------------------------------------------- Kurvenstuecke verketten

def test_chain_polylines_joins_pieces_in_any_order_and_direction():
    """Fusion liefert die Kurven eines Loops ungeordnet und ungerichtet."""
    pieces = [[(0, 0), (4, 0)], [(4, 4), (4, 0)], [(4, 4), (0, 4)], [(0, 4), (0, 0)]]
    ring = geom.chain_polylines(pieces)
    assert ring == [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]


def test_chain_polylines_works_in_three_dimensions():
    pieces = [[(0, 0, 1), (4, 0, 1)], [(4, 0, 1), (0, 0, 1)][::-1]]
    assert geom.chain_polylines(pieces) is not None


def test_chain_polylines_reports_an_open_contour():
    assert geom.chain_polylines([[(0, 0), (4, 0)], [(4, 4), (0, 4)]]) is None
    assert geom.chain_polylines([]) is None


def test_chain_polylines_tolerates_tiny_gaps():
    pieces = [[(0, 0), (4, 0)], [(4, 1e-6), (4, 4)], [(4, 4), (0, 4)],
              [(0, 4), (0, 0)]]
    assert geom.chain_polylines(pieces, tol=1e-4) is not None
    assert geom.chain_polylines(pieces, tol=1e-9) is None
