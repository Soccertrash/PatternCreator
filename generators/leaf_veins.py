"""Blattadern - zweistufiges Voronoi (Hauptadern + Nebenadern)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

from core import ir
from core.clip import clip_polygon
from core.geom import (bbox, chain_segments, chaikin, dist, polygon_area,
                       polygon_segments, snap_segments)
from core.pattern_doc import Param, T_FLOAT, T_INT

from .base import GenContext
from .organic_cells import MAX_CELLS, OrganicGenerator, build_cells, voronoi_cells

Point = Tuple[float, float]


def _on_boundary(p: Point, poly: Sequence[Point], tol: float) -> bool:
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        abx, aby = b[0] - a[0], b[1] - a[1]
        ll = abx * abx + aby * aby
        if ll < 1e-12:
            continue
        t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / ll
        t = max(0.0, min(1.0, t))
        if dist(p, (a[0] + abx * t, a[1] + aby * t)) <= tol:
            return True
    return False


class LeafVeinsGenerator(OrganicGenerator):
    id = "leaf_veins"
    label = "Blattadern"
    description = ("Zweistufiges Adernetz: grobe Zellen bilden die dicken Hauptadern, "
                   "ein feines Sub-Voronoi je Zelle die dünnen Nebenadern.")
    icon = "M5 19c0-8 6-14 14-14 0 8-6 14-14 14zM5 19 16 8M9 15l2-5M12 12l2-5"
    fill_targets = ("webs",)
    own_gap = False
    presets = {
        "fein": {"coarseCells": 26, "fineCells": 14},
        "mittel": {"coarseCells": 14, "fineCells": 9},
        "grob": {"coarseCells": 7, "fineCells": 6},
    }

    params = [
        Param("coarseCells", "Grobzellen", T_INT, 14, min=2, max=120, step=1,
              help="Zahl der Hauptader-Zellen."),
        Param("fineCells", "Feinzellen je Grobzelle", T_INT, 9, min=0, max=40, step=1,
              help="0 = nur Hauptadern."),
        Param("relax", "Gleichmäßigkeit", T_INT, 2, min=0, max=3, step=1),
        Param("veinRatio", "Dickenverhältnis", T_FLOAT, 2.5, min=1.0, max=8.0, step=0.1,
              help="Wie viel dicker die Hauptadern gegenüber den Nebenadern sind."),
        Param("roundness", "Rundheit", T_INT, 1, min=0, max=3, step=1),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        coarse_n = int(params.get("coarseCells", 14))
        fine_n = int(params.get("fineCells", 9))
        ratio = float(params.get("veinRatio", 2.5))
        smooth = int(params.get("roundness", 1))
        rnd = ctx.rnd

        coarse = build_cells(ctx, count=coarse_n, relax=int(params.get("relax", 2)),
                             smooth=smooth)
        thin = ctx.thickness
        thick = ctx.thickness * ratio

        out: List[Any] = []

        # -- Hauptadern ---------------------------------------------------
        segs: List[Tuple[Point, Point]] = []
        for cell in coarse:
            segs.extend(polygon_segments(cell))
        for pts, closed in chain_segments(snap_segments(segs)):
            if len(pts) >= 2:
                out.append(ir.Path(points=pts, closed=closed,
                                   curve="spline" if smooth else "line",
                                   role=ir.ROLE_EDGE, widths=[thick] * len(pts)))

        # -- Nebenadern je Grobzelle -------------------------------------
        if fine_n > 0:
            for cell in coarse:
                x0, y0, x1, y1 = bbox(cell)
                if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
                    continue
                sites: List[Point] = []
                guard = 0
                while len(sites) < fine_n and guard < fine_n * 40:
                    guard += 1
                    p = (x0 + rnd.random() * (x1 - x0), y0 + rnd.random() * (y1 - y0))
                    if _point_in(p, cell):
                        sites.append(p)
                if len(sites) < 2:
                    continue
                tol = min(x1 - x0, y1 - y0) * 0.02 + 1e-6
                sub_segs: List[Tuple[Point, Point]] = []
                for sub in voronoi_cells(sites, (x0, y0, x1, y1)):
                    clipped = clip_polygon(sub, cell)
                    if len(clipped) < 3 or abs(polygon_area(clipped)) < 1e-9:
                        continue
                    for a, b in polygon_segments(clipped):
                        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                        if _on_boundary(mid, cell, tol):
                            continue        # liegt auf der Hauptader
                        sub_segs.append((a, b))
                for pts, closed in chain_segments(snap_segments(sub_segs)):
                    if len(pts) >= 2:
                        out.append(ir.Path(points=pts, closed=closed, curve="line",
                                           role=ir.ROLE_EDGE, widths=[thin] * len(pts)))
        return out


def _point_in(p: Point, poly: Sequence[Point]) -> bool:
    from core.geom import point_in_polygon
    return point_in_polygon(p, poly)
