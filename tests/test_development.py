"""Abwicklung einer Mantelflaeche (``core/development.py``).

Der Zylinderpfad ist umgesetzt; der Kegel wartet auf eine Messung in Fusion
(``Context.md`` 15.6) und muss bis dahin ausdrücklich scheitern statt still
etwas Falsches zu rechnen.
"""

import math

import pytest

from core import development as dev

R = 2.5          # cm
LENGTH = 6.0     # cm


def cyl():
    return dev.cylinder(R, LENGTH)


# ------------------------------------------------------------ Abbildung

def test_touch_line_is_the_origin_of_the_development():
    assert cyl().to_plane(0.0, 0.0) == (0.0, 0.0)


def test_circumference_is_mapped_as_arc_length_not_chord():
    """Gemessen in Fusion: 20 mm Skizze werden 20,000 mm Bogenlänge."""
    d = cyl()
    x, _y = d.to_plane(math.radians(45.837), 0.0)
    assert x == pytest.approx(2.0, abs=1e-4)          # 20 mm
    chord = 2.0 * R * math.sin(math.radians(45.837) / 2.0)
    assert abs(x - chord) > 0.04                      # deutlich mehr als die Sehne


def test_period_is_the_circumference():
    assert cyl().period() == pytest.approx(2 * math.pi * R)


def test_bounds_span_one_full_wrap():
    x0, y0, x1, y1 = cyl().bounds()
    assert x1 - x0 == pytest.approx(2 * math.pi * R)
    assert y1 - y0 == pytest.approx(LENGTH)
    assert (x0, y0) == pytest.approx((-x1, -y1))


@pytest.mark.parametrize("theta,s", [(0.0, 0.0), (1.0, 2.0), (-2.5, -1.5)])
def test_mapping_is_an_isometry_along_both_axes(theta, s):
    """Abstände auf dem Zylinder = Abstände in der Abwicklung."""
    d = cyl()
    # umfangsparallel: Bogenlänge r*dtheta
    a = d.to_plane(theta, s)
    b = d.to_plane(theta + 0.3, s)
    assert math.dist(a, b) == pytest.approx(R * 0.3)
    # achsparallel: unverändert
    c = d.to_plane(theta, s + 1.7)
    assert math.dist(a, c) == pytest.approx(1.7)


# --------------------------------------------------------------- Entrollen

def test_unwrap_removes_the_jump_at_the_seam():
    raw = [3.0, 3.1, -3.1, -3.0]                  # laeuft ueber +-pi
    out = dev.unwrap_angles(raw)
    assert out[0] == pytest.approx(3.0)
    assert out[2] == pytest.approx(-3.1 + 2 * math.pi)
    for a, b in zip(out, out[1:]):
        assert abs(b - a) < 1.0


def test_unwrap_keeps_a_monotone_run_untouched():
    raw = [0.0, 0.5, 1.0, 1.5]
    assert dev.unwrap_angles(raw) == pytest.approx(raw)


def test_unwrap_handles_several_turns():
    raw = [t % (2 * math.pi) - math.pi for t in
           [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]]
    out = dev.unwrap_angles(raw)
    for a, b in zip(out, out[1:]):
        assert abs(b - a) < math.pi


def test_theta_coverage_and_periodicity():
    n = 64
    full = [(2 * math.pi * i / n - math.pi, 0.0) for i in range(n + 1)]
    assert dev.is_periodic(full)
    half = [(math.pi * i / n - math.pi / 2, 0.0) for i in range(n + 1)]
    assert not dev.is_periodic(half)
    assert dev.theta_coverage([p[0] for p in half]) == pytest.approx(math.pi)


# ------------------------------------------------------------- Konturen

def test_frame_points_unrolls_a_contour_crossing_the_seam():
    d = cyl()
    outline = [(math.pi - 0.1, -1.0), (math.pi - 0.05, -1.0),
               (-math.pi + 0.05, -1.0), (-math.pi + 0.1, -1.0)]
    points = d.frame_points(outline)
    xs = [p[0] for p in points]
    assert xs == sorted(xs), "die Kontur darf sich nicht zurückfalten"
    assert xs[-1] - xs[0] == pytest.approx(R * 0.2, abs=1e-9)


def test_obliquely_cut_cylinder_becomes_a_cosine():
    """Ein schräg geschnittener Zylinder ergibt in der Abwicklung eine
    Kosinuskurve - das ist die Probe aufs Exempel für die Isometrie."""
    d = cyl()
    tilt = 0.4
    n = 96
    outline = [(2 * math.pi * i / n - math.pi, R * math.tan(tilt) *
                math.cos(2 * math.pi * i / n - math.pi)) for i in range(n)]
    points = d.frame_points(outline)
    for x, y in points:
        assert y == pytest.approx(R * math.tan(tilt) * math.cos(x / R), abs=1e-9)
    xs = [p[0] for p in points]
    assert max(xs) - min(xs) == pytest.approx(2 * math.pi * R * (n - 1) / n)


def test_frame_points_of_an_empty_contour():
    assert cyl().frame_points([]) == []


# ------------------------------------------------------------------ Kegel

def test_the_cone_refuses_to_guess():
    """Solange die Messung fehlt, muss der Kegel scheitern - nicht raten."""
    cone = dev.Development(kind=dev.KIND_CONE, radius=R, half_angle=0.16,
                           length=LENGTH, periodic=True)
    with pytest.raises(NotImplementedError):
        cone.to_plane(0.0, 0.0)
    with pytest.raises(NotImplementedError):
        cone.period()


# ------------------------------------------------- Fläche -> Flächenkoordinaten

def test_the_reference_direction_is_deterministic_and_perpendicular():
    """Fusion nennt zu einer Zylinderfläche keine Null-Richtung.

    Sie wird aus der Achse gebaut - und muss für dieselbe Achse jedes Mal
    dieselbe sein, sonst zeigt der Nahtwinkel nach einem Neustart woandershin.
    """
    for axis in ((0, 0, 1), (1, 0, 0), (0, 1, 0), (1, 1, 1), (-2, 0.5, 3)):
        e1, e2 = dev.axis_frame(axis)
        assert dev.axis_frame(axis) == (e1, e2)
        unit = dev.normalized(axis)
        assert dev.dot3(e1, unit) == pytest.approx(0.0, abs=1e-12)
        assert dev.dot3(e2, unit) == pytest.approx(0.0, abs=1e-12)
        assert dev.dot3(e1, e2) == pytest.approx(0.0, abs=1e-12)
        assert dev.dot3(e1, e1) == pytest.approx(1.0)
        # Rechtshändig: e1 x e2 zeigt in Achsenrichtung
        assert dev.cross3(e1, e2) == pytest.approx(unit, abs=1e-12)


def test_the_z_axis_keeps_x_as_zero_direction():
    assert dev.axis_frame((0, 0, 1)) == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def test_world_points_become_angle_and_height():
    points = [(2.0, 0.0, 0.0), (0.0, 2.0, 1.5), (-2.0, 0.0, -3.0)]
    out = dev.surface_coords(points, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert [p[1] for p in out] == pytest.approx([0.0, 1.5, -3.0])
    assert [p[0] for p in out] == pytest.approx([0.0, math.pi / 2, math.pi])


def test_surface_coords_follow_a_tilted_axis():
    axis = (0.0, 1.0, 1.0)
    unit = dev.normalized(axis)
    e1, e2 = dev.axis_frame(axis)
    origin = (1.0, 2.0, 3.0)
    for s, theta in ((0.0, 0.0), (2.5, 1.0), (-1.0, -2.0)):
        p = tuple(origin[i] + s * unit[i]
                  + 3.0 * (math.cos(theta) * e1[i] + math.sin(theta) * e2[i])
                  for i in range(3))
        got = dev.surface_coords([p], origin, axis)[0]
        assert got[0] == pytest.approx(theta)
        assert got[1] == pytest.approx(s)


def test_a_slanted_cut_only_keeps_what_lies_on_the_face():
    """Der schräg abgeschnittene Zylinder läuft rundum, ist aber kein Rechteck."""
    assert dev.usable_span([(0.0, 0.0), (6.0, 6.0)]) == (0.0, 6.0)
    assert dev.usable_span([(0.0, 0.0), (5.0, 6.0)]) == (0.0, 5.0)
    assert dev.usable_span([(-0.5, 0.5), (5.0, 6.0)]) == (0.5, 5.0)
    # Beide Kurven auf derselben Seite, oder nur eine: kein brauchbares Stück
    assert dev.usable_span([(0.0, 0.0)]) is None
    assert dev.usable_span([(0.0, 3.0), (0.5, 3.5)]) is None


def test_describe_speaks_millimetres():
    assert dev.describe(
        {"kind": "cylinder", "radius": 2.5, "length": 6.0, "periodic": True}
    ) == "Zylinder r = 25 mm, L = 60 mm, rundum (nahtlos)"
    assert dev.describe(
        {"kind": "cylinder", "radius": 1.25, "length": 3.0, "periodic": False}
    ) == "Zylinder r = 12.5 mm, L = 30 mm, Teilfläche"
    assert dev.describe(None) == ""
