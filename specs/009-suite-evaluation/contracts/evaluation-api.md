# Contrato: funções de julgamento (`evaluation.judging`, `evaluation.sources`)

Funções puras sobre um motor injetável (`run(binary, stdin, limits, slot) -> RunResult`), para os
testes de unidade rodarem sem C++ (motor falso) e a integração com o motor real.

## `evaluation.sources`

| Função | Entrada | Saída | Regras |
|---|---|---|---|
| `final_suite(root, model, problem_id, scenario)` | | `SuiteToEvaluate` | modelo local: pasta pelo `provenance.json`; `discarded_manual` → sem suíte |
| `attempt_suite(root, problem_id, scenario, attempt)` | | `SuiteToEvaluate` | testes = entradas mantidas da tentativa com as saídas da solução (mesma regra de `ai_clients.store._build_suite`); tentativa de predição, inexistente ou sem entrada mantida → sem suíte com o motivo |
| `problem_targets(root, problem_id)` | | `ProblemTargets` | fontes do `AC_ref`, de `WA_1..100`, `Mutant_1..100`, e `ExecutionLimits` do `metadata.json` |

`SuiteToEvaluate`: `tests: tuple[Test, ...]`, `source: SuiteSource`, `no_suite_reason`.

## `evaluation.judging`

### `judge_ac(binary, tests, limits, slot, *, run) -> AcResult`

- Executa todos os testes, sem interromper (FR-004).
- Erro (TLE/MLE/RE) → repetição (R9); `unstable` quando uma repetição não é erro.
- `approved` ⇔ todos `passed`.
- `InfraError` propaga; nunca vira veredito.

### `judge_target(binary, tests, ac, limits, slot, *, run) -> TargetResult`

- `tests` na ordem da suíte; `ac` é o `AcResult` da mesma suíte.
- Para i = 0, 1, …: executa o teste i uma vez (com repetição se erro).
  - Oráculo declarado ainda não decidido: veredito final contra `tests[i].output`.
  - Oráculo corrigido ainda não decidido e `ac.tests[i].verdict != runtime_error`: veredito final
    contra `ac.tests[i].actual_output`.
  - Erro final decide os dois oráculos ainda abertos (o do corrigido só se o teste for válido nele).
- Para quando os dois oráculos decidiram ou os testes acabaram (R3).
- `tests_run` = testes executados; `unstable_tests` = índices instáveis.

### `evaluate_problem(problem_id, suites, targets, *, compile, run, slot) -> dict[(set, scenario), CombinationResult]`

- Compila o AC; falha de compilação do AC → `InfraError` (o AC foi validado no dataset; nunca é
  veredito).
- Para cada suíte com testes: `judge_ac`.
- Para cada alvo, na ordem `WA_1..WA_100`, `Mutant_1..Mutant_100`: compila uma vez; `CE` →
  `compiled=false` em todas as suítes; senão `judge_target` em cada suíte; apaga o binário.
- Suíte sem testes → `CombinationResult` com `has_suite=false`, sem executar nada.
- O resultado não depende do número de trabalhadores nem da ordem de término.
