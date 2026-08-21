"""Brücke zwischen Editor-Palette (HTML/JS) und Python.

Nachrichtenfluss:

* JS -> Python (``incomingFromHTML``): ``ready``, ``docChanged``, ``commit``,
  ``cancel``, ``pickFrame``, ``rereadFrame``
* Python -> JS (``sendInfoToHTML``): ``init``, ``preview``, ``busy``, ``done``,
  ``frame``

Jede Vorschau-Anfrage traegt eine ``requestId``; veraltete Antworten verwirft der
Editor. Alle Handler werden global referenziert (GC-Schutz).
"""

from __future__ import annotations

import copy
import json
import os
import traceback
from typing import Any, Dict, List, Optional

import adsk.core
import adsk.fusion

from core import build, pattern_doc
from fusion import frame_reader, renderer, storage

PALETTE_ID = "PatternCreatorEditorPalette"
COMMIT_CMD_ID = "PatternCreatorCommitCmd"
FRAME_CMD_ID = "PatternCreatorFrameCmd"

_handlers: List[Any] = []          # GC-Schutz: darf nie leer laufen


class Session:
    """Zustand des gerade offenen Editors."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.mode = "create"          # "create" | "edit"
        self.plane = None             # ConstructionPlane oder BRepFace
        self.sketch = None            # bestehende Muster-Skizze (edit)
        self.doc: Dict[str, Any] = pattern_doc.default_doc()
        self.pending: Optional[Dict[str, Any]] = None
        self.force = False            # Warnungen (Entity-Zahl) bereits bestaetigt
        self.frame_request: Optional[str] = None   # "pickFrame" | "rereadFrame"


SESSION = Session()


# ------------------------------------------------------------------ Palette

def _palette_url() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "palette", "editor.html")
    try:
        from pathlib import Path
        url = Path(path).as_uri()
    except Exception:
        url = "file://" + path.replace("\\", "/")
    # Fusion cacht Palette-HTML -> Version aus der Änderungszeit anhängen
    try:
        stamp = int(os.path.getmtime(path))
    except OSError:
        stamp = 0
    return "%s?v=%d" % (url, stamp)


def get_palette(ui: "adsk.core.UserInterface") -> "adsk.core.Palette":
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette is None:
        palette = ui.palettes.add(PALETTE_ID, "Muster-Editor", _palette_url(),
                                  True, True, True, 460, 760)
        palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        on_incoming = _IncomingHandler()
        palette.incomingFromHTML.add(on_incoming)
        _handlers.append(on_incoming)
        on_closed = _ClosedHandler()
        palette.closed.add(on_closed)
        _handlers.append(on_closed)
    return palette


def open_editor(ui: "adsk.core.UserInterface", mode: str, doc: Dict[str, Any],
                plane=None, sketch=None) -> None:
    SESSION.mode = mode
    SESSION.doc = doc
    SESSION.plane = plane
    SESSION.sketch = sketch
    SESSION.force = False
    palette = get_palette(ui)
    palette.isVisible = True
    _send(ui, "init", _init_payload())


def close_palette(ui: "adsk.core.UserInterface") -> None:
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.isVisible = False


def destroy(ui: "adsk.core.UserInterface") -> None:
    """Palette rueckstandsfrei entfernen (``stop()``)."""
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        try:
            palette.deleteMe()
        except Exception:
            pass
    _handlers.clear()


def _send(ui: "adsk.core.UserInterface", action: str, payload: Any) -> None:
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.sendInfoToHTML(action, json.dumps(payload, ensure_ascii=False))


def _init_payload() -> dict:
    return {
        "schema": pattern_doc.schema(),
        "doc": SESSION.doc,
        "mode": SESSION.mode,
        "target": _target_label(),
        "entityWarnLimit": build.ENTITY_WARN_LIMIT,
        "previewWarnLimit": build.PREVIEW_WARN_LIMIT,
    }


def _target_label() -> str:
    label = _plane_label()
    source = (SESSION.doc.get("container") or {}).get("customSource") or {}
    if SESSION.doc.get("container", {}).get("shape") == "custom" and source.get("label"):
        label += " · Rahmen: %s" % source["label"]
    return label


def _plane_label() -> str:
    if SESSION.mode == "edit" and SESSION.sketch is not None:
        return "Skizze: %s" % SESSION.sketch.name
    if SESSION.plane is not None:
        try:
            return "Ebene: %s" % SESSION.plane.name
        except Exception:
            return "Gewählte Fläche"
    return "Ebene: XY (Standard)"


# ---------------------------------------------------------------- Handler

class _IncomingHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            event = adsk.core.HTMLEventArgs.cast(args)
            action = event.action
            data = json.loads(event.data) if event.data else {}

            if action == "ready":
                _send(ui, "init", _init_payload())
            elif action == "docChanged":
                _handle_preview(ui, data)
            elif action == "commit":
                _handle_commit(ui, data)
            elif action in ("pickFrame", "rereadFrame"):
                _handle_frame(ui, action)
            elif action == "cancel":
                close_palette(ui)
            else:
                event.returnData = "unknown"
        except Exception:
            if ui:
                ui.messageBox("Fehler im Editor-Datenaustausch:\n%s"
                              % traceback.format_exc())


class _ClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def notify(self, args):
        SESSION.pending = None


def _handle_preview(ui: "adsk.core.UserInterface", data: dict) -> None:
    request_id = data.get("requestId", 0)
    doc, errors = pattern_doc.parse(data.get("doc"))
    payload: Dict[str, Any] = {"requestId": request_id, "errors": errors, "doc": doc}
    if errors:
        payload["scene"] = None
        _send(ui, "preview", payload)
        return
    SESSION.doc = doc
    try:
        scene = build.build_scene(doc)
    except Exception:
        payload["scene"] = None
        payload["errors"] = {"_global": "Muster konnte nicht erzeugt werden: %s"
                                        % traceback.format_exc(limit=1)}
        _send(ui, "preview", payload)
        return
    payload["scene"] = scene.to_dict()
    payload["entityEstimate"] = build.entity_estimate(scene)
    _send(ui, "preview", payload)


def _handle_commit(ui: "adsk.core.UserInterface", data: dict) -> None:
    doc, errors = pattern_doc.parse(data.get("doc"))
    if errors:
        _send(ui, "preview", {"requestId": data.get("requestId", 0),
                              "errors": errors, "scene": None})
        return
    SESSION.doc = doc
    SESSION.pending = doc
    SESSION.force = bool(data.get("force"))
    _send(ui, "busy", {"message": "Erzeuge Muster …"})
    cmd_def = ui.commandDefinitions.itemById(COMMIT_CMD_ID)
    if cmd_def is None:
        _send(ui, "done", {"ok": False, "message": "Commit-Befehl nicht gefunden."})
        return
    cmd_def.execute()


# --------------------------------------------------------------- Rahmen

def _handle_frame(ui: "adsk.core.UserInterface", action: str) -> None:
    """Rahmen einlesen - als Command, damit die Hilfsskizze in einer Transaktion
    entsteht und wieder verschwindet."""
    SESSION.frame_request = action
    cmd_def = ui.commandDefinitions.itemById(FRAME_CMD_ID)
    if cmd_def is None:
        _send(ui, "frame", {"ok": False,
                            "message": "Rahmen-Befehl nicht gefunden."})
        return
    cmd_def.execute()


def perform_frame(app, ui, request: str) -> Dict[str, Any]:
    """Auswahl bzw. gespeicherte Quelle einlesen und ins Doc uebernehmen."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise frame_reader.FrameError("Kein Konstruktionsdokument aktiv.")

    if request == "rereadFrame":
        source = (SESSION.doc.get("container") or {}).get("customSource") or {}
        entity = frame_reader.find_source(source.get("token", ""), design)
    else:
        entity = frame_reader.pick_from_selection(ui)

    # Im Edit-Modus ist die Skizze das Ziel: ``read_frame`` rechnet dann in
    # deren Koordinaten und lehnt eine Auswahl ab, die nicht in ihrer Ebene
    # liegt. Im Create-Modus darf die Ebene dagegen wechseln.
    sketch = SESSION.sketch if SESSION.mode == "edit" else None
    snapshot = frame_reader.read_frame(entity, sketch=sketch, design=design)

    doc = copy.deepcopy(SESSION.doc)
    pattern_doc.apply_custom_frame(doc, snapshot.points, snapshot.source())
    doc, errors = pattern_doc.parse(doc)
    if errors:
        raise frame_reader.FrameError("; ".join(errors.values()))
    SESSION.doc = doc
    if SESSION.mode != "edit":
        SESSION.plane = snapshot.plane
    return {
        "ok": True,
        "doc": doc,
        "target": _target_label(),
        "message": "Rahmen übernommen: %s (%d Punkte)."
                   % (snapshot.label, len(doc["container"]["customPoints"])),
    }


class _FrameCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
            cmd.isAutoExecute = True
            cmd.isExecutedWhenPreEmpted = False
            handler = _FrameExecuteHandler()
            cmd.execute.add(handler)
            _handlers.append(handler)
        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox("Rahmen-Befehl konnte nicht gestartet "
                                         "werden:\n%s" % traceback.format_exc())


class _FrameExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        request = SESSION.frame_request
        if request is None:
            return
        SESSION.frame_request = None
        try:
            _send(ui, "frame", perform_frame(app, ui, request))
        except frame_reader.FrameError as err:
            _send(ui, "frame", {"ok": False, "message": str(err)})
        except Exception:
            _send(ui, "frame", {"ok": False,
                                "message": "Der Rahmen konnte nicht eingelesen "
                                           "werden."})
            ui.messageBox("Fehler beim Einlesen des Rahmens:\n%s"
                          % traceback.format_exc())


def register_frame_command(ui: "adsk.core.UserInterface") -> None:
    cmd_def = ui.commandDefinitions.itemById(FRAME_CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            FRAME_CMD_ID, "Rahmen einlesen",
            "Liest die Außenkontur der Auswahl als Rahmen ein.")
    handler = _FrameCreatedHandler()
    cmd_def.commandCreated.add(handler)
    _handlers.append(handler)


def unregister_frame_command(ui: "adsk.core.UserInterface") -> None:
    cmd_def = ui.commandDefinitions.itemById(FRAME_CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


# ------------------------------------------------------- Commit als Command
#
# Der eigentliche Commit laeuft als Fusion-Command. Nur so wird der gesamte
# Vorgang (Skizze + Geometrie + Attribute) zu **einem** Timeline-/Undo-Schritt
# zusammengefasst.

class _CommitCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
            cmd.isAutoExecute = True
            cmd.isExecutedWhenPreEmpted = False
            handler = _CommitExecuteHandler()
            cmd.execute.add(handler)
            _handlers.append(handler)
        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox("Commit konnte nicht gestartet werden:\n%s"
                                         % traceback.format_exc())


class _CommitExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = SESSION.pending
        if doc is None:
            return
        SESSION.pending = None
        try:
            message = perform_commit(app, ui, doc)
            _send(ui, "done", {"ok": True, "message": message})
        except _Abort as abort:
            _send(ui, "done", {"ok": False, "message": str(abort), "warn": True})
        except Exception:
            _send(ui, "done", {"ok": False, "message": "Fehler beim Erzeugen."})
            ui.messageBox("Fehler beim Erzeugen des Musters:\n%s"
                          % traceback.format_exc())


class _Abort(Exception):
    pass


def perform_commit(app, ui, doc: Dict[str, Any]) -> str:
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise _Abort("Kein Konstruktionsdokument aktiv.")

    scene = build.build_scene(doc)
    estimate = build.entity_estimate(scene)
    if estimate > build.ENTITY_WARN_LIMIT and not SESSION.force:
        answer = ui.messageBox(
            "Das Muster erzeugt etwa %d Skizzen-Elemente.\n"
            "Das kann in Fusion sehr lange dauern.\n\nTrotzdem erzeugen?" % estimate,
            "PatternCreator",
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType)
        if answer != adsk.core.DialogResults.DialogYes:
            raise _Abort("Abgebrochen – Muster wurde nicht erzeugt.")

    if SESSION.mode == "edit" and SESSION.sketch is not None:
        sketch = SESSION.sketch
        if storage.was_modified_manually(sketch):
            answer = ui.messageBox(
                "Die Skizze „%s“ wurde seit dem Erzeugen von Hand verändert.\n"
                "Beim Neuaufbau gehen diese Änderungen verloren.\n\nFortfahren?"
                % sketch.name, "PatternCreator",
                adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                adsk.core.MessageBoxIconTypes.WarningIconType)
            if answer != adsk.core.DialogResults.DialogYes:
                raise _Abort("Abgebrochen – Skizze wurde nicht verändert.")
        renderer.clear_pattern_geometry(sketch)
    else:
        comp = design.activeComponent
        plane = SESSION.plane or design.rootComponent.xYConstructionPlane
        # Auf einer Flaeche **ohne** projizierte Kanten skizzieren: Fusion legte
        # sonst die Flaechenkanten in die Skizze - genau auf den Rahmenumriss.
        # Doppelte Kurven zerstoeren die Profile.
        if frame_reader.is_face(plane):
            sketch = comp.sketches.addWithoutEdges(plane)
        else:
            sketch = comp.sketches.add(plane)
        sketch.name = "Muster %s" % doc["pattern"]["type"]
        SESSION.sketch = sketch
        SESSION.mode = "edit"

    result = renderer.render_scene(sketch, scene)
    storage.save(sketch, doc, sketch.sketchCurves.count + sketch.sketchTexts.count)

    message = "Muster erzeugt: %d Elemente in „%s“." % (result.entities, sketch.name)
    for warn in result.warnings:
        message += "\n" + warn
    return message


def register_commit_command(ui: "adsk.core.UserInterface") -> None:
    cmd_def = ui.commandDefinitions.itemById(COMMIT_CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            COMMIT_CMD_ID, "Muster erzeugen", "Erzeugt das Muster in einer Skizze.")
    handler = _CommitCreatedHandler()
    cmd_def.commandCreated.add(handler)
    _handlers.append(handler)


def unregister_commit_command(ui: "adsk.core.UserInterface") -> None:
    cmd_def = ui.commandDefinitions.itemById(COMMIT_CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()
