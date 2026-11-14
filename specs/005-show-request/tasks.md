# Tasks: Visualizar o pedido enviado a cada modelo

**Input**: Design documents from `/specs/005-show-request/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md),
[quickstart.md](./quickstart.md); Constitution v1.7.1 (`.specify/memory/constitution.md`)

**Tests**: INCLUÍDOS. A Constitution (Princípio VI) exige suíte própria, e SC-001, SC-002 e SC-004
são verificados por teste. Em cada história, os testes vêm antes da implementação: escreva-os e
confirme que **falham** antes de implementar. Nenhum teste chama uma API nem o Ollama.

**Organization**: tarefas agrupadas por história de usuário, na ordem de prioridade da spec: as
duas P1 (US1, ver uma tentativa feita; US4, dry-run com gravação), depois US2 (prévia, P2) e US3
(arquivo, P3); por fim a validação no dado real e o fechamento.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec (US1 a US4); só nas fases de história
- Caminhos relativos à raiz do repositório
- **Onde rodar**: todo `pytest` no serviço `sandbox` (`docker compose run --rm sandbox pytest
  ...`, sem rede e sem o `.git` do projeto); `show-request`, `generate --dry-run`, lint e
  `check_docs_sync.py` no serviço `app` (`docker compose run --rm app ...`), o único com o `.git`
  montado

## Regras que valem para TODAS as tarefas (Constitution, Princípios II, III, V, VIII, IX, X, XI)

- **📌 PROPAGAR**: a tarefa marcada com 📌 produz dado medido ou decisão nova. Ela **só está
  concluída** depois de a informação ser escrita, **na própria tarefa**, em
  `docs/metodologia-referencia.md` (seção 3 e uma linha datada na seção 8) **e** nos artefatos da
  feature que ela afeta (`spec.md`, `plan.md`, `research.md`), com data e fonte.
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
  [contracts/cli.md](./contracts/cli.md) fazem parte do aceite; não as reinterprete.
- **Só leitura** (FR-002): nenhum comando desta feature chama uma API, o Ollama ou qualquer rede,
  nem lê `OPENAI_API_KEY`/`GEMINI_API_KEY`/`OLLAMA_BASE_URL`; a única escrita é o arquivo de
  `--output` ou a pasta de `--save-requests`, nunca dentro de `data/suites/`, `data/dataset/` ou
  `manifests/`.
- **Nada muda no que a geração grava nem envia**: os schemas de tentativa, `run.json` e `suite.json`
  não mudam; os bytes enviados pelos dois clientes continuam os mesmos (conferido em T008); a
  suíte inteira continua passando com o número de testes medido em T001 mais os novos.
- **Nunca mostrar como enviado um prompt cujo hash não confere** (FR-003, SC-004).
- **Git só para leitura**: o código chama apenas `git log` e `git cat-file`; o `.git` é montado
  `:ro` e só no serviço `app` (S1). O `sandbox` continua sem `.git` e sem `.env` (Princípio V).
- **Sem dependência nova**: `pyproject.toml` e `uv.lock` não mudam.
- **O agente nunca roda `git add`/`commit`/`push`** (Princípio X); as chamadas de Git do código
  são as de leitura acima, feitas pelo comando dos autores.

## Path Conventions

- **Código novo:** `src/ai_clients/requests_view.py` e `src/ai_clients/template_history.py`.
- **Mudanças pequenas:** `src/ai_clients/prompt.py` (`wire_bytes`), `ollama.py`,
  `llm/providers.py`, `store.py` e `llm/store.py` (pasta da árvore opcional), `__main__.py`
  (subcomando e opções), `llm/cli.py` (opção no dry-run).
- **Testes:** `tests/ai_clients/` e `tests/ai_clients/llm/` (sem `__init__.py`; `pytest` usa
  `--import-mode=importlib`), reaproveitando os construtores e falsos que já existem
  (`tests/ai_clients/llm/fakes.py`, `builders`, `conftest.py` e os do SLM).
- **Ambiente:** `docker-compose.yml`, comentário de `docker-compose.override.yml`.

---

## Phase 1: Setup

**Purpose**: medir a linha de base e preparar o ambiente.

- [X] T001 Medir a linha de base: `docker compose run --rm sandbox pytest -q` e anotar, nesta tarefa, o número de testes que passam (o "mesmo número mais os novos" das regras gerais) *(2026-10-16: 1.777 passando; depois da implementação, 1.868)*
- [X] T002 Acrescentar `"./.git:/app/.git:ro"` à lista `volumes` do serviço `app` em `docker-compose.yml` (só nele; **não** no `docker-compose.override.yml`, onde `sandbox: *dev` repetiria o mapa — research R8) e atualizar o comentário do topo de `docker-compose.override.yml` para dizer que o `.git` é montado somente leitura e só no `app`, pelo `docker-compose.yml`, e que o `.env` continua fora. Conferir: `docker compose run --rm app git -c safe.directory=* -C /app log --oneline -1` imprime o último commit; `docker compose run --rm sandbox test -e /app/.git` sai diferente de 0
- [X] T003 [P] Esqueleto de `src/ai_clients/template_history.py` e `src/ai_clients/requests_view.py` com docstrings de módulo (o que fazem, que só leem, research R2 e R4–R7), sem lógica

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: as peças que as quatro histórias usam: serialização única do corpo, texto-base pelo
hash, conferência de fidelidade, aviso de expoente e leitura de uma árvore escolhida.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

### Tests for Foundational ⚠️ (escrever primeiro; devem FALHAR)

- [X] T004 [P] Testes em `tests/ai_clients/test_template_history.py` (research R2, R9), num repositório Git temporário criado pelo teste (`git init` em `tmp_path`, `git -c user.name=t -c user.email=t@t commit`), com dois commits do mesmo `src/prompt_templates/llm_prompt.txt` (os 3 marcadores em cada versão):
  - o hash do arquivo atual devolve `origin = "current"`, `commit = None`;
  - o hash da 1ª versão devolve `origin = "git"` e o commit curto da 1ª;
  - a versão gravada com `\r\n` no Git é achada pelo hash do texto com `\n` (mesma normalização do `load_template`);
  - um hash ausente levanta `TemplateNotFound` com `reason = "not_in_history"`, o hash usado e o atual;
  - sem `.git` → `reason = "no_repository"`; com `PATH` sem `git` (monkeypatch) → `reason = "git_unavailable"`;
  - a lista de arquivos e os `mtime` de `.git/` são os mesmos antes e depois (só leitura)
- [X] T005 [P] Testes em `tests/ai_clients/test_fidelity.py` (research R4, R5; data-model §2 e §3), com um problema mínimo escrito pelo teste:
  - os três cenários, prompt de `build_prompt` → `faithful`; `checked` é `["statement", "example_input", "example_output"]` na caixa-preta, `["code", ...]` na caixa-branca e os quatro no híbrido;
  - `enunciado.md` com `\r\n` no arquivo → `missing` com `piece = "statement"`, `file = "enunciado.md"` e `matched_chars < expected_chars`;
  - prompt cortado no meio do código → `missing` com `piece = "code"`;
  - entrada do exemplo terminando em `" \n"` cortada além do `\n` → divergência; só `\n` finais cortados → fiel;
  - caixa-preta contendo `<reference_solution_cpp>` → `scenario_leak`, e `faithful = false`;
  - expoente: marcados `1 ≤ n ≤ 105`, `a_i < 109`, `(109 + 7)` e `does not exceed 104`; não marcados `10^5`, `100000`, `modulo 1000000007` e `105 apples` (sem operador antes); `matches` com o trecho de até 30 caracteres ao redor, na ordem do texto; caixa-branca → nenhum aviso
- [X] T006 [P] Testes em `tests/ai_clients/test_wire_bytes.py`: `prompt.wire_bytes(body) == json.dumps(body).encode("utf-8")` para um corpo com `≤` (vira `≤`); o `OllamaClient._open` e o `_Client.call` dos comerciais enviam exatamente `wire_bytes(body)` (capturar o `data` do `urllib.request.Request` com monkeypatch de `urlopen`, sem rede)
- [X] T007 [P] Testes em `tests/ai_clients/test_tree_dir.py`: os leitores de `store` (SLM) e `llm/store` com a pasta da árvore explícita (`tree=tmp/x`) leem `run.json`, tentativas, barradas e estado de uma árvore copiada para outra pasta; sem o parâmetro, o caminho é o de hoje (`data/suites/slm`, `data/suites/<modelo>`)

### Implementation for Foundational

- [X] T008 `wire_bytes(body: dict) -> bytes` em `src/ai_clients/prompt.py` (`json.dumps(body).encode("utf-8")`, sem outras opções) e trocar a serialização em `src/ai_clients/ollama.py` (`_open`) e `src/ai_clients/llm/providers.py` (`_Client.call`) por ela; T006 passa e a suíte do SLM e da 004 continua passando
- [X] T009 [P] `src/ai_clients/template_history.py` (research R2; data-model §1): `TemplateSource(path, expected_sha256, origin, commit, template)`, `TemplateNotFound(path, expected_sha256, current_sha256, reason)` com `reason` em `"not_in_history" | "git_unavailable" | "no_repository"`, e `resolve(root, rel_path, expected_sha256) -> TemplateSource`: 1) arquivo atual por `prompt.load_template`; 2) `git -c safe.directory=* -C <root> log --all --format=%h --raw --no-abbrev -- <rel_path>` para os blobs (os dois lados de cada mudança, sem repetir) e o commit mais recente de cada um; `git ... cat-file --batch` para lê-los; normalizar como o `load_template` (UTF-8, `\r\n` → `\n`), conferir os 3 marcadores e o `sha256`; 3) senão, `TemplateNotFound`. `subprocess.run` com lista de argumentos, `check=True`, sem `shell`. T004 passa
- [X] T010 [P] Em `src/ai_clients/requests_view.py`: `check_fidelity(root, problem_id, scenario, prompt) -> FidelityResult` e `exponent_warning(root, problem_id, scenario) -> ExponentWarning | None`, com `MissingPiece(piece, file, matched_chars, expected_chars)`, lendo **os bytes crus** de `enunciado.md`, `AC_ref.cpp` e `testes.json` (nunca o `ProblemInput`), com os blocos da tabela de research R4 e as três expressões de research R5 copiadas literalmente. T005 passa
- [X] T011 [P] Parâmetro opcional com a pasta da árvore nos leitores de `src/ai_clients/store.py` e `src/ai_clients/llm/store.py` (`read_run`, `attempt_files`/`combination_state`, `barred_files`, `read_generation`/`read_attempt`), no mesmo estilo de `ensure_tree`/`lock_tree`; sem o parâmetro, comportamento idêntico. T007 passa e nenhuma outra assinatura pública muda de sentido

**Checkpoint**: `docker compose run --rm sandbox pytest tests/ai_clients` passa com o número de T001 mais os novos.

---

## Phase 3: User Story 1 - Ver o pedido de uma tentativa já feita (Priority: P1) 🎯 MVP

**Goal**: `show-request --output ARQUIVO` grava o corpo da requisição (com o prompt dentro) de uma
tentativa gravada, nos três modelos, com o hash conferido, a fidelidade ao dataset conferida, o
texto-base antigo achado no Git quando preciso, e nunca a resposta. O pedido não é impresso no
terminal (FR-007, refinado no analyze em 2026-10-16).

**Independent Test**: com a tentativa 1 de `1_B` caixa-preta do piloto do Gemini
(`--suites-dir data/suites/gemini-piloto1`), o comando grava o corpo no arquivo pedido, imprime só
a linha `written: … prompt sha256 matches; dataset: faithful` e sai com 0; nenhuma API é chamada e
nenhum outro arquivo é gravado.

### Tests for User Story 1 ⚠️

- [X] T012 [P] [US1] Testes em `tests/ai_clients/llm/test_show_request.py` (gpt e gemini), com tentativas gravadas pela própria geração da 004 usando o `FakeProvider`:
  - sem `--attempt` → a última tentativa (`attempt N (of N)` na linha do terminal); `--attempt 2` → a 2;
  - o hash confere, e `json.loads` do arquivo gravado é igual ao corpo que o `FakeProvider` recebeu (o prompt dentro: `input` no gpt, `contents[0].parts[0].text` no gemini);
  - o arquivo é `json.dumps(body, indent=2, ensure_ascii=False)` mais `\n` (contrato §0): um prompt com `≤` aparece com `≤` literal no arquivo;
  - uma tentativa com `request_parameters` diferente do atual grava o corpo com os parâmetros **gravados** e imprime `warning: parameters changed since this attempt: <chaves>` (research R1);
  - `--barred 1` grava a barrada e imprime `barred response 1 (no reasoning tokens)`; `--barred` com `--attempt` → código 2;
  - nem o arquivo nem a saída do terminal contêm `raw_body`, `model_returned`, `usage` ou `cost` (B3), nem o valor de `OPENAI_API_KEY`/`GEMINI_API_KEY` definido no ambiente do teste;
  - **o prompt nunca aparece no stdout nem no stderr**;
  - `--suites-dir` lê uma árvore copiada
- [X] T013 [P] [US1] Testes em `tests/ai_clients/test_requests_view.py` (SLM). A tentativa 1 é gravada pela geração do SLM com o cliente falso do Ollama; as tentativas 13 e 15 podem ser construídas direto com os construtores de `GenerationRecord` dos testes do SLM:
  - tentativas 1, 13 e 15: o corpo gravado tem em `options` a seed e a temperatura daquela linha da política, e o `model` do `run.json`; 13 e 15 usam o texto-base de predição;
  - uma tentativa com `template_sha256 = null` usa o hash do `run.json` para o tipo (research R2, S5);
  - o hash confere, e `json.loads` do arquivo é o corpo que o cliente falso recebeu na tentativa 1
- [X] T014 [P] [US1] Testes de recusa e só leitura em `tests/ai_clients/llm/test_show_request_refusals.py` (na pasta `llm/`, que tem o provedor falso):
  - **SC-004**: texto-base alterado e não commitado (sem `.git`) → código 1, mensagem com os dois hashes, e o arquivo de saída **não** é criado;
  - texto-base antigo num repositório Git temporário (o `root` do teste com `git init`) → gravado, com `warning: OLD TEMPLATE VERSION from git <commit>`, código 0;
  - hash do prompt remontado diferente do gravado (registro editado no teste) → código 1, nada gravado;
  - dataset divergente do manifesto → código 1 (FR-008); combinação danificada → código 1;
  - prompt infiel ao dataset com hash conferido → gravado, linha `dataset: UNFAITHFUL — …`, código 1;
  - falta `--output`; modelo, problema ou cenário inexistente; `--attempt 4` com 3 tentativas (`has no attempt 4 (attempts: 1–3)`); `--barred` com `--model slm` → código 2;
  - uma tentativa que só existe em `superseded/` não é achada pela numeração; um arquivo temporário deixado na pasta da combinação (como o de uma geração em andamento) é ignorado;
  - **SC-002**: `socket.socket` trocado por um que falha e nenhuma tentativa de conexão; retrato de `data/` (caminhos, tamanhos, `mtime`) igual antes e depois, exceto o arquivo de `--output`

### Implementation for User Story 1

- [X] T015 [US1] `RequestView` e `build_view(root, model, problem_id, scenario, *, attempt=None, barred=None, tree=None) -> RequestView` em `src/ai_clients/requests_view.py` (data-model §4; research R1–R3): escolhe a tentativa (a maior atual, ou a pedida, ou a barrada), resolve o texto-base com `template_history.resolve`, monta o prompt com `prompt.build_prompt`, **recusa** se `prompt_sha256 != recorded_prompt_sha256` (exceção própria, código 1), monta o corpo (comerciais: `request_parameters` gravado com toda string igual a `PROMPT_PLACEHOLDER` trocada pelo prompt, e `parameters_changed` comparando com `providers.request_parameters(model)`; SLM: `ollama.request_body(run.model, prompt, generation.generation_options(run, n))`), e preenche `fidelity` e `exponent`. Invariantes do data-model §4: sem campo de resposta nem de chave
- [X] T016 [US1] Em `src/ai_clients/requests_view.py`: `body_text(body) -> str` (`json.dumps(body, indent=2, ensure_ascii=False) + "\n"`, contrato §0; usada também pelo dry-run), `write_output(path, text, *, force)` com a checagem de destino proibido (`data/suites/`, `data/dataset/`, `manifests/`) e de arquivo existente, compartilhada com T021, e `status_lines(view, path) -> list[str]` com a linha `written: …` e as linhas `warning:` exatas de [contracts/cli.md](./contracts/cli.md) §1 (nenhuma delas contém o prompt)
- [X] T017 [US1] Subcomando `show-request` em `src/ai_clients/__main__.py`: `--model {slm,gpt,gemini}`, `--problem`/`--scenario` e `--output ARQUIVO` obrigatórios (uma combinação), `--force`, `--attempt N`, `--barred N`, `--suites-dir DIR`; ordem de [contracts/cli.md](./contracts/cli.md) §1 (uso e destino → `dataset_gate` → `run.json`/combinação → texto-base → prompt → hash → corpo → conferências → gravação); códigos 0/1/2 de research R7 (prompt infiel com hash conferido: gravado e código 1); mensagens de recusa exatamente as do contrato, em stderr, sem gravar nada. T012 a T014 passam
- [X] T018 [US1] `src/ai_clients/README.md`: `show-request` (com `--output`, `--force`, `--attempt`, `--barred`, `--suites-dir`) na tabela única de comandos, no cenário "usar o que já existe", com o serviço `app` explicado (é o que lê o histórico do Git), o que o arquivo contém (o corpo, com o prompt dentro), que o terminal só mostra o resultado das conferências, e os códigos; linha `pendente` em "Comandos verificados"; `check_docs_sync.py --module ...` sai 0

**Checkpoint**: US1 funciona sozinha com `pytest tests/ai_clients` (MVP).

---

## Phase 4: User Story 4 - Conferir todos os pedidos contra o dataset antes de pagar (Priority: P1)

**Goal**: `generate --dry-run --save-requests DIR` grava, nos três modelos, o corpo de cada
combinação pendente (um arquivo, com o prompt dentro) e um `summary.json` com a fidelidade e os
avisos de expoente.

**Independent Test**: `generate --model gpt --dry-run --save-requests data/requests` grava os
arquivos e o resumo, sem chamar API e sem tocar em `data/suites/`.

### Tests for User Story 4 ⚠️

- [X] T019 [P] [US4] Testes em `tests/ai_clients/llm/test_save_requests.py` (os três modelos, dataset mínimo do teste):
  - grava **só** `DIR/<modelo>/<id>.<cenário>.request.json` (nenhum `.prompt.txt`), numa pasta **plana**, sem nenhuma subpasta em `DIR/<modelo>/` (data-model §5), só das combinações pendentes; `json.loads` de cada um é igual ao dos bytes (`wire_bytes`) do corpo que o cliente falso receberia na próxima tentativa, e o texto é o de `body_text` (contrato §0); respeita `--problem`, `--scenario` e `--limit`;
  - `summary.json` valida no `RequestsSummary` e cumpre as três validações do data-model §5; um prompt infiel (dataset com `\r\n` no `enunciado.md`) entra em `unfaithful` e o código é 1, com a gravação até o fim;
  - a saída do dry-run de hoje continua impressa antes da linha `requests: N saved in ...` (contrato §2), e nenhum prompt é impresso;
  - `DIR/<modelo>/` com arquivo → código 2; com `--force` apaga **só** `DIR/<modelo>/` (outro modelo em `DIR/` fica);
  - `--save-requests data/suites/x`, `data/dataset/x`, `manifests/x` ou `data` (que contém `data/suites`) → código 2;
  - `--save-requests` sem `--dry-run` → código 2; `--force` sem `--save-requests` → código 2;
  - nenhuma rede (socket que falha) e nenhum arquivo muda fora de `DIR/<modelo>/`; a chave e `OLLAMA_BASE_URL` não são lidas (ambiente sem elas)

### Implementation for User Story 4

- [X] T020 [P] [US4] `RequestsSummary`, `SavedRequest` e `UnfaithfulEntry` (Pydantic, `extra="forbid"`, `schema_version: Literal[1]`) em `src/ai_clients/requests_view.py`, com os campos e as validações literais do data-model §5 (`SavedRequest` com `request_file` e sem arquivo de prompt; "`faithful == sum(r.faithful for r in requests)`; `combinations == len(requests)`; os ids em `unfaithful` são exatamente os `requests` com `faithful = false`")
- [X] T021 [US4] `save_requests(root, model, pending, dest, *, force) -> RequestsSummary` em `src/ai_clients/requests_view.py` (research R6): a checagem de destino de T016 (pasta proibida; `DIR/<modelo>/` com arquivos), um arquivo por combinação, `<id>.<cenário>.request.json`, direto em `DIR/<modelo>/` (pasta plana, data-model §5; texto de `body_text`), `summary.json`, e as linhas de terminal do contrato §2 (`requests: …`, `unfaithful: …`, `exponent: …`)
- [X] T022 [US4] Ligar `--save-requests DIR` e `--force` ao dry-run: no SLM em `src/ai_clients/__main__.py` (`_dry_run_generate` passa as combinações pendentes com a próxima tentativa e o texto-base dela) e nos comerciais em `src/ai_clients/llm/cli.py` (`_estimate`/`run_generate`); código final combinado (1 se infiel ou danificado). T019 passa
- [X] T023 [US4] `src/ai_clients/README.md`: `generate --dry-run --save-requests` na tabela única (as duas variações `--force`; um arquivo por combinação com o corpo, que traz o prompt; `≤` legível no arquivo; a sugestão `data/requests`), linha `pendente` em "Comandos verificados"; `check_docs_sync.py --module ...` sai 0

**Checkpoint**: US1 e US4 (as duas P1) funcionam; `pytest tests/ai_clients` passa.

---

## Phase 5: User Story 2 - Ver o pedido que seria feito, antes de gastar (Priority: P2)

**Goal**: para uma combinação sem tentativa, `show-request` grava a prévia e diz no terminal que
ela não foi enviada.

**Independent Test**: numa árvore sem tentativas para `1_B` híbrido, o comando grava o corpo,
imprime `written: … preview, not sent (next: attempt 1)` e sai com 0.

### Tests for User Story 2 ⚠️

- [X] T024 [P] [US2] Testes em `tests/ai_clients/llm/test_show_request_preview.py` (junto com os de T027):
  - sem árvore (`data/suites/<modelo>` inexistente) e sem tentativa → prévia, com o corpo atual (`providers.request_body`; no SLM `config.MODEL`, `sampling_options()` e a seed/temperatura de `config.attempt_spec(1)`, sem chamar o Ollama);
  - combinação com 1 tentativa por formato e ainda pendente, sem `--attempt` → grava a tentativa 1 (a última feita), não a prévia;
  - sem tentativa e `--attempt 1` → código 2 (`has no attempt 1 (no attempt yet)`), nada gravado;
  - a prévia nunca procura no Git (o hash esperado é o do arquivo atual)

### Implementation for User Story 2

- [X] T025 [US2] Ramo `kind = "preview"` em `build_view` e o trecho `preview, not sent (next: attempt N)` em `status_lines`, em `src/ai_clients/requests_view.py` (research R1 e R3); a mensagem de uso do contrato para `--attempt` sem tentativa em `src/ai_clients/__main__.py`. T024 passa
- [X] T026 [US2] `src/ai_clients/README.md`: a prévia na linha do `show-request` da tabela única (o que é gravado quando ainda não há tentativa); `check_docs_sync.py --module ...` sai 0

---

## Phase 6: User Story 3 - Guardar o arquivo sem perder um anterior (Priority: P3)

**Goal**: o arquivo de `show-request --output` nunca sobrescreve outro sem `--force`, e nunca cai
numa pasta do experimento.

**Independent Test**: repetir a visualização da US1 com o mesmo `--output` é recusado; com
`--force`, o arquivo é sobrescrito com o mesmo conteúdo.

### Tests for User Story 3 ⚠️

- [X] T027 [P] [US3] Testes em `tests/ai_clients/llm/test_show_request_preview.py` (parte "the output file"):
  - arquivo existente sem `--force` → código 2 (`already exists; use --force`) e o arquivo não muda; com `--force` → sobrescrito;
  - caminho dentro de `data/suites/`, `data/dataset/` ou `manifests/` → código 2, nada criado;
  - nas recusas de código 1 (hash, texto-base), o arquivo **não** é criado, e um arquivo existente com `--force` também não é tocado
- [X] T028 [US3] Ajustes, se T027 apontar algum, em `write_output` (`src/ai_clients/requests_view.py`) e no `show-request` (`src/ai_clients/__main__.py`): a checagem do destino acontece antes de qualquer leitura, e a escrita só depois de todas as conferências. T027 passa
- [X] T029 [US3] `src/ai_clients/README.md`: o que `--force` faz e as pastas recusadas, na linha do `show-request`; `check_docs_sync.py --module ...` sai 0

---

## Phase 7: Validação no dado real e fechamento

**Purpose**: rodar o [quickstart](./quickstart.md) no dataset e nas árvores reais, carimbar os
comandos e propagar os números.

- [X] T030 📌 PROPAGAR — **Dry-run com gravação** (quickstart, nível 2; SC-005):
  - **GPT**, antes da execução completa dele: `generate --model gpt --dry-run --save-requests data/requests` → 600 de 600 fiéis;
  - **SLM**: rodar o mesmo comando; registrar quantas combinações pendentes foram gravadas (a execução terminou, então devem ser 0);
  - **Gemini**: a execução completa já começou; os autores rodam um dry-run separado (decidido no analyze em 2026-10-16); registrar quantas combinações pendentes foram gravadas e que todas são fiéis;
  - **calibração do expoente** no GPT (600 pendentes): os problemas avisados são exatamente os 71 da metodologia (seção 3); qualquer diferença é examinada à mão e registrada antes de mudar a expressão (research R5);
  - abrir `data/requests/gpt/1_B.black_box.request.json` e conferir o `input` contra o `enunciado.md`;
  - o tempo não é medido (SC-003);
  - registrar os números em `research.md` (R5, R6), no SC-005 de `spec.md` e na metodologia (seção 3 + seção 8);
  - carimbar `generate --dry-run --save-requests` no README e fazer a revisão de prosa por `grep`
- [X] T031 📌 PROPAGAR — **Tentativas feitas** (quickstart, nível 3; SC-001):
  - as 15 combinações de `data/suites/gemini-piloto1` com `--suites-dir` e `--output`: todas com código 0, hash conferido e `dataset: faithful`, e nenhum prompt no terminal;
  - o SLM (`data/suites/slm`): as tentativas 1 e 12 de `1000_B` caixa-preta e uma tentativa de predição (13 a 15), se houver; uma árvore de piloto antigo com o texto-base mudado (`--suites-dir data/suites/slm-piloto2` ou outra): versão antiga achada no Git, ou recusa com os dois hashes;
  - repetir um `--output` sem `--force` → código 2 (US3);
  - registrar os resultados (quantas conferidas, quantas pelo Git, quantas recusadas e por quê) em `research.md` R2 e na metodologia (seção 3 + seção 8); carimbar `show-request` no README e fazer a revisão de prosa por `grep`
- [X] T032 [P] **Prévia** (quickstart, nível 4): antes da execução completa do GPT, `show-request --model gpt --problem 1_B --scenario hybrid --output data/requests/1_B.hybrid.json` → `written: … preview, not sent (next: attempt 1)`, código 0; `--attempt 1` → código 2
- [X] T033 📌 PROPAGAR — **Documentação de uso**:
  - **`README.md` da raiz:** "Referência de comandos" com `show-request` e `generate --dry-run --save-requests`; na preparação do ambiente, que o serviço `app` lê o histórico do Git (somente leitura) e o `sandbox` não;
  - **`CLAUDE.md`:** "Comandos do dia a dia" com os dois comandos;
  - **Metodologia:** marcar a nota da seção 3 como implementada, com uma linha na seção 8;
  - **Checagem:** `docker compose run --rm app python scripts/check_docs_sync.py` e o `--module ...` saem 0
- [ ] T034 Constitution v1.7.1 compliance review: refazer a tabela "Constitution Check" de `plan.md` contra o código. *(2026-10-16: as quatro conferências abaixo passaram — o `.git` aparece só no `app`, o `git` só em `template_history.py` com `log` e `cat-file`, nada de rede ou chave nos dois módulos novos, `pyproject.toml` e `uv.lock` sem mudança; falta a revisão do código por um dos autores.)* Em especial: *(2026-11-14: sem mudança — falta o registro da revisão do código por um dos autores.)*
  - **V:** `docker compose config` mostra `/app/.git` (`read_only: true`) só no `app`;
  - **X:** `grep -rn "subprocess\|\"git\"" src/ai_clients` mostra só `log` e `cat-file`, em `template_history.py`;
  - **VIII/FR-002:** `grep -rn "urlopen\|API_KEY\|OLLAMA_BASE_URL" src/ai_clients/requests_view.py src/ai_clients/template_history.py` não encontra nada;
  - **IX:** `pyproject.toml` e `uv.lock` sem mudança.

  Desvios vão em "Complexity Tracking". Um dos autores revisa o código gerado com apoio de IA (Princípio X); registrar quem e quando.
- [ ] T035 Fechamento: *(2026-10-16: suíte inteira com 1.868 passando, `ruff` e `black --check` em 0, `check_docs_sync.py` e `--module` em 0. O `--closing` aponta 11 linhas de "Comandos verificados": 9 da feature 004, pendentes ou carimbadas em revisão suja, e as 2 desta, carimbadas em `d005d57+dirty`; estas 2 fecham ao rodar os dois comandos de novo depois do commit e carimbar a revisão limpa.)* *(2026-11-14: fechamento depende de recarimbar comandos em revisão commitada; ver nota da T060 da feature 004.)*
  - `docker compose run --rm sandbox pytest` (suíte inteira) passa, com o número de T001 mais os novos;
  - `docker compose run --rm app ruff check .` e `docker compose run --rm app black --check .` saem 0;
  - `docker compose run --rm app python scripts/check_docs_sync.py --closing --feature specs/005-show-request` sai 0;
  - **Entrega:** dizer aos autores os arquivos a commitar (código, testes, `docker-compose.yml`, `docker-compose.override.yml`, documentação; **não** `data/requests/`, que fica fora do Git), **sem** rodar nenhum comando de Git

---

## Phase 8: A tentativa que gerou cada suíte, de uma vez (FR-014; pedido dos autores em 2026-10-18)

- [X] T036 [P] Testes em `tests/ai_clients/llm/test_suite_attempts.py` (comerciais: a tentativa do `suite.json`, não a última; combinação sem suíte pulada; hash que não confere recusado e não gravado; filtros e destino; erros de uso; árvore sem `run.json`) e em `tests/ai_clients/test_requests_view.py` (SLM: `accepted_fallback` da tentativa 3 com 12 feitas; `discarded_manual` pulada)
- [X] T037 `suite_attempt_requests` em `src/ai_clients/requests_view.py`, `source` e `skipped` no `RequestsSummary`, `read_suite` com a pasta da árvore em `src/ai_clients/store.py` e `src/ai_clients/llm/store.py`, e `--suite-attempts`/`--output-dir` no `show-request` em `src/ai_clients/__main__.py` (research R12)
- [X] T038 📌 PROPAGAR — Rodar no SLM real e registrar em `research.md` R12, SC-006 e metodologia (seção 3 + seção 8): `show-request --model slm --suite-attempts` sobre a execução completa do SLM: 600 de 600 pedidos gravados, todos com o hash do prompt conferido e fiéis ao dataset, nenhum pulado nem recusado, aviso de expoente nos mesmos 71 problemas (142 combinações), cerca de 23 s; a tentativa que gerou a suíte foi a 1 em 355 combinações, a 2 em 84, a 3 em 32, de 4 a 12 em 127 e a 14 e a 15 (predição) em 1 cada; em `1000_B` caixa-preta (`accepted_fallback`) a suíte veio da tentativa 1, embora a última feita tenha sido a 12
- [X] T039 Documentação de uso: a variação na tabela única de `src/ai_clients/README.md`, a "Referência de comandos" do `README.md` da raiz e o `CLAUDE.md`; `check_docs_sync.py` em 0

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 antes de qualquer mudança; T002 e T003 `[P]`.
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias. T008 antes de T021
  (o corpo gravado usa `wire_bytes`).
- **US1 (Phase 3)**: depende da Fase 2.
- **US4 (Phase 4)**: depende da Fase 2 (fidelidade, expoente, `wire_bytes`) e de T016 (`body_text`
  e a checagem de destino); o resto é independente de US1, exceto pelo README (T023 depois de T018,
  mesmo arquivo).
- **US2 (Phase 5)**: depende de US1 (T015–T017: o mesmo `build_view` e o mesmo subcomando).
- **US3 (Phase 6)**: depende de US1 (T016, T017: `write_output` e o subcomando).
- **Phase 7**: depende de todas as histórias; T030 e T031 rodam no serviço `app` com o dado real;
  T030 (GPT) e T032 só antes da execução completa do GPT; T033 a T035 por último.

### Within Each User Story

- Testes escritos e vistos falhar antes da implementação.
- `template_history`/fidelidade → `build_view` → `body_text`/`status_lines`/`write_output` → subcomando → README.
- Cada história termina com o README do módulo atualizado e `check_docs_sync.py --module` em `0`.

### Parallel Opportunities

- **Fase 2:** T004 a T007 (testes) em arquivos diferentes; T009, T010 e T011 em arquivos
  diferentes (T008 toca `prompt.py`, `ollama.py` e `providers.py`, sem conflito com eles).
- **US1:** T012, T013 e T014 `[P]`.
- **US4:** T019 e T020 `[P]`; US4 inteira pode andar em paralelo com US1 (só o README é comum).
- **US2 e US3:** os testes T024 e T027 `[P]`.

---

## Parallel Example: Foundational

```bash
# Testes, independentes entre si:
Task: "Write tests in tests/ai_clients/test_template_history.py"
Task: "Write tests in tests/ai_clients/test_fidelity.py"
Task: "Write tests in tests/ai_clients/test_wire_bytes.py"
Task: "Write tests in tests/ai_clients/test_tree_dir.py"

# Implementação em arquivos diferentes:
Task: "Implement resolve() in src/ai_clients/template_history.py"
Task: "Implement check_fidelity/exponent_warning in src/ai_clients/requests_view.py"
Task: "Add the optional tree folder to src/ai_clients/store.py and src/ai_clients/llm/store.py"
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 + Phase 2 (T001 antes de tudo).
2. Phase 3 (US1): ver uma tentativa feita, nos três modelos, com hash e Git.
3. **STOP e VALIDE**: `pytest tests/ai_clients` e o piloto do Gemini (parte de T031).

### Incremental Delivery

1. US1 → ver o que foi enviado (MVP).
2. US4 → conferir todos os pedidos contra o dataset antes de pagar (a outra P1; pode vir antes de
   US1 se a conferência for mais urgente, por exemplo antes da execução completa do GPT).
3. US2 → prévia de uma combinação.
4. US3 → gravar num arquivo.
5. Validação no dado real (T030–T032) → documentação e fechamento.

## Notes

- `[P]` = arquivos diferentes, sem dependência.
- `[Story]` mapeia a tarefa à história, para rastreabilidade.
- Confirme que os testes falham antes de implementar.
- Commit depois de cada tarefa ou grupo lógico, **sempre por decisão do autor** (Princípio X); o
  agente nunca commita.
- Pare em qualquer checkpoint para validar uma história isoladamente.
