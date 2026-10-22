# Feature Specification: Revisão 2 do dataset (enunciados corrigidos)

**Feature Branch**: `007-dataset-revision`

**Created**: 2026-10-18

**Status**: Implemented (revisão 2 gerada em 2026-10-18; SLM refeito e pacote juntado em 2026-10-22)

**Input**: User description: "Módulo 007 — aplicar ao dataset a correção dos enunciados (revisão 2
do dataset). Com o relatório da feature 006 (152 expoentes perdidos em 79 problemas e 701 índices
em 74, contra o original do Codeforces), os autores decidiram em 2026-10-18 refazer o dataset: os
102 enunciados corrigidos automaticamente [...] mais os 15 da lista de revisão, corrigidos à mão
pelos autores com o original ao lado; os 83 fiéis e todos os outros arquivos ficam iguais. Gera um
dataset.zip e um manifesto novos (revisão 2), com a proveniência da revisão [...], e precisa de
emenda da constitution [...]. Efeitos: o SLM refaz só as combinações afetadas [...]; Gemini e GPT
ainda não começaram a execução completa e rodam direto com a revisão 2; mutantes não mudam [...]; o
cli check e todos os run.json passam a apontar para o manifesto novo. A decidir no clarify: [...]"

## Contexto

O dataset da revisão 1 (`data/dataset.zip`, 2026-09-22) traz enunciados em que o texto do site
perdeu as marcações: `10^5` aparece como `105` e `a_i` como `ai`. A conferência contra o original
do Codeforces (feature 006, relatório versionado de 2026-10-18) mediu:
- **152 expoentes perdidos, em 79 problemas**;
- **701 índices perdidos, em 74 problemas**;
- **83 problemas fiéis**;
- **102 corrigidos automaticamente**: só marcações inseridas, aprovados nas três conferências;
- **15 para revisão manual**: 12 por fórmula com mudança de forma, 3 por outra diferença.

No mesmo dia, os autores decidiram:
- refazer o dataset com os 102 corrigidos e os 15 revisados à mão;
- refazer no modelo local só as combinações afetadas;
- rodar a execução completa dos dois modelos comerciais, que ainda não começou, direto com a
  revisão nova.

## Clarifications

### Session 2026-10-18

- Q: Como os autores registram a correção feita à mão em cada um dos 15 enunciados da lista de
  revisão? → A: Um arquivo de decisão por problema (texto corrigido ou "manter", motivo, quem
  revisou, data), versionado junto da proveniência; a geração confere cada um (F1; US2, FR-001).
- Q: Como reaproveitar as suítes do SLM não afetadas sem misturar a origem com as refeitas? → A:
  Uma execução nova do SLM só com as combinações afetadas; o pacote final junta essa execução com
  as suítes não afetadas da execução da revisão 1, que fica intocada, e cada combinação é marcada
  com a execução e a revisão do dataset de onde veio (F2; US3, FR-006).
- Q: O pacote e o manifesto da revisão 1 continuam guardados no repositório? → A: Sim, renomeados
  como arquivo de auditoria (o pacote e o manifesto da revisão 1); os comandos usam só a revisão 2
  (F3; FR-003).
- Q: O que acontece com os relatórios dos pilotos e com o relatório dos mutantes, que guardam o
  hash da revisão 1? → A: Os pilotos ficam intocados (registram a revisão 1); o relatório dos
  mutantes é regenerado para a revisão 2, sem regerar os mutantes, e o pacote dos mutantes é
  conferido arquivo a arquivo e fica igual (F4; FR-010).

## Decisões já tomadas pelos autores (2026-10-18)

- **D1 — Escopo do dataset corrigido**: só os `enunciado.md` mudam; os 102 corrigidos
  automaticamente entram como estão, e os 15 da revisão entram com a correção feita à mão pelos
  autores; os 83 fiéis e todos os outros arquivos dos 200 problemas ficam byte a byte iguais.
- **D2 — Modelo local (SLM)**: só as combinações afetadas são refeitas (caixa-preta e híbrido dos
  problemas cujo enunciado mudou); as demais reaproveitam as suítes da execução atual.
- **D3 — Modelos comerciais**: a execução completa do GPT e a do Gemini, ainda não começadas, usam
  a revisão 2.

## Decisões do clarify (F1 a F4)

Os quatro pontos foram decididos em 2026-10-18 (Clarifications acima).

- **F1 — Registro dos 15 revisados à mão.** **DECIDIDA em 2026-10-18**: um arquivo de decisão por
  problema, com o texto corrigido (ou "manter"), o motivo, quem revisou e a data, versionado junto
  da proveniência; cada um passa pelas mesmas conferências automáticas que se apliquem.
- **F2 — Reaproveitar suítes do SLM sem misturar proveniência.** **DECIDIDA em 2026-10-18**: uma
  execução nova do SLM, com a revisão 2, só com as combinações afetadas; a execução da revisão 1
  fica intocada, e o pacote final junta as duas, dizendo, por combinação, de qual execução e de
  qual revisão do dataset ela vem.
- **F3 — A revisão 1 fica guardada?** **DECIDIDA em 2026-10-18**: sim, como arquivo de auditoria
  (o pacote e o manifesto da revisão 1, renomeados), para que os números já registrados continuem
  verificáveis; os comandos usam só a revisão 2.
- **F4 — Pilotos e relatório dos mutantes.** **DECIDIDA em 2026-10-18**: os relatórios dos pilotos
  ficam como estão (registram a revisão 1, que é a verdade da época); o relatório dos mutantes é
  regenerado apontando para a revisão 2, sem regerar os mutantes (que só dependem do código de
  referência, que não muda), e o pacote dos mutantes é conferido e fica igual.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Gerar a revisão 2 do dataset (Priority: P1)

Os autores aplicam ao dataset os enunciados corrigidos (os 102 automáticos e os 15 revisados à
mão) e obtêm um pacote e um manifesto novos, com a proveniência da revisão.

**Why this priority**: é o pedido central: o dataset que os modelos recebem passa a ter os
expoentes e índices do original.

**Independent Test**: a revisão 2 difere da revisão 1 só nos `enunciado.md` dos problemas
corrigidos, e em cada um só nas marcações (ou na correção revisada à mão); todos os outros arquivos
dos 200 problemas são byte a byte iguais; a conferência de integridade do dataset passa contra o
manifesto novo.

**Acceptance Scenarios**:

1. **Given** os 102 corrigidos e os 15 revisados, **When** a revisão 2 é gerada, **Then** só os
   `enunciado.md` desses problemas mudam, e o pacote e o manifesto novos são gravados.
2. **Given** a revisão 2, **When** a conferência contra o original roda de novo, **Then** não
   restam expoentes nem índices perdidos nos problemas corrigidos.
3. **Given** um corrigido que deixou de passar numa das conferências (por exemplo, o enunciado da
   revisão 1 mudou desde o relatório), **When** a geração roda, **Then** ela recusa e não grava
   nada.
4. **Given** a revisão 2 gerada, **When** a proveniência é lida, **Then** ela diz de qual relatório
   e de qual pacote de originais veio a correção, quais problemas mudaram e por quê.

---

### User Story 2 - Registrar os 15 revisados à mão (Priority: P1)

Os autores corrigem à mão os 15 enunciados da lista de revisão, com o original ao lado, e cada
correção é registrada e conferida antes de entrar na revisão 2.

**Why this priority**: sem esses 15, a revisão 2 fica incompleta (D1).

**Independent Test**: uma decisão registrada para um dos 15 entra na revisão 2; uma decisão que
muda texto além do necessário é recusada pelas conferências.

**Acceptance Scenarios**:

1. **Given** um dos 15, **When** os autores registram a correção, **Then** o registro guarda o
   texto, o motivo, quem revisou e a data (F1).
2. **Given** um dos 15 sem decisão registrada, **When** a revisão 2 é gerada, **Then** a geração
   recusa, listando o que falta.

---

### User Story 3 - Levar os comandos e as execuções para a revisão 2 (Priority: P2)

Depois da revisão 2, os comandos que conferem o dataset passam a usar o manifesto novo; o modelo
local refaz só as combinações afetadas (D2); os modelos comerciais rodam com a revisão 2 (D3).

**Why this priority**: a revisão 2 só vale para o experimento quando as suítes são feitas com ela.

**Independent Test**: a conferência entre artefatos passa com a revisão 2; a lista de combinações
afetadas do modelo local é exatamente caixa-preta e híbrido dos problemas cujo enunciado mudou;
nenhuma suíte final mistura revisões sem dizer de qual veio.

**Acceptance Scenarios**:

1. **Given** a revisão 2, **When** a conferência entre artefatos roda, **Then** dataset, mutantes
   e suítes estão coerentes com o manifesto novo, e cada suíte diz de qual revisão veio.
2. **Given** a execução do modelo local da revisão 1, **When** as combinações afetadas são
   refeitas, **Then** só elas são refeitas, com a revisão 2, e as demais são reaproveitadas com a
   proveniência registrada (F2).
3. **Given** a revisão 2, **When** um modelo comercial começa a execução completa, **Then** ele usa
   a revisão 2.

---

### Edge Cases

- **Problema corrigido cuja correção mudaria algo além das marcações**: recusado, vai para os
  autores.
- **Enunciado da revisão 1 diferente do que o relatório da 006 conferiu** (o relatório é de outro
  dataset): a geração recusa e pede para rodar a conferência de novo.
- **Algum dos 15 decide manter o texto atual** (por exemplo, `670_D2`, cuja página mudou): a decisão
  registra isso, com o motivo; o problema entra igual à revisão 1.
- **Combinação do modelo local afetada que já estava fechada à mão**: refeita como as demais.
- **Pilotos**: continuam registrando a revisão 1 (F4); a conferência entre artefatos não os trata
  como dano.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST gerar a revisão 2 do dataset aplicando só os enunciados corrigidos
  (D1): os 102 do relatório da 006, cada um aprovado de novo nas três conferências no momento da
  geração, e os 15 com decisão registrada pelos autores, num arquivo de decisão por problema com o
  texto corrigido (ou "manter"), o motivo, quem revisou e a data (F1).
- **FR-002**: Todos os outros arquivos dos 200 problemas MUST ficar byte a byte iguais aos da
  revisão 1, e isso MUST ser conferido na geração.
- **FR-003**: A revisão 2 MUST ter pacote e manifesto próprios, com a proveniência: a revisão de
  origem, o relatório e o pacote de originais da 006 (por hash), a lista de problemas alterados, o
  motivo de cada um e a decisão de cada um dos 15. O pacote e o manifesto da revisão 1 MUST ficar
  guardados, renomeados, como arquivo de auditoria, sem que nenhum comando os use (F3).
- **FR-004**: A geração MUST recusar sem gravar nada se faltar decisão para algum dos 15, se algum
  corrigido não passar nas conferências ou se o relatório da 006 não for do dataset da revisão 1.
- **FR-005**: Os comandos que conferem o dataset (integridade e conferência entre artefatos) MUST
  passar a usar a revisão 2.
- **FR-006**: O sistema MUST listar as combinações afetadas do modelo local (caixa-preta e híbrido
  dos problemas cujo enunciado mudou) e permitir refazer só elas, numa execução nova com a revisão
  2; a execução da revisão 1 MUST ficar intocada, e o pacote final MUST juntar as duas, marcando em
  cada combinação a execução e a revisão do dataset de onde veio (D2, F2).
- **FR-007**: A execução completa dos modelos comerciais MUST usar a revisão 2 (D3).
- **FR-008**: A mudança de regra sobre o dataset (extração e validação únicas) MUST ser registrada
  por emenda da constitution antes da geração da revisão 2.
- **FR-010**: O relatório dos mutantes MUST ser regenerado para a revisão 2 sem regerar os
  mutantes, e o pacote dos mutantes MUST ser conferido contra o seu manifesto e ficar igual; os
  relatórios dos pilotos MUST ficar intocados, registrando a revisão 1 (F4).
- **FR-009**: A documentação de uso, a metodologia e a lista de limitações do TCC MUST descrever a
  revisão 2, a correção aplicada e o que ela garante e não garante.

### Key Entities *(include if feature involves data)*

- **Revisão do dataset**: número, pacote, manifesto e proveniência.
- **Decisão de revisão manual**: problema, texto corrigido (ou manter), motivo, quem, quando.
- **Combinação afetada**: modelo local, problema e cenário que precisam ser refeitos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A revisão 2 difere da revisão 1 em exatamente os `enunciado.md` dos problemas
  corrigidos (102 mais os revisados que mudaram), e em nenhum outro arquivo.
- **SC-002**: A conferência contra o original, rodada sobre a revisão 2, não acha nenhum expoente
  nem índice perdido nos problemas corrigidos.
- **SC-003**: A conferência de integridade e a conferência entre artefatos passam com a revisão 2.
- **SC-004**: O número de combinações do modelo local refeitas é exatamente o de combinações
  afetadas, e nenhuma suíte final deixa de dizer de qual revisão do dataset veio.

## Assumptions

- **Autores**: os dois, no contêiner do projeto; os 15 revisados à mão são feitos por eles.
- **Os mutantes não mudam**: só dependem do código de referência, que não é alterado.
- **Os modelos comerciais ainda não começaram** a execução completa (2026-10-18).
- **A revisão 1 é preservada** para auditoria (F3, decidida em 2026-10-18).
- **Fora do escopo**: corrigir outros arquivos do dataset; mudar a forma das fórmulas LaTeX do
  formato novo; corrigir o que o original também não tem.
