# Review und Überarbeitung 272 KT RAEUMEN / 273 KT BODEN SCHLICHTEN

Bearbeitet mit Claude Fable 5.2 nach `PROMPT_FUER_KI.md`, Stand 2026-11-24, nach der Zweitprüfung korrigiert
(Abschnitt e), nach deren zweiter Runde nochmals (Abschnitt f) und nach einer unabhängigen dritten Prüfung
(Abschnitt g). Die Messwerte in (c) sind die des Stands nach Runde 3. Aussagen in früheren Abschnitten, die die
dritte Prüfung als zu stark eingestuft hat, sind dort mit **[Berichtigt, Runde 3: …]** gekennzeichnet, nicht gelöscht.
Dieses Ergebnis ist für eine unabhängige Zweitprüfung gedacht. Alles, was unsicher oder nur geschätzt ist,
steht ausdrücklich in Abschnitt (d).

Geändert: `projekt/cyclo/dialog/adaptive.py` (neu geschrieben), `projekt/cyclo/dialog/pocket.py`
(272, 273, `ocm_cycle`), `projekt/cyclo/dialog/translator.py` (8 Zeilen, siehe b.6),
`projekt/tests/test_cycles.py` (2 Tests angepasst, 172 neue Testfälle über alle Runden), `projekt/cyclo/dialog/cyclegen.py` (nur `_helix_in`), dazu neu erzeugt `gcode/*.ngc` (ohne Fusion),
`pruefung.txt`, `vergleich.md`. `quelle/` ist unverändert der alte Stand („vorher“).

Alle Zahlen sind gemessen: Rechner Apple M5 Max, Python aus `.venv`, Messung mit `erzeuge.py` und
`vergleich.py` aus diesem Repo. Zahlen für den Xeon sind **nicht gemessen**, sondern hochgerechnet (siehe d.1).

---

## (a) Befunde am bisherigen Code (`quelle/`), nach Schwere

Belege: „gemessen“ = Wert aus `vergleich.md` (Stand vor der Änderung, git `b1fea37`); „gelesen“ = aus dem Code
abgeleitet, nicht eigens durch einen Test nachgestellt.

| # | Schwere | Befund | Beleg |
|---|---|---|---|
| 1 | hoch | **272: Umschlingung weit über dem Sollwert.** Jede Bahn beginnt stirnseitig an der Wand und schwenkt am Ende eng um das Frontende. Anteil des Schnittwegs über Soll + 15°: T1 8,2 %, T2 6,9 %, T4-Tasche 13,3 %; 95-%-Wert 150–160°, Maximum 175°. Das ist nahe am Vollschnitt mitten in der Bearbeitung (Sicherheitsanforderung 4). | gemessen |
| 2 | hoch | **272: seitlich offene Tasche (T2) wird wie eine geschlossene behandelt.** Das Rohteil ist dem Zyklus nicht bekannt, also Helix ins Volle und Bahnen gegen die offene Seite. Fusion kommt bei demselben Teil auf max. 55°, der alte Code auf 175°. | gemessen |
| 3 | mittel | **272: viele Rückzüge.** T1 25, T2 38, T3 70, T4 52 + 67 (Fusion 4 / 16 / 30 / 30). Jeder Rückzug ist ein Wiedereintauchen neben stehendem Material. | gemessen |
| 4 | mittel | **Rechenzeit.** Punkt-in-Polygon- und Abstandsrechnungen laufen je Bahnpunkt über alle Kanten (`_inside_np`, `_dist_np`, `engagement`). Hier gemessen 2,6–5,0 s je 272-Zyklus; laut Prompt auf dem Xeon bis 12 s. | gemessen (hier) |
| 5 | mittel | **273: senkrechtes Eintauchen, nur Geraden, Ringwechsel mit Knick.** 0 Bögen in allen vier Teilen; Q595 und Q577 werden nicht ausgewertet. | gemessen / gelesen |
| 6 | mittel | **272: Q575, Q577, Q578 ohne Wirkung**, Zustellungen nicht gleichmäßig aufgeteilt (`_levels`: volle Schritte, letzter Schritt = Rest). | gelesen |
| 7 | niedrig | **Clipper-Versatz kann bei entarteten Splitterpolygonen leer zurückkommen** (`slcycles.offset`: Clipper richtet den Umlaufsinn nach dem untersten Polygon aus). Im alten Code habe ich das **nicht** als Fehler nachgestellt; es trat beim Neubau auf und ist dort abgefangen (`adaptive.offset`). Betrifft möglicherweise auch andere Aufrufer von `slcycles.offset`. | beim Neubau beobachtet |
| 8 | niedrig | **273 mit Q370 > 1:** Ringabstand größer als R, zwischen den innersten Ringen kann Boden stehen bleiben. | gelesen, nicht nachgestellt |

Nicht beanstandet: Der alte Code hält die Fertigkontur ein (Verletzung 0,000, Restfläche 0 an allen vier Teilen).
**[Berichtigt, Runde 3: Das gilt nur für die vier Vergleichsteile. Die unabhängige Prüfung misst am alten Code
Wandverletzungen bis 1,9 mm (Tasche 10,1 mm für D10) und eine weggefräste Insel an der offenen Begrenzung
(8,77 mm, Befund K1). Die Aussage „hält die Fertigkontur ein“ war als allgemeine Aussage zu stark.]**

---

## (b) Was geändert wurde und warum

### 1. 272: neuer Bahnplaner „rollende Fronten“ (`adaptive.py`)
Beschreibung der Rechenweise steht als Modul-Docstring in `adaptive.py`. Kurz:
- Die geräumte Fläche F wächst je Schritt um ke; die neue Front wird mit einer **morphologischen Öffnung**
  (Rollradius ρ) ausgerundet. Dadurch läuft jede Bahn tangential an der Wand an und aus, enge Schwenkbögen
  entfallen. Das beseitigt Befund 1.
- Rollradien 2R, R, R/2 … bis Q578·R. Der Schritt ke(ρ) wird je Radius so verkleinert, dass die Umschlingung
  beim Sollwert bleibt. Kleine Rollen arbeiten nur dort, wo die große nicht hinkommt (Ecken, Engstellen).
- Reihenfolge über einen Abhängigkeitsgraphen (ein Stück erst, wenn die Stücke dahinter gefahren sind),
  Verbindungen Bogen–Gerade–Bogen durch geräumte Fläche oder an der fertigen Wand entlang, 0,2 mm angehoben.
- Der fertige Plan läuft durch eine eigene Rastersimulation (0,2 mm): Sie prüft jede Verbindung, bestimmt,
  wo im Eilgang eingetaucht werden darf, und senkt den Vorschub, wo die Umschlingung trotzdem zu hoch ist
  (mit Warnung „Engstelle …“).
- Ausgabe als Geraden und Kreisbögen (Bogenanpassung der Clipper-Polygone), Bögen höchstens 162° je Satz in Schnitt und Verbindungen, in der Helix höchstens 180° (seit e.4; im ersten Stand
  galt das nur für Schnittbahnen – die Aussage „höchstens Halbkreise“ war dort falsch),
  punktförmige Bögen als G1.

### 2. 272: offene Seiten über das Rohteil (`stock`)
`ocm_cycle(..., stock=None)` nimmt optional das Rohteil-Rechteck (xmin, ymin, xmax, ymax). Liegt ein Teil der
Tasche neben dem Rohteil, startet die Bearbeitung von dort ohne Helix. Die Werkzeugmitte bleibt dabei in
`offset(reg, R + Q368)` (Anforderung 1 unverändert).
**Bewusst vorsichtig:** Neben dem Rohteil (Luft nur laut BLK FORM, nicht selbst geräumt) wird nie im Eilgang
zugestellt, sondern mit Q253. Das kostet bei T2 etwa 15 s, schützt aber, falls das wirkliche Rohteil größer
ist als die BLK FORM.
**[Berichtigt, Runde 3: Es fehlte der Hinweis, dass der Bediener davon nichts erfuhr, und dass eine Tasche ganz
außerhalb der BLK FORM ein leeres Unterprogramm ohne Meldung ergab. Beides ist in g.4 behoben (Warnung bzw.
Fehler). Ob die BLK FORM die Bahn überhaupt bestimmen darf, bleibt eine Frage an Steffen.]**

### 3. 272: Parameter
- **Q577**: Radius der An-/Abfahr- und Verbindungsbögen = Q577·R.
- **Q578**: kleinster Rollradius der Räumbahnen in Innenecken = Q578·R.
- **Q575**: 0 = Ebene für Ebene über alle Teilflächen; 1 und 2 = Teilfläche für Teilfläche bis auf Tiefe.
- Zustellungen in gleichen Schritten (`_levels_equal`). Der 2D-Plan wird einmal gerechnet und je Ebene wiederholt.

### 4. 273: zwei Schlichtarten über Q595
- **Q595 = 0, gleiche Bahnabstände** (`_floor_rings`): konturparallele Ringe wie bisher, aber als Bögen,
  Einfahren über eine Helix, die tangential in den ersten Ring mündet, Ringwechsel tangential über Bögen
  (Q577·R), Reihenfolge nach Erreichbarkeit. Bei offener Begrenzung entfällt ein Außenring, der nur Luft
  schneidet. Ringabstand auf höchstens R begrenzt (Befund 8).
- **Q595 = 1, gleicher Eingriff** (Vorgabe im Katalog und in `erzeuge.py`): derselbe Planer wie 272.
- In beiden Arten wird wie bisher ab Sicherheitshöhe im Vorschub zugestellt, nie im Eilgang.

### 5. Tests
- `test_272_adaptive_rounded_links_and_entries` **angepasst**: Der Test verlangte ≥ 4 angehobene *Bögen*.
  Der neue Plan verbindet an einer geraden, fertigen Wand entlang mit angehobenen *Geraden*. Der Test zählt jetzt angehobene Sätze G1/G2/G3 (≥ 4) und verlangt weiter
  mindestens einen angehobenen Bogen. Die übrigen Bedingungen (≤ 2 Rückzüge, kein senkrechtes Eintauchen)
  sind unverändert. Bitte in der Zweitprüfung bewerten, ob das die Absicht des Tests trifft.
- Neu: `test_273_floor_strategies_clear_floor_with_arcs` für Q595 = 0 und 1.

### 6. Abweichung von „alles andere nicht ändern“: `translator.py`
Damit `stock` überhaupt ankommt, übergibt der Übersetzer das Rohteil der BLK FORM an `ocm_cycle` und nimmt
es in den Cache-Schlüssel auf. **Korrigiert (e.1):** Im ersten Stand stand hier, das gelte nur ohne
Verschiebung/Drehung – das war falsch, gesperrt war nur Spiegeln/Maßfaktor. Jetzt gilt es wirklich nur bei
Werkzeugachse Z und ohne Spiegeln/Maßfaktor, TRANS DATUM, Zyklus-10-Drehung, geschwenkte Ebene und
Bezugspunktwechsel (Zyklus 247) nach der BLK FORM. Das ist ein **Vorschlag**; ohne diese Zeilen verhält sich 272 bei T2 wie bisher (geschlossene Tasche).

---

## (c) Messwerte vorher / nachher

Werkzeug D10, 272 mit k = 2 mm (Soll 53°), 273 mit k = 5 mm. Zeit nach `vergleich.py` (Eilgang 10000 mm/min,
ohne Beschleunigung). „> Soll“ = Anteil des Schnittwegs über Soll + 15°.

### 272 KT RAEUMEN

| Teil | Stand | Zeit | Vorschubweg | Rückzüge | G1 | G2/G3 | Umschl. Ø / 95 % / max | > Soll | Rechenzeit (M5 Max) |
|---|---|---|---|---|---|---|---|---|---|
| T1 | vorher | 3:39 | 4992 | 25 | 3225 | 109 | 51° / 155° / 175° | 8,2 % | 2,78 s |
| T1 | **nachher** | 3:20 | 4770 | 2 | 839 | 1046 | 50° / 155° / 175° | 7,2 % | 0,52 s |
| T1 | Fusion | 3:31 | 5005 | 4 | 4424 | 198 | 48° / 150° / 180° | 6,6 % | – |
| T2 | vorher | 4:28 | 6143 | 38 | 3527 | 134 | 50° / 150° / 175° | 6,9 % | 5,00 s |
| T2 | **nachher** | 4:29 | 6504 | 14 | 890 | 1334 | 41° / 55° / 65° | 0,0 % | 0,53 s |
| T2 | Fusion | 4:28 | 6448 | 16 | 5286 | 263 | 40° / 50° / 55° | 0,0 % | – |
| T3 | vorher | 6:57 | 9418 | 70 | 1170 | 142 | 40° / 50° / 100° | 0,1 % | 2,86 s |
| T3 | **nachher** | 7:14 | 10333 | 42 | 662 | 798 | 39° / 50° / 60° | 0,0 % | 0,24 s |
| T3 | Fusion | 6:27 | 9212 | 30 | 5026 | 332 | 39° / 50° / 55° | 0,0 % | – |
| T4 außen | vorher | 5:51 | 7982 | 52 | 1022 | 110 | 38° / 45° / 75° | 0,1 % | 2,58 s |
| T4 außen | **nachher** | 6:07 | 8711 | 38 | 540 | 604 | 38° / 45° / 60° | 0,0 % | 0,18 s |
| T4 Tasche | vorher | 3:08 | 3781 | 67 | 2896 | 167 | 55° / 160° / 175° | 13,3 % | 4,95 s |
| T4 Tasche | **nachher** | 2:56 | 4149 | 8 | 961 | 1539 | 47° / 155° / 175° | 8,4 % | 0,95 s |
| T4 gesamt | Fusion | 10:51 | 15496 | 30 | 14979 | 863 | 40° / 50° / 175° | 1,9 % | – |

**Zur Zeile „> Soll“ bei geschlossenen Taschen (T1, T4-Tasche):** `vergleich.py` zählt die Eintauchhelix mit
(zusammen 239 mm bei T1, 201 mm bei T4-Tasche). Ohne Helix gemessen
(eigenes Hilfsskript, gleiche Simulation):

| Teil | 95 % | max | > Soll |
|---|---|---|---|
| T1 nachher, ohne Helix | 55° | 110° | 0,13 % |
| T4-Tasche nachher, ohne Helix | 55° | 100° | 0,16 % |

Den entsprechenden Wert ohne Helix habe ich für den alten Stand und für Fusion **nicht** gemessen.

### 273 KT BODEN SCHLICHTEN

| Teil | vorher | nachher Q595 = 1 (Planer, wie `erzeuge.py`) | nachher Q595 = 0 (Ringe) | Fusion |
|---|---|---|---|---|
| T1 | 1:35, 1241 mm, 0 Bögen, 1 Rückz. | 2:56, 2227 mm, 358 Bögen, 2 Rückz. | 1:45, 1285 mm, 56 Bögen, 1 Rückz. | 2:50, 1609 mm, 114 Bögen, 1 Rückz. |
| T2 | 1:51, 1461 mm, 0, 1 | 3:49, 2984 mm, 461, 7 | 2:02, 1518 mm, 61, 1 | 2:33, 1703 mm, 66, 3 |
| T3 | 2:58, 2304 mm, 0, 6 | 3:11, 2462 mm, 176, 10 | 2:41, 1817 mm, 89, 4 | 3:46, 2368 mm, 106, 11 |
| T4 außen | 2:52, 2207 mm, 0, 6 | 2:46, 2120 mm, 142, 9 | 2:57, 1702 mm, 83, 8 | 5:27 (beide), 3151 mm, 151, 12 |
| T4 Tasche | 1:04, 826 mm, 0, 2 | 2:42, 2028 mm, 549, 5 | 1:23, 910 mm, 65, 2 | – |

Rechenzeit 273 nachher: Q595 = 1 0,10–0,37 s, Q595 = 0 höchstens 0,05 s. Für den alten Stand nicht getrennt gemessen.
Die Spalte Q595 = 0 stammt aus dem Hilfsskript (gleiche Simulation, im Dialogprogramm Q595 auf 0 gesetzt),
nicht aus `vergleich.md`.

### Abnahme

| Kriterium | Ergebnis |
|---|---|
| `pytest tests/test_cycles.py` | **230 passed, 10 skipped** (vorher 58 passed, 10 skipped; 2 Tests angepasst, 172 neue Testfälle, davon 85 aus Runde 3). Die 10 übersprungenen sind die Vergleichstests gegen den echten LinuxCNC-Interpreter (`CYCLO_RS274` nicht gesetzt), keine bestandenen Abnahmen |
| `erzeuge.py`, alle vier Teile, 272 und 272+273 | Verletzung −0,000, Restfläche Boden 0 mm², keine Befundzeilen (`pruefung.txt`) |
| `vergleich.py` am ganzen Teil | Verletzung 0,000 mm, Restfläche 0 mm², Eilgang im Material 0 – alle vier Teile |
| Mit Q595 = 0 (Hilfsskript) | Verletzung 0, Rest 0, Befunde 0 – alle vier Teile |
| Speicher | größter Wert 373 MB für den Lauf über alle vier Teile samt Simulation (Messskript, nicht der Übersetzer allein) |
| Programmlänge 272 (Zeilen) | T1 3442 → 1924, T2 3808 → 2299, T3 1556 → 1620 (länger), T4 4610 → 3840 |

### Ziele aus dem Prompt – erreicht oder nicht

| Ziel | Stand |
|---|---|
| 1 Umschlingung 95 % ≤ 60°, < 2 % über Soll + 15° (außer Eintauchen) | T2, T3, T4 außen: erreicht. T1, T4-Tasche: erreicht **ohne Helix** (0,13 % / 0,16 %); mit Helix wie bei Fusion nicht. |
| 2 Offene Seite (T2) | erreicht, braucht die Zeilen in `translator.py` |
| 3 Rückzüge ≤ Fusion | T1 2 ≤ 4, T2 14 ≤ 16: erreicht. **T3 42 > 30, T4 46 > 30: nicht erreicht.** |
| 4 Rechenzeit ≤ 3 s auf dem Xeon | nicht gemessen; hochgerechnet vermutlich erreicht außer T4-Tasche (siehe d.1). **[Berichtigt, Runde 3: zu optimistisch. Das gilt nur für die vier Teile. Die unabhängige Prüfung misst schon auf dem M5 Max 8,6–17,9 s in gewöhnlichen Fällen (kleines Q370, grob aufgelöste Inseln, siehe g „Nur dokumentiert“); der Xeon ist rund 4,3-mal langsamer. Ziel 4 ist allgemein nicht erreicht.]** |
| 5 273 mit Bögen, Helix, tangentialem Ringwechsel | erreicht (beide Schlichtarten) |
| 6 Q575, gleiche Zustellschritte | umgesetzt; Bedeutung von Q575 = 1 / 2 ist meine Festlegung (d.4) |
| 7 Q577, Q595, Q578 | umgesetzt; Q578 ist meine Auslegung (d.4) |
| Bearbeitungszeit nicht schlechter als heute | 272: T1 und T4-Tasche besser. **T2 +1 s, T3 +17 s (4 %), T4 außen +16 s (5 %) schlechter.** 273: mit Q595 = 1 **deutlich schlechter** (bis 2,5-fach), mit Q595 = 0 bei T3 besser, sonst 2–19 s schlechter (Helix). |

---

## (d) Offene Punkte und Unsicherheiten

1. **Rechenzeit auf dem Xeon ist nicht gemessen.** Aus dem Verhältnis alt (12 s laut Prompt bei T1) zu hier
   gemessen (2,78 s) ergibt sich Faktor etwa 4,3. Damit wären es rund 2,4 s (T1), 2,5 s (T2), 1,1 s (T3),
   0,8 s + **4,6 s (T4-Tasche, über dem Ziel von 3 s)**. Bitte auf der Zielmaschine messen. Die Zeit liegt
   zu etwa 60 % in Clipper-Versätzen (`grow_fronts`).
2. **Zielkonflikt Rückzüge gegen Zeit.** Die Grenze „Verbindung bis 10·R, sonst Rückzug“ (`Planner.stay`)
   ist an den vier Teilen abgestimmt, nicht hergeleitet. Gemessen an T2: 12·R → 1 Rückzug, 4:47;
   10·R → 15 Rückzüge, 4:28; 3·R → 67 Rückzüge, 3:26. `vergleich.py` rechnet ohne Beschleunigung, Rückzüge
   sind real teurer. T2 trifft Fusion und den alten Wert nur knapp – bei anderen Teilen kann es anders ausfallen.
3. **T3 und T4 außen (offene Begrenzung): Zeit und Rückzüge nicht auf Fusion-Niveau.** Der Schnittweg ist
   rund 300 mm länger als bei Fusion (ausgerollte Bahnenden), dazu mehr Leerwege. Ursache nicht abschließend
   untersucht.
4. **Parameterbedeutungen, die ich festgelegt habe:** Q575 (1 und 2 gleich behandelt: Teilfläche für
   Teilfläche; „von unten nach oben“ / „wechselnd“ sind damit nicht wörtlich umgesetzt), Q578 (kleinster
   Rollradius), Q595 (nach Katalog; der Prompt nennt „mäander/gleichmäßig“). Bitte bestätigen.
5. **273 mit Q595 = 1 ist langsamer als heute.** Gleicher Eingriff ist beim Bodenschlichten (wenige Zehntel
   Tiefe) kaum ein Vorteil. Empfehlung zur Entscheidung: Vorgabe auf 0 setzen oder Q595 = 1 so lassen.
   Nicht entschieden.
6. **Helix je Zustellebene.** Bei geschlossenen Taschen taucht 272 auf jeder Ebene neu per Helix ein
   (Vollschnitt, wie bisher). Die Option aus dem Prompt „Helix nur auf der ersten Ebene, danach Rampe in
   geräumter Fläche“ ist nicht umgesetzt.
7. **Vertrauen in die BLK FORM.** Mit `stock` beginnt 272 Bahnen neben dem Rohteil auf voller Tiefe im
   Vorschub. Ist das wirkliche Rohteil größer als die BLK FORM, schneidet der erste Schnitt dort voll.
   Kein Eilgang, aber ein Risiko, das es vorher nicht gab. Gleiches gilt wie bisher für die offene Begrenzung.
   **[Berichtigt, Runde 3: Seit g.4 gibt es dazu eine Warnung an den Bediener und einen Fehler statt eines
   leeren Unterprogramms; die Grundsatzfrage bleibt offen.]**
8. **Rastergenauigkeit.** Die Freigabe von Eilgang-Eintauchen und Verbindungen beruht auf einem
   0,2-mm-Raster mit Sicherheitszuschlag (Werkzeugfläche R + 0,3 muss leer sein). Die unabhängige Prüfung
   (`erzeuge.py`, `vergleich.py`, Raster 0,1 mm) meldet 0 Eilgänge im Material an den vier Teilen; ein
   Beweis für beliebige Konturen ist das nicht. Wandreste bis 0,06 mm (`TOL_WALL`) bleiben beim Schruppen stehen.
9. **Sicherheitsanforderung 1** wird seit der Korrektur e.3 für jedes ausgegebene Element geprüft (seit f.1 zuverlässig, mit 2 µm Toleranzreserve – nicht „exakt“)
   (`prims_within`) und durch `test_27x_feed_points_inside_allowed_area` am gerundeten G-Code belegt
   (n-Eck-Taschen). Ein Test mit Inseln und offener Begrenzung nach demselben Muster fehlt noch.
   **[Berichtigt, Runde 3: „für jedes ausgegebene Element“ war falsch. Die Helix-Einfahrt von 273 mit Q595 = 0
   wurde nur an 32 Punkten geprüft und lag bis 10 µm in der Wand (K3, behoben in g.3). Bei offener Begrenzung
   mit einer Insel an der Rohteilkante war schon die zulässige Fläche selbst falsch – dort half keine
   Elementprüfung (K1, behoben in g.1). Der fehlende Test mit Inseln und offener Begrenzung war genau die Lücke.]**
10. **Verbindungen an der fertigen Wand entlang** laufen 0,2 mm angehoben genau auf der Wandbahn. Seitlich
    berührt das Werkzeug dabei die fertige Wand (kein Abtrag laut Simulation). Ob das an der Maschine
    stört (Spuren), ist nicht beurteilt.
11. **Vorschubabsenkung an Engstellen** gibt Faktoren im F-Wort aus (z. B. halber Vorschub). Die Stufen
    (ab Soll + 30°) sind gewählt, nicht aus Schnittdaten hergeleitet.
12. **273 bei kleinerem Schlichtwerkzeug als Räumwerkzeug:** In Ecken, die das Räumwerkzeug nicht erreicht
    hat, steht volles Material. 273 fährt dort wie bisher auf Tiefe hinein. Unverändert, aber erwähnenswert.
13. **Testabdeckung:** Geprüft sind die vier Vergleichsteile und die Fälle in `test_cycles.py` (Rechteck,
    Kreis, Insel, Q370 = 0,3 … 1,5). **[Stand Runde 3: schmale Nuten, Werkzeuge ohne ANGLE, Inseln an der offenen Begrenzung, Ringnuten und ein Zufallstest mit 960 Fällen sind inzwischen geprüft, siehe f und g.]** Ursprünglich nicht geprüft: sehr schmale Nuten, viele Inseln, Gegenlauf (Q351 = −1)
    an den Vergleichsteilen, Werkzeuge ohne ANGLE an den Vergleichsteilen, gedrehte/verschobene Konturen
    mit `stock` (dort wird `stock` nicht übergeben).
14. **Nicht eingecheckt:** `erzeuge.py` schreibt `dialog/`, `gcode/`, `step/`, `stl/` unter
    `projekt/examples/trochoidal_vergleich/`. Nur die G-Code-Dateien sind nach `gcode/` kopiert.

---

## (e) Zweitprüfung und Korrekturen

Die unabhängige Zweitprüfung (Bericht `review-2/pkg/audit/REVIEW_RESULT.txt`) hat den ersten Stand **nicht**
freigegeben. Fünf Befunde waren zu beheben, zwei bleiben als Frage an den Entwickler. Die Gegenbeispiele der
Zweitprüfung sind als eigene Tests in `tests/test_cycles.py` nachgebaut (Abschnitt „Zweitprüfung 272/273“).
Alle Zahlen unten sind an diesem Stand gemessen.

### Einordnung der Befunde

„Regression“ = durch meinen ersten Stand neu entstanden. „Altverhalten“ = schon im alten Code so.
„Vorgabenabweichung“ = verletzt eine Vorgabe des Prompts, ohne dass ein Schaden nachgewiesen ist.
Nummern wie im Bericht der Zweitprüfung. Blocker für die Freigabe waren 1 und 2.

| # | Befund | Art | Formale Verletzung | Praktische Auswirkung | Stand |
|---|---|---|---|---|---|
| 1 | `stock` bei TRANS DATUM / Drehung | **Regression** (`stock` gab es vorher nicht) – **Blocker** | Anforderung 3 | Bei verschobenem/gedrehtem Nullpunkt: senkrechter Einstich im Vorschub auf volle Tiefe ins Material (nachgestellt bei T2 mit `TRANS DATUM X-30`). Kein Eilgang, aber Werkzeugbruch möglich. Ohne Verschiebung/Drehung kein Effekt. | behoben (e.1) |
| 2 | Schmale Nut: zweiter senkrechter Einstich | **Regression** im neuen Planer; wie der alte Code dieselbe Nut fährt, habe ich nicht gemessen – **Blocker** | Anforderung 3 | Zweiter Einstich auf volle Tiefe in unberührtes Material, rund 20 mm neben dem ersten. Das Vollnutfräsen selbst (Nut kaum breiter als das Werkzeug) ist Werkzeugwahl, kein Fehler der Bahnrechnung – zu beheben war der Einstich. | behoben (e.2) |
| 3 | Bahn bis 0,011 mm außerhalb der zulässigen Fläche | **Regression** (neue Verbindungsbögen und Bogenanpassung in 273) | Anforderung 1 | Bei Q368 = 0 bis 11 µm in die Fertigkontur, nur an Polygonecken beim Ringwechsel von 273. Im 0,1-mm-Abtragsraster nicht sichtbar. An den vier Teilen nicht aufgetreten (Verletzung 0,000). | behoben (e.3) |
| 4 | Helix auf jeder Zustellebene | **Altverhalten** (unverändert übernommen) | Anforderung 4 nach wörtlicher Lesart | Vollschnitt in der Helix je Ebene; Fusion macht es bei T1 ebenso. | offen – Frage an Steffen |
| 5a | Bögen über 180° in Verbindungen | **Altverhalten, durch mich verschlimmert**: `_emit_link` ist alter Code und teilt nicht. Nachgezählt im alten G-Code (`b1fea37`): T1 3, T2 0, T3 4, T4 9; in meinem ersten Stand 1 / 12 / 42 / 45. | Ausgabevorgabe „höchstens Halbkreise“ (**Vorgabenabweichung**) | Für LinuxCNC gültige I/J-Bögen, kein Konturfehler nachgewiesen. Meine Aussage „höchstens Halbkreise“ war falsch. | behoben (e.4) |
| 5b | Helix-Restbogen mit gleichen Endpunkten | **Altverhalten** (`cyclegen._helix_in`) | Vollkreis-Schutz der Ausgabevorgabe | Ein ungewollter Vollkreis auf dem Helixradius bei bestimmten Tiefen; kein Konturschaden nachgewiesen. | behoben (e.4) |
| 6 | `Grid.free` sieht Material in der Werkzeugscheibe nicht | **Regression** (neuer Code) – nachgewiesene Lücke der Verbindungsprüfung | keine direkt; schwächt den Nachweis für Anforderung 2/4 | Angehobene Verbindungen konnten durch Restmaterial freigegeben werden. Am Helfer nachgewiesen; eine Kollision im ganzen Programm wurde nicht nachgestellt. Die Eilgang-Freigabe (`clear`) war nicht betroffen. Tatsächlich aufgetreten ist der Fall in e.2 (Ring um Insel aus dem Vollen angefahren). | behoben (e.5) |
| 7 | Speicher / Rechenzeit bei großen Flächen und vielen Inseln | Speicher: **Vorgabenabweichung**, nur aus dem Code abgeleitet (über 500 MB ab etwa 5000 × 5000 mm), **nicht gemessen**. Rechenzeit: 14,9 s für 16 Inseln **gemessen** (Zweitprüfung); Altstand dazu nicht gemessen. | 500-MB-Grenze, 3-s-Ziel | Übersetzung dauert lange bzw. könnte bei sehr großen Flächen am Speicher scheitern; keine Auswirkung auf die Bahn. | teilweise (e.6) |

### e.1 `stock` bei Verschiebung/Drehung (kritisch) – behoben
- **Fehler:** `not xf` sperrte nur Spiegeln/Maßfaktor. Mit TRANS DATUM (G52) oder Zyklus 10 (G10 L2 R) bekam
  272 weiter das Rohteil und plante einen Start „aus der Luft“ an einer Stelle, an der Material steht.
  Meine Aussage in b.6 war falsch.
- **Fix (`translator.py`):** Das Rohteil geht nur an 272/273, wenn die BLK FORM ohne aktive
  Verschiebung/Drehung/Ebene definiert wurde und seither keine TRANS DATUM, keine Drehung (Zyklus 10),
  keine geschwenkte Ebene und kein Bezugspunktwechsel (Zyklus 247) aktiv ist; Zylinder-Rohteile nie.
  Sonst plant 272 wie für eine geschlossene Tasche (Helix). Transformiert wird nicht – nur gesperrt.
- **Test:** `test_272_stock_open_side_only_without_datum_shift_or_rotation` – mit `TRANS DATUM X-30`,
  `TRANS DATUM X+0 Y+0` und `ROT+90` ist das Unterprogramm zeilengleich mit dem ohne BLK FORM; nach
  `TRANS DATUM RESET` wieder zeilengleich mit dem offenen Plan.
- **Offen:** Andere Wege, das Koordinatensystem zu ändern (z. B. direkt programmiertes G-Code-Durchreichen,
  falls es das gibt), habe ich nicht gesucht.

### e.2 Schmale Nut: senkrechter Einstich (kritisch) – behoben
- **Fehler:** Helixradius unter 0,3 mm wurde verworfen, dann senkrecht eingetaucht; später ein zweiter
  Einstich ins Volle. Beim Nachstellen kam ein zweiter, bis dahin unentdeckter Fall dazu: In
  `test_ocm_island_with_boundary` wurde ein Ring um die Insel aus dem vollen Material angefahren (die
  Überblendung scheiterte an einer falschen Tangente an einer Mini-Kante, der Ersatzweg begann im Material).
- **Fix (`adaptive.py`, `pocket.py`):**
  - Ist für eine Helix wenig Platz (Radius < halber Sollradius), wird auf der längsten Sehne durch die
    Mitte eine **Pendelrampe** mit dem Winkel ANGLE gefahren, danach eine ebene Bahn. Warnung
    „Nut kaum breiter als das Werkzeug – Eintauchen über Pendelrampe im Vollschnitt“.
  - Sonst Helix auch mit kleinem Radius (ab 0,02 mm). Geht beides nicht: senkrecht **mit Warnung**
    „Kein Platz für Helix oder Rampe“.
  - Ein Bahnstück beginnt nur noch an einer nachweislich geräumten Stelle (bei Ringen werden zwölf
    Anfangspunkte versucht) oder wird auf Tiefe über eine dünne Haut (höchstens k/2, max. 1 mm) angefahren.
    Gibt es keinen solchen Anfang, bricht der Zyklus mit `CycleError` „Kein sicherer Einstieg bei X… Y…“ ab,
    statt senkrecht einzutauchen. Der frühere stille Ersatz ist entfernt.
- **Tests:** `test_272_narrow_slot_no_vertical_plunge` (50 × 10,4 / 10,6 / 11 / 14, 11 × 11 mit D10,
  1,2 × 1,2 mit D1): keine senkrechte Vorschubbewegung unter Z−0,3, höchstens 2 Rückzüge, Boden fertig,
  kein Eilgang im Material. `test_272_no_room_for_helix_or_ramp_warns`.
- **Bleibt:** In einer Nut, die kaum breiter ist als das Werkzeug, ist die Umschlingung zwangsläufig 180°
  (Rampe und Nutgrund). Das meldet die Warnung; Anforderung 4 ist dort geometrisch nicht erfüllbar.
  Der neue `CycleError` kann Programme abbrechen, die vorher (unsicher) durchliefen – an den vier Teilen
  und in allen Tests tritt er nicht auf.
  **[Berichtigt, Runde 3: Als Entwarnung war das zu schwach belegt. Im Zufallstest der unabhängigen Prüfung
  brachen 17 von 490 Taschen mit ANGLE und 34 von 113 ohne ANGLE ab, dazu 21 von 72 Ringnutbreiten – Fälle,
  die der alte Code rechnet (H2, H3; behoben in g.5 und g.6, Zahlen danach siehe dort).]**

### e.3 Bahn außerhalb der zulässigen Fläche (Anforderung 1) – behoben
- **Ursache (nachgemessen):** nicht der gefittete Ring, sondern der **Verbindungsbogen**, der an einer
  Polygonecke in den nächsten Ring mündet. Er lief bis 0,011 mm über die Nachbarkante; die Prüfung tastete
  nur alle 0,5 mm ab. Daneben können gefittete Bögen ihre Sehnen um die Pfeilhöhe verlassen.
- **Fix:** (1) Geplant wird in der um 6 µm verkleinerten Fläche (`WALL_MARGIN`). (2) Jedes ausgegebene
  Element – Schnittbögen, Geraden, Verbindungen, Ringwechsel – wird gegen (in diesem Stand noch mit Clipper und als „exakt“ bezeichnet – beides in f.1 korrigiert)
  `offset(reg, R + Q368)` geprüft (`prims_within`, keine Stichproben). Fällt ein Bogen durch, bleiben dort
  die Sehnen; fällt eine Verbindung durch, wird sie verworfen.
  **[Berichtigt, Runde 3: „Jedes ausgegebene Element … keine Stichproben“ stimmte nicht für die Helix-Einfahrt
  von 273 / Q595 = 0 (32 Stichpunkte, K3). Seit g.3 wird auch sie mit `prims_within` geprüft.]**
- **Test:** `test_27x_feed_points_inside_allowed_area` – 24-, 40-, 64-, 200-Eck, 272 und 273 (Q595 0 und 1):
  größte Überschreitung am gerundeten G-Code **0,000000 mm** (vorher bis 0,010982 mm).
  **[Berichtigt, Runde 3: Der Wert gilt für die geprüften n-Eck-Taschen, nicht allgemein (Gegenbeispiel K3:
  Quadrat 27,497, +10 µm).]**
- **Preis:** Die Bahn steht 6 µm weiter von der Wand. Deshalb habe ich die Restflächengrenze in
  `test_272_adaptive_pocket_engagement_and_rest[18]` von 0,5 auf 2,0 mm² angehoben (gemessen 0,92 mm²;
  der Test zählt Rasterzellen im 6-µm-Saum). **Das ist eine zweite gelockerte Testgrenze – bitte bewerten.**

### e.4 Bögen über 180° und Vollkreis-Rest (hoch) – behoben
- **Fehler:** `_emit_link` teilte Bögen nicht; in den gelieferten Programmen 1 / 12 / 42 / 45 Bögen über
  180°. `_helix_in` (alter Code) konnte einen Restbogen mit gleichen Endpunkten ausgeben.
- **Fix:** Eine gemeinsame Ausgabe `_out` für Schnitt und Verbindungen: Teilung auf höchstens 162°, und ein
  Bogen, dessen Endpunkte nach Runden und Transformation gleich wären, wird als G1 ausgegeben.
  `cyclegen._helix_in` (außerhalb meines eigentlichen Auftrags, auf Anweisung): winziger Restbogen als G1.
- **Test:** `test_27x_arcs_at_most_half_circle`, `test_helix_rest_arc_is_no_full_circle`.
  Nachgezählt in allen zwölf neu erzeugten `gcode/*.ngc`: **0 Bögen über 180°, 0 mit gleichen Endpunkten**.

### e.5 `Grid.free` (hoch) – behoben
- **Fehler:** nur Mitte + 24 Punkte auf einem Kreis; Material dazwischen blieb unsichtbar.
- **Fix:** Geprüft wird die ganze Werkzeugscheibe bis R − 0,1 mm (Zellmaske je Punkt). Ragt die Scheibe über
  das Raster, gilt die Stelle als nicht frei (auch in `Grid.clear`).
- **Test:** `test_grid_free_sees_material_inside_tool_disc` (Gegenbeispiel der Zweitprüfung).
- **Grenze bleibt:** Raster 0,2 mm; ein Rest schmaler als 0,1 mm am äußersten Werkzeugrand wird nicht
  gesehen. Die Bahn wird weiter als Polygon simuliert und erst danach in Bögen umgesetzt (Abweichung
  höchstens 0,012 mm).

### e.6 Speicher und Rechenzeit (mittel) – teilweise
- **Fix:** Vor dem Anlegen des Rasters wird die Größe geprüft (höchstens 12 Mio. Zellen, rund 480 000 mm²
  je Teilfläche). Darüber `CycleError` „Bearbeitungsfläche zu groß …“. Test `test_272_area_too_large_gives_error`.
- **Gemessen:** 80 × 80 mit 16 Inseln jetzt 3,88 s (Zweitprüfung: 14,9 s am alten Stand), 17 296 Zeilen.
  Warum es schneller wurde, habe ich nicht untersucht (vermutlich weniger verworfene Verbindungen).
  **[Berichtigt, Runde 3: Der Fall ist nicht schneller geworden. Die unabhängige Prüfung hat nachgemessen
  (M5 Max, ein Prozess): Inselkreise als 16-Eck 15,8 s / 19 484 Zeilen, als 32-Eck 17,9 s, als 64-Eck 3,86 s,
  als 128-Eck 4,5 s. Mein Wert galt für eine feinere Auflösung der Inselkreise als die der Zweitprüfung; die
  Rechenzeit hängt um den Faktor 4 bis 5 an dieser Auflösung. Als Verbesserung ist die Zahl nicht belastbar.]**
- **Nicht gemacht:** gekachelte Karte, Freigeben von `grid`/`pieces` nach dem Plan. Den Speicherbedarf an
  der Grenze von 12 Mio. Zellen habe ich **nicht gemessen**.

### Nicht behoben – Fragen an Steffen
1. **Helix auf jeder Zustellebene (Befund 4 der Zweitprüfung).** Auf der zweiten Ebene taucht 272 wieder per
   Helix ins Volle ein. Die Zweitprüfung wertet das als Verstoß gegen Anforderung 4 („außer beim allerersten
   Eintauchen“). Es ist das alte Verhalten, und Fusion macht es bei T1 ebenso. Entweder die Anforderung so
   auslegen, dass jede Ebene ihr Eintauchen haben darf, oder eine Rampe in geräumter Fläche bestellen.
2. **Q575 = 1 und 2** laufen weiter durch denselben Zweig (siehe d.4).
3. **Gelockerte Tests:** jetzt zwei (b.5 und e.3). Die Zweitprüfung merkt zu b.5 an, dass der Ersatz weder
   tangentiale Anschlüsse noch Materialfreiheit belegt. Materialfreiheit und Bogenwinkel decken jetzt die
   neuen Tests ab, Tangentialität nicht.

### Auswirkung der Korrekturen auf die Messwerte
Gegenüber dem ersten Stand (Commit `03c96b4`): T1 3:19 → 3:20, T2 4:28 → 4:29 (14 statt 15 Rückzüge),
T4 außen 6:06 → 6:07, T3 und T4-Tasche gleich. Rechenzeit 272 je Zyklus 0,16–0,97 s (vorher 0,14–0,89 s).
`erzeuge.py` und `vergleich.py`: alle vier Teile Verletzung 0,000, Restfläche 0 mm², kein Eilgang im Material.

---

## (f) Zweitprüfung Runde 2 und Korrekturen

Grundlage: `review-2/pkg2/audit/REVIEW_RESULT_ROUND2.txt` und `review-2/pkg2/FABLE_FIX_INSTRUCTIONS_ROUND2.md`.
Vier Befunde; Helix je Zustellebene und Q575 waren ausdrücklich nicht Teil des Auftrags.
Commits auf `fable-review`: `bbc605f` (Befund 1), `52f407a` (Befund 2), `f3da535` (Befunde 3 und 4), dazu der
Commit mit diesem Bericht und den neu erzeugten Ergebnisdateien.

**Art des Nachweises** – in diesem Abschnitt bedeutet:
*Helfertest* = eine einzelne Funktion mit konstruierten Eingaben; *G-Code-Prüfung* = Auswertung der gerundeten
ausgegebenen Sätze; *Abtragssimulation* = Z-Map des Projekts (`cyclo.sim`); *LinuxCNC* = Lauf im echten
Interpreter. **LinuxCNC-Läufe gab es nicht** (die 10 übersprungenen Tests brauchen `CYCLO_RS274`), auch keinen
Maschinenlauf und keine Messung auf dem Zielrechner.

### f.1 `prims_within` gab außen liegende Geraden frei (hoch)
- **Befund:** Rechteck (0,0)–(10,10), Gerade (1,−1)→(9,−1): Ergebnis `True`, ebenso bei y = −0,01.
- **Ursache:** Die Prüfung beruhte auf einer Clipper-Differenz „offener Pfad minus Fläche“. Für waagerechte
  offene Strecken außerhalb der Fläche liefert diese Operation (pyclipper 1.4.0) keine Reststücke; die leere
  Differenz wurde als „alles zulässig“ gelesen. Am alten Stand nachgestellt: waagerecht unterhalb falsch,
  waagerecht oberhalb und schräg richtig. Die tiefere Ursache in Clipper habe ich nicht weiter untersucht.
- **Änderung (`adaptive.py`, `bbc605f`):** Keine Clipper-Differenz mehr. Neue Klasse `Region`: Die Fläche wird
  um 2 µm verkleinert (`PRIMS_TOL`), dann in Gleitkomma geprüft: (1) keine Strecke der Bahn berührt oder
  kreuzt eine Kante (Endpunkte eingeschlossen, auch parallel aufliegende Strecken), (2) ein Punkt der
  zusammenhängenden Bahn liegt innen. Bögen werden durch Sehnen mit höchstens 0,1 µm Pfeilhöhe ersetzt.
  Entartete Elemente (Länge 0) werden als Punkt geprüft. Leere Fläche → `False`.
- **Garantierte Toleranz:** Ergebnis `True` heißt: Die wahre Bahn liegt in der zulässigen Fläche. Von den
  2 µm Reserve gehen bis 0,7 µm Ganzzahlrundung des verkleinerten Polygons, 0,1 µm Pfeilhöhe und rund
  0,1 µm Rundung der Ausgabe (vier Stellen) ab; es bleibt rund 1 µm. Die Prüfung ist **toleranzbehaftet,
  nicht exakt**: Bahnen näher als etwa 2–3 µm am Rand werden abgelehnt, obwohl sie zulässig wären. Frühere
  Formulierungen „exakt geprüft“ in (b), (d), (e) und im Code sind korrigiert. Nicht abgedeckt: die
  Interpretation der Bögen durch LinuxCNC selbst (Mittelpunktrundung in I/J).
- **Regressionstest (Helfertests):** 23 Fälle in fünf Tests `test_prims_within_*`: waagerecht unterhalb/oberhalb,
  senkrecht, schräg, innen→außen, quer durch; ganz innen; auf und entlang der Grenze; beide Endpunkte innen
  mit Insel bzw. einspringender Aussparung dazwischen; Bögen mit zulässigen Endpunkten und unzulässigem
  Zwischenverlauf (auch nur 0,02 mm); entartete und sehr kurze Elemente; leere Eingaben.
  **Am Stand vor dem Fix schlugen 6 dieser Fälle fehl** (waagerecht unterhalb ×2, entartet außen, Grenze,
  Insel/Aussparung, Bögen), danach bestehen alle.
- **Ergebnis:** G-Code-Prüfung unverändert sauber: n-Eck-Taschen 24/40/64/100/200, 272 und 273 (Q595 0/1),
  größte Überschreitung 0,0 mm. Die vier Teile verlieren dadurch praktisch keine Bögen (T1 1076 → 1074).
  **[Berichtigt, Runde 3: „größte Überschreitung 0,0 mm“ gilt für diese n-Eck-Taschen. Nicht genannt war die
  Folge der engen Toleranz: Bahnen näher als 2–3 µm am Rand werden abgelehnt, und wo der Planer keinen Ersatz
  hatte (Spirale um den Innenkreis), brach der Zyklus ab – Ringnuten und Zapfentaschen, H3, behoben in g.6.]**

### f.2 Pendelrampe fand schräge Nuten nicht (mittel)
- **Befund:** Rechtecktasche 100 × 10,4 bei 17° brach mit `CycleError` ab (ebenso 30 × 10,2 bei 43°,
  15 × 10,05 bei 7°), obwohl eine Rampe längs der Nut passt.
- **Ursache:** `_longest_chord` probierte nur Richtungen im 5°-Raster durch den Mittelpunkt. Bei 17° blieb
  eine 11-mm-Sehne; der Rest der Nut war danach nur über einen Einstich erreichbar → Abbruch. Bei
  gewinkelten Nuten lag der Stützpunkt im Knick, die Rampe wurde unnötig kurz (7 mm).
- **Änderung (`adaptive.py`, `pocket.py`, `52f407a`):** Zusätzliche Richtungen aus den Konturkanten der
  Fläche (die längsten zuerst), danach Winkelverfeinerung in vier Stufen bis 0,004°; zusätzliche Stützpunkte
  in der Mitte der längsten Schenkel. Die gewählte Strecke wird mit `prims_within` gegen die zulässige Fläche
  geprüft; fällt sie durch, gibt es keine Rampe. Der `CycleError` bleibt, mit getrennten Meldungen:
  „Bahnplaner findet keinen sicheren Anfahrweg … (kein Nachweis, dass es keinen gibt)“ bzw. „… findet weder
  Helix noch Rampe … (kein Nachweis, dass keine möglich ist)“. Senkrechtes Eintauchen mit Warnung
  „Kein Platz für Helix oder Rampe (Werkzeug füllt die Tasche aus)“ gibt es nur noch, wenn die Fläche der
  Werkzeugmitte in jeder Richtung kürzer als 0,3 mm ist – das ist ein Nachweis, kein Suchergebnis.
  Kein stiller senkrechter Ersatz.
  **[Berichtigt, Runde 3: Das galt nur für die Pendelrampe. Mit ANGLE ≥ 90° entstand ohne Meldung ein Einstich
  von Z+1 auf Z−4,96 über 0,29 mm mit dem Fräsvorschub (K2, behoben in g.2); eine Helix mit 0,04 mm Radius ist
  praktisch senkrecht und kam ohne Warnung (M3, Warnung seit g.7).]**
- **Regressionstest:** `test_27x_ramp_in_slots_of_any_direction`, 24 Fälle: 100 × 10,4 / 17°, 30 × 10,2 / 43°,
  15 × 10,05 / 7°, 50 × 10,4 / 0°, L-Nut 60 mm gerade und um 11° gedreht; jeweils 272 und 273/Q595 = 1,
  Q351 = +1 und −1. Geprüft wird je Fall:
  - *G-Code-Prüfung:* alle Vorschubpunkte unter der Oberfläche in `offset(reg, R)` (1 µm Probentoleranz);
    Rampe pendelt zwischen genau zwei Punkten, nutzt die Nutlänge (mindestens 80 % bzw. 40 mm); Neigung jeder
    Rampenstrecke ≤ ANGLE + 0,05° (0,05° = Rundung der Ausgabe auf 1e-4 bei Strecken ab 0,25 mm);
    Rampenvorschub = Q207·Q568 bzw. Q385·Q568; gerade Zahl von Strecken; Endtiefe.
  - *Abtragssimulation:* Boden im erreichbaren Bereich fertig, kein Eilgang im Material, und **kein
    senkrechter Einstich ins Material** – dafür wird vor jeder senkrechten Zustellung der Abtrag bis dahin
    simuliert; senkrechte Zustellungen über schon geräumtem Bereich zählen nicht. Bei 273 ist das Rohteil in
    der Simulation bis auf 0,3 mm Bodenaufmaß vorgeräumt.
  **Am Stand vor dem Fix schlugen 20 der 24 Fälle fehl** (alle außer 0°).
- **Ergebnis:** alle 24 bestehen. Die Einstiegsneigung ist aus `n = ceil(Tiefe / (L·tan ANGLE))`, auf gerade
  Zahl erhöht, konstruktiv ≤ ANGLE.
  **[Berichtigt, Runde 3: „konstruktiv ≤ ANGLE“ gilt im ungestreckten System und nur für 0 < ANGLE < 90°. Mit
  einem Maßfaktor nur in Z (Zyklus 26) werden Rampe und Helix steiler als ANGLE (N2 der dritten Prüfung, altes
  Verhalten, nicht behoben – siehe g, offene Punkte).]**
- **Grenzen:** Gesucht wird weiterhin nur eine **gerade** Rampe. In einer gewinkelten oder gebogenen Nut
  fährt die Rampe einen Schenkel; der Rest wird danach von dort aus im Vollschnitt geräumt (Warnung). Eine
  Rampe entlang einer gekrümmten Mittellinie gibt es nicht. Richtungswechsel an den Rampenenden,
  Beschleunigung und Schnittkräfte sind nicht geprüft. Bogenförmige Nuten habe ich nicht getestet.

### f.3 Speichergrenze galt nur je Teilfläche (mittel)
- **Befund:** 12 Mio. Zellen je Teilfläche; mehrere Pläne samt Raster, Bahnstücken, Masken und
  Zwischenfeldern konnten zusammen über 500 MB kommen.
- **Ursache:** Kein gemeinsames Budget; `grid` und `pieces` blieben in jedem Plan gespeichert; Masken und
  Zwischenfelder waren nicht berücksichtigt.
- **Änderung (`adaptive.py`, `pocket.py`, `f3da535`):**
  - `Budget` je Aufruf von `plan_regions` (= ein Zyklusaufruf), Grenze `MEM_BUDGET` = **200 MB geschätzte
    Planungsdaten**; bis 500 MB bleiben **300 MB Reserve** für Python, numpy, pyclipper, den Übersetzer und
    alles, was die Schätzung nicht erfasst.
  - `plan_need` schätzt je Teilfläche **vor** dem Anlegen des Rasters: Raster 1 Byte/Zelle; beim Füllen mit
    dem Rohteil +10 Byte/Zelle (vorübergehend); Werkzeugmasken 75 Byte × (2·(R/h + 1) + 1)²; Besitzerkarte
    der Reihenfolge 40 Byte je Zelle; Bahnen 400 Byte je halbem Millimeter (Länge ≈ Fläche/k); 10 MB pauschal
    für die Prüffläche. Dazu kommt, was schon gehalten wird (fertige Pläne, 2 MB Grunddaten).
    **Nicht enthalten:** Clipper-Zwischenergebnisse und Python-Verwaltung – dafür die Reserve.
  - Raster, Masken und Bahnstücke werden nach jeder Teilfläche freigegeben (`grid`/`pieces` nur noch mit
    `debug=True` im Plan). `Grid.fill` kommt ohne zweite Ganzzahlkarte aus; die Rechenfelder der Prüffläche
    sind auf rund 10 MB je Schritt begrenzt.
  - Überschreitung → `CycleError` „Bahnberechnung bräuchte etwa … MB Arbeitsspeicher (Grenze … MB)“.
  - Die 12-Mio.-Zellen-Grenze je Teilfläche bleibt zusätzlich bestehen.
- **Regressionstests (Helfertests, künstlich kleines Budget):**
  `test_memory_budget_counts_all_components_of_one_call` (zwei Teilflächen passen einzeln, zusammen nicht;
  Abbruch, bevor das zweite Raster angelegt wird; wiederholte Aufrufe addieren nichts auf),
  `test_memory_budget_includes_tool_masks` (R = 60 mm scheitert an den Masken, R = 5 mm passt; kein Raster
  angelegt), `test_memory_budget_error_message_from_cycle` (normaler Fall im Budget; Meldung über
  `ocm_cycle`), `test_memory_estimate_covers_measured_peak`.
- **Gemessen (Apple M5 Max, eigenes Messskript, je Fall ein eigener Prozess):**

  | Fall | Schätzung Spitze | tracemalloc Spitze (Python + numpy, ohne Clipper) | Prozess-Spitze (maxrss, mit 38 MB Grundlast) | Zeit |
  |---|---|---|---|---|
  | Tasche 200 × 200, k = 2 | 28,7 MB | 8,6 MB | 69 MB | 3,5 s |
  | Tasche 500 × 500, k = 2 | 120,0 MB | 37,8 MB | 176 MB | 20,4 s |
  | offene Begrenzung 600 × 600, k = 5 | 197,4 MB (knapp unter dem Budget) | 98,8 MB | 169 MB | 3,7 s |

  Prozess-Spitze aus dem Messskript selbst; `/usr/bin/time -l` meldet für dieselben Läufe 72 / 185 / 178 MB.
  Die Schätzung liegt in allen Messungen über dem tracemalloc-Wert. Gegen den Prozessspeicher ist sie bei
  der geschlossenen Tasche **zu niedrig** (120 MB geschätzt, 138 MB Zuwachs) – das fängt die Reserve.
- **Abschätzung, nicht gemessen:** Für eine geschlossene Tasche an der Budgetgrenze (200 MB geschätzt)
  ergäbe das Verhältnis aus der Messung rund 230 MB Zuwachs, also etwa 270 MB Prozessspeicher. Einen Fall
  genau an der Grenze mit kleinem k habe ich **nicht** laufen lassen. Speicher mit tracemalloc läuft
  langsamer; die Zeiten oben sind deshalb keine Leistungswerte.
- **Grenzen:** Der Bahn-Anteil der Schätzung ist ein Erfahrungswert aus drei Messungen, kein Nachweis. Bei
  sehr kleinem k oder sehr vielen Inseln kann das Verhältnis anders ausfallen. Die 500 MB sind damit
  konstruktiv begrenzt, aber nicht bewiesen. Auf dem Zielrechner nicht gemessen.
  **[Berichtigt, Runde 3: „konstruktiv begrenzt“ war zu stark. Die unabhängige Prüfung misst für einen
  Zufallsfall (Tasche rund 90 mm, D16, ohne ANGLE; Fall 400007) 632–710 MB Prozessspitze auf macOS bei einer
  Budget-Schätzung von 14 MB und 84 MB laut tracemalloc; der Sprung entsteht in `_link_tree`. Die Schätzung
  erfasst diesen Anteil nicht. Eigene Nachmessung nach Runde 3 siehe g, „Nur dokumentiert“.]**

### f.4 Helix-Regressionstest war unwirksam (niedrig)
- **Befund:** Der Test aus e.4 nutzte die Restzugabe 1e-5; damit bestand er auch mit dem alten `_helix_in`.
- **Ursache:** Falscher Wert übernommen; das Gegenbeispiel der ersten Runde hatte 1e-6. Ich hatte nicht
  geprüft, ob der Test am alten Helfer fehlschlägt.
- **Änderung (`tests/test_cycles.py`, `f3da535`; kein Produktivcode):**
  `test_helix_in_rest_arc_old_full_circle_new_none` ruft den Helfer direkt auf – einmal die unveränderte Kopie
  des alten `_helix_in` (im Test eingebettet), einmal den korrigierten – mit `rh = 4,75`, ANGLE 3°, Tiefe
  `3·pitch + 1e-6`. Ausgewertet werden die **gerundeten Wörter der Ausgabe**.
- **Ergebnis (G-Code-Prüfung am Helfer):** alter Helfer **1** Bogen mit gleichen Endpunkten (Vollkreis),
  korrigierter **0**; für beide Drehsinne. Zusätzlich geprüft: Endposition, Endtiefe, Vorschubwort, die
  beiden ebenen Abschluss-Halbkreise (je 180°, ohne Z), Drehsinn. `test_helix_in_regular_case_unchanged`
  (0,3 / 1,0 / 2,5 Umläufe, beide Drehsinne): Ausgabe des neuen Helfers **zeilengleich** mit dem alten.
  Der gemeinsame Helfer wurde in dieser Runde nicht geändert. Berichtigung zu e.4: Die Helix gibt weiter
  Halbkreise (180°) aus, nicht 162°-Stücke.
- **Nicht geprüft:** relative/gespiegelte/skalierte Ausgabe des Helfers (das hat die Zweitprüfung selbst
  getan), Ausführung in LinuxCNC.

### Abnahme nach Runde 2

| Schritt | Art | Ergebnis |
|---|---|---|
| `pytest tests/test_cycles.py` | Helfer-, G-Code- und Simulationstests | **145 passed, 10 skipped** (die 10: LinuxCNC-Abgleich, nicht ausgeführt) |
| `erzeuge.py`, vier Teile, 272 und 272+273 | Abtragssimulation | Verletzung −0,000, Restfläche Boden 0 mm², keine Befundzeilen |
| `vergleich.py` | Abtragssimulation | alle vier Teile Verletzung 0,000 mm, Restfläche 0 mm², Eilgang im Material 0 |
| Bögen in den zwölf neu erzeugten `gcode/*.ngc` | G-Code-Prüfung, eigenes Zählskript | 13 966 Bögen, **0 über 180°, 0 mit gleichen Endpunkten** |
| Gegenbeispiele Runde 1 (Nuten, n-Ecke, 16 Inseln) | G-Code-Prüfung und Simulation | Nuten ohne senkrechten Einstich, n-Ecke 0,0 mm außerhalb, 16 Inseln 4,07 s **[Berichtigt, Runde 3: die 4,07 s gelten für fein aufgelöste Inselkreise; mit 16- oder 32-Eck-Inseln misst die Prüfung 15,8 bzw. 17,9 s, siehe e.6]** |
| Gegenbeispiele Runde 2 | als eigene Tests nachgebaut | siehe f.1–f.4 |
| Skripte der Zweitprüfung (`review-2/pkg2/audit/*.py`) | – | **nicht ausgeführt**: sie laufen gegen die Kopie `pkg2/repo/`, nicht gegen `projekt/` |
| LinuxCNC-Interpreter, Maschine, Zielrechner | – | **nicht ausgeführt** |

Messwerte der vier Teile gegenüber Abschnitt (e): Bearbeitungszeiten, Wege und Rückzüge unverändert;
Satzzahlen leicht anders (z. B. T1 272: 877/1076 → 880/1074 G1/Bögen); Rechenzeit 272 je Zyklus 0,19–1,06 s
(vorher 0,16–0,97 s), weil die neue Flächenprüfung mehr rechnet. Tabelle (c) ist aktualisiert.
Keine Testgrenze wurde in dieser Runde gelockert.

### Verbleibende Grenzen
1. `prims_within` prüft mit Toleranz (rund 1 µm Reserve), nicht exakt; die Bahn wird weiter als Polygon
   simuliert und erst danach in Bögen umgesetzt.
2. Nur gerade Pendelrampen; gewinkelte und gebogene Nuten werden nach der Rampe im Vollschnitt geräumt.
3. Speicherbudget beruht auf einer Schätzung mit Reserve; an der Budgetgrenze nicht gemessen.
4. Der Sicherheitsrand von 6 µm zur Wand und die Restflächengrenze von 2 mm² im Test (e.3) bestehen
   unverändert. Die Zweitprüfung empfiehlt, zusätzlich Restzellen außerhalb eines vereinbarten Randbandes
   auszuschließen – **nicht umgesetzt**, weil es eine Vereinbarung mit Steffen über das Band braucht. Die
   2 mm² gelten nur für diesen einen Testfall.
5. Offene Entscheidungen für Steffen wie in (e): Helix je Zustellebene, Q575, senkrechter Einstieg mit
   Warnung, wenn das Werkzeug die Tasche ausfüllt oder ANGLE fehlt, Vollschnitt in schmalen Nuten.
   **[Berichtigt, Runde 3: Für „ANGLE fehlt“ war das kein bloßer Entscheidungspunkt, sondern ein Rückschritt:
   ohne ANGLE wurde die Bahn 3,5- bis 6-mal so lang oder der Zyklus brach ab (H2, behoben in g.5).]**
6. Rechenzeit auf dem Zielrechner weiter ungemessen; T4-Tasche hochgerechnet rund 4,6 s (Ziel 3 s).


---

## (g) Unabhängige dritte Prüfung und Korrekturen

Bericht der Prüfung (neue Sitzung ohne Kenntnis der Abschnitte a–f): `review-3/audit/REVIEW_RESULT.txt`.
Sie bestätigt die Abnahmeläufe und findet im Normalfall (geschlossene Tasche, 0 < ANGLE < 90°, Insel nicht an
der Rohteilkante) in rund 1500 Läufen keine Wandverletzung, keinen Eilgang im Material und kein Restmaterial.
Neu sind drei kritische Befunde (K1–K3), drei hohe (H1–H3) und Kleinigkeiten (M3, M4, N1), die hier behoben
sind. K1 und K2 stammen aus dem alten Code und waren von mir übernommen, K3, H2 und H3 sind Rückschritte
meiner Neufassung.

Commits (Branch `fable-review`, nicht gepusht): `1b77ef2` Code und Tests; der Commit mit diesem Abschnitt,
den Messwerten und dem neu erzeugten G-Code folgt direkt darauf.
**Berichtigung zur Commit-Nachricht von `1b77ef2`:** Dort steht, am Stand `f6d9828` schlügen 61 der 85 neuen
Testfälle fehl. Die Zahl stammt von einem Zwischenstand mit 79 Fällen. Nachgezählt am Endstand der Testdatei:
**67 von 85 schlagen an `f6d9828` fehl**, 18 sind Vergleichsfälle, die vorher wie nachher bestehen (ANGLE 3
und 0, Insel 0,5 mm innerhalb, breite Durchgänge, Insel abseits).

**Art des Nachweises** wie in (f): *Helfertest*, *G-Code-Prüfung* (gerundeter G-Code, eigener kleiner Parser
`_gcode_samples` in der Testdatei, Bögen als Bögen), *Abtragssimulation*. Zusätzlich *Prüfer-Skripte*: die
Skripte aus `review-3/audit/` in einer Kopie außerhalb des Repos, in der nur der Pfad auf `projekt/` zeigt
(und im Zufallstest die Inselprüfung auch für die offene Begrenzung eingeschaltet ist). Ihre Vergleichswerte
für den alten Stand stammen aus den Protokollen der Prüfung (`review-3/audit/log_*.txt`), nicht von mir.

### g.1 K1 – Insel an oder über der offenen Begrenzung wurde weggefräst (kritisch)
- **Befund:** Begrenzung 80 × 60 (Q569 = 1 bzw. Figur mit Begrenzung), Insel bündig an der Rohteilkante, über
  sie hinaus, in der Ecke oder als Streifen über die ganze Breite: Werkzeug bis 9,9 mm in der Insel, beim
  Streifen Eilgang 4 mm tief in die Insel. Anforderungen 1 und 2 verletzt. Altes Verhalten.
- **Ursache:** `_work_area` und `_floor_rings` lasen die Inseln aus den Löchern der fertigen Fläche ab. Berührt
  eine Insel die Begrenzung, ist sie kein Loch mehr, sondern eine Einbuchtung der Außenkontur. Die Außenkontur
  galt als Rohteilkante, wurde um R + Aufmaß + 2k nach außen geöffnet – also in die Insel hinein –, und die
  Insel galt als Luft neben dem Rohteil.
- **Änderung:** Die Inselkonturen werden selbst mitgeführt. `region_from_polys` gibt eine Liste zurück, die
  die Inseln als Attribut trägt (`pocket._Region.islands`); `ocm_cycle` nimmt sie zusätzlich als optionalen
  Parameter `islands=`. Neue Funktion `_open_parts` (für 272, 273/Q595 = 1 und 273/Q595 = 0): Rohteil ist die
  Außenkontur der Fläche **einschließlich** der Inseln, die sie berühren oder überlappen; gesperrt bleibt jede
  Insel um R + Q368. Der Übersetzer musste dafür nicht geändert werden (er ruft `region_from_polys`).
- **Regressionstest:** `test_27x_open_boundary_island_on_edge_is_protected`, 15 Fälle (4 Lagen der Insel und
  1 Vergleichslage 0,5 mm innerhalb; 272, 273/Q595 = 1, 273/Q595 = 0). *G-Code-Prüfung:* größte Eindringtiefe des
  Werkzeugkörpers in das Insel-Rechteck unter der Oberfläche, Eilgang und Vorschub. **Vorher bis 10,25 mm**
  (12 der 15 Fälle schlagen fehl), **nachher höchstens 0,006 mm** (Sehnenfehler des Clipper-Versatzes).
  `test_272_open_boundary_island_on_edge_explicit_islands_and_translator`: derselbe Fall über `islands=` mit
  einer einfachen Liste als Fläche und über den Übersetzer (Figur 1271 als Insel, Begrenzung 1281 verschoben).
  `test_272_open_boundary_island_far_outside_changes_nothing`: eine Insel ganz abseits ändert den G-Code nicht.
- **Ergebnis, Prüfer-Skripte:** `t08_open.py edge` (8 Lagen × 3 Zyklen): kein Fall mit Inselbefund (im Protokoll der Prüfung
  12 von 24, einer davon mit Eilgang im Material). Zufallstest: 189 Fälle mit offener Begrenzung, davon 129 mit Inseln, größte Eindringtiefe
  0,0072 mm.
- **Grenze:** Wer `ocm_cycle` mit einer Fläche aus anderer Quelle aufruft (einfache Liste, kein `islands=`),
  bekommt das alte Verhalten: Inseln nur aus den Löchern. Das ist nicht abgefangen, weil eine Einbuchtung der
  Begrenzung von einer Insel an der Kante dann nicht zu unterscheiden ist. Im Projekt gibt es keinen solchen
  Aufrufer. **Annahme, bitte bestätigen:** Der Teil einer Insel, der über die Begrenzung hinausragt, gilt als
  Material (das Werkzeug fährt außen um ihn herum).

### g.2 K2 – ANGLE ≥ 90° oder negativ: die Helix tauchte nie ein (kritisch)
- **Befund:** Werkzeug mit ANGLE = 90 (auch 120, 180, −3): Die Helix lief auf Z+1 in der Luft, der erste Satz
  unter der Oberfläche fiel von Z+1 auf Z−4,96 über 0,29 mm mit dem Fräsvorschub. 273/Q595 = 0 fuhr den ganzen
  Boden auf Z−4,6 statt Z−5. Keine Warnung. Ursache in `_helix_in` alt, die Folgen teils neu.
- **Ursache:** `pitch = 2πr·tan(ANGLE)` ist bei 90° praktisch unendlich und bei anderen Werten negativ; der
  Drehwinkel bis zur Tiefe wird 0 oder negativ, die Schleife läuft nicht, kein Satz bringt Z auf Tiefe.
- **Änderung:** (1) `pocket._plunge_tool`: nur 0 < ANGLE < 90° gilt als Eintauchwinkel. Jeder andere Eintrag
  wird wie ein fehlender behandelt – senkrecht mit dem Eintauchvorschub (Q568) – mit der Warnung
  „Eintauchwinkel ANGLE = …° … liegt nicht zwischen 0 und 90° – Werkzeug taucht senkrecht ein“. Gilt für 272
  und beide Schlichtarten von 273. (2) `cyclegen._helix_in` erzwingt die Endtiefe: Ergibt die Steigung keinen
  Drehwinkel, obwohl Tiefe zu fahren ist, wird senkrecht mit dem übergebenen Vorschub zugestellt. Der
  reguläre Fall bleibt zeilengleich (bestehender Test `test_helix_in_regular_case_unchanged`).
- **Regressionstest:** `test_27x_entry_reaches_depth_for_any_angle_entry`, 18 Fälle (ANGLE 90, 120, 180, −3, 3, 0;
  drei Zyklen), Tasche 60 × 40 mit Insel. *G-Code-Prüfung:* der tiefste Vorschubpunkt jeder Vorschubfolge
  zwischen zwei Eilgängen ist die Solltiefe; kein Satz mit XY-Bewegung fällt steiler als 45° (ausgenommen die
  0,2 mm zwischen Verbindungshöhe und Tiefe); bei unbrauchbarem ANGLE gibt es die Warnung und einen eigenen
  Satz `G1 Z-5` mit dem Eintauchvorschub. **Vorher schlagen die 12 Fälle mit unbrauchbarem ANGLE fehl.**
  `test_helix_in_forces_end_depth` (Helfertest, ANGLE 90, 135, −3): vorher blieb Z auf dem Startwert.
- **Ergebnis, Prüfer-Skripte:** `t07_angle90.py` – siehe Tabelle „Abnahme nach Runde 3“.
- **Grenze:** ANGLE knapp unter 90° (z. B. 89,999) bleibt ein gültiger Eintrag und ergibt einen sehr steilen
  kurzen Helixsatz mit dem Eintauchvorschub; das hat die Prüfung als in Ordnung eingestuft.

### g.3 K3 – 273 mit Q595 = 0: Helix-Einfahrt ragte über die Wand (kritisch, formal)
- **Befund:** Quadrattasche 27,497 (auch 27,495 … 27,501, 25,5, 20,0), D10, Q370 = 0,4, Q368 = 0: Helixkreis bis
  10 µm außerhalb von `offset(reg, R)`. Rückschritt (die Helix-Einfahrt bei 273 ist neu).
- **Ursache:** `enter()` in `_floor_rings` prüfte den Helixkreis an 32 Punkten mit `inside()`, das Randpunkte als
  innen zählt – die eine Stelle, die nicht durch `prims_within` ging.
- **Änderung:** Der Helixkreis wird als zwei Halbkreise mit `prims_within` gegen die zulässige Fläche geprüft,
  wie jedes andere Element. Mehr Radien zur Auswahl (0,95 / 0,8 / 0,6 / 0,45 / 0,35 / 0,25 / 0,15 · R), damit
  knappe Fälle weiter eine Helix bekommen.
- **Regressionstest:** `test_273_rings_helix_entry_inside_allowed_area`, 6 Größen. *G-Code-Prüfung*, Bögen als
  Bögen: **vorher 5,5 bis 10,5 µm außerhalb (alle 6 schlagen fehl), nachher höchstens 0,1 µm** (Rundung).
- **Ergebnis, Prüfer-Skripte:** `t03_floorhelix.py`: Quadrate 12 … 32 mm in Schritten von 0,025 (923 Läufe):
  0 Überschreitungen über 0,15 µm (Prüfung am alten Stand laut Bericht: 3 Treffer bei 801 Größen); Rechteck- und Inselreihen ebenfalls 0.

### g.4 H1 – BLK FORM bestimmt die Bahn: Warnung und Fehler (hoch)
- **Befund:** Mit `stock` startet die Bearbeitung neben dem „Rohteil“ laut BLK FORM; der Bediener erfuhr davon
  nichts. Tasche ganz außerhalb der BLK FORM: leeres Unterprogramm ohne Meldung.
- **Änderung:** `pocket._stock_warnings`. Liegt die Tasche ganz außerhalb des Rohteils: `CycleError` „Tasche
  liegt ganz außerhalb des Rohteils (BLK FORM) – nichts zu bearbeiten“. Ergibt die BLK FORM eine offene Seite:
  Warnung „Tasche seitlich offen laut BLK FORM – Werkzeug startet neben dem Rohteil und stellt dort mit Q253
  zu; die BLK FORM muss dem wirklichen Rohteil entsprechen“.
- **Regressionstest:** `test_27x_stock_open_side_warns_and_pocket_outside_stock_is_error` (272 und 273: halb
  außerhalb → Warnung, ganz innerhalb → keine, ganz außerhalb → Fehler). Vorher fehlgeschlagen.
- **Nicht entschieden (Frage an Steffen):** ob die BLK FORM die Bahn überhaupt bestimmen darf und ob das
  abschaltbar sein soll. Am Verhalten selbst ist nichts geändert.

### g.5 H2 – Werkzeug ohne ANGLE: Abbruch oder vielfache Bahnlänge (hoch)
- **Befund:** Ohne ANGLE brachen 34 von 113 geschlossenen Zufallstaschen ab („findet keinen sicheren
  Anfahrweg“); wo gerechnet wurde, war die Bahn 3,5- bis 6-mal so lang. Rückschritt.
- **Ursache:** Nach dem senkrechten Einstich wuchsen die Fronten aus einer Scheibe von 0,02 mm statt aus einem
  Kreis, und ohne Fahrtrichtung lehnte `_approach` jeden Anfahrweg ab.
- **Änderung** (`plan_regions`): Ohne ANGLE wird bei `c` senkrecht eingetaucht und von dort **dieselbe Spirale
  wie nach der Helix** gefahren (Radius ab 0 bis zum Innenkreis; Zuwachs je Umlauf mindestens min(k, 0,1·R),
  Vorschub bei hoher Umschlingung abgesenkt). In schmalen Nuten (gleiche Bedingung wie für die Pendelrampe):
  senkrecht am Anfang der längsten Sehne, dann die Sehne einmal auf Tiefe, Warnung „… nach dem senkrechten
  Einstich Vollschnitt entlang der Nut“.
- **Regressionstests:** `test_27x_tool_without_angle_plans_fuzz_cases` (die drei Zufallsfälle 100002, 100011,
  100040 der Prüfung, Geometrie auf 1 µm gerundet eingebettet; vorher `CycleError`).
  `test_272_tool_without_angle_same_path_as_with_angle` (Rechteck 80 × 50: Bahn höchstens 10 % länger als mit
  ANGLE, genau ein senkrechter Einstich, Boden laut Abtragssimulation fertig; **vorher 9238 mm gegen 2788 mm**).
  `test_27x_tool_without_angle_in_narrow_slot` (Nuten 10,4 / 11 / 14 breit, 272 und 273: eine Einstichstelle,
  Bahn nicht länger als mit ANGLE, Boden fertig; vorher alle 6 fehlgeschlagen).
- **Ergebnis:** Zufallstest der Prüfung, 960 Fälle: 145 nicht offene Fälle ohne ANGLE, **0 Abbrüche** (vorher 34).
  Bahnlängen nach `t16_noangle.py`: 

  | Fall (272, D10) | mit ANGLE 3° | ohne ANGLE, nachher | ohne ANGLE, vorher (Prüfung) |
  |---|---|---|---|
  | Rechteck 80 × 50 | 2659 mm, 1276 Zeilen, 0,3 s | 2634 mm, 1297 Zeilen, 0,3 s | 9177 mm, 10 825 Zeilen, 3,2 s |
  | Rechteck 80 × 50, Q370 = 0,2 | 4703 mm, 2849 Zeilen | 4705 mm, 2880 Zeilen, 0,6 s | 15 854 mm, 24 033 Zeilen, 7,3 s |
  | Kreis r30 | 1142 mm, 79 Zeilen | 1111 mm, 100 Zeilen | 4637 mm, 7825 Zeilen, 2,3 s |
  | Rechteck 150 × 100 | 8197 mm, 4466 Zeilen, 1,1 s | 8159 mm, 4487 Zeilen, 1,1 s | 31 801 mm, 44 863 Zeilen, 14,8 s |
  | Zufallsfall 400058 | 6921 mm, 2659 Zeilen | 6888 mm, 2693 Zeilen, 0,6 s | 42 803 mm, 84 438 Zeilen, 26,4 s |

  `t19_evidence.py`, 13 einfache Formen × Q370 0,4 / 1,0 ohne ANGLE: 0 Abbrüche von 26.
- **Grenzen:** Das Aufweiten nach dem senkrechten Einstich hat in den ersten Umläufen eine Umschlingung über
  dem Sollwert (Vorschub dort abgesenkt). Ich zähle es zum Eintauchen und nehme es aus der Meldung
  „Engstelle“ heraus; gemeldet wird der senkrechte Einstich. **Das ist meine Festlegung, bitte bewerten.**
  273/Q595 = 0 ohne ANGLE taucht wie bisher ohne Meldung senkrecht ein (nur Bodenaufmaß + 0,2 mm tief).

### g.6 H3 – „Bahn verlässt die zulässige Fläche“ bei Ringnuten und Zapfentaschen (hoch)
- **Befund:** Ringnut außen r30 / innen r14, Kreistasche r30 mit Zapfen r5 und 17 von 490 Zufallstaschen mit
  ANGLE brachen ab. Rückschritt aus f.1.
- **Ursache:** `inscribed()` meldete als Innenkreisradius den letzten gelungenen Clipper-Versatz. Der ist nur
  auf rund 5 µm genau; bei der Ringnut 16 mm waren es 2,9947 gemeldet gegen 2,9891 wirklichen Wandabstand. Die
  Spirale bis zu diesem Radius fiel durch `prims_within` (Reserve 4 µm), und dafür gab es nur den Abbruch.
- **Änderung:** (1) `inscribed()` misst den Wandabstand am Mittelpunkt in Gleitkomma nach (`wall_dist`) und
  meldet nie mehr als diesen. (2) In `plan_regions` wird der Endkreis der Spirale schrittweise verkleinert
  (um 1 µm bis 75 %), bis die Sehnen der Spirale `prims_within` bestehen; erst wenn das bei keinem Radius
  gelingt, kommt der Fehler „findet weder Helix noch Rampe“.
- **Regressionstests:** `test_inscribed_radius_never_exceeds_wall_distance` (Helfertest, 5 Nutbreiten; vorher 4
  fehlgeschlagen). `test_272_ring_groove_and_boss_pocket_plan` (5 Fälle, darunter die beiden der Prüfung;
  *G-Code-Prüfung:* Werkzeugmitte zwischen Zapfen + R und Wand − R; vorher 2 fehlgeschlagen).
- **Ergebnis:** Zufallstest: 626 nicht offene Fälle mit ANGLE, 1 Abbruch („Werkzeug zu groß für die Kontur“,
  Fall 400012, berechtigt und unverändert) – vorher 17 + 1. `t04_inscribed.py`: Ringnut außen r30,
  72 Breiten von 10,5 bis 28,25 mm: **0 Abbrüche** (Prüfung vorher: 21); Kreistasche mit mittigem Zapfen: 0 von
  39 (vorher 4); Rahmennut 0 von 87 und Quadrat mit runder Insel 0 von 45 (beide wie vorher). Bei Breite 16
  meldet `inscribed()` jetzt 2,9891 = gemessener Wandabstand.

### g.7 Kleinigkeiten M3, M4, N1
- **M3 – winzige Helix:** Warnung „Helixradius nur … mm (Tasche kaum größer als das Werkzeug) – Eintauchen fast
  senkrecht, Werkzeug mit Zentrumsschnitt nötig“, wenn der Helixradius unter 0,3·R liegt.
  Test `test_272_tiny_helix_radius_warns` (Tasche 10,1 × 10,1). Am Eintauchen selbst ist nichts geändert.
- **M4 – still ausgelassene Durchgänge:** Durchgänge, die im Sicherheitsrand von 6 µm verschwinden (bis 12 µm
  breiter als das Werkzeug), werden weiterhin nicht gefräst. In Runde 3 gab es die Warnung nur bei 272 und
  273/Q595 = 1; **seit Runde 4 (h) auch bei Q595 = 0**: „Durchgang kaum breiter als das Werkzeug … wird nicht
  bearbeitet – dort bleibt Material stehen“. Erkannt wird Boden, den nur die
  unverkleinerte Fläche erreicht (dicker als 0,1 mm). Test `test_272_skipped_passage_warns`: 10,004 und 10,012 →
  Warnung, 10,014 / 10,03 / 14 → keine. Nachgemessen (Abtragssimulation): bis 10,012 bleiben rund 112–116 mm²
  im Durchgang stehen, ab 10,014 wird er gefräst.
- **N1 – Eingabeprüfung** (`pocket._check_input`, für 272 und 273): `CycleError` bei Q200 < 0, Q368 < 0,
  Q369 < 0 oder ≥ |Q201|, Q568 ≤ 0, Q201 ≥ 0. Test `test_27x_input_checks` (14 Fälle, vorher 13 fehlgeschlagen).
  **Nicht geändert:** Q253 = FAUTO, stilles Begrenzen von Q370 auf 0,04 … 1,9, Q595 ≠ 0 als Planer.
  **Hinweis:** Programme mit Q369 ≥ |Q201| oder Q568 = 0 brechen jetzt ab, wo sie vorher eine nutzlose Bahn
  bzw. `F0` ergaben.

### Nicht behoben – Fragen an Steffen
1. **H1-Grundsatz:** Darf die BLK FORM die Bahn bestimmen? Soll es abschaltbar sein? (g.4)
2. **Helix auf jeder Zustellebene** (Anforderung 4 wörtlich; offen seit Runde 1, siehe e und d.6).
3. **Q575 = 1 und 2** gleich behandelt (d.4).
4. **M2 – Spiegeln einer Achse (Zyklus 8) macht aus Gleichlauf Gegenlauf.** Altes Verhalten, von der Prüfung
   gemessen: Material bei X-Spiegelung links der Bahn statt rechts; mit X und Y gespiegelt wieder Gleichlauf.
   Wand, Eilgang und Bögen sind unter Spiegelung in Ordnung. Soll Q351 beim Spiegeln einer Achse umgedreht werden?
5. **K1-Annahme:** Inselteil außerhalb der Begrenzung gilt als Material (g.1).
6. **N2 – Maßfaktor nur in Z (Zyklus 26):** Helix und Rampe werden um den Faktor steiler als ANGLE (aus dem
   Code gelesen, alt, nicht geändert).
7. **Die beiden gelockerten Testgrenzen** aus b.5 und e.3 (N5 der Prüfung) bitte ausdrücklich abnehmen.

### Nur dokumentiert – Rechenzeit und Speicher (M1, N4)
Messwerte **der Prüfung** am Stand vor Runde 3 (M5 Max, ein Prozess), nicht von mir nachgemessen, soweit nicht
anders vermerkt:
- **M1 Rechenzeit:** Tasche 60 × 40 mit Insel, Q370 ≤ 0,04: 8,6–10,2 s, 15 678 Zeilen; Q370 = 0,1: 3,6 s;
  Rechteck 300 × 300, Q370 = 0,1: 17,7 s. 80 × 80 mit 16 Inseln: 15,8 s (Inselkreise als 16-Eck), 17,9 s
  (32-Eck), 3,86 s (64-Eck), 4,5 s (128-Eck). Zufallstest (8 Prozesse nebeneinander): Median 0,13 s, 99 %
  5,4 s, größter Wert 29,8 s. Ziel 4 (≤ 3 s auf dem Xeon) ist damit schon auf dem M5 Max in gewöhnlichen
  Fällen nicht erreicht. An der Rechenzeit habe ich in Runde 3 nichts gezielt geändert.
  *Eigene Messung nach Runde 3, derselbe Zufallstest:* Median 0,12 s, 99 % 2,15 s, größter Wert 3,9 s. Die
  langen Läufe der Prüfung waren Fälle ohne ANGLE (g.5); kleines Q370 und grob aufgelöste Inseln sind davon
  nicht berührt.
  *Eigene Nachmessung nach Runde 3 (`t21_sealed_checks.py`):* 16 Inseln als 16-Eck 16,0 s, 32-Eck 17,9 s,
  64-Eck 3,9 s, 128-Eck 4,5 s – unverändert.
- **N4 Speicher:** Zufallsfall 400007 (Tasche rund 90 mm, D16, ohne ANGLE): 632–710 MB Prozessspitze auf macOS
  bei 84 MB laut tracemalloc und 14 MB Budget-Schätzung; der Sprung entsteht in `_link_tree`. Große Flächen
  mit ANGLE: 650 × 650 mm → 152 MB. Auf Debian nicht gemessen. Die Schätzung des Speicherbudgets (f.3) erfasst
  die datenabhängigen Spitzen in `_link_tree` nicht ausreichend – seit Runde 4 (h) werden die konkreten
  Arrays und Abhängigkeiten vorab budgetiert, die Abfragen erfolgen blockweise.
  *Eigene Nachmessung nach Runde 3 (`/usr/bin/time -l`, macOS):* derselbe Fall 400007 braucht jetzt 0,6 s,
  5156 Zeilen und **57 MB** Prozessspitze, weil ohne ANGLE nicht mehr aus einem Punkt geplant wird (g.5). Die
  Ursache in `_link_tree` ist damit nicht untersucht, nur dieser Auslöser entfällt; ein anderer Fall mit sehr
  vielen Bahnstücken kann denselben Speicher brauchen.

### Abnahme nach Runde 3

| Schritt | Art | Ergebnis |
|---|---|---|
| `pytest tests/test_cycles.py` | Helfer-, G-Code- und Simulationstests | **230 passed, 10 skipped** (vorher 145 / 10; die 10: LinuxCNC-Abgleich, nicht ausgeführt). 85 neue Testfälle, 67 davon schlagen am Stand `f6d9828` fehl |
| `erzeuge.py`, vier Teile, 272 und 272+273 | Abtragssimulation | Verletzung −0,000, Restfläche Boden 0 mm², keine Befundzeilen |
| `vergleich.py` | Abtragssimulation | alle vier Teile Verletzung 0,000 mm, Restfläche 0 mm², Eilgang im Material 0 |
| Bögen in den zwölf neu erzeugten `gcode/*.ngc` | G-Code-Prüfung, eigenes Zählskript | 14 014 Bögen, **0 über 180°, 0 mit gleichen Endpunkten**, größter Winkel 180,000° |
| Zufallstest der Prüfung (`t11_fuzz.py`, 960 Fälle, Inselprüfung auch bei offener Begrenzung) | Prüfer-Skript | **959 rechnen** (vorher 908), 1 berechtigter Abbruch. Kein Fall mit Wandverletzung über der Referenz (größter Wert −1,35 µm, negativ = innen), Inselverletzung (größter Wert 7,3 µm = Sehnenfehler), Eilgang im Material, senkrechtem Einstich bei 272 mit ANGLE oder Restfläche über 2 mm² (größter Wert 0,04 mm²). 48 Fälle mit mehr als 1 mm Vollschnitt außerhalb des Einstiegs (vorher 43 von 908), bei 272 alle mit Warnung. 1 Fall mit Bögen knapp über 180° – siehe unten |
| `t08_open.py edge / multi / stock / stock2` | Prüfer-Skript | edge: 16 ohne Befund, 8 nur „REQ4“ (Vollschnitt des innersten Rings bei 273/Q595 = 0, wie in der Vergleichslage), **kein Inselbefund**. multi: unverändert gegenüber dem Protokoll der Prüfung (3 × „REQ1phys“ +6,3 µm = Sehnenfehler des Clipper-Rundversatzes an einer runden Insel, G-Code zeilengleich). stock / stock2: kein Eilgangtreffer |
| `t03`, `t04`, `t07`, `t16`, `t19`, `t20`, `t21`, `t02`, `t06` | Prüfer-Skripte | `t03`: 0 Überschreitungen (g.3). `t04`: 0 Abbrüche (g.6). `t07` (ANGLE 90): 272 ein senkrechter Einstich 5 mm mit Warnung, Restfläche 0, kein Eilgangtreffer; 273/Q595 = 0 und 1 Boden auf Z−5, Restfläche 0. `t16`, `t19`: g.5; in `t19` Insel bündig an der Kante: Werkzeugkörper höchstens 0,002 mm in der Insel, 0 mm² der Insel abgetragen (Prüfung vorher: 693 von 1200 mm²). `t20`: alle fünf Kurzfälle rechnen. `t21`: siehe „Nur dokumentiert“. `t02` (Konturen, 198 gerechnete Läufe): 12 Abbrüche, alle „Werkzeug zu groß für die Kontur“ bei Taschen bis 10 µm über Werkzeugmaß (Prüfung: dieselben 12 und 4 weitere „Bahn verlässt die zulässige Fläche“, die jetzt rechnen); kein Befund Wand (Referenz), Eilgang, Insel oder Bogen; Restfläche nur an den Durchgängen 10,0 / 10,004 / 10,012 und der Engstelle 10,01 – jetzt jeweils mit der Warnung M4. `t06` (Parameter): kein Eilgang- und kein Bogenbefund mehr (Prüfung: 2 Fälle Eilgang unter der Oberfläche bei Q200 < 0, 3 Fälle Bogenradius); die 21 Abbrüche sind die neuen Eingabeprüfungen (16), „Werkzeug zu groß“ (3) und Q253 = FAUTO (2, unverändert). Senkrechte Einstiche ins Material nur bei Werkzeug ohne bzw. mit unbrauchbarem ANGLE, bei Taschen ohne Platz (10,03 und 1,05 für D10 / D1) und in einem Fall 273/Q595 = 0 mit Q368 = 2, Q369 = 1 (Zustellung Bodenaufmaß + 0,2 mm; ob das Protokoll der Prüfung denselben Fall zeigt, habe ich nicht abgeglichen) | |
| LinuxCNC-Interpreter, Maschine, Zielrechner | – | **nicht ausgeführt** |

**Bögen knapp über 180° bei winziger Helix:** Im Zufallstest meldet das Prüfer-Skript einen Fall (600113,
273, D6, Helixradius 0,128 mm) mit 3 Bögen über 180°. Das sind Helix-Halbkreise, deren Endpunkte nach dem
Runden auf vier Stellen den Winkel um Hundertstel Grad über 180° heben. Die Prüfung hat dasselbe am alten
Stand an einem anderen Fall gemessen (Radius 0,052 mm: 180,16°) und als im I/J-Format eindeutig eingestuft.
**Seit Runde 4 (h) behoben:** `cyclegen._helix_in` prüft die gerundeten Wörter und teilt nur betroffene Bögen.
Die Warnung M3 zum kleinen Helixradius bleibt richtig und erscheint weiterhin.

**Messwerte der vier Teile gegenüber (f):** T2, T3 und T4 außen sind zeilengleich. T1 und T4-Tasche ändern
sich geringfügig, weil der Innenkreis jetzt nachgemessen wird (g.6): T1 272 Vorschubweg 4771 → 4770 mm,
1993 → 1924 Zeilen; T4-Tasche 272 4143 → 4149 mm; 273 T4-Tasche 2:41 → 2:42. Zeiten 272 und Rückzüge
unverändert. Tabelle (c) ist aktualisiert.
Rechenzeit je Zyklus (M5 Max, Hilfsskript): 272 0,18–0,95 s, 273/Q595 = 1 0,10–0,37 s, 273/Q595 = 0 höchstens
0,05 s. Die Spalte Q595 = 0 ändert sich durch g.3 (Helixradius wird jetzt geprüft und fällt teils kleiner aus):
T1 1:44 → 1:45, T3 2:39 → 2:41 (1811 → 1817 mm), T4 außen 2:54 → 2:57 (1693 → 1702 mm); Verletzung 0,
Rest 0, Befunde 0 an allen vier Teilen.
**Keine bestehende Testgrenze wurde in dieser Runde geändert.**

### Verbleibende Grenzen nach Runde 3
1. Alle Grenzen aus (f) gelten weiter (Toleranzprüfung statt exakt, nur gerade Rampen, Speicherschätzung,
   6-µm-Rand).
2. K1 ist nur geschützt, wenn die Inseln mitkommen (über `region_from_polys` oder `islands=`), siehe g.1.
3. Ohne ANGLE: senkrechter Einstich ins Volle mit Warnung – das verlangt die Spezifikation so; das Aufweiten
   danach läuft die ersten Umläufe über dem Soll-Eingriff (g.5).
4. Rechenzeit (M1) ist weiterhin offen; datenabhängige Speicherfelder in `_link_tree` (N4) sind seit (h)
   begrenzt. Das ist kein Prozess-RSS-Hardlimit für sämtliche Bibliotheken.
5. Die Rundungsüberschreitung der Mikrohelix-Halbkreise ist seit (h) behoben.
6. Die Prüfer-Skripte liefen in einer Kopie gegen `projekt/`; ihre Vergleichszahlen für den alten Stand sind
   die der Prüfung. Kein LinuxCNC-, Maschinen- oder Zielrechnerlauf.

---

## (h) Runde 4 (Codex)

Umgesetzt im echten Arbeitsklon auf `fable-review`, ohne Push. Der zunächst auf R4-1/R4-2 begrenzte Auftrag
wurde danach ausdrücklich um R4-5, R4-3 und R4-4 erweitert. Keine bestehenden Testgrenzen gelockert.

| Befund | Ursache → Änderung | Commit / Regression |
|---|---|---|
| **R4-1: senkrechter Einstieg bei 273/Q595=0** | Nach gescheiterter Helixsuche fehlte die Rampenalternative. Jetzt vorhandene Sehnensuche und gemeinsame Pendelausgabe `_ramp_in`; beide Richtungen und Anschluss an den Ring bestehen `prims_within`. Ohne brauchbaren ANGLE bzw. in nachweislich kleiner Werkzeugmittenfläche bleibt senkrechter Einstieg mit Warnung. Größere Fläche ohne nachgewiesenen Einstieg: `CycleError`. | `7d47463`: 36 Nutvarianten (10,4/11/12 mm, Q369=0,2/1/4, Q351=±1, 0°/17°), zusätzlich Warn- und Abbruchfälle. G-Code auf Materialeinstich, Winkel/Vorschub, Kontur, Endtiefe und Restboden geprüft. |
| **R4-2: fehlende Durchgangswarnung bei Q595=0** | Verlorene erreichbare Bodenfläche wurde nur im adaptiven Zweig erkannt. `adaptive.skipped_passage` ist jetzt gemeinsame geometrische Prüfung; Ringstrategie gibt dieselbe Warnung aus. Der 6-µm-Rand bleibt erhalten. | `7d47463`: g=10,004/10,012/10,020 für 272 und beide 273-Strategien; neben Warnungen wird die Abdeckung eines tatsächlich erreichbaren Bodenpunkts im Durchgang am ausgegebenen G-Code geprüft. |
| **R4-5: gerundete Helixbögen >180°** | Nominaler Halbkreis ist nach XY/IJ-Rundung nicht immer ein Halbkreis. `_helix_in` prüft die ausgegebenen Werte nach Drehung/Spiegelung/Skalierung; zu große oder gerundet geschlossene Bögen werden rekursiv geteilt. Z folgt dem Teilungswinkel, Endpunkt/Tangente bleiben gleich. | `a156362`: zwölf Varianten für Radius 0,02/0,128/4,75, Drehsinn und Spiegelung bei versetztem/gedrehtem Kreis. Reguläre frühere Helix-Tests einschließlich bytegleicher Ausgabe bleiben grün. |
| **R4-3: fehlende Eingriffswarnung beim Schlichten** | 273 nutzte die gemessene Engstellenstatistik nicht für Warnungen. Q595=1 nutzt nun dieselbe Meldung wie 272. Q595=0 erhält einen ausdrücklich vorsorglichen Strategiehinweis auf möglichen Vollschnitt; dort wird keine laufende Eingriffsmessung oder automatische Vorschubabsenkung behauptet. Planungsstrategie unverändert. | `6161a94`, Testkorrektur `a510752`: beide positiven Durchgangsbeispiele und Kreistasche ohne Engstelle als Negativkontrolle. Die zunächst verwendete Rechtecktasche war als Negativkontrolle ungeeignet, weil sie an den Ecken tatsächlich erhöhten Eingriff hat. |
| **R4-4: datenabhängige Speicherfelder in `_link_tree`** | Nachbarschaftsauswahl wuchs mit sämtlichen Stützpunkten × Nachbarzellen. Jetzt Blöcke bis 256 Punkte, tatsächliche Punktzahlen und Besitzerkarte vor Allokation budgetiert, außerdem temporäre Arrays und wachsende Abhängigkeitsmengen. Kein `vstack` aller Punkte; gleiche Sicht auf die vorherigen Ebenen. Fehler wird als verständlicher `CycleError` weitergegeben. | `b7a799c`: Tests für Abbruch vor Resampling, begrenzte Abfragefelder bei unveränderten Abhängigkeiten und Nachprüfung trotz absichtlich unterschätzter Voraus-Schätzung. |

### Ergebnisse der Abnahme am endgültigen Codestand

- **`pytest tests/test_cycles.py`: 298 bestanden, 10 übersprungen, 52,09 s.** Vor dieser Runde 230/10;
  68 neue Testfälle. Die zehn ausgelassenen Interpreter-Vergleichstests werden nicht als bestanden gewertet.
  Protokoll: `review-4/audit/fix_final_pytest.log`.
- Nachweis gegen den jeweiligen Vorherstand: R4-1/R4-2 zunächst **38 fehlgeschlagen, 7 bestanden** in der
  neuen 45er-Matrix; R4-5 **6 fehlgeschlagen, 6 bestanden**; R4-3 zwei positive Gegenbeispiele fehlgeschlagen;
  R4-4 alle drei neuen Tests fehlgeschlagen. Logs `fix_baseline_tests.log`, `fix_r45_before.log`,
  `fix_r43_before.log`, `fix_r44_before.log` unter `review-4/audit/`.
- **`erzeuge.py`: alle vier Teile** sowohl 272 als auch 272+273 mit Verletzung 0,000, Restfläche Boden 0 und
  keinen Befunden. **Alle zwölf erzeugten G-Code-Dateien bytegleich mit `gcode/`**, deshalb keine künstlichen
  G-Code-Änderungen committet. Belege: `fix_erzeuge_final.log`, `fix_generated_comparison.txt`.
- Eigene Review-Skripte gegen das echte `projekt/`: `extra_cases.py` und `final_checks.py` erneut ausgeführt.
  Alle zwölf Zusatzfälle ohne senkrechten Materialeinstich; Q595=0 warnt jetzt bei den übersprungenen
  Durchgängen. Die Flächen **118,64/113,92 mm² bleiben dort weiterhin stehen**; der Fix meldet das, statt eine
  nicht vorhandene Räumung zu behaupten. Bei g=10,020 Restfläche 0. Die 28 Eingabegrenzwerte aus
  `final_checks.py` bleiben korrekt. Quellenkopien und Ergebnisse: `review-4/audit/fix_validation/`.
- Zusätzliche Regression: 58 Review-Eingaben, 57 berechnet, der einzige Abbruch bleibt seed400012
  (Werkzeug zu groß). Keine neue Offset-Referenzverletzung oder G0-Materialkollision in diesen Proben;
  kein Bogen >180° in deren Auswertung. 24 echte Übersetzervarianten ohne Fehler.
- **Eigener echter LinuxCNC-Interpreterlauf in der freigegebenen VM:** 117 Dateien, alle `rc=0`, keine
  Fehlerzeilen, keine Mehrfachumdrehungen. Enthalten: zwölf Beispielprogramme, 24 Übersetzervarianten,
  57 direkte Review-Programme, zwölf Zusatzfälle, zwölf transformierte Helixfälle. Standalone `rs274` mit
  vorhandener Simulationskonfiguration; Zugriff auf das Paket nur lesend, VM-Ausgaben unter `/tmp/`.
  Protokoll: `review-4/audit/fix_vm_rs274.log`. Kein Bewegungsplaner- oder Maschinenlauf. Der separate Lauf
  ersetzt nicht die wegen des fehlenden Hilfsmoduls weiterhin nicht verfügbaren pytest-Interpretervergleiche.

### Speicher: gemessener RSS und Schätzung getrennt

Frische macOS-Prozesse, `resource.getrusage`, jeweils Python/numpy/pyclipper bereits geladen. Die
Budget-Schätzung ist für verwaltete Planungsdaten; Prozess-RSS enthält zusätzlich Interpreter,
Bibliotheken und Allokatorreserven. MiB = 2²⁰ Byte.

| Fall | Prozessspitze RSS | RSS vor Fall | Zuwachs | Budget-Spitzenschätzung | Zeit |
|---|---:|---:|---:|---:|---:|
| `_link_tree`, 4 × 1000 lange Hin-/Herstrecken, 400.004 Stützpunkte | 47,16 MiB | 30,17 MiB | 16,98 MiB | 18,74 MiB | 1,09 s |
| Frühere Problemgeometrie seed400007, ohne ANGLE | 48,69 MiB | 30,22 MiB | 18,47 MiB | 17,25 MiB | 0,71 s |

Beim zweiten Fall liegt auch der RSS-Zuwachs leicht über der verwalteten Schätzung. Daraus wird ausdrücklich
keine exakte RSS-Garantie abgeleitet. Die vormals unbeschränkten Felder werden jetzt vorab geprüft und
blockweise begrenzt; für nicht erfasste Bibliotheks-/Allokatoranteile bleibt die Reserve zum 500-MB-Ziel.
Ein harter Prozessdeckel und der Zielrechner-Nachweis sind damit nicht erledigt. Rohdaten und reproduzierbares
Skript: `review-4/audit/fix_memory_probe.py`, `fix_memory_stress.json`, `fix_memory_cycle.json`.

### Verbleibende Grenzen

Warnungen ändern weder den geometrisch unvermeidbaren Vollschnitt noch die durch den Sicherheitsrand
verlorenen Durchgänge. Ohne brauchbaren ANGLE bzw. bei nachweislich zu kleinem Raum gibt es weiterhin
gewarnten senkrechten Einstieg. Die Eingriffswarnung der Ringstrategie ist bewusst konservativ und keine
Messung. Eine erfolglose Einstiegssuche kann jetzt auch bei Q595=0 abbrechen. BLK-FORM-Annahmen,
Spiegelung/Gleichlauf, Z-Skalierung und Maschinenabnahme bleiben Entwicklerentscheidungen.
Weitergehende Vorschläge sind ausschließlich in `review-4/audit/CODEX_SUGGESTIONS.md` dokumentiert.
