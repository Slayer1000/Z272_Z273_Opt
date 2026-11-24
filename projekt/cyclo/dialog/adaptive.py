"""Adaptives Räumen (272 KT RAEUMEN, 273 KT BODEN SCHLICHTEN) mit begrenzter Umschlingung.

Rechenweise („rollende Fronten“), je zusammenhängender Teilfläche A der zulässigen Werkzeugmitte
(Fläche um R + Aufmaß verkleinert; bei offener Begrenzung reicht sie um R + Aufmaß + 2k über die
Begrenzung hinaus, Inseln bleiben um R + Aufmaß frei):

1. Start
   * Liegt ein Teil von A neben dem Material (offene Begrenzung, offene Seite einer Tasche laut Rohteil
     ``stock``): Start dort, ohne Eintauchen ins Material. F0 = alle Mittelpunkte in A, bei denen das
     Werkzeug kein Material berührt.
   * Sonst: Helix im Mittelpunkt des größten einbeschriebenen Kreises von A (Radius rh ≤ 0,95·R,
     Steigung ANGLE), danach eine Spirale bis zur Wand. Ihr Zuwachs je Umlauf ist so gewählt, dass die
     Umschlingung auch bei kleinem Radius beim Sollwert bleibt (anfangs kleiner als k). F0 = Kreis.

2. Rollende Fronten
   F ist die Fläche der Mittelpunkte, an denen schon alles geräumt ist. Je Schritt, für die Rollradien
   ρ = 2R, R, R/2, … bis Q578·R:
       G    = (F um ke(ρ) vergrößert) ∩ A
       Fneu = F ∪ Öffnung(G, ρ)          Öffnung = um ρ verkleinert und wieder um ρ vergrößert
   Die größte Rolle rechnet über die ganze Fläche. Die kleineren ergänzen nur, was die größere an
   Wänden, in Ecken und Engstellen nicht erreicht (gerechnet in einem Fenster um diesen Rest).
   Die Öffnung rundet jede Front mit Radius ≥ ρ aus. Dadurch
   * läuft jede Bahn tangential an der Wand an und aus (Spandicke beginnt und endet bei 0),
   * gibt es keine engen Schwenkbögen um Frontenden (dort lag die Umschlingung bisher bei > 100°).
   Der Schritt ke(ρ) ≤ k ist der Zuwachs, bei dem ein Bogen mit Radius ρ gerade die Soll-Umschlingung
   acos(1 − k/R) + ENG_MARGIN hat (Formel der Innenbearbeitung einer Bohrung). Große Radien fahren mit
   vollem k, in Ecken und Engstellen werden Radius und Schritt kleiner – das sind die „trochoidalen“
   Schnitte, nur dort, wo sie nötig sind. Gefräst wird der Rand von Fneu, soweit er nicht schon Rand
   von F war.

3. Abschluss
   Was die kleinste Rolle nicht erreicht (Ecken mit Radius < Q578·R, sehr enge Nuten), räumen einfache
   Fronten mit kleinem Schritt. Danach eine Wandbahn überall dort, wo an der Wand noch mehr als
   TOL_WALL stehen blieb.

4. Reihenfolge und Verbindungen
   Jedes Bahnstück darf erst gefahren werden, wenn die Stücke hinter ihm gefahren sind. Unter den
   freigegebenen Stücken kommt das nächstgelegene dran, Nachfolger des letzten Stücks bevorzugt
   (eine Bucht wird erst fertig geräumt). Verbindungen bis 10·R Länge: Bogen–Gerade–Bogen (Radius
   Q577·R) durch geräumte Fläche oder an der fertigen Wand entlang, 0,2 mm angehoben; sonst Rückzug
   mit Ausfahrbogen. Nach einem Rückzug wird nur dort im Eilgang bis 1 mm über die Tiefe gefahren, wo
   die Simulation die ganze Werkzeugfläche (R + 0,3) als geräumt kennt; sonst im Vorschub. Geschlossene
   Ringe werden über eine tangentiale Überblendung von innen angefahren (Ringwechsel ohne Absetzen).

5. Kontrolle
   Der ganze Plan läuft durch eine Rastersimulation des Abtrags (Zelle 0,2 mm). Sie prüft jede
   Verbindung (kein Material im Weg), misst die Umschlingung je Bahnpunkt und senkt dort, wo sie trotz
   allem über dem Grenzwert liegt, den Vorschub (Faktor im F-Wort).

Die Bahnen werden als Geraden und Kreisbögen ausgegeben (Bogenanpassung der Clipper-Polygone).
Der 2D-Plan wird einmal gerechnet und auf jeder Zustellebene wiederholt.
273 nutzt denselben Planer für Q595 = 1 (gleicher Eingriff); Q595 = 0 sind konturparallele Ringe
(pocket._floor_rings).

Sicherheit der Bahn (nach der Zweitprüfung):
* Geplant wird in der um WALL_MARGIN (6 µm) verkleinerten zulässigen Fläche. Jedes ausgegebene Element
  (Schnitt, Verbindung) wird gegen die zulässige Fläche geprüft (prims_within, mit 2 µm Toleranzreserve); ein Bogen,
  der sie verließe, bleibt Sehnenzug, eine Verbindung wird verworfen.
* Einstieg in geschlossene Flächen: Helix; bei wenig Platz Pendelrampe auf der längsten Sehne; nur wenn
  beides nicht geht, senkrecht (mit Warnung).
* Ein Bahnstück beginnt nur an einer geräumten Stelle (ganze Werkzeugscheibe frei, Grid.free) oder wird
  auf Tiefe über eine dünne Haut angefahren. Gibt es keinen solchen Anfang: PlanError statt Einstich.
* Rastergröße ist begrenzt (MAX_CELLS), darüber PlanError.

Grenzen: Die Simulation rechnet auf einem 0,2-mm-Raster; Reste unter TOL_MAT/TOL_WALL bleiben stehen.
An Engstellen, die schmaler sind als Werkzeug + 2·Q578·R, kann die Umschlingung über dem Sollwert
liegen – dort wird der Vorschub gesenkt und eine Warnung ausgegeben. Die Helix selbst schneidet
zwangsläufig voll (erster Einstich).
"""

from __future__ import annotations

import math

import numpy as np

from .slcycles import SCALE, _flt, _int, inside, pyclipper  # noqa: F401
from .slcycles import offset as _offset_raw

TOL_MAT = 0.02    # dünnere Materialreste werden nicht eigens angefahren
TOL_PIECE = 0.01  # Rand von Fneu gilt als neu, wenn er weiter als das vor F liegt
TOL_WALL = 0.06   # Wandreste bis zu dieser Dicke bleiben stehen (Schruppen)
STEP = 0.25       # Abtastung (alte Schnittstelle)
SIM_H = 0.2       # Zellgröße der Abtragssimulation
SIM_STEP = 0.4    # Abtastung der Bahnen in der Simulation
ENG_MARGIN = 10.0  # Zuschlag auf die Soll-Umschlingung bei der Schrittweite ke(ρ), Grad
ARC_TOL = 0.004   # Bogenanpassung: größte Abweichung eines Stützpunkts
WALL_MARGIN = 0.006  # geplant wird in der um diesen Rand verkleinerten zulässigen Fläche; so haben die
#                      Bögen Platz, die Clippers Sehnenzüge ersetzen (Pfeilhöhe bis 5 µm). Jedes ausgegebene
#                      Element wird danach gegen die zulässige Fläche selbst geprüft (prims_within, Toleranz dort).
PRIMS_TOL = 0.002    # prims_within prüft gegen die um dieses Maß verkleinerte Fläche (Toleranzreserve)
MAX_CELLS = 12_000_000  # größtes Simulationsraster (0,2 mm: rund 480 000 mm²), begrenzt den Speicher


MEM_BUDGET = 200 * 2 ** 20   # geschätzte Planungsdaten je Zyklusaufruf (Byte). Bis zur Vorgabe von 500 MB
#                              bleiben 300 MB Reserve für Python, numpy, pyclipper, den Übersetzer und alles,
#                              was die Schätzung nicht erfasst (Clipper-Zwischenergebnisse, Listenverwaltung).


class Budget:
    """Speicherbudget eines Zyklusaufrufs. held = Schätzung der Daten, die bis zum Ende gehalten werden
    (fertige Pläne); need() prüft VOR einer Allokation, ob held + Bedarf ins Budget passt."""

    def __init__(self, limit=None):
        self.limit = MEM_BUDGET if limit is None else limit
        self.held = 0
        self.peak = 0

    def need(self, n):
        tot = self.held + int(n)
        if tot > self.limit:
            raise PlanError("memory", tot / 2 ** 20, self.limit / 2 ** 20)
        self.peak = max(self.peak, tot)

    def hold(self, n):
        self.held += int(n)
        self.peak = max(self.peak, self.held)


def plan_need(comp, R, k, sim_h=SIM_H, fill=False):
    """Geschätzter Arbeitsspeicher (Byte) für die Planung einer Teilfläche, solange sie läuft:
      Raster       1 Byte je Zelle (bool); beim Füllen mit dem Rohteil zusätzlich 10 Byte je Zelle
                   (int32-Zähler, Summe, Masken – nur vorübergehend)
      Masken       Werkzeugscheiben: 2 × 16 Lagen (Abtrag, „frei“) + bis zu 3 für clear, je (2m+1)² Byte,
                   dazu 5 float64-Hilfsfelder beim Aufbau -> 75 Byte × (2m+1)², m = R/h + 1
      Reihenfolge  Besitzerkarte in _link_tree: 4 int32 je Zelle (Zelle ≥ 1 mm) und eine Kopie -> 40 Byte
      Bahnen       400 Byte je halbem Millimeter Bahn, Bahnlänge geschätzt als Fläche / k. Der Wert ist an
                   Messungen des Prozessspeichers angepasst (Tasche 500 × 500, k = 2: Schätzung 120 MB,
                   gemessener Zuwachs 138 MB) und deckt damit Clipper-Zwischenergebnisse nur grob ab –
                   ein Erfahrungswert, kein Nachweis
      Prüffläche   10 MB pauschal für Region (Kantenfelder, Hilfsraster, Rechenfelder)
    Nicht enthalten: Clipper-Zwischenergebnisse, Python-Verwaltung -> Reserve, siehe MEM_BUDGET."""
    bx = _box(comp, R + 1.0)[0]
    w, h_ = (bx[2][0] - bx[0][0]) / SCALE, (bx[2][1] - bx[0][1]) / SCALE
    cells = (math.ceil(w / sim_h) + 1) * (math.ceil(h_ / sim_h) + 1)
    side = 2 * (int(math.ceil(R / sim_h)) + 1) + 1
    c = max(1.0, 1.05 * R / 6)
    area = abs(_area(comp))
    return int(cells * (11 if fill else 1) + 75 * side * side + 40 * (w + 3 * R) * (h_ + 3 * R) / (c * c)
               + 400 * (area / max(k, 0.05)) / 0.5 + 10 * 2 ** 20)


class PlanError(Exception):
    """Plan nicht möglich (zu große Fläche, kein sicherer Einstieg). args[0] = Schlüssel, args[1:] = Werte."""


# --------------------------------------------------------------------------- Clipper-Helfer
def _clean(paths):
    """Entartete Polygone (Fläche < 1e-4 mm²) entfernen. Nötig vor jedem Versatz: Clipper richtet den
    Umlaufsinn aller Pfade nach dem untersten Polygon aus – ist das ein entarteter Splitter mit
    falschem Umlaufsinn, kommt der ganze Versatz verkehrt (leer) heraus."""
    return [p for p in paths if len(p) >= 3 and abs(pyclipper.Area(p)) >= 100.0]


def offset(paths, d):
    """Versatz mit runden Ecken: d > 0 verkleinert, d < 0 vergrößert (wie slcycles.offset, aber robust
    gegen entartete Polygone)."""
    paths = _clean(paths)
    return _offset_raw(paths, d) if paths else []


def buffer_open(polylines, r):
    po = pyclipper.PyclipperOffset(2.0, 0.005 * SCALE)
    n = 0
    for pl in polylines:
        if len(pl) >= 2:
            po.AddPath(_int(pl), pyclipper.JT_ROUND, pyclipper.ET_OPENROUND)
            n += 1
    return po.Execute(r * SCALE) if n else []


def disc(cx, cy, r, n=48):
    return [_int([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
                  for i in range(n)])]


def _bool(a, b, op):
    pc = pyclipper.Pyclipper()
    pc.AddPaths(a, pyclipper.PT_SUBJECT, True)
    if b:
        pc.AddPaths(b, pyclipper.PT_CLIP, True)
    return pc.Execute(op, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def union(a, b):
    if not a:
        return b
    if not b:
        return a
    return _bool(a, b, pyclipper.CT_UNION)


def intersect(a, b):
    if not a or not b:
        return []
    return _bool(a, b, pyclipper.CT_INTERSECTION)


def difference(a, b):
    if not a or not b:
        return a
    return _bool(a, b, pyclipper.CT_DIFFERENCE)


def grow(paths, d):
    """Fläche um d vergrößern (runde Ecken)."""
    return offset(paths, -d)


def opening(paths, r):
    """Morphologische Öffnung: alle Kreise mit Radius r, die ganz in der Fläche liegen."""
    return offset(offset(paths, r), -r)


def components(paths):
    """Zusammenhängende Teilflächen: Liste von Pfadlisten (Außenkontur + Löcher)."""
    if not paths:
        return []
    pc = pyclipper.Pyclipper()
    pc.AddPaths(paths, pyclipper.PT_SUBJECT, True)
    tree = pc.Execute2(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    out = []

    def walk(node):
        for ch in node.Childs:
            if not ch.IsHole:
                comp = [ch.Contour] + [h.Contour for h in ch.Childs]
                out.append(comp)
                for h in ch.Childs:
                    walk(h)
    walk(tree)
    return out


def _area(paths):
    return sum(pyclipper.Area(p) for p in paths) / SCALE ** 2


def _box(paths, margin):
    xs = [p[0] for path in paths for p in path]
    ys = [p[1] for path in paths for p in path]
    m = int(margin * SCALE)
    return [[(min(xs) - m, min(ys) - m), (max(xs) + m, min(ys) - m), (max(xs) + m, max(ys) + m),
             (min(xs) - m, max(ys) + m)]]


def _clip_open(loops, clip):
    """Teile der geschlossenen Schleifen, die außerhalb von clip liegen (offene Polygonzüge, ganzzahlig)."""
    pc = pyclipper.Pyclipper()
    n = 0
    for lp in loops:
        if len(lp) >= 3:
            pc.AddPath(list(lp) + [lp[0]], pyclipper.PT_SUBJECT, False)
            n += 1
    if not n:
        return []
    if clip:
        pc.AddPaths(clip, pyclipper.PT_CLIP, True)
    tree = pc.Execute2(pyclipper.CT_DIFFERENCE, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    return pyclipper.OpenPathsFromPolyTree(tree)


# --------------------------------------------------------------------------- Geometrie
def k_eff(rho, R, k, margin=ENG_MARGIN):
    """Zuwachs, bei dem ein Frontbogen mit Radius rho (Mittelpunktsbahn, Material außen) die
    Umschlingung acos(1 − k/R) + margin hat; höchstens k."""
    th = math.acos(max(-1.0, min(1.0, 1 - k / R))) + math.radians(margin)
    c = math.cos(min(th, math.pi))
    return min(k, rho + R - math.sqrt(max(rho * rho + R * R + 2 * rho * R * c, 0.0)))


def inscribed(comp):
    """(Mittelpunkt, Radius) des größten einbeschriebenen Kreises: so weit verkleinern, bis nichts bleibt."""
    xs = [p[0] for p in comp[0]]
    ys = [p[1] for p in comp[0]]
    hi = min(max(xs) - min(xs), max(ys) - min(ys)) / SCALE / 2 + 1e-3
    lo, last = 0.0, comp
    for _ in range(22):
        mid = (lo + hi) / 2
        o = offset(comp, mid)
        if o:
            lo, last = mid, o
        else:
            hi = mid
        if hi - lo < 2e-4:
            break
    best = max(last, key=lambda p: abs(pyclipper.Area(p)))
    pts = _flt(best)
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        w = x0 * y1 - x1 * y0
        a += w
        cx += (x0 + x1) * w
        cy += (y0 + y1) * w
    if abs(a) > 1e-9:
        c = (cx / (3 * a), cy / (3 * a))
    else:
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    if not inside(comp, c):
        c = pts[0]
    # Der Versatz von Clipper ist nur auf einige µm genau (Sehnen statt Bögen): der Radius wird am
    # Mittelpunkt nachgemessen, nie größer als der wirkliche Abstand zum Rand gemeldet.
    return c, max(0.0, min(lo, wall_dist(comp, c)))


def wall_dist(comp, c):
    """Kleinster Abstand des Punkts c zu den Kanten der Fläche (alle Schleifen), in Gleitkomma."""
    best = float("inf")
    for path in comp:
        A = np.asarray(path, dtype=float) / SCALE
        if len(A) < 2:
            continue
        B = np.roll(A, -1, axis=0)
        d = B - A
        L2 = np.maximum((d * d).sum(1), 1e-18)
        t = np.clip(((c[0] - A[:, 0]) * d[:, 0] + (c[1] - A[:, 1]) * d[:, 1]) / L2, 0.0, 1.0)
        best = min(best, float(np.hypot(A[:, 0] + t * d[:, 0] - c[0], A[:, 1] + t * d[:, 1] - c[1]).min()))
    return best


def spiral(c, r0, r1, k, ccw, tol=0.004, R=None, g_min=0.02):
    """Spirale von Radius r0 (Winkel 0) bis r1, danach Vollkreis auf r1. Mit R: Zuwachs je Umlauf
    ke(r) (gleichbleibende Umschlingung), sonst k; mindestens g_min je Umlauf."""
    sg = 1 if ccw else -1
    pts, th, r = [], 0.0, r0
    while True:
        pts.append((c[0] + r * math.cos(sg * th), c[1] + r * math.sin(sg * th)))
        if r >= r1 - 1e-9:
            break
        dth = min(0.2, 2 * math.sqrt(2 * tol / max(r, 0.1)))
        kk = k_eff(r, R, k) if R else k
        r = min(r + max(kk, g_min) * dth / (2 * math.pi), r1)
        th += dth
    th_end = th + 2 * math.pi
    dth = min(0.2, 2 * math.sqrt(2 * tol / max(r1, 0.1)))
    while th < th_end - 1e-9:
        th = min(th + dth, th_end)
        pts.append((c[0] + r1 * math.cos(sg * th), c[1] + r1 * math.sin(sg * th)))
    return pts


def douglas_peucker(pts, tol=0.005):
    """Polygonzug vereinfachen (Abweichung höchstens tol)."""
    if len(pts) < 3:
        return list(pts)
    P = np.asarray(pts, dtype=float)
    keep = np.zeros(len(P), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        ab = b - a
        L = np.hypot(*ab)
        Q = P[i + 1:j]
        if L < 1e-12:
            d = np.hypot(*(Q - a).T)
        else:
            d = np.abs(ab[0] * (Q[:, 1] - a[1]) - ab[1] * (Q[:, 0] - a[0])) / L
        m = int(d.argmax())
        if d[m] > tol:
            keep[i + 1 + m] = True
            stack += [(i, i + 1 + m), (i + 1 + m, j)]
    return [tuple(map(float, p)) for p in P[keep]]


def _plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _resample(pts, step):
    """Punkte im Abstand ≤ step entlang des Polygonzugs (mit Stützpunkten) + Richtung je Punkt."""
    P = np.asarray(pts, dtype=float)
    if len(P) < 2:
        return P.reshape(-1, 2), np.zeros((len(P), 2))
    d = np.diff(P, axis=0)
    L = np.hypot(d[:, 0], d[:, 1])
    n = np.maximum(1, np.ceil(L / step).astype(int))
    idx = np.repeat(np.arange(len(L)), n)
    first = np.concatenate([[0], np.cumsum(n)[:-1]])
    t = (np.arange(len(idx)) - first[idx] + 1) / n[idx]
    Q = P[idx] + d[idx] * t[:, None]
    T = d[idx] / np.maximum(L[idx], 1e-12)[:, None]
    return np.vstack([P[:1], Q]), np.vstack([T[:1], T])


# --------------------------------------------------------------------------- Abtragssimulation (Raster)
class Grid:
    """Materialkarte für die Planung: Zelle True = Material steht. Werkzeug als Kreisscheibe."""

    def __init__(self, x0, y0, x1, y1, R, h=SIM_H):
        self.h, self.R = h, R
        self.x0, self.y0 = x0, y0
        self.nx = int(math.ceil((x1 - x0) / h)) + 1
        self.ny = int(math.ceil((y1 - y0) / h)) + 1
        self.mat = np.ones((self.ny, self.nx), dtype=bool)
        self._cm = {}
        m = int(math.ceil(R / h)) + 1
        self.m = m
        ax = (np.arange(-m, m + 1)) * h
        X, Y = np.meshgrid(ax, ax)
        sub = 4
        self.sub = sub
        # Scheiben für 4 × 4 Lagen innerhalb der Zelle (Zellmitte = Messpunkt)
        self.keep = [[~((X - (i + 0.5) / sub * h + h / 2) ** 2 + (Y - (j + 0.5) / sub * h + h / 2) ** 2 <= R * R)
                      for i in range(sub)] for j in range(sub)]
        ne = 72
        a = np.arange(ne) * 2 * math.pi / ne
        self.eu = np.stack([np.cos(a), np.sin(a)], 1)       # Richtungen der Messpunkte am Umfang
        self.er = max(R - 0.75 * h, 0.6 * R)                # Messradius Umschlingung
        # „frei“: ganze Werkzeugscheibe bis R − h/2 (Reste am äußersten Rand sind Rasterrauschen der Wandbahnen)
        rf = max(R - 0.5 * h, 0.5 * R)
        self.fmask = [[(X - (i + 0.5) / sub * h + h / 2) ** 2 + (Y - (j + 0.5) / sub * h + h / 2) ** 2 <= rf * rf
                       for i in range(sub)] for j in range(sub)]

    def fill(self, paths, value):
        """Fläche (Float-Pfade, überlappungsfrei) auf value setzen."""
        nx, ny, h = self.nx, self.ny, self.h
        T = np.zeros((ny, nx + 1), dtype=np.int32)
        for path in paths:
            P = np.asarray(path, dtype=float)
            if len(P) < 3:
                continue
            Q = np.roll(P, -1, axis=0)
            ya, yb = P[:, 1], Q[:, 1]
            lo, hi = np.minimum(ya, yb), np.maximum(ya, yb)
            ja = np.ceil((lo - self.y0) / h - 0.5).astype(int)   # erste Zeile mit Mitte ≥ lo
            jb = np.ceil((hi - self.y0) / h - 0.5).astype(int)   # erste Zeile mit Mitte ≥ hi
            ja, jb = np.clip(ja, 0, ny), np.clip(jb, 0, ny)
            cnt = jb - ja
            ok = cnt > 0
            if not ok.any():
                continue
            e = np.repeat(np.nonzero(ok)[0], cnt[ok])
            start = np.repeat(np.cumsum(cnt[ok]) - cnt[ok], cnt[ok])
            j = ja[e] + (np.arange(len(e)) - start)
            yc = self.y0 + (j + 0.5) * h
            x = P[e, 0] + (yc - ya[e]) * (Q[e, 0] - P[e, 0]) / (yb[e] - ya[e])
            i = np.clip(np.ceil((x - self.x0) / h - 0.5).astype(int), 0, nx)
            np.add.at(T, (j, i), 1)
        np.cumsum(T, axis=1, out=T)             # an Ort und Stelle: keine zweite große Ganzzahlkarte
        mask = (T[:, :nx] & 1).astype(bool)
        del T
        self.mat[mask] = value
        return mask

    def stamp(self, P):
        """Werkzeug an den Punkten P (n × 2) absetzen: Material weg."""
        h, m, sub, mat = self.h, self.m, self.sub, self.mat
        fx = (P[:, 0] - self.x0) / h
        fy = (P[:, 1] - self.y0) / h
        ix = np.floor(fx).astype(int)
        iy = np.floor(fy).astype(int)
        sx = np.minimum(((fx - ix) * sub).astype(int), sub - 1)
        sy = np.minimum(((fy - iy) * sub).astype(int), sub - 1)
        nx, ny = self.nx, self.ny
        keep = self.keep
        for a, b, u, v in zip(ix.tolist(), iy.tolist(), sx.tolist(), sy.tolist()):
            x0, x1, y0, y1 = a - m, a + m + 1, b - m, b + m + 1
            if x0 < 0 or y0 < 0 or x1 > nx or y1 > ny:
                cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, nx), min(y1, ny)
                if cx0 >= cx1 or cy0 >= cy1:
                    continue
                mat[cy0:cy1, cx0:cx1] &= keep[v][u][cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
            else:
                mat[y0:y1, x0:x1] &= keep[v][u]

    def clear(self, p, extra=0.3):
        """True, wenn im Umkreis R + extra um p keine Zelle Material trägt (für Eintauchen im Eilgang)."""
        key = round(extra, 3)
        if key not in self._cm:
            mm = int(math.ceil((self.R + extra) / self.h)) + 1
            ax = np.arange(-mm, mm + 1) * self.h
            X, Y = np.meshgrid(ax, ax)
            self._cm[key] = (mm, X * X + Y * Y <= (self.R + extra + 0.71 * self.h) ** 2)
        mm, mask = self._cm[key]
        ix = int(math.floor((p[0] - self.x0) / self.h))
        iy = int(math.floor((p[1] - self.y0) / self.h))
        x0, x1, y0, y1 = ix - mm, ix + mm + 1, iy - mm, iy + mm + 1
        if x0 < 0 or y0 < 0 or x1 > self.nx or y1 > self.ny:
            return False   # Scheibe ragt über das Raster hinaus: unbekannt = nicht frei
        return not (self.mat[y0:y1, x0:x1] & mask).any()

    def _look(self, X, Y):
        ix = np.floor((X - self.x0) / self.h).astype(int)
        iy = np.floor((Y - self.y0) / self.h).astype(int)
        ok = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        out = np.zeros(X.shape, dtype=bool)
        out[ok] = self.mat[iy[ok], ix[ok]]
        return out

    def engage(self, P, T):
        """Umschlingung (Grad) je Punkt: Material am Umfang der vorderen Werkzeughälfte (Richtung T)."""
        if len(P) == 0:
            return np.zeros(0)
        X = P[:, None, 0] + self.er * self.eu[None, :, 0]
        Y = P[:, None, 1] + self.er * self.eu[None, :, 1]
        front = (T[:, None, 0] * self.eu[None, :, 0] + T[:, None, 1] * self.eu[None, :, 1]) > 1e-6
        return (self._look(X, Y) & front).sum(1) * (360.0 / len(self.eu))

    def free(self, P):
        """True je Punkt, wenn in der ganzen Werkzeugscheibe (Radius R − h/2) um den Punkt keine Zelle
        Material trägt. Punkte, deren Scheibe über das Raster hinausragt, gelten als nicht frei."""
        out = np.zeros(len(P), dtype=bool)
        if len(P) == 0:
            return out
        h, m, sub, mat = self.h, self.m, self.sub, self.mat
        fx = (P[:, 0] - self.x0) / h
        fy = (P[:, 1] - self.y0) / h
        ix = np.floor(fx).astype(int)
        iy = np.floor(fy).astype(int)
        sx = np.minimum(((fx - ix) * sub).astype(int), sub - 1)
        sy = np.minimum(((fy - iy) * sub).astype(int), sub - 1)
        nx, ny, fm = self.nx, self.ny, self.fmask
        for n, (a, b, u, v) in enumerate(zip(ix.tolist(), iy.tolist(), sx.tolist(), sy.tolist())):
            x0, x1, y0, y1 = a - m, a + m + 1, b - m, b + m + 1
            if x0 < 0 or y0 < 0 or x1 > nx or y1 > ny:
                continue
            out[n] = not (mat[y0:y1, x0:x1] & fm[v][u]).any()
        return out


# --------------------------------------------------------------------------- Bahnelemente
class Prim:
    """Bahnelement: Gerade ("L") oder Kreisbogen ("A", Mittelpunkt c, Bogenwinkel sweep, + = gegen Uhrzeiger).
    ff = Vorschubfaktor (1 = Fräsvorschub)."""
    __slots__ = ("kind", "p0", "p1", "c", "sweep", "length", "ff")

    def __init__(self, kind, p0, p1, c=None, sweep=0.0, ff=1.0):
        self.kind, self.p0, self.p1, self.c, self.sweep, self.ff = kind, p0, p1, c, sweep, ff
        self.length = math.dist(p0, p1) if kind == "L" else abs(sweep) * math.dist(p0, c)

    def at(self, f):
        if self.kind == "L":
            return (self.p0[0] + (self.p1[0] - self.p0[0]) * f, self.p0[1] + (self.p1[1] - self.p0[1]) * f)
        r = math.dist(self.p0, self.c)
        a = math.atan2(self.p0[1] - self.c[1], self.p0[0] - self.c[0]) + self.sweep * f
        return (self.c[0] + r * math.cos(a), self.c[1] + r * math.sin(a))

    def split(self, f):
        m = self.at(f)
        if self.kind == "L":
            return Prim("L", self.p0, m, ff=self.ff), Prim("L", m, self.p1, ff=self.ff)
        return (Prim("A", self.p0, m, self.c, self.sweep * f, self.ff),
                Prim("A", m, self.p1, self.c, self.sweep * (1 - f), self.ff))

    def heading(self, end=True):
        """Fahrtrichtung am Ende (end=True) bzw. Anfang."""
        if self.kind == "L":
            return _unit((self.p1[0] - self.p0[0], self.p1[1] - self.p0[1]))
        p = self.p1 if end else self.p0
        r = (p[0] - self.c[0], p[1] - self.c[1])
        return _unit((-r[1], r[0]) if self.sweep > 0 else (r[1], -r[0]))


def _unit(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n) if n > 1e-12 else (1.0, 0.0)


def _lft(v):
    return (-v[1], v[0])


def _arc(p, c, q, left):
    a0 = math.atan2(p[1] - c[1], p[0] - c[0])
    a1 = math.atan2(q[1] - c[1], q[0] - c[0])
    sw = (a1 - a0) % (2 * math.pi) if left else -((a0 - a1) % (2 * math.pi))
    if abs(sw) > 2 * math.pi - 1e-7:
        sw = 0.0
    return Prim("A", p, q, c, sw) if abs(sw) > 1e-9 and math.dist(p, q) > 1e-9 else None


def dubins(p0, h0, p1, h1, r):
    """Kürzeste Wege Bogen–Gerade–Bogen (Radius r) von p0/Richtung h0 nach p1/Richtung h1,
    nach Länge sortiert. -> Liste von Prim-Listen"""
    h0, h1 = _unit(h0), _unit(h1)
    out = []
    for s0 in (True, False):        # True = Linkskurve
        for s1 in (True, False):
            n0, n1 = _lft(h0), _lft(h1)
            c0 = (p0[0] + (r if s0 else -r) * n0[0], p0[1] + (r if s0 else -r) * n0[1])
            c1 = (p1[0] + (r if s1 else -r) * n1[0], p1[1] + (r if s1 else -r) * n1[1])
            v = (c1[0] - c0[0], c1[1] - c0[1])
            D = math.hypot(*v)
            if s0 == s1:
                if D < 1e-9:
                    continue
                h = _unit(v)
            else:
                if D < 2 * r:
                    continue
                phi = math.atan2(v[1], v[0])
                th = phi + (1 if s0 else -1) * math.asin(2 * r / D)
                h = (math.cos(th), math.sin(th))
            lh = _lft(h)
            t0 = (c0[0] - (r if s0 else -r) * lh[0], c0[1] - (r if s0 else -r) * lh[1])
            t1 = (c1[0] - (r if s1 else -r) * lh[0], c1[1] - (r if s1 else -r) * lh[1])
            prims = [_arc(p0, c0, t0, s0), Prim("L", t0, t1) if math.dist(t0, t1) > 1e-9 else None,
                     _arc(t1, c1, p1, s1)]
            prims = [q for q in prims if q is not None]
            out.append((sum(q.length for q in prims), prims))
    out.sort(key=lambda x: x[0])
    return [p for _, p in out]


def prims_points(prims, step=0.3):
    """Abtastpunkte einer Elementfolge (n × 2)."""
    pts = []
    for q in prims:
        n = max(1, int(math.ceil(q.length / step)))
        pts += [q.at(i / n) for i in range(n + 1)]
    return np.asarray(pts, dtype=float).reshape(-1, 2)


class Region:
    """Prüffläche für prims_within: die Fläche paths, um shrink verkleinert, als Kantenfelder.
    Ein Hilfsraster merkt sich Zellen, die tief im Inneren liegen (dort entfällt die Kantenrechnung)."""

    def __init__(self, paths, shrink=PRIMS_TOL):
        t = offset(paths, shrink) if (paths and shrink > 0) else _clean(paths or [])
        A, B = [], []
        for path in t:
            q = np.asarray(path, dtype=float) / SCALE
            A.append(q)
            B.append(np.roll(q, -1, axis=0))
        self.empty = not A
        if self.empty:
            return
        self.A, self.B = np.concatenate(A), np.concatenate(B)
        self.lo, self.hi = np.minimum(self.A, self.B), np.maximum(self.A, self.B)
        x0, y0 = self.A.min(0)
        x1, y1 = self.A.max(0)
        self.c = c = max(1.0, math.sqrt((x1 - x0) * (y1 - y0) / 40000.0))
        self.gx0, self.gy0 = x0 - 3 * c, y0 - 3 * c
        nx, ny = int((x1 - x0) / c) + 7, int((y1 - y0) / c) + 7
        near = np.zeros((ny, nx), dtype=bool)
        d = self.B - self.A
        n = np.maximum(1, np.ceil(np.hypot(d[:, 0], d[:, 1]) / (0.4 * c)).astype(int))
        e = np.repeat(np.arange(len(n)), n + 1)
        f = (np.arange(len(e)) - np.repeat(np.cumsum(n + 1) - (n + 1), n + 1)) / np.repeat(n, n + 1)
        S = self.A[e] + d[e] * f[:, None]
        near[((S[:, 1] - self.gy0) / c).astype(int), ((S[:, 0] - self.gx0) / c).astype(int)] = True
        wide = near.copy()
        for dy in range(-2, 3):      # zwei Zellen Abstand zur Grenze
            for dx in range(-2, 3):
                ys, yd = slice(max(dy, 0), ny + min(dy, 0)), slice(max(-dy, 0), ny + min(-dy, 0))
                xs, xd = slice(max(dx, 0), nx + min(dx, 0)), slice(max(-dx, 0), nx + min(-dx, 0))
                wide[yd, xd] |= near[ys, xs]
        cx, cy = np.meshgrid(self.gx0 + (np.arange(nx) + 0.5) * c, self.gy0 + (np.arange(ny) + 0.5) * c)
        self.deep = np.zeros((ny, nx), dtype=bool)
        cand = ~wide
        if cand.any():
            self.deep[cand] = self.points_inside(np.stack([cx[cand], cy[cand]], 1))

    def points_inside(self, P):
        """Je Punkt: liegt er in der Prüffläche (Strahltest gerade/ungerade)."""
        P = np.asarray(P, dtype=float).reshape(-1, 2)
        out = np.zeros(len(P), dtype=bool)
        if self.empty or len(P) == 0:
            return out
        A, B = self.A, self.B
        step = max(1, 250_000 // len(A))        # Rechenfelder klein halten (je Schritt rund 10 MB)
        dy = B[:, 1] - A[:, 1]
        dy = np.where(dy == 0, 1.0, dy)
        for i in range(0, len(P), step):
            px, py = P[i:i + step, 0, None], P[i:i + step, 1, None]
            span = (A[None, :, 1] > py) != (B[None, :, 1] > py)
            xi = A[None, :, 0] + (py - A[None, :, 1]) * (B[None, :, 0] - A[None, :, 0]) / dy[None, :]
            out[i:i + step] = ((span & (xi > px)).sum(1) & 1) == 1
        return out

    def polyline_inside(self, P):
        """True, wenn der zusammenhängende Polygonzug P (n × 2, auch ein einzelner Punkt) ganz in der
        Prüffläche liegt: keine Strecke berührt oder kreuzt eine Kante, und ein Punkt liegt innen."""
        P = np.asarray(P, dtype=float).reshape(-1, 2)
        if self.empty or len(P) == 0:
            return False
        if len(P) == 1:
            return bool(self.points_inside(P)[0])
        p, r = P[:-1], P[1:] - P[:-1]
        # Strecken ganz in tiefen Zellen brauchen keine Kantenrechnung
        c = self.c
        ix = np.clip(((P[:, 0] - self.gx0) / c).astype(int), 0, self.deep.shape[1] - 1)
        iy = np.clip(((P[:, 1] - self.gy0) / c).astype(int), 0, self.deep.shape[0] - 1)
        dp = self.deep[iy, ix] & (P[:, 0] >= self.gx0) & (P[:, 1] >= self.gy0)
        easy = dp[:-1] & dp[1:] & (np.hypot(r[:, 0], r[:, 1]) <= c)
        p, r = p[~easy], r[~easy]
        A, s = self.A, self.B - self.A
        lo, hi = self.lo, self.hi
        for i in range(0, len(p), 48):   # stückweise, je Stück nur die Kanten in der Nähe
            pp, rr = p[i:i + 48], r[i:i + 48]
            e0, e1 = pp + rr, pp
            bx0 = min(e0[:, 0].min(), e1[:, 0].min()) - 1e-6
            bx1 = max(e0[:, 0].max(), e1[:, 0].max()) + 1e-6
            by0 = min(e0[:, 1].min(), e1[:, 1].min()) - 1e-6
            by1 = max(e0[:, 1].max(), e1[:, 1].max()) + 1e-6
            sel = (hi[:, 0] >= bx0) & (lo[:, 0] <= bx1) & (hi[:, 1] >= by0) & (lo[:, 1] <= by1)
            if not sel.any():
                continue
            Aa, ss = A[sel], s[sel]
            pp, rr = pp[:, None, :], rr[:, None, :]
            w = Aa[None, :, :] - pp
            rxs = rr[..., 0] * ss[None, :, 1] - rr[..., 1] * ss[None, :, 0]
            wxs = w[..., 0] * ss[None, :, 1] - w[..., 1] * ss[None, :, 0]
            wxr = w[..., 0] * rr[..., 1] - w[..., 1] * rr[..., 0]
            par = np.abs(rxs) < 1e-12
            den = np.where(par, 1.0, rxs)
            t, u = wxs / den, wxr / den
            if (~par & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)).any():
                return False
            # parallele Strecke genau auf einer Kante (auch Punkt auf Kante)
            if par.any():
                sl = np.maximum(np.hypot(ss[:, 0], ss[:, 1]), 1e-12)[None, :]
                on = par & (np.abs(wxs) / sl < 1e-9)
                if on.any():
                    a0 = -(w[..., 0] * ss[None, :, 0] + w[..., 1] * ss[None, :, 1]) / (sl * sl)
                    a1 = a0 + (rr[..., 0] * ss[None, :, 0] + rr[..., 1] * ss[None, :, 1]) / (sl * sl)
                    if (on & (np.maximum(a0, a1) >= 0) & (np.minimum(a0, a1) <= 1)).any():
                        return False
        # Der Polygonzug hängt zusammen und berührt keine Kante: er liegt ganz innen oder ganz außen.
        return bool(dp.any() or self.points_inside(P[:1])[0])


def prims_within(prims, region):
    """True, wenn die Elementfolge nachweislich in der Fläche region liegt (Clipper-Pfade oder Region).

    Geprüft wird gegen die um PRIMS_TOL (2 µm) verkleinerte Fläche: Keine Strecke darf deren Rand
    berühren oder kreuzen, jede Streckenmitte muss innen liegen (eigene Rechnung in Gleitkomma, keine
    Clipper-Differenz – die liefert für waagerechte offene Strecken außerhalb nichts zurück).
    Bögen werden durch Sehnen mit höchstens 0,1 µm Pfeilhöhe ersetzt.
    Garantie: Ergebnis True -> die wahre Bahn liegt in region. Reserve: 2 µm Verkleinerung, davon gehen
    bis 0,7 µm Ganzzahlrundung des verkleinerten Polygons, 0,1 µm Pfeilhöhe und rund 0,1 µm Rundung der
    G-Code-Ausgabe (vier Stellen) ab; es bleibt rund 1 µm. Das ist eine Prüfung mit Toleranz, keine exakte:
    Bahnen, die näher als etwa 2–3 µm am Rand liegen, werden abgelehnt, obwohl sie zulässig wären.
    Leere Folge -> True; leere Fläche -> False."""
    if not isinstance(region, Region):
        region = Region(region)
    pts = []
    for q in prims:
        n = 1
        if q.kind == "A" and q.length >= 1e-9:
            r = math.dist(q.p0, q.c)
            n = max(2, int(math.ceil(abs(q.sweep) / (2 * math.acos(max(0.0, 1 - 0.0001 / max(r, 0.0001)))))))
        if not pts or math.dist(pts[-1], q.p0) > 1e-9:
            if pts:   # Lücke zwischen zwei Elementen: getrennt prüfen
                if not region.polyline_inside(pts):
                    return False
                pts = []
            pts.append(q.p0)
        pts += [q.at(i / n) for i in range(1, n + 1)]
    if not pts:
        return True
    return region.polyline_inside(pts)


def fit_arcs(pts, tol=ARC_TOL, sag=0.012, ff=1.0, ok=None):
    """Polygonzug in Geraden und Kreisbögen umsetzen. Clipper liefert Bögen als Sehnenzüge mit
    Stützpunkten auf dem Kreis; hier werden die Kreise wiedergefunden. Ein Bogen wird nur angenommen,
    wenn alle Stützpunkte höchstens tol vom Kreis abliegen und keine Sehne mehr als sag vom Bogen
    abweicht (sonst war es wirklich ein Polygon). -> Liste von Prim"""
    P = np.asarray(pts, dtype=float)
    n = len(P)
    out = []
    if n < 2:
        return out
    seg = np.hypot(*(P[1:] - P[:-1]).T)

    def circle(i, j):
        m = (i + j) // 2
        ax, ay = P[i]
        bx, by = P[m]
        cx, cy = P[j]
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-9:
            return None
        ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
        uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
        r = math.hypot(ax - ux, ay - uy)
        if r > 2000 or r < 0.05:
            return None
        Q = P[i:j + 1]
        dev = np.abs(np.hypot(Q[:, 0] - ux, Q[:, 1] - uy) - r)
        if dev.max() > tol:
            return None
        s = seg[i:j]
        smax = float(s.max())
        if smax > 2 * r or r - math.sqrt(max(r * r - smax * smax / 4, 0.0)) > sag:
            return None
        # Drehsinn einheitlich, Gesamtwinkel < 360°
        v = Q - (ux, uy)
        cr = v[:-1, 0] * v[1:, 1] - v[:-1, 1] * v[1:, 0]
        if not ((cr > 0).all() or (cr < 0).all()):
            return None
        sw = float(np.arcsin(np.clip(cr / (r * r), -1, 1)).sum())
        if abs(sw) > 1.9 * math.pi:
            return None
        return ux, uy, r, sw

    i = 0
    line_start = 0
    while i < n - 1:
        best = None
        if i + 2 <= n - 1:
            j = i + 2
            c = circle(i, j)
            if c is not None:
                best = (j, c)
                stp = 2
                while True:  # verdoppeln, solange es passt
                    j2 = min(j + stp, n - 1)
                    if j2 == j:
                        break
                    c2 = circle(i, j2)
                    if c2 is None:
                        break
                    j, best = j2, (j2, c2)
                    stp *= 2
                lo, hi = j, min(j + stp, n - 1)
                while hi - lo > 1:  # Intervallhalbierung
                    mid = (lo + hi) // 2
                    c2 = circle(i, mid)
                    if c2 is not None:
                        lo, best = mid, (mid, c2)
                    else:
                        hi = mid
        arc = None
        if best is not None and (best[0] - i >= 3 or abs(best[1][3]) > 0.35):
            j, (ux, uy, r, sw) = best
            p0, p1 = (float(P[i, 0]), float(P[i, 1])), (float(P[j, 0]), float(P[j, 1]))
            # Mittelpunkt auf die Mittelsenkrechte der Endpunkte legen: Anfangs- und Endradius gleich
            mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            ch = math.hypot(dx, dy)
            if ch > 1e-6:
                nx_, ny_ = -dy / ch, dx / ch
                t = (ux - mx) * nx_ + (uy - my) * ny_
                arc = Prim("A", p0, p1, (mx + t * nx_, my + t * ny_), sw, ff)
                if ok is not None and not ok(arc):   # Bogen verließe die zulässige Fläche: Sehnen behalten
                    arc = None
        if arc is not None:
            if i > line_start:
                out += _lines(P, line_start, i, ff)
            out.append(arc)
            i = best[0]
            line_start = i
        else:
            i += 1
    if n - 1 > line_start:
        out += _lines(P, line_start, n - 1, ff)
    return out


def _lines(P, i, j, ff):
    pts = douglas_peucker([tuple(map(float, p)) for p in P[i:j + 1]], 0.003)
    return [Prim("L", a, b, ff=ff) for a, b in zip(pts, pts[1:]) if math.dist(a, b) > 1e-9]


# --------------------------------------------------------------------------- Fronten
class Piece:
    """Bahnstück: Polygonzug in Fräsrichtung. lead = Stück davor auf dem alten Rand (geräumt)."""
    __slots__ = ("pts", "closed", "it", "ke", "lead", "kind", "parents", "kids", "bbox", "smp", "idx")

    def __init__(self, pts, closed, it, ke, kind="front"):
        self.pts, self.closed, self.it, self.ke, self.kind = pts, closed, it, ke, kind
        self.lead = []
        self.parents, self.kids = set(), set()
        self.bbox = self.smp = None
        self.idx = -1


def _loop_arrays(loops):
    return [np.asarray(_flt(lp), dtype=float) for lp in loops]


def _lead_back(arrs, start, direction, ext):
    """ext mm vor dem Punkt start entlang der Schleife, auf der er liegt (gegen die Fahrtrichtung).
    direction +1: Fahrtrichtung = Umlaufsinn der Schleife. -> Punkte von weit nach nah, ohne start"""
    best = None
    sx, sy = start
    for li, A in enumerate(arrs):
        B = np.roll(A, -1, axis=0)
        ab = B - A
        L2 = np.maximum((ab ** 2).sum(1), 1e-18)
        t = np.clip(((sx - A[:, 0]) * ab[:, 0] + (sy - A[:, 1]) * ab[:, 1]) / L2, 0, 1)
        d = np.hypot(A[:, 0] + t * ab[:, 0] - sx, A[:, 1] + t * ab[:, 1] - sy)
        k = int(d.argmin())
        if best is None or d[k] < best[0]:
            best = (float(d[k]), li, k, float(t[k]))
    if best is None or best[0] > 0.02:
        return []
    _, li, k, t = best
    A = arrs[li]
    n = len(A)
    out, left, cur = [], ext, start
    # rückwärts laufen: bei direction +1 zu Stützpunkt k, k-1, …; bei −1 zu k+1, k+2, …
    j = k if direction > 0 else (k + 1) % n
    if direction > 0 and t < 1e-9:
        j = (k - 1) % n
    if direction < 0 and t > 1 - 1e-9:
        j = (k + 2) % n
    for _ in range(n):
        q = (float(A[j, 0]), float(A[j, 1]))
        d = math.dist(cur, q)
        if d >= left:
            f = left / d if d > 1e-12 else 0.0
            out.append((cur[0] + (q[0] - cur[0]) * f, cur[1] + (q[1] - cur[1]) * f))
            break
        if d > 1e-9:
            out.append(q)
            left -= d
            cur = q
        j = (j - 1) % n if direction > 0 else (j + 1) % n
    out.reverse()
    return out


def _extract(newF, clip, it, ke, climb, ext, kind="front", min_len=0.05):
    """Bahnstücke = Rand von newF außerhalb von clip, in Fräsrichtung, mit Vorlauf auf dem alten Rand."""
    raw = _clip_open(newF, clip)
    if not raw:
        return []
    pieces = []
    for path in raw:
        pts = _flt(path)
        if len(pts) < 2:
            continue
        # Umlaufsinn prüfen: geräumte Fläche (newF) links
        L = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
        m = max(range(len(L)), key=L.__getitem__)
        if L[m] < 1e-6:
            continue
        a, b = pts[m], pts[m + 1]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        nrm = (-(b[1] - a[1]) / L[m], (b[0] - a[0]) / L[m])
        e = min(0.02, L[m])
        lin = inside(newF, (mid[0] + nrm[0] * e, mid[1] + nrm[1] * e))
        rin = inside(newF, (mid[0] - nrm[0] * e, mid[1] - nrm[1] * e))
        if rin and not lin:
            pts.reverse()
        pieces.append(pts)
    # am Schleifenanfang geteilte Stücke wieder verbinden
    merged = True
    while merged and len(pieces) > 1:
        merged = False
        starts = {}
        for i, p in enumerate(pieces):
            starts.setdefault((round(p[0][0], 6), round(p[0][1], 6)), i)
        for i, p in enumerate(pieces):
            j = starts.get((round(p[-1][0], 6), round(p[-1][1], 6)))
            if j is not None and j != i:
                pieces[i] = p + pieces[j][1:]
                del pieces[j]
                merged = True
                break
    arrs = _loop_arrays(newF)
    out = []
    for pts in pieces:
        if _plen(pts) < min_len:
            continue
        closed = math.dist(pts[0], pts[-1]) < 1e-6 and len(pts) > 3
        if not climb:
            pts = pts[::-1]
        pc = Piece(pts, closed, it, ke, kind)
        if not closed and ext > 0:
            pc.lead = _lead_back(arrs, pts[0], 1 if climb else -1, ext)
        out.append(pc)
    return out


def rho_classes(R, k, rho_min, rho_max=None, equal_step=False):
    """Rollradien (groß -> klein) mit zugehörigem Schritt ke. equal_step: überall Schritt k
    (gleiche Bahnabstände) statt des auf gleiche Umschlingung verkleinerten Schritts."""
    rmax = rho_max if rho_max else 2 * R
    rho_min = max(rho_min, 0.02 * R)
    rhos, r = [], rmax
    while r > rho_min * 1.3:
        rhos.append(r)
        r /= 2
    rhos.append(rho_min)
    return [(r, k if equal_step else max(k_eff(r, R, k), 0.01)) for r in rhos]


def _substantial(paths, eps):
    """Teilflächen, die dicker als 2·eps sind (ganze Teilfläche bleibt, Splitter fallen weg)."""
    if not paths:
        return []
    sub = offset(paths, eps)
    if not sub:
        return []
    seeds = [q[0] for q in sub]
    keep = []
    for c in components(paths):
        if any(pyclipper.PointInPolygon(sd, c[0]) != 0 for sd in seeds):
            keep += c
    return keep


def grow_fronts(comp, F, E, R, k, climb, classes, ext, max_it=4000):
    """Rollende Fronten von F aus bis die ganze Fläche comp geräumt ist. -> (Bahnstücke, Schritte)

    Je Schritt: Fneu = F ∪ ⋃ Öffnung((F ⊕ ke_i) ∩ comp, ρ_i) über alle Rollradien. Die große Rolle
    bestimmt die Front in der freien Fläche (voller Schritt), die kleineren ergänzen nur, was sie an
    Wänden, in Ecken und Engstellen übrig lässt – dort mit kleinerem Schritt. Die Front läuft dadurch
    mit zur Wand hin kleiner werdendem Radius und abnehmender Spandicke aus („Fuß“ der Front)."""
    pieces = []
    it = 0
    eps = 0.04
    rho0, ke0 = classes[0]
    while it < max_it:
        it += 1
        # größte Rolle: ganze Fläche
        G = intersect(grow(F, ke0), comp)
        O = intersect(opening(union(G, E) if E else G, rho0), comp) if G else []
        newF = union(F, O) if O else F
        rest = _substantial(difference(G, O) if O else G, eps)  # was die große Rolle nicht erreicht
        for rho, ke in classes[1:]:
            if not rest:
                break
            win = grow(rest, 2 * rho + ke + 1.0)   # nur in der Nähe des Rests rechnen
            Fl = intersect(F, win)
            if not Fl:
                break
            Gl = intersect(intersect(grow(Fl, ke), comp), win)
            if not Gl:
                break
            GE = union(Gl, intersect(E, win)) if E else Gl
            Ol = intersect(opening(GE, rho), comp)
            if Ol:
                newF = union(newF, Ol)
            rest = _substantial(difference(intersect(rest, Gl), Ol) if Ol else intersect(rest, Gl), eps)
        D = _substantial(difference(newF, F), eps) if newF is not F else []
        if not D:
            break
        newF = union(F, D)
        clip = grow(F, TOL_PIECE) + (E or [])
        pieces += _extract(newF, clip, it, ke0, climb, ext)
        F = newF
    # Abschluss 1: was die kleinste Rolle nicht erreicht (enge Nuten, Ecken) mit einfachen Fronten
    step = classes[-1][1]
    while it < max_it:
        rest = difference(comp, F)
        if not rest or not offset(rest, max(step, 0.1)):
            break
        it += 1
        G = intersect(grow(F, step), comp)
        if _area(G) <= _area(F) + 1e-6:
            break
        pieces += _extract(G, grow(F, TOL_PIECE) + (E or []), it, step, climb, ext, kind="plain")
        F = G
    # Abschluss 2: Wandbahn, wo noch mehr als TOL_WALL steht; Lücken < 2R mitfahren
    it += 1
    need = _clip_open(comp, grow(F, TOL_WALL) + (E or []))
    if need:
        gap = buffer_open([_flt(p) for p in need], min(R, 2.0) + TOL_WALL)
        wall = _extract(comp, difference(_box(comp, 10), gap) if gap else [], it, classes[-1][1], climb, ext,
                        kind="wall", min_len=0.2)
        if E:  # Stücke ganz in der Luft weglassen
            wall = [w for w in wall if not all(inside(E, p) for p in w.pts)]
        pieces += wall
    return pieces, it


# --------------------------------------------------------------------------- Reihenfolge
def _link_tree(pieces, R):
    """Abhängigkeiten: ein Stück braucht alle Stücke früherer Schritte, deren Bahn näher als ~R liegt
    (sie räumen das Material hinter ihm). Suche über eine Besitzerkarte (Zelle 1 mm): je Zelle die
    Stücke, die dort durchlaufen; je Stück werden die Zellen im Umkreis R abgefragt."""
    if not pieces:
        return
    lim = 1.05 * R
    c = max(1.0, lim / 6)
    for i, p in enumerate(pieces):
        p.idx = i
        p.smp, _ = _resample(p.pts, 0.8 * c)
    allp = np.vstack([p.smp for p in pieces])
    x0, y0 = allp[:, 0].min() - lim - 2 * c, allp[:, 1].min() - lim - 2 * c
    nx = int((allp[:, 0].max() - x0 + lim) / c) + 3
    ny = int((allp[:, 1].max() - y0 + lim) / c) + 3
    m = int(math.ceil(lim / c)) + 1
    ax = np.arange(-m, m + 1)
    DX, DY = np.meshgrid(ax, ax)
    sel = np.hypot(DX, DY) * c <= lim + c
    dx, dy = DX[sel], DY[sel]
    depth = 4  # Stücke je Zelle (jüngste zuerst)
    own = np.full((depth, ny, nx), -1, dtype=np.int32)
    by_it = {}
    for p in pieces:
        by_it.setdefault(p.it, []).append(p)
    for it in sorted(by_it):
        cells = []
        for p in by_it[it]:
            ix = ((p.smp[:, 0] - x0) / c).astype(int)
            iy = ((p.smp[:, 1] - y0) / c).astype(int)
            cells.append((ix, iy))
            ids = np.unique(own[:, (iy[:, None] + dy[None, :]).ravel(), (ix[:, None] + dx[None, :]).ravel()])
            for j in ids.tolist():
                if j >= 0:
                    p.parents.add(j)
                    pieces[j].kids.add(p.idx)
        for p, (ix, iy) in zip(by_it[it], cells):
            # eintragen: vorhandene Einträge eine Ebene nach hinten schieben
            old = own[:, iy, ix]
            new = np.empty_like(old)
            new[0] = p.idx
            new[1:] = old[:-1]
            keep = old[0] == p.idx
            new[:, keep] = old[:, keep]
            own[:, iy, ix] = new


class Op:
    """Schritt des 2D-Plans: kind "jump" (Rückzug, Eilgang, eintauchen bei p), "link" (Verbindung in
    geräumter Fläche, angehoben) oder "cut" (Bahn)."""
    __slots__ = ("kind", "prims", "p", "air", "slow")

    def __init__(self, kind, prims=None, p=None, air=0.0, slow=False):
        self.kind, self.prims, self.p, self.air, self.slow = kind, prims or [], p, air, slow


class Planner:
    """Ordnet die Bahnstücke, baut Verbindungen und misst die Umschlingung (Rastersimulation)."""

    def __init__(self, comp, grid, R, k, climb, ra, stay=None, lim=None):
        self.comp, self.grid, self.R, self.k, self.climb, self.ra = comp, grid, R, k, climb, ra
        self.loops = _loop_arrays(comp)
        self.safe_in = offset(comp, 0.3)        # sicher innerhalb der Wand
        self.comp_tol = offset(comp, -0.005)    # Wand mit Rechentoleranz
        # zulässige Fläche: Grenze für jedes ausgegebene Element (Region, je Zyklus einmal aufgebaut)
        self.lim = lim if isinstance(lim, Region) else Region(lim if lim is not None else comp)
        th = math.degrees(math.acos(max(-1.0, min(1.0, 1 - k / R))))
        self.th_nom = th
        self.th_slow = min(th + 30.0, 170.0)    # darüber wird der Vorschub gesenkt
        self.stay = stay if stay is not None else 10 * R  # längere Leerwege: Rückzug (Abwägung Zeit gegen Rückzüge)
        self.ops = []
        self.cur = None      # aktuelle Position
        self.head = None     # aktuelle Fahrtrichtung
        self.stats = dict(links=0, jumps=0, slow_jumps=0, eng_max=0.0, slow_len=0.0, cut_len=0.0)

    # ---- Prüfungen
    def allowed(self, P):
        """Alle Punkte innerhalb der zulässigen Fläche (Punktprüfung gegen die Wand, 5 µm Rechentoleranz)."""
        for x, y in P.tolist():
            if not inside(self.safe_in, (x, y)) and not inside(self.comp_tol, (x, y)):
                return False
        return True

    def path_free(self, prims, skip_end=0.0):
        P = prims_points(prims, 0.3)
        if len(P) == 0:
            return True
        if skip_end > 0:
            end = P[-1]
            far = np.hypot(P[:, 0] - end[0], P[:, 1] - end[1]) >= skip_end
            if not self.grid.free(P[far]).all():
                return False
        elif not self.grid.free(P).all():
            return False
        return prims_within(prims, self.lim)

    def _fit(self, pts, ff=1.0):
        """Bogenanpassung; das Ergebnis liegt nachweislich in der zulässigen Fläche (sonst Sehnen)."""
        prims = fit_arcs(pts, ff=ff)
        if prims_within(prims, self.lim):
            return prims
        prims = fit_arcs(pts, ff=ff, ok=lambda a: prims_within([a], self.lim))
        if prims_within(prims, self.lim):
            return prims
        prims = [Prim("L", tuple(map(float, a)), tuple(map(float, b)), ff=ff) for a, b in zip(pts, pts[1:])
                 if math.dist(a, b) > 1e-9]
        if not prims_within(prims, self.lim):
            raise PlanError("outside")
        return prims

    # ---- Bahn
    def _cut(self, pts, air_len=0.0):
        """Polygonzug fräsen: Umschlingung messen, Vorschubfaktoren festlegen, Material abtragen."""
        g = self.grid
        S, T = _resample(pts, SIM_STEP)
        eng = np.zeros(len(S))
        for a in range(0, len(S), 24):  # stückweise: das Werkzeug räumt sich selbst den Weg frei
            b = min(a + 24, len(S))
            eng[a:b] = g.engage(S[a:b], T[a:b])
            g.stamp(S[a:b])
        self.stats["eng_max"] = max(self.stats["eng_max"], float(eng.max()) if len(eng) else 0.0)
        # Vorschubfaktor je Stützpunktabschnitt
        cth = 1 - math.cos(math.radians(self.th_nom))
        ff = np.ones(len(S))
        hot = eng > self.th_slow
        if hot.any():
            f = cth / np.maximum(1 - np.cos(np.radians(np.minimum(eng, 180.0))), 1e-6)
            f = np.clip(f, 0.25, 1.0)
            lv = np.array([1.0, 0.8, 0.65, 0.5, 0.35, 0.25])
            q = lv[np.abs(f[:, None] - lv[None, :]).argmin(1)]
            ff[hot] = q[hot]
            # Übergänge: ein Abtastpunkt davor ebenfalls langsam
            ff[:-1] = np.minimum(ff[:-1], ff[1:])
        # Polygonzug an den Wechseln des Faktors teilen (lange Segmente an den Abtastpunkten)
        P = np.asarray(pts, dtype=float)
        d = np.hypot(*(P[1:] - P[:-1]).T)
        n = np.maximum(1, np.ceil(d / SIM_STEP).astype(int))
        ends = np.cumsum(n)                     # Index in S des Endpunkts jedes Segments
        prims = []
        if not hot.any():
            prims = self._fit(pts)
            slow = 0.0
        else:
            sf = ff[1:]                         # Faktor des Abschnitts, der am Abtastpunkt i+1 endet
            run_pts, run_f, slow = [tuple(map(float, S[0]))], float(sf[0]), 0.0
            seg_end = set(ends.tolist())
            for i in range(len(sf)):
                f = float(sf[i])
                if f != run_f:
                    prims += self._fit(run_pts, run_f)
                    run_pts, run_f = [run_pts[-1]], f
                if (i + 1) in seg_end or i + 1 == len(sf) or float(sf[i + 1]) != f:
                    run_pts.append(tuple(map(float, S[i + 1])))
                if f < 1.0:
                    slow += float(np.hypot(*(S[i + 1] - S[i])))
            prims += self._fit(run_pts, run_f)
        L = float(d.sum())
        self.stats["cut_len"] += L
        self.stats["slow_len"] += slow
        if prims:
            self.ops.append(Op("cut", prims, air=air_len))
            self.cur = prims[-1].p1
            self.head = prims[-1].heading(True)
        return prims

    def _goto(self, p, h, allow_stay=True):
        """Zum Punkt p (Richtung h): Verbindung durch geräumte Fläche oder Rückzug."""
        if self.cur is not None and math.dist(self.cur, p) < 1e-6:
            return
        h = _unit(h)
        if self.cur is not None and self.head is not None and allow_stay and math.dist(self.cur, p) <= self.stay:
            for rr in (self.ra, self.ra / 2):
                for prims in dubins(self.cur, self.head, p, h, rr)[:3]:
                    if sum(q.length for q in prims) > max(2.5 * math.dist(self.cur, p), 6 * self.R):
                        continue
                    if self.path_free(prims):
                        self.ops.append(Op("link", prims))
                        self.stats["links"] += 1
                        self.cur, self.head = p, h
                        return
            # an der Wand entlang (um eine Insel / ein Teil herum, wo die Gerade durch die Wand ginge)
            poly = self._wall_path(self.cur, p)
            if poly is not None:
                S, _ = _resample(poly, 0.4)
                if self.grid.free(S).all():
                    prims = self._fit(poly)
                    if prims:
                        self.ops.append(Op("link", prims))
                        self.stats["links"] += 1
                        self.cur, self.head = p, h
                        return
        # Steht nur eine dünne Haut im Weg (z. B. die Wandreste einer Nut nach der Pendelrampe), auf Tiefe
        # als Schnitt hinfahren: kein Eintauchen, radiale Zustellung unter k
        if allow_stay and self._approach(p):
            self._cut([tuple(self.cur), tuple(p)])
            self.stats["approach"] = self.stats.get("approach", 0) + 1
            self.cur, self.head = p, h
            return
        # Rückzug. Im Eilgang eintauchen nur an einer nachweislich freien Stelle: p selbst oder ein Punkt
        # daneben auf der geräumten Seite, von dem ein freier Weg nach p führt.
        if self.cur is not None and self.ops and self.ops[-1].kind == "cut":
            out = self._lead_out()
            if out:
                self.ops.append(Op("out", out))
        self.stats["jumps"] += 1
        P1 = np.asarray([p], dtype=float)
        if self.grid.clear(p) and self.allowed(P1):
            self.ops.append(Op("jump", p=p))
            self.cur, self.head = p, h
            return
        side = 1.0 if self.climb else -1.0
        nl = (-h[1] * side, h[0] * side)  # zur geräumten Seite
        for dd in (0.7, 1.2, 2.0, 3.0, 4.5):
            for back in (0.0, 1.0, 2.0):
                c = (p[0] + nl[0] * dd - h[0] * back * dd, p[1] + nl[1] * dd - h[1] * back * dd)
                if not self.grid.clear(c) or not self.allowed(np.asarray([c], dtype=float)):
                    continue
                hc = _unit((p[0] - c[0], p[1] - c[1]))
                for prims in dubins(c, hc, p, h, self.ra / 2)[:2] + [[Prim("L", c, p)]]:
                    if sum(q.length for q in prims) < 8 * dd + 6 and self.path_free(prims):
                        self.ops.append(Op("jump", p=c))
                        self.ops.append(Op("link", prims, air=1.0))
                        self.cur, self.head = p, h
                        return
        # keine nachweislich freie Stelle gefunden. Steht nur am äußersten Werkzeugrand noch etwas
        # (Scheibe R − 0,3 leer), im Vorschub von oben zustellen; sonst wäre es ein senkrechter Einstich
        # ins Material – das wird nicht ausgegeben.
        if not self.grid.clear(p, extra=-0.3 - 0.71 * self.grid.h):
            raise PlanError("entry", p[0], p[1])
        self.ops.append(Op("jump", p=p, slow=True))
        self.stats["slow_jumps"] = self.stats.get("slow_jumps", 0) + 1
        self.cur, self.head = p, h

    def _approach(self, p):
        """True, wenn von der aktuellen Stelle (auf Tiefe) geradlinig nach p gefräst werden darf: Weg in der
        zulässigen Fläche, nicht länger als die Verbindungsgrenze, und im Weg steht nur eine Haut von
        höchstens k/2 (max. 1 mm) am Werkzeugrand – die radiale Zustellung bleibt also unter k."""
        if self.cur is None or self.head is None:
            return False
        d = math.dist(self.cur, p)
        if d < 1e-6 or d > self.stay:
            return False
        if not prims_within([Prim("L", tuple(self.cur), tuple(p))], self.lim):
            return False
        # nur eine Haut: im Abstand bis R − skin um die Werkzeugmitte steht nirgends Material
        skin = min(0.5 * self.k, 1.0)
        S, T = _resample([tuple(self.cur), tuple(p)], SIM_STEP)
        return all(self.grid.clear((float(x), float(y)), extra=-skin - 0.71 * self.grid.h) for x, y in S)

    def _on_loop(self, p):
        """-> (Schleife, Kante, Lage auf der Kante), wenn p auf dem Rand der zulässigen Fläche liegt."""
        best = None
        for li, A in enumerate(self.loops):
            B = np.roll(A, -1, axis=0)
            ab = B - A
            L2 = np.maximum((ab ** 2).sum(1), 1e-18)
            t = np.clip(((p[0] - A[:, 0]) * ab[:, 0] + (p[1] - A[:, 1]) * ab[:, 1]) / L2, 0, 1)
            d = np.hypot(A[:, 0] + t * ab[:, 0] - p[0], A[:, 1] + t * ab[:, 1] - p[1])
            k = int(d.argmin())
            if best is None or d[k] < best[0]:
                best = (float(d[k]), li, k, float(t[k]))
        if best is None or best[0] > 0.03:
            return None
        return best[1:]

    def _wall_path(self, p0, p1):
        """Weg von p0 nach p1 auf dem Rand der zulässigen Fläche in Fräsrichtung, wenn beide auf derselben
        Randschleife liegen und der Weg kürzer als die Verbindungsgrenze ist. -> Punktliste oder None"""
        a, b = self._on_loop(p0), self._on_loop(p1)
        if a is None or b is None or a[0] != b[0]:
            return None
        A = self.loops[a[0]]
        n = len(A)
        fwd = self.climb
        out, length = [tuple(p0)], 0.0
        if a[1] == b[1] and ((b[2] >= a[2]) if fwd else (b[2] <= a[2])):
            out.append(tuple(p1))
            return out if math.dist(p0, p1) > 1e-6 else None
        j = (a[1] + 1) % n if fwd else a[1]
        for _ in range(n + 1):
            q = (float(A[j, 0]), float(A[j, 1]))
            length += math.dist(out[-1], q)
            if length > self.stay:
                return None
            if math.dist(out[-1], q) > 1e-9:
                out.append(q)
            # liegt p1 auf der nächsten Kante?
            e = j if fwd else (j - 1) % n
            if e == b[1]:
                out.append(tuple(p1))
                return out
            j = (j + 1) % n if fwd else (j - 1) % n
        return None

    def _lead_out(self):
        """Ausfahrbogen (Viertelkreis zur geräumten Seite) am Ende einer Bahn, wenn er frei ist."""
        p, h = self.cur, self.head
        if p is None or h is None:
            return None
        left = self.climb
        r = self.ra
        while r > 0.24:
            n = _lft(h) if left else (h[1], -h[0])
            c = (p[0] + r * n[0], p[1] + r * n[1])
            q = (c[0] + r * h[0], c[1] + r * h[1])
            a = _arc(p, c, q, left)
            if a is not None and self.path_free([a]):
                return [a]
            r /= 2
        return None

    def _blend_entry(self, ring, i0, ke):
        """Geschlossener Ring: tangentiale Überblendung von innen (geräumte Seite) auf den Ring.
        -> (Punkte der Überblendung, Länge auf dem Ring) oder None"""
        n = len(ring) - 1
        R = self.R
        Lb = max(2.0 * math.sqrt(max(3 * R * ke, 1e-6)), 2.0)
        side = 1.0 if self.climb else -1.0
        seq, s = [], 0.0
        j = i0
        pts = [ring[i0]]
        cut = None
        while s < Lb and len(pts) <= n:
            a, b = ring[j % n], ring[(j + 1) % n]
            d = math.dist(a, b)
            if s + d > Lb + 0.5:  # langes Segment: Überblendung endet mittendrin
                f = (Lb - s) / d
                cut = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
                pts.append(cut)
                s = Lb
                break
            s += d
            pts.append(b)
            j += 1
        if s < 0.5 * Lb:
            return None
        P, T = _resample(pts, 0.5)
        if len(P) >= 3:  # Tangente aus den Nachbarpunkten: winzige Kanten des Polygons verfälschen sie sonst
            D = np.empty_like(P)
            D[1:-1] = P[2:] - P[:-2]
            D[0], D[-1] = P[1] - P[0], P[-1] - P[-2]
            T = D / np.maximum(np.hypot(D[:, 0], D[:, 1]), 1e-12)[:, None]
        dist = np.concatenate([[0.0], np.cumsum(np.hypot(*(P[1:] - P[:-1]).T))])
        tot = dist[-1]
        for d0 in (ke + 0.15, 1.5 * ke + 0.15, 2 * ke + 0.3):
            d = d0 * (1 + np.cos(np.pi * np.clip(dist / tot, 0, 1))) / 2
            Q = P + side * d[:, None] * np.stack([-T[:, 1], T[:, 0]], 1)
            if self.grid.free(Q[:1]).all() and self.allowed(Q):
                seq = [tuple(map(float, q)) for q in Q]
                seq[-1] = pts[-1]
                return seq, j - i0, cut
        return None

    def run(self, pieces, start=None, head=None):
        """Stücke in Abhängigkeits-Reihenfolge abarbeiten. start/head: Position nach Helix/Spirale."""
        self.cur, self.head = start, head
        _link_tree(pieces, self.R)
        left = set(range(len(pieces)))
        done = set()
        ready = {i for i in left if not pieces[i].parents}
        last = None
        R = self.R
        while left:
            if not ready:  # sollte nicht vorkommen (Abhängigkeiten nur zu früheren Schritten)
                ready = {min(left, key=lambda i: pieces[i].it)}
            cands = []
            for i in ready:
                p = pieces[i]
                if self.cur is None:
                    d = float(p.it)
                    j = 0
                elif p.closed:
                    A = np.asarray(p.pts[:-1])
                    dd = np.hypot(A[:, 0] - self.cur[0], A[:, 1] - self.cur[1])
                    j = int(dd.argmin())
                    d = float(dd[j])
                else:
                    s = p.lead[0] if p.lead else p.pts[0]
                    d, j = math.dist(self.cur, s), 0
                # Kosten = Weg bis zum Anfang; weiter als die Verbindungsgrenze heißt Rückzug (teuer, aber
                # dann zählt die Entfernung kaum noch). Nachfolger des letzten Stücks leicht bevorzugt.
                if self.cur is not None:
                    if d > self.stay:
                        d = self.stay + 30.0 + 0.1 * d
                    if last is not None and i in pieces[last].kids:
                        d *= 0.8
                d += 0.02 * (p.it - 1)
                cands.append((d, i, j))
            cands.sort()
            chosen = None
            # Ein Stück wird nur von einer geräumten Stelle aus begonnen. Liegt der Anfang noch im
            # Material, wird es zurückgestellt; bei Ringen werden weitere Anfangspunkte versucht.
            for d, i, j in cands:
                chosen = self._free_start(pieces[i], i, j)
                if chosen:
                    break
            if chosen is None:  # notfalls ein Stück außerhalb der Reihenfolge, das frei beginnt
                for i in sorted(left - ready, key=lambda q: pieces[q].it):
                    chosen = self._free_start(pieces[i], i, 0)
                    if chosen:
                        break
            if chosen is None:  # kein freier Anfang: einer, der auf Tiefe mit kleinem Eingriff erreichbar ist
                for d, i, j in cands:
                    path, air = self._path_of(pieces[i], j)
                    if self._approach(path[0]):
                        chosen = (i, path, air)
                        break
            if chosen is None:
                p0 = pieces[cands[0][1]].pts[0]
                raise PlanError("entry", p0[0], p0[1])
            i, path, air = chosen
            p = pieces[i]
            h = (path[1][0] - path[0][0], path[1][1] - path[0][1])
            self._goto(path[0], h)
            self._cut(path, air_len=air)
            left.discard(i)
            ready.discard(i)
            done.add(i)
            for c in p.kids:
                if c in left and pieces[c].parents <= done:
                    ready.add(c)
            last = i
        return self.ops

    def _free_start(self, p, i, j):
        """-> (Index, Bahn, Luftstück), wenn das Stück an einer geräumten Stelle beginnen kann, sonst None"""
        tries = [j]
        if p.closed:
            n = len(p.pts) - 1
            tries += [(j + n * t // 12) % n for t in range(1, 12)]
        for jj in tries:
            path, air = self._path_of(p, jj)
            if self.grid.free(np.asarray(path[:1], dtype=float))[0]:
                return i, path, air
        return None

    def _path_of(self, p, j):
        """-> (Punkte der Bahn samt Vorlauf bzw. Überblendung, Länge des Luftstücks am Anfang)"""
        if p.closed:
            ring = p.pts[:-1]
            ring = ring[j:] + ring[:j]
            ring = ring + [ring[0]]
            ent = self._blend_entry(ring, 0, p.ke)
            if ent is not None:
                seq, nb, cut = ent
                # Überblendung, dann der ganze Ring bis zum Ende der Überblendung
                return seq + ring[nb + 1:] + ring[1:nb + 1] + ([cut] if cut else []), 0.0
            return ring, 0.0
        lead = list(p.lead)
        if lead:
            L = np.asarray(lead, dtype=float)
            if not self.grid.free(L).all():
                lead = []
        return lead + p.pts, (_plen(lead + [p.pts[0]]) if lead else 0.0)


# --------------------------------------------------------------------------- Plan einer Fläche
def _chord(lim, c, ang, L):
    """Längstes Stück der Geraden durch c (Richtung ang, Grad), das in lim liegt und c enthält.
    -> (Länge², a, b) oder None"""
    u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
    ci = (int(round(c[0] * SCALE)), int(round(c[1] * SCALE)))
    pc = pyclipper.Pyclipper()
    try:
        pc.AddPath(_int([(c[0] - L * u[0], c[1] - L * u[1]), c, (c[0] + L * u[0], c[1] + L * u[1])]),
                   pyclipper.PT_SUBJECT, False)
    except pyclipper.ClipperException:
        return None
    pc.AddPaths(lim, pyclipper.PT_CLIP, True)
    tree = pc.Execute2(pyclipper.CT_INTERSECTION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    best = None
    for o in pyclipper.OpenPathsFromPolyTree(tree):
        a, b = o[0], o[-1]
        ab = (b[0] - a[0], b[1] - a[1])
        l2 = ab[0] ** 2 + ab[1] ** 2
        if l2 < 1:
            continue
        t = ((ci[0] - a[0]) * ab[0] + (ci[1] - a[1]) * ab[1]) / l2
        d = math.hypot(a[0] + t * ab[0] - ci[0], a[1] + t * ab[1] - ci[1])
        if -1e-6 <= t <= 1 + 1e-6 and d < 3 and (best is None or l2 > best[0]):
            best = (l2, _flt([a])[0], _flt([b])[0])
    return best


def _longest_chord(comp, c, more=False):
    """Lange Strecke durch c, die ganz in der Fläche comp liegt. Richtungen: 5°-Raster und die Richtungen
    der Konturkanten (eine Nut liegt selten auf dem Raster), danach Verfeinerung um die beste Richtung.
    more: zusätzlich weitere Punkte der Fläche als Stützpunkt versuchen (gewinkelte Flächen).
    -> (a, b) oder None. Die Strecke ist ein Suchergebnis; ob sie zulässig ist, prüft der Aufrufer."""
    xs = [p[0] for p in comp[0]]
    ys = [p[1] for p in comp[0]]
    L = (max(xs) - min(xs) + max(ys) - min(ys)) / SCALE + 1.0
    lim = offset(comp, 0.002)   # Enden knapp innerhalb
    if not lim:
        return None
    edges = []
    for path in comp:
        q = _flt(path)
        for (x0, y0), (x1, y1) in zip(q, q[1:] + q[:1]):
            d = math.hypot(x1 - x0, y1 - y0)
            if d > 0.05:
                edges.append((d, round(math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180.0, 3),
                              ((x0 + x1) / 2, (y0 + y1) / 2)))
    angs = [5.0 * i for i in range(36)]
    for d, a, _m in sorted(edges, reverse=True):
        if all(abs(a - b) > 1e-3 for b in angs):
            angs.append(a)
        if len(angs) >= 96:
            break
    bases = [c]
    if more:
        # Mitte der Fläche quer zu den längsten Kanten (bei einer gewinkelten Nut: Mitte jedes Schenkels)
        for d, a, m in sorted(edges, reverse=True)[:8]:
            u = (math.cos(math.radians(a + 90)), math.sin(math.radians(a + 90)))
            for sgn in (1, -1):
                q = (m[0] + sgn * 0.004 * u[0], m[1] + sgn * 0.004 * u[1])
                r = _chord(lim, q, a + 90, L)
                if r is not None:
                    bases.append(((r[1][0] + r[2][0]) / 2, (r[1][1] + r[2][1]) / 2))
                    break
    best = None
    for base in bases:
        for ang in angs:
            r = _chord(lim, base, ang, L)
            if r is not None and (best is None or r[0] > best[0][0]):
                best = (r, base, ang)
    if best is None:
        return None
    for span, step in ((2.5, 0.5), (0.5, 0.1), (0.1, 0.02), (0.02, 0.004)):   # Winkel verfeinern
        r0, base, a0 = best
        for i in range(-int(round(span / step)), int(round(span / step)) + 1):
            r = _chord(lim, base, a0 + i * step, L)
            if r is not None and r[0] > best[0][0]:
                best = (r, base, a0 + i * step)
    return best[0][1], best[0][2]


def skipped_passage(allowed, R):
    """Erreichbarer Boden, der durch den Sicherheitsrand verloren geht, unabhängig von der Strategie.
    Dünne Wandsäume zählen nicht; ein um >0,1 mm breiter Rest im Durchgang hingegen schon.
    Das halbe µm zusätzlich vermeidet entartete Reste direkt an der Offset-Grenze."""
    lost = difference(grow(allowed, R), grow(offset(allowed, WALL_MARGIN + 0.0005), R + WALL_MARGIN + 0.01))
    return bool(lost and offset(lost, 0.05))


def plan_regions(allowed, solid, R, k, climb, rh_max, rho_min, ra, rho_max=None, sim_h=SIM_H, equal_step=False,
                 budget=None, debug=False):
    """2D-Plan für alle Teilflächen der zulässigen Werkzeugmitte.

    allowed  zulässige Werkzeugmitte (Clipper-Pfade)
    solid    Fläche, auf der Material steht (Clipper-Pfade), None = überall (geschlossene Tasche)
    budget   Speicherbudget dieses Aufrufs (Budget); None = neues Budget mit MEM_BUDGET. Es gilt für
             alle Teilflächen zusammen und nur für diesen Aufruf.
    debug    Raster und Bahnstücke im Plan behalten (nur für Auswertungen; kostet Speicher)
    -> Liste von Plänen (dict): comp, center, rh, spiral (Prims), ops, stats"""
    budget = budget if budget is not None else Budget()
    budget.hold(2 * 2 ** 20)   # Prüffläche und Grunddaten dieses Aufrufs
    # Sicherheitsrand: geplant wird etwas innerhalb der zulässigen Fläche; jedes ausgegebene Element
    # wird gegen die zulässige Fläche lim geprüft (prims_within)
    lim = Region(allowed)
    full = allowed
    allowed = offset(allowed, WALL_MARGIN)
    comps = components(allowed)
    if not comps:
        return []
    skipped = skipped_passage(full, R)
    classes = rho_classes(R, k, rho_min, rho_max, equal_step)
    box = _box(allowed, 2 * classes[0][0] + 2 * R + 4 * k + 2)  # Platz für die größte Rolle neben dem Rohteil
    E = difference(box, grow(solid, R + 0.2)) if solid is not None else []
    xs = [p[0] for p in box[0]]
    ys = [p[1] for p in box[0]]
    plans = []
    for comp in comps:
        bx = _box(comp, R + 1.0)[0]
        cells = ((bx[2][0] - bx[0][0]) / SCALE / sim_h + 2) * ((bx[2][1] - bx[0][1]) / SCALE / sim_h + 2)
        if cells > MAX_CELLS:
            raise PlanError("size", (bx[2][0] - bx[0][0]) / SCALE, (bx[2][1] - bx[0][1]) / SCALE)
        # Speicher: Bedarf dieser Teilfläche + schon gehaltene Pläne, geprüft vor dem Anlegen des Rasters
        budget.need(plan_need(comp, R, k, sim_h, fill=solid is not None))
        grid = Grid(bx[0][0] / SCALE, bx[0][1] / SCALE, bx[2][0] / SCALE, bx[2][1] / SCALE, R, sim_h)
        if solid is not None:
            grid.mat[:] = False
            grid.fill([_flt(p) for p in union(solid, [])], True)
        free0 = intersect(comp, E) if E else []
        if free0:  # Reste dünner als 0,1 mm zählen nicht als Startfläche
            free0 = [q for c in components(free0) if offset(c, 0.05) for q in c]
        pl = dict(comp=comp, center=None, rh=0.0, spiral=[], open=bool(free0), r_in=0.0)
        planner = Planner(comp, grid, R, k, climb, ra, lim=lim)
        start = head = None
        if free0:
            F = free0
        else:
            c, r_in = inscribed(comp)
            rh = min(rh_max, r_in)
            pl["center"], pl["r_in"] = c, r_in
            ramp = None
            # Werkzeug ohne ANGLE (rh_max = 0): gleiche Entscheidung wie mit Helix, eingetaucht wird senkrecht
            rh_ref = rh_max if rh_max > 0 else 0.95 * R
            if min(rh_ref, r_in) < 0.5 * rh_ref:
                # wenig Platz für eine Helix (schmale Nut): Pendelrampe auf einer langen Sehne der Fläche;
                # ohne ANGLE: senkrecht am Anfang der Sehne, dann die Sehne einmal im Vollschnitt
                need = max(2 * math.pi * min(rh_ref, r_in), 0.3)
                ramp = _longest_chord(comp, c, more=True)
                # nur eine Strecke, die nachweislich in der zulässigen Fläche liegt
                if (ramp is None or math.dist(*ramp) < need
                        or not prims_within([Prim("L", ramp[0], ramp[1])], lim)):
                    ramp = None
            if ramp is not None:
                a, b = ramp
                pl["ramp"] = ramp
                if rh_max <= 0:
                    pl["vertical"] = True
                n = max(1, int(math.ceil(math.dist(a, b) / 0.2)))
                grid.stamp(np.asarray([(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)
                                       for i in range(n + 1)], dtype=float))
                F = intersect(buffer_open([[a, b]], 0.01), comp)
                start, head = b, _unit((b[0] - a[0], b[1] - a[1]))
                planner.cur, planner.head = start, head
                c = pl["center"] = a
            elif rh >= 0.02 or (rh_max <= 0 and r_in >= 0.02):
                # Helix, danach Spirale bis zum größten Kreis um c. Werkzeug ohne ANGLE (rh_max = 0): senkrecht
                # bei c eintauchen und von dort dieselbe Spirale fahren (Radius ab 0), damit die Fronten wie
                # nach einer Helix aus einem Kreis wachsen und nicht aus einem Punkt.
                vertical = rh_max <= 0
                if vertical:
                    rh = 0.0
                # Die Spirale muss in der zulässigen Fläche liegen. r_in ist am Mittelpunkt nachgemessen;
                # reicht das wegen der Prüftoleranz nicht, wird der Kreis verkleinert statt abzubrechen.
                # Geprüft werden die Sehnen des Polygonzugs: bestehen sie, findet _fit immer eine Bahn.
                sp = r1 = None
                for cut in (1e-3, 5e-3, 0.012, 0.03, 0.1, 0.25 * r_in, 0.5 * r_in, 0.75 * r_in):
                    r1 = r_in - cut
                    if r1 < 0.02:
                        break
                    cand = spiral(c, min(rh, r1), r1, k, climb, R=R, g_min=min(k, 0.1 * R) if vertical else 0.02)
                    if prims_within([Prim("L", a, b) for a, b in zip(cand, cand[1:]) if math.dist(a, b) > 1e-9],
                                    lim):
                        sp, rh = cand, min(rh, r1)
                        break
                if sp is None:
                    raise PlanError("noentry", c[0], c[1])
                pl["rh"] = rh
                if vertical:
                    pl["vertical"] = True
                    grid.stamp(np.asarray([c], dtype=float))
                else:
                    ang = np.arange(0, 2 * math.pi, 0.05)
                    grid.stamp(np.stack([c[0] + rh * np.cos(ang), c[1] + rh * np.sin(ang)], 1))
                planner.cur = sp[0]
                planner.head = (0.0, 1.0 if climb else -1.0)
                slow0 = planner.stats["slow_len"]
                planner._cut(sp)
                if vertical:
                    # das Aufweiten nach dem senkrechten Einstich gehört zum Eintauchen (Vorschub ist dort
                    # abgesenkt); es zählt nicht als Engstelle – gemeldet wird der senkrechte Einstich
                    planner.stats["slow_len"] = slow0
                pl["spiral"] = planner.ops.pop().prims
                F = intersect(disc(c[0], c[1], r1 - 1e-3, 256), comp)
                start, head = planner.cur, planner.head
            else:
                # Weder Helix noch Rampe gefunden (oder kein Platz für eine Spirale). Senkrecht eintauchen nur,
                # wenn nachweislich kein Platz ist: Die Fläche der Werkzeugmitte ist in jeder Richtung kürzer
                # als die kürzeste Rampe (0,3 mm). Sonst hat nur die Suche versagt -> Abbruch.
                bb = _box(comp, 0.0)[0]
                if rh_max > 0 and math.hypot(bb[2][0] - bb[0][0], bb[2][1] - bb[0][1]) / SCALE >= 0.3:
                    raise PlanError("noentry", c[0], c[1])
                pl["rh"] = 0.0
                pl["vertical"] = True
                grid.stamp(np.asarray([c], dtype=float))
                F = intersect(disc(c[0], c[1], 0.02, 12), comp)
                start, head = c, None
        pieces, nit = grow_fronts(comp, F, E, R, k, climb, classes, ext=max(ra, 1.0))
        pl["ops"] = planner.run(pieces, start, head)
        pl["stats"] = dict(planner.stats, fronts=nit, pieces=len(pieces))
        if debug:
            pl["pieces"] = pieces
            pl["grid"] = grid
        # Raster, Masken und Bahnstücke werden hier frei; gehalten werden nur die Bahnelemente
        nprim = len(pl["spiral"]) + sum(len(op.prims or ()) for op in pl["ops"])
        budget.hold(500 * nprim + 100 * sum(len(q) for q in comp) + 2000)
        del grid, planner, pieces
        plans.append(pl)
    if plans:
        plans[0]["mem"] = dict(limit=budget.limit, peak=budget.peak, held=budget.held)
        plans[0]["skipped"] = skipped
    return plans
