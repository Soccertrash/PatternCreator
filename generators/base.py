"""Basisklasse und Kontext fuer alle Muster-Generatoren.

Generatoren sind **Fusion-frei** und **deterministisch**: der einzige
Zufallsgenerator ist ``ctx.rnd`` (eine ``random.Random(seed)``-Instanz).
Sie fuellen immer das Bounding-Rechteck ``ctx.bbox``; das Clipping gegen die
Container-Form macht ``core/build.py`` zentral.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.pattern_doc import Param

Point = Tuple[float, float]


@dataclass
class GenContext:
    """Alles, was ein Generator ausser seinen eigenen Parametern braucht."""

    bbox: Tuple[float, float, float, float]
    rnd: random.Random
    thickness: float = 0.08
    fill_target: str = "webs"
    mode: str = "area"

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def center(self) -> Point:
        return ((self.bbox[0] + self.bbox[2]) / 2.0, (self.bbox[1] + self.bbox[3]) / 2.0)

    def expanded(self, margin: float) -> Tuple[float, float, float, float]:
        x0, y0, x1, y1 = self.bbox
        return (x0 - margin, y0 - margin, x1 + margin, y1 + margin)


class Generator:
    """Abstrakte Basis. Ein neues Muster = neue Datei + Registry-Eintrag."""

    id: str = ""
    label: str = ""
    description: str = ""
    icon: str = ""                       # SVG-Pfaddaten (viewBox 0 0 24 24)
    #: Welche Flaechen-Ziele sinnvoll sind ("webs" = Stege, "cells" = Zellen)
    fill_targets: Tuple[str, ...] = ("webs", "cells")
    #: True, wenn der Generator den Zellabstand selbst erzeugt (eigene Fugenbreite)
    own_gap: bool = False
    #: True, wenn die Zellen die Flaeche lueckenlos kacheln (Gitter, Wabe, Voronoi ...).
    #: Nur dann ist das Stegnetz exakt "Rahmen minus verkleinerte Zellen" und laesst
    #: sich als **eine** Flaeche mit Loechern erzeugen (siehe ``core/build.py``).
    tiling: bool = False
    #: Voreinstellungen fuer den Editor
    presets: Dict[str, Dict[str, Any]] = {}

    params: List[Param] = []

    # -- Schnittstelle ----------------------------------------------------
    def generate(self, params: Dict[str, Any], ctx: GenContext) -> List[Any]:
        raise NotImplementedError

    def gap(self, params: Dict[str, Any]) -> float:
        """Fugenbreite, die der Generator **selbst** zwischen den Zellen laesst.

        0.0 heisst: die Zellen stossen aneinander, die Stegbreite kommt allein
        aus der eingestellten Dicke. Nur fuer ``tiling``-Generatoren relevant.
        """
        return 0.0

    # -- Hilfen -----------------------------------------------------------
    @classmethod
    def defaults(cls) -> Dict[str, Any]:
        return {p.key: p.default for p in cls.params}

    @classmethod
    def schema(cls) -> dict:
        return {
            "id": cls.id,
            "label": cls.label,
            "description": cls.description,
            "icon": cls.icon,
            "fillTargets": list(cls.fill_targets),
            "ownGap": cls.own_gap,
            "presets": cls.presets,
            "params": [p.to_dict() for p in cls.params],
        }
