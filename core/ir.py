"""Zwischenrepraesentation (IR) fuer PatternCreator.

Die IR ist bewusst **Fusion-frei**: sie wird sowohl vom Canvas-Renderer der
Palette (als JSON) als auch vom Fusion-Renderer (``fusion/renderer.py``)
konsumiert. Dadurch koennen Vorschau und erzeugte Skizze nicht auseinanderlaufen.

Alle Koordinaten sind in **cm** (API-interne Laengeneinheit von Fusion).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]

# Rollen steuern die Weiterverarbeitung im Style-Schritt.
ROLE_EDGE = "edge"        # offene/geschlossene Kurve -> im Flaechenmodus gestrichelt zu Streifen
ROLE_REGION = "region"    # geschlossene Zelle -> im Flaechenmodus eingezogen (Inset)
ROLE_DECOR = "decor"      # eigenstaendiges Element (z. B. Zellkern), wird nicht gestrokt

# Layer trennen Muster, Containerumriss und Text.
LAYER_PATTERN = "pattern"
LAYER_BORDER = "border"
LAYER_TEXT = "text"


@dataclass
class Path:
    """Polylinie oder Spline (ueber Stuetzpunkte definiert)."""

    points: List[Point]
    closed: bool = False
    curve: str = "line"           # "line" | "spline"
    role: str = ROLE_EDGE
    layer: str = LAYER_PATTERN
    widths: Optional[List[float]] = None   # variable Dicke je Stuetzpunkt (cm)

    def to_dict(self) -> dict:
        d = {
            "t": "path",
            "pts": [[round(x, 6), round(y, 6)] for x, y in self.points],
            "closed": self.closed,
            "curve": self.curve,
            "role": self.role,
            "layer": self.layer,
        }
        if self.widths is not None:
            d["widths"] = [round(w, 6) for w in self.widths]
        return d


@dataclass
class Circle:
    center: Point
    radius: float
    role: str = ROLE_DECOR
    layer: str = LAYER_PATTERN

    def to_dict(self) -> dict:
        return {
            "t": "circle",
            "c": [round(self.center[0], 6), round(self.center[1], 6)],
            "r": round(self.radius, 6),
            "role": self.role,
            "layer": self.layer,
        }


@dataclass
class Arc:
    """Kreisbogen; Winkel im Bogenmass, gegen den Uhrzeigersinn von ``a0`` nach ``a1``."""

    center: Point
    radius: float
    a0: float
    a1: float
    role: str = ROLE_EDGE
    layer: str = LAYER_PATTERN

    def to_dict(self) -> dict:
        return {
            "t": "arc",
            "c": [round(self.center[0], 6), round(self.center[1], 6)],
            "r": round(self.radius, 6),
            "a0": round(self.a0, 6),
            "a1": round(self.a1, 6),
            "role": self.role,
            "layer": self.layer,
        }


@dataclass
class Ellipse:
    center: Point
    rx: float
    ry: float
    rotation: float = 0.0
    role: str = ROLE_EDGE
    layer: str = LAYER_BORDER

    def to_dict(self) -> dict:
        return {
            "t": "ellipse",
            "c": [round(self.center[0], 6), round(self.center[1], 6)],
            "rx": round(self.rx, 6),
            "ry": round(self.ry, 6),
            "rot": round(self.rotation, 6),
            "role": self.role,
            "layer": self.layer,
        }


@dataclass
class TextItem:
    text: str
    x: float
    y: float
    height: float
    angle: float = 0.0            # Bogenmass
    font: str = "Arial"
    layer: str = LAYER_TEXT
    role: str = ROLE_DECOR

    def to_dict(self) -> dict:
        return {
            "t": "text",
            "text": self.text,
            "x": round(self.x, 6),
            "y": round(self.y, 6),
            "h": round(self.height, 6),
            "angle": round(self.angle, 6),
            "font": self.font,
            "layer": self.layer,
            "role": self.role,
        }


Element = object  # Path | Circle | Arc | Ellipse | TextItem


@dataclass
class Scene:
    """Ergebnis eines Generierungslaufs."""

    elements: List[Element] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # -- Statistik -------------------------------------------------------
    def counts(self) -> dict:
        contours = 0
        areas = 0
        texts = 0
        for el in self.elements:
            if isinstance(el, TextItem):
                texts += 1
                continue
            contours += 1
            if isinstance(el, (Circle, Ellipse)):
                areas += 1
            elif isinstance(el, Path) and el.closed:
                areas += 1
        return {"contours": contours, "areas": areas, "texts": texts}

    def bounds(self) -> Tuple[float, float, float, float]:
        xs: List[float] = []
        ys: List[float] = []
        for el in self.elements:
            if isinstance(el, Path):
                for x, y in el.points:
                    xs.append(x)
                    ys.append(y)
            elif isinstance(el, Circle):
                xs.extend([el.center[0] - el.radius, el.center[0] + el.radius])
                ys.extend([el.center[1] - el.radius, el.center[1] + el.radius])
            elif isinstance(el, Ellipse):
                r = max(el.rx, el.ry)
                xs.extend([el.center[0] - r, el.center[0] + r])
                ys.extend([el.center[1] - r, el.center[1] + r])
            elif isinstance(el, Arc):
                xs.extend([el.center[0] - el.radius, el.center[0] + el.radius])
                ys.extend([el.center[1] - el.radius, el.center[1] + el.radius])
            elif isinstance(el, TextItem):
                xs.extend([el.x, el.x + el.height * max(1, len(el.text))])
                ys.extend([el.y, el.y + el.height])
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def to_dict(self) -> dict:
        x0, y0, x1, y1 = self.bounds()
        return {
            "elements": [el.to_dict() for el in self.elements],
            "stats": self.counts(),
            "bounds": [round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)],
            "warnings": list(self.warnings),
        }


def path(points: Sequence[Point], closed: bool = False, **kw) -> Path:
    """Kurzform-Konstruktor fuer Generatoren."""
    return Path(points=[(float(p[0]), float(p[1])) for p in points], closed=closed, **kw)
