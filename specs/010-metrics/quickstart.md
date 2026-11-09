# Quickstart: validar as métricas (010)

Comandos em [contracts/cli.md](contracts/cli.md); tabelas em [data-model.md](data-model.md).

## Pré-requisitos

- `docker compose build` depois de entrarem `scipy` e `matplotlib`.
- Avaliações descompactadas (`unzip data/evaluation_<conjunto>.zip -d data/`), dataset e suítes
  descompactados; `cli check --deep` com `Resultado: OK`.

## 1. Testes

```bash
docker compose run --rm sandbox pytest tests/metrics
```

## 2. Calcular

```bash
docker compose run --rm app python -m metrics compute
```

Esperado: `data/metrics/` com as 6 tabelas e o `run.json`; o resumo traz TDF, MS, TFP e TC por
conjunto × cenário. Rodar de novo dá os mesmos arquivos (`sha256sum data/metrics/*.csv`).

## 3. Conferir à mão (SC-002, SC-003)

- Somas de `wa_declared` por conjunto em `per_problem.csv` = `detected.declared_wa` do
  `manifests/evaluation_<conjunto>_report.json`.
- O custo total de cada comercial em `cost.csv` = `cost_usd.total` do relatório de geração.
- Três combinações conferidas com a conta manual de TDF, MS, TFP, TDF\* e MS\*.

## 4. Figuras

```bash
docker compose run --rm app python -m metrics figures
docker compose run --rm app python -m metrics figures --macrocategoria matematica
```

Esperado: arquivos `data/metrics/figures/tdf_by_model.png` e
`tdf_by_model__macrocategoria-matematica.pdf` etc., com o filtro no rodapé. A mesma figura baixada
no dashboard (página Métricas, mesmo filtro) é idêntica.

## 5. Pacote

```bash
docker compose run --rm app python -m metrics package
docker compose run --rm app python -m metrics verify --extracted data/metrics
```
