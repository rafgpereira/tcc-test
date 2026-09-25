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

> **Resolvido em R18 (2026-09-24)**: piloto medido nos três problemas mais esparsos; sem orçamento de
> tentativas. O texto abaixo é o da fase de pesquisa.

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
conclusão) para `data/mutants/problems/<problem_id>/` quando os 100 mutantes (ou a exclusão registrada,
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

### R13 (complemento) — Geração completa de `189_C` (2026-09-24, executada pelos autores)

`generate --problem 189_C` (cota 100, primeira ordem, motor real, em série): **795 s** (13 min 16 s);
100 aceitos após avaliar 241 candidatos (**41,5%** de aceitação no conjunto, contra 24% nos
primeiros 83); descartados 141: 64 erro de compilação, 48 equivalentes, 18 RE, 11 TLE; ~3,3 s por
candidato avaliado. **Substitui a extrapolação anterior** (≈30 min por problema e ≈100 h no total,
feita a partir dos 24% iniciais): com esse problema como referência, 200 problemas em série são
**≈44 h** (200 × 795 s), sem contar os problemas que precisarem de ordem superior. Observação de
qualidade (não decidida): o `Mutant_1.cpp` é `0 >> n` no lugar de `cin >> n`, isto é, o ABS aceitou
um mutante que simplesmente não lê a entrada; é válido (WA) mas pouco informativo, e sítios de
E/S de fluxo (`cin >>`, `cout <<`) respondem por parte dos 64 erros de compilação. Decisão dos
autores: manter (sem novo filtro) ou excluir o ABS/UOI dos operandos de `cin`/`cout`.

### R14 — Paralelização de `generate` (proposta de 2026-09-24, aprovada, implementada e validada no mesmo dia)

**Desenho: paralelismo entre problemas, não dentro de um problema.** `generate --workers N`
(padrão: metade das CPUs, mínimo 1, como em `validate`/`audit` do módulo de dataset; `N=1` é o
comportamento atual). Cada problema é uma tarefa independente e inteira: um trabalhador roda
`select_mutants` (o código de hoje, sem alteração) no **seu próprio `slot`** do motor.

- **Mecanismo reaproveitado** de `dataset.validation.runtime.PoolRuntime`: `ProcessPoolExecutor`
  com contexto `fork`, uma fila de `slot`s, `initializer` que pega um `slot`, prepara o diretório de
  trabalho (`isolation.prepare_slot_workdir`) e constrói `real_engine()`; `kill_slot_processes` de
  todos os `slot`s ao começar e ao terminar; SIGINT ignorado nos filhos (o processo principal trata
  Ctrl+C e limpa). Novo arquivo `src/mutation/runtime.py` (`PoolRuntime`, `InlineRuntime` e
  `ThreadRuntime` para os testes, com a mesma interface).
- **Por que entre problemas e não entre candidatos** (o que `validate` faz): são 200 tarefas
  independentes para 4 a 7 trabalhadores, então a ocupação é total sem janela de candidatos em voo
  nem candidatos desperdiçados ao atingir a cota; o resultado de cada problema é exatamente o de
  hoje por construção (a ordem dos candidatos, o conjunto `seen` e o corte em 100 são internos ao
  problema), então **o número de trabalhadores não pode mudar o conjunto de mutantes** — só
  a ordem em que as linhas de progresso aparecem. Limite assumido: um problema isolado (`--problem
  X`, ou a cauda de um problema difícil de ordem superior) continua em série.
- **Persistência só no processo principal**: o trabalhador devolve o `Selection` (dataclasses
  imutáveis, serializáveis) e o processo principal grava (`building/` → `problems/`, igual a hoje),
  à medida que os problemas terminam; uma interrupção nunca deixa problema parcial em `problems/`.
  `InfraError` num trabalhador cancela o restante e sai com código `3`; Ctrl+C sai com `130`; ambos
  retomáveis como hoje.
- **Estimativa** (a partir dos 795 s medidos em `189_C`, supondo-o típico): 200 × 795 s ≈ 44 h em
  série; ≈ 11 h com 4 trabalhadores (padrão em 8 CPUs) e ≈ 6,3 h com 7, no ideal. Não medido para os
  outros problemas.
- **Risco a medir, não assumir**: sob carga, um veredito de margem (tempo no limiar) pode mudar. O
  motor mede tempo de CPU, não de relógio, o que atenua, e as 6 execuções concordantes protegem cada
  aceite; mesmo assim, a validação da proposta compara, para 8 problemas, o resultado com `--workers 1`
  e com `--workers 4` (hash a hash) e registra a taxa de divergência aqui.
- **Tarefas**: T059 a T064 em `tasks.md`; T059–T062 e T064 implementadas (`src/mutation/runtime.py`,
  `--workers`); **T063 (medir 8 problemas com `--workers 1` e `4`) é execução dos autores**.
  Com o filtro de R16 o tempo por problema também cai (menos candidatos que não compilam, e cada
  um custava 4 compilações): as estimativas de horas acima usam os 795 s de antes do filtro e são,
  portanto, conservadoras.

### R15 — Estabilidade entre rodadas independentes (2026-09-24, teste da simplificação de R10)

**Pergunta**: seis execuções sobre um único binário compilado (R10) bastam para que duas rodadas
independentes de `generate` aceitem o mesmo conjunto, ou o conjunto diverge como divergiram as WA
do dataset (D13/D18/D19)? **Medição**: `generate --problem 189_C` duas vezes, cada uma sobre um
`data/mutants/problems/189_C` vazio, sem reaproveitar nada da outra (a primeira, dos autores, 795 s;
a segunda, minha, 831 s; código sem alteração entre elas). Resultado:

| Comparação | Resultado |
|---|---|
| Arquivos `Mutant_1.cpp` a `Mutant_100.cpp` | 100 de 100 idênticos (`diff -rq`) |
| SHA-256 por mutante, na mesma posição | 100 de 100 iguais; hash do conjunto ordenado igual nas duas rodadas |
| `generation.json` (operador/variante de cada um, descartes por motivo) | idêntico: 64 erro de compilação, 48 equivalentes, 18 RE, 11 TLE |
| **Taxa de divergência** | **0 de 100 mutantes (0%)**; 0 candidatos com veredito diferente entre as rodadas |

**Leitura**: nenhuma instabilidade apareceu num problema em que os candidatos descartados
incluem 11 TLE e 18 RE (os casos de margem que causaram a divergência no dataset). Isso sustenta
R10 **para este problema**, mas é uma amostra de um problema e duas rodadas (um erro de 0/100 não
prova taxa zero): a comparação deve ser repetida na validação de R14 (8 problemas, `--workers 1`
contra `--workers 4`) e, com mais peso, na execução final, comparando o pacote com uma segunda
geração. Se alguma divergência aparecer, R10 é reaberto (recompilar entre as verificações).

### R16 — Redução dos erros de compilação (2026-09-24, a pedido dos autores)

**Medição da causa** (todos os candidatos de primeira ordem de 5 problemas reais — `189_C`,
`265_D`, `171_F`, `1005_C`, `630_L` — compilados um a um com o motor real): **353 de 1.463 (24%) não
compilam**. Os erros dominantes: (1) E/S de fluxo — operador `<<`/`>>` trocado, ou `abs`/`-`/`++`
na frente de `cin`/`cout`/`endl`/da variável lida: `abs(std::ostream&)`, `abs(std::istream&)`,
`no match for operator>>`, **~65% do total**; (2) `++`/`--` na frente de algo que não é atribuível
(`lvalue required as increment/decrement operand`, 94 casos); (3) `abs` de tamanho sem sinal
(`abs(size_type)` ambíguo, 14 casos). Custo adicional: como o motor tenta 4 padrões da cascata,
**um erro de compilação custa 4 compilações** (~7 s), não uma.

**Decisão** (só sintaxe, sem inferência de tipos, R9 refinado): não são sítios (a) o operador e o
operando esquerdo de uma cadeia de `<<`/`>>` que começa em `cin`/`cout`/`cerr`/`clog` (com ou sem
`std::`), nem o operando direito de `cin >>`; o operando direito de `cout <<` (o valor impresso)
continua; (b) operandos que são literal de string ou `endl`/`flush`/`ends`; (c) ABS sobre
`.size()`/`.length()`/`sizeof` (sem sinal: ambíguo ou equivalente); (d) `++`/`--` só na frente de
operando atribuível (identificador, subscrito, membro, ponteiro, parênteses). Expressões dentro de
uma instrução de fluxo (`cout << (a + b)`) mantêm os seus sítios.

**Efeito medido** (mesmos problemas, motor real; a regra (c) ainda não existia nesta medição):

| Problema | Candidatos antes → depois | Não compilam antes → depois | Que compilam antes → depois |
|---|---|---|---|
| `189_C` | 259 → 172 | 76 (29%) → **0 (0%)** | 183 → 172 |
| `630_L` | 315 → 224 | 88 (28%) → **2 (1%)** | 227 → 222 |
| `171_F` | 292 → 233 | 94 (32%) → **39 (17%)** | 198 → 194 |

Erros restantes em `171_F`: sobretudo `abs(size_type)` (regra (c), acrescentada depois da medição) e
variáveis `stringstream` (`ss >> x`, `ss << x`), que só um tipo revelaria. **Custo em qualidade**:
os candidatos que compilam caíram de 3% a 6% (11, 5 e 4 por problema): são os poucos que mexiam na
E/S e compilavam (ex.: `0 >> n` no lugar de `cin >> n`, mutante que não lê a entrada, R13), que
saem por serem pouco informativos. **Consequência para a cota**: o número de candidatos brutos nos
200 `AC_ref.cpp` cai (mediana 274 → 198; mínimo 26; **34 problemas abaixo de 100**, antes 8; 102
abaixo de 200), porque o que saiu era quase só o que não compilaria; o conjunto de candidatos
**válidos** cai pouco (3–6%), então o risco de precisar de ordem superior sobe um pouco, e a
medição por problema (`generation.json`, relatório) é quem mostra quantos. O `Mutant_1.cpp` de
`189_C` deixa de ser `0 >> n`.

### R14 (validação, T063) — `--workers 1` contra `--workers 4` em 8 problemas (2026-09-24)

**Execução** (feita por mim, a pedido dos autores, uma rodada depois da outra, sem outra carga
relevante na máquina, código com o filtro de R16): `generate` sobre 8 problemas —
`1196_D1`, `1278_B`, `1288_C`, `265_D`, `523_C`, `630_G`, `719_A`, `967_C` (os de menores `testes.json`
com pelo menos 230 candidatos brutos) — duas vezes, cada uma sobre `data/mutants` vazio; máquina:
Intel i7-1165G7 (4 núcleos, 8 threads).

| Comparação | Resultado |
|---|---|
| Arquivos (`Mutant_<n>.cpp` e `generation.json`) das duas rodadas | **idênticos** (`diff -rq`) |
| SHA-256 por mutante, mesma posição | **800 de 800 iguais** (8 problemas × 100), hash do conjunto ordenado igual em cada problema |
| Funil de descartes por problema | idêntico nos 8 (incluindo 70 TLE, 77 RE e 6 MLE entre os descartados, os casos de margem) |
| **Taxa de divergência** | **0 de 800 mutantes (0%)** |
| Tempo (relógio) | **3.520 s** com `--workers 1`; **1.700 s** com `--workers 4`: **aceleração de 2,07×**, não 4× |

**Leitura**: (1) o número de trabalhadores não mudou nenhum mutante, como previsto por construção
(R14) e por R10/R15 (estabilidade entre execuções); junto com R15 são 900 mutantes comparados entre
execuções independentes, nenhuma divergência. (2) O ganho real é de ~2×: cada problema ficou ~1,8×
mais lento sob 4 trabalhadores (ex.: `1196_D1`, 404 s → 746 s), porque a máquina tem 4 núcleos
físicos (8 threads) e é um portátil sujeito a redução de frequência; e o fim da rodada tem cauda
(as duas ondas de 4 problemas). Em outra máquina o ganho será outro; `--workers` é regulável.
(3) **Extrapolação para os 200 problemas** (não medida; o tempo médio de 440 s por problema
em série vem destes 8, que são de testes pequenos): ≈ 24 h em série, ≈ 12 h com 4 trabalhadores,
sem contar os problemas que precisarem de ordem superior (US2). Substitui as estimativas de 44 h/11 h
(feitas sobre `189_C` antes do filtro de R16).

### R16 (complemento) — Erros de compilação nos 8 problemas da validação de R14

Nas 8 gerações completas de R14: **63 erros de compilação em 1.415 candidatos avaliados
(4,5%)**, contra 24% antes do filtro (R16); aceitação **56,5%** (800 de 1.415, contra 41,5% em
`189_C` antes do filtro). Por problema, de 0 (`265_D`) a 26 (`967_C`) erros. Descartes totais nos 8:
63 não compilam, 466 equivalentes, 77 RE, 70 TLE, 6 MLE (o que restou de falhas são os mutantes
equivalentes, que só a suíte oficial revela).

### R17 — Ordem superior: decisões de implementação (2026-09-24, História 2)

Implementa FR-004, FR-004a e FR-009 sem contradizer D3/D4/D6; cada ponto abaixo fecha algo que o
texto deixava em aberto.

- **Base das combinações**: só os mutantes de **primeira ordem aceitos**, na ordem de aceitação
  (que é a ordem de descoberta dos sítios, R3). Um trio combina três mutantes de primeira ordem,
  nunca um par com outro mutante; pares e trios usam a mesma base, fixada antes de começar a
  ordem 2. A ordem de tentativa é `itertools.combinations` sobre essa lista (o primeiro mutante
  varia mais devagar): `(1,2), (1,3), ... (2,3), ...`.
- **Sítios distintos e disjuntos**: a combinação é descartada (nem chega à validação) se dois
  sítios coincidem (duas variantes do mesmo sítio) **ou se seus intervalos de bytes se
  sobrepõem** — o operando esquerdo `(a + b)` de `(a + b) * c` contém o sítio do `+`, e mudar os
  dois ao mesmo tempo não tem significado. O texto resulta de aplicar as mudanças **da direita para
  a esquerda**, para os deslocamentos de bytes dos sítios ainda por aplicar continuarem válidos.
- **Nada novo na validação**: um par cujas duas mudanças se cancelam cai como `equivalent` pelo
  mesmo caminho da primeira ordem; texto repetido cai como `duplicate` (R11); o funil registra
  cada descarte com a ordem (2 ou 3) do candidato.
- **Esgotamento e alerta**: se os pares e depois os trios se esgotam sem chegar a 100, o problema é
  excluído: `select_mutants` devolve `Selection.alert` (`ExclusionAlert` com o que se alcançou e a
  maior ordem tentada, 3 quando ambas se esgotaram), **nada** de `Mutant_<n>.cpp` é gravado e o
  `generation.json` (`status: excluded`) fecha o problema. `generate` termina com código `0`
  nesse caso (uma exclusão é um resultado, FR-009a, não uma falha); o conceito de problema
  "falho" e a exceção provisória `HigherOrderNotAvailable` da primeira história deixaram de existir.
- **Orçamento de tentativas**: `select_mutants(max_attempts=...)` limita quantos candidatos de
  ordem superior são tentados (`None` = sem limite); esgotá-lo é tratado como esgotar as
  combinações (alerta com a maior ordem tentada). O limite existe no código desde já, testado;
  se a constante correspondente entra em `config.py` é a decisão do piloto de R4 (registrado em
  R18).
- **Custo teórico**: para `n` mutantes de primeira ordem há até `C(n,2)` pares e `C(n,3)` trios
  (com `n = 99`, 4.851 e 156.849); cada candidato custa uma compilação (~1,8 s, mais 4 se não
  compilar). É o risco que R4 descreve; o piloto mede.

### R18 — Piloto de desempenho da ordem superior (T033; resolve R4) — 2026-09-24

**Execução** (feita por mim, a pedido dos autores): `generate --workers 3` sobre os três problemas
com **menos candidatos de primeira ordem** dos 200 (após o filtro de R16): `569_A` (26 candidatos
brutos), `630_J` (31) e `270_B` (39); motor real, revisão `5a0f7cc` mais as alterações da História 2
(não commitadas); os três em paralelo (um por `slot`).

| Problema | Candidatos brutos | 1ª ordem aceitos | Pares aceitos | Pares tentados | Trios | Descartes | Tempo |
|---|---|---|---|---|---|---|---|
| `569_A` | 26 | 17 | 83 | 83 | 0 | 3 equivalentes + 6 TLE (1ª ordem) | 371 s |
| `630_J` | 31 | 23 | 77 | 96 | 0 | 7 equiv. + 1 RE (1ª); 19 equiv. (pares) | 408 s |
| `270_B` | 39 | 24 | 76 | 84 | 0 | 8 equiv. + 7 TLE (1ª); 8 TLE (pares) | 425 s |

**Leitura**: (1) os três problemas mais esparsos do dataset fecham **só com pares** (nenhum
precisou de trio e nenhum foi excluído, 0 alertas); (2) 76% a 83% dos mutantes deles são de
**segunda ordem** — o custo em qualidade de FR-004 que a metodologia (2.4) já assumia, agora
medido; (3) a taxa de aceitação dos pares é alta (77 de 96, 83 de 83, 76 de 84: 90% no conjunto),
porque os pares partem de mutantes que já sabidamente são WA; (4) o custo por candidato tentado é
~4 s (compilar + 6 execuções), e o problema inteiro levou de 6 a 7 minutos, no mesmo patamar dos
problemas de primeira ordem (R14: média de 440 s).

**Decisão sobre o orçamento de tentativas (R4)**: **não é necessário** para o dataset atual. O
espaço só seria proibitivo se `n` fosse grande e a taxa de sucesso dos pares muito baixa, e o
piloto mostra o contrário: com `n` pequeno o espaço é pequeno (`C(26,2) = 325` pares,
`C(26,3) = 2.600` trios, no máximo ~3.000 candidatos, ~3 h no pior caso e só se todos os pares
falhassem), e com `n` grande faltam poucos mutantes e os pares aceitos chegam rápido.
`max_attempts` fica no código (testado, `None`), sem constante em `config.py`: introduzi-lo só por
precaução seria uma regra a justificar sem medida que a sustente. **Reabrir se** a execução
completa mostrar algum problema com mais de 1.000 candidatos de ordem superior tentados sem fechar
(o `generation.json` traz o funil por ordem).

**Limite da amostra**: 3 problemas, os mais esparsos por contagem bruta de candidatos, não por
contagem de aceitos; um problema com muitos candidatos que são quase todos equivalentes (aceitos
poucos) não foi exercitado. O relatório da execução completa mostra isso.

### R19 — Recuperação: garantias, falha encontrada e validação real (2026-09-24, a pedido dos autores)

**Garantias** (Princípio VII, R5): (1) um problema só existe em `data/mutants/problems/` completo:
é montado em `building/` e fechado por **uma** renomeação atômica; (2) o que estava em andamento é
refeito do zero e só isso (`generate` grava um problema apenas quando ele termina; nada de um
problema em voo estava em disco); (3) um problema fechado nunca é reescrito nem tocado; (4) o
resultado depois de retomar é **o mesmo, byte a byte**, de uma execução nunca interrompida, porque a
ordem dos candidatos não depende de quando se parou.

**Falha encontrada ao validar** (motor real, `--workers 2`, SIGINT com 2 problemas em voo): o
container **não saía** (40 s depois ainda rodava): `PoolRuntime.close` usava `shutdown(wait=True)`,
que espera os problemas em voo terminarem (minutos), e os trabalhadores ignoram SIGINT. Ctrl+C
parecia travado e, com `docker stop` (10 s de tolerância), acabava em SIGKILL. **Correção**:
`close(abort=True)` em qualquer exceção (Ctrl+C, SIGTERM, falha do motor) encerra os trabalhadores e
os processos dos `slot`s na hora.

**Endurecimentos acrescentados** (nenhum muda o resultado de uma execução normal): (a)
`persistence.check_closed`: um problema fechado que perdeu ou teve um `Mutant_<n>.cpp` alterado é
apontado (`DAMAGED`, código `1`), não pulado em silêncio, e `package` se recusa; (b)
`persistence.exclusive_run`: `flock` em `data/mutants/.lock` impede dois `generate` ao mesmo tempo
(o segundo apagaria o `building/` do primeiro no reset inicial); o SO solta a trava se o processo
morre, então nunca fica obsoleta; (c) `package` se recusa se faltarem problemas do dataset
(`--allow-partial` só para teste): um pacote a versionar tem de ser o de uma execução inteira.

**Validação automatizada** (`tests/mutation/test_recovery.py`, 14 testes, motor falso; e um teste
de integração com o pool real): interrupção entre problemas, no meio da gravação de um problema, por
`kill -9` (sobras em `building/` e arquivo temporário de escrita atômica), com 2 e 4 problemas em
voo e repetida 3 vezes — em todos, o resultado depois de retomar é idêntico ao de uma execução
limpa e os problemas já fechados não mudam nem de `mtime`; dois `generate` simultâneos; problema
danificado; pasta recebida do pacote.

**Validação real** (motor real, dois problemas `630_G` e `719_A`, executada por mim):

| Cenário | Resultado |
|---|---|
| E1: SIGINT com `--workers 2`, 60 s depois de começar | container encerrou em **1 s**, código 130, `problems/` vazio e `building/` vazio (nada pela metade) |
| E2: `--workers 1`, SIGKILL 20 s depois de `630_G` fechar (durante `719_A`) | `problems/` = só `630_G` (completo), sem `building/`, sem processos remanescentes |
| E3: retomar o mesmo comando | `630_G: already generated, skipped` (mesmo hash do conjunto e mesmo `mtime` de antes do kill), `719_A` gerado (100 mutantes, 386 s), `building/` vazio; o funil de `719_A` (2 compilação, 28 equivalentes, 1 RE, 12 TLE) é o mesmo da geração sem interrupção de R14 |

Perda observada: só o trabalho do problema em andamento no instante do kill (~5 min de CPU de
`719_A`), como previsto; nenhum problema fechado foi perdido ou refeito.

### R20 — `report`, `package` e `verify`: decisões (2026-09-24)

- **Revisão do código no relatório — retirada (2026-09-25)**: a primeira versão tinha `code_revision` e
  a opção `--code-revision "$(git rev-parse HEAD)"` (os contêineres não montam `.git`, então o
  `git` não funciona lá dentro, contra o que T046 previa). **Os autores pediram para remover**: o
  módulo de dataset não grava revisão nenhuma e os comandos ficam mais limpos. O campo saiu do
  relatório, a opção saiu de `report` e `package`, e FR-013 foi revisado. A rastreabilidade do
  código passa a ser o commit que versiona os artefatos; o relatório segue ligado à versão exata
  do dataset por `dataset_manifest_sha256`.
- **`problems` no relatório** (acréscimo ao contrato): `closed`, `complete`, `first_order_only`,
  `higher_order`, `excluded`. É o número que a metodologia (2.6) compara com a estimativa de que ao
  menos 75% dos problemas fecham só de primeira ordem (SC-003); sem ele, T052 teria de recontá-lo
  à mão.
- **`report` confere o dataset** (`dataset_manifest_sha256`): recusa-se se `data/dataset` divergir
  do manifesto, como `generate`.
- **`package`** recusa: dataset divergente, revisão malformada, `building/` pendente, problema
  danificado, problemas do dataset ainda não gerados (`--allow-partial`); grava zip → manifesto →
  relatório (nessa ordem, o relatório reflete o que foi empacotado). Rodar duas vezes dá os mesmos
  bytes (medido: mesmo SHA-256 do zip em duas execuções reais).
- **Layout do zip** `mutants/problems/<id>/Mutant_<n>.cpp` (fluxo de circulação, cli.md): `unzip`
  cai no caminho de consumo. `verify --extracted` só considera `Mutant_*.cpp` de `problems/<id>/`.
- **Execução real** (2 problemas reais, `--allow-partial`, revisão `5c726d8+dirty`): `report`,
  `package`, `verify` `OK`; `unzip` em `data/` e `verify --extracted data/mutants` `OK`; um byte
  alterado aponta `changed: mutants/problems/630_G/Mutant_3.cpp` e `FAIL`; `generate` sobre a
  pasta recebida pulou o problema (`already generated, skipped`). Resultado apagado depois: nada
  disso é o pacote da execução final.

### R21 — Execução final da geração sobre os 200 problemas (2026-09-24/25, executada pelos autores)

`generate --workers 4` sobre os 200 problemas do dataset (commit `8a45e6c`), computador de 4 núcleos e
8 threads. Números lidos do log do autor e dos `generation.json` (nada foi recalculado): o relatório
(`report`) e o pacote (`package`, `verify`) **ainda não foram gerados**; estes valores entram nele.

| Medida | Valor |
|---|---|
| Resultado | `done: 200 generated, 0 skipped, 0 excluded`, código 0; 0 `DAMAGED`, 0 `ALERT`, `building/` vazio |
| Problemas | 200 completos, **0 excluídos** (SC-001 atingido); 20.000 mutantes, 20.200 arquivos (200 × 101) |
| Tempo | **~7 h 26 min** de relógio (20:19 do dia 24 às 03:45 do dia 25, pelos horários do log), contra ~12 h extrapoladas em R14 |
| Candidatos avaliados | 34.355; aceitos 20.000 (**58,2%**) |
| Descartes (14.355) | 8.997 equivalentes (26,2% dos avaliados), 2.014 RE, 1.816 TLE, **1.334 não compilam (3,9%)**, 166 MLE, 28 instáveis (0,08%), 0 duplicatas |
| Mutantes por ordem | 1ª: 16.930 (84,7%); 2ª: 3.061 (15,3%); 3ª: **9** (só em `981_B`) |
| Problemas por forma de fechar | **113 só com primeira ordem (56,5%)**; 87 com ordem superior (43,5%) |
| Operadores usados (em 23.079 usos) | UOI 8.580; ROR 6.332; ABS 5.372; AOR 2.624; LCR 171 |
| Ordem superior por problema | nos 87 problemas com ela, mediana de 35 mutantes de ordem superior; 24 problemas com 50 ou mais; máximo 85 (`981_B`, com 15 de 1ª, 76 de 2ª e 9 de 3ª) |

**SC-003 (estimativa de ≥75% dos problemas só com primeira ordem) não se confirmou**: 56,5%. A
estimativa de pesquisa (2.2 da metodologia) contava sítios brutos, antes do filtro de fluxo de R16
e antes de descontar os 26% de candidatos equivalentes; a medição real desta rodada substitui a
estimativa. Isso **não** viola a feature (FR-004 existe para esse caso; nenhum problema foi excluído),
mas muda o que o texto do TCC deve dizer: 15,3% dos mutantes são de ordem superior, e o ganho de
realismo de um mutante de uma alteração só vale para 84,7% deles.

**Achado sobre o log**: o tempo `N s` impresso ao fim de cada problema **inclui a espera na fila** do
pool (é contado desde a submissão, e até `2 × workers` problemas ficam submetidos), então com
`--workers > 1` **não** mede o tempo de cada problema (a soma dos tempos impressos é 82 h, para 7,4 h
de relógio). O tempo total de relógio acima é o confiável. Corrigir o cronômetro (contar a partir do
início da tarefa no trabalhador) é pendência de código, não de dados.

### R22 — Verificação de consistência entre artefatos (`python -m cli check`) — 2026-09-25

**Origem**: os autores notaram que (a) `dataset verify` sem `--extracted` só confere o **zip** (editar
ou apagar um `AC_ref.cpp` em `data/dataset/` continuava dando `OK`; reproduzido numa cópia, R21 e
resposta de 2026-09-25) e (b) nada conferia o conjunto — dataset e mutantes 1:1, com todos os arquivos
de cada problema —, que precisa estar certo antes de a execução final extrair os dados do
experimento e antes do envio às IAs. Confirmado também que `data/dataset/` só existe depois de um
`unzip` manual (nenhum comando a cria), o que faltava no tutorial do dataset.

**Decisões** (contrato e referência viva em `docs/verificacao-consistencia.md`):

- **Comando do pacote `cli`** (`python -m cli check`, `src/cli/`; primeiro foi `scripts/check_consistency.py`
  e passou para `src/cli` em 2026-09-25 para ter nome limpo, como os demais comandos), só biblioteca
  padrão, só lê, serviço `app`; não pertence a um módulo porque cruza os artefatos de vários (e dos
  futuros: testes das IAs).
- **Nomes e contagens, não conteúdo** (pedido dos autores): pastas, arquivos, `100` WAs e `100`
  mutantes por problema, nada além do esperado, nomes iguais aos que o manifesto lista; a **relação
  1:1** dataset × mutantes nos dois sentidos (a verificação "de volta": pasta de mutantes sem
  problema no dataset é falha). `--deep` acrescenta os SHA-256 de todos os arquivos e dos zips
  contra os manifestos, para o momento em que os dados são consumidos.
- **Extensível por `Layer`**: um módulo novo declara a pasta, os grupos de nomes e o manifesto; a
  relação 1:1 com o dataset é conferida sem outra mudança (testado com uma camada fictícia de
  "testes da IA").
- **Contagem esperada de problemas vem do manifesto do dataset** (`problem_count`), não de uma
  constante; excluído por FR-009 é `[AVISO]`; manifesto de mutantes ausente é `[AVISO]` (só existe
  depois de `package`); `building/` não vazio é falha.
- **Ainda não confere** (decisão dos autores: não se preocupar): se os mutantes vieram do `AC_ref`
  atual do dataset (`generation.json` não guarda o hash do `AC_ref`).
- **Como portão**: `--deep` com código `0` é a condição para etapas que consomem os dados; o futuro
  orquestrador (`src/cli/`) chamará `run_checks`; mover o código para `src/` fica para essa feature.

**Execução real** (dataset e mutantes reais, 2026-09-25, antes de `report`/`package`): 0,6 s, `OK`,
1 aviso (sem manifesto de mutantes ainda); dataset 200 pastas (manifesto: 200), `200/200` em cada arquivo
fixo e em `WA_1..WA_100`, nomes batem com o manifesto (21.000 arquivos); mutantes 200/200 com 100
cada, `building/` vazio; relação 200/200 e 0 sobrando; `--deep` também `OK` (hash do dataset e do zip).

### R23 — Fechamento da feature (2026-09-25)

**Artefatos finais** (gerados pelos autores e commitados): `data/mutants.zip` — 20.000 arquivos,
9.499.327 bytes, SHA-256 `ffd44455a94715feeae869e556d95ec8614661c7b33a8cf4e63f7d88896a1d81`;
`manifests/mutants.manifest.json` (3.387.809 bytes, 20.000 itens); `manifests/mutation_report.json`
(629 bytes): 200 problemas fechados, 200 completos, 0 excluídos, 113 só de primeira ordem, 87 com
ordem superior; ordem 1: 16.930, ordem 2: 3.061, ordem 3: 9; funil: 8.997 equivalentes, 2.014 RE,
1.816 TLE, 1.334 não compilam, 166 MLE, 28 instáveis, 0 duplicatas; operadores: UOI 8.580, ROR
6.332, ABS 5.372, AOR 2.624, LCR 171. `mutation verify` `OK`; `python -m cli check --deep` `OK`, 0
falhas, 0 avisos (hash de 21.000 arquivos do dataset e 20.000 mutantes, e dos dois zips).

**Decisões do fechamento**: (a) sem `code_revision` no relatório (R20 revisado); (b) a conferência de
consistência ficou no pacote `src/cli` (R22); (c) os READMEs dos módulos passam a ter dois cenários
e uma tabela de comandos, sem citação ao processo (Constitution 1.7.0, `docs/template-modulo.md`,
checagem C8); (d) `scripts/verify_dataset.py` continua no repositório mas não é mais o comando
documentado: a documentação usa `python -m dataset verify` (o script e os documentos da feature
001 que o citam ficam a critério dos autores remover). **Pendências que não bloqueiam**: registrar a
revisão de código pelos autores (Princípio X); carimbar `check` no README do `cli` depois do
commit; corrigir o cronômetro por problema do `generate` (inclui a espera na fila com mais de um
trabalhador, R21).
