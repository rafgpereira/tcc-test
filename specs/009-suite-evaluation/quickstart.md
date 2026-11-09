# Quickstart: validar a avaliação das suítes (009)

Guia de validação ponta a ponta. Comandos detalhados em [contracts/cli.md](contracts/cli.md);
formato dos resultados em [data-model.md](data-model.md).

## Pré-requisitos

- Imagem construída (`docker compose build`), `.env` com `HOST_UID`/`HOST_GID`.
- Dataset, mutantes e as 4 suítes descompactados em `data/`:
  `unzip data/dataset.zip -d data/`, `unzip data/mutants.zip -d data/` e o mesmo para
  `slm_suites.zip`, `gpt_suites.zip`, `gemini_suites.zip`, `claude_suites.zip`.
- `docker compose run --rm app python -m cli check --deep` com saída `0`.

## 1. Testes do módulo

```bash
docker compose run --rm sandbox pytest tests/evaluation tests/cli
```

Esperado: tudo `passed`, inclusive os casos conhecidos de research R10.

## 2. Conferência num problema

```bash
docker compose run --rm sandbox python -m evaluation run --problem 1000_B --output-dir data/evaluation-conf
```

Conferir em `data/evaluation-conf/gpt/problems/1000_B/black_box.json`:

- `ac.tests` tem um item por teste de `data/suites/gpt/problems/1000_B/black_box/suite.json`;
- para um WA com `declared.detected = true`, o teste `declared.test_index` de fato reprova esse WA
  (comparar a saída do WA com a declarada);
- se `ac.approved = true`, os conjuntos `detected.declared_*` e `detected.corrected_*` são iguais.

## 3. Piloto (FR-021)

```bash
docker compose run --rm sandbox python -m evaluation run \
  --problem 1000_B --problem 1005_C --problem 1008_B --problem 1_B --problem 61_B
docker compose run --rm app python -m evaluation report
```

Esperado: 60 combinações finais e 15 da 1ª tentativa; o relatório traz o tempo total (base da
estimativa da execução completa), os testes instáveis e os `CE` de alvo (esperado 0). Os autores
conferem à mão a amostra (SC-003) e registram a decisão na metodologia antes de seguir.

## 4. Execução completa, pacote e conferência

```bash
docker compose run --rm sandbox python -m evaluation run           # retoma o piloto
docker compose run --rm app python -m evaluation report
docker compose run --rm app python -m evaluation package --set gpt  # um por conjunto
docker compose run --rm app python -m evaluation verify --set gpt --extracted data/evaluation/gpt
docker compose run --rm app python -m cli check --deep
```

Esperado: 600 combinações por conjunto; `claude` com 3 "sem suíte" (`discarded_manual`);
`verify` e `cli check --deep` com saída `0`.

## 5. Retomada

Interromper o `run` (Ctrl+C) no meio e rodá-lo de novo: nenhum problema é refeito além dos que
estavam em andamento, e `building/` fica vazio ao fim.
