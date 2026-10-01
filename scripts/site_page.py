"""
The HTML half of `site`: turning what a run left behind into one page.

Kept out of entrypoint.py because it is a different kind of code -- markup and
a stylesheet rather than driving an EDA tool. entrypoint.py's cmd_site finds
the files and copies them; this module only reads cocotb's results and writes
markup. Nothing here touches the filesystem except to parse the XML it is
handed.
"""
import html
from datetime import datetime, timezone
from xml.etree import ElementTree

CSS = """
:root { --bg: #f6f8fa; --card: #ffffff; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0;
        --accent: #0969da; --pass: #1a7f37; --fail: #cf222e; --skip: #9a6700;
        --pass-bg: #dafbe1; --fail-bg: #ffebe9; --skip-bg: #fff8c5; --bar: #0969da33; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #0d1117; --card: #151b23; --fg: #e6edf3; --muted: #9198a1; --line: #3d444d;
          --accent: #4493f8; --pass: #3fb950; --fail: #f85149; --skip: #d29922;
          --pass-bg: #2ea04326; --fail-bg: #f8514926; --skip-bg: #bb800926; --bar: #4493f840; }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 64px; }
body { background: var(--bg); color: var(--fg); margin: 0;
       font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
.wrap { max-width: 1040px; margin: 0 auto; padding: 0 16px; }
a { color: var(--accent); text-decoration: none; } a:hover { text-decoration: underline; }
code { font: 0.9em ui-monospace, SFMono-Regular, Menlo, monospace; }
header { padding: 40px 0 24px; }
.eyebrow { margin: 0; color: var(--muted); font-size: 14px; letter-spacing: .04em;
           text-transform: uppercase; font-weight: 600; }
h1 { margin: 4px 0 8px; font-size: 40px; line-height: 1.15; overflow-wrap: anywhere; }
.meta { margin: 0; color: var(--muted); font-size: 14px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; font-size: 14px;
        font-weight: 600; border-radius: 999px; border: 1px solid currentColor; }
.chip::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.chip.PASS { background: var(--pass-bg); } .chip.FAIL { background: var(--fail-bg); }
.chip.SKIP { background: var(--skip-bg); }
nav { position: sticky; top: 0; z-index: 1; background: var(--bg); border-bottom: 1px solid var(--line); }
nav .wrap { display: flex; gap: 4px; overflow-x: auto; padding-top: 8px; padding-bottom: 8px; }
nav a { flex: none; padding: 4px 10px; border-radius: 6px; color: var(--muted); font-size: 14px; }
nav a:hover { background: var(--card); color: var(--fg); text-decoration: none; }
main { padding: 24px 0 8px; }
section { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
          padding: 20px 24px; margin: 0 0 16px; }
h2 { margin: 0 0 12px; font-size: 20px; }
section > p, .note { color: var(--muted); font-size: 14px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 12px; }
.kpi { border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }
.kpi.wide { grid-column: 1 / -1; }
.kpi .label { color: var(--muted); font-size: 13px; text-transform: capitalize; }
.kpi .value { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums;
              overflow-wrap: anywhere; }
.kpi.wide .value { font-size: 15px; font-weight: 500; }
.kpi .detail { color: var(--muted); font-size: 13px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 15px; }
th, td { text-align: left; padding: 6px 12px 6px 0; border-bottom: 1px solid var(--line);
         overflow-wrap: break-word; }
tr:last-child > th, tr:last-child > td { border-bottom: 0; }
th { font-weight: 600; }
td.num, th.num { text-align: right; }
td.num, td.PASS, td.FAIL, td.SKIP { white-space: nowrap; }
td.PASS, td.FAIL, td.SKIP { font-weight: 600; }
.PASS { color: var(--pass); } .FAIL { color: var(--fail); } .SKIP { color: var(--skip); }
.share { position: relative; }
.share span { position: absolute; inset: 20% auto 20% 0; background: var(--bar); border-radius: 3px; z-index: -1; }
.share { z-index: 0; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.btn, .actions a[download] { display: inline-block; padding: 6px 14px; border: 1px solid var(--line); border-radius: 6px;
       background: var(--card); color: var(--fg); font-weight: 600; font-size: 14px; }
.btn:hover, .actions a[download]:hover { text-decoration: none; border-color: var(--accent); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.hint { color: var(--muted); font-size: 13px; }
details { border: 1px solid var(--line); border-radius: 8px; }
summary { cursor: pointer; padding: 8px 12px; font-weight: 600; }
details .scroll { border-top: 1px solid var(--line); padding: 12px; }
pre { margin: 0; font-size: 13px; line-height: 1.4; }
img { max-width: 100%; height: auto; background: #fff; }
.zoom { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; margin: 4px 0 0; }
.zoom-tools { display: flex; gap: 4px; padding: 6px; border-bottom: 1px solid var(--line);
              align-items: center; color: var(--muted); font-size: 13px; flex-wrap: wrap; }
.zoom-tools button { font: inherit; min-width: 32px; padding: 2px 8px; color: var(--fg); cursor: pointer;
                     background: var(--card); border: 1px solid var(--line); border-radius: 6px; }
.zoom-view { overflow: hidden; background: #fff; cursor: grab; }
.zoom-view img { display: block; border: 0; transform-origin: 0 0; user-select: none; }
footer { color: var(--muted); font-size: 14px; padding: 8px 0 40px; }
.lede { margin: 0 0 8px; font-size: 18px; max-width: 46em; }
header .actions { margin: 16px 0 0; }
#layout .zoom-view img { max-height: 480px; width: auto; }
details > .zoom { border: 0; border-top: 1px solid var(--line); border-radius: 0; margin: 0; }
@media (max-width: 600px) { h1 { font-size: 30px; } section { padding: 16px; }
  table.power td:nth-child(2), table.power th:nth-child(2),
  table.power td:nth-child(3), table.power th:nth-child(3) { display: none; } }
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

def zoomable(target, alt):
    """
    A diagram the reader can zoom and pan in place (ZOOM_JS), which still
    opens the file itself on a click -- where a block diagram's own links work.
    Without JavaScript it is the plain link it always was.
    """
    esc = html.escape
    return ('<div class="zoom"><div class="zoom-tools">'
            '<button type="button" data-zoom="in" aria-label="Zoom in">+</button>'
            '<button type="button" data-zoom="out" aria-label="Zoom out">&minus;</button>'
            '<button type="button" data-zoom="reset">reset</button>'
            '<span>Ctrl + wheel or pinch to zoom, drag to pan, click to open</span></div>'
            f'<div class="zoom-view"><a href="{esc(target)}"><img src="{esc(target)}" '
            f'alt="{esc(alt)}" draggable="false"></a></div></div>')

# Plain wheel scrolling is left to the page: a diagram that swallowed it would
# trap anyone scrolling past. Ctrl + wheel is also what a trackpad pinch sends.
ZOOM_JS = """
document.querySelectorAll('.zoom').forEach(function (z) {
  var view = z.querySelector('.zoom-view'), img = view.querySelector('img'),
      link = view.querySelector('a'), s = 1, x = 0, y = 0, drag = null, moved = false;
  function apply() {
    if (s <= 1) { s = 1; x = 0; y = 0; }
    img.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(' + s + ')';
    view.style.touchAction = s > 1 ? 'none' : '';
  }
  function zoomAt(f, cx, cy) {
    var n = Math.min(20, Math.max(1, s * f));
    x = cx - (cx - x) * n / s; y = cy - (cy - y) * n / s; s = n; apply();
  }
  function centre(f) { zoomAt(f, view.clientWidth / 2, view.clientHeight / 2); }
  view.addEventListener('wheel', function (e) {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    var r = view.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  view.addEventListener('pointerdown', function (e) {
    if (e.pointerType === 'touch' && s <= 1) return;  /* let the page scroll */
    drag = { x: e.clientX - x, y: e.clientY - y }; moved = false;
  });
  view.addEventListener('pointermove', function (e) {
    if (!drag) return;
    var nx = e.clientX - drag.x, ny = e.clientY - drag.y;
    if (Math.abs(nx - x) + Math.abs(ny - y) > 3) moved = true;
    x = nx; y = ny; if (s > 1) apply();
  });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (t) {
    view.addEventListener(t, function () { drag = null; });
  });
  link.addEventListener('click', function (e) { if (moved) e.preventDefault(); });
  z.querySelectorAll('[data-zoom]').forEach(function (b) {
    b.addEventListener('click', function () {
      var k = b.getAttribute('data-zoom');
      if (k === 'in') centre(1.5); else if (k === 'out') centre(1 / 1.5); else { s = 1; apply(); }
    });
  });
});
"""

# Tiny Tapeout's viewer fetches the GDS by URL, so the link can only be built
# where the page itself has one: on a published page, not one opened from disk.
# Until then the button stays hidden and a note says where it will work.
GDS_VIEWER = "https://gds-viewer.tinytapeout.com/"
GDS_VIEWER_JS = """
document.querySelectorAll('[data-viewer]').forEach(function (s) {
  if (!/^https?:$/.test(location.protocol)) return;
  var gds = new URL(s.getAttribute('data-gds'), location.href).href;
  s.querySelector('a').href = '""" + GDS_VIEWER + """?pdk=' +
    encodeURIComponent(s.getAttribute('data-viewer')) + '&model=' + encodeURIComponent(gds);
  s.hidden = false;
  var off = s.parentNode.querySelector('[data-viewer-off]');
  if (off) off.hidden = true;
});
"""

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

def kpi(label, value):
    """
    One summary number as a card: `report` writes "+4.70 ns  (0 violations)",
    and the part in brackets is the detail under the headline figure.
    """
    esc = html.escape
    # `report` writes um^2 for a terminal; on the page it is a real superscript.
    value = value.replace("um^2", "um\u00b2")
    main, _, detail = value.partition("  (")
    wide = " wide" if len(main) > 32 else ""
    detail = f'<div class="detail">{esc(detail.rstrip(")"))}</div>' if detail else ""
    return (f'<div class="kpi{wide}"><div class="label">{esc(label)}</div>'
            f'<div class="value">{esc(main)}</div>{detail}</div>')

def run_name(title):
    """"cocotb, RTL" -> "RTL", "cocotb, gate level" -> "gates": a column head."""
    return {"cocotb, RTL": "RTL", "cocotb, gate level": "gates"}.get(title, title)

def merged_tests(cocotb_runs):
    """
    One table for every run: a row per test, a column per run. The RTL and the
    gate-level runs execute the same tests, and side by side that reads as what
    it is -- the design still passing after synthesis -- instead of one table
    printed twice.
    """
    esc = html.escape
    names = []
    for _, _, run in cocotb_runs:
        names += [name for name, _, _ in run if name not in names]
    verdicts = [{name: verdict for name, verdict, _ in run} for _, _, run in cocotb_runs]
    sim = {}
    for _, _, run in cocotb_runs:
        for name, _, ns in run:
            sim.setdefault(name, ns)
    heads = [run_name(title) for title, _, _ in cocotb_runs]
    score = ", ".join(f"{sum(v == 'PASS' for v in vs.values())}/{len(vs)} on {h}"
                      for h, vs in zip(heads, verdicts))
    seeds = "".join(f"<p>Seed <code>{esc(seed)}</code> reruns the {esc(h)} run exactly.</p>"
                    for h, (_, seed, _) in zip(heads, cocotb_runs) if seed)
    def cell(verdict):
        return f'<td class="{verdict}">{verdict}</td>' if verdict else "<td>&mdash;</td>"
    return (f"<h2>Tests: {score}</h2><p>The same cocotb tests, run on the RTL and again "
            f"on the gates synthesis produced.</p>{seeds}"
            '<div class="scroll"><table><tr><th>test</th>'
            + "".join(f"<th>{esc(h)}</th>" for h in heads)
            + '<th class="num">sim time (ns)</th></tr>' + "".join(
                f"<tr><td><code>{esc(name)}</code></td>"
                + "".join(cell(vs.get(name)) for vs in verdicts)
                + f'<td class="num">{sim[name]:g}</td></tr>'
                for name in names) + "</table></div>")

def render(design, numbers, layout, cocotb_runs, schematic, env,
           signoff=(), timing=None, area=(), power=None, blocks=None, wave=None, gds=None,
           description=None):
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
    gds          -- (the GDS's name next to the page, PDK for the 3D viewer or
                    None when the viewer has no layers for it), or None
    description  -- one line saying what the design is, or None

    The page is laid out to be shared, as a portfolio piece: the layout first,
    then the numbers, then the evidence that it works, then the detail.
    """
    esc = html.escape
    parts = []  # (anchor, nav label, markup), in page order
    add = lambda anchor, label, markup: parts.append((anchor, label, markup))

    # The verdicts first: what someone landing on the page wants to know is
    # whether it works, before any number. Each chip only for what was run.
    chips = []
    cases = [verdict for _, _, run in cocotb_runs for _, verdict, _ in run]
    if cases:
        passed = cases.count("PASS")
        if len(cocotb_runs) > 1:
            # Per run, so "6/6 on RTL · 6/6 on gates" says the same tests
            # held after synthesis, which a single 12/12 hides.
            text = " · ".join(
                f"{sum(v == 'PASS' for _, v, _ in run)}/{len(run)} on {run_name(title)}"
                for title, _, run in cocotb_runs)
        else:
            text = f"{passed}/{len(cases)} tests passed"
        chips.append(("PASS" if passed == len(cases) else "FAIL", text))
    if signoff:
        errors = sum(count for _, count in signoff)
        chips.append(("FAIL", f"Signoff: {errors} errors") if errors
                     else ("PASS", "Signoff clean"))
    # Setup and hold both: a negative hold slack is a chip that fails on
    # silicon at any clock speed, so "Timing met" on setup alone would be a
    # wrong verdict, not a partial one.
    slacks = [dict(numbers).get(k) for k in ("setup slack", "hold slack")]
    slacks = [s for s in slacks if s]
    if slacks:
        chips.append(("FAIL", "Timing missed") if any(s.startswith("-") for s in slacks)
                     else ("PASS", "Timing met"))

    if numbers:
        add("summary", "Summary", '<h2>Summary</h2><div class="kpis">'
            + "".join(kpi(label, value) for label, value in numbers) + "</div>")

    if len(cocotb_runs) > 1:
        add("tests", "Tests", merged_tests(cocotb_runs))
    for index, (title, seed, run) in enumerate(cocotb_runs if len(cocotb_runs) == 1 else ()):
        passed = sum(verdict == "PASS" for _, verdict, _ in run)
        # The seed is what turns a failure on this page into one you can rerun.
        replay = f"<p>Seed <code>{esc(seed)}</code> reruns exactly these tests.</p>" if seed else ""
        add(f"tests-{index}", title.replace("cocotb, ", "Tests, "),
            f"<h2>{esc(title)}: {passed}/{len(run)} passed</h2>{replay}"
            '<div class="scroll"><table><tr><th>test</th><th>result</th>'
            '<th class="num">sim time (ns)</th></tr>' + "".join(
                f'<tr><td><code>{esc(name)}</code></td><td class="{verdict}">{verdict}</td>'
                f'<td class="num">{sim_ns:g}</td></tr>'
                for name, verdict, sim_ns in run) + "</table></div>")

    if signoff:
        add("signoff", "Signoff",
            "<h2>Signoff checks</h2><p>The checks a layout has to pass before it can be "
            'manufactured.</p><div class="scroll"><table><tr><th>check</th><th class="num">errors</th><th>result</th></tr>'
            + "".join(
                f'<tr><td>{esc(check)}</td><td class="num">{count}</td>'
                f'<td class="{"FAIL" if count else "PASS"}">{"FAIL" if count else "PASS"}</td></tr>'
                for check, count in signoff) + "</table></div>")

    if layout:
        add("layout", "Layout", "<h2>Layout</h2>" + zoomable(layout, f"Layout of {design}"))

    if wave:
        image, vcd = wave
        add("waveform", "Waveform",
            f"<h2>Waveform</h2><p>From <code>{esc(vcd)}</code>, the signals "
            "<code>WAVE_SIGNALS</code> names.</p>" + zoomable(image, f"Waveform of {design}"))

    if timing:
        corner, path = timing
        # The whole path is long; its last line is the one that answers.
        verdict = path.strip().splitlines()[-1].split()
        headline = " ".join(verdict[-2:]) if len(verdict) >= 3 else "the path"
        slack = f"{float(verdict[0]):+.3f} ns, " if len(verdict) >= 3 else ""
        add("timing", "Timing",
            f"<h2>Worst setup path</h2><p>Corner <code>{esc(corner)}</code>, the one with "
            "the least setup slack. Printed as OpenSTA reports it.</p>"
            f"<details><summary>{esc(slack + headline)}: show the full path</summary>"
            f'<div class="scroll"><pre>{esc(path)}</pre></div></details>')

    if area:
        largest = max(value for _, value in area) or 1
        add("area", "Area", '<h2>Area</h2><div class="scroll"><table>' + "".join(
            f'<tr><th>{esc(label)}</th><td class="num share">'
            f'<span style="width:{value / largest:.0%}"></span>{value:,.1f} um&sup2;</td></tr>'
            for label, value in area) + "</table></div>")

    if power:
        corner, rows = power
        total = next((r[4] for r in rows if r[0] == "Total"), 0) or 1
        uw = lambda w: f"{w * 1e6:.4g}"
        add("power", "Power",
            f"<h2>Power</h2><p>Corner <code>{esc(corner)}</code>, in &micro;W. Dynamic is internal "
            "plus switching; static is leakage. Switching activity is OpenSTA's default, "
            "not taken from simulation, so this is an estimate of where power goes, "
            "not a measurement of a workload.</p>"
            '<div class="scroll"><table class="power"><tr><th>group</th><th class="num">internal</th>'
            '<th class="num">switching</th><th class="num">leakage</th>'
            '<th class="num">total</th><th class="num">share</th></tr>' + "".join(
                f'<tr><td>{esc(group)}</td><td class="num">{uw(i)}</td><td class="num">{uw(sw)}</td>'
                f'<td class="num">{uw(lk)}</td><td class="num">{uw(t)}</td>'
                f'<td class="num share"><span style="width:{t / total:.0%}"></span>{t / total:.1%}</td></tr>'
                for group, i, sw, lk, t in rows) + "</table></div>")

    if blocks:
        add("blocks", "Blocks",
            "<h2>Block diagram</h2><p>The top module as its submodules and the "
            "nets between them. Wiring that passes through the top's own gates "
            "meets them at the dashed box. Open it and click a block to go one "
            "level down: to that module's own block diagram, or to its schematic "
            "when it has no submodules.</p>" + zoomable(blocks, f"Block diagram of {design}"))

    if schematic:
        # Collapsed: past a few hundred cells it is a texture, not a picture,
        # and the block diagram above says more. One click away for a small one.
        add("schematic", "Schematic",
            "<details><summary>Schematic (RTL)</summary>"
            + zoomable(schematic, f"Schematic of {design}") + "</details>")

    # Only on GitHub Actions, where these say which commit the page shows.
    # When the page was built, always: a published page stays up until the
    # next one replaces it, so a reader needs to know how old it is.
    # SOURCE_DATE_EPOCH, when set, pins it (reproducible builds, tests).
    epoch = env.get("SOURCE_DATE_EPOCH")
    built = (datetime.fromtimestamp(int(epoch), timezone.utc) if epoch
             else datetime.now(timezone.utc))
    meta = [f"Built {built:%Y-%m-%d %H:%M} UTC"]
    server, repo = env.get("GITHUB_SERVER_URL"), env.get("GITHUB_REPOSITORY")
    sha, run = env.get("GITHUB_SHA"), env.get("GITHUB_RUN_ID")
    if server and repo and sha:
        meta.append(f'<a href="{esc(server)}/{esc(repo)}">{esc(repo)}</a>')
        meta.append(f'commit <a href="{esc(server)}/{esc(repo)}/commit/{esc(sha)}">'
                    f"<code>{esc(sha[:7])}</code></a>")
        if run:
            meta.append(f'<a href="{esc(server)}/{esc(repo)}/actions/runs/{esc(run)}">CI run</a>')
    source = f'<p class="meta">{" &middot; ".join(meta)}</p>'

    # What a visitor does with a chip: turn it around in 3D, take the GDS,
    # read the code. Each button only when there is something behind it.
    actions = []
    if gds:
        name, pdk = gds
        if pdk:
            actions.append(f'<span data-viewer="{esc(pdk)}" data-gds="{esc(name)}" hidden>'
                           '<a class="btn primary" target="_blank" rel="noopener">'
                           'Open in 3D</a></span>')
        actions.append(f'<a class="btn" href="{esc(name)}" download>Download GDS</a>')
    if server and repo:
        actions.append(f'<a class="btn" href="{esc(server)}/{esc(repo)}">View source</a>')
    if gds and gds[1]:
        actions.append('<span class="hint" data-viewer-off>The 3D view, in Tiny Tapeout\'s '
                       'viewer, opens from the published page.</span>')
    actions = f'<p class="actions">{"".join(actions)}</p>' if actions else ""

    # Link previews (chat apps, LinkedIn) need an absolute image URL; it is
    # only known on Actions, from where GitHub Pages serves a repository.
    summary = description or f"Verification and signoff results for {design}."
    og = (f'<meta property="og:title" content="{esc(design)}">'
          f'<meta property="og:description" content="{esc(summary)}">'
          '<meta property="og:type" content="website">')
    if layout and repo and "/" in repo:
        owner, name = repo.split("/", 1)
        og += (f'<meta property="og:image" content="https://{esc(owner.lower())}.github.io/'
               f'{esc(name)}/{esc(layout)}"><meta name="twitter:card" content="summary_large_image">')

    order = ["layout", "summary", "tests", "blocks", "waveform", "signoff",
             "timing", "area", "power", "schematic"]
    parts.sort(key=lambda p: order.index(p[0].split("-")[0]) if p[0].split("-")[0] in order
               else len(order))

    body = "".join(markup for _, _, markup in parts)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="description" content="{esc(summary)}">{og}'
        f"<title>{esc(design)} · chip design</title><style>{CSS}</style></head><body>"
        f'<header><div class="wrap"><p class="eyebrow">Chip design · open-source flow</p>'
        f"<h1>{esc(design)}</h1>"
        + (f'<p class="lede">{esc(description)}</p>' if description else "")
        + f"{source}"
        + ('<div class="chips">' + "".join(
            f'<span class="chip {state}">{esc(text)}</span>' for state, text in chips)
           + "</div>" if chips else "")
        + actions
        + "</div></header>"
        + ('<nav aria-label="Sections"><div class="wrap">' + "".join(
            f'<a href="#{anchor}">{esc(label)}</a>' for anchor, label, _ in parts)
           + "</div></nav>" if len(parts) > 1 else "")
        + '<main class="wrap">'
        + "".join(f'<section id="{anchor}">{markup}</section>' for anchor, _, markup in parts)
        + "</main>"
        + '<footer class="wrap"><p>'
        + (f'Source: <a href="{esc(server)}/{esc(repo)}">{esc(repo)}</a>. ' if server and repo else "")
        + 'Built with <a href="https://github.com/anlit75/ChipForAll">'
          "ChipForAll</a>, on open-source EDA tools. Generated by c4o-core "
          "<code>site</code>.</p></footer>"
        + (f"<script>{ZOOM_JS}</script>" if 'class="zoom"' in body else "")
        + (f"<script>{GDS_VIEWER_JS}</script>" if "data-viewer=" in actions else "")
        + "</body></html>\n"
    )
