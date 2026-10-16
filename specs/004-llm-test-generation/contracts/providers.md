# Contract: Pedidos HTTP aos dois provedores e interface interna dos clientes

**Feature**: `004-llm-test-generation` | Origem: research R2, R3, R4, R6, R7 | Fontes oficiais
acessadas em 2026-10-15 (research A3 e R3).

## 1. Interface interna (`ai_clients/llm/providers.py`)

```python
class LLMProvider(Protocol):
    key: str                                   # "gpt" | "gemini"
    def request_body(self, prompt: str) -> dict: ...          # pura; testada campo a campo
    def call(self, prompt: str) -> ProviderAnswer: ...        # um pedido, sem repetir nada

@dataclass(frozen=True)
class ProviderAnswer:
    http_status: int; raw_body: str; latency_s: float
    model_returned: str; response_id: str
    finish: Finish                             # status, reason, safety_categories
    usage: Usage                               # input, cached_input, output, reasoning (ou None)
    text: str | None                           # o texto da resposta, sem partes de raciocínio
    refusal: str | None                        # item `refusal` da OpenAI
```

**Exceções:**
- `ProviderUnavailable(reason, retry_after_s | None)`: falha de infraestrutura; repetir a mesma
  chamada.
- `ProviderFatal(message)`: erro que não passa sozinho; o comando sai com código 3.

O cliente **nunca** repete pedidos. A espera e a repetição ficam no coordenador (research R7, R8).
O cliente não guarda estado entre chamadas, só a configuração (chave, URL, tempo de leitura).

## 2. OpenAI — `POST https://api.openai.com/v1/responses`

Cabeçalhos: `Authorization: Bearer $OPENAI_API_KEY` e `Content-Type: application/json`.

```json
{
  "input": "<prompt inteiro>",
  "max_output_tokens": 32768,
  "model": "gpt-5.4-mini-2026-03-17",
  "reasoning": {"effort": "medium"},
  "store": false,
  "text": {"format": {"name": "test_suite", "schema": {"...": "research R4"},
                      "strict": true, "type": "json_schema"}}
}
```

Os campos são exatamente esses. Não vão `instructions`, `previous_response_id`, `conversation`,
`temperature`, `top_p`, `seed`, `tools` nem `metadata`.

| Resposta | Leitura |
|---|---|
| `id`, `model` | `response_id`, `model_returned` |
| `status`, `incomplete_details.reason` | `finish` (`completed`; `incomplete` com `max_output_tokens` → `truncated`; com `content_filter` → `safety_block`) |
| itens `output[*]` do tipo `message`, conteúdo `output_text` | `text` (concatenado) |
| conteúdo `refusal` | `refusal` → falha `refusal` |
| `usage.input_tokens`, `.input_tokens_details.cached_tokens`, `.output_tokens`, `.output_tokens_details.reasoning_tokens` | `usage` (a saída cobrada é `output_tokens`) |

| Erro | Classe |
|---|---|
| rede, *timeout*, corpo cortado, HTTP 5xx, 408, 409, 429 com `error.code` diferente de `insufficient_quota` | `ProviderUnavailable` (`Retry-After` em segundos, se vier) |
| HTTP 400, 401, 403, 404, 429 com `insufficient_quota` | `ProviderFatal` |

## 3. Gemini — `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent`

Cabeçalhos: `x-goog-api-key: $GEMINI_API_KEY` e `Content-Type: application/json`.

```json
{
  "contents": [{"parts": [{"text": "<prompt inteiro>"}], "role": "user"}],
  "generationConfig": {
    "maxOutputTokens": 32768,
    "responseFormat": {"text": {"mimeType": "application/json",
                                "schema": {"...": "research R4"}}},
    "thinkingConfig": {"thinkingLevel": "medium"}
  }
}
```

Os campos são exatamente esses. Não vão `systemInstruction`, `cachedContent`, `safetySettings`,
`temperature`, `topP`, `topK`, `seed` nem `tools`. Se a primeira chamada do piloto receber HTTP
400 por causa de `responseFormat`, que não é cobrado e para com código 3, o plano B é
`responseMimeType` + `responseJsonSchema` (research R3), registrado como decisão.

| Resposta | Leitura |
|---|---|
| `responseId`, `modelVersion` | `response_id`, `model_returned` |
| `promptFeedback.blockReason` | falha `safety_block` (o motivo vai em `finish.reason`) |
| `candidates[0].finishReason` | `STOP`: segue; `MAX_TOKENS` → `truncated`; `SAFETY`, `PROHIBITED_CONTENT`, `BLOCKLIST`, `SPII`, `RECITATION` → `safety_block` (as categorias de `safetyRatings` bloqueadas vão em `finish.safety_categories`) |
| `candidates[0].content.parts[*].text`, sem `thought: true` | `text` (concatenado) |
| `usageMetadata.promptTokenCount`, `.cachedContentTokenCount`, `.candidatesTokenCount`, `.thoughtsTokenCount` | `usage` (a saída cobrada é `candidatesTokenCount + thoughtsTokenCount`; `reasoning` = `thoughtsTokenCount`) |

| Erro | Classe |
|---|---|
| rede, *timeout*, corpo cortado, HTTP 5xx, 408, 429 | `ProviderUnavailable` (`Retry-After` ou `retryDelay` do `google.rpc.RetryInfo`, se vier) |
| HTTP 400, 401, 403, 404 | `ProviderFatal` |

## 4. Ordem das conferências de uma resposta 200 (research R6)

1. *tokens* de raciocínio iguais a 0 ou ausentes → `BarredResponse`, código 6;
2. término (`truncated`, `refusal`, `safety_block`);
3. texto (`empty_response`, `not_json`, `schema_violation`);
4. testes (`no_usable_test`), segundo FR-013.
