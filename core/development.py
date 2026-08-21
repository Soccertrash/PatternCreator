"""Abwicklung: Mantelflaeche -> Ebene. Reine Mathematik, kein ``adsk``.

Fusions Emboss bildet eine Skizze auf einer Tangentialebene auf die Mantelflaeche
ab. Gemessen (``Context.md`` 15.6): die Abbildung ist **laengentreu** - eine
Strecke von 20 mm in Skizzen-x wird zu 20,000 mm **Bogenlaenge** auf dem
Zylinder, nicht zur Sehne (19,471 mm). Genau das erlaubt es, das Muster in der
Ebene zu erzeugen und Fusion das Wickeln zu ueberlassen.

Koordinaten der Flaeche sind ``(theta, s)``:

* ``theta`` - Winkel um die Achse (Bogenmass), 0 auf der Beruehrlinie der
  Tangentialebene,
* ``s`` - Lage entlang der Achse, gemessen **von der Mitte** der Flaeche.

Die Abwicklung eines Zylinders ist damit das Rechteck
``[-pi*r, pi*r] x [-L/2, L/2]``; ``x = 0`` ist die Beruehrlinie, die Naht liegt
bei ``x = +-pi*r``.

**Der Kegel** wickelt sich als Kreisringsektor ab - gemessen, nicht geraten
(``Context.md`` 15.6, Punkt 4: der Abstand zum Apex bleibt erhalten, der Winkel
wird um ``sin(alpha)`` gestaucht). Das Ueberraschende daran: in den Koordinaten
dieses Moduls sieht der Kegel **genauso aus wie der Zylinder**. Mit ``radius``
als Radius auf der Beruehrlinie und ``y`` als Weg entlang der Mantellinie gilt
fuer beide

    x = radius * theta,   Periode = 2*pi*radius

Der Unterschied steckt allein im letzten Schritt: die fertige Szene wird beim
Kegel noch in den Sektor gebogen (``core/warp.py``). Generatoren, Naht,
Behaelter und Flaechenmodell merken davon nichts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]

KIND_CYLINDER = "cylinder"
KIND_CONE = "cone"

#: Groesster Sprung zwischen zwei Konturpunkten, der noch als Verlauf gilt.
#: Alles darueber ist ein Umlauf ueber die Naht und wird entrollt.
UNWRAP_JUMP = math.pi

#: Ab dieser Ueberdeckung gilt eine Kontur als rundum laufend (Bogenmass).
PERIODIC_TOL = 1e-3


@dataclass
class Development:
    """Beschreibung einer abwickelbaren Mantelflaeche.

    ``radius``    Der Radius auf der Beruehrlinie, also in der Mitte der
                  Flaeche. Beim Kegel ist das **nicht** der Radius an der
                  Flaechengeometrie - der Leser rechnet ihn um.
    ``half_angle`` Kegel: halber Oeffnungswinkel (rad), **mit Vorzeichen**:
                  positiv, wenn die Flaeche in Achsrichtung weiter wird, also
                  wenn der Apex entgegen der Achse liegt. Zylinder: 0.
    ``length``    Zylinder: axiale Laenge. Kegel: Laenge der Mantellinie.
    ``periodic``  Laeuft die Flaeche rundum?
    """

    kind: str = KIND_CYLINDER
    radius: float = 1.0
    half_angle: float = 0.0
    length: float = 1.0
    periodic: bool = False

    # -- Abbildung -------------------------------------------------------
    def to_plane(self, theta: float, s: float) -> Point:
        """Flaechenkoordinaten ``(theta, s)`` -> Abwicklung ``(x, y)``.

        ``s`` ist der axiale Abstand von der Mitte der Flaeche. Beim Kegel wird
        daraus der Weg entlang der **Mantellinie** - laenger als der axiale Weg,
        und entgegengesetzt gezaehlt, wenn der Apex in Achsrichtung liegt.
        Die Umfangsrichtung ist bei beiden dieselbe Formel.
        """
        if self.kind == KIND_CYLINDER:
            return (self.radius * theta, s)
        alpha = abs(self.half_angle)
        away = 1.0 if self.half_angle >= 0.0 else -1.0
        return (self.radius * theta, away * s / math.cos(alpha))

    def period(self) -> float:
        """Breite eines vollen Umlaufs in der Abwicklung.

        Beim Kegel ist das die Breite des **Rechtecks vor dem Biegen**: der
        Sektor ueberstreicht ``2*pi*sin(alpha)`` bei einem Apex-Abstand von
        ``radius / sin(alpha)`` - das Produkt ist wieder ``2*pi*radius``.
        """
        return 2.0 * math.pi * self.radius

    # -- Kegel -----------------------------------------------------------
    def is_cone(self) -> bool:
        return self.kind == KIND_CONE and abs(self.half_angle) > 1e-12

    def apex_distance(self) -> float:
        """Abstand Beruehrlinie -> Apex entlang der Mantellinie."""
        if not self.is_cone():
            return 0.0
        return self.radius / math.sin(abs(self.half_angle))

    def sector_angle(self) -> float:
        """Winkel, den die volle Abwicklung als Kreisringsektor ueberstreicht."""
        if not self.is_cone():
            return 0.0
        return 2.0 * math.pi * math.sin(abs(self.half_angle))

    def bounds(self) -> Tuple[float, float, float, float]:
        """Rechteck der vollen Abwicklung (nur sinnvoll bei ``periodic``)."""
        half_x = self.period() / 2.0
        half_y = self.length / 2.0
        return (-half_x, -half_y, half_x, half_y)

    def frame_points(self, outline: Sequence[Point]) -> List[Point]:
        """Kontur in Flaechenkoordinaten -> Kontur in der Abwicklung.

        Die ``theta``-Werte werden vorher entrollt: eine Kontur, die die Naht
        kreuzt, springt sonst um 2*pi und die Abwicklung faltet sich zusammen.
        """
        if not outline:
            return []
        thetas = unwrap_angles([p[0] for p in outline])
        return [self.to_plane(theta, outline[i][1])
                for i, theta in enumerate(thetas)]


# ------------------------------------------------------------------ Winkel

def unwrap_angles(thetas: Sequence[float]) -> List[float]:
    """Spruenge ueber die Naht herausrechnen (wie ``numpy.unwrap``).

    Aufeinanderfolgende Werte mit einem Sprung groesser als
    :data:`UNWRAP_JUMP` werden um Vielfache von 2*pi korrigiert.
    """
    out: List[float] = []
    offset = 0.0
    previous = None
    for theta in thetas:
        value = float(theta) + offset
        if previous is not None:
            while value - previous > UNWRAP_JUMP:
                offset -= 2.0 * math.pi
                value -= 2.0 * math.pi
            while previous - value > UNWRAP_JUMP:
                offset += 2.0 * math.pi
                value += 2.0 * math.pi
        out.append(value)
        previous = value
    return out


def theta_coverage(thetas: Sequence[float]) -> float:
    """Wie viel Winkel deckt eine Kontur ab (nach dem Entrollen)?"""
    if len(thetas) < 2:
        return 0.0
    unwrapped = unwrap_angles(thetas)
    return max(unwrapped) - min(unwrapped)


def is_periodic(outline: Sequence[Point], tol: float = PERIODIC_TOL) -> bool:
    """Laeuft die Kontur rundum?

    Kriterium aus dem Plan: die theta-Ueberdeckung erreicht 2*pi. Ob ein
    Konturstueck entlang einer Mantellinie laeuft, entscheidet der Leser in
    ``fusion/`` anhand der Kantenarten - gemessen wurde, dass eine volle
    Mantelflaeche **zwei** Aussen-Loops mit je einer Kreiskante hat und gar
    keine Mantellinie (``Context.md`` 15.6, Punkt 8).
    """
    return theta_coverage([p[0] for p in outline]) >= 2.0 * math.pi - tol


# ------------------------------------------------------- Flaeche -> Koordinaten

Vector = Tuple[float, float, float]


def normalized(v: Vector) -> Vector:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length <= 1e-12:
        raise ValueError("Richtungsvektor der Länge 0.")
    return (v[0] / length, v[1] / length, v[2] / length)


def axis_frame(axis: Vector) -> Tuple[Vector, Vector]:
    """Zwei Einheitsvektoren senkrecht zur Achse, als Bezug fuer den Winkel.

    Fusion liefert zu einer Zylinderflaeche nur Ursprung, Achse und Radius -
    eine Null-Richtung gibt es nicht. Sie wird hier **deterministisch** aus der
    Achse gebaut (kleinste Komponente als Startvektor, damit er nie parallel
    liegt), damit derselbe Koerper in jeder Sitzung denselben Bezug bekommt.
    Der Nahtwinkel im Dokument zaehlt ab dieser Richtung.
    """
    a = normalized(axis)
    smallest = min(range(3), key=lambda i: abs(a[i]))
    helper = [0.0, 0.0, 0.0]
    helper[smallest] = 1.0
    along = dot3(tuple(helper), a)
    e1 = normalized((helper[0] - along * a[0], helper[1] - along * a[1],
                     helper[2] - along * a[2]))
    return e1, cross3(a, e1)


def cross3(a: Vector, b: Vector) -> Vector:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot3(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def surface_coords(points: Sequence[Vector], origin: Vector, axis: Vector,
                   frame: Optional[Tuple[Vector, Vector]] = None) -> List[Point]:
    """Weltpunkte -> ``(theta, s)`` auf der Mantelflaeche.

    ``s`` ist die Lage entlang der Achse, gemessen ab ``origin``; ``theta`` der
    Winkel um die Achse, gezaehlt ab der ersten Achse von :func:`axis_frame`.
    """
    a = normalized(axis)
    e1, e2 = frame if frame is not None else axis_frame(a)
    out: List[Point] = []
    for p in points:
        v = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
        s = dot3(v, a)
        radial = (v[0] - s * a[0], v[1] - s * a[1], v[2] - s * a[2])
        out.append((math.atan2(dot3(radial, e2), dot3(radial, e1)), s))
    return out


def usable_span(loop_spans: Sequence[Tuple[float, float]]
                ) -> Optional[Tuple[float, float]]:
    """Groesstes Achsenstueck, das **jede** Randkurve freilaesst.

    Ein schraeg abgeschnittener Zylinder laeuft rundum, ist aber kein Rechteck:
    seine obere Randkurve schwankt. Das Muster bekommt deshalb nur das Stueck,
    das ueberall auf der Flaeche liegt - der Rest bliebe sonst in der Luft.
    Ein gerade abgeschnittener Zylinder verliert dabei nichts.
    """
    spans = [(float(lo), float(hi)) for lo, hi in loop_spans if hi >= lo]
    if len(spans) < 2:
        return None
    middle = (min(sp[0] for sp in spans) + max(sp[1] for sp in spans)) / 2.0
    lower = [sp for sp in spans if (sp[0] + sp[1]) / 2.0 <= middle]
    upper = [sp for sp in spans if (sp[0] + sp[1]) / 2.0 > middle]
    if not lower or not upper:
        return None
    low = max(sp[1] for sp in lower)
    high = min(sp[0] for sp in upper)
    return (low, high) if high - low > 1e-9 else None


def touch_point(development: dict, origin: Vector, axis: Vector,
                seam_angle: Optional[float] = None) -> Vector:
    """Punkt auf der Flaeche, an dem die Tangentialebene anliegen soll.

    Der Nahtwinkel sagt, wo die **Naht** sitzt; beruehrt wird die Flaeche
    gegenueber - die Naht liegt am Rand der Abwicklung, die Beruehrlinie in
    deren Mitte.
    """
    angle = math.radians(float(development.get("seamAngle", 0.0)
                               if seam_angle is None else seam_angle)) + math.pi
    a = normalized(axis)
    e1, e2 = axis_frame(a)
    radius = float(development.get("radius", 0.0))
    middle = float(development.get("axisMiddle", 0.0))
    return tuple(origin[i] + middle * a[i]
                 + radius * (math.cos(angle) * e1[i] + math.sin(angle) * e2[i])
                 for i in range(3))


def describe(development: Optional[dict]) -> str:
    """Klartext fuer den Editor - Masse in mm, wie ueberall in der Oberflaeche."""
    dev = development_from_doc(development)
    if dev is None:
        return ""
    kind = "Zylinder" if dev.kind == KIND_CYLINDER else "Kegel"
    text = "%s r = %s mm, L = %s mm" % (kind, _mm(dev.radius), _mm(dev.length))
    if dev.kind == KIND_CONE:
        text += ", Öffnung %s°" % _round(math.degrees(abs(dev.half_angle)) * 2.0)
    return text + (", rundum (nahtlos)" if dev.periodic else ", Teilfläche")


def _mm(value: float) -> str:
    return _round(value * 10.0)


def _round(value: float) -> str:
    text = "%.1f" % value
    return text[:-2] if text.endswith(".0") else text


# ------------------------------------------------------------------ aus dem Doc

def development_from_doc(raw) -> Optional["Development"]:
    """``doc["development"]`` -> :class:`Development`, oder ``None``.

    Bewusst nachsichtig: ein unbrauchbarer Eintrag heisst „keine Mantelflaeche",
    nicht „Absturz". Die Fehlermeldung fuer den Nutzer macht
    ``core/pattern_doc.parse``.
    """
    if not isinstance(raw, dict):
        return None
    try:
        kind = str(raw.get("kind", KIND_CYLINDER))
        radius = float(raw.get("radius", 0.0))
        length = float(raw.get("length", 0.0))
        half_angle = float(raw.get("halfAngle", 0.0))
    except (TypeError, ValueError):
        return None
    if kind not in (KIND_CYLINDER, KIND_CONE):
        return None
    for value in (radius, length, half_angle):
        if not math.isfinite(value):
            return None
    if radius <= 0.0 or length <= 0.0 or abs(half_angle) >= math.pi / 2.0:
        return None
    if kind == KIND_CYLINDER and half_angle != 0.0:
        return None
    return Development(kind=kind, radius=radius, half_angle=half_angle,
                       length=length, periodic=bool(raw.get("periodic", False)))


# ------------------------------------------------------- fertige Formen

def cylinder(radius: float, length: float, periodic: bool = True) -> Development:
    return Development(kind=KIND_CYLINDER, radius=float(radius),
                       half_angle=0.0, length=float(length),
                       periodic=bool(periodic))


def cone(radius: float, length: float, half_angle: float,
         periodic: bool = True) -> Development:
    """``radius`` auf der Beruehrlinie, ``length`` entlang der Mantellinie."""
    return Development(kind=KIND_CONE, radius=float(radius),
                       half_angle=float(half_angle), length=float(length),
                       periodic=bool(periodic))
