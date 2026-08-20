"""Flächenmodell: kachelnde Muster ergeben EINE Fläche mit Löchern.

Damit ist das Stegnetz in Fusion mit einem Klick auswählbar, überlappt sich
nicht mehr an den Knoten und ist als geschlossener Körper 3D-druckbar.
"""

import math

import pytest

import generators
from core import ir
from core import pattern_doc as pd
from core.build import build_scene
from core.containers import make_container
from core.geom import point_in_polygon, polygon_area

TILING_IDS = [pid for pid, cls in generators.REGISTRY.items() if cls.tiling]
STROKE_IDS = [pid for pid, cls in generators.REGISTRY.items() if not cls.tiling]


def face_doc(pattern_id, **style):
    doc = pd.default_doc(pattern_id)
    doc["style"].update({"mode": "area", "fillTarget": "webs", "border": True,
                         "thickness": 0.1, "borderWidth": 0.2, "clip": "cut"})
    doc["style"].update(style)
    return doc


def roles(scene):
    return [getattr(el, "role", "") for el in scene.elements]


# ------------------------------------------------------------------ Struktur

def test_nine_patterns_are_tiling():
    assert set(TILING_IDS) == {"grid", "rhombus", "honeycomb", "brick", "puzzle",
                               "voronoi", "pebbles", "tissue", "leaf_veins"}


@pytest.mark.parametrize("pattern_id", TILING_IDS)
def test_tiling_pattern_is_one_face_with_holes(pattern_id):
    scene = build_scene(face_doc(pattern_id))
    r = roles(scene)
    assert r.count(ir.ROLE_FACE) == 1, "genau eine Außenkontur erwartet"
    assert r.count(ir.ROLE_HOLE) >= 1, "keine Löcher erzeugt"


@pytest.mark.parametrize("pattern_id", TILING_IDS)
def test_holes_are_smaller_than_the_face(pattern_id):
    """Löcher dürfen sich nicht überlappen - Summe < Fläche des Rahmens."""
    doc = face_doc(pattern_id)
    container = make_container(doc["container"])
    outer = abs(polygon_area(container.clip_polygon()))
    holes = [abs(polygon_area(el.points)) for el in build_scene(doc).elements
             if getattr(el, "role", "") == ir.ROLE_HOLE and isinstance(el, ir.Path)]
    assert holes
    assert sum(holes) < outer


@pytest.mark.parametrize("pattern_id", TILING_IDS)
def test_holes_stay_inside_the_container(pattern_id):
    doc = face_doc(pattern_id)
    poly = make_container(doc["container"]).clip_polygon()
    for el in build_scene(doc).elements:
        if getattr(el, "role", "") == ir.ROLE_HOLE and isinstance(el, ir.Path):
            for p in el.points:
                assert point_in_polygon(p, poly), "%s: Loch ragt aus dem Rahmen" % pattern_id


@pytest.mark.parametrize("pattern_id", STROKE_IDS)
def test_stroke_patterns_keep_the_old_model(pattern_id):
    """Strich-Muster (ohne Zellen) bleiben vorerst einzelne Streifen."""
    scene = build_scene(face_doc(pattern_id))
    assert ir.ROLE_HOLE not in roles(scene)


# --------------------------------------------------------------- Rahmendicke

@pytest.mark.parametrize("width", [0.2, 0.5, 1.0])
def test_border_width_is_measured_inwards(width):
    """Außenmaß bleibt; der Rand wächst nach innen."""
    doc = face_doc("honeycomb", borderWidth=width)
    doc["container"] = dict(doc["container"], shape="circle", diameter=9.0)
    scene = build_scene(doc)
    radius = 4.5
    outer = max(math.hypot(*p) for el in scene.elements
                if getattr(el, "role", "") == ir.ROLE_HOLE and isinstance(el, ir.Path)
                for p in el.points)
    # Toleranz: der Kreis wird für das Clipping polygonal angenähert
    assert radius - outer == pytest.approx(width, abs=0.02)


def test_border_width_changes_geometry():
    thin = build_scene(face_doc("honeycomb", borderWidth=0.1)).to_dict()
    thick = build_scene(face_doc("honeycomb", borderWidth=1.0)).to_dict()
    assert thin != thick


def test_border_off_falls_back_to_strokes():
    """Ohne Rahmen fehlt die Außenkontur - dann bleibt es beim Stroken."""
    scene = build_scene(face_doc("honeycomb", border=False))
    assert ir.ROLE_FACE not in roles(scene)
    assert ir.ROLE_HOLE not in roles(scene)


def test_clip_off_falls_back_to_strokes():
    scene = build_scene(face_doc("honeycomb", clip="off"))
    assert ir.ROLE_HOLE not in roles(scene)


# --------------------------------------------------------------- Stegbreite

def test_web_width_matches_thickness():
    """Zwei benachbarte Waben-Löcher liegen genau ``thickness`` auseinander."""
    doc = face_doc("honeycomb", thickness=0.2, borderWidth=0.2)
    doc["pattern"]["params"]["cellSize"] = 1.0
    holes = [el.points for el in build_scene(doc).elements
             if getattr(el, "role", "") == ir.ROLE_HOLE and isinstance(el, ir.Path)]
    # Nur vollständige Sechsecke - Randzellen sind beschnitten
    inner = [h for h in holes if len(h) == 6]
    assert len(inner) > 10
    pairs = [(a, b) for i, a in enumerate(inner[:12]) for b in inner[i + 1:12]]
    gaps = sorted(min(math.dist(p, q) for p in a for q in b) for a, b in pairs)
    assert gaps[0] == pytest.approx(0.2, abs=0.01)


# ------------------------------------------------------------------ Text

def test_knockout_removes_holes_instead_of_cutting_them():
    doc = face_doc("honeycomb")
    doc["textLayers"][0].update({"enabled": True, "knockout": True, "text": "AB",
                                 "height": 1.5, "x": -1.0, "y": -0.5})
    with_text = build_scene(doc)
    doc2 = face_doc("honeycomb")
    without = build_scene(doc2)
    n_with = roles(with_text).count(ir.ROLE_HOLE)
    n_without = roles(without).count(ir.ROLE_HOLE)
    assert n_with < n_without, "Textbereich muss massiv werden"
    assert roles(with_text).count(ir.ROLE_FACE) == 1, "Rahmen darf nicht wegfallen"


# ------------------------------------------------------- Eigene Fuge des Musters

def test_brick_joint_wins_over_thickness():
    """Mauerfuge ist breiter als die Dicke -> Ziegelmaße bleiben exakt."""
    doc = face_doc("brick", thickness=0.06)
    doc["pattern"]["params"].update({"brickWidth": 2.0, "brickHeight": 0.8,
                                     "jointWidth": 0.12, "bond": "stack"})
    holes = [el.points for el in build_scene(doc).elements
             if getattr(el, "role", "") == ir.ROLE_HOLE and isinstance(el, ir.Path)]
    full = [h for h in holes if len(h) == 4]
    sizes = {(round(max(p[0] for p in h) - min(p[0] for p in h), 4),
              round(max(p[1] for p in h) - min(p[1] for p in h), 4)) for h in full}
    assert (2.0 - 0.12, 0.8 - 0.12) in {(round(a, 4), round(b, 4)) for a, b in sizes}


def test_thickness_beats_a_smaller_joint():
    """Ist die Dicke größer als die Fuge, bestimmt sie die Stegbreite."""
    doc = face_doc("brick", thickness=0.3)
    doc["pattern"]["params"].update({"brickWidth": 2.0, "brickHeight": 0.8,
                                     "jointWidth": 0.1, "bond": "stack"})
    holes = [el.points for el in build_scene(doc).elements
             if getattr(el, "role", "") == ir.ROLE_HOLE and isinstance(el, ir.Path)]
    full = [h for h in holes if len(h) == 4]
    widths = {round(max(p[0] for p in h) - min(p[0] for p in h), 3) for h in full}
    assert 1.7 in widths      # 2.0 - 0.3 (Dicke), nicht 2.0 - 0.1 (Fuge)


def test_voronoi_without_joint_still_has_webs():
    """Fugenbreite 0 darf nicht zu Löchern auf Stoß führen."""
    doc = face_doc("voronoi", thickness=0.2)
    doc["pattern"]["params"]["inset"] = 0.0
    holes = [el.points for el in build_scene(doc).elements
             if getattr(el, "role", "") == ir.ROLE_HOLE and isinstance(el, ir.Path)]
    assert len(holes) > 20
    gaps = []
    for i, a in enumerate(holes[:10]):
        for b in holes[i + 1:10]:
            gaps.append(min(math.dist(p, q) for p in a for q in b))
    assert min(gaps) > 0.1
