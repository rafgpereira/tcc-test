# Módulo `ai_clients` (geração de suítes de teste pelo modelo local)

> **Status**: em implementação · **Metodologia**: `docs/metodologia-referencia.md`, seção 3

## (a) Propósito

Gera, para cada problema do dataset e cada um dos três cenários de contexto, uma suíte de casos de teste com o modelo local Qwen2.5-Coder-7B (via Ollama), cuja saída esperada é calculada executando de verdade uma solução em Python escrita pelo próprio modelo, para alimentar a etapa de avaliação.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
e tenha o dataset descompactado em `data/dataset/`
([README do módulo `dataset`](../dataset/README.md), Cenário B).

**Este módulo ainda está em implementação: nenhum comando dele existe ainda.** Esta seção descreve
o funcionamento planejado e será completada, com os comandos exatos, à medida que cada comando for
implementado e executado de verdade.

Para cada problema e cada cenário — **caixa-preta** (o modelo vê só o enunciado), **caixa-branca**
(só a solução de referência em C++) e **híbrido** (os dois) — o modelo recebe um único pedido, sem
memória de pedidos anteriores, e responde com duas coisas: **entradas de teste** que exploram casos
difíceis e uma **solução do problema em Python**. O modelo nunca diz qual é a saída certa: ela é
obtida rodando essa solução Python sobre cada entrada, isolada, sem internet. A solução Python só é
aceita se acertar os testes públicos do problema; se errar, ou se a resposta do modelo não puder
ser lida, é feito um novo pedido, até 6 por problema e cenário. Detalhes da decisão:
[`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 3.

O trabalho tem duas etapas, cada uma num serviço do Docker Compose:

1. **Geração** (serviço `app`, com internet, para falar com o Ollama): envia os pedidos e guarda
   cada resposta do modelo exatamente como veio, sem executar nada.
2. **Execução** (serviço `sandbox`, sem internet, o único autorizado a executar código de
   terceiros): roda as soluções Python e calcula as saídas esperadas.

### Cenário A — Rodar do zero

A completar quando os comandos existirem. Em linhas gerais: alternar a geração e a execução até
todas as combinações de problema e cenário terminarem, gerar o relatório e empacotar.

### Cenário B — Descompactar o que já existe

A completar quando o pacote `data/slm_suites.zip` existir: descompactá-lo em `data/` e conferir a
integridade contra o manifesto.

### Comandos

Subcomandos **planejados** (ainda não disponíveis):

| Subcomando | Serviço | O que vai fazer |
|---|---|---|
| `generate` | `app` | envia os pedidos ao modelo e guarda as respostas; `--resume` para continuar uma execução já começada, `--dry-run` para só mostrar o que seria enviado, `--limit N`, `--problem ID`, `--scenario S` |
| `execute` | `sandbox` | roda as soluções Python e calcula as saídas esperadas; `--dry-run`, `--limit N`, `--problem ID`, `--scenario S` |
| `report` | `app` | grava o relatório com os números agregados |
| `package` | `app` | gera o pacote versionável da execução final e o manifesto de integridade |
| `verify` | `app` | confere o pacote (e, com `--extracted`, a pasta descompactada) contra o manifesto |

Códigos de saída planejados: `0` sucesso, `1` falha de dados, `2` uso incorreto, `3` falha de
infraestrutura ou de configuração do Ollama, `130` interrompido.

### Se algo der errado

A completar junto com os comandos.

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/enunciado.md`, `AC_ref.cpp`, `testes.json`, `metadata.json` | texto, C++ e JSON | dataset descompactado ([`dataset`](../dataset/README.md)); `metadata.json` traz os limites de tempo e memória, `testes.json` os testes públicos |
| `manifests/dataset.manifest.json` | JSON | versionado; conferido antes de qualquer trabalho |
| `src/prompt_templates/slm_prompt.txt` | texto (inglês) | versionado; o texto-base do pedido enviado ao modelo, igual nos três cenários exceto pelo bloco de contexto |
| `OLLAMA_BASE_URL`, `OLLAMA_HARDWARE_LABEL` (e, opcionais, `OLLAMA_HTTP_TIMEOUT_S`, `OLLAMA_MAX_INFRA_RETRIES`) | variáveis do `.env` | preenchidas pelo operador (ver `.env.example`) |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| Respostas do modelo, execuções e suíte final de cada problema e cenário | JSON | `data/suites/slm/problems/<id>/<cenário>/` (não versionado); a suíte final é de onde a etapa de avaliação vai ler |
| Relatório agregado | JSON | `manifests/slm_generation_report.json` (versionado) |
| Pacote da execução final e manifesto | zip e JSON | `data/slm_suites.zip` e `manifests/slm_suites.manifest.json` (versionados) |

## (e) Dependências e pré-requisitos

- Python 3.11 da imagem (`docker compose build`); nenhuma dependência além das já fixadas no
  `uv.lock`.
- Um servidor Ollama acessível, na própria máquina ou remoto, com o modelo `qwen2.5-coder:7b`
  baixado (`ollama pull qwen2.5-coder:7b`), e as variáveis do `.env` preenchidas.
- Serviço `app` para a geração e `sandbox` para a execução (motor do módulo
  [`sandbox`](../sandbox/README.md), sem alteração).
- Dataset descompactado em `data/dataset/` e íntegro.

## (f) Limitações conhecidas

- A solução Python do modelo só é validada pelos testes públicos do problema; se ela estiver
  errada numa entrada que nenhum teste público cobre, a saída esperada daquela entrada fica errada.
- Nos cenários com código, o modelo pode só traduzir a solução C++ para Python, em vez de resolver
  o problema de forma independente.
- Não há verificação de que a solução Python é determinística nem de que cada entrada gerada
  respeita as restrições do enunciado.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 3
- Testes: `tests/ai_clients/` (`docker compose run --rm sandbox pytest tests/ai_clients`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `generate` | pendente | — |
| `execute` | pendente | — |
| `report` | pendente | — |
| `package` | pendente | — |
| `verify` | pendente | — |
