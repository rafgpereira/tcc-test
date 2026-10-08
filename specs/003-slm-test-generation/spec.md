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

### Session 2026-10-04 (revisão depois do piloto 1, `research.md` R13)

- Q: Uma cerca Markdown (```` ```python ````) em volta de todo o `<reference_py>` faz a solução
  virar `SyntaxError` e reprovar no teste público (as 6 RE do híbrido no piloto 1). Remover? → A:
  Só a cerca que envolve o código inteiro (primeira linha ```` ```python ````, ```` ```py ```` ou
  ```` ``` ````; última ```` ``` ````) é removida, e a remoção é registrada por tentativa e somada
  por cenário no relatório; qualquer outra cerca fica como veio (FR-010).
- Q: Um `<input>` vazio invalida a tentativa inteira? → A: Não — é descartado sozinho e contado,
  como uma entrada que quebra a solução (FR-019); só "todas vazias" é falha de interpretação. A
  frase "including empty input if allowed" saiu do prompt.
- Q: O Ollama responder HTTP 500 `token repeat limit reached` é falha de infraestrutura? → A: Não —
  é falha do próprio modelo (com a mesma seed ele repetiria o laço): consome a tentativa com a
  razão `repetition`, registrada, e a próxima seed é chamada (FR-018(d)).

### Session 2026-10-05 (piloto 2, `research.md` R14)

- Q: No piloto 2 as 7 suítes descartadas caíram todas pela solução Python errando um teste público.
  Usar o `AC_ref` para calcular as saídas? → A: Não. O TCC avalia a IA como apoio à escrita de
  testes unitários, e na vida real não existe uma implementação de referência correta para isso. O
  `AC_ref` continua sem papel na execução (FR-017).
- Q: Reaproveitar as entradas de uma tentativa cuja solução errou? → A: Não. Cada tentativa continua
  independente e pede entradas e solução de novo; as entradas de uma tentativa reprovada saem com ela
  (FR-018).
- Q: Mudar o orçamento de 6 tentativas? → A: Não; continua 6 (mediana medida de 29 s por chamada).
  **Superado em 2026-10-05, depois do piloto 4** (sessão abaixo): 8 tentativas estritas, suíte de
  reserva e teto de 12.
- Q: O que registrar de um teste público reprovado? → A: O início do `stdout` (até 2.048 bytes), o
  final do `stderr`, o tempo de CPU e o pico de memória, no registro de execução da tentativa.
- Q: Como revisar o prompt para a solução Python errar menos? → A: Planejar o algoritmo e simulá-lo
  à mão no exemplo antes de escrever o código; avisar que a solução roda primeiro no exemplo;
  pedir de 10 a 20 entradas distintas, todas escritas por extenso; tirar o pedido de entradas
  inválidas e a menção a entrada vazia; dicas de leitura e de recursão em Python. O texto continua
  igual nos 3 cenários (FR-004, FR-006, FR-007). Abre o piloto 3.
- Q: O piloto 3 ainda deixaria ≈ 40% das combinações sem suíte. Trocar de modelo? → A: Primeiro um
  piloto 4 com `qwen2.5-coder:14b`, nos mesmos 5 problemas, escolhido pela variável opcional
  `OLLAMA_MODEL` (o modelo do desenho continua o 7B até a decisão). Depois, Milena e Rafael decidem
  entre manter o 7B, trocar para o 14B ou fazer o SLM prever as saídas (`research.md` R15). O
  Python passa a rodar sem `-S`, que deixava `exit()` indefinido.

### Session 2026-10-05 (piloto 4, `research.md` R16)

- Q: Nenhuma combinação pode ficar sem suíte. O que fazer quando todas as tentativas falham? → A:
  O orçamento estrito passa de 6 para **8** tentativas (seeds 43 a 50). Se as 8 falharem, a
  melhor delas que reprovou um teste público **só por WA** e manteve ao menos uma entrada gerada
  vira a suíte, com status próprio `accepted_fallback` (FR-022a): a que passou mais testes
  públicos, depois a que manteve mais entradas, depois a de menor número. Para isso, uma tentativa
  que reprova um teste público por WA roda as entradas geradas assim mesmo (FR-018(b)). Se nenhuma
  das 8 puder ser reserva (respostas não interpretadas, RE, TLE, MLE ou nenhuma entrada mantida),
  as tentativas 9 a 12 (seeds 51 a 54) aceitam a primeira que passar em tudo ou puder ser reserva.
  Só depois de 12 sem nenhuma das duas a suíte é descartada (FR-022).
- Q: Marcar as suítes de reserva igual às aceitas? → A: Não. Elas têm saídas esperadas vindas de
  uma solução que sabidamente erra em algum caso, então o status é próprio, a tentativa usada fica
  em `accepted_attempt` e cada tentativa diz se podia ser reserva (`fallback_eligible`); a análise
  pode separá-las ou excluí-las (FR-023).

### Session 2026-10-06 (nenhuma combinação sem suíte)

*(A ordem de tentativas desta sessão — 8 estritas, extras até a 20ª e baixa confiança — foi
substituída no mesmo dia pela política de 5 fases, sessão "política de 5 fases" abaixo; o
tratamento manual e o fechamento continuam valendo.)*

- Q: Em que momento a suíte de baixa confiança pode ser escolhida, dado que as tentativas extras
  vêm antes dela e o teto é de 20 tentativas? → A: Só depois da 20ª. Ordem completa (FR-022 a
  FR-022c): (1) tentativas 1 a 8, a primeira que passa em todos os testes públicos vira a suíte
  (`accepted`); (2) se nenhuma passou, a reserva entre as que falharam só por WA
  (`accepted_fallback`, critérios de desempate de FR-022a), sem chamada nova; (3) se nenhuma das 8
  pode ser reserva, tentativas 9 a 20, parando na primeira que for `accepted` ou puder ser
  reserva; (4) depois da 20ª sem nenhuma das duas, `accepted_low_confidence` = a primeira das 20
  cuja solução rodou em pelo menos uma entrada gerada (mesmo tendo falhado nos testes públicos por
  RE, TLE ou MLE); (5) se nem isso existir, predição: o mesmo modelo recebe um segundo template
  (`src/prompt_templates/slm_predict_prompt.txt`) e escreve entradas **e** saídas esperadas, sem
  solução Python e sem validação pelos testes públicos; nova tentativa só por resposta não
  interpretável, até 3 (tentativas 21 a 23, seeds seguintes às já usadas); a suíte recebe
  `accepted_predicted`; (6) se nem as 3 forem interpretáveis, o comando para e reporta a
  combinação para tratamento manual. O status `discarded` deixa de existir no fluxo normal, e
  relatório e métricas separam as suítes por status.
- Q: Quando uma combinação esgota as 3 tentativas por predição sem resposta interpretável, o
  comando para na hora ou continua com as outras? → A: Continua. A combinação fica marcada como
  aguardando tratamento manual, o comando segue com as demais e, no fim, sai com um código de saída
  próprio listando todas as marcadas; o `report` as conta à parte e o `package` recusa enquanto
  existir alguma (FR-022).
- Q: Que tratamento manual tira uma combinação desse estado e com qual status ela fecha? → A: Um
  comando explícito dos autores a fecha com o status `discarded_manual` e um motivo obrigatório
  (registrados no resultado da combinação, com data); o status é contado à parte no relatório e a
  combinação continua no N = 200 (FR-022d).

### Session 2026-10-06 (piloto 5, `research.md` R20)

- Q: Qual modelo o experimento usa? → A: `qwen2.5-coder:14b` (FR-001), escolhido depois dos
  pilotos 4 e 5; diverge do Qwen2.5-Coder-7B do texto do TCC.
- Q: Como as métricas tratam as suítes que não vêm de uma solução aprovada (FR-023)? → A: as
  `accepted_fallback` entram como as `accepted`; `accepted_low_confidence` e `accepted_predicted`
  ficam separadas por status.
- Q: A temperatura e a seed base podem variar? → A: só num piloto (o 6) que compara
  configurações, pelo `.env` (`OLLAMA_TEMPERATURE`, `OLLAMA_SEED_BASE`); os valores entram no
  `run.json` e uma execução nunca mistura dois (FR-020, FR-025). A temperatura do experimento sai
  desse piloto. *(Substituído no mesmo dia: as duas variáveis saem e a temperatura e a seed vêm da
  tabela de FR-020; sessão "política de 5 fases" abaixo.)*

### Session 2026-10-06 (política de 5 fases, `research.md` R21)

Política de tentativas definida pela Milena para o piloto 6, que **substitui** a de R16/R18
(8 estritas, extras até a 20ª, `accepted_low_confidence`) e o piloto de temperaturas de R20
(FR-020, FR-022 a FR-022d): fase 1, tentativas 1–6, temperatura 0,7 e seeds 42 a 47 (seed
41 + n); fase 2, tentativas 7–12, seed 48 e temperatura decrescente 0,7; 0,6; 0,5; 0,4; 0,3; 0,2
— as duas param na primeira `accepted`; fase 3, se nenhuma das 12 passou, reserva
`accepted_fallback` entre as 12, sem chamada nova; fase 4, se nenhuma das 12 pode ser reserva,
predição nas tentativas 13–15, seeds 49 a 51, temperatura 0,7, nova tentativa só por resposta não
interpretável (`accepted_predicted`); fase 5, sem resposta interpretável, a combinação aguarda
tratamento manual (decisão B já tomada). Não existem mais tentativas extras nem
`accepted_low_confidence`. A tabela tentativa → fase, seed, temperatura fica numa configuração
única no código, gravada no `run.json`, e cada tentativa registra seed, temperatura e fase.

- Q: A política de 5 fases vale só para o piloto 6 ou também para a execução completa? → A: É a
  política do experimento: o piloto 6 a valida nos mesmos 5 problemas e, se der certo, ela roda
  na execução completa sem mudança.
- Q: As variáveis `OLLAMA_TEMPERATURE` e `OLLAMA_SEED_BASE` do `.env` continuam? → A: Não. São
  removidas (a tabela no código é a única fonte de seed e temperatura), e o piloto de temperaturas
  de R20 (uma execução por temperatura, com repetição de seeds) é substituído por um piloto 6
  único com esta política. `OLLAMA_MODEL` continua.
- Q: Uma solução que reprova um teste público por RE, TLE ou MLE ainda roda as entradas
  geradas? → A: Não. As entradas rodam só quando a solução passa em todos os testes públicos ou
  quando o primeiro erro é WA (a reserva só usa WA), como até 2026-10-05 (FR-018).

### Session 2026-10-07 (duas GPUs e continuação da execução, `research.md` R23 e R24)

Decisões da Milena: a configuração do piloto 6 fica congelada e a execução completa é a
continuação da mesma execução com `--resume` até as 600 combinações; as 585 restantes são geradas
em duas GPUs T4 idênticas, com dois `generate --resume` em paralelo sobre metades disjuntas dos
problemas, cada um com seu `OLLAMA_BASE_URL` (passado com `docker compose run -e`) e o mesmo
`OLLAMA_HARDWARE_LABEL`; um único `execute` depois. Para isso, a trava única de `data/suites/slm/`
vira uma trava compartilhada para `generate`/`execute` mais uma trava exclusiva por combinação;
`package` e `close` continuam exclusivos (FR-026a). Não há teste de determinismo entre as GPUs.

- Q: Quando um `generate` ou o `execute` chega a uma combinação que outro processo está tratando,
  ele pula ou espera? → A: Pula: segue com as outras combinações e informa no resumo final quantas
  pulou por estarem em uso; a pulada fica com o processo que a pegou primeiro (FR-026a).

### Session 2026-10-07 (resposta do Ollama em *streaming*, `research.md` R25)

Pedido da Milena: pelo túnel do cloudflared, toda chamada que passa de ~100 s recebe HTTP 524 (o
proxy do Cloudflare encerra o pedido sem nenhum byte nesse tempo), e o `generate` repete a mesma
chamada até esgotar as 30 repetições. A resposta passa a vir em *streaming* (`"stream": true`); o
texto, as opções e a seed não mudam, e o resultado gravado é idêntico ao da chamada sem
*streaming*, então a execução em andamento continua com `--resume` (FR-002a).

- Q: Uma conexão que cai no meio da resposta é o quê? → A: Falha de infraestrutura: a mesma
  chamada, com a mesma seed, é refeita, e nada da resposta parcial é gravado (FR-018a).
- Q: O que passa a medir `OLLAMA_HTTP_TIMEOUT_S`? → A: O maior tempo sem receber nenhum byte da
  resposta (o silêncio), não a resposta inteira; uma geração longa que continua mandando pedaços
  não é cortada, e a duração dela continua limitada por `num_predict` (decidido pelo agente e
  registrado em R25, item 3, por ser a única leitura compatível com o *streaming*).


### Session 2026-10-07 (divisão automática do trabalho entre as GPUs, `research.md` R26)

Pedido da Milena: com metades fixas, uma GPU terminou a sua e ficou parada enquanto a outra ainda
tinha fila. O laço passa a dar **todos** os problemas aos dois `generate`; a trava por combinação
(FR-026a) já faz quem chega a uma combinação em uso pulá-la e seguir para a seguinte, então os dois
dividem o trabalho sozinhos, sem código novo no módulo.

- Q: Uma combinação pulada por estar em uso fica sem tratamento nessa rodada? → A: Não: quem a
  tem a trata; o `skipped` passa a ser o esperado com duas máquinas (cada linha é uma combinação
  feita pelo outro processo), e a próxima rodada só retoma o que ainda faltar (FR-026a).
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
2. **Given** uma resposta cuja estrutura de blocos (`<edge_cases_analysis>`, `<reference_py>`,
   `<inputs>` com um ou mais `<input>`) não pode ser interpretada, **When** ela é processada,
   **Then** o sistema registra essa tentativa como falha de interpretação (uma das razões de
   descarte de tentativa de FR-018), sem produzir uma suíte a partir dela.
3. **Given** um problema e um cenário cuja tentativa anterior falhou, **When** uma nova
   tentativa é disparada, **Then** o sistema usa a próxima seed prevista (seed base + número da
   tentativa) e envia uma chamada nova e independente, sem qualquer contexto da tentativa
   anterior.

---

### User Story 2 - Calcular a saída esperada por execução real (oráculo por execução) (Priority: P1)

Depois da geração, os autores disparam a fase de execução — em sandbox, sem rede — que roda a
solução Python de referência de cada tentativa pendente contra os testes públicos do problema
(para validar a solução) e contra as entradas geradas (para calcular o `expected_output` de cada
uma; se a solução reprova um teste público, as entradas só rodam quando o primeiro erro é WA, para
a tentativa poder servir de reserva). Entradas em que a solução falha isoladamente são
descartadas uma a uma; se a solução falha nos testes públicos, ou se falha — por erro de
execução, por timeout, ou por uma combinação das duas razões entre entradas diferentes — em 100%
das entradas geradas (nenhuma sobrevive ao descarte individual), a tentativa falha e uma nova
rodada de geração é disparada para aquele problema × cenário, nas fases 1 e 2 de FR-022 (12
tentativas); depois delas valem, nesta ordem, a reserva (FR-022a) e a predição (FR-022c), a única
exceção ao oráculo por execução.

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
5. **Given** um problema × cenário cujas 12 tentativas das fases 1 e 2 falharam (por qualquer
   combinação das razões de FR-018), **When** alguma delas reprovou um teste público só por WA e
   manteve entradas, **Then** a melhor dessas vira a suíte com status `accepted_fallback`
   (FR-022a), sem chamada nova; **When** nenhuma pode ser reserva, **Then** seguem até 3
   tentativas por predição (`accepted_predicted`, FR-022c); **When** nenhuma das 3 é interpretável,
   **Then** a combinação fica aguardando tratamento manual, as demais seguem e o comando sai no fim
   com código próprio listando-a. Em todos os casos o motivo de cada tentativa fica registrado e o
   problema continua contando no N = 200.
6. **Given** uma falha de infraestrutura na chamada ao Ollama (endereço inacessível, timeout de
   conexão, erro do lado do servidor), **When** ela ocorre, **Then** o sistema NÃO consome uma
   das tentativas — a mesma chamada é reexecutada com a mesma seed assim que o serviço volta a
   responder, distinguindo esse caso das razões de descarte de FR-018.

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

- Resposta do modelo com blocos presentes mas em ordem trocada ou duplicados: tratada como
  falha de interpretação (mesma razão de descarte de "resposta não interpretável"), sem tentativa
  de correção heurística. Um `<input>` vazio dentro de `<inputs>` é descartado sozinho e contado;
  só se **todos** forem vazios a resposta é não interpretável (decidido em 2026-10-04; antes um
  único `<input>` vazio invalidava a tentativa).
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
- O mesmo problema × cenário atinge as 12 tentativas das fases 1 e 2 com falha por razões
  diferentes em cada tentativa (ex.: tentativa 1 não interpretável, tentativa 2 falha nos testes
  públicos por RE, tentativa 3 timeout), sem nenhuma que possa ser reserva: todas as 12 razões,
  distintas ou repetidas, ficam registradas individualmente, e a combinação segue para a predição
  (FR-022c); a suíte final não perde o detalhe de qual tentativa falhou por qual motivo.
- As 3 tentativas por predição (FR-022c) dão resposta não interpretável: a combinação fica
  marcada como aguardando tratamento manual, o comando segue com as demais e sai no fim com código
  próprio listando as marcadas; o pacote é recusado enquanto houver alguma (FR-022). Não existe
  descarte automático.
- Dois processos recebem a mesma combinação (dois `generate` com todos os problemas, o uso
  normal com duas máquinas, ou um `execute` rodando junto de um `generate`): só um a trata; o
  outro a pula, a conta no resumo e segue para a seguinte; nenhum arquivo é duplicado nem
  corrompido, e a próxima rodada retoma o que faltar (FR-026a).
- Falha de infraestrutura (Ollama fora do ar) ocorre repetidamente, sem nunca voltar a responder:
  a mesma chamada é repetida até um teto de repetições consecutivas configurável no `.env`
  (FR-018a); ao atingi-lo, o comando para com erro de infraestrutura, sem gravar nada daquela
  tentativa e sem consumir o orçamento de tentativas — rodar o comando de novo, com o serviço de
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
  (`qwen2.5-coder:14b` via Ollama desde 2026-10-06, `research.md` R20; era o
  Qwen2.5-Coder-7B) até obter uma suíte, nas fases de FR-022: aceita, de reserva (FR-022a) ou
  por predição (FR-022c). Nenhuma combinação termina sem suíte no fluxo normal (revisado em
  2026-10-06; antes uma suíte podia ser descartada depois de 12 tentativas).
- **FR-002**: Cada chamada ao modelo MUST ser uma única requisição *stateless* — sem reter ou
  reaproveitar histórico de nenhuma chamada anterior, para o mesmo ou para outro problema ×
  cenário (Constitution, Princípio III).
- **FR-002a**: A resposta MUST ser pedida em *streaming* e montada no cliente: o conteúdo é a
  junção dos pedaços, e modelo, `created_at`, `done_reason`, contagens de *tokens* e durações vêm
  do último pedaço (`done: true`), de modo que o registro gravado seja idêntico ao da mesma chamada
  sem *streaming*; nada do transporte MUST entrar no `run.json`, e uma execução começada sem
  *streaming* MUST continuar com `--resume`. Decidido em 2026-10-07 (R25).
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
  **Revisado em 2026-10-05** (`research.md` R14, depois do piloto 2): também a escrever todo valor
  por extenso, sem abreviações como "..." ou "(repeated N times)".
- **FR-008**: A janela de contexto (`num_ctx`) MUST ser grande o suficiente para o maior prompt
  entre os 200 problemas, com folga; o valor exato MUST ser medido e fixado no planejamento
  técnico da feature (fora do escopo desta especificação).

### Formato de resposta e interpretação

- **FR-009**: A resposta do modelo MUST ser texto plano com 3 blocos marcados, nesta ordem —
  `<edge_cases_analysis>`, `<reference_py>` e `<inputs>` (contendo um ou mais `<input>`) — nunca
  JSON, para evitar erros de escape de código dentro da solução Python. A ordem é a que o template
  pede (até 2026-10-06 era análise, entradas, solução; `research.md` R17). Só nas tentativas por
  predição (FR-022c) a resposta tem 2 blocos, `<edge_cases_analysis>` e `<tests>`.
- **FR-010**: O sistema MUST interpretar deterministicamente os 3 blocos da resposta crua; se
  qualquer bloco obrigatório estiver ausente, vazio ou malformado, a tentativa correspondente
  MUST ser registrada como falha de interpretação (uma das razões de descarte de tentativa, ver
  FR-018). Duas regras fixas, cada ocorrência registrada por tentativa e somada por cenário no
  relatório (decididas em 2026-10-04): uma cerca Markdown que envolve o `<reference_py>` inteiro
  (primeira linha ```` ```python ````, ```` ```py ```` ou ```` ``` ````; última ```` ``` ````) MUST
  ser removida, e nenhuma outra; um `<input>` vazio MUST ser descartado sozinho, e só a resposta
  com todos os `<input>` vazios é falha de interpretação.
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
  falha, consumindo uma unidade do orçamento (as 15 tentativas de FR-022), quando: (a) a resposta
  crua não pode ser interpretada (FR-010); (b) a solução Python falha em pelo menos um teste
  público do problema (se a primeira falha for WA, as entradas geradas MUST rodar assim mesmo, para
  a tentativa poder ser reserva; com RE, TLE ou MLE nenhuma roda — regra de 2026-10-05, restaurada
  em 2026-10-06 depois de um dia em que as entradas rodavam após qualquer falha, para a baixa
  confiança, que deixou de existir);
  ou (c) a solução Python falha — por erro de execução, por timeout (FR-016), ou por qualquer
  combinação das duas razões entre entradas diferentes — em 100% das entradas geradas (ou seja,
  nenhuma entrada sobrevive ao descarte individual de FR-019; uma tentativa nunca é aceita com
  suíte de tamanho zero); ou (d) o próprio modelo falha a chamada, sem resposta — o Ollama
  interrompe a geração com `token repeat limit reached` (razão `repetition`, acrescentada em
  2026-10-04: com a mesma seed o laço se repetiria, então não é falha de infraestrutura).
- **FR-018a**: Uma falha de infraestrutura na chamada ao Ollama (serviço inacessível, timeout de
  conexão, erro do lado do servidor que não seja a falha do modelo de FR-018(d), resposta em
  *streaming* que termina antes do último pedaço — desde 2026-10-07, R25) MUST NOT consumir uma unidade do orçamento de tentativas —
  a mesma chamada, com a mesma seed, MUST ser reexecutada quando o serviço voltar a responder.
  As repetições consecutivas de uma mesma chamada MUST ter um teto, e o tempo máximo de espera de
  uma resposta MUST ser um *timeout* de leitura (desde 2026-10-07, o maior silêncio entre dois
  pedaços da resposta, R25); nada de uma resposta incompleta MUST ser gravado; ambos são configuráveis pelo operador no `.env`
  (com valor padrão). Atingir o teto MUST encerrar o comando com erro de infraestrutura, sem
  gravar a tentativa e sem consumir o orçamento; a próxima execução refaz a mesma chamada.
- **FR-019**: Quando a solução Python falha (erro de execução ou timeout) em algumas entradas
  geradas, mas não em todas, MUST ser descartada só a entrada que falhou — a suíte mantém as
  demais entradas, e o descarte MUST registrar qual entrada e por quê.

### Retentativas e descarte

- **FR-020**: A seed, a temperatura e a fase de cada tentativa MUST vir de uma única tabela
  explícita no código (tentativa → fase, seed, temperatura), gravada no `run.json` e comparada pelo
  `--resume`; cada tentativa MUST registrar no seu arquivo a seed, a temperatura e a fase usadas, e
  nenhum par (seed, temperatura) se repete numa combinação. A tabela (desde 2026-10-06, R21):

  | Tentativa | Fase | Seed | Temperatura |
  |---|---|---|---|
  | 1 a 6 | 1 (solução) | 42 a 47 (41 + n) | 0,7 |
  | 7 a 12 | 2 (solução) | 48 | 0,7; 0,6; 0,5; 0,4; 0,3; 0,2 |
  | 13 a 15 | 4 (predição) | 49, 50, 51 | 0,7 |

  Até 2026-10-06 a seed era 42 + n e a temperatura, 0,7 em todas as tentativas.
- **FR-021**: As novas tentativas MUST acontecer em rodadas: depois de cada execução, somente os
  problemas × cenários cuja tentativa foi marcada como falha (FR-018) MUST voltar para uma nova
  chamada de geração, com a próxima seed; combinações já aceitas MUST NOT ser regeneradas. A
  falha de interpretação (FR-018, razão (a)) é a exceção: como não há nada a executar, a fase de
  geração já faz a tentativa seguinte, com a próxima seed, na mesma execução, sem esperar uma
  rodada de execução (decidido no plano, 2026-09-30, `research.md` R8).
- **FR-022**: Nenhum problema × cenário MUST terminar sem suíte no fluxo normal. As fases, em
  ordem (R21, 2026-10-06): **fase 1**, tentativas 1–6 (seed varia, temperatura 0,7) e **fase 2**,
  tentativas 7–12 (seed 48, temperatura decrescente), as duas terminando na primeira tentativa
  cuja solução passa em todos os testes públicos (`accepted`); **fase 3**, reserva (FR-022a);
  **fase 4**, predição (FR-022c); **fase 5**: se nem a predição produzir uma resposta
  interpretável, a combinação MUST ficar marcada como aguardando tratamento manual: o comando MUST
  continuar com as demais combinações e, no fim, sair com um código de saída próprio listando todas
  as marcadas; o relatório MUST contá-las à parte e o pacote final (FR-028) MUST ser recusado
  enquanto existir alguma. Não há tentativas extras nem suíte de baixa confiança. (Até 2026-10-05:
  descarte depois de 6 tentativas; até 2026-10-06: 8 estritas, extras até a 20ª e baixa
  confiança.)
- **FR-022a**: Uma tentativa **pode ser reserva** se a resposta foi interpretada, a solução
  reprovou um teste público por WA (não RE, TLE ou MLE) e ao menos uma entrada gerada foi mantida.
  Quando as 12 tentativas das fases 1 e 2 falharam e alguma pode ser reserva, a suíte MUST ser a
  da melhor delas (mais testes públicos aprovados; depois mais entradas mantidas; depois o menor
  número), com status `accepted_fallback`, sem nova chamada. Decidido em 2026-10-05 (`research.md`
  R16); entre 12 tentativas desde 2026-10-06 (R21).
- **FR-022b**: *(removido em 2026-10-06, R21: a suíte de baixa confiança, `accepted_low_confidence`,
  deixou de existir.)*
- **FR-022c**: Se nenhuma das 12 pode ser reserva, o mesmo modelo MUST receber um
  segundo template (`src/prompt_templates/slm_predict_prompt.txt`), com a mesma composição de
  cenários (FR-004) e o mesmo exemplo (FR-005), que pede entradas **e** saídas esperadas
  diretamente, sem solução Python, em dois blocos: `<edge_cases_analysis>` e `<tests>` (cada
  `<test>` com um `<input>` e um `<output>`). As regras de entrada são as do template principal
  (restrições, casos-limite, tamanho máximo, sem entrada vazia ou repetida). Não há validação pelos
  testes públicos (não existe programa a validar). Uma nova tentativa MUST acontecer só por
  resposta não interpretável, até 3 (tentativas 13 a 15, seeds 49 a 51, temperatura 0,7; FR-020).
  A suíte recebe status `accepted_predicted`. Decidido em 2026-10-06.
- **FR-022d**: Uma combinação aguardando tratamento manual (FR-022) só MUST sair desse estado por
  um comando explícito dos autores, que a fecha com o status `discarded_manual` e um motivo
  obrigatório, gravados com a data no resultado da combinação. Esse é o único caminho para uma
  combinação terminar sem suíte; ela continua contando no N = 200 e é reportada à parte (FR-023).
  Decidido em 2026-10-06.
- **FR-023**: O relatório MUST contar as combinações por status (`accepted`, `accepted_fallback`,
  `accepted_predicted`, `discarded_manual` e aguardando tratamento manual), por cenário e no total,
  e mostrar, por cenário, em qual fase e em qual tentativa cada combinação ficou com a suíte. Nas
  métricas do experimento, as `accepted_fallback` contam como as `accepted` e as
  `accepted_predicted` ficam separadas (saídas não calculadas por nenhum programa). Decidido em
  2026-10-06 (R20, R21).
- **FR-024**: O resultado de cada problema × cenário MUST registrar todas as seeds usadas
  (inclusive das tentativas que falharam), o motivo de cada falha e, quando houver sucesso, qual
  tentativa foi aceita.

### Reprodutibilidade e proveniência

- **FR-025**: A temperatura e a seed de cada tentativa MUST seguir a tabela de FR-020 e ser
  registradas; o hardware em que o Ollama
  rodou (etiqueta de configuração manual, FR-003a) MUST ser registrado junto com os resultados de
  cada chamada.
- **FR-026**: O pipeline (ambas as fases) MUST poder ser interrompido e retomado a qualquer
  momento sem duplicar nem corromper dados já persistidos (Constitution, Princípio VII).
- **FR-026a**: Vários `generate --resume` e um `execute` MUST poder rodar ao mesmo tempo sobre a
  mesma execução (por exemplo, dois `generate` com todos os problemas, cada um ligado a um servidor
  Ollama, que assim dividem o trabalho sozinhos, R26), sem duplicar nem corromper nada: cada combinação é tratada por um processo de cada vez
  (trava exclusiva por combinação); uma combinação em uso por outro processo MUST ser pulada e
  contada no resumo final, nunca esperada; `package` e `close` MUST continuar exigindo que nenhum
  outro comando esteja rodando (recusa com código 1), assim como o `generate` que começa a execução
  (sem `--resume`); um segundo `execute` MUST ser recusado com código 1 (o *slot* do motor é um
  só). Decidido em 2026-10-07 (R24).
- **FR-027**: O sistema MUST produzir um relatório versionável, agregando: a contagem por status
  e a fase e tentativa em que cada combinação ficou com a suíte (FR-023), distribuição do tamanho das suítes aceitas, funil de falha de tentativa
  por razão (não interpretável, falha em teste público, falha — erro de execução e/ou timeout —
  em 100% das entradas, falha do modelo por repetição), seeds usadas por combinação e hardware
  registrado por chamada; e, por cenário, as respostas cortadas pelo teto de saída
  (`done_reason = "length"`), as cercas Markdown removidas e os `<input>` vazios descartados
  (FR-010).
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
  identificada pelo número da tentativa (1 a 12 com solução Python, 13 a 15 por predição), com a
  fase, a seed e a temperatura da tabela de FR-020; guarda a resposta crua, o
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
- **Suíte de reserva** (`accepted_fallback`): a suíte tirada de uma tentativa que reprovou um
  teste público por WA, depois de 12 tentativas sem acerto (FR-022a); tem o mesmo formato da
  aceita, mas saídas esperadas possivelmente erradas.
- **Suíte por predição** (`accepted_predicted`): entradas e saídas esperadas escritas diretamente
  pelo modelo com o segundo template, sem solução Python nem validação (FR-022c).
- **Relatório de geração de suítes SLM**: dado quantitativo agregado (taxa de descarte,
  distribuição de tamanho de suíte, funil de falha por razão, seeds e hardware), para citação no
  texto do TCC sem reabrir os arquivos-fonte das suítes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Para cada uma das 600 combinações (200 problemas × 3 cenários), a execução
  completa termina em exatamente um de três estados — `accepted`, `accepted_fallback` ou
  `accepted_predicted`, com o tamanho, a fase e a tentativa usada registrados
  — ou, só por decisão explícita dos autores, `discarded_manual` com motivo (FR-022d); nunca um
  estado intermediário ou ambíguo no pacote final.
- **SC-002**: 100% dos casos de teste mantidos em suítes aceitas têm `expected_output`
  calculado por execução real da solução Python sobre a entrada, nunca por previsão do modelo.
- **SC-003**: A proporção de suítes de cada status é medida e reportada separadamente, por cenário
  e no total, sem reduzir silenciosamente o N = 200 usado pelas demais métricas do experimento.
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
  das tentativas em nenhuma execução observada — só as razões de FR-018 consomem
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
  problema × 10 e memória = limite do problema × 4 (ambos a confirmar no piloto).
  **Revisado em 2026-10-04** (`research.md` R13, depois do piloto 1): `num_predict = 5120`, com a
  razão mínima medida de 3,32 caracteres por *token*; maior prompt com o template novo: 8.074. Temperatura e
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
  responde em texto plano com 3 blocos marcados por tags (`<edge_cases_analysis>`, `<reference_py>`,
  `<inputs>` com vários `<input>`; ordem de R17, 2026-10-06), interpretados deterministicamente pelo pipeline; a suíte
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
