# Data Model: Conferência dos enunciados contra o original do Codeforces

**Feature**: `specs/006-statement-fidelity` | **Date**: 2026-10-18 | **Plan**: [plan.md](./plan.md)

Todos os schemas são Pydantic, com `extra="forbid"` e `schema_version: Literal[1]`, em
`src/dataset/schemas/statements.py`.

## 1. `manifests/statement_originals.manifest.json` — `OriginalsManifest` (versionado)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `Literal[1]` | — |
| `dataset_manifest_sha256` | hex de 64 | o dataset cujos `metadata.json` deram as URLs |
| `user_agent` | str | o identificador usado nos pedidos (E2) |
| `min_interval_s` | float ≥ 3 | E2 |
| `originals` | lista de `OriginalEntry`, uma por problema, ordenada por `problem_id` | 200 entradas |

`OriginalEntry`:
- `problem_id`, `url`;
- `fetched_at` (UTC, ISO 8601) e `http_status`;
- `page_bytes`, `page_sha256`: a página inteira, guardada em `data/statements/originals/<id>.html`;
- `statement_sha256`: o bloco `problem-statement` extraído, que vai no pacote (S1); `null` se a
  página não tem o bloco;
- `error`: `null`, ou o motivo de não haver cópia (`http_404`, `no_statement_block`, …).

**Validações**:
- `error` nulo ⇔ `http_status == 200` e `page_sha256` presente;
- os `problem_id` são únicos.

## 2. `manifests/statement_fidelity_report.json` — `FidelityReport` (versionado)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `Literal[1]` | — |
| `dataset_manifest_sha256`, `originals_manifest_sha256` | hex | ligam o relatório às duas entradas |
| `equivalences` | dict `comando LaTeX → texto` | a tabela de R4 usada (S3) |
| `problems` | lista de `ProblemFidelity`, ordenada por `problem_id` | uma por problema |
| `totals` | `FidelityTotals` | contagens |

`ProblemFidelity`:
- `problem_id`;
- `format`: `"marked"` (formato antigo, com `sup`/`sub`) | `"latex"` (formato novo) | `"mixed"`;
- `status`: `"faithful"` | `"losses"` | `"unchecked"`;
- `unchecked_reason`: str | `null`; não nulo ⇔ `status == "unchecked"`;
- `differences`: lista de `Difference`; vazia ⇔ `status == "faithful"`.

`Difference`:
- `kind`: `"lost_exponent"` | `"lost_index"` | `"formula"` | `"image"` | `"table"` | `"other"`;
- `original`: o trecho do original, marcado, por exemplo `10^{5}`;
- `ours`: o trecho do nosso texto, por exemplo `105`;
- `context`: até 30 caracteres em volta, do nosso texto;
- `ours_offset`: a posição no `enunciado.md`; é o que a correção usa.

`FidelityTotals`:
- `problems`, `faithful`, `with_losses`, `unchecked`;
- `by_kind`: dict `kind → número de diferenças`;
- `problems_by_kind`: dict `kind → número de problemas`.

**Validação**: `faithful + with_losses + unchecked == problems == 200` no dataset real.

## 3. `DIR/summary.json` — `CorrectionSummary` (não versionado, para revisão)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `Literal[1]` | — |
| `report_sha256` | hex | o relatório de onde vieram as diferenças |
| `corrected` | lista de `CorrectedStatement` | uma por problema com perdas corrigíveis |
| `unchanged` | lista de `problem_id` | `faithful`: nada a corrigir |
| `review` | lista de `{problem_id, reasons}` | imagem, fórmula desconhecida, `other`, conferência que falhou, `unchecked` |

`CorrectedStatement`:
- `problem_id`, `file` (`<id>.md`);
- `markups_inserted`: dict `kind → n`;
- `checks`: `{text_equal: bool, all_marks_present: bool, only_markup_diff: bool}`, que tem de
  ser tudo `true` para o problema estar em `corrected`;
- `sha256_before` (o `enunciado.md` atual) e `sha256_after` (o corrigido).

**Validação**: cada `problem_id` do dataset aparece em exatamente uma das três listas.

## 4. Arquivos

```text
data/statements/originals/<id>.html      # as páginas inteiras (fora do Git)
data/statement_originals.zip             # statements/<id>.html: só os blocos (versionado, S1)
manifests/statement_originals.manifest.json
manifests/statement_fidelity_report.json
DIR/<id>.md  DIR/summary.json            # correct-statements, pasta plana (fora do Git)
```
