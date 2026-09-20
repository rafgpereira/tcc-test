# Implementation Plan: Extração, Validação e Persistência do Dataset Experimental

**Branch**: `001-dataset-extraction` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-dataset-extraction/spec.md`

## Summary

O módulo lê o `deepmind/code_contests` em streaming (revisão fixada), filtra e classifica os
problemas elegíveis, valida cada código C++ (AC e submissões incorretas) num **motor de
execução único**, persiste 200 problemas completos (cada um com exatamente 100 WAs validados)
e empacota o resultado em `data/dataset.zip` com manifesto SHA-256.

Abordagem técnica (detalhes em [research.md](./research.md)):

- **Motor de execução** em `src/sandbox/`: compila com as flags do juiz (sem `-Wl,--stack`),
  cascata de padrões, executa como um uid sem privilégios por trabalhador, com `setrlimit`
  (pilha 256 MiB, memória e CPU do problema), sem rede, e atribui o veredito. É construído e
  verificado aqui e reutilizado sem alteração pela avaliação futura (D7).
- **Validação** em `src/dataset/validation/`: escolhe e executa o `AC_ref` no motor (falha de AC
  ⇒ interrupção do problema e triagem, D8), depois valida candidatas a WA em paralelo com
  consumo em ordem determinística, até 100 retidas.
- **Idempotência**: cada problema é construído em `building/` e movido atomicamente; estado no
  `validacao.json`; retomada preserva o que está completo.
- **Fundação compartilhada** do projeto inteiro (seção abaixo): imagem `gcc:13.2.0` + Python
  3.11 via `uv`, layout `src/<modulo>/`, Compose com dois serviços (com rede / sem rede).

## Technical Context

**Language/Version**: Python 3.11.16 (fixado por `.python-version`, instalado pelo `uv`); C++
compilado com GCC 13.2.0 (`gnu++20 → gnu++17 → gnu++14 → gnu++11`).

**Primary Dependencies**: `datasets` 5.0.1 (Hugging Face, streaming), `pydantic` 2.x (schemas),
biblioteca padrão (`hashlib`, `subprocess`, `resource`, `zipfile`, `concurrent.futures`,
`argparse`). Dev: `pytest`, `ruff`, `black`. Versões exatas fixadas no `uv.lock`.

**Storage**: arquivos. Dataset final em `data/dataset.zip` (versionado) com manifesto em
`manifests/`; trabalho em `data/work/` (ignorado pelo Git).

**Testing**: `pytest` no serviço `sandbox`; suíte própria para motor, classificação, persistência
e integridade (Princípio VI); programas de veredito conhecido embarcados em
`src/sandbox/selfcheck/` (também usados como portão de `validate`).

**Target Platform**: Linux, dentro de contêiner Docker (imagem `gcc:13.2.0`, Debian 12). Host:
qualquer um com Docker Compose v2. Nenhum código C++ de terceiros roda no host.

**Project Type**: pipeline em Python (CLI + bibliotecas por módulo), estrutura `src/<modulo>/`.

**Performance Goals**: validar ~350 problemas processados (para chegar a 200 completos) em
~5 h com 8 trabalhadores, com paralelismo por candidata (R11); extração em uma única passagem
pelo dataset de origem (≥ 30 min: a passagem só com colunas leves levou ~28 min, R1).

**Constraints**: nenhum limite de tempo/memória de problema é constante no código; sem rede
durante a execução de código de terceiros; mesmos resultados em duas execuções (exceto
`extraction_timestamp`); `data/` fora do Git salvo `data/dataset.zip`.

**Scale/Scope**: 200 problemas completos a partir de um pool de 1.279 elegíveis, já sem os 9 de E/S por arquivo (R1); ~10^5
compilações; zip estimado em ~10 MB (R15).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.2.1.

| Princípio | Verificação | Resultado |
|---|---|---|
| I. Metodologia mutável, divergências registradas | Divergências desta fase confirmadas e registradas na spec (D6–D11) e na metodologia (seções 1.1, 1.2, 1.4, 1.6, 7) | PASS |
| II. Reprodutibilidade | Seeds documentadas (R12), revisão do HF fixada (R1), `uv.lock`, imagem por digest, Docker, zip determinístico + manifesto, dados soltos nunca versionados (R14) | PASS |
| III. Sem estado nas chamadas de IA | Este módulo não chama IA | N/A |
| IV. Contratos explícitos e versionados | Pydantic com `schema_version` para `testes/metadata/validacao/manifesto/pool/relatório` ([data-model.md](./data-model.md)) | PASS |
| V. Execução isolada e segura | Uid dedicado sem capabilities, rlimits, sem rede, raiz somente leitura, `data/work/` com permissão `0700` (D15), limites vindos dos metadados (R5–R8) | PASS |
| VI. O pipeline testa a si próprio | Motor, classificação, persistência, triagem, zip/manifesto e verificação têm testes; portão `selfcheck` | PASS |
| VII. Idempotência e retomada | Construção atômica + estado no `validacao.json` + descarte de `building/` (R13) | PASS |
| VIII. Observabilidade de custo de IA | Sem chamadas pagas; o streaming do HF é gratuito. Logs de progresso e tempo por etapa | N/A |
| IX. Simplicidade | Uma imagem, `argparse`, sem `common/` nem pacotes vazios, sem abstração para outros datasets/linguagens; complexidade justificada em "Complexity Tracking" | PASS |
| X. Revisão humana | Processo, não código; registrado no fluxo (PR revisado por um dos autores) | PASS |
| XI. Documentação viva, sincronizada e padronizada | Dados medidos e decisões propagados para spec, plano, pesquisa e metodologia (auditoria de 2026-09-19); READMEs de `dataset` e `sandbox` pelo template, README da raiz e sincronização da metodologia como tarefas obrigatórias (seção "Documentação") | PASS |

Convenções técnicas: Python 3.11+, `pytest`, `ruff`/`black`, nomes de código em inglês,
GCC 13.2+, segredos só em `.env` (com `.env.example`), `data/` em `.gitignore` com a exceção
do zip, manifesto e comando de verificação. Todas atendidas; os segredos seguem a convenção da
v1.2.1 (`.env` injetado por `env_file` do compose, sem `python-dotenv`).

**Resultado do portão inicial**: PASS. Sem violação a justificar (a tabela de Complexity
Tracking registra decisões de custo, não violações).

## Fundação compartilhada do projeto (não só deste módulo)

Esta seção documenta a decisão de base, pedida explicitamente: a infraestrutura abaixo serve a
**todos** os módulos (mutação, orquestração de IA, sandbox de avaliação, métricas, CLI), que
serão adicionados depois no mesmo ambiente **sem refazer** nenhuma destas peças. Nada
específico desses módulos é construído agora (Princípio IX).

### Layout do repositório

```text
.
├── README.md                 # visão geral do projeto (Princípio XI)
├── docs/                     # metodologia-referencia.md, template-modulo.md
├── pyproject.toml            # uv, [tool.uv] package = false; ruff, black, pytest
├── uv.lock                   # dependências pinadas (Princípio II)
├── .python-version           # 3.11.16
├── Dockerfile                # imagem única do projeto
├── docker-compose.yml        # serviços `app` (com rede) e `sandbox` (sem rede)
├── docker-compose.override.yml  # desenvolvimento: monta o working tree (sem `.env` nem `.git`)
├── .dockerignore
├── .gitignore                # data/* e !data/dataset.zip; .env; caches
├── .env.example              # HF_TOKEN opcional, HOST_UID/HOST_GID (segredos só em .env)
├── manifests/                # versionado: manifesto de hashes e relatório final (com .gitkeep)
├── scripts/                  # (com .gitkeep até haver scripts)
│   ├── verify_dataset.py     # verificação de integridade pós-clonagem
│   └── check_docs_sync.py    # conformidade da documentação (Princípio XI)
├── src/
│   ├── dataset/              # ESTE módulo (+ README.md pelo template)
│   └── sandbox/              # motor de execução (compartilhado; D7) (+ README.md)
│   #   mutation/ ai_clients/ metrics/ cli/  → criados pelas suas features, não agora
├── tests/
│   ├── dataset/              # espelha src/dataset/
│   ├── sandbox/              # espelha src/sandbox/
│   └── docs/                 # testes do script de sincronização
└── data/                     # ignorado pelo Git, exceto data/dataset.zip
```

Regra para adicionar um módulo depois (sem refazer a fundação): criar `src/<modulo>/` com
`__init__.py` e `tests/<modulo>/`; se precisar de dependência nova, `uv add <pacote>` e
reconstruir a imagem (o `uv.lock` muda, a imagem base e o layout não). Não é preciso editar o
`pyproject.toml` para o pacote ser importável (`package = false`, `PYTHONPATH=/app/src`).
Módulos que precisam executar código C++ importam `sandbox`; módulos de IA não precisam de
capabilities e rodam no serviço `app`.

### Dockerfile (desenho)

```dockerfile
FROM gcc:13.2.0@sha256:15c73bc59ae88b3fd563ef2ec4a8743a8848a9f74362b6d116c4543c4844b6e0   # GCC exato; Debian 12
ENV LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv   # versão fixada (digest na implementação)
WORKDIR /app
COPY .python-version pyproject.toml uv.lock ./
RUN uv sync --frozen                     # CPython 3.11.16 + dependências (incluindo grupo dev)
RUN useradd --uid 1000 --create-home pipeline
COPY src ./src
COPY scripts ./scripts
COPY tests ./tests
COPY .gitignore ./.gitignore              # o teste da regra do .gitignore roda no contêiner
```

Notas: (1) `uv` só é usado no build; em execução, `python` do `/opt/venv`; (2) não há segredos
na imagem (`.dockerignore` exclui `.env` e `data/`); (3) os uids do sandbox (`10000 + slot`)
não precisam de entradas em `/etc/passwd`.

### `pyproject.toml` (desenho)

```toml
[project]
name = "tcc-testgen-pipeline"
requires-python = ">=3.11,<3.12"
dependencies = ["datasets==5.0.1", "pydantic>=2,<3"]

[dependency-groups]
dev = ["pytest", "ruff", "black"]

[tool.uv]
package = false

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "--import-mode=importlib -p no:cacheprovider"
markers = ["integration: compila e executa C++ (serviço sandbox)"]

[tool.ruff]
line-length = 100
[tool.black]
line-length = 100
```

### `docker-compose.yml` (desenho)

```yaml
services:
  app:                       # extração, empacotamento, verificação (com rede)
    build: .
    user: "${HOST_UID:-1000}:${HOST_GID:-1000}"   # o mesmo usuário do host nas duas máquinas dos autores
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    env_file: [{ path: .env, required: false }]   # forma longa exige lista (validado com `docker compose config`)
    environment: { HF_HOME: /tmp/hf }     # raiz somente leitura: cache do Hugging Face no tmpfs
    volumes: ["./data:/app/data", "./manifests:/app/manifests"]
    tmpfs: ["/tmp:size=2g"]

  sandbox:                   # executa código de terceiros: SEM rede
    build: .
    user: "0:0"              # necessário só para soltar privilégios por execução (setuid)
    network_mode: none
    read_only: true
    cap_drop: [ALL]
    cap_add: [CHOWN, DAC_OVERRIDE, SETUID, SETGID, KILL]
    security_opt: ["no-new-privileges:true"]
    pids_limit: 2048
    environment: { HOST_UID: "${HOST_UID:-1000}", HOST_GID: "${HOST_GID:-1000}" }
    volumes: ["./data:/app/data", "./manifests:/app/manifests"]
    tmpfs: ["/sandbox:exec,mode=0755,size=2g", "/tmp:size=512m"]
```

O `tmpfs` de `/sandbox` precisa da opção `exec`: o padrão do Docker é `noexec`, o que impediria
executar o binário compilado. Os comandos de `docker compose run --rm app|sandbox ...` do
`CLAUDE.md` passam a valer com estes nomes de serviço (o `CLAUDE.md` cita `app` para o `pytest`;
aqui ele roda em `sandbox`, ver divergências).

### `docker-compose.override.yml` (desenho)

Carregado automaticamente pelo `docker compose`; serve ao ciclo de desenvolvimento (testar e
formatar o working tree sem reconstruir a imagem). Sem ele, `black .` rodaria sobre a cópia
dentro da imagem e não alteraria o repositório.

```yaml
services:
  app: &dev
    environment: { RUFF_CACHE_DIR: /tmp/.ruff_cache, BLACK_CACHE_DIR: /tmp/.black_cache }
    volumes:
      - ./src:/app/src
      - ./tests:/app/tests
      - ./scripts:/app/scripts
      - ./docs:/app/docs
      - ./specs:/app/specs
      - ./README.md:/app/README.md
      - ./pyproject.toml:/app/pyproject.toml
      - ./.gitignore:/app/.gitignore:ro
      - ./CLAUDE.md:/app/CLAUDE.md:ro
      - ./.specify:/app/.specify:ro
  sandbox: *dev
```

Montagens **explícitas**: `.env` e `.git` NÃO são montados. `CLAUDE.md` e `.specify/` entram só
para leitura, porque o `README.md` da raiz os cita e o `check_docs_sync.py` (checagem C3) falha em
link quebrado (descoberto na rodada em contêiner de 2026-09-20). No serviço `sandbox` o código de
terceiros roda no mesmo contêiner; com `.env` montado ele poderia ler o token e imprimi-lo, e a
saída acabaria em `validacao.json`, que é versionado. Mudança de dependência (`uv.lock`) continua
exigindo `docker compose build`. Os caches de `ruff`, `black` e `pytest` ficam fora do working
tree (`/tmp` no tmpfs; `-p no:cacheprovider`), para não gerar arquivos de root no repositório.

## Divergência de plataforma: `-Wl,--stack=268435456`

Não é escolha arbitrária, é incompatibilidade real de sistema operacional, **verificada**: no
`ld` do Linux (GCC 13.2.0) a opção falha com `unrecognized option '--stack=268435456'`
([research.md](./research.md) R4). O juiz original do Codeforces roda em Windows/MinGW, onde a
opção é aceita.

- **Compilação**: `g++ -Wall -Wextra -Wconversion -static -DONLINE_JUDGE -O2 -std=<padrão>`,
  cascata `gnu++20 → gnu++17 → gnu++14 → gnu++11`.
- **Substituição**: limite de pilha de 256 MiB aplicado **em tempo de execução** ao processo
  do sandbox.
- **Unidades (cuidado explícito)**: `268435456` são **bytes**; o `ulimit -s` do shell espera
  **KiB**, então o equivalente é `262144`. Como o motor aplica o limite com
  `resource.setrlimit(RLIMIT_STACK, ...)` (Python), a unidade ali é **bytes** (`268435456`), e
  passar `262144` seria o erro inverso (256 KiB). Por isso o valor vive em **uma constante**
  (`STACK_LIMIT_BYTES`), com uma função de conversão única (`stack_limit_bytes_to_kib`) e
  testes: unitário nos dois sentidos, e de integração que lê o limite efetivo do filho e roda
  uma recursão de ~150 MB (deve passar) e uma que excede 256 MiB (deve estourar). Detalhes: R5.
- **Registro**: esta divergência entra no texto final do TCC (metodologia, seção 7).

## Arquitetura do módulo

```text
  extract (app, rede)                 validate / audit (sandbox, sem rede)            package / verify (app)
  ───────────────────                 ───────────────────────────────────            ──────────────────────
  HF streaming ─▶ elegibilidade ─▶    selfcheck (portão) ─▶ por problema, na ordem   problemas complete ─▶ zip
  classificação ─▶ pool + raw         do pool:                                        determinístico ─▶ manifesto
                                       1. AC_ref no motor (falha ⇒ triagem, D8)         (SHA-256) ─▶ verify
                                       2. candidatas WA em lotes (paralelo,
                                          consumo em ordem) até 100
                                       3. grava atomicamente; status no validacao.json
```

### Módulos e responsabilidades

`src/sandbox/` (fundação compartilhada, sem conhecimento de dataset/IA):

- `types.py`: `ExecutionLimits`, `CompileResult`, `RunResult`, `Verdict`, `SuiteVerdict`,
  `InfraError`.
- `limits.py`: `STACK_LIMIT_BYTES`, `stack_limit_bytes_to_kib`, fatores de folga de tempo.
- `isolation.py`: `preexec` de isolamento (sessão, `setgroups`, `setgid`, `setuid`, `setrlimit`),
  alocação de `slot` (uid `10000 + slot`) e diretório de trabalho do slot.
- `compiler.py`: flags do juiz, cascata de padrões, `compile_cpp`.
- `runner.py`: `run_binary` (rlimits, `wait4`, teto de saída, morte por grupo).
- `judge.py`: `outputs_equal`, `judge_test`, `run_suite`, `judge_source`.
- `selfcheck/`: programas C++ de veredito conhecido + `selfcheck()`.

`src/dataset/` (este módulo):

- `config.py`: `SEED`, `HF_DATASET`, `HF_REVISION`, alvo 200, WAs por problema 100, limiar 30,
  listas de tags/termos.
- `schemas/`: modelos Pydantic (`Metadata`, `Testes`, `Validacao`, `Manifest`, `Pool`, `Report`).
- `extraction/`: `stream.py` (streaming e `staging`).
- `filtering/`: `eligibility.py` (critérios e motivos), `classification.py` (macrocategoria).
- `validation/`: `ac.py` (escolha e execução do `AC_ref`, triagem), `wa.py` (candidatas em lotes,
  estabilidade, contagem 100), `problem.py` (orquestra um problema), `audit.py` (FR-015a).
- `persistence/`: `store.py` (escrita atômica, `building/` → `problems/`, `chown`), `report.py`.
- `integrity/`: `packaging.py` (zip determinístico), `manifest.py`, `verify.py`.
- `__main__.py`: subcomandos (`argparse`).

### Regras que os testes MUST cobrir (Princípio VI)

Motor (`tests/sandbox/`): conversão bytes→KiB e valor passado ao `setrlimit`; limite efetivo
lido de `/proc/self/limits`; recursão profunda passa e estouro é `RE`; cada veredito
(`AC/WA/TLE/MLE/RE/CE`); recuo na cascata registra o padrão usado; curto-circuito no primeiro
teste falho; `outputs_equal` (espaços no fim); isolamento (não lê/escreve em `data/`, fork bomb
contida); `InfraError` nunca vira veredito.

Dataset (`tests/dataset/`): elegibilidade (cada critério, limites 1000/1600 inclusivos, rating ausente,
termos visuais sem distinção de caixa, tag proibida prevalece, E/S por arquivo rejeitada com
motivo `file_io`); macrocategoria pelos cinco exemplos
da metodologia e independente da ordem das tags; "AC divergente é registrado em
`validacao.json` e interrompe o problema" (sem tentar outro AC, sem tolerância); auditoria que
para no AC; contagem exata de 100 WAs e deduplicação; problema com WAs insuficientes vira
`discarded`; mesmo conjunto retido com 1 ou N trabalhadores; retomada com problema parcial;
gravação atômica; zip determinístico ("manifesto bate após regenerar o zip"); verificação
detecta alterado/ausente/excedente; alerta de menos de 30 por categoria; funil por motivo.

## Project Structure

### Documentation (this feature)

```text
specs/001-dataset-extraction/
├── plan.md              # este arquivo
├── research.md          # Fase 0
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/
│   ├── cli.md           # comandos e serviços
│   ├── engine-api.md    # API pública do motor (reutilizada pela avaliação)
│   └── file-formats.md  # formatos dos arquivos do dataset
├── sync-matrix.json     # decisão D# da spec → termos na metodologia (checado por scripts/check_docs_sync.py)
├── checklists/requirements.md
└── tasks.md             # Fase 2 (/speckit-tasks; não criado aqui)
```

### Source Code (repository root)

```text
src/
├── sandbox/
│   ├── README.md             # pelo template docs/template-modulo.md
│   ├── __init__.py
│   ├── types.py
│   ├── limits.py
│   ├── isolation.py
│   ├── compiler.py
│   ├── runner.py
│   ├── judge.py
│   └── selfcheck/            # programas .cpp de veredito conhecido + selfcheck.py
└── dataset/
    ├── README.md             # pelo template docs/template-modulo.md
    ├── __init__.py
    ├── __main__.py
    ├── config.py
    ├── schemas/              # metadata.py testes.py validacao.py manifest.py pool.py report.py
    ├── extraction/           # stream.py
    ├── filtering/            # eligibility.py classification.py
    ├── validation/           # ac.py wa.py problem.py audit.py
    ├── persistence/          # store.py report.py
    └── integrity/            # packaging.py manifest.py verify.py
scripts/verify_dataset.py
scripts/check_docs_sync.py
tests/
├── sandbox/
├── dataset/
└── docs/
manifests/                    # dataset.manifest.json, extraction_report.json (gerados)
```

**Structure Decision**: dois pacotes em `src/` (`sandbox` compartilhado, `dataset` deste módulo),
mais a fundação do repositório acima. O motor fica em `src/sandbox/`, e não dentro de
`src/dataset/`, para que a avaliação futura o importe sem depender de internos do dataset (ver
divergências).

## Divergências e decisões do plano (confirmadas em 2026-09-19)

Itens que se afastam do texto do pedido, da spec, da metodologia ou do `CLAUDE.md`. Os quatro
primeiros foram confirmados pelos autores na revisão do plano e já estão refletidos na spec
(D6, D7, D9, D10, D11), na metodologia (seções 1.1, 1.2, 1.4, 1.6, 6 e 7) e no `CLAUDE.md`.

### Confirmadas pelos autores

1. **Motor em `src/sandbox/`, separado de `src/dataset/`** (mantido). O pedido listava
   "validação/sandbox" como submódulo de `src/dataset/`. A *regra de validação do dataset*
   (escolha do AC, contagem de 100 WAs, triagem, auditoria) fica em `src/dataset/validation/`, e
   o *motor genérico* (compilar, executar, veredito) fica em `src/sandbox/`, o diretório que o
   `CLAUDE.md` já reserva para "compilação e execução isolada em C++". Motivo: D7 e FR-010b
   exigem que a avaliação futura reutilize o motor sem alteração, sem importar internos do
   dataset. Registrado na spec (D7).
2. **Manifesto em `manifests/dataset.manifest.json`, fora de `data/`** (confirmado). A spec
   (FR-027) e a Constitution v1.1.0 (única exceção em `data/` é o zip) implicam manifesto fora
   de `data/`. O `CLAUDE.md` foi ajustado (caminho do manifesto e `pytest` rodando no serviço
   `sandbox`, não em `app`). Registrado na spec (D6) e na metodologia (1.6).
3. **Novo critério de elegibilidade: sem E/S por arquivo** (adotado). 9 problemas do pool
   (0,7%) leem `input.txt` e escrevem `output.txt`; o motor injeta `stdin` (metodologia,
   seção 4), então o AC deles falharia e cada um viraria triagem manual (D8). É FR-004(h) na
   spec (D9) e o critério da seção 1.2 da metodologia, com motivo de rejeição `file_io`. A
   regra é implementada em `filtering/eligibility.py` e **está ativa** (não é opcional).
4. **Seed = 42** (confirmado), em `dataset/config.py`; gravada no pool, no manifesto e no
   relatório. Trocar depois da primeira extração muda a seleção. Registrado na spec (D11) e na
   metodologia (1.4).

### Registradas (refletidas na spec e na metodologia em 2026-09-19)

5. **Limite de pilha pelo Python, não pelo shell.** O motor usa `resource.setrlimit` em
   **bytes** (`268435456`), e não `ulimit -s` (KiB, `262144`); o efeito é o mesmo e o valor em
   KiB é derivado por função única com testes (seção "Divergência de plataforma"). Refletido na
   spec (D2) e na metodologia (1.4).
6. **Correção factual da metodologia 1.1** (feita em 2026-09-19, spec D10). O dataset na
   revisão atual tem 13.328 + 117 + 165 = 13.610 exemplos (a metodologia dizia 4.044, com
   `train` 3.760), e 118 problemas Codeforces vêm sem `cf_rating` (inelegíveis).
7. **Extração em passagem única**, revisão do Hugging Face fixada e checkpoint por shard
   (R1); staging local em `data/work/` (subconjunto do pool, não o repositório completo,
   compatível com FR-001). Refletido na spec (D12, FR-001) e na metodologia (1.1).
8. **Relatório final versionado**: `package` copia o relatório de extração para
   `manifests/extraction_report.json`, para que os números citados no TCC acompanhem a versão
   do dataset (pequeno acréscimo; sem impacto no pacote). Refletido na spec (FR-018b, D12) e na
   metodologia (1.6).
9. **Tamanho do zip**: estimado em ~10 MB (R15); Git LFS não é planejado. Refletido na
   metodologia (1.6, 1.7) e na spec (D12).
10. **`valid` e `test` dificilmente fecham 100 WAs**: mediana de 101 incorretas brutas contra
    ~200 no `train` (R19). Tende-se a ter uma amostra quase toda do `train`; a spec não impõe
    equilíbrio entre splits. Refletido na spec (D12) e na metodologia (1.7).
11. **`data/work/` com permissão `0700`** (D15). O `./data` montado herda a permissão do host
    (tipicamente `0755`) e o filho de uid dedicado conseguiria lê-lo. Criado por
    `ensure_work_dir`/`make_private_dir` no `store.py`, com teste de permissões e de isolamento.
    Refletido na spec (D15, FR-009) e na metodologia (1.4, 1.7).
12. **Segredos**: a convenção foi generalizada na constitution v1.2.1 (`.env` injetado por
    `env_file` do compose ou carregado com `python-dotenv`); não há dependência nova nem
    desvio a justificar.

## Riscos

| # | Risco | Impacto | Mitigação |
|---|---|---|---|
| 1 | A fração de incorretas que é WA de verdade pode ser baixa (o resto é TLE/RE/CE); só o motor a mede (R19) | A meta de 200 problemas com exatamente 100 WAs pode não fechar sem relaxar D4 ou critérios | Piloto de ~10 problemas do `train` logo após o motor; parada antecipada; relatório mostra o déficit exato (FR-017); nenhuma relaxação automática |
| 2 | Vereditos por tempo variam entre execuções (carga da máquina) e podem mudar a seleção | Quebra de determinismo (FR-025) | Tempo de CPU, não de parede; `stability_runs = 2`; `--workers` padrão deixa folga de CPU |
| 3 | Queda de rede/reset de conexão durante o streaming (observado) | Perda de tempo | Retentativas da biblioteca + checkpoint por shard |
| 4 | Problemas com verificador especial que escaparam do filtro de tags | Volume de triagens manuais (D8) | Cada uma é registrada com a saída divergente; o relatório as lista; sem tolerância agregada |
| 5 | `RLIMIT_AS` conta espaço de endereçamento (ex.: arenas do glibc em programas com threads) | Falso MLE em AC ou WA | Programas C++ de competição raramente usam threads; qualquer falso MLE em AC aparece na triagem, não passa silenciosamente |
| 6 | Docker rootless ou sem as 5 capabilities | Motor não consegue soltar privilégios | `selfcheck` falha de forma explícita antes de qualquer validação; documentar o requisito |
| 7 | Hash do zip depende do zlib da imagem | Hash diferente fora da imagem fixada | Identidade do conteúdo vem dos hashes por arquivo; o zip é reproduzido dentro da imagem (R14) |

## Documentação (Princípio XI)

A feature só é concluída com a documentação abaixo; o `/speckit-tasks` MUST gerar uma tarefa
para cada item (Constitution, Fluxo de Desenvolvimento).

| Entrega | Onde | Regra |
|---|---|---|
| README do módulo `dataset` | `src/dataset/README.md` | template `docs/template-modulo.md` (seis campos); comandos de [contracts/cli.md](./contracts/cli.md) registrados na tabela "Comandos verificados" (`pendente` até a tarefa que os executa carimbar data, revisão e tarefa) |
| README do módulo `sandbox` | `src/sandbox/README.md` | idem; API de [contracts/engine-api.md](./contracts/engine-api.md); dependências e serviço do Compose (sem rede) |
| Script de conformidade | `scripts/check_docs_sync.py` (+ `tests/docs/`) | checagens C1 a C6: seções do README, comandos contra a CLI (no README do módulo dono da CLI, `src/dataset`, todo subcomando também precisa estar documentado), links, estado do README raiz, matriz de sincronização, ausência de `[PROPOSTA]` ativa (riscadas e legenda não contam); é o gate do FR-031/FR-032/SC-016 |
| Matriz de sincronização | `specs/001-dataset-extraction/sync-matrix.json` | toda decisão D# da spec tem linha e termos que precisam aparecer na metodologia |
| Gate das regras do motor | primeira tarefa da US2 | os autores confirmam ou alteram as regras operacionais, hoje `[PROPOSTA]`, antes dos testes e do código do motor |
| `--help` e docstrings | `python -m dataset --help` e pacotes | não podem contradizer os READMEs |
| Visão geral do projeto | `README.md` (raiz) | passa de "planejado" para "disponível" cada etapa concluída, com comandos exatos e já executados; a frase "Estado atual" e a data são reescritas a cada atualização (checagem C4) |
| Metodologia sincronizada | `docs/metodologia-referencia.md` | todo dado medido e toda decisão da implementação entram no mesmo ciclo, com nova linha no histórico (seção 8) |
| Checagem final | revisão (Princípio X) | `scripts/check_docs_sync.py --closing` com saída 0 e os itens da lista de `docs/template-modulo.md` que o script não decide (FR-032, SC-016) |

Auditoria retroativa (2026-09-19): os itens 5 e 7 a 10 da seção de divergências estavam
marcados como "a refletir" e não estavam na spec nem na metodologia; foram propagados junto
com os dados medidos de R1, R15 e R19. Nenhum módulo estava implementado nem tinha README, então
não houve README existente a ajustar.

## Complexity Tracking

Decisões de custo, todas justificadas por um princípio; nenhuma é violação.

| Decisão | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Orquestrador root com 5 capabilities e uid por execução | Princípio V: código de terceiros sem privilégios e sem acesso a `data/work/` (R8, D15) | Rodar tudo como um usuário: o código de terceiros poderia escrever em `data/` e matar o orquestrador |
| Dois serviços Compose (`app` com rede, `sandbox` sem rede) | Princípio V: código de terceiros sem rede; a extração precisa de rede | Um serviço só: ou o código de terceiros teria rede, ou a extração não funcionaria |
| Processos paralelos com consumo em ordem | ~10^5 s de CPU (R11); sem paralelismo, dezenas de horas | Execução serial: inviável; paralelismo com ordem de conclusão: quebra FR-014/FR-025 |
| Override do compose que monta o working tree (`src`, `tests`, `scripts`, `docs`, `specs`, `README.md`, `pyproject.toml`; sem `.env` nem `.git`) | Laço de desenvolvimento: `black .`, `ruff --fix` e `pytest` agem sobre o repositório sem rebuild a cada edição | Sem override: `black .` roda dentro da imagem e não altera o repositório, e cada teste exigiria `docker compose build` |
| Pacote `src/sandbox/` separado de `src/dataset/` | D7/FR-010b: o motor é reutilizado sem alteração pela avaliação | Motor dentro de `dataset/`: a avaliação dependeria de internos do dataset |

## Reavaliação da Constitution após o desenho (Fase 1)

Sem mudança no resultado: **PASS** em todos os princípios aplicáveis, incluindo o Princípio XI
adicionado na v1.2.0 (seção "Documentação"). Pontos de atenção
carregados para `/speckit-tasks`: (a) teste de integração do isolamento dentro do motor (R8);
(b) medir o tamanho real do zip e decidir Git LFS (R15); (c) fixar o digest da imagem do `uv` no
`Dockerfile` (o da imagem `gcc:13.2.0` já está no desenho).
