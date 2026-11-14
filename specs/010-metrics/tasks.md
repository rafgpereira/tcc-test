# Tasks: Métricas de avaliação

**Input**: Design documents from `/specs/010-metrics/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md),
[contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md); Constitution **v1.9.0**

**Tests**: INCLUÍDOS. O Princípio VI cita o cálculo de métricas pelo nome: nenhuma métrica está
pronta sem teste de casos conhecidos. Os testes vêm antes da implementação em cada história.

**Organization**:
- base: dependências, pacote, leitura do `results.csv` (tabela por problema e WAs detectados),
  cortes, portão;
- US1 (P1): TDF, MS, TFP, TC, IIC;
- US2 (P1): TDF\*, MS\*, Δ_oráculo, TFP por teste e por causa;
- US3 (P1): testes estatísticos e cortes nas tabelas;
- US4 (P2): custo e densidade;
- US5 (P2): `compute` (as tabelas), pacote, `verify`, metodologia, dashboard;
- US6 (P3): figuras (comando e dashboard);
- por fim: documentação, execução real e fechamento.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: arquivos diferentes, sem dependência de tarefa incompleta
- **[Story]**: US1 a US6, só nas fases de história
- **Onde rodar**: `pytest` no `sandbox`; os comandos no `app`

## Regras que valem para TODAS as tarefas

- **📌 PROPAGAR**: decisão nova ou dado medido vai, na própria tarefa, para
  `docs/metodologia-referencia.md` e para `spec.md`/`plan.md`/`research.md`.
- **Toda conta mora em `src/metrics/`**; o dashboard só chama as funções públicas
  (contracts/api.md).
- **Modelo local nunca em US$** (FR-009).
- **O agente não commita**; comando novo nasce `pendente` em "Comandos verificados".

---

## Phase 1: Setup

- [X] T001 Add `scipy` and `matplotlib` to `pyproject.toml` and `uv.lock` (`docker compose run --rm -e UV_CACHE_DIR=/tmp/uv -v ./uv.lock:/app/uv.lock app uv add --no-sync scipy matplotlib`), check that no existing pin changed, then `docker compose build`; record the pinned versions in `specs/010-metrics/research.md` R3/R7
- [X] T002 [P] Create `src/metrics/__init__.py`, `src/metrics/config.py` (`SETS`, `SCENARIOS` in canonical order, `ALPHA = 0.05`, `METRICS_DIR = Path("data/metrics")`, `FIGURES_DIR`, file names of data-model.md, `WA_PER_PROBLEM = 100`, `MUTANTS_PER_PROBLEM = 100`) and `src/metrics/__main__.py` (subcommands `compute`, `figures`, `package`, `verify` as stubs)
- [X] T003 [P] Create `tests/metrics/conftest.py` with builders of small `per_problem` and `detected_wa` tables (3 problems, 2 sets, 3 scenarios, known values; one `discarded_manual` combination) and of a minimal repository with `results.csv` files built by `evaluation.report.results_csv` from fake `CombinationResult`s (reuse `tests/dashboard/conftest.py::build_evaluated`)

---

## Phase 2: Foundational

- [X] T004 [P] Write `tests/metrics/test_sources.py`: `sources.load` builds `per_problem.csv` with exactly the columns of data-model.md (in order), one row per set × scenario × problem; a combination without suite has `has_suite=false`, zero counts and `n_wa = n_mutants = 100`; `wa_declared` sums equal `evaluation.report` `detected.declared_wa`; `detected_wa` has one row per detected WA per oracle; `macrocategoria` from `metadata.json`
- [X] T005 Implement `src/metrics/sources.py` (`load(root, evaluation_dir)`, reading `data/evaluation/<set>/results.csv`) (makes T004 pass)
- [X] T006 [P] Write `tests/metrics/test_cuts.py`: empty lists filter nothing; `macrocategorias`, `statuses`, `sets`, `scenarios`; a cut that leaves one problem raises (FR-017: never one problem)
- [X] T007 Implement `src/metrics/cuts.py` (`apply`) (makes T006 pass)
- [X] T008 [P] Write `tests/metrics/test_gate.py` and implement `src/metrics/gate.py`: `cli check --deep --only dataset,slm_suites,gpt_suites,gemini_suites,claude_suites,evaluation_*` must pass and every `manifests/evaluation_<set>_report.json` must say `complete`; otherwise nothing is computed (FR-002)

---

## Phase 3: User Story 1 - Métricas primárias (Priority: P1) 🎯 MVP

**Independent Test**: com as tabelas pequenas de T003, cada métrica bate com a conta à mão

- [X] T009 [P] [US1] Write `tests/metrics/test_primary.py::test_tdf_ms_tfp_tc`: "MS com DM=0 e M=100 deve retornar 0.0"; TDF of 3 problems with 10, 50, 90 WAs = 50.0; a `discarded_manual` combination counts 0% in TDF and MS; TFP with N = problems of the cut, plus `TFP_with_suite` and `without_suite`; TC = with-suite ÷ problems × 100
- [X] T010 [US1] Implement TDF, MS, TFP, `TFP_with_suite`, `without_suite`, TC in `src/metrics/primary.py::table` (rows of `metrics.csv`) (makes T009 pass)
- [X] T011 [P] [US1] Write `tests/metrics/test_iic.py`: IIC_cod and IIC_req pooled from small sets (gains − losses) ÷ |base| × 100; a problem with empty base is excluded from the per-problem view and counted in `excluded`; IIC > 100% allowed; median, q1, q3, positive/negative/zero; both oracles (`declared`, `corrected`)
- [X] T012 [US1] Implement `src/metrics/iic.py::table` (rows of `iic.csv`) (makes T011 pass)

---

## Phase 4: User Story 2 - Oráculo corrigido e causas (Priority: P1)

**Independent Test**: sem AC reprovado, TDF = TDF\*; com AC reprovado por saída diferente, Δ > 0 e causa `oráculo`

- [X] T013 [P] [US2] Write `tests/metrics/test_primary.py::test_corrected_and_causes`: `TDF_star`, `MS_star`, `delta_TDF`, `delta_MS`; `TFP_test = (FP_tests_oracle + FP_tests_invalid_input) ÷ total_tests × 100`, with `ac_wrong_output_tests` → oracle and `ac_runtime_error_tests` → invalid input
- [X] T014 [US2] Add these columns to `src/metrics/primary.py::table` (makes T013 pass)

---

## Phase 5: User Story 3 - Estatística e cortes (Priority: P1)

**Independent Test**: dados construídos com diferença conhecida dão p < 0,05 e A12 coerente; sem diferença, p alto

- [X] T015 [P] [US3] Write `tests/metrics/test_stats.py`: A12 against hand counts (A12 = P(X>Y) + 0,5·P(X=Y); Cliff = 2·A12 − 1); Holm against the textbook example (p = 0,01, 0,04, 0,03 → 0,03, 0,06, 0,06 order-preserving); McNemar exact equals the two-sided binomial on discordant pairs; Friedman/Wilcoxon equal `scipy` directly; all pairs equal → p = 1, "sem diferença", no exception
- [X] T016 [US3] Implement `src/metrics/stats.py` (helpers and `table(per_problem)` with the families `scenarios`, `models`, `attempt1` of research R3, rows of `stats.csv`; post-hoc only when the Friedman p < α; TFP via McNemar) (makes T015 pass)
- [X] T017 [P] [US3] Write `tests/metrics/test_tables.py::test_cuts_in_metrics`: `metrics.csv` has `cut = all`, one block per `macrocategoria` value and per `status` value present, each with `problems`
- [X] T018 [US3] Implement the cut loop in `src/metrics/tables.py` (makes T017 pass)

---

## Phase 6: User Story 4 - Custo e densidade (Priority: P2)

**Independent Test**: o custo total de cada comercial bate com o relatório de geração

- [X] T019 [P] [US4] Write `tests/metrics/test_cost.py`: commercial cost and tokens per scenario from `cost_usd.by_group`/`tokens` of a small generation report; CPD = cost ÷ detected (both oracles); local model rows have empty `cost_usd` and `cpd_*` and the sum of tokens/duration of its attempts (only attempt 1 for `slm-attempt1`); `density_TDF = TDF ÷ mean_suite_size`
- [X] T020 [US4] Implement `src/metrics/cost.py::table` and `density_TDF`/`mean_suite_size` in `src/metrics/primary.py` (makes T019 pass)

---

## Phase 7: User Story 5 - Tabelas, pacote, metodologia e dashboard (Priority: P2)

**Independent Test**: `compute` duas vezes dá os mesmos bytes; o dashboard mostra os valores das tabelas

- [X] T021 [P] [US5] Write `tests/metrics/test_cli.py`: `compute` on the repository of T003 writes the 6 tables and `run.json` (columns of data-model.md) atomically; a second run gives identical bytes; gate failure → exit `1` and nothing written; `package` + `verify` (with and without `--extracted`) deterministic, codes `0/1/2`
- [X] T022 [US5] Implement `src/metrics/tables.py` (write/read with column validation), `compute` in `src/metrics/__main__.py`, and `src/metrics/packaging.py` (`data/metrics.zip`, `manifests/metrics.manifest.json`, `verify`) following `src/evaluation/packaging.py`; add `!data/metrics.zip` to `.gitignore` (makes T021 pass)
- [X] T023 [US5] Update `src/dashboard/views/metrics.py`: when `data/metrics/metrics.csv` exists, show `metrics.csv` (with `cut` selector), `iic.csv`, `stats.csv`, `cost.csv` via `views.common.table`; add the glossary entries of the new columns to `src/dashboard/glossary.py` (TDF\*, MS\*, Δ, TFP por teste, CPD, A12, Cliff, Holm, Friedman, Wilcoxon, McNemar); update `tests/dashboard/test_pages.py` and `tests/dashboard/test_glossary.py` (every column shown has an explanation)
- [X] T024 📌 PROPAGAR [US5] Rewrite section 5 of `docs/metodologia-referencia.md` (5.1–5.4 kept with B.2/B.3/B.4 rules; 5.5 complementares C.1–C.4; 5.6 estatística; 5.7 cortes; 5.8 figuras), add Q5 to section 0, the limitation "oráculo por execução × por predição" with the reason decided on 2026-11-09 to section 7, close pending items 3 and 26 in section 6; ask the authors before removing `docs/metricas-referencia.md` *(Concluída em 2026-11-14: seção 5 da metodologia consolidada, com a matriz de rastreabilidade do antigo `docs/metricas-referencia.md` na seção 5.10; o arquivo antigo foi removido/marcado como consolidado.)*

---

## Phase 8: User Story 6 - Figuras (Priority: P3)

**Independent Test**: a figura filtrada do comando e a do dashboard são idênticas; filtro no nome e no rodapé

- [X] T025 [P] [US6] Write `tests/metrics/test_figures.py`: each figure of `FIGURES` renders with and without filters; `render` twice gives identical bytes (PNG and PDF); the file name is `<figure>__<filter>-<value>...` and the footer text contains the filters and the source; a one-problem filter is refused
- [X] T026 [US6] Implement `src/metrics/figures.py` (`FIGURES`: `tdf_by_model`, `tdf_declared_vs_corrected`, `ms_declared_vs_corrected`, `tfp_by_cause`, `iic_distribution`, `cost_per_detection`; `render`; Agg backend; deterministic metadata) and `figures` in `src/metrics/__main__.py` with `--macrocategoria`, `--status`, `--set`, `--scenario`, `--format`, `--output-dir` (makes T025 pass)
- [X] T027 [US6] In `src/dashboard/views/metrics.py`, add the figure section: choose a figure, the filters (macrocategoria, status, conjuntos, cenários), draw with `metrics.figures.render` and offer "baixar PNG" and "baixar PDF" (same bytes as the command); test in `tests/dashboard/test_pages.py` that the downloaded bytes equal `render` with the same filters

---

## Phase 9: Documentação, execução e fechamento

- [X] T028 [P] Write `src/metrics/README.md` per `docs/template-modulo.md` (Cenário A: `compute`, `figures`, `package`, `verify`; Cenário B: `unzip data/metrics.zip -d data/` and `verify --extracted`; one command table; what each table means in plain language; no spec-kit citations); update `README.md` (module table, "Depois da preparação", "Referência de comandos", `Estado atual`) and `CLAUDE.md`
- [X] T029 [P] Create `specs/010-metrics/sync-matrix.json` with decision rows (add a "Divergências e Decisões" section with D1–D5 to `spec.md`: proposta sem C.5/C.6; TFP com N = 200 e visão com suíte; IIC agregado; estatística; figuras com filtros) and needles present in the methodology
- [X] T030 📌 PROPAGAR Run `docker compose run --rm app python -m metrics compute` on the real evaluation; check quickstart §3 (sums against `evaluation report`, cost against generation reports, 3 combinations by hand with the authors); record the main numbers (TDF, MS, TFP, TC, TDF\*, MS\*, IIC by set × scenario, significant comparisons) in the methodology, section 5, as **[MEDIDO]** *(Concluída: `compute` rodado em 2026-11-09; números na seção 5.9 da metodologia como **[MEDIDO]**.)*
- [ ] T031 Run `figures`, `package`, `verify --extracted data/metrics` and `scripts/check_docs_sync.py` (also `--feature specs/010-metrics`), `ruff`, `black`; stamp the commands in "Comandos verificados" after the authors commit; grep both READMEs for sentences still calling them pending *(`figures`, `package` e `verify` rodaram; os carimbos em "Comandos verificados" seguem em revisão `+dirty`/`pendente` até os autores commitarem e o comando ser rodado de novo.)*

---

## Dependencies & Execution Order

- Setup (T001–T003) → Base (T004–T008) → histórias.
- US1, US2, US4 dependem só da base; US2 estende `primary.py` (depois de T010); US3 depende de
  US1/US2 (usa os valores por problema e as colunas); US5 depende de US1–US4; US6 depende de US5
  (lê as tabelas) e do dashboard (T023).
- Fechamento: T028–T029 depois das histórias; T030 depois de T022; T031 por último.

### Parallel Opportunities

- T002 e T003; T004, T006, T008; os testes T009, T011, T013 (arquivos diferentes, exceto T009/T013
  no mesmo arquivo: em sequência), T015, T017, T019; T028 e T029.

## Implementation Strategy

### MVP (US1 + US2 + US3)

As métricas primárias, o oráculo corrigido e a estatística: é o que o capítulo de resultados
precisa. Validar com a conta à mão e contra o `evaluation report`.

### Depois

US4 (custo) → US5 (tabelas versionadas, metodologia, dashboard) → US6 (figuras) → fechamento.
