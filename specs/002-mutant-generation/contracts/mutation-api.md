# Contract: API interna de geração de mutantes (`src/mutation/`)

**Feature**: `002-mutant-generation` | Requisitos: FR-001 a FR-011 | Decisões: D1–D3, D6
(spec.md). Verificação empírica: `research.md`, R1–R3.

Esta API é interna ao módulo (não é reutilizada por outros módulos, ao contrário do
`sandbox.judge_source`, que este módulo consome sem alteração). Documentada como contrato
porque separa claramente as três responsabilidades que a spec trata como requisitos distintos:
encontrar sítios, aplicar operadores, e decidir a ordem de combinação.

## Tipos

| Tipo | Campos | Notas |
|---|---|---|
| `Site` | ver `data-model.md` | imutável; comparável por `(node_type, start_byte, end_byte, kind)` (a ordem de descoberta, os operadores elegíveis e o `parent_operator` não fazem parte da identidade) |
| `MutationOperator` | enum `ROR, AOR, LCR, ABS, UOI` | |
| `DiscardReason` | enum `duplicate, compile_error, tle, mle, re, equivalent, unstable` | valores em minúsculas, as chaves de `funnel` no relatório |
| `MutantCandidate` | `problem_id`, `sites: tuple[Site, ...]`, `operators: tuple[tuple[MutationOperator, int], ...]`, `source: str` | texto já mutado, antes de validação; `order` = número de sítios |
| `ValidationOutcome` | `verdict: Verdict \| None`, `discard_reason: DiscardReason \| None`, `deciding_index: int \| None` | exatamente um dos dois primeiros é preenchido; `deciding_index` só quando aceito |
| `Mutant` | ver `data-model.md` | só existe depois de passar por toda a validação |
| `Selection` | `mutants: tuple[Mutant, ...]`, `alert: ExclusionAlert \| None`, `discards: tuple[DiscardRecord, ...]` | resultado de `select_mutants` |

## Funções

| Função | Contrato |
|---|---|
| `find_sites(source: str) -> list[Site]` | Faz o parse com `tree-sitter-cpp` e retorna todos os sítios elegíveis, em ordem de descoberta pré-ordem (R3). Nunca retorna um sítio cujo intervalo de bytes esteja dentro de um nó `comment`, `string_literal` ou `char_literal` (garantido pela própria gramática, R1 — não é uma checagem adicional), nem dentro da condição de um `#if`/`#elif`. Os offsets são bytes UTF-8. |
| `apply(source: str, site: Site, operator: MutationOperator, variant: int) -> str \| None` | Aplica uma variante de um operador a um sítio; `None` quando a variante não se aplica ao sítio (o próprio operador, `!` na frente de um operando aritmético, operador que não é da categoria do sítio) **ou** deixaria o texto igual — não é erro. Cada operador também existe como função pura (`ror`, `aor`, `lcr`, `abs_`, `uoi`) com a mesma assinatura sem o parâmetro `operator`. Preserva byte a byte tudo fora do intervalo do sítio. |
| `first_order_candidates(problem_id: str, source: str, sites: list[Site], *, limit: int \| None = None) -> Iterator[MutantCandidate]` | Para cada sítio, cada operador elegível e cada variante aplicável, nessa ordem (sítio → operador → variante). Preguiçoso: nada além do que é consumido é construído. `limit` devolve só os `limit` primeiros (um prefixo, nunca uma amostra). |
| `higher_order_candidates(source: str, accepted: list[MutantCandidate], order: int) -> Iterator[MutantCandidate]` | `order` é 2 ou 3; combina sítios distintos dos candidatos já aceitos (`accepted`), em ordem determinística fixa (lexicográfica sobre `discovery_index`); nunca usa `random`. |
| `validate(candidate, suite: Suite, limits: ExecutionLimits, slot: int, *, engine: Engine, seen: set[str], runs: int = 6) -> ValidationOutcome` | Aplica FR-005(a–d) numa única compilação e uma primeira execução; só chama `confirm_stability` para o candidato que passaria. `seen` guarda o hash de todo texto já avaliado no problema (incluindo o `AC_ref.cpp`) e recebe o do candidato, qualquer que seja o resultado: nenhum texto é avaliado duas vezes. `Engine` é o par `compile`/`run_suite` de `dataset.validation.engine`, isto é, o motor do módulo `sandbox` sem alteração. |
| `confirm_stability(engine, binary, suite, limits, slot, first: SuiteVerdict, *, runs: int = 6) -> bool` | Reexecuta o **mesmo binário** já compilado até somar `runs` execuções (a primeira, `first`, inclusive) e devolve `False` na primeira divergência de veredito ou de teste decisivo (FR-007). |
| `select_mutants(problem_id: str, source: str, suite: Suite, limits: ExecutionLimits, *, engine: Engine, slot: int = 0, quota: int = 100, progress=None) -> Selection` | Orquestra: primeira ordem até `quota` ou esgotar sítios (FR-003a: consome só o prefixo necessário do fluxo de candidatos); se faltar, ordem 2 e depois 3 (FR-004); devolve o alerta se ainda faltar (FR-009). |

## Garantias (a cobrir por testes, Princípio VI)

1. `find_sites` sobre `vector<pair<int, string>> mb;` não retorna nenhum sítio para o `>>` de
   fechamento de template (caso real do dataset, `175_B`); sobre `x >> 1;` retorna um sítio ROR.
2. `find_sites` sobre um arquivo com `"a<b>>c"` (string) e `// ... < e >> ...` (comentário) não
   retorna nenhum sítio dentro desses dois nós.
3. Duas chamadas de `select_mutants` com o mesmo `source`/`tests`/`limits` produzem exatamente a
   mesma lista de sítios e a mesma ordem de tentativa de candidatos (determinismo por
   construção, sem seed) — a única fonte de variação possível é o veredito do motor de execução
   em si (`confirm_stability` existe exatamente para isso).
4. `select_mutants` nunca retorna mais de 100 mutantes, e nunca um número entre 1 e 99 sem um
   `ExclusionAlert` correspondente.
5. Nenhuma função deste contrato importa `random` nem qualquer gerador de números
   pseudoaleatórios (checagem estática possível via `ruff`/grep, para reforçar D6).
6. Um mesmo texto nunca é avaliado duas vezes para o mesmo problema, e nenhum mutante aceito é
   igual ao `AC_ref.cpp` nem a outro mutante aceito (`tests/mutation/test_uniqueness.py`).
