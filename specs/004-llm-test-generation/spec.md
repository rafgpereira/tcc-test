# Feature Specification: Geração de Suítes de Teste pelos LLMs Comerciais

**Feature Branch**: `004-llm-test-generation`

**Created**: 2026-10-13

**Status**: Draft

**Input**: User description: "Módulo 004 — geração de suítes de teste pelos LLMs comerciais
(GPT-5.4-mini via API da OpenAI e Gemini 3.5 Flash via API do Google). Para cada um dos 200
problemas do dataset, cada um dos 3 cenários de contexto e cada um dos 2 modelos, gerar uma suíte
de casos de teste (entradas e saídas esperadas) e persisti-la no mesmo formato de `suite.json`
usado pelas suítes do SLM (módulo 003), para que a etapa de avaliação leia os dois do mesmo jeito.
Ideia central (oráculo por predição): ao contrário do SLM, que calcula as saídas executando uma
solução Python, os LLMs preveem diretamente a saída esperada de cada entrada; essa é a única
diferença intencional entre os modelos, todo o resto deve ser igual ao SLM. Decisões já tomadas:
mesmo dataset, cenários e `<context_data>` do 003; few-shot com o primeiro teste público; regras
de geração das entradas idênticas às do prompt principal do SLM; prompt em inglês com a estrutura
XML do PDF e `edge_cases_analysis` antes dos testes; JSON com schema estrito; chamadas stateless;
esforço de raciocínio `medium` e temperatura no padrão de cada API; novas tentativas só por falha
de formato, até um limite fixo, sem validação pelos testes públicos; falha de infraestrutura não
conta como tentativa; resposta crua, modelo e versão sempre registrados; tokens, custo e tempo
por chamada, dry-run com estimativa de custo e lote pago só com confirmação explícita; chaves só
no `.env`; retomada segura por combinação; relatório, pacote e camada no `cli check`. A decidir no
clarify: limite de tentativas e o que acontece ao esgotar; tamanho máximo das entradas;
reprodutibilidade sem seed/temperatura; onde o código fica; paralelismo e rate limit. Fora do
escopo: o SLM, a execução das suítes contra AC/WA/mutantes e o cálculo das métricas."

## Clarifications

### Session 2026-10-13

- Q: Quantas novas tentativas uma combinação recebe por falha de formato e o que acontece quando
  elas acabam? → A: 3 tentativas (as mesmas da predição do SLM); esgotadas, a combinação fica
  aguardando os autores, o comando segue com as demais e termina com código próprio listando-as,
  o pacote é recusado, e só um fechamento explícito dos autores com motivo
  (`discarded_manual`) tira a combinação desse estado (A1; FR-015, FR-016).
- Q: Qual o tamanho máximo de cada entrada que os LLMs devem gerar? → A: O mesmo do prompt
  principal do SLM ("at most about 50 elements and 20 lines"), sem número fixo de testes, para
  a única diferença entre os modelos ser o oráculo; o limite menor do template de predição do SLM
  não é usado (A2; FR-007).
- Q: Que status as suítes dos LLMs recebem no `suite.json`? → A: `accepted_predicted` em todas:
  o status diz a origem da saída esperada (`accepted`/`accepted_fallback` = calculada por um
  programa; `accepted_predicted` = escrita pelo modelo), com o mesmo significado nos 3 modelos;
  as métricas comparam por modelo, e só dentro do SLM as suítes previstas ficam separadas das
  calculadas (A6; FR-017; metodologia, seção 6, item 31).
- Q: Em que pacote do código fica o cliente dos dois LLMs comerciais? → A: Dentro de
  `src/ai_clients/`, com os comandos do SLM escolhendo o modelo por uma opção (por exemplo,
  `python -m ai_clients generate --model gpt`) e os dados em uma pasta por modelo em
  `data/suites/`; o SLM continua funcionando sem mudança de comportamento (A4; FR-029).
- Q: Como as chamadas aos dois modelos comerciais devem ser paralelizadas e protegidas contra o
  limite de requisições da API? → A: Chamadas simultâneas dentro de um processo, em número
  configurável por modelo no `.env` (padrão baixo, 4, ajustado depois do piloto), com a trava
  por combinação do SLM; o HTTP 429 é falha de infraestrutura, com espera crescente e respeito
  ao tempo de espera indicado pela API; os dois modelos podem rodar ao mesmo tempo, em processos
  separados (A5; FR-012, FR-024).

### Session 2026-10-15

- Q: As suítes dos dois LLMs comerciais viram um pacote único ou um pacote por modelo? → A: Um
  pacote por modelo, cada um com manifesto e relatório próprios; o pacote de um modelo só é
  recusado pelas combinações pendentes desse modelo, e o pacote do SLM não muda (FR-026, FR-029).
- Q: A geração tem um teto de gasto que interrompe a execução quando o custo acumulado passa de
  um valor? → A: Sim, teto obrigatório por invocação, informado junto com a confirmação; ao
  atingi-lo nenhuma chamada nova sai, as já enviadas terminam e são gravadas, o comando sai com
  código próprio e a retomada continua de onde parou (FR-022a).
- Q: As respostas pagas do piloto podem ser aproveitadas na execução completa? → A: Não; o
  piloto é uma execução separada, com relatório próprio versionado como registro do piloto, e a
  execução completa começa do zero, como nos pilotos 1 a 5 do SLM; o piloto 6 do SLM foi a
  exceção e entrou na execução final (metodologia, seção 7, item 40) (FR-023a; Assumptions,
  "Piloto").
- Q: O schema de saída deve ter, em cada teste, um campo para o modelo escrever o cálculo da
  saída esperada? → A: Não; o cálculo passo a passo fica no raciocínio interno do modelo
  (esforço `medium`), e o schema continua `edge_cases_analysis` + `tests[{input, output}]`
  (FR-004, FR-007).
- Q: O prompt vai como uma única mensagem de usuário, como no SLM, ou com `<system_rules>` no
  campo de instruções de sistema de cada API? → A: Uma única mensagem de usuário com o texto
  inteiro, sem campo de sistema nas duas APIs, como no SLM (A11; FR-002, FR-006).
- Q: Uma resposta com zero tokens de raciocínio deve só ser conferida no piloto ou barrar
  automaticamente toda a execução? → A: Barreira automática em toda execução, nos dois modelos: a
  resposta é gravada, o comando para na hora com código próprio, sem gastar tentativa, e os
  autores investigam antes de retomar (A12; FR-018a).
- Q: As chamadas ao Gemini enviam configurações de filtro de segurança explícitas ou usam o padrão
  da API? → A: Não enviam `safetySettings` (vale o padrão da API); cada bloqueio é gravado com a
  categoria informada e contado à parte no relatório, e os autores revisitam a decisão se o piloto
  mostrar bloqueios (A13; FR-003, FR-025).

## Decisões do clarify e do plano (A1 a A13)

Os autores pediram que estes pontos sejam decididos no `/speckit-clarify`, e não nesta
especificação. Os requisitos abaixo já os citam pelo rótulo (A1 a A6) no lugar exato em que a
decisão entra; a sugestão de cada um é só um ponto de partida para a conversa. As decididas ficam
marcadas e registradas em Clarifications. Situação depois do clarify de 2026-10-13: A1, A2, A4,
A5 e A6 decididas; A3 adiada para o planejamento técnico, porque depende do que a documentação
oficial de cada API diz sobre seed e temperatura (`research.md`). O clarify de 2026-10-15
levantou e decidiu mais quatro pontos (A7 a A10), que não estavam na lista dos autores; o
terceiro clarify, no mesmo dia, decidiu a partir da A11; e os
autores decidiram a A3 no mesmo dia, depois de conferida a documentação oficial (`research.md`,
A3). Nenhuma decisão em aberto.

- **A1 — Limite de tentativas por falha de formato e o que acontece ao esgotar** — **DECIDIDA
  em 2026-10-13**: 3 tentativas; ao esgotar, aguardar os autores e fechamento manual com motivo
  (`discarded_manual`), como no SLM (FR-022 e FR-022d do 003).
- **A2 — Tamanho máximo de cada entrada** — **DECIDIDA em 2026-10-13**: o mesmo do prompt
  principal do SLM ("at most about 50 elements and 20 lines"), sem número fixo de testes; o
  limite do template de predição do SLM (10 elementos e 10 linhas, 5 a 12 testes) foi rejeitado
  porque mudaria as entradas entre os modelos.
- **A3 — Reprodutibilidade sem seed nem temperatura** (FR-003, FR-019) — **DECIDIDA em
  2026-10-15 pelos autores** (`research.md`, A3, com as fontes oficiais): nenhum dos dois modelos
  recebe seed, temperatura ou outro parâmetro de amostragem. O GPT é chamado pelo snapshot datado
  `gpt-5.4-mini-2026-03-17`, na Responses API, com `store: false`, `reasoning.effort: "medium"`
  enviado explicitamente (o padrão do modelo é `none`) e `text.format` `json_schema` com
  `strict: true`. O Gemini é chamado como `gemini-3.8-flash`, por `generateContent`, com
  `thinking_level: "medium"` enviado explicitamente, sem temperatura e com saída JSON com schema.
  O `gemini-3.5-flash` do desenho aprovado foi descontinuado em 2026-10-08. Entre os substitutos,
  os autores escolheram o 3.8 Flash, GA e o Flash mais recente, em vez do 3.6, que o Google
  descreve como "previous-generation" (revisto no mesmo dia; o 3.6 foi a primeira escolha). Cada
  tentativa grava o modelo e a versão devolvidos, os parâmetros enviados e a resposta crua; a não
  reprodutibilidade bit a bit é limitação declarada.
- **A4 — Onde o código fica** — **DECIDIDA em 2026-10-13**: dentro de `src/ai_clients/`,
  reaproveitando a leitura do problema, a composição do prompt, o schema da suíte, as travas, o
  relatório, o pacote, o `close` e o `change-template` do SLM (FR-029).
- **A5 — Paralelismo e controle de rate limit** — **DECIDIDA em 2026-10-13**: chamadas
  simultâneas dentro de um processo, em número configurável por modelo no `.env` (padrão 4), com
  as travas por combinação do SLM; HTTP 429 é falha de infraestrutura, com espera crescente e
  respeito ao tempo de espera indicado pela API (FR-012, FR-024).
- **A6 — Status das suítes dos LLMs no `suite.json`** (levantada nesta especificação, não estava
  na lista dos autores) — **DECIDIDA em 2026-10-13**: `accepted_predicted` em toda suíte dos
  LLMs; o status diz a origem da saída esperada, com o mesmo significado nos 3 modelos, e a
  regra das métricas (metodologia, seção 6, item 31) é reescrita para não tratar esse status como
  exceção ao comparar modelos.
- **A7 — Pacote único ou por modelo** — **DECIDIDA em 2026-10-15**: um pacote por modelo, com
  manifesto e relatório próprios; as pendências de um modelo não bloqueiam o pacote do outro
  (FR-026).
- **A8 — Teto de gasto** — **DECIDIDA em 2026-10-15**: obrigatório por invocação, junto com a
  confirmação; ao atingi-lo nenhuma chamada nova sai e o comando sai com código próprio (FR-022a).
- **A9 — Piloto aproveitado ou descartado** — **DECIDIDA em 2026-10-15**: descartado; a execução
  completa começa do zero e só o relatório do piloto é versionado (FR-023a).
- **A10 — Campo de cálculo por teste no schema** — **DECIDIDA em 2026-10-15**: não há; o cálculo
  da saída fica no raciocínio interno do modelo (FR-004, FR-007).
- **A11 — Prompt numa mensagem só ou com instrução de sistema** — **DECIDIDA em 2026-10-15**:
  uma única mensagem de usuário com o texto inteiro, sem `instructions`/mensagem `developer` na
  OpenAI nem `system_instruction` no Gemini, como no SLM (FR-006).
- **A12 — Resposta sem raciocínio** — **DECIDIDA em 2026-10-15**: barreira automática em toda
  execução, nos dois modelos; zero tokens de raciocínio para o comando com código próprio, sem
  gastar tentativa (FR-018a).
- **A13 — Filtros de segurança do Gemini** — **DECIDIDA em 2026-10-15**: `safetySettings` não é
  enviado (padrão da API, como o GPT, que não tem ajuste equivalente); bloqueios gravados com a
  categoria e contados à parte; revisitar se o piloto mostrar bloqueios (FR-003, FR-025).

## User Scenarios & Testing *(mandatory)*

<!--
  Os "usuários" deste módulo são os dois autores do TCC, que precisam de uma suíte de testes por
  problema × cenário × modelo comercial, no mesmo formato das suítes do SLM, para a etapa de
  avaliação (execução contra AC/WA/mutantes e cálculo de TDF/MS/TFP/IIC). Diferente do SLM, cada
  chamada custa dinheiro, então saber o custo antes e nunca pagar duas vezes pela mesma resposta
  faz parte do valor entregue.
-->

### User Story 1 - Gerar a suíte de uma combinação com um modelo comercial (Priority: P1)

Para um problema, um cenário (caixa-preta: só `enunciado.md`; caixa-branca: só `AC_ref.cpp`;
híbrido: os dois) e um modelo (GPT-5.4-mini ou Gemini 3.8 Flash), os autores disparam a geração,
que envia uma única chamada *stateless* com o prompt do experimento, recebe uma resposta em JSON
com a análise de casos-limite e a lista de testes (entrada e saída esperada prevista pelo modelo),
persiste a resposta crua e grava a suíte no mesmo formato de `suite.json` do SLM.

**Why this priority**: é a capacidade mínima do módulo; sem ela não há suíte de LLM para avaliar,
e a comparação entre os 3 modelos, objetivo do TCC, não existe.

**Independent Test**: rodar a geração para 1 problema × 1 cenário × 1 modelo (ou com respostas
gravadas, sem chamar a API) e conferir que a pasta da combinação tem a resposta crua, os metadados
da chamada (modelo devolvido, tokens, custo, tempo) e um `suite.json` que o leitor de suítes do
SLM aceita sem mudança.

**Acceptance Scenarios**:

1. **Given** um problema completo do dataset, um cenário e um modelo, **When** a geração roda,
   **Then** o sistema envia exatamente uma requisição autocontida (sem histórico, sem conversa
   guardada pelo provedor), com o modelo, o esforço de raciocínio `medium` e o schema de saída
   estrito, e persiste a resposta crua antes de interpretá-la.
2. **Given** uma resposta JSON válida com pelo menos um teste utilizável, **When** ela é
   interpretada, **Then** o sistema grava o `suite.json` da combinação com os testes no contrato
   `input`/`output` do projeto, o status `accepted_predicted`, o modelo e o tamanho da suíte.
3. **Given** uma resposta vazia, que não é JSON, que viola o schema, cortada pelo teto de saída
   ou que é uma recusa do modelo, **When** ela é interpretada, **Then** a tentativa é registrada
   como falha de formato, com a razão, e uma nova chamada independente é feita, até 3 tentativas;
   depois delas a combinação aguarda os autores (FR-016).
4. **Given** os 3 cenários de um mesmo problema, **When** os prompts são montados, **Then** só o
   conteúdo de `<context_data>` muda entre eles, e o texto é o mesmo para os 2 modelos.

---

### User Story 2 - Saber o custo antes e nunca pagar sem confirmar (Priority: P1)

Antes de qualquer chamada paga, os autores rodam um dry-run que monta todos os prompts pedidos e
mostra, por modelo e no total, o número de chamadas e o custo estimado; o lote pago só começa com
uma confirmação explícita de quem executa, e cada chamada feita registra tokens, custo estimado e
tempo de resposta.

**Why this priority**: é exigência do projeto (custo observável, lote pago só com confirmação) e
protege o orçamento da dupla; uma execução de 1.200 combinações disparada por engano, ou repetida
por um erro de retomada, é um custo que não volta.

**Independent Test**: rodar o dry-run sobre todos os problemas e conferir que nenhuma chamada à
API foi feita e que a estimativa aparece por modelo e no total; rodar a geração sem a confirmação
e conferir que ela recusa sem chamar a API.

**Acceptance Scenarios**:

1. **Given** um dataset íntegro e os dois modelos configurados, **When** o dry-run roda, **Then**
   o sistema lista as combinações pendentes, os tokens de entrada estimados a partir dos prompts
   reais (com a razão caracteres/token declarada), a suposição de tokens de saída usada e o custo
   estimado por modelo e no total, sem nenhuma chamada a nenhuma API.
2. **Given** uma geração que faria chamadas pagas, **When** ela é disparada sem a confirmação
   explícita ou sem o teto de gasto, **Then** ela recusa antes da primeira chamada e diz como
   confirmar e informar o teto.
3. **Given** uma geração confirmada com um teto de gasto, **When** o custo acumulado da
   invocação atinge o teto, **Then** nenhuma chamada nova é enviada, as já em andamento terminam
   e são gravadas, o comando sai com o código próprio do teto mostrando o gasto, e uma nova
   invocação com `--resume` continua de onde parou.
4. **Given** uma chamada concluída, **When** ela é registrada, **Then** o registro tem os tokens de
   entrada (e os servidos de cache, quando a API informar), os de saída (e os de raciocínio, quando
   a API informar), o custo estimado pela tabela de preços da execução e o tempo de resposta.

---

### User Story 3 - Retomar sem duplicar, sem corromper e sem pagar de novo (Priority: P2)

Ao interromper a geração (queda de rede, rate limit, falha do provedor, interrupção manual) e
rodar de novo, os autores recebem exatamente a continuação do que faltava: combinações terminadas
não são refeitas, nenhuma resposta já recebida é pedida de novo, e cada combinação problema ×
cenário × modelo pode ser gerada ou retomada isoladamente.

**Why this priority**: sem isso, uma interrupção obrigaria a recomeçar e pagar de novo; é também
exigência do projeto (retomada segura).

**Independent Test**: interromper uma geração pequena (com uma API simulada) no meio de uma
chamada e no meio da gravação, retomar, e conferir que o resultado é igual ao de uma execução
sem interrupção, sem arquivo duplicado ou parcial e sem chamada repetida de tentativa já gravada.

**Acceptance Scenarios**:

1. **Given** uma geração interrompida depois de receber e gravar algumas respostas, **When** ela
   é retomada, **Then** nenhuma tentativa já gravada é pedida de novo e a contagem de tentativas
   de cada combinação continua de onde parou.
2. **Given** uma interrupção entre o envio de uma chamada e a gravação da resposta, **When** a
   geração é retomada, **Then** só essa chamada é refeita (o custo dela pode ser pago duas vezes,
   e isso é conhecido e aceito) e nada parcial dela fica no disco.
3. **Given** um pedido restrito a um problema, um cenário e um modelo, **When** a geração roda,
   **Then** só essa combinação é tratada, sem tocar nas demais.

---

### User Story 4 - Relatório, pacote e conferência para sustentar o TCC (Priority: P3)

Ao final da execução completa, os autores precisam de um relatório versionado com os números da
geração por modelo, cenário e status (tokens, custo, tempo, tamanho das suítes, falhas por razão),
de um pacote por modelo com manifesto de integridade, e de a conferência entre artefatos do projeto
(`python -m cli check`) cobrir também as suítes dos LLMs.

**Why this priority**: é o mesmo fechamento já exigido do SLM; sem relatório os números do TCC não
têm proveniência, e sem a camada no `check` nada garante que as 1.200 suítes estão completas e 1:1
com o dataset.

**Independent Test**: gerar relatório, pacote e `check` sobre uma execução de teste pequena e
conferir que os totais batem com os arquivos, que o manifesto confere com o pacote e que uma pasta
faltando ou sobrando é apontada pelo `check`.

**Acceptance Scenarios**:

1. **Given** uma execução terminada, **When** o relatório é gerado, **Then** ele traz, por modelo
   e por cenário, a contagem por status, as tentativas por razão de falha, a distribuição do
   tamanho das suítes, os tokens (entrada, cache, saída, raciocínio), o custo estimado e o tempo,
   e os identificadores de modelo efetivamente devolvidos pela API.
2. **Given** uma execução de um modelo com alguma combinação desse modelo aguardando os autores,
   **When** o pacote desse modelo é pedido, **Then** ele é recusado e lista as combinações
   pendentes; o pacote do outro modelo, sem pendências, é gerado normalmente.
3. **Given** suítes dos LLMs descompactadas, **When** `python -m cli check` roda, **Then** ele
   confere que cada um dos 200 problemas tem exatamente 3 cenários × 2 modelos, sem sobrar nem
   faltar, e em modo `--deep` que cada `suite.json` segue o schema.

---

### Edge Cases

- **Resposta cortada pelo teto de saída** (o raciocínio e a resposta disputam o mesmo teto): é
  falha de formato, contada à parte no relatório, como o `done_reason = "length"` do SLM.
- **Recusa ou bloqueio de segurança** (a API devolve uma recusa ou bloqueia o prompt): é falha de
  formato e consome tentativa; se o bloqueio se repetir nas 3 tentativas, a combinação fica
  aguardando os autores (FR-016). O motivo informado pela API é gravado, e no Gemini também a
  categoria do filtro (nenhum `safetySettings` é enviado; A13). Se o piloto mostrar bloqueios, os
  autores revisitam a A13 antes da execução completa.
- **Teste com entrada ou saída vazia, ou abreviada** (`...`, `…`, "repeated N times"): descartado
  sozinho e contado, com as mesmas regras do template de predição do SLM (FR-010 e FR-022c do 003);
  se nenhum teste sobrar, a resposta conta como falha de formato.
- **Entradas repetidas na mesma resposta**: fica a primeira ocorrência e as repetidas são contadas;
  se a mesma entrada aparece com saídas diferentes, a primeira fica e o conflito é contado à parte
  (é sinal de oráculo inconsistente, útil para a análise de falsos positivos).
- **Teste igual ao exemplo do few-shot**: mantido e contado (a regra "do not copy the example" é só
  do prompt, como no SLM).
- **Entrada que viola as restrições do enunciado**: o módulo não valida restrições numéricas, como
  no SLM; o risco é registrado como limitação.
- **Rate limit, erro 5xx, queda de rede, timeout de leitura**: falha de infraestrutura; a mesma
  chamada é refeita sem gastar tentativa, até um teto de repetições seguidas configurável; ao
  atingi-lo o comando para com erro de infraestrutura e a retomada refaz a mesma chamada.
- **Erro que não passa sozinho** (chave inválida ou ausente, cota ou crédito esgotado, modelo
  inexistente, pedido recusado pela API como malformado): o comando para na hora, sem gastar
  tentativa e sem repetir, com uma mensagem que diz o que corrigir.
- **Provedor muda a versão do modelo no meio da execução** (o identificador devolvido muda): cada
  tentativa grava o identificador devolvido; o relatório lista todos os vistos por modelo; a
  execução não para (a mudança fica registrada como limitação).
- **Configuração mudou entre uma rodada e a retomada** (modelo pedido, esforço de raciocínio,
  teto de saída, template, schema, limite de tentativas, dataset): a retomada recusa e lista o que
  mudou, como o `--resume` do SLM; tabela de preços, teto de gasto e opções de espera e
  paralelismo podem mudar sem recusa, porque não mudam as respostas.
- **Teto de gasto atingido no meio da execução**: nenhuma chamada nova sai; as em andamento
  terminam e são gravadas (o gasto pode passar um pouco do teto, e o excesso é mostrado); o comando
  sai com código próprio e a retomada continua com um teto novo (FR-022a).
- **Resposta sem raciocínio** (zero tokens de raciocínio, ou a contagem não vem): a resposta é
  gravada fora das tentativas, nenhuma chamada nova sai e o comando para com código próprio, sem
  gastar tentativa; os autores investigam antes de retomar (FR-018a).
- **Dataset local ausente ou diferente do manifesto**: a geração recusa antes de qualquer chamada,
  como no SLM.
- **Chave de API presente só para um dos modelos**: o modelo sem chave não roda; o outro roda
  normalmente.

## Requirements *(mandatory)*

### Modelos e chamadas

- **FR-001**: O sistema MUST, para cada um dos 200 problemas do dataset, cada um dos 3 cenários e
  cada um dos 2 modelos comerciais (GPT-5.4-mini, pela API da OpenAI; Gemini 3.8 Flash, pela API do
  Google, no lugar do Gemini 3.5 Flash do desenho do TCC, descontinuado; A3), fazer chamadas até
  obter uma suíte ou esgotar as 3 tentativas de FR-015 — 1.200 combinações.
- **FR-002**: Cada chamada MUST ser uma única requisição autocontida, sem histórico de nenhuma
  chamada anterior e sem estado guardado pelo provedor: na OpenAI, sem armazenamento da resposta
  (`store: false`) e sem referência a resposta anterior; no Gemini, uma chamada `generateContent`
  de um turno só, sem sessão de chat nem conteúdo em cache criado pelo pipeline (Constitution,
  Princípio III).
- **FR-003**: Cada modelo MUST ser chamado com esforço de raciocínio `medium` **enviado
  explicitamente** (`reasoning.effort` na Responses API da OpenAI, cujo padrão para o modelo é
  `none`; `thinking_level` no Gemini) e MUST NOT receber seed, temperatura nem outro parâmetro de
  amostragem (`temperature`, `top_p`, `top_k`, `seed`); a temperatura fica no padrão de cada API
  (A3, decidida em 2026-10-15). O Gemini também MUST NOT receber `safetySettings`: valem os
  filtros padrão da API, como no GPT, que não tem ajuste equivalente na chamada (A13, decidida em
  2026-10-15). O identificador pedido de cada modelo MUST ser o mais específico
  que o provedor oferecer e MUST ficar na configuração da execução: `gpt-5.4-mini-2026-03-17`
  (snapshot datado, nunca o apelido `gpt-5.4-mini`) e `gemini-3.8-flash`. O Google não oferece
  versão datada do 3.8 Flash, então a versão que respondeu é conhecida pelo `modelVersion` gravado
  em cada tentativa (FR-011). O 3.8 Flash substitui o `gemini-3.5-flash`, descontinuado, por ser o
  Flash GA mais recente; o `gemini-3.6-flash`, para onde o 3.5 é redirecionado, é descrito pelo
  Google como "previous-generation".
- **FR-004**: A saída MUST ser pedida em JSON com schema estrito (`text.format` do tipo
  `json_schema` com `strict: true` na OpenAI; `generationConfig.responseFormat.text` com
  `mimeType: "APPLICATION_JSON"` e `schema` no Gemini, conferido na API em 2026-10-16, que recusou
  o valor `"application/json"` da documentação; `research.md` R3), o mesmo schema nos 2
  modelos: um campo `edge_cases_analysis` (texto) antes de um campo `tests` (lista de
  objetos com `input` e `output`, ambos texto, sem nenhum outro campo).
- **FR-005**: As chaves de API MUST ficar só no `.env` (nunca no Git, nem na imagem Docker, nem em
  arquivo gravado pelo pipeline, nem em log); `.env.example` MUST documentar as variáveis novas sem
  valor.

### Prompt

- **FR-006**: O prompt MUST ser um único texto-base em inglês, igual para os 2 modelos, com a
  estrutura `<system_rules>`, `<context_data>`, `<few_shot_example>`, `<task>`, enviado inteiro
  como **uma única mensagem de usuário**, como no SLM: nenhuma parte vai no campo de instruções de
  sistema das APIs (`instructions` ou mensagem `developer` na OpenAI; `system_instruction` no
  Gemini), e o hash do prompt (FR-011) cobre esse texto inteiro (A11, decidida em 2026-10-15);
  entre os cenários
  MUST variar só `<context_data>`, com exatamente o mesmo conteúdo que o SLM recebe em cada cenário
  (FR-004 do 003), e o `<few_shot_example>` MUST ser o primeiro teste público do próprio problema,
  como no SLM (FR-005 do 003).
- **FR-007**: As regras de geração de entradas do prompt MUST ser as do prompt principal do SLM
  (`src/prompt_templates/slm_prompt.txt`, STEP 3): não copiar o exemplo; todo valor dentro das
  restrições; nunca entrada vazia ou inválida; contagem de casos coerente com os casos que seguem;
  cobertura do menor caso, das fronteiras, de valores extremos, de elementos repetidos, de dados
  ordenados e invertidos e de casos médios irregulares; nunca truncar ou abreviar; sem entradas
  repetidas; cada entrada um stdin completo; cada entrada curta, com no máximo cerca de 50
  elementos e 20 linhas (o mesmo texto do SLM; A2, decidida em 2026-10-13), sem número fixo de
  testes. A
  única parte diferente é a do oráculo: o modelo escreve a saída esperada exata de cada entrada,
  no formato exigido, calculada passo a passo antes de escrevê-la. Esse cálculo acontece no
  raciocínio interno do modelo (FR-003), não na resposta: o schema MUST NOT ter campo de cálculo
  ou justificativa por teste (decidido em 2026-10-15).
- **FR-008**: O prompt MUST exigir a análise de casos-limite (`edge_cases_analysis`) antes dos
  testes, com as mesmas instruções do STEP 1 do SLM (reescrever formato de entrada e restrições,
  a regra que define a resposta correta com suas fronteiras, e conferir o exemplo à mão); a ordem
  dos campos no schema MUST pôr a análise antes dos testes.
- **FR-009**: Uma execução MUST usar uma única versão do texto-base; o hash do texto MUST ser
  gravado na configuração da execução e em cada tentativa, e a retomada MUST recusar um texto
  diferente. Trocar o texto no meio da execução MUST seguir a mesma regra do SLM (comando
  explícito com motivo, tentativas da versão antiga movidas para fora da execução e refeitas;
  FR-022e do 003).

### Geração, persistência e interpretação

- **FR-010**: A resposta crua de toda chamada (inclusive das que falharam por formato) MUST ser
  persistida antes da interpretação, com gravação atômica, de modo que reinterpretar uma tentativa
  nunca exija chamar a API de novo.
- **FR-011**: Cada tentativa MUST registrar: problema, cenário, modelo pedido, identificador do
  modelo devolvido pela API, identificador da resposta, número da tentativa, hash do prompt e do
  texto-base, todos os parâmetros efetivamente enviados (sem seed; A3), motivo de término
  informado pela API,
  tokens de entrada, de cache, de saída e de raciocínio (os que a API informar), custo estimado,
  tempo de resposta e o resultado da interpretação.
- **FR-012**: O pipeline MUST poder ser interrompido e retomado a qualquer momento sem duplicar nem
  corromper nada e sem refazer uma chamada cuja resposta já foi gravada; cada combinação problema ×
  cenário × modelo MUST poder ser pedida e retomada isoladamente; chamadas e processos simultâneos
  (FR-024) MUST nunca tratar a mesma combinação ao mesmo tempo (Constitution, Princípio VII).
- **FR-013**: A interpretação MUST ser determinística e aplicar as regras do template de predição
  do SLM a cada teste: cerca Markdown que envolve a entrada ou a saída inteira é removida e contada;
  teste com entrada ou saída vazia é descartado e contado; teste com entrada ou saída abreviada é
  descartado e contado; entradas repetidas e conflitos de saída são tratados como em Edge Cases. Uma
  tentativa só gera suíte se sobrar ao menos um teste.
- **FR-014**: Não há validação das saídas previstas pelos testes públicos nem por qualquer
  execução: não existe programa a validar, e o `AC_ref.cpp` MUST NOT ser usado para aprovar,
  corrigir ou descartar um teste ou uma suíte (mesma regra do SLM, FR-017 do 003). Nenhum código é
  executado por este módulo.

### Tentativas e falhas

- **FR-015**: Uma tentativa MUST ser marcada como falha de formato, consumindo uma das **3
  tentativas** da combinação (A1), quando a resposta está vazia, não é JSON, viola o schema, foi
  cortada pelo teto de
  saída, é uma recusa ou um bloqueio de segurança, ou não sobra nenhum teste depois de FR-013. A
  razão MUST ser gravada com uma das razões fixas. Cada nova tentativa é uma chamada nova e
  independente; nenhuma outra razão (nem a qualidade das saídas) gera nova tentativa.
- **FR-016**: Uma combinação cujas 3 tentativas falharam por formato MUST ficar marcada como
  aguardando os autores: o comando MUST continuar com as demais combinações e, no fim, sair com um
  código de saída próprio listando todas as marcadas; o relatório MUST contá-las à parte e o pacote
  **daquele modelo** (FR-026) MUST ser recusado enquanto existir alguma desse modelo. Só um comando explícito dos autores tira a
  combinação desse estado, fechando-a com o status `discarded_manual` e um motivo obrigatório,
  gravados com a data; ela continua contando no N = 200. Nenhuma combinação termina sem suíte de
  outro jeito (mesma regra do SLM, FR-022 e FR-022d do 003; A1, decidida em 2026-10-13).
- **FR-017**: A suíte MUST ser gravada num `suite.json` com o mesmo contrato de arquivo do SLM
  (`schema_version` 2, as mesmas chaves de topo do `SlmSuite`, contrato de
  `specs/003-slm-test-generation/contracts/file-formats.md`, seção 4, e o mesmo `tests` no
  contrato `input`/`output`). Ela é validada por um schema próprio, `LlmSuite`, porque o `SlmSuite`
  confere cada tentativa contra a política de seeds do SLM (decidido no plano em 2026-10-15,
  `research.md` R1). A avaliação lê as suítes dos 3 modelos por um leitor comum, `SuiteView`, sem
  ramificar por modelo. O status de toda suíte
  dos LLMs MUST ser `accepted_predicted` (A6, decidida em 2026-10-13): o status diz a origem da
  saída esperada, com o mesmo significado nos 3 modelos, e nas métricas a comparação é por
  modelo, sem tratar esse status como exceção (só dentro do SLM as previstas ficam separadas);
  campos que só fazem sentido para o SLM (fase, temperatura, hardware, reserva) ficam com valor
  nulo ou fixo documentado, e qualquer campo novo MUST ser uma mudança deliberada e versionada do
  schema (Constitution, Princípio IV), compatível com as suítes do SLM já empacotadas.
- **FR-018**: Uma falha de infraestrutura (rede, timeout de leitura, rate limit, erro 5xx do
  provedor, resposta interrompida) MUST NOT consumir tentativa: a mesma chamada MUST ser refeita,
  com espera crescente e respeitando o tempo de espera indicado pela API, até um teto de
  repetições seguidas configurável no `.env`; atingir o teto encerra o comando com erro de
  infraestrutura, sem gravar a tentativa. Erros que não passam sozinhos (autenticação, cota ou
  crédito esgotado, modelo inexistente, pedido recusado como malformado) MUST encerrar o comando na
  hora, sem repetir e sem gastar tentativa.
- **FR-018a**: Toda resposta MUST ter a contagem de tokens de raciocínio conferida
  (`usage.output_tokens_details.reasoning_tokens` no GPT; `usageMetadata.thoughtsTokenCount` no
  Gemini), em toda execução, inclusive no piloto (A12, decidida em 2026-10-15). Se a contagem for 0
  ou não vier, sinal de que o esforço `medium` (FR-003) não foi aplicado: a resposta crua e os
  metadados MUST ser gravados para investigação, **fora** das tentativas da combinação (não gastam
  tentativa, não viram suíte e não entram nas métricas); nenhuma chamada nova é enviada (as já em
  andamento terminam e passam pela mesma conferência); e o comando MUST sair com um código de saída
  próprio, diferente dos de FR-016, FR-018 e FR-022a, dizendo o modelo, a combinação e a contagem
  recebida. Os autores investigam antes de retomar; na retomada, a chamada da combinação afetada é
  refeita (o custo da resposta barrada é pago e registrado no relatório à parte). O custo dessas
  respostas MUST contar no gasto da invocação (FR-022a).

### Reprodutibilidade e custo

- **FR-019**: A configuração de cada execução (modelos pedidos, parâmetros, schema, hash do
  texto-base, limite de tentativas, teto de saída, hash do manifesto do dataset) MUST ficar num
  arquivo da execução por modelo, comparado pela retomada. Não há seed (A3, decidida em
  2026-10-15): a proveniência de cada resposta é o identificador do modelo e da versão devolvidos
  pela API (`model` na OpenAI, `modelVersion` no Gemini), os parâmetros enviados e a resposta crua,
  gravados em cada tentativa (FR-010, FR-011). A não reprodutibilidade bit a bit das respostas e a possível
  troca de versão do modelo pelo provedor MUST ficar registradas como limitações (Assumptions e
  metodologia).
- **FR-020**: Toda chamada MUST registrar tokens consumidos, custo estimado e tempo de resposta
  (Constitution, Princípio VIII). O custo estimado MUST vir de uma tabela de preços por modelo
  (entrada, entrada servida de cache, saída; tokens de raciocínio cobrados como saída) com a data e
  a fonte dos preços, gravada na configuração da execução; uma mudança de preço não invalida a
  retomada, mas MUST ficar registrada.
- **FR-021**: MUST existir um dry-run que, sem nenhuma chamada paga, monta os prompts das
  combinações pedidas e mostra, por modelo e no total, o número de chamadas, os tokens de entrada
  e o custo estimado, com a suposição de tokens de saída declarada (de medições reais quando
  existirem, senão o teto de saída, como limite superior). O dry-run MUST NOT chamar nenhuma API,
  nem endpoint de contagem: os tokens de entrada são estimados a partir dos prompts reais pela
  razão caracteres/token de cada modelo (3,0, conservadora, antes do piloto; a razão medida no
  piloto depois dele), sempre declarada na saída (decidido no plano em 2026-10-15,
  `research.md` R9).
- **FR-022**: A geração MUST NOT fazer nenhuma chamada paga sem a confirmação explícita de quem
  executa, dada a cada invocação (nunca guardada de uma rodada para outra); sem ela, o comando
  recusa antes da primeira chamada. Uma restrição de escopo (`--problem`, `--scenario`, modelo,
  limite de combinações) MUST valer também para a estimativa mostrada antes da confirmação.
- **FR-022a**: Toda invocação que faz chamadas pagas MUST receber, junto com a confirmação, um
  teto de gasto em dólares para aquela invocação (decidido em 2026-10-15); sem o teto, o comando
  recusa antes da primeira chamada, como sem a confirmação. O gasto acumulado é a soma dos custos
  estimados (FR-020) das chamadas concluídas na invocação. Ao atingir ou passar o teto, o sistema
  MUST NOT enviar nenhuma chamada nova; as chamadas já enviadas (FR-024) terminam e são gravadas
  normalmente, por isso o gasto final pode passar do teto em até o custo dessas chamadas em
  andamento, e esse excesso MUST ser mostrado. O comando então sai com um código de saída próprio,
  diferente do de combinações aguardando os autores e do de erro de infraestrutura, informando o
  gasto da invocação; a retomada continua de onde parou, com um teto novo. O teto MUST NOT entrar
  na comparação da retomada, porque não muda as respostas. O teto vale **por processo**: com dois
  `generate --resume` do mesmo modelo rodando juntos, o gasto total pode chegar à soma dos dois
  tetos, e o comando MUST dizer isso na sua ajuda e no README.
- **FR-023**: O teto de tokens de saída de cada modelo MUST ser fixo e gravado na configuração; o
  valor é fixado no planejamento técnico, a partir de medição num piloto pequeno, grande o bastante
  para o raciocínio e a resposta das maiores combinações.
- **FR-023a**: O piloto MUST ser uma execução separada da execução completa (decidido em
  2026-10-15): suas respostas MUST NOT ser reaproveitadas na execução completa, mesmo que a
  configuração não tenha mudado, e a execução completa MUST começar do zero, com uma única
  configuração para as 1.200 combinações. O relatório do piloto MUST ser versionado como registro
  do piloto (como os relatórios dos pilotos do SLM); as respostas do piloto não entram no pacote
  (FR-026).
- **FR-024**: Um processo de geração MUST poder fazer chamadas simultâneas a um modelo, em número
  configurável por modelo no `.env` (padrão 4, ajustado depois do piloto; A5, decidida em
  2026-10-13), cada chamada de uma combinação diferente, protegida pela trava exclusiva por
  combinação do SLM (FR-026a do 003); os dois modelos MUST poder rodar ao mesmo tempo em
  processos separados. O HTTP 429 é falha de infraestrutura (FR-018), com espera crescente e
  respeito ao tempo de espera indicado pela API. O paralelismo MUST NOT mudar o conteúdo de
  nenhuma chamada nem o número de tentativas de nenhuma combinação, e o número de chamadas
  simultâneas não entra na comparação da retomada.

### Relatório, pacote e conferência

- **FR-025**: O sistema MUST produzir um relatório versionável com, por modelo e por cenário: a
  contagem por status; as tentativas por razão de falha; a distribuição do tamanho das suítes; os
  testes descartados por razão (vazios, abreviados, cercas removidas, repetidos, conflitos); as
  respostas cortadas pelo teto; as recusas e os bloqueios de segurança, à parte e, no Gemini, por
  categoria informada pela API (A13); as respostas barradas por falta de raciocínio, com o custo
  delas (FR-018a); os tokens (entrada, cache, saída, raciocínio); o custo estimado; o
  tempo total e por chamada; e os identificadores de modelo devolvidos pela API.
- **FR-026**: Ao final da execução completa que sustenta os números publicados, o sistema MUST
  poder compactar as suítes de **cada modelo comercial separadamente** (respostas cruas, metadados
  de cada tentativa, `suite.json`, configuração da execução) num pacote por modelo, cada um com
  manifesto SHA-256 e relatório próprios, no mesmo formato do dataset, dos mutantes e das suítes do
  SLM (decidido em 2026-10-15); o pacote de um modelo MUST ser recusado enquanto alguma combinação
  **desse modelo** aguardar os autores, e as pendências de um modelo MUST NOT bloquear o pacote do
  outro. O pacote do SLM não é refeito. Um comando de verificação MUST conferir o pacote de um
  modelo e, opcionalmente, a pasta descompactada contra o manifesto dele.
- **FR-027**: O `python -m cli check` MUST ganhar a camada das suítes dos LLMs: 200 problemas ×
  3 cenários × 2 modelos, 1:1 com o dataset, sem sobrar nem faltar; em `--deep`, cada `suite.json`
  e cada tentativa validados pelo schema (Constitution, Princípio II;
  `docs/verificacao-consistencia.md`).

### Fora do escopo desta especificação

- **FR-028**: Este módulo MUST NOT alterar o comportamento nem os artefatos do SLM (módulo 003),
  nem executar as suítes contra AC/WA/mutantes, nem calcular TDF, MS, TFP ou IIC. Mudanças de schema
  compartilhado (FR-017) MUST manter as suítes do SLM já empacotadas válidas sem regravá-las.

### Onde o código fica

- **FR-029**: O módulo MUST ficar dentro de `src/ai_clients/` (A4, decidida em 2026-10-13): os
  comandos existentes (`generate`, `report`, `package`, `verify`, `close`, `change-template`)
  MUST passar a aceitar a escolha do modelo, mantendo o SLM como está quando nenhum modelo
  comercial é pedido; as suítes de cada modelo ficam numa pasta própria em `data/suites/`, com
  configuração de execução, travas, relatório e manifesto próprios; o código do SLM é
  reaproveitado, não copiado. O README do módulo MUST passar a descrever os 3 modelos.

### Key Entities *(include if feature involves data)*

- **Combinação**: problema × cenário × modelo comercial; 1.200 no total; unidade de geração,
  retomada, trava e conferência.
- **Tentativa**: uma chamada autocontida a um modelo para uma combinação, com a resposta crua, os
  metadados da chamada (modelo devolvido, identificador da resposta, tokens, custo, tempo, motivo de
  término) e o resultado da interpretação (testes mantidos e descartados, ou a razão da falha de
  formato).
- **Suíte LLM**: os testes mantidos da tentativa aceita, no mesmo `suite.json` do SLM, com o status
  `accepted_predicted` (ou `discarded_manual`, FR-016), o modelo, o tamanho e a lista de
  tentativas.
- **Configuração da execução**: por modelo; parâmetros, schema, hash do texto-base, limite de
  tentativas, teto de saída, hash do dataset e tabela de preços. A retomada compara tudo isso,
  **menos** a tabela de preços (uma mudança de preço fica registrada, FR-020) e a data de criação.
- **Tabela de preços**: preço por milhão de tokens de entrada, de entrada em cache e de saída, por
  modelo, com data e fonte; base do custo estimado.
- **Estimativa de custo (dry-run)**: chamadas, tokens de entrada estimados (razão caracteres/token
  declarada), suposição de saída e custo
  estimado por modelo e no total, antes de qualquer chamada paga.
- **Resposta barrada**: uma resposta com zero tokens de raciocínio (ou sem a contagem), gravada
  fora das tentativas da combinação, com o mesmo conteúdo de uma tentativa e o custo; não gasta
  tentativa, não vira suíte e não entra nas métricas, mas conta no gasto da invocação e no
  relatório (FR-018a).
- **Relatório de geração LLM**: os agregados de FR-025, para citação no TCC.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Ao fim da execução completa, cada uma das 1.200 combinações está em exatamente um
  estado final (com suíte, ou, só por decisão explícita dos autores, `discarded_manual` com
  motivo), sem nenhum estado intermediário ou
  ambíguo no pacote.
- **SC-002**: 100% das chamadas são autocontidas: nenhuma reaproveita histórico nem estado guardado
  pelo provedor.
- **SC-003**: 100% das chamadas feitas têm tokens, custo estimado e tempo de resposta registrados, e
  o custo total do relatório é exatamente a soma dos custos das chamadas.
- **SC-004**: Zero chamadas pagas acontecem sem confirmação explícita (verificado por teste: sem a
  confirmação, nenhuma requisição sai), e o dry-run nunca faz chamada paga.
- **SC-004a**: Nenhuma chamada é enviada depois que o gasto acumulado da invocação atinge o teto
  (verificado por teste com API simulada e preços artificiais); o gasto final passa do teto em, no
  máximo, o custo das chamadas que já estavam em andamento.
- **SC-004b**: Nenhuma resposta com zero tokens de raciocínio vira suíte; na primeira delas, nenhuma
  chamada nova é enviada (verificado por teste com API simulada que devolve contagem 0 ou ausente,
  nos dois modelos).
- **SC-005**: Interromper e retomar em qualquer ponto não refaz nenhuma tentativa já gravada, não
  deixa arquivo parcial e produz as mesmas suítes que uma execução sem interrupção daria a partir
  das mesmas respostas gravadas; só uma chamada em andamento no momento da interrupção pode ser
  paga duas vezes.
- **SC-006**: Uma falha de infraestrutura nunca é contada como tentativa em nenhuma execução
  observada.
- **SC-007**: O leitor comum de suítes (`SuiteView`) lê 100% dos `suite.json` dos 3 modelos sem
  tratamento por modelo, e 100% das suítes do SLM já empacotadas continuam válidas no `SlmSuite`,
  sem serem regravadas.
- **SC-008**: `python -m cli check --deep` sai `OK` com dataset, mutantes, suítes do SLM e suítes
  dos LLMs descompactados, e `scripts/check_docs_sync.py --closing` termina com código 0 ao fechar
  a feature.
- **SC-009**: O relatório permite comparar o custo real com a estimativa do dry-run, por modelo, e a
  diferença fica registrada na metodologia.

## Assumptions

- **Usuários**: os dois autores executam o módulo em contêiner, com rede, usando chaves próprias de
  contas com faturamento ativo nas duas APIs; não há usuários externos.
- **Dependência do dataset**: este módulo consome `data/dataset` (descompactado de
  `data/dataset.zip`) exatamente como o SLM: `enunciado.md`, `AC_ref.cpp` e `testes.json` (primeiro
  teste público no few-shot); nenhuma mudança no dataset. Antes de rodar, `cli check --deep` MUST
  passar (Constitution, Princípio II).
- **Nada executado**: o módulo não compila nem executa código; roda inteiro no serviço com rede.
- **`generateContent` rotulado "Legacy"**: em 2026-10-15, a documentação do Google chama o
  `generateContent` de "Legacy" e recomenda a Interactions API, mas diz que ele "remains fully
  supported", sem data de desligamento. Os autores mantiveram o `generateContent` (A3; plano,
  `research.md` R13). O rótulo fica registrado como risco e limitação, e a decisão é revista se
  o desligamento for anunciado antes da execução completa.
- **Cache de prompt do provedor**: as duas APIs podem reaproveitar, do lado delas, o processamento
  de um início de prompt igual entre chamadas (cobrando menos por esses tokens). Isso não leva
  conteúdo de uma chamada para outra (cada resposta depende só do seu próprio prompt), então não
  fere o isolamento de FR-002; os tokens servidos de cache são registrados por causa do custo.
- **Nomes e preços dos modelos**: `GPT-5.4-mini` e `Gemini 3.5 Flash` são os modelos do desenho do
  TCC. Conferidos na documentação oficial em 2026-10-15 (`research.md`, A3), os identificadores são
  `gpt-5.4-mini-2026-03-17` e `gemini-3.8-flash`. O 3.8 Flash substitui o `gemini-3.5-flash`
  descontinuado: é o Flash GA mais recente, e o 3.6 é "previous-generation". Os preços vigentes da
  tabela da execução são fixados no planejamento técnico com data e fonte (FR-020), nunca supostos.
  O preço do 3.8 Flash dobra em 2027-01-01 (fim do preço introdutório); se a execução atravessar
  essa data, a mudança fica registrada (FR-020).
- **Onde o código fica**: em `src/ai_clients/` (A4, FR-029), que o README da raiz já apresenta
  como o módulo das chamadas aos 3 modelos; o README do módulo passa a cobrir os 3 modelos.
- **Sem conferência das saídas previstas**: uma saída prevista errada vira um falso positivo na
  avaliação; é exatamente o que a Taxa de Falsos Positivos mede, e por isso não há filtro aqui.
- **Tamanho da suíte**: sem número fixo de testes por suíte, como no SLM; o tamanho é registrado.
  A regra de tamanho/normalização entre os 3 modelos continua pendente (metodologia, seção 6, item
  26); como as entradas seguem o mesmo limite do SLM (A2), o tamanho das entradas não é uma
  diferença entre os modelos.
- **Piloto**: antes da execução completa, um piloto pequeno (por exemplo, os mesmos 5 problemas dos
  pilotos do SLM, nos 3 cenários e 2 modelos) mede tokens de saída, tempo, custo e taxa de falha
  de formato, e fixa o teto de saída (FR-023); o custo do piloto também passa pela confirmação e
  pelo teto de gasto (FR-022a). O piloto é descartado para a execução completa, que começa do
  zero; só o seu relatório é versionado (FR-023a). O piloto também confere a A3: que o `model`
  devolvido pelo GPT é o snapshot pedido e qual `modelVersion` o Gemini 3.8 Flash devolve. A
  conferência dos tokens de raciocínio maiores que 0 (o `medium` chegou de fato) deixou de ser só
  do piloto: é uma barreira automática em toda execução, nos dois modelos (FR-018a).
- **Versionamento**: as suítes dos LLMs seguem a mesma exceção de versionamento do SLM
  (Constitution, Princípio II, emenda 1.6.0): só o pacote da execução final é commitado.

## Divergências e Decisões sobre a Metodologia

<!--
  Registro exigido pela Constitution (Princípio I): divergências ou preenchimentos de lacunas em
  relação a docs/metodologia-referencia.md, para atualizar o texto final do TCC.
-->

A seção 3 da metodologia dá só a parametrização dos dois modelos comerciais (`reasoning_effort:
medium`, JSON estrito, `store: false`; `thinking_level: medium`, `generateContent`, JSON) e a marca
como pendente. Esta especificação preenche as lacunas abaixo; as decisões tomadas no clarify e
depois dele estão em A1 a A13.

- **D1 — Oráculo por predição como única diferença intencional (decidido pelos autores)**: as
  regras de entrada, o contexto de cada cenário e o few-shot são os do SLM, e só o oráculo muda
  (predição pelo modelo × execução de uma solução Python). Preenche uma lacuna: a metodologia
  dizia que os modelos de fronteira "preveem o `expected_output`", sem dizer que o resto do prompt
  seria igual ao do SLM.
- **D2 — Novas tentativas só por falha de formato, sem validação pelos testes públicos (decidido
  pelos autores)**: o SLM valida a solução nos testes públicos; aqui não existe programa a validar,
  e a predição de entradas novas não pode ser conferida pelos exemplos. Saídas previstas erradas
  ficam na suíte e aparecem como falsos positivos na avaliação.
- **D3 — Temperatura no padrão da API (decidido pelos autores)**: diferente do SLM (temperatura
  fixa por tentativa, FR-020 do 003); a metodologia não fixava temperatura para os modelos
  comerciais.
- **D4 — Mesmo `suite.json` do SLM (decidido pelos autores)**: a avaliação lê as suítes dos 3
  modelos do mesmo jeito; estende a decisão de 2026-09-30 (contrato `TestCase`, metodologia seção 6,
  item 29) ao arquivo inteiro da suíte.
- **D5 — Custo observável com dry-run e confirmação a cada invocação (decidido pelos autores)**:
  operacionaliza o Princípio VIII para este módulo.
- **D6 — Few-shot e versionamento iguais ao SLM (já decididos em 2026-09-29, D2 e D3 do 003)**:
  aplicados aqui como a metodologia já previa.
- **D7 — Nomes atuais dos parâmetros e troca do Gemini (decidido pelos autores em 2026-10-15,
  A3)**: os nomes da Tabela 2 do texto do TCC mudaram nas APIs. Na OpenAI, `reasoning_effort`
  virou `reasoning.effort` (Responses API), e o JSON estrito agora se pede por `text.format`
  `json_schema` com `strict: true`. No Google, o `Gemini 3.5 Flash` foi descontinuado em
  2026-10-08 (as chamadas a ele são redirecionadas para o `gemini-3.6-flash`). O modelo pedido
  passa a ser o `gemini-3.8-flash`, o Flash GA mais recente, porque o 3.6 é descrito pelo Google
  como "previous-generation" (o 3.6 chegou a ser escolhido e foi revisto no mesmo dia). O
  `mimeType: application/json` do texto vai em `generationConfig.responseFormat.text`, com o
  valor `"APPLICATION_JSON"` (`research.md` R3, conferido na API em 2026-10-16). Também ficam explícitos: o `reasoning.effort`
  enviado sempre (o padrão do GPT-5.4-mini é `none`), o snapshot datado do GPT e a ausência de
  seed e temperatura. O texto final do TCC deve trazer os nomes atuais e o modelo efetivamente
  usado.
