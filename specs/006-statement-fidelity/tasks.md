# Tasks: Conferência dos enunciados contra o original do Codeforces

**Input**: Design documents from `/specs/006-statement-fidelity/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md),
[quickstart.md](./quickstart.md); Constitution v1.7.1 (`.specify/memory/constitution.md`)

**Tests**: INCLUÍDOS. A Constitution (Princípio VI) exige suíte própria para um módulo de
infraestrutura, e SC-001, SC-003 e SC-004 são verificados por teste. Em cada história, os testes vêm
antes da implementação: escreva-os e confirme que **falham** antes de implementar. Nenhum teste
acessa a internet.

**Organization**:
- primeiro a base comum (schemas, extração e renderização);
- depois US2 (P1, guardar o original), pré-requisito prático da US1;
- depois US1 (P1, conferir e gerar o relatório);
- depois US3 (P2, gerar os corrigidos para revisão);
- por fim a validação no dado real e o fechamento.

Aplicar a correção ao dataset está fora desta feature (E1).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história da spec (US1 a US3); só nas fases de história
- Caminhos relativos à raiz do repositório
- **Onde rodar**:
  - todo `pytest` no `sandbox` (`docker compose run --rm sandbox pytest ...`), sem rede;
  - os comandos, `ruff`, `black` e `check_docs_sync.py` no `app` (`docker compose run --rm app ...`),
    que tem rede.

## Regras que valem para TODAS as tarefas (Constitution, Princípios II, IV, VI, IX, X, XI)

- **📌 PROPAGAR**: a tarefa marcada com 📌 produz dado medido ou decisão nova. Ela **só está
  concluída** depois de a informação ser escrita, **na própria tarefa**, em
  `docs/metodologia-referencia.md` (seções 1 e 3 e uma linha datada na seção 8) **e** nos artefatos
  da feature que ela afeta (`spec.md`, `plan.md`, `research.md`), com data e fonte.
- **Documentação como critério de aceite**:
  - **Formato do README:** `src/dataset/README.md` segue `docs/template-modulo.md`: seis campos,
    dois cenários, uma tabela única com todos os comandos e variações, e nada de spec-kit, `FR-`,
    `T0xx` ou `specs/...`.
  - **Checagem:** cada tarefa que toca o README só termina quando `docker compose run --rm app
    python scripts/check_docs_sync.py --module src/dataset --cli "python -m dataset" --cli-owner
    src/dataset` sai `0`.
  - **Carimbo:** todo comando novo nasce `pendente` em "Comandos verificados" e só é carimbado na
    tarefa que o executa de verdade (data e `git rev-parse --short=7 HEAD`, mais `+dirty` se
    houver alteração não commitada); depois, procurar por `grep` o nome do comando nos dois
    READMEs e corrigir a prosa que o descreva como não executado.
- **Restrições citadas literalmente** de [data-model.md](./data-model.md) e
  [contracts/cli.md](./contracts/cli.md) fazem parte do aceite.
- **O dataset nunca muda** (FR-006, FR-009): nenhum comando desta feature escreve em
  `data/dataset/`, `data/dataset.zip`, `manifests/dataset.manifest.json`, `data/mutants*` ou
  `data/suites/`.
- **Acesso ao site só como em E2**:
  - um pedido por vez, com pelo menos 3 s entre pedidos;
  - `User-Agent` do projeto;
  - nunca nos testes;
  - nunca uma segunda vez sem `--refetch`.
- **Pastas planas**: nenhuma pasta por problema (o `cli check` não muda).
- **Sem dependência nova**: `pyproject.toml` e `uv.lock` não mudam.
- **O agente nunca roda `git add`/`commit`/`push`** (Princípio X).

---

## Phase 1: Setup

- [X] T001 Medir a linha de base: `docker compose run --rm sandbox pytest -q` e anotar aqui o número de testes que passam *(1.877, a medição da suíte inteira de 2026-10-18 depois do `--suite-attempts`; o código não mudou antes desta feature)*
- [X] T002 [P] Em `src/dataset/config.py`, acrescentar as constantes:
  - `STATEMENTS_DIR = DATA_DIR / "statements"`;
  - `STATEMENT_ORIGINALS_DIR = STATEMENTS_DIR / "originals"`;
  - `STATEMENT_ORIGINALS_ZIP = DATA_DIR / "statement_originals.zip"`;
  - `STATEMENT_ORIGINALS_MANIFEST = Path("manifests/statement_originals.manifest.json")`;
  - `STATEMENT_FIDELITY_REPORT = Path("manifests/statement_fidelity_report.json")`;
  - `CODEFORCES_PROBLEM_URL = "https://codeforces.com/problemset/problem/{contest}/{index}?locale=en"`;
  - `CODEFORCES_MIN_INTERVAL_S = 3.0`;
  - `CODEFORCES_USER_AGENT = "tcc-unb-statement-check/1.0"`;
  - `CODEFORCES_TIMEOUT_S = 30`;
  - `CODEFORCES_RETRY_WAITS_S = (30, 60, 120, 240, 300)`.

  São os valores de research R1 e E2.
- [X] T003 [P] Esqueleto de `src/dataset/statements/__init__.py`, `fetch.py`, `extract.py`, `render.py`, `compare.py` e `correct.py`, com docstrings de módulo (o que fazem, citando R1 a R5), sem lógica

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: o que US1, US2 e US3 usam: schemas, extração do bloco e renderização em texto
achatado e marcado.

### Tests for Foundational ⚠️

- [X] T004 [P] `tests/dataset/statements/fixtures.py` com blocos `<div class="problem-statement">` pequenos, escritos à mão com a estrutura medida (research R2):
  - formato antigo, com `<span class="tex-span">`, `<sup class="upper-index">5</sup>`, `<sub class="lower-index"><i>i</i></sub>` e `&thinsp;`;
  - formato novo, com `$$$1 \le n \le 10^5$$$` e `$$$a_i$$$`;
  - um com `<table>`, um com `<img>` e um com uma seção extra (`div.section-title` "Interaction");
  - um sem as partes esperadas;
  - para cada bloco, o `enunciado.md` correspondente: o texto achatado, com o bloco de exemplos, como o dataset tem;
  - nenhuma página do site copiada.
- [X] T005 [P] Testes em `tests/dataset/statements/test_extract_render.py` (R2; junto com T006):
  - ficam fora o cabeçalho (`div.header`) e os exemplos (`div.sample-tests`);
  - entram a descrição, `input-specification`, `output-specification`, `note` e a seção extra;
  - os nós saem na ordem: texto, `sup`, `sub`, fórmula, imagem, tabela, parágrafo;
  - `<i>`/`<b>`/`<span>` não deixam espaço;
  - um bloco sem as partes levanta o erro de bloco ausente.
- [X] T006 [P] Testes em `tests/dataset/statements/test_extract_render.py` (R4):
  - achatado: `10<sup>5</sup>` → `105`, `a<sub>i</sub>` → `ai`;
  - marcado: `10^{5}`, `a_{i}`;
  - fórmula `$$$1 \le n \le 10^5$$$` → `1 ≤ n ≤ 10^5` nos dois textos, com as equivalências medidas `\le`→`≤`, `\lt`→`<`, `\dots`→`...`;
  - um comando fora da tabela fica marcado como desconhecido;
  - imagem: nada no achatado e `[image]` no marcado;
  - tabela: células em sequência no achatado e tabela Markdown no marcado;
  - o mapa de posições aponta cada trecho para o nó de origem.
- [X] T007 [P] Testes em `tests/dataset/schemas/test_statements.py` com as validações literais do data-model:
  - `OriginalEntry`: "`error` nulo ⇔ `http_status == 200` e `page_sha256` presente";
  - "os `problem_id` são únicos";
  - `ProblemFidelity`: "`unchecked_reason` não nulo ⇔ `status == "unchecked"`" e "`differences` vazia ⇔ `status == "faithful"`";
  - `FidelityTotals` coerente com `problems`;
  - `CorrectionSummary`: "cada `problem_id` do dataset aparece em exatamente uma das três listas" e "`checks` tudo `true` para estar em `corrected`".

### Implementation for Foundational

- [X] T008 [P] `src/dataset/schemas/statements.py`: `OriginalEntry`, `OriginalsManifest`, `Difference` (`kind` ∈ `"lost_exponent" | "lost_index" | "formula" | "image" | "table" | "other"`), `ProblemFidelity` (`format` ∈ `"marked" | "latex" | "mixed"`, `status` ∈ `"faithful" | "losses" | "unchecked"`), `FidelityTotals`, `FidelityReport`, `CorrectedStatement`, `CorrectionSummary`. Pydantic, `extra="forbid"`, `schema_version: Literal[1]`, com as validações de data-model §1–§3. T007 passa.
- [X] T009 `src/dataset/statements/extract.py`: `extract_statement(html: str) -> list[Node]`, com `html.parser` (R2), e o erro `NoStatementBlock`. T005 passa.
- [X] T010 `src/dataset/statements/render.py`: `render(nodes) -> Rendered`, com o texto achatado, o texto marcado e o mapa de posições; a tabela `EQUIVALENCES = {r"\le": "≤", r"\lt": "<", r"\dots": "..."}` (S3, medida no piloto); `normalize_space(text)` (espaço normal, U+2009, U+00A0 e quebras viram um espaço só). T006 passa.

**Checkpoint**: `docker compose run --rm sandbox pytest tests/dataset/statements tests/dataset/schemas` passa.

---

## Phase 3: User Story 2 - Guardar o original com integridade (Priority: P1)

**Goal**: obter cada página uma vez, no ritmo de E2, guardar a cópia e o hash, e não acessar mais
o site depois disso.

**Independent Test**: com um servidor HTTP local no lugar do site, a primeira execução faz 200
pedidos espaçados e grava as cópias e o manifesto; a segunda não faz nenhum pedido; um byte
alterado numa cópia faz recusar.

### Tests for User Story 2 ⚠️

- [X] T011 [P] [US2] Testes em `tests/dataset/statements/test_fetch.py`, com um servidor HTTP local (`http.server` numa thread, no `localhost` do contêiner) e um relógio falso, apontando a URL para ele por monkeypatch de `config.CODEFORCES_PROBLEM_URL`.

  O **primeiro teste** confere que o servidor em `127.0.0.1` responde dentro do `sandbox`, que não tem rede (R7). Depois:
  - **Erros e retomada:**
    - um erro definitivo (`http_404`, `no_statement_block`) não é tentado de novo sem `--refetch`, e um temporário (429 esgotado) é;
    - **Pacote e hashes:**
    - empacotar duas vezes os mesmos blocos dá um `data/statement_originals.zip` com os mesmos bytes (pacote determinístico: ordem alfabética, data fixa);
    - com só o pacote, sem as páginas inteiras, a conferência usa o `statement_sha256` e um bloco alterado no pacote é recusado.

  E também:
  - um pedido por vez, nunca dois ao mesmo tempo;
  - o relógio recebe espera de ≥ 3 s entre pedidos;
  - o `User-Agent` vai igual a `config.CODEFORCES_USER_AGENT`;
  - a URL usa `cf_contest_id`, `cf_index` e `?locale=en`;
  - cópia gravada atomicamente em `data/statements/originals/<id>.html` e entrada no manifesto com `page_sha256` e `statement_sha256`;
  - 429 e depois 200: espera de 30 s e sucesso;
  - 429 em todas as esperas: para com `FetchStopped`, mantendo o que já tinha;
  - 404: entrada com `error = "http_404"`;
  - página sem o bloco: `error = "no_statement_block"`;
  - retomada que só pede o que falta;
  - `--refetch` pede de novo;
  - segunda execução sem nenhum pedido (SC-003);
  - cópia alterada: `OriginalMismatch` com o nome do problema;
  - o pacote `data/statement_originals.zip` tem só `statements/<id>.html` com os blocos, e reabri-lo dá os mesmos `statement_sha256`;
  - sem as cópias e com o pacote: a comparação usa o pacote.

### Implementation for User Story 2

- [X] T012 [US2] `src/dataset/statements/fetch.py`: `ensure_originals(root, problem_ids, *, refetch, clock, opener) -> OriginalsManifest` (R1).
  - **Ritmo e erros:** um pedido por vez; `clock.sleep` até completar `CODEFORCES_MIN_INTERVAL_S` desde o último; esperas `CODEFORCES_RETRY_WAITS_S` para 429/5xx; `FetchStopped` ao esgotá-las.
  - **Gravação:** cópia atômica (`dataset.persistence.store`); o manifesto é regravado a cada página, para que uma interrupção não perca nada.
  - **O que falta:** só se baixa o que não tem entrada no manifesto ou teve erro temporário; um erro definitivo só volta a ser tentado com `--refetch`.
  - **Leitura e pacote:**
    - `verify_originals(root)` confere os hashes (`OriginalMismatch`): `page_sha256` e `statement_sha256` com as páginas inteiras; só `statement_sha256` com o pacote;
    - `package_originals(root)` grava o zip só com os blocos, de forma determinística (entradas em ordem alfabética, data fixa 1980-01-01, sem dados da máquina);
    - `read_statement_blocks(root)` lê as cópias ou, sem elas, o pacote.

  T011 passa.

**Checkpoint**: US2 funciona sozinha (download, cópia, manifesto, pacote).

---

## Phase 4: User Story 1 - Conferir os 200 enunciados contra o original (Priority: P1) 🎯 MVP

**Goal**: comparar cada bloco com o `enunciado.md`, classificar cada diferença pelo elemento do
original e gravar o relatório.

**Independent Test**: com os blocos do T004, o relatório tem as diferenças certas, cada uma com o
tipo certo, e nada do dataset muda.

### Tests for User Story 1 ⚠️

- [X] T013 [P] [US1] Testes em `tests/dataset/statements/test_compare.py` (R3):
  - **Antes de comparar:** o `enunciado.md` perde o bloco de exemplos (de `Examples` até `Note` ou até o fim).
  - **Diferenças classificadas:**
    - `10^{5}` × `105` → `lost_exponent`;
    - `a_{i}` × `ai` → `lost_index`;
    - `10^{100000}` × `10100000` → `lost_exponent`;
    - o formato novo sem perda → `faithful`, com `format = "latex"`;
    - um comando LaTeX desconhecido → `formula`;
    - imagem → `image`;
    - tabela achatada → `table`;
    - uma palavra trocada → `other`, com os dois trechos.
  - **Diferenças ignoradas:**
    - só de espaço (`&thinsp;`, quebra de linha) não conta;
    - título e limites não contam.
  - **Problemas sem comparação:** sem bloco ou sem cópia → `unchecked`, com o motivo.
  - **Posição:** `ours_offset` aponta para o trecho certo do `enunciado.md`.
- [X] T014 [P] [US1] Testes em `tests/dataset/statements/test_cli.py` (junto com T020):
  - `python -m dataset check-statements` num dataset de teste com as cópias já guardadas: não faz nenhum pedido, grava `manifests/statement_fidelity_report.json` válido no `FidelityReport` e imprime a linha `statements: N checked; faithful F, with losses L, unchecked U` e a linha por tipo do contrato;
  - com `--problem`, o resultado é impresso e o relatório versionado **não** é gravado nem alterado;
  - código `0` mesmo com perdas;
  - código `1` com cópia alterada ou dataset divergente;
  - código `2` em uso errado;
  - código `3` com o servidor falso sempre em 429;
  - retrato de `data/dataset/`, do zip e do manifesto do dataset igual antes e depois (FR-006).

### Implementation for User Story 1

- [X] T015 [US1] `src/dataset/statements/compare.py`: `compare(block_nodes, enunciado_text) -> ProblemFidelity` (R3, R4).
  - **Antes de alinhar:** corta os exemplos do nosso lado; normaliza os espaços nos dois lados.
  - **Alinhamento:** `difflib.SequenceMatcher(autojunk=False)` entre o texto marcado e o nosso.
  - **Classificação:** cada trecho diferente recebe o tipo do nó do original que o cobre, pelo mapa de posições.
  - **Por diferença:** guarda `original`, `ours`, `context` (até 30 caracteres) e `ours_offset`.
  - **Formato:** `format` vem dos nós.
- [X] T016 [US1] `build_report(root) -> FidelityReport` em `src/dataset/statements/compare.py`: os 200 problemas, `totals` com `by_kind` e `problems_by_kind`, `equivalences` usadas e os hashes dos dois manifestos; a validação "`faithful + with_losses + unchecked == problems`".
- [X] T017 [US1] Subcomando `check-statements` em `src/dataset/__main__.py`, com `--refetch` e `--problem ID` (repetível). Segue a ordem do contrato §1: uso → dataset contra o manifesto → hashes das cópias → download do que falta → relatório → pacote. As linhas de saída e os códigos 0/1/2/3/130 são os do contrato. T013 e T014 passam.
- [X] T018 [US1] `src/dataset/README.md`: `check-statements` na tabela única (as variações `--refetch` e `--problem`, o serviço `app` com rede, o ritmo de 3 s, o que fica gravado e onde, que perdas não são falha); o Cenário B, com o pacote `data/statement_originals.zip` já no repositório (sem acessar o site); uma linha `pendente` em "Comandos verificados"; `check_docs_sync.py --module ...` sai 0.

**Checkpoint**: US1 e US2 funcionam (o MVP: o relatório confiável).

---

## Phase 5: User Story 3 - Gerar os enunciados corrigidos para revisão (Priority: P2)

**Goal**: inserir no texto atual as marcações do original e aceitar só os corrigidos que passam
nas três conferências.

**Independent Test**: para `161_A` de teste, o corrigido tem `10^{5}` e `a_{i}`, passa nas três
conferências e fica em `DIR/161_A.md`; o `enunciado.md` não muda.

### Tests for User Story 3 ⚠️

- [X] T019 [P] [US3] Testes em `tests/dataset/statements/test_correct.py` (R5):
  - **O corrigido:** é o texto atual com `^{` e `}` em volta de cada expoente perdido e `_{` e `}` em volta de cada índice; a tabela vira tabela Markdown; o bloco de exemplos, os espaços e as quebras ficam iguais.
  - **As três conferências:** passam no caso bom e cada uma falha quando o corrigido é adulterado no teste:
    - (a) uma letra trocada;
    - (b) uma marca removida;
    - (c) um espaço a mais fora das marcações.
  - **Revisão:** imagem, `formula` desconhecida, `other` e `unchecked` vão para `review`, com o motivo.
  - **Problema `faithful`:** fica em `unchanged`, sem arquivo.
  - **Resumo:** `summary.json` é válido no `CorrectionSummary`.
- [X] T020 [P] [US3] Testes em `tests/dataset/statements/test_cli.py`:
  - `correct-statements --output-dir out` grava `out/<id>.md` (pasta plana, sem subpasta) e `out/summary.json`, e imprime as linhas do contrato §2;
  - sem relatório, ou com relatório de outro dataset → `1`;
  - pasta com arquivos sem `--force` → `2`; com `--force`, substitui;
  - pasta dentro de `data/dataset/`, `data/suites/` ou `manifests/` → `2`;
  - uma conferência que falha → o problema vai para `review` e o código é `1`;
  - retrato de `data/dataset/` igual antes e depois.

### Implementation for User Story 3

- [X] T021 [US3] `src/dataset/statements/correct.py`: `correct(enunciado_text, fidelity, rendered) -> CorrectedStatement | Review`, com a inserção das marcações pelos `ours_offset`, a troca da tabela e as três conferências (a), (b) e (c) de FR-008; `correct_all(root, report, out_dir, *, force) -> CorrectionSummary`. T019 passa.
- [X] T022 [US3] Subcomando `correct-statements` em `src/dataset/__main__.py` (`--output-dir` obrigatória, `--force`), com a checagem do destino antes de ler qualquer coisa e as linhas e códigos do contrato §2. T020 passa.
- [X] T023 [US3] `src/dataset/README.md`: `correct-statements` na tabela única (o que é gravado, as três conferências, o que vai para revisão, que o dataset nunca muda); uma linha `pendente` em "Comandos verificados"; `check_docs_sync.py --module ...` sai 0.

---

## Phase 6: Validação no dado real e fechamento

- [X] T024 📌 PROPAGAR — **Os 5 do piloto** (quickstart, nível 2; SC-001):
  - rodar `check-statements --problem ...` com os 5. O comando baixa as 5 páginas de novo (5 pedidos, a cada 3 s ou mais), o que exercita o download de verdade; as cópias de `data/cf_pilot/` não são reaproveitadas, porque não têm entrada no manifesto. O resultado é só impresso (com `--problem`, o relatório versionado não é gravado);
  - conferir os números de SC-001 (`161_A`: 4 e 21; `1_B`: 2; `15_A`: 6; `102_B`: 1; `1000_B`: `faithful`);
  - qualquer diferença em relação à contagem à mão é examinada e registrada antes de mexer no código.
- [X] T025 📌 PROPAGAR — **Os 200** (quickstart, nível 3; SC-002, SC-003, SC-005). Só depois de T024 e com aviso aos autores, porque são 195 acessos ao site:
  - rodar `check-statements` e medir o tempo do download;
  - rodar de novo e conferir que não houve nenhuma linha `fetch:` e que o relatório é idêntico (`sha256sum`);
  - medir o tamanho de `data/statement_originals.zip`;
  - comparar com os 71 da contagem antiga: quantos se confirmam e quantos problemas novos aparecem;
  - registrar os totais por tipo, os números e o tempo em `research.md` (R1, R3), no SC-005 da spec e na metodologia (seções 1 e 3 + seção 8);
  - carimbar `check-statements` no README e fazer a revisão de prosa por `grep`.
- [X] T026 📌 PROPAGAR — **Corrigidos** (quickstart, nível 4; SC-004):
  - rodar `correct-statements --output-dir data/statements/corrected`;
  - conferir à mão `161_A.md` e um da revisão;
  - conferir que `python -m dataset verify --extracted data/dataset` continua `OK`;
  - registrar quantos corrigidos, inalterados e para revisão, e os motivos;
  - carimbar `correct-statements`.
- [X] T027 📌 PROPAGAR — **Documentação de uso**:
  - **`README.md` da raiz:** a "Referência de comandos" com os dois comandos, e `data/statement_originals.zip` e os dois manifestos na descrição dos artefatos;
  - **`CLAUDE.md`:** "Estrutura" e "Comandos do dia a dia";
  - **Metodologia:** a nota da seção 3 passa a "implementada", com uma linha na seção 8;
  - **Checagem:** `check_docs_sync.py` e `--module src/dataset ...` saem 0.
- [ ] T028 Constitution v1.7.1 compliance review: refazer a tabela "Constitution Check" de `plan.md` contra o código. *(2026-10-18: as quatro conferências passaram, registradas em `plan.md`; falta a revisão do código por um dos autores.)* Em especial:
  - **II:** a segunda execução não acessa a rede;
  - **FR-006/FR-009:** `grep -rn "dataset.zip\|enunciado.md" src/dataset/statements` só mostra leitura;
  - **IX:** `pyproject.toml` e `uv.lock` sem mudança;
  - **E2:** ritmo e `User-Agent` conferidos no teste.

  Um dos autores revisa o código (Princípio X); registrar quem e quando.
- [ ] T029 Fechamento: *(2026-10-18: suíte inteira com 1.916 passando e 1 falha conhecida e alheia — `test_stopping_wakes_every_waiting_thread`, teste de tempo da feature 004; `ruff` e `black --check` em 0; `check_docs_sync.py` em 0. O `--closing` aponta as 3 linhas de "Comandos verificados" do `dataset` carimbadas em `9df4f0e+dirty`, que fecham ao rodar os comandos de novo depois do commit e carimbar a revisão limpa.)*
  - `docker compose run --rm sandbox pytest` (suíte inteira) passa, com o número de T001 mais os novos;
  - `ruff check .` e `black --check .` saem 0;
  - `check_docs_sync.py --closing --feature specs/006-statement-fidelity` sai 0;
  - **Entrega:** dizer aos autores os arquivos a commitar (código, testes, `data/statement_originals.zip`, os dois manifestos, a documentação; **não** `data/statements/`), **sem** rodar nenhum comando de Git.

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: T001 antes de qualquer mudança; T002 e T003 `[P]`.
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias. T008 antes de T012,
  T015 e T021 (os schemas).
- **US2 (Phase 3)**: depende da Fase 2.
- **US1 (Phase 4)**: depende da Fase 2 e de T012 (lê as cópias pelo `read_statement_blocks`); os
  testes de comparação (T013) não dependem de US2 e podem ser escritos antes.
- **US3 (Phase 5)**: depende de US1 (o relatório e os `ours_offset`).
- **Phase 6**:
  - T024 depende de US1;
  - T025 depende de T024 e de um aviso aos autores;
  - T026 depende de US3 e T025;
  - T027 a T029 vêm por último.

### Parallel Opportunities

- **Fase 2:** T004 a T007 em arquivos diferentes; T008 em paralelo com T009/T010 (T010 depende de
  T009).
- **US1:** T013 e T014 `[P]`.
- **US3:** T019 e T020 `[P]`.

## Parallel Example: Foundational

```bash
Task: "Write fixtures in tests/dataset/statements/fixtures.py"
Task: "Write tests in tests/dataset/statements/test_extract.py"
Task: "Write tests in tests/dataset/statements/test_render.py"
Task: "Write tests in tests/dataset/schemas/test_statements.py"
```

## Implementation Strategy

### MVP (US2 + US1)

1. Fase 1 e Fase 2.
2. US2 (download e cópia) e US1 (comparação e relatório).
3. **STOP e VALIDE** com os 5 do piloto (T024), sem acessar o site de novo.

### Incremental Delivery

1. MVP → o relatório dos 200 (T025) responde à pergunta dos autores: o que se perdeu, com evidência
   do original.
2. US3 → os corrigidos para revisão.
3. Os autores decidem, com o relatório, se aplicam a correção (fora desta feature, E1).

## Notes

- Confirme que os testes falham antes de implementar.
- Commit sempre por decisão do autor (Princípio X); o agente nunca commita.
