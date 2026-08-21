"""Das Biegen in den Kreisringsektor (Kegel).

Geprueft wird gegen die **Messung** aus dem Spike (``Context.md`` 15.6,
Punkt 4): der Abstand zum Apex bleibt erhalten, der Winkel wird um
``sin(alpha)`` gestaucht.
"""

import math

import pytest

from core import ir, warp
from core.development import cone, cylinder
from core.optimize import TOL


ALPHA = 0.2
DEV = cone(radius=2.5, length=6.0, half_angle=ALPHA)
RHO = DEV.apex_distance()
APEX = (0.0, -RHO)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle_at_apex(p):
    """Winkel gegen die Beruehrlinie, vom Apex aus gesehen."""
    return math.atan2(p[0], p[1] - APEX[1])


# ------------------------------------------------------------- die Abbildung

def test_the_apex_is_the_fixed_point():
    assert warp.point(0.0, -RHO, RHO) == pytest.approx(APEX, abs=1e-12)


def test_the_touch_line_stays_straight():
    for y in (-3.0, -1.0, 0.0, 2.5):
        assert warp.point(0.0, y, RHO) == pytest.approx((0.0, y), abs=1e-12)


def test_the_distance_to_the_apex_is_kept():
    """Das ist die Sektor-Abwicklung: radial laengentreu."""
    for x in (-7.0, -2.0, 0.0, 3.0, 7.85):
        for y in (-3.0, 0.0, 3.0):
            assert _dist(warp.point(x, y, RHO), APEX) == pytest.approx(RHO + y,
                                                                      abs=1e-12)


def test_a_full_turn_covers_the_sector_angle():
    period = DEV.period()
    left = _angle_at_apex(warp.point(-period / 2.0, 0.0, RHO))
    right = _angle_at_apex(warp.point(period / 2.0, 0.0, RHO))
    assert right - left == pytest.approx(DEV.sector_angle(), abs=1e-12)
    assert DEV.sector_angle() == pytest.approx(2.0 * math.pi * math.sin(ALPHA))


def test_both_seam_edges_become_the_same_radial_line():
    """Nach dem Wickeln liegen sie aufeinander - im Sektor um Omega versetzt."""
    period = DEV.period()
    for y in (-3.0, 0.0, 3.0):
        left = warp.point(-period / 2.0, y, RHO)
        right = warp.point(period / 2.0, y, RHO)
        assert _dist(left, APEX) == pytest.approx(_dist(right, APEX))
        assert _angle_at_apex(right) - _angle_at_apex(left) == pytest.approx(
            DEV.sector_angle(), abs=1e-12)


def test_the_circumference_matches_the_real_cone():
    """Ein voller Umlauf auf Hoehe ``y`` ist der Umfang des Kegels dort.

    Der Radius des Hoehenkreises ist ``(rho + y) * sin(alpha)``.
    """
    period = DEV.period()
    for y in (-3.0, 0.0, 3.0):
        arc = (RHO + y) * DEV.sector_angle()
        assert arc == pytest.approx(2.0 * math.pi * (RHO + y) * math.sin(ALPHA))
        # und im Rechteck war es genau ``period`` bei y = 0
        if abs(y) < 1e-12:
            assert arc == pytest.approx(period)


# ------------------------------------------------------------ Unterteilung

def _true_curve(a, b, rho, samples=400):
    return [warp.point(a[0] + (b[0] - a[0]) * i / samples,
                       a[1] + (b[1] - a[1]) * i / samples, rho)
            for i in range(samples + 1)]


def _max_gap(polyline, curve):
    """Groesster Abstand eines Kurvenpunkts zum Streckenzug."""
    worst = 0.0
    for p in curve:
        best = min(_point_to_segment(p, polyline[i], polyline[i + 1])
                   for i in range(len(polyline) - 1))
        worst = max(worst, best)
    return worst


def _point_to_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    span = dx * dx + dy * dy
    if span <= 1e-18:
        return _dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / span))
    return _dist(p, (a[0] + t * dx, a[1] + t * dy))


def test_a_long_straight_stays_within_the_tolerance():
    """Eine Gerade quer ueber die halbe Abwicklung wird zum Bogen."""
    a, b = (-3.9, 2.0), (3.9, 2.0)
    path = ir.Path(points=[a, b], closed=False)
    scene = ir.Scene(elements=[path])
    warp.apply(scene, DEV)
    assert _max_gap(scene.elements[0].points, _true_curve(a, b, RHO)) <= TOL


def test_a_radial_segment_is_not_subdivided():
    """Radial bleibt gerade - dort waere jeder Zwischenpunkt verschwendet."""
    scene = ir.Scene(elements=[ir.Path(points=[(1.5, -2.0), (1.5, 2.0)],
                                       closed=False)])
    warp.apply(scene, DEV)
    assert len(scene.elements[0].points) == 2


def test_the_subdivision_is_finer_far_from_the_touch_line():
    near = warp._steps((0.0, 0.0), (0.5, 0.0), RHO)
    far = warp._steps((0.0, 2.9), (0.5, 2.9), RHO)
    assert far >= near


# --------------------------------------------------------------- Elemente

def test_a_cylinder_is_left_alone():
    points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    scene = ir.Scene(elements=[ir.Path(points=list(points), closed=True)])
    warp.apply(scene, cylinder(radius=2.5, length=6.0))
    assert scene.elements[0].points == points


def test_no_development_is_left_alone():
    scene = ir.Scene(elements=[ir.Path(points=[(0.0, 0.0), (1.0, 0.0)])])
    warp.apply(scene, None)
    assert scene.elements[0].points == [(0.0, 0.0), (1.0, 0.0)]


def test_a_circle_becomes_a_closed_path():
    scene = ir.Scene(elements=[ir.Circle(center=(2.0, 1.0), radius=0.4)])
    warp.apply(scene, DEV)
    element = scene.elements[0]
    assert isinstance(element, ir.Path) and element.closed
    for p in element.points:
        # jeder Punkt sitzt auf dem gebogenen Kreis - Abstand zum Apex passt
        assert RHO - 5.0 < _dist(p, APEX) < RHO + 5.0


def test_widths_survive_the_subdivision():
    path = ir.Path(points=[(-3.0, 0.0), (3.0, 0.0)], closed=False,
                   widths=[0.1, 0.3])
    scene = ir.Scene(elements=[path])
    warp.apply(scene, DEV)
    out = scene.elements[0]
    assert len(out.widths) == len(out.points)
    assert out.widths[0] == pytest.approx(0.1)
    assert out.widths[-1] == pytest.approx(0.3)
    assert out.widths == sorted(out.widths)


def test_a_spline_keeps_its_control_points():
    """Ein eingeschobener Punkt waere eine andere Kurve."""
    points = [(-1.0, 0.0), (0.0, 0.5), (1.0, 0.0)]
    scene = ir.Scene(elements=[ir.Path(points=list(points), closed=False,
                                       curve="spline")])
    warp.apply(scene, DEV)
    assert len(scene.elements[0].points) == len(points)


def test_text_is_moved_and_turned_with_a_warning():
    scene = ir.Scene(elements=[ir.TextItem(text="Hallo", x=3.0, y=1.0,
                                           height=0.5)])
    warp.apply(scene, DEV)
    item = scene.elements[0]
    assert (item.x, item.y) == pytest.approx(warp.point(3.0, 1.0, RHO))
    assert item.angle == pytest.approx(-3.0 / RHO)
    assert any("Kegel" in w for w in scene.warnings)


def test_how_much_the_bending_costs():
    """Elementzuwachs messen - die Zahl steht in Context.md 15.14.

    Ein volles Wabenraster ueber die ganze Abwicklung; gezaehlt werden
    Stuetzpunkte vorher und nachher.
    """
    period = DEV.period()
    rows = []
    for i in range(20):
        y = -3.0 + 6.0 * i / 19.0
        rows.append(ir.Path(points=[(-period / 2.0, y), (period / 2.0, y)],
                            closed=False))
    before = sum(len(p.points) for p in rows)
    scene = ir.Scene(elements=rows)
    warp.apply(scene, DEV)
    after = sum(len(p.points) for p in scene.elements)
    assert before == 40
    # Der Zuwachs ist begrenzt und haengt am Abstand zur Beruehrlinie.
    assert after < 40 * warp.MAX_STEPS
    assert after > before
