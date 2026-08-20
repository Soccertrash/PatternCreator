"""Schraffur - freie Zellflaechen mit zusaetzlichen Stegen fuellen.

Die Schraffur ist **kein** eigener Modus, sondern eine Zugabe zum Flaechenmodus
mit Fuellung *Stege*: dort sind die Zellen offen (im Flaechenmodell Loecher), und
genau diese offenen Flaechen bekommen zusaetzliche Stege eingezogen.

Warum Stege und keine Linien: das Ergebnis soll wie das uebrige Muster
extrudierbar und 3D-druckbar sein. Die Strichdicke ist deshalb **eigenstaendig**
einstellbar - eine Schraffur ist typischerweise feiner als das tragende Stegnetz.

Damit keine schwebenden Inseln entstehen, wird jede Schraffurlinie an beiden
Enden um ``web_half`` verlaengert: sie reicht damit bis zur Mittellinie des
umgebenden Stegs und ist sicher mit ihm verbunden.

Alle Laengen in cm, alle Winkel im Bogenmass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import ir
from .geom import centroid
from .stroker import stroke

Point = Tuple[float, float]

#: Notbremse: mehr Schraffurstege ergibt keine brauchbare Skizze mehr
MAX_STRIPS = 20000
#: Notbremse je Flaeche (sehr kleiner Abstand in einer sehr grossen Zelle)
MAX_LINES_PER_AREA = 2000
#: Segmente kuerzer als dieser Anteil der Strichdicke sind Eckensplitter
MIN_SEGMENT_FACTOR = 0.25

AIM_FIXED = "fixed"       # ein Winkel fuer alle Zellen
AIM_RANDOM = "random"     # je Zelle um den Grundwinkel gestreut (aus dem Seed)
AIM_CENTER = "center"     # je Zelle auf einen gemeinsamen Punkt ausgerichtet

KIND_PARALLEL = "parallel"
KIND_CROSS = "cross"


@dataclass
class HatchStyle:
    """Aufbereitete Schraffur-Einstellungen (Bogenmass, cm)."""

    kind: str = KIND_PARALLEL
    spacing: float = 0.4
    thickness: float = 0.06
    angle: float = math.pi / 4.0
    cross_angle: float = math.pi / 2.0
    aim: str = AIM_FIXED
    jitter: float = math.pi / 2.0
    center: Point = (0.0, 0.0)


def style_from_doc(style: Dict[str, Any]) -> Optional[HatchStyle]:
    """Stil-Abschnitt des Docs -> ``HatchStyle`` oder ``None`` (Schraffur aus).

    Die Schraffur greift nur im Flaechenmodus mit Fuellung *Stege*: nur dort sind
    die Zellen ueberhaupt frei. Im Editor ist sie deshalb auch nur dann sichtbar.
    """
    if not style.get("hatch"):
        return None
    if str(style.get("mode", "area")) != "area":
        return None
    if str(style.get("fillTarget", "webs")) != "webs":
        return None
    spacing = float(style.get("hatchSpacing", 0.4))
    thickness = float(style.get("hatchThickness", 0.06))
    if spacing <= 1e-9 or thickness <= 1e-9:
        return None
    return HatchStyle(
        kind=str(style.get("hatchType", KIND_PARALLEL)),
        spacing=spacing,
        thickness=thickness,
        angle=math.radians(float(style.get("hatchAngle", 45.0))),
        cross_angle=math.radians(float(style.get("hatchCrossAngle", 90.0))),
        aim=str(style.get("hatchAim", AIM_FIXED)),
        jitter=math.radians(float(style.get("hatchJitter", 90.0))),
        center=(float(style.get("hatchCenterX", 0.0)),
                float(style.get("hatchCenterY", 0.0))),
    )


# ------------------------------------------------------------------ Geometrie

def _rot(p: Point, ca: float, sa: float) -> Point:
    return (p[0] * ca - p[1] * sa, p[0] * sa + p[1] * ca)


def scanlines(poly: Sequence[Point], angle: float, spacing: float
              ) -> List[Tuple[Point, Point]]:
    """Mittellinien der Schraffur innerhalb eines - auch konkaven - Polygons.

    Klassisches Scanline-Verfahren: das Polygon wird in das Schraffur-Koordinaten-
    system gedreht (Linien werden waagerecht), je Rasterlinie werden die
    Kantenschnitte gesammelt, sortiert und paarweise verbunden (even-odd). Damit
    funktioniert es auch bei Einbuchtungen (Puzzle-Nasen) und liefert dort mehrere
    Teilstrecken je Linie - anders als das konvexe Clipping in ``core/clip.py``.

    Das Raster liegt auf den absoluten Vielfachen von ``spacing``; bei gleichem
    Winkel fluchten die Linien deshalb ueber Zellgrenzen hinweg.
    """
    if len(poly) < 3 or spacing <= 1e-9:
        return []
    ca, sa = math.cos(-angle), math.sin(-angle)
    rot = [_rot(p, ca, sa) for p in poly]
    ys = [p[1] for p in rot]
    lo, hi = min(ys), max(ys)
    k0 = int(math.ceil(lo / spacing))
    k1 = int(math.floor(hi / spacing))
    if k1 < k0:
        return []
    if k1 - k0 + 1 > MAX_LINES_PER_AREA:
        return []

    back_ca, back_sa = math.cos(angle), math.sin(angle)
    n = len(rot)
    out: List[Tuple[Point, Point]] = []
    for k in range(k0, k1 + 1):
        y = k * spacing
        # Linien genau auf der Randtangente liegen zur Haelfte im Steg: sie
        # wuerden ihn nur verbreitern und kosten unnoetige Entities.
        if y <= lo + 1e-9 or y >= hi - 1e-9:
            continue
        xs: List[float] = []
        for i in range(n):
            x0, y0 = rot[i]
            x1, y1 = rot[(i + 1) % n]
            # Halboffenes Intervall: Ecken werden genau einmal gezaehlt,
            # waagerechte Kanten fallen heraus.
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
        if len(xs) < 2:
            continue
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            if xs[i + 1] - xs[i] <= 1e-12:
                continue
            out.append((_rot((xs[i], y), back_ca, back_sa),
                        _rot((xs[i + 1], y), back_ca, back_sa)))
    return out


def _extended(a: Point, b: Point, amount: float) -> Tuple[Point, Point]:
    """Strecke an beiden Enden verlaengern (Anbindung an den Steg)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d <= 1e-12 or amount <= 0.0:
        return (a, b)
    ux, uy = dx / d, dy / d
    return ((a[0] - ux * amount, a[1] - uy * amount),
            (b[0] + ux * amount, b[1] + uy * amount))


def _angle_for(poly: Sequence[Point], hs: HatchStyle, rnd) -> float:
    """Grundwinkel dieser Flaeche - fest, gestreut oder auf den Punkt gerichtet."""
    if hs.aim == AIM_RANDOM:
        return hs.angle + rnd.uniform(-hs.jitter, hs.jitter)
    if hs.aim == AIM_CENTER:
        cx, cy = centroid(poly)
        dx, dy = hs.center[0] - cx, hs.center[1] - cy
        if math.hypot(dx, dy) < 1e-9:
            return hs.angle
        return math.atan2(dy, dx)
    return hs.angle


# --------------------------------------------------------------------- Aufbau

def hatch_areas(polys: Sequence[Sequence[Point]], hs: HatchStyle, rnd,
                web_half: float) -> Tuple[List[ir.Path], List[str]]:
    """Freie Flaechen schraffieren -> geschlossene Streifen (wie gestrokte Stege).

    ``polys`` sind die **offenen** Flaechen (im Flaechenmodell die Loecher),
    ``web_half`` die halbe Breite des umgebenden Stegs: um diesen Betrag wird
    jede Linie verlaengert, damit der Streifen im Steg verankert ist.
    """
    out: List[ir.Path] = []
    warnings: List[str] = []
    min_len = hs.thickness * MIN_SEGMENT_FACTOR
    truncated = False

    for poly in polys:
        if len(poly) < 3:
            continue
        base = _angle_for(poly, hs, rnd)
        angles = [base]
        if hs.kind == KIND_CROSS:
            angles.append(base + hs.cross_angle)
        for angle in angles:
            for a, b in scanlines(poly, angle, hs.spacing):
                if math.hypot(b[0] - a[0], b[1] - a[1]) < min_len:
                    continue
                p0, p1 = _extended(a, b, web_half)
                for ring in stroke([p0, p1], False, hs.thickness):
                    if len(ring) < 3:
                        continue
                    if len(out) >= MAX_STRIPS:
                        truncated = True
                        break
                    out.append(ir.Path(points=ring, closed=True, curve="line",
                                       role=ir.ROLE_REGION, layer=ir.LAYER_PATTERN))
                if truncated:
                    break
            if truncated:
                break
        if truncated:
            break

    if truncated:
        warnings.append("Schraffur bei %d Stegen abgebrochen – Abstand vergrößern."
                        % MAX_STRIPS)
    return out, warnings
