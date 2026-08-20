# PatternCreator – Review-Checkliste (v2)

Wird nach der Umsetzung Punkt für Punkt geprüft; jeder Punkt ist objektiv mit
„erfüllt / nicht erfüllt" bewertbar. Punkte mit *(Stretch)* gelten nur, wenn Phase 6 umgesetzt wurde.

## A. Projektstruktur & Installation
- [ ] Ordnerstruktur entspricht PLAN.md Abschnitt 2 (`commands/`, `core/`, `generators/`, `text/`, `fusion/`, `palette/`, `tests/`).
- [ ] Manifest ist gültiges JSON (`type: addin`, `supportedOS: windows|mac`).
- [ ] README beschreibt Installation für macOS **und** Windows.
- [ ] Keine externen Python-Pakete; Palette nutzt nur Vanilla JS/CSS (keine CDN-Links, offline lauffähig).

## B. Add-In-Lebenszyklus
- [ ] `run()` legt beide Buttons an („Muster erstellen", „Muster bearbeiten"); `stop()` entfernt Buttons, CommandDefinitions **und** die Palette rückstandsfrei (zweimal Laden/Entladen ohne Fehler/Duplikate).
- [ ] Alle Event-Handler (inkl. Palette-HTML-Events) global referenziert (GC-Schutz).
- [ ] Jeder Handler fängt Exceptions und zeigt eine verständliche Meldung.

## C. Editor (Palette)
- [ ] Palette öffnet mit Muster-Dropdown (alle 16 Muster, mit Piktogrammen), Canvas-Vorschau, Parametergruppen, Fußzeile.
- [ ] Vorschau aktualisiert live (debounced) und zeigt Containerumriss, Muster und Text-Layer lagerichtig; Zoom/Pan funktioniert.
- [ ] Formulare werden generisch aus den Parameter-Schemata erzeugt (neues Muster ⇒ kein UI-Code nötig – nachgewiesen am Code).
- [ ] Undo/Redo im Editor: Buttons + Cmd/Ctrl+Z bzw. +Shift+Z; mind. 50 Schritte; debounced (nicht pro Tastendruck ein Schritt).
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
- [ ] **Kiesel:** Rundheit (Chaikin) wirkt sichtbar, Fugenbreite wirkt, Kernpunkt-Option erzeugt Kreise je Zelle.
- [ ] **Zellgewebe:** Zellen länglich in Reihen (Anisotropie sichtbar), Reihenhöhe/Zelllänge wirken.
- [ ] **Wasser-Kaustik:** geglättete Kanten mit Dickenvariation; zweite Ebene zuschaltbar und mit eigenem Seed.
- [ ] **Blattadern:** zwei Hierarchiestufen sichtbar (Hauptadern dicker als Nebenadern), Parameter Grob-/Feinzellen wirken.
- [ ] **Fischgrät:** Rippenwinkel und -abstand wirken; 1 Achse = Palmwedel-Optik, n Achsen = Feld; Krümmung > 0 erzeugt Bögen.
- [ ] **Wellen:** Splines glatt; Wellenlänge/Amplitude/Abstand/Jitter wirken.
- [ ] **Schuppen:** Reihen versetzt und überlappend.
- [ ] **Phyllotaxis:** Goldener-Winkel-Spirale erkennbar; Elementform und Größenverlauf wirken.
- [ ] **Spiralen:** logarithmische Spiralen, Windungen/Anzahl/Streuung wirken, Drehrichtung mischbar.
- [ ] **Motiv-Streuung:** Blattmotiv parametrisch (schlank↔rund, Rippen); Raster-, Versatz- und Poisson-Streuung; Rotation/Größen-Jitter per Seed.
- [ ] Gleicher Seed ⇒ Vorschau, Commit und Re-Edit erzeugen identische Geometrie (bei allen Zufallsmustern stichprobenhaft geprüft).

## G. Stil, Dicke & Extrusion
- [ ] Linien- und Flächenmodus bei jedem Muster wählbar; Dicke wirkt im Flächenmodus überall.
- [ ] Flächenmodus erzeugt ausschließlich geschlossene, nicht selbst-schneidende Profile (Stichprobe: Wabe, Kiesel, Kaustik in Fusion extrudiert – ohne Profil-Fehler).
- [ ] Integrierte Extrusion: Tiefe/Richtung/Operation wählbar; „Stege vs. Zellen" wählbar; Ergebnis entspricht manueller Profilauswahl.
- [ ] Ein Commit = genau **ein** Timeline-Undo-Schritt (inkl. optionaler Extrusion).

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
- [ ] Tests decken ab: Clipping aller Containerformen, Stroker (geschlossen, Gehrung), Kanten-Deduplizierung, Seed-Determinismus je Generator, PatternDoc-Roundtrip, Knockout, Fehler bei Größe 0.
- [ ] README: Parameter-Referenz je Muster, manuelle Testmatrix mit Ergebnis, bekannte Einschränkungen (max. 500 Voronoi-Zellen, ein Text-Layer im UI, Knockout über Bounding-Box, Vorschau-Schrift ≈ Fusion-Schrift, Palette-Cache-Hinweis).

## L. Code-Qualität
- [ ] Neues Muster = neue Generator-Datei + Registry-Eintrag, keine Änderung an Editor/Command-Code (am Code nachgewiesen).
- [ ] Organische Zellen-Familie (Kiesel, Gewebe, Kaustik, Blattadern) teilt sich den `organic_cells`-Kern statt Copy-Paste.
- [ ] Generatoren und `core/` enthalten keine `adsk`-Aufrufe (Trennung IR ↔ Rendering).
- [ ] Jede Phase aus PLAN.md Abschnitt 11 als eigener Git-Commit nachvollziehbar.
