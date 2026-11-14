# Quickstart: revisão 2 do dataset

**Feature**: `specs/007-dataset-revision` | **Date**: 2026-10-18 | **Plan**: [plan.md](./plan.md)

Ordem de execução. Os formatos estão em [contracts/cli.md](./contracts/cli.md) e
[data-model.md](./data-model.md).

## 0. Emenda da constitution (bloqueante)

Os autores aprovam o texto de research R1. Só então a constitution vai a 1.8.0.

## 1. Testes

```text
docker compose run --rm sandbox pytest tests/dataset/test_revision.py tests/ai_clients/test_package_merge.py tests/cli
```

## 2. As 15 decisões (autores)

```text
docker compose run --rm app python -m dataset revise --draft-decisions
```

Os autores editam cada `manifests/statement_decisions/<id>.json`, com o original ao lado (a cópia
do Codeforces da 006): `decision`, o texto corrigido, o motivo, o nome e a data.

## 3. A revisão 2

```text
docker compose run --rm app python -m dataset revise --dry-run
docker compose run --rm app python -m dataset revise
rm -rf data/dataset && unzip data/dataset.zip -d data/
docker compose run --rm app python -m dataset verify --extracted data/dataset
docker compose run --rm app python -m dataset verify --zip data/dataset.rev1.zip --manifest manifests/dataset.rev1.manifest.json
docker compose run --rm app python -m dataset check-statements
```

Esperado:
- os dois `verify` dão `OK`;
- o `check-statements` dá 0 `lost_exponent` e 0 `lost_index` nos problemas corrigidos.

## 4. Mutantes (F4)

```text
docker compose run --rm app python -m mutation verify
```

## 5. SLM: só o afetado

```text
mv data/suites/slm data/suites/slm-rev1
```

Depois, alternar o `generate` e o `execute` que o `revise` imprimiu, até o fim, e então:

```text
docker compose run --rm app python -m ai_clients package --merge-from data/suites/slm-rev1
docker compose run --rm app python -m cli check --deep
```

**Medir e registrar**: o número de combinações afetadas e o tempo da execução nova.

## 6. GPT e Gemini

Rodam a execução completa normalmente: o `run.json` deles grava o hash do manifesto da revisão 2.
