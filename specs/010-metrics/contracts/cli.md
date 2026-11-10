# Contrato: `python -m metrics` (serviço `app`)

| Subcomando | Opções | Efeito | Códigos |
|---|---|---|---|
| `compute` | `--evaluation-dir DIR` (padrão `data/evaluation`) | portão (`cli check --deep` nas camadas do dataset, das 5 avaliações e das suítes) e relatórios de avaliação completos; grava as tabelas e o `run.json` em `data/metrics/` (troca atômica) e imprime o resumo (TDF, MS, TFP, TC por conjunto × cenário) | `0`; `1` portão ou avaliação incompleta; `2` uso |
| `figures` | `--macrocategoria M`, `--status S`, `--set S`, `--scenario C` (repetíveis), `--format png,svg,pdf`, `--output-dir DIR` (padrão `data/metrics/figures`) | desenha as figuras a partir das tabelas de `data/metrics/` com os filtros; nome e rodapé com os filtros e a fonte | `0`; `1` tabelas ausentes; `2` filtro inválido (incluindo um problema só) |
| `package` | — | `data/metrics.zip` (tabelas, `run.json` e figuras padrão) e `manifests/metrics.manifest.json`, determinísticos | `0`; `1` recusa (tabelas ausentes ou figuras padrão faltando) |
| `verify` | `--extracted DIR` | confere o zip e, opcionalmente, a pasta | `0` confere; `1` diverge; `2` manifesto ausente |
