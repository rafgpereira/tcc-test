# Contrato do provedor: Anthropic Messages API

**Feature**: `specs/008-claude-test-generation` | **Date**: 2026-10-20 | **Plan**: [../plan.md](../plan.md)

Implementa o mesmo `LLMProvider` da 004: `request_body(prompt)` e `call(prompt)`, que devolve
um `ProviderAnswer`.

## Pedido

`POST https://api.anthropic.com/v1/messages`, com os cabeçalhos `x-api-key: <chave>`,
`anthropic-version: 2023-06-01` e `content-type: application/json`. O corpo é o de research R1,
serializado com chaves ordenadas, como os outros dois.

## Resposta HTTP 200

| `ProviderAnswer` | Origem |
|---|---|
| `text` | os blocos `type == "text"` concatenados; `None` se não houver |
| `refusal` | o texto da resposta quando `stop_reason == "refusal"` (vazio se não houver) |
| `finish.status` | `stop_reason` |
| `finish.reason` | `stop_details.category` |
| `usage` | research R4 |
| `model_returned`, `response_id` | `model`, `id` |

Um corpo 200 que não é um objeto JSON é falha de infraestrutura, como nos outros dois.

## Interpretação

| Condição | Resultado |
|---|---|
| `reasoning_tokens` 0 ou `None` | resposta barrada (regra emendada da 004) |
| `stop_reason` `max_tokens` ou `model_context_window_exceeded` | falha `truncated` |
| `stop_reason` `refusal` | falha `refusal` |
| depois disso | as conferências de texto e de testes da 004, sem mudança |

## Erros

Os da research R5.
