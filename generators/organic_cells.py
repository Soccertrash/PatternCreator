"""Gemeinsamer Kern der organischen Muster.

Enthaelt Voronoi (Halbebenen-Schnitt, reines Python), Lloyd-Relaxation,
Chaikin-Rundung, Anisotropie und Inset. Darauf bauen ``voronoi``, ``pebbles``,
``tissue``, ``caustics`` und ``leaf_veins`` auf - kein Copy-Paste.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.geom import EPS, centroid, chaikin, dist, inset_polygon, polygon_area
from core.pattern_doc import Param, T_FLOAT, T_INT, T_LENGTH, T_PERCENT

from .base import GenContext, Generator

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]

MAX_CELLS = 500          # harte Obergrenze (Performance-Schutz, siehe README)


# ------------------------------------------------------------------ Voronoi

def _clip_half_plane(poly: Sequence[Point], a: float, b: float, c: float) -> List[Point]:
    """Polygon auf ``a*x + b*y + c <= 0`` beschneiden."""
    out: List[Point] = []
    n = len(poly)
    if n == 0:
        return out
    for i in range(n):
        p = poly[i]
        q = poly[(i + 1) % n]
        dp = a * p[0] + b * p[1] + c
        dq = a * q[0] + b * q[1] + c
        if dp <= 0:
            out.append(p)
        if (dp < 0 < dq) or (dq < 0 < dp):
            t = dp / (dp - dq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def voronoi_cells(sites: Sequence[Point], bbox: BBox) -> List[List[Point]]:
    """Voronoi-Zellen der Punkte, begrenzt durch ``bbox``.

    Halbebenen-Schnitt je Zelle. Durch Vorsortieren der Nachbarn nach Abstand und
    fruehen Abbruch bleibt das auch fuer einige hundert Punkte schnell genug.
    """
    x0, y0, x1, y1 = bbox
    base = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    n = len(sites)
    cells: List[List[Point]] = []
    for i, s in enumerate(sites):
        others = sorted(
            ((dist(s, sites[j]), sites[j]) for j in range(n) if j != i),
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
            poly = _clip_half_plane(poly, ax, ay, -(ax * mx + ay * my))
        if len(poly) >= 3 and abs(polygon_area(poly)) > 1e-9:
            cells.append(poly)
    return cells


def lloyd_relax(sites: Sequence[Point], bbox: BBox, iterations: int = 1) -> List[Point]:
    """Lloyd-Relaxation: Punkte in ihre Zellschwerpunkte ziehen (gleichmaessiger)."""
    pts = list(sites)
    for _ in range(max(0, int(iterations))):
        cells = voronoi_cells(pts, bbox)
        if len(cells) != len(pts):
            break
        pts = [centroid(c) for c in cells]
    return pts


def sample_sites(bbox: BBox, count: int, rnd, anisotropy: float = 1.0,
                 rows: int = 0, jitter: float = 1.0) -> List[Point]:
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
        return pts
    return [(x0 + rnd.random() * (x1 - x0), y0 + rnd.random() * (y1 - y0))
            for _ in range(count)]


def scale_points(pts: Sequence[Point], sx: float, sy: float) -> List[Point]:
    return [(p[0] * sx, p[1] * sy) for p in pts]


def build_cells(ctx: GenContext, count: int, relax: int = 0, anisotropy: float = 1.0,
                rows: int = 0, smooth: int = 0, inset: float = 0.0,
                jitter: float = 1.0) -> List[List[Point]]:
    """Kompletter Zell-Aufbau: Saat -> Voronoi -> Relax -> Rundung -> Inset.

    ``anisotropy`` > 1 streckt die Zellen in X (laengliche Zellen wie im Gewebe).
    """
    ax = max(0.05, float(anisotropy))
    x0, y0, x1, y1 = ctx.bbox
    work_bbox = (x0 / ax, y0, x1 / ax, y1)
    sites = sample_sites(work_bbox, count, ctx.rnd, rows=rows, jitter=jitter)
    if relax > 0:
        sites = lloyd_relax(sites, work_bbox, relax)
    cells = voronoi_cells(sites, work_bbox)
    out: List[List[Point]] = []
    for cell in cells:
        poly = scale_points(cell, ax, 1.0)
        if smooth > 0:
            poly = chaikin(poly, smooth, closed=True)
        if inset > 0:
            reduced = inset_polygon(poly, inset)
            if reduced is None:
                continue
            poly = reduced
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
                        help="Chaikin-Eckenglättung: 0 = eckig, 3 = rund wie Kiesel."))
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

    def cells_for(self, params: Dict[str, Any], ctx: GenContext) -> List[List[Point]]:
        return build_cells(
            ctx,
            count=int(params.get("cellCount", 120)),
            relax=int(params.get("relax", 1)),
            anisotropy=float(params.get("anisotropy", 1.0)),
            rows=int(params.get("rows", 0)),
            smooth=int(params.get("roundness", 0)),
            inset=float(params.get("inset", 0.0)),
        )
