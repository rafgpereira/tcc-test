# Research: Geração de Suítes de Teste pelos LLMs Comerciais

**Feature**: `004-llm-test-generation` | **Date**: 2026-10-15 | **Plan**: ainda não gerado
(`/speckit-plan` não rodou; este arquivo começa com a decisão A3, tomada antes do plano, e o
`/speckit-plan` acrescenta os demais itens sem apagar este)

Cada item: **Decisão**, **Motivo**, **Alternativas consideradas**, **Fontes** (documentação
oficial, com data de acesso) e, quando houver, **Conferir no piloto**.

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
| Saída | `text.format` do tipo `json_schema` com `strict: true` | `responseMimeType: application/json` com schema de resposta |

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
  REST, dentro de `generationConfig` (forma exata do campo a confirmar no plano, ver abaixo), e o
  `mimeType: application/json` do texto é o `responseMimeType`.

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

**A confirmar no plano** (as páginas lidas não mostraram por inteiro):
- O caminho exato do nível de raciocínio no `generateContent` REST (a página de raciocínio
  mostra `generation_config.thinking_level` só para a Interactions API).
- O campo do schema de resposta a usar (`responseSchema` ou `responseJsonSchema`).

**Conferir no piloto** (registrar o resultado neste item e na metodologia):
1. O GPT recebe de fato o raciocínio `medium`: toda tentativa do `gpt-5.4-mini` deve ter
   `usage.output_tokens_details.reasoning_tokens > 0`. Se vier 0, o parâmetro não chegou e a
   execução não segue.
2. Que versão do Gemini 3.8 Flash responde: registrar o `modelVersion` devolvido em cada tentativa
   (esperado `gemini-3.8-flash` ou uma versão dele) e se o `thoughtsTokenCount` vem maior que 0.
3. Que o GPT responde com o snapshot pedido: o `model` devolvido deve ser
   `gpt-5.4-mini-2026-03-17`.
