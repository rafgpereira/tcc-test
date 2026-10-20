"""What is sent to each model, rebuilt and checked; written to a file, never printed.

Two entry points share this module:

* ``show-request``: the request body of one recorded attempt (or of the next one, a preview),
  rebuilt with the same functions the generation uses and checked against the ``prompt_sha256``
  recorded in the attempt. A body whose prompt does not have the recorded hash is never written as
  "what was sent". When the template of the attempt is not the current file, the version with the
  recorded hash is looked up in the Git history (``template_history``).
* ``generate --dry-run --save-requests DIR``: the body of every pending combination, one file each,
  and a ``summary.json``.

Both check that the statement, the code and the example inside each prompt are the files of the
dataset, byte for byte (read here from the raw files, not through ``ProblemInput``, so the check
is not the assembly checked against itself), and warn about the statements whose powers of ten
lost their exponent in the dataset itself (``1 ≤ n ≤ 105`` for ``10^5``). The file written is the
body as JSON, indented and with ``≤`` readable: the same JSON as the bytes sent
(``prompt.wire_bytes``), only formatted. Nothing here calls a model, reads an API key or writes
outside the destination asked for.
"""

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from ai_clients import config, ollama, problem, prompt, store, template_history
from ai_clients.errors import UsageError
from ai_clients.llm import config as llm_config
from ai_clients.llm import providers
from ai_clients.llm import store as llm_store
from ai_clients.llm.schemas import BarredResponse
from ai_clients.schemas.common import Sha256Hex
from dataset.persistence import store as files
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema

# The repository root: src/prompt_templates/ and .git/ are found from it.
REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = "src/prompt_templates"
TEMPLATE_PATHS = {
    "solution": f"{TEMPLATE_DIR}/{config.PROMPT_TEMPLATE_PATH.name}",
    "prediction": f"{TEMPLATE_DIR}/{config.PREDICT_TEMPLATE_PATH.name}",
    "llm": f"{TEMPLATE_DIR}/{llm_config.LLM_TEMPLATE_PATH.name}",
}
# Never written into: the experiment's own files.
FORBIDDEN = (config.SUITES_DIR.parent, config.DATASET_DIR, Path("manifests"))

STATEMENT_TAG, CODE_TAG = "<problem_statement>", "<reference_solution_cpp>"
WITH_STATEMENT = ("black_box", "hybrid")
WITH_CODE = ("white_box", "hybrid")
LEAK = {"black_box": CODE_TAG, "white_box": STATEMENT_TAG}

# The lost exponents (methodology, section 3: the count of 2026-10-16, 71 problems).
_POWER = r"10(?:[2-9]|1[0-8])(?![\d.,])"
EXPONENT_PATTERNS = (
    re.compile(r"(?:≤|<|≥|>|·|×|\*)\s*-?\s*" + _POWER),
    re.compile(r"(?:modulo|up to|than|exceed|exceeds|to)\s+" + _POWER),
    re.compile(r"10(?:9|18)\s*\+\s*\d"),
)
_AROUND = 12  # characters kept on each side of a match (a snippet of about 30)


class ViewRefused(Exception):
    """Nothing is written: the request cannot be shown as what was sent (exit code 1)."""


# ------------------------------------------------------------------------- fidelity, exponent


class MissingPiece(Schema):
    piece: Literal["statement", "code", "example_input", "example_output"]
    file: str
    matched_chars: int = Field(ge=0)  # the longest prefix of the expected block found
    expected_chars: int = Field(ge=0)


class ExponentWarning(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    matches: list[str] = Field(min_length=1)


@dataclass(frozen=True)
class FidelityResult:
    checked: list[str]
    missing: list[MissingPiece] = field(default_factory=list)
    scenario_leak: list[str] = field(default_factory=list)

    @property
    def faithful(self) -> bool:
        return not self.missing and not self.scenario_leak


def _raw_text(folder: Path, name: str) -> str | None:
    try:
        return (folder / name).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _longest_prefix_in(block: str, text: str) -> int:
    """The length of the longest prefix of ``block`` found in ``text`` (prefixes are nested)."""
    low, high = 0, len(block)
    while low < high:
        middle = (low + high + 1) // 2
        if block[:middle] in text:
            low = middle
        else:
            high = middle - 1
    return low


def _expected_blocks(folder: Path, scenario: str) -> list[tuple[str, str, str | None]]:
    """``(piece, file, block)`` the prompt must contain; ``None`` if the file cannot be read."""
    blocks = []
    if scenario in WITH_STATEMENT:
        text = _raw_text(folder, "enunciado.md")
        block = None if text is None else f"{STATEMENT_TAG}\n{text}\n</problem_statement>"
        blocks.append(("statement", "enunciado.md", block))
    if scenario in WITH_CODE:
        text = _raw_text(folder, "AC_ref.cpp")
        block = None if text is None else f"{CODE_TAG}\n{text}\n</reference_solution_cpp>"
        blocks.append(("code", "AC_ref.cpp", block))
    raw = _raw_text(folder, "testes.json")
    try:
        example = json.loads(raw)["public_tests"][0]
        given, expected = example["input"].rstrip("\n"), example["output"].rstrip("\n")
    except (TypeError, ValueError, KeyError, IndexError):
        given = expected = None
    blocks.append(("example_input", "testes.json", None if given is None else f"Input: {given}\n"))
    blocks.append(
        (
            "example_output",
            "testes.json",
            None if expected is None else f"Expected Output: {expected}\n",
        )
    )
    return blocks


def check_fidelity(root: Path, problem_id: str, scenario: str, text: str) -> FidelityResult:
    """Whether the statement, the code and the example of the dataset are in ``text`` unchanged."""
    folder = problem.problem_folder(root, problem_id)
    checked, missing, rest = [], [], text
    for piece, name, block in _expected_blocks(folder, scenario):
        checked.append(piece)
        if block is not None and block in text:
            rest = rest.replace(block, "", 1)
            continue
        matched = 0 if block is None else _longest_prefix_in(block, text)
        size = 0 if block is None else len(block)
        missing.append(
            MissingPiece(piece=piece, file=name, matched_chars=matched, expected_chars=size)
        )
    leak = [LEAK[scenario]] if scenario in LEAK and LEAK[scenario] in rest else []
    return FidelityResult(checked, missing, leak)


def exponent_warning(root: Path, problem_id: str, scenario: str) -> ExponentWarning | None:
    """The powers of ten written without their exponent in the statement (only scenarios with it)."""
    if scenario not in WITH_STATEMENT:
        return None
    text = _raw_text(problem.problem_folder(root, problem_id), "enunciado.md") or ""
    found = sorted(
        {(m.start(), m.end()) for pattern in EXPONENT_PATTERNS for m in pattern.finditer(text)}
    )
    matches = []
    for start, end in found:
        snippet = " ".join(text[max(0, start - _AROUND) : end + _AROUND].split())
        if snippet not in matches:
            matches.append(snippet)
    return ExponentWarning(problem_id=problem_id, matches=matches) if matches else None


# ---------------------------------------------------------------------------- the request view


@dataclass(frozen=True)
class RequestView:
    model: str
    problem_id: str
    scenario: str
    kind: Literal["attempt", "barred", "preview"]
    number: int  # the attempt, the barred response, or the next attempt (preview)
    of: int  # the attempts recorded (0 in a preview)
    template: template_history.TemplateSource
    template_current_sha256: str
    prompt: str
    prompt_sha256: str
    recorded_prompt_sha256: str | None  # None only in a preview
    body: dict
    parameters_changed: list[str]
    fidelity: FidelityResult
    exponent: ExponentWarning | None


def _replace_placeholder(value: Any, text: str) -> Any:
    """``value`` with every string equal to ``<prompt>`` replaced by ``text``."""
    if value == providers.PROMPT_PLACEHOLDER:
        return text
    if isinstance(value, dict):
        return {key: _replace_placeholder(item, text) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_placeholder(item, text) for item in value]
    return value


def _leaves(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict) and value:
        out = {}
        for key, item in value.items():
            out.update(_leaves(item, f"{path}.{key}" if path else key))
        return out
    return {path: value}


def changed_parameters(recorded: dict, current: dict) -> list[str]:
    """The parameters (two levels deep, e.g. ``generationConfig.responseFormat``) that differ."""
    old, new = _leaves(recorded), _leaves(current)
    keys = {".".join(k.split(".")[:2]) for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
    return sorted(keys)


def _resolve(repo: Path, kind: str, expected: str) -> tuple[template_history.TemplateSource, str]:
    rel = TEMPLATE_PATHS[kind]
    current = prompt.load_template(Path(repo) / rel)
    return template_history.resolve(repo, rel, expected), current.sha256


def _checked(
    root: Path, problem_id: str, scenario: str, source, recorded: str | None
) -> tuple[str, str]:
    """The prompt built from ``source``; ``ViewRefused`` if its hash is not the recorded one."""
    loaded = problem.load_problem(root, problem_id)
    text = prompt.build_prompt(source.template, loaded, scenario)
    sha = prompt.prompt_sha256(text)
    if recorded is not None and sha != recorded:
        raise ViewRefused(
            f"the rebuilt prompt has sha256 {sha}, but the attempt recorded {recorded}; it is not "
            "written as what was sent"
        )
    return text, sha


def _no_attempt(problem_id: str, scenario: str, what: str, n: int, have: list[int]) -> UsageError:
    if not have:
        return UsageError(f"{problem_id} {scenario} has no {what} {n} (no {what} yet)")
    listed = f"{have[0]}–{have[-1]}" if len(have) > 1 else str(have[0])
    plural = "attempts" if what == "attempt" else "barred responses"
    return UsageError(f"{problem_id} {scenario} has no {what} {n} ({plural}: {listed})")


def _slm_view(root, problem_id, scenario, attempt, tree, repo) -> RequestView:
    from ai_clients import generation  # late: generation pulls the Ollama client

    run = store.read_run(root, tree) if store.run_exists(root, tree) else None
    generations = store.attempt_files(root, problem_id, scenario, run, tree).generations
    numbers = [g.attempt for g in generations]
    if attempt is not None and attempt not in numbers:
        raise _no_attempt(problem_id, scenario, "attempt", attempt, numbers)
    if generations:
        record = generations[(attempt or numbers[-1]) - 1]
        kind = record.template.value
        expected = record.template_sha256
        if expected is None:  # attempts written before 2026-10-07 (research R2, S5)
            expected = (
                run.template_sha256(kind)
                if run is not None
                else prompt.load_template(Path(repo) / TEMPLATE_PATHS[kind]).sha256
            )
        source, current = _resolve(repo, kind, expected)
        text, sha = _checked(root, problem_id, scenario, source, record.prompt_sha256)
        options = generation.generation_options(run, record.attempt)
        body = ollama.request_body(run.model, text, options)
        number, view_kind, recorded = record.attempt, "attempt", record.prompt_sha256
    else:
        number = 1
        spec = run.spec(number) if run is not None else config.attempt_spec(number)
        kind = getattr(spec.template, "value", spec.template)
        current = prompt.load_template(Path(repo) / TEMPLATE_PATHS[kind]).sha256
        source, _ = _resolve(repo, kind, current)
        text, sha = _checked(root, problem_id, scenario, source, None)
        if run is not None:
            options, model = generation.generation_options(run, number), run.model
        else:  # no run yet: the options a first generate would record
            options = ollama.GenerationOptions(
                **generation.sampling_options().model_dump(),
                temperature=spec.temperature,
                seed=spec.seed,
            )
            model = os.environ.get(config.ENV_MODEL, "").strip() or config.MODEL
        body = ollama.request_body(model, text, options)
        view_kind, recorded = "preview", None
    return RequestView(
        model="slm",
        problem_id=problem_id,
        scenario=scenario,
        kind=view_kind,
        number=number,
        of=len(numbers),
        template=source,
        template_current_sha256=current,
        prompt=text,
        prompt_sha256=sha,
        recorded_prompt_sha256=recorded,
        body=body,
        parameters_changed=[],
        fidelity=check_fidelity(root, problem_id, scenario, text),
        exponent=exponent_warning(root, problem_id, scenario),
    )


def _llm_view(root, model, problem_id, scenario, attempt, barred, tree, repo) -> RequestView:
    run = llm_store.read_run(root, model, tree) if llm_store.run_exists(root, model, tree) else None
    attempts = llm_store.attempt_files(root, model, problem_id, scenario, run, tree).attempts
    numbers = [a.attempt for a in attempts]
    record, view_kind = None, "attempt"
    if barred is not None:
        found = {
            int(p.stem): p for p in llm_store.barred_files(root, model, problem_id, scenario, tree)
        }
        if barred not in found:
            raise _no_attempt(problem_id, scenario, "barred response", barred, sorted(found))
        record = BarredResponse.model_validate_json(found[barred].read_bytes())
        number, view_kind = barred, "barred"
    elif attempt is not None and attempt not in numbers:
        raise _no_attempt(problem_id, scenario, "attempt", attempt, numbers)
    elif attempts:
        record = attempts[(attempt or numbers[-1]) - 1]
        number = record.attempt
    if record is not None:
        source, current = _resolve(repo, "llm", record.template_sha256)
        text, sha = _checked(root, problem_id, scenario, source, record.prompt_sha256)
        body = _replace_placeholder(record.request_parameters, text)
        changed = changed_parameters(record.request_parameters, providers.request_parameters(model))
        recorded = record.prompt_sha256
    else:
        number, view_kind = 1, "preview"
        current = prompt.load_template(Path(repo) / TEMPLATE_PATHS["llm"]).sha256
        source, _ = _resolve(repo, "llm", current)
        text, sha = _checked(root, problem_id, scenario, source, None)
        body, changed, recorded = providers.request_body(model, text), [], None
    return RequestView(
        model=model,
        problem_id=problem_id,
        scenario=scenario,
        kind=view_kind,
        number=number,
        of=len(numbers),
        template=source,
        template_current_sha256=current,
        prompt=text,
        prompt_sha256=sha,
        recorded_prompt_sha256=recorded,
        body=body,
        parameters_changed=changed,
        fidelity=check_fidelity(root, problem_id, scenario, text),
        exponent=exponent_warning(root, problem_id, scenario),
    )


def build_view(
    root: Path,
    model: str,
    problem_id: str,
    scenario: str,
    *,
    attempt: int | None = None,
    barred: int | None = None,
    tree: Path | None = None,
    repo: Path | None = None,
) -> RequestView:
    """The request of one attempt (the last one by default), of one barred response, or the next.

    ``repo`` is where ``src/prompt_templates/`` and ``.git`` are (default: this repository).
    ``template_history.TemplateNotFound`` and ``ViewRefused`` when it cannot be shown as sent;
    ``UsageError`` for an attempt that does not exist; ``DamagedCombination`` as the store says.
    """
    repo = REPO_ROOT if repo is None else Path(repo)
    if model == "slm":
        if barred is not None:
            raise UsageError("--barred is only for --model gpt or --model gemini")
        return _slm_view(root, problem_id, scenario, attempt, tree, repo)
    if attempt is not None and barred is not None:
        raise UsageError("--attempt and --barred cannot be used together")
    return _llm_view(root, model, problem_id, scenario, attempt, barred, tree, repo)


# ------------------------------------------------------------------------------------- output


def body_text(body: dict) -> str:
    """The file written: the body as JSON, indented, ``≤`` readable (the same JSON as sent)."""
    return json.dumps(body, indent=2, ensure_ascii=False) + "\n"


def forbidden_destination(root: Path, path: Path) -> str | None:
    """The experiment folder ``path`` falls into (or contains), or ``None`` if it is allowed."""
    target = (Path(root) / path).resolve()
    for folder in FORBIDDEN:
        base = (Path(root) / folder).resolve()
        if target == base or base in target.parents or target in base.parents:
            return folder.as_posix()
    return None


def check_output(root: Path, path: Path, *, force: bool) -> None:
    """``UsageError`` unless ``path`` may be written (checked before anything is read)."""
    folder = forbidden_destination(root, path)
    if folder is not None:
        raise UsageError(
            f"{Path(path).as_posix()} is inside {folder}/, which is never written here"
        )
    if (Path(root) / path).is_dir():
        raise UsageError(f"{Path(path).as_posix()} is a folder; give a file name")
    if (Path(root) / path).exists() and not force:
        raise UsageError(f"{Path(path).as_posix()} already exists; use --force to overwrite it")


def _make_dirs(folder: Path) -> None:
    """Create ``folder`` one level at a time (never owned by root in the bind-mounted data/)."""
    missing = []
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    for level in reversed(missing):
        files.make_private_dir(level)


def write_output(root: Path, path: Path, view: RequestView, *, force: bool) -> Path:
    check_output(root, path, force=force)
    target = Path(root) / path
    _make_dirs(target.parent)
    files.atomic_write_text(target, body_text(view.body))
    return target


def status_lines(view: RequestView, path: Path) -> list[str]:
    """What the terminal shows: what was written and the checks; never the prompt."""
    if view.kind == "preview":
        what = f"preview, not sent (next: attempt {view.number})"
    elif view.kind == "barred":
        what = f"barred response {view.number} (no reasoning tokens); prompt sha256 matches"
    else:
        what = f"attempt {view.number} (of {view.of}); prompt sha256 matches"
    verdict = "faithful" if view.fidelity.faithful else "UNFAITHFUL"
    first = (
        f"written: {Path(path).as_posix()} — {view.model} {view.problem_id} {view.scenario} "
        f"{what}; dataset: {verdict}"
    )
    lines = [first]
    lines += [
        f"dataset: UNFAITHFUL — {m.piece} ({m.file}) matched {m.matched_chars} of "
        f"{m.expected_chars} chars"
        for m in view.fidelity.missing
    ]
    lines += [
        f"dataset: UNFAITHFUL — {tag} found in a {view.scenario} prompt"
        for tag in view.fidelity.scenario_leak
    ]
    if view.template.origin == "git":
        lines.append(
            f"warning: OLD TEMPLATE VERSION from git {view.template.commit[:12]} (current is "
            f"{view.template_current_sha256[:12]})"
        )
    if view.parameters_changed:
        lines.append(
            f"warning: parameters changed since this attempt: {', '.join(view.parameters_changed)}"
        )
    if view.exponent is not None:
        quoted = ", ".join(f'"{m}"' for m in view.exponent.matches)
        lines.append(f"warning: lost exponent in enunciado.md: {quoted}")
    return lines


# ---------------------------------------------------------------- generate --dry-run --save-requests


@dataclass(frozen=True)
class PendingRequest:
    """One request the next generate would send (built by the dry-run of each model)."""

    problem_id: str
    scenario: str
    attempt: int
    prompt: str
    body: dict
    template_sha256: str
    seed: int | None = None  # the SLM only
    temperature: float | None = None


class SavedRequest(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Literal["black_box", "white_box", "hybrid"]
    attempt: int = Field(ge=1)
    prompt_chars: int = Field(ge=0)
    prompt_sha256: Sha256Hex
    template_sha256: Sha256Hex
    faithful: bool
    request_file: str
    seed: int | None = None
    temperature: float | None = None


class UnfaithfulEntry(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Literal["black_box", "white_box", "hybrid"]
    missing: list[MissingPiece]
    scenario_leak: list[str]


class RequestsSummary(Schema):
    """``DIR/<model>/summary.json`` (data-model.md, section 5)."""

    schema_version: Literal[1] = 1
    model: Literal["slm", "gpt", "gemini", "claude"]
    # "pending": the next request of each pending combination (generate --dry-run);
    # "suite_attempt": the attempt each suite came from, its prompt hash checked (show-request).
    source: Literal["pending", "suite_attempt"] = "pending"
    created_at: str
    dataset_manifest_sha256: Sha256Hex
    templates: dict[str, Sha256Hex]
    request_parameters: dict[str, Any]
    combinations: int = Field(ge=0)
    faithful: int = Field(ge=0)
    requests: list[SavedRequest]
    unfaithful: list[UnfaithfulEntry]
    exponent_warnings: list[ExponentWarning]
    damaged: list[str]  # also the combinations whose request could not be checked (nothing written)
    skipped: list[str] = Field(default_factory=list)  # "<id> <scenario>: <why>", nothing to write

    @model_validator(mode="after")
    def _counts(self) -> "RequestsSummary":
        if self.combinations != len(self.requests):
            raise ValueError("combinations must be the number of requests")
        if self.faithful != sum(r.faithful for r in self.requests):
            raise ValueError("faithful must count the faithful requests")
        bad = {(r.problem_id, r.scenario) for r in self.requests if not r.faithful}
        if {(u.problem_id, u.scenario) for u in self.unfaithful} != bad or len(
            self.unfaithful
        ) != len(bad):
            raise ValueError("unfaithful must list exactly the requests that are not faithful")
        return self


def check_save_destination(root: Path, dest: Path, model: str, *, force: bool) -> None:
    """``UsageError`` unless the dry-run may write ``dest/<model>/`` (before anything is done)."""
    folder = forbidden_destination(root, dest)
    if folder is not None:
        raise UsageError(
            f"{Path(dest).as_posix()} is inside (or contains) {folder}/, which is never written here"
        )
    target = Path(root) / dest / model
    if target.exists() and not target.is_dir():
        raise UsageError(f"{(Path(dest) / model).as_posix()} is a file, not a folder")
    if target.is_dir() and any(target.iterdir()) and not force:
        raise UsageError(
            f"{(Path(dest) / model).as_posix()} already has files; use --force to replace them"
        )


def save_requests(
    root: Path,
    model: str,
    pending: list[PendingRequest],
    dest: Path,
    *,
    force: bool,
    templates: dict[str, str],
    request_parameters: dict,
    dataset_manifest_sha256: str,
    damaged: list[str],
    now: str,
    source: Literal["pending", "suite_attempt"] = "pending",
    skipped: list[str] | None = None,
) -> tuple[RequestsSummary, list[str]]:
    """Write one ``<id>.<scenario>.request.json`` per request and ``summary.json``, flat in
    ``dest/<model>/``; the summary and the lines for the terminal."""
    check_save_destination(root, dest, model, force=force)
    target = Path(root) / dest / model
    if target.is_dir():
        shutil.rmtree(target)
    _make_dirs(target)
    saved, unfaithful, warnings, lines = [], [], {}, []
    for item in pending:
        name = f"{item.problem_id}.{item.scenario}.request.json"
        files.atomic_write_text(target / name, body_text(item.body))
        fidelity = check_fidelity(root, item.problem_id, item.scenario, item.prompt)
        saved.append(
            SavedRequest(
                problem_id=item.problem_id,
                scenario=item.scenario,
                attempt=item.attempt,
                prompt_chars=len(item.prompt),
                prompt_sha256=prompt.prompt_sha256(item.prompt),
                template_sha256=item.template_sha256,
                faithful=fidelity.faithful,
                request_file=name,
                seed=item.seed,
                temperature=item.temperature,
            )
        )
        if not fidelity.faithful:
            unfaithful.append(
                UnfaithfulEntry(
                    problem_id=item.problem_id,
                    scenario=item.scenario,
                    missing=fidelity.missing,
                    scenario_leak=fidelity.scenario_leak,
                )
            )
            lines += [
                f"unfaithful: {item.problem_id} {item.scenario}: {m.piece} ({m.file}) matched "
                f"{m.matched_chars} of {m.expected_chars} chars"
                for m in fidelity.missing
            ]
            lines += [
                f"unfaithful: {item.problem_id} {item.scenario}: {tag} found in a "
                f"{item.scenario} prompt"
                for tag in fidelity.scenario_leak
            ]
        warning = exponent_warning(root, item.problem_id, item.scenario)
        if warning is not None:
            warnings.setdefault(item.problem_id, [warning, 0])[1] += 1
    summary = RequestsSummary(
        model=model,
        created_at=now,
        dataset_manifest_sha256=dataset_manifest_sha256,
        templates=templates,
        request_parameters=request_parameters,
        combinations=len(saved),
        faithful=sum(r.faithful for r in saved),
        requests=saved,
        unfaithful=unfaithful,
        exponent_warnings=[warnings[pid][0] for pid in sorted(warnings)],
        damaged=damaged,
        source=source,
        skipped=skipped or [],
    )
    files.atomic_write_json(target / "summary.json", summary)
    combos = sum(count for _, count in warnings.values())
    what = "requests" if source == "pending" else "suite attempts"
    checked = "" if source == "pending" else "; prompt sha256 matches in all"
    extra = "" if source == "pending" else f"; {len(summary.skipped)} skipped"
    lines.append(
        f"{what}: {summary.combinations} saved in {(Path(dest) / model).as_posix()}{checked}; "
        f"faithful {summary.faithful}/{summary.combinations}{extra}; exponent warnings "
        f"{len(warnings)} problems ({combos} combinations)"
    )
    lines += [f'exponent: {w.problem_id}: "{w.matches[0]}"' for w in summary.exponent_warnings]
    return summary, lines


def suite_attempt_requests(
    root: Path,
    model: str,
    combinations: list[tuple[str, str]],
    *,
    tree: Path | None = None,
    repo: Path | None = None,
) -> tuple[list[PendingRequest], list[str], list[str]]:
    """The request of the attempt each suite came from (``accepted_attempt`` of ``suite.json``).

    ``(requests, skipped, refused)``: a combination without ``suite.json`` yet, or closed by hand
    (a suite with no attempt), is skipped; one whose request cannot be checked against its
    recorded hash (template not found, another hash, damage) is refused and never written.
    """
    requests, skipped, refused = [], [], []
    for problem_id, scenario in combinations:
        try:
            suite = (
                store.read_suite(root, problem_id, scenario, tree)
                if model == "slm"
                else llm_store.read_suite(root, model, problem_id, scenario, tree)
            )
        except ValueError as exc:  # a suite.json that does not validate
            refused.append(f"{problem_id} {scenario}: suite.json: {exc}")
            continue
        if suite is None:
            skipped.append(f"{problem_id} {scenario}: no suite.json yet")
            continue
        if suite.accepted_attempt is None:
            skipped.append(f"{problem_id} {scenario}: {suite.status.value} (no attempt)")
            continue
        try:
            view = build_view(
                root,
                model,
                problem_id,
                scenario,
                attempt=suite.accepted_attempt,
                tree=tree,
                repo=repo,
            )
        except (template_history.TemplateNotFound, ViewRefused, store.DamagedCombination) as exc:
            refused.append(f"{problem_id} {scenario}: {exc}")
            continue
        options = view.body.get("options", {}) if model == "slm" else {}
        requests.append(
            PendingRequest(
                problem_id=problem_id,
                scenario=scenario,
                attempt=view.number,
                prompt=view.prompt,
                body=view.body,
                template_sha256=view.template.expected_sha256,
                seed=options.get("seed"),
                temperature=options.get("temperature"),
            )
        )
    return requests, skipped, refused
