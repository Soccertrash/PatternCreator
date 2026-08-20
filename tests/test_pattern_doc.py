"""PatternDoc: Standardwerte, Validierung, Serialisierung."""

import json

import pytest

from core import pattern_doc as pd


def test_default_doc_has_all_sections():
    doc = pd.default_doc("honeycomb")
    for key in ("version", "container", "placement", "pattern", "style",
                "textLayers", "extrude", "seed"):
        assert key in doc
    assert doc["pattern"]["type"] == "honeycomb"
    assert doc["pattern"]["params"]["cellSize"] > 0


def test_roundtrip_is_stable():
    doc = pd.default_doc("voronoi")
    again = pd.deserialize(pd.serialize(doc))
    assert again == doc
    # zweiter Durchlauf ändert nichts mehr
    assert pd.deserialize(pd.serialize(again)) == again


def test_text_layers_is_a_list_even_for_legacy_documents():
    legacy = {"pattern": {"type": "grid"},
              "textLayer": {"enabled": True, "text": "alt", "height": 0.5}}
    doc, errors = pd.parse(legacy)
    assert errors == {}
    assert isinstance(doc["textLayers"], list)
    assert doc["textLayers"][0]["text"] == "alt"


def test_out_of_range_value_reports_field_and_range_in_mm():
    raw = pd.default_doc("honeycomb")
    raw["pattern"]["params"]["cellSize"] = 999.0
    doc, errors = pd.parse(raw)
    assert "pattern.params.cellSize" in errors
    message = errors["pattern.params.cellSize"]
    assert "Zellweite" in message
    assert "mm" in message
    # Ungültiger Wert fällt auf den Standardwert zurück -> Doc bleibt benutzbar
    assert doc["pattern"]["params"]["cellSize"] == 0.8


def test_zero_size_container_is_rejected():
    raw = pd.default_doc("grid")
    raw["container"]["width"] = 0.0
    doc, errors = pd.parse(raw)
    assert "container.width" in errors
    assert doc["container"]["width"] > 0


def test_zero_cell_size_is_rejected():
    raw = pd.default_doc("honeycomb")
    raw["pattern"]["params"]["cellSize"] = 0.0
    _doc, errors = pd.parse(raw)
    assert "pattern.params.cellSize" in errors


def test_unknown_pattern_falls_back_to_grid():
    doc, errors = pd.parse({"pattern": {"type": "gibtsnicht"}})
    assert "pattern.type" in errors
    assert doc["pattern"]["type"] == "grid"


def test_corner_radius_is_capped_to_half_the_shorter_edge():
    raw = pd.default_doc("grid")
    raw["container"].update({"shape": "rect", "width": 10.0, "height": 4.0,
                             "cornerRadius": 3.0})
    doc, errors = pd.parse(raw)
    assert "container.cornerRadius" in errors
    assert doc["container"]["cornerRadius"] == pytest.approx(2.0)


def test_length_params_are_displayed_in_millimetres():
    param = pd.Param("thickness", "Dicke", pd.T_LENGTH, 0.08, min=0.1, max=10.0)
    # 1,0 cm im Doc entspricht 10 mm im Editor
    assert param.display(1.0) == pytest.approx(10.0)
    assert param.unit() == "mm"
    assert "1 mm" in param.range_text() and "100 mm" in param.range_text()


def test_schema_is_json_serialisable_and_lists_all_patterns():
    schema = pd.schema()
    json.dumps(schema)                     # darf nicht werfen
    assert len(schema["patterns"]) == 16
    for entry in schema["patterns"]:
        assert entry["label"] and entry["icon"] and entry["params"] is not None
        assert entry["fillTargets"]


def test_parse_strict_raises_with_error_map():
    raw = pd.default_doc("grid")
    raw["style"]["thickness"] = -5
    with pytest.raises(pd.ValidationError) as exc:
        pd.parse_strict(raw)
    assert "style.thickness" in exc.value.errors
