# Data Model: Métricas (010)

Todas as tabelas são CSV com colunas fixas, nesta ordem, validadas ao gravar e ao ler. Os
conjuntos e cenários aparecem sempre na ordem `slm, gpt, gemini, claude, slm-attempt1` e
`black_box, white_box, hybrid`. Todas as métricas das tabelas estão em **porcentagem** (o MS também: DM ÷ M × 100, mantendo a fórmula
da metodologia), com 4 casas decimais.

## `per_problem.csv` (base de tudo)

`set, scenario, problem, macrocategoria, status, has_suite, suite_size, ac_rejected,
ac_wrong_output_tests, ac_runtime_error_tests, n_wa, n_mutants, wa_declared, wa_corrected,
mutants_declared, mutants_corrected`

Uma linha por conjunto × cenário × problema (3.000). Sem suíte: `has_suite=false`, contagens 0,
`n_wa = 100` e `n_mutants = 100` (contam 0% em TDF e MS, B.1).

## `detected_wa.csv`

`set, scenario, problem, target, oracle` (`declared` | `corrected`): os WAs detectados, um por
linha (base do IIC).

## `metrics.csv`

`set, scenario, cut, cut_value, problems, TC, TDF, MS, WA_killed, WA_killed_star, WA_total,
mutants_killed, mutants_killed_star, mutants_total, TFP, TFP_with_suite, without_suite,
TDF_star, MS_star, delta_TDF, delta_MS, TFP_test, FP_tests_oracle, FP_tests_invalid_input,
total_tests, mean_suite_size, density_TDF`

- `cut` ∈ `all` | `macrocategoria` | `status`, e `cut_value` é o valor do corte (vazio em `all`);
- `WA_killed`/`mutants_killed` (oráculo declarado) e `*_star` (corrigido): soma, nos problemas do
  corte, dos alvos mortos (cada alvo conta uma vez); `WA_total`/`mutants_total` = 100 × problemas;
  `problems` é o número de problemas do corte.
- TDF = média de `wa_declared / n_wa × 100`; MS = média de `mutants_declared / n_mutants`
  (× 100 na tabela); os `_star` usam os campos `corrected`.
- TFP = `Σ ac_rejected / problemas × 100` (N = problemas do corte); TFP_with_suite = o mesmo só
  sobre `has_suite`.
- TFP_test = `(FP_tests_oracle + FP_tests_invalid_input) / total_tests × 100`.
- density_TDF = `TDF / mean_suite_size` (só combinações com suíte).

## `iic.csv`

`set, oracle, direction, iic_pooled, gains, losses, base_size, per_problem_median, per_problem_q1,
per_problem_q3, positive, negative, zero, excluded`

`direction` ∈ `cod` (híbrido sobre caixa-preta) | `req` (híbrido sobre caixa-branca); `oracle` ∈
`declared` | `corrected`; `excluded` = problemas com denominador zero (fora da visão por problema).

## `stats.csv`

`family, metric, scope, group_a, group_b, test, statistic, p_value, p_adjusted, significant,
a12, cliff_delta, n_pairs`

- `family` ∈ `scenarios` (dentro de um conjunto) | `models` (dentro de um cenário) |
  `attempt1` (`slm-attempt1` × cada outro, dentro de um cenário).
- Linha global (Friedman): `group_a = group_b = "*"`, `test = friedman`.
- `test` ∈ `friedman` | `wilcoxon` | `mcnemar_exact`; `p_adjusted` por Holm dentro da família ×
  métrica × escopo; `a12`/`cliff_delta` só nas linhas par a par.

## `cost.csv`

`set, scenario, cost_usd, input_tokens, output_tokens, duration_s, cpd_wa_declared,
cpd_wa_corrected, cpd_mutants_declared, cpd_mutants_corrected`

`cost_usd` e os `cpd_*` vazios nos conjuntos do modelo local (nunca convertidos para US$).

## `run.json`

`schema_version, alpha, evaluation_manifests` (conjunto → SHA-256 do manifesto),
`dataset_manifest_sha256`, `generation_reports` (modelo → SHA-256).

## Figura

Nome `<figura>[__<filtro>-<valor>...].{png,svg,pdf}` (no pacote, só PNG e SVG das figuras sem filtro); subtítulo: `filtros: …  ·  fonte: data/metrics
(avaliação <hash curto dos manifestos>)`.
