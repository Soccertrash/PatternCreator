"""PatternDoc: Standardwerte, Validierung, Serialisierung."""

import json

import pytest

from core import pattern_doc as pd


def test_default_doc_has_all_sections():
    doc = pd.default_doc("honeycomb")
    for key in ("version", "container", "placement", "pattern", "style",
                "textLayers", "seed"):
        assert key in doc
    # Das Add-in zeichnet nur Skizzen; extrudiert wird in Fusion selbst.
    assert "extrude" not in doc
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


def test_legacy_extrude_section_is_dropped_without_error():
    """Skizzen aus der Zeit der integrierten Extrusion müssen weiter laden."""
    legacy = pd.default_doc("grid")
    legacy["extrude"] = {"enabled": True, "depth": 0.3, "direction": "positive",
                         "operation": "new"}
    doc, errors = pd.parse(legacy)
    assert errors == {}
    assert "extrude" not in doc


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
    assert len(schema["patterns"]) == 9
    for entry in schema["patterns"]:
        assert entry["label"] and entry["icon"] and entry["params"] is not None
        assert entry["fillTargets"]


def test_parse_strict_raises_with_error_map():
    raw = pd.default_doc("grid")
    raw["style"]["thickness"] = -5
    with pytest.raises(pd.ValidationError) as exc:
        pd.parse_strict(raw)
    assert "style.thickness" in exc.value.errors


# ------------------------------------------------------------ Eigener Rahmen

L_FRAME = [[0.0, 0.0], [6.0, 0.0], [6.0, 2.0], [2.0, 2.0], [2.0, 6.0], [0.0, 6.0]]


def custom_doc():
    raw = pd.default_doc("grid")
    raw["container"].update(shape="custom", customPoints=[list(p) for p in L_FRAME],
                            customSource={"kind": "profile",
                                          "label": "Skizze1 / Profil 2",
                                          "token": "abc123"})
    return raw


def test_custom_shape_is_offered_in_the_schema():
    shape = next(p for p in pd.schema()["container"] if p["key"] == "shape")
    assert "custom" in [c["value"] for c in shape["choices"]]


def test_custom_frame_survives_a_roundtrip():
    doc, errors = pd.parse(custom_doc())
    assert errors == {}
    assert doc["container"]["shape"] == "custom"
    assert doc["container"]["customPoints"] == L_FRAME
    assert doc["container"]["customSource"]["token"] == "abc123"
    assert pd.deserialize(pd.serialize(doc)) == doc


def test_custom_points_are_normalised_on_parse():
    """Schließpunkt, Dublette und Uhrzeigersinn kommen aus Fusion vor."""
    raw = custom_doc()
    raw["container"]["customPoints"] = [[0, 0], [0, 4], [0, 4], [4, 4], [4, 0], [0, 0]]
    doc, errors = pd.parse(raw)
    assert errors == {}
    pts = doc["container"]["customPoints"]
    assert len(pts) == 4
    from core.geom import polygon_area
    assert polygon_area([tuple(p) for p in pts]) > 0        # gegen den Uhrzeigersinn


@pytest.mark.parametrize("points", [
    [[0, 0], [1, 0]],                          # zu wenige Punkte
    [[0, 0], [1, 0], [2, 0]],                  # keine Fläche
    [[0, 0], [1, 0], [1, "x"]],                # keine Zahlen
])
def test_invalid_custom_points_report_a_field_error_and_fall_back(points):
    raw = custom_doc()
    raw["container"]["customPoints"] = points
    doc, errors = pd.parse(raw)
    assert "container.customPoints" in errors
    assert doc["container"]["shape"] == "rect"


def test_custom_shape_without_points_falls_back_to_rect():
    raw = pd.default_doc("grid")
    raw["container"]["shape"] = "custom"
    doc, errors = pd.parse(raw)
    assert "container.customPoints" in errors
    assert doc["container"]["shape"] == "rect"


def test_documents_without_the_new_fields_still_load():
    doc, errors = pd.parse(pd.default_doc("grid"))
    assert errors == {}
    assert "customPoints" not in doc["container"]
    assert "customSource" not in doc["container"]


def test_default_doc_stays_a_rectangle():
    assert pd.default_doc("grid")["container"]["shape"] == "rect"


def test_custom_points_are_kept_for_other_shapes():
    """Formwechsel im Editor darf die eingelesene Kontur nicht wegwerfen."""
    raw = custom_doc()
    raw["container"]["shape"] = "circle"
    doc, errors = pd.parse(raw)
    assert errors == {}
    assert doc["container"]["customPoints"] == L_FRAME


def test_apply_custom_frame_centres_the_contour_and_keeps_its_position():
    """Der Rahmen liegt lokal um die Bounding-Box-Mitte, die Lage trägt die
    Platzierung - so bleibt er deckungsgleich auf seiner Quelle."""
    doc = pd.default_doc("grid")
    pd.apply_custom_frame(doc, [(2, 1), (8, 1), (8, 5), (2, 5)],
                          {"kind": "face", "label": "Körper1 / Fläche 3",
                           "token": "tk"})
    assert doc["container"]["shape"] == "custom"
    assert doc["container"]["customPoints"] == [[-3.0, -2.0], [3.0, -2.0],
                                                [3.0, 2.0], [-3.0, 2.0]]
    assert doc["placement"]["originX"] == pytest.approx(5.0)
    assert doc["placement"]["originY"] == pytest.approx(3.0)
    assert doc["placement"]["rotation"] == 0.0
    assert doc["container"]["customSource"]["kind"] == "face"


def test_apply_custom_frame_result_parses_without_errors():
    doc = pd.default_doc("grid")
    pd.apply_custom_frame(doc, [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)])
    parsed, errors = pd.parse(doc)
    assert errors == {}
    assert parsed["container"]["shape"] == "custom"


def test_apply_custom_frame_rejects_a_degenerate_contour():
    with pytest.raises(ValueError):
        pd.apply_custom_frame(pd.default_doc("grid"), [(0, 0), (1, 0), (2, 0)])
