"""LCNC-Cyclo - werkstattorientierte Bedienoberfläche für LinuxCNC."""

import os

__version__ = "0.1.0"
CYCLO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NGC_DIR = os.path.join(CYCLO_ROOT, "ngc")
