# Contrato da CLI: `--model claude`

**Feature**: `specs/008-claude-test-generation` | **Date**: 2026-10-20 | **Plan**: [../plan.md](../plan.md)

Os comandos dos modelos comerciais (contrato da feature 004) aceitam `claude` em `--model`, com o
mesmo comportamento, as mesmas saídas e os mesmos códigos:

```text
docker compose run --rm app python -m ai_clients generate --model claude --dry-run
docker compose run --rm app python -m ai_clients generate --model claude --confirm-spend <US$> [--resume] [--problem ID] [--scenario S] [--limit N]
docker compose run --rm app python -m ai_clients close --model claude --problem ID --scenario S --reason "..."
docker compose run --rm app python -m ai_clients change-template --model claude --template llm --reason "..."
docker compose run --rm app python -m ai_clients report --model claude
docker compose run --rm app python -m ai_clients package --model claude
docker compose run --rm app python -m ai_clients verify --model claude [--extracted data/suites/claude]
docker compose run --rm app python -m ai_clients show-request --model claude --problem ID --scenario S --output FILE [--attempt N | --barred N]
docker compose run --rm app python -m cli check [--deep] [--only claude_suites]
```

## Variáveis do `.env`

| Variável | Obrigatória | Padrão |
|---|---|---|
| `ANTHROPIC_API_KEY` | só para chamar | — |
| `ANTHROPIC_MAX_CONCURRENCY` | não | 4 |
| `ANTHROPIC_MAX_INFRA_RETRIES` | não | 30 |
| `ANTHROPIC_MAX_REQUESTS_PER_MINUTE` | não | sem limite |
| `LLM_HTTP_TIMEOUT_S` (a mesma dos outros dois) | não | 900 |

Sem `ANTHROPIC_API_KEY`, o `generate --model claude` sai com `2` e diz qual variável falta. O
dry-run não precisa dela.

## Saídas específicas

- **Linha por pedido**: a mesma da 004. O `reasoning` mostra o `thinking_tokens`.
- **Crédito esgotado** (HTTP 400 "credit balance"): `configuration error: claude: the credit of the
  account is exhausted (...)`, saída `3`.
- **Prompt acima de 100 mil tokens**: o cálculo de custo recusa, com `3` e a mensagem
  `claude: a prompt over 100,000 tokens has another price (...)`. Não deve acontecer neste dataset.
