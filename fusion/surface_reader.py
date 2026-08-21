"""Mantelflaeche aus Fusion lesen: Zylinder oder Kegel.

Wie beim Rahmen (``fusion/frame_reader.py``) ist das Ergebnis ein
**Schnappschuss**: im PatternDoc stehen hinterher nur Zahlen (Radius, Laenge,
Oeffnungswinkel, Nahtwinkel) und der Entity-Token. Ein Re-Edit braucht die
Flaeche nur noch, um die Skizze zu platzieren und zu praegen.

Die Rechnung liegt in ``core/development.py`` und ist damit ohne Fusion
pruefbar; hier bleibt die API-Arbeit: Geometrie abfragen, Kanten abtasten,
Weltpunkte einsammeln.

Zwei Dinge aus dem Spike (``Context.md`` 15.6), die man der API nicht ansieht:

* Eine volle Mantelflaeche hat **zwei** Aussen-Loops mit je einer Kreiskante und
  gar keine Mantellinie. Die Annahme aus Phase 1 („genau ein ``isOuter``-Loop")
  gilt hier nicht.
* Flaechen-Referenzen veralten nach jedem Feature. Deshalb wird hier nichts
  gemerkt, was ueber den Commit hinaus gebraucht wuerde - nur der Token.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

import adsk.core
import adsk.fusion

from core.development import (KIND_CONE, KIND_CYLINDER, PERIODIC_TOL, axis_frame,
                              describe, normalized, surface_coords,
                              theta_coverage, touch_point, unwrap_angles,
                              usable_span)
from core.optimize import TOL

Point = Tuple[float, float]
Vector = Tuple[float, float, float]

#: Abtast-Toleranz fuer die Randkurven (cm) - dieselbe wie beim Rahmen.
STROKE_TOL = TOL


class SurfaceError(Exception):
    """Klartext-Fehler fuer den Editor - nie selbst eine ``messageBox`` zeigen."""


class SurfaceSnapshot:
    """Ergebnis von :func:`read_surface`: Zahlen fuer das Doc plus die Achse."""

    def __init__(self, development: dict, face: Any, origin: Vector, axis: Vector):
        self.development = development
        self.face = face
        self.origin = origin          # Punkt auf der Achse (Welt, cm)
        self.axis = axis              # Einheitsvektor der Achse (Welt)

    @property
    def label(self) -> str:
        return self.development["source"]["label"]

    def touch_point(self, seam_angle: Optional[float] = None) -> Vector:
        """Punkt, an dem die Tangentialebene anliegen soll (Welt, cm)."""
        return touch_point(self.development, self.origin, self.axis, seam_angle)


# --------------------------------------------------------------- Erkennung

def is_surface(entity: Any) -> bool:
    """Ist die Auswahl eine Zylinder- oder Kegelmantelflaeche?"""
    return _curved_face(entity) is not None


def _curved_face(entity: Any):
    try:
        face = adsk.fusion.BRepFace.cast(entity)
    except Exception:
        return None
    if face is None:
        return None
    try:
        geometry = face.geometry
    except Exception:
        return None
    if adsk.core.Cylinder.cast(geometry) or adsk.core.Cone.cast(geometry):
        return face
    return None


# ------------------------------------------------------------------ Lesen

def read_surface(entity: Any) -> SurfaceSnapshot:
    """Mantelflaeche einlesen. Wirft :class:`SurfaceError` mit Klartext."""
    face = _curved_face(entity)
    if face is None:
        raise SurfaceError("Bitte eine zylindrische oder konische Mantelfläche "
                           "wählen. Kugeln, Tori und Freiformflächen lassen "
                           "sich nicht abwickeln.")

    kind, origin, axis, radius, half_angle = _geometry(face)
    world = _loop_points(face)
    frame = axis_frame(axis)
    loops = [surface_coords(points, origin, axis, frame)
             for points in world if len(points) >= 2]
    if not loops:
        raise SurfaceError("Die Fläche hat keine auswertbaren Randkurven.")
    if kind == KIND_CONE:
        # Welche Richtung die Flaeche weiter wird, sagt die Geometrie selbst -
        # nicht das Vorzeichen aus ``getData``. Ein geratenes Vorzeichen haette
        # das Muster auf den Kopf gestellt.
        half_angle = math.copysign(half_angle,
                                   _taper(_flat(world), origin, axis) or 1.0)

    periodic = _is_full_wrap(loops)
    if periodic:
        span = usable_span([_span(loop) for loop in loops])
        if span is None:
            raise SurfaceError("Die Randkurven der Fläche liegen nicht "
                               "auseinander - die Fläche ist zu schmal.")
        low, high = span
        outline: List[List[float]] = []
    else:
        biggest = max(loops, key=_extent)
        low = min(p[1] for p in biggest)
        high = max(p[1] for p in biggest)
        outline = _centred(biggest, (low + high) / 2.0)
    if high - low <= 1e-9:
        raise SurfaceError("Die Fläche ist zu schmal für ein Muster.")

    middle = (low + high) / 2.0
    length = high - low
    if kind == KIND_CONE:
        # Der Radius der Flaechengeometrie gilt an ``origin``; gebraucht wird er
        # auf der Beruehrlinie, also in der Mitte der Flaeche - dort hat die
        # Abwicklung ihren Nullpunkt.
        radius = radius + middle * math.tan(half_angle)
        if radius <= 1e-9:
            raise SurfaceError("Die Fläche läuft in die Spitze des Kegels - "
                               "bitte einen Kegelstumpf wählen.")
        # Gemessen wird entlang der **Mantellinie**, nicht entlang der Achse:
        # das Muster liegt auf der Flaeche, nicht daneben.
        length = length / math.cos(abs(half_angle))

    development = {
        "kind": kind,
        "radius": radius,
        "halfAngle": half_angle,
        "length": length,
        "periodic": periodic,
        "seamAngle": 0.0,
        "outline": outline,
        "axisMiddle": middle,
        "source": {"label": "", "token": _token_of(face)},
    }
    development["source"]["label"] = "%s – %s" % (_face_label(face),
                                                  describe(development))
    return SurfaceSnapshot(development, face, origin, normalized(axis))


def _geometry(face) -> Tuple[str, Vector, Vector, float, float]:
    """Art, Achse und Masse der Flaeche - aus ``getData``, nicht aus Attributen."""
    cylinder = adsk.core.Cylinder.cast(face.geometry)
    if cylinder:
        ok, origin, axis, radius = cylinder.getData()
        if not ok:
            raise SurfaceError("Die Zylinderfläche lässt sich nicht auswerten.")
        return (KIND_CYLINDER, _xyz(origin), _xyz(axis), float(radius), 0.0)
    cone = adsk.core.Cone.cast(face.geometry)
    ok, origin, axis, radius, half_angle = cone.getData()
    if not ok:
        raise SurfaceError("Die Kegelfläche lässt sich nicht auswerten.")
    return (KIND_CONE, _xyz(origin), _xyz(axis), float(radius),
            abs(float(half_angle)))


def _xyz(p) -> Vector:
    return (p.x, p.y, p.z)


def _loop_points(face) -> List[List[Vector]]:
    """Jede Randkurve als Weltpunkte."""
    out: List[List[Vector]] = []
    for loop in face.loops:
        world: List[Vector] = []
        for co_edge in loop.coEdges:
            world.extend(_strokes(co_edge.edge))
        out.append(world)
    return out


def _flat(loops: Sequence[Sequence[Vector]]) -> List[Vector]:
    return [p for loop in loops for p in loop]


def _taper(points: Sequence[Vector], origin: Vector, axis: Vector) -> float:
    """Wie stark waechst der Radius entlang der Achse? (Ausgleichsgerade)

    Beim Kegel ist der Radius **linear** in der Achslage, die Gerade trifft also
    exakt; der Ausgleich glaettet nur das Abtastrauschen der Randkurven. Das
    Vorzeichen des Ergebnisses ist die eigentliche Auskunft: es sagt, auf
    welcher Seite der Apex liegt.
    """
    a = normalized(axis)
    samples = []
    for p in points:
        v = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
        s = sum(v[i] * a[i] for i in range(3))
        radial = tuple(v[i] - s * a[i] for i in range(3))
        samples.append((s, math.sqrt(sum(c * c for c in radial))))
    if len(samples) < 2:
        return 0.0
    n = float(len(samples))
    mean_s = sum(s for s, _ in samples) / n
    mean_r = sum(r for _, r in samples) / n
    spread = sum((s - mean_s) ** 2 for s, _ in samples)
    if spread <= 1e-12:
        return 0.0
    return sum((s - mean_s) * (r - mean_r) for s, r in samples) / spread


def _strokes(edge) -> List[Vector]:
    evaluator = getattr(edge, "evaluator", None)
    if evaluator is None:
        raise SurfaceError("Eine Randkurve lässt sich nicht auswerten.")
    ok, t0, t1 = evaluator.getParameterExtents()
    if not ok:
        raise SurfaceError("Eine Randkurve lässt sich nicht auswerten.")
    ok, points = evaluator.getStrokes(t0, t1, STROKE_TOL)
    if not ok or not points:
        raise SurfaceError("Eine Randkurve lässt sich nicht abtasten.")
    return [_xyz(p) for p in points]


def _is_full_wrap(loops: Sequence[Sequence[Point]]) -> bool:
    """Laeuft die Flaeche rundum?

    Kriterium aus dem Spike: eine volle Mantelflaeche hat zwei Randkurven, die
    **jede** einmal um die Achse laufen (``Context.md`` 15.6, Punkt 8). Ein
    Halbzylinder hat dagegen eine einzige Randkurve, und die deckt nur den
    halben Winkel ab. Gemessen wird der Winkel und nicht die Kantenart: ein
    schraeg abgeschnittener Zylinder laeuft ebenfalls rundum, seine Randkurve
    ist aber eine Ellipse und keine Kreiskante.
    """
    if len(loops) < 2:
        return False
    return all(theta_coverage([p[0] for p in loop]) >= 2.0 * math.pi - PERIODIC_TOL
               for loop in loops)


def _span(loop: Sequence[Point]) -> Tuple[float, float]:
    return (min(p[1] for p in loop), max(p[1] for p in loop))


def _extent(loop: Sequence[Point]) -> float:
    lo, hi = _span(loop)
    return (hi - lo) * theta_coverage([p[0] for p in loop])


def _centred(loop: Sequence[Point], middle: float) -> List[List[float]]:
    """Kontur um ihre Mitte legen - der Rahmen sitzt im Doc immer bei 0/0."""
    thetas = unwrap_angles([p[0] for p in loop])
    shift = (min(thetas) + max(thetas)) / 2.0
    return [[thetas[i] - shift, loop[i][1] - middle] for i in range(len(loop))]


def _face_label(face) -> str:
    try:
        body = face.body
        return "%s / Fläche %d" % (body.name, list(body.faces).index(face) + 1)
    except Exception:
        return "Fläche"


def _token_of(entity: Any) -> str:
    try:
        token = entity.entityToken
        if token:
            return str(token)
    except Exception:
        pass
    return ""


def find_surface(token: str, design: Any = None) -> Optional[Any]:
    """Flaeche zu einem gespeicherten Token suchen (Re-Edit, Praegen).

    Flaechen-Referenzen veralten nach jedem Feature (``Context.md`` 15.6,
    Punkt 10) - deshalb wird die Flaeche vor jedem Zugriff neu gesucht statt
    einmal gemerkt.
    """
    if not token:
        return None
    design = design or _design()
    try:
        found = design.findEntityByToken(token)
    except Exception:
        return None
    for entity in found or ():
        if _curved_face(entity) is not None:
            return entity
    return None


def _design():
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise SurfaceError("Kein Konstruktionsdokument aktiv.")
    return design
