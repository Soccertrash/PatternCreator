# PatternCreator – Review-Checkliste (v3)

Wird nach der Umsetzung Punkt für Punkt geprüft; jeder Punkt ist objektiv mit
„erfüllt / nicht erfüllt" bewertbar. Punkte mit *(Stretch)* gelten nur, wenn Phase 6 umgesetzt wurde.

## A. Projektstruktur & Installation
- [ ] Ordnerstruktur entspricht PLAN.md Abschnitt 2 (`commands/`, `core/`, `generators/`, `text/`, `fusion/`, `palette/`, `tests/`).
- [ ] Manifest ist gültiges JSON (`type: addin`, `supportedOS: windows|mac`).
- [ ] README beschreibt Installation für macOS **und** Windows.
- [ ] `./install.sh` installiert in den richtigen AddIns-Ordner: bricht bei laufendem Fusion ab, ersetzt eine vorhandene Installation vollständig und kopiert weder `.git` noch `.venv` oder Caches mit; `--dry-run`, `--force` und `--dir` wirken wie beschrieben.
- [ ] Keine externen Python-Pakete; Palette nutzt nur Vanilla JS/CSS (keine CDN-Links, offline lauffähig).

## B. Add-In-Lebenszyklus
- [ ] `run()` legt beide Buttons an („Muster erstellen", „Muster bearbeiten"); `stop()` entfernt Buttons, CommandDefinitions **und** die Palette rückstandsfrei (zweimal Laden/Entladen ohne Fehler/Duplikate).
- [ ] Alle Event-Handler (inkl. Palette-HTML-Events) global referenziert (GC-Schutz).
- [ ] Jeder Handler fängt Exceptions und zeigt eine verständliche Meldung.

## C. Editor (Palette)
- [ ] Palette öffnet mit Muster-Dropdown (alle 15 Muster, mit Piktogrammen), Canvas-Vorschau, Parametergruppen, Fußzeile.
- [ ] Vorschau aktualisiert live (debounced) und zeigt Containerumriss, Muster und Text-Layer lagerichtig; Zoom/Pan funktioniert.
- [ ] Formulare werden generisch aus den Parameter-Schemata erzeugt (neues Muster ⇒ kein UI-Code nötig – nachgewiesen am Code).
- [ ] Undo/Redo im Editor: Buttons + Cmd/Ctrl+Z bzw. +Shift+Z; mind. 50 Schritte (History-Stack laut PLAN.md Abschnitt 4: max. 100); debounced (nicht pro Tastendruck ein Schritt).
- [ ] „Abbrechen" hinterlässt nichts im Dokument; „Zurücksetzen" setzt auf Defaults.
- [ ] Veraltete Vorschau-Antworten werden verworfen (Request-IDs) – schnelles Schieben eines Sliders erzeugt keine flackernden/falschen Vorschauen.

## D. Nielsen-Heuristiken (Stichproben)
- [ ] Systemstatus: Element-Zähler unter der Vorschau; Beschäftigt-Anzeige beim Commit; Warnbanner bei > 5000 Vorschau-Elementen.
- [ ] Fehlervermeidung: min/max aus Schema erzwungen (Slider/Stepper); OK mit ungültigen Werten nicht möglich.
- [ ] Fehlerdiagnose: Validierungsfehler erscheinen feldbezogen in Klartext mit erlaubtem Bereich.
- [ ] Wiedererkennung: zuletzt benutzte Werte pro Mustertyp werden vorgeschlagen; Presets (fein/mittel/grob) vorhanden.
- [ ] Hilfe: „?" pro Muster zeigt Kurzbeschreibung + Parameter-Skizze.
- [ ] Einheiten im Editor in mm; interne Rechnung in cm (Stichprobe: 10 mm Eingabe ⇒ 1,0 cm im PatternDoc).

## E. Container
- [ ] Alle Formen wählbar: Rechteck (mit Eckenradius), Quadrat, Kreis, Ellipse, Vieleck (3–12 Seiten); Maße, Ursprung und Rotation wirken.
- [ ] Clipping-Modi `cut`, `dropPartial`, `off` funktionieren bei allen Formen (Stichprobe: Kreis + Wabe).
- [ ] `border`-Option zeichnet den Containerumriss als echten Kreis/Ellipse/Polygon (nicht als Polygon-Approximation).
- [ ] *(Stretch)* Bestehendes Profil/planare Fläche als Container wählbar.

## F. Muster-Korrektheit (je Muster: Defaults + ein Extremfall in Fusion getestet)
- [ ] **Gitter:** Abstände X/Y getrennt, Winkel wirkt.
- [ ] **Rauten:** Scharenwinkel ±α korrekt, Rautenmaße wirken.
- [ ] **Wabe:** lückenlos, keine doppelten Kanten, beide Ausrichtungen; Flächenmodus liefert wählbare Steg- UND Zell-Profile.
- [ ] **Mauer:** Reihenversatz (1/2, 1/3, frei), Fugenbreite 0 und > 0, Randziegel bei `cut` beschnitten.
- [ ] **Puzzle:** Nasenrichtung zufällig per Seed, Nasengröße/Halsbreite wirken; im Flächenmodus ist jedes Teil ein geschlossenes Profil.
- [ ] **Voronoi:** füllt Bereich vollständig, deterministisch per Seed, max. 500 Zellen erzwungen, Inset erzeugt Inseln.
- [ ] **Kiesel:** Rundheit wirkt sichtbar, Fugenbreite wirkt, Kernpunkt-Option erzeugt Kreise je Zelle.
- [ ] **Kiesel/Zellgewebe:** die Fuge frisst keine Zellen weg – die eingestellte Zellenzahl kommt auch mit Rundheit 3 an, ohne massive Flächen dazwischen.
- [ ] **Zellgewebe:** Zellen länglich in Reihen (Anisotropie sichtbar), Reihenhöhe/Zelllänge wirken.
- [ ] **Blattadern:** zwei Hierarchiestufen sichtbar (Hauptadern dicker als Nebenadern), Parameter Grob-/Feinzellen wirken; im Flächenmodus **eine** zusammenhängende Fläche ohne überlappende Streifen.
- [ ] **Fischgrät:** Rippenwinkel und -abstand wirken; 1 Achse = Palmwedel-Optik, n Achsen = Feld; Krümmung > 0 erzeugt Bögen.
- [ ] **Wellen:** Splines glatt; Wellenlänge/Amplitude/Abstand/Jitter wirken.
- [ ] **Schuppen:** Reihen versetzt und überlappend.
- [ ] **Phyllotaxis:** Goldener-Winkel-Spirale erkennbar; Elementform und Größenverlauf wirken.
- [ ] **Spiralen:** logarithmische Spiralen, Windungen/Anzahl/Streuung wirken, Drehrichtung mischbar.
- [ ] **Motiv-Streuung:** Blattmotiv parametrisch (schlank↔rund, Rippen); Raster-, Versatz- und Poisson-Streuung; Rotation/Größen-Jitter per Seed.
- [ ] Gleicher Seed ⇒ Vorschau, Commit und Re-Edit erzeugen identische Geometrie (bei allen Zufallsmustern stichprobenhaft geprüft).

## G. Stil & Dicke
- [ ] Linien- und Flächenmodus bei jedem Muster wählbar; Dicke wirkt im Flächenmodus überall.
- [ ] Flächenmodus erzeugt ausschließlich geschlossene, nicht selbst-schneidende Profile (Stichprobe: Wabe, Kiesel, Blattadern in Fusion extrudiert – ohne Profil-Fehler).
- [ ] Ein Commit = genau **ein** Timeline-Undo-Schritt.

## G2. Flächenmodell & 3D-Druck (kachelnde Muster)
- [ ] Gitter, Rauten, Wabe, Mauer, Puzzle, Voronoi, Kiesel, Zellgewebe ergeben im Flächenmodus mit *Stege* + *Rahmen zeichnen* **eine** Kontur mit Löchern – in Fusion mit **einem** Klick auswählbar.
- [ ] Keine überlappenden Streifen mehr an den Knoten (Stichprobe Wabe: keine Kreuzungen an den Dreipunkten).
- [ ] Stegbreite innen entspricht der eingestellten Dicke; bei Mauer/Kiesel gilt die größere von Dicke und eigener Fuge, Ziegelmaße bleiben exakt.
- [ ] **Rahmendicke** wirkt und wird nach innen gemessen: Außenmaß des Bauteils bleibt das eingestellte Rahmenmaß (Messung in Fusion).
- [ ] Rahmen ist an keiner Stelle dünner als eingestellt – auch nicht an angeschnittenen Randzellen.
- [ ] Keine Splitter am Rand: keine hauchdünnen Löcher aus angeschnittenen Zellen.
- [ ] Extrudiertes Ergebnis ist **ein** Körper ohne Selbstüberschneidung; STL-Export ohne Reparaturhinweis (Stichprobe Wabe + Puzzle).
- [ ] Vorschau zeigt die Fläche mit Löchern (nicht flächig zugemalt).
- [ ] Ohne Rahmen bzw. mit Beschnitt *Aus* greift weiterhin das alte Stroken (Gravur-Fall) – ohne Fehler.
- [ ] Strich-Muster (Wellen, Spiralen, Fischgrät, Schuppen, Phyllotaxis, Motiv-Streuung) bleiben mehrteilig, ergeben beim Extrudieren aber **einen** Körper. *(Stufe 2, siehe PLAN.md Abschnitt 12)*
- [ ] Puzzle: runder Kopf an schmalem Hals, Nasen greifen ineinander, keine Knicke am Halsansatz; Nase bleibt auch bei Formstreuung 1,0 auf ihrer Kante.

## G3. Schraffur (optionale Füllung der Zellflächen)
- [ ] Schalter **Schraffur in Zellen** erscheint nur im Flächenmodus mit Füllung *Stege*; sonst sind alle Schraffur-Felder ausgeblendet und wirkungslos.
- [ ] Schraffur ist additiv: Ein- und Ausschalten ändert das eigentliche Muster (Fläche + Löcher) nicht – auch die Zufallsmuster nicht (Voronoi, Kiesel, Zellgewebe).
- [ ] **Schraffur-Dicke** wirkt unabhängig von der Stegdicke (Stichprobe: Steg 1,0 mm + Schraffur 0,4 mm in Fusion gemessen).
- [ ] **Abstand** ist Strichmitte zu Strichmitte; bei festem Winkel fluchten die Linien über Zellgrenzen hinweg.
- [ ] Kein Schraffursteg schwebt frei: jeder Strich ist an beiden Enden mit dem Stegnetz verbunden (Stichprobe Wabe + Voronoi, im 3D-Druck kein loses Teil).
- [ ] Konkave Zellen korrekt gefüllt: beim Puzzle folgt die Schraffur den Nasen, es entstehen mehrere Teilstriche je Linie und keine Striche außerhalb der Zelle.
- [ ] **Zufällig je Zelle**: jede Zelle hat einen anderen Winkel; gleicher Seed ⇒ gleiches Ergebnis in Vorschau, Commit und Re-Edit.
- [ ] **Zum Mittelpunkt**: alle Zellen zeigen auf den eingestellten Punkt (Strahlenkranz); Punkt liegt relativ zur Rahmenmitte und verschiebt sich mit dem Rahmen.
- [ ] **Kreuz**: zweites Raster mit dem eingestellten Kreuzungswinkel; Überlappung an den Kreuzungen ist bekannt und extrudiert trotzdem zu **einem** Körper.
- [ ] Schraffur bleibt innerhalb des Rahmens und hält die Rahmendicke ein.
- [ ] Text-Knockout gilt auch für die Schraffur: kein Schraffursteg schneidet die Text-Box.
- [ ] Sehr kleiner Abstand ⇒ Warnung („Schraffur bei 20000 Stegen abgebrochen") statt Einfrieren; Entity-Warnung beim Commit greift.
- [ ] Ohne Rahmen (altes Stroken, Gravurfall) wird ebenfalls schraffiert.
- [ ] Schraffierte Skizze in Fusion extrudieren: Stege **und** Schraffur werden massiv, die Restflächen bleiben offen (mit Schraffur entstehen deutlich mehr und kleinere Restprofile – die Profilauswahl ist in Fusion zu prüfen).

## G4. Verbinder (Streu-Muster als ein Teil)
- [ ] Schalter **Verbinder** erscheint **nur** bei Phyllotaxis und Motiv-Streuung und nur im Flächenmodus; bei allen anderen Mustern sind die beiden Felder ausgeblendet und wirkungslos.
- [ ] Verbinder aus ⇒ exakt der Stand von vorher (Regressionsprüfung an einer bestehenden Skizze).
- [ ] **Ein Körper**: Phyllotaxis (Seed 42, Standardwerte) extrudieren und in Fusion prüfen, dass **ein** Volumenkörper entsteht – nicht 220. Ebenso Motiv-Streuung.
- [ ] Ausgedruckt hält das Teil zusammen: Stichprobe bei 0,8 mm Verbinder-Dicke vom Druckbett nehmen, nichts fällt ab.
- [ ] **Verbinder-Dicke** wirkt und ist in Fusion nachmessbar (Stichprobe 0,4 / 0,8 / 2,0 mm).
- [ ] **Rahmen-Verankerung**: das Muster hängt an mindestens zwei Stellen auf verschiedenen Seiten im Rahmenband, schwebt also nicht frei darin.
- [ ] Ohne Rahmen: Muster hängt untereinander zusammen **und** es erscheint der Hinweis auf das lose Einzelteil.
- [ ] Angeschnittene Randmotive (`Beschnitt = Am Rand beschneiden`, dichtes Muster) hinterlassen kein loses Teilstück; bleibt doch eines übrig, erscheint die Warnung statt stiller Einzelteile.
- [ ] **Zellen-Modus** (`Füllung = Zellen`) ebenso: ein Körper.
- [ ] Text-Knockout: läuft ein Steg durch die Text-Box, wird er ausgestanzt – das betroffene Motiv darf dabei wieder lose werden (dokumentierte Grenze, README „Bekannte Einschränkungen").
- [ ] Linienmodus: keine Verbinder (nichts wird extrudiert).
- [ ] Gleicher Seed ⇒ identische Steg-Geometrie in Vorschau, Commit und Re-Edit.
- [ ] Elementzahl bleibt unter der 2000er-Warnschwelle (Phyllotaxis Standardwerte: ~1625).

## G5. Skizzenelement-Optimierer
- [ ] Kein UI-Element – der Optimierer läuft immer mit fester Toleranz 0,02 mm.
- [ ] Sichtprüfung in Fusion: optimierte Kontur ist von der bisherigen nicht zu unterscheiden (Stichprobe Kiesel, Zellgewebe, Blattadern, Puzzle).
- [ ] Elementzahl sinkt bei den organischen Mustern spürbar (Blattadern 2506 → 2071, Zellgewebe 3735 → 3232) – Zähler in der Vorschau vergleichen.
- [ ] Zahl der Konturen bleibt gleich: kein Profil geht verloren.
- [ ] Re-Edit-Zyklus: mehrfach bearbeiten und neu erzeugen verändert die Geometrie nicht weiter (kein Driften).
- [ ] Re-Edit ist spürbar schneller als vorher (Löschen läuft jetzt ebenfalls unter `isComputeDeferred`).

## G6. Strok-Profile ohne Selbstschnitt
- [ ] **Angeschnittene Randmotive extrudieren sauber**: Phyllotaxis (Seed 42, Standardwerte, `Beschnitt = Am Rand beschneiden`) – die Kreise am Rahmenrand ergeben geschlossene Profile ohne Schleife an der Beschnittkante.
- [ ] Ebenso ohne Rahmen bzw. mit `Beschnitt = Aus` bei Zellgewebe, Blattadern, Puzzle und Kiesel – dort saßen die meisten kaputten Profile.
- [ ] Zahl der Konturen ist dieselbe wie vorher; die Elementzahl liegt leicht darunter (Phyllotaxis 1039 → 965 ohne Verbinder), weil die Schleifenpunkte wegfallen.
- [ ] Schraffur-Streifen und Verbinder-Stege sehen unverändert aus (4-Punkt-Rechtecke, an denen die Schleifenentfernung nichts zu tun hat).

## H. Text-Layer
- [ ] Text über jedem Mustertyp platzierbar; Schriftart, Höhe, Position, Winkel wirken; Position auch per Drag in der Vorschau.
- [ ] Knockout an: kein Muster-Element schneidet die Text-Box (+ Rand); Knockout aus: Überlagerung.
- [ ] Text als `SketchText` erzeugt und in Fusion extrudierbar (getestet).
- [ ] Unbekannte Schriftart ⇒ Fallback Arial + Hinweis, kein Absturz.
- [ ] Datenmodell hält `textLayers` als Liste (auch wenn UI nur einen Layer bietet).

## I. Nachträgliches Bearbeiten
- [ ] PatternDoc wird als Attribut (Gruppe `PatternCreator`, mit `version`) an der Skizze gespeichert.
- [ ] „Muster bearbeiten": nur Muster-Skizzen wählbar; Editor startet mit exakt den gespeicherten Werten.
- [ ] Re-Commit ersetzt die Geometrie **in derselben Skizze**; eine zuvor darauf gebaute Extrusion rechnet neu, statt zu verwaisen (End-zu-End getestet: erzeugen → extrudieren → bearbeiten → prüfen).
- [ ] Warnhinweis vor Überschreiben, wenn die Skizze manuell verändert wurde (oder dokumentierte Einschränkung im README).
- [ ] *(Stretch)* CustomFeature: Muster als Timeline-Eintrag mit Doppelklick-Edit.

## J. Performance & Robustheit
- [ ] `isComputeDeferred` in `try/finally`; Wabe 20×20 in < 5 s; Voronoi 300 Zellen in < 10 s.
- [ ] Warnung mit Abbruch-Option ab > 2000 Skizzen-Entities vor dem Commit.
- [ ] Kein globales `random.seed()`; nur `random.Random(seed)`-Instanzen (Code-Grep).

## K. Tests & Doku
- [ ] `pytest tests/` läuft ohne Fusion durch; `core/`, `generators/`, `text/` importieren kein `adsk` (Code-Grep).
- [ ] Tests decken ab: Clipping aller Containerformen, Stroker (geschlossen, Gehrung), Kanten-Deduplizierung, Seed-Determinismus je Generator, PatternDoc-Roundtrip, Knockout, Fehler bei Größe 0, Schraffur (Scanline in konkaven Zellen, Verankerung, Notbremsen).
- [ ] README: Parameter-Referenz je Muster, manuelle Testmatrix mit Ergebnis, bekannte Einschränkungen (max. 500 Voronoi-Zellen, ein Text-Layer im UI, Knockout über Bounding-Box, Vorschau-Schrift ≈ Fusion-Schrift, Palette-Cache-Hinweis).

## L. Code-Qualität
- [ ] Neues Muster = neue Generator-Datei + Registry-Eintrag, keine Änderung an Editor/Command-Code (am Code nachgewiesen).
- [ ] Organische Zellen-Familie (Kiesel, Gewebe, Blattadern) teilt sich den `organic_cells`-Kern statt Copy-Paste.
- [ ] Generatoren und `core/` enthalten keine `adsk`-Aufrufe (Trennung IR ↔ Rendering).
- [ ] Jede Phase aus PLAN.md Abschnitt 11 als eigener Git-Commit nachvollziehbar.
