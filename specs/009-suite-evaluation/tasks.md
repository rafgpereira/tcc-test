# Tasks: Avaliação das suítes contra AC, WAs e mutantes

**Input**: Design documents from `/specs/009-suite-evaluation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md),
[contracts/evaluation-api.md](./contracts/evaluation-api.md), [quickstart.md](./quickstart.md);
Constitution **v1.9.0**

**Tests**: INCLUÍDOS (Princípio VI: módulo de infraestrutura sem teste próprio não está pronto).
Em cada história, os testes vêm antes da implementação e devem falhar primeiro. Unidade com motor
falso (sequência programada de `RunResult`, sem C++); integração com C++ real marcada
`@pytest.mark.integration`.

**Organization**:
- base: pacote, configuração, esquemas, leitura das entradas, persistência e portões;
- US1 (P1): suítes finais — AC sem curto-circuito, alvos com curto-circuito (oráculo declarado),
  "sem suíte", repetição de erro, comando `run`;
- US2 (P1): oráculo corrigido pelo AC, na mesma passada;
- US3 (P2): 1ª tentativa do modelo local (conjunto `slm-attempt1`);
- US4 (P2): retomada, `run.json`, `report`, `package`, `verify` e camadas do `cli check`;
- por fim: documentação, piloto, execução completa e fechamento.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: arquivos diferentes, sem dependência de tarefa incompleta
- **[Story]**: US1 a US4, só nas fases de história
- **Onde rodar**: `pytest` e `python -m evaluation run` no `sandbox`; `report`, `package`,
  `verify` e `cli check` no `app`

## Regras que valem para TODAS as tarefas (Constitution 1.9.0)

- **📌 PROPAGAR**: dado medido ou decisão nova vai, na própria tarefa, para
  `docs/metodologia-referencia.md` (seção 4 e histórico) e para `spec.md`/`plan.md`/`research.md`.
- **O motor não muda**: nenhum arquivo de `src/sandbox/` é alterado (research R2); os testes de
  `tests/sandbox`, `tests/dataset` e `tests/mutation` passam sem mudança.
- **Nenhuma métrica aqui** (FR-020): nada de TDF, MS, TFP ou IIC neste pacote.
- **Documentação como critério de aceite**: README no formato de `docs/template-modulo.md`;
  `check_docs_sync.py` sai 0; comando novo nasce `pendente` em "Comandos verificados".
- **O agente não commita** (Princípio X): toda alteração fica `modified`/`untracked`.

---

## Phase 1: Setup

**Purpose**: esqueleto do pacote e da suíte de testes

- [X] T001 Create package skeleton `src/evaluation/__init__.py`, `src/evaluation/__main__.py` (argparse com os subcomandos `run`, `report`, `package`, `verify`, cada um ainda `NotImplementedError`) and `src/evaluation/schemas/__init__.py`, per plan.md "Project Structure"
- [X] T002 [P] Create `src/evaluation/config.py` with: `SETS = ("slm", "gpt", "gemini", "claude", "slm-attempt1")`, `SET_MODEL = {"slm-attempt1": "slm", ...}`, `SCENARIOS = ("black_box", "white_box", "hybrid")`, `ERROR_RUNS = 3` (research R9), `EVALUATION_DIR = "data/evaluation"`, nomes de pacote/manifesto/relatório `data/evaluation_<set>.zip`, `manifests/evaluation_<set>.manifest.json`, `manifests/evaluation_<set>_report.json` (research R7), `PILOT_PROBLEMS = ("1000_B", "1005_C", "1008_B", "1_B", "61_B")`
- [X] T003 [P] Create `tests/evaluation/__init__.py` and `tests/evaluation/conftest.py` with: um motor falso (`FakeEngine`: `compile(source, slot)` devolve `CompileResult` ok ou falho por nome de fonte; `run(binary, stdin, limits, slot)` devolve o próximo `RunResult` programado por (programa, entrada), contando chamadas) e um construtor de árvore mínima em `tmp_path` (dataset com 1 problema, 2 WAs e 2 mutantes reduzidos via parâmetro, suítes `suite.json` dos 4 modelos, `provenance.json` do modelo local, tentativas do modelo local)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: esquemas, leitura das entradas, persistência atômica e portões, usados por todas as histórias

**⚠️ CRITICAL**: nenhuma história começa antes desta fase

- [X] T004 [P] Write schema tests in `tests/evaluation/test_schemas.py`: `CombinationResult` rejeita `has_suite=false` com `ac` não nulo ou `targets` não vazia; rejeita `no_suite_reason` nulo com `has_suite=false`; `AcResult.approved` deve ser "⇔ todos os `tests[i].verdict == passed`"; `AcTest.error_kind` "não nulo ⇔ `runtime_error`"; `Detection.test_index`/`verdict` "não nulo ⇔ `detected`"; `DetectedSets` validado contra `targets`; `corrected_oracle_excluded == suite_size − corrected_oracle_tests`; `targets` com exatamente `WA_1..WA_100` e `Mutant_1..Mutant_100` quando há suíte (com o total parametrizável só nos testes); `extra="forbid"`
- [X] T005 Implement schemas in `src/evaluation/schemas/result.py` (`RunOutcome`, `AcTest`, `AcResult`, `Detection`, `TargetResult` com `kind` `wa` | `mutant` e `compiled`, `DetectedSets`, `SuiteSource` com `status` em `accepted` | `accepted_fallback` | `accepted_predicted` | `accepted_barred` | `discarded_manual` | null, `CombinationResult` com `schema_version: 1` e `no_suite_reason` em `discarded_manual` | `attempt_without_tests` | `prediction_attempt` | `attempt_missing` | null) and `src/evaluation/schemas/run.py` (`RunConfig`, campos de data-model.md "RunConfig", `error_runs: 3`), reusing `dataset.schemas.common.Schema` and `PROBLEM_ID_PATTERN` (makes T004 pass)
- [X] T006 [P] Write source tests in `tests/evaluation/test_sources.py`: `problem_targets` lê `AC_ref`, `WA_1..100`, `Mutant_1..100` e `ExecutionLimits` do `metadata.json` (nunca valor fixo); `final_suite` lê `data/suites/<modelo>/problems/<id>/<cenário>/suite.json`; para `slm`, a pasta vem de `provenance.json` (`suites/slm` ou `suites/slm-rev1`) e vai para `SuiteSource.tree`; `discarded_manual` → sem suíte com `no_suite_reason="discarded_manual"`; `suite_sha256` é o SHA-256 do arquivo lido; `status` copiado
- [X] T007 Implement `src/evaluation/sources.py` (`SuiteToEvaluate`, `ProblemTargets`, `problem_targets`, `final_suite`), reusing `ai_clients.store`/`ai_clients.schemas.provenance.SlmProvenance.in_force()` and the suite schemas of `ai_clients` and `ai_clients.llm.schemas` (makes T006 pass)
- [X] T008 [P] Write persistence tests in `tests/evaluation/test_store.py`: gravação de conjunto × problema em `building/<id>/` fechada com um único `rename` para `problems/<id>/`; `is_closed`; `reset_building` apaga o que sobrou; trava exclusiva de `<output-dir>/.lock` recusa segunda execução; leitura valida cada `<cenário>.json` contra o esquema
- [X] T009 Implement `src/evaluation/store.py` following the pattern of `src/mutation/persistence.py` (makes T008 pass)
- [X] T010 [P] Write gate tests in `tests/evaluation/test_gate.py`: falha do `selfcheck` ou de `cli.consistency.run_checks(root, only=["dataset", "mutants", "<modelo>_suites"], deep=True)` impede a execução e devolve código `1`; as camadas pedidas dependem dos conjuntos (`slm-attempt1` → `slm_suites`)
- [X] T011 Implement `src/evaluation/gate.py` (selfcheck do motor reaproveitando o de `dataset`, e `run_checks`) (makes T010 pass)

**Checkpoint**: base pronta — `pytest tests/evaluation` passa nos testes desta fase

---

## Phase 3: User Story 1 - Avaliar as suítes finais de um modelo (Priority: P1) 🎯 MVP

**Goal**: executar a suíte vigente de cada combinação contra o AC (todos os testes) e contra cada WA/mutante (curto-circuito), com repetição de erro e "sem suíte", e gravar o resultado

**Independent Test**: `python -m evaluation run --set gpt --problem <id> --output-dir data/evaluation-conf` e conferir à mão, contra a suíte e os códigos, os vereditos do AC e os alvos detectados (quickstart §2)

### Tests for User Story 1

- [X] T012 [P] [US1] Write AC judging tests in `tests/evaluation/test_judging_ac.py`: AC passa os N testes → N `passed` e `approved`; saída diferente no teste 2 e TLE no 5 → **todos** os N executados, `wrong_output` no 2, `runtime_error`/`TLE` no 5, `approved=false`; `actual_output` gravado em cada teste e vazio em erro; erro repetido nas 3 execuções → erro final com `runs` de 3 itens e o tipo da 1ª (TLE, RE, RE → TLE); erro que passa na 2ª execução → a 3ª ainda é executada (contagem de chamadas), `runs` de 3 itens, final `passed` com a saída da 2ª, `unstable=true`; sem erro → `runs=null`; `wrong_output` nunca repetido; `InfraError` propaga
- [X] T013 [P] [US1] Write target judging tests (oráculo declarado) in `tests/evaluation/test_judging_target.py`: WA que falha no teste 3 → detectado com `test_index=3` e o teste 4 **não** é executado (contagem de chamadas do motor falso); alvo que passa todos → não detectado; detecção por TLE só vale se repetir nas 3 (FR-006a; as 2 repetições sempre executadas, contagem de chamadas), senão o teste vai para `unstable_tests` e a passada continua (ou detecta com `wrong_output`, se a primeira repetição sem erro deu saída diferente); detecção por saída diferente vale na hora
- [X] T014 [P] [US1] Write problem evaluation tests in `tests/evaluation/test_problem_task.py`: AC compilado uma vez e cada alvo compilado uma vez para todas as suítes do problema (contagem de `compile`); alvo com `CE` → `compiled=false`, não detectado, em todas as suítes; falha de compilação do AC → `InfraError`; suíte sem testes → `has_suite=false`, nada executado; resultado idêntico com a ordem de suítes invertida
- [X] T015 [P] [US1] Write integration test in `tests/evaluation/test_integration.py` (`@pytest.mark.integration`, serviço `sandbox`): problema sintético com AC, 1 WA e 1 mutante conhecidos e uma suíte com um teste de saída declarada errada; conferir AC reprovado nesse teste e WA detectado no teste esperado com o motor real

### Implementation for User Story 1

- [X] T016 [US1] Implement `judge_ac` and the error-repetition helper (`config.ERROR_RUNS`, regra de data-model.md "Regras de transição") in `src/evaluation/judging.py` over `sandbox.runner.run_binary` and `sandbox.judge.judge_test`, mapping `Verdict.AC`→`passed`, `Verdict.WA`→`wrong_output`, `TLE`/`MLE`/`RE`→`runtime_error` (makes T012 pass)
- [X] T017 [US1] Implement `judge_target` for the declared oracle in `src/evaluation/judging.py`, keeping the signature of contracts/evaluation-api.md (`ac` argument already present) (makes T013 pass)
- [X] T018 [US1] Implement `evaluate_problem` in `src/evaluation/problem_task.py`: AC primeiro, depois um alvo de cada vez (`WA_1..WA_100`, `Mutant_1..Mutant_100`) contra todas as suítes, apagando o binário do alvo ao terminar (research R1, R4); monta os `CombinationResult` com `DetectedSets` e `elapsed_s` (makes T014 pass)
- [X] T019 [US1] Implement `src/evaluation/runtime.py` (inline, threads só para teste, e pool de processos, um *slot* por trabalhador, limpeza de slots no início e no fim), following `src/mutation/runtime.py`, with `tests/evaluation/test_runtime.py`: o mesmo conjunto de problemas avaliado com 1 trabalhador, com threads e com ordem de término embaralhada grava resultados iguais (FR-016)
- [X] T020 [US1] Implement `run` in `src/evaluation/__main__.py` for the final sets `slm`, `gpt`, `gemini`, `claude` per contracts/cli.md: opções `--set`, `--problem`, `--scenario` (só com `--output-dir` diferente de `data/evaluation`), `--workers`, `--output-dir`; portões (T011); trava; em cada problema avalia só os conjuntos pedidos que faltam, sem reescrever os prontos (FR-015); grava pelo processo principal; linha `ok <id> (<n> suites, <s> s)`; códigos `0`/`1`/`2`/`3`/`130`
- [X] T021 [US1] Write CLI tests in `tests/evaluation/test_cli_run.py` with the fake engine: códigos de saída; `--scenario` recusado com a pasta padrão; problema fechado não é refeito; com `gpt` pronto num problema, `run` com os 5 conjuntos avalia só os outros 4 e não reescreve o `gpt` (mesmo hash de arquivo); Ctrl+C simulado não deixa nada em `problems/` pela metade

**Checkpoint**: US1 funciona sozinha com o oráculo declarado; o oráculo corrigido (US2) completa o MVP

---

## Phase 4: User Story 2 - Detecção com o oráculo corrigido pelo AC (Priority: P1)

**Goal**: gravar, na mesma passada, a detecção de cada alvo com a saída esperada trocada pela saída real do AC, excluindo os testes em que o AC dá erro

**Independent Test**: num problema em que o AC é reprovado por saída diferente num teste, um WA que só "falhava" ali aparece detectado no declarado e não no corrigido (US2, cenário independente)

### Tests for User Story 2

- [X] T022 [P] [US2] Add corrected-oracle tests to `tests/evaluation/test_judging_target.py`: saídas declaradas iguais às do AC → `declared` e `corrected` idênticos; teste em que o AC deu `runtime_error` é ignorado no corrigido e contado em `corrected_oracle_excluded`; AC com erro em todos os testes → `corrected_oracle_tests=0` e nenhum alvo detectado no corrigido; passada única: cada teste executado **uma vez** para os dois oráculos e a passada para quando os dois decidiram (research R3); erro final do alvo decide os dois oráculos abertos; resultado igual ao de duas passadas independentes (comparação com uma implementação de referência ingênua no próprio teste)

### Implementation for User Story 2

- [X] T023 [US2] Extend `judge_target` in `src/evaluation/judging.py` to decide both oracles in one pass (contracts/evaluation-api.md) using `ac.tests[i].actual_output` and skipping tests whose final AC verdict is `runtime_error` (makes T022 pass)
- [X] T024 [US2] Fill `corrected_oracle_tests`, `corrected_oracle_excluded` and `DetectedSets.corrected_*` in `src/evaluation/problem_task.py`; update `tests/evaluation/test_problem_task.py` and `tests/evaluation/test_integration.py` to assert the corrected oracle (o WA do teste de integração com saída declarada errada)

**Checkpoint**: MVP completo (US1 + US2): as suítes finais dos 4 modelos podem ser avaliadas

---

## Phase 5: User Story 3 - Avaliar a 1ª tentativa do modelo local (Priority: P2)

**Goal**: conjunto `slm-attempt1`: avaliar a 1ª tentativa de cada combinação do modelo local, separado da suíte final

**Independent Test**: numa combinação cuja suíte final veio da tentativa 1, o resultado de `slm-attempt1` é idêntico ao de `slm` (exceto `suite_source`)

### Tests for User Story 3

- [X] T025 [P] [US3] Write attempt tests in `tests/evaluation/test_sources_attempt.py`: testes = entradas com `kept=true` da `attempt_<n>.execution.json` com as entradas de `attempt_<n>.generation.json` (`parse.inputs[index]`), mesma regra de `ai_clients.store._build_suite`, inclusive para tentativa rejeitada; tentativa de predição → `prediction_attempt`; tentativa inexistente → `attempt_missing`; resposta não interpretada ou nenhuma entrada mantida → `attempt_without_tests`; tentativa lida da pasta indicada pelo `provenance.json`; `SuiteSource.attempt=1`, `status=null`, `suite_sha256` dos dois arquivos
- [X] T026 [P] [US3] Add CLI tests to `tests/evaluation/test_cli_run.py`: `--set slm-attempt1` grava em `data/evaluation/slm-attempt1/` com `run.json.attempt=1`; resultado igual ao de `slm` quando a suíte final é a tentativa 1

### Implementation for User Story 3

- [X] T027 [US3] Implement `attempt_suite` in `src/evaluation/sources.py`, reusing `ai_clients.store.attempt_files` (makes T025 pass)
- [X] T028 [US3] Wire the set `slm-attempt1` into `run` in `src/evaluation/__main__.py` and into the default of `--set` (os 5 conjuntos) (makes T026 pass)

**Checkpoint**: os 5 conjuntos avaliáveis

---

## Phase 6: User Story 4 - Retomar, consolidar, empacotar e conferir (Priority: P2)

**Goal**: retomada segura com entradas congeladas, relatório e tabela consolidada, pacote com manifesto, verificação e camadas no `cli check`

**Independent Test**: interromper e retomar; as combinações fechadas antes da parada não são reescritas (mesmo hash de arquivo) e o resultado final tem os mesmos vereditos, índices e conjuntos de detectados de uma execução sem interrupção (tempo e memória fora da comparação, SC-004); `package`, `verify` e `cli check --deep` saem `0` (quickstart §4–§5)

### Tests for User Story 4

- [X] T029 [P] [US4] Write `run.json` tests in `tests/evaluation/test_run_config.py`: primeiro `run` grava `RunConfig` com os SHA-256 dos manifestos (dataset e revisão, mutantes, suítes do modelo), `gcc_version`, `error_runs=3`; retomada com qualquer campo diferente (menos `created_at`) → recusa com código `2`; retomada com `building/` sobrando refaz só esses problemas; problema já fechado não é reescrito (mesmo hash de arquivo); uma execução interrompida e retomada dá os mesmos vereditos, índices e conjuntos de detectados de uma sem interrupção, comparando sem os campos de tempo e memória (SC-004)
- [X] T030 [P] [US4] Write report tests in `tests/evaluation/test_report.py`: `results.csv` com as colunas exatas e na ordem de data-model.md "Tabela consolidada"; uma linha por combinação × alvo e uma linha com `target` vazio por combinação sem suíte; contagens do relatório (FR-017: avaliadas, sem suíte por motivo, AC aprovado/reprovado, testes do AC por veredito e tipo de erro, instáveis do AC e dos alvos, detectados por oráculo, excluídos do corrigido, `CE` de alvo, maior `actual_output`, tempo total); conjunto incompleto → `complete: false` com a lista do que falta
- [X] T031 [P] [US4] Write package/verify tests in `tests/evaluation/test_packaging.py`: `package` recusa conjunto sem 600 combinações, com `building/` ou com `results.csv`/relatório desatualizados; o zip contém só `run.json`, `results.csv` e `problems/` sob `evaluation/<set>/`; escrita atômica; `verify` com e sem `--extracted`, códigos `0`/`1`/`2`
- [X] T032 [P] [US4] Write consistency tests in `tests/cli/test_consistency.py` for the layers `evaluation_slm`, `evaluation_gpt`, `evaluation_gemini`, `evaluation_claude`, `evaluation_slm_attempt1`: cada problema com exatamente `black_box.json`, `white_box.json`, `hybrid.json`; falta é `[AVISO]` sem manifesto e `[FALHA]` com; arquivo estranho e pasta sem problema no dataset são `[FALHA]` sempre; camada ausente é `[AVISO]`; `--deep` confere hashes e zip

### Implementation for User Story 4

- [X] T033 [US4] Implement `RunConfig` creation and resume check in `src/evaluation/store.py` and `run` (makes T029 pass)
- [X] T034 [US4] Implement `src/evaluation/report.py` and the `report` subcommand (makes T030 pass); schema of the report in `src/evaluation/schemas/report.py`
- [X] T035 [US4] Implement `src/evaluation/packaging.py` (zip + manifesto no formato de `src/mutation/manifest.py`) and the `package`/`verify` subcommands (makes T031 pass); add to `.gitignore` the exceptions `!data/evaluation_slm.zip`, `!data/evaluation_gpt.zip`, `!data/evaluation_gemini.zip`, `!data/evaluation_claude.zip` and `!data/evaluation_slm-attempt1.zip`, with a comment as for the other packages (Constitution, Principle II: o pacote final e o manifesto são versionados)
- [X] T036 [US4] Add the five evaluation layers to `LAYERS` in `src/cli/consistency.py` (makes T032 pass), sem mudar o comportamento das camadas existentes (`pytest tests/cli` inteiro passa)

**Checkpoint**: todas as histórias funcionando e testadas

---

## Phase 7: Documentação, piloto, execução e fechamento

**Purpose**: Princípio XI, piloto obrigatório (FR-021) e execução final

- [X] T037 [P] Write `src/evaluation/README.md` per `docs/template-modulo.md`: seis seções, Cenário A (rodar do zero: portões, piloto, `run`, `report`, `package`, `verify`) e Cenário B (descompactar `data/evaluation_<set>.zip` e conferir), **uma** tabela com todos os comandos e variações (`--set`, `--problem`, `--scenario`, `--workers`, `--output-dir`, interrupção/retomada, códigos de saída), falhas comuns, "Comandos verificados" com cada comando `pendente`; sem citar spec-kit, constitution, `FR-`/`SC-`, tarefas ou `specs/NNN-...`
- [X] T038 [P] Update `README.md` (raiz): módulo `evaluation` na visão geral e no fluxo entre módulos, e os comandos na "Referência de comandos"; update `CLAUDE.md` "Estrutura" e "Comandos do dia a dia" com `src/evaluation/` e os comandos
- [X] T039 [P] Update `docs/verificacao-consistencia.md`: linha das camadas de avaliação na tabela e "Decisões (2026-11-04): camadas de avaliação"
- [X] T040 📌 PROPAGAR Update `docs/metodologia-referencia.md` seção 4 (de **[PLANEJADO]** para **[IMPLEMENTADO]**, com qualquer divergência do plano) e histórico (seção 8); create `specs/009-suite-evaluation/sync-matrix.json` (`schema_version: 1`, mesmo formato das features anteriores) with the decisions of this feature (dois oráculos, repetição de erro, piloto, conjuntos) and their needles in the metodologia; run `docker compose run --rm app python scripts/check_docs_sync.py` and `... check_docs_sync.py --feature specs/009-suite-evaluation`, `ruff check .` and `black --check .` with exit `0`
- [X] T041 📌 PROPAGAR **Piloto** (concluído 2026-11-05; medições e decisão na metodologia, seção 4) (FR-021, quickstart §3): `run` nos 5 problemas de `config.PILOT_PROBLEMS`, `report`, conferência manual dos autores na amostra (SC-003); registrar na metodologia (seção 4, **[MEDIDO]**) o tempo total, a estimativa da execução completa, testes instáveis, `CE` de alvo e a decisão dos autores de seguir; se algo mudar, guardar o piloto em `data/evaluation-piloto1/` e registrar o motivo
- [ ] T042 📌 PROPAGAR **Execução completa** (só com pedido dos autores; quickstart §4): `run` retomando o piloto, `report`, `package` e `verify --extracted` dos 5 conjuntos, `cli check --deep` com saída `0`; registrar na metodologia os números de cada relatório (seção 4, **[MEDIDO]**); carimbar os comandos em "Comandos verificados" e corrigir, por grep em `src/evaluation/README.md` e `README.md`, qualquer frase que os dê como pendentes
- [ ] T043 Run the full suite `docker compose run --rm sandbox pytest` and confirm `tests/sandbox`, `tests/dataset`, `tests/mutation`, `tests/ai_clients` unchanged and passing; tell the authors the exact `git add`/`git commit` command (o agente não commita)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias
- **US1 (Phase 3)**: depende da base
- **US2 (Phase 4)**: depende de US1 (estende `judge_target` e `evaluate_problem`)
- **US3 (Phase 5)**: depende da base e de US1 (`run`); independe de US2
- **US4 (Phase 6)**: depende da base e de US1 (`run`); T036 independe do resto da US4
- **Phase 7**: T037–T039 em paralelo depois de US4; T040 depois delas; T041 depois de US1–US4 e T040; T042 depois da decisão registrada em T041; T043 por último

### Within Each User Story

- Testes antes da implementação, falhando primeiro
- Esquemas → leitura → julgamento → problema → CLI

### Parallel Opportunities

- Setup: T002 e T003
- Base: T004, T006, T008 e T010 (testes) em paralelo; as implementações depois do respectivo teste
- US1: T012, T013, T014 e T015 em paralelo
- US3 e US4 podem andar em paralelo depois de US1 (arquivos diferentes, exceto `__main__.py`: T028 e T033 em sequência)
- US4: T029, T030, T031 e T032 em paralelo
- Docs: T037, T038 e T039 em paralelo

---

## Parallel Example: User Story 1

```text
T012 tests/evaluation/test_judging_ac.py
T013 tests/evaluation/test_judging_target.py
T014 tests/evaluation/test_problem_task.py
T015 tests/evaluation/test_integration.py
```

## Parallel Example: User Story 4

```text
T029 tests/evaluation/test_run_config.py
T030 tests/evaluation/test_report.py
T031 tests/evaluation/test_packaging.py
T032 tests/cli/test_consistency.py
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Phases 1 e 2 (base)
2. US1: avaliação das suítes finais com o oráculo declarado; parar e conferir num problema
   (quickstart §2)
3. US2: oráculo corrigido; o MVP só está completo com os dois oráculos, porque o resultado gravado
   precisa servir a TDF\*/MS\* sem nova execução (SC-007)

### Incremental Delivery

1. MVP → conferência num problema
2. US3 → conjunto `slm-attempt1`
3. US4 → retomada, relatório, pacote, `cli check`
4. Documentação → piloto com decisão dos autores → execução completa → pacotes

### Notes

- Um problema só é gravado quando está inteiro (building → rename); interromper nunca deixa
  resultado pela metade
- Antes de commitar (sempre os autores): `pytest`, `check_docs_sync.py`, `ruff`, `black`
