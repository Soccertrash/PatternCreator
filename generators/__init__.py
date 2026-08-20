"""Generator-Registry.

Ein neues Muster besteht aus **einer neuen Datei** und **einem Eintrag hier** -
weder Editor noch Command-Code muessen angefasst werden. Die Formulare im Editor
entstehen generisch aus ``Generator.params``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Type

from .base import GenContext, Generator
from .brick import BrickGenerator
from .grid import GridGenerator
from .honeycomb import HoneycombGenerator
from .puzzle import PuzzleGenerator
from .rhombus import RhombusGenerator

#: Reihenfolge = Reihenfolge im Editor-Dropdown (technisch, dann natuerlich)
GENERATOR_CLASSES: List[Type[Generator]] = [
    GridGenerator,
    RhombusGenerator,
    HoneycombGenerator,
    BrickGenerator,
    PuzzleGenerator,
]

REGISTRY: Dict[str, Type[Generator]] = {cls.id: cls for cls in GENERATOR_CLASSES}

#: Gruppierung nur fuer die Anzeige im Dropdown
GROUPS = [
    ("Technisch", ["grid", "rhombus", "honeycomb", "brick", "puzzle"]),
]


def get_generator(pattern_id: str) -> Generator:
    cls = REGISTRY.get(pattern_id)
    if cls is None:
        raise KeyError(pattern_id)
    return cls()


def params_for(pattern_id: str):
    cls = REGISTRY.get(pattern_id)
    return cls.params if cls else []


def default_params(pattern_id: str) -> Dict[str, Any]:
    cls = REGISTRY.get(pattern_id)
    return cls.defaults() if cls else {}


def registry_schema() -> List[dict]:
    groups = {gid: name for name, ids in GROUPS for gid in ids}
    out = []
    for cls in GENERATOR_CLASSES:
        s = cls.schema()
        s["group"] = groups.get(cls.id, "Weitere")
        out.append(s)
    return out


__all__ = ["GenContext", "Generator", "REGISTRY", "GROUPS", "get_generator",
           "params_for", "default_params", "registry_schema"]
