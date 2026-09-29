"""
Pictures the page draws itself: a block diagram from yosys's JSON of the top
module, and a waveform from a VCD. Pure functions over text and dicts; the
callers in entrypoint.py do the files and run `dot`.
"""
import html
import re

def module_label(cell_type):
    """
    The source name of a module. A parameterised instance has a type like
    $paramod\\io_generic_fifo\\DATA_WIDTH=... or $paramod$<hash>\\io_generic_fifo,
    which is noise in a picture.
    """
    if cell_type.startswith("$paramod"):
        parts = [p for p in cell_type.split("\\") if p]
        named = [p for p in parts[1:] if "=" not in p]
        return named[0] if named else cell_type
    return cell_type.lstrip("\\")

def diagram_plan(netlist, top):
    """
    {module: file stem} for the top and every module under it. A module with
    submodules gets a block diagram under that stem, one without gets its
    schematic, and every block links to its module's file -- so a design of
    any depth is read one level at a time instead of as one picture.

    Stems are the source names, numbered when two parameterisations share
    one: io_generic_fifo, io_generic_fifo_2.
    """
    modules = netlist["modules"]
    reachable, todo = [], [top]
    while todo:
        name = todo.pop(0)
        if name in reachable or name not in modules:
            continue
        reachable.append(name)
        todo += [c["type"] for c in modules[name].get("cells", {}).values()
                 if c["type"] in modules]
    plan, taken = {top: "top"}, {"top"}
    for name in sorted(reachable):
        if name == top:
            continue
        stem = re.sub(r"[^A-Za-z0-9_]", "_", module_label(name))
        unique, n = stem, 2
        while unique in taken:
            unique, n = f"{stem}_{n}", n + 1
        taken.add(unique)
        plan[name] = unique
    return plan

def has_submodules(netlist, module):
    modules = netlist["modules"]
    return any(c["type"] in modules for c in modules[module].get("cells", {}).values())

def block_diagram_dot(netlist, top, links=None, parent=None):
    """
    Graphviz source for a module drawn as its submodule instances, one box
    for its own logic, and its ports -- or None when it instantiates no module
    of the design, which leaves nothing to draw that the schematic does not
    already show. `links` maps a module name to the file its block opens;
    `parent` is (label, file) for the way back up.

    An edge joins two things that share a net. Wiring that goes through the
    top's own gates meets them at the "logic" box, so nothing reads as
    unconnected merely because a mux sits between two blocks.
    """
    modules = netlist["modules"]
    mod = modules[top]
    cells = mod.get("cells", {})
    blocks = {name: c for name, c in cells.items() if c["type"] in modules}
    if not blocks:
        return None

    # Every net bit, and who drives and reads it.
    drivers, readers = {}, {}
    def attach(node, bits, direction):
        for bit in bits:
            if isinstance(bit, int):
                (drivers if direction == "output" else readers).setdefault(bit, set()).add(node)
                if direction == "inout":
                    drivers.setdefault(bit, set()).add(node)

    for port, info in mod.get("ports", {}).items():
        # Seen from inside the module an input port drives its net.
        flipped = {"input": "output", "output": "input"}.get(info["direction"], "inout")
        attach(f"port:{port}", info["bits"], flipped)
    glue = "logic"
    for name, cell in cells.items():
        node = f"block:{name}" if name in blocks else glue
        directions = cell.get("port_directions", {})
        for port, bits in cell.get("connections", {}).items():
            attach(node, bits, directions.get(port, "inout"))

    names = {}
    for net, info in mod.get("netnames", {}).items():
        if not info.get("hide_name"):
            for bit in info["bits"]:
                if isinstance(bit, int):
                    names.setdefault(bit, net)

    edges = {}
    for bit, srcs in drivers.items():
        for src in srcs:
            for dst in readers.get(bit, ()):
                if src != dst:
                    edges.setdefault((src, dst), []).append(bit)

    def label(bits):
        nets = sorted({names[b] for b in bits if b in names})
        text = ", ".join(nets[:2]) + (f" +{len(nets) - 2}" if len(nets) > 2 else "")
        return text or f"{len(bits)} bit{'s' if len(bits) > 1 else ''}"

    # An input that reaches every block -- a clock, a reset -- would be an
    # edge into each of them and say nothing the caption cannot.
    everywhere = {f"block:{name}" for name in blocks}
    fanout = {}
    for (src, dst) in edges:
        fanout.setdefault(src, set()).add(dst)
    shared = sorted(src for src, dsts in fanout.items()
                    if src.startswith("port:") and everywhere <= dsts)
    edges = {pair: bits for pair, bits in edges.items() if pair[0] not in shared}

    q = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    # concentrate merges parallel edges. Not splines=ortho: Graphviz cannot
    # attach labels to orthogonal edges, and a net name floating beside the
    # wrong line is worse than a curve.
    lines = [f"digraph {q(top)} {{", "rankdir=LR; concentrate=true;",
             'node [fontname="Helvetica", fontsize=11]; edge [fontname="Helvetica", fontsize=9];']
    used = {n for pair in edges for n in pair}
    for port, info in mod.get("ports", {}).items():
        node = f"port:{port}"
        if node in used:
            lines.append(f"{q(node)} [label={q(port)}, shape=plaintext];")
    links = links or {}
    for name, cell in blocks.items():
        target = links.get(cell["type"])
        url = f", URL={q(target)}, tooltip={q('open ' + module_label(cell['type']))}" if target else ""
        lines.append(f"{q('block:' + name)} [label={q(name + chr(10) + module_label(cell['type']))}, "
                     f"shape=box, style=\"rounded,filled\", fillcolor=\"#dbe9f6\"{url}];")
    if parent:
        up_label, up_file = parent
        lines.append(f"{q('parent')} [label={q('up to ' + up_label)}, shape=note, URL={q(up_file)}];")
    if glue in used:
        lines.append(f"{q(glue)} [label={q('logic in ' + top)}, shape=box, style=dashed];")
    for (src, dst), bits in sorted(edges.items()):
        lines.append(f"{q(src)} -> {q(dst)} [label={q(label(bits))}];")
    if shared:
        caption = ", ".join(p.split(":", 1)[1] for p in shared) + " reach every block"
        lines.append(f"label={q(caption)}; labelloc=b; fontname=\"Helvetica\"; fontsize=10;")
    lines.append("}")
    return "\n".join(lines) + "\n"

def read_vcd(text):
    """
    The timescale in picoseconds per tick, and {dotted.name: (width, [(time,
    value)])} for every variable a VCD declares. Values are strings as the
    file writes them: '0', '1', 'x', 'z', or a vector's binary digits.
    """
    scale = {"s": 10**12, "ms": 10**9, "us": 10**6, "ns": 10**3, "ps": 1, "fs": 10**-3}
    header, _, body = text.partition("$enddefinitions")
    ps_per_tick = 1
    m = re.search(r"\$timescale\s+(\d+)\s*([munpf]?s)\s+\$end", header)
    if m:
        ps_per_tick = int(m.group(1)) * scale[m.group(2)]

    scopes, by_id, signals = [], {}, {}
    tokens = header.split()
    i = 0
    while i < len(tokens):
        if tokens[i] == "$scope":
            scopes.append(tokens[i + 2])
            i += 3
        elif tokens[i] == "$upscope":
            scopes.pop()
            i += 1
        elif tokens[i] == "$var":
            width, ident, name = int(tokens[i + 2]), tokens[i + 3], tokens[i + 4]
            changes = by_id.setdefault(ident, [])
            signals[".".join(scopes + [name])] = (width, changes)
            i += 5
        else:
            i += 1

    time = 0
    for token in body.split("\n"):
        token = token.strip()
        if not token or token.startswith("$"):
            continue
        if token[0] == "#":
            time = int(token[1:])
        elif token[0] in "bB":
            value, _, ident = token[1:].partition(" ")
            if ident in by_id:
                by_id[ident].append((time, value))
        elif token[0] in "01xXzZ" and token[1:] in by_id:
            by_id[token[1:]].append((time, token[0].lower()))
    return ps_per_tick, signals

def waveform_svg(text, wanted):
    """
    An SVG of the named signals across the whole VCD. Raises KeyError naming
    any signal the VCD does not declare, because a picture quietly missing the
    one trace somebody asked for is worse than no picture.
    """
    ps_per_tick, signals = read_vcd(text)
    missing = [name for name in wanted if name not in signals]
    if missing:
        raise KeyError(", ".join(missing))

    end = max((c[-1][0] for name in wanted for c in [signals[name][1]] if c), default=0) or 1
    label_w, plot_w, row_h, pad = 170, 760, 30, 8
    height = pad + row_h * len(wanted) + 28
    x = lambda t: label_w + plot_w * t / end
    esc = html.escape
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{label_w + plot_w + 20}" '
           f'height="{height}" font-family="Helvetica, sans-serif" font-size="11">',
           f'<rect width="100%" height="100%" fill="#fff"/>']

    for row, name in enumerate(wanted):
        width, changes = signals[name]
        top = pad + row * row_h
        hi, lo, mid = top + 4, top + row_h - 8, top + (row_h - 4) / 2
        out.append(f'<text x="4" y="{mid + 4}" fill="#1f2328">{esc(name.split(".")[-1])}</text>')
        # A testbench rewriting the value a signal already holds is recorded
        # as a change; drawn, it is a boundary where nothing happened.
        kept = [c for k, c in enumerate(changes) if k == 0 or c[1] != changes[k - 1][1]]
        spans = [(t, kept[k + 1][0] if k + 1 < len(kept) else end, v)
                 for k, (t, v) in enumerate(kept)]
        for start, stop, value in spans:
            x0, x1 = x(start), x(stop)
            unknown = any(ch in "xz" for ch in value)
            if width == 1 and not unknown:
                y = hi if value == "1" else lo
                out.append(f'<line x1="{x0:.1f}" y1="{y}" x2="{x1:.1f}" y2="{y}" stroke="#0969da" stroke-width="1.5"/>')
                out.append(f'<line x1="{x0:.1f}" y1="{hi}" x2="{x0:.1f}" y2="{lo}" stroke="#0969da" stroke-width="1"/>')
            else:
                fill = "#eaeef2" if unknown else "#ddf4ff"
                out.append(f'<rect x="{x0:.1f}" y="{hi}" width="{max(x1 - x0, 0.5):.1f}" height="{lo - hi}" '
                           f'fill="{fill}" stroke="#57606a" stroke-width="0.5"/>')
                text_value = "x" if unknown else format(int(value, 2), "X")
                if (x1 - x0) > 7 * len(text_value) + 4:
                    out.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{mid + 4}" text-anchor="middle" '
                               f'fill="#1f2328">{text_value}</text>')

    axis = pad + row_h * len(wanted) + 6
    out.append(f'<line x1="{label_w}" y1="{axis}" x2="{label_w + plot_w}" y2="{axis}" stroke="#57606a"/>')
    for k in range(6):
        t = end * k / 5
        out.append(f'<text x="{x(t):.1f}" y="{axis + 16}" text-anchor="middle" fill="#57606a">'
                   f'{t * ps_per_tick / 1000:g} ns</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
