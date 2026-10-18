# Feature Specification: Conferência dos enunciados contra o original do Codeforces

**Feature Branch**: `006-statement-fidelity`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "Módulo 006 — conferência dos enunciados contra o original do
Codeforces e correção opcional. Um comando do módulo dataset baixa uma vez, devagar, a página
original de cada um dos 200 problemas, guarda a cópia do HTML com hash num manifesto, e compara o
bloco do enunciado com o nosso enunciado.md sem depender de lista de padrões: toda diferença é
listada e classificada (expoente perdido, índice perdido, fórmula, imagem, tabela, outra), num
relatório versionado por problema. [...] Segunda parte, opcional e só por decisão dos autores:
gerar de novo o enunciado.md a partir do HTML original, em Markdown, com expoente como ^{...} e
índice como _{...}, aceitando cada enunciado novo só se três conferências passarem [...]. Aplicar a
correção gera um dataset.zip e um manifesto novos e afeta o experimento [...]; isso fica para
decisão dos autores no clarify, assim como a política de acesso ao Codeforces (ritmo, user-agent) e
o que fazer com imagens e tabelas."

## Contexto

Em 2026-10-16, ao inspecionar o prompt de `1_B` enviado ao Gemini, os autores viram `1 ≤ n ≤ 105`
onde o original diz `10^5`. Uma contagem por padrão de texto achou 71 enunciados assim. Em
2026-10-18, um piloto com 5 problemas comparou o nosso `enunciado.md` com a página original do
Codeforces (metodologia, seção 3) e mostrou que:

- a página tem dois formatos: o **antigo**, em que expoente e índice vêm marcados no HTML
  (sobrescrito e subscrito), e o **novo**, em que a fórmula vem escrita em LaTeX;
- no formato antigo, o nosso texto perdeu **os dois**: `10^5` virou `105`, `a_i` virou `ai`,
  `10^100000` virou `10100000`; no formato novo, o nosso texto preservou `10^5` e `a_i`;
- a contagem por padrão está incompleta: não viu `102_B` (`10^100000`) e nunca olhou os índices.

Os autores pediram uma conferência **automática e confiável**, que não dependa de memória nem de uma
lista de padrões escolhida à mão, e, se decidirem corrigir, um jeito de refazer os enunciados com
garantia de que nada do texto se perde.

## Clarifications

### Session 2026-10-18

- Q: Os enunciados corrigidos devem ser aplicados ao dataset do experimento, ou só gerados para
  revisão, com a aplicação decidida depois? → A: Só gerados para revisão, numa pasta separada; a
  aplicação ao dataset fica para uma decisão posterior dos autores, depois do relatório, e sai do
  escopo desta feature (E1; US4 e FR-009).
- Q: Como o comando deve acessar o site do Codeforces para baixar as 200 páginas? → A: Uma página
  por vez, com pelo menos 3 s entre pedidos e a identificação do projeto no pedido; só as 200
  páginas, uma única vez; baixar de novo só com uma opção explícita (E2; FR-001).
- Q: O que fazer quando o enunciado original tem imagem ou tabela? → A: Tabela vira tabela em
  Markdown automaticamente (e passa pelas mesmas três conferências); imagem é listada no relatório
  e o enunciado vai para revisão manual (E3; FR-008).
- Q: No enunciado corrigido, como marcar o expoente e o índice? → A: Sempre com chaves:
  `10^{5}`, `a_{i}`, `10^{18}` (E4; FR-007). Os enunciados do formato novo, que já trazem
  `10^5` e `a_i` sem perda, ficam como estão.

## Decisões do clarify (E1 a E4)

Os autores pediram que estes pontos fossem decididos no `/speckit-clarify`; os quatro foram
decididos em 2026-10-18 (Clarifications acima). Os requisitos os citam pelo rótulo.

- **E1 — A correção é aplicada ao dataset do experimento?** Gerar os enunciados corrigidos é sempre
  possível (em pasta separada, para revisão). Aplicá-los ao dataset muda o `dataset.zip` e o
  manifesto, e os três modelos têm de receber o mesmo texto: o modelo local já terminou com os
  enunciados atuais, o Gemini pode ter começado e o GPT não começou. **DECIDIDA em 2026-10-18**: a
  feature entrega a conferência e os enunciados corrigidos **para revisão**; aplicar fica para uma
  decisão separada dos autores, depois de verem o relatório, com o plano de refazer o que for
  preciso nos modelos (fora do escopo desta feature).
- **E2 — Política de acesso ao Codeforces.** **DECIDIDA em 2026-10-18**: um pedido por vez, com
  pelo menos 3 segundos entre pedidos, identificação do projeto no pedido, só as 200 páginas, uma
  única vez (a cópia guardada é reaproveitada; baixar de novo só com uma opção explícita).
- **E3 — Imagens e tabelas no enunciado.** O texto não as reproduz. **DECIDIDA em 2026-10-18**:
  a tabela é convertida automaticamente em tabela Markdown e passa pelas mesmas três conferências;
  a imagem é listada no relatório como diferença do tipo "imagem" e o enunciado com ela vai para
  revisão manual, nunca é convertido automaticamente.
- **E4 — Formato da marcação no Markdown corrigido.** **DECIDIDA em 2026-10-18**: sempre com
  chaves, `^{...}` para expoente e `_{...}` para índice (`10^{5}`, `a_{i}`, `10^{18}`), sem
  ambiguidade quando o expoente ou o índice tem mais de um caractere. Os enunciados do formato novo,
  que já trazem `10^5` e `a_i` sem perda, não são reescritos.

## User Scenarios & Testing *(mandatory)*

<!--
  Os "usuários" são os dois autores do TCC. Eles precisam saber, com evidência que não dependa de
  memória nem de suposição, o que se perdeu entre o enunciado original e o texto enviado aos
  modelos, para decidir se corrigem e para descrever a limitação no TCC.
-->

### User Story 1 - Conferir os 200 enunciados contra o original (Priority: P1)

Os autores rodam um comando que obtém a página original de cada problema e compara o enunciado
original com o `enunciado.md` do dataset, listando cada diferença com o trecho e o tipo, num
relatório por problema e num resumo geral.

**Why this priority**: é o pedido central: uma validação automática e confiável, que substitui a
contagem por padrão como fonte de verdade sobre o que se perdeu.

**Independent Test**: sobre os 5 problemas do piloto, o relatório mostra para `161_A` 4 expoentes
e 21 índices perdidos, para `1_B` 2 expoentes, para `15_A` 6 índices, para `102_B` 1 expoente e para
`1000_B` nenhuma perda, sem alterar nenhum arquivo do dataset.

**Acceptance Scenarios**:

1. **Given** o dataset íntegro e as páginas originais, **When** a conferência roda, **Then** cada
   problema tem no relatório a lista de diferenças, cada uma com o tipo (expoente perdido, índice
   perdido, fórmula, imagem, tabela, outra), o trecho do original e o trecho do nosso texto.
2. **Given** um enunciado no formato novo cuja fórmula foi preservada, **When** a conferência roda,
   **Then** o problema aparece sem perdas.
3. **Given** uma diferença que não é de nenhum tipo conhecido, **When** a conferência roda,
   **Then** ela aparece como "outra", com o trecho, e nunca é ignorada.
4. **Given** que o original tem título, limites de tempo e memória e o nosso texto tem os exemplos
   no fim, **When** a conferência roda, **Then** essas partes não contam como diferença.
5. **Given** qualquer execução da conferência, **When** ela termina, **Then** nenhum arquivo do
   dataset, dos mutantes ou das suítes foi alterado.

---

### User Story 2 - Guardar o original com integridade (Priority: P1)

A primeira execução guarda a cópia de cada página original com o hash num manifesto; as seguintes
usam a cópia guardada, sem acessar o site, e conferem que ela não mudou.

**Why this priority**: sem a cópia guardada a conferência não é reprodutível (o site pode mudar ou
ficar fora do ar), e o acesso ao site deve ser mínimo (E2).

**Independent Test**: rodar a conferência duas vezes: a segunda não faz nenhum acesso à internet e
dá o mesmo relatório; alterar um byte de uma cópia guardada faz a conferência recusar.

**Acceptance Scenarios**:

1. **Given** nenhuma cópia guardada, **When** a conferência roda, **Then** cada página é obtida uma
   vez, no ritmo de E2, e guardada com o hash no manifesto.
2. **Given** as cópias guardadas e o manifesto, **When** a conferência roda de novo, **Then** nenhum
   acesso à internet é feito e o relatório é o mesmo.
3. **Given** uma cópia guardada alterada, **When** a conferência roda, **Then** ela recusa,
   dizendo qual cópia diverge do manifesto.
4. **Given** uma página que não pôde ser obtida (fora do ar, recusada), **When** a conferência
   roda, **Then** o problema é marcado como não conferido, os demais seguem, e rodar de novo tenta
   só os que faltam: os que nunca foram obtidos e os que falharam por um erro temporário (site
   sobrecarregado). Um erro definitivo (página inexistente, página sem o enunciado) só é tentado de
   novo quando os autores pedem explicitamente.

---

### User Story 3 - Gerar os enunciados corrigidos para revisão (Priority: P2)

Os autores pedem a geração dos enunciados corrigidos: cada um é refeito a partir do original, em
Markdown, com expoentes e índices marcados (E4), e só é aceito se passar nas três conferências;
os aceitos e os que precisam de revisão ficam numa pasta separada, sem tocar no dataset.

**Why this priority**: é o caminho para corrigir, mas a decisão de aplicar é separada (E1); a
conferência (US1) já é útil sem isso.

**Independent Test**: para `161_A`, o enunciado gerado tem `10^{5}` e `a_{i}` nos lugares certos,
passa nas três conferências e fica na pasta de revisão; o `enunciado.md` do dataset não muda.

**Acceptance Scenarios**:

1. **Given** um enunciado do formato antigo, **When** a geração roda, **Then** o novo enunciado tem
   cada expoente e índice do original marcado, e o resto do texto igual ao atual.
2. **Given** um enunciado gerado, **When** as três conferências rodam, **Then** ele só é aceito se
   (a) tirando as marcações, o texto é igual ao texto do original; (b) todo expoente e índice do
   original aparece marcado; (c) a diferença para o `enunciado.md` atual está só nas marcações.
3. **Given** um enunciado que falha em alguma conferência, ou que tem imagem (E3), **When** a
   geração roda, **Then** ele vai para a lista de revisão manual, com o motivo, e não é aceito.
4. **Given** um enunciado com tabela (E3), **When** a geração roda, **Then** a tabela vira tabela
   em Markdown, com as mesmas células do original, e o enunciado só é aceito se passar nas três
   conferências.
5. **Given** um enunciado do formato novo, já sem perda, **When** a geração roda, **Then** ele é
   mantido igual ao atual.

---

### Fora desta feature - Aplicar a correção ao dataset

Decidido em 2026-10-18 (E1): aplicar os enunciados corrigidos ao dataset do experimento **não** faz
parte desta feature. Depois do relatório, os autores decidem se aplicam; se decidirem, isso é feito
à parte (novo pacote e manifesto do dataset e o plano de refazer as combinações afetadas dos
modelos), com os enunciados aceitos que esta feature deixa prontos para revisão.

---

### Edge Cases

- **Problema que não existe mais no site, ou página com formato inesperado** (sem o bloco do
  enunciado): marcado como não conferido, com o motivo; nunca tratado como "sem perdas".
- **Enunciado traduzido** (o dataset marca `is_description_translated`): o original pode estar em
  outro idioma; a conferência compara com a página em inglês e, se não houver, marca como não
  conferido.
- **Fórmula do formato novo com comandos que o nosso texto converteu** (`\le` em `≤`, `\lt` em `<`,
  `\dots` em `...`): equivalências conhecidas não contam como perda; uma conversão desconhecida
  aparece como "fórmula".
- **Espaços**: o original usa espaço fino e quebras diferentes; diferenças só de espaço não contam.
- **Imagens e tabelas** (E3): a tabela vira tabela em Markdown e é conferida como o resto do
  texto; a imagem é listada e o enunciado vai para revisão.
- **Site fora do ar ou recusando pedidos**: a execução para de pedir, guarda o que já obteve e diz
  como continuar.
- **Exemplos**: o nosso texto traz os exemplos no fim; eles já são conferidos contra o
  `testes.json` pela visualização do pedido e ficam fora desta comparação.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST obter, para cada problema do dataset, a página original indicada pelo
  contest e pelo índice do `metadata.json`, uma única vez, um pedido por vez, com pelo menos 3 s
  entre pedidos e a identificação do projeto no pedido (E2, decidida em 2026-10-18); obter de novo
  uma página já guardada só com uma opção explícita.
- **FR-002**: O sistema MUST guardar cada página obtida e registrar o hash dela num manifesto; as
  execuções seguintes MUST usar a cópia guardada, sem acessar a internet, e MUST recusar uma cópia
  que diverge do manifesto.
- **FR-003**: O sistema MUST comparar o enunciado original com o `enunciado.md` do dataset e listar
  **toda** diferença, sem depender de uma lista de padrões: cada uma com o tipo (expoente perdido,
  índice perdido, fórmula, imagem, tabela, outra), o trecho do original e o trecho do nosso texto.
- **FR-004**: A comparação MUST ignorar o que não faz parte do enunciado em um dos lados (título,
  limites de tempo e memória, exemplos) e as diferenças só de espaço, e MUST tratar os dois formatos
  da página (marcação de expoente e índice; fórmula em LaTeX).
- **FR-005**: O sistema MUST gravar um relatório versionado com, por problema, as diferenças e o
  estado (conferido sem perda, conferido com perdas, não conferido e por quê), e um resumo com as
  contagens por tipo.
- **FR-006**: A conferência MUST NOT alterar nenhum arquivo do dataset, dos mutantes ou das suítes.
- **FR-007**: O sistema MUST poder gerar, numa pasta separada, os enunciados refeitos a partir do
  original em Markdown, com expoente marcado como `^{...}` e índice como `_{...}`, sempre com
  chaves (E4, decidida em 2026-10-18); um enunciado sem perda é mantido igual ao atual.
  **Decidido no planejamento (2026-10-18, Milena; `plan.md` S2)**: o corrigido é o
  `enunciado.md` atual com as marcações que o **original** tem inseridas nos lugares que a
  comparação indica (e as tabelas convertidas), em vez de um texto refeito do zero a partir do
  HTML; assim os exemplos, os espaços e as quebras do dataset ficam iguais, e a conferência (c)
  vale por construção.
- **FR-008**: Cada enunciado gerado MUST ser aceito só se passar nas três conferências: (a) sem as
  marcações, igual ao texto do original; (b) todo expoente e índice do original marcado; (c)
  diferença para o `enunciado.md` atual só nas marcações (a de uma tabela inclusive). Uma tabela do
  original MUST virar tabela em Markdown com as mesmas células (E3, decidida em 2026-10-18). Os que
  falham, e os que têm imagem (E3), MUST ir para uma lista de revisão manual com o motivo.
- **FR-009**: Nenhum comando desta feature MUST alterar o `enunciado.md` do dataset nem o pacote ou
  o manifesto dele; os enunciados corrigidos ficam só na pasta de revisão (E1, decidida em
  2026-10-18: aplicar ao dataset é uma decisão posterior dos autores, fora desta feature).
- **FR-010**: A documentação de uso do módulo `dataset` e a referência de comandos da raiz MUST
  descrever o comando; a metodologia MUST registrar os números medidos.

### Key Entities *(include if feature involves data)*

- **Cópia do original**: a página de um problema como foi obtida, com o hash e a data.
- **Diferença**: um ponto em que o original e o nosso texto divergem: tipo, trecho de cada lado e
  posição.
- **Relatório de fidelidade**: por problema, o estado e as diferenças; no total, as contagens por
  tipo e a lista dos não conferidos.
- **Enunciado corrigido**: o Markdown gerado do original, com o resultado das três conferências
  (aceito ou para revisão, com o motivo).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Nos 5 problemas do piloto, o relatório reproduz as perdas medidas à mão em 2026-10-18
  (`161_A`: 4 expoentes e 21 índices; `1_B`: 2 expoentes; `15_A`: 6 índices; `102_B`: 1 expoente;
  `1000_B`: nenhuma).
  **Medido em 2026-10-18 (`research.md` R9)**: `check-statements --problem` com os 5 do piloto (2026-10-18, revisão `9df4f0e` mais a implementação não commitada): as 5 páginas baixadas de novo pelo comando (HTTP 200, cerca de 31 s com a subida do contêiner); `161_A` 4 `lost_exponent` e 21 `lost_index`, `1_B` 2 `lost_exponent`, `15_A` 6 `lost_index`, `102_B` 1 `lost_exponent` (`10^{100000}`), `1000_B` `faithful` (formato LaTeX); nenhuma diferença `other`, `formula`, `image` ou `table` — exatamente a contagem feita à mão no piloto (SC-001).
- **SC-002**: Os 200 problemas terminam conferidos ou com o motivo de não terem sido conferidos;
  nenhum fica sem estado.
  **Os 200 (2026-10-18, `research.md` R10)**: 200 de 200 com estado (SC-002); segunda execução sem acesso ao site e com o mesmo relatório (SC-003); 70 dos 71 da contagem antiga confirmados e 9 novos (SC-005); 102 corrigidos com as três conferências (SC-004).
- **SC-003**: Uma segunda execução, com as cópias guardadas, não acessa a internet e dá exatamente o
  mesmo relatório.
- **SC-004**: Nenhum enunciado corrigido aceito difere do original em outra coisa que não as
  marcações (verificado pelas três conferências em 100% dos aceitos).
- **SC-005**: O relatório permite dizer, para cada um dos 71 problemas da contagem anterior, se a
  perda é confirmada pelo original, e quantos problemas a contagem anterior deixou de ver.

## Assumptions

- **Usuários**: os dois autores, no contêiner com rede do projeto.
- **A página do Codeforces é a referência**: o dataset de origem veio dela; o piloto confirmou que o
  nosso texto é a página achatada, com as marcações perdidas.
- **O acesso ao site é mínimo e uma vez só** (E2); a reprodutibilidade vem da cópia guardada com
  hash, não do site.
- **Nada muda no experimento sem decisão dos autores** (E1): a conferência e a geração para revisão
  só leem o dataset.
- **Exemplos fora**: os exemplos do enunciado já são conferidos contra `testes.json` pela feature
  005; esta feature compara só o texto do enunciado.
- **Fora do escopo**: aplicar os enunciados corrigidos ao dataset (E1); corrigir outros campos do
  dataset; reescrever enunciados à mão; refazer as suítes dos modelos (tudo isso é decidido e feito
  à parte, se a correção for aplicada).
