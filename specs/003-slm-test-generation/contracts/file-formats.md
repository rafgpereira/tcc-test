# Contract: Formatos de arquivo do módulo `ai_clients` (SLM)

**Feature**: `003-slm-test-generation` | Schemas: [data-model.md](../data-model.md).

Todo JSON: UTF-8, chaves ordenadas, indentação 2, `\n` final, escrita atômica
(`dataset.persistence.store.atomic_write_json`), `schema_version: 2` (desde 2026-10-06, R22; era 1 — um `run.json` de versão 1 é recusado e a pasta precisa ser movida). Nada em `data/suites/` é
versionado; só o pacote da execução final (`data/slm_suites.zip`) e os arquivos de `manifests/`.

## 1. Árvore

```text
data/suites/slm/
├── .lock                                  # flock da execução; nunca empacotado
├── .execute.lock                          # flock: um execute por vez (desde 2026-10-07)
├── .locks/<id>__<scenario>.lock          # flock por combinação (desde 2026-10-07)
├── run.json                               # RunConfig
└── problems/<problem_id>/<scenario>/      # scenario ∈ black_box | white_box | hybrid
    ├── attempt_1.generation.json          # GenerationRecord
    ├── attempt_1.execution.json           # ExecutionRecord (só se a geração interpretou)
    ├── …                                  # até attempt_12.* (fases 1 e 2: solução Python)
    ├── attempt_13.generation.json         # 13 a 15: predição (fase 4), nunca com execution
    ├── manual_close.json                  # ManualClose — só depois do comando close
    └── suite.json                         # SlmSuite — estado terminal
manifests/slm_generation_report.json       # SlmGenerationReport (versionado)
manifests/slm_suites.manifest.json         # SlmSuitesManifest (versionado)
data/slm_suites.zip                        # só da execução final (versionado, D3)
```

Diretórios criados nível a nível com `store.make_private_dir` (mesmo motivo do `mutation`: o
serviço `sandbox` roda como root e nada pode ficar com dono root no `./data` montado).

## 2. `attempt_<n>.generation.json` (exemplo abreviado)

```json
{
  "attempt": 1,
  "hardware_label": "RTX 3060 12GB",
  "ollama": {
    "created_at": "2026-10-01T12:00:00.000Z",
    "done_reason": "stop",
    "eval_count": 812,
    "eval_duration_ns": 20400000000,
    "load_duration_ns": 31000000,
    "model": "qwen2.5-coder:14b",
    "prompt_eval_count": 1570,
    "prompt_eval_duration_ns": 900000000,
    "total_duration_ns": 21500000000
  },
  "model_failure": null,
  "parse": {
    "duplicate_inputs": 0,
    "edge_cases_analysis": "…",
    "empty_inputs": 0,
    "extraneous_chars": 0,
    "inputs": ["1\n", "5\n1 2 3 4 5\n"],
    "markdown_fence_removed": false,
    "ok": true,
    "reference_py": "import sys\n…"
  },
  "model_digest": "sha256:…",
  "phase": 1,
  "problem_id": "1000_B",
  "prompt_sha256": "…",
  "raw_response": "<edge_cases_analysis>\n…</inputs>",
  "requested_at": "2026-10-01T12:00:00Z",
  "scenario": "black_box",
  "schema_version": 2,
  "seed": 42,
  "temperature": 0.7,
  "template": "solution"
}
```

Falha de interpretação: `"parse": {"ok": false, "error": "missing_block:reference_py"}`.

`phase`, `seed`, `temperature` e `template` são a linha da tentativa no `attempt_policy` do
`run.json` (data-model §2). Tentativa por predição interpretada (13 a 15; research R19 item 4, R22
item 7):

```json
"parse": {
  "duplicate_inputs": 0,
  "edge_cases_analysis": "…",
  "empty_tests": 0,
  "extraneous_chars": 0,
  "markdown_fences_removed": 0,
  "ok": true,
  "tests": [{"input": "1\n", "output": "YES\n"}]
}
```

## 3. `attempt_<n>.execution.json` (exemplo abreviado)

```json
{
  "attempt": 1,
  "inputs": [
    {"cpu_time_s": 0.03, "discard": null, "index": 0, "kept": true, "output": "1\n",
     "peak_rss_bytes": 9437184, "stderr_tail": "", "verdict": null},
    {"cpu_time_s": 10.0, "discard": "timeout", "index": 1, "kept": false, "output": null,
     "peak_rss_bytes": 9437184, "stderr_tail": "", "verdict": "TLE"}
  ],
  "interpreter": "/opt/python/…/bin/python3.11 (3.11.16)",
  "limits": {"memory_limit_bytes": 1073741824, "problem_memory_limit_bytes": 268435456,
             "problem_time_limit_seconds": 1.0, "time_limit_seconds": 10.0},
  "outcome": "accepted",
  "problem_id": "1000_B",
  "public_tests": {"failed_cpu_time_s": null, "failed_index": null, "failed_output_head": null,
                   "failed_peak_rss_bytes": null, "failed_stderr_tail": null,
                   "failed_verdict": null, "passed": 2, "total": 2},
  "scenario": "black_box",
  "schema_version": 2
}
```

## 4. `suite.json` — formato unificado da suíte

```json
{
  "accepted_attempt": 2,
  "accepted_phase": 1,
  "attempts": [
    {"attempt": 1, "detail": "test 0: WA; 7 kept, 0 discarded", "failure": "public_test_failed",
     "fallback_eligible": true, "hardware_label": "RTX 3060 12GB", "phase": 1, "seed": 42,
     "temperature": 0.7, "template": "solution"},
    {"attempt": 2, "detail": "9 kept, 1 discarded", "failure": null, "fallback_eligible": false,
     "hardware_label": "RTX 3060 12GB", "phase": 1, "seed": 43, "temperature": 0.7,
     "template": "solution"}
  ],
  "discarded_inputs": [{"discard": "timeout", "index": 4, "verdict": "TLE"}],
  "duplicate_inputs": 0,
  "manual_close": null,
  "model": "qwen2.5-coder:14b",
  "model_digest": "sha256:…",
  "problem_id": "1000_B",
  "scenario": "black_box",
  "schema_version": 2,
  "status": "accepted",
  "suite_size": 9,
  "tests": [{"input": "1\n", "output": "1\n"}]
}
```

`tests[*]` tem **exatamente** a forma de `dataset.schemas.testes.TestCase` (`input`, `output`), o
único contrato de caso de teste existente no projeto (research R0; decisão S2 de 2026-09-30): o
consumidor converte cada item em `sandbox.types.Test(input, output)` sem renomear campos. A resposta
crua, a solução Python e os metadados de cada tentativa ficam nos arquivos `attempt_*` ao lado.

Por status (desde 2026-10-06, R21/R22):

- `accepted`: `accepted_phase` 1 ou 2 (a fase da tentativa aceita, a última).
- `accepted_fallback` (fase 3): 12 itens em `attempts`, todos com falha; `accepted_attempt` = a
  escolhida entre as que têm `"fallback_eligible": true` (não necessariamente a última);
  `accepted_phase` 3; as saídas vêm de uma solução que reprovou um teste público por WA.
- `accepted_predicted` (fase 4): de 13 a 15 itens; a última é `"template": "prediction"`, sem falha,
  e é a `accepted_attempt`; `accepted_phase` 4; `tests` são os pares escritos pelo modelo;
  `discarded_inputs` vazio.
- `discarded_manual` (fase 5): 15 itens, todos com falha; `accepted_attempt` e `accepted_phase`
  `null`, `tests` vazio e `"manual_close": {"closed_at": "…", "reason": "…"}`, copiado de
  `manual_close.json`.

`accepted_low_confidence` (R19) e `discarded` (até R18) não existem mais.

## 5. Relatório

`manifests/slm_generation_report.json` (`schema_version` 2) — chaves de topo: `schema_version`,
`model`, `model_digest`, `ollama_version`, `options`, `attempt_policy` (a tabela do `run.json`),
`prompt_template_sha256`, `predict_template_sha256`, `dataset_manifest_sha256`,
`combinations` (`total`, `accepted`, `accepted_fallback`, `accepted_predicted`, `discarded_manual`,
`awaiting_manual`, `pending_generation`, `pending_execution`, por cenário e no total),
`status_rate` (status → cenário e total → proporção sobre `total`),
**`acceptance`** (novo: por cenário e no total, `by_phase` — fase 1 a 4 → combinações que ficaram
com a suíte nela — e `by_attempt` — tentativa 1 a 15 → combinações cuja `accepted_attempt` é ela),
`suite_size` por status com testes (`count`, `min`, `p25`, `median`, `p75`, `max`, `histogram`, por
cenário e no total), `attempts` (`total` de chamadas respondidas, `failed`), **`per_phase`** (novo:
fase 1, 2 e 4 → `calls`, `failed`, `prompt_tokens`, `eval_tokens`, `duration_s`),
`attempt_failures` (razão × tentativa 1 a 15), `input_discards`, `duplicate_inputs`,
`done_reason_length`, `markdown_fences_removed` (solução e predição somadas), `empty_inputs`,
`empty_tests`, `tokens`, `duration_s_total`, `hardware`, `seeds`.

Regras fixadas na implementação (2026-10-01): o escopo é sempre todo problema do dataset × os 3
cenários; quartis e mediana por interpolação linear (a regra padrão do numpy), `null` sem suíte;
`histogram` com o tamanho como texto; `input_discards` conta as entradas descartadas de todas as
tentativas executadas; `duplicate_inputs` soma as das suítes com testes; uma combinação
`finalizable` entra pelo `suite.json` que os arquivos dão; os tempos são os `total_duration_ns`
do Ollama, sem tempo de espera de infraestrutura. Nenhuma data no arquivo: a mesma árvore dá os
mesmos bytes. Combinação danificada → o relatório não é gravado (código 1).

## 6. Camada `slm_suites` do `cli check`

Acrescentada a `cli.consistency.LAYERS` e a `docs/verificacao-consistencia.md`:

- toda pasta de problema do dataset tem `data/suites/slm/problems/<id>/` com as 3 pastas de cenário,
  e nenhuma pasta sobra (1:1 nos dois sentidos, como a dos mutantes);
- cada cenário tem `suite.json` e `attempt_1..k.generation.json` sem buraco, com `k ≤ 15` (era 6,
  depois 12 e 23), nenhuma execução sem a geração correspondente, nenhuma execução de tentativa
  `> 12`, e nenhum outro arquivo além de `manual_close.json`;
- `--deep`: SHA-256 de cada arquivo (todos os de `data/suites/slm/`, inclusive `run.json`, fora
  `.lock`) e do zip contra `manifests/slm_suites.manifest.json`; sem manifesto, aviso (como os
  mutantes antes do `package`).

**Severidade (revisto em 2026-10-01, na implementação)**: o texto do plano dizia "cenário sem
`suite.json`: falha com `--deep`, aviso sem ele". Isso tornava impossível o primeiro passo
obrigatório do piloto e da execução completa (`cli check --deep` com saída `0`), em que a árvore
ainda não existe ou está pela metade. Regra implementada: **enquanto o manifesto não existe**,
pasta inteira ausente, problema sem pasta, cenário faltando e `suite.json` faltando são `[AVISO]`,
com ou sem `--deep` (execução em andamento); buraco nas tentativas, mais de 15, arquivo estranho e
pasta sem problema no dataset são `[FALHA]` sempre. **Depois do `package`** (manifesto presente),
tudo o que falta é `[FALHA]`, inclusive a pasta não descompactada.

## 7. Pacote

`data/slm_suites.zip`: raiz `suites/slm/problems/…` (para `unzip data/slm_suites.zip -d data/` cair
no caminho que os comandos leem), todos os arquivos de cada combinação, **sem** `.lock`; `run.json`
entra (proveniência), e também `template_changes/` e `superseded/` (desde 2026-10-07, R27; o
manifesto aceita esses caminhos). Datas, permissões e compressão fixas de `dataset.integrity.packaging`.

## 8. Trocas de template (desde 2026-10-07, research R27)

```
data/suites/slm/
├── run.json                                   # nunca reescrito
├── template_changes/001.json                  # TemplateChange (data-model §3.7)
├── superseded/001/<id>/<cenário>/             # o que a troca 001 tirou de problems/ (§3.8)
│   ├── suite.json
│   ├── attempt_14.generation.json
│   └── attempt_13.generation.json
└── problems/<id>/<cenário>/attempt_13.generation.json   # refeita: "template_sha256" = o novo
```

```json
{
  "schema_version": 2,
  "number": 1,
  "template": "prediction",
  "from_sha256": "421adf86…",
  "to_sha256": "…",
  "changed_at": "2026-10-07T23:10:00Z",
  "reason": "…",
  "superseded": [
    {"problem_id": "939_C", "scenario": "black_box",
     "files": ["suite.json", "attempt_14.generation.json", "attempt_13.generation.json"]}
  ]
}
```

`files` está na ordem em que os arquivos são movidos (suíte e fechamento manual primeiro, depois as
tentativas da maior para a menor). `attempt_<n>.generation.json` ganha `"template_sha256"` (o hash
do template usado; ausente nas tentativas anteriores a 2026-10-07) e `PredictionParse` ganha
`"abbreviated_tests"` (ausente = 0). O relatório ganha `template_changes` (número, template, hashes,
data, motivo, combinações e arquivos movidos) e `abbreviated_tests` por cenário. Na camada
`slm_suites` do `cli check`, uma linha `INFO` (trocas, combinações refeitas, arquivos guardados) e
uma linha `superseded/ bate com as trocas de template` (`OK` ou `FALHA` listando o arquivo ainda
não movido, ausente ou que nenhuma troca lista).
