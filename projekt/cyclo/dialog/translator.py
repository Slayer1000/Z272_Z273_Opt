"""Übersetzer Dialog -> LinuxCNC-G-Code (RS274NGC).

Grundsätze
----------
* Es wird *echter* LinuxCNC-G-Code erzeugt, den der Original-Interpreter ausführt.
  Die Steuerungslogik von LinuxCNC (Bahnplanung, Kinematik, Werkzeugkorrektur)
  bleibt unverändert.
* Jede erzeugte G-Code-Zeile kennt ihren Dialog-Ursprungssatz (``blockmap``),
  damit Ausführungscursor, Einzelsatz und Simulation am Dialogsatz anzeigen.
* Q-Parameter werden zu benannten LinuxCNC-Parametern (#<_q1> ...) und erst zur
  Laufzeit ausgewertet. Inkrementale Koordinaten (IX ...) werden, wenn die Position
  statisch bekannt ist, absolut ausgerechnet, sonst über die aktuellen Positions-
  parameter #5420.. von LinuxCNC gebildet.
* Zyklus-Parameter werden beim CYCL DEF als Q-Parameter gesetzt
  (#<_q200> = 2 ...). Der Zyklus selbst ist ein O-Wort-Unterprogramm
  (cyclo/ngc/cyclo_cyclNNN.ngc), das diese Parameter liest.
"""

from __future__ import annotations

from ..i18n import _t

import dataclasses
import math
import re
from dataclasses import dataclass, field

from .cycles import IMPLEMENTED, REGISTRY
from .cyclegen import GENERATORS, CycleError, P, Tool, generate
from .expr import ExprError, q_name, translate_expr
from .parser import PLANE_WORDS, Block, Coord, ParseError, Program, Value, parse_program

AXIS_INDEX = {a: i for i, a in enumerate("XYZABCUVW")}
PLANE = {"Z": ("X", "Y", "G17"), "Y": ("Z", "X", "G18"), "X": ("Y", "Z", "G19")}

# M-Funktionen, die erst am Satzende wirken
M_AT_END = {0, 1, 2, 5, 9, 30, 99}


@dataclass
class TranslatorConfig:
    m128: str = "M428"  # TCP ein (Kinematik umschalten, Sim-Maschine XYZAC-TRT)
    m129: str = "M429"  # TCP aus
    rotary_axes: str = "B"  # Drehachsen der Maschine (PLANE RESET MOVE/TURN fährt sie auf 0)
    # PLANE AXIAL: Achswinkel -> Raumwinkel um X/Y/Z mit Vorzeichen (Kopf B: B+ neigt das Werkzeug nach -X)
    axial_signs: str = "A+B-C+"
    # TCP am Programmanfang ausschalten (m129): Werkzeuglängen ändern sich sonst in der TCP-Kinematik
    # ("the tool offset change put the point at …"); nur wenn m129 in der Maschine existiert (Remap)
    tcp_off_at_start: bool = False
    comments: bool = True  # Dialogsatz als Kommentar über jede Übersetzung
    tool_names: dict = field(default_factory=dict)  # Werkzeugname -> Nummer
    # Zyklus-Unterprogramme in die erzeugte Datei einbetten (eindeutige Zeilennummern für den
    # Ausführungscursor, Datei läuft ohne SUBROUTINE_PATH). None = Paketverzeichnis cyclo/ngc
    inline_cycles: bool = True
    cycle_dir: str | None = None
    # Werkzeugdaten für Zyklen mit Bahnberechnung: {T: {"R":.., "L":.., "ANGLE":.., "T_ANGLE":..}}
    tools: dict = field(default_factory=dict)
    # Werkzeugdatenbank: Werkzeugnummer -> Platz (= LinuxCNC-Nummer); None = Nummer unverändert
    tool_pockets: dict | None = None
    tool_db: object = None  # ToolDB für Schwesterwerkzeuge (resolve)
    # "/"-Sätze (Satz ausblenden) weglassen – Schalter "Überspringen" im Programmlauf
    skip_blocks: bool = False


@dataclass
class Message:
    line: int
    text: str
    severity: str = "error"  # error | warning

    def __str__(self):
        return _t('Zeile {0}: {1}').format(self.line + 1, self.text)


@dataclass
class Result:
    gcode_lines: list[str]
    blockmap: list[int | None]  # je G-Code-Zeile: Dialog-Quellzeile
    messages: list[Message]
    program: Program
    stock: dict | None = None  # BLK FORM: {"min": (x,y,z), "max": (x,y,z), "axis": "Z"}

    @property
    def gcode(self) -> str:
        return "\n".join(self.gcode_lines) + "\n"

    @property
    def errors(self) -> list[Message]:
        return [m for m in self.messages if m.severity == "error"]

    def source_line_for(self, gcode_line: int) -> int | None:
        if 0 <= gcode_line < len(self.blockmap):
            return self.blockmap[gcode_line]
        return None


def _fmt(v: float) -> str:
    if abs(v) < 5e-7:
        return "0"
    return f"{v:.4f}".rstrip("0").rstrip(".")


class TranslateError(Exception):
    pass


class Translator:
    def __init__(self, config: TranslatorConfig | None = None):
        self.cfg = config or TranslatorConfig()

    # ------------------------------------------------------------------ API
    def translate_text(self, text: str, filename: str = "") -> Result:
        program, perrors = parse_program(text)
        return self.translate(program, perrors, filename)

    def translate(self, program: Program, parse_errors=(), filename: str = "") -> Result:
        self.out: list[str] = []
        self.map: list[int | None] = []
        self.msgs: list[Message] = [Message(e.line, e.msg) for e in parse_errors]
        self.stock: dict = {}
        self._ocount = 1000
        self._used_cycles: set[int] = set()
        self._gen_subs: list[str] = []
        self._gen_cache: dict = {}
        self.tool = Tool()
        self.pattern: list | None = None
        self.used_rotation = False
        # Rohteil-Rechteck (BLK FORM) nur an 272/273 geben, solange die Zykluskoordinaten im System der
        # BLK FORM liegen: keine Verschiebung (G52), Drehung (Zyklus 10), anderer Bezugspunkt (247)
        self._stock_rect = False
        self._shift_active = False
        self._rot_active = False
        # Spiegeln (Zyklus 8) und Maßfaktor (11, 26): wirken beim Übersetzen auf alle Koordinaten
        self.mirror = {"X": 1.0, "Y": 1.0, "Z": 1.0}
        self.scale = 1.0
        self.ascale = {"X": 1.0, "Y": 1.0, "Z": 1.0}
        self.acenter = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.tcp = False  # TCP-Kinematik aktiv (M128/FUNCTION TCPM)
        self.spindle = None  # None = unbekannt (Programmanfang), False = aus, True = M3/M4
        self.plane = False  # geschwenkte Bearbeitungsebene aktiv (G68.2)
        self.plane_tcp = False  # TCP wurde von PLANE eingeschaltet
        self.plane_shift = False  # G52 in der geschwenkten Ebene
        self._reset_motion_state()
        self.tool_axis = "Z"
        self.active_cycle: Block | None = None
        self.sl_contour: list = []
        self.sl_data: Block | None = None
        self.ct_data = None  # Zyklus 270 KONTURZUG-DATEN
        self.ocm_data = None  # Zyklus 271 bzw. Figurdaten
        self.ocm_figure = None  # (Nummer, Werte) einer Standardfigur 127x
        self.ocm_boundary = None  # (Nummer, Werte) einer Begrenzung 128x

        blocks = program.blocks
        self._all_blocks = blocks
        main, subs = self._split_main_and_subs(blocks)
        rep_starts = self._find_section_repeats(main)
        sub_labels = {self._label_key(b.data["label"]) for b in subs if b.kind == "LBL" and b.data["label"] != 0}

        self._emit(None, _t("(Erzeugt vom LCNC-Cyclo Dialog-Uebersetzer - nicht von Hand aendern)"))
        if filename:
            self._emit(None, f"(Quelle: {filename})")
        unit = "G20" if program.unit == "INCH" else "G21"

        # Unterprogramme (LBL nach dem Programmende) werden beim CALL LBL an der Aufrufstelle
        # eingesetzt: so gelten Werkzeug, Spiegeln/Maßfaktor und Zustand des Aufrufs, und der Ausführungscursor springt in die Sätze des Unterprogramms.
        cur_sub = None
        self._sub_bodies: dict = {}
        for b in subs:
            if b.kind == "LBL":
                cur_sub = self._label_key(b.data["label"]) if b.data["label"] != 0 else None
                if cur_sub is not None:
                    self._sub_bodies[cur_sub] = []
                continue
            if cur_sub is None:
                if b.kind not in ("STRUCT", "COMMENT", "END_PGM"):
                    self.msgs.append(Message(b.line, _t("Satz nach Programmende ausserhalb eines LBL wird ignoriert"), "warning"))
                continue
            self._sub_bodies[cur_sub].append(b)
        self._inline_depth = 0

        self._reset_motion_state()
        self._emit(None, f"G17 {unit} G40 G49 G80 G90 G94 G64")
        if self.cfg.tcp_off_at_start:
            self._emit(None, _t('{0} (TCP aus zu Programmbeginn)').format(self.cfg.m129))
        open_reps: dict = {}
        self._open_reps = open_reps
        for b in main:
            if b.kind == "LBL" and b.data["label"] != 0:
                key = self._label_key(b.data["label"])
                if key in rep_starts:
                    o = self._onum()
                    open_reps[key] = o
                    count = rep_starts[key] + 1
                    self._emit(b.line, f"o{o} repeat [{count}]")
                    self._reset_motion_state()
                continue
            self._block(b, blocks, sub_labels, rep_starts)
        if self.used_rotation:
            self._emit(None, "G10 L2 P0 R0 (Drehung aus Zyklus 10 zuruecksetzen)")
        self._emit(None, "M2")
        if self._gen_subs:
            pos = 2 if filename else 1
            self.out[pos:pos] = self._gen_subs
            self.map[pos:pos] = [None] * len(self._gen_subs)
        if self.cfg.inline_cycles and self._used_cycles:
            self._inline_cycles(filename)
        return Result(self.out, self.map, self.msgs, program, self.stock or None)

    def _inline_cycles(self, filename):
        import os

        d = self.cfg.cycle_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "ngc")
        ins, imap = [], []
        for num in sorted(self._used_cycles):
            path = os.path.join(d, f"cyclo_cycl{num}.ngc")
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except OSError:
                self.msgs.append(Message(0, _t('Zyklusdatei {0} fehlt').format(path), "warning"))
                continue
            while lines and lines[-1].strip().upper() in ("M2", "M30", "%", ""):
                lines.pop()
            ins += [_t('(Zyklus {0} eingebettet aus cyclo_cycl{1}.ngc)').format(num, num)] + lines
            imap += [None] * (len(lines) + 1)
        pos = 2 if filename else 1
        self.out[pos:pos] = ins
        self.map[pos:pos] = imap

    # ------------------------------------------------------------ Struktur
    def _split_main_and_subs(self, blocks):
        for i, b in enumerate(blocks):
            ms = b.data.get("m", []) if b.kind in ("M", "L", "STOP") else []
            if b.kind == "END_PGM" or 30 in ms or 2 in ms:
                return blocks[: i + 1], blocks[i + 1 :]
        return blocks, []

    def _find_section_repeats(self, main):
        """LBL n ... CALL LBL n REP k im Hauptprogramm = Programmteil-Wiederholung."""
        reps, open_labels = {}, set()
        for b in main:
            if b.kind == "LBL" and b.data["label"] != 0:
                open_labels.add(self._label_key(b.data["label"]))
            elif b.kind == "CALL_LBL":
                key = self._label_key(b.data["label"])
                if key in open_labels:
                    reps[key] = b.data["rep"]
        return reps

    @staticmethod
    def _label_key(label) -> str:
        if isinstance(label, int):
            return f"lbl_{label}"
        return "lbl_" + re.sub(r"[^a-z0-9_]", "_", str(label).lower())

    def _onum(self) -> int:
        self._ocount += 1
        return self._ocount

    def _reset_motion_state(self):
        self.pos: dict[str, float | None] = {a: None for a in "XYZABCUVW"}
        self.cc: tuple | None = None  # (u, v) als Text + statisch
        self.comp = "R0"
        self.feed_text: str | None = None
        self.tool_feed: str | None = None
        self.pending_corner: list[str] | None = None
        self.tool_dr: float = 0.0

    # ------------------------------------------------------------ Ausgabe
    def _emit(self, line: int | None, text: str):
        self.out.append(text)
        self.map.append(line)

    def _err(self, b: Block, text: str):
        self.msgs.append(Message(b.line, text))
        self._emit(b.line, f"(FEHLER: {text})")

    def _warn(self, b: Block, text: str):
        if not any(m.line == b.line and m.text == text for m in self.msgs):
            self.msgs.append(Message(b.line, text, "warning"))

    def _value(self, v: Value) -> tuple[str, float | None]:
        if v.is_param:
            name = q_name(v.body)
            return (f"[-{name}]" if v.sign < 0 else name), None
        n = v.number()
        return _fmt(n), n

    # ------------------------------------------------------------ Sätze
    def _block(self, b: Block, blocks, sub_labels, rep_starts):
        if self.cfg.comments and b.kind not in ("STRUCT", "COMMENT", "LBL"):
            src = b.text.split("\n")[0].replace("(", "<").replace(")", ">")
            num = f"{b.number} " if b.number is not None else ""
            self._emit(b.line, f"({num}{src})")
        handler = getattr(self, "_k_" + b.kind, None)
        if b.skip and self.cfg.skip_blocks:
            self._emit(b.line, "(/ ausgeblendet)")
            return
        try:
            if handler is None:
                self._err(b, _t('Satzart {0} wird noch nicht unterstützt').format(b.kind))
            else:
                handler(b, blocks=blocks, sub_labels=sub_labels, rep_starts=rep_starts)
        except (TranslateError, ExprError) as e:
            self._err(b, str(e))

    def _k_STRUCT(self, b, **_):
        if self.cfg.comments and b.comment:
            self._emit(b.line, f"(* {b.comment.replace('(', '<').replace(')', '>')})")

    def _k_COMMENT(self, b, **_):
        pass

    def _k_BEGIN_PGM(self, b, **_):
        pass

    def _k_END_PGM(self, b, **_):
        pass

    def _k_LBL(self, b, **_):
        pass  # wird in translate() behandelt

    def _k_BLK_FORM(self, b, **_):
        vals = {c.axis: c.value.number() for c in b.data["coords"]}
        if b.data["which"] == "0.1":
            self.stock["axis"] = b.data.get("tool_axis", "Z")
            self._stock_rect = False
            self.stock["min"] = tuple(vals.get(a, 0.0) for a in "XYZ")
        elif b.data["which"] == "0.2":
            mn = self.stock.get("min", (0.0, 0.0, 0.0))
            incr = {c.axis: c.incremental for c in b.data["coords"]}
            self.stock["max"] = tuple(
                (mn[i] + vals.get(a, 0.0)) if incr.get(a) else vals.get(a, 0.0) for i, a in enumerate("XYZ")
            )
            # gilt nur, wenn bei der Definition nichts verschoben/gedreht/geschwenkt ist
            self._stock_rect = not (self._shift_active or self._rot_active or self.plane)
        else:
            try:
                cyl = cylinder_stock(b.data.get("tool_axis", "Z"), b.data.get("extra", []),
                                     {c.axis: c.value.number() for c in b.data["coords"]})
            except ValueError as ex:
                raise TranslateError(str(ex))
            self.stock.clear()
            self.stock.update(cyl)
            self._stock_rect = False

    def _k_TOOL_CALL(self, b, **_):
        d = b.data
        words = []
        if "tool" in d:
            t = d["tool"]
            if isinstance(t, str):
                if t not in self.cfg.tool_names:
                    raise TranslateError(_t('Werkzeugname "{0}" nicht in der Werkzeugtabelle').format(t))
                t = self.cfg.tool_names[t]
            axis = d.get("axis", "Z")
            if axis != "Z":
                self._warn(b, _t('Werkzeugachse {0}: LinuxCNC-Längenkorrektur wirkt vorerst nur in Z').format(axis))
            self.tool_axis = axis
            if self.cfg.tool_db is not None:
                t0 = t
                t, notes = self.cfg.tool_db.resolve(t)
                for n in notes:
                    self._warn(b, _t(n).format(t0, t))
            td = self.cfg.tools.get(t, {})
            self.tool = Tool(t, td.get("R"), td.get("L", 0.0), td.get("ANGLE", 0.0), td.get("T_ANGLE", 0.0))
            if t not in self.cfg.tools and self.cfg.tools:
                self._warn(b, _t('T{0} steht nicht in der Werkzeugtabelle').format(t))
            elif td.get("L_EST"):
                self._warn(b, _t('T{0}: Länge nur gerechnet (Halter + Auskragung) – vor dem Fräsen messen')
                           .format(t))
            p = t
            if self.cfg.tool_pockets is not None:
                p = self.cfg.tool_pockets.get(t)
                if p is None:
                    raise TranslateError(_t('Werkzeug {0} ist keinem Platz zugeordnet (Tabellen → Platztabelle)')
                                         .format(t))
            name = str(td.get("NAME", "")).replace("(", "<").replace(")", ">")
            self._emit(b.line, f"T{p} M6" + (f" (Werkzeug {t} {name})" if p != t or name else ""))
            self.spindle = False  # Werkzeugwechsel hält die Spindel an
            self._emit(b.line, f"{PLANE[axis][2]} G43 H{p}")
            self.pos = {a: None for a in self.pos}
        if "dl" in d:
            txt, _ = self._value(d["dl"])
            self._emit(b.line, f"G43.2 Z{txt}")
        if "dr" in d:
            n = d["dr"].number()
            if n is None:
                raise TranslateError(_t("DR mit Q-Parameter wird noch nicht unterstützt"))
            self.tool_dr = n
            if self.tool.radius is not None:
                self.tool.radius += n
        if "s" in d:
            words.append("S" + self._value(d["s"])[0])
        if "f" in d:
            ftxt = self._value(d["f"])[0]
            self._emit(b.line, f"#<_cyclo_fauto> = {ftxt}")
            self.tool_feed = "#<_cyclo_fauto>"
            self.tool.feed = "#<_cyclo_fauto>"
            words.append("F" + ftxt)
            self.feed_text = ftxt
        if words:
            self._emit(b.line, " ".join(words))

    def _k_WMAT(self, b, **_):
        # Werkstoff: nur für die Schnittdaten beim Programmieren; im G-Code als Kommentar
        self._emit(b.line, f"(Werkstoff {b.data['material'].replace('(', '<').replace(')', '>')})")

    def _k_TOOL_DEF(self, b, **_):
        self._warn(b, "TOOL DEF (Werkzeug vorbereiten) wird ignoriert")

    def _k_QFORMULA(self, b, **_):
        target = q_name(b.data["target"])
        txt, _ = translate_expr(b.data["expr"])
        self._emit(b.line, f"{target} = [{txt}]")

    def _k_STOP(self, b, **_):
        self._emit_m(b, b.data.get("m", []), before=True)
        self._emit(b.line, "M0")
        self._emit_m(b, b.data.get("m", []), before=False)

    def _k_M(self, b, **_):
        self._emit_m(b, b.data["m"], before=True)
        self._emit_m(b, b.data["m"], before=False)

    def _k_TCPM(self, b, **_):
        self._emit(b.line, self.cfg.m128 if b.data["on"] else self.cfg.m129)
        self.tcp = bool(b.data["on"])
        self.plane_tcp = False

    # ------------------------------------------------------------ PLANE
    def _pv(self, b, name: str, default: str = "0") -> str:
        v = b.data["values"].get(name)
        return self._value(v)[0] if v is not None else default

    def _k_PLANE(self, b, **_):
        """PLANE -> LinuxCNC Tilted Work Plane (G68.2/G68.4/G69) und Orientierung (G53.x).

        Abbildung: SPATIAL -> G68.2 P1 Q123 (Raumwinkel um feste Achsen), EULER -> G68.2 P0 Q313,
        VECTOR/POINTS/PROJECTED -> G68.2 P3 (Basis- und Normalenvektor), RELATIV -> G68.4 P1,
        AXIAL -> G68.2 P1 mit dem Achswinkel als Raumwinkel (Vorzeichen je Maschine, axial_signs).
        MOVE -> G53.6 (Werkzeugspitze bleibt), TURN -> G53.1 (nur Drehachsen), STAY -> G53.2
        (Lösung in Q120..Q122, Positionieren im Programm). SEQ+/- -> P1/P2, TABLE ROT -> Q1.
        """
        d = b.data
        mode = d["mode"]
        line = b.line
        if self.comp != "R0":
            raise TranslateError(_t("PLANE bei aktiver Radiuskorrektur nicht erlaubt (erst R0)"))
        if d.get("dist") is not None:
            self._warn(b, _t("PLANE: DIST wird ignoriert (Drehpunkt ist die Werkzeugspitze)"))
        mb = d.get("mb")
        if mb == "MAX":
            self._emit(line, "G53 G0 Z0 (MB MAX)")
        elif mb is not None:
            txt, val = self._value(mb)
            if val is None or val != 0:
                self._emit(line, f"G91 G0 Z{txt} (MB)")
                self._emit(line, "G90")
        if mode == "RESET":
            if self.plane_shift:
                self.plane_shift = False
            self._emit(line, "G69")
            self.plane = False
            zero = "G0 " + " ".join(f"{a}0" for a in self.cfg.rotary_axes)
            if d.get("pos") == "MOVE":  # Drehachsen auf 0, Werkzeugspitze bleibt (TCP)
                if not self.tcp:
                    self._emit(line, self.cfg.m128)
                    self.tcp = self.plane_tcp = True
                self._emit(line, zero)
            if self.plane_tcp:
                self._emit(line, self.cfg.m129)
                self.tcp = self.plane_tcp = False
            if d.get("pos") == "TURN":  # nur die Drehachsen drehen (Gelenke, ohne TCP)
                if self.tcp:
                    self._emit(line, self.cfg.m129)
                self._emit(line, zero)
                if self.tcp:
                    self._emit(line, self.cfg.m128)
            self.pos = {a: None for a in self.pos}
            return
        if self.plane_shift:
            self._emit(line, "G52 X0 Y0 Z0 (Nullpunkt in der Ebene vor neuer Ebene aufheben)")
            self._warn(b, "TRANS DATUM in der geschwenkten Ebene wird vor dem neuen PLANE aufgehoben")
            self.plane_shift = False
        if not self.tcp:
            # Die Ebene braucht die TCP-Kinematik: Positionen sind Werkzeugspitze in der Ebene
            self._emit(line, self.cfg.m128)
            self.tcp = self.plane_tcp = True
        v = lambda n, dflt="0": self._pv(b, n, dflt)  # noqa: E731
        if mode == "SPATIAL":
            self._emit(line, f"G68.2 P1 Q123 I{v('SPA')} J{v('SPB')} K{v('SPC')}")
        elif mode == "EULER":
            self._emit(line, f"G68.2 P0 Q313 I{v('EULPR')} J{v('EULNU')} K{v('EULROT')}")
        elif mode == "RELATIV":
            (name, val), = d["values"].items()
            ang = self._value(val)[0]
            ijk = {"SPA": f"I{ang} J0 K0", "SPB": f"I0 J{ang} K0", "SPC": f"I0 J0 K{ang}"}[name]
            self._emit(line, f"{'G68.4' if self.plane else 'G68.2'} P1 Q123 {ijk}")
        elif mode == "VECTOR":
            # Die Normale gilt, der Basisvektor wird in die Ebene projiziert
            vals = d["values"]
            nums = {k: vals[k].number() for k in PLANE_WORDS["VECTOR"]}
            if all(x is not None for x in nums.values()):
                bv = [nums["BX"], nums["BY"], nums["BZ"]]
                nv = [nums["NX"], nums["NY"], nums["NZ"]]
                nn = sum(x * x for x in nv)
                if nn < 1e-12:
                    raise TranslateError("PLANE VECTOR: Normalenvektor ist null")
                k = sum(bv[i] * nv[i] for i in range(3)) / nn
                bx, by, bz = (_fmt(round(bv[i] - k * nv[i], 6)) for i in range(3))
            else:
                k = (f"[[{v('BX')}*{v('NX')}+{v('BY')}*{v('NY')}+{v('BZ')}*{v('NZ')}]"
                     f"/[{v('NX')}*{v('NX')}+{v('NY')}*{v('NY')}+{v('NZ')}*{v('NZ')}]]")
                bx, by, bz = (f"[{v('B' + c)}-{k}*{v('N' + c)}]" for c in "XYZ")
            self._emit(line, f"G68.2 P3 Q1 I{bx} J{by} K{bz}")
            self._emit(line, f"G68.2 P3 Q2 I{v('NX')} J{v('NY')} K{v('NZ')}")
        elif mode == "POINTS":
            # X-Richtung P1->P2, Normale (P2-P1) x (P3-P1); Ursprung bleibt der aktuelle Nullpunkt
            a = [f"[{v('P2' + c)}-{v('P1' + c)}]" for c in "XYZ"]
            c3 = [f"[{v('P3' + c)}-{v('P1' + c)}]" for c in "XYZ"]
            n = [f"[{a[1]}*{c3[2]}-{a[2]}*{c3[1]}]", f"[{a[2]}*{c3[0]}-{a[0]}*{c3[2]}]",
                 f"[{a[0]}*{c3[1]}-{a[1]}*{c3[0]}]"]
            self._emit(line, f"G68.2 P3 Q1 I{a[0]} J{a[1]} K{a[2]}")
            self._emit(line, f"G68.2 P3 Q2 I{n[0]} J{n[1]} K{n[2]}")
        elif mode == "PROJECTED":
            # X' ~ (1, 0, -tan PROPR), Y' ~ (0, 1, tan PROMIN), Normale = X' x Y'
            pr, pm, rot = v("PROPR"), v("PROMIN"), v("PROROT")
            rw = f" R{rot}" if rot not in ("0", "+0") else ""
            self._emit(line, f"G68.2 P3 Q1 I1 J0 K[-TAN[{pr}]]{rw}")
            self._emit(line, f"G68.2 P3 Q2 I[TAN[{pr}]] J[-TAN[{pm}]] K1")
        elif mode == "AXIAL":
            ang = {"A": "0", "B": "0", "C": "0"}
            for ax, val in d["values"].items():
                i = self.cfg.axial_signs.find(ax)
                sign = self.cfg.axial_signs[i + 1] if i >= 0 else "+"
                txt = self._value(val)[0]
                ang[ax] = txt if sign == "+" else (f"[-{txt}]" if not txt.startswith("-") else txt[1:])
            self._emit(line, f"G68.2 P1 Q123 I{ang['A']} J{ang['B']} K{ang['C']}")
        self.plane = True
        pos = d["pos"]
        pw = f" P{1 if d['seq'] > 0 else 2}" if d.get("seq") else ""
        qw = " Q1" if d.get("rot") == "TABLE" else ""
        if pos == "MOVE":
            self._emit(line, f"G53.6{pw}{qw}")
        elif pos == "TURN":
            self._emit(line, f"G53.1{pw}{qw}")
        else:
            self._emit(line, f"G53.2{pw}{qw}")
            for q, ax in ((120, "a"), (121, "b"), (122, "c")):
                self._emit(line, f"#<_q{q}> = #<_orient_{ax}>")
        self.pos = {a: None for a in self.pos}

    def _k_CALL_PGM(self, b, **_):
        name = re.sub(r"\.h$", "", b.data["path"].split("/")[-1], flags=re.I)
        self._warn(b, "CALL PGM: aufgerufenes Programm muss als <name>.ngc im SUBROUTINE_PATH liegen")
        self._emit(b.line, f"o<{name.lower()}> call")
        self.pos = {a: None for a in self.pos}

    def _k_CALL_LBL(self, b, sub_labels, rep_starts, **_):
        key = self._label_key(b.data["label"])
        if key in getattr(self, "_open_reps", {}):
            o = self._open_reps.pop(key)
            self._emit(b.line, f"o{o} endrepeat")
        elif key in sub_labels:
            if self._inline_depth >= 16:
                raise TranslateError(_t("Unterprogramme zu tief verschachtelt (Rekursion?)"))
            rep = b.data["rep"]
            o = None
            if rep:
                o = self._onum()
                self._warn(b, "CALL LBL mit REP auf ein Unterprogramm: wird REP-mal aufgerufen")
                self._emit(b.line, f"o{o} repeat [{rep}]")
                self.pos = {a: None for a in self.pos}
            self._inline_depth += 1
            try:
                for x in self._sub_bodies.get(key, []):
                    self._block(x, self._all_blocks, sub_labels, rep_starts)
            finally:
                self._inline_depth -= 1
            if o is not None:
                self._emit(b.line, f"o{o} endrepeat")
                self.pos = {a: None for a in self.pos}
            return
        else:
            raise TranslateError(_t('LBL {0} nicht gefunden').format(b.data['label']))
        self.pos = {a: None for a in self.pos}

    # ------------------------------------------------------------ Zyklen
    def _k_CYCL_DEF(self, b, **_):
        num = b.data["cycle"]
        sub = b.data["sub"]
        head = b.data["head"]
        cyc = REGISTRY.get(num)
        if num == 14:
            if sub == 1:
                labels = re.findall(r'\d+|"[^"]+"', head.replace("KONTURLABEL", ""))
                self.sl_contour = [int(x) if x.isdigit() else x.strip('"') for x in labels]
            return
        if num in (8, 9, 10, 11, 12, 13, 26, 32):
            return self._def_active(b, num, sub, head)
        if cyc is None:
            raise TranslateError(_t('Zyklus {0} ist nicht hinterlegt').format(num))
        params = b.data["params"]
        values = P()
        for p in cyc.params:
            v = params.get(p.q)
            if p.mode == "text":
                values[p.q] = v.text.strip('"') if v is not None else ""
                continue
            if v is None:
                self._warn(b, _t('Q{0} fehlt, Vorgabewert {1:g} verwendet').format(p.q, p.default))
                txt, val = _fmt(p.default), p.default
            elif v.text.upper().endswith("PREDEF"):
                txt, val = _fmt(p.default), p.default
            elif v.text.upper().endswith("FAUTO"):
                if not self.tool_feed:
                    raise TranslateError(f"Q{p.q}=FAUTO ohne F im TOOL CALL")
                txt = val = self.tool_feed
            elif v.text.upper().endswith("FMAX"):
                txt, val = "99999", 99999.0
            else:
                txt, val = self._value(v)
                if val is None:
                    val = ("Q", txt)  # Laufzeitwert (Q-Parameter)
            self._emit(b.line, f"#<_q{p.q}> = {txt}")
            values[p.q] = val
        b.data["values"] = values
        if num == 20:
            self.sl_data = b
            return
        from .pocket import BOUNDARIES, FIGURES

        if num == 270:
            self.ct_data = values
            return
        if num == 271:
            self.ocm_data, self.ocm_figure = values, None
            return
        if num in FIGURES:  # Figur definiert die Konturdaten neu und hebt 271 auf
            self.ocm_data, self.ocm_figure = values, (num, values)
            return
        if num in BOUNDARIES:
            self.ocm_boundary = (num, values)
            return
        if num in (220, 221):
            return self._pattern_cycle(b, num, values)
        if num == 247:
            n = values.get(339)
            if not isinstance(n, float):
                raise TranslateError(_t("Q339 muss eine Zahl sein"))
            # Bezugspunkt-Nummer = Zeile der Bezugspunkttabelle: 0 -> G54 … 8 -> G59.3
            codes = ["G54", "G55", "G56", "G57", "G58", "G59", "G59.1", "G59.2", "G59.3"]
            idx = int(n)
            if not 0 <= idx < len(codes):
                raise TranslateError(_t("Bezugspunkt 0…8 (LinuxCNC G54…G59.3)"))
            self._emit(b.line, codes[idx])
            self._stock_rect = False  # anderer Bezugspunkt: Lage der BLK FORM dazu unbekannt
            return
        if num == 2028:
            return self._home_cycle(b, values)
        if cyc.call_active:
            self.active_cycle = b

    def _home_cycle(self, b, values):
        """2028 GRUNDSTELLUNG: wie LinuxCNC G28/G30 – erst Z, dann (wahlweise) X/Y und Drehachsen auf die
        gespeicherte Position (#5161… bzw. #5181…, Maschinenkoordinaten). G91 mit 0 = ohne Zwischenpunkt."""
        pos, axes = values.get(596, 0.0), values.get(597, 1.0)
        if not isinstance(pos, float) or not isinstance(axes, float):
            raise TranslateError(_t("Q596/Q597 müssen Zahlen sein"))
        g = "G30" if int(pos) == 1 else "G28"
        if self.comp != "R0":
            raise TranslateError(_t("Grundstellung bei aktiver Radiuskorrektur nicht erlaubt (erst R0)"))
        self._emit(b.line, f"G91 {g} Z0")
        if int(axes) >= 1:
            self._emit(b.line, f"{g} X0 Y0")
        if int(axes) >= 2:
            rot = "".join(f" {a}0" for a in self.cfg.rotary_axes.upper() if a in "ABC")
            if rot:
                self._emit(b.line, f"{g}{rot}")
        self._emit(b.line, "G90")

    def _def_active(self, b, num, sub, head):
        """Koordinatenumrechnung und Sonderzyklen mit eigener Satzsyntax."""
        if sub in (None, 0):
            return
        h = head.upper()
        if num == 9:
            m = re.search(r"([\d.]+)", h)
            self._emit(b.line, f"G4 P{m.group(1) if m else 0}")
        elif num == 10:
            m = re.search(r"ROT\s*([-+]?[\d.]+)", h)
            ang = float(m.group(1)) if m else 0.0
            self.used_rotation = ang != 0 or self.used_rotation
            self._rot_active = ang != 0
            self._emit(b.line, f"G10 L2 P0 R{_fmt(ang)}")
            self._warn(b, _t("Drehung über G10 L2 R: wirkt um den Nullpunkt des aktiven Bezugspunkts"))
        elif num == 13:
            m = re.search(r"([-+]?[\d.]+)", h)
            self._emit(b.line, f"M19 R{m.group(1) if m else 0}")
        elif num == 32:
            m = re.search(r"T\s*([\d.]+)", h)
            self._emit(b.line, f"G64 P{m.group(1)}" if m else "G64")
        elif num == 12:
            m = re.search(r'PGM\s+"?([^"\s]+)"?', head, re.I)
            if m:
                name = re.sub(r"\.h$", "", m.group(1).replace("\\", "/").split("/")[-1].split(":")[-1], flags=re.I)
                self.active_cycle = b
                b.data["pgm"] = name.lower()
        elif num in (8, 11, 26):
            self._k_xform(b, num, head)
        else:
            raise TranslateError(_t('Zyklus {0}: noch nicht umgesetzt').format(num))

    def _tool_for_cycle(self):
        return self.tool

    def _check_spindle(self, b):
        if self.spindle is False:
            self._warn(b, _t("Spindel steht: nach TOOL CALL bzw. M5 fehlt M3/M4"))
            self.spindle = None  # je Abschnitt nur einmal warnen

    def _call_cycle(self, b, override=None):
        if self.active_cycle is None:
            raise TranslateError("Zyklusaufruf ohne vorherige CYCL DEF")
        self._check_spindle(b)
        d = self.active_cycle.data
        num = d["cycle"]
        if self.comp != "R0":
            raise TranslateError(_t("Zyklusaufruf mit aktiver Radiuskorrektur RL/RR nicht erlaubt"))
        if num == 12:
            self._emit(b.line, f"o<{d['pgm']}> call")
            self.pos = {a: None for a in self.pos}
            return
        impl = IMPLEMENTED.get(num)
        if num in (21, 22, 23, 24, 25, 275):
            return self._call_sl(b, num, d)
        if num in (272, 273, 274, 277):
            return self._call_ocm(b, num, d)
        if impl == "ngc":
            fz = self._f("Z")
            if abs(fz - 1.0) > 1e-12:
                # Zyklus 200 rechnet zur Laufzeit in Z: Höhen und Tiefen hier umrechnen
                if fz < 0:
                    raise TranslateError(_t('Zyklus {0}: Spiegeln der Werkzeugachse nicht möglich').format(num))
                vals = dict(d["values"])
                vals.update(override or {})
                if any(isinstance(vals.get(q), tuple) for q in (200, 201, 202, 203, 204)):
                    raise TranslateError(_t('Zyklus {0}: Maßfaktor mit Q-Parametern im Zyklus nicht möglich').format(num))
                override = {q: float(vals.get(q, 0.0)) * fz for q in (200, 201, 202, 204)}
                override[203] = self._t("Z", float(vals.get(203, 0.0)))
            if override:
                for q, v in override.items():
                    self._emit(b.line, f"#<_q{q}> = {_fmt(v)}")
            self._emit(b.line, f"o<cyclo_cycl{num}> call")
            self._used_cycles.add(num)
        elif impl == "python":
            values = P(d["values"])
            if override:
                values.update(override)
            bad = [q for q, v in values.items() if isinstance(v, tuple)]
            if bad:
                raise TranslateError(_t('Zyklus {0}: Q-Parameter als Zyklusparameter (Q{1}) werden noch nicht unterstützt').format(num, bad[0]))
            tool = self._tool_for_cycle()
            xf = self._cycle_xf()
            if xf and tool.radius:
                # Bahn wird skaliert, der Werkzeugradius nicht: vorher durch den Faktor teilen
                k = self._rscale(b)
                tool = dataclasses.replace(tool, radius=tool.radius / k)
            key = (id(self.active_cycle), tool.number, tool.radius, tuple(sorted((override or {}).items())),
                   tuple(sorted((xf or {}).items())))
            name = self._gen_cache.get(key)
            if name is None:
                name = f"cyc{num}_{len(self._gen_cache) + 1}"
                try:
                    lines, warns = generate(num, values, tool, name, xf)
                except CycleError as e:
                    raise TranslateError(_t('Zyklus {0}: {1}').format(num, e))
                for w in warns:
                    self._warn(b, _t('Zyklus {0}: {1}').format(num, w))
                self._gen_subs += [_t('(Zyklus {0} {1}, berechnet)').format(num, REGISTRY[num].name)] + lines
                self._gen_cache[key] = name
            self._emit(b.line, f"o<{name}> call")
        else:
            raise TranslateError(_t('Zyklus {0} {1}: Bahnberechnung folgt (siehe Roadmap)').format(num, REGISTRY[num].name))
        self.pos = {a: None for a in self.pos}

    def _call_sl(self, b, num, d):
        from .contour import ContourError, contour_from_blocks, find_label_blocks
        from .cyclegen import Emit
        from .slcycles import contour_train, sl_cycle

        if self.ct_data is not None and any(isinstance(v, tuple) for v in self.ct_data.values()):
            raise TranslateError(_t("Zyklus 270: Q-Parameter als Zyklusparameter noch nicht unterstützt"))
        if not self.sl_contour:
            raise TranslateError(_t('Zyklus {0}: Zyklus 14 KONTUR fehlt').format(num))
        if num not in (25, 275) and self.sl_data is None:
            raise TranslateError(_t('Zyklus {0}: Zyklus 20 KONTUR-DATEN fehlt').format(num))
        values = P(d["values"])
        d20 = P(self.sl_data.data["values"]) if self.sl_data else P()
        for src in (values, d20):
            bad = [q for q, v in src.items() if isinstance(v, tuple)]
            if bad:
                raise TranslateError(_t('Zyklus {0}: Q-Parameter als Zyklusparameter (Q{1}) noch nicht unterstützt').format(num, bad[0]))
        xf = self._cycle_xf()
        ct = P(self.ct_data) if self.ct_data is not None else None
        key = ("sl", id(self.active_cycle), id(self.sl_data), tuple(self.sl_contour), self.tool.number, self.tool.radius,
               self.tool.angle, tuple(sorted((xf or {}).items())), tuple(sorted(ct.items())) if ct else None)
        name = self._gen_cache.get(key)
        if name is None:
            name = f"cyc{num}_{len(self._gen_cache) + 1}"
            try:
                contours = [contour_from_blocks(lab, find_label_blocks(self._all_blocks, lab)) for lab in self.sl_contour]
                e = Emit(rel=False)
                tool = self.tool
                if xf:
                    for k, v in xf.items():
                        setattr(e, k, v)
                    if tool.radius:
                        tool = dataclasses.replace(tool, radius=tool.radius / self._rscale(b))
                e.begin(name)
                if num == 25:
                    contour_train(values, contours, tool, e, ct)
                elif num == 275:
                    from .slot275 import trochoid_slot
                    trochoid_slot(values, contours, tool, e, ct)
                else:
                    sl_cycle(num, values, d20, contours, tool, self.cfg.tools, e)
                e.end(name)
            except (ContourError, CycleError) as ex:
                raise TranslateError(_t('Zyklus {0}: {1}').format(num, ex))
            for w in e.warn:
                self._warn(b, _t('Zyklus {0}: {1}').format(num, w))
            self._gen_subs += [_t('(Zyklus {0} {1}, berechnet)').format(num, REGISTRY[num].name)] + e.lines
            self._gen_cache[key] = name
        self._emit(b.line, f"o<{name}> call")
        self.pos = {a: None for a in self.pos}

    def _call_ocm(self, b, num, d):
        from .contour import ContourError, contour_from_blocks, find_label_blocks
        from .cyclegen import Emit
        from .pocket import boundary_polygon, figure_polygon, ocm_cycle, region_from_polys
        from .slcycles import region

        if self.ocm_data is None:
            raise TranslateError(_t('Zyklus {0}: zuerst 271 KT DATEN oder eine Figur 127x definieren').format(num))
        values = P(d["values"])
        data = P(self.ocm_data)
        for src in (values, data):
            bad = [q for q, v in src.items() if isinstance(v, tuple)]
            if bad:
                raise TranslateError(_t('Zyklus {0}: Q-Parameter als Zyklusparameter (Q{1}) noch nicht unterstützt').format(num, bad[0]))
        xf = self._cycle_xf()
        tool = self.tool
        try:
            if self.ocm_figure:
                u, v, _ = PLANE[self.tool_axis]
                px, py = self.pos.get(u), self.pos.get(v)
                if px is None or py is None:
                    raise TranslateError(_t('Zyklus {0}: Figur braucht eine bekannte Position (ohne Q-Parameter)').format(num))
                fnum, fv = self.ocm_figure
                poly, center = figure_polygon(fnum, P(fv), px, py)
                ftype = int(P(fv).n(650, 0))
                bnd = None
                if self.ocm_boundary:
                    bnd = boundary_polygon(self.ocm_boundary[0], P(self.ocm_boundary[1]), *center)
                if ftype == 1:
                    if bnd is None:
                        raise TranslateError(_t('Zyklus {0}: Insel braucht eine Begrenzung (Zyklus 1281/1282)').format(num))
                    reg = region_from_polys([], [poly], bnd)
                    open_bnd = True
                elif ftype == 2:
                    reg, open_bnd = region_from_polys([poly], []), True
                else:
                    reg, open_bnd = region_from_polys([poly], []), False
                key_geo = ("fig", fnum, tuple(sorted(fv.items())), px, py,
                           tuple(sorted(self.ocm_boundary[1].items())) if self.ocm_boundary else None)
            else:
                if not self.sl_contour:
                    raise TranslateError(_t('Zyklus {0}: Zyklus 14 KONTUR fehlt').format(num))
                contours = [contour_from_blocks(lab, find_label_blocks(self._all_blocks, lab)) for lab in self.sl_contour]
                open_bnd = int(data.n(569, 0)) == 1
                if open_bnd:  # erste Kontur = offene Begrenzung, weitere Inseln/Taschen
                    first = contours[0].polyline()
                    reg = region_from_polys([c.polyline() for c in contours[1:] if c.is_pocket],
                                            [c.polyline() for c in contours[1:] if not c.is_pocket], first)
                else:
                    reg = region(contours)
                key_geo = ("sl", tuple(self.sl_contour), open_bnd)
        except (ContourError, CycleError) as ex:
            raise TranslateError(_t('Zyklus {0}: {1}').format(num, ex))
        if not reg:
            raise TranslateError(_t('Zyklus {0}: keine Bearbeitungsfläche (Begrenzung/Figur prüfen)').format(num))
        if xf and tool.radius:
            tool = dataclasses.replace(tool, radius=tool.radius / self._rscale(b))
        # Rohteil-Rechteck für offene Taschenseiten: nur, wenn die Zykluskoordinaten sicher im System der
        # BLK FORM liegen – nicht bei Spiegeln/Maßfaktor (xf), TRANS DATUM (G52), Drehung (Zyklus 10),
        # geschwenkter Ebene oder nach einem Bezugspunktwechsel. Sonst plant 272 wie für eine geschlossene Tasche.
        stock = None
        if (not xf and self._stock_rect and not self._shift_active and not self._rot_active and not self.plane
                and self.stock.get("min") and self.stock.get("max") and self.tool_axis == "Z"
                and self.stock.get("axis", "Z") == "Z"):
            stock = (self.stock["min"][0], self.stock["min"][1], self.stock["max"][0], self.stock["max"][1])
        key = ("ocm", num, id(self.active_cycle), key_geo, tuple(sorted(data.items())), tool.number, tool.radius,
               tool.angle, tool.t_angle, tuple(sorted((xf or {}).items())), stock)
        name = self._gen_cache.get(key)
        if name is None:
            name = f"cyc{num}_{len(self._gen_cache) + 1}"
            e = Emit(rel=False)
            for k, v in (xf or {}).items():
                setattr(e, k, v)
            e.begin(name)
            try:
                ocm_cycle(num, values, data, reg, tool, e, open_bnd, stock=stock)
            except CycleError as ex:
                raise TranslateError(_t('Zyklus {0}: {1}').format(num, ex))
            e.end(name)
            for w in e.warn:
                self._warn(b, _t('Zyklus {0}: {1}').format(num, w))
            self._gen_subs += [_t('(Zyklus {0} {1}, berechnet)').format(num, REGISTRY[num].name)] + e.lines
            self._gen_cache[key] = name
        self._emit(b.line, f"o<{name}> call")
        self.pos = {a: None for a in self.pos}

    def _cycle_heights(self):
        """Sicherheitshöhe des aktiven Zyklus (für Positionieren zwischen Musterpunkten)."""
        d = self.active_cycle.data if self.active_cycle else {}
        v = d.get("values") or {}
        try:
            surf = float(v.get(203, 0.0))
            safe = surf + float(v.get(200, 2.0))
            sec = surf + float(v.get(204, 0.0))
            return safe, max(safe, sec)
        except (TypeError, ValueError):
            return None, None

    def _pattern_cycle(self, b, num, v):
        """220 MUSTER KREIS / 221 MUSTER LINIEN: ruft den zuletzt definierten Zyklus je Punkt auf."""
        if self.active_cycle is None:
            raise TranslateError(_t('Zyklus {0}: zuerst einen Bearbeitungszyklus definieren').format(num))
        if any(isinstance(x, tuple) for x in v.values()):
            raise TranslateError(_t('Zyklus {0}: Q-Parameter als Musterparameter werden noch nicht unterstützt').format(num))
        pts = []
        if num == 220:
            n = int(v.get(241, 1))
            a0, a1, step = v.get(245, 0.0), v.get(246, 0.0), v.get(247, 0.0)
            if not step:
                step = (a1 - a0) / n if (a1 - a0) and abs(abs(a1 - a0) - 360) < 1e-6 else ((a1 - a0) / (n - 1) if n > 1 else 0)
                if a1 == a0:
                    step = 360.0 / n
            r = v.get(244, 0.0) / 2
            for i in range(n):
                a = math.radians(a0 + i * step)
                pts.append((v.get(216, 0.0) + r * math.cos(a), v.get(217, 0.0) + r * math.sin(a)))
            if v.get(365, 0):
                self._warn(b, _t("Q365=1 (Kreisbogen zwischen Punkten): es wird geradlinig verfahren"))
        else:
            rot = math.radians(v.get(224, 0.0))
            for j in range(int(v.get(243, 1))):
                cols = range(int(v.get(242, 1)))
                for i in (cols if j % 2 == 0 else reversed(cols)):
                    dx, dy = i * v.get(237, 0.0), j * v.get(238, 0.0)
                    pts.append((v.get(225, 0.0) + dx * math.cos(rot) - dy * math.sin(rot),
                                v.get(226, 0.0) + dx * math.sin(rot) + dy * math.cos(rot)))
        override = {200: v.get(200, 2.0), 203: v.get(203, 0.0), 204: v.get(204, 50.0)}
        safe = override[203] + override[200]
        sec = max(safe, override[203] + override[204])
        between = sec if v.get(301, 1) else safe
        self._emit(b.line, f"G0 Z{_fmt(self._t('Z', sec))}")
        for i, (x, y) in enumerate(pts):
            self._emit(b.line, f"G0 X{_fmt(self._t('X', x))} Y{_fmt(self._t('Y', y))}")
            self.pos["X"], self.pos["Y"] = x, y
            self._call_cycle(b, override)
            if i < len(pts) - 1 and between < sec:
                self._emit(b.line, f"G0 Z{_fmt(self._t('Z', between))}")
        self.pos = {a: None for a in self.pos}

    def _k_PATTERN(self, b, **_):
        self.pattern = b.data["points"]

    def _k_CYCL_CALL(self, b, **_):
        self._emit_m(b, b.data.get("m", []), before=True)
        if b.data.get("variant") == "PAT":
            if not self.pattern:
                raise TranslateError("CYCL CALL PAT ohne PATTERN DEF")
            safe, sec = self._cycle_heights()
            for x, y, z in self.pattern:
                if z:
                    self._warn(b, "Z im PATTERN DEF wird noch nicht berücksichtigt")
                if sec is not None:
                    self._emit(b.line, f"G0 Z{_fmt(self._t('Z', sec))}")
                self._emit(b.line, f"G0 X{_fmt(self._t('X', x))} Y{_fmt(self._t('Y', y))}")
                self.pos["X"], self.pos["Y"] = x, y
                self._call_cycle(b)
        else:
            self._call_cycle(b)
        self._emit_m(b, b.data.get("m", []), before=False)

    def _k_TRANS(self, b, **_):
        self._shift_active = not b.data.get("reset")
        if self.plane:
            self.plane_shift = not b.data.get("reset")
        if b.data.get("reset"):
            self._emit(b.line, "G52 X0 Y0 Z0")
        else:
            words = []
            for c in b.data["coords"]:
                txt, _ = self._value(c.value)
                words.append(f"{c.axis}{txt}")
            self._emit(b.line, "G52 " + " ".join(words))
        self.pos = {a: None for a in self.pos}

    # ------------------------------------------------------------ Spiegeln / Maßfaktor
    def _f(self, a: str) -> float:
        if a not in "XYZ":
            return 1.0
        return self.mirror[a] * self.scale * self.ascale[a]

    def _xf_active(self) -> bool:
        return any(abs(self._f(a) - 1.0) > 1e-12 or abs(self._k(a)) > 1e-12 for a in "XYZ")

    def _mirrored(self) -> bool:
        u, v, _ = PLANE[self.tool_axis]
        return self._f(u) * self._f(v) < 0

    def _k(self, a: str) -> float:
        """Verschiebung aus dem Streckzentrum (Zyklus 26): x' = f*x + k."""
        s = self.scale * self.ascale[a]
        return self.acenter[a] * (1.0 - s)

    def _t(self, a: str, v: float) -> float:
        """Programmkoordinate -> umgerechnet: erst Spiegeln am Nullpunkt, dann Maßfaktor
        (um das Zentrum CC von Zyklus 26, sonst um den Nullpunkt)."""
        if a not in "XYZ":
            return v
        return self._f(a) * v + self._k(a)

    def _tt(self, a: str, txt: str) -> str:
        f = self._f(a)
        if a not in "XYZ" or (abs(f - 1.0) < 1e-12 and abs(self._k(a)) < 1e-12):
            return txt
        k = self._k(a)
        core = f"{_fmt(f)}*{txt}"
        return f"[{core}]" if abs(k) < 1e-12 else f"[{core}+{_fmt(k)}]"

    def _rscale(self, b) -> float:
        """Faktor für Radien (CR, RND): nur bei gleichem Maßfaktor in der Ebene definiert."""
        u, v, _ = PLANE[self.tool_axis]
        fu, fv = abs(self._f(u)), abs(self._f(v))
        if abs(fu - fv) > 1e-9:
            raise TranslateError(_t("Kreise mit unterschiedlichem Maßfaktor je Achse (Zyklus 26) nicht möglich"))
        return fu

    def _cycle_xf(self) -> dict | None:
        if not self._xf_active():
            return None
        return {"fx": self._f("X"), "fy": self._f("Y"), "fz": self._f("Z"),
                "ox": self._k("X"), "oy": self._k("Y"), "oz": self._k("Z")}

    def _k_xform(self, b, num, head):
        """CYCL DEF 8.1 / 11.1 / 26.1 auswerten."""
        h = head.upper()
        if re.search(r"Q[LRS]?\d", h):
            raise TranslateError(_t('Zyklus {0}: Q-Parameter werden hier noch nicht unterstützt').format(num))
        if num == 8:
            axes = set(re.findall(r"\b([XYZUVWABC])\b", h))
            if self.tool_axis in axes:
                raise TranslateError(_t("Zyklus 8: die Werkzeugachse kann nicht gespiegelt werden"))
            self.mirror = {a: (-1.0 if a in axes else 1.0) for a in "XYZ"}
        elif num == 11:
            m = re.search(r"SCL\s*([-+]?[\d.]+)", h)
            f = float(m.group(1)) if m else 1.0
            if f <= 0:
                raise TranslateError(_t("Zyklus 11: Maßfaktor muss größer 0 sein"))
            self.scale = f
        else:  # 26
            fac = {a: 1.0 for a in "XYZ"}
            cen = {a: 0.0 for a in "XYZ"}
            for a, val in re.findall(r"(?<!C)\b([XYZ])\s*([-+]?[\d.]+)", h):
                fac[a] = float(val)
            for a, val in re.findall(r"CC([XYZ])\s*([-+]?[\d.]+)", h):
                cen[a] = float(val)
            if any(f <= 0 for f in fac.values()):
                raise TranslateError(_t("Zyklus 26: Faktoren müssen größer 0 sein"))
            self.ascale, self.acenter = fac, cen
        self.pos = {a: None for a in self.pos}
        if self._xf_active():
            self._emit(b.line, _t('(Spiegeln/Maßfaktor aktiv: X{0} Y{1} Z{2})').format(_fmt(self._f('X')), _fmt(self._f('Y')), _fmt(self._f('Z'))))

    # ------------------------------------------------------------ Bahn
    def _coord_words(self, b: Block, coords: list[Coord], update=True) -> tuple[list[str], dict]:
        words, newpos = [], {}
        for c in coords:
            txt, val = self._value(c.value)
            cur = self.pos.get(c.axis)
            if c.incremental:
                if val is not None and cur is not None:
                    v = cur + val
                    words.append(f"{c.axis}{_fmt(self._t(c.axis, v))}")
                    newpos[c.axis] = v
                else:
                    f = self._f(c.axis)
                    inc = txt if abs(f - 1) < 1e-12 else f"[{_fmt(f)}*{txt}]"
                    words.append(f"{c.axis}[#{5420 + AXIS_INDEX[c.axis]}+{inc}]")
                    newpos[c.axis] = None
            else:
                if val is not None:
                    words.append(f"{c.axis}{_fmt(self._t(c.axis, val))}")
                else:
                    words.append(f"{c.axis}{self._tt(c.axis, txt)}")
                newpos[c.axis] = val
        if update:
            self.pos.update(newpos)
        return words, newpos

    def _comp_word(self, b: Block) -> str:
        rc = b.data.get("radius_comp")
        if rc is None or rc == self.comp:
            return ""
        if rc in ("R+", "R-"):
            raise TranslateError(_t("R+/R- (Paraxiale Korrektur) wird nicht unterstützt"))
        prev, self.comp = self.comp, rc
        if rc == "R0":
            return "G40"
        g = "G41" if (rc == "RL") != self._mirrored() else "G42"  # Spiegeln tauscht die Seite
        if prev != "R0":
            raise TranslateError(_t("Wechsel RL<->RR ohne R0 dazwischen ist in LinuxCNC nicht möglich"))
        if self.tool_dr:
            return f"{g}.1 D[#5410+{_fmt(2 * self.tool_dr)}]"
        return g

    def _feed(self, b: Block) -> tuple[str, str]:
        """-> (Bewegungsart G0/G1, F-Wort)"""
        f = b.data.get("feed")
        if f == "FMAX":
            return "G0", ""
        if f == "FAUTO":
            if not self.tool_feed:
                raise TranslateError("FAUTO ohne F im TOOL CALL")
            self.feed_text = self.tool_feed
            self._check_spindle(b)
            return "G1", f"F{self.tool_feed}"
        if isinstance(f, Value):
            self.feed_text = self._value(f)[0]
            self._check_spindle(b)
            return "G1", f"F{self.feed_text}"
        self._check_spindle(b)
        return "G1", ""

    def _emit_m(self, b: Block, ms: list[int], before: bool):
        words = []
        for m in ms:
            at_end = m in M_AT_END
            if at_end == before:
                continue
            if m in (91, 92):
                continue  # wird an der Bewegung behandelt
            if m == 99:
                self._call_cycle(b)
            elif m == 30:
                pass  # Programmende -> M2 am Dateiende
            elif m == 13:
                words += ["M3", "M8"]
                self.spindle = True
            elif m == 14:
                words += ["M4", "M8"]
                self.spindle = True
            elif m == 128:
                words.append(self.cfg.m128)
                self.tcp, self.plane_tcp = True, False
            elif m == 129:
                words.append(self.cfg.m129)
                self.tcp, self.plane_tcp = False, False
            elif m in (126, 127):
                self._warn(b, f"M{m} (Rundachsen wegoptimiert) wird ignoriert")
            else:
                words.append(f"M{m}")
                if m in (3, 4):
                    self.spindle = True
                elif m == 5:
                    self.spindle = False
        if words:
            # LinuxCNC erlaubt nur je ein M aus derselben modalen Gruppe pro Zeile
            for w in words:
                self._emit(b.line, w)

    def _k_L(self, b, blocks, **_):
        ms = b.data.get("m", [])
        self._emit_m(b, ms, before=True)
        start = dict(self.pos)
        comp = self._comp_word(b)
        g, fw = self._feed(b)
        coords = b.data["coords"]
        words, _ = self._coord_words(b, coords)
        corner = self._lookahead_corner(b, blocks, start)
        if corner:
            # Endpunkt auf ersten Tangentialpunkt von RND/CHF verkürzen
            (t1u, t1v), arc = corner
            u, v, _ = PLANE[self.tool_axis]
            words = [w for w in words if w[0] not in (u, v)] + [f"{u}{_fmt(self._t(u, t1u))}",
                                                                 f"{v}{_fmt(self._t(v, t1v))}"]
            self.pending_corner = arc
        if not words and not comp:
            if not ms:
                self._warn(b, _t("L-Satz ohne Koordinaten"))
        else:
            prefix = "G53 " if 91 in ms else ""
            self._emit(b.line, " ".join(x for x in (prefix + g, comp, *words, fw) if x))
        self._emit_m(b, ms, before=False)

    def _k_CC(self, b, **_):
        u, v, _ = PLANE[self.tool_axis]
        coords = b.data["coords"]
        if not coords:
            if self.pos[u] is None or self.pos[v] is None:
                raise TranslateError(_t("CC ohne Koordinaten: letzte Position nicht bekannt"))
            self.cc = (self.pos[u], self.pos[v])
            return
        res = {}
        for c in coords:
            txt, val = self._value(c.value)
            base = self.cc[0 if c.axis == u else 1] if (self.cc and c.incremental) else None
            if c.incremental:
                if base is None or val is None:
                    raise TranslateError(_t("Inkrementaler Kreismittelpunkt nur mit bekanntem vorherigem CC"))
                val = base + val
            res[c.axis] = val if val is not None else txt
        # fehlende Achse: letzte Position
        cu = res.get(u, self.pos[u])
        cv = res.get(v, self.pos[v])
        if cu is None or cv is None:
            raise TranslateError(_t("CC: Mittelpunkt nicht vollständig bestimmbar"))
        self.cc = (cu, cv)

    def _k_C(self, b, **_):
        if self.cc is None:
            raise TranslateError(_t("C ohne vorheriges CC"))
        u, v, plane = PLANE[self.tool_axis]
        ms = b.data.get("m", [])
        self._emit_m(b, ms, before=True)
        su, sv = self.pos[u], self.pos[v]
        comp = self._comp_word(b)
        _, fw = self._feed(b)
        words, _ = self._coord_words(b, b.data["coords"])
        g = "G3" if (b.data["dir"] == "+") != self._mirrored() else "G2"
        if self._xf_active():
            self._rscale(b)
        iw = self._center_offset("I", self.cc[0], su, u)
        jw = self._center_offset("J", self.cc[1], sv, v)
        self._emit(b.line, " ".join(x for x in (g, comp, *words, iw, jw, fw) if x))
        self._emit_m(b, ms, before=False)

    def _center_offset(self, letter, center, start, axis):
        if isinstance(center, (int, float)) and start is not None:
            return f"{letter}{_fmt(self._f(axis) * (center - start))}"
        ctext = _fmt(self._t(axis, center)) if isinstance(center, (int, float)) else self._tt(axis, center)
        return f"{letter}[{ctext}-#{5420 + AXIS_INDEX[axis]}]"

    def _k_CR(self, b, **_):
        ms = b.data.get("m", [])
        self._emit_m(b, ms, before=True)
        comp = self._comp_word(b)
        _, fw = self._feed(b)
        words, _ = self._coord_words(b, b.data["coords"])
        g = "G3" if (b.data["dir"] == "+") != self._mirrored() else "G2"
        r, rv = self._value(b.data["radius"])
        if self._xf_active():
            k = self._rscale(b)
            r = _fmt(rv * k) if rv is not None else f"[{_fmt(k)}*{r}]"
        self._emit(b.line, " ".join(x for x in (g, comp, *words, f"R{r}", fw) if x))
        self._emit_m(b, ms, before=False)

    def _k_CT(self, b, **_):
        raise TranslateError(_t("CT (tangentialer Kreis) folgt mit dem Kontur-Modul"))

    # RND / CHF ------------------------------------------------------------
    def _lookahead_corner(self, b, blocks, start):
        # Satzindex über eine einmal je Satzliste gebaute Tabelle (vorher lineare Suche je Satz: O(n²))
        if getattr(self, "_idx_of", (None,))[0] is not blocks:
            self._idx_of = (blocks, {id(x): i for i, x in enumerate(blocks)})
        idx = self._idx_of[1].get(id(b))
        if idx is None or idx + 2 >= len(blocks):
            return None
        nxt = blocks[idx + 1]
        if nxt.kind not in ("RND", "CHF"):
            return None
        after = blocks[idx + 2]
        if after.kind != "L":
            raise TranslateError(_t('{0}: vorerst nur zwischen zwei Geraden (L) möglich').format(nxt.kind))
        u, v, _ = PLANE[self.tool_axis]
        p0 = (start[u], start[v])
        p1 = (self.pos[u], self.pos[v])
        if None in p0 or None in p1:
            raise TranslateError(_t('{0}: Positionen müssen bekannt sein (keine Q-Parameter)').format(nxt.kind))
        p2 = list(p1)
        for c in after.data["coords"]:
            if c.axis not in (u, v):
                continue
            val = c.value.number()
            if val is None:
                raise TranslateError(_t('{0}: Folgesatz mit Q-Parameter nicht unterstützt').format(nxt.kind))
            i = 0 if c.axis == u else 1
            p2[i] = p1[i] + val if c.incremental else val
        size = nxt.data["size"].number()
        if size is None:
            raise TranslateError(_t('{0}: Größe als Q-Parameter nicht unterstützt').format(nxt.kind))
        a = (p0[0] - p1[0], p0[1] - p1[1])
        c = (p2[0] - p1[0], p2[1] - p1[1])
        la, lc = math.hypot(*a), math.hypot(*c)
        if la < 1e-9 or lc < 1e-9:
            raise TranslateError(_t('{0}: Geraden ohne Länge').format(nxt.kind))
        ua, uc = (a[0] / la, a[1] / la), (c[0] / lc, c[1] / lc)
        cosang = max(-1.0, min(1.0, ua[0] * uc[0] + ua[1] * uc[1]))
        ang = math.acos(cosang)
        if ang < 1e-6 or abs(ang - math.pi) < 1e-6:
            raise TranslateError(_t('{0}: Geraden sind parallel').format(nxt.kind))
        d = size / math.tan(ang / 2) if nxt.kind == "RND" else size
        if d > la + 1e-9 or d > lc + 1e-9:
            raise TranslateError(_t('{0} {1:g} ist zu groß für die angrenzenden Geraden').format(nxt.kind, size))
        t1 = (p1[0] + ua[0] * d, p1[1] + ua[1] * d)
        t2 = (p1[0] + uc[0] * d, p1[1] + uc[1] * d)
        tu, tv = _fmt(self._t(u, t2[0])), _fmt(self._t(v, t2[1]))
        if nxt.kind == "RND":
            d1 = (-ua[0], -ua[1])
            cross = d1[0] * uc[1] - d1[1] * uc[0]
            g = "G3" if (cross > 0) != self._mirrored() else "G2"
            k = self._rscale(nxt) if self._xf_active() else 1.0
            seg = f"{g} {u}{tu} {v}{tv} R{_fmt(size * k)}"
        else:
            seg = f"G1 {u}{tu} {v}{tv}"
        self.pos[u], self.pos[v] = t1
        return t1, [seg, t2]

    def _corner(self, b):
        if not self.pending_corner:
            raise TranslateError(_t('{0} muss zwischen zwei Geraden stehen').format(b.kind))
        seg, t2 = self.pending_corner
        self.pending_corner = None
        f = b.data.get("feed")
        if isinstance(f, Value):
            seg += f" F{self._value(f)[0]}"
        self._emit(b.line, seg)
        u, v, _ = PLANE[self.tool_axis]
        self.pos[u], self.pos[v] = t2

    def _k_RND(self, b, **_):
        self._corner(b)

    def _k_CHF(self, b, **_):
        self._corner(b)


def translate(text: str, filename: str = "", config: TranslatorConfig | None = None) -> Result:
    return Translator(config).translate_text(text, filename)


def cylinder_stock(rot_axis: str, extra, center: dict | None = None) -> dict:
    """BLK FORM CYLINDER <Achse> R|D… L… [DIST…] [RI|DI…] [X… Y… Z…] -> Rohteil-Beschreibung.

    Die Achse geht durch den Nullpunkt (X/Y/Z-Angaben verschieben sie – Erweiterung von Cyclo).
    Entlang der Achse reicht der Zylinder von DIST−L bis DIST (Standard DIST = 0, also bis zum Nullpunkt)."""
    rot = (rot_axis or "Z").upper()
    vals = {}
    for tok in extra or []:
        m = re.fullmatch(r"(DIST|RI|DI|R|D|L)([-+]?\d*\.?\d+)", str(tok).upper())
        if not m:
            raise ValueError(_t("BLK FORM CYLINDER: unbekanntes Wort {0}").format(tok))
        vals[m.group(1)] = float(m.group(2))
    r = vals["R"] if "R" in vals else vals.get("D", 0.0) / 2
    ri = vals["RI"] if "RI" in vals else vals.get("DI", 0.0) / 2
    length = vals.get("L", 0.0)
    if r <= 0 or length <= 0:
        raise ValueError(_t("BLK FORM CYLINDER: Radius/Durchmesser und Länge L angeben"))
    if ri >= r:
        raise ValueError(_t("BLK FORM CYLINDER: Innenradius muss kleiner als der Außenradius sein"))
    dist = vals.get("DIST", 0.0)
    ax = "XYZ".index(rot)
    c = [float((center or {}).get(a, 0.0)) for a in "XYZ"]
    mn, mx = [0.0] * 3, [0.0] * 3
    for i in range(3):
        if i == ax:
            mn[i], mx[i] = dist - length, dist
        else:
            mn[i], mx[i] = c[i] - r, c[i] + r
    c[ax] = dist - length / 2
    return {"min": tuple(mn), "max": tuple(mx), "axis": "Z", "shape": "cylinder", "rot": rot,
            "r": r, "ri": ri, "center": tuple(c)}


_BLK_RX = re.compile(r"BLK\s+FORM\s+(0\.1|0\.2)\s*(?:[XYZ]\s+)?((?:\s*I?[XYZ][-+]?\d*\.?\d+)+)", re.I)
_BLK_COORD = re.compile(r"(I?)([XYZ])([-+]?\d*\.?\d+)", re.I)


def preview_stock(text: str) -> dict | None:
    """Rohteil (BLK FORM 0.1/0.2) schnell aus dem Programmtext lesen – ohne Übersetzung.
    Für die Anzeige, während der freie Texteditor aktiv ist. -> {"min", "max", "axis"} oder None"""
    mn = mx = None
    axis = "Z"
    for line in text.splitlines()[:60]:
        mc = re.search(r"BLK\s+FORM\s+CYLINDER\s+([XYZ])\s+(.*)", line, re.I)
        if mc:
            toks = mc.group(2).split()
            extra = [t for t in toks if not re.fullmatch(r"[XYZ][-+]?\d*\.?\d+", t, re.I)]
            cen = {t[0].upper(): float(t[1:]) for t in toks if re.fullmatch(r"[XYZ][-+]?\d*\.?\d+", t, re.I)}
            try:
                return cylinder_stock(mc.group(1), extra, cen)
            except ValueError:
                return None
        m = _BLK_RX.search(line)
        if not m:
            continue
        head = re.search(r"BLK\s+FORM\s+0\.1\s+([XYZ])\b", line, re.I)
        if head:
            axis = head.group(1).upper()
        vals, incr = {}, {}
        body = m.group(2)
        for i_, a, v in _BLK_COORD.findall(body):
            vals[a.upper()] = float(v)
            incr[a.upper()] = bool(i_)
        if m.group(1) == "0.1":
            mn = tuple(vals.get(a, 0.0) for a in "XYZ")
        else:
            base = mn or (0.0, 0.0, 0.0)
            mx = tuple((base[k] + vals.get(a, 0.0)) if incr.get(a) else vals.get(a, 0.0)
                       for k, a in enumerate("XYZ"))
    if mn is None or mx is None:
        return None
    return {"min": mn, "max": mx, "axis": axis}
