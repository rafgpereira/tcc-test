# Geração de Casos de Teste com Modelos de Linguagem — Pipeline Experimental

Software experimental de um Trabalho de Conclusão de Curso (Engenharia de Software, UnB, TCC
de dupla) que avalia a eficácia de modelos de linguagem na geração automática de casos de
teste unitários em C++.

> **Este é o guia geral do projeto.** Ele explica a arquitetura do experimento, como os módulos
> se conectam, e como preparar o ambiente — uma vez por máquina — antes de usar qualquer módulo.
> Cada módulo tem seu próprio README com o passo a passo completo de como usá-lo (link na tabela
> "Módulos e estado", abaixo); este documento é o ponto de partida e o índice, não o detalhe de
> cada módulo.
>
> **Estado atual (2026-10-15)**: os módulos `dataset` (extração, validação e empacotamento do
> dataset), `sandbox` (motor de execução isolada de C++), `mutation` (100 mutantes por problema) e
> `ai_clients` para o modelo local (suítes de teste do Qwen2.5-Coder-14B) estão **implementados**,
> e os três artefatos do experimento já foram gerados de verdade e estão neste repositório, cada
> um com o seu manifesto de integridade: o dataset (`data/dataset.zip`, 200 problemas), os mutantes
> (`data/mutants.zip`, 20.000 mutantes) e as suítes do modelo local (`data/slm_suites.zip`, 600
> combinações de problema e cenário, todas com suíte: 505 `accepted`, 93 `accepted_fallback`, 2
> `accepted_predicted`, nenhuma fechada à mão). Quem clona o projeto só precisa descompactar e
> conferir, não precisa gerar nada. Um comando na raiz, `python -m cli check`, confere se dataset,
> mutantes e suítes estão completos e 1:1. As chamadas aos dois modelos comerciais estão sendo
> especificadas, ainda sem código; os demais módulos (avaliação, métricas, orquestrador) ainda não
> têm especificação nem código; a tabela "Módulos e estado" marca isso.

## O que o experimento responde

Três modelos (dois LLMs comerciais, **GPT-5.4-mini** e **Gemini 3.8 Flash**, e um SLM local,
**Qwen2.5-Coder-14B** via Ollama) geram testes unitários para problemas algorítmicos, sob três
cenários de contexto:

- **Caixa-preta**: só o enunciado.
- **Caixa-branca**: só o código da solução correta.
- **Híbrida**: enunciado e código.

Os testes gerados são executados, em ambiente isolado, contra códigos com falhas reais (submissões
incorretas humanas) e falhas artificiais (mutantes), e contra o código correto. Perguntas
centrais: qual estratégia de contexto detecta melhor falhas reais, qual é mais sensível a
defeitos sintéticos, qual gera mais falsos positivos (alucinações) e como combinar contexto
ajuda ou atrapalha. Detalhes completos do desenho experimental:
[`docs/metodologia-referencia.md`](docs/metodologia-referencia.md).

Escala: **200 problemas × 3 modelos × 3 cenários** (1.800 suítes de teste geradas).

## Arquitetura: como os módulos se conectam

```text
 code_contests (Hugging Face, streaming)
        │
        ▼
 ┌──────────────┐  dataset.zip: por problema, enunciado.md, AC_ref.cpp,
 │   dataset    │  WA_1..100.cpp, testes.json, metadata.json, validacao.json
 └──────┬───────┘
        │  usa o motor de execução para validar AC e WAs
        ▼                                   ┌──────────────────────────────┐
 ┌──────────────┐                           │  sandbox (motor de execução) │
 │   mutation   │  100 mutantes por problema│  compila e executa C++ sob   │
 └──────┬───────┘  a partir do AC_ref       │  limites de tempo, memória e │
        │                                   │  pilha e atribui o veredito  │
        ▼                                   └───────────────▲──────────────┘
 ┌──────────────┐  suítes de teste (JSON)                   │ reutilizado sem
 │  ai_clients  │  3 modelos × 3 cenários                   │ alteração
 └──────┬───────┘                                           │
        ▼                                                   │
 ┌──────────────┐  executa cada suíte contra AC, WAs e      │
 │  avaliação   │  mutantes, com curto-circuito ────────────┘
 └──────┬───────┘  → registro CSV de vereditos
        ▼
 ┌──────────────┐  TDF (falhas reais), MS (mutantes),
 │   metrics    │  TFP (falsos positivos), IIC (influência do contexto)
 └──────────────┘
        ▲
   cli: orquestrador que amarra tudo
```

O **motor de execução** (`src/sandbox/`) é um só: o mesmo que valida o dataset é reutilizado
na avaliação, para que nenhum código do dataset falhe no motor só durante o experimento.

## Módulos e estado

| Módulo | Papel | Metodologia | Estado | README do módulo |
|---|---|---|---|---|
| `src/dataset/` | extrai, valida e empacota o dataset experimental | seção 1 | **implementado**: dataset real gerado, validado e empacotado (200 problemas, ~12 MiB) | [README](src/dataset/README.md) |
| `src/sandbox/` | motor de execução isolada de C++, usado pelo `dataset` | seções 1.4 e 4 | **implementado**: motor, isolamento e auto-checagem testados | [README](src/sandbox/README.md) |
| `src/mutation/` | gera 100 mutantes por problema e os empacota | seção 2 | **implementado**: 200 problemas, 20.000 mutantes, pacote versionado (~9 MiB) | [README](src/mutation/README.md) |
| `src/ai_clients/` | chamadas stateless aos 3 modelos | seção 3 | **implementado** para o modelo local (SLM): 600 de 600 combinações com suíte, pacote versionado (6.597.040 bytes); os dois modelos comerciais ainda não implementados | [README](src/ai_clients/README.md) |
| avaliação | injeta as suítes geradas e registra vereditos em CSV | seção 4 | **sem spec** | a criar |
| `src/metrics/` | TDF, MS, TFP, IIC | seção 5 | **sem spec** (IIC ainda não operacionalizado) | a criar |
| `src/cli/` | comandos que cruzam módulos (hoje `check`) e, no futuro, o orquestrador do experimento | — | **em implementação**: `check` pronto; o orquestrador ainda sem especificação | [README](src/cli/README.md) |

O formato dos READMEs de módulo é o de [`docs/template-modulo.md`](docs/template-modulo.md).

## Guia de execução, do clone ao primeiro comando

Este guia parte do zero e **não pressupõe conhecimento de Docker**. Ele cobre a preparação do
ambiente, que se faz **uma vez por máquina** e vale para todos os módulos. Depois disso, cada
módulo tem o seu próprio passo a passo na seção "(b) Como executar" do seu README (tabela acima).
O projeto foi desenvolvido e testado em **Linux**; macOS e Windows (WSL2) não foram verificados.
Nenhum código C++ de terceiros é compilado ou executado fora do Docker.

### O que você precisa ter instalado

| Programa | Para quê | Como conferir |
|---|---|---|
| Git | baixar o projeto | `git --version` |
| Docker Engine com o plugin Compose v2 | rodar tudo (ver "Docker em poucas palavras") | `docker --version` e `docker compose version` |

Para instalar o Docker, siga a página da sua distribuição em <https://docs.docker.com/engine/install/>,
incluindo os "Post-installation steps for Linux" (eles permitem usar `docker` sem `sudo`). Você
também precisa de internet (para baixar a imagem base e, se for gerar o dataset do zero, os dados
de origem) e de espaço livre em disco (a imagem base do compilador tem cerca de 1 GB).

Teste se o Docker está pronto: `docker run --rm hello-world`. Se aparecer `permission denied` com
`/var/run/docker.sock`, o seu usuário não está no grupo `docker`: rode
`sudo usermod -aG docker "$USER"`, saia da sessão do sistema e entre de novo.

### Docker em poucas palavras

- **Imagem**: um "computador congelado" com tudo instalado (compilador GCC 13.2.0, Python 3.11 e
  as bibliotecas do projeto). É igual para todo mundo, e é por isso que o experimento é
  reprodutível. Você a constrói uma vez (Passo 4).
- **Contêiner**: uma execução dessa imagem. Nasce quando você roda um comando e some quando o
  comando termina. O que o contêiner grava *dentro* dele se perde; o que grava em uma pasta
  compartilhada com o seu computador fica.
- **Volume (pasta compartilhada)**: uma pasta do seu computador que também aparece dentro do
  contêiner. Aqui são `./data` e `./manifests` (e, em desenvolvimento, o código). Por isso os
  arquivos que os comandos criam em `data/` aparecem para você na pasta `data/` do repositório.
- **Serviço**: uma "receita de contêiner" definida no arquivo `docker-compose.yml`. O projeto tem
  dois, e você escolhe qual usar em cada comando:

| Serviço | Acesso à internet | Para que serve |
|---|---|---|
| `app` | sim | baixar dados de origem, gerar relatórios, empacotar e verificar dados, lint e formatação |
| `sandbox` | **não**, de propósito | compilar e executar código C++ de terceiros com segurança (o dataset e, no futuro, as suítes geradas por IA); também roda os testes do projeto |

Como ler um comando do projeto:

| Pedaço de `docker compose run --rm app python -m dataset extract` | Significado |
|---|---|
| `docker compose run` | crie um contêiner de um serviço do `docker-compose.yml` e rode um comando nele |
| `--rm` | apague o contêiner quando o comando terminar (os arquivos em `data/` ficam) |
| `app` | o serviço escolhido (com internet) |
| `python -m dataset extract` | o comando que roda **dentro** do contêiner: o módulo Python `dataset`, subcomando `extract` |

Todos os comandos são executados **na pasta do repositório** (a que contém `docker-compose.yml`).

### Passo 1: baixar o projeto

```bash
git clone <url do repositório>
cd tcc-testgen-pipeline
```

### Passo 2: criar o arquivo `.env`

O `.env` guarda configurações locais suas; ele **nunca** vai para o Git. Ele tem três valores:

| Variável | O que é | Que valor colocar |
|---|---|---|
| `HOST_UID` | número que identifica o **seu usuário** no Linux | **não é qualquer valor: é o seu.** Rode `id -u` |
| `HOST_GID` | número do **seu grupo** principal | rode `id -g` |
| `HF_TOKEN` | chave opcional do Hugging Face (site de onde vem o dataset de origem) | pode ficar vazia: o dataset é público, o token só aumenta o limite de requisições |

Para que servem `HOST_UID` e `HOST_GID`: o contêiner roda os comandos como um usuário identificado
por esse número. Se o número for o seu, os arquivos criados em `data/` pertencem a você e você os lê,
edita e apaga normalmente. Se for outro, eles ficam com outro dono (como `root`) e você precisaria de
`sudo` para mexer neles, e o serviço `app` pode até falhar ao gravar. Em computadores Linux com um
único usuário os valores costumam ser `1000` e `1000`, que é o padrão do projeto, mas confira com
`id -u` e `id -g`.

O comando abaixo cria o `.env` já com os seus números (e não sobrescreve um `.env` que já exista):

```bash
[ -f .env ] || printf 'HOST_UID=%s\nHOST_GID=%s\nHF_TOKEN=\n' "$(id -u)" "$(id -g)" > .env
cat .env      # confira: HOST_UID e HOST_GID devem ser iguais à saída de `id -u` e `id -g`
```

A alternativa manual é `cp .env.example .env` e editar os números. Quando os módulos que chamam
modelos comerciais existirem, as chaves de API também vão neste arquivo (e só nele).

### Passo 3: criar a pasta `data/`

```bash
mkdir -p data
```

O Git não versiona `data/`, então ela não existe em um clone novo. Se você pulasse este passo, o
Docker a criaria como `root` na primeira execução, e o serviço `app` (que roda com o seu usuário)
não conseguiria gravar nela.

### Passo 4: construir a imagem

```bash
docker compose build
```

Baixa a imagem base do compilador e instala o Python e as bibliotecas fixadas em `uv.lock`. A
primeira vez leva alguns minutos e depende da sua conexão; as seguintes são rápidas. Só é preciso
repetir se o `Dockerfile` ou o `uv.lock` mudarem: o código do projeto é lido diretamente da sua
pasta (volumes de `docker-compose.override.yml`), então editar código não exige reconstruir.

### Passo 5: conferir que o ambiente funciona

```bash
docker compose run --rm sandbox pytest
```

Roda a suíte de testes do projeto inteiro. Esperado: a última linha diz `passed` (com o número de
testes) e não menciona `failed`. Este comando usa o serviço `sandbox` porque parte dos testes
compila e executa C++, o que só é permitido dentro dele.

### Onde ficam os arquivos

| Onde | O que é | No Git? |
|---|---|---|
| `.env` | suas configurações locais | não, nunca |
| `data/work/` | espaço de trabalho de quem gera o dataset do zero (ver README do módulo `dataset`) | não |
| `data/dataset/` | o dataset já descompactado e pronto para uso (ver README do módulo `dataset`) | não (é gerado a partir do zip) |
| `data/dataset.zip` | o dataset validado, compactado | **sim** |
| `data/mutants/` | os mutantes já descompactados (ou gerados) e prontos para uso (ver README do módulo `mutation`) | não (é gerado a partir do zip) |
| `data/mutants.zip` | os mutantes da execução final, compactados | **sim** |
| `manifests/` | manifestos de hashes e relatórios, para conferir a integridade dos artefatos | sim |

### Problemas comuns

| O que aparece | Causa provável | O que fazer |
|---|---|---|
| `permission denied` com `docker.sock` | seu usuário não está no grupo `docker` | `sudo usermod -aG docker "$USER"` e reinicie a sessão do sistema |
| `'compose' is not a docker command` | falta o plugin Compose v2 | instale o `docker-compose-plugin` (página de instalação do Docker acima) |
| `no configuration file provided: not found` | você não está na pasta do repositório | `cd tcc-testgen-pipeline` |
| `PermissionError` ao gravar em `data/`, ou arquivos em `data/` que você não consegue apagar | `data/` foi criada por `root` (Passo 3 pulado) | `sudo chown -R "$(id -u):$(id -g)" data` |
| um comando termina com falha de rede (código de saída `3`) | queda de conexão | rode o **mesmo comando** de novo: a maioria dos comandos retoma de onde parou |
| você apertou Ctrl+C no meio de um comando | interrupção pedida por você | rode o mesmo comando de novo; é seguro |

Para ver o código de saída do último comando: `echo $?` (`0` é sucesso).

## Depois da preparação: o que fazer em cada módulo

| Módulo | Quando usar | Onde está o passo a passo |
|---|---|---|
| `dataset` | obter o dataset (o caso comum: descompactar e conferir) ou gerá-lo do zero | [README do módulo](src/dataset/README.md) |
| `sandbox` | sem uso direto: é a biblioteca de execução isolada; só se opera diretamente para conferir a saúde do motor | [README do módulo](src/sandbox/README.md) |
| `mutation` | obter os mutantes (descompactar e conferir) ou gerá-los do zero | [README do módulo](src/mutation/README.md) |
| `cli` | conferir se dataset, mutantes e suítes do modelo local estão consistentes entre si | [README do módulo](src/cli/README.md) |
| `ai_clients` | obter as suítes de teste do modelo local (descompactar e conferir) ou gerá-las do zero (a preparação do Ollama, com o exemplo de um notebook do Kaggle com duas placas, está no README do módulo) | [README do módulo](src/ai_clients/README.md) |
| avaliação, `metrics` | ainda não implementados | sem README ainda |

## Conferir se os artefatos estão consistentes entre si

Cada módulo confere o seu próprio artefato contra o manifesto (`dataset verify`, `mutation verify`).
Para conferir o **conjunto** — se o dataset descompactado tem os 200 problemas e todos os arquivos
de cada um, se os mutantes têm exatamente 100 por problema, se as suítes do modelo local têm os 3
cenários de cada problema e se **não sobra nem falta nada** em
nenhum dos lados —, há um comando que percorre as pastas de verdade e imprime um resumo com as
contagens:

```bash
docker compose run --rm app python -m cli check          # nomes e contagens (menos de 1 s)
docker compose run --rm app python -m cli check --deep   # e também os hashes de todos os arquivos
```

Ele só lê, não olha o conteúdo dos códigos e termina com código `0` (sem falhas) ou `1`. Rode-o
depois de descompactar o dataset e os mutantes e **antes de qualquer etapa que consuma os dados** (o
envio às IAs e a execução final do experimento). O que ele confere e como estendê-lo estão em
[`docs/verificacao-consistencia.md`](docs/verificacao-consistencia.md).

## Reprodutibilidade

- Dependências fixadas em lockfile (`uv.lock`); imagem base fixada por digest; revisão do
  dataset de origem fixada; seed fixa (`42`).
- O dataset é distribuído como `data/dataset.zip` versionado, com o manifesto
  `manifests/dataset.manifest.json` (SHA-256 por arquivo) para verificar a identidade exata dos
  dados. Os mutantes seguem o mesmo modelo: só o pacote da **execução final**
  (`data/mutants.zip` e `manifests/mutants.manifest.json`) é versionado, porque o motor de execução
  tem uma margem de instabilidade medida e regenerar não garante os mesmos mutantes. Arquivos soltos
  de dataset ou de mutantes gerados durante o desenvolvimento nunca são versionados.
- Chamadas a modelos comerciais custam dinheiro: o pipeline nunca as dispara em lote sem
  confirmação explícita de quem executa.

## Referência de comandos

Lista única de **todos os comandos do projeto e suas variações**, para não ser preciso procurá-los
no código. Todos rodam na pasta do repositório; `app` tem internet, `sandbox` não tem e é o único
que compila e executa C++ de terceiros ("Docker em poucas palavras"). O passo a passo de cada módulo
está no README dele; `--help` de qualquer comando lista as opções de fato disponíveis
(`docker compose run --rm app python -m dataset --help`).

### Ambiente, testes e qualidade

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `docker compose build` | (nenhum) | constrói a imagem; repita depois de mudar o `Dockerfile` ou o `uv.lock` |
| `docker compose run --rm sandbox pytest` | `sandbox` | todos os testes do projeto; `pytest tests/<pasta>` roda uma parte: `tests/dataset`, `tests/sandbox`, `tests/mutation`, `tests/ai_clients`, `tests/cli` ou `tests/docs` |
| `docker compose run --rm app ruff check .` | `app` | análise estática; `--fix` corrige o que for automático |
| `docker compose run --rm app black --check .` | `app` | confere a formatação; sem `--check` reformata os arquivos |
| `docker compose run --rm app python scripts/check_docs_sync.py` | `app` | verifica se a documentação está sincronizada (READMEs, links, metodologia); `--module src/<módulo>` confere só um módulo |

### Módulo `dataset` ([README](src/dataset/README.md))

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `docker compose run --rm app python -m dataset extract` | `app` | lê o dataset de origem e grava o pool de elegíveis; `--limit-rows N` (teste rápido), `--splits LIST`, `--seed INT`; retoma se interrompido |
| `docker compose run --rm app python -m dataset report` | `app` | regenera o relatório legível do que já foi processado |
| `docker compose run --rm sandbox python -m dataset selfcheck` | `sandbox` | confere a saúde do motor com programas de veredito conhecido |
| `docker compose run --rm sandbox python -m dataset validate` | `sandbox` | executa cada problema no motor até reunir 200 completos; `--target N` (piloto: `--target 10`), `--workers N`, `--problem ID`; retoma se interrompido |
| `docker compose run --rm sandbox python -m dataset audit` | `sandbox` | reexecuta a amostra e repara o que divergir; `--problem ID` (repetível), `--workers N` |
| `docker compose run --rm app python -m dataset package` | `app` | gera `data/dataset.zip` e o manifesto; `--target N`, `--allow-partial` (só para teste) |
| `docker compose run --rm app python -m dataset verify` | `app` | confere o zip contra o manifesto; `--extracted data/dataset` confere também a pasta descompactada |
| `unzip data/dataset.zip -d data/` | (host) | descompacta o dataset em `data/dataset/` (nenhum comando o faz) |

### Módulo `mutation` ([README](src/mutation/README.md))

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `docker compose run --rm sandbox python -m mutation generate` | `sandbox` | gera 100 mutantes por problema; `--problem ID` (repetível), `--workers N` (padrão metade das CPUs); pula o que já está concluído e retoma sem perda se interrompido |
| `docker compose run --rm app python -m mutation report` | `app` | recalcula `manifests/mutation_report.json` a partir do que já foi gerado |
| `docker compose run --rm app python -m mutation package` | `app` | só na execução final: gera `data/mutants.zip`, o manifesto e o relatório; `--allow-partial` (só para teste) |
| `docker compose run --rm app python -m mutation verify` | `app` | confere o zip contra o manifesto; `--extracted data/mutants` confere também a pasta descompactada |
| `unzip data/mutants.zip -d data/` | (host) | descompacta os mutantes em `data/mutants/problems/` |

### Módulo `ai_clients` ([README](src/ai_clients/README.md))

Implementado para o modelo local: a execução completa gerou as 600 combinações com suíte, e o
pacote `data/slm_suites.zip` (com o manifesto e o relatório) está no repositório; para usá-lo, basta
descompactar e rodar o `verify`. A geração precisa de `OLLAMA_BASE_URL` e `OLLAMA_HARDWARE_LABEL` no `.env` (ver
`.env.example`) e de um servidor Ollama no ar (preparação no README do módulo).

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `docker compose run --rm app python -m ai_clients generate` | `app` | pede ao modelo local (Ollama) as entradas de teste e a solução Python de cada problema e cenário pendente e grava as respostas em `data/suites/slm/`, até 12 pedidos com solução (seed e temperatura de uma tabela fixa) e depois até 3 de predição (o modelo escreve as saídas); recusa com código `2` uma pasta com execução de versão anterior (mova-a antes); `--resume` (obrigatório depois da primeira execução), `--dry-run` (só lista os pedidos, sem Ollama e sem gravar), `--limit N`, `--problem ID`, `--scenario S`; se o Ollama não responde, repete a mesma chamada sem gastar tentativa até `OLLAMA_MAX_INFRA_RETRIES` vezes e para com código `3` (o `token repeat limit reached` do modelo, ao contrário, gasta a tentativa e segue para a próxima seed); sai com `4`, listando cada um com o comando `close`, se algum problema e cenário aguarda os autores; retoma sem perda se interrompido; vários `generate --resume` (um por máquina de Ollama, cada um com `-e OLLAMA_BASE_URL=...` e todos os problemas) rodam juntos, e o problema e cenário em uso por outro é pulado e contado (`skipped`), o que divide o trabalho entre as máquinas; o primeiro `generate` roda sozinho |
| `docker compose run --rm sandbox python -m ai_clients execute` | `sandbox` | roda, sem internet, a solução Python de cada resposta lida, sobre os testes públicos e as entradas geradas, e grava as saídas esperadas e o `suite.json` de cada problema e cenário que termina; exige o `generate` antes; `--dry-run`, `--limit N`, `--problem ID`, `--scenario S`; termina com `next: ...generate --resume`, com os mesmos `--problem`/`--scenario`, enquanto houver tentativa à espera de novo pedido ao modelo (alternar os dois até sumir); sai com `4` como o `generate`; retoma sem perda se interrompido; roda junto com `generate --resume`, mas só um `execute` por vez |
| `docker compose run --rm app python -m ai_clients close --problem ID --scenario S --reason "TEXTO"` | `app` | fecha à mão um problema e cenário que aguarda os autores (os 15 pedidos não deram suíte): grava o motivo e a data e o `suite.json` com `status: discarded_manual`; `--dry-run` só mostra o que seria gravado; recusa (`1`) se outro comando estiver rodando |
| `docker compose run --rm app python -m ai_clients change-template --template prediction --reason "TEXTO"` | `app` | depois de os autores editarem um texto-base no meio da execução: grava a troca e move para `data/suites/slm/superseded/` os pedidos feitos com o texto antigo, que o `generate --resume` refaz com o texto novo e as mesmas seeds (uma execução nunca mistura duas versões); `--dry-run` só lista; rodar de novo termina uma troca interrompida; recusa (`1`) se outro comando estiver rodando |
| `docker compose run --rm app python -m ai_clients report` | `app` | grava `manifests/slm_generation_report.json` (contagens e proporção de cada `status` de suíte por cenário, tamanho das suítes de cada `status`, falhas por motivo e tentativa, *tokens*, máquinas, seeds), lendo só `data/suites/slm/`; pode rodar no meio da execução |
| `docker compose run --rm app python -m ai_clients package` | `app` | gera `data/slm_suites.zip`, `manifests/slm_suites.manifest.json` e o relatório; recusa se algum problema e cenário não tem `suite.json` (inclusive os que aguardam os autores) ou se outro comando estiver rodando |
| `docker compose run --rm app python -m ai_clients verify` | `app` | confere o zip contra o manifesto; `--extracted data/suites/slm` confere também a pasta descompactada |
| `unzip data/slm_suites.zip -d data/` | (host) | descompacta as suítes em `data/suites/slm/` |

### Módulo `cli` ([README](src/cli/README.md))

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `docker compose run --rm app python -m cli check` | `app` | confere, pelas pastas de verdade, se dataset, mutantes e suítes do modelo local estão completos e 1:1 (200 problemas, 100 mutantes cada, 3 cenários cada, nada sobrando; suítes ainda em geração são só aviso); `--deep` confere também os hashes; `--only dataset` (ou `mutants`, ou `slm_suites`) confere só uma camada |

### Módulo `sandbox` ([README](src/sandbox/README.md))

O motor não tem comando próprio: é uma biblioteca usada pelo `dataset` e pelo `mutation` (e, no
futuro, pela avaliação). `docker compose run --rm sandbox pytest tests/sandbox` roda os testes dele,
e `python -m dataset selfcheck` (acima) confere a saúde do motor. Os comandos dos módulos ainda não
implementados (clientes dos modelos comerciais, avaliação, `metrics`) entram aqui quando existirem.

## Glossário

| Sigla | Significado |
|---|---|
| **AC** | código correto (Accepted); `AC_ref` é a solução de referência de um problema |
| **WA** | falha lógica real: submissão humana incorreta que responde errado (Wrong Answer) |
| **TLE / MLE / RE / CE** | tempo excedido, memória excedida, falha de execução, erro de compilação |
| **Mutante** | cópia do AC com uma alteração sintática (defeito artificial) |
| **TDF** | Taxa de Detecção de Falhas reais: % de WAs reprovados pela suíte gerada |
| **MS** | Escore de Mutação: mutantes mortos sobre mutantes válidos |
| **TFP** | Taxa de Falsos Positivos: % de problemas em que a suíte reprova o AC |
| **IIC** | Índice de Influência do Contexto (sinergia ou sobrecarga ao combinar requisito e código) |
| **Macrocategoria** | `matematica`, `estrutural_otimizacao` ou `logica_direta` (por prioridade de tags) |
| **SLM** | modelo de linguagem pequeno, executado localmente (Qwen2.5-Coder-14B) |

## Mapa da documentação

| Documento | Para que serve |
|---|---|
| [`docs/metodologia-referencia.md`](docs/metodologia-referencia.md) | desenho experimental **corrente**: critérios, decisões e dados medidos de cada módulo, com histórico datado; é a base para o texto do TCC |
| `src/<modulo>/README.md` | como usar cada módulo (propósito, execução, entradas, saídas, dependências, limitações) |
| [`docs/template-modulo.md`](docs/template-modulo.md) | formato padronizado do README de cada módulo |
| [`docs/verificacao-consistencia.md`](docs/verificacao-consistencia.md) | o que `python -m cli check` confere entre os artefatos e como estendê-lo |

## Regras de trabalho

Todo dado medido, critério ou decisão de desenho precisa estar refletido em
[`docs/metodologia-referencia.md`](docs/metodologia-referencia.md), nunca só no código. Código
gerado com apoio de IA é revisado por um dos autores antes de ser considerado pronto. A
sincronização da documentação é conferida por
`docker compose run --rm app python scripts/check_docs_sync.py`.
