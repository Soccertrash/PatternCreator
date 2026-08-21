"""Blattadern - zweistufiges Voronoi (Hauptadern + Nebenadern)."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from core import ir
from core.clip import clip_polygon
from core.geom import bbox, erode_convex, polygon_area
from core.pattern_doc import Param, T_FLOAT, T_INT

from .base import GenContext
from .organic_cells import (ROUND_FACTORS, OrganicGenerator, build_cells,
                            round_corners, scatter_in_polygon, voronoi_cells)

Point = Tuple[float, float]


class LeafVeinsGenerator(OrganicGenerator):
    id = "leaf_veins"
    tiling = True
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
        """Die Zellen **zwischen** den Adern, nicht die Adern selbst.

        Die Adern sind das, was zwischen den Zellen stehen bleibt - genau wie bei
        Wabe oder Kiesel. Vorher wurde jede Ader einzeln gestrichelt und gestrokt;
        an jedem Aderknoten überlappten sich die Streifen, das Muster bestand aus
        hunderten sich schneidenden Rechtecken und ergab in Fusion keinen
        einzelnen Körper. Die Dicke der Hauptadern entsteht jetzt geometrisch:
        jede Grobzelle wird vor dem Unterteilen um ``(veinRatio - 1) * Dicke / 2``
        verkleinert. Zwei Feinzellen derselben Grobzelle trennt dann eine Stegdicke
        (Nebenader), zwei Feinzellen verschiedener Grobzellen ``veinRatio``
        Stegdicken (Hauptader).
        """
        coarse_n = int(params.get("coarseCells", 14))
        fine_n = int(params.get("fineCells", 9))
        ratio = max(1.0, float(params.get("veinRatio", 2.5)))
        smooth = min(int(params.get("roundness", 1)), len(ROUND_FACTORS) - 1)
        factor = ROUND_FACTORS[smooth]
        rnd = ctx.rnd

        coarse = build_cells(ctx, count=coarse_n, relax=int(params.get("relax", 2)))
        extra = (ratio - 1.0) * ctx.thickness / 2.0

        out: List[Any] = []
        for cell in coarse:
            inner = erode_convex(cell, extra) if extra > 1e-9 else list(cell)
            if inner is None or len(inner) < 3:
                continue
            for sub in self._sub_cells(inner, fine_n, rnd):
                out.append(ir.path(round_corners(sub, factor), closed=True,
                                   role=ir.ROLE_REGION))
        return out

    def seam_cells(self, params: Dict[str, Any], ctx: GenContext):
        """Die Grobzellen: ihre Waende **sind** die Hauptadern.

        Genau dort gehoert die Naht hin. Laeuft sie mitten durch eine Hauptader,
        treffen sich nach dem Wickeln deren beide Haelften und niemand sieht,
        wo der Schnitt war.
        """
        return build_cells(ctx, count=int(params.get("coarseCells", 14)),
                           relax=int(params.get("relax", 2)))

    @staticmethod
    def _sub_cells(cell: Sequence[Point], count: int, rnd) -> List[List[Point]]:
        """Grobzelle in Feinzellen unterteilen (leere Liste = Zelle bleibt ganz)."""
        if count <= 0:
            return [list(cell)]
        sites = scatter_in_polygon(cell, count, rnd)
        if len(sites) < 2:
            return [list(cell)]
        out: List[List[Point]] = []
        for sub in voronoi_cells(sites, bbox(cell)):
            clipped = clip_polygon(sub, cell)
            if len(clipped) >= 3 and abs(polygon_area(clipped)) > 1e-9:
                out.append(clipped)
        return out or [list(cell)]
