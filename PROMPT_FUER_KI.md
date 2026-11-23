# Prompt: Bahnberechnung 272 KT RAEUMEN und 273 KT BODEN SCHLICHTEN optimieren

> Diese Datei komplett als Prompt übergeben, zusammen mit der ZIP (`quelle/`, `step/`, `dialog/`, `gcode/`,
> `erzeuge.py`). Die Fusion-Programme der vier Teile kommen als Vergleich dazu.

---

## Deine Aufgabe

Du überarbeitest die Werkzeugbahnberechnung von zwei Fräszyklen eines CNC-Projekts in Python:

- **272 KT RAEUMEN**: adaptives Räumen mit begrenzter Eingriffsbreite, Ziel „wie Fusion 360 Adaptive Clearing“
- **273 KT BODEN SCHLICHTEN**

Die neuen Bahnen sollen mindestens so gut sein wie die von Fusion 360 für dieselben Teile. Gemessen wird an Eingriffskonstanz, Bearbeitungszeit, Zahl der Rückzüge, Glätte (Bögen statt Polygonzüge) und Programmlänge. Dabei darf nichts an der Sicherheit und an der Schnittstelle verloren gehen.

Liefere **geänderte, vollständige Python-Dateien** `adaptive.py` und `pocket.py`, bei Bedarf auch neue Hilfsmodule, und dazu eine kurze Beschreibung der Änderungen. Die Dateien müssen ohne Nacharbeit wieder ins Projekt passen (siehe „Schnittstelle“).

## Hintergrund

LCNC-Cyclo ist eine Bedienoberfläche für LinuxCNC. Sie bildet die werkstattorientierte Dialogprogrammierung nach. Ein Dialogprogramm mit Zyklen (`CYCL DEF 272 …`) wird beim Übersetzen in LinuxCNC-G-Code umgerechnet. Die Bahn jedes Zyklus berechnet Python **einmal beim Übersetzen**, auf dem Steuerungsrechner (Beckhoff C6920, schwache CPU, Debian 13, Python 3.13). Heraus kommt ein G-Code-Unterprogramm `o<cyc272_n> sub … endsub`.

Maschine: 4-Achs-Fräse (XYZ + B-Schwenkkopf). Bearbeitet wird nur in der XY-Ebene (G17), Werkzeugachse Z.

## Wie der Zyklus angesteuert wird

```
CYCL DEF 14.0 KONTUR
CYCL DEF 14.1 KONTURLABEL 1 /2        ; LBL 1 = Tasche bzw. Begrenzung, LBL 2 = Insel …
CYCL DEF 271 KT DATEN  Q203 Oberfläche, Q201 Tiefe (neg.), Q368 Aufmaß seitlich, Q369 Aufmaß Boden,
                       Q260 sichere Höhe, Q578 Faktor Innenecken, Q569 erste Figur
                       (0 = Tasche, 1 = Begrenzung = offen nach außen, 2 = Begrenzung mit offener Seite)
CYCL DEF 272 KT RAEUMEN Q202 Zustellung, Q370 Überlappung (k = Q370·R), Q207 Vorschub, Q568 Faktor Eintauchen,
                       Q253 Vorschub Positionieren, Q200 Sicherheitsabstand, Q438 Räumwerkzeug,
                       Q577 Faktor Anfahrradius, Q351 Fräsrichtung (+1 Gleichlauf, −1 Gegenlauf),
                       Q576 Drehzahl, Q579 Faktor Eintauchdrehzahl, Q575 Zustellfolge
CYCL DEF 273 KT BODEN SCHLICHTEN Q370 Überlappung (k = Q370·R), Q385 Vorschub Schlichten, Q568 Faktor Eintauchen,
                       Q253, Q200, Q438, Q595 Schlichtart, Q577 Faktor Anfahrradius
CYCL CALL
```

Taschen und Inseln erkennt das Programm am Umlaufsinn: gegen den Uhrzeiger mit RL = Tasche, gegen den Uhrzeiger mit RR = Insel. Beispiele liegen in `dialog/*.h`.

Q370 ist ein Faktor auf den **Radius**. Q370 = 0,4 bei D10 heißt seitliche Zustellung 2,0 mm.

## Derzeitige Rechenweise

Code: `quelle/adaptive.py` und `quelle/pocket.py`. Geometrie mit **pyclipper** (Ganzzahlen, `SCALE = 1000` → 1 µm) und **numpy**.

### Fläche

Der Übersetzer baut `reg` als Clipper-Pfade:

- Tasche: Taschen − Inseln
- offene Begrenzung (Q569 = 1): (Begrenzung ∪ Taschen) − Inseln, mit `open_bnd = True`. Die Begrenzung ist das Rohteil, außerhalb ist Luft.

`offset(paths, d)` mit d > 0 verkleinert die Fläche, mit d < 0 vergrößert sie (JT_ROUND).

### 272, geschlossene Tasche (`adaptive.plan` → `plan_component`)

1. **Zulässige Werkzeugmitte:** `allowed = offset(reg, R + Q368)`, in zusammenhängende Teilflächen zerlegt.
2. **Start je Teilfläche:**
   - Größter einbeschriebener Kreis, gesucht per Rasterverfeinerung (`max_inscribed`).
   - Darin eine Helix mit Radius `rh = min(0,95·R, r_in)`. Die Steigung kommt aus ANGLE in der Werkzeugtabelle und bleibt konstant. Start 1 mm über der Oberfläche, am Grund ein ebener Vollkreis.
   - Danach eine archimedische Spirale mit Zuwachs k je Umlauf bis `r_in`, dort ein Vollkreis.
   - Ohne ANGLE wird senkrecht eingetaucht, mit Warnung.
3. **Wachsende Fronten:**
   - Front₀ = Kreis um die Spirale ∩ Fläche.
   - Front_{n+1} = (Front_n um k vergrößert) ∩ Fläche.
   - Gefräst wird der Rand der neuen Front, abgetastet in 0,25-mm-Schritten. Nur die Stücke, vor denen noch Material liegt (Punkt nicht im geräumten Kern `offset(cleared, R − 0,02)`), je um bis zu min(R, 2) in geräumtes Gebiet verlängert.
   - Dadurch liegt jeder Bahnpunkt höchstens k vor dem Geräumten, auch in Ecken, Engstellen und um Inseln.
4. **Stirnseitiger Eingriff:** Die Umschlingung je Punkt (`engagement`) wird gegen eine Grenze `acos(1 − k/R) + 40°` (höchstens 160°) geprüft. Liegt der Anfang eines Stücks darüber (Wand vor der Front), wird erst der Rest der Front gefräst und der Anfang danach neu bewertet.
5. **Geräumte Fläche** `cleared` = Vereinigung aller Bahnen, je um R aufgeweitet (`buffer_open`).
6. **Reihenfolge:** Front für Front, innerhalb der Front jeweils das nächstgelegene Stück. Geschlossene Ringe beginnen am Punkt, der dem Werkzeug am nächsten ist. Danach Douglas-Peucker mit 0,005 mm.

### 272, offene Begrenzung (`plan_open`)

- Material = Begrenzung − Inseln.
- Zulässig = Außenkontur um R + Aufmaß + 2k vergrößert, minus Inseln um R + Aufmaß.
- Geräumt zu Beginn = alles außerhalb des Rohteils.
- Die Fronten wachsen von außen nach innen. Das Werkzeug taucht neben dem Material ein, ohne Helix.

### Verbindungen und Anfahren (`pocket.adaptive_272`)

- Radius der Bögen `ra = max(0,2·R, 0,5)`. Q577 wird dabei **nicht** ausgewertet.
- **Zwischen zwei Stücken:** Dubins-Weg (Bogen–Gerade–Bogen, Radius ra bzw. ra/2) durch geräumte Fläche. Er hebt auf dem ersten Stück um 0,2 mm an und senkt auf dem letzten ab (`_emit_link`).
- **Geht das nicht:** Gerade bzw. Weg über einen Zwischenpunkt Richtung Flächenmitte.
- **Geht auch das nicht:** Rückzug auf Q200, Eilgang, Eintauchen mit Einfahr-Viertelkreis oder schräger Rampe. Liegt der Startpunkt im Material, wird daneben in Geräumtem eingetaucht und per Dubins-Weg seitlich angefahren. Senkrecht nur als letzte Möglichkeit.
- **Ende jeder Teilfläche:** tangential ausfahren und dabei abheben.

### Zustellungen

- `_levels(Oberfläche, Grund, Q202)`: Ebenen in gleichen Schritten von oben, die letzte auf Grund (Q201 + Q369).
- **Der 2D-Plan wird einmal berechnet** und auf jeder Ebene wiederholt. Ab der 2. Ebene beginnt die Helix 0,5 mm über der vorigen Ebene.

### 273 (`pocket.floor_273`)

- Konturparallele Ringe aus `loops_for(reg, R + Q368, k)`, von innen nach außen, Abstand k = Q370·R.
- Senkrechtes Eintauchen auf Grund + Aufmaß + 0,2, dann mit Q385·Q568 auf Grund.
- Ringwechsel mit einer Geraden, wenn sie in der Fläche liegt, sonst Rückzug.
- Bei offener Begrenzung darf die Werkzeugmitte bis R − 0,2 über die Rohteilkante hinaus.
- Q595 und Q577 werden nicht ausgewertet.

### Gemessen an den vier Teilen (D10, k = 2 mm)

| Teil | 272 Zeilen | G1 | G2/G3 | Rückzüge auf Q200 | Rechenzeit (Xeon 2,1 GHz) |
|---|---|---|---|---|---|
| T1 geschlossen | 3442 | 3227 | 109 | 26 | 12 s |
| T2 seitlich offen | 3808 | 3529 | 134 | 39 | 19 s |
| T3 Außenkontur, 2 Ebenen | 1556 | 1172 | 142 | 71 | 9 s |
| T4 innen + außen | 4610 | 3920 | 277 | 121 | 26 s |

Alle Teile laufen ohne Eilgang im Material, ohne Konturverletzung und ohne Restmaterial am Boden (`pruefung.txt`).

## Bekannte Schwächen = Optimierungsziele (nach Priorität)

1. **Rechenzeit:** 10–26 s auf einem Xeon, auf dem Beckhoff deutlich mehr. Ziel: ≤ 3 s je Zyklus auf dem Xeon.
   - `cleared` wird bei jedem Stück neu vereinigt und für `core` neu versetzt.
   - `engagement` und `_inside_np` rechnen Punkt-in-Polygon mit allen Kanten (O(n·m)).
   - Ideen: Rasterkarte/Abstandsfeld für das Geräumte, inkrementell, oder ein räumlicher Index.
2. **Bögen statt Polygonzüge:** Fronten und Spirale kommen als tausende G1 heraus. Bögen fitten (G2/G3, Toleranz ≤ 0,005 mm, tangentenstetig), wo die Bahn kreisförmig ist. Ziel: Zeilenzahl deutlich unter Fusion-Niveau.
3. **Offene Seiten erkennen (T2):**
   - Die offene Tasche wird derzeit wie eine geschlossene behandelt: Helix in der Mitte, Fronten von innen.
   - Besser: von der offenen Seite außerhalb des Materials beginnen, wie Fusion es mit Rohteilkonturen macht.
   - Q569 = 2 („Begrenzung mit offener Seite“) ist im Katalog vorgesehen, wird im Übersetzer aber noch nicht ausgewertet. Es reicht, wenn der Planer erkennt, welche Teile von `reg` außerhalb des Rohteils liegen; das Rohteil kann dafür als zusätzlicher Parameter kommen (siehe Schnittstelle).
4. **Weniger Rückzüge und kürzere Leerwege:** Verbindungen möglichst auf Tiefe oder nur leicht angehoben durch geräumte Fläche. Reihenfolge der Stücke so, dass wenig gesprungen wird.
5. **Gleichmäßigere Umschlingung:**
   - Die Fronten halten k nur als Abstand ein. In Innenecken und beim Durchbrechen in schmale Bereiche steigt die Umschlingung.
   - Ziel: Umschlingung über die ganze Bahn ≤ `acos(1 − k/R)` + kleine Reserve.
   - Wo das nicht geht: trochoidale Schleifen, oder den Vorschub per F-Wort absenken.
6. **Mehrere Zustellungen:** Q575 (Zustellfolge) und eine sinnvolle Aufteilung (gleiche Schritte) auswerten. Optional: Plan je Ebene nur einmal, Helix nur auf der ersten Ebene, danach Rampe in geräumter Fläche.
7. **Parameter, die heute ignoriert werden:**
   - Q577 (An-/Abfahrradius = Q577·R) bei 272 und 273
   - Q595 bei 273: 0 = konturparallel, 1 = mäander/gleichmäßig; die genaue Bedeutung darfst du festlegen und dokumentieren
   - Q578 Innenecken
8. **273:**
   - Einfahren über Bogen bzw. Rampe statt senkrecht
   - Ringwechsel tangential (S-Bogen) statt Gerade
   - Reihenfolge optimieren

Q438 (Restmaterial eines Vorwerkzeugs) ist **nicht** Teil dieser Aufgabe.

## Schnittstelle (muss so bleiben)

Der Übersetzer ruft ausschließlich auf:

```python
# pocket.py
def ocm_cycle(num: int, p: P, data: P, reg, tool: Tool, e: Emit, open_bnd: bool) -> None
#   num 272 -> rough_272(e, reg, tool, p, data, open_bnd)
#   num 273 -> floor_273(e, reg, tool, p, data, open_bnd)
#   274/277 (side_274, chamfer_277) bitte unverändert lassen
```

**Eingaben:**

- `reg`: Liste von Clipper-Pfaden (Liste von (int, int), Maßstab `SCALE = 1000`), Nonzero-Regel, Außenkonturen gegen den Uhrzeiger, Löcher im Uhrzeiger. Absolutkoordinaten im Werkstücksystem.
- `p`: Zyklusparameter 272/273. `p.n(q, default)` gibt float zurück. `p.f(q)` gibt das Vorschub-**Wort** als Text zurück (kann `#<_cyclo_fauto>` sein); niemals in float umwandeln. Zum Skalieren `_num_feed(f, faktor)` verwenden, das kommt mit Text zurecht.
- `data`: Werte aus 271 bzw. der Figur. Gebraucht werden: `203` Oberfläche, `201` Tiefe (< 0), `368`/`369` Aufmaß, `260` sichere Höhe.
- `tool`: `Tool` mit `tool.r()` (Radius, wirft CycleError, wenn er fehlt), `tool.angle` (Eintauchwinkel in Grad, 0 = keine Helix), `tool.number`.
- `open_bnd`: True, wenn die erste Kontur eine Begrenzung (Rohteil) ist.
- Optional darfst du einen zusätzlichen Parameter `stock=None` einführen: ein Rohteil-Rechteck (xmin, ymin, xmax, ymax) für das Erkennen offener Seiten. Er muss einen Standardwert haben; ich verdrahte ihn dann im Übersetzer.

**Ausgabe** nur über das `Emit`-Objekt (`cyclegen.Emit`, `rel = False`). Keinen G-Code-Text selbst zusammenbauen, außer mit `e.raw()` für S-Wörter:

| Aufruf | Wirkung |
|---|---|
| `e.rapid_z(z)` | G0 Z |
| `e.rapid_xy(x, y)` | G0 X Y |
| `e.feed_z(z, f)` | G1 Z F |
| `e.feed_xy(x, y, f=None, z=None)` | G1 X Y [Z] [F] (gleiche Position wird unterdrückt) |
| `e.arc(x, y, cx, cy, ccw, f=None, z=None)` | G2/G3 vom aktuellen Punkt nach (x, y) um (cx, cy), mit z als Helix; Spiegeln und Drehen macht Emit selbst |
| `e.cur` | aktuelle XY-Position oder None (nach Rückzug unbekannt setzen: `e.cur = None`) |
| `e.raw("S…")` | Rohzeile |
| `e.warn.append(text)` | Warnung an den Bediener (Text mit `_t(...)` für die Übersetzung) |

**Regeln für den Ausgabe-G-Code:**

- Nur G0/G1/G2/G3 in G17.
- G2/G3 höchstens Halbkreise (eindeutig). Ein G2/G3 mit gleichem Start- und Endpunkt ist in LinuxCNC ein **Vollkreis**. Bögen, deren Endpunkte nach dem Runden auf 4 Nachkommastellen gleich wären, als G1 ausgeben. Das war ein echter Fehler: Er schnitt bei T4 die Taschenwand an. `_emit_link` fängt das jetzt ab.
- Vorschub-Wörter: Fräsen Q207, Eintauchen/Rampe Q207·Q568, Positionieren Q253 (wenn < 99999), bei 273 Q385 bzw. Q385·Q568.
- Höhen: Start und Ende auf `clear = max(Q260, Oberfläche + Q200)`. Rückzug zwischen Stücken auf `Oberfläche + Q200`.
- Fehler als `CycleError(_t("…"))` mit verständlichem deutschem Text (z. B. „Werkzeug zu groß für die Kontur“).

**Technische Grenzen:**

- Nur Python-Standardbibliothek, numpy und pyclipper. Kein shapely, kein scipy, keine C-Erweiterungen, kein Netz.
- Deterministisch: gleiche Eingabe gibt gleichen G-Code.
- Speicher ≤ 500 MB.
- Code-Stil wie im Projekt: deutsche Kommentare und Docstrings, Benutzertexte in `_t("…")`.

## Sicherheitsanforderungen (dürfen nie verletzt werden)

1. Die Werkzeugmitte bleibt auf Bearbeitungstiefe immer in `offset(reg, R + Q368)`. Bei offener Begrenzung darf sie über die Rohteilkante hinaus, aber nie in Inseln + R + Q368.
2. Kein Eilgang (G0) im Material, auch nicht in XY auf Tiefe.
3. Kein Eintauchen senkrecht ins volle Material, wenn eine Helix oder Rampe möglich ist.
4. Kein stirnseitiger Vollschnitt (Umschlingung 180°) außer beim allerersten Eintauchen.
5. Am Ende ist die Fläche bis auf Aufmaß und Ecken mit Radius < R vollständig geräumt.

## Abnahme

Deine Fassung gilt als fertig, wenn:

1. **Tests:** `pytest tests/test_cycles.py` grün ist. Wichtig sind vor allem `test_272_*`, `test_273_*`, `test_ocm_*` und `test_emit_link_tiny_arc_is_no_full_circle`. Tests nur ändern, wenn sie ein bewusst geändertes Verhalten prüfen, und das begründen.
2. **Vergleichsteile:** `python3 examples/trochoidal_vergleich/erzeuge.py` für alle vier Teile meldet:
   - Verletzung 0,000
   - Restfläche Boden 0 mm²
   - keine Befunde (Eilgang im Material)
3. **Messwerte:** Rechenzeit, Zeilenzahl, Zahl der Rückzüge und Vorschubweg je Teil, vorher und nachher, als Tabelle. Die Vorher-Werte stehen oben.
4. **Beschreibung:** Eine kurze Erklärung der neuen Rechenweise im Stil dieses Abschnitts. Sie kommt als Modul-Docstring an den Anfang von `adaptive.py`.

## Mitgeliefert (ZIP)

- **`projekt/`: lauffähiger Auszug des Projekts.** Darin Übersetzer, alle Zyklen (`cyclo/dialog/`), Bahnverfolgung und Abtragssimulation (`cyclo/sim/`), Zyklus-Unterprogramme (`ngc/`), `tests/test_cycles.py` und `examples/trochoidal_vergleich/erzeuge.py`. **Hier entwickelst du.** Im Ordner `projekt/`:
  - `pip install numpy pyclipper pytest cadquery`
  - `python3 -m pytest -q tests/test_cycles.py` (derzeit 58 grün, 10 übersprungen)
  - `python3 examples/trochoidal_vergleich/erzeuge.py` erzeugt STEP, G-Code und `pruefung.txt` neu (cadquery nur für STEP/STL)
- **`quelle/`:** dieselben Kerndateien noch einmal zum schnellen Lesen: `adaptive.py`, `pocket.py`, `slcycles.py` (offset/inside/loops_for), `cyclegen.py` (Emit, `_helix_in`, `_levels`) und `test_cycles.py`.
- **`step/*.step`:** die vier Fertigteile.
- **`stl/*.stl`:** dieselben Teile als STL, für die Prüfung.
- **`dialog/*.h`:** die Dialogprogramme.
- **`gcode/*.ngc`:** der heutige G-Code, jeweils `_272`, `_273` und beides.
- **`pruefung.txt`:** heutiges Prüfergebnis.
- **`bahnen_272.png`:** Draufsicht der heutigen 272-Bahnen (blau Vorschub, grün angehoben, rot Eilgang). Gut zu sehen: viele Eilwege bei T3/T4 außen; T2 wird wie eine geschlossene Tasche von innen geräumt.
- **`README.md`:** Werkzeug und Zustellungen für den Vergleich mit Fusion.
- **Fusion-Programme** der vier Teile, wenn vorhanden, mit gleichen Einstellungen (D10, Optimale Last 2,0 mm, Aufmaß 0,3/0,2).

Zurück ins Projekt kommen nur die geänderten Dateien aus `projekt/cyclo/dialog/` (und ggf. Tests). Alles andere im Auszug bitte nicht ändern.
