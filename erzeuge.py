#!/usr/bin/env python3
"""Vergleichsteile für 272 KT RAEUMEN / 273 KT BODEN SCHLICHTEN gegen Fusion 360.

Erzeugt aus *einer* Geometriebeschreibung je Teil:
  step/<TEIL>.step      Fertigteil (Rohteil minus Bearbeitung), Nullpunkt = Rohteil links vorne oben
  stl/<TEIL>.stl        dasselbe als STL (für die Abtragsprüfung)
  dialog/<TEIL>.h       Dialogprogramm mit 272 + 273 (Konturen als LBL)
  gcode/<TEIL>_272.ngc  von LCNC-Cyclo berechneter G-Code nur 272
  gcode/<TEIL>_273.ngc  nur 273
  gcode/<TEIL>.ngc      beide Zyklen nacheinander
  pruefung.txt          Abtragssimulation: Eilgang im Material, Konturverletzung, Restmaterial

Aufruf (im Ordner cyclo/):  python3 examples/trochoidal_vergleich/erzeuge.py
Braucht: cadquery, pyclipper, numpy.
"""

from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

# ------------------------------------------------------------------ gemeinsame Vorgaben (Fusion gleich einstellen)
TOOL = dict(T=2, D=10.0, ANGLE=3.0, L=50.0)        # Schaftfräser D10, Eintauchwinkel 3°
S, F_RAUM, F_SCHL, F_POS = 8000, 1500, 800, 750
Q370_272, Q370_273 = 0.4, 1.0                       # seitliche Zustellung k = Q370 · R
AUFMASS_SEITE, AUFMASS_BODEN = 0.3, 0.2


# ------------------------------------------------------------------ Konturbeschreibung
# Ecke ("P", x, y, rnd) – rnd > 0 rundet die Ecke (nur zwischen zwei Geraden)
# Bogen ("ARC", vx, vy) – die Kante zur nächsten Ecke ist ein Kreisbogen durch (vx, vy)
def _circ(p0, pv, p1):
    ax, ay = p0
    bx, by = pv
    cx, cy = p1
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    ccw = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 0
    return (ux, uy), ccw


def elements(spec):
    """-> [("L", p0, p1) | ("A", p0, p1, c, ccw)], geschlossen, gegen den Uhrzeigersinn."""
    verts, arcs = [], {}
    for it in spec:
        if it[0] == "P":
            verts.append(((it[1], it[2]), it[3]))
        else:
            arcs[len(verts) - 1] = (it[1], it[2])
    n = len(verts)
    pts = [v[0] for v in verts]
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    assert area > 0, "Kontur gegen den Uhrzeigersinn angeben"
    # Rundungen: Tangentenpunkte je Ecke
    start = {}  # Ecke i -> (Punkt, an dem die abgehende Kante beginnt)
    end = {}    # Ecke i -> Punkt, an dem die ankommende Kante endet
    fil = {}
    for i, (p, r) in enumerate(verts):
        a, b = pts[i - 1], pts[(i + 1) % n]
        if r <= 0:
            start[i] = end[i] = p
            continue
        assert (i - 1) % n not in arcs and i not in arcs, "Rundung nur zwischen Geraden"
        ua = ((a[0] - p[0]), (a[1] - p[1]))
        ub = ((b[0] - p[0]), (b[1] - p[1]))
        la, lb = math.hypot(*ua), math.hypot(*ub)
        ua, ub = (ua[0] / la, ua[1] / la), (ub[0] / lb, ub[1] / lb)
        ang = math.acos(max(-1, min(1, ua[0] * ub[0] + ua[1] * ub[1])))
        d = r / math.tan(ang / 2)
        assert d < min(la, lb) / 2, f"Rundung {r} an {p} zu groß"
        t1 = (p[0] + ua[0] * d, p[1] + ua[1] * d)
        t2 = (p[0] + ub[0] * d, p[1] + ub[1] * d)
        bis = (ua[0] + ub[0], ua[1] + ub[1])
        lbis = math.hypot(*bis)
        h = r / math.sin(ang / 2)
        c = (p[0] + bis[0] / lbis * h, p[1] + bis[1] / lbis * h)
        turn = (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])
        end[i], start[i] = t1, t2
        fil[i] = (t1, t2, c, turn > 0)
    out = []
    for i in range(n):
        j = (i + 1) % n
        p0, p1 = start[i], end[j]
        if i in arcs:
            c, ccw = _circ(p0, arcs[i], p1)
            out.append(("A", p0, p1, c, ccw))
        else:
            out.append(("L", p0, p1))
        if j in fil:
            t1, t2, c, ccw = fil[j]
            out.append(("A", t1, t2, c, ccw))
    # mit einer Geraden beginnen (Startpunkt der Kontur)
    k = next(i for i, e in enumerate(out) if e[0] == "L")
    return out[k:] + out[:k]


def f(v):
    s = f"{v:+.4f}".rstrip("0").rstrip(".")
    return s if s not in ("+", "-", "+0", "-0") else "+0"


def dialog_lbl(label, elems, comp, nr):
    lines = [f"{nr} LBL {label}"]
    nr += 1
    p = elems[0][1]
    lines.append(f"{nr} L X{f(p[0])} Y{f(p[1])} {comp}")
    nr += 1
    for e in elems:
        if e[0] == "L":
            lines.append(f"{nr} L X{f(e[2][0])} Y{f(e[2][1])}")
            nr += 1
        else:
            c = e[3]
            lines.append(f"{nr} CC X{f(c[0])} Y{f(c[1])}")
            lines.append(f"{nr + 1} C X{f(e[2][0])} Y{f(e[2][1])} DR{'+' if e[4] else '-'}")
            nr += 2
    lines.append(f"{nr} LBL 0")
    return lines, nr + 1


def cq_face(elems):
    import cadquery as cq
    wp = cq.Workplane("XY").moveTo(*elems[0][1])
    for e in elems:
        if e[0] == "L":
            wp = wp.lineTo(*e[2])
        else:
            p0, p1, c, ccw = e[1], e[2], e[3], e[4]
            a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
            a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
            sw = a1 - a0
            if ccw:
                while sw <= 0:
                    sw += 2 * math.pi
            else:
                while sw >= 0:
                    sw -= 2 * math.pi
            r = math.dist(p0, c)
            m = (c[0] + r * math.cos(a0 + sw / 2), c[1] + r * math.sin(a0 + sw / 2))
            wp = wp.threePointArc(m, p1)
    return wp.close()


# ------------------------------------------------------------------ Teile
STOCK_Z = -30.0

TEILE = {
    "T1_TASCHE_GESCHLOSSEN": dict(
        stock=(150, 100),
        info="Unregelmäßige geschlossene Tasche, Tiefe 12, eine Innenecke mit Einschnürung",
        ops=[dict(kind="pocket", depth=-12, q202=12,
                  pocket=[("P", 25, 18, 6), ("P", 92, 12, 10), ("P", 128, 30, 0), ("ARC", 140, 55),
                          ("P", 118, 82, 0), ("P", 72, 88, 12), ("P", 58, 62, 5), ("P", 30, 80, 6),
                          ("P", 14, 48, 8)])]),
    "T2_TASCHE_SEITLICH_OFFEN": dict(
        stock=(150, 100),
        info="Tasche nach rechts (X+150) offen, Tiefe 10; Kontur läuft 12 mm über die Rohteilkante hinaus",
        ops=[dict(kind="pocket", depth=-10, q202=10,
                  pocket=[("P", 28, 30, 8), ("P", 85, 18, 6), ("P", 162, 18, 0), ("P", 162, 78, 0),
                          ("P", 120, 78, 8), ("P", 95, 70, 0), ("ARC", 70, 90), ("P", 40, 82, 0),
                          ("P", 18, 55, 6)])]),
    "T3_AUSSENKONTUR": dict(
        stock=(140, 110),
        info="Unregelmäßige Außenkontur (Insel in Begrenzung = Rohteil), Tiefe 16 in 2 Zustellungen",
        ops=[dict(kind="outside", depth=-16, q202=8,
                  island=[("P", 18, 20, 5), ("P", 78, 10, 15), ("P", 122, 28, 0), ("ARC", 132, 58),
                          ("P", 112, 88, 0), ("P", 68, 98, 10), ("P", 48, 72, 6), ("P", 16, 82, 4),
                          ("P", 8, 48, 6)])]),
    "T4_INNEN_UND_AUSSEN": dict(
        stock=(160, 120),
        info="Bauteil mit Außenkontur (Tiefe 16, 2 Zustellungen) und Innentasche mit Insel (Tiefe 10)",
        ops=[dict(kind="outside", depth=-16, q202=8,
                  island=[("P", 15, 15, 8), ("P", 95, 8, 12), ("P", 148, 22, 0), ("ARC", 156, 62),
                          ("P", 140, 105, 0), ("P", 80, 112, 15), ("P", 55, 95, 6), ("P", 20, 108, 5),
                          ("P", 8, 60, 10)]),
             dict(kind="pocket", depth=-10, q202=10,
                  pocket=[("P", 35, 30, 6), ("P", 100, 28, 8), ("P", 125, 50, 5), ("P", 118, 85, 10),
                          ("P", 70, 92, 0), ("ARC", 45, 82), ("P", 30, 60, 0)],
                  island=[("P", 65, 50, 4), ("P", 95, 48, 4), ("P", 80, 72, 4)])]),
}


def rect(w, h):
    return [("P", 0, 0, 0), ("P", w, 0, 0), ("P", w, h, 0), ("P", 0, h, 0)]


# ------------------------------------------------------------------ Dialogprogramm
def q(lines):
    return " ~\n".join(f"  {s}" for s in lines)


def cyc271(depth, first):
    return q([f"Q203=+0 ;Oberfläche", f"Q201={f(depth)} ;Tiefe", f"Q368={f(AUFMASS_SEITE)} ;Aufmaß seitlich",
              f"Q369={f(AUFMASS_BODEN)} ;Aufmaß Boden", "Q260=+50 ;Sichere Höhe", "Q578=+0.2 ;Faktor Innenecken",
              f"Q569=+{first} ;Erste Figur"])


def cyc272(q202):
    return q([f"Q202={f(q202)} ;Zustellung", f"Q370={f(Q370_272)} ;Überlappung", f"Q207=+{F_RAUM} ;Vorschub Fräsen",
              "Q568=+0.6 ;Faktor Eintauchen", f"Q253=+{F_POS} ;Vorschub Positionieren", "Q200=+2 ;Sicherheitsabstand",
              "Q438=-1 ;Räumwerkzeug", "Q577=+0.2 ;Faktor Anfahrradius", "Q351=+1 ;Fräsrichtung",
              "Q576=+0 ;Drehzahl", "Q579=+1 ;Faktor Eintauchdrehzahl", "Q575=+0 ;Zustellfolge"])


def cyc273():
    return q([f"Q370={f(Q370_273)} ;Überlappung", f"Q385=+{F_SCHL} ;Vorschub Schlichten", "Q568=+0.3 ;Faktor Eintauchen",
              f"Q253=+{F_POS} ;Vorschub Positionieren", "Q200=+2 ;Sicherheitsabstand", "Q438=-1 ;Räumwerkzeug",
              "Q595=+1 ;Schlichtart", "Q577=+0.2 ;Faktor Anfahrradius"])


def program(name, teil, cycles=(272, 273)):
    w, h = teil["stock"]
    L = [f"0 BEGIN PGM {name} MM", f"1 BLK FORM 0.1 Z X+0 Y+0 Z{f(STOCK_Z)}", f"2 BLK FORM 0.2 X+{w} Y+{h} Z+0",
         f"3 * - {teil['info']}", f"4 TOOL CALL {TOOL['T']} Z S{S} F{F_RAUM}", "5 L Z+50 R0 FMAX M3"]
    nr = 6
    lbls, lab = [], 1
    for op in teil["ops"]:
        labels = []
        if op["kind"] == "outside":
            labels.append((lab, elements(rect(w, h)), "RL"))       # Begrenzung = Rohteil
            labels.append((lab + 1, elements(op["island"]), "RR"))  # Insel (gegen Uhrzeiger mit RR)
            first = 1
        else:
            labels.append((lab, elements(op["pocket"]), "RL"))      # Tasche (gegen Uhrzeiger mit RL)
            if op.get("island"):
                labels.append((lab + 1, elements(op["island"]), "RR"))
            first = 0
        lab += len(labels)
        lbls += labels
        L.append(f"{nr} * - {'Außenkontur (Begrenzung + Insel)' if first else 'Tasche'}")
        L.append(f"{nr + 1} CYCL DEF 14.0 KONTUR")
        L.append(f"{nr + 2} CYCL DEF 14.1 KONTURLABEL " + " /".join(str(x[0]) for x in labels))
        L.append(f"{nr + 3} CYCL DEF 271 KT DATEN ~\n{cyc271(op['depth'], first)}")
        nr += 4
        if 272 in cycles:
            L.append(f"{nr} CYCL DEF 272 KT RAEUMEN ~\n{cyc272(op['q202'])}")
            L.append(f"{nr + 1} CYCL CALL")
            nr += 2
        if 273 in cycles:
            L.append(f"{nr} CYCL DEF 273 KT BODEN SCHLICHTEN ~\n{cyc273()}")
            L.append(f"{nr + 1} CYCL CALL")
            nr += 2
    L.append(f"{nr} L Z+100 R0 FMAX M30")
    nr += 1
    for label, el, comp in lbls:
        ll, nr = dialog_lbl(label, el, comp, nr)
        L += ll
    L.append(f"{nr} END PGM {name} MM")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ CAD
def solid(teil):
    import cadquery as cq
    w, h = teil["stock"]
    body = cq.Workplane("XY").box(w, h, -STOCK_Z, centered=False).translate((0, 0, STOCK_Z))
    for op in teil["ops"]:
        d = -op["depth"]
        if op["kind"] == "outside":
            big = cq.Workplane("XY").box(w + 40, h + 40, d, centered=False).translate((-20, -20, -d))
            keep = cq_face(elements(op["island"])).extrude(d).translate((0, 0, -d))
            body = body.cut(big.cut(keep))
        else:
            cut = cq_face(elements(op["pocket"])).extrude(d).translate((0, 0, -d))
            if op.get("island"):
                cut = cut.cut(cq_face(elements(op["island"])).extrude(d).translate((0, 0, -d)))
            body = body.cut(cut)
    return body


# ------------------------------------------------------------------ Übersetzen + Prüfen
def translate(text, name):
    from cyclo.dialog import TranslatorConfig, translate as tr
    r = tr(text, name, TranslatorConfig(tools={TOOL["T"]: {"R": TOOL["D"] / 2, "L": TOOL["L"], "ANGLE": TOOL["ANGLE"]}}))
    if r.errors:
        raise SystemExit(f"{name}: " + "; ".join(str(e) for e in r.errors))
    return r


def check(r, stl, teil, ops_done):
    """Abtragssimulation (Z-Map): Eilgang im Material, Verletzung der Fertigkontur, Restmaterial."""
    import numpy as np
    from cyclo.sim.dexel import ToolShape, ZMap, load_stl, target_heights
    from cyclo.sim.tracer import Tracer
    t = Tracer(tool_lengths={TOOL["T"]: TOOL["L"]}).trace_text(r.gcode)
    if t.errors:
        return [f"Tracer: {e}" for e in t.errors], {}
    zm = ZMap.from_stock_dict(r.stock, max_cells=1_500_000)
    zm.run(t.moves, {TOOL["T"]: ToolShape(TOOL["D"] / 2)})
    tgt = target_heights(zm, load_stl(stl))
    ok = np.isfinite(tgt)
    diff = np.where(ok, zm.h - tgt, 0.0)
    rep = []
    for e in zm.events:
        rep.append(f"Befund Zeile {e.line}: {e.kind} {e.text}")
    gouge = float(-diff.min()) if ok.any() else 0.0
    lim = (AUFMASS_BODEN if 273 not in ops_done else 0.0) + 0.05
    floor = ok & (tgt < -0.5)  # Böden (Oberseite Z0 bleibt unberührt)
    # Band unter dem Seitenaufmaß an den Wänden nicht mitzählen (Boden um 0,6 mm verkleinert)
    for _ in range(int(math.ceil(0.6 / zm.res))):
        fl = floor.copy()
        fl[1:, :] &= floor[:-1, :]
        fl[:-1, :] &= floor[1:, :]
        fl[:, 1:] &= floor[:, :-1]
        fl[:, :-1] &= floor[:, 1:]
        floor = fl
    rest_area = float(((diff > lim) & floor).sum()) * zm.res ** 2
    # Länge und Zeit
    feed_len = rapid_len = 0.0
    for m in t.moves:
        L = sum(math.dist(m.points[i][:3], m.points[i + 1][:3]) for i in range(len(m.points) - 1))
        if m.kind == "rapid":
            rapid_len += L
        else:
            feed_len += L
    stats = dict(gouge=gouge, rest=rest_area, feed_len=feed_len, rapid_len=rapid_len,
                 lines=len([ln for ln in r.gcode_lines if ln and not ln.startswith("(")]),
                 cell=zm.res)
    return rep, stats


def main():
    for sub in ("step", "stl", "dialog", "gcode"):
        os.makedirs(os.path.join(HERE, sub), exist_ok=True)
    import cadquery as cq
    report = ["Abtragsprüfung LCNC-Cyclo (Z-Map, Werkzeug D10). Werte in mm.",
              "Verletzung = tiefster Schnitt unter die Fertigkontur (Rasterauflösung beachten),",
              "Restfläche Boden = Bodenfläche (ohne 0,6-mm-Band an den Wänden), auf der mehr als Aufmaß + 0,05 stehen blieb",
              "(Ecken mit RND < Fräserradius bleiben zwangsläufig stehen).", ""]
    for name, teil in TEILE.items():
        body = solid(teil)
        sp = os.path.join(HERE, "step", f"{name}.step")
        stl = os.path.join(HERE, "stl", f"{name}.stl")
        cq.exporters.export(body, sp)
        cq.exporters.export(body, stl, tolerance=0.01, angularTolerance=0.05)
        txt = program(name, teil)
        open(os.path.join(HERE, "dialog", f"{name}.h"), "w").write(txt)
        for cyc, suffix in (((272,), "_272"), ((273,), "_273"), ((272, 273), "")):
            r = translate(program(name, teil, cyc), f"{name}{suffix}.h")
            open(os.path.join(HERE, "gcode", f"{name}{suffix}.ngc"), "w").write(r.gcode)
            if cyc == (273,):
                continue  # 273 allein (ohne vorheriges Räumen) wird nicht simuliert
            rep, st = check(r, stl, teil, cyc)
            report.append(f"{name}{suffix or ' (272+273)'}: Zeilen {st.get('lines')}, Vorschubweg {st.get('feed_len', 0):.0f}, "
                          f"Eilweg {st.get('rapid_len', 0):.0f}, Verletzung {st.get('gouge', 0):.3f}, Restfläche Boden {st.get('rest', 0):.0f} mm² (Raster {st.get('cell', 0):.2f})")
            report += [f"    {x}" for x in rep[:20]]
            print(report[-1 - len(rep[:20])])
    open(os.path.join(HERE, "pruefung.txt"), "w").write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
