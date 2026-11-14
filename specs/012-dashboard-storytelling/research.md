# Research: Painel que conta a história dos resultados

Decisões técnicas da feature 012. Nenhum "NEEDS CLARIFICATION" ficou em aberto: a única pergunta
da spec (FR-020) foi respondida em 2026-11-12 (opção A).

## R1 — Onde moram as contas: um módulo de narrativa dentro de `metrics`

- **Decision**: um módulo novo, `src/metrics/story.py`, em Python puro (sem Streamlit), que recebe
  as tabelas do módulo de métricas e o recorte, e devolve o placar, o vencedor de cada critério, o
  título-conclusão de cada seção e os cartões do guia de escolha. O painel e o comando de figuras
  chamam as mesmas funções.
- **Rationale**: FR-017 proíbe fórmula de métrica no painel, e FR-020 exige que as figuras novas do
  comando sejam as da tela. Pondo a lógica em `metrics`, as duas saídas partem do mesmo código, como
  já acontece com `metrics.figures` e `metrics.charts` (feature 010, emenda de 2026-11-09).
- **Alternatives considered**: lógica dentro de `src/dashboard/` (o comando de figuras não poderia
  usá-la sem importar o painel); uma tabela pré-calculada nova em `data/metrics/` (não responde a
  filtros arbitrários).

## R2 — O corte por rating

- **Decision**: `per_problem.csv` ganha a coluna `rating` (o `cf_rating` do `metadata.json` do
  problema, lido junto com a macrocategoria em `metrics.sources`); `metrics.cuts.apply` ganha o
  argumento `ratings`; o comando `figures` ganha `--rating` (repetível); a tabela do painel
  (`dashboard.data`) ganha a mesma coluna e o filtro. `metrics compute` é rodado de novo e
  `data/metrics.zip` reempacotado.
- **Rationale**: a coluna fica junto da macrocategoria, que tem o mesmo papel; os cortes do comando e
  do painel continuam sendo uma função só. Os valores de `metrics.csv`, `iic.csv`, `stats.csv`,
  `cost.csv` e `detected_wa.csv` não mudam (só o `per_problem.csv` ganha uma coluna); o teste de
  regressão confere isso antes do reempacotamento.
- **Medido (2026-11-12, T007)**: `metrics compute` sobre os dados reais (32 s): `metrics.csv`,
  `iic.csv`, `stats.csv`, `cost.csv` e `detected_wa.csv` com o mesmo SHA-256 de antes; o
  `per_problem.csv` só ganhou a coluna `rating` (3.000 linhas idênticas fora dela, nenhum rating
  vazio); `data/metrics.zip` reempacotado e `verify --extracted` OK.
- **Alternatives considered**: ler o rating do dataset na hora do corte (o comando de figuras e o
  painel teriam de ter o dataset descompactado só para isso; a cópia pública já o tem, mas o comando
  não precisa dele hoje); acrescentar o corte por rating em `metrics.csv` como os de macrocategoria e
  status (7 cortes a mais na tabela oficial sem pedido dos autores).

## R3 — Testes estatísticos e recortes

- **Decision**: nenhum teste novo. Para dizer se o 1º e o 2º colocados de um critério diferem, o
  painel procura o par em `stats.csv`: família `models` (os 4 modelos, por cenário) ou `attempt1`
  (a 1ª tentativa do modelo local contra cada conjunto, por cenário), métrica `TDF_star`, `MS_star`
  ou `TFP`, coluna `significant` (p corrigido por Holm). O resultado tem três estados: **diferem**,
  **empate estatístico**, **não testado**. É "não testado" quando: o recorte não é o completo (há
  filtro de problema, macrocategoria, rating ou status), o critério não tem teste (Δ_oráculo, TC,
  custo), ou o valor é a média de mais de um cenário (o placar).
- **Rationale**: FR-005 e FR-014; os testes da feature 010 são pareados pelos 200 problemas, e
  refazê-los num recorte seria um número que não está no texto do TCC.
- **Alternatives considered**: rodar Wilcoxon/McNemar no recorte (cria resultado estatístico fora
  do módulo de métricas e sem a correção de Holm do conjunto de comparações).

## R4 — O valor de cada critério num recorte com vários cenários

- **Decision**: TDF\*, MS\*, TFP, Δ_oráculo e TC de um conjunto = a média dos valores de
  `metrics.primary.table` por cenário no recorte. Como cada cenário tem os mesmos problemas, é o
  mesmo que somar sobre os cenários. Custo por 1.000 WAs = 1.000 × (soma do custo dos cenários) ÷
  (soma dos WAs mortos pelo gabarito do AC), de `cost.csv` e `metrics.primary.table`. Com um cenário
  só no filtro, o valor é o daquele cenário.
- **Rationale**: o roteiro usa a média dos 3 cenários (`docs/roteiro-painel.md` (consolidado na metodologia, seção do painel), seção 3.0) e os
  valores conferem: TDF\* do Gemini 90,1%, TFP do Claude 17,3%. O custo somado evita a média de
  razões.
- **Alternatives considered**: mostrar o placar só por cenário (três placares, abertura mais pesada
  para a banca).

## R5 — Títulos-conclusão por regra

- **Decision**: cada seção tem um modelo de frase com lacunas, preenchido pelo líder do recorte e
  pelo resultado de R3; por exemplo, `"{líder} encontra {valor} das falhas reais"` e, em empate,
  `"{líder} e {segundo} empatam em falhas reais encontradas ({v1} × {v2})"`. Os modelos ficam numa
  tabela de `metrics.story` (contrato em `contracts/narrative.md`), revisada pelos autores na
  implementação. Nenhum texto descreve um resultado que não venha do recorte.
- **Rationale**: FR-012 e SC-002; o título é a primeira coisa lida, e um título fixo ficaria errado
  ao filtrar.
- **Alternatives considered**: títulos fixos com o tema ("TDF por modelo"), que contrariam o
  princípio 1 da skill (*lead with insight*); texto gerado por modelo de linguagem (não
  determinístico).

## R6 — Gráficos novos (Altair, como os atuais)

- **Decision**: os gráficos continuam em Altair, desenhados por `metrics.charts` e exportados por
  vl-convert (feature 010). Tipos novos: placar (grade de células com posição e valor), troca
  detecta × erra (dispersão com a região ideal sombreada), IIC divergente (barras a partir do zero),
  variação entre cenários (linhas ligando os 3 cenários), cartões do guia (grade de texto), roscas da
  página 1. Cor: o líder numa cor de destaque única e os demais num cinza neutro, nos dois temas; as
  categorias de status da página 1 usam a paleta validada já existente. Antes de desenhar, aplicar a
  skill `dataviz` do projeto às cores e marcas.
- **Rationale**: as figuras do comando e da tela são o mesmo desenho (FR-020); o destaque do líder
  dispensa uma paleta de 5 cores para os conjuntos.
- **Aplicado (2026-11-12, US1)**: a skill `dataviz` foi carregada e o validador rodado: as 8 cores
  categóricas validadas entram na ordem fixa (1–3 valem para todos os pares, nas roscas; 1–6 para
  pares vizinhos, na barra de status); o par divergente validado é azul ↔ vermelho com cinza no
  meio (o plano dizia azul/laranja); a ausência ("sem suíte") é cinza, não uma cor de categoria;
  como três cores do tema claro ficam abaixo de 3:1, todo gráfico da página 1 tem os valores
  escritos e uma tabela "ver os números".
- **Alternatives considered**: matplotlib (saiu do projeto em 2026-11-09); componentes Streamlit
  nativos (não exportam para o comando).

- **Revisão visual (2026-11-12, pedido de Milena: "visualmente ruim, não está clean")**, feita com
  capturas da página real nos temas claro e escuro: cada gráfico tinha um fundo próprio, diferente
  do da página (efeito de colcha de retalhos), título pequeno dentro do gráfico, uma caixa "ver os
  números" por gráfico, a barra de status espremida no navegador (no PNG estático estava certa), a
  rosca do gasto cortada e o gráfico de testes com o eixo no zero. Mudou: gráfico dentro de um
  cartão com borda, título-conclusão e denominador como texto da página, fundo transparente, a
  largura do cartão, eixos sem linhas de domínio, roscas com a legenda "nome · %" ao lado (nunca
  cortada), testes por suíte num gráfico de pontos com o eixo ajustado aos dados, uma única seção
  "Ver os números desta página", barra lateral com "Filtros" no topo e "Fonte dos dados"
  recolhida, rótulos amigáveis nos filtros. Achado na revisão: com o tema fixado na configuração,
  `st.context.theme` devolvia a preferência do navegador, e os gráficos saíam com as cores do outro
  tema; o painel passa a olhar primeiro `theme.base`.

## R7 — Páginas e navegação

- **Decision**: `st.navigation` com três páginas: `experiment` ("O experimento", padrão),
  `evaluation` ("A avaliação") e `metrics` ("As métricas"). A página 2 junta as visões atuais em duas
  abas (Comparações e Combinação), com os números da avaliação acima delas; os módulos
  `views/combination.py` e `views/compare.py` viram funções chamadas pela página nova, sem mudança de
  conteúdo. `views/overview.py` sai: os números de contexto vão para a página 1, e os da execução
  (avaliadas, AC aprovado e reprovado, detectados por oráculo, com o rótulo de prévia) para o topo da
  página 2. O seletor "Corte das tabelas" da página de métricas sai: as tabelas seguem a barra
  lateral (FR-003).
- **Rationale**: FR-001, FR-003, FR-009; abas não mudam o recorte (FR-006).
- **Alternatives considered**: manter quatro páginas com "Visão geral" (contradiz a ordem decidida).

## R8 — Desempenho

- **Decision**: as funções de `metrics.story` recebem as tabelas já lidas e guardadas
  (`st.cache_data`, como hoje) e o recorte como chave de cache. O IIC por recorte usa
  `metrics.iic.table` sobre o `detected_wa` cortado, a parte mais pesada (cerca de 490 mil linhas);
  medir na implementação contra SC-004 (página em menos de 10 s, filtro em menos de 5 s).
- **Rationale**: SC-004; a feature 011 já mediu leitura e filtro dentro do limite.

## R9 — Testes

- **Decision**: (a) `tests/metrics/test_story.py`: casos conhecidos sem filtro, conferindo SC-001
  contra os números do roteiro (TDF\* do Gemini 90,1%, TFP do Claude 17,3%, os empates da TFP e da
  TDF\* na caixa-branca), e uma verificação de que, em recortes de exemplo, o líder nomeado tem sempre
  o melhor valor (SC-002); (b) o corte por rating em `test_sources_cuts_gate.py`; (c) as figuras
  novas: mesmo arquivo a cada execução (PNG e SVG) e presença no pacote; (d) `tests/dashboard/
  test_pages.py`: as três páginas abrem com `AppTest`, com e sem filtro, e o recorte vazio ou de um
  problema só mostra o aviso; (e) nenhum arquivo muda depois de abrir as páginas (SC-006).
- **Rationale**: Princípio VI; os casos conhecidos são os números já conferidos em 2026-11-12.

## R10 — Revisão final pela skill de storytelling

- **Decision**: a última tarefa abre o painel real, captura as três páginas e aplica o checklist de
  10 itens da skill *visual-storytelling-design* (passo 4), mais a conferência de honestidade (o líder
  também aparece onde perde, empates como empates, limitações). O resultado vai para os autores, que
  decidem os ajustes. SC-003 (uma pessoa de fora em menos de 2 minutos) é conferido pelos autores.
- **Rationale**: pedido de Milena em 2026-11-12: a skill não fica só no roteiro.
