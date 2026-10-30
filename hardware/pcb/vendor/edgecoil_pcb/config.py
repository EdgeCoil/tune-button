# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""What a board project tells the toolkit about itself.

Every option defaults to the newest behaviour. Boards ordered before a fix landed set the option
that keeps their committed output, so a port can be proven identical before anything changes; a
revision then turns the fix on as a reviewed change of its own.
"""
import os
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

PAPER = {"A3": (420.0, 297.0), "A2": (594.0, 420.0)}


@dataclass
class Config:
    project: str                       # "cec-bridge", "tune-button"
    here: str                          # the board's directory: variants are written to here/<variant>/
    ns: uuid.UUID                      # namespace for the board's stable UUIDs
    variants: dict                     # name -> function returning (parts, h, keepouts, silk, extras)
    width: float = 40.0                # board width unless a variant gives extras["width"]
    file_prefix: str = ""              # variant files are <prefix><variant>.kicad_*
    # Local symbol/footprint libraries: nickname -> (directory relative to `here`, description).
    # The directory holds <nickname>.kicad_sym and <nickname>.pretty.
    local_libs: dict = field(default_factory=dict)
    symbol_dir: str = os.environ.get("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols")
    footprint_dir: str = os.environ.get("KICAD_FOOTPRINT_DIR", "/usr/share/kicad/footprints")

    # Schematic.
    paper: str = "A2"
    sheet_bottom: Optional[float] = None   # where a column wraps; None: 20 mm above the border
    flag_x: Optional[float] = None         # x of the PWR_FLAG column; None: one column past the parts
    generator: str = ""                    # default "<project>-gen"
    title: Optional[Callable] = None       # variant -> sheet title; default the variant name
    company: str = ""
    comment: str = ""                      # title block comment 1
    instance_project: Optional[Callable] = None  # variant -> project name in symbol instances
    hide_ic_values: bool = True            # U* values hidden on the sheet (audit: printed over pin names)
    off_sheet_ok: bool = False             # only warn, not stop, for a symbol drawn past the sheet's edge

    # Board.
    power_nets: tuple = ("VBUS", "3V3")    # the wide "Power" net class
    back_text: Optional[Callable] = None   # (variant, w, h) -> [(x, y, text, size)]
    board_hooks: tuple = ()                # functions (board) run after the shell keepouts
    block_copper: list = field(default_factory=list)  # placed blocks' copper (Block.copper), laid locked
    logo_svg: Optional[str] = None         # the board supplies its own mark; the toolkit ships none
    trim_silk: bool = True                 # clear footprint silk off pads and the edge (cec-bridge)
    title_block: bool = True               # board title block: variant name, rev A
    labels_avoid_marks: bool = True        # labels keep off footprints' own silk marks
    labels_avoid_own_outline: bool = True  # and off their own part's outline
    keycap: float = 18.0                   # a 1u MX keycap's square, which labels keep out of
    # Routing replay: refuse redundant segments and joints made only by overlapping copper
    # (cec-bridge audit rounds 16-17). Off, they are only reported.
    replay_checks: bool = True

    def base(self, variant):
        return os.path.join(self.here, variant, f"{self.file_prefix}{variant}")

    def uid(self, *parts):
        return str(uuid.uuid5(self.ns, "/".join(parts)))

    def lib_dir(self, nickname):
        """The directory a library nickname lives in, or None for KiCad's own."""
        if nickname in self.local_libs:
            return os.path.join(self.here, self.local_libs[nickname][0])
        return None

    def sheet(self):
        return PAPER[self.paper]
