# Quickstart: validação dos LLMs comerciais

**Feature**: `004-llm-test-generation` | Comandos: [contracts/cli.md](./contracts/cli.md) |
Arquivos: [data-model.md](./data-model.md)

Roteiro para provar, nível a nível, que o módulo funciona. Os níveis 1 a 3 não gastam nada. O
nível 4 é o piloto pago, e o 5 é a execução completa. Todos os comandos rodam no contêiner.

## Pré-requisitos

- **Ambiente:** a imagem construída (`docker compose build`), o dataset descompactado
  (`unzip data/dataset.zip -d data/`) e `docker compose run --rm app python -m cli check --deep`
  terminando com código 0.
- **Texto-base:** `src/prompt_templates/llm_prompt.txt` revisado pelos autores (rascunho em
  research R5).
- **Chaves:** `.env` com `OPENAI_API_KEY` e `GEMINI_API_KEY`, de contas com faturamento ativo,
  necessárias só a partir do nível 4.

## Nível 1 — testes automáticos, sem nenhuma chamada

```bash
docker compose run --rm sandbox pytest tests/ai_clients tests/cli
```

Esperado: tudo passa, incluindo toda a suíte do SLM já existente (FR-028). Os testes novos cobrem
o que está em research R14:
- o corpo exato dos pedidos, sem nenhum campo proibido;
- a leitura de respostas reais dos dois provedores e cada falha de formato;
- confirmação, teto de gasto e barreira de raciocínio;
- infraestrutura, retomada e concorrência;
- o `SuiteView` lendo suítes do SLM e dos LLMs;
- relatório, pacote e as camadas do `cli check`.

## Nível 2 — dry-run (nada é chamado nem gravado)

```bash
docker compose run --rm app python -m ai_clients generate --model gpt --dry-run
docker compose run --rm app python -m ai_clients generate --model gemini --dry-run
```

Esperado:
- uma linha por cenário e o total, com combinações, chamadas, *tokens* estimados e a faixa de
  custo;
- `data/suites/` sem mudança;
- funciona sem chave no `.env`.

Antes do piloto, a razão caracteres/*token* aparece como `3.0 (conservative, before the pilot)`.

## Nível 3 — recusas, sem nenhuma chamada

| Comando | Esperado |
|---|---|
| `generate --model gpt --problem 1000_B --scenario black_box` | a estimativa e `error: ... run again with --confirm-spend ...`, com código 2 e nenhum pedido enviado (SC-004) |
| o mesmo, sem `OPENAI_API_KEY` | código 2, dizendo qual variável falta |
| `generate --model gpt --confirm-spend 1` com o dataset alterado | código 1, antes de qualquer pedido |
| `execute --model gemini` | código 2 (não há execução para os modelos comerciais) |

## Nível 4 — piloto pago (FR-023a; execução separada)

**Escopo:** os mesmos 5 problemas dos pilotos do SLM (`1000_B`, `1005_C`, `1008_B`, `1_B`,
`61_B`), nos 3 cenários e nos 2 modelos, ou seja, 30 combinações. Os dois modelos rodam em
paralelo, cada um num terminal:

```bash
docker compose run --rm app python -m ai_clients generate --model gpt \
  --problem 1000_B --problem 1005_C --problem 1008_B --problem 1_B --problem 61_B \
  --dry-run   # primeiro a estimativa; depois o mesmo comando com --confirm-spend <teto em US$>
```

**O que conferir e registrar** (em research A3 e R12, e na metodologia):
1. **A primeira chamada de cada modelo é aceita pela API.** Um HTTP 400 no Gemini por causa de
   `responseFormat` aciona o plano B de R3.
2. **Nenhuma resposta barrada.** Se houver código 6, investigar antes de seguir (A12).
3. **O `model` do GPT** é `gpt-5.4-mini-2026-03-17`, e o **`modelVersion` do Gemini** fica
   registrado (A3).
4. **Números medidos:** maior saída total (resposta mais raciocínio) por modelo, que fixa o teto
   de R12; razão caracteres/*token* de entrada por modelo, que fixa o `CHARS_PER_TOKEN` de R9;
   tempo por chamada; taxa de falha de formato por razão; bloqueios de segurança, que podem fazer
   os autores revisitarem a A13; custo real comparado com a estimativa do dry-run (SC-009).

**Fechamento do piloto:**

```bash
docker compose run --rm app python -m ai_clients report --model gpt   # e --model gemini
```

Os relatórios são guardados como `manifests/<m>_generation_report.piloto1.json`. Depois, as pastas
`data/suites/<m>` são movidas para fora (`mv data/suites/gpt data/suites/gpt-piloto1`), porque a
execução completa começa do zero.

## Nível 5 — execução completa e fechamento

1. `cli check --deep` com código 0.
2. `generate --model <m> --dry-run` (com a razão medida) e depois `generate --model <m>
   --confirm-spend <teto>`. Repetir com `--resume` até não sobrar nada pendente. Os códigos 5 e 6 e
   as linhas `manual:` dizem o que fazer.
3. `close` para cada combinação em `awaiting_manual`, se houver.
4. `report`, `package` e `verify --extracted data/suites/<m>`, para cada modelo.
5. `python -m cli check --deep` com código 0 nas camadas `gpt_suites` e `gemini_suites` (SC-008).
6. `scripts/check_docs_sync.py --closing --feature specs/004-llm-test-generation` com código 0.
