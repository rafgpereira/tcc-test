# Geração de Casos de Teste com Modelos de Linguagem — Pipeline Experimental

Software experimental de um Trabalho de Conclusão de Curso (Engenharia de Software, UnB, TCC
de dupla) que avalia a eficácia de modelos de linguagem na geração automática de casos de
teste unitários em C++.

> **Este é o documento de visão geral do projeto** (Constitution, Princípio XI). Ele explica a
> arquitetura do experimento, como os módulos se conectam e como reproduzir o experimento do
> zero. É atualizado sempre que um módulo é adicionado ou o fluxo entre módulos muda.
>
> **Estado atual (2026-09-22)**: o "Guia de execução, do clone ao primeiro comando" (abaixo) cobre a
> preparação do ambiente para quem não conhece Docker. A fundação do projeto está pronta e verificada em contêiner
> (imagem `gcc:13.2.0` com Python 3.11 via `uv`, tipos e limites do motor, armazenamento
> determinístico, CLI base e o verificador de documentação). No módulo `dataset`, a extração
> (`extract`) foi **executada de verdade em 2026-09-20** (13.610 exemplos lidos, pool de 1.234
> problemas elegíveis) e o relatório (`report`) está implementado. O motor de execução (módulo
> `sandbox`) está implementado e passa em todos os testes no contêiner, inclusive isolamento e o
> `selfcheck`; a validação dos códigos no motor (`validate` e `audit`) está implementada; `validate`
> foi executado por completo em 2026-09-21 (200 problemas validados em 5 h 06 min) e `audit` em
> 2026-09-22, em 3 rodadas até convergir (decisão D18: 20 dos 200 problemas precisaram de reparo
> automático em alguma rodada; ver metodologia, seção 1.7); falta só uma auditoria de fechamento
> antes do `package`, que ainda não existe. A feature `001-dataset-extraction` tem spec, plano e tarefas
> prontos; o restante do experimento está descrito na metodologia, mas ainda não especificado. Por isso a seção "Executando os módulos" marca cada etapa
> com o seu estado. **A reprodução completa só será possível quando todas as etapas estiverem
> implementadas**; este documento será completado à medida que os módulos chegarem.

## O que o experimento responde

Três modelos (dois LLMs comerciais, **GPT-5.4-mini** e **Gemini 3.5 Flash**, e um SLM local,
**Qwen2.5-Coder-7B** via Ollama) geram testes unitários para problemas algorítmicos, sob três
cenários de contexto:

- **Caixa-preta**: só o enunciado.
- **Caixa-branca**: só o código da solução correta.
- **Híbrida**: enunciado e código.

Os testes gerados são executados, em ambiente isolado, contra códigos com falhas reais (submissões
incorretas humanas) e falhas artificiais (mutantes), e contra o código correto. Perguntas
centrais: qual estratégia de contexto detecta melhor falhas reais, qual é mais sensível a
defeitos sintéticos, qual gera mais falsos positivos (alucinações) e como combinar contexto
ajuda ou atrapalha. Detalhes: [`docs/metodologia-referencia.md`](docs/metodologia-referencia.md).

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
| `src/dataset/` | extrai, filtra, valida e empacota o dataset | seção 1 | em implementação ([`specs/001-dataset-extraction/`](specs/001-dataset-extraction/)): `extract` executado de verdade em 2026-09-20 (pool de 1.234 problemas) e `report` implementados; validação, motor e empacotamento ainda não | [README](src/dataset/README.md) |
| `src/sandbox/` | motor de execução isolada de C++ | seções 1.4 e 4 | implementado (construído na feature 001): motor (compilação, execução isolada, veredito) e `selfcheck`, testados no contêiner e com os comandos carimbados em 2026-09-21 | [README](src/sandbox/README.md) |
| `src/mutation/` | gera 100 mutantes por problema | seção 2 | **sem spec** | a criar |
| `src/ai_clients/` | chamadas stateless aos 3 modelos | seção 3 | **sem spec** (pontos pendentes na metodologia, em especial o oráculo do SLM) | a criar |
| avaliação | injeta as suítes geradas e registra vereditos em CSV | seção 4 | **sem spec** | a criar |
| `src/metrics/` | TDF, MS, TFP, IIC | seção 5 | **sem spec** (IIC ainda não operacionalizado) | a criar |
| `src/cli/` | orquestrador do experimento | — | **sem spec** | a criar |

O formato dos READMEs de módulo é o de [`docs/template-modulo.md`](docs/template-modulo.md).

## Como o dataset circula entre os autores

**Ideia central**: o dataset é **gerado uma única vez**, por um dos autores, e depois **distribuído
pelo Git** como um arquivo compactado (`data/dataset.zip`) mais um manifesto de hashes
(`manifests/dataset.manifest.json`). Quem recebe o zip **não roda extração nem validação**: só
descompacta e confere. Gerar de novo não é necessário nem recomendado, porque a validação executa
código e o resultado pode variar com o ambiente; a reexecução completa existe para retomada e
auditoria, não para redistribuição. Em um clone novo, você só executa o que está em "Quem recebe o
dataset", mais abaixo.

### O ciclo de geração (quem gera, uma vez)

| Fase | Comando (`docker compose run --rm <serviço> python -m dataset <comando>`) | O que acontece | O que fica em disco | Estado |
|---|---|---|---|---|
| 1 | `extract` (serviço `app`, com internet) | lê **todos** os 13.610 exemplos do `code_contests` em streaming, descarta na hora os que não servem e grava só os 1.234 elegíveis (medido na extração real de 2026-09-20), cada um com enunciado, testes, códigos corretos e **todas as submissões incorretas em C++ como candidatas** a WA. **Não executa nenhum código** | `data/work/staging/` | disponível (ainda sem execução real) |
| 2 | `validate` (serviço `sandbox`) | executa, no motor isolado, o código correto e as candidatas a WA de cada problema, na ordem do pool, até reunir 200 problemas completos com exatamente 100 WAs cada | `data/work/problems/` | **executado em 2026-09-21**: 200 de 200 em 5 h 06 min (264 problemas processados); o relatório é regerado ao fim |
| 3 | `audit` (serviço `sandbox`) | conferência, repetida até convergir, antes do `package`: reexecuta no motor o código correto e as 100 WA de cada problema completo, a partir dos arquivos gravados, e compara com o registrado; uma WA que diverge é **reparada automaticamente**, substituída pelo próximo candidato não tentado com confirmação reforçada (decisão D18) | — | **executado em 3 rodadas em 2026-09-21/22** até os autores aceitarem o estado (20 de 200 problemas tocados); uma última rodada de fechamento roda antes do `package`; detalhes no README do módulo |
| 4 | `package` (serviço `app`) | copia **só os problemas completos** para um zip determinístico e gera o manifesto e o relatório final | `data/dataset.zip`, `manifests/` | planejado |
| 5 | `verify` (serviço `app`) | confere o zip contra o manifesto | — | planejado |
| 6 | `git add data/dataset.zip manifests/` e commit/push | é o único jeito de o dataset chegar ao outro autor; nada mais de `data/` é versionado | — | planejado |

Cada fase é um comando **separado e manual**: o `validate` não gera o zip sozinho. O zip só existe
depois que alguém roda `package` (fase 4) com a meta de 200 atingida.

### Como os 200 problemas são escolhidos

O pool elegível (1.234 problemas, dos três splits juntos) foi embaralhado **uma única vez** com a
seed 42 e gravado nessa ordem em `data/work/staging/pool.json`. A fase 2 (`validate`) percorre essa
ordem e a amostra são os **200 primeiros problemas que completam a validação** (código correto
aprovado e exatamente 100 WA). Os que não completam são pulados e usa-se a próxima posição da ordem.
Não há cota por macrocategoria nem prioridade por split ou dificuldade (a distribuição da amostra é
consequência do sorteio e das exclusões, e o relatório a informa). Os problemas cujo código correto
falha no motor ficam em `pending_triage`: a inspeção manual deles é **adiada** e só ocorre se a meta
de 200 não for atingida com os demais. Detalhes: metodologia, seção 1.4, e spec, decisões D5, D11 e
D17.

### O que sobra em `data/work/`

`data/work/` é o espaço de trabalho de **quem gera**: fica só na máquina dele, com permissão `0700`,
e nunca vai para o Git. **Nenhum comando o apaga automaticamente** (a spec não prevê limpeza).
Nela ficam os 1.234 problemas elegíveis extraídos, inclusive os que a validação não chegou a
processar (ela para ao reunir 200 completos), e os problemas descartados ou em triagem. Os que não
entram no zip continuam ali, sem uso. Apagar `data/work/` é uma decisão manual e só faz sentido
depois do `package` e do commit; quem apaga aceita refazer extração e validação (horas) se precisar
retomar ou auditar. O espaço em disco real ocupado será medido na primeira extração.

### Quem recebe o dataset (o outro autor, ou você em outra máquina)

Uma vez por máquina, faça os Passos 1 a 5 do guia abaixo. Depois, sempre que o zip mudar no
repositório (`git pull` trouxe um `data/dataset.zip` ou um manifesto novo):

```bash
rm -rf data/dataset                 # só se já existir uma versão anterior
unzip data/dataset.zip -d data/
docker compose run --rm app python scripts/verify_dataset.py --extracted data/dataset
```

Esperado: a última linha da verificação é `OK`. O `unzip` cria `data/dataset/problems/<id>/`, com
`enunciado.md`, `AC_ref.cpp`, `WA_1.cpp` a `WA_100.cpp`, `testes.json`, `metadata.json` e
`validacao.json` de cada problema. Estes três comandos ainda **não existem por inteiro**
(`scripts/verify_dataset.py` é planejado) e não foram testados; a tabela "Executando os módulos"
registra o estado.

### Como isso funciona com o Docker de cada autor

- **Cada autor constrói a sua própria imagem** (`docker compose build`); as duas ficam idênticas
  porque a imagem base, o Python e as bibliotecas têm versão fixada. Não há imagem compartilhada.
- **O dataset não vai dentro da imagem.** A pasta `data/` do seu computador é montada nos contêineres
  como `/app/data`. Por isso, depois do `unzip` no seu computador, os contêineres enxergam
  `data/dataset/` imediatamente, sem reconstruir nada, e os módulos futuros a leem de lá.
- **O `.env` é pessoal** (cada um usa o seu `HOST_UID`/`HOST_GID`) e nunca vai para o Git.
- **O que é sempre local**: `.env`, `data/work/`, `data/dataset/` (descompactado). **O que vai pelo
  Git**: `data/dataset.zip` e `manifests/`, além do código e da documentação.

## Guia de execução, do clone ao primeiro comando

Este guia parte do zero e **não pressupõe conhecimento de Docker**. Ele cobre a preparação do
ambiente, que se faz **uma vez por máquina**. Depois disso, cada módulo tem o seu próprio passo a
passo na seção "(b) Como executar" do seu README (links na tabela "Módulos e estado" acima); esses
passo a passo crescem à medida que os módulos são implementados. O projeto foi desenvolvido e
testado em **Linux**; macOS e Windows (WSL2) não foram verificados. Nenhum código C++ de terceiros
é compilado ou executado fora do Docker (Constitution, Princípio V).

### O que você precisa ter instalado

| Programa | Para quê | Como conferir |
|---|---|---|
| Git | baixar o projeto | `git --version` |
| Docker Engine com o plugin Compose v2 | rodar tudo (ver "Docker em poucas palavras") | `docker --version` e `docker compose version` |

Para instalar o Docker, siga a página da sua distribuição em <https://docs.docker.com/engine/install/>,
incluindo os "Post-installation steps for Linux" (eles permitem usar `docker` sem `sudo`). Você
também precisa de internet (para baixar a imagem base e o dataset) e de espaço livre em disco: a
imagem base do GCC tem na ordem de 1 GB; a extração real de 2026-09-20 ocupou cerca de 104 MB em
`data/work/`.

Teste se o Docker está pronto: `docker run --rm hello-world`. Se aparecer `permission denied` com
`/var/run/docker.sock`, o seu usuário não está no grupo `docker`: rode
`sudo usermod -aG docker "$USER"`, saia da sessão do sistema e entre de novo.

### Docker em poucas palavras

- **Imagem**: um "computador congelado" com tudo instalado (compilador GCC 13.2.0, Python 3.11 e as
  bibliotecas do projeto). É igual para todo mundo, e é por isso que o experimento é reprodutível.
  Você a constrói uma vez (Passo 4).
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
| `app` | sim | baixar o dataset, gerar relatórios, empacotar e verificar dados, lint e formatação |
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
| `HF_TOKEN` | chave opcional do Hugging Face (site de onde vem o dataset) | pode ficar vazia: o dataset é público, o token só aumenta o limite de requisições |

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

Baixa a imagem base do GCC e instala o Python 3.11.16 e as bibliotecas fixadas em `uv.lock`. A
primeira vez leva alguns minutos e depende da sua conexão; as seguintes são rápidas. Só é preciso
repetir se o `Dockerfile` ou o `uv.lock` mudarem: o código do projeto é lido diretamente da sua
pasta (volumes de `docker-compose.override.yml`), então editar código não exige reconstruir.

### Passo 5: conferir que o ambiente funciona

```bash
docker compose run --rm sandbox pytest
```

Roda a suíte de testes do projeto. Esperado: a última linha diz `passed` (com o número de testes) e
não menciona `failed`. Este comando usa o serviço `sandbox` porque parte dos testes compila e
executa C++, o que só é permitido dentro dele.

### Onde ficam os arquivos

| Onde | O que é | No Git? |
|---|---|---|
| `.env` | suas configurações locais | não, nunca |
| `data/work/` | dados de trabalho da extração e da validação, com permissão `0700` (só o seu usuário lê, para o código de terceiros não o alcançar) | não |
| `data/dataset.zip` | o dataset validado, compactado (existirá quando a feature 001 terminar) | sim, é a única exceção em `data/` |
| `manifests/` | manifesto de hashes e relatório final da extração | sim |

### Problemas comuns

| O que aparece | Causa provável | O que fazer |
|---|---|---|
| `permission denied` com `docker.sock` | seu usuário não está no grupo `docker` | `sudo usermod -aG docker "$USER"` e reinicie a sessão do sistema |
| `'compose' is not a docker command` | falta o plugin Compose v2 | instale o `docker-compose-plugin` (página de instalação do Docker acima) |
| `no configuration file provided: not found` | você não está na pasta do repositório | `cd tcc-testgen-pipeline` |
| `PermissionError` ao gravar em `data/`, ou arquivos em `data/` que você não consegue apagar | `data/` foi criada por `root` (Passo 3 pulado) | `sudo chown -R "$(id -u):$(id -g)" data` |
| um comando termina com falha de rede (código de saída `3`) | queda de conexão | rode o **mesmo comando** de novo: a extração retoma de onde parou |
| você apertou Ctrl+C no meio de um comando | interrupção pedida por você | rode o mesmo comando de novo; é seguro |

Para ver o código de saída do último comando: `echo $?` (`0` é sucesso).

### Executando os módulos

| Etapa | O que fazer | Estado |
|---|---|---|
| 0 e 1. Preparar o ambiente | Passos 1 a 5 deste guia | disponível |
| 2. Obter o dataset (quem recebe) | **sem rodar a extração**: `unzip data/dataset.zip -d data/` e depois `docker compose run --rm app python scripts/verify_dataset.py --extracted data/dataset` (detalhes e o caso de atualização em "Como o dataset circula entre os autores") | planejado (o zip só existe depois da feature 001) |
| 2b. Ou gerar o dataset do zero (quem gera, uma vez) | [passo a passo do módulo `dataset`](src/dataset/README.md): `docker compose run --rm app python -m dataset extract` e `docker compose run --rm app python -m dataset report` estão **disponíveis** (`extract` executado de verdade em 2026-09-20); `validate` e `audit` estão implementados e testados (`validate` foi executado por completo em 2026-09-21, 200 de 200; o `audit` ainda não rodou); `package` é planejado ([contrato dos comandos](specs/001-dataset-extraction/contracts/cli.md), [roteiro de aceite](specs/001-dataset-extraction/quickstart.md)) | em implementação (feature 001) |
| Verificar o motor de execução | `docker compose run --rm sandbox python -m dataset selfcheck` (passo a passo em [`src/sandbox/README.md`](src/sandbox/README.md)) | disponível (verificado em 2026-09-21) |
| 3. Gerar mutantes | — | não especificado |
| 4. Gerar suítes com os modelos | — | não especificado (exige chaves de API em `.env`; ver `.env.example`) |
| 5. Avaliar as suítes | — | não especificado |
| 6. Calcular as métricas | — | não especificado |
| 7. Executar tudo com um comando | — | não especificado (`src/cli/`) |

Cada linha "não especificado" ou "planejado" MUST virar comandos exatos, testados, quando o
módulo correspondente for concluído; uma feature só é concluída com isso feito
(Constitution, Princípio XI). O passo a passo de cada módulo, escrito para quem não conhece
Docker, MUST estar na seção "(b) Como executar" do README do módulo.

### Reprodutibilidade

- Dependências fixadas em lockfile (`uv.lock`); imagem base fixada por digest; revisão do
  dataset de origem fixada; seed fixa (`42`).
- O dataset é distribuído como `data/dataset.zip` versionado, com o manifesto
  `manifests/dataset.manifest.json` (SHA-256 por arquivo) para verificar a identidade exata dos
  dados. Arquivos soltos do dataset e mutantes nunca são versionados.
- Chamadas a modelos comerciais custam dinheiro: o pipeline nunca as dispara em lote sem
  confirmação explícita de quem executa (Constitution, Princípio VIII).

## Referência de comandos

Lista única de **todos os comandos do projeto**, para não ser preciso procurá-los no código. Todos
rodam na pasta do repositório; o que cada `<serviço>` é está em "Docker em poucas palavras" (`app`
tem internet; `sandbox` não tem e é o único que compila e executa C++ de terceiros). O passo a passo
de cada comando (o que aparece na tela, como conferir, o que fazer se falhar) está no README do
módulo, na coluna "Detalhes". A ajuda embutida da CLI lista o que existe de fato:
`docker compose run --rm app python -m dataset --help`. **Todo comando novo entra aqui no mesmo
ciclo em que é criado** (o `scripts/check_docs_sync.py` confere que cada subcomando da CLI aparece
nesta seção).

### Ambiente, testes e qualidade (valem para todos os módulos)

| Comando | Serviço | O que faz | Estado | Detalhes |
|---|---|---|---|---|
| `docker compose build` | (nenhum) | constrói a imagem (GCC 13.2.0, Python 3.11, dependências e o lançador `sandbox-launch`); repita depois de mudanças no `Dockerfile` ou no `uv.lock` | disponível | "Guia de execução", Passo 4 |
| `docker compose run --rm sandbox pytest` | `sandbox` | todos os testes do projeto, inclusive os de integração que compilam e executam C++ | disponível | Passo 5 do guia |
| `docker compose run --rm sandbox pytest tests/<pasta>` | `sandbox` | os testes de uma parte: `tests/dataset`, `tests/sandbox` ou `tests/docs` | disponível | README de cada módulo |
| `docker compose run --rm app ruff check .` | `app` | análise estática (`--fix` corrige o que for automático) | disponível | `CLAUDE.md` |
| `docker compose run --rm app black --check .` | `app` | confere a formatação; sem `--check` (`black .`) reformata os arquivos do repositório | disponível | `CLAUDE.md` |
| `docker compose run --rm app python scripts/check_docs_sync.py` | `app` | verifica se a documentação está sincronizada (READMEs dos módulos, links, estado deste README, metodologia); opções: `--module src/<módulo>` (só um módulo), `--only C1,C2,...` (só algumas checagens), `--closing` (rigor de fechamento da feature) | disponível | [`docs/template-modulo.md`](docs/template-modulo.md) |

### Módulo `dataset` ([README](src/dataset/README.md); contrato completo em [`cli.md`](specs/001-dataset-extraction/contracts/cli.md))

| Comando | Serviço | O que faz | Estado |
|---|---|---|---|
| `docker compose run --rm app python -m dataset extract` | `app` | lê o `code_contests` em streaming e grava o pool de problemas elegíveis em `data/work/staging/` (opções `--seed`, `--splits`, `--limit-rows`) | disponível (executado em 2026-09-20) |
| `docker compose run --rm app python -m dataset report` | `app` | regenera o relatório em `data/work/reports/` a partir do pool e dos problemas validados | disponível |
| `docker compose run --rm sandbox python -m dataset selfcheck` | `sandbox` | confere o motor de execução com 9 programas de veredito conhecido | disponível (README do `sandbox`) |
| `docker compose run --rm sandbox python -m dataset validate` (roteiro completo em [`src/dataset/README.md`](src/dataset/README.md), seção "Roteiro da execução completa") | `sandbox` | roda o `selfcheck` e depois executa o código correto e as candidatas a WA de cada problema no motor, até reunir a meta de problemas completos; grava as pastas em `data/work/problems/` (opções `--target`, `--workers`, `--problem`; piloto: `--target 10`) | **executado em 2026-09-21** (200 de 200 em 5 h 06 min); comandos carimbados no README do módulo |
| `docker compose run --rm sandbox python -m dataset audit` | `sandbox` | reexecuta o motor sobre os problemas completos e confere com `validacao.json` (opção `--problem`, repetível) | implementado e testado; ainda não executado sobre o dataset real |
| `package` | `app` | gera `data/dataset.zip` e os manifestos | planejado (feature 001) |
| `verify` e `scripts/verify_dataset.py` | `app` | confere o zip e a pasta descompactada contra o manifesto | planejado (feature 001) |
| `unzip data/dataset.zip -d data/` | (host) | descompacta o dataset recebido pelo Git, em `data/dataset/` (quem recebe o dataset) | planejado (o zip só existe depois da feature 001) |

Os comandos planejados são escritos só com o nome do subcomando porque ainda não existem; ganham a
forma completa (`docker compose run --rm <serviço> python -m dataset <comando>`) quando forem
implementados.

### Módulo `sandbox` ([README](src/sandbox/README.md))

| Comando | Serviço | O que faz | Estado |
|---|---|---|---|
| `docker compose run --rm sandbox pytest tests/sandbox` | `sandbox` | testes do motor: juiz, compilador, isolamento, fork bomb, limites e `selfcheck` | disponível |
| `docker compose run --rm sandbox python -m dataset selfcheck` | `sandbox` | ver a tabela do módulo `dataset` (mesmo comando) | disponível |

O motor não tem comando próprio: é uma biblioteca usada pelo `dataset` e, no futuro, pela avaliação.

### Módulos ainda não especificados

`mutation`, `ai_clients`, avaliação, `metrics` e `cli` não têm comandos; quando forem
implementados cada um traz o seu README e as suas linhas nesta seção.

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
| **SLM** | modelo de linguagem pequeno, executado localmente (Qwen2.5-Coder-7B) |

## Mapa da documentação

| Documento | Para que serve |
|---|---|
| [`.specify/memory/constitution.md`](.specify/memory/constitution.md) | princípios do projeto (reprodutibilidade, isolamento, testes, documentação viva...) |
| [`docs/metodologia-referencia.md`](docs/metodologia-referencia.md) | desenho experimental **corrente**; base para atualizar o texto do TCC; tem histórico de atualizações datado |
| [`docs/template-modulo.md`](docs/template-modulo.md) | formato padronizado do README de cada módulo |
| `src/<modulo>/README.md` | como usar cada módulo (propósito, execução, entradas, saídas, dependências, limitações) |
| [`specs/NNN-nome/`](specs/) | especificação, plano, contratos e roteiro de aceite de cada feature (spec-kit) |
| [`CLAUDE.md`](CLAUDE.md) | contexto rápido para sessões do Claude Code neste repositório |

## Regras de trabalho

Ciclo de cada módulo (spec-kit): `specify → clarify → plan → tasks → implement → converge`.
Toda informação nova (dado medido, divergência, decisão) MUST ser propagada, no mesmo ciclo de
trabalho, para os artefatos da feature **e** para a metodologia; todo código gerado com apoio de
IA é revisado por um dos autores antes de ir para a branch principal. Detalhes na constitution.
A conformidade da documentação é verificada por
`docker compose run --rm app python scripts/check_docs_sync.py` (Princípio XI).
