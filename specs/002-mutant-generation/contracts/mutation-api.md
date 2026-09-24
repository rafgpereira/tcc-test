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
| `Site` | ver `data-model.md` | imutável; comparável por `(node_type, start_byte, end_byte, kind)` |
| `MutationOperator` | enum `ROR, AOR, LCR, ABS, UOI` | |
| `MutantCandidate` | `problem_id`, `sites: list[Site]`, `operators: list[tuple[MutationOperator, int]]`, `source: str` | texto já mutado, antes de validação |
| `ValidationOutcome` | `verdict: Verdict \| None`, `discard_reason: DiscardReason \| None` | `verdict` só é preenchido quando `discard_reason` é `None` |

## Funções

| Função | Contrato |
|---|---|
| `find_sites(source: str) -> list[Site]` | Faz o parse com `tree-sitter-cpp` e retorna todos os sítios elegíveis, em ordem de descoberta pré-ordem (R3). Nunca retorna um sítio cujo intervalo de bytes esteja dentro de um nó `comment`, `string_literal` ou `char_literal` (garantido pela própria gramática, R1 — não é uma checagem adicional). |
| `first_order_candidates(source: str, sites: list[Site]) -> Iterator[MutantCandidate]` | Para cada sítio, gera cada variante de operador legal (R2), na ordem sítio → variante. |
| `higher_order_candidates(source: str, accepted: list[MutantCandidate], order: int) -> Iterator[MutantCandidate]` | `order` é 2 ou 3; combina sítios distintos dos candidatos já aceitos (`accepted`), em ordem determinística fixa (lexicográfica sobre `discovery_index`); nunca usa `random`. |
| `validate(candidate: MutantCandidate, tests: Suite, limits: ExecutionLimits, slot: int) -> ValidationOutcome` | Aplica FR-005(a–d) com uma única execução (compila, roda, compara); só chama `confirm_stability` para o candidato que passaria. |
| `confirm_stability(candidate, tests, limits, slot, *, runs: int = 6) -> bool` | Repete a validação `runs` vezes (FR-007); `True` só se todas concordarem em veredito e teste decisivo. |
| `select_mutants(problem_id: str, source: str, tests: Suite, limits: ExecutionLimits) -> tuple[list[Mutant], ExclusionAlert \| None]` | Orquestra: primeira ordem até 100 ou esgotar sítios (FR-003a trunca se sobrar); se faltar, ordem 2 e depois 3 (FR-004); devolve o alerta se ainda faltar (FR-009). |

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
