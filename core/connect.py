"""Verbinder-Stege: aus vielen frei stehenden Motiven wird **ein** Teil.

Streu-Muster (Phyllotaxis, Motiv-Streuung) kacheln nicht. Im Flaechenmodus
entsteht daraus kein zusammenhaengendes Stegnetz, sondern eine Wolke einzelner
Inseln - jeder Kreisring, jede Blattkontur ein eigener schwebender Koerper.
Gedruckt werden daraus lauter lose Teile.

Dieses Modul zieht duenne Stege dazwischen:

1. **Inseln finden.** Was sich beim Extrudieren ohnehin zu einem Koerper
   verbindet, ist eine Insel (siehe :func:`islands`).
2. **Nachbar-Netz.** Ein minimaler Spannbaum ueber die Inselschwerpunkte
   verbindet jede Insel mit ihrem naechsten Nachbarn - k-1 Stege fuer k Inseln,
   also so wenig Material wie moeglich.
3. **Rahmen-Verankerung.** Mit gezeichnetem Rahmen wird das Netz zusaetzlich im
   Rahmenband verankert, sonst haengt das Muster zwar zusammen, schwebt aber
   frei im Rahmen.

Jeder Steg wird an beiden Enden in die Motive hinein verlaengert - dasselbe
Idiom wie bei der Schraffur (``core/hatch.py``): ueberlappende geschlossene
Profile werden beim Extrudieren zu **einem** Koerper.

Reines Python, deterministisch, kein Zufall: gleicher Seed + gleiche Parameter
ergeben dieselben Stege.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import ir
from .geom import _segments_cross, point_in_polygon
from .stroker import stroke

Point = Tuple[float, float]

#: Kuerzere Stege sind ueberfluessig - die Motive beruehren sich dort schon.
MIN_SPAN = 1e-9

#: So viele Rahmen-Anker mindestens, damit das Muster nicht an einem Punkt haengt.
MIN_FRAME_ANCHORS = 2


# ------------------------------------------------------------------ Inseln

def outlines(elements: Sequence[Any]) -> List[Tuple[int, List[Point]]]:
    """Geschlossene Musterkonturen als ``(Index, Polygon)``.

    Rahmen, Text und Deko bleiben aussen vor: der Rahmen ist das Ziel der
    Verankerung (keine Insel), Text und Deko werden nicht verbunden.
    """
    out: List[Tuple[int, List[Point]]] = []
    for i, el in enumerate(elements):
        if getattr(el, "layer", "") != ir.LAYER_PATTERN:
            continue
        if getattr(el, "role", "") == ir.ROLE_DECOR:
            continue
        if isinstance(el, ir.Circle):
            out.append((i, _circle_polygon(el.center, el.radius)))
        elif isinstance(el, ir.Path) and el.closed and len(el.points) >= 3:
            out.append((i, list(el.points)))
    return out


def _circle_polygon(center: Point, radius: float, segments: int = 32) -> List[Point]:
    return [(center[0] + radius * math.cos(2 * math.pi * i / segments),
             center[1] + radius * math.sin(2 * math.pi * i / segments))
            for i in range(segments)]


def _bbox(poly: Sequence[Point]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def _inner_point(poly: Sequence[Point], eps: float = 1e-7) -> Point:
    """Ein Punkt sicher **innerhalb** der Kontur.

    Ein Eckpunkt taugt dafuer nicht: beschnittene Motive haben ihre Kante exakt
    auf der Rahmenkante, und ``point_in_polygon`` ist auf der Grenze nicht
    entscheidbar. Deshalb die Mitte der laengsten Kante, ein Haar nach innen
    versetzt.
    """
    n = len(poly)
    i = max(range(n), key=lambda k: ((poly[(k + 1) % n][0] - poly[k][0]) ** 2
                                     + (poly[(k + 1) % n][1] - poly[k][1]) ** 2, -k))
    a, b = poly[i], poly[(i + 1) % n]
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = math.hypot(dx, dy)
    if ll < eps:
        return mid
    # Innen-Normale; bei umgekehrtem Umlaufsinn zeigt sie nach aussen, deshalb
    # die Richtung an der Flaeche pruefen.
    sign = 1.0 if _signed_area(poly) >= 0.0 else -1.0
    return (mid[0] - dy / ll * eps * sign, mid[1] + dx / ll * eps * sign)


def _signed_area(poly: Sequence[Point]) -> float:
    n = len(poly)
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
                     for i in range(n))


def _segments_with_boxes(poly: Sequence[Point]) -> List[Tuple[Point, Point, float,
                                                              float, float, float]]:
    """Kanten mit ihrem Huellrechteck - der Vorfilter fuer den Schnitttest."""
    n = len(poly)
    out = []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        out.append((a, b, min(a[0], b[0]), min(a[1], b[1]),
                    max(a[0], b[0]), max(a[1], b[1])))
    return out


def _boundaries_cross(sa: Sequence[tuple], sb: Sequence[tuple]) -> bool:
    """Schneiden sich zwei Konturen?

    Der Huellrechteck-Vorfilter ist hier nicht Feinschliff, sondern
    entscheidend: zwei 32-Eck-Ringe waeren sonst 1024 volle Schnitttests, und
    davon gibt es bei 500 Motiven einige hundert je Aufbau.
    """
    for a, b, ax0, ay0, ax1, ay1 in sa:
        for c, d, bx0, by0, bx1, by1 in sb:
            if bx0 > ax1 or bx1 < ax0 or by0 > ay1 or by1 < ay0:
                continue
            if _segments_cross(a, b, c, d) is not None:
                return True
    return False


class _Sets:
    """Union-Find."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        a, b = self.find(i), self.find(j)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def _neighbour_pairs(boxes: Sequence[Tuple[float, float, float, float]]
                     ) -> List[Tuple[int, int]]:
    """Kandidatenpaare ueber ein Raster - O(n^2) waere bei 500 Motiven zaeh."""
    n = len(boxes)
    if n < 2:
        return []
    span = max(max(b[2] - b[0], b[3] - b[1]) for b in boxes)
    cell = max(span, 1e-6)
    buckets: Dict[Tuple[int, int], List[int]] = {}
    for i, b in enumerate(boxes):
        for gx in range(int(math.floor(b[0] / cell)), int(math.floor(b[2] / cell)) + 1):
            for gy in range(int(math.floor(b[1] / cell)),
                            int(math.floor(b[3] / cell)) + 1):
                buckets.setdefault((gx, gy), []).append(i)
    pairs = set()
    for (gx, gy), members in buckets.items():
        near: List[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near.extend(buckets.get((gx + dx, gy + dy), ()))
        for i in members:
            bi = boxes[i]
            for j in near:
                if j <= i:
                    continue
                bj = boxes[j]
                if bi[2] < bj[0] or bj[2] < bi[0] or bi[3] < bj[1] or bj[3] < bi[1]:
                    continue
                pairs.add((i, j))
    return sorted(pairs)


def islands(elements: Sequence[Any]) -> List[List[int]]:
    """Konturen zu Inseln buendeln - eine Insel = ein extrudierter Koerper.

    Zwei Konturen gehoeren zusammen, wenn sie sich **schneiden** (ueberlappende
    Profile verschmelzen beim Extrudieren) oder wenn die eine in der anderen
    liegt. Das Umschliessen ist noetig, damit ein Kreisring (Aussen- plus
    Innenkontur) eine Insel ist und nicht zwei.

    Die Regel gilt bewusst nur fuer den Musterlayer. Der Rahmen ist ein *Band*:
    er umschliesst alles, ohne es zu beruehren - er wird deshalb in
    :func:`outlines` ausgelassen und getrennt verankert. Innerhalb des Musters
    ist die Regel dagegen sicher: was ineinander liegt, haengt dort auch
    zusammen (die Blattrippen liegen in der Blattkontur und sind ueber die
    Mittelrippe ohnehin mit ihr verbunden).
    """
    polys = [poly for _, poly in outlines(elements)]
    n = len(polys)
    if n == 0:
        return []
    boxes = [_bbox(p) for p in polys]
    sets = _Sets(n)
    # Umschliessen setzt ueberlappende Huellrechtecke voraus - dieselbe
    # Kandidatenliste taugt also fuer beide Beziehungen.
    inner = [_inner_point(p) for p in polys]
    segments: Dict[int, list] = {}

    def segs(i: int) -> list:
        if i not in segments:
            segments[i] = _segments_with_boxes(polys[i])
        return segments[i]

    for i, j in _neighbour_pairs(boxes):
        if sets.find(i) == sets.find(j):
            continue
        if (_boundaries_cross(segs(i), segs(j))
                or point_in_polygon(inner[i], polys[j])
                or point_in_polygon(inner[j], polys[i])):
            sets.union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(sets.find(i), []).append(i)
    return [groups[k] for k in sorted(groups)]


# ------------------------------------------------------------- Stegnetz

def _centroid(points: Sequence[Point]) -> Point:
    n = float(len(points))
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def _nearest(points: Sequence[Point], target: Point) -> Point:
    return min(points, key=lambda p: ((p[0] - target[0]) ** 2
                                      + (p[1] - target[1]) ** 2, p))


def _spanning_tree(centres: Sequence[Point]) -> List[Tuple[int, int]]:
    """Minimaler Spannbaum (Prim), deterministisch.

    Start bei Insel 0; gleich weite Kandidaten entscheidet der kleinere Index.
    Kein Zufall, keine Sortierung nach Gleitkomma-Zufall - zwei Laeufe mit
    demselben Doc liefern denselben Baum.
    """
    k = len(centres)
    if k < 2:
        return []
    inside = [False] * k
    inside[0] = True
    best_from = [0] * k
    best_dist = [float("inf")] * k
    for j in range(1, k):
        best_dist[j] = _sq(centres[0], centres[j])
    edges: List[Tuple[int, int]] = []
    for _ in range(k - 1):
        pick = -1
        for j in range(k):
            if inside[j]:
                continue
            if pick < 0 or best_dist[j] < best_dist[pick]:
                pick = j
        if pick < 0:
            break
        inside[pick] = True
        edges.append((best_from[pick], pick))
        for j in range(k):
            if inside[j]:
                continue
            d = _sq(centres[pick], centres[j])
            if d < best_dist[j]:
                best_dist[j] = d
                best_from[j] = pick
    return edges


def _sq(a: Point, b: Point) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _point_on_segment(p: Point, a: Point, b: Point) -> Point:
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    if ll < 1e-24:
        return a
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return (a[0] + dx * t, a[1] + dy * t)


def _nearest_on_polygon(points: Sequence[Point], poly: Sequence[Point]
                        ) -> Tuple[float, Point, Point]:
    """Kuerzeste Verbindung von einer Punktwolke zum Polygonzug."""
    best = (float("inf"), points[0], poly[0])
    n = len(poly)
    for p in points:
        for i in range(n):
            q = _point_on_segment(p, poly[i], poly[(i + 1) % n])
            d = math.hypot(p[0] - q[0], p[1] - q[1])
            if d < best[0]:
                best = (d, p, q)
    return best


def _extended(a: Point, b: Point, reach: float) -> Optional[List[Point]]:
    """Mittellinie an beiden Enden um ``reach`` verlaengern.

    Der Steg soll die Motive nicht beruehren, sondern in sie hineinlaufen -
    erst eine echte Ueberlappung wird beim Extrudieren ein Koerper.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = math.hypot(dx, dy)
    if ll < MIN_SPAN:
        return None
    ux, uy = dx / ll, dy / ll
    return [(a[0] - ux * reach, a[1] - uy * reach),
            (b[0] + ux * reach, b[1] + uy * reach)]


#: So oft wird hoechstens nachgebessert, wenn der Beschnitt einen Steg kuerzt.
MAX_ROUNDS = 4


def connector_areas(elements: Sequence[Any], frame_inner: Optional[Sequence[Point]],
                    width: float, reach: float, clip=None
                    ) -> Tuple[List[ir.Path], List[str]]:
    """Verbinder-Stege als geschlossene Profile.

    ``frame_inner`` ist die **innere** Rahmenkante (``container.shrunk``);
    ``None`` heisst: kein Rahmen gezeichnet. ``reach`` ist die Strecke, um die
    jeder Steg in die Motive hineinlaeuft. ``clip`` beschneidet die fertigen
    Stege auf die Containerform.

    Warum in Runden: ein Steg an einem angeschnittenen Randmotiv kann durch den
    Beschnitt genau das Stueck verlieren, mit dem er in sein Motiv hineinlaeuft -
    dann haengt die Insel wieder frei. Statt das zu ignorieren, wird nach dem
    Beschnitt erneut gezaehlt und nachverbunden. Meist ist nach der ersten Runde
    Schluss; bleibt danach etwas uebrig, sagt das eine Warnung.
    """
    warnings: List[str] = []
    produced: List[ir.Path] = []
    pool: List[Any] = list(elements)

    if frame_inner is None and len(islands(pool)) <= 1:
        return [], warnings

    for _ in range(MAX_ROUNDS):
        fresh = _one_round(pool, frame_inner, width, reach)
        if not fresh:
            break
        clipped = list(clip(fresh)) if clip is not None else fresh
        produced.extend(clipped)
        pool = pool + clipped
        if len(clipped) == len(fresh) and _same_shape(fresh, clipped):
            break                       # nichts beschnitten - der Plan ging auf
    else:
        warnings.append("Einzelne Motive am Rand konnten nicht angebunden werden – "
                        "sie bleiben lose Teile.")

    if frame_inner is None:
        warnings.append("Ohne Rahmen bleibt das Muster ein loses Einzelteil – "
                        "die Verbinder halten es nur untereinander zusammen.")
    return produced, warnings


def _same_shape(a: Sequence[ir.Path], b: Sequence[ir.Path]) -> bool:
    return all(x.points == y.points for x, y in zip(a, b))


def _one_round(elements: Sequence[Any], frame_inner: Optional[Sequence[Point]],
               width: float, reach: float) -> List[ir.Path]:
    """Ein Spannbaum plus Rahmenanker ueber den aktuellen Inselbestand."""
    polys = [poly for _, poly in outlines(elements)]
    groups = islands(elements)
    clouds = [[p for idx in g for p in polys[idx]] for g in groups]
    centres = [_centroid(c) for c in clouds]

    spans: List[Tuple[Point, Point]] = []
    shortest = [float("inf")] * len(groups)
    for i, j in _spanning_tree(centres):
        a = _nearest(clouds[i], centres[j])
        b = _nearest(clouds[j], centres[i])
        d = math.hypot(a[0] - b[0], a[1] - b[1])
        shortest[i] = min(shortest[i], d)
        shortest[j] = min(shortest[j], d)
        spans.append((a, b))
    if frame_inner is not None:
        spans.extend(_frame_spans(clouds, centres, shortest, frame_inner, reach))

    out: List[ir.Path] = []
    for a, b in spans:
        line = _extended(a, b, reach)
        if line is None:
            continue
        for ring in stroke(line, False, width):
            out.append(ir.Path(points=ring, closed=True, curve="line",
                               role=ir.ROLE_REGION, layer=ir.LAYER_PATTERN))
    return out


def _frame_spans(clouds: Sequence[Sequence[Point]], centres: Sequence[Point],
                 shortest: Sequence[float], frame_inner: Sequence[Point],
                 reach: float) -> List[Tuple[Point, Point]]:
    """Verankerung im Rahmenband.

    Mindestens zwei Anker, moeglichst weit auseinander (bester Kandidat je
    Rahmenquadrant, davon die zwei kuerzesten). Zusaetzlich jede Insel, die dem
    Rahmen naeher ist als ihrem Nachbarn - dort ist der Anker der kuerzere Weg.
    """
    reach_to_frame = [_nearest_on_polygon(c, frame_inner) for c in clouds]
    middle = _centroid([p for c in clouds for p in c]) if clouds else (0.0, 0.0)

    chosen: Dict[int, Tuple[Point, Point]] = {}
    for i, (d, a, b) in enumerate(reach_to_frame):
        if d > reach and d < shortest[i]:
            chosen[i] = (a, b)

    if len(chosen) < MIN_FRAME_ANCHORS:
        # Bester Kandidat je Quadrant - so landen die Pflichtanker auf
        # verschiedenen Seiten und das Muster haengt nicht an einer Ecke.
        by_quadrant: Dict[int, int] = {}
        for i, centre in enumerate(centres):
            if reach_to_frame[i][0] <= reach:
                continue                       # beruehrt den Rahmen schon
            q = (1 if centre[0] >= middle[0] else 0) + (2 if centre[1] >= middle[1] else 0)
            if q not in by_quadrant or reach_to_frame[i][0] < reach_to_frame[by_quadrant[q]][0]:
                by_quadrant[q] = i
        order = sorted(by_quadrant.values(), key=lambda i: (reach_to_frame[i][0], i))
        for i in order:
            if len(chosen) >= MIN_FRAME_ANCHORS:
                break
            chosen.setdefault(i, (reach_to_frame[i][1], reach_to_frame[i][2]))

    return [chosen[i] for i in sorted(chosen)]
