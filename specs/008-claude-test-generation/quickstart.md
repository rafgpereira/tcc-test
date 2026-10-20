# Quickstart: validar o terceiro modelo comercial (Claude)

**Feature**: `specs/008-claude-test-generation` | **Date**: 2026-10-20

## 1. Sem custo

```bash
docker compose run --rm sandbox pytest -q tests/ai_clients/llm tests/cli
docker compose run --rm app python -m ai_clients generate --model claude --dry-run
docker compose run --rm app python -m ai_clients generate --model claude --dry-run --save-requests data/requests --force
```

O que se espera:
- os testes passam, e os testes dos outros modelos continuam passando;
- o dry-run mostra 600 combinações e a faixa de custo, sem chave;
- o `summary.json` dos pedidos salvos diz que todos os prompts são fiéis ao dataset, com o mesmo
  `template_sha256` dos outros dois.

## 2. Piloto (pago; só com pedido explícito dos autores)

```bash
docker compose run --rm app python -m cli check --deep --only dataset
docker compose run --rm app python -m ai_clients generate --model claude --limit 1 --confirm-spend 1
```

Na primeira resposta, `data/suites/claude/problems/<id>/<cenário>/attempt_1.json` deve ter
`usage.reasoning_tokens` maior que 0 e o bloco `thinking` no `raw_body`. Se ela tiver ido para
`barred/`, o motivo está no arquivo; investigue antes de seguir (research R2).

```bash
docker compose run --rm app python -m ai_clients generate --model claude --resume --confirm-spend 2 \
  --problem 1000_B --problem 1005_C --problem 1008_B --problem 1_B --problem 61_B
docker compose run --rm app python -m ai_clients report --model claude
cp manifests/claude_generation_report.json manifests/claude_generation_report.piloto1.json
mv data/suites/claude data/suites/claude-piloto1
```

Do relatório, registre:
- a razão caracteres/token;
- a média de tokens de saída;
- a latência;
- a taxa de falha de formato e a de respostas sem raciocínio;
- o custo real, comparado com o dry-run.

## 3. Execução completa

```bash
docker compose run --rm app python -m ai_clients generate --model claude --confirm-spend <US$>
docker compose run --rm app python -m ai_clients report --model claude
docker compose run --rm app python -m ai_clients package --model claude
docker compose run --rm app python -m ai_clients verify --model claude --extracted data/suites/claude
docker compose run --rm app python -m cli check --deep
```

Esperado: 600 combinações encerradas e `Resultado: OK`.
