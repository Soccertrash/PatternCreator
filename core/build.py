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
9. Optimierung (``core/optimize.py``): weniger Skizzenelemente, gleiche Geometrie
"""

from __future__ import annotations

import math
import random
from typing import Any, List, Optional, Sequence, Tuple

from . import ir, warp
from .containers import Container, make_container
from .development import development_from_doc
from .geom import (chain_segments, polygon_area, polygon_segments,
                   polyline_length, rotate, snap_segments)
from .hatch import hatch_areas, style_from_doc
from .optimize import TOL as OPTIMIZE_TOL, optimize
from .stroker import shrink_polygon as _shrink_cell, stroke

Point = Tuple[float, float]

#: Ab dieser Elementzahl warnt die Vorschau und zeichnet vereinfacht
PREVIEW_WARN_LIMIT = 5000
#: Ab dieser Entity-Zahl warnt der Commit (mit Abbruch-Option)
ENTITY_WARN_LIMIT = 2000

#: Der Rahmen ist irgendwo schmaler als zweimal die Rahmendicke - dann laesst
#: sich das Mass dort nicht einhalten (nur bei eigenen Rahmen moeglich).
SHRINK_WARNING = ("Rahmendicke ist für diesen Rahmen an mindestens einer "
                  "Stelle zu groß.")

#: Auf der Mantelflaeche liess sich keine Bahn entlang der Zellwaende finden -
#: dann bleibt es beim geraden Schnitt (siehe ``core/seam.py``).
SEAM_WARNING = ("Keine Naht entlang der Zellwände gefunden – der Schnitt ist "
                "gerade und kann bei versetzten Mustern sichtbar bleiben.")

#: Ohne Trennlinie in der Mitte gibt es nur ein Profil - und ein Profil ueber
#: volle 360 Grad laesst sich nicht praegen (``Context.md`` 15.6, Punkt 6).
SPLIT_WARNING = ("Keine Trennlinie für die Prägung gefunden – das Muster lässt "
                 "sich als Skizze erzeugen, aber nicht rundum prägen.")

#: Ohne Beschnitt reicht das Muster ueber den Umlauf hinaus - nach dem Wickeln
#: laege es auf sich selbst. Auf einer Mantelflaeche wird deshalb immer
#: beschnitten, egal was im Dokument steht.
CLIP_WARNING = ("Auf einer Mantelfläche wird immer am Rand beschnitten – sonst "
                "läge das Muster nach dem Wickeln auf sich selbst.")

#: Ab welcher Stauchung am schmalen Kegelende gewarnt wird.
CONE_TAPER_LIMIT = 0.9

#: Wie weit die Trennlinie beim Kegel ueber den Rand hinausstehen muss (cm).
#:
#: Nach dem Biegen ist die Aussenkontur ein **Polygonzug** durch den Bogen, die
#: Trennlinie endet aber auf dem echten Bogen - gemessen 15 µm daneben. Fusion
#: sieht dann keine Teilung, macht ein einziges Profil ueber den ganzen Sektor
#: und lehnt es als sich selbst durchdringenden Koerper ab (Context.md 15.19).
#: Sechs Toleranzen decken beides ab: die Sehnenhoehe beim Biegen und die
#: Vereinfachung des Optimierers danach. Sichtbar ist der Ueberstand mit
#: 0,12 mm nicht.
DIVIDER_OVERSHOOT = 6.0 * OPTIMIZE_TOL


def cone_taper_warning(narrow: float, thickness: float) -> str:
    """Klartext dazu, wie schmal das Muster an der Spitze wird."""
    return ("Am schmalen Ende des Kegels ist das Muster nur %d %% so breit wie "
            "am weiten – Stege sind dort etwa %.2f mm statt %.2f mm."
            % (round(narrow * 100.0), thickness * narrow * 10.0,
               thickness * 10.0))


def _shrunk(container: Container, delta: float, warnings: List[str],
            seam_free: bool = False) -> Container:
    """``container.shrunk`` mit Warnung, wenn der Versatz nicht moeglich war.

    ``seam_free`` heisst: in x nicht einruecken. An der Naht einer Mantelflaeche
    darf kein Rand stehen - dort treffen sich nach dem Wickeln die beiden
    Haelften des Nahtstegs.
    """
    inner = container.shrunk_xy(0.0 if seam_free else delta, delta)
    if getattr(inner, "shrink_failed", False) and SHRINK_WARNING not in warnings:
        warnings.append(SHRINK_WARNING)
    return inner


def build_scene(doc: dict, container: Optional[Container] = None) -> ir.Scene:
    """PatternDoc -> fertige IR-Szene (in Skizzenkoordinaten, cm)."""
    from generators import get_generator

    development = doc.get("development")
    container = container or make_container(doc["container"], development)
    style = doc["style"]
    placement = doc["placement"]
    warnings: List[str] = []

    period = _period_of(development, container)
    # Ein gedrehtes Muster ist nicht x-periodisch - auf einer Mantelflaeche
    # bleibt die Musterdrehung deshalb aus (der Editor blendet sie dort aus).
    pattern_angle = (0.0 if period > 0.0
                     else math.radians(float(placement.get("patternAngle", 0.0))))
    bbox = _generation_bbox(container, pattern_angle)

    gen = get_generator(doc["pattern"]["type"])
    params = dict(doc["pattern"]["params"])
    elements = list(gen.generate(params, _context(doc, bbox, period)))

    if abs(pattern_angle) > 1e-12:
        elements = [_rotate_element(el, pattern_angle) for el in elements]

    fill_target = str(style.get("fillTarget", "webs"))
    if fill_target not in getattr(gen, "fill_targets", ("webs",)):
        fill_target = getattr(gen, "fill_targets", ("webs",))[0]

    mode = str(style.get("mode", "area"))
    clip_mode = str(style.get("clip", "cut"))
    if period > 0.0 and clip_mode == "off":
        clip_mode = "cut"
        warnings.append(CLIP_WARNING)
    seam_net: List[Any] = []
    seam_grow = 0.0
    if period > 0.0 and clip_mode != "off":
        container, elements, seam_net, seam_grow = _apply_seam(
            container, gen, doc, params, bbox, elements, period, warnings)
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
    seam_free = period > 0.0
    clip_container = container
    if as_face:
        inset = max(0.0, border_width - thickness / 2.0)
        if inset > 1e-9:
            clip_container = _shrunk(container, inset, warnings, seam_free)

    elements = _clip_elements(elements, clip_container, clip_mode)

    if as_face:
        elements = _drop_regions_in_text(elements, doc, thickness)
        elements = _to_face(elements, container, thickness, own_gap=own_gap,
                            hole_limit=_shrunk(container, border_width, warnings,
                                               seam_free))
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
        if period > 0.0 and bool(style.get("embossOn")):
            bent = development_from_doc(development)
            elements.extend(_divider(elements, container,
                                     max(thickness, own_gap) / 2.0,
                                     seam_net, seam_grow, warnings,
                                     overshoot=(DIVIDER_OVERSHOOT
                                                if bent is not None
                                                and bent.is_cone() else 0.0)))
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
            # Im Flaechenmodus ist der Rahmen ein Band, kein Strich: nur so haengen
            # die Streifen eines Strich-Musters ueberhaupt zusammen. Jeder Streifen
            # endet am Umriss und laeuft damit in das Band hinein - extrudiert wird
            # daraus ein Koerper statt vieler loser Teile.
            outline = list(container.outline())
            if mode == "area" and border_width > 1e-9:
                inner = _shrunk(container, border_width, warnings, seam_free)
                if inner is not container:
                    outline += list(inner.outline())
            elements = outline + elements

    from text.text_layer import text_elements
    for layer in doc.get("textLayers", []):
        elements.extend(text_elements(layer))

    # Beim Kegel wird die fertige Szene jetzt in den Kreisringsektor gebogen -
    # nach allem, was in geraden Koordinaten rechnet, und vor der Platzierung,
    # die nur noch verschiebt und dreht (Context.md 15.14).
    dev = development_from_doc(development)
    elements, bend_warnings = warp.bend(elements, dev)
    warnings.extend(bend_warnings)
    narrow = _cone_narrowing(dev)
    if narrow < CONE_TAPER_LIMIT:
        warnings.append(cone_taper_warning(narrow, thickness))

    origin = (float(placement.get("originX", 0.0)), float(placement.get("originY", 0.0)))
    frame_angle = math.radians(float(placement.get("rotation", 0.0)))
    if abs(frame_angle) > 1e-12 or origin != (0.0, 0.0):
        elements = [_place_element(el, frame_angle, origin) for el in elements]

    # Zuletzt: Skizzenelemente zusammenfassen. Weil das vor der Scene-Erzeugung
    # passiert, sehen Vorschau, ``entity_estimate`` und Fusion denselben Stand.
    scene = ir.Scene(elements=optimize(elements), warnings=warnings)
    n = scene.counts()["contours"]
    if n > PREVIEW_WARN_LIMIT:
        warnings.append("Sehr viele Elemente (%d) – Erzeugen kann dauern." % n)
    return scene


# --------------------------------------------------------------- Teilschritte

def _context(doc: dict, bbox: Tuple[float, float, float, float], period: float):
    """Generator-Kontext. Zweimal gebraucht: fuers Muster und fuer die Naht."""
    from generators import GenContext

    style = doc["style"]
    return GenContext(
        bbox=bbox,
        rnd=random.Random(int(doc.get("seed", 0))),
        thickness=float(style.get("thickness", 0.08)),
        fill_target=str(style.get("fillTarget", "webs")),
        mode=str(style.get("mode", "area")),
        period_x=period,
    )


def _cone_narrowing(dev) -> float:
    """Wie schmal wird das Muster am spitzen Ende? (1.0 = gar nicht)

    Ein Muster, das rundum passt, hat auf jedem Hoehenkreis gleich viele Zellen -
    und der Umfang nimmt zur Spitze hin ab. Die Stege gehen mit: ein radial
    verlaufender Steg ist dort nur noch diesen Bruchteil breit. Fuer den Druck
    ist das die entscheidende Zahl.
    """
    if dev is None or not dev.is_cone():
        return 1.0
    rho = dev.apex_distance()
    if rho <= 0.0:
        return 1.0
    return max(0.0, (rho - dev.length / 2.0) / rho)


def _period_of(development: Optional[dict], container: Container) -> float:
    """Breite eines Umlaufs - 0, wenn das Muster nicht rundum laeuft."""
    dev = development_from_doc(development)
    if dev is None or not dev.periodic:
        return 0.0
    try:
        period = dev.period()
    except NotImplementedError:
        return 0.0
    x0, _y0, x1, _y1 = container.bounding_rect()
    # Der Rahmen kommt aus derselben Abwicklung; weicht er ab, wurde er von
    # aussen vorgegeben (Tests, Vorschau) und die Periode gilt nicht.
    return period if abs((x1 - x0) - period) < 1e-6 else 0.0


def _divider(elements: Sequence[Any], container: Container, web_half: float,
             net: Sequence[Any], net_grow: float, warnings: List[str],
             overshoot: float = 0.0) -> List[Any]:
    """Trennlinie durch die Mitte der Abwicklung - fuer die Praegung.

    Eine rundum laufende Praegung braucht in Fusion **zwei** Features: ein
    Profil ueber volle 360 Grad wird als sich selbst durchdringender Koerper
    abgelehnt (``Context.md`` 15.6, Punkt 6). Zwei Features brauchen zwei
    Profile - und die entstehen, indem eine Linie die Flaeche teilt.

    Gesucht wird sie mit derselben Maschinerie wie die Naht - zuerst an den
    **Loechern** (der endgueltigen Geometrie: um den halben Steg aufgeweitet
    stossen sie aneinander, die Bahn laeuft dann genau in der Stegmitte), und
    wenn das nichts ergibt, am Zellnetz. Beides kann scheitern: beim Puzzle sind
    die Stege zwischen zwei Nasen schmaler als anderswo, bei den Blattadern
    liegen verschieden breite Fugen nebeneinander. Deshalb wird das Ergebnis
    **nachgerechnet**: eine Bahn, die kein Loch anschneidet, hat Vorrang.

    Findet sich keine saubere, wird trotzdem geteilt. Eine Linie, die ein Loch
    kreuzt, laesst Fusion dort zwei Profile statt einem entstehen - an der
    Praegung aendert das nichts (die beiden grossen Profile sind weiterhin das
    Stegnetz), sichtbar bleibt nur ein zusaetzlicher Strich in der Skizze. Ganz
    ohne Trennlinie liesse sich dagegen gar nicht praegen.
    """
    from . import seam

    holes = [el.points for el in elements
             if isinstance(el, ir.Path) and el.role == ir.ROLE_HOLE]
    if len(holes) < 2:
        warnings.append(SPLIT_WARNING)
        return []
    x0, y0, x1, y1 = container.bounding_rect()
    middle = (x0 + x1) / 2.0
    fallback = None
    for cells, grow in ((holes, max(0.0, web_half)), (list(net), net_grow)):
        if len(cells) < 2:
            continue
        path = seam.seam_path(cells, middle, y0, y1,
                              seam.suggest_offset(cells, x1 - x0), grow=grow)
        if path is None:
            continue
        if not seam.crossed_cells(holes, path):
            return [ir.path(_over(path, overshoot), closed=False,
                            role=ir.ROLE_EDGE, layer=ir.LAYER_BORDER)]
        fallback = fallback or path
    if fallback is None:
        warnings.append(SPLIT_WARNING)
        return []
    return [ir.path(_over(fallback, overshoot), closed=False,
                    role=ir.ROLE_EDGE, layer=ir.LAYER_BORDER)]


def _over(path: Sequence[Any], overshoot: float) -> List[Any]:
    """Die Trennlinie an beiden Enden ueber den Rand hinaus verlaengern.

    Sie muss die Aussenkontur **kreuzen**, nicht nur beruehren - siehe
    :data:`DIVIDER_OVERSHOOT`. Verlaengert wird senkrecht (in y), denn dort
    liegen die beiden Raender; nach dem Biegen zeigt das radial nach aussen.
    """
    if overshoot <= 0.0 or len(path) < 2:
        return list(path)
    out = [(float(x), float(y)) for x, y in path]
    low, high = (0, -1) if out[0][1] < out[-1][1] else (-1, 0)
    out[low] = (out[low][0], out[low][1] - overshoot)
    out[high] = (out[high][0], out[high][1] + overshoot)
    return out


def _apply_seam(container: Container, gen, doc: dict, params: dict,
                bbox: Tuple[float, float, float, float], elements: List[Any],
                period: float, warnings: List[str]):
    """Rahmen mit Naht bauen und die Zellen jenseits davon nachliefern."""
    from . import seam
    from .containers import DevelopmentContainer

    x0, y0, x1, y1 = container.bounding_rect()
    net = gen.seam_cells(params, _context(doc, bbox, period))
    if not net:
        net = [el.points for el in elements
               if isinstance(el, ir.Path) and el.closed and el.role == ir.ROLE_REGION]
    path = None
    offset = 0.0
    grow = gen.gap(params) / 2.0
    if len(net) >= 2:
        offset = seam.suggest_offset(net, period)
        path = seam.seam_path(net, x0, y0, y1, offset, grow=grow, period=period)
    if path is not None:
        try:
            wrapped = DevelopmentContainer(path, period)
        except ValueError:
            path = None
    if path is None:
        warnings.append(SEAM_WARNING)
        return container, list(elements), net, grow
    return (wrapped, _wrapped_copies(elements, x0, x1, period, offset), net, grow)


def _x_span(el: Any) -> Optional[Tuple[float, float]]:
    if isinstance(el, ir.Path):
        xs = [p[0] for p in el.points]
        return (min(xs), max(xs)) if xs else None
    if isinstance(el, ir.Circle):
        return (el.center[0] - el.radius, el.center[0] + el.radius)
    if isinstance(el, ir.Ellipse):
        r = max(el.rx, el.ry)
        return (el.center[0] - r, el.center[0] + r)
    if isinstance(el, ir.Arc):
        return (el.center[0] - el.radius, el.center[0] + el.radius)
    return None


def _wrapped_copies(elements: Sequence[Any], x0: float, x1: float,
                    period: float, offset: float) -> List[Any]:
    """Zellen am Nahtband zusaetzlich um einen Umlauf versetzt anlegen.

    Organische Muster liefern jede Zelle genau **einmal**. Weicht die Nahtbahn
    nach aussen aus, faellt manche davon aus dem Rahmen - und ihr Platz auf der
    anderen Nahtseite bliebe leer. Die Kopie fuellt ihn. Welche der beiden im
    Rahmen liegt, entscheidet das Clipping: der Bereich zwischen den beiden
    Nahtkanten ist genau einen Umlauf breit, also liegt nie beides drin.
    """
    out = list(elements)
    left, right = x0 + offset, x1 - offset
    for el in elements:
        span = _x_span(el)
        if span is None:
            continue
        if span[1] <= left:
            out.append(_map_points(el, lambda p: (p[0] + period, p[1])))
        elif span[0] >= right:
            out.append(_map_points(el, lambda p: (p[0] - period, p[1])))
    return out


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
