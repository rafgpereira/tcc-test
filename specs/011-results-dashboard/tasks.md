# Tasks: Dashboard de exploração dos resultados

**Input**: Design documents from `/specs/011-results-dashboard/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md),
[contracts/pages.md](./contracts/pages.md), [quickstart.md](./quickstart.md); Constitution **v1.9.0**

**Tests**: INCLUÍDOS. A camada de dados tem testes de casos conhecidos, porque os números dela precisam
bater com o `evaluation report` (SC-001); cada página tem um teste de fumaça com `AppTest` (research
R8). Os testes vêm antes da implementação em cada história.

**Organization**:
- base: dependência nova, pacote, `serve`, camada de leitura e a moldura do app (barra lateral,
  recarregar, filtros);
- US1 (P1): visão geral;
- US2 (P1): detalhe de uma combinação e de um alvo (código lado a lado);
- US3 (P2): comparações;
- US4 (P3): página de métricas (aviso até a feature 010);
- por fim: documentação e aposentar a prévia provisória do piloto.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: arquivos diferentes, sem dependência de tarefa incompleta
- **[Story]**: US1 a US4, só nas fases de história
- **Onde rodar**: `pytest` no `sandbox`; `serve`, `uv` e os comandos de documentação no `app`

## Regras que valem para TODAS as tarefas

- **Só leitura** (FR-003): nenhum código do pacote escreve em disco; o teste de T034 confere.
- **Nenhuma métrica oficial calculada** (FR-004, FR-005): só contagens e a prévia, sempre rotulada
  "prévia" e sempre como Σ detectados / Σ total (data-model.md).
- **📌 PROPAGAR**: decisão nova ou dado medido vai, na própria tarefa, para
  `docs/metodologia-referencia.md` (histórico) e para `spec.md`/`plan.md`/`research.md`.
- **O agente não commita**; comando novo nasce `pendente` em "Comandos verificados".

---

## Phase 1: Setup

- [X] T001 Add `streamlit` (versão com `st.navigation` e `streamlit.testing.v1.AppTest`) and `pandas` (explícita; hoje já vem por `datasets`) to `pyproject.toml` dependencies and update `uv.lock` with `docker compose run --rm app uv lock`; then `docker compose build`; record the pinned Streamlit version in `specs/011-results-dashboard/research.md` R1
- [X] T002 [P] Create `src/dashboard/__init__.py`, `src/dashboard/views/__init__.py` and `src/dashboard/config.py` (`DEFAULT_EVALUATION_DIR = Path("data/evaluation")`, `PORT = 8501`, `SETS = ("slm", "gpt", "gemini", "claude", "slm-attempt1")`, `SCENARIOS = ("black_box", "white_box", "hybrid")`, `METRICS_DIR = Path("data/metrics")`, `PREVIEW_LABEL = "prévia"`)
- [X] T003 [P] Create `tests/dashboard/conftest.py` reusing `make_tree` and the fake engine of `tests/evaluation/conftest.py` to build, in `tmp_path`, a repository with an evaluated tree (run `evaluation.problem_task.evaluate_problem` with the fake engine and write it with `evaluation.store.write_problem`), including one `discarded_manual` combination, one `slm-attempt1` set, one `suites/slm-rev1` origin and a `metadata.json` with `macrocategoria`

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: nenhuma história começa antes desta fase

- [X] T004 [P] Write `tests/dashboard/test_data.py::test_combinations_*`: one row per closed combination with the fixed columns of data-model.md "Combination" (in order); `building/` ignored; an invalid `<scenario>.json` goes to `invalid` with its reason and the rest loads; `closed` per set; `macrocategoria` from `metadata.json`, empty when the dataset is not extracted; `loaded_at` set
- [X] T005 Implement `combinations(base, root=".") -> LoadedTree` in `src/dashboard/data.py`, validating each file with `evaluation.schemas.result.CombinationResult` (logic of `data/scratch/pilot_view.py::combinations`, plus `model`, `tree`, `attempt`, `macrocategoria`) (makes T004 pass)
- [X] T006 [P] Write `tests/dashboard/test_data.py::test_filters_*` and `::test_preview_*`: `apply_filters(table, sets, scenarios, problems, macrocategorias, statuses)` with empty lists filtering nothing; `preview(table, by)` computes `wa_pct_declared` etc. as "Σ detectados / Σ total", excluding combinations without a suite, never a mean of percentages
- [X] T007 Implement `apply_filters` and `preview` in `src/dashboard/data.py` (makes T006 pass)
- [X] T008 [P] Write `tests/dashboard/test_cli.py`: `python -m dashboard serve` builds the command `streamlit run <path of app.py> --server.address 0.0.0.0 --server.port <port> --server.headless true` with `HOME=/tmp`, `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false` and `STREAMLIT_SERVER_FILE_WATCHER_TYPE=none` (the process call injected, nothing really started); a nonexistent `--evaluation-dir` exits `2`; missing Streamlit exits `3`
- [X] T009 Implement `src/dashboard/__main__.py` (`serve`, contracts/cli.md) (makes T008 pass)
- [X] T010 Implement `src/dashboard/app.py`: `st.navigation` with the four pages; sidebar with the evaluation folder (default from `--evaluation-dir`), the **recarregar dados** button (a counter in `st.session_state` that is part of the `st.cache_data` key of `combinations`), the time of the last read, problems closed per set, invalid files, and the filters, stored in `st.session_state` for the pages; empty-folder message with the `evaluation run` command

**Checkpoint**: `serve` abre um painel vazio com a barra lateral; `pytest tests/dashboard` passa

---

## Phase 3: User Story 1 - Visão geral (Priority: P1) 🎯 MVP

**Goal**: o que já foi avaliado, por conjunto × cenário, com os filtros

**Independent Test**: com o piloto parcial, os números batem com `python -m evaluation report` (SC-001)

- [X] T011 [P] [US1] Write `tests/dashboard/test_data.py::test_overview_matches_the_evaluation_report`: for the tree of T003, `overview(table)` per set gives the same AC approved/rejected, AC tests by verdict and detected per oracle as `evaluation.report.build_report` for the same files
- [X] T012 [US1] Implement `overview(table) -> DataFrame` in `src/dashboard/data.py` (per set × scenario: combinations, without suite by reason, AC rejected, AC tests with wrong output and with error, preview percentages for WAs and mutants in both oracles, unstable, not compiled) (makes T011 pass)
- [X] T013 [US1] Implement `src/dashboard/views/overview.py` (contracts/pages.md "Visão geral"): the overview table, the per-problem table, the "prévia" label on every percentage, CSV download of each filtered table (`st.download_button`, nothing written to disk)
- [X] T014 [P] [US1] Write `tests/dashboard/test_pages.py::test_overview_page` with `AppTest`: runs without exception on the tree of T003 and on an empty folder; shows the "prévia" label; the macrocategoria filter changes the counts

**Checkpoint**: MVP de leitura do piloto (substitui a tabela da prévia em texto)

---

## Phase 4: User Story 2 - Detalhe de uma combinação (Priority: P1)

**Goal**: teste a teste, alvos pegos só pelo declarado, detalhe de um alvo com o código lado a lado

**Independent Test**: `1000_B`, Gemini, caixa-preta, na conferência: testes 4, 7 e 9 com saída diferente, 14 WAs só pelo declarado, `WA_3` com o código ao lado do `AC_ref` (quickstart §4)

- [X] T015 [P] [US2] Write `tests/dashboard/test_data.py::test_combination_tests_*`: rows of data-model.md "TestRow" (input and expected from `data/<suite_source.tree>/problems/<id>/<scenario>/suite.json`; for `slm-attempt1` via `evaluation.sources.attempt_suite`; for a `suites/slm-rev1` origin, read from that tree); detections per test in each oracle; `suite_changed=True` when the file hash differs from `suite_sha256`; suite not extracted → input/expected empty and a warning flag; combination without suite → no rows and its reason
- [X] T016 [US2] Implement `combination_tests(base, set, problem, scenario, root=".")` and `only_declared(result)` (targets detected by the declared oracle and not by the corrected one) in `src/dashboard/data.py` (makes T015 pass)
- [X] T017 [P] [US2] Write `tests/dashboard/test_data.py::test_target_detail_*`: data-model.md "TargetDetail"; `source` from `data/dataset/problems/<id>/WA_<n>.cpp` or `data/mutants/problems/<id>/Mutant_<n>.cpp`, `ac_source` from `AC_ref.cpp`; `diff_html` from `difflib.HtmlDiff` marks the changed line of a mutant; missing files → `source=None` and no exception
- [X] T018 [US2] Implement `target_detail(base, set, problem, scenario, target, root=".")` in `src/dashboard/data.py` (makes T017 pass)
- [X] T019 [US2] Implement `src/dashboard/views/combination.py` (contracts/pages.md "Combinação"): set → problem → scenario selectors (SC-003); header (status, origin, size, AC approved, warning when `suite_changed`); test table with long outputs abbreviated and full on expand; list "só pelo oráculo declarado"; target selector opening its detection in each oracle and the side-by-side code (`st.html`/`components.html` of `diff_html`, FR-007a); CSV download of the test table
- [X] T020 [P] [US2] Write `tests/dashboard/test_pages.py::test_combination_page` with `AppTest`: runs for a combination with suite, one without suite and one of `slm-attempt1`; opening a target shows the code section or the "código não disponível" warning

---

## Phase 5: User Story 3 - Comparações (Priority: P2)

**Goal**: declarado × corrigido por combinação; modelo local final × 1ª tentativa × comerciais

**Independent Test**: com a conferência do `1000_B`, diferença no Gemini e no SLM caixa-preta, nenhuma no GPT e no Claude

- [X] T021 [P] [US3] Write `tests/dashboard/test_data.py::test_oracle_gap_*` and `::test_local_vs_commercial`: `oracle_gap(table)` gives per combination `wa_declared - wa_corrected` and `mutants_declared - mutants_corrected` with `ac_approved`; `local_vs_commercial(table)` puts `slm`, `slm-attempt1`, `gpt`, `gemini`, `claude` side by side per problem × scenario (preview percentages); a combination whose final SLM suite came from attempt 1 has equal values in `slm` and `slm-attempt1`
- [X] T022 [US3] Implement `oracle_gap` and `local_vs_commercial` in `src/dashboard/data.py` (makes T021 pass)
- [X] T023 [US3] Implement `src/dashboard/views/compare.py` (contracts/pages.md "Comparações"): both tables, rows with AC rejected highlighted, "prévia" label, CSV download
- [X] T024 [P] [US3] Write `tests/dashboard/test_pages.py::test_compare_page` with `AppTest`

---

## Phase 6: User Story 4 - Métricas oficiais (Priority: P3)

**Goal**: aviso enquanto a feature 010 não existir; a integração de verdade vem com ela (research R7)

**Independent Test**: sem `data/metrics/`, a página mostra o aviso e o comando, sem erro

- [X] T025 [US4] Implement `src/dashboard/views/metrics.py`: if `config.METRICS_DIR` has no tables, show "métricas oficiais ainda não calculadas" and that they come from the metrics module; otherwise list the files found (the columns and charts are a task of the 010, when its format exists)
- [X] T026 [P] [US4] Write `tests/dashboard/test_pages.py::test_metrics_page` with `AppTest` (folder absent → warning; never computes a metric)

---

## Phase 7: Documentação e fechamento

- [X] T027 [P] Write `src/dashboard/README.md` per `docs/template-modulo.md`: status `em implementação` until `serve` is stamped; (b) how it is used per rule 3 of `docs/template-modulo.md` (module without a distributed artifact: no invented scenario): build, open with `docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve`, open `http://localhost:8501`, and that it reads whatever evaluation tree exists (a run in progress or the extracted packages), what each page shows, that it is local only and writes nothing, the "prévia" meaning; one command table (`serve`, `--evaluation-dir`, `--port`, Ctrl+C, exit codes); no spec-kit citations
- [X] T028 [P] Update `README.md` (raiz): module table and "Depois da preparação" row for `dashboard`; "Referência de comandos" with `serve`; the `Estado atual` sentence and date; and `CLAUDE.md` "Estrutura" and "Comandos do dia a dia"
- [ ] T029 Retire `data/scratch/pilot_view.py`: tell the authors it is replaced by the dashboard (it is not versioned; delete only with their ok) and remove its mention from `CLAUDE.md`/READMEs if any
- [X] T030 📌 PROPAGAR Update `docs/metodologia-referencia.md` history row of the dashboard (planned → implemented, the pinned Streamlit version, any divergence); create `specs/011-results-dashboard/sync-matrix.json` (`schema_version: 1`, rows D1–D4 of the spec with needles found in the methodology: `não fonte dos números do TCC`, `prévia rotulada`, `uso só local`, `download apenas do CSV`); run `docker compose run --rm app python scripts/check_docs_sync.py` and `... check_docs_sync.py --feature specs/011-results-dashboard`, `ruff check .` and `black --check .` with exit `0`
- [ ] T031 📌 PROPAGAR Measure SC-002 on the largest tree available (the pilot; the full run when it exists): time to open and to apply a filter; record in `research.md` R4 and the methodology
- [ ] T032 Run quickstart §3–§6 on the pilot with the authors (`data/evaluation-conf` only as a fallback): numbers equal to `evaluation report`, the `1000_B` detail, reload during a `run`; this is also the check of SC-004 (for each combination with the AC rejected, the authors find the reason in the dashboard)
- [ ] T033 Stamp `serve` in "Comandos verificados" of `src/dashboard/README.md` (only after T032 on a committed revision) and grep both READMEs for sentences still calling it pending
- [X] T034 Write `tests/dashboard/test_pages.py::test_nothing_is_written`: open every page with `AppTest` over the tree of T003 and compare the set of files (and their mtimes) under `tmp_path` before and after (SC-005); then run `docker compose run --rm sandbox pytest tests/dashboard tests/evaluation`

- [X] T035 [US1] Tooltips and glossary (FR-013, pedido de 2026-11-05): `src/dashboard/glossary.py` (full name of every abbreviation, column and cell value), `src/dashboard/views/common.py` (tables with Portuguese headers and the explanation on hover, text with `<abbr>`, the sidebar glossary), applied to every page; `tests/dashboard/test_glossary.py` checks that every column shown has an explanation
---

## Dependencies & Execution Order

- **Setup (T001–T003)** → **Base (T004–T010)** → histórias.
- **US1 (T011–T014)** e **US2 (T015–T020)** dependem só da base; podem andar em paralelo
  (arquivos de página diferentes; `data.py` é compartilhado: as implementações T012, T016, T018 em
  sequência).
- **US3 (T021–T024)** depende da base; **US4 (T025–T026)** depende só de T010.
- **Fechamento**: T027–T029 depois das histórias; T030 depois deles; T031–T033 com os autores;
  T034 pode entrar logo depois de T013.

### Parallel Opportunities

- T002 e T003; os testes T004, T006 e T008; T011, T015, T017, T021 (testes de dados) entre si;
  os testes de página T014, T020, T024 e T026; T027 e T028.

## Parallel Example: base

```text
T004 tests/dashboard/test_data.py (combinations)
T006 tests/dashboard/test_data.py (filters, preview)   # mesmo arquivo: escrever em sequência
T008 tests/dashboard/test_cli.py
```

## Implementation Strategy

### MVP (US1 + US2)

1. Setup e base → o painel abre e lê a pasta.
2. US1 → a visão geral substitui a prévia em texto do piloto.
3. US2 → o detalhe teste a teste explica cada número estranho (conferência manual do piloto).

### Depois

4. US3 (comparações) → 5. US4 (aviso de métricas) → 6. documentação, medição e carimbo.
7. Quando a feature 010 existir: tarefa nova para ligar a página de métricas às tabelas dela.
