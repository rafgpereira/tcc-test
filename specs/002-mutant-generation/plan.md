# Implementation Plan: Geração de Mutantes

**Branch**: `002-mutant-generation` | **Date**: 2026-09-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-mutant-generation/spec.md`

## Summary

O módulo lê o dataset já extraído, validado e empacotado pelo módulo `001-dataset-extraction`
(verificado contra `manifests/dataset.manifest.json` antes de qualquer trabalho), identifica
sítios de mutação em cada `AC_ref.cpp` por análise sintática real (AST, `tree-sitter-cpp`),
aplica o conjunto de operadores de Offutt et al. (ROR/AOR/LCR completos + ABS + UOI), valida cada
candidato reutilizando sem alteração o motor do módulo `sandbox`, e persiste até 100 mutantes
válidos e distintos por problema — recorrendo a combinações determinísticas de ordem superior
quando a primeira ordem não basta. Não usa nenhuma operação aleatória. O resultado de
desenvolvimento nunca é versionado; o resultado da execução final que sustenta os números do TCC
é compactado (`data/mutants.zip`) e versionado com manifesto próprio, pela mesma razão que já
levou a versionar o dataset (Constitution, Princípio II, emenda 1.6.0).

Abordagem técnica (detalhes em [research.md](./research.md)):

- **Identificação de sítios** em `src/mutation/sites.py`: percorre a AST de `tree-sitter-cpp` em
  ordem pré-fixa; sítios ROR/AOR/LCR são o campo `operator` de nós `binary_expression` cujo
  operador pertence à categoria correspondente; sítios ABS/UOI são os campos `left`/`right`
  desses mesmos nós (evita precisar de informação de tipos — verificado empiricamente, ver
  research.md).
- **Aplicação de operadores** em `src/mutation/operators.py`: cada operador é uma função pura
  `(source: str, site: Site) -> str` que substitui o intervalo de bytes do sítio pelo texto
  mutado, preservando o resto do arquivo byte a byte.
- **Validação** em `src/mutation/validation.py`: reutiliza o motor do módulo `sandbox` sem
  alteração, pelo mesmo par `compile`/`run_suite` (`dataset.validation.engine.Engine`) que o
  módulo de dataset já usa e testa com motor falso — em vez de `sandbox.judge_source`, que
  compila e roda uma vez só e não permitiria reexecutar o mesmo binário; roda a suíte oficial do
  problema (`testes.json`); aplica os critérios de FR-005 (unicidade, compilação, limites,
  equivalência) e a confirmação de 6 execuções concordantes de FR-007 (o mesmo binário,
  compilado uma vez) só para candidatos que sobrevivem ao primeiro filtro (barato). Ver
  research.md, R10.
- **Ordem superior** em `src/mutation/higher_order.py`: combina pares (depois trios) de sítios
  de primeira ordem já válidos, em ordem determinística fixa, até fechar 100 ou esgotar o
  orçamento de tentativas (a ser medido por um piloto durante a implementação, no mesmo espírito
  do piloto do módulo de dataset).
- **Empacotamento** em `src/mutation/packaging.py`: espelha `dataset.persistence`/`dataset.integrity`
  — `data/mutants.zip` determinístico + `manifests/mutants.manifest.json` (SHA-256 por arquivo) +
  `manifests/mutation_report.json`, gerados só sob comando explícito, nunca durante o
  desenvolvimento iterativo.

## Technical Context

**Language/Version**: Python 3.11 (mesmo ambiente do projeto, `uv`); nenhuma mudança na cascata
de compilação C++ (reutiliza o motor do módulo `sandbox` sem alteração).

**Primary Dependencies**: `tree-sitter` 0.26.x e `tree-sitter-cpp` 0.23.x (parsing sintático,
sem exigir resolução de headers — verificado empiricamente nesta fase, ver research.md);
`pydantic` 2.x (schemas, já uma dependência do projeto); biblioteca padrão (`hashlib`,
`zipfile`, `itertools` para combinações de ordem superior). Reaproveita `sandbox.compiler`/`sandbox.judge` (via
`dataset.validation.engine.Engine`), `sandbox.types.ExecutionLimits`, `dataset.schemas.common` e
`dataset.integrity` sem alteração.

**Storage**: arquivos. Mutantes de desenvolvimento em `data/mutants/` (nunca versionado, análogo
a `data/work/`); pacote da execução final em `data/mutants.zip` (versionado sob condição, ver
Constitution emenda 1.6.0) com manifesto em `manifests/mutants.manifest.json` e relatório em
`manifests/mutation_report.json`.

**Testing**: `pytest` no serviço `sandbox` (compila e executa C++, como o módulo de dataset);
suíte própria para: detecção de sítios (fixtures de código C++ conhecido, inclusive o caso real
`vector<pair<int,string>>` que não deve gerar sítio, e o caso `x >> 1` que deve), aplicação de
cada operador, deduplicação/equivalência, geração de ordem superior e regra de parada,
empacotamento/manifesto (mesmos casos de teste do módulo de dataset: byte alterado, arquivo
removido, arquivo extra).

**Target Platform**: o mesmo ambiente Docker já fixado (`gcc:13.2.0`, Debian 12) — nenhuma nova
imagem, nenhuma segunda cadeia de compiladores (decisão D1: descartado o uso de LLVM/Clang via
Mull).

**Project Type**: módulo de biblioteca + CLI dentro do pipeline Python já existente
(`src/mutation/`, espelhando `src/dataset/`).

**Performance Goals**: sem meta fixada a priori — a exemplo do módulo de dataset, medida por um
piloto durante a implementação (quantos problemas completam com só primeira ordem, tempo médio
por problema, orçamento de tentativas de ordem superior necessário). Ver research.md, "Risco de
desempenho da busca combinatória de ordem superior".

**Constraints**: sem seed (Clarifications, D6 revisado); sem uso de ACs adicionais do dataset de
origem (D4); sem alteração do motor de execução nem do schema do pacote do dataset; mutantes de
desenvolvimento nunca versionados; pacote da execução final só compactado sob comando explícito.

**Scale/Scope**: até 200 problemas × 100 mutantes = 20.000 arquivos na execução final (mesma
ordem de grandeza dos 20.000 arquivos `WA_*.cpp` já no dataset); estimativa de pesquisa: ≥ 75%
dos problemas fecham a cota inteiramente de primeira ordem (ver spec, SC-003).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.6.0.

| Princípio | Verificação | Resultado |
|---|---|---|
| I. Metodologia mutável, divergências registradas | Divergências D1–D6 registradas na spec e propagadas para `docs/metodologia-referencia.md` §2, com revisão em `/speckit.clarify` (D4–D6 corrigidos) | PASS |
| II. Reprodutibilidade | Sem seed (vacuamente satisfeito, D6); dependências novas serão pinadas no `uv.lock`; gate de manifesto contra o dataset antes de rodar (FR-010); pacote da execução final versionado com manifesto próprio, pela emenda 1.6.0 | PASS |
| III. Sem estado nas chamadas de IA | Este módulo não chama IA | N/A |
| IV. Contratos explícitos e versionados | `schema_version` em `mutants.manifest.json` e `mutation_report.json` (Pydantic, [data-model.md](./data-model.md)) | PASS |
| V. Execução isolada e segura | Nenhuma sandbox nova: reutiliza o motor do `sandbox` (compilação e execução da suíte) sem alteração; limites sempre lidos de `metadata.json` do problema | PASS |
| VI. O pipeline testa a si próprio | Suíte própria para sítios, operadores, ordem superior, empacotamento/manifesto (ver Testing acima) | PASS (a construir na implementação) |
| VII. Idempotência e retomada | Cada problema processado em `building/` e movido atomicamente para `data/mutants/`, mesmo padrão do módulo de dataset (ver research.md); interrupção não duplica nem corrompe | PASS (desenho; a verificar como SC na implementação) |
| VIII. Observabilidade de custo de IA | Sem chamadas pagas | N/A |
| IX. Simplicidade | Mutador leve próprio sobre `tree-sitter`, sem adotar o Mull (motor de execução único preservado); sem generalizar para outras linguagens ou datasets | PASS |
| X. Revisão humana | Processo, não código; nenhum commit feito pelo agente nesta sessão (`git status` só mostra `modified`/`untracked`) | PASS |
| XI. Documentação viva | `docs/metodologia-referencia.md` §2, §5.2, §7, §8 já atualizados nesta sessão; README raiz atualizado; README de `src/mutation/` fica pendente até a implementação (Princípio XI, mesma regra do módulo de dataset) | PASS (documentação de módulo pendente até implementar, como já é o caso) |

Convenções técnicas: Python 3.11+, `pytest`, `ruff`/`black`, nomes de código em inglês — sem
divergência nova.

**Resultado do portão inicial**: PASS. Sem violação a justificar.

## Fundação reutilizada (não recriada)

Este módulo **não** cria uma nova fundação — reutiliza integralmente a já decidida em
`specs/001-dataset-extraction/plan.md` (imagem `gcc:13.2.0` fixada por dígito, `uv`/`uv.lock`,
layout `src/<modulo>/`, dois serviços do Compose). A única mudança de infraestrutura é uma nova
dependência Python (`tree-sitter` + `tree-sitter-cpp`), adicionada com `uv add` na implementação
— não exige nova imagem base nem segundo compilador.

## Project Structure

### Documentation (this feature)

```text
specs/002-mutant-generation/
├── plan.md              # este arquivo
├── research.md          # Fase 0
├── data-model.md         # Fase 1
├── quickstart.md         # Fase 1
├── contracts/            # Fase 1
│   ├── cli.md
│   ├── mutation-api.md
│   └── file-formats.md
└── tasks.md              # Fase 2 (/speckit-tasks, não criado aqui)
```

### Source Code (repository root)

```text
src/
├── dataset/              # já existente, sem alteração
├── sandbox/               # já existente, sem alteração (reutilizado sem modificação)
└── mutation/              # ESTE módulo
    ├── __init__.py
    ├── __main__.py        # CLI: python -m mutation <comando> (generate; package, verify; report)
    ├── config.py          # constantes (cota 100, 6 execuções, ordem máxima 3, caminhos); sem seed
    ├── types.py           # Site, MutationOperator, DiscardReason, MutantCandidate, Mutant, Selection...
    ├── dataset_gate.py    # portão de consistência: data/dataset contra o manifesto do dataset (FR-010)
    ├── sites.py           # travessia da AST, descoberta de sítios (tree-sitter-cpp)
    ├── operators.py       # ROR, AOR, LCR, ABS, UOI — funções puras de substituição
    ├── candidates.py      # geração (preguiçosa) de candidatos de 1ª ordem
    ├── validation.py      # reutiliza o motor do sandbox; critérios de FR-005/FR-007
    ├── higher_order.py    # (US2) combinação em pares/trios, ordem determinística, regra de parada
    ├── orchestrator.py    # select_mutants: primeira ordem, depois ordem superior (US2), alerta
    ├── persistence.py     # gravação em data/mutants/ (building/ + move atômico) e generation.json
    ├── packaging.py       # (US3) data/mutants.zip + manifests/mutants.manifest.json
    ├── integrity.py       # (US3) verify
    ├── report.py          # (US4) manifests/mutation_report.json
    └── schemas/
        ├── generation.py  # generation.json por problema (não empacotado)
        ├── manifest.py    # (US3)
        └── report.py      # (US4)

tests/
├── dataset/               # já existente
├── sandbox/                # já existente
└── mutation/               # espelha src/mutation/
    ├── conftest.py         # motor falso, suíte mínima, construtor de dataset de teste
    ├── fixtures/189_C/     # problema real denso (AC_ref.cpp, testes.json, metadata.json)
    ├── test_types.py, test_dataset_gate.py, test_sites.py, test_operators.py
    ├── test_candidates.py, test_validation.py, test_validation_integration.py
    ├── test_persistence.py, test_orchestrator.py, test_uniqueness.py, test_cli_generate.py
    └── (US2 a US4) test_higher_order.py, test_exclusion_alert.py, test_packaging.py,
        test_manifest.py, test_verify.py, test_report.py
```

**Structure Decision**: módulo único `src/mutation/`, no mesmo padrão de `src/dataset/` —
biblioteca + CLI (`__main__.py`), sem pacote `common/` nem abstração para linguagens além de
C++ (Princípio IX). Não há opção de estrutura alternativa a documentar (o projeto já fixou o
layout `src/<modulo>/` na feature 001).

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

Nenhuma violação a justificar — a tabela fica vazia intencionalmente.

## Constitution Check (pós-desenho da Fase 1)

Reavaliado depois de `research.md`, `data-model.md`, `quickstart.md` e `contracts/`: nenhum
gate mudou de resultado. Em particular, a Fase 1 tornou concreto o que na primeira passagem
era apenas uma promessa: o Princípio IV (contratos versionados) tem agora `schema_version`
definido para `mutants.manifest.json` e `mutation_report.json` ([data-model.md](./data-model.md),
[contracts/file-formats.md](./contracts/file-formats.md)); o Princípio VI (testes) tem agora uma
lista concreta de garantias a cobrir ([contracts/mutation-api.md](./contracts/mutation-api.md),
seção "Garantias"); o Princípio VII (idempotência) tem o desenho de `building/` + movimento
atômico (R5). **Resultado**: PASS, sem violação nova.
