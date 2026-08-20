"""Befehl „Muster erstellen“ - Ebene wählen, dann Editor-Palette öffnen."""

from __future__ import annotations

import traceback
from typing import Any, List

import adsk.core
import adsk.fusion

from core import pattern_doc

from . import palette_bridge

CMD_ID = "PatternCreatorCreateCmd"
CMD_NAME = "Muster erstellen"
CMD_TOOLTIP = ("Öffnet den Muster-Editor mit Live-Vorschau und erzeugt daraus "
               "eine parametrische Skizze.")

_handlers: List[Any] = []


class _CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
            inputs = cmd.commandInputs
            sel = inputs.addSelectionInput("planeSel", "Skizzenebene",
                                           "Ebene oder planare Fläche wählen "
                                           "(leer = XY-Ursprungsebene)")
            sel.addSelectionFilter("ConstructionPlanes")
            sel.addSelectionFilter("PlanarFaces")
            sel.setSelectionLimits(0, 1)
            inputs.addTextBoxCommandInput(
                "hint", "", "Nach OK öffnet sich der Muster-Editor.", 2, True)

            execute = _ExecuteHandler()
            cmd.execute.add(execute)
            _handlers.append(execute)
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                "Fehler beim Öffnen von „%s“:\n%s" % (CMD_NAME, traceback.format_exc()))


class _ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            cmd = adsk.core.CommandEventArgs.cast(args).command
            sel = cmd.commandInputs.itemById("planeSel")
            plane = sel.selection(0).entity if sel and sel.selectionCount > 0 else None
            doc = palette_bridge.SESSION.doc or pattern_doc.default_doc()
            palette_bridge.open_editor(ui, "create", pattern_doc.parse(doc)[0],
                                       plane=plane, sketch=None)
        except Exception:
            ui.messageBox("Fehler beim Starten des Editors:\n%s" % traceback.format_exc())


def register(ui: "adsk.core.UserInterface") -> "adsk.core.CommandDefinition":
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_TOOLTIP, "resources/create")
    handler = _CreatedHandler()
    cmd_def.commandCreated.add(handler)
    _handlers.append(handler)
    return cmd_def


def unregister(ui: "adsk.core.UserInterface") -> None:
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()
    _handlers.clear()
