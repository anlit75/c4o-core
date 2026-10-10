"""
The progress ledger of `make sim` and `make gds`.

Both commands used to be the raw output of their tools: 510 lines for `all`,
9,500 for `gds`, with the verdicts somewhere inside. Here the raw output goes to
build/log/ and the terminal gets one line per command (`all`) or per stage
(`gds`), only ever appended to, plus the reason and the command to run next
when something fails. On a terminal, up to three rows under that show what is
running now and are erased at the end.

Three modes, chosen by C4O_PROGRESS (`make ... PROGRESS=`):

  raw    the tools' own output, as before. No ledger, no files.
  plain  the ledger as text: no colour codes, no redrawing. What CI gets.
  tty    the ledger plus the live rows.
  auto   tty when stdout is a terminal, CI is not set and TERM is not dumb;
         plain otherwise.

NO_COLOR removes colour from either, not the symbols that carry the meaning.

Where the state comes from: `all` times the commands it runs itself. `gds` does
not read LibreLane's formatted output. It watches the run directory:
runs/<tag>/NN-<step> appears when a step starts, and the step is over when its
state_out.json can be parsed, or when the next step's directory appears (a
signoff check that fails with a deferred error never writes one). What LibreLane
printed is used for one thing only: the last line, for the live rows, and the
text of an error when there is no better one.

Errors are not truncated, boxed or indented here: what the tool said is printed
as it is, at the left margin, so that it can be pasted.
"""
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from xml.etree import ElementTree

from c4o import stages

LOG_DIR = os.path.join("build", "log")

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# ---------------------------------------------------------------- the mode

def parse_mode(env):
    """(what was asked for, whether c4o-core knows that word). Empty is auto."""
    want = (env.get("C4O_PROGRESS") or "auto").strip().lower()
    return want, want in ("raw", "plain", "tty", "auto")

def choose_mode(env, isatty):
    """raw, plain or tty. auto is tty on a terminal that is not a CI log."""
    want, known = parse_mode(env)
    if known and want != "auto":
        return want
    if isatty and not env.get("CI") and env.get("TERM") != "dumb":
        return "tty"
    return "plain"

def term_width(default=80):
    return shutil.get_terminal_size((default, 24)).columns

# ---------------------------------------------------------------- style

CODES = {"bold": "1", "dim": "2", "green": "92", "red": "91", "yellow": "93", "cyan": "96", "grey": "90"}
ATTRIBUTES = ("bold", "dim")

class Style:
    """
    What the ledger looks like in a mode. Plain has no escape codes and says
    ok, FAIL and skip. A terminal has symbols and colour. NO_COLOR keeps the
    symbols and the bold and dim, and drops the colours. Colour never carries
    a meaning alone: every state has a symbol or a word.
    """
    def __init__(self, mode, env=None):
        env = os.environ if env is None else env
        self.mode = mode
        self.tty = mode == "tty"
        self.color = self.tty and not env.get("NO_COLOR")
        encoding = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
        self.ascii = (not self.tty) or bool(env.get("C4O_ASCII")) or encoding not in ("utf8", "")
        self.sep = ", " if self.ascii else " · "

    def paint(self, text, *names):
        if not self.tty or not names:
            return text
        codes = [CODES[n] for n in names if n in ATTRIBUTES or self.color]
        if not codes:
            return text
        return "".join(f"\x1b[{c}m" for c in codes) + text + "\x1b[0m"

    def mark(self, kind):
        """The visible state word or symbol, padded to the width of its column."""
        words = {"ok": "ok", "fail": "FAIL", "skip": "skip", "run": ">"}
        symbols = {"ok": "✓", "fail": "✗", "skip": "–", "run": "▸"}
        colors = {"ok": "green", "fail": "red", "skip": "grey", "run": "cyan"}
        if self.ascii:
            return self.paint(words[kind].ljust(4), colors[kind])
        return self.paint(symbols[kind], colors[kind])

    def bar(self, done, total, room):
        room = max(8, room)
        fill = int(room * done / total) if total else 0
        fill = max(0, min(room, fill))
        if self.ascii:
            return "#" * fill + "-" * (room - fill)
        body = "━" * max(0, fill - 1) + ("╸" if fill else "")
        return (self.paint(body, "green") if body else "") + self.paint("─" * (room - fill), "grey")

def vlen(text):
    return len(ANSI.sub("", text))

def fit(text, width, ellipsis="…"):
    """Cut a plain string to width columns. A cut shows."""
    if width <= 0 or len(text) <= width:
        return text
    return text[:max(0, width - 1)] + ellipsis

def compose(style, width, parts):
    """
    A row made of (text, *styles) parts. Cut to the width of the terminal when
    it does not fit, which decorative rows are allowed to do and errors are not.
    """
    plain = "".join(p[0] for p in parts)
    if width and len(plain) > width:
        return fit(plain, width, "~" if style.ascii else "…")
    return "".join(style.paint(p[0], *p[1:]) for p in parts)

def fmt_secs(x):
    if x < 0.5:
        return "<1s"
    if x < 60:
        return f"{x:.0f}s"
    return fmt_clock(x)

def fmt_clock(x):
    x = int(x + 0.5)
    if x >= 3600:
        return f"{x // 3600}:{x % 3600 // 60:02d}:{x % 60:02d}"
    return f"{x // 60}:{x % 60:02d}"

def fmt_time(x):
    return f"{x:.1f} s"

# ---------------------------------------------------------------- the rows

def ledger_row(style, kind, name, text, name_width=7):
    """`  ok    rtl     verilator, no warnings`: one command of `make sim`."""
    return f"  {style.mark(kind)} {name.ljust(name_width)} {text}".rstrip()

def stage_row(style, kind, stage, count, secs, width, extra=""):
    """One stage of `make gds`, with its explanation when the terminal is wide."""
    name = stage.name.ljust(14)
    text = f"{count} {'step' if count == 1 else 'steps'}".ljust(10) + fmt_secs(secs).ljust(6)
    row = f"  {style.mark(kind)} {name}{text}"
    if extra:
        return (row + extra).rstrip()
    if style.tty and width >= 100:
        return compose(style, width, [(row, ), (stage.blurb, "dim")])
    return row.rstrip()

def live_rows(style, width, head, bar_done, bar_total, bar_label, last):
    """
    The pinned rows. `head` is a list of (text, styles...) parts for the first
    row. At 100 columns and up the first row is whole; below 60 there is no
    bar; below 40 there is nothing to pin and the ledger alone does the job.
    """
    if width < 40:
        return []
    rows = [compose(style, width - 1, head)]
    if width >= 60:
        label = f"  {bar_label}"
        rows.append("  " + style.bar(bar_done, bar_total, width - 1 - 2 - len(label)) + label)
    if last:
        pipe = "|" if style.ascii else "│"
        rows.append(compose(style, width - 1, [(f"    {pipe} {last}", "dim")]))
    return rows

class Live:
    """
    Rows pinned under the ledger. Drawn by moving up over what was drawn and
    clearing to the end of the screen: no absolute positions and no alternate
    screen, so the ledger above stays in the terminal's scrollback and the rows
    leave nothing behind. Not a terminal: every method does nothing.
    """
    def __init__(self, out, enabled):
        self.out, self.enabled = out, enabled
        self.drawn = []     # visible lengths of the rows on screen
        self.shown = None

    def _up(self):
        if not self.drawn:
            return
        width = max(term_width(), 1)
        # Rows are cut to the width they were drawn at. After a window got
        # narrower the terminal wrapped them, and each took more lines.
        lines = sum(max(1, math.ceil(n / width)) for n in self.drawn)
        self.out.write(f"\x1b[{lines}A\r\x1b[J")
        self.drawn = []

    def draw(self, rows):
        if not self.enabled or rows == self.shown:
            return
        self._up()
        for row in rows:
            self.out.write(row + "\n")
        self.drawn = [vlen(r) for r in rows]
        self.shown = rows
        self.out.flush()

    def commit(self, line):
        """A line for the ledger. It goes above the rows, which are drawn again."""
        shown = self.shown
        if self.enabled:
            self._up()
        self.out.write(line + "\n")
        self.out.flush()
        if self.enabled and shown:
            self.shown = None
            self.draw(shown)

    def close(self):
        if self.enabled:
            self._up()
            self.shown = None
            self.out.flush()

# ---------------------------------------------------------------- files

def read_lines(path):
    try:
        with open(path, errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []

def tail_lines(path, count, block=65536):
    """The last non-empty lines of a file, read from its end, cleaned of colour codes."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - block))
            data = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [ANSI.sub("", l).rstrip() for l in data.splitlines()]
    return [l for l in lines if l.strip()][-count:]

def last_output(path):
    """
    The last line a tool printed, for the live rows. LibreLane wraps its output
    at 80 columns, and the rest of a wrapped line starts with spaces: that is
    not a line of its own, so the last one that starts at the margin is shown.
    """
    lines = tail_lines(path, 20)
    for line in reversed(lines):
        if not line[0].isspace():
            return line.strip()
    return lines[-1].strip() if lines else ""

def count_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0

def excerpt(path, count=30):
    """The end of a log, with a line that says it is the end of it."""
    lines = read_lines(path)
    shown = [l for l in lines if l.strip()][-count:]
    head = f"last {len(shown)} of {len(lines)} lines of {path}:"
    return [head] + shown

def group_raw(env, title, path, out):
    """On GitHub Actions the raw output is a collapsed group of the log."""
    if env.get("GITHUB_ACTIONS") != "true":
        return
    out.write(f"::group::{title}\n")
    try:
        with open(path, errors="replace") as f:
            shutil.copyfileobj(f, out)
    except OSError:
        pass
    out.write("::endgroup::\n")
    out.flush()

# ---------------------------------------------------------------- make sim

# What `make sim` runs: the RTL checks, the config of the tests, then each kind
# of test the config lists. `check` here is `check --for sim`.
ALL_STEPS = ("rtl", "check", "sim", "cocotb")

def summarize_cocotb(log_text, results_path, cwd=None):
    """
    What a cocotb run says, from its output and from the results file:

      dict(seed, total, passed, failures=[dict(name, module, where, message)])

    The verdict is the results file's. The output gives what the file does not:
    the seed, where in the test the assertion was, and the message with the
    `assert` line under it, which is what a person wants to read first.
    """
    cwd = cwd or os.getcwd()
    seed = re.search(r"Seeding Python random module with (?:supplied seed )?(\d+)", log_text)
    info = dict(seed=seed.group(1) if seed else None, total=0, passed=0, failures=[])

    cases = []
    try:
        for case in ElementTree.parse(results_path).getroot().iter("testcase"):
            bad = case.find("failure")
            if bad is None:
                bad = case.find("error")
            module = (case.get("classname") or "").rsplit(".", 1)[-1]
            cases.append((case.get("name"), module, bad))
    except (OSError, ElementTree.ParseError):
        cases = []
    info["total"] = len(cases)
    info["passed"] = sum(1 for _, _, bad in cases if bad is None)

    blocks = cocotb_failure_blocks(log_text)
    for name, module, bad in cases:
        if bad is None:
            continue
        block = blocks.get(name, {})
        where = block.get("where")
        if where and os.path.isabs(where[0]):
            rel = os.path.relpath(where[0], cwd)
            where = (where[0] if rel.startswith("..") else rel, where[1])
        message = block.get("message") or [m for m in (bad.get("message") or bad.text or "").splitlines() if m.strip()]
        if not module and where:
            module = os.path.splitext(os.path.basename(where[0]))[0]
        info["failures"].append(dict(
            name=name, module=module,
            where=f"{where[0]}:{where[1]}" if where else None,
            message=message,
        ))
    return info

# cocotb's own log lines start with the simulation time: `327803.00ns INFO  ...`.
COCOTB_LINE = re.compile(r"^\s*[-\d.]+\s*[munpf]?s\s+(INFO|WARNING|ERROR|DEBUG|CRITICAL)\s")
FRAME = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')

def indent_of(line):
    return len(line) - len(line.lstrip())

def cocotb_failure_blocks(log_text):
    """
    The traceback cocotb printed under `<test> failed`, for each failed test:
    {name: dict(where=(path, line), message=[lines])}. cocotb indents it by the
    width of its own columns, which is taken off here. Where is the last frame
    that is not cocotb's own.
    """
    lines = log_text.splitlines()
    found = {}
    for i, line in enumerate(lines):
        m = re.search(r"cocotb\.regression\s+(\S+) failed\s*$", line)
        if not m:
            continue
        block = []
        for nxt in lines[i + 1:]:
            if COCOTB_LINE.match(nxt):
                break
            block.append(nxt)
        entry = {}
        start = next((k for k, l in enumerate(block) if l.strip().startswith("Traceback")), None)
        if start is not None:
            base = indent_of(block[start])
            frames = [(f[0], f[1]) for f in FRAME.findall("\n".join(block)) if "/site-packages/" not in f[0]]
            if frames:
                entry["where"] = (frames[-1][0], frames[-1][1])
            after = next((k for k in range(start + 1, len(block))
                          if block[k].strip() and indent_of(block[k]) <= base), None)
            if after is not None:
                entry["message"] = [l[base:].rstrip() for l in block[after:]]
                while entry["message"] and not entry["message"][-1].strip():
                    entry["message"].pop()
        found[m.group(1)] = entry
    return found

def lint_text(log_text):
    warnings = len(re.findall(r"^%Warning", log_text, re.M))
    return "verilator, no warnings" if not warnings else f"verilator, {warnings} warning{'s' if warnings != 1 else ''}"

def synth_text(log_text):
    text = []
    version = re.search(r"^Yosys (\S+) ", log_text, re.M)
    if version:
        text.append(f"yosys {version.group(1)}")
    cells = re.findall(r"Number of cells:\s+(\d+)", log_text)
    if cells:
        text.append(f"{cells[-1]} cells")
    return ", ".join(text)

def skip_reason(log_text, command):
    m = re.search(rf"^\[INFO\] {command} skipped: (.*?)\.?\s*$", log_text, re.M)
    return f"skipped: {m.group(1)}" if m else None

def error_lines(log_text):
    return [l for l in log_text.splitlines() if l.startswith("[ERROR]")]

def run_all(entry, design, version, env=None, out=None, clock=time.monotonic, sleep=time.sleep):
    """
    rtl, check, sim and cocotb in this order, each as the command it is on its
    own, with its output in build/log/<command>.log. Returns the exit status of
    the first that failed, or 0. A kind of test that is not configured says so
    and counts as passed. Neither kind configured is `check`'s error.
    """
    env = dict(os.environ if env is None else env)
    out = out or sys.stdout
    mode = choose_mode(env, out.isatty())
    if parse_mode(env)[1] is False:
        out.write(f"[WARN] C4O_PROGRESS={env.get('C4O_PROGRESS')} is not raw, plain, tty or auto. Using auto.\n")

    if mode == "raw":
        for step in ALL_STEPS:
            rc = subprocess.run(command_of(entry, step), env=env).returncode
            if rc:
                return rc
        return 0

    style = Style(mode, env)
    width = term_width()
    os.makedirs(LOG_DIR, exist_ok=True)
    live = Live(out, style.tty and width >= 40)
    title = f"c4o all{style.sep}{design}" + (f"{style.sep}c4o-core {version}" if version else "")
    out.write(style.paint(title, "bold") + "\n")
    t_start = clock()
    done_logs = []
    failed = None
    try:
        for index, step in enumerate(ALL_STEPS):
            log = os.path.join(LOG_DIR, f"{step}.log")
            began = clock()
            with open(log, "wb") as f:
                proc = subprocess.Popen(command_of(entry, step), stdout=f, stderr=subprocess.STDOUT, env=env)
                while proc.poll() is None:
                    live.draw(all_live_rows(style, term_width(), step, index, began, clock, log, t_start))
                    sleep(0.25)
            spent = clock() - began
            text = read_text(log)
            group_raw(env, f"{step} raw output", log, out)
            if proc.returncode:
                live.commit(ledger_row(style, "fail", step, failed_text(step, text, spent, style)))
                failed = (step, index, proc.returncode, text, log)
                break
            kind, line = summarize_step(step, text, spent, style)
            if kind != "skip":
                done_logs.append(log)
            live.commit(ledger_row(style, kind, step, line))
        live.close()
    except BaseException:
        live.close()
        raise

    if failed:
        step, index, rc, text, log = failed
        for line in failure_block(step, text, log):
            out.write(line + "\n")
        for later in ALL_STEPS[index + 1:]:
            out.write(ledger_row(style, "skip", later, f"not run: {step} failed first") + "\n")
        out.flush()
        return rc
    out.write("\n" + f"  all passed in {fmt_time(clock() - t_start)}. raw output: "
              + ", ".join(done_logs) + "\n")
    out.flush()
    return 0

def command_of(entry, step):
    cmd = [sys.executable, entry, step]
    if step == "check":
        cmd += ["--for", "sim"]
    if step in ("sim", "cocotb"):
        cmd.append("--if-configured")
    return cmd

def read_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""

def summarize_step(step, text, spent, style):
    """(state, what the ledger says) for a command that exited 0."""
    sep = style.sep
    if step == "rtl":
        return "ok", sep.join(p for p in (lint_text(text), synth_text(text), fmt_time(spent)) if p)
    if step == "check":
        return "ok", f"tests configured{sep}{fmt_time(spent)}"
    if step in ("sim", "cocotb"):
        why = skip_reason(text, step)
        if why:
            return "skip", why
    if step == "sim":
        return "ok", f"testbench ran{sep}{fmt_time(spent)}"
    if step == "cocotb":
        info = summarize_cocotb(text, os.path.join("build", "cocotb-results.xml"))
        parts = [f"{info['passed']}/{info['total']} passed" if info["total"] else "passed"]
        if info["seed"]:
            parts.append(f"seed {info['seed']}")
        parts.append(fmt_time(spent))
        return "ok", sep.join(parts)

def failed_text(step, text, spent, style):
    """What the ledger says of a command that failed: for cocotb, how many tests did."""
    parts = []
    if step == "cocotb":
        info = summarize_cocotb(text, os.path.join("build", "cocotb-results.xml"))
        if info["failures"]:
            parts.append(f"{info['passed']} passed, {len(info['failures'])} failed")
            if info["seed"]:
                parts.append(f"seed {info['seed']}")
    return style.sep.join(parts or ["failed"] ) + style.sep + fmt_time(spent)

def failure_block(step, text, log):
    """
    Why a command failed, at the left margin: the line `[ERROR] cocotb tests
    failed: <names>` exactly as c4o-core has always printed it (a README quotes
    it and a CI step looks for it), then one entry for each failed test, and the
    paths. A command that is not cocotb gets the end of its own output.
    """
    out = []
    info = summarize_cocotb(text, os.path.join("build", "cocotb-results.xml")) if step == "cocotb" else None
    if info and info["failures"]:
        out += error_lines(text)
        for fail in info["failures"]:
            out.append("")
            out.append(fail["name"] + (f"  {fail['where']}" if fail["where"] else ""))
            out += fail["message"]
            if fail["module"]:
                seed = f"SEED={info['seed']} " if info["seed"] else ""
                out.append(f"make cocotb {seed}TEST={fail['module']}.{fail['name']}")
        out.append("")
        out.append(f"full output: {log} ({count_lines(log)} lines)")
        out.append("verdicts:    build/cocotb-results.xml")
    else:
        out.append("")
        out += excerpt(log)
        out.append("")
        out.append(f"full output: {log}")
    return out

def all_live_rows(style, width, step, index, began, clock, log, t_start):
    now = clock()
    tests = re.findall(r"running (\S+) \((\d+)/(\d+)\)", "\n".join(tail_lines(log, 400))) if step == "cocotb" else []
    detail = f"{style.sep}test {tests[-1][1]}/{tests[-1][2]} {tests[-1][0]}" if tests else ""
    head = [(f"  {style.mark('run')} ", ), (step, "bold"), (f"{detail}{style.sep}{fmt_secs(now - began)}", )]
    last = last_output(log)
    return live_rows(style, width, head, index, len(ALL_STEPS),
                     f"{index + 1}/{len(ALL_STEPS)} commands{style.sep}{fmt_clock(now - t_start)} elapsed", last)

# ---------------------------------------------------------------- make gds

TOP_STEP = re.compile(r"^(\d+)-(.+)$")

def read_runtime(path):
    """The seconds in a step's runtime.txt (HH:MM:SS.mmm), or None."""
    try:
        with open(path) as f:
            h, m, s = f.read().strip().split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (OSError, ValueError):
        return None

class Plan:
    """
    The steps this run will take, in order, as `make gds` asked LibreLane for
    them before the flow started (build/log/plan.json). Without it the display
    still works and says "step N" with no total.
    """
    def __init__(self, version, everything, steps):
        self.version, self.steps = version, [tuple(s) for s in steps]
        self.total = len(self.steps)
        self.skipped = max(0, everything - self.total)
        self.by_slug = {stages.slug(i): (i, n) for i, n in self.steps}

    @classmethod
    def load(cls, path):
        try:
            with open(path) as f:
                data = json.load(f)
            steps = [(str(i), str(n)) for i, n in data["steps"]]
            if not steps:
                return None
            return cls(str(data.get("version") or ""), int(data.get("all") or len(steps)), steps)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def step_id(self, slug):
        """The LibreLane id of a directory's step. Dots are hyphens in a name, so
        without the plan the first hyphen is the dot, which matches case-blind."""
        if slug in self.by_slug:
            return self.by_slug[slug][0]
        return guess_id(slug)

    def title(self, slug):
        return self.by_slug[slug][1] if slug in self.by_slug else self.step_id(slug)

def guess_id(slug):
    return slug.replace("-", ".", 1)

class Step:
    def __init__(self, name, stage, now):
        m = TOP_STEP.match(name)
        self.name, self.ordinal, self.slug = name, int(m.group(1)), m.group(2)
        self.stage, self.t0, self.t1 = stage, now, None
        self.ok = False         # its state_out.json parses
        self.ended = False      # it is over: ok, or the next step began
        self.runtime = None

    @property
    def seconds(self):
        if self.runtime is not None:
            return self.runtime
        return (self.t1 - self.t0) if self.t1 is not None else 0.0

class RunDir:
    """
    runs/<tag>/ as the flow writes it. Only the first level counts: a step that
    holds steps (42-openroad-repairantennas/1-...) is one step. Directories that
    were there before the flow started are not ours: a resume adds new ones next
    to the old.
    """
    def __init__(self, path):
        self.path = path
        self.before = set(self._names())
        self.errors_before = len(read_error_log(path))
        self.steps = []
        self._known = set()

    def _names(self):
        try:
            return os.listdir(self.path)
        except OSError:
            return []

    def _state_ok(self, step):
        try:
            with open(os.path.join(self.path, step.name, "state_out.json")) as f:
                json.load(f)
            return True
        except (OSError, ValueError):
            return False

    def scan(self, now):
        fresh = [n for n in self._names() if n not in self._known and n not in self.before
                 and TOP_STEP.match(n) and os.path.isdir(os.path.join(self.path, n))]
        for name in sorted(fresh, key=lambda n: int(TOP_STEP.match(n).group(1))):
            self._known.add(name)
            stage = stages.advance(self.steps[-1].stage if self.steps else None, TOP_STEP.match(name).group(2))
            self.steps.append(Step(name, stage, now))
        for i, step in enumerate(self.steps):
            if not step.ok and self._state_ok(step):
                step.ok = True
                if not step.ended:
                    step.ended, step.t1 = True, now
            elif not step.ended and i + 1 < len(self.steps):
                step.ended, step.t1 = True, now
            if step.ok and step.runtime is None:
                step.runtime = read_runtime(os.path.join(self.path, step.name, "runtime.txt"))

    def finish(self, now):
        """The flow is over: whatever is running is not."""
        self.scan(now)
        for step in self.steps:
            if not step.ended:
                step.ended, step.t1 = True, now

    @property
    def current(self):
        return self.steps[-1] if self.steps and not self.steps[-1].ended else None

    def stage_steps(self, k):
        return [s for s in self.steps if s.stage == k]

    def unfinished(self):
        """Steps with no state_out.json that parses. After a flow: the ones that failed."""
        return [s for s in self.steps if not s.ok]

    def errors(self):
        """What this flow added to error.log. A resume appends to the one of the run before."""
        return read_error_log(self.path)[self.errors_before:]

def read_error_log(run_dir):
    return [l.rstrip() for l in read_lines(os.path.join(run_dir, "error.log")) if l.strip()]

def step_log(run_dir, step):
    """A step's own log: the one file of *.log in its directory, if it has one."""
    try:
        logs = sorted(f for f in os.listdir(os.path.join(run_dir, step.name)) if f.endswith(".log"))
    except OSError:
        return None
    return os.path.join(run_dir, step.name, logs[0]) if logs else None

def raw_line_of(raw_log, step_slug):
    """The line of the raw log where LibreLane says it runs the step, 0 if it does not."""
    found = 0
    pattern = re.compile(r"Running '([^']+)'")
    for number, line in enumerate(read_lines(raw_log), 1):
        m = pattern.search(line)
        if m and stages.slug(m.group(1)) == step_slug:
            found = number
    return found

def resume_command(run_dir, step, plan):
    ident = plan.step_id(step.slug) if plan else guess_id(step.slug)
    state = os.path.join(run_dir, step.name, "state_in.json")
    return f'make gds LIBRELANE_ARGS="--from {ident} --with-initial-state {state}"'

def stale_gds_note(gds, run_dir, design, kind):
    """
    build/<design>.gds is copied after a flow that passed, so after one that did
    not it is the file of an earlier run, and it looks like the answer. It is not
    removed: --overwrite already cleared that run's directory, so this file is
    the one copy of the last good result that is left.
    """
    if not os.path.exists(gds):
        return []
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(gds)))
    note = [f"{gds} is from an earlier run ({when}), not from this one."]
    this_run = os.path.join(run_dir, "final", "gds", f"{design}.gds")
    if kind == "deferred" and os.path.exists(this_run):
        note.append(f"This run's GDS is {this_run}. It failed a signoff check.")
    return note

def final_stamp(run_dir):
    try:
        st = os.stat(os.path.join(run_dir, "final", "metrics.json"))
        return (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return None

def watch_flow(run_dir, status, log, plan_path, gds, design, partial=False, env=None, out=None,
               report=None, clock=time.monotonic, sleep=time.sleep):
    """
    Follows a LibreLane run until the status file appears, and prints the ledger.
    Returns 0 for a flow that passed and 1 for one that did not; the caller has
    LibreLane's own exit status and returns that.
    """
    env = dict(os.environ if env is None else env)
    out = out or sys.stdout
    mode = choose_mode(env, out.isatty())
    if mode == "raw":
        mode = "plain"      # raw is rules.mk's, which does not start this at all
    style = Style(mode, env)
    plan = Plan.load(plan_path)
    if plan and partial:
        plan.total, plan.skipped = None, 0      # the names are good for any run, the count only for a whole one
    run = RunDir(run_dir)
    before = final_stamp(run_dir)
    live = Live(out, style.tty and term_width() >= 40)
    t_start = clock()
    interrupted = []

    def on_interrupt(signum, frame):
        interrupted.append(True)
    try:
        signal.signal(signal.SIGINT, on_interrupt)
    except ValueError:      # not the main thread
        pass

    title = f"c4o gds{style.sep}{design}"
    if plan and plan.version:
        title += f"{style.sep}LibreLane {plan.version} Classic flow"
    out.write(style.paint(title, "bold") + "\n")
    out.flush()

    printed = 0             # stages written to the ledger
    last_output = clock()
    try:
        while True:
            now = clock()
            run.scan(now)
            printed, wrote = commit_stages(run, printed, live, rows_of(style, run, plan, None))
            if wrote:
                last_output = now
            current = run.current
            if current is not None:
                live.draw(flow_live(style, term_width(), run, current, plan, now, t_start, log))
                if not style.tty and now - last_output >= 30:
                    live.commit(f"  still running: {named(plan, current)}, {step_label(run, plan)}, "
                                f"{fmt_clock(now - t_start)} elapsed")
                    last_output = now
            if os.path.exists(status):
                break
            sleep(0.25)
        end = clock()
        run.finish(end)
        live.close()
        try:
            with open(status) as f:
                code = int(f.read().strip() or 1)
        except (OSError, ValueError):
            code = 1
        kind = None
        if code:
            kind = ("deferred" if final_stamp(run_dir) not in (None, before)
                    else "interrupted" if interrupted else "step" if run.steps else "start")
        commit_stages(run, printed, live, rows_of(style, run, plan, kind, end - t_start), final=True, kind=kind)
    except BaseException:
        live.close()
        raise

    elapsed = end - t_start
    group_raw(env, "LibreLane raw output", log, out)
    if code == 0:
        n = len(run.steps)
        skipped = f" ({plan.skipped} skipped by the config)" if plan and plan.skipped else ""
        total = f"{n}/{plan.total} steps" if plan and plan.total and plan.total != n else f"{n} steps"
        out.write(f"  {style.mark('ok')} flow complete: {total}{skipped} in {fmt_clock(elapsed)}\n")
        out.write(f"  step logs   {run_dir}/NN-*/   raw output  {log}\n")
        out.flush()
        return 0

    for line in failure_report(kind, run, run_dir, plan, log, gds, design, report):
        out.write(line + "\n")
    out.flush()
    return 1

def named(plan, step):
    """`Detailed Routing (OpenROAD.DetailedRouting)`, or the id alone without a plan."""
    if plan:
        return f"{plan.title(step.slug)} ({plan.step_id(step.slug)})"
    return guess_id(step.slug)

def rows_of(style, run, plan, kind, elapsed=0):
    """A function that makes the ledger row of stage k."""
    def row(k):
        steps = run.stage_steps(k)
        stage = stages.STAGES[k]
        secs = sum(s.seconds for s in steps)
        bad = [s for s in steps if not s.ok]
        if not (kind and bad):
            return stage_row(style, "ok", stage, len(steps), secs, term_width())
        if kind == "deferred":
            ids = ", ".join(plan.step_id(s.slug) if plan else guess_id(s.slug) for s in bad)
            return stage_row(style, "fail", stage, len(steps), secs, 0, extra=f"failed: {ids}")
        step = run.steps[-1]
        of = f" of {plan.total}" if plan and plan.total else ""
        return stage_row(style, "fail", stage, len(steps), secs, 0,
                         extra=f"stopped at step {len(run.steps)}{of}: {named(plan, step)}, "
                               f"{fmt_secs(step.seconds)} into it, {fmt_clock(elapsed)} into the flow")
    return row

def commit_stages(run, printed, live, row, final=False, kind=None):
    """
    Writes the rows of the stages that are over: a later stage has begun, or the
    flow has ended. During the flow a stage with a step that has no state_out.json
    waits: it is a failure that is deferred to the end, or a file that is still
    being written, and the ledger does not guess. Returns (stages written, whether any row was).
    """
    if not run.steps:
        return printed, False
    top = len(stages.STAGES) if final else run.steps[-1].stage
    wrote = False
    for k in range(printed, top):
        steps = run.stage_steps(k)
        if steps and not final and any(not s.ok for s in steps):
            break
        if steps and not (kind in ("interrupted", "start") and final and any(not s.ok for s in steps)):
            live.commit(row(k))
            wrote = True
        printed = k + 1
    return printed, wrote

def step_label(run, plan):
    n = len(run.steps)
    return f"step {n} of {plan.total}" if plan and plan.total else f"step {n}"

def flow_live(style, width, run, step, plan, now, t_start, log):
    stage = stages.STAGES[step.stage]
    title = plan.title(step.slug) if plan else guess_id(step.slug)
    ident = plan.step_id(step.slug) if plan else guess_id(step.slug)
    spent = fmt_secs(now - step.t0)
    n = len(run.steps)
    if width >= 100:
        head = [(f"  {style.mark('run')} ", ), (stage.name, "bold"),
                (f"  stage {step.stage + 1}/{len(stages.STAGES)}{style.sep}{title} ", ), (f"({ident})", "dim"),
                (f"{style.sep}{spent} in this step", )]
    else:
        head = [(f"  {style.mark('run')} ", ), (stage.name, "bold"),
                (f" {step.stage + 1}/{len(stages.STAGES)}{style.sep}{title}{style.sep}{spent}", )]
    total = plan.total if plan else None
    label = (f"{n}/{total} steps" if total else f"step {n}") + f"{style.sep}{fmt_clock(now - t_start)} elapsed"
    last = last_output(log)
    return live_rows(style, width, head, n if total else 0, total or 1, label, last)

def failure_report(kind, run, run_dir, plan, log, gds, design, report):
    """
    What follows the ledger when the flow did not pass: the reason, where to
    read more, how to go on, and what build/<design>.gds is.
    """
    out = []
    errors = run.errors()
    n = len(run.steps)
    of = f" of {plan.total}" if plan and plan.total else ""

    if kind == "deferred":
        bad = run.unfinished()
        ids = ", ".join(plan.step_id(s.slug) if plan else guess_id(s.slug) for s in bad) or "a signoff check"
        out.append("")
        out += errors
        if report is not None:
            out.append("")
            out.extend(capture(report))
        out.append("")
        out += stale_gds_note(gds, run_dir, design, kind)
        out.append(f"FAIL gds: the flow ran to the end and {ids} failed: {errors[0] if errors else 'a deferred error'}")
        out.append(f"raw output: {log}")
        return out

    if kind == "start":
        out.append("")
        out += excerpt(log)
        out.append("")
        out += stale_gds_note(gds, run_dir, design, kind)
        out.append("FAIL gds: LibreLane stopped before its first step")
        out.append(f"raw output: {log}")
        return out

    step = run.steps[-1]
    stage = stages.STAGES[step.stage]
    resume = resume_command(run_dir, step, plan)
    line = raw_line_of(log, step.slug)
    where = f"{log}:{line}" if line else log

    if kind == "interrupted":
        out.append(f"interrupted at step {n}{of} ({stage.name}): {named(plan, step)}")
        out += stale_gds_note(gds, run_dir, design, kind)
        out.append("resume from this step:")
        out.append(resume)
        out.append(f"raw output: {where}")
        return out

    out.append("")
    out += errors if errors else tail_lines(log, 5)
    own = step_log(run_dir, step)
    tail = tail_lines(own, 8) if own else []
    if tail:
        out.append("")
        out.append(f"last {len(tail)} lines of {os.path.basename(own)}:")
        out += tail
    out.append("")
    if own:
        out.append(f"step log    {own}")
    out.append("resume from this step:")
    out.append(resume)
    out += stale_gds_note(gds, run_dir, design, kind)
    out.append(f"FAIL gds: {stage.name} stopped at step {n}{of}, {named(plan, step)}: "
               f"{errors[0] if errors else 'see the output above'}")
    out.append(f"raw output: {where}")
    return out

def capture(fn):
    """The lines a function prints."""
    import contextlib
    import io
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        fn()
    return buffer.getvalue().rstrip("\n").splitlines()
