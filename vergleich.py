#!/usr/bin/env python3
"""Vergleich LCNC-Cyclo (272/273) gegen Fusion 360 (Adaptives 2D-Schruppen / 2D-Versatz-Schruppen).

Beide Programme laufen durch dieselbe Abtragssimulation (Z-Map, Raster 0,1 mm). Je Arbeitsgang:
  Zeit        Vorschubwege mit programmiertem F, Eilgang mit RAPID mm/min, ohne Beschleunigung
  Zeilen      Bewegungssätze G0/G1/G2/G3 (ohne Kommentare)
  Rückzüge    Wechsel aus dem Material (Z < Oberfläche) über die Oberfläche
  Luftschnitt Vorschubweg auf Tiefe ohne Materialkontakt
  Umschlingung  Winkel des Werkzeugumfangs im Material je Bahnpunkt (Abtastung 0,25 mm):
              Mittel, 95-%-Wert, Maximum, Anteil über Sollwert acos(1 - k/R) + 15°
Am Ende: Verletzung der Fertigkontur und Restfläche Boden gegen das STL.

Fusion hat den Nullpunkt in Rohteilmitte oben – wird auf Rohteilecke links vorne verschoben.

Aufruf (im Ordner dieses Repos):  python3 vergleich.py   -> vergleich.md
"""

from __future__ import annotations

import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "projekt"))
sys.path.insert(0, os.path.join(HERE, "projekt", "examples", "trochoidal_vergleich"))

from cyclo.sim.dexel import ToolShape, ZMap, load_stl, target_heights  # noqa: E402
from cyclo.sim.tracer import Tracer  # noqa: E402
import erzeuge as E  # noqa: E402

R = E.TOOL["D"] / 2
K = E.Q370_272 * R
SOLL = math.degrees(math.acos(1 - K / R))
RAPID = 10000.0  # mm/min für die Zeitschätzung
STEP = 0.25


def fusion_source(name):
    """Fusion-Programm: Maschinenzeilen raus, Arbeitsgänge als Kommentarzeilen markiert."""
    w, h = E.TEILE[name]["stock"]
    src = open(os.path.join(HERE, "gcode", f"{name}_fusion.ngc")).read().split("\n")
    out, ops = [], []
    for ln in src:
        if re.search(r"G53|M428|M429|B0\.|^%", ln):
            continue
        m = re.match(r"^\(([A-Z0-9ÄÖÜ \-]+)\)$", ln.strip())
        if m and ("SCHRUPPEN" in m.group(1) or "SCHLICHT" in m.group(1) or "TASCHE" in m.group(1)):
            ops.append((len(out), m.group(1).title()))
        out.append(ln)
    return "\n".join(out), ops, (w / 2, h / 2)


def cyclo_source(name):
    txt = open(os.path.join(HERE, "gcode", f"{name}.ngc")).read()
    ops = []
    for i, ln in enumerate(txt.split("\n")):
        m = re.match(r"^o<(cyc27[23])_\d+> call", ln.strip())
        if m:
            ops.append((i, {"cyc272": "272 KT RAEUMEN", "cyc273": "273 KT BODEN SCHLICHTEN"}[m.group(1)]))
    return txt, ops, (0.0, 0.0)


def count_lines(txt, ops, n_lines):
    """Bewegungssätze je Arbeitsgang. Fusion: nach Zeilenbereich; Cyclo: im jeweiligen Unterprogramm."""
    lines = txt.split("\n")
    res = {}
    if ops and ops[0][1].startswith("27"):
        cur = None
        for ln in lines:
            m = re.match(r"^o<(cyc27[23]_\d+)> sub", ln.strip())
            if m:
                cur = m.group(1)
                res[cur] = [0, 0, 0]
                continue
            if re.match(r"^o<.*> endsub", ln.strip()):
                cur = None
                continue
            if cur:
                _tally(res[cur], ln)
        out = {}
        for i, (ln_no, name) in enumerate(ops):
            sub = re.match(r"^o<(cyc27[23]_\d+)> call", lines[ln_no].strip()).group(1)
            out[i] = res[sub]
        return out
    out = {}
    bounds = [o[0] for o in ops] + [len(lines)]
    for i in range(len(ops)):
        c = [0, 0, 0]
        mode = None
        for ln in lines[bounds[i]:bounds[i + 1]]:
            mode = _tally(c, ln, mode)
        out[i] = c
    return out


def _tally(c, ln, mode=None):
    """c = [G0, G1, G2/G3]; Fusion schreibt Folgesätze ohne G-Wort (modal)."""
    s = ln.strip()
    if not s or s.startswith("("):
        return mode
    m = re.search(r"\bG0?([0-3])\b", s)
    if m:
        mode = int(m.group(1))
    if mode is not None and re.search(r"[XYZ]-?\d", s):
        c[0 if mode == 0 else 1 if mode == 1 else 2] += 1
    return mode


def engagement_at(zm, x, y, z, n=72):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    px, py = x + (R - 0.05) * np.cos(a), y + (R - 0.05) * np.sin(a)
    i = np.floor((px - zm.x0) / zm.res).astype(int)
    j = np.floor((py - zm.y0) / zm.res).astype(int)
    ok = (i >= 0) & (i < zm.nx) & (j >= 0) & (j < zm.ny)
    h = np.full(n, -1e9)
    h[ok] = zm.h[j[ok], i[ok]]
    mat = np.nan_to_num(h, nan=-1e9) > z + 0.02
    return mat.mean() * 360.0


def analyse(name, which):
    txt, ops, off = fusion_source(name) if which == "fusion" else cyclo_source(name)
    t = Tracer(tool_lengths={1: E.TOOL["L"], 2: E.TOOL["L"]}).trace_text(txt)
    assert not t.errors, t.errors
    w, h = E.TEILE[name]["stock"]
    zm = ZMap.from_stock((0, 0, E.STOCK_Z), (w, h, 0), max_cells=1_500_000)
    tool = ToolShape(R)
    starts = [o[0] for o in ops]

    def op_of(line):
        k = 0
        for i, s in enumerate(starts):
            if line >= s:
                k = i
        return k
    st = {i: dict(name=ops[i][1], feed_t=0.0, rapid_t=0.0, feed_len=0.0, rapid_len=0.0, retracts=0, air=0.0,
                  eng=[], eng_len=[]) for i in range(len(ops))}
    below = False
    for mv in t.moves:
        if mv.line < starts[0] or not mv.start_known:
            continue  # vor dem ersten Arbeitsgang bzw. Startpunkt unbekannt (nach Werkzeugwechsel)
        o = st[op_of(mv.line)]
        pts = [(p[0] + off[0], p[1] + off[1], p[2]) for p in mv.points]
        L = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        if mv.kind == "rapid":
            o["rapid_len"] += L
            o["rapid_t"] += L / RAPID * 60
        else:
            o["feed_len"] += L
            o["feed_t"] += L / (mv.feed or RAPID) * 60
        for a, b in zip(pts, pts[1:]):
            seg = math.dist(a, b)
            nseg = max(1, int(math.ceil(seg / STEP)))
            prev = a
            for s_ in range(1, nseg + 1):
                q = tuple(a[c] + (b[c] - a[c]) * s_ / nseg for c in range(3))
                if mv.kind != "rapid" and q[2] < -0.3 and abs(q[2] - prev[2]) < 0.05:
                    e = engagement_at(zm, q[0], q[1], q[2])
                    d = math.dist(prev, q)
                    o["eng"].append(e)
                    o["eng_len"].append(d)
                    if e < 1.0:
                        o["air"] += d
                zm.cut(prev, q, tool, rapid=mv.kind == "rapid", line=mv.line)
                prev = q
            if a[2] < 0 and b[2] >= 0.5 and below:
                o["retracts"] += 1
                below = False
            if b[2] < 0:
                below = True
    tgt = target_heights(zm, load_stl(os.path.join(HERE, "stl", f"{name}.stl")))
    ok = np.isfinite(tgt)
    diff = np.where(ok, zm.h - tgt, 0.0)
    floor = ok & (tgt < -0.5)
    for _ in range(int(math.ceil(0.6 / zm.res))):
        fl = floor.copy()
        fl[1:, :] &= floor[:-1, :]
        fl[:-1, :] &= floor[1:, :]
        fl[:, 1:] &= floor[:, :-1]
        fl[:, :-1] &= floor[:, 1:]
        floor = fl
    final = dict(gouge=max(0.0, float(-diff.min())), rest=float(((diff > 0.05) & floor).sum()) * zm.res ** 2,
                 rapid_events=len([e for e in zm.events if e.kind == "rapid"]))
    cnt = count_lines(txt, ops, None)
    for i, o in st.items():
        o["g0"], o["g1"], o["g23"] = cnt[i]
        e = np.asarray(o["eng"])
        wgt = np.asarray(o["eng_len"])
        cut = e > 1.0
        if cut.any():
            o["eng_mean"] = float(np.average(e[cut], weights=wgt[cut]))
            o["eng_p95"] = float(np.percentile(e[cut], 95))
            o["eng_max"] = float(e.max())
            o["eng_over"] = float(wgt[cut & (e > SOLL + 15)].sum() / max(wgt[cut].sum(), 1e-9) * 100)
        else:
            o["eng_mean"] = o["eng_p95"] = o["eng_max"] = o["eng_over"] = 0.0
    return st, final


def mmss(s):
    return f"{int(s // 60)}:{int(round(s % 60)):02d}"


def main():
    out = ["# Vergleich LCNC-Cyclo gegen Fusion 360", "",
           f"Werkzeug D{E.TOOL['D']:g}, seitliche Zustellung 272: {K:g} mm (Soll-Umschlingung acos(1 − k/R) = {SOLL:.0f}°).",
           f"Zeit: Vorschub mit programmiertem F, Eilgang {RAPID:.0f} mm/min, ohne Beschleunigung "
           "(viele kurze Sätze sind real langsamer).",
           "Umschlingung: Winkel des Werkzeugumfangs im Material, je 0,25 mm Bahn, nur waagerechte Bahn auf Tiefe. "
           "„> Soll“ = Anteil des Schnittwegs mit mehr als Soll + 15°.", "",
           "| Teil | Programm | Arbeitsgang | Zeit | Vorschubweg | Eilweg | G0 | G1 | G2/G3 | Rückzüge | Luftschnitt | "
           "Umschl. Ø | 95 % | max | > Soll |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    finals = []
    for name in E.TEILE:
        for which in ("cyclo", "fusion"):
            st, fin = analyse(name, which)
            finals.append((name, which, fin))
            for i, o in st.items():
                if not ("272" in o["name"] or "Adaptiv" in o["name"]):
                    o["eng_mean_s"] = "–"  # Boden schlichten: Bodenhaut zählt als Umschlingung – nicht aussagekräftig
                out.append(f"| {name.split('_')[0]} | {'Cyclo' if which == 'cyclo' else 'Fusion'} | {o['name']} | "
                           f"{mmss(o['feed_t'] + o['rapid_t'])} | {o['feed_len']:.0f} | {o['rapid_len']:.0f} | {o['g0']} | "
                           f"{o['g1']} | {o['g23']} | {o['retracts']} | {o['air']:.0f} | " + (
                               "– | – | – | – |" if o.get("eng_mean_s") else
                               f"{o['eng_mean']:.0f}° | {o['eng_p95']:.0f}° | {o['eng_max']:.0f}° | {o['eng_over']:.1f} % |"))
            print(name, which, "fertig", flush=True)
    out += ["", "## Ergebnis am Teil (ganzes Programm)", "",
            "| Teil | Programm | Verletzung | Restfläche Boden | Eilgang im Material |", "|---|---|---|---|---|"]
    for name, which, fin in finals:
        out.append(f"| {name} | {which} | {fin['gouge']:.3f} mm | {fin['rest']:.0f} mm² | {fin['rapid_events']} |")
    open(os.path.join(HERE, "vergleich.md"), "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
