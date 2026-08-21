"""Gemeinsamer Kern der organischen Muster.

Enthaelt Voronoi (Halbebenen-Schnitt, reines Python), Lloyd-Relaxation,
Eckenrundung, Anisotropie und Fuge. Darauf bauen ``voronoi``, ``pebbles``,
``tissue`` und ``leaf_veins`` auf - kein Copy-Paste.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

from core.geom import (EPS, bbox, centroid, clip_half_plane, convex_hull,
                       dist, erode_convex, point_in_polygon, polygon_area)
from core.pattern_doc import Param, T_FLOAT, T_INT, T_LENGTH

from .base import GenContext, Generator

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]

MAX_CELLS = 500          # harte Obergrenze (Performance-Schutz, siehe README)


# ------------------------------------------------------------------ Voronoi

def voronoi_cells(sites: Sequence[Point], bbox: BBox,
                  ghosts: Sequence[Point] = ()) -> List[List[Point]]:
    """Voronoi-Zellen der Punkte, begrenzt durch ``bbox``.

    Halbebenen-Schnitt je Zelle. Durch Vorsortieren der Nachbarn nach Abstand und
    fruehen Abbruch bleibt das auch fuer einige hundert Punkte schnell genug.

    ``ghosts`` sind Punkte, die die Zellen **begrenzen**, aber selbst keine Zelle
    bekommen. Damit rechnet der periodische Modus so, als ginge das Muster
    jenseits der Naht unveraendert weiter (siehe :func:`ghost_sites`).
    """
    x0, y0, x1, y1 = bbox
    base = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    n = len(sites)
    pool = list(sites) + list(ghosts)
    cells: List[List[Point]] = []
    for i, s in enumerate(sites):
        others = sorted(
            ((dist(s, pool[j]), pool[j]) for j in range(len(pool)) if j != i),
            key=lambda t: t[0])
        poly = list(base)
        for d, o in others:
            if not poly:
                break
            far = max(dist(s, p) for p in poly)
            if d > 2.0 * far + EPS:
                break                    # alle weiteren Punkte koennen nicht mehr schneiden
            ax, ay = o[0] - s[0], o[1] - s[1]
            mx, my = (o[0] + s[0]) / 2.0, (o[1] + s[1]) / 2.0
            poly = clip_half_plane(poly, ax, ay, -(ax * mx + ay * my))
        # Der wiederholte Schnitt hinterlaesst winzige Faltungen (Punkte, die um
        # Bruchteile eines Hundertstel Millimeters zurueckspringen). Eine
        # Voronoi-Zelle ist konvex - die Huelle ist also nicht nur eine Naeherung,
        # sondern die exakte Zelle, nur ohne diese Artefakte.
        poly = convex_hull(poly)
        if len(poly) >= 3 and abs(polygon_area(poly)) > 1e-9:
            cells.append(poly)
    return cells


def lloyd_relax(sites: Sequence[Point], bbox: BBox, iterations: int = 1,
                period: float = 0.0, band: float = 0.0) -> List[Point]:
    """Lloyd-Relaxation: Punkte in ihre Zellschwerpunkte ziehen (gleichmaessiger).

    Im periodischen Modus (``period`` > 0) laufen die Geisterpunkte in jeder
    Iteration mit und die Zellen werden **nicht** an der Naht abgeschnitten -
    sonst zoege der abgeschnittene Schwerpunkt die Punkte vom Rand weg und die
    Zellen am Nahtband wuerden groesser als der Rest.
    """
    pts = list(sites)
    x0 = bbox[0]
    box = bbox if period <= EPS else (bbox[0] - band, bbox[1], bbox[2] + band, bbox[3])
    for _ in range(max(0, int(iterations))):
        ghosts = ghost_sites(pts, x0, period, band) if period > EPS else ()
        cells = voronoi_cells(pts, box, ghosts)
        if len(cells) != len(pts):
            break
        pts = [centroid(c) for c in cells]
        if period > EPS:
            pts = [wrap_x(p, x0, period) for p in pts]
    return pts


# ------------------------------------------------------------- periodischer Modus

#: Wie weit reicht das Nahtband, gemessen in mittleren Zellradien. Nur Punkte
#: darin bekommen einen Geisterpunkt - Punkte weiter weg koennen die Zellen an
#: der Naht nicht mehr beruehren. 4 Radien sind grosszuegig; der Test
#: ``test_band_ghosts_match_full_ghosts`` haelt das nach.
SEAM_BAND_RADII = 4.0


def wrap_x(p: Point, x0: float, period: float) -> Point:
    """Punkt in das Fenster ``[x0, x0 + period)`` zurueckholen."""
    if period <= EPS:
        return p
    return (x0 + (p[0] - x0) % period, p[1])


def seam_band(bbox: BBox, count: int, period: float) -> float:
    """Breite des Bandes an jeder Fensterkante, in dem Geisterpunkte entstehen."""
    if period <= EPS:
        return 0.0
    w = max(bbox[2] - bbox[0], EPS)
    h = max(bbox[3] - bbox[1], EPS)
    radius = math.sqrt(w * h / float(max(1, count)))
    return min(period, SEAM_BAND_RADII * radius)


def ghost_sites(sites: Sequence[Point], x0: float, period: float,
                band: float) -> List[Point]:
    """Kopien der randnahen Punkte, um **genau eine Periode** versetzt.

    Der Plan sah gespiegelte Geisterpunkte vor. Verschobene sind besser: sie
    machen das Muster echt periodisch (nach dem Wickeln setzt es sich fort statt
    sich zu spiegeln), die Zellenzahl bleibt unangetastet, und die Naht selbst
    muss keine Zellgrenze mehr sein - die sucht sich ``core/seam.py`` entlang
    der vorhandenen Waende. Begruendung in ``Context.md`` 15.7.
    """
    if period <= EPS or band <= 0.0:
        return []
    x1 = x0 + period
    out: List[Point] = []
    for p in sites:
        if p[0] < x0 + band:
            out.append((p[0] + period, p[1]))
        if p[0] > x1 - band:
            out.append((p[0] - period, p[1]))
    return out


def sample_sites(bbox: BBox, count: int, rnd, anisotropy: float = 1.0,
                 rows: int = 0, jitter: float = 1.0,
                 period: float = 0.0) -> List[Point]:
    """Zufaellige Saatpunkte; ``rows`` > 0 erzwingt eine Reihenstruktur (Gewebe)."""
    x0, y0, x1, y1 = bbox
    count = max(1, min(MAX_CELLS, int(count)))
    if rows and rows > 0:
        per_row = max(1, int(round(count / float(rows))))
        dy = (y1 - y0) / rows
        dx = (x1 - x0) / per_row
        pts = []
        for j in range(rows):
            offset = dx * 0.5 * (j % 2)
            for i in range(per_row):
                px = x0 + (i + 0.5) * dx + offset + (rnd.random() - 0.5) * dx * jitter * 0.6
                py = y0 + (j + 0.5) * dy + (rnd.random() - 0.5) * dy * jitter * 0.4
                pts.append((px, py))
        # Der Reihenversatz und die Unruhe schieben Punkte ueber die Naht
        # hinaus; periodisch gehoeren sie auf die andere Seite des Fensters.
        if period > EPS:
            return [wrap_x(p, x0, period) for p in pts]
        return pts
    return scatter_sites(bbox, count, rnd, period=period)


def _bucket(p: Point, origin: Point, cell: float) -> Tuple[int, int]:
    return (int(math.floor((p[0] - origin[0]) / cell)),
            int(math.floor((p[1] - origin[1]) / cell)))


def _crowded(p: Point, grid: Dict[Tuple[int, int], List[Point]], origin: Point,
             cell: float, radius: float, shifts: Sequence[float]) -> bool:
    """Liegt ``p`` - oder eine seiner Kopien jenseits der Naht - zu dicht?"""
    for shift in shifts:
        q = (p[0] + shift, p[1])
        gx, gy = _bucket(q, origin, cell)
        for iy in range(gy - 1, gy + 2):
            for ix in range(gx - 1, gx + 2):
                for other in grid.get((ix, iy), ()):
                    if dist(q, other) < radius:
                        return True
    return False


def scatter_sites(bbox: BBox, count: int, rnd, period: float = 0.0) -> List[Point]:
    """``count`` Punkte mit Mindestabstand streuen.

    Rein zufaellige Punkte liegen paarweise fast aufeinander; die Voronoi-Zelle
    dazwischen wird zum Splitter (gemessen: Groessenverhaeltnis 1:1000 innerhalb
    eines Musters). Hier wird jeder Kandidat verworfen, der einem schon gesetzten
    Punkt zu nahe kommt. Klappt das mehrfach nicht, sinkt der Mindestabstand -
    so kommen immer genau ``count`` Punkte heraus, auch in engen Rahmen.
    """
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    if count <= 1 or w <= 0 or h <= 0:
        return [(x0 + rnd.random() * w, y0 + rnd.random() * h) for _ in range(max(1, count))]
    radius = 0.75 * math.sqrt(w * h / float(count))
    cell = max(radius, 1e-9)
    # Periodisch zaehlt der Abstand ueber die Naht hinweg mit: sonst landen ein
    # Punkt am linken und einer am rechten Rand nach dem Wickeln aufeinander.
    shifts = (0.0,) if period <= EPS else (0.0, period, -period)
    grid: Dict[Tuple[int, int], List[Point]] = {}
    pts: List[Point] = []
    misses = 0
    while len(pts) < count:
        p = (x0 + rnd.random() * w, y0 + rnd.random() * h)
        ok = not _crowded(p, grid, (x0, y0), cell, radius, shifts)
        if ok:
            pts.append(p)
            grid.setdefault(_bucket(p, (x0, y0), cell), []).append(p)
            misses = 0
        else:
            misses += 1
            if misses >= 24:            # Rahmen ist voll -> Anspruch senken
                radius *= 0.8
                misses = 0
    return pts


def scatter_in_polygon(poly: Sequence[Point], count: int, rnd) -> List[Point]:
    """``count`` Punkte mit Mindestabstand **innerhalb** eines Polygons streuen."""
    x0, y0, x1, y1 = bbox(poly)
    w, h = x1 - x0, y1 - y0
    if count <= 0 or w <= 0 or h <= 0:
        return []
    area = abs(polygon_area(poly))
    radius = 0.75 * math.sqrt(max(area, 1e-12) / float(count))
    pts: List[Point] = []
    misses = 0
    guard = 0
    while len(pts) < count and guard < count * 200:
        guard += 1
        p = (x0 + rnd.random() * w, y0 + rnd.random() * h)
        if not point_in_polygon(p, poly):
            continue
        if any(dist(p, q) < radius for q in pts):
            misses += 1
            if misses >= 24:
                radius *= 0.8
                misses = 0
            continue
        pts.append(p)
        misses = 0
    return pts


def scale_points(pts: Sequence[Point], sx: float, sy: float) -> List[Point]:
    return [(p[0] * sx, p[1] * sy) for p in pts]


#: "Rundheit" 0..3 -> Anteil der halben Kantenlaenge, der je Ecke verrundet wird.
#: 1.0 entspricht der maximalen Rundung (Grenzkurve von Chaikin).
ROUND_FACTORS = (0.0, 0.4, 0.7, 1.0)


def round_corners(poly: Sequence[Point], factor: float, samples: int = 4) -> List[Point]:
    """Ecken mit **begrenztem** Radius ausrunden.

    Chaikin schneidet jede Ecke um ein Viertel der Kantenlaenge ab und zieht damit
    die ganze Kontur nach innen - je groesser die Zelle, desto mehr Material bleibt
    zwischen den Zellen stehen. Hier wird nur die Ecke selbst verrundet, die
    Kantenmitten bleiben liegen. Die gerundete Zelle fuellt ihre Voronoi-Zelle
    dadurch fast vollstaendig aus, und benachbarte Zellen beruehren sich weiterhin
    entlang ihrer gemeinsamen Kante (die Fuge kommt allein aus ``inset``).
    """
    n = len(poly)
    if n < 3 or factor <= 0.0:
        return list(poly)
    lens = [dist(poly[i], poly[(i + 1) % n]) for i in range(n)]
    f = min(1.0, float(factor)) * 0.5      # 0.5 => Schnitt bis zur Kantenmitte
    cut = [f * min(lens[(i - 1) % n], lens[i]) for i in range(n)]
    # Zwei benachbarte Ecken duerfen dieselbe Kante nicht doppelt verbrauchen -
    # sonst ueberschlagen sich die Rundungen und es entstehen Zacken.
    limit = [1.0] * n
    for i in range(n):
        j = (i + 1) % n
        total = cut[i] + cut[j]
        if total > lens[i] * 0.98 and total > EPS:
            k = lens[i] * 0.98 / total
            limit[i] = min(limit[i], k)
            limit[j] = min(limit[j], k)
    out: List[Point] = []
    for i in range(n):
        p = poly[i]
        t = cut[i] * limit[i]
        d0 = lens[(i - 1) % n]
        d1 = lens[i]
        if t < EPS or d0 < EPS or d1 < EPS:
            out.append(p)
            continue
        a = poly[(i - 1) % n]
        b = poly[(i + 1) % n]
        p0 = (p[0] + (a[0] - p[0]) * t / d0, p[1] + (a[1] - p[1]) * t / d0)
        p1 = (p[0] + (b[0] - p[0]) * t / d1, p[1] + (b[1] - p[1]) * t / d1)
        for k in range(samples + 1):       # quadratische Bezier p0 -> p -> p1
            u = k / float(samples)
            v = 1.0 - u
            out.append((v * v * p0[0] + 2 * v * u * p[0] + u * u * p1[0],
                        v * v * p0[1] + 2 * v * u * p[1] + u * u * p1[1]))
    return [q for i, q in enumerate(out) if dist(q, out[i - 1]) > EPS]


def build_cells(ctx: GenContext, count: int, relax: int = 0, anisotropy: float = 1.0,
                rows: int = 0, smooth: int = 0, inset: float = 0.0,
                jitter: float = 1.0) -> List[List[Point]]:
    """Kompletter Zell-Aufbau: Saat -> Voronoi -> Relax -> Rundung -> Inset.

    ``anisotropy`` > 1 streckt die Zellen in X (laengliche Zellen wie im Gewebe).
    """
    ax = max(0.05, float(anisotropy))
    x0, y0, x1, y1 = ctx.bbox
    work_bbox = (x0 / ax, y0, x1 / ax, y1)
    # Die Anisotropie staucht x - die Periode macht das mit.
    period = ctx.period_x / ax if ctx.periodic else 0.0
    band = seam_band(work_bbox, count, period)
    sites = sample_sites(work_bbox, count, ctx.rnd, rows=rows, jitter=jitter,
                         period=period)
    if relax > 0:
        sites = lloyd_relax(sites, work_bbox, relax, period=period, band=band)
    # Periodisch duerfen die Zellen ueber die Naht hinausragen: sie werden
    # **ganz** gebraucht, damit die Nahtbahn um sie herumlaufen kann statt sie
    # zu zerschneiden. Das Zuschneiden auf den Rahmen macht ohnehin build.py.
    clip_box = (work_bbox if period <= EPS
                else (work_bbox[0] - band, y0, work_bbox[2] + band, y1))
    cells = voronoi_cells(sites, clip_box,
                          ghost_sites(sites, work_bbox[0], period, band))
    out: List[List[Point]] = []
    for cell in cells:
        # Reihenfolge: erst die konvexe Zelle verkleinern, dann runden. Umgekehrt
        # muesste eine gerundete (und damit fast punktdichte) Kontur versetzt
        # werden - genau daran sind vorher die halben Zellen zerbrochen.
        poly = erode_convex(scale_points(cell, ax, 1.0), inset)
        if poly is None:
            continue
        if smooth > 0:
            idx = min(int(smooth), len(ROUND_FACTORS) - 1)
            poly = round_corners(poly, ROUND_FACTORS[idx])
        if len(poly) >= 3 and abs(polygon_area(poly)) > 1e-9:
            out.append(poly)
    return out


# ------------------------------------------------------- gemeinsame Parameter

def cell_params(default_count: int = 120, with_rows: bool = False,
                with_smooth: bool = True, with_inset: bool = True,
                default_roundness: int = 0, default_inset: float = 0.0) -> List[Param]:
    ps = [
        Param("cellCount", "Zellenzahl", T_INT, default_count, min=3, max=MAX_CELLS, step=1,
              help="Maximal %d Zellen (Performance-Schutz)." % MAX_CELLS),
        Param("relax", "Gleichmäßigkeit", T_INT, 1, min=0, max=3, step=1,
              help="Lloyd-Relaxation: 0 = wild gestreut, 3 = sehr gleichmäßig."),
    ]
    if with_smooth:
        ps.append(Param("roundness", "Rundheit", T_INT, default_roundness,
                        min=0, max=3, step=1,
                        help="Eckenrundung: 0 = eckig, 3 = rund wie Kiesel."))
    if with_inset:
        ps.append(Param("inset", "Fugenbreite", T_LENGTH, default_inset,
                        min=0.0, max=5.0, step=0.01,
                        help="Zellen werden um diesen Betrag verkleinert."))
    if with_rows:
        ps.append(Param("rows", "Reihen", T_INT, 8, min=1, max=80, step=1))
        ps.append(Param("anisotropy", "Streckung X", T_FLOAT, 2.5, min=0.2, max=10.0,
                        step=0.1, help="> 1 macht die Zellen in X länglich."))
    return ps


class OrganicGenerator(Generator):
    """Basis fuer alle Generatoren der organischen Zellen-Familie."""

    fill_targets = ("webs", "cells")
    own_gap = True

    def gap(self, params):
        # Jede Zelle ist um "inset" verkleinert -> Abstand = 2 * inset
        return max(0.0, float(params.get("inset", 0.0))) * 2.0

    def cells_for(self, params: Dict[str, Any], ctx: GenContext) -> List[List[Point]]:
        return build_cells(
            ctx,
            count=int(params.get("cellCount", 120)),
            relax=int(params.get("relax", 1)),
            anisotropy=float(params.get("anisotropy", 1.0)),
            rows=int(params.get("rows", 0)),
            smooth=int(params.get("roundness", 0)),
            inset=float(params.get("inset", 0.0)),
            jitter=float(params.get("rowJitter", 1.0)),
        )

