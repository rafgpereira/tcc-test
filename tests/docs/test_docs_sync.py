"""Tests for scripts/check_docs_sync.py (T019; Constitution, Principle XI).

Every test builds a small repository in ``tmp_path`` (no dependence on the real one) with a fake
CLI, loads the script with ``importlib`` (``scripts/`` is not a package) and calls ``main``.
"""

import importlib.util
import json
import re
import sys
import textwrap
from pathlib import Path

import pytest

SECTIONS = [
    "(a) Propósito",
    "(b) Como executar",
    "(c) Entradas esperadas",
    "(d) Saídas produzidas",
    "(e) Dependências e pré-requisitos",
    "(f) Limitações conhecidas",
]
ROW_PENDING = ("pendente", "—")


@pytest.fixture(scope="module")
def sync(repo_root):
    path = repo_root / "scripts" / "check_docs_sync.py"
    spec = importlib.util.spec_from_file_location("check_docs_sync", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- builders


def module_readme(
    status="em implementação",
    purpose="Faz uma coisa útil para o experimento.",
    commands=("alpha",),
    rows=None,
    sections=SECTIONS,
    with_table=True,
    extra="",
):
    fence = "```"
    cmd_block = "\n".join(f"docker compose run --rm app python -m dataset {c}" for c in commands)
    bodies = {
        "(a) Propósito": purpose,
        "(b) Como executar": f"{fence}bash\n{cmd_block}\n{fence}\n{extra}",
        "(c) Entradas esperadas": "Nenhuma.",
        "(d) Saídas produzidas": "Nenhuma.",
        "(e) Dependências e pré-requisitos": "Nenhuma.",
        "(f) Limitações conhecidas": "Nenhuma.",
    }
    parts = [
        "# Módulo",
        "",
        f"> **Status**: {status} · **Feature**:",
        "> `specs/001-x/` · **Metodologia**: `docs/metodologia-referencia.md`, seção 1",
        "",
    ]
    for name in sections:
        parts += [f"## {name}", "", bodies[name], ""]
    if with_table:
        rows = rows if rows is not None else [(f"`{c}`",) + ROW_PENDING for c in commands]
        parts += ["## Comandos verificados", "", "| Comando | Verificado em | Revisão |"]
        parts += ["|---|---|---|"]
        parts += ["| " + " | ".join(r) + " |" for r in rows]
        parts += [""]
    return "\n".join(parts)


def root_readme(
    date="2026-09-19",
    phrase="a feature está em andamento.",
    dataset_cell=None,
    sandbox_cell="[README](src/sandbox/README.md)",
    extra="",
    reference=None,
):
    if reference is None:
        reference = (
            "## Referência de comandos\n\n"
            "| Comando | O que faz |\n|---|---|\n"
            "| `python -m dataset alpha` | a |\n| `python -m dataset beta` | b |\n"
        )
    dataset_cell = dataset_cell or "[README](src/dataset/README.md)"
    template = textwrap.dedent("""\
        # Projeto

        > **Estado atual (@DATE@)**: @PHRASE@

        ## Módulos e estado

        | Módulo | Papel | Metodologia | Estado | README do módulo |
        |---|---|---|---|---|
        | `src/dataset/` | dados | seção 1 | ok | @DATASET@ |
        | `src/sandbox/` | motor | seção 4 | ok | @SANDBOX@ |
        | `src/mutation/` | mutantes | seção 2 | sem spec | a criar |

        @EXTRA@

        @REFERENCE@
        """)
    for key, value in {
        "@DATE@": date,
        "@PHRASE@": phrase,
        "@DATASET@": dataset_cell,
        "@SANDBOX@": sandbox_cell,
        "@EXTRA@": extra,
        "@REFERENCE@": reference,
    }.items():
        template = template.replace(key, value)
    return template


def methodology(dates=("2026-09-18", "2026-09-19"), extra=""):
    rows = "\n".join(f"| {d} | mudança | 1 |" for d in dates)
    return (
        "# Metodologia\n\n> legenda **[PROPOSTA]** em citação\n\n## 1. Dataset\n\n"
        "Termo alpha needle e o termo beta\nneedle quebrado em duas linhas.\n\n"
        f"{extra}\n## 8. Histórico de atualizações deste documento\n\n"
        f"| Data | O que mudou | Seções |\n|---|---|---|\n{rows}\n"
    )


SPEC = (
    "# Spec\n\n## Divergências e Decisões sobre a Metodologia\n\n"
    "- **D1 — Primeira (confirmado)**: texto.\n- **D2 — Segunda**: texto.\n"
)
FAKE_CLI = "print('usage: fake [-h] {alpha,beta} ...')\n"


def matrix(rows=None):
    rows = (
        rows
        if rows is not None
        else [
            {
                "id": "D1",
                "source": "spec.md#D1",
                "methodology_section": "1",
                "needles": ["alpha needle"],
            },
            {
                "id": "D2",
                "source": "spec.md#D2",
                "methodology_section": "1",
                "needles": ["beta needle"],
            },
        ]
    )
    return json.dumps({"schema_version": 1, "rows": rows})


def make_repo(root: Path, **kw):
    """A valid repository; keyword arguments replace individual documents."""
    files = {
        "README.md": kw.get("root_readme", root_readme()),
        "docs/metodologia-referencia.md": kw.get("methodology", methodology()),
        "specs/001-dataset-extraction/spec.md": kw.get("spec", SPEC),
        "specs/001-dataset-extraction/sync-matrix.json": kw.get("matrix", matrix()),
        "src/dataset/README.md": kw.get(
            "dataset_readme", module_readme(commands=("alpha", "beta"))
        ),
        "src/sandbox/README.md": kw.get("sandbox_readme", module_readme(commands=("alpha",))),
        "fake_cli.py": FAKE_CLI,
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if content is not None:
            path.write_text(content, encoding="utf-8")
    return root


STAMP = ("2026-09-20", "a1b2c3d")


def make_closed_repo(root: Path, **kw):
    """A repository that also satisfies --closing (implemented modules, every command stamped)."""
    dataset = module_readme(
        status="implementado",
        commands=("alpha", "beta"),
        rows=[("`alpha`", *STAMP), ("`beta`", *STAMP)],
    )
    sandbox = module_readme(status="implementado", rows=[("`alpha`", *STAMP)])
    return make_repo(root, dataset_readme=dataset, sandbox_readme=sandbox, **kw)


def run(sync, root, *extra):
    argv = ["--root", str(root), "--cli", f"{sys.executable} {root / 'fake_cli.py'}", *extra]
    return sync.main(argv)


# --------------------------------------------------------------------------- baseline


def test_a_consistent_repository_passes_every_check(sync, tmp_path):
    make_repo(tmp_path)
    assert run(sync, tmp_path) == 0


def test_closing_also_passes_on_a_consistent_repository(sync, tmp_path):
    make_closed_repo(tmp_path)
    assert run(sync, tmp_path, "--closing") == 0


def test_a_readme_built_from_the_real_template_skeleton_passes_c1_and_cv(sync, repo_root, tmp_path):
    template = (repo_root / "docs" / "template-modulo.md").read_text(encoding="utf-8")
    skeleton = re.search(r"````markdown\n(.*?)\n````", template, re.DOTALL).group(1)
    skeleton = skeleton.replace("<planejado | em implementação | implementado>", "em implementação")
    skeleton = re.sub(r"<Uma frase:[^>]*>", "Faz uma coisa.", skeleton)
    make_repo(tmp_path, sandbox_readme=skeleton)
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1,CV") == 0


# --------------------------------------------------------------------------- C1


def test_c1_missing_section_fails(sync, tmp_path, capsys):
    sections = [s for s in SECTIONS if not s.startswith("(c)")]
    make_repo(tmp_path, sandbox_readme=module_readme(sections=sections))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1") == 1
    out = capsys.readouterr().out
    assert "C1" in out and "(c)" in out and "src/sandbox/README.md" in out


def test_c1_out_of_order_sections_fail(sync, tmp_path):
    swapped = [SECTIONS[1], SECTIONS[0]] + SECTIONS[2:]
    make_repo(tmp_path, sandbox_readme=module_readme(sections=swapped))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1") == 1


def test_c1_purpose_with_more_than_one_sentence_fails(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=module_readme(purpose="Faz uma coisa. Faz outra coisa."))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1") == 1


def test_c1_purpose_with_abbreviations_and_versions_is_one_sentence(sync, tmp_path):
    purpose = "Compila com GCC 13.2.0 (ex.: gnu++20) e executa `a.out` sob limites."
    make_repo(tmp_path, sandbox_readme=module_readme(purpose=purpose))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1") == 0


def test_c1_empty_purpose_fails(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=module_readme(purpose=""))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1") == 1


def test_c1_missing_status_line_fails(sync, tmp_path):
    text = module_readme().replace("> **Status**: em implementação · **Feature**:", "> Feature:")
    make_repo(tmp_path, sandbox_readme=text)
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1") == 1


def test_c1_unknown_status_value_fails(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=module_readme(status="quase pronto"))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1") == 1


def test_c1_missing_module_readme_fails(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=None)
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C1") == 1


# --------------------------------------------------------------------------- C2


def test_c2_documented_subcommand_that_does_not_exist_fails(sync, tmp_path, capsys):
    make_repo(tmp_path, sandbox_readme=module_readme(commands=("alpha", "ghost")))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C2") == 1
    assert "ghost" in capsys.readouterr().out


def test_c2_owner_readme_must_document_every_cli_subcommand(sync, tmp_path, capsys):
    make_repo(tmp_path, dataset_readme=module_readme(commands=("alpha",)))
    assert run(sync, tmp_path, "--module", "src/dataset", "--only", "C2") == 1
    assert "beta" in capsys.readouterr().out


def test_c2_non_owner_module_need_not_document_the_whole_cli(sync, tmp_path):
    """src/sandbox documents only `selfcheck`-like commands and that is fine."""
    make_repo(tmp_path, sandbox_readme=module_readme(commands=("alpha",)))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C2") == 0


def test_c2_owner_is_configurable(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=module_readme(commands=("alpha",)))
    argv = ["--module", "src/sandbox", "--only", "C2", "--cli-owner", "src/sandbox"]
    assert run(sync, tmp_path, *argv) == 1  # sandbox now owns the CLI but lacks `beta`


def test_c2_help_flags_are_not_subcommands(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=module_readme(commands=("alpha", "--help")))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C2") == 0


def test_c2_cli_that_cannot_run_is_reported(sync, tmp_path):
    make_repo(tmp_path)
    argv = ["--root", str(tmp_path), "--cli", f"{sys.executable} {tmp_path / 'missing.py'}"]
    assert sync.main(argv + ["--module", "src/dataset", "--only", "C2"]) == 1


def test_c2_root_readme_command_reference_lists_every_cli_subcommand_and_passes(sync, tmp_path):
    make_repo(tmp_path)
    assert run(sync, tmp_path, "--only", "C2") == 0


def test_c2_root_readme_without_a_command_reference_fails(sync, tmp_path, capsys):
    make_repo(tmp_path, root_readme=root_readme(reference="no section here"))
    assert run(sync, tmp_path, "--only", "C2") == 1
    assert "Referência de comandos" in capsys.readouterr().out


def test_c2_root_readme_reference_must_list_every_cli_subcommand(sync, tmp_path, capsys):
    reference = "## Referência de comandos\n\n| `python -m dataset alpha` | a |\n"
    make_repo(tmp_path, root_readme=root_readme(reference=reference))
    assert run(sync, tmp_path, "--only", "C2") == 1
    out = capsys.readouterr().out
    assert "beta" in out and "README.md" in out


def test_c2_root_readme_reference_cannot_cite_a_subcommand_that_does_not_exist(
    sync, tmp_path, capsys
):
    reference = (
        "## Referência de comandos\n\n| `python -m dataset alpha` | a |\n"
        "| `python -m dataset beta` | b |\n| `python -m dataset ghost` | g |\n"
    )
    make_repo(tmp_path, root_readme=root_readme(reference=reference))
    assert run(sync, tmp_path, "--only", "C2") == 1
    assert "ghost" in capsys.readouterr().out


def test_c2_module_mode_does_not_check_the_root_readme_reference(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme(reference="no section here"))
    assert run(sync, tmp_path, "--module", "src/dataset", "--only", "C2") == 0


# --------------------------------------------------------------------------- C3


def test_c3_dangling_link_in_the_root_readme_fails(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme(extra="[x](docs/nao-existe.md)"))
    assert run(sync, tmp_path, "--only", "C3") == 1


def test_c3_dangling_link_in_docs_fails(sync, tmp_path):
    make_repo(tmp_path)
    (tmp_path / "docs" / "outro.md").write_text("[x](../sumiu.md)\n", encoding="utf-8")
    assert run(sync, tmp_path, "--only", "C3") == 1


def test_c3_dangling_link_in_a_module_readme_fails(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=module_readme(extra="[x](../../specs/nao-existe.md)"))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C3") == 1


def test_c3_ignores_http_anchors_and_fenced_blocks(sync, tmp_path):
    extra = "[a](https://example.com) [b](#secao) [c](docs/metodologia-referencia.md#1)\n"
    extra += "```\n[d](nao/existe.md)\n```\n"
    make_repo(tmp_path, root_readme=root_readme(extra=extra))
    assert run(sync, tmp_path, "--only", "C3") == 0


# --------------------------------------------------------------------------- C4


def test_c4_missing_estado_atual_line_fails(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme().replace("Estado atual", "Situação"))
    assert run(sync, tmp_path, "--only", "C4") == 1


def test_c4_estado_atual_older_than_the_newest_history_row_fails(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme(date="2026-09-18"))
    assert run(sync, tmp_path, "--only", "C4") == 1


def test_c4_estado_atual_equal_or_newer_than_history_passes(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme(date="2026-09-19"))
    assert run(sync, tmp_path, "--only", "C4") == 0
    make_repo(tmp_path, root_readme=root_readme(date="2026-12-01"))
    assert run(sync, tmp_path, "--only", "C4") == 0


def test_c4_row_link_to_a_missing_readme_fails(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme(dataset_cell="[README](src/dataset/LEIAME.md)"))
    assert run(sync, tmp_path, "--only", "C4") == 1


def test_c4_a_criar_row_with_an_existing_readme_fails(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme(dataset_cell="a criar na feature 001"))
    assert run(sync, tmp_path, "--only", "C4") == 1


def test_c4_a_criar_row_without_a_readme_passes(sync, tmp_path):
    make_repo(tmp_path)  # src/mutation/ row says "a criar" and has no README
    assert run(sync, tmp_path, "--only", "C4") == 0


@pytest.mark.parametrize("status", ["implementado", "em implementação"])
def test_c4_no_module_implemented_phrase_fails_when_a_module_is_underway(sync, tmp_path, status):
    phrase = "nenhum módulo está\nimplementado ainda."  # also across a line break
    make_repo(
        tmp_path,
        root_readme=root_readme(phrase=phrase),
        sandbox_readme=module_readme(status=status),
    )
    assert run(sync, tmp_path, "--only", "C4") == 1


def test_c4_no_module_implemented_phrase_passes_while_everything_is_planned(sync, tmp_path):
    make_repo(
        tmp_path,
        root_readme=root_readme(phrase="nenhum módulo está implementado ainda."),
        dataset_readme=module_readme(status="planejado", commands=("alpha", "beta")),
        sandbox_readme=module_readme(status="planejado"),
    )
    assert run(sync, tmp_path, "--only", "C4") == 0


# --------------------------------------------------------------------------- comandos verificados (CV)


def test_cv_missing_table_fails(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=module_readme(with_table=False))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV") == 1


def test_cv_pending_row_is_fine_while_the_module_is_under_implementation(sync, tmp_path):
    make_repo(tmp_path)
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV") == 0


def test_cv_pending_row_fails_when_the_module_is_implemented(sync, tmp_path):
    make_repo(tmp_path, sandbox_readme=module_readme(status="implementado"))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV") == 1


def test_cv_pending_row_fails_with_closing(sync, tmp_path):
    make_repo(tmp_path)
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV", "--closing") == 1


@pytest.mark.parametrize(
    "row",
    [
        ("`alpha`", "20/09/2026", "a1b2c3d"),  # wrong date format
        ("`alpha`", "2026-09-20", "XYZ"),  # wrong revision
        ("`alpha`", "2026-09-20", "a1b2c3"),  # revision too short
        ("`alpha`", "2026-09-20", "A1B2C3D"),  # uppercase revision
    ],
)
def test_cv_malformed_stamps_fail(sync, tmp_path, row):
    make_repo(tmp_path, sandbox_readme=module_readme(rows=[row]))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV") == 1


def test_cv_well_formed_stamps_pass(sync, tmp_path):
    rows = [("`alpha`", "2026-09-20", "a1b2c3d")]
    make_repo(tmp_path, sandbox_readme=module_readme(status="implementado", rows=rows))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV") == 0


def test_cv_dirty_revision_is_accepted_normally_and_rejected_when_closing(sync, tmp_path):
    rows = [("`alpha`", "2026-09-20", "a1b2c3d+dirty")]
    make_repo(tmp_path, sandbox_readme=module_readme(rows=rows))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV") == 0
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV", "--closing") == 1


def test_cv_every_documented_subcommand_must_be_listed_in_the_table(sync, tmp_path, capsys):
    rows = [("`alpha`",) + ROW_PENDING]
    make_repo(tmp_path, dataset_readme=module_readme(commands=("alpha", "beta"), rows=rows))
    assert run(sync, tmp_path, "--module", "src/dataset", "--only", "CV") == 1
    assert "beta" in capsys.readouterr().out


def test_cv_extra_rows_such_as_pytest_are_allowed(sync, tmp_path):
    rows = [("`alpha`",) + ROW_PENDING, ("`pytest tests/sandbox`",) + ROW_PENDING]
    make_repo(tmp_path, sandbox_readme=module_readme(rows=rows))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "CV") == 0


# --------------------------------------------------------------------------- C5


def test_c5_missing_matrix_row_fails_naming_the_id(sync, tmp_path, capsys):
    only_d1 = matrix(
        [{"id": "D1", "source": "s", "methodology_section": "1", "needles": ["alpha needle"]}]
    )
    make_repo(tmp_path, matrix=only_d1)
    assert run(sync, tmp_path, "--only", "C5") == 1
    out = capsys.readouterr().out
    assert "C5" in out and "D2" in out


def test_c5_missing_needle_fails_naming_the_id(sync, tmp_path, capsys):
    rows = [
        {"id": "D1", "source": "s", "methodology_section": "1", "needles": ["alpha needle"]},
        {"id": "D2", "source": "s", "methodology_section": "1", "needles": ["nao aparece"]},
    ]
    make_repo(tmp_path, matrix=matrix(rows))
    assert run(sync, tmp_path, "--only", "C5") == 1
    out = capsys.readouterr().out
    assert "D2" in out and "nao aparece" in out


def test_c5_needles_match_after_collapsing_whitespace(sync, tmp_path):
    """`beta needle` is split across two lines in the methodology fixture."""
    make_repo(tmp_path)
    assert run(sync, tmp_path, "--only", "C5") == 0


def test_c5_row_for_a_decision_that_no_longer_exists_fails(sync, tmp_path, capsys):
    rows = json.loads(matrix())["rows"] + [
        {"id": "D9", "source": "s", "methodology_section": "1", "needles": ["alpha needle"]}
    ]
    make_repo(tmp_path, matrix=matrix(rows))
    assert run(sync, tmp_path, "--only", "C5") == 1
    assert "D9" in capsys.readouterr().out


def test_c5_missing_matrix_file_fails(sync, tmp_path):
    make_repo(tmp_path, matrix=None)
    assert run(sync, tmp_path, "--only", "C5") == 1


@pytest.mark.parametrize(
    "bad",
    [
        json.dumps({"schema_version": 2, "rows": []}),
        json.dumps({"schema_version": 1, "rows": [{"id": "D1", "needles": []}]}),
        "not json",
    ],
)
def test_c5_invalid_matrix_fails(sync, tmp_path, bad):
    make_repo(tmp_path, matrix=bad)
    assert run(sync, tmp_path, "--only", "C5") == 1


# --------------------------------------------------------------------------- C6


def test_c6_active_proposta_tag_fails_when_closing(sync, tmp_path):
    make_repo(tmp_path, methodology=methodology(extra="- **[PROPOSTA]** regra ativa\n"))
    assert run(sync, tmp_path, "--only", "C6") == 1


def test_c6_is_not_part_of_the_default_run_but_is_part_of_closing(sync, tmp_path):
    make_closed_repo(tmp_path, methodology=methodology(extra="- **[PROPOSTA]** regra ativa\n"))
    assert run(sync, tmp_path) == 0
    assert run(sync, tmp_path, "--closing") == 1


def test_c6_ignores_blockquote_legend_lines(sync, tmp_path):
    make_repo(tmp_path)  # the fixture already has a blockquote legend with [PROPOSTA]
    assert run(sync, tmp_path, "--only", "C6") == 0


def test_c6_ignores_single_line_struck_through_tags(sync, tmp_path):
    extra = "4. ~~**[PROPOSTA]** já resolvida~~ — **RESOLVIDO**\n"
    make_repo(tmp_path, methodology=methodology(extra=extra))
    assert run(sync, tmp_path, "--only", "C6") == 0


def test_c6_ignores_multi_line_struck_through_tags(sync, tmp_path):
    extra = "5. ~~**[PROPOSTA]** já resolvida em\n   duas linhas~~ — **RESOLVIDO**\n"
    make_repo(tmp_path, methodology=methodology(extra=extra))
    assert run(sync, tmp_path, "--only", "C6") == 0


def test_c6_an_active_tag_after_struck_through_text_still_fails(sync, tmp_path):
    extra = "4. ~~**[PROPOSTA]** resolvida~~\n6. **[PROPOSTA — aguardando confirmação]** ativa\n"
    make_repo(tmp_path, methodology=methodology(extra=extra))
    assert run(sync, tmp_path, "--only", "C6") == 1


def test_c6_reports_the_line_of_the_active_tag(sync, tmp_path, capsys):
    make_repo(tmp_path, methodology=methodology(extra="- **[PROPOSTA]** ativa\n"))
    run(sync, tmp_path, "--only", "C6")
    assert re.search(r"metodologia-referencia\.md:\d+", capsys.readouterr().out)


# --------------------------------------------------------------------------- C7


def test_c7_clean_readmes_pass(sync, tmp_path):
    make_repo(tmp_path)
    assert run(sync, tmp_path, "--only", "C7") == 0


def test_c7_a_task_id_in_a_module_readme_fails(sync, tmp_path):
    dataset = module_readme(commands=("alpha",), extra="Veja a tarefa T093 para mais detalhes.\n")
    make_repo(tmp_path, dataset_readme=dataset)
    assert run(sync, tmp_path, "--only", "C7") == 1


def test_c7_a_task_id_in_the_root_readme_fails(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme(extra="Carimbado na tarefa T035.\n"))
    assert run(sync, tmp_path, "--only", "C7") == 1


def test_c7_is_skipped_for_the_root_readme_in_module_mode(sync, tmp_path):
    """--module checks only that module's README, never the root one."""
    make_repo(tmp_path, root_readme=root_readme(extra="Carimbado na tarefa T035.\n"))
    assert run(sync, tmp_path, "--module", "src/sandbox", "--only", "C7") == 0


def test_c7_runs_by_default_in_module_mode(sync, tmp_path):
    dataset = module_readme(commands=("alpha",), extra="Achado na tarefa T093.\n")
    make_repo(tmp_path, dataset_readme=dataset)
    assert run(sync, tmp_path, "--module", "src/dataset") == 1


def test_c7_the_methodology_is_exempt(sync, tmp_path):
    """D-numbers, dates and task ids are expected citation apparatus in the methodology."""
    make_repo(tmp_path, methodology=methodology(extra="Medido na tarefa T035.\n"))
    assert run(sync, tmp_path, "--only", "C7") == 0


def test_c7_reports_the_readme_and_line(sync, tmp_path, capsys):
    dataset = module_readme(commands=("alpha",), extra="Veja a tarefa T093.\n")
    make_repo(tmp_path, dataset_readme=dataset)
    run(sync, tmp_path, "--only", "C7")
    out = capsys.readouterr().out
    assert "T093" in out
    assert re.search(r"src/dataset/README\.md:\d+", out)


# --------------------------------------------------------------------------- selection and exit codes


def test_module_option_runs_only_the_module_checks_by_default(sync, tmp_path):
    """C4 and C5 are broken on purpose; explicit --module must not run them."""
    make_repo(tmp_path, root_readme=root_readme(date="1999-01-01"), matrix=None)
    assert run(sync, tmp_path, "--module", "src/sandbox") == 0


def test_without_module_option_the_repository_checks_run(sync, tmp_path):
    make_repo(tmp_path, root_readme=root_readme(date="1999-01-01"))
    assert run(sync, tmp_path) == 1


def test_only_runs_exactly_the_requested_checks(sync, tmp_path, capsys):
    make_repo(tmp_path, root_readme=root_readme(date="1999-01-01"), matrix=None)
    assert run(sync, tmp_path, "--only", "C3") == 0
    assert run(sync, tmp_path, "--only", "C4,C5") == 1
    out = capsys.readouterr().out
    assert "C4" in out and "C5" in out


def test_unknown_check_id_is_a_usage_error(sync, tmp_path):
    make_repo(tmp_path)
    assert run(sync, tmp_path, "--only", "C9") == 2


def test_missing_root_is_a_usage_error(sync, tmp_path):
    assert sync.main(["--root", str(tmp_path / "nope")]) == 2


def test_default_modules_are_every_src_readme(sync, tmp_path):
    """Without --module the two module READMEs are both checked."""
    make_repo(tmp_path, sandbox_readme=module_readme(purpose="Uma. Duas."))
    assert run(sync, tmp_path, "--only", "C1") == 1


def test_output_names_check_file_and_message(sync, tmp_path, capsys):
    make_repo(tmp_path, sandbox_readme=module_readme(purpose=""))
    run(sync, tmp_path, "--only", "C1")
    line = next(l for l in capsys.readouterr().out.splitlines() if "C1" in l)
    assert "src/sandbox/README.md" in line
