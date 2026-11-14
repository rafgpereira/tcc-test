# Tasks: Geração de Suítes de Teste pelos LLMs Comerciais

**Input**: Design documents from `/specs/004-llm-test-generation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md);
Constitution v1.7.1 (`.specify/memory/constitution.md`)

**Tests**: INCLUÍDOS. A Constitution (Princípio VI) exige suíte própria, e SC-002, SC-004,
SC-004a, SC-004b, SC-005, SC-006 e SC-007 são verificados por teste. Em cada história, os testes
vêm antes da implementação: escreva-os e confirme que **falham** antes de implementar. Nenhum teste
chama uma API real (`FakeProvider`).

**Organization**: tarefas agrupadas por história de usuário (US1 a US4, na ordem de prioridade da
spec), seguidas do piloto, da execução completa e do fechamento.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec (US1 a US4); só nas fases de história
- Caminhos relativos à raiz do repositório
- **Onde rodar**: todo `pytest` no serviço `sandbox` (`docker compose run --rm sandbox pytest
  ...`); `generate`, `report`, `package`, `verify`, `close`, `change-template`, lint e
  `check_docs_sync.py` no serviço `app` (`docker compose run --rm app ...`), que tem rede

## Regras que valem para TODAS as tarefas (Constitution, Princípios III, VIII, IX, X, XI)

- **📌 PROPAGAR**: a tarefa marcada com 📌 produz dado medido ou decisão nova. Ela **só está
  concluída** depois de a informação ser escrita, **na própria tarefa**, em
  `docs/metodologia-referencia.md` (seção 3, seção 6 item 32 e uma linha datada na seção 8) **e**
  nos artefatos da feature que ela afeta (`spec.md`, `plan.md`, `research.md`), com data e fonte.
- **Documentação como critério de aceite**:
  - **Formato do README:** `src/ai_clients/README.md` segue
    [`docs/template-modulo.md`](../../docs/template-modulo.md): seis campos, dois cenários, uma
    tabela única com todos os comandos e variações, e nada de spec-kit, `FR-`, `T0xx` ou
    `specs/...`.
  - **Checagem:** cada tarefa que toca o README só termina quando `docker compose run --rm app
    python scripts/check_docs_sync.py --module src/ai_clients --cli "python -m ai_clients"
    --cli-owner src/ai_clients` sai `0`.
  - **Carimbo de comando:** todo comando novo nasce `pendente` na tabela "Comandos verificados" e
    só é carimbado na tarefa que o executa de verdade, com a data e a revisão (`git rev-parse
    --short=7 HEAD`, mais `+dirty` se houver alteração não commitada). Depois de carimbar, procurar
    o nome do comando por `grep` no README do módulo e no da raiz e corrigir a prosa que o descreva
    como não executado.
- **Restrições citadas literalmente** de [data-model.md](./data-model.md) e
  [contracts/](./contracts/) fazem parte do aceite; não as reinterprete.
- **Sem estado** (Princípio III): os clientes não guardam prompt nem resposta entre chamadas. O
  corpo de cada pedido é **exatamente** o de [contracts/providers.md](./contracts/providers.md) §2
  e §3: nunca `instructions`, `previous_response_id`, `conversation`, `systemInstruction`,
  `cachedContent`, `safetySettings`, `temperature`, `top_p`/`topP`, `top_k`/`topK` nem `seed`.
- **Custo** (Princípio VIII): nenhuma chamada paga sai sem `--confirm-spend`. O dry-run não chama
  nenhuma API, nem endpoint de contagem.
- **Sem dependência nova**: `pyproject.toml` e `uv.lock` não mudam (HTTP por `urllib.request`,
  sem SDK; research R2).
- **O SLM não muda de comportamento** (FR-028): toda mudança em `src/ai_clients/*.py` fora de
  `llm/` é só de nome público ou de parâmetro, e a suíte inteira do SLM continua passando com o
  mesmo número de testes medido em T006.
- **Segredos** (FR-005): nenhuma chave em arquivo gravado, em log, em mensagem de erro nem em
  `raw_body` (os cabeçalhos não são gravados).
- **O agente nunca roda `git add`/`commit`/`push`** (Princípio X).

## Path Conventions

- **Código novo:** subpacote `src/ai_clients/llm/` (plan.md, Project Structure), testes em
  `tests/ai_clients/llm/` (sem `__init__.py`; `pytest` usa `--import-mode=importlib`) e o
  texto-base em `src/prompt_templates/llm_prompt.txt`.
- **Mudanças pequenas em arquivos do SLM** (research R0): `src/ai_clients/__main__.py`,
  `parser.py`, `store.py`, `packaging.py` e o novo `schemas/suite_view.py`.
- **Camadas novas do `cli check`:** em `src/cli/consistency.py`.

---

## Phase 1: Setup

**Purpose**: esqueleto, texto-base, configuração e documentação inicial.

- [X] T001 Create `src/ai_clients/llm/__init__.py` (vazio), a pasta `tests/ai_clients/llm/` e `tests/ai_clients/llm/fixtures/` (corpos HTTP de exemplo, T013)
- [X] T002 [P] 📌 PROPAGAR — Create `src/prompt_templates/llm_prompt.txt` com o texto **exato** do rascunho de [research.md](./research.md) R5 (os três marcadores `(scenario-dependent content)`, `(dataset example input)` e `(dataset example output)`, cada um exatamente uma vez). **Gate**: um dos autores revisa e aprova o texto antes de T020; registrar a aprovação, ou o texto alterado, em R5 e na metodologia (seção 3 + seção 8). O hash vai para o `run.json` (FR-009)
- [X] T003 Create `src/ai_clients/llm/config.py` (docstring citando `docs/metodologia-referencia.md`, seção 3), com:
  - **Modelos:** `MODELS = ("gpt", "gemini")`; `MODEL_ID = {"gpt": "gpt-5.4-mini-2026-03-17", "gemini": "gemini-3.8-flash"}`.
  - **Endpoints:** `ENDPOINT = {"gpt": "https://api.openai.com/v1/responses", "gemini": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"}`.
  - **Pedido:** `REASONING_LEVEL = "medium"`; `MAX_OUTPUT_TOKENS = 32768` (provisório, research R12); `MAX_ATTEMPTS = 3`.
  - **Concorrência e espera:** `DEFAULT_MAX_CONCURRENCY = 4`; `DEFAULT_MAX_INFRA_RETRIES = 30`; `DEFAULT_HTTP_TIMEOUT_S = 900`; `BACKOFF_START_S = 5`, `BACKOFF_MAX_S = 60`, reaproveitados de `ai_clients.config`.
  - **Estimativa:** `CHARS_PER_TOKEN = {"gpt": 3.0, "gemini": 3.0}` com o comentário `conservative, before the pilot` (R9).
  - **Preços:** `PRICE_TABLE` com as três linhas de R9 (US$ por milhão de *tokens*, `valid_from`, `source`, `accessed_on = 2026-10-15`).
  - **Variáveis de ambiente:** `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENAI_MAX_CONCURRENCY`, `GEMINI_MAX_CONCURRENCY`, `OPENAI_MAX_INFRA_RETRIES`, `GEMINI_MAX_INFRA_RETRIES`, `LLM_HTTP_TIMEOUT_S`.
  - **Caminhos por modelo:** `suites_dir(m) = data/suites/<m>`, `report_path(m) = manifests/<m>_generation_report.json`, `manifest_path(m) = manifests/<m>_suites.manifest.json`, `zip_path(m) = data/<m>_suites.zip`, `zip_root(m) = "suites/<m>"`, `BARRED_DIR = "barred"`, `LLM_TEMPLATE_PATH`.
  - **Nomes de arquivo:** `attempt_file_name(n) = f"attempt_{n}.json"` (1 ≤ n ≤ 3, senão `ValueError`).
- [X] T004 [P] Add to `.env.example`, no estilo dos comentários existentes e **sem valor**: `OPENAI_API_KEY=` e `GEMINI_API_KEY=` (contas com faturamento ativo; a camada gratuita do Gemini pode usar o conteúdo, research R9) e as opcionais comentadas `OPENAI_MAX_CONCURRENCY`/`GEMINI_MAX_CONCURRENCY` (padrão 4), `OPENAI_MAX_INFRA_RETRIES`/`GEMINI_MAX_INFRA_RETRIES` (padrão 30) e `LLM_HTTP_TIMEOUT_S` (padrão 900), dizendo que nenhuma delas muda uma resposta
- [X] T005 [P] Update `src/ai_clients/README.md` para os 3 modelos: propósito em uma frase cobrindo SLM e LLMs; dois cenários (do zero / descompactar `data/slm_suites.zip`, `data/gpt_suites.zip`, `data/gemini_suites.zip`); a tabela única de comandos ganha as variações `--model gpt|gemini`, `--confirm-spend`, os códigos 5 e 6 e o que a interrupção e a retomada fazem; as linhas novas de "Comandos verificados" ficam `pendente`; nada de spec-kit, `FR-`, tarefas ou `specs/...`. **Enquanto a CLI não tiver as opções** (até T021 e T034), as variações novas aparecem como **planejadas**, sem a forma `python -m ai_clients ... --model`, como o 003 fez na sua T005 (regra 9 do template e checagem C2, que roda o `--help`); a forma completa entra na tarefa que implementa cada opção


---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: base do SLM sem mudar o comportamento, schemas, leitor comum, duplos de teste, base
do `store` e `--model` na CLI.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

### Tests for Foundational ⚠️ (escrever primeiro; devem FALHAR)

- [X] T006 Rodar `docker compose run --rm sandbox pytest tests/ai_clients tests/cli` **antes de qualquer mudança** e anotar, no checkpoint desta fase, o número de testes que passam (a referência de FR-028 para o resto da feature)
- [X] T007 [P] Write tests in `tests/ai_clients/test_parser_public.py`: `ai_clients.parser.strip_data_fence` e `ai_clients.parser.is_abbreviated` dão, para a tabela de casos de `test_parser_prediction.py` (cercas ```` ``` ````/```` ```text ````/```` ```txt ````/```` ```plaintext ````; `...`, `…`, "repeated N times"), exatamente o resultado que o `parse_prediction` já dá hoje
- [X] T008 [P] Write tests in `tests/ai_clients/test_store_lock_message.py`: `store.exclusive_run(root)` sobre `data/suites/slm` continua com a mensagem `another python -m ai_clients command is already running over data/suites/slm/`, e sobre `data/suites/gpt` ela cita `data/suites/gpt/`
- [X] T009 [P] Write tests in `tests/ai_clients/test_packaging_params.py`: o núcleo de `packaging` chamado com os caminhos do SLM dá os mesmos bytes de zip e o mesmo manifesto de antes, para uma árvore sintética; chamado com `zip_root="suites/gpt"`, gera entradas sob `suites/gpt/`
- [X] T010 [P] Write tests in `tests/ai_clients/llm/test_schemas.py` (data-model §3). Todos os schemas têm `extra` proibido. Para cada schema:
  - **`LlmRunConfig`:** só `schema_version` `1`; recusa `request_parameters` com qualquer um de "`temperature`, `top_p`, `top_k`, `seed`, `instructions`, `systemInstruction`, `safetySettings` nem `previous_response_id`"; `max_attempts` `3`.
  - **`LlmAttempt`:** `attempt` "de 1 a 3"; `usage` com inteiros "maiores ou iguais a 0"; `parse` é `LlmParsed` (com `tests` de "pelo menos 1 item, cada `input` e `output` terminando em exatamente um `\n`" e `edge_cases_analysis` "texto não vazio") ou `LlmFormatFailure` (`failure` ∈ `empty_response`, `not_json`, `schema_violation`, `truncated`, `refusal`, `safety_block`, `no_usable_test`); recusa `usage.reasoning_tokens == 0` (a resposta deveria ser `BarredResponse`).
  - **`BarredResponse`:** tem `reason: "no_reasoning_tokens"` e não tem `attempt` nem `parse`.
  - **`LlmSuite`:** `schema_version` `2`; `accepted_phase` "sempre `null`"; `discarded_inputs` "sempre `[]`"; `attempts` "de 1 a 3", "numerada de 1 sem buraco"; em `accepted_predicted`, só a última tentativa tem `failure` nulo e `tests` não é vazio; em `discarded_manual`, "exatamente 3 tentativas, todas com falha", `tests` vazio, `manual_close` presente, `model_digest` e `accepted_attempt` nulos; `suite_size == len(tests)`.
  - **`LlmAnswer`:** exatamente `edge_cases_analysis` (texto) e `tests` (lista de `{input, output}`, texto).
  - **`PriceRow`:** os campos de §3.8.
  - **Modelos de troca de template:** o `TemplateChange` e o `GenerationRecord` do SLM continuam recusando `template: "llm"`, e o `LlmTemplateChange` (§3.9) recusa `solution` e `prediction`.
- [X] T011 [P] Write tests in `tests/ai_clients/test_suite_view.py` (SC-007): `read_suite_view` lê, sem saber o modelo, (a) um `suite.json` `accepted`, um `accepted_fallback`, um `accepted_predicted` e um `discarded_manual` do SLM (construídos como nos testes do SLM) e (b) um `accepted_predicted` e um `discarded_manual` de LLM. Recusa `suite_size != len(tests)` e `tests` vazio fora de `discarded_manual`. O `SlmSuite` continua recusando uma suíte de LLM, e o `LlmSuite` recusa uma do SLM
- [X] T012 [P] Write tests in `tests/ai_clients/test_cli_model.py`:
  - todo subcomando aceita `--model {slm,gpt,gemini}`; sem a opção, o comportamento é o do SLM (comparar a saída de `generate --dry-run` e `report` sobre uma árvore sintética antes e depois);
  - `execute --model gpt` e `execute --model gemini` saem com código 2 e `the commercial models run nothing: there is no execute step`;
  - existem as constantes `EXIT_SPEND_CAP = 5` e `EXIT_NO_REASONING = 6`;
  - a precedência de `finish` é "`130` > `3` > `6` > `1` > `5` > `4` > `0`".
- [X] T013 [P] Create `tests/ai_clients/llm/fakes.py`, `tests/ai_clients/llm/conftest.py` e `tests/ai_clients/llm/fixtures/`:
  - **`FakeProvider`:** tabela `(modelo, problema, cenário, número da chamada) → ProviderAnswer | ProviderUnavailable | ProviderFatal`; grava em `self.requests` o corpo exato de cada pedido, e falha o teste, com a chave, numa chamada não prevista.
  - **`FakeClock`:** registra as esperas.
  - **Construtores:** `openai_body(...)` e `gemini_body(...)` geram corpos HTTP realistas (completo, `incomplete`/`max_output_tokens`, `incomplete`/`content_filter`, `refusal`, `MAX_TOKENS`, `SAFETY` com categorias, `promptFeedback.blockReason`, texto vazio, texto não JSON, JSON fora do schema, raciocínio 0 e raciocínio ausente).
  - **`conftest.py`:** reaproveita `build_dataset` de `tests/ai_clients/conftest.py`.
- [X] T014 [P] Write tests in `tests/ai_clients/llm/test_store_base.py`: `ensure_suites_dir("gpt")` cria `data/suites/gpt/problems/` nível a nível; `write_attempt`, `write_barred` e `write_run` recusam sobrescrever e são atômicos (nenhum `*.tmp` sobra depois de uma exceção simulada); `read_run` recusa `schema_version` diferente; `LlmRunConfig.differences` lista campo a campo, menos "`created_at`, `price_table`"

### Implementation for Foundational

- [X] T015 [P] Expose in `src/ai_clients/parser.py` os nomes públicos `strip_data_fence(text) -> tuple[str, bool]` e `is_abbreviated(text)`, sem mudar o que `parse_prediction` faz (makes T007 pass)
- [X] T016 [P] Make the lock message of `src/ai_clients/store.py` cite a pasta recebida (o texto do SLM fica idêntico) (makes T008 pass)
- [X] T017 [P] Parametrize the core of `src/ai_clients/packaging.py` (`_tree`, `build_zip`, `build_manifest`, `verify`) por `zip_path`, `zip_root` e o conjunto de caminhos aceitos; o SLM chama com os valores de hoje (makes T009 pass)
- [X] T018 [P] Implement `src/ai_clients/llm/schemas.py` exatamente como [data-model.md](./data-model.md) §2–§3 (herdando `dataset.schemas.common.Schema`; `tests: list[dataset.schemas.testes.TestCase]`; `Scenario` e `SuiteStatus` importados de `ai_clients.schemas.common`; `ManualClose` reaproveitado sem mudança; `LlmTemplateChange` novo, data-model §3.9, com `template: Literal["llm"]`; o `AttemptKind` do SLM fica intocado) (makes T010 pass)
- [X] T019 [P] Implement `src/ai_clients/schemas/suite_view.py`: `SuiteView` (`extra="ignore"`, campos e validações de data-model §3.5) e `read_suite_view(path) -> SuiteView` (makes T011 pass)
- [X] T020 Implement the foundation of `src/ai_clients/llm/store.py`: `ensure_suites_dir`, `combination_dir`, `write_attempt`, `write_barred`, `write_run`, `read_run`, `read_attempt` (via `dataset.persistence.store.atomic_write_json` e `make_private_dir`; `FileExistsError` se o arquivo já existe), e as travas reaproveitadas de `ai_clients.store` (`exclusive_run`, `shared_run`, `claim`) sobre `data/suites/<m>` (makes T014 pass)
- [X] T021 Add `--model {slm,gpt,gemini}` (padrão `slm`) a `generate`, `close`, `change-template`, `report`, `package` e `verify` em `src/ai_clients/__main__.py`; `execute` com `--model` diferente de `slm` → código 2; `EXIT_SPEND_CAP = 5`, `EXIT_NO_REASONING = 6` e a precedência nova em `finish`; o despacho para `ai_clients.llm` fica para as histórias (makes T012 pass)

**Checkpoint**: `docker compose run --rm sandbox pytest tests/ai_clients tests/cli` passa, com o
número de testes do SLM igual ao de T006 mais os novos.

---

## Phase 3: User Story 1 - Gerar a suíte de uma combinação com um modelo comercial (Priority: P1) 🎯 MVP

**Goal**: para um problema × cenário × modelo, uma chamada sem estado por tentativa, a resposta
crua gravada antes de interpretada e o `suite.json` (`accepted_predicted`). Inclui até 3
tentativas só por falha de formato, a espera por falha de infraestrutura, a barreira de raciocínio
e o fechamento manual.

**Independent Test**: com o `FakeProvider`, `generate --model gpt --problem 1_A --scenario
black_box --confirm-spend 1` grava `attempt_1.json` (com resposta crua, modelo devolvido, *tokens*,
custo e tempo) e um `suite.json` que `read_suite_view` aceita.

### Tests for User Story 1 ⚠️

- [X] T022 [P] [US1] Write tests in `tests/ai_clients/llm/test_providers.py`:
  - **`request_body`:** igual, chave a chave, aos corpos de [contracts/providers.md](./contracts/providers.md) §2 e §3, nos dois modelos (inclui `"store": false`, `"reasoning": {"effort": "medium"}`, `"thinkingConfig": {"thinkingLevel": "medium"}`, `"strict": true`, `responseFormat.text` com `mimeType: "APPLICATION_JSON"` (desde 2026-10-16, R3), o prompt inteiro numa única mensagem `user`) e sem nenhum campo proibido (SC-002, A11, A13).
  - **Leitura das respostas:** `model_returned`, `response_id`, `finish`, `usage` e `text` lidos dos corpos de T013; no Gemini, a saída cobrada é `candidatesTokenCount + thoughtsTokenCount` e as partes `thought: true` ficam fora de `text`.
  - **Classificação dos erros** (§2 e §3): 429 com `insufficient_quota` → `ProviderFatal`; outro 429, 5xx, 408 e *timeout* → `ProviderUnavailable`, com `Retry-After` e `retryDelay` lidos.
  - **Segredos:** a chave não aparece em nenhuma exceção nem em `raw_body` (FR-005).
- [X] T023 [P] [US1] Write tests in `tests/ai_clients/llm/test_interpret.py` (research R6), cobrindo:
  - **A ordem das conferências:** raciocínio → término → texto → testes.
  - **As 7 falhas, uma por corpo de T013:** `truncated` (OpenAI `max_output_tokens`; Gemini `MAX_TOKENS`), `refusal`, `safety_block` (OpenAI `content_filter`; Gemini `blockReason` e `finishReason` de segurança, com as categorias), `empty_response`, `not_json`, `schema_violation` e `no_usable_test`.
  - **As regras de FR-013:** cerca que envolve a entrada ou a saída inteira retirada e contada; exatamente um `\n` final; teste vazio ou abreviado descartado e contado; entrada repetida fica a primeira (contada); saída diferente para a mesma entrada conta como `conflicting_outputs`; cópia do exemplo mantida e contada em `example_copies`.
  - **Determinismo:** a mesma resposta dá o mesmo resultado (FR-013).
- [X] T024 [P] [US1] Write tests in `tests/ai_clients/llm/test_cost.py` (parte de US1): custo de uma chamada = "`(entrada − cache) × preço de entrada + cache × preço de cache + saída × preço de saída`", com a linha válida na data da chamada; uma chamada do Gemini em 2026-12-31 e outra em 2027-01-01 usam linhas diferentes
- [X] T025 [P] [US1] Write tests in `tests/ai_clients/llm/test_states.py`: cada estado de [data-model.md](./data-model.md) §4 (`pending(n)`, `finalizable`, `done`, `awaiting_manual`, `closable → done`) e cada causa de `damaged` listada lá, uma por teste; os temporários `.<nome>.<sufixo>.tmp` são ignorados; `barred/` não muda o estado
- [X] T026 [P] [US1] Write tests in `tests/ai_clients/llm/test_generation.py`, com N = 1 e o `FakeProvider`:
  - **Sucesso:** uma tentativa interpretada grava `attempt_1.json` e depois `suite.json` (`accepted_predicted`).
  - **Resposta crua:** o corpo HTTP inteiro vai no registro da tentativa, e reinterpretá-lo dá o mesmo resultado sem chamar a API (FR-010). *(Ajustado na implementação, em 2026-10-15: como no SLM, a interpretação é pura e nunca levanta exceção, testado com entradas hostis em `test_interpret.py`; por isso não há um registro separado antes da interpretação.)*
  - **Falhas de formato:** 3 falhas → `awaiting_manual`, linha `manual: ... close it with: docker compose run --rm app python -m ai_clients close --model <m> --problem <id> --scenario <cenário> --reason "<motivo>"` e código 4; a tentativa 2 só existe se a 1 falhou.
  - **Prompts:** entre os 3 cenários de um problema só muda `<context_data>`, e o prompt é o mesmo nos 2 modelos (US1, cenário 4).
  - **Infraestrutura** (FR-018, SC-006): `ProviderUnavailable` repete a mesma chamada sem gravar nada, esperando de 5 a 60 s ou o `Retry-After`/`retryDelay`, quando maior; ao atingir o teto, código 3 com `nothing was recorded`; `ProviderFatal` → código 3 sem repetir.
  - **Barreira** (FR-018a, SC-004b): `reasoning_tokens` 0 ou ausente → `barred/<id>/<cenário>/1.json`, nenhuma chamada nova, código 6, a combinação continua `pending(n)`, e o custo da barrada entra no gasto.
- [X] T027 [P] [US1] Write tests in `tests/ai_clients/llm/test_closing.py`: `close --model gemini` só vale para `awaiting_manual` (outro estado → código 2, `<id> <cenário> is <estado>, not awaiting manual handling; nothing was recorded`); grava `manual_close.json` e depois `suite.json` (`discarded_manual`); `--reason` vazio → código 2; `--dry-run` não grava nada

### Implementation for User Story 1

- [X] T028 [P] [US1] Implement `src/ai_clients/llm/providers.py` (`LLMProvider`, `ProviderAnswer`, `Finish`, `Usage`, `ProviderUnavailable`, `ProviderFatal`, `OpenAIClient`, `GeminiClient`), com `urllib.request`, uma conexão por pedido, sem *streaming* e sem repetir nada (research R2, R3; makes T022 pass)
- [X] T029 [P] [US1] Implement `src/ai_clients/llm/interpret.py`, reaproveitando `ai_clients.parser.strip_data_fence`/`is_abbreviated` e validando com `LlmAnswer` (makes T023 pass)
- [X] T030 [P] [US1] Implement `price_row_for(model, when)` e `call_cost(usage, row)` em `src/ai_clients/llm/cost.py` (makes T024 pass)
- [X] T031 [US1] Implement the states of `src/ai_clients/llm/store.py`: `combination_state`, `expected_suite` (`LlmSuite` como função pura dos arquivos), `finalize`, `awaiting_manual` e o dano detalhado (`missing:`/`changed:`/`inconsistent:`, como no SLM) (makes T025 pass)
- [X] T032 [US1] Implement `src/ai_clients/llm/generation.py` (versão com N = 1):
  - **Por combinação:** monta o prompt com `ai_clients.prompt.build_prompt` sobre `llm_prompt.txt`, chama, grava a tentativa (com custo, `latency_s` sem as esperas e `price_row`), interpreta e grava o `suite.json`, ou passa à tentativa seguinte.
  - **Esperas e paradas:** a espera e o teto de R7, e a barreira de R6.1.
  - **`run.json`:** criado no primeiro `generate` (makes T026 pass).
- [X] T033 [US1] Implement `src/ai_clients/llm/closing.py` e o despacho de `close --model gpt|gemini` em `src/ai_clients/__main__.py` (makes T027 pass)
- [X] T034 [US1] Wire `generate --model gpt|gemini` em `src/ai_clients/__main__.py`, conforme [contracts/cli.md](./contracts/cli.md):
  - **Antes de qualquer trabalho:** verificar o dataset; ler a chave do modelo pedido (ausente → código 2, só para esse modelo) e as variáveis opcionais (valor que não é inteiro positivo → 2).
  - **Opções:** `--problem`, `--scenario`, `--limit` e `--resume` (o `run.json` existente sem `--resume` → 2); `--confirm-spend USD` obrigatório fora do dry-run, e o teto entra em US2.
  - **Saídas:** as linhas por chamada e o resumo do contrato.

**Checkpoint**: US1 testável sozinha: `pytest tests/ai_clients/llm -k "providers or interpret or
states or generation or closing"` passa, e a árvore de um `generate` com o `FakeProvider` é a de
data-model §1.

---

## Phase 4: User Story 2 - Saber o custo antes e nunca pagar sem confirmar (Priority: P1)

**Goal**: dry-run sem nenhuma chamada; recusa sem `--confirm-spend`, mostrando a estimativa; teto
de gasto respeitado (código 5); *tokens*, custo e tempo de cada chamada registrados.

**Independent Test**: `generate --model gpt --dry-run` sobre o dataset sintético não faz nenhum
pedido nem grava nada; sem `--confirm-spend`, recusa com código 2 e zero pedidos; com um teto
menor que o custo de duas chamadas, o `FakeProvider` recebe no máximo as chamadas que já tinham
sido despachadas.

### Tests for User Story 2 ⚠️

- [X] T035 [P] [US2] Write tests in `tests/ai_clients/llm/test_estimate.py` (FR-021, SC-004):
  - **Isolamento:** o dry-run não faz nenhum pedido (o `FakeProvider` sem entradas falharia), não grava nada (nem `run.json`, nem trava) e funciona sem chave.
  - **Saída:** as linhas por cenário e o total do contrato, com combinações, chamadas (`up to 3N`), *tokens* = "caracteres ÷ `CHARS_PER_TOKEN`" (declarado na linha), saída pelo teto (e pela média medida quando houver) e a faixa de custo.
  - **Escopo:** `--problem`, `--scenario` e `--limit` mudam a estimativa (FR-022).
- [X] T036 [P] [US2] Write tests in `tests/ai_clients/llm/test_spend_cap.py`:
  - **Sem confirmação** (SC-004): sem `--confirm-spend`, código 2 com a estimativa e `run again with --confirm-spend`, e zero pedidos; `--confirm-spend` zero, negativo ou que não é número → 2.
  - **Com teto** (SC-004a): com N = 4 e um teto atingido depois da 3ª chamada concluída, nenhuma chamada é despachada depois disso; as já em andamento terminam e são gravadas; a linha `spend cap reached: spent US$ X of US$ Y (US$ Z over the cap ...)` mostra o excesso, e o código é 5.
  - **Retomada:** `--resume --confirm-spend <novo>` continua de onde parou, e o teto não entra na comparação da retomada.
  - **Barradas:** o custo das respostas barradas conta no gasto.
- [X] T037 [P] [US2] Write tests in `tests/ai_clients/llm/test_cost_records.py` (SC-003): toda tentativa e toda barrada têm `usage`, `cost_usd`, `price_row` e `latency_s`, e o gasto da invocação impresso é a soma delas

### Implementation for User Story 2

- [X] T038 [P] [US2] Implement `estimate(...)` em `src/ai_clients/llm/cost.py` (research R9) e o `--dry-run` de `generate --model gpt|gemini` em `src/ai_clients/__main__.py` (makes T035 pass)
- [X] T039 [US2] Implement the spend cap in `src/ai_clients/llm/generation.py`: a soma protegida por `threading.Lock`, a parada do despacho e as mensagens e o código 5 de [contracts/cli.md](./contracts/cli.md); e a recusa com a estimativa em `src/ai_clients/__main__.py` (makes T036 and T037 pass)
- [X] T040 [US2] 📌 PROPAGAR — Rodar `docker compose run --rm app python -m ai_clients generate --model gpt --dry-run` e o mesmo com `--model gemini`, sobre os 200 problemas reais. Registrar em `research.md` R9 e na metodologia (seção 3 + seção 8): o maior prompt por cenário (caracteres), o total de *tokens* de entrada estimado e a faixa de custo de cada modelo, deixando explícito que a razão 3,0 é a conservadora de antes do piloto. Carimbar `generate --model ... --dry-run` no README

**Checkpoint**: US1 e US2 juntas: nenhuma chamada paga é possível sem `--confirm-spend`, e o gasto
nunca segue depois do teto.

---

## Phase 5: User Story 3 - Retomar sem duplicar, sem corromper e sem pagar de novo (Priority: P2)

**Goal**: retomada exata em qualquer ponto; N chamadas simultâneas num processo e dois processos
juntos, sem tratar a mesma combinação duas vezes; recusa de configuração diferente; troca de
texto-base pelo `change-template`.

**Independent Test**: interromper com o `FakeProvider` em cada ponto (antes da chamada, durante,
depois de gravar a tentativa, antes do `suite.json`), retomar e obter a mesma árvore de uma
execução sem interrupção, sem nenhuma chamada repetida de tentativa já gravada.

### Tests for User Story 3 ⚠️

- [X] T041 [P] [US3] Write tests in `tests/ai_clients/llm/test_resume.py` (SC-005):
  - **Interrupção em cada ponto do Independent Test:** nenhum arquivo parcial; nenhuma chamada repetida de tentativa gravada; só a chamada em andamento é refeita.
  - **Configuração diferente** (`model_requested`, `request_parameters` campo a campo, `response_schema`, `template_sha256`, `max_attempts`, `dataset_manifest_sha256`): recusa com código 2, listando `<campo>: recorded <valor>, current <valor>`.
  - **O que pode mudar sem recusa:** `price_table`, o teto de gasto, a concorrência e as esperas.
  - **Escopo:** uma combinação pedida sozinha (`--problem`/`--scenario`) não toca nas outras.
- [X] T042 [P] [US3] Write tests in `tests/ai_clients/llm/test_concurrency.py` (FR-012, FR-024):
  - **Uma combinação por vez:** com N = 4, nenhuma combinação é tratada por duas *threads* (o `FakeProvider` registra a combinação de cada pedido em andamento); as tentativas de uma combinação são sequenciais.
  - **Dois processos:** sobre a mesma pasta, os dois dividem a fila; a combinação em uso é pulada (`skipped (in use by another command)`); `generate` sem `--resume`, `close` e `package` recusam com código 1 enquanto outro roda.
  - **Dois modelos:** rodam ao mesmo tempo sem interferir.
  - **Determinismo:** o resultado com N = 4 é igual ao com N = 1, para as mesmas respostas.
  - **Barreira com chamadas em andamento** (FR-018a): com N = 4, o `FakeProvider` devolve uma resposta com `reasoning_tokens` 0 enquanto outras 3 chamadas estão em andamento → nenhuma chamada nova é despachada depois dela; as 3 terminam e passam pela mesma conferência (gravadas como tentativas se tiverem raciocínio, ou em `barred/` se não tiverem); se o teto de gasto também for atingido nessa invocação, o código de saída é 6 (precedência "`6` > `1` > `5` > `4`").
- [X] T043 [P] [US3] Write tests in `tests/ai_clients/llm/test_template_change.py`: `change-template --model gpt --template llm --reason "..."` grava `template_changes/001.json`, move para `superseded/001/<id>/<cenário>/` as tentativas feitas com o texto antigo (e o `suite.json`) e a combinação volta a `pending`; texto igual ao corrente → código 2; `--template solution` com `--model gpt` → código 2; `--resume` com texto diferente sem `change-template` → código 2, terminando com a sugestão do comando
- [X] T044 [P] [US3] Write tests in `tests/ai_clients/llm/test_damage.py`: cada causa de dano de data-model §4 numa combinação faz o `generate`, o `report` e o `package` pularem só essa combinação, imprimirem `damaged: <id> <cenário>: ...` e saírem com código 1

### Implementation for User Story 3

- [X] T045 [US3] Extend `src/ai_clients/llm/generation.py` to N *threads* (`ThreadPoolExecutor(max_workers=N)`; `claim` por combinação tomado pela *thread*; coordenador que despacha em ordem canônica e para por teto, barreira, teto de repetições, erro fatal ou interrupção; research R8) e a retomada com `--resume` (makes T041, T042 pass)
- [X] T046 [US3] Implement `src/ai_clients/llm/template_change.py` e o despacho de `change-template --model gpt|gemini` em `src/ai_clients/__main__.py`, com as mensagens do SLM (makes T043 pass)
- [X] T047 [US3] Make damage reporting in `src/ai_clients/llm/store.py` and the commands match T044 (makes T044 pass)

**Checkpoint**: interromper e retomar não muda o resultado; N = 4 e dois processos dão a mesma
árvore que N = 1.

---

## Phase 6: User Story 4 - Relatório, pacote e conferência para sustentar o TCC (Priority: P3)

**Goal**: relatório versionável por modelo (FR-025), pacote e manifesto por modelo (FR-026, A7),
`verify` e as camadas `gpt_suites` e `gemini_suites` do `cli check` (FR-027).

**Independent Test**: sobre uma árvore sintética pequena, os totais do relatório batem com os
arquivos; o manifesto confere com o pacote; uma pasta faltando ou sobrando é apontada pelo `cli
check`.

### Tests for User Story 4 ⚠️

- [X] T048 [P] [US4] Write tests in `tests/ai_clients/llm/test_report.py`:
  - **Conteúdo:** todas as chaves de data-model §3.6, por cenário e no total; `cost_usd.total` = soma das tentativas + `barred_cost_usd` (SC-003); `models_returned` com todos os identificadores vistos; `safety_blocks_by_category` só no Gemini.
  - **Determinismo:** a mesma árvore dá os mesmos bytes (nenhuma data no arquivo).
  - **Execução incompleta:** funciona e conta `pending` e `awaiting_manual`.
  - **Dano:** código 1.
- [X] T049 [P] [US4] Write tests in `tests/ai_clients/llm/test_packaging.py`:
  - **Recusa:** `package --model gpt` recusa (código 1) se alguma das 600 combinações **do GPT** não tem `suite.json`, listando-as, e **ignora** as pendências do Gemini (A7).
  - **Zip:** determinístico, com raiz `suites/gpt/`, sem `.lock` nem `.locks/`, com `run.json`, `barred/`, `template_changes/` e `superseded/`.
  - **Manifesto:** aceita exatamente os caminhos de data-model §3.7.
  - **`verify`:** `0`/`1`/`2` como no SLM, e `--extracted` aponta `changed:`/`missing:`/`extra:`.
- [X] T050 [P] [US4] Write tests in `tests/cli/test_consistency.py` (casos novos): camadas `gpt_suites` e `gemini_suites` com as regras de R11:
  - **Sem manifesto:** pasta, problema, cenário ou `suite.json` ausente → `[AVISO]`.
  - **Sempre `[FALHA]`:** buraco nas tentativas, mais de 3 tentativas, arquivo estranho ou pasta sem problema no dataset.
  - **Com manifesto:** tudo o que falta → `[FALHA]`.
  - **Outros:** `--deep` confere o SHA-256 contra o manifesto do modelo; `--only gpt_suites` funciona.
  - **Não regressão:** as camadas antigas continuam com a mesma saída.

### Implementation for User Story 4

- [X] T051 [P] [US4] Implement `src/ai_clients/llm/report.py` (reaproveitando `ai_clients.report.size_stats`) e o despacho de `report --model gpt|gemini` (makes T048 pass)
- [X] T052 [P] [US4] Implement `src/ai_clients/llm/packaging.py` sobre o núcleo parametrizado em T017, o manifesto `LlmSuitesManifest` e o despacho de `package`/`verify --model gpt|gemini` (makes T049 pass)
- [X] T053 [US4] Add the layers `gpt_suites` e `gemini_suites` to `src/cli/consistency.py` (`LAYERS`) (makes T050 pass) e documentá-las em `docs/verificacao-consistencia.md` (o que conferem, a severidade, como rodar só uma)

**Checkpoint**: todas as histórias funcionam juntas com o `FakeProvider`; a suíte inteira passa
(número do SLM igual ao de T006).

---

## Phase 7: Piloto pago, execução completa e fechamento

**Purpose**: medir no mundo real, fixar os valores provisórios e produzir os artefatos finais.
Nada aqui começa sem T002 aprovado.

**Estado em 2026-10-15**: T001 a T054 concluídas (1.765 testes do projeto passando, `ruff` e
`black` limpos, `check_docs_sync.py` em `0`, dry-run real carimbado). Já feito de T058: o README do
módulo, o README da raiz, o `CLAUDE.md`, o `docs/template-modulo.md` e o
`docs/verificacao-consistencia.md` descrevem os 3 modelos, com os comandos pagos ainda `pendente`.
Já feito de T060: o leitor comum leu as 600 suítes reais do SLM (os 1.200 dos LLMs dependem de
T057). T055 a T060 dependem de chamadas pagas e de decisões dos autores.

- [X] T054 Rodar `docker compose run --rm app ruff check .` e `docker compose run --rm app black --check .`; corrigir o que aparecer
- [X] T055 📌 PROPAGAR — **Piloto** ([quickstart.md](./quickstart.md), nível 4; FR-023a). *(Gemini feito e registrado em 2026-10-16, `research.md` R15: 15 de 15 suítes na 1ª tentativa, US$ 0,126; falta o GPT.)* *(Concluída: pilotos de 2026-10-16 registrados em `research.md` R15 e na metodologia, seção 3; a execução completa que se seguiu partiu do zero.)*
  - **Primeiro passo, obrigatório:** `docker compose run --rm app python -m cli check --deep` sai `0`; se não sair, parar.
  - **Execução:** dry-run e depois `generate --model gpt` e `--model gemini`, em paralelo, com `--problem 1000_B --problem 1005_C --problem 1008_B --problem 1_B --problem 61_B` e `--confirm-spend <teto combinado com os autores>`.
  - **Conferir e registrar** (`research.md` A3, R3, R9, R12; metodologia seção 3, seção 6 item 32 e seção 8):
    1. A primeira chamada de cada modelo foi aceita. (Já conferido para o Gemini em 2026-10-16 num pedido de teste: `responseFormat` com `"APPLICATION_JSON"`; R3.)
    2. Houve alguma resposta barrada (código 6)? Se sim, parar e investigar com os autores.
    3. O `model` do GPT foi `gpt-5.4-mini-2026-03-17`? Qual `modelVersion` o Gemini devolveu?
    4. Maior saída total por modelo (resposta + raciocínio) e quantas respostas foram `truncated`.
    5. Razão caracteres/*token* de entrada medida por modelo.
    6. Tempo por chamada (mediana e máximo frente a `LLM_HTTP_TIMEOUT_S = 900`).
    7. Falhas de formato por razão.
    8. Bloqueios de segurança por categoria (A13).
    9. Esperas de infraestrutura e 429.
    10. Custo real × estimativa do dry-run (SC-009).
  - **Fechamento:** `report --model gpt|gemini`, salvos como `manifests/<m>_generation_report.piloto1.json`; carimbar `generate`, `report` e `close` (se usado) no README.
- [X] T056 📌 PROPAGAR — **Ponto de decisão com os autores** (depois de T055): *(Concluída: `MAX_OUTPUT_TOKENS = 32768` e `CHARS_PER_TOKEN` medidos fixados em `src/ai_clients/llm/config.py`; registro em `research.md` e na metodologia.)*
  - **Teto de saída:** fixar `MAX_OUTPUT_TOKENS` (R12).
  - **Razão de tokens:** trocar `CHARS_PER_TOKEN` pelas razões medidas, com data e origem no comentário de `src/ai_clients/llm/config.py` (R9).
  - **Revisões:** revisitar a A13 se houve bloqueio e, se necessário, o texto-base. Um texto novo vai direto para `llm_prompt.txt`, sem `change-template`, porque o piloto é descartado e a execução completa começa do zero (FR-023a).
  - **Concorrência:** ajustar `*_MAX_CONCURRENCY` ao limite de requisições observado.
  - **Pastas do piloto:** mover `data/suites/gpt` e `data/suites/gemini` para `data/suites/<m>-piloto1`.
  - **Registro:** registrar tudo em `spec.md` (FR-023), `research.md`, `plan.md` (S4, S6) e na metodologia. **Não avançar para T057 sem esta tarefa propagada.**
- [X] T057 📌 PROPAGAR — **Execução completa** (quickstart, nível 5). *(Concluída: execução final dos 3 modelos comerciais em 2026-10-20 sobre a revisão 2 do dataset; resultados na seção 3 da `docs/metodologia-referencia.md`.)*
  - **Primeiro passo, obrigatório:** `docker compose run --rm app python -m cli check --deep` sai `0`.
  - **Execução:** para cada modelo, `generate --dry-run` (com a razão medida) e depois `generate --confirm-spend <teto>`, repetido com `--resume` até não sobrar pendência; `close` para cada `awaiting_manual`, com o motivo decidido pelos autores.
  - **Fechamento:** `report`, `package` e `verify --extracted data/suites/<m>`; `python -m cli check --deep` sai `0` com as camadas `gpt_suites` e `gemini_suites` (SC-008).
  - **Registrar** (`research.md`, `spec.md` SC-001 e SC-009, metodologia seção 3 com uma subseção de resultado e seção 8):
    1. As 1.200 combinações em estado final, por status, cenário e modelo.
    2. Tentativas e falhas por razão.
    3. Tamanho das suítes.
    4. *Tokens*, custo real e estimado.
    5. Tempo.
    6. Identificadores de modelo vistos.
    7. Respostas barradas.
    8. Interrupções e retomadas.
  - **Carimbo:** carimbar `package` e `verify` no README.
- [X] T058 📌 PROPAGAR — **Documentação de uso**: *(Concluída: READMEs e `CLAUDE.md` descrevem os 3 modelos; revisados na limpeza final de 2026-11-14.)*
  - **`src/ai_clients/README.md`:** os 3 modelos nos dois cenários e todos os comandos na tabela única, com as variações `--model`, `--confirm-spend`, `--dry-run`, `--resume`, `--problem`, `--scenario`, `--limit`, `--extracted`, os códigos 4, 5 e 6, e o que a interrupção, o teto e a barreira fazem.
  - **`README.md` da raiz:** "Referência de comandos" com cada comando novo; "Estado atual"; a tabela de módulos; a preparação do `.env` com as chaves.
  - **`CLAUDE.md`:** "Comandos do dia a dia" com os LLMs, e `data/gpt_suites.zip`/`data/gemini_suites.zip` na "Estrutura".
  - **Revisão de prosa:** procurar por `grep` "em especificação", "planejad" e "Gemini 3.5" nos dois READMEs e corrigir o que contradiga a tabela.
  - **Metodologia:** marcar a seção 3 como implementada, com uma linha na seção 8.
  - **Checagem:** `docker compose run --rm app python scripts/check_docs_sync.py --module src/ai_clients --cli "python -m ai_clients" --cli-owner src/ai_clients` sai `0`.
- [ ] T059 Constitution v1.7.1 compliance review: refazer a tabela "Constitution Check" de `plan.md` contra o código implementado. Em especial: *(2026-11-14: as conferências automáticas passaram; falta o registro da revisão do código por um dos autores — quem e quando — antes de marcar.)*
  - **III:** `grep -rn "temperature\|top_p\|topP\|seed\|instructions\|systemInstruction\|safetySettings\|previous_response_id" src/ai_clients/llm` mostra só a lista de campos proibidos do validador.
  - **VIII:** nenhum caminho que chega a `LLMProvider.call` sem `--confirm-spend`.
  - **IX:** `pyproject.toml` e `uv.lock` sem mudança.
  - **FR-014 (nada executado):** `grep -rn "sandbox\|subprocess\|os.system\|exec(" src/ai_clients/llm` não encontra nada.

  Desvios vão em "Complexity Tracking". Um dos autores revisa o código gerado com apoio de IA (Princípio X); registrar quem e quando.
- [ ] T060 📌 PROPAGAR — Fechamento: *(2026-11-14: suíte inteira rodada; o `--closing` ainda aponta carimbos de "Comandos verificados" em revisão `+dirty` ou `pendente` em outras features; só fecha ao recarimbar em revisão commitada. Os carimbos dos comandos pagos (`generate`) não devem ser refeitos só para isso.)*
  - `docker compose run --rm sandbox pytest` (suíte inteira) passa.
  - **SC-007 sobre os dados reais:** com `data/suites/slm` descompactado de `data/slm_suites.zip` (`unzip data/slm_suites.zip -d data/`, se ainda não estiver), as 600 `suite.json` do SLM validam no `SlmSuite` **e** são lidas por `read_suite_view`, e as 1.200 dos LLMs (T057) são lidas por `read_suite_view`. Conferir com um comando de uma linha no serviço `app` (`python -c` que percorre as três pastas) e registrar o resultado (contagens e zero recusas) na seção 3 da metodologia e no SC-007 de `spec.md`.
  - **Documentação:** `docker compose run --rm app python scripts/check_docs_sync.py --closing --feature specs/004-llm-test-generation` sai `0` (SC-008).
  - **Entrega:** dizer aos autores os arquivos a commitar (`data/gpt_suites.zip`, `data/gemini_suites.zip`, os manifestos, os relatórios e o código), **sem** rodar nenhum comando de Git

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 → T003; T002, T004 e T005 são `[P]`. **T002 (texto aprovado) bloqueia
  T032 e tudo o que chama `build_prompt` com o texto real.**
- **Foundational (Phase 2)**: depende do Setup; T006 vem antes de qualquer mudança; bloqueia todas
  as histórias.
- **US1 (Phase 3)**: depende da Fase 2.
- **US2 (Phase 4)**: os testes T035 a T037 e o `estimate` podem começar logo depois da Fase 2; o
  teto (T039) depende de T032; o dry-run real T040 depende de T002 e T038.
- **US3 (Phase 5)**: depende de US1 (T032) e de T039 (a parada do despacho é a mesma).
- **US4 (Phase 6)**: testável com árvores sintéticas logo depois de T031; os números reais só em
  T057.
- **Phase 7**: T055 depende de todas as histórias e de T002; T056 depende de T055; T057 depende
  de T056; T058 a T060 vêm por último.

### Within Each User Story

- Testes escritos e vistos falhar antes da implementação.
- `schemas` → `providers`/`interpret`/`cost` → `store` (estados) → `generation` → subcomando.
- Cada história termina com o README do módulo atualizado e `check_docs_sync.py --module` em `0`.

### Parallel Opportunities

- **Fase 2:** T007 a T014 (testes) em arquivos diferentes; T015 a T019 em arquivos diferentes.
- **US1:** T022 a T027 todos `[P]`; T028, T029 e T030 `[P]` entre si.
- **US2:** T035 a T037 `[P]`; o `estimate` (T038) em paralelo com US1.
- **US3:** T041 a T044 `[P]`.
- **US4:** T048 a T050 `[P]`; T051 e T052 `[P]`.
- **Piloto e execução completa:** os dois modelos rodam em paralelo, em processos separados.

---

## Parallel Example: User Story 1

```bash
# Testes de US1, independentes entre si:
Task: "Write tests in tests/ai_clients/llm/test_providers.py"
Task: "Write tests in tests/ai_clients/llm/test_interpret.py"
Task: "Write tests in tests/ai_clients/llm/test_cost.py"
Task: "Write tests in tests/ai_clients/llm/test_states.py"
Task: "Write tests in tests/ai_clients/llm/test_generation.py"

# Implementação em arquivos diferentes:
Task: "Implement src/ai_clients/llm/providers.py"
Task: "Implement src/ai_clients/llm/interpret.py"
Task: "Implement price_row_for/call_cost in src/ai_clients/llm/cost.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2, as duas P1)

1. Phase 1 + Phase 2 (com T006 antes de tudo e T002 aprovado).
2. Phase 3 (US1): uma combinação, do pedido ao `suite.json`, com o `FakeProvider`.
3. Phase 4 (US2): dry-run, confirmação e teto. **Nenhuma chamada paga é possível antes de US2
   estar pronta**, então o MVP utilizável é US1 + US2.
4. **STOP e VALIDE**: `pytest tests/ai_clients`, com o SLM sem regressão, e `generate --dry-run`
   real (T040).

### Incremental Delivery

1. US1 + US2 → gerar com custo controlado (MVP).
2. US3 → retomada, concorrência e troca de texto-base.
3. US4 → relatório, pacote e `cli check`.
4. Piloto (T055) → ponto de decisão (T056) → execução completa (T057) → documentação e
   fechamento.

### Ponto de decisão explícito (T056)

O piloto fixa o teto de saída e a razão caracteres/*token*, confirma a forma do JSON no Gemini e
mostra se há bloqueios, respostas barradas ou limite de requisições apertado. Mudar o teto, os
parâmetros ou o texto-base depois de começar a execução completa exige uma execução nova (o
`--resume` recusa), por isso tudo se decide aqui, com os autores, e é propagado antes de T057.

## Notes

- `[P]` = arquivos diferentes, sem dependência.
- `[Story]` mapeia a tarefa à história, para rastreabilidade.
- Confirme que os testes falham antes de implementar.
- Commit depois de cada tarefa ou grupo lógico, **sempre por decisão do autor** (Princípio X); o
  agente nunca commita.
- Pare em qualquer checkpoint para validar uma história isoladamente.
