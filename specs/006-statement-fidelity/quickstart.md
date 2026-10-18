# Quickstart: validar a conferência dos enunciados

**Feature**: `specs/006-statement-fidelity` | **Date**: 2026-10-18 | **Plan**: [plan.md](./plan.md)

Os formatos estão em [contracts/cli.md](./contracts/cli.md) e [data-model.md](./data-model.md).

## Nível 1 — testes (sem rede)

```text
docker compose run --rm sandbox pytest tests/dataset/statements
docker compose run --rm sandbox pytest        # a suíte inteira continua passando
```

## Nível 2 — os 5 do piloto (SC-001)

```text
docker compose run --rm app python -m dataset check-statements --problem 161_A --problem 1_B --problem 1000_B --problem 15_A --problem 102_B
```

Esperado no relatório (medido à mão em 2026-10-18):

| Problema | Esperado |
|---|---|
| `161_A` | 4 `lost_exponent`, 21 `lost_index` |
| `1_B` | 2 `lost_exponent` |
| `15_A` | 6 `lost_index` |
| `102_B` | 1 `lost_exponent` (`10^{100000}`) |
| `1000_B` | `faithful` |

As cópias do piloto em `data/cf_pilot/` podem ser copiadas para `data/statements/originals/`, para
não baixar de novo.

## Nível 3 — os 200 (SC-002, SC-003, SC-005)

1. `check-statements` sem opções: o primeiro download leva pelo menos 200 × 3 s; **medir o tempo**.
   Esperado: os 200 com estado; a linha de totais por tipo.
2. De novo, sem opções: nenhuma linha `fetch:` (nenhum acesso ao site) e um relatório idêntico.
   Conferir com `sha256sum manifests/statement_fidelity_report.json` antes e depois.
3. Comparar com a contagem antiga: dos 71 da metodologia, quantos têm `lost_exponent` no relatório,
   e quantos problemas novos aparecem. Registrar na metodologia.

## Nível 4 — corrigidos para revisão

```text
docker compose run --rm app python -m dataset correct-statements --output-dir data/statements/corrected
```

- abrir `data/statements/corrected/161_A.md`: `1 ≤ n, m ≤ 10^{5}`, `a_{i}`; o resto igual ao atual
  (`diff data/dataset/problems/161_A/enunciado.md data/statements/corrected/161_A.md` só mostra
  marcações);
- `git status` não mostra nada em `data/dataset/`, e `python -m dataset verify --extracted
  data/dataset` continua `OK`.

## Depois da validação

- registrar na metodologia (seções 1 e 3, histórico) os números do nível 3 e o tempo do download;
- carimbar os dois comandos no README do módulo `dataset` e fazer a revisão de prosa por `grep`;
- os autores decidem, com o relatório, se aplicam a correção (fora desta feature, E1).
