"""Kleine, abhaengigkeitsfreie Geometrie-Helfer (reines Python, kein numpy)."""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]

EPS = 1e-9


# ---------------------------------------------------------------- Vektoren

def add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def mul(a: Point, s: float) -> Point:
    return (a[0] * s, a[1] * s)


def dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def length(a: Point) -> float:
    return math.hypot(a[0], a[1])


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize(a: Point) -> Point:
    l = length(a)
    if l < EPS:
        return (0.0, 0.0)
    return (a[0] / l, a[1] / l)


def rotate(p: Point, angle: float, origin: Point = (0.0, 0.0)) -> Point:
    ca, sa = math.cos(angle), math.sin(angle)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return (origin[0] + dx * ca - dy * sa, origin[1] + dx * sa + dy * ca)


def lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


# ---------------------------------------------------------------- Polygone

def polygon_area(pts: Sequence[Point]) -> float:
    """Vorzeichenbehaftete Flaeche (positiv = gegen den Uhrzeigersinn)."""
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s * 0.5


def centroid(pts: Sequence[Point]) -> Point:
    a = polygon_area(pts)
    if abs(a) < EPS:
        n = max(1, len(pts))
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        f = x0 * y1 - x1 * y0
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return (cx / (6.0 * a), cy / (6.0 * a))


def ensure_ccw(pts: Sequence[Point]) -> List[Point]:
    return list(pts) if polygon_area(pts) >= 0 else list(reversed(pts))


def point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    """Ray-Casting; Randpunkte gelten als innen (tolerant)."""
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            t = (y - y0) / (y1 - y0)
            if x < x0 + t * (x1 - x0):
                inside = not inside
    return inside


def bbox(pts: Iterable[Point]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_of_paths(paths: Iterable[Sequence[Point]]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for p in paths:
        for x, y in p:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def polyline_length(pts: Sequence[Point], closed: bool = False) -> float:
    total = 0.0
    n = len(pts)
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        total += dist(pts[i], pts[(i + 1) % n])
    return total


# ------------------------------------------------------------ Bearbeitung

def chaikin(pts: Sequence[Point], iterations: int = 1, closed: bool = True) -> List[Point]:
    """Chaikin-Eckenglaettung: macht aus eckigen Zellen runde "Kiesel"."""
    out = list(pts)
    for _ in range(max(0, int(iterations))):
        if len(out) < 3:
            break
        new: List[Point] = []
        n = len(out)
        rng = range(n) if closed else range(n - 1)
        if not closed:
            new.append(out[0])
        for i in rng:
            a = out[i]
            b = out[(i + 1) % n]
            new.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            new.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        if not closed:
            new.append(out[-1])
        out = new
    return out


def resample(pts: Sequence[Point], step: float, closed: bool = False) -> List[Point]:
    """Polylinie mit ungefaehr konstantem Punktabstand neu abtasten."""
    if len(pts) < 2 or step <= 0:
        return list(pts)
    src = list(pts) + ([pts[0]] if closed else [])
    out = [src[0]]
    carry = 0.0
    for i in range(len(src) - 1):
        a, b = src[i], src[i + 1]
        seg = dist(a, b)
        if seg < EPS:
            continue
        t = step - carry
        while t <= seg:
            out.append(lerp(a, b, t / seg))
            t += step
        carry = (carry + seg) % step
    if not closed and dist(out[-1], src[-1]) > EPS:
        out.append(src[-1])
    return out


def dedupe_key(a: Point, b: Point, precision: int = 5) -> Tuple:
    """Richtungsunabhaengiger Schluessel fuer eine Kante (Deduplizierung)."""
    ka = (round(a[0], precision), round(a[1], precision))
    kb = (round(b[0], precision), round(b[1], precision))
    return (ka, kb) if ka <= kb else (kb, ka)


def dedupe_segments(segments: Iterable[Tuple[Point, Point]], precision: int = 5
                    ) -> List[Tuple[Point, Point]]:
    """Doppelte Kanten entfernen - Pflicht, damit Profile nicht brechen."""
    seen = set()
    out: List[Tuple[Point, Point]] = []
    for a, b in segments:
        if dist(a, b) < 1e-7:
            continue
        k = dedupe_key(a, b, precision)
        if k in seen:
            continue
        seen.add(k)
        out.append((a, b))
    return out


def snap_segments(segments: Iterable[Tuple[Point, Point]], precision: int = 4
                  ) -> List[Tuple[Point, Point]]:
    """Endpunkte auf ein Raster fangen und doppelte Kanten entfernen.

    Zellen benachbarter Generatoren berechnen gemeinsame Ecken unabhaengig
    voneinander; ohne Fangen weichen sie um Gleitkomma-Rauschen ab und die
    Deduplizierung greift nicht (-> doppelte Kanten, kaputte Profile).
    """
    canon: dict = {}

    def key(p: Point) -> Point:
        k = (round(p[0], precision), round(p[1], precision))
        if k not in canon:
            canon[k] = k
        return canon[k]

    seen = set()
    out: List[Tuple[Point, Point]] = []
    for a, b in segments:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        ek = (ka, kb) if ka <= kb else (kb, ka)
        if ek in seen:
            continue
        seen.add(ek)
        out.append((ka, kb))
    return out


def chain_segments(segments: Sequence[Tuple[Point, Point]]) -> List[Tuple[List[Point], bool]]:
    """Segmente zu moeglichst langen Polylinien verketten.

    Liefert ``(punkte, geschlossen)``. Knoten mit Grad != 2 beenden eine Kette;
    dadurch entstehen deutlich weniger Skizzen-Entities als bei Einzelsegmenten.
    """
    adj: dict = {}
    for a, b in segments:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    used = set()

    def edge_key(a: Point, b: Point):
        return (a, b) if a <= b else (b, a)

    chains: List[Tuple[List[Point], bool]] = []

    def walk(start: Point, nxt: Point) -> List[Point]:
        pts = [start, nxt]
        used.add(edge_key(start, nxt))
        prev, cur = start, nxt
        while len(adj.get(cur, ())) == 2:
            a, b = adj[cur]
            follow = b if a == prev else a
            k = edge_key(cur, follow)
            if k in used:
                break
            used.add(k)
            pts.append(follow)
            prev, cur = cur, follow
            if follow == start:
                break
        return pts

    # 1. Ketten, die an einem Knoten mit Grad != 2 beginnen
    for node in sorted(adj.keys()):
        if len(adj[node]) == 2:
            continue
        for nb in list(adj[node]):
            if edge_key(node, nb) in used:
                continue
            pts = walk(node, nb)
            chains.append((pts, False))
    # 2. verbleibende Ringe (alle Knoten Grad 2)
    for a, b in segments:
        if edge_key(a, b) in used:
            continue
        pts = walk(a, b)
        closed = len(pts) > 2 and pts[0] == pts[-1]
        if closed:
            pts = pts[:-1]
        chains.append((pts, closed))
    return chains


def polygon_segments(poly: Sequence[Point]) -> List[Tuple[Point, Point]]:
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)]


def inset_polygon(pts: Sequence[Point], delta: float) -> Optional[List[Point]]:
    """Konvexes/leicht konkaves Polygon um ``delta`` nach innen versetzen.

    Arbeitet mit Winkelhalbierenden. Kollabiert das Polygon, wird ``None``
    zurueckgegeben (die Zelle ist dann zu klein fuer den gewaehlten Inset).
    """
    if len(pts) < 3 or delta <= 0:
        return list(pts) if len(pts) >= 3 else None
    poly = ensure_ccw([p for i, p in enumerate(pts)
                       if dist(p, pts[i - 1]) > 1e-12 or i == 0])
    n = len(poly)
    if n < 3:
        return None
    out: List[Point] = []
    for i in range(n):
        p_prev = poly[(i - 1) % n]
        p = poly[i]
        p_next = poly[(i + 1) % n]
        d0 = normalize(sub(p, p_prev))
        d1 = normalize(sub(p_next, p))
        if length(d0) < EPS or length(d1) < EPS:
            return None
        # Innen-Normalen (CCW -> links von der Laufrichtung)
        n0 = (-d0[1], d0[0])
        n1 = (-d1[1], d1[0])
        m = add(n0, n1)
        lm = length(m)
        if lm < 1e-6:                       # ~180°-Ruecklauf
            return None
        miter = min(2.0 * delta / lm, delta * 6.0)   # Gehrung begrenzen
        out.append(add(p, mul((m[0] / lm, m[1] / lm), miter)))
    # Kollaps erkennen: kehrt eine Kante ihre Richtung um, ist das Polygon
    # "durchgeschlagen" (Inset groesser als die halbe Zellbreite).
    for i in range(n):
        before = sub(poly[(i + 1) % n], poly[i])
        after = sub(out[(i + 1) % n], out[i])
        if dot(before, after) <= 0:
            return None
    area_before = abs(polygon_area(poly))
    area_after = abs(polygon_area(out))
    if area_after < 1e-9 or area_after >= area_before:
        return None
    return out


def catmull_rom(pts: Sequence[Point], samples: int = 8, closed: bool = False) -> List[Point]:
    """Catmull-Rom-Interpolation - nur fuer Laengen-/Flaechenrechnungen und Tests.

    Fusion bekommt die Stuetzpunkte direkt als ``sketchFittedSplines``.
    """
    n = len(pts)
    if n < 3:
        return list(pts)
    out: List[Point] = []
    idx = range(n) if closed else range(n - 1)
    for i in idx:
        p0 = pts[(i - 1) % n] if closed else pts[max(0, i - 1)]
        p1 = pts[i % n]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed else pts[min(n - 1, i + 2)]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    if not closed:
        out.append(pts[-1])
    return out


def regular_polygon(center: Point, radius: float, sides: int, rotation: float = 0.0
                    ) -> List[Point]:
    return [
        (center[0] + radius * math.cos(rotation + 2 * math.pi * i / sides),
         center[1] + radius * math.sin(rotation + 2 * math.pi * i / sides))
        for i in range(sides)
    ]


def circle_points(center: Point, radius: float, segments: int = 96) -> List[Point]:
    return regular_polygon(center, radius, segments, 0.0)


def ellipse_points(center: Point, rx: float, ry: float, segments: int = 96,
                   rotation: float = 0.0) -> List[Point]:
    out = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        p = (rx * math.cos(a), ry * math.sin(a))
        p = rotate(p, rotation)
        out.append((center[0] + p[0], center[1] + p[1]))
    return out


def rounded_rect_points(cx: float, cy: float, w: float, h: float, r: float,
                        corner_segments: int = 12) -> List[Point]:
    """Rechteck (ggf. mit Eckenradius) als Polygon, gegen den Uhrzeigersinn."""
    hw, hh = w / 2.0, h / 2.0
    r = max(0.0, min(r, hw - 1e-6, hh - 1e-6)) if r > 0 else 0.0
    if r <= 0:
        return [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)]
    pts: List[Point] = []
    corners = [
        (cx + hw - r, cy - hh + r, -math.pi / 2),
        (cx + hw - r, cy + hh - r, 0.0),
        (cx - hw + r, cy + hh - r, math.pi / 2),
        (cx - hw + r, cy - hh + r, math.pi),
    ]
    for ccx, ccy, a0 in corners:
        for i in range(corner_segments + 1):
            a = a0 + (math.pi / 2) * i / corner_segments
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def poisson_disk(x0: float, y0: float, x1: float, y1: float, radius: float, rnd,
                 attempts: int = 20, max_points: int = 5000) -> List[Point]:
    """Bridson-Poisson-Disk-Sampling (deterministisch ueber ``rnd``)."""
    if radius <= 0:
        return []
    cell = radius / math.sqrt(2)
    gw = max(1, int(math.ceil((x1 - x0) / cell)))
    gh = max(1, int(math.ceil((y1 - y0) / cell)))
    grid: List[Optional[Point]] = [None] * (gw * gh)

    def grid_idx(p: Point) -> Tuple[int, int]:
        return (min(gw - 1, max(0, int((p[0] - x0) / cell))),
                min(gh - 1, max(0, int((p[1] - y0) / cell))))

    def fits(p: Point) -> bool:
        gx, gy = grid_idx(p)
        for iy in range(max(0, gy - 2), min(gh, gy + 3)):
            for ix in range(max(0, gx - 2), min(gw, gx + 3)):
                q = grid[iy * gw + ix]
                if q is not None and dist(p, q) < radius:
                    return False
        return True

    first = (x0 + (x1 - x0) * rnd.random(), y0 + (y1 - y0) * rnd.random())
    samples = [first]
    active = [first]
    gx, gy = grid_idx(first)
    grid[gy * gw + gx] = first

    while active and len(samples) < max_points:
        i = rnd.randrange(len(active))
        base = active[i]
        found = False
        for _ in range(attempts):
            a = rnd.random() * 2 * math.pi
            r = radius * (1 + rnd.random())
            p = (base[0] + r * math.cos(a), base[1] + r * math.sin(a))
            if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
                continue
            if fits(p):
                samples.append(p)
                active.append(p)
                ggx, ggy = grid_idx(p)
                grid[ggy * gw + ggx] = p
                found = True
                break
        if not found:
            active.pop(i)
    return samples
