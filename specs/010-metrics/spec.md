# Feature Specification: Métricas de avaliação

**Feature Branch**: `010-metrics` (sem branch própria; trabalho direto na `main`)

**Created**: 2026-11-09

**Status**: Implemented (`compute` executado em 2026-11-09; carimbos de comando em revisão commitada pendentes, ver tasks T030–T031)

**Input**: User description: "do modulo de metricas" — o módulo que calcula as métricas do TCC a
partir dos resultados da avaliação (feature 009), segundo a proposta consolidada em
`docs/metricas-referencia.md` (consolidado na metodologia, seção 5), confirmada pelos autores em 2026-11-04 **sem C.5
(complementaridade) e sem C.6 (IIC sobre mutantes)**.

## Contexto

A avaliação terminou em 2026-11-06: 5 conjuntos (`slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`)
× 200 problemas × 3 cenários, empacotados com manifesto. Cada combinação registra o AC teste a
teste, a detecção de cada um dos 100 WAs e 100 mutantes por dois oráculos (declarado pela IA e
corrigido pelo `AC_ref`) e os conjuntos exatos de detectados. As tentativas de geração registram
custo (US$, só os comerciais), *tokens* e tempo de cada pedido.

Esta feature transforma esses dados nas métricas que respondem às perguntas da pesquisa (Q1 a Q5 de
`docs/metricas-referencia.md` (consolidado na metodologia, seção 5), seção A), com a camada estatística que sustenta qualquer afirmação
"X é melhor que Y", e incorpora a proposta confirmada à seção 5 de `docs/metodologia-referencia.md`.
O dashboard (feature 011) passa a exibir essas tabelas sem recalcular nada.

## Clarifications

### Session 2026-11-09

- Q: Por que a predição direta foi descartada no modelo local? → A: As saídas previstas erravam
  muito, e o modelo é treinado para escrever código, não para prever saídas (Milena; FR-015).
- Q: Quem gera as figuras do TCC, e com filtro? → A: Este módulo, por funções com filtros
  (macrocategoria, status, modelos, cenários); geradas por comando e exibidas no dashboard com
  download PNG/PDF; filtros e fonte no rodapé e no nome do arquivo (Milena; FR-017, US6).
- Q: As figuras do dashboard eram imagens estáticas; pode plotar os gráficos no painel? → A: Sim:
  gráficos interativos com os filtros, exportáveis como foto pelo menu de cada gráfico; o PDF do
  texto continua sendo o do comando (Milena, 2026-11-09; FR-017).
- Q: As cores estão ruins no tema escuro (texto preto sobre fundo preto) e alguns gráficos estão
  pequenos; o que fazer? → A: paleta e tons de texto por tema, um painel por cenário em largura
  cheia, barras finas e espaçadas, custo em US$ por 1.000 WAs (Milena, 2026-11-09; FR-017).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Métricas primárias por modelo e cenário (Priority: P1)

Um autor gera, para cada conjunto × cenário, as quatro métricas já aprovadas pela banca e a
companheira delas: **TDF** (Taxa de Detecção de Falhas reais), **MS** (Mutation Score), **TFP**
(Taxa de Falsos Positivos), **IIC** (Índice de Influência do Contexto, nas duas direções) e **TC**
(Taxa de Cobertura).

**Why this priority**: são as métricas do desenho aprovado (Q1 a Q4); sem elas não há resultado.

**Independent Test**: para a avaliação de exemplo de um problema, cada métrica confere com a conta
feita à mão a partir dos arquivos de resultado.

**Acceptance Scenarios**:

1. **Given** a avaliação completa, **When** as métricas são geradas, **Then** há TDF, MS, TFP, TC e
   os dois IIC para cada conjunto × cenário (o IIC é por conjunto, comparando os cenários).
2. **Given** uma combinação `discarded_manual` (Claude), **When** a TDF e o MS são calculados,
   **Then** ela conta como 0% nos 200 problemas; **When** a TFP é calculada, **Then** o valor
   oficial usa N = 200 e vem acompanhado da contagem de combinações sem suíte e da TFP entre as
   combinações com suíte.
3. **Given** um problema em que a caixa-preta não detecta nenhum WA, **When** o IIC é calculado,
   **Then** o IIC oficial (agregado nos 200 problemas) é definido, e a visão por problema exclui
   esse problema e diz quantos foram excluídos.

---

### User Story 2 - Oráculo corrigido e causas do falso positivo (Priority: P1)

Um autor gera **TDF\*** e **MS\*** (as mesmas métricas pelo oráculo corrigido), a diferença
**Δ_oráculo** = TDF − TDF\* (e MS − MS\*), e a **TFP por teste e por causa**: o teste reprova o AC
porque a IA errou a saída esperada (`oráculo`) ou porque a entrada faz o próprio AC falhar
(`entrada_inválida`).

**Why this priority**: é o que torna comparáveis o modelo local (oráculo por execução) e os
comerciais (oráculo por predição), a limitação mais séria do desenho (prioridade máxima da
proposta).

**Independent Test**: num conjunto em que o AC é sempre aprovado, TDF = TDF\* e MS = MS\*; num em
que o AC é reprovado por saída diferente, Δ_oráculo > 0 e a causa é `oráculo`.

**Acceptance Scenarios**:

1. **Given** a avaliação completa, **When** gerada, **Then** cada conjunto × cenário tem TDF\*, MS\*,
   os dois Δ_oráculo e a TFP por teste com a contagem por causa.

---

### User Story 3 - Testes estatísticos e cortes (Priority: P1)

Um autor obtém, para cada comparação da matriz de rastreabilidade, se a diferença é estatisticamente
significativa e de que tamanho: cenários entre si (dentro de cada modelo) e modelos entre si (dentro
de cada cenário), pareados pelos mesmos 200 problemas, com correção para múltiplas comparações. E
recorta qualquer métrica por macrocategoria, por status da suíte e pelo conjunto da 1ª tentativa.

**Why this priority**: sem ela, "X teve TDF maior" é só descrição da amostra; nenhuma afirmação do
texto se sustenta.

**Independent Test**: para dados sintéticos com diferença conhecida (e sem diferença), os testes
indicam significância e tamanho de efeito coerentes com o construído.

**Acceptance Scenarios**:

1. **Given** três cenários de um modelo, **When** comparados, **Then** há o teste global para mais
   de dois grupos pareados e, se significativo, as comparações par a par com p-valor corrigido e
   tamanho de efeito.
2. **Given** a TFP (binária por problema), **When** dois grupos pareados são comparados, **Then** o
   teste é o adequado a dados binários pareados.
3. **Given** o corte por macrocategoria, **When** pedido, **Then** cada métrica é recalculada só
   sobre os problemas daquela categoria, com o número de problemas ao lado.

---

### User Story 4 - Custo e densidade (Priority: P2)

Um autor gera o **CPD** (custo por detecção, em US$, por WA e por mutante detectado) dos três
comerciais, os *tokens* e o tempo totais de geração dos quatro modelos (o modelo local sem
conversão para US$) e a **densidade de detecção** (TDF dividida pelo tamanho médio das suítes).

**Why this priority**: responde à parte de custo-benefício da Q5 e fecha a pendência 26 (tamanho da
suíte como variável de confusão); complementa, não muda, a comparação principal.

**Independent Test**: o custo total de cada modelo bate com o do relatório de geração do modelo.

**Acceptance Scenarios**:

1. **Given** o modelo local, **When** o custo é exibido, **Then** aparecem só *tokens* e tempo, nunca
   um valor em US$.

---

### User Story 5 - Tabelas versionadas, metodologia e dashboard (Priority: P2)

As métricas ficam em tabelas versionadas com manifesto (o resultado publicado do TCC), conferidas
pela verificação de integridade; a seção 5 da metodologia passa a conter a proposta confirmada; o
dashboard mostra as tabelas na página de métricas.

**Why this priority**: torna os números reproduzíveis e citáveis; liga o painel já pronto.

**Independent Test**: gerar duas vezes dá os mesmos arquivos (mesmo hash); o dashboard mostra os
mesmos valores das tabelas.

**Acceptance Scenarios**:

1. **Given** as tabelas geradas, **When** o dashboard abre a página de métricas, **Then** exibe os
   valores das tabelas, sem recalcular nenhum.

---

### User Story 6 - Figuras do TCC (Priority: P3)

Um autor gera os gráficos do capítulo de resultados (por exemplo, TDF por modelo e cenário, TDF ×
TDF\*, a distribuição do IIC por problema, a TFP por causa) por um comando, com ou sem filtros, ou
os explora na página de métricas do dashboard, filtrando e baixando em PNG ou PDF.

**Why this priority**: o texto precisa de figuras que batam sempre com as tabelas; depende das
métricas (US1 a US4) existirem.

**Independent Test**: a figura baixada do dashboard com um filtro é idêntica à gerada pelo comando
com o mesmo filtro, e o rodapé diz o filtro e a fonte.

**Acceptance Scenarios**:

1. **Given** o filtro macrocategoria = `matematica` no dashboard, **When** a figura é baixada,
   **Then** o nome do arquivo e o rodapé dizem o filtro, e o comando com o mesmo filtro gera o mesmo
   arquivo.
2. **Given** um pedido de figura por um problema só, **When** feito, **Then** é recusado (a página
   Combinação é o lugar de olhar um problema).

### Edge Cases

- **Combinação sem suíte** (3 do Claude; 53 da 1ª tentativa do SLM): 0% em TDF/MS, fora do
  numerador da TFP oficial, contada na TC e na nota que acompanha a TFP.
- **Denominador zero no IIC por problema**: o problema sai só da visão distribucional, com a
  contagem de excluídos; o IIC agregado nunca fica indefinido na prática.
- **IIC acima de 100%**: possível e correto (o teto não existe); documentado ao reportar.
- **Teste excluído do oráculo corrigido** (AC com erro de execução): não entra em TDF\*/MS\*; é a
  causa `entrada_inválida` da TFP por teste.
- **Teste estatístico sem variação** (todos os pares iguais): reportado como "sem diferença", sem
  erro.
- **Avaliação incompleta ou divergente do manifesto**: as métricas não são geradas.

## Requirements *(mandatory)*

### Functional Requirements

**Entradas**

- **FR-001**: O módulo MUST ler só os resultados da avaliação (os 5 pacotes descompactados), os
  metadados do dataset (macrocategoria), o tamanho das suítes e o custo/*tokens*/tempo gravados nas
  tentativas de geração; MUST NOT executar código de terceiros nem chamar IA.
- **FR-002**: Antes de calcular, MUST exigir a verificação de consistência completa (com hashes)
  das camadas lidas; falha = nada calculado.

**Métricas primárias (seção B da proposta)**

- **FR-003**: TDF = (WAs detectados ÷ 100) × 100, média nos 200 problemas; combinação sem suíte
  conta 0%. MS = mutantes detectados ÷ (100 − equivalentes), equivalentes = 0, média nos problemas
  com mutantes completos (os 200).
  **Emenda de 2026-11-09 (Milena)**: ao lado da TDF e do MS, a tabela de métricas MUST trazer as
  contagens — WAs e mutantes mortos, pelo oráculo declarado e pelo corrigido, e o total de cada —,
  em que cada alvo conta uma vez (morto se algum teste da suíte o reprovou); com 100 de cada por
  problema, TDF = WAs mortos ÷ total × 100.
- **FR-004**: TFP = (problemas com o AC reprovado ÷ 200) × 100, sempre acompanhada do número de
  combinações sem suíte do conjunto × cenário e da TFP entre as combinações com suíte (visão
  secundária).
- **FR-005**: IIC_cod = (|D(H) \ D(R)| − |D(R) \ D(H)|) ÷ |D(R)| × 100 e IIC_req = (|D(H) \ D(C)| −
  |D(C) \ D(H)|) ÷ |D(C)| × 100, com D(R), D(C), D(H) = a união, nos 200 problemas, dos pares
  (problema, WA) detectados em caixa-preta, caixa-branca e híbrido (forma agregada, oficial). Junto,
  a visão por problema: mediana, intervalo interquartil e proporção de IIC positivo/negativo/zero,
  excluindo e contando os problemas com denominador zero.
- **FR-006**: TC = (combinações com suíte ÷ 200) × 100, reportada ao lado de TDF/MS/TFP sempre que
  menor que 100%.

**Complementares (seção C, sem C.5 e C.6)**

- **FR-007**: TDF\* e MS\* pelo oráculo corrigido (mesmas regras de FR-003) e Δ_oráculo = TDF − TDF\*
  e MS − MS\*.
- **FR-008**: TFP por teste = testes que reprovam o AC ÷ total de testes das suítes, com cada teste
  reprovado classificado como `oráculo` (saída diferente) ou `entrada_inválida` (erro de execução
  do AC).
- **FR-009**: CPD = custo em US$ do conjunto × cenário ÷ WAs detectados (e ÷ mutantes detectados),
  só para os comerciais, com o custo de todos os pedidos (inclusive repetidos e barrados); para os
  quatro modelos, *tokens* e tempo totais; o modelo local nunca convertido para US$.
- **FR-010**: Densidade = TDF ÷ tamanho médio das suítes do conjunto × cenário (combinações com
  suíte).

**Estatística (seção D)**

- **FR-011**: Comparações pareadas pelos 200 problemas: mais de dois grupos (os 3 cenários de um
  modelo; os 4 modelos de um cenário) com teste de Friedman; pares com Wilcoxon pareado; TFP
  (binária por problema) com McNemar; tamanho de efeito A12 de Vargha-Delaney (e o delta de Cliff
  equivalente) sempre que uma diferença for significativa; correção de Holm-Bonferroni nas
  comparações par a par; nível de significância 0,05. Para a TFP (binária), só comparações par a
  par com McNemar exato e Holm, sem teste global (o Friedman não serve a dado binário). Nos testes
  pareados, uma combinação sem suíte entra com o valor da regra de FR-003/FR-004 (0% em TDF e MS;
  AC não reprovado na TFP), e a TC é reportada ao lado.

**Cortes (seção E)**

- **FR-012**: Toda métrica MUST poder ser recalculada por macrocategoria e por status da suíte, com
  o número de problemas (ou combinações) de cada corte; o conjunto `slm-attempt1` é tratado como um
  modelo a mais nas mesmas tabelas (a comparação "uma chamada contra uma").

**Saída e documentação**

- **FR-013**: As métricas MUST ser gravadas em tabelas com esquema versionado, num lugar fixo lido
  pelo dashboard; geradas de forma determinística (mesmas entradas → mesmos arquivos).
- **FR-014**: O resultado final MUST ser empacotado com manifesto de hashes, com verificação de
  integridade (`verify`, do zip e da pasta). Não ganha camada no `cli check`: o módulo não produz
  uma pasta por problema, que é o critério da constitution para uma camada nova.
- **FR-015**: A seção 5 de `docs/metodologia-referencia.md` MUST passar a conter a proposta
  confirmada (5.1–5.4 mantidas, mais as complementares, a estatística e os cortes), fechando as
  pendências 3 e 26; a pergunta Q5 entra na seção 0; e a limitação "oráculo por execução × por
  predição" entra na seção de limitações, com o motivo por que a predição direta foi descartada no
  modelo local: as saídas que ele previa sem executar erravam muito, e o modelo (Qwen2.5-Coder) é
  treinado para escrever código, não para prever a saída de um programa; por isso o oráculo dele é
  a execução da solução que ele escreve (decisão dos autores, registrada em 2026-11-09; a taxa de
  acerto medida, se recuperada, entra junto).
- **FR-016**: A página de métricas do dashboard MUST exibir as tabelas geradas, sem recalcular.
- **FR-017**: As figuras do TCC MUST ser desenhadas por funções deste módulo, a partir das tabelas
  de métricas, com filtros por macrocategoria, status da suíte, modelos (conjuntos) e cenários (nunca
  por um problema só). Um comando gera as figuras em PNG e PDF, com os mesmos filtros; a página de
  métricas do dashboard redesenha a figura pela mesma função com os filtros escolhidos e oferece o
  download em PNG e PDF. Cada figura traz no rodapé e no nome do arquivo os filtros aplicados e a
  fonte (as tabelas e a revisão), de modo que qualquer figura baixada se refaz pelo comando.
  **Emenda de 2026-11-09 (Milena)**: no dashboard, os gráficos são **interativos** (valor ao passar
  o mouse e escrito em cada barra), desenhados com os dados que este módulo devolve para cada figura
  (as mesmas funções das tabelas), filtrados pelos filtros da barra lateral do painel (que valem
  também para um subconjunto de problemas, com pelo menos 2), com o filtro e a fonte no subtítulo; cada gráfico
  se salva como foto (PNG ou SVG) pelo seu menu, e o botão "PDF para o texto" baixa a versão do
  comando, idêntica à de `python -m metrics figures` com o mesmo filtro.
  **Emenda de 2026-11-09 (Milena — legibilidade)**: os gráficos MUST seguir o tema (claro ou
  escuro) do painel, com uma paleta categórica validada por tema (a cor segue a série) e textos em
  tons de tinta, nunca na cor da série; figuras com muitas barras têm um painel por cenário; os
  valores escritos não se sobrepõem; o IIC omite os pontos extremos (ficam na tabela); a TFP por
  causa escreve só o total; o custo por detecção é mostrado em US$ por 1.000 WAs detectados.
  **Emenda de 2026-11-09 (Milena — download igual à tela)**: a figura baixada MUST ser o gráfico
  mostrado: os botões PNG, SVG e PDF do painel e o comando exportam o mesmo gráfico (o comando no
  tema claro, o painel no tema em uso); PNG e SVG são iguais byte a byte a cada execução e são os
  formatos do pacote; o PDF tem o mesmo desenho, mas não é empacotado.

### Key Entities

- **Linha por problema**: conjunto × cenário × problema, com detecção (declarada e corrigida), AC
  aprovado, tamanho da suíte, macrocategoria e status; base de todas as médias e dos testes pareados.
- **Tabela de métricas**: conjunto × cenário (× corte), com TDF, MS, WAs e mutantes mortos (e o total), TFP, TC, TDF\*, MS\*,
  Δ_oráculo, TFP por teste e por causa, CPD, *tokens*, tempo e densidade.
- **Tabela de IIC**: por conjunto, IIC_cod e IIC_req agregados e a visão por problema.
- **Tabela estatística**: comparação, métrica, teste, estatística, p-valor (bruto e corrigido),
  tamanho de efeito e o veredito.
- **Pacote de métricas**: as tabelas com o manifesto.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: As 5 métricas primárias, as 4 complementares e as comparações estatísticas existem
  para os 5 conjuntos × 3 cenários.
- **SC-002**: Para uma amostra de 3 combinações conferidas à mão, TDF, MS, TFP, TDF\* e MS\* batem
  com a conta manual; o IIC de um conjunto bate com a conta de conjuntos feita à mão.
- **SC-003**: As somas de detectados usadas batem 100% com os relatórios da avaliação; o custo
  total de cada comercial bate com o relatório de geração dele.
- **SC-004**: Gerar duas vezes produz arquivos idênticos.
- **SC-005**: Todo número citado no texto do TCC sobre as métricas sai destas tabelas.

## Assumptions

- A proposta de `docs/metricas-referencia.md` (consolidado na metodologia, seção 5) foi confirmada pelos autores em 2026-11-04, sem C.5 e
  C.6; depois de incorporada à metodologia, aquele arquivo é removido ou arquivado com o ok dos
  autores.
- O modelo local é comparado pela suíte final (`slm`); `slm-attempt1` é a leitura complementar.
- Tamanho de efeito: A12 como principal, o delta de Cliff ao lado (δ = 2·A12 − 1).
- As tabelas são pequenas (centenas de linhas); são versionadas como os outros resultados finais.
- Regra de uso, não de código (SC-005): o texto do TCC cita só números destas tabelas; o README
  do módulo diz isso.
- O dashboard já espera as tabelas num lugar fixo (`data/metrics/`); o formato definido aqui é o que
  ele passa a ler.

## Divergências e Decisões sobre a Metodologia

- **D1 — Proposta sem C.5 e C.6 (decidido pelos autores em 2026-11-04)**: a seção 5 passa a ter as
  complementares C.1–C.4; a complementaridade entre modelos e o IIC sobre mutantes ficam fora.
- **D2 — TFP com N = 200 e visão com suíte (decidido em 2026-11-04)**: a combinação sem suíte não é
  falso positivo; a TFP oficial mantém N = 200, com a contagem de sem suíte e a TFP entre as com
  suíte ao lado.
- **D3 — IIC agregado (decidido em 2026-11-04)**: os conjuntos de detectados são a união nos 200
  problemas; a visão por problema é diagnóstico, com os excluídos contados.
- **D4 — Camada estatística (decidido em 2026-11-04)**: Friedman, Wilcoxon pareado, McNemar exato,
  Holm-Bonferroni e A12, pareados pelos 200 problemas.
- **D5 — Figuras com filtros (decidido por Milena em 2026-11-09)**: desenhadas por este módulo,
  geradas por comando e exibidas no dashboard com download, com o filtro e a fonte no rodapé.
