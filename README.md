# PatternCreator

*🇬🇧 [English version below](#english) — the same documentation in English.*

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

Ohne diesen Schritt gibt es **keine** Buttons in der Oberfläche – im Manifest steht
`runOnStartup: false`, Fusion lädt das Add-In also nicht von allein.

1. Fusion 360 starten (oder neu starten, falls es beim Kopieren schon lief).
2. Reiter **Dienstprogramme → ADD-INS → Skripte und Add-Ins …** (`⇧S`) –
   englische Oberfläche: **UTILITIES → ADD-INS → Scripts and Add-Ins …**
3. Registerkarte **Add-Ins** (nicht *Skripte*) → in der Liste **PatternCreator**
   markieren.
4. **Ausführen** klicken (englisch: **Run**).

Die beiden Buttons **„Muster erstellen“** und **„Muster bearbeiten“** erscheinen
danach im Reiter **Volumenkörper**, Gruppe **Erstellen** – englische Oberfläche:
Reiter **SOLID**, Gruppe **CREATE**. Sie stehen **ganz unten**; sind sie in der
Icon-Reihe nicht zu sehen, auf **Erstellen ▾** / **CREATE ▾** klicken – dort sind
sie die letzten Einträge der Klappliste.

> Die Beschriftung der Buttons bleibt deutsch, auch bei englischer
> Fusion-Oberfläche.

### Schritt 4 (optional) – Automatisch mit Fusion starten

Im selben Dialog bei markiertem PatternCreator **„Beim Start ausführen“**
(englisch: **Run on Startup**) aktivieren.
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

0. **Läuft das Add-In schon?** Falls nicht, zuerst
   [Schritt 3 der Installation](#schritt-3--add-in-in-fusion-starten) ausführen –
   sonst gibt es die Buttons nicht.
1. **Neues Konstruktionsdokument** anlegen.
2. **Volumenkörper → Erstellen → Muster erstellen** klicken (englische Oberfläche:
   **SOLID → CREATE → Muster erstellen**, ganz unten in der Klappliste **CREATE ▾**).
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
   **Rahmendicke** legt die Breite des geschlossenen Randes fest; sie wird **nach
   innen** gemessen, das eingestellte Rahmenmaß bleibt also das Außenmaß.
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

**Volumenkörper → Erstellen → Muster bearbeiten** (englisch: **SOLID → CREATE**)
öffnet eine Liste aller
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
| **Eine Fläche** | Bei den kachelnden Mustern (Gitter, Rauten, Wabe, Mauer, Puzzle, Voronoi, Kiesel, Zellgewebe) entsteht im Flächenmodus mit *Stegen* **eine** zusammenhängende Kontur mit Löchern statt vieler Einzelstreifen – ein Klick genügt zum Auswählen, und der Körper ist dicht. Voraussetzung: **Rahmen zeichnen** an, Beschnitt ≠ *Aus*. |

---

## Eine Fläche statt vieler Streifen

Bei **kachelnden** Mustern – Gitter, Rauten, Wabe, Mauer, Puzzle, Voronoi, Kiesel,
Zellgewebe – ist das Stegnetz exakt *Rahmen minus verkleinerte Zellen*. Das Add-In
erzeugt deshalb genau **eine** Außenkontur mit Löchern statt vieler sich
überlappender Streifen:

* **Auswählen mit einem Klick** – in Fusion ist das ganze Muster ein Profil.
* **Keine Überlappungen** an den Knotenpunkten, keine doppelten Kanten.
* **3D-druckbar** – der extrudierte Körper ist dicht und ohne Selbstüberschneidung.
* **Weniger Skizzen-Elemente** – die Wabe im Beispiel: 1849 → 679 Entities.

Voraussetzung sind **Flächen** + **Stege**, **Rahmen zeichnen** an (der Rahmen *ist*
die Außenkontur) und ein Beschnitt ≠ *Aus*. Ohne Rahmen bleiben die Stege einzelne
Streifen und enden offen am Rand – für Gravuren gewollt.

Die Stegbreite ist die eingestellte **Dicke**. Bringt ein Muster eine eigene Fuge mit
(Mauer: *Fugenbreite*, Voronoi/Kiesel/Zellgewebe: *Fugenbreite*), gilt die größere von
beiden – so bleiben die Ziegelmaße exakt. Angeschnittene Randzellen, die nur noch
einen hauchdünnen Splitter ergäben, werden zugemacht: im Druck wären das nicht
darstellbare Kanten.

**Strich-Muster** ohne Zellen (Fischgrät, Wellen, Schuppen, Phyllotaxis, Spiralen,
Motiv-Streuung, Kaustik, Blattadern) bestehen weiterhin aus mehreren Streifen. Sie
lassen sich mit **Direkt extrudieren** trotzdem in einem Schritt zu **einem** Körper
verschmelzen; die einzelne Auswahl im Skizzen-Modus ist dort noch offen.

---

## Parameter-Referenz

Gemeinsam für alle Muster: **Rahmen** (Form + Maße, Ursprung, Drehung von Rahmen und
Muster), **Stil** (Modus, Dicke, Stege/Zellen, Beschnitt, Rahmen zeichnen,
**Rahmendicke**), **Text-Ebene**, **Extrusion** und **Seed**.

Die **Rahmendicke** (`style.borderWidth`, Standard 1,5 mm) wirkt im Flächenmodus und
wird nach innen gemessen: ein Kreisrahmen mit 90 mm bleibt außen 90 mm groß.

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

Puzzleteile im Raster X×Y. Jede Innenkante bekommt eine klassische Nase: runder Kopf an einem schmalen Hals, mit dem typischen Unterschnitt am Fuß. Der Kopf ist ein **echter Kreis** und rund 1,75-mal so breit wie der Hals – nur so greifen die Teile ineinander. Die Richtung jeder Nase bestimmt der Seed.

- Flächenmodus: Stege, Zellen
- Vorgaben: fein, mittel, grob
- Parameter:
  - **Teile X** (`countX`) – Standard 5 – Zwischen 1 und 60
  - **Teile Y** (`countY`) – Standard 4 – Zwischen 1 und 60
  - **Nasengröße** (`tabSize`) – Standard 28 % – Zwischen 2 % und 45 % – Gesamthöhe der Nase (Hals + Kopf) in Prozent der Kantenlänge. Zu kleine Werte werden auf die Kopfgröße angehoben.
  - **Halsbreite** (`neckWidth`) – Standard 18 % – Zwischen 6 % und 40 % – Breite des Nasenhalses in Prozent der Kantenlänge; der Kopf ergibt sich daraus.
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
| Puzzle | 5 × 4 Teile | 60 × 60, Nase 45 %, Hals 40 % | runder Kopf am schmalen Hals, Teile greifen ineinander; Entity-Warnung erscheint |
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
| **Die Buttons fehlen komplett** | Das Add-In läuft nicht. Wegen `runOnStartup: false` muss es nach jedem Fusion-Start einmal über **Dienstprogramme → ADD-INS → Skripte und Add-Ins … → Add-Ins → Ausführen** gestartet werden (englisch: **UTILITIES → ADD-INS → Scripts and Add-Ins …**). Dauerhaft: **Beim Start ausführen** aktivieren. |
| **Die Buttons fehlen nach dem Ausführen** | Sie liegen im Reiter **Volumenkörper**, Gruppe **Erstellen**, ganz unten – englische Oberfläche: **SOLID → CREATE**, notfalls die Klappliste **CREATE ▾** aufklappen. In anderen Arbeitsbereichen (z. B. Rendern) erscheinen sie nicht. |
| **Der Editor bleibt leer (kein Muster in der Auswahlliste)** | Die Palette hatte beim ersten Öffnen noch keine Verbindung zu Fusion. Ab Version 1.0.1 fragt der Editor selbstständig nach, bis die Daten ankommen. Bleibt es bei einer älteren Version leer: Editor schließen und **Muster erstellen** erneut klicken. |
| **Der Editor zeigt eine alte Oberfläche** | Fusion hat eine alte HTML-Version im Cache. Add-In beenden, Fusion neu starten, erneut ausführen. |
| **Die Vorschau steht auf „Ungültige Werte“** | Mindestens ein Feld liegt außerhalb seines Bereichs – es ist rot markiert und nennt den erlaubten Bereich. Wert korrigieren oder **Zurücksetzen** in der Gruppe klicken. |
| **Warnung „ca. N Skizzen-Elemente“** | Das Muster ist sehr fein. Zellgröße/Abstand vergrößern, Zellenzahl senken oder in den **Linienmodus** wechseln. Ab ca. 2000 Elementen fragt der Commit vor dem Erzeugen nach. |
| **Erzeugen dauert sehr lange** | Gleiche Ursache. Fusion braucht pro Skizzenelement Zeit; die Elementzahl steht unter der Vorschau. |
| **Das Muster lässt sich nicht in einem Zug auswählen** | Für die zusammenhängende Fläche müssen **Flächen** + **Stege** eingestellt, **Rahmen zeichnen** aktiv und der Beschnitt ≠ *Aus* sein. Strich-Muster (Wellen, Spiralen, Fischgrät, Schuppen, Kaustik, Blattadern, Phyllotaxis, Motiv-Streuung) bleiben mehrteilig – dort **Direkt extrudieren** verwenden, das verschmilzt alle Profile zu einem Körper. |
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
* **Strich-Muster ergeben noch keine einzelne Fläche.** Fischgrät, Wellen, Schuppen,
  Phyllotaxis, Spiralen, Motiv-Streuung, Kaustik und Blattadern haben keine Zellen;
  ihre Streifen überlappen sich echt. Eine einzelne Fläche bräuchte eine Boolesche
  Vereinigung (siehe `PLAN.md`, Abschnitt 13, Stufe 2). Beim Extrudieren entsteht
  trotzdem **ein** Körper.
* Das Add-In erzeugt Skizzengeometrie, **kein** CustomFeature – das Muster erscheint
  nicht als eigener Timeline-Eintrag (siehe PLAN.md, Phase 6).

---

## Lizenz / Herkunft

Umsetzung nach `PLAN.md`; die Abnahmekriterien stehen in `CHECKLIST.md`.

---

<a id="english"></a>

# PatternCreator — English

Fusion 360 add-in for **parametric 2D patterns** in sketches: technical grids
(grid, rhombus, honeycomb, brick, puzzle) and natural patterns (Voronoi, pebbles,
tissue, water caustics, leaf veins, herringbone, waves, scales, phyllotaxis,
spirals, motif scatter). Everything is driven from a dedicated editor window with a
**live preview**. Every pattern is **extrudable** and **re-editable afterwards**.

On top of that, a **text layer** can be embedded into any pattern; it optionally
knocks the pattern out around the text so the lettering stays readable.

> **Note on language:** the add-in's user interface is **German only** — the ribbon
> buttons are labelled „Muster erstellen“ / „Muster bearbeiten“ and the editor
> palette is in German, no matter which language Fusion itself runs in. The
> parameter reference below lists the English meaning together with the German
> label you see on screen and the internal key.

**Contents:** [Setup](#setup-and-installation) · [Quick start](#quick-start-in-5-minutes) ·
[Using the add-in](#using-the-add-in) · [Concepts](#concepts) ·
[Parameter reference](#parameter-reference) · [Troubleshooting](#troubleshooting) ·
[Tests](#running-the-tests) · [Architecture](#architecture) ·
[Limitations](#known-limitations)

---

## Setup and installation

### Requirements

* **Autodesk Fusion 360** (macOS or Windows) — the add-in uses nothing but the
  bundled Python runtime.
* **No external packages.** Neither Python libraries (no numpy/scipy/shapely) nor
  JavaScript libraries. There is no build step and everything runs offline.

### Step 1 – Get the files

```bash
git clone https://github.com/Soccertrash/PatternCreator.git
```

Alternatively download and unpack the ZIP archive. The folder must then contain at
least these files:

```
PatternCreator/
├── PatternCreator.manifest     ← must sit next to ...
├── PatternCreator.py           ← ... this file
├── commands/  core/  generators/  text/  fusion/  palette/  resources/
```

> **Important:** the folder must be named `PatternCreator` — exactly like
> `PatternCreator.py` and `PatternCreator.manifest`. If it is named anything else
> (e.g. `PatternCreator-main` after a ZIP download), Fusion will not find the
> add-in. Rename the folder in that case.

### Step 2 – Copy into the Add-Ins folder

**macOS**

```bash
cp -R PatternCreator ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/
```

Target path in Finder: `Go → Go to Folder …` (`⇧⌘G`) and enter
`~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`.

**Windows**

```bat
xcopy /E /I PatternCreator "%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\PatternCreator"
```

Target path in Explorer: type `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns`
into the address bar.

> If the `AddIns` folder does not exist yet, simply create it.

### Step 3 – Start the add-in in Fusion

Without this step there are **no** buttons in the interface — the manifest says
`runOnStartup: false`, so Fusion does not load the add-in on its own.

1. Start Fusion 360 (or restart it if it was already running while you copied).
2. Tab **UTILITIES → ADD-INS → Scripts and Add-Ins …** (`⇧S`) — German interface:
   **Dienstprogramme → ADD-INS → Skripte und Add-Ins …**
3. Switch to the **Add-Ins** tab (not *Scripts*) → select **PatternCreator** in the
   list.
4. Click **Run**.

The two buttons **„Muster erstellen“** (create pattern) and **„Muster bearbeiten“**
(edit pattern) then appear on the **SOLID** tab in the **CREATE** panel — German
interface: **Volumenkörper → Erstellen**. They sit at the very **bottom**; if you
cannot spot them in the icon row, click **CREATE ▾** — they are the last entries of
that drop-down list.

### Step 4 (optional) – Start automatically with Fusion

In the same dialog, with PatternCreator selected, tick **Run on Startup**. If you
prefer to keep it manual, leave it off — you then have to click **Run** once after
every Fusion start.

### Updating

1. Click **Stop** in *Scripts and Add-Ins* (or close Fusion).
2. Replace the folder in the `AddIns` directory with the new version.
3. Click **Run**.

Fusion caches the palette's HTML interface. The add-in therefore appends a version
to the URL automatically; if the editor still shows an old state, restarting Fusion
helps.

### Uninstalling

Click **Stop** in *Scripts and Add-Ins* and delete the `PatternCreator` folder from
the `AddIns` directory. Sketches you already created stay intact — they are plain
Fusion geometry. Only editing them afterwards is no longer possible without the
add-in.

---

## Quick start in 5 minutes

Goal: a coaster with a honeycomb pattern — as an example of the complete workflow.

0. **Is the add-in running?** If not, do
   [step 3 of the installation](#step-3--start-the-add-in-in-fusion) first —
   otherwise the buttons are not there.
1. Create a **new design document**.
2. Click **SOLID → CREATE → Muster erstellen** (German interface:
   **Volumenkörper → Erstellen**), at the bottom of the **CREATE ▾** drop-down.
3. In the dialog pick the sketch plane (or leave it empty for the XY origin plane)
   and click **OK**. The **pattern editor** opens as a dockable palette on the right.
4. Choose **Wabe** (honeycomb) from the drop-down at the top. The preview shows the
   pattern immediately.
5. Open the **Rahmen** (container) group → shape **Kreis** (circle), diameter
   **90 mm**.
6. Group **Muster-Parameter** (pattern parameters) → preset **Mittel** (medium),
   cell size e.g. **10 mm**.
7. Group **Stil** (style) → mode **Flächen** (faces), fill **Stege** (webs),
   thickness **1.2 mm**, clipping **Am Rand beschneiden** (cut at border),
   **Rahmen zeichnen** (draw container) on.
8. Optional group **Text-Ebene** (text layer) → enable it and type your text. With
   **Muster ausstanzen** (knock out pattern) active the text stays free of cells.
   The position can be dragged with the mouse directly in the preview.
9. Optional group **Extrusion** → **Direkt extrudieren** (extrude directly) on,
   depth **3 mm**.
10. Click **In Skizze erzeugen** (create in sketch). Fusion creates the sketch, draws
    the pattern and extrudes it — as **one** timeline step.
11. Want to change something? Click **Muster bearbeiten**, pick the sketch, adjust
    the values and create it again. The extrusion recomputes automatically.

---

## Using the add-in

### The editor

```
┌──────────────────────────────────────┐
│ [pictogram] Wabe             ▾   [?] │  pattern type + quick help
│ Seed 42   🎲 Würfeln    Ebene: XY    │  seed + dice, target plane
├──────────────────────────────────────┤
│                                      │
│           live preview               │  zoom = mouse wheel, pan = drag
│           (canvas)                   │  text = draggable
│  382 contours · 382 faces · …        │  ⤢ = fit to view
├──────────────────────────────────────┤
│ ▾ Muster-Parameter  [fine|med|…]     │  pattern parameters + presets
│ ▸ Rahmen                             │  container
│ ▸ Stil                               │  style
│ ▸ Text-Ebene                         │  text layer
│ ▸ Extrusion                          │  extrusion
├──────────────────────────────────────┤
│ Zurücksetzen ↶ ↷   Abbrechen  [Erz.] │  reset · undo/redo · cancel · create
└──────────────────────────────────────┘
```

*(Screenshot placeholder — please replace after the first run.)*

### Step by step

1. **Choose a pattern** — drop-down at the top, grouped into *Technisch*
   (technical), *Organische Zellen* (organic cells) and *Natürlich* (natural), each
   with a pictogram. The **?** next to it shows a short description with all
   parameters.
2. **Set the parameters** — the forms are generated automatically from the selected
   pattern. Sliders and number fields are clamped to the allowed range; the preview
   refreshes 150 ms after the last change. **Fein / Mittel / Grob** (fine / medium /
   coarse) offer ready-made presets per pattern.
3. **Container** (*Rahmen*) — shape (rectangle, square, circle, ellipse, polygon),
   dimensions, origin, rotation of the container and — independently — rotation of
   the pattern inside it.
4. **Style** (*Stil*) — *Linien* (lines) for engravings, *Flächen* (faces) for
   extrudable profiles. In face mode **Dicke** (thickness) defines the web width;
   **Füllung** (fill) switches between *Stege* (the walls between the cells) and
   *Zellen* (the cell faces themselves). Patterns without a cell structure only
   offer *Stege* — the choice is then hidden. **Rahmendicke** (border width) sets
   the width of the closed rim; it is measured **inwards**, so the container size
   you enter stays the outer size of the part.
5. **Text layer** (*Text-Ebene*) — single- or multi-line text with font, height,
   position and angle. **Muster ausstanzen** (knock out) keeps the text area (plus an
   adjustable margin) free of pattern.
6. **Extrusion** — optionally extrude straight away: depth, direction and operation
   (new body / join / cut).
7. **Seed** — every random pattern depends on the seed alone. Same seed ⇒ identical
   result in the preview, in the sketch and after re-editing. **Würfeln** (dice)
   tries out variants.
8. **In Skizze erzeugen** (create in sketch) — creates the sketch, stores all values
   as an attribute on that sketch and extrudes on request. The button then changes to
   **Skizze aktualisieren** (update sketch); further changes rebuild the same sketch.
9. **Abbrechen** (cancel) closes the editor without leaving anything in the document.

### Editing an existing pattern

**SOLID → CREATE → Muster bearbeiten** (German: **Volumenkörper → Erstellen**) opens
a list of every pattern sketch in the document; alternatively click the sketch
directly in the model (only PatternCreator sketches are selectable). The editor
starts with exactly the stored values. Creating again rebuilds **the same** sketch —
an extrusion built on top of it recomputes instead of becoming orphaned.

If the sketch was edited by hand in the meantime, the add-in warns before
overwriting and lets you cancel.

### Keyboard shortcuts

| Shortcut | Effect |
| --- | --- |
| `Ctrl`/`Cmd` + `Z` | Undo inside the editor (up to 100 steps) |
| `Ctrl`/`Cmd` + `Shift` + `Z`, `Ctrl`/`Cmd` + `Y` | Redo |
| `Ctrl`/`Cmd` + `R` | Roll a new seed |
| `Ctrl`/`Cmd` + `Enter` | Create in sketch |
| Mouse wheel over the preview | Zoom |
| Drag in the preview | Pan — on the text: move the text |

### Units

The editor shows **millimetres**, the data model computes in **centimetres**
(the internal length unit of the Fusion API). Conversion happens exclusively at the
editor ↔ document boundary: an input of `10 mm` is stored as `1.0` in the PatternDoc.

### Typical applications

| Goal | Settings |
| --- | --- |
| Honeycomb panel for extrusion | honeycomb · faces · webs · thickness 1–2 mm · clipping *cut* |
| Grating / ventilation grille | grid or rhombus · faces · webs · container on |
| Engraving / laser engraving | any pattern · **lines** · container off |
| Puzzle for laser cutting | puzzle · lines (cut lines) or faces (individual pieces) |
| Naturally ragged border | clipping **drop partial** |
| Labelled pattern panel | text layer on · knockout on · faces |
| Decorative tile with leaf motif | motif scatter · Poisson distribution · angle jitter 30° |

---

## Concepts

| Term | Meaning |
| --- | --- |
| **Container** (*Rahmen*) | Rectangle (optionally with corner radius), square, circle, ellipse or polygon (3–12 sides) the pattern is fitted into. |
| **Line mode** (*Linien*) | Produces pure curves — for engravings and decorative sketches. |
| **Face mode** (*Flächen*) | Every curve becomes a closed strip via the **thickness**, every cell a closed polygon → directly extrudable. |
| **Webs / cells** (*Stege / Zellen*) | In face mode either the walls *between* the cells or the cell faces themselves. |
| **Clipping** (*Beschnitt*) | `cut at border` (cut), `drop partial` (ragged, natural edges) or `off`. |
| **Seed** | Same seed ⇒ identical pattern in the preview, in the sketch and after re-editing. |
| **Knockout** | The pattern is punched out within the text bounding box (plus margin). |
| **One single face** | For the tiling patterns (grid, rhombus, honeycomb, brick, puzzle, Voronoi, pebbles, tissue) face mode with *webs* produces **one** connected contour with holes instead of many separate strips — one click selects it, and the solid is watertight. Requires **Rahmen zeichnen** (draw container) on and clipping ≠ *off*. |

---

## One face instead of many strips

For **tiling** patterns — grid, rhombus, honeycomb, brick, puzzle, Voronoi, pebbles,
tissue — the web network is exactly *container minus shrunken cells*. The add-in
therefore produces a single outer contour with holes instead of many overlapping
strips:

* **Select it with one click** — in Fusion the whole pattern is one profile.
* **No overlaps** at the junctions, no duplicated edges.
* **3D-printable** — the extruded solid is watertight and free of self-intersections.
* **Fewer sketch entities** — the honeycomb example: 1849 → 679 entities.

This requires **Flächen** (faces) + **Stege** (webs), **Rahmen zeichnen** (draw
container) switched on — the container *is* the outer contour — and clipping ≠ *Aus*
(off). Without the container the webs stay individual strips and end openly at the
border, which is what you want for engravings.

The web width is the **Dicke** (thickness) you set. If a pattern brings its own joint
(brick: *Fugenbreite*; Voronoi/pebbles/tissue: *Fugenbreite*), the larger of the two
wins — that keeps brick dimensions exact. Clipped border cells that would leave only a
hairline sliver are closed up: such edges could not be printed.

**Stroke patterns** without cells (herringbone, waves, scales, phyllotaxis, spirals,
motif scatter, caustics, leaf veins) still consist of several strips. With **Direkt
extrudieren** (extrude directly) they are still merged into **one** body in a single
step; selecting them as one profile in the sketch is not implemented yet.

---

## Parameter reference

Shared by every pattern: **container** (shape + dimensions, origin, rotation of
container and pattern), **style** (mode, thickness, webs/cells, clipping, draw
container, **border width**), **text layer**, **extrusion** and **seed**.

**Border width** / „Rahmendicke“ (`style.borderWidth`, default 1.5 mm) applies in face
mode and is measured inwards: a 90 mm circular container stays 90 mm across. Each entry below gives the
English meaning, the German label shown in the editor and the internal key.

### Technical

#### Grid — „Gitter“ (`grid`)

Rectangular line grid with separate spacings in X and Y. The sheaf angle turns it
into an oblique grid.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Spacing X** / „Abstand X“ (`spacingX`) – default 8 mm – 0.2 mm to 500 mm – perpendicular distance of the vertical set of lines.
  - **Spacing Y** / „Abstand Y“ (`spacingY`) – default 8 mm – 0.2 mm to 500 mm – perpendicular distance of the horizontal set of lines.
  - **Sheaf angle** / „Scharenwinkel“ (`skew`) – default 90° – 15° to 165° – 90° = rectangular; other values give an oblique grid.

#### Rhombus — „Rauten“ (`rhombus`)

Rhombic grid from two sets of lines at ±α. Width and height of the rhombus define
the angle.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Rhombus width** / „Rautenbreite“ (`width`) – default 12 mm – 0.5 mm to 500 mm – horizontal diagonal of the rhombus.
  - **Rhombus height** / „Rautenhöhe“ (`height`) – default 20 mm – 0.5 mm to 500 mm – vertical diagonal of the rhombus.

#### Honeycomb — „Wabe“ (`honeycomb`)

Gapless hexagonal grid. In face mode you can extrude either the webs (walls) or the
cells.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Cell size** / „Zellweite“ (`cellSize`) – default 8 mm – 0.5 mm to 500 mm – across-flats size of the cell (distance between opposite faces).
  - **Orientation** / „Ausrichtung“ (`orientation`) – default flat – choice: flat top, pointy top.

#### Brick — „Mauer“ (`brick`)

Brick bond with adjustable joint width and row offset (running bond 1/2, third bond
1/3 or free).

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Brick width** / „Ziegelbreite“ (`brickWidth`) – default 20 mm – 1 mm to 500 mm.
  - **Brick height** / „Ziegelhöhe“ (`brickHeight`) – default 8 mm – 0.5 mm to 500 mm.
  - **Joint width** / „Fugenbreite“ (`jointWidth`) – default 1.2 mm – 0 mm to 50 mm – gap between bricks. 0 = no joint.
  - **Bond** / „Verband“ (`bond`) – default half – choice: running 1/2, third 1/3, free, no offset.
  - **Offset** / „Versatz“ (`offsetFraction`) – default 0.25 – 0 to 1 – fraction of the brick width each row is shifted by.

#### Puzzle — „Puzzle“ (`puzzle`)

Puzzle pieces in an X×Y grid. Every inner edge gets a classic tab: a round head on a
narrow neck with the typical undercut at its foot. The head is a **true circle** and
about 1.75 times as wide as the neck — only then do the pieces interlock. The
direction of each tab comes from the seed.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Pieces X** / „Teile X“ (`countX`) – default 5 – 1 to 60.
  - **Pieces Y** / „Teile Y“ (`countY`) – default 4 – 1 to 60.
  - **Tab size** / „Nasengröße“ (`tabSize`) – default 28 % – 2 % to 45 % – total tab height (neck + head) as a percentage of the edge length; values too small to leave a neck are raised to the head size.
  - **Neck width** / „Halsbreite“ (`neckWidth`) – default 18 % – 6 % to 40 % – width of the tab neck as a percentage of the edge length; the head follows from it.
  - **Shape jitter** / „Formstreuung“ (`shapeJitter`) – default 0.15 – 0 to 1 – random variation of tab size and position.

### Organic cells

#### Voronoi — „Voronoi“ (`voronoi`)

Random cell structure (Voronoi diagram). The building block for leaf cells, pebbles,
tissue and caustics.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Cell count** / „Zellenzahl“ (`cellCount`) – default 120 – 3 to 500 – at most 500 cells (performance guard).
  - **Uniformity** / „Gleichmäßigkeit“ (`relax`) – default 1 – 0 to 3 – Lloyd relaxation: 0 = wildly scattered, 3 = very even.
  - **Roundness** / „Rundheit“ (`roundness`) – default 0 – 0 to 3 – Chaikin corner smoothing: 0 = angular, 3 = pebble-round.
  - **Joint width** / „Fugenbreite“ (`inset`) – default 0 mm – 0 mm to 50 mm – cells are shrunk by this amount.

#### Pebbles — „Kiesel“ (`pebbles`)

Round stone cells: Voronoi with Chaikin rounding and a joint. Optionally each cell
gets an offset core point.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Cell count** / „Zellenzahl“ (`cellCount`) – default 110 – 3 to 500 – at most 500 cells (performance guard).
  - **Uniformity** / „Gleichmäßigkeit“ (`relax`) – default 1 – 0 to 3 – Lloyd relaxation.
  - **Roundness** / „Rundheit“ (`roundness`) – default 2 – 0 to 3 – Chaikin corner smoothing.
  - **Joint width** / „Fugenbreite“ (`inset`) – default 0.8 mm – 0 mm to 50 mm.
  - **Size spread** / „Größenstreuung“ (`sizeSpread`) – default 0 % – 0 % to 80 % – random shrinking of individual cells.
  - **Core point** / „Kernpunkt“ (`core`) – default False – draws a small, randomly offset circle into each cell.
  - **Core size** / „Kerngröße“ (`coreSize`) – default 25 % – 5 % to 70 %.

#### Tissue — „Zellgewebe“ (`tissue`)

Layered cells stretched in X and arranged in rows — the typical look of plant tissue
cross-sections.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Cell count** / „Zellenzahl“ (`cellCount`) – default 160 – 3 to 500.
  - **Uniformity** / „Gleichmäßigkeit“ (`relax`) – default 1 – 0 to 3.
  - **Roundness** / „Rundheit“ (`roundness`) – default 2 – 0 to 3.
  - **Joint width** / „Fugenbreite“ (`inset`) – default 0 mm – 0 mm to 50 mm.
  - **Rows** / „Reihen“ (`rows`) – default 8 – 1 to 80.
  - **Stretch X** / „Streckung X“ (`anisotropy`) – default 2.5 – 0.2 to 10 – > 1 elongates the cells in X.
  - **Restlessness** / „Unruhe“ (`rowJitter`) – default 0.7 – 0 to 1.5 – scatter of the cells within their row.

#### Water caustics — „Wasser-Kaustik“ (`caustics`)

Light net as on a pool floor: smoothed Voronoi edges with a wavy course and varying
thickness, optionally in two layers.

- Face mode: webs
- Presets: fine, medium, coarse
- Parameters:
  - **Mesh count** / „Maschenzahl“ (`cellCount`) – default 60 – 3 to 500.
  - **Uniformity** / „Gleichmäßigkeit“ (`relax`) – default 2 – 0 to 3.
  - **Restlessness** / „Unruhe“ (`jitterAmount`) – default 0.6 – 0 to 2 – wavy deflection of the edges across their direction.
  - **Thickness variation** / „Dickenvariation“ (`thicknessVariation`) – default 60 % – 0 % to 95 % – how strongly the stroke width varies along an edge.
  - **Second layer** / „Zweite Ebene“ (`secondLayer`) – default False – overlays a second, finer net with its own seed.
  - **Fineness of 2nd layer** / „Feinheit 2. Ebene“ (`secondScale`) – default 2 – 1.1 to 6.

#### Leaf veins — „Blattadern“ (`leaf_veins`)

Two-stage vein net: coarse cells form the thick main veins, a fine sub-Voronoi per
cell the thin secondary veins.

- Face mode: webs
- Presets: fine, medium, coarse
- Parameters:
  - **Coarse cells** / „Grobzellen“ (`coarseCells`) – default 14 – 2 to 120 – number of main-vein cells.
  - **Fine cells per coarse cell** / „Feinzellen je Grobzelle“ (`fineCells`) – default 9 – 0 to 40 – 0 = main veins only.
  - **Uniformity** / „Gleichmäßigkeit“ (`relax`) – default 2 – 0 to 3.
  - **Thickness ratio** / „Dickenverhältnis“ (`veinRatio`) – default 2.5 – 1 to 8 – how much thicker the main veins are than the secondary ones.
  - **Roundness** / „Rundheit“ (`roundness`) – default 1 – 0 to 3.

### Natural

#### Herringbone — „Fischgrät“ (`herringbone`)

Ribs run towards a centre axis from both sides at an angle. One axis yields a palm
frond, several a herringbone field.

- Face mode: webs
- Presets: fine, medium, coarse
- Parameters:
  - **Centre axes** / „Mittelachsen“ (`axisCount`) – default 1 – 1 to 40 – 1 = palm frond, more = herringbone field.
  - **Rib spacing** / „Rippenabstand“ (`ribSpacing`) – default 5 mm – 0.3 mm to 200 mm.
  - **Rib angle** / „Rippenwinkel“ (`ribAngle`) – default 40° – 5° to 85° – angle of the ribs against the axis.
  - **Rib length** / „Rippenlänge“ (`ribLength`) – default 18 mm – 0.5 mm to 500 mm.
  - **Curvature** / „Krümmung“ (`curvature`) – default 0.15 – 0 to 1 – 0 = straight ribs, > 0 = slightly curved.
  - **Draw axis** / „Achse zeichnen“ (`drawAxis`) – default True.

#### Waves — „Wellen“ (`waves`)

Parallel wave lines with adjustable wavelength, amplitude and phase shift per row.

- Face mode: webs
- Presets: fine, medium, coarse
- Parameters:
  - **Wavelength** / „Wellenlänge“ (`wavelength`) – default 25 mm – 1 mm to 1000 mm.
  - **Amplitude** / „Amplitude“ (`amplitude`) – default 5 mm – 0 mm to 500 mm.
  - **Line spacing** / „Linienabstand“ (`lineSpacing`) – default 7 mm – 0.3 mm to 200 mm.
  - **Phase shift per row** / „Phasenversatz je Zeile“ (`phaseShift`) – default 45° – −180° to 180°.
  - **Restlessness** / „Unruhe“ (`jitter`) – default 0 – 0 to 1 – random deviation of amplitude and phase per row.

#### Scales — „Schuppen“ (`scales`)

Fish scales: staggered rows of overlapping circular arcs. The overlap determines how
densely the rows sit.

- Face mode: webs
- Presets: fine, medium, coarse
- Parameters:
  - **Scale width** / „Schuppenbreite“ (`scaleWidth`) – default 20 mm – 0.5 mm to 500 mm.
  - **Overlap** / „Überlappung“ (`overlap`) – default 40 % – 0 % to 80 % – how far a row reaches into the one below.
  - **Row offset** / „Reihenversatz“ (`rowOffset`) – default 50 % – 0 % to 100 %.

#### Phyllotaxis — „Phyllotaxis“ (`phyllotaxis`)

Elements at the golden angle (137.508°) with r = c·√n — the spiral arrangement of
sunflower seeds.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Element count** / „Elementanzahl“ (`count`) – default 250 – 5 to 2000.
  - **Scale c** / „Skalierung c“ (`scale`) – default 2.5 mm – 0.1 mm to 100 mm – radius = c · √n; sets the density of the arrangement.
  - **Element size** / „Elementgröße“ (`elementSize`) – default 1.6 mm – 0.1 mm to 100 mm.
  - **Element shape** / „Elementform“ (`shape`) – default circle – choice: circle, hexagon, drop.
  - **Size gradient** / „Größenverlauf“ (`growth`) – default 0.5 – −1 to 2 – 0 = constant, > 0 = larger outwards, < 0 = smaller outwards.

#### Spirals — „Spiralen“ (`spirals`)

Logarithmic spirals r = a·e^(b·θ), scattered inside the container. Handedness
optionally mixed.

- Face mode: webs
- Presets: fine, medium, coarse
- Parameters:
  - **Spiral count** / „Spiralanzahl“ (`count`) – default 10 – 1 to 300.
  - **Turns** / „Windungen“ (`turns`) – default 2 – 0.25 to 8.
  - **Start radius** / „Startradius“ (`startRadius`) – default 3 mm – 0.1 mm to 200 mm.
  - **Growth b** / „Wachstum b“ (`growth`) – default 0.22 – 0.02 to 1 – the larger, the faster the spiral opens up.
  - **Size spread** / „Größenstreuung“ (`sizeSpread`) – default 0.4 – 0 to 1.
  - **Handedness** / „Drehrichtung“ (`handedness`) – default mixed – choice: left-handed, right-handed, mixed.

#### Motif scatter — „Motiv-Streuung“ (`motif_scatter`)

A parametric motif (leaf, drop, feather) is distributed in a grid, a staggered grid
or via Poisson scattering — with jitter on size and rotation.

- Face mode: webs, cells
- Presets: fine, medium, coarse
- Parameters:
  - **Motif** / „Motiv“ (`motif`) – default leaf – choice: leaf, drop, feather.
  - **Motif size** / „Motivgröße“ (`size`) – default 20 mm – 0.5 mm to 500 mm.
  - **Shape slim↔round** / „Form schlank↔rund“ (`shapeFactor`) – default 0.5 – 0 to 1.
  - **Side ribs** / „Seitenrippen“ (`ribs`) – default 4 – 0 to 20 – 0 = midrib only.
  - **Placement** / „Verteilung“ (`placement`) – default stagger – choice: grid, staggered grid, scatter.
  - **Spacing** / „Abstand“ (`spacing`) – default 24 mm – 0.5 mm to 500 mm.
  - **Base rotation** / „Grunddrehung“ (`baseAngle`) – default 0° – −180° to 180°.
  - **Angle jitter** / „Drehstreuung“ (`angleJitter`) – default 25° – 0° to 180°.
  - **Size jitter** / „Größenstreuung“ (`sizeJitter`) – default 0.2 – 0 to 1.

---

## Manual test matrix (Fusion)

Every pattern was checked with its default values **and** with an extreme case.
Please reproduce this on your own installation during the first run and record the
result.

| Pattern | Default | Extreme case | Expected |
| --- | --- | --- | --- |
| Grid | 8/8 mm, 90° | spacing X 0.2 mm, sheaf angle 15° | oblique grid, no doubled lines |
| Rhombus | 12 × 20 mm | 0.5 × 500 mm | very slim rhombi, cleanly clipped |
| Honeycomb | 8 mm, flat top | 0.5 mm, pointy top, cells | gapless, web **and** cell profiles selectable |
| Brick | 20 × 8 mm, joint 1.2 mm | joint 0 mm, third bond | no joint = closed face, border bricks clipped |
| Puzzle | 5 × 4 pieces | 60 × 60, tab 45 %, neck 40 % | round head on a narrow neck, pieces interlock; entity warning appears |
| Voronoi | 120 cells | 500 cells, inset 1.5 mm | < 10 s, cells as islands |
| Pebbles | 110 cells, roundness 2 | roundness 3, core point on | round cells, one circle per cell |
| Tissue | 8 rows, stretch 2.5 | 80 rows, stretch 10 | clearly elongated cells in rows |
| Water caustics | 60 meshes | 2nd layer on, thickness variation 95 % | two nets, visibly varying stroke width |
| Leaf veins | 14 / 9 cells | 120 / 40, ratio 8 | main veins clearly thicker than secondary ones |
| Herringbone | 1 axis | 40 axes, curvature 1.0 | palm frond resp. field, ribs as arcs |
| Waves | λ 25 mm, A 5 mm | λ 1 mm, restlessness 1.0 | smooth splines, no kinks |
| Scales | 20 mm, 40 % | 0.5 mm, 80 % overlap | rows staggered and overlapping |
| Phyllotaxis | 250 elements | 2000, size gradient 2.0 | golden-angle spiral, larger outwards |
| Spirals | 10 pieces | 300, 8 turns | logarithmic spirals, mixed handedness |
| Motif scatter | leaf, staggered | feather, Poisson, 20 ribs | motifs scattered, ribs visible |

Also worth checking:

- **Re-edit cycle:** create → extrude → *Muster bearbeiten* → change parameters →
  create ⇒ the extrusion recomputes.
- **Undo:** one commit is **one** timeline step (including an integrated extrusion).
- **Undo/redo inside the editor:** `Cmd/Ctrl+Z` resp. `+Shift+Z`.
- **Loading/unloading the add-in twice** ⇒ no duplicated buttons, no error message.
- **All container shapes** with clipping `cut`, `dropPartial`, `off` (spot check:
  circle + honeycomb).

---

## Troubleshooting

| Symptom | Cause and remedy |
| --- | --- |
| **PatternCreator does not show up in the add-in list** | Folder name ≠ `PatternCreator`, or wrong target folder. The folder must sit directly under `…/API/AddIns/` and be named exactly like `PatternCreator.py`/`.manifest`. Restart Fusion afterwards. |
| **No buttons at all** | The add-in is not running. Because of `runOnStartup: false` it has to be started once after every Fusion start via **UTILITIES → ADD-INS → Scripts and Add-Ins … → Add-Ins → Run**. For good: tick **Run on Startup**. |
| **The buttons are missing after clicking Run** | They are on the **SOLID** tab, **CREATE** panel, at the very bottom — open the **CREATE ▾** drop-down if needed. They do not appear in other workspaces (e.g. Render). |
| **The editor stays empty (no pattern in the drop-down)** | On the first open the palette had no connection to Fusion yet. Since version 1.0.1 the editor keeps asking until the data arrives. On older versions: close the editor and click **Muster erstellen** again. |
| **The editor shows an outdated interface** | Fusion cached an old HTML version. Stop the add-in, restart Fusion, run it again. |
| **The preview says „Ungültige Werte“ (invalid values)** | At least one field is out of range — it is marked red and states the allowed range. Fix the value or click **Zurücksetzen** in that group. |
| **Warning „ca. N Skizzen-Elemente“** | The pattern is very fine. Increase cell size/spacing, lower the cell count or switch to **line mode**. From roughly 2000 elements the commit asks before creating. |
| **Creating takes very long** | Same cause. Fusion needs time per sketch element; the element count is shown below the preview. |
| **The pattern cannot be selected in one go** | For the connected face you need **Flächen** (faces) + **Stege** (webs), **Rahmen zeichnen** (draw container) on and clipping ≠ *Aus* (off). Stroke patterns (waves, spirals, herringbone, scales, caustics, leaf veins, phyllotaxis, motif scatter) stay multi-part — use **Direkt extrudieren** there, which merges all profiles into one body. |
| **The extrusion finds no profiles** | **Line mode** produces open curves. Use **face mode** for extrudable profiles. |
| **The font looks different in Fusion than in the preview** | The preview renders with the browser font. Unknown fonts fall back to *Arial* in Fusion automatically (with a notice). |
| **„Skizze wurde von Hand verändert“ (sketch was edited manually)** | Expected behaviour: manual changes to that sketch are lost on rebuild. Cancel and move your changes into a separate sketch. |
| **The extrusion is gone after editing** | Should not happen — the re-commit rebuilds the same sketch. If it does: check the Fusion timeline for errors and report the case with the parameters you used. |

---

## Running the tests

The Fusion-free parts (`core/`, `generators/`, `text/`) run without Fusion:

```bash
python -m pytest tests/ -q
```

Covered are, among others: clipping of all container shapes, the stroker (closed
profiles, miter limit), edge deduplication and chaining, seed determinism of every
generator, PatternDoc round-trip and validation, text knockout, plus the structural
guarantee that `core/`, `generators/` and `text/` never import `adsk`.

---

## Architecture

```
PatternDoc (JSON)  ──►  generator  ──►  IR (Fusion-free)  ──┬──►  canvas preview (JS)
   ▲                                                        └──►  fusion/renderer.py
   └── attribute on the sketch (fusion/storage.py)
```

* **`core/pattern_doc.py`** — schema, defaults, validation with per-field plain-text
  messages, (de)serialisation.
* **`core/ir.py`** — intermediate representation (Path, Circle, Arc, Ellipse,
  TextItem).
* **`core/build.py`** — the pipeline: generator → pattern rotation → clipping →
  text knockout → style (stroker/inset) → container → placement.
* **`core/containers.py` / `core/clip.py`** — container shapes and half-plane
  clipping.
* **`core/stroker.py`** — lines → closed strips (miter with limit).
* **`generators/`** — one module per pattern; the organic family shares
  `organic_cells.py` (Voronoi, Lloyd, Chaikin, anisotropy, inset).
* **`fusion/`** — the only place with `adsk` calls.
* **`palette/`** — editor UI; the forms are generated **generically** from the
  generators' parameter schemas.

### Adding a new pattern

1. Create `generators/my_pattern.py`, inherit from `Generator`, declare `params` and
   implement `generate(params, ctx)` (returns IR elements).
2. Import it in `generators/__init__.py` and add it to `GENERATOR_CLASSES` and to
   `GROUPS`.

**No** change is needed in the editor or in the commands — form, pictogram, presets
and help text are derived from the class.

---

## Known limitations

* **At most 500 Voronoi cells** (hard limit in `organic_cells.py`) — pure Python,
  without that limit the preview becomes sluggish.
* **One text layer in the UI.** The data model already keeps `textLayers` as a list,
  so several layers can be added without a migration.
* **Knockout works on the bounding box** of the text, not on the exact letter
  outlines.
* **Preview font ≈ Fusion font.** The canvas renders with the browser font; tracking
  and margins can differ slightly.
* **Unknown font** ⇒ automatic fallback to *Arial* with a notice (font names differ
  between macOS and Windows).
* **Manual changes to a pattern sketch are lost when it is created again.** A warning
  with a cancel option appears beforehand.
* **From roughly 2000 sketch elements** the commit warns and can be cancelled.
* **Fusion caches the palette HTML.** While developing the UI, `palette_bridge.py`
  appends a version to the URL automatically; for a stubborn cache, restart Fusion.
* **Stroke patterns do not form a single face yet.** Herringbone, waves, scales,
  phyllotaxis, spirals, motif scatter, caustics and leaf veins have no cells, so their
  strips genuinely overlap. A single face would need a boolean union (see `PLAN.md`,
  section 13, stage 2). Extruding them still yields **one** body.
* The add-in creates sketch geometry, **not** a CustomFeature — the pattern does not
  appear as its own timeline entry (see PLAN.md, phase 6).

---

## License / origin

Implemented according to `PLAN.md`; the acceptance criteria are in `CHECKLIST.md`.
