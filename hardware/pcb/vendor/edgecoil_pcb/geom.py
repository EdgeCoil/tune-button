# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
import pcbnew


def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
