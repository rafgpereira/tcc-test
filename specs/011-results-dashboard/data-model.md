# Data Model: Dashboard (011)

Nada é persistido. Estas são as estruturas em memória da camada de dados (`dashboard.data`),
derivadas dos arquivos da avaliação (`specs/009-suite-evaluation/data-model.md`).

## LoadedTree (resultado de `combinations(base)`)

| Campo | Tipo | Regra |
|---|---|---|
| `base` | caminho | a pasta lida (padrão `data/evaluation`) |
| `loaded_at` | data e hora | quando foi lida (FR-001a) |
| `table` | DataFrame `Combination` | uma linha por combinação concluída e válida |
| `invalid` | lista de (arquivo, motivo) | arquivos que não validam pelo esquema da avaliação |
| `closed` | mapa conjunto → nº de problemas concluídos | o que a tela mostra no topo |

## Combination (uma linha da tabela base)

As colunas são fixas, nesta ordem. São as mesmas da prévia do piloto, mais `macrocategoria`.

| Coluna | Origem | Observação |
|---|---|---|
| `set`, `model`, `problem`, `scenario` | resultado | chave única: (`set`, `problem`, `scenario`) |
| `macrocategoria` | `metadata.json` | `matematica` \| `estrutural_otimizacao` \| `logica_direta`; vazio se o dataset não estiver descompactado |
| `status`, `tree`, `attempt` | `suite_source` | |
| `has_suite`, `no_suite_reason`, `suite_size` | resultado | |
| `ac_approved` | `ac.approved` | vazio sem suíte |
| `ac_wrong_output`, `ac_runtime_error`, `ac_unstable` | contagens em `ac.tests` | |
| `n_wa`, `n_mutants` | contagens em `targets` | |
| `wa_declared`, `wa_corrected`, `mutants_declared`, `mutants_corrected` | tamanhos de `detected` | |
| `target_unstable`, `not_compiled` | contagens em `targets` | |
| `elapsed_s` | resultado | tempo de executar os testes (sem a compilação) |

**Prévia** (sempre rotulada assim na tela, FR-004): `wa_pct_declared = wa_declared / n_wa`, e o
mesmo para o oráculo corrigido e para os mutantes. Na agregação, a razão é feita das somas
(Σ detectados / Σ total), nunca média de porcentagens. As combinações sem suíte ficam fora.

## TestRow (detalhe de uma combinação, `combination_tests`)

| Campo | Origem |
|---|---|
| `index` | `ac.tests[i].index` |
| `input`, `expected` | suíte (R5) |
| `actual` | `ac.tests[i].actual_output` |
| `ac_verdict`, `error_kind`, `unstable` | `ac.tests[i]` |
| `wa_declared_here`, `wa_corrected_here`, `mut_declared_here`, `mut_corrected_here` | quantos alvos têm `test_index == i` em cada oráculo |

Junto vem `suite_changed: bool`: o hash do arquivo da suíte lido difere de `suite_sha256`.

## TargetDetail (`target_detail`)

| Campo | Origem |
|---|---|
| `target`, `kind`, `compiled`, `declared`, `corrected`, `tests_run`, `unstable_tests` | `targets[...]` |
| `source`, `ac_source` | arquivos do dataset e dos mutantes; `None` se ausentes (aviso na tela) |
| `diff_html` | `difflib.HtmlDiff` de `ac_source` × `source` (R6) |

## Filtros (estado da tela, não persistido)

`sets`, `scenarios`, `problems`, `macrocategorias`, `statuses`: listas de valores permitidos. Uma
lista vazia não filtra nada. São aplicados à tabela base antes de qualquer agregação.
