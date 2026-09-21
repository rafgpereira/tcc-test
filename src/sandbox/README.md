# Módulo `sandbox` (motor de execução)

> **Status**: em implementação · **Feature**:
> `specs/001-dataset-extraction/` · **Metodologia**: `docs/metodologia-referencia.md`, seções 1.4 e 4

## (a) Propósito

Compila e executa código C++ de terceiros em isolamento, sob limites de tempo, memória e pilha lidos dos metadados de cada problema, e atribui um veredito (`AC`, `WA`, `TLE`, `MLE`, `RE` ou `CE`).

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
(baixar o projeto, criar o `.env`, criar `data/`, construir a imagem e conferir com o `pytest`).
Tudo aqui roda no serviço **`sandbox`** do Docker Compose, que **não tem internet** de propósito e
é o único autorizado a compilar e executar código C++ de terceiros.

> **Depois de um `git pull` que altere o `Dockerfile`** (por exemplo, quando o lançador
> `sandbox-launch` foi acrescentado) rode `docker compose build` de novo; sem isso o motor não
> encontra o lançador e os comandos abaixo terminam com `infrastructure failure`.

### O que este módulo faz, na prática

É uma biblioteca Python (`src/sandbox/`), sem comando próprio: quem o usa é o módulo
[`dataset`](../dataset/README.md) (para validar os códigos do dataset) e, no futuro, a etapa de
avaliação, sem alteração. Para cada programa ele: grava o código-fonte num diretório privado do
"slot" (um trabalhador), compila com as flags do juiz original e uma cascata de padrões
(`gnu++20`, `gnu++17`, `gnu++14`, `gnu++11`), roda cada teste como um usuário sem privilégios (um
`uid` por slot, sem rede, sem capabilities), com os limites do problema, e dá o veredito do
**primeiro teste que falhar**. Falha do próprio ambiente nunca vira veredito: vira um erro de
infraestrutura (`InfraError`).

### Passo a passo

1. **Conferir o motor (`selfcheck`).** Roda 9 programas de veredito conhecido (um `AC`, um `WA`,
   um `TLE`, um `MLE`, um `RE`, um `CE`, uma recursão profunda que só passa com a pilha de 256 MiB,
   um que só compila em `gnu++14` e um estável), cada um duas vezes, e compara o veredito obtido
   com o esperado:

   ```bash
   docker compose run --rm sandbox python -m dataset selfcheck
   ```

   Leva cerca de 7 segundos. Esperado: uma linha `ok   <caso>: expected X, obtained X` por caso,
   a última linha `selfcheck OK: 9/9 cases` e código de saída `0` (`echo $?`). É também o portão de
   entrada do `validate`, quando ele existir: se falhar, nenhum código real é validado.

2. **Rodar os testes do motor.** Unidades e integração (compilam e executam C++ de verdade,
   inclusive testes de isolamento, fork bomb e limites):

   ```bash
   docker compose run --rm sandbox pytest tests/sandbox
   ```

   Esperado: a última linha diz `passed` e não menciona `failed`.

### Se algo der errado

| O que aparece | O que significa | O que fazer |
|---|---|---|
| `infrastructure failure: cannot prepare the workdir /sandbox/slot0: Read-only file system` (código `3`) | você rodou no serviço `app`, que não tem o motor | use `docker compose run --rm sandbox ...` |
| `infrastructure failure: ... sandbox-launch ...` (código `3`) | a imagem não tem o lançador | `docker compose build` |
| `infrastructure failure: cannot start ...: ... Operation not permitted` (código `3`) | o contêiner não tem as capabilities `SETUID`, `SETGID`, `KILL`, `CHOWN` e `DAC_OVERRIDE` (Docker rootless, por exemplo) | use o Docker Engine com o `docker-compose.yml` do projeto |
| uma linha `FAIL` no `selfcheck` (código `1`) | o motor deu um veredito diferente do esperado, ou vereditos diferentes em duas execuções | não valide nada; avise os autores com a saída completa |

### API para quem usa o motor

Resumo; o contrato completo está em
[engine-api.md](../../specs/001-dataset-extraction/contracts/engine-api.md).

| Função | Para que serve |
|---|---|
| `compile_cpp(source, workdir, slot)` | compila em `gnu++20` e recua até `gnu++11`; devolve o binário ou os quatro diagnósticos |
| `run_binary(binary, stdin, limits, slot)` | executa uma vez, com os limites, e devolve status, saída, tempo de CPU e pico de memória |
| `judge_test(run, expected, limits)` | veredito de uma execução (`TLE`, `MLE`, `RE`, `AC` ou `WA`) |
| `run_suite(binary, tests, limits, slot)` | roda os testes em ordem; o primeiro que não é `AC` decide e interrompe |
| `judge_source(source, tests, limits, slot, workdir)` | compila e roda a suíte; falha de compilação em todos os padrões é `CE` |
| `outputs_equal(expected, actual)` | a **única** regra de comparação de saída do projeto |
| `prepare_slot_workdir(slot)` | cria o diretório privado do slot onde se compila e se executa |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| Código-fonte C++ | `str` com o arquivo inteiro | quem chama (o `dataset` lê de `data/work/staging/raw/`) |
| Testes | sequência de `Test(input, output)`, na ordem de execução (públicos, privados, gerados) | quem chama |
| Limites | `ExecutionLimits(time_limit_seconds, memory_limit_bytes, stack_limit_bytes)`; tempo e memória sem valor padrão | metadados do problema (`time_limit`, `memory_limit_bytes`) |
| Slot | inteiro de 0 a 999 (uid `10000 + slot`) | quem chama (um por trabalhador) |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| `CompileResult` | `ok`, `binary`, `standard_used` e `attempts` (um diagnóstico por padrão tentado) | quem chama |
| `RunResult` | `status`, `exit_code`, `signal`, `stdout`, cauda do `stderr`, tempo de CPU e de parede, pico de memória | quem chama |
| `SuiteVerdict` | `verdict`, padrão usado, índice do teste decisivo, quantos testes rodaram, maiores tempo e memória e o primeiro teste que falhou | quem chama; o `dataset` grava em `validacao.json` |
| `Verdict` | `AC`, `WA`, `TLE`, `MLE`, `RE` ou `CE`; **não existe** veredito de infraestrutura | idem |
| `InfraError` | exceção para falha do ambiente (fork, disco cheio, compilador ou lançador ausente, isolamento) | quem chama decide repetir; nunca vira veredito |

O módulo só escreve dentro do diretório do slot, em `/sandbox/slot<N>` (`tmpfs`); não cria arquivos
no repositório.

## (e) Dependências e pré-requisitos

- GCC 13.2.0 e Python 3.11.16, na imagem única do projeto (`docker compose build`); o lançador
  `sandbox-launch` (`src/sandbox/launcher/launcher.cpp`) é compilado nessa imagem.
- Serviço `sandbox` do Docker Compose: **sem rede**, raiz somente leitura, `root` só com as
  capabilities `CHOWN`, `DAC_OVERRIDE`, `SETUID`, `SETGID` e `KILL`, `init: true`, e `tmpfs` em
  `/sandbox` (com `exec`, senão o binário compilado não executa), `/tmp` e `/dev/shm` (estes dois
  privados, `0700`).
- Nenhum módulo anterior precisa ter rodado; nenhuma variável de ambiente é necessária
  (`SANDBOX_ROOT` e `SANDBOX_LAUNCHER` existem só para testes).

## (f) Limitações conhecidas

- **Memória por espaço de endereçamento** (`RLIMIT_AS`), que não é idêntico à métrica do juiz
  original; pode haver `MLE` espúrio em programas que reservam muito espaço virtual, e ele
  apareceria como triagem de AC, não em silêncio (decisão D13, regra 6).
- **`MLE` e `RE` por `abort()`** não se distinguem só pelo sinal: o motor procura `bad_alloc` no
  `stderr`. Um programa que trata a falha de alocação e sai com erro é `RE`.
- **Comparação de saída** ignora só espaços no fim das linhas e linhas em branco no fim do
  arquivo (decisão D13, regra 2); e o **tempo** é de CPU do processo, não de parede (regra 5). As
  duas são as candidatas a reabertura pelo critério do piloto (metodologia, seção 1.4).
- **Precisa das cinco capabilities** listadas em (e); Docker rootless não funciona. O `selfcheck`
  falha de forma explícita nesse caso.
- Um programa cria no máximo **30 processos filhos** (o limite de 32 conta o lançador e o próprio
  programa). O pico de memória vale `0` quando o programa estoura a reserva de tempo de parede (o
  veredito é `TLE` de qualquer forma).
- Processos que saem da sessão do programa (`setsid`) só são mortos, por uid, quando o grupo morto
  ainda tinha sobreviventes.
- O limite de pilha é de 256 MiB e é aplicado em tempo de execução, não na compilação
  (metodologia, seção 1.4).

## Referências

- Contratos: [engine-api.md](../../specs/001-dataset-extraction/contracts/engine-api.md)
- Decisões: D7, D13 e D16 em [spec.md](../../specs/001-dataset-extraction/spec.md); pesquisa R4 a R11
  em [research.md](../../specs/001-dataset-extraction/research.md)
- Testes: `tests/sandbox/` (`docker compose run --rm sandbox pytest tests/sandbox`)

## Comandos verificados

| Comando | Verificado em | Revisão | Tarefa |
|---|---|---|---|
| `selfcheck` | pendente | — | — |
| `pytest tests/sandbox` | pendente | — | — |
