"""225 GRAVIEREN: Text mit eigener Einstrich-Schrift (Raster 4 x 6, Grundlinie y=0).

Eigene Zeichnung der Zeichen (keine fremde Schrift). Kleinbuchstaben werden als
Großbuchstaben graviert. Textlage Q516: 0 Gerade, 1 auf einem Kreisbogen (Radius Q517,
Grundlinie auf dem Kreis, Text oben mittig, im Uhrzeigersinn lesbar), 2 innerhalb eines
Kreisbogens (Oberkante der Zeichen auf dem Kreis). Q367 Bezugspunkt bei der Geraden
(0/1 links unten … 9 rechts Mitte), beim Kreis immer Kreismitte. Q374 Drehlage,
Q513 Zeichenhöhe, Q514 Abstandsfaktor (Lücke = Q514 · Zeichenhöhe / 3),
Q574 maximale Textlänge (0 = beliebig, sonst wird die Schrift verkleinert).
"""

from __future__ import annotations

from ..i18n import _t

import math

from .cyclegen import CycleError, Emit, P, Tool, _levels, heights

# Zeichen: Striche aus Punkten "x,y x,y ...", getrennt durch "|"; optional Breite "w:"
_GLYPHS = {
    "A": "0,0 0,4 2,6 4,4 4,0|0,3 4,3",
    "B": "0,0 0,6 3,6 4,5 4,4 3,3 0,3|3,3 4,2 4,1 3,0 0,0",
    "C": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1",
    "D": "0,0 0,6 2,6 4,4 4,2 2,0 0,0",
    "E": "4,6 0,6 0,0 4,0|0,3 3,3",
    "F": "4,6 0,6 0,0|0,3 3,3",
    "G": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,3 2,3",
    "H": "0,0 0,6|4,0 4,6|0,3 4,3",
    "I": "w2:1,0 1,6|0,0 2,0|0,6 2,6",
    "J": "4,6 4,1 3,0 1,0 0,1",
    "K": "0,0 0,6|4,6 0,2|1,3 4,0",
    "L": "0,6 0,0 4,0",
    "M": "0,0 0,6 2,3 4,6 4,0",
    "N": "0,0 0,6 4,0 4,6",
    "O": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0",
    "P": "0,0 0,6 3,6 4,5 4,4 3,3 0,3",
    "Q": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0|2,2 4,0",
    "R": "0,0 0,6 3,6 4,5 4,4 3,3 0,3|2,3 4,0",
    "S": "4,5 3,6 1,6 0,5 0,4 1,3 3,3 4,2 4,1 3,0 1,0 0,1",
    "T": "0,6 4,6|2,6 2,0",
    "U": "0,6 0,1 1,0 3,0 4,1 4,6",
    "V": "0,6 2,0 4,6",
    "W": "0,6 1,0 2,4 3,0 4,6",
    "X": "0,0 4,6|0,6 4,0",
    "Y": "0,6 2,3 4,6|2,3 2,0",
    "Z": "0,6 4,6 0,0 4,0",
    "0": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0|0,1 4,5",
    "1": "w3:0,4 2,6 2,0|0,0 3,0",
    "2": "0,5 1,6 3,6 4,5 4,4 0,0 4,0",
    "3": "0,5 1,6 3,6 4,5 4,4 3,3 1,3|3,3 4,2 4,1 3,0 1,0 0,1",
    "4": "3,0 3,6 0,2 4,2",
    "5": "4,6 0,6 0,3 3,3 4,2 4,1 3,0 0,0",
    "6": "4,6 2,6 0,4 0,1 1,0 3,0 4,1 4,2 3,3 0,3",
    "7": "0,6 4,6 1,0",
    "8": "1,3 0,4 0,5 1,6 3,6 4,5 4,4 3,3 1,3 0,2 0,1 1,0 3,0 4,1 4,2 3,3",
    "9": "0,0 2,0 4,2 4,5 3,6 1,6 0,5 0,4 1,3 4,3",
    "Ä": "0,0 0,4 2,6 4,4 4,0|0,3 4,3|1,7 1,7.5|3,7 3,7.5",
    "Ö": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0|1,7 1,7.5|3,7 3,7.5",
    "Ü": "0,6 0,1 1,0 3,0 4,1 4,6|1,7 1,7.5|3,7 3,7.5",
    "ß": "0,0 0,5 1,6 2,6 3,5 3,4 2,3 3,3 4,2 4,1 3,0 2,0",
    "-": "w3:0,3 3,3",
    "+": "0,3 4,3|2,1 2,5",
    "=": "0,2 4,2|0,4 4,4",
    ".": "w1:0.5,0 0.5,0.5",
    ",": "w1:0.5,0.5 0.5,0 0,-1",
    ":": "w1:0.5,0 0.5,0.5|0.5,3 0.5,3.5",
    "/": "0,0 4,6",
    "(": "w2:2,6 0,4 0,2 2,0",
    ")": "w2:0,6 2,4 2,2 0,0",
    "#": "1,0 1,6|3,0 3,6|0,2 4,2|0,4 4,4",
    "%": "0,0 4,6|0,6 0,5|4,0 4,1",
    "*": "2,1 2,5|0,2 4,4|0,4 4,2",
    "_": "0,-0.5 4,-0.5",
    "°": "w2:0,6 2,6 2,4 0,4 0,6",
    "Ø": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0|0,0 4,6",
    "?": "0,5 1,6 3,6 4,5 4,4 2,3 2,2|2,0 2,0.5",
    "!": "w1:0.5,6 0.5,2|0.5,0 0.5,0.5",
    "&": "4,0 1,4 1,5 2,6 3,5 3,4 0,2 0,1 1,0 2,0 4,2",
    "'": "w1:0.5,6 0.5,4.5",
    '"': "w2:0,6 0,4.5|2,6 2,4.5",
    "<": "4,5 0,3 4,1",
    ">": "0,5 4,3 0,1",
}
SPACE = 3.0
HEIGHT = 6.0


def glyph(ch: str):
    """-> (Breite, Striche) im Raster."""
    if ch == " ":
        return SPACE, []
    spec = _GLYPHS.get(ch.upper()) if ch not in _GLYPHS else _GLYPHS[ch]
    if spec is None:
        raise CycleError(_t("Zeichen '{0}' ist in der Gravierschrift nicht vorhanden").format(ch))
    width = 4.0
    if spec.startswith("w"):
        w, spec = spec[1:].split(":", 1)
        width = float(w)
    strokes = [[tuple(float(v) for v in pt.split(",")) for pt in s.split()] for s in spec.split("|")]
    return width, strokes


def layout(text: str, height: float, gap_factor: float):
    """Striche des Textes in mm, links unten = (0, 0); -> (Striche, Länge)."""
    s = height / HEIGHT
    gap = gap_factor * height / 3.0
    x = 0.0
    out = []
    chars = []
    for i, ch in enumerate(text):
        w, strokes = glyph(ch)
        chars.append((x, w * s, [[(x + px * s, py * s) for px, py in st] for st in strokes]))
        x += w * s + (gap if i < len(text) - 1 else 0.0)
    for _, _, st in chars:
        out += st
    return out, x, chars


_ANCHOR = {0: (0, 0), 1: (0, 0), 2: (0.5, 0), 3: (1, 0), 4: (1, 1), 5: (0.5, 1), 6: (0, 1), 7: (0, 0.5),
           8: (0.5, 0.5), 9: (1, 0.5)}


def engrave_strokes(p: P, text: str):
    """Striche in Werkstückkoordinaten relativ zur Aufrufposition (0, 0)."""
    if not text:
        raise CycleError(_t("Gravier-Text QS500 ist leer"))
    h = p.n(513, 10)
    if h <= 0:
        raise CycleError(_t("Zeichenhöhe Q513 muss > 0 sein"))
    gapf = p.n(514, 0.5)
    strokes, length, chars = layout(text, h, gapf)
    maxlen = p.n(574, 0)
    if maxlen > 0 and length > maxlen:
        f = maxlen / length
        h *= f
        strokes, length, chars = layout(text, h, gapf)
    rot = math.radians(p.n(374, 0))
    mode = int(p.n(516, 0))
    out = []
    if mode == 0:
        ax, ay = _ANCHOR.get(int(p.n(367, 0)), (0, 0))
        dx, dy = -ax * length, -ay * h
        cr, sr = math.cos(rot), math.sin(rot)
        for st in strokes:
            out.append([((x + dx) * cr - (y + dy) * sr, (x + dx) * sr + (y + dy) * cr) for x, y in st])
        return out
    r = p.n(517, 0)
    if r <= 0:
        raise CycleError(_t("Radius Q517 muss > 0 sein"))
    base = r if mode == 1 else r - h  # Grundlinie
    mid = math.pi / 2 + rot
    for x0, w, sts in chars:
        for st in sts:
            pts = []
            for x, y in st:
                # Abwicklung: Bogenlänge auf der Grundlinie, Zeichen radial nach außen
                ang = mid - (x - length / 2) / base
                rr = base + y
                pts.append((rr * math.cos(ang), rr * math.sin(ang)))
            out.append(pts)
    return out


def engrave_225(p: P, text: str, tool: Tool, e: Emit):
    e.rel = True
    surf, safe, second = heights(p)
    depth = p.n(201)
    if depth >= 0:
        raise CycleError(_t("Tiefe Q201 muss negativ sein"))
    strokes = engrave_strokes(p, text)
    e.rapid_z(second)
    levels = _levels(surf, surf + depth, p.n(202))
    for st in strokes:
        e.rapid_xy(*st[0])
        e.rapid_z(safe)
        for i, z in enumerate(levels):
            pts = st if i % 2 == 0 else st[::-1]  # hin und zurück, ohne Abheben
            e.feed_z(z, p.f(206))
            e.feed_xy(*pts[0], p.f(207))
            for q in pts[1:]:
                e.feed_xy(*q)
        e.rapid_z(safe)
    e.rapid_z(second)
