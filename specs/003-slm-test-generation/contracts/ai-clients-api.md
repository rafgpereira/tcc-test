# Contract: API interna do módulo `ai_clients` (SLM)

**Feature**: `003-slm-test-generation`. Assinaturas de referência para `/speckit-tasks` e para os
testes; nomes podem ser refinados na implementação sem mudar o comportamento.

## `ai_clients.ollama` — cliente sem estado

```python
@dataclass(frozen=True)
class GenerationOptions:          # enviados SEMPRE, todos, em "options"
    temperature: float; top_p: float; top_k: int; repeat_penalty: float
    num_ctx: int; num_predict: int; seed: int

@dataclass(frozen=True)
class Completion:
    content: str                   # message.content integral
    model: str; created_at: str; done_reason: str
    prompt_eval_count: int; eval_count: int
    total_duration_ns: int; load_duration_ns: int
    prompt_eval_duration_ns: int; eval_duration_ns: int

class OllamaUnavailable(Exception): ...   # infraestrutura: repetir a MESMA chamada (R9)
class OllamaConfigError(Exception): ...   # configuração: abortar, código 3
class ModelRepetition(Exception): ...     # HTTP 500 "token repeat limit reached": tentativa falha
                                          # com a razão `repetition`, próxima seed (R13)

class SLMClient(Protocol):
    def model_info(self, model: str) -> ModelInfo: ...        # digest, quantização, versão
    def complete(self, model: str, prompt: str, options: GenerationOptions) -> Completion: ...

class OllamaClient:                # implementação real, urllib, POST /api/chat, stream=false
    def __init__(self, base_url: str, *, timeout_s: float) -> None: ...
        # timeout_s = OLLAMA_HTTP_TIMEOUT_S do .env, ou config.DEFAULT_HTTP_TIMEOUT_S (900)
```

Invariantes (testadas com `FakeSLMClient` em `tests/ai_clients/fakes.py`):

- o corpo de toda requisição tem `messages` com **exatamente um** item (`role: user`), e nunca
  `context`, `system`, `format` ou `template`;
- o cliente não guarda nenhuma resposta nem prompt entre chamadas (sem atributo mutável além da
  configuração);
- `FakeSLMClient` recebe uma tabela `(problem_id, scenario, seed) → Completion | Exception`, grava
  cada requisição recebida e falha o teste se uma chamada não prevista acontecer.

## `ai_clients.prompt` — montador

```python
def load_template(path: Path = config.PROMPT_TEMPLATE_PATH) -> PromptTemplate: ...
    # valida que cada um dos 3 marcadores aparece exatamente 1 vez; guarda o sha256

def context_data(problem: ProblemInput, scenario: Scenario) -> str: ...
def build_prompt(template: PromptTemplate, problem: ProblemInput, scenario: Scenario) -> str: ...
```

Propriedades testadas: para um mesmo problema, os prompts dos 3 cenários só diferem dentro de
`<context_data>…</context_data>`; `hybrid` contém literalmente os conteúdos de `black_box` e
`white_box`; o few-shot é sempre `public_tests[0]`; nenhum dado de outro problema aparece.

## `ai_clients.parser` — interpretação

```python
def parse_response(raw: str) -> ParseResult: ...   # puro, determinístico, sem exceções
```

Tabela de casos mínima (`tests/ai_clients/test_parser.py`): resposta bem formada; texto antes/
depois/entre blocos; cada bloco ausente; cada bloco duplicado; ordem trocada; `<input>` vazio e só
espaços (descartado sozinho e contado; todos vazios → `only_empty_inputs`); texto não branco entre
`<input>`s; `<inputs>` sem `<input>`; bloco não fechado; `\r\n`; cerca Markdown em volta de todo o
`<reference_py>` (```` ```python ````/```` ```py ````/```` ``` ```` … ```` ``` ````: removida e
registrada) e qualquer outra cerca (mantida); entradas duplicadas (mantidas e contadas); `<`, `&` e
`</input>` dentro do código Python. (Cerca e entrada vazia revistas em 2026-10-04, research R13.)

## `ai_clients.oracle` — execução do `reference_py`

```python
PythonRunner = Callable[[str, bytes, ExecutionLimits, int], RunResult]   # (código, stdin, limites, slot)

def run_python(code: str, stdin: bytes, limits: ExecutionLimits, slot: int) -> RunResult: ...
    # prepare_slot_workdir -> main.py -> give_to_slot -> sandbox.runner.execute(
    #   [python3.11, "-I", "-B", "-X", "utf8", "main.py"], env={},
    #   rlimits=isolation.run_rlimits(limits), measured_by_launcher=True, ...)

def python_limits(metadata: Metadata) -> ExecutionLimits: ...    # tl × 10, ml × 4

def evaluate_attempt(
    generation: GenerationRecord, problem: ProblemInput, *, slot: int = 0,
    runner: PythonRunner = run_python,
) -> ExecutionRecord: ...
```

`evaluate_attempt` usa `sandbox.judge.judge_test` para todo veredito. `InfraError` do motor
propaga (nunca vira veredito nem falha de tentativa). Testes unitários injetam um `runner` falso
(sem processo); testes de integração (`@pytest.mark.integration`, serviço `sandbox`) usam o real
com programas Python conhecidos: correto, `SyntaxError`, laço infinito, estouro de memória, saída
não UTF-8, escrita em arquivo, tentativa de rede (falha), e uma solução que só erra uma das
entradas.

## `ai_clients.store` — estado em disco

```python
def combination_state(root: Path, problem_id: str, scenario: Scenario) -> State: ...
def write_generation(root: Path, record: GenerationRecord) -> None: ...   # falha se já existe
def write_execution(root: Path, record: ExecutionRecord) -> None: ...     # falha se já existe
def finalize(root: Path, problem_id: str, scenario: Scenario, run: RunConfig) -> SlmSuite | None: ...
@contextmanager
def exclusive_run(root: Path) -> Iterator[None]: ...
```

`finalize` é pura em relação aos arquivos (mesma entrada → mesmos bytes de `suite.json`) e é o único
lugar que grava `suite.json`.

## Desde 2026-10-06 (research R19)

```python
# ai_clients.config
@dataclass(frozen=True)
class AttemptSpec:  # R22: phase 1, 2 or 4; template "solution" or "prediction"
    attempt: int; phase: int; seed: int; temperature: float; template: str
ATTEMPT_POLICY: tuple[AttemptSpec, ...]   # the 15 rows of data-model §2, written out
def attempt_spec(attempt: int) -> AttemptSpec: ...
SOLUTION_ATTEMPTS = 12; MAX_ATTEMPTS = 15   # derived from ATTEMPT_POLICY
PREDICT_TEMPLATE_PATH = .../prompt_templates/slm_predict_prompt.txt
def attempt_kind(attempt: int) -> str: ...   # the template of the row: solution / prediction
# the old STRICT_ATTEMPTS, PREDICT_ATTEMPTS, SEED_BASE, seed_for and the
# OLLAMA_TEMPERATURE / OLLAMA_SEED_BASE overrides are removed (R22, item 11)
MANUAL_CLOSE_FILE = "manual_close.json"

# ai_clients.parser
def parse_prediction(raw: str) -> PredictionParse | UnparsedResponse: ...  # puro, nunca levanta

# ai_clients.store
State.kind: Literal["terminal", "pending_generation", "pending_execution", "finalizable",
                    "awaiting_manual"]
def write_manual_close(root: Path, record: ManualClose) -> Path: ...   # falha se já existe

# ai_clients.closing
def close(root: Path, problem_id: str, scenario: Scenario, reason: str, *, run: RunConfig,
          now: Callable[[], str]) -> SlmSuite: ...
    # NotAwaitingManual (código 2) se o estado não é awaiting_manual; grava manual_close.json e
    # depois chama finalize
```

O `generate` recebe os dois templates (`load_template()` e `load_template(PREDICT_TEMPLATE_PATH)`;
os mesmos 3 marcadores, a mesma `build_prompt`) e escolhe pelo `attempt_kind` da tentativa; o
parser também (`parse_response` ou `parse_prediction`). `GenerateResult` e `ExecuteResult` trocam
`fallback`/`discarded` por um contador por status de suíte e ganham `awaiting_manual:
list[tuple[str, str]]` (as combinações da seleção nesse estado ao fim, para as linhas `manual:`
e o código 4).

Tabela mínima de `tests/ai_clients/test_parser_prediction.py`: resposta bem formada; texto
fora dos blocos (contado); cada bloco ausente ou duplicado; ordem trocada; `<tests>` sem `<test>`;
texto entre `<test>`s; `<test>` sem `<input>` ou sem `<output>`, com os dois trocados, com dois
`<input>`, com texto solto dentro; `<test>` aninhado; entrada vazia e saída vazia (descartadas
sozinhas e contadas); todos vazios; entradas repetidas (mantidas e contadas); `\r\n`; `<` e `&`
dentro da saída.

## Desde 2026-10-06, política de 5 fases (research R22)

```python
# ai_clients.store
class IncompatibleRunError(Exception): ...   # run.json that is not schema_version 2 (code 2)
def read_run(root: Path) -> RunConfig: ...   # raises IncompatibleRunError for an older run

# ai_clients.generation
def generation_options(run: RunConfig, attempt: int) -> GenerationOptions: ...
    # seed and temperature of run.attempt_policy[attempt - 1]
```

Testes pedidos (R21) e onde ficam: `tests/ai_clients/test_config.py` (novo: a tabela exata, nenhum
par (seed, temperatura) repetido, as validações ao importar); `test_generation.py` /
`test_execution.py` (parada na primeira `accepted` na fase 1 e na fase 2, passagem para a reserva,
passagem direta para a predição, `awaiting_manual`, seed e temperatura enviadas em cada pedido);
`test_resume.py` (interrupção nas tentativas 3, 9 e 14); `test_resume_config.py` (uma linha da
tabela alterada recusa o `--resume`); `test_cli_*` (`run.json` de versão 1 recusado com código
2); `test_damage.py` (fase, seed, temperatura ou template divergentes); `test_parser_prediction.py`
(cerca em `<input>`/`<output>`); `test_report.py` (`acceptance` e `per_phase`).

## Desde 2026-10-07, execução concorrente (research R24)

```python
# ai_clients.store
@contextmanager
def shared_run(root: Path) -> Iterator[None]: ...       # LOCK_SH | LOCK_NB on .lock
@contextmanager
def exclusive_run(root: Path) -> Iterator[None]: ...    # LOCK_EX | LOCK_NB on .lock (unchanged)
@contextmanager
def single_execute(root: Path) -> Iterator[None]: ...   # LOCK_EX | LOCK_NB on .execute.lock
@contextmanager
def claim(root: Path, problem_id: str, scenario: str) -> Iterator[bool]: ...
    # LOCK_EX | LOCK_NB on .locks/<id>__<scenario>.lock; yields False (and holds nothing) if taken
```

`GenerateResult` e `ExecuteResult` ganham `skipped: int`. Testes em
`tests/ai_clients/test_concurrency.py` (R24, item 5).
