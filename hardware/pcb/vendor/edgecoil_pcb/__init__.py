# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""edgecoil-pcb: the shared pipeline behind EdgeCoil's generated KiCad boards.

A board's gen.py keeps only its netlist, placement and variants; everything else is here.
"""
from .board import esd_ground, outline, usb_crossover, zone
from .config import Config
from .geom import mm
from .parts import (C, C0603, C0805, LCSC_C, LCSC_LED_RED, LCSC_R0603, LCSC_R0805, LCSC_R1206, LED0603,
                    LED0805, MIN_DRILL, R, R0603, R0805, R1206, Part, holes)
from .project import build, write_project
