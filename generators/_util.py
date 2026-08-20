"""Gemeinsame Bausteine mehrerer Generatoren (Lattice-Zellen, Wabenraster ...)."""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from core.geom import EPS, add

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]


def bbox_polygon(bbox: BBox) -> List[Point]:
    x0, y0, x1, y1 = bbox
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def expand(bbox: BBox, margin: float) -> BBox:
    x0, y0, x1, y1 = bbox
    return (x0 - margin, y0 - margin, x1 + margin, y1 + margin)


def lattice_cells(bbox: BBox, e1: Point, e2: Point, origin: Point = (0.0, 0.0),
                  margin: float = 0.0, max_cells: int = 20000) -> List[List[Point]]:
    """Parallelogramm-Zellen eines von ``e1``/``e2`` aufgespannten Gitters."""
    det = e1[0] * e2[1] - e1[1] * e2[0]
    if abs(det) < 1e-12:
        return []
    box = expand(bbox, margin)
    inv = ((e2[1] / det, -e2[0] / det), (-e1[1] / det, e1[0] / det))
    us: List[float] = []
    vs: List[float] = []
    for c in bbox_polygon(box):
        p = (c[0] - origin[0], c[1] - origin[1])
        us.append(inv[0][0] * p[0] + inv[0][1] * p[1])
        vs.append(inv[1][0] * p[0] + inv[1][1] * p[1])
    i0, i1 = int(math.floor(min(us))) - 1, int(math.ceil(max(us))) + 1
    j0, j1 = int(math.floor(min(vs))) - 1, int(math.ceil(max(vs))) + 1
    if (i1 - i0 + 1) * (j1 - j0 + 1) > max_cells:
        return []
    out: List[List[Point]] = []
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            base = (origin[0] + i * e1[0] + j * e2[0], origin[1] + i * e1[1] + j * e2[1])
            quad = [base,
                    add(base, e1),
                    add(base, add(e1, e2)),
                    add(base, e2)]
            if _quad_hits(quad, box):
                out.append(quad)
    return out


def _quad_hits(quad: Sequence[Point], box: BBox) -> bool:
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return not (max(xs) < box[0] or min(xs) > box[2]
                or max(ys) < box[1] or min(ys) > box[3])


def hex_centers(bbox: BBox, cell_size: float, flat_top: bool, margin: float = 0.0
                ) -> List[Point]:
    """Mittelpunkte eines Wabenrasters; ``cell_size`` = Schluesselweite."""
    if cell_size <= EPS:
        return []
    box = expand(bbox, margin + cell_size)
    r = cell_size / math.sqrt(3.0)          # Umkreisradius aus Schluesselweite
    if flat_top:
        dx = 1.5 * r
        dy = cell_size
        cols = int(math.ceil((box[2] - box[0]) / dx)) + 2
        rows = int(math.ceil((box[3] - box[1]) / dy)) + 2
        out = []
        for i in range(-1, cols):
            for j in range(-1, rows):
                x = box[0] + i * dx
                y = box[1] + j * dy + (dy / 2 if i % 2 else 0.0)
                out.append((x, y))
        return out
    dx = cell_size
    dy = 1.5 * r
    cols = int(math.ceil((box[2] - box[0]) / dx)) + 2
    rows = int(math.ceil((box[3] - box[1]) / dy)) + 2
    out = []
    for j in range(-1, rows):
        for i in range(-1, cols):
            x = box[0] + i * dx + (dx / 2 if j % 2 else 0.0)
            y = box[1] + j * dy
            out.append((x, y))
    return out


def bezier(p0: Point, p1: Point, p2: Point, p3: Point, samples: int = 12) -> List[Point]:
    """Kubische Bezier-Kurve abtasten (ohne Endpunkt ``p3``)."""
    out = []
    for i in range(samples):
        t = i / float(samples)
        mt = 1 - t
        x = (mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0]
             + 3 * mt * t * t * p2[0] + t ** 3 * p3[0])
        y = (mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1]
             + 3 * mt * t * t * p2[1] + t ** 3 * p3[1])
        out.append((x, y))
    return out
