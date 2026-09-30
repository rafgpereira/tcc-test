# Tasks: Geração de Suítes de Teste pelo SLM

**Input**: Design documents from `/specs/003-slm-test-generation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md); Constitution v1.7.0 (`.specify/memory/constitution.md`)

**Tests**: INCLUÍDOS. A Constitution (Princípio VI) exige suíte própria para módulo de
infraestrutura, e o autor pediu "testes automatizados com cliente Ollama falso". Em cada história,
os testes vêm antes da implementação: escreva-os e confirme que **falham** antes de implementar.

**Organization**: tarefas agrupadas por história de usuário (US1 a US4, na ordem de prioridade da
spec), mais uma fase de empacotamento/consistência (FR-028, Princípio II) e o fechamento.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec (US1 a US4); só nas fases de história
- Caminhos relativos à raiz do repositório
- **Onde rodar**: nenhum código gerado pelo modelo roda no host nem no serviço `app`.
  `docker compose run --rm app ...` (com rede: `generate`, `report`, `package`, `verify`, lint,
  `check_docs_sync.py`) ou `docker compose run --rm sandbox ...` (sem rede: `execute` e **todo**
  `pytest`)

## Regras que valem para TODAS as tarefas (Constitution, Princípio XI)

- **📌 PROPAGAR**: uma tarefa marcada com 📌 produz dado medido ou decisão nova. Ela **só está
  concluída** depois de a informação ser escrita, **na própria tarefa**, em
  `docs/metodologia-referencia.md` (seção 3 + nova linha datada na seção 8) **e** nos artefatos
  da feature que ela afeta (`spec.md`, `plan.md`, `research.md`), com data e fonte.
- **Documentação como critério de aceite**: `src/ai_clients/README.md` segue
  [`docs/template-modulo.md`](../../docs/template-modulo.md) (seis campos, dois cenários, uma
  tabela com todos os comandos e variações, nada de spec-kit/`FR-`/`T0xx`) e cada tarefa que o
  toca só termina quando `docker compose run --rm app python scripts/check_docs_sync.py --module
  src/ai_clients --cli "python -m ai_clients" --cli-owner src/ai_clients` sai `0`. Todo comando
  nasce `pendente` na tabela "Comandos verificados" e só é carimbado (data e revisão `git
  rev-parse --short=7 HEAD`, `+dirty` se houver alteração não commitada em `src/`, `scripts/`,
  `pyproject.toml`, `uv.lock`, `Dockerfile` ou compose) na tarefa que o executa de verdade;
  depois de carimbar, `grep` do nome do comando no README do módulo e no da raiz e corrigir prosa
  que o descreva como não executado.
- **Restrições citadas literalmente** de [data-model.md](./data-model.md) e
  [contracts/](./contracts/) fazem parte do aceite; não as reinterprete.
- **Sem estado nas chamadas** (Princípio III): nenhum objeto guarda prompt ou resposta entre
  chamadas; toda requisição tem `messages` com **exatamente um** item e nunca `context`,
  `system`, `format` ou `template`.
- **Nenhum limite absoluto** de tempo/memória no código (Princípio V): só os fatores
  `PY_TIME_FACTOR = 10` e `PY_MEMORY_FACTOR = 4` multiplicando `metadata.json`.
- **Sem dependência nova**: `pyproject.toml`/`uv.lock` não mudam (HTTP por `urllib.request`).
- **O agente nunca roda `git add`/`commit`/`push`** (Princípio X).

## Path Conventions

Pacote novo `src/ai_clients/` e `tests/ai_clients/`; reaproveita sem alteração `src/sandbox/`,
`src/dataset/` e `mutation.dataset_gate` (via import); o `src/cli/` ganha uma camada. O template do
prompt fica em `src/prompt_templates/slm_prompt.txt` (já ajustado para FR-007 em 2026-09-30).

---

## Phase 1: Setup

**Purpose**: esqueleto do pacote e configuração do ambiente.

- [X] T001 Create the package skeleton: `src/ai_clients/__init__.py`, `src/ai_clients/schemas/__init__.py` (vazios) e a pasta `tests/ai_clients/` (sem `__init__.py`, como `tests/mutation/`; `pytest` usa `--import-mode=importlib`)
- [X] T002 Create `src/ai_clients/config.py` com as constantes do desenho (docstring citando `docs/metodologia-referencia.md`, seção 3): `MODEL = "qwen2.5-coder:7b"`; `TEMPERATURE = 0.7`, `TOP_P = 0.8`, `TOP_K = 20`, `REPEAT_PENALTY = 1.05`, `NUM_CTX = 8192`, `NUM_PREDICT = 4096`; `SEED_BASE = 42`, `MAX_ATTEMPTS = 6`, função `seed_for(attempt) -> SEED_BASE + attempt` (1 ≤ attempt ≤ 6, senão `ValueError`); `PY_TIME_FACTOR = 10`, `PY_MEMORY_FACTOR = 4`; padrões `DEFAULT_HTTP_TIMEOUT_S = 900` e `DEFAULT_MAX_INFRA_RETRIES = 30` (sobrescritos por `OLLAMA_HTTP_TIMEOUT_S` e `OLLAMA_MAX_INFRA_RETRIES` do `.env`; research R9/R12); recuo de infraestrutura `BACKOFF_START_S = 5`, `BACKOFF_MAX_S = 60` (dobra a cada espera); `SCENARIOS = ("black_box", "white_box", "hybrid")` (ordem canônica); caminhos `SUITES_DIR = data/suites/slm`, `PROBLEMS_DIR`, `RUN_FILE = run.json`, `LOCK_FILE = .lock`, `REPORT_PATH = manifests/slm_generation_report.json`, `MANIFEST_PATH = manifests/slm_suites.manifest.json`, `ZIP_PATH = data/slm_suites.zip`, `ZIP_ROOT = "suites/slm"`, `PROMPT_TEMPLATE_PATH` (resolvido a partir de `Path(__file__).parents[1] / "prompt_templates" / "slm_prompt.txt"`); nomes das variáveis de ambiente `OLLAMA_BASE_URL`, `OLLAMA_HARDWARE_LABEL`, `OLLAMA_HTTP_TIMEOUT_S`, `OLLAMA_MAX_INFRA_RETRIES`
- [X] T003 [P] Add to `.env.example` as variáveis `OLLAMA_BASE_URL` (ex.: `http://host.docker.internal:11434` para o Ollama da própria máquina; `http://<servidor>:11434` para um remoto) e `OLLAMA_HARDWARE_LABEL` (texto livre descrevendo a máquina onde o Ollama roda, ex.: `RTX 3060 12GB, Ryzen 5 5600`; nunca detectado automaticamente) e as opcionais comentadas `OLLAMA_HTTP_TIMEOUT_S` (padrão 900; aumentar se o Ollama roda em CPU) e `OLLAMA_MAX_INFRA_RETRIES` (padrão 30), com comentários no estilo dos já existentes
- [X] T004 [P] Add `extra_hosts: ["host.docker.internal:host-gateway"]` **só** ao serviço `app` de `docker-compose.yml`, com comentário (Ollama do host no Linux); `sandbox` continua `network_mode: none` (plan.md, S6)
- [X] T005 [P] Create `src/ai_clients/README.md` no template de `docs/template-modulo.md`: `Status: em implementação`, propósito em uma frase, seções (a)–(f) com os dois cenários (do zero / descompactar `data/slm_suites.zip`), tabela única de comandos (`generate`, `execute`, `report`, `package`, `verify` e as variações `--resume`, `--dry-run`, `--limit`, `--problem`, `--scenario`, `--extracted`, e o que a interrupção faz) e tabela "Comandos verificados" com todas as linhas `pendente`; sem citar spec-kit, Constitution, `FR-`/`SC-`, tarefas ou `specs/...` *(feito em 2026-09-30; enquanto o CLI não existe, a tabela lista os subcomandos como **planejados**, sem a forma `python -m ai_clients <sub>` — regra 9 do template e checagem C2, que roda `--help` do CLI; a forma completa entra a partir de T014)*

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: schemas, leitura do problema, trava e fakes de teste usados por todas as histórias.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

### Tests for Foundational ⚠️ (escrever primeiro; devem FALHAR)

- [X] T006 Create `tests/ai_clients/conftest.py` com: (a) `build_dataset(root, problems)` repetindo os passos de `build_dataset` de `tests/mutation/conftest.py` (dataset sintético empacotado, com manifesto e extraído, para o portão `verify_dataset` passar); (b) fixture `problem_files` com 2 problemas sintéticos (`1_A`, `2_B`) com `enunciado.md`, `AC_ref.cpp`, `metadata.json` válido para `Metadata` (limites `time_limit_seconds = 1.0`, `memory_limit_bytes = 268435456`) e `testes.json` com 2 testes públicos; (c) fixture `repo` que chama `build_dataset` em `tmp_path`
- [X] T007 [P] Create `tests/ai_clients/fakes.py`: `FakeSLMClient` (tabela `(problem_id, scenario, seed) → Completion | Exception`; grava cada requisição recebida — corpo JSON completo — em `self.requests`; falha o teste, com a chave, em chamada não prevista; `model_info` devolve `digest`, `quantization_level`, `ollama_version` configuráveis); `FakePythonRunner` (tabela `(código, stdin) → RunResult`, grava chamadas); `FakeClock` (`now()`, `sleep(s)` que só avança o relógio e registra as esperas); construtor `completion(content, *, done_reason="stop", prompt_eval_count=1000, eval_count=500)`; construtor `well_formed_response(inputs: list[str], code: str)`
- [X] T008 [P] Write tests in `tests/ai_clients/test_schemas.py`: `extra` proibido em todo schema; `schema_version` só `1`; `GenerationRecord` rejeita `seed != 42 + attempt` e `attempt` fora de 1–6, e exige `model_digest` não vazio; `ParseResult` com `ok: true` exige `inputs` com ≥ 1 item, cada um não vazio e terminado em exatamente um `\n`, e `reference_py` não vazio; `ExecutionRecord` rejeita `inputs` não vazio quando `public_tests.failed_index` não é nulo, e `outcome` incoerente com os campos (`public_test_failed` ⇔ `failed_index` não nulo; `all_inputs_failed` ⇔ nenhum `kept`); `SlmSuite` rejeita: `accepted` com `accepted_attempt` nulo, `tests` vazio ou `suite_size != len(tests)`; `discarded` sem exatamente 6 tentativas todas com `failure` não nulo, ou com `tests` não vazio; `tests[*]` com campos diferentes de `input`/`output`
- [X] T009 [P] Write tests in `tests/ai_clients/test_problem.py`: `load_problem(root, "1_A")` devolve enunciado, `AC_ref.cpp`, `Metadata` e `Testes` do problema; `testes.json` sem `public_tests` → `ValueError` (o few-shot e a validação precisam de ao menos um); `problem_id` diferente do nome da pasta → erro (herdado de `read_in_folder`); `list_problem_ids(root)` em ordem alfabética
- [X] T010 [P] Write tests in `tests/ai_clients/test_store.py` (parte de base): `ensure_suites_dir` cria `data/suites/slm/problems/` nível a nível; `exclusive_run` impede um segundo comando simultâneo (`AlreadyRunningError`) e solta a trava ao sair por exceção; `write_generation`/`write_execution` recusam sobrescrever arquivo existente; toda escrita é atômica (nenhum `*.tmp` sobra depois de uma exceção simulada no meio)

### Implementation for Foundational

- [X] T011 [P] Implement `src/ai_clients/schemas/generation.py`, `execution.py`, `suite.py`, `run.py` exatamente como [data-model.md](./data-model.md) §2–§3 (herdando `dataset.schemas.common.Schema`, `schema_version: SchemaVersion`), com os enums `Scenario`, `AttemptFailure` (`unparseable_response` · `public_test_failed` · `all_inputs_failed`), `InputDiscard` (`timeout` · `runtime_error` · `non_utf8_output`), `SuiteStatus` (`accepted` · `discarded`); `SlmSuite.tests: list[dataset.schemas.testes.TestCase]` (reaproveitado por import, decisão S2); validadores de T008 (makes T008 pass)
- [X] T012 [P] Implement `src/ai_clients/problem.py`: dataclass imutável `ProblemInput(problem_id, statement, ac_ref, metadata, testes)`, `load_problem(root, problem_id)` compondo `Metadata.from_folder`, `Testes.from_folder` e a leitura de `enunciado.md`/`AC_ref.cpp` (decisão S1: nada novo no pacote `dataset`), `list_problem_ids(root)` (makes T009 pass)
- [X] T013 Implement the foundation of `src/ai_clients/store.py`: `ensure_suites_dir` (via `store.make_private_dir` de `dataset.persistence`), `combination_dir`, `exclusive_run` (`flock` em `data/suites/slm/.lock`, como `mutation.persistence.exclusive_run`; mensagem `another python -m ai_clients command is already running`), `write_generation`, `write_execution` (via `store.atomic_write_json`; `FileExistsError` se o arquivo já existe), `read_generation`, `read_execution` (makes T010 pass)
- [X] T014 Create `src/ai_clients/__main__.py` com o padrão de registro de `mutation/__main__.py` (`Subcommand`, `_REGISTRY`, `register`, `build_parser` em ordem alfabética, `main` com `SIGTERM` → `KeyboardInterrupt`, códigos `EXIT_OK = 0`, `EXIT_DATA_FAILURE = 1`, `EXIT_USAGE = 2`, `EXIT_INFRA = 3`, `EXIT_INTERRUPTED = 130`, `InfraError` e `OllamaConfigError` → 3) e os helpers comuns de [contracts/cli.md](./contracts/cli.md) "Opções comuns": `--problem` (repetível; ID fora de `data/dataset` → 2), `--scenario` (repetível; valores de `config.SCENARIOS`), `--limit` (inteiro positivo, senão 2), `--dry-run`; portão `mutation.dataset_gate.verify_dataset` antes de qualquer trabalho, inclusive no `--dry-run` (divergência → 1; `manifests/dataset.manifest.json` ausente, `FileNotFoundError`, → também 1, com a orientação `unzip data/dataset.zip -d data/`); leitura e validação de `OLLAMA_HTTP_TIMEOUT_S`/`OLLAMA_MAX_INFRA_RETRIES` (inteiro positivo, senão 2; ausentes → padrões de `config.py`)

**Checkpoint**: `docker compose run --rm sandbox pytest tests/ai_clients` passa para T008–T010. *(2026-09-30: 85 testes passando — `test_schemas`, `test_problem`, `test_store`, mais
`test_cli_common` (helpers da T014: opções comuns, portão do dataset, variáveis opcionais do `.env`,
códigos de saída) e `test_gitignore_rule` (exceção `!data/slm_suites.zip`, acrescentada nesta fase
junto com a linha do `ai_clients` em `docs/template-modulo.md`). `ConfigurationError` ficou em
`src/ai_clients/errors.py`, para o `OllamaConfigError` da T022 derivar dela)*

---

## Phase 3: User Story 1 - Gerar candidatos de suíte via SLM, sem executar nada (Priority: P1) 🎯 MVP

**Goal**: `generate` faz uma chamada sem estado por tentativa, persiste resposta crua, entradas,
`reference_py` e seed; falha de interpretação encadeia a próxima seed; falha de infraestrutura
repete a mesma seed sem consumir tentativa.

**Independent Test**: com `FakeSLMClient`, `generate --problem 1_A --scenario black_box` grava
`attempt_1.generation.json` com `raw_response` integral, `parse.inputs`, `parse.reference_py` e
`seed = 43`, sem nenhum processo Python executado.

### Tests for User Story 1 ⚠️ (escrever primeiro; devem FALHAR)

- [ ] T015 [P] [US1] Write tests in `tests/ai_clients/test_prompt.py`: `load_template` falha se qualquer um dos marcadores `(scenario-dependent content)`, `(dataset example input)`, `(dataset example output)` aparecer 0 ou 2+ vezes; guarda o SHA-256 do arquivo; `context_data` = `<problem_statement>\n{enunciado}\n</problem_statement>` (black_box), `<reference_solution_cpp>\n{AC_ref}\n</reference_solution_cpp>` (white_box), os dois separados por uma linha em branco (hybrid); para o mesmo problema os 3 prompts são idênticos fora de `<context_data>…</context_data>` (FR-004); o few-shot é sempre `public_tests[0]` (FR-005), igual nos 3 cenários; `black_box` não contém o `AC_ref.cpp` e `white_box` não contém o enunciado; o template real `src/prompt_templates/slm_prompt.txt` carrega sem erro, **contém** a frase `Every value in every input MUST respect the constraints stated in the context.` e o trecho `the largest case you can write out IN FULL`, e **não contém** `the maximum size allowed by the constraints` (proteção de FR-007 contra edição acidental)
- [ ] T016 [P] [US1] Write tests in `tests/ai_clients/test_parser.py` — tabela de casos de [contracts/ai-clients-api.md](./contracts/ai-clients-api.md) e research R6: resposta bem formada; texto antes/depois/entre blocos ignorado e contado em `extraneous_chars`; cada bloco ausente (`missing_block:<tag>`); cada bloco duplicado (`duplicated_block:<tag>`); ordem trocada (`wrong_order`); bloco não fechado; `<inputs>` sem `<input>` (`no_inputs`); `<input>` vazio ou só espaços (`empty_input`); texto não branco entre `<input>`s (`text_between_inputs`); `<edge_cases_analysis>` ou `<reference_py>` só com espaço (`empty_block:<tag>`); `\r\n` normalizado; linhas brancas das pontas de cada entrada removidas e exatamente um `\n` final, espaços internos preservados; cerca Markdown dentro de `<reference_py>` **mantida**; entradas repetidas mantidas e contadas em `duplicate_inputs`; `<`, `&` dentro do código Python; `parse_response` nunca lança exceção
- [ ] T017 [P] [US1] Write tests in `tests/ai_clients/test_ollama.py` (servidor HTTP local de teste em `127.0.0.1`, porta efêmera, `http.server` numa thread): `OllamaClient.complete` faz `POST /api/chat` com `stream: false`, `messages` com exatamente um item `{"role": "user", "content": prompt}`, sem `context`/`system`/`format`/`template`, e `options` com **todos** os campos de `GenerationOptions`; devolve `Completion` com `content`, `done_reason`, `prompt_eval_count`, `eval_count` e as quatro durações; recusa de conexão, *timeout*, HTTP 500 e corpo não JSON → `OllamaUnavailable`; HTTP 404/400 → `OllamaConfigError`; `model_info` lê `digest` e `details.quantization_level` de `/api/tags` e a versão de `/api/version`, e modelo ausente em `/api/tags` → `OllamaConfigError`; o cliente não guarda nada entre duas chamadas (mesmo `__dict__` antes e depois); o `timeout_s` passado ao construtor é o usado na requisição (servidor que demora mais que ele → `OllamaUnavailable`)
- [ ] T018 [P] [US1] Write tests in `tests/ai_clients/test_generation.py` (com `FakeSLMClient` e `FakeClock`): primeira execução cria `run.json` com `model_digest`, `ollama_version`, `options`, `seed_base = 42`, `prompt_template_sha256`, `dataset_manifest_sha256`, fatores; tentativa 1 usa seed 43; resposta interpretável grava `attempt_1.generation.json` e **não** chama nada de execução; resposta não interpretável grava a falha e faz na hora a tentativa 2 com seed 44 (research R8); 6 respostas não interpretáveis → `attempt_1..6.generation.json` e `suite.json` com `status: discarded`, 6 `failure: unparseable_response`, seeds 43–48; `OllamaUnavailable` 3 vezes e depois sucesso → uma única tentativa gravada, 3 esperas de 5, 10, 20 s no `FakeClock`, mesma seed nas 4 requisições, orçamento intacto (SC-007); com `max_infra_retries = 3`, 4 `OllamaUnavailable` seguidos → exceção de teto atingido (código 3 na CLI), nada gravado para a tentativa, nenhuma tentativa consumida, e uma nova execução refaz a mesma chamada com a mesma seed; o contador de repetições zera depois de uma resposta recebida (falhas intercaladas em chamadas diferentes não somam); `model_digest` gravado em cada `attempt_<n>.generation.json` igual ao do `run.json`; `OllamaConfigError` → nada gravado para a tentativa e erro propagado; guarda de `num_ctx`: `prompt_eval_count + 4096 > 8192` → `OllamaConfigError`, nada gravado; toda requisição do fake tem exatamente uma mensagem (SC-005); `hardware_label` gravado vem da variável de ambiente no momento da chamada; combinação com `suite.json` não é chamada; `pending_execution` não é chamada
- [ ] T019 [P] [US1] Write tests in `tests/ai_clients/test_cli_generate.py`: sem `OLLAMA_BASE_URL` ou `OLLAMA_HARDWARE_LABEL` → código 2 (exceto `--dry-run`); `OLLAMA_HTTP_TIMEOUT_S` ou `OLLAMA_MAX_INFRA_RETRIES` que não é inteiro positivo → código 2; teto de repetições atingido → código 3 com a mensagem de [contracts/cli.md](./contracts/cli.md); `manifests/dataset.manifest.json` ausente → código 1; `--dry-run` não grava nada (nem `run.json`, nem `.lock`) e imprime tamanho do prompt, tentativa e seed por combinação e o maior prompt por cenário; `--limit 2` processa só as 2 primeiras combinações pendentes na ordem canônica (problema em ordem alfabética, depois `black_box`, `white_box`, `hybrid`), contando uma vez a combinação que encadeou falhas de interpretação; `--problem`/`--scenario` filtram; dataset divergente do manifesto → 1 antes de qualquer chamada; resumo final `done: N calls, N parsed, N unparseable, N discarded suites; N pending execution`

### Implementation for User Story 1

- [ ] T020 [P] [US1] Implement `src/ai_clients/prompt.py`: `PromptTemplate` (texto, `sha256`), `load_template`, `context_data`, `build_prompt` conforme research R5 (makes T015 pass)
- [ ] T021 [P] [US1] Implement `src/ai_clients/parser.py`: `parse_response(raw) -> ParseResult`, puro e determinístico, sem correção heurística, regras 1–6 de research R6 (makes T016 pass)
- [ ] T022 [P] [US1] Implement `src/ai_clients/ollama.py`: `GenerationOptions`, `Completion`, `ModelInfo`, `OllamaUnavailable`, `OllamaConfigError`, `SLMClient` (`Protocol`), `OllamaClient` com `urllib.request` e o `timeout_s` recebido no construtor, uma conexão por requisição, classificação de erros de research R9 (makes T017 pass)
- [ ] T023 [US1] Implement `src/ai_clients/generation.py`: `current_run_config(client, template, root)`, `generate(root, combos, client, *, clock, echo, hardware_label, limit)` com o laço de tentativas (falha de interpretação → próxima seed na hora; 6ª falha → `store.finalize`), gravação de `model_digest` em cada tentativa, a espera de infraestrutura com recuo `5 → 10 → 20 → … ≤ 60 s` até `max_infra_retries` repetições consecutivas (contador zerado a cada resposta recebida; teto atingido → exceção que a CLI converte em código 3, nada gravado) e as mensagens `ollama unavailable (<motivo>); retrying the same call (seed S) in T s (retry k of N)` e `ollama unavailable after N consecutive retries …` de [contracts/cli.md](./contracts/cli.md), a guarda de `num_ctx` e a linha por chamada de [contracts/cli.md](./contracts/cli.md) `generate` (makes T018 pass)
- [ ] T024 [US1] Implement in `src/ai_clients/store.py` o que US1 precisa da máquina de estados de [data-model.md](./data-model.md) §4: `combination_state` para `terminal`, `pending_generation(n)`, `pending_execution(n)`, e `finalize` para o caso `discarded` por 6 falhas de interpretação (T024 é completado em US2 e US3)
- [ ] T025 [US1] Register `generate` in `src/ai_clients/__main__.py` com as opções comuns, `--resume` (só a regra "sem `run.json`: cria; com `run.json` e sem `--resume`: código 2 com a mensagem `a run already exists in data/suites/slm; use --resume to continue it`; `--resume` sem `run.json`: código 2" — a comparação de configuração fica em US3, T043) e a leitura de `OLLAMA_BASE_URL`/`OLLAMA_HARDWARE_LABEL` (makes T019 pass)
- [ ] T026 [US1] Update `src/ai_clients/README.md` com o `generate` (serviço `app`, o que grava, o que a interrupção faz, variáveis do `.env`) e confirmar `check_docs_sync.py --module src/ai_clients --cli "python -m ai_clients" --cli-owner src/ai_clients` sai `0`
- [ ] T027 [US1] 📌 PROPAGAR — Rodar `docker compose run --rm app python -m ai_clients generate --dry-run` sobre os 200 problemas reais: confirmar 600 chamadas previstas e o maior prompt por cenário (esperado pela medição de research R3: 7.870 caracteres, híbrido `61_B`; o template foi alterado em 2026-09-30 e ficou alguns caracteres maior — registrar o valor novo); propagar o número em `research.md` R3 e na metodologia (seção 3) e carimbar `generate --dry-run` na tabela do README

**Checkpoint**: US1 testável sozinha com o cliente falso; MVP de geração pronto.

---

## Phase 4: User Story 2 - Calcular a saída esperada por execução real (Priority: P1)

**Goal**: `execute` valida o `reference_py` nos testes públicos e deriva `expected_output`
executando-o na sandbox; descarte de entrada isolada vs. tentativa inteira; 6 falhas → suíte
descartada.

**Independent Test**: com uma `attempt_1.generation.json` fixa (sem Ollama), `execute` grava
`attempt_1.execution.json` e `suite.json` com `tests[*].output` vindo só da execução, limites
`tl × 10` / `ml × 4`, e uma entrada que falha sozinha não derruba as demais.

### Tests for User Story 2 ⚠️ (escrever primeiro; devem FALHAR)

- [ ] T028 [P] [US2] Write tests in `tests/ai_clients/test_oracle.py` (com `FakePythonRunner`): `python_limits` = `ExecutionLimits(time_limit_seconds = tl × 10, memory_limit_bytes = ml × 4)` a partir de `metadata.json` (nunca constante); todos os testes públicos passam → cada entrada roda e `output` = `stdout` decodificado **sem normalização**; o primeiro teste público com WA/TLE/MLE/RE → `outcome: public_test_failed`, `failed_index`/`failed_verdict` gravados, **nenhuma** entrada roda (curto-circuito) e `inputs` vazio; entrada com `TLE` → `discard: timeout`; com `RE` ou `MLE` → `discard: runtime_error` e `verdict` gravado; `stdout` não UTF-8 → `non_utf8_output`; algumas falham → só elas descartadas, com `index` e motivo (FR-019); todas falham (mistura de `timeout` e `runtime_error`) → `outcome: all_inputs_failed`, nunca suíte de tamanho zero (FR-018c); todo veredito vem de `sandbox.judge.judge_test` com os limites multiplicados; `InfraError` do runner propaga e nada é gravado; `AC_ref.cpp` nunca é lido nem executado (o runner falso falha se receber código C++)
- [ ] T029 [P] [US2] Write tests in `tests/ai_clients/test_execution.py`: `execute` processa só `pending_execution`; `accepted` → `attempt_n.execution.json` + `suite.json` (`status: accepted`, `accepted_attempt = n`, `tests` no formato `TestCase` `{input, output}`, `suite_size`, `discarded_inputs`, `duplicate_inputs`, `attempts` com seeds e `hardware_label` de todas as tentativas); falha com `n < 6` → só o `execution.json` e a combinação volta a `pending_generation(n+1)`; falha na tentativa 6 → `suite.json` `discarded` com as 6 razões individuais (Edge Case "razões diferentes"); combinação `finalizable` sem `suite.json` → só grava o `suite.json`; `finalize` é determinística (mesmos arquivos → mesmos bytes); resumo `done: N executed, N accepted, N failed (N need a new generation), N discarded suites` e a linha `next: docker compose run --rm app python -m ai_clients generate --resume` quando sobra geração
- [ ] T030 [P] [US2] Write tests in `tests/ai_clients/test_cli_execute.py`: sem `run.json` → código 2 (`run generate first`); `--dry-run` lista id, cenário, tentativa, nº de entradas, testes públicos e limites efetivos e não grava nada; `--limit`, `--problem`, `--scenario`; `InfraError` → código 3
- [ ] T031 [US2] Write integration tests in `tests/ai_clients/test_oracle_integration.py` (`@pytest.mark.integration`, motor real, serviço `sandbox`), com programas Python conhecidos: correto (eco); `SyntaxError`; laço infinito (vira `TLE` pela reserva de CPU de `tl × 10`); alocação acima de `ml × 4` (`RE`/`MLE`); saída não UTF-8; `import pydantic` falha (só biblioteca padrão, interpretador fora do `venv`, teste `interpreter` do quickstart Nível 0); tentativa de abrir socket falha (sem rede); arquivo escrito numa execução não existe na seguinte (workdir novo); roda como uid de slot, não root; uma solução que só erra uma entrada específica

### Implementation for User Story 2

- [ ] T032 [US2] Implement `src/ai_clients/oracle.py`: `interpreter_path()` = `Path(sys.base_prefix) / "bin" / f"python{major}.{minor}"`; `run_python(code, stdin, limits, slot)` = `isolation.prepare_slot_workdir(slot)` → `main.py` → `isolation.give_to_slot` → `sandbox.runner.execute([interp, "-I", "-S", "-B", "-X", "utf8", "main.py"], stdin=..., slot=..., rlimits=isolation.run_rlimits(limits), cwd=workdir, wall_limit_s=limits_module.wall_reserve_seconds(limits.time_limit_seconds), env={}, measured_by_launcher=True)`; `python_limits(metadata)`; `evaluate_attempt(generation, problem, *, slot=0, runner=run_python) -> ExecutionRecord` conforme research R7 — **nenhuma alteração em `src/sandbox/`** (makes T028 and T031 pass)
- [ ] T033 [US2] Complete `store.combination_state` e `store.finalize` em `src/ai_clients/store.py` para todos os estados de [data-model.md](./data-model.md) §4 (`finalizable` accepted e discarded; `suite.json` como função pura dos arquivos de tentativa; `model`/`model_digest` copiados do `run.json`)
- [ ] T034 [US2] Implement `src/ai_clients/execution.py`: `execute(root, combos, *, runner, echo, limit)` percorrendo `pending_execution` e `finalizable` na ordem canônica, gravando `execution.json` e depois `suite.json`, com a linha por tentativa de [contracts/cli.md](./contracts/cli.md) `execute` (makes T029 pass)
- [ ] T035 [US2] Register `execute` in `src/ai_clients/__main__.py` (sem `--resume`; `isolation.kill_slot_processes(0)` no início, como o `mutation`) (makes T030 pass)
- [ ] T036 [US2] Update `src/ai_clients/README.md` com o `execute` (serviço `sandbox`, sem rede; como alternar com `generate --resume` até não haver `next:`; limites efetivos explicados em linguagem comum) e confirmar `check_docs_sync.py --module src/ai_clients ...` sai `0`
- [ ] T037 [US2] 📌 PROPAGAR — Piloto real (quickstart, Nível 4) com Ollama de verdade, incluindo ao menos um dos 7 problemas de 61 MiB (`--problem`). **Primeiro passo, obrigatório (Constitution, Princípio II)**: `docker compose run --rm app python -m cli check --deep` sai `0` — se não sair, parar e resolver antes de qualquer chamada ao modelo. Depois: `generate --limit 9`, `execute`, `generate --resume --limit 9`, `execute`. Registrar em `research.md` (R3, R6, R7) e na metodologia (seção 3 + linha na seção 8): maior `prompt_eval_count` real (a guarda de `num_ctx` disparou?), taxa de `unparseable_response` por código de erro, de `done_reason = "length"`, de `public_test_failed`, de cerca Markdown no código, tamanho das suítes, tempo por chamada no hardware registrado (máximo real frente ao padrão de `OLLAMA_HTTP_TIMEOUT_S = 900`; se chegar perto, rever o padrão), quantas esperas de infraestrutura ocorreram, e se alguma solução correta falhou por limite de memória/tempo (se sim: rever `PY_MEMORY_FACTOR`/`PY_TIME_FACTOR` com os autores antes de seguir). Carimbar `generate` e `execute` no README. **Não avançar para T055 sem esta tarefa propagada**

**Checkpoint**: US1 + US2 produzem suítes aceitas e descartadas de ponta a ponta.

---

## Phase 5: User Story 3 - Retomar sem duplicar nem corromper (Priority: P2)

**Goal**: interromper `generate` ou `execute` em qualquer ponto e retomar dá o mesmo resultado
final que uma execução ininterrupta; `--resume` recusa configuração alterada.

**Independent Test**: com fakes, interromper em cada ponto de escrita e comparar byte a byte a
árvore final com a de uma execução ininterrupta (SC-004).

### Tests for User Story 3 ⚠️ (escrever primeiro; devem FALHAR)

- [ ] T038 [P] [US3] Write tests in `tests/ai_clients/test_resume.py`: `KeyboardInterrupt` injetado (a) durante a chamada ao modelo, (b) entre `generation.json` e a próxima tentativa, (c) durante a avaliação de uma tentativa, (d) entre `execution.json` e `suite.json` → rodar de novo produz a **mesma árvore** (mesmos nomes e bytes, exceto `requested_at`/`created_at`) que a execução ininterrupta; nenhum `*.tmp` sobra; a tentativa interrompida em (a) é refeita com a **mesma** seed; nenhuma chamada repetida para tentativa já gravada; combinação com `suite.json` nunca é tocada
- [ ] T039 [P] [US3] Write tests in `tests/ai_clients/test_resume_config.py`: `generate --resume` com diferença em **qualquer** campo do `RunConfig` exceto `created_at` — um caso por campo: `model`, `model_digest`, `model_quantization`, `ollama_version`, cada item de `options`, `seed_base`, `max_attempts`, `prompt_template_sha256`, `dataset_manifest_sha256`, `py_time_factor`, `py_memory_factor` — → código 2 listando campo, valor gravado e valor atual; `created_at`, a etiqueta de hardware, `OLLAMA_HTTP_TIMEOUT_S` e `OLLAMA_MAX_INFRA_RETRIES` **não** entram na comparação (trocar de máquina no meio é permitido e fica gravado por tentativa)
- [ ] T040 [P] [US3] Write tests in `tests/ai_clients/test_damage.py`: `attempt_3` sem `attempt_2`, `execution.json` sem `generation.json`, `seed` que não bate, `model_digest` de tentativa diferente do `run.json`, `suite.json` diferente de `finalize(...)` dos arquivos, arquivo JSON inválido → a combinação é reportada como dano (lista do que diverge), não é consertada, os demais seguem e o comando termina com código 1

### Implementation for User Story 3

- [ ] T041 [US3] Garantir em `src/ai_clients/generation.py` e `execution.py` que nada é gravado antes de a unidade (chamada ou avaliação inteira) terminar, e que `main` converte `KeyboardInterrupt` em código 130 com `interrupted; it is safe to run the command again` (makes T038 pass)
- [ ] T042 [US3] Implement a detecção de dano em `src/ai_clients/store.py` (`DamagedCombination` com a lista `missing:`/`changed:`/`inconsistent:`) e seu uso em `generate`/`execute` (makes T040 pass)
- [ ] T043 [US3] Implement a comparação de configuração do `--resume` em `src/ai_clients/generation.py` / `__main__.py` (`RunConfig` atual × `run.json`, todos os campos exceto `created_at`, research R8) (makes T039 pass)
- [ ] T044 [US3] Update `src/ai_clients/README.md`: linha da tabela de comandos sobre interrupção e retomada (`Ctrl+C`/`docker stop` → 130, é seguro rodar de novo; `--resume` recusa se modelo, template, opções ou dataset mudaram) e `check_docs_sync.py --module src/ai_clients ...` sai `0`
- [ ] T045 [US3] 📌 PROPAGAR — Validação real de retomada (quickstart, Nível 5): `Ctrl+C` no `generate` durante uma chamada e no `execute` no meio de uma tentativa; retomar; confirmar sem duplicata/truncamento e mesma seed refeita; registrar em `research.md` (R8) e na metodologia (seção 3 + seção 8)

**Checkpoint**: interromper e retomar é seguro nas duas fases.

---

## Phase 6: User Story 4 - Relatório de geração (Priority: P3)

**Goal**: `report` grava `manifests/slm_generation_report.json` com os números do TCC.

**Independent Test**: sobre uma árvore sintética com suítes aceitas, descartadas e pendentes, os
totais batem e as somas de controle fecham.

### Tests for User Story 4 ⚠️ (escrever primeiro; devem FALHAR)

- [ ] T046 [P] [US4] Write tests in `tests/ai_clients/test_report.py`: todos os campos de [contracts/file-formats.md](./contracts/file-formats.md) §5; `accepted + discarded + pending_generation + pending_execution == total` por cenário e no total; `discard_rate = discarded / total` com `total` sempre o número de combinações do escopo (N nunca reduzido, FR-023/SC-003); `suite_size` (mín., quartis, mediana, máx., histograma) só sobre as aceitas; `attempt_failures` por razão × número da tentativa soma o total de tentativas falhas; `input_discards` por razão; `duplicate_inputs`; `done_reason_length`; `tokens` (`prompt_total`, `eval_total`, `prompt_max`); `hardware` (etiqueta → nº de chamadas); `seeds` por `<id>/<scenario>`; mesma árvore → mesmos bytes; combinação danificada → código 1

### Implementation for User Story 4

- [ ] T047 [US4] Implement `src/ai_clients/schemas/report.py` (`SlmGenerationReport` com as somas de controle validadas) e `src/ai_clients/report.py` (só leitura de `data/suites/slm/`) (makes T046 pass)
- [ ] T048 [US4] Register `report` in `src/ai_clients/__main__.py` (serviço `app`) e documentar no `src/ai_clients/README.md`; `check_docs_sync.py --module src/ai_clients ...` sai `0`

**Checkpoint**: relatório versionável disponível a qualquer momento da execução.

---

## Phase 7: Empacotamento, verificação e consistência entre artefatos (FR-028; Constitution, Princípio II)

**Purpose**: pacote da execução final e a camada `slm_suites` do `python -m cli check`.

- [ ] T049 [P] Write tests in `tests/ai_clients/test_packaging.py`: `package` gera `data/slm_suites.zip` com raiz `suites/slm/problems/…`, `run.json` incluído, `.lock` excluído, datas/permissões/compressão fixas de `dataset.integrity.packaging` (mesma árvore → mesmos bytes); recusa (código 1) se alguma combinação do dataset não tem `suite.json` ou há dano; manifesto `manifests/slm_suites.manifest.json` com SHA-256 de cada arquivo e do zip; `verify` sem opção confere o zip, `--extracted data/suites/slm` confere a árvore, e acha byte alterado, arquivo removido e arquivo extra; sem manifesto → código 2; `unzip data/slm_suites.zip -d data/` recria `data/suites/slm/` idêntico
- [ ] T050 [P] Write tests in `tests/cli/test_consistency.py` para a camada `slm_suites` ([contracts/file-formats.md](./contracts/file-formats.md) §6): repositório consistente passa; problema do dataset sem pasta de suítes, pasta de suítes sem problema, cenário faltando, cenário sem `suite.json` (aviso sem `--deep`, falha com `--deep`), tentativa com buraco, mais de 6 tentativas; `--deep` acha byte alterado; manifesto ausente → aviso; `--only slm_suites`
- [ ] T051 Implement `src/ai_clients/schemas/manifest.py` e `src/ai_clients/packaging.py` (zip, manifesto, `verify`, reaproveitando as constantes de `dataset.integrity.packaging` como `mutation.packaging` faz) e registrar `package` e `verify` em `src/ai_clients/__main__.py` (makes T049 pass)
- [ ] T052 Add `SLM_SUITES_LAYER` a `LAYERS` em `src/cli/consistency.py` (makes T050 pass) e documentar a camada em `docs/verificacao-consistencia.md` e em `src/cli/README.md`
- [ ] T053 Update `src/ai_clients/README.md` com `package`/`verify` e o cenário "descompactar o que já existe" (`unzip data/slm_suites.zip -d data/` + `verify --extracted`); `check_docs_sync.py --module src/ai_clients ...` sai `0`

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: fechar a feature (Constitution, Princípios VI, X e XI).

- [ ] T054 [P] Run lint and format: `docker compose run --rm app ruff check .` e `docker compose run --rm app black --check .`; corrigir até ambos limpos
- [ ] T055 📌 PROPAGAR — Execução completa real. **Primeiro passo, obrigatório (Constitution, Princípio II)**: `docker compose run --rm app python -m cli check --deep` sai `0`; se não sair, parar. Depois alternar `docker compose run --rm app python -m ai_clients generate --resume` e `docker compose run --rm sandbox python -m ai_clients execute` até o `execute` não imprimir `next:`; depois `report`. Registrar em `research.md`, `spec.md` (SC-001, SC-003) e na metodologia (seção 3, nova subseção de resultado + seção 8): 600 combinações terminais, taxa de descarte por cenário e total, distribuição do tamanho das suítes, funil por razão e tentativa, *tokens*, tempo total medido, hardware
- [ ] T056 Run the full suite: `docker compose run --rm sandbox pytest` (inclusive os `integration`); registrar a contagem no relatório final
- [ ] T057 Package the real result: `python -m ai_clients package` e `python -m ai_clients verify --extracted data/suites/slm`, depois `docker compose run --rm app python -m cli check --deep` (`OK`); confirmar que `git status --short` mostra como novidade só `data/slm_suites.zip`, `manifests/slm_suites.manifest.json` e `manifests/slm_generation_report.json` — commitar é decisão do autor (Princípio X); carimbar `report`, `package`, `verify` no README do módulo
- [ ] T058 Execute `quickstart.md` Níveis 0 a 6 e registrar o resultado de cada um (comandos, saída, data) numa seção "Resultado da validação" ao final do arquivo
- [ ] T059 Final update of the root `README.md`: linha de `src/ai_clients/` na tabela "Módulos e estado" (`implementado` para o SLM, link para o README do módulo), "Referência de comandos" com os cinco comandos de `ai_clients` e o serviço de cada, "Estado atual" reescrito com a data, passo do `.env` (`OLLAMA_BASE_URL`, `OLLAMA_HARDWARE_LABEL`) no guia de preparação; `CLAUDE.md` ("Comandos do dia a dia") com os comandos novos; `check_docs_sync.py --only C2,C3,C4` sai `0`
- [ ] T060 Documentation conformity: `src/ai_clients/README.md` → `Status: implementado`; `docker compose run --rm app python scripts/check_docs_sync.py --closing --module src/ai_clients --cli "python -m ai_clients" --cli-owner src/ai_clients` sai `0` (sem linha `pendente`, sem `+dirty`)
- [ ] T061 📌 Methodology synchronization check: `docker compose run --rm app python scripts/check_docs_sync.py --closing --feature specs/003-slm-test-generation` (C1 a C8, CV) sai `0`; para qualquer decisão nova depois do plano, atualizar `sync-matrix.json` e a metodologia; linha final datada na seção 8
- [ ] T062 Constitution v1.7.0 compliance review: refazer a tabela "Constitution Check" de `plan.md` contra o código implementado (em especial III: nenhum `context` enviado; V: nenhum limite absoluto — `grep -rn "memory_limit_bytes=\|time_limit_seconds=" src/ai_clients` só mostra multiplicações de `metadata`); desvios em "Complexity Tracking"; um dos autores revisa o código gerado com apoio de IA (Princípio X) — registrar quem e quando
- [ ] T063 Set `Status:` de `specs/003-slm-test-generation/spec.md` para `Implemented` só se T054–T062 estiverem concluídas, com a linha de fechamento na seção 8 da metodologia; senão manter `Draft` e listar as pendências no relatório final

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 → T002; T003, T004, T005 são `[P]`
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias
- **US1 (Phase 3)**: depende da Fase 2
- **US2 (Phase 4)**: os testes unitários (T028–T030) e `oracle.py` podem começar logo depois da
  Fase 2 (usam `GenerationRecord` fixo); o piloto real T037 depende de US1 completa
- **US3 (Phase 5)**: depende de US1 e US2 (interrompe as duas fases)
- **US4 (Phase 6)**: testável com árvores sintéticas logo depois da Fase 2 + T033; números reais só
  depois de T055
- **Phase 7**: depende de T033 (formato final do `suite.json`); o pacote real só em T057
- **Polish (Phase 8)**: depende de todas as anteriores; T055 depende de T037 propagada

### Within Each User Story

- Testes escritos e vistos falhar antes da implementação
- `schemas` → `problem.py`/`store.py` → `prompt.py`/`parser.py`/`ollama.py` → `generation.py` →
  subcomando; `oracle.py` → `execution.py` → subcomando
- Cada história termina com o README do módulo atualizado e `check_docs_sync.py --module` em `0`

### Parallel Opportunities

- Fase 2: T007–T010 (testes) e T011/T012 (implementação) em arquivos diferentes
- US1: T015–T019 (testes) todos `[P]`; T020, T021, T022 `[P]` entre si
- US2: T028–T030 `[P]`, e podem ser escritos em paralelo com US1 por outra pessoa
- US3: T038–T040 `[P]`
- US4 e Phase 7 (T046, T049, T050) podem ser escritas em paralelo depois de T033

---

## Parallel Example: User Story 1

```bash
# Testes de US1, independentes entre si:
Task: "Write tests in tests/ai_clients/test_prompt.py"
Task: "Write tests in tests/ai_clients/test_parser.py"
Task: "Write tests in tests/ai_clients/test_ollama.py"
Task: "Write tests in tests/ai_clients/test_generation.py"

# Implementação de base, em arquivos diferentes:
Task: "Implement src/ai_clients/prompt.py"
Task: "Implement src/ai_clients/parser.py"
Task: "Implement src/ai_clients/ollama.py"
```

---

## Implementation Strategy

### MVP First (US1 apenas)

1. Phase 1 + Phase 2
2. Phase 3 (US1): `generate` com cliente falso, depois `--dry-run` real (T027)
3. **STOP e VALIDE**: árvore gravada contém resposta crua, entradas, código e seed, sem nenhum
   Python executado

### Incremental Delivery

1. US1 → gerar e guardar respostas (MVP)
2. US2 → `expected_output` por execução real; piloto T037 (ponto de decisão abaixo)
3. US3 → retomada garantida nas duas fases
4. US4 → relatório para o texto do TCC
5. Phase 7 → pacote e `cli check`
6. Phase 8 → execução completa e fechamento

### Ponto de decisão explícito (T037)

O piloto mede se `num_ctx`, os fatores de limite do Python e a redação do template (FR-007)
funcionam com o modelo real. Se a guarda de `num_ctx` disparar, se soluções corretas falharem por
limite, ou se a taxa de `unparseable_response`/`done_reason = "length"` for alta, parar e decidir
com os autores (e propagar) antes da execução completa T055 — mudar o template ou as opções depois
de começar exige uma execução nova (o `--resume` recusa).

## Notes

- `[P]` = arquivos diferentes, sem dependência
- `[Story]` mapeia a tarefa à história, para rastreabilidade
- Confirme que os testes falham antes de implementar
- Commit depois de cada tarefa ou grupo lógico — **decisão sempre do autor** (Princípio X); o
  agente nunca commita
- Pare em qualquer checkpoint para validar uma história isoladamente
