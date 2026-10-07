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
| `app` | com rede (precisa alcançar o Ollama) | `generate`, `close`, `report`, `package`, `verify` — nenhum executa código gerado pelo modelo |
| `sandbox` | **sem rede** | `execute` — roda o `reference_py` de cada tentativa via `sandbox.runner.execute` |

`generate` e `execute` nunca rodam no mesmo serviço: uma rodada completa é o operador alternando os
dois (research R8). Rodado por engano no serviço `sandbox`, `generate` não alcança o Ollama e
entra na espera de infraestrutura (R9), sem gravar nada; rodado por engano no `app`, `execute`
falha ao preparar o isolamento (`InfraError` do motor, código 3), sem gravar nada.

## Códigos de saída (os de `mutation`, mais o `4`)

`0` sucesso · `1` falha de dados (dataset divergente do manifesto, combinação danificada, trava
ocupada, pacote/manifesto divergente) · `2` uso incorreto (opção inválida, `run.json` existente sem
`--resume`, `--resume` com configuração diferente, `.env` incompleto, `close` sobre uma combinação
que não aguarda tratamento manual) · `3` falha de infraestrutura
não recuperável ou de configuração do Ollama (modelo ausente, guarda de `num_ctx`, `InfraError` do
motor) · `4` (desde 2026-10-06, research R19 item 7) o comando terminou, mas há combinação da
seleção aguardando tratamento manual · `130` interrompido (`Ctrl+C`, `docker stop`; é seguro rodar
de novo). Precedência: `130`, `3` e `1` vencem o `4`; as linhas `manual:` saem mesmo assim.

## Execução de uma versão anterior (desde 2026-10-06, R22 item 4)

Se `data/suites/slm/run.json` existe mas não é de `schema_version` 2 (os pilotos 1 a 5),
`generate`, `execute`, `close`, `report` e `package` saem com código 2, sem ler nem gravar nada:
`error: data/suites/slm holds a run of an older version of python -m ai_clients (it cannot be
resumed nor read); move it away first: mv data/suites/slm data/suites/slm-<name>`. Antes do
piloto 6, `data/suites/slm` (o piloto 5) precisa ser movida.

## Opções comuns a `generate` e `execute`

| Opção | Padrão | Efeito |
|---|---|---|
| `--problem ID` | todos os 200 | só esse problema; repetível; ID fora de `data/dataset` → código 2 |
| `--scenario S` | os 3 | `black_box`, `white_box` ou `hybrid`; repetível |
| `--limit N` | sem limite | processa no máximo `N` combinações problema × cenário **pendentes para este comando**, na ordem canônica (problema em ordem alfabética, depois `black_box`, `white_box`, `hybrid`); inteiro positivo, senão código 2. No `generate`, uma combinação conta uma vez mesmo que faça várias chamadas por falha de interpretação |
| `--dry-run` | desligado | não chama o modelo, não executa nada, **não grava nada** (nem `run.json`, nem trava); lista o que seria feito e sai com 0 |

Antes de qualquer trabalho (inclusive no `--dry-run`), os dois verificam `data/dataset` contra
`manifests/dataset.manifest.json` com `mutation.dataset_gate.verify_dataset` e saem com código 1
se divergir (Edge Case da spec). `manifests/dataset.manifest.json` ausente (`FileNotFoundError` do
portão) também sai com código 1, com a mesma orientação de restauração
(`unzip data/dataset.zip -d data/`).

Comandos ao mesmo tempo sobre `data/suites/slm/` (desde 2026-10-07, research R24, data-model §5):
vários `generate --resume` e um `execute` podem rodar juntos — cada combinação é tratada por um
processo de cada vez, e a que estiver em uso por outro é pulada (linha `<id> <cenário>: skipped (in
use by another command)`) e contada no fim do resumo (`; N skipped (in use by another command)`, só
quando N > 0); um segundo `execute`, e `generate` sem `--resume`, `close` e `package`
enquanto outro comando roda, recusam com código 1 (`another python -m ai_clients command is already
running over data/suites/slm/`). Até 2026-10-07 era um comando por vez.

## `generate` (serviço `app`)

Para cada combinação em `pending_generation(n)` ([data-model.md §4](../data-model.md#4-máquina-de-estados-de-uma-combinação)):
monta o prompt com o template da linha `n` do `attempt_policy` do `run.json` (o principal nas
tentativas 1 a 12, o de predição, `src/prompt_templates/slm_predict_prompt.txt`, nas 13 a 15), faz
**uma** chamada sem estado ao Ollama com a seed e a temperatura dessa linha (data-model §2) e grava
`attempt_<n>.generation.json` (resposta crua, interpretação, fase, seed, temperatura, template).
Se a interpretação falhar, faz na hora a tentativa `n + 1`, a menos que a combinação tenha ficado
`finalizable` ou `awaiting_manual` (data-model §4). Uma tentativa por predição interpretada vira
`suite.json` (`accepted_predicted`) na hora, sem passar pelo `execute`. Toda vez que grava um
`suite.json` imprime `<id> <scenario>: suite recorded (<status>)`.

| Opção | Efeito |
|---|---|
| `--resume` | obrigatória se `data/suites/slm/run.json` já existe; sem ela o comando recusa (código 2: `a run already exists in data/suites/slm; use --resume to continue it`). Com ela, a configuração atual — todos os campos do `RunConfig` exceto `created_at` ([data-model.md §3.1](../data-model.md#31-runconfig--datasuitesslmrunjson-1-por-execução)) — é comparada com o `run.json`; qualquer diferença → código 2, listando campo, valor gravado e valor atual. Sem `run.json`, `--resume` também é erro (código 2: nada a retomar) |
| `--dry-run` | imprime, por combinação que seria chamada, o tamanho do prompt em caracteres e a tentativa/seed; ao fim, o maior prompt por cenário e o total de chamadas previstas; não exige `OLLAMA_BASE_URL`/`OLLAMA_HARDWARE_LABEL` |

Variáveis de ambiente (`.env`, research R12): `OLLAMA_BASE_URL` e `OLLAMA_HARDWARE_LABEL`,
obrigatórias fora do `--dry-run` (código 2 se faltarem); `OLLAMA_HTTP_TIMEOUT_S` (padrão 900; desde 2026-10-07 o maior silêncio entre dois pedaços da resposta, R25) e
`OLLAMA_MAX_INFRA_RETRIES` (padrão 30), opcionais — valor que não é inteiro positivo → código 2.
`OLLAMA_MODEL`, opcional (desde 2026-10-05, R15): outro modelo do Ollama para um piloto que compara
modelos (padrão `qwen2.5-coder:7b`); vai para o `run.json`, e o `--resume` recusa um modelo
diferente do gravado (código 2).

Falha de infraestrutura (Ollama inacessível, *timeout*, HTTP 5xx — inclusive o 524 de um proxy —, túnel do ngrok fora do ar — HTTP de erro com `ERR_NGROK_` no corpo —, resposta em *streaming* que termina antes do último pedaço, desde 2026-10-07): imprime
`ollama unavailable (<motivo>); retrying the same call (seed S) in T s (retry k of N)` e repete a
mesma chamada, sem gravar nada, até `OLLAMA_MAX_INFRA_RETRIES` repetições consecutivas; atingido o
teto, sai com código 3 (`ollama unavailable after N consecutive retries (<motivo>); nothing was
recorded for <id> <scenario> attempt <n>; run generate --resume when the service is back`), sem
consumir tentativa. O operador também pode interromper antes com `Ctrl+C` (código 130). Nos dois
casos a retomada refaz a mesma chamada com a mesma seed. Erro de configuração (HTTP 4xx, modelo ausente, `digest` diferente, guarda de
`num_ctx`): código 3, nada gravado para a tentativa. Exceção (desde 2026-10-04, research R13): o
HTTP 500 com `token repeat limit reached` no corpo é falha do modelo, não de infraestrutura — grava
a tentativa como falha `repetition` e segue para a próxima seed, sem esperar.

Saída por chamada: `<id> <scenario> attempt <n> seed <s>: parsed (<k> inputs) | unparseable
(<erro>) — <prompt_eval_count>+<eval_count> tokens, <done_reason>, <duração> s`, ou
`<id> <scenario> attempt <n> seed <s>: model failure (repetition) — <erro do Ollama>`; numa
tentativa por predição, `parsed (<k> tests)` no lugar de `parsed (<k> inputs)`. Resumo final
(desde 2026-10-06): `done: N calls, N parsed, N unparseable, N repetition; suites: N
accepted_fallback, N accepted_predicted; N pending execution, N awaiting
manual handling`.

Combinações aguardando tratamento manual (desde 2026-10-06): depois do resumo, uma linha em
`stderr` por combinação da seleção nesse estado, inclusive as que já estavam assim antes deste
comando — `manual: <id> <scenario>: 3 prediction attempts unparseable; close it with: docker compose
run --rm app python -m ai_clients close --problem <id> --scenario <scenario> --reason "<motivo>"`
— e saída com código 4.

## `execute` (serviço `sandbox`)

Para cada combinação em `pending_execution(n)` (só tentativas 1 a 12): roda o `reference_py` nos
testes públicos (até o primeiro não-AC) e, se passar em todos ou se o primeiro erro for WA, em cada
entrada gerada (research R7, R22 item 6); grava `attempt_<n>.execution.json`; se `accepted`, grava
`suite.json` (`accepted`); se a 12ª falhou e alguma das 12 pode ser reserva, grava `suite.json`
(`accepted_fallback`) e imprime `<id> <scenario>: suite recorded (<status>)`. Sem reserva depois
da 12ª, a combinação volta para o `generate` (predição, tentativa 13). As suítes por predição não
passam por aqui: o `generate` as grava direto da resposta.
Também grava o `suite.json` de toda combinação `finalizable` que encontrar. Não tem `--resume`: não
inicia execução nova (sem `run.json` → código 2, `run generate first`) e só processa pendências.

| Opção | Efeito |
|---|---|
| `--dry-run` | lista as tentativas pendentes de execução (id, cenário, tentativa, nº de entradas, testes públicos, limites efetivos): `<id> <scenario> attempt <n>: <k> inputs, <p> public tests, limits <t> s and <m> MiB`, e no fim `dry run: N attempts to execute`; também exige o `run.json` |

Saída por tentativa: `<id> <scenario> attempt <n>: accepted (<k> kept, <d> discarded) |
public_test_failed (test <i>: <verdict>; <k> kept, <d> discarded) | all_inputs_failed (<t>
timeout, <r> runtime_error)` (desde 2026-10-06 toda reprovação em teste público traz as
contagens),
com `, <u> non_utf8_output` acrescentado ao último caso quando houver. Uma combinação
`finalizable` (interrompida entre a execução e o `suite.json`) imprime
`<id> <scenario> attempt <n>: suite recorded (<status>)` e **não** conta para o `--limit` (não há
nada a executar). O `generate` também grava, sem chamar o modelo, o `suite.json` de toda
combinação `finalizable` que encontrar (data-model §4: "quem encontrar grava").

## Combinação danificada (`generate`, `execute`, `report`)

Antes de decidir o que fazer com uma combinação, o comando lê e confere todos os arquivos dela;
qualquer divergência é dano (data-model §4): a combinação não é tocada, os demais seguem, e ao fim
o comando imprime em `stderr` uma linha `damaged: <id> <scenario>: <problema>; <problema>…` por
combinação — cada problema começa com `missing:` (arquivo de tentativa que falta), `changed:`
(`suite.json` diferente, byte a byte, do que os arquivos de tentativa dão) ou `inconsistent:`
(JSON inválido, schema violado — inclusive seed que não bate —, arquivo que fala de outra
combinação, `model_digest` diferente do `run.json`, execução de tentativa não interpretada, número
de entradas diferente do da geração, tentativa depois de uma aceita, tentativa além da 23ª,
fase, seed, temperatura ou template diferentes da linha da tentativa no `attempt_policy`,
tentativa além da 15ª, tentativa 13 ou mais com uma reserva possível entre as 12, execução de uma
tentativa por predição, entradas executadas depois de RE/TLE/MLE, `manual_close.json` numa
combinação que não aguarda tratamento manual, arquivo estranho na pasta) — e sai com código 1. Temporários de escrita atômica deixados por um
`kill -9` (`.<nome>.<sufixo>.tmp`) são ignorados, nunca lidos.

Mensagem do `--resume` com configuração diferente (código 2): `the configuration differs from
data/suites/slm/run.json, and a run never mixes configurations:` seguida de uma linha
`  <campo>: recorded <valor gravado>, current <valor atual>` por campo (os de `options` como
`options.<nome>`).
Resumo final (desde 2026-10-06): `done: N executed, N accepted, N failed (N need a new
generation); suites: N accepted_fallback; N awaiting manual handling`,
seguido das linhas `manual:` e do código 4 nas mesmas condições do `generate`.
Se sobrou combinação que precisa de nova geração, a última linha diz o comando seguinte, com a
mesma seleção (`--problem`, ordenados e sem repetição, e `--scenario`, na ordem canônica) com que o
`execute` foi chamado (desde 2026-10-04):
`next: docker compose run --rm app python -m ai_clients generate --resume [--problem ID ...] [--scenario S ...]`.

## `close` (serviço `app`, desde 2026-10-06)

Fecha **uma** combinação que aguarda tratamento manual (FR-022d, research R19 item 8): grava
`manual_close.json` (`reason`, `closed_at`) e, em seguida, `suite.json` (`discarded_manual`), e
imprime `<id> <scenario>: suite recorded (discarded_manual)`. Usa a trava e a verificação do
dataset como os demais; exige o `run.json` (sem ele, código 2). Não chama o modelo nem executa nada.

| Opção | Efeito |
|---|---|
| `--problem ID` | obrigatória, uma só |
| `--scenario S` | obrigatória, uma só |
| `--reason TEXTO` | obrigatória; vazia ou só espaços → código 2 |
| `--dry-run` | mostra o `manual_close.json` que seria gravado e não grava nada |

Combinação em qualquer outro estado → código 2: `<id> <scenario> is <estado>, not awaiting manual
handling; nothing was recorded`.

## `report` (serviço `app`)

Lê `data/suites/slm/` (só leitura) e grava `manifests/slm_generation_report.json` (research R10,
R19 item 10). Funciona com a execução incompleta (conta pendentes e as que aguardam tratamento
manual, sem código 4). Código 1 se houver combinação danificada.

## `package` (serviço `app`)

Gera `data/slm_suites.zip` (determinístico) e `manifests/slm_suites.manifest.json`. Recusa (código 1)
se alguma das 600 combinações não tiver `suite.json` — inclusive as que aguardam tratamento manual,
listadas com o comando `close` — ou se houver dano. Não tem `--problem` nem
`--scenario`: o pacote é sempre da execução completa (D3), e passar uma dessas opções é erro de uso
do `argparse` (código 2).

## `verify` (serviço `app`)

| Opção | Efeito |
|---|---|
| (nenhuma) | recalcula o SHA-256 de `data/slm_suites.zip` e compara com o manifesto |
| `--extracted DIR` | também confere a árvore descompactada (tipicamente `data/suites/slm`) arquivo a arquivo (`changed:`/`missing:`/`extra:`) |

Código 0 se tudo bate, 1 se não, 2 se o manifesto não existe.

## Camada nova de `python -m cli check`

`slm_suites` (research R10): chave aceita em `--only`; ver
[file-formats.md](./file-formats.md#6-camada-slm_suites-do-cli-check).

## Duas GPUs (desde 2026-10-07, research R23 e R24)

Dois `generate --resume` em paralelo, cada um com seu `OLLAMA_BASE_URL` (`docker compose run -e
OLLAMA_BASE_URL=...`, que tem prioridade sobre o `.env`) e metades disjuntas dos problemas
(`--problem`), e um único `execute` depois que os dois terminam; repetir enquanto o `execute`
imprimir `next:`. O laço em bash fica no README do módulo.
