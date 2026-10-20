# Tasks: Terceiro modelo comercial: Claude

**Input**: Design documents from `/specs/008-claude-test-generation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md),
[contracts/provider.md](./contracts/provider.md), [quickstart.md](./quickstart.md); Constitution
**v1.9.0** (emenda de escopo aplicada em 2026-10-20)

**Tests**: INCLUÍDOS (Princípio VI). Os testes de cada história vêm antes da implementação.
Nenhum teste chama a API: o provedor é falso, e as respostas no formato da Anthropic ficam em
`tests/ai_clients/llm/fakes.py`.

**Organization**:
- base: configuração e corpo de resposta falso;
- US1 (P1): pedido e leitura da resposta;
- US2 (P1): custo, dry-run e teto;
- US3 (P2): piloto e retomada;
- US4 (P3): relatório, pacote e `cli check`;
- por fim, a documentação, a execução real e o fechamento.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: arquivos diferentes, sem dependência de tarefa incompleta
- **[Story]**: US1 a US4, só nas fases de história
- **Onde rodar**: `pytest` no `sandbox`; os comandos no `app`

## Regras que valem para TODAS as tarefas (Constitution 1.9.0)

- **📌 PROPAGAR**: dado medido ou decisão nova vai, na própria tarefa, para
  `docs/metodologia-referencia.md` (seção 3 e histórico) e para `spec.md`/`plan.md`/`research.md`.
- **Nada muda nos outros modelos** (FR-019): os testes do modelo local, do GPT e do Gemini passam
  sem mudança de comportamento.
- **Muitos testes da 004 são parametrizados por `config.MODELS`**: ao entrar `"claude"`, eles passam
  a rodar também com o Claude, o que já é parte da cobertura. Um teste que falhar só por isso é
  ajustado no corpo falso, nunca no comportamento.
- **Documentação como critério de aceite**:
  - READMEs no formato de `docs/template-modulo.md`;
  - `check_docs_sync.py` sai 0;
  - comando novo nasce `pendente` em "Comandos verificados".
- **Sem dependência nova** (nenhum SDK). **O agente nunca roda `git add`/`commit`/`push`**.
- **Execução paga só com pedido explícito dos autores.**

---

## Phase 1: Setup

- [X] T001 Medir a linha de base: `docker compose run --rm sandbox pytest -q`, anotando o número de testes que passam — **1.941** (2026-10-20); depois da feature, **1.981**
- [X] T002 [P] `.env.example`: `ANTHROPIC_API_KEY=` e as opcionais `ANTHROPIC_MAX_CONCURRENCY`, `ANTHROPIC_MAX_INFRA_RETRIES` e `ANTHROPIC_MAX_REQUESTS_PER_MINUTE`, comentadas como as do GPT e do Gemini (contrato cli.md)

---

## Phase 2: Foundational

- [X] T003 [P] `tests/ai_clients/llm/fakes.py`:
  - `anthropic_body(text=None, *, stop_reason="end_turn", category=None, thinking=1200, input_tokens=2000, cached=0, output=1500, model="claude-haiku-5-5", response_id="msg_1", thinking_block=True)`, com o formato de research R3/R4:
    - os blocos `content`: um `thinking` com texto vazio e `signature`, quando `thinking_block`, e depois um `text` com a resposta;
    - `usage` com `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens` e `output_tokens_details.thinking_tokens` (ausente quando `thinking=None`);
    - `stop_details` só na recusa;
  - `body("claude", ...)` usa esse formato;
  - `answer("claude", reasoning=0)` monta uma resposta sem raciocínio, como nos outros dois.
- [X] T004 `src/ai_clients/llm/config.py` (research R7):
  - `MODELS = ("gpt", "gemini", "claude")`;
  - `MODEL_ID["claude"] = "claude-haiku-5-5"`;
  - `ENDPOINT["claude"] = "https://api.anthropic.com/v1/messages"`;
  - `ANTHROPIC_VERSION = "2023-06-01"`;
  - `CHARS_PER_TOKEN["claude"] = 3.0`, com origem "conservative, before the pilot";
  - `MEASURED_MEAN_OUTPUT_TOKENS["claude"] = None`;
  - linha de preço `Price("claude", date(2026, 10, 20), 0.10, 0.01, 0.50, "https://platform.claude.com/docs/en/about-claude/pricing", date(2026, 10, 20))`;
  - `CLAUDE_PROMPT_TOKEN_LIMIT = 100_000`, o limite do preço cadastrado;
  - as quatro variáveis `ANTHROPIC_*` nos dicionários `ENV_*`.

  `src/ai_clients/llm/schemas.py`: `LlmModel = Literal["gpt", "gemini", "claude"]`.

**Checkpoint**: `pytest tests/ai_clients/llm` mostra quais testes parametrizados ainda não sabem o formato do Claude; a US1 resolve.

---

## Phase 3: User Story 1 — Gerar a suíte de uma combinação com o Claude (P1) 🎯 MVP

**Goal**: o pedido e a leitura da resposta do Claude, com a regra da resposta sem raciocínio.

**Independent Test**: com o provedor falso, uma combinação vira `suite.json`; o corpo enviado é o de research R1; as respostas sem raciocínio vão para `barred/`.

### Tests ⚠️

- [X] T005 [P] [US1] `tests/ai_clients/llm/test_providers.py`, casos do Claude:
  - **Corpo do pedido**, exatamente: `model`, `max_tokens` 32768, uma mensagem `user`, `thinking` `{"type": "adaptive"}`, `output_config.effort` `"medium"`, `output_config.format` `{"type": "json_schema", "schema": response_schema()}`; nenhuma chave de `FORBIDDEN_PARAMETERS`; sem `system`.
  - **Cabeçalhos**: `x-api-key`, `anthropic-version: 2023-06-01` e `content-type`.
  - **Leitura da resposta**:
    - o texto é a junção dos blocos `text` (o bloco `thinking` é ignorado);
    - `reasoning_tokens` vem de `thinking_tokens`, ou é `None` se o campo faltar;
    - a entrada soma os três campos de entrada;
    - `stop_reason` e `stop_details.category` vão para `Finish`;
    - um corpo que não é objeto JSON é `ProviderUnavailable`.
  - **Erros**:
    - 429 com `retry-after`, 529 e 500 dão `ProviderUnavailable`;
    - 401/403, 404 e 400 dão `ProviderFatal`;
    - um 400 com "credit balance" dá a mensagem de crédito esgotado;
    - a chave nunca aparece em mensagem nenhuma.
- [X] T006 [P] [US1] `tests/ai_clients/llm/test_interpret.py`: no Claude, `stop_reason` `max_tokens` e `model_context_window_exceeded` dão `truncated`, e `refusal` dá `refusal`. Uma resposta normal passa pelas mesmas 7 falhas de formato.
- [X] T007 [P] [US1] `tests/ai_clients/llm/test_generation.py`: `--model claude` de ponta a ponta, com o provedor falso:
  - uma combinação vira `accepted_predicted`;
  - três respostas sem raciocínio (`thinking_tokens` 0, e também campo ausente) viram `accepted_barred`;
  - falha de formato leva à próxima tentativa;
  - o `run.json` grava os parâmetros de research R1 e o mesmo `template_sha256` de uma execução do Gemini.

### Implementation

- [X] T008 [US1] `src/ai_clients/llm/providers.py`:
  - **`request_body("claude", prompt)`** com o corpo de research R1;
  - **`_claude_answer`** com o mapeamento de data-model §3;
  - **`answer_from_body`** que despacha para o Claude;
  - **`ClaudeClient`** com os cabeçalhos;
  - **`classify_http_error`**: a mensagem de crédito esgotado para o 400 com "credit balance";
  - `CLIENTS["claude"]`.
- [X] T009 [US1] `src/ai_clients/llm/interpret.py`: `_finish_failure` reconhece os términos da Anthropic (`max_tokens` e `model_context_window_exceeded` dão `truncated`; a recusa já vem pelo campo `refusal`). T005 a T007 passam.

**Checkpoint**: `pytest tests/ai_clients/llm` passa por completo, com o Claude nos testes parametrizados.

---

## Phase 4: User Story 2 — Custo antes e nunca pagar sem confirmar (P1)

**Goal**: o dry-run e o teto de gasto do Claude.

**Independent Test**: o dry-run sem chave dá 600 combinações e a faixa de custo; `generate` sem `--confirm-spend` não chama nada; com teto baixo, para no teto.

### Tests ⚠️

- [X] T010 [P] [US2] `tests/ai_clients/llm/test_cost.py` e `test_estimate.py`:
  - o custo de uma chamada do Claude usa a linha de 2026-10-20;
  - a entrada em cache é cobrada a 0,01;
  - uma chamada com mais de `CLAUDE_PROMPT_TOKEN_LIMIT` tokens de entrada é recusada com a mensagem do contrato;
  - o dry-run imprime a linha do Claude com a origem "conservative, before the pilot" e funciona sem `ANTHROPIC_API_KEY`.
- [X] T011 [P] [US2] `tests/ai_clients/llm/test_spend_cap.py` e `test_cli_model.py`:
  - `--model claude` sem `--confirm-spend` sai com `2` sem chamada;
  - sem a chave, sai com `2` e nomeia `ANTHROPIC_API_KEY`;
  - o teto vale como nos outros.

### Implementation

- [X] T012 [US2] `src/ai_clients/llm/cost.py` (e o que for preciso no dry-run): a recusa acima do limite de prompt do Claude. T010 e T011 passam.

---

## Phase 5: User Story 3 — Piloto, retomada e execução completa (P2)

**Goal**: retomar sem refazer nada, e o caminho do piloto.

**Independent Test**: interromper e retomar não refaz tentativa; duas invocações juntas do Claude dividem o trabalho; o Claude roda junto com o Gemini sem bloqueio.

- [X] T013 [P] [US3] `tests/ai_clients/llm/test_resume.py` e `test_concurrency.py`:
  - a retomada do Claude não refaz tentativa;
  - uma execução do Claude e uma do Gemini, juntas, não se bloqueiam;
  - a retomada com configuração diferente (outro `effort` gravado) sai com `2`.
- [X] T014 [US3] Se T013 apontar algo além de configuração, ajustar o código. Se não, registrar no `tasks.md` que a 004 já cobria. **Feito: a 004 já cobria; só o teste dos modelos juntos passou a rodar os três.**

---

## Phase 6: User Story 4 — Relatório, pacote e conferência (P3)

**Goal**: o relatório, o pacote e o manifesto do Claude, e a camada `claude_suites`.

**Independent Test**: uma execução do Claude terminada se empacota e se confere; o `cli check --deep` sai `OK` com a camada nova.

### Tests ⚠️

- [X] T015 [P] [US4] `tests/ai_clients/llm/test_packaging.py` e `test_report.py`: `package --model claude` gera `data/claude_suites.zip`, o manifesto e o relatório. O manifesto só aceita caminhos `suites/claude/...`. O `verify --model claude` confere o pacote.
- [X] T016 [P] [US4] `tests/cli/test_consistency.py`:
  - a camada `claude_suites` aparece com o título "Suítes do Claude Haiku 5.5";
  - sem pasta, é aviso;
  - com o pacote, `--deep` sai `OK`;
  - entra na relação 1:1;
  - `--only claude_suites` funciona;
  - as saídas das outras camadas não mudam.

### Implementation

- [X] T017 [US4] `src/cli/consistency.py`: `CLAUDE_SUITES_LAYER = _llm_layer("claude", "Claude Haiku 5.5")` em `LAYERS`. `docs/verificacao-consistencia.md` ganha uma seção datada com a camada. T015 e T016 passam.

---

## Phase 7: Documentação e execução real

- [X] T018 Documentação:
  - **`src/ai_clients/README.md`**: os 3 modelos comerciais, `--model claude` na tabela única, as variáveis `ANTHROPIC_*` nas entradas, e as linhas `pendente` em "Comandos verificados" para o `generate --model claude` e os demais comandos;
  - **`README.md` da raiz**: "Três modelos (dois LLMs comerciais" passa a 4 modelos e 3 comerciais, e a "Referência de comandos" ganha `--model claude`;
  - **`CLAUDE.md`**: a lista dos modelos, `data/claude_suites.zip` e a referência à constitution 1.9.0;
  - **`check_docs_sync.py`** sai 0.
- [X] T019 📌 PROPAGAR — **Dry-run real** (sem custo): `generate --model claude --dry-run` e `--save-requests`. Registrar na metodologia a faixa de custo das 600 combinações e confirmar que o `template_sha256` é o mesmo dos outros dois.
- [X] T020 📌 PROPAGAR — **Piloto (pago; só com pedido dos autores)** — **substituído (2026-10-20, Milena)** pela chamada de conferência (`--limit 1`: `thinking_tokens` 5.165, US$ 0,0031); as medidas vêm da execução completa (T021), quickstart §2:
  - primeiro `--limit 1`, para conferir o sinal de raciocínio (research R2, S2);
  - depois os 5 problemas.

  Registrar na metodologia, no `research.md` e no `config.py`:
  - a razão caracteres/token e a média de saída;
  - a latência;
  - a taxa de falha de formato e a de respostas sem raciocínio;
  - o custo real comparado com o dry-run.

  Guardar o relatório do piloto e mover a pasta.
- [X] T021 📌 PROPAGAR — **Execução completa (paga; só com pedido dos autores)**, quickstart §3. Carimbar os comandos em "Comandos verificados" e corrigir as frases que os davam como pendentes (grep nos dois READMEs).

---

## Phase 8: Polish

- [X] T022 Conferência contra a constitution 1.9.0 no `plan.md`: Princípios III, VIII e IX, conferidos contra o código e os testes.
- [X] T023 Fechamento:
  - a suíte inteira passa (comparar com T001);
  - `ruff` e `black` limpos;
  - `check_docs_sync.py` e `--feature specs/008-claude-test-generation` saem 0;
  - `spec.md` com o status;
  - o comando de commit para os autores (o agente não roda Git).

---

## Dependencies & Execution Order

- **T003 e T004** (base) bloqueiam todas as histórias.
- **US1** (T005 a T009) bloqueia a US2 a US4, porque sem o cliente os testes parametrizados falham.
- **US2, US3 e US4** podem andar em paralelo depois da US1.
- **T018** depois da US4.
- **T019** depois de T018.
- **T020 e T021**: pagos, só com pedido explícito dos autores; T020 antes de T021.
- **[P]**: T002/T003; T005/T006/T007; T010/T011; T015/T016.

## Implementation Strategy

1. **MVP**: base + US1. O Claude gera suítes com o provedor falso, e os testes parametrizados passam.
2. **US2 a US4**: custo, retomada, pacote e `cli check`.
3. **Documentação e dry-run real**, sem custo.
4. **Piloto e execução completa**: pagos, quando os autores pedirem.

## Fechamento (2026-10-20)

- T021: execução completa — 589 `accepted_predicted`, 8 `accepted_barred`, 3 `discarded_manual`, 632 chamadas, US$ 0,98; pacote conferido (`verify` e `cli check --deep`).
- T023: 1.981 testes passando; `ruff`, `black` e `check_docs_sync` (raiz e `--feature`) limpos.
