"""Eigener Zyklenkatalog von LCNC-Cyclo.

Enthält nur die Zyklen, die LCNC-Cyclo tatsächlich nach LinuxCNC-G-Code umsetzt. Kurznamen,
Fragen, Vorgabewerte, Eingabebereiche und Auswahltexte sind eigene Formulierungen.

Übernommen ist nur, was für das Lesen vorhandener Dialogprogramme zwingend gleich sein muss:
die Zyklusnummer, die Nummer jedes Q-Parameters und dessen Reihenfolge im ``CYCL DEF``.

Aufbau
------
``Q``       je Q-Nummer eine Grundbeschreibung (gilt in allen Zyklen)
``OVERRIDE`` abweichende Bedeutung eines Q-Parameters in einem bestimmten Zyklus
``CYCLES``   je Zyklus: Name, Gruppe und die Q-Nummern in Satzreihenfolge
"""

from __future__ import annotations

from ..i18n import _t

from dataclasses import dataclass, replace

BIG = 99999.9999


@dataclass(frozen=True)
class QDef:
    label: str          # Kurzname (steht als Kommentar hinter dem Wert im Programm)
    prompt: str         # Frage im Formular
    default: float = 0.0
    lo: float | None = None
    hi: float | None = None
    unit: str = "mm"    # mm | mm/min | s | ° | 1/min | "" (Zahl/Auswahl)
    group: str = "Geometrie"  # Geometrie | Standard | Erweitert | Sicherheit
    mode: str = ""      # inkremental | absolut | text | ""
    also: str = ""      # weitere zulässige Eingaben (FMAX, FAUTO, PREDEF ...)
    options: tuple = ()

    @property
    def range(self) -> str:
        if self.mode == "text":
            return _t("bis 255 Zeichen")
        if self.lo is None or self.hi is None:
            return ""
        def f(v):
            return f"{v:+g}" if v < 0 else f"{v:g}"
        r = f"{f(self.lo)}...{f(self.hi)}"
        return _t('{0} alternativ {1}').format(r, self.also) if self.also else r


G, S, E, SI = "Geometrie", "Standard", "Erweitert", "Sicherheit"
INC, ABS = "inkremental", "absolut"
_F = "FAUTO, FU, FZ"


def _len(label, prompt, d=0.0, lo=-BIG, hi=BIG, g=G, mode="", **kw):
    return QDef(label, prompt, d, lo, hi, "mm", g, mode, **kw)


def _pos(label, prompt, d=0.0, g=G, mode="", **kw):
    """Länge ≥ 0."""
    return _len(label, prompt, d, 0.0, BIG, g, mode, **kw)


def _feed(label, prompt, d=0.0, also=_F, g=S):
    return QDef(label, prompt, d, 0.0, BIG, "mm/min", g, "", also)


def _ang(label, prompt, d=0.0, lo=-360.0, hi=360.0, g=G, mode=""):
    return QDef(label, prompt, d, lo, hi, "°", g, mode)


def _num(label, prompt, d=0.0, lo=0.0, hi=BIG, g=E, unit=""):
    return QDef(label, prompt, d, lo, hi, unit, g)


def _sel(label, prompt, d, options, g=S, also=""):
    vals = [float(a) for a, _ in options]
    return QDef(label, prompt, d, min(vals), max(vals), "", g, "", also, tuple(options))


_SIDE = (("+1", _t("Gleichlauf")), ("-1", _t("Gegenlauf")))
_CORNER5 = (("0", _t("Werkzeug steht in der Mitte der Figur")), ("1", _t("Werkzeug steht an der Ecke links unten")),
            ("2", _t("Werkzeug steht an der Ecke rechts unten")), ("3", _t("Werkzeug steht an der Ecke rechts oben")),
            ("4", _t("Werkzeug steht an der Ecke links oben")))

# --------------------------------------------------------------------------- Q-Parameter
Q: dict[int, QDef] = {
    # SL-Konturdaten (Zyklus 20) und SL-Bearbeitung
    1: _len(_t("Frästiefe"), _t("Wie tief wird die Kontur gefräst (Vorzeichen = Richtung)?"), -10, mode=INC),
    2: _num(_t("Überlappung"), _t("Faktor für die seitliche Bahnüberlappung (× Werkzeugradius)?"), 1, 0.0001, 1.9999, g=S),
    3: _len(_t("Aufmaß seitlich"), _t("Wie viel Material bleibt an den Wänden für das Schlichten stehen?"), 0.2, g=S),
    4: _len(_t("Aufmaß Boden"), _t("Wie viel Material bleibt am Boden für das Schlichten stehen?"), 0.1, g=S, mode=INC),
    5: _len(_t("Oberfläche"), _t("Auf welcher Höhe liegt die Werkstückoberfläche?"), 0, g=SI, mode=ABS),
    6: _len(_t("Sicherheitsabstand"), _t("Abstand über der Oberfläche, ab dem mit Vorschub gefahren wird?"), 2, g=SI, mode=INC),
    7: _len(_t("Sichere Höhe"), _t("Auf welcher Höhe fährt das Werkzeug kollisionsfrei zwischen den Bereichen?"), 50, g=SI, mode=ABS),
    8: _pos(_t("Innenradius"), _t("Mit welchem Radius werden Innenecken der Werkzeugbahn verrundet?"), 0, g=E),
    9: _sel(_t("Drehsinn"), _t("In welche Richtung läuft die Bearbeitung um die Tasche?"), 1,
            (("+1", _t("Gegen den Uhrzeigersinn")), ("-1", _t("Im Uhrzeigersinn")))),
    10: _len(_t("Zustellung"), _t("Wie tief wird pro Durchgang zugestellt?"), -5, g=S),
    11: _feed(_t("Vorschub Tiefe"), _t("Mit welchem Vorschub wird in die Tiefe gefahren?"), 150),
    12: _feed(_t("Vorschub Räumen"), _t("Mit welchem Vorschub wird ausgeräumt?"), 500),
    13: _num(_t("Räumwerkzeug"), _t("Nummer oder Name des Werkzeugs, das später ausräumt?"), 0, 0, 999999.9),
    14: _len(_t("Aufmaß seitlich"), _t("Welches seitliche Aufmaß bleibt beim Schlichten stehen?"), 0, g=S, mode=INC),
    15: _sel(_t("Fräsrichtung"), _t("Gleichlauf oder Gegenlauf fräsen?"), 1, _SIDE),
    18: _num(_t("Vorräumwerkzeug"), _t("Nummer des Werkzeugs, das vorher geräumt hat (0 = keines)?"), 0, 0, 99999.9),
    19: _feed(_t("Vorschub Pendeln"), _t("Mit welchem Vorschub wird beim Eintauchen gependelt?"), 0),
    # Bohren, gemeinsame Parameter
    200: _pos(_t("Sicherheitsabstand"), _t("Abstand zwischen Werkzeugspitze und Oberfläche beim Anfahren?"), 2, g=SI,
              mode=INC, also="PREDEF"),
    201: _len(_t("Tiefe"), _t("Wie tief wird bearbeitet (negativ = ins Material)?"), -10, mode=INC),
    202: _pos(_t("Zustellung"), _t("Wie viel wird pro Schritt zugestellt?"), 5, g=S, mode=INC),
    203: _len(_t("Oberfläche"), _t("Auf welcher Höhe liegt die Werkstückoberfläche?"), 0, g=SI, mode=ABS),
    204: _pos(_t("2. Sicherheitsabstand"), _t("Auf welche Höhe über der Oberfläche fährt das Werkzeug zum Schluss?"), 50,
              g=SI, mode=INC, also="PREDEF"),
    205: _pos(_t("Kleinste Zustellung"), _t("Kleinster Zustellschritt, wenn mit Abnahme gebohrt wird?"), 0, g=E),
    206: _feed(_t("Vorschub Tiefe"), _t("Mit welchem Vorschub wird in die Tiefe gefahren?"), 150, also="FAUTO, FU"),
    207: _feed(_t("Vorschub Fräsen"), _t("Mit welchem Vorschub wird gefräst?"), 500),
    208: _feed(_t("Vorschub Rückzug"), _t("Mit welchem Vorschub fährt das Werkzeug heraus (0 = wie Zustellung)?"), 0,
               also="FMAX, FAUTO, PREDEF"),
    210: QDef(_t("Pause oben"), _t("Wie lange wartet das Werkzeug oben nach dem Entspänen?"), 0, 0, 3600, "s", E, "",
              "PREDEF"),
    211: QDef(_t("Pause unten"), _t("Wie lange wartet das Werkzeug am Grund?"), 0, 0, 3600, "s", E, "", "PREDEF"),
    212: _pos(_t("Abnahme"), _t("Um wie viel wird die Zustellung nach jedem Schritt kleiner?"), 0, g=E, mode=INC),
    213: _num(_t("Spanbrüche"), _t("Wie viele Spanbrüche bis zum vollständigen Herausfahren?"), 0, 0, 99999),
    214: _sel(_t("Freifahren"), _t("In welche Richtung fährt die Schneide am Grund frei?"), 0,
             (("0", _t("Nicht freifahren")), ("1", _t("Minus 1. Achse")), ("2", _t("Minus 2. Achse")),
              ("3", _t("Plus 1. Achse")), ("4", _t("Plus 2. Achse"))), g=E),
    215: _sel(_t("Umfang"), _t("Was wird bearbeitet?"), 0,
              (("0", _t("Schruppen und Schlichten")), ("1", _t("Nur Schruppen")), ("2", _t("Nur Schlichten")))),
    216: _len(_t("Mitte X"), _t("Mittelpunkt in der 1. Achse?"), 50, mode=ABS),
    217: _len(_t("Mitte Y"), _t("Mittelpunkt in der 2. Achse?"), 50, mode=ABS),
    218: _len(_t("Länge"), _t("Länge der Figur in der 1. Achse?"), 60),
    219: _len(_t("Breite"), _t("Breite der Figur in der 2. Achse?"), 40),
    220: _pos(_t("Eckenradius"), _t("Radius in den Ecken der Figur?"), 0),
    222: _pos(_t("Rohteil-Ø"), _t("Durchmesser des Rohteils?"), 52),
    223: _pos(_t("Durchmesser"), _t("Durchmesser der fertigen Figur?"), 50),
    224: _ang(_t("Drehung"), _t("Um welchen Winkel ist die Figur gedreht?"), 0, mode=ABS),
    225: _len(_t("Start X"), _t("Startpunkt in der 1. Achse?"), 0, mode=ABS),
    226: _len(_t("Start Y"), _t("Startpunkt in der 2. Achse?"), 0, mode=ABS),
    227: _len(_t("Start Z"), _t("Höhe der Rohteiloberfläche?"), 2, mode=ABS),
    237: _len(_t("Abstand X"), _t("Abstand der Punkte in der 1. Achse?"), 10),
    238: _len(_t("Abstand Y"), _t("Abstand der Punkte in der 2. Achse?"), 10),
    239: _len(_t("Steigung"), _t("Gewindesteigung (positiv = Rechtsgewinde, negativ = Linksgewinde)?"), 1, -99.9999, 99.9999),
    241: _num(_t("Anzahl"), _t("Wie viele Bearbeitungen auf dem Kreis?"), 6, 1, 99999, g=G),
    242: _num(_t("Spalten"), _t("Wie viele Punkte je Zeile?"), 3, 0, 99999, g=G),
    243: _num(_t("Zeilen"), _t("Wie viele Zeilen?"), 2, 0, 99999, g=G),
    244: _pos(_t("Kreis-Ø"), _t("Durchmesser des Lochkreises?"), 60),
    245: _ang(_t("Startwinkel"), _t("Bei welchem Winkel liegt die erste Bearbeitung?"), 0, mode=ABS),
    246: _ang(_t("Endwinkel"), _t("Bei welchem Winkel endet der Kreisbogen (= Startwinkel bei Vollkreis)?"), 360, mode=ABS),
    247: _ang(_t("Winkelschritt"), _t("Winkel zwischen zwei Bearbeitungen (0 = gleichmäßig verteilen)?"), 0, mode=INC),
    248: _ang(_t("Öffnungswinkel"), _t("Über welchen Winkel erstreckt sich die Nut?"), 90, 0, 360),
    249: _len(_t("Senktiefe"), _t("Wie tief wird von unten gesenkt?"), 3, mode=INC),
    250: QDef(_t("Materialstärke"), _t("Wie dick ist das Werkstück?"), 20, 0.0001, BIG),
    251: QDef(_t("Ausmittigkeit"), _t("Um wie viel ist die Schneide aus der Werkzeugmitte versetzt?"), 3, 0.0001, BIG,
              mode=INC),
    252: _len(_t("Schneidenhöhe"), _t("Abstand von der Schneide bis zur Werkzeugspitze?"), 10, mode=INC),
    253: _feed(_t("Vorschub Positionieren"), _t("Mit welchem Vorschub wird vorpositioniert?"), 1000,
              also="FMAX, FAUTO, PREDEF"),
    254: _feed(_t("Vorschub Senken"), _t("Mit welchem Vorschub wird gesenkt?"), 200, also="FAUTO, FU"),
    255: QDef(_t("Pause"), _t("Wie lange wartet das Werkzeug am Senkgrund?"), 0, 0, 99999, "s", E),
    256: _pos(_t("Rückzug Spanbruch"), _t("Um wie viel fährt das Werkzeug zum Spanbrechen zurück?"), 0.2, g=E, mode=INC,
              also="PREDEF"),
    257: _pos(_t("Tiefe Spanbruch"), _t("Nach wie viel Tiefe wird jeweils ein Span gebrochen (0 = nie)?"), 0, g=E, mode=INC),
    258: _pos(_t("Vorhalt oben"), _t("Abstand vor dem letzten Bohrgrund beim ersten Wiederanfahren?"), 0.2, g=E),
    259: _pos(_t("Vorhalt unten"), _t("Abstand vor dem letzten Bohrgrund beim letzten Wiederanfahren?"), 0.2, g=E),
    260: _len(_t("Sichere Höhe"), _t("Auf welcher Höhe fährt das Werkzeug kollisionsfrei?"), 50, g=SI, mode=ABS,
              also="PREDEF"),
    301: _sel(_t("Zwischenhöhe"), _t("Auf welche Höhe fährt das Werkzeug zwischen den Bearbeitungen?"), 1,
              (("0", _t("Sicherheitsabstand")), ("1", _t("2. Sicherheitsabstand"))), g=SI),
    334: _pos(_t("Zustellung je Umlauf"), _t("Wie viel wird pro Schraubenlinie zugestellt?"), 0.5, g=S, mode=INC),
    335: _pos(_t("Soll-Ø"), _t("Welcher Durchmesser soll entstehen?"), 10, mode=ABS),
    336: _ang(_t("Spindelwinkel"), _t("Unter welchem Winkel wird die Spindel ausgerichtet?"), 0, 0, 360, g=E, mode=ABS),
    338: _pos(_t("Zustellung Schlichten"), _t("Wie viel wird beim Schlichten je Durchgang zugestellt (0 = auf einmal)?"), 0,
              g=S, mode=INC),
    339: _num(_t("Bezugspunkt"), _t("Welche Zeile der Bezugspunkttabelle wird aktiv (0 = G54)?"), 0, 0, 8, g=G),
    342: _pos(_t("Vorgebohrt-Ø"), _t("Durchmesser der vorhandenen Bohrung (0 = keine)?"), 0, g=E, mode=ABS),
    343: _sel(_t("Durchmesser/Tiefe"), _t("Wird auf den Durchmesser oder auf die Tiefe zentriert?"), 1,
              (("0", _t("Auf die Tiefe")), ("1", _t("Auf den Durchmesser")))),
    344: _len(_t("Senk-Ø"), _t("Durchmesser der Zentriersenkung?"), 5),
    347: _sel(_t("Begrenzung 1"), _t("Ist die Fläche auf einer Seite durch eine Wand begrenzt?"), 0,
              (("0", _t("Keine Wand")), ("-1", _t("Wand bei 1. Achse minus")), ("+1", _t("Wand bei 1. Achse plus")),
               ("-2", _t("Wand bei 2. Achse minus")), ("+2", _t("Wand bei 2. Achse plus"))), g=E),
    348: _sel(_t("Begrenzung 2"), _t("Zweite begrenzende Wand?"), 0,
              (("0", _t("Keine Wand")), ("-1", _t("1. Achse minus")), ("+1", _t("1. Achse plus")), ("-2", _t("2. Achse minus")),
               ("+2", _t("2. Achse plus"))), g=E),
    349: _sel(_t("Begrenzung 3"), _t("Dritte begrenzende Wand?"), 0,
              (("0", _t("Keine Wand")), ("-1", _t("1. Achse minus")), ("+1", _t("1. Achse plus")), ("-2", _t("2. Achse minus")),
               ("+2", _t("2. Achse plus"))), g=E),
    350: _sel(_t("Fräsrichtung"), _t("In welcher Achse laufen die Bahnen?"), 1, (("1", _t("1. Achse")), ("2", _t("2. Achse")))),
    351: _sel(_t("Fräsrichtung"), _t("Gleichlauf oder Gegenlauf fräsen?"), 1, _SIDE, also="PREDEF"),
    353: _len(_t("Spitzentiefe"), _t("Wie tief taucht die Werkzeugspitze ein?"), -1, -999.9999, -0.0001, mode=INC),
    354: _ang(_t("Fasenwinkel"), _t("Winkel der Fase (0 = halber Spitzenwinkel des Werkzeugs)?"), 0, 0, 89),
    355: _num(_t("Gänge je Umlauf"), _t("Wie viele Gewindegänge pro Umlauf (0 = alle auf einmal)?"), 0, 0, 99999),
    356: _len(_t("Bohrtiefe"), _t("Wie tief wird gebohrt?"), -20, mode=INC),
    357: _pos(_t("Seitenabstand"), _t("Seitlicher Abstand des Werkzeugs zum Werkstück beim Anfahren?"), 2, g=SI),
    358: _len(_t("Stirnsenktiefe"), _t("Wie tief wird an der Stirnseite gesenkt?"), 0),
    359: _pos(_t("Stirnversatz"), _t("Um wie viel wird die Schneide beim Stirnsenken versetzt?"), 0, mode=INC),
    360: _sel(_t("Senken wann"), _t("Wird vor oder nach dem Gewinde gesenkt?"), 0, (("0", _t("Vorher")), ("1", _t("Nachher")))),
    365: _sel(_t("Zwischenweg"), _t("Wie fährt das Werkzeug zwischen den Bearbeitungen?"), 0,
              (("0", _t("Auf einer Geraden")), ("1", _t("Auf dem Teilkreis"))), g=E),
    366: _sel(_t("Eintauchen"), _t("Wie taucht das Werkzeug ein?"), 1,
              (("0", _t("Senkrecht")), ("1", _t("Auf einer Schraubenlinie")), ("2", _t("Pendelnd"))), also="PREDEF"),
    367: _sel(_t("Lage"), _t("Wo steht das Werkzeug beim Zyklusaufruf im Verhältnis zur Figur?"), 0, _CORNER5),
    368: _pos(_t("Aufmaß seitlich"), _t("Wie viel Material bleibt an den Wänden für das Schlichten stehen?"), 0, g=S),
    369: _pos(_t("Aufmaß Boden"), _t("Wie viel Material bleibt am Boden für das Schlichten stehen?"), 0, g=S, mode=INC),
    370: _num(_t("Überlappung"), _t("Faktor für die seitliche Bahnüberlappung (× Werkzeugradius)?"), 1, 0.0001, 1.999, g=S),
    373: _feed(_t("Vorschub Wiederanfahren"), _t("Mit welchem Vorschub wird nach dem Entspänen angefahren (0 = Eilgang)?"),
              0, also="FAUTO, FMAX, FU, FZ", g=E),
    374: _ang(_t("Drehung"), _t("Um welchen Winkel ist die Figur gedreht?"), 0),
    375: _pos(_t("Kreis-Ø"), _t("Durchmesser des Kreises, auf dem die Nut liegt?"), 60),
    376: _ang(_t("Startwinkel"), _t("Bei welchem Winkel beginnt die Figur?"), 0),
    377: _num(_t("Anzahl"), _t("Wie oft wird die Figur auf dem Kreis wiederholt?"), 1, 1, 99999, g=G),
    378: _ang(_t("Winkelschritt"), _t("Winkel zwischen den Wiederholungen?"), 0, mode=INC),
    379: _pos(_t("Vertiefter Start"), _t("Wie tief ist schon vorgebohrt (dort beginnt die Zustellung)?"), 0, g=E, mode=INC),
    385: _feed(_t("Vorschub Schlichten"), _t("Mit welchem Vorschub wird geschlichtet?"), 500),
    386: _len(_t("Ende Z"), _t("Auf welche Höhe wird plangefräst?"), 0, mode=ABS),
    389: _sel(_t("Strategie"), _t("Wie werden die Bahnen gelegt?"), 1,
              (("0", _t("Hin und her, Zustellung außerhalb")), ("1", _t("Hin und her, Zustellung auf der Fläche")),
               ("2", _t("Immer in eine Richtung, Rückweg im Eilgang")), ("3", _t("Immer in eine Richtung, Rückweg über der Fläche")),
               ("4", _t("Von außen nach innen (spiralförmig)")))),
    390: _sel(_t("An-/Wegfahren"), _t("Wie wird die Kontur an- und verlassen?"), 1,
              (("1", _t("Tangential auf einem Kreisbogen")), ("2", _t("Tangential auf einer Geraden")),
               ("3", _t("Senkrecht zur Kontur")))),
    391: _sel(_t("Radiuskorrektur"), _t("Auf welcher Seite der Kontur fährt das Werkzeug?"), 1,
              (("0", _t("Auf der Kontur (R0)")), ("1", _t("Links (RL)")), ("2", _t("Rechts (RR)")))),
    392: _pos(_t("Anfahrradius"), _t("Radius des An- und Abfahrbogens?"), 5),
    393: _ang(_t("Bogenwinkel"), _t("Wie groß ist der An- und Abfahrbogen?"), 90, 0, BIG),
    394: _pos(_t("Hilfspunktabstand"), _t("Abstand des Hilfspunkts vor dem Anfahren?"), 0, g=E),
    395: _sel(_t("Tiefenbezug"), _t("Worauf bezieht sich die Tiefe?"), 0,
              (("0", _t("Werkzeugspitze")), ("1", _t("Beginn des vollen Durchmessers"))), g=E),
    401: _num(_t("Vorschubfaktor %"), _t("Auf wie viel Prozent wird der Vorschub beim Vollschnitt reduziert?"), 100,
              0.0001, 100),
    403: _num(_t("Drehzahlfaktor"), _t("Mit welchem Faktor ändert sich die Drehzahl beim Herausfahren?"), 1, 0.0001, 10),
    404: _sel(_t("Nachräumen"), _t("Wie fährt das Werkzeug zwischen den Nachräumbereichen?"), 0,
              (("0", _t("Auf Sicherheitsabstand anheben")), ("1", _t("Auf der Tiefe bleiben")))),
    424: _pos(_t("Rohteil Länge"), _t("Länge des Rohteils in der 1. Achse?"), 75),
    425: _pos(_t("Rohteil Breite"), _t("Breite des Rohteils in der 2. Achse?"), 60),
    426: _sel(_t("Drehrichtung An/Ab"), _t("Wie dreht die Spindel beim Ein- und Ausfahren?"), 5,
              (("3", _t("Rechtslauf (M3)")), ("4", _t("Linkslauf (M4)")), ("5", _t("Spindel steht"))), g=E),
    427: _num(_t("Drehzahl An/Ab"), _t("Drehzahl beim Ein- und Ausfahren?"), 50, 1, 99999, unit="1/min"),
    428: _num(_t("Drehzahl Bohren"), _t("Drehzahl beim Bohren?"), 500, 0, 99999, g=S, unit="1/min"),
    429: _num(_t("Kühlung ein"), _t("Welche M-Funktion schaltet das Kühlmittel ein?"), 8, 0, 999),
    430: _num(_t("Kühlung aus"), _t("Welche M-Funktion schaltet das Kühlmittel aus?"), 9, 0, 999),
    435: _pos(_t("Pausentiefe"), _t("Nach welcher Tiefe wird kurz verweilt (0 = nie)?"), 0, g=E, mode=INC),
    436: _pos(_t("Zustellung je Umlauf"), _t("Wie viel wird pro Umlauf in die Tiefe zugestellt?"), 2, g=S, mode=ABS),
    437: _sel(_t("Anfahrpunkt"), _t("Von wo wird die Figur angefahren?"), 0,
              (("0", _t("Rechts neben der Figur")), ("1", _t("Ecke links unten")), ("2", _t("Ecke rechts unten")),
               ("3", _t("Ecke rechts oben")), ("4", _t("Ecke links oben"))), g=E),
    438: _num(_t("Räumwerkzeug"), _t("Werkzeug, das vorher ausgeräumt hat (-1 = zuletzt benutztes, 0 = keines)?"), -1,
              -1, 32767.9),
    439: _sel(_t("Vorschubbezug"), _t("Worauf bezieht sich der Vorschub?"), 0,
              (("0", _t("Werkzeugmitte")), ("1", _t("Schneide nur beim Schlichten")), ("2", _t("Schneide beim Schlichten und Eintauchen")),
               ("3", _t("Immer Schneide"))), g=E),
    446: _num(_t("Restmaterial"), _t("Welche Restmaterialdicke darf stehen bleiben?"), 0.01, 0.001, 9.999, unit="mm"),
    447: _num(_t("Verbindungsabstand"), _t("Bis zu welchem Abstand werden Bereiche ohne Abheben verbunden?"), 10, 0, 999.999,
              unit="mm"),
    448: _num(_t("Bahnverlängerung"), _t("Um wie viel werden die Bahnen an offenen Enden verlängert?"), 2, 0, 99.999, unit="mm"),
    500: QDef(_t("Text"), _t("Welcher Text wird graviert?"), 0, None, None, "", G, "text"),
    512: _feed(_t("Vorschub Anfahren"), _t("Mit welchem Vorschub wird an das Gewinde gefahren (0 = Fräsvorschub)?"), 0,
              also="FAUTO"),
    513: _pos(_t("Zeichenhöhe"), _t("Wie hoch sind die Zeichen?"), 10),
    514: _num(_t("Zeichenabstand"), _t("Faktor für den Abstand zwischen den Zeichen?"), 0.5, 0, 10, g=S),
    515: _num(_t("Schrift"), _t("Welche Schrift (0 = eingebaute Strichschrift)?"), 0, 0, 0, g=E),
    516: _sel(_t("Textanordnung"), _t("Wie wird der Text angeordnet?"), 0,
              (("0", _t("Auf einer Geraden")), ("1", _t("Auf einem Kreisbogen (außen)")), ("2", _t("Auf einem Kreisbogen (innen)")))),
    517: _pos(_t("Textradius"), _t("Radius des Kreises für Text auf dem Bogen?"), 50),
    568: _num(_t("Faktor Eintauchen"), _t("Faktor für den Vorschub beim Eintauchen?"), 0.6, 0.1, 1, g=S),
    569: _sel(_t("Erste Figur"), _t("Was ist die erste Figur der Kontur?"), 0,
              (("0", _t("Tasche")), ("1", _t("Begrenzung")), ("2", _t("Begrenzung mit offener Seite")))),
    571: _pos(_t("Bezugs-Ø"), _t("Durchmesser des Bezugskreises?"), 50),
    572: _num(_t("Ecken"), _t("Wie viele Ecken hat das Vieleck?"), 6, 3, 30, g=G),
    573: _sel(_t("Kreisbezug"), _t("Bezieht sich der Durchmesser auf Inkreis oder Umkreis?"), 0,
              (("0", _t("Inkreis")), ("1", _t("Umkreis"))), g=G),
    574: _pos(_t("Max. Textlänge"), _t("Höchstens wie lang darf der Text werden (0 = beliebig)?"), 0, g=E),
    575: _sel(_t("Zustellfolge"), _t("In welcher Reihenfolge wird zugestellt?"), 0,
              (("0", _t("Von oben nach unten")), ("1", _t("Von unten nach oben")), ("2", _t("Wechselnd")))),
    576: _num(_t("Drehzahl"), _t("Drehzahl für den Zyklus (0 = wie beim Werkzeugaufruf)?"), 0, 0, 99999, g=S, unit="1/min"),
    577: _num(_t("Faktor Anfahrradius"), _t("Faktor für den An- und Abfahrradius?"), 0.2, 0.15, 0.99),
    578: _num(_t("Faktor Innenecken"), _t("Faktor für den Radius in Innenecken?"), 0.2, 0.05, 0.99),
    579: _num(_t("Faktor Eintauchdrehzahl"), _t("Faktor für die Drehzahl beim Eintauchen?"), 1, 0.2, 1.5),
    595: _sel(_t("Schlichtart"), _t("Wie wird der Boden geschlichtet?"), 1,
              (("0", _t("Gleiche Bahnabstände")), ("1", _t("Gleicher Eingriff")))),
    # LCNC-Cyclo-eigen (Zyklus 2028 GRUNDSTELLUNG)
    596: _sel(_t("Position"), _t("Welche gespeicherte Position wird angefahren?"), 0,
              (("0", _t("Grundstellung (G28, Referenzpunkt)")), ("1", _t("2. Position (G30, z. B. Wechselposition)")))),
    597: _sel(_t("Achsen"), _t("Welche Achsen fahren dorthin? Z fährt immer zuerst."), 1,
              (("0", _t("Nur Z (Werkzeugachse)")), ("1", _t("Erst Z, dann X und Y")),
               ("2", _t("Erst Z, dann X, Y und Drehachsen")))),
    650: _sel(_t("Figurart"), _t("Ist die Figur eine Tasche, eine Insel oder eine Planfläche?"), 1,
              (("0", _t("Tasche")), ("1", _t("Insel")), ("2", _t("Begrenzung zum Planfräsen"))), g=G),
    651: QDef(_t("Länge"), _t("Länge der Begrenzung in der 1. Achse?"), 50, 0.001, 9999.999),
    652: QDef(_t("Breite"), _t("Breite der Begrenzung in der 2. Achse?"), 50, 0.001, 9999.999),
    653: QDef(_t("Durchmesser"), _t("Durchmesser der Begrenzung?"), 50, 0.001, 9999.999),
    654: _sel(_t("Mittenbezug"), _t("Worauf bezieht sich die Mitte der Begrenzung?"), 0,
              (("0", _t("Auf die Position beim Aufruf")), ("1", _t("Auf die Mitte der Figur"))), g=G),
    655: QDef(_t("Versatz X"), _t("Versatz der Begrenzung in der 1. Achse?"), 0, -999.999, 999.999),
    656: QDef(_t("Versatz Y"), _t("Versatz der Begrenzung in der 2. Achse?"), 0, -999.999, 999.999),
    660: _sel(_t("Eckenform"), _t("Wie werden die Ecken ausgeführt?"), 0,
              (("0", _t("Radius")), ("1", _t("Fase")), ("2", _t("Freistich in beide Achsen")), ("3", _t("Freistich in der 1. Achse")),
               ("4", _t("Freistich in der 2. Achse"))), g=G),
}

# Abweichende Bedeutung in einzelnen Zyklen (Zyklus, Q) -> geänderte Felder
OVERRIDE: dict[tuple[int, int], dict] = {
    (206, 201): dict(label=_t("Gewindetiefe"), prompt=_t("Wie tief wird das Gewinde (negativ = ins Material)?"), default=-18),
    (207, 201): dict(label=_t("Gewindetiefe"), prompt=_t("Wie tief wird das Gewinde (negativ = ins Material)?"), default=-18),
    (209, 201): dict(label=_t("Gewindetiefe"), prompt=_t("Wie tief wird das Gewinde (negativ = ins Material)?"), default=-18),
    (262, 201): dict(label=_t("Gewindetiefe"), prompt=_t("Wie tief wird das Gewinde (negativ = ins Material)?"), default=-18),
    (263, 201): dict(label=_t("Gewindetiefe"), prompt=_t("Wie tief wird das Gewinde (negativ = ins Material)?"), default=-18),
    (264, 201): dict(label=_t("Gewindetiefe"), prompt=_t("Wie tief wird das Gewinde (negativ = ins Material)?"), default=-18),
    (265, 201): dict(label=_t("Gewindetiefe"), prompt=_t("Wie tief wird das Gewinde (negativ = ins Material)?"), default=-18),
    (267, 201): dict(label=_t("Gewindetiefe"), prompt=_t("Wie tief wird das Gewinde (negativ = ins Material)?"), default=-18),
    (225, 201): dict(prompt=_t("Wie tief wird graviert?"), default=-0.5),
    (225, 202): dict(label=_t("Max. Zustellung"), default=0.5),
    (225, 367): dict(label=_t("Textlage"), prompt=_t("Auf welchen Punkt des Textes bezieht sich die Position?"),
                     options=(("0", _t("Links unten")), ("1", _t("Mitte unten")), ("2", _t("Rechts unten")), ("3", _t("Rechts oben")),
                              ("4", _t("Mitte oben")), ("5", _t("Links oben")), ("6", _t("Links Mitte")), ("7", _t("Textmitte")),
                              ("8", _t("Rechts Mitte"))), lo=0.0, hi=8.0),
    (232, 218): dict(prompt=_t("Länge der Fläche in der 1. Achse?"), default=100, mode=INC),
    (232, 219): dict(prompt=_t("Breite der Fläche in der 2. Achse?"), default=60, mode=INC),
    (232, 389): dict(options=Q[389].options[:3], hi=2.0),
    (233, 218): dict(prompt=_t("Länge der Fläche in der 1. Achse?"), default=100),
    (233, 219): dict(prompt=_t("Breite der Fläche in der 2. Achse?"), default=60),
    (233, 367): dict(label=_t("Flächenlage"), prompt=_t("Wo steht das Werkzeug im Verhältnis zur Fläche?"), default=-1,
                     options=(("-1", _t("Aktuelle Position ist die Mitte")),) + _CORNER5, lo=-1.0),
    (253, 218): dict(label=_t("Nutlänge"), prompt=_t("Länge der Nut?"), default=60, lo=0.0),
    (253, 219): dict(label=_t("Nutbreite"), prompt=_t("Breite der Nut?"), default=10, lo=0.0),
    (253, 367): dict(label=_t("Nutlage"), options=(("0", _t("Mitte der Nut")), ("1", _t("Linkes Ende")),
                                              ("2", _t("Mitte des linken Bogens")), ("3", _t("Mitte des rechten Bogens")),
                                              ("4", _t("Rechtes Ende")))),
    (254, 219): dict(label=_t("Nutbreite"), prompt=_t("Breite der Nut?"), default=10, lo=0.0),
    (254, 367): dict(label=_t("Nutlage"), lo=0.0, hi=3.0,
                     options=(("0", _t("Aktuelle Position ohne Bedeutung")), ("1", _t("Mitte des linken Bogens")),
                              ("2", _t("Mitte der Nut")), ("3", _t("Mitte des rechten Bogens")))),
    (275, 219): dict(label=_t("Nutbreite"), prompt=_t("Breite der Nut?"), default=12, lo=0.0),
    (275, 201): dict(default=-10), (275, 202): dict(default=3),
    (256, 220): dict(label=_t("Radius/Fase"), prompt=_t("Eckenradius (+) oder Fase (−)?"), lo=-BIG),
    (258, 220): dict(label=_t("Radius/Fase"), prompt=_t("Eckenradius (+) oder Fase (−)?"), lo=-BIG),
    (1271, 220): dict(label=_t("Radius/Fase"), prompt=_t("Größe von Radius oder Fase an den Ecken?")),
    (1278, 220): dict(label=_t("Radius/Fase"), prompt=_t("Größe von Radius oder Fase an den Ecken?")),
    (1273, 219): dict(label=_t("Breite"), prompt=_t("Breite der Nut bzw. des Stegs?"), default=10),
    (1273, 218): dict(label=_t("Länge"), prompt=_t("Länge der Nut bzw. des Stegs?"), default=60),
    (257, 223): dict(label=_t("Fertig-Ø"), prompt=_t("Durchmesser des fertigen Zapfens?")),
    (264, 356): dict(label=_t("Bohrtiefe")),
    (263, 356): dict(label=_t("Senktiefe"), prompt=_t("Wie tief wird gesenkt?")),
    (277, 359): dict(label=_t("Fasenbreite"), prompt=_t("Breite der Fase (negativ = in die andere Richtung)?"), default=0.2,
                     lo=-999.9999, hi=999.9999),
    (208, 370): dict(prompt=_t("Faktor für die seitliche Bahnüberlappung (0 = automatisch)?"), default=0, lo=0.0),
    (232, 370): dict(label=_t("Max. Überlappung")),
    (233, 370): dict(label=_t("Max. Überlappung")),
    (252, 366): dict(options=Q[366].options[:2], hi=1.0),
    (257, 366): dict(options=Q[366].options[:2], hi=1.0),
    (204, 253): dict(default=750),
    (240, 201): dict(prompt=_t("Tiefe der Zentrierung (wenn auf Tiefe zentriert wird)?"), default=-2),
}

# --------------------------------------------------------------------------- Zyklen
# Nummer: (Name, Gruppe, Q-Nummern in Satzreihenfolge)
GROUP_NAMES = {
    "bohren": _t("Bohren"), "gewinde": _t("Gewinde"), "fraesen": _t("Taschen, Zapfen, Nuten, Planen"),
    "umrechnung": _t("Koordinaten-Umrechnung"), "kontur": _t("Konturbearbeitung"), "kt": _t("Konturtaschen"),
    "muster": _t("Punktemuster"), "sonder": _t("Sonderzyklen"),
}

CYCLES: dict[int, tuple[str, str, tuple[int, ...]]] = {
    8: ("SPIEGELN", "umrechnung", ()),
    9: ("VERWEILZEIT", "sonder", ()),
    10: ("DREHUNG", "umrechnung", ()),
    11: ("MASSFAKTOR", "umrechnung", ()),
    12: ("PGM CALL", "sonder", ()),
    13: ("ORIENTIERUNG", "sonder", ()),
    14: ("KONTUR", "kontur", ()),
    20: ("KONTURDATEN", "kontur", (1, 2, 3, 4, 5, 6, 7, 8, 9)),
    21: ("VORBOHREN", "kontur", (10, 11, 13)),
    22: ("RAEUMEN", "kontur", (10, 11, 12, 18, 19, 208, 401, 404)),
    23: ("BODEN SCHLICHTEN", "kontur", (11, 12, 208)),
    24: ("SEITE SCHLICHTEN", "kontur", (9, 10, 11, 12, 14, 438)),
    25: ("KONTURZUG", "kontur", (1, 3, 5, 7, 10, 11, 12, 15, 18, 446, 447, 448)),
    26: ("MASSFAKTOR ACHSWEISE", "umrechnung", ()),
    32: ("TOLERANZ", "sonder", ()),
    200: ("BOHREN", "bohren", (200, 201, 206, 202, 210, 203, 204, 211, 395)),
    201: ("REIBEN", "bohren", (200, 201, 206, 211, 208, 203, 204)),
    202: ("AUSDREHEN", "bohren", (200, 201, 206, 211, 208, 203, 204, 214, 336)),
    203: ("BOHREN MIT ABNAHME", "bohren", (200, 201, 206, 202, 210, 203, 204, 212, 213, 205, 211, 208, 256, 395)),
    204: ("SENKEN VON UNTEN", "bohren", (200, 249, 250, 251, 252, 253, 254, 255, 203, 204, 214, 336)),
    205: ("TIEFBOHREN", "bohren", (200, 201, 206, 202, 203, 204, 212, 205, 258, 259, 257, 256, 211, 379, 253, 208,
                                   395, 373)),
    206: ("GEWINDEBOHREN", "gewinde", (200, 201, 206, 211, 203, 204)),
    207: ("GEWINDEBOHREN STARR", "gewinde", (200, 201, 239, 203, 204)),
    208: ("BOHRUNG FRAESEN", "bohren", (200, 201, 206, 334, 203, 204, 335, 342, 351, 370)),
    209: ("GEWINDEBOHREN SPANBRUCH", "gewinde", (200, 201, 239, 203, 204, 257, 256, 336, 403)),
    220: ("PUNKTE AUF KREIS", "muster", (216, 217, 244, 245, 246, 247, 241, 200, 203, 204, 301, 365)),
    221: ("PUNKTE AUF RASTER", "muster", (225, 226, 237, 238, 242, 243, 224, 200, 203, 204, 301)),
    225: ("GRAVIEREN", "sonder", (500, 200, 201, 202, 203, 204, 206, 207, 367, 374, 513, 514, 515, 516, 517, 574)),
    232: ("PLANEN", "fraesen", (389, 225, 226, 227, 386, 218, 219, 202, 369, 370, 207, 385, 253, 200, 357, 204)),
    233: ("PLANEN MIT WAENDEN", "fraesen", (215, 389, 350, 218, 219, 227, 386, 369, 202, 370, 207, 385, 253, 357, 200,
                                           204, 347, 348, 349, 220, 368, 338, 367)),
    240: ("ZENTRIEREN", "bohren", (200, 343, 201, 344, 206, 211, 203, 204, 342, 253)),
    241: ("TIEFBOHREN EINSCHNEIDIG", "bohren", (200, 201, 206, 211, 203, 204, 379, 253, 208, 426, 427, 428, 429, 430,
                                                435, 401, 202, 212, 205)),
    247: ("BEZUGSPUNKT", "umrechnung", (339,)),
    251: ("RECHTECKTASCHE", "fraesen", (215, 218, 219, 220, 368, 224, 367, 207, 351, 201, 202, 369, 206, 338, 200,
                                        203, 204, 370, 366, 385, 439)),
    252: ("KREISTASCHE", "fraesen", (215, 223, 368, 207, 351, 201, 202, 369, 206, 338, 200, 203, 204, 370, 366, 385,
                                     439)),
    253: ("NUT", "fraesen", (215, 218, 219, 368, 374, 367, 207, 351, 201, 202, 369, 206, 338, 200, 203, 204, 366, 385,
                             439)),
    254: ("BOGENNUT", "fraesen", (215, 219, 368, 375, 367, 216, 217, 376, 248, 378, 377, 207, 351, 201, 202, 369, 206,
                                  338, 200, 203, 204, 366, 385, 439)),
    256: ("RECHTECKZAPFEN", "fraesen", (218, 424, 219, 425, 220, 368, 224, 367, 207, 351, 201, 202, 206, 200, 203, 204,
                                        370, 437, 215, 369, 338, 385)),
    257: ("KREISZAPFEN", "fraesen", (223, 222, 368, 207, 351, 201, 202, 206, 200, 203, 204, 370, 376, 215, 369, 338,
                                     385)),
    258: ("VIELECKZAPFEN", "fraesen", (573, 571, 222, 572, 224, 220, 368, 207, 351, 201, 202, 206, 200, 203, 204, 370,
                                       215, 369, 338, 385)),
    262: ("GEWINDEFRAESEN", "gewinde", (335, 239, 201, 355, 253, 351, 200, 203, 204, 207, 512)),
    263: ("GEWINDE MIT SENKUNG", "gewinde", (335, 239, 201, 356, 253, 351, 200, 357, 358, 359, 203, 204, 254, 207,
                                            512)),
    264: ("GEWINDE MIT BOHREN", "gewinde", (335, 239, 201, 356, 253, 351, 202, 258, 257, 256, 358, 359, 200, 203, 204,
                                           206, 207, 512)),
    265: ("GEWINDE HELIX", "gewinde", (335, 239, 201, 253, 358, 359, 360, 200, 203, 204, 254, 207)),
    267: ("AUSSENGEWINDE", "gewinde", (335, 239, 201, 355, 253, 351, 200, 358, 359, 203, 204, 254, 207, 512)),
    270: ("KONTURZUG AN/AB", "kontur", (390, 391, 392, 393, 394)),
    271: ("KT DATEN", "kt", (203, 201, 368, 369, 260, 578, 569)),
    272: ("KT RAEUMEN", "kt", (202, 370, 207, 568, 253, 200, 438, 577, 351, 576, 579, 575)),
    273: ("KT BODEN SCHLICHTEN", "kt", (370, 385, 568, 253, 200, 438, 595, 577)),
    274: ("KT SEITE SCHLICHTEN", "kt", (338, 385, 253, 200, 14, 438, 351)),
    275: ("KONTURNUT TROCHOIDAL", "kontur", (200, 201, 202, 203, 204, 206, 207, 215, 219, 338, 351, 366, 368, 369, 385,
                                            436, 439)),
    277: ("KT FASE", "kt", (353, 359, 207, 253, 200, 438, 351, 354)),
    1271: ("KT RECHTECK", "kt", (650, 218, 219, 660, 220, 367, 224, 203, 201, 368, 369, 260, 578)),
    1272: ("KT KREIS", "kt", (650, 223, 367, 203, 201, 368, 369, 260, 578)),
    1273: ("KT NUT/STEG", "kt", (650, 219, 218, 367, 224, 203, 201, 368, 369, 260, 578)),
    1278: ("KT VIELECK", "kt", (650, 573, 571, 572, 660, 220, 224, 203, 201, 368, 369, 260, 578)),
    1281: ("KT BEGRENZUNG RECHTECK", "kt", (651, 652, 654, 655, 656)),
    1282: ("KT BEGRENZUNG KREIS", "kt", (653, 654, 655, 656)),
    # 2000…: LCNC-Cyclo-eigene Zyklen für den LinuxCNC-Unterbau (keine Heidenhain-Nummern)
    2028: ("GRUNDSTELLUNG", "sonder", (596, 597)),
}


def qdef(cycle: int, q: int) -> QDef:
    base = Q[q]
    o = OVERRIDE.get((cycle, q))
    return replace(base, **o) if o else base
