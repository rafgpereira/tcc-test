# Implementation Plan: Geração de Suítes de Teste pelo SLM

**Branch**: `003-slm-test-generation` (feature do spec-kit; o trabalho acontece na `main`, Princípio X)
| **Date**: 2026-09-30 (revisto em 2026-10-06: R18, R19, R22; em 2026-10-07: R23 a R27; em 2026-10-11: R28, execução completa) | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-slm-test-generation/spec.md`

## Summary

Para cada um dos 200 problemas × 3 cenários (caixa-preta, caixa-branca, híbrido), o módulo pede ao
`qwen2.5-coder:14b` (Ollama; até 2026-10-06, nos pilotos 1 a 4, o 7B — R20) **entradas** de teste e uma **solução Python** do problema numa única
chamada sem estado, e deriva o `expected_output` executando essa solução na sandbox — o modelo nunca
prevê a saída. Duas fases, dois comandos, dois serviços: `generate` (serviço `app`, com rede) chama o
modelo e grava a resposta crua e a interpretação; `execute` (serviço `sandbox`, sem rede) valida a
solução nos testes públicos e calcula as saídas. Política de 5 fases por combinação (R21, R22), numa tabela única no código gravada no
`run.json`: fase 1, tentativas 1–6 com seeds 42–47 a temperatura 0,7; fase 2, tentativas 7–12 com
seed 48 e temperatura 0,7 → 0,2 (as duas param na primeira solução que passa em todos os testes
públicos); fase 3, a reserva `accepted_fallback` entre as 12, sem chamada nova; fase 4, predição
nas tentativas 13–15 (seeds 49–51, 0,7; o modelo escreve as saídas, `accepted_predicted`); fase 5,
a combinação aguarda os autores (código 4) até ser fechada com `close` (`discarded_manual`);
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
| **S4** | **Temperatura e amostragem** não estão definidas em lugar nenhum; com `temperature = 0` as 6 retentativas seriam idênticas. | R4: `0.7 / top_p 0.8 / top_k 20 / repeat_penalty 1.05` (configuração do fabricante), seed base 42 (seed base e temperatura única substituídas por `ATTEMPT_POLICY` em S14). | **Decidido em 2026-09-30 (Milena)**: A — valores do fabricante. |
| **S5** | O `slm_prompt.txt` **não cumpre FR-007** (pede "maximum size allowed by the constraints" e não manda respeitar as restrições nem limitar o tamanho ao que cabe na resposta). | Template editado com a redação de R5a (RULE 2 e RULE 3). | **Decidido em 2026-09-30 (Milena)**: A — template editado; FR-007 passa a ser cumprido. |
| **S6** | No Linux o serviço `app` não alcança o Ollama do host sem `extra_hosts`. | Acrescenta `extra_hosts: ["host.docker.internal:host-gateway"]` só ao `app` (o `sandbox` continua sem rede). | — (mudança de uma linha no `docker-compose.yml`). |
| **S7** | Piloto 1 (2026-10-01 a 03, R13): cerca Markdown em volta de todo o código derrubou 6 tentativas do híbrido; um `<input>` vazio invalidava a tentativa inteira; `token repeat limit reached` (HTTP 500) era repetido como queda até o teto; 3 respostas cortadas por `num_predict`; o `next:` do `execute` sugeria o `generate` sem `--problem`. | Parser remove só a cerca que envolve o código inteiro e descarta `<input>` vazio sozinho (os dois contados); razão nova `repetition` (próxima seed); relatório por cenário de cortes, cercas e entradas vazias; RULE 2 trocada; `num_predict = 5120`; `next:` repete a seleção. | **Decidido em 2026-10-04 (Milena)**; o piloto 2 começa uma execução nova. |
| **S8** | Piloto 2 (2026-10-04, R14): 8 de 15 suítes aceitas (caixa-preta 1/5); as 7 descartadas caíram todas pela solução Python errando um teste público (33 WA, 29 RE, 1 TLE no total), nenhuma por causa das entradas; o registro de execução não guardava o `stdout`/`stderr` do teste público reprovado, então não dava para saber se algum RE foi falta de memória. | `AC_ref` continua fora da execução; cada tentativa continua independente; orçamento de 6 mantido; `public_tests` ganha `failed_output_head`, `failed_stderr_tail`, `failed_cpu_time_s` e `failed_peak_rss_bytes` (nulos sem falha e nos registros antigos, `schema_version` 1). | **Decidido em 2026-10-05 (Milena)**; a revisão do prompt abre o piloto 3. |
| **S9** | Revisão do prompt depois do piloto 2 (R14): a RULE 2 pedia entradas inválidas e a RULE 3 exigia que todas respeitassem as restrições; a RULE 1 ainda citava entrada vazia; o modelo abreviava entradas grandes (`... (120000 times)`); a solução Python errava os exemplos por erro de raciocínio. | Template revisto (R14, item 6): planejar e simular à mão no exemplo, aviso de que a solução roda primeiro no exemplo, de 10 a 20 entradas distintas e por extenso, entradas "quase inválidas mas válidas", dicas de Python. Maior prompt 8.993 caracteres (híbrido, `61_B`); `num_ctx`/`num_predict` não mudam. | **Decidido em 2026-10-05 (Milena)**; o piloto 3 é uma execução nova. |
| **S10** | Piloto 3 (parcial, R15): formato resolvido, mas 14% de acerto por tentativa (≈ 40% das combinações sem suíte, ≈ 20 h); 3 RE eram `exit()` indefinido porque o Python rodava com `-S`. | `-S` removido (`-I -B -X utf8`); `OLLAMA_MODEL` opcional no `.env` (padrão `qwen2.5-coder:7b`, `qwen2.5-coder:14b` desde S13; gravado no `run.json`, `--resume` recusa outro); piloto 4 com `qwen2.5-coder:14b`. | **Decidido em 2026-10-05 (Milena)**; modelo e método do experimento pendentes (metodologia, seção 6, item 30). |
| **S11** | Piloto 4 (`qwen2.5-coder:14b`, R16): 13 de 15 suítes aceitas; as 2 descartadas são de caixa-preta (`1000_B`, `1008_B`), as 6 tentativas de cada uma errando um teste público (11 de 12 por WA). Os autores decidiram que nenhuma combinação pode ficar sem suíte. | `STRICT_ATTEMPTS = 8`, `MAX_ATTEMPTS = 12` (`run.json` ganha `strict_attempts`); uma tentativa que reprova um teste público por WA roda as entradas geradas assim mesmo; depois de 8 falhas, a melhor delas que pode ser reserva (mais testes públicos aprovados, mais entradas mantidas, menor número) vira `suite.json` com `status: accepted_fallback`; sem nenhuma, as tentativas 9 a 12 terminam na primeira que passa ou pode ser reserva; relatório com `accepted_fallback` e `fallback_rate`. | **Decidido em 2026-10-05 (Milena)**; as árvores dos pilotos 1 a 4 não são lidas pelo código novo (`run.json` sem `strict_attempts`). |
| **S12** | Os autores decidiram (2026-10-06, R18) que nenhuma combinação termina sem suíte: depois das 8 tentativas e da reserva, tentativas 9 a 20, depois `accepted_low_confidence`, depois até 3 tentativas por predição com um segundo template (`accepted_predicted`); sem resposta interpretável, a combinação aguarda tratamento manual e só fecha como `discarded_manual`. | **Planejado e implementado em 2026-10-06 (R19; T064 a T074)**: `MAX_ATTEMPTS = 23` (20 com solução, 3 por predição, tipo derivado do número); entradas rodando depois de qualquer reprovação em teste público; `parse_prediction` e `PredictionParse`; `predict_template_sha256`, `solution_attempts` e `predict_attempts` no `run.json`; estado `awaiting_manual`, código de saída 4 e linhas `manual:`; comando `close` gravando `manual_close.json`; `suite.json` com os 5 status, `kind`, `low_confidence_eligible` e `manual_close`; relatório por status (`status_rate`); `cli check` até 23 tentativas. | **Decidido em 2026-10-06 (Milena)**: spec FR-022 a FR-022d; desenho em R19 (data-model §3–4, contratos). As árvores dos pilotos não são lidas pelo código novo. |
| **S13** | Piloto 5 (R20): com o 14B e a regra de R18, 15 de 15 combinações com suíte. Os autores escolheram o 14B como modelo do experimento e pediram um piloto 6 de temperatura e seeds. | `config.MODEL = "qwen2.5-coder:14b"`; `OLLAMA_TEMPERATURE` e `OLLAMA_SEED_BASE` opcionais no `.env`, gravados no `run.json` e comparados no `--resume`; a seed passa a ser conferida pelo `store` contra a `seed_base` do `run.json` (antes, contra a constante 42 nos schemas). | **Decidido em 2026-10-06 (Milena)**: R20. |
| **S14** | Política de 5 fases (R21): fase 1, tentativas 1–6 (seeds 42–47, temperatura 0,7); fase 2, 7–12 (seed 48, temperatura 0,7 a 0,2); fase 3, reserva entre as 12; fase 4, predição 13–15 (seeds 49–51, 0,7); fase 5, tratamento manual. Saem as tentativas extras, `accepted_low_confidence`, `OLLAMA_TEMPERATURE` e `OLLAMA_SEED_BASE`; as entradas voltam a rodar só depois de WA. | **Planejado em 2026-10-06 (R22; data-model §2–4, contratos)**: `config.ATTEMPT_POLICY` com as 15 linhas, gravada no `run.json` (`attempt_policy`) e comparada linha a linha pelo `--resume`; fase, seed, temperatura e template em cada `attempt_<n>.generation.json`, conferidos pelo `store`; `schema_version` 2 e recusa de `run.json` antigo (código 2, mandando mover a pasta); máquina de estados de 15 tentativas com reserva só depois da 12ª; entradas só depois de WA; cerca removida em `<input>`/`<output>` da predição; relatório com `acceptance` (fase e tentativa) e `per_phase` (chamadas, *tokens*, tempo); `cli check` até 15. | **Decidido em 2026-10-06 (Milena)**: spec FR-018, FR-020, FR-022 a FR-022d, FR-023; R21. |
| **S15** | Piloto 6 (R23): 15 de 15 combinações com suíte; configuração congelada e a execução completa continua a mesma, com duas GPUs T4 em paralelo. A trava única de `data/suites/slm/` impede dois `generate` ao mesmo tempo. | **Implementado em 2026-10-07 (R24; data-model §5, contratos; Phase 12)**: trava compartilhada para `generate --resume`/`execute`, exclusiva para `generate` sem `--resume`, `close` e `package`; trava exclusiva por combinação em `.locks/`, combinação em uso pulada e contada (`skipped`); um `execute` por vez (`.execute.lock`, o *slot* do motor é único); testes em `test_concurrency.py`; laço em bash para duas GPUs no README do módulo. **Corrigido em 2026-10-08**: o arquivo de trava criado pelo `execute` (root, serviço `sandbox`) passa a ser entregue ao usuário do host (`store._open_lock`), porque o `generate` do serviço `app` não conseguia abri-lo (R24). | **Decidido em 2026-10-07 (Milena)**: FR-026a. |
| **S16** | Pelo túnel do cloudflared, chamadas de mais de ~100 s recebem HTTP 524 e são repetidas até esgotar as repetições: sem *streaming*, o Ollama não manda nenhum byte antes do fim. | **Implementado em 2026-10-07 (R25; contratos; Phase 13)**: `"stream": true`, conteúdo juntado e métricas do último pedaço (registro idêntico ao sem *streaming*); resposta incompleta é falha de infraestrutura sem gravar nada; `OLLAMA_HTTP_TIMEOUT_S` vira o maior silêncio entre pedaços; `run.json` inalterado (`--resume` aceita a execução atual, conferido). | **Decidido em 2026-10-07 (Milena)**: FR-002a, FR-018a. |
| **S17** | Com metades fixas de `--problem`, uma GPU terminou a sua e ficou parada enquanto a outra ainda tinha fila. | **Implementado em 2026-10-07 (R26; Phase 14)**: o laço dá todos os problemas aos dois `generate`, e a trava por combinação (R24) os faz dividir a fila sozinhos; nenhum código de `src/` muda; teste em `test_concurrency.py`. | **Decidido em 2026-10-07 (Milena)**: FR-026a. |
| **S18** | O template de predição gerou entradas degeneradas (`1 1 1 ...` até o teto de tokens) e uma suíte `accepted_predicted` com entrada abreviada (`939_C` caixa-preta, a única que passou pela predição); o `--resume` recusa qualquer troca de template. | **Implementado em 2026-10-07 (R27; data-model §3.7 e §3.8; contratos; Phase 15)**: STEP 2 novo; comando `change-template` (registro em `template_changes/`, tentativas da versão antiga movidas para `superseded/`, refeitas com as mesmas seeds); `template_sha256` por tentativa; template corrente = `run.json` + trocas; teste abreviado descartado na predição; pacote, relatório e `cli check` com as trocas. Troca feita em 2026-10-08 (`939_C` caixa-preta refeita); motivo, gravado por engano como `"..."`, corrigido em 2026-10-11 antes do pacote (R27). | **Decidido em 2026-10-07 (Milena)**: FR-022c, FR-022e. |
| **S19** | Execução completa terminada (2026-10-06 a 2026-10-09, R28): 600 de 600 combinações com suíte — 505 `accepted`, 93 `accepted_fallback`, 2 `accepted_predicted` (`939_C` caixa-preta, `237_A` caixa-branca, ambas do template novo), 0 `discarded_manual`, 0 aguardando; 2.185 chamadas, 1.678 falhas; ≈ 37,5 h de modelo. Todas as chamadas têm a mesma etiqueta de hardware, mas a execução usou mais de uma máquina (mesma GPU T4, Ollama e digest). | Nenhuma mudança de código; `close` não foi necessário; os arquivos gravados não mudam (a etiqueta fica registrada como divergência em R28 e na metodologia). Pendentes: `package`, `verify --extracted` e `cli check --deep`. | **Decidido em 2026-10-11 (Milena)**: R28. |

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
absolutas (R7); seed e temperatura de cada tentativa pela tabela `ATTEMPT_POLICY` (12 com solução Python, 3 por
predição, 15 no total; R22); chamadas sequenciais dentro de cada `generate`, com um `generate
--resume` por GPU rodando ao mesmo tempo (cada um com seu `OLLAMA_BASE_URL`, todos os problemas,
divididos pela trava por combinação; R24, R26);
*timeout* de leitura (`OLLAMA_HTTP_TIMEOUT_S`, padrão 900 s) e teto de repetições consecutivas por
falha de infraestrutura (`OLLAMA_MAX_INFRA_RETRIES`, padrão 30) configuráveis no `.env` (R9, R12).

**Scale/Scope**: 600 combinações; no máximo 9.000 chamadas ao modelo (15 por combinação) e 7.200
avaliações (12 por combinação); 1 a 4 testes públicos por problema. Os máximos não são estimativa
de custo: o custo real depende das taxas medidas no piloto.

## Constitution Check

*GATE: antes da Fase 0 e revisto depois da Fase 1.*

| Princípio | Como o plano cumpre | Status |
|---|---|---|
| I. Metodologia mutável | Decisões novas do plano (R3, R4, R5a, R7, R8, e as decisões S1/S2/S4/S5 de 2026-09-30) registradas na metodologia, seção 3, e na seção 7; corrigida a contagem "4 razões" → 3 (clarificação de 2026-09-29) | ✅ |
| II. Reprodutibilidade | Seeds fixas e registradas; todas as opções de amostragem explícitas; `digest` do modelo (também em cada tentativa), versão do Ollama e hashes do template e do dataset no `run.json` e comparados no `--resume`; `cli check --deep` antes do piloto e da execução completa; JSON determinístico; pacote + manifesto da execução final (exceção da emenda 1.6.0, D3); camada `slm_suites` no `cli check` | ✅ |
| III. Sem estado | `/api/chat` com uma única mensagem, sem `context`; cliente sem estado mutável; verificado em todo teste pelo cliente falso (SC-005) | ✅ |
| IV. Contratos versionados | Pydantic com `schema_version: 2` (era 1 até R22, 2026-10-06) para `run.json`, troca de template, geração, execução, suíte, relatório, manifesto; casos no contrato `TestCase` existente (S2) | ✅ |
| V. Sandboxing | `reference_py` só no serviço `sandbox`, pelo mesmo `execute` do motor (uid por slot, rlimits, sem rede, sem capacidades), limites derivados de `metadata.json`; workdir novo por execução | ✅ |
| VI. Testa a si próprio | Testes unitários (parser, prompt, cliente, estados, retomada, relatório, pacote) e de integração com o motor real | ✅ |
| VII. Retomada | Arquivos imutáveis, escrita atômica, estado derivado dos arquivos, `suite.json` função pura, `flock` da execução e, desde 2026-10-07, por combinação (vários processos sem corromper, R24) | ✅ |
| VIII. Custo/uso de IA | SLM local, sem custo por chamada; mesmo assim *tokens*, durações e `done_reason` gravados por chamada e somados no relatório; nenhuma chamada paga | ✅ |
| IX. Simplicidade | Sem dependência nova, sem paralelismo dentro de um processo (desde R24, processos concorrentes coordenados por travas de arquivo), sem abstração multi-modelo além do `Protocol` usado pelo falso | ✅ |
| X. Revisão humana | Nenhuma operação de Git pelo agente; tudo fica `modified`/`untracked`; o código gerado com apoio de IA foi revisado por Milena em 2026-10-11, antes do fechamento | ✅ |
| XI. Documentação viva | Metodologia, `spec.md` e `sync-matrix.json` atualizados neste ciclo; `tasks.md` terá as tarefas de `src/ai_clients/README.md`, README da raiz (tabela de módulos, "Referência de comandos", `.env`), `docs/verificacao-consistencia.md` e `.env.example` | ✅ |

**Reavaliação pós-Fase 1**: sem violação. Duas dependências entre módulos, justificadas abaixo.

**Reavaliação da política de 5 fases (2026-10-06, R21, R22)**: sem violação nova. II — a tabela
inteira (seed e temperatura por tentativa) vai para o `run.json`, é comparada linha a linha no
`--resume` e conferida em cada tentativa; `schema_version` 2 em todos os arquivos, e uma execução
de versão anterior é recusada com mensagem clara, nunca lida pela metade. III — continua uma
mensagem por pedido; só a seed e a temperatura variam. IV — `schema_version` incrementado porque
os campos mudam de sentido (temperatura sai de `options`). IX — a tabela é escrita por extenso,
sem gerador; saem as variáveis do `.env` e a baixa confiança, que só serviam à política antiga.

**Reavaliação de 2026-10-06 (R18, R19)**: sem violação nova. III — as tentativas por predição são
chamadas sem estado como as outras (uma mensagem, sem `context`; o falso confere). V — a predição não
executa nada; as entradas que passam a rodar depois de RE/TLE/MLE rodam no mesmo isolamento, com os
mesmos limites derivados. II — o segundo template entra no `run.json` (`predict_template_sha256`) e
no `--resume`. IV — schemas mudam sem trocar `schema_version` porque nenhum arquivo antigo é lido
(execução nova, como em R16). VI — testes novos listados no quickstart, Nível 1. IX — nenhuma
dependência; um módulo pequeno novo (`closing.py`). X — o fechamento manual é sempre um comando dos
autores, com motivo gravado. XI — spec, research (R18, R19), data-model, contratos, quickstart e
metodologia atualizados neste ciclo; o README do módulo muda junto com o código.


**Reavaliação de fechamento (2026-10-11, contra o código de `c967f97`)**: sem violação nem desvio
novo (nada a acrescentar em "Complexity Tracking"). III — `ollama.request_body` manda uma única
mensagem (`messages: [{role: user, ...}]`), sem `context` nem histórico (conferido no código e por
`grep`); a execução completa confirma o efeito (`prompt_eval_count` só do prompt). V — `grep -rn
"memory_limit_bytes=\|time_limit_seconds=" src/ai_clients` só mostra os limites de `metadata.json`
multiplicados por `PY_TIME_FACTOR`/`PY_MEMORY_FACTOR` (`oracle.py:96-97`) ou repassados deles; nenhum
limite absoluto. VI — suíte completa `1498 passed`. VII — 44 interrupções reais retomadas sem perda
(R28). II — pacote, manifesto e `cli check --deep` `OK` (R28). X — nenhuma operação de Git pelo
agente; o código gerado com apoio de IA foi revisado por Milena em 2026-10-11 (T062).

## Project Structure

### Documentation (this feature)

```text
specs/003-slm-test-generation/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # R0–R28
├── data-model.md
├── quickstart.md
├── sync-matrix.json     # D1–D3 da spec ↔ metodologia (check_docs_sync C5)
├── contracts/
│   ├── cli.md
│   ├── file-formats.md
│   └── ai-clients-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/prompt_templates/slm_prompt.txt   # do autor; FR-007 cumprido (S5); texto revisto em R14 e R17
src/prompt_templates/slm_predict_prompt.txt  # do autor (2026-10-06); tentativas 13 a 15 (R22); STEP 2 trocado em 2026-10-08 (R27)
src/ai_clients/
├── __init__.py
├── __main__.py          # registro de subcomandos (padrão de mutation/__main__.py)
├── README.md            # template docs/template-modulo.md
├── config.py            # modelo, opções, ATTEMPT_POLICY (fase, seed, temperatura por tentativa), fatores, caminhos, padrões de timeout/teto
├── problem.py           # ProblemInput (composição S1)
├── prompt.py            # template + context_data por cenário
├── ollama.py            # SLMClient, OllamaClient, exceções
├── parser.py            # parse_response, parse_prediction (R19)
├── closing.py           # close: manual_close.json + suite.json(discarded_manual) (R19)
├── oracle.py            # run_python, python_limits, evaluate_attempt
├── store.py             # estados, escrita, finalize; travas exclusive_run, shared_run, claim (por combinação), single_execute (R24)
├── template_change.py   # change-template: registro + superseded/ (R27)
├── generation.py        # laço do generate (tentativas, espera de infraestrutura)
├── execution.py         # laço do execute
├── report.py
├── packaging.py         # zip + manifesto + verify
└── schemas/
    ├── __init__.py
    ├── run.py  generation.py  execution.py  suite.py  report.py  manifest.py
    └── template_change.py  # TemplateChange (R27)
src/cli/consistency.py   # + camada slm_suites
tests/ai_clients/
├── conftest.py          # dataset sintético empacotado e com manifesto (como tests/mutation)
├── fakes.py             # FakeSLMClient, runner Python falso, relógio falso
├── test_schemas.py  test_problem.py  test_store.py
├── test_config.py   # a tabela ATTEMPT_POLICY (R22)
├── test_concurrency.py   # dois generate, execute junto, travas (R24)
├── test_prompt.py  test_parser.py  test_parser_prediction.py  test_ollama.py
├── test_generation.py  test_cli_generate.py  test_closing.py  test_cli_close.py
├── test_oracle.py  test_execution.py  test_cli_execute.py
├── test_resume.py  test_resume_config.py  test_damage.py
├── test_report.py  test_packaging.py
├── test_template_change.py   # troca de template, superseded/ (R27)
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
| Código de saída `4`, que `mutation` não tem (R19 item 7) | "aguardando tratamento manual" é um estado esperado do fluxo, que o operador precisa distinguir de dano | reaproveitar o código 1 misturaria esse estado com dano nos arquivos |
| `extra_hosts` no serviço `app` (S6) | o Ollama do host é inalcançável do contêiner no Linux sem ela | exigir sempre um servidor remoto contrariaria FR-003 ("máquina local ou servidor remoto") |
