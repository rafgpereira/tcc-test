"""The data layer of the dashboard: plain Python and pandas, no Streamlit, nothing written.

specs/011-results-dashboard/data-model.md. Everything comes from the evaluation tree written by
``python -m evaluation run`` (validated with its own schema), the suites the results point to, and
the source files of the dataset and the mutants. The percentages are a PREVIEW of detection, always
Σ detected / Σ total over the combinations with a suite; the official metrics belong to the metrics
module.
"""

import difflib
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from dashboard import config
from evaluation import sources
from evaluation.schemas.result import CombinationResult, TargetResult

COLUMNS = (
    "set",
    "model",
    "problem",
    "scenario",
    "macrocategoria",
    "status",
    "tree",
    "attempt",
    "has_suite",
    "no_suite_reason",
    "suite_size",
    "ac_approved",
    "ac_wrong_output",
    "ac_runtime_error",
    "ac_unstable",
    "n_wa",
    "n_mutants",
    "wa_declared",
    "wa_corrected",
    "mutants_declared",
    "mutants_corrected",
    "target_unstable",
    "not_compiled",
    "elapsed_s",
)
PREVIEW = {  # preview column -> (detected column, total column)
    "wa_pct_declared": ("wa_declared", "n_wa"),
    "wa_pct_corrected": ("wa_corrected", "n_wa"),
    "mutants_pct_declared": ("mutants_declared", "n_mutants"),
    "mutants_pct_corrected": ("mutants_corrected", "n_mutants"),
}


@dataclass(frozen=True)
class LoadedTree:
    base: Path
    loaded_at: datetime
    table: pd.DataFrame
    invalid: tuple[tuple[str, str], ...]  # (file, reason)
    closed: dict[str, int]  # set -> problems closed


def _macrocategoria(root: Path, problem: str, cache: dict[str, str]) -> str:
    if problem not in cache:
        path = Path(root) / "data/dataset/problems" / problem / "metadata.json"
        try:
            cache[problem] = json.loads(path.read_text(encoding="utf-8")).get("macrocategoria", "")
        except (OSError, ValueError):
            cache[problem] = ""
    return cache[problem]


def _row(r: CombinationResult, macro: str) -> dict:
    tests = r.ac.tests if r.ac else []
    return {
        "set": r.set,
        "model": r.model,
        "problem": r.problem_id,
        "scenario": r.scenario,
        "macrocategoria": macro,
        "status": r.suite_source.status or "",
        "tree": r.suite_source.tree,
        "attempt": r.suite_source.attempt,
        "has_suite": r.has_suite,
        "no_suite_reason": r.no_suite_reason or "",
        "suite_size": r.suite_size,
        "ac_approved": r.ac.approved if r.ac else None,
        "ac_wrong_output": sum(t.verdict == "wrong_output" for t in tests),
        "ac_runtime_error": sum(t.verdict == "runtime_error" for t in tests),
        "ac_unstable": sum(t.unstable for t in tests),
        "n_wa": sum(t.kind == "wa" for t in r.targets),
        "n_mutants": sum(t.kind == "mutant" for t in r.targets),
        "wa_declared": len(r.detected.declared_wa),
        "wa_corrected": len(r.detected.corrected_wa),
        "mutants_declared": len(r.detected.declared_mutants),
        "mutants_corrected": len(r.detected.corrected_mutants),
        "target_unstable": sum(len(t.unstable_tests) for t in r.targets),
        "not_compiled": sum(not t.compiled for t in r.targets),
        "elapsed_s": r.elapsed_s,
    }


def combinations(base: Path, root: Path = Path(".")) -> LoadedTree:
    """One row per closed combination of the tree (``building/`` is never read)."""
    base = Path(base)
    rows, invalid, closed, macro = [], [], {}, {}
    for set_dir in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        problems = set_dir / "problems"
        if not problems.is_dir():
            continue
        closed[set_dir.name] = sum(1 for p in problems.iterdir() if p.is_dir())
        for path in sorted(problems.glob("*/*.json")):
            try:
                result = CombinationResult.model_validate_json(path.read_bytes())
            except (OSError, ValueError) as exc:
                reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                invalid.append((path.relative_to(base).as_posix(), reason))
                continue
            rows.append(_row(result, _macrocategoria(root, result.problem_id, macro)))
    table = pd.DataFrame(rows, columns=list(COLUMNS))
    return LoadedTree(base, datetime.now(UTC), table, tuple(invalid), closed)


def apply_filters(
    table: pd.DataFrame,
    sets=(),
    scenarios=(),
    problems=(),
    macrocategorias=(),
    statuses=(),
) -> pd.DataFrame:
    """Keep the rows whose values are in each non-empty list (an empty list filters nothing)."""
    mask = pd.Series(True, index=table.index)
    for column, allowed in (
        ("set", sets),
        ("scenario", scenarios),
        ("problem", problems),
        ("macrocategoria", macrocategorias),
        ("status", statuses),
    ):
        if allowed:
            mask &= table[column].isin(list(allowed))
    return table[mask]


def _ordered(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    order = {"set": config.SETS, "scenario": config.SCENARIOS}
    keys = [c for c in columns if c in order]
    if not keys or frame.empty:
        return frame
    rank = {c: {v: i for i, v in enumerate(order[c])} for c in keys}
    sort = frame.assign(**{f"_{c}": frame[c].map(rank[c]).fillna(99) for c in keys})
    return sort.sort_values([f"_{c}" for c in keys]).drop(columns=[f"_{c}" for c in keys])


def preview(table: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Detection preview per group: Σ detected / Σ total, only combinations with a suite."""
    with_suite = table[table["has_suite"]]
    sums = with_suite.groupby(by, sort=False)[
        [
            "wa_declared",
            "wa_corrected",
            "mutants_declared",
            "mutants_corrected",
            "n_wa",
            "n_mutants",
        ]
    ].sum()
    out = pd.DataFrame(index=sums.index)
    for name, (detected, total) in PREVIEW.items():
        out[name] = (100 * sums[detected] / sums[total].where(sums[total] > 0)).round(1)
    return _ordered(out.reset_index(), by)


def overview(table: pd.DataFrame) -> pd.DataFrame:
    """Per set × scenario: what was evaluated, the AC, the detections (counts and preview)."""
    by = ["set", "scenario"]
    if table.empty:
        return pd.DataFrame(columns=by)
    g = table.groupby(by, sort=False)
    with_suite = table[table["has_suite"]]
    s = with_suite.groupby(by, sort=False)
    counts = pd.DataFrame(
        {
            "combinations": g.size(),
            "without_suite": g["has_suite"].apply(lambda x: int((~x).sum())),
            "ac_approved": s["ac_approved"].apply(lambda x: int((x == True).sum())),
            "ac_rejected": s["ac_approved"].apply(lambda x: int((x == False).sum())),
            "ac_wrong_output_tests": s["ac_wrong_output"].sum(),
            "ac_runtime_error_tests": s["ac_runtime_error"].sum(),
            "wa_declared": s["wa_declared"].sum(),
            "wa_corrected": s["wa_corrected"].sum(),
            "mutants_declared": s["mutants_declared"].sum(),
            "mutants_corrected": s["mutants_corrected"].sum(),
            "unstable_tests": s["ac_unstable"].sum() + s["target_unstable"].sum(),
            "not_compiled": s["not_compiled"].sum(),
        }
    ).fillna(0)
    counts = counts.astype({c: int for c in counts.columns}).reset_index()
    return _ordered(counts.merge(preview(table, by), on=by, how="left"), by)


def per_problem(table: pd.DataFrame) -> pd.DataFrame:
    """One row per combination with its preview, for the table under the overview."""
    rows = table[table["has_suite"]].copy()
    for name, (detected, total) in PREVIEW.items():
        rows[name] = (100 * rows[detected] / rows[total].where(rows[total] > 0)).round(1)
    columns = ["problem", "scenario", "set", "macrocategoria", "status", "ac_approved"]
    return _ordered(rows[columns + list(PREVIEW)].sort_values(["problem"]), ["set", "scenario"])


# ------------------------------------------------------------------------ one combination


@dataclass(frozen=True)
class CombinationDetail:
    result: CombinationResult
    tests: pd.DataFrame  # TestRow
    suite_available: bool  # the suite (input, expected) could be read
    suite_changed: bool  # its hash differs from the one recorded by the evaluation


def read_result(base: Path, set_name: str, problem: str, scenario: str) -> CombinationResult:
    path = Path(base) / set_name / "problems" / problem / f"{scenario}.json"
    return CombinationResult.model_validate_json(path.read_bytes())


def _suite_tests(root: Path, r: CombinationResult) -> tuple[list[tuple[str, str]] | None, bool]:
    """(input, expected) of every test of the suite evaluated, and whether it changed since."""
    source = r.suite_source
    try:
        if source.attempt is not None:
            suite = sources.attempt_suite(root, r.problem_id, r.scenario, source.attempt)
            pairs = [(t.input, t.output) for t in suite.tests]
            return pairs, suite.source.suite_sha256 != source.suite_sha256
        path = Path(root) / "data" / source.tree / "problems" / r.problem_id / r.scenario
        raw = (path / "suite.json").read_bytes()
        pairs = [(t["input"], t["output"]) for t in json.loads(raw)["tests"]]
        return pairs, hashlib.sha256(raw).hexdigest() != source.suite_sha256
    except (OSError, ValueError, KeyError):
        return None, False


def combination_tests(
    base: Path, set_name: str, problem: str, scenario: str, root: Path = Path(".")
) -> CombinationDetail:
    r = read_result(base, set_name, problem, scenario)
    columns = [
        "index",
        "input",
        "expected",
        "actual",
        "ac_verdict",
        "error_kind",
        "unstable",
        "wa_declared_here",
        "wa_corrected_here",
        "mut_declared_here",
        "mut_corrected_here",
    ]
    if r.ac is None:
        return CombinationDetail(r, pd.DataFrame(columns=columns), False, False)
    pairs, changed = _suite_tests(root, r)

    def here(kind: str, oracle: str, i: int) -> int:
        return sum(t.kind == kind and getattr(t, oracle).test_index == i for t in r.targets)

    rows = []
    for t in r.ac.tests:
        known = pairs is not None and t.index < len(pairs)
        rows.append(
            {
                "index": t.index,
                "input": pairs[t.index][0] if known else "",
                "expected": pairs[t.index][1] if known else "",
                "actual": t.actual_output,
                "ac_verdict": t.verdict,
                "error_kind": t.error_kind or "",
                "unstable": t.unstable,
                "wa_declared_here": here("wa", "declared", t.index),
                "wa_corrected_here": here("wa", "corrected", t.index),
                "mut_declared_here": here("mutant", "declared", t.index),
                "mut_corrected_here": here("mutant", "corrected", t.index),
            }
        )
    return CombinationDetail(r, pd.DataFrame(rows, columns=columns), pairs is not None, changed)


def only_declared(result: CombinationResult) -> list[str]:
    """Targets detected by the declared oracle and not by the corrected one (target order)."""
    return [t.target for t in result.targets if t.declared.detected and not t.corrected.detected]


# --------------------------------------------------------------------------------- one target


@dataclass(frozen=True)
class TargetDetail:
    target: TargetResult
    source: str | None
    ac_source: str | None
    diff_html: str | None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def target_detail(
    base: Path, set_name: str, problem: str, scenario: str, target: str, root: Path = Path(".")
) -> TargetDetail:
    r = read_result(base, set_name, problem, scenario)
    found = next(t for t in r.targets if t.target == target)
    folder = "data/dataset/problems" if found.kind == "wa" else "data/mutants/problems"
    source = _read(Path(root) / folder / problem / f"{target}.cpp")
    ac_source = _read(Path(root) / "data/dataset/problems" / problem / "AC_ref.cpp")
    diff = None
    if source is not None and ac_source is not None:
        diff = difflib.HtmlDiff(wrapcolumn=70).make_table(
            ac_source.splitlines(), source.splitlines(), "AC_ref.cpp", f"{target}.cpp"
        )
    return TargetDetail(found, source, ac_source, diff)


# -------------------------------------------------------------------------------- comparisons


def oracle_gap(table: pd.DataFrame) -> pd.DataFrame:
    """Per combination with a suite: how many detections only the declared oracle gives."""
    rows = table[table["has_suite"]].copy()
    rows["wa_gap"] = rows["wa_declared"] - rows["wa_corrected"]
    rows["mutants_gap"] = rows["mutants_declared"] - rows["mutants_corrected"]
    columns = ["set", "problem", "scenario", "ac_approved", "ac_wrong_output", "ac_runtime_error"]
    columns += ["wa_declared", "wa_corrected", "wa_gap"]
    columns += ["mutants_declared", "mutants_corrected", "mutants_gap"]
    return _ordered(rows[columns].sort_values(["problem"]), ["set", "scenario"])


def local_vs_commercial(table: pd.DataFrame) -> pd.DataFrame:
    """The five sets side by side per problem × scenario (preview of detection)."""
    rows = table[table["has_suite"]].copy()
    for name, (detected, total) in PREVIEW.items():
        rows[name] = (100 * rows[detected] / rows[total].where(rows[total] > 0)).round(1)
    wide = rows.pivot_table(
        index=["problem", "scenario"],
        columns="set",
        values=["wa_pct_declared", "wa_pct_corrected"],
        aggfunc="first",
    )
    present = [s for s in config.SETS if s in wide.columns.get_level_values(1)]
    columns = [(v, s) for v in ("wa_pct_declared", "wa_pct_corrected") for s in present]
    wide = wide.reindex(columns=columns)
    wide.columns = [f"{s} {'decl' if v.endswith('declared') else 'corr'}" for v, s in columns]
    return wide.reset_index()


def metrics_files(root: Path = Path(".")) -> list[str]:
    folder = Path(root) / config.METRICS_DIR
    if not folder.is_dir():
        return []
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
