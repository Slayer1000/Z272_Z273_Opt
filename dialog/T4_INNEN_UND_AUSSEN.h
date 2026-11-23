0 BEGIN PGM T4_INNEN_UND_AUSSEN MM
1 BLK FORM 0.1 Z X+0 Y+0 Z-30
2 BLK FORM 0.2 X+160 Y+120 Z+0
3 * - Bauteil mit Außenkontur (Tiefe 16, 2 Zustellungen) und Innentasche mit Insel (Tiefe 10)
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
14 * - Tasche
15 CYCL DEF 14.0 KONTUR
16 CYCL DEF 14.1 KONTURLABEL 3 /4
17 CYCL DEF 271 KT DATEN ~
  Q203=+0 ;Oberfläche ~
  Q201=-10 ;Tiefe ~
  Q368=+0.3 ;Aufmaß seitlich ~
  Q369=+0.2 ;Aufmaß Boden ~
  Q260=+50 ;Sichere Höhe ~
  Q578=+0.2 ;Faktor Innenecken ~
  Q569=+0 ;Erste Figur
18 CYCL DEF 272 KT RAEUMEN ~
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
19 CYCL CALL
20 CYCL DEF 273 KT BODEN SCHLICHTEN ~
  Q370=+1 ;Überlappung ~
  Q385=+800 ;Vorschub Schlichten ~
  Q568=+0.3 ;Faktor Eintauchen ~
  Q253=+750 ;Vorschub Positionieren ~
  Q200=+2 ;Sicherheitsabstand ~
  Q438=-1 ;Räumwerkzeug ~
  Q595=+1 ;Schlichtart ~
  Q577=+0.2 ;Faktor Anfahrradius
21 CYCL CALL
22 L Z+100 R0 FMAX M30
23 LBL 1
24 L X+0 Y+0 RL
25 L X+160 Y+0
26 L X+160 Y+120
27 L X+0 Y+120
28 L X+0 Y+0
29 LBL 0
30 LBL 2
31 L X+21.2442 Y+14.4536 RR
32 L X+92.9139 Y+8.1825
33 CC X+93.9599 Y+20.1369
34 C X+97.0246 Y+8.5348 DR+
35 L X+148 Y+22
36 CC X+76.8577 Y+57.0285
37 C X+140 Y+105 DR+
38 L X+85.5512 Y+111.3524
39 CC X+83.813 Y+96.4534
40 C X+75.3784 Y+108.8573 DR+
41 L X+57.5604 Y+96.7411
42 CC X+54.1866 Y+101.7026
43 C X+52.0974 Y+96.0781 DR-
44 L X+25.2368 Y+106.0549
45 CC X+23.4958 Y+101.3678
46 C X+18.6451 Y+102.5805 DR+
47 L X+8.4908 Y+61.963
48 CC X+18.1922 Y+59.5377
49 C X+8.311 Y+58.0006 DR+
50 L X+14.0366 Y+21.1935
51 CC X+21.9415 Y+22.4232
52 C X+21.2442 Y+14.4536 DR+
53 LBL 0
54 LBL 3
55 L X+39.924 Y+29.8485 RL
56 L X+96.8413 Y+28.0972
57 CC X+97.0874 Y+36.0934
58 C X+102.3724 Y+30.0877 DR+
59 L X+122.8345 Y+48.0944
60 CC X+119.5314 Y+51.848
61 C X+124.4343 Y+52.8285 DR+
62 L X+119.3833 Y+78.0837
63 CC X+109.5775 Y+76.1225
64 C X+111.0205 Y+86.0178 DR+
65 L X+70 Y+92
66 CC X+73.8 Y+46.25
67 C X+30 Y+60 DR+
68 L X+34.1901 Y+34.8593
69 CC X+40.1085 Y+35.8457
70 C X+39.924 Y+29.8485 DR+
71 LBL 0
72 LBL 4
73 L X+71.9792 Y+49.5347 RR
74 L X+87.1974 Y+48.5202
75 CC X+87.4634 Y+52.5113
76 C X+90.8554 Y+54.6313 DR+
77 L X+83.2464 Y+66.8058
78 CC X+79.8544 Y+64.6858
79 C X+76.5494 Y+66.9392 DR+
80 L X+68.9404 Y+55.7792
81 CC X+72.2453 Y+53.5259
82 C X+71.9792 Y+49.5347 DR+
83 LBL 0
84 END PGM T4_INNEN_UND_AUSSEN MM
