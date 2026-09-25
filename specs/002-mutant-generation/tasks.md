# Tasks: Geração de Mutantes

**Input**: Design documents from `/specs/002-mutant-generation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md); Constitution v1.6.0 (`.specify/memory/constitution.md`)

**Tests**: INCLUÍDOS. A Constitution (Princípio VI) exige suíte própria para este módulo, e o
pedido explícito desta rodada ("robustez e confiabilidade", "garantir que os mutantes são
diferentes entre si") só é verificável com testes dedicados — ver T020 e T029. Em cada história,
os testes vêm antes da implementação: escreva-os e confirme que **falham** antes de implementar.

**Organization**: tarefas agrupadas por história de usuário (US1 a US4, na ordem de prioridade da
spec) para implementação e teste independentes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec (US1 a US4); só nas fases de história
- Caminhos relativos à raiz do repositório
- **Onde rodar**: nada de C++ de terceiros roda no host. Comandos usam `docker compose run --rm
  app ...` (com rede; nunca compila/executa C++) ou `docker compose run --rm sandbox ...` (sem
  rede; obrigatório para tudo que compila, executa C++, ou roda `pytest`)

## Regras que valem para TODAS as tarefas (Constitution, Princípio XI)

- **📌 PROPAGAR**: uma tarefa marcada com 📌 produz dado medido ou decisão nova. Ela **só está
  concluída** depois de a informação ser escrita, **na própria tarefa**, em
  `docs/metodologia-referencia.md` (seção certa + nova linha datada na seção 8) **e** nos
  artefatos da feature que ela afeta (`spec.md`, `plan.md`, `research.md`), com data e fonte.
  Não existe tarefa separada de "atualizar a metodologia depois".
- **Documentação como critério de aceite (verificável)**: a tarefa de README de módulo segue
  [`docs/template-modulo.md`](../../docs/template-modulo.md) (seis campos) e só termina quando
  `docker compose run --rm app python scripts/check_docs_sync.py --module src/mutation --cli
  "python -m mutation" --cli-owner src/mutation` sai com `0` (checagens C1 a C3, C7). Todo
  comando documentado nasce `pendente` na tabela "Comandos verificados" e só passa a "verificado"
  (data e revisão git) na tarefa que o executa de verdade sobre dados reais; `Status: implementado`
  não pode conviver com uma linha `pendente`. **Revisão do carimbo**: saída de `git rev-parse
  --short=7 HEAD` no host, obtida depois de commitar e antes de rodar o comando, com `+dirty` se
  `src/`, `scripts/`, `pyproject.toml`, `uv.lock`, `Dockerfile` ou os arquivos do compose tiverem
  alteração não commitada; o fechamento (`--closing`) rejeita `+dirty`.
- **Restrições citadas literalmente** de [data-model.md](./data-model.md) e
  [contracts/](./contracts/) fazem parte do aceite; não as reinterprete.
- **Sem seed neste módulo** (Clarifications, D6): ao contrário de outros módulos do projeto,
  nenhuma tarefa aqui usa `random` nem qualquer gerador pseudoaleatório — toda ordem vem da
  travessia da AST (research.md, R3). Um `grep -rn "^import random\|from random"
  src/mutation/` que retorne algo é uma falha de aceite, não um detalhe de estilo.
- Nenhum limite de tempo/memória de problema é constante no código (Constitution, Princípio V) —
  este módulo nunca define seus próprios limites, só repassa os já lidos por `dataset`/`sandbox`.

## Path Conventions

Novo pacote `src/mutation/` (espelha `src/dataset/`) e `tests/mutation/`; reutiliza sem
alteração `src/sandbox/` e `src/dataset/integrity/` (via import). Fundação do repositório já
existe (`pyproject.toml`, `uv.lock`, `Dockerfile`, `docker-compose.yml`) — só `uv add` de duas
dependências novas, sem tocar no `Dockerfile` nem no compose (plan.md, "Fundação reutilizada").

---

## Phase 1: Setup

**Purpose**: dependência nova e esqueleto do pacote — nada de lógica de mutação ainda.

- [X] T001 Add `tree-sitter>=0.26,<0.27` and `tree-sitter-cpp>=0.23,<0.24` to `[project].dependencies`
  in `pyproject.toml`; run `uv lock` and `uv lock --check`; rebuild the image
  (`docker compose build`) and confirm `docker compose run --rm app python -c "import
  tree_sitter, tree_sitter_cpp; print('ok')"` prints `ok` (research.md, R7)
- [X] T002 [P] Create the package skeleton: empty `src/mutation/__init__.py`,
  `tests/mutation/__init__.py` (or a `conftest.py` re-exporting fixtures from
  `tests/conftest.py` if the existing one needs a `mutation`-specific fixture); confirm
  `pytest --collect-only tests/mutation` runs without error (empty collection is fine at this
  point)
- [X] T003 [P] Update `.gitignore`: add `!data/mutants.zip` right after the existing
  `!data/dataset.zip` line (Constitution, Princípio II, emenda 1.6.0 — o pacote da execução
  final de mutantes é a única outra exceção a "arquivos soltos nunca versionados"; `data/mutants/`
  de desenvolvimento continua coberto pela regra geral `data/*`). Verify with `git check-ignore -v
  data/mutants/1000_B/Mutant_1.cpp data/mutants.zip`: the first is ignored, the second is not
- [X] T004 [P] Create `src/mutation/README.md` from `docs/template-modulo.md` (six fields, in
  order); header states `> **Status**: não implementado`; (a) uma frase (gera até 100 mutantes
  por problema a partir do `AC_ref`, para medir o Escore de Mutação); (b) a (f) MAY dizer "a
  preencher pela história correspondente" por enquanto — cada história completa sua parte
  (regra de "Documentação como critério de aceite" acima); confirm the root `README.md` row for
  `src/mutation/` (already updated in `/speckit.specify`) still points to this file

**Checkpoint**: `docker compose run --rm app python -c "import tree_sitter, tree_sitter_cpp"`
funciona; `src/mutation/` importável.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: tipos, constantes, o portão de consistência com o dataset (FR-010), e a extensão da
ferramenta de sincronização de documentação para reconhecer uma segunda CLI — usados por TODAS
as histórias.

**⚠️ CRITICAL**: nenhuma história começa antes desta fase.

- [X] T005 [P] Write tests in `tests/docs/test_docs_sync.py` (novos casos, sem remover os já
  existentes do módulo `dataset`): com um README de módulo fixture documentando `python -m
  mutation generate`, chamar `main(["--module", "<tmp>/src/mutation", "--cli", "python -m
  mutation", "--cli-owner", "<tmp>/src/mutation"])` e confirmar C2 passa quando o subcomando
  existe na CLI falsa e falha quando não existe (mesmo comportamento hoje só coberto para
  `python -m dataset`); confirmar que rodar com `--cli "python -m dataset"` (o padrão) continua
  funcionando exatamente como antes (teste de regressão — a generalização não pode quebrar C2
  para o módulo de dataset)
- [X] T006 Implement the generalization in `scripts/check_docs_sync.py` (makes T005 pass): hoje
  `CLI_SUB_RE = re.compile(r"python -m dataset\s+([A-Za-z][\w-]*)")` é fixo; troque por uma
  função `cli_subcommand_pattern(cli: list[str]) -> re.Pattern` que deriva o nome do módulo do
  argumento `--cli` (o token depois de `-m`) e monta o regex dinamicamente; use essa função em
  `documented_subcommands`, e troque as duas mensagens de `Finding` que hoje têm o texto literal
  `python -m dataset` (linhas citando `f"documents \`python -m dataset {sub}\`..."` e `f"...cita
  \`python -m dataset {sub}\`..."`) para usar o comando de `ctx.cli` real. Sem mudança de
  comportamento quando `--cli` não é passado (mantém o padrão `python -m dataset`)
- [X] T007 [P] Write tests in `tests/mutation/test_types.py`: `MutationOperator` tem exatamente
  `ROR, AOR, LCR, ABS, UOI`; `DiscardReason` tem exatamente `DUPLICATE, COMPILE_ERROR, TLE, MLE,
  RE, EQUIVALENT, UNSTABLE` (data-model.md, "Registro de descarte"); `Site` é congelado/imutável
  e comparável por `(node_type, start_byte, end_byte, kind)`; `Site.kind` tem exatamente
  `OPERATOR, OPERAND_LEFT, OPERAND_RIGHT` (data-model.md, "Sítio de mutação")
- [X] T008 Implement `src/mutation/config.py` (makes part of later tests pass): `MUTANTS_PER_PROBLEM
  = 100`; `MUTANT_FILE_PREFIX = "Mutant_"` (R6 — nunca `WA_`, para não confundir com falhas
  reais); `STABILITY_RUNS = 6` (FR-007, Clarifications); `HOM_MAX_ORDER = 3`; work-dir paths sob
  `data/mutants/` (`building/`, `problems/`); `MANIFEST_PATH = manifests/mutants.manifest.json`;
  `REPORT_PATH = manifests/mutation_report.json`; nenhuma constante de seed (D6)
- [X] T009 Implement `src/mutation/types.py` per [contracts/mutation-api.md](./contracts/mutation-api.md)
  ("Tipos") and [data-model.md](./data-model.md): `Site` (`kind`, `node_type`, `start_byte`,
  `end_byte`, `discovery_index`, `eligible_operators`), `MutationOperator` enum, `DiscardReason`
  enum, `MutantCandidate` (`problem_id`, `sites`, `operators`, `source`), `ValidationOutcome`
  (makes T007 pass)
- [X] T010 [P] Write tests in `tests/mutation/test_dataset_gate.py`: `verify_dataset(root:
  Path) -> None` levanta `DatasetMismatchError` (com a lista de arquivos divergentes) quando
  `data/dataset` não corresponde a `manifests/dataset.manifest.json` (byte alterado, arquivo
  removido, arquivo extra — os mesmos 3 casos já usados para o dataset); não levanta nada sobre
  uma árvore íntegra
- [X] T011 Implement `src/mutation/dataset_gate.py` (makes T010 pass; FR-010): reaproveita
  `dataset.integrity.verify` sem reimplementar a lógica de hash — só adapta o resultado para
  `DatasetMismatchError` quando há qualquer `changed`/`missing`/`extra`
- [X] T012 Create `src/mutation/__main__.py` skeleton (`python -m mutation`) with `argparse`, a
  subcommand registry and the same common exit codes já usados pelo `dataset` (`0` sucesso, `1`
  falha de verificação, `2` uso incorreto, `3` falha de infraestrutura, `130` interrompido — ver
  [contracts/cli.md](./contracts/cli.md)); registers no subcommand yet (cada história adiciona o
  seu: US1 `generate`; US3 `package`, `verify`; US4 `report`), so every story stays independently
  testable
- [X] T013 Create `specs/002-mutant-generation/sync-matrix.json` (`schema_version: 1`, mesmo
  formato de `specs/001-dataset-extraction/sync-matrix.json`) with rows for D1–D6 and the needles
  abaixo; run `docker compose run --rm app python scripts/check_docs_sync.py --feature
  specs/002-mutant-generation --only C5` and fix any mismatch

  | ID | Termos que devem aparecer na metodologia |
  |---|---|
  | D1 | `tree-sitter`, `Mull` |
  | D2 | `Offutt` |
  | D3 | `sem busca` |
  | D4 | `sem ACs adicionais` |
  | D5 | `data/mutants.zip` |
  | D6 | `Sem seed própria` |

**Checkpoint**: `docker compose run --rm sandbox pytest tests/mutation/test_types.py
tests/docs/test_docs_sync.py` passa; `python -m mutation --help` roda;
`check_docs_sync.py --feature specs/002-mutant-generation --only C5` sai `0`; histórias podem
começar.

---

## Phase 3: User Story 1 - Gerar mutantes válidos a partir do `AC_ref` (Priority: P1) 🎯 MVP

**Goal**: para um problema cujo `AC_ref.cpp` tem sítios de mutação suficientes, produzir até 100
mutantes de primeira ordem válidos, distintos entre si, e comprovadamente sem tocar literais de
string/char nem comentários.

**Independent Test**: rodar `generate --problem <id>` sobre um problema real cujo `AC_ref.cpp` já
tenha ≥ 100 sítios de primeira ordem (medido na pesquisa: uso o conjunto completo de operadores);
confirmar 100 arquivos `Mutant_<n>.cpp`, todos com hash distinto entre si e do original.

### Tests for User Story 1 ⚠️ (escrever primeiro; devem FALHAR)

- [X] T014 [P] [US1] Write tests in `tests/mutation/test_sites.py` usando fixtures de código C++
  reais e sintéticos (research.md, R1): `find_sites` sobre um trecho com
  `vector<pair<int, string>> mb;` (caso real de `175_B/AC_ref.cpp`) não retorna nenhum sítio para
  esse `>>`; sobre `x >> 1;` retorna um sítio `OPERATOR` de categoria ROR/AOR (é aritmético neste
  contexto); sobre `"a<b>>c"` (string) e `// ... < e >> ...` (comentário) no mesmo arquivo, nenhum
  sítio cai dentro desses nós; sobre `-x`, `!y`, `++x`, `x--`, todos geram sítio `UOI`
  (`update_expression` distinto de `unary_expression`, ambos cobertos); a ordem retornada é a
  ordem de descoberta pré-ordem (R3) — duas chamadas com o mesmo texto devolvem a mesma lista, na
  mesma ordem
- [X] T015 [P] [US1] Write tests in `tests/mutation/test_operators.py`: ROR sobre um sítio `<`
  gera as 5 variantes legais (`<=, >, >=, ==, !=`), nunca gera `<` de volta; AOR sobre `+` gera as
  demais aritméticas legais; LCR sobre `&&` gera só `||` (1 variante); ABS sobre um operando gera
  exatamente 3 variantes (zero, `+abs(...)`, `-abs(...)` — data-model.md, "Operador de mutação");
  UOI sobre um operando de sítio ROR/LCR pode inserir `!`, mas UOI sobre um operando de sítio AOR
  não gera a variante `!` (ilegalidade sintática, `apply` retorna `None` — não é erro); toda
  função de operador preserva o arquivo byte a byte fora do intervalo do sítio
- [X] T016 [P] [US1] Write tests in `tests/mutation/test_candidates.py`: `first_order_candidates`
  itera sítio a sítio, variante a variante, na mesma ordem de `find_sites`; sobre um `AC_ref`
  sintético com mais de 100 sítios elegíveis, o truncamento determinístico (FR-003a) retém
  exatamente os primeiros 100 na ordem de descoberta, e duas chamadas dão o mesmo resultado byte
  a byte (nenhuma amostragem)
- [X] T017 [P] [US1] Write tests in `tests/mutation/test_validation.py` com um motor falso
  (mesmo padrão de motor falso já usado nos testes do módulo `dataset`, injetado por parâmetro de
  palavra-chave em `sandbox.judge_source`): cada um dos motivos de FR-005 produz o
  `DiscardReason` certo (`DUPLICATE` antes de qualquer execução, por hash já visto;
  `COMPILE_ERROR`; `TLE`; `MLE`; `RE`; `EQUIVALENT` quando o motor falso devolve 100% `AC`);
  `confirm_stability` com um motor falso que devolve o mesmo veredito 6 vezes retorna `True`; com
  uma das 6 divergente, retorna `False` e o `DiscardReason` é `UNSTABLE`; `confirm_stability`
  nunca é chamado para um candidato já descartado pelo primeiro filtro (asserção de contagem de
  chamadas ao motor falso)
- [X] T018 [US1] Write an **integration** test (marker `integration`, roda no serviço `sandbox`)
  in `tests/mutation/test_validation_integration.py`: sobre um `AC_ref.cpp` sintético minúsculo e
  seu `testes.json` (um teste só, entrada/saída conhecidas), gerar os candidatos ROR/AOR de
  primeira ordem, validar de verdade (compila e executa via `sandbox.judge_source` real) e
  confirmar que ao menos um candidato correto e conhecido (ex.: trocar `<` por `>=` num laço que
  isso quebra) é aceito com veredito `WA`
- [X] T019 [P] [US1] Write tests in `tests/mutation/test_persistence.py`: `select_mutants`/a
  gravação escreve primeiro em `data/mutants/building/<problem_id>/` e só move atomicamente para
  `data/mutants/problems/<problem_id>/` ao concluir (research.md, R5); interromper (simular
  levantando uma exceção) no meio da gravação de um problema não deixa nada em
  `data/mutants/problems/<problem_id>/`, e uma nova chamada refaz do zero; um problema já
  completo em `data/mutants/problems/` é pulado (mesmo comportamento de retomada do módulo de
  dataset)
- [X] T020 [US1] 🎯 Write a test in `tests/mutation/test_uniqueness.py` que prova diretamente o
  pedido desta rodada ("garantir que os mutantes são diferentes entre si"): usando um `AC_ref.cpp`
  real do dataset com sítios suficientes (fixture de `tests/mutation/fixtures/`, marker
  `integration`), gerar o conjunto final de mutantes e afirmar que (a) todos os `source_sha256`
  são dois a dois distintos; (b) nenhum é igual ao hash do `AC_ref.cpp` original; (c) rodar a
  geração duas vezes sobre o mesmo arquivo produz o mesmo conjunto de hashes, na mesma ordem
  (determinismo por construção, D6)

### Implementation for User Story 1

- [X] T021 [P] [US1] Implement `src/mutation/sites.py` (`find_sites`) per
  [contracts/mutation-api.md](./contracts/mutation-api.md) usando `tree_sitter_cpp` (makes T014
  pass)
- [X] T022 [P] [US1] Implement `src/mutation/operators.py` (uma função pura por operador,
  `apply(source, site, variant) -> str | None`) (makes T015 pass; depends on T009)
- [X] T023 [US1] Implement `src/mutation/candidates.py` (`first_order_candidates`, truncamento de
  FR-003a) (makes T016 pass; depends on T021, T022)
- [X] T024 [US1] Implement `src/mutation/validation.py` (`validate`, `confirm_stability`,
  reaproveitando `sandbox.judge_source` sem alteração) (makes T017, T018 pass; depends on T009)
- [X] T025 [US1] Implement `src/mutation/persistence.py` (gravação em `building/` + movimento
  atômico, retomada por pular problema já completo) (makes T019 pass)
- [X] T026 [US1] Implement `src/mutation/orchestrator.py` (`select_mutants`, caminho de primeira
  ordem completo; combinação de ordem superior ainda como `NotImplementedError` explícito, a ser
  substituído em US2): mantém um `set[str]` de hashes já aceitos para o problema e nunca aceita
  um candidato cujo hash já esteja nele — é o mecanismo concreto que faz T020 passar (depends on
  T021–T025)
- [X] T027 [US1] Add the `generate` subcommand to `src/mutation/__main__.py`: chama
  `dataset_gate.verify_dataset` antes de processar qualquer problema (FR-010); aceita `--problem
  ID` (repetível); usa `orchestrator.select_mutants` por problema; problemas cujo primeiro-ordem
  já não bastar terminam em erro explícito por enquanto (US2 substitui) (depends on T011, T012,
  T026)
- [X] T028 [US1] Update `src/mutation/README.md` (b), (c), (d): descreve `generate` no escopo
  desta história (só primeira ordem), a entrada (`data/dataset` verificado) e a saída
  (`data/mutants/problems/<id>/Mutant_<n>.cpp`); comando nasce `pendente` na tabela

**Checkpoint**: US1 funciona e é testável isoladamente sobre qualquer problema cujo `AC_ref`
tenha ≥ 100 sítios de primeira ordem (a maioria, pela estimativa da spec).

---

## Phase 3b: Paralelização de `generate` (aprovada pelos autores em 2026-09-24; research.md, R14)

**Purpose**: reduzir a geração dos 200 problemas de ≈44 h em série (extrapolado de `189_C`, R13; ≈24 h em série com o filtro de R16, medido em 8 problemas) para
horas, com um trabalhador por `slot` do motor, sem mudar o conjunto de mutantes.

- [X] T059 [P] Write tests in `tests/mutation/test_runtime.py` com motor falso: com `ThreadRuntime`
  de 4 trabalhadores e atrasos que invertem a ordem de conclusão, os arquivos gravados (bytes de
  cada `Mutant_<n>.cpp` e de cada `generation.json`) são idênticos aos de `InlineRuntime`; um
  `InfraError` num trabalhador propaga e nada desse problema é gravado; `close()` limpa os `slot`s
- [X] T060 [P] Write tests in `tests/mutation/test_cli_generate.py`: `--workers` (inteiro positivo;
  `0` ou texto é erro de uso, código `2`), padrão metade das CPUs, `--workers 1` igual ao
  comportamento atual, Ctrl+C durante o pool sai com `130` sem deixar problema em `problems/`
- [X] T061 Implement `src/mutation/runtime.py` (`PoolRuntime`, `InlineRuntime`, `ThreadRuntime`),
  espelhando `dataset.validation.runtime` (fork, fila de `slot`s, `initializer`, `kill_slot_processes`)
- [X] T062 Adapt `generate` em `src/mutation/__main__.py` para submeter problemas ao runtime e
  gravar cada `Selection` no processo principal, com a opção `--workers`
- [X] T063 📌 PROPAGAR — Validar a proposta: rodar 8 problemas com `--workers 1` e com `--workers 4`
  (executada em 2026-09-24, a pedido dos autores: 0 de 800 mutantes divergentes, aceleração de 2,07×; research.md R14) e comparar os hashes de cada mutante; registrar a taxa de divergência
  medida e o tempo de cada rodada em `research.md` (R14) e em `docs/metodologia-referencia.md`
  (seção 2.7)
- [X] T064 Atualizar `src/mutation/README.md` (b) e o `README.md` da raiz com `--workers`

**Checkpoint** (atingido em 2026-09-24): `generate --workers 4` produziu, nos 8 problemas testados, os
mesmos mutantes que `--workers 1`, em ~48% do tempo (aceleração de 2,07× nesta máquina de 4 núcleos).

---

## Phase 4: User Story 2 - Fechar a cota de 100 com ordem superior determinística (Priority: P1)

**Goal**: quando a primeira ordem não basta, completar a cota de 100 combinando pares e, se
necessário, trios de mutações já válidas, em ordem determinística, sem busca; registrar um
alerta explícito quando nem isso bastar.

**Independent Test**: sobre um `AC_ref.cpp` sintético com poucos sítios (menos de 100 de
primeira ordem, mas mais de zero pares válidos possíveis), confirmar que a cota fecha com
mutantes de ordem 2 (ou 3), na mesma ordem em execuções repetidas; sobre um `AC_ref.cpp`
sintético com sítios insuficientes mesmo para ordem 3, confirmar o `ExclusionAlert`.

**Depende de**: US1 (a combinação de ordem superior parte dos candidatos de primeira ordem já
aceitos).

### Tests for User Story 2 ⚠️ (escrever primeiro; devem FALHAR)

- [X] T029 [P] [US2] Write tests in `tests/mutation/test_higher_order.py`:
  `higher_order_candidates(source, accepted, order=2)` combina pares de sítios distintos dos
  candidatos já aceitos, em ordem lexicográfica sobre `discovery_index` (research.md, R3); uma
  combinação cujas duas mudanças se cancelam (equivalente ao original, motor falso devolvendo
  100% `AC`) é descartada com `DiscardReason.EQUIVALENT`, pelo mesmo caminho de FR-005 (sem
  lógica nova); `order=3` só é tentado depois de `order=2` esgotar; duas chamadas com a mesma
  entrada produzem exatamente a mesma sequência de combinações (nenhum `random`)
- [X] T030 [US2] Write tests in `tests/mutation/test_exclusion_alert.py`: sobre um `AC_ref.cpp`
  sintético com sítios insuficientes mesmo depois de esgotar pares e trios,
  `orchestrator.select_mutants` devolve um `ExclusionAlert` com `mutants_reached < 100` e
  `highest_order_attempted == 3`, e **nenhum** arquivo de mutante é persistido para esse problema
  (FR-009)

### Implementation for User Story 2

- [X] T031 [US2] Implement `src/mutation/higher_order.py` (`higher_order_candidates`) (makes T029
  pass; depends on T009, T021-T023)
- [X] T032 [US2] Wire `higher_order.py` into `orchestrator.select_mutants` (substitui o
  `NotImplementedError` de T026): depois de esgotar a primeira ordem, tenta pares e depois trios,
  na ordem determinística; devolve `ExclusionAlert` se ainda faltar (makes T030 pass; depends on
  T026, T031)
- [X] T033 [US2] 📌 PROPAGAR — Piloto de desempenho da busca combinatória (research.md, R4): rodar
  `docker compose run --rm sandbox python -m mutation generate --problem <2 ou 3 ids conhecidos
  por terem poucos sítios, pela contagem já medida na pesquisa>`; medir tempo total, quantos
  pares/trios foram tentados até fechar a cota (ou até um alerta), e decidir **nesta tarefa** se
  um orçamento de tentativas é necessário para o restante dos 200 problemas. Escrever o número e
  a decisão em `docs/metodologia-referencia.md` (seção 2.4) e em `research.md` (R4), com data e
  revisão git
- [X] T034 [US2] Se o piloto (T033) decidir por um orçamento: adicionar a constante
  correspondente a `src/mutation/config.py` e um teste que prova que esgotar o orçamento (sem
  fechar 100) produz o mesmo `ExclusionAlert` de T030, nunca uma exceção não tratada. Se o piloto
  decidir que não é necessário, esta tarefa só registra essa decisão (já feito em T033) e não
  altera código
- [X] T035 [US2] Update `src/mutation/README.md` (b): completa a descrição de `generate` agora
  que a ordem superior está implementada, incluindo o que o autor vê quando um problema recebe um
  `ExclusionAlert`

**Checkpoint**: US1 e US2 juntas cobrem os 200 problemas do dataset sem depender de bases de
mutação adicionais (Clarifications, D4).

---

## Phase 5: User Story 3 - Empacotar e verificar a integridade da execução final (Priority: P2)

**Goal**: `data/mutants.zip` determinístico + manifesto SHA-256 em `manifests/` + comando de
verificação, mesmo formato já usado para o dataset (FR-012, FR-014).

**Independent Test**: empacotar um `data/mutants/problems/` sintético pequeno; a verificação
passa; alterar 1 byte, remover um arquivo e acrescentar um arquivo extra faz a verificação
falhar apontando o arquivo, exatamente como já é provado para o dataset.

**Depende de**: US1 (e US2, se aplicável) para ter algo real para empacotar; os testes e o
código deste bloco usam fixtures sintéticas e podem ser desenvolvidos em paralelo depois da
fase 2.

### Tests for User Story 3 ⚠️ (escrever primeiro; devem FALHAR)

- [X] T036 [P] [US3] Write tests in `tests/mutation/test_packaging.py`: entradas do zip
  ordenadas por caminho; mesmas convenções determinísticas já testadas para o dataset (timestamp
  fixo, `ZIP_DEFLATED` em nível fixo, raiz `mutants/problems/<id>/` dentro do zip, de modo que `unzip data/mutants.zip -d data/` produza o mesmo caminho que `generate` grava); empacotar o mesmo
  `data/mutants/problems/` duas vezes dá o mesmo hash de zip; `package` se recusa (código `1`) se
  houver qualquer `data/mutants/building/<id>/` pendente; problemas com `ExclusionAlert` não têm
  pasta dentro do zip
- [X] T037 [P] [US3] Write tests in `tests/mutation/test_manifest.py`: restrições do
  `Manifest` citadas literalmente de [data-model.md](./data-model.md) ("Pacote de mutantes e
  manifesto"): `schema_version == 1`; `mutants_zip = {path, sha256, size}` com `path ==
  "data/mutants.zip"`; `files` ordenada por `path`, um item por arquivo dentro do zip; hash do
  manifesto bate após reempacotar os mesmos bytes
- [X] T038 [P] [US3] Write tests in `tests/mutation/test_verify.py`: pacote íntegro → `OK`,
  código `0`; um byte alterado → `changed`; um arquivo removido → `missing`; um arquivo extra →
  `extra`; funciona só com o zip e o manifesto, sem precisar de `data/mutants/` (mesmo
  comportamento pós-clonagem já provado para o dataset); com `extracted_dir`, só os `Mutant_<n>.cpp` de
  `problems/<id>/` contam: `generation.json` e `building/` de uma geração local não são `extra`
  (contracts/cli.md, "Fluxo: quem gera e quem só recebe")

### Implementation for User Story 3

- [X] T039 [P] [US3] Implement `src/mutation/schemas/manifest.py` (Pydantic; restrições exatas de
  T037) (makes the schema part of T037 pass)
- [X] T040 [US3] Implement `src/mutation/packaging.py` (`build_mutants_zip`) (makes T036 pass;
  depends on T039)
- [X] T041 [US3] Implement `src/mutation/integrity.py` (`verify`) (makes T038 pass; depends on
  T039, T040)
- [X] T042 [US3] Add `package` (com a recusa de `building/` pendente) and `verify` subcommands to
  `src/mutation/__main__.py` (depends on T011, T012, T040, T041)
- [X] T043 [US3] Update `src/mutation/README.md` (b), (e): descreve `package`/`verify`,
  deixando claro que só fazem sentido na execução final que sustenta os números do TCC
  (Constitution, emenda 1.6.0) — não em toda rodada de desenvolvimento; comandos nascem
  `pendente`

**Checkpoint**: US3 funciona e é testável sozinha; o resultado de uma execução completa é
distribuível e verificável, sem depender de determinismo bit a bit (Clarifications, D5).

---

## Phase 6: User Story 4 - Relatório de geração de mutantes (Priority: P3)

**Goal**: `manifests/mutation_report.json` com os agregados exigidos por FR-013, para citar no
texto do TCC sem reabrir os arquivos-fonte dos mutantes.

**Independent Test**: sobre um `data/mutants/` sintético com descartes e alertas conhecidos,
`report` produz um JSON cujos totais somam corretamente e cujo `exclusion_alerts` reflete
exatamente os alertas sintéticos.

### Tests for User Story 4 ⚠️ (escrever primeiro; devem FALHAR)

- [X] T044 [P] [US4] Write tests in `tests/mutation/test_report.py`: restrições citadas
  literalmente de [contracts/file-formats.md](./contracts/file-formats.md) (`schema_version`,
  `funnel`, `order_distribution`, `operator_distribution`, `exclusion_alerts`,
  `dataset_manifest_sha256`); `exclusion_alerts` é `[]` (nunca omitido) quando não há nenhum
  alerta; o relatório é idempotente (rodar `report` duas vezes sobre o mesmo `data/mutants/` dá o
  mesmo JSON, exceto nada — não há timestamp neste arquivo)

### Implementation for User Story 4

- [X] T045 [P] [US4] Implement `src/mutation/schemas/report.py` (Pydantic, restrições exatas de
  T044)
- [X] T046 [US4] Implement `src/mutation/report.py` (`build_report`): lê `data/mutants/problems/`
  e os registros de descarte acumulados durante `generate`, calcula os agregados, lê
  `dataset_manifest_sha256` do gate (T011) (a revisão do código foi retirada do relatório em 2026-09-25) (makes T044
  pass; depends on T045)
- [X] T047 [US4] Add `report` subcommand to `src/mutation/__main__.py`; fazer `package` (T042)
  chamar `report` internamente antes de finalizar, para o relatório sempre refletir o que foi
  empacotado (per [contracts/cli.md](./contracts/cli.md)) (depends on T042, T046)
- [X] T048 [US4] Update `src/mutation/README.md` (b), (d): descreve `report`, com um exemplo do
  JSON produzido

**Checkpoint**: as quatro histórias funcionam de forma independente e compõem o módulo completo.

---

## Phase 6b: Recuperação e robustez (adicionada a pedido dos autores em 2026-09-24; research.md, R19)

**Purpose**: garantir que uma execução interrompida por qualquer motivo é retomada sem perda e sem
refazer o que já estava pronto, e que dois `generate` ao mesmo tempo ou um problema danificado nunca
passam em silêncio.

- [X] T065 [P] Write tests in `tests/mutation/test_recovery.py`: interrupção entre problemas,
  no meio da gravação de um problema, por `kill -9` (sobras em `building/`, arquivo temporário de
  escrita atômica), com vários problemas em voo (2 e 4 trabalhadores) e repetida 3 vezes; em todos, o
  resultado depois de retomar é **byte a byte** o de uma execução nunca interrompida, e um problema
  já fechado nunca é reescrito (nem o `mtime` muda)
- [X] T066 Fix `PoolRuntime.close` (`abort=True`): Ctrl+C / `docker stop` / falha do motor não
  esperam os problemas em voo (minutos) — encerram os trabalhadores e os processos dos `slot`s na
  hora; medido em 2026-09-24 com o motor real: o container saiu em 1 s (antes, não saía em 40 s)
- [X] T067 Add `persistence.check_closed` e o aviso `DAMAGED` em `generate` (e a recusa em
  `package`): um problema fechado que perdeu ou teve um `Mutant_<n>.cpp` alterado é apontado, nunca
  pulado em silêncio; apagar a pasta do problema basta para regerar só ele
- [X] T068 Add `persistence.exclusive_run` (`flock` em `data/mutants/.lock`): um segundo `generate`
  sobre os mesmos dados se recusa (código `1`); o SO solta o trava se o processo morrer, então nunca
  fica obsoleta
- [X] T069 📌 PROPAGAR — Validação real de recuperação (execuções dos autores/assistente sobre o
  motor real): SIGINT com 2 trabalhadores, SIGKILL depois de um problema fechado e retomada;
  registrar o resultado em `research.md` (R19) e em `docs/metodologia-referencia.md` (2.10)

**Checkpoint**: interromper e retomar não perde nada e não refaz problemas fechados.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: fechar a feature (Constitution, Princípios VI e XI); nada aqui substitui as tarefas
de documentação e propagação já feitas dentro das histórias.

- [X] T049 [P] Run lint and format over the whole repo: `docker compose run --rm app ruff check
  .` and `docker compose run --rm app black --check .`; fix findings with `--fix`/`black .` até
  ambos ficarem limpos
- [X] T050 Run the full suite: `docker compose run --rm sandbox pytest` (incluindo os testes
  `integration` deste módulo); todos passam; registrar a contagem no relatório final
- [X] T051 Execute `quickstart.md` Níveis 0 a 4 (níveis 0 a 3 registrados em 2026-09-24; o 4 é a execução final, T052/T053) e registrar o resultado de cada um (comandos,
  saída, data) numa seção "Resultado da validação" ao final do arquivo; qualquer nível que falhe
  bloqueia a feature
- [X] T052 📌 PROPAGAR — Run the real generation over the 200 problems:
  `docker compose run --rm sandbox python -m mutation generate`. Registrar em
  `manifests/mutation_report.json` e propagar para `docs/metodologia-referencia.md` (seção 2) e
  `spec.md`/`plan.md`/`research.md`: quantos problemas fecharam só com primeira ordem (compara
  com a estimativa de ≥ 75% da spec, SC-003), quantos precisaram de ordem superior, quantos
  `ExclusionAlert` ocorreram (se algum, os `problem_id` e o motivo), e o tempo total de execução
  *(`generate` executado pelos autores em 2026-09-24/25 e números registrados em `research.md` R21 e
  metodologia 2.11: 113 só de primeira ordem, 87 com ordem superior, 0 alertas, ~7 h 26 min; falta
  gerar `manifests/mutation_report.json` com `report`, o que aguarda a revisão do fluxo de
  verificação)*
- [X] T053 Package the real result: `python -m mutation package` seguido de `python -m mutation
  verify`; confirmar que `git status --short` mostra só `data/mutants.zip`,
  `manifests/mutants.manifest.json` e `manifests/mutation_report.json` como novidade — a decisão
  de commitá-los (Constitution, emenda 1.6.0) é sempre do autor, nunca automática (Princípio X)
- [X] T054 Documentation conformity: set `src/mutation/README.md` to `Status: implementado` and
  run `docker compose run --rm app python scripts/check_docs_sync.py --closing --module
  src/mutation --cli "python -m mutation" --cli-owner src/mutation` (exit `0`, sem linha
  `pendente`)
- [X] T055 📌 Methodology synchronization check: run `docker compose run --rm app python
  scripts/check_docs_sync.py --closing --feature specs/002-mutant-generation` (C1 a C6); para
  qualquer decisão ou número medido criado depois de T013, atualizar `sync-matrix.json` e
  `docs/metodologia-referencia.md` até o comando sair `0`; acrescentar a linha final datada à
  seção 8 da metodologia
- [X] T056 Final update of the root `README.md`: linha de `src/mutation/` na tabela "Módulos e
  estado" passa a `implementado`, seção "Referência de comandos" recebe os comandos de
  `mutation`, e a nota "Estado atual" é reescrita com a data; confirmar
  `check_docs_sync.py --only C2,C3,C4` sai `0`
- [X] T057 Constitution v1.6.0 compliance review for the feature: re-rodar a tabela "Constitution
  Check" de `plan.md` contra o código e a documentação implementados; registrar qualquer desvio
  com justificativa em `plan.md` ("Complexity Tracking"); um dos autores revisa o código gerado
  com apoio de IA antes de integrar à `main` (Princípio X) — registrar quem e quando no relatório
  final
- [X] T058 Set `Status:` em `specs/002-mutant-generation/spec.md` para `Implemented` só se T049
  a T057 estiverem concluídas, e acrescentar a linha de fechamento à seção 8 da metodologia;
  senão deixar `Draft` e listar os itens pendentes no relatório final

---

## Phase 8: Verificação de consistência entre artefatos (adicionada a pedido dos autores em 2026-09-25; research.md, R22)

**Purpose**: um comando (`python -m cli check`, pacote `src/cli`) que percorre as pastas de verdade e confere, por nomes e contagens,
que dataset e mutantes estão completos e 1:1; portão das etapas que consomem os dados. Referência
viva: [`docs/verificacao-consistencia.md`](../../docs/verificacao-consistencia.md) — os módulos
seguintes acrescentam a sua camada lá.

- [X] T070 [P] Write tests in `tests/cli/` (`test_consistency.py`, `test_main.py`): repositório sintético
  consistente passa com as contagens no resumo; cada arquivo fixo faltando, 99 WAs, WA fora da faixa,
  arquivo a mais, contagem diferente do manifesto, pasta que não é de problema, nomes diferentes do
  manifesto, dataset ausente e manifesto ausente (código `2`); 99 e 101 mutantes, `generation.json`
  permitido, excluído como aviso, `building/` pendente, manifesto de mutantes ausente como aviso;
  problema sem mutantes, mutantes sem problema, `--only`, camada desconhecida; `--deep` acha um byte
  alterado que os nomes não veem, mutante alterado, zip diferente, zip ausente como aviso; listas
  longas cortadas; uma camada nova é conferida sem mudar as verificações
- [X] T071 Implement `python -m cli check` (`src/cli/consistency.py` e `__main__.py`; inicialmente `scripts/check_consistency.py`, movido para `src/cli` em 2026-09-25 para ter nome limpo) (`Layer`/`Group`, `check_layer`,
  `check_relation`, `run_checks`, `main`; só biblioteca padrão) (makes T070 pass)
- [X] T072 Documentar: `docs/verificacao-consistencia.md`, seção no `README.md` da raiz e linha na
  "Referência de comandos", `CLAUDE.md`, README do módulo `dataset` (passo 6 do cenário "do zero":
  descompactar) e do `mutation`, `quickstart.md` (Nível 4), metodologia (seção 0.1)
- [X] T073 📌 PROPAGAR — Execução real sobre os dados reais (dataset descompactado e 200 problemas
  de mutantes): `OK`, 0 falhas, 1 aviso; registrar em `research.md` (R22) e na metodologia (0.1)
- [X] T074 Depois de `package`: rodar `python -m cli check --deep` (sem o aviso de manifesto de
  mutantes) e registrar o resultado (execução dos autores, roteiro do Nível 4 do `quickstart.md`)

**Checkpoint**: `docker compose run --rm app python -m cli check --deep` sai `0` (executado em 2026-09-25 sobre os dados finais: `OK`, 0 falhas, 0 avisos).

---

## Phase 9: Fechamento, README e governança (2026-09-25)

- [X] T075 Mover a conferência de consistência para `src/cli/` (`python -m cli check`), com
  `README.md` do módulo `cli`, testes em `tests/cli/` e o comando com nome limpo na "Referência de
  comandos"; `scripts/verify_dataset.py` deixa de ser o comando documentado (`python -m dataset
  verify`)
- [X] T076 Reescrever `src/dataset/README.md` e `src/mutation/README.md` em dois cenários (do zero /
  descompactar o que já existe), uma tabela de comandos com as variações e sem citação ao processo
  de especificação; README da raiz alinhado; `docs/template-modulo.md` atualizado
- [X] T077 Checagem automática C8 em `scripts/check_docs_sync.py` (README sem spec-kit, Constitution,
  `FR-`/`SC-`, `specs/NNN-...`), com testes; regra no `CLAUDE.md`
- [X] T078 Constitution 1.7.0 (Princípios II e XI) e propagação: metodologia (0.1, 2, 2.11, 5.2, 7,
  8), `plan.md` (Constitution Check de fechamento), `research.md` (R23), `quickstart.md`
- [X] T079 Fechamento: `Status: Implemented`; README do módulo `Status: implementado`; carimbos
  refeitos (`generate` `8a45e6c`, `report`/`package`/`verify` `29af6d0`; `check` do `cli` a carimbar
  depois do commit)

**Checkpoint**: `check_docs_sync.py --closing` sem achados; suíte completa e verificações verdes.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências; T001 → T002; T003, T004 são `[P]`
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias; inclui a
  generalização do `check_docs_sync.py` (T005, T006) e o portão de consistência com o dataset
  (T010, T011)
- **US1 (Phase 3)** e **US2 (Phase 4)**: ambas P1; US2 depende de US1 (a ordem superior parte dos
  candidatos de primeira ordem já aceitos) — não são paralelas entre si, ao contrário do padrão
  usual do template
- **US3 (Phase 5)**: pode ser desenvolvida em paralelo com US1/US2 depois da fase 2 (usa
  fixtures sintéticas nos testes), mas só produz um pacote real depois que US1+US2 gerarem
  mutantes de verdade
- **US4 (Phase 6)**: idem US3 — testável com fixtures desde a fase 2, mas só relata números
  reais depois de US1+US2
- **Polish (Phase 7)**: depende de US1 a US4 completas

### Within Each User Story

- Testes escritos e vistos falhar antes da implementação
- `sites.py`/`operators.py` antes de `candidates.py`; `candidates.py` antes de `orchestrator.py`;
  `orchestrator.py` antes do subcomando de CLI
- Cada história termina com a atualização do README do módulo (aceite verificável, não só
  narrativo)

### Parallel Opportunities

- T001–T004 (Setup) majoritariamente `[P]`
- Dentro da Fase 2: T005/T006 (doc-sync) e T007–T009 (tipos) e T010/T011 (portão do dataset) são
  trilhas independentes, paralelizáveis entre si
- Dentro de US1: T014, T015, T016, T017, T019 são `[P]` (arquivos de teste diferentes, sem
  dependência entre si); T018 e T020 dependem de fixtures reais e da implementação já existir,
  não são `[P]`
- US3 e US4 podem ser desenvolvidas em paralelo por pessoas diferentes depois da Fase 2, usando
  fixtures sintéticas, sem esperar US1/US2 terminarem

---

## Parallel Example: User Story 1

```bash
# Testes de US1 que não dependem uns dos outros:
Task: "Write tests in tests/mutation/test_sites.py"
Task: "Write tests in tests/mutation/test_operators.py"
Task: "Write tests in tests/mutation/test_candidates.py"
Task: "Write tests in tests/mutation/test_validation.py"
Task: "Write tests in tests/mutation/test_persistence.py"

# Implementação de base, em arquivos diferentes:
Task: "Implement src/mutation/sites.py"
Task: "Implement src/mutation/operators.py"
```

---

## Implementation Strategy

### MVP First (US1 apenas)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — bloqueia tudo)
3. Complete Phase 3: US1
4. **STOP e VALIDE**: rodar `generate` sobre um problema real denso o bastante para não precisar
   de ordem superior; confirmar 100 mutantes distintos (T020)

### Incremental Delivery

1. Setup + Foundational → fundação pronta
2. US1 → testável isoladamente sobre problemas densos → MVP
3. US2 → cobre os problemas que precisam de ordem superior (a maioria dos 200, pela estimativa)
4. US3 → pacote e verificação da execução final
5. US4 → relatório para o texto do TCC
6. Cada história soma valor sem quebrar as anteriores

### Ponto de decisão explícito (T033)

Ao contrário do módulo de dataset (onde o piloto mede se a meta de 200 problemas fecha), o
piloto aqui (T033) mede se a busca combinatória de ordem superior é rápida o bastante sem um
orçamento de tentativas — uma pergunta de desempenho, não de viabilidade. Não avance para a
execução completa (T052) antes de T033 estar concluída e propagada.

## Notes

- `[P]` = arquivos diferentes, sem dependência
- `[Story]` mapeia a tarefa à história, para rastreabilidade
- Cada história deve ser completável e testável de forma independente
- Confirme que os testes falham antes de implementar
- Faça commit depois de cada tarefa ou grupo lógico — **decisão sempre do autor** (Constitution,
  Princípio X); o agente nunca commita por conta própria
- Pare em qualquer checkpoint para validar uma história isoladamente
- Evite: tarefas vagas, conflito no mesmo arquivo, dependências entre histórias que quebrem a
  independência
