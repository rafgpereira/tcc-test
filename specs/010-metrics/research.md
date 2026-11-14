# Research: Métricas (010)

Nenhum `NEEDS CLARIFICATION` ficou. Cada item tem a decisão, o motivo e as alternativas.

## R1. Fonte: o `results.csv` de cada conjunto

- **Decision**: as métricas leem o `results.csv` dos 5 conjuntos (uma linha por combinação × alvo,
  com o AC aprovado, os testes do AC com saída diferente e com erro, o tamanho da suíte, o status e,
  por alvo, a detecção nos dois oráculos). A macrocategoria vem do `metadata.json`.
- **Rationale**: tem tudo o que as métricas pedem. A TFP por teste usa as contagens de testes do AC
  por combinação, e o IIC usa a detecção por alvo. É derivado dos JSON e versionado no pacote.
- **Alternatives considered**: ler os 3.000 JSON (mais lento, sem ganho de informação).

## R2. Tabela por problema como base

- **Decision**: `per_problem` tem uma linha por conjunto × cenário × problema, com `has_suite`,
  `status`, `macrocategoria`, `suite_size`, `ac_rejected`, `ac_wrong_output_tests`,
  `ac_runtime_error_tests`, `wa_declared`, `wa_corrected`, `mutants_declared`,
  `mutants_corrected`, `n_wa` e `n_mutants`. Os **conjuntos** de WAs detectados, que o IIC usa, ficam
  numa tabela longa à parte (`detected_wa`: conjunto, cenário, problema, alvo, oráculo).
- **Rationale**: TDF, MS e TFP são médias por problema. O W_total e o M são constantes (100), então a
  média das razões é igual à razão das somas, como mostra a proposta (B.3). Os testes pareados
  precisam do valor por problema.

## R3. Testes estatísticos

- **Decision**: `scipy.stats.friedmanchisquare` (3 cenários; 4 modelos), `scipy.stats.wilcoxon`
  (pares; `zero_method="wilcox"`, bilateral) e McNemar exato pelo teste binomial bilateral sobre os
  pares discordantes (`scipy.stats.binomtest`). Holm-Bonferroni à mão, sobre as comparações par a
  par de cada família (uma métrica × um conjunto ou um cenário). A12 = P(X > Y) + 0,5·P(X = Y), e o
  delta de Cliff = 2·A12 − 1. α = 0,05.
- **Rationale**: são os da proposta (seção D). O McNemar exato é o correto com poucos pares
  discordantes. O `statsmodels` seria uma dependência grande só para isso.
- **Famílias**: (a) cenários dentro de cada conjunto: Friedman e, se p < α, 3 Wilcoxon com Holm;
  (b) modelos dentro de cada cenário (`slm`, `gpt`, `gemini`, `claude`): Friedman e 6 Wilcoxon com
  Holm; (c) `slm-attempt1` × cada comercial e × `slm`, por cenário: Wilcoxon com Holm. Para a TFP, o
  McNemar substitui o Wilcoxon (e o teste Q de Cochran, binário, não é usado: a proposta não o pede;
  para mais de dois grupos fica só a comparação par a par com Holm).
- **Sem variação** (todos os pares iguais): resultado "sem diferença", p = 1, sem exceção.

## R4. IIC

- **Decision**: D(R), D(C) e D(H) são conjuntos de pares (problema, WA) detectados (oráculo
  declarado, como na métrica original) em caixa-preta, caixa-branca e híbrido. O IIC agregado e a
  visão por problema são feitos com os mesmos conjuntos restritos a um problema. O IIC também é
  calculado pelo oráculo corrigido, numa coluna à parte, para a discussão do Δ_oráculo.
- **Rationale**: é a definição B.3 confirmada. A versão corrigida é barata e evita que um IIC
  "positivo" venha de gabarito errado.

## R5. Custo, tokens e tempo

- **Decision**:
  - **Comerciais**: custo e *tokens* por cenário de `manifests/<modelo>_generation_report.json`
    (`cost_usd.by_group`, que inclui os pedidos barrados e repetidos, e `tokens`); o tempo é a
    soma da latência das tentativas e dos barrados.
  - **Modelo local**: *tokens* (`prompt_eval_count` + `eval_count`) e tempo (`total_duration_ns`) de
    todas as tentativas da árvore vigente de cada combinação; para `slm-attempt1`, só da tentativa 1.
  - **CPD** = custo do cenário ÷ WAs detectados (e ÷ mutantes), pelos dois oráculos.
- **Rationale**: o relatório já é a soma oficial (SC-003 confere o total). O modelo local não tem
  custo monetário e nunca é convertido.

## R6. Cortes

- **Decision**: `cuts.apply(per_problem, macrocategorias, statuses, sets, scenarios)` antes de
  qualquer conta. As tabelas versionadas trazem as métricas sem corte e por macrocategoria (3) e por
  status (cada status presente); outros cortes são feitos sob demanda (figuras e dashboard). Corte
  por um problema só é recusado.
- **Rationale**: FR-012; os cortes versionados são os que o texto cita.

## R7. Figuras

- **Decision**: matplotlib com o backend `Agg`. Cada figura é uma função
  `fig_<nome>(per_problem, detected_wa, filters) -> Figure`, que recalcula pelas funções de métrica.
  `save(fig, name, filters)` grava PNG (200 dpi) e PDF com `metadata` sem data (`CreationDate=None`,
  `Software` fixo) e `svg.hashsalt`/`SOURCE_DATE_EPOCH` fixos, para os bytes serem iguais a cada
  execução. O rodapé traz os filtros e a fonte: os hashes curtos dos manifestos de avaliação lidos,
  não a revisão do Git, que não existe dentro do contêiner. O nome do arquivo é
  `<figura>__<filtros>.{png,pdf}` (sem filtro, só `<figura>`).
- **Revisão (2026-11-09, Milena)**: a figura baixada precisa ser igual ao gráfico da tela. As
  figuras passaram a ser o gráfico Altair do painel (`metrics/charts.py`), exportado pelo
  `vl-convert-python` 1.9.0.post1: PNG (escala 2) e SVG saem iguais byte a byte a cada chamada (os
  ids `clipN` do SVG são renumerados na ordem em que aparecem); o PDF tem o mesmo desenho, mas o
  vl-convert muda a ordem dos objetos de fonte de uma chamada para outra (medido: 4 variantes em 20
  chamadas), por isso o pacote leva PNG e SVG e não o PDF. O matplotlib saiu das dependências.
- **Figuras iniciais**: `tdf_by_model` (barras, modelo × cenário), `tdf_declared_vs_corrected`
  (barras pareadas, Δ_oráculo), `ms_declared_vs_corrected`, `tfp_by_cause` (barras empilhadas:
  `oráculo` × `entrada_inválida`), `iic_distribution` (boxplot por problema, por conjunto e direção),
  `cost_per_detection` (comerciais).
- **Rationale**: FR-017; uma função por figura é o que o comando e o dashboard compartilham.

## R8. Saída e pacote

- **Decision**: `compute` grava em `data/metrics/` (pasta temporária ao lado e troca atômica):
  `per_problem.csv`, `detected_wa.csv`, `metrics.csv`, `iic.csv`, `stats.csv`, `cost.csv` e um
  `run.json` (hashes dos manifestos das entradas, versão do esquema, α). `figures` sem filtro grava as
  figuras padrão em `data/metrics/figures/`. `package` gera `data/metrics.zip` (tabelas e figuras
  padrão) e `manifests/metrics.manifest.json`; `verify` confere o zip e a pasta.
- **Rationale**: Princípio II; o dashboard lê `data/metrics/`.
- **Sem camada no `cli check`**: o módulo não produz uma pasta por problema (é o critério da
  constitution para ganhar uma camada); a integridade é do `verify`.

## R9. Metodologia

- **Decision**: a seção 5 é reescrita com 5.1–5.4 (as fórmulas mantidas, com as regras B.2/B.3/B.4),
  seguidas de 5.5 (complementares C.1–C.4), 5.6 (estatística), 5.7 (cortes) e 5.8 (figuras). A Q5
  entra na seção 0. A limitação "oráculo por execução × por predição" entra na seção 7, com o motivo
  decidido em 2026-11-09. As pendências 3 e 26 são fechadas. `docs/metricas-referencia.md` (consolidado na metodologia, seção 5) é
  removido com o ok dos autores, porque o conteúdo passa à metodologia.

## R10. Testes

- **Decision**: casos conhecidos por métrica: MS com DM=0 → 0,0; TDF com 3 problemas e detecções
  conhecidas; TFP com `discarded_manual` (N = 200 e a visão com suíte); IIC com conjuntos pequenos,
  incluindo denominador zero e IIC > 100%; TC; Δ_oráculo; TFP por causa; densidade; CPD (e a
  ausência de US$ no modelo local). Estatística conferida contra exemplos clássicos: Wilcoxon e
  Friedman contra o próprio `scipy`; o McNemar exato contra a binomial à mão; Holm contra o exemplo do
  artigo de Holm; o A12 contra contagens à mão. Figuras: geradas duas vezes têm os mesmos bytes, e
  o filtro aparece no nome e no rodapé. As somas de detectados conferem com `evaluation report`.
