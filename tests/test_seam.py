"""Nahtbahn entlang der Zellwände (``core/seam.py``).

Die entscheidende Zusicherung: die Bahn zerschneidet **keine** Zelle. Damit wird
die Naht auch bei versetzten Mustern (Wabe, Rauten, Mauer im Verband)
unsichtbar - das war mit einem geraden Schnitt geometrisch nicht möglich
(``Context.md`` 15.7).
"""

import random

import pytest

import generators
from core import ir, seam
from core.polyclip import point_on_boundary
from generators.base import GenContext

PERIOD = 15.0
HEIGHT = 6.0

PATTERNS = [
    ("grid", {}),
    ("grid", {"skew": 65.0}),
    ("rhombus", {}),
    ("honeycomb", {"orientation": "flat"}),
    ("honeycomb", {"orientation": "pointy"}),
    ("brick", {"bond": "half"}),
    ("brick", {"bond": "stack"}),
    ("puzzle", {"countX": 6, "countY": 4}),
]
IDS = ["%s-%s" % (p[0], "-".join(str(v) for v in p[1].values()) or "std")
       for p in PATTERNS]


def context(x0=0.0):
    return GenContext(bbox=(x0, -HEIGHT / 2.0, x0 + PERIOD, HEIGHT / 2.0),
                      rnd=random.Random(42), thickness=0.1, period_x=PERIOD)


def cells_of(pattern_id, params, ctx):
    gen = generators.get_generator(pattern_id)
    merged = gen.defaults()
    merged.update(params)
    return [el.points for el in gen.generate(merged, ctx)
            if isinstance(el, ir.Path) and el.role == ir.ROLE_REGION]


def path_for(pattern_id, params, ctx=None, offset=None):
    ctx = ctx or context()
    gen = generators.get_generator(pattern_id)
    merged = gen.defaults()
    merged.update(params)
    cells = cells_of(pattern_id, params, ctx)
    x0, y0, _x1, y1 = ctx.bbox
    return cells, seam.seam_path(cells, x0, y0, y1,
                                 offset if offset is not None else PERIOD / 4.0,
                                 grow=gen.gap(merged) / 2.0)


@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_a_path_is_found_and_spans_the_full_height(pattern_id, params):
    cells, path = path_for(pattern_id, params)
    assert path, "keine Nahtbahn gefunden"
    assert len(path) >= 2
    assert path[0][1] <= -HEIGHT / 2.0 + 1e-9
    assert path[-1][1] >= HEIGHT / 2.0 - 1e-9


@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_the_path_never_cuts_a_cell(pattern_id, params):
    """Das ist der Zweck der Übung."""
    cells, path = path_for(pattern_id, params)
    assert seam.crossed_cells(cells, path) == []


@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_every_step_runs_along_a_cell_edge(pattern_id, params):
    """Nicht nur „schneidet nichts", sondern wirklich auf den Wänden.

    Bei Mustern mit eigener Fuge (Mauer) ist die Wand die **Fugenmitte** - dort
    verglichen wird deshalb mit den um die halbe Fuge aufgeweiteten Zellen.
    """
    gen = generators.get_generator(pattern_id)
    merged = gen.defaults()
    merged.update(params)
    grow = gen.gap(merged) / 2.0
    cells, path = path_for(pattern_id, params)
    walls = [seam._grown(c, grow) if grow > 1e-12 else c for c in cells]
    for a, b in zip(path, path[1:]):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        assert any(point_on_boundary(mid, cell, 1e-6) for cell in walls), (
            "Schritt %s -> %s liegt auf keiner Zellkante" % (a, b))


@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_the_path_only_goes_upwards(pattern_id, params):
    cells, path = path_for(pattern_id, params)
    for a, b in zip(path, path[1:]):
        assert b[1] >= a[1] - 1e-9


@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_the_path_stays_close_to_the_seam(pattern_id, params):
    cells, path = path_for(pattern_id, params)
    xs = [p[0] for p in path]
    assert max(xs) - min(xs) <= PERIOD / 4.0 + 1e-9
    assert min(xs) >= -PERIOD / 4.0 - 1e-9


def test_straight_walls_give_a_straight_path():
    """Wo eine gerade Naht schon eine Zellgrenze ist, bleibt es dabei."""
    _cells, path = path_for("grid", {})
    assert all(abs(p[0]) < 1e-9 for p in path), path[:5]


def test_staggered_patterns_need_a_zigzag():
    """Und wo nicht, weicht die Bahn aus - sonst wäre die Übung sinnlos."""
    for pattern_id, params in (("honeycomb", {"orientation": "pointy"}),
                               ("honeycomb", {"orientation": "flat"}),
                               ("rhombus", {})):
        _cells, path = path_for(pattern_id, params)
        assert max(abs(p[0]) for p in path) > 1e-6, pattern_id


def test_the_same_input_gives_the_same_path():
    a = path_for("honeycomb", {"orientation": "pointy"})[1]
    b = path_for("honeycomb", {"orientation": "pointy"})[1]
    assert a == b


def test_no_band_no_path():
    cells, _path = path_for("grid", {})
    assert seam.seam_path(cells, 0.0, -3.0, 3.0, 0.0) is None
    assert seam.seam_path([], 0.0, -3.0, 3.0, 1.0) is None


# ---------------------------------------------- Kopien von der anderen Seite

def test_periodic_cells_copies_only_the_far_seam():
    """Nur die Zellen am rechten Nahtrand werden nach links kopiert."""
    left = [(-0.2, 0.0), (0.3, 0.0), (0.3, 1.0), (-0.2, 1.0)]
    middle = [(7.0, 0.0), (8.0, 0.0), (8.0, 1.0), (7.0, 1.0)]
    right = [(PERIOD - 0.3, 0.0), (PERIOD + 0.2, 0.0),
             (PERIOD + 0.2, 1.0), (PERIOD - 0.3, 1.0)]
    out = seam.periodic_cells([left, middle, right], 0.0, PERIOD, 1.0)
    assert len(out) == 4
    copy = out[-1]
    assert min(p[0] for p in copy) == pytest.approx(-0.3)
    assert seam.periodic_cells([left, middle, right], 0.0, 0.0, 1.0) == \
        [left, middle, right]


def test_the_shifted_path_cuts_nothing_either():
    """Die eigentliche Zusicherung: die Bahn taugt auf **beiden** Nahtseiten.

    Ohne die Kopien von der anderen Seite sieht die Suche links der Naht ein
    Loch, wo in Wirklichkeit das Muster weitergeht - und legt die Bahn
    mittendurch. Auffallen würde das erst am gewickelten Teil.
    """
    for pattern_id, params in PATTERNS:
        gen = generators.get_generator(pattern_id)
        merged = gen.defaults()
        merged.update(params)
        ctx = context()
        cells = cells_of(pattern_id, params, ctx)
        path = seam.seam_path(cells, 0.0, -HEIGHT / 2.0, HEIGHT / 2.0,
                              PERIOD / 4.0, grow=gen.gap(merged) / 2.0,
                              period=PERIOD)
        assert path is not None, pattern_id
        shifted = [(x + PERIOD, y) for x, y in path]
        assert not seam.crossed_cells(cells, shifted), pattern_id


# ------------------------------------------------------- Band und Verlängerung

def test_suggest_offset_scales_with_the_cell_size():
    small = [[(x, 0.0), (x + 0.5, 0.0), (x + 0.5, 1.0), (x, 1.0)]
             for x in (0.0, 0.5, 1.0)]
    large = [[(x, 0.0), (x + 2.0, 0.0), (x + 2.0, 1.0), (x, 1.0)]
             for x in (0.0, 2.0, 4.0)]
    assert seam.suggest_offset(small, PERIOD) == pytest.approx(1.5)
    assert seam.suggest_offset(large, 100.0) == pytest.approx(6.0)
    # Ein Viertel Umlauf ist die Grenze - sonst wandert die Bahn durchs Muster.
    assert seam.suggest_offset(large, PERIOD) == pytest.approx(PERIOD / 4.0)
    assert seam.suggest_offset([], PERIOD) == 0.0


def test_the_path_reaches_the_border_even_with_a_gap():
    """Muster mit eigener Fuge lassen oben und unten einen Streifen frei.

    Die Bahn wird dort senkrecht verlängert - aber nur, wenn dieses Stück keine
    Zelle anschneidet.
    """
    cells = [[(x, y), (x + 0.9, y), (x + 0.9, y + 0.9), (x, y + 0.9)]
             for x in (-1.0, 0.0, 1.0) for y in (-2.0, -1.0, 0.0, 1.0)]
    path = seam.seam_path(cells, 0.0, -3.0, 3.0, 2.0, grow=0.05)
    assert path is not None
    assert path[0][1] == pytest.approx(-3.0)
    assert path[-1][1] == pytest.approx(3.0)
    assert not seam.crossed_cells(cells, path)


def test_no_path_through_a_cell_wall():
    """Eine Verlängerung, die mitten durch eine Zelle liefe, gibt es nicht."""
    # Eine breite Zelle deckt den ganzen Bereich unter dem Kantennetz ab.
    blocker = [(-2.0, -3.0), (2.0, -3.0), (2.0, -1.0), (-2.0, -1.0)]
    cells = [blocker,
             [(-0.5, 0.0), (0.5, 0.0), (0.5, 1.0), (-0.5, 1.0)],
             [(-0.5, 1.0), (0.5, 1.0), (0.5, 2.0), (-0.5, 2.0)]]
    assert seam.seam_path(cells, 0.0, -3.0, 3.0, 1.0) is None


# ----------------------------------------------------------------- Probe

def test_the_probe_ignores_rounding_noise():
    """Ein Schnitt von einem Nanometer Tiefe ist kein Schnitt.

    Die Bahnpunkte sind auf 1e-9 cm gefangen und liegen dadurch minimal neben
    der Wand, auf der sie laufen. Wird das als Schnitt gewertet, meldet die
    Probe bei gerundeten Zellen ein Dutzend Treffer, die es nicht gibt.
    """
    cell = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    on_the_wall = [(0.0, 0.0), (1e-10, 0.5), (0.0, 1.0)]
    assert not seam.crossed_cells([cell], on_the_wall)
    really_through = [(-0.1, 0.5), (0.5, 0.5)]
    assert seam.crossed_cells([cell], really_through)
