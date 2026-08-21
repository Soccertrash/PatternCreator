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
import math
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
        ("ellipse", "Ellipse"), ("polygon", "Vieleck"),
        ("custom", "Eigener Rahmen")],
        help="Rahmenform, in die das Muster eingepasst wird. „Eigener Rahmen“ "
             "übernimmt die Außenkontur eines Skizzenprofils oder einer ebenen "
             "Fläche aus Fusion."),
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

#: Schraffur-Detailfelder erscheinen nur, wenn die Schraffur aktiv sein kann
HATCH_ON = {"mode": ["area"], "fillTarget": ["webs"], "hatch": [True]}

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

    # -- Praegung: nur sinnvoll, wenn das Muster auf einer Mantelflaeche liegt.
    # Dass eine Mantelflaeche gewaehlt ist, kann ``visible_if`` nicht ausdruecken
    # (es sieht nur den Stil-Abschnitt) - der Editor blendet die Gruppe deshalb
    # zusaetzlich nach ``doc.development`` aus.
    Param("embossOn", "Auf die Fläche prägen", T_BOOL, False,
          visible_if={"mode": ["area"], "fillTarget": ["webs"], "border": [True]},
          help="Legt das Muster mit „Prägen“ auf die Mantelfläche statt es nur "
               "als Skizze auf der Tangentialebene zu hinterlassen."),
    Param("embossDepth", "Prägetiefe", T_LENGTH, 0.1, min=-5.0, max=5.0, step=0.01,
          visible_if={"mode": ["area"], "fillTarget": ["webs"], "border": [True],
                      "embossOn": [True]},
          help="Positiv steht das Muster von der Fläche ab, negativ ist es "
               "eingesenkt."),

    # -- Schraffur: fuellt die freien Zellflaechen mit zusaetzlichen Stegen.
    # Nur im Flaechenmodus mit Fuellung "Stege" sinnvoll - nur dort sind die
    # Zellen ueberhaupt offen. Geometrie siehe ``core/hatch.py``.
    Param("hatch", "Schraffur in Zellen", T_BOOL, False,
          visible_if={"mode": ["area"], "fillTarget": ["webs"]},
          help="Zieht zus\u00e4tzliche Stege in die offenen Zellfl\u00e4chen. Eigene "
               "Dicke, deshalb auch als feine F\u00fcllung in einem groben "
               "Stegnetz verwendbar."),
    Param("hatchType", "Schraffurart", T_CHOICE, "parallel", choices=[
        ("parallel", "Parallel"), ("cross", "Kreuz")],
        visible_if=HATCH_ON,
        help="Kreuz legt ein zweites Linienraster dar\u00fcber."),
    Param("hatchSpacing", "Schraffur-Abstand", T_LENGTH, 0.4, min=0.02, max=20.0,
          step=0.01, visible_if=HATCH_ON,
          help="Abstand von Strichmitte zu Strichmitte."),
    Param("hatchThickness", "Schraffur-Dicke", T_LENGTH, 0.06, min=0.005, max=5.0,
          step=0.005, visible_if=HATCH_ON,
          help="Strichbreite der Schraffur - unabh\u00e4ngig von der Stegdicke."),
    Param("hatchAim", "Schraffur-Richtung", T_CHOICE, "fixed", choices=[
        ("fixed", "Fester Winkel"), ("random", "Zuf\u00e4llig je Zelle"),
        ("center", "Zum Mittelpunkt")],
        visible_if=HATCH_ON,
        help="Zuf\u00e4llig streut den Winkel je Zelle (aus dem Seed); Mittelpunkt "
             "richtet jede Zelle auf einen gemeinsamen Punkt aus."),
    Param("hatchAngle", "Schraffur-Winkel", T_ANGLE, 45.0, min=-180.0, max=180.0,
          step=1.0, visible_if=dict(HATCH_ON, hatchAim=["fixed", "random"]),
          help="Bei \u201eZuf\u00e4llig je Zelle\u201c der Grundwinkel, um den gestreut wird."),
    Param("hatchJitter", "Winkel-Streuung", T_ANGLE, 90.0, min=0.0, max=180.0,
          step=1.0, visible_if=dict(HATCH_ON, hatchAim=["random"]),
          help="Gr\u00f6\u00dfte Abweichung vom Grundwinkel. 180\u00b0 = v\u00f6llig zuf\u00e4llig."),
    Param("hatchCenterX", "Mittelpunkt X", T_LENGTH, 0.0, min=-500.0, max=500.0,
          step=0.1, visible_if=dict(HATCH_ON, hatchAim=["center"]),
          help="Zielpunkt aller Schraffuren, bezogen auf die Rahmenmitte (0/0)."),
    Param("hatchCenterY", "Mittelpunkt Y", T_LENGTH, 0.0, min=-500.0, max=500.0,
          step=0.1, visible_if=dict(HATCH_ON, hatchAim=["center"])),
    Param("hatchCrossAngle", "Kreuzungswinkel", T_ANGLE, 90.0, min=10.0, max=170.0,
          step=1.0, visible_if=dict(HATCH_ON, hatchType=["cross"]),
          help="Winkel des zweiten Linienrasters gegen\u00fcber dem ersten."),
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
        "development": None,
        "textLayers": [default_text_layer()],
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
    doc["development"] = _apply_development(raw.get("development"), errors)

    # Eigener Rahmen: Punktliste und Quelle liegen neben den Formularfeldern,
    # weil sie kein Formular haben - der Editor zeigt sie als Infozeile.
    _apply_custom_frame(doc["container"], raw.get("container"), errors)

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


#: Groesster Betrag des Nahtwinkels (Grad).
MAX_SEAM_ANGLE = 180.0


def _apply_development(raw: Any, errors: Dict[str, str]) -> Optional[dict]:
    """``development`` uebernehmen und pruefen. ``None`` = ebener Rahmen.

    Der Abschnitt hat keine Formularfelder: er kommt komplett aus der in Fusion
    gewaehlten Flaeche (``fusion/surface_reader.py``). Geprueft wird er trotzdem
    hier - ein Doc aus einer alten Version oder aus einer Datei darf die
    Pipeline nicht zum Absturz bringen.
    """
    from .containers import MAX_FRAME_POINTS
    from .development import development_from_doc

    if not isinstance(raw, dict) or not raw:
        return None
    dev = development_from_doc(raw)
    if dev is None:
        errors["development"] = "Die gespeicherte Mantelfläche ist unbrauchbar."
        return None

    try:
        seam_angle = float(raw.get("seamAngle", 0.0))
    except (TypeError, ValueError):
        seam_angle = 0.0
    if not -MAX_SEAM_ANGLE <= seam_angle <= MAX_SEAM_ANGLE:
        errors["development.seamAngle"] = (
            "Der Nahtwinkel muss zwischen -180° und 180° liegen.")
        seam_angle = 0.0

    outline: List[List[float]] = []
    raw_outline = raw.get("outline")
    if isinstance(raw_outline, (list, tuple)):
        if len(raw_outline) > MAX_FRAME_POINTS:
            errors["development.outline"] = (
                "Die Flächenkontur hat mehr als %d Punkte." % MAX_FRAME_POINTS)
        else:
            try:
                outline = [[float(a), float(b)] for a, b in raw_outline]
            except (TypeError, ValueError):
                errors["development.outline"] = "Die Flächenkontur ist unbrauchbar."
                outline = []

    # Lage der Flaechenmitte auf der Achse (cm). Die Praegung braucht sie, um
    # die Tangentialebene an der richtigen Stelle anzulegen; gerechnet wird sie
    # beim Einlesen, damit hier nichts von der Flaeche uebrig bleiben muss.
    try:
        axis_middle = float(raw.get("axisMiddle", 0.0))
    except (TypeError, ValueError):
        axis_middle = 0.0
    if not math.isfinite(axis_middle):
        axis_middle = 0.0

    # Was Fusion beim letzten Erzeugen angelegt hat. Ohne diese Tokens wuerde
    # ein Re-Edit eine zweite Tangentialebene anlegen und die alte Praegung
    # stehen lassen.
    tokens = raw.get("embossTokens")
    tokens = [str(t) for t in tokens] if isinstance(tokens, (list, tuple)) else []

    source = raw.get("source")
    source = source if isinstance(source, dict) else {}
    return {
        "kind": dev.kind,
        "radius": dev.radius,
        "halfAngle": dev.half_angle,
        "length": dev.length,
        "periodic": dev.periodic,
        "seamAngle": seam_angle,
        "outline": outline,
        "axisMiddle": axis_middle,
        "planeToken": str(raw.get("planeToken", "")),
        "pointToken": str(raw.get("pointToken", "")),
        "embossTokens": tokens,
        "source": {"label": str(source.get("label", "")),
                   "token": str(source.get("token", ""))},
    }


def _apply_custom_frame(container: Dict[str, Any], raw: Any,
                        errors: Dict[str, str]) -> None:
    """``customPoints`` / ``customSource`` uebernehmen und pruefen.

    Die Punkte werden dabei normalisiert (Duplikate weg, gegen den
    Uhrzeigersinn, Selbstschnitte weg, auf die Optimierer-Toleranz
    vereinfacht) - siehe ``containers.normalize_frame``. Ein ``shape ==
    "custom"`` ohne brauchbare Kontur ist ein Feldfehler; das Doc faellt dann
    auf ``rect`` zurueck und bleibt benutzbar.
    """
    from .containers import normalize_frame

    raw = raw if isinstance(raw, dict) else {}
    points = raw.get("customPoints")
    if points:
        try:
            container["customPoints"] = [[x, y] for x, y in normalize_frame(points)]
        except (ValueError, TypeError) as exc:
            errors["container.customPoints"] = str(exc)
    source = raw.get("customSource")
    if isinstance(source, dict):
        container["customSource"] = {
            "kind": str(source.get("kind", "")),
            "label": str(source.get("label", "")),
            "token": str(source.get("token", "")),
        }
    if container.get("shape") == "custom" and not container.get("customPoints"):
        errors.setdefault("container.customPoints",
                          "Für „Eigener Rahmen“ fehlt eine gültige Kontur.")
        container["shape"] = "rect"


def apply_custom_frame(doc: dict, points: Sequence[Sequence[float]],
                       source: Optional[dict] = None) -> dict:
    """Eine eingelesene Kontur als eigenen Rahmen ins Doc setzen.

    ``points`` sind **Skizzenkoordinaten** (cm). Im Doc steht die Kontur lokal um
    den Mittelpunkt ihrer Bounding-Box; die Lage traegt die Platzierung. So
    bleibt die bestehende Platzierungslogik unveraendert und der Rahmen liegt
    exakt auf seiner Quelle. Die Drehung wird zurueckgesetzt - der Rahmen kommt
    ja schon in der richtigen Lage.

    Wirft ``ValueError``, wenn die Kontur unbrauchbar ist.
    """
    from .containers import normalize_frame

    pts = normalize_frame(points)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    container = doc.setdefault("container", {})
    container["shape"] = "custom"
    container["customPoints"] = [[x - cx, y - cy] for x, y in pts]
    if source is not None:
        container["customSource"] = {
            "kind": str(source.get("kind", "")),
            "label": str(source.get("label", "")),
            "token": str(source.get("token", "")),
        }
    placement = doc.setdefault("placement", {})
    placement["originX"] = cx
    placement["originY"] = cy
    placement["rotation"] = 0.0
    return doc


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
        "seed": SEED_PARAM.to_dict(),
        "patterns": registry_schema(),
    }
