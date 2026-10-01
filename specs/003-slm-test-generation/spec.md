# Feature Specification: Geração de Suítes de Teste pelo SLM

**Feature Branch**: `003-slm-test-generation`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Módulo 003 — geração de suítes de teste pelo SLM
(Qwen2.5-Coder-7B, local via Ollama). Para cada um dos 200 problemas do dataset e para cada um
dos 3 cenários de contexto (caixa-preta, caixa-branca, híbrido), gerar uma suíte de casos de
teste (entrada / saída esperada) usando o SLM, e persistir essas suítes para a etapa de
avaliação. Ideia central (oráculo por execução): o SLM gera ENTRADAS que exploram casos-limite
e, na mesma resposta, uma solução do problema em Python cuja única função é calcular as saídas;
o pipeline executa essa solução sobre as entradas geradas, em ambiente isolado, e o
`expected_output` é o que a execução produziu — o SLM nunca prevê a saída, e a solução Python
não é objeto de avaliação. Decisões detalhadas de modelo, formato de resposta, prompt,
reprodutibilidade, retentativas, fases de geração/execução e registro de proveniência tomadas
em rodada de pesquisa e discussão técnica prévia à especificação (registrada em documento
compartilhado com a dupla), confirmadas por ambos os autores antes deste `/speckit.specify`, e
refinadas nas 3 perguntas de esclarecimento respondidas nesta sessão (ver Clarifications); as
decisões D1–D3 estão em Divergências.
Fora do escopo: clientes do GPT-5.4-mini e do Gemini 3.5 Flash, execução das suítes contra
WA/mutantes e cálculo das métricas."

## Clarifications

### Session 2026-09-29

- Q: Quando as entradas geradas falham individualmente (FR-019) por razões diferentes e nenhuma
  sobrevive (ex.: metade com erro de execução, metade com timeout), isso conta como a tentativa
  inteira falhando, mesmo não sendo 100% de uma única razão pura? → A: Sim — FR-018(c)/(d) são
  combinadas numa única condição: a solução falha (erro de execução ou timeout, em qualquer
  combinação entre as duas) em 100% das entradas geradas.
- Q: O "hardware em que o Ollama rodou" (FR-025) é registrado por configuração manual do
  operador ou autodetectado da máquina que roda o pipeline? → A: Configuração manual — o
  operador informa uma etiqueta de hardware via `.env` (junto do endereço do Ollama), e o
  pipeline só grava esse texto; não há autodetecção, o que seria incorreto quando o Ollama roda
  num servidor remoto (FR-003).
- Q: Uma falha de infraestrutura na chamada ao Ollama (serviço inacessível, timeout de conexão,
  erro do lado do servidor) consome uma das 6 tentativas do problema × cenário? → A: Não — a
  mesma chamada é refeita com a **mesma seed** quando o serviço volta a responder; só as 3 razões
  de conteúdo (FR-018) consomem o orçamento (FR-018a, SC-007). (Registrada em 2026-09-30: a
  pergunta foi respondida na sessão de 2026-09-29, mas tinha ficado fora desta lista. O teto de
  repetições consecutivas acrescentado em 2026-09-30, FR-018a, não muda essa regra: atingi-lo
  encerra o comando sem gastar tentativa, e a retomada usa a mesma seed.)

## User Scenarios & Testing *(mandatory)*

<!--
  Os "usuários" deste módulo são os dois autores do TCC, que precisam de uma suíte de testes por
  problema × cenário gerada pelo SLM local, com saída esperada calculada por execução real (não
  prevista pelo modelo), para alimentar a etapa de avaliação (execução contra AC/WA/mutantes e
  cálculo de TDF/MS/TFP/IIC) nos mesmos moldes já usados para o dataset e os mutantes.
-->

### User Story 1 - Gerar candidatos de suíte via SLM, sem executar nada (Priority: P1)

Para cada um dos 200 problemas e cada um dos 3 cenários de contexto (caixa-preta: só
`enunciado.md`; caixa-branca: só `AC_ref.cpp`; híbrido: os dois), os autores disparam a fase de
geração — com rede, contra o Ollama — que envia uma única chamada *stateless* por tentativa e
persiste a resposta crua, as entradas propostas pelo modelo e a solução Python de referência
que o próprio modelo escreveu, junto com a seed usada, sem rodar nenhum código Python ainda.

**Why this priority**: é a capacidade mínima do módulo — sem a chamada ao modelo e a
persistência confiável da resposta crua, nenhuma etapa seguinte (execução, avaliação) tem o que
consumir, e uma falha de rede não pode obrigar a repetir uma chamada já bem-sucedida.

**Independent Test**: pode ser testado isoladamente rodando a geração sobre um problema e um
cenário, e inspecionando que o resultado persistido contém a resposta crua completa, a lista de
entradas propostas, o código Python de referência e a seed — mesmo sem a fase de execução ter
rodado.

**Acceptance Scenarios**:

1. **Given** um problema completo do dataset e um dos 3 cenários, **When** a fase de geração é
   executada, **Then** o sistema envia exatamente uma requisição *stateless* ao Ollama (sem
   histórico de chamadas anteriores), configurado com o modelo, a temperatura, a seed e o
   `num_ctx` fixados e registrados, e persiste a resposta crua, as entradas extraídas e a
   solução Python de referência.
2. **Given** uma resposta cuja estrutura de blocos (`<edge_cases_analysis>`, `<inputs>` com um
   ou mais `<input>`, `<reference_py>`) não pode ser interpretada, **When** ela é processada,
   **Then** o sistema registra essa tentativa como falha de interpretação (uma das 3 razões de
   descarte de tentativa), sem produzir uma suíte a partir dela.
3. **Given** um problema e um cenário cuja tentativa anterior falhou, **When** uma nova
   tentativa é disparada, **Then** o sistema usa a próxima seed prevista (seed base + número da
   tentativa) e envia uma chamada nova e independente, sem qualquer contexto da tentativa
   anterior.

---

### User Story 2 - Calcular a saída esperada por execução real (oráculo por execução) (Priority: P1)

Depois da geração, os autores disparam a fase de execução — em sandbox, sem rede — que roda a
solução Python de referência de cada tentativa pendente contra os testes públicos do problema
(para validar a solução) e, se ela passa, contra as entradas geradas (para calcular o
`expected_output` de cada uma). Entradas em que a solução falha isoladamente são descartadas
uma a uma; se a solução falha nos testes públicos, ou se falha — por erro de execução, por
timeout, ou por uma combinação das duas razões entre entradas diferentes — em 100% das entradas
geradas (nenhuma sobrevive ao descarte individual), a tentativa inteira é descartada e uma nova
rodada de geração é disparada para aquele problema × cenário, até o limite de 6 tentativas.

**Why this priority**: é o núcleo conceitual do módulo — sem essa etapa, o `expected_output`
seria uma previsão do modelo (sujeita a erro), não um valor obtido por execução real, o que
contraria a premissa central do desenho (oráculo por execução).

**Independent Test**: pode ser testado isoladamente com uma tentativa já persistida pela User
Story 1 (respostas fixas, sem chamar o Ollama de novo), verificando que a solução Python roda
sob os mesmos limites de tempo/memória do problema, que `expected_output` só é preenchido a
partir do resultado dessa execução, e que uma entrada cuja execução falha sozinha não derruba as
demais.

**Acceptance Scenarios**:

1. **Given** uma tentativa cuja solução Python passa em 100% dos testes públicos do problema,
   **When** a fase de execução roda essa solução sobre cada entrada gerada, **Then** o sistema
   preenche `expected_output` de cada entrada com a saída produzida pela execução real, dentro
   dos limites de tempo (múltiplo generoso do limite do problema, só contra laço infinito) e
   memória (derivados dos metadados do problema, nunca fixos no código).
2. **Given** uma tentativa cuja solução Python falha em pelo menos um teste público do problema,
   **When** a fase de execução avalia essa tentativa, **Then** a tentativa inteira é descartada
   (o `AC_ref.cpp` nunca é usado para validar, corrigir ou substituir essa solução), e o motivo
   fica registrado.
3. **Given** uma tentativa cuja solução Python passa nos testes públicos mas falha (erro de
   execução ou timeout) em uma entrada gerada específica, mantendo-se correta nas demais,
   **When** a fase de execução processa essa tentativa, **Then** o sistema descarta só essa
   entrada (registrando qual e por quê) e mantém as demais na suíte.
4. **Given** uma tentativa cuja solução Python falha — por erro de execução, por timeout, ou por
   uma combinação das duas razões entre entradas diferentes — em 100% das entradas geradas (ou
   seja, nenhuma entrada sobrevive ao descarte individual do Acceptance Scenario 3), **When** a
   fase de execução avalia essa tentativa, **Then** a tentativa inteira é descartada (nunca
   aceita como uma suíte de tamanho zero) e uma nova tentativa de geração é disparada para o
   mesmo problema × cenário, com a próxima seed.
5. **Given** um problema × cenário que acumula 6 tentativas descartadas (por qualquer
   combinação das 3 razões: resposta não interpretável, falha nos testes públicos, ou falha —
   erro de execução e/ou timeout, em qualquer combinação — em 100% das entradas geradas),
   **When** a 6ª tentativa também falha, **Then** o sistema descarta a suíte inteira daquele
   problema × cenário, registra o motivo de cada uma das 6 tentativas e continua contando esse
   problema no N = 200 usado pelas métricas, sem substituí-lo por outro.
6. **Given** uma falha de infraestrutura na chamada ao Ollama (endereço inacessível, timeout de
   conexão, erro do lado do servidor), **When** ela ocorre, **Then** o sistema NÃO consome uma
   das 6 tentativas — a mesma chamada é reexecutada com a mesma seed assim que o serviço volta a
   responder, distinguindo esse caso das 3 razões de descarte de conteúdo.

---

### User Story 3 - Retomar sem duplicar nem corromper o que já foi gerado ou executado (Priority: P2)

Ao interromper a geração ou a execução por qualquer motivo (queda de rede, falha do Ollama,
interrupção manual) e rodar o comando de novo, os autores recebem exatamente a continuação do
que faltava — os problemas × cenários já concluídos (com suíte aceita ou já descartada
definitivamente) não são reprocessados, e nenhum arquivo fica parcialmente escrito ou
inconsistente.

**Why this priority**: sem isso, uma interrupção no meio da execução completa (200 × 3
combinações, com chamadas de rede e execução em sandbox) obrigaria a recomeçar do zero, com
risco de gastar tentativas e tempo de forma redundante e de deixar dados corrompidos para trás.

**Independent Test**: pode ser testado isoladamente interrompendo a geração ou a execução no
meio de um lote pequeno (com o motor real) e comparando o resultado de uma retomada com o de uma
execução ininterrupta sobre a mesma entrada e as mesmas seeds.

**Acceptance Scenarios**:

1. **Given** uma execução da fase de geração interrompida no meio de um problema × cenário,
   **When** o comando é executado de novo, **Then** o sistema retoma exatamente daquele ponto,
   sem duplicar tentativas já persistidas nem perder o que já foi concluído para os demais
   problemas × cenários.
2. **Given** uma execução da fase de execução interrompida no meio da avaliação de uma
   tentativa, **When** o comando é executado de novo, **Then** o resultado final (suíte aceita
   ou descartada, com o mesmo conjunto de entradas e o mesmo `expected_output`) é idêntico ao de
   uma execução ininterrupta sobre a mesma entrada.

---

### User Story 4 - Relatório de geração para sustentar o texto do TCC (Priority: P3)

Ao final de uma execução completa, os autores precisam de um relatório versionado com os números
agregados da geração de suítes pelo SLM (taxa de descarte por problema × cenário, distribuição
do tamanho das suítes aceitas, seeds usadas e motivo de cada falha, hardware em que o Ollama
rodou), para citar no texto escrito sem precisar reabrir os arquivos-fonte das suítes.

**Why this priority**: é a mesma exigência de documentação viva já aplicada aos módulos
anteriores (Constitution, Princípio XI) — sem isso, os números do TCC não têm proveniência
auditável, e o tamanho variável da suíte (variável de confusão conhecida) não pode ser
analisado.

**Independent Test**: pode ser testado isoladamente conferindo que o relatório gerado ao final
de uma execução de teste contém os campos exigidos e que os totais (aceitas, descartadas,
tentativas por razão) somam corretamente.

**Acceptance Scenarios**:

1. **Given** uma execução completa das fases de geração e execução sobre um conjunto de
   problemas × cenários, **When** ela termina, **Then** o sistema grava um relatório com a taxa
   de descarte, a distribuição do tamanho das suítes aceitas, o funil de falha de tentativa por
   razão, todas as seeds usadas por problema × cenário e o hardware registrado para cada chamada
   ao Ollama.

---

### Edge Cases

- Resposta do modelo com blocos presentes mas em ordem trocada, duplicados, ou com um
  `<input>` vazio dentro de `<inputs>`: tratada como falha de interpretação (mesma razão de
  descarte de "resposta não interpretável"), sem tentativa de correção heurística.
- Uma entrada gerada que viola as restrições do enunciado (valor fora do intervalo declarado,
  mais elementos do que o limite): a instrução de respeitar as restrições é dada ao modelo no
  prompt; o módulo não valida cada entrada contra as restrições numéricas do enunciado depois de
  gerada (ver Assumptions) — uma entrada assim só é percebida indiretamente se causar erro de
  execução na solução Python, caso em que o tratamento já previsto (descarte da entrada isolada)
  se aplica.
- Solução Python que produz saída não determinística (ex.: usa `random` sem seed, itera sobre um
  `set` sem ordenação, imprime timestamp): não há verificação própria deste módulo para detectar
  não determinismo na solução Python — o risco fica registrado como limitação conhecida
  (Assumptions), já que a validação existente (testes públicos + entradas geradas, uma execução
  cada) não teria como diferenciar não determinismo de acerto.
- O mesmo problema × cenário atinge 6 tentativas descartadas por razões diferentes em cada
  tentativa (ex.: tentativa 1 não interpretável, tentativa 2 falha nos testes públicos,
  tentativa 3 timeout): todas as 6 razões, distintas ou repetidas, ficam registradas
  individualmente; o descarte final da suíte não perde o detalhe de qual tentativa falhou por
  qual motivo.
- Falha de infraestrutura (Ollama fora do ar) ocorre repetidamente, sem nunca voltar a responder:
  a mesma chamada é repetida até um teto de repetições consecutivas configurável no `.env`
  (FR-018a); ao atingi-lo, o comando para com erro de infraestrutura, sem gravar nada daquela
  tentativa e sem consumir o orçamento de 6 tentativas — rodar o comando de novo, com o serviço de
  volta, refaz a mesma chamada com a mesma seed. Não é uma condição de descarte de suíte.
  (Decidido em 2026-09-30, na revisão de consistência dos artefatos; antes o módulo não tinha
  teto e dependia de o operador interromper manualmente.)
- Solução Python referenciando bibliotecas fora da biblioteca padrão do Python, ou com uma
  sintaxe inválida: tratada pela sandbox como erro de execução, cobrindo os mesmos casos já
  previstos (falha em todos os testes públicos ou em todas as entradas, conforme onde o erro
  aparecer primeiro).
- `data/dataset` local ausente ou divergente do manifesto já versionado: a geração e a execução
  se recusam a rodar antes de processar qualquer problema, no mesmo padrão já exigido para o
  módulo de mutantes.

## Requirements *(mandatory)*

### Chamada ao modelo e prompt

- **FR-001**: O sistema MUST, para cada um dos 200 problemas do dataset e cada um dos 3
  cenários de contexto (caixa-preta, caixa-branca, híbrido), disparar chamadas ao SLM
  (Qwen2.5-Coder-7B, via Ollama) até obter uma suíte aceita ou esgotar 6 tentativas.
- **FR-002**: Cada chamada ao modelo MUST ser uma única requisição *stateless* — sem reter ou
  reaproveitar histórico de nenhuma chamada anterior, para o mesmo ou para outro problema ×
  cenário (Constitution, Princípio III).
- **FR-003**: O endereço do servidor Ollama MUST ser configurável via `.env` (máquina local ou
  servidor remoto), e cada resultado persistido MUST registrar o identificador exato do modelo
  que respondeu.
- **FR-003a**: O hardware em que o Ollama roda MUST ser informado por configuração manual do
  operador (uma etiqueta de texto no `.env`, junto do endereço do Ollama), nunca autodetectado da
  máquina que executa o pipeline — autodetecção seria incorreta sempre que o endereço apontar
  para um servidor remoto (FR-003).
- **FR-004**: O prompt MUST seguir a estrutura XML `<system_rules>`, `<context_data>`,
  `<few_shot_example>`, `<task>` (Few-Shot Prompting + Chain-of-Thought), em inglês; entre os 3
  cenários, MUST variar apenas o conteúdo de `<context_data>` — caixa-preta: só
  `enunciado.md`; caixa-branca: só `AC_ref.cpp`; híbrido: os dois.
- **FR-005**: O `<few_shot_example>` MUST usar o primeiro teste público do próprio problema
  sendo perguntado (escolha determinística, pela ordem em que os testes públicos aparecem em
  `testes.json`), igual nos 3 cenários daquele problema — nunca um exemplo de outro problema.
- **FR-006**: O prompt MUST exigir do modelo um bloco de análise prévia de casos-limite
  (`<edge_cases_analysis>`) antes de gerar as entradas, para reduzir alucinação e
  superficialidade.
- **FR-007**: O prompt MUST instruir o modelo a respeitar as restrições declaradas no enunciado
  ao gerar cada entrada (valores até o máximo das restrições) e a limitar a quantidade de
  elementos por entrada a um tamanho que o modelo consiga escrever por completo, sem truncar.
- **FR-008**: A janela de contexto (`num_ctx`) MUST ser grande o suficiente para o maior prompt
  entre os 200 problemas, com folga; o valor exato MUST ser medido e fixado no planejamento
  técnico da feature (fora do escopo desta especificação).

### Formato de resposta e interpretação

- **FR-009**: A resposta do modelo MUST ser texto plano com 3 blocos marcados —
  `<edge_cases_analysis>`, `<inputs>` (contendo um ou mais `<input>`) e `<reference_py>` — nunca
  JSON, para evitar erros de escape de código dentro da solução Python.
- **FR-010**: O sistema MUST interpretar deterministicamente os 3 blocos da resposta crua; se
  qualquer bloco obrigatório estiver ausente, vazio ou malformado, a tentativa correspondente
  MUST ser registrada como falha de interpretação (uma das 3 razões de descarte de tentativa,
  ver FR-018).
- **FR-011**: A suíte persistida (depois de interpretada e, na fase de execução, com
  `expected_output` preenchido) MUST seguir um schema JSON formal e versionado (Constitution,
  Princípio IV), independentemente de a resposta crua do modelo não ser JSON.
- **FR-012**: O sistema MUST NOT impor limite fixo de quantidade de casos de teste por suíte; o
  tamanho de cada suíte aceita MUST ser registrado para a análise (variável de confusão
  conhecida).

### Oráculo por execução (fase de execução, sandbox sem rede)

- **FR-013**: O pipeline MUST separar geração e execução em duas fases distintas: (a) geração,
  com rede — envia a requisição ao Ollama e persiste a resposta crua, as entradas interpretadas,
  a solução Python e a seed, sem executar nenhum código; (b) execução, em sandbox sem rede —
  roda a solução Python contra os testes públicos do problema e as entradas geradas, e preenche
  `expected_output`.
- **FR-014**: A resposta crua do modelo MUST ser sempre persistida, de forma que a fase de
  execução (ou uma repetição dela) nunca precise chamar o modelo de novo para reprocessar uma
  tentativa já recebida.
- **FR-015**: A solução Python de referência de cada tentativa MUST rodar em sandbox própria —
  sem rede, sem privilégios além do necessário, com limite de memória derivado dos metadados do
  problema (nunca fixo no código) — reaproveitando o isolamento do motor de execução já
  construído no módulo `sandbox`.
- **FR-016**: O tempo de execução da solução Python MUST ser limitado a um múltiplo generoso do
  limite de tempo do problema (valor exato do múltiplo definido no planejamento técnico), servindo
  só como proteção contra laço infinito, nunca como restrição de desempenho.
- **FR-017**: A solução Python de referência MUST ser validada exclusivamente contra os testes
  públicos do próprio problema; `AC_ref.cpp` MUST NOT ser usado, em nenhuma circunstância, para
  aprovar, descartar ou corrigir uma tentativa ou uma suíte.
- **FR-018**: Uma tentativa (problema × cenário × número da tentativa) MUST ser marcada como
  falha, consumindo uma unidade do orçamento de 6, quando: (a) a resposta crua não pode ser
  interpretada (FR-010); (b) a solução Python falha em pelo menos um teste público do problema;
  ou (c) a solução Python falha — por erro de execução, por timeout (FR-016), ou por qualquer
  combinação das duas razões entre entradas diferentes — em 100% das entradas geradas (ou seja,
  nenhuma entrada sobrevive ao descarte individual de FR-019; uma tentativa nunca é aceita com
  suíte de tamanho zero).
- **FR-018a**: Uma falha de infraestrutura na chamada ao Ollama (serviço inacessível, timeout de
  conexão, erro do lado do servidor) MUST NOT consumir uma unidade do orçamento de 6 tentativas —
  a mesma chamada, com a mesma seed, MUST ser reexecutada quando o serviço voltar a responder.
  As repetições consecutivas de uma mesma chamada MUST ter um teto, e o tempo máximo de espera de
  uma resposta MUST ser um *timeout* de leitura; ambos são configuráveis pelo operador no `.env`
  (com valor padrão). Atingir o teto MUST encerrar o comando com erro de infraestrutura, sem
  gravar a tentativa e sem consumir o orçamento; a próxima execução refaz a mesma chamada.
- **FR-019**: Quando a solução Python falha (erro de execução ou timeout) em algumas entradas
  geradas, mas não em todas, MUST ser descartada só a entrada que falhou — a suíte mantém as
  demais entradas, e o descarte MUST registrar qual entrada e por quê.

### Retentativas e descarte

- **FR-020**: Cada tentativa de um mesmo problema × cenário MUST usar uma seed diferente e
  previsível, derivada da seed base somada ao número da tentativa (1 a 6).
- **FR-021**: As novas tentativas MUST acontecer em rodadas: depois de cada execução, somente os
  problemas × cenários cuja tentativa foi marcada como falha (FR-018) MUST voltar para uma nova
  chamada de geração, com a próxima seed; combinações já aceitas MUST NOT ser regeneradas. A
  falha de interpretação (FR-018, razão (a)) é a exceção: como não há nada a executar, a fase de
  geração já faz a tentativa seguinte, com a próxima seed, na mesma execução, sem esperar uma
  rodada de execução (decidido no plano, 2026-09-30, `research.md` R8).
- **FR-022**: Depois de 6 tentativas marcadas como falha (FR-018) para o mesmo problema ×
  cenário, a suíte MUST ser descartada por completo, com o motivo registrado.
- **FR-023**: Uma suíte descartada (FR-022) MUST continuar contando no N = 200 problemas usado
  pelas demais métricas do experimento; a taxa de descarte (por problema × cenário) MUST ser
  reportada separadamente, nunca reduzindo esse N em silêncio.
- **FR-024**: O resultado de cada problema × cenário MUST registrar todas as seeds usadas
  (inclusive das tentativas que falharam), o motivo de cada falha e, quando houver sucesso, qual
  tentativa foi aceita.

### Reprodutibilidade e proveniência

- **FR-025**: Temperatura e seed base MUST ser fixadas e registradas; o hardware em que o Ollama
  rodou (etiqueta de configuração manual, FR-003a) MUST ser registrado junto com os resultados de
  cada chamada.
- **FR-026**: O pipeline (ambas as fases) MUST poder ser interrompido e retomado a qualquer
  momento sem duplicar nem corromper dados já persistidos (Constitution, Princípio VII).
- **FR-027**: O sistema MUST produzir um relatório versionável, agregando: taxa de descarte por
  problema × cenário, distribuição do tamanho das suítes aceitas, funil de falha de tentativa
  por razão (não interpretável, falha em teste público, falha — erro de execução e/ou timeout —
  em 100% das entradas), seeds usadas por combinação e hardware registrado por chamada.
- **FR-028**: Ao final da execução completa que sustenta os números publicados do experimento, o
  sistema MUST poder compactar as suítes SLM de todos os problemas × cenários em um pacote
  único, acompanhado de um manifesto de integridade SHA-256, no mesmo formato já usado para o
  dataset e para os mutantes (ver Divergências, D3).

### Fora do escopo desta especificação

- **FR-029**: Este módulo MUST NOT implementar os clientes do GPT-5.4-mini ou do Gemini 3.5
  Flash, nem a execução das suítes geradas contra AC/WA/mutantes, nem o cálculo de TDF, MS, TFP
  ou IIC — essas etapas são escopo de módulos futuros que apenas consomem o resultado deste.

### Key Entities *(include if feature involves data)*

- **Tentativa**: uma chamada *stateless* ao SLM para um problema × cenário específico,
  identificada pelo número da tentativa (1 a 6) e pela seed derivada; guarda a resposta crua, o
  identificador do modelo, o hardware do Ollama e o veredito (aceita, ou falha com uma das
  razões de FR-018).
- **Suíte SLM**: o conjunto de casos de teste aceitos para um problema × cenário, junto com o
  tamanho da suíte, a tentativa que a originou e, quando aplicável, a lista de entradas
  descartadas individualmente (FR-019) com o motivo de cada uma. Termo próprio deste módulo —
  não deve ser confundido com o campo `generated_tests` já existente em `testes.json` do
  dataset, que vem da fonte original dos problemas.
- **Caso de teste gerado**: um par entrada / `expected_output` dentro de uma suíte SLM; a
  entrada vem da resposta interpretada do modelo, e `expected_output` só existe depois da fase
  de execução.
- **Solução Python de referência**: o código Python que acompanha uma tentativa, cuja única
  função é calcular `expected_output` a partir das entradas daquela mesma tentativa; nunca é
  objeto de avaliação nem persiste além do necessário para auditoria da tentativa.
- **Registro de descarte de suíte**: quando uma suíte é descartada após 6 tentativas, o registro
  de todas as seeds usadas e o motivo de cada uma das 6 falhas.
- **Relatório de geração de suítes SLM**: dado quantitativo agregado (taxa de descarte,
  distribuição de tamanho de suíte, funil de falha por razão, seeds e hardware), para citação no
  texto do TCC sem reabrir os arquivos-fonte das suítes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Para cada uma das 600 combinações (200 problemas × 3 cenários), a execução
  completa termina em exatamente um de dois estados — suíte aceita (com tamanho registrado) ou
  suíte descartada (com as 6 razões de falha registradas) — nunca um estado intermediário ou
  ambíguo.
- **SC-002**: 100% dos casos de teste mantidos em suítes aceitas têm `expected_output`
  calculado por execução real da solução Python sobre a entrada, nunca por previsão do modelo.
- **SC-003**: A taxa de descarte de suítes (combinações que esgotam as 6 tentativas) é medida e
  reportada separadamente, sem reduzir silenciosamente o N = 200 usado pelas demais métricas do
  experimento.
- **SC-004**: Interromper a geração ou a execução em qualquer ponto e retomar produz o mesmo
  resultado final (mesmas suítes aceitas, mesmo conteúdo, mesmas entradas descartadas) que uma
  execução ininterrupta sobre a mesma entrada e as mesmas seeds, sem arquivo duplicado ou
  corrompido.
- **SC-005**: 100% das chamadas ao modelo são *stateless* — nenhuma chamada reaproveita
  histórico de qualquer chamada anterior, para o mesmo ou para outro problema × cenário.
- **SC-006**: Toda solução Python roda sob isolamento sem rede e sem privilégios elevados em
  100% das execuções, com limites de tempo e memória derivados dos metadados do problema (nunca
  hardcoded).
- **SC-007**: Uma falha de infraestrutura na chamada ao Ollama nunca é contabilizada como uma
  das 6 tentativas em nenhuma execução observada — só as 3 razões de conteúdo (FR-018) consomem
  o orçamento, e nenhuma tentativa é aceita com uma suíte de tamanho zero.
- **SC-008**: Ao concluir a feature, `docker compose run --rm app python
  scripts/check_docs_sync.py --closing` (sobre o pacote novo deste módulo, quando implementado)
  termina com código 0, nas mesmas condições já exigidas para os módulos anteriores.

## Assumptions

- **Usuários**: os dois autores do TCC executam o módulo localmente ou contra um servidor Ollama
  remoto configurado no `.env`; não há usuários finais externos.
- **Dependência do dataset**: este módulo consome `data/dataset` (ou `data/dataset.zip`
  descompactado), já validado pelo módulo `001-dataset-extraction`; usa `enunciado.md`,
  `AC_ref.cpp`, `testes.json` (para as restrições do enunciado, os limites de tempo/memória de
  `metadata.json`, e o primeiro teste público usado no few-shot) e nada além disso — nenhuma
  mudança de schema é necessária nesses módulos.
- **Nome do campo da saída esperada**: o `expected_output` desta especificação é gravado no campo
  `output` de cada caso da suíte, que segue o contrato de caso de teste já existente no projeto
  (`TestCase`, `input`/`output`, o mesmo de `testes.json`); o futuro módulo de avaliação e as suítes
  dos dois modelos comerciais adotam a mesma forma (decisão de 2026-09-30, `plan.md`, S2).
- **Motor de execução**: a fase de execução reaproveita, sem alteração, o isolamento (sandbox
  sem rede, limites via metadados do problema) já construído no módulo `sandbox`; a validação
  contra os testes públicos e as entradas geradas usa o mesmo mecanismo de comparação de saída
  já estabelecido nesse motor.
- **Sem validação própria de restrições nas entradas geradas**: o módulo não implementa uma
  verificação pós-hoc de que cada entrada gerada respeita os limites numéricos do enunciado —
  essa exigência é só uma instrução de prompt (FR-007); uma violação só é percebida
  indiretamente, se causar erro de execução na solução Python (tratado pelo mesmo mecanismo de
  descarte de entrada isolada, FR-019). Risco aceito, documentado como limitação conhecida.
- **Sem verificação de determinismo da solução Python**: o módulo não detecta se a solução
  Python gerada pelo modelo é não determinística (ex.: depende de ordem de iteração de `set`,
  usa `random` sem seed); uma execução por entrada é o único crivo, o mesmo já usado para os
  testes públicos. Limitação conhecida, a registrar na análise de resultados.
- **Regra de tamanho de suíte a alinhar entre módulos**: não há limite fixo de casos por suíte
  neste módulo; a regra final (se algum teto ou normalização for necessário para comparar
  cenários e modelos de forma justa) é uma decisão a alinhar com os módulos de orquestração do
  GPT-5.4-mini e do Gemini 3.5 Flash, fora do escopo desta especificação — pendência que MUST
  ser registrada em `docs/metodologia-referencia.md` (seção 6, Pendências Consolidadas) até ser
  fechada.
- **Valores exatos de `num_ctx` e do múltiplo de timeout da solução Python**: dependem de
  medição sobre os 200 prompts reais e MUST ser fixados no planejamento técnico (`plan.md`), não
  nesta especificação. **Fixados em 2026-09-30** (`plan.md`, `research.md` R3 e R7): `num_ctx =
  8192` e `num_predict = 4096`, a partir do maior prompt medido (7.870 caracteres, híbrido de
  `61_B`; remedido com o prompt real em 2026-09-30: 8.118), com guarda de truncamento em tempo de execução; tempo da solução Python = limite do
  problema × 10 e memória = limite do problema × 4 (ambos a confirmar no piloto). Temperatura e
  demais parâmetros de amostragem (FR-025) decididos em 2026-09-30 (`research.md` R4): `temperature
  0.7`, `top_p 0.8`, `top_k 20`, `repeat_penalty 1.05`, seed base 42. O template do prompt foi
  ajustado no mesmo dia para cumprir FR-007 (`research.md` R5a).
- **Versionamento das suítes SLM**: como decidido nesta sessão (ver Divergências, D3), a
  identidade de uma suíte depende de uma chamada real e não estritamente reprodutível a uma API
  de IA — o mesmo caso já coberto pela exceção do Princípio II (Constitution, emenda 1.6.0). Ao
  final da execução completa do experimento, as suítes MAY ser compactadas e commitadas (pacote
  + manifesto SHA-256), no mesmo formato do dataset e dos mutantes; suítes geradas durante o
  desenvolvimento iterativo do módulo continuam nunca sendo versionadas.
- **Dependência de módulos futuros**: a execução das suítes SLM contra AC, WA e mutantes, e o
  cálculo de TDF/MS/TFP/IIC, consomem o resultado deste módulo, mas nada disso é entregue nesta
  feature.

## Divergências e Decisões sobre a Metodologia

<!--
  Registro exigido pela Constitution (Princípio I): divergências ou preenchimentos de lacunas
  em relação a docs/metodologia-referencia.md, para atualizar o texto final do TCC.
-->

A seção 3 da metodologia (`docs/metodologia-referencia.md`) estava marcada como "PENDENTE —
parte menos polida, especialmente a configuração do SLM" e continha um "Ponto em aberto" sobre o
detalhamento operacional do oráculo por execução. As decisões abaixo, tomadas em rodada de
pesquisa e discussão técnica prévia a este `/speckit.specify` (documento compartilhado com a
dupla), junto com as 3 perguntas de esclarecimento respondidas nesta sessão (2026-09-29,
registradas em Clarifications), fecham essa pendência.

- **D1 — Formato de resposta: texto com 3 blocos marcados, não JSON (decidido, diverge do texto
  atual da metodologia)**: a metodologia (seção 3) descreve a saída do Qwen2.5-Coder como
  `format: json`, igual aos dois modelos comerciais. Na prática, pedir ao SLM uma solução Python
  inteira dentro de um campo JSON expõe o pipeline a erros de escape de aspas, quebras de linha
  e barras invertidas dentro do código gerado — risco que os dois modelos de fronteira mitigam
  melhor, mas que um modelo de 7B tende a errar com mais frequência. **Decisão**: o Qwen
  responde em texto plano com 3 blocos marcados por tags (`<edge_cases_analysis>`, `<inputs>` com
  vários `<input>`, `<reference_py>`), interpretados deterministicamente pelo pipeline; a suíte
  persistida depois da interpretação continua sendo JSON com schema formal e versionado
  (Constitution, Princípio IV) — só a resposta crua do modelo deixa de ser JSON. Reflete-se em
  FR-009 a FR-011; **este parágrafo da metodologia (seção 3) MUST ser atualizado no mesmo ciclo
  de trabalho** (Constitution, Princípio XI).
- **D2 — Exemplo do few-shot: o primeiro teste público do próprio problema, não um exemplo fixo
  (decidido)**: a metodologia (seção 3) só diz "um caso de teste público real do dataset é
  incluído como exemplo estrutural", sem especificar se é fixo entre chamadas ou varia por
  problema. Avaliou-se um exemplo único e fixo (mesmo teste ilustrativo em todas as 600
  chamadas, risco: pode induzir o modelo pequeno a um formato de entrada que não corresponde ao
  problema real sendo perguntado, especialmente no cenário caixa-branca, onde o exemplo seria a
  única pista de formato de entrada além do próprio código). **Decisão**: usar sempre o primeiro
  teste público do próprio problema (escolha determinística pela ordem em `testes.json`), igual
  nos 3 cenários daquele problema — não há vazamento de informação nova, já que testes públicos
  já são os exemplos do enunciado original (Codeforces); a mesma regra MUST ser adotada pelos
  módulos de orquestração do GPT-5.4-mini e do Gemini 3.5 Flash, para manter o desenho
  experimental comparável entre os 3 modelos. Reflete-se em FR-005.
- **D3 — Suítes SLM seguem a mesma exceção de versionamento dos mutantes (decidido, não requer
  nova emenda à Constitution)**: a emenda 1.6.0 do Princípio II já generalizou a exceção de
  versionamento (antes exclusiva do dataset) para qualquer artefato cuja identidade dependa de
  execução real de código de terceiros no motor **ou de chamadas a APIs de IA não estritamente
  reprodutíveis bit a bit** — este último caso é exatamente o das suítes SLM (a mesma seed pode
  produzir uma resposta diferente do modelo entre execuções, além da instabilidade de margem já
  conhecida do motor de execução usado na fase de execução). **Decisão**: ao final da execução
  completa do experimento, o pacote de suítes SLM (respostas cruas, entradas, soluções Python,
  `expected_output`) MAY ser compactado e commitado com manifesto SHA-256 próprio, no mesmo
  formato do dataset e dos mutantes, sem necessidade de nova emenda — a emenda 1.6.0 já cobre
  este caso. Reflete-se em FR-028 e na Assumption de versionamento.
