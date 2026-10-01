# Módulo `ai_clients` (geração de suítes de teste pelo modelo local)

> **Status**: em implementação · **Metodologia**: `docs/metodologia-referencia.md`, seção 3

## (a) Propósito

Gera, para cada problema do dataset e cada um dos três cenários de contexto, uma suíte de casos de teste com o modelo local Qwen2.5-Coder-7B (via Ollama), cuja saída esperada é calculada executando de verdade uma solução em Python escrita pelo próprio modelo, para alimentar a etapa de avaliação.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
e tenha o dataset descompactado em `data/dataset/`
([README do módulo `dataset`](../dataset/README.md), Cenário B).

**Este módulo ainda está em implementação.** Hoje só existe a etapa de geração (`generate`); a
execução das soluções, o relatório e o pacote ainda não existem, e a seção será completada à
medida que cada comando for implementado e executado de verdade.

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
   terceiros): roda as soluções Python e calcula as saídas esperadas. *(ainda não disponível)*

### Cenário A — Rodar do zero

**Preparar o Ollama e o `.env`.** Num servidor Ollama (nesta máquina ou em outra), baixe o modelo
com `ollama pull qwen2.5-coder:7b`. No `.env` (o arquivo de configuração na raiz do projeto, ver
`.env.example`), preencha:

- `OLLAMA_BASE_URL` — o endereço do Ollama: `http://host.docker.internal:11434` se ele roda nesta
  máquina (o serviço `app` enxerga a máquina por esse nome), ou `http://<servidor>:11434` se roda
  em outra;
- `OLLAMA_HARDWARE_LABEL` — um texto que descreve a máquina onde o Ollama roda (placa de vídeo,
  processador, memória), gravado junto de cada resposta; nunca é detectado sozinho.

Opcionais: `OLLAMA_HTTP_TIMEOUT_S` (quanto esperar por uma resposta, padrão 900 segundos; aumente
se o Ollama roda sem placa de vídeo) e `OLLAMA_MAX_INFRA_RETRIES` (quantas vezes seguidas a mesma
chamada é repetida se o Ollama não responder, padrão 30).

**1. Conferir o que seria enviado, sem chamar o modelo:**

```bash
docker compose run --rm app python -m ai_clients generate --dry-run
```

Não grava nada nem precisa do Ollama. Imprime uma linha por pedido previsto
(`<id> <cenário> attempt 1 seed 43: prompt <N> chars`) e, no fim, `dry run: 600 calls planned` e o
maior pedido de cada cenário. Medido em 2026-09-30 sobre os 200 problemas: 600 pedidos; o maior tem
8.118 caracteres (híbrido de `61_B`). Antes de listar, o comando confere o dataset inteiro contra o
manifesto, o que pode levar alguns minutos.

**2. Gerar:**

```bash
docker compose run --rm app python -m ai_clients generate
```

A primeira execução cria `data/suites/slm/run.json` (qual modelo, com quais parâmetros, sobre qual
dataset). Para cada problema e cenário, grava em `data/suites/slm/problems/<id>/<cenário>/` um
arquivo `attempt_<n>.generation.json` com a resposta do modelo e o que foi lido dela, e imprime uma
linha por pedido, como `1000_B black_box attempt 1 seed 43: parsed (7 inputs) — 1570+812 tokens,
stop, 21.5 s` (exemplo ilustrativo, não medido). Se a resposta não puder ser lida
(`unparseable (...)`), o pedido seguinte, com a próxima seed, é feito na hora; depois de 6
respostas ilegíveis a suíte daquele problema e cenário é descartada (`suite.json` com `status:
discarded`). No fim: `done: N calls, N parsed, N unparseable, N discarded suites; N pending
execution`.

Rodar de novo exige `--resume` (proteção contra continuar por engano uma execução antiga):
`docker compose run --rm app python -m ai_clients generate --resume`.

A etapa de execução (que calcula as saídas esperadas) e o relatório ainda não existem.

### Cenário B — Descompactar o que já existe

A completar quando o pacote `data/slm_suites.zip` existir: descompactá-lo em `data/` e conferir a
integridade contra o manifesto.

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m ai_clients generate` | `app` | pede ao modelo as entradas e a solução Python de cada problema e cenário ainda pendente e grava as respostas. `--resume` é obrigatório quando já existe `data/suites/slm/run.json` (continua a mesma execução; sem ele o comando recusa com código `2`). `--dry-run` só lista os pedidos previstos e o tamanho de cada um, sem Ollama e sem gravar nada. `--limit N` trata no máximo N combinações de problema e cenário (na ordem: problema em ordem alfabética, depois caixa-preta, caixa-branca, híbrido). `--problem ID` e `--scenario black_box`, `white_box` ou `hybrid` (repetíveis) restringem. Se o Ollama não responde, a mesma chamada é repetida (espera de 5 s dobrando até 60 s) sem gastar tentativa, até `OLLAMA_MAX_INFRA_RETRIES` vezes seguidas; aí o comando para com código `3` sem gravar nada daquela tentativa. Interrompido (Ctrl+C, `docker stop`), sai com `130`; rodar de novo com `--resume` refaz só a chamada que estava em andamento, com a mesma seed |

Subcomandos **planejados** (ainda não disponíveis):

| Subcomando | Serviço | O que vai fazer |
|---|---|---|
| `execute` | `sandbox` | roda as soluções Python e calcula as saídas esperadas; `--dry-run`, `--limit N`, `--problem ID`, `--scenario S` |
| `report` | `app` | grava o relatório com os números agregados |
| `package` | `app` | gera o pacote versionável da execução final e o manifesto de integridade |
| `verify` | `app` | confere o pacote (e, com `--extracted`, a pasta descompactada) contra o manifesto |

Códigos de saída: `0` sucesso, `1` falha de dados, `2` uso incorreto, `3` falha de infraestrutura
ou de configuração do Ollama, `130` interrompido.

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `error: data/dataset does not match manifests/dataset.manifest.json`, ou `... not found; restore the versioned dataset` (`1`) | `unzip data/dataset.zip -d data/` (apague `data/dataset` antes) e rode de novo |
| `error: OLLAMA_BASE_URL is not set in .env` (ou `OLLAMA_HARDWARE_LABEL`) (`2`) | preencha a variável no `.env` |
| `error: a run already exists in data/suites/slm; use --resume to continue it` (`2`) | rode com `--resume`; para começar do zero, apague `data/suites/slm` |
| `ollama unavailable (...); retrying the same call ...` | o Ollama não respondeu; o comando espera e tenta de novo sozinho. Confira se o Ollama está no ar e se o endereço do `.env` está certo |
| `infrastructure failure: ollama unavailable after N consecutive retries ...` (`3`) | coloque o Ollama no ar e rode `generate --resume`; nada foi perdido |
| `configuration error: model qwen2.5-coder:7b is not installed ...` (`3`) | `ollama pull qwen2.5-coder:7b` no servidor do Ollama |
| `configuration error: ... the prompt may have been truncated ...` (`3`) | o pedido não coube na janela de contexto do modelo; avise os autores (é um parâmetro do experimento); nada foi gravado |
| `error: another ... command is already running` (`1`) | espere o outro comando terminar |

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
| `generate --dry-run` (200 problemas) | 2026-09-30 | 2e679ae+dirty |
| `generate` | pendente | — |
| `execute` | pendente | — |
| `report` | pendente | — |
| `package` | pendente | — |
| `verify` | pendente | — |
