# Plan: Eigener Rahmen (1.6.0) und Mantelflächen (1.7.0)

**Stand: 2026-08-21.** Umsetzungsplan für zwei neue Features. Entscheidungen und
Begründungen stehen zusätzlich in `Context.md`, Abschnitt 15 – wer eine
Entscheidung ändern will, ändert sie dort mit Begründung.

Zielgruppe dieses Dokuments: die umsetzende Instanz (Opus). Der Plan ist in
Phasen und nummerierte Arbeitspakete gegliedert. Jedes Paket nennt Dateien,
Akzeptanzkriterien und Tests. Die Reihenfolge ist verbindlich, weil die Pakete
aufeinander aufbauen; innerhalb einer Phase ist ein Paket ein Commit.

---

## 0. Leitplanken (gelten für beide Phasen)

Alle Leitplanken aus `Context.md` Abschnitt 1 bleiben. Konkret:

- `core/`, `generators/`, `text/` importieren **kein** `adsk` – alles, was Fusion
  anfasst, liegt in `fusion/` oder `commands/` (Struktur-Test).
- Reines Python, keine externen Pakete. Das gilt insbesondere für den neuen
  Polygon-Clipper: **keine** shapely/pyclipper.
- Alles Neue passiert **vor** der Scene-Erzeugung in `core/build.build_scene()`;
  nichts im Renderer „nachbessern".
- Deterministisch: gleiches Doc ⇒ identische Geometrie in Vorschau, Commit und
  Re-Edit. Neue Zufallsströme nur als `random.Random(seed + konstante)`.
- Ein Muster = ein Dokument: alles, was zum Neuaufbau nötig ist, steht im
  PatternDoc. Ein Re-Edit darf **nie** davon abhängen, dass Quellgeometrie
  (Profil, Fläche) noch existiert.
- `pytest tests/` muss nach jedem Paket grün sein. Neue Zusicherungen kommen als
  Tests dazu, nicht als Kommentare.
- Doku: README (deutscher **und** englischer Teil), `Context.md` (Entscheidungen,
  Messwerte, Abnahmeliste), Manifest-Version und -Beschreibung.

Fusion-API-Aufrufe, deren Verhalten unten als **[prüfen]** markiert ist, sind vor
dem Bauen des Pakets in Fusion zu verifizieren (kleines Skript oder manuell).
Ergebnis in `Context.md` festhalten – auch wenn es „funktioniert wie erwartet"
lautet.

---

## Phase 1 – Eigener Rahmen (Version 1.6.0)

### Was der Nutzer bekommt

1. Im Befehl **Muster erstellen** kann statt einer Ebene ein **geschlossenes
   Skizzenprofil** oder eine **planare Fläche** gewählt werden. Deren Außenkontur
   wird zum Rahmen; die Skizze entsteht auf derselben Ebene bzw. auf der Fläche.
2. Im Editor gibt es in der Gruppe *Rahmen* die Form **Eigener Rahmen** mit
   - Info-Zeile (Quelle, Punktzahl, Maße),
   - Knopf **Aus Fusion-Auswahl übernehmen** (liest die aktuelle Auswahl im
     Fusion-Canvas ein),
   - Knopf **Rahmen neu einlesen** (liest die gespeicherte Quelle erneut ein –
     z. B. nachdem die Rahmen-Skizze geändert wurde).
3. Alles andere (Muster, Stil, Schraffur, Text, Flächenmodell, Rahmendicke,
   Re-Edit) funktioniert im eigenen Rahmen genauso wie in den Standardformen.
   Konkave Rahmen sind voll unterstützt.
4. Innenkonturen (Löcher im Profil/in der Fläche) werden **ignoriert** – nur
   die Außenkontur zählt (Nutzerentscheidung 2026-08-21).
5. Der Rahmen ist ein **Snapshot** (Punktliste im PatternDoc). Re-Edit braucht
   die Quelle nicht mehr; „Rahmen neu einlesen" holt sie bei Bedarf.

### Datenmodell

`doc["container"]` bekommt:

```
shape:         "custom"                     (neuer Choice-Wert)
customPoints:  [[x, y], ...]                cm, lokal, Schwerpunkt der Bounding-Box bei (0,0),
                                            CCW, ohne Duplikate, ohne Schließpunkt
customSource:  {"kind": "profile"|"face", "label": "Skizze1 / Profil", "token": "<entityToken>"}
                                            (optional; nur für „neu einlesen" und Anzeige)
```

Beim Einlesen wird `placement.originX/Y` auf den Bounding-Box-Mittelpunkt der
Kontur **in Skizzenkoordinaten** gesetzt, `placement.rotation` auf 0. So bleibt
die bestehende Platzierungslogik unverändert, und der Rahmen liegt exakt auf der
Quelle. Der Nutzer darf Ursprung/Drehung danach ändern (der Rahmen ist dann
bewusst verschoben); „neu einlesen" setzt beides zurück.

Validierung in `pattern_doc.parse()`:
- `shape == "custom"` ohne gültige `customPoints` (≥ 3 endliche Punktpaare,
  |Fläche| > 1e-8, ≤ 5000 Punkte) ⇒ Fehler `container.customPoints`, Doc fällt
  auf `rect` zurück.
- `customPoints` werden beim Parsen normalisiert (siehe 1.1: `normalize_frame`).

### Paket 1.1 – Allgemeiner Polygon-Clipper (`core/polyclip.py`)

**Warum neu:** `core/clip.py` kann nur gegen konvexe Bereiche (Halbebenen).
Ein gezeichneter Rahmen ist in der Regel konkav. `core/clip.py` bleibt
unverändert (konvexe Fälle bleiben auf dem schnellen Pfad).

**Verfahren (verbindlich): Randklassifikation, kein Greiner–Hormann.**

Für `polygon ∩ frame` (beide einfach, ohne Löcher, Zelle darf konkav sein):
1. Alle Schnittpunkte zwischen Zellkanten und Rahmenkanten bestimmen
   (inkl. Berührungen und kollinearer Überlappungen; bei kollinearen Kanten
   die Projektionen der Endpunkte als Schnittparameter nehmen).
2. Beide Polygone an allen Schnittparametern aufteilen (Parameter < 1e-9
   zusammenfassen).
3. Jede Teilkante über ihren **Mittelpunkt** klassifizieren:
   - Zell-Teilkante: behalten, wenn Mittelpunkt **innen oder auf dem Rand**
     des Rahmens (Randabstand < 1e-7 cm gilt als „auf dem Rand").
   - Rahmen-Teilkante: behalten, wenn Mittelpunkt **strikt innen** in der Zelle
     (auf dem Rand ⇒ verwerfen). Dadurch kommt eine gemeinsame Kante genau
     einmal – aus der Zelle.
4. Behaltene Teilkanten zu Ringen verketten (Endpunkt-Matching mit Rundung auf
   1e-7 cm), Ringe mit |Fläche| ≤ 1e-10 verwerfen, CCW orientieren. Mehrere
   Ringe = mehrere Stücke (Zelle, die durch eine Einbuchtung in zwei Teile
   zerfällt).
5. Schnellpfade **vor** Schritt 1 (sie entscheiden 95 % der Zellen):
   - Bounding-Boxen disjunkt ⇒ leer.
   - Keine Kantenschnitte **und** ein Zellpunkt innen ⇒ Zelle unverändert.
   - Keine Kantenschnitte **und** ein Rahmenpunkt in der Zelle ⇒ Ergebnis ist
     der Rahmen selbst.
   - Keine Kantenschnitte, nichts davon ⇒ leer.
   - Für „Zellpunkt innen" das Beschleunigungsraster aus 1.2 benutzen.

Begründung der Wahl (für `Context.md` 15): Greiner–Hormann und Weiler–Atherton
brechen an den Degenerationen, die hier die Regel sind (Gitterlinie exakt auf
Rahmenkante, Zellecke auf Rahmenkante, kollineare Überlappung). Die
Randklassifikation behandelt diese Fälle mit zwei expliziten Regeln
(Zelle: Rand = innen; Rahmen: Rand = außen) und wiederverwendet
`chain_segments`/`snap_segments`-Ideen aus `core/geom.py`. Konvexe Zerlegung
plus Verkleben wurde verworfen: das Verkleben entlang der Diagonalen ist bei
konkaven Zellen (Puzzle) eine Polygon-Vereinigung – genau das, was das Projekt
bisher vermeidet.

API:

```python
def clip_polygon_general(subject, frame) -> List[List[Point]]     # Stücke, CCW
def clip_polyline_general(pts, frame, closed=False) -> List[List[Point]]
def polygon_fully_inside(pts, frame) -> bool    # alle Punkte innen/auf Rand, keine Kantenschnitte
def point_on_boundary(p, poly, eps=1e-7) -> bool
def segment_intersections(a, b, c, d) -> List[Tuple[float, float]]  # (t_ab, t_cd), inkl. kollinear
```

`clip_polyline_general`: Segmentweise – Schnittparameter mit allen Rahmenkanten
sammeln, sortieren, Teilsegmente über Mittelpunkt klassifizieren (innen oder auf
Rand = behalten), zusammenhängende behaltene Teilsegmente zu Polylinien
verketten. Genau das, was `clip.clip_polyline` für konvexe Bereiche tut.

**Tests (`tests/test_polyclip.py`):**
- Rechteckiger „custom"-Rahmen ⇒ Ergebnisse bitgleich (Toleranz 1e-9) mit
  `clip.clip_polygon`/`clip.clip_polyline` für 50 zufällige konvexe und konkave
  Zellen (Seed fest). Das ist der Regressionsanker.
- L-Form, U-Form (Zelle zerfällt in zwei Stücke), Stern (viele Reflexecken),
  Kamm (schmale Zähne).
- Degenerationen: Zellkante exakt auf Rahmenkante; Zellecke auf Rahmenkante;
  Zelle berührt Rahmen nur in einem Punkt (⇒ leer); Zelle umschließt den
  ganzen Rahmen (⇒ Rahmen); Zelle identisch mit Rahmen (⇒ Zelle).
- Konkav ∩ konkav (Puzzle-Teil mit Nasen gegen U-Form).
- Flächen-Invariante: Σ Flächen der Stücke ≤ min(Zelle, Rahmen) + 1e-9; für
  eine innen liegende Zelle exakt die Zellfläche.
- Jedes Ergebnis-Stück ist einfach (`optimize._self_intersects` = False).
- Determinismus: zweimal gleicher Aufruf ⇒ gleiche Bytes.

### Paket 1.2 – `CustomContainer` vollständig (`core/containers.py`)

Der vorhandene Stub („Phase 6") wird zur vollwertigen Implementierung:

- Konstruktor: `normalize_frame(points)` – entfernt Duplikate und den
  Schließpunkt (`clean_polygon`), orientiert CCW (`ensure_ccw`), entfernt
  Selbstschnitte (`remove_loops`), vereinfacht mit RDP auf `optimize.TOL`
  (die Fusion-Tesselierung liefert sonst hunderte Punkte auf Bögen). Ergebnis
  < 3 Punkte oder Fläche ~0 ⇒ `ValueError` (wird in `pattern_doc.parse` zum
  Feldfehler).
- `clip_polygon()` ⇒ die Punkte; `contains()` ⇒ Raster-Schnellpfad, sonst
  `point_in_polygon`.
- `clip_path()` ⇒ `polyclip.clip_polygon_general` / `clip_polyline_general`.
- `fully_inside()` ⇒ `polyclip.polygon_fully_inside`.
- `shrunk(delta)` ⇒ Stroker-Offset nach innen (wie `build._shrink_cell`, die
  Logik nach `core/geom.py` oder `core/stroker.py` als `shrink_polygon()`
  auslagern und in `build.py` wiederverwenden). Misslingt das (Fläche wächst,
  < 3 Punkte, Kontur zerfällt) ⇒ `self` zurückgeben **und** Flag
  `self.shrink_failed = True` setzen; `build_scene` hängt dann die Warnung
  „Rahmendicke ist für diesen Rahmen an mindestens einer Stelle zu groß" an.
  Zerfällt der Offset in mehrere Ringe (Hantelform), gilt der größte.
- `face_outline()`/`outline()` wie bisher (ein geschlossener Pfad, Rolle
  `face` bzw. `edge`, Layer `border`).
- **Beschleunigungsraster:** einmal je Punktfolge ein 64×64-Raster über der
  Bounding-Box: jede Rasterzelle ist `inside` / `outside` / `boundary`
  (Boundary = von einer Rahmenkante berührt; sonst Mittelpunkt-Test). Cache auf
  Modulebene, Schlüssel = Tupel der Punkte (Vorschau baut den Container bei
  jeder Reglerbewegung neu). Genutzt von `contains` und den Schnellpfaden aus
  1.1 über eine Methode `classify_bbox(x0, y0, x1, y1) -> "inside"|"outside"|"mixed"`.
- `make_container()` ⇒ `CustomContainer(cfg["customPoints"])` bei `shape == "custom"`.
- `SHAPES` um `"custom"` ergänzen.

`core/build.py`:
- Nach `container.shrunk(...)`-Aufrufen `shrink_failed` prüfen und Warnung
  anhängen (beide Stellen: `clip_container` und `hole_limit`).
- Sonst **keine** Änderung – das ist die Zusicherung, dass der Rahmen ein
  reines Container-Thema ist. Wenn sich im Bau herausstellt, dass `build.py`
  doch eine Sonderbehandlung braucht, in `Context.md` begründen.

**Tests (`tests/test_custom_container.py`):**
- Rechteck-Custom vs. `RectContainer`: `build_scene` für alle neun Muster mit
  Default-Parametern ⇒ gleiche Anzahl Konturen, gleiche Summe der
  Lochflächen (Toleranz 1e-6). Regressionsanker.
- 96-Eck-Custom vs. `CircleContainer`: Lochflächen-Summe ±0,5 % (der echte
  Kreis ist `ir.Circle`, sonst gleich).
- Konkaver Rahmen (L, U, Stern) mit jedem Muster im Flächenmodell: kein Loch
  schneidet die Außenkontur; für 200 Stichproben auf der Außenkontur ist der
  Abstand zum nächsten Loch ≥ `borderWidth − 1e-6`; Splitterfilter greift;
  alle Konturen einfach.
- Puzzle (konkave Zellen) in U-Rahmen.
- `dropPartial` in konkavem Rahmen: nur vollständig innen liegende Zellen.
- Linienmodus (`mode = "lines"`) im konkaven Rahmen: keine Kurve ragt heraus.
- Text-Knockout + Schraffur im konkaven Rahmen laufen durch (kein Absturz,
  Schraffurstege liegen in den Löchern).
- `shrunk` an Hantelform ⇒ Warnung, kein Absturz.
- `normalize_frame`: Schließpunkt, Duplikate, CW-Eingabe, selbstschneidende
  Eingabe, 2000-Punkte-Kreis ⇒ nach RDP deutlich weniger Punkte, Fläche ±0,1 %.
- **Performance:** Voronoi 500 Zellen in einem 400-Punkte-Stern: `build_scene`
  ≤ 1,5 × Laufzeit desselben Musters im Rechteck (gemessen im selben Test;
  Referenzwert in `Context.md` eintragen).
- Determinismus über zwei Aufrufe.

### Paket 1.3 – Datenmodell und Schema (`core/pattern_doc.py`)

- `CONTAINER_PARAMS`: Choice `("custom", "Eigener Rahmen")`. Keine numerischen
  Felder mit `visible_if shape == custom`; die Custom-Anzeige macht der Editor
  (1.5).
- `parse()`: `customPoints`/`customSource` durchreichen und validieren (siehe
  Datenmodell). `customSource` darf fehlen; `token`/`label`/`kind` sind Strings.
- `default_doc()` unverändert (`rect`).
- Alt-Dokumente ohne die Felder laden unverändert (Test).
- `schema()`: keine Sonderbehandlung nötig – aber ein Test sichert, dass
  `"custom"` in den Choices ankommt.

**Tests (`tests/test_pattern_doc.py` erweitern):** Roundtrip
serialize/deserialize mit `custom`; ungültige `customPoints` ⇒ Feldfehler und
Rückfall auf `rect`; Alt-Doc ohne Felder.

### Paket 1.4 – Fusion: Rahmen einlesen (`fusion/frame_reader.py`, neu)

Fusion-seitiger Leser, **Fusion-frei testbar ist nur die Nachbearbeitung**
(die liegt in `core`). Aufgaben:

```python
def read_frame(entity, sketch_or_plane) -> FrameSnapshot
    # entity: adsk.fusion.Profile | adsk.fusion.BRepFace (planar)
    # liefert: points2d (Skizzenkoordinaten, cm), plane (ConstructionPlane|BRepFace),
    #          label, kind, token
```

- **Profil:** `profile.profileLoops` ⇒ Loop mit `isOuter` ⇒ `profileCurves`
  ⇒ `sketchEntity.worldGeometry` ⇒ `evaluator.getParameterExtents()` +
  `getStrokes(t0, t1, tol)` mit `tol = optimize.TOL` (0,002 cm) ⇒ Punkte im
  Weltkoordinatensystem. Ebene = `profile.parentSketch.referencePlane`
  **[prüfen: Eigenschaft liefert ConstructionPlane oder BRepFace; bei
  gelöschter Referenz `None` ⇒ Fehlermeldung]**.
- **Planare Fläche:** `face.loops` ⇒ `isOuter` ⇒ `coEdges` ⇒ `edge.geometry`
  ⇒ `evaluator.getStrokes` ⇒ Weltkoordinaten. Ebene = die Fläche selbst.
  Richtung der CoEdges **nicht** trauen, sondern Kurvenstücke über
  Endpunkt-Matching verketten (Rundung 1e-6 cm); Lücken > 1e-4 cm ⇒ Fehler
  „Kontur nicht geschlossen".
- **Welt ⇒ Skizze:** Wenn eine Ziel-Skizze existiert (Edit-Modus), direkt
  `sketch.modelToSketchSpace(p)`. Im Create-Modus gibt es noch keine Skizze:
  dann **Temporärskizze** `comp.sketches.addWithoutEdges(plane)`, alle Punkte
  umrechnen, `sketch.deleteMe()`. Das läuft innerhalb eines Commands (siehe
  1.6), damit nichts in der Timeline zurückbleibt **[prüfen: Create+Delete in
  einem Command hinterlässt keinen Timeline-Eintrag; falls doch, Alternative:
  Skizzenrahmen aus `plane.geometry` (Plane.uDirection/vDirection) ableiten
  und in Fusion verifizieren, dass er dem Frame einer neuen Skizze auf dieser
  Ebene entspricht]**. Koplanaritätsprüfung: |z| aller Punkte in
  Skizzenkoordinaten < 1e-4 cm, sonst Fehler „Auswahl liegt nicht auf der
  Skizzenebene".
- Danach `core`-Nachbearbeitung: `normalize_frame`, Bounding-Box-Mittelpunkt
  ⇒ `originX/Y`, Punkte relativ dazu ⇒ `customPoints`.
- `token = entity.entityToken` **[prüfen: Profile hat entityToken; sonst
  Fallback: Token der Eltern-Skizze + Loop-Index]**, `label` = „Skizze / Profil n"
  bzw. „Körper / Fläche".
- Wiederfinden: `design.findEntityByToken(token)` ⇒ Liste; leer ⇒ Meldung
  „Quelle nicht mehr vorhanden – bitte neu auswählen".
- Fehler sind Klartext-Exceptions (`FrameError`), die die Brücke als Meldung
  an den Editor gibt – nie `messageBox` aus dem Leser heraus.

**Wichtig – Skizze ohne projizierte Kanten:** Bei einer Fläche als Ziel
erzeugt `sketches.add(face)` automatisch die projizierten Flächenkanten in der
Skizze. Die lägen exakt auf dem Rahmenumriss ⇒ doppelte Kurven ⇒ kaputte
Profile. `perform_commit` muss deshalb für Flächen **`addWithoutEdges`**
verwenden **[prüfen: Methode vorhanden; für ConstructionPlanes weiterhin
`add`]**. Das gilt auch, wenn der Nutzer eine Fläche wählt, aber einen
Standardrahmen behält – die projizierten Kanten waren schon bisher unerwünschte
Beifracht.

### Paket 1.5 – Editor (`palette/editor.js`, `editor.html`, `editor.css`)

- Im Formular der Gruppe *Rahmen*: Die generische Choice `shape` bleibt. Ist
  `shape == "custom"`, wird unter den (ausgeblendeten) Maßfeldern ein Block
  `#customFrameBox` gezeigt:
  - Info: „Quelle: Skizze1 / Profil 2 · 213 Punkte · 54,2 × 31,0 mm"
    (Quelle aus `customSource.label`, Maße aus Bounding-Box der `customPoints`).
  - Knopf **Aus Fusion-Auswahl übernehmen** ⇒ `sendToFusion('pickFrame', {})`.
  - Knopf **Rahmen neu einlesen** ⇒ `sendToFusion('rereadFrame', {})`; nur
    aktiv, wenn `customSource.token` vorhanden.
- Ohne `customPoints` ist die Option „Eigener Rahmen" im Dropdown **wählbar**,
  zeigt aber statt der Info den Hinweis „Im Fusion-Canvas ein geschlossenes
  Skizzenprofil oder eine ebene Fläche auswählen, dann *Aus Fusion-Auswahl
  übernehmen*" und die Vorschau bleibt beim bisherigen Rahmen (das Doc darf
  `shape: custom` ohne Punkte **nicht** an Python schicken – Editor hält in dem
  Fall intern `rect` und zeigt nur die Custom-Oberfläche; einfacher: erst nach
  erfolgreichem Einlesen wird `shape` wirklich auf `custom` gesetzt).
- Neue Nachrichten Python ⇒ JS: `frame` mit `{ok, doc?, message}`. Bei `ok`
  ersetzt der Editor `doc.container` und `doc.placement` (Origin/Rotation) aus
  der Antwort, pusht History, fordert Vorschau mit `fit` an.
- `resetSection('container')` bei `custom`: setzt auf `rect` zurück und
  behält `customPoints`/`customSource` **nicht** (Zurücksetzen heißt
  zurücksetzen).
- Zielbeschriftung (`targetLabel`): „Ebene: … · Rahmen: Skizze1 / Profil 2".
- Hilfe-Text zur Form ergänzen (im Param-`help`).

Keine Änderung an `preview.js`: der Rahmen kommt als IR-Pfad (Layer `border`).

### Paket 1.6 – Brücke und Befehle (`commands/`)

`commands/create_command.py`:
- Die Auswahl `planeSel` akzeptiert zusätzlich **`Profiles`** (Filterstring
  `"Profiles"`). Beschriftung: „Ebene, Fläche oder Profil".
- Neue Checkbox `useAsFrame` „Kontur als Rahmen verwenden" (Standard **an**),
  nur sichtbar, wenn die Auswahl eine Fläche oder ein Profil ist
  (`inputChanged`-Handler, Referenz global halten).
- Execute: bei Profil/Fläche mit `useAsFrame` ⇒ `frame_reader.read_frame`
  (innerhalb dieses Commands läuft die Temporärskizze) ⇒ Doc mit `custom`
  ⇒ `open_editor(..., plane=<aus Snapshot>)`. Fehler ⇒ `messageBox` mit
  Klartext, Editor öffnet trotzdem mit Standardrahmen auf der Ebene.

`commands/palette_bridge.py`:
- Neue Aktionen `pickFrame` und `rereadFrame`. Beide laufen **als
  Auto-Execute-Command** (`PatternCreatorFrameCmd`, analog zum Commit-Command),
  damit die Temporärskizze im Create-Modus innerhalb einer Transaktion
  entsteht und verschwindet.
- `pickFrame`: `ui.activeSelections` **[prüfen: liefert die Canvas-Auswahl,
  während die Palette offen ist]** ⇒ erstes Profil / erste planare Fläche
  (sonst Meldung). Create-Modus: Ebene darf wechseln (`SESSION.plane`
  aktualisieren, `target`-Label neu senden). Edit-Modus: Koplanarität mit
  `SESSION.sketch` erzwingen.
- `rereadFrame`: Token aus `SESSION.doc["container"]["customSource"]` ⇒
  `findEntityByToken` ⇒ `read_frame`.
- Antwort `frame` wie in 1.5.
- `perform_commit`: `addWithoutEdges` für Flächen (siehe 1.4).
- `SESSION.reset()` unverändert; `SESSION.plane` kann jetzt durch `pickFrame`
  gesetzt werden.

`PatternCreator.py`: Registrierung/Deregistrierung des neuen Frame-Commands
(wie Commit-Command). Zweimal Laden/Entladen ⇒ keine Duplikate (bestehender
Abnahmepunkt).

### Paket 1.7 – Doku, Version, Abnahme

- `PatternCreator.manifest`: Version `1.6.0`, Beschreibung um „eigene
  Rahmen aus Skizzenprofilen oder Flächen" ergänzen.
- README (DE und EN): Bedienung (neuer Abschnitt „Eigener Rahmen" unter
  *Bedienung* mit den zwei Wegen: im Befehlsdialog, im Editor), Grundbegriffe,
  Testmatrix (konkaver Rahmen, Fläche als Rahmen, Re-Edit nach Änderung der
  Rahmen-Skizze, „neu einlesen" mit gelöschter Quelle), Bekannte
  Einschränkungen (nur Außenkontur; Bögen im Rahmen werden als Linienzug
  gezeichnet, Toleranz 0,02 mm; Rahmen ist Snapshot; Rahmendicke kann an engen
  Stellen nicht eingehalten werden ⇒ Warnung), Architektur (`core/polyclip.py`,
  `fusion/frame_reader.py`).
- `Context.md` Abschnitt 15: Messwerte (Performance-Faktor aus 1.2, Elementzahl
  eines Beispielrahmens vor/nach RDP), **[prüfen]**-Ergebnisse, gestrichene
  Erwartungen. Abschnitt 3 „Offen geblieben" aktualisieren. Abschnitt 12
  (Abnahme in Fusion) ergänzen: Rahmen liegt deckungsgleich auf der Quelle;
  Fläche als Rahmen ohne projizierte Kanten; Muster im konkaven Rahmen als
  **ein** Profil wählbar; Re-Edit nach Verschieben der Quell-Skizze (Snapshot
  bleibt, „neu einlesen" zieht nach).
- Galerie: ein Bild „Voronoi in Herzform" oder Ähnliches (optional).

**Abnahme Phase 1 (in Fusion):** alle Punkte aus Abschnitt 12 von `Context.md`
plus die oben genannten; Extrusion des Flächenmodells im konkaven Rahmen ergibt
**einen** Körper; STL ohne Reparaturhinweis.

---

## Phase 2 – Mantelflächen: Zylinder und Kegel (Version 1.7.0)

### Was der Nutzer bekommt

1. Im Befehl **Muster erstellen** (und per *Aus Fusion-Auswahl übernehmen*) kann
   eine **zylindrische oder konische Fläche** gewählt werden.
2. Das Add-In **wickelt die Fläche ab** und erzeugt die Skizze auf einer
   **Tangentialebene** an die Fläche, in den Maßen der Abwicklung. Die Kontur
   der abgewickelten Fläche ist der Rahmen (Phase-1-Mechanik). Ist die Fläche
   rundum geschlossen (voller Zylinder/Kegel), ist der Rahmen das
   Abwicklungsrechteck bzw. der Kreisringsektor, und das Muster läuft an der
   **Naht nahtlos** durch (Nutzerentscheidung 2026-08-21).
3. Optionale Checkbox **Auf Fläche prägen (Emboss)** mit **Prägetiefe** (mm,
   positiv = erhaben, negativ = vertieft) und **Nahtwinkel** (Drehung um die
   Achse). Standard: aus. Das ist die eine, bewusste Ausnahme vom Grundsatz
   „das Add-In erzeugt nur Skizzen" (Begründung in `Context.md` 15).
4. Würfel/Quader und andere planare Flächen: bereits durch Phase 1 abgedeckt
   (Fläche als Rahmen). Kugeln und Freiformflächen: **nicht** unterstützt
   (keine Abwicklung; Fusions Emboss wickelt nur Zylinder/Kegel) – klare
   Fehlermeldung bei Auswahl.

### Paket 2.0 – Spike in Fusion (vor allem anderen, Ergebnis in `Context.md`)

Ein Wegwerf-Skript (nicht einchecken) klärt in dieser Reihenfolge; jedes
Ergebnis entscheidet über den Zuschnitt der Folgepakete:

1. `design.rootComponent.features.embossFeatures` vorhanden? (API seit
   September 2025; sonst **Emboss-Checkbox deaktiviert mit Hinweis auf die
   Fusion-Version**, Rest der Phase bleibt.)
2. **Tangentialebene parametrisch anlegen:** `ConstructionPlaneInput.setByTangent(face, angle, planarEntity)` – welche `planarEntity` ist zulässig
   (muss sie parallel zur Achse sein)? Funktioniert es bei beliebig
   orientierter Achse? Fallback-Reihenfolge: (a) `setByTangentAtPoint(face,
   vertex/sketchPoint)`; (b) Achse per `constructionAxes … setByCircularFace`
   + Ebene `setByAngle`; (c) notfalls Ebene nur bei achsparallelen Zylindern
   (Achse ∥ X/Y/Z) unterstützen und das dokumentieren.
3. **Wie landet die Skizze auf der Fläche?** Sketch auf der Tangentialebene mit
   einem bekannten Rechteck (z. B. 20 × 10 mm, Mittelpunkt auf der
   Berührlinie) ⇒ Emboss ⇒ Lage auf dem Zylinder messen: bildet Skizzen-x auf
   die Bogenlänge ab? Wo liegt die Naht bei einem 360°-Rechteck? Was tun
   `horizontalDistance`/`verticalDistance`/`rotationAngle`?
4. **Kegel:** gleicher Test auf einem Kegelstumpf. Ist der Wrap eine exakte
   Abwicklung (Kreisringsektor) oder eine Näherung? Davon hängt ab, ob der
   Kegel in 2.5 exakt oder mit Warnung „Näherung" kommt.
5. **Profilauswahl:** Bei der Flächenmodell-Skizze (Außenkontur + n Löcher) hat
   das Stegprofil die meisten Loops ⇒ `max(profiles, key=loops.count)`.
   Prüfen, dass Emboss dieses eine Profil akzeptiert und wie lange Emboss für
   100 / 300 / 600 Löcher braucht (Messwerte!). Über ~60 s ⇒ Warnschwelle
   analog `ENTITY_WARN_LIMIT`.
6. **Re-Edit:** Skizze leeren und neu zeichnen ⇒ rechnet das Emboss-Feature
   neu (wie die Extrusion) oder verliert es sein Profil? Wenn es verliert:
   Emboss im Re-Edit löschen und neu anlegen (Feature-Token im Doc merken).
7. Vollzylinder-Fläche: hat der äußere Loop eine Nahtkante (Mantellinie) oder
   nur die zwei Kreise? Bestimmt die Periodizitäts-Erkennung in 2.2.

Erst wenn 1–3 geklärt sind, weiterbauen. Scheitert 2 oder 3 grundsätzlich,
bleibt Phase 2 beim Zuschnitt „abgewickelte Skizze auf Tangentialebene,
Emboss macht der Nutzer" – das ist als Rückfallebene von vornherein ein
gültiges Ergebnis.

### Paket 2.1 – Abwicklung (`core/development.py`, neu, Fusion-frei)

Reine Mathematik: Mantelfläche ⇒ Ebene.

```python
@dataclass
class Development:
    kind: str            # "cylinder" | "cone"
    radius: float        # Zylinder: r; Kegel: Radius am unteren Rand
    half_angle: float    # Kegel: halber Öffnungswinkel (rad); Zylinder 0
    length: float        # axiale Länge (Zylinder) bzw. Mantellinienlänge (Kegel)
    periodic: bool       # volle Umwicklung
    def to_plane(self, theta: float, s: float) -> Point   # Flächenkoordinaten -> Abwicklung
    def period(self) -> float                              # Umfang in Abwicklungs-x (Zylinder)
    def frame_points(self, outline_theta_s: List[Point]) -> List[Point]   # Kontur abwickeln
```

- **Zylinder:** `to_plane(θ, s) = (r·θ, s)`; Abwicklung ist das Rechteck
  `[−πr, πr] × [−L/2, L/2]`; `x = 0` ist die Berührlinie der Tangentialebene,
  die Naht liegt bei `x = ±πr`.
- **Kegel:** Koordinaten (ρ, φ) mit ρ = Abstand vom Apex entlang der
  Mantellinie, φ = θ·sin(α). Abwicklung ist ein Kreisringsektor. **Das Muster
  wird nicht direkt im Sektor erzeugt**, sondern im Rechteck
  `[−½·Ω·ρ_m, ½·Ω·ρ_m] × [ρ_0, ρ_1]` (Ω = Sektorwinkel, ρ_m = mittlerer
  Radius) und anschließend mit `warp_to_sector(x, y) = (y·sin(x/ρ_m), y·cos(x/ρ_m))`
  in den Sektor verzerrt. Vorher werden alle geraden IR-Segmente so
  unterteilt, dass die Sehnenhöhe nach dem Verzerren ≤ `optimize.TOL`
  bleibt (Schrittweite aus Krümmung 1/ρ ableiten). So bleiben Gitter,
  Periodizität und Flächenmodell unverändert; Zellen werden zum Apex hin
  schmaler – genau so, wie eine Abwicklung aussieht. Der Verzerrungsschritt
  läuft in `build_scene` **nach** der Flächenbildung/Schraffur und **vor** der
  Platzierung; Kreise (`ir.Circle`) werden dafür tesselliert, `ir.Arc`/
  `ir.Ellipse` ebenfalls (im Flächenmodell kommen sie ohnehin nicht vor).
- **Kontur einer Teilfläche** (Halbzylinder, Kegelstumpf-Sektor, schräg
  geschnittener Zylinder): Kantenpunkte der Fläche in (θ, s) ⇒ `to_plane` ⇒
  Polygon ⇒ `CustomContainer` (Phase 1). Die θ-Werte einer Kontur, die die
  Naht kreuzt, müssen **entrollt** werden (aufeinanderfolgende Punkte mit
  Sprung > π um 2π korrigieren).
- **Periodizitätserkennung** (Fusion-seitig in 2.4, Kriterium hier
  definiert): Fläche ist periodisch, wenn kein Kontur-Teilstück entlang einer
  Mantellinie verläuft **und** die θ-Überdeckung der Kontur ≥ 2π − 1e-3 ist.

**Tests (`tests/test_development.py`):** Isometrie (Abstände auf dem
Zylinder = Abstände in der Abwicklung für achs- und umfangsparallele
Strecken); Kegel-Sektorwinkel = 2π·sin α; `warp_to_sector` bildet das
Rechteck flächentreu ab (±0,1 % bei feiner Unterteilung); Entrollen der
θ-Werte; ein schräg geschnittener Zylinder ergibt eine Sinuskontur.

### Paket 2.2 – Periodischer Modus in Generatoren und Pipeline

`GenContext` bekommt `period_x: float = 0.0` (0 = aus). Ist er gesetzt,
**garantiert jeder Generator**, dass die linke und rechte bbox-Kante
(`bbox[0]`, `bbox[2]`, Abstand exakt `period_x`) **Zellgrenzen** sind und das
Muster mit Periode `period_x` fortsetzbar ist. Die Regel für `Context.md`:
**„Die Naht ist immer ein Steg. Jeder Generator legt im periodischen Modus eine
Zellgrenze auf die Naht."** Ein Steg auf der Naht ist nach dem Wickeln ein
normaler Steg (zwei halbe Stege treffen sich), und das Muster hat dort keinen
Bruch – weder in der Zellgröße noch in der Ausrichtung.

Generator-Regeln (alle über einen gemeinsamen Helfer `_util.snap_period(value, period)`
⇒ `period / max(1, round(period / value))`):
- **Gitter:** `spacingX` rasten (wirksame Periode in x ist `e1.x = sx/sinθ`;
  rasten, sodass `period_x / e1.x` ganzzahlig). Lattice-Ursprung auf
  `bbox[0]` legen, damit die Naht eine Gitterlinie ist.
- **Rauten:** Periode `width` rasten, Ursprung `bbox[0]`.
- **Wabe:** flat-top Periode `√3·cellSize`, pointy Periode `cellSize`; rasten,
  Spaltenraster bei `bbox[0]` beginnen.
- **Mauer:** `brickWidth` rasten, Reihen bei `bbox[0]` beginnen. Bei Verbänden
  mit Versatz liegt die Naht in jeder zweiten Reihe **in** einem Ziegel – der
  Steg dort ist genau eine Fuge breit (`max(Dicke, Fuge)`). Das ist sichtbar
  und wird so dokumentiert (Alternative – Naht „offen" lassen – lässt sich in
  einer 2D-Skizze nicht darstellen).
- **Puzzle:** `countX` Teile auf exakt `period_x`; die x-Außenkanten bekommen
  **keine** Nasen (eine Nase über die Naht würde vom Nahtsteg durchtrennt).
- **Organische Zellen (`organic_cells.build_cells`):** Saatpunkte im Fenster
  `[x0, x0 + P)`; für Voronoi, Relax und Mindestabstand werden **Spiegel-
  Geisterpunkte** an beiden Fensterkanten hinzugefügt (Punkte mit Abstand
  < `w` zur Kante an der Kante gespiegelt, `w` = 2·mittlerer Zellradius).
  Voraussetzung dafür: die Punkte im Band `[x0 + P − w, x0 + P)` werden durch
  die Spiegelbilder der Punkte aus `[x0, x0 + w)` **ersetzt** (Ersetzen, nicht
  ergänzen – sonst stimmt die Zellenzahl nicht). Dann ist jede Zellgrenze
  nahe der Naht exakt die Naht, die Zellen beiderseits sind spiegelsymmetrisch,
  und nach dem Wickeln ist die Naht eine gewöhnliche Zellgrenze. Lloyd
  erhält die Symmetrie (symmetrische Konfiguration bleibt symmetrisch), wenn
  die Geister in jeder Iteration mitgeführt werden. `rows`-Modus (Gewebe):
  `per_row` so wählen, dass `dx` die Periode teilt (ergibt sich, wenn
  `bbox`-Breite = Periode). `leaf_veins` (zweistufig): beide Stufen mit
  Geistern.
- `ctx.rnd` bleibt der einzige Zufall; Geisterpunkte sind abgeleitet, nicht
  gewürfelt.

`core/build.py`:
- `doc["development"]` (siehe 2.3) vorhanden ⇒ Container ist ein
  `DevelopmentContainer` (2.3), `period_x` = Umfang, **`patternAngle` wird
  ignoriert** (ein gedrehtes Gitter ist nicht x-periodisch; der Editor blendet
  das Feld aus und zeigt einen Hinweis).
- Nahtsteg: `clip_container` wird in x **nicht** verkleinert (Zellen laufen
  bis zur Naht), `hole_limit` in x um `max(Dicke, eigene Fuge)/2`, in y wie
  bisher um `borderWidth`. Dazu bekommt `Container` eine Methode
  `shrunk_xy(dx, dy)` (Standard: `shrunk(max(dx, dy))`; `DevelopmentContainer`
  überschreibt). `face_outline()` bleibt das volle Rechteck. Rahmenband im
  Nicht-Flächenmodus: volles Rechteck (eine Linie auf der Naht ist bei
  Gravuren unschädlich).
- Nach Flächenbildung/Schraffur/Text, vor Platzierung: `warp_to_sector` für
  den Kegel (2.1).

**Tests (`tests/test_periodic.py`):**
- Für jedes der neun Muster im periodischen Modus: linker und rechter
  Rand des Fensters sind Zellgrenzen (kein Loch schneidet `x = x0` bzw.
  `x = x0 + P`; jedes Loch endet dort mit Abstand `web_half` ± 1e-6).
- Versetzt man das Fenster um `P` (zweiter Lauf mit `bbox + (P, 0)`), ist das
  Ergebnis das um `P` verschobene erste (Lattice-Muster exakt; organische
  Muster: gleiche Saat ⇒ gleiche Zellen).
- Organisch: Zellen im Nahtband sind paarweise spiegelsymmetrisch (Fläche,
  Schwerpunkt-Abstand zur Naht); Zellenzahl = `cellCount` ± 0.
- Puzzle: keine Nase auf den x-Außenkanten; Teilebreite = P/countX.
- Mauer: Nahtsteg genau `max(Dicke, Fuge)` breit.
- Kegel-Warp: Flächenmodell bleibt eine Fläche mit Löchern; kein Loch
  schneidet die Außenkontur; Elementzahl-Zuwachs messen und in `Context.md`
  eintragen.

### Paket 2.3 – Datenmodell (`core/pattern_doc.py`, `core/containers.py`)

```
doc["development"] = None | {
    "kind": "cylinder" | "cone",
    "radius": float,          # cm
    "halfAngle": float,       # rad, Zylinder 0
    "length": float,          # cm (axial bzw. Mantellinie)
    "periodic": bool,
    "seamAngle": float,       # Grad, Drehung um die Achse (Nahtwinkel)
    "source": {"token": "...", "label": "Körper1 / Fläche 3"},
}
doc["style"] += embossOn (bool, Standard False), embossDepth (T_LENGTH, 0.1 cm, −5..5)
```

- `development` vorhanden ⇒ `container.shape` ist `"custom"` mit den
  abgewickelten Konturpunkten (Teilfläche) **oder** `"rect"` mit
  `width = Umfang`, `height = length` und Flag `periodic` (volle Umwicklung).
  Dafür: `DevelopmentContainer(RectContainer)` mit `periodic_x = True`,
  `shrunk_xy`, und `make_container(cfg, development)`.
- `parse()`: `development` validieren (Zahlen endlich, `radius > 0`,
  `length > 0`, `halfAngle ∈ [0, π/2)`), Alt-Docs ⇒ `None`.
- `embossOn`/`embossDepth` im Style-Schema mit `visible_if`, das nur im
  Flächenmodell (`mode = area`, `fillTarget = webs`, `border = True`) und nur
  bei vorhandener `development` greift – Letzteres kann `visible_if` nicht
  ausdrücken ⇒ der Editor blendet die Gruppe zusätzlich nach
  `doc.development` (kleiner Sonderfall in `applyVisibility`, dokumentieren).
- Schema-Test (`test_every_style_parameter_reaches_the_editor_schema`) bleibt
  automatisch gültig.

### Paket 2.4 – Fusion: Mantelfläche einlesen (`fusion/surface_reader.py`, neu)

```python
def read_surface(face) -> SurfaceSnapshot
    # face.geometry: adsk.core.Cylinder | adsk.core.Cone; sonst SurfaceError
    # liefert: development-Dict, Konturpunkte in (θ, s) (für Teilflächen),
    #          periodic, Achse/Ursprung (für Tangentialebene), token, label
```

- Kontur: äußerer Loop ⇒ Kanten ⇒ `getStrokes` ⇒ Punkte ⇒ in (θ, s)
  umrechnen (Zylinder: θ = atan2 in der Achsen-Ebene, s = Projektion auf die
  Achse; Kegel: ρ = Abstand zum Apex, θ wie beim Zylinder). Entrollen und
  Periodizität gemäß 2.1. Innere Loops ignorieren (wie Phase 1).
- Kugel, Torus, NURBS ⇒ `SurfaceError("Nur zylindrische und konische
  Mantelflächen (und ebene Flächen) werden unterstützt.")`.
- Kein `adsk`-Zustand im Doc – nur Zahlen und der Token.

### Paket 2.5 – Fusion: Tangentialebene, Platzierung, Emboss (`fusion/surface_target.py`, neu)

- `ensure_tangent_plane(comp, face, seam_angle)`: Konstruktionsebene nach dem
  in 2.0 ermittelten Weg; Name „PatternCreator Tangente". Beim Re-Edit die
  vorhandene Ebene wiederverwenden (Token im Doc: `development.planeToken`);
  Nahtwinkel geändert ⇒ Ebene neu setzen (Parameter ändern, nicht neu
  anlegen).
- Skizze auf dieser Ebene (`addWithoutEdges`). **Ausrichtung der Szene:**
  Berührlinie (Punkte `axisPoint ± axisDir·L/2`, radial um `r` versetzt) per
  `modelToSketchSpace` in Skizzenkoordinaten holen ⇒ die Szene (Abwicklungs-
  koordinaten, x = Umfang, y = Achse, Ursprung = Mitte der Berührlinie) wird
  durch eine starre Transformation so gelegt, dass x = 0 auf der Berührlinie
  liegt und y entlang der Achse zeigt. Diese Transformation ist **Teil der
  Platzierung** (`placement.originX/Y/rotation` im Doc setzen, wie in Phase 1
  beim Rahmen-Snapshot) – so bleibt der Renderer dumm und das Doc vollständig.
- Emboss (`embossOn`): Profil mit den meisten Loops + alle `SketchText`s ⇒
  `embossFeatures.createInput([...], [face], ValueInput.createByReal(depth))`,
  `isTangentChain = False` ⇒ `add`. Feature-Token im Doc
  (`development.embossToken`). Re-Edit: je nach 2.0 Punkt 6 Feature behalten
  oder löschen/neu anlegen. Emboss **nur** im Flächenmodell; sonst Checkbox
  deaktiviert (Hilfetext erklärt warum: nur dort ist das Muster ein Profil).
- Vorwarnung analog `ENTITY_WARN_LIMIT`: Lochzahl über der in 2.0 gemessenen
  Schwelle ⇒ Ja/Nein-Dialog vor dem Emboss.
- Alles in `perform_commit`, weiterhin ein Command = ein Undo-Schritt (Ebene +
  Skizze + Emboss zusammen; Timeline zeigt naturgemäß drei Einträge).

### Paket 2.6 – Befehle und Editor

- `create_command`: Filter `CylindricalFaces`, `ConicalFaces` zusätzlich;
  Beschriftung „Ebene, Fläche, Profil oder Mantelfläche". Bei Mantelfläche
  ⇒ `surface_reader` ⇒ Doc mit `development` ⇒ Editor.
- `pickFrame` (Phase 1) akzeptiert ebenfalls Mantelflächen (Create-Modus;
  im Edit-Modus nur, wenn die Skizze schon zu einer Mantelfläche gehört –
  sonst Meldung).
- Editor: Zielbeschriftung „Zylinder r = 25 mm, L = 60 mm, rundum (nahtlos)"
  bzw. „Kegelstumpf … Sektor 210°"; Vorschau zeigt die Abwicklung (bei
  Kegel den Sektor). Gruppe *Stil*: `embossOn`/`embossDepth`/Nahtwinkel
  (`development.seamAngle`, Grad, −180..180) erscheinen nur mit
  `development`. `patternAngle` ausgeblendet mit Hinweis, wenn periodisch.
  In der Vorschau eine gestrichelte **Nahtlinie** an beiden x-Rändern
  (nur Darstellung, `preview.js`, aus `scene.meta.seams`, die `build_scene`
  bei `periodic` mitschickt).

### Paket 2.7 – Doku, Version, Abnahme

- Manifest `1.7.0`, Beschreibung um „auf Zylinder- und Kegelmantelflächen
  (Abwicklung, optional Emboss)".
- README DE/EN: Abschnitt „Muster auf Zylinder und Kegel" (Ablauf, Nahtregel,
  Emboss-Checkbox, was nicht geht: Kugel/Freiform, Mauer-Versatz an der Naht,
  Kegel-Näherung falls 2.0 das ergibt), Testmatrix (Vollzylinder nahtlos mit
  jedem Muster, Halbzylinder, Kegelstumpf, schräg geschnittener Zylinder,
  Re-Edit mit Emboss, Fusion ohne Emboss-API), Bekannte Einschränkungen.
- `Context.md` 15: Spike-Ergebnisse, Messwerte (Emboss-Dauer je Lochzahl,
  Elementzuwachs Kegel-Warp), die Nahtregel, die Entscheidung Emboss-Ausnahme.
  Abschnitt 6 („Keine integrierte Extrusion") um den Satz ergänzen, dass
  Emboss die bewusste Ausnahme ist und warum (ohne Wrap gibt es keinen
  anderen Weg auf die Fläche; Extrusion dagegen ist ein Klick in Fusion).
- Galerie: ein Bild (Wabe auf Zylinder).

**Abnahme Phase 2 (in Fusion):** Vollzylinder mit Wabe: Naht nicht
erkennbar, Stegbreite an der Naht = eingestellte Dicke (nachmessen);
Voronoi auf Vollzylinder: keine Zellverzerrung, keine halbe Zelle an der Naht;
Halbzylinder: Rahmenband rundum; Kegelstumpf: Muster folgt der Verjüngung;
Emboss erzeugt **einen** Körper-Zuwachs; Re-Edit (Zellgröße ändern) ⇒ Emboss
rechnet neu; Abbruch bei Kugel mit klarer Meldung; Fusion-Version ohne
`embossFeatures` ⇒ Checkbox grau, Skizze trotzdem korrekt.

---

## Reihenfolge, Umfang, Schnitte

| Schritt | Pakete | Ergebnis |
| --- | --- | --- |
| 1 | 1.1, 1.2, 1.3 | Kern ohne Fusion, komplett getestet |
| 2 | 1.4, 1.6, 1.5 | Ende-zu-Ende in Fusion |
| 3 | 1.7 | Release 1.6.0 |
| 4 | 2.0 | Spike – entscheidet über Zuschnitt von 2.5 |
| 5 | 2.1, 2.2, 2.3 | Kern ohne Fusion (Zylinder zuerst, Kegel-Warp danach) |
| 6 | 2.4, 2.5, 2.6 | Ende-zu-Ende in Fusion |
| 7 | 2.7 | Release 1.7.0 |

Wenn im Spike 2.0 die Tangentialebene oder das Emboss-Verhalten nicht
beherrschbar ist, wird Phase 2 auf „abgewickelte Skizze auf Tangentialebene,
Emboss manuell" zugeschnitten und **trotzdem** ausgeliefert; die Entscheidung
samt Messwerten kommt in `Context.md`.

Nicht Teil dieses Plans (bewusst): Innenkonturen im Rahmen, Rahmen in der
Vorschau zeichnen, Kugel/Freiform, Mehrfachauswahl von Flächen, CustomFeature.
