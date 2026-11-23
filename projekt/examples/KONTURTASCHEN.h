0 BEGIN PGM KONTURTASCHEN MM
1 BLK FORM 0.1 Z X+0 Y+0 Z-20
2 BLK FORM 0.2 X+230 Y+100 Z+0
3 * - Rechtecktasche als Konturtaschen-Figur: Schruppen, Schlichten Tiefe/Seite
4 TOOL CALL 2 Z S8000 F1500
5 L Z+50 R0 FMAX M3
6 CYCL DEF 1271 KT RECHTECK ~
  Q650=+0 ;Figurart ~
  Q218=+70 ;Länge ~
  Q219=+50 ;Breite ~
  Q660=+0 ;Eckenform ~
  Q220=+8 ;Radius/Fase ~
  Q367=+0 ;Lage ~
  Q224=+0 ;Drehung ~
  Q203=+0 ;Oberfläche ~
  Q201=-8 ;Tiefe ~
  Q368=+0.3 ;Aufmaß seitlich ~
  Q369=+0.2 ;Aufmaß Boden ~
  Q260=+50 ;Sichere Höhe ~
  Q578=+0.2 ;Faktor Innenecken
7 CYCL DEF 272 KT RAEUMEN ~
  Q202=+4 ;Zustellung ~
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
8 L X+50 Y+50 R0 FMAX M99
9 CYCL DEF 273 KT BODEN SCHLICHTEN ~
  Q370=+1 ;Überlappung ~
  Q385=+800 ;Vorschub Schlichten ~
  Q568=+0.3 ;Faktor Eintauchen ~
  Q253=+750 ;Vorschub Positionieren ~
  Q200=+2 ;Sicherheitsabstand ~
  Q438=-1 ;Räumwerkzeug ~
  Q595=+1 ;Schlichtart ~
  Q577=+0.2 ;Faktor Anfahrradius
10 L X+50 Y+50 R0 FMAX M99
11 CYCL DEF 274 KT SEITE SCHLICHTEN ~
  Q338=+0 ;Zustellung Schlichten ~
  Q385=+800 ;Vorschub Schlichten ~
  Q253=+750 ;Vorschub Positionieren ~
  Q200=+2 ;Sicherheitsabstand ~
  Q14=+0 ;Aufmaß seitlich ~
  Q438=-1 ;Räumwerkzeug ~
  Q351=+1 ;Fräsrichtung
12 L X+50 Y+50 R0 FMAX M99
13 * - Insel als Kreis in einer rechteckigen Begrenzung (Planfraesen um die Insel)
14 CYCL DEF 1272 KT KREIS ~
  Q650=+1 ;Figurart ~
  Q223=+36 ;Durchmesser ~
  Q367=+0 ;Lage ~
  Q203=+0 ;Oberfläche ~
  Q201=-5 ;Tiefe ~
  Q368=+0 ;Aufmaß seitlich ~
  Q369=+0 ;Aufmaß Boden ~
  Q260=+50 ;Sichere Höhe ~
  Q578=+0.2 ;Faktor Innenecken
15 CYCL DEF 1281 KT BEGRENZUNG RECHTECK ~
  Q651=+80 ;Länge ~
  Q652=+80 ;Breite ~
  Q654=+0 ;Mittenbezug ~
  Q655=+0 ;Versatz X ~
  Q656=+0 ;Versatz Y
16 CYCL DEF 272 KT RAEUMEN ~
  Q202=+5 ;Zustellung ~
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
17 L X+140 Y+50 R0 FMAX M99
18 * - Freie Kontur aus LBL 1 mit 271 und 14
19 CYCL DEF 14.0 KONTUR
20 CYCL DEF 14.1 KONTURLABEL 1
21 CYCL DEF 271 KT DATEN ~
  Q203=+0 ;Oberfläche ~
  Q201=-6 ;Tiefe ~
  Q368=+0 ;Aufmaß seitlich ~
  Q369=+0 ;Aufmaß Boden ~
  Q260=+50 ;Sichere Höhe ~
  Q578=+0.2 ;Faktor Innenecken ~
  Q569=+0 ;Erste Figur
22 CYCL DEF 272 KT RAEUMEN ~
  Q202=+3 ;Zustellung ~
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
23 CYCL CALL
24 CYCL DEF 274 KT SEITE SCHLICHTEN ~
  Q338=+0 ;Zustellung Schlichten ~
  Q385=+800 ;Vorschub Schlichten ~
  Q253=+750 ;Vorschub Positionieren ~
  Q200=+2 ;Sicherheitsabstand ~
  Q14=+0 ;Aufmaß seitlich ~
  Q438=-1 ;Räumwerkzeug ~
  Q351=+1 ;Fräsrichtung
25 CYCL CALL
26 * - Kanten anfasen mit dem Zentrierer
27 TOOL CALL 4 Z S6000 F600
28 L Z+50 R0 FMAX M3
29 CYCL DEF 277 KT FASE ~
  Q353=-2 ;Spitzentiefe ~
  Q359=+0.5 ;Fasenbreite ~
  Q207=+600 ;Vorschub Fräsen ~
  Q253=+750 ;Vorschub Positionieren ~
  Q200=+2 ;Sicherheitsabstand ~
  Q438=-1 ;Räumwerkzeug ~
  Q351=+1 ;Fräsrichtung ~
  Q354=+0 ;Fasenwinkel
30 CYCL CALL
31 L Z+100 R0 FMAX M30
32 LBL 1
33 L X+190 Y+20 RL
34 L X+220
35 L Y+80
36 RND R10
37 L X+190
38 L Y+20
39 LBL 0
40 END PGM KONTURTASCHEN MM
