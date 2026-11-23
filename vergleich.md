# Vergleich LCNC-Cyclo gegen Fusion 360

Werkzeug D10, seitliche Zustellung 272: 2 mm (Soll-Umschlingung acos(1 − k/R) = 53°).
Zeit: Vorschub mit programmiertem F, Eilgang 10000 mm/min, ohne Beschleunigung (viele kurze Sätze sind real langsamer).
Umschlingung: Winkel des Werkzeugumfangs im Material, je 0,25 mm Bahn, nur waagerechte Bahn auf Tiefe. „> Soll“ = Anteil des Schnittwegs mit mehr als Soll + 15°.

| Teil | Programm | Arbeitsgang | Zeit | Vorschubweg | Eilweg | G0 | G1 | G2/G3 | Rückzüge | Luftschnitt | Umschl. Ø | 95 % | max | > Soll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | Cyclo | 272 KT RAEUMEN | 3:39 | 4992 | 994 | 77 | 3225 | 109 | 25 | 1566 | 51° | 155° | 175° | 8.2 % |
| T1 | Cyclo | 273 KT BODEN SCHLICHTEN | 1:35 | 1241 | 243 | 5 | 664 | 0 | 1 | 10 | – | – | – | – |
| T1 | Fusion | Adaptives 2D-Schruppen1 | 3:31 | 5005 | 328 | 14 | 4424 | 198 | 4 | 1357 | 48° | 150° | 180° | 6.6 % |
| T1 | Fusion | 2D-Versatz-Schruppen2 | 2:50 | 1609 | 106 | 4 | 42 | 114 | 1 | 243 | – | – | – | – |
| T2 | Cyclo | 272 KT RAEUMEN | 4:28 | 6143 | 1008 | 116 | 3527 | 134 | 38 | 2449 | 50° | 150° | 175° | 6.9 % |
| T2 | Cyclo | 273 KT BODEN SCHLICHTEN | 1:51 | 1461 | 248 | 5 | 543 | 0 | 1 | 117 | – | – | – | – |
| T2 | Fusion | Adaptives 2D-Schruppen1 | 4:28 | 6448 | 1318 | 50 | 5286 | 263 | 16 | 2643 | 40° | 50° | 55° | 0.0 % |
| T2 | Fusion | 2D-Versatz-Schruppen2 | 2:33 | 1703 | 264 | 6 | 63 | 66 | 3 | 246 | – | – | – | – |
| T3 | Cyclo | 272 KT RAEUMEN | 6:57 | 9418 | 5894 | 213 | 1170 | 142 | 70 | 1381 | 40° | 50° | 100° | 0.1 % |
| T3 | Cyclo | 273 KT BODEN SCHLICHTEN | 2:58 | 2304 | 731 | 20 | 968 | 0 | 6 | 795 | – | – | – | – |
| T3 | Fusion | Adaptives 2D-Schruppen1 | 6:27 | 9212 | 2425 | 92 | 5026 | 332 | 30 | 1237 | 39° | 50° | 55° | 0.0 % |
| T3 | Fusion | 2D-Versatz-Schruppen2 | 3:46 | 2368 | 1078 | 24 | 362 | 106 | 11 | 281 | – | – | – | – |
| T4 | Cyclo | 272 KT RAEUMEN | 5:51 | 7982 | 5038 | 159 | 1022 | 110 | 52 | 1081 | 38° | 45° | 75° | 0.1 % |
| T4 | Cyclo | 273 KT BODEN SCHLICHTEN | 2:52 | 2207 | 855 | 20 | 697 | 0 | 6 | 846 | – | – | – | – |
| T4 | Cyclo | 272 KT RAEUMEN | 3:08 | 3781 | 2719 | 203 | 2896 | 167 | 67 | 1407 | 55° | 160° | 175° | 13.3 % |
| T4 | Cyclo | 273 KT BODEN SCHLICHTEN | 1:04 | 826 | 284 | 8 | 546 | 0 | 2 | 44 | – | – | – | – |
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
