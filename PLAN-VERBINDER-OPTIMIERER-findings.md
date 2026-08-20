# Findings zu PLAN-VERBINDER-OPTIMIERER.md

**Stand:** 2026-08-20, Meilensteine 1–7 umgesetzt (8 und 9.1 offen).
**Testlage:** 667 Tests grün (435 vor Beginn, 232 neu).

Dieses Dokument hält fest, wo die Code-Analyse im Plan von der gemessenen
Wirklichkeit abweicht, welche Plan-Schritte deshalb anders umgesetzt wurden und
was das für die verbleibenden Meilensteine bedeutet.

---

## 1. Messwerte (Referenz: Default-Parameter, Seed 42, Verbinder aus)

Elementzahl nach `entity_estimate`, unoptimiert → optimiert, mit Pässen 1–4.
Die Zahlen sind nach dem Stroker-Fix (Meilenstein 6, Abschnitt 15) neu gemessen;
in Klammern steht der Stand davor, wo er abweicht:

| Muster | vorher | nachher | |
| --- | ---: | ---: | ---: |
| phyllotaxis | 965 (1039) | 723 (772) | −25,1 % |
| leaf_veins | 2506 | 2071 | −17,4 % |
| motif_scatter | 1493 (1498) | 1238 (1243) | −17,1 % |
| tissue | 3735 | 3232 | −13,5 % |
| pebbles | 2756 | 2460 | −10,7 % |
| puzzle | 1363 | 1245 | −8,7 % |
| scales | 2598 | 2583 | −0,6 % |
| voronoi | 662 | 660 | −0,3 % |
| honeycomb | 684 | 683 | −0,1 % |
| grid, rhombus, brick, herringbone, waves, spirals | | | ±0 % |
| **Gesamt** | **18 972** (19 051) | **17 105** (17 158) | **−9,8 %** |

Über alle 15 Muster × 7 Stil-Varianten (`{}`, `lines`, `cells`, `border=False`,
`hatch`, `dropPartial`, `clip=off`): 172 065 → 158 617 Elemente, **−7,8 %**
(vor dem Stroker-Fix: 175 374 → 160 985, −8,2 %).
Konturzahl in **allen** Fällen unverändert – es geht kein Element verloren.

Der Stroker-Fix senkt die **Ausgangs**zahl (die entfernten Schleifen waren
zusätzliche Punkte), nicht die Wirkung des Optimierers. Deshalb sinkt der
Prozentsatz leicht, obwohl absolut weniger Elemente herauskommen.

---

## 2. Pass 1 bringt praktisch nichts

**Plan (B.3):** „Größter Gewinn bei Stroker-Ringen und Schraffur-Rechtecken;
O(n), risikofrei."

**Gemessen:** über alle Muster × Stil-Varianten 156 323 → 156 302 Elemente
(−0,01 %). Es greift nur an zwei Stellen: `honeycomb` im Linienmodus
(744 → 729) und `pebbles` ohne Rahmen (5960 → 5957).

**Grund:** Die Pipeline ist bereits sauber, bevor der Optimierer sie sieht.

- `stroker._clean` (`core/stroker.py:26-33`) läuft schon in `stroke_open` und
  `stroke_closed` über jeden Ring.
- `clean_polygon` (`core/geom.py:384-405`) entfernt Dubletten und kollineare
  Punkte in jedem `_shrink_cell`- und `erode_convex`-Durchlauf.
- `offset_polyline` erzeugt genau einen Punkt je Stützpunkt – an einer geraden
  Kette gäbe es kollineare Reste, aber `chain_segments` verkettet nur über
  Knoten vom Grad 2, und die Kreuzungen in Gitter-, Waben- und Voronoi-Mustern
  haben Grad 3 oder 4. Es entstehen also gar keine langen geraden Ketten.
- Schraffur-Streifen sind bereits 4-Punkt-Rechtecke (`core/hatch.py:174-217`).

**Doppelte Elemente:** In keiner der 105 Kombinationen wurde ein einziges
Duplikat gefunden. `dedupe_segments` (`core/geom.py:192-205`) ist weiterhin
nirgends aufgerufen – das ist aber kein Versäumnis, sondern folgerichtig:
`snap_segments` erledigt die Deduplizierung an der einzigen Stelle, an der
doppelte Kanten entstehen können.

**Konsequenz:** Pass 1 bleibt drin (er ist korrekt, kostet fast nichts und
sichert die aggressiveren Pässe ab), taugt aber nicht als „sofort messbarer
Gewinn". Der eigentliche Ertrag von Meilenstein 1 ist der Fidelity-Harness.

---

## 3. Pass 2 (Kreis-Refit) greift nie

**Plan (B.3):** „…wohl aber ungeklippte tessellierte Kreise, falls solche in der
Pipeline entstehen."

**Gemessen:** In keiner der 105 Kombinationen existiert ein geschlossener
Linienzug, der die Kreisbedingung erfüllt. Es entstehen schlicht keine
tessellierten Vollkreise:

- Phyllotaxis-Kreise bleiben von der Erzeugung bis zur Szene `ir.Circle`
  (418 von 441 Konturen im Default-Fall).
- `_to_areas` erzeugt aus `ir.Circle` wieder `ir.Circle` (Außen-/Innenring,
  `core/build.py:340-344`).
- `_circle_to_points` (48-Eck) wird nur für `fully_inside`-Prüfungen und für
  den Clip-Fall benutzt – und dessen Ergebnis ist danach kein Vollkreis mehr.

Der Pass ist trotzdem umgesetzt und synthetisch getestet: er ist die
Absicherung für künftige Generatoren und für Feature A (Verbinder-Stege an
runden Motiven).

---

## 4. Pass 3 (Bogen-Refit) greift nie – und der Clip-Umbau ist nicht machbar

**Plan (B.3):** „Wichtig für geklippte Kreise: `_clip_elements` so ändern, dass
ein geklippter Kreis nicht als 48-Eck-Polygon, sondern als **Bogen +
Schließkante** weitergereicht wird. […] Minimalziel: geklippter Kreis kostet
danach ≤ ~5 Elemente statt 48."

Der Umbau ist **bewusst nicht** umgesetzt. Drei Gründe:

1. **Das 48-Eck erreicht die Szene gar nicht.** Ein angeschnittener
   Phyllotaxis-Kreis wird in `_clip_elements` zum Polygonstück, läuft dann als
   `ROLE_REGION` in `region_segments` (`core/build.py:333`), wird von
   `snap_segments`/`chain_segments` verkettet und schließlich gestrokt. In der
   Szene stehen davon Ringe mit **25–35** Punkten, nie 48. Die
   Ausgangsbehauptung des Akzeptanzkriteriums trifft nicht zu.
2. **Bogen + Schließkante als getrennte Elemente würde das Flächenmodell
   brechen.** `_to_areas` sammelt Zellkanten als Segmente ein und verkettet sie;
   ein `ir.Arc` mitten in dieser Kette hätte keinen Platz, und `_to_areas`
   tesselliert einen Arc ohnehin sofort wieder (`core/build.py:350-353`).
3. **Der gestrokte Ring ist ein Mischling.** Der Offset eines Kreisbogens ist
   zwar wieder ein Kreisbogen, aber der Ring besteht aus Bogen + Sehne + Bogen +
   Sehne. Das exakt abzubilden hieße gemischte Linie/Bogen-Pfade in der IR – und
   genau die schließt der Plan unter „Nicht-Ziele" aus.

Ein Bogen-Refit **könnte** hier nur mit einem bogenfähigen Stroker greifen. Das
ist ein eigener, deutlich größerer Umbau; ich habe ihn nicht angefangen.

Offene Linienzüge gibt es im Übrigen fast nirgends: im Flächenmodus ist alles
geschlossen, im Linienmodus sind die offenen Pfade entweder Splines (zählen
schon als 1 Element) oder 2-Punkt-Rippen. `scales` erzeugt bereits echte
`ir.Arc`-Elemente. Auch Pass 3 ist also umgesetzt und synthetisch getestet, aber
ohne Wirkung auf den heutigen Bestand.

---

## 5. Das Toleranzbudget muss anders aufgeteilt werden

Erster Ansatz war „Punktabstand ≤ TOL/2 **und** Bogenhöhe ≤ TOL/2". Das ist zu
streng: ein exaktes 48-Eck mit r = 0,9 cm hat eine Bogenhöhe von
0,9 · (1 − cos(π/48)) = **0,00193 cm** – knapp unter TOL, aber deutlich über
TOL/2. Der kanonische Fall aus dem Plan wäre damit abgelehnt worden.

Umgesetzt ist jetzt die additive Schranke **radialer Fehler + Bogenhöhe ≤ TOL**.
Das ist auch die geometrisch richtige Rechnung: beide Fehler treffen in der
Sehnenmitte zusammen und addieren sich dort.

---

## 6. Der Fidelity-Harness braucht Sehnenmitten

Der Plan (B.5.1) verlangt „Punkt-zu-Segment-Abstand, beidseitig gesampelt".
Wichtiger Zusatz: es genügt **nicht**, nur die Stützpunkte zu messen. Ein
Kreis- oder Bogen-Refit läuft exakt durch alle Stützpunkte und beult trotzdem
zwischen ihnen aus. Der Harness sampelt deshalb Stützpunkte **und**
Sehnenmitten – erst dadurch misst er die Bogenhöhe überhaupt.

Zweiter Zusatz: der Harness muss `ir.Circle` und `ir.Arc` als Ergebnis
akzeptieren, nicht nur Pfade, sonst prüft er die Refit-Pässe gar nicht.

---

## 7. Der Selbstschnitt-Wächter muss relativ prüfen

Der Plan sagt „bei neuem Selbstschnitt den Pfad unvereinfacht lassen". Das
„neu" ist wesentlich – und zwar deutlich wesentlicher als erwartet: über die
105 gemessenen Kombinationen sind **508 Rohkonturen schon vor jeder
Optimierung selbstschneidend**. Ein absoluter Test würde dort jede
Vereinfachung blockieren. Umgesetzt ist deshalb: vereinfachen, wenn das
Ergebnis sich nicht schneidet **oder** das Original sich schon geschnitten hat.

### Nebenbefund: der Stroker erzeugte kaputte Profile (Bestandsfehler) — **erledigt**

> **Erledigt mit Meilenstein 6** (2026-08-20, Abschnitt 15): `remove_loops`
> läuft jetzt über jeden Stroker-Ring, alle unten genannten Fälle sind auf
> **0** selbstschneidende Konturen zurückgegangen. Der Rest dieses Abschnitts
> beschreibt den Befund, wie er beim Bau des Wächters aussah.

Das ist kein Optimierer-Thema, fiel aber beim Bau des Wächters auf und gehört
festgehalten. Betroffen ist immer der **Strok-Pfad** (`_to_areas` → `stroke`),
nie das Flächenmodell (`_to_face`):

| Fall | selbstschneidende Konturen | nach Meilenstein 6 |
| --- | ---: | ---: |
| `phyllotaxis`, Default | 10 von 441 | 0 |
| `motif_scatter`, Default | 4 von 144 | 0 |
| `tissue`, `border=False` bzw. `clip=off` | je 94 | 0 |
| `leaf_veins`, `border=False` bzw. `clip=off` | je 78 | 0 |
| `puzzle` / `pebbles`, `border=False` bzw. `clip=off` | je 31 / 30 | 0 |

Stichprobe Phyllotaxis: ein 31-Punkt-Ring aus einem am Rahmen angeschnittenen
Kreis, Segment 3 kreuzt Segment 8 bei (0,142 / 2,96) – also direkt an der
Beschnittkante (Rahmenhälfte = 3,0). Der Gehrungs-Offset legt dort eine
Schleife an, `stroke_open`/`stroke_closed` hatten aber – anders als
`_shrink_cell` (`core/build.py:439`) – **kein** `remove_loops`.

Ein sich selbst schneidendes Profil ist in Fusion unbrauchbar; diese Konturen
extrudierten nicht sauber. Genau diese Ringe sind zugleich die „isolierten
Inseln", die die Verbinder anbinden – der Fix gehörte deshalb vor die
Fusion-Abnahme von Feature A.

Der zugehörige Testfall musste konstruiert werden – die naheliegenden
„dünner Zwickel"-Beispiele sind bereits vorher selbstschneidend und beweisen
nichts. Der Fall in `tests/test_optimize.py` (`SELF_INTERSECTION_TRAP`) hat
deshalb eine Gegenprobe: erst wird gezeigt, dass das Original sauber ist und die
rohe RDP-Vereinfachung tatsächlich einen Schnitt erzeugt, dann dass der Wächter
greift.

---

## 8. Der Flächen-Invariantentest braucht eine geometrische Schranke

„Fläche bleibt gleich" lässt sich nach RDP nicht mit einem festen Epsilon
prüfen. Die richtige Schranke ist **|ΔA| ≤ Umfang · TOL** – so weit kann sich
der Inhalt ändern, wenn sich der Rand um höchstens TOL verschiebt.

Nebenbefund zu den Druck-Garantien: RDP verschiebt Ränder um ≤ TOL, zwei
benachbarte Löcher können sich also um ≤ 2·TOL = 0,04 mm nähern. Gemessen
bleiben alle Stege weit darüber. Die Rahmendicken-Garantie aus `_limit_hole`
bleibt unberührt, weil RDP eine gerade Beschnittkante nicht bewegt.

---

## 9. Pass 5 kann die Toleranz 0,02 mm grundsätzlich nicht halten

Das ist der wichtigste Befund von Meilenstein 3.

**Plan (B.3):** „Pfade, die nach Pass 4 immer noch ≥ 12 Punkte haben **und**
glatt sind […] ⇒ `curve="spline"` setzen. Trifft v. a. Puzzle-Zellringe
(~65 Punkte → 1)."

**Gemessen:** Bei der vom Nutzer festgelegten Toleranz von 0,02 mm wandelt
Pass 5 in **keiner** der 105 Kombinationen eine einzige Kontur um.

### Warum das keine Einstellungsfrage ist

Ein interpolierender Spline durch die Stützpunkte einer Polylinie weicht von
dieser Polylinie um ungefähr die **Bogenhöhe ihrer eigenen Sehnen** ab – der
Spline schneidet die Ecken, die die Polylinie stehen lässt. Gegenprobe mit
einem exakt gleichmäßig abgetasteten Einheitskreis: 40 Punkte ergeben einen
Spline-Fehler von 0,00307 cm, und das ist *genau* die Sehnen-Bogenhöhe
1 · (1 − cos(π/40)) = 0,00308 cm.

Daraus folgt die Schranke: damit die Bogenhöhe unter TOL bleibt, braucht eine
Kontur vom Radius r mindestens 2π / (2·arccos(1 − TOL/r)) Stützpunkte – bei
r = 0,5 cm also 35 Punkte, bei r = 1 cm 50 Punkte. Genau in dem Bereich, in dem
die Umwandlung nennenswert Elemente spart, verletzt sie die Toleranz.

**Die Spline-Umwandlung ist damit keine toleranztreue Optimierung, sondern eine
bewusste Glättung.** Sie mit dem Fidelity-Kriterium aus B.5.1 („maximale
Abweichung optimierte ↔ unoptimierte Kontur < TOL") zu kombinieren, ist ein
Widerspruch im Plan.

### Was es kosten würde, Pass 5 wirken zu lassen

Gemessen über alle 15 Muster (Default, Seed 42, Verbinder aus), Pass 5 mit
eigener Toleranz; Δ bezogen auf die unoptimierten 18 972 Elemente. Die Tabelle
ist nach dem Stroker-Fix neu gemessen:

| Spline-Toleranz | Knick-Gate | Elemente | Δ | umgewandelt |
| --- | --- | ---: | ---: | ---: |
| 0,02 mm (Plan) | 30° | 17 105 | −9,8 % | 0 |
| 0,05 mm | 30° | 16 824 | −11,3 % | 11 |
| 0,1 mm | 30° | 16 657 | −12,2 % | 17 |
| 0,2 mm | 30° | 16 361 | −13,8 % | 28 |
| 0,5 mm | 30° | 15 403 | −18,8 % | 67 |
| 0,1 mm | 60° | 15 838 | −16,5 % | 53 |
| 0,5 mm | 60° | 13 133 | −30,8 % | 171 |

Selbst bei 0,5 mm und 60° – beides weit jenseits des Vertretbaren – bleibt es
bei −31 %. Die Plan-Zielmarke „Puzzle ≥ 80 %" ist **bei keiner Einstellung**
erreichbar, und zwar aus einem zweiten, unabhängigen Grund (siehe unten).

Umgesetzt ist Pass 5 mit der vom Nutzer entschiedenen Toleranz. Das ist eine
Entscheidung, die nur der Nutzer ändern kann; der Code hat dafür genau zwei
Stellschrauben (`MIN_SPLINE_POINTS`, `MAX_SPLINE_KINK`) plus das Budget.

### Der Puzzle-Fall beruht auf einer Fehlannahme

Der Plan nennt Puzzle-Zellringe als Hauptkandidat („glatte, dichte Konturen").
Gemessen haben die 20 Kandidatenringe Knickwinkel von **106° bis 127°** – das
sind die Puzzle-Nasen. Der Plan schließt Ecken selbst aus („Pfade mit Ecken
**nicht** umwandeln – Fitted Splines überschwingen an Knicken"). Beides zusammen
geht nicht: die Puzzle-Ringe *sind* die Ecken. Dasselbe gilt für `scales`,
`waves` und `spirals` – deren Ringe haben 90°-Knicke, weil ein gestrichener
offener Streifen **flache Endkappen** bekommt (`stroke_open`).

### Reihenfolge: Pass 5 muss vor Pass 4 laufen

Nicht im Plan, aber zwingend. Läuft die Vereinfachung zuerst, nimmt sie dem
Spline die Stützpunkte weg (längere Sehnen ⇒ größere Ausbeulung) **und**
verbraucht das Toleranzbudget – ein Kontur, die vorher ein Spline (1 Element)
geworden wäre, wird danach ein 75-Punkt-Linienzug. Umgesetzt ist deshalb:
Pass 5 zuerst mit vollem Budget, Pass 4 nur als Rückfallebene. Es greift immer
nur einer von beiden, sonst summierten sich ihre Abweichungen auf 2 × TOL.

### Vorschau-Parität: der Plan-Hinweis ist überholt, ein anderer Fehler war echt

**Plan:** „`palette/preview.js:137-143` zeichnet Splines als Quadratik-Näherung
– Sichtprüfung Puzzle/Kiesel […] falls nötig auf Catmull-Rom umstellen."

Trifft nicht zu: `Preview.prototype._trace` zeichnet bereits kubische Béziers
mit Catmull-Rom-Tangenten (`(p2−p0)/6`) – also exakt Catmull-Rom. Nichts zu tun.

Dafür gab es einen echten Fehler daneben: `Preview.prototype._sub`, der Pfad
für die **gefüllte** Fläche (`ROLE_FACE`/`ROLE_HOLE`, evenodd-Füllung), ignorierte
`curve` und zog immer gerade Linien. Eine Spline-Kontur wäre dort als gestrichene
Kurve über einer eckigen Füllung erschienen. Heute tritt der Fall nicht auf (kein
Generator liefert Spline-Löcher), er wäre aber mit dem ersten wirksamen Pass 5
sofort sichtbar geworden. Behoben: `_trace` und `_sub` teilen sich jetzt
`_emit`.

### Architektureller Schluss

Ob eine Punktfolge die Abtastung einer glatten Kurve ist, weiß der **Generator**
– und er sagt es bereits: `motif_scatter`, `scales`, `waves`, `spirals` und
`herringbone` liefern ihre Konturen von sich aus mit `curve="spline"`. Der
Optimierer kann das nicht rekonstruieren, er sieht nur Punkte. Die
Spline-Entscheidung gehört deshalb dorthin, wo sie schon getroffen wird, und
nicht in einen nachgelagerten Pass.

---

## 10. Feature A: Inseln statt Gruppen-IDs

Die Verbinder funktionieren – alle Streu-Muster ergeben in jeder geprüften
Stil-Variante **einen** Körper. Der Weg dorthin weicht aber an einer zentralen
Stelle vom Plan ab.

### Gruppen-IDs sind überflüssig

**Plan (A.3, Schritt 1):** `ir.Path`/`ir.Circle` bekommen ein Feld `group`, die
Generatoren vergeben pro Motiv eine ID, und `_to_areas`/`_clip_elements` reichen
sie durch.

**Umgesetzt:** kein IR-Feld, keine Generator-IDs. Die Gruppen werden aus der
**fertigen Geometrie** abgeleitet (`core/connect.islands`): was sich schneidet
oder ineinander liegt, ist eine Insel. Vier Gründe:

1. Der Plan verlangt in seinen eigenen Sonderfällen ohnehin, die Gruppen
   **nach** dem Clipping zu bilden („ein Motiv kann in mehrere Teilstücke
   zerfallen ⇒ jedes Teilstück als eigene Gruppe"). Generator-IDs müssten also
   nachträglich wieder aufgebrochen werden.
2. Motive, die sich schon berühren, wären getrennte Gruppen und bekämen Stege,
   die sie nicht brauchen. Gemessen: Motiv-Streuung hat 144 Profile, aber nur
   **15 Inseln** – Gruppen-IDs hätten 143 Stege gezogen statt der nötigen 14.
3. Kein Durchreichen durch `_map_points`, `_clip_elements`, `_to_areas` und die
   Serialisierung – vier Stellen weniger, an denen das Feld verlorengehen kann.
4. Ein künftiger Streu-Generator funktioniert ohne jedes Tagging.

Das Klassen-Flag `Generator.scatter` bleibt – aber nur noch für die **UI**:
es entscheidet, ob die Palette die beiden Verbinder-Felder anzeigt. Für den
Algorithmus wird es nicht gebraucht.

### Schritt 2 (Rippen verschweißen) ist nicht nötig

**Plan:** „Die Rippen enden heute frei im Blattinneren bzw. an der Kontur, ohne
garantiert zu überlappen." – Sie überlappen bereits: die Mittelrippe läuft von
(0,0) nach (0,s), und beide Punkte sind **exakt Konturpunkte** des Blattes
(`_leaf_outline` beginnt und endet auf der Mittelachse). Die Seitenrippen
starten auf der Mittelachse. Gemessen enthält ein Blatt genau eine Insel.

### Ein Akzeptanzkriterium ist arithmetisch unmöglich

**Plan:** „Phyllotaxis, Seed 42: Verbinder an ⇒ eine Zusammenhangskomponente;
Elementzahl trotz zusätzlicher Stege **unter** dem heutigen Wert (1039)."

Phyllotaxis zerfällt in **220 Inseln**. Ein Spannbaum braucht dafür 219 Stege,
jeder Steg ist ein 4-Punkt-Rechteck = 4 Entities ⇒ **mindestens +876**. Die
Motive selbst kosten nach Optimierung 723. Weniger als 1599 ist nicht möglich;
tatsächlich sind es 1625. Der Optimierer spart 242 Entities, die Stege kosten
876 – er kann sie nicht kompensieren.

Zahlen nach dem Stroker-Fix, in Klammern der Stand davor. Die Inselzahl bleibt
unverändert – die entfernten Schleifen waren Punkte, keine Konturen:

| | heute | optimiert, ohne Stege | mit Verbindern |
| --- | ---: | ---: | ---: |
| phyllotaxis | 965 (1039), 220 Inseln | 723 (772) | **1625 (1673), 1 Körper** |
| motif_scatter | 1493 (1498), 15 Inseln | 1238 (1243) | **1302 (1307), 1 Körper** |

Beide bleiben unter der 2000er-Warnschwelle. Motiv-Streuung erfüllt sein
Kriterium sogar vollständig: ein Körper **und** weniger Elemente als heute.

### Der Beschnitt kann einen Steg durchtrennen

Nicht im Plan. Ein Steg an einem angeschnittenen Randmotiv verliert beim
Clipping genau das Stück, mit dem er in sein Motiv hineinläuft – die Insel hängt
danach wieder frei. Gemessen bei Phyllotaxis mit `count=400, scale=0.35`:
4 von 192 Stegen beschnitten, eine Insel wieder lose.

Umgesetzt ist deshalb ein **Nachbesser-Durchlauf**: nach dem Beschnitt werden
die Inseln erneut gezählt und fehlende Verbindungen ergänzt (höchstens vier
Runden). Bleibt danach etwas übrig, sagt das eine Warnung, statt still lose
Teile zu erzeugen. In der Regel ist nach der ersten Runde Schluss.

### Zusammenhang: „schneidet oder liegt darin", nicht Even-odd

Der naheliegende Ansatz – Schachtelungstiefe, Even-odd wie bei Fusions
Profilbildung – geht schief, sobald sich zwei Stege überlappen: ein winziges
Motiv in der Überlappung hat Tiefe 2, gilt als eigene Außenkontur und wird für
isoliert gehalten. (Phyllotaxis erzeugt im Zellen-Modus tatsächlich Scheiben von
0,005 cm Radius – 0,05 mm, selbst nicht mehr druckbar.)

Umgesetzt ist die einfachere Regel: **Konturen, die sich schneiden oder
ineinander liegen, gehören zusammen.** Innerhalb des Musterlayers ist sie sicher
(die Blattrippen liegen in der Blattkontur und hängen ohnehin an ihr). Für den
**Rahmen** gilt sie nicht – das Band umschließt alles, ohne es zu berühren.
Deshalb lässt `outlines()` `LAYER_BORDER` aus und der Rahmen wird getrennt
verankert.

### Beschnittene Motive liegen exakt auf der Rahmenkante

Ein Eckpunkt taugt nicht als Prüfpunkt für „liegt darin": beschnittene Motive
haben ihre Kante exakt auf der Containerkante, und `point_in_polygon` ist auf
der Grenze nicht entscheidbar. Das kostete zunächst 8 falsch als isoliert
gemeldete Motive. `_inner_point` nimmt stattdessen die Mitte der längsten Kante
und versetzt sie ein Haar nach innen.

### Kosten

Der Zusammenhangstest ist der teuerste Teil: zwei 32-Eck-Ringe wären 1024 volle
Strecken-Schnitttests. Mit Raster-Vorauswahl der Kandidatenpaare und
Hüllrechteck-Filter je Kantenpaar kostet ein Phyllotaxis-Aufbau **0,135 s**
statt 0,01 s. Die Vorschau baut bei jeder Reglerbewegung neu auf – das ist
spürbar, aber vertretbar; ohne die beiden Filter waren es 0,4 s.

---

## 11. Nicht reproduzierbare Akzeptanzkriterien

- **„Motiv-Streuung, Seed 42 (heute ~2146 Elemente ⇒ Warnung)"**: Mit
  Default-Parametern messe ich **1493** Elemente – unter dem 2000er-Limit, also
  ohne Warnung. Das Kriterium bezieht sich offenbar auf einen anderen
  Container/Parametersatz. Nach Pässen 1–4: 1238.
- **„Phyllotaxis, Seed 42 (heute 441 Konturen / ~1039 Elemente)"**: stimmte
  exakt – bis der Stroker-Fix die Schleifenpunkte entfernte, seither sind es
  **965** Elemente bei denselben 441 Konturen. Nach Pässen 1–4: 723.
- **„geklippter Phyllotaxis-Kreis ≤ 5 Elemente statt 48"**: nicht erreichbar,
  siehe Abschnitt 4.
- **„Puzzle ≥ 80 %, Motiv-Streuung ≥ 50 %"**: mit Pässen 1–4 nicht erreicht
  (−8,7 % bzw. −17,1 %). Diese Ziele hängen vollständig an **Pass 5**
  (Spline-Umwandlung), siehe unten.

---

## 12. Kosten

| | vorher | nachher |
| --- | ---: | ---: |
| `optimize()`, schwerstes Muster (`tissue`) | – | +0,04 s je Aufbau |
| Verbinder, `phyllotaxis` | 0,01 s | 0,135 s je Aufbau |
| `remove_loops` im Stroker, `tissue` | – | +0,02 s je Aufbau |

Der Stroker-Fix ist damit praktisch gratis: die Ringe haben 25–70 Punkte, und
die Schraffur-Streifen und Verbinder-Stege sind 4-Punkt-Rechtecke, an denen der
Aufruf ein No-op ist. Die Phyllotaxis wird sogar messbar **schneller**, weil
danach 74 Punkte weniger durch `optimize()` laufen.

`optimize()` verteilt sich (cProfile, kumulativ) auf RDP ~31 %,
Selbstschnitt-Wächter ~14 %, Pass 1 ~12 %, Kreis-Fit ~10 %. Bei den Verbindern
dominiert der Zusammenhangstest.

Beides ist vertretbar: in Fusion spart jede eingesparte Linie einen
API-Roundtrip, und die dominieren die Commit-Zeit um Größenordnungen. Die
Vorschau baut allerdings bei **jeder** Reglerbewegung neu auf – 0,135 s für die
Phyllotaxis ist spürbar. Erste Hebel, falls das stört: den Selbstschnitt-Wächter
bei konvexen Ringen überspringen (dort kann RDP keinen erzeugen) und den
Inselbestand über mehrere Aufbauten zwischenspeichern, solange sich weder Seed
noch Musterparameter ändern.

---

## 13. Meilenstein 5: Doku und Version

- README: neuer Abschnitt **Verbinder** (deutsch und englisch), Grundbegriffe
  ergänzt, Navigationsleisten verlinkt.
- Der Einschränkungs-Absatz zu den Strich-Mustern ist angepasst: Streu-Muster
  sind jetzt einteilig druckbar.
- Zwei **neue** dokumentierte Grenzen: Text-Knockout kann einen Verbinder
  durchtrennen, und der Optimierer arbeitet mit fester Toleranz und wandelt
  deshalb kaum etwas in Splines um.
- `CHECKLIST.md`: neue Abschnitte **G4 Verbinder** und **G5 Optimierer** – die
  Punkte, die sich nur in Fusion und am gedruckten Teil prüfen lassen.
- Manifest-Version 1.3.0 → **1.4.0**, Versionsangaben im README nachgezogen.
- Drei neue Architektur-Tests halten das fest: README-Abschnitte vorhanden,
  bekannte Grenze dokumentiert, jeder Stil-Parameter erreicht das Editor-Schema.

---

## 14. Was offen bleibt

**Entscheidung beim Nutzer (Abschnitt 9): erledigt.** Der Nutzer hat sich am
2026-08-20 für **Option A** entschieden: Pass 5 bleibt bei 0,02 mm und damit
schlafende Absicherung, die Spline-Entscheidung bleibt beim Generator. Die
Prüfung, ob `organic_cells` seine gerundeten Konturen generatorseitig als
Spline liefern kann, ist gelaufen und **negativ** ausgefallen – Abschnitt 16.

**Bestandsfehler (Abschnitt 7): erledigt.** `remove_loops` läuft seit
Meilenstein 6 über jeden Stroker-Ring; in keiner der geprüften Kombinationen
bleibt eine selbstschneidende Kontur übrig – Abschnitt 15.

**Nicht angefangen, bewusst:** der bogenfähige Stroker (Abschnitt 4), ohne den
das Bogen-Refit an geklippten Kreisen nicht greifen kann.

**Noch offen:** die Vorschau-Performance der Verbinder (Meilenstein 8, nur bei
Bedarf) und alles, was Fusion selbst braucht – Extrusion der Verbinder-Szenen
zu **einem** Volumenkörper, Re-Edit-Geschwindigkeit nach der Renderer-Änderung,
Sichtprüfung der optimierten Konturen. Das steht in `CHECKLIST.md` G4/G5 und
lässt sich hier nicht automatisieren.

---

## 15. Meilenstein 6: der Stroker-Fix

`stroke_open` und `stroke_closed` schicken ihre fertigen Ringe jetzt durch
`remove_loops` (`core/geom.py:422`) – in `stroke_open` den einen Ring, in
`stroke_closed` Außen- und Innenring, jeweils **vor** den bestehenden Gates
(≥ 3 Punkte, |Fläche| > 1e-10). Das `_clean` läuft davor und danach: der neue
Schnittpunkt kann auf einem Nachbarpunkt zu liegen kommen.

**Wirkung.** Über alle 15 Muster × 8 Stil-Varianten bleibt **keine einzige**
selbstschneidende geschlossene Kontur übrig (vorher 508 Rohkonturen, siehe
Tabelle in Abschnitt 7). Der Fix greift an beiden Enden: über alle geprüften
Kombinationen legte der ungesicherte Offset 390-mal in einem offenen und
118-mal in einem geschlossenen Strok-Vorgang eine Schleife an.

**Konturzahl-Invariante gehalten.** Über dieselben 105 Kombinationen liefert
der Stroker mit und ohne `remove_loops` exakt gleich viele Konturen – kein Ring
kollabiert, es gibt keinen stillen Verlust. Die Gates fangen nur ab, was
ohnehin schon leer wäre.

**Wechselwirkung mit dem Wächter (wie im Nachtrag erwartet).** Der relative
Selbstschnitt-Wächter (`core/optimize.py:401`) darf jetzt seltener durchwinken,
weil weniger Originalkonturen schon vorher krumm sind. Zusammen mit den
entfallenen Schleifenpunkten verschieben sich die Elementzahlen leicht –
nachgezogen in den Abschnitten 1, 9 und 10. Betroffen sind nur `phyllotaxis`
(1039 → 965 unoptimiert) und `motif_scatter` (1498 → 1493); alle übrigen Muster
bleiben auf ihren Zahlen.

Die beiden Zahlen im Plan-Nachtrag („erfüllt mit 1673" bzw. „1307 mit
Verbindern") lauten damit jetzt **1625** und **1302** – beide weiterhin deutlich
unter der 2000er-Warnschwelle, beide weiterhin ein Körper.

**Fidelity-Harness bleibt grün.** Die entfernte Schleife *ist* der Fehler;
außerhalb der Schleifenzone bewegt sich nichts. Ein eigener Test hält fest, dass
ein Ring ohne Selbstschnitt punktgenau unverändert bleibt.

**Tests** (`tests/test_stroker.py`, `tests/test_optimize.py`): synthetischer
Reproduzierer für beide Zweige (angeschnittener Kreis für `stroke_closed`,
enge Doppelkehre für `stroke_open`), jeweils mit Gegenprobe gegen den
ungesicherten Stroker; szenenweit „keine selbstschneidende Kontur" für die
bekannten Treffer **und** für alle Muster × Stil-Varianten; Konturzahl-Invariante.

---

## 16. Meilenstein 7 (Option A): `organic_cells` bleibt beim Linienzug

**Auftrag:** prüfen, ob `generators/organic_cells.py` seine gerundeten
Ecken-Konturen generatorseitig als `curve="spline"` liefern kann, ohne die
Geometrie sichtbar zu verändern (< 0,002 cm gegenüber heute).

**Ergebnis: nein – nicht umgesetzt.** Gemessen mit dem Fidelity-Ansatz aus
`tests/test_optimize.py` (Stützpunkte + Sehnenmitten der heutigen Polylinie
gegen den Catmull-Rom-Spline durch dieselben Punkte), Default-Parameter,
Seed 42:

| Muster | Rundheit | Konturen | max. Abweichung | Median | größter Knick |
| --- | ---: | ---: | ---: | ---: | ---: |
| pebbles | 1 | 110 | 0,00273 cm (1,4 × TOL) | 0,00183 cm | 83° |
| pebbles | **2** (Default) | 110 | 0,00466 cm (2,3 × TOL) | 0,00269 cm | 83° |
| pebbles | 3 | 110 | 0,00665 cm (3,3 × TOL) | 0,00350 cm | 83° |
| tissue | **2** (Default) | 160 | 0,00507 cm (2,5 × TOL) | 0,00315 cm | 76° |
| tissue | 3 | 160 | 0,00724 cm (3,6 × TOL) | 0,00420 cm | 76° |
| leaf_veins | **1** (Default) | 125 | 0,04052 cm (20 × TOL) | 0,00259 cm | 107° |

Selbst die günstigste Einstellung (`pebbles`, Rundheit 1) reißt die Toleranz.
`voronoi` steht gar nicht zur Debatte: sein Default ist Rundheit 0, die Kontur
ist ein reines Vieleck.

**Warum das keine Frage der Abtastdichte ist.** Eine gerundete Voronoi-Zelle
ist keine glatte Kurve, sondern ein Vieleck mit Verrundungen: lange gerade
Kanten (bis 0,47 cm) wechseln sich mit winzigen Rundungs-Sehnen ab (bis herunter
zu 1,4e-5 cm). Das Längenverhältnis erreicht **33 000 : 1**. Ein
interpolierender Spline schätzt seine Tangenten aus den Nachbarpunkten; am
Übergang von der langen Kante zur kurzen Rundungs-Sehne dominiert der lange
Nachbar, und die Kurve schießt über die kurze Sehne hinaus. Gemessen an einer
35-Punkt-Kiesel-Kontur: der Fehler auf den langen, geraden Sehnen beträgt
0,00036 cm, auf den kurzen Rundungs-Sehnen dagegen 0,02479 cm – die Ausbeulung
sitzt **in** der Rundung, nicht auf der Geraden.

Dazu kommt der zweite, unabhängige Grund: `round_corners` begrenzt die Rundung
an kurzen Kanten (`limit[]` in `organic_cells.py:190-197`), damit sich
benachbarte Rundungen nicht überschlagen. Wo die Begrenzung greift, bleibt die
Ecke eine Ecke – gemessen 76° bis 107° Knick, weit über dem 30°-Gate, das der
Plan für Splines aus gutem Grund setzt („Fitted Splines überschwingen an
Knicken"). Es ist derselbe Befund wie beim Puzzle (Abschnitt 9): die Ringe
*sind* die Ecken.

**Was es gebracht hätte.** Der Verzicht ist teuer, und das gehört zur
Entscheidung dazu: als Spline gemeldet, kostete jede Zelle 1 statt n Elemente –
`pebbles` 2460 → 114, `tissue` 3232 → 164, `leaf_veins` 2071 → 130
(je Default, Flächenmodus, −94 bis −96 %). Diesen Gewinn gäbe es nur um den
Preis einer sichtbar anderen Kontur; das wäre Glättung (Option B), nicht die
toleranztreue Optimierung, die der Plan verlangt.

**Pass 5 bleibt unverändert im Code** und greift, sobald ein künftiger Generator
dichte, gleichmäßig abgetastete glatte Linienzüge liefert. Am Optimierer wurde
für diesen Meilenstein nichts geändert.
