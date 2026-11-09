# Data Model: Avaliação das suítes (009)

Esquemas Pydantic em `src/evaluation/schemas/` (`extra="forbid"`, como os demais módulos), todos
com `schema_version`. Nomes de campo em inglês (convenção do código); valores de enumeração entre
crases.

## Layout em disco

```text
data/evaluation/
├── .lock                         # trava exclusiva de uma execução (fora do pacote)
└── <set>/                        # slm | gpt | gemini | claude | slm-attempt1
    ├── run.json                  # RunConfig (R8)
    ├── building/<problem_id>/    # em gravação; apagado e refeito na retomada (fora do pacote)
    ├── problems/<problem_id>/
    │   ├── black_box.json        # CombinationResult
    │   ├── white_box.json
    │   └── hybrid.json
    └── results.csv               # gerado por `report` (R6)
```

## RunConfig (`run.json`)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `1` | |
| `set` | `slm` \| `gpt` \| `gemini` \| `claude` \| `slm-attempt1` | |
| `model` | `slm` \| `gpt` \| `gemini` \| `claude` | `slm` para `slm-attempt1` |
| `attempt` | int ≥ 1 \| null | só em `slm-attempt1` (= 1) |
| `dataset_manifest_sha256`, `dataset_revision` | str (64 hex), int | do manifesto vigente |
| `mutants_manifest_sha256` | str | |
| `suites_manifest_sha256` | str | do manifesto de suítes do modelo |
| `gcc_version` | str | |
| `error_runs` | `3` | R9 |
| `created_at` | str ISO-8601 | |

A retomada compara todos os campos menos `created_at`; qualquer diferença recusa o `run`.

## CombinationResult (`<scenario>.json`)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | `1` | |
| `set`, `model`, `problem_id`, `scenario` | | `problem_id` no padrão do dataset |
| `suite_source` | `SuiteSource` | proveniência (FR-013) |
| `has_suite` | bool | `false` = "sem suíte" (FR-010) |
| `no_suite_reason` | `discarded_manual` \| `attempt_without_tests` \| `prediction_attempt` \| `attempt_missing` \| null | não nulo ⇔ `has_suite = false` |
| `suite_size` | int ≥ 0 | 0 ⇔ sem suíte |
| `ac` | `AcResult` \| null | null ⇔ sem suíte |
| `corrected_oracle_tests` | int ≥ 0 | testes válidos no oráculo corrigido (AC sem erro final) |
| `corrected_oracle_excluded` | int ≥ 0 | `suite_size − corrected_oracle_tests` |
| `targets` | list[`TargetResult`] | 200 itens (`WA_1`..`WA_100`, `Mutant_1`..`Mutant_100`) se há suíte; vazia se não |
| `detected` | `DetectedSets` | derivado de `targets`; validado contra eles |
| `elapsed_s` | float | tempo de parede gasto executando os testes da combinação (a compilação é feita uma vez por problema, para todas as suítes, e não entra; o `run` imprime o tempo total de cada problema) |

### SuiteSource

| Campo | Tipo | Regra |
|---|---|---|
| `status` | `accepted` \| `accepted_fallback` \| `accepted_predicted` \| `accepted_barred` \| `discarded_manual` \| null | copiado do `suite.json`; null em tentativa isolada |
| `tree` | str | `suites/slm`, `suites/slm-rev1`, `suites/gpt`, … |
| `attempt` | int \| null | tentativa avaliada (só `slm-attempt1`) |
| `suite_sha256` | str \| null | SHA-256 do arquivo lido (`suite.json` ou as duas tentativas) |

### AcResult

| Campo | Tipo | Regra |
|---|---|---|
| `approved` | bool | ⇔ todos os `tests[i].verdict == passed` (FR-005) |
| `tests` | list[`AcTest`] | um por teste da suíte, na ordem (FR-004) |
| `standard_used` | str | padrão C++ da compilação |

### AcTest

| Campo | Tipo | Regra |
|---|---|---|
| `index` | int ≥ 0 | posição na suíte |
| `verdict` | `passed` \| `wrong_output` \| `runtime_error` | final, depois das repetições |
| `error_kind` | `RE` \| `TLE` \| `MLE` \| null | não nulo ⇔ `runtime_error` |
| `actual_output` | str | stdout da execução que decidiu; vazio em `runtime_error` |
| `cpu_time_s`, `peak_memory_bytes` | float, int | da execução que decidiu |
| `unstable` | bool | o primeiro resultado foi erro e uma repetição não foi |
| `runs` | list[`RunOutcome`] \| null | exatamente 3 itens quando a 1ª execução deu erro (as 2 repetições são sempre feitas); null quando não houve repetição (R9) |

### TargetResult

| Campo | Tipo | Regra |
|---|---|---|
| `target` | str | `WA_<n>` ou `Mutant_<n>` |
| `kind` | `wa` \| `mutant` | |
| `compiled` | bool | `false` = `CE`, nunca detectado, anomalia no relatório |
| `declared` | `Detection` | oráculo declarado (FR-007) |
| `corrected` | `Detection` | oráculo corrigido (FR-008) |
| `tests_run` | int | testes executados na passada única (R3) |
| `unstable_tests` | list[int] | índices em que um erro não se repetiu (FR-006a) |

### Detection

| Campo | Tipo | Regra |
|---|---|---|
| `detected` | bool | |
| `test_index` | int \| null | não nulo ⇔ `detected` |
| `verdict` | `wrong_output` \| `RE` \| `TLE` \| `MLE` \| null | não nulo ⇔ `detected` |

### DetectedSets

`declared_wa`, `declared_mutants`, `corrected_wa`, `corrected_mutants`: listas ordenadas de
identificadores (FR-009). Validadas contra `targets` ao carregar.

### RunOutcome

`verdict` (`passed` \| `wrong_output` \| `RE` \| `TLE` \| `MLE`), `cpu_time_s`,
`peak_memory_bytes`.

## Regras de transição de um teste (AC e alvos)

```text
execução 1 → passed / wrong_output → final (sem repetição, runs = null)
execução 1 → RE|TLE|MLE → executa SEMPRE as execuções 2 e 3 (runs = as 3)
    alguma das 2 e 3 sem erro → final = a primeira delas sem erro, unstable = true
    2 e 3 com erro            → final = erro, com o tipo da execução 1
```

Para um alvo, o oráculo corrigido só olha os testes em que o veredito final do AC não é
`runtime_error`; a saída esperada é `AcTest.actual_output`.

## Tabela consolidada (`results.csv`)

Uma linha por combinação × alvo; combinação sem suíte gera uma linha só, com `target` vazio.
Colunas fixas, nesta ordem:

`set, model, problem_id, scenario, suite_status, has_suite, suite_size, ac_approved,
ac_wrong_output_tests, ac_runtime_error_tests, ac_unstable_tests, corrected_oracle_tests, target,
kind, compiled, declared_detected, declared_test_index, declared_verdict, corrected_detected,
corrected_test_index, corrected_verdict, tests_run`

## EvaluationReport (`manifests/evaluation_<set>_report.json`)

Contagens do conjunto (FR-017): combinações avaliadas e sem suíte (por motivo); AC aprovado e
reprovado; testes do AC por veredito final e por tipo de erro; testes instáveis do AC e dos alvos;
WAs e mutantes detectados por oráculo; testes excluídos do oráculo corrigido; alvos com `CE`;
maior `actual_output` em bytes; tempo total; versão do esquema e hash do `run.json`.

## Manifesto (`manifests/evaluation_<set>.manifest.json`)

Mesmo formato dos manifestos de mutantes: SHA-256 e tamanho de cada arquivo do pacote (prefixo
`evaluation/<set>/`), mais o SHA-256 do zip.
