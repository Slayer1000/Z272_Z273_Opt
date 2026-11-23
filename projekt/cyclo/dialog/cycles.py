"""Zyklus-Registry.

Die Parameter der Zyklen kommen aus dem eigenen Katalog ``catalog.py`` (eigene Kurznamen,
Fragen, Vorgaben und Eingabebereiche; gleich zum Dialogformat sind nur Zyklus- und
Q-Nummern und deren Reihenfolge).

Umsetzung (``impl``):
  * "ngc":    Zyklus als LinuxCNC-Unterprogramm cyclo/ngc/cyclo_cyclNNN.ngc (liest #<_qNNN>
              zur Laufzeit).
  * "python": Bahn wird beim Übersetzen berechnet (cyclegen.py) und als eingebettetes
              O-Unterprogramm relativ zur Aufrufposition ausgegeben.
  * "def":    DEF-aktiver Zyklus, wirkt im Übersetzer (Kontur, Koordinatenumrechnung).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import catalog
from ..i18n import N_

# Gruppen in der Reihenfolge der Auswahl "NC-Funktion einfügen"
_GROUP_KEYS = list(catalog.GROUP_NAMES)
CHAPTERS = {i + 1: catalog.GROUP_NAMES[k] for i, k in enumerate(_GROUP_KEYS)}

# Umsetzungsstand je Zyklusnummer
IMPLEMENTED: dict[int, str] = {}


@dataclass(frozen=True)
class CycleParam:
    q: int
    label: str
    prompt: str
    default: float = 0.0
    range: str = ""
    mode: str = ""  # inkremental | absolut | text | ""
    options: tuple = ()
    unit: str = "mm"
    group: str = "Erweitert"


@dataclass
class Cycle:
    number: int
    name: str
    group: str
    params: list[CycleParam] = field(default_factory=list)
    call_active: bool = True
    chapter: int = 0

    @property
    def impl(self) -> str | None:
        return IMPLEMENTED.get(self.number)

    def param(self, q: int) -> CycleParam | None:
        return next((p for p in self.params if p.q == q), None)

    def template(self) -> str:
        """Dialog-Vorlage für "NC-Funktion einfügen"."""
        if not self.params:
            return f"CYCL DEF {self.number} {self.name}"
        lines = [f"CYCL DEF {self.number} {self.name} ~"]
        for i, p in enumerate(self.params):
            tail = " ~" if i < len(self.params) - 1 else ""
            if p.mode == "text":
                lines.append(f'  QS{p.q}="" ;{p.label}{tail}')
            else:
                lines.append(f"  Q{p.q}={_fmt_default(p.default)} ;{p.label}{tail}")
        return "\n".join(lines)


def _fmt_default(v: float) -> str:
    s = f"{v:+.4f}".rstrip("0").rstrip(".")
    return s if s not in ("+", "-") else "+0"


# DEF-aktive Zyklen: wirken beim Lesen, ohne CYCL CALL
DEF_ACTIVE = {7, 8, 9, 10, 11, 12, 13, 14, 20, 26, 32, 247, 270, 271, 2028}

REGISTRY: dict[int, Cycle] = {}


def _load():
    for num, (name, gkey, qs) in catalog.CYCLES.items():
        params = []
        for q in qs:
            d = catalog.qdef(num, q)
            params.append(CycleParam(q, d.label, d.prompt, d.default, d.range, d.mode, d.options, d.unit, d.group))
        REGISTRY[num] = Cycle(num, name, catalog.GROUP_NAMES[gkey], params, call_active=num not in DEF_ACTIVE,
                              chapter=_GROUP_KEYS.index(gkey) + 1)


_load()


def register(c: Cycle) -> Cycle:
    REGISTRY[c.number] = c
    return c


# Zyklus 200 als LinuxCNC-Unterprogramm (Laufzeit-Q-Parameter)
IMPLEMENTED[200] = "ngc"
for _n in (14, 20, 8, 9, 10, 11, 12, 13, 26, 32, 220, 221, 247, 270, 271, 2028, 1271, 1272, 1273, 1278, 1281, 1282):
    IMPLEMENTED[_n] = "def"
for _n in (201, 202, 203, 205, 206, 207, 208, 209, 240, 262, 251, 252, 253, 256, 257, 232, 233,
           21, 22, 23, 24, 25, 254, 258, 204, 241, 263, 264, 265, 267, 272, 273, 274, 277, 275, 225):
    IMPLEMENTED[_n] = "python"


# Vorlagen für Zyklen mit eigener Satzsyntax (keine Q-Parameter)
SPECIAL_TEMPLATES = {
    8: "CYCL DEF 8.0 SPIEGELUNG\nCYCL DEF 8.1 X",
    9: "CYCL DEF 9.0 VERWEILZEIT\nCYCL DEF 9.1 V.ZEIT 1",
    10: "CYCL DEF 10.0 DREHUNG\nCYCL DEF 10.1 ROT+0",
    11: "CYCL DEF 11.0 MASSFAKTOR\nCYCL DEF 11.1 SCL 1",
    12: 'CYCL DEF 12.0 PGM CALL\nCYCL DEF 12.1 PGM "NAME.h"',
    13: "CYCL DEF 13.0 ORIENTIERUNG\nCYCL DEF 13.1 WINKEL 0",
    14: "CYCL DEF 14.0 KONTUR\nCYCL DEF 14.1 KONTURLABEL 1",
    26: "CYCL DEF 26.0 MASSFAKTOR ACHSSPEZ.\nCYCL DEF 26.1 X1 Y1 CCX+0 CCY+0",
    32: "CYCL DEF 32.0 TOLERANZ\nCYCL DEF 32.1 T0.05",
}


def template_for(num: int) -> str:
    if num in SPECIAL_TEMPLATES:
        return SPECIAL_TEMPLATES[num]
    return REGISTRY[num].template()


# --------------------------------------------------------------------------- Formular-Gruppen
GROUPS = ("Geometrie", "Standard", "Erweitert", "Sicherheit")   # Kennungen; Anzeige über _t()
_GROUP_NAMES = (N_("Geometrie"), N_("Standard"), N_("Erweitert"), N_("Sicherheit"))


def param_group(p: CycleParam) -> str:
    """Gruppe im Formular: Geometrie, Standard, Erweitert, Sicherheit (aus dem Katalog)."""
    return p.group if p.group in GROUPS else "Erweitert"
