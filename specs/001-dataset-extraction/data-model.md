# Data Model: Extração, Validação e Persistência do Dataset

**Feature**: `001-dataset-extraction` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Todos os modelos abaixo são classes Pydantic (Constitution, Princípio IV), com o campo
`schema_version` (inteiro, começa em `1`). Mudar um schema exige incrementar `schema_version`,
registrar a decisão e migrar/regenerar os dados; nunca é efeito colateral de outra alteração.

Convenções de nomenclatura dos arquivos JSON:

- Chaves definidas pela metodologia (`metadata.json`) são mantidas exatamente como na
  metodologia, inclusive as em português (`macrocategoria`, `dataset_split_origem`,
  `num_wa_validados`, `num_wa_brutos_disponiveis`).
- Chaves dos arquivos novos (`validacao.json`, manifesto, relatório, pool) são `snake_case` em
  inglês, e os valores enumerados também (`complete`, `pending_triage`, `discarded`), salvo os
  valores de `macrocategoria`, fixados pela metodologia (`matematica`,
  `estrutural_otimizacao`, `logica_direta`).
- Identificador do problema: `problem_id = "<cf_contest_id>_<cf_index>"` (ex.: `1101_A`). É
  também o nome da pasta.

## 1. Entidades persistidas no dataset (dentro do `dataset.zip`)

Raiz do pacote: `dataset/`. Só problemas com `status == "complete"` entram no pacote.

```text
dataset/
└── problems/
    └── <problem_id>/
        ├── enunciado.md
        ├── AC_ref.cpp
        ├── WA_1.cpp … WA_100.cpp
        ├── testes.json
        ├── metadata.json
        └── validacao.json
```

### 1.1 `Metadata` (`metadata.json`) — FR-021

| Campo | Tipo | Regra de validação |
|---|---|---|
| `schema_version` | int | `== 1` |
| `problem_id` | str | `^\d+_[A-Za-z0-9]+$`; igual à pasta |
| `cf_contest_id` | int | `> 0` |
| `cf_index` | str | não vazio |
| `name` | str | não vazio |
| `source` | `"CODEFORCES"` | literal (único valor elegível) |
| `cf_rating` | int | `1000 <= x <= 1600` |
| `cf_points` | float | `>= 0` (o dataset traz `float32`; a metodologia ilustra com inteiro) |
| `cf_tags` | list[str] | ordenada alfabeticamente ao gravar (determinismo, FR-007) |
| `macrocategoria` | enum | `matematica` \| `estrutural_otimizacao` \| `logica_direta`; MUST ser igual a `classify(cf_tags)` |
| `time_limit_seconds` | float | `> 0`; `seconds + nanos/1e9` |
| `memory_limit_bytes` | int | `> 0` |
| `is_description_translated` | bool | `== false` (critério de elegibilidade) |
| `dataset_split_origem` | enum | `train` \| `valid` \| `test` |
| `num_wa_brutos_disponiveis` | int | `>= 100` (D4); contagem antes da remoção de duplicatas |
| `num_wa_validados` | int | `== 100` |
| `extraction_timestamp` | str | ISO 8601 UTC; gravado uma única vez e preservado (D3) |

### 1.2 `Testes` (`testes.json`) — FR-020

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | int | `== 1` |
| `problem_id` | str | igual à pasta |
| `public_tests` | list[`TestCase`] | ordem original do dataset |
| `private_tests` | list[`TestCase`] | ordem original do dataset |
| `generated_tests` | list[`TestCase`] | ordem original do dataset (D1) |

`TestCase = { "input": str, "output": str }`. Regra: em cada grupo, o dataset traz `input` e
`output` como listas paralelas; o validador MUST rejeitar grupos com tamanhos diferentes. A
ordem de execução da suíte é `public_tests` → `private_tests` → `generated_tests` (FR-012).
Pelo menos um teste no total; grupos podem ser vazios individualmente.

### 1.3 `Validacao` (`validacao.json`) — FR-011b, FR-021a

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | int | `== 1` |
| `problem_id` | str | igual à pasta |
| `status` | enum | `complete` \| `pending_triage` \| `discarded` |
| `engine` | `EngineInfo` | configuração exata do motor usada (ver abaixo) |
| `ac_ref` | `CodeValidation` \| null | presente se o AC chegou a ser executado |
| `wa` | list[`WaValidation`] | `len == 100` se `complete`; vazio caso contrário |
| `discard_reason` | enum \| null | obrigatório se `discarded`: `insufficient_wa` \| `insufficient_raw_wa` |
| `triage` | `TriageRecord` \| null | obrigatório se `pending_triage`; proibido caso contrário |

`EngineInfo`: `gcc_version` (str), `flags` (list[str], sem `-std`), `standard_cascade`
(list[str]), `stack_limit_bytes` (int), `time_limit_seconds` (float), `memory_limit_bytes`
(int), `stability_runs` (int).

`CodeValidation`: `file` (str, nome do arquivo), `sha256` (str), `verdict` (enum `Verdict`),
`standard_used` (str \| null), `max_cpu_time_s` (float), `max_memory_bytes` (int),
`tests_run` (int).

`WaValidation` estende `CodeValidation` com: `source_index` (int, posição na lista
`incorrect_solutions` do dataset), `deciding_test` (`{group, index}`, o primeiro teste que não
terminou com sucesso), `stable` (bool, sempre `true` em WA retido).

Invariantes (validadas a cada gravação, FR-022):

- `status == complete` ⇒ `ac_ref.verdict == AC` e `wa[i].verdict == WA` para todo `i`, os 100
  `sha256` são distintos entre si (duplicatas de texto contam uma vez).
- `wa[i].file == "WA_{i+1}.cpp"`.
- `status == pending_triage` ⇒ `triage != null`.

`TriageRecord` (FR-011b): `problem_id`, `stage` (`selection` \| `audit`), `verdict` (enum
`Verdict` \| `"AUDIT_MISMATCH"`), `reason` (str legível), `divergence`
(`{group, index, input, expected, actual, truncated}` \| null), `engine_diagnostic`
(str \| null; ex.: saída do compilador). Campos de texto longos são truncados em 64 KiB com
`truncated = true`. Sem timestamp (mantém o registro determinístico).

### 1.4 `Verdict` (enum do motor)

`AC`, `WA`, `TLE`, `MLE`, `RE`, `CE` (erro de compilação em todos os padrões).
`INFRA` **não** é um veredito: falha de infraestrutura é exceção (`InfraError`), nunca um valor
deste enum (FR-010).

### 1.5 Manifesto de integridade — FR-027

Arquivo versionado **fora de `data/`**: `manifests/dataset.manifest.json`.

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | int | `== 1` |
| `dataset_zip` | `{path, size, sha256}` | `path == "data/dataset.zip"` |
| `files` | list[`{path, size, sha256}`] | um item por arquivo dentro do zip; `path` relativo à raiz do zip (`dataset/problems/...`); ordenada por `path` |
| `problem_count` | int | `== número de pastas` |
| `provenance` | `{hf_dataset, hf_revision, seed, gcc_version}` | rastreabilidade; não entra em hash |

Sem carimbo de data/hora: regenerar o manifesto a partir do mesmo zip produz arquivo idêntico.

## 2. Entidades de trabalho (não empacotadas, dentro de `data/work/`, ignoradas pelo Git)

O diretório `data/work/` e seus subdiretórios são criados com permissão `0700` (dono: usuário do
host), para que o código de terceiros não os acesse (spec D15).

### 2.0 Checkpoint de extração (`data/work/staging/shards/<split>-<NNNNN>.json`)

Um arquivo por shard já processado (`schema_version`, `split`, `shard_index`, `rows_read`,
contagens do funil do shard e a lista de `problem_id` elegíveis encontrados, na ordem de
leitura). Sua existência marca o shard como concluído; é gravado depois dos `raw` do shard, de
forma atômica. O `pool.json` é derivado destes arquivos, na ordem global determinística, com
a primeira ocorrência de cada `problem_id` vencendo.

### 2.1 `Pool` (`data/work/staging/pool.json`)

`schema_version`, `hf_dataset`, `hf_revision`, `seed` (`42`), `counts` (funil: lidos, por
critério rejeitado, elegíveis), `order` (list[`problem_id`], ordem de processamento após embaralhar com
a seed) e `problems` (mapa `problem_id` → `{split, macrocategoria, raw_wa_count,
raw_ac_count, source_row}`).

Motivos de rejeição registrados no funil (FR-005; um problema pode ter mais de um), como
enum `RejectionReason`: `not_codeforces`, `rating_out_of_range` (inclui rating ausente),
`no_allowed_tag`, `forbidden_tag`, `visual_dependency`, `translated`, `file_io` (FR-004(h)),
`no_cpp_correct`, `no_cpp_incorrect`, `insufficient_raw_wa` (menos de 100 incorretas em C++).

### 2.2 `RawProblem` (`data/work/staging/raw/<problem_id>.json.gz`)

Dados pesados de um problema do pool, em formato próprio do módulo (não é o formato do
dataset): enunciado, testes (três grupos), soluções corretas C++ (ordem original) e submissões
incorretas C++ (ordem original, com o índice original), mais os campos de metadados brutos.
Gravado de forma atômica; reexecutar a extração não reescreve arquivos já completos.

### 2.3 Registro de problema em construção/encerrado

- `data/work/building/<problem_id>/` — construção em andamento; apagado e refeito se
  encontrado no início da execução (parcial, FR-023/FR-024).
- `data/work/problems/<problem_id>/` — problema encerrado. O `validacao.json.status` decide:
  `complete` (pasta completa, com os 6 tipos de arquivo), `pending_triage` (contém só
  `validacao.json` e `AC_candidate.cpp` para inspeção) ou `discarded` (só `validacao.json`).

### 2.4 `ExtractionReport` (`data/work/reports/extraction_report.json` e `.md`) — FR-018/FR-018a

`schema_version`, `funnel` (lidos; rejeitados por critério; descartados por motivo; incluídos),
`distribution` (por macrocategoria), `category_alerts` (macrocategorias com `< 30` problemas;
FR-018a), `pending_triage` (lista de `{problem_id, stage, reason}`, destacada quando não
vazia), `target` (200), `deficit` (`max(0, 200 - included)`), `engine_selfcheck` (resultado
da suíte de veredito conhecido) e `provenance`. O comando `package` copia o JSON para
`manifests/extraction_report.json` (versionado).

## 3. Máquina de estados de um problema

```text
(ausente) ──extract──▶ pool (elegível, com raw em staging)
pool ──validate──▶ building/
building ──AC ok e 100 WA──▶ problems/<id> [complete]
building ──AC falhou (FR-011b)──▶ problems/<id> [pending_triage]
building ──WA insuficientes (D4)──▶ problems/<id> [discarded]
building ──interrupção / InfraError──▶ (permanece em building/; refeito na retomada)
problems/<id> [complete] ──audit: AC falhou──▶ problems/<id> [pending_triage]
problems/<id> [pending_triage] ──resolução manual (apagar a pasta)──▶ (ausente; reprocessável)
```

Regras de retomada (FR-024): `complete`, `pending_triage` e `discarded` não são reprocessados;
`building/` é sempre descartado e refeito. Contam para a meta de 200 somente os `complete`.
