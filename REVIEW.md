# Review und Überarbeitung 272 KT RAEUMEN / 273 KT BODEN SCHLICHTEN

Bearbeitet mit Claude Fable 5.2 nach `PROMPT_FUER_KI.md`, Stand 2026-11-24.
Dieses Ergebnis ist für eine unabhängige Zweitprüfung gedacht. Alles, was unsicher oder nur geschätzt ist,
steht ausdrücklich in Abschnitt (d).

Geändert: `projekt/cyclo/dialog/adaptive.py` (neu geschrieben), `projekt/cyclo/dialog/pocket.py`
(272, 273, `ocm_cycle`), `projekt/cyclo/dialog/translator.py` (8 Zeilen, siehe b.6),
`projekt/tests/test_cycles.py` (1 Test angepasst, 2 neue), dazu neu erzeugt `gcode/*.ngc` (ohne Fusion),
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
- Ausgabe als Geraden und Kreisbögen (Bogenanpassung der Clipper-Polygone), Bögen höchstens Halbkreise,
  punktförmige Bögen als G1.

### 2. 272: offene Seiten über das Rohteil (`stock`)
`ocm_cycle(..., stock=None)` nimmt optional das Rohteil-Rechteck (xmin, ymin, xmax, ymax). Liegt ein Teil der
Tasche neben dem Rohteil, startet die Bearbeitung von dort ohne Helix. Die Werkzeugmitte bleibt dabei in
`offset(reg, R + Q368)` (Anforderung 1 unverändert).
**Bewusst vorsichtig:** Neben dem Rohteil (Luft nur laut BLK FORM, nicht selbst geräumt) wird nie im Eilgang
zugestellt, sondern mit Q253. Das kostet bei T2 etwa 15 s, schützt aber, falls das wirkliche Rohteil größer
ist als die BLK FORM.

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
es in den Cache-Schlüssel auf (8 Zeilen). Nur wenn Werkzeugachse Z und keine Verschiebung/Drehung/Spiegelung
aktiv ist. Das ist ein **Vorschlag**; ohne diese Zeilen verhält sich 272 bei T2 wie bisher (geschlossene Tasche).

---

## (c) Messwerte vorher / nachher

Werkzeug D10, 272 mit k = 2 mm (Soll 53°), 273 mit k = 5 mm. Zeit nach `vergleich.py` (Eilgang 10000 mm/min,
ohne Beschleunigung). „> Soll“ = Anteil des Schnittwegs über Soll + 15°.

### 272 KT RAEUMEN

| Teil | Stand | Zeit | Vorschubweg | Rückzüge | G1 | G2/G3 | Umschl. Ø / 95 % / max | > Soll | Rechenzeit (M5 Max) |
|---|---|---|---|---|---|---|---|---|---|
| T1 | vorher | 3:39 | 4992 | 25 | 3225 | 109 | 51° / 155° / 175° | 8,2 % | 2,78 s |
| T1 | **nachher** | 3:19 | 4750 | 2 | 866 | 1029 | 50° / 155° / 175° | 7,2 % | 0,48 s |
| T1 | Fusion | 3:31 | 5005 | 4 | 4424 | 198 | 48° / 150° / 180° | 6,6 % | – |
| T2 | vorher | 4:28 | 6143 | 38 | 3527 | 134 | 50° / 150° / 175° | 6,9 % | 5,00 s |
| T2 | **nachher** | 4:28 | 6462 | 15 | 894 | 1327 | 41° / 55° / 70° | 0,0 % | 0,50 s |
| T2 | Fusion | 4:28 | 6448 | 16 | 5286 | 263 | 40° / 50° / 55° | 0,0 % | – |
| T3 | vorher | 6:57 | 9418 | 70 | 1170 | 142 | 40° / 50° / 100° | 0,1 % | 2,86 s |
| T3 | **nachher** | 7:14 | 10339 | 42 | 612 | 752 | 39° / 50° / 60° | 0,0 % | 0,19 s |
| T3 | Fusion | 6:27 | 9212 | 30 | 5026 | 332 | 39° / 50° / 55° | 0,0 % | – |
| T4 außen | vorher | 5:51 | 7982 | 52 | 1022 | 110 | 38° / 45° / 75° | 0,1 % | 2,58 s |
| T4 außen | **nachher** | 6:06 | 8680 | 38 | 510 | 564 | 38° / 45° / 60° | 0,0 % | 0,14 s |
| T4 Tasche | vorher | 3:08 | 3781 | 67 | 2896 | 167 | 55° / 160° / 175° | 13,3 % | 4,95 s |
| T4 Tasche | **nachher** | 2:56 | 4135 | 8 | 912 | 1517 | 47° / 155° / 175° | 8,4 % | 0,89 s |
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
| T1 | 1:35, 1241 mm, 0 Bögen, 1 Rückz. | 2:56, 2225 mm, 352 Bögen, 2 Rückz. | 1:45, 1287 mm, 61 Bögen, 1 Rückz. | 2:50, 1609 mm, 114 Bögen, 1 Rückz. |
| T2 | 1:51, 1461 mm, 0, 1 | 3:48, 2976 mm, 445, 7 | 2:02, 1516 mm, 39, 1 | 2:33, 1703 mm, 66, 3 |
| T3 | 2:58, 2304 mm, 0, 6 | 3:11, 2465 mm, 167, 10 | 2:39, 1814 mm, 56, 4 | 3:46, 2368 mm, 106, 11 |
| T4 außen | 2:52, 2207 mm, 0, 6 | 2:46, 2121 mm, 132, 9 | 2:54, 1694 mm, 56, 8 | 5:27 (beide), 3151 mm, 151, 12 |
| T4 Tasche | 1:04, 826 mm, 0, 2 | 2:41, 2020 mm, 551, 5 | 1:23, 911 mm, 59, 2 | – |

Rechenzeit 273 nachher: Q595 = 1 0,07–0,36 s, Q595 = 0 unter 0,02 s. Für den alten Stand nicht getrennt gemessen.
Die Spalte Q595 = 0 stammt aus dem Hilfsskript (gleiche Simulation, im Dialogprogramm Q595 auf 0 gesetzt),
nicht aus `vergleich.md`.

### Abnahme

| Kriterium | Ergebnis |
|---|---|
| `pytest tests/test_cycles.py` | **60 passed, 10 skipped** (vorher 58 passed, 10 skipped; 1 Test angepasst, 2 neu) |
| `erzeuge.py`, alle vier Teile, 272 und 272+273 | Verletzung −0,000, Restfläche Boden 0 mm², keine Befundzeilen (`pruefung.txt`) |
| `vergleich.py` am ganzen Teil | Verletzung 0,000 mm, Restfläche 0 mm², Eilgang im Material 0 – alle vier Teile |
| Mit Q595 = 0 (Hilfsskript) | Verletzung 0, Rest 0, Befunde 0 – alle vier Teile |
| Speicher | größter Wert 340 MB für den Lauf über alle vier Teile samt Simulation |
| Programmlänge 272 (Zeilen) | T1 3442 → 1934, T2 3808 → 2298, T3 1556 → 1524, T4 4610 → 3699 |

### Ziele aus dem Prompt – erreicht oder nicht

| Ziel | Stand |
|---|---|
| 1 Umschlingung 95 % ≤ 60°, < 2 % über Soll + 15° (außer Eintauchen) | T2, T3, T4 außen: erreicht. T1, T4-Tasche: erreicht **ohne Helix** (0,13 % / 0,16 %); mit Helix wie bei Fusion nicht. |
| 2 Offene Seite (T2) | erreicht, braucht die Zeilen in `translator.py` |
| 3 Rückzüge ≤ Fusion | T1 2 ≤ 4, T2 15 ≤ 16: erreicht. **T3 42 > 30, T4 46 > 30: nicht erreicht.** |
| 4 Rechenzeit ≤ 3 s auf dem Xeon | nicht gemessen; hochgerechnet vermutlich erreicht außer T4-Tasche (siehe d.1) |
| 5 273 mit Bögen, Helix, tangentialem Ringwechsel | erreicht (beide Schlichtarten) |
| 6 Q575, gleiche Zustellschritte | umgesetzt; Bedeutung von Q575 = 1 / 2 ist meine Festlegung (d.4) |
| 7 Q577, Q595, Q578 | umgesetzt; Q578 ist meine Auslegung (d.4) |
| Bearbeitungszeit nicht schlechter als heute | 272: T1, T2, T4-Tasche gleich oder besser. **T3 +17 s (4 %), T4 außen +15 s (4 %) schlechter.** 273: mit Q595 = 1 **deutlich schlechter** (bis 2,5-fach), mit Q595 = 0 bei T3 besser, sonst 2–19 s schlechter (Helix). |

---

## (d) Offene Punkte und Unsicherheiten

1. **Rechenzeit auf dem Xeon ist nicht gemessen.** Aus dem Verhältnis alt (12 s laut Prompt bei T1) zu hier
   gemessen (2,78 s) ergibt sich Faktor etwa 4,3. Damit wären es rund 2,1 s (T1), 2,2 s (T2), 0,8 s (T3),
   0,6 s + **3,8 s (T4-Tasche, über dem Ziel von 3 s)**. Bitte auf der Zielmaschine messen. Die Zeit liegt
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
8. **Rastergenauigkeit.** Die Freigabe von Eilgang-Eintauchen und Verbindungen beruht auf einem
   0,2-mm-Raster mit Sicherheitszuschlag (Werkzeugfläche R + 0,3 muss leer sein). Die unabhängige Prüfung
   (`erzeuge.py`, `vergleich.py`, Raster 0,1 mm) meldet 0 Eilgänge im Material an den vier Teilen; ein
   Beweis für beliebige Konturen ist das nicht. Wandreste bis 0,06 mm (`TOL_WALL`) bleiben beim Schruppen stehen.
9. **Sicherheitsanforderung 1 ist nur indirekt geprüft** (Verletzung 0 in der Abtragssimulation und der
   vorhandene Inseltest). Einen Test, der jeden Bahnpunkt gegen `offset(reg, R + Q368)` prüft, gibt es nicht.
10. **Verbindungen an der fertigen Wand entlang** laufen 0,2 mm angehoben genau auf der Wandbahn. Seitlich
    berührt das Werkzeug dabei die fertige Wand (kein Abtrag laut Simulation). Ob das an der Maschine
    stört (Spuren), ist nicht beurteilt.
11. **Vorschubabsenkung an Engstellen** gibt Faktoren im F-Wort aus (z. B. halber Vorschub). Die Stufen
    (ab Soll + 30°) sind gewählt, nicht aus Schnittdaten hergeleitet.
12. **273 bei kleinerem Schlichtwerkzeug als Räumwerkzeug:** In Ecken, die das Räumwerkzeug nicht erreicht
    hat, steht volles Material. 273 fährt dort wie bisher auf Tiefe hinein. Unverändert, aber erwähnenswert.
13. **Testabdeckung:** Geprüft sind die vier Vergleichsteile und die Fälle in `test_cycles.py` (Rechteck,
    Kreis, Insel, Q370 = 0,3 … 1,5). Nicht geprüft: sehr schmale Nuten, viele Inseln, Gegenlauf (Q351 = −1)
    an den Vergleichsteilen, Werkzeuge ohne ANGLE an den Vergleichsteilen, gedrehte/verschobene Konturen
    mit `stock` (dort wird `stock` nicht übergeben).
14. **Nicht eingecheckt:** `erzeuge.py` schreibt `dialog/`, `gcode/`, `step/`, `stl/` unter
    `projekt/examples/trochoidal_vergleich/`. Nur die G-Code-Dateien sind nach `gcode/` kopiert.
