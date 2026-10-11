# Contract: Formatos de arquivo do dataset

**Feature**: `001-dataset-extraction` | Fonte de verdade dos campos: [data-model.md](../data-model.md).
Os modelos Pydantic em `src/dataset/schemas/` são a definição executável; este documento traz
exemplos e as regras de serialização. Os módulos futuros MUST consumir os dados por esses
modelos.

## Regras de serialização (valem para todo JSON gravado pelo módulo)

- UTF-8, sem BOM; quebras de linha `\n`.
- `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)` mais uma quebra de linha
  final. Chaves ordenadas e listas na ordem definida garantem bytes idênticos entre execuções
  (Princípio II).
- Gravação atômica: escrever em arquivo temporário no mesmo diretório e `os.replace`.
- `enunciado.md` e os `.cpp` preservam o conteúdo original, normalizando apenas codificação
  para UTF-8 e `\r\n` → `\n`. Sem alteração semântica.

## `metadata.json`

```json
{
  "schema_version": 1,
  "problem_id": "1101_A",
  "cf_contest_id": 1101,
  "cf_index": "A",
  "name": "Minimum Integer",
  "source": "CODEFORCES",
  "cf_rating": 1000,
  "cf_points": 500.0,
  "cf_tags": ["math"],
  "macrocategoria": "matematica",
  "time_limit_seconds": 2.0,
  "memory_limit_bytes": 256000000,
  "is_description_translated": false,
  "dataset_split_origem": "train",
  "num_wa_brutos_disponiveis": 247,
  "num_wa_validados": 100,
  "extraction_timestamp": "2026-09-18T22:00:00Z"
}
```

## `testes.json`

```json
{
  "schema_version": 1,
  "problem_id": "1101_A",
  "public_tests": [{ "input": "5\n1 2 3 4 5\n", "output": "15\n" }],
  "private_tests": [{ "input": "1\n7\n", "output": "7\n" }],
  "generated_tests": [{ "input": "2\n3 3\n", "output": "6\n" }]
}
```

## `validacao.json` — problema completo (trecho)

```json
{
  "schema_version": 1,
  "problem_id": "1101_A",
  "status": "complete",
  "engine": {
    "gcc_version": "13.2.0",
    "flags": ["-Wall", "-Wextra", "-Wconversion", "-static", "-DONLINE_JUDGE", "-O2"],
    "standard_cascade": ["gnu++20", "gnu++17", "gnu++14", "gnu++11"],
    "stack_limit_bytes": 268435456,
    "time_limit_seconds": 2.0,
    "memory_limit_bytes": 256000000,
    "stability_runs": 2
  },
  "ac_ref": {
    "file": "AC_ref.cpp",
    "sha256": "…",
    "verdict": "AC",
    "standard_used": "gnu++20",
    "max_cpu_time_s": 0.21,
    "max_memory_bytes": 3145728,
    "tests_run": 214
  },
  "wa": [
    {
      "file": "WA_1.cpp",
      "sha256": "…",
      "verdict": "WA",
      "standard_used": "gnu++17",
      "max_cpu_time_s": 0.02,
      "max_memory_bytes": 2621440,
      "tests_run": 3,
      "source_index": 41,
      "deciding_test": { "group": "private_tests", "index": 0 },
      "stable": true
    }
  ],
  "discard_reason": null,
  "triage": null
}
```

(`wa` tem exatamente 100 itens em um problema `complete`.)

## `validacao.json` — problema pendente de triagem (FR-011b)

```json
{
  "schema_version": 1,
  "problem_id": "1234_C",
  "status": "pending_triage",
  "engine": { "…": "…" },
  "ac_ref": {
    "file": "AC_candidate.cpp",
    "sha256": "…",
    "verdict": "WA",
    "standard_used": "gnu++20",
    "max_cpu_time_s": 0.05,
    "max_memory_bytes": 3145728,
    "tests_run": 2
  },
  "wa": [],
  "discard_reason": null,
  "triage": {
    "problem_id": "1234_C",
    "stage": "selection",
    "verdict": "WA",
    "reason": "AC diverged from the official answer on public_tests[1]",
    "divergence": {
      "group": "public_tests",
      "index": 1,
      "input": "3\n1 2 3\n",
      "expected": "YES\n",
      "actual": "NO\n",
      "truncated": false,
      "format_only": false
    },
    "engine_diagnostic": null
  }
}
```

Para falha sem saída a comparar (ex.: erro de compilação em todos os padrões), `divergence` é
`null` e `engine_diagnostic` traz os diagnósticos de cada padrão tentado. Na auditoria
(`stage: "audit"`), `verdict` pode ser `"AUDIT_MISMATCH"` quando o veredito atual difere do
registrado.

## `validacao.json` — problema descartado (D4)

Mesmo esquema, com `status: "discarded"`, `discard_reason: "insufficient_wa"` (esgotou as
candidatas sem chegar a 100 WAs) ou `"insufficient_raw_wa"` (o dataset traz menos de 100
submissões incorretas em C++), `wa: []` e `triage: null`.

## `manifests/dataset.manifest.json`

```json
{
  "schema_version": 1,
  "dataset_zip": { "path": "data/dataset.zip", "size": 48213377, "sha256": "…" },
  "files": [
    { "path": "dataset/problems/1101_A/AC_ref.cpp", "size": 412, "sha256": "…" }
  ],
  "problem_count": 200,
  "provenance": {
    "hf_dataset": "deepmind/code_contests",
    "hf_revision": "802411c3010cb00d1b05bad57ca77365a3c699d6",
    "seed": 42,
    "gcc_version": "13.2.0"
  }
}
```

## Estrutura do `dataset.zip`

Entradas ordenadas por caminho, carimbo de modificação fixo `1980-01-01 00:00:00`, permissões
`0644` (arquivos) e `0755` (diretórios), compressão `deflate` com nível fixo, sem campos extras
e sem comentários. A raiz é `dataset/`, para que `unzip data/dataset.zip -d data/` produza
`data/dataset/problems/<problem_id>/`.
