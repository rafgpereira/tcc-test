# Data Model: Geração de Mutantes

**Feature**: `002-mutant-generation` | Fonte: `spec.md` (Key Entities) + `research.md` (R1–R3).
Os modelos executáveis (Pydantic) vivem em `src/mutation/schemas/`; este documento é a
referência de campos e invariantes.

## Sítio de mutação (`Site`)

Não persistido como arquivo — estrutura interna de `src/mutation/sites.py`.

| Campo | Tipo | Notas |
|---|---|---|
| `kind` | enum `OPERATOR`, `OPERAND_LEFT`, `OPERAND_RIGHT` | qual parte do nó AST o sítio ocupa (ver research.md, R2) |
| `node_type` | `"binary_expression"` \| `"unary_expression"` \| `"update_expression"` | tipo do nó `tree-sitter` de origem; `unary_expression` cobre o `-x` e o `!x` que já existem no código |
| `start_byte`, `end_byte` | `int` | intervalo de bytes no `AC_ref.cpp` original a substituir |
| `discovery_index` | `int` | posição na travessia pré-ordem (R3) — define a ordem determinística de tudo neste módulo |
| `eligible_operators` | `tuple[MutationOperator, ...]` | quais operadores (ROR/AOR/LCR/ABS/UOI) se aplicam a este sítio, na ordem em que são tentados |
| `operand_type` | `str \| None` | tipo do nó `tree-sitter` do operando (`None` nos sítios de operador); só se põe `++`/`--` na frente de algo que pode ser atribuído (`identifier`, `subscript_expression`, `field_expression`, ...) |
| `parent_operator` | `str \| None` | token do operador do `binary_expression` a que um sítio de operando pertence (`None` nos sítios de operador); decide qual unário é legal na frente do operando |

Identidade: dois sítios são o mesmo sítio quando `(node_type, start_byte, end_byte, kind)` coincidem;
`discovery_index`, `eligible_operators` e `parent_operator` são propriedades, não identidade.

## Operador de mutação (`MutationOperator`)

Enum: `ROR`, `AOR`, `LCR`, `ABS`, `UOI`. Cada um é uma função pura em `operators.py`:
`apply(source: str, site: Site, variant: int) -> str | None` (retorna `None` se a variante não
é sintaticamente aplicável ao sítio, ex.: `!` num sítio ABS).

| Operador | Sítio (`kind`) | Nº de variantes por sítio |
|---|---|---|
| ROR | `OPERATOR` (nó relacional: `< <= > >= == !=`) | 5 (todos os outros operadores relacionais) |
| AOR | `OPERATOR` (nó aritmético: `+ - * / %`, e os deslocamentos `<< >>`) | 4 para `+ - * / %` (os outros quatro); 1 para `<<`/`>>` (o outro deslocamento — nunca trocado por `+ - * / %`, que não tipa para os fluxos `cin >>`/`cout <<`) |
| LCR | `OPERATOR` (nó lógico: `&& \|\|`) | 1 (o outro conector) |
| ABS | `OPERAND_LEFT`/`OPERAND_RIGHT` de sítio ROR ou AOR | 3 (`0`, `(+abs(x))`, `(-abs(x))`); zero sobre o literal `0` não é mutação |
| UOI | `OPERAND_LEFT`/`OPERAND_RIGHT` de qualquer sítio ROR/AOR/LCR, ou `OPERATOR` de `unary_expression`/`update_expression` | operando de ROR: `- ! ++ --`; de AOR: `- ++ --` (nunca `!`); de LCR: só `!`; sobre `-x`/`!x` existente troca um pelo outro; sobre `++`/`--` existente troca um pelo outro |

Não são sítios (medido em R16, por só gerarem candidatos que não compilam): **E/S de fluxo** — em
`cin >> a >> b` e `cout << x << endl` (cadeia de deslocamentos que começa em `cin`/`cout`/`cerr`/
`clog`, com ou sem `std::`) não há sítio de operador nem de operando esquerdo, e o operando direito
só existe para `cout <<` (o valor impresso; o que `cin >>` lê é um destino, não um valor);
**operandos que são texto** (literal de string) ou **manipuladores** (`endl`, `flush`, `ends`); **ABS
sobre tamanhos** (`x.size()`, `x.length()`, `sizeof ...`: são sem sinal, `abs` é ambíguo ou não
muda nada). Expressões aritméticas/relacionais dentro de uma instrução de fluxo (`cout << (a + b)`)
continuam com os seus próprios sítios. `++`/`--` só entram na frente de operando atribuível
(`operand_type`).

Um operando composto recebe parênteses na frente do unário (`!(a * b) < c`), para o unário valer
sobre a subexpressão inteira. Operadores bit a bit (`& \| ^`), vírgula e `~`/`+` unário não são
sítios. Sítios dentro da condição de `#if`/`#elif` não existem (não são lógica do programa).

## Mutante (`MutantCandidate` → `Mutant`)

| Campo | Tipo | Notas |
|---|---|---|
| `problem_id` | `str` | mesmo identificador `<ContestID>_<Index>` do dataset |
| `index` | `int` (1–100) | número final do arquivo (`Mutant_<index>.cpp`), na ordem de aceitação |
| `order` | `int` (1, 2 ou 3) | primeira ordem, par ou trio |
| `sites` | `tuple[Site, ...]` | 1 sítio (ordem 1), 2 (ordem 2) ou 3 (ordem 3) |
| `operators` | `tuple[tuple[MutationOperator, int], ...]` | operador + variante aplicado a cada sítio, na mesma ordem de `sites` |
| `source` | `str` | texto do mutante (é o que vira `Mutant_<index>.cpp`) |
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
| `reason` | enum `duplicate`, `compile_error`, `tle`, `mle`, `re`, `equivalent`, `unstable` (nomes em maiúsculas no código, valores em minúsculas no JSON) | motivo de FR-005/FR-007; `duplicate` cobre todo texto já avaliado no problema (aceito **ou** descartado antes), não só os aceitos |

Agregado no funil do relatório (`mutation_report.json`) e, por problema, em contagens por
(ordem, motivo) no `generation.json` abaixo; nunca persistido candidato a candidato (diferente do dataset, que persiste `WA_*.cpp` mesmo descartadas em `data/work/` — aqui só
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

## Registro de geração por problema (`data/mutants/problems/<problem_id>/generation.json`)

Existe só no desenvolvimento e na máquina de quem gerou (nunca entra no zip): é a memória de que
`report` precisa para recalcular funil e distribuições depois, sem regerar nada. Escrito por
último e fecha o problema (a pasta só existe em `problems/` com ele dentro).

| Campo | Tipo | Notas |
|---|---|---|
| `schema_version` | `int` | 1 |
| `problem_id` | `str` | igual ao nome da pasta |
| `status` | `"complete"` \| `"excluded"` | `complete`: exatamente 100 mutantes e sem `exclusion`; `excluded`: nenhum mutante e `exclusion` presente |
| `mutants` | `list[{file, order, operators: [{operator, variant}], sha256}]` | `file` = `Mutant_1.cpp`, `Mutant_2.cpp`, ... em ordem; `len(operators) == order` |
| `discards` | `list[{order, reason, count}]` | uma linha por par (ordem, motivo), ordenada |
| `exclusion` | `{mutants_reached, highest_order_attempted} \| null` | só em `excluded` (FR-009) |

## Pacote de mutantes (`data/mutants.zip`) e manifesto (`mutants.manifest.json`)

Mesma estrutura já usada para `data/dataset.zip`/`manifests/dataset.manifest.json` (ver
`specs/001-dataset-extraction/contracts/file-formats.md`): zip determinístico (entradas
ordenadas, timestamps fixos), manifesto com `schema_version`, hash SHA-256 e tamanho de cada
arquivo, mais o hash e tamanho do próprio zip. Layout dentro do zip:

```text
mutants/
└── problems/
    └── <problem_id>/
        ├── Mutant_1.cpp
        ├── ...
        └── Mutant_100.cpp    # ausente para problemas com ExclusionAlert
```

Com `unzip data/mutants.zip -d data/` o resultado é `data/mutants/problems/<problem_id>/`, **o mesmo
caminho** em que `generate` grava (e, portanto, o mesmo que os módulos consumidores leem, tenha o
autor gerado os mutantes ou só recebido o pacote) — analogamente ao dataset, cuja raiz do zip
(`dataset/problems/<id>/`) reproduz o layout de consumo `data/dataset/problems/<id>/`.

Só os `Mutant_<n>.cpp` entram no zip; o `generation.json` fica de fora.

Só existe depois de um comando explícito de empacotamento (`python -m mutation package`),
nunca gerado automaticamente durante o desenvolvimento — ver contracts/cli.md.

## Relatório (`manifests/mutation_report.json`)

| Campo | Tipo | Notas |
|---|---|---|
| `schema_version` | `int` | começa em 1 |
| `problems` | `{closed, complete, first_order_only, higher_order, excluded}` | quantos problemas já fechados terminaram como completos (só primeira ordem ou com ordem superior) e quantos excluídos |
| `funnel` | `dict[DiscardReason, int]` | agregado de todos os `DiscardRecord` |
| `order_distribution` | `dict[int, int]` | quantos mutantes (somando todos os problemas) vieram de ordem 1, 2 ou 3 |
| `operator_distribution` | `dict[MutationOperator, int]` | quantos mutantes usaram cada operador (um mutante de ordem 2+ conta para cada operador que usa) |
| `exclusion_alerts` | `list[ExclusionAlert]` | vazia no caso esperado (SC-003/SC-001) |
| `dataset_manifest_sha256` | `str` | hash de `manifests/dataset.manifest.json` verificado antes de rodar (liga este relatório à versão exata do dataset consumida) |

## Reexportações do módulo `sandbox` (sem alteração)

`Verdict`, `ExecutionLimits`, `Test`, `SuiteVerdict`, `judge_source` — ver
`specs/001-dataset-extraction/contracts/engine-api.md`. Este módulo não define nenhum tipo novo
de execução; só consome os já existentes.
