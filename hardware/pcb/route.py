# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Route a generated board, then fill the ground pours (edgecoil_pcb.route).

    python3 route.py <variant>             replay <variant>/routing.json if there is one, else autoroute
    python3 route.py --reroute <variant>   autoroute with Freerouting even so
    python3 route.py --freeze <variant>    record the board's current copper in <variant>/routing.json

(FREEROUTING=path/to/freerouting.jar, JAVA=path/to/java; ROUTE_DEBUG=1 prints why each autoroute
attempt failed.) Freerouting lays the board out afresh on every run, so once a routing has passed
review it is frozen: later builds replay it, and a fix is a small edit to routing.json rather than
a new layout.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
from edgecoil_pcb.route import cli  # noqa: E402

from gen import CFG  # noqa: E402

if __name__ == "__main__":
    cli(CFG, sys.argv[1:])
