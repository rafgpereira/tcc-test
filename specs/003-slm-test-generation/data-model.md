# Data Model: Geração de Suítes de Teste pelo SLM

**Feature**: `003-slm-test-generation` | **Date**: 2026-09-30 | **Plan**: [plan.md](./plan.md)

Todos os schemas são Pydantic em `src/ai_clients/schemas/`, herdam `dataset.schemas.common.Schema`
(`extra="forbid"`) e têm `schema_version: Literal[1]` (Princípio IV). Todo JSON é gravado por
`dataset.persistence.store.atomic_write_json` (chaves ordenadas, indentação 2, `\n` final). O formato
em disco está em [contracts/file-formats.md](./contracts/file-formats.md).

## 1. Entradas (reaproveitadas, sem mudança)

| Entidade | Origem | Campos usados |
|---|---|---|
| `Metadata` | `dataset.schemas.metadata`, `metadata.json` | `problem_id`, `time_limit_seconds`, `memory_limit_bytes` |
| `Testes` / `TestCase` | `dataset.schemas.testes`, `testes.json` | `public_tests` (todos, para validar; o **primeiro**, para o few-shot) |
| enunciado | `enunciado.md` (texto) | inteiro, cenários `black_box` e `hybrid` |
| código de referência | `AC_ref.cpp` (texto) | inteiro, cenários `white_box` e `hybrid` — **só no prompt**, nunca executado nem usado para validar |

`ProblemInput` (dataclass imutável em `ai_clients/problem.py`) agrupa esses quatro itens de um
problema; é a composição sinalizada em research R0 (não um leitor novo do `dataset`).

## 2. Enumerações

- `Scenario`: `black_box` (só enunciado) · `white_box` (só `AC_ref.cpp`) · `hybrid` (os dois). Ordem
  canônica de processamento: esta.
- `AttemptFailure` (as 4 razões de FR-018, as únicas que consomem orçamento):
  `repetition` (desde 2026-10-04) · `unparseable_response` · `public_test_failed` ·
  `all_inputs_failed`.
- `InputDiscard` (FR-019): `timeout` (veredito `TLE`) · `runtime_error` (veredito `RE` ou `MLE`,
  guardado em `verdict`) · `non_utf8_output`.
- `SuiteStatus` (desde 2026-10-06, research R19): `accepted` · `accepted_fallback` (reserva,
  FR-022a) · `accepted_low_confidence` (FR-022b) · `accepted_predicted` (FR-022c) ·
  `discarded_manual` (FR-022d, só por decisão dos autores). Até 2026-10-06 havia `discarded`.
- `AttemptKind`: `solution` (tentativas 1 a 20, template principal) · `prediction` (21 a 23,
  template de predição). Derivado do número da tentativa, nunca gravado à parte nos arquivos de
  tentativa.

## 3. Entidades persistidas

### 3.1 `RunConfig` — `data/suites/slm/run.json` (1 por execução)

Identidade da execução; criado pelo primeiro `generate` (sem `--resume`) e comparado em todo
`--resume` (research R8): **todos os campos abaixo exceto `created_at`** entram na comparação.
Imutável. O *timeout* de leitura e o teto de repetições de infraestrutura (research R9, R12) não
fazem parte dele — não mudam o conteúdo de nenhuma resposta.

| Campo | Tipo | Regra |
|---|---|---|
| `model` | str | `"qwen2.5-coder:7b"` (constante) |
| `model_digest` | str | `digest` de `/api/tags`; mudou → recusa |
| `model_quantization` | str | `details.quantization_level` de `/api/tags` |
| `ollama_version` | str | `/api/version` |
| `options` | objeto | `temperature`, `top_p`, `top_k`, `repeat_penalty`, `num_ctx`, `num_predict` |
| `seed_base` | int | `42` |
| `strict_attempts` | int | `8` (desde 2026-10-05; tentativas antes de valer a reserva, FR-022a) |
| `solution_attempts` | int | `20` (desde 2026-10-06; tentativas com solução Python, FR-022a/b) |
| `predict_attempts` | int | `3` (desde 2026-10-06; tentativas por predição, FR-022c) |
| `max_attempts` | int | `23` = `solution_attempts + predict_attempts` (validado); era `6` até 2026-10-05 e `12` até 2026-10-06 |
| `prompt_template_sha256` | str (hex 64) | do `slm_prompt.txt` usado |
| `predict_template_sha256` | str (hex 64) | do `slm_predict_prompt.txt` usado (desde 2026-10-06) |
| `dataset_manifest_sha256` | str (hex 64) | liga a execução ao dataset versionado |
| `py_time_factor`, `py_memory_factor` | int | `10`, `4` (research R7) |
| `created_at` | str ISO-8601 UTC | informativo, **fora** da comparação do `--resume` |

### 3.2 `GenerationRecord` — `problems/<id>/<scenario>/attempt_<n>.generation.json`

Uma tentativa na fase de geração (FR-013a, FR-014, FR-024, FR-025). Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id`, `scenario`, `attempt` | str, `Scenario`, int 1–23 | `attempt` sem buraco a partir de 1; 1–20 `solution`, 21–23 `prediction` |
| `seed` | int | `== seed_base + attempt` (validado) |
| `model_digest` | str | `digest` do modelo que respondeu (FR-003); `==` `run.json.model_digest`, senão a combinação é dano (§4) |
| `prompt_sha256` | str | do prompt exato enviado (o texto se recompõe do template + dataset) |
| `raw_response` | str | `message.content` **integral**, sem nenhuma alteração; `""` quando há `model_failure` |
| `ollama` | objeto ou `null` | `model`, `created_at`, `done_reason`, `prompt_eval_count`, `eval_count`, `total_duration_ns`, `load_duration_ns`, `prompt_eval_duration_ns`, `eval_duration_ns`; `null` só quando há `model_failure` |
| `hardware_label` | str | de `OLLAMA_HARDWARE_LABEL` no momento da chamada |
| `requested_at` | str ISO-8601 UTC | informativo |
| `parse` | `ParseResult` | ver abaixo |
| `model_failure` | objeto ou `null` (padrão) | desde 2026-10-04: `{reason: "repetition", detail}` quando o Ollama interrompeu a geração com `token repeat limit reached` (HTTP 500); então `parse = {ok: false, error: "repetition"}` e a tentativa é a falha `repetition` |

`ParseResult` (desde 2026-10-06, três formatos; o schema confere que tentativas 1–20 só têm os
dois primeiros e 21–23 só `PredictionParse` ou `ok: false`):

- `ok: true` → `edge_cases_analysis: str`, `inputs: list[str]` (≥ 1, cada uma não vazia e
  terminada em um único `\n`), `reference_py: str` (não vazio), `extraneous_chars: int ≥ 0`,
  `duplicate_inputs: int ≥ 0`, `empty_inputs: int ≥ 0` (`<input>` vazios descartados, fora de
  `inputs`; padrão 0) e `markdown_fence_removed: bool` (a cerca que envolvia o código inteiro foi
  removida; padrão `false`) — os dois desde 2026-10-04 (research R13).
- `ok: false` → `error: str` (código do parser, ex. `missing_block:reference_py`,
  `duplicated_block:inputs`, `wrong_order`, `only_empty_inputs`, `text_between_inputs`; até
  2026-10-04 também `empty_input`; nas tentativas por predição, também `missing_block:tests`,
  `no_tests`, `text_between_tests`, `malformed_test`, `only_empty_tests`, research R19 item 4). A
  tentativa **é** a falha `unparseable_response` (ou `repetition`, quando há `model_failure`).
- `PredictionParse` (`ok: true`, só tentativas 21–23) → `edge_cases_analysis: str`, `tests:
  list[TestCase]` (≥ 1; `input` e `output` não vazios, cada um terminado em um único `\n`),
  `extraneous_chars: int ≥ 0`, `duplicate_inputs: int ≥ 0`, `empty_tests: int ≥ 0` (`<test>` com
  entrada ou saída vazia, descartados sozinhos).

### 3.3 `ExecutionRecord` — `problems/<id>/<scenario>/attempt_<n>.execution.json`

Só existe para tentativas 1–20 com `parse.ok = true` (FR-013b); nunca para uma tentativa por
predição. Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id`, `scenario`, `attempt` | | iguais aos da geração correspondente |
| `limits` | objeto | `time_limit_seconds`, `memory_limit_bytes` efetivos (problema × fatores) e os do problema, para auditoria |
| `interpreter` | str | caminho e versão do CPython usado |
| `public_tests` | objeto | `total`, `passed`, `failed_index: int \| null`, `failed_verdict: Verdict \| null`; do teste que reprovou (nulos sem falha e nos registros gravados antes de 2026-10-05, R14): `failed_output_head: str \| null` (primeiros 2.048 bytes do `stdout`, sem normalização), `failed_stderr_tail: str \| null`, `failed_cpu_time_s: float \| null`, `failed_peak_rss_bytes: int \| null` |
| `inputs` | list[`InputOutcome`] | um por entrada da geração, na mesma ordem |
| `outcome` | `accepted` \| `AttemptFailure` | `public_test_failed` se `failed_index` não nulo; senão `all_inputs_failed` se nenhuma entrada sobreviveu; senão `accepted` |

`InputOutcome`: `index: int` (0-based na lista da geração), `kept: bool`, `output: str | null`
(só se `kept`), `discard: InputDiscard | null`, `verdict: Verdict | null`, `cpu_time_s: float`,
`peak_rss_bytes: int`, `stderr_tail: str` (só nos descartes, para diagnóstico).

Regra: os testes públicos param no primeiro não-AC (curto-circuito), mas as entradas geradas rodam
**sempre**, qualquer que seja o veredito desse teste (desde 2026-10-06, research R19 item 2; até
2026-10-05 nenhuma rodava depois de uma reprovação, e até 2026-10-06 só depois de WA): `inputs` tem
um item por entrada da geração.

### 3.4 `SlmSuite` — `problems/<id>/<scenario>/suite.json` (estado terminal)

Função pura dos arquivos de tentativa (research R8). Formato "unificado" pedido pelo autor.

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id`, `scenario` | | |
| `model`, `model_digest` | str | copiados do `run.json` (a suíte se identifica sozinha) |
| `status` | `SuiteStatus` | |
| `attempts` | list[`AttemptSummary`] | todas, em ordem: `attempt`, `seed`, `kind: AttemptKind`, `hardware_label`, `failure: AttemptFailure \| null`, `detail: str` (código do parser, índice/veredito do teste público, contagem de descartes e de entradas mantidas), `fallback_eligible: bool` (FR-022a), `low_confidence_eligible: bool` (FR-022b; desde 2026-10-06); os dois `false` por padrão |
| `accepted_attempt` | int \| null | não nulo ⇔ `status` ≠ `discarded_manual`; numa reserva, a tentativa escolhida (não necessariamente a última); numa de baixa confiança, a primeira elegível |
| `tests` | list[`TestCase`] | **`dataset.schemas.testes.TestCase` reaproveitado** (`input`, `output`); `output` é o `expected_output` da spec, obtido por execução real (SC-002) — exceto em `accepted_predicted`, em que é a saída escrita pelo modelo; vazio ⇔ `discarded_manual` |
| `suite_size` | int | `== len(tests)`; `≥ 1` em todo status `accepted*` (nunca suíte de tamanho zero, FR-018c) |
| `discarded_inputs` | list | `{index, discard, verdict}` da tentativa escolhida (FR-019); vazio em `accepted_predicted` e `discarded_manual` |
| `duplicate_inputs` | int | da tentativa escolhida |
| `manual_close` | objeto \| null | desde 2026-10-06: `{reason, closed_at}` copiado de `manual_close.json`; não nulo ⇔ `discarded_manual` |

Validações (desde 2026-10-06; `S` = 8 estritas, `P` = 20 com solução, `M` = 23):

- `accepted` ⇒ a última tentativa tem `failure = null`, é `solution` e é a `accepted_attempt`; todas
  as anteriores têm falha.
- `accepted_fallback` ⇒ todas falharam e a `accepted_attempt` tem `fallback_eligible`; com exatamente
  `S` tentativas, qualquer uma delas (a melhor, conferido pelo `store`); com `S+1` a `P`, só a
  última.
- `accepted_low_confidence` ⇒ exatamente `P` tentativas, todas com falha, nenhuma com
  `fallback_eligible`, e a `accepted_attempt` é a **primeira** com `low_confidence_eligible`.
- `accepted_predicted` ⇒ de `P+1` a `M` tentativas; nenhuma das `P` primeiras com
  `fallback_eligible` ou `low_confidence_eligible`; a última é `prediction`, sem falha, e é a
  `accepted_attempt`; as anteriores por predição falharam (`unparseable_response` ou `repetition`).
- `discarded_manual` ⇒ exatamente `M` tentativas, todas com falha, nenhuma elegível, e
  `manual_close` presente.
- Sempre: `kind` = `solution` ⇔ `attempt ≤ P`; `fallback_eligible` e `low_confidence_eligible` só
  numa tentativa `solution` com `public_test_failed`; depois da `S`-ésima, nenhuma tentativa
  anterior à última pode ser reserva.

### 3.4a `ManualClose` — `problems/<id>/<scenario>/manual_close.json` (desde 2026-10-06)

Decisão dos autores sobre uma combinação em `awaiting_manual` (FR-022d), gravada pelo comando
`close` (research R19 item 8). Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id`, `scenario` | | os da pasta |
| `reason` | str | não vazio (depois de tirar espaços das pontas) |
| `closed_at` | str ISO-8601 UTC | quando o comando rodou |

### 3.5 `SlmGenerationReport` — `manifests/slm_generation_report.json`

Campos em research R10 / [contracts/file-formats.md](./contracts/file-formats.md#5-relatório). Somas
de controle validadas no schema: os cinco status de `SuiteStatus` + `awaiting_manual` +
`pending_generation` + `pending_execution` `== total` em cada cenário e no total (desde 2026-10-06;
antes `accepted + accepted_fallback + discarded + …`), com `status_rate` por status no lugar de
`discard_rate` e `fallback_rate`; os cenários somam o total, o funil por razão (tentativas 1 a 23)
soma `attempts.failed`, e as chamadas por etiqueta de hardware somam `attempts.total`.

### 3.6 `SlmSuitesManifest` — `manifests/slm_suites.manifest.json`

Mesma forma do manifesto dos mutantes, em `ai_clients/schemas/manifest.py`: `slm_suites_zip:
{path, size, sha256}` (com `path` sempre `data/slm_suites.zip`, como o `mutants_zip` dos mutantes)
e `files: [{path, size, sha256}]`, um por arquivo dentro do zip, `path` como dentro do zip
(`suites/slm/...`), ordenado. *(2026-10-01: a forma `zip: {path, sha256, bytes}` escrita aqui no
plano foi trocada pela do manifesto dos mutantes, que é o que "mesma forma" pedia.)*

## 4. Máquina de estados de uma combinação

Derivada só dos arquivos presentes (sem campo de estado gravado), com `n` = maior tentativa
existente:

Desde 2026-10-06 (research R19); `S` = 8, `P` = 20, `M` = 23. Uma linha vale quando nenhuma
anterior vale:

| Arquivos presentes | Estado | Próximo passo (comando) |
|---|---|---|
| `suite.json` | **terminal** (um dos 5 status) | nenhum — nunca reprocessado |
| nenhum | `pending_generation(1)` | `generate` chama com seed 43 |
| `attempt_n.generation` (`n ≤ P`) com `parse.ok = true`, sem `attempt_n.execution` | `pending_execution(n)` | `execute` |
| `attempt_n.execution` com `outcome = accepted` | `finalizable` | quem encontrar grava `suite.json(accepted)` |
| `n = S`, a última falhou e alguma das `S` pode ser reserva | `finalizable` | `suite.json(accepted_fallback)` da melhor |
| `S < n ≤ P`, a última falhou e pode ser reserva | `finalizable` | `suite.json(accepted_fallback)` da última |
| `n < P`, a última falhou (qualquer razão) | `pending_generation(n+1)` | `generate` (na mesma execução se não interpretou, R8; senão `generate --resume`) |
| `n = P`, a última falhou, alguma das `P` é `low_confidence_eligible` | `finalizable` | `suite.json(accepted_low_confidence)` da primeira |
| `n = P`, a última falhou, nenhuma elegível | `pending_generation(P+1)` | `generate` (predição, seed 63) |
| `attempt_n.generation` (`n > P`) com `parse.ok = true` | `finalizable` | `suite.json(accepted_predicted)`, gravado pelo próprio `generate` |
| `P < n < M`, a última não interpretou | `pending_generation(n+1)` | `generate` (na mesma execução) |
| `n = M`, a última não interpretou, sem `manual_close.json` | `awaiting_manual` | os autores rodam `close` (FR-022d); `generate`/`execute` saem com código 4 |
| `n = M`, a última não interpretou, com `manual_close.json` | `finalizable` | `suite.json(discarded_manual)` |

Inconsistências (ex.: `attempt_3` sem `attempt_2`, execução sem geração, `seed` que não bate,
tentativa além da 23ª, `attempt_n.execution` com `n > P`, `PredictionParse` numa tentativa `≤ P` ou
`ParsedResponse` numa `> P`, tentativa além da `S`-ésima com uma reserva possível antes dela,
tentativa além da `P`-ésima com uma reserva ou baixa confiança possível, `manual_close.json` fora
do estado `awaiting_manual`, `model_digest` de tentativa diferente do `run.json`, `suite.json` que
não é a função dos arquivos) são **dano**: o comando não conserta, lista e sai com código 1, e
`cli check` aponta o mesmo.
