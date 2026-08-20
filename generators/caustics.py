"""Wasser-Kaustik - geglättete Netzkanten mit variabler Dicke."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from core import ir
from core.geom import (chain_segments, dist, normalize, polygon_segments, resample,
                       snap_segments, sub)
from core.pattern_doc import Param, T_BOOL, T_FLOAT, T_INT, T_PERCENT

from .base import GenContext
from .organic_cells import MAX_CELLS, OrganicGenerator, build_cells

Point = Tuple[float, float]


class CausticsGenerator(OrganicGenerator):
    id = "caustics"
    label = "Wasser-Kaustik"
    description = ("Lichtnetz wie auf einem Poolboden: geglättete Voronoi-Kanten mit "
                   "welligem Verlauf und wechselnder Dicke, optional zweilagig.")
    icon = "M3 8c3-4 6 4 9 0s6-4 9 0M3 16c3-4 6 4 9 0s6-4 9 0"
    fill_targets = ("webs",)
    own_gap = False
    presets = {
        "fein": {"cellCount": 150, "jitterAmount": 0.5},
        "mittel": {"cellCount": 60, "jitterAmount": 0.6},
        "grob": {"cellCount": 25, "jitterAmount": 0.8},
    }

    params = [
        Param("cellCount", "Maschenzahl", T_INT, 60, min=3, max=MAX_CELLS, step=1),
        Param("relax", "Gleichmäßigkeit", T_INT, 2, min=0, max=3, step=1),
        Param("jitterAmount", "Unruhe", T_FLOAT, 0.6, min=0.0, max=2.0, step=0.05,
              help="Wellige Auslenkung der Kanten quer zur Laufrichtung."),
        Param("thicknessVariation", "Dickenvariation", T_PERCENT, 60.0, min=0.0, max=95.0,
              step=5.0, help="Wie stark die Strichstärke entlang der Kante schwankt."),
        Param("secondLayer", "Zweite Ebene", T_BOOL, False,
              help="Überlagert ein zweites, feineres Netz mit eigenem Seed."),
        Param("secondScale", "Feinheit 2. Ebene", T_FLOAT, 2.0, min=1.1, max=6.0, step=0.1,
              visible_if={"secondLayer": [True]}),
    ]

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        out = self._layer(params, ctx, count=int(params.get("cellCount", 120)),
                          width_factor=1.0, seed_offset=0)
        if params.get("secondLayer"):
            scale = float(params.get("secondScale", 2.0))
            count = min(MAX_CELLS, max(3, int(params.get("cellCount", 120) * scale)))
            out += self._layer(params, ctx, count=count, width_factor=0.45,
                               seed_offset=7919)
        return out

    # ------------------------------------------------------------------
    def _layer(self, params: Dict[str, Any], ctx: GenContext, count: int,
               width_factor: float, seed_offset: int) -> List[Any]:
        import random as _random

        rnd = ctx.rnd if seed_offset == 0 else _random.Random(
            ctx.rnd.randrange(0, 10 ** 6) + seed_offset)
        sub_ctx = GenContext(bbox=ctx.bbox, rnd=rnd, thickness=ctx.thickness,
                             fill_target=ctx.fill_target, mode=ctx.mode)
        cells = build_cells(sub_ctx, count=count, relax=int(params.get("relax", 2)),
                            smooth=2)
        segs: List[Tuple[Point, Point]] = []
        for cell in cells:
            segs.extend(polygon_segments(cell))
        chains = chain_segments(snap_segments(segs))

        jitter = float(params.get("jitterAmount", 0.6))
        variation = float(params.get("thicknessVariation", 60.0)) / 100.0
        base_w = max(1e-4, ctx.thickness * width_factor)
        step = max(0.02, min(0.35, (ctx.width + ctx.height) / 70.0))

        out: List[Any] = []
        for pts, closed in chains:
            if len(pts) < 2:
                continue
            pts = resample(pts, step, closed=closed)
            if len(pts) < 3:
                continue
            phase = rnd.random() * 2 * math.pi
            freq = 0.8 + rnd.random() * 1.6
            amp = jitter * step * 0.9
            wavy: List[Point] = []
            widths: List[float] = []
            n = len(pts)
            for i, p in enumerate(pts):
                nxt = pts[min(i + 1, n - 1)]
                prv = pts[max(i - 1, 0)]
                d = normalize(sub(nxt, prv))
                nrm = (-d[1], d[0])
                edge_fade = 1.0 if closed else math.sin(math.pi * i / max(1, n - 1))
                off = amp * math.sin(phase + freq * i * 0.6) * edge_fade
                wavy.append((p[0] + nrm[0] * off, p[1] + nrm[1] * off))
                w = base_w * (1.0 - variation * 0.5
                              * (1.0 + math.sin(phase * 1.7 + i * 0.35)))
                widths.append(max(base_w * 0.12, w))
            out.append(ir.Path(points=wavy, closed=closed, curve="spline",
                               role=ir.ROLE_EDGE, widths=widths))
        return out
