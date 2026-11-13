# Contrato: funções de narrativa, figuras e comando

## `metrics.story` (novo; Python puro, sem Streamlit)

Todas recebem as tabelas lidas por `metrics.tables.read` (`per_problem`, `detected_wa`, `metrics`,
`iic`, `stats`, `cost`) e um `Recorte` (data-model.md). Nenhuma lê arquivo nem grava nada.

| Função | Devolve | Erros |
|---|---|---|
| `criteria()` | a lista fixa de `Criterio` (ordem do placar) | — |
| `values(tables, recorte)` | um quadro conjunto × critério com o valor no recorte (R4) | `CutError` se o recorte tem 1 problema ou nenhum |
| `scoreboard(tables, recorte)` | o quadro do placar: valor e posição (empates com a mesma posição; o modelo local sem posição em custo) | idem |
| `leader(tables, recorte, criterio, cenario=None)` | `Resultado`: líder, valor, segundo, valor do segundo, estado do teste (R3) | idem |
| `conclusion(tables, recorte, secao)` | `Titulo`: o texto do título-conclusão da seção, pela regra de `contracts/narrative.md` | idem |
| `guide(tables, recorte)` | a lista de `Cartao` (critério × cenário do recorte) | idem |
| `test_state(stats, metrica, cenario, a, b, recorte)` | `"differ"`, `"tie"` ou `"untested"` | — |

Recorte completo, sem filtro: os valores de `values` coincidem com `metrics.csv` e `cost.csv`
(média dos cenários) até a 4ª casa (SC-001).

## `metrics.cuts.apply` (alterado)

Ganha `ratings=()` (inteiros), que restringe pela coluna `rating` de `per_problem`. Com os demais
argumentos, nada muda.

## `metrics.sources` (alterado)

`per_problem.csv` ganha a coluna `rating` (inteiro, o `cf_rating` do `metadata.json`), logo depois de
`macrocategoria`. Nenhuma outra tabela muda.

## `metrics.figures` e `metrics.charts` (alterados)

`FIGURES` ganha `scoreboard`, `tradeoff`, `scenario_shift`, `iic_diverging` e `choice_guide`;
`tdf_by_model`, `ms_declared_vs_corrected` e `cost_per_detection` passam a seguir o contrato de
narrativa (título-conclusão por regra, destaque do líder). `tdf_declared_vs_corrected`,
`tfp_by_cause` e `iic_distribution` continuam. `NO_PROBLEM_CUTS` continua com
`cost_per_detection` e ganha a parte de custo do `scoreboard`/`choice_guide`, que mostram a nota
em vez de recusar. Cada figura continua com `chart(name, tables, filters, source, mode)` e
`render(...)`, iguais para o painel e o comando; o subtítulo traz o recorte e a fonte.

## Comando (alterado)

```text
python -m metrics figures [--figure NOME ...] [--macrocategoria M ...] [--rating R ...]
                          [--status S ...] [--set S ...] [--scenario C ...] [--problem ID ...]
                          [--format png,svg,pdf] [--output-dir DIR]
```

- `--figure` aceita os nomes novos; sem `--figure`, desenha todas.
- `--rating` (novo, repetível): um inteiro de 1000 a 1600; valor inexistente no dataset → código `2`.
- `python -m metrics package` passa a exigir também as figuras novas sem filtro (PNG e SVG).
- Códigos de saída: os mesmos da feature 010.

## Painel (alterado)

- Páginas: `experiment` (padrão), `evaluation`, `metrics` (`st.navigation`).
- Barra lateral: conjunto, cenário, macrocategoria, **rating**, status, problema; o mesmo recorte
  vai para `dashboard.data.apply_filters` (páginas 1 e 2) e para `metrics.story`/`metrics.figures`
  (página 3).
- `python -m dashboard serve` não muda.
