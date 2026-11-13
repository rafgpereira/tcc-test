---

description: "Task list for the storytelling dashboard"
---

# Tasks: Painel que conta a história dos resultados

**Input**: Design documents from `specs/012-dashboard-storytelling/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/narrative.md,
contracts/api.md, quickstart.md; roteiro `docs/roteiro-painel.md`

**Tests**: incluídos. `metrics` é infraestrutura de métrica (Constitution, Princípio VI), e a spec
pede conferência automática (SC-001, SC-002, SC-006). Cada teste é escrito antes da implementação
que o faz passar. Todos rodam com `docker compose run --rm sandbox pytest <caminho>`.

**Organization**: por história de usuário (spec.md): US1 o experimento (P1), US2 quem ganhou em
cada métrica (P1), US3 guia de escolha (P1), US4 a avaliação (P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: US1–US4

---

## Phase 1: Setup

**Purpose**: deixar a base de dados de referência pronta para os testes

- [X] T001 Extend the metrics test fixtures in `tests/metrics/conftest.py` so the fake `metadata.json` of each problem carries `cf_rating` (two values, e.g. 1000 and 1600, across at least 4 problems) and the fake tables include `stats.csv` rows for the families `models` and `attempt1` with metrics `TDF_star`, `MS_star` and `TFP` (one pair `significant=True`, one `False`) and `cost.csv` rows for the 3 commercial sets
- [X] T002 [P] Extend `tests/dashboard/conftest.py` so the fake dataset `metadata.json` carries `cf_rating`, and add a fixture that writes a small `data/metrics/` (the six tables from `metrics.tables.build` over the fake tree) so the pages can open the metrics page

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: o corte por rating, o núcleo de `metrics.story` e as três páginas vazias. Bloqueia todas
as histórias.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

### Rating (R2)

- [X] T003 [P] Write `tests/metrics/test_sources_cuts_gate.py::test_rating_*`: `per_problem` has the column `rating` (integer, from `cf_rating`) right after `macrocategoria` (contracts/api.md); `cuts.apply(per_problem, ratings=(1000,))` keeps only those problems and also cuts `detected_wa`; `ratings=()` filters nothing; a rating that leaves one problem raises `CutError`
- [X] T004 Add `rating` to `PER_PROBLEM_COLUMNS` and read `cf_rating` together with `macrocategoria` in `src/metrics/sources.py` (missing value → empty, never invented); add `ratings=()` to `apply` in `src/metrics/cuts.py` (makes T003 pass)
- [X] T005 [P] Write `tests/dashboard/test_data.py::test_rating_*`: the combinations table has `rating` from `metadata.json`; `apply_filters(..., ratings=[1600])` keeps only those rows; empty list filters nothing
- [X] T006 Add `rating` to `COLUMNS` and `_row` and the `ratings` argument to `apply_filters` in `src/dashboard/data.py` (makes T005 pass)
- [X] T007 Run `docker compose run --rm app python -m metrics compute` on the real data and confirm that `metrics.csv`, `iic.csv`, `stats.csv`, `cost.csv` and `detected_wa.csv` in `data/metrics/` have the same bytes as before (`sha256sum` before and after) and that `per_problem.csv` only gained the `rating` column; record the result in `specs/012-dashboard-storytelling/research.md` R2

### Núcleo de `metrics.story` (R1, R3, R4)

- [X] T008 [P] Write `tests/metrics/test_story.py::test_values_*` on the fake tables: `criteria()` returns, in order, `tdf_star`, `ms_star`, `tfp`, `delta_tdf`, `tc`, `cost` with the fields of data-model.md "Criterio"; `values(tables, recorte)` gives, per set, the mean of the per-scenario values of `metrics.primary.table` for TDF\*, MS\*, TFP, Δ and TC, and cost = 1000 × Σ cost ÷ Σ WAs killed by the AC oracle (R4); with one scenario in the cut, that scenario's value; a cut with 1 or 0 problems raises `CutError`
- [X] T009 [P] Write `tests/metrics/test_story.py::test_test_state_*`: `test_state(stats, metric, scenario, a, b, recorte)` returns `"differ"` / `"tie"` from the `significant` column of the `models` family (or `attempt1` when one side is `slm-attempt1`), in either order of the pair; `"untested"` when the cut is not complete ("sem filtro de problema, macrocategoria, rating ou status"), when the criterion has no `stats_metric` (Δ, TC, cost), or when `scenario` is `None` (mean of scenarios)
- [X] T010 Implement `Recorte`, `Criterio`, `criteria()`, `values()` and `test_state()` in the new `src/metrics/story.py` (pure Python, no Streamlit, no file I/O; reuses `cuts.apply` and `primary.table`) (makes T008 and T009 pass). Done 2026-11-12: `test_real_numbers` (T013) runs against the real `data/metrics` and passes
- [X] T011 [P] Write `tests/metrics/test_story.py::test_scoreboard_*` and `::test_leader_*`: positions 1..n per criterion in the direction of `better`; exact ties share the position; the local sets (`slm`, `slm-attempt1`) have no position in `cost` and are never its leader; `leader(...)` returns leader, value, second, second value and the state of T009; property check: on every cut of a fixed list (each macrocategoria, each rating, each status, each single scenario, each pair of sets), the named leader has the best value of the cut (SC-002)
- [X] T012 Implement `scoreboard()` and `leader()` returning `Resultado` (data-model.md) in `src/metrics/story.py` (makes T011 pass)
- [X] T013 [P] Write `tests/metrics/test_story.py::test_real_numbers` (skipped when `data/metrics/` is not extracted): without filter, the scoreboard gives Gemini 1st in TDF\* (90.1%) and MS\* (97.0%), Claude 1st in TFP (17.3%) and cost, GPT 1st in Δ (1.9), `slm-attempt1` TC 91.2%; `leader` in `white_box` for TFP is `slm` 16.5% with `tie` against Claude 17.5%, in `hybrid` GPT 15.0% `tie` Claude 16.5%, for TDF\* in `white_box` Gemini 89.7% `tie` Claude 88.0% (SC-001; numbers checked on 2026-11-12)

### Páginas e barra lateral (R7)

- [X] T014 Restructure `src/dashboard/app.py`: `st.navigation` with three pages, `experiment` ("O experimento", default), `evaluation` ("A avaliação") and `metrics` ("As métricas"); add the **Rating** multiselect to the sidebar (values from the table, `help`: "Dificuldade do problema no Codeforces"); keep the filters only in the sidebar and pass the same dict to the three pages; `PAGES` updated so the tests can open each page by key. Done: the three pages are the navigation (`NAVIGATION`); the keys of feature 011 (`overview`, `combination`, `compare`) stay in `PAGES`, out of the navigation, until T037; the provisional evaluation page already shows Comparações and Combinação in tabs
- [X] T015 [P] Create `src/dashboard/views/common.py::cut_banner(filters, n_problems)`: the line at the top of every page with the active filters and the number of problems ("filtros: macrocategoria = matemática · 41 problemas"; "sem filtros · 200 problemas"); and `bridge(text, page_key)`: the closing sentence with the link to the next page (FR-002)
- [X] T016 Create placeholder `src/dashboard/views/experiment.py` and `src/dashboard/views/evaluation.py` (title, `cut_banner`, `bridge`) so navigation works before the stories

**Checkpoint**: rating funciona nos dois módulos; `metrics.story` dá placar e vencedores; as três
páginas abrem.

---

## Phase 3: User Story 1 - Entender o experimento (Priority: P1) 🎯 MVP

**Goal**: a primeira página dá o contexto: problemas, ratings, macrocategorias, falhas, IAs, suítes,
testes e gasto, tudo pelo recorte.

**Independent Test**: sem filtro, 200 problemas, 20.000 WAs, 20.000 mutantes, 4 IAs × 3 cenários,
2.400 suítes, 24.274 testes, US$ 19,35 (GPT 70%, Gemini 25%, Claude 5%), ratings 33/24/20/22/35/31/35,
macrocategorias 98/61/41.

- [X] T017 [P] [US1] Write `tests/dashboard/test_data.py::test_experiment_*`: `experiment_summary(per_problem, cost, recorte)` returns problems, WAs (100 per problem), mutants (100 per problem), sets × scenarios, suites (combinations with a suite), tests (Σ `suite_size` of the four final models), money spent per commercial set and its share, model hours of the local model (`duration_s` of `cost.csv` ÷ 3600); `ratings_count` and `macro_count` per value; suites per set and status with the denominator; mean tests per suite per set and scenario; all of them respect the cut
- [X] T018 [US1] Implement `experiment_summary`, `ratings_count`, `macro_count`, `suites_by_status` and `tests_per_suite` in `src/dashboard/data.py`, reading only `per_problem.csv` and `cost.csv` through `metrics.tables.read` and the cut of `metrics.cuts.apply` (no metric formula; counts only) (makes T017 pass). **Divergence (2026-11-12)**: the counts come from the evaluation table the dashboard already loads (same status, suite size, macrocategoria and rating), not from `per_problem.csv`, so page 1 works before the metrics exist (spec, edge case "Métricas ainda não calculadas"); only the money comes from `data/metrics/cost.csv`, when present. Totals checked on the real data: 200 problems, 24.274 tests, US$ 19,35, 91,2% minimum
- [X] T019 [P] [US1] Add to `src/metrics/charts.py` the kinds needed by page 1, following contracts/narrative.md "Página 1": `donut` (at most 4 slices, value and share as direct labels, total in the centre), `bars` (vertical, value on each bar), `stacked100` (one bar per set, statuses with the validated categorical palette, the denominator in the subtitle), `dots` (mean per set and scenario); load the project skill `dataviz` before choosing colours. Done: palette extended to the 8 validated slots in their fixed order; `validate_palette.js` run: slots 1–6 PASS adjacent in light and dark, slots 1–3 PASS all-pairs (donuts); light contrast WARN on 3 slots → relief by value labels and a "ver os números" table under every chart; an absence part ("sem suíte") is drawn in the muted ink, never a hue; charts rendered with the real data and looked at (a hidden tie in the ratings subtitle was found and fixed)
- [X] T020 [US1] Implement `src/dashboard/views/experiment.py`: `cut_banner`; the KPI row (`st.metric`) with problems, WAs + mutants ("100 + 100 por problema"), IAs × cenários, suítes, testes, gasto; the five charts of contracts/narrative.md "Página 1" with the title rules there (title = conclusion of the cut, e.g. "Toda IA entregou suíte em pelo menos {mínimo} das combinações"); the local model shown beside the spending donut with its model hours and "sem custo em dinheiro"; the empty-cut message; `bridge` to the evaluation page
- [X] T021 [P] [US1] Write `tests/dashboard/test_pages.py::test_experiment_page`: opens with `AppTest` as the default page; without filter shows the numbers of the fake tree; with a macrocategoria filter the banner and the numbers change; an empty cut shows the message; no file under the repository or `data/` changes (SC-006)

**Checkpoint**: a página 1 funciona sozinha e é o MVP apresentável.

---

## Phase 4: User Story 2 - Ver quem ganhou em cada métrica (Priority: P1)

**Goal**: a página 3 abre com o placar dos 5 conjuntos e segue com uma seção por critério, cada uma
com título-conclusão, denominador, anotações e o estado do teste.

**Independent Test**: sem filtro, o placar e os títulos mostram os números de T013; com filtro, os
títulos mudam com o líder do recorte e as notas viram "não testado".

- [X] T022 [P] [US2] Write `tests/metrics/test_story.py::test_conclusion_*`: `conclusion(tables, recorte, section)` for `scoreboard`, `tdf`, `ms`, `tfp`, `context`, `cost` returns a `Titulo` whose `text` names the leader of the cut and its value, uses the tie rule when `state == "tie"` ("{líder} e {segundo} empatam…"), the scoreboard rule "Nenhum conjunto venceu em todos os critérios" when leaders differ and "{líder} venceu em todos os critérios" when they coincide, and the tradeoff rule "Quem mais detecta também mais erra o gabarito" only when the TDF\* leader is last in TFP; `subtitle` carries the denominator of the cut ("de {n·100} WAs", "dos {n} problemas"); `rule` identifies the template used
- [X] T023 [US2] Implement the title templates (contracts/narrative.md, one per section) and `conclusion()` in `src/metrics/story.py`, numbers formatted in Portuguese (comma decimal, "%"), the templates in one table at the top of the module for the authors to edit (makes T022 pass)
- [X] T024 [P] [US2] Add to `src/metrics/charts.py`: `scoreboard_grid` (sets × criteria, rank and value in each cell, the leader cell in the single highlight colour, the others neutral, notes under the grid); `ranked_before_after` (horizontal bars sorted by TDF\*, TDF → TDF\* on the same scale, value labels, leader highlighted, others grey); `tradeoff_scatter` (TFP on x, TDF\* on y, one point per set × scenario with direct labels, the ideal region shaded at 10–20% opacity); `scenario_lines` (TDF\* across the 3 scenarios per set); `diverging_bars` (IIC from zero, the validated diverging pair of the `dataviz` skill: blue above and red below with a neutral grey midpoint; never green × red); every kind accepts at most 3 annotations (text + point) and keeps the subtitle with the cut and the source
- [X] T025 [US2] Add the figures `scoreboard`, `tradeoff`, `scenario_shift` and `iic_diverging` to `FIGURES`, `TITLES` (now produced by `story.conclusion`), `KIND` and `figure_data` in `src/metrics/figures.py`; revise `tdf_by_model`, `ms_declared_vs_corrected` and `cost_per_detection` to the narrative contract (title from `story.conclusion`, leader highlighted, annotations of contracts/narrative.md 3.1, 3.2, 3.5); `iic_diverging` takes the oracle (`declared`/`corrected`) and uses `metrics.iic.table` over the cut; cost figures with a per-problem filter show the all-problems value with the note "o custo não se divide por problema" instead of failing; add `--rating` to `figures` in `src/metrics/__main__.py`
- [X] T026 [P] [US2] Write `tests/metrics/test_dashboard_page.py::test_new_figures_*`: each new and revised figure renders for the fake tables without filter and with a rating filter; PNG and SVG are the same bytes on two calls; the file name carries the filters (`scoreboard__rating-1600.png`); the title of `tdf_by_model` names the leader of the cut; `--rating 9999` exits `2`
- [X] T027 [US2] Rewrite `src/dashboard/views/metrics.py` as page 3: `cut_banner`; the scoreboard (3.0) with its notes; the sections 3.1 to 3.5 in the order of FR-011, each with the title and subtitle from `story.conclusion`, the chart from `metrics.figures.chart`, the test-state note ("diferença significativa", "empate estatístico", "diferença não testada neste recorte") and the PNG/SVG/PDF buttons (kept from feature 011); in 3.4 a page control to choose the IIC oracle (it does not change the cut, FR-006); the box plot of the IIC kept in a collapsed expander; the warning for a one-problem cut pointing to page 2; remove the "Corte das tabelas" selectbox: the official tables at the end follow the sidebar cut (the official rows when the cut is complete, otherwise `primary.table` of the cut, labelled as such)
- [X] T028 [P] [US2] Write `tests/dashboard/test_pages.py::test_metrics_page_*`: with the fake `data/metrics/`, the page shows the scoreboard before any section and the sections in order; a macrocategoria filter changes the titles and shows "não testado"; a one-problem cut shows the warning; without `data/metrics/`, the message of feature 011 and no exception

**Checkpoint**: placar e seções funcionam, com títulos que mudam com o recorte.

---

## Phase 5: User Story 3 - Escolher a IA pela própria prioridade (Priority: P1)

**Goal**: o guia de escolha no fim da página 3: vencedor de cada critério por cenário, empates e
"não testado", a prioridade realçada pelo leitor, nenhum vencedor geral.

**Independent Test**: sem filtro, "caixa-branca" mostra TFP modelo local × Claude em empate e TDF\*
Gemini × Claude em empate; "híbrido" mostra TFP GPT × Claude em empate; "gastar pouco" mostra o
Claude nos três cenários como "não testado".

- [X] T029 [P] [US3] Write `tests/metrics/test_story.py::test_guide_*`: `guide(tables, recorte)` returns one `Cartao` per criterion × scenario of the cut, scenarios labelled "caixa-preta" (`black_box`), "caixa-branca" (`white_box`), "híbrido" (`hybrid`); the extra criterion "rodar sem custo de API" names the local model without a number; no card or field declares an overall winner; with the real numbers (skipped without `data/metrics/`) the three cases of the Independent Test above
- [X] T030 [US3] Implement `Cartao` and `guide()` in `src/metrics/story.py` (makes T029 pass)
- [X] T031 [US3] Add `guide_grid` to `src/metrics/charts.py` (rows = criteria in plain language, columns = scenarios of the cut, each cell: winner, value, second and the state as a short tag; an optional highlighted row) and the figure `choice_guide` to `src/metrics/figures.py` (in the command, no row highlighted)
- [X] T032 [US3] Add section 3.6 to `src/dashboard/views/metrics.py`: title "Qual IA escolher depende do que importa para você", a radio "Minha prioridade" (gastar pouco, encontrar o máximo de falhas, não reprovar o código correto, confiar no gabarito, pegar defeitos sintéticos, rodar sem custo de API) that only highlights a row, the `choice_guide` chart with its download buttons, and the limitations of the experiment (contracts/narrative.md 3.6)
- [X] T033 [P] [US3] Write `tests/dashboard/test_pages.py::test_guide_section`: the guide appears after section 3.5 and before the official tables; changing the priority does not change any number shown; a single-scenario filter shows only that column

**Checkpoint**: a página 3 está completa.

---

## Phase 6: User Story 4 - Conferir uma combinação na avaliação (Priority: P2)

**Goal**: Combinação e Comparações numa página só, com os números da avaliação no topo.

**Independent Test**: `61_B`, `slm`, caixa-preta: o teste 3 reprova o AC, 100 WAs pelo gabarito da IA e
45 pelo do AC.

- [ ] T034 [US4] Turn `render` of `src/dashboard/views/combination.py` and `src/dashboard/views/compare.py` into functions that draw their content without a page title (`combination_section(tree, filters)`, `compare_section(tree, filters)`), with no change of content; in the combination section, the set/problem/scenario choices list only what fits the sidebar cut, and a cut with a single combination opens it directly (FR-006)
- [ ] T035 [US4] Implement `src/dashboard/views/evaluation.py`: `cut_banner`; on top, the evaluation numbers of the cut (combinations evaluated and without suite, AC approved and rejected, WAs and mutants detected in each oracle, with the "prévia" label of feature 011) from `data.overview`; two tabs, "Comparações" and "Combinação"; `bridge` to the metrics page
- [ ] T036 [US4] Remove `src/dashboard/views/overview.py` and move `PREVIEW_NOTE` to `src/dashboard/views/common.py`; update the imports in `compare.py`
- [ ] T037 [P] [US4] Update `tests/dashboard/test_pages.py`: replace the overview, combination and compare page tests with `test_evaluation_page` (the tabs, the numbers on top, the single-combination cut opening the detail, the cut restricting the choices); keep the assertions of feature 011 about the detail and the oracle gap

**Checkpoint**: as três páginas estão completas.

---

## Phase 6b: User Story 5 - Rastrear um número até a fonte (Priority: P1)

**Goal**: a página "Rastreabilidade", entre as métricas e a avaliação, com os 11 casos da US5.

- [X] T047 [US5] Implement `src/dashboard/trace.py` (plain pandas): `targets` (the `results.csv` of each set), `cut_targets`, `missing_suites` and `no_suite_reason` (the authors' `manual_close.json` or the evaluation's reason), `attempts` (commercial and local-model attempt files), `barred_responses`, `barred_suites`, `slm_origin`, `ac_rejections`, `ac_rejections_by_problem`, `oracle_only`, `oracle_only_targets`, `detected_by`, `undetected`, `exclusive`, `target_matrix`, `killed_by_test`, `problem_grid`, `problem_info`
- [X] T048 [US5] Implement `src/dashboard/views/trace.py`: "O que você quer rastrear?" with the 11 cases, each a list of the sidebar cut and an "Abrir" choice that opens a combination card (status, origin, reason, attempts, tests with the AC's output), a target card (who detected it, first test per oracle, code beside the AC) or a problem card (metadata, statement, AC, the 15 combinations); a notice when `results.csv` is missing
- [X] T049 [US5] Reorder the pages in `src/dashboard/app.py` (experiment → metrics → trace → evaluation) and the bridges (experiment → metrics → trace → evaluation; the one-problem warning of page 3 points to the traceability)
- [X] T050 [P] [US5] Write `tests/dashboard/test_trace.py`: the data of every case on the evaluated tree (missing suite with a reason, the rejected AC, the oracle gap, hard targets consistent with the detections, each target killed by its first failing test, the problem grid and the target matrix with 15 rows), every case opening with `AppTest`, the cases following the sidebar, the notice without `results.csv`; the page order
- [X] T051 [US5] Check on the real data: 56 combinations without a suite (53 + 3), 9 barred suites (8 reject the AC), 174 WAs undetected by the four models in 67 problems, 390 exclusive WAs (GPT 135, Gemini 108, Claude 99, SLM 48), 65 surviving mutants in 29 problems, WA detections by one answer key only 17.876 / 2.102 (equal to `detected_wa.csv`)

**Checkpoint**: cada número das métricas pode ser rastreado até o arquivo de origem.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T038 Update `python -m metrics package` in `src/metrics/__main__.py` to require the new figures without filter (PNG and SVG); run `compute`, `figures`, `package` and `verify --extracted data/metrics` on the real data; record the new zip size in `src/metrics/README.md`
- [ ] T039 [P] Update `src/dashboard/public/streamlit_app.py` only if needed for the three pages and check the public copy logic (`src/dashboard/cloud.py`) still unpacks the 12 packages; run `tests/dashboard/test_cloud.py`
- [ ] T040 [P] Update `src/dashboard/glossary.py`: `rating`, the criteria in plain language, "não testado", "empate estatístico", the scenario names, always caixa-preta / caixa-branca / híbrido (Milena, 2026-11-12)
- [ ] T041 Measure on the real data (SC-004): time to open each page and to apply a filter (macrocategoria, rating); if the IIC of a cut exceeds 5 s, cache it by cut; record the numbers in `specs/012-dashboard-storytelling/research.md` R8 and in `docs/metodologia-referencia.md` section 8
- [ ] T042 [P] Update `src/dashboard/README.md`: the three pages and what each shows, the filters (with rating) and what does not split by cut, "Como ler os gráficos" rewritten for the new sections and the guide; `src/metrics/README.md`: the new figures, `--rating`, the `rating` column; the root `README.md` (command reference: `--rating`); keep both READMEs within `docs/template-modulo.md`
- [ ] T043 [P] Add a note at the top of `specs/011-results-dashboard/spec.md` saying the pages and filters are now defined by feature 012 (the rest still holds), and mark `docs/roteiro-painel.md` as implemented by feature 012
- [ ] T044 Update `docs/metodologia-referencia.md`: section 5.8 (the amendment of 2026-11-12 from "em planejamento" to implemented, with any divergence from the plan), section 5.9 if any number shown changed, section 8 (one dated row with what was measured)
- [ ] T045 Run `docker compose run --rm sandbox pytest`, `docker compose run --rm app ruff check .`, `docker compose run --rm app black --check .`, `docker compose run --rm app python scripts/check_docs_sync.py` and `docker compose run --rm app python -m cli check`; fix what fails
- [ ] T046 Final review with the skill *visual-storytelling-design* (research.md R10): open the real dashboard, capture the three pages without filter and with one filter, apply the 10-item checklist of the skill and the honesty checks (the leader also shown where it loses, ties as ties, limitations present, denominators visible, at most 3 annotations per chart), and write the result in `specs/012-dashboard-storytelling/review.md` for the authors to decide the adjustments; SC-003 (a person from outside in under 2 minutes) is left for the authors

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → **Foundational (T003–T016)** → histórias.
- **US1 (T017–T021)** depende só da fase 2 (rating e páginas); não usa `metrics.story`.
- **US2 (T022–T028)** depende da fase 2 (núcleo de `metrics.story`).
- **US3 (T029–T033)** depende de US2 (a página 3 e `charts.py` com as anotações).
- **US4 (T034–T037)** depende só da fase 2 (páginas e barra lateral).
- **Polish (T038–T046)** depois das histórias; T046 é a última.

Dentro da fase 2: T003 → T004 → T007; T005 → T006; T008 e T009 → T010 → T011 → T012 → T013; T014 →
T015 → T016.

## Parallel Opportunities

- Fase 1: T001 ∥ T002.
- Fase 2: os testes T003, T005, T008, T009 juntos; o bloco rating (T003–T007) em paralelo com o bloco
  `metrics.story` (T008–T013) e com o das páginas (T014–T016).
- Depois da fase 2: **US1 ∥ US2 ∥ US4** (arquivos diferentes: `views/experiment.py`,
  `views/metrics.py` + `story.py`, `views/evaluation.py`). Cuidado: US1 (T019) e US2 (T024) mexem
  em `src/metrics/charts.py`; fazer uma depois da outra ou em funções separadas sem conflito.
- Polish: T039, T040, T042, T043 juntos.

### Exemplo (US2)

```text
T022 test_conclusion_*  ∥  T024 charts.py (novos tipos)
→ T023 conclusion()  → T025 figures.py  ∥  T026 testes das figuras
→ T027 página 3  ∥  T028 teste da página
```

## Implementation Strategy

1. **MVP = Fases 1, 2 e US1**: o painel abre na página "O experimento" com o contexto e o filtro de
   rating; já serve para a apresentação do método.
2. **US2 + US3**: a página das métricas com placar, seções e guia, que é o centro da história para a
   banca.
3. **US4**: a reorganização da avaliação.
4. **Polish**: pacote de métricas com as figuras novas, documentação, medição e a revisão final pela
   skill (T046), que os autores usam para os últimos ajustes antes da defesa.
