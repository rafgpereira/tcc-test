# Data Model: Revisão 2 do dataset

**Feature**: `specs/007-dataset-revision` | **Date**: 2026-10-18 | **Plan**: [plan.md](./plan.md)

## 1. `manifests/statement_decisions/<id>.json` — `StatementDecision` (versionado; F1)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `Literal[1]` | — |
| `problem_id` | str | um dos problemas `review` do relatório da 006 |
| `decision` | `"correct"` \| `"keep"` | — |
| `enunciado` | str \| null | não nulo ⇔ `decision == "correct"` |
| `reason` | str, não vazio | — |
| `reviewed_by` | str, não vazio | — |
| `reviewed_at` | data ISO | — |
| `sha256_before` | hex | igual ao `enunciado.md` da revisão 1 |

## 2. `manifests/dataset.manifest.json` com `schema_version` 2 (S2)

Os campos de hoje mais os seguintes:

| Campo | Tipo | Regra |
|---|---|---|
| `revision` | int ≥ 2 | 2 nesta feature |
| `revision_of` | `RevisionOf` | só com `schema_version` 2 |

`RevisionOf`:
- `previous_manifest_sha256`: hash do manifesto da revisão 1;
- `fidelity_report_sha256`, `originals_manifest_sha256`, `revision_record_sha256`;
- `created_at`.

O manifesto da revisão 1 fica guardado em `manifests/dataset.rev1.manifest.json`, com
`schema_version` 1 e sem nenhum byte alterado.

## 3. `manifests/dataset_revision.json` — `DatasetRevision` (versionado)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `Literal[1]` | — |
| `revision` | 2 | — |
| `previous_manifest_sha256` | hex | — |
| `changed` | lista de `ChangedStatement`, ordenada por `problem_id` | — |
| `kept` | lista de `{problem_id, reason}` | decisões `"keep"` |

`ChangedStatement`:
- `problem_id`;
- `origin`: `"automatic"` | `"manual"`;
- `markups`: dict de tipo → n, só para `"automatic"`;
- `reason`: só para `"manual"`;
- `sha256_before`, `sha256_after`.

**Validações**:
- os `problem_id` de `changed` e `kept` são disjuntos;
- `changed` + `kept` cobrem todos os problemas `losses` do relatório.

## 4. `provenance.json` dentro de `data/slm_suites.zip` (R6)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `Literal[1]` | — |
| `combinations` | lista de `{problem_id, scenario, tree, dataset_manifest_sha256, dataset_revision, superseded_in}` | 600, uma por combinação, todas presentes |

- `tree` vale `"suites/slm"` (execução nova) ou `"suites/slm-rev1"`.
- `superseded_in` só aparece nas entradas da árvore anterior que foram refeitas.
- **Validação**: cada combinação aparece **uma vez** como vigente.
