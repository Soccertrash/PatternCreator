"""Befehl „Muster erstellen“ - Ziel wählen, dann Editor-Palette öffnen.

Ziel ist eine Konstruktionsebene, eine planare Fläche **oder** ein geschlossenes
Skizzenprofil. Bei Fläche und Profil wird deren Außenkontur auf Wunsch gleich
zum Rahmen des Musters (Kontrollkästchen, standardmäßig an).
"""

from __future__ import annotations

import traceback
from typing import Any, List

import adsk.core
import adsk.fusion

from core import pattern_doc
from fusion import frame_reader

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
            sel = inputs.addSelectionInput("planeSel", "Ebene, Fläche oder Profil",
                                           "Ebene, planare Fläche oder "
                                           "geschlossenes Skizzenprofil wählen "
                                           "(leer = XY-Ursprungsebene)")
            sel.addSelectionFilter("ConstructionPlanes")
            sel.addSelectionFilter("PlanarFaces")
            sel.addSelectionFilter("Profiles")
            sel.setSelectionLimits(0, 1)
            # Das Kaestchen startet **sichtbar** und wird erst ausgeblendet,
            # wenn die Auswahl eine reine Konstruktionsebene ist. Andersherum
            # (unsichtbar anlegen, spaeter einblenden) blieb es in Fusion
            # dauerhaft unsichtbar - gepruefte Beobachtung 2026-08-21, siehe
            # Context.md 15.5. Der Rueckfall ist damit die sichere Richtung:
            # schlimmstenfalls steht das Kaestchen da, wo es nichts bewirkt.
            frame = inputs.addBoolValueInput(
                "useAsFrame", "Kontur als Rahmen verwenden", True, "", True)
            frame.tooltip = ("Die Außenkontur der Fläche bzw. des Profils wird "
                             "zum Rahmen des Musters. Innenkonturen bleiben "
                             "unberücksichtigt. Bei einer Konstruktionsebene "
                             "gibt es keine Kontur - dann bleibt der bisherige "
                             "Rahmen.")
            inputs.addTextBoxCommandInput(
                "hint", "", "Nach OK öffnet sich der Muster-Editor.", 2, True)

            changed = _InputChangedHandler()
            cmd.inputChanged.add(changed)
            _handlers.append(changed)
            execute = _ExecuteHandler()
            cmd.execute.add(execute)
            _handlers.append(execute)
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                "Fehler beim Öffnen von „%s“:\n%s" % (CMD_NAME, traceback.format_exc()))


class _InputChangedHandler(adsk.core.InputChangedEventHandler):
    """Das Rahmen-Kästchen verschwindet nur bei einer reinen Ebene."""

    def notify(self, args):
        try:
            changed = adsk.core.InputChangedEventArgs.cast(args)
            if changed.input.id != "planeSel":
                return
            inputs = changed.inputs
            sel = inputs.itemById("planeSel")
            frame = inputs.itemById("useAsFrame")
            if sel is None or frame is None:
                return
            entity = sel.selection(0).entity if sel.selectionCount > 0 else None
            # Ohne Auswahl sichtbar lassen: das Kaestchen soll nie fehlen, wenn
            # es gebraucht wird.
            frame.isVisible = entity is None or frame_reader.is_supported(entity)
        except Exception:
            pass          # Sichtbarkeit ist Komfort, kein Grund zum Abbruch


class _ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            cmd = adsk.core.CommandEventArgs.cast(args).command
            inputs = cmd.commandInputs
            sel = inputs.itemById("planeSel")
            entity = sel.selection(0).entity if sel and sel.selectionCount > 0 else None
            use_frame = bool(inputs.itemById("useAsFrame").value)
            doc = pattern_doc.parse(palette_bridge.SESSION.doc
                                    or pattern_doc.default_doc())[0]
            plane, doc = _target_and_doc(ui, entity, use_frame, doc)
            palette_bridge.open_editor(ui, "create", doc, plane=plane, sketch=None)
        except Exception:
            ui.messageBox("Fehler beim Starten des Editors:\n%s" % traceback.format_exc())


def _target_and_doc(ui, entity, use_frame: bool, doc: dict):
    """Zielebene bestimmen und - wenn gewuenscht - die Kontur als Rahmen setzen.

    Misslingt das Einlesen, oeffnet der Editor trotzdem: mit der Zielebene und
    dem bisherigen Rahmen. Ein Klartext-Hinweis sagt, woran es lag.
    """
    if entity is None:
        return None, doc
    plane = entity
    try:
        plane = frame_reader.plane_of(entity)
    except Exception as exc:
        ui.messageBox("Die Ebene der Auswahl ließ sich nicht bestimmen:\n%s" % exc)
        return None, doc
    if not (use_frame and frame_reader.is_supported(entity)):
        return plane, doc
    try:
        snapshot = frame_reader.read_frame(entity, sketch=None)
        pattern_doc.apply_custom_frame(doc, snapshot.points, snapshot.source())
        parsed, errors = pattern_doc.parse(doc)
        if errors:
            raise ValueError("; ".join(errors.values()))
        return snapshot.plane, parsed
    except Exception as exc:
        ui.messageBox("Die Kontur konnte nicht als Rahmen übernommen werden:\n%s"
                      "\n\nDer Editor öffnet mit dem bisherigen Rahmen." % exc)
        return plane, doc


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
