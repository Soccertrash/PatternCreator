"""Additive Text-Ebene inklusive Knockout.

Die Ebene liegt **über** dem Muster und landet im selben Commit in derselben
Skizze. Mit aktivem Knockout wird das Muster im Bereich der (gedrehten)
Text-Bounding-Box plus Rand ausgestanzt, damit der Text lesbar bleibt und beim
Extrudieren keine überlappenden Profile aus Text + Muster entstehen.

Modul ist **Fusion-frei** - die eigentliche ``SketchText``-Erzeugung passiert in
``fusion/renderer.py``.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core import ir
from core.clip import polygon_intersects, subtract_polyline
from core.geom import rotate

Point = Tuple[float, float]

#: Naeherung fuer die mittlere Zeichenbreite einer Proportionalschrift
CHAR_WIDTH_FACTOR = 0.62
LINE_SPACING = 1.35


def text_lines(layer: Dict[str, Any]) -> List[str]:
    return str(layer.get("text", "")).split("\n")


def text_box(layer: Dict[str, Any], margin: Optional[float] = None) -> Optional[List[Point]]:
    """Gedrehte Bounding-Box des Textes (4 Punkte) inklusive Rand.

    Gibt ``None`` zurueck, wenn die Ebene aus ist oder keinen Text enthaelt.
    """
    if not layer.get("enabled"):
        return None
    lines = text_lines(layer)
    if not any(l.strip() for l in lines):
        return None
    h = float(layer.get("height", 1.0))
    if margin is None:
        margin = float(layer.get("knockoutMargin", 0.0))
    cols = max(len(l) for l in lines)
    w = cols * h * CHAR_WIDTH_FACTOR
    total_h = h * (1 + (len(lines) - 1) * LINE_SPACING)
    x = float(layer.get("x", 0.0))
    y = float(layer.get("y", 0.0))
    angle = math.radians(float(layer.get("angle", 0.0)))
    # lokale Box: Ursprung links unten an der letzten Zeile
    x0, y0 = -margin, -margin
    x1, y1 = w + margin, total_h + margin
    local = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [(x + p[0] * math.cos(angle) - p[1] * math.sin(angle),
             y + p[0] * math.sin(angle) + p[1] * math.cos(angle)) for p in local]


def text_elements(layer: Dict[str, Any]) -> List[Any]:
    """IR-Elemente der Text-Ebene (ein ``TextItem`` je Zeile)."""
    if not layer.get("enabled"):
        return []
    lines = text_lines(layer)
    if not any(l.strip() for l in lines):
        return []
    h = float(layer.get("height", 1.0))
    x = float(layer.get("x", 0.0))
    y = float(layer.get("y", 0.0))
    angle = math.radians(float(layer.get("angle", 0.0)))
    font = str(layer.get("font", "Arial")) or "Arial"
    out: List[Any] = []
    for i, line in enumerate(lines):
        if not line:
            continue
        dy = (len(lines) - 1 - i) * h * LINE_SPACING
        p = rotate((0.0, dy), angle)
        out.append(ir.TextItem(text=line, x=x + p[0], y=y + p[1], height=h,
                               angle=angle, font=font))
    return out


def apply_knockout(elements: Sequence[Any], boxes: Sequence[Sequence[Point]]) -> List[Any]:
    """Muster-Elemente im Bereich der Text-Boxen entfernen bzw. beschneiden.

    * offene Kurven werden geclippt (der Teil in der Box faellt weg)
    * geschlossene Zellen und Kreise werden entfernt, sobald sie die Box beruehren
    """
    if not boxes:
        return list(elements)
    out: List[Any] = []
    for el in elements:
        if getattr(el, "layer", ir.LAYER_PATTERN) != ir.LAYER_PATTERN:
            out.append(el)
            continue
        if isinstance(el, ir.Path):
            pieces = [el.points]
            closed = el.closed
            drop = False
            for box in boxes:
                if closed:
                    if polygon_intersects(el.points, box):
                        drop = True
                        break
                else:
                    nxt: List[List[Point]] = []
                    for piece in pieces:
                        nxt.extend(subtract_polyline(piece, box, closed=False))
                    pieces = nxt
            if drop or not pieces:
                continue
            if closed:
                out.append(el)
                continue
            for piece in pieces:
                out.append(ir.Path(points=piece, closed=False, curve=el.curve,
                                   role=el.role, layer=el.layer,
                                   widths=_trim_widths(el, piece)))
        elif isinstance(el, ir.Circle):
            poly = [(el.center[0] + el.radius * math.cos(2 * math.pi * i / 24),
                     el.center[1] + el.radius * math.sin(2 * math.pi * i / 24))
                    for i in range(24)]
            if any(polygon_intersects(poly, box) for box in boxes):
                continue
            out.append(el)
        elif isinstance(el, ir.Arc):
            poly = [(el.center[0] + el.radius * math.cos(el.a0 + (el.a1 - el.a0) * i / 12),
                     el.center[1] + el.radius * math.sin(el.a0 + (el.a1 - el.a0) * i / 12))
                    for i in range(13)]
            if not any(_polyline_hits(poly, box) for box in boxes):
                out.append(el)
        else:
            out.append(el)
    return out


def _polyline_hits(pts: Sequence[Point], box: Sequence[Point]) -> bool:
    """True, wenn irgendein Teil der Polylinie in der konvexen Box liegt."""
    from core.clip import clip_segment, half_planes
    planes = half_planes(box)
    for i in range(len(pts) - 1):
        if clip_segment(pts[i], pts[i + 1], planes) is not None:
            return True
    return False


def _trim_widths(el: "ir.Path", piece: Sequence[Point]) -> Optional[List[float]]:
    if el.widths is None:
        return None
    avg = sum(el.widths) / float(len(el.widths))
    return [avg] * len(piece)
