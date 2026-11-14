# Feature Specification: Avaliação das suítes contra AC, WAs e mutantes

**Feature Branch**: `009-suite-evaluation` (sem branch própria; trabalho direto na `main`)

**Created**: 2026-11-04

**Status**: Implemented (execução completa em 2026-11-06)

**Input**: User description: "Módulo de avaliação (seção 4 da metodologia): executa cada suíte dos 4
modelos × 3 cenários × 200 problemas contra AC_ref, os 100 WAs e os mutantes, no sandbox. Requisitos
da seção F de docs/metricas-referencia.md (consolidado na metodologia, seção 5): curto-circuito mantido para WA/mutante; sem curto-circuito
para o AC, com veredito por teste (passou / saída diferente / RE-TLE) e a saída real do AC por
entrada; conjunto exato de WAs e mutantes mortos por suíte (não só contagem); avaliar um attempt_N
isolado do SLM além do suite.json final. Entra no cli check."

## Contexto

As quatro execuções de geração estão concluídas e empacotadas: o modelo local (`slm_suites`, 600
suítes, juntando a revisão 1 e a refeita na revisão 2 por `provenance.json`) e os três comerciais
(`gpt_suites`, `gemini_suites`, `claude_suites`, 600 combinações cada; o Claude tem 3
`discarded_manual`, sem suíte). O dataset (revisão 2) traz, por problema, o `AC_ref.cpp`, os 100
WAs validados e os limites; o pacote de mutantes traz 100 mutantes por problema.

A seção 4 da metodologia descreve a avaliação só em curto-circuito para todo código-alvo e um CSV
de saída, sem spec. A proposta consolidada de métricas (`docs/metricas-referencia.md` (consolidado na metodologia, seção 5), confirmada
pelos autores em 2026-11-04, sem C.5 e C.6) exige mais do que isso: o veredito de **cada** teste
contra o `AC_ref`, a saída real do `AC_ref` em cada entrada, os conjuntos exatos de WAs e mutantes
detectados e a avaliação da 1ª tentativa do modelo local sem o filtro das 12 tentativas.

Esta feature só **executa e registra**. O cálculo das métricas (TDF, MS, TFP, IIC, TC, TDF\*/MS\*,
TFP por teste e por causa, custo, densidade, estatística) é da feature seguinte (010), que lê só o
que esta grava, sem executar nada.

## Clarifications

### Session 2026-11-04

- Q: Quando o `AC_ref` dá erro de execução num teste (possível instabilidade de margem de tempo),
  o que fazer? → A: Executar o AC mais 2 vezes só nesse teste; o erro só vale se aparecer nas 3
  execuções; a instabilidade vai para o relatório (Milena; FR-005a).
- Q: Quando um WA ou mutante é detectado por erro de execução (TLE, RE ou MLE), a detecção é
  confirmada com novas execuções? → A: Sim, mesma regra do AC: o teste é repetido mais 2 vezes e a
  detecção só vale se o erro aparecer nas 3; senão o alvo segue para os próximos testes e o teste
  fica marcado como instável (FR-006a).
- Q: A execução completa exige um piloto antes? → A: Sim: piloto obrigatório nos 5 problemas dos
  pilotos × 4 modelos × 3 cenários (60 combinações), com conferência manual e decisão dos autores
  registrada; se nada mudar, a execução completa reaproveita o resultado do piloto (FR-021).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Avaliar as suítes finais de um modelo (Priority: P1)

Um autor escolhe um modelo (`slm`, `gpt`, `gemini` ou `claude`) e roda a avaliação. Para cada
problema e cenário, a suíte vigente é executada contra o `AC_ref`, os 100 WAs e os 100 mutantes do
problema, dentro do serviço sem rede, com os limites do próprio problema. O resultado de cada
combinação fica gravado em disco: o veredito por teste do `AC_ref` com a saída real dele, e, para
cada WA e mutante, se foi detectado e por qual teste.

**Why this priority**: é o insumo direto de todas as métricas primárias (TDF, MS, TFP, IIC); sem
ele nada da feature 010 pode ser calculado.

**Independent Test**: rodar a avaliação de um modelo em um problema só e conferir, à mão, contra a
suíte e os códigos do problema, que os WAs e mutantes marcados como detectados falham de fato no
teste indicado e que o veredito por teste do `AC_ref` está correto.

**Acceptance Scenarios**:

1. **Given** uma suíte com N testes e um `AC_ref` que passa em todos, **When** a combinação é
   avaliada, **Then** o registro do AC tem N vereditos "passou", a saída real de cada entrada, e o
   AC é dado como aprovado.
2. **Given** uma suíte em que o `AC_ref` difere da saída declarada no teste 2 e estoura o tempo no
   teste 5, **When** a combinação é avaliada, **Then** **todos** os N testes são executados contra
   o AC (sem parar no teste 2), o teste 2 fica "saída diferente", o 5 fica "erro de execução" com o
   tipo (TLE) por ter estourado o tempo nas 3 execuções (FR-005a), e o AC é dado como reprovado.
3. **Given** um WA que falha no teste 3, **When** ele é avaliado, **Then** ele fica registrado como
   detectado pelo teste 3 e os testes seguintes não são executados para ele.
4. **Given** um mutante que passa em todos os testes, **When** ele é avaliado, **Then** ele fica
   registrado como não detectado (sobrevivente).
5. **Given** uma combinação `discarded_manual` (sem suíte), **When** o modelo é avaliado, **Then**
   nada é executado para ela e o registro diz explicitamente "sem suíte", sem contar como AC
   aprovado nem reprovado.

---

### User Story 2 - Detecção com o oráculo corrigido pelo AC (Priority: P1)

Para cada combinação, além da detecção pela saída declarada pela IA, o módulo registra a detecção
de cada WA e mutante quando a saída esperada de cada teste é trocada pela saída real do `AC_ref`
naquela mesma entrada (as entradas continuam sendo as da IA). Testes em que o próprio `AC_ref` dá
erro de execução não têm saída de referência e ficam fora desse segundo oráculo.

**Why this priority**: é o pré-requisito de TDF\*, MS\* e Δ_oráculo (C.1, prioridade máxima da
proposta de métricas), que tornam comparáveis o modelo local (oráculo por execução) e os
comerciais (oráculo por predição). Sem gravar a detecção sob os dois oráculos aqui, a feature 010
teria de executar código de novo.

**Independent Test**: num problema em que o AC é reprovado por saída diferente num teste, conferir
que um WA que só "falhava" naquele teste aparece detectado pelo oráculo declarado e não detectado
pelo corrigido.

**Acceptance Scenarios**:

1. **Given** uma suíte cujas saídas declaradas batem todas com as do `AC_ref`, **When** a
   combinação é avaliada, **Then** os conjuntos de detectados pelos dois oráculos são idênticos.
2. **Given** um teste em que o `AC_ref` estoura o tempo, **When** o oráculo corrigido é aplicado,
   **Then** esse teste não é usado para nenhum WA ou mutante no oráculo corrigido, e o número de
   testes excluídos fica registrado.
3. **Given** uma suíte em que o `AC_ref` dá erro em todos os testes, **When** o oráculo corrigido é
   aplicado, **Then** a combinação tem `corrected_oracle_tests = 0` (nenhum teste válido no oráculo
   corrigido) e nenhum alvo é dado como detectado por ele.

---

### User Story 3 - Avaliar a 1ª tentativa do modelo local (Priority: P2)

Um autor avalia, em vez da suíte final, a 1ª tentativa de cada combinação do modelo local ("1ª
tentativa, sem filtro"; conjunto `slm-attempt1`), para comparar o modelo local com os
comerciais em pé de igualdade (uma chamada contra uma). Os testes dessa tentativa são as entradas
que ela manteve, com as saídas da solução do modelo, mesmo que a tentativa tenha sido rejeitada
nos testes públicos.

**Why this priority**: é um eixo de corte complementar (seção E da proposta), não a comparação
oficial; depende do mesmo motor da User Story 1.

**Independent Test**: avaliar a tentativa 1 de uma combinação cuja suíte final veio da tentativa 1
e conferir que o resultado é idêntico ao da suíte final.

**Acceptance Scenarios**:

1. **Given** uma combinação cuja tentativa 1 foi rejeitada por errar um teste público, **When** a
   tentativa 1 é avaliada, **Then** ela é executada com as entradas mantidas e as saídas que a
   solução do modelo produziu, e o resultado fica separado do da suíte final.
2. **Given** uma combinação cuja tentativa 1 não produziu nenhuma entrada utilizável (resposta não
   interpretada, ou todas as entradas descartadas), **When** a tentativa 1 é avaliada, **Then** o
   registro diz "sem suíte" para essa tentativa.

---

### User Story 4 - Retomar, consolidar, empacotar e conferir (Priority: P2)

A avaliação de um modelo leva horas. Um autor interrompe e retoma sem refazer nem corromper o que
já foi gravado; ao fim, gera um relatório-resumo e uma tabela consolidada, empacota o resultado com
manifesto de hashes e confere a integridade; e o `cli check` passa a conferir a nova camada contra
o dataset e as suítes.

**Why this priority**: exigência dos Princípios II e VII da constitution para todo artefato do
experimento; sem isso o resultado não é publicável, mas não bloqueia o desenvolvimento das
User Stories 1 a 3.

**Independent Test**: interromper uma avaliação no meio, retomar, e conferir que as combinações já
concluídas antes da parada não foram reescritas e que o resultado final tem os mesmos vereditos,
índices de teste e conjuntos de detectados de uma avaliação sem interrupção (tempo e memória
medidos ficam fora da comparação, porque mudam a cada execução).

**Acceptance Scenarios**:

1. **Given** uma avaliação interrompida, **When** ela é retomada, **Then** em cada problema só os
   conjuntos ainda sem resultado completo são avaliados (os prontos não são tocados), e um
   problema que estava em gravação é refeito do início para os conjuntos que faltavam.
2. **Given** uma avaliação completa, **When** o empacotamento roda, **Then** são gerados o pacote,
   o manifesto com o SHA-256 de cada arquivo e o relatório; a verificação de integridade confere o
   pacote e a pasta descompactada.
3. **Given** um resultado de avaliação com uma pasta de problema que não está no dataset, ou um
   cenário faltando depois do empacotamento, **When** o `cli check` roda, **Then** ele aponta
   falha nessa camada.

### Edge Cases

- **AC instável na margem de tempo**: um teste em que o `AC_ref` estoura o tempo pode ser um falso
  positivo do ambiente, não da IA. Tratamento (Q1, 2026-11-04): o `AC_ref` é executado mais 2
  vezes só nesse teste, e o erro só vale se aparecer nas 3 execuções (FR-005a).
- **Erro de compilação de um WA ou mutante**: não deveria ocorrer (todos foram validados no mesmo
  motor). Se ocorrer, o alvo é registrado com o veredito `CE`, não conta como detectado, e é
  listado no relatório como anomalia.
- **Falha de infraestrutura** (motor, disco, lançador): nunca vira veredito; o comando para com
  código próprio, nada do problema em andamento é gravado, e rodar de novo retoma.
- **Suíte com teste de entrada idêntica repetida**: executada como está (a deduplicação já é da
  geração); cada teste conta na própria posição.
- **Saída real do AC muito grande**: gravada inteira (as saídas do dataset e das suítes são
  pequenas); o relatório registra o maior tamanho encontrado.
- **`accepted_barred`, `accepted_fallback`, `accepted_predicted`**: avaliadas como qualquer suíte;
  o status é copiado para o resultado para permitir o corte por status na feature 010.
- **Modelo local com junção de execuções**: a suíte vigente de cada combinação é lida da pasta que
  o `provenance.json` indica (`slm` ou `slm-rev1`), e a origem é copiada para o resultado.
- **Mutantes ou suítes ausentes, ou `cli check --deep` com falha**: a avaliação não começa.

## Requirements *(mandatory)*

### Functional Requirements

**Entradas e portão**

- **FR-001**: O módulo MUST ler a suíte vigente de cada combinação problema × cenário de um modelo
  escolhido (`slm`, `gpt`, `gemini`, `claude`) a partir das pastas descompactadas dos pacotes de
  suítes, e, de cada problema, o `AC_ref`, os 100 WAs, os limites (do `metadata.json`) e os 100
  mutantes.
- **FR-002**: Antes de executar qualquer código, o módulo MUST exigir que `cli check --deep` passe
  (código de saída 0) para o dataset, os mutantes e as suítes do modelo escolhido; senão, não
  executa nada.
- **FR-003**: Todo código C++ MUST ser compilado e executado no serviço sem rede, pelo motor já
  existente (o mesmo do dataset e dos mutantes), com os limites de tempo, memória e pilha lidos dos
  metadados do problema, e com a regra de comparação de saída única do projeto.

**Execução contra o AC**

- **FR-004**: Contra o `AC_ref`, o módulo MUST executar **todos** os testes da suíte, sem
  curto-circuito, e gravar para cada teste: o índice, o veredito (`passou`, `saída diferente`,
  `erro de execução` com o tipo `RE`, `TLE` ou `MLE`), a saída real produzida (vazia quando houve
  erro), o tempo e o pico de memória.
- **FR-005**: O AC MUST ser dado como aprovado na combinação se, e somente se, todos os testes têm
  veredito `passou`.
- **FR-005a**: Quando o `AC_ref` dá `erro de execução` (RE, TLE ou MLE) num teste, o módulo MUST
  executá-lo mais 2 vezes nesse mesmo teste — as 2 repetições são sempre feitas, mesmo que a 2ª
  execução já não dê erro. O erro só vale se aparecer nas 3 execuções (com tipos diferentes entre
  as execuções, vale o tipo da 1ª). Se alguma delas passar ou der `saída diferente`, vale o
  resultado da primeira execução sem erro, e o teste fica marcado como instável. As 3 execuções
  ficam gravadas, e o relatório conta os testes instáveis. `saída diferente` não é repetida, porque é determinística.

**Execução contra WAs e mutantes**

- **FR-006**: Contra cada WA e cada mutante, o módulo MUST manter o curto-circuito: os testes são
  executados na ordem da suíte e a execução para no primeiro teste que o alvo falha (qualquer
  veredito diferente de `passou`).
- **FR-006a**: Quando o teste que interromperia um WA ou mutante tem veredito `erro de execução`
  (RE, TLE ou MLE), o módulo MUST executá-lo mais 2 vezes nesse teste (as 2 repetições são sempre
  feitas, como no FR-005a). A detecção só vale se o erro aparecer nas 3 execuções. Senão, vale a
  primeira execução sem erro e o teste fica marcado como instável para aquele alvo: se ela passou,
  a execução segue para o próximo teste; se deu `saída diferente`, a detecção vale com esse
  veredito. O relatório conta os testes instáveis por tipo de alvo. A regra vale para os dois
  oráculos.
- **FR-007**: Para cada WA e mutante, o módulo MUST gravar, sob o oráculo declarado pela IA: se foi
  detectado, o índice do teste que o detectou e o veredito desse teste.
- **FR-008**: Para cada WA e mutante, o módulo MUST gravar também a detecção sob o **oráculo
  corrigido**: a saída esperada de cada teste trocada pela saída real do `AC_ref` naquela entrada,
  usando só os testes em que o `AC_ref` não deu erro de execução, com o mesmo curto-circuito. O
  número de testes excluídos desse oráculo MUST ficar gravado na combinação.
- **FR-009**: O resultado de cada combinação MUST conter os **conjuntos** exatos de WAs e de
  mutantes detectados (identificadores, sob cada oráculo), não só as contagens.

**Combinações sem suíte e 1ª tentativa do modelo local**

- **FR-010**: Uma combinação sem suíte (`discarded_manual`, ou tentativa sem entradas utilizáveis)
  MUST ser gravada com a marca "sem suíte", sem nenhuma execução, e contada à parte no relatório.
- **FR-011**: Para o modelo local, o módulo MUST avaliar também a **1ª tentativa** de cada
  combinação (conjunto `slm-attempt1`), em vez da suíte final, usando como testes as entradas
  mantidas por essa tentativa e as saídas produzidas pela solução do modelo; o resultado MUST
  ficar separado do resultado da suíte final e dizer que é a tentativa 1. Outras tentativas não
  são avaliadas (nenhuma métrica as usa).
- **FR-012**: Uma 1ª tentativa de predição (sem execução de solução), inexistente ou sem entrada
  mantida MUST ser registrada como "sem suíte" para aquela combinação, com o motivo.

**Registro, retomada e saída**

- **FR-013**: A proveniência MUST ficar registrada em dois níveis: por conjunto de avaliação
  (comum a todas as combinações dele) a revisão e o hash do dataset, o hash dos mutantes, o hash
  das suítes do modelo, a versão do compilador e o número de repetições; por combinação o
  modelo, cenário, problema, status da suíte, origem (pasta e tentativa do modelo local), hash da
  suíte avaliada e versão do esquema.
- **FR-014**: Cada estrutura gravada MUST ter esquema formal versionado.
- **FR-015**: A avaliação MUST ser retomável. A unidade gravada é o conjunto × problema (os 3
  cenários juntos, gravados de uma só vez). Rodar de novo avalia, em cada problema, só os
  conjuntos pedidos que ainda não têm resultado completo, sem tocar nos prontos, e refaz do
  início o que ficou em gravação, sem duplicar nem corromper dados.
- **FR-016**: O módulo MUST permitir restringir a avaliação a um problema (e a um cenário) para
  conferência, e permitir vários trabalhadores em paralelo na mesma avaliação sem duas avaliarem a
  mesma combinação; o resultado não depende do número de trabalhadores.
- **FR-017**: O módulo MUST gerar uma tabela consolidada (uma linha por modelo × cenário × problema
  × alvo, com o veredito sob cada oráculo) e um relatório-resumo por modelo: combinações avaliadas,
  sem suíte, AC aprovado/reprovado, testes do AC por veredito, WAs e mutantes detectados, testes
  excluídos do oráculo corrigido, anomalias (`CE` de alvo) e tempo total de execução.
- **FR-018**: O módulo MUST empacotar o resultado final de cada conjunto de avaliação num pacote próprio com manifesto SHA-256 commitado, e oferecer verificação de
  integridade do pacote e da pasta descompactada.
- **FR-019**: O `cli check` MUST ganhar uma camada por pacote de avaliação, conferindo 1:1 com o
  dataset (200 problemas × 3 cenários, nada sobrando nem faltando), os arquivos permitidos e, com
  `--deep`, os hashes; faltas são aviso antes do empacotamento e falha depois, como nas camadas de
  suítes.
- **FR-020**: Nenhuma métrica é calculada por este módulo; ele não lê custos nem tokens.
- **FR-021**: Antes da execução completa, MUST rodar um piloto nos 5 problemas dos pilotos
  (`1000_B`, `1005_C`, `1008_B`, `1_B`, `61_B`) × 4 modelos × 3 cenários (60 combinações). O piloto
  mede o tempo de execução e é a amostra da conferência manual (SC-003). A decisão dos autores de
  seguir fica registrada antes da execução completa. Se nada que afete o resultado mudar depois do
  piloto, a execução completa continua a mesma, retomada, e reaproveita as 60 combinações. Se algo
  mudar, o piloto é guardado à parte e a execução completa começa numa pasta nova.

### Key Entities

- **Conjunto de avaliação**: o que se avalia de um modelo — `slm`, `gpt`, `gemini`, `claude`
  (suítes finais) e `slm-attempt1` (1ª tentativa do modelo local). Cada um tem a sua
  proveniência comum, o seu relatório e o seu pacote.
- **Combinação avaliada**: um modelo × cenário × problema (× tentativa, para o modelo local),
  com a proveniência (FR-013), o status da suíte, a marca "sem suíte" quando for o caso, e os
  resultados abaixo.
- **Resultado do AC por teste**: índice, veredito, tipo de erro, saída real, tempo e memória.
- **Resultado de alvo**: um WA ou mutante (identificador), detectado ou não sob cada oráculo, com
  o teste e o veredito que o detectaram.
- **Tabela consolidada**: uma linha por combinação × alvo, insumo da feature 010.
- **Relatório de avaliação**: o resumo de FR-017 por conjunto de avaliação.
- **Pacote de avaliação**: o resultado final empacotado com o manifesto de hashes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: As 2.400 combinações (4 modelos × 3 cenários × 200 problemas) têm resultado
  gravado, cada uma avaliada ou marcada "sem suíte" (esperado: 3 "sem suíte", todas do Claude).
- **SC-002**: Em 100% das combinações avaliadas, o AC tem um veredito para cada teste da suíte, e
  cada WA e mutante tem um veredito sob os dois oráculos.
- **SC-003**: Numa amostra de conferência manual (os 5 problemas dos pilotos, nos 4 modelos e 3
  cenários), 100% dos vereditos do AC e das detecções conferem com a execução manual da suíte.
- **SC-004**: Uma avaliação interrompida e retomada não reescreve as combinações já completas e
  produz, em todas as combinações, os mesmos vereditos, índices de teste e conjuntos de detectados
  de uma execução sem interrupção (campos de tempo e memória excluídos da comparação), salvo a
  instabilidade de margem do motor registrada no relatório.
- **SC-005**: A 1ª tentativa do modelo local tem resultado nas 600 combinações (avaliada ou "sem
  suíte"), separado do resultado da suíte final.
- **SC-006**: `cli check --deep` passa com a nova camada depois do empacotamento, e a verificação
  de integridade confere pacote e pasta descompactada.
- **SC-007**: A feature 010 consegue calcular todas as métricas confirmadas (sem C.5 e C.6) lendo
  só a saída deste módulo, sem executar nenhum código.

## Assumptions

- O motor de execução e a regra de comparação de saída são os do dataset, sem alteração.
- Veredito `passou` e `saída diferente` são tomados numa execução só (a comparação de saída é
  determinística); só os erros de execução são repetidos (FR-005a, FR-006a). A instabilidade de
  margem que ainda sobrar fica documentada como limitação.
- Cada programa (AC, WA, mutante) é compilado uma vez por problema e reaproveitado em todas as
  suítes do problema; compilar não altera o veredito.
- O oráculo corrigido usa o `AC_ref` porque ele é, por construção do dataset, a referência
  correta; os testes em que ele dá erro são justamente o sinal de entrada fora de especificação
  (causa `entrada_inválida` da métrica C.2).
- Só a 1ª tentativa do modelo local é avaliada isoladamente: é a única que a comparação "em pé
  de igualdade" usa (uma chamada contra uma).
- As suítes avaliadas são as dos pacotes da execução final; pilotos e pastas guardadas (`slm-piloto*`,
  `gemini-piloto1`) ficam fora.
- O tempo total de execução não é estimado aqui: é medido no piloto (FR-021).
- Os pacotes de avaliação seguem a exceção de versionamento do Princípio II (artefato que depende
  de execução real de código de terceiros no motor).

## Divergências e Decisões sobre a Metodologia

- **D1 — Curto-circuito só para WA e mutante (decidido pelos autores em 2026-11-04)**: a seção 4
  aplicava o curto-circuito a todo código-alvo; contra o `AC_ref` todos os testes rodam, com
  veredito e saída real por teste (FR-004), para separar as causas do falso positivo e servir ao
  oráculo corrigido.
- **D2 — Dois oráculos (decidido pelos autores em 2026-11-04)**: cada WA e mutante tem a detecção
  gravada sob o oráculo declarado pela IA e sob o oráculo corrigido pelo `AC_ref` (FR-008), base de
  TDF\*, MS\* e Δ_oráculo.
- **D3 — Erro de execução repetido (clarify de 2026-11-04)**: um erro de execução só vale se
  aparecer nas 3 execuções, no AC e nos alvos; senão o teste é instável (FR-005a, FR-006a).
- **D4 — 1ª tentativa do modelo local (decidido pelos autores em 2026-11-04)**: o conjunto
  `slm-attempt1` avalia a 1ª tentativa de cada combinação, para a comparação de uma chamada contra
  uma (FR-011).
- **D5 — Piloto obrigatório (clarify de 2026-11-04)**: 60 combinações nos 5 problemas dos pilotos,
  com conferência manual e decisão dos autores antes da execução completa (FR-021).
- **D6 — Saída por combinação e tabela consolidada (plano de 2026-11-04)**: em vez de só o registro
  CSV da seção 4, um JSON por combinação (com o AC teste a teste e os conjuntos de detectados) e o
  `results.csv` derivado dele, num pacote por conjunto de avaliação (FR-017, FR-018).
