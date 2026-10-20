# Contract: Linha de comando dos LLMs comerciais (`python -m ai_clients ... --model gpt|gemini`)

**Feature**: `004-llm-test-generation` | Estados e arquivos: [data-model.md](../data-model.md) |
Pedidos HTTP: [providers.md](./providers.md)

O ponto de entrada é o mesmo do SLM, `python -m ai_clients <comando>`, sempre no serviço `app`,
que tem rede. Os subcomandos existentes ganham a opção **`--model {slm,gpt,gemini}`**, com padrão
`slm`. Sem ela, todo comando faz exatamente o que faz hoje (FR-029). O `execute` é só do SLM: com
`--model gpt` ou `--model gemini`, sai com código 2 (`the commercial models run nothing: there is
no execute step`).

## Códigos de saída

| Código | Situação |
|---|---|
| `0` | sucesso |
| `1` | falha de dados: dataset divergente, combinação danificada, trava ocupada, pacote divergente |
| `2` | uso incorreto: opção inválida, `.env` incompleto, `--resume` com configuração diferente, falta de confirmação ou teto |
| `3` | erro de infraestrutura não recuperável (teto de repetições) ou erro que não passa sozinho (chave, cota, modelo, pedido malformado) |
| `4` | o comando terminou, mas há combinação aguardando os autores |
| `5` **(novo)** | teto de gasto atingido (FR-022a) |
| `6` **(novo)** | resposta sem raciocínio barrada (FR-018a); **sem uso desde 2026-10-20**: a combinação é pedida de novo, até 3 barradas, e fica `accepted_barred`; o comando segue |
| `130` | interrompido |

Precedência: `130` > `3` > `6` > `1` > `5` > `4` > `0`. As linhas `manual:`, `damaged:` e o gasto
da invocação saem sempre.

## `.env`

| Variável | Obrigatória | Padrão | Efeito |
|---|---|---|---|
| `OPENAI_API_KEY` | para `generate --model gpt` fora do dry-run | — | chave da OpenAI |
| `GEMINI_API_KEY` | para `generate --model gemini` fora do dry-run | — | chave do Gemini |
| `OPENAI_MAX_CONCURRENCY`, `GEMINI_MAX_CONCURRENCY` | não | `4` | chamadas simultâneas por processo (A5) |
| `OPENAI_MAX_INFRA_RETRIES`, `GEMINI_MAX_INFRA_RETRIES` | não | `30` | repetições seguidas por falha de infraestrutura (FR-018) |
| `LLM_HTTP_TIMEOUT_S` | não | `900` | maior espera pela resposta de uma chamada |
| `OPENAI_MAX_REQUESTS_PER_MINUTE`, `GEMINI_MAX_REQUESTS_PER_MINUTE` | não | sem limite | no máximo tantos inícios de pedido por minuto no processo, repetições incluídas, espaçados por 60/N s (desde 2026-10-16; research R7) |

Um valor que não é inteiro positivo dá código 2. Uma chave ausente dá código 2 só para o modelo
dela (Edge Case: o outro modelo roda normalmente). Nenhuma chave aparece em arquivo gravado nem em
log (FR-005).

## `generate --model gpt|gemini`

| Opção | Efeito |
|---|---|
| `--problem ID` (repetível), `--scenario S` (repetível), `--limit N` | o mesmo do SLM; valem também para a estimativa (FR-022) |
| `--resume` | obrigatória se `data/suites/<m>/run.json` existe; compara a configuração (data-model §3.1) e recusa com código 2, listando cada campo diferente |
| `--dry-run` | não chama nenhuma API, não grava nada e não exige chave; imprime a estimativa (abaixo) e sai com 0. Com `--save-requests DIR` (feature 005, `specs/005-show-request/contracts/cli.md`), grava também os pedidos que seriam enviados em `DIR/<modelo>/`, com a conferência contra o dataset, e só ali |
| `--confirm-spend USD` | **a confirmação da invocação e o teto de gasto, juntos** (FR-022, FR-022a); número positivo em dólares. Sem ela, e fora do `--dry-run`, o comando imprime a estimativa e recusa com código 2 antes de qualquer chamada: `error: this would make up to K paid calls (estimated US$ X to Y); to confirm, run again with --confirm-spend <max US$ for this run>`. O teto vale **por processo**: dois `generate --resume` do mesmo modelo rodando juntos podem gastar até a soma dos dois tetos, e o `--help` e o README dizem isso |

Antes de qualquer trabalho, inclusive no dry-run:
1. confere o dataset contra o manifesto (código 1 se divergir);
2. lê o texto-base (`src/prompt_templates/llm_prompt.txt`);
3. monta a configuração.

**Estimativa** (dry-run e recusa; research R9), uma linha por cenário e o total:
`<m> <cenário>: N combinations, N calls (up to 3N), ~T input tokens (CHARS_PER_TOKEN=r <origem>),
output <teto> max[ / <média> measured]; US$ <mín>–<máx>`, e a linha `total: ...`.

**Saída por chamada:**

```text
<id> <cenário> attempt <n>: parsed (<k> tests) | <falha> (<detalhe>) — in <i> (cache <c>) out <o> (reasoning <r>) tokens, US$ <custo>, <s> s
```

- **Suíte gravada:** `<id> <cenário>: suite recorded (accepted_predicted)`.
- **Falha de infraestrutura:** `<m> unavailable (<motivo>); retrying the same call in T s (retry k of N)`.
- **Combinação em uso por outro processo:** `<id> <cenário>: skipped (in use by another command)`.

**Resumo final:**

```text
done: N calls, N parsed, N format failures; suites: N accepted_predicted; N awaiting manual handling; spent US$ X (cap US$ Y)
```

Depois do resumo vêm, conforme o caso:

| Situação | Mensagem | Código |
|---|---|---|
| combinação aguardando os autores | `manual: <id> <cenário>: 3 attempts failed by format; close it with: docker compose run --rm app python -m ai_clients close --model <m> --problem <id> --scenario <cenário> --reason "<motivo>"` | 4 |
| teto de gasto atingido | `spend cap reached: spent US$ X of US$ Y (US$ Z over the cap by the calls already in flight); nothing new was sent; continue with: ... generate --model <m> --resume --confirm-spend <novo teto>` | 5 |
| resposta sem raciocínio | `barred: <id> <cenário>: the answer reports 0 reasoning tokens (reasoning effort "medium" was sent); saved in data/suites/<m>/barred/...; nothing new was sent; investigate before resuming` | 6 |
| teto de repetições | `<m> unavailable after N consecutive retries (<motivo>); nothing was recorded for <id> <cenário> attempt <n>; run generate --model <m> --resume when the service is back` | 3 |
| erro que não passa sozinho | `error: <m>: <o que corrigir> (HTTP <código>: <mensagem da API>)` | 3 |

## `close --model gpt|gemini`, `change-template --model gpt|gemini --template llm`

Têm o mesmo contrato do SLM (`specs/003-slm-test-generation/contracts/cli.md`), com estas
diferenças:
- **`close`:** fecha uma combinação em `awaiting_manual` (3 falhas de formato).
- **`change-template`:** com o modelo, aceita só `--template llm` e move as tentativas feitas com o
  texto-base antigo.

## `report`, `package`, `verify --model gpt|gemini`

| Comando | Lê / grava | Particularidades |
|---|---|---|
| `report` | grava `manifests/<m>_generation_report.json` | funciona com a execução incompleta; código 1 se houver dano |
| `package` | grava `data/<m>_suites.zip` e `manifests/<m>_suites.manifest.json` | recusa (código 1) se alguma das 600 combinações **desse modelo** não tiver `suite.json` (as pendências do outro modelo não contam; A7) ou se houver dano |
| `verify [--extracted DIR]` | só lê | confere o zip do modelo e, opcionalmente, a árvore descompactada, contra o manifesto dele |

## `python -m cli check`

Ganha duas camadas, `gpt_suites` e `gemini_suites` (`--only gpt_suites`), com as regras da
`slm_suites` adaptadas a 3 tentativas e a `barred/` (research R11).
