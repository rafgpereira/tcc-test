# Implementation Plan: Painel que conta a história dos resultados

**Branch**: `012-dashboard-storytelling` (sem branch própria; trabalho direto na `main`) | **Date**: 2026-11-12 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-dashboard-storytelling/spec.md`; roteiro
`docs/roteiro-painel.md`; skill *visual-storytelling-design* (passo 3 em
[contracts/narrative.md](contracts/narrative.md), passo 4 em R10).

## Summary

O painel (`src/dashboard/`, feature 011) passa de quatro páginas de exploração para três páginas
que contam a história: **O experimento** (contexto, abre primeiro), **A avaliação** (Combinação e
Comparações juntas, em abas) e **As métricas** (placar → seções por critério → guia de escolha →
tabelas oficiais). Os filtros ficam só na barra lateral, com o **rating** novo, e valem para tudo.

Toda a lógica de "quem ganhou" fica num módulo novo do pacote de métricas, **`metrics.story`**
(Python puro): valor de cada critério no recorte (pelas funções que já existem, `cuts.apply`,
`primary.table`, `iic.table` e `cost.csv`), placar, vencedor e segundo colocado com o estado do teste
estatístico lido de `stats.csv` (diferem, empate, não testado), título-conclusão por regra e cartões
do guia (R1, R3, R4, R5). O painel e o comando `python -m metrics figures` chamam as mesmas funções,
e as cinco figuras novas (`scoreboard`, `tradeoff`, `scenario_shift`, `iic_diverging`,
`choice_guide`) entram no pacote de métricas (FR-020). O `per_problem.csv` ganha a coluna `rating`,
e `metrics.cuts` e o comando ganham o corte por rating (R2); as demais tabelas não mudam. Cada
gráfico segue o contrato de narrativa (título = conclusão, denominador, no máximo 3 anotações,
destaque do líder, empates ditos como empates). A última etapa revisa o painel real com o checklist
da skill (R10).

## Technical Context

**Language/Version**: Python 3.11 (imagem única do projeto)

**Primary Dependencies**: as já fixadas no `uv.lock`: `streamlit` 1.66.1, `pandas` 3.0.6, `altair`,
`vl-convert-python`, `scipy` (só nos testes já existentes da 010); nenhuma dependência nova

**Storage**: leitura de `data/metrics/*.csv`, `data/evaluation/`, `data/dataset/`,
`data/mutants/`, `data/suites/`; escrita só pelo módulo de métricas (`compute`, `figures`,
`package`): `per_problem.csv` com `rating`, as figuras novas, o pacote e o manifesto

**Testing**: `pytest` no serviço `sandbox`: casos conhecidos de `metrics.story` (números do roteiro,
empates), propriedade "o líder tem o melhor valor" em recortes de exemplo, corte por rating,
determinismo das figuras novas, `AppTest` das três páginas (R9)

**Target Platform**: serviço `app` (painel e comando), navegador local; cópia pública no Streamlit
Community Cloud, que passa a ter as figuras novas no pacote reempacotado

**Project Type**: aplicação web local (painel) e biblioteca/CLI do pipeline

**Performance Goals**: página em menos de 10 s e filtro em menos de 5 s com a avaliação completa
(SC-004); o IIC por recorte sobre ~490 mil linhas de `detected_wa` é o ponto a medir (R8)

**Constraints**: o painel só lê (FR-019); nenhuma fórmula de métrica fora de `metrics` (FR-017);
nenhum teste estatístico novo (R3); `metrics.csv`, `iic.csv`, `stats.csv`, `cost.csv` e
`detected_wa.csv` com os mesmos valores depois do recálculo (R2)

**Scale/Scope**: 3 páginas, 5 figuras novas e 3 revistas, 6 critérios, 5 conjuntos, 3 cenários, 200
problemas

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Como o plano cumpre | OK |
|---|---|---|
| I. Metodologia mutável | As decisões D1–D4 e a emenda das figuras foram registradas na metodologia (seções 5.8 e 8) no mesmo ciclo | ✅ |
| II. Reprodutibilidade | Nenhuma dependência nova; `data/metrics.zip` é reempacotado com manifesto; as figuras PNG e SVG continuam iguais byte a byte | ✅ |
| III. Sem estado nas IAs | Nenhuma chamada de IA | ✅ (n/a) |
| IV. Contratos explícitos | `per_problem.csv` ganha uma coluna documentada; contratos em `contracts/api.md` e `contracts/narrative.md` | ✅ |
| V. Sandbox | Nada executa código de terceiros | ✅ |
| VI. Testa a si próprio | `metrics` é infraestrutura de métrica: `metrics.story` tem testes de casos conhecidos e de propriedade; as páginas têm `AppTest` | ✅ |
| VII. Idempotência | `compute`, `figures` e `package` continuam determinísticos; o painel não grava | ✅ |
| VIII. Custo de IA | Só lê o custo já registrado | ✅ (n/a) |
| IX. Simplicidade | Um módulo novo de funções puras; reaproveita cortes, tabelas, gráficos e exportação existentes; nenhum teste estatístico novo | ✅ |
| X. Revisão humana | Agente não commita; os textos dos títulos e a revisão final ficam com os autores | ✅ |
| XI. Documentação viva | Tarefas para `src/dashboard/README.md` (páginas, filtros, como ler), `src/metrics/README.md` (figuras, `--rating`, `rating`), `README.md` da raiz, metodologia (5.8, 5.9, 8), spec 011 (nota de que a 012 a substitui nas páginas) e `check_docs_sync.py` | ✅ |

Nenhuma violação. **Reavaliado depois da Fase 1**: o desenho (um módulo puro em `metrics`, uma
coluna nova, figuras novas no pacote) não acrescenta nada fora da tabela.

## Project Structure

### Documentation (this feature)

```text
specs/012-dashboard-storytelling/
├── plan.md               # este arquivo
├── research.md           # R1–R10
├── data-model.md         # Recorte, Criterio, Resultado, Titulo, Cartao
├── quickstart.md         # validação ponta a ponta
├── contracts/
│   ├── narrative.md      # contrato de narrativa por gráfico (skill, passo 3)
│   └── api.md            # metrics.story, cortes, figuras, comando, painel
├── checklists/requirements.md
├── sync-matrix.json      # D1–D4 → metodologia
└── tasks.md              # (/speckit-tasks)
```

### Source Code (repository root)

```text
src/metrics/
├── story.py              # NOVO: critérios, valores no recorte, placar, vencedor, títulos, guia
├── sources.py            # + coluna rating no per_problem
├── cuts.py               # + ratings
├── charts.py             # + placar, dispersão com região ideal, linhas entre cenários,
│                         #   barras divergentes, grade do guia; destaque do líder
├── figures.py            # + 5 figuras; 3 revistas com título-conclusão
├── __main__.py           # + --rating; package exige as figuras novas
└── README.md

src/dashboard/
├── app.py                # 3 páginas; filtro de rating na barra lateral
├── data.py               # + coluna rating; apply_filters(ratings=...)
├── views/
│   ├── experiment.py     # NOVO: página 1
│   ├── evaluation.py     # NOVO: página 2 (abas com combination e compare)
│   ├── metrics.py        # página 3 reorganizada; sem o seletor "Corte das tabelas"
│   ├── combination.py    # vira função chamada pela página 2
│   ├── compare.py        # idem
│   └── overview.py       # REMOVIDO (números vão para as páginas 1 e 2)
├── glossary.py           # + rating, critérios em linguagem de uso
└── README.md

tests/metrics/test_story.py           # NOVO
tests/metrics/test_sources_cuts_gate.py  # + rating
tests/metrics/test_dashboard_page.py  # figuras novas
tests/dashboard/test_pages.py         # 3 páginas, filtros, avisos
```

**Structure Decision**: tudo dentro dos dois pacotes existentes, `src/metrics/` (as contas e as
figuras) e `src/dashboard/` (as páginas); nenhum pacote novo.

## Ordem de implementação (para o `/speckit-tasks`)

1. `rating` em `sources`, `cuts` e `dashboard.data` (+ testes); `metrics compute` de novo e conferência
   de que as outras tabelas não mudaram.
2. `metrics.story` com testes (casos do roteiro, empates, propriedade do líder).
3. Gráficos e figuras novas (+ determinismo; skill `dataviz` para cores e marcas).
4. Página 3 (placar → seções → guia → tabelas), depois página 1, depois página 2.
5. `metrics figures` e `package`; `verify`; cópia pública conferida com o pacote novo.
6. Documentação (READMEs, metodologia 5.9 se algum número mudar, spec 011) e `check_docs_sync.py`.
7. Revisão do painel real com o checklist da skill (R10); relatório para os autores.

## Complexity Tracking

Nenhuma violação a justificar.
