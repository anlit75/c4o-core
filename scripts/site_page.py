"""
The HTML half of `site`: turning what a run left behind into one page.

Kept out of entrypoint.py because it is a different kind of code -- markup and
a stylesheet rather than driving an EDA tool. entrypoint.py's cmd_site finds
the files and copies them; this module only reads cocotb's results and writes
markup. Nothing here touches the filesystem except to parse the XML it is
handed.
"""
import html
import os
import re
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

CSS = """
:root { color-scheme: light dark; --bg: #f6f8fa; --card: #ffffff; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0;
        --accent: #0969da; --pass: #1a7f37; --fail: #cf222e; --skip: #9a6700;
        --pass-bg: #dafbe1; --fail-bg: #ffebe9; --skip-bg: #fff8c5; --accent2: #54aeff;
        --primary: #0969da; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #0d1117; --card: #151b23; --fg: #e6edf3; --muted: #9198a1; --line: #3d444d;
          --accent: #4493f8; --pass: #3fb950; --fail: #f85149; --skip: #d29922;
          --pass-bg: #2ea04326; --fail-bg: #f8514926; --skip-bg: #bb800926; --accent2: #79c0ff;
          /* #4493f8 behind white text is 3.1:1; this is 4.6:1. */
          --primary: #1f6feb; }
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
main.wrap { padding-top: 32px; padding-bottom: 8px; }
section { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
          padding: 24px 28px; margin: 0 0 20px; }
h2 { margin: 0 0 12px; font-size: 22px; letter-spacing: -.01em; }
section > p, .note { color: var(--muted); font-size: 14px; }
.kpis { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }
.kpi { grid-column: span 4; min-width: 0; border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.kpi.timing { grid-column: span 8; }
.kpi.wide { grid-column: 1 / -1; }
.kpi .stats { display: grid; gap: 4px 8px; }
.kpi.timing .stats { grid-template-columns: 1fr 1fr; }
.kpi.timing .stat + .stat { border-left: 1px solid var(--line); padding-left: 16px; }
.kpi .stat.good .value { color: var(--pass); } .kpi .stat.bad .value { color: var(--fail); }
.kpi.coverage .stats { grid-auto-flow: column; grid-auto-columns: auto; justify-content: space-between; }
.kpi.coverage .stat .value { font-size: 22px; }
.kpi .stat .value { white-space: nowrap; overflow-wrap: normal; }
.kpi .label { color: var(--muted); font-size: 12px; font-weight: 600; letter-spacing: .05em;
              text-transform: uppercase; }
.kpi .value { font-size: 26px; font-weight: 650; letter-spacing: -.01em; line-height: 1.25;
              font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.kpi.good .value { color: var(--pass); }
.kpi.wide .value { font-size: 15px; font-weight: 500; }
.kpi.bad .value { color: var(--fail); }
.kpi .detail { color: var(--muted); font-size: 13px; }
details { margin-top: 16px; }
summary { cursor: pointer; font-weight: 600; font-size: 16px; }
details > :not(summary) { margin-top: 12px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 15px; }
th, td { text-align: left; padding: 6px 12px 6px 0; border-bottom: 1px solid var(--line);
         overflow-wrap: break-word; }
tr:last-child > th, tr:last-child > td { border-bottom: 0; }
th { font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase;
     letter-spacing: .05em; }
td > th, tr > th[scope] { font-size: inherit; }
td.num, th.num { text-align: right; }
td.num, td.PASS, td.FAIL, td.SKIP { white-space: nowrap; }
td.FAIL { font-weight: 600; } td.PASS { font-weight: 500; }
td.PASS::before { content: "\u2713"; margin-right: 6px; }
td.FAIL::before { content: "\u2715"; margin-right: 6px; }
table.tests th:not(:first-child), table.tests td:not(:first-child) { width: 96px; }
tr.total td { font-weight: 650; border-top: 2px solid var(--fg); }
.PASS { color: var(--pass); } .FAIL { color: var(--fail); } .SKIP { color: var(--skip); }
td.src { overflow-wrap: anywhere; }
td.bar, th.bar { width: 120px; padding-right: 0; }
td.bar span { display: block; height: 8px; border-radius: 4px; background: var(--accent); }
td.bar .track { background: var(--line); }
.stack { display: flex; gap: 2px; height: 22px; border-radius: 6px; overflow: hidden;
         margin: 8px 0 6px; background: var(--card); }
.stack span { display: block; height: 100%; }
.seg-synthesis, .seg-ff { background: var(--accent); } .seg-logic { background: var(--accent2); }
.seg-flow { background: var(--muted); } .seg-other { background: var(--skip); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 0 0 16px; padding: 0; list-style: none;
          font-size: 14px; }
.legend li::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px;
                     margin-right: 6px; background: var(--c); }
.legend .of { color: var(--muted); }
h3 { margin: 16px 0 0; font-size: 16px; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.btn, .actions a[download] { display: inline-block; padding: 6px 14px; border: 1px solid var(--line); border-radius: 6px;
       background: var(--card); color: var(--fg); font-weight: 600; font-size: 14px; }
.btn:hover, .actions a[download]:hover { text-decoration: none; border-color: var(--accent); }
.btn.primary { background: var(--primary); border-color: var(--primary); color: #fff; }
.hint { color: var(--muted); font-size: 13px; }
img { max-width: 100%; height: auto; background: #fff; }
footer { color: var(--muted); font-size: 14px; }
footer.wrap { padding-top: 8px; padding-bottom: 48px; }
.lede { margin: 0 0 8px; font-size: 18px; max-width: 46em; }
.byline { margin: 0 0 12px; font-size: 16px; color: var(--muted); }
.byline a { color: var(--fg); font-weight: 600; }
header .actions { margin: 16px 0 0; }
h1 { font-size: clamp(32px, 5vw, 48px); letter-spacing: -.02em; }
.hero { display: grid; gap: 40px; align-items: center; }
header.has-art .hero { grid-template-columns: minmax(0, 1fr) minmax(280px, 400px); }
.hero-art { margin: 0; }
.hero-art a { display: block; background: #fff; padding: 12px; border-radius: 14px;
              border: 1px solid var(--line);
              box-shadow: 0 1px 2px rgb(0 0 0 / .06), 0 24px 48px -24px rgb(0 0 0 / .35); }
.hero-art img { display: block; width: 100%; aspect-ratio: 1; object-fit: contain; }
.hero-art figcaption { margin-top: 8px; font-size: 13px; color: var(--muted); text-align: center;
                       font-variant-numeric: tabular-nums; }
nav .wrap { mask-image: linear-gradient(90deg, #000 88%, transparent); }
@media (prefers-color-scheme: dark) {
  .hero-art a { filter: brightness(.88); }
}
@media (max-width: 760px) {
  header.has-art .hero { grid-template-columns: 1fr; gap: 20px; }
  .hero-art { max-width: 320px; margin-inline: auto; }
}
@media (max-width: 600px) { section { padding: 16px; }
  .kpis { grid-template-columns: 1fr 1fr; }
  .kpi { grid-column: span 1; padding: 12px; } .kpi .value { font-size: 20px; }
  .kpi.timing, .kpi.coverage, .kpi.wide { grid-column: span 2; }
  .kpi.coverage .stat .value { font-size: 20px; }
  .kpi.timing .stat + .stat { padding-left: 12px; }
  table.power td:nth-child(2), table.power th:nth-child(2),
  table.power td:nth-child(3), table.power th:nth-child(3),
  table.power td:nth-child(4), table.power th:nth-child(4) { display: none; }
  table.tests th:not(:first-child), table.tests td:not(:first-child) { width: 56px; }
  th { letter-spacing: .02em; font-size: 11px; } th, td { padding-right: 8px; }
  td.bar, th.bar { width: 60px; } }
@media (max-width: 360px) { .kpi.coverage .stat .value { font-size: 17px; } }
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

GDS_VIEWER = "https://gds-viewer.tinytapeout.com/"
GDS_VIEWER_JS = """
document.querySelectorAll('[data-viewer]').forEach(function (s) {
  if (!/^https?:$/.test(location.protocol)) return;
  var gds = new URL(s.getAttribute('data-gds'), location.href).href;
  s.querySelector('a').href = '""" + GDS_VIEWER + """?pdk=' +
    encodeURIComponent(s.getAttribute('data-viewer')) + '&model=' + encodeURIComponent(gds);
  s.hidden = false;
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

def kpi(label, value, state=None):
    """
    One summary number as a card: `report` writes "+4.70 ns  (0 violations)",
    and the part in brackets is the detail under the headline figure.
    state -- "good" or "bad" colours the figure; a slack is good when it is
             not negative, unless the caller says otherwise
    """
    esc = html.escape
    main, _, detail = value.partition("  (")
    detail = detail.rstrip(")")
    # `report` writes for a terminal: "69.485 x 80.205 um  (5573.04 um^2)".
    # The page rounds the sides, uses the real symbols and groups thousands.
    die = re.fullmatch(r"([\d.]+) x ([\d.]+) um", main)
    if die:
        main = f"{float(die[1]):,.1f} \u00d7 {float(die[2]):,.1f} \u00b5m"
        area = re.fullmatch(r"([\d.]+) um\^2", detail)
        detail = f"{float(area[1]):,.1f} \u00b5m\u00b2" if area else detail
    elif main.isdigit():
        main = f"{int(main):,}"
    detail = detail.replace("um^2", "\u00b5m\u00b2")
    if state is None and label.endswith("slack"):
        state = "bad" if main.startswith("-") else "good" if main.startswith("+") else None
    good = f" {state}" if state else ""
    wide = " wide" if len(main) > 32 else ""
    detail = f'<div class="detail">{esc(detail)}</div>' if detail else ""
    return (f'<div class="kpi{wide}{good}"><div class="label">{esc(label)}</div>'
            f'<div class="value">{esc(main)}</div>{detail}</div>')

def stack(parts, label):
    """One bar split into (css class, value) segments, with an accessible label."""
    total = sum(v for _, v in parts) or 1
    return (f'<div class="stack" role="img" aria-label="{html.escape(label)}">'
            + "".join(f'<span class="seg-{c}" style="width:{v / total:.2%}"></span>'
                      for c, v in parts if v > 0) + "</div>")

def legend(items):
    """(colour variable, markup) per entry under a stack."""
    return ('<ul class="legend">' + "".join(
        f'<li style="--c: var(--{c})">{text}</li>' for c, text in items) + "</ul>")

def makeup(area, cells, instances=None):
    """
    What the chip is made of, in area and in instances. Synthesis's flip-flops
    and logic are one stage; the instance total after routing contains
    them, so the part the flow added is the difference. One bar per measure,
    split by where each part came from -- not three bars side by side, which
    read as peers when one of them contains the other two.

    instances -- the count after synthesis, when stat.json gave one
    """
    esc = html.escape
    um2 = lambda v: f"{v:,.1f} &micro;m&sup2;"
    out = ""
    ff, logic, routed = area.get("flip_flops"), area.get("logic"), area.get("routed")
    if ff is not None and logic is not None:
        synth = ff + logic
        parts = [("ff", ff), ("logic", logic)]
        items = [("accent", f"flip-flops {um2(ff)}"), ("accent2", f"combinational logic {um2(logic)}")]
        if routed is not None and routed >= synth:
            parts.append(("flow", routed - synth))
            items.append(("muted", f"added or resized by place and route {um2(routed - synth)}"))
            out += (f"<p>Synthesis produced {um2(synth)} of instances. Place and route grew it "
                    f"by {(routed - synth) / synth:.0%} to {um2(routed)}.</p>")
        out += stack(parts, "Instance area by origin") + legend(items)
    elif routed is not None:
        out += f"<p>Instance area after routing: {um2(routed)}.</p>"
    if area.get("macros"):
        out += f"<p>Macros (memories, hard blocks): {um2(area['macros'])}.</p>"

    if cells:
        groups = [("synthesis", "accent", "from synthesis"), ("flow", "muted", "added by the flow"),
                  ("other", "skip", "other")]
        sums = {g: sum(n for _, n, k in cells if k == g) for g, _, _ in groups}
        total = sum(sums.values())
        head = (f"{instances:,} after synthesis, {total:,} after routing" if instances is not None
                else f"{total:,} after routing")
        out += (f"<h3>Instances: {head}</h3>"
                "<p>Placed instances, by LibreLane class. Fill is not counted.</p>"
                + stack([(g, sums[g]) for g, _, _ in groups], "Instances by origin")
                + legend([(colour, f"{name} {sums[g]:,} " + '<span class="of">('
                           + ", ".join(f"{n:,} {esc(cls)}" for cls, n, k in cells if k == g)
                           + ")</span>")
                          for g, colour, name in groups if sums[g]]))
    return out

def join_words(items):
    """['a', 'b', 'c'] -> 'a, b and c'."""
    return " and ".join(filter(None, [", ".join(items[:-1]), items[-1:] and items[-1]]))

def clock_mhz(period):
    """A clock period in ns as '100 MHz', or None when it is not a period."""
    return f"{1000 / period:.0f} MHz" if period and period > 0 else None

def milliwatts(watts):
    """Watts as '0.248 mW': the unit of every power headline."""
    return f"{watts * 1e3:.3f} mW"

def slack_text(ws):
    """A slack in ns, signed: '+4.70 ns'."""
    return f"{ws:+.2f} ns"

def violations_text(n):
    """'0 violations', '1 violation'; '?' when the run did not say."""
    return "? violations" if n is None else f"{n:,} violation{'' if n == 1 else 's'}"

def signoff_words(present):
    """
    (failed, ran) for the signoff checks of entrypoint.signoff_checks: `failed`
    names what failed, with counts, and is empty when nothing did; `ran` names
    the checks that reported. One reading for `report`, the chip and the card.
    """
    failed = ", ".join(f"{count} {label}" + (f" ({bad})" if bad else "")
                       for label, count, _, bad in present if count)
    ran = ", ".join(f"{tools} DRC" if label == "DRC" and " and " not in tools else label
                    for label, _, tools, _ in present)
    return failed, ran

def instance_counts(numbers):
    """(after synthesis, after routing) from the `instances` row, each None when absent."""
    text = dict(numbers).get("instances", "")
    synth = re.search(r"(\d+) after synthesis", text)
    routed = re.search(r"(\d+) after routing", text)
    return (int(synth[1]) if synth else None, int(routed[1]) if routed else None)

def drive_table(drive):
    """
    Instances by drive strength, after synthesis and after routing, as a table
    with a line reading what the flow changed. A stage with no source is None in
    every row and has no column.

    drive -- (strength, after synthesis, after routing) per strength, smallest first
    """
    if not drive:
        return ""
    stages = [(i, name) for i, name in ((1, "after synthesis"), (2, "after routing"))
              if drive[0][i] is not None]
    head = "".join(f'<th class="num">{name}</th>' for _, name in stages)
    body = "".join(
        f"<tr><td>X{n}</td>" + "".join(f'<td class="num">{row[i]:,}</td>' for i, _ in stages) + "</tr>"
        for row in drive for n in (row[0],))
    total = "".join(f'<td class="num">{sum(row[i] for row in drive):,}</td>' for i, _ in stages)
    out = ("<p>Well taps, decap, fill and antenna diodes have no drive strength and are not counted.</p>"
           f'<div class="scroll"><table class="drive"><tr><th>drive strength</th>{head}</tr>'
           f'{body}<tr class="total"><td>Total</td>{total}</tr></table></div>')
    if len(stages) == 2:
        changed = sorted(((r[2] - r[1], r[0]) for r in drive if r[2] != r[1]),
                         key=lambda c: (-abs(c[0]), c[1]))
        sentences = [f"{verb} {join_words([f'{abs(d):,} X{n}' for d, n in changed if (d > 0) == up])} instances."
                     for up, verb in ((True, "added"), (False, "removed"))
                     if any((d > 0) == up for d, _ in changed)]
        out += ("<p>Place and route " + " It ".join(sentences) + "</p>" if sentences
                else "<p>Place and route did not change the mix.</p>")
    return (f'<details class="drive-strength"><summary>Drive strength of the instances '
            f'({len(drive)} size{"" if len(drive) == 1 else "s"})</summary>'
            + out + "</details>")

def human_size(n):
    """Bytes as a short size: 6 B, 12.3 kB, 3.8 MB."""
    for unit in ("B", "kB", "MB"):
        if n < 1000 or unit == "MB":
            return f"{n:g} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000

def hero_art(layout, design, numbers, pdk):
    """
    The layout as the page's picture, framed like a print beside the title.
    The render is drawn on white, so it gets a white mount in either theme.
    It opens the full image on a click; at this size it is a texture to zoom
    into, which the full image does better.
    """
    if not layout:
        return ""
    esc = html.escape
    rows = dict(numbers)
    caption = []
    die = re.match(r"([\d.]+) x ([\d.]+) um", rows.get("die", ""))
    if die:
        caption.append(f"{float(die[1]):,.1f} \u00d7 {float(die[2]):,.1f} \u00b5m")
    # The picture is the routed layout, so the count is the routed one. Say
    # which count it is when that is the only one there is.
    synth, routed = instance_counts(numbers)
    if routed is not None:
        caption.append(f"{routed:,} instances after routing")
    elif synth is not None:
        caption.append(f"{synth:,} instances after synthesis")
    if pdk:
        caption.append(esc(pdk))
    caption = f"<figcaption>{' &middot; '.join(caption)}</figcaption>" if caption else ""
    return (f'<figure class="hero-art" id="layout"><a href="{esc(layout)}">'
            f'<img src="{esc(layout)}" alt="Layout of {esc(design)}"></a>{caption}</figure>')

CORNER = re.compile(r"(min|nom|max)_(ss|tt|ff|sf|fs)_(n?)(\d+)C_(\d+)v(\d+)$")
PROCESS = {"ss": "slow", "tt": "typical", "ff": "fast", "sf": "slow-fast", "fs": "fast-slow"}
RC = {"min": "minimum", "nom": "typical", "max": "maximum"}

def corner_words(corner):
    """'max_ss_100C_1v60' -> 'maximum wire RC, slow transistors, 100 °C, 1.60 V', or None.
    The name pads the temperature to three digits: 025C is 25 °C."""
    m = CORNER.match(corner)
    if not m:
        return None
    rc, process, minus, temp, volts, frac = m.groups()
    return (f"{RC[rc]} wire RC, {PROCESS[process]} transistors, {'-' if minus else ''}{int(temp)} &deg;C, "
            f"{volts}.{frac} V")

def run_name(title):
    """"cocotb, RTL" -> "RTL", "cocotb, gate level" -> "gates": a column head."""
    return {"cocotb, RTL": "RTL", "cocotb, gate level": "gates"}.get(title, title)

def test_name(name):
    """
    A test name for a table cell. It may wrap after an underscore and nowhere
    else: <wbr> is a break opportunity that adds no character, so a copied
    name is the exact name.
    """
    return html.escape(name).replace("_", "_<wbr>")

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
    heads = [run_name(title) for title, _, _ in cocotb_runs]
    score = ", ".join(f"{sum(v == 'PASS' for v in vs.values())}/{len(vs)} on {h}"
                      for h, vs in zip(heads, verdicts))
    seeds = " &middot; ".join(f"{esc(h)} <code>{esc(seed)}</code>"
                              for h, (_, seed, _) in zip(heads, cocotb_runs) if seed)
    seeds = f"<p>Seeds: {seeds}. Each seed reruns its run exactly.</p>" if seeds else ""
    def cell(verdict):
        return f'<td class="{verdict}">{verdict}</td>' if verdict else "<td>&mdash;</td>"
    return (f"<h2>Tests: {score}</h2><p>The same cocotb tests, on the RTL and on the "
            f"synthesized netlist with the PDK cell models.</p>{seeds}"
            '<div class="scroll"><table class="tests"><tr><th>test</th>'
            + "".join(f"<th>{esc(h)}</th>" for h in heads) + "</tr>" + "".join(
                f"<tr><td><code>{test_name(name)}</code></td>"
                + "".join(cell(vs.get(name)) for vs in verdicts) + "</tr>"
                for name in names) + "</table></div>")

def corner_volts(corner):
    """'nom_tt_025C_1v80' -> 1.8, or None. The supply the corner's liberty files are for."""
    m = CORNER.match(corner or "")
    return float(f"{m[5]}.{m[6]}") if m else None

def significant(value):
    """Two significant digits below 100, whole numbers above: 12, 0.67, 0.0029, 340."""
    return f"{value:.2g}" if abs(value) < 100 else f"{value:.0f}"

def timing_section(physical):
    """
    Whether timing is met, then the constraints that verdict depends on. Slack
    is the worst over every corner the flow analysed, and each constraint is
    labelled with where its value came from: config.yaml, or the flow's default.
    """
    checks = [(name, physical[name]) for name in ("setup", "hold") if name in physical]
    if not checks:
        return ""
    met = all(ws >= 0 for _, (ws, _) in checks)
    count = lambda n: "?" if n is None else f"{n:,}"
    def row(name, ws, vio):
        r2r = physical.get("r2r_" + name)
        return (f'<tr><td>{name}</td><td class="num {"PASS" if ws >= 0 else "FAIL"}">{slack_text(ws)}</td>'
                f'<td class="num">{count(vio)}</td>'
                f'<td class="num">{slack_text(r2r) if r2r is not None else "&mdash;"}</td></tr>')
    rows = "".join(row(name, ws, vio) for name, (ws, vio) in checks)
    out = (f'<h2>Timing</h2><p class="{"PASS" if met else "FAIL"}"><strong>'
           f'{"Timing is met: no setup or hold slack is negative." if met else "Timing is not met."}'
           "</strong></p>"
           '<p>Worst slack after routing, over every corner the flow analysed.</p>'
           '<div class="scroll"><table><tr><th>check</th><th class="num">worst slack</th>'
           '<th class="num">violations</th><th class="num">reg-to-reg</th></tr>'
           + rows + "</table></div>")

    constraints = physical.get("constraints") or {}
    if constraints:
        period = constraints.get("clock_period", (None,))[0]
        value = {
            "clock_period": lambda v: f"{v:g} ns" + (f" ({clock_mhz(v)})" if clock_mhz(v) else ""),
            "uncertainty": lambda v: f"{v:g} ns",
            "transition": lambda v: f"{v:g} ns",
            "derate": lambda v: f"{v:g}%",
            "io_delay": lambda v: f"{v:g}% of the clock period"
                                  + (f" ({v * period / 100:.3g} ns)" if period else ""),
        }
        source = {True: "set in config.yaml", False: "flow default"}
        label = {"clock_period": "clock period", "uncertainty": "clock uncertainty",
                 "transition": "clock transition", "derate": "timing derate",
                 "io_delay": "input and output delay"}
        shown = [n for n in value if n in constraints]
        out += (f'<details class="constraints"><summary>Constraints the run used ({len(shown)})</summary>'
                "<p>From the post-route timing step. "
                "The slack above holds only for these values.</p>"
                '<div class="scroll"><table><tr><th>constraint</th><th>value</th><th>source</th></tr>'
                + "".join(f"<tr><td>{label[name]}</td><td>{value[name](v)}</td>"
                          f"<td>{source[mine]}</td></tr>"
                          for name, (v, mine) in ((n, constraints[n]) for n in shown))
                + "</table></div></details>")
    return out

def signoff_section(signoff, physical):
    """
    The physical verification rows, then static IR drop when the run reported
    it. DRC is one row for the two tools; antenna says it is not part of them.
    """
    esc = html.escape
    rows = ""
    for check, count, tools, failed in signoff:
        result = "FAIL" if count else "PASS"
        note = {"DRC": tools and f"{tools}", "antenna": "checked by OpenROAD, not by DRC",
                "XOR": "Magic GDS against KLayout GDS"}.get(check, "")
        errors = f"{count} ({esc(failed)})" if failed else str(count)
        rows += (f'<tr><td>{esc(check)}'
                 + (f' <span class="hint">{esc(note)}</span>' if note else "")
                 + f'</td><td class="num">{errors}</td><td class="{result}">{result}</td></tr>')
    out = ("<h2>Signoff checks</h2><p>The DRC row adds the errors of both tools.</p>"
           '<div class="scroll"><table><tr><th>check</th><th class="num">errors</th><th>result</th></tr>'
           + rows + "</table></div>"
           "<p>Not analysed: electromigration, crosstalk and dynamic IR drop.</p>")
    ir = physical.get("ir_worst")
    if ir is not None:
        mv = f"{significant(ir * 1000)} mV"
        volts = corner_volts(physical.get("corner"))
        share = f", {significant(ir / volts * 100)}% of {volts:.2f} V" if volts else ""
        out += (f"<p>Static IR drop, worst: {mv}{share}.</p>"
                '<p class="hint">From OpenROAD (<code>ir__drop__worst</code>). LibreLane sets no limit for it, '
                "so it is not a pass or fail."
                + (f" The supply is the voltage of the default corner, <code>{esc(physical['corner'])}</code>."
                   if volts else "")
                + "</p>")
    return out

COVERAGE_LABELS = {"line": "Block", "branch": "Branch", "toggle": "Toggle", "user": "User cover"}

def coverage_percent(entry):
    """'79.2%', or None when the design has nothing of that kind."""
    return None if entry is None or entry.get("percent") is None else f"{entry['percent']:.1f}%"

def coverage_card(coverage):
    """
    The Summary card: one stat for each kind, with no total across them. Block,
    branch and toggle count different things, so one number for all of them
    would mean none of them.
    """
    types = coverage.get("types", {})
    stats = "".join(
        f'<div class="stat"><div class="value">{coverage_percent(types[name]) or "&mdash;"}</div>'
        f'<div class="detail">{COVERAGE_LABELS[name]}</div></div>'
        for name in COVERAGE_LABELS if name in types)
    return f'<div class="kpi coverage"><div class="label">code coverage</div><div class="stats">{stats}</div></div>'

def timing_card(physical):
    """
    The Summary card for timing: worst setup and hold slack side by side, each
    coloured by its sign. A slack the run did not report is left out, and with
    neither there is no card.
    """
    stats = ""
    for name in ("setup", "hold"):
        if name in physical:
            ws, vio = physical[name]
            text = slack_text(ws)
            state = "bad" if text.startswith("-") else "good"
            stats += (f'<div class="stat {state}"><div class="value">{html.escape(text)}</div>'
                      f'<div class="detail">{name} &middot; {html.escape(violations_text(vio))}</div></div>')
    return (f'<div class="kpi timing"><div class="label">timing, worst slack</div>'
            f'<div class="stats">{stats}</div></div>') if stats else ""

def coverage_section(coverage, cocotb_runs=(), regression=None):
    """
    What fraction of the RTL the cocotb tests ran, from build/coverage/summary.json:
    a row per kind and the same numbers per module.
    The run is Verilator's, a second one beside the Icarus run in Tests, so the
    section says it is not the verdict.
    """
    esc = html.escape
    types = coverage.get("types", {})
    rows = "".join(
        f"<tr><td>{COVERAGE_LABELS[name]}</td>"
        f'<td class="num">{entry["hit"]:,} / {entry["total"]:,}</td>'
        f'<td class="num">{coverage_percent(entry) or "&mdash;"}</td>'
        '<td class="bar"><span class="track"><span style="width:'
        f'{entry["percent"] or 0:.0f}%"></span></span></td></tr>'
        for name, entry in ((n, types[n]) for n in COVERAGE_LABELS if n in types))
    seed = coverage.get("seed")
    rtl_seed = next((sd for title, sd, _ in cocotb_runs if title == "cocotb, RTL"), None)
    if coverage.get("runs"):
        # Merged over a test list: the seed is the list's base seed, not a run's.
        base = (regression or {}).get("seed")
        if regression and str(base) == str(seed):
            # The Regression section shows the seed; naming it again says nothing.
            source = (f"<p>Code coverage of the RTL, from the {coverage['runs']} runs of Regression, "
                      "run again under Verilator and merged.</p>")
        else:
            match = " It is not the base seed of the Regression section." if regression else ""
            source = (f"<p>Code coverage of the RTL, from {coverage['runs']} regression runs under Verilator, "
                      f"merged. Base seed <code>{esc(str(seed))}</code>.{match}</p>")
    else:
        source = "<p>Code coverage of the RTL, from a second run of the cocotb tests under Verilator.</p>"
        if seed and seed == rtl_seed:
            source += f"<p>This run used seed <code>{esc(seed)}</code>, the seed of the RTL run in Tests.</p>"
        elif seed:
            source += (f"<p>This run used seed <code>{esc(seed)}</code>. "
                       "It is not the seed of the RTL run in Tests.</p>")
    out = ("<h2>Coverage</h2>" + source
           +
           '<div class="scroll"><table class="coverage"><tr><th>kind</th><th class="num">covered</th>'
           f'<th class="num">share</th><th class="bar"></th></tr>{rows}</table></div>')
    out += ('<p class="hint">Not measured: expression and FSM coverage. '
            "The Verilator in the image does not support them.</p>")

    modules = coverage.get("modules") or []
    if modules:
        shown = [n for n in COVERAGE_LABELS if n in types]
        cell = lambda t, n: f'<td class="num">{coverage_percent(t.get(n)) or "&mdash;"}</td>'
        out += (f'<details class="coverage-modules"><summary>Coverage by module ({len(modules)})</summary>'
                '<div class="scroll"><table><tr><th>module</th>'
                + "".join(f'<th class="num">{COVERAGE_LABELS[n].lower()}</th>' for n in shown) + "</tr>"
                + "".join(f"<tr><td class=\"src\"><code>{esc(m['name'])}</code></td>"
                          + "".join(cell(m["types"], n) for n in shown) + "</tr>" for m in modules)
                + "</table></div></details>")

    return out

def regression_section(regression):
    """
    The regress run of build/regress/summary.json: runs passed out of runs for
    each test, and for each failed seed the command that replays it.
    """
    esc = html.escape
    runs = regression.get("runs") or []
    counts = {}
    for run in runs:
        row = counts.setdefault(run["entry"], [0, 0])
        row[1] += 1
        row[0] += run["verdict"] == "pass"
    passed = sum(done for done, _ in counts.values())
    out = (f"<h2>Regression: {passed}/{len(runs)} runs passed</h2>"
           "<p>Each test in the list, run once per seed.</p>"
           f"<p>Base seed <code>{esc(str(regression.get('seed')))}</code>. "
           f"<code>make regress SEED={esc(str(regression.get('seed')))}</code> reruns the list with the same seeds.</p>"
           '<div class="scroll"><table><tr><th>test</th><th class="num">passed</th></tr>'
           + "".join(f'<tr><td><code>{test_name(entry)}</code></td>'
                     f'<td class="num {"PASS" if done == total else "FAIL"}">{done}/{total}</td></tr>'
                     for entry, (done, total) in counts.items())
           + "</table></div>")
    failed = [run for run in runs if run["verdict"] != "pass"]
    if failed:
        out += ("<p>Replay a failed run with its own seed:</p><ul>"
                + "".join(f'<li><code>make cocotb SEED={esc(str(run["seed"]))} TEST={esc(run["entry"])}</code></li>'
                          for run in failed) + "</ul>")
    return out

def summary_cards(numbers, physical, power, signoff, coverage=None):
    """
    The Summary section's cards: the numbers a visitor asks first, each built
    from the data its section below is built from, and left out when that
    data is missing. No card is a placeholder.
    """
    rows = dict(numbers)
    cards = []
    # Three to a row: what the chip is, then its clock and timing, then what
    # it was checked by and what it costs.
    if "die" in rows:
        cards.append(kpi("die", rows["die"]))
    if "utilization" in rows:
        # Of the core, not the die beside it.
        core = physical.get("core")
        cards.append(kpi("core utilization" if core else "utilization", rows["utilization"]
                         + (f"  (of a {core[0]:,.1f} \u00d7 {core[1]:,.1f} \u00b5m core)" if core else "")))
    synth, routed = instance_counts(numbers)
    if routed is not None:
        cards.append(kpi("instances", f"{routed:,}  (after routing"
                         + (f", {synth:,} after synthesis)" if synth is not None else ")")))
    elif synth is not None:
        cards.append(kpi("instances", f"{synth:,}  (after synthesis)"))
    period = (physical.get("constraints") or {}).get("clock_period", (None,))[0]
    if clock_mhz(period):
        cards.append(kpi("clock", f"{clock_mhz(period)}  ({period:g} ns period)"))
    cards.append(timing_card(physical))
    if coverage:
        cards.append(coverage_card(coverage))
    total = next((r[4] for r in power[1] if r[0] == "Total"), None) if power else None
    if total is not None:
        # The corner in words, as the Power section gives it.
        words = corner_words(power[0])
        cards.append(kpi("total power", f"{milliwatts(total)}  ("
                         + (html.unescape(words) if words else f"corner {power[0]}") + ")"))
    elif "power" in rows:
        cards.append(kpi("total power", rows["power"]))
    if signoff:
        failed, ran = signoff_words(signoff)
        cards.append(kpi("signoff", failed or f"clean  ({ran})", "bad" if failed else "good"))
    cards = [c for c in cards if c]
    return f'<h2>Summary</h2><div class="kpis">{"".join(cards)}</div>' if cards else ""

def render(design, numbers, layout, cocotb_runs, env,
           signoff=(), area=None, power=None, gds=None,
           description=None, cells=(), physical=None, drive=(), coverage=None,
           regression=None):
    """
    The page, as a string. Every argument may be empty, and its section is
    then left out.

    numbers      -- (label, value) rows, as `report` prints them
    layout       -- the layout image's name next to the page, or None
    cocotb_runs  -- (title, seed, cases) per results file, cases as above
    env          -- os.environ; on GitHub Actions it names the commit and run
    signoff      -- (check, errors, tools, failed) per signoff check the run
                    reported, as entrypoint.signoff_checks gives them
    area         -- {flip_flops, logic, routed, macros: um^2}, any of them absent
    power        -- (corner, power_groups rows), or None
    gds          -- (the GDS's name next to the page, PDK for the 3D viewer or
                    None when the viewer has no layers for it), or None
    description  -- one line saying what the design is, or None
    physical     -- what a physical designer reads first, from metrics.json and
                    the run's config, any key absent: core (w, h um), taps,
                    hold_buffers, r2r_setup, r2r_hold (ns), setup and hold
                    (worst slack ns, violations), constraints {name: (value,
                    set in config.yaml)}, corner, synthesized (instances),
                    ir_worst (V)
    cells        -- (class, count, 'synthesis' | 'flow' | 'other') per instance class
    drive        -- (drive strength, after synthesis, after routing) per strength,
                    a stage with no source None; physical may also carry library
    coverage     -- build/coverage/summary.json as a dict (types, modules, files,
                    uncovered), or None
    regression   -- build/regress/summary.json as a dict (seed, runs), or None

    The page is laid out to be shared, as a portfolio piece: the layout first,
    then the verdicts (tests, timing and its constraints), then what the chip
    is made of, what it burns, and the physical verification last.
    """
    esc = html.escape
    physical = physical or {}
    parts = []  # (anchor, nav label, markup), in page order
    add = lambda anchor, label, markup: parts.append((anchor, label, markup))

    # The verdicts first: what someone landing on the page wants to know is
    # whether it works, before any number. Each chip only for what was run.
    chips = []
    cases = [verdict for _, _, run in cocotb_runs for _, verdict, _ in run]
    if cases:
        passed = cases.count("PASS")
        if len(cocotb_runs) > 1:
            # One chip per run, so "6/6 on RTL" and "6/6 on gates" say the
            # same tests held after synthesis, which a single 12/12 hides --
            # and a run that failed is red on its own, not dragging the other.
            for title, _, run in cocotb_runs:
                ok = sum(v == "PASS" for _, v, _ in run)
                chips.append(("PASS" if ok == len(run) else "FAIL",
                              f"{ok}/{len(run)} on {run_name(title)}"))
        else:
            chips.append(("PASS" if passed == len(cases) else "FAIL",
                          f"{passed}/{len(cases)} tests passed"))
    if regression and regression.get("runs"):
        ok = sum(run["verdict"] == "pass" for run in regression["runs"])
        total = len(regression["runs"])
        chips.append(("PASS" if ok == total else "FAIL", f"{ok}/{total} regression runs"))
    # Setup and hold both: a negative hold slack is a chip that fails on
    # silicon at any clock speed, so "Timing met" on setup alone would be a
    # wrong verdict, not a partial one.
    slacks = [physical[k][0] for k in ("setup", "hold") if k in physical]
    if slacks:
        chips.append(("FAIL", "Timing missed") if any(s < 0 for s in slacks)
                     else ("PASS", "Timing met"))
    if signoff:
        errors = sum(item[1] for item in signoff)
        chips.append(("FAIL", f"Signoff: {errors} errors") if errors
                     else ("PASS", "Signoff clean"))

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
                f'<tr><td><code>{test_name(name)}</code></td><td class="{verdict}">{verdict}</td>'
                f'<td class="num">{sim_ns:g}</td></tr>'
                for name, verdict, sim_ns in run) + "</table></div>")

    if regression and regression.get("runs"):
        add("regression", "Regression", regression_section(regression))

    glance = summary_cards(numbers, physical, power, signoff, coverage)
    if glance:
        add("summary", "Summary", glance)

    if coverage:
        add("coverage", "Coverage", coverage_section(coverage, cocotb_runs, regression))

    timing = timing_section(physical)
    if timing:
        add("timing", "Timing", timing)

    if area or cells or drive:
        hold = physical.get("hold_buffers")
        if hold:
            # Most of them, in a design with a fast-corner hold problem.
            cells = [(f"{name}, {hold:,} of them for hold" if name == "timing-repair buffers" else name, n, k)
                     for name, n, k in cells]
        library = physical.get("library")
        # Single-VT is a fact of the sky130 libraries, one device pair each.
        # Another PDK's library is named and nothing more is claimed.
        library_line = (f"<p>Standard cell library <code>{esc(library)}</code>"
                        + (", single threshold voltage" if library.startswith("sky130_fd_sc_") else "")
                        + ".</p>" if library else "")
        add("area", "Area and instances", "<h2>Area and instances</h2>" + library_line
            + makeup(area or {}, cells, physical.get("synthesized"))
            + drive_table(drive))

    if power:
        corner, rows = power
        total_w = next((r[4] for r in rows if r[0] == "Total"), None)
        total = total_w or 1
        rows = [r for r in rows if r[4] or r[0] == "Total"]  # Macro, Pad: zero here
        # One decimal throughout; leakage is orders of magnitude below the
        # rest, and four significant digits of it were noise.
        uw = lambda w: f"{w * 1e6:,.1f}" if w * 1e6 >= 0.05 or not w else "&lt;0.1"
        words = corner_words(corner)
        period = (physical.get("constraints") or {}).get("clock_period", (None,))[0]
        clock = f", clock {clock_mhz(period)}" if clock_mhz(period) else ""
        add("power", "Power",
            "<h2>Power</h2><p>" + (f"<strong>{milliwatts(total_w)} in total</strong> at corner "
                                   if total_w is not None else "Corner ")
            + f"<code>{esc(corner)}</code>" + (f" ({words})" if words else "")
            + f"{clock}. The table is in &micro;W.</p>"
            "<p>Switching activity is OpenSTA's default, 0.1 toggles per clock on data nets. "
            "It is not taken from simulation, so this estimates where power goes. "
            "It does not measure a workload.</p>"
            '<div class="scroll"><table class="power"><tr><th>group</th><th class="num">internal</th>'
            '<th class="num">switching</th><th class="num">leakage</th>'
            '<th class="num">total</th><th class="num">share</th><th class="bar"></th></tr>' + "".join(
                ('<tr class="total">' if group == "Total" else "<tr>") + f'<td>{esc(group)}</td>'
                f'<td class="num">{uw(i)}</td><td class="num">{uw(sw)}</td>'
                f'<td class="num">{uw(lk)}</td><td class="num">{uw(t)}</td>'
                f'<td class="num">{t / total:.1%}</td><td class="bar">'
                # A share of the whole, on a track that is the whole: a bar
                # scaled to the largest group read as that group's share.
                + ("" if group == "Total" else
                   f'<span class="track"><span style="width:{t / total:.0%}"></span></span>')
                + "</td></tr>"
                for group, i, sw, lk, t in rows) + "</table></div>")

    if signoff:
        add("signoff", "Signoff", signoff_section(signoff, physical))

    # Only on GitHub Actions, where these say which commit the page shows.
    # When the page was built, always: a published page stays up until the
    # next one replaces it, so a reader needs to know how old it is.
    # SOURCE_DATE_EPOCH, when set, pins it (reproducible builds, tests).
    epoch = env.get("SOURCE_DATE_EPOCH")
    # Taiwan time, a fixed offset: no DST, and no tz database in the image.
    taipei = timezone(timedelta(hours=8))
    built = (datetime.fromtimestamp(int(epoch), taipei) if epoch
             else datetime.now(taipei))
    meta = [f"Built {built:%Y-%m-%d %H:%M} (UTC+8)"]
    server, repo = env.get("GITHUB_SERVER_URL"), env.get("GITHUB_REPOSITORY")
    sha, run = env.get("GITHUB_SHA"), env.get("GITHUB_RUN_ID")
    if server and repo and sha:
        meta.append(f'<a href="{esc(server)}/{esc(repo)}">{esc(repo)}</a>')
        meta.append(f'commit <a href="{esc(server)}/{esc(repo)}/commit/{esc(sha)}">'
                    f"<code>{esc(sha[:7])}</code></a>")
        if run:
            meta.append(f'<a href="{esc(server)}/{esc(repo)}/actions/runs/{esc(run)}">CI run</a>')
    source = f'<p class="meta">{" &middot; ".join(meta)}</p>'
    # Whose chip it is: a portfolio page is about a person, and the owner of
    # the repository is the one name the build knows.
    owner = repo.split("/", 1)[0] if repo and "/" in repo else None
    byline = (f'<p class="byline">by <a href="{esc(server)}/{esc(owner)}">{esc(owner)}</a></p>'
              if owner and server else "")

    # What a visitor does with a chip: turn it around in 3D, take the GDS,
    # read the code. Each button only when there is something behind it.
    actions = []
    gds_name, gds_pdk, gds_size = (tuple(gds) + (None,))[:3] if gds else (None, None, None)
    if gds_pdk:
        actions.append(f'<span data-viewer="{esc(gds_pdk)}" data-gds="{esc(gds_name)}" hidden>'
                       '<a class="btn primary" target="_blank" rel="noopener">'
                       'Open in 3D</a></span>')
    if server and repo:
        actions.append(f'<a class="btn" href="{esc(server)}/{esc(repo)}">View source</a>')
    if gds_name:
        # Last, and framed like View source: a visitor rarely has the tools
        # to open a GDS, but it is the chip itself and should read as a button.
        size = f" &middot; {human_size(gds_size)}" if gds_size else ""
        actions.append(f'<a class="btn" href="{esc(gds_name)}" download>GDS{size}</a>')
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
               f'{esc(name)}/{esc(layout)}"><meta name="twitter:card" content="summary">')

    order = ["layout", "summary", "tests", "regression", "coverage", "timing", "area", "power", "signoff"]
    parts.sort(key=lambda p: order.index(p[0].split("-")[0]) if p[0].split("-")[0] in order
               else len(order))

    body = "".join(markup for _, _, markup in parts)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="description" content="{esc(summary)}">{og}'
        f"<title>{esc(design)} · chip design</title><style>{CSS}</style></head><body>"
        
        + (f'<header class="has-art">' if layout else "<header>")
        + '<div class="wrap hero"><div class="hero-text">'
        '<p class="eyebrow">Chip design · open-source flow</p>'
        f"<h1>{esc(design)}</h1>"
        + byline
        + (f'<p class="lede">{esc(description)}</p>' if description else "")
        + f"{source}"
        + ('<div class="chips">' + "".join(
            f'<span class="chip {state}">{esc(text)}</span>' for state, text in chips)
           + "</div>" if chips else "")
        + actions
        # Locally, before the flow has run, the page is the tests only; say what is missing and what adds it, or it reads as all there is.
        + ("" if layout or signoff else '<p class="hint">The layout, signoff checks, timing, area and '
           "power appear here once <code>make gds</code> has run.</p>")
        + "</div>" + hero_art(layout, design, numbers, gds_pdk) + "</div></header>"
        + ('<nav aria-label="Sections"><div class="wrap">' + "".join(
            f'<a href="#{anchor}">{esc(label)}</a>' for anchor, label, _ in parts)
           + "</div></nav>" if len(parts) > 1 else "")
        + '<main class="wrap">'
        + "".join(f'<section id="{anchor}">{markup}</section>' for anchor, _, markup in parts)
        + "</main>"
        + '<footer class="wrap"><p>'
        + 'Made with <a href="https://github.com/anlit75/ChipForAll">ChipForAll</a>, '
          "an open-source chip design flow. "
          '<a href="https://github.com/anlit75/c4o-core">c4o-core</a> generated this page.</p></footer>'
        + (f"<script>{GDS_VIEWER_JS}</script>" if "data-viewer=" in actions else "")
        + "</body></html>\n"
    )
