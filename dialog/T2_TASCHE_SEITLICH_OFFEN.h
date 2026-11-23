0 BEGIN PGM T2_TASCHE_SEITLICH_OFFEN MM
1 BLK FORM 0.1 Z X+0 Y+0 Z-30
2 BLK FORM 0.2 X+150 Y+100 Z+0
3 * - Tasche nach rechts (X+150) offen, Tiefe 10; Kontur läuft 12 mm über die Rohteilkante hinaus
4 TOOL CALL 2 Z S8000 F1500
5 L Z+50 R0 FMAX M3
6 * - Tasche
7 CYCL DEF 14.0 KONTUR
8 CYCL DEF 14.1 KONTURLABEL 1
9 CYCL DEF 271 KT DATEN ~
  Q203=+0 ;Oberfläche ~
  Q201=-10 ;Tiefe ~
  Q368=+0.3 ;Aufmaß seitlich ~
  Q369=+0.2 ;Aufmaß Boden ~
  Q260=+50 ;Sichere Höhe ~
  Q578=+0.2 ;Faktor Innenecken ~
  Q569=+0 ;Erste Figur
10 CYCL DEF 272 KT RAEUMEN ~
  Q202=+10 ;Zustellung ~
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
16 L X+32.1896 Y+29.118 RL
17 L X+84.3887 Y+18.1287
18 CC X+85.6247 Y+24
19 C X+85.6247 Y+18 DR+
20 L X+162 Y+18
21 L X+162 Y+78
22 L X+121.2488 Y+78
23 CC X+121.2488 Y+70
24 C X+118.8106 Y+77.6194 DR+
25 L X+95 Y+70
26 CC X+63.075 Y+55.7188
27 C X+40 Y+82 DR+
28 L X+20.2314 Y+57.7385
29 CC X+24.8828 Y+53.9485
30 C X+19.3119 Y+51.7201 DR+
31 L X+26.4099 Y+33.9752
32 CC X+33.8377 Y+36.9464
33 C X+32.1896 Y+29.118 DR+
34 LBL 0
35 END PGM T2_TASCHE_SEITLICH_OFFEN MM
