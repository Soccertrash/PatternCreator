# PatternCreator – Fusion 360 Add-In: Umsetzungsplan (v2)

**Ziel:** Ein Fusion-360-Add-In (Python) mit eigenem **Editor-Fenster** (Palette mit Live-Vorschau),
das parametrische 2D-Muster in Skizzen erzeugt. Muster: technische (Gitter, Rauten, Wabe, Mauer)
und natürliche (Blattadern, Voronoi, Fischgrät, Wellen, Schuppen, Phyllotaxis/Spiralen,
Blatt-Streumuster). Zusätzlich kann **Text additiv in jedes Muster eingebettet** werden.
Alle Muster sind **extrudierbar** (geschlossene Profile) und **nachträglich bearbeitbar**.

**Zielplattform:** Fusion 360 auf macOS und Windows, Python-API (`adsk.core`, `adsk.fusion`).
Nur die eingebettete Python-Umgebung – **keine externen Pakete** (kein numpy/scipy/shapely).
Editor-UI als HTML/JS-Palette – dort ebenfalls **keine externen JS-Bibliotheken** (Vanilla JS + Canvas),
damit alles offline und ohne Build-Schritt funktioniert.

---

## 1. Leitideen (bestimmen alle Design-Entscheidungen)

1. **Extrudierbarkeit zuerst:** Jedes Muster hat zwei Ausgabemodi:
   - *Linienmodus*: reine Kurven (für Gravuren, dekorative Skizzen).
   - *Flächenmodus* (Standard): jede Kurve wird über den Parameter **Dicke** zu einem
     geschlossenen Streifen (Offset beidseitig + Endkappen), Zellen werden geschlossene
     Polygone. Ergebnis: saubere Profile, die Fusion direkt extrudieren kann.
2. **Ein Muster = ein Dokument:** Der komplette Zustand (Mustertyp, Container, alle Parameter,
   Text-Layer, Seed) ist ein einziges JSON-Objekt („PatternDoc"). Editor, Generator, Vorschau,
   Attribut-Speicherung und Re-Edit arbeiten alle nur mit diesem JSON.
3. **Geometrie getrennt von Fusion:** Generatoren erzeugen eine Fusion-freie Zwischenrepräsentation
   (IR). Dieselbe IR wird (a) im Editor-Canvas gezeichnet und (b) vom Renderer in die Skizze
   übertragen. Vorschau und Ergebnis können dadurch nicht auseinanderlaufen.

---

## 2. Projektstruktur

```
PatternCreator/
├── PatternCreator.manifest        # Add-In-Manifest (JSON)
├── PatternCreator.py              # run()/stop(): Buttons "Muster erstellen" + "Muster bearbeiten"
├── commands/
│   ├── create_command.py          # Öffnet Editor-Palette (Neuanlage)
│   ├── edit_command.py            # Auswahl bestehender Muster-Skizze -> Editor mit alten Werten
│   └── palette_bridge.py          # Messaging Palette <-> Python, Commit-Logik
├── core/
│   ├── pattern_doc.py             # PatternDoc: Schema, Defaults, Validierung, (De-)Serialisierung
│   ├── ir.py                      # Zwischenrepräsentation: Path, Polygon, Circle, Arc, TextItem
│   ├── stroker.py                 # Linien -> geschlossene Streifen (Dicke, Endkappen, Gehrung)
│   └── containers.py              # Rahmenformen + Clipping (siehe Abschnitt 5)
├── generators/
│   ├── __init__.py                # Registry: id -> Generator (inkl. UI-Schema für den Editor)
│   ├── base.py                    # Abstrakte Basisklasse
│   ├── grid.py  rhombus.py  honeycomb.py  brick.py  puzzle.py
│   ├── herringbone.py  waves.py  scales.py
│   ├── voronoi.py  organic_cells.py      # gemeinsamer Kern: Voronoi+Glättung+Anisotropie
│   ├── leaf_veins.py  pebbles.py  tissue.py  caustics.py   # bauen auf organic_cells auf
│   ├── phyllotaxis.py  spirals.py
│   └── motif_scatter.py           # Blatt-/Motiv-Streumuster
├── text/
│   └── text_layer.py              # Additive Text-Ebene inkl. Knockout (Abschnitt 7)
├── fusion/
│   ├── renderer.py                # IR -> Skizzengeometrie (isComputeDeferred, Batching)
│   ├── storage.py                 # PatternDoc <-> Fusion-Attribute an der Skizze
│   └── extrude.py                 # Optionale integrierte Extrusion (Abschnitt 8)
├── palette/
│   ├── editor.html  editor.css  editor.js   # Editor-UI (Vanilla JS)
│   └── preview.js                 # Canvas-Renderer für die IR (JSON vom Python-Backend)
├── resources/                     # Icons
├── tests/                         # pytest, ohne Fusion lauffähig (core/ + generators/ + text/)
├── README.md
├── PLAN.md
└── CHECKLIST.md
```

Manifest wie üblich (`type: addin`, `supportedOS: windows|mac`). Installation nach
`~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/` (macOS) bzw.
`%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\` (Windows); README dokumentiert beides.

---

## 3. PatternDoc – das zentrale Datenmodell

```jsonc
{
  "version": 1,
  "container": { "shape": "rect", "width": 10.0, "height": 6.0,   // cm (API-intern!)
                 "cornerRadius": 0, "sides": 6 },                  // je nach shape relevant
  "placement": { "originX": 0, "originY": 0, "rotation": 0 },
  "pattern":   { "type": "honeycomb", "params": { "cellSize": 0.8, "orientation": "flat" } },
  "style":     { "mode": "area",          // "area" (Flächen) | "lines"
                 "thickness": 0.08,       // Steg-/Strichdicke
                 "clip": "cut",           // "cut" | "dropPartial" | "off"
                 "border": true },        // Containerumriss mitzeichnen
  "textLayer": { "enabled": true, "text": "MP 2026", "font": "Arial", "height": 0.6,
                 "x": 1.0, "y": 1.0, "angle": 0, "knockout": true, "knockoutMargin": 0.1 },
  "seed": 42
}
```

- `core/pattern_doc.py` validiert gegen Defaults + Grenzen (min/max je Parameter) und liefert
  verständliche Fehlermeldungen (Feldname + erlaubter Bereich) an den Editor zurück.
- Jeder Generator deklariert sein Parameter-Schema deklarativ
  (`[{key, label, type: length|int|float|choice|bool|string, min, max, default, step}]`).
  Der Editor baut die Formulare daraus generisch – neue Muster brauchen **keine** UI-Änderung.

---

## 4. Editor (HTML-Palette) – Phase 2

**Entscheidung:** Kein nativer Command-Dialog, sondern eine `adsk.core.Palette`
(HTML/JS, dockbar, ca. 420×720). Begründung: Live-Canvas-Vorschau in < 50 ms statt langsamer
Skizzen-Neuaufbauten, echtes Undo/Redo im Editor, freie UI-Gestaltung für die Heuristiken.

**Aufbau:**
- Oben: Dropdown Mustertyp (mit kleinen Vorschau-Piktogrammen), daneben Seed + „Würfeln"-Button.
- Mitte: **Canvas-Vorschau** (zeichnet die IR, inkl. Containerumriss und Text-Layer; Zoom/Pan
  per Mausrad/Drag; Anzeige „n Konturen / m Flächen" unter dem Canvas).
- Rechts/unten einklappbare Gruppen: Container, Muster-Parameter (generisch aus Schema),
  Stil (Modus/Dicke/Clipping), Text-Layer.
- Fußzeile: `Zurücksetzen` | `Undo` | `Redo` | `Abbrechen` | `In Skizze erzeugen`.

**Datenfluss (palette_bridge.py):**
- JS -> Python: `docChanged` (debounced 150 ms) mit komplettem PatternDoc.
- Python: validieren, `generate()` ausführen, IR als JSON zurücksenden (`previewData`).
  Bei Fehlern stattdessen `validationErrors` (Feld -> Meldung); Editor markiert das Feld rot
  und zeigt die Meldung daneben (nicht nur ein globaler Fehlertext).
- Bei sehr großen Mustern (> 5000 IR-Elemente): Vorschau zeichnet vereinfachte Darstellung
  und Warnbanner „Sehr viele Elemente – Erzeugen kann dauern".
- `commit`: Python erzeugt die Skizze (Abschnitt 8), speichert Attribute, schließt/leert Palette.

**Undo/Redo im Editor:** History-Stack von PatternDoc-Snapshots im JS (max. 100 Einträge,
Push bei jeder abgeschlossenen Änderung, d. h. debounced – nicht pro Tastendruck).
Buttons + Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z. Zusätzlich gilt in Fusion selbst: ein Commit = **ein**
Timeline-Undo-Schritt.

**Nielsen-Heuristiken – konkrete Maßnahmen (im Review prüfbar):**
1. *Sichtbarkeit des Systemstatus:* Live-Vorschau; Element-Zähler; Spinner + „Erzeuge…" beim Commit.
2. *Übereinstimmung mit der realen Welt:* Deutsche Begriffe („Wabe", „Fuge", „Steg"), Einheiten
   sichtbar in mm (Umrechnung nach cm nur intern).
3. *Nutzerkontrolle:* Undo/Redo, Abbrechen ohne Seiteneffekt, „Zurücksetzen" auf Defaults je Gruppe.
4. *Konsistenz:* Alle Parameter-Gruppen gleich aufgebaut (aus dem deklarativen Schema generiert).
5. *Fehlervermeidung:* Slider/Stepper mit min/max aus dem Schema statt freier Textfelder,
   wo sinnvoll; ungültige Kombinationen werden abgefangen, bevor sie die Vorschau erreichen.
6. *Wiedererkennung statt Erinnern:* Piktogramme im Muster-Dropdown; zuletzt benutzte Werte
   werden pro Mustertyp vorgeschlagen.
7. *Flexibilität/Effizienz:* Presets pro Muster („fein/mittel/grob"), Seed-Würfeln, Tastenkürzel.
8. *Ästhetik/Minimalismus:* Nur die Parameter des aktiven Musters sichtbar, Gruppen einklappbar.
9. *Fehlerdiagnose:* Feldbezogene Meldungen in Klartext („Zellgröße muss zwischen 1 mm und 100 mm liegen").
10. *Hilfe:* „?"-Icon pro Muster mit Kurzbeschreibung + Skizze der Parameterbedeutung (statisches PNG/SVG).

---

## 5. Container (Rahmenformen) – `core/containers.py`

Formen (alle mit Maßen, Ursprung relativ zum Skizzenursprung, Rotation):
- **Rechteck** (Breite, Höhe, optional Eckenradius), **Quadrat** (Kantenlänge, Kurzform von Rechteck),
- **Kreis** (Durchmesser), **Ellipse** (Breite, Höhe),
- **Regelmäßiges Vieleck** (Seitenzahl 3–12, Umkreisdurchmesser).

Einheitliche Schnittstelle: `contains(point)`, `clip_path(path)`, `outline() -> IR`,
`bounding_rect()`. Die Generatoren füllen immer das Bounding-Rechteck; das Clipping gegen die
tatsächliche Form macht der Container zentral (Polygon-Clipping via Sutherland-Hodgman gegen die
polygonal angenäherte Containerkontur, Kreis/Ellipse mit 96 Segmenten approximiert – nur fürs
Clipping; der gezeichnete Umriss selbst ist ein echter Kreis/Ellipsenbogen).

Clipping-Optionen (`style.clip`): `cut` (Zellen am Rand beschneiden), `dropPartial`
(angeschnittene Zellen weglassen – ergibt „ausgefranste" natürliche Ränder), `off`.

**Stretch (Phase 6):** Bestehendes **Skizzenprofil oder planare Fläche als Container** wählen
(Selection im Edit-/Create-Command vor Öffnen der Palette; Profilkontur wird als Polygon
abgetastet und wie eine eingebaute Form behandelt). Das ist der Fusion-nativste Weg, Muster in
beliebige Umrisse zu legen.

---

## 6. Muster-Katalog – Phase 3/4 (Kern)

Alle Generatoren: Fusion-frei, deterministisch über `random.Random(doc.seed)`, liefern IR.
Gemeinsame Parameter überall: Dicke (aus `style`), Abstand/Zellgröße, Rotation des Musters
im Container. Musterspezifische Parameter darunter.

**Technische Muster (Phase 3 – einfach, zuerst):**
1. **Gitter** (`grid`): Linienabstand X/Y getrennt, Winkel (0° = rechtwinklig, frei drehbar).
2. **Rauten** (`rhombus`): wie Gitter, aber zwei Scharen mit Winkel ±α (Standard 60°/120°);
   Parameter Rautenbreite/-höhe.
3. **Wabe** (`honeycomb`): Zellweite, Ausrichtung (Spitze/Fläche oben). Im Flächenmodus:
   Zellen als Innen-Hexagone mit Steg = Dicke (dedupliziert, extrudierbar als Wände ODER Zellen).
4. **Mauer** (`brick`): Ziegelbreite/-höhe, Fugenbreite, Reihenversatz (1/2, 1/3, frei).

**Natürliche Muster (Phase 4) – abgeleitet aus den Beispielbildern:**
5. **Voronoi** (`voronoi`) – *Bild „Blattzellen", Grundbaustein:* Zellenzahl (max. 500), Seed,
   Lloyd-Relaxation (0–2), Zell-Inset in %. Halbebenen-Schnitt (O(n²), reines Python).
6. **Blattadern** (`leaf_veins`) – *Bild 1 (Blatt-Makro):* **zweistufiges Voronoi**:
   grobe Zellen (Hauptadern, größere Dicke) + je Zelle ein feines Sub-Voronoi (Nebenadern,
   kleinere Dicke). Parameter: Grobzellenzahl, Feinzellen pro Grobzelle, Dickenverhältnis
   Haupt-/Nebenader. Ergibt genau die hierarchische Optik des Fotos. *Stretch:* echte
   Aderbäume per Space-Colonization-Algorithmus.
7. **Fischgrät/Chevron** (`herringbone`) – *Bild 3 (Palmwedel):* parallele Rippen, die in einem
   Winkel (Standard 40°) auf eine Mittelachse zulaufen; Parameter: Rippenabstand, Winkel,
   Anzahl Mittelachsen (1 = Palmwedel, n = Parkett-/Fischgrät-Feld), Achsen-Krümmung (0 = gerade,
   > 0 = leicht gebogene Rippen wie im Foto, als Bögen).
8. **Wellen** (`waves`): Wellenlänge, Amplitude, Linienabstand, Phasenversatz/Zeile, Jitter (Seed).
   Als gefittete Splines.
9. **Schuppen** (`scales`): Schuppenbreite, Überlappung %, Reihenversatz (Bögen).
10. **Phyllotaxis** (`phyllotaxis`) – *Bild 6 (Sonnenblume):* Punkte nach Vogel-Modell
    (Goldener Winkel 137,508°, r = c·√n); jedes Element als Kreis oder kleines Polygon,
    Größe wächst optional mit dem Radius. Parameter: Elementanzahl, Skalierung c,
    Elementform (Kreis/Hexagon/Tropfen), Größenverlauf innen→außen.
11. **Spiralen** (`spirals`) – *Bild 4 (Farn-Spiralen):* logarithmische Spiralen
    (r = a·e^(b·θ)) als Splines; Parameter: Spiralanzahl, Windungen, Streuung über den
    Container (Platzierung wie Motiv-Streuung), Größenvariation, Drehrichtung gemischt.
12. **Motiv-Streuung** (`motif_scatter`) – *Bilder 2 und 5 (Blätter-Muster):* ein parametrisches
    **Blatt-Motiv** (zwei Spline-Bögen + Mittelrippe + optionale Seitenrippen; Formfaktor
    schlank↔rund) wird im Raster, versetzten Raster oder per Poisson-Disk-Streuung (Seed)
    platziert; Rotation/Größe mit Jitter. Motiv-Registry, damit später weitere Motive
    (Tropfen, Feder, Ast) ergänzbar sind. Deckt die „gezeichnete Blätter"- und die
    „organische Matisse"-Optik ab (letztere über großes Motiv + enge, rotierte Kachelung).

**Organische-Zellen-Familie** (Bilder: Kieselsteine, grüne Zellen, Zellgewebe, Wasser) –
gemeinsamer Kern `organic_cells.py`: Voronoi + **Chaikin-Eckenglättung** (0–3 Iterationen,
macht aus eckigen Zellen runde „Kiesel") + optionale **Anisotropie** (Punktdichte/Streckung in
X ≠ Y für längliche Zellen) + Inset. Darauf drei Generatoren:

13. **Kiesel/Steinzellen** (`pebbles`) – *Bilder „Steinmuster" und „grüne Zellen":* Zellenzahl,
    Fugenbreite (= Inset), Rundheit (Chaikin-Stufen), Größenstreuung, optional **Kernpunkt**
    je Zelle (kleiner Kreis, zufällig versetzt – ergibt die Zellkern-Optik; als eigenes
    extrudierbares Profil).
14. **Zellgewebe** (`tissue`) – *Bild „Gewebe-Mikroskopie":* Zellen in Reihen, in X gestreckt
    (Anisotropie-Faktor), Reihenhöhe, Zelllänge, Jitter, Rundheit. Ergibt die geschichtete
    länglich-organische Zellstruktur.
15. **Wasser-Kaustik** (`caustics`) – *Bild „Pool-Wasser":* Voronoi-Kanten als geglättete
    Splines mit Wellen-Jitter entlang der Kante und **variabler Dicke** (dünn↔dick moduliert
    per Seed); optional zweite überlagerte Netz-Ebene mit anderem Seed und kleinerer Dicke
    für die typische Mehrschicht-Lichtoptik. Parameter: Maschengröße, Unruhe (Jitter),
    Dickenvariation, zweite Ebene an/aus.

16. **Puzzle** (`puzzle`) – *Bild „Puzzleteile":* Raster X×Y; jede Innenkante bekommt eine
    klassische Puzzle-Nase (kubische Bézier-/Spline-Kontur), Richtung (rein/raus) zufällig
    per Seed, Nasengröße % und Halsbreite % einstellbar, leichter Formfaktor-Jitter.
    Primär Linienmodus (Schnittlinien, z. B. für Lasercut); im Flächenmodus sind die
    einzelnen Teile geschlossene, extrudierbare Profile.

Jedes Muster dedupliziert gemeinsame Kanten (gerundete Koordinaten als Set-Schlüssel), sonst
brechen Profile bei der Extrusion.

---

## 7. Text-Layer (additiv, in jedes Muster einbettbar)

- Unabhängige Ebene **über** dem aktiven Muster, im selben Commit, gleiche Skizze.
- Parameter: Text (mehrzeilig), Schriftart, Schrifthöhe, Position (X/Y, per Eingabe UND per
  Drag im Vorschau-Canvas verschiebbar), Winkel, optional Kreisbogen-Anordnung (Stretch).
- **Knockout-Option (Standard an):** Im Bereich der Text-Bounding-Box (+ einstellbarer Rand)
  wird das Muster ausgestanzt (Muster-Elemente, die die Box schneiden, werden geclippt bzw.
  entfernt). Dadurch bleibt der Text lesbar und beim Extrudieren entstehen keine überlappenden
  Profile aus Text + Muster. Ohne Knockout wird der Text einfach überlagert.
- Umsetzung in Fusion: `sketch.sketchTexts.createInput2(...)` (SketchText ist direkt
  extrudierbar). Für die Canvas-Vorschau genügt gerenderter Browser-Text in derselben
  Position/Größe (Hinweis im UI: „Vorschau-Schrift kann leicht abweichen").
- Mehrere Text-Layer: MVP **ein** Layer; Datenmodell als Liste anlegen (`textLayers: [...]`),
  damit mehrere später ohne Migration möglich sind.

## 8. Skizze, Extrusion & Commit – `fusion/renderer.py`, `fusion/extrude.py`

- Commit-Ablauf: neue Skizze auf gewählter Ebene/Fläche (Auswahl vor Palette-Öffnung; Standard
  XY-Ursprungsebene) → `isComputeDeferred = True` → IR zeichnen → Text-Layer → Attribute
  schreiben → `isComputeDeferred = False`. Alles innerhalb eines Commands ⇒ **ein Undo-Schritt**.
- IR-Abbildung: Linien → `sketchLines`, Bögen → `sketchArcs`, Kreise → `sketchCircles`,
  Splines → `sketchFittedSplines`, Polygone → Linienzug (geschlossen), Text → `sketchTexts`.
- **Optionale integrierte Extrusion:** Checkbox „Direkt extrudieren" + Tiefe + Richtung
  (Neuer Körper / Verbinden / Ausschneiden). Umsetzung: nach dem Zeichnen alle geschlossenen
  Profile der Skizze einsammeln (`sketch.profiles`), nach Flächenmodus-Logik filtern
  (Stege vs. Zellen: Auswahl „Stege extrudieren" oder „Zellen extrudieren") und ein
  `extrudeFeature` erzeugen. Wer manuell extrudieren will, lässt die Checkbox aus – die
  Profile sind dank Flächenmodus sauber wählbar.

## 9. Nachträgliches Bearbeiten – `fusion/storage.py`, `commands/edit_command.py`

- Beim Commit: PatternDoc-JSON als Attribut an der Skizze
  (`attributes.add('PatternCreator', 'doc', json)`; zusätzlich `version`).
- **„Muster bearbeiten"-Befehl:** Benutzer wählt eine Muster-Skizze (Selection-Filter auf
  Skizzen mit PatternCreator-Attribut; alternativ Liste aller Muster-Skizzen im Dokument zur
  Auswahl anzeigen). Editor öffnet mit gespeicherten Werten. Beim erneuten Commit werden alle
  von PatternCreator erzeugten Kurven der Skizze gelöscht und neu erzeugt (die Skizze selbst
  und ihre Timeline-Position bleiben erhalten, damit abhängige Features – z. B. eine bestehende
  Extrusion – neu berechnet werden statt zu verwaisen).
- Grenzen dokumentieren: Wenn der Benutzer die erzeugte Geometrie manuell verändert hat, gehen
  diese Änderungen beim Re-Generate verloren → Warnhinweis vor dem Überschreiben.
- **Stretch (Phase 6):** `CustomFeature`-API – Muster als eigener Timeline-Eintrag mit
  Doppelklick-Edit und automatischem Recompute. Erst angehen, wenn alles andere stabil ist.

---

## 10. Tests & Doku – Phase 5

- `pytest tests/` ohne Fusion lauffähig (nichts unter `core/`, `generators/`, `text/` importiert `adsk`):
  Clipping-Randfälle (alle Containerformen), Stroker (Dicke, Gehrung, geschlossene Ergebnisse),
  Kanten-Deduplizierung, Seed-Determinismus jedes Generators, Parametervalidierung,
  PatternDoc-Roundtrip (serialize → parse → identisch), Knockout entfernt schneidende Elemente.
- Manuelle Testmatrix im README: jedes Muster mit Defaults + Extremwerten; Re-Edit-Zyklus
  (erzeugen → extrudieren → bearbeiten → Extrusion rechnet neu); Undo/Redo im Editor und in Fusion.
- Entity-Schutz: ab > 2000 Skizzen-Entities Warnung mit Abbruch-Option vor dem Commit.
- README: Installation, Bedienung mit Screenshots-Platzhaltern, Parameter-Referenz je Muster,
  bekannte Einschränkungen (max. 500 Voronoi-Zellen, ein Text-Layer, Knockout über Bounding-Box,
  Vorschau-Schrift ≈ Fusion-Schrift).

---

## 11. Umsetzungsreihenfolge für Opus 5

1. **Phase 1 – Gerüst:** Manifest, run/stop, zwei Buttons, leere Palette öffnet/schließt sauber,
   Messaging Palette↔Python steht (Echo-Test).
2. **Phase 2 – Editor-Kern:** PatternDoc + Validierung, generischer Formular-Builder aus
   Parameter-Schemata, Canvas-Vorschau der IR, Undo/Redo, Container Rechteck.
3. **Phase 3 – Erste Muster Ende-zu-Ende:** Stroker, Renderer, Commit mit Attributen;
   Muster: Gitter, Rauten, Wabe, Mauer, Puzzle. Ab hier ist das Add-In benutzbar.
4. **Phase 4 – Natürliche Muster + Text:** Voronoi → organische Zellen-Familie
   (Kiesel, Zellgewebe, Wasser-Kaustik) → Blattadern → Fischgrät → Wellen → Schuppen →
   Phyllotaxis → Spiralen → Motiv-Streuung; alle Containerformen; Text-Layer mit
   Knockout; integrierte Extrusion.
5. **Phase 5 – Re-Edit + Qualität:** edit_command, Re-Generate-Logik, Tests, Entity-Schutz,
   Presets, Hilfe-Icons, README, Icons.
6. **Phase 6 (Stretch, nur nach Freigabe):** Profil/Fläche als Container, CustomFeature,
   Text auf Kreisbogen, mehrere Text-Layer, Space-Colonization-Blattadern.

Jede Phase als eigener Git-Commit. **Definition of Done:** alle Pflichtpunkte in `CHECKLIST.md`
erfüllt, `pytest` grün, manuelle Testmatrix in Fusion dokumentiert.

---

## 12. Bekannte Fallstricke

- Event-Handler-Referenzen global halten (GC), auch die Palette-HTML-Event-Handler.
- API-interne Längeneinheit ist **cm**; Editor zeigt mm – Umrechnung nur an der Grenze Editor↔Doc.
- `isComputeDeferred` immer in `try/finally` zurücksetzen.
- `random` nie global seeden; ausschließlich `random.Random(doc.seed)`-Instanzen ⇒ Vorschau,
  Commit und Re-Edit erzeugen identische Muster.
- Palette-Messaging ist asynchron: Antworten über `sendInfoToHTML`, eingehende Events über
  `HTMLEventHandler`; Request-IDs mitführen, damit veraltete Vorschau-Antworten (Race bei
  schnellen Änderungen) verworfen werden.
- Doppelte Kanten oder sich schneidende Streifen zerstören Profile → Deduplizierung und
  Knockout sind Pflicht, nicht Kosmetik.
- SketchText-Schriftarten unterscheiden sich zwischen macOS/Windows → Fallback auf „Arial"
  und Fehlermeldung statt Absturz bei unbekannter Schrift.
- Palette-HTML wird von Fusion gecacht → beim Entwickeln Version-Query an die URL hängen.
