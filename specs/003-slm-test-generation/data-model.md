# Data Model: Geração de Suítes de Teste pelo SLM

**Feature**: `003-slm-test-generation` | **Date**: 2026-09-30 (revisto em 2026-10-06 para a política
de 5 fases, research R21/R22) | **Plan**: [plan.md](./plan.md)

Todos os schemas são Pydantic em `src/ai_clients/schemas/`, herdam `dataset.schemas.common.Schema`
(`extra="forbid"`) e têm **`schema_version: Literal[2]`** desde 2026-10-06 (R22, item 3; era 1 —
`ai_clients.schemas.common.SchemaVersion`; o `dataset` continua em 1). Todo JSON é gravado por
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

## 2. Política de tentativas e enumerações

**`config.ATTEMPT_POLICY`** (R22, item 1): a única fonte de fase, seed, temperatura e template de
cada tentativa, escrita por extenso no código e validada ao importar (números 1 a 15 sem buraco,
nenhum par (seed, temperatura) repetido, temperatura > 0, fases nas faixas abaixo).

| Tentativa | `phase` | `seed` | `temperature` | `template` |
|---|---|---|---|---|
| 1 | 1 | 42 | 0.7 | `solution` |
| 2 | 1 | 43 | 0.7 | `solution` |
| 3 | 1 | 44 | 0.7 | `solution` |
| 4 | 1 | 45 | 0.7 | `solution` |
| 5 | 1 | 46 | 0.7 | `solution` |
| 6 | 1 | 47 | 0.7 | `solution` |
| 7 | 2 | 48 | 0.7 | `solution` |
| 8 | 2 | 48 | 0.6 | `solution` |
| 9 | 2 | 48 | 0.5 | `solution` |
| 10 | 2 | 48 | 0.4 | `solution` |
| 11 | 2 | 48 | 0.3 | `solution` |
| 12 | 2 | 48 | 0.2 | `solution` |
| 13 | 4 | 49 | 0.7 | `prediction` |
| 14 | 4 | 50 | 0.7 | `prediction` |
| 15 | 4 | 51 | 0.7 | `prediction` |

`solution` = `src/prompt_templates/slm_prompt.txt` (entradas + solução Python); `prediction` =
`src/prompt_templates/slm_predict_prompt.txt` (entradas + saídas). A fase 3 (reserva) e a fase 5
(tratamento manual) não fazem chamada. Derivados: `SOLUTION_ATTEMPTS = 12`, `MAX_ATTEMPTS = 15`.

- `Scenario`: `black_box` (só enunciado) · `white_box` (só `AC_ref.cpp`) · `hybrid` (os dois). Ordem
  canônica de processamento: esta.
- `AttemptFailure` (as 4 razões de FR-018, as únicas que consomem orçamento):
  `repetition` · `unparseable_response` · `public_test_failed` · `all_inputs_failed`.
- `InputDiscard` (FR-019): `timeout` (veredito `TLE`) · `runtime_error` (veredito `RE` ou `MLE`,
  guardado em `verdict`) · `non_utf8_output`.
- `SuiteStatus` (desde 2026-10-06, R21): `accepted` · `accepted_fallback` (fase 3, FR-022a) ·
  `accepted_predicted` (fase 4, FR-022c) · `discarded_manual` (fase 5, FR-022d, só por decisão dos
  autores). `accepted_low_confidence` existiu de R19 a R21; `discarded`, até R18.
- `AttemptTemplate`: `solution` · `prediction` (coluna `template` da tabela).

## 3. Entidades persistidas

### 3.1 `RunConfig` — `data/suites/slm/run.json` (1 por execução)

Identidade da execução; criado pelo primeiro `generate` (sem `--resume`) e comparado em todo
`--resume` (research R8): **todos os campos abaixo exceto `created_at`** entram na comparação, e
`attempt_policy` linha a linha. Imutável. O *timeout* de leitura e o teto de repetições de
infraestrutura (research R9, R12) não fazem parte dele. Um `run.json` que não valida como
`schema_version: 2` (os pilotos 1 a 5) é recusado por todo comando com código 2 (R22, item 4).

| Campo | Tipo | Regra |
|---|---|---|
| `model` | str | `config.MODEL` (`"qwen2.5-coder:14b"`) ou `OLLAMA_MODEL` |
| `model_digest` | str | `digest` de `/api/tags`; mudou → recusa |
| `model_quantization` | str | `details.quantization_level` de `/api/tags` |
| `ollama_version` | str | `/api/version` |
| `options` | objeto | `top_p`, `top_k`, `repeat_penalty`, `num_ctx`, `num_predict` (a temperatura saiu daqui: é por tentativa) |
| `attempt_policy` | list[`AttemptSpec`] | a tabela da §2 inteira: `{attempt, phase, seed, temperature, template}` × 15 (substitui `seed_base`, `strict_attempts`, `solution_attempts`, `predict_attempts`, `max_attempts`) |
| `prompt_template_sha256` | str (hex 64) | do `slm_prompt.txt` usado |
| `predict_template_sha256` | str (hex 64) | do `slm_predict_prompt.txt` usado |
| `dataset_manifest_sha256` | str (hex 64) | liga a execução ao dataset versionado |
| `py_time_factor`, `py_memory_factor` | int | `10`, `4` (research R7) |
| `created_at` | str ISO-8601 UTC | informativo, **fora** da comparação do `--resume` |

### 3.2 `GenerationRecord` — `problems/<id>/<scenario>/attempt_<n>.generation.json`

Uma tentativa na fase de geração (FR-013a, FR-014, FR-024, FR-025). Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id`, `scenario`, `attempt` | str, `Scenario`, int 1–15 | `attempt` sem buraco a partir de 1 |
| `phase`, `seed`, `temperature`, `template` | int, int, float, `AttemptTemplate` | **novos em 2026-10-06**: a linha `attempt` do `attempt_policy` do `run.json`; o `store` confere os quatro (divergência é dano) |
| `model_digest` | str | `digest` do modelo que respondeu (FR-003); `==` `run.json.model_digest`, senão dano |
| `prompt_sha256` | str | do prompt exato enviado (o texto se recompõe do template + dataset) |
| `template_sha256` | str ou ausente | **novo em 2026-10-07 (R27)**: hash do template usado; `==` o template corrente do mesmo tipo (`run.json` + trocas), senão dano; ausente só nas tentativas gravadas antes, e então dano se aquele template já foi trocado |
| `raw_response` | str | `message.content` **integral**; `""` quando há `model_failure` |
| `ollama` | objeto ou `null` | `model`, `created_at`, `done_reason`, `prompt_eval_count`, `eval_count`, `total_duration_ns`, `load_duration_ns`, `prompt_eval_duration_ns`, `eval_duration_ns`; `null` só com `model_failure` |
| `hardware_label` | str | de `OLLAMA_HARDWARE_LABEL` no momento da chamada |
| `requested_at` | str ISO-8601 UTC | informativo |
| `parse` | `ParseResult` | ver abaixo; o schema confere que tentativas `solution` só têm `ParsedResponse` ou `ok: false`, e `prediction` só `PredictionParse` ou `ok: false` |
| `model_failure` | objeto ou `null` | `{reason: "repetition", detail}` (`token repeat limit reached`); então `parse = {ok: false, error: "repetition"}` |

`ParseResult`:

- `ParsedResponse` (`ok: true`, tentativas `solution`) → `edge_cases_analysis`, `inputs: list[str]`
  (≥ 1, cada uma não vazia e terminada em um único `\n`), `reference_py` (não vazio),
  `extraneous_chars`, `duplicate_inputs`, `empty_inputs`, `markdown_fence_removed: bool`.
- `PredictionParse` (`ok: true`, tentativas `prediction`) → `edge_cases_analysis`, `tests:
  list[TestCase]` (≥ 1; `input` e `output` não vazios, cada um terminado em um único `\n`),
  `extraneous_chars`, `duplicate_inputs`, `empty_tests` (testes com entrada ou saída vazia,
  descartados sozinhos) e **`markdown_fences_removed: int`** (novo: cercas que envolviam um
  `<input>` ou `<output>` inteiro, removidas; R22, item 7) e `abbreviated_tests` (desde
  2026-10-07, R27: testes com entrada ou saída abreviada, descartados sozinhos; ausente = 0).
- `UnparsedResponse` (`ok: false`) → `error` (código do parser: `missing_block:<tag>`,
  `duplicated_block:<tag>`, `wrong_order`, `only_empty_inputs`, `text_between_inputs`,
  `missing_block:tests`, `no_tests`, `text_between_tests`, `malformed_test`, `nested_test`,
  `only_empty_tests`, `only_abbreviated_tests`, `only_empty_or_abbreviated_tests`, …). A tentativa **é** a falha `unparseable_response` (ou `repetition`).

### 3.3 `ExecutionRecord` — `problems/<id>/<scenario>/attempt_<n>.execution.json`

Só existe para tentativas `solution` (1 a 12) com `parse.ok = true` (FR-013b). Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id`, `scenario`, `attempt` | | iguais aos da geração correspondente |
| `limits` | objeto | `time_limit_seconds`, `memory_limit_bytes` efetivos (problema × fatores) e os do problema |
| `interpreter` | str | caminho e versão do CPython usado |
| `public_tests` | objeto | `total`, `passed`, `failed_index`, `failed_verdict` e, do teste que reprovou, `failed_output_head`, `failed_stderr_tail`, `failed_cpu_time_s`, `failed_peak_rss_bytes` |
| `inputs` | list[`InputOutcome`] | um por entrada da geração, na mesma ordem — ou **vazio** depois de RE, TLE ou MLE num teste público |
| `outcome` | `accepted` \| `AttemptFailure` | `public_test_failed` se `failed_index` não nulo; senão `all_inputs_failed` se nenhuma entrada sobreviveu; senão `accepted` |

Regra (restaurada em 2026-10-06, R22 item 6): os testes públicos param no primeiro não-AC; as
entradas geradas rodam se todos passaram ou se o primeiro erro foi **WA** (a tentativa pode ser
reserva); depois de RE, TLE ou MLE nenhuma roda.

### 3.4 `SlmSuite` — `problems/<id>/<scenario>/suite.json` (estado terminal)

Função pura dos arquivos da combinação e do `run.json` (research R8).

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id`, `scenario` | | |
| `model`, `model_digest` | str | copiados do `run.json` |
| `status` | `SuiteStatus` | |
| `accepted_phase` | int \| null | **novo**: 1 ou 2 (`accepted`, a fase da tentativa), 3 (`accepted_fallback`), 4 (`accepted_predicted`); `null` em `discarded_manual` |
| `attempts` | list[`AttemptSummary`] | todas, em ordem: `attempt`, `phase`, `seed`, `temperature`, `template`, `hardware_label`, `failure`, `detail`, `fallback_eligible` |
| `accepted_attempt` | int \| null | a tentativa de onde vêm os testes (numa reserva, a escolhida entre as 12); `null` ⇔ `discarded_manual` |
| `tests` | list[`TestCase`] | `input`, `output`; `output` vem da execução real, exceto em `accepted_predicted` (escrito pelo modelo); vazio ⇔ `discarded_manual` |
| `suite_size` | int | `== len(tests)` |
| `discarded_inputs` | list | `{index, discard, verdict}` da tentativa escolhida; vazio em `accepted_predicted` e `discarded_manual` |
| `duplicate_inputs` | int | da tentativa escolhida |
| `manual_close` | objeto \| null | `{reason, closed_at}` ⇔ `discarded_manual` |

Validações (`P` = 12, `M` = 15):

- Cada `AttemptSummary` é a linha da sua tentativa no `ATTEMPT_POLICY` (fase, seed, temperatura,
  template); só a última tentativa pode não ter falha.
- `fallback_eligible` só numa tentativa `solution` com `public_test_failed` por WA.
- `accepted` ⇒ a última tentativa é `solution`, sem falha, é a `accepted_attempt`, e
  `accepted_phase` é a fase dela (1 ou 2).
- `accepted_fallback` ⇒ exatamente `P` tentativas, todas com falha, e a `accepted_attempt` tem
  `fallback_eligible` (a melhor pelo desempate, conferido pelo `store`); `accepted_phase` = 3.
- `accepted_predicted` ⇒ de `P+1` a `M` tentativas, nenhuma das `P` com `fallback_eligible`, a
  última é `prediction` sem falha e é a `accepted_attempt`; `accepted_phase` = 4.
- `discarded_manual` ⇒ exatamente `M` tentativas, todas com falha, nenhuma elegível, `manual_close`
  presente, `accepted_phase` e `accepted_attempt` nulos.

### 3.4a `ManualClose` — `problems/<id>/<scenario>/manual_close.json`

Decisão dos autores sobre uma combinação em `awaiting_manual` (FR-022d), gravada pelo comando
`close`. Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| `problem_id`, `scenario` | | os da pasta |
| `reason` | str | não vazio |
| `closed_at` | str ISO-8601 UTC | quando o comando rodou |

### 3.5 `SlmGenerationReport` — `manifests/slm_generation_report.json`

Campos em [contracts/file-formats.md](./contracts/file-formats.md#5-relatório). Somas de controle
validadas no schema: `accepted + accepted_fallback + accepted_predicted + discarded_manual +
awaiting_manual + pending_generation + pending_execution == total` em cada cenário e no total; os
cenários somam o total; `acceptance` (fase e tentativa em que cada combinação ficou com a suíte)
soma, em cada cenário, as combinações terminais com suíte; o funil por razão (tentativas 1 a 15)
soma `attempts.failed`; `per_phase` soma `attempts.total` em chamadas; as chamadas por etiqueta de
hardware somam `attempts.total`.

### 3.6 `SlmSuitesManifest` — `manifests/slm_suites.manifest.json`

Mesma forma do manifesto dos mutantes: `slm_suites_zip: {path, size, sha256}` e `files: [{path,
size, sha256}]`, ordenado; os caminhos aceitos são os de `run.json`, `suite.json`,
`manual_close.json` e `attempt_<1..15>.(generation|execution).json`.

### 3.7 `TemplateChange` — `data/suites/slm/template_changes/<NNN>.json` (desde 2026-10-07, R27)

Uma troca de template no meio da execução, gravada uma vez por `change-template`; `<NNN>` é o
número com três dígitos (`001`, `002`, ...), sem buraco.

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `2` | |
| `number` | int ≥ 1 | igual ao nome do arquivo |
| `template` | `solution` \| `prediction` | |
| `from_sha256` / `to_sha256` | SHA-256 | diferentes; `from` é o hash corrente (o do `run.json` ou o `to` da troca anterior do mesmo template) |
| `changed_at` | texto UTC | |
| `reason` | texto não vazio | |
| `superseded` | lista de `{problem_id, scenario, files}` | por combinação, em ordem canônica; `files` = nomes movidos (não vazio) |

O **template corrente** de uma execução é o do `run.json` com as trocas aplicadas em ordem
(`store.read_run`); o `--resume` compara a configuração atual com ele.

### 3.8 `superseded/<NNN>/<id>/<cenário>/` (desde 2026-10-07, R27)

Os arquivos que a troca `<NNN>` tirou de `problems/<id>/<cenário>/`, com o mesmo nome. Entram no
pacote e no manifesto; não entram no relatório de métricas nem no estado de nenhuma combinação.

## 4. Máquina de estados de uma combinação

Derivada só dos arquivos presentes, com `n` = maior tentativa existente (`P` = 12, `M` = 15). Uma
linha vale quando nenhuma anterior vale:

| Arquivos presentes | Estado | Próximo passo (comando) |
|---|---|---|
| `suite.json` | **terminal** | nenhum — nunca reprocessado |
| nenhum | `pending_generation(1)` | `generate` (fase 1, seed 42, 0,7) |
| `attempt_n.generation` (`n ≤ P`) com `parse.ok = true`, sem `attempt_n.execution` | `pending_execution(n)` | `execute` |
| `attempt_n.execution` com `outcome = accepted` | `finalizable` | `suite.json(accepted)`, `accepted_phase` = fase de `n` |
| `n < P`, a última falhou (qualquer razão) | `pending_generation(n+1)` | `generate` (na mesma execução se não interpretou; senão `generate --resume`); de 6 para 7 a fase passa de 1 para 2 |
| `n = P`, a última falhou, alguma das `P` pode ser reserva | `finalizable` | `suite.json(accepted_fallback)` da melhor, fase 3 |
| `n = P`, a última falhou, nenhuma pode ser reserva | `pending_generation(P+1)` | `generate` (fase 4, predição) |
| `attempt_n.generation` (`n > P`) com `parse.ok = true` | `finalizable` | `suite.json(accepted_predicted)`, fase 4, gravado pelo próprio `generate` |
| `P < n < M`, a última não interpretou | `pending_generation(n+1)` | `generate` (na mesma execução) |
| `n = M`, sem `manual_close.json` | `awaiting_manual` | os autores rodam `close`; `generate`/`execute` saem com código 4 |
| `n = M`, com `manual_close.json` | `finalizable` | `suite.json(discarded_manual)` |

Inconsistências (são **dano**: o comando não conserta, lista e sai com código 1, e `cli check`
aponta o mesmo): `attempt_3` sem `attempt_2`; execução sem geração ou de uma tentativa
`prediction`; fase, seed, temperatura ou template de uma tentativa diferente da linha dela no
`attempt_policy` do `run.json`; tentativa além da 15ª; `PredictionParse` numa tentativa `solution`
ou o contrário; tentativa depois de uma aceita; tentativa 13 ou mais com uma reserva possível entre
as 12; entradas executadas depois de RE/TLE/MLE; `manual_close.json` fora de `awaiting_manual`;
`model_digest` diferente do `run.json`; `suite.json` que não é a função dos arquivos.

## 5. Concorrência (desde 2026-10-07, research R24, FR-026a)

| Trava (`flock`, sempre sem esperar) | Arquivo | Quem pega | Em conflito |
|---|---|---|---|
| da execução, compartilhada | `data/suites/slm/.lock` | `generate --resume`, `execute` | recusa com código 1 se alguém tem a exclusiva |
| da execução, exclusiva | `data/suites/slm/.lock` | `generate` sem `--resume` (cria o `run.json`), `close`, `package` | recusa com código 1 se alguém tem qualquer uma |
| do `execute` | `data/suites/slm/.execute.lock` | `execute` | um segundo `execute` recusa com código 1 |
| da combinação | `data/suites/slm/.locks/<id>__<cenário>.lock` | `generate` e `execute`, de ler o estado até gravar a última coisa daquela combinação | a combinação é **pulada** e contada (`skipped`) |

O estado de uma combinação (§4) só é lido com a trava dela. Os arquivos de trava não são dados da
execução: começam com ponto e ficam fora do pacote, do manifesto e do `cli check`.
