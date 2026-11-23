# Vergleich 272 KT RAEUMEN / 273 KT BODEN SCHLICHTEN gegen Fusion 360

Vier Testteile mit unregelmäßigen Konturen. Jedes Teil gibt es als STEP-Fertigteil, als Dialogprogramm und als
von LCNC-Cyclo berechneten G-Code. Dieselben Teile in Fusion programmieren und die Programme vergleichen.
`PROMPT_FUER_KI.md` ist die Vorlage für eine andere KI, die 272/273 überarbeiten soll.

| Teil | Rohteil (X × Y × Z) | Bearbeitung |
|---|---|---|
| T1_TASCHE_GESCHLOSSEN | 150 × 100 × 30 | geschlossene Tasche, Tiefe 12, Einschnürung an einer Innenecke |
| T2_TASCHE_SEITLICH_OFFEN | 150 × 100 × 30 | Tasche nach X+ offen, Tiefe 10 (Kontur läuft 12 mm über die Kante) |
| T3_AUSSENKONTUR | 140 × 110 × 30 | Außenkontur, Tiefe 16 in 2 Zustellungen à 8 |
| T4_INNEN_UND_AUSSEN | 160 × 120 × 30 | Außenkontur Tiefe 16 (2 × 8) + Innentasche mit Insel, Tiefe 10 |

## Inhalt

- `step/`: Fertigteile, eines je Teil
- `dialog/`: Dialogprogramme (272 + 273, Konturen als LBL)
- `gcode/<TEIL>_272.ngc`: nur Räumen
- `gcode/<TEIL>_273.ngc`: nur Boden schlichten
- `gcode/<TEIL>.ngc`: beides nacheinander
- `stl/`: Fertigteile als STL, für die Abtragsprüfung
- `pruefung.txt`: Abtragssimulation, Weglängen, Zeilenzahl
- `bahnen_272.png`: Draufsicht der 272-Bahnen (blau Vorschub, grün angehoben, rot Eilgang)
- `erzeuge.py`: erzeugt alles neu, aus einer einzigen Geometriebeschreibung. Aufruf im Ordner `cyclo/`: `python3 examples/trochoidal_vergleich/erzeuge.py`
- nur in der ZIP:
  - `quelle/`: der derzeitige Code von 272/273
  - `projekt/`: ein lauffähiger Auszug von Übersetzer, Zyklen und Simulation, für die KI zum Testen

## Nullpunkt

Der Nullpunkt liegt an der Rohteilecke links vorne oben: X0 Y0 = Xmin/Ymin des Rohteils, Z0 = Oberseite. Das Rohteil geht von Z0 bis Z-30.
In Fusion: WKS auf die Ecke links vorne oben legen. Rohteil = „Relative Quadergröße“ mit Versatz 0, denn das STEP hat die volle Rohteilgröße.

## Einstellungen, damit Fusion gleich rechnet

**Werkzeug (alle Teile):** Schaftfräser **D10** (R5), Schneidenlänge 25, Eintauchwinkel 3°. S 8000.

### 272 KT RAEUMEN → Fusion „2D adaptives Räumen“

| LCNC-Cyclo | Wert | Fusion |
|---|---|---|
| Q370 = 0,4 × R | **seitliche Zustellung 2,0 mm** (20 % von D) | Optimale Last 2,0 mm |
| Q351 = +1 | Gleichlauf | Gleichlauffräsen |
| Q368 / Q369 | Aufmaß 0,3 seitlich / 0,2 Boden | Radiales Aufmaß 0,3 / axiales Aufmaß 0,2 |
| Q202 | Zustellung je Teil, siehe unten | Mehrere Tiefen, max. Zustellung |
| Q207 | 1500 mm/min | Schnittvorschub 1500 |
| Q207 · Q568 | 900 mm/min | Rampen-/Eintauchvorschub 900 |
| ANGLE 3°, Helix Ø 9,5 (Werkzeugmitte, 0,95 · R) | Helix 3° | Rampe Helix, Winkel 3°, Rampendurchmesser 9,5 |
| Helix startet 1 mm über der Oberfläche | | Rampen-Freihöhe 1 mm |
| Verbindungen 0,2 mm angehoben | | Abhebehöhe 0,2 mm |
| Ein-/Ausfahrbögen 0,2 · R | 1,0 mm | Einfahr-/Ausfahrradius 1,0 mm |
| Q200 / Q260 | 2 mm / Z+50 | Rückzugshöhe 2 über Oberkante / Sicherheitshöhe 50 |

**Zustellung (Q202):**

| Teil | Zustellung |
|---|---|
| T1 | 12 (eine Ebene) |
| T2 | 10 (eine Ebene) |
| T3 | 8 (2 Ebenen) |
| T4 außen | 8 (2 Ebenen) |
| T4 Tasche | 10 (eine Ebene) |

### 273 KT BODEN SCHLICHTEN → Fusion „2D-Tasche“, nur Boden

| LCNC-Cyclo | Wert | Fusion |
|---|---|---|
| Q370 = 1,0 × R | **seitliche Zustellung 5,0 mm** (50 % von D) | Maximale Zustellung 5,0 |
| Q368 bleibt stehen | 0,3 seitlich, Boden auf Endmaß | Radiales Aufmaß 0,3, axiales 0 |
| Q385 | 800 mm/min | Schnittvorschub 800 |
| Q385 · Q568 | 240 mm/min | Eintauchvorschub 240, senkrecht |

Bei den Außenkonturen (T3, T4 außen) ist die Begrenzung das Rohteil. Bei 273 darf das Werkzeug dort über die Rohteilkante hinaus. In Fusion dafür „Rohteilkonturen“ einschalten.

## Prüfung der Bahnen (`pruefung.txt`)

Alle Programme haben die Abtragssimulation durchlaufen, Raster 0,1 mm. Ergebnis für alle Teile:

- kein Eilgang im Material
- keine Verletzung der Fertigkontur
- nach 272 + 273 kein Restmaterial am Boden

Bei diesen Teilen sind zwei Fehler im Code aufgefallen. Beide sind behoben und mit Tests abgesichert:

1. **272:** Ein fast punktförmiger Verbindungsbogen kam als G2/G3 mit gleichem Start- und Endpunkt heraus. LinuxCNC fährt das als Vollkreis. Bei T4 schnitt das auf Taschentiefe in die Wand der Innentasche.
2. **273 mit offener Begrenzung:** Das Werkzeug blieb um R innerhalb der Rohteilkante. Am Rand und im schmalen Steg zwischen Kante und Insel blieb dadurch Boden stehen.
