"""Skizzenelement-Optimierer: weniger Entities bei gleicher Geometrie.

Der Optimierer laeuft als letzter Schritt in ``core/build.build_scene()`` - also
**vor** der Scene-Erzeugung und damit fuer Vorschau und Fusion-Ausgabe identisch.
Er darf die sichtbare Geometrie nicht veraendern: die maximale Abweichung einer
optimierten von der urspruenglichen Kontur bleibt unter :data:`TOL`.

Ausgebaut wird der Optimierer in Paessen. Aktuell umgesetzt:

* **Pass 1 - exakte Bereinigung (verlustfrei).**
  1. aufeinanderfolgende (nahezu) identische Punkte entfernen,
  2. exakt kollineare Punktfolgen zusammenfassen (Stroker-Ringe und
     Schraffur-Rechtecke bestehen zum grossen Teil aus solchen Punkten),
  3. doppelte Elemente entfernen (identische Ringe nach Rasterung).
* **Pass 2 - Kreis-Refit:** ein geschlossener Linienzug, der rundum auf einem
  Kreis liegt, wird ein ``ir.Circle`` (n Linien -> 1 Element).
* **Pass 3 - Bogen-Refit:** ein offener Linienzug, der auf einem Kreisbogen
  liegt, wird ein ``ir.Arc`` (n-1 Linien -> 1 Element).
* **Pass 5 - Spline-Umwandlung:** eine glatte, punktreiche Kontur wird ein
  einziger fitted Spline (n Linien -> 1 Element).
* **Pass 4 - Vereinfachung:** Ramer-Douglas-Peucker mit ``TOL`` auf allen
  uebrigen Linienzuegen, abgesichert gegen neu entstehende Selbstschnitte.

Pass 5 laeuft **vor** Pass 4 und nur einer von beiden greift. Zwei Gruende:
ein Spline ist mit einem Element ohnehin nicht zu unterbieten, und die
Vereinfachung macht eine Kontur fuer den Spline nur schlechter (weniger
Stuetzpunkte = laengere Sehnen = groessere Ausbeulung). Nacheinander duerfen
beide schon deshalb nicht laufen, weil sich ihre Abweichungen sonst auf das
Doppelte von :data:`TOL` summieren wuerden.

Geschuetzt bleiben Text-Layer und ``ROLE_DECOR``: diese Elemente werden
unveraendert durchgereicht und nicht dedupliziert.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

from . import ir
from .geom import catmull_rom
# Derselbe Strecken-Schnitttest, mit dem ``remove_loops`` Offset-Schleifen
# findet - hier als Waechter fuer die Vereinfachung.
from .geom import _segments_cross

Point = Tuple[float, float]

#: Maximale Abweichung der optimierten von der urspruenglichen Kontur (cm).
#: 0,002 cm = 0,02 mm - weit unter der Aufloesung eines FDM-Druckers.
TOL = 0.002

#: Punkte, die dichter beieinander liegen, sind derselbe Punkt (cm).
POINT_TOL = 1e-9

#: Bis zu diesem Abstand von der Verbindungsgeraden seiner Nachbarn gilt ein
#: Punkt als exakt kollinear (cm). Bewusst winzig: Pass 1 ist verlustfrei,
#: die toleranzbasierte Vereinfachung kommt spaeter in einem eigenen Pass.
COLLINEAR_TOL = 1e-9

#: Nachkommastellen fuer die Duplikaterkennung (1e-4 cm = 1 Mikrometer).
DEDUPE_PRECISION = 4

#: Unterhalb dieser Punktzahl ist ein Kreis-Refit reine Spekulation.
MIN_CIRCLE_POINTS = 8

#: Unterhalb dieser Punktzahl ist ein Bogen-Refit reine Spekulation
#: (3 Punkte liegen immer exakt auf einem Kreis).
MIN_ARC_POINTS = 4

#: Ab dieser Punktzahl lohnt die Spline-Umwandlung. Darunter waere der Gewinn
#: klein und das Risiko einer sichtbar anderen Kurvenform verhaeltnismaessig gross.
MIN_SPLINE_POINTS = 12

#: Groesster erlaubter Knickwinkel zwischen zwei Folgesegmenten. Ein fitted
#: Spline schwingt an einer echten Ecke ueber - dort bleibt es beim Linienzug.
MAX_SPLINE_KINK = math.radians(30.0)

#: Stuetzstellen je Segment fuer die Abschaetzung des Splineverlaufs.
SPLINE_SAMPLES = 8


def optimize(elements: Sequence[Any]) -> List[Any]:
    """Elementliste optimieren; Reihenfolge bleibt erhalten."""
    out: List[Any] = []
    seen = set()
    for el in elements:
        if _is_protected(el):
            out.append(el)
            continue
        el = _simplify_element(el)              # Pass 1
        el = _refit_element(el)                 # Pass 2 + 3
        spline = _to_spline(el, TOL)            # Pass 5
        el = spline if spline is not el else _reduce_element(el)    # sonst Pass 4
        key = _dedupe_key(el)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        out.append(el)
    return out


# ------------------------------------------------------------------ Schutz

def _is_protected(el: Any) -> bool:
    """Text und eigenstaendige Deko bleiben unangetastet."""
    if isinstance(el, ir.TextItem):
        return True
    return (getattr(el, "layer", "") == ir.LAYER_TEXT
            or getattr(el, "role", "") == ir.ROLE_DECOR)


# ----------------------------------------------------- Pass 1: Bereinigung

def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _deviation(a: Point, b: Point, c: Point) -> float:
    """Abstand von ``b`` zur Geraden ``a``-``c`` (unendlich bei Richtungsumkehr).

    Genau dieser Abstand ist der Fehler, den das Weglassen von ``b`` erzeugt.
    Kehrt der Weg an ``b`` seine Richtung um (Spitze), darf ``b`` nie wegfallen -
    aus der Spitze wuerde sonst eine Strecke.
    """
    ux, uy = b[0] - a[0], b[1] - a[1]
    vx, vy = c[0] - b[0], c[1] - b[1]
    if ux * vx + uy * vy <= 0.0:
        return float("inf")
    wx, wy = c[0] - a[0], c[1] - a[1]
    base = math.hypot(wx, wy)
    if base < POINT_TOL:
        return float("inf")
    return abs(wx * (b[1] - a[1]) - wy * (b[0] - a[0])) / base


def _drop_duplicate_points(pts: Sequence[Point], closed: bool) -> List[int]:
    """Indizes der Punkte, die nach dem Entfernen von Dubletten uebrig bleiben."""
    keep: List[int] = []
    for i, p in enumerate(pts):
        if keep and _dist(pts[keep[-1]], p) <= POINT_TOL:
            continue
        keep.append(i)
    if closed and len(keep) > 2 and _dist(pts[keep[0]], pts[keep[-1]]) <= POINT_TOL:
        keep.pop()
    return keep


def _drop_collinear(pts: Sequence[Point], keep: Sequence[int], closed: bool,
                    tol: float = COLLINEAR_TOL) -> List[int]:
    """Kollineare Zwischenpunkte in einem Zug entfernen.

    Bewusst *ein* Durchgang mit den urspruenglichen Nachbarn: bei einer geraden
    Punktfolge faellt dabei jeder Zwischenpunkt weg, und der Fehler kann sich -
    anders als beim schrittweisen Verschmelzen - nicht aufsummieren.
    """
    n = len(keep)
    if n < 3:
        return list(keep)
    out: List[int] = []
    rng = range(n) if closed else range(1, n - 1)
    if not closed:
        out.append(keep[0])
    for i in rng:
        a = pts[keep[(i - 1) % n]]
        b = pts[keep[i]]
        c = pts[keep[(i + 1) % n]]
        if _deviation(a, b, c) > tol:
            out.append(keep[i])
    if not closed:
        out.append(keep[-1])
    return out


def _simplify_element(el: Any) -> Any:
    if not isinstance(el, ir.Path) or len(el.points) < 2:
        return el
    pts = el.points
    keep = _drop_duplicate_points(pts, el.closed)
    # Fitted Splines laufen durch ihre Stuetzpunkte: ein "kollinearer" Punkt
    # traegt dort trotzdem Form - nur Dubletten duerfen weg.
    if el.curve != "spline":
        merged = _drop_collinear(pts, keep, el.closed)
        if len(merged) >= (3 if el.closed else 2):
            keep = merged
    if len(keep) == len(pts):
        return el
    if len(keep) < (3 if el.closed else 2):
        return el
    return ir.Path(points=[pts[i] for i in keep], closed=el.closed, curve=el.curve,
                   role=el.role, layer=el.layer,
                   widths=([el.widths[i] for i in keep]
                           if el.widths is not None else None))


# -------------------------------------------- Pass 2 + 3: Kreis und Bogen

def _fit_circle(pts: Sequence[Point]) -> Optional[Tuple[Point, float]]:
    """Ausgleichskreis nach Kasa (geschlossene 3x3-Loesung, reines Python).

    Minimiert die algebraische Abweichung ``(x^2 + y^2) - (A x + B y + C)``.
    Die Punkte werden vorher in ihren Schwerpunkt verschoben, sonst wird das
    Gleichungssystem bei weit vom Ursprung entfernten Konturen schlecht
    konditioniert.
    """
    n = len(pts)
    if n < 3:
        return None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    suu = suv = svv = suw = svw = 0.0
    for px, py in pts:
        u, v = px - mx, py - my
        w = u * u + v * v
        suu += u * u
        suv += u * v
        svv += v * v
        suw += u * w
        svw += v * w
    det = suu * svv - suv * suv
    if abs(det) < 1e-18:
        return None                                  # alle Punkte auf einer Geraden
    cu = 0.5 * (suw * svv - svw * suv) / det
    cv = 0.5 * (svw * suu - suw * suv) / det
    center = (mx + cu, my + cv)
    radius = sum(math.hypot(px - center[0], py - center[1]) for px, py in pts) / n
    if radius <= POINT_TOL:
        return None
    return center, radius


def _radial_error(pts: Sequence[Point], center: Point, radius: float) -> float:
    return max(abs(math.hypot(p[0] - center[0], p[1] - center[1]) - radius) for p in pts)


def _sagitta(radius: float, sweep: float) -> float:
    """Bogenhoehe: so weit weicht die Sehne vom Bogen ab."""
    return radius * (1.0 - math.cos(min(abs(sweep), math.pi) / 2.0))


def _angles(pts: Sequence[Point], center: Point) -> List[float]:
    return [math.atan2(p[1] - center[1], p[0] - center[0]) for p in pts]


def _step(a: float, b: float) -> float:
    """Winkeldifferenz b-a, normiert auf (-pi, pi]."""
    d = (b - a) % (2.0 * math.pi)
    return d - 2.0 * math.pi if d > math.pi else d


def _fit_full_circle(el: ir.Path) -> Optional[ir.Circle]:
    """Pass 2: geschlossener Linienzug rundum auf einem Kreis -> ``ir.Circle``."""
    pts = el.points
    if len(pts) < MIN_CIRCLE_POINTS:
        return None
    fit = _fit_circle(pts)
    if fit is None:
        return None
    center, radius = fit
    radial = _radial_error(pts, center, radius)
    if radial > TOL:
        return None
    # Der Vollwinkel muss lueckenlos abgedeckt sein: die groesste Winkelluecke
    # bestimmt, wie weit der Kreis von der urspruenglichen Sehne abweicht.
    # Beide Fehler treffen in der Sehnenmitte zusammen und werden deshalb
    # zusammen gegen das Toleranzbudget geprueft.
    angs = sorted(_angles(pts, center))
    gap = max([angs[i + 1] - angs[i] for i in range(len(angs) - 1)]
              + [angs[0] + 2.0 * math.pi - angs[-1]])
    if radial + _sagitta(radius, gap) > TOL:
        return None
    return ir.Circle(center=center, radius=radius, role=el.role, layer=el.layer)


def _fit_arc(el: ir.Path) -> Optional[ir.Arc]:
    """Pass 3: offener Linienzug auf einem Kreisbogen -> ``ir.Arc``."""
    pts = el.points
    if len(pts) < MIN_ARC_POINTS:
        return None
    fit = _fit_circle(pts)
    if fit is None:
        return None
    center, radius = fit
    radial = _radial_error(pts, center, radius)
    if radial > TOL:
        return None
    angs = _angles(pts, center)
    steps = [_step(angs[i], angs[i + 1]) for i in range(len(angs) - 1)]
    if not steps or min(steps) <= 0.0 < max(steps) or any(s == 0.0 for s in steps):
        return None                                  # Richtungswechsel oder Stillstand
    sweep = sum(steps)
    if abs(sweep) >= 2.0 * math.pi - 1e-9:
        return None                                  # geschlossen, nicht offen
    # Die Sehnen selbst muessen ebenfalls nah am Bogen liegen - sonst zoege der
    # Bogen ueber einen Punktabstand hinweg, den die Polylinie gerade abkuerzt.
    if radial + _sagitta(radius, max(abs(s) for s in steps)) > TOL:
        return None
    return ir.Arc(center=center, radius=radius, a0=angs[0], a1=angs[0] + sweep,
                  role=el.role, layer=el.layer)


def _refit_element(el: Any) -> Any:
    if not isinstance(el, ir.Path) or el.curve != "line" or el.widths is not None:
        return el
    out = _fit_full_circle(el) if el.closed else _fit_arc(el)
    return out if out is not None else el


# ------------------------------------------------- Pass 4: Vereinfachung

def _point_to_segment(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    ll = dx * dx + dy * dy
    if ll < 1e-24:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / ll
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(p[0] - ax - dx * t, p[1] - ay - dy * t)


def _rdp(pts: Sequence[Point], first: int, last: int, eps: float,
         keep: set) -> None:
    """Ramer-Douglas-Peucker, iterativ (Rekursion sprengt bei langen Ketten den Stack)."""
    stack = [(first, last)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        best, idx = -1.0, -1
        for k in range(i + 1, j):
            d = _point_to_segment(pts[k], pts[i], pts[j])
            if d > best:
                best, idx = d, k
        if best > eps:
            keep.add(idx)
            stack.append((i, idx))
            stack.append((idx, j))


def _reduce_indices(pts: Sequence[Point], closed: bool, eps: float) -> List[int]:
    n = len(pts)
    if closed:
        if n < 4:
            return list(range(n))
        # Zwei feste Anker, damit der Ring in zwei Haelften zerfaellt: Punkt 0
        # und der am weitesten entfernte Punkt. Beides haengt nur an der
        # Punktfolge - das Ergebnis ist damit reproduzierbar.
        far = max(range(n), key=lambda i: (math.hypot(pts[i][0] - pts[0][0],
                                                      pts[i][1] - pts[0][1]), -i))
        if far == 0:
            return list(range(n))
        keep = {0, far}
        _rdp(pts, 0, far, eps, keep)
        loop = list(pts[far:]) + [pts[0]]
        tail: set = {0, len(loop) - 1}
        _rdp(loop, 0, len(loop) - 1, eps, tail)
        keep.update((far + i) % n for i in tail)
        return sorted(keep)
    if n < 3:
        return list(range(n))
    keep = {0, n - 1}
    _rdp(pts, 0, n - 1, eps, keep)
    return sorted(keep)


def _self_intersects(pts: Sequence[Point], closed: bool) -> bool:
    n = len(pts)
    segs = [(pts[i], pts[(i + 1) % n]) for i in range(n if closed else n - 1)]
    m = len(segs)
    if m < 4:
        return False
    boxes = [(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
             for a, b in segs]
    for i in range(m):
        a, b = segs[i]
        x0, y0, x1, y1 = boxes[i]
        for j in range(i + 2, m):
            if closed and i == 0 and j == m - 1:
                continue          # erstes und letztes Segment sind Nachbarn
            u0, v0, u1, v1 = boxes[j]
            if u0 > x1 or u1 < x0 or v0 > y1 or v1 < y0:
                continue
            if _segments_cross(a, b, segs[j][0], segs[j][1]) is not None:
                return True
    return False


def _reduce_element(el: Any) -> Any:
    if not isinstance(el, ir.Path) or el.curve != "line":
        return el
    pts = el.points
    keep = _reduce_indices(pts, el.closed, TOL)
    if len(keep) == len(pts) or len(keep) < (3 if el.closed else 2):
        return el
    reduced = [pts[i] for i in keep]
    # Waechter: eine Vereinfachung darf keinen Selbstschnitt erzeugen - ein
    # sich selbst schneidendes Profil ist in Fusion unbrauchbar. War die
    # Kontur schon vorher selbstschneidend, aendert die Vereinfachung daran
    # nichts und darf greifen.
    if _self_intersects(reduced, el.closed) and not _self_intersects(pts, el.closed):
        return el
    return ir.Path(points=reduced, closed=el.closed, curve=el.curve, role=el.role,
                   layer=el.layer,
                   widths=([el.widths[i] for i in keep]
                           if el.widths is not None else None))


# ------------------------------------------- Pass 5: Spline-Umwandlung

def _max_kink(pts: Sequence[Point], closed: bool) -> float:
    """Groesster Richtungswechsel zwischen zwei Folgesegmenten (Bogenmass)."""
    n = len(pts)
    worst = 0.0
    for i in (range(n) if closed else range(1, n - 1)):
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        ux, uy = b[0] - a[0], b[1] - a[1]
        vx, vy = c[0] - b[0], c[1] - b[1]
        lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
        if lu < POINT_TOL or lv < POINT_TOL:
            continue
        cos = (ux * vx + uy * vy) / (lu * lv)
        ang = math.acos(-1.0 if cos < -1.0 else (1.0 if cos > 1.0 else cos))
        if ang > worst:
            worst = ang
    return worst


def _spline_error(pts: Sequence[Point], closed: bool) -> float:
    """Wie weit weicht der Spline zwischen den Stuetzpunkten vom Linienzug ab?

    Gemessen wird segmentweise: der Bogen zwischen zwei Stuetzpunkten gegen
    seine Sehne. Modell ist Catmull-Rom - dieselbe Kurve, die die Vorschau
    zeichnet, und eine gute Naeherung fuer den fitted Spline in Fusion.
    """
    n = len(pts)
    curve = catmull_rom(pts, samples=SPLINE_SAMPLES, closed=closed)
    worst = 0.0
    for i in range(n if closed else n - 1):
        a, b = pts[i], pts[(i + 1) % n]
        for k in range(i * SPLINE_SAMPLES, (i + 1) * SPLINE_SAMPLES):
            d = _point_to_segment(curve[k], a, b)
            if d > worst:
                worst = d
    return worst


def _to_spline(el: Any, budget: float) -> Any:
    if not isinstance(el, ir.Path) or el.curve != "line":
        return el
    # Der Rahmen bleibt ein Linienzug: an ihm haengt die zugesicherte
    # Rahmendicke, und zu gewinnen waeren dort ein, zwei Elemente.
    if el.layer == ir.LAYER_BORDER or el.role == ir.ROLE_FACE:
        return el
    pts = el.points
    if len(pts) < MIN_SPLINE_POINTS or budget <= 0.0:
        return el
    if _max_kink(pts, el.closed) > MAX_SPLINE_KINK:
        return el
    if _spline_error(pts, el.closed) > budget:
        return el
    return ir.Path(points=list(pts), closed=el.closed, curve="spline", role=el.role,
                   layer=el.layer, widths=el.widths)


# ------------------------------------------------- Pass 1c: Duplikatfilter

def _q(value: float) -> float:
    """Auf das Duplikat-Raster runden (``-0.0`` und ``0.0`` fallen zusammen)."""
    return round(value, DEDUPE_PRECISION) + 0.0


def _canonical_ring(pts: Sequence[Point]) -> Tuple[Point, ...]:
    """Rotations- und richtungsunabhaengige Normalform eines geschlossenen Rings."""
    best: Optional[Tuple[Point, ...]] = None
    for seq in (list(pts), list(reversed(pts))):
        start = min(range(len(seq)), key=lambda i: seq[i])
        rotated = tuple(seq[start:] + seq[:start])
        if best is None or rotated < best:
            best = rotated
    return best or ()


def _dedupe_key(el: Any) -> Optional[tuple]:
    """Schluessel fuer identische Elemente; ``None`` = nicht deduplizieren."""
    if isinstance(el, ir.Path):
        pts = [(_q(x), _q(y)) for x, y in el.points]
        shape = _canonical_ring(pts) if el.closed else tuple(pts)
        return ("path", el.closed, el.curve, el.role, el.layer, shape)
    if isinstance(el, ir.Circle):
        return ("circle", _q(el.center[0]), _q(el.center[1]), _q(el.radius),
                el.role, el.layer)
    if isinstance(el, ir.Arc):
        return ("arc", _q(el.center[0]), _q(el.center[1]), _q(el.radius),
                _q(el.a0), _q(el.a1), el.role, el.layer)
    if isinstance(el, ir.Ellipse):
        return ("ellipse", _q(el.center[0]), _q(el.center[1]), _q(el.rx), _q(el.ry),
                _q(el.rotation), el.role, el.layer)
    return None
