"""Befehl „Muster bearbeiten“ - bestehende Muster-Skizze erneut öffnen."""

from __future__ import annotations

import traceback
from typing import Any, List

import adsk.core
import adsk.fusion

from fusion import storage

from . import palette_bridge

CMD_ID = "PatternCreatorEditCmd"
CMD_NAME = "Muster bearbeiten"
CMD_TOOLTIP = ("Öffnet eine bestehende Muster-Skizze mit ihren gespeicherten Werten "
               "im Editor. Beim Erzeugen wird dieselbe Skizze neu aufgebaut.")

_handlers: List[Any] = []


class _SelectionFilter(adsk.core.SelectionEventHandler):
    """Nur Skizzen mit PatternCreator-Attribut zulassen."""

    def notify(self, args):
        try:
            event = adsk.core.SelectionEventArgs.cast(args)
            event.isSelectable = storage.is_pattern_sketch(event.selection.entity)
        except Exception:
            pass


class _CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
            inputs = cmd.commandInputs
            design = adsk.fusion.Design.cast(app.activeProduct)
            sketches = storage.find_pattern_sketches(design) if design else []

            if not sketches:
                inputs.addTextBoxCommandInput(
                    "empty", "", "In diesem Dokument gibt es noch keine "
                                 "PatternCreator-Skizze.", 3, True)
                return

            drop = inputs.addDropDownCommandInput(
                "sketchList", "Muster-Skizze",
                adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, (label, _sk) in enumerate(sketches):
                drop.listItems.add(label, i == 0)

            sel = inputs.addSelectionInput("sketchSel", "…oder im Modell wählen",
                                           "Muster-Skizze anklicken")
            sel.addSelectionFilter("Sketches")
            sel.setSelectionLimits(0, 1)

            _CACHE["sketches"] = sketches

            sel_filter = _SelectionFilter()
            cmd.selectionEvent.add(sel_filter)
            _handlers.append(sel_filter)
            execute = _ExecuteHandler()
            cmd.execute.add(execute)
            _handlers.append(execute)
        except Exception:
            ui.messageBox("Fehler beim Öffnen von „%s“:\n%s"
                          % (CMD_NAME, traceback.format_exc()))


_CACHE: dict = {"sketches": []}


class _ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            cmd = adsk.core.CommandEventArgs.cast(args).command
            inputs = cmd.commandInputs
            sketch = None
            sel = inputs.itemById("sketchSel")
            if sel and sel.selectionCount > 0:
                sketch = adsk.fusion.Sketch.cast(sel.selection(0).entity)
            if sketch is None:
                drop = inputs.itemById("sketchList")
                sketches = _CACHE.get("sketches", [])
                if drop and sketches:
                    idx = drop.selectedItem.index if drop.selectedItem else 0
                    sketch = sketches[idx][1]
            if sketch is None:
                ui.messageBox("Keine Muster-Skizze ausgewählt.")
                return
            doc = storage.load(sketch)
            if doc is None:
                ui.messageBox("Diese Skizze enthält keine PatternCreator-Daten.")
                return
            palette_bridge.open_editor(ui, "edit", doc, plane=None, sketch=sketch)
        except Exception:
            ui.messageBox("Fehler beim Laden des Musters:\n%s" % traceback.format_exc())


def register(ui: "adsk.core.UserInterface") -> "adsk.core.CommandDefinition":
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_TOOLTIP, "resources/edit")
    handler = _CreatedHandler()
    cmd_def.commandCreated.add(handler)
    _handlers.append(handler)
    return cmd_def


def unregister(ui: "adsk.core.UserInterface") -> None:
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()
    _handlers.clear()
    _CACHE["sketches"] = []
