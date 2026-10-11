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

- [X] T015 [P] [US1] Write tests in `tests/ai_clients/test_prompt.py`: `load_template` falha se qualquer um dos marcadores `(scenario-dependent content)`, `(dataset example input)`, `(dataset example output)` aparecer 0 ou 2+ vezes; guarda o SHA-256 do arquivo; `context_data` = `<problem_statement>\n{enunciado}\n</problem_statement>` (black_box), `<reference_solution_cpp>\n{AC_ref}\n</reference_solution_cpp>` (white_box), os dois separados por uma linha em branco (hybrid); para o mesmo problema os 3 prompts são idênticos fora de `<context_data>…</context_data>` (FR-004); o few-shot é sempre `public_tests[0]` (FR-005), igual nos 3 cenários; `black_box` não contém o `AC_ref.cpp` e `white_box` não contém o enunciado; o template real `src/prompt_templates/slm_prompt.txt` carrega sem erro, **contém** a frase `Every value in every input MUST respect the constraints stated in the context.` e o trecho `the largest case you can write out IN FULL`, e **não contém** `the maximum size allowed by the constraints` (proteção de FR-007 contra edição acidental)
- [X] T016 [P] [US1] Write tests in `tests/ai_clients/test_parser.py` — tabela de casos de [contracts/ai-clients-api.md](./contracts/ai-clients-api.md) e research R6: resposta bem formada; texto antes/depois/entre blocos ignorado e contado em `extraneous_chars`; cada bloco ausente (`missing_block:<tag>`); cada bloco duplicado (`duplicated_block:<tag>`); ordem trocada (`wrong_order`); bloco não fechado; `<inputs>` sem `<input>` (`no_inputs`); `<input>` vazio ou só espaços (`empty_input`); texto não branco entre `<input>`s (`text_between_inputs`); `<edge_cases_analysis>` ou `<reference_py>` só com espaço (`empty_block:<tag>`); `\r\n` normalizado; linhas brancas das pontas de cada entrada removidas e exatamente um `\n` final, espaços internos preservados; cerca Markdown dentro de `<reference_py>` **mantida**; entradas repetidas mantidas e contadas em `duplicate_inputs`; `<`, `&` dentro do código Python; `parse_response` nunca lança exceção
- [X] T017 [P] [US1] Write tests in `tests/ai_clients/test_ollama.py` (servidor HTTP local de teste em `127.0.0.1`, porta efêmera, `http.server` numa thread): `OllamaClient.complete` faz `POST /api/chat` com `stream: false`, `messages` com exatamente um item `{"role": "user", "content": prompt}`, sem `context`/`system`/`format`/`template`, e `options` com **todos** os campos de `GenerationOptions`; devolve `Completion` com `content`, `done_reason`, `prompt_eval_count`, `eval_count` e as quatro durações; recusa de conexão, *timeout*, HTTP 500 e corpo não JSON → `OllamaUnavailable`; HTTP 404/400 → `OllamaConfigError`; `model_info` lê `digest` e `details.quantization_level` de `/api/tags` e a versão de `/api/version`, e modelo ausente em `/api/tags` → `OllamaConfigError`; o cliente não guarda nada entre duas chamadas (mesmo `__dict__` antes e depois); o `timeout_s` passado ao construtor é o usado na requisição (servidor que demora mais que ele → `OllamaUnavailable`)
- [X] T018 [P] [US1] Write tests in `tests/ai_clients/test_generation.py` (com `FakeSLMClient` e `FakeClock`): primeira execução cria `run.json` com `model_digest`, `ollama_version`, `options`, `seed_base = 42`, `prompt_template_sha256`, `dataset_manifest_sha256`, fatores; tentativa 1 usa seed 43; resposta interpretável grava `attempt_1.generation.json` e **não** chama nada de execução; resposta não interpretável grava a falha e faz na hora a tentativa 2 com seed 44 (research R8); 6 respostas não interpretáveis → `attempt_1..6.generation.json` e `suite.json` com `status: discarded`, 6 `failure: unparseable_response`, seeds 43–48; `OllamaUnavailable` 3 vezes e depois sucesso → uma única tentativa gravada, 3 esperas de 5, 10, 20 s no `FakeClock`, mesma seed nas 4 requisições, orçamento intacto (SC-007); com `max_infra_retries = 3`, 4 `OllamaUnavailable` seguidos → exceção de teto atingido (código 3 na CLI), nada gravado para a tentativa, nenhuma tentativa consumida, e uma nova execução refaz a mesma chamada com a mesma seed; o contador de repetições zera depois de uma resposta recebida (falhas intercaladas em chamadas diferentes não somam); `model_digest` gravado em cada `attempt_<n>.generation.json` igual ao do `run.json`; `OllamaConfigError` → nada gravado para a tentativa e erro propagado; guarda de `num_ctx`: `prompt_eval_count + 4096 > 8192` → `OllamaConfigError`, nada gravado; toda requisição do fake tem exatamente uma mensagem (SC-005); `hardware_label` gravado vem da variável de ambiente no momento da chamada; combinação com `suite.json` não é chamada; `pending_execution` não é chamada
- [X] T019 [P] [US1] Write tests in `tests/ai_clients/test_cli_generate.py`: sem `OLLAMA_BASE_URL` ou `OLLAMA_HARDWARE_LABEL` → código 2 (exceto `--dry-run`); `OLLAMA_HTTP_TIMEOUT_S` ou `OLLAMA_MAX_INFRA_RETRIES` que não é inteiro positivo → código 2; teto de repetições atingido → código 3 com a mensagem de [contracts/cli.md](./contracts/cli.md); `manifests/dataset.manifest.json` ausente → código 1; `--dry-run` não grava nada (nem `run.json`, nem `.lock`) e imprime tamanho do prompt, tentativa e seed por combinação e o maior prompt por cenário; `--limit 2` processa só as 2 primeiras combinações pendentes na ordem canônica (problema em ordem alfabética, depois `black_box`, `white_box`, `hybrid`), contando uma vez a combinação que encadeou falhas de interpretação; `--problem`/`--scenario` filtram; dataset divergente do manifesto → 1 antes de qualquer chamada; resumo final `done: N calls, N parsed, N unparseable, N discarded suites; N pending execution`

### Implementation for User Story 1

- [X] T020 [P] [US1] Implement `src/ai_clients/prompt.py`: `PromptTemplate` (texto, `sha256`), `load_template`, `context_data`, `build_prompt` conforme research R5 (makes T015 pass)
- [X] T021 [P] [US1] Implement `src/ai_clients/parser.py`: `parse_response(raw) -> ParseResult`, puro e determinístico, sem correção heurística, regras 1–6 de research R6 (makes T016 pass)
- [X] T022 [P] [US1] Implement `src/ai_clients/ollama.py`: `GenerationOptions`, `Completion`, `ModelInfo`, `OllamaUnavailable`, `OllamaConfigError`, `SLMClient` (`Protocol`), `OllamaClient` com `urllib.request` e o `timeout_s` recebido no construtor, uma conexão por requisição, classificação de erros de research R9 (makes T017 pass)
- [X] T023 [US1] Implement `src/ai_clients/generation.py`: `current_run_config(client, template, root)`, `generate(root, combos, client, *, clock, echo, hardware_label, limit)` com o laço de tentativas (falha de interpretação → próxima seed na hora; 6ª falha → `store.finalize`), gravação de `model_digest` em cada tentativa, a espera de infraestrutura com recuo `5 → 10 → 20 → … ≤ 60 s` até `max_infra_retries` repetições consecutivas (contador zerado a cada resposta recebida; teto atingido → exceção que a CLI converte em código 3, nada gravado) e as mensagens `ollama unavailable (<motivo>); retrying the same call (seed S) in T s (retry k of N)` e `ollama unavailable after N consecutive retries …` de [contracts/cli.md](./contracts/cli.md), a guarda de `num_ctx` e a linha por chamada de [contracts/cli.md](./contracts/cli.md) `generate` (makes T018 pass)
- [X] T024 [US1] Implement in `src/ai_clients/store.py` o que US1 precisa da máquina de estados de [data-model.md](./data-model.md) §4: `combination_state` para `terminal`, `pending_generation(n)`, `pending_execution(n)`, e `finalize` para o caso `discarded` por 6 falhas de interpretação (T024 é completado em US2 e US3)
- [X] T025 [US1] Register `generate` in `src/ai_clients/__main__.py` com as opções comuns, `--resume` (só a regra "sem `run.json`: cria; com `run.json` e sem `--resume`: código 2 com a mensagem `a run already exists in data/suites/slm; use --resume to continue it`; `--resume` sem `run.json`: código 2" — a comparação de configuração fica em US3, T043) e a leitura de `OLLAMA_BASE_URL`/`OLLAMA_HARDWARE_LABEL` (makes T019 pass)
- [X] T026 [US1] Update `src/ai_clients/README.md` com o `generate` (serviço `app`, o que grava, o que a interrupção faz, variáveis do `.env`) e confirmar `check_docs_sync.py --module src/ai_clients --cli "python -m ai_clients" --cli-owner src/ai_clients` sai `0`
- [X] T027 [US1] 📌 PROPAGAR — Rodar `docker compose run --rm app python -m ai_clients generate --dry-run` sobre os 200 problemas reais: confirmar 600 chamadas previstas e o maior prompt por cenário (esperado pela medição de research R3: 7.870 caracteres, híbrido `61_B`; o template foi alterado em 2026-09-30 e ficou alguns caracteres maior — registrar o valor novo); propagar o número em `research.md` R3 e na metodologia (seção 3) e carimbar `generate --dry-run` na tabela do README

**Checkpoint**: US1 testável sozinha com o cliente falso; MVP de geração pronto. *(2026-09-30: 170 testes em `tests/ai_clients`
passando; `generate --dry-run` real sobre os 200 problemas: 600 chamadas previstas, maior prompt
8.118 caracteres (híbrido, `61_B`; caixa-preta 6.896, `61_B`; caixa-branca 5.674, `893_C`),
propagado para `research.md` R3, `spec.md`, `quickstart.md`, `config.py` e a metodologia (seção 3 e
seção 8). `generate` também entrou na "Referência de comandos" do `README.md` da raiz. Pendente de
US3: o `--resume` ainda não compara a configuração atual com o `run.json` (T043))*

---

## Phase 4: User Story 2 - Calcular a saída esperada por execução real (Priority: P1)

**Goal**: `execute` valida o `reference_py` nos testes públicos e deriva `expected_output`
executando-o na sandbox; descarte de entrada isolada vs. tentativa inteira; 6 falhas → suíte
descartada.

**Independent Test**: com uma `attempt_1.generation.json` fixa (sem Ollama), `execute` grava
`attempt_1.execution.json` e `suite.json` com `tests[*].output` vindo só da execução, limites
`tl × 10` / `ml × 4`, e uma entrada que falha sozinha não derruba as demais.

### Tests for User Story 2 ⚠️ (escrever primeiro; devem FALHAR)

- [X] T028 [P] [US2] Write tests in `tests/ai_clients/test_oracle.py` (com `FakePythonRunner`): `python_limits` = `ExecutionLimits(time_limit_seconds = tl × 10, memory_limit_bytes = ml × 4)` a partir de `metadata.json` (nunca constante); todos os testes públicos passam → cada entrada roda e `output` = `stdout` decodificado **sem normalização**; o primeiro teste público com WA/TLE/MLE/RE → `outcome: public_test_failed`, `failed_index`/`failed_verdict` gravados, **nenhuma** entrada roda (curto-circuito) e `inputs` vazio; entrada com `TLE` → `discard: timeout`; com `RE` ou `MLE` → `discard: runtime_error` e `verdict` gravado; `stdout` não UTF-8 → `non_utf8_output`; algumas falham → só elas descartadas, com `index` e motivo (FR-019); todas falham (mistura de `timeout` e `runtime_error`) → `outcome: all_inputs_failed`, nunca suíte de tamanho zero (FR-018c); todo veredito vem de `sandbox.judge.judge_test` com os limites multiplicados; `InfraError` do runner propaga e nada é gravado; `AC_ref.cpp` nunca é lido nem executado (o runner falso falha se receber código C++)
- [X] T029 [P] [US2] Write tests in `tests/ai_clients/test_execution.py`: `execute` processa só `pending_execution`; `accepted` → `attempt_n.execution.json` + `suite.json` (`status: accepted`, `accepted_attempt = n`, `tests` no formato `TestCase` `{input, output}`, `suite_size`, `discarded_inputs`, `duplicate_inputs`, `attempts` com seeds e `hardware_label` de todas as tentativas); falha com `n < 6` → só o `execution.json` e a combinação volta a `pending_generation(n+1)`; falha na tentativa 6 → `suite.json` `discarded` com as 6 razões individuais (Edge Case "razões diferentes"); combinação `finalizable` sem `suite.json` → só grava o `suite.json`; `finalize` é determinística (mesmos arquivos → mesmos bytes); resumo `done: N executed, N accepted, N failed (N need a new generation), N discarded suites` e a linha `next: docker compose run --rm app python -m ai_clients generate --resume` quando sobra geração
- [X] T030 [P] [US2] Write tests in `tests/ai_clients/test_cli_execute.py`: sem `run.json` → código 2 (`run generate first`); `--dry-run` lista id, cenário, tentativa, nº de entradas, testes públicos e limites efetivos e não grava nada; `--limit`, `--problem`, `--scenario`; `InfraError` → código 3
- [X] T031 [US2] Write integration tests in `tests/ai_clients/test_oracle_integration.py` (`@pytest.mark.integration`, motor real, serviço `sandbox`), com programas Python conhecidos: correto (eco); `SyntaxError`; laço infinito (vira `TLE` pela reserva de CPU de `tl × 10`); alocação acima de `ml × 4` (`RE`/`MLE`); saída não UTF-8; `import pydantic` falha (só biblioteca padrão, interpretador fora do `venv`, teste `interpreter` do quickstart Nível 0); tentativa de abrir socket falha (sem rede); arquivo escrito numa execução não existe na seguinte (workdir novo); roda como uid de slot, não root; uma solução que só erra uma entrada específica

### Implementation for User Story 2

- [X] T032 [US2] Implement `src/ai_clients/oracle.py`: `interpreter_path()` = `Path(sys.base_prefix) / "bin" / f"python{major}.{minor}"`; `run_python(code, stdin, limits, slot)` = `isolation.prepare_slot_workdir(slot)` → `main.py` → `isolation.give_to_slot` → `sandbox.runner.execute([interp, "-I", "-S", "-B", "-X", "utf8", "main.py"], stdin=..., slot=..., rlimits=isolation.run_rlimits(limits), cwd=workdir, wall_limit_s=limits_module.wall_reserve_seconds(limits.time_limit_seconds), env={}, measured_by_launcher=True)`; `python_limits(metadata)`; `evaluate_attempt(generation, problem, *, slot=0, runner=run_python) -> ExecutionRecord` conforme research R7 — **nenhuma alteração em `src/sandbox/`** (makes T028 and T031 pass)
- [X] T033 [US2] Complete `store.combination_state` e `store.finalize` em `src/ai_clients/store.py` para todos os estados de [data-model.md](./data-model.md) §4 (`finalizable` accepted e discarded; `suite.json` como função pura dos arquivos de tentativa; `model`/`model_digest` copiados do `run.json`)
- [X] T034 [US2] Implement `src/ai_clients/execution.py`: `execute(root, combos, *, runner, echo, limit)` percorrendo `pending_execution` e `finalizable` na ordem canônica, gravando `execution.json` e depois `suite.json`, com a linha por tentativa de [contracts/cli.md](./contracts/cli.md) `execute` (makes T029 pass)
- [X] T035 [US2] Register `execute` in `src/ai_clients/__main__.py` (sem `--resume`; `isolation.kill_slot_processes(0)` no início, como o `mutation`) (makes T030 pass)
- [X] T036 [US2] Update `src/ai_clients/README.md` com o `execute` (serviço `sandbox`, sem rede; como alternar com `generate --resume` até não haver `next:`; limites efetivos explicados em linguagem comum) e confirmar `check_docs_sync.py --module src/ai_clients ...` sai `0`
- [X] T037 [US2] 📌 PROPAGAR — Piloto real (quickstart, Nível 4) com Ollama de verdade, incluindo ao menos um dos 7 problemas de 61 MiB (`--problem`). **Primeiro passo, obrigatório (Constitution, Princípio II)**: `docker compose run --rm app python -m cli check --deep` sai `0` — se não sair, parar e resolver antes de qualquer chamada ao modelo. Depois: `generate --limit 9`, `execute`, `generate --resume --limit 9`, `execute`. Registrar em `research.md` (R3, R6, R7) e na metodologia (seção 3 + linha na seção 8): maior `prompt_eval_count` real (a guarda de `num_ctx` disparou?), taxa de `unparseable_response` por código de erro, de `done_reason = "length"`, de `public_test_failed`, de cerca Markdown no código, tamanho das suítes, tempo por chamada no hardware registrado (máximo real frente ao padrão de `OLLAMA_HTTP_TIMEOUT_S = 900`; se chegar perto, rever o padrão), quantas esperas de infraestrutura ocorreram, e se alguma solução correta falhou por limite de memória/tempo (se sim: rever `PY_MEMORY_FACTOR`/`PY_TIME_FACTOR` com os autores antes de seguir). Carimbar `generate` e `execute` no README. **Não avançar para T055 sem esta tarefa propagada**
  *(2026-10-05: pilotos 1 e 2 feitos e registrados — R13, R14 e metodologia, seção 3 e seção 8.
  O piloto 2 deixou 7 das 15 combinações sem suíte; decidido manter o desenho e o orçamento de 6, e o
  `execute` passou a gravar o diagnóstico do teste público reprovado. Template revisto (R14, item 6). Piloto 3 interrompido em 37 tentativas (R15: 14% de
  acerto por tentativa; bug do `-S` corrigido; `OLLAMA_MODEL` acrescentado). Próximo: piloto 4
  com `qwen2.5-coder:14b` e a decisão do modelo e do método (metodologia, seção 6, item 30).
  Falta para fechar: rodar o piloto final (execução nova, mesmos 5 problemas) começando por `cli check --deep`,
  com `report` no fim; responder com o diagnóstico novo se algum RE foi falta de memória; carimbar
  `generate`/`execute` no README)*

**Checkpoint**: US1 + US2 produzem suítes aceitas e descartadas de ponta a ponta. *(2026-10-01: T028–T036 feitas
com executor Python falso e 11 testes de integração no motor real — 221 testes em `tests/ai_clients`
passando no serviço `sandbox`. `execute` lê só `metadata.json`/`testes.json` (`problem.load_judge_input`).
T033 já estava completa desde US1 (`combination_state`/`finalize` cobrem todos os estados) e foi
confirmada pelos testes de `test_execution.py`. **T037 pendente**: precisa de um Ollama real e do
`.env` com `OLLAMA_BASE_URL`/`OLLAMA_HARDWARE_LABEL`, que não existem nesta máquina)*

---

## Phase 5: User Story 3 - Retomar sem duplicar nem corromper (Priority: P2)

**Goal**: interromper `generate` ou `execute` em qualquer ponto e retomar dá o mesmo resultado
final que uma execução ininterrupta; `--resume` recusa configuração alterada.

**Independent Test**: com fakes, interromper em cada ponto de escrita e comparar byte a byte a
árvore final com a de uma execução ininterrupta (SC-004).

### Tests for User Story 3 ⚠️ (escrever primeiro; devem FALHAR)

- [X] T038 [P] [US3] Write tests in `tests/ai_clients/test_resume.py`: `KeyboardInterrupt` injetado (a) durante a chamada ao modelo, (b) entre `generation.json` e a próxima tentativa, (c) durante a avaliação de uma tentativa, (d) entre `execution.json` e `suite.json` → rodar de novo produz a **mesma árvore** (mesmos nomes e bytes, exceto `requested_at`/`created_at`) que a execução ininterrupta; nenhum `*.tmp` sobra; a tentativa interrompida em (a) é refeita com a **mesma** seed; nenhuma chamada repetida para tentativa já gravada; combinação com `suite.json` nunca é tocada
- [X] T039 [P] [US3] Write tests in `tests/ai_clients/test_resume_config.py`: `generate --resume` com diferença em **qualquer** campo do `RunConfig` exceto `created_at` — um caso por campo: `model`, `model_digest`, `model_quantization`, `ollama_version`, cada item de `options`, `seed_base`, `max_attempts`, `prompt_template_sha256`, `dataset_manifest_sha256`, `py_time_factor`, `py_memory_factor` — → código 2 listando campo, valor gravado e valor atual; `created_at`, a etiqueta de hardware, `OLLAMA_HTTP_TIMEOUT_S` e `OLLAMA_MAX_INFRA_RETRIES` **não** entram na comparação (trocar de máquina no meio é permitido e fica gravado por tentativa)
- [X] T040 [P] [US3] Write tests in `tests/ai_clients/test_damage.py`: `attempt_3` sem `attempt_2`, `execution.json` sem `generation.json`, `seed` que não bate, `model_digest` de tentativa diferente do `run.json`, `suite.json` diferente de `finalize(...)` dos arquivos, arquivo JSON inválido → a combinação é reportada como dano (lista do que diverge), não é consertada, os demais seguem e o comando termina com código 1

### Implementation for User Story 3

- [X] T041 [US3] Garantir em `src/ai_clients/generation.py` e `execution.py` que nada é gravado antes de a unidade (chamada ou avaliação inteira) terminar, e que `main` converte `KeyboardInterrupt` em código 130 com `interrupted; it is safe to run the command again` (makes T038 pass)
- [X] T042 [US3] Implement a detecção de dano em `src/ai_clients/store.py` (`DamagedCombination` com a lista `missing:`/`changed:`/`inconsistent:`) e seu uso em `generate`/`execute` (makes T040 pass)
- [X] T043 [US3] Implement a comparação de configuração do `--resume` em `src/ai_clients/generation.py` / `__main__.py` (`RunConfig` atual × `run.json`, todos os campos exceto `created_at`, research R8) (makes T039 pass)
- [X] T044 [US3] Update `src/ai_clients/README.md`: linha da tabela de comandos sobre interrupção e retomada (`Ctrl+C`/`docker stop` → 130, é seguro rodar de novo; `--resume` recusa se modelo, template, opções ou dataset mudaram) e `check_docs_sync.py --module src/ai_clients ...` sai `0`
- [X] T045 [US3] 📌 PROPAGAR — Validação real de retomada (quickstart, Nível 5): `Ctrl+C` no `generate` durante uma chamada e no `execute` no meio de uma tentativa; retomar; confirmar sem duplicata/truncamento e mesma seed refeita; registrar em `research.md` (R8) e na metodologia (seção 3 + seção 8)
  *(2026-10-11: observada na execução completa — os logs `data/logs/gpu0.log`, `gpu1.log` e
  `gpu2.log` têm 44 linhas `interrupted; it is safe to run the command again` (18 + 22 + 4) de
  `generate` interrompidos; cada vez o `--resume` continuou, e o estado final não tem perda nem
  dano (`cli check` OK, 600/600, tentativas sem buraco). Registrado em `research.md` R28, item 3, e
  na metodologia)*

**Checkpoint**: interromper e retomar é seguro nas duas fases. *(2026-10-01: T038–T044 feitas com fakes — 258
testes em `tests/ai_clients` passando. T041 não precisou de código novo: nada era gravado antes de
a unidade terminar, e o `main` já convertia `KeyboardInterrupt` em 130; os testes de T038 o
confirmam. Decisão de implementação: o `generate` também grava o `suite.json` de uma combinação
`finalizable` que encontrar, e no `execute` o `finalizable` não conta para o `--limit`
(`contracts/cli.md`). **T045 pendente**: precisa do Ollama real)*

---

## Phase 6: User Story 4 - Relatório de geração (Priority: P3)

**Goal**: `report` grava `manifests/slm_generation_report.json` com os números do TCC.

**Independent Test**: sobre uma árvore sintética com suítes aceitas, descartadas e pendentes, os
totais batem e as somas de controle fecham.

### Tests for User Story 4 ⚠️ (escrever primeiro; devem FALHAR)

- [X] T046 [P] [US4] Write tests in `tests/ai_clients/test_report.py`: todos os campos de [contracts/file-formats.md](./contracts/file-formats.md) §5; `accepted + discarded + pending_generation + pending_execution == total` por cenário e no total; `discard_rate = discarded / total` com `total` sempre o número de combinações do escopo (N nunca reduzido, FR-023/SC-003); `suite_size` (mín., quartis, mediana, máx., histograma) só sobre as aceitas; `attempt_failures` por razão × número da tentativa soma o total de tentativas falhas; `input_discards` por razão; `duplicate_inputs`; `done_reason_length`; `tokens` (`prompt_total`, `eval_total`, `prompt_max`); `hardware` (etiqueta → nº de chamadas); `seeds` por `<id>/<scenario>`; mesma árvore → mesmos bytes; combinação danificada → código 1

### Implementation for User Story 4

- [X] T047 [US4] Implement `src/ai_clients/schemas/report.py` (`SlmGenerationReport` com as somas de controle validadas) e `src/ai_clients/report.py` (só leitura de `data/suites/slm/`) (makes T046 pass)
- [X] T048 [US4] Register `report` in `src/ai_clients/__main__.py` (serviço `app`) e documentar no `src/ai_clients/README.md`; `check_docs_sync.py --module src/ai_clients ...` sai `0`

**Checkpoint**: relatório versionável disponível a qualquer momento da execução. *(2026-10-01: T046–T048
feitas com árvores sintéticas. Regras fixadas na implementação e propagadas para
`contracts/file-formats.md` §5: bloco `attempts` para validar o funil, quartis por interpolação
linear, `input_discards` sobre todas as tentativas executadas, `duplicate_inputs` só das suítes
aceitas)*

---

## Phase 7: Empacotamento, verificação e consistência entre artefatos (FR-028; Constitution, Princípio II)

**Purpose**: pacote da execução final e a camada `slm_suites` do `python -m cli check`.

- [X] T049 [P] Write tests in `tests/ai_clients/test_packaging.py`: `package` gera `data/slm_suites.zip` com raiz `suites/slm/problems/…`, `run.json` incluído, `.lock` excluído, datas/permissões/compressão fixas de `dataset.integrity.packaging` (mesma árvore → mesmos bytes); recusa (código 1) se alguma combinação do dataset não tem `suite.json` ou há dano; manifesto `manifests/slm_suites.manifest.json` com SHA-256 de cada arquivo e do zip; `verify` sem opção confere o zip, `--extracted data/suites/slm` confere a árvore, e acha byte alterado, arquivo removido e arquivo extra; sem manifesto → código 2; `unzip data/slm_suites.zip -d data/` recria `data/suites/slm/` idêntico
- [X] T050 [P] Write tests in `tests/cli/test_consistency.py` para a camada `slm_suites` ([contracts/file-formats.md](./contracts/file-formats.md) §6): repositório consistente passa; problema do dataset sem pasta de suítes, pasta de suítes sem problema, cenário faltando, cenário sem `suite.json` (aviso sem `--deep`, falha com `--deep`), tentativa com buraco, mais de 6 tentativas; `--deep` acha byte alterado; manifesto ausente → aviso; `--only slm_suites`
- [X] T051 Implement `src/ai_clients/schemas/manifest.py` e `src/ai_clients/packaging.py` (zip, manifesto, `verify`, reaproveitando as constantes de `dataset.integrity.packaging` como `mutation.packaging` faz) e registrar `package` e `verify` em `src/ai_clients/__main__.py` (makes T049 pass)
- [X] T052 Add `SLM_SUITES_LAYER` a `LAYERS` em `src/cli/consistency.py` (makes T050 pass) e documentar a camada em `docs/verificacao-consistencia.md` e em `src/cli/README.md`
- [X] T053 Update `src/ai_clients/README.md` com `package`/`verify` e o cenário "descompactar o que já existe" (`unzip data/slm_suites.zip -d data/` + `verify --extracted`); `check_docs_sync.py --module src/ai_clients ...` sai `0`

*(2026-10-01: Phase 7 feita — 12 testes de pacote e 17 da camada `slm_suites` (o `build()` de
`tests/cli/test_consistency.py` passou a montar também uma árvore SLM empacotada). **Divergência
decidida na implementação**, propagada para `contracts/file-formats.md` §6, `research.md` R10,
`docs/verificacao-consistencia.md` e a metodologia: na camada `slm_suites` o que falta é aviso até o
manifesto existir, mesmo com `--deep` — o contrato pedia falha com `--deep`, o que tornaria
impossível o primeiro passo de T037 e T055. Manifesto com a chave `slm_suites_zip`, como o dos
mutantes (o data-model §3.6 dizia `zip`))*

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: fechar a feature (Constitution, Princípios VI, X e XI).

- [X] T054 [P] Run lint and format: `docker compose run --rm app ruff check .` e `docker compose run --rm app black --check .`; corrigir até ambos limpos *(2026-10-01: `black --check .` limpo; `ruff check .` limpo
exceto `EXE002` em todos os arquivos do repositório, inclusive os não tocados — artefato do bind
mount do Windows, que mostra todo arquivo como executável; `ruff check . --extend-ignore EXE002`
limpo)*
- [X] T055 📌 PROPAGAR — Execução completa real. **Primeiro passo, obrigatório (Constitution, Princípio II)**: `docker compose run --rm app python -m cli check --deep` sai `0`; se não sair, parar. Depois alternar `docker compose run --rm app python -m ai_clients generate --resume` e `docker compose run --rm sandbox python -m ai_clients execute` até o `execute` não imprimir `next:`; depois `report`. Registrar em `research.md`, `spec.md` (SC-001, SC-003) e na metodologia (seção 3, nova subseção de resultado + seção 8): 600 combinações terminais, contagem por status (`accepted`, `accepted_fallback`, `accepted_predicted`, `discarded_manual`, aguardando) por cenário e total, fase e tentativa da suíte, distribuição do tamanho das suítes, funil por razão e tentativa, *tokens*, tempo de modelo medido, hardware
  *(2026-10-11: execução completa feita de 2026-10-06 a 2026-10-09, como continuação do piloto 6 —
  505 `accepted`, 93 `accepted_fallback`, 2 `accepted_predicted`, 0 `discarded_manual`, 0
  aguardando; registrada em `research.md` R28, na spec (sessão de 2026-10-11, SC-003) e na
  metodologia)*
- [X] T056 Run the full suite: `docker compose run --rm sandbox pytest` (inclusive os `integration`); registrar a contagem no relatório final *(feito em 2026-10-11: `1498 passed in 228.97s`, revisão `c967f97`)*
- [X] T057 Package the real result: `python -m ai_clients package` e `python -m ai_clients verify --extracted data/suites/slm`, depois `docker compose run --rm app python -m cli check --deep` (`OK`); confirmar que `git status --short` mostra como novidade só `data/slm_suites.zip`, `manifests/slm_suites.manifest.json` e `manifests/slm_generation_report.json` (além dos relatórios dos pilotos 2 e 3 em `manifests/`, versionados como registro), e que o zip leva `template_changes/` e `superseded/` (a troca de 2026-10-08) — commitar é decisão do autor (Princípio X); carimbar `report`, `package`, `verify` no README do módulo *(feito em 2026-10-11: zip de 6.597.040 bytes com 4.850 arquivos, inclusive `template_changes/` e `superseded/`; `verify --extracted` `OK`; `cli check --deep` `OK` sem aviso; `package` e `verify` carimbados; R28)*
- [X] T058 Execute `quickstart.md` Níveis 0 a 6 e registrar o resultado de cada um (comandos, saída, data) numa seção "Resultado da validação" ao final do arquivo *(feito em 2026-10-11: "Resultado da validação" no fim do quickstart; níveis 0 a 3 rodados de novo, 4 a 8 validados pela execução real)*
- [X] T059 Final update of the root `README.md`: linha de `src/ai_clients/` na tabela "Módulos e estado" (`implementado` para o SLM, link para o README do módulo), "Referência de comandos" com os cinco comandos de `ai_clients` e o serviço de cada, "Estado atual" reescrito com a data, passo do `.env` (`OLLAMA_BASE_URL`, `OLLAMA_HARDWARE_LABEL`) no guia de preparação; `CLAUDE.md` ("Comandos do dia a dia") com os comandos novos; `check_docs_sync.py --only C2,C3,C4` sai `0` *(feito em 2026-10-11: módulo `implementado` na tabela, "Estado atual" e referência de comandos com os sete subcomandos; `CLAUDE.md` atualizado)*
- [X] T060 Documentation conformity: `src/ai_clients/README.md` → `Status: implementado`; `docker compose run --rm app python scripts/check_docs_sync.py --closing --module src/ai_clients --cli "python -m ai_clients" --cli-owner src/ai_clients` sai `0` (sem linha `pendente`, sem `+dirty`) *(feito em 2026-10-11)*
- [X] T061 📌 Methodology synchronization check: `docker compose run --rm app python scripts/check_docs_sync.py --closing --feature specs/003-slm-test-generation` (C1 a C8, CV) sai `0`; para qualquer decisão nova depois do plano, atualizar `sync-matrix.json` e a metodologia; linha final datada na seção 8 *(feito em 2026-10-11; linha de fechamento na seção 8)*
- [X] T062 Constitution v1.7.0 compliance review: refazer a tabela "Constitution Check" de `plan.md` contra o código implementado (em especial III: nenhum `context` enviado; V: nenhum limite absoluto — `grep -rn "memory_limit_bytes=\|time_limit_seconds=" src/ai_clients` só mostra multiplicações de `metadata`); desvios em "Complexity Tracking"; um dos autores revisa o código gerado com apoio de IA (Princípio X) — registrar quem e quando *(feito em 2026-10-11: tabela refeita em `plan.md`, "Reavaliação de fechamento", sem desvio; o código gerado com apoio de IA foi revisado por Milena em 2026-10-11)*
- [X] T063 Set `Status:` de `specs/003-slm-test-generation/spec.md` para `Implemented` só se T054–T062 estiverem concluídas, com a linha de fechamento na seção 8 da metodologia; senão manter `Draft` e listar as pendências no relatório final *(feito em 2026-10-11: T054 a T062 concluídas; `Status: Implemented (2026-10-11)`)*

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

## Phase 9: Convergence

Trabalho que falta para a regra "nenhuma combinação sem suíte" (spec FR-022 a FR-022d, research
R18 e R19, data-model §3–4, contratos). Valem as regras do topo: teste antes da implementação,
confirmado falhando; 📌 PROPAGAR onde marcado; tudo rodado com `docker compose run --rm sandbox
pytest tests/ai_clients tests/cli`. As árvores dos pilotos 1 a 4 não são lidas pelo código novo.

- [X] T064 Atualizar `src/ai_clients/config.py` (`STRICT_ATTEMPTS = 8`, `SOLUTION_ATTEMPTS = 20`, `PREDICT_ATTEMPTS = 3`, `MAX_ATTEMPTS = 23`, `attempt_kind`, `PREDICT_TEMPLATE_PATH`, `MANUAL_CLOSE_FILE`; `seed_for` de 1 a 23) e `src/ai_clients/schemas/run.py` (`solution_attempts`, `predict_attempts`, `predict_template_sha256`, `max_attempts == solution_attempts + predict_attempts`), com `generation.current_run_config` e `--resume` comparando os campos novos; testes em `tests/ai_clients/test_schemas.py` e `tests/ai_clients/test_resume_config.py` per FR-020, FR-022, plan R19 itens 1 e 6 (missing)
- [X] T065 Rodar as entradas geradas depois de **qualquer** reprovação em teste público em `src/ai_clients/oracle.py` (`evaluate_attempt`) e exigir isso em `src/ai_clients/schemas/execution.py` (`inputs` com um item por entrada sempre que a resposta foi interpretada), com a mensagem do `execute` (`public_test_failed (test <i>: <verdict>; <k> kept, <d> discarded)`, `src/ai_clients/execution.py`); testes em `tests/ai_clients/test_oracle.py`, `test_execution.py` e um caso de integração em `tests/ai_clients/test_oracle_integration.py` (solução com RE no teste público que roda as entradas) per FR-018(b), research R19 item 2 (contradicts)
- [X] T066 Trocar `SuiteStatus` em `src/ai_clients/schemas/common.py` (`accepted`, `accepted_fallback`, `accepted_low_confidence`, `accepted_predicted`, `discarded_manual`; sai `discarded`) e reescrever as validações de `SlmSuite`/`AttemptSummary` em `src/ai_clients/schemas/suite.py` (`kind`, `low_confidence_eligible`, `manual_close`, regras de data-model §3.4); testes em `tests/ai_clients/test_schemas.py` per FR-022, SC-001, data-model §3.4 (contradicts)
- [X] T067 Estender a máquina de estados de `src/ai_clients/store.py` (data-model §4): tentativas extras de 9 a 20 parando na primeira `accepted` ou reserva; depois da 20ª, `accepted_low_confidence` da primeira tentativa `low_confidence_eligible`; sem nenhuma, `pending_generation(21)`; detecção dos danos novos (execução de tentativa > 20, tentativa > 20 com reserva ou baixa confiança possível); testes em `tests/ai_clients/test_store.py`, `test_damage.py` e `test_resume.py` per FR-022a, FR-022b (partial)
- [X] T068 [P] Gravar `src/prompt_templates/slm_predict_prompt.txt` com o texto enviado pela Milena em 2026-10-06, sem alteração (2.333 caracteres; os 3 marcadores de `prompt.py` uma vez cada), e criar `parse_prediction` em `src/ai_clients/parser.py` e `PredictionParse` em `src/ai_clients/schemas/generation.py` (regras de research R19 item 4; o `GenerationRecord` só aceita `PredictionParse` nas tentativas 21 a 23); testes em `tests/ai_clients/test_parser_prediction.py` (tabela de contracts/ai-clients-api.md), `test_prompt.py` (template de predição carrega; ordem dos blocos igual à do parser) e `test_schemas.py` per FR-022c, FR-009 (missing)
- [X] T069 Usar o template e o parser de predição nas tentativas 21 a 23 em `src/ai_clients/generation.py` (por `attempt_kind`; a interpretada vira `suite.json` `accepted_predicted` no próprio `generate`; não interpretada encadeia a próxima seed) e gravar `suite.json(accepted_predicted)` em `store._build_suite`; `GenerateResult`/`ExecuteResult` com contadores por status; testes em `tests/ai_clients/test_generation.py` e `test_cli_generate.py` (cliente falso conferindo uma mensagem por requisição também na predição) per FR-022c, Constitution III (missing)
- [X] T070 Criar o estado `awaiting_manual` em `src/ai_clients/store.py` (23 tentativas, a 23ª não interpretada, sem `manual_close.json`) e, em `src/ai_clients/__main__.py`, o código de saída `EXIT_MANUAL = 4` no `generate` e no `execute`: linhas `manual: <id> <scenario>: …` com o comando `close` para toda combinação da seleção nesse estado, resumo final novo (contracts/cli.md) e precedência de `130`/`3`/`1` sobre o `4`; testes em `tests/ai_clients/test_cli_generate.py` e `test_cli_execute.py` (inclusive outras combinações concluídas no mesmo comando) per FR-022, research R19 item 7 (missing)
- [X] T071 Criar o comando `python -m ai_clients close --problem ID --scenario S --reason TEXTO [--dry-run]` (`src/ai_clients/closing.py` + registro em `src/ai_clients/__main__.py`, serviço `app`, trava e verificação do dataset como os demais): só aceita `awaiting_manual` (senão código 2), grava `manual_close.json` (`ManualClose`, schema novo) e depois `suite.json(discarded_manual)` com `manual_close` copiado; `store` trata `manual_close.json` fora desse estado como dano; testes em `tests/ai_clients/test_closing.py` e `test_cli_close.py` per FR-022d, research R19 item 8 (missing)
- [X] T072 Reescrever o relatório por status em `src/ai_clients/schemas/report.py` e `src/ai_clients/report.py` (`combinations` com os 5 status + `awaiting_manual` + pendentes, `status_rate`, `suite_size` por status, `attempt_failures` de 1 a 23, `empty_tests`, `predict_template_sha256`; somas de controle) e a contagem/recusa de `src/ai_clients/packaging.py` (combinações aguardando listadas com o comando `close`); testes em `tests/ai_clients/test_report.py` e `test_packaging.py` per FR-023, FR-027, FR-028 (partial)
- [X] T073 [P] Atualizar a camada `slm_suites` de `src/cli/consistency.py` (`SLM_MAX_ATTEMPTS = 23`, nenhuma execução de tentativa > 20, `manual_close.json` permitido) e `docs/verificacao-consistencia.md`; testes em `tests/cli/test_consistency.py` per research R19 item 11, contracts/file-formats.md §6 (partial)
- [X] T074 📌 PROPAGAR — Atualizar `src/ai_clients/README.md` (as 23 tentativas na ordem de FR-022, os 5 status, o código 4, o comando `close` na tabela única de comandos, sem citar spec/tarefas), o `README.md` da raiz ("Referência de comandos" com `close`, linha do módulo, "Estado atual") e `CLAUDE.md` ("Comandos do dia a dia"); depois, procurar por grep "12 tentativas", "discarded" e "até 12" nos dois READMEs e corrigir toda prosa que contradiga a tabela; marcar a seção 3 de `docs/metodologia-referencia.md` como implementada, com linha datada na seção 8; `docker compose run --rm app python scripts/check_docs_sync.py` sai `0` per Constitution XI (partial)

## Phase 10: Piloto 6 — temperatura e seeds (2026-10-06, `research.md` R20)

> **Substituída no mesmo dia pela política de 5 fases (`research.md` R21).** T075 foi
> implementada mas não testada (Docker fora do ar), e as variáveis dela saem com R21; T076 a
> T078 não serão feitas. As tarefas da política nova saem do próximo `/speckit-plan` +
> `/speckit-tasks` (ou `/speckit-converge`).

Antes da execução completa (T055). Mesmos 5 problemas × 3 cenários (`--problem 1000_B --problem
1005_C --problem 1008_B --problem 1_B --problem 61_B`), `qwen2.5-coder:14b`, uma execução nova por
configuração (antes de cada uma, `mv data/suites/slm data/suites/slm-piloto6-<config>`; o piloto 5
já está em `data/suites/slm-piloto5` e vale como temperatura 0,7 com seed base 42).

- [X] T075 *(cancelada em 2026-10-11: fase substituída pela política de 5 fases)* `OLLAMA_TEMPERATURE` e `OLLAMA_SEED_BASE` opcionais no `.env` (`src/ai_clients/__main__.py`, `generation.current_run_config`), gravados no `run.json` e comparados no `--resume`; seed conferida pelo `store` contra a `seed_base` do `run.json`; `config.MODEL = "qwen2.5-coder:14b"`; testes em `tests/ai_clients/test_cli_generate.py`, `test_schemas.py` e `test_damage.py` per R20, decisões 1 e 4
- [X] T076 *(cancelada em 2026-10-11: fase substituída pela política de 5 fases)* 📌 PROPAGAR — Rodar as temperaturas 0,2; 0,3; 0,4; 0,5; 0,6 com seed base 42 (`OLLAMA_TEMPERATURE` no `.env`; primeiro passo de cada uma: `docker compose run --rm app python -m cli check --deep` sai `0`); para cada uma, registrar suítes por status, tentativas aceitas/feitas, falhas por veredito, tempo por chamada e total de modelo
- [X] T077 *(cancelada em 2026-10-11: fase substituída pela política de 5 fases)* 📌 PROPAGAR — Repetir a melhor temperatura de T076 e a 0,7 com `OLLAMA_SEED_BASE` 1042 e 2042; escolher a configuração pelo critério de R20 (mais `accepted`, depois acerto por tentativa, depois tempo) e registrar a escolha e a variação entre seeds em `research.md` (R21), na metodologia (seção 3 + seção 8) e na spec
- [X] T078 *(cancelada em 2026-10-11: fase substituída pela política de 5 fases)* Fixar a temperatura escolhida em `src/ai_clients/config.py` (`TEMPERATURE`), com os testes que dependem dela, antes de T055; tirar `OLLAMA_TEMPERATURE`/`OLLAMA_SEED_BASE` do `.env` da execução completa

## Phase 11: Convergence

Política de 5 fases (spec FR-018, FR-020, FR-022 a FR-022d, FR-023, FR-027; research R21 e R22;
data-model §2–4; contratos). Valem as regras do topo (teste antes, 📌 PROPAGAR); tudo conferido com
`docker compose run --rm sandbox pytest tests/ai_clients tests/cli`. Substitui a fase 10.

- [X] T079 Criar `config.ATTEMPT_POLICY` (as 15 linhas de data-model §2 por extenso, `AttemptSpec(attempt, phase, seed, temperature, template)`, `attempt_spec(n)`, validação ao importar; `SOLUTION_ATTEMPTS = 12`, `MAX_ATTEMPTS = 15` derivados) e tirar `STRICT_ATTEMPTS`, `PREDICT_ATTEMPTS`, `SEED_BASE`, `seed_for` e `attempt_kind`; `RunConfig.attempt_policy` no lugar de `seed_base`/`*_attempts` e temperatura fora de `options`, com `differences` linha a linha; `generation_options(run, n)` com a seed e a temperatura da linha `n`; testes em `tests/ai_clients/test_config.py` (novo: tabela exata, nenhum par (seed, temperatura) repetido), `test_resume_config.py` e `test_generation.py` (seed e temperatura enviadas em cada pedido) per FR-020, R22 itens 1 e 2 (missing)
- [X] T080 Reescrever a máquina de estados de `src/ai_clients/store.py` e as validações de `schemas/suite.py` para 15 tentativas (data-model §4): parada na primeira `accepted` nas fases 1 e 2, reserva só depois da 12ª (fase 3), predição direto na 13ª sem reserva, `awaiting_manual` depois da 15ª; tirar `accepted_low_confidence`, `low_confidence_eligible` e as tentativas extras; dano para tentativa ≥ 13 com reserva possível; testes em `test_execution.py`, `test_generation.py`, `test_store.py`, `test_damage.py` e `test_schemas.py` per FR-022, FR-022a, FR-022c, R22 item 5 (contradicts)
- [X] T081 Voltar a rodar as entradas só quando a solução passa em todos os testes públicos ou o primeiro erro é WA (`oracle.evaluate_attempt`, `schemas/execution.py`, mensagem do `execute`); testes em `test_oracle.py`, `test_schemas.py` e no teste de integração com RE (as entradas não rodam) per FR-018(b), R22 item 6 (contradicts)
- [X] T082 Passar todos os schemas do módulo a `schema_version` 2 (`ai_clients.schemas.common.SchemaVersion = Literal[2]`); `phase`, `temperature` e `template` em `GenerationRecord`, conferidos pelo `store` contra a linha do `attempt_policy` do `run.json` (divergência é dano); `phase`, `temperature` e `template` em `AttemptSummary` e `accepted_phase` em `SlmSuite`; testes em `test_schemas.py` e `test_damage.py` per R22 item 3 (missing)
- [X] T083 Criar `store.IncompatibleRunError` em `read_run` para um `run.json` que não valida como `schema_version` 2, tratada em `generate`, `execute`, `close`, `report` e `package` com código 2 e a mensagem de contracts/cli.md (mover `data/suites/slm`); testes em `test_cli_generate.py`, `test_cli_execute.py`, `test_cli_close.py`, `test_report.py` e `test_packaging.py` per R22 item 4 (missing)
- [X] T084 Reescrever o relatório (`schemas/report.py`, `report.py`, `schema_version` 2): status sem `accepted_low_confidence`, `attempt_policy` no lugar de `seed_base`, `acceptance` (por cenário e total, `by_phase` 1–4 e `by_attempt` 1–15) e `per_phase` (fases 1, 2 e 4: `calls`, `failed`, `prompt_tokens`, `eval_tokens`, `duration_s`), `attempt_failures` de 1 a 15, com as somas de controle de data-model §3.5; teste em `test_report.py` per FR-023, FR-027, R22 item 9 (partial)
- [X] T085 Remover `OLLAMA_TEMPERATURE` e `OLLAMA_SEED_BASE` (`config.ENV_TEMPERATURE`, `ENV_SEED_BASE`, `__main__.temperature()`, `seed_base()`, os parâmetros de `current_run_config`) e os testes de T075 que dependem delas per R21 esclarecimento 2, R22 item 11 (unrequested)
- [X] T086 [P] Remover e contar (`markdown_fences_removed`) em `parse_prediction` a cerca Markdown que envolve um `<input>` ou `<output>` inteiro (primeira linha exatamente ```` ``` ````, ```` ```text ````, ```` ```txt ```` ou ```` ```plaintext ````, última ```` ``` ````); somar no relatório; testes em `test_parser_prediction.py` per R22 item 7 (partial)
- [X] T087 [P] Ajustar a camada `slm_suites` de `src/cli/consistency.py` (até 15 tentativas, execução só até a 12ª) e a regex de `schemas/manifest.py` (tentativas 1 a 15), com `docs/verificacao-consistencia.md` e `src/cli/README.md`; testes em `tests/cli/test_consistency.py` per R22 item 10 (partial)
- [X] T088 Testar a retomada no meio de cada fase (interrupção nas tentativas 3, 9 e 14 dá a mesma árvore que a execução sem interrupção) em `test_resume.py` per R21 (testes pedidos), SC-004 (partial)
- [X] T089 📌 PROPAGAR — Atualizar `src/ai_clients/README.md` (as 5 fases, a tabela de seeds e temperaturas, os status, a recusa de execução antiga e o `mv data/suites/slm` antes de uma execução nova), o `README.md` da raiz ("Referência de comandos", "Estado atual") e `.env.example` (sem as duas variáveis); procurar por grep "20", "23", "low_confidence", "OLLAMA_TEMPERATURE" e "42 +" nos dois READMEs e corrigir a prosa; marcar R22 como implementado na metodologia (seção 3 + seção 8) e em `research.md`; `docker compose run --rm app python scripts/check_docs_sync.py` sai `0` per Constitution XI (partial)

## Phase 12: Convergence

Execução concorrente para duas GPUs (spec FR-026a, sessão 2026-10-07; research R23 e R24; data-model
§5; contratos). Valem as regras do topo (teste antes, 📌 PROPAGAR); tudo conferido com
`docker compose run --rm sandbox pytest tests/ai_clients tests/cli`.

- [X] T090 📌 PROPAGAR — Registrar o piloto 6 (números do relatório, configuração congelada, continuar a mesma execução até 600 com `--resume`, duas GPUs) em `research.md` R23 e na metodologia (seção 3 + seção 8) per R23 (missing)
- [X] T091 Travas em `src/ai_clients/store.py`: `shared_run` (`LOCK_SH`), `exclusive_run` (inalterada), `single_execute` (`.execute.lock`) e `claim` (`.locks/<id>__<cenário>.lock`, devolve `False` sem esperar), com `config.EXECUTE_LOCK_FILE` e `config.COMBINATION_LOCKS_DIR`; testes em `tests/ai_clients/test_store.py` per FR-026a, R24 itens 1–3 (missing)
- [X] T092 `generation.generate` e `execution.execute` pegam a trava de cada combinação antes de tratá-la, releem o estado com ela, pulam e contam (`skipped`) a combinação em uso; o corpo das tentativas de uma combinação vira `generation._attempts` per FR-026a, R24 item 2 (missing)
- [X] T093 `__main__`: `generate --resume` e `execute` com a trava compartilhada (`execute` também com `single_execute`), o primeiro `generate`, `close` e `package` com a exclusiva; `; N skipped (in use by another command)` no resumo quando N > 0 per FR-026a, contracts/cli.md (missing)
- [X] T094 Testes em `tests/ai_clients/test_concurrency.py` (novo): dois `generate` em metades disjuntas ao mesmo tempo; metades sobrepostas (a combinação em uso pulada e contada, nenhuma tentativa repetida, relatório sem dano); `execute` com `generate` ativo; `execute` pulando a combinação em uso; `package` e `close` recusados com `generate` rodando; segundo `execute` recusado; `generate`/`execute` recusados com a exclusiva; travas fora do pacote. `test_resume.py` e `test_packaging.py` ignoram todo arquivo com ponto, como o pacote per R24 item 5 (missing)
- [X] T095 📌 PROPAGAR — `src/ai_clients/README.md` (tabela de comandos, "Se algo der errado", o laço em bash das duas GPUs no passo 4), `README.md` da raiz ("Estado atual", "Referência de comandos"), metodologia (seção 3 + seção 8), R24 e S15 marcados como implementados; `check_docs_sync.py` sai `0` per Constitution XI (missing)

## Phase 13: Convergence

Resposta do Ollama em *streaming* (spec FR-002a e FR-018a, sessão 2026-10-07; research R25;
contratos). Valem as regras do topo (teste antes, 📌 PROPAGAR); tudo conferido com
`docker compose run --rm sandbox pytest tests/ai_clients tests/cli`.

- [X] T096 Testes em `tests/ai_clients/test_ollama.py`: o servidor local de teste passa a responder em *streaming* (`stream_of`); *stream* completo em vários pedaços = o `Completion` sem *streaming*; métricas só do último pedaço; *timeout* como silêncio entre pedaços; *stream* sem `done` (0, 1 e 3 pedaços), cortado no meio de uma linha e menor que o `Content-Length` → `OllamaUnavailable`; `token repeat limit reached` no *stream* → `ModelRepetition`; outro erro e linha que não é JSON → `OllamaUnavailable` per FR-002a, R25 item 7 (missing)
- [X] T097 `src/ai_clients/ollama.py`: `"stream": true` em `request_body`; `OllamaClient._stream_chat` junta os pedaços e devolve o último; `_translated` concentra a tradução de erros (inclusive `http.client.HTTPException`) para abrir e para ler; `model_info` sem mudança per FR-002a, FR-018a, R25 itens 1–5 (missing)
- [X] T098 Conferir que o `run.json` não muda (`test_resume_config.py`: nenhum campo de *streaming*) e comparar o `run.json` da execução em andamento com a configuração atual (nenhuma diferença) per FR-002a, R25 item 6 (missing)
- [X] T099 📌 PROPAGAR — `src/ai_clients/README.md` (o que `OLLAMA_HTTP_TIMEOUT_S` mede, o 524 e a resposta interrompida em "Se algo der errado"), `.env.example`, metodologia (seção 3 + seção 8), R25 e S16 implementados; `check_docs_sync.py` sai `0` per Constitution XI (missing)

## Phase 14: Convergence

Divisão automática do trabalho entre as GPUs (spec FR-026a, sessão 2026-10-07; research R26).
Valem as regras do topo (teste antes, 📌 PROPAGAR); tudo conferido com
`docker compose run --rm sandbox pytest tests/ai_clients tests/cli`.

- [X] T100 Teste em `tests/ai_clients/test_concurrency.py`: dois `generate` com todos os problemas, cada um parado numa combinação diferente, pulam a do outro e dividem a fila; cada primeira tentativa feita uma vez só per FR-026a, R26 item 4 (missing)
- [X] T101 Laço do `src/ai_clients/README.md` sem as metades (`half0.args`/`half1.args`): os dois `generate --resume` sem `--problem`; texto, tabela de comandos e "Se algo der errado" (o `skipped` é o esperado) per R26 itens 1–2 (missing)
- [X] T102 📌 PROPAGAR — `README.md` da raiz ("Referência de comandos"), `CLAUDE.md`, contrato `cli.md`, quickstart Nível 7, metodologia (seção 3 + seção 8), R26 e S17 implementados; `check_docs_sync.py` sai `0` per Constitution XI (missing)

## Phase 15: Convergence

Troca do template de predição numa execução em andamento (spec FR-022c e FR-022e, sessão
2026-10-07; research R27; data-model §3.2, §3.7 e §3.8; contratos). Valem as regras do topo (teste
antes, 📌 PROPAGAR); tudo conferido com
`docker compose run --rm sandbox pytest tests/ai_clients tests/cli`.

- [X] T103 📌 PROPAGAR — Registrar o achado (1 combinação na predição, a `939_C` caixa-preta, com entrada abreviada aceita; o hash no `run.json`) e as decisões em `research.md` R27, na spec e na metodologia (seção 3 + seção 8) per R27 (missing)
- [X] T104 Testes do parser em `tests/ai_clients/test_parser_prediction.py`: teste com entrada ou saída abreviada descartado e contado (`abbreviated_tests`); só abreviados → `only_abbreviated_tests`; vazios e abreviados → `only_empty_or_abbreviated_tests`; grade com `...` mantida; depois `src/ai_clients/parser.py` e `PredictionParse.abbreviated_tests` per FR-022c, R27 item 7 (missing)
- [X] T105 `GenerationRecord.template_sha256` (opcional) gravado pelo `generate`; `store.read_run` aplica as trocas (`template_changes/`) e confere a cadeia; `store._load` recusa tentativa com hash diferente do template corrente, ou sem hash quando o template já foi trocado; testes em `tests/ai_clients/test_template_change.py` per FR-022e, R27 itens 3 e 5 (missing)
- [X] T106 `src/ai_clients/template_change.py` e o comando `change-template` (`--template`, `--reason`, `--dry-run`; trava exclusiva; recusa com dano, com o mesmo template e com outro comando; termina uma troca interrompida); a recusa do `--resume` por hash de template diz como trocar; testes per FR-022e, R27 itens 2 e 4 (missing)
- [X] T107 Pacote (recusa troca pela metade; leva `superseded/` e `template_changes/`), relatório (`template_changes`, `abbreviated_tests`) e `cli check` (pasta `superseded/` conferida à parte) com testes per FR-022e, R27 item 6 (missing)
- [X] T108 STEP 2 novo em `src/prompt_templates/slm_predict_prompt.txt` (texto da Milena), por último, para a rodada seguinte do laço recusar com código 2 até a troca per R27 item 1 (missing)
- [X] T109 📌 PROPAGAR — `src/ai_clients/README.md` (o comando na tabela, o passo da troca, "Se algo der errado"), `README.md` da raiz ("Referência de comandos"), `CLAUDE.md`, contratos (`cli.md`, `file-formats.md`, `ai-clients-api.md`), data-model, plan S18, R27 implementado; `check_docs_sync.py` sai `0` per Constitution XI (missing)
- [X] T110 Correção de R24 (2026-10-08): arquivo de trava criado pelo `execute` (root, `sandbox`) entregue ao usuário do host (`store._open_lock`), senão o `generate` (`app`) para com `PermissionError`; teste em `tests/ai_clients/test_store.py`; R24 e metodologia (seção 8) per FR-026a (missing)

## Phase 16: Fechamento da documentação da execução completa (2026-10-11)

Registro da execução completa (research R28) e alinhamento dos documentos ao modelo e à política
finais, antes do pacote (T057). Nenhum código de comportamento muda.

- [X] T111 📌 PROPAGAR — Artefatos de `specs/003-slm-test-generation/`: spec (14B como vigente, FR-010, FR-022c, FR-026a, FR-027, SC-002, User Stories 3 e 4 sem "descarte", sessão de 2026-10-11), plan (S19, data, árvore de código), research (R4 marcado como substituído, R27 com o que aconteceu, R28 novo), tasks (T045, T055, T075–T078), data-model, contratos e quickstart (14B, 15 tentativas)
- [X] T112 📌 PROPAGAR — `docs/metodologia-referencia.md`: resultado da execução completa (seção 3 + seção 8), etiqueta de hardware, `close` não usado, troca de template e relatórios dos pilotos 2 e 3
- [X] T113 📌 PROPAGAR — `src/ai_clients/README.md`, `README.md` da raiz, `CLAUDE.md` e `.env.example` com o 14B e o estado atual; "Comandos verificados" (`close` não necessário)
- [X] T114 Corrigir o `reason` de `template_changes/001.json` (gravado como `"..."`) antes do `package`: só esse campo, conferido valor antigo e ausência do manifesto, validado pelo schema `TemplateChange`, gravação atômica; `report` refeito (R27)
- [X] T115 `--help` de `python -m ai_clients` (`src/ai_clients/__main__.py`) cita o Qwen2.5-Coder-14B
