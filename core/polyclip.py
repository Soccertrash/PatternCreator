"""Clipping gegen beliebige - auch konkave - Rahmen.

``core/clip.py`` kann nur konvexe Bereiche (Halbebenen). Ein vom Nutzer
gezeichneter Rahmen ist dagegen in der Regel konkav; dafuer ist dieses Modul da.
``core/clip.py`` bleibt unangetastet, die Standardformen behalten also ihren
schnellen Weg.

**Verfahren: Randklassifikation.** Fuer ``polygon ∩ frame`` (beide einfach, ohne
Loecher, beide duerfen konkav sein):

1. alle Schnittpunkte zwischen Zell- und Rahmenkanten bestimmen (inklusive
   Beruehrungen und kollinearer Ueberlappungen),
2. beide Konturen an diesen Parametern aufteilen,
3. jede Teilkante ueber ihren **Mittelpunkt** einordnen:
   Zell-Teilkante bleibt, wenn der Mittelpunkt innen **oder auf dem Rand** des
   Rahmens liegt; Rahmen-Teilkante bleibt, wenn der Mittelpunkt **strikt innen**
   in der Zelle liegt. Dadurch kommt eine gemeinsame Kante genau einmal vor -
   aus der Zelle,
4. behaltene Teilkanten zu Ringen verketten.

Greiner-Hormann und Weiler-Atherton scheitern genau an den Degenerationen, die
hier die Regel sind (Gitterlinie exakt auf der Rahmenkante, Zellecke auf der
Rahmenkante, kollineare Ueberlappung). Die Randklassifikation behandelt sie mit
zwei ausdruecklichen Regeln statt mit Sonderfaellen.

Das **Beschleunigungsraster** (:class:`PolygonGrid`) entscheidet die
ueberwiegende Mehrzahl der Zellen ohne jede Schnittrechnung: Zellen tief im
Rahmen bleiben unveraendert, Zellen ausserhalb fallen weg.
"""

from __future__ import annotations

import bisect
import math
from typing import Dict, List, Optional, Sequence, Tuple

from .geom import EPS, dist, ensure_ccw, lerp, point_in_polygon, polygon_area

Point = Tuple[float, float]

#: Bis zu diesem Abstand gilt ein Punkt als "auf dem Rand" (cm).
ON_TOL = 1e-7

#: Schnittparameter, die dichter beieinander liegen, sind derselbe Punkt.
PARAM_TOL = 1e-9

#: Nachkommastellen fuers Endpunkt-Matching beim Verketten (1e-7 cm).
CHAIN_PRECISION = 7

#: Ringe mit kleinerer Flaeche sind Rundungsreste (cm^2).
MIN_RING_AREA = 1e-10

#: Aufloesung des Beschleunigungsrasters je Achse.
GRID_N = 64

#: So viele Raster bleiben im Cache (die Vorschau baut den Container bei jeder
#: Reglerbewegung neu, der Rahmen bleibt dabei derselbe).
GRID_CACHE_LIMIT = 32

OUTSIDE, INSIDE, BOUNDARY = 0, 1, 2


# --------------------------------------------------------------- Grundlagen

def _clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    """Abstand eines Punktes von einer Strecke."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    if ll < EPS * EPS:
        return dist(p, a)
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll
    t = _clamp01(t)
    return math.hypot(p[0] - (a[0] + dx * t), p[1] - (a[1] + dy * t))


def point_on_boundary(p: Point, poly: Sequence[Point], eps: float = ON_TOL) -> bool:
    """Liegt ``p`` (bis auf ``eps``) auf dem Rand von ``poly``?"""
    n = len(poly)
    for i in range(n):
        if point_segment_distance(p, poly[i], poly[(i + 1) % n]) <= eps:
            return True
    return False


def inside_or_on(p: Point, poly: Sequence[Point], eps: float = ON_TOL) -> bool:
    """Innen oder auf dem Rand (die Regel fuer Zell-Teilkanten)."""
    return point_in_polygon(p, poly) or point_on_boundary(p, poly, eps)


def strictly_inside(p: Point, poly: Sequence[Point], eps: float = ON_TOL) -> bool:
    """Strikt innen (die Regel fuer Rahmen-Teilkanten)."""
    return point_in_polygon(p, poly) and not point_on_boundary(p, poly, eps)


def segment_intersections(a: Point, b: Point, c: Point, d: Point
                          ) -> List[Tuple[float, float]]:
    """Schnittparameter zweier Strecken als ``(t_ab, t_cd)``.

    Beruehrungen an den Enden zaehlen mit; bei **kollinearer Ueberlappung**
    kommen die beiden Endpunkte der Ueberlappung zurueck. Beides ist Absicht:
    genau daran zerbrechen die klassischen Clipping-Verfahren.
    """
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    lr = math.hypot(rx, ry)
    ls = math.hypot(sx, sy)
    if lr < EPS or ls < EPS:
        return []
    qx, qy = c[0] - a[0], c[1] - a[1]
    den = rx * sy - ry * sx
    if abs(den) > 1e-12 * lr * ls:
        t = (qx * sy - qy * sx) / den
        u = (qx * ry - qy * rx) / den
        if -PARAM_TOL <= t <= 1.0 + PARAM_TOL and -PARAM_TOL <= u <= 1.0 + PARAM_TOL:
            return [(_clamp01(t), _clamp01(u))]
        return []
    # parallel - nur kollineare Paare koennen sich ueberlappen
    if abs(qx * ry - qy * rx) / lr > ON_TOL:
        return []
    inv = 1.0 / (lr * lr)
    tc = (qx * rx + qy * ry) * inv
    td = ((d[0] - a[0]) * rx + (d[1] - a[1]) * ry) * inv
    lo, hi = (tc, td) if tc <= td else (td, tc)
    lo = max(lo, 0.0)
    hi = min(hi, 1.0)
    if hi < lo - PARAM_TOL:
        return []
    ts = [lo] if hi <= lo + PARAM_TOL else [lo, hi]
    inv_s = 1.0 / (ls * ls)
    out: List[Tuple[float, float]] = []
    for t in ts:
        px, py = a[0] + rx * t, a[1] + ry * t
        u = ((px - c[0]) * sx + (py - c[1]) * sy) * inv_s
        out.append((t, _clamp01(u)))
    return out


def _prep(poly: Sequence[Point]) -> List[Point]:
    """Doppelte Folgepunkte und den Schliesspunkt entfernen."""
    pts = [(float(x), float(y)) for x, y in poly]
    out: List[Point] = []
    for p in pts:
        if not out or dist(out[-1], p) > 1e-12:
            out.append(p)
    while len(out) > 1 and dist(out[0], out[-1]) <= 1e-12:
        out.pop()
    return out


def _edges(poly: Sequence[Point]) -> List[Tuple[Point, Point]]:
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)]


# ------------------------------------------------- Beschleunigungsraster

class PolygonGrid:
    """Grobraster ueber der Bounding-Box - Klassifikation **und** Kantenindex.

    Drei Dinge entstehen beim Aufbau:

    * je Rasterzelle ``INSIDE`` / ``OUTSIDE`` / ``BOUNDARY``. Die Paritaet des
      Zellmittelpunkts kommt zeilenweise per Scanline, danach werden alle
      Rasterzellen, durch die eine Kante laeuft, als ``BOUNDARY`` markiert.
    * je Rasterzelle die Kanten, die sie beruehren (``edges_near``). Ohne diesen
      Index muesste jede Musterzelle gegen **alle** Rahmenkanten getestet werden;
      bei einem tessellierten Rahmen sind das schnell einige hundert.
    * je Rasterzeile die Kanten, die sie schneiden - damit ist auch der exakte
      Punkt-in-Polygon-Test lokal statt ueber die ganze Kontur.

    Der Rahmen wird beim Aufbau einmal aufbereitet (Duplikate weg, CCW); alle
    Nutzer arbeiten danach mit ``grid.points`` und ``grid.edges``.
    """

    def __init__(self, points: Sequence[Point], n: int = GRID_N):
        pts = _prep(points)
        self.points = ensure_ccw(pts) if len(pts) >= 3 else pts
        self.edges = _edges(self.points) if len(self.points) >= 3 else []
        self.n = max(1, int(n))
        xs = [p[0] for p in self.points] or [0.0]
        ys = [p[1] for p in self.points] or [0.0]
        self.x0, self.x1 = min(xs), max(xs)
        self.y0, self.y1 = min(ys), max(ys)
        self.cw = max((self.x1 - self.x0) / self.n, 1e-12)
        self.ch = max((self.y1 - self.y0) / self.n, 1e-12)
        self.cells = bytearray(self.n * self.n)
        self.buckets: Dict[int, List[int]] = {}
        self.row_edges: List[List[int]] = [[] for _ in range(self.n)]
        self._fill()
        self._index_edges()

    # -- Aufbau ----------------------------------------------------------
    def _fill(self) -> None:
        poly = self.points
        m = len(poly)
        if m < 3:
            return
        n = self.n
        for j in range(n):
            y = self.y0 + (j + 0.5) * self.ch
            xs: List[float] = []
            for i in range(m):
                ax, ay = poly[i]
                bx, by = poly[(i + 1) % m]
                if (ay > y) != (by > y):
                    xs.append(ax + (y - ay) * (bx - ax) / (by - ay))
            if not xs:
                continue
            xs.sort()
            row = j * n
            for i in range(n):
                x = self.x0 + (i + 0.5) * self.cw
                if bisect.bisect_right(xs, x) % 2:
                    self.cells[row + i] = INSIDE

    def _index_edges(self) -> None:
        n = self.n
        step = 0.5 * min(self.cw, self.ch)
        cells = self.cells
        for e, (a, b) in enumerate(self.edges):
            # Zeilenindex ueber die y-Ausdehnung
            j0 = self._row(min(a[1], b[1]))
            j1 = self._row(max(a[1], b[1]))
            for j in range(j0, j1 + 1):
                self.row_edges[j].append(e)
            # Rasterzellen entlang der Kante (mit Nachbarschaft, damit auch ein
            # nur angeschnittenes Eck erfasst ist)
            touched = set()
            steps = max(1, int(dist(a, b) / step) + 1)
            for k in range(steps + 1):
                ix, iy = self._cell(lerp(a, b, k / float(steps)))
                for dy in (-1, 0, 1):
                    yy = iy + dy
                    if yy < 0 or yy >= n:
                        continue
                    for dx in (-1, 0, 1):
                        xx = ix + dx
                        if 0 <= xx < n:
                            touched.add(yy * n + xx)
            for idx in touched:
                cells[idx] = BOUNDARY
                self.buckets.setdefault(idx, []).append(e)

    def _row(self, y: float) -> int:
        return min(self.n - 1, max(0, int((y - self.y0) / self.ch)))

    def _cell(self, p: Point) -> Tuple[int, int]:
        ix = int((p[0] - self.x0) / self.cw)
        iy = int((p[1] - self.y0) / self.ch)
        return (min(self.n - 1, max(0, ix)), min(self.n - 1, max(0, iy)))

    # -- exakte Tests, lokal beschleunigt --------------------------------
    def point_in(self, p: Point) -> bool:
        """Ray-Casting, aber nur ueber die Kanten der eigenen Rasterzeile."""
        x, y = p
        poly = self.points
        m = len(poly)
        inside = False
        for i in self.row_edges[self._row(y)]:
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % m]
            if (ay > y) != (by > y):
                if x < ax + (y - ay) * (bx - ax) / (by - ay):
                    inside = not inside
        return inside

    def on_boundary(self, p: Point, eps: float = ON_TOL) -> bool:
        ix, iy = self._cell(p)
        poly = self.points
        m = len(poly)
        for i in self.buckets.get(iy * self.n + ix, ()):
            if point_segment_distance(p, poly[i], poly[(i + 1) % m]) <= eps:
                return True
        return False

    def edges_near(self, x0: float, y0: float, x1: float, y1: float) -> List[int]:
        """Kantenindizes, die in der Naehe des Rechtecks liegen koennen.

        Die Reihenfolge folgt dem Raster - deterministisch, aber ohne den
        Sortierschritt, der bei einigen tausend Aufrufen je Muster ins Gewicht
        faellt.
        """
        i0, j0 = self._cell((x0, y0))
        i1, j1 = self._cell((x1, y1))
        buckets = self.buckets
        if i0 == i1 and j0 == j1:
            return buckets.get(j0 * self.n + i0, [])
        found: List[int] = []
        seen = set()
        for j in range(j0, j1 + 1):
            row = j * self.n
            for i in range(i0, i1 + 1):
                for e in buckets.get(row + i, ()):
                    if e not in seen:
                        seen.add(e)
                        found.append(e)
        return found

    # -- Abfragen --------------------------------------------------------
    def cell_state(self, p: Point) -> int:
        # Der Rand der Bounding-Box bekommt dieselbe Toleranz wie der Rand der
        # Kontur: ein Punkt, der rechnerisch um ein Bit darueber liegt (etwa
        # ``2.85 - 0.05 = 2.8000000000000003``), gilt sonst als aussen - und
        # damit faellt eine ganze Randzelle weg.
        if (p[0] < self.x0 - ON_TOL or p[0] > self.x1 + ON_TOL
                or p[1] < self.y0 - ON_TOL or p[1] > self.y1 + ON_TOL):
            return OUTSIDE
        ix, iy = self._cell(p)
        return self.cells[iy * self.n + ix]

    def contains(self, p: Point) -> bool:
        st = self.cell_state(p)
        if st != BOUNDARY:
            return st == INSIDE
        return self.point_in(p)

    def inside_or_on(self, p: Point, eps: float = ON_TOL) -> bool:
        st = self.cell_state(p)
        if st == INSIDE:
            return True
        if st == OUTSIDE:
            return False
        return self.point_in(p) or self.on_boundary(p, eps)

    def strictly_inside(self, p: Point, eps: float = ON_TOL) -> bool:
        st = self.cell_state(p)
        if st != BOUNDARY:
            return st == INSIDE
        return self.point_in(p) and not self.on_boundary(p, eps)

    def classify_bbox(self, x0: float, y0: float, x1: float, y1: float) -> str:
        """``"inside"`` / ``"outside"`` / ``"mixed"`` fuer ein Rechteck."""
        if (x1 < self.x0 - ON_TOL or x0 > self.x1 + ON_TOL
                or y1 < self.y0 - ON_TOL or y0 > self.y1 + ON_TOL):
            return "outside"
        outside_part = (x0 < self.x0 or x1 > self.x1
                        or y0 < self.y0 or y1 > self.y1)
        i0, j0 = self._cell((x0, y0))
        i1, j1 = self._cell((x1, y1))
        first = self.cells[j0 * self.n + i0]
        if first == BOUNDARY:
            return "mixed"
        for j in range(j0, j1 + 1):
            row = j * self.n
            for i in range(i0, i1 + 1):
                if self.cells[row + i] != first:
                    return "mixed"
        if first == INSIDE:
            return "mixed" if outside_part else "inside"
        return "outside"


_GRID_CACHE: Dict[Tuple, PolygonGrid] = {}


def grid_for(points: Sequence[Point]) -> PolygonGrid:
    """Raster zu einer Punktfolge - mit Cache (Schluessel = die Punkte)."""
    key = tuple((float(x), float(y)) for x, y in points)
    grid = _GRID_CACHE.get(key)
    if grid is None:
        grid = PolygonGrid(key)
        if len(_GRID_CACHE) >= GRID_CACHE_LIMIT:
            _GRID_CACHE.pop(next(iter(_GRID_CACHE)))
        _GRID_CACHE[key] = grid
    return grid


# ------------------------------------------------------------- Hilfsmittel

def _bbox(pts: Sequence[Point]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _split(a: Point, b: Point, params: Sequence[float]) -> List[Tuple[Point, Point]]:
    """Kante an den Schnittparametern aufteilen."""
    ts: List[float] = []
    for t in sorted(params):
        if t <= PARAM_TOL or t >= 1.0 - PARAM_TOL:
            continue
        if ts and t - ts[-1] <= PARAM_TOL:
            continue
        ts.append(t)
    pts = [a] + [lerp(a, b, t) for t in ts] + [b]
    out: List[Tuple[Point, Point]] = []
    for i in range(len(pts) - 1):
        if dist(pts[i], pts[i + 1]) > 1e-12:
            out.append((pts[i], pts[i + 1]))
    return out


def _chain_rings(segments: Sequence[Tuple[Point, Point]]) -> List[List[Point]]:
    """Gerichtete Teilkanten zu geschlossenen Ringen verketten.

    Die Rundung auf :data:`CHAIN_PRECISION` dient nur dem **Wiederfinden** der
    Endpunkte; in den Ring kommen die urspruenglichen Koordinaten. Sonst
    wanderten alle Punkte um bis zu einen halben Rundungsschritt - gegen einen
    rechteckigen Rahmen kaeme dann nicht mehr exakt dasselbe heraus wie aus dem
    konvexen Clipper.

    An einem Knoten mit mehreren Fortsetzungen (die Zelle beruehrt den Rahmen in
    einem Punkt) wird die **am weitesten im Uhrzeigersinn** liegende Kante
    genommen. So bleibt das Innere links und es entstehen die kleinsten Ringe -
    aus einer Acht werden zwei Schlaufen statt einer sich selbst schneidenden
    Kontur.
    """
    canon: Dict[Point, Point] = {}

    def key(p: Point) -> Point:
        k = (round(p[0], CHAIN_PRECISION), round(p[1], CHAIN_PRECISION))
        if k not in canon:
            canon[k] = (float(p[0]), float(p[1]))
        return k

    out_edges: Dict[Point, List[Point]] = {}
    ordered: List[Tuple[Point, Point]] = []
    seen = set()
    for a, b in segments:
        ka, kb = key(a), key(b)
        if ka == kb or (ka, kb) in seen:
            continue
        seen.add((ka, kb))
        ordered.append((ka, kb))
        out_edges.setdefault(ka, []).append(kb)

    used = set()

    def pick(prev: Point, cur: Point) -> Optional[Point]:
        cands = [b for b in out_edges.get(cur, ()) if (cur, b) not in used]
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        vx, vy = cur[0] - prev[0], cur[1] - prev[1]
        best, best_ang = None, None
        for b in cands:
            wx, wy = b[0] - cur[0], b[1] - cur[1]
            # Winkel von der Rueckrichtung (-v) im Uhrzeigersinn zu w
            ang = math.atan2(-vx * wy + vy * wx, -vx * wx - vy * wy)
            if ang <= 1e-12:
                ang += 2 * math.pi
            if best_ang is None or ang < best_ang:
                best, best_ang = b, ang
        return best

    rings: List[List[Point]] = []
    for start, first in ordered:
        if (start, first) in used:
            continue
        ring = [start]
        prev, cur = start, first
        while True:
            used.add((prev, cur))
            ring.append(cur)
            if cur == start:
                break
            nxt = pick(prev, cur)
            if nxt is None:
                ring = []
                break
            prev, cur = cur, nxt
        if len(ring) < 4 or ring[0] != ring[-1]:
            continue
        poly = [canon[k] for k in ring[:-1]]
        if abs(polygon_area(poly)) <= MIN_RING_AREA:
            continue
        rings.append(ensure_ccw(poly))
    return rings


# ---------------------------------------------------------------- Clipping

def clip_polygon_general(subject: Sequence[Point], frame: Sequence[Point],
                         grid: Optional[PolygonGrid] = None) -> List[List[Point]]:
    """Schnitt zweier einfacher Polygone - beide duerfen konkav sein.

    Liefert die Teilstuecke (CCW). Mehrere Stuecke entstehen, wenn eine
    Einbuchtung des Rahmens die Zelle zerteilt. ``grid`` ist das (gecachte)
    Raster des Rahmens; wer es hat, spart den Cache-Zugriff je Zelle.
    """
    subj = _prep(subject)
    if len(subj) < 3:
        return []
    subj = ensure_ccw(subj)
    grid = grid or grid_for(frame)
    fr = grid.points
    if len(fr) < 3:
        return []

    sx0, sy0, sx1, sy1 = _bbox(subj)
    cls = grid.classify_bbox(sx0, sy0, sx1, sy1)
    if cls == "outside":
        return []
    if cls == "inside":
        return [subj]

    se = _edges(subj)
    # Nur Rahmenkanten in der Naehe der Zelle koennen etwas beitragen: alles
    # andere liegt ausserhalb der Zell-Bounding-Box und damit ausserhalb der
    # Zelle. Das ist der Unterschied zwischen "geht" und "dauert ewig".
    near = grid.edges_near(sx0, sy0, sx1, sy1)
    s_params: List[List[float]] = [[] for _ in se]
    f_params: Dict[int, List[float]] = {}
    hits = False
    for i, (a, b) in enumerate(se):
        ax0, ax1 = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        ay0, ay1 = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        for j in near:
            c, d = grid.edges[j]
            if (max(c[0], d[0]) < ax0 - ON_TOL or min(c[0], d[0]) > ax1 + ON_TOL
                    or max(c[1], d[1]) < ay0 - ON_TOL or min(c[1], d[1]) > ay1 + ON_TOL):
                continue
            for t, u in segment_intersections(a, b, c, d):
                s_params[i].append(t)
                f_params.setdefault(j, []).append(u)
                hits = True

    if not hits:
        # Ohne Kantenschnitte liegt entweder alles ineinander oder nichts.
        if grid.inside_or_on(subj[0]):
            return [subj]
        if point_in_polygon(fr[0], subj):
            return [fr]
        return []

    # Fuer die Zelle kein Raster: sie ist bei jedem Aufruf eine andere, der
    # Rasteraufbau kostete mehr als der direkte Test auf zwei Dutzend Kanten.
    kept: List[Tuple[Point, Point]] = []
    for i, (a, b) in enumerate(se):
        for p, q in _split(a, b, s_params[i]):
            if grid.inside_or_on(((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)):
                kept.append((p, q))
    for j in near:
        c, d = grid.edges[j]
        for p, q in _split(c, d, f_params.get(j, ())):
            if strictly_inside(((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0), subj):
                kept.append((p, q))
    return _chain_rings(kept)


def clip_polyline_general(pts: Sequence[Point], frame: Sequence[Point],
                          closed: bool = False,
                          grid: Optional[PolygonGrid] = None) -> List[List[Point]]:
    """Polylinie gegen einen beliebigen Rahmen beschneiden.

    Segmentweise: Schnittparameter mit allen Rahmenkanten sammeln, Teilsegmente
    ueber ihren Mittelpunkt einordnen, benachbarte behaltene Stuecke wieder
    verketten. Das ist dasselbe Vorgehen wie in ``clip.clip_polyline`` - nur
    ohne die Voraussetzung, dass der Rahmen konvex ist.
    """
    src = _prep(pts) if closed else [(float(x), float(y)) for x, y in pts]
    if len(src) < 2:
        return []
    grid = grid or grid_for(frame)
    if len(grid.points) < 3:
        return []
    if closed and len(src) > 2:
        src = list(src) + [src[0]]

    pieces: List[List[Point]] = []
    current: List[Point] = []

    def flush() -> None:
        if len(current) > 1:
            pieces.append(list(current))
        del current[:]

    for k in range(len(src) - 1):
        a, b = src[k], src[k + 1]
        if dist(a, b) < 1e-12:
            continue
        x0, x1 = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        y0, y1 = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        params: List[float] = []
        for j in grid.edges_near(x0, y0, x1, y1):
            c, d = grid.edges[j]
            for t, _u in segment_intersections(a, b, c, d):
                params.append(t)
        for p, q in _split(a, b, params):
            mid = ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)
            if not grid.inside_or_on(mid):
                flush()
                continue
            if not current:
                current.extend((p, q))
            elif dist(current[-1], p) <= 1e-9:
                current.append(q)
            else:
                flush()
                current.extend((p, q))
    flush()
    return [_dedupe(p) for p in pieces if len(p) > 1]


def _dedupe(pts: Sequence[Point], tol: float = 1e-9) -> List[Point]:
    out: List[Point] = []
    for p in pts:
        if not out or dist(out[-1], p) > tol:
            out.append(p)
    return out


def polygon_fully_inside(pts: Sequence[Point], frame: Sequence[Point],
                         closed: bool = True,
                         grid: Optional[PolygonGrid] = None) -> bool:
    """Liegt die Kontur vollstaendig im Rahmen (Rand zaehlt als innen)?"""
    poly = _prep(pts) if closed else [(float(x), float(y)) for x, y in pts]
    if not poly:
        return False
    grid = grid or grid_for(frame)
    if len(grid.points) < 3:
        return False
    x0, y0, x1, y1 = _bbox(poly)
    cls = grid.classify_bbox(x0, y0, x1, y1)
    if cls == "inside":
        return True
    if cls == "outside":
        return False
    for p in poly:
        if not grid.inside_or_on(p):
            return False
    n = len(poly)
    rng = range(n) if closed else range(n - 1)
    near = grid.edges_near(x0, y0, x1, y1)
    for i in rng:
        a, b = poly[i], poly[(i + 1) % n]
        if dist(a, b) < 1e-12:
            continue
        if not grid.inside_or_on(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)):
            return False
        for j in near:
            c, d = grid.edges[j]
            for t, u in segment_intersections(a, b, c, d):
                if (PARAM_TOL < t < 1.0 - PARAM_TOL
                        and PARAM_TOL < u < 1.0 - PARAM_TOL):
                    return False
    return True
