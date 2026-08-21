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


# ------------------------------------------------------- durch die Pipeline

def _cone_doc(pattern="honeycomb", half_angle=ALPHA, **style):
    from core import pattern_doc
    doc = pattern_doc.default_doc()
    doc["pattern"]["type"] = pattern
    doc["development"] = {
        "kind": "cone", "radius": 2.5, "halfAngle": half_angle, "length": 6.0,
        "periodic": True, "seamAngle": 0.0, "outline": [], "axisMiddle": 0.0,
        "source": {"label": "Kegel", "token": ""},
    }
    doc["style"].update(style)
    parsed, errors = pattern_doc.parse(doc)
    assert not errors, errors
    return parsed


def _apex_of(dev):
    return (0.0, -dev.apex_distance())


def test_a_cone_pattern_builds_a_ring_sector():
    """Aussenkontur, Loecher darin - und alles zwischen den beiden Radien."""
    from core import build
    doc = _cone_doc()
    scene = build.build_scene(doc)
    faces = [el for el in scene.elements
             if isinstance(el, ir.Path) and el.role == ir.ROLE_FACE]
    holes = [el for el in scene.elements
             if isinstance(el, ir.Path) and el.role == ir.ROLE_HOLE]
    assert faces and holes
    apex = _apex_of(DEV)
    inner, outer = RHO - 3.0, RHO + 3.0
    for element in faces + holes:
        for p in element.points:
            assert inner - 0.01 <= _dist(p, apex) <= outer + 0.01


def test_no_hole_pokes_through_the_outer_edge_of_the_cone():
    """Der Rahmen muss ringsum geschlossen bleiben, sonst zerfaellt der Koerper."""
    from core import build
    doc = _cone_doc()
    scene = build.build_scene(doc)
    apex = _apex_of(DEV)
    faces = [el for el in scene.elements
             if isinstance(el, ir.Path) and el.role == ir.ROLE_FACE]
    reach = [_dist(p, apex) for el in faces for p in el.points]
    holes = [el for el in scene.elements
             if isinstance(el, ir.Path) and el.role == ir.ROLE_HOLE]
    for element in holes:
        for p in element.points:
            assert min(reach) - 1e-6 <= _dist(p, apex) <= max(reach) + 1e-6


def test_a_shift_by_one_turn_becomes_a_rotation_about_the_apex():
    """Das ist der Grund, warum die Naht auch am Kegel aufgeht.

    Die beiden Nahtkanten sind vor dem Biegen exakte Verschiebungen um eine
    Periode (das prüft ``test_periodic.py``). Bildet das Biegen eine solche
    Verschiebung auf eine **Drehung um den Apex** ab, liegen sie nach dem
    Wickeln aufeinander - egal, wie weit die Zickzack-Naht ausschlägt.
    """
    period = DEV.period()
    omega = DEV.sector_angle()
    for x, y in ((-2.0, -2.5), (0.0, 0.0), (1.7, 1.0), (3.4, 2.9)):
        here = warp.point(x, y, RHO)
        there = warp.point(x + period, y, RHO)
        assert _dist(there, APEX) == pytest.approx(_dist(here, APEX), abs=1e-12)
        assert _angle_at_apex(there) - _angle_at_apex(here) == pytest.approx(
            omega, abs=1e-12)


def test_the_seam_of_a_built_cone_pattern_spans_one_sector():
    """Am fertigen Muster: der Rahmen überstreicht einen Sektor - plus Zickzack.

    Die Naht läuft nicht gerade, sondern an den Zellwänden entlang; um deren
    Ausschlag ist die Abwicklung breiter als der reine Sektorwinkel. Mehr als
    eine Zellbreite darf es nicht sein.
    """
    from core import build
    doc = _cone_doc()
    scene = build.build_scene(doc)
    faces = [el for el in scene.elements
             if isinstance(el, ir.Path) and el.role == ir.ROLE_FACE]
    angles = [_angle_at_apex(p) for el in faces for p in el.points]
    span = max(angles) - min(angles)
    cell = float(doc["pattern"]["params"]["cellSize"]) / RHO
    assert DEV.sector_angle() <= span <= DEV.sector_angle() + 3.0 * cell


def test_bending_a_real_pattern_costs_about_a_fifth():
    """Die Zahl steht in Context.md 15.14 - hier bleibt sie ehrlich."""
    from core import build
    from core.development import cylinder as make_cylinder
    doc = _cone_doc()
    bent = build.build_scene(doc)
    flat = dict(doc)
    flat["development"] = dict(doc["development"])
    flat["development"]["kind"] = "cylinder"
    flat["development"]["halfAngle"] = 0.0
    straight = build.build_scene(flat)
    assert make_cylinder(2.5, 6.0).period() == pytest.approx(DEV.period())
    before = sum(len(getattr(el, "points", []) or []) for el in straight.elements)
    after = sum(len(getattr(el, "points", []) or []) for el in bent.elements)
    assert before > 0
    assert 1.0 <= after / before < 1.6


def test_every_pattern_stays_inside_the_ring_sector():
    """Kein Element darf über die beiden Randkreise hinausragen.

    Sonst läge es nach dem Prägen neben der Fläche.
    """
    import generators
    from core import build
    from core.development import development_from_doc
    for cls in generators.GENERATOR_CLASSES:
        doc = _cone_doc(cls().id)
        scene = build.build_scene(doc)
        dev = development_from_doc(doc["development"])
        apex = _apex_of(dev)
        inner, outer = dev.apex_distance() - 3.0, dev.apex_distance() + 3.0
        for element in scene.elements:
            for p in getattr(element, "points", []) or []:
                assert inner - 0.01 <= _dist(p, apex) <= outer + 0.01, cls().id


def test_a_steep_cone_warns_about_thin_webs_at_the_narrow_end():
    """Für den Druck ist das die entscheidende Zahl."""
    from core import build
    doc = _cone_doc(half_angle=ALPHA)
    scene = build.build_scene(doc)
    assert any("schmalen Ende" in w for w in scene.warnings)


def test_a_shallow_cone_says_nothing():
    from core import build
    scene = build.build_scene(_cone_doc(half_angle=0.05))
    assert not any("schmalen Ende" in w for w in scene.warnings)


def test_the_narrowing_is_the_ratio_of_the_two_radii():
    from core.build import _cone_narrowing
    from core.development import cone as make_cone, cylinder as make_cylinder
    dev = make_cone(radius=2.5, length=6.0, half_angle=ALPHA)
    assert _cone_narrowing(dev) == pytest.approx((RHO - 3.0) / RHO)
    assert _cone_narrowing(make_cylinder(2.5, 6.0)) == 1.0
    assert _cone_narrowing(None) == 1.0
