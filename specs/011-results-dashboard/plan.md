# Implementation Plan: Dashboard de exploração dos resultados

**Branch**: `011-results-dashboard` (sem branch própria; trabalho direto na `main`) | **Date**: 2026-11-04 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-results-dashboard/spec.md`

## Summary

Novo pacote `src/dashboard/`, aberto por `python -m dashboard serve` no serviço `app` com a porta
publicada só em `127.0.0.1` (R2). É um painel Streamlit de várias páginas, **só de leitura**, sobre a
árvore de avaliação (`data/evaluation` por padrão). A camada de dados (`dashboard.data`) é Python
puro, sem Streamlit, e testável. Ela promove a prévia do piloto (`data/scratch/pilot_view.py`) a
código do projeto: lê os `<cenário>.json` concluídos validando-os pelo esquema da avaliação, monta
a tabela "uma linha por combinação" com a macrocategoria e guarda o resultado até o botão
"recarregar dados" (R4). As páginas são finas: filtram e exibem. O detalhe de uma combinação lê a
suíte (entrada e saída esperada) da pasta indicada pela origem gravada no resultado, e o código de
um alvo ao lado do `AC_ref` vem de um diff da biblioteca padrão (R6). A página de métricas oficiais
só verifica se as tabelas da feature 010 existem e, até lá, mostra o aviso (R7). Nada é gravado em
disco, e a telemetria do Streamlit fica desligada (R3).

## Technical Context

**Language/Version**: Python 3.11 (imagem única do projeto)

**Primary Dependencies**: `streamlit` (nova, fixada no `uv.lock`; versão com navegação de
várias páginas e `streamlit.testing.v1.AppTest`, R1); `pandas` 3.0.6 (já no lock, via `datasets`;
passa a ser declarada explicitamente); `difflib` (biblioteca padrão); os esquemas de
`evaluation.schemas.result`

**Storage**: nenhum; leitura de `data/evaluation/<conjunto>/problems/<id>/<cenário>.json`,
`data/dataset/problems/<id>/{metadata.json,AC_ref.cpp,WA_<n>.cpp}`,
`data/mutants/problems/<id>/Mutant_<n>.cpp` e `data/suites/...` (R5)

**Testing**: `pytest` na camada de dados, com árvores mínimas em `tmp_path`; um teste de fumaça de
cada página com `AppTest` (sem navegador) (R8)

**Target Platform**: contêiner do serviço `app`; navegador da máquina do autor em
`http://localhost:8501`

**Project Type**: aplicação web local (painel), dentro do pipeline existente

**Performance Goals**: abrir com as 3.000 combinações em menos de 1 min e responder a um filtro em
menos de 5 s (SC-002); medir no piloto e na execução completa

**Constraints**: só leitura (FR-003); uso local (FR-011, porta só em `127.0.0.1`, sem telemetria),
e, desde 2026-11-09, uma cópia pública no Streamlit Community Cloud (`src/dashboard/cloud.py`
descompacta os pacotes na primeira abertura; entrada e dependências mínimas em
`src/dashboard/public/`; num Python 3.11 limpo, a primeira abertura levou 39 s com 176 MB de pico);
nenhuma métrica oficial calculada (FR-004, FR-005); a raiz do contêiner é somente leitura, então a
configuração do Streamlit e o seu diretório de trabalho ficam no `/tmp` (R3)

**Scale/Scope**: até 3.000 arquivos de combinação (cerca de 600 mil alvos); 5 páginas

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Como o plano cumpre | OK |
|---|---|---|
| I. Metodologia mutável | O dashboard não muda o desenho experimental; registrado como ferramenta de exploração (metodologia, seção 8) | ✅ |
| II. Reprodutibilidade | Dependência nova fixada no `uv.lock`, roda na imagem do projeto; nada é gravado, então não há artefato novo nem manifesto | ✅ |
| III. Sem estado nas IAs | Nenhuma chamada de IA | ✅ (n/a) |
| IV. Contratos explícitos | Lê os resultados pelo esquema versionado da avaliação; a tabela base tem colunas fixas (data-model.md) | ✅ |
| V. Sandbox | Não executa código de terceiros; só lê arquivos de código para exibir | ✅ |
| VI. Testa a si próprio | Não é infraestrutura do experimento, mas a camada de dados tem testes de casos conhecidos e cada página tem um teste de fumaça (R8) | ✅ |
| VII. Idempotência | Só leitura; reabrir ou recarregar não altera nada | ✅ |
| VIII. Custo de IA | n/a | ✅ |
| IX. Simplicidade | Uma camada de dados e páginas finas; sem banco, sem servidor próprio; a página de métricas é só um aviso até a 010 | ✅ |
| X. Revisão humana | Agente não commita | ✅ |
| XI. Documentação viva | `src/dashboard/README.md`, `README.md` da raiz, `CLAUDE.md`, metodologia e `check_docs_sync.py` nas tarefas; o `pilot_view.py` provisório é aposentado | ✅ |

Nenhuma violação. **Reavaliado depois da Fase 1**: o desenho não introduz nada novo frente à tabela.

## Project Structure

### Documentation (this feature)

```text
specs/011-results-dashboard/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # Fase 0
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/
│   ├── cli.md           # python -m dashboard serve
│   └── pages.md         # o que cada página mostra e aceita
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/dashboard/
├── __init__.py
├── __main__.py          # `serve`: chama `streamlit run` com a configuração local (R2, R3)
├── README.md
├── config.py            # pastas padrão, porta, ordem dos conjuntos e cenários
├── data.py              # Python puro: combinações, testes de uma combinação, alvos, código, diff
├── app.py               # ponto de entrada do Streamlit: navegação, seletor de pasta, recarregar
└── views/
    ├── overview.py      # US1
    ├── combination.py   # US2 (detalhe, alvo, código lado a lado)
    ├── compare.py       # US3
    └── metrics.py       # US4 (aviso até a 010)

tests/dashboard/
├── test_data.py         # camada de dados
└── test_pages.py        # fumaça de cada página com AppTest

pyproject.toml / uv.lock # + streamlit, + pandas explícita
```

**Structure Decision**: um pacote novo com a separação dados × páginas. Só `data.py` tem lógica,
e ela é testável sem Streamlit; as páginas apenas filtram e exibem. O `data/scratch/pilot_view.py`
deixa de ser usado: a sua função `combinations()` passa a ser `dashboard.data.combinations()`.

## Complexity Tracking

Sem violações a justificar.
