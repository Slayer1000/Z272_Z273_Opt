0 BEGIN PGM T1_TASCHE_GESCHLOSSEN MM
1 BLK FORM 0.1 Z X+0 Y+0 Z-30
2 BLK FORM 0.2 X+150 Y+100 Z+0
3 * - Unregelmäßige geschlossene Tasche, Tiefe 12, eine Innenecke mit Einschnürung
4 TOOL CALL 2 Z S8000 F1500
5 L Z+50 R0 FMAX M3
6 * - Tasche
7 CYCL DEF 14.0 KONTUR
8 CYCL DEF 14.1 KONTURLABEL 1
9 CYCL DEF 271 KT DATEN ~
  Q203=+0 ;Oberfläche ~
  Q201=-12 ;Tiefe ~
  Q368=+0.3 ;Aufmaß seitlich ~
  Q369=+0.2 ;Aufmaß Boden ~
  Q260=+50 ;Sichere Höhe ~
  Q578=+0.2 ;Faktor Innenecken ~
  Q569=+0 ;Erste Figur
10 CYCL DEF 272 KT RAEUMEN ~
  Q202=+12 ;Zustellung ~
  Q370=+0.4 ;Überlappung ~
  Q207=+1500 ;Vorschub Fräsen ~
  Q568=+0.6 ;Faktor Eintauchen ~
  Q253=+750 ;Vorschub Positionieren ~
  Q200=+2 ;Sicherheitsabstand ~
  Q438=-1 ;Räumwerkzeug ~
  Q577=+0.2 ;Faktor Anfahrradius ~
  Q351=+1 ;Fräsrichtung ~
  Q576=+0 ;Drehzahl ~
  Q579=+1 ;Faktor Eintauchdrehzahl ~
  Q575=+0 ;Zustellfolge
11 CYCL CALL
12 CYCL DEF 273 KT BODEN SCHLICHTEN ~
  Q370=+1 ;Überlappung ~
  Q385=+800 ;Vorschub Schlichten ~
  Q568=+0.3 ;Faktor Eintauchen ~
  Q253=+750 ;Vorschub Positionieren ~
  Q200=+2 ;Sicherheitsabstand ~
  Q438=-1 ;Räumwerkzeug ~
  Q595=+1 ;Schlichtart ~
  Q577=+0.2 ;Faktor Anfahrradius
13 CYCL CALL
14 L Z+100 R0 FMAX M30
15 LBL 1
16 L X+28.7886 Y+17.6607 RL
17 L X+89.1738 Y+12.2531
18 CC X+90.0658 Y+22.2132
19 C X+94.5379 Y+13.269 DR+
20 L X+128 Y+30
21 CC X+110.7735 Y+53.6487
22 C X+118 Y+82 DR+
23 L X+80.1981 Y+86.9307
24 CC X+78.646 Y+75.0315
25 C X+68.0804 Y+80.7207 DR+
26 L X+60.5615 Y+66.757
27 CC X+56.1591 Y+69.1275
28 C X+53.4553 Y+64.9216 DR-
29 L X+35.6221 Y+76.3858
30 CC X+32.3776 Y+71.3387
31 C X+27.011 Y+74.022 DR+
32 L X+15.5446 Y+51.0891
33 CC X+22.7 Y+47.5114
34 C X+15.189 Y+44.7574 DR+
35 L X+23.6905 Y+21.5713
36 CC X+29.3238 Y+23.6368
37 C X+28.7886 Y+17.6607 DR+
38 LBL 0
39 END PGM T1_TASCHE_GESCHLOSSEN MM
