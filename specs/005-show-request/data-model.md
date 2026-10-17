# Data Model: Visualizar o pedido enviado a cada modelo

**Feature**: `specs/005-show-request` | **Date**: 2026-10-16 | **Plan**: [plan.md](./plan.md)

A feature não muda nenhum arquivo que a geração grava. Ela **lê**:
- os registros de tentativa dos comerciais (`LlmAttempt`, `BarredResponse`);
- os registros do SLM (`GenerationRecord`);
- o `run.json` de cada árvore (`LlmRunConfig`, `RunConfig`);
- os arquivos do dataset.

Ela **cria** dois tipos de estrutura: as estruturas em memória da visualização (§1 a §4) e os
arquivos do dry-run com gravação (§5). Só o `summary.json` tem schema versionado (Princípio IV);
o texto do `show-request` é para leitura humana.

## 1. `TemplateSource` (em memória; `template_history.py`)

| Campo | Tipo | Regra |
|---|---|---|
| `path` | caminho relativo à raiz | `src/prompt_templates/llm_prompt.txt`, `slm_prompt.txt` ou `slm_predict_prompt.txt` (R2) |
| `expected_sha256` | hex de 64 | da tentativa; no SLM com `null`, do `run.json` para o tipo; na prévia, do arquivo atual |
| `origin` | `"current"` \| `"git"` | `current`: o arquivo de hoje tem o hash; `git`: achado no histórico |
| `commit` | hex curto \| `None` | só com `origin = "git"`: o commit mais recente que contém o blob |
| `template` | `PromptTemplate` | o texto normalizado e o hash, como o `load_template` devolve |

Achar nada é a exceção `TemplateNotFound(path, expected_sha256, current_sha256, reason)`, com
`reason` `"not_in_history"`, `"git_unavailable"` ou `"no_repository"` (código 1; R2).

## 2. `FidelityResult` (em memória; `requests_view.py`)

| Campo | Tipo | Regra |
|---|---|---|
| `checked` | lista de `"statement"`, `"code"`, `"example_input"`, `"example_output"` | conforme o cenário (R4) |
| `missing` | lista de `MissingPiece` | vazia ⇔ fiel |
| `scenario_leak` | lista de str | marca de outro cenário achada no prompt (`<reference_solution_cpp>` na caixa-preta, `<problem_statement>` na caixa-branca) |
| `faithful` | bool | `not missing and not scenario_leak` |

`MissingPiece`: `piece` (o trecho), `file` (`enunciado.md`, `AC_ref.cpp`, `testes.json`),
`matched_chars` (o maior prefixo do bloco achado no prompt), `expected_chars` (o tamanho do bloco).

## 3. `ExponentWarning` (em memória e no `summary.json`)

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id` | str | — |
| `matches` | lista de str, não vazia | o trecho de até 30 caracteres ao redor de cada ocorrência, na ordem do texto (R5) |

Só existe para os cenários com enunciado. O aviso é um só por problema e vale para os dois
cenários.

## 4. `RequestView` (em memória; o `show-request` grava o `body` e imprime uma linha com o resto)

| Campo | Tipo | Regra |
|---|---|---|
| `model` | `"slm"` \| `"gpt"` \| `"gemini"` | — |
| `problem_id`, `scenario` | str | — |
| `kind` | `"attempt"` \| `"barred"` \| `"preview"` | `barred` só nos comerciais |
| `number` | int | tentativa, número da barrada ou a próxima tentativa (na prévia) |
| `template` | `TemplateSource` | — |
| `prompt` | str | o texto inteiro |
| `prompt_sha256` | hex | do `prompt` |
| `recorded_prompt_sha256` | hex \| `None` | `None` só na prévia; se for diferente de `prompt_sha256`, a visualização **não existe** (erro, código 1) |
| `body` | dict | o corpo enviado (R1), com o prompt dentro; gravado no formato de [contracts/cli.md](./contracts/cli.md) §0 |
| `parameters_changed` | lista de str | chaves de `request_parameters` que mudaram desde a tentativa (só nos comerciais) |
| `fidelity` | `FidelityResult` | — |
| `exponent` | `ExponentWarning` \| `None` | — |

**Invariantes**:
- não há campo para a resposta do modelo (B3);
- não há campo com a chave da API (FR-004);
- um `RequestView` com `kind != "preview"` só é construído com `prompt_sha256 ==
  recorded_prompt_sha256` (FR-003, SC-004).

## 5. Arquivos de `generate --dry-run --save-requests DIR`

```text
DIR/<modelo>/
├── summary.json
├── 1_B.black_box.request.json    # o corpo da requisição, com o prompt dentro (contrato §0)
├── 1_B.white_box.request.json
├── 1_B.hybrid.request.json
└── …                             # <id>.<cenário>.request.json
```

Um arquivo por combinação, só com o corpo (decidido no analyze em 2026-10-16: o prompt já vem
dentro dele). O formato é o do [contrato](./contracts/cli.md) §0: JSON indentado, com `≤` legível,
e `json.loads` igual ao dos bytes enviados.

Só existem os arquivos das combinações **pendentes** selecionadas (R6). A pasta é **plana**, sem
subpasta por problema. Assim ela não é "uma pasta por problema" no sentido da constitution
(Princípio II, camada do `cli check`), e os arquivos de um problema ficam lado a lado na listagem,
porque o nome começa pelo id (decidido no analyze, 2026-10-16, achado C1).

### `summary.json` — `RequestsSummary` (Pydantic, `extra="forbid"`)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `Literal[1]` | — |
| `model` | `"slm"` \| `"gpt"` \| `"gemini"` | — |
| `created_at` | str (UTC, ISO 8601) | — |
| `dataset_manifest_sha256` | hex | o mesmo valor que o `run.json` guarda |
| `templates` | dict `tipo → sha256` | `llm` nos comerciais; `solution` e `prediction` no SLM; os hashes dos textos usados |
| `request_parameters` | dict | o corpo com `"<prompt>"` (comerciais); no SLM, `model` e `options` sem seed e temperatura, que vão por pedido |
| `combinations` | int ≥ 0 | quantos pedidos foram gravados |
| `faithful` | int ≥ 0 | ≤ `combinations` |
| `requests` | lista de `SavedRequest` | uma por combinação, em ordem de problema e cenário |
| `unfaithful` | lista de `UnfaithfulEntry` | `len == combinations - faithful` |
| `exponent_warnings` | lista de `ExponentWarning` | ordenada por `problem_id` |
| `damaged` | lista de str | combinações que não puderam ser lidas (`<id> <cenário>: <motivo>`) |

`SavedRequest`:
- `problem_id`, `scenario`, `attempt` (a próxima tentativa);
- `prompt_chars`, `prompt_sha256`, `template_sha256`, `faithful`;
- `request_file`, relativo a `DIR/<modelo>/`;
- no SLM, também `seed` e `temperature`.

`UnfaithfulEntry`: `problem_id`, `scenario`, `missing` (lista de `MissingPiece`), `scenario_leak`.

**Validações**:
- `faithful == sum(r.faithful for r in requests)`;
- `combinations == len(requests)`;
- os ids em `unfaithful` são exatamente os `requests` com `faithful = false`.
