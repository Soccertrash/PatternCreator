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
from fusion import (frame_reader, renderer, storage, surface_reader,
                    surface_target, trace)

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
    development = SESSION.doc.get("development")
    if development:
        return (development.get("source") or {}).get("label") or "Mantelfläche"
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
        development = SESSION.doc.get("development")
        if development:
            token = (development.get("source") or {}).get("token", "")
            entity = surface_reader.find_surface(token, design)
            if entity is None:
                raise frame_reader.FrameError("Die Mantelfläche ist nicht mehr "
                                              "auffindbar.")
        else:
            source = (SESSION.doc.get("container") or {}).get("customSource") or {}
            entity = frame_reader.find_source(source.get("token", ""), design)
    else:
        entity = frame_reader.pick_from_selection(ui)

    if surface_reader.is_surface(entity):
        return _take_surface(entity)

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
    # Eine ebene Auswahl loest eine vorher gewaehlte Mantelflaeche ab - sonst
    # bliebe das Muster gewickelt, obwohl der Rahmen jetzt flach ist.
    doc["development"] = None
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


def _take_surface(entity) -> Dict[str, Any]:
    """Mantelflaeche als Ziel uebernehmen.

    Im Edit-Modus geht das nur, wenn die Skizze schon zu einer Mantelflaeche
    gehoert: eine bestehende Skizze laesst sich nicht nachtraeglich von einer
    Ebene auf einen Zylinder umhaengen.
    """
    if SESSION.mode == "edit" and not SESSION.doc.get("development"):
        raise frame_reader.FrameError(
            "Diese Skizze liegt auf einer Ebene. Eine Mantelfläche lässt sich "
            "nur bei einem neuen Muster wählen.")
    try:
        snapshot = surface_reader.read_surface(entity)
    except surface_reader.SurfaceError as err:
        raise frame_reader.FrameError(str(err))
    doc = copy.deepcopy(SESSION.doc)
    previous = doc.get("development") or {}
    development = dict(snapshot.development)
    # Nahtwinkel und die Tokens der schon angelegten Geometrie bleiben.
    development["seamAngle"] = previous.get("seamAngle", 0.0)
    development["planeToken"] = previous.get("planeToken", "")
    development["embossTokens"] = previous.get("embossTokens", [])
    doc["development"] = development
    doc, errors = pattern_doc.parse(doc)
    if errors:
        raise frame_reader.FrameError("; ".join(errors.values()))
    SESSION.doc = doc
    return {
        "ok": True,
        "doc": doc,
        "target": _target_label(),
        "message": "Fläche übernommen: %s." % snapshot.label,
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
        except surface_target.TargetError as err:
            # Klartext aus der Flaechenarbeit gehoert in den Editor, nicht als
            # Traceback in eine messageBox.
            _send(ui, "done", {"ok": False, "message": str(err), "warn": True})
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

    trace.begin("Muster erzeugen (%s, %s)"
                % (doc["pattern"]["type"], SESSION.mode))
    if doc.get("development"):
        # Die rohen Zahlen der Flaeche ins Protokoll: geht beim Praegen etwas
        # schief, laesst sich hinterher nachrechnen, ob die Flaeche richtig
        # gelesen wurde - ohne den Benutzer nach Massen fragen zu muessen.
        trace.step("Fläche: %s" % _numbers(doc["development"]))
    scene = build.build_scene(doc)
    estimate = build.entity_estimate(scene)
    if estimate > build.ENTITY_WARN_LIMIT and not SESSION.force:
        extra = ""
        if doc.get("development") and doc["style"].get("embossOn"):
            # Die Praegung kommt oben drauf - gemessen etwa 6,5 ms je Loch
            # (Context.md 15.6, Punkt 5).
            extra = ("\nDie Prägung braucht danach noch einmal etwa %d s."
                     % max(1, round(build.emboss_seconds(scene))))
        answer = ui.messageBox(
            "Das Muster erzeugt etwa %d Skizzen-Elemente.\n"
            "Das kann in Fusion sehr lange dauern.%s\n\nTrotzdem erzeugen?"
            % (estimate, extra),
            "PatternCreator",
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType)
        if answer != adsk.core.DialogResults.DialogYes:
            raise _Abort("Abgebrochen – Muster wurde nicht erzeugt.")

    comp = design.activeComponent
    development = doc.get("development")

    if SESSION.mode == "edit" and SESSION.sketch is not None:
        sketch = SESSION.sketch
        _adopt_tokens(sketch, development)
        if storage.was_modified_manually(sketch):
            answer = ui.messageBox(
                "Die Skizze „%s“ wurde seit dem Erzeugen von Hand verändert.\n"
                "Beim Neuaufbau gehen diese Änderungen verloren.\n\nFortfahren?"
                % sketch.name, "PatternCreator",
                adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                adsk.core.MessageBoxIconTypes.WarningIconType)
            if answer != adsk.core.DialogResults.DialogYes:
                raise _Abort("Abgebrochen – Skizze wurde nicht verändert.")
        if development:
            # **Vor** allem anderen: gibt es die Flaeche ueberhaupt noch? Wer
            # hier erst loescht und dann scheitert, laesst den Benutzer mit
            # einer leeren Skizze zurueck - das Muster waere weg, ohne dass er
            # etwas falsch gemacht haette (Context.md 15.23).
            if surface_target.target_face(design, development) is None:
                raise _Abort(surface_target.missing_face_message(design,
                                                                 development))
        # Die Gruppe vom letzten Mal aufloesen: in einer Gruppe laesst sich
        # schlecht loeschen und umhaengen.
        _unfold_timeline(design, sketch)
        if development:
            # **Zuerst** die Praegungen weg. Solange sie an der Skizze haengen,
            # rechnet Fusion jede Aenderung an Ebene und Kurven durch beide
            # Features durch - bei tausend Loechern steht die Anwendung dabei
            # minutenlang, und die Skizze kommt beschaedigt daraus hervor
            # (gemessen 2026-08-21, siehe Context.md 15.11).
            trace.step("Prägungen entfernen")
            surface_target.remove(design, development.get("embossTokens") or ())
            development["embossTokens"] = []
            trace.step("Tangentialebene prüfen")
            plane, stale = surface_target.ensure_tangent_plane(
                design, comp, development)
            # Die Skizze wird **ersetzt**, nicht geleert: tausende Kurven
            # einzeln zu loeschen hat Fusion minutenlang beschaeftigt
            # (Context.md 15.13). Hier ist das gefahrlos - was an der Skizze
            # hing, waren unsere Praegungen, und die sind schon weg.
            trace.step("Skizze neu anlegen")
            sketch = _replant(comp, sketch, plane)
            SESSION.sketch = sketch
            SESSION.plane = plane
            if stale:
                surface_target.remove(design, stale)
        else:
            trace.step("Skizze leeren")
            renderer.clear_pattern_geometry(sketch)
    else:
        plane = SESSION.plane or design.rootComponent.xYConstructionPlane
        if development:
            trace.step("Tangentialebene anlegen")
            plane, _stale = surface_target.ensure_tangent_plane(
                design, comp, development)
        # Auf einer Flaeche **ohne** projizierte Kanten skizzieren: Fusion legte
        # sonst die Flaechenkanten in die Skizze - genau auf den Rahmenumriss.
        # Doppelte Kurven zerstoeren die Profile.
        if development or frame_reader.is_face(plane):
            sketch = comp.sketches.addWithoutEdges(plane)
        else:
            sketch = comp.sketches.add(plane)
        sketch.name = "Muster %s" % doc["pattern"]["type"]
        SESSION.sketch = sketch
        SESSION.plane = plane
        SESSION.mode = "edit"

    if development:
        trace.step("Lage der Abwicklung messen")
        # Erst jetzt steht die Skizze - und damit, wie die Abwicklung auf ihr
        # liegen muss. Die Szene wird deshalb mit der gemessenen Platzierung
        # noch einmal gebaut; an der Elementzahl aendert eine starre
        # Verschiebung nichts, die Warnung oben gilt also weiterhin.
        face = surface_target.target_face(design, development)
        if face is None:
            raise _Abort(surface_target.missing_face_message(design, development))
        doc["placement"].update(
            surface_target.sketch_placement(sketch, development, face))
        scene = build.build_scene(doc)

    trace.step("Muster zeichnen")
    result = renderer.render_scene(sketch, scene)

    message = "Muster erzeugt: %d Elemente in „%s“." % (result.entities, sketch.name)
    if development and doc["style"].get("embossOn"):
        trace.step("prägen")
        message += "\n" + _emboss(design, comp, sketch, doc, development)
    trace.step("Muster im Dokument sichern")
    storage.save(sketch, doc, sketch.sketchCurves.count + sketch.sketchTexts.count)
    if development:
        trace.step("Zeitleiste zusammenfalten")
        _fold_timeline(design, sketch, development)
    trace.end(message.splitlines()[0])
    for warn in result.warnings:
        message += "\n" + warn
    return message


def _fold_timeline(design, sketch, development: dict) -> None:
    """Ebene, Punkt, Skizze und Praegungen zu **einem** Timeline-Eintrag falten.

    Ein Muster auf einer Mantelflaeche braucht fuenf Features; in der Zeitleiste
    sahen die aus wie fuenf voneinander unabhaengige Schritte. Zusammengefasst
    wird nur, wenn sie lueckenlos beieinanderliegen - sonst schloesse die Gruppe
    fremde Features ein. Misslingt es, bleibt es bei einzelnen Eintraegen: das
    ist Kosmetik und darf den Commit nicht gefaehrden.
    """
    _unfold_timeline(design, sketch)
    name = "Muster: %s" % sketch.name
    entities = [sketch]
    for token in ((development.get("planeToken"), development.get("pointToken"))
                  + tuple(development.get("embossTokens") or ())):
        found = surface_target.find_entity(design, token)
        if found is not None:
            entities.append(found)
    indices = []
    for entity in entities:
        try:
            indices.append(entity.timelineObject.index)
        except Exception:
            return
    if len(indices) < 2:
        return
    low, high = min(indices), max(indices)
    if high - low + 1 != len(set(indices)):
        return                                  # es liegt Fremdes dazwischen
    try:
        group = design.timeline.timelineGroups.add(low, high)
        group.name = name
        group.isCollapsed = True
    except Exception:
        pass


#: Was Fusion beim letzten Erzeugen angelegt hat. Diese Felder gehoeren der
#: Skizze, nicht dem Editor.
TOKEN_KEYS = ("planeToken", "pointToken", "embossTokens")


def _adopt_tokens(sketch, development: Optional[dict]) -> None:
    """Die Tokens des letzten Erzeugens aus der Skizze uebernehmen.

    Das Doc fuer den Commit kommt aus der Palette - und die kennt nur, was beim
    **Oeffnen** des Editors im Dokument stand. Was ein Commit anlegt (Ebene,
    Punkt, Praegungen), erfaehrt sie nie. Beim zweiten „Skizze aktualisieren"
    aus derselben offenen Palette waeren die Tokens deshalb veraltet: die
    Praegungen des ersten Durchlaufs bliebe stehen und zeigten ins Leere,
    und es entstuende bei jedem Mal eine weitere Tangentialebene
    (Context.md 15.21).

    Massgeblich ist, was an der Skizze steht: ``storage.save`` schreibt es am
    Ende **jedes** Commits dorthin.
    """
    if not development:
        return
    stored = (storage.load(sketch) or {}).get("development") or {}
    for key in TOKEN_KEYS:
        if stored.get(key):
            development[key] = stored[key]


def _numbers(development: dict) -> str:
    """Die Masse der Mantelflaeche in einer Zeile - fuer das Protokoll."""
    keys = ("kind", "radius", "faceRadius", "halfAngle", "length", "axisMiddle",
            "periodic", "seamAngle")
    return ", ".join("%s=%s" % (key, development.get(key)) for key in keys)


def _unfold_timeline(design, sketch) -> None:
    """Die Gruppe vom letzten Erzeugen aufloesen, Inhalt behalten.

    Sie wird beim naechsten ``_fold_timeline`` neu gebildet. Solange sie steht,
    liegen Ebene, Punkt, Skizze und Praegungen in einem zugeklappten Block -
    darin etwas zu loeschen oder umzuhaengen ist unnoetig heikel.
    """
    name = "Muster: %s" % sketch.name
    try:
        timeline = design.timeline
        for index in range(timeline.timelineGroups.count - 1, -1, -1):
            group = timeline.timelineGroups.item(index)
            if group.name == name:
                group.deleteMe(False)          # Gruppe loesen, Inhalt behalten
    except Exception:
        pass


def _replant(comp, sketch, plane):
    """Die Musterskizze durch eine leere auf ``plane`` ersetzen.

    Das loest gleich zwei Freezes auf einmal:

    * **Kurven loeschen.** Tausende Skizzenelemente einzeln zu loeschen kostet
      Fusion Minuten. Die Skizze wegzuwerfen ist **ein** Aufruf.
    * **Ebene wechseln.** ``Sketch.redefine`` waere der direkte Weg und war der
      Grund fuer zwei Haenger: Fusion muss die Skizze in der Zeitleiste hinter
      die neue Ebene haengen und rechnet dabei das ganze Muster durch; danach
      lieferte sie entartete Koordinaten - ``modelToSketchSpace`` bildete zwei
      Zentimeter auseinanderliegende Punkte auf denselben Skizzenpunkt ab,
      woran das Ausrichten scheiterte (Context.md 15.12).

    Gefahrlos ist das, weil an einer Musterskizze auf einer Mantelflaeche nur
    unsere eigenen Praegungen haengen - und die sind zu diesem Zeitpunkt schon
    geloescht. Alles, was sonst an ihr hing, schreibt ``storage.save`` gleich
    wieder an die neue.
    """
    name = sketch.name
    try:
        sketch.deleteMe()
    except Exception:
        pass
    fresh = comp.sketches.addWithoutEdges(plane)
    fresh.name = name
    return fresh


def _emboss(design, comp, sketch, doc: Dict[str, Any], development: dict) -> str:
    """Praegen - Fehler dabei sind kein Grund, die Skizze zu verwerfen."""
    depth = float(doc["style"].get("embossDepth", 0.0))
    if abs(depth) < 1e-9:
        return "Prägetiefe 0 – nicht geprägt."
    try:
        tokens = surface_target.emboss(design, comp, sketch, development, depth,
                                       development.get("embossTokens") or ())
    except surface_target.TargetError as err:
        development["embossTokens"] = []
        return "Nicht geprägt: %s" % err
    development["embossTokens"] = tokens
    return "Auf die Fläche geprägt (%d Feature%s)." % (len(tokens),
                                                       "" if len(tokens) == 1 else "s")


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
