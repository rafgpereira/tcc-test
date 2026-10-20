# Feature Specification: Terceiro modelo comercial: Claude

**Feature Branch**: `008-claude-test-generation`

**Created**: 2026-10-20

**Status**: Draft

**Input**: User description: "Módulo 008 — terceiro modelo comercial: Claude (Anthropic)
claude-haiku5.5, --model claude, nas mesmas condições do GPT-5.4-mini e do Gemini 3.8 Flash
(feature 004): mesmo prompt numa única mensagem, sem memória entre pedidos, resposta JSON no mesmo
formato, raciocínio equivalente ao medium, barreira de resposta sem raciocínio, até 3 tentativas,
teto de gasto por invocação, dry-run com estimativa, piloto nos 5 problemas dos pilotos,
pacote/manifesto/relatório próprios e camada claude_suites no cli check. Roda direto sobre a
revisão 2 do dataset. A decidir no clarify: qual modelo Claude, o valor do raciocínio equivalente
ao medium, e se a barreira de raciocínio vale igual."

## Contexto

O experimento compara as suítes de teste geradas por um modelo local (Qwen2.5-Coder-14B) e por dois
modelos comerciais (GPT-5.4-mini e Gemini 3.8 Flash), nos 200 problemas do dataset e nos 3
cenários de contexto. Os dois comerciais seguem as regras da feature 004: o mesmo texto-base numa
única mensagem, nenhuma memória entre pedidos, resposta em JSON com análise de casos-limite e
testes, raciocínio `medium`, até 3 tentativas por falha de formato, teto de gasto por invocação,
dry-run sem custo e um pacote por modelo.

Em 2026-10-20 os autores decidiram acrescentar um terceiro modelo comercial, da Anthropic, o
**Claude Haiku 5.5**: o modelo menor e mais barato da família, na mesma faixa dos outros dois. Ele
roda nas mesmas condições, para a comparação entre os comerciais ficar justa, e já sobre a
revisão 2 do dataset (enunciados corrigidos, feature 007).

Na mesma data, a regra da resposta sem raciocínio da feature 004 foi emendada (FR-018a da 004):
a resposta fica guardada em `barred/`, sem gastar tentativa; a combinação é pedida de novo; e,
na terceira resposta assim, a suíte é `accepted_barred`, com os testes da última resposta legível.

## Clarifications

### Session 2026-10-20

- Q: Qual modelo Claude entra no experimento como terceiro modelo comercial? → A: Claude Haiku 5.5 (`claude-haiku-5-5`), o modelo pequeno da família, na mesma faixa dos outros dois comerciais (P1).
- Q: Que nível de raciocínio (`effort`) o Claude recebe, para equivaler ao `medium` do GPT e do Gemini? → A: `effort: medium`, enviado explicitamente, com raciocínio adaptativo ligado (P2).
- Q: A regra da resposta sem raciocínio vale igual para o Claude? → A: Sim, a mesma regra emendada da 004 (resposta em `barred/`, a combinação é pedida de novo, e na 3ª a suíte é `accepted_barred`); como a resposta detecta a falta de raciocínio (contagem de tokens ou ausência do bloco de raciocínio) é conferido na documentação oficial no plano (P3).
- Q: Qual teto de tokens de saída por resposta o Claude recebe? → A: 32.768 tokens, o mesmo dos outros dois comerciais.

## Pendências para o clarify

Levantadas pelos autores no pedido desta especificação:
- **P1 — Qual modelo Claude**: **resolvida** (Clarifications): Claude Haiku 5.5, `claude-haiku-5-5`.
- **P2 — Raciocínio equivalente ao `medium`**: **resolvida** (Clarifications): `effort: medium`,
  explícito, com raciocínio adaptativo.
- **P3 — Barreira de raciocínio**: **resolvida** (Clarifications): vale a mesma regra emendada; o
  sinal de falta de raciocínio é definido no plano.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Gerar a suíte de uma combinação com o Claude (Priority: P1)

Um autor gera, com `--model claude`, a suíte de um problema e cenário. O pedido é o mesmo dos outros
dois modelos comerciais: o mesmo texto-base, numa única mensagem, sem memória de pedidos
anteriores. A resposta crua é gravada inteira, interpretada pelas mesmas regras e vira um
`suite.json` com o mesmo contrato dos outros modelos.

**Why this priority**: sem isso não há terceiro modelo; é o núcleo da feature.

**Independent Test**: com um provedor falso que devolve uma resposta conhecida, gerar uma combinação
e conferir a tentativa gravada, a suíte e o pedido enviado (sem histórico, sem campos proibidos,
raciocínio pedido).

**Acceptance Scenarios**:

1. **Given** o dataset da revisão 2 conferido, **When** o autor gera uma combinação com `--model
   claude` e confirma o gasto, **Then** é feito um único pedido autocontido com o prompt do
   texto-base dos modelos comerciais, e a resposta lida vira `suite.json` (`accepted_predicted`).
2. **Given** uma resposta fora do formato, **When** ela é interpretada, **Then** a tentativa é
   gravada como falha de formato e um novo pedido é feito, até 3; depois, a combinação aguarda os
   autores (`close`).
3. **Given** uma resposta sem raciocínio, **When** ela chega, **Then** fica em `barred/`, sem gastar
   tentativa, e a combinação é pedida de novo; na terceira, a suíte é `accepted_barred`.
4. **Given** um pedido gravado, **When** o autor roda `show-request --model claude`, **Then** recebe
   o corpo enviado, conferido contra o hash e o dataset, como nos outros modelos.

---

### User Story 2 - Saber o custo antes e nunca pagar sem confirmar (Priority: P1)

O autor estima o custo do Claude sem nenhuma chamada. Nenhuma chamada paga sai sem a confirmação
e o teto de gasto da invocação.

**Why this priority**: cada chamada custa dinheiro; é a mesma garantia dada aos outros dois.

**Independent Test**: dry-run sem chave nem rede dá a estimativa por cenário e no total; `generate`
sem `--confirm-spend` não chama nada; com teto baixo, para no teto.

**Acceptance Scenarios**:

1. **Given** nenhuma chave configurada, **When** o autor roda o dry-run do Claude, **Then** vê o
   número de combinações, de pedidos, os tokens estimados e a faixa de custo, sem nenhuma chamada.
2. **Given** um teto de gasto, **When** o gasto da invocação o atinge, **Then** nenhum pedido novo
   sai, os em andamento terminam e são gravados, e o comando sai com o código do teto.

---

### User Story 3 - Piloto, retomada e execução completa (Priority: P2)

O autor roda o piloto nos 5 problemas dos pilotos anteriores (1000_B, 1005_C, 1008_B, 1_B e 61_B),
nos 3 cenários. O piloto mede tokens, tempo, custo e taxa de falha, e depois é guardado à parte.
Em seguida vem a execução completa (600 combinações), que pode ser interrompida e retomada sem
refazer nada nem pagar de novo.

**Why this priority**: o piloto confere o raciocínio e o custo real antes da execução paga completa.

**Independent Test**: interromper a geração no meio e retomá-la não refaz nenhuma tentativa gravada.
Uma falha de infraestrutura nunca conta como tentativa.

**Acceptance Scenarios**:

1. **Given** uma execução interrompida, **When** o autor retoma com `--resume`, **Then** só as
   combinações pendentes recebem pedido.
2. **Given** o piloto terminado, **When** os autores o guardam à parte, **Then** a execução
   completa começa do zero, e só o relatório do piloto é versionado.

---

### User Story 4 - Relatório, pacote e conferência (Priority: P3)

O autor gera o relatório, o pacote e o manifesto do Claude, separados dos outros modelos. O `cli
check` passa a conferir uma camada `claude_suites`.

**Why this priority**: sustenta os números do TCC e a reprodutibilidade, como nos outros modelos.

**Independent Test**: com uma execução terminada, o pacote se gera e se confere pelo `verify`. O
`cli check --deep` sai `OK` com a camada nova, e as camadas dos outros modelos não mudam.

**Acceptance Scenarios**:

1. **Given** as 600 combinações encerradas, **When** o autor roda `package --model claude`,
   **Then** são gerados `data/claude_suites.zip`, o manifesto e o relatório do Claude.
2. **Given** o pacote do Claude, **When** o autor roda `cli check --deep`, **Then** a camada
   `claude_suites` confere 200 problemas × 3 cenários, e as dos outros modelos saem como antes.

---

### Edge Cases

- **Chave só para alguns modelos**: o Claude sem chave não roda; os outros modelos rodam
  normalmente.
- **Resposta cortada pelo teto de saída, recusa ou bloqueio**: falha de formato, como nos outros
  modelos.
- **Limite de pedidos da conta (rate limit) ou serviço fora do ar**: falha de infraestrutura. O
  mesmo pedido é repetido com espera crescente (ou a espera pedida pela API), sem gastar
  tentativa.
- **Erro que não passa sozinho** (chave recusada, crédito esgotado, modelo inexistente): o comando
  para na hora, sem gastar tentativa.
- **Modelo devolvido diferente do pedido**: registrado em cada tentativa, como nos outros modelos.
- **Cache de prompt do provedor**: se a API cobrar menos por um início de prompt repetido, os
  tokens servidos de cache são registrados por causa do custo. Isso não leva conteúdo de um pedido
  para outro.
- **Rodar junto com os outros modelos**: cada modelo tem a sua pasta, e uma execução do Claude
  nunca bloqueia nem altera a do GPT, a do Gemini ou a do modelo local.

## Requirements *(mandatory)*

### Modelo e pedidos

- **FR-001**: O sistema MUST aceitar `--model claude` em todos os comandos que hoje aceitam `--model
  gpt|gemini`: `generate`, o dry-run, `close`, `change-template --template llm`, `report`,
  `package`, `verify` e `show-request`. O comportamento é o mesmo, com uma pasta, um pacote, um
  manifesto e um relatório próprios.
- **FR-002**: O modelo MUST ser o Claude Haiku 5.5, identificador `claude-haiku-5-5` (decidido no
  clarify, P1), gravado na configuração da execução. O modelo devolvido em cada resposta MUST ser
  registrado.
- **FR-003**: Cada pedido MUST ser autocontido: uma única mensagem de usuário com o texto inteiro,
  sem instrução de sistema, sem histórico e sem estado guardado pelo provedor. Nada de temperatura,
  seed ou outros parâmetros de amostragem, como nos outros dois (A3 e A11 da 004).
- **FR-004**: O prompt MUST ser o mesmo texto-base dos modelos comerciais (`llm_prompt.txt`), com
  o mesmo hash dos outros dois na mesma execução; só o contexto do cenário varia.
- **FR-005**: O raciocínio MUST ser pedido explicitamente no nível `medium`, o mesmo nível nominal dos
  outros dois (decidido no clarify, P2), com o raciocínio adaptativo ligado, e gravado na
  configuração da execução.
- **FR-006**: A resposta MUST ser pedida em JSON com o mesmo formato dos outros dois (análise de
  casos-limite e lista de testes com entrada e saída). Ela é interpretada pelas mesmas regras e
  pelas mesmas 7 falhas de formato.
- **FR-006a**: O teto de tokens de saída de cada resposta (raciocínio e resposta juntos) MUST ser
  32.768, o mesmo dos outros dois comerciais (decidido no clarify), fixo e gravado na configuração
  da execução. Uma resposta cortada pelo teto é falha de formato (`truncated`).
- **FR-007**: A chave de API MUST ficar só no `.env` (nunca no Git nem na imagem); o
  `.env.example` ganha a variável, sem valor.

### Tentativas, barreira e falhas

- **FR-008**: As tentativas, as falhas de formato, o `close` dos autores e as falhas de
  infraestrutura MUST seguir as regras da 004 (FR-015 a FR-018): até 3 tentativas por falha de
  formato, e uma falha de infraestrutura nunca gasta tentativa.
- **FR-009**: Toda resposta MUST ter o raciocínio conferido, e a resposta sem raciocínio segue a
  mesma regra emendada da 004 em 2026-10-20 (decidido no clarify, P3):
  - a resposta fica em `barred/`, sem gastar tentativa;
  - a combinação é pedida de novo;
  - na terceira resposta assim, a suíte é `accepted_barred`, com os testes da última legível.

  O sinal de "sem raciocínio" (contagem de tokens de raciocínio igual a zero ou ausente, ou nenhum
  bloco de raciocínio na resposta) MUST ser definido no plano, a partir da documentação oficial,
  e coberto por teste.

### Custo, reprodutibilidade e execução

- **FR-010**: Toda chamada MUST registrar tokens (entrada, cache, saída e raciocínio), custo
  estimado e tempo. O preço vem de uma tabela com data e fonte oficial, conferida no planejamento,
  nunca suposta.
- **FR-011**: O dry-run MUST estimar, sem nenhuma chamada nem chave, os pedidos, os tokens e a faixa
  de custo do Claude, por cenário e no total.
- **FR-012**: Nenhuma chamada paga MUST sair sem a confirmação explícita e o teto de gasto da
  invocação (FR-022 e FR-022a da 004).
- **FR-013**: O número de pedidos simultâneos e o ritmo por minuto MUST ser configuráveis no
  `.env`, como nos outros dois.
- **FR-014**: A execução MUST registrar o hash do manifesto do dataset da revisão 2. Ela é recusada
  se o dataset descompactado não bater com o manifesto.
- **FR-015**: O piloto MUST ser uma execução separada da completa, nos 5 problemas dos pilotos
  anteriores e nos 3 cenários. Ele é guardado à parte, e só o seu relatório é versionado. O piloto
  mede os tokens de saída, a taxa de falha de formato e o raciocínio, e serve para conferir se o teto
  de saída (32.768) basta e o custo real.

### Relatório, pacote e conferência

- **FR-016**: O sistema MUST gerar `manifests/claude_generation_report.json`,
  `data/claude_suites.zip` e `manifests/claude_suites.manifest.json`, no mesmo formato dos outros
  dois modelos comerciais.
- **FR-017**: O `python -m cli check` MUST ganhar a camada `claude_suites`, com as mesmas
  conferências das camadas `gpt_suites` e `gemini_suites`, e entrar na relação 1:1 com o dataset.
- **FR-018**: O leitor comum de suítes (`SuiteView`) MUST ler os `suite.json` do Claude sem
  distinção dos outros modelos.

### Fora do escopo

- **FR-019**: Este módulo MUST NOT alterar o comportamento nem os artefatos do modelo local, do GPT
  ou do Gemini. As execuções e os pacotes deles continuam válidos e são conferidos como antes.

### Key Entities

- **Configuração da execução do Claude** (`run.json`): o modelo pedido, os parâmetros enviados
  (incluindo o raciocínio), o schema da resposta, o hash do texto-base, o hash do manifesto do
  dataset, a tabela de preço e o teto de saída.
- **Tentativa**: uma resposta com raciocínio; guarda a resposta crua, a interpretação, os tokens,
  o custo e o tempo.
- **Resposta barrada**: uma resposta sem raciocínio, guardada fora das tentativas.
- **Suíte** (`suite.json`): o mesmo contrato dos outros modelos (`accepted_predicted`,
  `accepted_barred` ou `discarded_manual`).
- **Relatório, pacote e manifesto do Claude**: um conjunto por modelo, versionados.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Ao fim da execução completa, cada uma das 600 combinações do Claude está em
  exatamente um estado encerrado: `accepted_predicted`, `accepted_barred` ou `discarded_manual`.
- **SC-002**: 100% dos pedidos do Claude são autocontidos e usam o mesmo texto-base, com o mesmo
  hash, dos outros dois modelos comerciais.
- **SC-003**: 100% das chamadas têm tokens, custo e tempo registrados. O custo total do relatório é
  a soma das chamadas, incluindo as respostas barradas.
- **SC-004**: Zero chamadas pagas acontecem sem confirmação e teto, verificado por teste.
- **SC-005**: Interromper e retomar em qualquer ponto não refaz nenhuma tentativa gravada.
- **SC-006**: `python -m cli check --deep` sai `OK` com as camadas do dataset, dos mutantes e dos
  4 modelos.
- **SC-007**: Os testes automatizados das features 003, 004 e 007 continuam passando sem mudança de
  comportamento.

## Assumptions

- **Usuários**: os dois autores, em contêiner, com uma chave própria de uma conta da Anthropic com
  faturamento ativo.
- **Mesma infraestrutura da 004**: o Claude reaproveita o que os outros dois modelos comerciais
  usam (tentativas, barreira, teto, dry-run, relatório, pacote, `cli check`). A parte nova é o
  cliente da API da Anthropic, a configuração e os preços.
- **Revisão 2 do dataset**: o Claude não roda sobre a revisão 1, porque a execução dele começa
  depois da revisão 2.
- **Nomes, preços e parâmetros**: o identificador exato do modelo, os preços e o parâmetro de
  raciocínio são conferidos na documentação oficial da Anthropic no planejamento, com data e
  fonte, nunca supostos.
- **Sem seed nem temperatura**: como os outros dois, o Claude não recebe parâmetros de amostragem.
  Com o raciocínio ligado, a API não permite ajustar a temperatura. As respostas não são
  reproduzíveis bit a bit, e isso entra nas limitações.
- **Versionamento**: só o pacote da execução final e os relatórios são versionados, como nos outros
  modelos.

## Divergências e Decisões sobre a Metodologia

- **D1 — Terceiro modelo comercial (decidido pelos autores em 2026-10-20)**: o desenho do TCC
  passa de 2 para 3 modelos comerciais, com o **Claude Haiku 5.5** nas mesmas condições do
  GPT-5.4-mini e do Gemini 3.8 Flash. As comparações entre modelos ganham um participante, e a
  metodologia e o texto do TCC precisam refletir isso.
- **D2 — Mesmas condições da 004 (decidido pelos autores)**: o mesmo texto-base, uma mensagem só,
  nenhuma memória entre pedidos, JSON no mesmo formato, até 3 tentativas, teto de gasto e um pacote
  próprio. Só o cliente da API e o parâmetro de raciocínio são específicos do Claude.
- **D3 — Execução direto sobre a revisão 2 do dataset (decidido pelos autores)**: o Claude nunca
  usa a revisão 1.
