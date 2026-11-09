# Implementation Plan: Avaliação das suítes contra AC, WAs e mutantes

**Branch**: `009-suite-evaluation` (sem branch própria; trabalho direto na `main`) | **Date**: 2026-11-04 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-suite-evaluation/spec.md`

## Summary

Novo pacote `src/evaluation/` (`python -m evaluation ...`, serviço `sandbox`) que, **por problema**,
compila uma única vez cada programa (`AC_ref`, 100 WAs, 100 mutantes; o AC primeiro, depois um alvo
de cada vez) e executa contra ele todas as suítes pedidas daquele problema: as finais dos 4 modelos e a 1ª tentativa do modelo local (5 **conjuntos
de avaliação**: `slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`). Contra o AC, todos os testes
rodam (veredito e saída real por teste); contra cada WA/mutante, **uma única passada** pelos testes
decide os dois oráculos ao mesmo tempo (declarado e corrigido pelo AC), parando quando os dois já
detectaram ou os testes acabaram. Erro de execução é repetido 2 vezes (FR-005a, FR-006a). O
resultado de cada conjunto × problema é gravado de uma vez (pasta montada à parte e renomeada),
o que dá retomada sem corrupção. `report` gera o resumo e a tabela consolidada (CSV); `package` e
`verify` seguem o padrão dos mutantes; o `cli check` ganha uma camada por conjunto. Paralelismo
entre problemas, um *slot* do motor por trabalhador, como nos mutantes (R14 da 002).

## Technical Context

**Language/Version**: Python 3.11 (imagem única do projeto; C++ por GCC 13.2 no motor existente)

**Primary Dependencies**: `pydantic` 2 (esquemas, já usado), biblioteca padrão (`csv`, `zipfile`,
`hashlib`, `concurrent.futures`); módulos internos `sandbox` (compilar/executar/julgar),
`dataset` (leitura do problema, `Engine`), `mutation` (leitura dos mutantes), `ai_clients`
(leitura de `suite.json`, `provenance.json` e das tentativas do modelo local) e `cli.consistency`
(portão). Nenhuma dependência nova.

**Storage**: arquivos em `data/evaluation/<conjunto>/` (JSON por cenário, por problema) e
`run.json` por conjunto; pacotes `data/evaluation_<conjunto>.zip` com manifesto e relatório em
`manifests/` (research R6, R7)

**Testing**: `pytest` (unidade com motor falso, integração no serviço `sandbox` com C++ real);
casos conhecidos exigidos pelo Princípio VI (research R10)

**Target Platform**: contêiner Linux do serviço `sandbox` (sem rede; `tmpfs` de 2 GB em `/sandbox`)

**Project Type**: pacote de linha de comando dentro do pipeline existente

**Performance Goals**: sem meta fixa; o tempo é medido no piloto (FR-021). Ordem de grandeza:
200 problemas × 201 compilações (uma vez por problema, R3) e, por problema, 15 suítes × 201 alvos

**Constraints**: limites de tempo/memória sempre dos metadados do problema; nenhum código de
terceiros fora do `sandbox`; no `tmpfs` do *slot* só ficam vivos o binário do AC e o do alvo
corrente (laço alvo → suítes, R4); nenhuma métrica calculada aqui (FR-020)

**Scale/Scope**: 2.400 combinações finais + 600 da 1ª tentativa; até 3.000 × 201 alvos julgados

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Como o plano cumpre | OK |
|---|---|---|
| I. Metodologia mutável | Divergências da seção 4 (curto-circuito só para WA/mutante, dois oráculos, repetição de erro, JSON por combinação + CSV consolidado em vez de só CSV) registradas na spec e na metodologia | ✅ |
| II. Reprodutibilidade | Sem aleatoriedade; ordem dos testes = ordem da suíte; `run.json` congela hashes de entrada e parâmetros, conferidos na retomada (R8); pacote + manifesto SHA-256 por conjunto; `cli check --deep` como portão (FR-002) e camada nova (FR-019) | ✅ |
| III. Sem estado nas IAs | Nenhuma chamada de IA | ✅ (n/a) |
| IV. Contratos explícitos | Esquemas Pydantic versionados em `src/evaluation/schemas/` (data-model.md); o CSV tem cabeçalho fixo e versão no relatório | ✅ |
| V. Sandbox | Só o motor existente, serviço `sandbox`, limites do `metadata.json` | ✅ |
| VI. Testa a si próprio | Casos conhecidos: AC sem curto-circuito, curto-circuito do alvo, dois oráculos, repetição de erro, "sem suíte", retomada (R10) | ✅ |
| VII. Idempotência | Gravação por conjunto × problema com pasta `building/` e `rename` atômico; trava de execução única (R5) | ✅ |
| VIII. Custo de IA | Sem chamada paga | ✅ (n/a) |
| IX. Simplicidade | Só os 5 conjuntos do experimento; a tentativa isolada é só a 1ª (`slm-attempt1`), sem opção para outras; sem abstração para outros juízes | ✅ |
| X. Revisão humana | Agente não commita; piloto com decisão dos autores (FR-021) | ✅ |
| XI. Documentação viva | Metodologia (seção 4 e histórico), `src/evaluation/README.md`, `README.md` da raiz, `docs/verificacao-consistencia.md` e `check_docs_sync.py` nas tarefas | ✅ |

Nenhuma violação; *Complexity Tracking* vazio. **Reavaliado depois da Fase 1**: o desenho
(data-model, contratos) não introduz nada novo frente à tabela acima.

## Project Structure

### Documentation (this feature)

```text
specs/009-suite-evaluation/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # Fase 0
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/
│   ├── cli.md           # comandos python -m evaluation
│   └── evaluation-api.md  # funções puras de julgamento (unidade testável)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/evaluation/
├── __init__.py
├── __main__.py          # CLI: run, report, package, verify
├── README.md            # template de docs/template-modulo.md
├── config.py            # conjuntos, nº de repetições (3), caminhos
├── schemas/             # Pydantic: run.json, resultado por cenário, relatório, manifesto
├── sources.py           # lê problema, mutantes, suítes (finais, provenance, 1ª tentativa)
├── judging.py           # AC sem curto-circuito; alvo em passada única, dois oráculos, repetição
├── problem_task.py      # um problema: compila 201 programas, avalia todas as suítes pedidas
├── runtime.py           # inline / pool de processos, um slot por trabalhador (padrão da 002)
├── store.py             # building/ + rename atômico, trava, run.json, retomada
├── report.py            # relatório JSON e tabela CSV consolidada
├── packaging.py         # zip + manifesto + verify
└── gate.py              # selfcheck do motor + cli check --deep nas camadas de entrada

src/cli/consistency.py   # + camadas evaluation_<conjunto>
tests/evaluation/        # unidade (motor falso) e integração (C++ real, marcador integration)
tests/cli/               # + testes das camadas novas
docs/verificacao-consistencia.md  # + linha e decisões da camada
```

**Structure Decision**: um pacote novo no padrão de `src/mutation/` (mesma divisão orquestração /
runtime / persistência / pacote), reaproveitando o motor sem alterá-lo. O julgamento por teste
fica em `evaluation/judging.py`, sobre `sandbox.runner.run_binary` e `sandbox.judge.judge_test`:
`run_suite` do motor continua intocado, porque o curto-circuito dele não serve ao AC nem aos dois
oráculos (R2).

## Complexity Tracking

Sem violações a justificar.
