# Tasks: Revisão 2 do dataset (enunciados corrigidos)

**Input**: Design documents from `/specs/007-dataset-revision/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md),
[quickstart.md](./quickstart.md); Constitution **v1.8.0** (emenda do Princípio II aplicada em
2026-10-18)

**Tests**: INCLUÍDOS (Princípio VI). Os testes de cada história vêm antes da implementação.
Nenhum teste toca no dataset real.

**Organization**:
- base comum (schemas e empacotamento);
- US2 (P1, as decisões dos 15), que vem antes da US1 porque a geração exige as decisões;
- US1 (P1, gerar a revisão 2);
- US3 (P2, comandos e execuções);
- por fim, a execução real e o fechamento.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: arquivos diferentes, sem dependência de tarefa incompleta
- **[Story]**: US1 a US3, só nas fases de história
- **Onde rodar**: `pytest` no `sandbox`; os comandos no `app`; o `execute` do SLM no `sandbox`

## Regras que valem para TODAS as tarefas (Constitution 1.8.0)

- **📌 PROPAGAR**: dado medido ou decisão nova vai, na própria tarefa, para
  `docs/metodologia-referencia.md` (seção 1.6.1 e histórico) e para `spec.md`/`plan.md`/`research.md`.
- **Revisões do dataset (Princípio II, 1.8.0)**: só os `enunciado.md` justificados mudam; a
  revisão 1 é guardada sem nenhum byte alterado; o manifesto registra a revisão e a proveniência;
  cada artefato derivado diz de qual revisão veio.
- **Nada pela metade**: o `revise` grava tudo ou nada.
- **Documentação como critério de aceite**:
  - READMEs no formato de `docs/template-modulo.md`;
  - `check_docs_sync.py` (raiz e `--module`) sai 0;
  - comando novo nasce `pendente` em "Comandos verificados" e só é carimbado quando roda de verdade.
- **Sem dependência nova**; **o agente nunca roda `git add`/`commit`/`push`**.

---

## Phase 1: Setup

- [X] T001 Medir a linha de base: `docker compose run --rm sandbox pytest -q`, anotando o número de testes que passam
- [X] T002 [P] `.gitignore`: acrescentar a exceção `!data/dataset.rev1.zip`, com comentário dizendo que é a revisão 1 guardada para auditoria (Princípio II, 1.8.0)

---

## Phase 2: Foundational

### Tests ⚠️

- [X] T003 [P] Testes em `tests/dataset/schemas/test_revision.py` com as regras literais do data-model:
  - `StatementDecision`: "`enunciado` não nulo ⇔ `decision == "correct"`"; `reason`, `reviewed_by` não vazios;
  - `Manifest`: `schema_version` 2 exige `revision ≥ 2` e `revision_of`; `schema_version` 1 recusa os dois; o manifesto atual (`schema_version` 1) continua válido;
  - `DatasetRevision`: "os `problem_id` de `changed` e `kept` são disjuntos";
  - `Provenance` do pacote do SLM: "cada combinação aparece uma vez como vigente".
- [X] T004 [P] Teste em `tests/dataset/integrity/test_packaging_source.py`: `build_dataset_zip` com uma pasta de problemas qualquer dá o mesmo zip que hoje quando a pasta tem o mesmo conteúdo de `data/work/problems`; sem o parâmetro, o comportamento é o atual.

### Implementation

- [X] T005 [P] `src/dataset/schemas/revision.py`: `StatementDecision`, `ChangedStatement`, `DatasetRevision`, `RevisionOf` (data-model §1–§3); `src/dataset/schemas/manifest.py`: `Manifest` aceita `schema_version` 1 ou 2, com `revision` e `revision_of` só em 2. T003 passa (a parte do dataset).
- [X] T006 [P] `src/dataset/integrity/packaging.py`: parâmetro opcional `problems_dir` em `build_dataset_zip` e `_planned_entries` (padrão `config.PROBLEMS_DIR`) e a lista de problemas pela própria pasta quando ele é dado. T004 passa.

---

## Phase 3: User Story 2 - Registrar os 15 revisados à mão (Priority: P1)

**Goal**: rascunhos das decisões para os autores e conferência de cada decisão.

**Independent Test**: com um relatório de teste com 2 problemas em revisão, o `--draft-decisions`
grava 2 rascunhos; uma decisão `correct` que só mexe no trecho apontado é aceita, e uma que mexe
fora dele é recusada, com o trecho.

### Tests ⚠️

- [X] T007 [P] [US2] Testes em `tests/dataset/test_revision_decisions.py` (research R3):
  - **Rascunhos:** com o texto atual, as diferenças e, quando o problema tem `lost_exponent`/`lost_index`, o texto com essas marcações já inseridas como sugestão; sem sobrescrever uma decisão existente.
  - **Decisões aceitas:**
    - `correct` com marcação dentro de uma diferença;
    - `correct` trocando o trecho de uma diferença `formula`/`other`;
    - `keep`.
  - **Decisões recusadas:**
    - `correct` mudando texto fora das diferenças (mensagem com o trecho);
    - `sha256_before` errado;
    - `problem_id` fora da lista de revisão;
    - decisão faltando (a lista do que falta).

### Implementation

- [X] T008 [US2] `src/dataset/revision.py`:
  - `draft_decisions(root, report) -> list[Path]`;
  - `load_decisions(root, report) -> dict[str, StatementDecision]`, com as recusas de R3;
  - `check_decision(enunciado_rev1, decision, differences)`.

  T007 passa.

---

## Phase 4: User Story 1 - Gerar a revisão 2 (Priority: P1) 🎯 MVP

**Goal**: `python -m dataset revise` (R2, R4, R5).

**Independent Test**: num dataset sintético de 3 problemas (um com expoente perdido, um em
revisão com decisão, um fiel):
- a revisão 2 muda só os 2 `enunciado.md`;
- a revisão 1 fica guardada byte a byte;
- o manifesto 2 é válido;
- a conferência contra o original, depois, não acha perdas.

### Tests ⚠️

- [X] T009 [P] [US1] Testes em `tests/dataset/test_revision.py`:
  - **Geração:**
    - só os `enunciado.md` corrigidos e os `correct` mudam, e todos os outros arquivos têm o mesmo SHA-256 (FR-002);
    - `data/dataset.rev1.zip` e `manifests/dataset.rev1.manifest.json` com os bytes da revisão 1;
    - manifesto novo com `schema_version` 2, `revision` 2 e `revision_of` com os quatro hashes;
    - `dataset_revision.json` válido;
    - `check-statements` sobre a revisão 2 sem `lost_exponent`/`lost_index` nos corrigidos (SC-002).
  - **Determinismo:** a mesma geração duas vezes, sobre as mesmas entradas, dá o mesmo zip.
  - **Recusas com código 1 e nenhum arquivo alterado:**
    - dataset extraído divergente;
    - relatório de outro dataset;
    - pacote de originais divergente;
    - decisão faltando;
    - corrigido que falha numa conferência;
    - resultado que mudaria outro arquivo;
    - revisão 2 já existente.
  - **`--dry-run`:** confere tudo e não grava nada.
  - **Próximo passo:** a lista das combinações afetadas impressa é exatamente caixa-preta e híbrido dos problemas alterados.

### Implementation

- [X] T010 [US1] `src/dataset/revision.py`: `build_revision(root, *, dry_run) -> DatasetRevision`, com as entradas e conferências de R2, os corrigidos refeitos em memória com `dataset.statements.correct` (`corrected_text`, `checks`), a cópia em `data/work/revision2/problems/`, o empacotamento (T006), o manifesto 2, a conferência arquivo a arquivo de R5 e, por último, a gravação atômica (revisão 1 renomeada, revisão 2, `dataset_revision.json`).
- [X] T011 [US1] Subcomando `revise` em `src/dataset/__main__.py`, com `--draft-decisions` e `--dry-run` e as linhas e códigos do contrato §1. T009 passa.
- [X] T012 [US1] `src/dataset/README.md`: `revise` na tabela única (o que faz, as decisões, o que guarda, o que imprime), o Cenário B dizendo que o zip versionado é a revisão 2 e como conferir a revisão 1, uma linha `pendente` em "Comandos verificados"; `check_docs_sync --module src/dataset ...` sai 0.

---

## Phase 5: User Story 3 - Levar comandos e execuções para a revisão 2 (Priority: P2)

**Goal**: a junção do pacote do SLM com a origem por combinação e o `cli check` coerente.

**Independent Test**: com duas árvores sintéticas do SLM (a anterior completa, a nova só com as
afetadas), o `package --merge-from` gera um pacote com `provenance.json` cobrindo todas as
combinações, e o `cli check` passa.

### Tests ⚠️

- [X] T013 [P] [US3] Testes em `tests/ai_clients/test_package_merge.py` (R6):
  - origem certa por combinação;
  - as afetadas vêm da execução nova, as demais da anterior, e as substituídas marcadas;
  - recusa se faltar uma afetada na execução nova ou uma não afetada na anterior;
  - a árvore anterior é conferida antes de entrar, com as regras do `store` (combinação danificada, `suite.json` diferente do que os arquivos dão), sem exigir que o `run.json` dela aponte para o dataset atual (ela é da revisão 1, por definição); uma árvore anterior danificada é recusada;
  - `provenance.json` válido e cobrindo todas;
  - o manifesto e o relatório dizem a revisão por combinação.
- [X] T014 [P] [US3] Testes em `tests/cli/test_consistency.py`: a camada `slm_suites` aceita a junção (usa a árvore de `provenance.json`); acusa combinação sem origem; a camada `dataset` passa com um manifesto `schema_version` 2.

### Implementation

- [X] T015 [US3] `src/ai_clients/packaging.py` e `src/ai_clients/__main__.py`: `package --merge-from DIR` (só `slm`), com a conferência da árvore anterior (as regras do `store`, sem comparar o `run.json` dela com o dataset atual), a junção de R6, o `provenance.json` e as saídas do contrato §2; `SuiteView`/leitura do pacote usam a origem. T013 passa.
- [X] T016 [US3] `src/cli/consistency.py`: a camada `slm_suites` com a junção e a camada `dataset` com o manifesto 2; `docs/verificacao-consistencia.md` atualizado. T014 passa.
- [X] T017 [US3] `src/ai_clients/README.md`: `package --merge-from` na tabela única e o que é a origem por combinação; linha `pendente`; `check_docs_sync --module src/ai_clients ...` sai 0.

---

## Phase 6: Execução real e fechamento

- [X] T018 **Decisões dos 15 (autores)**: rodar `python -m dataset revise --draft-decisions`; os autores preenchem `manifests/statement_decisions/<id>.json` com o original ao lado (decisão, texto, motivo, nome, data). Os rascunhos trazem também as diferenças `lost_exponent`/`lost_index` do problema já com a marcação sugerida (caso de `190_A`, que tem um expoente perdido além de outra diferença), para os autores aceitarem ou recusarem. O agente não preenche nenhuma decisão.
- [X] T019 📌 PROPAGAR — **Revisão 2**:
  - `revise --dry-run`, depois `revise`, depois `rm -rf data/dataset && unzip data/dataset.zip -d data/`;
  - `dataset verify --extracted data/dataset` e o `verify` da revisão 1 dão `OK`;
  - `check-statements` não mostra mais perdas nos corrigidos;
  - **antes de liberar GPT e Gemini**: `dataset verify --extracted data/dataset` com a revisão 2 e um `generate --model gpt --dry-run` e `--model gemini --dry-run`, conferindo que o dataset extraído é o da revisão 2 (o `run.json` deles vai gravar esse hash); o hash da revisão 1 (`a092d987…`) é registrado na metodologia como "não usar nas execuções novas".

  Registrar quantos mudaram (automáticos e manuais), quantos foram mantidos e o tamanho do zip novo; carimbar `revise`.
  **Feito (2026-10-18)**: 104 alterados (102 automáticos, 2 manuais), 13 mantidos; zip `5a9b66b8…`, 12.892.995 bytes; detalhes na metodologia 1.6.1.
- [ ] T020 📌 PROPAGAR — **Mutantes (F4)**: `python -m mutation report` (aponta para a revisão 2) e `python -m mutation verify` (`OK`, sem mudança no pacote); registrar que o relatório antigo apontava para `6b3628c3…` (S4).
- [ ] T021 📌 PROPAGAR — **SLM (D2, F2)**:
  - `mv data/suites/slm data/suites/slm-rev1` (o `revise` imprime esse passo); conferir que `data/suites/slm` não existe antes do primeiro `generate` e que `data/suites/slm-rev1` não existia antes do `mv`;
  - alternar o `generate` e o `execute` que o `revise` imprimiu até o fim;
  - `package --merge-from data/suites/slm-rev1`;
  - `cli check --deep`.

  Registrar o número de combinações refeitas, o tempo e o resultado (`status` das suítes novas comparado com as antigas das mesmas combinações); carimbar `package --merge-from`.
- [ ] T022 📌 PROPAGAR — **Documentação**:
  - `README.md` da raiz: a revisão 2, a 1 guardada, a referência de comandos e a lista de artefatos;
  - `CLAUDE.md`: a frase "commitado uma única vez" passa a dizer que há revisões numeradas (1.8.0), e a "Estrutura" e os comandos ganham `dataset.rev1.zip`, `dataset_revision.json`, as decisões e o `revise`;
  - metodologia: a seção 1.6.1 passa a implementada, com os números;
  - limitações do TCC: o que a correção garante e não garante (FR-009);
  - nos modelos comerciais, a revisão de cada suíte é identificada pelo hash do manifesto do dataset gravado no `run.json` e nos relatórios (SC-004); no SLM, pelo `provenance.json`.
- [ ] T023 Constitution 1.8.0 compliance review no `plan.md`: as quatro obrigações da emenda conferidas contra o código e os artefatos; revisão do código por um dos autores.
- [ ] T024 Fechamento:
  - suíte inteira passando (T001 mais os novos);
  - `ruff`, `black --check` e `check_docs_sync` (com `--closing --feature specs/007-dataset-revision`) saem 0;
  - entrega: dizer aos autores os arquivos a commitar (`data/dataset.zip`, `data/dataset.rev1.zip`, os manifestos, `dataset_revision.json`, as decisões, `data/slm_suites.zip` e o manifesto dele, o relatório dos mutantes, o código e a documentação), sem rodar Git.

---

## Dependencies & Execution Order

- Setup → Foundational → US2 → US1 → US3 → Phase 6.
- T018 (as decisões dos autores) bloqueia T019. T019 bloqueia T020 e T021.
- **GPT e Gemini**: a execução completa deles só depois de T019, com a revisão 2.
- **[P]**: T003/T004; T005/T006; T013/T014.

## Implementation Strategy

1. **MVP**: Foundational + US2 + US1. O `revise` funciona nos testes.
2. **Junção (US3)**: pacote do SLM e `cli check`.
3. **Execução real (Phase 6)**, na ordem: decisões dos autores, revisão 2, mutantes, SLM, documentação.
