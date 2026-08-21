# PatternCreator – Context: die Entscheidungen und ihre Gründe

**Stand: 2026-08-21.** Dieses Dokument ersetzt `PLAN.md` (Umsetzungsplan v3),
`CHECKLIST.md` (Review-Checkliste v3), `PLAN-VERBINDER-OPTIMIERER.md` und
`PLAN-VERBINDER-OPTIMIERER-findings.md`. Alle vier sind gelöscht; ihr Inhalt ist
hier eingedampft auf das, was der Code **nicht** von selbst erzählt: warum etwas
so gebaut ist, was gemessen wurde, was verworfen wurde und woran es lag.

Reine Beschreibungen des Ist-Zustands stehen nicht hier, sondern im Code und in
der `README.md`. Was hier steht, ist Gedächtnis – Entscheidungen samt Begründung
und die Messwerte, gegen die künftige Änderungen zu prüfen sind.

---

## 1. Leitideen

Drei Sätze, aus denen fast alle anderen Entscheidungen folgen:

1. **Extrudierbarkeit zuerst.** Jedes Muster hat einen *Linienmodus* (reine
   Kurven, für Gravuren) und einen *Flächenmodus* (Standard): jede Kurve wird
   über die **Dicke** zu einem geschlossenen Streifen, jede Zelle zu einem
   geschlossenen Polygon. Ergebnis sind Profile, die Fusion direkt extrudiert.
2. **Ein Muster = ein Dokument.** Der komplette Zustand ist ein einziges
   JSON-Objekt („PatternDoc"): Mustertyp, Container, alle Parameter, Text-Layer,
   Seed. Editor, Generator, Vorschau, Attribut-Speicherung und Re-Edit arbeiten
   ausschließlich damit.
3. **Geometrie getrennt von Fusion.** Generatoren erzeugen eine Fusion-freie
   Zwischenrepräsentation (IR). Dieselbe IR wird im Editor-Canvas gezeichnet und
   vom Renderer in die Skizze übertragen. Vorschau und Ergebnis können deshalb
   nicht auseinanderlaufen.

**Leitplanken, die nie aufgeweicht wurden:**

- Reines Python, keine externen Pakete (kein numpy/scipy/shapely), keine
  JS-Bibliotheken – alles offline, ohne Build-Schritt. Festgeschrieben in
  `tests/test_architecture.py`.
- `core/`, `generators/` und `text/` importieren **kein** `adsk` (Struktur-Test).
- Deterministisch: gleicher Seed + gleiche Parameter ⇒ identische Geometrie in
  Vorschau, Commit und Re-Edit. Nie `random.seed()` global, nur
  `random.Random(seed)`-Instanzen.
- Alles Neue passiert **vor** der Scene-Erzeugung in `core/build.build_scene()`,
  weil Vorschau und Fusion-Ausgabe beide dort durchlaufen. Nichts im Renderer
  „nachbessern".

---

## 2. Editor: Palette statt Command-Dialog

**Entscheidung:** kein nativer Fusion-Command-Dialog, sondern eine
`adsk.core.Palette` (HTML/JS). Begründung: Live-Canvas-Vorschau in < 50 ms statt
langsamer Skizzen-Neuaufbauten, echtes Undo/Redo im Editor, freie UI-Gestaltung.

- Formulare entstehen **generisch** aus den Parameter-Schemata der Generatoren.
  Ein neues Muster braucht deshalb keinen UI-Code – nur eine neue Datei und einen
  Registry-Eintrag. Das ist eine harte Zusicherung (Test in
  `tests/test_architecture.py`).
- Datenfluss: JS → Python `docChanged` (debounced 150 ms) mit komplettem
  PatternDoc; Python validiert, generiert und schickt die IR als JSON zurück.
  Fehler kommen **feldbezogen** zurück (Feldname + erlaubter Bereich), nicht als
  globaler Fehlertext.
- Request-IDs: Palette-Messaging ist asynchron. Ohne mitgeführte IDs erzeugt
  schnelles Schieben eines Reglers flackernde oder veraltete Vorschauen.
- Undo/Redo im Editor: History-Stack von PatternDoc-Snapshots im JS (max. 100),
  debounced – nicht pro Tastendruck. In Fusion selbst gilt: ein Commit = **ein**
  Timeline-Schritt.
- Einheiten: API-intern ist **cm**, der Editor zeigt **mm**. Umgerechnet wird nur
  an der Grenze Editor ↔ Doc.
- Nielsen-Heuristiken waren beim Entwurf Pflichtprogramm; daraus stammen
  Element-Zähler unter der Vorschau, Presets (fein/mittel/grob), Piktogramme im
  Dropdown, „?"-Hilfe je Muster, Warnbanner bei sehr großen Mustern.

---

## 3. Container

Formen: Rechteck (optional Eckenradius), Quadrat, Kreis, Ellipse, regelmäßiges
Vieleck (3–12 Seiten). Einheitliche Schnittstelle `contains` / `clip_path` /
`outline` / `bounding_rect`.

- Generatoren füllen **immer** das Bounding-Rechteck; das Clipping gegen die
  echte Form macht `core/build.py` zentral. So muss kein Generator die
  Containerform kennen.
- Kreis/Ellipse werden fürs Clipping mit 96 Segmenten angenähert; der
  **gezeichnete** Umriss bleibt ein echter Kreis- bzw. Ellipsenbogen.
- Clipping-Modi: `cut`, `dropPartial` (ergibt ausgefranste, natürliche Ränder),
  `off`.
- Ein bestehendes Skizzenprofil oder eine planare Fläche als Container: war
  Stretch, ist seit 2026-08-21 geplant – Entscheidungen in Abschnitt 15,
  Arbeitspakete in `PLAN-RAHMEN-3D.md`.

---

## 4. Muster-Katalog

Heutiger Stand: **9 Muster** in zwei Gruppen.

- **Technisch:** Gitter, Rauten, Wabe, Mauer, Puzzle.
- **Organische Zellen:** Voronoi, Kiesel, Zellgewebe, Blattadern.

Entscheidungen, die dahinterstehen:

- Die organische Familie teilt sich den Kern `generators/organic_cells.py`
  (Voronoi + Chaikin-Eckenglättung + optionale Anisotropie + Inset) statt
  Copy-Paste. Kiesel, Zellgewebe und Blattadern sind Aufsätze darauf.
- **Blattadern** sind bewusst ein *zweistufiges Voronoi* (grobe Hauptader-Zellen,
  darin feine Sub-Zellen) statt echter Aderbäume per Space-Colonization – die
  hierarchische Optik entsteht geometrisch, der Aufwand bleibt klein.
- **Puzzle-Nase:** Der Kopf ist ein **echter Kreis** (Radius = halbe Kopfbreite,
  Faktor 1,75 × Halsbreite), der Hals läuft bei 205° **tangential** hinein, am
  Fuß sitzt ein kleiner Unterschnitt. Die alte Fassung aus drei Bezier-Abschnitten
  hatte einen flachen Kopf, geknickte Übergänge und spiegelte am falschen Punkt.
  `tabSize` ist die Gesamthöhe und wird auf `half_head * 1.55` angehoben, damit
  der Hals nicht verschwindet.
- Harte Grenze **500 Voronoi-Zellen**: reines Python, ohne die Grenze wird die
  Vorschau zäh.
- Jedes Muster dedupliziert gemeinsame Kanten (gerundete Koordinaten als
  Set-Schlüssel) – sonst brechen die Profile beim Extrudieren.

---

## 5. Text-Layer

- Additive Ebene über dem Muster, im selben Commit, in derselben Skizze.
- **Knockout (Standard an):** im Bereich der Text-Bounding-Box (+ Rand) wird das
  Muster ausgestanzt. Ohne das entstünden beim Extrudieren überlappende Profile
  aus Text + Muster, und der Text wäre unlesbar.
- Knockout arbeitet über die **Bounding-Box**, nicht über die exakten
  Buchstabenkonturen – bewusst, weil exakte Konturen die Pipeline verkomplizieren
  würden.
- Datenmodell hält `textLayers` als **Liste**, obwohl die UI nur einen Layer
  bietet: mehrere Ebenen sind dadurch ohne Migration nachrüstbar.
- Schriftarten unterscheiden sich zwischen macOS und Windows ⇒ Rückfall auf
  *Arial* mit Hinweis statt Absturz.

---

## 6. Commit und Re-Edit

- Ablauf: neue Skizze → `isComputeDeferred = True` → IR zeichnen → Text →
  Attribute schreiben → `isComputeDeferred = False`, immer in `try/finally`.
  Alles in einem Command ⇒ ein Undo-Schritt.
- **Keine integrierte Extrusion.** Eine Checkbox „Direkt extrudieren" war
  vorgesehen *und umgesetzt* (`fusion/extrude.py`) und wurde bewusst wieder
  entfernt: das Add-In erzeugt ausschließlich Skizzen, extrudiert wird mit
  Fusions eigenem Befehl. Alte Dokumente mit gespeichertem `extrude`-Abschnitt
  laden weiterhin, der Abschnitt wird beim Einlesen verworfen.
- Re-Edit: PatternDoc als Attribut an der Skizze (`PatternCreator`/`doc` +
  `version`). Beim erneuten Commit werden die erzeugten Kurven gelöscht und neu
  gezeichnet – **dieselbe** Skizze, damit eine darauf gebaute Extrusion neu
  rechnet statt zu verwaisen. Manuelle Änderungen an der Skizze gehen dabei
  verloren; davor warnt der Commit.
- Kein `CustomFeature` (Muster als eigener Timeline-Eintrag mit Doppelklick-Edit)
  – bleibt Stretch-Ziel.

---

## 7. Flächenmodell: eine zusammenhängende Fläche

**Warum:** Das Stroken einzelner Stegketten erzeugt an jedem Knoten überlappende
Streifen. Fusion sieht dann hunderte Einzelprofile: nicht in einem Zug wählbar
und keine saubere Grundlage für den 3D-Druck.

**Kernidee:** Bei einem kachelnden Muster ist das Stegnetz exakt *Rahmen minus
verkleinerte Zellen*. Also keine Boolesche Operation, sondern:

```
Außenkontur = container.face_outline()      role = face
Löcher      = Zelle verkleinert um delta    role = hole
delta       = max(0, (Dicke − eigene Fuge) / 2)
```

Umgesetzte Details und ihre Gründe:

- `Generator.tiling` markiert die kachelnden Muster (heute: alle neun).
  `Generator.gap(params)` meldet die Fuge, die das Muster selbst lässt
  (Mauerfuge, Voronoi-Fugenbreite). Stegbreite ist `max(Dicke, eigene Fuge)` –
  so bleiben Ziegelmaße exakt, und Fuge 0 erzeugt keine Löcher auf Stoß.
- **Rahmendicke** wird **nach innen** gemessen: das eingestellte Rahmenmaß bleibt
  das Außenmaß. Das Muster wird gegen `container.shrunk(borderWidth − Dicke/2)`
  beschnitten, die Löcher zusätzlich auf `container.shrunk(borderWidth)` begrenzt
  – sonst machen Gehrungsspitzen beschnittener Randzellen den Rahmen dünner als
  eingestellt.
- **Splitterfilter:** Löcher mit mittlerer Breite (`2·Fläche/Umfang`) unter der
  halben Stegdicke stammen aus angeschnittenen Randzellen und werden zugemacht –
  im Druck wären das nicht darstellbare Kanten.
- Zellen verkleinern über den **Stroker-Offset**, nicht über Winkelhalbierende:
  `inset_polygon` kollabiert an konkaven Konturen und ließ vom Puzzle im
  Zellen-Modus 3 von 20 Teilen übrig.
- Voraussetzung: **Rahmen zeichnen** an (er *ist* die Außenkontur) und Beschnitt
  ≠ *Aus*. Sonst bleibt es beim alten Stroken – für Gravuren gewollt.
- Die Vorschau zeichnet Fläche und Löcher als **einen** Pfad (`evenodd`), sonst
  malen die Löcher die Fläche wieder zu.
- Messwert: Wabe im Beispiel 1849 → 679 Entities.

**Rahmen als Band:** Im Flächenmodus ist der Rahmen kein Strich, sondern ein Band
(Außen- und Innenkontur). Nur so laufen gestrokte Streifen in den Rahmen hinein
und hängen zusammen, statt offen am Rand zu enden.

**Offen:** Wo das Flächenmodell nicht greift (Füllung *Zellen*, kein Rahmen,
Beschnitt *Aus*), überlappen sich die Streifen echt. Eine einzelne Fläche
bräuchte dort eine echte Polygon-Vereinigung in reinem Python (Sonderfälle:
gemeinsame Kanten, Berührung in einem Punkt). Beim Extrudieren entsteht trotzdem
ein Körper.

---

## 8. Schraffur

**Kernidee:** Die Schraffur ist **kein eigener Modus**, sondern additiv – sie
erzeugt zusätzliche **Stege** in den freien Flächen. Damit bleibt alles
extrudierbar, und das eigentliche Muster ändert sich beim Zuschalten nicht (durch
Test abgesichert: Fläche und Löcher bleiben Bit für Bit gleich).

Entscheidungen:

- **Stege statt Linien** (Vorgabe des Auftraggebers): eine Schraffur aus offenen
  Kurven wäre nicht extrudierbar. Die Strichdicke ist **eigenständig**, eine feine
  Schraffur in einem groben Stegnetz ist also möglich.
- **Nur im Flächenmodus mit Füllung *Stege*** – nur dort sind die Zellen offen.
- **Verankerung statt schwebender Inseln:** jede Mittellinie wird an beiden Enden
  um `web_half = max(Dicke, eigene Fuge)/2` verlängert und endet in der Mitte des
  umgebenden Stegs. Ein Schraffursteg kann so nie frei in der Zelle schweben.
  Dieses „Verlängern bis zur Überlappung" ist das zentrale Idiom des Projekts:
  überlappende geschlossene Profile werden beim Extrudieren zu **einem** Körper.
- **Eigene Scanline statt `core/clip.py`:** der vorhandene Clipper kann nur gegen
  **konvexe** Bereiche schneiden, Zellen sind oft konkav (Puzzle-Nasen,
  Zellgewebe). `hatch.scanlines()` liefert an Einbuchtungen korrekt mehrere
  Teilstrecken je Linie.
- **Absolutes Raster** (Vielfache des Abstands, nicht relativ zur Zelle): bei
  festem Winkel fluchten die Linien über Zellgrenzen hinweg.
- **Randtangenten fallen weg** – eine Linie genau auf der Zellkante läge zur
  Hälfte im Steg und würde ihn nur verbreitern.
- Eigener Zufallsstrom `random.Random(seed + 7919)`: Zusatzgeometrie darf nie aus
  `ctx.rnd` gespeist werden, sonst ändert sich beim Zuschalten der Schraffur auch
  das Muster.
- Notbremsen: 2000 Linien je Fläche, 20000 Streifen gesamt, dann Warnung statt
  unbrauchbarer Skizze.
- Bewusst offen: Kreuzschraffur überlappt sich an den Kreuzungspunkten (dasselbe
  Union-Thema wie oben); konturparallele Schraffur ist nicht umgesetzt.

---

## 9. Skizzenelement-Optimierer

Ziel war, die Elementzahl zu senken (Warnschwelle 2000 in `core/build.py`), ohne
die sichtbare Geometrie zu verändern. `core/optimize.py` läuft **unmittelbar vor**
der Scene-Erzeugung und gilt damit automatisch für alle Muster; Vorschau,
`entity_estimate` und die 2000er-Warnung messen den optimierten Stand.

**Feste Toleranz TOL = 0,02 mm**, kein UI-Regler – Nutzerentscheidung.

### Was die Messungen ergaben (Referenz, Default-Parameter, Seed 42)

Diese Tabelle ist die Referenz für künftige Regressionen. Sie stammt aus dem
Stand von 1.4.0, also **mit** den inzwischen entfernten Mustern; die Zeilen der
verbliebenen Muster gelten unverändert.

| Muster | unoptimiert | optimiert | |
| --- | ---: | ---: | ---: |
| leaf_veins | 2506 | 2071 | −17,4 % |
| tissue | 3735 | 3232 | −13,5 % |
| pebbles | 2756 | 2460 | −10,7 % |
| puzzle | 1363 | 1245 | −8,7 % |
| voronoi | 662 | 660 | −0,3 % |
| honeycomb | 684 | 683 | −0,1 % |
| grid, rhombus, brick | | | ±0 % |

### Die Pässe – und was von den Erwartungen übrig blieb

- **Pass 1 (verlustfreie Bereinigung)** bringt praktisch nichts: über alle
  gemessenen Kombinationen 156 323 → 156 302 Elemente (−0,01 %). Grund: die
  Pipeline ist bereits sauber, bevor der Optimierer sie sieht (`stroker._clean`,
  `clean_polygon`, `snap_segments`). Auch **kein einziges** doppeltes Element in
  105 Kombinationen. Pass 1 bleibt drin, weil er korrekt ist und die
  aggressiveren Pässe absichert – aber nicht als Gewinnbringer.
- **Pass 2 (Kreis-Refit) greift nie.** Es entstehen keine tessellierten
  Vollkreise; Kreise bleiben von der Erzeugung bis zur Szene `ir.Circle`. Der
  Pass ist als Absicherung für künftige Generatoren umgesetzt und synthetisch
  getestet.
- **Pass 3 (Bogen-Refit) greift nie**, und der geplante Clip-Umbau ist **nicht
  machbar**: Das 48-Eck erreicht die Szene gar nicht (der gestrokte Ring hat
  25–35 Punkte); ein `ir.Arc` mitten in der Segment-Verkettung von `_to_areas`
  hätte keinen Platz; und der gestrokte Ring eines geklippten Kreises ist ein
  Mischling aus Bogen + Sehne + Bogen + Sehne. Das exakt abzubilden hieße
  gemischte Linie/Bogen-Pfade in der IR – ausdrückliches Nicht-Ziel. Ein
  **bogenfähiger Stroker** wäre der einzige Weg und ist bewusst vertagt.
- **Pass 4 (RDP)** ist der eigentliche Gewinn.
- **Pass 5 (Spline-Umwandlung) kann die Toleranz prinzipiell nicht halten.** Ein
  interpolierender Spline durch die Stützpunkte einer Polylinie weicht um etwa
  die **Bogenhöhe ihrer eigenen Sehnen** ab – er schneidet die Ecken, die die
  Polylinie stehen lässt. Gegenprobe am Einheitskreis: 40 Punkte ⇒ Spline-Fehler
  0,00307 cm, exakt die Sehnen-Bogenhöhe 0,00308 cm. Damit braucht eine Kontur
  vom Radius r mindestens `2π / (2·arccos(1 − TOL/r))` Punkte – bei r = 1 cm also
  50. Genau im Bereich, wo die Umwandlung etwas spart, verletzt sie die Toleranz.
  **Spline-Umwandlung ist Glättung, keine toleranztreue Optimierung.**

### Entscheidungen daraus

- **Toleranzbudget additiv:** radialer Fehler + Bogenhöhe ≤ TOL. „Je TOL/2" war
  zu streng und hätte den kanonischen 48-Eck-Fall abgelehnt. Beide Fehler treffen
  in der Sehnenmitte zusammen und addieren sich dort.
- **Fidelity-Harness misst Stützpunkte *und* Sehnenmitten.** Nur Stützpunkte zu
  messen genügt nicht: ein Refit läuft exakt durch sie und beult dazwischen aus.
- **Selbstschnitt-Wächter prüft relativ:** vereinfachen, wenn das Ergebnis sich
  nicht schneidet **oder** das Original sich schon geschnitten hat. Ein absoluter
  Test hätte jede Vereinfachung blockiert – 508 Rohkonturen waren vor jeder
  Optimierung selbstschneidend (Ursache siehe Abschnitt 10).
- **Flächen-Invariante geometrisch schranken:** `|ΔA| ≤ Umfang · TOL`. Ein festes
  Epsilon ist nach RDP nicht haltbar.
- **Pass 5 läuft vor Pass 4**, und es greift immer nur einer von beiden. Läuft
  die Vereinfachung zuerst, nimmt sie dem Spline die Stützpunkte weg *und*
  verbraucht das Budget; liefen beide, summierten sich ihre Abweichungen auf
  2 × TOL.
- **Option A (Nutzerentscheidung 2026-08-20):** Pass 5 bleibt bei 0,02 mm und
  damit schlafende Absicherung; die Spline-Entscheidung bleibt beim **Generator**,
  der als Einziger weiß, ob eine Punktfolge eine abgetastete glatte Kurve ist.
  Option B (eigene Glättungs-Toleranz, z. B. 0,1 mm ⇒ −12,2 % statt −9,8 %) ist
  verworfen: das wäre erklärtermaßen Glättung und bräuchte ein getrenntes
  Fidelity-Budget.
- **`organic_cells` bleibt beim Linienzug.** Die Prüfung, ob die gerundeten
  Konturen generatorseitig als Spline geliefert werden können, fiel **negativ**
  aus: pebbles 1,4–3,3 × TOL, tissue 2,5–3,6 × TOL, leaf_veins bis 20 × TOL. Eine
  gerundete Voronoi-Zelle ist keine glatte Kurve, sondern ein Vieleck mit
  Verrundungen – lange gerade Kanten (bis 0,47 cm) neben winzigen
  Rundungs-Sehnen (bis 1,4e-5 cm), Längenverhältnis bis **33 000 : 1**. Der
  Spline schätzt seine Tangenten aus den Nachbarpunkten, der lange Nachbar
  dominiert, und die Kurve schießt über die kurze Sehne hinaus – die Ausbeulung
  sitzt *in* der Rundung. Dazu begrenzt `round_corners` die Rundung an kurzen
  Kanten, dort bleibt die Ecke eine Ecke (76°–107° Knick, weit über dem
  30°-Gate). **Was der Verzicht kostet:** als Spline gemeldet, kostete jede Zelle
  1 statt n Elemente – pebbles 2460 → 114, tissue 3232 → 164, leaf_veins
  2071 → 130 (−94 bis −96 %). Diesen Gewinn gäbe es nur um den Preis einer
  sichtbar anderen Kontur.
- **Gestrichene Zielmarken:** „Puzzle ≥ 80 %", „Motiv-Streuung ≥ 50 %" und
  „geklippter Kreis ≤ 5 Elemente statt 48" sind ersatzlos gestrichen – alle drei
  beruhten auf Annahmen, die die Messung widerlegt hat. Sie kehren nicht zurück.
  Der Puzzle-Fall im Besonderen: die Kandidatenringe haben Knicke von 106°–127° –
  die Ringe *sind* die Ecken.

### Kosten

`optimize()` kostet beim schwersten Muster (tissue) +0,04 s je Aufbau und
verteilt sich (cProfile) auf RDP ~31 %, Selbstschnitt-Wächter ~14 %, Pass 1
~12 %, Kreis-Fit ~10 %. Vertretbar: in Fusion spart jede eingesparte Linie einen
API-Roundtrip, und die dominieren die Commit-Zeit um Größenordnungen.

### Flankierend im Renderer

`clear_pattern_geometry` löscht beim Re-Edit jetzt ebenfalls unter
`isComputeDeferred` (vorher Element für Element ohne), und `arePointsShown` wird
während des Aufbaus abgeschaltet. Eine Batch-API gibt es in Fusion nicht –
weniger Elemente ist der einzige Hebel.

---

## 10. Der Stroker-Fix (Bestandsfehler, behoben)

Beim Bau des Selbstschnitt-Wächters fiel auf: `stroke_open`/`stroke_closed`
hatten – anders als `_shrink_cell` – **kein** `remove_loops`. Der Gehrungs-Offset
legt an Beschnittkanten Schleifen an, und diese Ringe erreichten Fusion
unbereinigt. Ein sich selbst schneidendes Profil ist dort unbrauchbar.

Betroffen war immer der **Strok-Pfad** (`_to_areas`), nie das Flächenmodell
(`_to_face`): tissue und leaf_veins je 94 bzw. 78 kaputte Konturen (mit
`border=False` bzw. `clip=off`), puzzle/pebbles je 31/30; insgesamt 508
Rohkonturen über 105 Kombinationen.

**Fix:** `remove_loops` läuft jetzt über jeden Stroker-Ring – in `stroke_open`
über den einen Ring, in `stroke_closed` über Außen- und Innenring, jeweils *vor*
den bestehenden Gates (≥ 3 Punkte, |Fläche| > 1e-10). `_clean` läuft davor und
danach, weil der neue Schnittpunkt auf einem Nachbarpunkt landen kann.

**Wirkung:** keine einzige selbstschneidende geschlossene Kontur mehr. Die
Konturzahl-Invariante hält (mit und ohne `remove_loops` exakt gleich viele
Konturen – kein stiller Verlust). Kosten: +0,02 s bei tissue; bei
4-Punkt-Rechtecken ist der Aufruf ein No-op.

**Wechselwirkung, die man kennen muss:** Nach dem Fix sind weniger
Originalkonturen von Haus aus selbstschneidend, der *relative*
Selbstschnitt-Wächter wird dadurch strenger und die Elementzahlen verschieben
sich leicht.

---

## 11. Bekannte Fallstricke

- Event-Handler-Referenzen global halten (GC), auch die Palette-HTML-Handler.
- `isComputeDeferred` immer in `try/finally` zurücksetzen.
- Doppelte Kanten oder sich schneidende Streifen zerstören Profile ⇒
  Deduplizierung und Knockout sind Pflicht, nicht Kosmetik.
- `inset_polygon` kollabiert an konkaven Konturen ⇒ zum Verkleinern von Zellen
  den Stroker-Offset verwenden.
- `core/clip.py` kann nur gegen **konvexe** Bereiche schneiden ⇒ alles, was durch
  konkave Zellen geschnitten werden muss, braucht die Scanline aus `core/hatch.py`.
- Zusatzgeometrie nie aus `ctx.rnd` speisen.
- Fusion cacht Palette-HTML ⇒ Version-Query an die URL hängen.
- Ein Eckpunkt taugt nicht als „liegt darin"-Prüfpunkt: beschnittene Motive haben
  ihre Kante exakt auf der Containerkante, und `point_in_polygon` ist auf der
  Grenze nicht entscheidbar. Mitte der längsten Kante, ein Haar nach innen
  versetzt, funktioniert.

---

## 12. Abnahme in Fusion (nicht automatisierbar)

`pytest tests/` deckt die Fusion-freien Teile ab. Was sich **nur** in Fusion und
am gedruckten Teil prüfen lässt und deshalb beim Abnehmen einer Änderung
durchgegangen werden sollte:

- Jedes Muster mit Standardwerten **und** einem Extremfall (Matrix im README).
- Flächenmodell: Muster mit **einem** Klick auswählbar; keine Überlappungen an
  den Knoten; Stegbreite innen = eingestellte Dicke; Rahmen nirgends dünner als
  eingestellt, auch nicht an angeschnittenen Randzellen; keine Splitter am Rand;
  extrudiert **ein** Körper, STL-Export ohne Reparaturhinweis.
- Rahmendicke in Fusion **nachmessen**: Außenmaß bleibt das eingestellte Maß.
- Schraffur: kein Steg schwebt frei; konkave Zellen (Puzzle) korrekt gefüllt;
  Schraffur-Dicke unabhängig von der Stegdicke; Text-Knockout gilt auch für die
  Schraffur.
- Optimierer: optimierte Kontur ist von der bisherigen **nicht zu unterscheiden**
  (Sichtprüfung Kiesel, Zellgewebe, Blattadern, Puzzle); Konturzahl bleibt
  gleich; mehrfaches Re-Edit driftet nicht.
- Strok-Profile ohne Selbstschnitt: angeschnittene Randmotive extrudieren sauber,
  besonders bei `border=False` bzw. `clip=off`.
- Re-Edit-Zyklus: erzeugen → extrudieren → bearbeiten → die Extrusion rechnet neu.
- Zweimal Laden/Entladen des Add-Ins: keine doppelten Buttons, keine Fehler.

---

## 13. Chronik der Entfernungen

Was einmal gebaut und wieder herausgenommen wurde – damit es nicht aus Versehen
zurückkommt.

### 13.1 Direkt-Extrusion (vor 1.2)

Checkbox „Direkt extrudieren" samt Tiefe/Richtung/Vorgang war umgesetzt und wurde
entfernt: Das Add-In erzeugt Skizzen, extrudiert wird mit Fusions eigenem Befehl.

### 13.2 Wasser-Kaustik (1.3.0)

Das Muster war in der Praxis nicht benutzbar: gewellte Einzelkanten mit variabler
Dicke, Überlappung an jedem Knoten, weder zusammenhängende Fläche noch sauberes
Profil. Entfernt mit Generator, Registry-Eintrag, Tests und allen Erwähnungen in
README, Plan, Checkliste und Manifest.

### 13.3 Natürliche Muster und Verbinder (1.5.0, 2026-08-20)

**Auf Wunsch des Nutzers entfernt: die komplette Gruppe „Natürlich" – Fischgrät
(`herringbone`), Wellen (`waves`), Schuppen (`scales`), Phyllotaxis
(`phyllotaxis`), Spiralen (`spirals`), Motiv-Streuung (`motif_scatter`).**
Begründung: sie funktionieren in der Praxis nicht gut. Die Gruppe „Organische
Zellen" (Voronoi, Kiesel, Zellgewebe, Blattadern) bleibt.

Mitentfernt, weil ohne Anwendung: das **Verbinder-Feature** (`core/connect.py`,
die Stil-Parameter `connectors`/`connectorWidth`, das Klassen-Flag
`Generator.scatter`, die Sichtbarkeitslogik in `palette/editor.js`, der Aufruf in
`core/build.py`, `tests/test_connectors.py` und die README-Abschnitte in beiden
Sprachen). Phyllotaxis und Motiv-Streuung waren die einzigen Streu-Muster
(`scatter = True`); ohne sie gibt es keine frei stehenden Inseln mehr, die
Verbinder-Stege zusammenhalten müssten.

Ebenfalls entfallen: die verwaisten Helfer `parallel_lines`, `jitter_point` und
`arc_points` in `generators/_util.py` – sie hatten nach dem Löschen der
Strich-Muster keinen Aufrufer mehr.

**Was das für die Architektur bedeutet:** Alle verbliebenen neun Muster sind
`tiling = True`. Der Strok-Pfad (`_to_areas`) wird deshalb nur noch erreicht,
wenn das Flächenmodell bewusst nicht greift – Füllung *Zellen*, kein Rahmen oder
Beschnitt *Aus*. Das Rahmen-Band bleibt trotzdem nötig: dort enden die gestrokten
Streifen sonst offen am Rand. Auch der Stroker-Fix aus Abschnitt 10 bleibt
relevant, denn genau dieser Pfad erzeugte die selbstschneidenden Profile.

**Was aus den Messwerten wurde:** Die Referenzzahlen für phyllotaxis (965 → 723,
mit Verbindern 1625, 220 Inseln) und motif_scatter (1493 → 1238, mit Verbindern
1302, 15 Inseln) sind gegenstandslos. Die Zeilen der verbliebenen Muster in
Abschnitt 9 gelten unverändert.

**Verworfene Erkenntnisse, die trotzdem wertvoll bleiben** (falls je wieder
frei stehende Motive dazukommen):

- **Inseln statt Gruppen-IDs.** Die Zugehörigkeit aus der *fertigen Geometrie*
  abzuleiten („was sich schneidet oder ineinander liegt, gehört zusammen") war
  dem geplanten IR-Feld `group` deutlich überlegen: Motiv-Streuung hatte 144
  Profile, aber nur **15 Inseln** – Generator-IDs hätten 143 Stege gezogen statt
  der nötigen 14. Außerdem entfiel das Durchreichen durch vier Pipeline-Stufen.
- **Even-odd/Schachtelungstiefe geht schief**, sobald sich zwei Stege überlappen:
  ein winziges Motiv in der Überlappung hat Tiefe 2 und gilt fälschlich als
  isoliert. Die einfachere Schnitt-oder-Enthalten-Regel ist sicher – nur nicht
  für den Rahmen, der alles umschließt, ohne es zu berühren.
- **Der Beschnitt kann einen Steg durchtrennen.** Ein Steg an einem
  angeschnittenen Randmotiv verliert beim Clipping genau das Stück, mit dem er in
  sein Motiv hineinläuft. Nötig war ein Nachbesser-Durchlauf (Inseln erneut
  zählen, fehlende Verbindungen ergänzen, höchstens vier Runden) und danach eine
  Warnung statt stiller loser Teile.
- **Kosten des Zusammenhangstests:** mit Raster-Vorauswahl und Hüllrechteck-Filter
  0,135 s je Aufbau statt 0,4 s ohne – bei einer Vorschau, die bei jeder
  Reglerbewegung neu baut, ist das die spürbare Grenze.

**Testlage nach der Entfernung:** 475 Tests grün (vorher 667; die Differenz sind
die Verbinder-Tests und die Tests der entfernten Muster).

---

## 14. Offene Punkte und ausdrückliche Nicht-Ziele

**Offen:**

- Polygon-Vereinigung für den Strok-Pfad (Füllung *Zellen*, kein Rahmen,
  Beschnitt *Aus*) und für die Kreuzschraffur.
- Bestehendes Skizzenprofil / planare Fläche als Container – **geplant**,
  siehe Abschnitt 15 und `PLAN-RAHMEN-3D.md`; ebenso Mantelflächen
  (Zylinder/Kegel) per Abwicklung.
- `CustomFeature` statt reiner Skizzengeometrie.
- Mehrere Text-Layer in der Oberfläche, Text auf Kreisbogen.
- Konturparallele Schraffur.

**Nicht-Ziele (bewusst, nicht aus Zeitmangel):**

- Gemischte Linie/Bogen-Pfade in der IR (Composite-Paths).
- Bogenfähiger Stroker – ohne ihn kann das Bogen-Refit an geklippten Kreisen
  nicht greifen; das ist ein eigenes Vorhaben, kein Nebenbei-Umbau.
- Biarc-Fitting (G1-stetige Bogenpaare): greedy Bogen-Refit + Splines liefern
  fast denselben Gewinn bei einem Bruchteil der Komplexität.
- UI-Regler für die Optimierer-Toleranz.
- Externe Pakete oder JS-Bibliotheken, in keiner Form.

---

## 15. Geplant: Eigener Rahmen (1.6.0) und Mantelflächen (1.7.0)

**Stand 2026-08-21, vor der Umsetzung.** Die Arbeitspakete stehen in
`PLAN-RAHMEN-3D.md`; hier stehen die Entscheidungen, die der Plan voraussetzt,
samt Begründung. Messwerte und Spike-Ergebnisse trägt die Umsetzung hier nach;
`PLAN-RAHMEN-3D.md` wird danach – wie seine Vorgänger – gelöscht und hier
eingedampft.

### 15.1 Eigener Rahmen

- **Quelle: Skizzenprofil oder planare Fläche, nur die Außenkontur.**
  Innenkonturen (Löcher im Profil, Bohrungen in der Fläche) werden ignoriert.
  Nutzerentscheidung; Grund: kleinster Umfang, robust. Löcher hießen
  Mehrfach-Container im Clipping und eigene Rahmenstege um jedes Loch.
- **Snapshot statt Live-Verknüpfung.** Die Kontur liegt als Punktliste im
  PatternDoc (`container.customPoints`, lokal um den Bounding-Box-Mittelpunkt,
  `placement.originX/Y` trägt die Lage). Re-Edit braucht die Quelle nicht;
  „Rahmen neu einlesen" holt sie über den gespeicherten Entity-Token nach.
  Grund: die Leitidee „ein Muster = ein Dokument" – ein Doc, das auf eine
  gelöschte oder verschobene Skizze zeigt, wäre nicht mehr neu aufbaubar.
- **Konkave Rahmen sind Pflicht**, nicht Kür: ein gezeichneter Rahmen ist fast
  nie konvex. `core/clip.py` (Halbebenen) bleibt für die Standardformen und die
  Knockout-Box; daneben kommt `core/polyclip.py` mit **Randklassifikation**
  (Schnittpunkte bestimmen, beide Konturen dort teilen, Teilkanten über ihren
  Mittelpunkt als innen/außen einordnen, verketten). Regel für Degenerationen:
  Zellkante auf dem Rahmenrand zählt als **innen**, Rahmenkante auf dem
  Zellrand als **außen** – so kommt eine gemeinsame Kante genau einmal.
  Verworfen: Greiner–Hormann/Weiler–Atherton (brechen genau an diesen
  Degenerationen, die hier die Regel sind: Gitterlinie exakt auf Rahmenkante)
  und konvexe Zerlegung mit Verkleben (das Verkleben ist bei konkaven Zellen
  eine Polygon-Vereinigung – das Thema, das das Projekt bisher meidet).
- **Rahmendicke im konkaven Rahmen** über den Stroker-Offset (wie
  `_shrink_cell`), nicht über `inset_polygon` (kollabiert an Einbuchtungen).
  Wo der Rahmen schmaler ist als zweimal die Rahmendicke, lässt sich das Maß
  nicht einhalten ⇒ Warnung, kein stiller Fehler.
- **Bögen im Rahmen werden Linienzüge** (Fusion-Tesselierung, danach RDP auf
  die Optimierer-Toleranz 0,02 mm). Echte Bögen im Rahmenumriss hießen
  gemischte Linie/Bogen-Pfade in der IR – erklärtes Nicht-Ziel (Abschnitt 9).
- **Fläche als Ziel ⇒ Skizze ohne projizierte Kanten** (`addWithoutEdges`).
  Die von Fusion projizierten Flächenkanten lägen exakt auf dem Rahmenumriss
  und zerstörten die Profile.
- Nicht geplant: Rahmen direkt in der Vorschau zeichnen (der Nutzer zeichnet
  in Fusion, dort hat er Bemaßung und Constraints).

### 15.2 Mantelflächen (Zylinder, Kegel) – „sinnvoll möglich?"

Prüfergebnis: **ja, für abwickelbare Flächen; nein für Kugel und Freiform.**

- Fusion kann keine Skizze auf einer gekrümmten Fläche anlegen. Der gangbare
  Weg ist **Abwicklung + Tangentialebene + Emboss**: das Add-In wickelt die
  Mantelfläche ab (Zylinder ⇒ Rechteck, Kegel ⇒ Kreisringsektor), erzeugt die
  Skizze auf einer Ebene tangential zur Fläche, und Fusions Emboss wickelt das
  Profil auf die Fläche. Fusions Emboss wickelt **nur zylindrische und konische**
  Flächen; auf Kugeln/Freiformflächen projiziert es verzerrt ⇒ dort bewusst
  nicht unterstützt, klare Fehlermeldung.
- **Würfel/Quader** brauchen kein Extra: Seiten sind planare Flächen, die
  Auswahl gab es schon; mit 14.1 wird die Fläche selbst zum Rahmen.
- **Emboss durch das Add-In, optional (Checkbox, Standard aus).**
  Nutzerentscheidung – und die eine bewusste Ausnahme von „das Add-In erzeugt
  nur Skizzen" (Abschnitt 6). Begründung: Extrudieren ist in Fusion ein Klick
  auf ein Profil; das Wickeln auf eine Fläche verlangt dagegen die richtige
  Tangentialebene, die passende Ausrichtung und – ohne Flächenmodell – die
  Auswahl hunderter Profile. Die API (`Features.embossFeatures`, seit
  September 2025) wird zur Laufzeit geprüft; fehlt sie, bleibt es bei der
  abgewickelten Skizze.
- **Nahtregel bei voller Umwicklung: „Die Naht ist immer ein Steg, und jeder
  Generator legt eine Zellgrenze auf die Naht."** Nutzerentscheidung für
  *nahtlos*; die Zellgröße rastet dafür auf einen Teiler des Umfangs
  (Gitter, Rauten, Wabe, Mauer, Puzzle), organische Zellen bekommen
  **gespiegelte Geisterpunkte** an den Fensterkanten, sodass die Naht exakt
  eine Voronoi-Grenze ist. Grund: in einer 2D-Skizze lässt sich eine „offene"
  Naht nicht darstellen (die Außenkontur muss geschlossen sein); ein Steg auf
  der Naht ist nach dem Wickeln ein normaler Steg – unsichtbar, **wenn** dort
  ohnehin eine Zellgrenze liegt. Bekannte Ausnahme: Mauer mit Versatz hat in
  jeder zweiten Reihe eine Fuge auf der Naht.
- **Kegel: Muster im Rechteck erzeugen, dann in den Sektor verzerren**
  (Polar-Warp, Segmente vorher auf Toleranz unterteilen), statt im Sektor zu
  generieren. Nur so bleiben Periodizität, Flächenmodell und alle Generatoren
  unverändert; die Zellen werden zum Apex hin schmaler – wie eine echte
  Abwicklung. Ob Fusions Emboss den Kegel exakt abwickelt oder nähert, klärt
  der Spike (Plan 2.0).
- **Spike vor dem Bau** (Plan 2.0): Tangentialebene parametrisch anlegen,
  Abbildung Skizze ⇒ Fläche, Emboss-Dauer bei vielen Löchern, Re-Edit-Verhalten
  des Emboss-Features. Scheitert davon etwas grundsätzlich, wird Phase 2 auf
  „abgewickelte Skizze, Emboss manuell" zugeschnitten und trotzdem ausgeliefert.

### 15.3 Was nach der Umsetzung hier stehen muss

Performance-Faktor konkaver Rahmen vs. Rechteck (Plan 1.2), Punktzahl eines
Beispielrahmens vor/nach RDP, Ergebnisse aller **[prüfen]**-Punkte, Emboss-Dauer
je Lochzahl, Elementzuwachs durch den Kegel-Warp, gestrichene Erwartungen.

### 15.4 Umsetzung: Messwerte und Abweichungen vom Plan

**Stand: 2026-08-21, Phase 1.** Wird waehrend der Umsetzung fortgeschrieben.

**Messwerte (Plan 1.2).** Voronoi mit 500 Zellen, Flaechenmodell, Dicke 1 mm,
Rahmendicke 2 mm; Laufzeit von `build_scene` gegen dasselbe Muster im
Rechteck (bestes von drei Laeufen, Caches jeweils geleert):

| Rahmen | Punkte roh → nach RDP | Laufzeit | Faktor |
| --- | --- | --- | --- |
| Rechteck (Referenz) | – | 0,177 s | 1,00 |
| L-Form | 6 → 6 | 0,180 s | 1,02 |
| Herz | 400 → 170 | 0,219 s | 1,24 |
| Stern, 200 Zacken | 400 → 400 | 0,356 s | 2,02 |

Der Plan hatte 1,5 als Schranke gesetzt. Realistische Rahmen bleiben darunter;
der 400-Punkte-Stern nicht. Er ist der denkbar unguenstigste Fall: 200 Zacken,
von denen die Vereinfachung keinen Punkt entfernen kann, und mehr als die
Haelfte aller Zellen liegt im Zackenkranz, also im Beschnitt. Dazu kommt, dass
angeschnittene Zellen dort konkav werden und deshalb den teuren Stroker-Offset
statt der Halbebenen-Erosion brauchen. Der Test sichert 2,5 ab – als Schranke
gegen Rueckschritte um Groessenordnungen, nicht gegen Messrauschen.

Ohne Beschleunigungsraster und Kantenindex lag derselbe Fall bei Faktor **7,1**.
Was die 7,1 auf 2,0 gebracht hat: 64x64-Raster mit innen/aussen/Rand je
Rasterzelle (Scanline-Fuellung), Kantenindex je Rasterzelle (eine Musterzelle
wird nur gegen die Rahmenkanten in ihrer Nachbarschaft getestet), Punkt-in-
Polygon nur ueber die Kanten der eigenen Rasterzeile, und ein Cache fuer den
Versatz `shrunk()` (die Vorschau baut den Container bei jeder Reglerbewegung
neu, der Rahmen bleibt derselbe).

**Punktzahl vor/nach RDP.** Kreis mit 2000 Tesselierungspunkten → 62 Punkte bei
0,02 mm Toleranz, Flaeche auf 0,1 % gleich. Herz mit 400 Punkten → 170.
Der Stern mit 200 Zacken → 400 (jeder Punkt traegt Form, nichts faellt weg).

**Abweichungen vom Plan (mit Begruendung):**

1. *Das Beschleunigungsraster liegt in `core/polyclip.py`, nicht in
   `core/containers.py`.* Der Plan beschreibt es unter Paket 1.2, verlangt es
   aber schon fuer die Schnellpfade in 1.1. Es liegt deshalb dort, wo es zuerst
   gebraucht wird; `CustomContainer` benutzt dasselbe Objekt (`grid_for`, Cache
   auf Modulebene). Aus dem Raster wurde dabei mehr als eine Innen/Aussen-Karte:
   es traegt zusaetzlich den Kantenindex (siehe Messwerte).
2. *`normalize_frame` vereinfacht (RDP) **vor** `remove_loops`, nicht danach.*
   `remove_loops` ist O(n^2) je Durchgang; bei einer tessellierten Kontur mit
   2000 Punkten dauert das Sekunden – und zwar bei jedem Parsen des Dokuments.
   Nach der Vereinfachung ist die Kontur klein genug. Beide Schritte sind
   voneinander unabhaengig, das Ergebnis ist dasselbe.
3. *Der Regressionsanker in `tests/test_polyclip.py` vergleicht Ringe nur, wenn
   Sutherland-Hodgman ueberhaupt einen einfachen Ring liefern kann.* Zerfaellt
   eine konkave Zelle am Rahmen in mehrere Stuecke, gibt der konvexe Clipper
   einen entarteten Ring mit Null-Breite-Verbindungen zurueck – genau deshalb
   gibt es `polyclip`. Verglichen wird dann die Flaeche. Fuer den rechteckigen
   Rahmen trat der Fall in keinem der 50 Zufallsfaelle ein: alle 50 Ringe sind
   punktgleich (Abweichung < 1e-14).
4. *Der Versatz `shrunk()` prueft zusaetzlich, ob der Abstand wirklich
   eingehalten ist.* Der Plan nennt als Fehlerfaelle „Flaeche waechst, < 3
   Punkte, Kontur zerfaellt". Bei einer Hantelform schlaegt der Gehrungs-Offset
   im Hals durch, ohne dass sich die Kanten kreuzen – sie ueberlappen sich nur
   kollinear, und `remove_loops` sieht das nicht. Geprueft wird deshalb direkt
   die zugesagte Eigenschaft: jede Ecke und jede Kantenmitte der neuen Kontur
   liegt innen und mindestens `delta` von der alten Kontur entfernt
   (Kandidatenkanten aus dem Raster, sonst waere der Test quadratisch).
5. *`core/build.py` hat drei statt zwei Stellen mit Warnung.* Der Plan nennt
   `clip_container` und `hole_limit`; das Rahmenband im Nicht-Flaechenmodus
   (`inner = container.shrunk(border_width)`) hat dieselbe Ursache und dieselbe
   Folge (der innere Umriss faellt weg), also dieselbe Warnung. Sonst ist
   `build.py` unveraendert – der Rahmen bleibt ein reines Container-Thema.
6. *`_shrink_cell` ist nach `core/stroker.py` gewandert* (als `shrink_polygon`
   / `shrink_polygon_checked`, wie im Plan vorgesehen); `core/build.py`
   importiert es unter dem alten Namen weiter.

**Bekannte Einschraenkung.** `CustomContainer.fully_inside` behandelt die
Punktfolge immer als geschlossenen Ring. Fuer den Beschnitt „Angeschnittene
weglassen" im Linienmodus heisst das: eine offene Kurve, deren gedachte
Verbindung vom letzten zum ersten Punkt aus dem Rahmen liefe, faellt weg,
obwohl die Kurve selbst innen liegt. Konservativ und selten; die Alternative
waere eine Signaturaenderung an `Container.fully_inside` und damit eine
Aenderung in `core/build.py`.
