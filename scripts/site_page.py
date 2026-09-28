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

def render(design, numbers, layout, cocotb_runs, schematic, env):
    """
    The page, as a string. Every argument may be empty, and its section is
    then left out.

    numbers      -- (label, value) rows, as `report` prints them
    layout       -- the layout image's name next to the page, or None
    cocotb_runs  -- (title, seed, cases) per results file, cases as above
    schematic    -- the schematic's name next to the page, or None
    env          -- os.environ; on GitHub Actions it names the commit and run
    """
    esc = html.escape
    parts = []

    if numbers:
        parts.append("<h2>Signoff summary</h2><table>" + "".join(
            f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>"
            for label, value in numbers) + "</table>")

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
