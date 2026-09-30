# Contract: Interface de linha de comando do módulo `ai_clients` (SLM)

**Feature**: `003-slm-test-generation` | Consumidores: os dois autores; o futuro módulo de avaliação
só lê `data/suites/slm/problems/<id>/<scenario>/suite.json` (ou `data/slm_suites.zip` da execução
final), não chama esta CLI.

Ponto de entrada: `python -m ai_clients <comando>` (pacote `src/ai_clients/`, `__main__.py`,
`argparse`, mesmo padrão de registro de `python -m mutation`: `Subcommand` + `register(...)`,
subcomandos em ordem alfabética), sempre dentro do contêiner.

## Serviços do Docker Compose

| Serviço | Rede | Usado para |
|---|---|---|
| `app` | com rede (precisa alcançar o Ollama) | `generate`, `report`, `package`, `verify` — nenhum executa código gerado pelo modelo |
| `sandbox` | **sem rede** | `execute` — roda o `reference_py` de cada tentativa via `sandbox.runner.execute` |

`generate` e `execute` nunca rodam no mesmo serviço: uma rodada completa é o operador alternando os
dois (research R8). Rodado por engano no serviço `sandbox`, `generate` não alcança o Ollama e
entra na espera de infraestrutura (R9), sem gravar nada; rodado por engano no `app`, `execute`
falha ao preparar o isolamento (`InfraError` do motor, código 3), sem gravar nada.

## Códigos de saída (iguais aos de `mutation`)

`0` sucesso · `1` falha de dados (dataset divergente do manifesto, combinação danificada, trava
ocupada, pacote/manifesto divergente) · `2` uso incorreto (opção inválida, `run.json` existente sem
`--resume`, `--resume` com configuração diferente, `.env` incompleto) · `3` falha de infraestrutura
não recuperável ou de configuração do Ollama (modelo ausente, guarda de `num_ctx`, `InfraError` do
motor) · `130` interrompido (`Ctrl+C`, `docker stop`; é seguro rodar de novo).

## Opções comuns a `generate` e `execute`

| Opção | Padrão | Efeito |
|---|---|---|
| `--problem ID` | todos os 200 | só esse problema; repetível; ID fora de `data/dataset` → código 2 |
| `--scenario S` | os 3 | `black_box`, `white_box` ou `hybrid`; repetível |
| `--limit N` | sem limite | processa no máximo `N` combinações problema × cenário **pendentes para este comando**, na ordem canônica (problema em ordem alfabética, depois `black_box`, `white_box`, `hybrid`); inteiro positivo, senão código 2. No `generate`, uma combinação conta uma vez mesmo que faça várias chamadas por falha de interpretação |
| `--dry-run` | desligado | não chama o modelo, não executa nada, **não grava nada** (nem `run.json`, nem trava); lista o que seria feito e sai com 0 |

Antes de qualquer trabalho (inclusive no `--dry-run`), os dois verificam `data/dataset` contra
`manifests/dataset.manifest.json` com `mutation.dataset_gate.verify_dataset` e saem com código 1
se divergir (Edge Case da spec).

Uma única instância por vez sobre `data/suites/slm/`: `flock` em `data/suites/slm/.lock`; um
segundo comando se recusa com código 1 (`another python -m ai_clients command is already running`).

## `generate` (serviço `app`)

Para cada combinação em `pending_generation(n)` ([data-model.md §4](../data-model.md#4-máquina-de-estados-de-uma-combinação)):
monta o prompt, faz **uma** chamada sem estado ao Ollama com a seed `42 + n`, grava
`attempt_<n>.generation.json` (resposta crua + interpretação). Se a interpretação falhar e `n < 6`,
faz na hora a tentativa `n + 1`; se `n = 6`, grava `suite.json` com `status: discarded`.

| Opção | Efeito |
|---|---|
| `--resume` | obrigatória se `data/suites/slm/run.json` já existe; sem ela o comando recusa (código 2: `a run already exists in data/suites/slm; use --resume to continue it`). Com ela, a configuração atual (modelo e `digest`, versão do Ollama, opções, seed base, SHA-256 do template e do manifesto do dataset, fatores de limite) é comparada com o `run.json`; qualquer diferença → código 2, listando campo, valor gravado e valor atual. Sem `run.json`, `--resume` também é erro (código 2: nada a retomar) |
| `--dry-run` | imprime, por combinação que seria chamada, o tamanho do prompt em caracteres e a tentativa/seed; ao fim, o maior prompt por cenário e o total de chamadas previstas; não exige `OLLAMA_BASE_URL`/`OLLAMA_HARDWARE_LABEL` |

Variáveis de ambiente (`.env`, research R12): `OLLAMA_BASE_URL` e `OLLAMA_HARDWARE_LABEL`,
obrigatórias fora do `--dry-run` (código 2 se faltarem).

Falha de infraestrutura (Ollama inacessível, *timeout*, HTTP 5xx): imprime
`ollama unavailable (<motivo>); retrying the same call (seed S) in T s` e repete a mesma chamada,
sem gravar nada e sem limite de repetições; o operador interrompe com `Ctrl+C` se quiser (código
130, retomável). Erro de configuração (HTTP 4xx, modelo ausente, `digest` diferente, guarda de
`num_ctx`): código 3, nada gravado para a tentativa.

Saída por chamada: `<id> <scenario> attempt <n> seed <s>: parsed (<k> inputs) | unparseable
(<erro>) — <prompt_eval_count>+<eval_count> tokens, <done_reason>, <duração> s`. Resumo final:
`done: N calls, N parsed, N unparseable, N discarded suites; N pending execution`.

## `execute` (serviço `sandbox`)

Para cada combinação em `pending_execution(n)`: roda o `reference_py` nos testes públicos e, se
passar em todos, em cada entrada gerada (research R7); grava `attempt_<n>.execution.json`; se
`accepted`, grava `suite.json` (`accepted`); se falhou e `n = 6`, grava `suite.json` (`discarded`).
Também grava o `suite.json` de toda combinação `finalizable` que encontrar. Não tem `--resume`: não
inicia execução nova (sem `run.json` → código 2, `run generate first`) e só processa pendências.

| Opção | Efeito |
|---|---|
| `--dry-run` | lista as tentativas pendentes de execução (id, cenário, tentativa, nº de entradas, testes públicos, limites efetivos) |

Saída por tentativa: `<id> <scenario> attempt <n>: accepted (<k> kept, <d> discarded) |
public_test_failed (test <i>: <verdict>) | all_inputs_failed (<t> timeout, <r> runtime_error)`.
Resumo final: `done: N executed, N accepted, N failed (N need a new generation), N discarded suites`.
Se sobrou combinação que precisa de nova geração, a última linha diz o comando seguinte:
`next: docker compose run --rm app python -m ai_clients generate --resume`.

## `report` (serviço `app`)

Lê `data/suites/slm/` (só leitura) e grava `manifests/slm_generation_report.json` (research R10).
Funciona com a execução incompleta (conta pendentes). Código 1 se houver combinação danificada.

## `package` (serviço `app`)

Gera `data/slm_suites.zip` (determinístico) e `manifests/slm_suites.manifest.json`. Recusa (código 1)
se alguma das 600 combinações não tiver `suite.json`, se houver dano, ou se `--problem`/`--scenario`
forem usados (não existem neste comando: o pacote é sempre da execução completa, D3).

## `verify` (serviço `app`)

| Opção | Efeito |
|---|---|
| (nenhuma) | recalcula o SHA-256 de `data/slm_suites.zip` e compara com o manifesto |
| `--extracted DIR` | também confere a árvore descompactada (tipicamente `data/suites/slm`) arquivo a arquivo (`changed:`/`missing:`/`extra:`) |

Código 0 se tudo bate, 1 se não, 2 se o manifesto não existe.

## Camada nova de `python -m cli check`

`slm_suites` (research R10): chave aceita em `--only`; ver
[file-formats.md](./file-formats.md#6-camada-slm_suites-do-cli-check).
