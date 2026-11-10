# Contrato: funções públicas (usadas pelo comando e pelo dashboard)

| Função | Entrada | Saída |
|---|---|---|
| `metrics.sources.load(root, evaluation_dir)` | pastas | `(per_problem: DataFrame, detected_wa: DataFrame)` |
| `metrics.cuts.apply(per_problem, *, macrocategorias=(), statuses=(), sets=(), scenarios=())` | filtros (listas vazias não filtram) | `DataFrame` filtrado; erro se o resultado for um problema só |
| `metrics.primary.table(per_problem)` | tabela por problema (já cortada) | linhas de `metrics.csv` por conjunto × cenário |
| `metrics.iic.table(detected_wa, problems)` | detectados e a lista de problemas do corte | linhas de `iic.csv` |
| `metrics.stats.table(per_problem)` | tabela por problema | linhas de `stats.csv` |
| `metrics.cost.table(root, per_problem)` | pastas e detectados | linhas de `cost.csv` |
| `metrics.figures.FIGURES` | — | os nomes das figuras |
| `metrics.figures.chart(name, tables, filters, source, mode)` | figura, tabelas, filtros, fonte, tema `light`/`dark` | o gráfico Altair que o painel mostra |
| `metrics.figures.render(name, tables, filters, fmt, source, mode)` | o mesmo, e `png`, `svg` ou `pdf` | `(file_name, bytes)` do mesmo gráfico; PNG e SVG determinísticos |

O dashboard usa `cuts.apply`, `primary.table`, `figures.chart` e `figures.render`. Nenhuma conta de métrica é feita
fora deste pacote.
