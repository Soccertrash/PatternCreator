"""Generatoren: Registry, Determinismus und musterspezifisches Verhalten."""

import json
import math

import pytest

import generators
from core import ir, pattern_doc as pd
from core.build import build_scene, entity_estimate
from core.geom import bbox, dedupe_segments, polygon_segments

ALL_IDS = list(generators.REGISTRY.keys())
CONTAINERS = [
    {"shape": "rect", "width": 10.0, "height": 6.0},
    {"shape": "circle", "diameter": 8.0},
    {"shape": "ellipse", "width": 10.0, "height": 6.0},
    {"shape": "polygon", "diameter": 8.0, "sides": 6},
    {"shape": "rect", "width": 10.0, "height": 6.0, "cornerRadius": 1.0},
]


def scene_for(pattern_id, **overrides):
    doc = pd.default_doc(pattern_id)
    for section, values in overrides.items():
        if section == "params":
            doc["pattern"]["params"].update(values)
        elif section == "seed":
            doc["seed"] = values
        else:
            doc[section].update(values)
    return build_scene(doc)


# ------------------------------------------------------------------ Registry

def test_registry_has_all_sixteen_patterns():
    assert len(generators.GENERATOR_CLASSES) == 16
    assert len(generators.REGISTRY) == 16


def test_registry_entries_are_complete_and_unique():
    labels = set()
    for cls in generators.GENERATOR_CLASSES:
        assert cls.id and cls.label and cls.description and cls.icon
        assert cls.label not in labels
        labels.add(cls.label)
        assert cls.fill_targets
        assert all(t in ("webs", "cells") for t in cls.fill_targets)


def test_every_pattern_is_listed_in_exactly_one_group():
    grouped = [pid for _name, ids in generators.GROUPS for pid in ids]
    assert sorted(grouped) == sorted(ALL_IDS)


# --------------------------------------------------------------- Grundlagen

@pytest.mark.parametrize("pattern_id", ALL_IDS)
def test_defaults_produce_geometry(pattern_id):
    scene = scene_for(pattern_id)
    assert scene.counts()["contours"] > 0


@pytest.mark.parametrize("pattern_id", ALL_IDS)
@pytest.mark.parametrize("container", CONTAINERS)
def test_all_container_shapes_work(pattern_id, container):
    scene = scene_for(pattern_id, container=container)
    assert scene.counts()["contours"] > 0


@pytest.mark.parametrize("pattern_id", ALL_IDS)
def test_same_seed_gives_identical_geometry(pattern_id):
    a = json.dumps(scene_for(pattern_id, seed=1234).to_dict())
    b = json.dumps(scene_for(pattern_id, seed=1234).to_dict())
    assert a == b


@pytest.mark.parametrize("pattern_id", ["voronoi", "pebbles", "tissue", "caustics",
                                        "leaf_veins", "puzzle", "spirals",
                                        "motif_scatter"])
def test_different_seed_changes_random_patterns(pattern_id):
    a = json.dumps(scene_for(pattern_id, seed=1).to_dict())
    b = json.dumps(scene_for(pattern_id, seed=2).to_dict())
    assert a != b


@pytest.mark.parametrize("pattern_id", ALL_IDS)
def test_area_mode_only_produces_closed_profiles(pattern_id):
    scene = scene_for(pattern_id, style={"mode": "area", "border": False})
    for el in scene.elements:
        if isinstance(el, ir.Path):
            assert el.closed, "%s: offene Kurve im Flächenmodus" % pattern_id
        else:
            assert isinstance(el, (ir.Circle, ir.Ellipse)), \
                "%s: %r ist im Flächenmodus nicht extrudierbar" % (pattern_id, el)


@pytest.mark.parametrize("pattern_id", ALL_IDS)
def test_line_mode_keeps_curves(pattern_id):
    scene = scene_for(pattern_id, style={"mode": "lines"})
    assert scene.counts()["contours"] > 0
    # Linienmodus erzeugt deutlich weniger Entities als der Flächenmodus
    assert entity_estimate(scene) <= entity_estimate(scene_for(pattern_id))


@pytest.mark.parametrize("pattern_id", ALL_IDS)
def test_thickness_changes_area_geometry(pattern_id):
    thin = scene_for(pattern_id, style={"thickness": 0.04})
    thick = scene_for(pattern_id, style={"thickness": 0.16})
    assert json.dumps(thin.to_dict()) != json.dumps(thick.to_dict())


@pytest.mark.parametrize("pattern_id", ALL_IDS)
def test_clip_modes(pattern_id):
    """`cut` haelt alles im Rahmen, `off` laesst es ueberstehen, `dropPartial`
    entfernt angeschnittene Elemente (ergibt nie mehr Konturen als `cut`)."""
    style = {"border": False, "thickness": 0.05}
    cut = scene_for(pattern_id, style=dict(style, clip="cut"))
    off = scene_for(pattern_id, style=dict(style, clip="off"))
    inside = scene_for(pattern_id, style=dict(style, clip="dropPartial"))

    assert cut.counts()["contours"] > 0
    # Toleranz: halbe Stegdicke, bei Blattadern das 2,5-fache (Hauptadern)
    tol = 0.05 * 2.5
    cx0, cy0, cx1, cy1 = -5.0, -3.0, 5.0, 3.0   # Standard-Rahmen 10 x 6 cm
    bx0, by0, bx1, by1 = cut.bounds()
    assert bx0 >= cx0 - tol and by0 >= cy0 - tol
    assert bx1 <= cx1 + tol and by1 <= cy1 + tol

    ox0, oy0, ox1, oy1 = off.bounds()
    assert (ox1 - ox0) >= (bx1 - bx0) - 1e-6
    assert inside.counts()["contours"] <= cut.counts()["contours"]


@pytest.mark.parametrize("pattern_id", ALL_IDS)
def test_pattern_rotation_is_applied(pattern_id):
    straight = scene_for(pattern_id, placement={"patternAngle": 0.0})
    turned = scene_for(pattern_id, placement={"patternAngle": 30.0})
    assert json.dumps(straight.to_dict()) != json.dumps(turned.to_dict())


def test_placement_moves_and_rotates_the_whole_pattern():
    base = scene_for("grid", style={"border": True})
    moved = scene_for("grid", style={"border": True},
                      placement={"originX": 5.0, "originY": -2.0})
    b0 = base.bounds()
    b1 = moved.bounds()
    assert b1[0] == pytest.approx(b0[0] + 5.0, abs=1e-6)
    assert b1[1] == pytest.approx(b0[1] - 2.0, abs=1e-6)


# ----------------------------------------------------- Technische Muster

def test_grid_spacing_acts_separately_per_axis():
    coarse = scene_for("grid", params={"spacingX": 2.0, "spacingY": 2.0})
    fine_x = scene_for("grid", params={"spacingX": 0.5, "spacingY": 2.0})
    assert fine_x.counts()["contours"] > coarse.counts()["contours"]


def test_grid_skew_produces_a_non_rectangular_raster():
    right = scene_for("grid", style={"mode": "lines"}, params={"skew": 90.0})
    skew = scene_for("grid", style={"mode": "lines"}, params={"skew": 60.0})
    assert json.dumps(right.to_dict()) != json.dumps(skew.to_dict())


def test_rhombus_dimensions_define_the_angle():
    flat = scene_for("rhombus", params={"width": 3.0, "height": 1.0})
    tall = scene_for("rhombus", params={"width": 1.0, "height": 3.0})
    assert json.dumps(flat.to_dict()) != json.dumps(tall.to_dict())


def test_honeycomb_has_no_duplicate_edges():
    """Doppelte Kanten zerstoeren Profile - der Wabengenerator muss sie vermeiden."""
    from generators import GenContext, get_generator
    import random
    gen = get_generator("honeycomb")
    ctx = GenContext(bbox=(-5, -3, 5, 3), rnd=random.Random(1))
    cells = gen.generate({"cellSize": 0.8, "orientation": "flat"}, ctx)
    segs = []
    for cell in cells:
        segs.extend(polygon_segments(cell.points))
    from core.geom import snap_segments
    assert len(snap_segments(segs)) < len(segs)          # geteilte Kanten existieren
    assert len(snap_segments(snap_segments(segs))) == len(snap_segments(segs))


@pytest.mark.parametrize("orientation", ["flat", "pointy"])
def test_honeycomb_orientations(orientation):
    scene = scene_for("honeycomb", params={"orientation": orientation})
    assert scene.counts()["contours"] > 0


def test_honeycomb_offers_webs_and_cells():
    gen = generators.get_generator("honeycomb")
    assert set(gen.fill_targets) == {"webs", "cells"}
    webs = scene_for("honeycomb", style={"fillTarget": "webs"})
    cells = scene_for("honeycomb", style={"fillTarget": "cells"})
    assert webs.counts()["contours"] != cells.counts()["contours"]


@pytest.mark.parametrize("bond,joint", [("half", 0.12), ("third", 0.12),
                                        ("free", 0.12), ("stack", 0.0)])
def test_brick_bonds_and_joints(bond, joint):
    scene = scene_for("brick", params={"bond": bond, "jointWidth": joint})
    assert scene.counts()["contours"] > 0


def test_brick_joint_width_shrinks_the_bricks():
    from generators import GenContext, get_generator
    from core.geom import polygon_area
    import random
    gen = get_generator("brick")
    ctx = GenContext(bbox=(-5, -3, 5, 3), rnd=random.Random(1))
    base = {"brickWidth": 2.0, "brickHeight": 0.8, "bond": "half",
            "offsetFraction": 0.5}
    tight = gen.generate(dict(base, jointWidth=0.0), ctx)
    loose = gen.generate(dict(base, jointWidth=0.3), ctx)
    assert polygon_area(tight[0].points) > polygon_area(loose[0].points)


def test_puzzle_pieces_are_closed_and_tabs_follow_the_seed():
    scene = scene_for("puzzle", style={"mode": "lines"}, seed=5)
    closed = [e for e in scene.elements
              if isinstance(e, ir.Path) and e.closed and e.layer == ir.LAYER_PATTERN]
    assert closed, "jedes Puzzleteil muss ein geschlossenes Profil sein"
    other = scene_for("puzzle", style={"mode": "lines"}, seed=6)
    assert json.dumps(scene.to_dict()) != json.dumps(other.to_dict())


def test_puzzle_tab_size_and_neck_width_have_an_effect():
    small = scene_for("puzzle", style={"mode": "lines"},
                      params={"tabSize": 5.0, "shapeJitter": 0.0})
    big = scene_for("puzzle", style={"mode": "lines"},
                    params={"tabSize": 40.0, "shapeJitter": 0.0})
    neck = scene_for("puzzle", style={"mode": "lines"},
                     params={"tabSize": 40.0, "neckWidth": 35.0, "shapeJitter": 0.0})
    assert json.dumps(small.to_dict()) != json.dumps(big.to_dict())
    assert json.dumps(neck.to_dict()) != json.dumps(big.to_dict())


# ------------------------------------------------------ Organische Muster

def test_voronoi_cell_count_is_capped_at_500():
    param = next(p for p in generators.REGISTRY["voronoi"].params
                 if p.key == "cellCount")
    assert param.max == 500
    doc = pd.default_doc("voronoi")
    doc["pattern"]["params"]["cellCount"] = 5000
    _parsed, errors = pd.parse(doc)
    assert "pattern.params.cellCount" in errors


def test_voronoi_fills_the_container():
    scene = scene_for("voronoi", params={"cellCount": 60}, style={"border": False})
    x0, y0, x1, y1 = scene.bounds()
    assert x1 - x0 > 9.0 and y1 - y0 > 5.0


def test_voronoi_inset_creates_separate_islands():
    joined = scene_for("voronoi", style={"fillTarget": "cells"},
                       params={"cellCount": 40, "inset": 0.0})
    islands = scene_for("voronoi", style={"fillTarget": "cells"},
                        params={"cellCount": 40, "inset": 0.15})
    assert json.dumps(joined.to_dict()) != json.dumps(islands.to_dict())


def test_pebbles_roundness_adds_points_and_core_adds_circles():
    edgy = scene_for("pebbles", style={"mode": "lines"},
                     params={"roundness": 0, "core": False})
    round_ = scene_for("pebbles", style={"mode": "lines"},
                       params={"roundness": 3, "core": False})
    edgy_pts = sum(len(e.points) for e in edgy.elements if isinstance(e, ir.Path))
    round_pts = sum(len(e.points) for e in round_.elements if isinstance(e, ir.Path))
    assert round_pts > edgy_pts

    with_core = scene_for("pebbles", style={"mode": "lines"}, params={"core": True})
    assert any(isinstance(e, ir.Circle) for e in with_core.elements)


def test_tissue_cells_are_elongated_in_x():
    from generators import GenContext, get_generator
    import random
    gen = get_generator("tissue")
    ctx = GenContext(bbox=(-5, -3, 5, 3), rnd=random.Random(3))
    params = dict(gen.defaults())
    params.update({"anisotropy": 4.0, "rows": 6, "cellCount": 60, "roundness": 0})
    cells = gen.generate(params, ctx)
    ratios = []
    for c in cells:
        x0, y0, x1, y1 = bbox(c.points)
        if y1 - y0 > 1e-6:
            ratios.append((x1 - x0) / (y1 - y0))
    assert sum(ratios) / len(ratios) > 1.5


def test_caustics_uses_variable_widths_and_optional_second_layer():
    from generators import GenContext, get_generator
    import random
    gen = get_generator("caustics")
    ctx = GenContext(bbox=(-5, -3, 5, 3), rnd=random.Random(3), thickness=0.1)
    params = dict(gen.defaults())
    single = gen.generate(params, ctx)
    assert all(e.widths is not None for e in single)
    assert any(max(e.widths) - min(e.widths) > 1e-6 for e in single)

    ctx2 = GenContext(bbox=(-5, -3, 5, 3), rnd=random.Random(3), thickness=0.1)
    params["secondLayer"] = True
    layered = gen.generate(params, ctx2)
    assert len(layered) > len(single)


def test_leaf_veins_has_two_thickness_levels():
    from generators import GenContext, get_generator
    import random
    gen = get_generator("leaf_veins")
    ctx = GenContext(bbox=(-5, -3, 5, 3), rnd=random.Random(3), thickness=0.05)
    els = gen.generate(dict(gen.defaults()), ctx)
    widths = sorted({round(e.widths[0], 6) for e in els})
    assert len(widths) == 2
    assert widths[1] > widths[0] * 2


def test_leaf_veins_without_fine_cells_only_draws_main_veins():
    from generators import GenContext, get_generator
    import random
    gen = get_generator("leaf_veins")
    ctx = GenContext(bbox=(-5, -3, 5, 3), rnd=random.Random(3), thickness=0.05)
    els = gen.generate(dict(gen.defaults(), fineCells=0), ctx)
    assert len({round(e.widths[0], 6) for e in els}) == 1


# --------------------------------------------------------- Natürliche Muster

def test_herringbone_axis_count_and_curvature():
    one = scene_for("herringbone", style={"mode": "lines"}, params={"axisCount": 1})
    many = scene_for("herringbone", style={"mode": "lines"}, params={"axisCount": 5})
    assert many.counts()["contours"] > one.counts()["contours"]

    straight = scene_for("herringbone", style={"mode": "lines"},
                         params={"curvature": 0.0})
    bowed = scene_for("herringbone", style={"mode": "lines"}, params={"curvature": 0.8})
    assert not any(getattr(e, "curve", "line") == "spline" for e in straight.elements)
    assert any(getattr(e, "curve", "line") == "spline" for e in bowed.elements)


def test_waves_are_splines_and_react_to_parameters():
    scene = scene_for("waves", style={"mode": "lines"})
    assert all(e.curve == "spline" for e in scene.elements
               if isinstance(e, ir.Path) and e.layer == ir.LAYER_PATTERN)
    dense = scene_for("waves", style={"mode": "lines"}, params={"lineSpacing": 0.2})
    assert dense.counts()["contours"] > scene.counts()["contours"]
    tall = scene_for("waves", style={"mode": "lines"}, params={"amplitude": 2.0})
    assert json.dumps(tall.to_dict()) != json.dumps(scene.to_dict())


def test_scales_rows_are_offset_and_overlapping():
    from generators import GenContext, get_generator
    import random
    gen = get_generator("scales")
    ctx = GenContext(bbox=(-5, -3, 5, 3), rnd=random.Random(1))
    arcs = gen.generate({"scaleWidth": 2.0, "overlap": 40.0, "rowOffset": 50.0}, ctx)
    rows = {}
    for a in arcs:
        rows.setdefault(round(a.center[1], 4), []).append(a.center[0])
    keys = sorted(rows)
    assert len(keys) > 2
    # Reihenabstand kleiner als der Radius -> Ueberlappung
    assert keys[1] - keys[0] < 1.0
    # benachbarte Reihen sind gegeneinander versetzt
    assert abs((min(rows[keys[0]]) - min(rows[keys[1]])) % 2.0) > 1e-6


def test_phyllotaxis_uses_the_golden_angle():
    from generators import GenContext, get_generator
    import random
    gen = get_generator("phyllotaxis")
    ctx = GenContext(bbox=(-5, -5, 5, 5), rnd=random.Random(1))
    els = gen.generate({"count": 12, "scale": 0.5, "elementSize": 0.2,
                        "shape": "circle", "growth": 0.0}, ctx)
    a1 = math.atan2(els[0].center[1], els[0].center[0])
    a2 = math.atan2(els[1].center[1], els[1].center[0])
    delta = (a2 - a1) % (2 * math.pi)
    assert delta == pytest.approx(math.radians(137.508), abs=1e-6)


@pytest.mark.parametrize("shape", ["circle", "hexagon", "drop"])
def test_phyllotaxis_element_shapes(shape):
    scene = scene_for("phyllotaxis", params={"shape": shape, "count": 60})
    assert scene.counts()["contours"] > 0


def test_phyllotaxis_growth_changes_element_size():
    from generators import GenContext, get_generator
    import random
    gen = get_generator("phyllotaxis")
    ctx = GenContext(bbox=(-5, -5, 5, 5), rnd=random.Random(1))
    els = gen.generate({"count": 100, "scale": 0.3, "elementSize": 0.2,
                        "shape": "circle", "growth": 1.0}, ctx)
    assert els[-1].radius > els[0].radius


@pytest.mark.parametrize("hand", ["ccw", "cw", "mixed"])
def test_spiral_handedness(hand):
    scene = scene_for("spirals", style={"mode": "lines"}, params={"handedness": hand})
    assert scene.counts()["contours"] > 0


def test_spiral_turns_and_count():
    few = scene_for("spirals", style={"mode": "lines"}, params={"count": 3})
    many = scene_for("spirals", style={"mode": "lines"}, params={"count": 20})
    assert many.counts()["contours"] > few.counts()["contours"]


@pytest.mark.parametrize("placement", ["grid", "stagger", "poisson"])
def test_motif_placements(placement):
    scene = scene_for("motif_scatter", params={"placement": placement})
    assert scene.counts()["contours"] > 0


@pytest.mark.parametrize("motif", ["leaf", "drop", "feather"])
def test_motif_shapes_and_ribs(motif):
    with_ribs = scene_for("motif_scatter", style={"mode": "lines"},
                          params={"motif": motif, "ribs": 5})
    without = scene_for("motif_scatter", style={"mode": "lines"},
                        params={"motif": motif, "ribs": 0})
    assert with_ribs.counts()["contours"] > without.counts()["contours"]


def test_motif_shape_factor_changes_the_outline():
    slim = scene_for("motif_scatter", style={"mode": "lines"},
                     params={"shapeFactor": 0.0, "angleJitter": 0.0, "sizeJitter": 0.0})
    round_ = scene_for("motif_scatter", style={"mode": "lines"},
                       params={"shapeFactor": 1.0, "angleJitter": 0.0, "sizeJitter": 0.0})
    assert json.dumps(slim.to_dict()) != json.dumps(round_.to_dict())


# ------------------------------------------------------------- Performance

def test_honeycomb_20x20_is_fast():
    import time
    start = time.time()
    scene = scene_for("honeycomb", container={"shape": "rect", "width": 20.0,
                                              "height": 20.0},
                      params={"cellSize": 1.0})
    assert scene.counts()["contours"] > 100
    assert time.time() - start < 5.0


def test_voronoi_300_cells_is_fast():
    import time
    start = time.time()
    scene = scene_for("voronoi", params={"cellCount": 300})
    assert scene.counts()["contours"] > 100
    assert time.time() - start < 10.0
