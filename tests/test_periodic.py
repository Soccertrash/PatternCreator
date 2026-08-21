"""Periodischer Modus: das Muster muss sich nach einem Umlauf wiederholen.

Wird ein Muster auf eine Mantelfläche gewickelt, liegen die linke und die rechte
Kante des Fensters hinterher aufeinander. Beide Bedingungen werden hier geprüft:

1. **Fortsetzbarkeit** – dasselbe Muster im um eine Periode versetzten Fenster
   ist das um eine Periode verschobene Original. Ohne das hätte die Naht einen
   Versatz, und der wäre auf dem Zylinder sofort zu sehen.
2. **Naht auf einer Zellgrenze**, wo die Musterform das hergibt. Bei Mustern
   ohne senkrechte Zellwände (Rauten, schiefes Gitter, Wabe mit Fläche oben)
   ist das geometrisch unmöglich – dort ist die Naht ein zusätzlicher Steg
   (siehe ``Context.md`` 15.7).
"""

import math
import random

import pytest

import generators
from core import ir
from generators.base import GenContext
from generators._util import snap_period

PERIOD = 15.0            # cm - Umfang eines Zylinders mit r ~ 24 mm
HEIGHT = 6.0


def context(period=PERIOD, x0=0.0, seed=42):
    return GenContext(bbox=(x0, -HEIGHT / 2.0, x0 + period, HEIGHT / 2.0),
                      rnd=random.Random(seed), thickness=0.1,
                      fill_target="webs", mode="area", period_x=period)


def cells(pattern_id, params=None, ctx=None):
    gen = generators.get_generator(pattern_id)
    merged = gen.defaults()
    merged.update(params or {})
    out = []
    for el in gen.generate(merged, ctx or context()):
        if isinstance(el, ir.Path) and el.role == ir.ROLE_REGION:
            out.append(el.points)
    return out


def centroids_in_window(polys, x0, x1):
    """Schwerpunkte der Zellen, die im Fenster liegen (auf 1e-6 gerundet)."""
    from core.geom import centroid
    out = []
    for poly in polys:
        c = centroid(poly)
        if x0 - 1e-9 <= c[0] <= x1 + 1e-9:
            out.append((round(c[0] - x0, 6), round(c[1], 6)))
    return sorted(out)


LATTICE = [
    ("grid", {}),
    ("grid", {"spacingX": 1.1, "spacingY": 0.7}),
    ("grid", {"skew": 65.0}),
    ("rhombus", {}),
    ("honeycomb", {"orientation": "flat"}),
    ("honeycomb", {"orientation": "pointy"}),
    ("brick", {"bond": "half"}),
    ("brick", {"bond": "stack"}),
    ("puzzle", {"countX": 6, "countY": 4}),
]


@pytest.mark.parametrize("pattern_id,params", LATTICE,
                         ids=[p[0] + str(sorted(p[1].items())) for p in LATTICE])
def test_pattern_continues_across_the_seam(pattern_id, params):
    """Fenster um eine Periode versetzt ⇒ dasselbe Muster, nur verschoben."""
    left = cells(pattern_id, params, context(x0=0.0))
    right = cells(pattern_id, params, context(x0=PERIOD))
    a = centroids_in_window(left, 0.0, PERIOD)
    b = centroids_in_window(right, PERIOD, 2 * PERIOD)
    assert a, "keine Zellen erzeugt"
    assert len(a) == len(b)
    for pa, pb in zip(a, b):
        assert pa == pytest.approx(pb, abs=1e-6)


#: Muster, deren Zellen in **jeder** Reihe eine senkrechte Wand haben. Nur dort
#: kann die Naht auf einer Zellgrenze liegen und damit unsichtbar werden.
VERTICAL_WALLS = [
    ("grid", {}),
    ("brick", {"bond": "stack"}),
    ("puzzle", {"countX": 6, "countY": 4}),
]

#: Versetzte oder schräge Muster: hier ist eine gerade Naht geometrisch nie eine
#: Zellgrenze - jede zweite Reihe wird durchschnitten. Der Steg an der Naht ist
#: trotzdem genau einen Steg breit, das Muster läuft ohne Versatz durch; nur
#: sieht man die Trennung. Siehe ``Context.md`` 15.7.
STAGGERED = [
    ("honeycomb", {"orientation": "pointy"}),
    ("honeycomb", {"orientation": "flat"}),
    ("rhombus", {}),
    ("grid", {"skew": 65.0}),
    ("brick", {"bond": "half"}),
]


def crosses_seam(polys, seam=0.0):
    """Zellen, die die Naht wirklich durchschneiden (nicht nur berühren)."""
    out = []
    for poly in polys:
        xs = [p[0] for p in poly]
        if min(xs) < seam - 1e-9 and max(xs) > seam + 1e-9:
            out.append(poly)
    return out


@pytest.mark.parametrize("pattern_id,params", VERTICAL_WALLS,
                         ids=[p[0] for p in VERTICAL_WALLS])
def test_the_seam_is_a_cell_boundary(pattern_id, params):
    """Kein Loch schneidet die Naht: an x = 0 liegt eine Zellwand."""
    assert not crosses_seam(cells(pattern_id, params, context()))


@pytest.mark.parametrize("pattern_id,params", STAGGERED,
                         ids=["%s%s" % (p[0], sorted(p[1].values())) for p in STAGGERED])
def test_staggered_patterns_are_cut_by_the_seam(pattern_id, params):
    """Festgehalten, was **nicht** geht - damit es nicht unbemerkt kippt.

    Versetzte Muster haben in jeder zweiten Reihe keine Wand an der Naht. Das
    ist keine Nachlässigkeit, sondern Geometrie: die Reihen sind um eine halbe
    Zelle versetzt, eine gerade Linie kann nicht in beiden eine Grenze sein.
    """
    cut = crosses_seam(cells(pattern_id, params, context()))
    assert cut, ("%s: unerwartet sauber - dann kann die Zusicherung in "
                 "Context.md 15.7 verschärft werden" % pattern_id)


# ------------------------------------------------------------------ Rasten

def test_snap_period_hits_an_integer_divisor():
    assert snap_period(1.0, 10.0) == pytest.approx(1.0)
    assert snap_period(0.9, 10.0) == pytest.approx(10.0 / 11.0)
    assert snap_period(3.0, 10.0) == pytest.approx(10.0 / 3.0)
    # Größer als die Periode: genau ein Umlauf
    assert snap_period(20.0, 10.0) == pytest.approx(10.0)
    # Ohne Periode bleibt der Wert unverändert
    assert snap_period(1.234, 0.0) == pytest.approx(1.234)


def test_grid_spacing_snaps_to_a_divisor_of_the_period():
    ctx = context()
    raw = sorted(min(p[0] for p in poly)
                 for poly in cells("grid", {"spacingX": 1.1}, ctx))
    xs = []
    for x in raw:                      # ohne Runden entdoppeln
        if not xs or x - xs[-1] > 1e-9:
            xs.append(x)
    steps = [b - a for a, b in zip(xs, xs[1:])]
    step = sum(steps) / len(steps)
    assert max(steps) - min(steps) < 1e-6, "ungleichmäßiges Raster"
    assert PERIOD / step == pytest.approx(round(PERIOD / step), abs=1e-6)
    assert step == pytest.approx(PERIOD / 14, abs=1e-9)      # 1,1 rastet auf 15/14


def test_brick_width_snaps_to_a_divisor_of_the_period():
    polys = cells("brick", {"brickWidth": 2.2, "jointWidth": 0.1,
                            "bond": "stack"}, context())
    widths = {round(max(p[0] for p in poly) - min(p[0] for p in poly), 6)
              for poly in polys}
    assert len(widths) == 1
    brick = widths.pop() + 0.1                    # Fuge zurückrechnen
    assert PERIOD / brick == pytest.approx(round(PERIOD / brick), abs=1e-6)


def test_puzzle_pieces_divide_the_period_exactly():
    polys = cells("puzzle", {"countX": 6, "countY": 4}, context())
    assert len(polys) == 24
    # Die x-Außenkanten sind gerade: kein Punkt ragt über das Fenster hinaus
    for poly in polys:
        for x, _y in poly:
            assert -1e-9 <= x <= PERIOD + 1e-9


def test_without_a_period_nothing_changes():
    """Der periodische Modus darf das gewohnte Verhalten nicht anfassen."""
    plain = GenContext(bbox=(0.0, -3.0, 15.0, 3.0), rnd=random.Random(42),
                       thickness=0.1)
    assert not plain.periodic
    for pattern_id, params in LATTICE:
        a = cells(pattern_id, params, plain)
        b = cells(pattern_id, params,
                  GenContext(bbox=(0.0, -3.0, 15.0, 3.0),
                             rnd=random.Random(42), thickness=0.1))
        assert a == b
