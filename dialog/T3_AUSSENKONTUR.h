0 BEGIN PGM T3_AUSSENKONTUR MM
1 BLK FORM 0.1 Z X+0 Y+0 Z-30
2 BLK FORM 0.2 X+140 Y+110 Z+0
3 * - Unregelmäßige Außenkontur (Insel in Begrenzung = Rohteil), Tiefe 16 in 2 Zustellungen
4 TOOL CALL 2 Z S8000 F1500
5 L Z+50 R0 FMAX M3
6 * - Außenkontur (Begrenzung + Insel)
7 CYCL DEF 14.0 KONTUR
8 CYCL DEF 14.1 KONTURLABEL 1 /2
9 CYCL DEF 271 KT DATEN ~
  Q203=+0 ;Oberfläche ~
  Q201=-16 ;Tiefe ~
  Q368=+0.3 ;Aufmaß seitlich ~
  Q369=+0.2 ;Aufmaß Boden ~
  Q260=+50 ;Sichere Höhe ~
  Q578=+0.2 ;Faktor Innenecken ~
  Q569=+1 ;Erste Figur
10 CYCL DEF 272 KT RAEUMEN ~
  Q202=+8 ;Zustellung ~
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
16 L X+0 Y+0 RL
17 L X+140 Y+0
18 L X+140 Y+110
19 L X+0 Y+110
20 L X+0 Y+0
21 LBL 0
22 LBL 2
23 L X+20.8984 Y+19.5169 RR
24 L X+73.7976 Y+10.7004
25 CC X+76.2636 Y+25.4963
26 C X+81.9431 Y+11.6131 DR+
27 L X+122 Y+28
28 CC X+93.6667 Y+54.1111
29 C X+112 Y+88 DR+
30 L X+74.2405 Y+96.5817
31 CC X+72.0243 Y+86.8304
32 C X+64.0981 Y+92.9275 DR+
33 L X+50.5513 Y+75.3168
34 CC X+45.7956 Y+78.975
35 C X+44.006 Y+73.2481 DR-
36 L X+20.1024 Y+80.718
37 CC X+18.9093 Y+76.9001
38 C X+15.0156 Y+77.8163 DR+
39 L X+8.4057 Y+49.7242
40 CC X+14.2462 Y+48.3499
41 C X+8.5957 Y+46.3319 DR+
42 L X+17.0117 Y+22.7672
43 CC X+21.7204 Y+24.4489
44 C X+20.8984 Y+19.5169 DR+
45 LBL 0
46 END PGM T3_AUSSENKONTUR MM
