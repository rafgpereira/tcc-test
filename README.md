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
> **Estado atual (2026-09-25)**: os módulos `dataset` (extração, validação e empacotamento do
> dataset) e `sandbox` (motor de execução isolada de C++, usado pelo `dataset` internamente) estão
> **implementados**. O dataset experimental já foi gerado, validado e empacotado de verdade — o
> zip (`data/dataset.zip`) e os manifestos de integridade já estão neste repositório; quem clona o
> projeto agora só precisa descompactar e conferir, não precisa gerar nada. O módulo de **geração
> de mutantes** (`mutation`) está **em implementação**: o comando `generate` já gera os 100 mutantes
> de cada problema (uma alteração por vez e, quando não basta, combinações de duas e três, ou a
> exclusão do problema com alerta), pode ser interrompido e retomado sem perda, e o módulo também
> tem o relatório (`report`) e o empacotamento verificável (`package`, `verify`). A geração dos 200
> problemas já foi executada de verdade (20.000 mutantes, nenhum problema excluído); o relatório e o
> pacote versionado ainda serão gerados (ver o
> [README do módulo](src/mutation/README.md)). Os demais módulos seguintes (chamadas aos modelos de
> IA, avaliação, métricas, orquestrador) ainda não têm especificação nem código; a seção "Módulos
> e estado" marca isso.

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
| `src/mutation/` | gera 100 mutantes por problema | seção 2 | **em implementação** ([spec](specs/002-mutant-generation/spec.md)): comandos `generate`, `report`, `package` e `verify` implementados; a execução final que gera o pacote versionado ainda não foi feita | [README](src/mutation/README.md) |
| `src/ai_clients/` | chamadas stateless aos 3 modelos | seção 3 | **sem spec** (pontos pendentes na metodologia, em especial o oráculo do SLM) | a criar |
| avaliação | injeta as suítes geradas e registra vereditos em CSV | seção 4 | **sem spec** | a criar |
| `src/metrics/` | TDF, MS, TFP, IIC | seção 5 | **sem spec** (IIC ainda não operacionalizado) | a criar |
| `src/cli/` | orquestrador do experimento | — | **sem spec** | a criar |

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
| `data/dataset.zip` | o dataset validado, compactado | **sim**, é a única exceção em `data/` |
| `manifests/` | manifesto de hashes e relatório final, para conferir a integridade do dataset | sim |

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
| `dataset` | para obter o dataset experimental (o caso mais comum: só descompactar e conferir) ou para gerá-lo/regenerá-lo do zero | [README do módulo](src/dataset/README.md), seção "Qual é o seu cenário?" |
| `sandbox` | não tem uso direto — é a biblioteca de execução isolada usada pelo `dataset` por baixo dos panos; só é operado diretamente para conferir a saúde do motor | [README do módulo](src/sandbox/README.md) |
| `mutation` | para gerar os mutantes de cada problema (em implementação: `generate`, `report`, `package` e `verify` prontos; falta a execução final) | [README do módulo](src/mutation/README.md) |
| `ai_clients`, avaliação, `metrics`, `cli` | ainda não implementados | sem README ainda |

## Reprodutibilidade

- Dependências fixadas em lockfile (`uv.lock`); imagem base fixada por digest; revisão do
  dataset de origem fixada; seed fixa (`42`).
- O dataset é distribuído como `data/dataset.zip` versionado, com o manifesto
  `manifests/dataset.manifest.json` (SHA-256 por arquivo) para verificar a identidade exata dos
  dados. Arquivos soltos do dataset e mutantes gerados durante o desenvolvimento nunca são
  versionados; o pacote de mutantes da **execução final** que sustenta os números publicados do
  experimento é uma exceção (Constitution, Princípio II, emenda 1.6.0), pelo mesmo motivo do
  dataset: o motor de execução tem instabilidade de margem já medida, então regenerar com a
  mesma seed não garante reproduzir exatamente o mesmo conjunto.
- Chamadas a modelos comerciais custam dinheiro: o pipeline nunca as dispara em lote sem
  confirmação explícita de quem executa.

## Referência de comandos

Lista única de **todos os comandos do projeto**, para não ser preciso procurá-los no código. Todos
rodam na pasta do repositório; o que cada `<serviço>` é está em "Docker em poucas palavras" (`app`
tem internet; `sandbox` não tem e é o único que compila e executa C++ de terceiros). O passo a
passo de cada comando está no README do módulo correspondente. A ajuda embutida da CLI lista o que
existe de fato: `docker compose run --rm app python -m dataset --help`.

### Ambiente, testes e qualidade (valem para todos os módulos)

| Comando | Serviço | O que faz |
|---|---|---|
| `docker compose build` | (nenhum) | constrói a imagem; repita depois de mudanças no `Dockerfile` ou no `uv.lock` |
| `docker compose run --rm sandbox pytest` | `sandbox` | todos os testes do projeto, inclusive os que compilam e executam C++ |
| `docker compose run --rm sandbox pytest tests/<pasta>` | `sandbox` | os testes de uma parte: `tests/dataset`, `tests/sandbox`, `tests/mutation` ou `tests/docs` |
| `docker compose run --rm app ruff check .` | `app` | análise estática (`--fix` corrige o que for automático) |
| `docker compose run --rm app black --check .` | `app` | confere a formatação; sem `--check` (`black .`) reformata os arquivos do repositório |
| `docker compose run --rm app python scripts/check_docs_sync.py` | `app` | verifica se a documentação está sincronizada (READMEs, links, metodologia) |

### Módulo `dataset` (passo a passo completo: [README](src/dataset/README.md))

| Comando | Serviço | O que faz |
|---|---|---|
| `docker compose run --rm app python -m dataset extract` | `app` | lê o dataset de origem e grava o pool de problemas elegíveis |
| `docker compose run --rm app python -m dataset report` | `app` | regenera o relatório legível a partir do que já foi processado |
| `docker compose run --rm sandbox python -m dataset selfcheck` | `sandbox` | confere a saúde do motor de execução com programas de veredito conhecido |
| `docker compose run --rm sandbox python -m dataset validate` | `sandbox` | executa cada problema no motor até reunir a amostra completa |
| `docker compose run --rm sandbox python -m dataset audit` | `sandbox` | reexecuta a amostra já validada e repara automaticamente o que divergir |
| `docker compose run --rm app python -m dataset package` | `app` | gera `data/dataset.zip` e o manifesto de integridade |
| `docker compose run --rm app python -m dataset verify` | `app` | confere o zip (e, opcionalmente, uma extração) contra o manifesto |
| `docker compose run --rm app python scripts/verify_dataset.py` | `app` | a mesma verificação, para quem só recebeu o zip (sem precisar do restante do projeto instalado) |
| `unzip data/dataset.zip -d data/` | (host) | descompacta o dataset recebido pelo Git |

### Módulo `sandbox` ([README](src/sandbox/README.md))

| Comando | Serviço | O que faz |
|---|---|---|
| `docker compose run --rm sandbox pytest tests/sandbox` | `sandbox` | testes do motor: juiz, compilador, isolamento, limites |
| `docker compose run --rm sandbox python -m dataset selfcheck` | `sandbox` | ver a tabela do módulo `dataset` (mesmo comando) |

O motor não tem comando próprio: é uma biblioteca usada pelo `dataset` e, no futuro, pela
avaliação.

### Módulo `mutation` (passo a passo completo: [README](src/mutation/README.md))

| Comando | Serviço | O que faz |
|---|---|---|
| `docker compose run --rm sandbox python -m mutation generate` | `sandbox` | gera até 100 mutantes por problema a partir do `AC_ref.cpp` (uma alteração por mutante e, quando não basta, duas ou três; exclui com alerta o problema que nem assim chega a 100); `--problem ID` restringe a um problema; `--workers N` processa N problemas ao mesmo tempo (padrão: metade das CPUs); pode ser interrompido e retomado sem perda |
| `docker compose run --rm app python -m mutation report` | `app` | recalcula `manifests/mutation_report.json` (funil de descartes, mutantes por ordem e por operador, alertas de exclusão) a partir do que já foi gerado |
| `docker compose run --rm app python -m mutation package` | `app` | só na execução final: gera `data/mutants.zip`, `manifests/mutants.manifest.json` e o relatório |
| `docker compose run --rm app python -m mutation verify` | `app` | confere o zip (e, com `--extracted data/mutants`, a pasta descompactada) contra o manifesto |
| `unzip data/mutants.zip -d data/` | (host) | descompacta os mutantes recebidos pelo Git em `data/mutants/problems/` |
| `docker compose run --rm sandbox pytest tests/mutation` | `sandbox` | testes do módulo, inclusive os que compilam e executam C++ |

### Módulos ainda não implementados

`ai_clients`, avaliação, `metrics` e `cli` ainda não têm código nem comandos; quando forem
implementados, cada um traz o seu README e as suas linhas nesta seção.

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
| [`docs/metodologia-referencia.md`](docs/metodologia-referencia.md) | desenho experimental **corrente**: critérios, decisões e dados medidos de cada módulo, com histórico datado; é a base para o texto do TCC |
| `src/<modulo>/README.md` | como usar cada módulo (propósito, execução, entradas, saídas, dependências, limitações) |
| [`docs/template-modulo.md`](docs/template-modulo.md) | formato padronizado do README de cada módulo |
| [`.specify/memory/constitution.md`](.specify/memory/constitution.md) | princípios do projeto (reprodutibilidade, isolamento, testes, documentação viva...) |
| [`specs/NNN-nome/`](specs/) | especificação técnica e histórico de decisões de cada módulo, para quem quer o detalhe de implementação |

## Regras de trabalho

Reprodutibilidade acima de tudo: todo dado medido, critério ou decisão de desenho precisa estar
refletido em [`docs/metodologia-referencia.md`](docs/metodologia-referencia.md), nunca só no
código. Código gerado com apoio de IA é sempre revisado por um dos autores antes de ser
considerado pronto. A sincronização da documentação é conferida por
`docker compose run --rm app python scripts/check_docs_sync.py`.
