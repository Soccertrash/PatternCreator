"""Text-Ebene und Knockout."""

import pytest

from core import ir, pattern_doc as pd
from core.build import build_scene
from core.clip import polygon_intersects
from text.text_layer import apply_knockout, text_box, text_elements


def layer(**kw):
    base = pd.default_text_layer()
    base.update({"enabled": True, "text": "MP 2026", "height": 1.0,
                 "x": 0.0, "y": 0.0, "angle": 0.0, "knockout": True,
                 "knockoutMargin": 0.1})
    base.update(kw)
    return base


def test_disabled_layer_produces_nothing():
    off = pd.default_text_layer()
    assert text_box(off) is None
    assert text_elements(off) == []


def test_empty_text_produces_nothing():
    assert text_box(layer(text="   ")) is None
    assert text_elements(layer(text="")) == []


def test_box_grows_with_margin_and_height():
    small = text_box(layer(knockoutMargin=0.0))
    big = text_box(layer(knockoutMargin=0.5))
    from core.geom import polygon_area
    assert abs(polygon_area(big)) > abs(polygon_area(small))


def test_box_follows_rotation():
    straight = text_box(layer(angle=0.0))
    turned = text_box(layer(angle=45.0))
    assert straight != turned
    assert len(turned) == 4


def test_multiline_text_yields_one_item_per_line():
    items = text_elements(layer(text="Zeile 1\nZeile 2"))
    assert len(items) == 2
    assert items[0].y > items[1].y            # erste Zeile liegt oben


def test_unknown_font_is_kept_in_the_ir_for_the_renderer_fallback():
    items = text_elements(layer(font="GibtsNicht"))
    assert items[0].font == "GibtsNicht"      # Fallback passiert in fusion/renderer.py
    assert text_elements(layer(font=""))[0].font == "Arial"


def test_knockout_removes_open_curves_inside_the_box():
    box = text_box(layer())
    line = ir.Path(points=[(-5.0, 0.5), (5.0, 0.5)], role=ir.ROLE_EDGE)
    result = apply_knockout([line], [box])
    assert result, "ausserhalb liegende Teile bleiben erhalten"
    for piece in result:
        for p in piece.points:
            assert not _inside(p, box)


def test_knockout_drops_cells_that_touch_the_box():
    box = text_box(layer())
    hit = ir.Path(points=[(0.1, 0.1), (0.6, 0.1), (0.6, 0.6), (0.1, 0.6)],
                  closed=True, role=ir.ROLE_REGION)
    far = ir.Path(points=[(-4.0, -2.0), (-3.5, -2.0), (-3.5, -1.5), (-4.0, -1.5)],
                  closed=True, role=ir.ROLE_REGION)
    result = apply_knockout([hit, far], [box])
    assert result == [far]


def test_knockout_keeps_border_and_text_layers():
    box = text_box(layer())
    border = ir.Path(points=[(-5.0, 0.5), (5.0, 0.5)], layer=ir.LAYER_BORDER)
    assert apply_knockout([border], [box]) == [border]


def test_knockout_without_boxes_is_a_noop():
    line = ir.Path(points=[(0.0, 0.0), (1.0, 0.0)])
    assert apply_knockout([line], []) == [line]


@pytest.mark.parametrize("pattern_id", ["grid", "honeycomb", "voronoi", "waves",
                                        "phyllotaxis", "motif_scatter"])
def test_knockout_clears_the_text_area_end_to_end(pattern_id):
    doc = pd.default_doc(pattern_id)
    doc["textLayers"][0].update({"enabled": True, "text": "MUSTER", "height": 1.2,
                                 "x": -2.0, "y": -0.6, "knockout": True,
                                 "knockoutMargin": 0.15})
    box = text_box(doc["textLayers"][0])
    scene = build_scene(doc)
    for el in scene.elements:
        if not isinstance(el, ir.Path) or el.layer != ir.LAYER_PATTERN:
            continue
        assert not polygon_intersects(el.points, box), \
            "%s: Muster ragt in die Text-Box" % pattern_id


def test_without_knockout_the_pattern_stays_under_the_text():
    doc = pd.default_doc("grid")
    doc["textLayers"][0].update({"enabled": True, "text": "MUSTER", "height": 1.2,
                                 "x": -2.0, "y": -0.6, "knockout": False})
    with_text = build_scene(doc)
    doc2 = pd.default_doc("grid")
    without = build_scene(doc2)
    assert with_text.counts()["contours"] == without.counts()["contours"]
    assert with_text.counts()["texts"] == 1


def test_text_is_part_of_the_scene():
    doc = pd.default_doc("grid")
    doc["textLayers"][0].update({"enabled": True, "text": "Hallo", "height": 1.0})
    scene = build_scene(doc)
    assert scene.counts()["texts"] == 1
    assert any(isinstance(e, ir.TextItem) for e in scene.elements)


def test_text_moves_with_the_placement():
    doc = pd.default_doc("grid")
    doc["textLayers"][0].update({"enabled": True, "text": "Hallo", "height": 1.0,
                                 "x": 0.0, "y": 0.0})
    doc["placement"].update({"originX": 3.0, "originY": 1.0})
    scene = build_scene(doc)
    item = next(e for e in scene.elements if isinstance(e, ir.TextItem))
    assert (item.x, item.y) == pytest.approx((3.0, 1.0))


def _inside(p, box):
    from core.clip import half_planes
    return all(a * p[0] + b * p[1] + c < -1e-6 for a, b, c in half_planes(box))
