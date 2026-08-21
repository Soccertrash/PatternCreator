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
erlaubt sind nur Kanten in einem schmalen Band um die Naht. Die Kosten sind die
Kantenlaenge plus ein Aufschlag fuer den Abstand zur Naht - die Bahn bleibt so
dicht wie moeglich an der Ideallinie. Gibt es keinen durchgehenden Weg, liefert
die Suche ``None`` und der Aufrufer bleibt beim geraden Schnitt.

Gesucht wird in zwei Anlaeufen. Zuerst **monoton**: eine Bahn, die nie nach
unten laeuft, kann sich unmoeglich selbst kreuzen, und die Aussenkontur ist
damit garantiert ein einfaches Polygon. Bei eckigen Zellen reicht das immer.
Gerundete Zellen (Kiesel, Gewebe) buchten aus - um eine Ausbuchtung herum fuehrt
kein monotoner Weg, und der erste Anlauf findet nichts. Dann wird die Suche
freigegeben und die gefundene Bahn auf Selbstkreuzung geprueft.
"""

from __future__ import annotations

import heapq
from bisect import bisect_left, bisect_right
from typing import Dict, List, Optional, Sequence, Tuple

from .geom import (clean_polygon, dist, ensure_ccw, point_in_polygon,
                   polygon_segments, snap_segments)
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

#: Ab welcher Tiefe (cm) ein Schnitt als Schnitt zaehlt. Die Bahnpunkte sind auf
#: 1e-9 gefangen und liegen dadurch um Bruchteile eines Nanometers neben der
#: Wand, auf der sie laufen - parametrisch gemessen sieht das auf einem kurzen
#: Schritt nach einem Schnitt aus. Gemessen wird deshalb in cm, mit derselben
#: Toleranz, mit der ``core/polyclip.py`` Punkte als "auf dem Rand" erkennt.
CROSS_TOL = 1e-7


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
    # Nach x sortiert - damit findet die Suche je Kante in zwei Halbierungen den
    # Streifen, in dem ueberhaupt Knoten liegen koennen. Ohne das wird jede
    # Kante gegen jeden Knoten geprueft, und bei feinen Mustern ist genau das
    # der teuerste Schritt der ganzen Nahtsuche (gemessen: 98 % der Zeit).
    xs = [n[0] for n in nodes]
    out: List[Tuple[Point, Point]] = []
    for a, b in edges:
        lo_x, hi_x = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        lo_y, hi_y = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        first = bisect_left(xs, lo_x - EPS_Y)
        last = bisect_right(xs, hi_x + EPS_Y)
        inner = [n for n in nodes[first:last]
                 if lo_y - EPS_Y <= n[1] <= hi_y + EPS_Y
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


def suggest_offset(cells: Sequence[Sequence[Point]], period: float) -> float:
    """Wie breit das Suchband sein sollte: etwa drei Zellbreiten.

    Zu schmal, und die Suche verliert die langen Waende grosser Zellen (nur
    Kanten, die **ganz** im Band liegen, zaehlen); zu breit, und die Bahn darf
    quer durch das halbe Muster wandern. Drei Zellbreiten sind grosszuegig genug
    fuer versetzte Muster und bleiben weit unter einem Viertel Umlauf.
    """
    widths = sorted(max(p[0] for p in c) - min(p[0] for p in c)
                    for c in cells if len(c) >= 3)
    if not widths:
        return 0.0
    typical = widths[len(widths) // 2]
    limit = period / 4.0 if period > 0.0 else float("inf")
    return max(min(3.0 * typical, limit), 0.0)


def periodic_cells(cells: Sequence[Sequence[Point]], x_seam: float,
                   period: float, margin: float) -> List[Sequence[Point]]:
    """Die Zellen von der anderen Nahtseite dazunehmen, um eine Periode versetzt.

    Das Muster ist periodisch, die **Liste** ist es nicht: sie enthaelt jede
    Zelle genau einmal. Links der Naht klafft dadurch eine Luecke, wo in
    Wirklichkeit die Fortsetzung des Musters liegt - und die Suche legt die Bahn
    seelenruhig mitten hindurch. Zerschnitten wird dann nichts, was in der Liste
    steht, aber nach dem Wickeln sehr wohl: an der rechten Naht liegt dieselbe
    Stelle mitten in einer echten Zelle. Mit den Kopien sieht die Suche
    beiderseits der Naht dasselbe Bild, und jede Wand, die sie benutzt, ist eine
    Wand des gewickelten Musters.
    """
    if period <= 0.0:
        return list(cells)
    lo, hi = x_seam + period - margin, x_seam + period + margin
    out = list(cells)
    for cell in cells:
        xs = [p[0] for p in cell]
        if min(xs) <= hi and max(xs) >= lo:
            out.append([(p[0] - period, p[1]) for p in cell])
    return out


def seam_path(cells: Sequence[Sequence[Point]], x_seam: float,
              y_bottom: float, y_top: float, max_offset: float,
              grow: float = 0.0, period: float = 0.0) -> Optional[List[Point]]:
    """Bahn entlang der Zellkanten von unten nach oben, dicht an ``x_seam``.

    ``max_offset`` begrenzt das Band, in dem gesucht wird. Die Bahn beginnt auf
    ``y_bottom`` und endet auf ``y_top``, damit die Aussenkontur die volle Hoehe
    abdeckt. Reichen die Zellen dort nicht hin - Muster mit eigener Fuge lassen
    unten und oben einen Streifen frei -, wird die Bahn senkrecht verlaengert;
    dass dieses Stueck keine Zelle anschneidet, wird nachgerechnet.

    ``grow`` weitet die Zellen vorher auf (siehe :func:`cell_edges`).

    ``period`` ist die Breite eines Umlaufs. Ist sie gesetzt, kommen die Zellen
    der anderen Nahtseite als Kopien dazu (:func:`periodic_cells`) - ohne sie
    findet die Suche Wege, die es nach dem Wickeln nicht gibt.

    ``None`` heisst: kein durchgehender Weg im Band - dann bleibt es beim
    geraden Schnitt.
    """
    if max_offset <= 0.0:
        return None
    cells = periodic_cells(cells, x_seam, period, max_offset + abs(grow))
    lo, hi = x_seam - max_offset, x_seam + max_offset
    edges = [(a, b) for a, b in cell_edges(cells, grow=grow, band=(lo, hi))
             if lo <= a[0] <= hi and lo <= b[0] <= hi and dist(a, b) > 0.0]
    if not edges:
        return None
    for monotone in (True, False):
        path = _search(edges, x_seam, y_bottom, y_top, monotone)
        if path is None or (not monotone and _self_crossing(path)):
            continue
        full = _extend(path, cells, y_bottom, y_top)
        if full is not None:
            return full
    return None


def _search(edges: Sequence[Tuple[Point, Point]], x_seam: float,
            y_bottom: float, y_top: float, monotone: bool
            ) -> Optional[List[Point]]:
    """Kuerzeste Bahn im Kantennetz; ``monotone`` verbietet Schritte nach unten."""
    graph: Dict[Point, List[Tuple[Point, float]]] = {}
    for a, b in edges:
        cost = dist(a, b) + OFFSET_WEIGHT * abs((a[0] + b[0]) / 2.0 - x_seam)
        if not monotone or b[1] >= a[1] - EPS_Y:
            graph.setdefault(a, []).append((b, cost))
        if not monotone or a[1] >= b[1] - EPS_Y:
            graph.setdefault(b, []).append((a, cost))
    if not graph:
        return None
    # Wo die Zellen den Rand gar nicht erreichen, faengt die Bahn an der
    # untersten vorhandenen Wand an (und wird spaeter senkrecht verlaengert).
    low = max(y_bottom, min(n[1] for n in graph))
    high = min(y_top, max(n[1] for n in graph))
    if high <= low:
        return None
    starts = [n for n in graph if n[1] <= low + EPS_Y]
    ends = set(n for n in graph if n[1] >= high - EPS_Y)
    if not starts or not ends:
        return None
    return _dijkstra(graph, starts, ends, x_seam)


def _extend(path: Sequence[Point], cells: Sequence[Sequence[Point]],
            y_bottom: float, y_top: float) -> Optional[List[Point]]:
    """Bahn auf die Raender bringen: ueberstehendes klemmen, fehlendes ergaenzen.

    Die Zellen reichen fast nie genau bis zum Rand. Stehen sie darueber hinaus
    (Gitter-Muster erzeugen immer ein paar Reihen zu viel), wird die Bahn dort
    **geschnitten** - der Schnittpunkt liegt auf derselben Zellwand, die Bahn
    laeuft also weiter auf Waenden. Geklemmt werden darf sie nicht: das ergaebe
    ein waagerechtes Stueck quer durch die Randzellen. Bleiben die Zellen unter
    dem Rand (Muster mit eigener Fuge lassen oben und unten einen Streifen
    frei), wird die Bahn senkrecht verlaengert.
    """
    out = _trimmed(path, y_bottom, y_top)
    if out is None or len(out) < 2:
        return None
    if out[0][1] > y_bottom + EPS_Y:
        foot = (out[0][0], y_bottom)
        if not _free_line(cells, foot, out[0]):
            return None
        out.insert(0, foot)
    if out[-1][1] < y_top - EPS_Y:
        head = (out[-1][0], y_top)
        if not _free_line(cells, head, out[-1]):
            return None
        out.append(head)
    return out


def _trimmed(path: Sequence[Point], y_bottom: float, y_top: float
             ) -> Optional[List[Point]]:
    """Bahnstueck zwischen den beiden Randlinien, an den Kanten geschnitten."""
    out = list(path)
    below = [i for i, p in enumerate(out) if p[1] <= y_bottom + EPS_Y]
    if below:
        i = below[-1]
        out = ([_cross_y(out[i], out[i + 1], y_bottom)] + out[i + 1:]
               if i + 1 < len(out) else out[i:])
    above = [i for i, p in enumerate(out) if p[1] >= y_top - EPS_Y]
    if above:
        j = above[0]
        out = (out[:j] + [_cross_y(out[j - 1], out[j], y_top)]
               if j > 0 else out[:1])
    return _dedupe(out)


def _cross_y(a: Point, b: Point, y: float) -> Point:
    """Punkt auf der Strecke ``a``-``b`` bei der Hoehe ``y``."""
    if abs(b[1] - a[1]) < 1e-15:
        return (a[0], y)
    t = (y - a[1]) / (b[1] - a[1])
    t = min(max(t, 0.0), 1.0)
    return (a[0] + t * (b[0] - a[0]), y)


def _dedupe(points: Sequence[Point]) -> List[Point]:
    """Aufeinanderfolgende gleiche Punkte zusammenfassen."""
    out: List[Point] = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > 1e-12 or abs(p[1] - out[-1][1]) > 1e-12:
            out.append(p)
    return out


def _free_line(cells: Sequence[Sequence[Point]], a: Point, b: Point) -> bool:
    """Laeuft die Strecke ``a``-``b`` durch keine Zelle?

    Zwei Faelle, und beide kommen vor: die Strecke **kreuzt** eine Zellwand, oder
    sie liegt ganz **in** einer Zelle und beruehrt deren Rand nur in den
    Endpunkten - der eine ist ja immer ein Knoten des Kantennetzes und der andere
    liegt gern auf der Aussenkante. Fuer den zweiten Fall wird die Mitte
    geprueft; auf den Endpunkten ist ``point_in_polygon`` genau dort unzuverlaessig,
    wo es darauf ankaeme.
    """
    from .polyclip import segment_intersections

    steps = [(a, b)]
    middle = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    for cell in cells:
        if _cell_is_crossed(cell, len(cell), steps, segment_intersections):
            return False
        if point_in_polygon(middle, cell):
            return False
    return True


def _self_crossing(path: Sequence[Point]) -> bool:
    """Kreuzt die Bahn sich selbst? (Nur fuer den freien, nicht-monotonen Lauf.)"""
    from .polyclip import segment_intersections

    steps = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
    for i in range(len(steps)):
        a, b = steps[i]
        for j in range(i + 2, len(steps)):
            c, d = steps[j]
            for t, u in segment_intersections(a, b, c, d):
                if -EPS_Y < t < 1 + EPS_Y and -EPS_Y < u < 1 + EPS_Y:
                    return True
    return False


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
    liefert ``segment_intersections`` Parameter mitten im Segment. Und ein
    Schnitt zaehlt erst ab :data:`CROSS_TOL` Tiefe - alles darunter ist das
    Rundungsrauschen der Bahnpunkte.
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
    from .polyclip import point_segment_distance

    for i in range(n):
        a, b = cell[i], cell[(i + 1) % n]
        lo_x, hi_x = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        lo_y, hi_y = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        for c, d in steps:
            if (min(c[0], d[0]) > hi_x + CROSS_TOL or max(c[0], d[0]) < lo_x - CROSS_TOL
                    or min(c[1], d[1]) > hi_y + CROSS_TOL
                    or max(c[1], d[1]) < lo_y - CROSS_TOL):
                continue
            if _same_wall(a, b, c, d, point_segment_distance):
                continue
            for t, u in segment_intersections(a, b, c, d):
                if (_deep(t, a, b) and _deep(u, c, d)):
                    return True
    return False


def _same_wall(a: Point, b: Point, c: Point, d: Point, distance) -> bool:
    """Laeuft der Bahnschritt auf dieser Zellkante (ganz oder teilweise)?

    Das ist der Normalfall und kein Schnitt. Frueher wurde das ueber den Winkel
    zwischen den beiden Strecken entschieden - das faellt auseinander, sobald
    eine Zellkante nur noch Bruchteile eines Mikrometers lang ist (die
    Eckenrundung erzeugt solche Splitter): das Rundungsrauschen der Bahnpunkte
    verdreht so kurze Strecken um ein Vielfaches der Winkeltoleranz. Gemessen
    wird deshalb der Abstand, nicht der Winkel.
    """
    if (distance(c, a, b) <= CROSS_TOL and distance(d, a, b) <= CROSS_TOL):
        return True
    return (distance(a, c, d) <= CROSS_TOL and distance(b, c, d) <= CROSS_TOL)


def _deep(t: float, a: Point, b: Point) -> bool:
    """Liegt der Schnittpunkt weit genug von beiden Enden der Strecke weg?"""
    return min(t, 1.0 - t) * dist(a, b) > CROSS_TOL
