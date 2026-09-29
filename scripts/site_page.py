"""
The HTML half of `site`: turning what a run left behind into one page.

Kept out of entrypoint.py because it is a different kind of code -- markup and
a stylesheet rather than driving an EDA tool. entrypoint.py's cmd_site finds
the files and copies them; this module only reads cocotb's results and writes
markup. Nothing here touches the filesystem except to parse the XML it is
handed.
"""
import html
from xml.etree import ElementTree

CSS = """
:root { --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0;
        --pass: #1a7f37; --fail: #cf222e; --skip: #9a6700; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #3d444d;
          --pass: #3fb950; --fail: #f85149; --skip: #d29922; }
}
body { background: var(--bg); color: var(--fg); margin: 0 auto; max-width: 960px;
       padding: 16px; font: 16px/1.5 system-ui, sans-serif; }
header p, footer { color: var(--muted); }
a { color: inherit; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 4px 12px 4px 0; border-bottom: 1px solid var(--line);
         overflow-wrap: anywhere; }
td.num { text-align: right; }
.PASS { color: var(--pass); } .FAIL { color: var(--fail); } .SKIP { color: var(--skip); }
pre { margin: 0; font-size: 13px; line-height: 1.4; }
img { max-width: 100%; height: auto; border: 1px solid var(--line); background: #fff; }
.scroll { overflow-x: auto; }
"""

def cocotb_cases(path):
    """
    The seed and (name, verdict, simulated ns) per testcase of a results file.

    Simulated time rather than the `time` attribute: that one is wall-clock
    seconds, which rounds to 0.00 for every test of a small design.

    Raises ElementTree.ParseError on a file that is not XML; the caller decides
    what that means.
    """
    root = ElementTree.parse(path).getroot()
    seed = next((prop.get("value") for prop in root.iter("property")
                 if prop.get("name") == "random_seed"), None)
    cases = []
    for case in root.iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            verdict = "FAIL"
        elif case.find("skipped") is not None:
            verdict = "SKIP"
        else:
            verdict = "PASS"
        cases.append((case.get("name", "?"), verdict, float(case.get("sim_time_ns", 0))))
    return seed, cases

def power_groups(text):
    """
    The group rows of an OpenSTA `report_power`, as
    (group, internal, switching, leakage, total) in watts, Total row last.
    """
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[0] in (
            "Sequential", "Combinational", "Clock", "Macro", "Pad", "Total"
        ):
            try:
                rows.append((fields[0], *(float(v) for v in fields[1:5])))
            except ValueError:
                continue
    return rows

def first_path(text):
    """
    The first path of an OpenSTA `report_checks`, from its Startpoint line to
    its slack line inclusive, or None. report_checks sorts by slack, so the
    first path is the worst one in that file.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Startpoint:")), None)
    if start is None:
        return None
    for end in range(start, len(lines)):
        if lines[end].rstrip().endswith(("slack (MET)", "slack (VIOLATED)")):
            return "\n".join(lines[start:end + 1])
    return None

def render(design, numbers, layout, cocotb_runs, schematic, env,
           signoff=(), timing=None, area=(), power=None, blocks=None, wave=None):
    """
    The page, as a string. Every argument may be empty, and its section is
    then left out.

    numbers      -- (label, value) rows, as `report` prints them
    layout       -- the layout image's name next to the page, or None
    cocotb_runs  -- (title, seed, cases) per results file, cases as above
    schematic    -- the schematic's name next to the page, or None
    env          -- os.environ; on GitHub Actions it names the commit and run
    signoff      -- (check, error count) per signoff check the run reported
    timing       -- (corner, path text) for the worst setup path, or None
    area         -- (label, um^2) rows
    power        -- (corner, power_groups rows), or None
    blocks       -- the block diagram's name next to the page, or None
    wave         -- (waveform's name next to the page, VCD it came from), or None
    """
    esc = html.escape
    parts = []

    if numbers:
        parts.append("<h2>Summary</h2><table>" + "".join(
            f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>"
            for label, value in numbers) + "</table>")

    if signoff:
        parts.append(
            "<h2>Signoff checks</h2><table><tr><th>check</th><th>errors</th><th>result</th></tr>"
            + "".join(
                f'<tr><td>{esc(check)}</td><td class="num">{count}</td>'
                f'<td class="{"FAIL" if count else "PASS"}">{"FAIL" if count else "PASS"}</td></tr>'
                for check, count in signoff) + "</table>")

    if timing:
        corner, path = timing
        parts.append(
            f"<h2>Worst setup path</h2><p>Corner <code>{esc(corner)}</code>, the one with "
            "the least setup slack. Printed as OpenSTA reports it.</p>"
            f'<div class="scroll"><pre>{esc(path)}</pre></div>')

    if area:
        parts.append("<h2>Area</h2><table>" + "".join(
            f'<tr><th>{esc(label)}</th><td class="num">{value:,.1f} um&sup2;</td></tr>'
            for label, value in area) + "</table>")

    if power:
        corner, rows = power
        total = next((r[4] for r in rows if r[0] == "Total"), 0) or 1
        uw = lambda w: f"{w * 1e6:.4g}"
        parts.append(
            f"<h2>Power</h2><p>Corner <code>{esc(corner)}</code>, in &micro;W. Dynamic is internal "
            "plus switching; static is leakage. Switching activity is OpenSTA's default, "
            "not taken from simulation, so this is an estimate of where power goes, "
            "not a measurement of a workload.</p>"
            "<table><tr><th>group</th><th>internal</th><th>switching</th><th>leakage</th>"
            "<th>total</th><th>share</th></tr>" + "".join(
                f'<tr><td>{esc(group)}</td><td class="num">{uw(i)}</td><td class="num">{uw(sw)}</td>'
                f'<td class="num">{uw(lk)}</td><td class="num">{uw(t)}</td>'
                f'<td class="num">{t / total:.1%}</td></tr>'
                for group, i, sw, lk, t in rows) + "</table>")

    if layout:
        parts.append(f'<h2>Layout</h2><a href="{esc(layout)}">'
                     f'<img src="{esc(layout)}" alt="Layout of {esc(design)}"></a>')

    for title, seed, cases in cocotb_runs:
        passed = sum(verdict == "PASS" for _, verdict, _ in cases)
        # The seed is what turns a failure on this page into one you can rerun.
        replay = f"<p>Seed <code>{esc(seed)}</code></p>" if seed else ""
        parts.append(
            f"<h2>{esc(title)}: {passed}/{len(cases)} passed</h2>{replay}"
            "<table><tr><th>test</th><th>result</th><th>sim time (ns)</th></tr>" + "".join(
                f'<tr><td>{esc(name)}</td><td class="{verdict}">{verdict}</td>'
                f'<td class="num">{sim_ns:g}</td></tr>'
                for name, verdict, sim_ns in cases) + "</table>")

    if wave:
        image, vcd = wave
        parts.append(f"<h2>Waveform</h2><p>From <code>{esc(vcd)}</code>, the signals "
                     "<code>WAVE_SIGNALS</code> names.</p>"
                     f'<div class="scroll"><a href="{esc(image)}"><img src="{esc(image)}" '
                     f'alt="Waveform of {esc(design)}"></a></div>')

    if blocks:
        parts.append("<h2>Block diagram</h2><p>The top module as its submodules and the "
                     "nets between them. Wiring that passes through the top's own gates "
                     "meets them at the dashed box.</p>"
                     f'<div class="scroll"><a href="{esc(blocks)}"><img src="{esc(blocks)}" '
                     f'alt="Block diagram of {esc(design)}"></a></div>')

    if schematic:
        parts.append(f'<h2>Schematic (RTL)</h2><div class="scroll"><a href="{esc(schematic)}">'
                     f'<img src="{esc(schematic)}" alt="Schematic of {esc(design)}"></a></div>')

    # Only on GitHub Actions, where these say which commit the page shows.
    source = ""
    server, repo = env.get("GITHUB_SERVER_URL"), env.get("GITHUB_REPOSITORY")
    sha, run = env.get("GITHUB_SHA"), env.get("GITHUB_RUN_ID")
    if server and repo and sha:
        source = (f'<p>Commit <a href="{esc(server)}/{esc(repo)}/commit/{esc(sha)}">'
                  f"<code>{esc(sha[:7])}</code></a>")
        if run:
            source += f' &middot; <a href="{esc(server)}/{esc(repo)}/actions/runs/{esc(run)}">CI run</a>'
        source += "</p>"

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(design)}</title><style>{CSS}</style></head><body>"
        f"<header><h1>{esc(design)}</h1>{source}</header>"
        + "".join(f"<section>{part}</section>" for part in parts)
        + "<footer><p>Generated by c4o-core <code>site</code>.</p></footer></body></html>\n"
    )
