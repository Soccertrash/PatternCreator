"""Struktur-Zusicherungen: Trennung IR <-> Fusion, Determinismus, Projektlayout."""

import ast
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUSION_FREE = ("core", "generators", "text")


def python_files(*folders):
    for folder in folders:
        base = os.path.join(ROOT, folder)
        for dirpath, _dirnames, filenames in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def test_project_layout_matches_the_plan():
    for folder in ("commands", "core", "generators", "text", "fusion", "palette",
                   "resources", "tests"):
        assert os.path.isdir(os.path.join(ROOT, folder)), folder
    for name in ("PatternCreator.py", "PatternCreator.manifest", "README.md",
                 "PLAN.md", "CHECKLIST.md"):
        assert os.path.isfile(os.path.join(ROOT, name)), name


def test_manifest_is_valid_json_for_an_addin():
    with open(os.path.join(ROOT, "PatternCreator.manifest"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["type"] == "addin"
    assert manifest["supportedOS"] == "windows|mac"
    assert manifest["id"]


def test_core_generators_and_text_never_import_adsk():
    for path in python_files(*FUSION_FREE):
        tree = ast.parse(read(path), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("adsk"), path
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("adsk"), path
    # ...und auch nicht ueber das ``fusion``-Paket
    for path in python_files(*FUSION_FREE):
        assert "import fusion" not in read(path), path


def test_no_global_random_seeding():
    """Nur ``random.Random(seed)``-Instanzen - sonst waeren Vorschau und Commit
    nicht reproduzierbar."""
    for path in python_files("core", "generators", "text", "commands", "fusion"):
        source = read(path)
        assert not re.search(r"\brandom\.seed\s*\(", source), path
        assert not re.search(r"\brandom\.random\s*\(\s*\)", source), path


def test_palette_has_no_external_resources():
    palette = os.path.join(ROOT, "palette")
    for name in os.listdir(palette):
        source = read(os.path.join(palette, name))
        assert "http://" not in source, name
        assert "https://" not in source, name
        assert "cdn." not in source, name


def test_generators_do_not_touch_editor_or_command_code():
    """Neues Muster = neue Datei + Registry-Eintrag, kein UI-Code."""
    forbidden = ("commands", "fusion", "palette")
    for path in python_files("generators"):
        tree = ast.parse(read(path), filename=path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert name.split(".")[0] not in forbidden, "%s -> %s" % (path, name)


def test_organic_family_shares_the_same_core():
    """Kiesel, Gewebe, Kaustik und Blattadern bauen auf ``organic_cells`` auf."""
    for name in ("pebbles", "tissue", "caustics", "leaf_veins", "voronoi"):
        source = read(os.path.join(ROOT, "generators", "%s.py" % name))
        assert "organic_cells" in source, name


def test_every_generator_module_has_exactly_one_registry_entry():
    import generators
    registry_source = read(os.path.join(ROOT, "generators", "__init__.py"))
    for cls in generators.GENERATOR_CLASSES:
        assert cls.__name__ in registry_source


def test_compute_deferred_is_reset_in_a_finally_block():
    source = read(os.path.join(ROOT, "fusion", "renderer.py"))
    tree = ast.parse(source)
    finallys = [n for n in ast.walk(tree) if isinstance(n, ast.Try) and n.finalbody]
    assert finallys, "isComputeDeferred muss in try/finally zurückgesetzt werden"
    assert any("isComputeDeferred" in ast.dump(ast.Module(body=t.finalbody,
                                                          type_ignores=[]))
               for t in finallys)


def test_readme_documents_both_platforms_and_limits():
    readme = read(os.path.join(ROOT, "README.md"))
    for needle in ("macOS", "Windows", "AddIns", "500", "pytest"):
        assert needle in readme, needle


def test_manifest_carries_a_usable_version():
    """Fusion zeigt diese Version im Add-Ins-Dialog - daran erkennt man, ob die
    neue Fassung geladen ist. Sie muss deshalb gueltiges Semver sein."""
    import json
    import re

    manifest = json.loads(read(os.path.join(ROOT, "PatternCreator.manifest")))
    assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"]), manifest["version"]
    assert manifest["type"] == "addin"
