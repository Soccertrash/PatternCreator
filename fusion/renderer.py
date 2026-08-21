"""IR -> Skizzengeometrie.

Wichtig fuer die Performance: ``sketch.isComputeDeferred`` wird um den gesamten
Zeichenvorgang **und** um das Loeschen gelegt (immer in ``try/finally``
zurueckgesetzt); ``areProfilesShown`` und ``arePointsShown`` sind waehrend des
Aufbaus abgeschaltet.
"""

from __future__ import annotations

import math
import traceback
from typing import List, Optional, Tuple

import adsk.core
import adsk.fusion

from core import ir

from . import trace

Point = Tuple[float, float]


class RenderResult:
    def __init__(self) -> None:
        self.entities = 0
        self.texts = 0
        self.warnings: List[str] = []


def _p3(x: float, y: float) -> "adsk.core.Point3D":
    return adsk.core.Point3D.create(x, y, 0.0)


def clear_pattern_geometry(sketch: "adsk.fusion.Sketch") -> int:
    """Alle Kurven und Texte der Skizze loeschen (Re-Generate).

    Gedacht fuer Muster auf einer Ebene. Auf einer Mantelflaeche wird die Skizze
    stattdessen ersetzt (``palette_bridge._replant``) - das ist **ein** Aufruf
    statt tausender und damit unvergleichlich schneller.

    Drei Schalter muessen um das Loeschen herum stehen, nicht nur einer:
    ``isComputeDeferred`` haelt die Neuberechnung an, aber die **Darstellung**
    laeuft weiter. Eine Musterskizze zeigt tausende schattierte Profile; jedes
    ``deleteMe()`` liess Fusion sie neu aufbauen. Genau daran ist die Anwendung
    haengengeblieben (gemessen 2026-08-21, siehe Context.md 15.13) - der
    Aufwand waechst quadratisch mit der Elementzahl.
    """
    removed = 0
    previous_defer = sketch.isComputeDeferred
    previous_profiles = sketch.areProfilesShown
    previous_points = getattr(sketch, "arePointsShown", None)
    try:
        sketch.isComputeDeferred = True
        _quiet(sketch, profiles=False, points=False)
        trace.step("Skizze leeren: %d Kurven" % sketch.sketchCurves.count)
        for c in list(sketch.sketchCurves):
            try:
                c.deleteMe()
                removed += 1
                if removed % 500 == 0:
                    trace.step("   %d gelöscht" % removed)
            except Exception:
                pass
        for t in list(sketch.sketchTexts):
            try:
                t.deleteMe()
                removed += 1
            except Exception:
                pass
        for p in list(sketch.sketchPoints):
            if p == sketch.originPoint:
                continue
            try:
                p.deleteMe()
            except Exception:
                pass
    finally:
        _quiet(sketch, profiles=previous_profiles, points=previous_points)
        sketch.isComputeDeferred = previous_defer
    return removed


def _quiet(sketch: "adsk.fusion.Sketch", profiles, points) -> None:
    """Profil- und Punktdarstellung setzen - beides ist reine Anzeige."""
    if profiles is not None:
        try:
            sketch.areProfilesShown = profiles
        except Exception:
            pass
    if points is not None:
        try:
            sketch.arePointsShown = points
        except Exception:
            pass


def render_scene(sketch: "adsk.fusion.Sketch", scene: ir.Scene) -> RenderResult:
    """Szene in die Skizze zeichnen. Gibt Statistik und Warnungen zurueck."""
    result = RenderResult()
    previous_defer = sketch.isComputeDeferred
    previous_profiles = sketch.areProfilesShown
    previous_points = getattr(sketch, "arePointsShown", None)
    try:
        sketch.isComputeDeferred = True
        # Jede Linie bringt zwei Skizzenpunkte mit, und jede Masche ein Profil -
        # bei tausenden Elementen kostet allein deren Darstellung spuerbar Zeit.
        _quiet(sketch, profiles=False, points=False)
        curves = sketch.sketchCurves
        for el in scene.elements:
            try:
                if isinstance(el, ir.Path):
                    result.entities += _draw_path(curves, el)
                elif isinstance(el, ir.Circle):
                    curves.sketchCircles.addByCenterRadius(_p3(*el.center), el.radius)
                    result.entities += 1
                elif isinstance(el, ir.Arc):
                    result.entities += _draw_arc(curves, el)
                elif isinstance(el, ir.Ellipse):
                    result.entities += _draw_ellipse(curves, el)
                elif isinstance(el, ir.TextItem):
                    ok, warn = _draw_text(sketch, el)
                    result.texts += 1 if ok else 0
                    result.entities += 1 if ok else 0
                    if warn:
                        result.warnings.append(warn)
            except Exception:
                result.warnings.append("Ein Element konnte nicht gezeichnet werden:\n"
                                       + traceback.format_exc(limit=1))
    finally:
        _quiet(sketch, profiles=previous_profiles, points=previous_points)
        sketch.isComputeDeferred = previous_defer
    return result


# ----------------------------------------------------------------- Elemente

def _draw_path(curves: "adsk.fusion.SketchCurves", el: ir.Path) -> int:
    pts = el.points
    if len(pts) < 2:
        return 0
    if el.curve == "spline" and len(pts) >= 3:
        coll = adsk.core.ObjectCollection.create()
        for x, y in pts:
            coll.add(_p3(x, y))
        if el.closed:
            coll.add(_p3(pts[0][0], pts[0][1]))
        curves.sketchFittedSplines.add(coll)
        return 1
    count = 0
    lines = curves.sketchLines
    n = len(pts)
    last = n if el.closed else n - 1
    prev_pt = _p3(pts[0][0], pts[0][1])
    first_pt = prev_pt
    for i in range(last):
        j = (i + 1) % n
        nxt = first_pt if (el.closed and j == 0) else _p3(pts[j][0], pts[j][1])
        line = lines.addByTwoPoints(prev_pt, nxt)
        prev_pt = line.endSketchPoint
        count += 1
    return count


def _draw_arc(curves: "adsk.fusion.SketchCurves", el: ir.Arc) -> int:
    sweep = el.a1 - el.a0
    if abs(sweep) < 1e-9:
        return 0
    start = _p3(el.center[0] + el.radius * math.cos(el.a0),
                el.center[1] + el.radius * math.sin(el.a0))
    curves.sketchArcs.addByCenterStartSweep(_p3(*el.center), start, sweep)
    return 1


def _draw_ellipse(curves: "adsk.fusion.SketchCurves", el: ir.Ellipse) -> int:
    cx, cy = el.center
    ca, sa = math.cos(el.rotation), math.sin(el.rotation)
    major = _p3(cx + el.rx * ca, cy + el.rx * sa)
    minor = _p3(cx - el.ry * sa, cy + el.ry * ca)
    curves.sketchEllipses.add(_p3(cx, cy), major, minor)
    return 1


def _draw_text(sketch: "adsk.fusion.Sketch", el: ir.TextItem) -> Tuple[bool, Optional[str]]:
    """SketchText erzeugen; unbekannte Schriftart faellt auf Arial zurueck."""
    texts = sketch.sketchTexts
    warn = None
    width = max(el.height * 0.62 * max(1, len(el.text)), el.height)
    corner = _p3(el.x, el.y)
    diagonal = _p3(el.x + width * 1.4, el.y + el.height * 1.6)
    text_input = texts.createInput2(el.text, el.height)
    try:
        text_input.setAsMultiLine(
            corner, diagonal,
            adsk.core.HorizontalAlignments.LeftHorizontalAlignment,
            adsk.core.VerticalAlignments.BottomVerticalAlignment, 0.0)
    except Exception:
        warn = "Textposition konnte nicht exakt gesetzt werden."
    try:
        text_input.fontName = el.font
    except Exception:
        warn = ("Schriftart „%s“ ist nicht verfügbar – es wird Arial verwendet."
                % el.font)
        try:
            text_input.fontName = "Arial"
        except Exception:
            pass
    try:
        sketch_text = texts.add(text_input)
    except Exception:
        try:
            text_input.fontName = "Arial"
            sketch_text = texts.add(text_input)
            warn = ("Schriftart „%s“ ist nicht verfügbar – es wird Arial verwendet."
                    % el.font)
        except Exception:
            return False, "Text konnte nicht erzeugt werden (Schriftart „%s“)." % el.font
    if abs(el.angle) > 1e-9:
        _rotate_entity(sketch, sketch_text, (el.x, el.y), el.angle)
    return True, warn


def _rotate_entity(sketch: "adsk.fusion.Sketch", entity, pivot: Point, angle: float) -> None:
    try:
        coll = adsk.core.ObjectCollection.create()
        coll.add(entity)
        matrix = adsk.core.Matrix3D.create()
        matrix.setToRotation(angle, adsk.core.Vector3D.create(0, 0, 1),
                             _p3(pivot[0], pivot[1]))
        sketch.move(coll, matrix)
    except Exception:
        pass
