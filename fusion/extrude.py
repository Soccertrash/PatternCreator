"""Optionale integrierte Extrusion direkt nach dem Zeichnen.

Der Flaechenmodus liefert saubere, geschlossene Profile. Hier werden alle
Profile der Skizze eingesammelt, nach "Stege" bzw. "Zellen" gefiltert und in
**einem** ``extrudeFeature`` verarbeitet - damit bleibt der Commit ein einziger
Timeline-Schritt.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import adsk.core
import adsk.fusion

OPERATIONS = {
    "new": adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    "join": adsk.fusion.FeatureOperations.JoinFeatureOperation,
    "cut": adsk.fusion.FeatureOperations.CutFeatureOperation,
}


def extrude_sketch(sketch: "adsk.fusion.Sketch", depth: float, operation: str = "new",
                   direction: str = "positive", fill_target: str = "webs"
                   ) -> Tuple[Optional["adsk.fusion.ExtrudeFeature"], Optional[str]]:
    """Alle passenden Profile der Skizze extrudieren.

    ``fill_target`` steuert die Auswahl:
    * ``webs``  - die Steg-Profile (alles ausser dem groessten Aussenprofil)
    * ``cells`` - dieselbe Menge; im Zellen-Modus sind die Zellen bereits die
      gezeichneten Profile.
    """
    comp = sketch.parentComponent
    profiles = _collect_profiles(sketch)
    if not profiles:
        return None, "Die Skizze enthält keine geschlossenen Profile zum Extrudieren."

    coll = adsk.core.ObjectCollection.create()
    for p in profiles:
        coll.add(p)

    op = OPERATIONS.get(operation, OPERATIONS["new"])
    extrudes = comp.features.extrudeFeatures
    ext_input = extrudes.createInput(coll, op)
    distance = adsk.core.ValueInput.createByReal(abs(depth))
    if direction == "symmetric":
        ext_input.setSymmetricExtent(distance, True)
    else:
        signed = adsk.core.ValueInput.createByReal(
            abs(depth) if direction != "negative" else -abs(depth))
        ext_input.setDistanceExtent(False, signed)
    try:
        feature = extrudes.add(ext_input)
    except Exception as exc:                       # pragma: no cover - nur in Fusion
        return None, "Extrusion fehlgeschlagen: %s" % exc
    return feature, None


def _collect_profiles(sketch: "adsk.fusion.Sketch") -> List["adsk.fusion.Profile"]:
    """Profile einsammeln; das umschliessende Aussenprofil wird ausgelassen."""
    profiles = [p for p in sketch.profiles]
    if len(profiles) <= 1:
        return profiles
    areas = []
    for p in profiles:
        try:
            areas.append((p.areaProperties(
                adsk.fusion.CalculationAccuracy.LowCalculationAccuracy).area, p))
        except Exception:
            areas.append((0.0, p))
    areas.sort(key=lambda t: t[0], reverse=True)
    largest, rest = areas[0], areas[1:]
    total_rest = sum(a for a, _ in rest)
    # Ein Profil, das (nahezu) die Summe aller anderen umfasst, ist der Rahmen.
    if rest and largest[0] > total_rest * 0.9:
        return [p for _, p in rest]
    return [p for _, p in areas]
