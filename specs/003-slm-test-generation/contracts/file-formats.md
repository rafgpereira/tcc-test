# Contract: Formatos de arquivo do módulo `ai_clients` (SLM)

**Feature**: `003-slm-test-generation` | Schemas: [data-model.md](../data-model.md).

Todo JSON: UTF-8, chaves ordenadas, indentação 2, `\n` final, escrita atômica
(`dataset.persistence.store.atomic_write_json`), `schema_version: 1`. Nada em `data/suites/` é
versionado; só o pacote da execução final (`data/slm_suites.zip`) e os arquivos de `manifests/`.

## 1. Árvore

```text
data/suites/slm/
├── .lock                                  # flock; nunca empacotado
├── run.json                               # RunConfig
└── problems/<problem_id>/<scenario>/      # scenario ∈ black_box | white_box | hybrid
    ├── attempt_1.generation.json          # GenerationRecord
    ├── attempt_1.execution.json           # ExecutionRecord (só se a geração interpretou)
    ├── …                                  # até attempt_6.*
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
    "model": "qwen2.5-coder:7b",
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
  "problem_id": "1000_B",
  "prompt_sha256": "…",
  "raw_response": "<edge_cases_analysis>\n…</reference_py>",
  "requested_at": "2026-10-01T12:00:00Z",
  "scenario": "black_box",
  "schema_version": 1,
  "seed": 43
}
```

Falha de interpretação: `"parse": {"ok": false, "error": "missing_block:reference_py"}`.

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
  "schema_version": 1
}
```

## 4. `suite.json` — formato unificado da suíte

```json
{
  "accepted_attempt": 2,
  "attempts": [
    {"attempt": 1, "detail": "test 0: WA", "failure": "public_test_failed",
     "hardware_label": "RTX 3060 12GB", "seed": 43},
    {"attempt": 2, "detail": "9 kept, 1 discarded", "failure": null,
     "hardware_label": "RTX 3060 12GB", "seed": 44}
  ],
  "discarded_inputs": [{"discard": "timeout", "index": 4, "verdict": "TLE"}],
  "duplicate_inputs": 0,
  "model": "qwen2.5-coder:7b",
  "model_digest": "sha256:…",
  "problem_id": "1000_B",
  "scenario": "black_box",
  "schema_version": 1,
  "status": "accepted",
  "suite_size": 9,
  "tests": [{"input": "1\n", "output": "1\n"}]
}
```

`tests[*]` tem **exatamente** a forma de `dataset.schemas.testes.TestCase` (`input`, `output`), o
único contrato de caso de teste existente no projeto (research R0; decisão S2 de 2026-09-30): o consumidor
converte cada item em `sandbox.types.Test(input, output)` sem renomear campos. A resposta crua, a
solução Python e os metadados de cada tentativa ficam nos arquivos `attempt_*` ao lado (e vão juntos
no pacote), não repetidos aqui.

Suíte descartada: `"status": "discarded"`, `"accepted_attempt": null`, `"tests": []`,
`"suite_size": 0`, 6 itens em `attempts`, todos com `failure` não nulo.

## 5. Relatório

`manifests/slm_generation_report.json` — chaves de topo: `schema_version`, `model`, `model_digest`,
`ollama_version`, `options`, `seed_base`, `prompt_template_sha256`, `dataset_manifest_sha256`,
`combinations` (`total`, `accepted`, `discarded`, `pending_generation`, `pending_execution`, por
cenário e no total), `discard_rate` (por cenário e total, sobre `total`), `suite_size`
(`count`, `min`, `p25`, `median`, `p75`, `max`, `histogram` por cenário e no total),
`attempts` (`total` de chamadas respondidas, `failed` das que consumiram tentativa),
`attempt_failures` (por razão × número da tentativa, razões de `AttemptFailure`, inclusive
`repetition`), `input_discards` (por razão), `duplicate_inputs`, `done_reason_length`,
`markdown_fences_removed` e `empty_inputs` (os três por cenário e no total, desde 2026-10-04;
antes `done_reason_length` era um número só), `tokens` (`prompt_total`, `eval_total`, `prompt_max`), `duration_s_total`,
`hardware` (etiqueta → nº de chamadas), `seeds` (`<id>/<scenario>` → lista de seeds usadas).

Regras fixadas na implementação (2026-10-01): o escopo é sempre todo problema do dataset × os 3
cenários; quartis e mediana por interpolação linear entre as posições vizinhas (a regra padrão do
numpy), `null` quando não há suíte aceita; `histogram` com o tamanho como texto (chave JSON);
`input_discards` conta as entradas descartadas de **todas** as tentativas executadas (inclusive as
de tentativas que falharam por `all_inputs_failed`); `duplicate_inputs` soma só as das suítes
aceitas (são as que inflam o tamanho de uma suíte usada); uma combinação `finalizable` entra pelo
`suite.json` que os arquivos dão; `duration_s_total` é a soma de `total_duration_ns` relatada pelo
Ollama, sem tempo de espera de infraestrutura. Nenhuma data no arquivo: a mesma árvore dá os
mesmos bytes. Combinação danificada → o relatório não é gravado (código 1).

## 6. Camada `slm_suites` do `cli check`

Acrescentada a `cli.consistency.LAYERS` e a `docs/verificacao-consistencia.md`:

- toda pasta de problema do dataset tem `data/suites/slm/problems/<id>/` com as 3 pastas de cenário,
  e nenhuma pasta sobra (1:1 nos dois sentidos, como a dos mutantes);
- cada cenário tem `suite.json` e `attempt_1..k.generation.json` sem buraco, com `k ≤ 6`, nenhuma
  execução sem a geração correspondente e nenhum outro arquivo;
- `--deep`: SHA-256 de cada arquivo (todos os de `data/suites/slm/`, inclusive `run.json`, fora
  `.lock`) e do zip contra `manifests/slm_suites.manifest.json`; sem manifesto, aviso (como os
  mutantes antes do `package`).

**Severidade (revisto em 2026-10-01, na implementação)**: o texto do plano dizia "cenário sem
`suite.json`: falha com `--deep`, aviso sem ele". Isso tornava impossível o primeiro passo
obrigatório do piloto e da execução completa (`cli check --deep` com saída `0`), em que a árvore
ainda não existe ou está pela metade. Regra implementada: **enquanto o manifesto não existe**,
pasta inteira ausente, problema sem pasta, cenário faltando e `suite.json` faltando são `[AVISO]`,
com ou sem `--deep` (execução em andamento); buraco nas tentativas, mais de 6, arquivo estranho e
pasta sem problema no dataset são `[FALHA]` sempre. **Depois do `package`** (manifesto presente),
tudo o que falta é `[FALHA]`, inclusive a pasta não descompactada.

## 7. Pacote

`data/slm_suites.zip`: raiz `suites/slm/problems/…` (para `unzip data/slm_suites.zip -d data/` cair
no caminho que os comandos leem), todos os arquivos de cada combinação, **sem** `.lock`; `run.json`
entra (proveniência). Datas, permissões e compressão fixas de `dataset.integrity.packaging`.
