"""Skizzenelement-Optimierer: weniger Entities, gleiche sichtbare Geometrie.

Die wichtigste Datei hier ist der **Fidelity-Harness**: für jedes Muster der
Registry wird die optimierte gegen die unoptimierte Kontur gemessen. Solange die
maximale Abweichung unter ``TOL`` bleibt, darf der Optimierer beliebig
aggressiver werden - dieser Test ist das Sicherheitsnetz für alle weiteren Pässe.
"""

import math
from unittest import mock

import pytest

import generators
import core.build as build
import core.stroker as stroker
from core import ir
from core import pattern_doc as pd
from core.build import build_scene, entity_estimate
from core.geom import catmull_rom, polygon_area, polyline_length
from core.optimize import TOL, optimize
from core.optimize import (MAX_SPLINE_KINK, MIN_SPLINE_POINTS, _drop_collinear,
                           _max_kink, _reduce_indices, _self_intersects, _to_spline)

PATTERN_IDS = sorted(generators.REGISTRY)

#: Stil-Varianten, die deutlich verschiedene Pipeline-Zweige treffen
STYLE_CASES = [
    {},
    {"mode": "lines"},
    {"fillTarget": "cells"},
    {"border": False},
    {"hatch": True},
]


def doc_for(pattern_id, **style):
    doc = pd.default_doc(pattern_id)
    doc["seed"] = 42
    doc["style"].update(style)
    return doc


def raw_scene(doc):
    """Szene ohne Optimierer - der Vergleichsmaßstab."""
    with mock.patch.object(build, "optimize", lambda els: list(els)):
        return build_scene(doc)


# --------------------------------------------------------------- Messhilfen

def _point_to_segment(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    if ll < 1e-24:
        return math.dist(p, a)
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / ll
    t = max(0.0, min(1.0, t))
    return math.dist(p, (ax + dx * t, ay + dy * t))


def max_deviation(src, dst, closed):
    """Größter Abstand eines Punktes aus ``src`` zur Polylinie ``dst``."""
    if len(dst) < 2:
        return float("inf")
    n = len(dst)
    segs = [(dst[i], dst[(i + 1) % n]) for i in range(n if closed else n - 1)]
    return max(min(_point_to_segment(p, a, b) for a, b in segs) for p in src)


def samples_of(pts, closed):
    """Stützpunkte **und** Sehnenmitten.

    Nur die Stützpunkte zu messen wäre zu gutmütig: ein Kreis- oder Bogen-Refit
    kann exakt durch alle Punkte laufen und trotzdem zwischen ihnen ausbeulen.
    Genau diese Bogenhöhe fangen die Sehnenmitten ab.
    """
    n = len(pts)
    out = list(pts)
    for i in range(n if closed else n - 1):
        a, b = pts[i], pts[(i + 1) % n]
        out.append(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0))
    return out


def reference_samples(el):
    """Stichproben der **tatsächlichen** Ausgangskurve.

    Ein Element, das schon der Generator als Spline geliefert hat, ist keine
    Polylinie - es gegen seine eigenen Sehnen zu messen würde die Ausbeulung
    des Generators dem Optimierer anlasten.
    """
    if el.curve == "spline" and len(el.points) > 2:
        return catmull_rom(el.points, samples=4, closed=el.closed)
    return samples_of(el.points, el.closed)


def _arc_distance(p, el):
    dx, dy = p[0] - el.center[0], p[1] - el.center[1]
    a0, a1 = min(el.a0, el.a1), max(el.a0, el.a1)
    ang = math.atan2(dy, dx)
    while ang < a0:
        ang += 2.0 * math.pi
    if ang <= a1:
        return abs(math.hypot(dx, dy) - el.radius)
    ends = [(el.center[0] + el.radius * math.cos(a),
             el.center[1] + el.radius * math.sin(a)) for a in (el.a0, el.a1)]
    return min(math.dist(p, e) for e in ends)


def deviation(src, closed, out):
    """Abweichung der Stichproben ``src`` vom optimierten Element ``out``."""
    if isinstance(out, ir.Circle):
        return max(abs(math.dist(p, out.center) - out.radius) for p in src)
    if isinstance(out, ir.Arc):
        return max(_arc_distance(p, out) for p in src)
    if out.curve == "spline":
        # Ein Spline ist keine Polylinie - er muss erst abgetastet werden,
        # sonst misst der Harness die Ausbeulung zwischen den Stützpunkten nicht.
        return max_deviation(src, catmull_rom(out.points, samples=8, closed=out.closed),
                             out.closed)
    return max_deviation(src, out.points, closed)


def test_the_harness_measures_what_it_promises():
    """Der Harness selbst muss stimmen, sonst misst er nichts."""
    assert max_deviation([(1.0, 0.5)], [(0.0, 0.0), (2.0, 0.0)], False) == pytest.approx(0.5)
    assert max_deviation([(1.0, 0.0)], [(0.0, 0.0), (2.0, 0.0)], False) == pytest.approx(0.0)
    # Sehnenmitte einer Sehne quer durch den Einheitskreis: 1 - 0 = 1 daneben
    circle = ir.Circle((0.0, 0.0), 1.0)
    assert deviation(samples_of([(-1.0, 0.0), (1.0, 0.0)], False), False,
                     circle) == pytest.approx(1.0)


# ------------------------------------------------------------- 1. Fidelity

@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_optimized_contours_stay_within_tolerance(pattern_id):
    """Jede einzelne Kontur weicht um weniger als ``TOL`` ab."""
    for style in STYLE_CASES:
        scene = raw_scene(doc_for(pattern_id, **style))
        for el in scene.elements:
            if not isinstance(el, ir.Path) or len(el.points) < 2:
                continue
            out = optimize([el])
            assert len(out) == 1, "ein Element darf nicht verschwinden"
            if out[0] is el:
                continue                   # unangetastet, nichts zu messen
            dev = deviation(reference_samples(el), el.closed, out[0])
            assert dev < TOL, "%s %s: %.6f cm Abweichung" % (pattern_id, style, dev)


@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_closed_contours_keep_their_area(pattern_id):
    """Flächen bleiben Flächen - und behalten ihren Inhalt.

    Verschiebt sich eine Kontur um höchstens ``TOL``, kann sich ihr Inhalt um
    höchstens ``Umfang * TOL`` ändern. Mehr wäre keine Vereinfachung mehr.
    """
    for el in raw_scene(doc_for(pattern_id)).elements:
        if not isinstance(el, ir.Path) or not el.closed or len(el.points) < 3:
            continue
        out = optimize([el])[0]
        if not isinstance(out, ir.Path):
            continue                       # Kreis-Refit: eigener Test unten
        assert out.closed and len(out.points) >= 3
        before, after = abs(polygon_area(el.points)), abs(polygon_area(out.points))
        limit = polyline_length(el.points, closed=True) * TOL + 1e-9
        assert abs(after - before) <= limit, pattern_id


# ------------------------------------------------------------ 2. Reduktion

@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_optimizer_never_adds_entities(pattern_id):
    for style in STYLE_CASES:
        doc = doc_for(pattern_id, **style)
        assert entity_estimate(build_scene(doc)) <= entity_estimate(raw_scene(doc))


# ---------------------------------------------------------- 3. Gültigkeit

@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_roles_and_layers_survive(pattern_id):
    """Rolle und Layer bleiben erhalten.

    Der *Typ* darf sich ändern - genau das tun Kreis- und Bogen-Refit.
    """
    doc = doc_for(pattern_id)
    def profile(scene):
        return sorted((getattr(el, "role", ""), getattr(el, "layer", ""))
                      for el in scene.elements)
    assert profile(build_scene(doc)) == profile(raw_scene(doc))


@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_optimizing_never_creates_a_self_intersection(pattern_id):
    """Ein sich selbst schneidendes Profil ist in Fusion unbrauchbar.

    Gemessen wird die *Zunahme*: was schon vorher krumm war, macht der
    Optimierer nicht gerade - er darf es aber auch nicht schlimmer machen.
    """
    def broken(scene):
        return sum(1 for el in scene.elements
                   if isinstance(el, ir.Path) and el.curve == "line"
                   and _self_intersects(el.points, el.closed))
    for style in STYLE_CASES:
        doc = doc_for(pattern_id, **style)
        assert broken(build_scene(doc)) <= broken(raw_scene(doc)), \
            "%s %s" % (pattern_id, style)


#: Die Fälle, in denen der Stroker vor dem Fix nachweislich Schleifen anlegte -
#: immer der Strok-Pfad (``_to_areas``), nie das Flächenmodell (``_to_face``).
LOOP_CASES = [(pid, style)
              for pid in ("tissue", "leaf_veins", "puzzle", "pebbles")
              for style in ({"border": False}, {"clip": "off"})]


def unguarded_stroker():
    """Der Stroker ohne ``remove_loops`` - der Stand vor dem Fix."""
    return mock.patch.object(stroker, "remove_loops", lambda pts, **kw: list(pts))


def self_intersecting(scene):
    return sum(1 for el in scene.elements
               if isinstance(el, ir.Path) and el.curve == "line" and el.closed
               and _self_intersects(el.points, True))


@pytest.mark.parametrize("pattern_id,style", LOOP_CASES)
def test_no_ring_of_a_built_scene_self_intersects(pattern_id, style):
    """Der Gehrungs-Versatz legt an Beschnittkanten Schleifen an.

    Ein sich selbst schneidendes Profil ist in Fusion nicht extrudierbar. Die
    Gegenprobe gehört dazu: ohne ``remove_loops`` sind diese Konturen wirklich
    kaputt - sonst bewiese der Test nur, dass hier nichts entsteht.
    """
    doc = doc_for(pattern_id, **style)
    with unguarded_stroker():
        before = build_scene(doc)
    assert self_intersecting(before) > 0, "Fall ohne Befund - Testfall veraltet?"
    assert self_intersecting(build_scene(doc)) == 0


@pytest.mark.parametrize("pattern_id,style", LOOP_CASES)
def test_removing_the_loops_costs_no_contour(pattern_id, style):
    """Konturzahl-Invariante: die Schleife fällt weg, der Ring bleibt."""
    doc = doc_for(pattern_id, **style)
    with unguarded_stroker():
        before = build_scene(doc).counts()
    assert build_scene(doc).counts()["contours"] == before["contours"]


@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_the_scene_is_free_of_self_intersections(pattern_id):
    """Und zwar in jeder Stil-Variante, nicht nur in den bekannten Fällen."""
    for style in STYLE_CASES:
        assert self_intersecting(build_scene(doc_for(pattern_id, **style))) == 0, \
            "%s %s" % (pattern_id, style)


def test_face_structure_of_tiling_patterns_is_untouched():
    """Fläche + Löcher bleiben genau erhalten (Ergänzung zu test_face_mode)."""
    for pattern_id in [pid for pid, cls in generators.REGISTRY.items() if cls.tiling]:
        doc = doc_for(pattern_id, mode="area", fillTarget="webs", border=True,
                      thickness=0.1, borderWidth=0.2, clip="cut")
        roles = [getattr(el, "role", "") for el in build_scene(doc).elements]
        raw_roles = [getattr(el, "role", "") for el in raw_scene(doc).elements]
        assert roles.count(ir.ROLE_FACE) == 1, pattern_id
        assert roles.count(ir.ROLE_HOLE) == raw_roles.count(ir.ROLE_HOLE), pattern_id


# ------------------------------------------ 4./5. Determinismus & Idempotenz

@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_two_builds_are_identical(pattern_id):
    doc = doc_for(pattern_id)
    assert build_scene(doc).to_dict() == build_scene(doc).to_dict()


@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_optimize_is_idempotent(pattern_id):
    """Sonst driftet die Geometrie über Re-Edit-Zyklen hinweg."""
    elements = raw_scene(doc_for(pattern_id)).elements
    once = optimize(elements)
    twice = optimize(once)
    assert [el.to_dict() for el in twice] == [el.to_dict() for el in once]


# ---------------------------------------------------- Pass 1 im Einzelnen

def region(points, closed=True, **kw):
    return ir.Path(points=[(float(x), float(y)) for x, y in points], closed=closed,
                   role=ir.ROLE_REGION, **kw)


def test_duplicate_points_are_dropped():
    out = optimize([region([(0, 0), (0, 0), (1, 0), (1, 0), (1, 1)], closed=False)])
    assert out[0].points == [(0, 0), (1, 0), (1, 1)]


def test_closing_duplicate_of_a_ring_is_dropped():
    out = optimize([region([(0, 0), (1, 0), (1, 1), (0, 0)])])
    assert out[0].points == [(0, 0), (1, 0), (1, 1)]


def test_collinear_runs_collapse_to_one_segment():
    out = optimize([region([(0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (0, 1)])])
    assert out[0].points == [(0, 0), (3, 0), (3, 1), (0, 1)]


def test_collinear_run_across_the_seam_of_a_ring_collapses():
    """Punkt 0 darf nicht bloß deshalb überleben, weil er Punkt 0 ist."""
    out = optimize([region([(1, 0), (2, 0), (3, 0), (3, 1), (0, 1), (0, 0)])])
    assert out[0].points == [(3, 0), (3, 1), (0, 1), (0, 0)]


def test_endpoints_of_an_open_path_survive():
    out = optimize([region([(0, 0), (1, 0), (2, 0)], closed=False)])
    assert out[0].points == [(0, 0), (2, 0)]


def test_a_spike_is_never_flattened():
    """Richtungsumkehr: kollinear, aber Weglassen würde die Spitze löschen."""
    pts = [(0, 0), (2, 0), (0, 1e-10), (0, 1)]
    assert optimize([region(pts, closed=False)])[0].points == pts


def test_splines_keep_all_their_points():
    """Ein fitted Spline läuft durch seine Stützpunkte - jeder trägt Form."""
    pts = [(0, 0), (1, 0), (2, 0), (3, 1)]
    out = optimize([region(pts, closed=False, curve="spline")])
    assert out[0].points == pts


def test_widths_stay_aligned_with_the_points():
    src = region([(0, 0), (1, 0), (2, 0), (2, 1)], closed=False)
    src.widths = [0.1, 0.2, 0.3, 0.4]
    out = optimize([src])[0]
    assert out.points == [(0, 0), (2, 0), (2, 1)]
    assert out.widths == [0.1, 0.3, 0.4]


def test_pass_one_alone_keeps_a_bend_below_the_tolerance():
    """Pass 1 ist verlustfrei: erst Pass 4 räumt Beulen unter ``TOL`` weg."""
    pts = [(0, 0), (1, 0.001), (2, 0)]
    keep = _drop_collinear(pts, [0, 1, 2], False)
    assert keep == [0, 1, 2]


# ------------------------------------------------- Pass 2: Kreis-Refit

def polygon_on_circle(center, radius, n, start=0.0, sweep=2 * math.pi):
    return [(center[0] + radius * math.cos(start + sweep * i / n),
             center[1] + radius * math.sin(start + sweep * i / n))
            for i in range(n)]


def test_a_tessellated_circle_becomes_one_circle_element():
    """Der klassische 48-Eck-Rest aus dem Clipping-Fallback."""
    pts = polygon_on_circle((1.5, -2.0), 0.9, 48)
    out = optimize([region(pts)])
    assert len(out) == 1 and isinstance(out[0], ir.Circle)
    assert out[0].center == pytest.approx((1.5, -2.0), abs=1e-9)
    assert out[0].radius == pytest.approx(0.9, abs=1e-9)
    assert out[0].role == ir.ROLE_REGION


def test_the_refitted_circle_stays_within_tolerance():
    pts = polygon_on_circle((0.0, 0.0), 0.9, 48)
    out = optimize([region(pts)])[0]
    assert deviation(samples_of(pts, True), True, out) < TOL


def test_a_coarse_polygon_is_no_circle():
    """Ein Sechseck ist ein Sechseck - die Sehnen liegen viel zu weit innen."""
    out = optimize([region(polygon_on_circle((0, 0), 1.0, 6))])
    assert isinstance(out[0], ir.Path)


def test_an_incomplete_ring_is_no_circle():
    """Fehlt ein Kreissegment, schließt die Sehne die Lücke - kein Vollkreis."""
    pts = polygon_on_circle((0, 0), 1.0, 40, sweep=1.5 * math.pi)
    out = optimize([region(pts)])
    assert isinstance(out[0], ir.Path)


def test_an_ellipse_is_no_circle():
    pts = [(1.2 * math.cos(2 * math.pi * i / 48), 0.8 * math.sin(2 * math.pi * i / 48))
           for i in range(48)]
    assert isinstance(optimize([region(pts)])[0], ir.Path)


# -------------------------------------------------- Pass 3: Bogen-Refit

def test_an_arc_polyline_becomes_one_arc_element():
    pts = polygon_on_circle((0.5, 0.5), 1.2, 24, start=0.3, sweep=1.1)
    out = optimize([region(pts, closed=False)])
    assert len(out) == 1 and isinstance(out[0], ir.Arc)
    arc = out[0]
    assert arc.center == pytest.approx((0.5, 0.5), abs=1e-9)
    assert arc.radius == pytest.approx(1.2, abs=1e-9)
    assert arc.a0 == pytest.approx(0.3, abs=1e-9)
    assert arc.a1 - arc.a0 == pytest.approx(1.1 * 23 / 24, abs=1e-9)


def test_a_clockwise_arc_keeps_its_direction():
    """Der Renderer zeichnet über ``addByCenterStartSweep`` - das Vorzeichen zählt."""
    pts = polygon_on_circle((0, 0), 1.0, 24, start=0.0, sweep=-1.2)
    arc = optimize([region(pts, closed=False)])[0]
    assert isinstance(arc, ir.Arc)
    assert arc.a1 < arc.a0


def test_the_refitted_arc_stays_within_tolerance():
    pts = polygon_on_circle((0, 0), 1.2, 24, start=0.3, sweep=1.1)
    out = optimize([region(pts, closed=False)])[0]
    assert deviation(samples_of(pts, False), False, out) < TOL


def test_a_straight_line_never_becomes_an_arc():
    out = optimize([region([(0, 0), (1, 0), (2, 0), (3, 0)], closed=False)])
    assert isinstance(out[0], ir.Path)
    assert out[0].points == [(0, 0), (3, 0)]


def test_an_s_curve_is_no_arc():
    """Richtungswechsel um den Mittelpunkt - ein Bogen kann das nicht."""
    left = polygon_on_circle((0, 0), 1.0, 12, start=0.0, sweep=1.0)
    right = polygon_on_circle((2 * math.cos(1.0), 2 * math.sin(1.0)), 1.0, 12,
                              start=1.0 + math.pi, sweep=-1.0)
    assert isinstance(optimize([region(left + right, closed=False)])[0], ir.Path)


def test_three_points_are_not_enough_for_an_arc():
    """Durch drei Punkte geht immer ein Kreis - das beweist nichts."""
    pts = polygon_on_circle((0, 0), 1.0, 3, sweep=0.6)
    assert isinstance(optimize([region(pts, closed=False)])[0], ir.Path)


# ------------------------------------------------ Pass 4: Vereinfachung

def test_a_bend_below_the_tolerance_is_removed():
    pts = [(0, 0), (1, TOL / 2), (2, 0), (2, 1)]
    assert optimize([region(pts, closed=False)])[0].points == [(0, 0), (2, 0), (2, 1)]


def test_a_bend_above_the_tolerance_survives():
    pts = [(0, 0), (1.0, 2 * TOL), (2, 0), (2, 1)]
    assert optimize([region(pts, closed=False)])[0].points == pts


def test_a_dense_wobble_collapses_but_keeps_the_shape():
    """Feine Tesselierung eines Quadrats: die Ecken bleiben, der Rest geht."""
    pts = []
    corners = [(0, 0), (4, 0), (4, 4), (0, 4)]
    for i, a in enumerate(corners):
        b = corners[(i + 1) % 4]
        pts += [(a[0] + (b[0] - a[0]) * t / 20.0, a[1] + (b[1] - a[1]) * t / 20.0)
                for t in range(20)]
    out = optimize([region(pts)])[0]
    assert sorted(out.points) == sorted([(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)])


#: Ein flaches Zelt über einer Nadel, die knapp darunter endet. Das Zelt darf
#: weg (Abweichung < TOL) - aber die begradigte Kante liefe dann durch die Nadel.
SELF_INTERSECTION_TRAP = [(0.0, 0.0), (1.0, 0.001), (2.0, 0.0), (2.0, -1.0),
                          (1.05, -1.0), (1.0, 0.0005), (0.95, -1.0), (0.0, -1.0)]


def test_the_trap_is_sound_and_rdp_would_fall_into_it():
    """Gegenprobe: ohne Wächter würde hier tatsächlich ein Selbstschnitt entstehen."""
    assert not _self_intersects(SELF_INTERSECTION_TRAP, True)
    naive = [SELF_INTERSECTION_TRAP[i]
             for i in _reduce_indices(SELF_INTERSECTION_TRAP, True, TOL)]
    assert naive != SELF_INTERSECTION_TRAP
    assert _self_intersects(naive, True)


def test_simplification_that_would_self_intersect_is_dropped():
    out = optimize([region(SELF_INTERSECTION_TRAP)])[0]
    assert out.points == SELF_INTERSECTION_TRAP, "Selbstschnitt-Wächter hat nicht gegriffen"


def test_widths_stay_aligned_through_simplification():
    src = region([(0, 0), (1, TOL / 4), (2, 0), (2, 1)], closed=False)
    src.widths = [0.1, 0.2, 0.3, 0.4]
    out = optimize([src])[0]
    assert out.points == [(0, 0), (2, 0), (2, 1)]
    assert out.widths == [0.1, 0.3, 0.4]


def test_splines_are_never_simplified():
    pts = [(0, 0), (1, TOL / 4), (2, 0), (2, 1)]
    out = optimize([region(pts, closed=False, curve="spline")])[0]
    assert out.points == pts


# --------------------------------------------- Pass 5: Spline-Umwandlung

def dense_ellipse(n, rx=1.3, ry=0.7):
    """Glatt, aber kein Kreis - sonst greift schon Pass 2."""
    return [(rx * math.cos(2 * math.pi * i / n), ry * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def test_a_densely_sampled_smooth_contour_becomes_a_spline():
    """Dicht genug abgetastet, damit die Ausbeulung unter ``TOL`` bleibt."""
    pts = dense_ellipse(90)
    out = optimize([region(pts)])[0]
    assert isinstance(out, ir.Path) and out.curve == "spline"
    assert out.points == pts, "die Stützpunkte bleiben unverändert"


def test_the_spline_stays_within_tolerance():
    pts = dense_ellipse(90)
    out = optimize([region(pts)])[0]
    assert deviation(samples_of(pts, True), True, out) < TOL


def test_a_spline_saves_all_but_one_entity():
    from core.build import entity_estimate
    pts = dense_ellipse(90)
    assert entity_estimate(ir.Scene(elements=[region(pts)])) == 90
    assert entity_estimate(ir.Scene(elements=optimize([region(pts)]))) == 1


def test_a_coarsely_sampled_contour_stays_a_polyline():
    """Wenige Punkte ⇒ die Sehnen liegen zu weit vom Spline entfernt."""
    out = optimize([region(dense_ellipse(24))])[0]
    assert isinstance(out, ir.Path) and out.curve == "line"


def test_a_contour_with_corners_stays_a_polyline():
    """Fitted Splines schwingen an echten Ecken über - Knick-Gate."""
    pts = []
    corners = [(0, 0), (4, 0), (4, 4), (0, 4)]
    for i, a in enumerate(corners):                 # dicht, aber mit 90°-Ecken
        b = corners[(i + 1) % 4]
        pts += [(a[0] + (b[0] - a[0]) * t / 8.0, a[1] + (b[1] - a[1]) * t / 8.0)
                for t in range(8)]
    # Pass 4 würde die Geraden einebnen - deshalb hier direkt Pass 5 befragen
    assert _max_kink(pts, True) > MAX_SPLINE_KINK
    assert _to_spline(region(pts), TOL).curve == "line"


def test_short_contours_are_not_worth_a_spline():
    pts = dense_ellipse(MIN_SPLINE_POINTS - 1)
    assert _to_spline(region(pts), TOL).curve == "line"


def test_the_frame_is_never_turned_into_a_spline():
    """An der Rahmenkontur hängt die zugesicherte Rahmendicke."""
    pts = dense_ellipse(90)
    face = ir.Path(points=pts, closed=True, role=ir.ROLE_FACE, layer=ir.LAYER_BORDER)
    assert _to_spline(face, TOL).curve == "line"


def test_the_spline_wins_against_the_simplification():
    """Pass 5 läuft vor Pass 4 - sonst nähme die Vereinfachung dem Spline die
    Stützpunkte weg und beide zusammen überschritten ``TOL``."""
    pts = dense_ellipse(90)
    out = optimize([region(pts)])[0]
    assert out.curve == "spline"
    assert len(out.points) == 90, "Pass 4 darf hier gar nicht erst gelaufen sein"
    # Nur eine der beiden Vereinfachungen greift, nie beide
    assert deviation(samples_of(pts, True), True, out) < TOL


def test_a_tighter_budget_blocks_the_spline():
    assert _to_spline(region(dense_ellipse(90)), TOL / 10.0).curve == "line"


# ------------------------------------------------------- Duplikatfilter

def test_identical_rings_are_dropped_once():
    a = region([(0, 0), (1, 0), (1, 1)])
    b = region([(1, 1), (1, 0), (0, 0)])       # gespiegelt und rotiert
    assert len(optimize([a, b])) == 1


def test_rings_of_different_roles_are_both_kept():
    a = region([(0, 0), (1, 0), (1, 1)])
    b = ir.Path(points=[(0, 0), (1, 0), (1, 1)], closed=True, role=ir.ROLE_HOLE)
    assert len(optimize([a, b])) == 2


def test_identical_circles_are_dropped_once():
    c = ir.Circle((0.0, 0.0), 1.0, role=ir.ROLE_REGION)
    d = ir.Circle((0.0, 0.0), 1.0, role=ir.ROLE_REGION)
    assert len(optimize([c, d])) == 1


# ------------------------------------------------------------- Schutzzonen

def test_text_and_decor_are_passed_through_untouched():
    text = ir.TextItem("AB", 0.0, 0.0, 1.0)
    decor = ir.Path(points=[(0, 0), (1, 0), (2, 0)], closed=False, role=ir.ROLE_DECOR)
    layer = ir.Path(points=[(0, 0), (1, 0), (2, 0)], closed=False, layer=ir.LAYER_TEXT)
    out = optimize([text, decor, layer])
    assert out == [text, decor, layer]
    assert decor.points == [(0, 0), (1, 0), (2, 0)]


def test_duplicate_decor_is_not_deduplicated():
    a = ir.Circle((0.0, 0.0), 1.0, role=ir.ROLE_DECOR)
    b = ir.Circle((0.0, 0.0), 1.0, role=ir.ROLE_DECOR)
    assert len(optimize([a, b])) == 2
