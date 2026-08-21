"""Eigener Rahmen: ``CustomContainer`` im vollen Muster-Durchlauf.

Der Rahmen ist ein reines Container-Thema - ``core/build.py`` weiss nichts von
ihm. Diese Tests sichern beides ab: dass ein rechteckiger *eigener* Rahmen
genau dasselbe liefert wie ``RectContainer`` (Regressionsanker), und dass ein
konkaver Rahmen das Flaechenmodell nicht zerreisst.
"""

import math
import random
import time

import pytest

import generators
from core import ir
from core import pattern_doc as pd
from core.build import SHRINK_WARNING, MIN_HOLE_WIDTH_FACTOR, _is_sliver, build_scene
from core.containers import (CustomContainer, RectContainer, make_container,
                             normalize_frame)
from core.geom import circle_points, polygon_area
from core.optimize import _self_intersects
from core.polyclip import point_segment_distance

PATTERNS = list(generators.REGISTRY)
TILING = [pid for pid, cls in generators.REGISTRY.items() if cls.tiling]

RECT_POINTS = [(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]
L_SHAPE = [(-5.0, -3.0), (5.0, -3.0), (5.0, 0.0), (0.0, 0.0), (0.0, 3.0), (-5.0, 3.0)]
U_SHAPE = [(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (3.0, 3.0), (3.0, -1.0),
           (-3.0, -1.0), (-3.0, 3.0), (-5.0, 3.0)]


def star_points(n=400, r_out=5.0, r_in=3.5):
    return [((r_out if i % 2 == 0 else r_in) * math.cos(2 * math.pi * i / n),
             (r_out if i % 2 == 0 else r_in) * math.sin(2 * math.pi * i / n))
            for i in range(n)]


STAR = star_points(24, 5.0, 2.5)


def face_doc(pattern_id, points=None, **style):
    doc = pd.default_doc(pattern_id)
    doc["style"].update({"mode": "area", "fillTarget": "webs", "border": True,
                         "thickness": 0.1, "borderWidth": 0.2, "clip": "cut"})
    doc["style"].update(style)
    if points is not None:
        doc["container"] = dict(doc["container"], shape="custom",
                                customPoints=[list(p) for p in points])
    return doc


def holes(scene):
    return [el.points for el in scene.elements
            if isinstance(el, ir.Path) and el.role == ir.ROLE_HOLE]


def hole_area(scene):
    return sum(abs(polygon_area(h)) for h in holes(scene))


def sample_outline(points, count=200):
    """Gleichmaessig verteilte Punkte auf einer geschlossenen Kontur."""
    n = len(points)
    edges = [(points[i], points[(i + 1) % n]) for i in range(n)]
    total = sum(math.dist(a, b) for a, b in edges)
    out = []
    for k in range(count):
        s = total * k / count
        for a, b in edges:
            d = math.dist(a, b)
            if s <= d or d <= 0:
                t = 0.0 if d <= 0 else s / d
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                break
            s -= d
    return out


def distance_to_nearest_hole(p, hole_list):
    best = float("inf")
    for h in hole_list:
        xs = [q[0] for q in h]
        ys = [q[1] for q in h]
        if (min(xs) - p[0] > best or p[0] - max(xs) > best
                or min(ys) - p[1] > best or p[1] - max(ys) > best):
            continue                      # Bounding-Box zu weit weg
        m = len(h)
        for i in range(m):
            d = point_segment_distance(p, h[i], h[(i + 1) % m])
            if d < best:
                best = d
    return best


# ------------------------------------------------------------ Regressionsanker

@pytest.mark.parametrize("pattern_id", PATTERNS)
def test_rectangular_custom_frame_equals_the_rect_container(pattern_id):
    """Ein eigener Rahmen in Rechteckform muss dasselbe Muster ergeben."""
    ref = build_scene(face_doc(pattern_id))
    mine = build_scene(face_doc(pattern_id, RECT_POINTS))
    assert len(mine.elements) == len(ref.elements)
    assert hole_area(mine) == pytest.approx(hole_area(ref), abs=1e-6)


def test_ninety_six_gon_matches_the_circle_container():
    """Der Kreis wird fuers Clipping als 96-Eck genaehert - also fast dasselbe."""
    doc = face_doc("honeycomb")
    doc["container"] = dict(doc["container"], shape="circle", diameter=8.0)
    ref = hole_area(build_scene(doc))
    poly = circle_points((0.0, 0.0), 4.0 / math.cos(math.pi / 96), 96)
    mine = hole_area(build_scene(face_doc("honeycomb", poly)))
    assert abs(mine - ref) / ref < 0.005


# --------------------------------------------------------------- Konkave Rahmen

@pytest.mark.parametrize("frame", [L_SHAPE, U_SHAPE, STAR],
                         ids=["L", "U", "Stern"])
@pytest.mark.parametrize("pattern_id", TILING)
def test_holes_stay_inside_a_concave_frame(frame, pattern_id):
    scene = build_scene(face_doc(pattern_id, frame))
    container = CustomContainer(frame)
    hole_list = holes(scene)
    assert hole_list, "kein einziges Loch im konkaven Rahmen"
    for h in hole_list:
        assert not _self_intersects(h, True), "Loch schneidet sich selbst"
        for p in h:
            assert container.grid.inside_or_on(p, 1e-6), "Loch ragt aus dem Rahmen"


@pytest.mark.parametrize("frame", [L_SHAPE, U_SHAPE], ids=["L", "U"])
def test_border_width_is_kept_along_a_concave_outline(frame):
    """200 Stichproben auf der Aussenkontur: nirgends ist der Rand zu duenn."""
    doc = face_doc("honeycomb", frame, borderWidth=0.3)
    scene = build_scene(doc)
    hole_list = holes(scene)
    for p in sample_outline(normalize_frame(frame), 200):
        assert distance_to_nearest_hole(p, hole_list) >= 0.3 - 1e-6


@pytest.mark.parametrize("frame", [L_SHAPE, U_SHAPE, STAR],
                         ids=["L", "U", "Stern"])
def test_sliver_filter_works_in_a_concave_frame(frame):
    """Angeschnittene Randzellen duerfen keine Splitter hinterlassen."""
    scene = build_scene(face_doc("voronoi", frame))
    for h in holes(scene):
        assert not _is_sliver(h, 0.1 * MIN_HOLE_WIDTH_FACTOR)


def test_puzzle_with_concave_cells_in_a_concave_frame():
    scene = build_scene(face_doc("puzzle", U_SHAPE))
    hole_list = holes(scene)
    assert hole_list
    container = CustomContainer(U_SHAPE)
    for h in hole_list:
        assert not _self_intersects(h, True)
        for p in h:
            assert container.grid.inside_or_on(p, 1e-6)


def test_drop_partial_keeps_only_complete_cells():
    doc = face_doc("grid", U_SHAPE, clip="dropPartial")
    scene = build_scene(doc)
    container = CustomContainer(U_SHAPE)
    inner = container.shrunk(max(0.0, 0.2 - 0.05))
    for h in holes(scene):
        assert inner.fully_inside(h) or container.fully_inside(h)
    # ... und es bleibt etwas uebrig
    assert holes(scene)


def test_line_mode_stays_inside_a_concave_frame():
    doc = face_doc("grid", U_SHAPE, mode="lines")
    scene = build_scene(doc)
    container = CustomContainer(U_SHAPE)
    for el in scene.elements:
        if isinstance(el, ir.Path) and el.layer == ir.LAYER_PATTERN:
            for p in el.points:
                assert container.grid.inside_or_on(p, 1e-6)


def test_text_knockout_and_hatch_run_in_a_concave_frame():
    doc = face_doc("honeycomb", U_SHAPE, hatch=True, hatchSpacing=0.3,
                   hatchThickness=0.05)
    doc["textLayers"][0].update({"enabled": True, "knockout": True, "text": "AB",
                                 "height": 1.0, "x": -1.0, "y": -2.5})
    scene = build_scene(doc)
    assert holes(scene)
    strips = [el for el in scene.elements
              if isinstance(el, ir.Path) and el.role == ir.ROLE_REGION]
    assert strips, "keine Schraffurstege erzeugt"
    container = CustomContainer(U_SHAPE)
    for el in strips:
        for p in el.points:
            assert container.grid.inside_or_on(p, 1e-6)


# ------------------------------------------------------------------ shrunk

def test_dumbbell_frame_warns_instead_of_failing_silently():
    """Hantelform: der Hals ist schmaler als zweimal die Rahmendicke."""
    dumbbell = [(-4.0, -2.0), (-1.0, -2.0), (-1.0, -0.2), (1.0, -0.2),
                (1.0, -2.0), (4.0, -2.0), (4.0, 2.0), (1.0, 2.0),
                (1.0, 0.2), (-1.0, 0.2), (-1.0, 2.0), (-4.0, 2.0)]
    container = CustomContainer(dumbbell)
    inner = container.shrunk(0.5)
    assert inner.shrink_failed or container.shrink_failed
    scene = build_scene(face_doc("honeycomb", dumbbell, borderWidth=0.5))
    assert SHRINK_WARNING in scene.warnings
    assert holes(scene), "trotz Warnung muss ein Muster entstehen"


def test_a_wide_frame_does_not_warn():
    scene = build_scene(face_doc("honeycomb", L_SHAPE, borderWidth=0.2))
    assert SHRINK_WARNING not in scene.warnings


def test_shrunk_moves_the_outline_inwards():
    container = CustomContainer(L_SHAPE)
    inner = container.shrunk(0.5)
    assert inner is not container
    assert abs(polygon_area(inner.points)) < abs(polygon_area(container.points))


# ---------------------------------------------------------- normalize_frame

def test_normalize_frame_drops_the_closing_point_and_duplicates():
    pts = normalize_frame([(0, 0), (0, 0), (4, 0), (4, 4), (0, 4), (0, 0)])
    assert len(pts) == 4


def test_normalize_frame_orients_counter_clockwise():
    cw = [(0, 0), (0, 4), (4, 4), (4, 0)]
    assert polygon_area(normalize_frame(cw)) > 0


def test_normalize_frame_removes_self_intersections():
    bowtie = [(0, 0), (4, 4), (4, 0), (0, 4)]
    pts = normalize_frame(bowtie)
    assert not _self_intersects(pts, True)


def test_normalize_frame_simplifies_a_tessellated_circle():
    """2000 Punkte auf einem Kreis - nach RDP bleibt ein Bruchteil, die Flaeche
    stimmt auf ein Promille."""
    raw = circle_points((0.0, 0.0), 4.0, 2000)
    pts = normalize_frame(raw)
    assert len(pts) < len(raw) / 4
    assert abs(polygon_area(pts)) == pytest.approx(math.pi * 16.0, rel=0.001)


@pytest.mark.parametrize("bad", [
    [],
    [(0, 0), (1, 1)],
    [(0, 0), (1, 0), (2, 0)],                  # kollinear, keine Flaeche
    [(0, 0), (1, 0), (float("nan"), 1)],
])
def test_normalize_frame_rejects_unusable_input(bad):
    with pytest.raises(ValueError):
        normalize_frame(bad)


def test_make_container_falls_back_to_rect_without_points():
    c = make_container({"shape": "custom", "width": 10.0, "height": 6.0})
    assert isinstance(c, RectContainer)


def test_make_container_builds_a_custom_container():
    c = make_container({"shape": "custom", "customPoints": L_SHAPE})
    assert isinstance(c, CustomContainer)
    assert c.shape == "custom"


# ------------------------------------------------------- Leistung, Determinismus

def test_a_four_hundred_point_star_stays_within_budget():
    """Voronoi mit 500 Zellen im 400-Punkte-Stern gegen dasselbe im Rechteck.

    Der Stern ist der schlimmste denkbare Fall: 200 Zacken, von denen die
    Vereinfachung keinen einzigen Punkt entfernen kann, und mehr als die Haelfte
    aller Zellen liegt im Zackenkranz. Gemessen (siehe ``Context.md`` 15.3):
    Faktor 2,0 - der Plan hatte 1,5 vorgesehen, das erreichen realistische
    Rahmen (Herz aus 400 Punkten: 1,2; L-Form: 1,0). Die Schranke hier faengt
    Groessenordnungs-Rueckschritte ab, nicht Messrauschen.
    """
    doc = face_doc("voronoi")
    doc["pattern"]["params"]["cellCount"] = 500
    star_doc = face_doc("voronoi", star_points())
    star_doc["pattern"]["params"]["cellCount"] = 500

    def best(d):
        return min(_timed(d) for _ in range(3))

    def _timed(d):
        t = time.perf_counter()
        build_scene(d)
        return time.perf_counter() - t

    assert best(star_doc) <= 2.5 * best(doc)


def test_the_same_document_gives_the_same_scene_twice():
    doc = face_doc("voronoi", STAR)
    assert build_scene(doc).to_dict() == build_scene(doc).to_dict()


def test_clipping_is_deterministic_for_random_cells():
    rnd = random.Random(7)
    container = CustomContainer(STAR)
    for _ in range(20):
        cx, cy = rnd.uniform(-4, 4), rnd.uniform(-4, 4)
        cell = [(cx + rnd.uniform(-1, 1), cy + rnd.uniform(-1, 1)) for _ in range(3)]
        assert (container.clip_path(cell, True) == container.clip_path(cell, True))
