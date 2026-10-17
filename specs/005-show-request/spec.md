# Feature Specification: Visualizar o pedido enviado a cada modelo

**Feature Branch**: `005-show-request`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "Módulo 005 — visualizar o pedido enviado a cada modelo. Um comando
python -m ai_clients show-request --model gemini --problem 1_B --scenario black_box [--attempt N]
mostra o prompt e o corpo HTTP exatos de uma tentativa já feita (ou do pedido que seria feito, se
ainda não houve tentativa), sem chamar nenhuma API. O texto é reconstruído a partir do texto-base e
dos arquivos do problema e conferido contra o prompt_sha256 gravado; se não bater, avisa e não
mostra. Mostra também o resumo da resposta (modelo devolvido, término, tokens, custo) e pode gravar
tudo num arquivo. Vale para gpt e gemini e, se possível, para o slm. A decidir no clarify: incluir
o SLM; saída no terminal, arquivo ou os dois; mostrar a resposta crua; o que fazer quando o
texto-base mudou."

## Clarifications

### Session 2026-10-16

- Q: O comando de visualização deve valer também para o modelo local (SLM)? → A: Sim, os três
  modelos (`--model slm`, `gpt` ou `gemini`); no SLM, o texto-base de cada tentativa (solução nas
  1 a 12, predição nas 13 a 15) e o corpo com a seed e a temperatura dela (B1; FR-001).
- Q: A visualização deve aparecer no terminal, ser gravada num arquivo, ou os dois? → A: Gravar em
  arquivo, principalmente no dry-run: o `generate --dry-run` ganha a opção de gravar todos os
  pedidos que seriam enviados numa pasta (um arquivo por problema e cenário), com uma conferência
  automática de que o enunciado, o código e o exemplo dentro de cada prompt são idênticos aos
  arquivos do dataset e um aviso nos enunciados com expoente perdido; o `show-request` mostra no
  terminal e grava com `--output` (B2; FR-007, FR-011 a FR-013).
- Q: A visualização de uma tentativa feita deve mostrar a resposta crua do modelo, ou só um
  resumo? → A: Nenhum dos dois: a feature mostra só o que é enviado ao modelo (o prompt e o corpo
  da requisição), nunca a resposta nem um resumo dela (B3; FR-005).
- Q: Quando o texto-base usado numa tentativa não é mais o atual, o que o comando deve fazer? → A:
  Procurar no histórico do Git a versão do texto-base com o hash gravado; achando, mostrar o prompt
  montado com ela, avisando que é uma versão antiga; não achando, recusar mostrar o prompt e dizer
  o hash usado e o atual (B4; FR-003).
- Q (analyze): O que o dry-run grava para cada combinação: o prompt e o corpo, ou só o corpo? → A:
  Só o corpo da requisição, porque o prompt inteiro já vem dentro dele; um arquivo por problema e
  cenário (FR-011).
- Q (analyze): O `show-request` mostra o pedido no terminal? → A: Não; só grava o corpo num
  arquivo e confere que nada do dataset se perdeu. No terminal aparece só o resultado das
  conferências (FR-005, FR-007).
- Q (analyze): Como conferir o dry-run do Gemini, cuja execução completa já começou? → A: Os
  autores rodam um dry-run separado para o Gemini; o critério vale para as combinações gravadas
  (SC-005).
- Q (analyze): É preciso medir o tempo de cada visualização? → A: Não (SC-003).

## Decisões do clarify (B1 a B4)

Os autores pediram que estes pontos fossem decididos no `/speckit-clarify`; os quatro foram
decididos em 2026-10-16 (Clarifications acima). Os requisitos os citam pelo rótulo.

- **B1 — Incluir o modelo local (SLM)?** — **DECIDIDA em 2026-10-16**: sim, os três modelos no
  mesmo comando.
- **B2 — Onde sai a visualização: terminal, arquivo ou os dois?** — **DECIDIDA em 2026-10-16**:
  arquivos, com ênfase no dry-run (todos os pedidos de uma vez numa pasta, conferidos contra o
  dataset). **Refinado no analyze (2026-10-16)**: cada arquivo é só o corpo da requisição, que
  traz o prompt, e o `show-request` também só grava, sem mostrar o pedido no terminal.
- **B3 — Mostrar a resposta crua do modelo?** — **DECIDIDA em 2026-10-16**: não; a feature
  mostra só o que é enviado ao modelo, sem a resposta nem um resumo dela.
- **B4 — O que fazer quando o texto-base usado na tentativa não é mais o atual?** — **DECIDIDA em
  2026-10-16**: procurar no histórico do Git a versão com o hash gravado e montar o prompt com ela,
  avisando que é uma versão antiga; sem ela, recusar mostrar o prompt e dizer os dois hashes.

## User Scenarios & Testing *(mandatory)*

<!--
  Os "usuários" são os dois autores do TCC. Eles precisam ver, sem gastar nada, exatamente o que
  cada modelo recebeu em cada problema e cenário, para conferir o desenho experimental (o mesmo
  texto para os modelos, só o contexto mudando entre cenários), investigar uma resposta estranha e
  mostrar exemplos reais no texto do TCC.
-->

### User Story 1 - Ver o pedido de uma tentativa já feita (Priority: P1)

Para um modelo, um problema e um cenário que já têm tentativas gravadas, os autores pedem a
visualização e recebem, num arquivo, o corpo exato da requisição daquela tentativa (a última, por
padrão, ou uma escolhida), com o prompt completo dentro dele, e a confirmação de que o texto
gravado é o mesmo que foi enviado e não perdeu nada do dataset. A resposta do modelo não faz parte
da visualização (B3).

**Why this priority**: é o motivo da feature: hoje cada tentativa grava só a impressão digital
(hash) do prompt, e não há um jeito simples de ver o texto enviado.

**Independent Test**: com uma tentativa gravada (por exemplo, a do piloto do Gemini para `1_B`,
caixa-preta), o comando grava o corpo no arquivo pedido e diz que o hash confere e que o prompt é
fiel ao dataset; nenhuma API é chamada e nenhum outro arquivo é gravado.

**Acceptance Scenarios**:

1. **Given** uma combinação com tentativas gravadas, **When** os autores pedem a visualização sem
   escolher a tentativa, **Then** é gravado o pedido da última tentativa, e o comando diz o número
   dela.
2. **Given** uma combinação com 3 tentativas, **When** os autores escolhem a tentativa 2, **Then**
   é gravado o pedido da tentativa 2.
3. **Given** o prompt reconstruído, **When** o hash dele é comparado ao gravado, **Then** o comando
   diz que confere; se não conferir, o comando procura no histórico do Git a versão do texto-base
   que a tentativa usou (B4): achando, grava o pedido montado com ela e avisa que é uma versão
   antiga; não achando, não grava nada e diz o hash usado e o atual.
4. **Given** qualquer pedido de visualização, **When** ele termina, **Then** nenhuma API foi
   chamada, nenhum arquivo do experimento foi criado nem alterado, e o pedido não foi impresso no
   terminal.

---

### User Story 2 - Ver o pedido que seria feito, antes de gastar (Priority: P2)

Para uma combinação ainda sem tentativa, os autores recebem num arquivo o pedido que a próxima
geração enviaria, e o comando deixa claro que é uma prévia e não algo já enviado.

**Why this priority**: permite conferir um pedido antes de pagar por ele (por exemplo, depois de
mexer no texto-base), mas a feature já é útil sem isso.

**Independent Test**: para uma combinação sem tentativa, o comando grava o pedido e diz que é
"ainda não enviado".

**Acceptance Scenarios**:

1. **Given** uma combinação sem tentativas (ou um modelo que ainda não começou a execução),
   **When** os autores pedem a visualização, **Then** é gravado o pedido que seria enviado, e o
   comando avisa que é uma prévia.
2. **Given** uma combinação sem tentativas, **When** os autores pedem uma tentativa específica,
   **Then** o comando diz que ela não existe e não grava nada.

---

### User Story 3 - Guardar a visualização para consulta e para o texto do TCC (Priority: P3)

Os autores guardam o arquivo gravado para anexar a uma análise ou citar no texto do TCC (B2), sem
risco de perder um arquivo anterior.

**Why this priority**: conveniência; o arquivo já é gravado pela User Story 1, e esta história só
protege o que já existe.

**Independent Test**: o arquivo da User Story 1 é o mesmo corpo, como JSON, que a geração envia;
pedir de novo para o mesmo caminho é recusado, a menos que os autores peçam para sobrescrever.

**Acceptance Scenarios**:

1. **Given** um caminho de arquivo, **When** os autores pedem a visualização com ele, **Then** o
   arquivo é criado com o conteúdo da visualização e nenhum outro arquivo muda.
2. **Given** um caminho que já existe, **When** a visualização é pedida, **Then** o comando recusa
   sobrescrever, a menos que os autores peçam isso explicitamente.

---

### User Story 4 - Conferir todos os pedidos contra o dataset antes de pagar (Priority: P1)

Antes de uma execução paga, os autores rodam o dry-run com a opção de gravar os pedidos e recebem,
numa pasta, um arquivo por problema e cenário com o corpo exato da requisição que seria enviada
(o prompt inteiro vem dentro dele), mais um resumo da conferência: se o enunciado, o código e o exemplo de cada prompt são idênticos
aos arquivos do dataset, e quais enunciados têm expoente perdido (como `1 ≤ n ≤ 105` no lugar de
`10^5`).

**Why this priority**: é o pedido explícito dos autores (2026-10-16): ver, antes de pagar, que nada
do dataset se perde no caminho até o modelo.

**Independent Test**: `generate --model gpt --dry-run --save-requests PASTA` sobre o dataset real,
antes da execução do GPT, grava 600 arquivos e um resumo com 600 de 600 prompts fiéis ao dataset e
71 enunciados com expoente perdido (a contagem de 2026-10-16), sem chamar nenhuma API e sem tocar
em `data/suites/`. O Gemini, cuja execução completa já começou, é conferido num dry-run separado
pelos autores.

**Acceptance Scenarios**:

1. **Given** um dataset íntegro, **When** o dry-run grava os pedidos, **Then** cada combinação
   pendente tem um arquivo com o corpo da requisição, e o resumo diz quantos prompts são fiéis ao
   dataset.
2. **Given** um prompt em que algum trecho do dataset não aparece idêntico, **When** a conferência
   roda, **Then** a combinação é listada como divergente, com o arquivo e o trecho que falta.
3. **Given** um enunciado com expoente perdido, **When** a conferência roda, **Then** a combinação
   aparece como aviso (não erro), porque a perda vem do próprio dataset, que não é corrigido.
4. **Given** uma pasta que já tem arquivos, **When** o dry-run é pedido com ela, **Then** recusa,
   a menos que os autores peçam para sobrescrever.

---

### Edge Cases

- **Texto-base mudou depois da tentativa** (uma troca registrada ou o arquivo editado): o hash do
  texto-base gravado não é o do arquivo atual; o comando procura no histórico do Git a versão com
  aquele hash (B4). Um texto-base editado e nunca commitado não está no histórico: recusa, dizendo
  os dois hashes. Sem o Git disponível no ambiente, também recusa, com a mesma mensagem.
- **Arquivos do problema alterados** (dataset diferente do manifesto): o prompt não pode ser
  reconstruído com confiança; o comando recusa, como os demais comandos fazem com um dataset
  divergente.
- **Tentativa barrada por falta de raciocínio** (modelos comerciais): também é uma chamada enviada;
  pode ser escolhida e gravada, identificada como barrada.
- **Tentativa movida para `superseded/` por uma troca de texto-base**: não é uma tentativa atual da
  combinação; o comando não a acha pela numeração normal.
- **Combinação danificada**: o comando diz que os arquivos estão inconsistentes e não grava nada.
- **Problema, cenário ou modelo inexistente; tentativa fora do intervalo; arquivo de saída que já
  existe**: mensagem de uso incorreto, nada gravado.
- **Prompts grandes** (o maior tem cerca de 7.500 caracteres; o SLM, perto de 9.000): gravados
  inteiros, sem cortar.
- **Leitura durante uma geração do mesmo modelo** (por exemplo, a execução completa do Gemini
  rodando): os comandos leem o estado daquele momento; um arquivo que a geração ainda está
  escrevendo é ignorado, como nos demais comandos.
- **Segredos**: o corpo gravado nunca contém a chave da API (ela vai num cabeçalho, que não é
  mostrado).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST oferecer um comando que, dados o modelo, o problema e o cenário (e,
  opcionalmente, o número da tentativa), grava num arquivo o corpo exato da requisição daquela
  tentativa, com o prompt completo dentro dele; sem número, a última tentativa da combinação. Vale para os três modelos (B1,
  decidida em 2026-10-16): GPT, Gemini e o modelo local; no modelo local, com o texto-base que a
  tentativa usou (solução nas tentativas 1 a 12, predição nas 13 a 15) e o corpo enviado ao
  Ollama com a seed e a temperatura daquela tentativa.
- **FR-002**: O comando MUST NOT chamar nenhuma API, nem gravar ou alterar nenhum arquivo do
  experimento (só lê; a única escrita permitida é o arquivo de saída pedido em FR-007).
- **FR-003**: O prompt MUST ser reconstruído a partir do texto-base e dos arquivos do problema, do
  mesmo jeito que a geração o monta, e o hash dele MUST ser comparado ao hash gravado na tentativa;
  o resultado da comparação MUST aparecer na visualização. Quando o texto-base usado na tentativa
  não é o atual (hash diferente), o comando MUST procurar no histórico do Git a versão do texto-base
  com o hash gravado e, achando, montar o prompt com ela e avisar que é uma versão antiga; não
  achando, nada MUST ser gravado, e a mensagem MUST dizer o hash usado e o atual (B4, decidida em
  2026-10-16). Em nenhum caso um prompt cujo hash não confere é gravado como "o que foi enviado".
- **FR-004**: O corpo gravado MUST ser o mesmo JSON que a geração envia (os mesmos campos e
  valores, com o prompt dentro dele) e MUST NOT conter a chave da API.
- **FR-005**: O arquivo gravado MUST conter só o que é enviado ao modelo: o corpo da requisição. A
  identificação (modelo, problema, cenário, número da tentativa ou "prévia") e o resultado das
  conferências (FR-003, FR-012, FR-013) aparecem no terminal. A resposta do modelo, crua ou
  resumida, MUST NOT aparecer em nenhum dos dois (B3, decidida em 2026-10-16).
- **FR-006**: Para uma combinação sem tentativa, o comando MUST gravar o pedido que a próxima
  geração enviaria e dizer no terminal que é uma prévia não enviada.
- **FR-007**: O `show-request` MUST gravar o corpo num arquivo indicado pelos autores, sem mostrar
  o pedido no terminal, e MUST conferir que nada do dataset se perdeu (FR-012); no terminal aparece
  só o resultado das conferências (B2, refinada no analyze em 2026-10-16). Um arquivo existente
  MUST NOT ser sobrescrito sem pedido explícito.
- **FR-008**: Antes de reconstruir um prompt, o comando MUST conferir o dataset contra o manifesto,
  como os demais comandos, e recusar se divergir.
- **FR-009**: Erros de uso (modelo, problema, cenário ou tentativa inexistentes) e combinação
  danificada MUST ter mensagens claras e códigos de saída coerentes com os dos demais comandos do
  módulo.
- **FR-011**: O dry-run da geração (`generate --dry-run`, dos três modelos) MUST poder gravar,
  numa pasta indicada pelos autores, um arquivo por combinação pendente com o corpo exato da
  requisição que seria enviada (o prompt inteiro vem dentro dele), e um resumo da conferência (FR-012, FR-013). Fora dessa pasta, o
  dry-run continua sem gravar nada e sem chamar nenhuma API; uma pasta que já tem arquivos MUST NOT
  ser sobrescrita sem pedido explícito.
- **FR-012**: Para cada pedido gravado (e para o `show-request`), o sistema MUST conferir que o
  enunciado (`enunciado.md`), o código de referência (`AC_ref.cpp`) e o exemplo (o primeiro teste
  público de `testes.json`) aparecem no prompt **idênticos** aos arquivos do dataset, conforme o
  cenário (caixa-preta: enunciado; caixa-branca: código; híbrido: os dois; o exemplo em todos), e
  listar as combinações em que algum trecho não aparece.
- **FR-013**: O sistema MUST marcar como aviso os pedidos cujo enunciado tem expoente perdido (uma
  potência de 10 escrita sem o expoente, como `105` ou `109` depois de `≤`, `<`, `·`), com o
  trecho encontrado; o aviso não impede nada, porque a perda vem do próprio dataset, que não é
  corrigido (metodologia, seção 3).
- **FR-010**: A documentação de uso do módulo (o README do módulo e a referência de comandos do
  README da raiz) MUST passar a descrever o comando.

### Key Entities *(include if feature involves data)*

- **Visualização de pedido**: o arquivo com o corpo da requisição (que traz o prompt completo) e,
  no terminal, o modelo, o problema, o cenário, o número da tentativa (ou "prévia") e o resultado
  das conferências (hash, fidelidade ao dataset, expoente perdido); nunca a resposta do modelo.
- **Tentativa gravada**: o registro que a geração já grava (hash do prompt e do texto-base,
  parâmetros enviados, resposta crua, uso, custo, interpretação); a feature só lê dele o que
  identifica o pedido enviado (hash do prompt e do texto-base, parâmetros, tentativa).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Para 100% das tentativas gravadas com o texto-base atual, o prompt reconstruído tem o
  mesmo hash que o gravado (verificado no piloto do Gemini e por teste).
- **SC-002**: Nenhum pedido de visualização faz chamada a uma API nem altera arquivos do experimento
  (verificado por teste).
- **SC-003**: Os autores obtêm a visualização de qualquer combinação com um único comando, sem
  conhecer o código (o tempo não é medido, decidido no analyze em 2026-10-16).
- **SC-004**: Uma divergência de hash nunca resulta num prompt gravado como "o que foi enviado"
  (verificado por teste com um texto-base alterado).
- **SC-005**: No dataset real, o dry-run com gravação mostra todos os prompts gravados fiéis ao
  dataset (600 de 600 num modelo cuja execução ainda não começou, como o GPT e o SLM do zero) e
  marca, entre os gravados, os enunciados com expoente perdido: os 71 da contagem de 2026-10-16
  quando todas as combinações estão pendentes; tudo sem nenhuma chamada a uma API. O Gemini é
  conferido num dry-run separado pelos autores.

## Assumptions

- **Usuários**: os dois autores, no contêiner do projeto; não há usuários externos.
- **Sem custo**: a feature nunca chama um modelo; serve inclusive para conferir pedidos antes de
  uma execução paga.
- **Nada muda no que é gravado**: a decisão A do autor (2026-10-16) foi reconstruir o prompt e
  conferir o hash, em vez de passar a gravar o texto inteiro em cada tentativa; por isso a feature
  funciona para tudo o que já foi gerado (inclusive o piloto do Gemini e as 600 suítes do SLM) e
  pode ser construída em paralelo à execução completa dos modelos comerciais.
- **Reaproveitamento**: o prompt e o corpo vêm das mesmas funções que a geração usa, para que a
  visualização nunca divirja do que é enviado.
- **Histórico do Git (B4)**: os textos-base são versionados, então uma versão antiga costuma estar
  no histórico. **Decidido no planejamento (2026-10-16, Milena; `plan.md` S1)**: o contêiner de
  extração e empacotamento passa a ver o histórico do repositório em modo somente leitura; o
  contêiner que roda código de terceiros continua sem ele. Onde o histórico não estiver disponível,
  a tentativa feita com um texto-base antigo é recusada com os dois hashes, nunca gravada com o
  texto atual.
- **O dry-run passa a poder gravar arquivos** (FR-011): só na pasta pedida explicitamente, nunca em
  `data/suites/`; isso estende o dry-run da geração dos modelos comerciais, que até aqui não
  gravava nada, e a mudança é propagada à documentação daquele módulo no planejamento.
- **Fora do escopo**: editar ou reenviar pedidos; comparar visualmente dois pedidos; visualizar as
  suítes ou as métricas.
