# Vergleich LCNC-Cyclo gegen Fusion 360

Werkzeug D10, seitliche Zustellung 272: 2 mm (Soll-Umschlingung acos(1 − k/R) = 53°).
Zeit: Vorschub mit programmiertem F, Eilgang 10000 mm/min, ohne Beschleunigung (viele kurze Sätze sind real langsamer).
Umschlingung: Winkel des Werkzeugumfangs im Material, je 0,25 mm Bahn, nur waagerechte Bahn auf Tiefe. „> Soll“ = Anteil des Schnittwegs mit mehr als Soll + 15°.

| Teil | Programm | Arbeitsgang | Zeit | Vorschubweg | Eilweg | G0 | G1 | G2/G3 | Rückzüge | Luftschnitt | Umschl. Ø | 95 % | max | > Soll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | Cyclo | 272 KT RAEUMEN | 3:19 | 4750 | 310 | 8 | 866 | 1029 | 2 | 1337 | 50° | 155° | 175° | 7.2 % |
| T1 | Cyclo | 273 KT BODEN SCHLICHTEN | 2:56 | 2225 | 332 | 7 | 253 | 352 | 2 | 617 | – | – | – | – |
| T1 | Fusion | Adaptives 2D-Schruppen1 | 3:31 | 5005 | 328 | 14 | 4424 | 198 | 4 | 1357 | 48° | 150° | 180° | 6.6 % |
| T1 | Fusion | 2D-Versatz-Schruppen2 | 2:50 | 1609 | 106 | 4 | 42 | 114 | 1 | 243 | – | – | – | – |
| T2 | Cyclo | 272 KT RAEUMEN | 4:28 | 6462 | 1309 | 46 | 894 | 1327 | 15 | 2735 | 41° | 55° | 70° | 0.0 % |
| T2 | Cyclo | 273 KT BODEN SCHLICHTEN | 3:48 | 2976 | 677 | 17 | 302 | 445 | 7 | 1197 | – | – | – | – |
| T2 | Fusion | Adaptives 2D-Schruppen1 | 4:28 | 6448 | 1318 | 50 | 5286 | 263 | 16 | 2643 | 40° | 50° | 55° | 0.0 % |
| T2 | Fusion | 2D-Versatz-Schruppen2 | 2:33 | 1703 | 264 | 6 | 63 | 66 | 3 | 246 | – | – | – | – |
| T3 | Cyclo | 272 KT RAEUMEN | 7:14 | 10339 | 3289 | 129 | 612 | 752 | 42 | 1998 | 39° | 50° | 60° | 0.0 % |
| T3 | Cyclo | 273 KT BODEN SCHLICHTEN | 3:11 | 2465 | 842 | 23 | 143 | 167 | 10 | 381 | – | – | – | – |
| T3 | Fusion | Adaptives 2D-Schruppen1 | 6:27 | 9212 | 2425 | 92 | 5026 | 332 | 30 | 1237 | 39° | 50° | 55° | 0.0 % |
| T3 | Fusion | 2D-Versatz-Schruppen2 | 3:46 | 2368 | 1078 | 24 | 362 | 106 | 11 | 281 | – | – | – | – |
| T4 | Cyclo | 272 KT RAEUMEN | 6:06 | 8680 | 2989 | 117 | 510 | 564 | 38 | 1476 | 38° | 45° | 60° | 0.0 % |
| T4 | Cyclo | 273 KT BODEN SCHLICHTEN | 2:46 | 2121 | 927 | 21 | 134 | 132 | 9 | 293 | – | – | – | – |
| T4 | Cyclo | 272 KT RAEUMEN | 2:56 | 4135 | 577 | 26 | 912 | 1517 | 8 | 1681 | 47° | 155° | 175° | 8.4 % |
| T4 | Cyclo | 273 KT BODEN SCHLICHTEN | 2:41 | 2020 | 404 | 13 | 333 | 551 | 5 | 771 | – | – | – | – |
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
