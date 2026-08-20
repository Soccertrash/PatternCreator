"""Organische Zellen: Saat, Rundung, Fuge.

Die Regressionen, die hier abgesichert werden, hatten alle dieselbe sichtbare
Folge: aus einer verlorenen oder kaputten Zelle wird im Flächenmodell massives
Material - genau die "großen Flächen", die das Muster unbrauchbar machen.
"""

import math
import random

import pytest

from core.geom import (clean_polygon, convex_hull, erode_convex, is_convex,
                       point_in_polygon, polygon_area)
from generators.base import GenContext
from generators.organic_cells import (build_cells, round_corners, scatter_sites,
                                      voronoi_cells)

BBOX = (-5.0, -3.0, 5.0, 3.0)


def ctx(seed=42):
    return GenContext(bbox=BBOX, rnd=random.Random(seed))


# ------------------------------------------------------------------- Saat

def test_scatter_delivers_exactly_the_requested_count():
    for count in (3, 50, 500):
        assert len(scatter_sites(BBOX, count, random.Random(1))) == count


def test_scatter_keeps_a_minimum_distance():
    """Rein zufällige Punkte liegen paarweise aufeinander - daraus wurden Splitter."""
    pts = scatter_sites(BBOX, 200, random.Random(3))
    closest = min(math.dist(a, b)
                  for i, a in enumerate(pts) for b in pts[i + 1:])
    assert closest > 0.5 * 0.75 * math.sqrt(60.0 / 200)


def test_cell_sizes_stay_within_one_order_of_magnitude():
    cells = build_cells(ctx(), count=260, relax=1, smooth=2, inset=0.08)
    areas = sorted(abs(polygon_area(c)) for c in cells)
    assert areas[-1] / areas[0] < 30.0        # vorher: Faktor 1100


# ------------------------------------------------------------------- Zellen

def test_voronoi_cells_are_convex_and_free_of_folds():
    sites = scatter_sites(BBOX, 120, random.Random(5))
    for cell in voronoi_cells(sites, BBOX):
        assert is_convex(cell), cell
        assert clean_polygon(cell) == [tuple(p) for p in cell]


def test_the_gap_does_not_swallow_cells():
    """``inset_polygon`` verwarf bei Rundheit 2 mehr als die Hälfte aller Zellen."""
    for smooth in (0, 1, 2, 3):
        cells = build_cells(ctx(), count=110, relax=1, smooth=smooth, inset=0.08)
        assert len(cells) == 110, (smooth, len(cells))


def test_cells_shrink_by_exactly_the_gap():
    cells_raw = build_cells(ctx(), count=60, relax=1, smooth=0, inset=0.0)
    cells_gap = build_cells(ctx(), count=60, relax=1, smooth=0, inset=0.1)
    for raw, small in zip(cells_raw, cells_gap):
        for p in small:
            assert point_in_polygon(p, raw)


# ------------------------------------------------------------------- Rundung

def test_rounding_stays_inside_the_cell():
    """Sonst würden benachbarte Zellen ineinander laufen (überlappende Löcher)."""
    cell = [(0.0, 0.0), (2.0, 0.0), (2.4, 1.2), (1.0, 2.0), (-0.2, 1.0)]
    for factor in (0.4, 0.7, 1.0):
        for p in round_corners(cell, factor):
            assert point_in_polygon(p, cell) or _on_edge(p, cell)


def test_rounding_keeps_the_edge_midpoints():
    """Die Zelle liegt weiter an ihrer Voronoi-Kante an - das hält das Muster dicht."""
    cell = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    rounded = round_corners(cell, 1.0)
    # 1.0 rundet maximal, die Kontur laeuft trotzdem durch die Kantenmitte
    # (2 % Rest, damit sich zwei Ecken die Kante nicht streitig machen).
    assert min(math.dist((2.0, 0.0), p) for p in rounded) < 0.02 * 4.0


def test_rounding_never_folds_over_short_edges():
    """Zwei Ecken dürfen sich dieselbe (kurze) Kante nicht doppelt wegschneiden."""
    cell = [(0.0, 0.0), (3.0, 0.0), (3.02, 0.01), (3.0, 2.0), (0.0, 2.0)]
    rounded = round_corners(cell, 1.0)
    assert abs(polygon_area(rounded)) > 0.8 * abs(polygon_area(cell))


def test_rounding_reduces_the_area_less_than_chaikin_did():
    cell = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    kept = abs(polygon_area(round_corners(cell, 0.7))) / abs(polygon_area(cell))
    assert kept > 0.9


# -------------------------------------------------------------- Erosion

def test_erode_convex_is_exact_for_a_square():
    square = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    small = erode_convex(square, 1.0)
    assert abs(abs(polygon_area(small)) - 4.0) < 1e-9


def test_erode_convex_drops_a_cell_that_is_thinner_than_the_gap():
    sliver = [(0.0, 0.0), (4.0, 0.0), (4.0, 0.05), (0.0, 0.05)]
    assert erode_convex(sliver, 0.1) is None


def test_erode_convex_cuts_a_sharp_tip_instead_of_folding_it():
    """Der Gehrungs-Offset legte an dieser Spitze eine Schleife an."""
    tip = [(0.0, 0.0), (5.0, 0.1), (5.0, -0.1), (0.0, -1.0), (-1.0, -0.5)]
    small = erode_convex(convex_hull(tip), 0.15)
    assert small is not None
    assert is_convex(small)
    assert max(p[0] for p in small) < 4.9


def test_convex_hull_removes_a_fold():
    folded = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (1.999, 1.998), (0.0, 2.0)]
    assert len(convex_hull(folded)) == 4


def _on_edge(p, poly, tol=1e-9):
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        abx, aby = b[0] - a[0], b[1] - a[1]
        ll = abx * abx + aby * aby
        if ll < 1e-15:
            continue
        t = max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / ll))
        if math.dist(p, (a[0] + abx * t, a[1] + aby * t)) <= tol:
            return True
    return False
