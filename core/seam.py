"""Die Nahtbahn: ein Schnitt durch das Muster, der keine Zelle zerteilt.

Wird ein Muster auf einen Zylinder gewickelt, treffen die linke und die rechte
Kante der Abwicklung aufeinander. Ein **gerader** Schnitt ist nur bei Mustern
mit durchgehend senkrechten Zellwaenden auch eine Zellgrenze (Gitter, Mauer ohne
Versatz, Puzzle). Bei versetzten Mustern - Wabe, Rauten, Mauer im Verband -
liegt in jeder zweiten Reihe keine Wand an der Naht, und der Schnitt zerteilt
dort eine Zelle. Sichtbar wird das als zusaetzliche Trennung durch jede zweite
Zelle (``Context.md`` 15.7).

Die Loesung ist ein Schnitt **entlang der Zellwaende**: eine Bahn von unten nach
oben, die nur ueber vorhandene Zellkanten laeuft. Die Aussenkontur der
Abwicklung benutzt dieselbe Bahn zweimal - links und um genau eine Periode nach
rechts versetzt. Beide Kanten sind damit deckungsgleich, sobald gewickelt ist,
und keine Zelle wird zerschnitten.

Gesucht wird die Bahn **im fertigen Zellnetz**, nicht in jedem Generator
einzeln. Das hat drei Vorteile: kein Generator muss etwas von Naehten wissen
(die Leitidee „neues Muster = neue Datei"), es gilt fuer kuenftige Muster
automatisch, und es funktioniert auch dort, wo die Zellen gar keiner Formel
folgen (organische Muster).

Das Verfahren ist eine Kuerzeste-Wege-Suche (Dijkstra) im Netz der Zellkanten:
erlaubt sind nur Kanten in einem schmalen Band um die Naht und nur Schritte, die
nicht nach unten fuehren. Die Kosten sind die Kantenlaenge plus ein Aufschlag
fuer den Abstand zur Naht - die Bahn bleibt so dicht wie moeglich an der
Ideallinie. Gibt es keinen durchgehenden Weg, liefert die Suche ``None`` und der
Aufrufer bleibt beim geraden Schnitt.
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Sequence, Tuple

from .geom import (clean_polygon, cross, dist, ensure_ccw, polygon_segments,
                   snap_segments, sub)
from .stroker import offset_polyline

Point = Tuple[float, float]

#: Nachkommastellen, mit denen Kantenendpunkte zusammengefasst werden.
#: Nachbarzellen rechnen dieselbe Ecke unabhaengig aus und weichen dabei um
#: Gleitkomma-Rauschen ab; 1e-9 cm faengt das ein und bleibt weit unter der
#: Toleranz, mit der ``core/polyclip.py`` Punkte auf dem Rand erkennt (1e-7).
SNAP_PRECISION = 9

#: Aufschlag je cm Abstand von der Ideallinie. Hoch genug, dass die Bahn nur
#: dann ausweicht, wenn es keinen Weg an der Naht gibt.
OFFSET_WEIGHT = 8.0

#: Toleranz fuer "nicht nach unten" und fuer das Erreichen der Raender.
EPS_Y = 1e-9


def cell_edges(cells: Sequence[Sequence[Point]], grow: float = 0.0,
               band: Optional[Tuple[float, float]] = None
               ) -> List[Tuple[Point, Point]]:
    """Alle Zellkanten, doppelte zusammengefasst und auf ein Raster gefangen.

    ``band`` beschraenkt die Auswertung auf einen x-Bereich. Ohne diese
    Einschraenkung kostet das Teilen der Kanten bei feinen Mustern ein Vielfaches
    - und die Vorschau soll fluessig bleiben.

    ``grow`` weitet jede Zelle vorher um diesen Betrag auf. Das ist fuer Muster
    noetig, die ihre Fuge selbst lassen (Mauer): deren Zellen beruehren einander
    gar nicht, das Kantennetz zerfaellt in lauter einzelne Rechtecke und es gibt
    keinen durchgehenden Weg. Um die halbe Fuge aufgeweitet stossen sie wieder
    aneinander, und die gefundene Bahn laeuft genau in der **Fugenmitte** - dort,
    wo die Naht ohnehin hingehoert.
    """
    lo = hi = None
    if band is not None:
        lo, hi = band[0] - grow, band[1] + grow
    segments: List[Tuple[Point, Point]] = []
    for cell in cells:
        if len(cell) < 3:
            continue
        if lo is not None:
            xs = [p[0] for p in cell]
            if max(xs) < lo or min(xs) > hi:
                continue      # Zelle liegt gar nicht am Band - spart die Arbeit
        poly = cell
        if grow > 1e-12:
            poly = _grown(cell, grow)
            if not poly:
                continue
        segments.extend(polygon_segments(poly))
    return _split_at_nodes(snap_segments(segments, precision=SNAP_PRECISION))


def _split_at_nodes(edges: Sequence[Tuple[Point, Point]]
                    ) -> List[Tuple[Point, Point]]:
    """Kanten an allen Knoten teilen, die auf ihnen liegen.

    Zwei Kanten koennen sich ueberlappen, ohne einen Endpunkt zu teilen: bei der
    Mauer liegt die Oberkante einer Reihe auf der Unterkante der naechsten, aber
    um den Reihenversatz verschoben. Ohne Teilung hat der Graph dort keine
    Verbindung - die Bahn kaeme nie von einer Reihe in die naechste.
    """
    nodes = sorted(set([a for a, _b in edges] + [b for _a, b in edges]))
    out: List[Tuple[Point, Point]] = []
    for a, b in edges:
        lo_x, hi_x = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        lo_y, hi_y = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        inner = [n for n in nodes
                 if lo_x - EPS_Y <= n[0] <= hi_x + EPS_Y
                 and lo_y - EPS_Y <= n[1] <= hi_y + EPS_Y
                 and n != a and n != b and _on_segment(n, a, b)]
        if not inner:
            out.append((a, b))
            continue
        inner.sort(key=lambda n: dist(a, n))
        chain = [a] + inner + [b]
        for i in range(len(chain) - 1):
            if dist(chain[i], chain[i + 1]) > 0.0:
                out.append((chain[i], chain[i + 1]))
    return out


def _on_segment(p: Point, a: Point, b: Point, tol: float = 1e-9) -> bool:
    """Liegt ``p`` (bis auf ``tol``) auf der Strecke ``a``-``b``?"""
    ux, uy = b[0] - a[0], b[1] - a[1]
    length = (ux * ux + uy * uy) ** 0.5
    if length <= tol:
        return False
    return abs((p[0] - a[0]) * uy - (p[1] - a[1]) * ux) / length <= tol


def _grown(cell: Sequence[Point], delta: float) -> List[Point]:
    """Zelle nach aussen versetzen (negativer Stroker-Offset)."""
    src = clean_polygon(ensure_ccw(cell))
    if len(src) < 3:
        return []
    return offset_polyline(src, [-delta] * len(src), closed=True)


def seam_path(cells: Sequence[Sequence[Point]], x_seam: float,
              y_bottom: float, y_top: float, max_offset: float,
              grow: float = 0.0) -> Optional[List[Point]]:
    """Bahn entlang der Zellkanten von unten nach oben, dicht an ``x_seam``.

    ``max_offset`` begrenzt das Band, in dem gesucht wird. Die Bahn beginnt auf
    oder unter ``y_bottom`` und endet auf oder ueber ``y_top``, damit die
    Aussenkontur die volle Hoehe abdeckt.

    ``grow`` weitet die Zellen vorher auf (siehe :func:`cell_edges`).

    ``None`` heisst: kein durchgehender Weg im Band - dann bleibt es beim
    geraden Schnitt.
    """
    if max_offset <= 0.0:
        return None
    lo, hi = x_seam - max_offset, x_seam + max_offset
    edges = cell_edges(cells, grow=grow, band=(lo, hi))

    graph: Dict[Point, List[Tuple[Point, float]]] = {}
    for a, b in edges:
        if not (lo <= a[0] <= hi and lo <= b[0] <= hi):
            continue
        length = dist(a, b)
        if length <= 0.0:
            continue
        offset = abs((a[0] + b[0]) / 2.0 - x_seam)
        cost = length + OFFSET_WEIGHT * offset
        # Nur aufwaerts (oder waagerecht) - so bleibt die Bahn eine Bahn und
        # kann die Aussenkontur nicht in sich selbst zurueckfuehren.
        if b[1] >= a[1] - EPS_Y:
            graph.setdefault(a, []).append((b, cost))
        if a[1] >= b[1] - EPS_Y:
            graph.setdefault(b, []).append((a, cost))

    if not graph:
        return None
    starts = [n for n in graph if n[1] <= y_bottom + EPS_Y]
    if not starts:
        return None
    ends = set(n for n in graph if n[1] >= y_top - EPS_Y)
    if not ends:
        return None

    best = _dijkstra(graph, starts, ends, x_seam)
    if best is None:
        return None
    return best


def _dijkstra(graph: Dict[Point, List[Tuple[Point, float]]],
              starts: Sequence[Point], ends: set, x_seam: float
              ) -> Optional[List[Point]]:
    """Kuerzester Weg von irgendeinem Start zu irgendeinem Ziel.

    Die Startkosten enthalten den Abstand zur Ideallinie: sonst faenge die Bahn
    beliebig weit aussen an, solange der Weg selbst kurz ist.
    """
    distance: Dict[Point, float] = {}
    previous: Dict[Point, Optional[Point]] = {}
    heap: List[Tuple[float, Point]] = []
    for node in sorted(starts):
        start_cost = OFFSET_WEIGHT * abs(node[0] - x_seam)
        if start_cost < distance.get(node, float("inf")):
            distance[node] = start_cost
            previous[node] = None
            heapq.heappush(heap, (start_cost, node))

    goal: Optional[Point] = None
    while heap:
        cost, node = heapq.heappop(heap)
        if cost > distance.get(node, float("inf")) + 1e-12:
            continue
        if node in ends:
            goal = node
            break
        for other, edge_cost in graph.get(node, ()):
            new_cost = cost + edge_cost
            if new_cost + 1e-12 < distance.get(other, float("inf")):
                distance[other] = new_cost
                previous[other] = node
                heapq.heappush(heap, (new_cost, other))

    if goal is None:
        return None
    path: List[Point] = []
    node: Optional[Point] = goal
    while node is not None:
        path.append(node)
        node = previous[node]
    path.reverse()
    return path


def crossed_cells(cells: Sequence[Sequence[Point]], path: Sequence[Point]
                  ) -> List[Sequence[Point]]:
    """Zellen, die die Bahn wirklich durchschneidet (Probe fuer die Tests).

    Eine Bahn, die nur auf Zellkanten laeuft, darf keine liefern. **Kollineare
    Ueberlappungen zaehlen nicht**: dass ein Bahnschritt ein Stueck einer
    Zellkante mitbenutzt, ist ja gerade der Sinn der Sache - und genau dafuer
    liefert ``segment_intersections`` Parameter mitten im Segment.
    """
    from .polyclip import segment_intersections

    steps = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
    out: List[Sequence[Point]] = []
    for cell in cells:
        n = len(cell)
        if _cell_is_crossed(cell, n, steps, segment_intersections):
            out.append(cell)
    return out


def _cell_is_crossed(cell, n, steps, segment_intersections) -> bool:
    for i in range(n):
        a, b = cell[i], cell[(i + 1) % n]
        for c, d in steps:
            u, v = sub(b, a), sub(d, c)
            lu = (u[0] * u[0] + u[1] * u[1]) ** 0.5
            lv = (v[0] * v[0] + v[1] * v[1]) ** 0.5
            # Relativ pruefen: die Bahnpunkte sind auf 1e-9 gefangen und damit
            # minimal gegen die Zellkante verdreht, auf der sie liegen.
            if lu <= 0.0 or lv <= 0.0 or abs(cross(u, v)) < 1e-6 * lu * lv:
                continue                  # parallel: hoechstens Ueberlappung
            for t, u in segment_intersections(a, b, c, d):
                if 1e-9 < t < 1 - 1e-9 and 1e-9 < u < 1 - 1e-9:
                    return True
    return False
