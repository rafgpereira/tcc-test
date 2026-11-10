# Implementation Plan: Métricas de avaliação

**Branch**: `010-metrics` (sem branch própria; trabalho direto na `main`) | **Date**: 2026-11-09 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-metrics/spec.md`

## Summary

Novo pacote `src/metrics/` (`python -m metrics compute|figures|package|verify`, serviço `app`, sem
executar código de terceiros). O `compute` lê três fontes, todas versionadas:

- o `results.csv` de cada um dos 5 conjuntos de avaliação, uma linha por combinação × alvo, que
  já traz tudo o que as métricas pedem (R1);
- a macrocategoria em `metadata.json`;
- o custo, os *tokens* e o tempo dos relatórios e das tentativas de geração (R5).

A partir disso, ele monta uma **tabela por problema** (conjunto × cenário × problema). Todas as
métricas são funções puras dela: TDF, MS e TFP como médias por problema, IIC por operações de
conjunto, e os testes pareados pelos 200 problemas. O resultado são cinco tabelas CSV em
`data/metrics/`, o lugar que o dashboard já espera: por problema, métricas, IIC, estatística e
custo.

As figuras (US6) são funções de desenho que recebem a tabela por problema e filtros, recalculam
pelas mesmas funções de métrica e gravam PNG/PDF determinísticos, com o filtro e a fonte no
rodapé e no nome (R7). O dashboard chama essas mesmas funções na página de métricas.
**Emenda de 2026-11-09 (Milena)**: as figuras passaram a ser o gráfico Altair do painel
(`metrics/charts.py`), exportado pelo vl-convert em PNG, SVG e PDF; o matplotlib saiu do projeto
(R7).

`package`/`verify` empacotam `data/metrics/` (tabelas e figuras padrão) com manifesto. A seção 5
da metodologia é reescrita com a proposta confirmada (R9).

## Technical Context

**Language/Version**: Python 3.11 (imagem única do projeto)

**Primary Dependencies**: `pandas` 3.0.6 e `numpy` 2.4.6 (já no lock); **novas** `scipy` (Friedman,
Wilcoxon pareado, teste binomial exato para o McNemar) e `matplotlib` (figuras; trocado por `altair` + `vl-convert-python` na emenda de 2026-11-09), fixadas no
`uv.lock` (R3, R7); Holm-Bonferroni e A12 de Vargha-Delaney implementados à mão (fórmulas curtas,
testadas contra valores conhecidos)

**Storage**: entrada `data/evaluation/<conjunto>/results.csv`, `data/dataset/problems/*/metadata.json`,
`manifests/<modelo>_generation_report.json` e as tentativas de `data/suites/`; saída
`data/metrics/*.csv` e `data/metrics/figures/`, pacote `data/metrics.zip` + manifesto (R8)

**Testing**: `pytest` com casos conhecidos (Princípio VI: "MS com DM=0 e M=100 deve retornar 0.0"
é exatamente o tipo de teste exigido), tabelas pequenas montadas à mão e conferência contra
`evaluation report` (R10)

**Target Platform**: serviço `app`; o dashboard importa as funções de figura

**Project Type**: pacote de linha de comando + biblioteca usada pelo dashboard

**Performance Goals**: `compute` em poucos minutos sobre ~3 milhões de linhas de `results.csv`
(5 × 600 × 200 + sem suíte); medido na execução

**Constraints**: determinismo (mesmas entradas → mesmos bytes, inclusive PNG/SVG; o PDF do vl-convert não, e fica fora do pacote); nenhuma
conversão do custo do modelo local para US$; nada calculado sem o portão de consistência

**Scale/Scope**: 5 conjuntos × 3 cenários × 200 problemas; ~40 comparações estatísticas por métrica

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Como o plano cumpre | OK |
|---|---|---|
| I. Metodologia mutável | A seção 5 é reescrita com a proposta confirmada, e as divergências da implementação são registradas (R9) | ✅ |
| II. Reprodutibilidade | Funções puras, ordem fixa, figuras sem data embutida; dependências novas no lock; pacote com manifesto e `verify` | ✅ |
| III. Sem estado nas IAs | Nenhuma chamada de IA | ✅ (n/a) |
| IV. Contratos explícitos | Cada tabela tem colunas fixas e esquema validado na escrita e na leitura (data-model.md) | ✅ |
| V. Sandbox | Não executa código de terceiros | ✅ |
| VI. Testa a si próprio | Módulo de infraestrutura citado nominalmente ("cálculo de métricas TDF/MS/TFP"): testes de casos conhecidos para cada métrica, IIC, testes estatísticos e figuras (R10) | ✅ |
| VII. Idempotência | `compute` reescreve `data/metrics/` inteiro de forma atômica (pasta temporária + troca) | ✅ |
| VIII. Custo de IA | Só lê custos já gravados | ✅ |
| IX. Simplicidade | Uma tabela por problema como base de tudo; sem banco; figuras como funções simples | ✅ |
| X. Revisão humana | Agente não commita | ✅ |
| XI. Documentação viva | Metodologia (seções 0, 5, limitações, histórico), README do módulo e da raiz, `CLAUDE.md`, `check_docs_sync.py`, `sync-matrix.json` | ✅ |

Nenhuma violação. **Reavaliado depois da Fase 1**: sem mudança.

## Project Structure

### Documentation (this feature)

```text
specs/010-metrics/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── cli.md           # compute, figures, package, verify
│   └── api.md           # funções de métrica e de figura (usadas pelo dashboard)
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/metrics/
├── __init__.py
├── __main__.py          # compute, figures, package, verify
├── README.md
├── config.py            # conjuntos, cenários, α = 0,05, pastas, colunas
├── sources.py           # results.csv → tabela por problema; macrocategoria; custo/tokens/tempo
├── primary.py           # TDF, MS, TFP (+ visão com suíte), TC, TDF*, MS*, Δ, TFP por teste/causa, densidade
├── iic.py               # IIC agregado e visão por problema
├── cost.py              # CPD, tokens, tempo
├── stats.py             # Friedman, Wilcoxon, McNemar exato, Holm, A12/Cliff
├── cuts.py              # filtros (macrocategoria, status, conjuntos, cenários)
├── tables.py            # monta e grava as cinco tabelas (esquema validado)
├── figures.py           # dados de cada figura (filtros), subtítulo, nome e exportação (vl-convert)
├── charts.py            # o gráfico Altair de cada figura, por tema (claro/escuro)
├── gate.py              # cli check --deep nas camadas lidas
└── packaging.py         # zip + manifesto + verify

src/dashboard/views/metrics.py   # passa a mostrar as tabelas e as figuras (com filtros e download)
tests/metrics/                    # casos conhecidos
```

**Structure Decision**: as métricas são funções puras sobre um `DataFrame` por problema. É o que
permite o dashboard e o comando de figuras recalcularem um corte filtrado pelas **mesmas** funções,
sem duplicar nenhuma conta.

## Complexity Tracking

Sem violações a justificar.
