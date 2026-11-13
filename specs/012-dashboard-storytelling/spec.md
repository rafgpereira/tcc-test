# Feature Specification: Painel que conta a história dos resultados

**Feature Branch**: `012-dashboard-storytelling` (sem branch própria; trabalho direto na `main`)

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: refatorar o painel de resultados (feature 011) para contar a história
do TCC, conforme o roteiro aprovado em `docs/roteiro-painel.md`: três páginas (o experimento, a
avaliação, as métricas), filtros só na barra lateral e sempre aplicados (com o rating como filtro
novo), placar dos 5 conjuntos pelas métricas com gabarito do AC, seções por métrica com
título-conclusão calculado dos dados, troca detecta × erra, contexto (cenários e IIC), custo, e um
fechamento que mostra quem ganhou em cada critério para o leitor decidir. Só lê; nenhum número é
calculado fora do módulo de métricas. Público: a banca, ao vivo, e leitores pelo link público.

## Clarifications

### Session 2026-11-12

- Q: Os gráficos novos da página 3 também viram figuras do texto do TCC (comando de figuras e pacote
  de métricas)? → A: Sim, todos: placar, detecta × erra, IIC divergente e guia de escolha (Milena;
  FR-020). Emendado em 2026-11-13 (Milena): nenhuma figura no repositório nem no pacote; o comando
  de figuras fica opcional.
- Q: As 9 suítes `accepted_barred` (respostas sem raciocínio: 1 do Gemini, 8 do Claude) entram no
  placar e nas métricas? → A: Sim, ficam incluídas, como suítes que a ferramenta entregou; o placar
  diz quantas há no recorte e se algum 1º lugar mudaria sem elas (sem filtro: 9, nenhum muda)
  (Milena, 2026-11-12).
- Q: Que ordem e que página nova? → A: O experimento → As métricas → Rastreabilidade (nova, US5) → A avaliação (Milena, 2026-11-12).

## Contexto

O painel da feature 011 foi feito como ferramenta de **exploração** dos autores: quatro páginas
(Visão geral, Combinação, Comparações, Métricas) que mostram os dados corretamente, mas não dizem ao
leitor o que concluir. Com o experimento terminado (200 problemas, 4 IAs + a 1ª tentativa do modelo
local, 3 cenários, métricas calculadas), o painel passa a ser também o lugar onde a banca e qualquer
leitor do link público entendem os resultados.

O roteiro (`docs/roteiro-painel.md`, método de *visual storytelling*: contexto → avaliação →
resultados, título que é a conclusão, anotação do achado, denominador visível, honestidade sobre
quem perde) foi aprovado pelos autores em 2026-11-12 com estas decisões:

- ordem das páginas: **o experimento → a avaliação → as métricas**;
- filtros **só na barra lateral**, sempre aplicados a todas as páginas, e o **rating** como filtro
  novo;
- placar e seções de métricas pelo **gabarito do AC** (TDF\*, MS\*), para nenhuma posição vir de
  saída esperada errada;
- a **1ª tentativa do modelo local** entra no placar e nas seções, como quinto conjunto (uma chamada
  contra uma, como os comerciais);
- **sem conclusão única**: o painel mostra quem ganhou em cada critério, em cada cenário, e o leitor
  decide pela sua prioridade (gastar pouco, detectar mais, não reprovar o código correto…) e pelo que
  tem em mãos (caixa-preta, caixa-branca ou híbrido). A frase final do TCC fica em aberto e não é
  escrita no painel.

O que a feature 011 decidiu e não muda aqui: o painel só lê e nunca grava; as métricas e os testes
estatísticos vêm do módulo de métricas (feature 010) e o painel não refaz conta; há uso local e uma
cópia pública; o glossário e os nomes completos ao passar o mouse; o download das tabelas em CSV e dos
gráficos de métricas em PNG, SVG e PDF exatamente como aparecem na tela.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Entender o experimento antes dos resultados (Priority: P1)

Um leitor que não conhece o trabalho abre o painel e, na primeira página, entende o que foi feito: quantos
problemas, de que dificuldade (rating) e de que tipo (macrocategoria); que cada problema tem 100
falhas reais e 100 mutantes; quais IAs geraram testes, em quais cenários; quantas suítes e testes
foram gerados e com que status; quanto se gastou em cada IA comercial e quanto tempo o modelo local
usou.

**Why this priority**: sem o contexto, nenhum resultado faz sentido para quem chega pelo link ou para a
banca; é a página que abre o painel.

**Independent Test**: sem filtro, a página mostra 200 problemas, 20.000 WAs, 20.000 mutantes, 4 IAs ×
3 cenários, 2.400 suítes, 24.274 testes, US$ 19,35 (GPT 70%, Gemini 25%, Claude 5%), os ratings
(1000: 33, 1100: 24, 1200: 20, 1300: 22, 1400: 35, 1500: 31, 1600: 35) e as macrocategorias (lógica
direta 98, estrutural/otimização 61, matemática 41), iguais aos dos artefatos.

**Acceptance Scenarios**:

1. **Given** o painel recém-aberto, **When** a primeira página carrega, **Then** ela é "O experimento",
   com os números grandes no topo e os gráficos de rating, macrocategoria, suítes por IA e status,
   testes por suíte e gasto.
2. **Given** o filtro de macrocategoria `matematica`, **When** aplicado, **Then** todos os números e
   gráficos passam a contar só os 41 problemas dessa macrocategoria, e o topo da página diz o recorte
   ativo.
3. **Given** o gasto em dinheiro, **When** exibido, **Then** os três comerciais aparecem com valor e
   participação, e o modelo local aparece à parte, com o tempo de modelo e sem custo em dinheiro.

---

### User Story 2 - Ver quem ganhou em cada métrica (Priority: P1)

O leitor vai à página de métricas e vê, primeiro, um **placar**: a posição de cada um dos 5 conjuntos
(`slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`) em cada critério (falhas reais detectadas,
mutantes detectados, problemas com falso positivo, detecção vinda de gabarito errado, combinações com
suíte, custo por falha detectada), com o 1º lugar destacado. Depois, uma seção por métrica, cada uma
com um título que já é a conclusão, um gráfico com o ranking e as anotações do que importa.

**Why this priority**: é a resposta do TCC ("quem se saiu bem em quê"); é o que a banca vai ver.

**Independent Test**: sem filtro, o placar mostra Gemini 1º em TDF\* (90,1%) e MS\* (97,0%), Claude
1º em TFP (17,3%) e em custo (US$ 0,02 por 1.000 WAs), GPT 1º em Δ_oráculo (1,9 pontos), e a 1ª
tentativa do modelo local com 91,2% de combinações com suíte; os valores são os de `metrics.csv` e
`cost.csv` (média dos 3 cenários).

**Acceptance Scenarios**:

1. **Given** as métricas calculadas, **When** o leitor abre a página, **Then** o placar vem antes de
   qualquer seção, e cada célula mostra a posição e o valor.
2. **Given** uma seção de métrica, **When** exibida, **Then** o título diz o vencedor e o valor no
   recorte ("O Gemini encontra 90,1% das falhas reais…"), com o denominador ("de 20.000 WAs") e a
   indicação de empate estatístico quando o teste não separa os primeiros colocados.
3. **Given** a seção de falsos positivos, **When** exibida, **Then** há um gráfico que cruza detecção
   (TDF\*) e falso positivo (TFP) por conjunto e cenário, com a região ideal (muito detecta, pouco
   erra) marcada.
4. **Given** a seção de contexto, **When** exibida, **Then** ela mostra a variação de cada conjunto
   entre os 3 cenários e o IIC (ganho ou perda ao juntar requisito e código) em barras a partir do
   zero, com a escolha entre o gabarito da IA e o do AC.
5. **Given** a 1ª tentativa do modelo local, **When** aparece no placar, **Then** traz a nota de que
   as combinações sem suíte contam 0% de detecção.

---

### User Story 3 - Escolher a IA pela própria prioridade (Priority: P1)

No fim da página de métricas, o leitor encontra um **guia de escolha**: para cada critério (gastar
pouco, encontrar o máximo de falhas, não reprovar o código correto, confiar no gabarito, pegar
defeitos sintéticos, rodar sem custo de API), quem ganhou e o segundo colocado, no cenário que
corresponde ao que ele tem (caixa-preta, caixa-branca ou híbrido). Ele destaca a sua prioridade, e o
painel não declara um vencedor geral.

**Why this priority**: é a decisão dos autores sobre como o trabalho conclui: o leitor decide.

**Independent Test**: sem filtro, o critério "não reprovar o código correto" mostra, com "só o
código" (caixa-branca), o modelo local (16,5%) e o Claude (17,5%) em empate estatístico, e, com "os
dois" (híbrido), o GPT (15,0%) e o Claude (16,5%) em empate estatístico (McNemar com Holm, `stats.csv`);
"encontrar o máximo de falhas" (TDF\*) mostra o Gemini à frente com diferença significativa em "só o
requisito" e em "híbrido", e em empate estatístico com o Claude em "caixa-branca" (89,7% × 88,0%); "gastar pouco" mostra o Claude nos três cenários, como diferença não testada.

**Acceptance Scenarios**:

1. **Given** o cenário escolhido na barra lateral, **When** o guia é exibido, **Then** cada cartão
   mostra o vencedor daquele cenário, o valor e o segundo colocado.
2. **Given** um critério sem teste estatístico (custo, Δ_oráculo) ou um recorte filtrado, **When** o
   cartão é exibido, **Then** ele diz "diferença não testada" em vez de declarar vitória.
3. **Given** a prioridade escolhida pelo leitor, **When** ele a seleciona, **Then** o cartão
   correspondente é realçado, e os números não mudam.

---

### User Story 5 - Rastrear um número até o problema, a suíte e o teste (Priority: P1)

Depois das métricas, a página "Rastreabilidade" responde "de onde vem isso?". O leitor escolhe o que
rastrear e abre o item: (1) as combinações sem suíte, com o motivo (os 3 do Claude: `171_F`
caixa-preta e híbrido, recusa do filtro de segurança; `182_B` caixa-preta, corte no teto de saída) e
as tentativas de geração; (2) as 9 suítes "sem raciocínio" e as respostas barradas; (3) a origem da
suíte do modelo local (aceita, reserva, predita; revisão 1 ou 2); (4) qual teste reprovou um WA ou
mutante, com a entrada, as duas saídas esperadas e o código do alvo ao lado do AC; (5) o que um
teste derrubou; (6) por que o AC foi reprovado (os testes com a saída esperada errada ou a entrada
inválida); (7) as detecções que só existem por um dos gabaritos; (8) os WAs que nenhuma IA detectou;
(9) os WAs que só uma IA detectou; (10) os mutantes que sobreviveram a todas as suítes; (11) a ficha
de um problema (enunciado, AC, as 15 combinações).

**Why this priority**: pedido de Milena (2026-11-12) depois de ver a página das métricas: cada número
precisa poder ser conferido na fonte, na defesa e por quem lê o link.

**Independent Test**: sem filtro, "combinações sem suíte" lista 56 (53 da 1ª tentativa do modelo
local e 3 do Claude, com o motivo dos autores); "WAs que nenhuma IA detectou" lista 174 WAs em 67
problemas; as detecções de WAs só pelo gabarito da IA somam 17.876 e só pelo do AC 2.102 (os mesmos
números de `detected_wa.csv`).

**Acceptance Scenarios**:

1. **Given** os filtros da barra lateral, **When** o leitor escolhe um caso, **Then** a lista tem só
   os itens do recorte.
2. **Given** um WA escolhido numa combinação, **When** a ficha abre, **Then** ela mostra, para cada
   gabarito, o primeiro teste que o reprovou (ou que nenhum reprovou), a entrada, a saída esperada
   pela IA e a do AC, e o código do WA ao lado do AC.
3. **Given** a tabela de alvos da avaliação ausente (`results.csv`), **When** um caso que depende dela
   é escolhido, **Then** a página diz como obtê-la, sem erro.

---

### User Story 4 - Conferir uma combinação na avaliação (Priority: P2)

Entre o contexto e as métricas, o leitor (ou um autor) abre a página "A avaliação", que junta as
páginas atuais de Combinação e Comparações: no topo, os números da avaliação no recorte (combinações
avaliadas, AC aprovado e reprovado, detectados em cada oráculo); depois, as comparações entre oráculos
e entre o modelo local e os comerciais; e o detalhe teste a teste de uma combinação.

**Why this priority**: é a ponte entre o contexto e os números (de onde vêm as detecções) e é onde se
explica um número estranho; o conteúdo já existe e só muda de lugar.

**Independent Test**: o detalhe de `61_B`, `slm`, caixa-preta mostra o teste 3 reprovando o AC, 100
WAs detectados pelo gabarito da IA e 45 pelo do AC, como hoje.

**Acceptance Scenarios**:

1. **Given** os filtros da barra lateral, **When** o leitor escolhe uma combinação, **Then** as opções
   de modelo, problema e cenário são só as que cabem no recorte.
2. **Given** um recorte que deixa uma única combinação, **When** a página abre, **Then** o detalhe
   dela aparece direto.

### Edge Cases

- **Recorte com um só problema**: as páginas 1 e 2 funcionam; a página 3 diz que uma métrica precisa
  de pelo menos 2 problemas e aponta a página 2.
- **Recorte vazio**: cada página diz que nenhum problema atende aos filtros e mostra quais estão
  ativos.
- **Testes estatísticos num recorte**: só existem para os 200 problemas; em qualquer recorte por
  problema, macrocategoria, rating ou status, as notas de empate somem e aparece "sem teste
  estatístico para este recorte".
- **Custo num recorte**: o custo existe por modelo e cenário, não por problema; com filtro por
  problema, macrocategoria, rating ou status, a seção de custo mostra o valor de todos os problemas,
  com a nota "o custo não se divide por problema".
- **Filtro só de modelo ou de cenário**: o placar e as seções continuam com os conjuntos ou cenários
  escolhidos; o guia de escolha mostra só os cenários do filtro.
- **Métricas ainda não calculadas**: a página 3 diz isso e como gerá-las (como hoje); as páginas 1 e
  2 funcionam com a avaliação.
- **Avaliação ou pacotes não descompactados**: cada página diz o que falta descompactar.
- **Empate exato de valores**: o placar dá a mesma posição aos empatados.
- **Modelo sem custo (local)**: fica fora do ranking de custo, com a nota, nunca em último lugar.

## Requirements *(mandatory)*

### Functional Requirements

**Estrutura**

- **FR-001**: O painel MUST ter quatro páginas, nesta ordem: "O experimento" (a que abre), "As
  métricas", "Rastreabilidade" e "A avaliação" (emenda de 2026-11-12, Milena: antes eram três, com a
  avaliação no meio). A página "Visão geral" atual deixa de existir: os números dela vão para "O
  experimento" (contexto) e para o topo de "A avaliação" (resultado da execução).
- **FR-002**: Cada página MUST terminar com uma frase de passagem para a seguinte ("Cada suíte foi
  executada… veja como foi →"), e a ordem de leitura MUST ser contexto → métricas → rastreabilidade → avaliação.

**Filtros**

- **FR-003**: Os filtros MUST ficar só na barra lateral, iguais em todas as páginas: conjunto,
  cenário, macrocategoria, **rating** (novo, lido do problema), status da suíte e problema. Nenhuma
  página tem filtro próprio que mude o recorte.
- **FR-004**: Todo número, gráfico, título e denominador de todas as páginas MUST ser recalculado
  para o recorte dos filtros, e cada página MUST mostrar no topo o recorte ativo e quantos problemas
  ele tem.
- **FR-005**: O que não se divide por recorte MUST ser avisado, nunca escondido em silêncio: testes
  estatísticos (só os 200 problemas), custo (só por modelo e cenário) e métricas com um só problema.
- **FR-006**: Os controles que não mudam o recorte (a combinação a detalhar na página 2, a prioridade
  realçada no guia, o gabarito do IIC) MAY ficar na própria página.

**Página 1 — O experimento**

- **FR-007**: MUST mostrar, como números grandes: problemas, WAs e mutantes (com "100 + 100 por
  problema"), IAs × cenários, suítes, testes gerados e gasto em dinheiro.
- **FR-008**: MUST mostrar os ratings em barras (um valor por faixa), as macrocategorias em rosca,
  as suítes por IA divididas por status (com o total como denominador), os testes por suíte por IA e
  cenário, e o gasto dos comerciais em rosca com o total, com o modelo local à parte (tempo de modelo,
  sem custo em dinheiro).

**Página 2 — A avaliação**

- **FR-009**: MUST reunir o conteúdo atual das páginas Combinação e Comparações, sem perder nenhuma
  informação delas (detalhe teste a teste, código do alvo ao lado do `AC_ref`, oráculo declarado ×
  corrigido, modelo local × comerciais), com os números da avaliação no recorte no topo.

**Página 3 — As métricas**

- **FR-010**: MUST abrir com o placar: a posição e o valor de cada conjunto em TDF\*, MS\*, TFP,
  Δ_oráculo, TC e custo por 1.000 WAs detectados (média dos cenários do recorte), com o 1º lugar
  destacado, empates com a mesma posição e o modelo local fora do ranking de custo.
- **FR-011**: MUST ter uma seção por tema, nesta ordem: falhas reais (TDF e TDF\*), mutantes (MS e
  MS\*), falsos positivos (com o gráfico detecta × erra e a TFP por teste), contexto (variação entre
  cenários e IIC por oráculo) e custo-benefício.
- **FR-012**: O título de cada seção MUST ser uma conclusão gerada a partir dos dados do recorte (quem
  lidera e com que valor), por uma regra fixa e documentada; MUST NOT haver conclusão escrita à mão
  que fique errada quando o filtro muda.
- **FR-013**: Cada gráfico MUST mostrar o denominador, escrever o valor nos elementos, destacar o
  líder com uma cor única e os outros em tom neutro, e ter no máximo 3 anotações do achado.
- **FR-014**: Quando o teste estatístico existe (sem recorte), o painel MUST dizer se o 1º e o 2º
  colocados diferem significativamente; sem teste, MUST dizer que a diferença não foi testada.
- **FR-015**: A página MUST terminar com o guia de escolha: um cartão por critério (gastar pouco,
  encontrar o máximo de falhas, não reprovar o código correto, confiar no gabarito, pegar defeitos
  sintéticos, rodar sem custo de API), com o vencedor, o valor e o segundo colocado no cenário do
  recorte, com os cenários sempre nomeados caixa-preta, caixa-branca e híbrido (Milena, 2026-11-12), uma prioridade que o leitor realça, as limitações do experimento e **nenhum vencedor
  geral**.
- **FR-016**: As tabelas oficiais (métricas, IIC, estatística, custo) MUST continuar na página 3,
  depois do guia, com o download em CSV.

**Dados e integridade**

- **FR-017**: Todo número das páginas 1 e 3 MUST vir das tabelas do módulo de métricas, dos artefatos
  versionados ou das mesmas funções que o módulo de métricas usa para os seus cortes; o painel MUST
  NOT ter uma fórmula própria de métrica. O corte por rating MUST ser acrescentado ao módulo de
  métricas, para valer também no comando de figuras.
- **FR-018**: Sem filtro, os números exibidos MUST coincidir com os de `metrics.csv`, `iic.csv`,
  `stats.csv` e `cost.csv`.
- **FR-019**: O painel continua só de leitura (feature 011, FR-003), com o glossário e os nomes
  completos ao passar o mouse (FR-013 da 011), e funciona igual no uso local e na cópia pública.
- **FR-020**: Cada gráfico da página das métricas MUST ter "Como se calcula" (a fórmula, a mesma em
  palavras e a conta com os números do recorte); salvar o gráfico é pelo menu do próprio gráfico (PNG
  ou SVG), sem botão próprio. Nenhuma figura MUST ficar no repositório: o pacote de métricas tem só as
  tabelas e o `run.json`; o comando de figuras fica opcional e desenha com as mesmas funções do
  painel (emenda de 2026-11-13, Milena: antes, botões PNG, SVG e PDF e as figuras novas no pacote).
- **FR-021**: Abaixo do placar, a página MUST mostrar o placar por cenário: uma linha por IA e
  cenário, os mesmos 6 critérios e a posição comparando as IAs dentro do mesmo cenário, com o título
  dizendo em quantos critérios o 1º lugar muda com o cenário (Milena, 2026-11-13).

### Key Entities

- **Recorte**: a combinação de filtros ativos (conjuntos, cenários, macrocategorias, ratings,
  status, problemas) e quantos problemas ela tem.
- **Critério**: uma métrica com a direção do "melhor" (maior ou menor), o nome em linguagem de uso e
  se tem teste estatístico.
- **Placar**: para cada critério e conjunto, o valor no recorte e a posição.
- **Título-conclusão**: o texto gerado por uma regra a partir do líder e do valor de um critério no
  recorte.
- **Cartão do guia**: critério × cenário, com vencedor, valor, segundo colocado e o resultado do teste
  (diferem, empate, não testado).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Sem filtro, 100% dos números do placar, das seções e do guia coincidem com as tabelas do
  módulo de métricas (conferido por teste automático).
- **SC-002**: Com qualquer combinação de filtros, nenhum título ou cartão nomeia como líder um
  conjunto que não tem o melhor valor do recorte (conferido por teste automático em recortes de
  exemplo).
- **SC-003**: Uma pessoa que não conhece o experimento, usando só o painel, consegue dizer em menos
  de 2 minutos quem ganhou em cada critério no cenário "caixa-preta" (conferido pelos autores com
  ao menos uma pessoa de fora antes da defesa).
- **SC-004**: Com a avaliação completa, cada página abre em menos de 10 segundos e um filtro responde
  em menos de 5 segundos (o mesmo limite de filtro da feature 011).
- **SC-005**: Todo gráfico tem o denominador e o recorte visíveis; nenhuma rosca ou pizza tem mais de
  4 fatias (partes com mais categorias usam barras).
- **SC-006**: Nenhum arquivo do repositório ou de `data/` muda depois de usar o painel.

## Assumptions

- Público: a banca, na defesa ao vivo, e leitores do link público; a interface segue em português.
- A média dos 3 cenários é o valor do placar quando o recorte tem mais de um cenário; o detalhe por
  cenário fica nas seções.
- O rating vem do `metadata.json` de cada problema (`cf_rating`), já presente no dataset.
- As frases-conclusão seguem regras simples e fixas ("O {líder} {verbo} {valor}…"); o texto final de
  cada regra é revisado pelos autores na implementação.
- Testes estatísticos só existem para o corte completo (feature 010); a feature não cria testes
  novos para recortes.
- O conteúdo das páginas Combinação e Comparações não muda, só o lugar.
- A frase final do TCC não é escrita no painel.

## Divergências e Decisões sobre a Metodologia

- **D1 — Contar a história, sem conclusão única (Milena, 2026-11-12)**: o painel passa de ferramenta
  de exploração para apresentação dos resultados; mostra quem ganhou em cada critério e o leitor
  decide. Emenda a D1 da feature 011 só no papel do painel: os números continuam vindo do módulo de
  métricas.
- **D2 — Ordem das páginas e filtros únicos (Milena, 2026-11-12)**: o experimento → a avaliação → as
  métricas; filtros só na barra lateral, sempre aplicados; rating como filtro novo.
- **D3 — Gabarito do AC no placar (Milena, 2026-11-12)**: TDF\* e MS\*, não TDF e MS.
- **D4 — 1ª tentativa do modelo local no placar (Milena, 2026-11-12)**: como quinto conjunto, com a
  nota das combinações sem suíte.
