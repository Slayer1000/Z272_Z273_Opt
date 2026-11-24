"""Zyklen mit Bahnberechnung: Geometrie und Abgleich mit dem Original-Interpreter."""

import math
import re
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cyclo import NGC_DIR  # noqa: E402
from cyclo.dialog import TranslatorConfig, translate  # noqa: E402
from cyclo.sim.tracer import Tracer  # noqa: E402

HERE = os.path.dirname(__file__)
TOOLS = {1: {"R": 3}, 2: {"R": 5, "ANGLE": 3}, 3: {"R": 10}, 4: {"R": 5, "T_ANGLE": 90}, 5: {"R": 4}, 6: {"R": 4}}
LENGTHS = {1: 40, 2: 50, 3: 60, 4: 45, 5: 55, 6: 50}


RADII = {k: v["R"] for k, v in TOOLS.items()}


def run(text):
    r = translate(text, "t.h", TranslatorConfig(tools=TOOLS))
    assert not r.errors, [str(e) for e in r.errors]
    t = Tracer([NGC_DIR], tool_lengths=LENGTHS, tool_radii=RADII, work_offset=(0, 0, 0)).trace_text(r.gcode)
    assert not t.errors, t.errors
    return r, t


def cyc(num, name, params, call="L X+0 Y+0 FMAX M99", tool=2):
    body = " ~\n".join(f"  Q{q}={v:+g} ;X" for q, v in params.items())
    return (f"0 BEGIN PGM T MM\n1 TOOL CALL {tool} Z S3000 F500\n2 L Z+100 R0 FMAX M3\n"
            f"3 CYCL DEF {num} {name} ~\n{body}\n4 {call}\n5 L Z+100 FMAX M30\n6 END PGM T MM\n")


POCKET = {215: 0, 218: 60, 219: 30, 220: 5, 368: 0, 224: 0, 367: 0, 207: 800, 351: 1, 201: -10, 202: 5,
          369: 0, 206: 150, 338: 0, 200: 2, 203: 0, 204: 50, 370: 1, 366: 0, 385: 500, 439: 0}


def feed_pts(t, zmax=-0.001):
    return [p for m in t.moves if m.kind != "rapid" for p in m.points if p[2] < zmax]


def test_rect_pocket_wall_on_size():
    r, t = run(cyc(251, "RECHTECKTASCHE", POCKET, "L X+100 Y+50 FMAX M99"))
    pts = feed_pts(t)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    # Werkzeugmitte bleibt um R=5 innerhalb der Taschenwand
    assert max(xs) == pytest.approx(100 + 30 - 5, abs=1e-3)
    assert min(xs) == pytest.approx(100 - 30 + 5, abs=1e-3)
    assert max(ys) == pytest.approx(50 + 15 - 5, abs=1e-3)
    assert min(p[2] for p in pts) == pytest.approx(-10, abs=1e-6)


def test_rect_pocket_rotated_and_corner_position():
    p = {**POCKET, 224: 90, 367: 1}
    r, t = run(cyc(251, "RECHTECKTASCHE", p, "L X+0 Y+0 FMAX M99"))
    pts = feed_pts(t)
    # Q367=1: Werkzeugposition = linke untere Ecke, um 90° gedreht -> Tasche liegt bei X<0, Y>0
    assert max(q[0] for q in pts) == pytest.approx(-5, abs=1e-3)
    assert min(q[0] for q in pts) == pytest.approx(-25, abs=1e-3)
    assert min(q[1] for q in pts) == pytest.approx(5, abs=1e-3)
    assert max(q[1] for q in pts) == pytest.approx(55, abs=1e-3)


def test_circular_pocket_radius():
    p = {215: 0, 223: 40, 368: 0, 207: 800, 351: 1, 201: -6, 202: 3, 369: 0, 206: 150, 338: 0, 200: 2,
         203: 0, 204: 50, 370: 1, 366: 0, 385: 500, 439: 0}
    r, t = run(cyc(252, "KREISTASCHE", p, "L X+10 Y+10 FMAX M99"))
    rmax = max(math.hypot(q[0] - 10, q[1] - 10) for q in feed_pts(t))
    assert rmax == pytest.approx(20 - 5, abs=0.01)


def test_stud_stays_outside():
    p = {218: 40, 424: 50, 219: 30, 425: 40, 220: 0, 368: 0, 224: 0, 367: 0, 207: 800, 351: 1, 201: -8,
         202: 4, 206: 150, 200: 2, 203: 0, 204: 50, 370: 1, 437: 0, 215: 0, 369: 0, 338: 0, 385: 500}
    r, t = run(cyc(256, "RECHTECKZAPFEN", p))
    dmin = 1e9
    for q in feed_pts(t, zmax=-0.5):
        dx, dy = max(abs(q[0]) - 20, 0), max(abs(q[1]) - 15, 0)
        dmin = min(dmin, math.hypot(dx, dy))
    assert dmin == pytest.approx(5, abs=1e-3)  # Werkzeugmitte genau R vom Zapfen entfernt


def test_drill_203_reaches_depth_and_retracts():
    p = {200: 2, 201: -20, 206: 150, 202: 5, 210: 0, 203: 0, 204: 50, 212: 0, 213: 0, 205: 0, 211: 0,
         208: 0, 256: 0.2, 395: 0}
    r, t = run(cyc(203, "UNIVERSAL-BOHREN", p, tool=1))
    zs = [m.points[-1][2] for m in t.moves]
    assert min(zs) == pytest.approx(-20)
    assert zs[-2] == pytest.approx(50)  # 2. Sicherheitsabstand


def test_pattern_circle_calls_cycle_at_each_point():
    text = (cyc(200, "BOHREN", {200: 2, 201: -5, 206: 150, 202: 5, 210: 0, 203: 0, 204: 20, 211: 0, 395: 0},
                call="CYCL DEF 220 MUSTER KREIS ~\n Q216=+0 ;X ~\n Q217=+0 ;X ~\n Q244=+50 ;X ~\n Q245=+0 ;X ~\n"
                     " Q246=+360 ;X ~\n Q247=+0 ;X ~\n Q241=+5 ;X ~\n Q200=+2 ;X ~\n Q203=+0 ;X ~\n Q204=+20 ;X ~\n"
                     " Q301=+1 ;X ~\n Q365=+0 ;X", tool=1))
    r, t = run(text)
    bottoms = {(round(m.points[-1][0], 3), round(m.points[-1][1], 3)) for m in t.moves
               if abs(m.points[-1][2] + 5) < 1e-6}
    assert len(bottoms) == 5
    for x, y in bottoms:
        assert math.hypot(x, y) == pytest.approx(25, abs=1e-3)


def test_pattern_def_pos_and_row():
    text = cyc(201, "REIBEN", {200: 2, 201: -5, 206: 100, 211: 0, 208: 200, 203: 0, 204: 20},
               call="PATTERN DEF ~\n POS1 (X+10 Y+10 Z+0) ~\n ROW1 (X+30 Y+10 D+10 NUM3 ROT+0 Z+0)\n"
                    "4 CYCL CALL PAT FMAX", tool=1)
    r, t = run(text)
    bottoms = sorted({round(m.points[-1][0], 3) for m in t.moves if abs(m.points[-1][2] + 5) < 1e-6})
    assert bottoms == [10, 30, 40, 50]


@pytest.mark.skipif(not os.environ.get("CYCLO_RS274"), reason="CYCLO_RS274 nicht gesetzt")
@pytest.mark.parametrize("name", ["ZYKLEN_BOHREN", "ZYKLEN_TASCHEN", "SL_KONTUR", "BOHREN_200", "ZYKLEN_NUT_VIELECK",
                                  "ZYKLEN_GEWINDE", "ZYKLEN_SPIEGELN", "KONTURTASCHEN", "ZYKLEN_KONTURNUT", "GRAVIEREN"])  # 4ACHS_SCHWENKEN braucht B-Achse + M428-Remap der 4-Achs-Konfiguration
def test_examples_match_linuxcnc(name, tmp_path):
    from test_against_linuxcnc import _endpoints_rs274_tbl

    path = os.path.join(HERE, "..", "examples", name + ".h")
    if not os.path.exists(path):
        pytest.skip("Beispiel fehlt")
    r, t = run(open(path).read())
    ref = _endpoints_rs274_tbl(r.gcode, tmp_path, os.path.join(HERE, "tools.tbl"))
    mine = [m.points[-1][:3] for m in t.moves]
    # jeder Endpunkt des Original-Interpreters kommt in gleicher Reihenfolge im Tracer vor
    j = 0
    for k, q in enumerate(ref):
        while j < len(mine) and max(abs(a - b) for a, b in zip(mine[j], q)) > 5e-2:
            j += 1
        assert j < len(mine), f"Punkt {k} {q} nicht im Tracer gefunden"
        j += 1


def test_round_slot_on_pitch_circle():
    p = {215: 0, 219: 12, 368: 0, 375: 80, 367: 0, 216: 50, 217: 50, 376: 0, 248: 90, 378: 0, 377: 1,
         207: 600, 351: 1, 201: -5, 202: 5, 369: 0, 206: 150, 338: 0, 200: 2, 203: 0, 204: 20, 366: 0, 385: 500,
         439: 0}
    r, t = run(cyc(254, "RUNDE NUT", p))
    rs = [math.hypot(q[0] - 50, q[1] - 50) for q in feed_pts(t)]
    assert min(rs) == pytest.approx(40 - 6 + 5, abs=0.05)
    assert max(rs) == pytest.approx(40 + 6 - 5, abs=0.05)


def test_polygon_stud_outside_hexagon():
    p = {573: 0, 571: 40, 222: 60, 572: 6, 224: 0, 220: 0, 368: 0, 207: 600, 351: 1, 201: -6, 202: 3,
         206: 150, 200: 2, 203: 0, 204: 20, 370: 1, 215: 0, 369: 0, 338: 0, 385: 500}
    r, t = run(cyc(258, "VIELECKZAPFEN", p))
    # Inkreis 40 -> Werkzeugmitte nie näher als Inkreisradius + R an der Mitte
    assert min(math.hypot(q[0], q[1]) for q in feed_pts(t, zmax=-0.5)) >= 20 + 5 - 0.05


# ------------------------------------------------------------------ Gewindefräsen 263..267, 204, 241
def _pts(t):
    """Punkte ab dem ersten bekannten Startpunkt (ohne den angenommenen Programmanfang)."""
    return [pt for m in t.moves if m.start_known for pt in m.points]


def _helix_sense(t, center=(0.0, 0.0), r_expect=None, tol=1e-3):
    """Summe dz*dtheta über alle Schraubenbögen auf dem Gewinderadius: >0 Rechtsgewinde."""
    s = 0.0
    for m in t.moves:
        if m.kind != "arc":
            continue
        pts = m.points
        if abs(pts[-1][2] - pts[0][2]) < 1e-6:
            continue
        rr = [math.hypot(p[0] - center[0], p[1] - center[1]) for p in pts]
        if r_expect is not None and max(abs(x - r_expect) for x in rr) > tol:
            continue
        for a, b in zip(pts, pts[1:]):
            th = math.atan2(b[1] - center[1], b[0] - center[0]) - math.atan2(a[1] - center[1], a[0] - center[0])
            th = (th + math.pi) % (2 * math.pi) - math.pi
            s += th * (b[2] - a[2])
    return s


THREAD = {335: 12, 239: 1.75, 201: -15, 356: -18, 253: 750, 351: 1, 202: 6, 258: 0.2, 257: 0, 256: 0.2,
          358: -1, 359: 0.5, 200: 2, 203: 0, 204: 30, 206: 150, 207: 400, 512: 0}


@pytest.mark.parametrize("q351,q239", [(1, 1.75), (-1, 1.75), (1, -1.75), (-1, -1.75)])
def test_264_thread_hand_and_radius(q351, q239):
    p = {**THREAD, 351: q351, 239: q239}
    r, t = run(cyc(264, "BOHRGEWINDEFRAESEN", p, tool=6))
    pr = 12 / 2 - 4
    s = _helix_sense(t, r_expect=pr)
    assert (s > 0) == (q239 > 0)
    assert min(pt[2] for pt in _pts(t)) == pytest.approx(-18)
    helix = [pt for m in t.moves if m.kind == "arc" for pt in m.points
             if abs(math.hypot(pt[0], pt[1]) - pr) < 1e-3]
    assert min(pt[2] for pt in helix) >= -15 - 1.75 / 8 - 1e-6


def test_263_countersink_and_thread():
    p = {335: 12, 239: 1.75, 201: -15, 356: -17, 253: 750, 351: 1, 200: 2, 357: 0.2, 358: 0, 359: 0,
         203: 0, 204: 30, 254: 200, 207: 400, 512: 0}
    r, t = run(cyc(263, "SENKGEWINDEFRAESEN", p, tool=6))
    assert min(pt[2] for pt in _pts(t)) == pytest.approx(-17)
    assert max(math.hypot(pt[0], pt[1]) for pt in _pts(t)) == pytest.approx(2, abs=1e-3)
    assert _helix_sense(t, r_expect=2) > 0


def test_265_helix_down_to_depth():
    p = {335: 16, 239: 1.5, 201: -12, 253: 750, 358: 0, 359: 0, 360: 0, 200: 2, 203: 0, 204: 30, 254: 200,
         207: 300}
    r, t = run(cyc(265, "HELIX-BOHRGEWINDEFR.", p, tool=6))
    pr = 8 - 4
    helix = [pt for m in t.moves if m.kind == "arc" for pt in m.points if abs(math.hypot(pt[0], pt[1]) - pr) < 1e-3]
    assert min(pt[2] for pt in helix) == pytest.approx(-12, abs=1e-6)
    assert _helix_sense(t, r_expect=pr) > 0  # Rechtsgewinde


@pytest.mark.parametrize("q355", [0, 3])
def test_267_outer_thread(q355):
    p = {335: 20, 239: 1.5, 201: -10, 355: q355, 253: 750, 351: 1, 200: 2, 358: 0, 359: 0, 203: 0, 204: 30,
         254: 150, 207: 400, 512: 0}
    r, t = run(cyc(267, "AUSSENGEWINDE FR.", p, tool=6))
    pr = 10 + 4
    helix = [pt for m in t.moves if m.kind == "arc" for pt in m.points if abs(math.hypot(pt[0], pt[1]) - pr) < 1e-3]
    assert min(pt[2] for pt in helix) <= -10 + 1e-6
    assert max(pt[2] for pt in helix) >= -1.5
    # nie innerhalb des Zapfens
    assert min(math.hypot(pt[0], pt[1]) for pt in _pts(t) if pt[2] < 0) >= pr - 1e-6
    assert _helix_sense(t, r_expect=pr) > 0


def test_204_back_bore():
    p = {200: 2, 249: 3, 250: 20, 251: 0.5, 252: 4, 253: 750, 254: 100, 255: 0, 203: 0, 204: 30, 214: 1, 336: 0}
    r, t = run(cyc(204, "RUECKWAERTS-SENKEN", p, tool=1))
    zs = [m.points[-1][2] for m in t.moves]
    assert min(zs) == pytest.approx(0 - 20 - 2 - 4)
    assert -20 + 3 - 4 in [round(z, 6) for z in zs]  # Schneide auf Senkungsgrund
    # Ein- und Ausfahren exzentrisch nach -X
    assert any(abs(m.points[-1][0] + 0.5) < 1e-9 for m in t.moves)
    assert "M19 R0" in r.gcode


def test_241_dwell_depth_and_feed_factor():
    p = {200: 2, 201: -25, 206: 150, 211: 0.5, 203: 0, 204: 30, 379: 5, 253: 750, 208: 1000, 426: 3, 427: 300,
         428: 3000, 429: 8, 430: 9, 435: 20, 401: 50, 202: 10, 212: 2, 205: 4}
    r, t = run(cyc(241, "EINLIPPEN-TIEFBOHREN", p, tool=1))
    assert min(m.points[-1][2] for m in t.moves) == pytest.approx(-25)
    lines = r.gcode.splitlines()
    assert "G4 P0.5" in lines and "M8" in lines and "M9" in lines
    assert any(l.startswith("G1 Z-25") and "F75" in l for l in lines)  # 50 % Vorschub nach Verweiltiefe
    assert "M3 S300" in lines and "M3 S3000" in lines


def _ocm(defs, call="L X+50 Y+50 R0 FMAX M99", tool=2, extra=""):
    blocks = "\n".join(f"{i + 3} {d}" for i, d in enumerate(defs))
    n = len(defs) + 3
    return (f"0 BEGIN PGM T MM\n1 TOOL CALL {tool} Z S3000 F500\n2 L Z+100 R0 FMAX M3\n{blocks}\n"
            f"{n} {call}\n{n + 1} L Z+100 FMAX M30\n{extra}{n + 2} END PGM T MM\n")


def _q(num, name, **q):
    from cyclo.dialog.cycles import REGISTRY
    vals = {p.q: p.default for p in REGISTRY[num].params}
    vals.update({int(k[1:]): v for k, v in q.items()})
    return f"CYCL DEF {num} {name} ~\n" + " ~\n".join(f"  Q{k}={v:+g} ;X" for k, v in vals.items())


def test_cycle_names_without_option():
    from cyclo.dialog.cycles import REGISTRY
    assert all("Option" not in c.name for c in REGISTRY.values())


def test_ocm_rectangle_rough_and_finish():
    fig = _q(1271, "KT RECHTECK", Q650=0, Q218=70, Q219=50, Q220=0, Q201=-8, Q368=0.3, Q369=0.2)
    r, t = run(_ocm([fig, _q(272, "KT RAEUMEN", Q202=4)]))
    pts = feed_pts(t)
    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    # Werkzeug R5, Aufmass 0,3 seitlich, 0,2 Boden
    assert min(xs) == pytest.approx(20.3, abs=0.02) and max(xs) == pytest.approx(79.7, abs=0.02)
    assert min(ys) == pytest.approx(30.3, abs=0.02) and min(zs) == pytest.approx(-7.8, abs=1e-3)
    r, t = run(_ocm([fig, _q(274, "KT SEITE SCHLICHTEN")]))
    pts = feed_pts(t)
    assert max(p[0] for p in pts) == pytest.approx(80, abs=0.02)
    assert min(p[2] for p in pts) == pytest.approx(-8, abs=1e-3)


def test_ocm_island_with_boundary():
    fig = _q(1272, "KT KREIS", Q650=1, Q223=36, Q201=-5)
    bnd = _q(1281, "KT BEGRENZUNG RECHTECK", Q651=80, Q652=80)
    r, t = run(_ocm([fig, bnd, _q(272, "KT RAEUMEN", Q202=5)]))
    pts = feed_pts(t)
    assert min(math.hypot(p[0] - 50, p[1] - 50) for p in pts) >= 23 - 0.02  # Insel R18 + Werkzeug R5
    assert any(math.hypot(p[0] - 50, p[1] - 50) > 35 for p in pts)


def test_ocm_contour_and_chamfer():
    contour = ("90 LBL 1\n91 L X+10 Y+10 RL\n92 L X+40\n93 L Y+60\n94 L X+10\n95 L Y+10\n96 LBL 0\n")
    defs = ["CYCL DEF 14.0 KONTUR", "CYCL DEF 14.1 KONTURLABEL 1", _q(271, "KT DATEN", Q201=-6),
            _q(277, "KT FASE", Q353=-2, Q359=0.5)]
    r, t = run(_ocm(defs, call="CYCL CALL", tool=4, extra=contour))
    pts = feed_pts(t)
    # Fasenbreite 0,5, Spitze -2, 90°: Mittelpunkt 1,5 mm innerhalb der Wand
    assert min(p[0] for p in pts) == pytest.approx(11.5, abs=0.02)
    assert max(p[1] for p in pts) == pytest.approx(58.5, abs=0.02)
    assert min(p[2] for p in pts) == pytest.approx(-2, abs=1e-3)


def test_cycle_def_single_line_params():
    text = cyc(200, "BOHREN", {}).replace(
        "CYCL DEF 200 BOHREN ~\n", "CYCL DEF 200 BOHREN Q200=+2 Q201=-12 Q206=+150 Q202=+5 Q210=+0 Q203=+0 Q204=+50\n")
    r, t = run(text)
    assert min(p[2] for p in feed_pts(t)) == pytest.approx(-12)


def _ct_prog(c270, c25_or_275, contour, tool=2):
    return (f"0 BEGIN PGM T MM\n1 TOOL CALL {tool} Z S3000 F500\n2 L Z+100 R0 FMAX M3\n"
            f"3 CYCL DEF 14.0 KONTUR\n4 CYCL DEF 14.1 KONTURLABEL 1\n"
            + (f"5 {c270}\n" if c270 else "") + f"6 {c25_or_275}\n7 CYCL CALL\n8 L Z+100 FMAX M30\n"
            f"9 LBL 1\n{contour}LBL 0\n10 END PGM T MM\n")


SLOT_LINE = "L X+10 Y+20 R0\nL X+70\n"


def test_275_slot_width_and_depth():
    c = _q(275, "KONTURNUT WIRBELFR.", Q219=14, Q201=-6, Q202=3, Q436=2, Q368=0.2, Q369=0, Q203=0, Q200=2, Q204=20)
    r, t = run(_ct_prog(None, c, SLOT_LINE))
    pts = feed_pts(t)
    ys = [p[1] for p in pts]
    assert min(ys) == pytest.approx(20 - 2, abs=0.02) and max(ys) == pytest.approx(20 + 2, abs=0.02)  # 7 - R5
    assert min(p[0] for p in pts) == pytest.approx(8, abs=0.02) and max(p[0] for p in pts) == pytest.approx(72, abs=0.02)
    assert min(p[2] for p in pts) == pytest.approx(-6)


def test_275_contour_is_wall_with_rl():
    c = _q(275, "KONTURNUT WIRBELFR.", Q219=14, Q201=-6, Q202=6, Q436=2, Q368=0, Q203=0, Q200=2, Q204=20)
    ct = _q(270, "KONTURZUG-DATEN", Q390=1, Q391=1, Q392=8, Q393=90, Q394=0)
    r, t = run(_ct_prog(ct, c, SLOT_LINE))
    ys = [p[1] for p in feed_pts(t)]
    # RL: Nut links der Kontur (Richtung +X) -> Y 20..34, Werkzeugmitte 25..29
    assert min(ys) == pytest.approx(25, abs=0.02) and max(ys) == pytest.approx(29, abs=0.02)


@pytest.mark.parametrize("q390,q391,q15", [(1, 1, 1), (1, 2, 1), (2, 1, -1), (3, 2, -1), (2, 0, 1)])
def test_25_with_270_approach(q390, q391, q15, tmp_path):
    ct = _q(270, "KONTURZUG-DATEN", Q390=q390, Q391=q391, Q392=8, Q393=60, Q394=6)
    c25 = _q(25, "KONTUR-ZUG", Q1=-4, Q3=0, Q5=0, Q7=20, Q10=-4, Q11=200, Q12=500, Q15=q15)
    r, t = run(_ct_prog(ct, c25, "L X+10 Y+20 R0\nL X+60\nCR X+80 Y+40 R+20 DR+\nL Y+60\n"))
    pts = feed_pts(t)
    on = [p for p in pts if 20 < p[0] < 55]  # gerades Stück entlang Y20
    side = {0: 0, 1: 1, 2: -1}[q391]
    assert all(abs(p[1] - (20 + side * 5)) < 0.02 for p in on if abs(p[2] + 4) < 1e-6 and abs(p[1] - 20) < 6)
    if os.environ.get("CYCLO_RS274"):
        from test_against_linuxcnc import _endpoints_rs274_tbl

        ref = _endpoints_rs274_tbl(r.gcode, tmp_path, os.path.join(HERE, "tools.tbl"))
        mine = [m.points[-1][:3] for m in t.moves]
        j = 0
        for k, q in enumerate(ref):
            while j < len(mine) and max(abs(a - b) for a, b in zip(mine[j], q)) > 5e-2:
                j += 1
            assert j < len(mine), f"Punkt {k} {q} nicht im Tracer gefunden"
            j += 1


def _engrave_prog(text, **q):
    from cyclo.dialog.cycles import template_for

    t = template_for(225).replace('QS500=""', f'QS500="{text}"')
    for k, v in q.items():
        t = re.sub(rf"(Q{k[1:]}=)[+-][\d.]+", lambda m: m.group(1) + f"{v:+g}", t)
    return f"0 BEGIN PGM T MM\n1 TOOL CALL 4 Z S3000 F500\n2 L Z+100 R0 FMAX M3\n3 {t}\n4 L X+20 Y+10 FMAX M99\n5 END PGM T MM\n"


def test_225_engrave_line_size_and_depth():
    r, t = run(_engrave_prog("HI 7", Q513=12, Q514=0.5, Q201=-0.3, Q202=0.1, Q367=1))
    pts = feed_pts(t)
    # Raster 4x6, 2 mm/Einheit, Lücke 0,5*12/3 = 2 mm: H 8 + 2 + I 4 + 2 + Leer 6 + 2 + 7 8 = 32 mm
    assert min(p[0] for p in pts) == pytest.approx(20) and max(p[0] for p in pts) == pytest.approx(20 + 32)
    assert min(p[1] for p in pts) == pytest.approx(10) and max(p[1] for p in pts) == pytest.approx(22)
    assert sorted({round(p[2], 3) for p in pts}) == [-0.3, -0.2, -0.1]


def test_225_engrave_on_arc_and_maxlen():
    r, t = run(_engrave_prog("ABC", Q513=6, Q516=1, Q517=30, Q201=-0.2, Q202=0.2))
    rad = [math.hypot(p[0] - 20, p[1] - 10) for p in feed_pts(t)]
    assert min(rad) == pytest.approx(30, abs=1e-3) and max(rad) <= 36 + 1e-3
    r, t = run(_engrave_prog("ABCDEFGH", Q513=10, Q574=40, Q201=-0.2, Q202=0.2))
    xs = [p[0] for p in feed_pts(t)]
    assert max(xs) - min(xs) == pytest.approx(40, abs=1e-3)


def test_225_text_param_roundtrip():
    from cyclo.dialog.cycles import REGISTRY
    from cyclo.dialog.format import cycle_values, format_cycle_block

    lines = format_cycle_block("3 CYCL DEF 225 GRAVIEREN", REGISTRY[225], {500: "Teil 4", 513: "8"})
    assert lines[1].strip().startswith('QS500="Teil 4"')
    vals = cycle_values(lines, 0, len(lines) - 1)
    assert vals[500][1] == '"Teil 4"' and vals[513][1] == "+8"
    with pytest.raises(AssertionError):
        run(_engrave_prog("A{B"))


# --------------------------------------------------------------- Taschenstrategie (Abgleich mit CAM)
SQUARE = {**POCKET, **{218: 80, 219: 80, 220: 18, 202: 4, 366: 1, 200: 5}}


def _arc_radii(gcode):
    return [round(math.hypot(float(i), float(j)), 3)
            for i, j in re.findall(r"^G[23] .*I(-?[\d.]+) J(-?[\d.]+)", gcode, re.M)]


def _planar_turns(t):
    """Größter Richtungswechsel (Grad) zwischen aufeinanderfolgenden Bahnpunkten in einer Ebene."""
    worst, run_ = 0.0, []
    for m in t.moves:
        if m.kind == "rapid":
            run_ = []
            continue
        for p in m.points:
            if not run_ or math.dist(p[:2], run_[-1][:2]) > 1e-4 or abs(p[2] - run_[-1][2]) > 1e-6:
                run_.append(p)
            if len(run_) >= 3:
                a, b, c = run_[-3:]
                if abs(a[2] - b[2]) < 1e-6 and abs(b[2] - c[2]) < 1e-6:
                    u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
                    worst = max(worst, abs(math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0],
                                                                   u[0] * v[0] + u[1] * v[1]))))
    return worst


def test_pocket_ring_corners_follow_wall_radius():
    r, t = run(cyc(251, "RECHTECKTASCHE", SQUARE, "L X+50 Y+50 FMAX M99"))
    radii = set(_arc_radii(r.gcode))
    assert 0.32 in radii          # Innenringe: kleiner Mindestradius statt scharfer Ecke
    assert {3.0, 8.0, 13.0} <= radii  # Außenringe: Eckenradius minus Abstand zur Wand


def test_pocket_transitions_tangent():
    """Keine scharfen Richtungswechsel beim Schruppen (S-Übergänge, gerundete Ecken)."""
    r, t = run(cyc(251, "RECHTECKTASCHE", SQUARE, "L X+50 Y+50 FMAX M99"))
    assert _planar_turns(t) < 10
    for params in ({**SQUARE, **{351: -1}}, {**POCKET, **{366: 1, 220: 8}}):
        r, t = run(cyc(251, "RECHTECKTASCHE", params))
        assert _planar_turns(t) < 10


def test_pocket_stays_inside_wall():
    from cyclo.dialog.cyclegen import _sdf_rrect
    for params in (SQUARE, {**SQUARE, **{351: -1, 224: 30}}, {**POCKET, **{366: 1, 220: 0}}):
        r, t = run(cyc(251, "RECHTECKTASCHE", params, "L X+50 Y+50 FMAX M99"))
        a, b = params[218] / 2 - 5, params[219] / 2 - 5
        rc = max(params[220] - 5, 0)
        ang = -math.radians(params[224])
        for m in t.moves:
            for p in (m.points if m.kind != "rapid" else []):
                if p[2] < -1e-3:
                    x, y = p[0] - 50, p[1] - 50
                    x, y = x * math.cos(ang) - y * math.sin(ang), x * math.sin(ang) + y * math.cos(ang)
                    assert _sdf_rrect(x, y, a, b, rc) < 1e-3, p


def test_pocket_helix_constant_pitch_from_just_above_surface():
    r, t = run(cyc(251, "RECHTECKTASCHE", SQUARE, "L X+50 Y+50 FMAX M99"))
    pr = 0.95 * 5
    helix = [m for m in t.moves if m.kind == "arc" and m.points[0][2] - m.points[-1][2] > 1e-6
             and all(abs(math.hypot(p[0] - 50, p[1] - 50) - pr) < 1e-3 for p in m.points)]
    assert helix
    assert helix[0].points[0][2] == pytest.approx(1.0, abs=1e-6)  # nicht vom Sicherheitsabstand aus
    for m in helix:  # gleichbleibende Steigung = Werkzeug-Eintauchwinkel 3°
        xy = sum(math.dist(a[:2], b[:2]) for a, b in zip(m.points, m.points[1:]))
        drop = m.points[0][2] - m.points[-1][2]
        assert math.degrees(math.atan(drop / xy)) == pytest.approx(3, abs=0.1)


def test_pocket_finish_tangential_and_no_duplicate_rapids():
    r, t = run(cyc(251, "RECHTECKTASCHE", SQUARE, "L X+50 Y+50 FMAX M99"))
    body = r.gcode[r.gcode.index("o<cyc251_1> sub"):r.gcode.index("endsub")].splitlines()
    assert not any(a == b and a.startswith("G0") for a, b in zip(body, body[1:]))
    # Wand schlichten: Anfahrbogen endet tangential auf der Wandbahn (X = 35 relativ)
    i = next(k for k, ln in enumerate(body) if "F500" in ln)
    assert body[i].startswith("G3") and "X[#<cx>+35]" in body[i]


def test_circular_pocket_rings_tangent():
    C = {215: 0, 223: 60, 368: 0, 207: 800, 351: 1, 201: -10, 202: 5, 369: 0, 206: 150, 338: 0,
         200: 2, 203: 0, 204: 50, 370: 1, 366: 1, 385: 500, 439: 0}
    r, t = run(cyc(252, "KREISTASCHE", C))
    assert _planar_turns(t) < 10
    for m in t.moves:
        for p in (m.points if m.kind != "rapid" else []):
            if p[2] < -1e-3:
                assert math.hypot(p[0], p[1]) <= 25 + 1e-3


def test_circular_pocket_half_circle_spiral():
    """252: Spirale aus Halbkreisen, Helix neben der Mitte endet tangential im Spiralanfang."""
    C = {215: 1, 223: 80, 368: 0, 207: 800, 351: 1, 201: -10, 202: 10, 369: 0, 206: 150, 338: 0,
         200: 2, 203: 0, 204: 50, 370: 1, 366: 1, 385: 500, 439: 0}
    r, t = run(cyc(252, "KREISTASCHE", C))
    body = r.gcode[r.gcode.index("o<cyc252_1> sub"):r.gcode.index("endsub")]
    mill = [ln for ln in body.splitlines() if "F800" in ln or (ln.startswith("G3") and "Z" not in ln)]
    i0 = next(i for i, ln in enumerate(mill) if "F800" in ln)
    spiral = mill[i0:i0 + 15]
    assert all(ln.startswith("G3") for ln in spiral)        # nur Bögen, keine Geraden
    assert "X[#<cx>+5] Y#<cy> I2.5 J0" in spiral[0]          # erster Halbbogen ab der Mitte
    assert "X[#<cx>+35] Y#<cy> I35 J0" in spiral[-1]         # Wandbahn als Vollkreis geschlossen
    assert _planar_turns(t) < 10
    helix = [m for m in t.moves if m.kind == "arc" and m.points[0][2] - m.points[-1][2] > 1e-6]
    assert helix[-1].points[-1][:2] == pytest.approx((0, 0), abs=1e-3)


@pytest.mark.parametrize("width", [20, 12])
def test_slot_helix_at_end_and_tangent(width):
    """253: Helix am Ende der Mittellinie, dünne Innenschleife, S-Übergang zur Wandbahn."""
    from cyclo.dialog.cyclegen import _sdf_rrect
    S = {215: 0, 218: 60, 219: width, 368: 0, 374: 0, 367: 0, 207: 500, 351: 1, 201: -10, 202: 10,
         369: 0, 206: 150, 338: 0, 200: 2, 203: 0, 204: 50, 366: 1, 385: 500, 439: 0}
    r, t = run(cyc(253, "NUT", S))
    assert _planar_turns(t) < 10
    b = width / 2
    helix = [m for m in t.moves if m.kind == "arc" and m.points[0][2] - m.points[-1][2] > 1e-6]
    ex, ey = helix[-1].points[-1][:2]
    assert ex == pytest.approx(-(30 - b) - 0.064 * 5, abs=1e-3) and ey == pytest.approx(0, abs=1e-3)
    for m in t.moves:
        for p in (m.points if m.kind != "rapid" else []):
            if p[2] < -1e-3:
                assert _sdf_rrect(p[0], p[1], 30 - 5, b - 5, b - 5) < 1e-3, p


# --------------------------------------------------------------- 272 adaptives Räumen
def _kt(figs, call_xy=(50, 50), q370=1, q202=10, extra="", contour=None):
    blocks = list(figs) + [_q(272, "KT RAEUMEN", Q202=q202, Q370=q370, Q207=1000, Q351=1)]
    if contour:
        return _ocm(blocks, call="CYCL CALL", extra=contour)
    return _ocm(blocks, call=f"L X+{call_xy[0]} Y+{call_xy[1]} R0 FMAX M99")


def _material_sim(t, inside_mat, bbox, R=5.0, h=0.2):
    """Abtrag auf einem Raster nachrechnen: -> (Restfläche mm², Umschlingungen in Grad je Bahnpunkt)."""
    import numpy as np
    x0, y0, x1, y1 = bbox
    xs, ys = np.arange(x0, x1, h) + h / 2, np.arange(y0, y1, h) + h / 2
    X, Y = np.meshgrid(xs, ys)
    mat = inside_mat(X, Y)
    zb = min(p[2] for m in t.moves if m.kind != "rapid" for p in m.points)
    ang = np.linspace(0, 2 * math.pi, 72, endpoint=False)
    eng = []
    for m in t.moves:
        if m.kind == "rapid":
            continue
        for a, b in zip(m.points, m.points[1:]):
            if min(a[2], b[2]) > zb + 4:
                continue
            n = max(1, int(math.dist(a[:2], b[:2]) / 0.25))
            for i in range(1, n + 1):
                x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
                if a[2] <= zb + 0.01 and b[2] <= zb + 0.01:
                    px, py = x + (R - 0.1) * np.cos(ang), y + (R - 0.1) * np.sin(ang)
                    ii, jj = ((px - x0) / h).astype(int), ((py - y0) / h).astype(int)
                    ok = (ii >= 0) & (ii < mat.shape[1]) & (jj >= 0) & (jj < mat.shape[0])
                    eng.append(mat[jj[ok], ii[ok]].sum() / len(ang) * 360)
                i0, i1 = max(int((x - R - x0) / h), 0), int((x + R - x0) / h) + 1
                j0, j1 = max(int((y - R - y0) / h), 0), int((y + R - y0) / h) + 1
                sub = mat[j0:j1, i0:i1]
                sub[(X[j0:j1, i0:i1] - x) ** 2 + (Y[j0:j1, i0:i1] - y) ** 2 <= R * R] = False
    return mat.sum() * h * h, np.array(eng)


def _rrect_inside(cx, cy, a, b, r):
    import numpy as np

    def f(X, Y):
        qx, qy = np.abs(X - cx) - (a - r), np.abs(Y - cy) - (b - r)
        return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r < 0
    return f


# Restfläche: Die Bahn hält 6 µm Sicherheitsrand zur Wand (adaptive.WALL_MARGIN); auf dem 0,2-mm-Raster
# zählt eine Zelle, deren Mitte in diesem Saum liegt, als Rest (Umfang 258 mm × 0,006 = 1,5 mm² möglich).
@pytest.mark.parametrize("rc,rest_max", [(18, 0.5 + 1.5), (0, 4 * (25 - math.pi * 25 / 4) + 1.5)])
def test_272_adaptive_pocket_engagement_and_rest(rc, rest_max):
    """272 geschlossene Tasche: Helix + Spirale + Fronten – Eingriff begrenzt, nichts bleibt stehen."""
    import numpy as np
    from cyclo.dialog.cyclegen import _sdf_rrect
    fig = _q(1271, "KT RECHTECK", Q650=0, Q218=80, Q219=80, Q220=rc, Q201=-10, Q368=0, Q369=0)
    r, t = run(_kt([fig]))
    for m in t.moves:  # nie in die Wand
        if m.kind != "rapid":
            for p in m.points:
                if p[2] < -1e-3:
                    assert _sdf_rrect(p[0] - 50, p[1] - 50, 35, 35, max(rc - 5, 0)) < 0.01, p
    rest, eng = _material_sim(t, _rrect_inside(50, 50, 40, 40, rc), (10, 10, 90, 90))
    assert rest < rest_max
    assert np.percentile(eng, 99) <= 100 and eng.max() <= 125


def test_272_adaptive_narrow_pocket_no_slotting():
    import numpy as np
    fig = _q(1271, "KT RECHTECK", Q650=0, Q218=200, Q219=40, Q220=6, Q201=-10, Q368=0, Q369=0)
    r, t = run(_kt([fig], call_xy=(110, 30)))
    rest, eng = _material_sim(t, _rrect_inside(110, 30, 100, 20, 6), (10, 10, 210, 50))
    assert rest < 0.5
    assert np.percentile(eng, 99) <= 100 and eng.max() <= 130


def test_272_adaptive_island_and_open_boundary():
    """Offene Begrenzung mit Insel: Eintauchen neben dem Material, Insel bleibt um R frei."""
    import numpy as np
    fig = _q(1272, "KT KREIS", Q650=1, Q223=30, Q201=-8, Q368=0, Q369=0)
    bnd = _q(1281, "KT BEGRENZUNG RECHTECK", Q651=80, Q652=60)
    r, t = run(_kt([fig, bnd]))
    first_plunge = next(p for m in t.moves if m.kind != "rapid" for p in m.points if p[2] < -1e-3)
    fx, fy = abs(first_plunge[0] - 50) - 40, abs(first_plunge[1] - 50) - 30
    assert math.hypot(max(fx, 0), max(fy, 0)) >= 5  # eintauchen neben dem Rohteil
    for m in t.moves:
        if m.kind != "rapid":
            for p in m.points:
                if p[2] < -1e-3:
                    assert math.hypot(p[0] - 50, p[1] - 50) >= 15 + 5 - 0.01, p

    def mat(X, Y):
        return (np.abs(X - 50) < 40) & (np.abs(Y - 50) < 30) & (np.hypot(X - 50, Y - 50) > 15)
    rest, eng = _material_sim(t, mat, (10, 20, 90, 80))
    assert rest < 0.5
    assert np.percentile(eng, 99) <= 100


def test_272_adaptive_contour_island_closed_pocket():
    import numpy as np
    contour = ("90 LBL 1\n91 L X+10 Y+10 RL\n92 L X+90\n93 L Y+90\n94 L X+10\n95 L Y+10\n96 LBL 0\n"
               "97 LBL 2\n98 L X+50 Y+35 RL\n99 L X+35 Y+50\n100 L X+50 Y+65\n101 L X+65 Y+50\n"
               "102 L X+50 Y+35\n103 LBL 0\n")
    defs = ["CYCL DEF 14.0 KONTUR", "CYCL DEF 14.1 KONTURLABEL 1 /2",
            _q(271, "KT DATEN", Q201=-10, Q368=0, Q369=0, Q569=0)]
    r, t = run(_kt(defs, contour=contour))

    def mat(X, Y):
        return (np.abs(X - 50) < 40) & (np.abs(Y - 50) < 40) & (np.abs(X - 50) + np.abs(Y - 50) > 15)
    rest, eng = _material_sim(t, mat, (10, 10, 90, 90))
    assert rest < 4 * (25 - math.pi * 25 / 4) + 3  # nur die scharfen Ecken (Werkzeugradius)
    assert np.percentile(eng, 99) <= 110
    isl = [(50, 35), (65, 50), (50, 65), (35, 50)]

    def dist_isl(x, y):
        best = 1e9
        for (ax, ay), (bx, by) in zip(isl, isl[1:] + isl[:1]):
            tt = max(0.0, min(1.0, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
            best = min(best, math.hypot(x - ax - tt * (bx - ax), y - ay - tt * (by - ay)))
        return best
    for m in t.moves:  # auch Verbindungen (angehoben) nie durch die Insel
        if m.kind != "rapid":
            for p in m.points:
                if p[2] < -1e-3:
                    assert dist_isl(p[0], p[1]) >= 5 - 0.01, p


def test_272_adaptive_rounded_links_and_entries():
    """Wie CAM: Aus-/Einfahren und Verbinden über Bögen, angehoben um 0,2 mm, kaum Rückzüge."""
    fig = _q(1271, "KT RECHTECK", Q650=0, Q218=80, Q219=80, Q220=18, Q201=-10, Q368=0, Q369=0)
    r, t = run(_kt([fig]))
    body = r.gcode[r.gcode.index("o<cyc272_1> sub"):r.gcode.index("o<cyc272_1> endsub")].splitlines()
    retracts = [ln for ln in body if re.match(r"G0 Z2$", ln)]
    assert len(retracts) <= 2  # Start und Ende
    # angehobene Verbindungen: Bögen oder – entlang einer geraden, fertigen Wand – Geraden
    lifted = [ln for ln in body if re.match(r"G[123] .*Z-9\.8", ln)]
    assert len(lifted) >= 4
    assert any(re.match(r"G[23] .*Z-9\.8", ln) for ln in body)
    assert not any(re.match(r"G1 Z-10\b", ln) for ln in body[10:])  # kein senkrechtes Eintauchen auf Tiefe


@pytest.mark.parametrize("q370", [0.3, 0.6, 1.0, 1.5])
def test_272_no_rapid_into_material(q370):
    """Abtragssimulation: nach einem Rückzug nie im Eilgang ins Material (Fehler bei Q370=0,6)."""
    from cyclo.sim.dexel import ToolShape, ZMap
    fig = _q(1271, "KT RECHTECK", Q650=0, Q218=80, Q219=80, Q220=18, Q201=-10, Q368=0, Q369=0)
    r, t = run(_kt([fig], q370=q370))
    zm = ZMap.from_stock((0, 0, -20), (100, 100, 0))
    zm.run(t.moves, {2: ToolShape(5)})
    assert not [e for e in zm.events if e.kind == "rapid"]


def test_slot_253_finish_lead_in_not_in_allowance():
    """Nut 253 mit Seitenaufmaß: der Schlicht-Anfahrpunkt liegt im geschruppten Feld, nicht im Endbogen
    auf der Fertigbahn (sonst Eilgang ins Aufmaß – Befund „Eilgang im Material“)."""
    import os

    from cyclo.dialog.translator import TranslatorConfig, translate
    from cyclo.sim.dexel import ToolShape, ZMap
    from cyclo.sim.tracer import Tracer

    radii = {2: 5, 3: 10, 4: 4, 5: 3}
    path = os.path.join(os.path.dirname(__file__), "..", "examples", "ZYKLEN_TASCHEN.h")
    r = translate(open(path).read(), "ZYKLEN_TASCHEN.h",
                  TranslatorConfig(tools={k: {"R": radii.get(k, 5), "L": 50} for k in range(10)}))
    assert not r.errors
    t = Tracer(tool_lengths={k: 50 for k in range(10)}).trace_text(r.gcode)
    zm = ZMap.from_stock_dict(r.stock)
    zm.run(t.moves, {k: ToolShape(radii.get(k, 5)) for k in range(10)})
    assert [(e.line, e.kind) for e in zm.events] == []


def test_cycle_2028_home_position():
    from cyclo.dialog.cycles import REGISTRY, template_for
    from cyclo.dialog.translator import translate
    from cyclo.sim.tracer import Tracer

    assert REGISTRY[2028].name == "GRUNDSTELLUNG" and not REGISTRY[2028].call_active
    assert "Q596=+0" in template_for(2028) and "Q597=+1" in template_for(2028)
    src = ("0 BEGIN PGM T MM\n1 CYCL DEF 2028 GRUNDSTELLUNG ~\n  Q596=+0 ;Position ~\n  Q597=+1 ;Achsen\n"
           "2 L X+10 Y+10 R0 FMAX\n3 L Z+5 FMAX\n4 CYCL DEF 2028 GRUNDSTELLUNG ~\n  Q596=+1 ;Position ~\n"
           "  Q597=+2 ;Achsen\n5 END PGM T MM\n")
    r = translate(src, "t.h")
    assert not r.errors
    g = [ln for ln in r.gcode_lines if ln and not ln.startswith("(")]
    i = g.index("G91 G28 Z0")
    assert g[i:i + 3] == ["G91 G28 Z0", "G28 X0 Y0", "G90"]
    j = g.index("G91 G30 Z0")
    assert g[j:j + 4] == ["G91 G30 Z0", "G30 X0 Y0", "G30 B0", "G90"]
    # Simulation: Start an der G28-Position (Maschinennull) statt auf dem Werkstücknullpunkt
    t = Tracer(work_offset=(460, 231, -329), params={5181: 100, 5182: 50, 5183: -10}).trace_text(r.gcode)
    first_known = next(m for m in t.moves if m.start_known)
    assert first_known.points[0][2] == pytest.approx(329)
    last = t.moves[-1].points[-1]
    assert last[:3] == pytest.approx((100 - 460, 50 - 231, -10 + 329))
    # mit Radiuskorrektur verboten
    bad = "0 BEGIN PGM T MM\n1 L X+0 Y+0 RL F100\n2 CYCL DEF 2028 GRUNDSTELLUNG ~\n  Q596=+0 ;P ~\n  Q597=+0 ;A\n3 END PGM T MM\n"
    assert translate(bad, "t.h").errors


def test_face_meander_connects_rows_with_half_circles():
    """Planen: Bahnwechsel tangential über Halbkreise (r = halbe Zustellung), nicht eckig."""
    p = {389: 0, 225: 0, 226: 0, 227: 0, 386: -1, 218: 100, 219: 30, 202: 5, 369: 0, 370: 0.7,
         207: 1000, 385: 800, 253: 300, 200: 2, 357: 2, 204: 50}
    r, t = run(cyc(232, "PLANEN", p))
    sub = r.gcode[r.gcode.find("o<cyc232"):r.gcode.find("endsub")]
    arcs = re.findall(r"^(G[23]) X(\S+) Y\S+ I0 J1\.6667", sub, re.M)
    assert len(arcs) == 9  # 10 Bahnen -> 9 Verbindungen
    # rechts gegen den Uhrzeigersinn hoch, links im Uhrzeigersinn
    assert all(g == ("G3" if float(x) > 50 else "G2") for g, x in arcs)
    # keine reine Querfahrt in Y mehr auf Fräshöhe
    assert not re.search(r"^G1 X(\S+) Y\S+ F\S+\nG1 X\1 ", sub, re.M)
    pts = feed_pts(t)
    assert max(p[0] for p in pts) == pytest.approx(100 + 7 + 1.6667, abs=1e-3)


def test_emit_link_tiny_arc_is_no_full_circle():
    """Verbindungsbogen mit fast gleichem Start/Ende: als Gerade ausgeben – im G-Code wären gleiche
    Endpunkte sonst ein Vollkreis (fuhr bei Vergleichsteil T4 durch die Taschenwand)."""
    from cyclo.dialog.adaptive import Prim
    from cyclo.dialog.cyclegen import Emit
    from cyclo.dialog.pocket import _emit_link
    e = Emit(rel=False)
    e.cur = (10.0, 10.0)
    c = (9.0, 10.0)
    a = 1e-5
    p1 = (c[0] + math.cos(a), c[1] + math.sin(a))
    _emit_link(e, [Prim("L", (10.0, 10.0), (10.0, 10.0 + 1e-6)), Prim("A", (10.0, 10.0), p1, c, a)], -5, 0.2, 1000)
    assert not any(ln.startswith(("G2", "G3")) for ln in e.lines)


def test_273_open_boundary_floor_between_island_and_stock_edge():
    """273 mit offener Begrenzung: schmaler Steg (4 mm) zwischen Insel und Rohteilkante wird am Boden
    geschlichtet – das Werkzeug darf über die Kante hinaus."""
    from cyclo.sim.dexel import ToolShape, ZMap
    import numpy as np
    fig = _q(1272, "KT KREIS", Q650=1, Q223=72, Q367=0, Q203=0, Q201=-5, Q368=0, Q369=0, Q260=50)
    bnd = _q(1281, "KT BEGRENZUNG RECHTECK", Q651=80, Q652=80, Q654=0, Q655=0, Q656=0)
    fin = _q(273, "KT BODEN SCHLICHTEN", Q370=1, Q385=800)
    r, t = run(_ocm([fig, bnd, fin], call="L X+50 Y+50 R0 FMAX M99"))
    zm = ZMap.from_stock((10, 10, -20), (90, 90, 0))
    zm.run(t.moves, {2: ToolShape(5)})
    X = zm.x0 + (np.arange(zm.nx) + 0.5) * zm.res
    Y = zm.y0 + (np.arange(zm.ny) + 0.5) * zm.res
    gx, gy = np.meshgrid(X, Y)
    gap = np.hypot(gx - 50, gy - 50) > 36.5
    assert np.nanmax(zm.h[gap]) < -4.95


@pytest.mark.parametrize("q595", [0, 1])
def test_273_floor_strategies_clear_floor_with_arcs(q595):
    """273 in beiden Schlichtarten (Q595 = 0 Ringe / 1 gleicher Eingriff): Boden bis auf den Rand fertig,
    Bahnen mit Bögen, kein Eilgang unter Sicherheitshöhe."""
    from cyclo.sim.dexel import ToolShape, ZMap
    import numpy as np
    fig = _q(1272, "KT KREIS", Q650=1, Q223=72, Q367=0, Q203=0, Q201=-5, Q368=0, Q369=0, Q260=50)
    bnd = _q(1281, "KT BEGRENZUNG RECHTECK", Q651=80, Q652=80, Q654=0, Q655=0, Q656=0)
    fin = _q(273, "KT BODEN SCHLICHTEN", Q370=1, Q385=800, Q595=q595)
    r, t = run(_ocm([fig, bnd, fin], call="L X+50 Y+50 R0 FMAX M99"))
    body = r.gcode[r.gcode.index("o<cyc273_1> sub"):r.gcode.index("o<cyc273_1> endsub")].splitlines()
    assert sum(1 for ln in body if re.match(r"G[23] ", ln)) >= 4
    for ln in body:  # Eilgang in Z nur auf Sicherheitshöhe oder höher
        m = re.match(r"G0 Z(-?[\d.]+)", ln)
        assert not m or float(m.group(1)) >= 2 - 1e-9, ln
    zm = ZMap.from_stock((10, 10, -20), (90, 90, 0))
    zm.run(t.moves, {2: ToolShape(5)})
    X = zm.x0 + (np.arange(zm.nx) + 0.5) * zm.res
    Y = zm.y0 + (np.arange(zm.ny) + 0.5) * zm.res
    gx, gy = np.meshgrid(X, Y)
    gap = np.hypot(gx - 50, gy - 50) > 36.5
    assert np.nanmax(zm.h[gap]) < -4.95
    assert np.nanmin(zm.h[np.hypot(gx - 50, gy - 50) < 35.5]) > -0.01  # Insel unberührt


# --------------------------------------------------------------------------- Zweitprüfung 272/273
def _ocm_direct(reg, cycle=272, r=5.0, angle=3.0, q370=0.4, depth=-5.0, step=5.0, q595=1, stock=None,
                q351=1, q369=0.0):
    """ocm_cycle direkt aufrufen -> (Emit, Tracer-Ergebnis)."""
    from cyclo.dialog.cyclegen import Emit, P, Tool
    from cyclo.dialog.pocket import ocm_cycle
    e = Emit(rel=False)
    ocm_cycle(cycle, P({202: step, 370: q370, 207: 1000, 385: 800, 253: 750, 568: 0.5, 351: q351, 595: q595}),
              P({201: depth, 203: 0, 368: 0, 369: q369, 260: 50}), reg, Tool(2, r, 50, angle), e, False,
              stock=stock)
    t = Tracer([NGC_DIR]).trace_text("G21 G90 G17 G91.1\nG0 Z50\n" + "\n".join(e.lines))
    assert not t.errors, t.errors
    return e, t


def _arc_sweeps(lines):
    """Bogenwinkel (Grad) aller G2/G3 aus den gerundeten Wörtern; gleiche Endpunkte = 360."""
    x = y = None
    out = []
    for ln in lines:
        if not re.match(r"G[0123] ", ln):
            continue
        d = {k: float(v) for k, v in re.findall(r"([XYIJ])(-?[\d.]+)", ln)}
        xx, yy = d.get("X", x), d.get("Y", y)
        if ln.startswith(("G2 ", "G3 ")) and x is not None:
            cx, cy = x + d.get("I", 0), y + d.get("J", 0)
            a, b = math.atan2(y - cy, x - cx), math.atan2(yy - cy, xx - cx)
            sw = ((b - a) if ln.startswith("G3") else (a - b)) % (2 * math.pi)
            out.append(360.0 if (xx == x and yy == y) else math.degrees(sw))
        x, y = xx, yy
    return out


def _vertical_plunges(t, below=-0.3):
    """Senkrechte Vorschubbewegungen nach unten, die tiefer als below enden."""
    return [(m.points[0], m.points[-1]) for m in t.moves
            if m.kind != "rapid" and len(m.points) == 2 and math.dist(m.points[0][:2], m.points[-1][:2]) < 1e-6
            and m.points[-1][2] < m.points[0][2] - 1e-6 and m.points[-1][2] < below]


def _rect(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


@pytest.mark.parametrize("w,h,r", [(50, 10.4, 5), (50, 10.6, 5), (50, 11, 5), (50, 14, 5), (11, 11, 5),
                                   (1.2, 1.2, 0.5)])
def test_272_narrow_slot_no_vertical_plunge(w, h, r):
    """Schmale Nut / kleine Tasche mit ANGLE: Einstieg über Pendelrampe oder Helix, nie senkrecht ins
    Material; danach kein zweiter Einstich. Boden fertig."""
    from cyclo.dialog.pocket import region_from_polys
    from cyclo.sim.dexel import ToolShape, ZMap
    import numpy as np
    e, t = _ocm_direct(region_from_polys([_rect(w, h)], []), r=r)
    assert _vertical_plunges(t) == []
    assert sum(1 for ln in e.lines if re.match(r"G0 Z2$", ln)) <= 2
    zm = ZMap.from_stock((-w / 2 - 1, -h / 2 - 1, -10), (w / 2 + 1, h / 2 + 1, 0))
    zm.run(t.moves, {0: ToolShape(r), 2: ToolShape(r)})
    assert not zm.events
    X = zm.x0 + (np.arange(zm.nx) + 0.5) * zm.res
    Y = zm.y0 + (np.arange(zm.ny) + 0.5) * zm.res
    gx, gy = np.meshgrid(X, Y)
    reach = np.hypot(np.maximum(abs(gx) - (w / 2 - r), 0), np.maximum(abs(gy) - (h / 2 - r), 0)) < r - 0.1
    assert ((zm.h > -4.95) & reach).sum() == 0
    if h < 2.5 * r and w > 4 * r:
        assert any("Pendelrampe" in m for m in e.warn)


def test_272_no_room_for_helix_or_ramp_warns():
    """Tasche genau so groß wie das Werkzeug (+2 µm): weder Helix noch Rampe möglich – senkrecht mit Warnung."""
    from cyclo.dialog.pocket import region_from_polys
    e, t = _ocm_direct(region_from_polys([_rect(10.03, 10.03)], []))
    assert any("senkrecht" in m for m in e.warn)


@pytest.mark.parametrize("n", [24, 40, 64, 200])
@pytest.mark.parametrize("cycle,q595", [(272, 1), (273, 0), (273, 1)])
def test_27x_feed_points_inside_allowed_area(n, cycle, q595):
    """Sicherheitsanforderung 1 am fertigen, gerundeten G-Code: jeder Vorschubpunkt unter der Oberfläche
    liegt in offset(reg, R + Q368). Polygonale Tasche (n-Eck): Bögen dürfen die Sehnen nicht verlassen."""
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.pocket import region_from_polys
    import numpy as np
    reg = region_from_polys([[(30 * math.cos(i * 2 * math.pi / n), 30 * math.sin(i * 2 * math.pi / n))
                              for i in range(n)]], [])
    allowed = ad.offset(reg, 5)
    e, t = _ocm_direct(reg, cycle, q595=q595)
    Q = np.array([v[:2] for m in t.moves if m.kind != "rapid" for v in m.points if v[2] < -0.001])
    A = np.array(ad._flt(allowed[0]))
    B = np.roll(A, -1, axis=0)
    V = B - A
    cross = V[:, 0, None] * (Q[None, :, 1] - A[:, 1, None]) - V[:, 1, None] * (Q[None, :, 0] - A[:, 0, None])
    outside = float(np.maximum(-cross / np.hypot(V[:, 0], V[:, 1])[:, None], 0).max())
    assert outside <= 1e-4, outside   # 0,1 µm = Rundung der Ausgabe auf vier Stellen
    assert any(ln.startswith(("G2 ", "G3 ")) for ln in e.lines)


@pytest.mark.parametrize("cycle,q595", [(272, 1), (273, 0), (273, 1)])
def test_27x_arcs_at_most_half_circle(cycle, q595):
    """Alle Bögen (Schnitt, Verbindungen, Helix) höchstens 180°, keiner mit gleichen Endpunkten (Vollkreis)."""
    from cyclo.dialog.pocket import region_from_polys
    holes = [[(x + 4 * math.cos(i * math.pi / 12), y + 4 * math.sin(i * math.pi / 12)) for i in range(24)]
             for x, y in [(-15, 0), (15, 5)]]
    for reg, kw in [(region_from_polys([_rect(80, 50)], holes), {}),
                    (region_from_polys([_rect(50, 30)], []), dict(depth=-10))]:
        e, t = _ocm_direct(reg, cycle, q595=q595, **kw)
        sw = _arc_sweeps(e.lines)
        assert sw and max(sw) <= 180.01, max(sw)


def test_helix_rest_arc_is_no_full_circle():
    """Rundungsrest der Helix (Tiefe knapp über einem ganzen Umlauf): kein Bogen mit gleichen Endpunkten."""
    from cyclo.dialog.pocket import region_from_polys
    rh = 4.75
    pitch = 2 * math.pi * rh * math.tan(math.radians(3))
    e, t = _ocm_direct(region_from_polys([_rect(50, 30)], []), depth=-(3 * pitch + 1e-5 - 1))
    assert max(_arc_sweeps(e.lines)) <= 180.01


def test_grid_free_sees_material_inside_tool_disc():
    """Grid.free prüft die ganze Werkzeugscheibe, nicht nur Punkte auf einem Kreis."""
    import numpy as np
    from cyclo.dialog import adaptive as ad
    g = ad.Grid(-10, -10, 10, 10, 5.0)
    g.mat[:] = False
    g.fill([[(1.9, -0.1), (2.1, -0.1), (2.1, 0.1), (1.9, 0.1)]], True)
    assert g.mat.sum() >= 1
    assert not g.free(np.array([[0.0, 0.0]]))[0]
    assert not g.clear((0.0, 0.0))
    assert g.free(np.array([[-4.0, 0.0]]))[0]            # Materialzelle außerhalb der Scheibe
    assert not g.free(np.array([[9.0, 9.0]]))[0]         # Scheibe ragt über das Raster: nicht frei


def test_272_area_too_large_gives_error():
    from cyclo.dialog.cyclegen import CycleError
    from cyclo.dialog.pocket import region_from_polys
    with pytest.raises(CycleError, match="zu groß"):
        _ocm_direct(region_from_polys([_rect(5000, 5000)], []))


def _blk_program(extra_before="", figure_x=150):
    """Rechtecktasche 60 × 40 um (figure_x, 50): bei figure_x = 150 ragt sie halb über das Rohteil
    (BLK FORM 0…150 × 0…100) hinaus = seitlich offen."""
    fig = _q(1271, "KT RECHTECK", Q650=0, Q218=60, Q219=40, Q220=0, Q201=-5, Q368=0, Q369=0)
    cyc = _q(272, "KT RAEUMEN", Q202=5, Q370=0.4, Q207=1000, Q351=1)
    pre = "".join(f"{ln}\n" for ln in extra_before.splitlines())
    return ("0 BEGIN PGM T MM\n1 BLK FORM 0.1 Z X+0 Y+0 Z-30\n2 BLK FORM 0.2 X+150 Y+100 Z+0\n"
            "3 TOOL CALL 2 Z S3000 F500\n4 L Z+100 R0 FMAX M3\n" + pre +
            f"5 {fig}\n6 {cyc}\n7 L X+{figure_x} Y+50 R0 FMAX M99\n8 L Z+100 FMAX M30\n9 END PGM T MM\n")


def _sub272(text):
    r = translate(text, "t.h", TranslatorConfig(tools=TOOLS))
    assert not r.errors, [str(m) for m in r.errors]
    g = r.gcode
    return g[g.index("o<cyc272_1> sub"):g.index("o<cyc272_1> endsub")].splitlines()


def test_272_stock_open_side_only_without_datum_shift_or_rotation():
    """Das Rohteil der BLK FORM gilt nur ohne Verschiebung/Drehung: mit TRANS DATUM, Zyklus 10 oder
    geändertem Bezugspunkt wird wie für eine geschlossene Tasche geplant (Helix statt Start „aus der Luft“)."""
    def helix(body):   # geschlossen geplant: erster Einstich in der Tasche über dem Rohteil, mit Helix
        first_feed = next(i for i, ln in enumerate(body) if ln.startswith("G1"))
        return all(re.match(r"G[23] .*Z", ln) for ln in body[first_feed + 1:first_feed + 4])

    base = _sub272(_blk_program())
    assert not helix(base)                                  # offene Seite: Start neben dem Rohteil
    closed = _sub272(_blk_program().replace("1 BLK FORM 0.1 Z X+0 Y+0 Z-30\n2 BLK FORM 0.2 X+150 Y+100 Z+0\n", ""))
    assert helix(closed)
    for pre in ("TRANS DATUM AXIS X-30 Y+0", "CYCL DEF 10.0 DREHUNG\nCYCL DEF 10.1 ROT+90",
                "TRANS DATUM AXIS X+0 Y+0"):
        body = _sub272(_blk_program(pre))
        assert helix(body), pre
        assert body == closed, pre
    # Verschiebung wieder aufgehoben: Rohteil gilt wieder
    assert _sub272(_blk_program("TRANS DATUM AXIS X-30 Y+0\nTRANS DATUM RESET")) == base


# --------------------------------------------------------------------------- Runde 2: prims_within
def _sq(x0, y0, x1, y1):
    from cyclo.dialog.slcycles import _int
    return _int([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _line(a, b):
    from cyclo.dialog.adaptive import Prim
    return Prim("L", a, b)


def _arc3(p0, c, sweep):
    """Bogen ab p0 um c mit Winkel sweep (+ = gegen Uhrzeiger)."""
    from cyclo.dialog.adaptive import Prim
    a = math.atan2(p0[1] - c[1], p0[0] - c[0]) + sweep
    r = math.dist(p0, c)
    return Prim("A", p0, (c[0] + r * math.cos(a), c[1] + r * math.sin(a)), c, sweep)


@pytest.mark.parametrize("a,b", [
    ((1, -1), (9, -1)), ((1, -0.01), (9, -0.01)),          # waagerecht unterhalb (Gegenbeispiel Runde 2)
    ((1, 11), (9, 11)), ((1, 10.01), (9, 10.01)),          # waagerecht oberhalb
    ((-1, 1), (-1, 9)), ((11, 1), (11, 9)),                # senkrecht links / rechts
    ((1, -1), (9, -2)), ((-3, 2), (-1, 8)),                # schräg außen
    ((5, 5), (15, 5)), ((-5, 5), (5, 5)), ((5, -5), (5, 15)),   # innen -> außen, quer durch
    ((-1, -1), (-1, -1)), ((12, 5), (12, 5 + 1e-7)),       # entartet / sehr kurz, außen
])
def test_prims_within_rejects_outside_lines(a, b):
    from cyclo.dialog import adaptive as ad
    assert not ad.prims_within([_line(a, b)], [_sq(0, 0, 10, 10)])


@pytest.mark.parametrize("a,b", [
    ((1, 1), (9, 1)), ((1, 1), (9, 9)), ((5, 0.01), (5, 9.99)), ((0.01, 0.01), (9.99, 0.01)),
    ((5, 5), (5, 5)), ((5, 5), (5, 5 + 1e-7)),             # entartet / sehr kurz, innen
])
def test_prims_within_accepts_inside_lines(a, b):
    from cyclo.dialog import adaptive as ad
    assert ad.prims_within([_line(a, b)], [_sq(0, 0, 10, 10)])


def test_prims_within_boundary_tolerance():
    """Genau auf der Grenze und entlang der Grenze: abgelehnt, weil die Prüfung PRIMS_TOL (2 µm) Abstand
    zur Grenze verlangt; ab 5 µm innerhalb angenommen. Dazwischen ist das Ergebnis nicht festgelegt."""
    from cyclo.dialog import adaptive as ad
    reg = [_sq(0, 0, 10, 10)]
    assert not ad.prims_within([_line((1, 0), (9, 0))], reg)          # entlang der Grenze
    assert not ad.prims_within([_line((5, 5), (10, 5))], reg)         # endet auf der Grenze
    assert not ad.prims_within([_line((1, 0.001), (9, 0.001))], reg)  # 1 µm innerhalb: zu knapp
    assert ad.prims_within([_line((1, 0.005), (9, 0.005))], reg)      # 5 µm innerhalb
    assert ad.prims_within([_line((0.005, 0.005), (9.995, 0.005))], reg)


def test_prims_within_island_and_notch_between_inside_endpoints():
    """Beide Endpunkte zulässig, dazwischen eine Insel bzw. eine einspringende Aussparung."""
    from cyclo.dialog import adaptive as ad
    island = list(reversed(_sq(4, 4, 6, 6)))                          # Loch = Uhrzeigersinn
    reg = [_sq(0, 0, 10, 10), island]
    assert not ad.prims_within([_line((1, 5), (9, 5))], reg)
    assert not ad.prims_within([_line((1, 4.5), (9, 5.5))], reg)
    assert ad.prims_within([_line((1, 3), (9, 3))], reg)
    assert not ad.prims_within([_line((5, 5), (5, 5))], reg)          # Punkt in der Insel
    from cyclo.dialog.slcycles import _int
    notch = [_int([(0, 0), (10, 0), (10, 10), (6, 10), (6, 3), (4, 3), (4, 10), (0, 10)])]   # U-Form
    assert not ad.prims_within([_line((2, 8), (8, 8))], notch)
    assert not ad.prims_within([_line((2, 8), (3.999, 3.001)), _line((3.999, 3.001), (6.001, 3.001)),
                                _line((6.001, 3.001), (8, 8))], notch)   # schneidet die Ecken der Aussparung
    assert ad.prims_within([_line((2, 8), (2, 1.5)), _line((2, 1.5), (8, 1.5)), _line((8, 1.5), (8, 8))], notch)


def test_prims_within_arcs_with_inside_endpoints():
    """Bogen mit zulässigen Endpunkten, dessen Zwischenverlauf die Fläche verlässt (und Gegenprobe)."""
    from cyclo.dialog import adaptive as ad
    reg = [_sq(0, 0, 10, 10)]
    out = _arc3((2, 0.5), (5, 0.5), math.pi)          # Halbkreis nach unten: bis y = −2,5
    assert out.p1[0] == pytest.approx(8) and out.p1[1] == pytest.approx(0.5)
    assert not ad.prims_within([out], reg)
    assert ad.prims_within([_arc3((2, 0.5), (5, 0.5), -math.pi)], reg)   # nach oben: bis y = 3,5
    # knapper Fall: Bogen taucht nur 0,02 mm unter die Grenze / bleibt 0,02 mm darüber
    r = 20.0
    for dip, ok in ((-0.02, False), (0.02, True)):
        c = (5.0, dip + r)
        x = math.sqrt(r * r - (c[1] - 0.5) ** 2)
        a0 = math.atan2(0.5 - c[1], -x)
        a1 = math.atan2(0.5 - c[1], x)
        assert ad.prims_within([_arc3((5 - x, 0.5), c, a1 - a0)], reg) is ok
    # Bogen um eine Insel herum bzw. durch sie hindurch
    island = [_sq(0, 0, 10, 10), list(reversed(_sq(4.5, 4.5, 5.5, 5.5)))]
    assert ad.prims_within([_arc3((3, 5), (5, 5), math.pi)], island)
    assert not ad.prims_within([_arc3((4, 4), (4, 5), math.pi)], island)    # Halbkreis über (5, 5): durch die Insel
    assert ad.prims_within([_arc3((4, 4), (4, 5), -math.pi)], island)       # andersherum über (3, 5): frei


def test_prims_within_empty_and_no_region():
    from cyclo.dialog import adaptive as ad
    assert ad.prims_within([], [_sq(0, 0, 10, 10)])
    assert not ad.prims_within([_line((1, 1), (2, 2))], [])


# --------------------------------------------------------------------------- Runde 2: Pendelrampe
def _rot_poly(pts, deg):
    c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * sn, x * sn + y * c) for x, y in pts]


def _l_slot(width, leg=60.0, deg=0.0):
    """L-förmige Nut: zwei Schenkel der Länge leg, Breite width. Keine Gerade läuft durch beide Schenkel."""
    w = width
    return _rot_poly([(0, 0), (leg, 0), (leg, w), (w, w), (w, leg), (0, leg)], deg)


def _plunges_into_material(t, r, lo, hi, tool_no=0):
    """Senkrechte Vorschubbewegungen nach unten, unter denen (Werkzeugscheibe R − 0,15) noch Material über
    der Zieltiefe steht. Senkrechte Zustellungen über schon geräumtem Bereich zählen nicht."""
    from cyclo.sim.dexel import ToolShape, ZMap
    import numpy as np
    zm = ZMap.from_stock(lo, hi, max_cells=400_000)
    tools = {0: ToolShape(r), 2: ToolShape(r)}
    X = zm.x0 + (np.arange(zm.nx) + 0.5) * zm.res
    Y = zm.y0 + (np.arange(zm.ny) + 0.5) * zm.res
    gx, gy = np.meshgrid(X, Y)
    bad, done = [], 0
    for i, m in enumerate(t.moves):
        a, b = m.points[0], m.points[-1]
        if (m.kind != "rapid" and len(m.points) == 2 and math.dist(a[:2], b[:2]) < 1e-6
                and b[2] < a[2] - 1e-6 and b[2] < hi[2] - 0.05):
            zm.run(t.moves, tools, start=done, stop=i)
            done = i
            disc = np.hypot(gx - a[0], gy - a[1]) < r - 0.15
            if disc.any() and float(np.nanmax(zm.h[disc])) > b[2] + 0.05:
                bad.append((tuple(round(v, 3) for v in a[:3]), round(b[2], 3)))
    zm.run(t.moves, tools, start=done)
    return bad, zm


_SLOTS = [("rect", 100, 10.4, 17), ("rect", 30, 10.2, 43), ("rect", 15, 10.05, 7), ("rect", 50, 10.4, 0),
          ("L", 60, 10.4, 0), ("L", 60, 10.4, 11)]


@pytest.mark.parametrize("kind,length,width,deg", _SLOTS)
@pytest.mark.parametrize("q351", [1, -1])
@pytest.mark.parametrize("cycle", [272, 273])
def test_27x_ramp_in_slots_of_any_direction(kind, length, width, deg, q351, cycle):
    """Schmale Nut in beliebiger Richtung (auch L-förmig), 272 und 273/Q595 = 1, beide Fräsrichtungen:
    Einstieg über eine Pendelrampe in der Nut, Neigung höchstens ANGLE, Rampenvorschub, Endtiefe,
    Boden fertig, kein senkrechter Einstich ins Material."""
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.pocket import region_from_polys
    import numpy as np
    R, ang, depth = 5.0, 3.0, -5.0
    poly = _rot_poly(_rect(length, width), deg) if kind == "rect" else _l_slot(width, length, deg)
    reg = region_from_polys([poly], [])
    allowed = ad.offset(reg, R)
    q369 = 0.3 if cycle == 273 else 0.0
    e, t = _ocm_direct(reg, cycle, q351=q351, q369=q369)
    assert any("Pendelrampe" in m for m in e.warn), e.warn
    feeds = [m for m in t.moves if m.kind != "rapid"]
    # 1. alle Vorschubpunkte unter der Oberfläche in der zulässigen Fläche (1 µm Rechentoleranz der Probe)
    Q = np.array([v[:2] for m in feeds for v in m.points if v[2] < -0.001])
    assert ad.Region(ad.offset(allowed, -0.001), shrink=0).points_inside(Q).all()
    # 2. Rampe = die absteigenden Geraden bis zum ersten Erreichen der Endtiefe
    ramp = []
    for m in feeds:
        a, b = m.points[0], m.points[-1]
        if b[2] < a[2] - 1e-6 and math.dist(a[:2], b[:2]) > 1e-6:
            ramp.append(m)
        if b[2] <= depth + 1e-6:
            break
    assert len(ramp) >= 2 and len(ramp) % 2 == 0
    f_ramp = (1000 if cycle == 272 else 800) * 0.5
    ends = set()
    for m in ramp:
        a, b = m.points[0], m.points[-1]
        slope = math.degrees(math.atan2(a[2] - b[2], math.dist(a[:2], b[:2])))
        # Ausgabe auf 1e-4 gerundet: bei Rampenlängen ab 0,25 mm höchstens 0,05° Fehler
        assert slope <= ang + 0.05, slope
        assert m.feed == pytest.approx(f_ramp)
        ends |= {tuple(round(v, 3) for v in a[:2]), tuple(round(v, 3) for v in b[:2])}
    assert len(ends) == 2                                    # Pendeln zwischen genau zwei Punkten
    p0, p1 = sorted(ends)
    assert math.dist(p0, p1) >= min(0.8 * (length - 2 * R), 40) - 0.2   # Rampe nutzt die Nutlänge
    assert ramp[-1].points[-1][2] == pytest.approx(depth, abs=1e-4)
    # 3. Endtiefe, Einstiche, Boden
    assert min(v[2] for m in feeds for v in m.points) == pytest.approx(depth, abs=1e-4)
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    top = 0.0 if cycle == 272 else depth + q369              # 273: bis auf das Bodenaufmaß vorgeräumt
    lo, hi = (min(xs) - 1, min(ys) - 1, -10), (max(xs) + 1, max(ys) + 1, top)
    bad, zm = _plunges_into_material(t, R, lo, hi)
    assert bad == []
    assert not zm.events
    X = zm.x0 + (np.arange(zm.nx) + 0.5) * zm.res
    Y = zm.y0 + (np.arange(zm.ny) + 0.5) * zm.res
    gx, gy = np.meshgrid(X, Y)
    reach = ad.Region(ad.offset(allowed, -(R - 0.15)), shrink=0).points_inside(
        np.stack([gx.ravel(), gy.ravel()], 1)).reshape(gx.shape)
    assert reach.sum() > 0
    assert ((zm.h > depth + 0.05) & reach).sum() == 0


# --------------------------------------------------------------------------- Runde 2: Helix-Restbogen
def _helix_in_old(e, t, sx, sy, rh, z_from, z_to, f, ccw, start_at=None):
    """Unveränderte Kopie des alten cyclegen._helix_in (Stand b1fea37) – nur als Vergleich im Test."""
    pitch = 2 * math.pi * rh * math.tan(math.radians(t.angle))
    a = 0.0 if start_at is None else start_at
    sgn = 1 if ccw else -1
    p0 = (sx + rh * math.cos(a), sy + rh * math.sin(a))
    e.feed_xy(*p0, f)
    total = max(z_from - z_to, 0.0) / pitch * 2 * math.pi
    done = 0.0
    while total - done > 1e-6:
        step = min(math.pi, total - done)
        done += step
        ang = a + sgn * done
        z = z_from - (z_from - z_to) * done / total
        e.arc(sx + rh * math.cos(ang), sy + rh * math.sin(ang), sx, sy, ccw, f, z=z)
    ang = a + sgn * done
    for _ in range(2):
        ang += sgn * math.pi
        e.arc(sx + rh * math.cos(ang), sy + rh * math.sin(ang), sx, sy, ccw, f)
    u = (math.cos(ang), math.sin(ang))
    tan = (-u[1], u[0]) if ccw else (u[1], -u[0])
    return (sx + rh * u[0], sy + rh * u[1]), tan, ang


def _run_helix(fn, ccw, z_to, rh=4.75, z_from=1.0):
    from cyclo.dialog.cyclegen import Emit, Tool
    e = Emit(rel=False)
    e.rapid_xy(rh, 0.0)
    end, tan, ang = fn(e, Tool(2, 5.0, 50, 3.0), 0.0, 0.0, rh, z_from, z_to, "600", ccw)
    return e, end


@pytest.mark.parametrize("ccw", [True, False])
def test_helix_in_rest_arc_old_full_circle_new_none(ccw):
    """Tatsächliches Gegenbeispiel der Zweitprüfung (Rest 1e-6 über drei Umläufen): Der alte Helfer gibt
    einen Bogen mit gleichen gerundeten Endpunkten aus (= Vollkreis), der korrigierte nicht.
    Ausgewertet werden die gerundeten Wörter der Ausgabe."""
    from cyclo.dialog.cyclegen import _helix_in, fmt
    rh = 4.75
    pitch = 2 * math.pi * rh * math.tan(math.radians(3))
    z_to = 1.0 - (3 * pitch + 1e-6)          # entspricht Tiefe −(3·pitch + 1e-6 − 1) ab Z+1
    old, _ = _run_helix(_helix_in_old, ccw, z_to)
    new, end = _run_helix(_helix_in, ccw, z_to)
    assert _arc_sweeps(old.lines).count(360.0) == 1          # alter Helfer: ungewollter Vollkreis
    sw = _arc_sweeps(new.lines)
    assert sw.count(360.0) == 0 and max(sw) <= 180.01        # neuer Helfer: keiner
    # Endposition, Endtiefe, Vorschub
    assert end == pytest.approx((rh, 0.0), abs=2e-4)
    x = y = z = None
    for ln in new.lines:
        d = {k: float(v) for k, v in re.findall(r"([XYZ])(-?[\d.]+)", ln)}
        x, y, z = d.get("X", x), d.get("Y", y), d.get("Z", z)
    assert (x, y) == pytest.approx((rh, 0.0), abs=1e-4)
    assert z == pytest.approx(z_to, abs=1e-4)
    assert f"Z{fmt(z_to)}" in " ".join(new.lines)
    moves = [ln for ln in new.lines if re.match(r"G[123] ", ln)]
    assert all(ln.endswith(" F600") for ln in moves)
    # die beiden ebenen Abschluss-Halbkreise bleiben erhalten (ohne Z-Wort)
    assert all(re.match(r"G[23] ", ln) and " Z" not in ln for ln in moves[-2:])
    assert sw[-2:] == pytest.approx([180.0, 180.0], abs=0.01)
    # Drehsinn
    assert all(ln.startswith("G3" if ccw else "G2") for ln in moves if ln[:2] in ("G2", "G3"))


@pytest.mark.parametrize("ccw", [True, False])
@pytest.mark.parametrize("turns", [0.3, 1.0, 2.5])
def test_helix_in_regular_case_unchanged(ccw, turns):
    """Regulärer Fall: neuer und alter Helfer geben dasselbe aus; Abschluss = zwei ebene Halbkreise."""
    from cyclo.dialog.cyclegen import _helix_in
    rh = 4.75
    pitch = 2 * math.pi * rh * math.tan(math.radians(3))
    old, _ = _run_helix(_helix_in_old, ccw, 1.0 - turns * pitch)
    new, _ = _run_helix(_helix_in, ccw, 1.0 - turns * pitch)
    assert new.lines == old.lines
    sw = _arc_sweeps(new.lines)
    assert sw.count(360.0) == 0 and sw[-2:] == pytest.approx([180.0, 180.0], abs=0.01)


# --------------------------------------------------------------------------- Runde 2: Speicherbudget
def _count_grids(monkeypatch):
    from cyclo.dialog import adaptive as ad
    made = []
    orig = ad.Grid.__init__

    def init(self, *a, **kw):
        made.append(a)
        orig(self, *a, **kw)
    monkeypatch.setattr(ad.Grid, "__init__", init)
    return made


def _plan(polys, R=5.0, k=2.0, budget=None):
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.pocket import region_from_polys
    allowed = ad.offset(region_from_polys(polys, []), R)
    return ad.plan_regions(allowed, None, R, k, True, 0.95 * R, 0.2 * R, 0.2 * R, budget=budget)


def _sq_at(cx, size=40.0):
    return [(cx - size / 2, -size / 2), (cx + size / 2, -size / 2), (cx + size / 2, size / 2), (cx - size / 2, size / 2)]


def test_memory_budget_counts_all_components_of_one_call(monkeypatch):
    """Zwei Teilflächen, die einzeln ins Budget passen, zusammen nicht: Abbruch vor dem zweiten Raster.
    Jeder neue Aufruf beginnt mit leerem Budget (nichts wird über Aufrufe hinweg aufaddiert)."""
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.pocket import region_from_polys
    comp = ad.components(ad.offset(ad.offset(region_from_polys([_sq_at(0)], []), 5.0), ad.WALL_MARGIN))[0]
    limit = 2 * 2 ** 20 + ad.plan_need(comp, 5.0, 2.0) + 1000     # Grunddaten + eine Teilfläche
    made = _count_grids(monkeypatch)
    for _ in range(2):                                            # einzeln: passt, auch wiederholt
        plans = _plan([_sq_at(0)], budget=ad.Budget(limit))
        assert len(plans) == 1 and plans[0]["mem"]["peak"] <= limit
    assert len(made) == 2
    del made[:]
    with pytest.raises(ad.PlanError) as ex:
        _plan([_sq_at(0), _sq_at(100)], budget=ad.Budget(limit))
    assert ex.value.args[0] == "memory"
    assert len(made) == 1                                         # zweites Raster wurde nicht angelegt
    # ohne ausdrückliches Budget: neues Budget je Aufruf, Grenze = MEM_BUDGET zum Zeitpunkt des Aufrufs
    monkeypatch.setattr(ad, "MEM_BUDGET", limit)
    del made[:]
    for _ in range(3):
        assert len(_plan([_sq_at(0)])) == 1
    assert len(made) == 3
    assert "grid" not in plans[0] and "pieces" not in plans[0]    # Simulationsdaten werden nicht gehalten


def test_memory_budget_includes_tool_masks(monkeypatch):
    """Großer Werkzeugradius: die Werkzeugmasken (∝ (R/h)²) zählen mit; Abbruch vor der Allokation."""
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.pocket import region_from_polys
    comp5 = ad.components(ad.offset(region_from_polys([_sq_at(0, 200)], []), 5.0))[0]
    comp60 = ad.components(ad.offset(region_from_polys([_sq_at(0, 200)], []), 60.0))[0]
    side60 = 2 * (int(math.ceil(60 / ad.SIM_H)) + 1) + 1
    assert ad.plan_need(comp60, 60.0, 24.0) >= 75 * side60 * side60 > 25 * 2 ** 20
    limit = 30 * 2 ** 20
    assert ad.plan_need(comp5, 5.0, 2.0) + 2 * 2 ** 20 < limit < ad.plan_need(comp60, 60.0, 24.0)
    made = _count_grids(monkeypatch)
    assert len(_plan([_sq_at(0, 200)], R=5.0, k=2.0, budget=ad.Budget(limit))) == 1
    assert len(made) == 1
    with pytest.raises(ad.PlanError) as ex:
        _plan([_sq_at(0, 200)], R=60.0, k=24.0, budget=ad.Budget(limit))
    assert ex.value.args[0] == "memory" and len(made) == 1


def test_memory_budget_error_message_from_cycle(monkeypatch):
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.cyclegen import CycleError
    from cyclo.dialog.pocket import region_from_polys
    reg = region_from_polys([_rect(80, 50)], [])
    e, t = _ocm_direct(reg)                                       # normaler Fall: im Budget
    assert e.lines
    monkeypatch.setattr(ad, "MEM_BUDGET", 5 * 2 ** 20)
    made = _count_grids(monkeypatch)
    with pytest.raises(CycleError, match="Arbeitsspeicher"):
        _ocm_direct(reg)
    assert made == []


def test_memory_estimate_covers_measured_peak():
    """Kontrollierte Messung (tracemalloc: Python- und numpy-Speicher, ohne Clipper): Die Schätzung des
    Budgets liegt über dem gemessenen Spitzenwert."""
    import tracemalloc
    tracemalloc.start()
    plans = _plan([_sq_at(0, 120)])
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak <= plans[0]["mem"]["peak"]
    assert cur <= plans[0]["mem"]["held"] + 2 ** 20


# ------------------------------------------------------------------ Runde 3 (unabhängige Prüfung review-3)
def _ocm3(reg, cycle=272, r=5.0, angle=3.0, open_bnd=False, stock=None, pq=None, dq=None, **kw):
    """ocm_cycle direkt, alle Parameter wählbar -> (Emit, Tracer-Ergebnis)."""
    from cyclo.dialog.cyclegen import Emit, P, Tool
    from cyclo.dialog.pocket import ocm_cycle
    p = {202: 5.0, 370: 0.4, 207: 1000, 385: 800, 253: 750, 568: 0.5, 351: 1, 595: 1, 200: 2}
    d = {201: -5.0, 203: 0.0, 368: 0.0, 369: 0.0, 260: 50}
    p.update(pq or {})
    d.update(dq or {})
    e = Emit(rel=False)
    ocm_cycle(cycle, P(p), P(d), reg, Tool(2, r, 50, angle), e, open_bnd, stock=stock, **kw)
    t = Tracer([NGC_DIR]).trace_text("G21 G90 G17 G91.1\nG0 Z50\n" + "\n".join(e.lines))
    assert not t.errors, t.errors
    return e, t


def _gcode_samples(lines, step=0.1):
    """Eigener kleiner Parser für den gerundeten G-Code -> Liste (g, x, y, z, Zeile, Bahnlänge bis hier in
    diesem Satz). Geraden alle step mm, Bögen als Bögen (höchstens 0,01 rad je Schritt)."""
    x = y = None
    z = 50.0
    out = []
    for n, ln in enumerate(lines):
        m = re.match(r"G([0123]) ", ln)
        if not m:
            continue
        g = int(m.group(1))
        w = {k: float(v) for k, v in re.findall(r"([XYZIJ])(-?[\d.]+)", ln)}
        x1, y1, z1 = w.get("X", x), w.get("Y", y), w.get("Z", z)
        if x is None or y is None:
            x, y, z = x1, y1, z1
            continue
        if g in (2, 3):
            cx, cy = x + w.get("I", 0.0), y + w.get("J", 0.0)
            r = math.hypot(x - cx, y - cy)
            a0, a1 = math.atan2(y - cy, x - cx), math.atan2(y1 - cy, x1 - cx)
            sw = ((a1 - a0) if g == 3 else (a0 - a1)) % (2 * math.pi)
            k = max(1, int(math.ceil(sw / 0.01)))
            for i in range(k + 1):
                a = a0 + (1 if g == 3 else -1) * sw * i / k
                out.append((g, cx + r * math.cos(a), cy + r * math.sin(a), z + (z1 - z) * i / k, n, r * sw * i / k))
        else:
            L = math.hypot(x1 - x, y1 - y)
            k = max(1, int(math.ceil(L / step)))
            for i in range(k + 1):
                out.append((g, x + (x1 - x) * i / k, y + (y1 - y) * i / k, z + (z1 - z) * i / k, n, L * i / k))
        x, y, z = x1, y1, z1
    return out


def _feed_len(lines):
    """Vorschubweg in XY (mm) aus dem G-Code."""
    last, total = None, 0.0
    for s in _gcode_samples(lines, 1e9):
        if last is not None and s[0] != 0 and s[4] == last[4]:
            total += math.hypot(s[1] - last[1], s[2] - last[2])
        last = s
    return total


def _rect_at(w, h, cx=0.0, cy=0.0):
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def _circle_at(cx, cy, r, n=64):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


# ---- K1: Insel an oder über der offenen Begrenzung
_EDGE_ISLANDS = {"buendig unten": (40, 30, 0, -15), "5 mm ueber die Kante": (40, 30, 0, -20),
                 "buendig in der Ecke": (40, 30, -20, -15), "Streifen ueber die ganze Breite": (80, 20, 0, 0),
                 "0,5 mm innerhalb (Vergleich)": (40, 30, 0, -14.5)}


@pytest.mark.parametrize("name", list(_EDGE_ISLANDS))
@pytest.mark.parametrize("cycle,q595", [(272, 1), (273, 1), (273, 0)])
def test_27x_open_boundary_island_on_edge_is_protected(name, cycle, q595):
    """Offene Begrenzung 80 × 60, Insel an / über der Rohteilkante: das Werkzeug (Eilgang wie Vorschub) kommt
    unter der Oberfläche der Insel nirgends näher als R. Gemessen am gerundeten G-Code gegen das Insel-Rechteck
    selbst. Vor der Korrektur: bis 9,9 mm in der Insel, beim Streifen Eilgang in die Insel."""
    from cyclo.dialog.pocket import region_from_polys
    w, h, cx, cy = _EDGE_ISLANDS[name]
    reg = region_from_polys([], [_rect_at(w, h, cx, cy)], _rect_at(80, 60))
    e, t = _ocm3(reg, cycle, open_bnd=True, pq={595: q595}, dq={369: 0.2} if cycle == 273 else None)
    worst, cut = -1e9, 0
    for g, x, y, z, n, s in _gcode_samples(e.lines):
        if z < -1e-3:
            dx, dy = abs(x - cx) - w / 2, abs(y - cy) - h / 2
            sd = math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0.0)   # Abstand zur Insel, innen negativ
            worst = max(worst, 5.0 - sd)
            cut += g != 0
    assert cut > 100                      # es wird gefräst
    assert worst <= 0.006, worst          # 5 µm Sehnenfehler des Clipper-Versatzes + Rundung


def test_272_open_boundary_island_on_edge_explicit_islands_and_translator():
    """Dieselbe Sicherung über die beiden anderen Wege: Inseln ausdrücklich an ocm_cycle übergeben (Fläche als
    einfache Liste), und über den Übersetzer (Figur als Insel, Begrenzung so verschoben, dass die Insel
    bündig an der unteren Rohteilkante liegt)."""
    from cyclo.dialog.pocket import region_from_polys
    from cyclo.dialog.slcycles import _int
    isl = _rect_at(40, 30, 0, -15)
    reg = region_from_polys([], [isl], _rect_at(80, 60))
    e, t = _ocm3(list(reg), 272, open_bnd=True, islands=[_int(isl)])

    def worst(samples, cx, cy):
        out = -1e9
        for g, x, y, z, n, s in samples:
            if z < -1e-3:
                dx, dy = abs(x - cx) - 20, abs(y - cy) - 15
                out = max(out, 5.0 - (math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0.0)))
        return out
    assert worst(_gcode_samples(e.lines), 0, -15) <= 0.006
    fig = _q(1271, "KT RECHTECK", Q650=1, Q218=40, Q219=30, Q201=-5, Q368=0, Q369=0)
    bnd = _q(1281, "KT BEGRENZUNG RECHTECK", Q651=80, Q652=60, Q655=0, Q656=15)
    r, t = run(_kt([fig, bnd], q370=0.4))
    pts = [(1 if m.kind != "rapid" else 0, a[0] + (b[0] - a[0]) * i / 20, a[1] + (b[1] - a[1]) * i / 20,
            a[2] + (b[2] - a[2]) * i / 20, 0, 0) for m in t.moves if m.start_known
           for a, b in zip(m.points, m.points[1:]) for i in range(21)]
    assert sum(1 for q in pts if q[3] < -1e-3) > 1000
    assert worst(pts, 50, 50) <= 0.02     # Tracer-Punkte: Bögen als Sehnen


def test_272_open_boundary_island_far_outside_changes_nothing():
    """Eine Insel ganz abseits der Begrenzung erweitert das Rohteil nicht: gleicher G-Code wie ohne sie."""
    from cyclo.dialog.pocket import region_from_polys
    isl = _rect_at(20, 20, 0, 0)
    a, _ = _ocm3(region_from_polys([], [isl], _rect_at(80, 60)), open_bnd=True)
    b, _ = _ocm3(region_from_polys([], [isl, _rect_at(20, 20, 150, 0)], _rect_at(80, 60)), open_bnd=True)
    assert a.lines == b.lines


# ---- K2: ANGLE außerhalb 0…90°
def _feed_runs(lines):
    """Vorschubsätze zwischen zwei Eilgängen -> Liste von Listen der Abtastpunkte."""
    runs, cur = [], []
    for s in _gcode_samples(lines):
        if s[0] == 0:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(s)
    if cur:
        runs.append(cur)
    return runs


@pytest.mark.parametrize("angle", [90.0, 120.0, 180.0, -3.0, 3.0, 0.0])
@pytest.mark.parametrize("cycle,q595", [(272, 1), (273, 1), (273, 0)])
def test_27x_entry_reaches_depth_for_any_angle_entry(angle, cycle, q595):
    """Tasche 60 × 40 mit Insel, Tiefe 5: Der tiefste Vorschubpunkt jedes Einstiegs (jeder Vorschubfolge
    zwischen zwei Eilgängen) ist die Solltiefe, und kein Satz mit XY-Bewegung fällt steiler als 45°
    (außer den 0,2 mm zwischen Verbindungshöhe und Tiefe). ANGLE außerhalb 0…90°: senkrecht mit dem
    Eintauchvorschub und mit Warnung. Vor der Korrektur (ANGLE = 90): Helix in der Luft, dann von Z+1 auf
    Z−4,96 über 0,29 mm mit Fräsvorschub; 273/Q595 = 0 fuhr den Boden auf Z−4,6."""
    from cyclo.dialog.pocket import region_from_polys
    reg = region_from_polys([_rect_at(60, 40)], [_circle_at(8, 0, 6, 32)])
    e, t = _ocm3(reg, cycle, angle=angle, pq={595: q595}, dq={369: 0.2} if cycle == 273 else None)
    runs = _feed_runs(e.lines)
    assert runs
    for run_ in runs:
        assert abs(min(s[3] for s in run_) + 5.0) < 1e-6, (run_[0], min(s[3] for s in run_))
    # Gefälle je Satz
    first = {}
    for s in _gcode_samples(e.lines):
        if s[0] != 0:
            a = first.setdefault(s[4], s)
            first[("end", s[4])] = s
    for n, a in list(first.items()):
        if isinstance(n, tuple):
            continue
        b = first[("end", n)]
        drop = a[3] - b[3]
        if drop > 0.25 and b[5] > 1e-6:
            assert drop <= b[5] + 1e-6, e.lines[n]
    bad = not 0.0 < angle < 90.0
    if not (cycle == 273 and q595 == 0 and angle == 0.0):   # Ringe ohne ANGLE: senkrecht ohne Meldung (alt)
        assert any("senkrecht" in m for m in e.warn) == bad
    if bad and angle:
        assert any("ANGLE" in m and "90" in m for m in e.warn)
    if bad:   # Einstich = eigener senkrechter Satz mit dem Eintauchvorschub (Q568 · Vorschub)
        f_plunge = "F500" if cycle == 272 else "F400"
        assert any(re.match(r"G1 Z-5 " + f_plunge + "$", ln) for ln in e.lines), e.lines[:12]


@pytest.mark.parametrize("angle", [90.0, 135.0, -3.0])
def test_helix_in_forces_end_depth(angle):
    """_helix_in mit unbrauchbarem Winkel: die Endtiefe wird trotzdem erreicht (vorher blieb Z auf z_from)."""
    from cyclo.dialog.cyclegen import Emit, Tool, _helix_in
    e = Emit(rel=False)
    e.rapid_xy(4.75, 0.0)
    _helix_in(e, Tool(2, 5.0, 50, angle), 0.0, 0.0, 4.75, 1.0, -5.0, "600", True)
    zs = [s[3] for s in _gcode_samples(["G0 X4.75 Y0 Z1"] + e.lines)]
    assert abs(min(zs) + 5.0) < 1e-9 and abs(zs[-1] + 5.0) < 1e-9


# ---- K3: Helix-Einfahrt von 273 / Q595 = 0
@pytest.mark.parametrize("size", [27.495, 27.497, 27.499, 27.501, 25.5, 20.0])
def test_273_rings_helix_entry_inside_allowed_area(size):
    """Quadrattasche, D10, Q370 = 0,4, Q368 = 0, 273 mit Q595 = 0: auch die Helix-Einfahrt bleibt in
    offset(reg, R). Bögen werden als Bögen ausgewertet. Vor der Korrektur: bis 10 µm in der Wand."""
    from cyclo.dialog.pocket import region_from_polys
    e, t = _ocm3(region_from_polys([_rect_at(size, size)], []), 273, pq={595: 0}, dq={369: 0.2})
    lim = size / 2 - 5.0
    worst = max(max(abs(x), abs(y)) - lim for g, x, y, z, n, s in _gcode_samples(e.lines) if g != 0 and z < -1e-3)
    assert worst <= 1e-4, worst            # Rundung der Ausgabe auf vier Stellen
    assert any(ln.startswith(("G2 ", "G3 ")) for ln in e.lines)


# ---- H1: BLK FORM bestimmt die Bahn
def test_27x_stock_open_side_warns_and_pocket_outside_stock_is_error():
    from cyclo.dialog.cyclegen import CycleError
    from cyclo.dialog.pocket import region_from_polys
    stock = (-75.0, -50.0, 75.0, 50.0)
    for cycle in (272, 273):
        dq = {369: 0.2} if cycle == 273 else None
        e, t = _ocm3(region_from_polys([_rect_at(60, 40, 75, 0)], []), cycle, stock=stock, dq=dq)
        assert any("BLK FORM" in m for m in e.warn)
        e, t = _ocm3(region_from_polys([_rect_at(60, 40)], []), cycle, stock=stock, dq=dq)
        assert not any("BLK FORM" in m for m in e.warn)
        with pytest.raises(CycleError, match="außerhalb des Rohteils"):
            _ocm3(region_from_polys([_rect_at(60, 40, 200, 0)], []), cycle, stock=stock, dq=dq)


# ---- H2: Werkzeug ohne ANGLE
_NOANGLE = {
    100002: (8.0, [(21.418, 38.184), (-19.041, 19.359), (-39.515, -18.96), (2.665, -28.099), (44.253, -8.057)], [],
             272, {370: 0.7, 577: 0.2, 202: 2.5, 575: 1}, {578: 0.1, 368: 0.3}),
    100011: (5.0, [(15.837, 21.423), (5.81, 33.868), (-11.382, 30.811), (-22.485, 18.55), (-25.583, 5.613),
                   (-32.169, -12.028), (-23.132, -19.987), (-4.72, -29.549), (11.209, -29.181), (21.202, -18.003),
                   (35.427, -4.826), (30.776, 10.629)],
             [[(-13.935, -14.221), (-15.261, -11.019), (-18.463, -9.692), (-21.665, -11.019), (-22.991, -14.221),
               (-21.665, -17.422), (-18.463, -18.749), (-15.261, -17.422)]],
             272, {370: 1.0, 577: 0.5, 202: 2.5, 575: 1}, {578: 0.5}),
    100040: (5.0, [(-29.564, 17.098), (-25.717, -10.131), (-16.409, -28.719), (8.598, -54.077), (40.937, -25.009),
                   (32.707, -0.28), (39.129, 34.403), (7.654, 44.034), (-19.669, 33.459)],
             [[(10.886, -15.153), (8.631, -9.708), (3.185, -7.452), (-2.26, -9.708), (-4.516, -15.153),
               (-2.26, -20.599), (3.185, -22.854), (8.631, -20.599)]],
             273, {370: 1.4, 577: 0.2, 575: 1}, {578: 0.2, 369: 0.2}),
}


@pytest.mark.parametrize("seed", list(_NOANGLE))
def test_27x_tool_without_angle_plans_fuzz_cases(seed):
    """Drei Zufallstaschen der unabhängigen Prüfung (Geometrie auf 1 µm gerundet), Werkzeug ohne ANGLE:
    vor der Korrektur CycleError „findet keinen sicheren Anfahrweg“, jetzt ein Plan mit Warnung."""
    from cyclo.dialog.pocket import region_from_polys
    r, pocket, islands, cycle, pq, dq = _NOANGLE[seed]
    e, t = _ocm3(region_from_polys([pocket], islands), cycle, r=r, angle=0.0, pq=pq, dq=dq)
    assert any("senkrecht" in m for m in e.warn)


def test_272_tool_without_angle_same_path_as_with_angle():
    """Rechteck 80 × 50, D10, Q370 = 0,4: ohne ANGLE senkrecht eintauchen und wie nach der Helix aufweiten –
    Bahn höchstens 10 % länger als mit ANGLE (vorher das 3,5-fache), Boden fertig."""
    from cyclo.dialog.pocket import region_from_polys
    from cyclo.sim.dexel import ToolShape, ZMap
    import numpy as np
    reg = region_from_polys([_rect_at(80, 50)], [])
    e0, t0 = _ocm3(reg, angle=0.0)
    e3, t3 = _ocm3(reg, angle=3.0)
    assert _feed_len(e0.lines) <= 1.1 * _feed_len(e3.lines), (_feed_len(e0.lines), _feed_len(e3.lines))
    assert len(e0.lines) <= 1.2 * len(e3.lines)
    assert len(_vertical_plunges(t0, below=-4.9)) == 1
    assert any("Engstelle" in m for m in e0.warn) == any("Engstelle" in m for m in e3.warn)
    zm = ZMap.from_stock((-41, -26, -10), (41, 26, 0))
    zm.run(t0.moves, {0: ToolShape(5.0), 2: ToolShape(5.0)})
    X = zm.x0 + (np.arange(zm.nx) + 0.5) * zm.res
    Y = zm.y0 + (np.arange(zm.ny) + 0.5) * zm.res
    gx, gy = np.meshgrid(X, Y)
    reach = np.hypot(np.maximum(abs(gx) - 35, 0), np.maximum(abs(gy) - 20, 0)) < 4.9
    assert ((zm.h > -4.95) & reach).sum() == 0


@pytest.mark.parametrize("w,h", [(50, 10.4), (50, 11), (50, 14)])
@pytest.mark.parametrize("cycle", [272, 273])
def test_27x_tool_without_angle_in_narrow_slot(w, h, cycle):
    """Schmale Nut, Werkzeug ohne ANGLE: ein senkrechter Einstich (mit Warnung), dann einmal entlang der Nut –
    kein Abbruch, kein zweiter Einstich ins Material, Bahn nicht länger als mit ANGLE, Boden fertig."""
    from cyclo.dialog.pocket import region_from_polys
    import numpy as np
    reg = region_from_polys([_rect_at(w, h)], [])
    dq = {369: 0.2} if cycle == 273 else None
    e0, t0 = _ocm3(reg, cycle, angle=0.0, dq=dq)
    e3, t3 = _ocm3(reg, cycle, angle=3.0, dq=dq)
    assert any("senkrecht" in m for m in e0.warn)
    assert _feed_len(e0.lines) <= _feed_len(e3.lines)
    bad, zm = _plunges_into_material(t0, 5.0, (-w / 2 - 1, -h / 2 - 1, -10), (w / 2 + 1, h / 2 + 1, 0))
    assert len({q[0][:2] for q in bad}) == 1, bad      # eine Einstichstelle (273: Vorposition + Einstich)
    X = zm.x0 + (np.arange(zm.nx) + 0.5) * zm.res
    Y = zm.y0 + (np.arange(zm.ny) + 0.5) * zm.res
    gx, gy = np.meshgrid(X, Y)
    reach = np.hypot(np.maximum(abs(gx) - (w / 2 - 5), 0), np.maximum(abs(gy) - (h / 2 - 5), 0)) < 4.9
    assert ((zm.h > -4.95) & reach).sum() == 0


# ---- H3: Ringnuten und Taschen mit Zapfen
@pytest.mark.parametrize("ro,ri,n_in", [(30, 14, 128), (30, 5, 64), (30, 19.25, 128), (30, 8, 128), (40, 20, 64)])
def test_272_ring_groove_and_boss_pocket_plan(ro, ri, n_in):
    """Ringnut / Kreistasche mit mittigem Zapfen, D10: vorher „Bahn verlässt die zulässige Fläche“ (der
    gemeldete Innenkreis war größer als der wirkliche Wandabstand), jetzt ein Plan; Werkzeugmitte bleibt
    zwischen Zapfen + R und Wand − R."""
    from cyclo.dialog.pocket import region_from_polys
    e, t = _ocm3(region_from_polys([_circle_at(0, 0, ro, 128)], [_circle_at(0, 0, ri, n_in)]))
    rr = [math.hypot(x, y) for g, x, y, z, n, s in _gcode_samples(e.lines) if g != 0 and z < -1e-3]
    assert len(rr) > 1000
    assert max(rr) <= ro - 5.0 + 1e-4 and min(rr) >= ri * math.cos(math.pi / n_in) + 5.0 - 0.006


@pytest.mark.parametrize("width", [11.0, 13.5, 16.0, 22.0, 26.0])
def test_inscribed_radius_never_exceeds_wall_distance(width):
    """inscribed(): der gemeldete Radius ist höchstens der wirkliche Abstand des Mittelpunkts zum Rand
    (vorher bei der Ringnut 16 mm: 2,9947 gemeldet, 2,9891 wirklich)."""
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.pocket import region_from_polys
    reg = region_from_polys([_circle_at(0, 0, 30, 128)], [_circle_at(0, 0, 30 - width, 128)])
    comp = ad.components(ad.offset(ad.offset(reg, 5.0), ad.WALL_MARGIN))[0]
    c, r_in = ad.inscribed(comp)
    A = [q for path in comp for q in ad._flt(path)]
    true = min(math.dist(c, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) for path in comp
               for a, b in zip(ad._flt(path), ad._flt(path)[1:] + ad._flt(path)[:1]))
    assert r_in <= true + 1e-9 and r_in <= min(math.dist(c, a) for a in A) + 1e-9
    assert r_in > 0.4 * (width - 10.0) / 2


# ---- M3, M4, N1
def test_272_tiny_helix_radius_warns():
    """Tasche 10,1 × 10,1 für D10: Helixradius 0,04 mm – praktisch senkrecht, jetzt mit Warnung."""
    from cyclo.dialog.pocket import region_from_polys
    e, t = _ocm3(region_from_polys([_rect_at(10.1, 10.1)], []))
    assert any("Helixradius" in m for m in e.warn)
    e, t = _ocm3(region_from_polys([_rect_at(60, 40)], []))
    assert not any("Helixradius" in m for m in e.warn)


@pytest.mark.parametrize("gap,warn", [(10.004, True), (10.012, True), (10.014, False), (10.03, False), (14.0, False)])
def test_272_skipped_passage_warns(gap, warn):
    """Durchgang zwischen Insel und Wand, 0…12 µm breiter als das Werkzeug: wird nicht gefräst (Sicherheitsrand)
    – jetzt mit Warnung. Breitere Durchgänge werden gefräst, ohne diese Warnung."""
    from cyclo.dialog.pocket import region_from_polys
    isl = [(-10, -25 + gap), (10, -25 + gap), (10, 5), (-10, 5)]
    e, t = _ocm3(region_from_polys([_rect_at(80, 50)], [isl]))
    assert any("Durchgang" in m for m in e.warn) == warn


@pytest.mark.parametrize("pq,dq,word", [({200: -1}, {}, "Q200"), ({}, {369: -0.5}, "Q369"), ({}, {369: 5.0}, "Q369"),
                                        ({}, {369: 7.0}, "Q369"), ({}, {368: -0.1}, "Q368"), ({568: 0}, {}, "Q568"),
                                        ({}, {201: 5.0}, "Q201")])
@pytest.mark.parametrize("cycle", [272, 273])
def test_27x_input_checks(pq, dq, word, cycle):
    from cyclo.dialog.cyclegen import CycleError
    from cyclo.dialog.pocket import region_from_polys
    with pytest.raises(CycleError, match=word):
        _ocm3(region_from_polys([_rect_at(60, 40)], []), cycle, pq=pq, dq=dq)


# ------------------------------------------------------------------ Runde 4: Ringstrategie, Einstieg und Durchgänge
@pytest.mark.parametrize("width", [10.4, 11.0, 12.0])
@pytest.mark.parametrize("allowance", [0.2, 1.0, 4.0])
@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("rotation", [0, 17])
def test_273_rings_ramp_through_floor_allowance(width, allowance, direction, rotation):
    """Der fertige G-Code darf auch bei großem Bodenaufmaß nicht senkrecht in die Nut eintauchen."""
    import numpy as np
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.pocket import region_from_polys
    poly = _rot_poly(_rect_at(50, width), rotation)
    reg = region_from_polys([poly], [])
    e, t = _ocm3(reg, 273, pq={595: 0, 351: direction}, dq={369: allowance})
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    bad, zm = _plunges_into_material(t, 5.0, (min(xs) - 1, min(ys) - 1, -10),
                                    (max(xs) + 1, max(ys) + 1, -5 + allowance))
    assert bad == [], bad
    assert not zm.events
    assert min(p[2] for m in t.moves for p in m.points) == pytest.approx(-5, abs=1e-4)
    ramps = [m for m in t.moves if m.kind != "rapid" and m.points[-1][2] < m.points[0][2] - 1e-6
             and math.dist(m.points[0][:2], m.points[-1][:2]) > 1e-6]
    assert len(ramps) >= 2
    for m in ramps:
        a, b = m.points[0], m.points[-1]
        assert math.degrees(math.atan2(a[2] - b[2], math.dist(a[:2], b[:2]))) <= 3.05
        assert m.feed == pytest.approx(400)
    samples = _gcode_samples(e.lines)
    pts = np.array([(x, y) for g, x, y, z, n, s in samples if z < 0])
    allowed = ad.offset(reg, 5)
    assert ad.Region(ad.offset(allowed, -0.001), shrink=0).points_inside(pts).all()
    # Erreichbarer Boden, ohne scharfe werkzeugbedingt nicht erreichbare Ecken, muss fertig sein.
    X, Y = np.meshgrid(zm.x0 + (np.arange(zm.nx) + .5) * zm.res,
                       zm.y0 + (np.arange(zm.ny) + .5) * zm.res)
    reach = ad.Region(ad.offset(allowed, -4.85), shrink=0).points_inside(
        np.stack([X.ravel(), Y.ravel()], 1)).reshape(X.shape)
    assert reach.any() and not ((zm.h > -4.95) & reach).any()


@pytest.mark.parametrize("cycle,strategy", [(272, 1), (273, 0), (273, 1)])
@pytest.mark.parametrize("gap,skipped", [(10.004, True), (10.012, True), (10.02, False)])
def test_27x_passage_warning_matches_emitted_coverage(cycle, strategy, gap, skipped):
    """Warnung und tatsächlicher Materialrest im Durchgang müssen für alle drei Wege übereinstimmen."""
    from cyclo.dialog.pocket import region_from_polys
    isl = [(-10, -25 + gap), (10, -25 + gap), (10, 5), (-10, 5)]
    reg = region_from_polys([_rect_at(80, 50)], [isl])
    e, t = _ocm3(reg, cycle, pq={595: strategy}, dq={369: 1 if cycle == 273 else 0})
    assert min(p[2] for m in t.moves for p in m.points) == pytest.approx(-5, abs=1e-4)
    # Unabhängige Probe des Werkzeug-Fußabdrucks im mittleren Durchgang, am gerundeten G-Code.
    # Punkt (0,-20) ist mit D10 erreichbar, liegt weder an einer Ecken- noch an einer Saumtoleranz.
    pts = [(x, y) for g, x, y, z, n, s in _gcode_samples(e.lines, .05) if g != 0 and z <= -4.9999]
    covered = any(math.hypot(x, y + 20) < 5 - .001 for x, y in pts)
    assert covered is not skipped
    assert any("Durchgang" in w for w in e.warn) is skipped


@pytest.mark.parametrize("angle,word", [(0, "ANGLE fehlt"), (90, "nicht zwischen"), (-3, "nicht zwischen")])
def test_273_rings_vertical_without_usable_angle_warns(angle, word):
    from cyclo.dialog.pocket import region_from_polys
    e, t = _ocm3(region_from_polys([_rect_at(50, 10.4)], []), 273, angle=angle,
                 pq={595: 0}, dq={369: 1})
    assert sum(word in w for w in e.warn) == 1
    assert min(p[2] for m in t.moves for p in m.points) == pytest.approx(-5)


def test_273_rings_no_room_for_entry_warns():
    from cyclo.dialog.pocket import region_from_polys
    e, t = _ocm3(region_from_polys([_rect_at(10.03, 10.03)], []), 273, pq={595: 0}, dq={369: 1})
    assert any("Kein Platz für Helix oder Rampe" in w for w in e.warn)
    assert min(p[2] for m in t.moves for p in m.points) == pytest.approx(-5)


def test_273_rings_failed_entry_search_does_not_allow_vertical(monkeypatch):
    """Fehlgeschlagene geometrische Nachweise sind kein Beweis für eine zu kleine Tasche."""
    from cyclo.dialog import adaptive as ad
    from cyclo.dialog.cyclegen import CycleError, Emit, P, Tool
    from cyclo.dialog.pocket import ocm_cycle, region_from_polys
    monkeypatch.setattr(ad, "prims_within", lambda *args, **kw: False)
    e = Emit(rel=False)
    with pytest.raises(CycleError, match="weder Helix noch Rampe"):
        ocm_cycle(273, P({595: 0, 385: 800, 253: 750, 568: .5, 200: 2}),
                  P({201: -5, 203: 0, 368: 0, 369: 1, 260: 50}),
                  region_from_polys([_rect_at(50, 10.4)], []), Tool(2, 5, 50, 3), e, False)
    assert not any(s.startswith(("G1 ", "G2 ", "G3 ")) for s in e.lines)
