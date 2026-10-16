# Implementation Plan: Geração de Suítes de Teste pelos LLMs Comerciais

**Branch**: `004-llm-test-generation` (feature do spec-kit; o trabalho acontece na `main`, Princípio X)
| **Date**: 2026-10-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-llm-test-generation/spec.md`

## Summary

Para cada um dos 200 problemas × 3 cenários × 2 modelos comerciais (`gpt-5.4-mini-2026-03-17` pela
Responses API da OpenAI; `gemini-3.8-flash` pelo `generateContent` do Google), o módulo faz uma
chamada sem estado com o mesmo texto-base, e só o `<context_data>` muda entre os cenários. A
chamada leva raciocínio `medium` explícito, nenhuma seed ou temperatura e saída JSON com schema
estrito (`edge_cases_analysis` antes de `tests`). O modelo prevê as saídas esperadas, e nada é
executado. Uma tentativa nova acontece só por falha de formato, até 3; esgotadas, a combinação
aguarda os autores (`close`).

Toda resposta crua é gravada antes de ser interpretada. A suíte vai para um `suite.json` com
status `accepted_predicted`, as mesmas chaves de topo do SLM e um leitor comum para a avaliação.
O custo tem quatro proteções:
- dry-run sem nenhuma chamada;
- confirmação obrigatória a cada invocação, que já traz o teto de gasto (`--confirm-spend`);
- parada quando o teto é atingido (código 5);
- barreira automática contra resposta sem raciocínio (código 6).

Cada modelo roda num processo próprio, com N chamadas simultâneas (padrão 4) e a trava por
combinação do SLM. Relatório, pacote, manifesto e camada do `cli check` são um por modelo.

Abordagem técnica (detalhes em [research.md](./research.md)):

- **Reaproveitado do SLM** (R0), por importação e sem mudar o comportamento do SLM: leitura do
  problema, montagem do prompt (os mesmos três marcadores), regras de teste vazio, abreviado e
  cercado da predição, travas, escrita atômica, verificação do dataset, núcleo do zip, manifesto e
  `verify`, estatísticas de tamanho, registro de subcomandos e códigos 0–4 e 130.
- **Novo** em `src/ai_clients/llm/`:
  - clientes HTTP da biblioteca padrão, sem SDK (R2, R3);
  - schema de resposta (R4);
  - classificação das respostas e dos erros (R6);
  - coordenador com *threads*, espera, teto de gasto e barreira (R7, R8);
  - custo, preços e estimativa (R9);
  - estado por arquivos, `close` e `change-template` (R10);
  - relatório e pacote (R11).
- **Também novos:** o schema `LlmSuite` e o leitor comum `SuiteView` (R1), o texto-base
  `src/prompt_templates/llm_prompt.txt` (R5) e as camadas `gpt_suites` e `gemini_suites` do
  `cli check`.

## Sinalizações e decisões

| # | Lacuna encontrada ao planejar | O que o plano faz | Decisão |
|---|---|---|---|
| **S1** | O `SlmSuite` confere cada tentativa contra a tabela de seeds do SLM e exige 15 tentativas no `discarded_manual`, então uma suíte de LLM não passa nele (FR-017, SC-007). | `LlmSuite` com as mesmas chaves de topo e valores fixos documentados nas do SLM; leitor comum `SuiteView` para a avaliação; o `SlmSuite` e as 600 suítes empacotadas não mudam (R1). | **Decidido em 2026-10-15 (Milena)**: schema LLM + leitor comum. FR-017 e SC-007 atualizados. |
| **S2** | O dry-run precisa de *tokens* de entrada sem chamada paga, e a OpenAI não documenta se `/v1/responses/input_tokens` é cobrado (FR-021, SC-004). | Estimativa offline: caracteres dos prompts reais ÷ razão por modelo (3,0 antes do piloto, a medida depois); saída pelo teto e, depois do piloto, pela média medida (R9). | **Decidido em 2026-10-15 (Milena)**: estimativa offline. FR-021 e a User Story 2 dizem "estimados". |
| **S3** | O Google passou a rotular o `generateContent` como "Legacy" e recomenda a Interactions API, que guarda estado por padrão. | Mantém o `generateContent`; o rótulo fica registrado como risco e limitação (R13). | **Decidido em 2026-10-15 (Milena)**: manter. |
| **S4** | A forma REST do JSON com schema no `generateContent` mudou: a documentação atual usa `generationConfig.responseFormat.text` (`mimeType`, `schema`), e o texto da A3 dizia `responseMimeType`. | Usa `responseFormat.text`; o plano B (`responseMimeType` + `responseJsonSchema`) entra se a primeira chamada do piloto receber HTTP 400, que não é cobrado (R3). | — (informativo; a confirmação real é a primeira chamada do piloto). |
| **S5** | A confirmação e o teto de gasto (FR-022, FR-022a) precisam de uma forma na CLI. | Uma opção só, `--confirm-spend USD`: dar o teto é confirmar. Sem ela, a recusa mostra a estimativa (contracts/cli.md). | — (informativo; cumpre FR-022 e FR-022a sem uma segunda opção). |
| **S6** | O teto de saída (FR-023) só é fixado depois do piloto. | 32.768 nos dois modelos no piloto; o valor final vem da maior saída medida (R12). | — (o piloto fixa). |

## Technical Context

**Language/Version**: Python 3.11 (o da imagem, `uv`).

**Primary Dependencies**: **nenhuma nova**:
- `pydantic` para os schemas;
- biblioteca padrão para HTTP (`urllib.request`), `json`, `concurrent.futures`, `threading`,
  trava (`fcntl`) e zip.

Serviços externos: a Responses API da OpenAI e o `generateContent` da Gemini API (R3).

**Storage**:
- arquivos JSON em `data/suites/gpt/` e `data/suites/gemini/`, nunca versionados;
- `manifests/<m>_generation_report.json` e `manifests/<m>_suites.manifest.json`, versionados;
- `data/<m>_suites.zip`, só da execução final.

**Testing**: `pytest` no serviço `sandbox`, com `FakeProvider` (corpos HTTP gravados) e relógio
falso. Nenhum teste chama uma API real (R14).

**Target Platform**: o contêiner `app` do `docker-compose.yml`, que tem rede. Nada é compilado nem
executado.

**Project Type**: pipeline de linha de comando (subpacote `src/ai_clients/llm/` do pacote
existente, A4).

**Performance Goals**: nenhuma meta. O tempo por chamada e a vazão sob o limite de requisições são
medidos no piloto (quickstart, nível 4); nenhum tempo é afirmado sem medição.

**Constraints**:
- 3 tentativas por combinação, só por falha de formato (A1);
- teto de saída provisório de 32.768 (R12);
- até `*_MAX_CONCURRENCY` chamadas simultâneas por processo, com padrão 4 (A5);
- espera de 5 a 60 s respeitando o `Retry-After`/`retryDelay`, com teto de 30 repetições (R7);
- tempo de leitura de 900 s;
- nenhum parâmetro de amostragem (A3);
- prompt numa mensagem só (A11);
- nenhum `safetySettings` (A13).

**Scale/Scope**: 600 combinações por modelo, 1.200 no total. No máximo 3.600 chamadas que geram
tentativa, mais as repetições de infraestrutura, que não são cobradas por falha, e as eventuais
respostas barradas. Esses máximos não são estimativa de custo: o custo vem do dry-run e do piloto.

## Constitution Check

*GATE: antes da Fase 0 e revisto depois da Fase 1.* Constitution 1.7.1.

| Princípio | Como o plano cumpre | Status |
|---|---|---|
| I. Metodologia mutável | Decisões do plano (S1–S6, R1–R14) registradas na metodologia, seções 3 e 6; divergências com o PDF na seção 7, item 41 (modelo do Gemini e nomes dos parâmetros) | ✅ |
| II. Reprodutibilidade | **Desvio justificado (ver Complexity Tracking): nenhuma seed nos LLMs (A3).** A proveniência de cada resposta vem do `model_returned`, dos parâmetros enviados e da resposta crua, gravados em cada tentativa; `run.json` com modelo, parâmetros, schema, texto-base e dataset, comparado no `--resume`; `cli check --deep` antes do piloto e da execução; pacote e manifesto da execução final (emenda 1.6.0); camadas novas do `cli check`; a não reprodutibilidade bit a bit fica registrada como limitação | ✅ com desvio justificado |
| III. Sem estado | OpenAI com `store: false` e sem `previous_response_id`/`conversation`/`instructions`; Gemini com `generateContent` de um turno, sem `cachedContent`/`systemInstruction`; cliente sem estado; o corpo exato é conferido em teste (SC-002) | ✅ |
| IV. Contratos versionados | Pydantic para `run.json`, tentativa, resposta barrada, `LlmSuite`, `SuiteView`, relatório e manifesto; o `suite.json` mantém o contrato de arquivo do SLM (`schema_version` 2, mesmas chaves de topo) e o `SlmSuite` não muda (S1) | ✅ |
| V. Sandboxing | Não se aplica: o módulo não compila nem executa código (FR-014) | ✅ |
| VI. Testa a si próprio | Testes de R14 com provedor falso, sem chamada real; a suíte inteira do SLM continua passando | ✅ |
| VII. Retomada | Arquivos imutáveis, escrita atômica, estado derivado, `suite.json` função pura, trava por combinação também entre *threads*; uma chamada em andamento na interrupção pode ser paga de novo (aceito, SC-005) | ✅ |
| VIII. Custo/uso de IA | *Tokens*, custo e tempo por chamada; dry-run sem chamada; nenhuma chamada paga sem `--confirm-spend` a cada invocação; teto de gasto; custo das barradas contado | ✅ |
| IX. Simplicidade | Sem dependência nova nem SDK; reaproveita o SLM por importação; o coordenador com *threads* é o mínimo para A5 | ✅ |
| X. Revisão humana | Nenhuma operação de Git pelo agente; o texto-base (R5) é revisado pelos autores antes da implementação | ✅ |
| XI. Documentação viva | Spec, research e metodologia atualizados neste ciclo, mais `sync-matrix.json`; o `tasks.md` terá o README do módulo (3 modelos), o README da raiz (comandos, `.env`), `docs/verificacao-consistencia.md` e `.env.example` | ✅ |

**Reavaliação pós-Fase 1**: sem violação. As dependências entre módulos estão justificadas em
Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/004-llm-test-generation/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # A3, R0–R14
├── data-model.md
├── quickstart.md
├── sync-matrix.json     # D1–D7 da spec ↔ metodologia (check_docs_sync C5)
├── contracts/
│   ├── cli.md
│   └── providers.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/prompt_templates/llm_prompt.txt     # novo; rascunho em research R5, revisado pelos autores
src/ai_clients/
├── __main__.py          # + --model {slm,gpt,gemini} nos subcomandos; códigos 5 e 6; despacho para llm/
├── parser.py            # strip_data_fence e is_abbreviated públicos (sem mudar o comportamento)
├── store.py             # mensagem de trava com a pasta recebida (o SLM imprime o mesmo texto)
├── packaging.py         # núcleo com caminhos por parâmetro (o SLM chama com os de hoje)
├── schemas/
│   └── suite_view.py    # SuiteView + read_suite_view (R1)
└── llm/
    ├── __init__.py
    ├── config.py        # modelos, URLs, parâmetros, teto de saída, preços, CHARS_PER_TOKEN, caminhos, variáveis do .env
    ├── schemas.py       # LlmRunConfig, LlmAttempt, BarredResponse, LlmSuite, relatório, manifesto, LlmAnswer
    ├── providers.py     # LLMProvider, OpenAIClient, GeminiClient, ProviderAnswer, exceções
    ├── interpret.py     # R6: término, texto, testes (FR-013)
    ├── cost.py          # preço por data, custo da chamada, estimativa do dry-run
    ├── store.py         # estados (data-model §4), escrita, finalize, barred/
    ├── generation.py    # coordenador: threads, espera, teto de gasto, barreira
    ├── closing.py  template_change.py  report.py  packaging.py
src/cli/consistency.py   # + camadas gpt_suites e gemini_suites
tests/ai_clients/llm/
├── fakes.py             # FakeProvider, relógio falso
├── fixtures/            # corpos HTTP de exemplo dos dois provedores
├── test_providers.py  test_interpret.py  test_cost.py  test_schemas.py  test_store.py
├── test_generation.py  test_spend_cap.py  test_barrier.py  test_concurrency.py
├── test_resume.py  test_damage.py  test_closing.py  test_template_change.py
├── test_report.py  test_packaging.py  test_cli.py
tests/ai_clients/test_suite_view.py       # lê suítes do SLM e dos LLMs (SC-007)
tests/cli/test_consistency.py             # + camadas novas
.env.example                              # + OPENAI_API_KEY, GEMINI_API_KEY e opcionais (sem valor)
```

**Structure Decision**: um subpacote `src/ai_clients/llm/` dentro do pacote existente (A4). O SLM
continua nos módulos atuais, que só ganham parâmetros ou nomes públicos onde o reaproveitamento
exige (R0), sem mudar o que fazem. O `cli` ganha duas camadas. `sandbox`, `dataset` e `mutation`
não mudam.

## Complexity Tracking

| Ponto | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| *Threads* dentro de um processo (`ThreadPoolExecutor`) | A5 pede chamadas simultâneas num processo; a latência de cada chamada é dominada pelo raciocínio do modelo | rodar vários processos, como no SLM, foi rejeitado na A5; `asyncio` não tem cliente HTTP na biblioteca padrão |
| Códigos de saída 5 e 6, que o SLM não tem | teto de gasto e resposta sem raciocínio são paradas esperadas, e o operador precisa distingui-las de dano (1) e de infraestrutura (3) | reaproveitar 1 ou 3 misturaria uma parada por orçamento ou por suspeita de parâmetro perdido com falhas que pedem outra ação |
| Um segundo schema de `suite.json` (`LlmSuite`) e um leitor comum | o `SlmSuite` não aceita suítes sem a política de seeds do SLM (S1) | generalizar o `SlmSuite` acoplaria os dois módulos e mexeria no schema das suítes já empacotadas |
| Pequenas mudanças em `parser.py`, `store.py` e `packaging.py` do SLM | FR-029 manda reaproveitar, não copiar | copiar as funções duplicaria regras; essas mudanças não alteram o comportamento do SLM, conferido pela suíte dele |
| Nenhuma seed nas chamadas aos LLMs, apesar do Princípio II ("toda operação com aleatoriedade MUST usar seed fixa e documentada") | Decisão A3 dos autores (2026-10-15, `research.md` A3): nenhuma das duas APIs garante reprodução com seed. A OpenAI não documenta seed para modelos de raciocínio na Responses API, e no Gemini 3.x a amostragem (`temperature`, `top_p`, `top_k`) está descontinuada e é ignorada. Mandar seed só onde fosse aceita parametrizaria os dois modelos de formas diferentes (D3). A reprodutibilidade dos números publicados vem do pacote versionado da execução final, com manifesto, que é exatamente a exceção da emenda 1.6.0 para "chamadas a APIs de IA não estritamente reprodutíveis bit a bit" | enviar seed onde a API aceitasse não garante reprodução e cria uma assimetria entre os modelos sem ganho mensurável; fixar a temperatura em 0 contraria a recomendação do Google e é ignorada no Gemini 3.8 Flash |
