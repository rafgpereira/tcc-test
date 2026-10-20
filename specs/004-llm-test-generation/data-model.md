# Data Model: Geração de Suítes de Teste pelos LLMs Comerciais

**Feature**: `004-llm-test-generation` | **Plan**: [plan.md](./plan.md) | **Research**:
[research.md](./research.md)

Todo JSON segue as mesmas regras do SLM:
- UTF-8, chaves ordenadas, indentação 2 e `\n` final;
- escrita atômica, com `dataset.persistence.store.atomic_write_json`;
- arquivo gravado uma vez e nunca alterado, salvo onde dito.

Os schemas são Pydantic com `extra="forbid"` (classe base `dataset.schemas.common.Schema`). Os
arquivos novos têm `schema_version: 1`. O `suite.json` tem `schema_version: 2`, o mesmo contrato
de arquivo do SLM (R1).

## 1. Árvore (uma por modelo; `<m>` ∈ `gpt`, `gemini`)

```text
data/suites/<m>/
├── .lock                                   # flock da execução (compartilhado no generate --resume)
├── .locks/<id>__<cenário>.lock            # flock por combinação
├── run.json                                # LlmRunConfig (§3.1)
├── problems/<id>/<cenário>/                # cenário ∈ black_box | white_box | hybrid
│   ├── attempt_1.json                      # LlmAttempt (§3.2)
│   ├── attempt_2.json                      # só se a 1 falhou por formato
│   ├── attempt_3.json                      # só se a 2 falhou por formato
│   ├── manual_close.json                   # ManualClose (o mesmo do SLM), só depois do close
│   └── suite.json                          # LlmSuite (§3.4), estado terminal
├── barred/<id>/<cenário>/<n>.json          # BarredResponse (§3.3), resposta sem raciocínio
├── template_changes/<NNN>.json             # LlmTemplateChange (§3.9), template "llm"
└── superseded/<NNN>/<id>/<cenário>/…       # o que a troca <NNN> tirou de problems/
manifests/<m>_generation_report.json        # LlmGenerationReport (§3.6), versionado
manifests/<m>_generation_report.piloto<N>.json  # relatório de um piloto (FR-023a), versionado
manifests/<m>_suites.manifest.json          # LlmSuitesManifest (§3.7), versionado
data/<m>_suites.zip                         # só da execução final, versionado; raiz suites/<m>/
```

Nada em `data/suites/` é versionado, assim como no SLM. As pastas são criadas com
`store.make_private_dir`.

## 2. Enumerações

| Nome | Valores |
|---|---|
| `LlmModel` | `gpt`, `gemini` (a chave da CLI e da pasta) |
| `Scenario` | a do SLM (`black_box`, `white_box`, `hybrid`) |
| `FormatFailure` | `empty_response`, `not_json`, `schema_violation`, `truncated`, `refusal`, `safety_block`, `no_usable_test` (FR-015; R6) |
| `SuiteStatus` | a do SLM. Nos LLMs só aparecem `accepted_predicted` e `discarded_manual` (A6, FR-016) |
| `LlmTemplateKind` | `Literal["llm"]` (o texto-base `llm_prompt.txt`). O enum `AttemptKind` do SLM (`solution`, `prediction`) **não muda**: nem o `GenerationRecord` nem o `TemplateChange` do SLM passam a aceitar `llm` |

## 3. Schemas

### 3.1 `LlmRunConfig` — `run.json` (um por modelo e por execução)

| Campo | Tipo | Comparado no `--resume` |
|---|---|---|
| `schema_version` | `1` | sim |
| `model_key` | `LlmModel` | sim |
| `model_requested` | texto (`gpt-5.4-mini-2026-03-17` ou `gemini-3.8-flash`) | sim |
| `endpoint` | texto (URL do método) | sim |
| `request_parameters` | objeto: todos os campos do corpo de R3, menos o prompt (esforço de raciocínio, `store`, teto de saída, formato) | sim, campo a campo |
| `response_schema` | o schema de R4, inteiro | sim |
| `template_sha256` | SHA-256 de `llm_prompt.txt` | sim (troca só por `change-template`) |
| `max_attempts` | `3` | sim |
| `dataset_manifest_sha256` | SHA-256 de `manifests/dataset.manifest.json` | sim |
| `price_table` | lista de `PriceRow` (§3.8) | **não**; a mudança fica registrada no relatório |
| `created_at` | data ISO | não |

`request_parameters` nunca traz `temperature`, `top_p`, `top_k`, `seed`, `instructions`,
`systemInstruction`, `safetySettings` nem `previous_response_id`: o validador recusa esses campos
(FR-002, FR-003, A11, A13). A concorrência, o teto de gasto, as esperas e o tempo de leitura não
estão aqui (R7, R8).

### 3.2 `LlmAttempt` — `attempt_<n>.json`

| Campo | Tipo / regra |
|---|---|
| `schema_version` | `1` |
| `problem_id`, `scenario`, `attempt` | identificação; `attempt` de 1 a 3 |
| `model_requested` | igual ao do `run.json` |
| `model_returned` | texto devolvido pela API (`model`; `modelVersion`) |
| `response_id` | texto (`id`; `responseId`) |
| `prompt_sha256`, `template_sha256` | hashes do prompt montado e do texto-base |
| `request_parameters` | igual ao do `run.json` (conferido pelo estado, §4) |
| `requested_at` | data ISO do envio |
| `latency_s` | segundos entre o envio e o fim da resposta, sem esperas de infraestrutura |
| `http_status` | 200 |
| `raw_body` | o corpo HTTP inteiro, como texto (FR-010) |
| `finish` | objeto: `status` (OpenAI `status`; Gemini `finishReason`), `reason` (`incomplete_details.reason` ou `promptFeedback.blockReason`, ou nulo) e `safety_categories` (lista, só no Gemini) |
| `usage` | `input_tokens`, `cached_input_tokens`, `output_tokens` (o que é cobrado como saída, R9) e `reasoning_tokens`; todos inteiros maiores ou iguais a 0 |
| `cost_usd` | número; o custo pela linha de preço válida em `requested_at` |
| `price_row` | a `PriceRow` usada |
| `parse` | `LlmParsed` ou `LlmFormatFailure` (abaixo) |

`LlmParsed` tem `ok: true`, além de:
- `edge_cases_analysis` (texto não vazio);
- `tests`, uma lista de `TestCase` com pelo menos 1 item, cada `input` e `output` terminando em
  exatamente um `\n`;
- os contadores `empty_tests`, `abbreviated_tests`, `markdown_fences_removed`,
  `duplicate_inputs`, `conflicting_outputs` e `example_copies`.

`LlmFormatFailure` tem `ok: false`, `failure` (um valor de `FormatFailure`) e `detail` (texto).

Regra: uma tentativa só é gravada se tiver *tokens* de raciocínio maiores que 0. Uma resposta sem
eles vira `BarredResponse` (§3.3) e nunca vira tentativa.

### 3.3 `BarredResponse` — `barred/<id>/<cenário>/<n>.json`

Tem os mesmos campos de `LlmAttempt`, exceto `attempt` e `parse`, e acrescenta `barred_at` e
`reason: "no_reasoning_tokens"`. O custo entra no gasto da invocação e no relatório
(`barred_cost_usd`), nunca nas métricas.

### 3.4 `LlmSuite` — `suite.json` (R1)

O `suite.json` tem as mesmas chaves de topo do `SlmSuite`, com os valores do LLM:

| Campo | Valor nos LLMs |
|---|---|
| `schema_version` | `2` |
| `problem_id`, `scenario` | identificação |
| `model` | `model_requested` do `run.json` |
| `model_digest` | `model_returned` da tentativa aceita; `null` em `discarded_manual` |
| `status` | `accepted_predicted` ou `discarded_manual` |
| `accepted_phase` | sempre `null` |
| `attempts` | lista de 1 a 3 `LlmAttemptSummary` (`attempt`, `failure` ou nulo, `detail`, `model_returned`, `cost_usd`), numerada de 1 sem buraco |
| `accepted_attempt` | o número da última tentativa; `null` em `discarded_manual` |
| `tests` | os `tests` de `LlmParsed` da tentativa aceita |
| `suite_size` | `len(tests)` |
| `discarded_inputs` | sempre `[]` |
| `duplicate_inputs` | o contador da tentativa aceita |
| `manual_close` | `{reason, closed_at}`, só em `discarded_manual` |

Validações:
- **`accepted_predicted`:** só a última tentativa tem `failure` nulo, e `tests` não é vazio.
- **`discarded_manual`:** são exatamente 3 tentativas, todas com falha; `tests` é vazio e
  `manual_close` está presente.

### 3.5 `SuiteView` — leitor comum dos 3 modelos (R1)

`ai_clients/schemas/suite_view.py`, com `extra="ignore"`. Campos: `schema_version` (`2`),
`problem_id`, `scenario`, `model`, `status` (`SuiteStatus`), `tests` (lista de `TestCase`) e
`suite_size`. Validações: `suite_size == len(tests)`, e `tests` é vazio se e só se o status é
`discarded_manual`.

`read_suite_view(path) -> SuiteView` lê qualquer `suite.json` dos 3 modelos sem saber de qual
modelo ele é (SC-007). O módulo de avaliação usa só isso.

### 3.6 `LlmGenerationReport` — `manifests/<m>_generation_report.json`

O relatório tem `schema_version: 1` e nenhuma data própria: a mesma árvore dá os mesmos bytes,
como no SLM. Chaves de topo:

| Chave | Conteúdo |
|---|---|
| `model_key`, `model_requested`, `request_parameters`, `template_sha256`, `dataset_manifest_sha256` | identificação da execução |
| `models_returned` | cada identificador devolvido → número de respostas (tentativas e barradas) |
| `combinations` | por cenário e no total: `total`, `accepted_predicted`, `discarded_manual`, `awaiting_manual`, `pending` |
| `attempts_by_number` e `failures` | chamadas por número de tentativa (1, 2, 3); falhas por razão (`FormatFailure`) × tentativa |
| `safety_blocks_by_category` | só no Gemini (A13) |
| `truncated` | respostas cortadas pelo teto, por cenário |
| `test_discards` | `empty_tests`, `abbreviated_tests`, `markdown_fences_removed`, `duplicate_inputs`, `conflicting_outputs`, `example_copies`, por cenário |
| `suite_size` | `count`, `min`, `p25`, `median`, `p75`, `max`, `histogram`, por cenário e no total, calculados com `report.size_stats` |
| `tokens` | soma de `input`, `cached_input`, `output` e `reasoning`, por cenário e no total |
| `cost_usd` | `by_group` (das tentativas, por cenário e no total), `barred_cost_usd`, `total` e `price_rows_used` |
| `latency_s` | `calls`, `total_s`, `mean_s`, `median_s`, `max_s` |
| `barred` | número de respostas barradas e suas combinações |
| `template_changes` | como no SLM |

Regra: `cost_usd.total` é igual à soma de `cost_usd` de todas as tentativas mais
`barred_cost_usd` (SC-003).

### 3.7 `LlmSuitesManifest` — `manifests/<m>_suites.manifest.json`

Tem a forma do manifesto do SLM, com `schema_version` 1, `model_key`, `suites_zip` (o `FileHash`
do zip; o nome não leva o modelo, que está em `model_key`) e `files`, em ordem de caminho. Os caminhos aceitos dentro do zip são `suites/<m>/run.json`,
`suites/<m>/problems/<id>/<cenário>/(attempt_[1-3].json|suite.json|manual_close.json)`,
`suites/<m>/barred/<id>/<cenário>/<n>.json`, `suites/<m>/template_changes/<NNN>.json` e
`suites/<m>/superseded/<NNN>/<id>/<cenário>/…`.

### 3.8 `PriceRow`

`model_key`, `valid_from` (data), `input_per_mtok`, `cached_input_per_mtok`, `output_per_mtok`
(US$), `source` (URL) e `accessed_on` (data). As linhas iniciais estão em research R9.

### 3.9 `LlmTemplateChange` — `template_changes/<NNN>.json`

Tem os mesmos campos do `TemplateChange` do SLM (`number`, `from_sha256`, `to_sha256`,
`changed_at`, `reason`, `superseded`), com `schema_version: 1` e `template: Literal["llm"]`. O
`TemplateChange` do SLM e o seu `AttemptKind` não mudam.

## 4. Estados de uma combinação

O estado é derivado só dos arquivos da pasta e do `run.json`. Nada é guardado à parte.

| Estado | Condição | O que o `generate` faz |
|---|---|---|
| `pending(n)` | `n − 1` tentativas, todas com falha de formato, `n ≤ 3`, sem `suite.json` | chama, grava `attempt_<n>.json`; se interpretou, grava `suite.json` |
| `finalizable` | a última tentativa interpretou e não há `suite.json` | grava `suite.json` sem chamar |
| `done` | há `suite.json` igual ao que os arquivos dão | nada |
| `awaiting_manual` | 3 tentativas com falha e nenhum `manual_close.json` | nada; linha `manual:` e código 4 |
| `closable → done` | `manual_close.json` presente e sem `suite.json` | grava `suite.json` (`discarded_manual`) |
| `damaged` | qualquer divergência (abaixo) | não toca; linha `damaged:` e código 1 |

A combinação é **danificada** em qualquer um destes casos:
- falta um arquivo de tentativa, ou há um buraco na numeração;
- há mais de 3 tentativas, ou uma tentativa depois de uma aceita;
- um arquivo fala de outra combinação, ou o JSON é inválido ou viola o schema;
- `model_requested`, `request_parameters` ou `template_sha256` divergem do `run.json` corrente
  (`run.json` mais as trocas de template);
- o `suite.json` é diferente, byte a byte, do que os arquivos dão;
- há `manual_close.json` sem 3 falhas;
- há um arquivo estranho na pasta.

Os temporários de escrita atômica (`.<nome>.<sufixo>.tmp`) são ignorados.

Desde 2026-10-20 (emenda de FR-018a), cada resposta em `barred/` guarda também a interpretação
(`parse`, ausente nas gravadas antes). A combinação continua `pending(n)` até 3 respostas
barradas; com 3 ou mais, fica `finalizable` se alguma for legível (a suíte é `accepted_barred`,
com os testes da última legível e `barred_close: {responses, accepted}`), `awaiting_manual` se
nenhuma for (o `close` dá `discarded_manual` com `barred_close.accepted = null`), e `pending(n)`
se todas forem anteriores à emenda (sem interpretação). Uma tentativa aceita ou 3 tentativas com
falha de formato decidem antes. O campo `barred_close` só aparece nessas suítes.

## 5. Travas e concorrência (R8)

As travas são as do SLM, sobre a pasta do modelo:
- `.lock` é compartilhado por `generate --resume`;
- `.lock` é exclusivo para `generate` sem `--resume`, `close`, `change-template` e `package`;
- `.locks/<id>__<cenário>.lock` é exclusivo por combinação, tomado pela *thread* que a trata e
  mantido entre as tentativas dela.

Uma combinação em uso por outro processo é pulada (`skipped`). O `report` e o `verify` só leem.
As pastas `data/suites/gpt` e `data/suites/gemini` são independentes, então os dois modelos rodam
juntos.
