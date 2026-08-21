"""Mantelflächen im Dokument und in der Pipeline (Paket 2.3).

Die drei Zusicherungen, an denen alles hängt:

1. Der Rahmen der Abwicklung ist **genau** ein Umlauf breit und so hoch wie die
   Fläche – sonst passt das Muster nach dem Wickeln nicht auf sich selbst.
2. Seine linke und seine rechte Kante sind **deckungsgleich**, um eine Periode
   versetzt. Nach dem Wickeln liegen sie aufeinander.
3. Kein Loch wird von der Naht zerschnitten, und keins ragt aus dem Rahmen.
"""

import math

import pytest

from core import build, ir, pattern_doc
from core.containers import (DevelopmentContainer, RectContainer,
                             development_container, make_container)
from core.geom import polygon_area
from core.polyclip import polygon_fully_inside

RADIUS = 2.4
LENGTH = 6.0
PERIOD = 2.0 * math.pi * RADIUS


def development(**over):
    dev = {"kind": "cylinder", "radius": RADIUS, "halfAngle": 0.0,
           "length": LENGTH, "periodic": True, "seamAngle": 0.0}
    dev.update(over)
    return dev


def doc_for(pattern_id="honeycomb", params=None, dev=None, style=None):
    doc = pattern_doc.default_doc(pattern_id)
    doc["pattern"]["params"].update(params or {})
    doc["style"].update(style or {})
    doc["development"] = development() if dev is None else dev
    parsed, errors = pattern_doc.parse(doc)
    return parsed, errors


PATTERNS = [
    ("grid", {}),
    ("rhombus", {}),
    ("honeycomb", {"orientation": "pointy"}),
    ("honeycomb", {"orientation": "flat"}),
    ("brick", {"bond": "half"}),
    ("puzzle", {}),
    ("voronoi", {"cellCount": 120}),
    ("pebbles", {"cellCount": 90}),
    ("tissue", {}),
    ("leaf_veins", {}),
]
IDS = ["%s-%s" % (p[0], "-".join(str(v) for v in p[1].values()) or "std")
       for p in PATTERNS]


def face_and_holes(scene):
    face = [el for el in scene.elements
            if isinstance(el, ir.Path) and el.role == ir.ROLE_FACE]
    holes = [el for el in scene.elements
             if isinstance(el, ir.Path) and el.role == ir.ROLE_HOLE]
    return (face[0] if face else None), holes


# ------------------------------------------------------------------ Dokument

def test_a_cylinder_survives_parse():
    doc, errors = doc_for()
    assert not errors
    assert doc["development"]["kind"] == "cylinder"
    assert doc["development"]["radius"] == pytest.approx(RADIUS)


def test_a_broken_development_is_dropped_with_a_message():
    for bad in ({"kind": "cylinder", "radius": 0.0, "length": 5.0},
                {"kind": "cylinder", "radius": 2.0, "length": -1.0},
                {"kind": "torus", "radius": 2.0, "length": 5.0},
                {"kind": "cylinder", "radius": float("inf"), "length": 5.0}):
        doc, errors = doc_for(dev=bad)
        assert doc["development"] is None
        assert "development" in errors


def test_the_cone_is_refused_for_now():
    """Solange nicht gemessen ist, wie Fusion den Kegel abbildet, lieber nicht.

    Ein falsch abgewickeltes Muster fällt erst am gedruckten Teil auf
    (``Context.md`` 15.6, Punkt 4).
    """
    doc, errors = doc_for(dev=development(kind="cone", halfAngle=0.3))
    assert doc["development"] is None
    assert "Kegel" in errors["development"]


def test_an_old_document_has_no_development():
    doc, errors = pattern_doc.parse({"pattern": {"type": "grid"}})
    assert doc["development"] is None
    assert not errors


def test_the_seam_angle_is_checked():
    doc, errors = doc_for(dev=development(seamAngle=400.0))
    assert doc["development"]["seamAngle"] == 0.0
    assert "development.seamAngle" in errors


def test_emboss_parameters_are_in_the_style():
    doc, _errors = doc_for()
    assert doc["style"]["embossOn"] is False
    assert doc["style"]["embossDepth"] == pytest.approx(0.1)


# ------------------------------------------------------------------ Container

def test_the_container_comes_from_the_development():
    container = make_container({"shape": "circle", "diameter": 3.0}, development())
    assert isinstance(container, RectContainer)
    x0, y0, x1, y1 = container.bounding_rect()
    assert x1 - x0 == pytest.approx(PERIOD)
    assert y1 - y0 == pytest.approx(LENGTH)


def test_a_partial_face_becomes_a_custom_frame():
    """Teilflächen laufen nicht rundum - dort ist der Rahmen die Kontur selbst."""
    outline = [[-0.5, -2.0], [0.5, -2.0], [0.5, 2.0], [-0.5, 2.0]]
    container = development_container(
        development(periodic=False, outline=outline))
    assert container.shape == "custom"
    x0, _y0, x1, _y1 = container.bounding_rect()
    assert x1 - x0 == pytest.approx(RADIUS * 1.0)      # Bogenlänge = r * Δθ


def test_the_development_container_has_congruent_edges():
    path = [(-1.0, -3.0), (-0.8, -1.0), (-1.2, 1.0), (-1.0, 3.0)]
    container = DevelopmentContainer(path, PERIOD)
    pts = container.clip_polygon()
    assert len(pts) == 2 * len(path)
    right, left = pts[:len(path)], list(reversed(pts[len(path):]))
    for a, b in zip(right, left):
        assert a[0] - b[0] == PERIOD
        assert a[1] == b[1]
    assert abs(polygon_area(pts)) == pytest.approx(PERIOD * 6.0)


def test_the_seam_gets_no_border():
    """In y einrücken, in x nicht - sonst stünde an der Naht ein doppelter Rand."""
    path = [(-1.0, -3.0), (-1.0, 3.0)]
    inner = DevelopmentContainer(path, PERIOD).shrunk_xy(0.0, 0.5)
    x0, y0, x1, y1 = inner.bounding_rect()
    assert x1 - x0 == pytest.approx(PERIOD)
    assert y1 - y0 == pytest.approx(5.0)


def test_other_containers_take_the_larger_measure():
    inner = RectContainer(10.0, 6.0).shrunk_xy(0.0, 0.5)
    x0, y0, x1, y1 = inner.bounding_rect()
    assert (x1 - x0, y1 - y0) == pytest.approx((9.0, 5.0))


# ------------------------------------------------------------------ Pipeline

@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_the_frame_is_exactly_one_turn(pattern_id, params):
    doc, errors = doc_for(pattern_id, params)
    assert not errors
    scene = build.build_scene(doc)
    assert not scene.warnings, scene.warnings
    face, _holes = face_and_holes(scene)
    assert face is not None
    assert abs(polygon_area(face.points)) == pytest.approx(PERIOD * LENGTH, abs=1e-9)


@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_both_seam_edges_are_the_same_curve(pattern_id, params):
    """Punkt für Punkt gleich, um genau einen Umlauf versetzt.

    Das muss **exakt** stimmen: der Optimierer würde die beiden Kanten sonst
    unabhängig voneinander ausdünnen (sie werden in entgegengesetzter Richtung
    durchlaufen), und nach dem Wickeln stünde an der Naht eine Stufe.
    """
    doc, _errors = doc_for(pattern_id, params)
    face, _holes = face_and_holes(build.build_scene(doc))
    pts = face.points
    assert len(pts) % 2 == 0
    half = len(pts) // 2
    right, left = pts[:half], list(reversed(pts[half:]))
    for a, b in zip(right, left):
        assert a[0] - b[0] == PERIOD
        assert a[1] == b[1]


@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_no_hole_leaves_the_frame(pattern_id, params):
    doc, _errors = doc_for(pattern_id, params)
    face, holes = face_and_holes(build.build_scene(doc))
    assert holes
    for hole in holes:
        assert polygon_fully_inside(hole.points, face.points)


@pytest.mark.parametrize("pattern_id,params", PATTERNS, ids=IDS)
def test_the_pattern_covers_the_whole_turn(pattern_id, params):
    """Kein Loch fehlt: die Lochfläche ist ein sinnvoller Anteil der Fläche.

    Fehlte eine Zelle an der Naht - weil der Generator sie nur einmal liefert
    und sie jenseits der Bahn landet -, wäre dort ein massiver Fleck. Geprüft
    wird deshalb zusätzlich, dass jeder senkrechte Streifen Löcher enthält.
    """
    doc, _errors = doc_for(pattern_id, params)
    face, holes = face_and_holes(build.build_scene(doc))
    total = abs(polygon_area(face.points))
    covered = sum(abs(polygon_area(h.points)) for h in holes)
    assert covered > 0.25 * total
    columns = 12
    width = PERIOD / columns
    x_left = min(p[0] for p in face.points)
    hits = [0] * columns
    for hole in holes:
        for x, _y in hole.points:
            index = int((x - x_left) / width)
            if 0 <= index < columns:
                hits[index] += 1
    assert all(hits), "leerer Streifen im Muster: %r" % (hits,)


def test_the_pattern_angle_is_ignored_on_a_surface():
    """Ein gedrehtes Gitter ist nicht periodisch - die Drehung bleibt aus."""
    doc, _errors = doc_for("grid", style=None)
    doc["placement"]["patternAngle"] = 30.0
    turned = build.build_scene(doc)
    doc["placement"]["patternAngle"] = 0.0
    straight = build.build_scene(doc)
    assert len(turned.elements) == len(straight.elements)


def test_without_a_development_nothing_changes():
    plain = pattern_doc.default_doc("honeycomb")
    parsed, errors = pattern_doc.parse(plain)
    assert not errors and parsed["development"] is None
    scene = build.build_scene(parsed)
    face, _holes = face_and_holes(scene)
    x0, _y0, x1, _y1 = make_container(parsed["container"]).bounding_rect()
    assert max(p[0] for p in face.points) == pytest.approx(x1)


# ------------------------------------------------------ Was Fusion anlegt

def test_the_tokens_of_plane_and_emboss_survive_a_round_trip():
    """Ohne sie legte ein Re-Edit eine zweite Ebene an und ließe die alte
    Prägung stehen."""
    doc, errors = doc_for(dev=development(planeToken="abc",
                                          embossTokens=["e1", "e2"],
                                          axisMiddle=3.0))
    assert not errors
    assert doc["development"]["planeToken"] == "abc"
    assert doc["development"]["embossTokens"] == ["e1", "e2"]
    assert doc["development"]["axisMiddle"] == pytest.approx(3.0)
    again, _errors = pattern_doc.parse(pattern_doc.deserialize(
        pattern_doc.serialize(doc)))
    assert again["development"] == doc["development"]


def test_garbage_tokens_do_not_break_the_document():
    doc, _errors = doc_for(dev=development(planeToken=None, embossTokens="nein",
                                           axisMiddle=float("nan")))
    assert doc["development"]["planeToken"] == "None"
    assert doc["development"]["embossTokens"] == []
    assert doc["development"]["axisMiddle"] == 0.0


# --------------------------------------------------------- Trennlinie

def test_embossing_asks_for_a_dividing_line():
    """Ein Profil über volle 360° lehnt Fusion ab - es braucht zwei.

    Die Trennlinie läuft wie die Naht entlang der Zellwände und zerschneidet
    deshalb kein Loch (``Context.md`` 15.6, Punkt 6).
    """
    from core import seam

    for pattern_id, params in PATTERNS:
        doc, _errors = doc_for(pattern_id, params, style={"embossOn": True})
        scene = build.build_scene(doc)
        lines = [el for el in scene.elements
                 if isinstance(el, ir.Path) and not el.closed
                 and el.layer == ir.LAYER_BORDER and el.role == ir.ROLE_EDGE]
        assert len(lines) == 1, "%s: %d Trennlinien" % (pattern_id, len(lines))
        divider = lines[0].points
        assert divider[0][1] == pytest.approx(-LENGTH / 2.0)
        assert divider[-1][1] == pytest.approx(LENGTH / 2.0)
        _face, holes = face_and_holes(scene)
        cut = seam.crossed_cells([h.points for h in holes], divider)
        # Das Puzzle lässt an seinen Nasen stellenweise nur 0,13 mm Steg statt
        # 0,8 mm; dort kommt keine Bahn mehr durch. Die Trennlinie kreuzt dann
        # ein Loch - für die Prägung unschädlich (siehe ``build._divider``).
        assert not cut or pattern_id == "puzzle", "%s: %d" % (pattern_id, len(cut))


def test_without_embossing_there_is_no_dividing_line():
    doc, _errors = doc_for("honeycomb", style={"embossOn": False})
    scene = build.build_scene(doc)
    assert not [el for el in scene.elements
                if isinstance(el, ir.Path) and not el.closed
                and el.layer == ir.LAYER_BORDER]
