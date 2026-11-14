# Feature Specification: Dashboard de exploração dos resultados

**Feature Branch**: `011-results-dashboard` (sem branch própria; trabalho direto na `main`)

**Created**: 2026-11-04

**Status**: Implemented (páginas antigas superadas pela 012; medição de tempo e carimbo do `serve` pendentes, ver tasks T031–T033)

> **Nota (2026-11-14)**: as páginas e os filtros do painel passaram a ser definidos pela feature `012-dashboard-storytelling` (4 páginas: O experimento, As métricas, Rastreabilidade, A avaliação); o restante desta spec (só leitura, camada de dados, dados parciais) continua valendo. As páginas de visão geral, detalhe de uma combinação e comparação ficam fora da navegação, mantidas só porque os testes as exercitam.

**Input**: User description: "do dashboard" — o painel de exploração proposto na conversa de
2026-11-04: só leitura, sobre os resultados da avaliação (`data/evaluation/<conjunto>/problems/<id>/
<cenário>.json` e `results.csv`) e, quando existirem, sobre as tabelas do módulo de métricas, sem
recalcular métrica; funciona com o piloto em andamento; páginas de visão geral, oráculo declarado ×
corrigido, modelo local (final × 1ª tentativa × comerciais), detalhe de uma combinação e métricas
oficiais; camada de dados a partir da prévia usada no piloto (`data/scratch/pilot_view.py`).

## Contexto

A avaliação (feature 009) grava, por conjunto (`slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`),
problema e cenário, um JSON com o AC teste a teste e os 200 alvos julgados por dois oráculos, e um
`results.csv` consolidado. Na execução completa são 3.000 combinações e cerca de 600 mil linhas de
alvo: inviável de ler à mão. A conferência de 2026-11-04 (`1000_B`) já mostrou um achado que só
aparece cruzando os dados (com o AC reprovado, o oráculo declarado "pega" 100% dos WAs, contra 64% a
89% pelo corrigido), e a prévia em texto (`pilot_view.py`) não permite filtrar nem descer ao
detalhe com facilidade.

O dashboard é a ferramenta de **exploração** dos autores e do orientador: entender os resultados,
conferir casos estranhos e preparar a discussão. Ele não é fonte de números do TCC: as métricas
oficiais (TDF, MS, TFP, IIC, TC, TDF\*, MS\*, Δ_oráculo, custo por detecção, testes estatísticos)
são calculadas pelo módulo de métricas (feature 010), e as figuras do texto saem de lá.

## Clarifications

### Session 2026-11-04

- Q: Antes das métricas oficiais, mostrar porcentagens de detecção ou só contagens? → A: Porcentagens,
  rotuladas como prévia; quando a 010 existir, a página de métricas é a referência (Milena; FR-004).
- Q: Uso local ou publicado? → A: Só local, no navegador de quem roda; sem publicação (FR-011).
  Revisto em 2026-11-09: também uma cópia pública no Streamlit Community Cloud (FR-011, emenda).
- Q: Baixar tabelas e gráficos? → A: CSV das tabelas filtradas; as figuras do TCC só pelo módulo de
  métricas (FR-012).
- Q: Como trazer os problemas concluídos durante uma avaliação em andamento? → A: Lê ao abrir e
  guarda; um botão "recarregar dados" relê; a tela mostra quando os dados foram lidos e quantos
  problemas estão concluídos (FR-001a).
- Q: No detalhe de um alvo, mostrar o código dele ao lado do `AC_ref`? → A: Sim, lado a lado com as
  diferenças destacadas, lido dos arquivos do dataset e dos mutantes, para WAs e mutantes (FR-007a).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visão geral do que já foi avaliado (Priority: P1)

Um autor abre o dashboard durante o piloto ou depois da execução completa e vê, por conjunto ×
cenário: quantas combinações já foram avaliadas e quantas estão sem suíte, em quantas o AC foi
reprovado, quantos testes do AC deram saída diferente ou erro, quantos WAs e mutantes foram
detectados em cada oráculo e quantos testes ficaram instáveis. Pode filtrar por problema,
macrocategoria e status da suíte.

**Why this priority**: é o que responde "como está a avaliação" e substitui a prévia em texto; é o
uso mais frequente, desde o piloto.

**Independent Test**: com a avaliação parcial do piloto, os números da visão geral batem com os do
`python -m evaluation report` e da prévia `pilot_view.py` para os mesmos problemas.

**Acceptance Scenarios**:

1. **Given** uma avaliação em andamento com 3 dos 5 problemas do piloto concluídos, **When** o autor
   abre a visão geral, **Then** ela mostra só esses 3 problemas e diz quantos estão concluídos por
   conjunto, sem erro pelos que faltam.
2. **Given** o filtro de macrocategoria `matematica`, **When** aplicado, **Then** todos os números
   passam a considerar só os problemas dessa macrocategoria (lida do `metadata.json` do problema).
3. **Given** uma combinação sem suíte (`discarded_manual`), **When** a visão geral é exibida,
   **Then** ela aparece contada como "sem suíte" e fica fora das contagens de AC e de detecção.

---

### User Story 2 - Detalhe de uma combinação (Priority: P1)

O autor escolhe um conjunto, um problema e um cenário e vê, teste a teste: a entrada, a saída
esperada escrita na suíte, a saída real do AC, o veredito do AC (com erro e instabilidade, se
houver) e quantos WAs e mutantes cada teste detectou em cada oráculo. Vê também a lista dos alvos
detectados só pelo oráculo declarado, e pode abrir um alvo para ver em que teste e com que veredito
foi detectado em cada oráculo.

**Why this priority**: é o que explica um número estranho (por que o AC foi reprovado, de onde vem
a diferença entre os oráculos) e é a base da conferência manual do piloto.

**Independent Test**: para `1000_B`, Gemini, caixa-preta, o detalhe mostra os testes 4, 7 e 9 com
saída esperada diferente da real e 14 WAs detectados só pelo oráculo declarado, como a prévia.

**Acceptance Scenarios**:

1. **Given** uma combinação do modelo local cuja suíte vem da execução anterior do dataset, **When**
   o detalhe é aberto, **Then** a saída esperada é lida da pasta indicada pela origem da suíte
   gravada no resultado.
2. **Given** uma combinação de `slm-attempt1`, **When** o detalhe é aberto, **Then** a saída
   esperada é a da solução do modelo naquela tentativa.
3. **Given** uma saída longa (muitas linhas), **When** exibida, **Then** aparece abreviada na tabela
   e inteira ao expandir.

---

### User Story 3 - Oráculo declarado × corrigido e modelo local × comerciais (Priority: P2)

O autor compara, lado a lado, a detecção de WAs e de mutantes pelo oráculo declarado e pelo
corrigido, por conjunto e cenário, com destaque para as combinações em que o AC foi reprovado; e
compara o modelo local pela suíte final, pela 1ª tentativa e os três comerciais.

**Why this priority**: são as duas leituras novas que a avaliação permite (Δ_oráculo e comparação
de uma chamada contra uma); enriquecem a discussão, mas dependem da visão geral.

**Independent Test**: com os dados da conferência do `1000_B`, a página mostra a diferença
declarado × corrigido no Gemini e no SLM caixa-preta e nenhuma no GPT e no Claude.

**Acceptance Scenarios**:

1. **Given** combinações com e sem AC reprovado, **When** a página é aberta, **Then** as com AC
   reprovado ficam destacadas e a diferença entre os oráculos aparece por combinação.
2. **Given** um problema cuja suíte final do modelo local veio da 1ª tentativa, **When** comparados,
   **Then** `slm` e `slm-attempt1` mostram os mesmos valores para essa combinação.

---

### User Story 4 - Métricas oficiais (Priority: P3)

Quando o módulo de métricas tiver gerado as suas tabelas, o dashboard as mostra, com os mesmos
filtros: TDF, MS, TFP, IIC, TC, TDF\*, MS\*, Δ_oráculo, custo por detecção e os resultados dos testes
estatísticos, por modelo, cenário e macrocategoria.

**Why this priority**: depende da feature 010; enquanto ela não existir, a página diz que as
métricas ainda não foram calculadas.

**Independent Test**: com uma tabela de métricas de exemplo, os valores exibidos são exatamente os
da tabela, sem nenhuma conta refeita.

**Acceptance Scenarios**:

1. **Given** que as tabelas de métricas não existem, **When** a página é aberta, **Then** ela diz
   isso e como gerá-las, sem erro.

### Edge Cases

- **Nada avaliado ainda**: o dashboard abre e diz que não há resultado, com o comando para começar.
- **Problema em gravação** (`building/`): ignorado; só o que está concluído aparece.
- **Resultado que não valida contra o esquema da avaliação**: a combinação é apontada como
  inválida, e o resto continua visível.
- **Árvore de conferência ou piloto guardado** (`--output-dir`): o autor escolhe qual pasta de
  avaliação está olhando; a padrão é `data/evaluation`.
- **Pacotes descompactados** (Cenário B dos módulos): funciona igual, porque a estrutura de pastas é
  a mesma.
- **Dataset ou mutantes não descompactados**: o detalhe de um alvo mostra a detecção e avisa que o
  código não está disponível (FR-007a).
- **Volume da execução completa** (3.000 combinações): os números agregados são preparados uma vez
  ao abrir e reaproveitados ao filtrar.

## Requirements *(mandatory)*

### Functional Requirements

**Dados**

- **FR-001**: O dashboard MUST ler os resultados da avaliação de uma pasta escolhida (padrão
  `data/evaluation`), só das combinações concluídas, validando cada uma pelo esquema da avaliação.
- **FR-001a**: Os dados MUST ser lidos ao abrir o dashboard e guardados para os filtros; um
  botão "recarregar dados" MUST reler a pasta (pegando os problemas concluídos desde a última
  leitura), e a tela MUST mostrar a data e hora da última leitura e quantos problemas estão
  concluídos por conjunto. Não há releitura automática.
- **FR-002**: O dashboard MUST montar uma tabela com uma linha por conjunto × problema × cenário
  (a mesma da prévia do piloto), acrescida da macrocategoria do problema.
- **FR-003**: O dashboard MUST NOT gravar nada em `data/`, `manifests/` ou no repositório, e MUST
  NOT executar código de terceiros.
- **FR-004**: Antes de existirem as tabelas do módulo de métricas, o dashboard MUST mostrar as
  porcentagens de detecção (WAs e mutantes detectados ÷ total, em cada oráculo) **rotuladas como
  prévia** em todo lugar em que aparecem; quando as tabelas oficiais existirem, a página de métricas
  passa a ser a referência e a prévia continua rotulada como tal.
- **FR-005**: Quando existirem as tabelas do módulo de métricas, o dashboard MUST exibi-las sem
  recalcular nenhum valor. A exibição das colunas e dos gráficos dessas tabelas é ligada por uma tarefa da
  feature 010, quando o formato delas existir; até lá vale o aviso do FR-009.

**Páginas**

- **FR-006**: Visão geral (US1) por conjunto × cenário, com os filtros de problema, macrocategoria
  e status da suíte, e a contagem de problemas concluídos por conjunto.
- **FR-007**: Detalhe de uma combinação (US2): por teste, entrada, saída esperada, saída real do
  AC, veredito do AC (tipo de erro e instabilidade) e detecções por teste em cada oráculo; lista
  dos alvos detectados só pelo oráculo declarado; o detalhe de um alvo.
- **FR-007a**: Ao abrir um alvo (WA ou mutante), o dashboard MUST mostrar o código-fonte dele e o
  do `AC_ref` lado a lado, com as linhas diferentes destacadas, lidos de
  `data/dataset/problems/<id>/` e `data/mutants/problems/<id>/`; sem esses arquivos descompactados,
  mostra o aviso e o resto do detalhe continua.
- **FR-008**: Comparações (US3): declarado × corrigido por combinação, com destaque para AC
  reprovado; `slm` × `slm-attempt1` × comerciais.
- **FR-009**: Métricas oficiais (US4), com aviso quando ainda não calculadas.

**Uso**

- **FR-010**: O dashboard MUST ser aberto por um único comando documentado, no ambiente
  containerizado do projeto, e acessado pelo navegador da própria máquina.
- **FR-011**: O dashboard é de uso **local**: aberto por quem roda o comando, no navegador da
  própria máquina, sem publicação na internet nem controle de acesso; para mostrar a outra pessoa,
  compartilha-se a tela. Os dados não saem da máquina. **Emenda de 2026-11-09 (Milena)**: além do
  uso local, existe uma **cópia pública** no Streamlit Community Cloud (gratuito, até 2,7 GB de
  memória). Ela é o mesmo painel, só de leitura, sobre os 12 pacotes versionados (avaliação dos 5
  conjuntos, métricas, dataset, mutantes e suítes), descompactados em `data/` na primeira abertura
  do servidor; entrada `src/dashboard/public/streamlit_app.py`, dependências mínimas em
  `src/dashboard/public/requirements.txt` (versões do `uv.lock`). Ela é publicada pelos autores, na
  conta do GitHub com acesso ao repositório. O Hugging Face Spaces chegou a ser escolhido, mas um
  Space Docker exige plano pago para ser criado (documentação conferida em 2026-11-10).
- **FR-013**: Toda sigla (AC, WA, TLE, TDF…) e todo cabeçalho de coluna MUST mostrar o nome completo
  ao passar o mouse, e a barra lateral MUST ter um glossário com as siglas e os valores que aparecem
  nas células (conjuntos, cenários, status, vereditos, macrocategorias). Pedido de Milena em
  2026-11-05.
- **FR-012**: Cada tabela exibida (já filtrada) MUST poder ser baixada em CSV pelo navegador, sem
  gravar nada no repositório. **Emenda de 2026-11-09 (Milena)**: a página de métricas mostra as
  figuras oficiais, desenhadas pelas funções do módulo de métricas com os filtros escolhidos, e
  oferece o download delas em PNG e PDF, com o filtro e a fonte no rodapé e no nome do arquivo
  (feature 010, FR-017); nenhum outro gráfico do painel tem download. **Emenda de 2026-11-09
  (Milena)**: os botões são PNG, SVG e PDF e baixam o gráfico exatamente como aparece na tela, no
  tema em uso; as linhas das combinações com o AC reprovado (Comparações) são marcadas por um tom
  vermelho translúcido, legível nos dois temas.

### Key Entities

- **Combinação**: conjunto × problema × cenário, com a origem da suíte, o status, o AC e as
  contagens de detecção por oráculo (uma linha da tabela base).
- **Teste da suíte**: entrada, saída esperada, saída real do AC, veredito, erro, instabilidade.
- **Alvo**: um WA ou mutante, com a detecção em cada oráculo.
- **Problema**: identificador e macrocategoria.
- **Tabela de métricas**: as saídas do módulo de métricas (feature 010), quando existirem.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Os números da visão geral coincidem 100% com os do relatório da avaliação e da prévia
  do piloto para os mesmos dados.
- **SC-002**: Com a execução completa (3.000 combinações), o dashboard abre em menos de 1 minuto e
  um filtro responde em menos de 5 segundos.
- **SC-003**: Partindo da visão geral, o autor chega ao detalhe teste a teste de qualquer combinação
  em no máximo 3 escolhas (conjunto, problema, cenário).
- **SC-004**: Na conferência manual do piloto, os autores conseguem responder, só pelo dashboard,
  por que o AC foi reprovado em cada combinação reprovada.
- **SC-005**: Nenhum arquivo do repositório ou de `data/` muda depois de usar o dashboard.

## Assumptions

- Usuários: os dois autores e o orientador, que conhecem o experimento; não há controle de acesso.
- As métricas oficiais e as figuras do texto são responsabilidade do módulo de métricas; o dashboard
  é exploração.
- A interface é em português, como a documentação do experimento.
- O dashboard roda no mesmo ambiente containerizado do projeto, sem rede para fora além de servir a
  página para o navegador local; a escolha de biblioteca (a conversa sugeriu Streamlit) fica para o
  plano.
- O piloto em andamento é o primeiro uso; nada no dashboard depende da execução completa existir.

## Divergências e Decisões sobre a Metodologia

- **D1 — Ferramenta de exploração, não fonte de números (decidido em 2026-11-04)**: o dashboard só
  lê e exibe; as métricas oficiais e as figuras do TCC vêm do módulo de métricas (feature 010).
- **D2 — Prévia rotulada (decidido por Milena em 2026-11-04)**: antes das métricas oficiais, as
  porcentagens de detecção aparecem sempre como prévia (FR-004).
- **D3 — Uso só local (decidido por Milena em 2026-11-04)**: sem publicação nem controle de acesso;
  os dados não saem da máquina (FR-011). Emendada em 2026-11-09 (Milena): também há uma cópia
  pública no Streamlit Community Cloud (FR-011).
- **D4 — Download só de CSV (decidido por Milena em 2026-11-04)**: as tabelas filtradas podem ser
  baixadas; gráficos não, para não haver uma segunda fonte de figuras (FR-012).
