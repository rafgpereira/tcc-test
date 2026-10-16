# Research: Geração de Suítes de Teste pelos LLMs Comerciais

**Feature**: `004-llm-test-generation` | **Date**: 2026-10-15 | **Plan**: [plan.md](./plan.md)

Começa pela decisão A3, tomada antes do plano. O `/speckit-plan` de 2026-10-15 acrescentou os
itens R0 a R14, no fim do arquivo.

Cada item: **Decisão**, **Motivo**, **Alternativas consideradas**, **Fontes** (documentação
oficial, com data de acesso) e, quando houver, **Conferir no piloto**. Os números provisórios
(teto de saída, razão caracteres/*token*) são fixados depois do piloto. Até lá, nenhum tempo,
custo ou tamanho é afirmado sem medição.

---

## A3 — Reprodutibilidade sem seed nem temperatura **[DECIDIDO, 2026-10-15 — autores; modelo do Gemini revisto no mesmo dia: `gemini-3.6-flash` → `gemini-3.8-flash`]**

**Decisão**: nenhum dos dois LLMs comerciais recebe seed, temperatura ou outro parâmetro de
amostragem. A configuração segue a Tabela 2 do TCC, com os nomes atuais dos parâmetros:

| | GPT-5.4-mini | Gemini 3.8 Flash |
|---|---|---|
| Identificador pedido | `gpt-5.4-mini-2026-03-17` (snapshot datado, não o apelido `gpt-5.4-mini`) | `gemini-3.8-flash` (GA; o Google não oferece identificador datado, então a proveniência é o `modelVersion` devolvido) |
| Endpoint | Responses API | `generateContent` (um turno, sem sessão de chat nem cache criado pelo pipeline) |
| Estado no provedor | `store: false`, sem `previous_response_id` | nenhum (a chamada é sem estado; sem `previous_interaction_id`) |
| Raciocínio | `reasoning.effort: "medium"`, **enviado explicitamente** (o padrão do modelo é `none`) | `thinking_level: "medium"`, **enviado explicitamente** (é também o padrão do 3.8 Flash; enviar evita depender dele) |
| Amostragem | sem `temperature`, `top_p` ou `seed` | sem `temperature`, `top_p`, `top_k` ou `seed` |
| Saída | `text.format` do tipo `json_schema` com `strict: true` | JSON com schema: `generationConfig.responseFormat.text` com `mimeType: "APPLICATION_JSON"` e `schema` (conferido na API em 2026-10-16: o `mimeType` é uma lista fixa de valores, e `"application/json"`, como na documentação, foi recusado; R3) |
| Prompt (A11) | o texto inteiro numa única mensagem de usuário, sem `instructions` nem mensagem `developer` | o texto inteiro numa única mensagem de usuário, sem `system_instruction` |
| Filtros de segurança (A13) | não há ajuste equivalente na chamada | `safetySettings` não é enviado (padrão da API); bloqueios gravados com a categoria |
| Barreira de raciocínio (A12) | `reasoning_tokens` igual a 0 ou ausente para o comando | `thoughtsTokenCount` igual a 0 ou ausente para o comando |

Em cada tentativa ficam gravados: o identificador do modelo devolvido na resposta (`model` na
OpenAI, `modelVersion` no Gemini), o identificador da resposta (`id`; `responseId`), todos os
parâmetros efetivamente enviados e a resposta crua (FR-010, FR-011). A não reprodutibilidade bit a
bit das respostas é declarada como limitação (FR-019; metodologia, seção 3).

**Motivo**:
- Sem seed não há como reproduzir uma resposta; mesmo onde uma API aceita seed, a reprodução é
  "melhor esforço", nunca garantida. A proveniência vem do que fica gravado (parâmetros, versão
  devolvida, resposta crua), e o pacote versionado da execução final (FR-026) é o que sustenta os
  números, como no SLM.
- Temperatura: para os modelos Gemini 3, o Google recomenda **fortemente** manter o padrão 1,0,
  porque o raciocínio é otimizado para ele, e alterá-la pode causar repetição em laço ou queda de
  qualidade. A página do 3.8 Flash manda ainda remover `temperature`, `top_p` e `top_k`, que trata
  como descontinuados. Na OpenAI, a Tabela 2 do TCC já não fixava amostragem para o modelo de
  raciocínio. Não enviar nada mantém os dois modelos iguais nesse ponto (D3).
- `reasoning.effort` explícito: o padrão documentado do `gpt-5.4-mini` é `none`, ou seja, sem
  enviar o parâmetro o modelo **não raciocinaria**, e o experimento compararia um modelo sem
  raciocínio com um que raciocina.
- Snapshot datado no GPT: a OpenAI documenta que o snapshot fixa a versão do modelo; o apelido
  pode passar a apontar para outro snapshot sem aviso (FR-003).
- **`gemini-3.8-flash`** (decisão revista em 2026-10-15): em 2026-10-08 o Google descontinuou o
  `gemini-3.5-flash` do desenho aprovado e passou a rotear as chamadas a ele para o
  `gemini-3.6-flash`, recomendando migrar para o 3.6 ou para o 3.8. Entre os dois substitutos, os
  autores escolheram o Flash mais recente: o próprio Google descreve o 3.6 como
  "previous-generation" e indica o 3.8 para projetos novos. O 3.8 é GA desde 2026-09-02, aceita o
  `thinking_level: "medium"` e tem esse nível como padrão.
- Sem identificador datado no Gemini: a lista de modelos não mostra versão datada nem apelido do
  3.8 Flash, só `gemini-3.8-flash`. Por isso a versão que efetivamente respondeu é conhecida pelo
  `modelVersion` gravado em cada tentativa, e uma troca silenciosa feita pelo provedor fica visível
  no relatório (Edge Cases da spec).

**Divergência em relação ao texto do TCC (PDF, Tabela 2)**: os nomes dos parâmetros e o modelo do
Gemini mudaram desde que o texto foi escrito:
- OpenAI: `reasoning_effort` (forma da Chat Completions) virou `reasoning.effort` na Responses API,
  e "Structured Outputs com `strict: true`" é hoje `text.format` do tipo `json_schema` com
  `strict: true`.
- Gemini: o PDF diz **Gemini 3.5 Flash**, e o modelo usado é o **`gemini-3.8-flash`**, porque o
  3.5 foi descontinuado e o 3.8 é o Flash mais recente (ver Motivo). O `thinking_level` fica, na API
  REST, em `generationConfig.thinkingConfig.thinkingLevel`, e o `mimeType: application/json` do
  texto vai em `generationConfig.responseFormat.text`, com o valor `"APPLICATION_JSON"` e o
  `schema` (R3, conferido na API em 2026-10-16).

O texto final do TCC deve trazer os nomes atuais, o modelo efetivamente usado e a nota da troca do
Gemini.

**Alternativas consideradas**:
- Enviar seed onde a API aceitasse, com o esquema de seeds do SLM: rejeitada pelos autores. Não
  garante reprodução e deixaria os dois modelos parametrizados de formas diferentes.
- Fixar temperatura (por exemplo 0) para "reduzir a variação": rejeitada, porque contraria a
  recomendação do Google para o Gemini 3, e o parâmetro está descontinuado no 3.8 Flash.
- Pedir `gemini-3.5-flash` e aceitar o redirecionamento: rejeitada, porque a configuração gravada
  diria um modelo e outro responderia.
- **`gemini-3.6-flash`** (escolhido primeiro em 2026-10-15 e revisto no mesmo dia): não adotado. É
  o destino do redirecionamento do 3.5, mas o próprio Google o descreve como "previous-generation"
  e recomenda o 3.8 Flash para projetos novos; os autores preferiram o Flash mais recente.
- Usar o apelido `gpt-5.4-mini`: rejeitada (FR-003).

**Fontes** (acessadas em 2026-10-15):
- OpenAI, página do modelo GPT-5.4 mini: <https://developers.openai.com/api/docs/models/gpt-5.4-mini>.
  Snapshot `gpt-5.4-mini-2026-03-17`; "Reasoning.effort supports: none (default), low, medium,
  high and xhigh"; Structured Outputs suportado; preço por milhão de tokens: US$ 0,75 de entrada,
  US$ 0,075 de entrada em cache e US$ 4,50 de saída.
- OpenAI, guia de raciocínio: <https://developers.openai.com/api/docs/guides/reasoning>.
  `reasoning.effort` na Responses API; os tokens de raciocínio aparecem em
  `usage.output_tokens_details.reasoning_tokens` e são cobrados como saída; ao atingir
  `max_output_tokens`, a resposta vem com `status: incomplete` e motivo `max_output_tokens`,
  possivelmente sem nenhum texto visível.
- Google, changelog da Gemini API: <https://ai.google.dev/gemini-api/docs/changelog>.
  - 2026-09-02: "Gemini 3.8 Flash generally available (GA)".
  - 2026-09-18: "For any new projects, use our latest models: 3.5 Flash-Lite or 3.8 Flash".
  - 2026-10-08: o `gemini-3.5-flash` foi descontinuado e as chamadas a ele são roteadas
    automaticamente para o `gemini-3.6-flash`, com a recomendação de atualizar para o
    `gemini-3.6-flash` ou o `gemini-3.8-flash`.
  - 2026-10-08: na mesma data, o `gemini-3.7-flash` passou a ser roteado para o
    `gemini-3.8-flash`.
- Google, lista de modelos: <https://ai.google.dev/gemini-api/docs/models>.
  `gemini-3.8-flash` marcado "New Stable", na seção dos estáveis, sem identificador datado nem
  apelido listado; `gemini-3.6-flash` descrito como "previous-generation".
- Google, novidades do Gemini 3.8 Flash: <https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8?hl=en>.
  - Identificador `gemini-3.8-flash`, sem variante datada.
  - `thinking_level` `low`, `medium` e `high`, com padrão `medium`; "`minimal` thinking level is
    not supported for Gemini 3.8 Flash and will return an error".
  - 1M tokens de contexto e 64k de saída.
  - Na migração, "Remove deprecated sampling parameters (`temperature`, `top_p`, `top_k`)".
  - A página não diz GA nem preview; o status vem do changelog e da lista de modelos.
- Google, preços: <https://ai.google.dev/gemini-api/docs/pricing>.
  Camada paga padrão do 3.8 Flash, em US$ por milhão de tokens:

  | Item | Até 2026-12-31 (preço introdutório) | A partir de 2027-01-01 |
  |---|---|---|
  | Entrada | 0,75 | 1,50 |
  | Saída, incluindo os tokens de raciocínio | 3,75 | 7,50 |
  | Entrada em cache | 0,075 | 0,15 |
  | Armazenamento de cache (por milhão de tokens por hora) | 0,50 | 1,00 |

  Existe camada gratuita, mas nela o conteúdo "may be used to improve Google's products".
- Google, guia de raciocínio: <https://ai.google.dev/gemini-api/docs/thinking>.
  Linha do `gemini-3.8-flash`: níveis "low, medium, high", padrão "On (medium)", sem `minimal`.
- Google, guia do Gemini 3: <https://ai.google.dev/gemini-api/docs/gemini-3>.
  "For all Gemini 3 models, we strongly recommend keeping the temperature parameter at its default
  value of `1.0`". A página está marcada como descontinuada em favor do guia do 3.8.
- Google, referência do `generateContent`: <https://ai.google.dev/api/generate-content>.
  A resposta traz `modelVersion` ("The model version used to generate the response") e
  `responseId`. Os campos de uso são `promptTokenCount`, `cachedContentTokenCount`,
  `candidatesTokenCount` e `thoughtsTokenCount`. `finishReason` pode ser `STOP`, `MAX_TOKENS` ou
  `SAFETY`, entre outros.

Os preços acima são o registro do que estava publicado na data de acesso, não a tabela de preços da
execução: essa é fixada no plano, com data e fonte (FR-020). O preço do Gemini **dobra em
2027-01-01**. Se a execução atravessar essa data, a tabela muda no meio dela, e essa mudança fica
registrada sem invalidar a retomada (FR-020). A chave usada deve ser de conta com faturamento
ativo (Assumptions da spec), não da camada gratuita.

**Confirmado no plano (2026-10-15, R3)**, os dois pontos que estavam em aberto aqui:
- **Nível de raciocínio:** no `generateContent` REST, o caminho é
  `generationConfig.thinkingConfig.thinkingLevel`.
- **Schema de resposta:** a documentação atual do `generateContent` pede JSON em
  `generationConfig.responseFormat.text` (`mimeType` + `schema`). O par `responseMimeType` +
  `responseSchema` aparece só em páginas mais antigas (guia de migração). **Conferido na API em
  2026-10-16, antes do piloto, com um pedido "hello world" de cada forma**: a forma da documentação
  com o valor `"application/json"` foi recusada (HTTP 400, não cobrado: `Invalid value at
  'generation_config.response_format.text.mime_type'`, o campo é uma lista fixa de valores,
  `TextResponseFormat.MimeType`), e a mesma forma com o valor `"APPLICATION_JSON"` foi aceita:
  JSON no schema, `finishReason` `STOP`, `thoughtsTokenCount` 309, `modelVersion`
  `gemini-3.8-flash`. O código usa essa forma; o plano B (`responseMimeType` +
  `responseJsonSchema`) não foi necessário. A resposta real está em
  `tests/ai_clients/llm/fixtures/gemini_hello_world_2026-10-16.json`.

O nome `responseMimeType` usado acima, na tabela da Tabela 2, é o do texto do PDF. A primeira
chamada do piloto confirma a forma aceita: um HTTP 400 não é cobrado e para o comando com o
código 3 (R6).

**Conferir no piloto** (registrar o resultado neste item e na metodologia):
1. O GPT recebe de fato o raciocínio `medium`: toda tentativa do `gpt-5.4-mini` deve ter
   `usage.output_tokens_details.reasoning_tokens > 0`. Desde o terceiro clarify (2026-10-15, A12)
   isso deixou de ser só conferência do piloto: é uma barreira automática em toda execução, nos
   dois modelos (spec, FR-018a). Uma contagem 0 ou ausente para o comando com código próprio, e no
   piloto o resultado é registrado aqui.
2. Que versão do Gemini 3.8 Flash responde: registrar o `modelVersion` devolvido em cada tentativa
   (esperado `gemini-3.8-flash` ou uma versão dele). O `thoughtsTokenCount` maior que 0 é
   garantido pela mesma barreira (FR-018a).
3. Que o GPT responde com o snapshot pedido: o `model` devolvido deve ser
   `gpt-5.4-mini-2026-03-17`.

---

## R0 — Inventário do que o SLM já tem e como cada peça é reaproveitada

Levantamento no código atual (`main`, 2026-10-15), feito para cumprir FR-029: reaproveitar o
código do SLM, sem copiá-lo, e sem mudar o comportamento do SLM.

| Peça do SLM | Situação | Como o plano usa |
|---|---|---|
| `ai_clients.problem` (`load_problem`, `list_problem_ids`) | genérica | importada sem mudança |
| `ai_clients.prompt` (`load_template`, `context_data`, `build_prompt`, `prompt_sha256`) | genérica (três marcadores) | importada sem mudança; o template novo usa os mesmos três marcadores (R5) |
| `ai_clients.parser` (`is_abbreviated`, retirada de cerca de `<input>`/`<output>` da predição) | funções privadas | expostas com nome público, sem mudar o comportamento (`strip_data_fence`); a regra de teste vazio, abreviado e cercado é a mesma da predição do SLM (FR-013) |
| `ai_clients.store` (`_flock`, `_open_lock`, `claim`, `exclusive_run`, `shared_run`) | genéricas sobre `root`, mas a mensagem cita `data/suites/slm/` | a mensagem passa a citar a pasta recebida; o SLM continua imprimindo o mesmo texto |
| máquina de estados do `store` (fases, execução, reserva) | específica do SLM (15 tentativas, `execute`) | **não** reaproveitada: o LLM tem a sua, muito menor (data-model §4) |
| `schemas.suite.SlmSuite` | confere cada tentativa contra a tabela de seeds do SLM; `discarded_manual` exige 15 tentativas | **não** valida suíte de LLM: schema `LlmSuite` novo, com as mesmas chaves de topo, e um leitor comum `SuiteView` (R1) |
| `closing` e `template_change` | regra genérica, código preso ao estado do SLM | mesma regra e mesmas mensagens; implementação própria fina sobre o estado do LLM (R10) |
| `packaging` (zip determinístico, manifesto, `verify`) | caminhos fixos do SLM em `config` | o núcleo (`_tree`, `_file_info`, `build_zip`, `verify`) passa a receber os caminhos por parâmetro; o SLM chama com os mesmos valores de hoje |
| `report` (`size_stats`, quartis) | genérica | importada |
| `__main__` (registro de subcomandos, `dataset_gate`, `finish`, códigos 0–4 e 130) | genérico | os subcomandos existentes ganham `--model`; os códigos 5 e 6 são novos (R8) |
| `mutation.dataset_gate.verify_dataset`, `dataset.persistence.store` (escrita atômica), `dataset.integrity.packaging` (constantes de zip) | genéricos | importados, como no SLM |
| `cli.consistency.Layer` | genérico | duas camadas novas, `gpt_suites` e `gemini_suites` (R11) |

Nenhum teste do SLM pode mudar de resultado (FR-028), e isso MUST ser conferido rodando a suíte
inteira na implementação. As funções que só mudam de nome ou de parâmetro (`parser`, `store`,
`packaging`) ganham um teste que compara a saída do SLM antes e depois.

## R1 — `suite.json` dos LLMs: schema próprio e leitor comum **[DECIDIDO, 2026-10-15 — autores]**

**Decisão**:
- **Schema `LlmSuite`** (`ai_clients/llm/schemas.py`), gravado no mesmo nome de arquivo
  (`suite.json`), com `schema_version: 2` e **as mesmas chaves de topo** do `SlmSuite`:
  `schema_version`, `problem_id`, `scenario`, `model`, `model_digest`, `status`, `accepted_phase`,
  `attempts`, `accepted_attempt`, `tests`, `suite_size`, `discarded_inputs`, `duplicate_inputs`,
  `manual_close`.
- **Chaves que só fazem sentido no SLM**, com valor fixo documentado:
  - `accepted_phase` é sempre `null`;
  - `discarded_inputs` é sempre `[]`, porque nada é executado;
  - `model_digest` traz a versão devolvida pela API na tentativa aceita (`model` na OpenAI,
    `modelVersion` no Gemini), ou `null` numa suíte `discarded_manual`.
- **Itens de `attempts`:** têm a forma do LLM (`attempt`, `failure`, `detail`, `model_returned`,
  `cost_usd`), sem seed, temperatura, fase nem hardware.
- **Leitor comum `SuiteView`** (`ai_clients/schemas/suite_view.py`): um schema com
  `extra="ignore"` que lê as chaves que a avaliação usa (`problem_id`, `scenario`, `model`,
  `status`, `tests`, `suite_size`) e confere `suite_size == len(tests)` e o status. A função
  `read_suite_view(path)` lê qualquer `suite.json` dos 3 modelos sem ramificar por modelo.

**Motivo**:
- O `SlmSuite` confere cada tentativa contra a tabela de seeds e temperaturas do SLM e exige 15
  tentativas num `discarded_manual`, então uma suíte de LLM nunca passaria nele.
- Mudar o `SlmSuite` mexeria no schema das 600 suítes já empacotadas (FR-028).
- O leitor comum dá à avaliação o que FR-017 e SC-007 pedem (os 3 modelos lidos do mesmo jeito),
  sem acoplar os validadores dos dois módulos.

**Alternativas consideradas**:
- Generalizar o `SlmSuite` com um campo novo (`generator`): rejeitada, porque acopla os dois
  módulos e muda o schema compartilhado.
- Gravar suítes de LLM no `SlmSuite` com valores de mentira nos campos do SLM: inviável sem
  afrouxar o validador.

**Efeito na spec**: FR-017 e SC-007 passam a citar o `LlmSuite` e o `SuiteView` (propagado em
2026-10-15).

## R2 — Cliente HTTP: biblioteca padrão, sem SDK

**Decisão**: dois clientes em `ai_clients/llm/providers.py`, `OpenAIClient` e `GeminiClient`.
- **Transporte:** `urllib.request`, como o `OllamaClient`, uma conexão nova por pedido, **sem
  streaming** e sem repetição escondida.
- **Resultado:** cada um devolve uma `ProviderAnswer` com o corpo HTTP cru (texto), o status
  HTTP, o modelo e a versão devolvidos, o identificador da resposta, o motivo de término, o uso
  de *tokens* e o tempo.
- **Erros:** a classificação está em R6.

**Motivo**:
- Nenhuma dependência nova (Princípio IX).
- O corpo cru é o que FR-010 manda gravar.
- Os SDKs oficiais repetem pedidos sozinhos por padrão, o que esconderia falhas de infraestrutura
  e tentativas (FR-018), e montam o pedido por conta própria, o que tornaria mais difícil provar
  que nada além do esperado é enviado (FR-002, FR-003; testado contra o corpo exato).

**Alternativas consideradas**: o SDK `openai` e o `google-genai`, com as repetições desligadas.
Rejeitados, porque trazem duas dependências e o mesmo controle exige configurar e testar o que
eles fazem por baixo.

## R3 — Formato dos pedidos e das respostas

**OpenAI** (`POST https://api.openai.com/v1/responses`, cabeçalho `Authorization: Bearer`).

O corpo é exatamente este:
```json
{"model": "gpt-5.4-mini-2026-03-17", "input": "<prompt inteiro>", "store": false,
 "reasoning": {"effort": "medium"}, "max_output_tokens": <teto>,
 "text": {"format": {"type": "json_schema", "name": "test_suite", "strict": true,
                     "schema": <schema de R4>}}}
```
- `input` como texto equivale a uma única mensagem `user` (A11). Nunca vão `instructions`,
  `previous_response_id`, `conversation`, `temperature`, `top_p` nem `seed`.
- **Resposta lida:**
  - identificação: `id`, `model`;
  - estado: `status` (`completed` ou `incomplete`) e `incomplete_details.reason`
    (`max_output_tokens` ou `content_filter`);
  - conteúdo: os itens `message` de `output`, com conteúdo `output_text` (o texto) ou `refusal`;
  - uso: `usage.input_tokens`, `usage.input_tokens_details.cached_tokens`, `usage.output_tokens`
    (inclui o raciocínio) e `usage.output_tokens_details.reasoning_tokens`.

**Gemini** (`POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent`,
cabeçalho `x-goog-api-key`).

O corpo é exatamente este:
```json
{"contents": [{"role": "user", "parts": [{"text": "<prompt inteiro>"}]}],
 "generationConfig": {"thinkingConfig": {"thinkingLevel": "medium"},
                      "maxOutputTokens": <teto>,
                      "responseFormat": {"text": {"mimeType": "APPLICATION_JSON",
                                                  "schema": <schema de R4>}}}}
```
- Nunca vão `systemInstruction`, `cachedContent`, `safetySettings` (A13), `temperature`, `topP`,
  `topK` nem `seed`.
- **Resposta lida:**
  - identificação: `responseId`, `modelVersion`;
  - bloqueio do prompt: `promptFeedback.blockReason`;
  - candidato: `candidates[0].finishReason` (`STOP`, `MAX_TOKENS`, `SAFETY` e outros) e o texto,
    que é a junção das `parts` sem `thought: true`;
  - uso: `usageMetadata.promptTokenCount`, `cachedContentTokenCount`, `candidatesTokenCount` e
    `thoughtsTokenCount` (cobrados como saída junto com os candidatos).

**Motivo**: a forma documentada de cada API na data de acesso (fontes abaixo), mínima, e a mesma
para os 2 modelos em tudo o que não é nome de campo.

**Alternativas consideradas**:
- `responseMimeType` + `responseSchema`/`responseJsonSchema` no Gemini: é a forma das páginas
  mais antigas, mantida como plano B se a primeira chamada do piloto receber HTTP 400 (que não é
  cobrado).
- *Streaming*: rejeitado, porque não há proxy no caminho, e o tempo de espera de leitura é
  configurável (R7).

**Fontes** (acessadas em 2026-10-15):
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs.md):
  "all fields ... must be specified as `required`"; `additionalProperties: false`; "the same order
  as the ordering of keys in the schema"; `incomplete_details.reason` `"content_filter"`.
- [Reasoning](https://developers.openai.com/api/docs/guides/reasoning) (A3).
- [Structured outputs do generateContent](https://ai.google.dev/gemini-api/docs/generate-content/structured-output):
  `generationConfig.responseFormat.text` (`mimeType`, `schema`; o exemplo usa
  `"application/json"`, que a API recusou em 2026-10-16: o valor aceito é `"APPLICATION_JSON"`,
  ver acima); "the model will produce outputs
  in the same order as the keys in the schema"; palavras aceitas: `properties`, `required`,
  `additionalProperties`, `items`, `minItems`, `maxItems`, entre outras, e **não** `minLength`.
- [Thinking do generateContent](https://ai.google.dev/gemini-api/docs/generate-content/thinking):
  `generationConfig.thinkingConfig.thinkingLevel`; `thoughtsTokenCount`.
- [Migrating to the Interactions API](https://ai.google.dev/gemini-api/docs/migrate-to-interactions):
  "While `generateContent` remains fully supported, we recommend the Interactions API for all new
  development" (R13).

## R4 — Schema da resposta (o mesmo nos 2 modelos)

```json
{"type": "object",
 "properties": {
   "edge_cases_analysis": {"type": "string"},
   "tests": {"type": "array", "items": {
       "type": "object",
       "properties": {"input": {"type": "string"}, "output": {"type": "string"}},
       "required": ["input", "output"], "additionalProperties": false}}},
 "required": ["edge_cases_analysis", "tests"], "additionalProperties": false}
```

- A ordem das chaves põe a análise antes dos testes (FR-008), e as duas APIs geram na ordem do
  schema.
- O schema não usa `minItems` nem `minLength`. Uma lista vazia ou um texto vazio é tratado pela
  interpretação (falha de formato `no_usable_test`, ou teste descartado), e não pelo schema: assim
  a regra é a mesma nos dois modelos, independente do que cada API aceita.
- Não há campo de cálculo por teste (A10).
- O mesmo schema é o modelo Pydantic `LlmAnswer` (`extra="forbid"`), que confere a resposta
  depois de recebida. Mesmo com o modo estrito, a resposta é conferida, porque uma resposta
  cortada ou recusada não segue o schema.

## R5 — Texto-base `src/prompt_templates/llm_prompt.txt` (rascunho para os autores)

Os mesmos três marcadores do SLM, para `ai_clients.prompt` montar o prompt sem mudança.
Comparado com `slm_prompt.txt`:
- o STEP 1 é o mesmo, com o traço do exemplo feito "à mão";
- o STEP 2 (entradas) é o STEP 3 do SLM, palavra por palavra (FR-007);
- a única parte nova é a do oráculo;
- o formato pedido passa a ser os dois campos JSON (sem blocos XML na resposta, porque a API
  impõe o schema).

```text
<system_rules>
You are an expert competitive programmer and test designer.

Given the problem in <context_data>, write a diverse set of test cases that
would expose subtle bugs in other solutions. For each test case, give the
INPUT and the exact EXPECTED OUTPUT that a correct program would print.

If <context_data> contains only source code, infer what the program must do and
the exact input format from how the code reads its input.

STEP 1 - Analyze (write it in the field edge_cases_analysis)
- Restate the input format and every constraint in your own words.
- Restate the exact rule that defines the correct answer, including boundary
  conditions (equality, ties, limits, off-by-one).
- Trace the example in <few_shot_example> by hand and confirm that you get
  EXACTLY the expected output. If you do not, fix your understanding first.
- Keep this analysis short: at most 15 lines.

STEP 2 - Test cases (write them in the field tests)
- Do NOT copy the example.
- Every value in every input MUST satisfy ALL constraints of the problem.
  Never write an empty input. Never write an invalid input.
- If the input starts with the number of test cases, that number MUST match the
  number of test cases that follow.
- Cover, when relevant to this problem:
  * the smallest possible case;
  * values exactly at each boundary of the rules, and just below and above it;
  * extreme VALUES (for example the maximum allowed number) to catch overflow;
  * all-equal or repeated elements;
  * sorted and reverse-sorted data;
  * a few medium, irregular cases.
- Keep each input SHORT: at most about 50 elements and 20 lines.
  Never truncate, abbreviate or write "...".
- Do not repeat the same input twice.
- Each input is one complete stdin, exactly as the program would read it.
- For each input, compute the expected output carefully, step by step, before
  writing it, and write it exactly in the required output format.

OUTPUT FORMAT
Answer with one JSON object with the field edge_cases_analysis (text) and the
field tests (a list of objects, each with the fields input and output, both
text).
</system_rules>

<context_data>
(scenario-dependent content)
</context_data>

<few_shot_example>
Here is a public test case of this problem, for reference:
Input: (dataset example input)
Expected Output: (dataset example output)
</few_shot_example>

<task>
Follow STEP 1 and STEP 2 and answer with the JSON object described in OUTPUT
FORMAT.
</task>
```

**Motivo**: FR-006 a FR-008, A2, A10 e A11. O SLM é a referência de tudo o que não é oráculo (D1).
O texto é dos autores, que o revisam antes da implementação. O hash é gravado no `run.json` e em
cada tentativa (FR-009).

## R6 — Classificação de cada resposta e de cada erro

Uma resposta HTTP 200 passa por quatro conferências, nesta ordem. A primeira que falhar decide o
resultado.
1. **Raciocínio (A12, FR-018a).** Se os *tokens* de raciocínio forem 0 ou não vierem, a resposta
   é barrada: fica gravada em `barred/`, o envio de chamadas novas para, e o código de saída é 6.
2. **Término.** Uma resposta cortada pelo teto de saída é a falha `truncated` (OpenAI
   `incomplete`/`max_output_tokens`; Gemini `MAX_TOKENS`). Uma recusa ou um bloqueio é a falha
   `refusal` (o item `refusal` da OpenAI) ou `safety_block` (OpenAI `content_filter`; Gemini
   `promptFeedback.blockReason` ou um `finishReason` de segurança, com a categoria gravada, A13).
3. **Texto.** Texto vazio é a falha `empty_response`; texto que não é JSON é `not_json`; JSON fora
   do `LlmAnswer` é `schema_violation`.
4. **Testes (FR-013).**
   - A cerca Markdown que envolve a entrada ou a saída inteira é retirada, como na predição do SLM.
   - O texto ganha exatamente uma quebra de linha final.
   - Um teste vazio ou abreviado é descartado.
   - Uma entrada repetida fica só na primeira ocorrência, e uma saída diferente para ela conta como
     conflito.
   - Uma cópia do exemplo é mantida e contada.
   - Se não sobrar nenhum teste, a falha é `no_usable_test`.

As 7 falhas de formato de FR-015, com nome fixo, são `empty_response`, `not_json`,
`schema_violation`, `truncated`, `refusal`, `safety_block` e `no_usable_test`.

**Decidido na implementação (2026-10-15)**: um JSON válido pode trazer um caractere substituto
solto (`\ud800`), que não é texto UTF-8 e não poderia ser gravado; a resposta inteira é então
`schema_violation` ("a text is not valid UTF-8"), gravada normalmente, e JSON aninhado demais
(`RecursionError`) é `not_json`. A interpretação é pura e nunca levanta exceção (testada com
entradas hostis), o que garante FR-010: a resposta crua vai inteira no registro da tentativa, e
reinterpretá-la nunca exige chamar a API de novo (o mesmo desenho do SLM).

| Erro HTTP ou de rede | Classe | Efeito |
|---|---|---|
| rede, *timeout* de leitura, corpo cortado, 5xx, 408, 409, 429 (exceto cota esgotada) | infraestrutura (FR-018) | a mesma chamada é repetida, sem gravar nada |
| 400 (pedido malformado, schema recusado), 401/403 (chave), 404 (modelo), 429 com `insufficient_quota` (OpenAI: cota ou crédito esgotado) | erro que não passa sozinho | para na hora com código 3, sem repetir e sem gastar tentativa |

No Gemini, o 429 de cota (`RESOURCE_EXHAUSTED`) era tratado igual ao 429 de limite de
requisições. **Revisto em 2026-10-16, depois da primeira tentativa do piloto** (camada gratuita,
limites de 5 pedidos por minuto e 20 por dia): o corpo do 429 traz um `google.rpc.QuotaFailure` com
o `quotaId` da cota estourada; quando ele tem `PerDay`, a cota é diária, e repetir antes de ela
renovar só gastaria as repetições, então é um erro que não passa sozinho (código 3, nada gravado,
retomada com `--resume` depois). A cota por minuto continua sendo esperada, respeitando o
`retryDelay`.

## R7 — Espera, repetições e tempo de leitura

- **Espera:** começa em 5 s, dobra a cada falha seguida e para em 60 s, como no SLM (`config`).
  Se a API indicar um tempo de espera (`Retry-After` na OpenAI e no Gemini, ou `retryDelay` do
  `RetryInfo` nos detalhes do erro do Gemini), espera-se o maior entre o valor indicado e a espera
  crescente, sem limite superior.
- **Teto de repetições seguidas:** configurável por modelo, `OPENAI_MAX_INFRA_RETRIES` e
  `GEMINI_MAX_INFRA_RETRIES`, com padrão 30.
- **Tempo de leitura:** `LLM_HTTP_TIMEOUT_S`, com padrão 900 s, porque uma resposta sem streaming
  só chega depois do raciocínio inteiro.
- **Ritmo de pedidos (desde 2026-10-16):** `OPENAI_MAX_REQUESTS_PER_MINUTE` e
  `GEMINI_MAX_REQUESTS_PER_MINUTE`, opcionais. Com N, os inícios de pedido do processo, repetições
  incluídas e entre todas as *threads*, ficam espaçados por 60/N s. Motivo: a primeira tentativa do
  piloto do Gemini, na camada gratuita (5 pedidos por minuto, 20 por dia), mandou 4 pedidos ao
  mesmo tempo e recebeu 429 e 503 seguidos; a espera depois do erro não basta para não estourar o
  limite.
- **Esperas interrompíveis (desde 2026-10-16):** toda espera (a do ritmo e a de uma falha de
  infraestrutura) acaba na hora quando a invocação para (teto de gasto, resposta barrada, erro que
  não passa sozinho, `Ctrl+C`): antes, um `Ctrl+C` durante uma espera de 42 s esperava os 42 s.
- Nenhum desses valores muda a resposta, e nenhum entra no `run.json`.

## R8 — Concorrência, teto de gasto e barreira: um processo, N chamadas

- **Chamadas simultâneas:** cada `generate` de um modelo abre um conjunto de N *threads*
  (`concurrent.futures.ThreadPoolExecutor`), com N vindo de `OPENAI_MAX_CONCURRENCY` ou
  `GEMINI_MAX_CONCURRENCY` (padrão 4, A5). Cada *thread* trata uma combinação inteira, uma
  tentativa depois da outra, sob a trava da combinação: o `flock` de `claim`, que também vale
  entre *threads*, porque cada uma abre o seu arquivo.
- **Despacho:** um coordenador entrega as combinações em ordem canônica e para de entregar, e de
  começar tentativas novas, quando algum destes sinais é ligado:
  - o **teto de gasto** foi atingido (soma protegida por um `Lock` dos custos das tentativas
    concluídas e das respostas barradas);
  - uma **resposta foi barrada** (A12);
  - o **teto de repetições** de infraestrutura estourou;
  - houve um **erro que não passa sozinho**;
  - o processo foi **interrompido** (`Ctrl+C` ou `SIGTERM`).

  As chamadas já enviadas terminam e são gravadas (FR-022a), **também na interrupção**
  (implementado em 2026-10-15): o `Ctrl+C` chega à *thread* principal, que para de despachar e
  espera as chamadas em andamento, cujas respostas são gravadas atomicamente; a retomada não as
  pede de novo. Só um encerramento à força (`kill -9`, ou o `docker stop` passados os seus 10 s)
  abandona uma chamada em andamento, que então é refeita e paga duas vezes (o que SC-005
  admite).
- **Códigos de saída novos:** **5**, teto de gasto atingido; **6**, resposta sem raciocínio.
- **Precedência:** `130` > `3` > `6` > `1` > `5` > `4` > `0`. As linhas `manual:` e o gasto da
  invocação saem sempre.
- **Dois modelos ao mesmo tempo:** dois processos, um por modelo, cada um na sua pasta.

**Alternativas consideradas**:
- `asyncio`: rejeitado, porque a biblioteca padrão não tem cliente HTTP assíncrono.
- Vários processos por modelo, como os dois `generate` do SLM: rejeitado como padrão, porque A5
  pede as chamadas dentro de um processo. Ainda assim, continua possível e seguro, pela trava por
  combinação.

## R9 — Custo e dry-run sem nenhuma chamada **[DECIDIDO, 2026-10-15 — autores]**

**Tabela de preços** (`ai_clients/llm/config.py`): linhas `(modelo, válido a partir de,
entrada, entrada em cache, saída)`, em US$ por milhão de *tokens*, cada uma com fonte e data de
acesso.

| Modelo | Válido a partir de | Entrada | Entrada em cache | Saída |
|---|---|---|---|---|
| GPT | 2026-10-15 | 0,75 | 0,075 | 4,50 |
| Gemini | 2026-10-15 | 0,75 | 0,075 | 3,75 |
| Gemini | 2027-01-01 | 1,50 | 0,15 | 7,50 |

- **Custo de uma chamada:** usa a linha válida na data da chamada,
  `(entrada − cache) × preço de entrada + cache × preço de cache + saída × preço de saída`.
- **O que conta como saída:** na OpenAI é `output_tokens`, que já inclui o raciocínio; no Gemini
  é `candidatesTokenCount + thoughtsTokenCount`.
- **Registro:** a tabela inteira vai para o `run.json`, mas não é comparada no `--resume`
  (FR-020). O custo de cada tentativa é gravado nela.

**Dry-run** (decidido pelos autores): **não chama nenhuma API**. Monta os prompts reais das
combinações pendentes e estima:
- **Entrada:** `caracteres ÷ CHARS_PER_TOKEN`, um valor por modelo. Antes do piloto é 3,0,
  conservador: o SLM mediu no mínimo 3,32 caracteres por *token* no piloto 1, e um valor menor
  dá mais *tokens* e mais custo. Depois do piloto, a constante passa a ser a razão medida
  (soma dos caracteres dos prompts ÷ soma de `input_tokens` ou `promptTokenCount`), com data e
  origem.
- **Saída:** duas colunas. Uma é o teto de saída, limite superior de cada chamada. A outra é a
  média medida no piloto, ausente antes dele.
- **O que mostra:** por modelo e no total, o número de combinações e de chamadas (uma por
  combinação, mais o limite superior de 3), os *tokens* estimados e o custo nas duas colunas.
  Nada é gravado.

**Motivo**: SC-004 exige zero chamadas pagas, e a documentação da OpenAI não diz se o
`/v1/responses/input_tokens` é cobrado. Assim o dry-run também não depende de chave nem de rede.

**Alternativas consideradas**: os endpoints de contagem dos dois provedores, ou só o do Gemini.
Rejeitados pelos autores.

**Efeito na spec**: FR-021 e a User Story 2 passam a dizer "estimados a partir dos prompts reais",
e não "medidos" (propagado em 2026-10-15).

**Medido em 2026-10-15** (`generate --model gpt|gemini --dry-run` sobre os 200 problemas reais,
nenhuma chamada; revisão `696da2c` com o código ainda não commitado): 600 combinações por modelo;
caracteres dos prompts por cenário 834.962 (caixa-preta), 641.316 (caixa-branca) e 996.366
(híbrido), 2.472.644 no total, cerca de 824 mil *tokens* de entrada no total pela razão 3,0; maior prompt de 6.237
caracteres na caixa-preta (`61_B`), 5.015 na caixa-branca (`893_C`) e 7.459 no híbrido (`61_B`).
Faixa de custo, com a saída no teto de 32.768 *tokens* nos dois extremos (antes do piloto não há
média medida): GPT de US$ 89,09 (uma chamada por combinação) a US$ 267,28 (as três tentativas);
Gemini de US$ 74,35 a US$ 223,04, pelo preço introdutório. O custo real tende a ser bem menor que o
extremo de baixo, porque uma resposta raramente usa o teto inteiro; o piloto mede isso.

## R10 — Persistência, retomada, `close` e `change-template`

A árvore e os arquivos estão no data-model §1 e §3; os estados, no §4. As regras do SLM valem
iguais:
- todo fato é um arquivo imutável gravado atomicamente;
- o estado é derivado dos arquivos;
- o `suite.json` é função pura das tentativas (ou de `manual_close.json`);
- uma combinação danificada é listada e pulada (código 1);
- a configuração do `run.json` é comparada campo a campo no `--resume`, menos `created_at`,
  `price_table`, o teto de gasto, as esperas e a concorrência.

`close` e `change-template` têm o mesmo comportamento e as mesmas mensagens do SLM, sobre o estado
do LLM:
- `close` só vale para `awaiting_manual` (3 tentativas com falha de formato);
- `change-template` move, para `superseded/<NNN>/`, as tentativas feitas com o texto-base antigo e
  o `suite.json`, e a combinação é refeita a partir da tentativa movida.

Uma resposta barrada fica em `barred/<id>/<cenário>/<n>.json` (`n` sequencial), fora de
`problems/`. Ela é empacotada e entra no relatório, mas não nas métricas.

## R11 — Relatório, pacote, `verify` e `cli check`

**Relatório e pacote**, um por modelo (A7):

| Modelo | Relatório | Pacote | Manifesto |
|---|---|---|---|
| GPT | `manifests/gpt_generation_report.json` | `data/gpt_suites.zip` (raiz `suites/gpt/`) | `manifests/gpt_suites.manifest.json` |
| Gemini | `manifests/gemini_generation_report.json` | `data/gemini_suites.zip` (raiz `suites/gemini/`) | `manifests/gemini_suites.manifest.json` |

- O relatório traz os agregados de FR-025 (data-model §3.6).
- O relatório do piloto é versionado com o sufixo `.piloto<N>.json`, como no SLM (FR-023a).

**`cli check`:** duas camadas, `gpt_suites` e `gemini_suites`, com as mesmas regras de
severidade da camada `slm_suites`:
- enquanto não há manifesto, o que falta é `[AVISO]`;
- buraco nas tentativas, mais de 3 tentativas ou arquivo estranho é sempre `[FALHA]`;
- depois do `package`, tudo o que falta é `[FALHA]`.

`docs/verificacao-consistencia.md` ganha as duas camadas.

## R12 — Teto de saída (FR-023): provisório para o piloto

- **Valor do piloto:** `max_output_tokens` e `maxOutputTokens` em **32.768** nos dois modelos.
- **Motivo:** a OpenAI recomenda reservar ao menos 25.000 *tokens* para raciocínio e resposta
  quando se começa; o Gemini 3.8 Flash aceita até 64k de saída. O mesmo número nos dois deixa o
  teto fora da comparação.
- **Depois do piloto:** o valor final é fixado com o maior total de saída medido (resposta mais
  raciocínio) e uma folga, ou mantido se nenhuma resposta passou perto. O valor entra no `run.json`,
  e mudá-lo depois do piloto significa uma execução nova, o que o FR-023a já exige.

## R15 — Piloto 1 do Gemini **[MEDIDO, 2026-10-16]**

Conta com faturamento ativo (decidido por Milena em 2026-10-16), revisão `94fec3a` com o ritmo de
pedidos e a cota diária ainda não commitados, `GEMINI_MAX_CONCURRENCY=1`, relatório versionado em
`manifests/gemini_generation_report.piloto1.json`, árvore arquivada em
`data/suites/gemini-piloto1/`. Uma primeira tentativa na camada gratuita, no mesmo dia, recebeu
só 503 e 429 e não gravou nenhuma resposta (R6, R7).

**Medido**: 15 combinações (os 5 problemas `1000_B`, `1005_C`, `1008_B`, `1_B` e `61_B` nos 3 cenários),
15 chamadas, todas com suíte na 1ª tentativa; nenhuma falha de formato, resposta cortada, resposta
barrada ou bloqueio de segurança; `finishReason` `STOP` e `modelVersion` `gemini-3.8-flash` nas 15;
saída por chamada (resposta mais raciocínio) média de 1.965 *tokens*, mediana 1.640, mínima 1.114 e
máxima 3.551 (11% do teto de 32.768), dos quais raciocínio médio de 1.206 (de 334 a 2.845) e a
resposta visível no máximo 894; 69.717 caracteres de prompt para 20.786 *tokens* de entrada
devolvidos pela API (3,354 caracteres por *token*; a estimativa usava 3,0); suítes de 7 a 12
testes (mediana 10), 2 testes descartados por entrada vazia; tempo por chamada mediano de 13,1 s e
máximo de 29,1 s; custo real US$ 0,126, contra US$ 1,86 a 5,58 estimados antes do piloto.

**O que muda**:
- **Estimativa (R9):** `CHARS_PER_TOKEN` do Gemini passa a 3,354 e a média de saída medida,
  1.965, vira o extremo de baixo da faixa. Dry-run da execução completa refeito em 2026-10-16:
  cerca de 737 mil *tokens* de entrada, US$ 4,97 (uma chamada por combinação, saída média) a
  US$ 222,84 (três chamadas no teto).
- **Teto de saída (R12):** mantido em 32.768 nos dois modelos. A maior saída usou 11% dele, e só
  se paga o que é usado; reduzir arriscaria cortar uma resposta longa (`truncated`) sem economia.
  Fica no `run.json`; mudá-lo depois exige uma execução nova.
- **Concorrência e ritmo:** sem 429 nem 503 na conta paga com uma chamada por vez; a execução
  completa pode usar mais chamadas ao mesmo tempo, dentro do limite de pedidos por minuto da conta.

Pendente: o piloto do GPT (T055) e a parte da decisão T056 que depende dele.

## R13 — `generateContent` rotulado "Legacy" **[DECIDIDO, 2026-10-15 — autores: manter]**

As páginas do `generateContent` passaram a se chamar "Gemini Generate Content API (Legacy)", e o
Google recomenda a Interactions API para projetos novos. Ao mesmo tempo, o `generateContent`
"remains fully supported", sem data de desligamento.

**Decisão**: manter o `generateContent`, que é a decisão A3 e a Tabela 2. O rótulo fica registrado
como risco e limitação na metodologia; se o Google anunciar desligamento antes da execução
completa, os autores revisitam a decisão.

**Alternativa rejeitada**: a Interactions API com `store=false`. O estado é guardado por padrão
(`store=true`), e o isolamento passaria a depender de um parâmetro, e não da natureza da chamada.

## R14 — Testes

**Duplos de teste:**
- um `FakeProvider` com uma tabela `(modelo, problema, cenário, número da chamada) → corpo HTTP |
  exceção`, que grava o corpo exato de cada pedido;
- um relógio falso;
- um coordenador com N = 1 e N = 4.

**O que cada área de testes cobre:**

| Área | O que se confere |
|---|---|
| Corpo do pedido | igual ao de R3, campo a campo, nos dois modelos; nenhum campo proibido (FR-002, FR-003, A11, A13) |
| Leitura das respostas | corpos reais dos dois provedores, gravados no piloto e em exemplos da documentação, para cada falha de R6 |
| Interpretação | as regras de FR-013, com as mesmas tabelas de casos da predição do SLM |
| Custo e preços | a soma do relatório é igual à soma das chamadas (SC-003); troca de preço na virada de data |
| Confirmação e teto de gasto | sem confirmação, nenhum pedido sai (SC-004); com teto, nenhum pedido depois dele (SC-004a) |
| Barreira de raciocínio | contagem 0 ou ausente, nos dois modelos (SC-004b) |
| Infraestrutura | repetição sem gastar tentativa (SC-006); `Retry-After`; teto; erros fatais |
| Retomada e concorrência | interrupção em cada ponto (SC-005); dois processos e N *threads* |
| Integridade | dano; relatório; pacote; `verify`; camadas do `cli check` |
| Leitor comum | o `SuiteView` lê suítes do SLM e dos LLMs (SC-007) |
| Não regressão | toda a suíte do SLM continua passando (FR-028) |

Nenhum teste chama uma API real. A única chamada real antes do piloto é a do próprio piloto,
com confirmação.
