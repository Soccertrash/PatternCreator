"""Muster auf eine Mantelflaeche bringen: Tangentialebene, Lage, Praegung.

Der Weg (alles im Spike gemessen, ``Context.md`` 15.6):

1. **Tangentialebene** ueber ``setByTangentAtPoint``. ``setByTangent`` verlangt
   eine Referenzebene parallel zur Achse und scheitert am Kegel; der Punkt-Weg
   funktioniert in allen geprueften Faellen. Der Beruehrpunkt liegt dem
   Nahtwinkel **gegenueber**: die Naht sitzt am Rand der Abwicklung, die
   Beruehrlinie in ihrer Mitte.
2. **Lage der Skizze.** Die Skizze auf dieser Ebene liegt gegenueber der Flaeche
   gedreht (gemessen: Skizzen-x entgegen der Umfangsrichtung, Skizzen-y entgegen
   der Achse - zusammen eine Drehung um 180 Grad, keine Spiegelung). Statt das
   fest einzubauen, wird es hier **gemessen**: zwei Richtungen in die Skizze
   umgerechnet, daraus Drehung und Ursprung. Die landen in ``placement`` im Doc -
   der Renderer bleibt dumm, das Dokument vollstaendig.
3. **Praegung** in zwei Features. Ein Profil ueber volle 360 Grad lehnt Fusion
   als sich selbst durchdringenden Koerper ab; zwei getrennte Features zu je
   180 Grad sind gesund. Die Trennlinie zwischen ihnen erzeugt ``core/build.py``
   entlang der Zellwaende, sie ist am Teil also nicht zu sehen.

Zwei Fallen, die den Spike gekostet haben und hier beruecksichtigt sind:
**Flaechen-Referenzen veralten nach jedem Feature** (die Flaeche wird vor jedem
Zugriff frisch geholt), und **nach dem ersten Praegen ist auch die Oberseite der
Praegung eine Zylinderflaeche** - gebraucht wird die mit dem Originalradius.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import adsk.core
import adsk.fusion

from core.development import normalized, touch_point

Vector = Tuple[float, float, float]

PLANE_NAME = "PatternCreator Tangente"
POINT_NAME = "PatternCreator Berührpunkt"

#: Toleranz, mit der eine Flaeche als "dieselbe" gilt (cm).
RADIUS_TOL = 1e-6


class TargetError(Exception):
    """Klartext-Fehler fuer den Editor."""


# ------------------------------------------------------- Tangentialebene

def ensure_tangent_plane(design: Any, comp: Any,
                         development: dict) -> Tuple[Any, Tuple[str, ...]]:
    """Tangentialebene zum Nahtwinkel. Liefert ``(Ebene, veraltete Tokens)``.

    Passt die vorhandene Ebene noch, wird sie weiterverwendet - das ist der
    Normalfall beim Bearbeiten, und dann ist hier nichts zu tun.

    Ist der Nahtwinkel gewandert, entsteht eine neue Ebene, die alte wird aber
    **nicht** geloescht: auf ihr liegt noch die Skizze des Musters. Ihre Tokens
    gehen an den Aufrufer zurueck, der sie wegraeumt, sobald die Skizze
    umgezogen ist. Die Reihenfolge im Rueckgabewert ist Punkt, dann Ebene -
    ``remove`` loescht rueckwaerts, also zuerst die Ebene und dann den Punkt,
    an dem sie haengt.
    """
    face = target_face(design, development)
    if face is None:
        raise TargetError("Die Mantelfläche ist nicht mehr auffindbar. Bitte "
                          "das Muster neu erzeugen.")
    origin, axis = axis_of(face)
    wanted = touch_point(development, origin, axis)

    existing = _by_token(design, development.get("planeToken"))
    if existing is not None and _touches(existing, wanted):
        return existing, ()

    stale: Tuple[str, ...] = ()
    if existing is not None:
        stale = tuple(token for token in (development.get("pointToken"),
                                          development.get("planeToken"))
                      if token)
    plane, point = _tangent_plane(comp, face, wanted)
    development["pointToken"] = _token(point)
    development["planeToken"] = _token(plane)
    return plane, stale


def _tangent_plane(comp: Any, face: Any, where: Vector) -> Tuple[Any, Any]:
    point = _point_entity(comp, where)
    planes = comp.constructionPlanes
    try:
        inp = planes.createInput()
        inp.setByTangentAtPoint(face, point)
        plane = planes.add(inp)
    except Exception as exc:
        raise TargetError("Die Tangentialebene ließ sich nicht anlegen: %s" % exc)
    plane.name = PLANE_NAME
    return plane, point


def _point_entity(comp: Any, where: Vector) -> Any:
    """Konstruktionspunkt am Beruehrpunkt - ``setByTangentAtPoint`` braucht einen."""
    location = adsk.core.Point3D.create(where[0], where[1], where[2])
    try:
        points = comp.constructionPoints
        inp = points.createInput()
        inp.setByPoint(location)
        point = points.add(inp)
        point.name = POINT_NAME
        return point
    except Exception:
        pass
    # Rueckfall: ein Skizzenpunkt tut es auch. Die Skizze bleibt stehen, weil
    # die Ebene auf ihren Punkt verweist.
    sketch = comp.sketches.add(comp.xYConstructionPlane)
    sketch.name = POINT_NAME
    sketch.isVisible = False
    return sketch.sketchPoints.add(sketch.modelToSketchSpace(location))


def _touches(plane: Any, where: Vector, tol: float = 1e-6) -> bool:
    """Beruehrt diese Ebene die Flaeche genau an diesem Punkt?

    Verglichen wird **nicht** der Ursprung der Ebene: den legt Fusion irgendwo
    auf die Ebene, nicht auf den Beruehrpunkt (gemessen: Beruehrpunkt
    (25|0|30) mm, Ebenenursprung (-25|0|60) mm - Spike 2.0, Abschnitt 2).
    Der Ursprungsvergleich schlug deshalb **immer** fehl, und jedes Bearbeiten
    legte eine neue Ebene an, obwohl sich am Nahtwinkel nichts geaendert hatte.

    Richtig ist der Abstand des Punktes zur Ebene: ein Punkt der Mantelflaeche
    liegt genau dann auf der Tangentialebene, wenn er ihr Beruehrpunkt ist -
    die Ebene beruehrt die Flaeche ja nur entlang dieser einen Mantellinie.
    """
    try:
        geometry = plane.geometry
        origin = geometry.origin
        normal = geometry.normal
    except Exception:
        return False
    offset = (where[0] - origin.x, where[1] - origin.y, where[2] - origin.z)
    return abs(offset[0] * normal.x + offset[1] * normal.y
               + offset[2] * normal.z) < tol


# ----------------------------------------------------------- Lage im Doc

def sketch_placement(sketch: Any, development: dict, face: Any) -> Dict[str, float]:
    """Wie die Abwicklung auf der Skizze liegen muss.

    Gemessen statt geraten: die Achsenrichtung und die Umfangsrichtung am
    Beruehrpunkt werden in Skizzenkoordinaten umgerechnet. Die Abwicklung hat
    x in Umfangsrichtung und y entlang der Achse - daraus folgen Drehung und
    Ursprung unmittelbar.
    """
    origin, axis = axis_of(face)
    where = touch_point(development, origin, axis)
    radial = _radial(where, origin, axis)
    around = _cross(axis, radial)                # Umfangsrichtung (wachsendes theta)

    base, along_axis, along_theta = _measure(sketch, where, axis, around)

    # Die Abwicklung zaehlt ihr y **vom Apex weg**. Beim Zylinder ist das die
    # Achsrichtung; beim Kegel die Gegenrichtung, wenn die Flaeche entgegen der
    # Achse weiter wird. Das Vorzeichen des Halbwinkels sagt welche
    # (Context.md 15.14) - stuende es falsch, laege das Muster kopfueber.
    if float(development.get("halfAngle", 0.0)) < 0.0:
        along_axis = (-along_axis[0], -along_axis[1])

    handedness = along_theta[0] * along_axis[1] - along_theta[1] * along_axis[0]
    if handedness <= 0.0:
        # Waere die Skizze gespiegelt, liesse sich die Abwicklung nicht durch
        # eine Drehung auflegen - Text stuende seitenverkehrt auf dem Teil.
        # Gemessen ist der Fall nicht aufgetreten; kommt er vor, soll er
        # auffallen und nicht still schieflaufen.
        raise TargetError("Die Tangentialebene liegt spiegelverkehrt zur "
                          "Fläche. Bitte melden - das Muster wäre spiegelbildlich.")
    return {
        "originX": base[0],
        "originY": base[1],
        "rotation": math.degrees(math.atan2(along_theta[1], along_theta[0])),
    }


def axis_of(face: Any) -> Tuple[Vector, Vector]:
    """Ursprung und Einheitsvektor der Flaechenachse."""
    cylinder = adsk.core.Cylinder.cast(face.geometry)
    if cylinder:
        ok, origin, axis, _radius = cylinder.getData()
    else:
        cone = adsk.core.Cone.cast(face.geometry)
        if not cone:
            raise TargetError("Die Fläche ist keine Mantelfläche mehr.")
        ok, origin, axis, _radius, _half = cone.getData()
    if not ok:
        raise TargetError("Die Mantelfläche lässt sich nicht auswerten.")
    return ((origin.x, origin.y, origin.z),
            normalized((axis.x, axis.y, axis.z)))


def _radial(point: Vector, origin: Vector, axis: Vector) -> Vector:
    v = tuple(point[i] - origin[i] for i in range(3))
    along = sum(v[i] * axis[i] for i in range(3))
    return normalized(tuple(v[i] - along * axis[i] for i in range(3)))


def _cross(a: Vector, b: Vector) -> Vector:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _shift(point: Vector, direction: Vector, distance: float = 1.0) -> Vector:
    return tuple(point[i] + distance * direction[i] for i in range(3))


def _measure(sketch: Any, where: Vector, axis: Vector, around: Vector):
    """Beruehrpunkt und die beiden Richtungen in Skizzenkoordinaten.

    Erst ueber ``modelToSketchSpace`` (der Weg aus dem Spike), und wenn dabei
    etwas Entartetes herauskommt, ueber die Transformation der Skizze. Zwei Wege,
    weil der erste an einer frisch umdefinierten Skizze schon einmal zwei um
    einen Zentimeter entfernte Punkte auf denselben Skizzenpunkt abgebildet hat.
    """
    try:
        base = _to_sketch(sketch, where)
        along_axis = _unit(base, _to_sketch(sketch, _shift(where, axis)))
        along_theta = _unit(base, _to_sketch(sketch, _shift(where, around)))
        if along_axis is not None and along_theta is not None:
            return base, along_axis, along_theta
    except Exception:
        pass

    frame = _sketch_frame(sketch)
    if frame is None:
        raise TargetError("Die Skizze lässt sich nicht auf der Fläche "
                          "ausrichten - bitte das Muster neu erzeugen.")
    origin, ex, ey = frame
    offset = tuple(where[i] - origin[i] for i in range(3))
    base = (_dot(offset, ex), _dot(offset, ey))
    along_axis = _unit((0.0, 0.0), (_dot(axis, ex), _dot(axis, ey)))
    along_theta = _unit((0.0, 0.0), (_dot(around, ex), _dot(around, ey)))
    if along_axis is None or along_theta is None:
        raise TargetError("Die Skizze steht senkrecht auf der Fläche - bitte "
                          "das Muster neu erzeugen.")
    return base, along_axis, along_theta


def _sketch_frame(sketch: Any):
    """Ursprung und die beiden Achsen der Skizze im Modell."""
    try:
        m = sketch.transform.asArray()
    except Exception:
        return None
    origin = (m[3], m[7], m[11])
    return origin, (m[0], m[4], m[8]), (m[1], m[5], m[9])


def _dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _to_sketch(sketch: Any, point: Vector) -> Tuple[float, float]:
    p = sketch.modelToSketchSpace(adsk.core.Point3D.create(*point))
    return (p.x, p.y)


def _unit(a: Tuple[float, float], b: Tuple[float, float]):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return None if length < 1e-9 else (dx / length, dy / length)


# -------------------------------------------------------------- Praegung

def is_available(comp: Any) -> bool:
    """Kennt diese Fusion-Version die Praegung?"""
    return _emboss_features(comp) is not None


def _emboss_features(comp: Any):
    try:
        return comp.features.embossFeatures
    except Exception:
        return None


def emboss(design: Any, comp: Any, sketch: Any, development: dict,
           depth: float, previous: Sequence[str] = ()) -> List[str]:
    """Muster auf die Flaeche praegen. Liefert die Tokens der Features.

    Vorhandene Praegungen werden vorher geloescht: nach dem Neuzeichnen der
    Skizze findet ein bestehendes Emboss sein Profil nicht wieder und rechnet
    mit zwischengespeicherter Geometrie weiter (``Context.md`` 15.6, Punkt 7).
    """
    features = _emboss_features(comp)
    if features is None:
        raise TargetError("Diese Fusion-Version kennt „Prägen“ nicht. Das "
                          "Muster liegt als Skizze auf der Tangentialebene.")
    remove(design, previous)

    wanted = 2 if development.get("periodic") else 1
    profiles = material_profiles(sketch, wanted)
    if not profiles:
        raise TargetError("In der Skizze ist kein prägbares Profil - „Prägen“ "
                          "braucht das Flächenmodell (Modus „Flächen“, Füllung "
                          "„Stege“, Rahmen an).")
    if len(profiles) < wanted:
        raise TargetError("Für eine rundum laufende Prägung fehlt die "
                          "Trennlinie; Fusion lehnt ein Profil über volle "
                          "360° ab.")
    texts = [sketch.sketchTexts.item(i) for i in range(sketch.sketchTexts.count)]

    tokens: List[str] = []
    body_name = None
    for index, profile in enumerate(profiles):
        # Die Flaeche vor **jedem** Emboss frisch holen: nach dem ersten ist die
        # alte Referenz ungueltig. Ab dem zweiten Durchgang nur noch im selben
        # Koerper suchen - dort stehen nach dem Praegen tausende Flaechen, und
        # ein gleich grosser Zylinder woanders im Dokument waere ein Fehlgriff.
        face = target_face(design, development, body_name)
        if body_name is None and face is not None:
            try:
                body_name = face.body.name
            except Exception:
                body_name = None
        if face is None:
            raise TargetError("Die Mantelfläche ist nach dem Prägen nicht mehr "
                              "auffindbar.")
        try:
            inp = features.createInput(
                [profile] + (texts if index == 0 else []), [face],
                adsk.core.ValueInput.createByReal(depth))
            inp.isTangentChain = False
            feature = features.add(inp)
        except Exception as exc:
            remove(design, tokens)
            raise TargetError("Die Prägung ist fehlgeschlagen: %s" % exc)
        if getattr(feature, "healthState", 0) != 0:
            message = ""
            try:
                message = feature.errorOrWarningMessage or ""
            except Exception:
                pass
            remove(design, tokens + [_token(feature)])
            raise TargetError("Fusion konnte das Muster nicht prägen. %s" % message)
        tokens.append(_token(feature))
    return tokens


def material_profiles(sketch: Any, wanted: int) -> List[Any]:
    """Die Profile, die das Stegnetz sind - nicht die Loecher darin.

    Sortiert wird nach der Groesse des Huellrechtecks. ``areaProperties`` waere
    naeher an der Anschauung, kostet aber je Aufruf eine eigene
    Flaechenberechnung - bei tausend Loechern summiert sich das. Und es waere
    sogar falscher: bei duennen Stegen hat ein grosses Loch mehr **Flaeche** als
    das ganze Stegnetz. Das Huellrechteck kennt diese Falle nicht, denn jedes
    Loch liegt im Stegnetz und sein Rechteck damit in dessen Rechteck.
    """
    scored = []
    for i in range(sketch.profiles.count):
        profile = sketch.profiles.item(i)
        scored.append((_extent(profile), i, profile))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:max(1, wanted)]]


def _extent(profile: Any) -> float:
    """Flaeche des Huellrechtecks eines Profils (0.0, wenn unbekannt)."""
    try:
        box = profile.boundingBox
        return ((box.maxPoint.x - box.minPoint.x)
                * (box.maxPoint.y - box.minPoint.y))
    except Exception:
        return 0.0


def target_face(design: Any, development: dict,
                body_name: Optional[str] = None) -> Optional[Any]:
    """Die Mantelflaeche - ueber den Token, sonst ueber den Radius.

    Nach dem ersten Praegen ist der Token oft wertlos (die Flaeche wurde
    geteilt) und die Oberseite der Praegung ist selbst eine Zylinderflaeche.
    Gesucht wird deshalb die groesste Flaeche mit dem **urspruenglichen**
    Radius.
    """
    radius = float(development.get("radius", 0.0))
    token = (development.get("source") or {}).get("token", "")
    face = _by_token(design, token)
    if face is not None and _radius_of(face) is not None \
            and abs(_radius_of(face) - radius) < RADIUS_TOL:
        return face
    best = None
    best_area = -1.0
    for body in _bodies(design):
        if body_name is not None and body.name != body_name:
            continue
        for candidate in body.faces:
            found = _radius_of(candidate)
            if found is None or abs(found - radius) >= RADIUS_TOL:
                continue
            try:
                area = candidate.area
            except Exception:
                area = 0.0
            if area > best_area:
                best, best_area = candidate, area
    return best


def _radius_of(face: Any) -> Optional[float]:
    try:
        geometry = face.geometry
    except Exception:
        return None
    cylinder = adsk.core.Cylinder.cast(geometry)
    if cylinder:
        ok, _origin, _axis, radius = cylinder.getData()
        return float(radius) if ok else None
    cone = adsk.core.Cone.cast(geometry)
    if cone:
        ok, _origin, _axis, radius, _half = cone.getData()
        return float(radius) if ok else None
    return None


def _bodies(design: Any):
    try:
        for comp in design.allComponents:
            for body in comp.bRepBodies:
                yield body
    except Exception:
        return


def remove(design: Any, tokens: Sequence[str]) -> None:
    """Features zu diesen Tokens loeschen - rueckwaerts, wie in der Timeline.

    Rueckwaerts, weil das spaetere Feature auf dem frueheren aufbaut: erst die
    Praegung, dann ihre Skizze; erst die Ebene, dann ihr Beruehrpunkt.
    """
    for token in reversed(list(tokens or ())):
        feature = _by_token(design, token)
        _delete(feature)


def find_entity(design: Any, token: Optional[str]) -> Any:
    """Entity zu einem gespeicherten Token - ``None``, wenn es sie nicht mehr gibt."""
    return _by_token(design, token)


def _by_token(design: Any, token: Optional[str]) -> Any:
    if not token:
        return None
    try:
        found = design.findEntityByToken(str(token))
    except Exception:
        return None
    for entity in found or ():
        return entity
    return None


def _token(entity: Any) -> str:
    try:
        return str(entity.entityToken or "")
    except Exception:
        return ""


def _delete(entity: Any) -> None:
    if entity is None:
        return
    try:
        entity.deleteMe()
    except Exception:
        pass
