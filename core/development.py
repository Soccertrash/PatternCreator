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

**Der Kegel fehlt noch.** Zwei Modelle passen auf die bisherige Messung und
liegen bei schmalen Mustern nur Hundertstelgrad auseinander; welches gilt,
entscheidet ein breites Testrechteck (``Context.md`` 15.6, Punkt 4). Davon
haengt ab, ob die Skizze fuer den Vollkegel ein Kreisringsektor oder ein Trapez
sein muss - also eine Zeile Mathematik, aber die falsche Zeile faellt erst am
gedruckten Teil auf.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

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

    ``radius``    Zylinder: der Radius. Kegel: der Radius bei ``s = 0``.
    ``half_angle`` Kegel: halber Oeffnungswinkel (rad); Zylinder: 0.
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
        """Flaechenkoordinaten ``(theta, s)`` -> Abwicklung ``(x, y)``."""
        if self.kind == KIND_CYLINDER:
            return (self.radius * theta, s)
        raise NotImplementedError(
            "Die Abwicklung des Kegels steht noch aus - siehe Context.md 15.6.")

    def period(self) -> float:
        """Breite eines vollen Umlaufs in der Abwicklung."""
        if self.kind == KIND_CYLINDER:
            return 2.0 * math.pi * self.radius
        raise NotImplementedError(
            "Die Abwicklung des Kegels steht noch aus - siehe Context.md 15.6.")

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


# ---------------------------------------------------------------- Zylinder

def cylinder(radius: float, length: float, periodic: bool = True) -> Development:
    return Development(kind=KIND_CYLINDER, radius=float(radius),
                       half_angle=0.0, length=float(length),
                       periodic=bool(periodic))
