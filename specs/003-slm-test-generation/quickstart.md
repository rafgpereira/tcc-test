# Quickstart: validar a geração de suítes pelo SLM ponta a ponta

**Feature**: `003-slm-test-generation` | Contratos: [cli.md](./contracts/cli.md),
[ai-clients-api.md](./contracts/ai-clients-api.md), [file-formats.md](./contracts/file-formats.md).

Roteiro de aceite, do mais barato ao mais caro. Os comandos só existem depois de `/speckit-tasks` +
`/speckit-implement`. Nenhum código gerado pelo modelo roda fora do serviço `sandbox`.

## Pré-requisitos

- Ambiente preparado conforme o [README da raiz](../../README.md) (mesma imagem; **nenhuma
  dependência Python nova**).
- `data/dataset/` descompactado e conferido: `docker compose run --rm app python -m cli check --only dataset --deep`.
- Para os níveis 3 em diante: um Ollama acessível com o modelo baixado (`ollama pull
  qwen2.5-coder:7b`) e, no `.env`, `OLLAMA_BASE_URL` e `OLLAMA_HARDWARE_LABEL` (research R12). Se o
  Ollama está na própria máquina Linux, o serviço `app` precisa do `extra_hosts` de research R12.

## Nível 0 — Interpretador isolado disponível ao slot

```bash
docker compose run --rm sandbox pytest tests/ai_clients/test_oracle_integration.py -k interpreter
```

Esperado: o CPython base (`/opt/python/.../python3.11`) executa como uid de slot com `-I -B -X
utf8`, sem `venv` no caminho (`import pydantic` falha dentro do programa de teste), confirmando
permissões de leitura/execução do `/opt/python` e o limite de memória com os fatores de R7.

## Nível 1 — Suíte do módulo com cliente Ollama falso (sem rede, sem modelo)

```bash
docker compose run --rm sandbox pytest tests/ai_clients
```

Esperado: tudo passa, cobrindo (Princípio VI): parser (tabela de casos do contrato); montagem do
prompt (3 cenários só diferem em `<context_data>`, few-shot = primeiro teste público); cliente sem
estado (uma mensagem por requisição, sem `context`); a tabela de tentativas exata (seeds 42 a 47 a
0,7; seed 48 de 0,7 a 0,2; predição 49 a 51 a 0,7), sem par (seed, temperatura) repetido, enviada
em cada pedido; falha de interpretação encadeando a próxima tentativa no mesmo `generate`; falha de
infraestrutura repetindo a mesma seed sem consumir tentativa (relógio falso); guarda de `num_ctx`;
descarte de entrada isolada vs. tentativa inteira; nunca suíte de tamanho zero; entradas rodando só
depois de WA; parada na primeira `accepted` na fase 1 e na fase 2; 12 falhas com um WA →
`accepted_fallback` da melhor (fase 3); 12 falhas sem reserva → predição direto (tentativa 13) →
`accepted_predicted`; 3 predições não interpretáveis → `awaiting_manual`, linhas `manual:` e código
4; `close` → `discarded_manual`; `package` recusando enquanto houver combinação aguardando; parser
da predição (com a cerca em `<input>`/`<output>`); `run.json` de versão anterior recusado com
código 2; `--resume` recusando configuração alterada (inclusive o template de predição);
retomada depois de interrupção simulada em cada ponto de escrita e no meio de cada fase (mesmos bytes finais que a execução
ininterrupta, SC-004); `--dry-run` não grava nada; `--limit`; relatório somando certo; pacote
determinístico e `verify` (byte alterado, arquivo removido, arquivo extra); camada `slm_suites` do
`cli check`.

## Nível 2 — Documentação e lint

```bash
docker compose run --rm app python scripts/check_docs_sync.py
docker compose run --rm app ruff check .
docker compose run --rm app black --check .
```

## Nível 3 — Dry-run sobre os 200 problemas (sem chamar o modelo)

```bash
docker compose run --rm app python -m ai_clients generate --dry-run
```

Esperado: 600 chamadas previstas (tentativa 1, seed 42), maior prompt por cenário igual à medição de
research R3 com o prompt real (8.118 caracteres no híbrido, `61_B`, medido em 2026-09-30); nada gravado em `data/suites/`.

## Nível 4 — Piloto real pequeno (Ollama de verdade)

```bash
docker compose run --rm app python -m ai_clients generate --limit 9
docker compose run --rm sandbox python -m ai_clients execute
docker compose run --rm app python -m ai_clients generate --resume --limit 9
docker compose run --rm sandbox python -m ai_clients execute
docker compose run --rm app python -m ai_clients report
```

Verificar e **propagar para a metodologia** (Princípio XI): maior `prompt_eval_count` real (guarda de
`num_ctx` nunca disparou?), taxa de `unparseable_response` e de `done_reason = "length"` (efeito da
redação de FR-007 no template, research R5a), taxa de `public_test_failed`, tamanho das suítes, tempo por chamada
no hardware registrado, e se alguma solução correta falhou por limite nos problemas de 61 MiB
(fatores de R7). Incluir no piloto ao menos um dos 7 problemas de 61 MiB (`--problem`). Desde
2026-10-06 (research R19), medir também: quantas combinações chegam a cada status, o tempo do
`execute` nas tentativas que reprovam um teste público por TLE (as entradas passam a rodar) e, se
alguma combinação chegar à predição, o tamanho da resposta e o tempo da chamada.

## Nível 5 — Retomada com o motor e o modelo reais (SC-004)

Interromper `generate` com `Ctrl+C` durante uma chamada e `execute` no meio de uma tentativa; rodar
de novo (`generate --resume` / `execute`); conferir que não há arquivo duplicado nem truncado, que a
tentativa interrompida foi refeita com a **mesma** seed e que `cli check --only slm_suites` não
aponta dano.

## Nível 6 — Execução completa, pacote e conferência

Alternar `generate --resume` e `execute` até o `execute` não sugerir mais `next:`. Se algum dos
dois sair com código 4, os autores decidem cada combinação listada e a fecham com `docker compose
run --rm app python -m ai_clients close --problem <id> --scenario <cenário> --reason "<motivo>"`.
Depois:

```bash
docker compose run --rm app python -m ai_clients report
docker compose run --rm app python -m ai_clients package
docker compose run --rm app python -m ai_clients verify --extracted data/suites/slm
docker compose run --rm app python -m cli check --deep
docker compose run --rm app python scripts/check_docs_sync.py --closing
```

Esperado: 600 combinações terminais (SC-001), proporção de cada status reportada à parte com
N = 200 (SC-003),
`verify` e `check --deep` `OK`, `--closing` com código 0 (SC-008).

## Nível 7 — Duas GPUs (desde 2026-10-07, research R23 e R24)

Primeiro passo, obrigatório: `docker compose run --rm app python -m cli check --deep` com saída 0.
Depois, o laço do README do módulo: dois `generate --resume` em paralelo (um `OLLAMA_BASE_URL` por
GPU, metades disjuntas dos problemas, logs separados), um único `execute`, repetido enquanto houver
`next:`, e o `report` no fim. Esperado: nenhum `skipped` com metades disjuntas; a contagem de
chamadas por etiqueta de hardware soma as duas GPUs (a etiqueta é a mesma nos dois processos).
