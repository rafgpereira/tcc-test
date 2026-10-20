# Research: Terceiro modelo comercial: Claude

**Feature**: `specs/008-claude-test-generation` | **Date**: 2026-10-20 | **Plan**: [plan.md](./plan.md)

Fontes oficiais consultadas em 2026-10-20:
- preços: `https://platform.claude.com/docs/en/about-claude/pricing`;
- raciocínio: `https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost`;
- saída estruturada: `https://platform.claude.com/docs/en/build-with-claude/structured-outputs`;
- guia de migração para o Haiku 5.5, da documentação da API.

## R1 — Pedido

**Decision**: `POST https://api.anthropic.com/v1/messages`, com os cabeçalhos `x-api-key`,
`anthropic-version: 2023-06-01` e `content-type: application/json`. O corpo:

```json
{
  "max_tokens": 32768,
  "messages": [{"content": "<prompt>", "role": "user"}],
  "model": "claude-haiku-5-5",
  "output_config": {
    "effort": "medium",
    "format": {"schema": {"...": "o mesmo response_schema() dos outros dois"}, "type": "json_schema"}
  },
  "thinking": {"type": "adaptive"}
}
```

**Rationale**:
- uma única mensagem de usuário, sem `system` (A11 da 004);
- `thinking: adaptive` e `effort: medium` explícitos (clarify P2). `medium` é o padrão do Haiku
  5.5, e mandá-lo explícito deixa o valor gravado no `run.json`;
- a saída estruturada (`output_config.format`, GA, sem cabeçalho beta) usa o schema que já existe.
  Ele tem `additionalProperties: false` e `required`, como a API exige. A gramática vale só para a
  resposta final, não para o raciocínio: a saída estruturada funciona junto com o raciocínio;
- `max_tokens` é 32.768 (clarify), e o raciocínio conta dentro dele.

O Haiku 5.5 recusa (HTTP 400) qualquer `temperature`, `top_p` ou `top_k` fora do padrão, e também
o orçamento de raciocínio (`budget_tokens`). Nenhum deles é enviado, e a lista de parâmetros
proibidos da 004 continua valendo. Nenhum `cache_control` é enviado: sem ele a API não guarda o
início do prompt.

**Alternatives considered**:
- `budget_tokens`: recusado pelo modelo.
- Instrução de sistema: fere A11.
- SDK oficial da Anthropic: os outros dois clientes usam a biblioteca padrão (decisão da 004), e
  manter o mesmo transporte evita uma dependência nova e diferenças de comportamento (repetições
  automáticas do SDK, tempo de espera). Rejeitado por paridade.

## R2 — Sinal de "sem raciocínio" (P3)

**Decision**: a contagem de raciocínio é `usage.output_tokens_details.thinking_tokens`. Valor 0
ou campo ausente leva a `reasoning_tokens` 0 ou `None`, e a resposta é barrada (a regra emendada
da 004). O conteúdo da resposta é gravado inteiro, como nos outros, inclusive os blocos
`thinking`.

**Rationale**:
- a documentação diz que o modelo decide, a cada pedido, se raciocina; no `medium`, ele "pode
  pular o raciocínio em pedidos simples". Quando pula, a resposta não tem bloco `thinking`;
- a contagem oficial do raciocínio é `thinking_tokens`, sempre menor ou igual a `output_tokens`;
- é o mesmo critério dos outros dois (contagem 0 ou ausente).

**Risco e mitigação**: se o Haiku 5.5 não trouxer o campo em nenhuma resposta, todas seriam
barradas. Por isso o piloto começa com `--limit 1`: a primeira resposta é conferida na pasta antes
de seguir. Ela deve trazer o campo e um bloco `thinking`, ou, se estiver em `barred/`, mostrar o
motivo. Se o campo não existir, o plano é revisto antes de gastar mais.

**Alternatives considered**: usar só a presença do bloco `thinking`. Não mede quanto o modelo
raciocinou e não é o critério dos outros dois.

## R3 — Leitura da resposta

**Decision**:
- **Texto**: a junção dos blocos `type: "text"`. A saída estruturada vem como uma string JSON
  num bloco `text`, interpretada pelas mesmas regras e pelas 7 falhas de formato da 004.
- **Término** (`stop_reason`):

  | `stop_reason` | O que vira |
  |---|---|
  | `end_turn` | normal |
  | `max_tokens` ou `model_context_window_exceeded` | falha `truncated` |
  | `refusal` | falha `refusal` (a categoria de `stop_details.category` vai no `Finish.reason`) |
  | outro valor | registrado; a interpretação segue pelo texto |

- **Modelo e identificador**: `model` e `id` da resposta.

**Rationale**: os mesmos campos do `ProviderAnswer` dos outros dois. Uma recusa é HTTP 200 e é
cobrada, como diz a documentação.

## R4 — Tokens e custo

**Decision**:
- **Entrada**: `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
- **Entrada em cache**: `cache_read_input_tokens`.
- **Saída**: `output_tokens`, que já inclui o raciocínio.
- **Raciocínio**: `thinking_tokens` (R2).

**Linha de preço** (US$ por milhão de tokens), válida desde 2026-10-20, conferida nessa data:

| Entrada | Entrada em cache | Saída | Fonte |
|---|---|---|---|
| 0,10 | 0,01 | 0,50 | `https://platform.claude.com/docs/en/about-claude/pricing` |

Esses valores valem para prompts de até 100 mil tokens. Acima disso o preço é outro (0,50 / 0,05
/ 2,50). O maior prompt da execução tem 7.459 caracteres (híbrido do `61_B`), muito abaixo do
limite. Uma chamada com mais de 100 mil tokens de entrada é recusada pelo cálculo de custo, com
mensagem, em vez de ser cobrada pelo preço errado.

`CHARS_PER_TOKEN` do Claude começa em 3,0 (conservador, antes do piloto), e a média de saída
começa vazia. O piloto mede os dois.

## R5 — Erros HTTP

**Decision**: os mesmos códigos e as mesmas saídas da 004:

| Erro | O que vira | Código do comando |
|---|---|---|
| 429, 500, 529 (sobrecarga) e demais 5xx; 408, 409 | `ProviderUnavailable`, que respeita o `retry-after` | `3`, só depois do teto de repetições |
| 401 e 403 (chave) | `ProviderFatal` | `3` na hora |
| 404 (modelo) | `ProviderFatal` | `3` na hora |
| 400 e 413 (pedido recusado) | `ProviderFatal` | `3` na hora |

Um 400 de crédito esgotado ("credit balance") ganha uma mensagem própria de crédito. O formato do
erro da Anthropic é `{"type":"error","error":{"type":...,"message":...}}`: o `error.message` que o
código já lê funciona.

## R6 — Sem streaming

**Decision**: um pedido sem streaming, com o mesmo tempo de espera da 004 (`LLM_HTTP_TIMEOUT_S`,
padrão 900 s).

**Rationale**: os outros dois também não usam streaming, e o Haiku é o modelo rápido da família.
O piloto mede a latência. Se aparecerem conexões cortadas em respostas longas, o streaming entra
como mudança só de transporte, como foi feito no Ollama (R25 da 003).

## R7 — Onde muda o código

**Decision**:
- **`ai_clients/llm/config.py`**: `"claude"` em `MODELS`, `MODEL_ID`, `ENDPOINT`, nas variáveis
  `ENV_*` (`ANTHROPIC_API_KEY`, `ANTHROPIC_MAX_CONCURRENCY`, `ANTHROPIC_MAX_INFRA_RETRIES`,
  `ANTHROPIC_MAX_REQUESTS_PER_MINUTE`), em `CHARS_PER_TOKEN`, na origem dessa estimativa, em
  `MEASURED_MEAN_OUTPUT_TOKENS` e na linha de preço.
- **`ai_clients/llm/providers.py`**: o corpo do Claude, `_claude_answer`, `ClaudeClient` e a
  mensagem de crédito.
- **`ai_clients/llm/interpret.py`**: o término `max_tokens` (Anthropic) entra em `truncated`.
- **`ai_clients/llm/schemas.py`**: `LlmModel` ganha `"claude"`.
- **`cli/consistency.py`**: a camada `claude_suites`.
- **`.env.example`**: as variáveis novas, sem valor.

Os comandos aceitam `--model claude` sozinhos, porque as opções vêm de `MODELS`. O `README` do
módulo, a referência da raiz e o `CLAUDE.md` passam a citar 3 modelos comerciais.

**Rationale**: a estrutura da 004 já é por modelo. O que muda é configuração e um cliente novo.

## R8 — Piloto

**Decision**:
1. Rodar primeiro `--limit 1` e conferir R2.
2. Rodar os 5 problemas dos pilotos (`1000_B`, `1005_C`, `1008_B`, `1_B`, `61_B`) nos 3 cenários:
   15 combinações, com teto de gasto.
3. Gerar o relatório, guardá-lo como `manifests/claude_generation_report.piloto1.json` e mover a
   pasta para `data/suites/claude-piloto1`.
4. A execução completa começa do zero.

O piloto mede a razão caracteres/token, a média de saída, a latência, a taxa de falha de formato e
a de respostas sem raciocínio. Os números vão para o `config` e para a metodologia.

## R9 — Emenda da constitution (S1)

**Decision**: proposta **1.9.0** (MINOR: amplia o escopo do experimento):
- **Contexto do Projeto**: "dois LLMs comerciais" passa a "três LLMs comerciais".
- **Princípio III**: inclui o Claude Haiku 5.5 na lista dos modelos.
- **Princípios IV e IX**: "três modelos" passa a "quatro modelos" (3 comerciais e o SLM), e o
  tamanho do experimento passa a "200 problemas × 4 modelos × 3 cenários".

Nenhuma regra muda.

**Rationale**: o texto atual fixa a quantidade e a lista dos modelos. Sem a emenda, a feature
contraria a constitution.
