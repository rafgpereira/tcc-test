# Research: Geração de Mutantes

**Feature**: `002-mutant-generation` | **Fase**: 0

A maior parte das decisões de desenho desta feature já foi fechada antes do `/speckit.specify`,
numa rodada dedicada de pesquisa e discussão técnica (registrada como D1–D6 em
`spec.md`, seção "Divergências e Decisões sobre a Metodologia", e revisada em
`/speckit.clarify`). Este documento resolve o que ficou como "NEEDS CLARIFICATION" no Technical
Context do plano — todo de natureza técnica/empírica, não de desenho — e registra a verificação
concreta feita nesta fase.

## R1 — `tree-sitter-cpp` resolve mesmo a ambiguidade do `>>` em templates aninhados?

**Decisão**: sim, confirmado empiricamente; usar o campo `operator` do nó `binary_expression`
como o sítio ROR/LCR/AOR, nunca uma busca textual pelo símbolo.

**Verificação feita nesta fase**: instalado `tree-sitter` 0.26.0 + `tree-sitter-cpp` 0.23.4 num
ambiente descartável, e parseados (a) um `AC_ref.cpp` real do dataset
(`175_B`, que contém `vector<pair<int, string>> mb;` literalmente) e (b) um trecho sintético
combinando os casos de risco identificados na pesquisa original.

- Em `175_B/AC_ref.cpp`, a travessia da AST encontrou 20 nós `binary_expression`, entre eles
  `cin >> n` (operador `>>`, um sítio real) — mas **nenhum** nó `binary_expression` foi gerado
  para `vector<pair<int, string>> mb;`: o parser reconhece o `>>` ali como parte da sintaxe de
  tipo (fechamento de dois templates aninhados), não como operador, exatamente como esperado.
- No trecho sintético, `vector<vector<int>> grid;` (mesmo arquivo que também tem `return x >> 1;`
  mais abaixo) confirma a mesma disambiguação **dentro do mesmo arquivo**: o `>>` de tipo não
  gera `binary_expression`, o `>>` de operador (right-shift) gera.
- O mesmo trecho confirma que `string_literal` (`"a<b>>c"`) e `comment` (`// ... < e >> aqui`)
  são nós de tipo próprio, nunca aparecendo como filhos de um `binary_expression` — um mutador
  restrito a nós `binary_expression`/`unary_expression`/`update_expression` estruturalmente não
  pode tocar o conteúdo de um literal ou de um comentário.
- Cada `binary_expression` tem um campo nomeado `operator` (`node.child_by_field_name("operator")`),
  cujo `.type` é o próprio token do operador (`"<"`, `"+"`, `"&&"`, etc.) — não é preciso inferir o
  operador por diferença de posição entre `left` e `right`.

**Alternativas reconsideradas**: nenhuma — a pesquisa original já tinha descartado `libclang`
(exige resolver headers) e regex/`UniversalMutator` (risco de mutar literais/comentários); esta
verificação só confirma que a escolha funciona no C++ real do dataset, não neste projeto.

## R2 — Como delimitar os sítios de ABS e UOI sem informação de tipos?

**Decisão**: os sítios de ABS e UOI são os operandos (`left` e `right`) de todo
`binary_expression` já elegível para ROR ou AOR — não uma busca separada por "toda subexpressão
numérica" (que exigiria inferência de tipo, indisponível num parser puramente sintático).

**Racional**: um operando de um operador aritmético ou relacional é, por construção sintática, um
valor numérico — não é preciso resolver o tipo declarado da variável para saber isso. Isso dá,
por `binary_expression` elegível a ROR/AOR: 1 sítio de substituição de operador **mais** até 2
sítios de operando (ABS ou UOI, um por lado). Concretamente:

- **ABS** em um operando: emite três variantes (força a subexpressão a `0`, a `+abs(...)` e a
  `-abs(...)`) — a mesma lista de três casos do operador original de Offutt et al.
- **UOI** em um operando: insere `-`, `!`, `++` ou `--` na frente, restrito ao que é sintaticamente
  legal para o tipo de nó do operando (`!` só faz sentido para os sítios de LCR/ROR, `-`/`++`/`--`
  para os de AOR — a checagem de legalidade sintática, não semântica, é suficiente; um candidato
  ilegal simplesmente não compila e é descartado pelo critério já existente, FR-005(b)).
- Nós `update_expression` (`++x`, `x--`) já existentes no código-fonte são, por si só, sítios de
  ROR/AOR? Não — são tratados como sítios UOI próprios (substituir `++`↔`--`), verificado
  empiricamente (nó `update_expression` distinto de `binary_expression`, cobre prefixo e sufixo).

**Custo aceito conscientemente**: um candidato ABS/UOI aplicado a um operando cujo tipo real não
é numérico (ex.: `std::string`) simplesmente não compila — é o mesmo custo de eficiência (não de
correção) já aceito na spec (seção "Assumptions"), pago porque o parser puramente sintático não
resolve tipos. Não é esperado que seja frequente: os operandos de operadores aritméticos e
relacionais em código de competição são, na prática observada, quase sempre numéricos.

## R3 — Ordem determinística de descoberta de sítios

**Decisão**: pré-ordem (*pre-order*) da travessia padrão da AST de `tree-sitter`, index 0 em
`AC_ref.cpp`, avançando pelos filhos na ordem em que o parser os retorna. Dentro de um mesmo
`binary_expression`, a ordem interna é: sítio do operador (ROR/AOR/LCR), depois sítio do operando
esquerdo (ABS, depois UOI), depois sítio do operando direito (ABS, depois UOI). Essa ordem é
100% determinística para um mesmo arquivo-fonte (a gramática de `tree-sitter-cpp` não introduz
não-determinismo), o que satisfaz FR-003a, FR-004 e FR-011 sem precisar de nenhuma seed.

## R4 — Risco de desempenho da busca combinatória de ordem superior

**Situação**: FR-004 diz "combinar... até completar 100 ou esgotar as combinações de pares
possíveis". Para um problema com `n` sítios de primeira ordem válidos e faltando `k < 100 - n`,
o espaço de pares é `C(n, 2)`, que cresce rápido (`n=70` → 2.415 pares). Cada tentativa exige, na
pior análise, compilar e rodar a suíte oficial pelo menos uma vez (barato: descarta já na
primeira execução se não compilar, TLE/MLE/RE ou for equivalente) — só os candidatos que
sobrevivem a esse primeiro filtro pagam o custo de 6 execuções concordantes (FR-007). Isso já
limita bastante o custo esperado (a maioria dos pares é descartada na primeira tentativa, barata),
mas o **pior caso** (poucos pares sobrevivendo, exigindo percorrer uma fração grande de `C(n,2)`
antes de fechar `k`) não está medido.

**Decisão**: não fixar um número de tentativas a priori. Medir com um piloto durante a
implementação — no mesmo espírito do piloto do módulo de dataset (`validate --target 10`, que
mediu a fração real de WA antes de comprometer a estimativa de tempo total). O piloto deste
módulo roda a geração sobre uma amostra pequena de problemas que já se sabe (pela estimativa da
spec, seção 2.2) precisarem de ordem superior, mede o tempo e a fração de pares/trios válidos
encontrados, e só então se decide se um orçamento de tentativas é necessário. Se for, um
problema que esgota o orçamento sem fechar 100 é tratado exatamente como "esgotar as combinações
possíveis" (FR-009) — a interpretação operacional de "esgotar" passa a incluir o orçamento
medido, e isso é registrado como uma divergência/decisão nova no ciclo da implementação
(Princípio XI), não decidido especulativamente aqui.

## R5 — Idempotência e retomada (Princípio VII)

**Decisão**: mesmo padrão já usado no módulo de dataset — cada problema é processado
isoladamente, seus mutantes escritos primeiro em `data/mutants/building/<problem_id>/` e só
movidos atomicamente (`os.replace` por diretório, ou arquivo a arquivo com um marcador de
conclusão) para `data/mutants/<problem_id>/` quando os 100 mutantes (ou a exclusão registrada,
FR-009) estiverem decididos. Uma interrupção no meio de um problema descarta o `building/`
parcial e o refaz do zero na retomada, sem tocar nos problemas já completos — não há
necessidade de checkpoint mais fino dentro de um problema, porque o motor de execução já é o
gargalo (não a orquestração).

## R6 — Formato e nomenclatura dos arquivos de mutante

**Decisão**: `Mutant_1.cpp` a `Mutant_100.cpp` por problema (nunca reaproveitando o prefixo
`WA_`, para não confundir com falhas reais na leitura de diretório por módulos futuros),
numerados na ordem final de aceitação (primeira ordem primeiro, depois ordem superior, na ordem
de descoberta de R3) — mesmo padrão de numeração sequencial 1–100 já usado para `WA_<n>.cpp`.

## R7 — Dependências: versões

**Decisão**: `tree-sitter>=0.26,<0.27` e `tree-sitter-cpp>=0.23,<0.24` (as versões verificadas
nesta fase), pinadas no `uv.lock` na implementação — nenhuma outra dependência nova.
