# Contract: API pública do motor de execução (`src/sandbox/`)

**Feature**: `001-dataset-extraction` | Requisitos: FR-008, FR-009, FR-009a, FR-010, FR-010a,
FR-010b | Decisão: D7 (motor único, reutilizado sem alteração pelo módulo de avaliação).

O motor é a fundação compartilhada de "compilar e executar código C++ sob limites e atribuir
veredito". Ele é usado agora por `dataset.validation` e será usado, sem alteração, pelo módulo
de avaliação e pelo oráculo do SLM. Ele **não** conhece dataset, IA, mutantes nem métricas
(Princípio IX): a regra de "como usar o veredito" pertence a quem chama.

Assinaturas descritas em alto nível; os tipos são modelos Pydantic ou `dataclass` imutáveis
definidos em `sandbox/types.py`.

## Tipos

| Tipo | Campos | Notas |
|---|---|---|
| `ExecutionLimits` | `time_limit_seconds: float`, `memory_limit_bytes: int`, `stack_limit_bytes: int = STACK_LIMIT_BYTES` | Tempo e memória vêm sempre dos metadados do problema; nenhum valor padrão para eles. |
| `CompileResult` | `ok: bool`, `binary: Path \| None`, `standard_used: str \| None`, `attempts: list[CompileAttempt]` | `attempts` guarda o diagnóstico de cada padrão tentado. |
| `RunResult` | `status: RunStatus`, `exit_code: int \| None`, `signal: int \| None`, `stdout: bytes`, `stderr_tail: bytes`, `cpu_time_s: float`, `wall_time_s: float`, `peak_rss_bytes: int` | `RunStatus`: `OK`, `TIMEOUT`, `SIGNALED`, `NONZERO_EXIT`, `OUTPUT_LIMIT`. |
| `Verdict` | enum `AC, WA, TLE, MLE, RE, CE` | Ver [data-model.md](../data-model.md) §1.4. |
| `TestVerdict` | `verdict`, `run: RunResult`, `expected`, `actual` | Resultado de um teste. |
| `SuiteVerdict` | `verdict`, `standard_used`, `deciding_index: int \| None`, `tests_run: int`, `max_cpu_time_s`, `max_memory_bytes`, `first_failure: TestVerdict \| None` | Resultado de um programa sobre uma suíte ordenada. |

Exceção `InfraError` (única forma de expressar falha de infraestrutura, FR-010): falha de
`fork`, `tmpfs` cheio, compilador ausente, erro ao aplicar isolamento, morte inesperada do
lançador. **Nunca** vira `TLE/MLE/RE`.

## Funções

| Função | Contrato |
|---|---|
| `compile_cpp(source: str, workdir: Path, slot: int) -> CompileResult` | Grava a fonte, compila com as flags do juiz (sem `-Wl,--stack`) na cascata `gnu++20 → gnu++17 → gnu++14 → gnu++11`, parando no primeiro sucesso. O compilador roda como o uid do `slot`, sem rede, com limites de tempo e memória próprios do compilador. Falhou em todos ⇒ `ok=False` com os quatro diagnósticos. |
| `run_binary(binary: Path, stdin: bytes, limits: ExecutionLimits, slot: int) -> RunResult` | Executa em novo processo como o uid do `slot`, com `RLIMIT_STACK = stack_limit_bytes`, `RLIMIT_AS = memory_limit_bytes`, `RLIMIT_CPU` de reserva, `RLIMIT_NPROC`, `RLIMIT_CORE = 0`, `RLIMIT_FSIZE` pequeno, sessão própria, diretório de trabalho privado, entrada por `stdin` e saída capturada com teto. Mede tempo de CPU por `wait4`. |
| `judge_test(run: RunResult, expected: str, limits: ExecutionLimits) -> Verdict` | Regra única de veredito por teste: `TLE` se CPU `> limite` ou estouro do tempo de parede; `MLE` se assinatura de `bad_alloc` no `stderr` com `SIGABRT` ou pico de memória `>= limite`; `RE` para sinal ou saída não zero; senão compara saídas: iguais ⇒ `AC`, diferentes ⇒ `WA`. |
| `outputs_equal(expected: str, actual: str) -> bool` | Iguais após ignorar espaços em branco no fim de cada linha e linhas vazias/espaços no fim do arquivo (única regra de comparação do projeto). |
| `run_suite(binary, tests: Sequence[Test], limits, slot) -> SuiteVerdict` | Executa os testes na ordem dada; o **primeiro** teste que não terminar em `AC` decide o veredito (FR-012) e interrompe a suíte (curto-circuito). Todos `AC` ⇒ `AC`. |
| `judge_source(source, tests, limits, slot, workdir) -> SuiteVerdict` | Atalho: `compile_cpp` + `run_suite`; erro de compilação ⇒ `CE`. |
| `stack_limit_bytes_to_kib(n: int) -> int` | Conversão explícita bytes → KiB, com verificação de múltiplo de 1024. `stack_limit_bytes_to_kib(268435456) == 262144`. |
| `selfcheck() -> SelfCheckReport` | Executa a suíte de programas de veredito conhecido embarcada em `sandbox/selfcheck/` (FR-010a). |

## Garantias (cobertas por testes, Princípio VI)

1. **Unidades do limite de pilha**: `STACK_LIMIT_BYTES == 268_435_456`; `setrlimit` recebe
   **bytes**; o equivalente do shell `ulimit -s` é **262 144 KiB**; a conversão é uma função
   única testada nos dois sentidos, e um teste de integração lê o limite efetivo do processo
   filho em `/proc/self/limits` e roda uma recursão de ~150 MB que deve passar.
2. Nenhum limite de tempo ou memória de problema tem valor padrão ou constante no código.
3. O código de terceiros nunca roda como o usuário do orquestrador nem com capabilities, e não
   consegue listar, ler nem escrever `data/work/` (permissão `0700`, D15).
4. Duas execuções do mesmo programa e das mesmas entradas no mesmo ambiente produzem o mesmo
   veredito (a suíte de veredito conhecido repete cada caso).
5. Falha de infraestrutura levanta `InfraError`; nunca produz veredito.
6. O motor não escreve fora do `workdir` do `slot`.

## Fora do contrato (fica para módulos futuros)

Injeção de suítes geradas por IA, avaliação com curto-circuito sobre mutantes e WAs,
orquestração do oráculo do SLM e exportação de CSV. Esses módulos chamam as funções acima.
