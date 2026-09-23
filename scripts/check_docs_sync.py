"""Check that the living documentation is in sync (Constitution, Principle XI).

Run inside the containers::

    docker compose run --rm app python scripts/check_docs_sync.py [options]

Checks (stdlib only, so it runs anywhere):

C1  module README structure: Status line, sections (a) to (f) in the template order, and a
    purpose of one sentence.
C2  commands: every ``python -m dataset <sub>`` in a module README must exist in the CLI; in the
    README of the module that owns the CLI (``--cli-owner``) every CLI subcommand must also be
    documented. Outside module mode the root README must also have a "Referência de comandos"
    section that lists every CLI subcommand (and cites none that does not exist), so that no
    command lives only in the code.
C3  relative markdown links resolve.
C4  root README state: ``Estado atual (AAAA-MM-DD)`` line, its date against the newest row of the
    methodology history (section 8), the module table against the module READMEs on disk, and
    the "nenhum módulo está implementado" phrase.
C5  sync matrix: every decision D# of the spec has a row, and the terms of each row appear in
    ``docs/metodologia-referencia.md``.
C6  (--closing) no ACTIVE ``[PROPOSTA`` tag in the methodology. Blockquote lines (the legend) and
    struck-through text (already resolved items) are ignored.
CV  "Comandos verificados" table of each module README: stamps are well formed, ``pendente`` rows
    are not allowed once the module is implemented (or with --closing), every documented
    subcommand is listed, and with --closing a ``+dirty`` revision is rejected.

Selection: ``--only`` wins; otherwise ``--closing`` runs everything; otherwise ``--module`` runs
C1, C2, C3 and CV for those modules; otherwise everything except C6.

Exit codes: 0 all selected checks pass, 1 at least one finding, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ALL_IDS = ("C1", "C2", "C3", "C4", "C5", "C6", "CV")
MODULE_IDS = ("C1", "C2", "C3", "CV")
REPO_IDS = ("C1", "C2", "C3", "C4", "C5", "CV")

SECTIONS = (
    "(a) Propósito",
    "(b) Como executar",
    "(c) Entradas esperadas",
    "(d) Saídas produzidas",
    "(e) Dependências e pré-requisitos",
    "(f) Limitações conhecidas",
)
STATUS_VALUES = ("planejado", "em implementação", "implementado")
VERIFIED_HEADING = "## Comandos verificados"
COMMAND_REFERENCE = "Referência de comandos"
METHODOLOGY = "docs/metodologia-referencia.md"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REVISION_RE = re.compile(r"^[0-9a-f]{7}(\+dirty)?$")
STATUS_RE = re.compile(
    r"^>\s*\*\*Status\*\*:\s*(planejado|em implementação|implementado)\b", re.MULTILINE
)
CLI_SUB_RE = re.compile(r"python -m dataset\s+([A-Za-z][\w-]*)")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
NO_MODULE_PHRASE = "nenhum módulo está implementado"


@dataclass(frozen=True)
class Finding:
    check: str
    file: str
    message: str

    def __str__(self) -> str:
        return f"{self.check} {self.file}: {self.message}"


@dataclass
class Context:
    root: Path
    modules: list[str]
    feature: str
    closing: bool
    module_mode: bool
    cli: list[str]
    cli_owner: str
    _cli_subs: list[str] | None = field(default=None, repr=False)

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read(self, rel: str) -> str | None:
        path = self.path(rel)
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def module_readme(self, module: str) -> str:
        return f"{module.rstrip('/')}/README.md"


class CliError(Exception):
    pass


# ---------------------------------------------------------------------------- text helpers


def strip_fences(text: str) -> str:
    """Remove fenced code blocks (lines between ``` fences)."""
    kept, inside = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept)


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def section_body(text: str, heading: str) -> str | None:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE
    )
    return match.group(1) if match else None


def table_rows(block: str) -> list[list[str]]:
    """Cells of every table row in ``block`` (header and separator rows included)."""
    rows = []
    for line in block.split("\n"):
        line = line.strip()
        if line.startswith("|"):
            rows.append([cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))])
    return rows


def is_separator(row: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in row if cell)


def status_of(text: str) -> str | None:
    match = STATUS_RE.search(text)
    return match.group(1) if match else None


def documented_subcommands(text: str) -> list[str]:
    seen: list[str] = []
    for sub in CLI_SUB_RE.findall(text):
        if sub not in seen:
            seen.append(sub)
    return seen


# ---------------------------------------------------------------------------- CLI listing


def list_cli_subcommands(ctx: Context) -> list[str]:
    """Subcommands listed by ``<cli> --help`` (the ``{a,b,c}`` group of the usage line)."""
    if ctx._cli_subs is not None:
        return ctx._cli_subs
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ctx.root / "src"), env.get("PYTHONPATH")])
    )
    try:
        done = subprocess.run(
            ctx.cli + ["--help"],
            cwd=ctx.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CliError(f"cannot run `{' '.join(ctx.cli)} --help`: {exc}") from exc
    if done.returncode != 0:
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or [""]
        raise CliError(f"`{' '.join(ctx.cli)} --help` exited {done.returncode}: {tail[0]}")
    group = re.search(r"\{([^{}]*)\}", done.stdout)
    ctx._cli_subs = [s.strip() for s in group.group(1).split(",") if s.strip()] if group else []
    return ctx._cli_subs


# ---------------------------------------------------------------------------- checks


def check_c1(ctx: Context) -> list[Finding]:
    findings = []
    for module in ctx.modules:
        rel = ctx.module_readme(module)
        text = ctx.read(rel)
        if text is None:
            findings.append(Finding("C1", rel, "module README is missing"))
            continue
        if status_of(text) is None:
            findings.append(
                Finding("C1", rel, f"missing `> **Status**: <{' | '.join(STATUS_VALUES)}>` line")
            )
        headings = [m for m in re.finditer(r"^## (.+?)\s*$", text, re.MULTILINE)]
        positions = {m.group(1): m.start() for m in headings}
        missing = [s for s in SECTIONS if s not in positions]
        for name in missing:
            findings.append(Finding("C1", rel, f"missing section `## {name}`"))
        present = [positions[s] for s in SECTIONS if s in positions]
        if not missing and present != sorted(present):
            findings.append(Finding("C1", rel, "sections (a) to (f) are out of the template order"))
        body = section_body(text, SECTIONS[0])
        if body is not None:
            findings += _purpose_findings(rel, body)
    return findings


def _purpose_findings(rel: str, body: str) -> list[Finding]:
    prose = strip_fences(body)
    prose = re.sub(r"`[^`]*`", "code", prose)
    prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", prose)
    prose = collapse(prose).strip()
    if not prose:
        return [Finding("C1", rel, "section (a) Propósito is empty")]
    sentences = len(re.findall(r"[.!?](?=\s|$)", prose))
    if sentences > 1:
        return [Finding("C1", rel, f"the purpose must be ONE sentence, found {sentences}")]
    return []


def check_c2(ctx: Context) -> list[Finding]:
    findings = []
    docs = {}
    for module in ctx.modules:
        rel = ctx.module_readme(module)
        text = ctx.read(rel)
        if text is not None:
            docs[module.rstrip("/")] = (rel, documented_subcommands(text))
    owner = ctx.cli_owner.rstrip("/")
    if ctx.module_mode and not any(subs for _, subs in docs.values()) and owner not in docs:
        return findings
    try:
        cli_subs = list_cli_subcommands(ctx)
    except CliError as exc:
        return [Finding("C2", ctx.cli_owner, str(exc))]
    for module, (rel, subs) in docs.items():
        for sub in subs:
            if sub not in cli_subs:
                findings.append(
                    Finding(
                        "C2",
                        rel,
                        f"documents `python -m dataset {sub}`, but the CLI has no such subcommand "
                        f"(CLI: {', '.join(cli_subs) or 'none'})",
                    )
                )
        if module == owner:
            for sub in cli_subs:
                if sub not in subs:
                    findings.append(
                        Finding("C2", rel, f"CLI subcommand `{sub}` is not documented here")
                    )
    if not ctx.module_mode:
        findings += _root_reference_findings(ctx, cli_subs)
    return findings


def _root_reference_findings(ctx: Context, cli_subs: list[str]) -> list[Finding]:
    """The root README must list every CLI subcommand in its "Referência de comandos" section."""
    text = ctx.read("README.md")
    if text is None:
        return []  # a missing root README is reported by C4
    section = section_body(text, COMMAND_REFERENCE)
    if section is None:
        return [Finding("C2", "README.md", f"missing the section `## {COMMAND_REFERENCE}`")]
    listed = documented_subcommands(section)
    findings = [
        Finding(
            "C2",
            "README.md",
            f"CLI subcommand `{sub}` is missing from the section `{COMMAND_REFERENCE}`",
        )
        for sub in cli_subs
        if sub not in listed
    ]
    findings += [
        Finding(
            "C2",
            "README.md",
            f"the section `{COMMAND_REFERENCE}` cites `python -m dataset {sub}`, "
            f"but the CLI has no such subcommand",
        )
        for sub in listed
        if sub not in cli_subs
    ]
    return findings


def _link_files(ctx: Context) -> list[str]:
    files = [ctx.module_readme(m) for m in ctx.modules]
    if not ctx.module_mode:
        files = (
            ["README.md"]
            + sorted(str(p.relative_to(ctx.root)) for p in ctx.path("docs").glob("*.md"))
            + files
        )
    return [f for f in files if ctx.path(f).is_file()]


def check_c3(ctx: Context) -> list[Finding]:
    findings = []
    for rel in _link_files(ctx):
        text = strip_fences(ctx.read(rel) or "")
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = target.split("#", 1)[0].split("?", 1)[0]
            if not path:
                continue
            if not (ctx.path(rel).parent / path).resolve().exists():
                findings.append(Finding("C3", rel, f"dangling link `{target}`"))
    return findings


def _newest_history_date(methodology: str) -> str | None:
    start = re.search(r"^## 8\.", methodology, re.MULTILINE)
    if not start:
        return None
    dates = re.findall(r"^\| (\d{4}-\d{2}-\d{2}) \|", methodology[start.start() :], re.MULTILINE)
    return max(dates) if dates else None


def check_c4(ctx: Context) -> list[Finding]:
    text = ctx.read("README.md")
    if text is None:
        return [Finding("C4", "README.md", "root README is missing")]
    findings = []
    state = re.search(r"\*\*Estado atual \((\d{4}-\d{2}-\d{2})\)\*\*", text)
    if not state:
        findings.append(
            Finding("C4", "README.md", "missing the `**Estado atual (AAAA-MM-DD)**` line")
        )
    else:
        methodology = ctx.read(METHODOLOGY)
        newest = _newest_history_date(methodology) if methodology else None
        if newest is None:
            findings.append(Finding("C4", METHODOLOGY, "no history row (section 8) with a date"))
        elif state.group(1) < newest:
            findings.append(
                Finding(
                    "C4",
                    "README.md",
                    f"`Estado atual` date {state.group(1)} is older than the newest methodology "
                    f"history row ({newest}); rewrite the state sentence and its date",
                )
            )
    findings += _module_table_findings(ctx, text)
    findings += _no_module_phrase_findings(ctx, text)
    return findings


def _module_table_findings(ctx: Context, text: str) -> list[Finding]:
    findings = []
    lines = text.split("\n")
    start = next(
        (i for i, l in enumerate(lines) if l.startswith("|") and "README do módulo" in l), None
    )
    if start is None:
        return [Finding("C4", "README.md", "module table (`README do módulo` column) not found")]
    block = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        block.append(line)
    for cells in table_rows("\n".join(block))[1:]:
        if is_separator(cells) or len(cells) < 2:
            continue
        module = re.search(r"`(src/[^`]+?)/?`", cells[0])
        last = cells[-1]
        link = re.search(r"\[[^\]]*\]\(([^)\s]+)\)", last)
        if link:
            if not ctx.path(link.group(1)).is_file():
                findings.append(
                    Finding(
                        "C4", "README.md", f"module row links to a missing README `{link.group(1)}`"
                    )
                )
        elif (
            last.lower().startswith("a criar")
            and module
            and ctx.path(ctx.module_readme(module.group(1))).is_file()
        ):
            findings.append(
                Finding(
                    "C4",
                    "README.md",
                    f'row of `{module.group(1)}` says "a criar", but its README already exists',
                )
            )
    return findings


def _module_dirs(root: Path) -> list[str]:
    src = root / "src"
    if not src.is_dir():
        return []
    return sorted(
        f"src/{p.name}"
        for p in src.iterdir()
        if p.is_dir() and ((p / "__init__.py").exists() or (p / "README.md").exists())
    )


def _no_module_phrase_findings(ctx: Context, text: str) -> list[Finding]:
    normalized = collapse(re.sub(r"^>\s?", "", text, flags=re.MULTILINE)).lower()
    if NO_MODULE_PHRASE not in normalized:
        return []
    underway = []
    for module in _module_dirs(ctx.root):
        readme = ctx.read(ctx.module_readme(module))
        if readme and status_of(readme) in ("implementado", "em implementação"):
            underway.append(module)
    if not underway:
        return []
    return [
        Finding(
            "C4",
            "README.md",
            f"says \"{NO_MODULE_PHRASE}\", but {', '.join(underway)} is implemented or under "
            "implementation",
        )
    ]


def check_c5(ctx: Context) -> list[Finding]:
    matrix_rel = f"{ctx.feature.rstrip('/')}/sync-matrix.json"
    spec = ctx.read(f"{ctx.feature.rstrip('/')}/spec.md")
    methodology = ctx.read(METHODOLOGY)
    raw = ctx.read(matrix_rel)
    if raw is None:
        return [Finding("C5", matrix_rel, "sync matrix is missing")]
    try:
        matrix = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [Finding("C5", matrix_rel, f"invalid JSON: {exc}")]
    if not isinstance(matrix, dict) or matrix.get("schema_version") != 1:
        return [Finding("C5", matrix_rel, "`schema_version` must be 1")]
    rows = matrix.get("rows")
    if not isinstance(rows, list):
        return [Finding("C5", matrix_rel, "`rows` must be a list")]
    findings = []
    valid: dict[str, list[str]] = {}
    for row in rows:
        needles = row.get("needles") if isinstance(row, dict) else None
        ident = row.get("id") if isinstance(row, dict) else None
        if (
            not isinstance(ident, str)
            or not isinstance(needles, list)
            or not needles
            or not all(isinstance(n, str) and n.strip() for n in needles)
        ):
            findings.append(
                Finding("C5", matrix_rel, f"invalid row `{ident}`: `needles` must be non-empty")
            )
            continue
        valid[ident] = needles
    if spec is None:
        return findings + [Finding("C5", f"{ctx.feature}/spec.md", "spec is missing")]
    decisions = re.findall(r"^- \*\*(D\d+) —", spec, re.MULTILINE)
    for ident in decisions:
        if ident not in valid and not any(f"`{ident}`" in f.message for f in findings):
            findings.append(
                Finding("C5", matrix_rel, f"decision {ident} of the spec has no matrix row")
            )
    for ident in valid:
        if ident not in decisions:
            findings.append(
                Finding("C5", matrix_rel, f"row {ident} matches no decision of the spec")
            )
    text = collapse(methodology or "")
    for ident, needles in valid.items():
        for needle in needles:
            if collapse(needle) not in text:
                findings.append(
                    Finding("C5", METHODOLOGY, f"decision {ident}: term `{needle}` not found")
                )
    return findings


def _mask_inactive(text: str) -> str:
    """Blank out blockquote lines and struck-through text, keeping every newline."""

    def blank(segment: str) -> str:
        return re.sub(r"[^\n]", " ", segment)

    lines = [blank(l) if l.lstrip().startswith(">") else l for l in text.split("\n")]
    return re.sub(r"~~.*?~~", lambda m: blank(m.group(0)), "\n".join(lines), flags=re.DOTALL)


def check_c6(ctx: Context) -> list[Finding]:
    text = ctx.read(METHODOLOGY)
    if text is None:
        return [Finding("C6", METHODOLOGY, "methodology is missing")]
    masked = _mask_inactive(text)
    return [
        Finding(
            "C6",
            f"{METHODOLOGY}:{masked[: m.start()].count(chr(10)) + 1}",
            "active `[PROPOSTA` tag (confirm it or change it, then mark it [DECIDIDO])",
        )
        for m in re.finditer(r"\[PROPOSTA", masked)
    ]


def check_cv(ctx: Context) -> list[Finding]:
    findings = []
    for module in ctx.modules:
        rel = ctx.module_readme(module)
        text = ctx.read(rel)
        if text is None:
            continue  # C1 reports the missing README
        block = section_body(text, VERIFIED_HEADING[3:])
        rows = table_rows(block or "")
        if block is None or len(rows) < 2:
            findings.append(Finding("CV", rel, f"missing the `{VERIFIED_HEADING}` table"))
            continue
        status = status_of(text)
        stamped_or_pending = [r for r in rows[1:] if not is_separator(r) and len(r) >= 3]
        for cells in stamped_or_pending:
            findings += _verified_row_findings(ctx, rel, status, cells)
        commands = " ".join(r[0] for r in stamped_or_pending)
        for sub in documented_subcommands(text):
            if not re.search(rf"(?<![\w-]){re.escape(sub)}(?![\w-])", commands):
                findings.append(
                    Finding("CV", rel, f"documented command `{sub}` is not in the table")
                )
    return findings


def _verified_row_findings(
    ctx: Context, rel: str, status: str | None, cells: list[str]
) -> list[Finding]:
    command, date, revision = cells[0], cells[1], cells[2]
    if date.lower() == "pendente":
        if status == "implementado" or ctx.closing:
            reason = "the module is implemented" if status == "implementado" else "closing"
            return [Finding("CV", rel, f"{command} is still `pendente` ({reason})")]
        return []
    out = []
    if not DATE_RE.match(date):
        out.append(Finding("CV", rel, f"{command}: date `{date}` must be AAAA-MM-DD or `pendente`"))
    if not REVISION_RE.match(revision):
        out.append(
            Finding("CV", rel, f"{command}: revision `{revision}` must match 7 hex digits [+dirty]")
        )
    elif ctx.closing and revision.endswith("+dirty"):
        out.append(
            Finding(
                "CV", rel, f"{command}: revision `{revision}` is dirty; rerun on committed code"
            )
        )
    return out


CHECKS = {
    "C1": check_c1,
    "C2": check_c2,
    "C3": check_c3,
    "C4": check_c4,
    "C5": check_c5,
    "C6": check_c6,
    "CV": check_cv,
}


# ---------------------------------------------------------------------------- main


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="check_docs_sync.py", description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument(
        "--module", action="append", default=[], help="module dir, e.g. src/dataset"
    )
    parser.add_argument("--feature", default="specs/001-dataset-extraction")
    parser.add_argument("--closing", action="store_true", help="run every check, incl. C6")
    parser.add_argument("--only", help="comma separated check ids, e.g. C3,C4,C5")
    parser.add_argument("--cli", help='command that lists the CLI (default: "<python> -m dataset")')
    parser.add_argument("--cli-owner", default="src/dataset", help="module that documents the CLI")
    return parser


def _selected(args: argparse.Namespace) -> tuple[str, ...] | None:
    if args.only:
        ids = tuple(part.strip().upper() for part in args.only.split(",") if part.strip())
        return ids if all(i in ALL_IDS for i in ids) else None
    if args.closing:
        return ALL_IDS
    return MODULE_IDS if args.module else REPO_IDS


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: --root {args.root} is not a directory", file=sys.stderr)
        return 2
    selected = _selected(args)
    if selected is None:
        print(f"error: --only must list ids among {', '.join(ALL_IDS)}", file=sys.stderr)
        return 2
    ctx = Context(
        root=root,
        modules=[m.rstrip("/") for m in args.module] or _module_dirs(root),
        feature=args.feature,
        closing=args.closing,
        module_mode=bool(args.module),
        cli=shlex.split(args.cli) if args.cli else [sys.executable, "-m", "dataset"],
        cli_owner=args.cli_owner,
    )
    findings: list[Finding] = []
    for check_id in ALL_IDS:
        if check_id in selected:
            findings += CHECKS[check_id](ctx)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s) in {', '.join(selected)}")
        return 1
    print(f"OK: {', '.join(selected)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
