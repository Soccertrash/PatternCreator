"""PatternDoc <-> Fusion-Attribute an der Skizze."""

from __future__ import annotations

from typing import List, Optional, Tuple

import adsk.core
import adsk.fusion

from core import pattern_doc

GROUP = "PatternCreator"
KEY_DOC = "doc"
KEY_VERSION = "version"
KEY_ENTITIES = "entityCount"


def save(sketch: "adsk.fusion.Sketch", doc: dict, entity_count: int = 0) -> None:
    attrs = sketch.attributes
    attrs.add(GROUP, KEY_DOC, pattern_doc.serialize(doc))
    attrs.add(GROUP, KEY_VERSION, str(pattern_doc.DOC_VERSION))
    attrs.add(GROUP, KEY_ENTITIES, str(entity_count))


def load(sketch: "adsk.fusion.Sketch") -> Optional[dict]:
    attr = sketch.attributes.itemByName(GROUP, KEY_DOC)
    if attr is None:
        return None
    return pattern_doc.deserialize(attr.value)


def is_pattern_sketch(entity) -> bool:
    try:
        return (isinstance(entity, adsk.fusion.Sketch)
                and entity.attributes.itemByName(GROUP, KEY_DOC) is not None)
    except Exception:
        return False


def stored_entity_count(sketch: "adsk.fusion.Sketch") -> int:
    attr = sketch.attributes.itemByName(GROUP, KEY_ENTITIES)
    try:
        return int(attr.value) if attr else 0
    except (TypeError, ValueError):
        return 0


def was_modified_manually(sketch: "adsk.fusion.Sketch") -> bool:
    """Heuristik: weicht die aktuelle Entity-Zahl von der gespeicherten ab?"""
    expected = stored_entity_count(sketch)
    if expected <= 0:
        return False
    actual = sketch.sketchCurves.count + sketch.sketchTexts.count
    return actual != expected


def find_pattern_sketches(design: "adsk.fusion.Design") -> List[Tuple[str, "adsk.fusion.Sketch"]]:
    """Alle Muster-Skizzen des Dokuments (Name, Skizze)."""
    found: List[Tuple[str, "adsk.fusion.Sketch"]] = []
    for comp in design.allComponents:
        for sketch in comp.sketches:
            if is_pattern_sketch(sketch):
                label = sketch.name
                if comp != design.rootComponent:
                    label = "%s / %s" % (comp.name, sketch.name)
                found.append((label, sketch))
    return found
