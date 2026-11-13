# Roteiro do painel: a história dos resultados

Rascunho para os autores validarem antes da spec. Método: skill *visual-storytelling-design*
(narrativa → estrutura → anotação → revisão). Todos os números vêm de `data/metrics/`
(`metrics.csv`, `stats.csv`, `cost.csv`, `iic.csv`) e dos relatórios em `manifests/`.

## 1. A narrativa

| Etapa do arco | Conteúdo |
|---|---|
| **Contexto** | 4 IAs geraram testes para 200 problemas do Codeforces, em 3 cenários de contexto; cada suíte foi executada contra 20.000 falhas reais (WAs) e 20.000 mutantes |
| **Pergunta** | Qual IA gera os melhores testes, e em quê? Detectar falhas, não errar o gabarito, custar pouco, aproveitar o contexto |
| **Evidência** | Uma seção por métrica, cada uma com um ranking dos modelos |
| **Conclusão** | **Nenhuma IA vence em tudo.** O Gemini detecta mais falhas, mas reprova o código correto em mais da metade dos problemas. Claude e GPT empatam estatisticamente em detecção e em falsos positivos, e o Claude custa cerca de 13× menos. O cenário de contexto muda pouco o resultado |

**Abertura** (achado surpreendente): *"A IA que mais encontra falhas é também a que mais erra o
gabarito."*

**Público**: a banca, na defesa ao vivo, e leitores pelo link público. Por isso a estrutura combina
dois modelos da skill: *Step-by-Step Arc* (contexto → avaliação → resultados, uma página por etapa)
e *Interactive Exploration* (tudo responde aos mesmos filtros).

## 2. A estrutura: páginas e seções

**Decidido (Milena, 2026-11-12)**: três páginas, nesta ordem, e **filtros num lugar só, sempre
aplicados**.

| Página | O que é | Vem de |
|---|---|---|
| **1. O experimento** (abre por padrão) | o contexto: problemas, falhas, IAs, suítes, testes, gasto | nova; absorve os números da "Visão geral" atual |
| **2. A avaliação** | como cada suíte se saiu, combinação por combinação | as páginas atuais **Combinação** e **Comparações**, juntas |
| **3. As métricas** | quem se saiu bem em cada métrica: placar, seções por métrica, troca detecta × erra, contexto, custo | a página **Métricas** atual, reorganizada como história, com as tabelas oficiais no fim |

### Filtros: um lugar só, sempre dinâmicos

- **Onde**: a barra lateral, a mesma em todas as páginas, e só ela; nenhuma página tem filtro próprio
  que contradiga a barra.
- **Quais**: modelo (conjunto), cenário, macrocategoria, rating (novo), status da suíte, problema.
- **Efeito**: todo número, gráfico e **título-conclusão** é recalculado para o recorte. O título vem
  de uma regra, não de texto fixo: por exemplo, "O {líder} encontra {x}% das falhas reais" com o
  líder e o valor do recorte. Um aviso no topo de cada página diz o recorte ativo ("filtros:
  macrocategoria = matemática · 41 problemas").
- **O que não muda com filtro, e por quê** (aparece como nota, nunca em silêncio):
  - **testes estatísticos** (`stats.csv`): só existem para os 200 problemas; num recorte, a nota de
    significância some e aparece "sem teste estatístico para este recorte";
  - **custo**: existe por modelo e cenário, não por problema; com filtro de macrocategoria, rating ou
    problema, a seção de custo mostra o valor total com a nota "custo não se divide por problema";
  - **métrica com um problema só**: não tem sentido (o módulo de métricas já recusa); a página 3 pede
    pelo menos 2, e a página 2 é o lugar de olhar um problema só.
- **Página 2 com filtros**: a escolha de uma combinação (modelo, problema, cenário) parte dos filtros
  da barra; se a barra deixa mais de uma opção, a página lista as que cabem no recorte.

Convenção em todas as seções: **"melhor" sempre com a mesma cor de destaque**, os outros modelos
em cinza; valor escrito na barra; denominador visível e recalculado ("de 4.100 WAs" num recorte de
41 problemas); nota de significância quando existe; fonte e recorte no rodapé.

---

### Página 1 — O experimento

- **Título**: "200 problemas, 40.000 falhas, 4 IAs, 2.400 suítes" (recalculado com os filtros).
- **Linha de números grandes** (KPI): problemas · WAs e mutantes (100 + 100 por problema) · IAs ×
  cenários · suítes · testes gerados (24.274 sem filtro) · gasto (US$ 19,35 sem filtro).
- **Ratings**: barras (7 faixas, 1000 a 1600: 33, 24, 20, 22, 35, 31, 35). Barras, não pizza: 7
  fatias de tamanho parecido não se comparam a olho.
- **Macrocategorias**: rosca (3 fatias): lógica direta 98, estrutural/otimização 61, matemática 41.
- **Suítes por IA**: barra 100% empilhada por status (aceita, reserva, prevista, barrada, sem suíte),
  com o denominador. Destaque: "todas as IAs entregaram suíte em ≥ 99,5% das combinações".
- **Testes por suíte**: pontos com a média por modelo e cenário (GPT ~8, SLM ~9–10, Claude ~11,
  Gemini ~12); total por modelo: SLM 5.815, GPT 4.817, Gemini 7.019, Claude 6.623. Anotação: "o
  Gemini escreve mais testes, o que ajuda a detectar e a errar o gabarito".
- **Gasto**: rosca dos 3 comerciais (GPT 70%, Gemini 25%, Claude 5%) com o total no centro, e uma nota
  ao lado para o SLM (38 h de modelo, sem custo em dinheiro).
- **Ponte para a página 2**: "Cada uma dessas suítes foi executada contra o código correto, os WAs e
  os mutantes. Veja como foi →".

### Página 2 — A avaliação

As páginas atuais **Combinação** e **Comparações**, numa só, com o conteúdo de hoje:

- no topo, os números da avaliação no recorte (combinações avaliadas, AC aprovado e reprovado,
  detectados em cada oráculo), que hoje estão na "Visão geral";
- **Comparações**: oráculo declarado × corrigido por combinação e o modelo local ao lado dos
  comerciais;
- **Combinação**: teste a teste, com o código do alvo ao lado do `AC_ref`;
- **Ponte para a página 3**: "Somando todas as combinações, quem se saiu melhor? →".

---

### Página 3 — As métricas

#### 3.0 Abertura: o placar

- **Título**: "Nenhuma IA venceu em todas as métricas"
- **Subtítulo**: "Posição de cada modelo em cada métrica (média dos 3 cenários). 1º = melhor."
- **Gráfico**: tabela-placar (*Rankings*), modelos nas linhas, métricas nas colunas, a posição e o
  valor em cada célula, o 1º lugar destacado:

| Métrica (melhor =) | Gemini | Claude | GPT | SLM | SLM 1ª tentativa |
|---|---|---|---|---|---|
| Falhas reais detectadas, TDF\* (maior) | **1º — 90,1%** | 2º — 85,9% | 3º — 84,7% | 4º — 71,5% | 5º — 64,2% |
| Mutantes detectados, MS\* (maior) | **1º — 97,0%** | 2º — 95,3% | 3º — 94,4% | 4º — 90,9% | 5º — 82,7% |
| Problemas com falso positivo, TFP (menor) | 5º — 54,8% | **1º — 17,3%** | 2º — 20,2% | 3º — 30,5% | 4º — 42,5% |
| Detecção vinda de gabarito errado, Δ (menor) | 3º — 5,4 pts | 2º — 2,0 pts | **1º — 1,9 pts** | 4º — 6,3 pts | 5º — 10,7 pts |
| Combinações com suíte, TC (maior) | 100% | 99,5% | 100% | 100% | 91,2% |
| Custo por 1.000 WAs detectados (menor) | 2º — US$ 0,09 | **1º — US$ 0,02** | 3º — US$ 0,26 | — (local) | — (local) |

- **SLM 1ª tentativa** é o modelo local com um único pedido por combinação, como os comerciais, sem
  as novas tentativas do SLM final. Nota no placar: "53 das 600 combinações ficaram sem suíte e contam
  0% de detecção", o que puxa a TDF\* e o MS\* para baixo. A comparação justa com os comerciais (uma
  chamada contra uma) é o motivo de ela estar aqui.

- **Anotação** (callout): "O Gemini lidera em detecção; o Claude, em confiabilidade e custo."
- **Nota honesta**: a média dos 3 cenários esconde diferenças por cenário (seção 3.4); o SLM roda
  local, sem custo em dinheiro, e por isso não entra no ranking de custo.
- O placar usa TDF\*/MS\* (gabarito do AC), e não TDF/MS, para nenhuma posição vir de gabarito
  errado (decidido, 2026-11-12).

#### 3.1 Falhas reais (TDF e TDF\*)

- **Título**: "O Gemini encontra cerca de 9 em cada 10 falhas reais, em qualquer cenário"
- **Gráfico**: barras horizontais ordenadas (*Rankings*) com dois marcadores por modelo, TDF → TDF\*
  (*Before/After*, mesma escala); um painel por cenário ou um seletor de cenário.
- **Números** (TDF → TDF\*, de 20.000 WAs):

| | caixa-preta | caixa-branca | híbrido |
|---|---|---|---|
| Gemini | 95,2 → 90,0 | 95,6 → 89,7 | 95,8 → 90,7 |
| Claude | 86,1 → 83,8 | 89,7 → 88,0 | 87,8 → 86,0 |
| GPT | 85,9 → 84,4 | 88,9 → 86,7 | 85,1 → 83,1 |
| SLM | 82,7 → 69,9 | 74,8 → 72,3 | 76,0 → 72,3 |

- **Anotações**: (1) "pelo gabarito do AC, Gemini à frente de todos na caixa-preta e no híbrido
  (Wilcoxon com Holm); na caixa-branca, empate estatístico com o Claude (p = 0,07)"; (2) seta no SLM
  caixa-preta: "perde 12,8 pontos quando o gabarito é corrigido: 1 em cada 6 detecções era por saída
  esperada errada"; (3) "GPT e Claude: empate estatístico na caixa-preta e na caixa-branca".

#### 3.2 Mutantes (MS e MS\*)

- **Título**: "Mutantes são mais fáceis: todos os modelos passam de 88%; o Gemini volta a liderar"
- **Gráfico**: o mesmo do 3.1 (mesmo desenho, para comparar sem reaprender), em tamanho menor.
- **Números (MS\*)**: Gemini 96,8–97,1; Claude 94,4–96,2; GPT 93,9–94,9; SLM 88,8–92,2.
- **Anotação**: "A diferença entre os modelos é menor do que nas falhas reais: falhas humanas são o
  teste mais exigente."

#### 3.3 Falsos positivos (TFP) — o clímax

- **Título**: "Quem mais detecta também mais erra: o Gemini reprova o código correto em 55% dos
  problemas"
- **Gráfico principal** (*Deviation*/troca): dispersão com **TFP no eixo x** (menor é melhor) e
  **TDF\* no eixo y**, um ponto por modelo × cenário, com o canto "ideal" (muito detecta, pouco erra)
  sombreado. Mostra num só gráfico a resposta a "quem se saiu bem em tudo".
- **Números (TFP, % dos 200 problemas)**: Gemini 54,5 / 55,0 / 55,0; SLM 55,5 / 16,5 / 19,5; GPT
  20,0 / 25,5 / 15,0; Claude 18,0 / 17,5 / 16,5 (caixa-preta / branca / híbrido).
- **Anotações**: (1) no Gemini: "mais da metade das suítes tem algum teste com saída esperada
  errada"; (2) no SLM caixa-preta: "sem o código, o SLM erra o gabarito como o Gemini"; (3) no canto
  ideal: "Claude e GPT: menos falsos positivos, detecção ~5 pts abaixo do Gemini".
- **Apoio**: % dos **testes** errados (TFP por teste): Gemini ~10%, SLM caixa-preta 26%, GPT e
  Claude 2–6%. Deixar claro o denominador: problemas × testes.

#### 3.4 Contexto: o cenário importa? (IIC)

- **Título**: "Dar mais contexto muda pouco: juntar enunciado e código não melhora a detecção"
- **Gráfico 1**: pontos ligados por linha (*slope*), um por modelo, nos 3 cenários (TDF\*), para ver a
  inclinação; Gemini praticamente plano (Friedman p = 0,41, sem diferença entre cenários).
- **Gráfico 2**: barras divergentes do IIC oficial (agregado nos 200 problemas), "+ código" e "+
  enunciado" por modelo, a partir do zero; seletor de oráculo (declarado / corrigido).
- **Números (IIC, declarado → corrigido)**: SLM +código −8,2 → **+3,5**; GPT +enunciado −4,3 → −4,1;
  Claude +código +2,0 → +2,6; Gemini entre −0,1 e +1,0.
- **Anotações**: (1) "O SLM vai melhor só com o enunciado; GPT e Claude, só com o código"; (2) no
  SLM: "a 'perda' ao receber o código some com o gabarito corrigido: eram detecções por gabarito
  errado"; (3) "nenhum IIC passa de ±5% fora o SLM".

#### 3.5 Custo-benefício

- **Título**: "O Claude detecta 1.000 falhas reais por US$ 0,02, cerca de 13× menos que o GPT"
- **Gráfico**: barras horizontais ordenadas, US$ por 1.000 WAs detectados (gabarito do AC), um valor
  por modelo comercial (média dos cenários) com o detalhe por cenário no tooltip.
- **Números**: Claude US$ 0,018–0,020; Gemini US$ 0,085–0,096; GPT US$ 0,241–0,286; gasto total
  US$ 19,35 (GPT 70%, Gemini 25%, Claude 5%).
- **Anotação**: "O SLM não tem custo em dinheiro, mas somou 38 h de modelo nas GPUs (contexto, não
  ranking)", conforme o `duration_s` de `cost.csv`.

#### 3.6 Fechamento: qual IA escolher? (o leitor decide)

**Decidido (Milena, 2026-11-12)**: o painel não dá uma conclusão única. Mostra **quem ganhou em
cada critério** e deixa o leitor escolher pela sua prioridade e pelo que ele tem em mãos.

- **Título**: "Qual IA escolher depende do que importa para você"
- **Entrada do leitor**: o **cenário** (o filtro da barra lateral, explicado em linguagem de uso:
  "tenho só o requisito" = caixa-preta, "tenho só o código" = caixa-branca, "tenho os dois" =
  híbrido) e a **prioridade**, escolhida aqui mesmo como um destaque, não como filtro: os critérios
  são as linhas do guia, e a prioridade só realça uma delas.
- **Gráfico**: um cartão por critério, com o vencedor, o valor e o segundo colocado:

| Se a sua prioridade é… | Critério | Vencedor (sem filtro, por cenário: só requisito / só código / os dois) |
|---|---|---|
| gastar pouco | custo por 1.000 WAs detectados | Claude / Claude / Claude (US$ 0,018–0,020) |
| encontrar o máximo de falhas | TDF\* | Gemini / Gemini, empate com Claude / Gemini (89,7–90,7%) |
| nunca reprovar o código correto | TFP | Claude 18,0%, empate com GPT / **SLM 16,5%**, empate com Claude / **GPT 15,0%**, empate com Claude |
| confiar no gabarito que a IA escreve | Δ_oráculo | GPT 1,5 / Claude 1,7 / Claude 1,9 pts |
| pegar defeitos sintéticos | MS\* | Gemini / Gemini, empate com Claude / Gemini (96,8–97,1%) |
| rodar sem custo de API | — | SLM (local; ver custo em tempo na página 1) |

- **Empate**: quando o teste estatístico não separa o 1º do 2º (por exemplo, a TFP do SLM e a do
  Claude na caixa-branca), o cartão diz "empate estatístico entre X e Y". Num recorte sem teste
  estatístico, diz "diferença não testada neste recorte".
- **Anotação**: "O vencedor muda com o cenário: com só o código, o modelo local é quem menos reprova
  o código correto."
- **Embaixo**: as **limitações**: uma execução por modelo (comerciais sem seed); saídas esperadas escritas pela IA
  sem conferência; 3 combinações do Claude sem suíte (contam 0%); problemas de rating 1000–1600 do
  Codeforces; o SLM é um modelo de 14B local, não comparável em custo.

## 3. Técnicas aplicadas (passo 3 da skill)

- **Título = conclusão** em toda seção; o tema vai no subtítulo.
- **Anotação do achado**: no máximo 2–3 por gráfico, perto do dado; nada óbvio anotado.
- **Rótulo direto** nas barras e pontos, sem legenda separada quando possível.
- **Denominador sempre visível**: "de 20.000 WAs", "dos 200 problemas", "dos testes".
- **Comparação justa**: mesmo tipo de gráfico e mesma escala no antes/depois (TDF → TDF\*).
- **Sem pizza com mais de 3–4 fatias**; ranking sempre em barras horizontais ordenadas.

## 4. Revisão (checklist da skill)

| Item | Situação no roteiro |
|---|---|
| Dá para dizer a conclusão numa frase? | sim: "nenhuma IA vence em tudo; Gemini detecta mais, Claude erra e gasta menos" |
| A abertura prende? | placar + "quem mais detecta mais erra" |
| Contexto suficiente? | página 1 "O experimento" antes dos resultados; denominadores recalculados com os filtros |
| Cada gráfico tem um ponto? | sim, no título |
| Arco completo? | experimento → avaliação → placar → métricas → clímax (troca) → contexto → custo → fechamento |
| Honestidade | mostra onde o líder perde (TFP), usa TDF\* no placar, cita empates estatísticos e limitações |
| A conferir pelos autores | as conclusões (são a tese do TCC), a média dos cenários no placar |

## 5. Decisões

Decididas (Milena, 2026-11-12):

1. Ordem das páginas: experimento → avaliação → métricas.
2. Filtros só na barra lateral, sempre aplicados, com os títulos recalculados para o recorte.
3. O placar e as seções da página 3 usam **TDF\*/MS\*** (gabarito do AC).
4. A **1ª tentativa do SLM entra** no placar e em todas as seções da página 3, como quinto conjunto,
   com a nota das combinações sem suíte.
5. O filtro de **rating** entra na barra lateral.

6. O fechamento é um **guia de escolha** (seção 3.6): quem ganhou em cada critério, por cenário, e
   o leitor decide pela sua prioridade; não há frase-tese única no painel.

Em aberto, sem bloquear a spec: **a frase final do TCC**. Opções a partir dos dados, para os autores
escolherem ou reescreverem no texto:

- (a) *"Nenhuma IA venceu em tudo: o Gemini detecta mais falhas, o Claude erra menos o gabarito e
  custa menos, e dar mais contexto quase não muda o resultado."* (resumo equilibrado)
- (b) *"Detectar mais não é o mesmo que testar melhor: a IA que mais encontra falhas é a que mais
  erra a saída esperada."* (destaca a troca detecta × erra, o achado mais surpreendente)
- (c) *"Para gerar testes de programas, um modelo comercial barato (Claude) chega perto do melhor em
  detecção com menos falsos positivos e uma fração do custo."* (recomendação prática; mais opinativa)

As frases-conclusão das seções 3.0 a 3.5 seguem a regra de cada título (recalculadas com os filtros).
