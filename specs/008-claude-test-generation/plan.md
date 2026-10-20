# Implementation Plan: Terceiro modelo comercial: Claude

**Branch**: `008-claude-test-generation` (feature do spec-kit; o trabalho acontece na `main`,
Princípio X) | **Date**: 2026-10-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-claude-test-generation/spec.md`

## Summary

O Claude Haiku 5.5 (`claude-haiku-5-5`) vira o terceiro modelo comercial, com `--model claude`,
reaproveitando tudo o que a feature 004 construiu para o GPT e o Gemini. O que muda:

- **Um cliente HTTP novo**, da Messages API da Anthropic (R1). O pedido leva:
  - uma única mensagem de usuário, sem instrução de sistema;
  - raciocínio adaptativo com `effort: medium`;
  - saída em JSON com o mesmo schema dos outros dois;
  - teto de saída de 32.768 tokens;
  - nenhum parâmetro de amostragem.
- **A leitura da resposta** (R3): texto, término, modelo e tokens. O raciocínio vem de
  `usage.output_tokens_details.thinking_tokens` (R2), o sinal da regra de resposta sem raciocínio.
- **A configuração**: identificador, endereço, variáveis do `.env`, estimativa e linha de preço com
  data e fonte (R4).
- **A camada `claude_suites`** no `cli check` e a documentação dos 3 modelos comerciais.
- **Uma emenda da constitution** (S1): o texto fixa "dois LLMs comerciais".

Nada muda no comportamento do modelo local, do GPT nem do Gemini (FR-019).

## Sinalizações e decisões

| # | Lacuna encontrada ao planejar | O que o plano faz | Decisão |
|---|---|---|---|
| **S1** | A constitution fala em "dois LLMs comerciais", lista os modelos no Princípio III e dimensiona o experimento em "200 × 3 modelos × 3 cenários" (IX). | Proposta de emenda **1.9.0**, só de escopo e nomes, sem regra nova (texto em research R9). | **Aprovada em 2026-10-20 (Milena); aplicada: constitution 1.9.0.** |
| **S2** | Se o Haiku 5.5 não trouxer `thinking_tokens`, todas as respostas seriam barradas e a combinação gastaria 3 pedidos antes de virar `accepted_barred`. | O piloto começa com `--limit 1` e a primeira resposta é conferida antes de seguir (R2, R8). | — (mitigação) |
| **S3** | O Haiku 5.5 tem dois preços, pelo tamanho do prompt (até 100 mil tokens ou mais). | Só a linha de até 100 mil é cadastrada; uma chamada maior é recusada no cálculo de custo, com mensagem (R4). O maior prompt tem 7.459 caracteres. | — (informativo) |

## Technical Context

**Language/Version**: Python 3.11 (o da imagem).

**Primary Dependencies**: **nenhuma nova**. Biblioteca padrão (`urllib`), como os outros dois
clientes (R1).

**Storage**:
- não versionados: `data/suites/claude/` e `data/suites/claude-piloto1/`;
- versionados:
  - `data/claude_suites.zip`, `manifests/claude_suites.manifest.json` e
    `manifests/claude_generation_report.json`;
  - `manifests/claude_generation_report.piloto1.json`.

**Testing**: `pytest` no `sandbox`. O provedor é falso (`FakeProvider`), com respostas no formato
da Anthropic gravadas nos testes; nenhum teste chama a API.

**Target Platform**: serviço `app` (com rede).

**Project Type**: pipeline de linha de comando; um modelo novo no módulo `ai_clients`.

**Performance Goals**: nenhuma; a latência e o custo são medidos no piloto.

**Constraints**:
- nenhuma chamada paga sem confirmação e teto;
- o pedido não leva estado nem parâmetros de amostragem;
- o mesmo texto-base (mesmo hash) dos outros dois;
- nada muda nos outros modelos.

**Scale/Scope**: 600 combinações (200 problemas × 3 cenários). A faixa de custo é estimada pelo
dry-run, com os preços de R4.

## Constitution Check

*GATE: antes da Fase 0 e revisto depois da Fase 1.* Constitution 1.8.0, com a emenda 1.9.0
proposta em S1.

| Princípio | Como o plano cumpre | Status |
|---|---|---|
| I. Metodologia mutável | D1 a D3 e as decisões do clarify estão na metodologia, seção 3 e histórico | ✅ |
| II. Reprodutibilidade | A configuração da execução grava o modelo, os parâmetros, o schema, o hash do texto-base, o hash do dataset (revisão 2), o preço e o teto; o pacote tem manifesto | ✅ |
| III. Sem estado | Um pedido por chamada, uma mensagem só, sem `system`, sem histórico e sem cache do provedor; o Claude entra na lista pela emenda S1 | ✅ (emenda 1.9.0) |
| IV. Contratos versionados | Nenhum schema novo; `LlmModel` ganha um valor; o `run.json`, a tentativa e a suíte do Claude seguem os schemas da 004 | ✅ |
| V. Sandboxing | Nada é executado | ✅ |
| VI. Testa a si próprio | Testes do corpo do pedido, da leitura da resposta, da regra de resposta sem raciocínio, dos erros, do custo, do dry-run e da camada do `cli check` | ✅ |
| VII. Retomada | A mesma da 004 | ✅ |
| VIII. Custo | A mesma confirmação, o mesmo teto e o mesmo registro de tokens, custo e tempo da 004, com a linha de preço datada | ✅ |
| IX. Simplicidade | Reaproveita a 004; só o cliente e a configuração são novos; sem SDK | ✅ (o tamanho do experimento muda pela emenda S1) |
| X. Revisão humana | A emenda e a execução paga são dos autores; o agente não roda Git | ✅ |
| XI. Documentação viva | README do `ai_clients`, referência da raiz, `CLAUDE.md`, `.env.example`, `docs/verificacao-consistencia.md` e metodologia | ✅ |

**Gate**: passou depois da emenda 1.9.0, aprovada e aplicada em 2026-10-20.

## Project Structure

### Documentation (this feature)

```text
specs/008-claude-test-generation/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md  sync-matrix.json
├── contracts/cli.md  contracts/provider.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
src/ai_clients/llm/
├── config.py       # "claude" em MODELS e nas tabelas; linha de preço; variáveis do .env
├── providers.py    # corpo do pedido, _claude_answer, ClaudeClient, mensagem de crédito
├── interpret.py    # término max_tokens / model_context_window_exceeded -> truncated
└── schemas.py      # LlmModel ganha "claude"
src/cli/consistency.py         # camada claude_suites
.env.example                   # ANTHROPIC_API_KEY e as opcionais
tests/ai_clients/llm/          # fixtures de resposta da Anthropic; testes por modelo
tests/cli/test_consistency.py  # a camada nova
```

**Structure Decision**: tudo dentro de `src/ai_clients/llm/`, como decidido na 004 (A4).

## Complexity Tracking

Sem violações a justificar, além da emenda S1, que é de escopo e não de regra.

## Constitution 1.9.0 compliance review (T022, 2026-10-20)

- **III**: o corpo do Claude é uma única mensagem `user`, sem `system`, sem histórico e sem `cache_control` (teste `test_the_claude_body_is_exactly_the_contract`); a lista de parâmetros proibidos vale para ele (`test_no_forbidden_parameter_is_ever_sent[claude]`).
- **VIII**: tokens, custo e tempo gravados em toda chamada (linha de preço datada de 2026-10-20); nenhuma chamada sem `--confirm-spend` (testes parametrizados por modelo); prompt acima do limite do preço recusado antes de chamar.
- **IX**: nenhuma dependência nova; o Claude reaproveita a estrutura da 004, com um cliente e a configuração novos.
