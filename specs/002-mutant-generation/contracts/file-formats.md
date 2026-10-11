# Contract: Formatos de arquivo do módulo `mutation`

**Feature**: `002-mutant-generation` | Fonte de verdade dos campos: [data-model.md](../data-model.md).
Mesmas regras de serialização já em vigor no módulo de dataset (UTF-8 sem BOM, `\n`,
`json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)`, escrita atômica) — ver
`specs/001-dataset-extraction/contracts/file-formats.md`, seção "Regras de serialização".

## `Mutant_<n>.cpp` (dentro de `data/mutants/<problem_id>/` ou de `data/mutants.zip`)

Texto C++ puro (não é JSON) — o `AC_ref.cpp` do problema com 1 a 3 sítios substituídos, byte a
byte idêntico ao original fora dos sítios alterados. Sem cabeçalho nem metadado embutido; a
proveniência (quais sítios, quais operadores, ordem) fica só em `mutation_report.json`
(agregado, não por arquivo) — decisão deliberada para não multiplicar por 100 o volume de
metadado por problema (diferente de `validacao.json`, que documenta cada `WA_<n>.cpp`
individualmente, porque falhas reais têm proveniência externa a auditar; mutantes são gerados
por este mesmo código, e a proveniência agregada já é suficiente).

## `data/mutants/problems/<problem_id>/generation.json` (só em desenvolvimento, fora do zip)

Registro de como os mutantes de um problema foram obtidos (operador e variante de cada um, contagem
de descartes por ordem e motivo, e a exclusão quando o problema não fechou 100): campos em
[data-model.md](../data-model.md), "Registro de geração por problema". Não fica dentro do
`Mutant_<n>.cpp` (ver acima) nem entra no zip: existe para que `report` recalcule os agregados de
`mutation_report.json` sem regerar. Mesmas regras de serialização dos demais JSON do projeto.

## `manifests/mutants.manifest.json`

```json
{
  "schema_version": 1,
  "mutants_zip": {
    "path": "data/mutants.zip",
    "sha256": "…",
    "size": 0
  },
  "files": [
    {
      "path": "mutants/problems/1000_B/Mutant_1.cpp",
      "sha256": "…",
      "size": 0
    }
  ]
}
```

Mesmo formato de `manifests/dataset.manifest.json` — lista `files` ordenada por `path`, hash
SHA-256 e tamanho de cada arquivo dentro do zip, mais o hash e tamanho do zip inteiro.

## `manifests/mutation_report.json`

```json
{
  "schema_version": 1,
  "problems": { "closed": 0, "complete": 0, "first_order_only": 0, "higher_order": 0, "excluded": 0 },
  "funnel": {
    "duplicate": 0,
    "compile_error": 0,
    "tle": 0,
    "mle": 0,
    "re": 0,
    "equivalent": 0,
    "unstable": 0
  },
  "order_distribution": { "1": 0, "2": 0, "3": 0 },
  "operator_distribution": { "ROR": 0, "AOR": 0, "LCR": 0, "ABS": 0, "UOI": 0 },
  "exclusion_alerts": [
    { "problem_id": "0_A", "mutants_reached": 0, "highest_order_attempted": 3 }
  ],
  "dataset_manifest_sha256": "…"
}
```

`problems` conta só o que já foi gerado: `complete + excluded = closed` e `first_order_only +
higher_order = complete` (base do número que a metodologia compara com a estimativa de 75%).
O relatório **não** traz a revisão do código (retirada em 2026-09-25, spec FR-013): quem versiona
os artefatos os liga ao commit. Todas as chaves de `funnel`, `order_distribution`
e `operator_distribution` estão sempre presentes, mesmo com contagem 0.

`exclusion_alerts` vazia é o caso esperado (spec, SC-003); presente sempre que o campo existir no
JSON (nunca omitido), para que sua ausência nunca seja ambígua com "não verificado".
