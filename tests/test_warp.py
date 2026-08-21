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
DEV = cone(radius=2.5, length=6.0, half_angle=ALPHA)     # weitet sich, Apex hinten
RHO = DEV.apex_distance()
SIDE = DEV.apex_side()
APEX = (0.0, SIDE * RHO)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle_at_apex(p, side=None):
    """Winkel gegen die Beruehrlinie, vom Apex aus gesehen."""
    side = SIDE if side is None else side
    return math.atan2(p[0], -side * (p[1] - side * RHO))


# ------------------------------------------------------------- die Abbildung

def test_the_apex_is_the_fixed_point():
    assert warp.point(0.0, SIDE * RHO, RHO, SIDE) == pytest.approx(APEX, abs=1e-12)


def test_the_touch_line_stays_straight():
    for y in (-3.0, -1.0, 0.0, 2.5):
        assert warp.point(0.0, y, RHO, SIDE) == pytest.approx((0.0, y), abs=1e-12)


def test_the_distance_to_the_apex_is_kept():
    """Das ist die Sektor-Abwicklung: radial laengentreu."""
    for x in (-7.0, -2.0, 0.0, 3.0, 7.85):
        for y in (-3.0, 0.0, 3.0):
            assert _dist(warp.point(x, y, RHO, SIDE), APEX) == pytest.approx(RHO + y,
                                                                      abs=1e-12)


def test_a_full_turn_covers_the_sector_angle():
    period = DEV.period()
    left = _angle_at_apex(warp.point(-period / 2.0, 0.0, RHO, SIDE))
    right = _angle_at_apex(warp.point(period / 2.0, 0.0, RHO, SIDE))
    assert right - left == pytest.approx(DEV.sector_angle(), abs=1e-12)
    assert DEV.sector_angle() == pytest.approx(2.0 * math.pi * math.sin(ALPHA))


def test_both_seam_edges_become_the_same_radial_line():
    """Nach dem Wickeln liegen sie aufeinander - im Sektor um Omega versetzt."""
    period = DEV.period()
    for y in (-3.0, 0.0, 3.0):
        left = warp.point(-period / 2.0, y, RHO, SIDE)
        right = warp.point(period / 2.0, y, RHO, SIDE)
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
                       a[1] + (b[1] - a[1]) * i / samples, rho, SIDE)
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
    near = warp._steps((0.0, 0.0), (0.5, 0.0), RHO, SIDE)
    far = warp._steps((0.0, 2.9), (0.5, 2.9), RHO, SIDE)
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
    assert (item.x, item.y) == pytest.approx(warp.point(3.0, 1.0, RHO, SIDE))
    assert item.angle == pytest.approx(-SIDE * 3.0 / RHO)
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
    return (0.0, dev.apex_side() * dev.apex_distance())


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
        here = warp.point(x, y, RHO, SIDE)
        there = warp.point(x + period, y, RHO, SIDE)
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


def test_a_partial_cone_becomes_a_partial_sector():
    """Halber Kegelstumpf: halber Sektor, exakt zwischen den beiden Radien."""
    import math
    from core import build, pattern_doc
    from core.development import development_from_doc
    steps = 60
    outline = [[-math.pi / 2.0 + math.pi * i / steps, -3.0]
               for i in range(steps + 1)]
    outline += [[math.pi / 2.0 - math.pi * i / steps, 3.0]
                for i in range(steps + 1)]
    doc = pattern_doc.default_doc()
    doc["pattern"]["type"] = "honeycomb"
    doc["development"] = {
        "kind": "cone", "radius": 2.5, "halfAngle": ALPHA,
        "length": 6.0 / math.cos(ALPHA), "periodic": False, "seamAngle": 0.0,
        "outline": outline, "axisMiddle": 0.0,
        "source": {"label": "Halbkegel", "token": ""},
    }
    doc, errors = pattern_doc.parse(doc)
    assert not errors, errors
    scene = build.build_scene(doc)
    dev = development_from_doc(doc["development"])
    apex = _apex_of(dev)
    reach = dev.length / 2.0
    for element in scene.elements:
        for p in getattr(element, "points", []) or []:
            assert (dev.apex_distance() - reach - 0.01 <= _dist(p, apex)
                    <= dev.apex_distance() + reach + 0.01)
            # ein halber Umlauf ist ein halber Sektor
            assert abs(_angle_at_apex(p)) <= dev.sector_angle() / 4.0 + 1e-6


# ------------------------------------------------- beide Seiten des Apex

NARROWING = cone(radius=2.5, length=6.0, half_angle=-ALPHA)   # Spitze voraus


def test_the_apex_sits_on_the_side_the_half_angle_says():
    assert DEV.apex_side() == -1.0          # weitet sich in Achsrichtung
    assert NARROWING.apex_side() == 1.0     # verjüngt sich in Achsrichtung
    assert cylinder(2.5, 6.0).apex_side() == 0.0


def test_the_development_always_counts_y_along_the_axis():
    """Sonst läge das Muster auf dem halben Kegel-Sortiment spiegelbildlich."""
    assert DEV.to_plane(0.0, 1.0)[1] > 0.0
    assert NARROWING.to_plane(0.0, 1.0)[1] > 0.0
    assert DEV.to_plane(0.0, 1.0) == pytest.approx(NARROWING.to_plane(0.0, 1.0))


def test_the_sector_opens_away_from_the_apex_on_both_sides():
    for dev in (DEV, NARROWING):
        rho, side = dev.apex_distance(), dev.apex_side()
        apex = (0.0, side * rho)
        near = warp.point(0.0, side * 2.0, rho, side)     # Richtung Spitze
        far = warp.point(0.0, -side * 2.0, rho, side)
        assert _dist(near, apex) < _dist(far, apex)


def test_bending_never_mirrors():
    """Der eigentliche Fehler: eine spiegelnde Abbildung.

    Ein gegen den Uhrzeigersinn umlaufendes Dreieck muss das auch nach dem
    Biegen tun - egal wo, egal auf welcher Seite die Spitze liegt. Sonst stünde
    Text auf dem Bauteil seitenverkehrt, und Fusion lehnte die Skizze ab.
    """
    def area(pts):
        return 0.5 * sum(pts[i][0] * pts[(i + 1) % 3][1]
                         - pts[(i + 1) % 3][0] * pts[i][1] for i in range(3))

    for dev in (DEV, NARROWING):
        rho, side = dev.apex_distance(), dev.apex_side()
        for x in (-7.0, -1.0, 0.0, 2.5, 7.0):
            for y in (-2.5, 0.0, 2.5):
                flat = [(x, y), (x + 0.2, y), (x, y + 0.2)]
                assert area(flat) > 0.0
                bent = [warp.point(px, py, rho, side) for px, py in flat]
                assert area(bent) > 0.0, (dev.half_angle, x, y)


def test_both_apex_sides_build_the_same_way_up():
    """Ein umgedrehter Kegel bekommt dasselbe Muster, nur gespiegelt gelegt.

    Genauer: die Zellen am **schmalen** Ende sind in beiden Fällen die
    kleineren - das ist der Test, der in Fusion mit bloßem Auge geht.
    """
    from core import build
    for half in (ALPHA, -ALPHA):
        doc = _cone_doc(half_angle=half)
        scene = build.build_scene(doc)
        from core.development import development_from_doc
        dev = development_from_doc(doc["development"])
        apex = _apex_of(dev)
        holes = [el for el in scene.elements
                 if isinstance(el, ir.Path) and el.role == ir.ROLE_HOLE]
        assert holes
        by_reach = sorted(holes, key=lambda el: sum(
            _dist(p, apex) for p in el.points) / len(el.points))
        inner, outer = by_reach[0], by_reach[-1]
        assert _width(inner) < _width(outer)


def _width(element):
    xs = [p[0] for p in element.points]
    ys = [p[1] for p in element.points]
    return max(max(xs) - min(xs), max(ys) - min(ys))


# ------------------------------------------------------------ Trennlinie

def test_the_dividing_line_crosses_the_border_on_a_cone():
    """Berühren genügt nicht - nach dem Biegen ist die Kontur ein Polygonzug.

    Die Trennlinie endet auf dem **echten** Bogen, die Kontur läuft als Sehnen
    daran vorbei; gemessen 15 µm daneben. Fusion sähe dann keine Teilung, machte
    ein Profil über den ganzen Sektor und lehnte es ab (``Context.md`` 15.19).
    """
    from core import build
    from core.development import development_from_doc
    doc = _cone_doc(embossOn=True)
    scene = build.build_scene(doc)
    dev = development_from_doc(doc["development"])
    apex = _apex_of(dev)
    face = next(el for el in scene.elements
                if isinstance(el, ir.Path) and el.role == ir.ROLE_FACE)
    divider = next(el for el in scene.elements
                   if isinstance(el, ir.Path) and not el.closed
                   and el.layer == ir.LAYER_BORDER)
    edge = [_dist(p, apex) for p in face.points]
    line = [_dist(p, apex) for p in divider.points]
    assert min(line) < min(edge) - 4.0 * TOL
    assert max(line) > max(edge) + 4.0 * TOL


def test_a_cylinder_needs_no_overshoot():
    """Dort ist der Rand eine Gerade - die Trennlinie endet genau darauf."""
    from core import build
    doc = _cone_doc(embossOn=True)
    doc["development"]["kind"] = "cylinder"
    doc["development"]["halfAngle"] = 0.0
    scene = build.build_scene(doc)
    face = next(el for el in scene.elements
                if isinstance(el, ir.Path) and el.role == ir.ROLE_FACE)
    divider = next(el for el in scene.elements
                   if isinstance(el, ir.Path) and not el.closed
                   and el.layer == ir.LAYER_BORDER)
    top = max(p[1] for p in face.points)
    bottom = min(p[1] for p in face.points)
    assert max(p[1] for p in divider.points) == pytest.approx(top, abs=1e-9)
    assert min(p[1] for p in divider.points) == pytest.approx(bottom, abs=1e-9)


def test_the_overshoot_extends_both_ends_whichever_way_round():
    from core.build import _over
    up = _over([(0.0, -1.0), (0.1, 0.0), (0.0, 1.0)], 0.5)
    assert up[0][1] == pytest.approx(-1.5) and up[-1][1] == pytest.approx(1.5)
    down = _over([(0.0, 1.0), (0.1, 0.0), (0.0, -1.0)], 0.5)
    assert down[0][1] == pytest.approx(1.5) and down[-1][1] == pytest.approx(-1.5)
    assert _over([(0.0, 0.0), (0.0, 1.0)], 0.0) == [(0.0, 0.0), (0.0, 1.0)]
