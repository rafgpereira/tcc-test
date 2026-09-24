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

## Decisões de implementação da primeira história (2026-09-24)

Registradas ao implementar `generate` (primeira ordem). Nenhuma contradiz uma decisão D1–D6 da
spec; cada uma fecha um ponto que a pesquisa deixou em aberto ou torna concreto um contrato.

### R8 — Deslocamentos (`<<`, `>>`) são sítios AOR, trocados só entre si

**Decisão**: `x >> 1` e `cin >> n` são `binary_expression` cujo operador conta como aritmético
(AOR); a variante de `<<` é `>>` e vice-versa, e **nunca** `+ - * / %`. **Motivo**: o teste de
sítios da própria pesquisa (R1) exige que `x >> 1` seja um sítio; trocar o deslocamento por `+`
não tipa para os fluxos `cin >> x` / `cout << x`, que dominam o código de competição, e só geraria
candidatos que não compilam. Os operandos de um deslocamento seguem a regra geral de R9 (custo
aceito: `cout << x` produz candidatos de operando que não compilam e são descartados).

### R9 — Quais operandos são sítios de ABS e UOI, e qual unário é legal

**Decisão** (refina R2): os operandos de um `binary_expression` cujo operador é relacional **ou**
aritmético são sítios de ABS **e** de UOI; os de um conector lógico só de UOI. O unário inserido em
frente de um operando depende do operador pai: relacional `- ! ++ --`; aritmético `- ++ --` (nunca
`!`); lógico só `!`. O `-x` e o `!x` que já existem no código (`unary_expression`) e o
`++`/`--` já existentes (`update_expression`) são sítios UOI de troca (`-`↔`!`, `++`↔`--`); `~` e
`+` unário não. Um operando composto entra entre parênteses depois do unário (`!(a * b) < c`) para o
unário valer para a subexpressão inteira. Uma variante que deixa o texto igual (`0` sobre o
literal `0`) não é mutação. `data-model.md` (tabela de operadores) tinha ABS só sobre operandos de
AOR e não citava `unary_expression`; foi alinhado a esta decisão.

### R10 — Motor: compila uma vez, roda 6 vezes o mesmo binário

**Decisão**: a validação usa o par `compile`/`run_suite` do motor do `sandbox`
(`dataset.validation.engine.Engine`, o mesmo que o módulo de dataset injeta e testa com motor
falso) em vez de `sandbox.judge_source`, que compila e roda uma vez só e não permitiria reexecutar
o binário. As 6 execuções de FR-007 são a primeira execução mais 5 reexecuções **do mesmo binário
compilado uma vez**. **Diferença assumida** em relação à redação "3 checagens independentes de 2
execuções" do reparo de WA (onde cada checagem recompilava): recompilar 3 vezes cada mutante
aceito triplicaria o custo dominante (a compilação, ~1,8 s, ver R13) e não exercita melhor a fonte
real de instabilidade, que é de tempo de execução (leitura de memória não inicializada, margem do
limite de tempo). A força de "6 execuções concordantes, mesmo veredito e mesmo teste decisivo" está
preservada. Se a auditoria futura mostrar mutantes instáveis que recompilar teria pegado, esta
decisão é reaberta.

### R11 — "Duplicata" cobre todo texto já avaliado

**Decisão**: o conjunto de hashes consultado por FR-005(a) contém o `AC_ref.cpp` original e **todo**
texto já avaliado no problema (aceito ou descartado antes), não só os aceitos: um texto já
rejeitado seria rejeitado de novo pelo mesmo motivo, então é contado como `duplicate` e não é
recompilado. Consequência: nenhum mutante aceito é igual ao original nem a outro aceito
(`tests/mutation/test_uniqueness.py`).

### R12 — `generation.json` por problema (fora do zip)

**Decisão**: cada problema fechado em `data/mutants/problems/<id>/` tem um `generation.json` (campos
em `data-model.md`) com o operador/variante de cada mutante e as contagens de descarte por
(ordem, motivo). Sem ele, `report` (US4) não teria de onde recalcular funil e distribuições sem
regerar tudo. Não entra no zip (só os `Mutant_<n>.cpp`) e é o que marca o problema como fechado
para a retomada; um problema excluído (FR-009) fecha só com ele. Não contradiz
`contracts/file-formats.md` ("a proveniência fica só em `mutation_report.json`, agregado"): o
`Mutant_<n>.cpp` continua sem metadado embutido e o pacote versionado continua só com os arquivos
de mutante.

### R13 — Medições (2026-09-24, dataset de `manifests/dataset.manifest.json`)

- **Candidatos de primeira ordem brutos nos 200 `AC_ref.cpp` reais** (gerador desta feature, antes
  de qualquer validação): mediana 274; mínimo 35 (`630_J`); máximo 2.104; 8 problemas abaixo de 100
  e 64 abaixo de 200. Mais folgado que a estimativa de pesquisa de 2.2 da metodologia (mediana ≈146,
  44 abaixo de 100), cujo proxy de operandos era a contagem de identificadores.
- **Compilação** (`189_C`, `bits/stdc++.h`, motor real): 1,75 s, 1,79 s, 1,82 s.
- **Aceitação** (`189_C`, cota 20, primeira ordem): 83 candidatos avaliados, 20 aceitos (24%);
  descartes: 28 equivalentes, 22 erro de compilação, 7 RE, 6 TLE; 359 s e 346 s em duas execuções em
  série que rodaram ao mesmo tempo (uma inflaciona a outra), com **exatamente o mesmo funil e a
  mesma distribuição de operadores** nas duas (mesma sequência de candidatos, sem seed). Extrapolação (não medida): ~30 min por problema de perfil parecido, ~100 h
  para 200 problemas em série. **Pergunta aberta para os autores**: paralelizar `generate` (vários
  `slot`s, resultados consumidos na ordem dos candidatos, como em `validate` do dataset) antes da
  execução completa; a mesma pergunta de desempenho do piloto de ordem superior (R4).
