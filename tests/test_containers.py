"""Container und Clipping - alle Rahmenformen."""

import math

import pytest

from core import ir
from core.containers import (CircleContainer, EllipseContainer, PolygonContainer,
                             RectContainer, make_container)
from core.geom import bbox, polygon_area

SHAPES = [
    ("rect", {"shape": "rect", "width": 10.0, "height": 6.0}),
    ("square", {"shape": "square", "width": 8.0}),
    ("rounded", {"shape": "rect", "width": 10.0, "height": 6.0, "cornerRadius": 1.0}),
    ("circle", {"shape": "circle", "diameter": 8.0}),
    ("ellipse", {"shape": "ellipse", "width": 10.0, "height": 6.0}),
    ("polygon", {"shape": "polygon", "diameter": 8.0, "sides": 6}),
    ("triangle", {"shape": "polygon", "diameter": 8.0, "sides": 3}),
    ("dodecagon", {"shape": "polygon", "diameter": 8.0, "sides": 12}),
]


@pytest.mark.parametrize("name,cfg", SHAPES)
def test_container_basics(name, cfg):
    c = make_container(cfg)
    x0, y0, x1, y1 = c.bounding_rect()
    assert x1 > x0 and y1 > y0
    assert len(c.clip_polygon()) >= 3
    assert c.contains((0.0, 0.0))
    assert c.outline()


@pytest.mark.parametrize("name,cfg", SHAPES)
def test_clipping_keeps_geometry_inside(name, cfg):
    """Eine lange Linie quer durch den Container wird auf die Form beschnitten."""
    c = make_container(cfg)
    pieces = c.clip_path([(-100.0, 0.3), (100.0, 0.3)], closed=False)
    assert pieces, "Linie durch die Mitte muss ein Teilstück ergeben"
    x0, y0, x1, y1 = c.bounding_rect()
    for piece in pieces:
        for x, y in piece:
            assert x0 - 1e-6 <= x <= x1 + 1e-6
            assert y0 - 1e-6 <= y <= y1 + 1e-6


@pytest.mark.parametrize("name,cfg", SHAPES)
def test_clipping_drops_geometry_completely_outside(name, cfg):
    c = make_container(cfg)
    assert c.clip_path([(500.0, 500.0), (600.0, 600.0)], closed=False) == []
    assert c.clip_path([(500.0, 500.0), (600.0, 500.0), (600.0, 600.0)],
                       closed=True) == []


@pytest.mark.parametrize("name,cfg", SHAPES)
def test_polygon_clipping_reduces_area(name, cfg):
    c = make_container(cfg)
    big = [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)]
    pieces = c.clip_path(big, closed=True)
    assert len(pieces) == 1
    area = abs(polygon_area(pieces[0]))
    x0, y0, x1, y1 = c.bounding_rect()
    assert 0 < area <= (x1 - x0) * (y1 - y0) + 1e-6


def test_fully_inside_detects_partial_geometry():
    c = RectContainer(10.0, 6.0)
    assert c.fully_inside([(0.0, 0.0), (1.0, 1.0)])
    assert not c.fully_inside([(0.0, 0.0), (100.0, 0.0)])


def test_circle_outline_is_a_real_circle_not_a_polygon():
    c = CircleContainer(8.0)
    outline = c.outline()
    assert len(outline) == 1
    assert isinstance(outline[0], ir.Circle)
    assert outline[0].radius == pytest.approx(4.0)


def test_ellipse_outline_is_a_real_ellipse():
    outline = EllipseContainer(10.0, 6.0).outline()
    assert isinstance(outline[0], ir.Ellipse)
    assert (outline[0].rx, outline[0].ry) == pytest.approx((5.0, 3.0))


def test_rounded_rect_outline_uses_real_arcs():
    outline = RectContainer(10.0, 6.0, 1.0).outline()
    arcs = [e for e in outline if isinstance(e, ir.Arc)]
    lines = [e for e in outline if isinstance(e, ir.Path)]
    assert len(arcs) == 4 and len(lines) == 4


def test_polygon_container_limits_side_count():
    assert PolygonContainer(8.0, 2).sides == 3
    assert PolygonContainer(8.0, 99).sides == 12
    assert len(PolygonContainer(8.0, 7).clip_polygon()) == 7


def test_circle_clip_polygon_encloses_the_true_circle():
    """Die Naeherung darf Randelemente nicht faelschlich abschneiden."""
    c = CircleContainer(8.0)
    poly = c.clip_polygon()
    for x, y in poly:
        assert math.hypot(x, y) >= 4.0 - 1e-9
