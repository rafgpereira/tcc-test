# Contrato: funções públicas (usadas pelo comando e pelo dashboard)

| Função | Entrada | Saída |
|---|---|---|
| `metrics.sources.load(root, evaluation_dir)` | pastas | `(per_problem: DataFrame, detected_wa: DataFrame)` |
| `metrics.cuts.apply(per_problem, *, macrocategorias=(), statuses=(), sets=(), scenarios=())` | filtros (listas vazias não filtram) | `DataFrame` filtrado; erro se o resultado for um problema só |
| `metrics.primary.table(per_problem)` | tabela por problema (já cortada) | linhas de `metrics.csv` por conjunto × cenário |
| `metrics.iic.table(detected_wa, problems)` | detectados e a lista de problemas do corte | linhas de `iic.csv` |
| `metrics.stats.table(per_problem)` | tabela por problema | linhas de `stats.csv` |
| `metrics.cost.table(root, per_problem)` | pastas e detectados | linhas de `cost.csv` |
| `metrics.figures.FIGURES` | — | nome → função `(per_problem, detected_wa, filters) -> Figure` |
| `metrics.figures.render(name, per_problem, detected_wa, filters, fmt)` | figura, dados, filtros, `png` ou `pdf` | `(file_name, bytes)` determinísticos, com o rodapé |

O dashboard usa `cuts.apply`, `primary.table` e `figures.render`. Nenhuma conta de métrica é feita
fora deste pacote.
