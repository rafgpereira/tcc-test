# Implementation Plan: Geração de Suítes de Teste pelo SLM

**Branch**: `003-slm-test-generation` (feature do spec-kit; o trabalho acontece na `main`, Princípio X)
| **Date**: 2026-09-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-slm-test-generation/spec.md`

## Summary

Para cada um dos 200 problemas × 3 cenários (caixa-preta, caixa-branca, híbrido), o módulo pede ao
Qwen2.5-Coder-7B (Ollama) **entradas** de teste e uma **solução Python** do problema numa única
chamada sem estado, e deriva o `expected_output` executando essa solução na sandbox — o modelo nunca
prevê a saída. Duas fases, dois comandos, dois serviços: `generate` (serviço `app`, com rede) chama o
modelo e grava a resposta crua e a interpretação; `execute` (serviço `sandbox`, sem rede) valida a
solução nos testes públicos e calcula as saídas. Até 6 tentativas por combinação (seeds 43–48);
falha de infraestrutura não consome tentativa. Todo fato é um arquivo JSON imutável gravado
atomicamente, o estado é derivado dos arquivos, e o resultado terminal é um `suite.json` por
combinação.

Abordagem técnica (detalhes em [research.md](./research.md)):

- **Reaproveitado sem alteração** (R0): o isolamento e o julgamento do motor (`sandbox.runner.execute`,
  `isolation.run_rlimits`, `judge.judge_test`/`outputs_equal`), os leitores `Metadata.from_folder` /
  `Testes.from_folder`, o contrato `TestCase`, a escrita atômica de `dataset.persistence.store`, a
  trava do dataset (`mutation.dataset_gate.verify_dataset`), as constantes de zip determinístico e o
  padrão de registro de subcomandos de `mutation/__main__.py`.
- **Novo** em `src/ai_clients/`: cliente Ollama sem estado (`/api/chat`, uma mensagem, `num_ctx`
  explícito, *tokens* e `done_reason` gravados — R2, R3, R9); montador de prompt sobre o template do
  autor, variando só `<context_data>` (R5); parser determinístico das 3 tags (R6); oráculo que roda
  o `reference_py` no motor com limites derivados do problema (R7); persistência com máquina de
  estados por arquivos, `--resume`, `--dry-run`, `--limit` (R8); relatório, pacote, verificação e
  camada nova do `cli check` (R10). Testes com cliente Ollama falso.

## Sinalizações (lacunas encontradas ao reaproveitar) e decisões

O autor pediu para sinalizar, em vez de criar por conta própria, o que não existisse. S1, S2, S4 e S5
foram decididos em 2026-09-30 (Milena, opção A em todas); S3 e S6 são informativos.

| # | Lacuna | O que o plano faz | Decisão |
|---|---|---|---|
| **S1** | Não existe um **leitor do dataset por problema**; há `Metadata.from_folder` e `Testes.from_folder`, e `enunciado.md`/`AC_ref.cpp` são lidos como texto solto no `mutation`. | Compõe essas peças em `ai_clients/problem.py` (≈15 linhas), sem mudar o pacote `dataset`. | **Decidido em 2026-09-30 (Milena)**: A — composição local no `ai_clients`; o `dataset` não muda. |
| **S2** | Não existe **schema de suíte do motor de avaliação** (o módulo de avaliação não foi especificado). | Não cria um schema de avaliação. Os casos da suíte usam **o contrato existente `TestCase` (`input`, `output`)**; o `expected_output` da spec é o campo `output`. | **Decidido em 2026-09-30 (Milena)**: A — `TestCase` (`input`, `output`); o futuro módulo de avaliação e as suítes dos modelos comerciais adotam a mesma forma (mudar exige alteração deliberada de schema, Princípio IV). |
| **S3** | O motor não tem **executor de Python**, só `run_binary` (C++ compilado). | Invólucro fino em `ai_clients/oracle.py` sobre `sandbox.runner.execute`; o pacote `sandbox` não muda. | — (informativo; decorre da spec: motor reaproveitado sem alteração). |
| **S4** | **Temperatura e amostragem** não estão definidas em lugar nenhum; com `temperature = 0` as 6 retentativas seriam idênticas. | R4: `0.7 / top_p 0.8 / top_k 20 / repeat_penalty 1.05` (configuração do fabricante), seed base 42. | **Decidido em 2026-09-30 (Milena)**: A — valores do fabricante. |
| **S5** | O `slm_prompt.txt` **não cumpre FR-007** (pede "maximum size allowed by the constraints" e não manda respeitar as restrições nem limitar o tamanho ao que cabe na resposta). | Template editado com a redação de R5a (RULE 2 e RULE 3). | **Decidido em 2026-09-30 (Milena)**: A — template editado; FR-007 passa a ser cumprido. |
| **S6** | No Linux o serviço `app` não alcança o Ollama do host sem `extra_hosts`. | Acrescenta `extra_hosts: ["host.docker.internal:host-gateway"]` só ao `app` (o `sandbox` continua sem rede). | — (mudança de uma linha no `docker-compose.yml`). |
| **S7** | Piloto 1 (2026-10-01 a 03, R13): cerca Markdown em volta de todo o código derrubou 6 tentativas do híbrido; um `<input>` vazio invalidava a tentativa inteira; `token repeat limit reached` (HTTP 500) era repetido como queda até o teto; 3 respostas cortadas por `num_predict`; o `next:` do `execute` sugeria o `generate` sem `--problem`. | Parser remove só a cerca que envolve o código inteiro e descarta `<input>` vazio sozinho (os dois contados); razão nova `repetition` (próxima seed); relatório por cenário de cortes, cercas e entradas vazias; RULE 2 trocada; `num_predict = 5120`; `next:` repete a seleção. | **Decidido em 2026-10-04 (Milena)**; o piloto 2 começa uma execução nova. |
| **S8** | Piloto 2 (2026-10-04, R14): 8 de 15 suítes aceitas (caixa-preta 1/5); as 7 descartadas caíram todas pela solução Python errando um teste público (33 WA, 29 RE, 1 TLE no total), nenhuma por causa das entradas; o registro de execução não guardava o `stdout`/`stderr` do teste público reprovado, então não dava para saber se algum RE foi falta de memória. | `AC_ref` continua fora da execução; cada tentativa continua independente; orçamento de 6 mantido; `public_tests` ganha `failed_output_head`, `failed_stderr_tail`, `failed_cpu_time_s` e `failed_peak_rss_bytes` (nulos sem falha e nos registros antigos, `schema_version` 1). | **Decidido em 2026-10-05 (Milena)**; a revisão do prompt abre o piloto 3. |
| **S9** | Revisão do prompt depois do piloto 2 (R14): a RULE 2 pedia entradas inválidas e a RULE 3 exigia que todas respeitassem as restrições; a RULE 1 ainda citava entrada vazia; o modelo abreviava entradas grandes (`... (120000 times)`); a solução Python errava os exemplos por erro de raciocínio. | Template revisto (R14, item 6): planejar e simular à mão no exemplo, aviso de que a solução roda primeiro no exemplo, de 10 a 20 entradas distintas e por extenso, entradas "quase inválidas mas válidas", dicas de Python. Maior prompt 8.993 caracteres (híbrido, `61_B`); `num_ctx`/`num_predict` não mudam. | **Decidido em 2026-10-05 (Milena)**; o piloto 3 é uma execução nova. |
| **S10** | Piloto 3 (parcial, R15): formato resolvido, mas 14% de acerto por tentativa (≈ 40% das combinações sem suíte, ≈ 20 h); 3 RE eram `exit()` indefinido porque o Python rodava com `-S`. | `-S` removido (`-I -B -X utf8`); `OLLAMA_MODEL` opcional no `.env` (padrão `qwen2.5-coder:7b`, gravado no `run.json`, `--resume` recusa outro); piloto 4 com `qwen2.5-coder:14b`. | **Decidido em 2026-10-05 (Milena)**; modelo e método do experimento pendentes (metodologia, seção 6, item 30). |

## Technical Context

**Language/Version**: Python 3.11 (CPython 3.11.16 da imagem, `uv`); nenhuma mudança na cascata C++
(esta feature não compila C++).

**Primary Dependencies**: **nenhuma nova**. `pydantic` (schemas, já no `uv.lock`); biblioteca padrão
para HTTP (`urllib.request`, `json`), trava (`fcntl`) e zip. Ollama ≥ versão registrada no
`run.json` (serviço externo, local ou remoto).

**Storage**: arquivos JSON em `data/suites/slm/` (nunca versionados); `manifests/slm_generation_report.json`
e `manifests/slm_suites.manifest.json` (versionados); `data/slm_suites.zip` só da execução final.

**Testing**: `pytest` no serviço `sandbox`; `FakeSLMClient` (tabela `(problema, cenário, seed) →
resposta | exceção`); `runner` Python falso nos testes unitários; testes `@pytest.mark.integration`
com o motor real e programas Python conhecidos.

**Target Platform**: contêineres Linux do `docker-compose.yml` (`app` com rede para o `generate`;
`sandbox` sem rede para o `execute`).

**Project Type**: pipeline de linha de comando (pacote Python novo `src/ai_clients/`).

**Performance Goals**: nenhuma meta; o tempo por chamada depende do hardware do Ollama e é medido no
piloto (quickstart, Nível 4) — não se afirma tempo não medido.

**Constraints**: `num_ctx = 8192`, `num_predict = 5120` (R3, medido; revisado no piloto 1, R13); limites do Python = limite do
problema × `PY_TIME_FACTOR = 10` (tempo) e × `PY_MEMORY_FACTOR = 4` (memória), nunca constantes
absolutas (R7); seed da tentativa `n` = `42 + n`; no máximo 6 tentativas; chamadas sequenciais;
*timeout* de leitura (`OLLAMA_HTTP_TIMEOUT_S`, padrão 900 s) e teto de repetições consecutivas por
falha de infraestrutura (`OLLAMA_MAX_INFRA_RETRIES`, padrão 30) configuráveis no `.env` (R9, R12).

**Scale/Scope**: 600 combinações; no máximo 3.600 chamadas ao modelo e 3.600 avaliações; 1 a 4
testes públicos por problema.

## Constitution Check

*GATE: antes da Fase 0 e revisto depois da Fase 1.*

| Princípio | Como o plano cumpre | Status |
|---|---|---|
| I. Metodologia mutável | Decisões novas do plano (R3, R4, R5a, R7, R8, e as decisões S1/S2/S4/S5 de 2026-09-30) registradas na metodologia, seção 3, e na seção 7; corrigida a contagem "4 razões" → 3 (clarificação de 2026-09-29) | ✅ |
| II. Reprodutibilidade | Seeds fixas e registradas; todas as opções de amostragem explícitas; `digest` do modelo (também em cada tentativa), versão do Ollama e hashes do template e do dataset no `run.json` e comparados no `--resume`; `cli check --deep` antes do piloto e da execução completa; JSON determinístico; pacote + manifesto da execução final (exceção da emenda 1.6.0, D3); camada `slm_suites` no `cli check` | ✅ |
| III. Sem estado | `/api/chat` com uma única mensagem, sem `context`; cliente sem estado mutável; verificado em todo teste pelo cliente falso (SC-005) | ✅ |
| IV. Contratos versionados | Pydantic com `schema_version: 1` para `run.json`, geração, execução, suíte, relatório, manifesto; casos no contrato `TestCase` existente (S2) | ✅ |
| V. Sandboxing | `reference_py` só no serviço `sandbox`, pelo mesmo `execute` do motor (uid por slot, rlimits, sem rede, sem capacidades), limites derivados de `metadata.json`; workdir novo por execução | ✅ |
| VI. Testa a si próprio | Testes unitários (parser, prompt, cliente, estados, retomada, relatório, pacote) e de integração com o motor real | ✅ |
| VII. Retomada | Arquivos imutáveis, escrita atômica, estado derivado dos arquivos, `suite.json` função pura, `flock` | ✅ |
| VIII. Custo/uso de IA | SLM local, sem custo por chamada; mesmo assim *tokens*, durações e `done_reason` gravados por chamada e somados no relatório; nenhuma chamada paga | ✅ |
| IX. Simplicidade | Sem dependência nova, sem paralelismo, sem abstração multi-modelo além do `Protocol` usado pelo falso | ✅ |
| X. Revisão humana | Nenhuma operação de Git pelo agente; tudo fica `modified`/`untracked` | ✅ |
| XI. Documentação viva | Metodologia, `spec.md` e `sync-matrix.json` atualizados neste ciclo; `tasks.md` terá as tarefas de `src/ai_clients/README.md`, README da raiz (tabela de módulos, "Referência de comandos", `.env`), `docs/verificacao-consistencia.md` e `.env.example` | ✅ |

**Reavaliação pós-Fase 1**: sem violação. Duas dependências entre módulos, justificadas abaixo.

## Project Structure

### Documentation (this feature)

```text
specs/003-slm-test-generation/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # R0–R13
├── data-model.md
├── quickstart.md
├── sync-matrix.json     # D1–D3 da spec ↔ metodologia (check_docs_sync C5)
├── contracts/
│   ├── cli.md
│   ├── file-formats.md
│   └── ai-clients-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (ainda não criado)
```

### Source Code (repository root)

```text
src/prompt_templates/slm_prompt.txt   # do autor; RULE 2/3 ajustadas para FR-007 (S5, decidido)
src/ai_clients/
├── __init__.py
├── __main__.py          # registro de subcomandos (padrão de mutation/__main__.py)
├── README.md            # template docs/template-modulo.md
├── config.py            # modelo, opções, seed base, fatores, caminhos, padrões de timeout/teto
├── problem.py           # ProblemInput (composição S1)
├── prompt.py            # template + context_data por cenário
├── ollama.py            # SLMClient, OllamaClient, exceções
├── parser.py            # parse_response
├── oracle.py            # run_python, python_limits, evaluate_attempt
├── store.py             # estados, escrita, finalize, exclusive_run
├── generation.py        # laço do generate (tentativas, espera de infraestrutura)
├── execution.py         # laço do execute
├── report.py
├── packaging.py         # zip + manifesto + verify
└── schemas/
    ├── __init__.py
    ├── run.py  generation.py  execution.py  suite.py  report.py  manifest.py
src/cli/consistency.py   # + camada slm_suites
tests/ai_clients/
├── conftest.py          # dataset sintético empacotado e com manifesto (como tests/mutation)
├── fakes.py             # FakeSLMClient, runner Python falso, relógio falso
├── test_schemas.py  test_problem.py  test_store.py
├── test_prompt.py  test_parser.py  test_ollama.py  test_generation.py  test_cli_generate.py
├── test_oracle.py  test_execution.py  test_cli_execute.py
├── test_resume.py  test_resume_config.py  test_damage.py
├── test_report.py  test_packaging.py
└── test_oracle_integration.py      # @pytest.mark.integration
tests/cli/test_consistency.py       # + casos da camada slm_suites
docker-compose.yml                  # + extra_hosts no app (S6)
.env.example                        # + OLLAMA_BASE_URL, OLLAMA_HARDWARE_LABEL
```

**Structure Decision**: um pacote novo, `src/ai_clients/`, como já previsto no `CLAUDE.md`
(research R1); o `sandbox` e o `dataset` não mudam; o `cli` ganha uma camada de consistência.

## Complexity Tracking

| Ponto | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| `ai_clients` importa `mutation.dataset_gate.verify_dataset` | a spec exige a mesma recusa a dataset divergente que o `mutation` já faz | copiar a função duplicaria a regra; movê-la para `dataset` mexeria em dois módulos fechados sem ganho |
| `extra_hosts` no serviço `app` (S6) | o Ollama do host é inalcançável do contêiner no Linux sem ela | exigir sempre um servidor remoto contrariaria FR-003 ("máquina local ou servidor remoto") |
