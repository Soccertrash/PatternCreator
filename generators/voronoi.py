"""Voronoi - Grundbaustein aller organischen Muster."""

from __future__ import annotations

from typing import Any, Dict, List

from core import ir

from .base import GenContext
from .organic_cells import OrganicGenerator, cell_params


class VoronoiGenerator(OrganicGenerator):
    id = "voronoi"
    tiling = True
    label = "Voronoi"
    description = ("Zufällige Zellstruktur (Voronoi-Diagramm). Grundbaustein für "
                   "Blattzellen, Kiesel, Gewebe und Kaustik.")
    icon = "M3 3l6 4-2 7 5 7M9 7l8-4M7 14l10 1M17 3l4 6-4 6M17 15l1 6"
    presets = {
        "fein": {"cellCount": 300, "relax": 1},
        "mittel": {"cellCount": 120, "relax": 1},
        "grob": {"cellCount": 40, "relax": 2},
    }
    params = cell_params(default_count=120, with_smooth=True, with_inset=True)

    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        return [ir.path(c, closed=True, role=ir.ROLE_REGION)
                for c in self.cells_for(params, ctx)]
