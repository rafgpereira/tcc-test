# Data Model: Terceiro modelo comercial: Claude

**Feature**: `specs/008-claude-test-generation` | **Date**: 2026-10-20 | **Plan**: [plan.md](./plan.md)

O Claude não cria nenhuma entidade nova. Ele usa os schemas da feature 004
(`specs/004-llm-test-generation/data-model.md`), com estas mudanças.

## 1. Valores novos

| Onde | Antes | Depois |
|---|---|---|
| `LlmModel` (schemas) | `"gpt" \| "gemini"` | `"gpt" \| "gemini" \| "claude"` |
| `config.MODELS` | `("gpt", "gemini")` | `("gpt", "gemini", "claude")` |
| `PriceRow` da execução | GPT e Gemini | mais `claude`, válida desde 2026-10-20: 0,10 / 0,01 / 0,50 (research R4) |

## 2. `data/suites/claude/run.json` (`LlmRunConfig`)

O schema é o mesmo. Para o Claude:

| Campo | Valor |
|---|---|
| `model_key` | `"claude"` |
| `model_requested` | `"claude-haiku-5-5"` |
| `endpoint` | `"https://api.anthropic.com/v1/messages"` |
| `request_parameters` | o corpo de research R1 com o prompt trocado por `<prompt>` (`max_tokens` 32768, `thinking.type` `adaptive`, `output_config.effort` `medium`, `output_config.format`) |
| `response_schema` | o mesmo dos outros dois |
| `template_sha256` | o mesmo dos outros dois (`llm_prompt.txt`) |
| `dataset_manifest_sha256` | o da revisão 2 |

A conferência dos parâmetros proibidos (`FORBIDDEN_PARAMETERS`) vale para o corpo do Claude: nada
de `temperature`, `top_p`, `top_k`, `system`, etc.

## 3. Tentativa e resposta barrada

O schema é o mesmo (`LlmAttempt`, `BarredResponse`). O `raw_body` guarda a resposta inteira da
Anthropic, inclusive os blocos `thinking`. O mapeamento dos campos está em research R3 e R4:

| Campo | De onde vem |
|---|---|
| `model_returned` | `model` |
| `response_id` | `id` |
| `finish.status` | `stop_reason` |
| `finish.reason` | `stop_details.category` (só quando há recusa) |
| `usage.input_tokens` | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` |
| `usage.cached_input_tokens` | `cache_read_input_tokens` |
| `usage.output_tokens` | `output_tokens` (inclui o raciocínio) |
| `usage.reasoning_tokens` | `output_tokens_details.thinking_tokens`, ou `None` se o campo não vier |

Regra de resposta sem raciocínio: `reasoning_tokens` 0 ou `None` leva a resposta para `barred/`,
pela regra emendada da 004.

## 4. Suíte, relatório, pacote

Não mudam. Os nomes são por modelo:
- `data/claude_suites.zip`;
- `manifests/claude_suites.manifest.json` (os caminhos começam com `suites/claude/`);
- `manifests/claude_generation_report.json`.

A camada `claude_suites` do `cli check` é a mesma das outras duas camadas de modelos comerciais.
