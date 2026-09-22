# Research: Extração, Validação e Persistência do Dataset

**Feature**: `001-dataset-extraction` | **Data**: 2026-09-19 | **Plan**: [plan.md](./plan.md)

Todas as incertezas do Technical Context foram resolvidas abaixo. Onde há "Verificado", o fato
foi medido neste ambiente durante o planejamento (Docker 29.7, `gcc:13.2.0`, `datasets` 5.0.1),
e não assumido. Onde há "A verificar na implementação", há um teste que fecha a dúvida.

## R1 — Acesso ao dataset em streaming

- **Verificado**: `deepmind/code_contests` está hospedado em Parquet (39 shards de treino, 1 de
  `valid`, 1 de `test`), sem script de carga, licença CC-BY-4.0, sem acesso restrito. Com
  `datasets` 5.0.1, `load_dataset(..., streaming=True)` funciona, `select_columns` reduz o que é
  lido, e o esquema real está abaixo. Revisão atual do repositório:
  `802411c3010cb00d1b05bad57ca77365a3c699d6`.
- **Esquema real relevante**: `source` e `language` são `ClassLabel` (inteiros):
  `source`: `UNKNOWN_SOURCE=0, CODECHEF=1, CODEFORCES=2, HACKEREARTH=3, CODEJAM=4, ATCODER=5,
  AIZU=6`; `language`: `UNKNOWN_LANGUAGE=0, PYTHON=1, CPP=2, PYTHON3=3, JAVA=4`. Isso confirma
  `CODEFORCES = 2` e `CPP = 2` da metodologia. `time_limit` é `{seconds:int64, nanos:int64}`;
  `cf_points` é `float32`; `cf_rating` é `int32`; `memory_limit_bytes` é `int64`. Além dos campos
  documentados na metodologia, existem `difficulty`, `untranslated_description`, `input_file` e
  `output_file`.
- **Decisão**: uma única passagem em streaming pelos três splits (ordem `train`, `valid`,
  `test`, primeira ocorrência de `problem_id` vence), com a revisão fixada, aplicando
  elegibilidade e classificação em linha e gravando em `staging/` apenas os problemas do pool
  (com testes e submissões C++). Checkpoint por **shard**: cada shard (`ds.shard(num_shards=n_shards, index=i)`) é
  processado e marcado como concluído em `staging/shards/`; uma queda de rede (observada
  durante a pesquisa: resets de conexão) refaz só o shard em andamento. A ordem global é
  determinística: shards de `train` em ordem, depois `valid`, depois `test`.
- **Rationale**: uma passagem lê o repositório uma vez; duas passagens (leve + pesada) leriam a
  parte pesada de qualquer forma. A revisão fixada dá "mesmo dataset de entrada" (Princípio II).
- **Alternativas**: duas passagens com projeção de colunas (sem ganho, pois a segunda
  precisaria reler tudo); leitura seletiva de row groups com `pyarrow` e `HfFileSystem`
  (mais rápida, mas é código próprio de acesso a Parquet, contra o Princípio IX e contra a
  escolha de `datasets` feita pelos autores); `state_dict()` para retomar o iterador (troca
  a granularidade de shard por linha, mas depende de recurso menos estável da biblioteca).

### Funil medido (revisão fixada, três splits, colunas leves)

Medido em 2026-09-19 (duas passagens completas, com resultados idênticos), revisão
`802411c3…`, três splits, com as regras de FR-004 (sem a checagem de soluções C++, que exige
as colunas pesadas). Este é o mesmo funil registrado na metodologia (seção 1.2):

| Etapa | Problemas restantes |
|---|---:|
| Linhas lidas (`train` 13.328 + `valid` 117 + `test` 165) | 13.610 |
| Origem Codeforces (`train` 7.819, `valid` 117, `test` 165) | 8.101 |
| `cf_rating` entre 1000 e 1600 (os 118 problemas Codeforces sem rating caem aqui) | 2.399 |
| Ao menos uma tag permitida | 2.155 |
| Nenhuma tag proibida | 1.751 |
| Sem termo de dependência visual | 1.288 |
| `is_description_translated == false` | 1.288 (nenhum removido nesta etapa) |
| `problem_id` único entre os splits | 1.288 (nenhuma duplicata) |
| Sem E/S por arquivo (`input_file` e `output_file` vazios) | 1.279 (9 removidos) |
| Ao menos uma solução correta e uma incorreta em C++ (medido na extração real de 2026-09-20) | 1.250 (29 removidos) |
| Ao menos 100 incorretas em C++ brutas (idem) | **1.234** (16 removidos) |

Os **1.288** problemas são os elegíveis antes do critério de E/S por arquivo e os **1.279** são
o pool antes da checagem de soluções em C++. **Atualização de 2026-09-20**: a extração real
reproduziu exatamente as nove primeiras etapas e o **pool final tem 1.234 problemas**:
`estrutural_otimizacao` 407, `matematica` 278, `logica_direta` 549; por origem, `train` 1.206,
`valid` 9, `test` 19. (A distribuição do pool de 1.279, sem a checagem em C++, era 417/285/577,
com `train` 1.250 e `test` 20.) Os 9 removidos por E/S
por arquivo (todos com `input.txt`/`output.txt`) são `120_A`, `120_B`, `120_C`, `234_B`,
`234_C`, `253_A`, `253_B`, `253_C` e `36_A` (2 matemática, 3 estrutural/otimização, 4 lógica
direta).

O filtro de termos visuais remove 463 problemas (26% dos que chegavam a ele); como único
motivo: `image` 189, `as follows` 77, `http` 27, `figure` 10, `picture` 8, `shown below` 1.
Há folga (pool ≈ 6× a meta), então não é necessário relaxar critério algum.

**Correção factual da metodologia (1.1)**: os tamanhos "4.044 exemplos, `train` 3.760" não
correspondem à revisão atual do dataset (13.328 + 117 + 165 = 13.610). A lógica do módulo não
depende desses números, mas o texto deve ser corrigido (Princípio I).

**Tempo**: a passagem completa em streaming, só com colunas leves, levou ~24 a 28 min (com
retentativas automáticas de rede da biblioteca). Com todas as colunas será maior; por isso a
extração grava checkpoints por shard (abaixo).

## R2 — Imagem base: GCC exato + Python

- **Verificado**: `gcc:13.2.0` (Debian 12, glibc 2.36) existe, traz `g++ (GCC) 13.2.0` e
  `libc.a` (necessário para `-static`). Digest observado:
  `sha256:15c73bc59ae88b3fd563ef2ec4a8743a8848a9f74362b6d116c4543c4844b6e0`.
- **Decisão**: `FROM gcc:13.2.0@sha256:15c73bc5…` (digest completo acima) com Python 3.11.16 instalado pelo `uv`
  (gerenciado, fixado em `.python-version`), não pelo `apt`.
- **Rationale**: a metodologia exige "GCC ≥ 13.2" e o compilador do juiz é o 13.2; fixar
  exatamente 13.2.0 por digest dá o ambiente mais próximo do original e reprodutível.
  O Python da distribuição (3.11.2) não é fixável por patch.
- **Alternativas**: `python:3.11-bookworm` (só traz GCC 12, abaixo do mínimo); `ubuntu:24.04` +
  `g++-13` (13.3, patch diferente e deriva por atualização de pacotes); `gcc:13` (tag móvel).

## R3 — Gerenciamento de dependências com `uv`

- **Decisão**: `pyproject.toml` com `[tool.uv] package = false` (aplicação, não biblioteca),
  `uv.lock` versionado, grupo `dev` (pytest, ruff, black) no mesmo ambiente. No `Dockerfile`, o
  ambiente virtual é criado em `/opt/venv` com `uv sync --frozen` e colocado no `PATH`; o
  código é encontrado por `PYTHONPATH=/app/src` (e `pythonpath = ["src"]` no pytest). O `uv`
  (versão fixada) só existe na fase de build; em execução não há resolução nem rede.
- **Rationale**: `package = false` elimina configuração de backend de build: um novo
  `src/<modulo>/` é importável sem editar o `pyproject.toml`, que é exatamente o requisito de
  "não precisar refazer a fundação". Uma imagem única evita manter dev/prod separados
  (Princípio IX).
- **Alternativas**: backend de build com lista de pacotes (obriga editar a cada módulo);
  `pip` + `requirements.txt` (sem lock com hashes; os autores pediram `uv`).

## R4 — Flags de compilação e a opção de linker do Windows

- **Verificado** (gcc 13.2.0, Debian 12): a linha original com `-Wl,--stack=268435456` falha em
  Linux com `/usr/bin/ld: unrecognized option '--stack=268435456'` e `rc=1`; sem a opção,
  `g++ -Wall -Wextra -Wconversion -static -DONLINE_JUDGE -O2 -std=gnu++20` compila (`rc=0`).
  Confirma D2: é incompatibilidade real de SO (linker PE/MinGW × ELF), não escolha.
- **Decisão**: usar exatamente as flags do juiz, exceto essa; a cascata troca só o `-std`. A
  substituição é o limite de pilha em tempo de execução (R5).

## R5 — Limite de pilha e o cuidado com unidades

- **Verificado**: com `ulimit -s 262144` (KiB) uma recursão de 2 milhões de níveis (~150 MB de
  pilha) conclui (`rc=0`); com o padrão de 8 MiB dá `SIGSEGV` (`rc=139`); com 256 MiB e 8
  milhões de níveis volta a estourar (`rc=139`), ou seja, o limite é real e não infinito.
  `ulimit -s` informa `262144` (KiB).
- **Ponto de atenção**: as unidades dependem do mecanismo. O `ulimit -s` do shell usa **KiB**
  (`262144`); o `resource.setrlimit(RLIMIT_STACK, ...)` do Python usa **bytes** (`268435456`).
  Passar `262144` ao `setrlimit` aplicaria 256 KiB, o erro inverso do descrito no pedido.
- **Decisão**: aplicar em processo, com `resource.setrlimit` (sem shell), em bytes; manter uma
  constante `STACK_LIMIT_BYTES = 268_435_456` e uma função única
  `stack_limit_bytes_to_kib()` para o equivalente do shell (`262144`), usada em
  documentação, relatórios e testes. Teste unitário nos dois sentidos e teste de integração que
  lê `Max stack size` de `/proc/self/limits` no filho e roda uma recursão de ~150 MB. Limite
  `soft = hard` para o filho não poder aumentá-lo. Como defesa em profundidade, valores abaixo de
  1 MiB são rejeitados (`ValueError`) em `apply_stack_limit` e em `ExecutionLimits`: um número
  como `262144` quase certamente é KiB passado no lugar de bytes (implementado e testado em
  2026-09-20).
- **Alternativa**: `sh -c 'ulimit -s 262144; exec prog'` (literal ao pedido, mas adiciona um
  shell por execução e outra camada de parsing; o efeito é o mesmo).

## R6 — Limite de memória e classificação de MLE

- **Medição do pico (2026-09-21, T049)**: `ru_maxrss` de um filho lido do processo Python herda o
  conjunto residente do `fork` (40 MB medidos para um programa de 0,6 MB), o que geraria falso
  `MLE` (pico `>=` limite) em limites pequenos, como os 61 MiB do menor problema do pool. O pico
  passa a ser medido por `sandbox-launch` (`src/sandbox/launcher/`), que executa o programa e lê
  `wait4` de um processo minúsculo: o mesmo programa mede 652 KiB. Só existe quando o lançador
  termina normalmente (no estouro da reserva de tempo de parede, o veredito é `TLE` de qualquer
  forma). D16.

- **Verificado** (binário estático): `RLIMIT_AS` (`ulimit -v`) coexiste com a pilha de 256 MiB
  (recursão de ~150 MB com `AS=256 MiB` conclui); um `hello` estático roda com `AS=20 MB`;
  alocar 300 MB sob `AS=256 MiB` termina com `SIGABRT` (`rc=134`, `std::bad_alloc`);
  alocações não tocadas também contam (o limite é de espaço de endereçamento, análogo à
  memória "commit" do Windows).
- **Decisão**: `RLIMIT_AS = memory_limit_bytes` do problema (extraído dos metadados, nunca
  fixo). Classificação: `MLE` quando há `SIGABRT` com a assinatura `bad_alloc` no `stderr` ou
  pico de memória (`ru_maxrss`) `>= limite`; demais sinais e saídas não zero são `RE`.
- **Limitação registrada**: `bad_alloc` e outros `abort()` produzem o mesmo sinal, e o
  espaço de endereçamento não é idêntico à métrica do juiz original. Baixo impacto: `MLE` e
  `RE` têm o mesmo destino (descartar a submissão incorreta; em AC, triagem), então a
  ambiguidade não muda o conteúdo do dataset, só o rótulo do relatório.

## R7 — Limite de tempo

- **Confirmada pelos autores em 2026-09-20 (D13)**, com critério objetivo de reabertura no
  piloto: mais de 10% dos ACs testados reprovados por `TLE` reabre a regra (metodologia, 1.4).

- **Decisão**: o tempo medido é o de CPU do processo filho (`wait4` → `ru_utime + ru_stime`),
  o que é robusto a carga da máquina; `TLE` se `> time_limit_seconds`. Reserva no kernel:
  `RLIMIT_CPU = ceil(limite) + 1`. Reserva de parede para programas bloqueados:
  `limite × 3 + 1 s`, com o processo morto por grupo de processos. Os fatores são constantes
  do motor (não dos problemas) e ficam em `sandbox/limits.py`.
- **Rationale**: o limite "de verdade" do problema continua vindo dos metadados; só a folga de
  parede é do motor.

## R8 — Isolamento do código de terceiros

- **Reverificação com o motor (2026-09-21, T049, D16)**: os fatos abaixo se confirmaram, com três
  correções: (a) `/tmp`, `/dev/shm` e `/dev/mqueue` eram graváveis pelo uid do slot; agora `/tmp`
  e `/dev/shm` são `tmpfs` `0700` e `RLIMIT_MSGQUEUE = 0`; (b) sem init, órfãos de grupos mortos
  viravam zumbis (o PID 1 era o Python), então o serviço usa `init: true`; (c) o `RLIMIT_NPROC`
  passou a contar também o lançador, então um programa cria no máximo 30 filhos (medido). Os
  processos que saem da sessão (`setsid`) sobrevivem à morte do grupo; o motor os mata por uid
  quando `killpg` encontra sobreviventes.

- **Verificado** (contêiner com `--network none`, raiz somente leitura, `cap_drop ALL` +
  `SETUID, SETGID, CHOWN, KILL, DAC_OVERRIDE`, `no-new-privileges`): o filho lançado com uid
  10001 tem `CapPrm = CapEff = 0`; não lê nem escreve em um diretório de dados `0700` do
  orquestrador; não escreve no sistema de arquivos raiz; uma fork bomb é contida por
  `RLIMIT_NPROC = 32` (31 processos criados); o orquestrador consegue matar o filho e apagar
  seus arquivos; só existe a interface `lo`.
- **Decisão**: o orquestrador roda como root sem privilégios extras além dos cinco acima; cada
  execução roda como um uid dedicado por `slot` de trabalhador (`10000 + slot`), em
  `preexec_fn` na ordem: nova sessão → `setgroups([])` → `setgid` → `setuid` (perde as
  capabilities) → `setrlimit` (só reduz limites). `tmpfs` de trabalho com opção `exec` (o
  padrão do Docker é `noexec`, o que impediria executar o binário compilado).
- **Ordem importa**: `setuid` antes de `RLIMIT_NPROC`, porque o kernel pode recusar o `execve`
  se o contador do uid novo já excede o limite.
- **A verificar na implementação**: teste de integração da fork bomb e do isolamento dentro do
  motor (não só com `setpriv`).
- **Alternativas**: orquestrador não root sem `setuid` (o código de terceiros rodaria como o
  mesmo usuário e poderia escrever em `data/`, violando o Princípio V); namespaces de usuário
  (bloqueados pelo perfil `seccomp` padrão sem `CAP_SYS_ADMIN`); um contêiner por execução
  (orquestração de contêineres é complexidade fora de escopo).
- **Efeito colateral e mitigação**: arquivos criados como root em um volume de bind ficariam
  com dono `root` no host. O gravador atômico aplica `chown` para `HOST_UID:HOST_GID`
  (variáveis passadas pelo Compose) usando a capability `CHOWN`.
- **Refinamento (2026-09-19, spec D15)**: a verificação acima usou um diretório `0700` criado
  dentro do contêiner. No compose real, o `./data` montado herda a permissão do host
  (tipicamente `0755`), que o filho de uid dedicado consegue **ler**. Decisão: `data/work/` é
  criado com `0700` (dono: usuário do host) por `ensure_work_dir`/`make_private_dir`, com
  `chmod` explícito (o `umask` não pode afrouxá-lo); o orquestrador (root com `DAC_OVERRIDE`) e o
  serviço `app` (usuário do host) continuam acessando. **Limitação medida no contêiner `sandbox`
  (2026-09-20)**: como root **sem** `CAP_FOWNER`, ele lê e escreve em qualquer lugar
  (`DAC_OVERRIDE`), mas não consegue mudar o modo (`chmod`) de um diretório que já pertence ao
  usuário do host; na segunda chamada de `ensure_work_dir` (por exemplo, ao retomar uma execução)
  isso dava `EPERM`. Solução sem capability nova: não mexer no modo quando ele já está certo e,
  se precisar mudar, tomar posse com `CAP_CHOWN`, aplicar o modo e devolver o diretório. O mesmo
  vale para qualquer operação que exija ser dono (por exemplo, `utime` com horário explícito): o
  código não deve depender delas. Arquivos públicos (`data/dataset.zip`)
  ficam legíveis. Vale a mesma restrição para `.env` e `.git`, que não são montados no serviço
  `sandbox` (ver o override do compose no plano).

## R9 — Regra de comparação de saída e veredito

- **Confirmada pelos autores em 2026-09-20 (D13)**, com critério objetivo de reabertura no
  piloto: mais de 10% dos ACs testados reprovados por divergência só de formatação reabre a
  regra (metodologia, 1.4). Diagnóstico: `TriageRecord.divergence.format_only`, calculado
  fora do motor (`dataset.validation.ac`), comparando tokens separados por espaço em branco;
  `outputs_equal` continua sendo a única regra que decide vereditos.

- **Decisão**: uma função única `outputs_equal` (sem diferença após remover espaços no fim de
  cada linha e linhas em branco no fim do arquivo), como definido na spec. Veredito de um
  programa sobre a suíte: o **primeiro** teste que não termina em `AC` decide (FR-012) e
  interrompe a execução (curto-circuito).
- **Consequência conhecida**: problemas com mais de uma resposta válida (verificador
  especial) não têm `AC` reproduzível pela comparação textual e vão para triagem (D8; inspeção adiada, D17).

## R10 — Estabilidade do veredito

- **Decisão**: `stability_runs = 2`. Uma submissão candidata só é retida como WA se duas
  execuções independentes até o teste decisivo produzirem o mesmo veredito e o mesmo teste
  decisivo. O `AC_ref` é executado uma vez na seleção e novamente na auditoria.
- **Rationale**: custo adicional pequeno (a execução para no teste decisivo, normalmente
  cedo) contra o risco de reter uma falha instável por comportamento indefinido (FR-013).

## R11 — Paralelismo sem perder determinismo

- **Estimativa**: cada problema do `train` traz ~200 candidatas (mediana; ver R19); com ~2 s
  de compilação cada e ~350 problemas processados para chegar a 200 completos, são ~1,4×10^5 s
  de CPU: ~39 h em série, ~5 h com 8 trabalhadores. **Medido em 2026-09-21 (T049)**: compilar com
  `#include <bits/stdc++.h>` leva **2,5 s** (não 2 s) e cada teste tem 2,5 ms de sobrecarga, então
  o mesmo cálculo dá ~1,75×10^5 s: ~49 h em série, ~6 h com 8 trabalhadores, sem contar o corte
  por parada antecipada. Parada antecipada quando
  `retidas + candidatas restantes < 100` corta o custo dos problemas que não vão fechar.
- **Decisão**: `ProcessPoolExecutor` com trabalhadores fixos (cada um com seu `slot` de uid e
  seu diretório de trabalho); as candidatas são despachadas em lotes na ordem determinística e
  os resultados são consumidos **na ordem das candidatas**, não na ordem de conclusão; para de
  despachar ao completar 100 retidas. O conjunto retido é o mesmo para qualquer número de
  trabalhadores. Usa processos (não threads), compatível com `preexec_fn`.
- **Rationale**: sem o paralelismo a execução não é viável; a ordem de consumo preserva FR-014 e
  FR-025.

## R12 — Seeds e ordens determinísticas

- **Decisão**: `random.Random(f"{SEED}:{contexto}")` (semente textual, determinística e
  independente de `PYTHONHASHSEED`). Ordens: (a) pool: ordenado por `problem_id` e embaralhado
  com `Random(f"{SEED}:pool")`; (b) candidatas WA de um problema: remove duplicatas de texto
  mantendo a primeira ocorrência e embaralha com `Random(f"{SEED}:wa:{problem_id}")`; (c)
  `AC_ref`: primeira solução C++ correta na ordem original do dataset (sem aleatoriedade).
  `SEED` fica em `dataset/config.py`, é gravado no pool, no manifesto e no relatório.
- **Confirmado pelos autores em 2026-09-19**: `SEED = 42` (spec D11).

## R13 — Persistência, idempotência e retomada

- **Decisão**: cada problema é construído em `work/building/<id>/` e movido com `os.rename`
  (atômico no mesmo sistema de arquivos) para `work/problems/<id>/`; `validacao.json.status`
  registra o desfecho. No início, todo `building/` é descartado. Arquivos JSON são gravados
  com escrita atômica. `complete`, `pending_triage` e `discarded` nunca são reprocessados.
  Detalhes: [data-model.md](./data-model.md) §3.

## R14 — Zip determinístico e manifesto

- **Decisão**: entradas ordenadas, `date_time = (1980, 1, 1, 0, 0, 0)`, `external_attr`
  fixo, `ZIP_DEFLATED` com nível fixo, raiz `dataset/`. O manifesto lista o SHA-256 de cada
  arquivo e do zip, sem carimbo de data/hora; fica em `manifests/` (fora de `data/`, que é
  ignorado pelo Git), o que é consistente com FR-027 e com a Constitution v1.1.0.
- **Limite conhecido**: os bytes do `deflate` dependem da versão do zlib; a igualdade de hash do
  zip é garantida na imagem fixada. A identidade do conteúdo entre ambientes é garantida pelos
  hashes por arquivo do manifesto.
- **Risco de tamanho**: ver R15.

## R15 — Tamanho do `dataset.zip` e o limite do GitHub

- **Fato**: o GitHub recusa arquivos acima de 100 MB em um push comum e avisa acima de 50 MB.
  A Constitution v1.1.0 manda versionar `data/dataset.zip`.
- **Medido** (29 problemas elegíveis de `valid`+`test`): mediana de 200 testes por problema
  (1 público, 0–30 privados, ~200 gerados), ~13 KB de payload de testes por problema (máx. 65
  KB) e ~170 KB de código-fonte para 100 submissões C++. Estimativa para 200 problemas: ~40 MB
  sem compressão e ~10 MB compactado, bem abaixo do limite.
- **Decisão**: o comando `package` mede o zip e avisa a partir de 95 MB. Git LFS só seria
  necessário se a estimativa estiver errada por uma ordem de grandeza; não é planejado.
- **Medido de verdade (2026-09-22, T093, revisão `9b87d7e`)**: `data/dataset.zip` real, dos 200
  problemas completos, tem **12.891.474 bytes (≈ 12,3 MiB)** — 29% acima da estimativa de ~10 MB,
  mas nem de longe uma ordem de grandeza; bem abaixo do aviso de 95 MB e do limite de 100 MB do
  GitHub. Git LFS confirmado como não necessário.

## R16 — Problemas com entrada/saída por arquivo (`input_file`, `output_file`)

- **Medido**: no pool de 1.288 problemas (antes deste critério), 9 (0,7%) têm `input_file`/`output_file` não vazios
  (`input.txt`/`output.txt`), todos de concursos antigos (120, 234, 253). As soluções desses
  problemas leem e escrevem arquivos, mas o motor injeta a entrada por `stdin` (metodologia,
  seção 4). O AC deles falharia no motor e, pela regra D8, cada um viraria uma triagem manual.
- **Decisão (confirmada pelos autores em 2026-09-19)**: novo critério de elegibilidade "sem
  E/S por arquivo" (`input_file` e `output_file` vazios), com motivo de rejeição `file_io`
  (FR-004(h), spec D9; metodologia 1.2). Evita 9 triagens previsíveis e custa 0,7% do pool. É
  uma regra ativa em `filtering/eligibility.py`, coberta por teste (problema com
  `input.txt`/`output.txt` é rejeitado com esse motivo).
- **Alternativa rejeitada**: manter o problema no pool e tratar cada falha de AC na triagem.

## R17 — Testes e ferramentas de qualidade

- **Decisão**: `pytest` (com `pythonpath = ["src"]`), `ruff` e `black` (versões fixadas no
  lock), testes em `tests/<modulo>/` espelhando `src/<modulo>/`. Testes que executam C++
  rodam no serviço `sandbox` (precisam de `SETUID/SETGID`); os demais também rodam ali, por
  simplicidade, sem rede. Fixtures pequenas embarcadas (programas de veredito conhecido,
  problemas sintéticos); nenhum teste depende da rede ou do dataset real.
- **Marcadores**: `@pytest.mark.integration` para os que compilam/executam C++ (mais lentos).

## R18 — CLI

- **Decisão**: `argparse` da biblioteca padrão, subcomandos em `dataset/__main__.py`. Sem
  `typer`/`click` (Princípio IX). A CLI de projeto (`src/cli/`) é escopo de outra feature.

## R19 — Quantas submissões incorretas existem, e quantas chegam a 100 WAs

- **Medido na extração real (2026-09-20), pool de 1.234**: `raw_wa_count` mín. 100 (pré-checagem),
  **mediana 200**, máx. 679; `train` (1.206) mediana 201; `valid` (9) mediana 101; `test` (19)
  mediana 101. 138 problemas têm entre 100 e 109 e 167 têm menos de 150 (144 `train`, 8 `valid`,
  15 `test`). A amostra de 150 do `train` estimava 99% com ≥ 100; na população, 1.206 dos 1.250
  problemas do `train` (96,5%) passam nas duas checagens em C++.

- **Medido, `train`** (amostra aleatória de 150 problemas elegíveis, streaming embaralhado):
  incorretas em C++ por problema: mín. 0, p10 102, p25 196, **mediana 200**, p75 281, p90 317,
  máx. 629. Com ≥ 100: 99%; com ≥ 150: 87%; com ≥ 200: 57%. Sem nenhuma solução correta em
  C++: 1 de 150.
- **Medido, `valid` + `test`** (os 29 elegíveis): incorretas em C++: mín. 98, **mediana 101**,
  máx. 217; ≥ 100 brutas em 28 de 29 e ≥ 100 de texto único em 25 de 29.
- **Leitura**: o corte de 100 WAs *validados* depende da fração das incorretas que é WA de
  verdade (o resto é TLE, MLE, RE, erro de compilação ou passa nos testes), e essa fração só o
  motor mede. Nos problemas do `train` (~200 brutas) é plausível chegar a 100; em `valid`/`test`
  (~100 brutas) é praticamente impossível, e eles serão `discarded` (D4).
- **Decisões de projeto**: (a) pré-checagem barata na extração (`raw_wa_count >= 100`, motivo
  `insufficient_raw_wa`); (b) parada antecipada por problema quando
  `retidas + candidatas restantes < 100` (motivo `insufficient_wa`); (c) recomenda-se um piloto
  de ~10 problemas do `train` logo após a implementação do motor para medir a fração de WA
  antes da execução completa (Nível 3 do quickstart).
- **Risco residual**: se a fração de WA validada for baixa (por exemplo, abaixo de ~50%),
  a meta de 200 problemas com exatamente 100 WAs pode não fechar sem relaxar D4 ou os critérios
  de elegibilidade. Ver "Riscos" em [plan.md](./plan.md).

- **Medido no piloto (2026-09-21, 14 problemas do `train`)**: 1.000 de 1.169 candidatas
  consumidas viraram WA (85,5%); 121 passam em todos os testes (10,3%), 33 não compilam, 9 `RE`,
  3 `TLE`, 2 `MLE`, 1 instável; por problema completo, 101 a 203 candidatas consumidas (mediana
  108). O risco residual acima não se materializou no `train`. Três ACs em triagem por causas
  distintas (verificador especial, gabarito com linha em branco inicial, teste gerado fora das
  restrições); ver metodologia 1.7.
- **Tempo medido (R11)**: mediana de 102 s por problema completo com 4 processos no piloto, ~7 h
  extrapoladas para 200 completos; **na validação completa (2026-09-21) foram 264 problemas
  processados em 5 h 06 min, mediana de 83 s por problema completo, 75,8% de problemas completos e
  84,6% das candidatas consumidas viraram WA**.

## R21 — Reparo de WA divergente na auditoria (D18)

- **Medido (2026-09-21/22)**: 13 dos ~26.400 WA gravados (0,05%) divergiram na auditoria; código-fonte confirma comportamento indefinido ou tempo no limiar em todos os casos inspecionados.
- **Alternativa investigada e descartada**: desligar ASLR (`personality(ADDR_NO_RANDOMIZE)`) eliminaria a fonte de variação de memória, mas o perfil de seccomp padrão do Docker bloqueia essa chamada mesmo para root (`EPERM`, verificado); um perfil customizado é um risco de infraestrutura à parte, e não resolveria os casos de tempo no limiar.
- **Decisão**: substituir o candidato pelo próximo não tentado da mesma ordem determinística, com confirmação reforçada (6 execuções concordantes em vez de 2, depois de corrigir um bug em que a confirmação inicial só chegava a comparar 2 chamadas de fato; ver spec D18); `dataset.validation.repair`.

## R20 — Documentação de módulo e sincronização (Princípio XI)

- **Decisão**: cada pacote de `src/` tem `README.md` no formato de `docs/template-modulo.md`;
  a visão geral fica em `README.md` na raiz; a metodologia é sincronizada no mesmo ciclo de
  cada descoberta e tem histórico datado. A ajuda da CLI (`argparse`) e as docstrings apontam
  para o README e não o contradizem.
- **Rationale**: a metodologia será a base para atualizar o texto escrito do TCC; dados medidos
  aqui (R1, R15, R19) só valem se chegarem a ela. Um formato único torna a conformidade
  verificável por lista.
- **Alternativas**: documentar só em docstrings (não cobre visão de execução nem reprodução);
  um wiki externo (fora do repositório, dessincroniza do código).
