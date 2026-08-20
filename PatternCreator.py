"""PatternCreator - Fusion-360-Add-In für parametrische 2D-Muster.

``run()`` legt die beiden Buttons „Muster erstellen“ und „Muster bearbeiten“ an,
``stop()`` entfernt Buttons, CommandDefinitions **und** die Palette rückstandsfrei.
"""

from __future__ import annotations

import os
import sys
import traceback

import adsk.core
import adsk.fusion

# Add-In-Ordner in den Suchpfad, damit ``core``/``generators``/``fusion`` importierbar sind
_ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _ADDIN_DIR not in sys.path:
    sys.path.insert(0, _ADDIN_DIR)

from commands import create_command, edit_command, palette_bridge   # noqa: E402

PANEL_ID = "SolidCreatePanel"
CONTROL_IDS = (create_command.CMD_ID, edit_command.CMD_ID)

_app = None
_ui = None


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        # Reste einer vorherigen Sitzung entfernen (zweimal Laden ohne Duplikate)
        _remove_controls(_ui)

        create_def = create_command.register(_ui)
        edit_def = edit_command.register(_ui)
        palette_bridge.register_commit_command(_ui)

        panel = _ui.allToolbarPanels.itemById(PANEL_ID)
        if panel is None:
            panel = _ui.allToolbarPanels.itemById("SketchCreatePanel")
        if panel is not None:
            panel.controls.addCommand(create_def)
            panel.controls.addCommand(edit_def)
    except Exception:
        if _ui:
            _ui.messageBox("PatternCreator konnte nicht gestartet werden:\n%s"
                           % traceback.format_exc())


def stop(context):
    global _app, _ui
    try:
        ui = _ui or adsk.core.Application.get().userInterface
        _remove_controls(ui)
        palette_bridge.destroy(ui)
        palette_bridge.unregister_commit_command(ui)
        create_command.unregister(ui)
        edit_command.unregister(ui)
    except Exception:
        if _ui:
            _ui.messageBox("PatternCreator konnte nicht sauber beendet werden:\n%s"
                           % traceback.format_exc())
    finally:
        _app = None
        _ui = None


def _remove_controls(ui: "adsk.core.UserInterface") -> None:
    for panel_id in (PANEL_ID, "SketchCreatePanel"):
        panel = ui.allToolbarPanels.itemById(panel_id)
        if panel is None:
            continue
        for control_id in CONTROL_IDS:
            control = panel.controls.itemById(control_id)
            if control:
                control.deleteMe()
