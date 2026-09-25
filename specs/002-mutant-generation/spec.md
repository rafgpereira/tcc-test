# Feature Specification: Geração de Mutantes

**Feature Branch**: `002-mutant-generation`

**Created**: 2026-09-23

**Status**: Draft

**Input**: User description: "Especificar o módulo de geração de mutantes, conforme
`docs/metodologia-referencia.md`, seção 2, e as decisões tomadas em rodada de pesquisa e
discussão técnica prévia (registrada em documento compartilhado com a dupla): parsing real via
AST (tree-sitter), conjunto completo de operadores de Offutt et al. (ROR/AOR/LCR/ABS/UOI),
mutação de ordem superior determinística (sem busca), uso exclusivo do `AC_ref` como base de
mutação (sem ACs adicionais do dataset de origem), motor de execução único reaproveitado do
módulo `sandbox`, e uma arquitetura de reprodutibilidade em que o pacote final de mutantes é
versionado (não apenas regenerável por seed), pelo mesmo motivo que já levou a versionar o
dataset: a instabilidade de margem já medida no motor de execução (D18/D19 do módulo de
dataset). Este módulo NÃO inclui chamadas a modelos de IA, avaliação das suítes geradas nem
cálculo de métricas — isso é escopo de módulos futuros."

## Clarifications

### Session 2026-09-23

- Q: Quando um problema tem mais de 100 mutantes de primeira ordem válidos, como o sistema
  escolhe exatamente quais 100 entram? → A: truncamento determinístico pelos primeiros 100 na
  ordem de descoberta da travessia da AST (mesma ordem já usada para ordem superior); o módulo
  não usa nenhuma operação aleatória, e por isso não precisa de seed própria.
- Q: A validação de estabilidade de cada mutante candidato deve exigir 2 execuções concordantes
  ou 3 (6 execuções no total)? → A: 3 (6 execuções no total) — a mesma força já usada no reparo
  de WA (D18), depois que a regra original de 2 execuções se mostrou insuficiente na prática.
- Q: Se um problema não fechar 100 mutantes válidos, isso afeta só a métrica de Escore de
  Mutação (podendo ficar com menos de 200 problemas nela) ou aciona a escolha de um substituto
  no dataset? → A: só a métrica de Escore de Mutação é afetada (TDF/TFP continuam sobre os 200);
  a exclusão sempre gera um alerta explícito e documentado no relatório, nunca silenciosa.

## User Scenarios & Testing *(mandatory)*

<!--
  Os "usuários" deste módulo são os dois autores do TCC, que precisam de um conjunto de
  defeitos sintéticos válidos e reprodutíveis para medir a sensibilidade (Escore de Mutação)
  das suítes geradas pelos três modelos, e de um artefato arquivável que sustente os números
  publicados no trabalho escrito.
-->

### User Story 1 - Gerar mutantes válidos a partir do `AC_ref` (Priority: P1)

Os autores executam a geração de mutantes sobre o dataset já validado e empacotado (módulo
`001-dataset-extraction`) e recebem, para cada problema completo, um conjunto de mutantes
sintaticamente válidos — cada um uma alteração pontual (ou, quando necessário, uma combinação
determinística de duas ou três alterações) do código de referência `AC_ref.cpp` — sem que
nenhum mutante seja uma mudança de texto dentro de um literal de string/char ou de um
comentário.

**Why this priority**: sem mutantes válidos não há como medir o Escore de Mutação (MS), uma das
quatro métricas centrais do experimento (metodologia, seção 5.2). É a capacidade mínima do
módulo.

**Independent Test**: pode ser testado isoladamente rodando a geração sobre um único problema
do dataset já extraído e inspecionando os mutantes produzidos (cada um compila, diverge da
suíte oficial, e nenhuma alteração recai sobre um literal ou comentário).

**Acceptance Scenarios**:

1. **Given** um problema completo do dataset com seu `AC_ref.cpp` e `testes.json`, **When** a
   geração de mutantes é executada, **Then** o sistema produz até 100 mutantes, cada um
   diferindo do original por uma alteração de código executável (nunca de texto literal ou
   comentário), que compila, executa dentro dos limites do problema e diverge da suíte oficial.
2. **Given** um mutante candidato que se comporta identicamente ao `AC_ref` em toda a suíte
   oficial, **When** ele é avaliado, **Then** o sistema o descarta como equivalente e não o
   conta para a cota de 100.

---

### User Story 2 - Fechar a cota de 100 mesmo quando a primeira ordem não basta (Priority: P1)

Para problemas cujo `AC_ref` não tem sítios de mutação de primeira ordem suficientes (mesmo com
o conjunto completo de operadores), os autores precisam que o sistema combine mutações de
primeira ordem já válidas, em uma ordem determinística e reprodutível, até fechar 100 mutantes
válidos, sem recorrer a busca nem a heurísticas não documentadas.

**Why this priority**: a medição de pesquisa sobre os 200 `AC_ref` reais mostrou que, mesmo com
o conjunto completo de operadores, uma fração dos problemas (estimativa: por volta de 1 em cada
4) não fecha 100 mutantes de primeira ordem — sem uma regra de ordem superior, o módulo não
cumpriria a meta da metodologia para todos os problemas.

**Independent Test**: pode ser testado isoladamente com um `AC_ref.cpp` sintético e pequeno,
com poucos sítios de mutação, verificando que o sistema completa a cota combinando sítios em
pares (e trios, se necessário) na mesma ordem em execuções repetidas.

**Acceptance Scenarios**:

1. **Given** um problema cujos mutantes de primeira ordem válidos e distintos são menos de 100,
   **When** a geração é executada, **Then** o sistema combina pares de mutações de primeira
   ordem em sítios distintos, na ordem de descoberta desses sítios, até completar 100 ou
   esgotar as combinações possíveis.
2. **Given** uma combinação de ordem superior cujas duas alterações se cancelam (o resultado é
   equivalente ao original), **When** ela é avaliada, **Then** o sistema a descarta pelo mesmo
   critério de equivalência da User Story 1, sem nenhuma lógica adicional.
3. **Given** um problema que esgota todas as combinações possíveis (primeira e segunda ordem)
   sem alcançar 100 mutantes válidos, **When** a geração é executada, **Then** o sistema exclui
   esse problema do conjunto final de mutantes e registra o motivo no relatório, sem usar
   nenhuma base de mutação adicional.

---

### User Story 3 - Empacotar e verificar os mutantes da execução final (Priority: P2)

Ao concluir a execução completa que vai sustentar os números publicados no TCC, um dos autores
empacota os mutantes de todos os problemas em um arquivo único, versionado, acompanhado de um
manifesto de integridade — para que os mutantes exatamente usados no experimento (e não apenas
"regeneráveis com a mesma seed") continuem disponíveis para conferência e para o outro autor,
mesmo que uma reexecução futura não produza exatamente o mesmo conjunto, dada a instabilidade de
margem já conhecida do motor de execução.

**Why this priority**: sem isso, os números do TCC dependeriam de uma promessa de determinismo
que o próprio projeto já provou, na prática, não se sustentar sempre (auditoria do módulo de
dataset, D18/D19) — o experimento deixaria de ser auditável por terceiros.

**Independent Test**: pode ser testado isoladamente empacotando o resultado de uma execução de
teste e verificando que a verificação de integridade aponta corretamente um arquivo alterado,
removido ou acrescentado.

**Acceptance Scenarios**:

1. **Given** um conjunto completo de mutantes gerados para os 200 problemas, **When** o
   empacotamento é executado, **Then** o sistema produz um arquivo compactado único e um
   manifesto de hashes SHA-256 por arquivo, no mesmo formato já usado para o dataset.
2. **Given** o pacote de mutantes e seu manifesto, **When** a verificação de integridade é
   executada sobre um mutante alterado, removido ou acrescentado, **Then** o sistema aponta
   exatamente esse arquivo como divergente.
3. **Given** que o dataset local não corresponde ao manifesto já versionado do dataset,
   **When** a geração de mutantes é iniciada, **Then** o sistema se recusa a rodar e informa a
   divergência, em vez de gerar mutantes sobre uma entrada não verificada.

---

### User Story 4 - Relatório de geração para sustentar o texto do TCC (Priority: P3)

Os autores precisam de um relatório versionado com os números agregados da geração de mutantes
(quantos vieram de primeira vs. de ordem superior, distribuição por operador, problemas
excluídos e por quê), para citar no texto escrito sem precisar reabrir os arquivos-fonte dos
mutantes.

**Why this priority**: é a mesma exigência de documentação viva já aplicada ao módulo de
dataset (Constitution, Princípio XI) — sem isso, os números do TCC não têm proveniência
auditável.

**Independent Test**: pode ser testado isoladamente conferindo que o relatório gerado ao final
de uma execução de teste contém os campos exigidos e que os totais somam corretamente.

**Acceptance Scenarios**:

1. **Given** uma execução completa da geração de mutantes, **When** ela termina, **Then** o
   sistema grava um relatório com o funil de descarte por motivo, a distribuição de mutantes
   por operador e por ordem (1ª vs. superior) e qualquer alerta de exclusão de problema.

---

### Edge Cases

- Um `AC_ref.cpp` com poucos sítios de mutação mesmo após o conjunto completo de operadores e
  toda a combinação de ordem superior possível: o problema é excluído da amostra de mutantes e
  registrado no relatório (mesmo tratamento já dado a WA insuficiente no módulo de dataset).
- Um mutante candidato idêntico, em texto, a outro já aceito para o mesmo problema (inclusive
  entre uma combinação de ordem superior e um mutante de primeira ordem já existente): é
  descartado por unicidade.
- Uma execução do motor que produz um veredito diferente para o mesmo mutante em duas rodadas
  de validação (a mesma instabilidade de margem já documentada para WA): o candidato só é
  aceito se as execuções concordarem; se não concordar, é descartado como instável, não como
  válido nem inválido por acaso.
- O `data/dataset` local está ausente, incompleto ou não corresponde ao manifesto já
  versionado: a geração se recusa a rodar antes de produzir qualquer mutante.
- Um operador ABS ou UOI aplicado a um sítio cujo tipo não é compatível (por exemplo, uma
  subexpressão que não é numérica): o candidato resultante simplesmente não compila e é
  descartado pelo mesmo critério de qualquer outro candidato que não compila — não é um caso
  especial.

## Requirements *(mandatory)*

### Functional Requirements

**Estratégia de mutação**

- **FR-001**: O sistema MUST identificar sítios de mutação em `AC_ref.cpp` por meio de uma
  análise sintática real (AST) do código-fonte C++, usando um parser tolerante a erro que não
  exige resolução de árvore de includes nem informação de tipos completa, de modo que nenhuma
  alteração recaia sobre o conteúdo de um literal de string/char ou de um comentário (ver
  Divergências, D1).
- **FR-002**: O sistema MUST implementar o conjunto de operadores de mutação de Offutt et al.
  (1996): **ROR** (troca um operador relacional por todos os demais legais), **AOR** (idem
  para operadores aritméticos), **LCR** (idem para conectores lógicos), **ABS** (força uma
  subexpressão aritmética a assumir zero, um valor positivo e um valor negativo) e **UOI**
  (insere um operador unário à frente de uma expressão existente) — ver Divergências, D2.
- **FR-003**: Cada mutante de primeira ordem MUST diferir do `AC_ref.cpp` por exatamente um
  sítio de mutação alterado por um único operador.
- **FR-003a**: Quando o número de mutantes de primeira ordem válidos e distintos de um problema
  for maior que 100, o sistema MUST reter exatamente os primeiros 100, na mesma ordem
  determinística de descoberta de sítios na travessia da AST usada em FR-004, descartando o
  restante sem nenhuma seleção aleatória (ver Divergências, D6, revisado nesta sessão de
  esclarecimento).

**Ordem superior**

- **FR-004**: Quando o número de mutantes de primeira ordem válidos e distintos de um problema
  for menor que 100, o sistema MUST combinar mutações de primeira ordem já validadas em pares,
  em sítios distintos, na ordem em que esses sítios foram descobertos na travessia da AST, até
  completar 100 ou esgotar as combinações de pares possíveis; se ainda insuficiente, MUST
  repetir o processo combinando em trios, na mesma ordem determinística (ver Divergências, D3).
- **FR-004a**: O sistema MUST NOT usar nenhuma técnica de busca (programação genética,
  otimização multi-objetivo ou equivalente) para escolher combinações de ordem superior — a
  regra de combinação MUST ser puramente determinística.

**Validação de mutantes**

- **FR-005**: O sistema MUST descartar um mutante candidato, de qualquer ordem, que: (a) seja
  lexicamente idêntico a outro já aceito para o mesmo problema; (b) não compile em nenhum
  padrão da cascata de fallback (`gnu++20` → `gnu++17` → `gnu++14` → `gnu++11`) usada pelo
  motor de execução; (c) não execute dentro dos limites de tempo e memória do problema (TLE,
  MLE ou RE); (d) produza a mesma saída do gabarito em 100% da suíte de testes oficial do
  problema (mutante equivalente).
- **FR-006**: O sistema MUST reutilizar, sem alteração, o motor de execução único já construído
  no módulo `sandbox` (metodologia, seções 1.4 e 4) para compilar, executar e julgar cada
  mutante candidato — as mesmas flags, os mesmos limites e a mesma regra de comparação de saída
  usados para validar o dataset.
- **FR-007**: O sistema MUST exigir **6 execuções concordantes** (mesmo veredito e mesmo teste
  decisivo) antes de aceitar definitivamente um mutante candidato como válido, descartando-o
  como instável quando alguma delas divergir — a mesma força (3 checagens de estabilidade
  independentes, 2 execuções cada) já usada para o reparo de WA depois que a regra original de
  2 execuções se mostrou insuficiente na prática (ver Divergências, D5).

**Base de mutação**

- **FR-008**: O sistema MUST usar exclusivamente o `AC_ref.cpp` de cada problema como base de
  mutação; MUST NOT usar nenhuma outra solução correta do dataset de origem como base adicional
  (ver Divergências, D4).
- **FR-009**: Quando um problema não atingir 100 mutantes válidos mesmo após esgotada a
  combinação de ordem superior (FR-004), o sistema MUST excluir esse problema do conjunto final
  de mutantes e registrar o motivo no relatório (FR-013), em vez de aceitar um número menor que
  100 ou de usar uma base de mutação adicional. O denominador de 200 problemas usado pelas
  demais métricas (TDF, TFP) MUST NOT ser afetado — só o cálculo do Escore de Mutação (MS), que
  passa a ser calculado sobre os problemas efetivamente completos (< 200 quando houver exclusão),
  fica sujeito a essa exclusão (ver Divergências, D4, revisado).
- **FR-009a**: Toda exclusão de problema por FR-009 MUST disparar um alerta explícito no
  relatório (FR-013) — identificador do problema, quantos mutantes válidos foram alcançados e em
  que ordem (1ª, 2ª ou 3ª) — de modo que a situação nunca passe silenciosa, mesmo sendo a
  estimativa de pesquisa que ela seja rara ou inexistente.

**Dependência do dataset**

- **FR-010**: Antes de gerar qualquer mutante, o sistema MUST verificar o conteúdo local de
  `data/dataset` contra `manifests/dataset.manifest.json`, recusando-se a executar, com
  mensagem clara sobre o que diverge, se o conteúdo não corresponder ao manifesto já
  versionado.

**Reprodutibilidade e empacotamento**

- **FR-011**: O módulo MUST NOT usar nenhuma operação aleatória: toda ordem de descoberta de
  sítios, toda combinação de ordem superior (FR-004) e todo truncamento de excedentes (FR-003a)
  MUST seguir exclusivamente a ordem determinística de travessia da AST — nunca amostragem ou
  escolha aleatória entre candidatos equivalentes. Não há, portanto, seed própria deste módulo
  a documentar (ver Divergências, D6, revisado).
- **FR-012**: Os mutantes gerados durante o desenvolvimento iterativo do módulo MUST NOT ser
  versionados no controle de versão. Ao final da execução completa que sustenta os números
  publicados do experimento, o sistema MUST poder compactar os mutantes de todos os problemas
  num pacote único (`data/mutants.zip`), acompanhado de um manifesto de integridade SHA-256
  (`manifests/mutants.manifest.json`), no mesmo formato já usado para o dataset (ver
  Divergências, D5).
- **FR-013**: O sistema MUST produzir um relatório versionável (`manifests/mutation_report.json`)
  contendo, no mínimo: o funil de descarte por motivo (duplicata, não compila, TLE/MLE/RE,
  equivalente, instável), quantos mutantes de cada problema vieram de primeira ordem e quantos
  de ordem superior, a distribuição de mutantes por operador, a lista de alertas de exclusão de
  problema (FR-009a, vazia no caso esperado). *(Revisado em 2026-09-25: a exigência da revisão de
  código (git) no relatório foi retirada a pedido dos autores — os contêineres não têm `.git`, o
  módulo de dataset não grava revisão nenhuma, e a rastreabilidade fica no commit que versiona os
  artefatos; o relatório continua ligado à versão exata do dataset pelo hash do manifesto.)*
- **FR-014**: O sistema MUST fornecer um comando de verificação, análogo ao já existente para o
  dataset, que recalcula os hashes de `data/mutants.zip` e os compara com
  `manifests/mutants.manifest.json`, apontando qualquer arquivo alterado, removido ou
  acrescentado.

### Key Entities *(include if feature involves data)*

- **Sítio de mutação**: nó da AST de `AC_ref.cpp` elegível para receber um operador de
  mutação — um operador relacional, aritmético ou lógico existente (para ROR/AOR/LCR), uma
  subexpressão numérica (para ABS) ou uma expressão existente (para UOI).
- **Operador de mutação**: uma das cinco transformações do conjunto de Offutt et al. (ROR,
  AOR, LCR, ABS, UOI), aplicável a um sítio de mutação.
- **Mutante**: cópia de `AC_ref.cpp` com uma (primeira ordem) ou mais (ordem superior)
  alterações pontuais aplicadas a sítios de mutação distintos; identificado por um índice de 1
  a 100 dentro do problema.
- **Mutante de ordem superior (HOM)**: mutante formado pela combinação determinística de duas
  ou três mutações de primeira ordem já válidas, em sítios distintos do mesmo `AC_ref.cpp`,
  usado apenas quando a primeira ordem não basta para completar a cota de 100.
- **Registro de descarte**: motivo pelo qual um mutante candidato foi rejeitado (duplicata, não
  compila, TLE/MLE/RE, equivalente, instável), usado para compor o funil do relatório.
- **Alerta de exclusão de problema**: registro de que um problema não alcançou 100 mutantes
  válidos mesmo após ordem superior; afeta só o denominador da métrica de Escore de Mutação
  (nunca o de TDF/TFP) e nunca é silencioso.
- **Pacote de mutantes**: `data/mutants.zip`, gerado apenas na execução final do experimento,
  com manifesto de integridade próprio (`manifests/mutants.manifest.json`).
- **Relatório de geração de mutantes**: `manifests/mutation_report.json`, dado quantitativo
  agregado, para citação no texto do TCC sem reabrir os arquivos-fonte dos mutantes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Todo problema completo do dataset termina a geração de mutantes com exatamente
  100 mutantes válidos e distintos, ou é excluído do conjunto de mutantes com o motivo
  registrado no relatório e um alerta explícito — nunca com um número intermediário sem
  explicação, e nunca reduzindo silenciosamente o denominador de 200 problemas usado por TDF e
  TFP (só o do Escore de Mutação, quando isso ocorrer).
- **SC-002**: Em uma amostra de mutantes gerados, 0% deles altera exclusivamente o conteúdo de
  um literal de texto ou de um comentário; toda alteração recai sobre uma posição de código
  executável.
- **SC-003**: Para ao menos três em cada quatro problemas completos do dataset, a cota de 100
  mutantes é alcançada inteiramente com mutantes de primeira ordem, sem precisar de combinações
  de ordem superior (estimativa de pesquisa baseada em medição sobre os 200 `AC_ref` reais; a
  execução final registra o número real no relatório). **Medido em 2026-09-25 (execução real):
  113 de 200 (56,5%) — a estimativa não se confirmou; nenhum problema foi excluído, então SC-001 se
  cumpre; 15,3% dos mutantes são de ordem superior (`research.md` R21).**
- **SC-004**: A verificação de integridade do pacote de mutantes passa em 100% das vezes sobre
  um pacote íntegro e falha, apontando exatamente o arquivo divergente, em 100% das vezes em
  que qualquer mutante for alterado, removido ou acrescentado sem reempacotar.
- **SC-005**: Rodar a geração de mutantes sobre um `data/dataset` local que não corresponde ao
  manifesto do dataset falha antes de qualquer mutante ser gerado, em 100% das tentativas.
- **SC-006**: Nenhum mutante da execução final é perdido para os autores: o pacote versionado e
  seu manifesto continuam disponíveis para conferência mesmo que uma reexecução futura, sobre o
  mesmo dataset e a mesma seed, não reproduza exatamente o mesmo conjunto (instabilidade de
  margem já documentada do motor de execução).
- **SC-007**: Ao concluir a feature, `docker compose run --rm app python
  scripts/check_docs_sync.py --closing` (sobre `src/mutation/`, quando implementado) termina
  com código 0, nas mesmas condições já exigidas para os módulos anteriores.

## Assumptions

- **Usuários**: os dois autores do TCC executam o módulo localmente; não há usuários finais
  externos.
- **Dependência total do módulo de dataset**: este módulo consome exclusivamente
  `data/dataset` (ou `data/dataset.zip` descompactado), já validado e empacotado pelo módulo
  `001-dataset-extraction` (Status: implementado). Nenhuma mudança de schema é necessária
  nesse módulo — a decisão de não usar ACs adicionais (D4) preserva o pacote do dataset como
  está.
- **Motor de execução**: reutilizado sem alteração do módulo `sandbox` — mesmas flags de
  compilação, mesmos limites de tempo/memória/pilha, mesma regra de comparação de saída.
- **Sem seed própria**: o módulo não usa nenhuma operação aleatória — seleção de sítios, ordem
  superior e truncamento de excedentes seguem só a ordem determinística da travessia da AST (ver
  Divergências, D6, revisado).
- **Instabilidade de margem do motor**: aceita como fato já documentado (auditoria do módulo de
  dataset, D18/D19); mitigada por uma checagem de estabilidade de 6 execuções concordantes (a
  mesma força já usada no reparo de WA), mas não eliminada — por isso a arquitetura de
  reprodutibilidade deste módulo depende do pacote da execução final versionado, não de uma
  garantia de determinismo por construção (ver Divergências, D5).
- **Ferramenta de parsing**: `tree-sitter` / `tree-sitter-cpp`. Risco residual aceito: um
  operador ABS ou UOI aplicado a um sítio de tipo incompatível gera um candidato que
  simplesmente não compila — custo de eficiência (tempo de validação desperdiçado), não de
  correção, pois o próprio motor descarta esse candidato pelo critério já existente (FR-005b).
- **Custo medido da validação (2026-09-24, primeira implementação)**: compilar um `AC_ref.cpp` que
  usa `bits/stdc++.h` leva ~1,8 s, e no problema `189_C` só 24% dos candidatos avaliados foram
  aceitos (28 equivalentes, 22 que não compilam, 7 RE e 6 TLE entre 83 avaliados até aceitar 20),
  o que extrapola para dezenas de minutos por problema em série. O risco aqui não é de cota (os
  200 `AC_ref.cpp` tinham, no mínimo, 35 candidatos de primeira ordem brutos e mediana de 274; com
  o filtro de R16 são 26 e 198, e 34 problemas ficam abaixo de 100) e sim
  de tempo de execução; a paralelização da geração (`--workers`, paralelismo entre problemas) foi
  aprovada, implementada e validada (0 de 800 mutantes divergentes entre `--workers 1` e `--workers 4`; 2,07×) e os erros de compilação foram reduzidos por filtro sintático de
  sítios (24% → ~0–17% medidos; metodologia, 2.7 e 2.8; `research.md`, R13, R14, R16).
- **Recuperação de execuções interrompidas** (Princípio VII): interromper `generate` por qualquer
  motivo perde só o problema em andamento; os fechados não são refeitos nem tocados e o resultado
  final é idêntico ao de uma execução nunca interrompida (validado com o motor real; metodologia
  2.10, `research.md` R19). Um segundo `generate` simultâneo se recusa e um problema fechado
  danificado é apontado (`DAMAGED`), nunca pulado em silêncio.
- **Verificação de consistência entre artefatos**: `scripts/check_consistency.py` (comando da raiz,
  só lê) confere por nomes e contagens que o dataset descompactado e os mutantes estão completos e
  1:1, nos dois sentidos; `--deep` confere os hashes. Contrato e decisões em
  `docs/verificacao-consistencia.md` e `research.md` R22; os módulos seguintes o estendem.
- **Dependência de módulos futuros**: a orquestração de IA e a avaliação experimental
  consomem os mutantes produzidos aqui, mas nada deles é entregue nesta feature.

## Divergências e Decisões sobre a Metodologia

<!--
  Registro exigido pela Constitution (Princípio I): divergências ou preenchimentos de lacunas
  em relação a docs/metodologia-referencia.md, para atualizar o texto final do TCC.
-->

Decisões D1–D6 tomadas em 2026-09-23, em rodada de pesquisa e discussão técnica prévia à
especificação (registrada em documento compartilhado com a dupla), confirmadas por Rafael antes
deste `/speckit.specify`.

- **D1 — Estratégia de parsing: AST via `tree-sitter`, não regex nem ferramenta externa
  (decidido)**: a metodologia original (seção 2) não especificava a estratégia técnica de
  geração. Pesquisa de literatura identificou riscos concretos de substituição textual em
  código C++ de competição real (fechamento de template aninhado `>>`, operadores dentro de
  literais de string/char, comentários com código morto) e comparou `libclang` (parsing
  semântico, mas exige resolver a árvore de includes de `bits/stdc++.h` sob o front-end do
  Clang, com risco de divergência das extensões do GCC 13.2 já fixado para o motor),
  `tree-sitter` (parsing sintático, tolerante a erro, não exige resolução de headers nem de
  tipos) e `UniversalMutator` (substituição textual cuidadosa por regras). Avaliou-se também a
  ferramenta `Mull` (mutação baseada em LLVM/Clang), descartada por exigir uma segunda cadeia de
  compiladores (LLVM/Clang, ao lado do GCC 13.2 já fixado) e por ter motor de injeção e execução
  de mutantes próprio, conflitando com a decisão já tomada em 1.4 de um motor de execução único,
  reutilizado sem alteração. **Decisão**: `tree-sitter` + `tree-sitter-cpp`, com um mutador leve
  próprio que só gera texto mutado e entrega ao motor do módulo `sandbox` já existente. Reflete-se
  em FR-001 e FR-006.
- **D2 — Conjunto de operadores ampliado para o conjunto de Offutt et al. (decidido)**: a
  metodologia original lista operadores relacionais, aritméticos e lógicos com substituição em
  pares fixos (ex.: `<`↔`<=`). Medição empírica sobre os 200 `AC_ref.cpp` reais (contagem de
  ocorrências desses operadores, ignorando comentários e literais) mostrou mediana de 23
  ocorrências por arquivo, com 199 dos 200 problemas (99,5%) abaixo de 100 — o conjunto original
  não é capaz de produzir 100 mutantes de primeira ordem para a quase totalidade da amostra.
  **Decisão**: adotar o conjunto de cinco operadores que Offutt, Lee, Rothermel, Untch e Zapf
  (1996, *"An Experimental Determination of Sufficient Mutant Operators"*, ACM TOSEM 5(2))
  mediram como suficiente (99,5% do escore de mutação do conjunto completo de operadores, com 4x
  menos mutantes): ROR e AOR e LCR com substituição **completa** (não por pares fixos), mais ABS
  e UOI. Uma nova estimativa, simulando esse conjunto sobre os mesmos 200 arquivos (multiplicando
  por ~4 os sítios de operador já existentes para ROR/AOR/LCR, e usando a contagem de ocorrências
  de identificador como proxy conservador dos sítios de ABS/UOI), deu mediana ≈146 e apenas 44
  dos 200 problemas (22%) ainda abaixo de 100, antes de qualquer combinação de ordem superior.
  Reflete-se em FR-002.
- **D3 — Ordem superior por regra determinística, sem busca (decidido)**: a metodologia original
  só diz "combinar duas mutações simultâneas", sem regra de escolha. A literatura de mutação de
  ordem superior (Jia & Harman, *"Higher Order Mutation Testing"*, 2009; Harman, Jia, Langdon e
  outros) é majoritariamente baseada em busca (programação genética, otimização multi-objetivo)
  para encontrar combinações "strongly subsuming" — incompatível com a simplicidade e o
  determinismo exigidos (Constitution, Princípios II e IX): combinar mutações ao acaso tende a
  produzir mutantes equivalentes ou triviais, e é exatamente por isso que essa linha de pesquisa
  usa busca. **Decisão**: combinação em pares (e, se ainda insuficiente, trios) na ordem em que
  os sítios de mutação foram descobertos na travessia da AST, sem busca — aceitando como
  consequência que uma fração dos mutantes de ordem superior seja mais fácil de matar do que o
  ideal da literatura, já que o objetivo aqui é fechar uma cota de defeitos distintos e válidos,
  não encontrar o mutante mais difícil possível. Reflete-se em FR-004 e FR-004a.
- **D4 — Base de mutação exclusivamente o `AC_ref` (decidido)**: a pesquisa avaliou usar outras
  soluções corretas do dataset de origem (`correct_solutions`, disponíveis apenas em
  `data/work/staging/raw/*.json.gz`, nunca persistidas além da primeira escolhida como `AC_ref`)
  como bases de mutação adicionais para problemas com poucos sítios. **Decisão**: não usar — a
  ampliação do conjunto de operadores (D2) já fecha a cota para a grande maioria dos problemas
  (estimativa: só 22% ficariam abaixo de 100 antes de ordem superior, e a margem da ordem
  superior é grande o suficiente para cobrir esse resto). Usar ACs adicionais exigiria reabrir o
  schema do pacote do módulo `001-dataset-extraction` (novo `schema_version`, reempacotamento),
  já concluído (`Status: implementado`, T103) — decisão evitada por não ser necessária. Um
  problema que, na prática, não fechar 100 mutantes válidos mesmo após ordem superior é excluído
  do conjunto final de mutantes e registrado no relatório, no mesmo espírito de D4 da spec
  `001-dataset-extraction` (WA insuficiente) — **com uma diferença importante, esclarecida em
  `/speckit.clarify` (2026-09-23)**: lá, a exclusão acontece durante a seleção dos 200 (o pool
  ainda tem candidatos para substituir); aqui, os 200 problemas já estão fixados e empacotados,
  então não há "próximo candidato" sem reabrir o módulo `001-dataset-extraction`. **Decisão**:
  a exclusão afeta só o cálculo do Escore de Mutação (MS), que passa a ser calculado sobre os
  problemas efetivamente completos (podendo ser menos de 200 problemas nessa métrica específica),
  sem afetar o denominador de 200 usado por TDF e TFP nem acionar a escolha de um substituto no
  dataset; toda ocorrência gera um alerta explícito no relatório (FR-009a), nunca silencioso,
  ainda que a estimativa de pesquisa (D2) sugira que seja rara ou inexistente na prática.
  Reflete-se em FR-008, FR-009 e FR-009a.
- **D5 — Reprodutibilidade do pacote final não depende só da seed; pacote de mutantes
  versionado ao final do experimento (decidido; requer emenda à Constitution)**: a validação de
  cada mutante candidato (compila, executa, compara com a suíte oficial) usa o mesmo motor de
  execução cuja instabilidade de margem já foi medida e documentada na auditoria do módulo de
  dataset (D18/D19 da spec `001-dataset-extraction`: 20 dos 200 problemas precisaram de reparo
  em pelo menos uma rodada de auditoria, por comportamento indefinido ou tempo de execução no
  limiar do limite — nunca por lógica de seleção). Isso significa que "regenerar os mutantes
  localmente com a mesma seed" reduz, mas não garante, obter exatamente o mesmo conjunto final —
  o mesmo argumento que já levou a versionar o dataset (Constitution, Princípio II, emenda
  1.1.0) se aplica, sem diferença de fundo, a mutantes. **Decisão**: (a) manter uma checagem de
  estabilidade na validação de cada mutante, com a mesma força já usada para o reparo de WA (6
  execuções concordantes — 3 checagens independentes de 2 execuções cada; ver Clarifications,
  sessão 2026-09-23), já que a força original de 2 execuções se mostrou insuficiente na prática
  do próprio módulo de dataset, para reduzir a frequência de instabilidade, mas sem tratá-la
  como garantia de determinismo bit a bit; (b)
  compactar e versionar o conjunto de mutantes da execução final que sustenta os números
  publicados (`data/mutants.zip` + `manifests/mutants.manifest.json`), no mesmo formato já usado
  para o dataset, em vez de depender só de regeneração por seed; mutantes gerados durante o
  desenvolvimento iterativo continuam nunca sendo versionados. Esta decisão **requer uma emenda
  ao Princípio II da Constitution** (que hoje diz que mutantes nunca têm a exceção do dataset),
  registrada e ratificada nesta mesma rodada (ver Constitution, emenda 1.6.0, 2026-09-23) — a
  mesma lógica se estende, em módulos futuros, a artefatos que dependam de execução real do
  motor ou de chamadas a APIs de IA (suítes geradas, resultados finais de avaliação). Reflete-se
  em FR-007 e FR-012.
- **D6 — Sem seed própria: o módulo não usa nenhuma operação aleatória (decidido, revisado em
  `/speckit.clarify`, 2026-09-23)**: a pesquisa original assumiu que a Constitution exigir seed
  fixa e documentada para "geração de mutantes" (Princípio II) implicava que este módulo
  precisaria nomear uma. Ao esclarecer a regra de seleção quando há **mais** de 100 mutantes de
  primeira ordem válidos (caso não coberto até então — FR-004 só cobria o caso de faltarem
  mutantes), ficou claro que a resposta certa é a mesma regra já determinística usada para ordem
  superior (truncar pelos primeiros 100 na ordem de descoberta da AST), não uma amostragem
  aleatória. **Decisão**: o módulo não usa nenhuma operação aleatória em nenhuma etapa (seleção
  de sítios, ordem superior, truncamento de excedentes); a exigência de seed do Princípio II é
  satisfeita por vacuidade — não há "operação com aleatoriedade" neste módulo para exigir seed.
  Reflete-se em FR-003a e FR-011 (revisado).
