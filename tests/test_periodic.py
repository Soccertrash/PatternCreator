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


# ------------------------------------------------------- organische Muster

ORGANIC = [
    ("voronoi", {"cellCount": 150, "relax": 1, "inset": 0.05}),
    ("voronoi", {"cellCount": 200, "relax": 0, "inset": 0.0}),
    ("voronoi", {"cellCount": 30, "relax": 2, "inset": 0.1}),
    ("pebbles", {"cellCount": 90, "relax": 1, "roundness": 2, "inset": 0.08}),
    ("pebbles", {"cellCount": 90, "roundness": 3, "inset": 0.08, "sizeSpread": 40.0}),
    ("tissue", {"cellCount": 120, "rows": 8, "anisotropy": 2.5, "roundness": 2}),
    ("tissue", {"cellCount": 320, "rows": 14, "anisotropy": 2.5, "roundness": 2}),
    ("leaf_veins", {"coarseCells": 12, "fineCells": 6}),
    ("leaf_veins", {"coarseCells": 26, "fineCells": 14}),
]
ORGANIC_IDS = ["%s-%s" % (p[0], "-".join(str(v) for v in p[1].values()))
               for p in ORGANIC]
SEEDS = (1, 42, 7, 99, 123)


def organic_run(pattern_id, params, seed):
    """Löcher, Nahtnetz und Fugenbreite eines organischen Musters.

    Das Nahtnetz kommt aus einem **frischen** Kontext mit demselben Seed - genau
    so, wie ``core/build.py`` es später aufruft.
    """
    gen = generators.get_generator(pattern_id)
    merged = gen.defaults()
    merged.update(params)
    holes = [el.points for el in gen.generate(merged, context(seed=seed))
             if isinstance(el, ir.Path) and el.role == ir.ROLE_REGION]
    net = gen.seam_cells(merged, context(seed=seed))
    return holes, (holes if net is None else net), gen.gap(merged) / 2.0


@pytest.mark.parametrize("pattern_id,params", ORGANIC, ids=ORGANIC_IDS)
def test_organic_seam_path_leaves_every_hole_whole(pattern_id, params):
    """Der Kern der Sache: eine Bahn, die auch **verschoben** nichts zerschneidet.

    Die zweite Prüfung ist die eigentliche: die Außenkontur benutzt die Bahn
    zweimal, links und um eine Periode versetzt. Nur wenn beide Kanten auf
    Zellwänden liegen, ist die Naht nach dem Wickeln keine.
    """
    from core import seam

    for seed in SEEDS:
        holes, net, grow = organic_run(pattern_id, params, seed)
        path = seam.seam_path(net, 0.0, -HEIGHT / 2.0, HEIGHT / 2.0,
                              seam.suggest_offset(net, PERIOD),
                              grow=grow, period=PERIOD)
        assert path is not None, "%s, Seed %d: keine Bahn gefunden" % (pattern_id, seed)
        assert path[0][1] == pytest.approx(-HEIGHT / 2.0)
        assert path[-1][1] == pytest.approx(HEIGHT / 2.0)
        assert not seam.crossed_cells(holes, path)
        shifted = [(x + PERIOD, y) for x, y in path]
        assert not seam.crossed_cells(holes, shifted), (
            "%s, Seed %d: die versetzte Bahn zerschneidet Löcher - nach dem "
            "Wickeln wäre die Naht sichtbar" % (pattern_id, seed))


@pytest.mark.parametrize("pattern_id,params", ORGANIC, ids=ORGANIC_IDS)
def test_organic_is_deterministic(pattern_id, params):
    a, _net, _g = organic_run(pattern_id, params, 42)
    b, _net, _g = organic_run(pattern_id, params, 42)
    assert [len(c) for c in a] == [len(c) for c in b]
    for pa, pb in zip(a, b):
        assert pa == pb


@pytest.mark.parametrize("pattern_id,params", ORGANIC[:7], ids=ORGANIC_IDS[:7])
def test_ghosts_do_not_change_the_cell_count(pattern_id, params):
    """Geisterpunkte begrenzen die Zellen, sie bekommen keine eigene."""
    holes, _net, _g = organic_run(pattern_id, params, 42)
    want = params["cellCount"]
    if params.get("rows"):
        # Im Reihenmodus wird die Zellenzahl auf volle Reihen gerundet - das war
        # schon immer so und hat mit der Naht nichts zu tun.
        rows = params["rows"]
        want = rows * max(1, int(round(want / float(rows))))
    assert len(holes) == want


def test_cells_are_not_truncated_at_the_seam():
    """Zellen an der Naht sind ganze Zellen, keine Hälften.

    Das ist der Unterschied zwischen „am Fensterrand abgeschnitten" und „echt
    periodisch": abgeschnitten wäre auch lückenlos, aber die Zellen an der Naht
    wären halb so groß und nach dem Wickeln als Bruch zu sehen.
    """
    from core.geom import polygon_area

    for seed in SEEDS:
        holes, _net, _g = organic_run("voronoi", {"cellCount": 150, "relax": 2}, seed)
        assert min(min(p[0] for p in c) for c in holes) < 0.0, "keine Zelle ragt über die Naht"
        assert max(max(p[0] for p in c) for c in holes) > PERIOD
        areas = sorted(abs(polygon_area(c)) for c in holes)
        median = areas[len(areas) // 2]
        at_seam = [abs(polygon_area(c)) for c in holes
                   if min(p[0] for p in c) < 0.0 < max(p[0] for p in c)]
        assert at_seam, "keine Zelle liegt auf der Naht"
        assert min(at_seam) > 0.5 * median


def test_scattered_sites_keep_their_distance_across_the_seam():
    """Der Mindestabstand gilt auch über die Naht hinweg.

    Ohne das rutschen ein Punkt am linken und einer am rechten Rand nach dem
    Wickeln aufeinander; gemessen sank der kleinste Abstand dabei auf ein
    Viertel (0,089 statt 0,326 cm) - und genau dort entsteht ein Zellsplitter.

    Genau gleich sind die beiden Werte nicht: fügt sich ein Punkt partout
    nirgends ein, sinkt der geforderte Mindestabstand (sonst käme das Muster in
    engen Rahmen nie auf seine Zellenzahl), und der kleinste Abstand überhaupt
    kann dann ebenso gut über die Naht laufen wie mitten im Feld.
    """
    from generators.organic_cells import scatter_sites

    box = (0.0, -HEIGHT / 2.0, PERIOD, HEIGHT / 2.0)
    for seed in range(6):
        pts = scatter_sites(box, 200, random.Random(seed), period=PERIOD)
        plain = min(_distance(pts[i], pts[j], 0.0)
                    for i in range(len(pts)) for j in range(i + 1, len(pts)))
        wrapped = min(_distance(pts[i], pts[j], PERIOD)
                      for i in range(len(pts)) for j in range(i + 1, len(pts)))
        assert wrapped >= 0.9 * plain


def _distance(a, b, period):
    dx = abs(a[0] - b[0])
    if period > 0.0:
        dx = min(dx, period - dx)
    return math.hypot(dx, a[1] - b[1])


def test_band_ghosts_match_full_ghosts():
    """Die Abkürzung rechnet dasselbe wie die volle Rechnung.

    Geisterpunkte entstehen nur in einem Band an den Fensterkanten
    (``SEAM_BAND_RADII`` Zellradien breit) - Punkte weiter innen können die
    Zellen an der Naht nicht mehr berühren. Hier wird das gegen die teure
    Variante gehalten, die **jeden** Punkt spiegelt.
    """
    from generators import organic_cells as oc

    box = (0.0, -HEIGHT / 2.0, PERIOD, HEIGHT / 2.0)
    for seed in range(4):
        sites = oc.sample_sites(box, 120, random.Random(seed), period=PERIOD)
        band = oc.seam_band(box, 120, PERIOD)
        assert band < PERIOD / 2.0, "Band zu breit - der Test prüft nichts"
        cheap = oc.voronoi_cells(sites, (box[0] - band, box[1], box[2] + band, box[3]),
                                 oc.ghost_sites(sites, box[0], PERIOD, band))
        full = oc.voronoi_cells(sites, (box[0] - band, box[1], box[2] + band, box[3]),
                                oc.ghost_sites(sites, box[0], PERIOD, PERIOD))
        assert len(cheap) == len(full)
        for a, b in zip(cheap, full):
            assert a == pytest.approx(b, abs=1e-9)


def test_without_a_period_organic_cells_stay_inside_the_window():
    """Ohne Periode bleibt alles wie bisher - die Zellen enden am Rahmen."""
    gen = generators.get_generator("voronoi")
    merged = gen.defaults()
    plain = GenContext(bbox=(0.0, -HEIGHT / 2.0, PERIOD, HEIGHT / 2.0),
                       rnd=random.Random(42), thickness=0.1,
                       fill_target="webs", mode="area")
    holes = [el.points for el in gen.generate(merged, plain)
             if isinstance(el, ir.Path) and el.role == ir.ROLE_REGION]
    assert min(min(p[0] for p in c) for c in holes) >= -1e-9
    assert max(max(p[0] for p in c) for c in holes) <= PERIOD + 1e-9


# --------------------------------------------------------- Prägen-Hinweise

def test_embossing_without_the_face_model_warns_in_the_preview():
    """Der Hinweis muss kommen, bevor die Skizze entsteht - nicht danach."""
    from core import build, pattern_doc
    doc = pattern_doc.default_doc()
    doc["style"].update({"embossOn": True, "mode": "lines"})
    doc["development"] = {"kind": "cylinder", "radius": 2.5, "halfAngle": 0.0,
                          "length": 6.0, "periodic": True, "seamAngle": 0.0,
                          "outline": [], "axisMiddle": 0.0,
                          "source": {"label": "Z", "token": ""}}
    doc, errors = pattern_doc.parse(doc)
    assert not errors
    scene = build.build_scene(doc)
    assert build.EMBOSS_MODEL_WARNING in scene.warnings


def test_the_face_model_says_nothing():
    from core import build, pattern_doc
    doc = pattern_doc.default_doc()
    doc["style"]["embossOn"] = True
    doc["development"] = {"kind": "cylinder", "radius": 2.5, "halfAngle": 0.0,
                          "length": 6.0, "periodic": True, "seamAngle": 0.0,
                          "outline": [], "axisMiddle": 0.0,
                          "source": {"label": "Z", "token": ""}}
    doc, _ = pattern_doc.parse(doc)
    scene = build.build_scene(doc)
    assert build.EMBOSS_MODEL_WARNING not in scene.warnings
    assert build.emboss_seconds(scene) > 0.0


def test_a_plane_pattern_is_never_told_about_embossing():
    """Ohne Mantelfläche gibt es die Prägung gar nicht."""
    from core import build, pattern_doc
    doc, _ = pattern_doc.parse(pattern_doc.default_doc())
    scene = build.build_scene(doc)
    assert build.EMBOSS_MODEL_WARNING not in scene.warnings
    assert build.emboss_seconds(scene) >= 0.0
