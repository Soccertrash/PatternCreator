"""Rahmenkontur aus Fusion lesen: Skizzenprofil oder planare Flaeche.

Der Rahmen ist ein **Schnappschuss**: gelesen wird einmal, danach steht die
Kontur als Punktliste im PatternDoc. Ein Re-Edit braucht die Quelle nicht mehr;
„Rahmen neu einlesen" holt sie ueber den gespeicherten Entity-Token nach.

Nur die **Aussenkontur** zaehlt - Innenkonturen (Loecher im Profil, Bohrungen in
der Flaeche) werden bewusst ignoriert (Entscheidung 2026-08-21, `Context.md`
15.1).

Alles, was ohne Fusion geht, liegt in ``core``: das Verketten der Kurvenstuecke
(``geom.chain_polylines``), das Normalisieren der Kontur
(``containers.normalize_frame``) und das Einsetzen ins Doc
(``pattern_doc.apply_custom_frame``). Hier bleibt nur die API-Arbeit.
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

import adsk.core
import adsk.fusion

from core.geom import chain_polylines
from core.optimize import TOL

Point = Tuple[float, float]

#: Abtast-Toleranz fuer Boegen und Splines (cm) - dieselbe, mit der der
#: Optimierer arbeitet. Feiner waere sinnlos: das RDP im Anschluss wirft es weg.
STROKE_TOL = TOL

#: Endpunkte, die dichter beieinander liegen, sind derselbe Punkt (cm).
JOIN_TOL = 1e-4

#: Groesster erlaubter Abstand von der Skizzenebene (cm).
PLANE_TOL = 1e-4


class FrameError(Exception):
    """Klartext-Fehler fuer den Editor - nie selbst eine ``messageBox`` zeigen."""


class FrameSnapshot:
    """Ergebnis von :func:`read_frame` - reine Zahlen plus die Zielebene."""

    def __init__(self, points: List[Point], plane: Any, label: str, kind: str,
                 token: str):
        self.points = points          # Skizzenkoordinaten, cm
        self.plane = plane            # ConstructionPlane oder BRepFace
        self.label = label
        self.kind = kind              # "profile" | "face"
        self.token = token

    def source(self) -> dict:
        return {"kind": self.kind, "label": self.label, "token": self.token}


# --------------------------------------------------------------- Erkennung

def is_supported(entity: Any) -> bool:
    """Taugt die Auswahl als Rahmenquelle?"""
    return _as_profile(entity) is not None or _as_planar_face(entity) is not None


def _as_profile(entity: Any):
    try:
        return adsk.fusion.Profile.cast(entity)
    except Exception:
        return None


def _as_planar_face(entity: Any):
    try:
        face = adsk.fusion.BRepFace.cast(entity)
    except Exception:
        return None
    if face is None:
        return None
    try:
        return face if adsk.core.Plane.cast(face.geometry) else None
    except Exception:
        return None


def plane_of(entity: Any) -> Any:
    """Zielebene einer Auswahl - auch ohne die Kontur zu lesen.

    Profil ⇒ Ebene seiner Skizze, Flaeche ⇒ die Flaeche selbst, sonst die
    Auswahl unveraendert (Konstruktionsebene).
    """
    profile = _as_profile(entity)
    if profile is not None:
        return _reference_plane(profile.parentSketch)
    face = _as_planar_face(entity)
    if face is not None:
        return face
    return entity


def is_face(entity: Any) -> bool:
    """Ist die Zielebene eine BRep-Flaeche? (Dann Skizze ohne Kantenprojektion.)"""
    return _as_planar_face(entity) is not None


# ------------------------------------------------------------------ Lesen

def read_frame(entity: Any, sketch: Any = None, design: Any = None
               ) -> FrameSnapshot:
    """Aussenkontur von ``entity`` als Punktliste in Skizzenkoordinaten.

    ``sketch`` ist die Ziel-Skizze, falls es sie schon gibt (Re-Edit). Sonst
    entsteht kurzzeitig eine leere Hilfsskizze auf der Zielebene, nur um die
    Weltkoordinaten umzurechnen - sie wird sofort wieder geloescht. Das laeuft
    innerhalb eines Commands, damit in der Timeline nichts zurueckbleibt.
    """
    design = design or _design()
    profile = _as_profile(entity)
    face = None if profile is not None else _as_planar_face(entity)
    if profile is None and face is None:
        raise FrameError("Bitte ein geschlossenes Skizzenprofil oder eine ebene "
                         "Fläche wählen.")

    if profile is not None:
        world, plane, label = _read_profile(profile)
        kind = "profile"
    else:
        world, plane, label = _read_face(face)
        kind = "face"

    points = _to_sketch_space(world, plane, sketch, design)
    return FrameSnapshot(points, plane, label, kind, _token_of(entity))


def _read_profile(profile) -> Tuple[List[Any], Any, str]:
    loop = _outer_loop(profile.profileLoops)
    if loop is None:
        raise FrameError("Das Profil hat keine Außenkontur.")
    pieces: List[List[Any]] = []
    for curve in loop.profileCurves:
        geometry = None
        entity = getattr(curve, "sketchEntity", None)
        if entity is not None:
            geometry = getattr(entity, "worldGeometry", None)
        if geometry is None:
            geometry = curve.geometry
        pieces.append(_strokes(geometry))
    sketch = profile.parentSketch
    plane = _reference_plane(sketch)
    label = "%s / Profil" % sketch.name
    return _chain(pieces), plane, label


def _read_face(face) -> Tuple[List[Any], Any, str]:
    loop = _outer_loop(face.loops)
    if loop is None:
        raise FrameError("Die Fläche hat keine Außenkontur.")
    pieces: List[List[Any]] = []
    for co_edge in loop.coEdges:
        # Der Richtung der CoEdges wird nicht getraut - verkettet wird ueber die
        # Endpunkte (``chain_polylines``).
        pieces.append(_strokes(co_edge.edge))
    body = face.body
    try:
        label = "%s / Fläche %d" % (body.name, list(body.faces).index(face) + 1)
    except Exception:
        label = "Fläche"
    return _chain(pieces), face, label


def _outer_loop(loops) -> Any:
    for loop in loops:
        if loop.isOuter:
            return loop
    return None


def _strokes(source) -> List[Any]:
    """Kurve (oder Kante) in Punkte aufloesen - Weltkoordinaten, cm."""
    evaluator = getattr(source, "evaluator", None)
    if evaluator is None:
        raise FrameError("Eine Kurve der Kontur lässt sich nicht auswerten.")
    ok, t0, t1 = evaluator.getParameterExtents()
    if not ok:
        raise FrameError("Eine Kurve der Kontur lässt sich nicht auswerten.")
    ok, points = evaluator.getStrokes(t0, t1, STROKE_TOL)
    if not ok or not points:
        raise FrameError("Eine Kurve der Kontur lässt sich nicht abtasten.")
    return list(points)


def _chain(pieces: Sequence[Sequence[Any]]) -> List[Tuple[float, float, float]]:
    """Kurvenstuecke ueber ihre Endpunkte zu einem Ring verketten (3D)."""
    as_xyz = [[(p.x, p.y, p.z) for p in piece] for piece in pieces]
    ring = chain_polylines(as_xyz, tol=JOIN_TOL)
    if ring is None:
        raise FrameError("Die Kontur ist nicht geschlossen (Lücke zwischen zwei "
                         "Kurven). Bitte die Skizze prüfen.")
    return ring


# ------------------------------------------------------- Welt -> Skizze

def _reference_plane(sketch) -> Any:
    """Ebene, auf der eine Skizze liegt (ConstructionPlane oder BRepFace)."""
    plane = None
    try:
        plane = sketch.referencePlane
    except Exception:
        plane = None
    if plane is None:
        raise FrameError("Die Skizzenebene des Profils ist nicht mehr vorhanden. "
                         "Bitte eine Ebene oder Fläche wählen.")
    return plane


def _to_sketch_space(world: Sequence[Tuple[float, float, float]], plane: Any,
                     sketch: Any, design: Any) -> List[Point]:
    """Weltpunkte in Skizzenkoordinaten - notfalls ueber eine Hilfsskizze."""
    target = sketch
    temporary = None
    try:
        if target is None:
            temporary = _temporary_sketch(design, plane)
            target = temporary
        out: List[Point] = []
        for x, y, z in world:
            p = target.modelToSketchSpace(adsk.core.Point3D.create(x, y, z))
            if abs(p.z) > PLANE_TOL:
                raise FrameError("Die Auswahl liegt nicht auf der Skizzenebene.")
            out.append((p.x, p.y))
        return out
    finally:
        if temporary is not None:
            try:
                temporary.deleteMe()
            except Exception:
                pass


def _temporary_sketch(design, plane):
    """Leere Hilfsskizze auf ``plane`` - ohne projizierte Kanten.

    ``addWithoutEdges`` ist Pflicht, sobald ``plane`` eine Flaeche ist: sonst
    projiziert Fusion deren Kanten in die Skizze, und die laegen exakt auf dem
    Rahmenumriss.
    """
    comp = design.activeComponent
    try:
        return comp.sketches.addWithoutEdges(plane)
    except Exception:
        return comp.sketches.add(plane)


def _design():
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise FrameError("Kein Konstruktionsdokument aktiv.")
    return design


# ------------------------------------------------------------------ Token

def _token_of(entity: Any) -> str:
    try:
        token = entity.entityToken
    except Exception:
        token = None
    if token:
        return str(token)
    # Fallback: Profile hatten historisch keinen eigenen Token - dann merken wir
    # uns die Eltern-Skizze und den Index des Profils in ihr.
    profile = _as_profile(entity)
    if profile is not None:
        try:
            sketch = profile.parentSketch
            index = list(sketch.profiles).index(profile)
            return "%s#%d" % (sketch.entityToken, index)
        except Exception:
            pass
    return ""


def find_source(token: str, design: Any = None) -> Any:
    """Quelle ueber ihren Token wiederfinden.

    Wirft ``FrameError``, wenn es sie nicht mehr gibt - die Meldung geht als
    Klartext an den Editor.
    """
    if not token:
        raise FrameError("Zu diesem Rahmen ist keine Quelle gespeichert. "
                         "Bitte im Fusion-Canvas neu auswählen.")
    design = design or _design()
    index = None
    if "#" in token:
        token, _, tail = token.rpartition("#")
        try:
            index = int(tail)
        except ValueError:
            index = None
    try:
        found = design.findEntityByToken(token)
    except Exception:
        found = None
    entities = list(found) if found else []
    if not entities:
        raise FrameError("Die Quelle des Rahmens ist nicht mehr vorhanden – "
                         "bitte neu auswählen.")
    entity = entities[0]
    if index is not None:
        sketch = adsk.fusion.Sketch.cast(entity)
        if sketch is None:
            raise FrameError("Die Quelle des Rahmens ist nicht mehr vorhanden – "
                             "bitte neu auswählen.")
        profiles = list(sketch.profiles)
        if index >= len(profiles):
            raise FrameError("Die Rahmen-Skizze hat sich verändert – bitte das "
                             "Profil neu auswählen.")
        entity = profiles[index]
    return entity


def pick_from_selection(ui: Any) -> Any:
    """Erstes brauchbares Element der aktuellen Canvas-Auswahl."""
    try:
        selections = ui.activeSelections
    except Exception:
        selections = None
    if selections:
        for i in range(selections.count):
            entity = selections.item(i).entity
            if is_supported(entity):
                return entity
    raise FrameError("Bitte im Fusion-Canvas ein geschlossenes Skizzenprofil "
                     "oder eine ebene Fläche auswählen.")
