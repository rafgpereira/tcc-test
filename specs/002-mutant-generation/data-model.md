# Data Model: Geração de Mutantes

**Feature**: `002-mutant-generation` | Fonte: `spec.md` (Key Entities) + `research.md` (R1–R3).
Os modelos executáveis (Pydantic) vivem em `src/mutation/schemas/`; este documento é a
referência de campos e invariantes.

## Sítio de mutação (`Site`)

Não persistido como arquivo — estrutura interna de `src/mutation/sites.py`.

| Campo | Tipo | Notas |
|---|---|---|
| `kind` | enum `OPERATOR`, `OPERAND_LEFT`, `OPERAND_RIGHT` | qual parte do nó AST o sítio ocupa (ver research.md, R2) |
| `node_type` | `"binary_expression"` \| `"update_expression"` | tipo do nó `tree-sitter` de origem |
| `start_byte`, `end_byte` | `int` | intervalo de bytes no `AC_ref.cpp` original a substituir |
| `discovery_index` | `int` | posição na travessia pré-ordem (R3) — define a ordem determinística de tudo neste módulo |
| `eligible_operators` | `list[MutationOperator]` | quais operadores (ROR/AOR/LCR/ABS/UOI) se aplicam a este sítio |

## Operador de mutação (`MutationOperator`)

Enum: `ROR`, `AOR`, `LCR`, `ABS`, `UOI`. Cada um é uma função pura em `operators.py`:
`apply(source: str, site: Site, variant: int) -> str | None` (retorna `None` se a variante não
é sintaticamente aplicável ao sítio, ex.: `!` num sítio ABS).

| Operador | Sítio (`kind`) | Nº de variantes por sítio |
|---|---|---|
| ROR | `OPERATOR` (nó relacional) | até 5 (todos os outros operadores relacionais legais) |
| AOR | `OPERATOR` (nó aritmético) | até 4–5 (demais operadores aritméticos legais) |
| LCR | `OPERATOR` (nó lógico) | 1 (o outro conector) |
| ABS | `OPERAND_LEFT`/`OPERAND_RIGHT` de sítio AOR | 3 (zero, positivo, negativo) |
| UOI | `OPERAND_LEFT`/`OPERAND_RIGHT` de qualquer sítio, ou `update_expression` | 1–4, conforme o unário legal para o sítio |

## Mutante (`MutantCandidate` → `Mutant`)

| Campo | Tipo | Notas |
|---|---|---|
| `problem_id` | `str` | mesmo identificador `<ContestID>_<Index>` do dataset |
| `index` | `int` (1–100) | número final do arquivo (`Mutant_<index>.cpp`), na ordem de aceitação |
| `order` | `int` (1, 2 ou 3) | primeira ordem, par ou trio |
| `sites` | `list[Site]` | 1 sítio (ordem 1), 2 (ordem 2) ou 3 (ordem 3) |
| `operators` | `list[tuple[MutationOperator, int]]` | operador + variante aplicado a cada sítio, na mesma ordem de `sites` |
| `source_sha256` | `str` | hash do texto mutado — usado para a checagem de unicidade (FR-005a) |
| `verdict` | `Verdict` (reexportado de `sandbox.types`) | veredito da validação (deve ser `WA` para ser aceito) |
| `stability_runs` | `int` (sempre 6, FR-007) | nº de execuções concordantes exigidas |

Invariante: um `Mutant` só existe (é persistido) depois de passar por todos os critérios de
FR-005 e pela confirmação de estabilidade de FR-007 — não há estado "candidato salvo, ainda não
confirmado".

## Registro de descarte (`DiscardRecord`)

| Campo | Tipo | Notas |
|---|---|---|
| `problem_id` | `str` | |
| `order` | `int` | 1, 2 ou 3 |
| `reason` | enum `DUPLICATE`, `COMPILE_ERROR`, `TLE`, `MLE`, `RE`, `EQUIVALENT`, `UNSTABLE` | motivo de FR-005/FR-007 |

Agregado no funil do relatório (`mutation_report.json`), nunca persistido individualmente fora
dele (diferente do dataset, que persiste `WA_*.cpp` mesmo descartadas em `data/work/` — aqui só
o texto-fonte de um mutante *aceito* é gravado, para não multiplicar por 10–50× o volume de
`data/mutants/` de desenvolvimento com candidatos rejeitados).

## Alerta de exclusão de problema (`ExclusionAlert`)

| Campo | Tipo | Notas |
|---|---|---|
| `problem_id` | `str` | |
| `mutants_reached` | `int` (< 100) | quantos mutantes válidos foram alcançados antes de esgotar as combinações (ou o orçamento medido, ver research.md R4) |
| `highest_order_attempted` | `int` (1, 2 ou 3) | |

Consequência (spec, FR-009/FR-009a): o problema é excluído do conjunto final de mutantes; o
denominador do Escore de Mutação (métricas, seção 5.2) passa a contar só os problemas com
mutantes completos; TDF e TFP não são afetados.

## Pacote de mutantes (`data/mutants.zip`) e manifesto (`mutants.manifest.json`)

Mesma estrutura já usada para `data/dataset.zip`/`manifests/dataset.manifest.json` (ver
`specs/001-dataset-extraction/contracts/file-formats.md`): zip determinístico (entradas
ordenadas, timestamps fixos), manifesto com `schema_version`, hash SHA-256 e tamanho de cada
arquivo, mais o hash e tamanho do próprio zip. Layout dentro do zip:

```text
mutants/
└── <problem_id>/
    ├── Mutant_1.cpp
    ├── ...
    └── Mutant_100.cpp        # ausente para problemas com ExclusionAlert
```

Só existe depois de um comando explícito de empacotamento (`python -m mutation package`),
nunca gerado automaticamente durante o desenvolvimento — ver contracts/cli.md.

## Relatório (`manifests/mutation_report.json`)

| Campo | Tipo | Notas |
|---|---|---|
| `schema_version` | `int` | começa em 1 |
| `funnel` | `dict[DiscardReason, int]` | agregado de todos os `DiscardRecord` |
| `order_distribution` | `dict[int, int]` | quantos mutantes (somando todos os problemas) vieram de ordem 1, 2 ou 3 |
| `operator_distribution` | `dict[MutationOperator, int]` | quantos mutantes usaram cada operador (um mutante de ordem 2+ conta para cada operador que usa) |
| `exclusion_alerts` | `list[ExclusionAlert]` | vazia no caso esperado (SC-003/SC-001) |
| `code_revision` | `str` | hash do commit git do módulo `mutation` usado nesta execução |
| `dataset_manifest_sha256` | `str` | hash de `manifests/dataset.manifest.json` verificado antes de rodar (liga este relatório à versão exata do dataset consumida) |

## Reexportações do módulo `sandbox` (sem alteração)

`Verdict`, `ExecutionLimits`, `Test`, `SuiteVerdict`, `judge_source` — ver
`specs/001-dataset-extraction/contracts/engine-api.md`. Este módulo não define nenhum tipo novo
de execução; só consome os já existentes.
