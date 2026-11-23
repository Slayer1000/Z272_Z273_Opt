0 BEGIN PGM ZYKLEN_TASCHEN MM
1 BLK FORM 0.1 Z X+0 Y+0 Z-30
2 BLK FORM 0.2 X+200 Y+150 Z+0
3 * - Planfräsen 233
4 TOOL CALL 3 Z S3000 F1200
5 L Z+100 R0 FMAX M3
6 CYCL DEF 233 PLANEN MIT WAENDEN ~
  Q215=+0 ;Umfang ~
  Q389=+1 ;Strategie ~
  Q350=+1 ;Fräsrichtung ~
  Q218=+200 ;Länge ~
  Q219=+150 ;Breite ~
  Q227=+1 ;Start Z ~
  Q386=+0 ;Ende Z ~
  Q369=+0.2 ;Aufmaß Boden ~
  Q202=+1 ;Zustellung ~
  Q370=+1.2 ;Max. Überlappung ~
  Q207=+1500 ;Vorschub Fräsen ~
  Q385=+800 ;Vorschub Schlichten ~
  Q253=+750 ;Vorschub Positionieren ~
  Q357=+2 ;Seitenabstand ~
  Q200=+2 ;Sicherheitsabstand ~
  Q204=+50 ;2. Sicherheitsabstand ~
  Q347=+0 ;Begrenzung 1 ~
  Q348=+0 ;Begrenzung 2 ~
  Q349=+0 ;Begrenzung 3 ~
  Q220=+0 ;Eckenradius ~
  Q368=+0 ;Aufmaß seitlich ~
  Q338=+0 ;Zustellung Schlichten ~
  Q367=+0 ;Flächenlage
7 L X+0 Y+0 FMAX M99
8 * - Rechtecktasche 251 (gedreht) und Kreistasche 252
9 TOOL CALL 2 Z S4000 F800
10 CYCL DEF 251 RECHTECKTASCHE ~
  Q215=+0 ;Umfang ~
  Q218=+60 ;Länge ~
  Q219=+35 ;Breite ~
  Q220=+8 ;Eckenradius ~
  Q368=+0.2 ;Aufmaß seitlich ~
  Q224=+15 ;Drehung ~
  Q367=+0 ;Lage ~
  Q207=+800 ;Vorschub Fräsen ~
  Q351=+1 ;Fräsrichtung ~
  Q201=-10 ;Tiefe ~
  Q202=+4 ;Zustellung ~
  Q369=+0.1 ;Aufmaß Boden ~
  Q206=+150 ;Vorschub Tiefe ~
  Q338=+5 ;Zustellung Schlichten ~
  Q200=+2 ;Sicherheitsabstand ~
  Q203=+0 ;Oberfläche ~
  Q204=+50 ;2. Sicherheitsabstand ~
  Q370=+1 ;Überlappung ~
  Q366=+1 ;Eintauchen ~
  Q385=+500 ;Vorschub Schlichten ~
  Q439=+0 ;Vorschubbezug
11 L X+50 Y+40 FMAX M3 M99
12 CYCL DEF 252 KREISTASCHE ~
  Q215=+0 ;Umfang ~
  Q223=+40 ;Durchmesser ~
  Q368=+0.2 ;Aufmaß seitlich ~
  Q207=+800 ;Vorschub Fräsen ~
  Q351=+1 ;Fräsrichtung ~
  Q201=-8 ;Tiefe ~
  Q202=+4 ;Zustellung ~
  Q369=+0 ;Aufmaß Boden ~
  Q206=+150 ;Vorschub Tiefe ~
  Q338=+0 ;Zustellung Schlichten ~
  Q200=+2 ;Sicherheitsabstand ~
  Q203=+0 ;Oberfläche ~
  Q204=+50 ;2. Sicherheitsabstand ~
  Q370=+1 ;Überlappung ~
  Q366=+0 ;Eintauchen ~
  Q385=+500 ;Vorschub Schlichten ~
  Q439=+0 ;Vorschubbezug
13 L X+50 Y+105 FMAX M99
14 * - Nut 253, Rechteckzapfen 256, Kreiszapfen 257
15 CYCL DEF 253 NUT ~
  Q215=+0 ;Umfang ~
  Q218=+50 ;Nutlänge ~
  Q219=+12 ;Nutbreite ~
  Q368=+0.2 ;Aufmaß seitlich ~
  Q374=+90 ;Drehung ~
  Q367=+0 ;Nutlage ~
  Q207=+800 ;Vorschub Fräsen ~
  Q351=+1 ;Fräsrichtung ~
  Q201=-6 ;Tiefe ~
  Q202=+3 ;Zustellung ~
  Q369=+0 ;Aufmaß Boden ~
  Q206=+150 ;Vorschub Tiefe ~
  Q338=+0 ;Zustellung Schlichten ~
  Q200=+2 ;Sicherheitsabstand ~
  Q203=+0 ;Oberfläche ~
  Q204=+50 ;2. Sicherheitsabstand ~
  Q366=+0 ;Eintauchen ~
  Q385=+500 ;Vorschub Schlichten ~
  Q439=+0 ;Vorschubbezug
16 L X+100 Y+75 FMAX M99
17 CYCL DEF 256 RECHTECKZAPFEN ~
  Q218=+40 ;Länge ~
  Q424=+50 ;Rohteil Länge ~
  Q219=+30 ;Breite ~
  Q425=+40 ;Rohteil Breite ~
  Q220=+5 ;Radius/Fase ~
  Q368=+0 ;Aufmaß seitlich ~
  Q224=+0 ;Drehung ~
  Q367=+0 ;Lage ~
  Q207=+800 ;Vorschub Fräsen ~
  Q351=+1 ;Fräsrichtung ~
  Q201=-8 ;Tiefe ~
  Q202=+4 ;Zustellung ~
  Q206=+150 ;Vorschub Tiefe ~
  Q200=+2 ;Sicherheitsabstand ~
  Q203=+0 ;Oberfläche ~
  Q204=+50 ;2. Sicherheitsabstand ~
  Q370=+1 ;Überlappung ~
  Q437=+0 ;Anfahrpunkt ~
  Q215=+0 ;Umfang ~
  Q369=+0 ;Aufmaß Boden ~
  Q338=+0 ;Zustellung Schlichten ~
  Q385=+500 ;Vorschub Schlichten
18 L X+150 Y+40 FMAX M99
19 CYCL DEF 257 KREISZAPFEN ~
  Q223=+30 ;Fertig-Ø ~
  Q222=+40 ;Rohteil-Ø ~
  Q368=+0 ;Aufmaß seitlich ~
  Q207=+800 ;Vorschub Fräsen ~
  Q351=+1 ;Fräsrichtung ~
  Q201=-8 ;Tiefe ~
  Q202=+4 ;Zustellung ~
  Q206=+150 ;Vorschub Tiefe ~
  Q200=+2 ;Sicherheitsabstand ~
  Q203=+0 ;Oberfläche ~
  Q204=+50 ;2. Sicherheitsabstand ~
  Q370=+1 ;Überlappung ~
  Q376=+0 ;Startwinkel ~
  Q215=+0 ;Umfang ~
  Q369=+0 ;Aufmaß Boden ~
  Q338=+0 ;Zustellung Schlichten ~
  Q385=+500 ;Vorschub Schlichten
20 L X+150 Y+110 FMAX M99
21 L Z+100 FMAX M30
22 END PGM ZYKLEN_TASCHEN MM
