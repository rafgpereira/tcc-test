"""Traceability (feature 012, US5): from a number of the metrics back to the files behind it.

Plain Python and pandas, no Streamlit, nothing written. Sources: the table of combinations the
dashboard already loads (``data.combinations``), the per-target table of each set written by
``python -m evaluation report`` (``data/evaluation/<set>/results.csv``: which test detected each
WA and mutant, in each oracle), the suite trees (attempts, manual closings, responses without
reasoning, the provenance of the local model's suites) and the dataset (statement, metadata).

Detection here is always per target, as in the metrics: a WA or mutant is "detected" by a
combination when some test of its suite fails it; with the short circuit of the evaluation, the
target stops at the first test that fails it, so ``*_test_index`` is that first test.
"""

import json
from pathlib import Path

import pandas as pd

from dashboard import config

FINAL_SETS = ("slm", "gpt", "gemini", "claude")
TARGET_COLUMNS = (
    "set",
    "problem_id",
    "scenario",
    "has_suite",
    "target",
    "kind",
    "compiled",
    "declared_detected",
    "declared_test_index",
    "corrected_detected",
    "corrected_test_index",
)
ORIGIN_LABEL = {
    "accepted": "aceita (solução do modelo conferida)",
    "accepted_fallback": "reserva (predição, depois de a solução falhar)",
    "accepted_predicted": "predita (saídas escritas pelo modelo)",
}


def _bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(("true", "1", "1.0"))


def targets(base: Path, sets=config.SETS) -> pd.DataFrame:
    """Every target of every combination of the sets whose ``results.csv`` exists.

    Columns: ``set, problem, scenario, has_suite, target, kind, compiled, declared,
    declared_test, corrected, corrected_test`` (the test index is -1 when not detected).
    """
    frames = []
    for set_name in sets:
        path = Path(base) / set_name / "results.csv"
        if not path.is_file():
            continue
        frame = pd.read_csv(path, usecols=list(TARGET_COLUMNS), dtype=str, keep_default_na=False)
        frames.append(frame)
    columns = [
        "set",
        "problem",
        "scenario",
        "has_suite",
        "target",
        "kind",
        "compiled",
        "declared",
        "declared_test",
        "corrected",
        "corrected_test",
    ]
    if not frames:
        return pd.DataFrame(columns=columns)
    raw = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame(
        {
            "set": raw["set"],
            "problem": raw["problem_id"],
            "scenario": raw["scenario"],
            "has_suite": _bool(raw["has_suite"]),
            "target": raw["target"],
            "kind": raw["kind"],
            "compiled": _bool(raw["compiled"]),
            "declared": _bool(raw["declared_detected"]),
            "declared_test": pd.to_numeric(raw["declared_test_index"], errors="coerce"),
            "corrected": _bool(raw["corrected_detected"]),
            "corrected_test": pd.to_numeric(raw["corrected_test_index"], errors="coerce"),
        }
    )
    for column in ("declared_test", "corrected_test"):
        out[column] = out[column].fillna(-1).astype(int)
    return out[out["target"] != ""].reset_index(drop=True)


def cut_targets(frame: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """The targets of the combinations of an (already filtered) table of combinations."""
    keys = table[["set", "problem", "scenario"]].drop_duplicates()
    return frame.merge(keys, on=["set", "problem", "scenario"])


# ------------------------------------------------------------------- suites missing or special


def suite_folder(root: Path, tree: str, problem: str, scenario: str) -> Path:
    return Path(root) / "data" / tree / "problems" / problem / scenario


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def no_suite_reason(root: Path, row: pd.Series) -> str:
    """Why a combination has no suite: the authors' closing reason, or the evaluation's own."""
    if row["tree"]:
        close = _read_json(
            suite_folder(root, row["tree"], row["problem"], row["scenario"]) / "manual_close.json"
        )
        if close and close.get("reason"):
            return f"fechada pelos autores: {close['reason']}"
    reason = row.get("no_suite_reason") or ""
    if row["set"] == "slm-attempt1":
        return f"a 1ª tentativa do modelo local não deu suíte ({reason or 'sem testes'})"
    return reason or "sem motivo registrado"


def missing_suites(table: pd.DataFrame, root: Path = Path(".")) -> pd.DataFrame:
    rows = table[~table["has_suite"]]
    out = rows[["set", "problem", "scenario", "status"]].copy()
    out["motivo"] = [no_suite_reason(root, r) for _, r in rows.iterrows()]
    return out.sort_values(["set", "problem", "scenario"]).reset_index(drop=True)


def barred_responses(root: Path, set_name: str, problem: str, scenario: str) -> pd.DataFrame:
    folder = Path(root) / "data" / "suites" / set_name / "barred" / problem / scenario
    rows = []
    for path in sorted(folder.glob("*.json"), key=lambda p: (len(p.stem), p.stem)):
        data = _read_json(path) or {}
        usage = data.get("usage") or {}
        rows.append(
            {
                "resposta": path.stem,
                "pedida em": data.get("requested_at", ""),
                "motivo": data.get("reason", ""),
                "tokens de saída": usage.get("output_tokens"),
                "tokens de raciocínio": usage.get("reasoning_tokens"),
                "US$": data.get("cost_usd"),
            }
        )
    return pd.DataFrame(rows)


def barred_suites(table: pd.DataFrame, root: Path = Path(".")) -> pd.DataFrame:
    rows = table[table["status"] == "accepted_barred"]
    out = rows[["set", "problem", "scenario", "suite_size", "ac_approved"]].copy()
    out["respostas sem raciocínio"] = [
        len(barred_responses(root, r["set"], r["problem"], r["scenario"]))
        for _, r in rows.iterrows()
    ]
    return out.sort_values(["set", "problem", "scenario"]).reset_index(drop=True)


def slm_origin(table: pd.DataFrame) -> pd.DataFrame:
    rows = table[(table["set"] == "slm") & table["has_suite"]]
    out = pd.DataFrame(
        {
            "problem": rows["problem"],
            "scenario": rows["scenario"],
            "origem": rows["status"].map(lambda s: ORIGIN_LABEL.get(s, s)),
            "execução": rows["tree"].map(
                lambda t: "revisão 1 do dataset" if t.endswith("rev1") else "revisão 2 do dataset"
            ),
            "status": rows["status"],
        }
    )
    return out.sort_values(["status", "problem", "scenario"]).reset_index(drop=True)


def _get(data: dict, *keys, default=None):
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key)
    return default if data is None else data


def attempts(root: Path, tree: str, problem: str, scenario: str) -> pd.DataFrame:
    """Every generation attempt of a combination: how it ended, its cost and tokens."""
    if not tree:
        return pd.DataFrame()
    folder = suite_folder(root, tree, problem, scenario)
    rows = []
    for path in sorted(folder.glob("attempt_*.json"), key=lambda p: (len(p.name), p.name)):
        name = path.name.removesuffix(".json")
        if name.endswith(".execution"):
            continue
        data = _read_json(path) or {}
        if name.endswith(".generation"):  # the local model: generation + execution of a solution
            execution = _read_json(path.with_name(name.replace(".generation", ".execution.json")))
            rows.append(
                {
                    "tentativa": data.get("attempt"),
                    "pedido": data.get("template", ""),
                    "pedida em": data.get("requested_at", ""),
                    "terminou": _get(data, "ollama", "done_reason", default=""),
                    "falha": data.get("model_failure") or "",
                    "resultado": _get(execution or {}, "outcome", default=""),
                    "tokens de saída": _get(data, "ollama", "eval_count"),
                }
            )
            continue
        parse = data.get("parse") or {}
        rows.append(
            {
                "tentativa": data.get("attempt"),
                "pedida em": data.get("requested_at", ""),
                "terminou": _get(data, "finish", "status", default=""),
                "motivo": _get(data, "finish", "reason", default="") or "",
                "falha": "" if parse.get("ok", True) else parse.get("failure", ""),
                "tokens de saída": _get(data, "usage", "output_tokens"),
                "tokens de raciocínio": _get(data, "usage", "reasoning_tokens"),
                "US$": data.get("cost_usd"),
                "segundos": data.get("latency_s"),
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- AC rejected, oracle gap


def ac_rejections(table: pd.DataFrame) -> pd.DataFrame:
    rows = table[table["has_suite"] & ~table["ac_approved"].astype(bool)]
    out = rows[
        ["set", "problem", "scenario", "suite_size", "ac_wrong_output", "ac_runtime_error"]
    ].rename(
        columns={
            "suite_size": "testes",
            "ac_wrong_output": "saída esperada errada",
            "ac_runtime_error": "AC falha (entrada inválida)",
        }
    )
    return out.sort_values(["problem", "set", "scenario"]).reset_index(drop=True)


def ac_rejections_by_problem(table: pd.DataFrame) -> pd.DataFrame:
    with_suite = table[table["has_suite"]]
    grouped = with_suite.groupby("problem").agg(
        suites=("set", "size"), reprovam=("ac_approved", lambda s: int((~s.astype(bool)).sum()))
    )
    grouped = grouped[grouped["reprovam"] > 0].reset_index()
    return grouped.sort_values(["reprovam", "problem"], ascending=[False, True]).reset_index(
        drop=True
    )


def oracle_only(frame: pd.DataFrame) -> pd.DataFrame:
    """Per combination: targets detected only by the AI's answer key, and only by the AC's."""
    with_suite = frame[frame["has_suite"]]
    keys = ["set", "problem", "scenario"]
    declared_only = (with_suite["declared"] & ~with_suite["corrected"]).groupby(
        [with_suite[k] for k in keys]
    )
    corrected_only = (with_suite["corrected"] & ~with_suite["declared"]).groupby(
        [with_suite[k] for k in keys]
    )
    out = pd.DataFrame(
        {
            "só pelo gabarito da IA": declared_only.sum(),
            "só pelo gabarito do AC": corrected_only.sum(),
        }
    ).reset_index()
    out = out[(out["só pelo gabarito da IA"] > 0) | (out["só pelo gabarito do AC"] > 0)]
    return out.sort_values(
        ["só pelo gabarito da IA", "problem"], ascending=[False, True]
    ).reset_index(drop=True)


def oracle_only_targets(frame: pd.DataFrame, set_name: str, problem: str, scenario: str):
    """(targets only the AI's key detects, targets only the AC's key detects) of a combination."""
    mine = frame[
        (frame["set"] == set_name) & (frame["problem"] == problem) & (frame["scenario"] == scenario)
    ]
    declared = mine[mine["declared"] & ~mine["corrected"]]["target"].tolist()
    corrected = mine[mine["corrected"] & ~mine["declared"]]["target"].tolist()
    return declared, corrected


# ------------------------------------------------------------------------------ hard targets


def _final(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["set"].isin(FINAL_SETS)]


def detected_by(frame: pd.DataFrame, oracle: str = "corrected") -> pd.DataFrame:
    """Per (problem, target, kind): the final sets that detected it in some scenario."""
    final = _final(frame)
    hits = final[final[oracle]]
    by = hits.groupby(["problem", "target", "kind"])["set"].agg(
        lambda s: tuple(x for x in FINAL_SETS if x in set(s))
    )
    every = final[["problem", "target", "kind"]].drop_duplicates()
    out = every.merge(by.rename("sets").reset_index(), on=["problem", "target", "kind"], how="left")
    out["sets"] = out["sets"].map(lambda v: v if isinstance(v, tuple) else ())
    return out


def _target_order(frame: pd.DataFrame) -> pd.DataFrame:
    number = frame["target"].str.extract(r"(\d+)$")[0].astype(int)
    mutant = frame["target"].str.startswith("Mutant")  # WAs first, then mutants
    return (
        frame.assign(_m=mutant, _n=number)
        .sort_values(["problem", "_m", "_n"])
        .drop(columns=["_m", "_n"])
    )


def undetected(frame: pd.DataFrame, kind: str = "wa") -> pd.DataFrame:
    """Targets of ``kind`` that no final set of the cut detected, in any scenario (AC's key)."""
    found = detected_by(frame)
    out = found[(found["kind"] == kind) & (found["sets"].map(len) == 0)]
    return _target_order(out[["problem", "target"]]).reset_index(drop=True)


def exclusive(frame: pd.DataFrame, kind: str = "wa") -> pd.DataFrame:
    """Targets of ``kind`` detected by exactly one final set of the cut (AC's key)."""
    found = detected_by(frame)
    out = found[(found["kind"] == kind) & (found["sets"].map(len) == 1)].copy()
    out["só quem detectou"] = out["sets"].map(lambda s: s[0])
    return _target_order(out[["problem", "target", "só quem detectou"]]).reset_index(drop=True)


def target_matrix(frame: pd.DataFrame, problem: str, target: str) -> pd.DataFrame:
    """Set × scenario for one target: the first test that detected it in each oracle, or "—"."""
    mine = frame[(frame["problem"] == problem) & (frame["target"] == target)]
    rows = []
    for _, r in mine.iterrows():
        rows.append(
            {
                "set": r["set"],
                "scenario": r["scenario"],
                "suíte": "sim" if r["has_suite"] else "não",
                "gabarito da IA": f"teste {r['declared_test']}" if r["declared"] else "—",
                "gabarito do AC": f"teste {r['corrected_test']}" if r["corrected"] else "—",
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    order = {s: i for i, s in enumerate(config.SETS)}
    scen = {s: i for i, s in enumerate(config.SCENARIOS)}
    return out.sort_values(
        ["set", "scenario"], key=lambda c: c.map(order if c.name == "set" else scen)
    ).reset_index(drop=True)


# -------------------------------------------------------------------------- tests and problems


def killed_by_test(frame: pd.DataFrame, set_name: str, problem: str, scenario: str, index: int):
    """{"declared": [...], "corrected": [...]}: targets whose first failing test is ``index``."""
    mine = frame[
        (frame["set"] == set_name) & (frame["problem"] == problem) & (frame["scenario"] == scenario)
    ]
    return {
        oracle: _target_order(mine[mine[oracle] & (mine[f"{oracle}_test"] == index)])[
            "target"
        ].tolist()
        for oracle in ("declared", "corrected")
    }


def problem_grid(table: pd.DataFrame, problem: str) -> pd.DataFrame:
    """The combinations of one problem: suite, AC verdict and the targets detected by the AC key."""
    mine = table[table["problem"] == problem]
    rows = []
    for _, r in mine.iterrows():
        rows.append(
            {
                "set": r["set"],
                "scenario": r["scenario"],
                "status": r["status"] or ("1ª tentativa" if r["set"] == "slm-attempt1" else ""),
                "testes": int(r["suite_size"]) if r["has_suite"] else 0,
                "AC aprovado": ("sim" if r["ac_approved"] else "não") if r["has_suite"] else "—",
                "WAs detectados (AC)": f"{int(r['wa_corrected'])}/{int(r['n_wa'])}",
                "mutantes detectados (AC)": f"{int(r['mutants_corrected'])}/{int(r['n_mutants'])}",
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    order = {s: i for i, s in enumerate(config.SETS)}
    scen = {s: i for i, s in enumerate(config.SCENARIOS)}
    return out.sort_values(
        ["set", "scenario"], key=lambda c: c.map(order if c.name == "set" else scen)
    ).reset_index(drop=True)


def problem_info(root: Path, problem: str) -> dict:
    """Metadata, statement and AC of a problem (empty strings when the dataset is not extracted)."""
    folder = Path(root) / "data" / "dataset" / "problems" / problem
    metadata = _read_json(folder / "metadata.json") or {}

    def text(name: str) -> str:
        try:
            return (folder / name).read_text(encoding="utf-8")
        except OSError:
            return ""

    return {
        "name": metadata.get("name", problem),
        "rating": metadata.get("cf_rating"),
        "macrocategoria": metadata.get("macrocategoria", ""),
        "tags": metadata.get("cf_tags", []),
        "time_limit_seconds": metadata.get("time_limit_seconds"),
        "statement": text("enunciado.md"),
        "ac": text("AC_ref.cpp"),
        "url": (
            f"https://codeforces.com/problemset/problem/{metadata['cf_contest_id']}/"
            f"{metadata['cf_index']}"
            if metadata.get("cf_contest_id") and metadata.get("cf_index")
            else ""
        ),
    }


# ------------------------------------------------------------------------------------- IIC sets
# The IIC compares the WAs a set detected in each scenario (metrics.iic): R = black box (only the
# requirement), C = white box (only the code), H = hybrid. IIC + código = hybrid over R; IIC +
# requisito = hybrid over C. Each element is a pair (problem, WA); the pairs are counted over
# every problem of the cut, so the scenario filter does not apply here.

IIC_BASE = {"cod": "black_box", "req": "white_box"}
IIC_LETTER = {"black_box": "R", "white_box": "C", "hybrid": "H"}
IIC_REGIONS = (  # the 8 regions of the three sets, as (in R, in C, in H)
    ("só R (só caixa-preta)", (True, False, False)),
    ("só C (só caixa-branca)", (False, True, False)),
    ("só H (só híbrido)", (False, False, True)),
    ("R e C, não H", (True, True, False)),
    ("R e H, não C", (True, False, True)),
    ("C e H, não R", (False, True, True)),
    ("R, C e H", (True, True, True)),
    ("nenhum", (False, False, False)),
)


def iic_wa_table(frame: pd.DataFrame, set_name: str, oracle: str = "corrected") -> pd.DataFrame:
    """One row per (problem, WA) of ``set_name`` in the cut: ``R``, ``C``, ``H`` (detected in that
    scenario by ``oracle``). A combination without a suite detects nothing."""
    mine = frame[(frame["set"] == set_name) & (frame["kind"] == "wa")]
    if mine.empty:
        return pd.DataFrame(columns=["problem", "target", "R", "C", "H"])
    wide = mine.pivot_table(
        index=["problem", "target"], columns="scenario", values=oracle, aggfunc="any"
    )
    out = pd.DataFrame(index=wide.index)
    for scenario, letter in IIC_LETTER.items():
        column = wide[scenario] if scenario in wide else pd.Series(False, index=wide.index)
        out[letter] = column.fillna(False).astype(bool)
    return _target_order(out.reset_index()).reset_index(drop=True)


def iic_regions(was: pd.DataFrame) -> pd.DataFrame:
    """How many pairs fall in each of the 8 regions of R, C and H."""
    rows = []
    for label, (r, c, h) in IIC_REGIONS:
        mask = (was["R"] == r) & (was["C"] == c) & (was["H"] == h)
        rows.append({"região": label, "WAs (pares problema, WA)": int(mask.sum())})
    return pd.DataFrame(rows)


def iic_terms(was: pd.DataFrame, direction: str) -> dict:
    r"""The terms of the formula: |H \ B|, |B \ H|, |B| and the IIC (NaN when B is empty)."""
    base = IIC_LETTER[IIC_BASE[direction]]
    gains = int((was["H"] & ~was[base]).sum())
    losses = int((was[base] & ~was["H"]).sum())
    size = int(was[base].sum())
    value = 100 * (gains - losses) / size if size else float("nan")
    return {"base": base, "gains": gains, "losses": losses, "base_size": size, "iic": value}


def iic_role(was: pd.DataFrame, direction: str) -> pd.Series:
    """The part each WA plays in the IIC of ``direction``."""
    base = was[IIC_LETTER[IIC_BASE[direction]]]
    hybrid = was["H"]
    role = pd.Series("nenhum dos dois", index=was.index)
    role[hybrid & ~base] = "ganho (só o híbrido)"
    role[base & ~hybrid] = "perda (só a base)"
    role[base & hybrid] = "os dois"
    return role


def iic_by_problem(was: pd.DataFrame, direction: str) -> pd.DataFrame:
    """Per problem: |B|, gains, losses, both and the IIC of the problem (empty base: excluded)."""
    rows = []
    for problem, group in was.groupby("problem", sort=True):
        terms = iic_terms(group, direction)
        role = iic_role(group, direction)
        rows.append(
            {
                "problem": problem,
                f"|{terms['base']}| (base)": terms["base_size"],
                "ganhos": terms["gains"],
                "perdas": terms["losses"],
                "os dois": int((role == "os dois").sum()),
                "IIC do problema (%)": round(terms["iic"], 2) if terms["base_size"] else None,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_weight"] = (out["ganhos"] - out["perdas"]).abs()
    return (
        out.sort_values(["_weight", "problem"], ascending=[False, True])
        .drop(columns="_weight")
        .reset_index(drop=True)
    )


def iic_term_regions(direction: str) -> dict[str, list[str]]:
    """Which of the 8 regions add up to each term, so the formula can be done by hand."""
    base = IIC_LETTER[IIC_BASE[direction]]
    position = {"R": 0, "C": 1, "H": 2}[base]
    out = {"gains": [], "losses": [], "base_size": []}
    for label, flags in IIC_REGIONS:
        in_base, in_hybrid = flags[position], flags[2]
        if in_hybrid and not in_base:
            out["gains"].append(label)
        if in_base and not in_hybrid:
            out["losses"].append(label)
        if in_base:
            out["base_size"].append(label)
    return out
