# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
"""KiCad symbol libraries: pull one symbol (resolving `extends`) and its pin positions."""
import os
import re


def block(text, start):
    """The balanced s-expression starting at text[start] == '('."""
    depth, i, instr = 0, start, False
    while True:
        ch = text[i]
        if instr:
            if ch == "\\":
                i += 1
            elif ch == '"':
                instr = False
        elif ch == '"':
            instr = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1


_libs = {}


def lib_symbol(lib_id, cfg):
    lib, name = lib_id.split(":")
    if lib not in _libs:
        d = cfg.lib_dir(lib) or cfg.symbol_dir
        _libs[lib] = open(os.path.join(d, lib + ".kicad_sym")).read()
    text = _libs[lib]
    m = re.search(r'\n\t\(symbol "%s"' % re.escape(name), text)
    if not m:
        raise SystemExit(f"symbol {lib_id} not found")
    blk = block(text, m.start() + 2)
    ext = re.search(r'\(extends "([^"]+)"\)', blk)
    if ext:
        parent = lib_symbol(f"{lib}:{ext.group(1)}", cfg)
        props = [block(blk, mm.start()) for mm in re.finditer(r"\(property ", blk)]
        body = re.sub(r'^\(symbol "[^"]+"', "", parent[0])
        body = re.sub(r"\n\t*\(property .*?\n\t\t\)", "", body, flags=re.S)  # drop parent's properties
        body = body.replace(f'"{ext.group(1)}_', f'"{name}_')
        head = f'(symbol "{lib_id}"'
        # Properties go after the pin_names/exclude flags; inserting them first is accepted too.
        return head + "\n" + "\n".join(props) + body, parent[1]
    pins = {}
    for pm in re.finditer(r"\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)", blk):
        pb = block(blk, pm.start())
        num = re.search(r'\(number "([^"]*)"', pb).group(1)
        unit = re.findall(r'\(symbol "%s_(\d+)_(\d+)"' % re.escape(name), blk[:pm.start()])
        if unit and unit[-1][1] == "2":
            continue  # De Morgan alternate body
        pname = re.search(r'\(name "([^"]*)"', pb).group(1)
        pins.setdefault(num, []).append((float(pm.group(1)), float(pm.group(2)), int(pm.group(3)), pname))
    out = blk.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
    return out, pins

