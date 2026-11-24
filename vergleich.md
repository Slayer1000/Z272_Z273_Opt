# Vergleich LCNC-Cyclo gegen Fusion 360

Werkzeug D10, seitliche Zustellung 272: 2 mm (Soll-Umschlingung acos(1 − k/R) = 53°).
Zeit: Vorschub mit programmiertem F, Eilgang 10000 mm/min, ohne Beschleunigung (viele kurze Sätze sind real langsamer).
Umschlingung: Winkel des Werkzeugumfangs im Material, je 0,25 mm Bahn, nur waagerechte Bahn auf Tiefe. „> Soll“ = Anteil des Schnittwegs mit mehr als Soll + 15°.

| Teil | Programm | Arbeitsgang | Zeit | Vorschubweg | Eilweg | G0 | G1 | G2/G3 | Rückzüge | Luftschnitt | Umschl. Ø | 95 % | max | > Soll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | Cyclo | 272 KT RAEUMEN | 3:20 | 4770 | 310 | 8 | 839 | 1046 | 2 | 1355 | 50° | 155° | 175° | 7.2 % |
| T1 | Cyclo | 273 KT BODEN SCHLICHTEN | 2:56 | 2227 | 332 | 7 | 262 | 358 | 2 | 619 | – | – | – | – |
| T1 | Fusion | Adaptives 2D-Schruppen1 | 3:31 | 5005 | 328 | 14 | 4424 | 198 | 4 | 1357 | 48° | 150° | 180° | 6.6 % |
| T1 | Fusion | 2D-Versatz-Schruppen2 | 2:50 | 1609 | 106 | 4 | 42 | 114 | 1 | 243 | – | – | – | – |
| T2 | Cyclo | 272 KT RAEUMEN | 4:29 | 6504 | 1239 | 44 | 890 | 1334 | 14 | 2765 | 41° | 55° | 65° | 0.0 % |
| T2 | Cyclo | 273 KT BODEN SCHLICHTEN | 3:49 | 2984 | 678 | 17 | 341 | 461 | 7 | 1185 | – | – | – | – |
| T2 | Fusion | Adaptives 2D-Schruppen1 | 4:28 | 6448 | 1318 | 50 | 5286 | 263 | 16 | 2643 | 40° | 50° | 55° | 0.0 % |
| T2 | Fusion | 2D-Versatz-Schruppen2 | 2:33 | 1703 | 264 | 6 | 63 | 66 | 3 | 246 | – | – | – | – |
| T3 | Cyclo | 272 KT RAEUMEN | 7:14 | 10333 | 3287 | 129 | 662 | 798 | 42 | 1993 | 39° | 50° | 60° | 0.0 % |
| T3 | Cyclo | 273 KT BODEN SCHLICHTEN | 3:11 | 2462 | 842 | 23 | 157 | 176 | 10 | 377 | – | – | – | – |
| T3 | Fusion | Adaptives 2D-Schruppen1 | 6:27 | 9212 | 2425 | 92 | 5026 | 332 | 30 | 1237 | 39° | 50° | 55° | 0.0 % |
| T3 | Fusion | 2D-Versatz-Schruppen2 | 3:46 | 2368 | 1078 | 24 | 362 | 106 | 11 | 281 | – | – | – | – |
| T4 | Cyclo | 272 KT RAEUMEN | 6:07 | 8711 | 2992 | 117 | 540 | 604 | 38 | 1495 | 38° | 45° | 60° | 0.0 % |
| T4 | Cyclo | 273 KT BODEN SCHLICHTEN | 2:46 | 2120 | 928 | 21 | 155 | 142 | 9 | 294 | – | – | – | – |
| T4 | Cyclo | 272 KT RAEUMEN | 2:56 | 4149 | 577 | 26 | 961 | 1539 | 8 | 1690 | 47° | 155° | 175° | 8.4 % |
| T4 | Cyclo | 273 KT BODEN SCHLICHTEN | 2:42 | 2028 | 404 | 13 | 308 | 549 | 5 | 782 | – | – | – | – |
| T4 | Fusion | Adaptives 2D-Schruppen1 | 10:51 | 15496 | 2605 | 93 | 14979 | 863 | 30 | 3828 | 40° | 50° | 175° | 1.9 % |
| T4 | Fusion | 2D-Versatz-Schruppen2 | 5:27 | 3151 | 1217 | 25 | 384 | 151 | 12 | 492 | – | – | – | – |

## Ergebnis am Teil (ganzes Programm)

| Teil | Programm | Verletzung | Restfläche Boden | Eilgang im Material |
|---|---|---|---|---|
| T1_TASCHE_GESCHLOSSEN | cyclo | 0.000 mm | 0 mm² | 0 |
| T1_TASCHE_GESCHLOSSEN | fusion | 0.000 mm | 0 mm² | 0 |
| T2_TASCHE_SEITLICH_OFFEN | cyclo | 0.000 mm | 0 mm² | 0 |
| T2_TASCHE_SEITLICH_OFFEN | fusion | 0.000 mm | 0 mm² | 0 |
| T3_AUSSENKONTUR | cyclo | 0.000 mm | 0 mm² | 0 |
| T3_AUSSENKONTUR | fusion | 0.000 mm | 0 mm² | 0 |
| T4_INNEN_UND_AUSSEN | cyclo | 0.000 mm | 0 mm² | 0 |
| T4_INNEN_UND_AUSSEN | fusion | 0.000 mm | 0 mm² | 0 |
