"""Verbinder: aus einer Wolke frei stehender Motive wird **ein** druckbares Teil.

Der Kern dieser Datei ist ``bodies()`` - eine vom Produktivcode **unabhängige**
Zusammenhangsprüfung. Sie modelliert, was beim Extrudieren zu einem Körper
verschmilzt, und beantwortet damit die einzige Frage, auf die es ankommt:
Bleibt am Ende genau ein Teil übrig?
"""

import math

import pytest

import generators
from core import ir
from core import pattern_doc as pd
from core.build import build_scene, _circle_to_points
from core.connect import connector_areas, islands, outlines
from core.containers import make_container
from core.geom import _segments_cross, point_in_polygon

SCATTER_IDS = [pid for pid, cls in generators.REGISTRY.items() if cls.scatter]
OTHER_IDS = [pid for pid, cls in generators.REGISTRY.items() if not cls.scatter]

#: Stil-Varianten, in denen Streu-Muster lose Inseln erzeugen
STYLE_CASES = [
    {},
    {"fillTarget": "cells"},
    {"clip": "off"},
    {"clip": "dropPartial"},
    {"hatch": True},
    {"borderWidth": 0.6},
]


def doc_for(pattern_id, **style):
    doc = pd.default_doc(pattern_id)
    doc["seed"] = 42
    doc["style"].update(style)
    return doc


# ------------------------------------------- unabhängige Zusammenhangsprüfung

def polygons(elements, layer=ir.LAYER_PATTERN):
    out = []
    for el in elements:
        if getattr(el, "layer", "") != layer or getattr(el, "role", "") == ir.ROLE_DECOR:
            continue
        if isinstance(el, ir.Circle):
            out.append(_circle_to_points(el, 32))
        elif isinstance(el, ir.Path) and el.closed and len(el.points) >= 3:
            out.append(list(el.points))
    return out


def touches(a, b):
    """Verschmelzen diese beiden Profile beim Extrudieren?

    Ja, wenn sich die Konturen schneiden (überlappende Flächen) oder eine in
    der anderen liegt (Kreisring aus Außen- und Innenkontur).
    """
    na, nb = len(a), len(b)
    for i in range(na):
        p, q = a[i], a[(i + 1) % na]
        for j in range(nb):
            if _segments_cross(p, q, b[j], b[(j + 1) % nb]) is not None:
                return True
    return point_in_polygon(_inside(a), b) or point_in_polygon(_inside(b), a)


def _inside(poly):
    """Punkt sicher innerhalb - ein Eckpunkt kann auf der Nachbarkontur liegen."""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        p = ((a[0] + b[0]) / 2.0 * 0.999 + cx * 0.001,
             (a[1] + b[1]) / 2.0 * 0.999 + cy * 0.001)
        if point_in_polygon(p, poly):
            return p
    return (cx, cy)


def bodies(elements):
    """Zahl der Körper, die aus den Musterprofilen entstehen."""
    polys = polygons(elements)
    n = len(polys)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    boxes = [(min(x for x, _ in p), min(y for _, y in p),
              max(x for x, _ in p), max(y for _, y in p)) for p in polys]
    for i in range(n):
        for j in range(i + 1, n):
            if find(i) == find(j):
                continue
            bi, bj = boxes[i], boxes[j]
            if bi[2] < bj[0] or bj[2] < bi[0] or bi[3] < bj[1] or bj[3] < bi[1]:
                continue
            if touches(polys[i], polys[j]):
                parent[find(i)] = find(j)
    return len(set(find(i) for i in range(n)))


def test_the_check_itself_is_sound():
    """Zwei getrennte Quadrate sind zwei Körper, zwei überlappende einer."""
    def square(x):
        return ir.Path(points=[(x, 0), (x + 1, 0), (x + 1, 1), (x, 1)], closed=True,
                       role=ir.ROLE_REGION)
    assert bodies([square(0), square(5)]) == 2
    assert bodies([square(0), square(0.5)]) == 1
    # Kreisring: Innenkontur liegt in der Außenkontur -> ein Körper
    ring = [ir.Circle((0.0, 0.0), 1.0, role=ir.ROLE_REGION),
            ir.Circle((0.0, 0.0), 0.9, role=ir.ROLE_REGION)]
    assert bodies(ring) == 1


# ---------------------------------------------------- 1./2. Ein Körper

@pytest.mark.parametrize("pattern_id", SCATTER_IDS)
def test_scatter_patterns_fall_apart_without_connectors(pattern_id):
    """Ohne Verbinder ist das Muster nicht druckbar - das ist der Ausgangspunkt."""
    assert bodies(build_scene(doc_for(pattern_id, connectors=False)).elements) > 1


@pytest.mark.parametrize("pattern_id", SCATTER_IDS)
def test_connectors_leave_exactly_one_body(pattern_id):
    for style in STYLE_CASES:
        scene = build_scene(doc_for(pattern_id, connectors=True, **style))
        assert bodies(scene.elements) == 1, "%s %s" % (pattern_id, style)


@pytest.mark.parametrize("pattern_id", SCATTER_IDS)
def test_one_body_survives_the_optimizer(pattern_id):
    """Der Optimierer läuft nach den Verbindern - er darf sie nicht abhängen."""
    from unittest import mock
    import core.build as build
    doc = doc_for(pattern_id, connectors=True)
    with mock.patch.object(build, "optimize", lambda els: list(els)):
        raw = build_scene(doc)
    assert bodies(raw.elements) == bodies(build_scene(doc).elements) == 1


# ------------------------------------------------- 5. Rahmen-Verankerung

def inner_frame(doc):
    container = make_container(doc["container"])
    return container.shrunk(float(doc["style"]["borderWidth"])).clip_polygon()


def crossings_of_the_frame(scene, frame):
    """Wie viele Musterprofile laufen in das Rahmenband hinein?"""
    n = len(frame)
    count = 0
    for poly in polygons(scene.elements):
        m = len(poly)
        hit = any(_segments_cross(poly[i], poly[(i + 1) % m],
                                  frame[j], frame[(j + 1) % n]) is not None
                  for i in range(m) for j in range(n))
        if hit:
            count += 1
    return count


@pytest.mark.parametrize("pattern_id", SCATTER_IDS)
def test_the_pattern_is_anchored_in_the_frame(pattern_id):
    """Sonst hängt das Muster zwar zusammen, schwebt aber im Rahmen."""
    doc = doc_for(pattern_id, connectors=True)
    scene = build_scene(doc)
    assert crossings_of_the_frame(scene, inner_frame(doc)) >= 2


@pytest.mark.parametrize("pattern_id", SCATTER_IDS)
def test_without_a_frame_the_user_is_warned(pattern_id):
    scene = build_scene(doc_for(pattern_id, connectors=True, border=False))
    assert bodies(scene.elements) == 1
    assert any("lose" in w for w in scene.warnings), scene.warnings


# ------------------------------------------------------ 3. Regressionsschutz

@pytest.mark.parametrize("pattern_id", SCATTER_IDS)
def test_switching_connectors_off_restores_the_old_scene(pattern_id):
    """Verbinder aus ⇒ exakt der Stand von vorher."""
    doc = doc_for(pattern_id, connectors=False)
    scene = build_scene(doc)
    del doc["style"]["connectors"]                 # so sah das Doc vorher aus
    assert build_scene(doc).to_dict() == scene.to_dict()


@pytest.mark.parametrize("pattern_id", OTHER_IDS)
def test_non_scatter_patterns_are_untouched(pattern_id):
    """Kachel- und Strich-Muster bekommen keine Stege - auch nicht mit Haken."""
    on = build_scene(doc_for(pattern_id, connectors=True))
    off = build_scene(doc_for(pattern_id, connectors=False))
    assert on.to_dict() == off.to_dict()


def test_only_scatter_generators_are_flagged():
    assert set(SCATTER_IDS) == {"phyllotaxis", "motif_scatter"}


def test_the_flag_reaches_the_editor_schema():
    """Ohne das Flag im Schema kann die Palette die Felder nicht ausblenden."""
    schema = {s["id"]: s for s in generators.registry_schema()}
    assert schema["phyllotaxis"]["scatter"] is True
    assert schema["grid"]["scatter"] is False


# --------------------------------------------------------- 4. Determinismus

@pytest.mark.parametrize("pattern_id", SCATTER_IDS)
def test_two_builds_produce_identical_connectors(pattern_id):
    doc = doc_for(pattern_id, connectors=True)
    assert build_scene(doc).to_dict() == build_scene(doc).to_dict()


def test_the_spanning_tree_does_not_depend_on_input_order():
    """Prim startet bei Insel 0 - die Inselreihenfolge muss stabil sein."""
    doc = doc_for("phyllotaxis", connectors=True)
    first = build_scene(doc).to_dict()
    doc["seed"] = 42
    assert build_scene(doc).to_dict() == first


# ------------------------------------------------------------ 6. Stegbreite

def strip_width(poly):
    """Kürzeste Seite eines Steg-Rechtecks."""
    n = len(poly)
    return min(math.dist(poly[i], poly[(i + 1) % n]) for i in range(n))


@pytest.mark.parametrize("width", [0.04, 0.08, 0.2])
def test_connector_width_is_what_was_asked_for(width):
    doc = doc_for("phyllotaxis", connectors=True, connectorWidth=width)
    stegs = [el.points for el in build_scene(doc).elements
             if isinstance(el, ir.Path) and el.closed and len(el.points) == 4]
    assert stegs, "keine Stege gefunden"
    widths = sorted(strip_width(s) for s in stegs)
    assert widths[len(widths) // 2] == pytest.approx(width, abs=1e-6)


# ---------------------------------------------- 7. Beschnitt und Sonderfälle

def test_clipped_motifs_do_not_leave_orphans():
    """Ein am Rand zerschnittenes Motiv darf kein loses Teilstück hinterlassen."""
    doc = doc_for("phyllotaxis", connectors=True)
    doc["pattern"]["params"].update({"count": 400, "scale": 0.35})
    assert bodies(build_scene(doc).elements) == 1


def test_connectors_stay_inside_the_container():
    doc = doc_for("phyllotaxis", connectors=True)
    poly = make_container(doc["container"]).clip_polygon()
    for el in build_scene(doc).elements:
        if isinstance(el, ir.Path) and el.closed and len(el.points) == 4:
            for p in el.points:
                assert point_in_polygon(p, poly) or _on_boundary(p, poly)


def _on_boundary(p, poly, tol=1e-6):
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ll = dx * dx + dy * dy
        t = 0.0 if ll < 1e-24 else max(0.0, min(1.0, ((p[0] - a[0]) * dx
                                                      + (p[1] - a[1]) * dy) / ll))
        if math.dist(p, (a[0] + dx * t, a[1] + dy * t)) <= tol:
            return True
    return False


def test_line_mode_has_no_connectors():
    """Im Linienmodus wird nichts extrudiert - Stege wären sinnlos."""
    on = build_scene(doc_for("phyllotaxis", mode="lines", connectors=True))
    off = build_scene(doc_for("phyllotaxis", mode="lines", connectors=False))
    assert on.to_dict() == off.to_dict()


# ------------------------------------------------------- Bausteine einzeln

def test_islands_sees_a_ring_as_one_island():
    ring = [ir.Circle((0.0, 0.0), 1.0, role=ir.ROLE_REGION),
            ir.Circle((0.0, 0.0), 0.9, role=ir.ROLE_REGION)]
    assert len(islands(ring)) == 1


def test_islands_ignores_border_and_text():
    frame = ir.Path(points=[(-5, -5), (5, -5), (5, 5), (-5, 5)], closed=True,
                    layer=ir.LAYER_BORDER, role=ir.ROLE_EDGE)
    motif = ir.Circle((0.0, 0.0), 0.2, role=ir.ROLE_REGION)
    assert len(outlines([frame, motif])) == 1
    assert len(islands([frame, motif])) == 1


def test_a_single_island_without_a_frame_needs_no_connector():
    motif = ir.Circle((0.0, 0.0), 0.2, role=ir.ROLE_REGION)
    paths, warnings = connector_areas([motif], None, width=0.08, reach=0.04)
    assert paths == [] and warnings == []


def test_the_spanning_tree_is_minimal():
    """k Inseln brauchen k-1 Stege - mehr wäre Materialverschwendung."""
    motifs = [ir.Circle((float(i), 0.0), 0.2, role=ir.ROLE_REGION) for i in range(6)]
    paths, _ = connector_areas(motifs, None, width=0.08, reach=0.04)
    assert len(paths) == 5
