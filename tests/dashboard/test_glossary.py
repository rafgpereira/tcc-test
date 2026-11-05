"""Every column shown has a full explanation on hover; abbreviations get their full name."""

from dashboard import data, glossary


def test_every_column_shown_has_an_explanation(evaluated):
    root, base = evaluated
    table = data.combinations(base, root).table
    frames = [
        data.overview(table),
        data.per_problem(table),
        data.oracle_gap(table),
        data.local_vs_commercial(table),
        data.combination_tests(base, "gemini", "1_A", "black_box", root).tests,
    ]
    missing = {c for f in frames for c in f.columns if glossary.column_help(str(c)) is None}
    assert missing == set()


def test_set_columns_of_the_comparison_are_explained():
    label, text = glossary.column_help("slm-attempt1 corr")
    assert label == "slm-attempt1 corr" and "1ª tentativa" in text and "gabarito do AC" in text


def test_abbr_wraps_known_abbreviations_only():
    out = glossary.abbr("AC reprovado; WA_3 e TLE; TDF e MS; decl × corr")
    assert '<abbr title="Accepted' in out
    assert "Time Limit Exceeded" in out and "Taxa de Detecção de Falhas" in out
    assert "WA_3" in out and '">WA</abbr>_3' not in out  # identifiers are left alone
    assert "oráculo declarado" in out and "oráculo corrigido" in out
    assert glossary.abbr("ACCEPTED e slm-attempt1") == "ACCEPTED e slm-attempt1"


def test_glossary_values_cover_the_filters():
    for value in ("slm-attempt1", "black_box", "accepted_predicted", "discarded_manual"):
        assert value in glossary.VALUES
