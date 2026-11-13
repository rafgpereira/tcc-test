# Contrato de narrativa por gráfico

Passo 3 da skill *visual-storytelling-design* (anotação, enquadramento, denominador) aplicado a
cada gráfico do painel. É o que a implementação segue e o que os testes conferem. Os textos entre
aspas são os modelos de frase (R5): `{líder}`, `{segundo}`, `{valor}`, `{n}` vêm do recorte, e o
texto final de cada modelo é revisado pelos autores.

## Regras que valem para todos os gráficos

| Regra | Origem na skill | Como se confere |
|---|---|---|
| O título é a conclusão do recorte, nunca o tema; o tema vai no subtítulo | princípio 1, *lead with insight* | teste: o nome no título é o líder do recorte |
| No máximo 3 anotações, perto do dado; nada óbvio anotado | seção 3, *annotation guidelines* | revisão (R10) |
| O valor escrito no elemento (rótulo direto), sem legenda separada quando possível | seção 3, *direct labels* | revisão |
| Denominador visível e recalculado ("de {n} WAs", "dos {n} problemas", "dos {n} testes") | seção 5, *clarify denominator* | teste: o denominador do subtítulo = total do recorte |
| O líder numa cor de destaque única; os demais em cinza neutro; a mesma cor em todas as seções | seção 3, *callouts*; R6 | revisão |
| Antes/depois (TDF → TDF\*) com o mesmo tipo de gráfico e a mesma escala | padrão *Before/After* | revisão |
| Onde o líder perde, isso aparece: o placar mostra todos os critérios | passo 4, *be honest* | revisão |
| Empate estatístico dito como empate; recorte sem teste dito como "não testado" | seção 5, *note limitations* | teste (R3) |
| Rodapé: recorte ativo e fonte (`data/metrics`, hash da avaliação) | seção 5, *data source stated* | teste (já existe na 010) |
| Rosca ou pizza só com até 4 fatias; mais categorias, barras | *Part-to-Whole*: "avoid pie > 6 slices", apertado para 4 | teste (SC-005) |

## Página 1 — O experimento

| Gráfico | Padrão | Título (modelo) | Denominador | Anotação |
|---|---|---|---|---|
| Números grandes | — | "{n} problemas, {2n·100} falhas, {k} IAs, {s} suítes" | — | "100 falhas reais + 100 mutantes por problema" |
| Ratings | *Rankings* (barras verticais em ordem de rating) | "Problemas de rating {min} a {max} do Codeforces" | "dos {n} problemas" | a faixa mais comum |
| Macrocategorias | *Part-to-Whole* (rosca, 3 fatias) | "{maior} é a maior parte ({valor})" | "dos {n} problemas" | — |
| Suítes por IA e status | *Part-to-Whole* (barra 100% por IA) | "Toda IA entregou suíte em pelo menos {mínimo} das combinações" | "de {c} combinações por IA" | as combinações sem suíte, se houver |
| Testes por suíte | *Rankings* (pontos por IA e cenário) | "{líder} escreve as suítes maiores: {valor} testes em média" | "{t} testes no total" | — |
| Gasto | *Part-to-Whole* (rosca, 3 comerciais) | "US$ {total} no total; {líder} ficou com {parte}" | total no centro | nota ao lado: modelo local, {h} h de modelo, sem custo em dinheiro |

Passagem para a página 2: "Cada uma dessas suítes foi executada contra o código correto, os WAs e os
mutantes. Veja como foi →".

## Página 2 — A avaliação

Sem gráfico novo: os números da avaliação no topo (com o rótulo de prévia da feature 011) e as
tabelas atuais de Comparações e de Combinação, em abas. Passagem para a página 3: "Somando todas
as combinações, quem se saiu melhor? →".

## Página 3 — As métricas

### 3.0 Placar (figura `scoreboard`)

- **Padrão**: *Rankings*, em grade (conjuntos × critérios), com posição e valor em cada célula.
- **Título**: "Nenhum conjunto venceu em todos os critérios" quando os líderes diferem entre os
  critérios; "{líder} venceu em todos os critérios" quando coincidem (a regra cobre os dois).
- **Subtítulo**: "Posição em cada critério ({cenários}); 1º = melhor. Gabarito do AC."
- **Destaque**: a célula do 1º de cada critério.
- **Notas**: modelo local fora do ranking de custo; 1ª tentativa com "{k} combinações sem suíte
  contam 0%"; "média dos cenários, sem teste estatístico".

### 3.1 Falhas reais (figura `tdf_by_model`, revista)

- **Padrão**: *Rankings* + *Before/After* (TDF → TDF\* por conjunto, barras horizontais ordenadas
  pela TDF\*).
- **Título**: "{líder} encontra {valor} das falhas reais" ou, em empate, "{líder} e {segundo}
  empatam em falhas reais encontradas ({v1} × {v2})".
- **Denominador**: "de {n·100} WAs".
- **Anotações**: (1) a diferença do 1º para o 2º e o estado do teste (R3); (2) o conjunto com o maior
  Δ_oráculo: "perde {Δ} pontos quando o gabarito é corrigido".

### 3.2 Mutantes (figura `ms_declared_vs_corrected`, revista)

- Mesmo desenho do 3.1, menor. **Título**: "{líder} detecta {valor} dos mutantes".
- **Anotação**: "a distância entre os conjuntos é menor que nas falhas reais" quando a amplitude do
  MS\* é menor que a da TDF\* no recorte (regra, não frase fixa).

### 3.3 Falsos positivos (figuras `tradeoff` e `tfp_by_cause`)

- **Padrão**: *Deviation*/troca: dispersão com TFP no eixo x (menor é melhor) e TDF\* no eixo y, um
  ponto por conjunto × cenário, a região ideal (alto em y, baixo em x) sombreada a 10–20% de
  opacidade.
- **Título**: "Quem mais detecta também mais erra o gabarito" se o líder da TDF\* for o último em TFP;
  senão "{líder TFP} reprova o código correto em menos problemas: {valor}".
- **Denominador**: "dos {n} problemas" (TFP) e "dos {n·100} WAs" (TDF\*).
- **Anotações**: (1) o ponto do líder da TDF\*; (2) o ponto do líder da TFP; (3) a região ideal.
- **Divergência (2026-11-12, implementação)**: um ponto por conjunto (a média dos cenários do
  recorte, os números do placar), não por conjunto × cenário: com 15 pontos os nomes se sobrepunham;
  o detalhe por cenário fica no guia. A região ideal é a das medianas das IAs do recorte. Em 3.1 e
  3.2, a barra leva um rótulo curto ("90,1% · +4,2") e as anotações completas ficam como notas sob o
  gráfico, porque não cabiam nos cartões de meia largura.
- **Apoio**: `tfp_by_cause` com o título "{maior} dos testes de {conjunto} esperam a saída errada" e o
  denominador "dos {t} testes".

### 3.4 Contexto (figuras `scenario_shift` e `iic_diverging`)

- **`scenario_shift`**: linhas ligando os 3 cenários por conjunto (TDF\*). **Título**: "O cenário
  muda até {Δmax} pontos ({conjunto}); {mais estável} quase não muda".
- **`iic_diverging`**: barras divergentes do IIC agregado ("+ código" e "+ requisito") por conjunto,
  a partir do zero, no par divergente validado pela skill `dataviz` (azul acima de zero, vermelho abaixo,
cinza neutro no zero; nunca verde × vermelho, que daltônicos não distinguem), com o seletor de
  gabarito (declarado / corrigido) na página. **Título**: "Juntar requisito e código muda no máximo
  {|IIC|max}% ({conjunto})". **Anotação**: quando o sinal de um conjunto muda entre os dois
  gabaritos: "com o gabarito do AC, o efeito de {conjunto} vira {sinal}".
- O boxplot atual (`iic_distribution`) continua como figura de diagnóstico, abaixo, recolhido.

### 3.5 Custo-benefício (figura `cost_per_detection`, revista)

- **Padrão**: *Rankings* (barras horizontais, US$ por 1.000 WAs pelo gabarito do AC).
- **Título**: "{líder} detecta 1.000 falhas por US$ {valor}, {razão}× menos que {último}".
- **Nota**: modelo local fora do ranking, com o tempo de modelo; com filtro por problema, "o custo não
  se divide por problema: valor de todos os problemas".

### 3.6 Guia de escolha (figura `choice_guide`)

- **Padrão**: *Interactive Exploration* (resumo dinâmico): uma linha por critério, uma coluna por
  cenário do recorte (caixa-preta, caixa-branca, híbrido), cada célula com vencedor, valor,
  segundo colocado e estado do teste (diferem / empate / não testado).
- **Título**: "Qual IA escolher depende do que importa para você". Nunca um vencedor geral.
- **Interação**: a prioridade escolhida pelo leitor realça a linha (não muda números).
- **Embaixo**: as limitações (uma execução por modelo; gabarito escrito pela IA sem conferência;
  combinações sem suíte contam 0%; problemas de rating 1000–1600; modelo local sem custo comparável).
