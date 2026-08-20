"""PatternDoc - das zentrale Datenmodell.

Der komplette Editor-Zustand (Mustertyp, Container, Stil, Text-Layer, Seed) ist
ein einziges JSON-Objekt. Editor, Generator, Vorschau, Attribut-Speicherung und
Re-Edit arbeiten ausschliesslich damit.

**Einheiten:** Im Dokument stehen Laengen in **cm** (Fusion-API-intern). Der
Editor zeigt **mm** an; umgerechnet wird nur an der Grenze Editor <-> Doc
(``ui_to_doc`` / ``doc_to_ui`` in ``palette/editor.js``).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

DOC_VERSION = 1

# Typen fuer Parameter-Schemata
T_LENGTH = "length"     # cm im Doc, mm im Editor
T_INT = "int"
T_FLOAT = "float"
T_ANGLE = "angle"       # Grad
T_CHOICE = "choice"
T_BOOL = "bool"
T_STRING = "string"
T_PERCENT = "percent"   # 0..100


@dataclass
class Param:
    """Deklaratives Parameter-Schema - der Editor baut daraus die Formulare."""

    key: str
    label: str
    type: str
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[List[Tuple[str, str]]] = None     # (wert, beschriftung)
    help: str = ""
    visible_if: Optional[Dict[str, List[Any]]] = None

    def to_dict(self) -> dict:
        d = {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "help": self.help,
        }
        for name in ("min", "max", "step"):
            v = getattr(self, name)
            if v is not None:
                d[name] = v
        if self.choices:
            d["choices"] = [{"value": v, "label": l} for v, l in self.choices]
        if self.visible_if:
            d["visibleIf"] = self.visible_if
        return d

    # -- Anzeige / Validierung -------------------------------------------
    def display(self, value: float) -> float:
        return value * 10.0 if self.type == T_LENGTH else value

    def unit(self) -> str:
        return {T_LENGTH: "mm", T_ANGLE: "°", T_PERCENT: "%"}.get(self.type, "")

    def range_text(self) -> str:
        if self.min is None and self.max is None:
            return ""
        u = self.unit()
        lo = _fmt(self.display(self.min)) + (" " + u if u else "") if self.min is not None else None
        hi = _fmt(self.display(self.max)) + (" " + u if u else "") if self.max is not None else None
        if lo is not None and hi is not None:
            return "zwischen %s und %s" % (lo, hi)
        if lo is not None:
            return "mindestens %s" % lo
        return "hoechstens %s" % hi


def _fmt(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.3f" % v).rstrip("0").rstrip(".").replace(".", ",")


# --------------------------------------------------------------- Schemata

CONTAINER_PARAMS: List[Param] = [
    Param("shape", "Form", T_CHOICE, "rect", choices=[
        ("rect", "Rechteck"), ("square", "Quadrat"), ("circle", "Kreis"),
        ("ellipse", "Ellipse"), ("polygon", "Vieleck")],
        help="Rahmenform, in die das Muster eingepasst wird."),
    Param("width", "Breite", T_LENGTH, 10.0, min=0.5, max=200.0, step=0.1,
          visible_if={"shape": ["rect", "ellipse"]}),
    Param("height", "Höhe", T_LENGTH, 6.0, min=0.5, max=200.0, step=0.1,
          visible_if={"shape": ["rect", "ellipse"]}),
    Param("width", "Kantenlänge", T_LENGTH, 10.0, min=0.5, max=200.0, step=0.1,
          visible_if={"shape": ["square"]}),
    Param("cornerRadius", "Eckenradius", T_LENGTH, 0.0, min=0.0, max=50.0, step=0.1,
          visible_if={"shape": ["rect", "square"]}),
    Param("diameter", "Durchmesser", T_LENGTH, 8.0, min=0.5, max=200.0, step=0.1,
          visible_if={"shape": ["circle", "polygon"]}),
    Param("sides", "Seitenzahl", T_INT, 6, min=3, max=12, step=1,
          visible_if={"shape": ["polygon"]}),
]

PLACEMENT_PARAMS: List[Param] = [
    Param("originX", "Ursprung X", T_LENGTH, 0.0, min=-500.0, max=500.0, step=0.1),
    Param("originY", "Ursprung Y", T_LENGTH, 0.0, min=-500.0, max=500.0, step=0.1),
    Param("rotation", "Drehung Rahmen", T_ANGLE, 0.0, min=-180.0, max=180.0, step=1.0),
    Param("patternAngle", "Drehung Muster", T_ANGLE, 0.0, min=-180.0, max=180.0, step=1.0,
          help="Dreht das Muster innerhalb des Rahmens."),
]

STYLE_PARAMS: List[Param] = [
    Param("mode", "Modus", T_CHOICE, "area", choices=[
        ("area", "Flächen (extrudierbar)"), ("lines", "Linien")],
        help="Flächen erzeugt geschlossene Profile, Linien nur Kurven."),
    Param("thickness", "Dicke (Steg)", T_LENGTH, 0.08, min=0.005, max=5.0, step=0.005,
          visible_if={"mode": ["area"]}),
    Param("fillTarget", "Füllung", T_CHOICE, "webs", choices=[
        ("webs", "Stege"), ("cells", "Zellen")],
        visible_if={"mode": ["area"]},
        help="Stege = Wände zwischen den Zellen, Zellen = Zellflächen."),
    Param("clip", "Beschnitt", T_CHOICE, "cut", choices=[
        ("cut", "Am Rand beschneiden"), ("dropPartial", "Angeschnittene weglassen"),
        ("off", "Aus")]),
    Param("border", "Rahmen zeichnen", T_BOOL, True,
          help="Im Flächenmodus ist der Rahmen die Außenkontur der "
               "zusammenhängenden Fläche - ohne ihn bleiben die Stege einzelne "
               "Streifen und enden offen am Rand."),
    Param("borderWidth", "Rahmendicke", T_LENGTH, 0.15, min=0.0, max=20.0, step=0.01,
          visible_if={"mode": ["area"], "border": [True]},
          help="Breite des geschlossenen Rands, nach innen gemessen - das "
               "eingestellte Rahmenmaß bleibt also das Außenmaß. 0 = nur so "
               "breit wie ein halber Steg."),
]

TEXT_PARAMS: List[Param] = [
    Param("enabled", "Text-Ebene aktiv", T_BOOL, False),
    Param("text", "Text", T_STRING, "PatternCreator", visible_if={"enabled": [True]}),
    Param("font", "Schriftart", T_STRING, "Arial", visible_if={"enabled": [True]}),
    Param("height", "Schrifthöhe", T_LENGTH, 1.0, min=0.05, max=50.0, step=0.05,
          visible_if={"enabled": [True]}),
    Param("x", "Position X", T_LENGTH, -2.0, min=-500.0, max=500.0, step=0.1,
          visible_if={"enabled": [True]}),
    Param("y", "Position Y", T_LENGTH, -0.5, min=-500.0, max=500.0, step=0.1,
          visible_if={"enabled": [True]}),
    Param("angle", "Winkel", T_ANGLE, 0.0, min=-180.0, max=180.0, step=1.0,
          visible_if={"enabled": [True]}),
    Param("knockout", "Muster ausstanzen", T_BOOL, True, visible_if={"enabled": [True]}),
    Param("knockoutMargin", "Stanz-Rand", T_LENGTH, 0.1, min=0.0, max=10.0, step=0.05,
          visible_if={"enabled": [True]}),
]

EXTRUDE_PARAMS: List[Param] = [
    Param("enabled", "Direkt extrudieren", T_BOOL, False),
    Param("depth", "Tiefe", T_LENGTH, 0.3, min=0.01, max=100.0, step=0.05,
          visible_if={"enabled": [True]}),
    Param("direction", "Richtung", T_CHOICE, "positive", choices=[
        ("positive", "Nach oben"), ("negative", "Nach unten"), ("symmetric", "Symmetrisch")],
        visible_if={"enabled": [True]}),
    Param("operation", "Vorgang", T_CHOICE, "new", choices=[
        ("new", "Neuer Körper"), ("join", "Verbinden"), ("cut", "Ausschneiden")],
        visible_if={"enabled": [True]}),
]

SEED_PARAM = Param("seed", "Seed", T_INT, 42, min=0, max=999999, step=1,
                   help="Gleicher Seed = gleiches Muster.")


# ------------------------------------------------------------- Standardwerte

def _defaults(params: Sequence[Param]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for p in params:
        out.setdefault(p.key, copy.deepcopy(p.default))
    return out


def default_text_layer() -> dict:
    return _defaults(TEXT_PARAMS)


def default_doc(pattern_type: str = "grid") -> dict:
    from generators import get_generator, default_params      # spaeter Import (Zyklus)
    get_generator(pattern_type)
    return {
        "version": DOC_VERSION,
        "container": _defaults(CONTAINER_PARAMS),
        "placement": _defaults(PLACEMENT_PARAMS),
        "pattern": {"type": pattern_type, "params": default_params(pattern_type)},
        "style": _defaults(STYLE_PARAMS),
        "textLayers": [default_text_layer()],
        "extrude": _defaults(EXTRUDE_PARAMS),
        "seed": SEED_PARAM.default,
    }


# -------------------------------------------------------------- Validierung

class ValidationError(Exception):
    def __init__(self, errors: Dict[str, str]):
        super().__init__("; ".join("%s: %s" % kv for kv in errors.items()))
        self.errors = errors


def _coerce(param: Param, value: Any, path: str, errors: Dict[str, str]) -> Any:
    if param.type == T_BOOL:
        return bool(value)
    if param.type == T_STRING:
        return "" if value is None else str(value)
    if param.type == T_CHOICE:
        allowed = [c[0] for c in (param.choices or [])]
        if value not in allowed:
            errors[path] = "Ungültige Auswahl „%s“ (erlaubt: %s)." % (
                value, ", ".join(allowed))
            return param.default
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        errors[path] = "„%s“ ist keine Zahl." % (value,)
        return param.default
    if num != num or num in (float("inf"), float("-inf")):
        errors[path] = "Wert muss eine endliche Zahl sein."
        return param.default
    if param.type == T_INT:
        num = int(round(num))
    if param.min is not None and num < param.min - 1e-9:
        errors[path] = "%s muss %s liegen." % (param.label, param.range_text())
        return param.default
    if param.max is not None and num > param.max + 1e-9:
        errors[path] = "%s muss %s liegen." % (param.label, param.range_text())
        return param.default
    return num


def _visible(param: Param, section: Dict[str, Any]) -> bool:
    if not param.visible_if:
        return True
    for key, allowed in param.visible_if.items():
        if section.get(key) not in allowed:
            return False
    return True


def _apply_section(params: Sequence[Param], raw: Any, prefix: str,
                   errors: Dict[str, str]) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    out = _defaults(params)
    # Auswahlfelder zuerst, damit ``visible_if`` korrekt greift
    ordered = [p for p in params if p.type in (T_CHOICE, T_BOOL)] + \
              [p for p in params if p.type not in (T_CHOICE, T_BOOL)]
    for p in ordered:
        if p.key in raw:
            out[p.key] = _coerce(p, raw[p.key], "%s.%s" % (prefix, p.key), errors)
    return out


def parse(raw: Any) -> Tuple[dict, Dict[str, str]]:
    """Rohdaten (aus dem Editor oder aus Fusion-Attributen) in ein gueltiges Doc.

    Liefert ``(doc, errors)``. ``doc`` ist immer benutzbar (fehlerhafte Felder
    fallen auf ihren Standardwert zurueck), ``errors`` bildet Feldpfad -> Klartext.
    """
    from generators import get_generator, params_for, default_params

    errors: Dict[str, str] = {}
    raw = raw if isinstance(raw, dict) else {}

    ptype = (raw.get("pattern") or {}).get("type", "grid")
    try:
        get_generator(ptype)
    except KeyError:
        errors["pattern.type"] = "Unbekannter Mustertyp „%s“." % ptype
        ptype = "grid"

    doc: Dict[str, Any] = {
        "version": DOC_VERSION,
        "container": _apply_section(CONTAINER_PARAMS, raw.get("container"), "container", errors),
        "placement": _apply_section(PLACEMENT_PARAMS, raw.get("placement"), "placement", errors),
        "style": _apply_section(STYLE_PARAMS, raw.get("style"), "style", errors),
        "extrude": _apply_section(EXTRUDE_PARAMS, raw.get("extrude"), "extrude", errors),
    }

    pparams = _apply_section(params_for(ptype), (raw.get("pattern") or {}).get("params"),
                             "pattern.params", errors)
    unknown = default_params(ptype)
    unknown.update(pparams)
    doc["pattern"] = {"type": ptype, "params": unknown}

    layers_raw = raw.get("textLayers")
    if layers_raw is None and isinstance(raw.get("textLayer"), dict):
        layers_raw = [raw["textLayer"]]           # Altformat aus fruehen Dokumenten
    if not isinstance(layers_raw, list) or not layers_raw:
        layers_raw = [{}]
    doc["textLayers"] = [
        _apply_section(TEXT_PARAMS, l, "textLayers.%d" % i, errors)
        for i, l in enumerate(layers_raw)
    ]

    doc["seed"] = _coerce(SEED_PARAM, raw.get("seed", SEED_PARAM.default), "seed", errors)

    # Querbezuege
    c = doc["container"]
    if c["shape"] in ("rect", "square"):
        w = c["width"]
        h = w if c["shape"] == "square" else c["height"]
        if c["cornerRadius"] > min(w, h) / 2.0 + 1e-9:
            errors["container.cornerRadius"] = (
                "Eckenradius darf höchstens %s mm betragen (halbe kleinste Kante)."
                % _fmt(min(w, h) / 2.0 * 10))
            c["cornerRadius"] = min(w, h) / 2.0
    return doc, errors


def validate(raw: Any) -> Dict[str, str]:
    return parse(raw)[1]


def parse_strict(raw: Any) -> dict:
    doc, errors = parse(raw)
    if errors:
        raise ValidationError(errors)
    return doc


# ------------------------------------------------------------ Serialisierung

def serialize(doc: dict) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def deserialize(text: str) -> dict:
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        raw = {}
    return parse(raw)[0]


def schema() -> dict:
    """Vollstaendiges UI-Schema fuer den Editor (einmalig beim Start gesendet)."""
    from generators import registry_schema
    return {
        "version": DOC_VERSION,
        "container": [p.to_dict() for p in CONTAINER_PARAMS],
        "placement": [p.to_dict() for p in PLACEMENT_PARAMS],
        "style": [p.to_dict() for p in STYLE_PARAMS],
        "text": [p.to_dict() for p in TEXT_PARAMS],
        "extrude": [p.to_dict() for p in EXTRUDE_PARAMS],
        "seed": SEED_PARAM.to_dict(),
        "patterns": registry_schema(),
    }
