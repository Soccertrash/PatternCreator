# PatternCreator – Umsetzungsplan: Verbinder für Streu-Muster + Skizzenelement-Optimierer

**Für:** Umsetzung durch Opus 5. Dieser Plan ist das Ergebnis einer Code-Analyse und
Recherche (Stand 2026-08-20) und enthält alle nötigen Code-Referenzen.

**Zwei Features:**

1. **Verbinder (Feature A):** Phyllotaxis und Motiv-Streuung erzeugen im Flächenmodus
   isolierte Inseln (jeder Kreisring, jede Blattkontur, jede Blattader ist ein eigener
   schwebender Körper) und sind daher nicht 3D-druckbar. Neue Verbinder-Stege verbinden
   alle Motive untereinander und mit dem Rahmen.
2. **Optimierer (Feature B):** Muster erzeugen bis zu 2000+ Skizzenelemente
   (Warnung `ENTITY_WARN_LIMIT` in `core/build.py:36`). Ein neuer Optimierer-Pass
   reduziert die Elementzahl deutlich, ohne die sichtbare Geometrie zu verändern.

**Vom Nutzer bereits entschieden:**

- Verbinder: neuer Stil-Parameter (Checkbox), bei Streu-Mustern **standardmäßig AN**.
- Steg-Layout: **Nachbar-Netz** (Spannbaum zum jeweils nächsten Nachbarn) **+ Verankerung
  im Rahmen** für randnahe Motive.
- Optimierer: **alle Stufen** (verlustfreie Bereinigung + Kreis-Refit + toleranzbasierte
  Vereinfachung/Spline-Umwandlung) mit **fester Toleranz 0,02 mm**, kein UI-Parameter.

**Leitplanken (gelten für beide Features):**

- Reines Python, keine externen Pakete (weder numpy/scipy/shapely noch JS-Libs) –
  wie in `PLAN.md` und `tests/test_architecture.py:44-56` festgeschrieben.
- Deterministisch: gleicher Seed + gleiche Parameter ⇒ identische Geometrie.
- Vorschau und Fusion-Ausgabe laufen beide durch `core/build.build_scene()`
  (`commands/palette_bridge.py:183` und `:261`) – **alles Neue muss vor der
  Scene-Erzeugung passieren**, damit beide nie auseinanderlaufen (Invariante aus
  `core/ir.py:3-5`). Nichts im Renderer „nachbessern".
- `core/` und `generators/` dürfen kein `adsk` importieren.

---

## Feature A: Verbinder für Streu-Muster

### A.1 Ist-Zustand (Analyse)

- Es gibt **keinen** bestehenden Verbinder-Mechanismus. Kachel-Muster (`tiling = True`)
  sind über das Ein-Flächen-Modell verbunden: `as_face`-Gate in `core/build.py:85-86`,
  `_to_face` in `core/build.py:453-489` (Rahmen minus geschrumpfte Zellen ⇒ Stegnetz
  ist konstruktionsbedingt zusammenhängend).
- Phyllotaxis (`generators/phyllotaxis.py:40-62`) und Motiv-Streuung
  (`generators/motif_scatter.py:93-121`) sind **nicht** `tiling` und laufen durch
  `_to_areas` (`core/build.py:318-363`):
  - Kreis/Sechseck/Tropfen ⇒ Annulus (Außen- + Innenring, `build.py:340-344`) bzw.
    bei `fillTarget="cells"` gefüllte Scheibe (`build.py:326-338`).
  - Blattkontur ⇒ Spline-Annulus; Mittelrippe und Seitenrippen (`ROLE_EDGE`) werden
    einzeln zu eigenen geschlossenen Ringen gestrokt (`build.py:345-349`).
  - Ergebnis nach Extrusion: **N unabhängige Körper** (README.md:316-318 nennt das
    als bekannte Einschränkung).
- **Vorlage im Code:** Die Schraffur verankert ihre Stege, indem jede Mittellinie an
  beiden Enden um `web_half = max(thickness, own_gap)/2` ins umgebende Netz verlängert
  wird: `core/hatch.py:148-156` (`_extended`) und `:198`, aufgerufen mit `web_half`
  aus `core/build.py:109`. Überlappende geschlossene Profile werden beim Extrudieren
  zu einem Körper – genau diese Idiomatik übernehmen die Verbinder.

### A.2 Datenmodell & UI

Neue Stil-Parameter in `STYLE_PARAMS` (`core/pattern_doc.py:123-184`), nach dem Muster
von `HATCH_ON` (`pattern_doc.py:121`):

- `connectors` (T_BOOL, Label **„Verbinder"**, Default `True`,
  `visible_if={"mode": ["area"]}`, Hilfetext: „Verbindet frei stehende Motive
  untereinander und mit dem Rahmen, damit das Muster als ein Teil druckbar ist.").
- `connectorWidth` (T_LENGTH, Label **„Verbinder-Dicke"**, Default `0.08` cm = 0,8 mm,
  min 0.02, max 1.0, step 0.01, `visible_if={"mode": ["area"], "connectors": [true]}`).

Sichtbarkeit: Die beiden Parameter nur bei Generatoren anzeigen, die sie brauchen.
Dafür ein neues Klassen-Flag in `generators/base.py` (analog `tiling`, base.py:61):
`scatter: bool = False`; `phyllotaxis.py` und `motif_scatter.py` setzen `scatter = True`.
`core/build.py` wertet `connectors` nur aus, wenn `getattr(gen, "scatter", False)`.
Die Palette braucht dafür keine Sonderlogik, wenn die Sichtbarkeit serverseitig über
das Schema gelöst wird (Parameter bei Nicht-Streu-Mustern aus dem Stil-Schema filtern,
analog zur `fill_targets`-Klemmung in `build.py:64-66` / `palette/editor.js:309-312`).

Kein neuer Generator-Parameter nötig – das Feature ist Stil-/Pipeline-Ebene und wirkt
damit automatisch für **beide** Streu-Muster (und künftige).

### A.3 Geometrie-Algorithmus (neues Modul `core/connect.py`)

Einstiegspunkt: in `build_scene`, an der Stelle, an der auch die Schraffur eingefügt
wird (`core/build.py:102-111` bzw. `:119-127`) – **nach** Clipping und `_to_areas`,
**vor** der Scene-Erzeugung. Signatur sinngemäß:

```python
def connector_areas(groups, frame_inner, width, web_half) -> list[ir.Path]:
    """Liefert geschlossene ROLE_REGION-Ringe (LAYER_PATTERN) für die Verbinder-Stege."""
```

**Schritt 1 – Motiv-Gruppen bilden.** `ir.Path`/`ir.Circle` bekommen ein optionales
Feld `group: int | None` (in `core/ir.py`, Default `None`, mit durch `to_dict`/
Serialisierung gereicht, aber von der Vorschau ignorierbar). Die Generatoren setzen
pro Motiv eine Gruppen-ID:

- `phyllotaxis.py`: eine ID pro Index `n` (Kreis/Sechseck/Tropfen, `phyllotaxis.py:54-61`).
- `motif_scatter.py`: eine ID pro Position – Kontur **und** alle Rippen desselben
  Blatts teilen die ID (`motif_scatter.py:111-120`).

`_to_areas` und `_clip_elements` müssen die Gruppen-ID auf die erzeugten Flächenringe
durchreichen (beim Strokern/Clippen geht sie sonst verloren).

**Schritt 2 – Innere Verschweißung pro Gruppe (Motiv-Streuung).** Die Rippen enden
heute frei im Blattinneren bzw. an der Kontur, ohne garantiert zu überlappen. Vor dem
Strokern jede offene `ROLE_EDGE`-Rippe an beiden Enden um `web_half` verlängern –
exakt das `_extended`-Idiom aus `core/hatch.py:148-156`. Damit überlappen Rippen die
Mittelrippe bzw. den Konturring und das Blatt wird **ein** Körper. (Nur für Elemente
mit Gruppen-ID; bestehende Muster bleiben unberührt.)

**Schritt 3 – Ankerpunkte je Gruppe.** Pro Gruppe: Punktwolke aller Ringpunkte
(nach Clipping), daraus Zentroid + Umriss. Für die Steg-Endpunkte reicht: Schnittpunkt
der Verbindungsgeraden Zentroid-A → Zentroid-B mit dem jeweiligen Gruppen-Umriss
(nächstliegender Ringpunkt genügt bei den kleinen Motiven; kein exakter
Polygonschnitt nötig).

**Schritt 4 – Spannbaum (Nachbar-Netz).** Deterministischer minimaler Spannbaum über
die Gruppen-Zentroiden (Prim, Start bei der Gruppe mit kleinster ID; Distanz-Ties über
Gruppen-ID brechen ⇒ deterministisch, kein RNG nötig). Reines Python, O(k²) ist bei
≤ 500 Motiven (`MAX_CELLS`/`max_points`-Kappen) unkritisch.

**Schritt 5 – Rahmen-Verankerung.** Wenn `border` an (`pattern_doc.py:136-139`):
für jede Gruppe den Abstand zum inneren Rahmenrand (`container.shrunk(borderWidth)`,
vgl. `core/build.py:445-450`) bestimmen; **mindestens 2** Anker-Stege setzen (die zwei
rahmennächsten Gruppen, möglichst auf gegenüberliegenden Seiten – z. B. beste Gruppe
pro Rahmenquadrant wählen und die zwei kürzesten nehmen), zusätzlich jede Gruppe
anbinden, deren Rahmenabstand kleiner ist als ihr kürzester Spannbaum-Steg. Wenn
`border` aus: nur Spannbaum (Muster ist dann **ein** zusammenhängender Körper) und
Szenen-Warnung ergänzen („Ohne Rahmen bleibt das Muster ein loses Einzelteil" –
Warnmechanismus wie `core/build.py:154-156`).

**Schritt 6 – Stege ausformen.** Jede Steg-Mittellinie an beiden Enden um
`max(width, thickness)/2` in die Motive hinein verlängern (Schritt-2-Idiom, damit
sicher Überlappung entsteht), dann mit `core/stroker.stroke()` (`stroker.py:128-134`)
zur geschlossenen Fläche mit Breite `connectorWidth` strokern ⇒ `ROLE_REGION`,
`LAYER_PATTERN`. Stege gegen den Container clippen (wie alles andere).

**Kanten-/Sonderfälle:**

- `fillTarget="cells"` (gefüllte Scheiben): identisch – Stege überlappen die Scheiben.
- Vom Clipping zerteilte Motive: Gruppen nach dem Clipping bilden (ein Motiv kann in
  mehrere Teilstücke zerfallen ⇒ jedes Teilstück als eigene Gruppe behandeln, sonst
  bleiben Splitter unverbunden). Winzige Splitter unterhalb der Sliver-Schwelle
  verwerfen (Idiom `_is_sliver`, `core/build.py:431-442`).
- Text-Knockout: Stege, die durch eine Knockout-Zone laufen würden, wie alle Flächen
  vom Knockout ausstanzen lassen (läuft automatisch, wenn die Stege vor dem
  Text-Layer-Schritt eingefügt werden – Reihenfolge in `build_scene` prüfen). Falls
  ein Knockout einen Steg durchtrennt und dadurch eine Gruppe wieder isoliert, ist das
  für v1 akzeptiert (Warnung genügt nicht zwingend; im Plan als bekannte Grenze
  dokumentieren, README „Einschränkungen").
- Linienmodus (`mode="lines"`): keine Verbinder (nichts wird extrudiert).

### A.4 Tests (Feature A)

Neue Datei `tests/test_connectors.py`, ohne Fusion lauffähig (wie `tests/test_face_mode.py`):

1. Phyllotaxis, Flächenmodus, Verbinder an: Union-Find über alle Flächenringe mit
   „überlappt/berührt"-Relation ⇒ **genau eine** Zusammenhangskomponente (inkl.
   Rahmenband bei `border=True`).
2. Motiv-Streuung: dito; zusätzlich pro Blatt: Rippenringe überlappen Konturring.
3. Verbinder aus ⇒ Szene identisch zum heutigen Stand (Regressionsschutz).
4. Determinismus: zwei Builds mit gleichem Doc ⇒ identische Steg-Geometrie.
5. `border=False` ⇒ eine Komponente + Warnung vorhanden.
6. Steg-Breite = `connectorWidth` (Messung wie `tests/test_face_mode.py:114-125`).
7. Clip-Fall: Motiv ragt über den Rand ⇒ kein unverbundenes Teilstück.

---

## Feature B: Skizzenelement-Optimierer

### B.1 Ist-Zustand (Analyse)

- Schätzung + Warnung: `entity_estimate` in `core/build.py:492-504` (Spline = 1,
  geschlossene Linien-Pfade = n, offene = n−1, Kreis/Bogen/Ellipse/Text = 1);
  Schwellen `ENTITY_WARN_LIMIT = 2000` (`build.py:36`), Meldungen in
  `palette/editor.js:540-542` und `commands/palette_bridge.py:262-271`.
- Haupt-Kostentreiber:
  - **Stroker**: aus jeder n-Punkt-Linie werden ~2n Skizzenlinien
    (`core/stroker.py:88-125`).
  - **Beschnittene Kreise** werden zu 48-Eck-Polygonen ⇒ 48 Linien
    (`core/build.py:221-257`, `_circle_to_points` mit `segments=48`, `build.py:215-218`).
  - **Puzzle**: ~60–70 Punkte pro Zelle (`generators/puzzle.py:100-166`).
  - **Abgerundete Voronoi-Zellen**: +5 Punkte pro Ecke (`organic_cells.py:172-216`).
  - **Schraffur**: 4 Linien pro Streifen (`core/hatch.py:174-217`).
- Vorhandene, aber unvollständige Bereinigung: `snap_segments`/`chain_segments`
  (`core/geom.py:208-290`, nur Stege-Pfad), `clean_polygon` (`geom.py:384-405`,
  Toleranz nur 1e-9, nicht auf Stroker-/Schraffur-/Clip-Ausgabe angewandt),
  `dedupe_segments` (`geom.py:192-205`, **nirgends aufgerufen**).
- Kein RDP, kein Kreis-/Bogen-Refit, keine Spline-Umwandlung vorhanden.

### B.2 Architektur

Neues Modul **`core/optimize.py`** mit einer Funktion
`optimize(elements: list) -> list`, eingehängt in `build_scene` **unmittelbar vor**
der Scene-Erzeugung (`core/build.py:153`, nach `_place_element`):

```python
scene = ir.Scene(elements=optimize(elements), warnings=warnings)
```

Damit gilt der Optimierer automatisch für **alle** Muster, die Vorschau zeigt die
optimierte Geometrie, und `entity_estimate` sowie die 2000er-Warnung messen den
optimierten Stand – ohne weitere Änderungen an Palette oder Bridge.

Feste Toleranz als Modul-Konstante: `TOL = 0.002` (cm, = 0,02 mm – maximale
Abweichung der optimierten von der ursprünglichen Kontur, weit unter FDM-Auflösung).

### B.3 Pässe (in dieser Reihenfolge)

**Pass 1 – Exakte Bereinigung (verlustfrei):**

- Aufeinanderfolgende (nahezu) identische Punkte entfernen (Idiom
  `stroker._clean`, `stroker.py:26-33`, auf alle Pfade anwenden).
- Exakt kollineare Folgen zusammenfassen: Punkt B fällt weg, wenn
  cross(B−A, C−B) ≈ 0 **und** dot > 0 (nie über Richtungsumkehr mergen).
  Größter Gewinn bei Stroker-Ringen und Schraffur-Rechtecken; O(n), risikofrei.
- Doppelte Elemente entfernen (identische Ringe nach Quantisierung auf 1e-4,
  Idiom `dedupe_segments`/`snap_segments`).

**Pass 2 – Kreis-Refit:** Geschlossener Linien-Pfad, dessen Punkte alle im Abstand
r ± TOL um den Zentroid liegen und den Vollwinkel gleichmäßig abdecken ⇒ durch
`ir.Circle` ersetzen (n Linien → 1 Element). Trifft die 48-Eck-Reste aus dem
Clipping-Fallback nicht (die sind nicht mehr geschlossen rund), wohl aber ungeklippte
tessellierte Kreise, falls solche in der Pipeline entstehen.

**Pass 3 – Bogen-Refit für offene Pfade:** Offener Pfad, dessen Punkte auf einem
Kreisbogen liegen (Kreis-Fit nach Kåsa: geschlossene 3×3-Lösung, reines Python;
radiale Abweichung aller Punkte **und** der Sehnen-Mittelpunkte < TOL) ⇒ `ir.Arc`
(`ir.py:72-92`, Renderer nutzt `addByCenterStartSweep`, `renderer.py:129-136`).
Wichtig für geklippte Kreise: `_clip_elements` so ändern, dass ein geklippter Kreis
nicht als 48-Eck-Polygon (`build.py:237-245`), sondern als **Bogen + Schließkante**
bzw. – wenn das Ring-Modell es erfordert – als Pfad weitergereicht wird, den Pass 3
wieder zu Bogen-Elementen zusammensetzen kann. Minimalziel: geklippter Kreis kostet
danach ≤ ~5 Elemente statt 48.

**Pass 4 – RDP-Vereinfachung (toleranzbasiert):** Ramer–Douglas–Peucker mit ε = TOL
auf allen verbleibenden Linien-Pfaden.

- Geschlossene Pfade: Anker = Punkt 0 und der davon entfernteste Punkt (deterministische
  Ankerregel), beide Hälften einzeln vereinfachen.
- **Selbstschnitt-Wächter:** Nach der Vereinfachung Segment-Schnitt-Test des Rings
  (Idiom `remove_loops`/Schnitttest aus `core/geom.py:422-453`); bei neuem
  Selbstschnitt den Pfad unvereinfacht lassen (Fallback, kein Halbieren-Retry nötig).
- Erwartung laut Recherche: 50–90 % Punktersparnis auf tessellierten organischen
  Konturen bei unsichtbarer Toleranz.

**Pass 5 – Spline-Umwandlung für glatte, dichte Konturen:** Pfade, die nach Pass 4
immer noch ≥ 12 Punkte haben **und** glatt sind (max. Knickwinkel zwischen
Folgesegmenten < ~30°) ⇒ `curve="spline"` setzen (Renderer: 1 fitted Spline,
`renderer.py:106-113`; Schätzer zählt 1, `build.py:497-499`). Trifft v. a.
Puzzle-Zellringe (~65 Punkte → 1) und abgerundete Organik-Zellen.
Pfade mit Ecken **nicht** umwandeln (Fitted Splines überschwingen an Knicken).
Hinweis Vorschau-Parität: `palette/preview.js:137-143` zeichnet Splines als
Quadratik-Näherung – Sichtprüfung Puzzle/Kiesel, ob die Näherung nahe genug ist;
falls nötig Vorschau-Zeichnung der Splines auf Catmull-Rom (`geom.py:501-528`)
umstellen (nur Canvas-Darstellung, keine Geometrieänderung).

**Ausnahmen/Schutz:** Elemente des Text-Layers und `ROLE_DECOR` unangetastet lassen;
`ROLE_FACE`/`ROLE_HOLE` durchlaufen die Pässe 1–5 normal (die Löcher sind unabhängige
Ringe, Schweißnähte existieren auf Scene-Ebene nicht mehr – Verbindung entsteht durch
Überlappung, nicht durch gemeinsame Punkte, daher ist RDP hier sicher).

### B.4 Flankierende Renderer-Maßnahmen (klein, aber wirksam)

- `clear_pattern_geometry` (`fusion/renderer.py:33-56`) löscht beim Re-Edit Element
  für Element **ohne** `isComputeDeferred` – in denselben
  `isComputeDeferred = True`-Rahmen wie `render_scene` (`renderer.py:59-97`) packen.
- In `render_scene` zusätzlich `sketch.arePointsShown = False` während des Aufbaus
  setzen (analog `areProfilesShown`, `renderer.py:63`).
- Keine weiteren Renderer-Eingriffe: Es gibt keine Batch-API in Fusion; weniger
  Elemente ist der einzige Hebel für weniger API-Roundtrips.

### B.5 Tests (Feature B)

Neue Datei `tests/test_optimize.py`:

1. **Fidelity:** Für jedes Muster der Registry (Default-Parameter, Seed 42):
   maximale Abweichung optimierte ↔ unoptimierte Kontur < TOL (Punkt-zu-Segment-
   Abstand, beidseitig gesampelt).
2. **Reduktion:** `entity_estimate` optimiert ≤ unoptimiert für alle Muster;
   konkrete Mindestersparnis für die bekannten Treiber festschreiben
   (z. B. Puzzle ≥ 80 %, Motiv-Streuung ≥ 50 %, geklippter Phyllotaxis-Kreis ≤ 5
   Elemente statt 48).
3. **Gültigkeit:** Kein Ring wird durch die Optimierung selbstschneidend; Anzahl
   geschlossener Konturen (Flächen) bleibt gleich; `ROLE_FACE`/`ROLE_HOLE`-Struktur
   der Kachel-Muster bleibt erhalten (Erweiterung von `tests/test_face_mode.py`).
4. **Determinismus:** Doppelbuild ⇒ identische Szene.
5. **Idempotenz:** `optimize(optimize(x)) == optimize(x)` (verhindert Drift bei
   Re-Edit-Zyklen).
6. **Kreis-/Bogen-Refit:** synthetischer 48-Eck-Kreis ⇒ `ir.Circle`; 24-Punkt-
   Bogenpolylinie ⇒ `ir.Arc` mit korrektem Zentrum/Radius/Winkeln.
7. **Zusammenspiel mit Feature A:** Verbinder-Szenen bleiben nach Optimierung eine
   Zusammenhangskomponente.

---

## Reihenfolge & Meilensteine

1. **B zuerst, Pass 1** (exakte Bereinigung + Renderer-Flankierung): risikofrei,
   sofort messbarer Gewinn, schafft die Test-Infrastruktur (Fidelity-Harness).
2. **B Pass 2–4** (Kreis-/Bogen-Refit, Clip-Pfad-Umbau, RDP mit Wächter).
3. **B Pass 5** (Spline-Umwandlung) inkl. Vorschau-Paritätsprüfung.
4. **A** (Verbinder): IR-Gruppenfeld, Generator-Tagging, `core/connect.py`,
   Stil-Parameter, Tests.
5. README aktualisieren: Abschnitt „Verbinder" (Parameter-Referenz + Grundbegriffe),
   Einschränkungs-Absatz README.md:316-318 anpassen (Streu-Muster jetzt druckbar),
   bekannte Grenze Text-Knockout ↔ Verbinder dokumentieren. Version bumpen,
   `CHECKLIST.md` ergänzen.

**Akzeptanzkriterien (Screenshot-Referenzfälle):**

- Phyllotaxis, Seed 42 (heute 441 Konturen / ~1039 Elemente): Verbinder an ⇒ eine
  Zusammenhangskomponente; Elementzahl trotz zusätzlicher Stege **unter** dem
  heutigen Wert (Optimierer kompensiert die Stege).
- Motiv-Streuung, Seed 42 (heute ~2146 Elemente ⇒ Warnung): nach Optimierung
  **deutlich unter 2000**, keine Warnung mehr; ein zusammenhängender Körper.
- Alle bestehenden Tests grün; `tests/test_face_mode.py` unverändert bestehen.

## Nicht-Ziele

- Kein Grundplatten-Feature (die README-„Stufe 2"-Idee einer echten Polygon-Union
  bleibt offen).
- Keine gemischten Linie/Bogen-Pfade in der IR (Composite-Paths) – Spline-Umwandlung
  deckt den Nutzen mit deutlich weniger Umbau ab.
- Kein UI-Regler für die Optimierer-Toleranz.
- Biarc-Fitting (G1-stetige Bogenpaare) bewusst verworfen: greedy Bogen-Refit +
  Splines liefern fast denselben Gewinn bei einem Bruchteil der Komplexität.

---

## Nachtrag (2026-08-20): Konsequenzen aus den Umsetzungs-Findings

Die Abweichungen der Umsetzung vom Plan sind in
`PLAN-VERBINDER-OPTIMIERER-findings.md` dokumentiert und wurden gegen den Code
und per Messung verifiziert (627 Tests grün; Elementzahlen, Inselzahlen und
Selbstschnitt-Zählungen reproduzieren exakt). Ergebnis der Prüfung: **alle
Findings treffen zu.** Insbesondere:

- `stroke_open`/`stroke_closed` (`core/stroker.py:88-125`) haben – anders als
  `_shrink_cell` (`core/build.py:439`) – kein `remove_loops`; die gemeldeten
  selbstschneidenden Strok-Profile existieren (Phyllotaxis Default: 10 Ringe).
- Pass 5 läuft vor Pass 4, es greift nur einer von beiden
  (`core/optimize.py:90-93`); die additive Toleranzschranke
  (radialer Fehler + Bogenhöhe ≤ TOL) ist umgesetzt (`optimize.py:270`, `:296`).
- Der Insel-Ansatz ersetzt die Gruppen-IDs (`core/connect.islands`); die
  IR-Felder aus A.3 Schritt 1 existieren nicht und werden nicht gebraucht.

Daraus ergeben sich Korrekturen am Plan und vier neue Meilensteine.

### Korrekturen am bestehenden Plan

Diese Punkte des Planoriginals sind durch die Findings **überholt** und gelten
in der ursprünglichen Form nicht mehr:

1. **A.3 Schritt 1 (Gruppen-IDs in der IR) und Schritt 2 (Rippen verschweißen):
   entfallen.** Die Gruppen werden aus der fertigen Geometrie abgeleitet
   (Findings §10); die Blattrippen überlappen die Kontur bereits.
2. **B.3 Pass 3, Clip-Umbau („Bogen + Schließkante", ≤ 5 Elemente):
   entfällt.** Das 48-Eck erreicht die Szene nicht (der gestrokte Ring hat
   25–35 Punkte), und Bogen-Elemente passen nicht in die Segment-Verkettung
   von `_to_areas` (Findings §4). Ein bogenfähiger Stroker wäre der einzige
   Weg und ist explizit **Nicht-Ziel** dieser Version (siehe Meilenstein 9).
3. **Akzeptanzkriterien (korrigiert auf gemessene Wirklichkeit):**
   - Phyllotaxis, Seed 42: „Elementzahl mit Verbindern unter 1039" ist
     arithmetisch unmöglich (219 Stege × 4 = mindestens +876, Findings §10).
     Neues Kriterium: **ein** Körper und Elementzahl **unter der
     2000er-Warnschwelle** – erfüllt mit 1673.
   - Motiv-Streuung, Seed 42: Ausgangswert ist 1498 (nicht ~2146). Kriterium
     erfüllt: 1307 mit Verbindern, ein Körper, keine Warnung.
   - „Puzzle ≥ 80 %, Motiv-Streuung ≥ 50 %": **ersatzlos gestrichen.** Beide
     Marken hängen an Pass 5, und der kann die Toleranz 0,02 mm prinzipiell
     nicht halten (Bogenhöhen-Argument, Findings §9); die Puzzle-Ringe haben
     zudem Knicke von 106–127° und sind damit kein Spline-Kandidat.

### Meilenstein 6 – Stroker-Fix: keine selbstschneidenden Profile (Bestandsfehler)

Der wichtigste offene Punkt (Findings §7): der Gehrungs-Offset legt an
Beschnittkanten Schleifen an, und die Strok-Ringe erreichen Fusion
unbereinigt. Betroffen sind genau die Motive, die die Verbinder anbinden –
der Fix gehört deshalb **vor** die Fusion-Abnahme von Feature A (G4).

1. `remove_loops` (`core/geom.py:422`) auf die Stroker-Ausgabe anwenden: in
   `stroke_open` auf den fertigen Ring (nach dem `_clean` in
   `stroker.py:98`), in `stroke_closed` auf Außen- und Innenring (vor den
   Flächen-Gates `stroker.py:118-124`). Die bestehenden Gates (≥ 3 Punkte,
   |Fläche| > 1e-10) fangen kollabierte Ergebnisse ab.
   - Kosten: `remove_loops` ist O(n²) je Durchlauf, die Ringe haben 25–70
     Punkte – vernachlässigbar. Schraffur-Streifen und Verbinder-Stege sind
     4-Punkt-Rechtecke, dort ist der Aufruf ein No-op.
2. **Wechselwirkung mit dem Wächter beachten:** Nach dem Fix sind weniger
   Originalkonturen selbstschneidend, der relative Selbstschnitt-Wächter
   (`core/optimize.py:401`) wird dadurch strenger. Elementzahlen können sich
   leicht verschieben ⇒ Messtabellen in den Findings (§1) nachziehen.
3. Tests (`tests/test_optimize.py` oder neue Datei):
   - Für die bekannten Treffer (Phyllotaxis/Motiv-Streuung Default;
     `tissue`/`leaf_veins`/`puzzle`/`pebbles` mit `border=False` und
     `clip=off`): **kein** geschlossener Musterlayer-Ring der Szene ist
     selbstschneidend (Prüfung mit `_self_intersects`).
   - Konturzahl-Invariante: Anzahl geschlossener Konturen bleibt gleich;
     kollabiert ein Ring vollständig, muss das ein bewusster, dokumentierter
     Fall sein (Sliver), kein stiller Verlust.
   - Fidelity-Harness bleibt grün: die entfernte Schleife *ist* der Fehler,
     außerhalb der Schleifenzone darf sich nichts bewegen.
4. Danach den Nebenbefund in den Findings (§7) und den offenen Punkt (§14)
   als erledigt markieren.

### Meilenstein 7 – Pass-5-Entscheidung: Spline-Glättung als bewusste Glättung

Pass 5 wandelt bei TOL = 0,02 mm nichts um und kann es prinzipiell nicht
(Findings §9). Es gibt zwei saubere Wege.

**Vom Nutzer entschieden (2026-08-20): Option A.** Option B bleibt nur als
verworfene Alternative dokumentiert.

- **Option A (empfohlen): Spline-Entscheidung beim Generator belassen,
  Pass 5 bleibt schlafende Absicherung.**
  Der Generator weiß, ob eine Punktfolge eine abgetastete glatte Kurve ist –
  und sagt es heute schon (`motif_scatter`, `scales`, `waves`, `spirals`,
  `herringbone` liefern `curve="spline"`). Konkreter Schritt: prüfen, ob
  `organic_cells` (Kiesel/abgerundete Ecken, +5 Punkte je Ecke) seine
  gerundeten Konturen generatorseitig als Spline liefern kann, ohne die
  Rundungs-Geometrie sichtbar zu verändern. Puzzle bleibt außen vor (die
  Ringe *sind* Ecken). Pass 5 selbst bleibt unverändert im Code – er greift,
  sobald ein künftiger Generator dichte glatte Linienzüge liefert.
  Kein UI, keine neue Toleranz, das Fidelity-Kriterium bleibt widerspruchsfrei.
- **Option B (nur auf ausdrücklichen Nutzerwunsch): eigene
  Glättungs-Toleranz für Pass 5.**
  Z. B. 0,1 mm bei Knick-Gate 30° ⇒ −12,6 % statt −9,9 % (Tabelle Findings
  §9). Das ist dann erklärtermaßen **Glättung**, keine toleranztreue
  Optimierung: der Fidelity-Harness braucht ein getrenntes Budget für
  Spline-Konturen, README/CHECKLIST müssen die Glättung nennen, und eine
  Sichtprüfung in Fusion (G5) ist Pflicht. Stellschrauben existieren bereits
  (`MIN_SPLINE_POINTS`, `MAX_SPLINE_KINK`, Budget-Parameter von
  `_to_spline`).

Die gestrichenen Reduktionsmarken (siehe Korrekturen, Punkt 3) kehren in
keinem Fall zurück.

### Meilenstein 8 – Vorschau-Performance der Verbinder (optional)

0,135 s je Phyllotaxis-Aufbau sind vertretbar, aber spürbar (Findings §12).
Erst angehen, wenn es in der Praxis stört – dann in dieser Reihenfolge:

1. **Selbstschnitt-Wächter bei konvexen Ringen überspringen** (~14 % der
   `optimize()`-Zeit): eine RDP-Teilmenge der Punkte eines konvexen Rings ist
   in Reihenfolge wieder konvex und kann sich nicht selbst schneiden. Ein
   O(n)-Konvexitätstest (alle Kreuzprodukte gleiches Vorzeichen) vor dem
   Wächter genügt.
2. **Inselbestand zwischenspeichern**, solange Seed, Muster- und
   Geometrie-relevante Stil-Parameter unverändert sind (Cache-Schlüssel aus
   dem Doc ableiten; bei jedem Treffer entfällt der teure Zusammenhangstest).
3. Beides mit dem Determinismus-Test absichern (Cache-Treffer ⇒ identische
   Szene wie Kaltstart).

### Meilenstein 9 – Fusion-Abnahme und Restpunkte

1. **CHECKLIST G4/G5 in Fusion durchgehen** (nicht automatisierbar, Findings
   §14): Extrusion der Verbinder-Szenen zu **einem** Volumenkörper,
   Re-Edit-Geschwindigkeit nach der Renderer-Flankierung, Sichtprüfung der
   optimierten Konturen. Voraussetzung: Meilenstein 6 ist umgesetzt, sonst
   scheitert die Extrusionsprüfung an den bekannten selbstschneidenden
   Profilen.
2. **Bogenfähiger Stroker: explizit vertagt.** Als eigenes Vorhaben notieren
   (Nicht-Ziel dieser Version): erst mit ihm können Pass 3 und ein
   Bogen-Refit an geklippten Kreisen greifen. Kein stiller Umbau im Rahmen
   dieses Plans.
3. **Findings-Messtabellen aktualisieren**, sobald Meilenstein 6 (und ggf. 7B)
   die Zahlen verschiebt – die Tabellen in §1 und §9 sind die
   Referenzmessungen für künftige Regressionen.
