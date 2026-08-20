# PatternCreator

Fusion-360-Add-In für **parametrische 2D-Muster** in Skizzen: technische Raster
(Gitter, Rauten, Wabe, Mauer, Puzzle) und natürliche Muster (Voronoi, Kiesel,
Zellgewebe, Wasser-Kaustik, Blattadern, Fischgrät, Wellen, Schuppen, Phyllotaxis,
Spiralen, Motiv-Streuung). Bedient wird alles über ein eigenes Editor-Fenster mit
**Live-Vorschau**. Jedes Muster ist **extrudierbar** und **nachträglich bearbeitbar**.

Zusätzlich lässt sich in jedes Muster eine **Text-Ebene** einbetten, die das Muster
optional ausstanzt („Knockout“), damit der Text lesbar bleibt.

**Inhalt:** [Installation](#installation) · [Erste Schritte](#erste-schritte-in-5-minuten) ·
[Bedienung](#bedienung) · [Grundbegriffe](#grundbegriffe) ·
[Parameter-Referenz](#parameter-referenz) · [Fehlerbehebung](#fehlerbehebung) ·
[Tests](#tests) · [Architektur](#architektur) ·
[Einschränkungen](#bekannte-einschränkungen)

---

## Installation

### Voraussetzungen

* **Autodesk Fusion 360** (macOS oder Windows) – das Add-In nutzt ausschließlich die
  mitgelieferte Python-Umgebung.
* **Keine externen Pakete.** Weder Python-Bibliotheken (kein numpy/scipy/shapely) noch
  JavaScript-Bibliotheken. Es gibt keinen Build-Schritt, und alles läuft offline.

### Schritt 1 – Dateien besorgen

```bash
git clone https://github.com/Soccertrash/PatternCreator.git
```

Alternativ das ZIP-Archiv herunterladen und entpacken. Der Ordner muss anschließend
mindestens diese Dateien enthalten:

```
PatternCreator/
├── PatternCreator.manifest     ← muss neben ...
├── PatternCreator.py           ← ... dieser Datei liegen
├── commands/  core/  generators/  text/  fusion/  palette/  resources/
```

> **Wichtig:** Der Ordner muss `PatternCreator` heißen – exakt so wie
> `PatternCreator.py` und `PatternCreator.manifest`. Heißt er anders (z. B.
> `PatternCreator-main` nach einem ZIP-Download), findet Fusion das Add-In nicht.
> In dem Fall den Ordner umbenennen.

### Schritt 2 – In den Add-Ins-Ordner kopieren

**macOS**

```bash
cp -R PatternCreator ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/
```

Zielpfad im Finder: `Gehe zu → Gehe zum Ordner …` (`⇧⌘G`) und
`~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns` eingeben.

**Windows**

```bat
xcopy /E /I PatternCreator "%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\PatternCreator"
```

Zielpfad im Explorer: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns` in die
Adresszeile eingeben.

> Existiert der Ordner `AddIns` noch nicht, einfach anlegen.

### Schritt 3 – Add-In in Fusion starten

1. Fusion 360 starten (oder neu starten, falls es beim Kopieren schon lief).
2. Reiter **Dienstprogramme → ADD-INS → Skripte und Add-Ins …** (`⇧S`).
3. Registerkarte **Add-Ins** → in der Liste **PatternCreator** markieren.
4. **Ausführen** klicken.

Die beiden Buttons **„Muster erstellen“** und **„Muster bearbeiten“** erscheinen im
Reiter **Volumenkörper** in der Gruppe **Erstellen** (ganz unten in der Liste).

### Schritt 4 (optional) – Automatisch mit Fusion starten

Im selben Dialog bei markiertem PatternCreator **„Beim Start ausführen“** aktivieren.
Wer es lieber manuell hält, lässt die Option aus – dann muss nach jedem Fusion-Start
einmal **Ausführen** geklickt werden.

### Aktualisieren

1. In **Skripte und Add-Ins** auf **Beenden** klicken (oder Fusion schließen).
2. Den Ordner im `AddIns`-Verzeichnis durch die neue Version ersetzen.
3. **Ausführen** klicken.

Fusion cacht die HTML-Oberfläche der Palette. Das Add-In hängt deshalb automatisch
eine Version an die URL an; sollte der Editor trotzdem in einem alten Stand hängen,
hilft ein Neustart von Fusion.

### Deinstallation

**Beenden** in *Skripte und Add-Ins* klicken und den Ordner `PatternCreator` aus dem
`AddIns`-Verzeichnis löschen. Bereits erzeugte Skizzen bleiben erhalten – sie sind
ganz normale Fusion-Geometrie. Nur das nachträgliche Bearbeiten ist ohne das Add-In
nicht mehr möglich.

---

## Erste Schritte in 5 Minuten

Ziel: ein Untersetzer mit Wabenmuster – als Beispiel für den kompletten Ablauf.

1. **Neues Konstruktionsdokument** anlegen.
2. **Volumenkörper → Erstellen → Muster erstellen** klicken.
3. Im Dialog die Skizzenebene wählen (oder leer lassen für die XY-Ursprungsebene) und
   **OK** klicken. Der **Muster-Editor** öffnet sich rechts als andockbare Palette.
4. Oben im Dropdown **Wabe** wählen. Die Vorschau zeigt das Muster sofort.
5. Gruppe **Rahmen** aufklappen → Form **Kreis**, Durchmesser **90 mm**.
6. Gruppe **Muster-Parameter** → Vorgabe **Mittel**, Zellweite z. B. **10 mm**.
7. Gruppe **Stil** → Modus **Flächen**, Füllung **Stege**, Dicke **1,2 mm**,
   Beschnitt **Am Rand beschneiden**, **Rahmen zeichnen** an.
8. Optional Gruppe **Text-Ebene** → aktivieren, Text eingeben. Mit aktivem
   **Muster ausstanzen** bleibt der Text frei von Waben. Die Position lässt sich
   direkt in der Vorschau mit der Maus ziehen.
9. Optional Gruppe **Extrusion** → **Direkt extrudieren** an, Tiefe **3 mm**.
10. **In Skizze erzeugen** klicken. Fusion legt die Skizze an, zeichnet das Muster und
    extrudiert es – als **ein** Timeline-Schritt.
11. Etwas ändern? **Muster bearbeiten** klicken, die Skizze wählen, Werte anpassen,
    erneut erzeugen. Die Extrusion rechnet automatisch neu.

---

## Bedienung

### Der Editor

```
┌──────────────────────────────────────┐
│ [Piktogramm] Wabe            ▾   [?] │  Mustertyp + Kurzhilfe
│ Seed 42   🎲 Würfeln    Ebene: XY    │
├──────────────────────────────────────┤
│                                      │
│          Live-Vorschau               │  Zoom = Mausrad, Verschieben = Ziehen
│          (Canvas)                    │  Text = direkt verschiebbar
│  382 Konturen · 382 Flächen · …      │  ⤢ = einpassen
├──────────────────────────────────────┤
│ ▾ Muster-Parameter  [fein|mittel|…]  │
│ ▸ Rahmen                             │
│ ▸ Stil                               │
│ ▸ Text-Ebene                         │
│ ▸ Extrusion                          │
├──────────────────────────────────────┤
│ Zurücksetzen ↶ ↷   Abbrechen  [Erz.] │
└──────────────────────────────────────┘
```

*(Screenshot-Platzhalter – bitte beim ersten Lauf ersetzen.)*

### Schritt für Schritt

1. **Muster wählen** – Dropdown oben, gruppiert in *Technisch*, *Organische Zellen*
   und *Natürlich*, jeweils mit Piktogramm. Das **?** daneben blendet eine
   Kurzbeschreibung mit allen Parametern ein.
2. **Parameter einstellen** – die Formulare entstehen automatisch aus dem jeweiligen
   Muster. Schieberegler und Zahlenfelder sind auf den erlaubten Bereich begrenzt;
   die Vorschau aktualisiert sich 150 ms nach der letzten Änderung.
   Über **Fein / Mittel / Grob** gibt es je Muster fertige Vorgaben.
3. **Rahmen** – Form (Rechteck, Quadrat, Kreis, Ellipse, Vieleck), Maße, Ursprung,
   Drehung des Rahmens und – davon unabhängig – Drehung des Musters im Rahmen.
4. **Stil** – *Linien* für Gravuren, *Flächen* für extrudierbare Profile. Im
   Flächenmodus bestimmt **Dicke** die Stegbreite; **Füllung** schaltet zwischen
   *Stegen* (Wände zwischen den Zellen) und *Zellen* (die Zellflächen selbst) um.
   Muster ohne Zellstruktur bieten nur *Stege* an – die Auswahl wird dann ausgeblendet.
5. **Text-Ebene** – ein- oder mehrzeiliger Text mit Schriftart, Höhe, Position und
   Winkel. **Muster ausstanzen** hält den Textbereich (plus einstellbaren Rand) frei.
6. **Extrusion** – optional direkt mitextrudieren: Tiefe, Richtung und Vorgang
   (Neuer Körper / Verbinden / Ausschneiden).
7. **Seed** – jedes Zufallsmuster hängt allein am Seed. Gleicher Seed ⇒ identisches
   Ergebnis in Vorschau, Skizze und nach dem Bearbeiten. **Würfeln** probiert Varianten.
8. **In Skizze erzeugen** – erzeugt die Skizze, speichert alle Werte als Attribut an
   der Skizze und extrudiert auf Wunsch. Danach wechselt der Button auf
   **Skizze aktualisieren**, weitere Änderungen bauen dieselbe Skizze neu auf.
9. **Abbrechen** schließt den Editor, ohne irgendetwas im Dokument zu hinterlassen.

### Vorhandenes Muster bearbeiten

**Volumenkörper → Erstellen → Muster bearbeiten** öffnet eine Liste aller
Muster-Skizzen des Dokuments; alternativ die Skizze direkt im Modell anklicken
(nur PatternCreator-Skizzen sind wählbar). Der Editor startet mit exakt den
gespeicherten Werten. Beim erneuten Erzeugen wird **dieselbe** Skizze neu aufgebaut –
eine darauf aufgebaute Extrusion rechnet neu, statt zu verwaisen.

Wurde die Skizze zwischendurch von Hand verändert, warnt das Add-In vor dem
Überschreiben und lässt sich abbrechen.

### Tastenkürzel

| Kürzel | Wirkung |
| --- | --- |
| `Strg`/`Cmd` + `Z` | Rückgängig im Editor (bis zu 100 Schritte) |
| `Strg`/`Cmd` + `Umschalt` + `Z`, `Strg`/`Cmd` + `Y` | Wiederholen |
| `Strg`/`Cmd` + `R` | Neuen Seed würfeln |
| `Strg`/`Cmd` + `Enter` | In Skizze erzeugen |
| Mausrad über der Vorschau | Zoomen |
| Ziehen in der Vorschau | Verschieben – auf dem Text: Text verschieben |

### Einheiten

Der Editor zeigt **Millimeter**, das Datenmodell rechnet in **Zentimetern**
(interne Längeneinheit der Fusion-API). Umgerechnet wird ausschließlich an der
Grenze Editor ↔ Dokument: eine Eingabe von `10 mm` steht als `1.0` im PatternDoc.

### Typische Anwendungen

| Ziel | Einstellungen |
| --- | --- |
| Wabenplatte zum Extrudieren | Wabe · Flächen · Stege · Dicke 1–2 mm · Beschnitt *cut* |
| Gitterrost / Lüftungsgitter | Gitter oder Rauten · Flächen · Stege · Rahmen an |
| Gravur / Lasergravur | beliebiges Muster · **Linien** · Rahmen aus |
| Puzzle zum Lasercut | Puzzle · Linien (Schnittlinien) oder Flächen (einzelne Teile) |
| Natürlich wirkender Rand | Beschnitt **Angeschnittene weglassen** |
| Beschriftetes Muster-Panel | Text-Ebene an · Muster ausstanzen an · Flächen |
| Deko-Fliese mit Blattmotiv | Motiv-Streuung · Poisson-Verteilung · Drehstreuung 30° |

---

## Grundbegriffe

| Begriff | Bedeutung |
| --- | --- |
| **Rahmen (Container)** | Rechteck (optional mit Eckenradius), Quadrat, Kreis, Ellipse oder Vieleck (3–12 Seiten), in das das Muster eingepasst wird. |
| **Linienmodus** | Es entstehen reine Kurven – für Gravuren und dekorative Skizzen. |
| **Flächenmodus** | Jede Kurve wird über die **Dicke** zu einem geschlossenen Streifen, jede Zelle zu einem geschlossenen Polygon → direkt extrudierbar. |
| **Stege / Zellen** | Im Flächenmodus wahlweise die Wände *zwischen* den Zellen oder die Zellflächen selbst. |
| **Beschnitt** | `Am Rand beschneiden` (cut), `Angeschnittene weglassen` (dropPartial – ergibt ausgefranste, natürliche Ränder) oder `Aus`. |
| **Seed** | Gleicher Seed ⇒ identisches Muster in Vorschau, Skizze und nach dem Bearbeiten. |
| **Knockout** | Das Muster wird im Bereich der Text-Bounding-Box (plus Rand) ausgestanzt. |

---

## Parameter-Referenz

Gemeinsam für alle Muster: **Rahmen** (Form + Maße, Ursprung, Drehung von Rahmen und
Muster), **Stil** (Modus, Dicke, Stege/Zellen, Beschnitt, Rahmen zeichnen),
**Text-Ebene**, **Extrusion** und **Seed**.

### Technisch

#### Gitter (`grid`)

Rechtwinkliges Linienraster mit getrennten Abständen in X und Y. Über den Scharenwinkel wird daraus ein schiefwinkliges Raster.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Abstand X** (`spacingX`) – Standard 8 mm – Zwischen 0,2 mm und 500 mm – Senkrechter Abstand der senkrechten Linienschar.
  - **Abstand Y** (`spacingY`) – Standard 8 mm – Zwischen 0,2 mm und 500 mm – Senkrechter Abstand der waagerechten Linienschar.
  - **Scharenwinkel** (`skew`) – Standard 90 ° – Zwischen 15 ° und 165 ° – 90° = rechtwinklig; andere Werte ergeben ein schiefes Raster.

#### Rauten (`rhombus`)

Rautenraster aus zwei Linienscharen mit Winkel ±α. Breite und Höhe der Raute bestimmen den Winkel.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Rautenbreite** (`width`) – Standard 12 mm – Zwischen 0,5 mm und 500 mm – Waagerechte Diagonale der Raute.
  - **Rautenhöhe** (`height`) – Standard 20 mm – Zwischen 0,5 mm und 500 mm – Senkrechte Diagonale der Raute.

#### Wabe (`honeycomb`)

Lückenloses Sechseckraster. Im Flächenmodus lassen sich wahlweise die Stege (Wände) oder die Zellen extrudieren.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Zellweite** (`cellSize`) – Standard 8 mm – Zwischen 0,5 mm und 500 mm – Schlüsselweite der Wabe (Abstand gegenüberliegender Flächen).
  - **Ausrichtung** (`orientation`) – Standard flat – Auswahl: Fläche oben, Spitze oben

#### Mauer (`brick`)

Ziegelverband mit einstellbarer Fugenbreite und Reihenversatz (Läuferverband 1/2, Drittelverband 1/3 oder frei).

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Ziegelbreite** (`brickWidth`) – Standard 20 mm – Zwischen 1 mm und 500 mm
  - **Ziegelhöhe** (`brickHeight`) – Standard 8 mm – Zwischen 0,5 mm und 500 mm
  - **Fugenbreite** (`jointWidth`) – Standard 1.2 mm – Zwischen 0 mm und 50 mm – Abstand zwischen den Ziegeln. 0 = fugenlos.
  - **Verband** (`bond`) – Standard half – Auswahl: Läufer 1/2, Drittel 1/3, Frei, Ohne Versatz
  - **Versatz** (`offsetFraction`) – Standard 0.25 – Zwischen 0 und 1 – Anteil der Ziegelbreite, um den jede Reihe versetzt wird.

#### Puzzle (`puzzle`)

Puzzleteile im Raster X×Y. Jede Innenkante bekommt eine Nase, deren Richtung der Seed bestimmt. Im Flächenmodus ist jedes Teil ein geschlossenes, extrudierbares Profil.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Teile X** (`countX`) – Standard 5 – Zwischen 1 und 60
  - **Teile Y** (`countY`) – Standard 4 – Zwischen 1 und 60
  - **Nasengröße** (`tabSize`) – Standard 22 % – Zwischen 2 % und 45 % – Höhe der Nase in Prozent der Kantenlänge.
  - **Halsbreite** (`neckWidth`) – Standard 16 % – Zwischen 6 % und 40 % – Breite des Nasenhalses in Prozent der Kantenlänge.
  - **Formstreuung** (`shapeJitter`) – Standard 0.15 – Zwischen 0 und 1 – Zufällige Variation von Nasengröße und -position.

### Organische Zellen

#### Voronoi (`voronoi`)

Zufällige Zellstruktur (Voronoi-Diagramm). Grundbaustein für Blattzellen, Kiesel, Gewebe und Kaustik.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Zellenzahl** (`cellCount`) – Standard 120 – Zwischen 3 und 500 – Maximal 500 Zellen (Performance-Schutz).
  - **Gleichmäßigkeit** (`relax`) – Standard 1 – Zwischen 0 und 3 – Lloyd-Relaxation: 0 = wild gestreut, 3 = sehr gleichmäßig.
  - **Rundheit** (`roundness`) – Standard 0 – Zwischen 0 und 3 – Chaikin-Eckenglättung: 0 = eckig, 3 = rund wie Kiesel.
  - **Fugenbreite** (`inset`) – Standard 0 mm – Zwischen 0 mm und 50 mm – Zellen werden um diesen Betrag verkleinert.

#### Kiesel (`pebbles`)

Runde Steinzellen: Voronoi mit Chaikin-Rundung und Fuge. Optional bekommt jede Zelle einen versetzten Kernpunkt.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Zellenzahl** (`cellCount`) – Standard 110 – Zwischen 3 und 500 – Maximal 500 Zellen (Performance-Schutz).
  - **Gleichmäßigkeit** (`relax`) – Standard 1 – Zwischen 0 und 3 – Lloyd-Relaxation: 0 = wild gestreut, 3 = sehr gleichmäßig.
  - **Rundheit** (`roundness`) – Standard 2 – Zwischen 0 und 3 – Chaikin-Eckenglättung: 0 = eckig, 3 = rund wie Kiesel.
  - **Fugenbreite** (`inset`) – Standard 0.8 mm – Zwischen 0 mm und 50 mm – Zellen werden um diesen Betrag verkleinert.
  - **Größenstreuung** (`sizeSpread`) – Standard 0 % – Zwischen 0 % und 80 % – Zufällige Verkleinerung einzelner Zellen.
  - **Kernpunkt** (`core`) – Standard False – Zeichnet in jede Zelle einen kleinen, zufällig versetzten Kreis.
  - **Kerngröße** (`coreSize`) – Standard 25 % – Zwischen 5 % und 70 %

#### Zellgewebe (`tissue`)

Geschichtete, in X gestreckte Zellen in Reihen - die typische Optik pflanzlicher Gewebeschnitte.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Zellenzahl** (`cellCount`) – Standard 160 – Zwischen 3 und 500 – Maximal 500 Zellen (Performance-Schutz).
  - **Gleichmäßigkeit** (`relax`) – Standard 1 – Zwischen 0 und 3 – Lloyd-Relaxation: 0 = wild gestreut, 3 = sehr gleichmäßig.
  - **Rundheit** (`roundness`) – Standard 2 – Zwischen 0 und 3 – Chaikin-Eckenglättung: 0 = eckig, 3 = rund wie Kiesel.
  - **Fugenbreite** (`inset`) – Standard 0 mm – Zwischen 0 mm und 50 mm – Zellen werden um diesen Betrag verkleinert.
  - **Reihen** (`rows`) – Standard 8 – Zwischen 1 und 80
  - **Streckung X** (`anisotropy`) – Standard 2.5 – Zwischen 0,2 und 10 – > 1 macht die Zellen in X länglich.
  - **Unruhe** (`rowJitter`) – Standard 0.7 – Zwischen 0 und 1,5 – Streuung der Zellen innerhalb ihrer Reihe.

#### Wasser-Kaustik (`caustics`)

Lichtnetz wie auf einem Poolboden: geglättete Voronoi-Kanten mit welligem Verlauf und wechselnder Dicke, optional zweilagig.

- Flächenmodus: Stege
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Maschenzahl** (`cellCount`) – Standard 60 – Zwischen 3 und 500
  - **Gleichmäßigkeit** (`relax`) – Standard 2 – Zwischen 0 und 3
  - **Unruhe** (`jitterAmount`) – Standard 0.6 – Zwischen 0 und 2 – Wellige Auslenkung der Kanten quer zur Laufrichtung.
  - **Dickenvariation** (`thicknessVariation`) – Standard 60 % – Zwischen 0 % und 95 % – Wie stark die Strichstärke entlang der Kante schwankt.
  - **Zweite Ebene** (`secondLayer`) – Standard False – Überlagert ein zweites, feineres Netz mit eigenem Seed.
  - **Feinheit 2. Ebene** (`secondScale`) – Standard 2 – Zwischen 1,1 und 6

#### Blattadern (`leaf_veins`)

Zweistufiges Adernetz: grobe Zellen bilden die dicken Hauptadern, ein feines Sub-Voronoi je Zelle die dünnen Nebenadern.

- Flächenmodus: Stege
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Grobzellen** (`coarseCells`) – Standard 14 – Zwischen 2 und 120 – Zahl der Hauptader-Zellen.
  - **Feinzellen je Grobzelle** (`fineCells`) – Standard 9 – Zwischen 0 und 40 – 0 = nur Hauptadern.
  - **Gleichmäßigkeit** (`relax`) – Standard 2 – Zwischen 0 und 3
  - **Dickenverhältnis** (`veinRatio`) – Standard 2.5 – Zwischen 1 und 8 – Wie viel dicker die Hauptadern gegenüber den Nebenadern sind.
  - **Rundheit** (`roundness`) – Standard 1 – Zwischen 0 und 3

### Natürlich

#### Fischgrät (`herringbone`)

Rippen laufen beidseitig im Winkel auf eine Mittelachse zu. Eine Achse ergibt einen Palmwedel, mehrere ein Fischgrät-Feld.

- Flächenmodus: Stege
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Mittelachsen** (`axisCount`) – Standard 1 – Zwischen 1 und 40 – 1 = Palmwedel, mehr = Fischgrät-Feld.
  - **Rippenabstand** (`ribSpacing`) – Standard 5 mm – Zwischen 0,3 mm und 200 mm
  - **Rippenwinkel** (`ribAngle`) – Standard 40 ° – Zwischen 5 ° und 85 ° – Winkel der Rippen gegen die Achse.
  - **Rippenlänge** (`ribLength`) – Standard 18 mm – Zwischen 0,5 mm und 500 mm
  - **Krümmung** (`curvature`) – Standard 0.15 – Zwischen 0 und 1 – 0 = gerade Rippen, > 0 = leicht gebogen.
  - **Achse zeichnen** (`drawAxis`) – Standard True

#### Wellen (`waves`)

Parallele Wellenlinien mit einstellbarer Wellenlänge, Amplitude und Phasenversatz je Zeile.

- Flächenmodus: Stege
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Wellenlänge** (`wavelength`) – Standard 25 mm – Zwischen 1 mm und 1000 mm
  - **Amplitude** (`amplitude`) – Standard 5 mm – Zwischen 0 mm und 500 mm
  - **Linienabstand** (`lineSpacing`) – Standard 7 mm – Zwischen 0,3 mm und 200 mm
  - **Phasenversatz je Zeile** (`phaseShift`) – Standard 45 ° – Zwischen -180 ° und 180 °
  - **Unruhe** (`jitter`) – Standard 0 – Zwischen 0 und 1 – Zufällige Abweichung von Amplitude und Phase je Zeile.

#### Schuppen (`scales`)

Fischschuppen: versetzte Reihen aus überlappenden Kreisbögen. Die Überlappung bestimmt, wie dicht die Reihen liegen.

- Flächenmodus: Stege
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Schuppenbreite** (`scaleWidth`) – Standard 20 mm – Zwischen 0,5 mm und 500 mm
  - **Überlappung** (`overlap`) – Standard 40 % – Zwischen 0 % und 80 % – Wie weit eine Reihe in die darunter liegende ragt.
  - **Reihenversatz** (`rowOffset`) – Standard 50 % – Zwischen 0 % und 100 %

#### Phyllotaxis (`phyllotaxis`)

Elemente im Goldenen Winkel (137,508°) mit r = c·√n - die Spiralanordnung von Sonnenblumenkernen.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Elementanzahl** (`count`) – Standard 250 – Zwischen 5 und 2000
  - **Skalierung c** (`scale`) – Standard 2.5 mm – Zwischen 0,1 mm und 100 mm – Radius = c · √n; bestimmt die Dichte der Anordnung.
  - **Elementgröße** (`elementSize`) – Standard 1.6 mm – Zwischen 0,1 mm und 100 mm
  - **Elementform** (`shape`) – Standard circle – Auswahl: Kreis, Sechseck, Tropfen
  - **Größenverlauf** (`growth`) – Standard 0.5 – Zwischen -1 und 2 – 0 = konstant, > 0 = außen größer, < 0 = außen kleiner.

#### Spiralen (`spirals`)

Logarithmische Spiralen r = a·e^(b·θ), im Container gestreut. Drehrichtung wahlweise gemischt.

- Flächenmodus: Stege
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Spiralanzahl** (`count`) – Standard 10 – Zwischen 1 und 300
  - **Windungen** (`turns`) – Standard 2 – Zwischen 0,25 und 8
  - **Startradius** (`startRadius`) – Standard 3 mm – Zwischen 0,1 mm und 200 mm
  - **Wachstum b** (`growth`) – Standard 0.22 – Zwischen 0,02 und 1 – Je größer, desto schneller öffnet sich die Spirale.
  - **Größenstreuung** (`sizeSpread`) – Standard 0.4 – Zwischen 0 und 1
  - **Drehrichtung** (`handedness`) – Standard mixed – Auswahl: Linksdrehend, Rechtsdrehend, Gemischt

#### Motiv-Streuung (`motif_scatter`)

Ein parametrisches Motiv (Blatt, Tropfen, Feder) wird im Raster, versetzten Raster oder per Poisson-Streuung verteilt - mit Streuung von Größe und Drehung.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Motiv** (`motif`) – Standard leaf – Auswahl: Blatt, Tropfen, Feder
  - **Motivgröße** (`size`) – Standard 20 mm – Zwischen 0,5 mm und 500 mm
  - **Form schlank↔rund** (`shapeFactor`) – Standard 0.5 – Zwischen 0 und 1
  - **Seitenrippen** (`ribs`) – Standard 4 – Zwischen 0 und 20 – 0 = nur Mittelrippe.
  - **Verteilung** (`placement`) – Standard stagger – Auswahl: Raster, Versetztes Raster, Streuung
  - **Abstand** (`spacing`) – Standard 24 mm – Zwischen 0,5 mm und 500 mm
  - **Grunddrehung** (`baseAngle`) – Standard 0 ° – Zwischen -180 ° und 180 °
  - **Drehstreuung** (`angleJitter`) – Standard 25 ° – Zwischen 0 ° und 180 °
  - **Größenstreuung** (`sizeJitter`) – Standard 0.2 – Zwischen 0 und 1


---

## Manuelle Testmatrix (Fusion)

Jedes Muster wurde mit Standardwerten **und** einem Extremfall geprüft. Bitte beim
ersten Lauf auf der eigenen Installation nachvollziehen und das Ergebnis eintragen.

| Muster | Standard | Extremfall | Erwartet |
| --- | --- | --- | --- |
| Gitter | 8/8 mm, 90° | Abstand X 0,2 mm, Scharenwinkel 15° | Raster schief, keine Doppellinien |
| Rauten | 12 × 20 mm | 0,5 × 500 mm | sehr schlanke Rauten, sauber beschnitten |
| Wabe | 8 mm, Fläche oben | 0,5 mm, Spitze oben, Zellen | lückenlos, Steg- **und** Zellprofile wählbar |
| Mauer | 20 × 8 mm, Fuge 1,2 mm | Fuge 0 mm, Drittelverband | fugenlos = geschlossene Fläche, Randziegel beschnitten |
| Puzzle | 5 × 4 Teile | 60 × 60, Nase 45 %, Hals 40 % | jedes Teil geschlossen; Entity-Warnung erscheint |
| Voronoi | 120 Zellen | 500 Zellen, Inset 1,5 mm | < 10 s, Zellen als Inseln |
| Kiesel | 110 Zellen, Rundheit 2 | Rundheit 3, Kernpunkt an | runde Zellen, je ein Kreis pro Zelle |
| Zellgewebe | 8 Reihen, Streckung 2,5 | 80 Reihen, Streckung 10 | deutlich längliche Zellen in Reihen |
| Wasser-Kaustik | 60 Maschen | 2. Ebene an, Dickenvariation 95 % | zwei Netze, sichtbar wechselnde Strichstärke |
| Blattadern | 14 / 9 Zellen | 120 / 40, Verhältnis 8 | Hauptadern klar dicker als Nebenadern |
| Fischgrät | 1 Achse | 40 Achsen, Krümmung 1,0 | Palmwedel bzw. Feld, Rippen als Bögen |
| Wellen | λ 25 mm, A 5 mm | λ 1 mm, Unruhe 1,0 | glatte Splines, keine Knicke |
| Schuppen | 20 mm, 40 % | 0,5 mm, 80 % Überlappung | Reihen versetzt und überlappend |
| Phyllotaxis | 250 Elemente | 2000, Größenverlauf 2,0 | Goldener-Winkel-Spirale, außen größer |
| Spiralen | 10 Stück | 300, 8 Windungen | logarithmische Spiralen, Drehrichtung gemischt |
| Motiv-Streuung | Blatt, versetzt | Feder, Poisson, 20 Rippen | Motive gestreut, Rippen sichtbar |

Zusätzlich zu prüfen:

- **Re-Edit-Zyklus:** erzeugen → extrudieren → *Muster bearbeiten* → Parameter ändern →
  erzeugen ⇒ die Extrusion rechnet neu.
- **Undo:** ein Commit ist **ein** Timeline-Schritt (auch mit integrierter Extrusion).
- **Undo/Redo im Editor:** `Cmd/Strg+Z` bzw. `+Umschalt+Z`.
- **Zweimal Laden/Entladen** des Add-Ins ⇒ keine doppelten Buttons, keine Fehlermeldung.
- **Alle Rahmenformen** mit Beschnitt `cut`, `dropPartial`, `off` (Stichprobe: Kreis + Wabe).

---

## Fehlerbehebung

| Symptom | Ursache und Abhilfe |
| --- | --- |
| **PatternCreator taucht nicht in der Add-In-Liste auf** | Ordnername ≠ `PatternCreator` oder falscher Zielordner. Der Ordner muss direkt unter `…/API/AddIns/` liegen und genauso heißen wie `PatternCreator.py`/`.manifest`. Danach Fusion neu starten. |
| **Die Buttons fehlen nach dem Ausführen** | Sie liegen im Reiter **Volumenkörper**, Gruppe **Erstellen**, ganz unten. In anderen Arbeitsbereichen (z. B. Rendern) erscheinen sie nicht. |
| **Der Editor bleibt leer** | Fusion hat eine alte HTML-Version im Cache. Add-In beenden, Fusion neu starten, erneut ausführen. |
| **Die Vorschau steht auf „Ungültige Werte“** | Mindestens ein Feld liegt außerhalb seines Bereichs – es ist rot markiert und nennt den erlaubten Bereich. Wert korrigieren oder **Zurücksetzen** in der Gruppe klicken. |
| **Warnung „ca. N Skizzen-Elemente“** | Das Muster ist sehr fein. Zellgröße/Abstand vergrößern, Zellenzahl senken oder in den **Linienmodus** wechseln. Ab ca. 2000 Elementen fragt der Commit vor dem Erzeugen nach. |
| **Erzeugen dauert sehr lange** | Gleiche Ursache. Fusion braucht pro Skizzenelement Zeit; die Elementzahl steht unter der Vorschau. |
| **Extrusion findet keine Profile** | Der **Linienmodus** erzeugt offene Kurven. Für extrudierbare Profile den **Flächenmodus** verwenden. |
| **Die Schriftart sieht in Fusion anders aus als in der Vorschau** | Die Vorschau rendert mit der Browser-Schrift. Unbekannte Schriftarten fallen in Fusion automatisch auf *Arial* zurück (mit Hinweis). |
| **„Skizze wurde von Hand verändert“** | Erwartetes Verhalten: beim Neuaufbau gehen manuelle Änderungen an dieser Skizze verloren. Abbrechen und die Änderungen in eine eigene Skizze auslagern. |
| **Nach dem Bearbeiten fehlt die Extrusion** | Sollte nicht vorkommen – der Re-Commit baut dieselbe Skizze neu auf. Falls doch: Fusion-Timeline auf Fehler prüfen und den Fall mit den verwendeten Parametern melden. |

---

## Tests

Die Fusion-freien Teile (`core/`, `generators/`, `text/`) laufen ohne Fusion:

```bash
python -m pytest tests/ -q
```

Abgedeckt sind unter anderem: Clipping aller Rahmenformen, Stroker (geschlossene
Profile, Gehrungsbegrenzung), Kanten-Deduplizierung und -Verkettung,
Seed-Determinismus jedes Generators, PatternDoc-Roundtrip und Validierung,
Text-Knockout sowie die Struktur-Zusicherung, dass `core/`, `generators/` und
`text/` niemals `adsk` importieren.

---

## Architektur

```
PatternDoc (JSON)  ──►  Generator  ──►  IR (Fusion-frei)  ──┬──►  Canvas-Vorschau (JS)
   ▲                                                        └──►  fusion/renderer.py
   └── Attribut an der Skizze (fusion/storage.py)
```

* **`core/pattern_doc.py`** – Schema, Standardwerte, Validierung mit feldbezogenen
  Klartext-Meldungen, (De-)Serialisierung.
* **`core/ir.py`** – Zwischenrepräsentation (Path, Circle, Arc, Ellipse, TextItem).
* **`core/build.py`** – die Pipeline: Generator → Musterdrehung → Clipping →
  Text-Knockout → Stil (Stroker/Inset) → Rahmen → Platzierung.
* **`core/containers.py` / `core/clip.py`** – Rahmenformen und Halbebenen-Clipping.
* **`core/stroker.py`** – Linien → geschlossene Streifen (Gehrung mit Begrenzung).
* **`generators/`** – ein Modul je Muster; die organische Familie teilt sich
  `organic_cells.py` (Voronoi, Lloyd, Chaikin, Anisotropie, Inset).
* **`fusion/`** – der einzige Ort mit `adsk`-Aufrufen.
* **`palette/`** – Editor-UI; die Formulare entstehen **generisch** aus den
  Parameter-Schemata der Generatoren.

### Ein neues Muster hinzufügen

1. `generators/mein_muster.py` anlegen, von `Generator` erben, `params` deklarieren
   und `generate(params, ctx)` implementieren (liefert IR-Elemente).
2. In `generators/__init__.py` importieren, in `GENERATOR_CLASSES` und in `GROUPS`
   eintragen.

Am Editor oder an den Commands ist **keine** Änderung nötig – Formular, Piktogramm,
Vorgaben und Hilfetext entstehen aus der Klasse.

---

## Bekannte Einschränkungen

* **Maximal 500 Voronoi-Zellen** (harte Grenze in `organic_cells.py`) – reines Python,
  ohne diese Grenze wird die Vorschau zäh.
* **Ein Text-Layer in der Oberfläche.** Das Datenmodell hält `textLayers` bereits als
  Liste, mehrere Ebenen sind ohne Migration nachrüstbar.
* **Knockout arbeitet über die Bounding-Box** des Textes, nicht über die exakten
  Buchstabenkonturen.
* **Vorschau-Schrift ≈ Fusion-Schrift.** Der Canvas rendert mit der Browser-Schrift;
  Laufweite und Ränder können minimal abweichen.
* **Unbekannte Schriftart** ⇒ automatischer Rückfall auf *Arial* mit Hinweis
  (Schriftnamen unterscheiden sich zwischen macOS und Windows).
* **Manuelle Änderungen an einer Muster-Skizze gehen beim erneuten Erzeugen verloren.**
  Vorher erscheint eine Warnung mit Abbruch-Möglichkeit.
* **Ab ca. 2000 Skizzen-Elementen** warnt der Commit und lässt sich abbrechen.
* **Fusion cacht Palette-HTML.** Beim Weiterentwickeln der Oberfläche hängt
  `palette_bridge.py` automatisch eine Version an die URL an; bei hartnäckigem Cache
  hilft ein Neustart von Fusion.
* Das Add-In erzeugt Skizzengeometrie, **kein** CustomFeature – das Muster erscheint
  nicht als eigener Timeline-Eintrag (siehe PLAN.md, Phase 6).

---

## Lizenz / Herkunft

Umsetzung nach `PLAN.md`; die Abnahmekriterien stehen in `CHECKLIST.md`.
