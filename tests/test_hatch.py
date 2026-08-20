"""Schraffur: freie Zellflächen mit zusätzlichen Stegen füllen.

Geprüft wird beides: die Geometrie (Scanline in konkaven Zellen, Verankerung im
Steg) und die Einbettung in die Pipeline (nur dort aktiv, wo sie Sinn ergibt,
deterministisch, Text-Knockout greift auch für die Schraffur).
"""

import math

import pytest

import generators
from core import ir
from core import pattern_doc as pd
from core.build import build_scene
from core.containers import make_container
from core.geom import point_in_polygon, polygon_area
from core.hatch import (AIM_CENTER, AIM_RANDOM, HatchStyle, KIND_CROSS,
                        hatch_areas, scanlines, style_from_doc)

TILING_IDS = [pid for pid, cls in generators.REGISTRY.items() if cls.tiling]


def square(size, cx=0.0, cy=0.0):
    h = size / 2.0
    return [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]


def rnd(seed=1):
    import random
    return random.Random(seed)


def hatch_doc(pattern_id="honeycomb", **style):
    doc = pd.default_doc(pattern_id)
    doc["style"].update({"mode": "area", "fillTarget": "webs", "border": True,
                         "thickness": 0.1, "borderWidth": 0.2, "clip": "cut",
                         "hatch": True, "hatchSpacing": 0.4, "hatchThickness": 0.06})
    doc["style"].update(style)
    doc["textLayers"][0]["enabled"] = False
    return doc


def strips(scene):
    return [el for el in scene.elements
            if isinstance(el, ir.Path) and el.role == ir.ROLE_REGION and el.closed]


def direction(strip):
    """Richtung eines Streifens (längste Kante des Rechtecks), 0..pi."""
    pts = strip.points
    best, ang = 0.0, 0.0
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d > best:
            best, ang = d, math.atan2(b[1] - a[1], b[0] - a[0])
    return ang % math.pi


# ------------------------------------------------------------------ Scanline

def test_scanline_fills_a_square():
    segs = scanlines(square(1.0), 0.0, 0.25)
    # Raster 0,25 in [-0,5 .. 0,5]; die beiden Randtangenten fallen weg
    assert len(segs) == 3
    assert sorted(round(a[1], 6) for a, _ in segs) == [-0.25, 0.0, 0.25]
    for a, b in segs:
        assert a[1] == pytest.approx(b[1])      # waagerecht
        assert abs(b[0] - a[0]) == pytest.approx(1.0, abs=1e-9)


def test_scanline_follows_the_angle():
    for deg in (0, 30, 45, 90, 137):
        segs = scanlines(square(2.0), math.radians(deg), 0.3)
        assert segs
        for a, b in segs:
            ang = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
            assert ang == pytest.approx(math.radians(deg) % math.pi, abs=1e-9)


def test_scanline_splits_at_a_notch():
    """Konkave Zelle (U-Form): eine Linie ergibt dort ZWEI Strecken.

    Genau das kann das konvexe Clipping in ``core/clip.py`` nicht - deshalb die
    eigene Scanline.
    """
    u = [(-1, -1), (1, -1), (1, 1), (0.4, 1), (0.4, -0.2),
         (-0.4, -0.2), (-0.4, 1), (-1, 1)]
    on_notch = [s for s in scanlines(u, 0.0, 0.1) if s[0][1] > 0.2]
    assert on_notch
    per_line = {}
    for a, b in on_notch:
        per_line.setdefault(round(a[1], 6), []).append((a, b))
    assert all(len(v) == 2 for v in per_line.values())


def test_scanline_grid_is_absolute_so_cells_align():
    """Gleicher Winkel ⇒ die Linien fluchten über Zellgrenzen hinweg."""
    left = scanlines(square(1.0, cx=-0.5), 0.0, 0.25)
    right = scanlines(square(1.0, cx=+0.5), 0.0, 0.25)
    assert [round(s[0][1], 9) for s in left] == [round(s[0][1], 9) for s in right]


def test_scanline_bails_out_on_absurd_density():
    assert scanlines(square(100.0), 0.0, 0.001) == []


# -------------------------------------------------------------- Streifenbau

def test_strips_are_anchored_in_the_web():
    """Kein schwebender Steg: jeder Streifen ragt über die freie Fläche hinaus."""
    poly = square(2.0)
    made, _ = hatch_areas([poly], HatchStyle(spacing=0.5, thickness=0.1),
                          rnd(), web_half=0.05)
    assert made
    for strip in made:
        assert any(not point_in_polygon(p, poly) for p in strip.points), \
            "Streifen liegt vollständig in der Zelle - er würde schweben"


def test_strips_are_closed_areas_with_the_hatch_thickness():
    made, _ = hatch_areas([square(2.0)], HatchStyle(spacing=0.5, thickness=0.08),
                          rnd(), web_half=0.0)
    assert made
    for strip in made:
        assert strip.closed and strip.role == ir.ROLE_REGION
        assert abs(polygon_area(strip.points)) > 0.0
        short = min(math.hypot(strip.points[i][0] - strip.points[i - 1][0],
                               strip.points[i][1] - strip.points[i - 1][1])
                    for i in range(len(strip.points)))
        assert short == pytest.approx(0.08, abs=1e-9)


def test_cross_hatch_adds_a_second_raster():
    single, _ = hatch_areas([square(2.0)], HatchStyle(spacing=0.4), rnd(), 0.0)
    cross, _ = hatch_areas([square(2.0)], HatchStyle(spacing=0.4, kind=KIND_CROSS),
                           rnd(), 0.0)
    assert len(cross) > len(single)
    assert len({round(direction(s), 6) for s in cross}) == 2


def test_random_aim_varies_per_cell():
    polys = [square(1.0, cx=x) for x in (-2.0, 0.0, 2.0)]
    style = HatchStyle(spacing=0.3, aim=AIM_RANDOM, jitter=math.pi / 2.0)
    made, _ = hatch_areas(polys, style, rnd(), 0.0)
    assert len({round(direction(s), 6) for s in made}) == 3


def test_center_aim_points_every_cell_at_the_center():
    center = (0.0, 0.0)
    polys = [square(1.0, cx=3.0, cy=0.0), square(1.0, cx=0.0, cy=3.0)]
    style = HatchStyle(spacing=0.3, aim=AIM_CENTER, center=center)
    made, _ = hatch_areas(polys, style, rnd(), 0.0)
    for strip in made:
        cx = sum(p[0] for p in strip.points) / len(strip.points)
        cy = sum(p[1] for p in strip.points) / len(strip.points)
        target = math.atan2(center[1] - cy, center[0] - cx) % math.pi
        # Winkelvergleich zyklisch: 0 und pi sind dieselbe Richtung
        delta = abs(direction(strip) - target) % math.pi
        assert min(delta, math.pi - delta) < 0.35


def test_too_many_strips_are_capped_with_a_warning():
    made, warnings = hatch_areas([square(60.0)] * 20, HatchStyle(spacing=0.05),
                                 rnd(), 0.0)
    assert warnings and len(made) <= 20000


# ---------------------------------------------------------------- Pipeline

def test_hatch_is_off_by_default():
    assert pd.default_doc("honeycomb")["style"]["hatch"] is False
    assert style_from_doc(pd.default_doc("honeycomb")["style"]) is None


@pytest.mark.parametrize("style", [
    {"mode": "lines"},                     # Linienmodus: kein Flächenmodell
    {"fillTarget": "cells"},               # Zellen sind schon massiv
])
def test_hatch_only_where_it_makes_sense(style):
    doc = hatch_doc(**style)
    assert style_from_doc(doc["style"]) is None


@pytest.mark.parametrize("pattern_id", TILING_IDS)
def test_every_tiling_pattern_can_be_hatched(pattern_id):
    plain = build_scene(hatch_doc(pattern_id, hatch=False))
    hatched = build_scene(hatch_doc(pattern_id))
    assert len(strips(hatched)) > len(strips(plain))
    assert not hatched.warnings


@pytest.mark.parametrize("pattern_id", TILING_IDS)
def test_hatch_does_not_change_the_pattern_itself(pattern_id):
    """Schraffur ist additiv - Fläche und Löcher bleiben Bit für Bit gleich."""
    def face(scene):
        return [el.to_dict() for el in scene.elements
                if getattr(el, "role", "") in (ir.ROLE_FACE, ir.ROLE_HOLE)]
    assert face(build_scene(hatch_doc(pattern_id))) == \
           face(build_scene(hatch_doc(pattern_id, hatch=False)))


def test_hatch_is_deterministic():
    doc = hatch_doc("voronoi", hatchAim="random")
    assert build_scene(doc).to_dict() == build_scene(doc).to_dict()


def test_hatch_stays_inside_the_container():
    doc = hatch_doc("grid")
    outline = make_container(doc["container"]).clip_polygon()
    for strip in strips(build_scene(doc)):
        for p in strip.points:
            assert point_in_polygon(p, outline)


def test_hatch_respects_the_text_knockout():
    from text.text_layer import text_box
    doc = hatch_doc("grid")
    doc["textLayers"][0].update({"enabled": True, "knockout": True,
                                 "text": "TEST", "height": 1.2})
    box = text_box(doc["textLayers"][0])
    for strip in strips(build_scene(doc)):
        assert not any(point_in_polygon(p, box) for p in strip.points)


def test_hatch_also_works_without_the_face_model():
    """Ohne Rahmen greift das alte Stroken - die Schraffur muss trotzdem kommen."""
    scene = build_scene(hatch_doc("grid", border=False))
    assert not [el for el in scene.elements if getattr(el, "role", "") == ir.ROLE_FACE]
    assert len(strips(scene)) > len(strips(build_scene(hatch_doc("grid", border=False,
                                                                hatch=False))))
