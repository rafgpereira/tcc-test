"""Cost, the tables with cuts, compute/package/verify and the figures (T017–T026)."""

import hashlib
import json
import math
import zipfile

import pytest

import metrics.__main__ as cli
from metrics import config, cost, figures, sources, tables


def test_cost_comes_from_the_reports_and_the_local_model_is_never_in_dollars(repo):
    per, _ = sources.load(repo)
    attempt = repo / "data/suites/slm/problems/2_B/white_box/attempt_1.generation.json"
    record = json.loads(attempt.read_text())
    record["ollama"] = {"prompt_eval_count": 7, "eval_count": 3, "total_duration_ns": 2_000_000_000}
    attempt.write_text(json.dumps(record))
    barred = repo / "data/suites/gemini/barred/1_A/black_box/1.json"
    barred.parent.mkdir(parents=True)
    barred.write_text(json.dumps({"cost_usd": 0.05, "latency_s": 4.0}))
    t = cost.table(repo, per).set_index(["set", "scenario"])
    gemini = t.loc[("gemini", "black_box")]
    assert gemini["cost_usd"] == pytest.approx(0.5 + 0.05)  # barred answers count (FR-009)
    assert gemini["duration_s"] == pytest.approx(4.0)
    gpt = t.loc[("gpt", "black_box")]
    assert gpt["cost_usd"] == pytest.approx(1.0)
    detected = per[(per["set"] == "gpt") & (per["scenario"] == "black_box")]["wa_declared"].sum()
    assert gpt["cpd_wa_declared"] == pytest.approx(1.0 / detected)
    assert gpt["input_tokens"] == 110
    assert t["cost_usd"].loc[["gpt", "gemini", "claude"]].sum() == pytest.approx(
        3 + 1.5 + 0.3 + 0.05
    )
    for set_name in ("slm", "slm-attempt1"):
        local = t.loc[(set_name, "white_box")]
        assert math.isnan(local["cost_usd"]) and math.isnan(local["cpd_wa_declared"])
        assert (local["input_tokens"], local["output_tokens"], local["duration_s"]) == (7, 3, 2.0)


def test_metrics_table_has_the_cuts(repo):
    built = tables.build(repo)
    m = built["metrics"]
    assert set(m["cut"]) == {"all", "status"} or set(m["cut"]) >= {"all"}
    assert tuple(m.columns) == tables.METRICS_COLUMNS
    assert (m[m["cut"] == "all"]["problems"] == 2).all()


def test_compute_is_atomic_deterministic_and_gated(repo, monkeypatch):
    monkeypatch.setattr(cli, "_run_gate", lambda root: ["not complete"])
    assert cli.main(["compute"]) == 1 and not (repo / "data/metrics").exists()
    monkeypatch.setattr(cli, "_run_gate", lambda root: [])
    assert cli.main(["compute"]) == 0
    folder = repo / "data/metrics"
    first = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()
    }
    assert set(first) == set(config.TABLES.values()) | {"run.json"}
    assert cli.main(["compute"]) == 0
    second = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()
    }
    assert first == second
    loaded = tables.read(repo)
    assert list(loaded["metrics"].columns) == list(tables.METRICS_COLUMNS)


def test_figures_package_and_verify(repo, monkeypatch):
    monkeypatch.setattr(cli, "_run_gate", lambda root: [])
    assert cli.main(["package"]) == 1  # tables missing
    assert cli.main(["compute"]) == 0
    assert cli.main(["figures"]) == 0
    assert cli.main(["figures", "--figure", "tdf_by_model", "--macrocategoria", "matematica"]) == 2
    assert cli.main(["figures", "--set", "gpt", "--set", "claude"]) == 0
    assert (repo / "data/metrics/figures/tdf_by_model__set-claude+gpt.png").is_file()
    assert cli.main(["package"]) == 0
    with zipfile.ZipFile(repo / config.METRICS_ZIP) as archive:  # no figure is packaged
        assert not [n for n in archive.namelist() if "/figures/" in n]
    zip_hash = hashlib.sha256((repo / config.METRICS_ZIP).read_bytes()).hexdigest()
    assert cli.main(["package"]) == 0
    assert hashlib.sha256((repo / config.METRICS_ZIP).read_bytes()).hexdigest() == zip_hash
    assert cli.main(["verify"]) == 0
    assert cli.main(["verify", "--extracted", "data/metrics"]) == 0
    (repo / "data/metrics/metrics.csv").write_text("changed")
    assert cli.main(["verify", "--extracted", "data/metrics"]) == 1


def test_render_is_deterministic_and_names_the_filters(repo, monkeypatch):
    monkeypatch.setattr(cli, "_run_gate", lambda root: [])
    assert cli.main(["compute"]) == 0
    loaded = tables.read(repo)
    filters = {"sets": ["gpt", "gemini"], "scenarios": ["hybrid", "black_box"]}
    for name in figures.FIGURES:
        for fmt in figures.PACKAGED_FORMATS:  # the packaged formats are the same bytes
            a = figures.render(name, loaded, filters, fmt, "fonte-x")
            b = figures.render(name, loaded, filters, fmt, "fonte-x")
            assert a == b
    pdf = figures.render("tfp_by_cause", loaded, filters, "pdf", "fonte-x")[1]
    assert pdf.startswith(b"%PDF")  # drawn the same, but never packaged (font order varies)
    file_name, _ = figures.render("tdf_by_model", loaded, filters, "pdf", "s")
    assert file_name == "tdf_by_model__set-gemini+gpt__scenario-black_box+hybrid.pdf"
    assert "set = gemini, gpt" in figures.footer(filters, "s")
    # the cost exists per set × scenario: a problem filter keeps the all-problems value and says so
    by_status = {"statuses": ["accepted"]}
    assert figures.render("cost_per_detection", loaded, by_status, "png", "s")[1]
    whole = figures.figure_data("cost_per_detection", loaded, {})
    assert figures.figure_data("cost_per_detection", loaded, by_status).equals(whole)
    subtitle = figures.title("cost_per_detection", loaded, by_status).subtitle
    assert "o custo não se divide por problema" in subtitle
