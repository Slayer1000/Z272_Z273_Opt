"""Abtragssimulation (Z-Dexel / Höhenfeld) mit Kollisionsprüfung und Soll-Ist-Vergleich.

Das Rohteil (BLK FORM) wird als Höhenfeld über ein XY-Raster abgebildet. Jede Bewegung
des Werkzeugs senkt die Höhen unter der Werkzeug-Hüllfläche ab:
  * Schaftfräser (flach), Kugelfräser, Bohrer/Zentrierer (Kegel mit T-ANGLE)
  * geschwenktes Werkzeug (B-Achse): Kugelkette entlang der Werkzeugachse (Näherung)
Prüfungen wie in der Steuerungssimulation:
  * Eilgang im Material
  * Schaft/Halter (oberhalb der Schneidenlänge LCUTS) berührt das Werkstück
  * Werkzeug unter der Rohteilunterkante (Tisch)
Soll-Ist: Fertigteil als STL rastern und mit dem simulierten Werkstück vergleichen.

Grenze des Höhenfelds: Hinterschnitte (z. B. mit B = 90°) sind nicht darstellbar. Dafür
ist ein Tri-Dexel-Modell vorgesehen (Fahrplan), dessen Rechenkern später in Rust
(optional über SolidCraft, siehe ARCHITEKTUR.md) entstehen kann.
"""

from __future__ import annotations

from ..i18n import _t

import math
import struct
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ToolShape:
    radius: float
    kind: str = "flat"  # flat | ball | drill
    tip_angle: float = 118.0
    lcuts: float | None = None  # Schneidenlänge (Schaftprüfung)
    # Halter als Rotationskörper: (L, ((z0, z1, r0, r1), …)) – z ab Bezugslinie nach unten (≤ 0),
    # L = Werkzeuglänge (Spitze -> Bezugslinie). None = kein Halter bekannt.
    holder: tuple | None = None

    def holder_underside(self, d: np.ndarray):
        """Unterkante des Halters über der Werkzeugspitze im Abstand d von der Achse (NaN = kein Halter)."""
        out = np.full(d.shape, np.nan, dtype=np.float64)
        if not self.holder:
            return out
        L, segs = self.holder
        for z0, z1, r0, r1 in segs:
            if max(r0, r1) <= 0:
                continue
            zb, hh = L + z1, z0 - z1
            if r0 > r1:   # nach oben breiter (Kegel): Unterkante steigt mit d
                u = np.where(d <= r1, zb, zb + (d - r1) / (r0 - r1) * hh)
            else:
                u = np.full(d.shape, zb)
            u = np.where(d <= max(r0, r1), u, np.nan)
            out = np.fmin(out, u)
        return out

    def body_profile(self):
        """Teile über der Schneide als Rotationskörper entlang der Werkzeugachse ab der Spitze:
        [(s0, s1, rho0, rho1)] (s0 < s1, rho0 bei s0). Schaft ab LCUTS, dann die Halterkontur."""
        out = []
        top = self.holder_low if self.holder else None
        if self.lcuts:
            s1 = top if top is not None and top < 1e8 else self.lcuts + 6 * self.radius
            if s1 > self.lcuts:
                out.append((float(self.lcuts), float(s1), self.radius, self.radius))
        if self.holder:
            L, segs = self.holder
            for z0, z1, r0, r1 in segs:
                if max(r0, r1) > 0 and z0 > z1:
                    out.append((L + z1, L + z0, r1, r0))
        return out

    @property
    def holder_radius(self) -> float:
        return max((max(s[2], s[3]) for s in self.holder[1]), default=0.0) if self.holder else 0.0

    @property
    def holder_low(self) -> float:
        """Tiefster Punkt des Halters über der Spitze."""
        return min((self.holder[0] + s[1] for s in self.holder[1] if max(s[2], s[3]) > 0), default=1e9) \
            if self.holder else 1e9

    @classmethod
    def from_table(cls, d: dict | None):
        d = d or {}
        r = float(d.get("R", 0) or 0) or 1.0
        name = str(d.get("NAME", "")).upper()
        typ = d.get("TYPE")
        if typ in ("ball", "probe"):
            kind = "ball"
        elif typ in ("drill", "center", "chamfer", "engrave") or (not typ and d.get("T_ANGLE")):
            kind = "drill"
        elif not typ and ("KUGEL" in name or "BALL" in name):
            kind = "ball"
        else:
            kind = "flat"
        holder = None
        stack = d.get("HOLDER_STACK")
        L = float(d.get("L") or 0.0)
        if stack and L > 0:
            holder = (L, tuple((float(a), float(b), float(c), float(e)) for a, b, c, e in stack))
        return cls(r, kind, float(d.get("T_ANGLE") or 118.0), d.get("LCUTS"), holder)


@dataclass
class Event:
    line: int
    kind: str  # rapid | holder (Schaft/Halter) | below
    text: str
    pos: tuple | None = None   # Werkzeugspitze (x, y, z, b) bei der Feststellung – zum Hinspringen


@dataclass
class ZMap:
    x0: float
    y0: float
    res: float
    nx: int
    ny: int
    ztop: float
    zbot: float
    h: np.ndarray = None
    events: list = field(default_factory=list)
    tid: np.ndarray = None      # je Zelle: Werkzeug, das zuletzt abgetragen hat (0 = Rohteil)
    cur_tool: int = 0
    # gemeldete Prüfungen (Einstellungen → Prüfungen): rapid, below, holder
    checks: frozenset = frozenset({"rapid", "below", "holder"})

    @classmethod
    def from_stock(cls, mn, mx, max_cells=220_000):
        w, d = mx[0] - mn[0], mx[1] - mn[1]
        res = max(math.sqrt(w * d / max_cells), 0.05)
        nx, ny = max(2, int(math.ceil(w / res))), max(2, int(math.ceil(d / res)))
        z = cls(mn[0], mn[1], res, nx, ny, mx[2], mn[2])
        z.h = np.full((ny, nx), float(mx[2]), dtype=np.float32)
        z.tid = np.zeros((ny, nx), dtype=np.int32)
        z.h0 = None
        return z

    @classmethod
    def from_stock_dict(cls, st: dict, max_cells=220_000):
        """Rohteil aus der Übersetzung: Quader oder Zylinder/Rohr (BLK FORM CYLINDER).
        Zellen ohne Material sind NaN. Stehender Zylinder: Kreis bzw. Ring; liegender Zylinder:
        gewölbte Oberseite (eine Bohrung im liegenden Rohr ist im Höhenfeld nicht darstellbar)."""
        z = cls.from_stock(st["min"], st["max"], max_cells)
        if st.get("shape") == "cylinder":
            X, Y = z._cell_xy(0, z.nx, 0, z.ny)
            c, r, ri, rot = st["center"], float(st["r"]), float(st.get("ri") or 0.0), st.get("rot", "Z")
            if rot == "Z":
                d = np.hypot(X - c[0], Y - c[1])
                z.h[(d > r) | (d < ri)] = np.nan
            else:
                q = (Y - c[1]) if rot == "X" else (X - c[0])
                top = c[2] + np.sqrt(np.maximum(r * r - q * q, 0.0))
                z.h[:] = np.where(np.abs(q) <= r, top, np.nan).astype(np.float32)
        z.h0 = z.h.copy()
        return z

    # ------------------------------------------------------------ Geometrie
    def _window(self, cx, cy, r):
        i0 = max(int(math.floor((cx - r - self.x0) / self.res)), 0)
        i1 = min(int(math.ceil((cx + r - self.x0) / self.res)) + 1, self.nx)
        j0 = max(int(math.floor((cy - r - self.y0) / self.res)), 0)
        j1 = min(int(math.ceil((cy + r - self.y0) / self.res)) + 1, self.ny)
        return i0, i1, j0, j1

    def _cell_xy(self, i0, i1, j0, j1):
        xs = self.x0 + (np.arange(i0, i1) + 0.5) * self.res
        ys = self.y0 + (np.arange(j0, j1) + 0.5) * self.res
        return np.meshgrid(xs, ys)

    @staticmethod
    def _profile(tool: ToolShape, d):
        """Höhe der Werkzeugunterkante über der Spitze im Abstand d von der Achse (NaN = außerhalb)."""
        r = tool.radius
        out = np.full(d.shape, np.nan, dtype=np.float32)
        m = d <= r
        if tool.kind == "ball":
            out[m] = r - np.sqrt(np.maximum(r * r - d[m] ** 2, 0))
        elif tool.kind == "drill":
            out[m] = d[m] / math.tan(math.radians(max(tool.tip_angle, 1.0) / 2))
        else:
            out[m] = 0.0
        return out

    # ------------------------------------------------------------ Abtrag
    def cut(self, p0, p1, tool: ToolShape, rapid=False, line=-1, b_deg=0.0):
        """Bewegung p0 -> p1 (Werkzeugspitze, x y z) abtragen; Ereignisse sammeln."""
        self._at = (p1[0], p1[1], p1[2], b_deg)   # Ort für Befunde (genauer, wo bekannt)
        if abs(b_deg) > 0.01:
            return self._cut_tilted(p0, p1, tool, rapid, line, b_deg)
        r = tool.radius
        x0, y0, z0 = p0[:3]
        x1, y1, z1 = p1[:3]
        if min(z0, z1) >= self.ztop and min(z0, z1) - (tool.lcuts or 1e9) >= self.ztop:
            return
        if min(z0, z1) < self.zbot - 1e-6:
            self._event(line, "below", _t("Werkzeug unter Rohteilunterkante (Tisch!)"))
        if tool.holder and "holder" in self.checks and min(z0, z1) + tool.holder_low < self.ztop:
            self._holder_check(x0, y0, z0, x1, y1, z1, tool, line)
        L = math.hypot(x1 - x0, y1 - y0)
        if abs(z1 - z0) < 1e-6 or L < 1e-9:
            # waagerecht (exakt über Abstand zur Strecke) oder senkrecht (Endpunkt)
            if L < 1e-9:
                self._apply_segment(x1, y1, x1, y1, min(z0, z1), tool, rapid, line)
            else:
                self._apply_segment(x0, y0, x1, y1, z0, tool, rapid, line)
            return
        # Rampe/Helix: abtasten
        n = max(2, int(math.ceil(max(L, abs(z1 - z0)) / max(self.res, r / 4))))
        for k in range(1, n + 1):
            t = k / n
            xa, ya = x0 + (x1 - x0) * (k - 1) / n, y0 + (y1 - y0) * (k - 1) / n
            xb, yb = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            self._apply_segment(xa, ya, xb, yb, z0 + (z1 - z0) * t, tool, rapid, line)

    def _apply_segment(self, xa, ya, xb, yb, z, tool, rapid, line):
        r = tool.radius
        i0 = max(int(math.floor((min(xa, xb) - r - self.x0) / self.res)), 0)
        i1 = min(int(math.ceil((max(xa, xb) + r - self.x0) / self.res)) + 1, self.nx)
        j0 = max(int(math.floor((min(ya, yb) - r - self.y0) / self.res)), 0)
        j1 = min(int(math.ceil((max(ya, yb) + r - self.y0) / self.res)) + 1, self.ny)
        if i0 >= i1 or j0 >= j1:
            return
        X, Y = self._cell_xy(i0, i1, j0, j1)
        dx, dy = xb - xa, yb - ya
        ll = dx * dx + dy * dy
        if ll < 1e-12:
            d = np.hypot(X - xa, Y - ya)
        else:
            t = np.clip(((X - xa) * dx + (Y - ya) * dy) / ll, 0, 1)
            d = np.hypot(X - (xa + t * dx), Y - (ya + t * dy))
        prof = self._profile(tool, d)
        zc = z + prof
        sub = self.h[j0:j1, i0:i1]
        m = ~np.isnan(zc) & (zc < sub)
        if not m.any():
            return
        if tool.lcuts and np.any(sub[m] > z + tool.lcuts + 1e-3):
            self._event(line, "holder", _t("Werkzeugschaft/Halter berührt das Werkstück (LCUTS)"), (xa, ya, z, 0.0))
        if rapid and np.any(sub[m] - zc[m] > 0.02):
            self._event(line, "rapid", _t("Eilgang im Material"), (xa, ya, z, 0.0))
        sub[m] = zc[m]
        if self.tid is not None:
            self.tid[j0:j1, i0:i1][m] = self.cur_tool

    def _holder_check(self, x0, y0, z0, x1, y1, z1, tool, line):
        """Halterkontur gegen das Material vor dieser Bewegung (Rampe: abschnittsweise, tiefste Höhe)."""
        R = tool.holder_radius
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(math.ceil(abs(z1 - z0) / max(self.res, 1.0)))) if L > 1e-9 else 1
        for k in range(n):
            xa, ya = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
            xb, yb = x0 + (x1 - x0) * (k + 1) / n, y0 + (y1 - y0) * (k + 1) / n
            z = min(z0 + (z1 - z0) * k / n, z0 + (z1 - z0) * (k + 1) / n)
            i0 = max(int(math.floor((min(xa, xb) - R - self.x0) / self.res)), 0)
            i1 = min(int(math.ceil((max(xa, xb) + R - self.x0) / self.res)) + 1, self.nx)
            j0 = max(int(math.floor((min(ya, yb) - R - self.y0) / self.res)), 0)
            j1 = min(int(math.ceil((max(ya, yb) + R - self.y0) / self.res)) + 1, self.ny)
            if i0 >= i1 or j0 >= j1:
                continue
            sub = self.h[j0:j1, i0:i1]
            if not np.nanmax(sub, initial=-1e9) > z + tool.holder_low:
                continue
            X, Y = self._cell_xy(i0, i1, j0, j1)
            dx, dy = xb - xa, yb - ya
            ll = dx * dx + dy * dy
            if ll < 1e-12:
                d = np.hypot(X - xa, Y - ya)
            else:
                t = np.clip(((X - xa) * dx + (Y - ya) * dy) / ll, 0, 1)
                d = np.hypot(X - (xa + t * dx), Y - (ya + t * dy))
            u = tool.holder_underside(d)
            with np.errstate(invalid="ignore"):
                if np.any(sub > z + u + max(0.02, self.res * 0.1)):
                    self._event(line, "holder", _t("Werkzeughalter berührt das Werkstück"), (xa, ya, z, 0.0))
                    return

    def _body_check_tilted(self, p0, p1, tool, line, b_deg):
        """Schaft (über LCUTS) und Halter bei geschwenkter Achse gegen das Material vor der Bewegung.

        Der Körper wird in Scheiben quer zur Achse zerlegt (Abstand ds); je Scheibe und Zelle die Höhe,
        in der die senkrechte Zellsäule die Scheibe schneidet. Material darüber = Berührung."""
        prof = tool.body_profile()
        b = math.radians(b_deg)
        az = math.cos(b)
        if not prof or az < 0.05:   # (fast) waagrechte Achse: Säulen schneiden Scheiben nicht in einem Punkt
            return
        ax, ay = -math.sin(b), 0.0
        sb = abs(math.sin(b))
        ds = max(self.res, 1.0)
        discs = []
        for s0, s1, r0, r1 in prof:
            n = max(1, int(math.ceil((s1 - s0) / ds)))
            for k in range(n + 1):
                t = k / n
                discs.append((s0 + (s1 - s0) * t, r0 + (r1 - r0) * t))
        smin = min(d[0] for d in discs)
        rmax = max(d[1] for d in discs)
        tol = 0.1 + self.res
        stride = max(1, int(round(0.5 / self.res)))
        L = math.dist(p0[:3], p1[:3])
        n = max(1, int(math.ceil(L / max(self.res * 2, 2.0))))
        for k in range(n + 1):
            t = k / n
            c = [p0[i] + (p1[i] - p0[i]) * t for i in range(3)]
            # tiefster Punkt des ganzen Körpers über dem höchsten Material? -> nichts zu prüfen
            if c[2] + smin * az - rmax * sb >= self.ztop:
                continue
            # höchstes Material unter dem ganzen Körper (ein Fenster) – Scheiben darüber sofort weglassen
            xs = [c[0] + ax * sd for sd, _ in (discs[0], discs[-1])]
            i0, i1, j0, j1 = self._window((min(xs) + max(xs)) / 2, c[1],
                                          rmax + (max(xs) - min(xs)) / 2)
            if i0 >= i1 or j0 >= j1:
                continue
            sub = self.h[j0:j1, i0:i1]
            hmax = float(np.nanmax(sub, initial=-1e9))
            cand = [(sd, rho) for sd, rho in discs if c[2] + az * sd - rho * sb + tol < hmax]
            if not cand:
                continue
            X, Y = self._cell_xy(i0, i1, j0, j1)
            # Zellen ausdünnen (etwa 0,5 mm): Halter/Schaft sind groß, Rechenzeit bleibt klein
            sub, X, Y = sub[::stride, ::stride], X[::stride, ::stride], Y[::stride, ::stride]
            sd = np.array([d[0] for d in cand])[:, None, None]
            rho = np.array([d[1] for d in cand])[:, None, None]
            dx = X[None] - (c[0] + ax * sd)
            dy = Y[None] - (c[1] + ay * sd)
            # Punkt der Scheibenebene über (X, Y): (p - q)·a = 0
            dz = -(dx * ax + dy * ay) / az
            inside = dx * dx + dy * dy + dz * dz <= rho * rho
            hit = inside & (sub[None] > c[2] + az * sd + dz + tol)
            if hit.any():
                k = int(np.argmax(hit.reshape(len(cand), -1).any(axis=1)))
                self._event(line, "holder", _t("Werkzeughalter berührt das Werkstück") if
                            tool.holder and cand[k][0] >= tool.holder_low - 1e-6 else
                            _t("Werkzeugschaft/Halter berührt das Werkstück (LCUTS)"), (c[0], c[1], c[2], b_deg))
                return

    def _cut_tilted(self, p0, p1, tool, rapid, line, b_deg):
        """Geschwenktes Werkzeug: Kugelkette entlang der Achse (Spitze -> Halter)."""
        if "holder" in self.checks and (tool.lcuts or tool.holder):
            self._body_check_tilted(p0, p1, tool, line, b_deg)
        b = math.radians(b_deg)
        ax = (-math.sin(b), 0.0, math.cos(b))
        r = tool.radius
        length = tool.lcuts or 4 * r
        nk = max(1, int(length / r))
        L = math.dist(p0[:3], p1[:3])
        step = max(self.res, r / 3)
        n = max(1, int(math.ceil(L / step)))
        # Kugelkette: Riefen zwischen den Abtastpunkten nicht als "Eilgang im Material" melden
        # (Näherung, im Höhenfeld auch an schrägen Bohrungen): erst ab einem Viertel Radius melden
        tol = max(0.02 + r - math.sqrt(max(r * r - (step / 2) ** 2 - 2 * self.res ** 2, 0.0)), 0.25 * r)
        for k in range(n + 1):
            t = k / n
            c = [p0[i] + (p1[i] - p0[i]) * t for i in range(3)]
            for s in range(nk + 1):
                sc = [c[i] + ax[i] * (r + s * r) for i in range(3)]
                i0, i1, j0, j1 = self._window(sc[0], sc[1], r)
                if i0 >= i1 or j0 >= j1:
                    continue
                X, Y = self._cell_xy(i0, i1, j0, j1)
                dd = (X - sc[0]) ** 2 + (Y - sc[1]) ** 2
                m = dd <= r * r
                zc = sc[2] - np.sqrt(np.maximum(r * r - dd, 0))
                sub = self.h[j0:j1, i0:i1]
                mm = m & (zc < sub)
                if mm.any():
                    if rapid and np.any(sub[mm] - zc[mm] > tol):
                        self._event(line, "rapid", _t("Eilgang im Material"))
                    sub[mm] = zc[mm]
                    if self.tid is not None:
                        self.tid[j0:j1, i0:i1][mm] = self.cur_tool

    def _event(self, line, kind, text, pos=None):
        if kind not in self.checks:
            return
        if not any(e.line == line and e.kind == kind for e in self.events):
            if pos is None:
                pos = getattr(self, "_at", None)
            self.events.append(Event(line, kind, text, tuple(float(v) for v in pos) if pos is not None else None))

    def run(self, moves, tools: dict, start=0, stop=None):
        """Bewegungen moves[start:stop] abtragen. tools: {T: ToolShape}."""
        for mv in moves[start:stop]:
            tool = tools.get(mv.tool)
            if tool is None:
                continue
            self.cur_tool = int(mv.tool or 0)
            pts = mv.points
            if not getattr(mv, "start_known", True):
                pts = pts[-1:] * 2  # Startpunkt unbekannt (nach Werkzeugwechsel): nur Zielpunkt
            for a, b in zip(pts[:-1], pts[1:]):
                bdeg = b[4] if len(b) > 4 else 0.0
                self.cut(a, b, tool, mv.kind == "rapid", mv.line, bdeg)
        return self

    # ------------------------------------------------------------ Volumen
    def removed_volume(self) -> float:
        h0 = getattr(self, "h0", None)
        base = h0 if h0 is not None else self.ztop
        return float(np.nansum(base - self.h)) * self.res * self.res


# =========================================================================== STL / Soll-Ist
def load_stl(path) -> np.ndarray:
    """Dreiecke (n, 3, 3) aus binärer oder ASCII-STL."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:5].lower() == b"solid" and b"facet" in data[:400]:
        nums = [float(x) for x in data.decode("ascii", "replace").split() if _isnum(x)]
        verts = []
        for line in data.decode("ascii", "replace").splitlines():
            line = line.strip()
            if line.startswith("vertex"):
                verts.append([float(v) for v in line.split()[1:4]])
        del nums
        return np.array(verts, dtype=np.float64).reshape(-1, 3, 3)
    n = struct.unpack("<I", data[80:84])[0]
    arr = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
                        count=n, offset=84)
    return arr["v"].astype(np.float64)


def _isnum(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def target_heights(zm: ZMap, tris: np.ndarray, offset=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Oberseite des Fertigteils auf dem Raster von zm (NaN = kein Material)."""
    t = tris + np.asarray(offset)
    out = np.full((zm.ny, zm.nx), np.nan, dtype=np.float32)
    for tri in t:
        xs, ys = tri[:, 0], tri[:, 1]
        i0 = max(int((xs.min() - zm.x0) / zm.res), 0)
        i1 = min(int((xs.max() - zm.x0) / zm.res) + 2, zm.nx)
        j0 = max(int((ys.min() - zm.y0) / zm.res), 0)
        j1 = min(int((ys.max() - zm.y0) / zm.res) + 2, zm.ny)
        if i0 >= i1 or j0 >= j1:
            continue
        X, Y = zm._cell_xy(i0, i1, j0, j1)
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / den
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / den
        l3 = 1 - l1 - l2
        m = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
        if not m.any():
            continue
        z = l1 * az + l2 * bz + l3 * cz
        sub = out[j0:j1, i0:i1]
        upd = m & (np.isnan(sub) | (z > sub))
        sub[upd] = z[upd]
    return out


# =========================================================================== Darstellung
STOCK = np.array([168, 182, 199], dtype=np.float32)


TOOL_COLORS = np.array([(70, 140, 220), (230, 150, 40), (90, 180, 90), (200, 80, 160), (150, 110, 220),
                        (40, 180, 180), (220, 90, 70), (160, 160, 60), (110, 110, 110), (240, 120, 160)], float)


def render(zm: ZMap, w: int, h: int, az: float, el: float, scale: float, center, pan=(0.0, 0.0),
           diff: np.ndarray | None = None, tol: float = 0.05, tool_colors: bool = False,
           section: tuple | None = None) -> np.ndarray:
    """Software-Renderer: Höhenfeld als schattierte Punktwolke (Painter-Verfahren).

    Liefert ein RGB-Array (h, w, 3) uint8; Hintergrund = 255 (wird transparent überlagert).
    ``diff`` (simuliert - Soll) färbt Restmaterial gelb/rot und Verletzungen blau.
    ``tool_colors``: bearbeitete Flächen in der Farbe des Werkzeugs (je T-Nummer), Rohteil grau.
    ``section``: ("X" | "Y", Wert) – Schnittansicht, der Teil vor dem Schnitt wird weggelassen.
    """
    empty = np.isnan(zm.h)   # kein Material (runde Rohteile)
    H = np.where(empty, zm.zbot, zm.h) if empty.any() else zm.h
    ny, nx = H.shape
    res = zm.res
    gx = np.zeros_like(H)
    gy = np.zeros_like(H)
    gx[:, 1:-1] = (H[:, 2:] - H[:, :-2]) / (2 * res)
    gy[1:-1, :] = (H[2:, :] - H[:-2, :]) / (2 * res)
    nrm = np.sqrt(gx * gx + gy * gy + 1)
    light = np.array([-0.35, -0.55, 0.76])
    shade = np.clip((-gx * light[0] - gy * light[1] + light[2]) / nrm, 0.15, 1.0)
    depthc = (H - zm.zbot) / max(zm.ztop - zm.zbot, 1e-6)
    base = STOCK[None, None, :]
    if tool_colors and zm.tid is not None:
        cut = zm.tid > 0
        tc = TOOL_COLORS[(zm.tid - 1) % len(TOOL_COLORS)]
        base = np.where(cut[..., None], tc, np.array([175, 175, 175], float)[None, None, :])
    col = base * (0.55 + 0.45 * shade[..., None]) * (0.8 + 0.2 * depthc[..., None])
    if diff is not None:
        rest = np.nan_to_num(diff, nan=0.0)
        over = rest > tol
        under = rest < -tol
        k = np.clip(rest / 1.0, 0, 1)[..., None]
        col = np.where(over[..., None], (1 - k) * np.array([240, 220, 60]) + k * np.array([220, 40, 30]), col)
        col = np.where(under[..., None], np.array([60, 90, 230]) * (0.6 + 0.4 * shade[..., None]), col)
    xs = zm.x0 + (np.arange(nx) + 0.5) * res
    ys = zm.y0 + (np.arange(ny) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    keep = np.ones_like(H, dtype=bool)
    if section is not None:
        keep = (X >= section[1]) if section[0] == "X" else (Y >= section[1])
    keep &= ~empty
    pts = [(X[keep], Y[keep], H[keep], col[keep])]
    # Seitenwände des Rohteils und steile Wände (Taschen) als gestapelte Punkte
    nb = np.minimum.reduce([np.pad(H, 1, mode="edge")[1:-1, :-2], np.pad(H, 1, mode="edge")[1:-1, 2:],
                            np.pad(H, 1, mode="edge")[:-2, 1:-1], np.pad(H, 1, mode="edge")[2:, 1:-1]])
    edge = np.zeros_like(H, dtype=bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    if empty.any():  # Rand zu leeren Zellen: Wand bis zur Unterkante
        ep = np.pad(empty, 1, constant_values=False)
        edge |= ep[1:-1, :-2] | ep[1:-1, 2:] | ep[:-2, 1:-1] | ep[2:, 1:-1]
    if section is not None:   # Schnittkante: dort bis zur Unterkante zeichnen (Schnittfläche)
        kp = np.pad(keep, 1, constant_values=True)
        edge |= keep & ~(kp[1:-1, :-2] & kp[1:-1, 2:] & kp[:-2, 1:-1] & kp[2:, 1:-1])
    low = np.where(edge, zm.zbot, nb)
    drop = H - low
    wall = (drop > res * 1.5) & keep
    if wall.any():
        wx, wy, wz0, wd = X[wall], Y[wall], H[wall], drop[wall]
        wc = col[wall] * 0.72
        steps = np.minimum(np.ceil(wd / (res * 1.2)).astype(int), 400)
        tot = int(steps.sum())
        if tot < 3_000_000:
            rep = np.repeat(np.arange(wx.size), steps)
            off = np.arange(tot) - np.repeat(np.cumsum(steps) - steps, steps)
            zz = wz0[rep] - (off + 1) * (wd[rep] / steps[rep])
            pts.append((wx[rep], wy[rep], zz, wc[rep] * (0.85 + 0.15 * (zz - zm.zbot)[:, None] /
                                                          max(zm.ztop - zm.zbot, 1e-6))))
    PX = np.concatenate([p[0] for p in pts]) - center[0]
    PY = np.concatenate([p[1] for p in pts]) - center[1]
    PZ = np.concatenate([p[2] for p in pts]) - center[2]
    PC = np.concatenate([p[3] for p in pts])
    a, e = math.radians(az), math.radians(el)
    ca, sa, ce, se = math.cos(a), math.sin(a), math.cos(e), math.sin(e)
    x1 = PX * ca - PY * sa
    y1 = PX * sa + PY * ca
    sx = (w / 2 + pan[0]) + x1 * scale
    sy = (h / 2 + pan[1]) - (PZ * ce + y1 * se) * scale
    depth = (y1 * ce - PZ * se).astype(np.float32)
    # Tiefenreihenfolge (hinten zuerst); gleiche Tiefe = gleicher Punkt, daher reicht die schnelle Sortierung
    order = np.argsort(-depth)
    splat = min(4, max(1, int(math.ceil(res * scale)) + 1))
    # Farben als RGBA in einem uint32 (ein Schreibzugriff je Pixel statt vier)
    rgb = np.clip(PC, 0, 255).astype(np.uint32)
    packed = rgb[:, 0] | (rgb[:, 1] << 8) | (rgb[:, 2] << 16) | np.uint32(0xFF000000)
    # Zeichenfläche mit Rand: Punkte am/außerhalb des Bildrands landen im Rand statt einer Maske je Pixel
    pad = splat
    W2, H2 = w + 2 * pad, h + 2 * pad
    ixs = np.clip(sx[order] + pad, 0, W2 - splat).astype(np.int32)
    iys = np.clip(sy[order] + pad, 0, H2 - splat).astype(np.int32)
    col = packed[order]
    flat_base = iys * W2 + ixs
    canvas = np.zeros(H2 * W2, dtype=np.uint32)  # transparent
    half = splat // 2
    # je Punkt splat×splat Pixel; spätere (nähere) Punkte überschreiben frühere
    offs = np.array([(dy - half) * W2 + (dx - half) for dy in range(splat) for dx in range(splat)], dtype=np.int32)
    idx = (flat_base[:, None] + offs[None, :]).ravel()
    np.clip(idx, 0, H2 * W2 - 1, out=idx)
    canvas[idx] = np.repeat(col, offs.size)
    img = canvas.reshape(H2, W2)[pad:pad + h, pad:pad + w].view(np.uint8).reshape(h, w, 4)
    return img
