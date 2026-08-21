"""Die fertige Szene in den Kreisringsektor biegen - der letzte Schritt beim Kegel.

Warum ueberhaupt gebogen wird: Fusions Emboss wickelt einen Kegel als
**Sektor** ab - der Abstand zum Apex bleibt erhalten, der Winkel wird um
``sin(alpha)`` gestaucht (gemessen, ``Context.md`` 15.6, Punkt 4). Die Skizze
fuer einen Vollkegel ist damit ein Kreisringsektor und kein Rechteck.

Erzeugt wird das Muster trotzdem im Rechteck. Das ist keine Bequemlichkeit,
sondern die einzige Art, die Naht sauber hinzubekommen: Generatoren, Nahtsuche,
Behaelter und Flaechenmodell rechnen alle in geraden Koordinaten, und die
Periodizitaet ist dort eine **Verschiebung** um ``2*pi*radius``. Erst ganz zum
Schluss - nach Flaechenbildung, Schraffur und Text, vor der Platzierung - wird
das Rechteck gebogen:

    x, y  ->  ((rho + y) * sin(x / rho),  (rho + y) * cos(x / rho) - rho)

``rho`` ist der Abstand von der Beruehrlinie zum Apex. Der Apex liegt bei
``(0, -rho)`` und bleibt dabei stehen, die Beruehrlinie ``x = 0`` bleibt gerade,
und die beiden Nahtkanten ``x = +-pi*radius`` treffen sich als **eine** radiale
Linie: ihr Winkelabstand ist genau der Sektorwinkel ``2*pi*sin(alpha)``.

Was das Biegen kostet: Geraden werden zu Bogen. Jede Strecke wird deshalb so
fein unterteilt, dass ihre Sehnenhoehe unter :data:`core.optimize.TOL` bleibt -
dieselbe Toleranz, mit der der Optimierer hinterher wieder zusammenfasst. Nahe
der Beruehrlinie kostet das nichts (dort ist der Bogen fast gerade), nahe der
Naht am meisten.

**Zellen werden zum Apex hin schmaler.** Das ist kein Fehler, sondern
unvermeidlich: ein Muster, das rundum passt, hat auf jedem Hoehenkreis gleich
viele Zellen, und der Umfang nimmt zur Spitze hin ab. Genau so sieht die
Abwicklung eines Kegels aus.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

from core import ir
from core.development import Development
from core.optimize import TOL

Point = Tuple[float, float]

#: Feinste Unterteilung einer einzelnen Strecke. Bremse gegen Entartungen
#: (eine Strecke ueber den halben Umfang bei winzigem ``rho``).
MAX_STEPS = 96

#: Warnung, wenn Text auf einen Kegel soll.
TEXT_WARNING = ("Text auf einem Kegel wird nur gedreht und verschoben, nicht "
                "gebogen – bei großen Buchstaben ist das zu sehen.")


def apply(scene: "ir.Scene", development: Optional[Development]) -> None:
    """Szene in den Sektor biegen. Zylinder und Ebene bleiben unberuehrt."""
    if development is None or not development.is_cone():
        return
    rho = development.apex_distance()
    if rho <= 0.0 or not math.isfinite(rho):
        return
    out: List[Any] = []
    warned = False
    for el in scene.elements:
        if isinstance(el, ir.TextItem):
            if not warned:
                scene.warnings.append(TEXT_WARNING)
                warned = True
            out.append(_text(el, rho))
        elif isinstance(el, ir.Path):
            out.append(_path(el, rho))
        elif isinstance(el, ir.Circle):
            out.append(_path(_circle_as_path(el), rho))
        elif isinstance(el, ir.Arc):
            out.append(_path(_arc_as_path(el), rho))
        elif isinstance(el, ir.Ellipse):
            out.append(_path(_ellipse_as_path(el), rho))
        else:
            out.append(el)
    scene.elements = out


def point(x: float, y: float, rho: float) -> Point:
    """Ein Punkt des Rechtecks an seiner Stelle im Sektor."""
    angle = x / rho
    reach = rho + y
    return (reach * math.sin(angle), reach * math.cos(angle) - rho)


# ------------------------------------------------------------------ Elemente

def _path(el: "ir.Path", rho: float) -> "ir.Path":
    pts, widths = _dense(el.points, el.widths, el.closed, rho,
                         curved=(el.curve == "spline"))
    return ir.Path(points=[point(x, y, rho) for x, y in pts],
                   closed=el.closed, curve=el.curve, role=el.role,
                   layer=el.layer, widths=widths)


def _dense(points: Sequence[Point], widths: Optional[Sequence[float]],
           closed: bool, rho: float, curved: bool):
    """Stuetzpunkte so verdichten, dass die Sehnenhoehe unter ``TOL`` bleibt.

    Splines bleiben unangetastet: ihre Stuetzpunkte sind der Kurve ihre
    Definition, und ein eingeschobener Punkt veraendert sie. Organische Muster
    liefern sie ohnehin dicht genug.
    """
    pts = [(float(p[0]), float(p[1])) for p in points]
    has_widths = widths is not None and len(widths) == len(pts)
    if curved or len(pts) < 2:
        return pts, (list(widths) if has_widths else None)

    out: List[Point] = []
    out_w: List[float] = []
    last = len(pts) if closed else len(pts) - 1
    for i in range(last):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        steps = _steps(a, b, rho)
        for k in range(steps):
            t = k / float(steps)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            if has_widths:
                wa = widths[i]
                wb = widths[(i + 1) % len(pts)]
                out_w.append(wa + (wb - wa) * t)
    if not closed:
        out.append(pts[-1])
        if has_widths:
            out_w.append(widths[-1])
    return out, (out_w if has_widths else None)


def _steps(a: Point, b: Point, rho: float) -> int:
    """In wie viele Stuecke muss diese Strecke zerfallen?

    Nach dem Biegen liegt sie auf einem Bogen mit Radius ``rho + y``. Die
    Sehnenhoehe eines Bogenstuecks mit Winkel ``d`` ist ungefaehr
    ``reach * d^2 / 8``; daraus folgt die groesste erlaubte Schrittweite. Eine
    radiale Strecke (gleiches ``x``) bleibt gerade und braucht nichts.
    """
    sweep = abs(b[0] - a[0]) / rho
    if sweep <= 1e-12:
        return 1
    reach = rho + max(a[1], b[1])
    if reach <= 1e-12:
        return 1
    widest = math.sqrt(8.0 * TOL / reach)
    if widest <= 1e-12:
        return MAX_STEPS
    return max(1, min(MAX_STEPS, int(math.ceil(sweep / widest))))


def _text(el: "ir.TextItem", rho: float) -> "ir.TextItem":
    """Text an seine Stelle im Sektor - gedreht, nicht gebogen."""
    x, y = point(el.x, el.y, rho)
    return ir.TextItem(text=el.text, x=x, y=y, height=el.height,
                       angle=el.angle - el.x / rho, font=el.font,
                       layer=el.layer, role=el.role)


# ------------------------------------------------------ Rundes zu Polygonen

def _circle_as_path(el: "ir.Circle") -> "ir.Path":
    return ir.Path(points=_ring(el.center, el.radius, el.radius, 0.0,
                                0.0, 2.0 * math.pi),
                   closed=True, role=el.role, layer=el.layer)


def _arc_as_path(el: "ir.Arc") -> "ir.Path":
    return ir.Path(points=_ring(el.center, el.radius, el.radius, 0.0,
                                el.a0, el.a1),
                   closed=False, role=el.role, layer=el.layer)


def _ellipse_as_path(el: "ir.Ellipse") -> "ir.Path":
    return ir.Path(points=_ring(el.center, el.rx, el.ry, el.rotation,
                                0.0, 2.0 * math.pi),
                   closed=True, role=el.role, layer=el.layer)


def _ring(center: Point, rx: float, ry: float, rotation: float,
          a0: float, a1: float) -> List[Point]:
    """Kreis, Bogen oder Ellipse als Punktzug - Sehnenhoehe unter ``TOL``."""
    biggest = max(abs(rx), abs(ry))
    sweep = a1 - a0
    if biggest <= 1e-12 or abs(sweep) <= 1e-12:
        return [center, center]
    widest = math.sqrt(8.0 * TOL / biggest)
    count = max(6, min(720, int(math.ceil(abs(sweep) / max(widest, 1e-9)))))
    closed = abs(abs(sweep) - 2.0 * math.pi) < 1e-9
    ca, sa = math.cos(rotation), math.sin(rotation)
    out: List[Point] = []
    for i in range(count if closed else count + 1):
        angle = a0 + sweep * (i / float(count))
        dx, dy = rx * math.cos(angle), ry * math.sin(angle)
        out.append((center[0] + dx * ca - dy * sa,
                    center[1] + dx * sa + dy * ca))
    return out
