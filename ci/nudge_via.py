# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""Negative control for CI: write a copy of a board with its first via moved by 1 um in x.

    python3 ci/nudge_via.py in.kicad_pcb out.kicad_pcb

canon must call the copy different; if it doesn't, the comparison is testing nothing.
"""
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
text = open(src).read()
m = re.search(r"\(via\b[^()]*(?:\([^()]*\)[^()]*)*?\(at ([-\d.]+) ([-\d.]+)\)", text)
if not m:
    sys.exit("nudge_via: no via found")
x = float(m.group(1)) + 0.001
text = text[:m.start(1)] + f"{x:.6f}".rstrip("0").rstrip(".") + text[m.end(1):]
open(dst, "w").write(text)
print(f"nudge_via: via at x={m.group(1)} moved to {x:.6f}")
