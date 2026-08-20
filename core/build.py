"""Die zentrale Pipeline: PatternDoc -> IR-Szene.

Ablauf (identisch fuer Editor-Vorschau und Fusion-Commit, deshalb koennen beide
nicht auseinanderlaufen):

1. Container aus dem Doc bauen (lokale Koordinaten, Mittelpunkt 0/0)
2. Generator fuellt das - bei Musterdrehung vergroesserte - Bounding-Rechteck
3. Musterdrehung anwenden
4. Clipping gegen die Containerform (``cut`` / ``dropPartial`` / ``off``)
5. Text-Knockout
6. Stilisierung: Linien- oder Flaechenmodus (Stroker / Inset)
   6a. Optionale Schraffur der freien Zellflaechen
7. Containerumriss ergaenzen
8. Platzierung (Ursprung + Rahmendrehung) anwenden
"""

from __future__ import annotations

import math
import random
from typing import Any, List, Optional, Sequence, Tuple

from . import ir
from .containers import Container, make_container
from .geom import (chain_segments, clean_polygon, ensure_ccw, erode_convex,
                   is_convex, polygon_area, polygon_segments, polyline_length,
                   rotate, snap_segments)
from .hatch import hatch_areas, style_from_doc
from .stroker import offset_polyline, stroke

Point = Tuple[float, float]

#: Ab dieser Elementzahl warnt die Vorschau und zeichnet vereinfacht
PREVIEW_WARN_LIMIT = 5000
#: Ab dieser Entity-Zahl warnt der Commit (mit Abbruch-Option)
ENTITY_WARN_LIMIT = 2000


def build_scene(doc: dict, container: Optional[Container] = None) -> ir.Scene:
    """PatternDoc -> fertige IR-Szene (in Skizzenkoordinaten, cm)."""
    from generators import GenContext, get_generator

    container = container or make_container(doc["container"])
    style = doc["style"]
    placement = doc["placement"]
    warnings: List[str] = []

    pattern_angle = math.radians(float(placement.get("patternAngle", 0.0)))
    bbox = _generation_bbox(container, pattern_angle)

    gen = get_generator(doc["pattern"]["type"])
    ctx = GenContext(
        bbox=bbox,
        rnd=random.Random(int(doc.get("seed", 0))),
        thickness=float(style.get("thickness", 0.08)),
        fill_target=str(style.get("fillTarget", "webs")),
        mode=str(style.get("mode", "area")),
    )
    elements = list(gen.generate(dict(doc["pattern"]["params"]), ctx))

    if abs(pattern_angle) > 1e-12:
        elements = [_rotate_element(el, pattern_angle) for el in elements]

    fill_target = str(style.get("fillTarget", "webs"))
    if fill_target not in getattr(gen, "fill_targets", ("webs",)):
        fill_target = getattr(gen, "fill_targets", ("webs",))[0]

    mode = str(style.get("mode", "area"))
    clip_mode = str(style.get("clip", "cut"))
    thickness = float(style.get("thickness", 0.08))
    border_on = bool(style.get("border"))
    border_width = float(style.get("borderWidth", 0.0)) if border_on else 0.0
    own_gap = gen.gap(doc["pattern"]["params"])
    # Die Schraffur bekommt einen eigenen Zufallsstrom: sie darf das Muster
    # selbst nicht veraendern, wenn man sie ein- oder ausschaltet.
    hatch_style = style_from_doc(style)
    hatch_rnd = random.Random(int(doc.get("seed", 0)) + 7919)

    # Stegnetz eines kachelnden Musters ist exakt "Rahmen minus verkleinerte
    # Zellen" - das ergibt EINE zusammenhaengende, dichte Flaeche statt vieler
    # sich ueberlappender Streifen (klickbar in einem Zug, 3D-druckbar).
    # Bedingung ist ein gezeichneter Rahmen: er ist die Aussenkontur dieser
    # Flaeche. Ohne Rahmen bleibt es beim Stroken der einzelnen Stegketten -
    # dann enden die Stege offen am Rand (fuer Gravuren gewollt).
    as_face = (mode == "area" and fill_target == "webs" and border_on
               and bool(getattr(gen, "tiling", False)) and clip_mode != "off")

    # Der Rand wird nach innen gemessen: das Muster endet ``border_width`` vor der
    # Aussenkante, ein halber Steg davon entsteht ohnehin durch das Verkleinern.
    clip_container = container
    if as_face:
        inset = max(0.0, border_width - thickness / 2.0)
        if inset > 1e-9:
            clip_container = container.shrunk(inset)

    elements = _clip_elements(elements, clip_container, clip_mode)

    if as_face:
        elements = _drop_regions_in_text(elements, doc, thickness)
        elements = _to_face(elements, container, thickness, own_gap=own_gap,
                            hole_limit=container.shrunk(border_width))
        if hatch_style is not None:
            # Die Loecher SIND die freien Flaechen - inklusive Randbeschnitt und
            # Splitterfilter. Deshalb hier schraffieren und nicht vorher.
            holes = [el.points for el in elements
                     if isinstance(el, ir.Path) and el.role == ir.ROLE_HOLE]
            strips, hatch_warnings = hatch_areas(
                holes, hatch_style, hatch_rnd,
                web_half=max(thickness, own_gap) / 2.0)
            elements.extend(strips)
            warnings.extend(hatch_warnings)
        elements = _knockout_sweep(elements, doc)
    else:
        elements = _apply_text_knockout(elements, doc, style)
        if mode == "area":
            # Ohne Flaechenmodell wird das Stegnetz gestrokt: frei bleibt jede
            # Zelle, um eine halbe Stegdicke verkleinert.
            strips: List[Any] = []
            if hatch_style is not None:
                free = [poly for poly in
                        (_shrink_cell(el.points, thickness / 2.0) for el in elements
                         if isinstance(el, ir.Path) and el.closed
                         and el.role == ir.ROLE_REGION)
                        if poly and len(poly) >= 3]
                strips, hatch_warnings = hatch_areas(
                    free, hatch_style, hatch_rnd, web_half=thickness / 2.0)
                warnings.extend(hatch_warnings)
            elements = _to_areas(elements, thickness=thickness,
                                 fill_target=fill_target, own_gap=bool(gen.own_gap))
            elements.extend(strips)
            elements = _knockout_sweep(elements, doc)
        if border_on:
            elements = list(container.outline()) + elements

    from text.text_layer import text_elements
    for layer in doc.get("textLayers", []):
        elements.extend(text_elements(layer))

    origin = (float(placement.get("originX", 0.0)), float(placement.get("originY", 0.0)))
    frame_angle = math.radians(float(placement.get("rotation", 0.0)))
    if abs(frame_angle) > 1e-12 or origin != (0.0, 0.0):
        elements = [_place_element(el, frame_angle, origin) for el in elements]

    scene = ir.Scene(elements=elements, warnings=warnings)
    n = scene.counts()["contours"]
    if n > PREVIEW_WARN_LIMIT:
        warnings.append("Sehr viele Elemente (%d) – Erzeugen kann dauern." % n)
    return scene


# --------------------------------------------------------------- Teilschritte

def _generation_bbox(container: Container, pattern_angle: float
                     ) -> Tuple[float, float, float, float]:
    x0, y0, x1, y1 = container.bounding_rect()
    if abs(pattern_angle) < 1e-12:
        return (x0, y0, x1, y1)
    r = 0.5 * math.hypot(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return (cx - r, cy - r, cx + r, cy + r)


def _map_points(el: Any, fn) -> Any:
    if isinstance(el, ir.Path):
        return ir.Path(points=[fn(p) for p in el.points], closed=el.closed,
                       curve=el.curve, role=el.role, layer=el.layer, widths=el.widths)
    if isinstance(el, ir.Circle):
        return ir.Circle(center=fn(el.center), radius=el.radius, role=el.role,
                         layer=el.layer)
    if isinstance(el, ir.Ellipse):
        return ir.Ellipse(center=fn(el.center), rx=el.rx, ry=el.ry,
                          rotation=el.rotation, role=el.role, layer=el.layer)
    if isinstance(el, ir.Arc):
        return ir.Arc(center=fn(el.center), radius=el.radius, a0=el.a0, a1=el.a1,
                      role=el.role, layer=el.layer)
    if isinstance(el, ir.TextItem):
        p = fn((el.x, el.y))
        return ir.TextItem(text=el.text, x=p[0], y=p[1], height=el.height,
                           angle=el.angle, font=el.font, layer=el.layer, role=el.role)
    return el


def _rotate_element(el: Any, angle: float) -> Any:
    out = _map_points(el, lambda p: rotate(p, angle))
    if isinstance(out, ir.Arc):
        out.a0 += angle
        out.a1 += angle
    elif isinstance(out, ir.Ellipse):
        out.rotation += angle
    elif isinstance(out, ir.TextItem):
        out.angle += angle
    return out


def _place_element(el: Any, angle: float, origin: Point) -> Any:
    out = _rotate_element(el, angle) if abs(angle) > 1e-12 else _map_points(el, lambda p: p)
    return _map_points(out, lambda p: (p[0] + origin[0], p[1] + origin[1]))


def _arc_to_points(el: ir.Arc, segments: int = 24) -> List[Point]:
    return [(el.center[0] + el.radius * math.cos(el.a0 + (el.a1 - el.a0) * i / segments),
             el.center[1] + el.radius * math.sin(el.a0 + (el.a1 - el.a0) * i / segments))
            for i in range(segments + 1)]


def _circle_to_points(el: ir.Circle, segments: int = 48) -> List[Point]:
    return [(el.center[0] + el.radius * math.cos(2 * math.pi * i / segments),
             el.center[1] + el.radius * math.sin(2 * math.pi * i / segments))
            for i in range(segments)]


def _clip_elements(elements: Sequence[Any], container: Container, mode: str) -> List[Any]:
    if mode == "off":
        return list(elements)
    out: List[Any] = []
    for el in elements:
        if isinstance(el, ir.Path):
            if mode == "dropPartial":
                if container.fully_inside(el.points):
                    out.append(el)
                continue
            for piece in container.clip_path(el.points, el.closed):
                if len(piece) < 2:
                    continue
                out.append(ir.Path(points=piece, closed=el.closed, curve=el.curve,
                                   role=el.role, layer=el.layer,
                                   widths=_resized_widths(el, piece)))
        elif isinstance(el, ir.Circle):
            pts = _circle_to_points(el)
            if container.fully_inside(pts):
                out.append(el)
            elif mode == "cut":
                for piece in container.clip_path(pts, True):
                    if len(piece) >= 3:
                        out.append(ir.Path(points=piece, closed=True, role=el.role,
                                           layer=el.layer))
        elif isinstance(el, ir.Arc):
            pts = _arc_to_points(el)
            if container.fully_inside(pts):
                out.append(el)
            elif mode == "cut":
                for piece in container.clip_path(pts, False):
                    if len(piece) >= 2:
                        out.append(ir.Path(points=piece, closed=False, curve="spline",
                                           role=el.role, layer=el.layer))
        else:
            out.append(el)
    return out


def _resized_widths(el: ir.Path, piece: Sequence[Point]) -> Optional[List[float]]:
    if el.widths is None:
        return None
    avg = sum(el.widths) / float(len(el.widths))
    return [avg] * len(piece)


def _apply_text_knockout(elements: Sequence[Any], doc: dict, style: dict) -> List[Any]:
    """Knockout anwenden.

    Im Flaechenmodus wird die Box zusaetzlich um die halbe (groesste) Stegdicke
    vergroessert - sonst schoebe der Stroker die verbreiterten Streifen wieder
    in den Textbereich hinein.
    """
    from text.text_layer import apply_knockout, text_box
    extra = 0.0
    if str(style.get("mode", "area")) == "area":
        widest = float(style.get("thickness", 0.08))
        for el in elements:
            if isinstance(el, ir.Path) and el.widths:
                widest = max(widest, max(el.widths))
        extra = widest / 2.0
    boxes = []
    for layer in doc.get("textLayers", []):
        if layer.get("enabled") and layer.get("knockout"):
            box = text_box(layer, margin=float(layer.get("knockoutMargin", 0.0)) + extra)
            if box:
                boxes.append(box)
    return apply_knockout(elements, boxes) if boxes else list(elements)


def _knockout_sweep(elements: Sequence[Any], doc: dict) -> List[Any]:
    """Nachkontrolle nach dem Stroken.

    Gehrungsspitzen koennen einen Streifen minimal ueber die vorab gestanzte
    Zone hinausschieben. Was danach noch die eigentliche Text-Box beruehrt,
    faellt hier weg - so ist der Textbereich garantiert frei.
    """
    from core.clip import polygon_intersects
    from text.text_layer import text_box
    boxes = [text_box(layer) for layer in doc.get("textLayers", [])
             if layer.get("enabled") and layer.get("knockout")]
    boxes = [b for b in boxes if b]
    if not boxes:
        return list(elements)
    out: List[Any] = []
    for el in elements:
        if isinstance(el, ir.Path) and el.layer == ir.LAYER_PATTERN and el.closed:
            if any(polygon_intersects(el.points, box) for box in boxes):
                continue
        elif isinstance(el, ir.Circle) and el.layer == ir.LAYER_PATTERN:
            poly = _circle_to_points(el, 24)
            if any(polygon_intersects(poly, box) for box in boxes):
                continue
        out.append(el)
    return out


def _to_areas(elements: Sequence[Any], thickness: float, fill_target: str,
              own_gap: bool) -> List[Any]:
    """Flaechenmodus: alles wird zu geschlossenen, extrudierbaren Profilen."""
    out: List[Any] = []
    region_segments: List[Tuple[Point, Point]] = []

    for el in elements:
        if isinstance(el, ir.Path) and el.role == ir.ROLE_REGION and el.closed:
            if fill_target == "cells":
                poly = (list(el.points) if own_gap
                        else _shrink_cell(el.points, thickness / 2.0))
                if poly and len(poly) >= 3:
                    out.append(ir.Path(points=list(poly), closed=True, curve=el.curve,
                                       role=ir.ROLE_REGION, layer=el.layer))
            else:
                region_segments.extend(polygon_segments(el.points))
        elif isinstance(el, ir.Circle) and el.role == ir.ROLE_REGION:
            if fill_target == "cells":
                r = el.radius if own_gap else el.radius - thickness / 2.0
                if r > 1e-4:
                    out.append(ir.Circle(el.center, r, role=ir.ROLE_REGION, layer=el.layer))
            else:
                out.append(ir.Circle(el.center, el.radius + thickness / 2.0,
                                     role=ir.ROLE_REGION, layer=el.layer))
                if el.radius - thickness / 2.0 > 1e-4:
                    out.append(ir.Circle(el.center, el.radius - thickness / 2.0,
                                         role=ir.ROLE_REGION, layer=el.layer))
        elif isinstance(el, ir.Path) and el.role == ir.ROLE_EDGE:
            widths = el.widths if el.widths is not None else thickness
            for ring in stroke(el.points, el.closed, widths):
                out.append(ir.Path(points=ring, closed=True, curve="line",
                                   role=ir.ROLE_REGION, layer=el.layer))
        elif isinstance(el, ir.Arc):
            for ring in stroke(_arc_to_points(el), False, thickness):
                out.append(ir.Path(points=ring, closed=True, curve="line",
                                   role=ir.ROLE_REGION, layer=el.layer))
        else:
            out.append(el)

    # Stege: gemeinsame Zellkanten deduplizieren, verketten und dann stroken.
    if region_segments:
        for pts, closed in chain_segments(snap_segments(region_segments)):
            for ring in stroke(pts, closed, thickness):
                out.append(ir.Path(points=ring, closed=True, curve="line",
                                   role=ir.ROLE_REGION, layer=ir.LAYER_PATTERN))
    return out


def _drop_regions_in_text(elements: Sequence[Any], doc: dict,
                          thickness: float) -> List[Any]:
    """Knockout im Flaechenmodell: Loecher im Textbereich fallen ganz weg.

    Anders als beim Stroken wird hier nicht die Zelle beschnitten - eine
    angeschnittene Zelle waere ein Loch mit Textkante. Stattdessen entfaellt das
    Loch komplett, der Textbereich wird also massiv und der Text bleibt lesbar.
    """
    from core.clip import polygon_intersects
    from text.text_layer import text_box

    boxes = []
    for layer in doc.get("textLayers", []):
        if layer.get("enabled") and layer.get("knockout"):
            margin = float(layer.get("knockoutMargin", 0.0)) + thickness / 2.0
            box = text_box(layer, margin=margin)
            if box:
                boxes.append(box)
    if not boxes:
        return list(elements)

    out: List[Any] = []
    for el in elements:
        pts = None
        if isinstance(el, ir.Path) and el.closed:
            pts = el.points
        elif isinstance(el, ir.Circle):
            pts = _circle_to_points(el, 24)
        if pts is not None and any(polygon_intersects(pts, box) for box in boxes):
            continue
        out.append(el)
    return out


def _shrink_cell(pts: Sequence[Point], delta: float) -> Optional[List[Point]]:
    """Zelle um ``delta`` verkleinern - auch bei konkaven Konturen.

    ``inset_polygon`` arbeitet mit Winkelhalbierenden und kollabiert an starken
    Einbuchtungen (Puzzle-Nasen). Der Offset des Strokers kommt damit zurecht;
    das Ergebnis wird verworfen, wenn es umklappt oder groesser wird.

    Konvexe Zellen - also alle Gitter-, Waben- und Voronoi-Muster - gehen den
    exakten Weg ueber die Halbebenen-Erosion. Der Gehrungs-Offset legt an einer
    spitz zulaufenden Zelle sonst eine kleine Schleife an, und ein sich selbst
    schneidendes Profil ist in Fusion unbrauchbar.
    """
    if delta <= 1e-12:
        return list(pts)
    src = clean_polygon(ensure_ccw(pts))
    if len(src) < 3:
        return None
    if is_convex(src):
        return erode_convex(src, delta)
    poly = offset_polyline(src, [delta] * len(src), closed=True)
    if not poly or len(poly) < 3:
        return None
    a_src, a_new = polygon_area(src), polygon_area(poly)
    if a_new <= 1e-10 or a_new >= a_src:
        return None
    return poly


#: Ein Loch, dessen mittlere Breite darunter liegt, ist ein Splitter aus einer
#: angeschnittenen Randzelle - es wird zugemacht (sonst duenne, nicht druckbare
#: Stellen und unnoetige Skizzen-Entities).
MIN_HOLE_WIDTH_FACTOR = 0.5


def _is_sliver(poly: Sequence[Point], min_width: float) -> bool:
    """Mittlere Breite = 2 * Flaeche / Umfang - unter ``min_width`` ein Splitter."""
    if min_width <= 0:
        return False
    area = abs(polygon_area(poly))
    perimeter = polyline_length(poly, closed=True)
    if perimeter <= 1e-12:
        return True
    return (2.0 * area / perimeter) < min_width


def _limit_hole(poly: Sequence[Point], limit: Optional[Container]
                ) -> List[List[Point]]:
    """Loch auf den erlaubten Bereich beschneiden (Rahmendicke einhalten)."""
    if limit is None or limit.fully_inside(poly):
        return [list(poly)]
    return [p for p in limit.clip_path(poly, True) if len(p) >= 3]


def _to_face(elements: Sequence[Any], container: Container, thickness: float,
             own_gap: float, hole_limit: Optional[Container] = None) -> List[Any]:
    """Kachelndes Stegnetz -> eine Flaeche: Aussenkontur + Loecher.

    Die Zelle wird so weit verkleinert, dass der Steg zwischen zwei Zellen genau
    ``thickness`` breit wird - wie beim Stroken, aber ohne dass sich an den Knoten
    Streifen ueberlappen. ``own_gap`` ist die Fuge, die der Generator schon selbst
    laesst (Mauerfuge, Voronoi-Fuge); sie wird angerechnet, die Stegbreite ist also
    ``max(thickness, own_gap)`` und die Ziegelmasse bleiben exakt.

    ``hole_limit`` begrenzt die Loecher zusaetzlich: an beschnittenen Randzellen
    kann die Gehrung eine Ecke nach aussen schieben und den Rahmen dort duenner
    machen als eingestellt. Das Beschneiden am Limit garantiert die Rahmendicke
    an **jeder** Stelle - wichtig fuer den 3D-Druck.
    """
    out: List[Any] = [container.face_outline()]
    delta = max(0.0, (thickness - own_gap) / 2.0)

    for el in elements:
        if isinstance(el, ir.Path) and el.role == ir.ROLE_REGION and el.closed:
            poly = _shrink_cell(el.points, delta)
            if not poly or len(poly) < 3:
                continue
            for piece in _limit_hole(poly, hole_limit):
                if abs(polygon_area(piece)) <= 1e-10:
                    continue
                if _is_sliver(piece, thickness * MIN_HOLE_WIDTH_FACTOR):
                    continue
                out.append(ir.Path(points=list(piece), closed=True, curve=el.curve,
                                   role=ir.ROLE_HOLE, layer=el.layer))
        elif isinstance(el, ir.Circle) and el.role == ir.ROLE_REGION:
            # Kreise sind bei kachelnden Mustern Einschluesse (z. B. Kiesel-Kern),
            # keine Kacheln - sie bleiben eigenstaendige Inseln im Loch.
            out.append(el)
        elif isinstance(el, ir.TextItem):
            out.append(el)
    return out


def entity_estimate(scene: ir.Scene) -> int:
    """Grobe Zahl der Skizzen-Entities, die der Commit erzeugen wuerde."""
    total = 0
    for el in scene.elements:
        if isinstance(el, ir.Path):
            n = len(el.points)
            if el.curve == "spline":
                total += 1
            else:
                total += n if el.closed else max(1, n - 1)
        elif isinstance(el, (ir.Circle, ir.Ellipse, ir.Arc, ir.TextItem)):
            total += 1
    return total
