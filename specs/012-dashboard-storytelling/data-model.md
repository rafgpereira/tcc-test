# Data model: Painel que conta a história dos resultados

Estruturas em memória de `metrics.story`; nada é gravado, exceto a coluna `rating` do
`per_problem.csv` (R2).

## Recorte

| Campo | Tipo | Regra |
|---|---|---|
| `sets` | tupla de conjuntos | vazio = os 5 (`slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`) |
| `scenarios` | tupla de cenários | vazio = os 3 |
| `macrocategorias`, `ratings`, `statuses`, `problems` | tuplas | vazias = sem restrição |
| `complete` | derivado | verdadeiro só sem filtro de problema, macrocategoria, rating ou status (R3) |
| `n_problems` | derivado | problemas no recorte; menos de 2 → `CutError` na página 3 |

## Criterio

| Campo | Exemplo |
|---|---|
| `key` | `tdf_star` |
| `label` (uso) | "encontrar o máximo de falhas" |
| `column` | `TDF_star` (de `metrics.primary.table`) ou `cpd_wa_corrected` (custo) |
| `better` | `"higher"` ou `"lower"` |
| `stats_metric` | `TDF_star`, `MS_star`, `TFP` ou `None` (sem teste) |
| `unit` | `%`, `pontos`, `US$ por 1.000 WAs` |
| `local_ranked` | falso só no custo (o modelo local fica fora) |

Lista fixa, na ordem do placar: `tdf_star`, `ms_star`, `tfp`, `delta_tdf`, `tc`, `cost`. O guia
acrescenta "rodar sem custo de API" (o modelo local, sem número).

## Resultado (de um critério num cenário ou no recorte)

`leader`, `value`, `second`, `second_value`, `state` (`differ` | `tie` | `untested`), `n_denominator`.

## Titulo

`text` (título-conclusão), `subtitle` (tema, recorte e denominador), `rule` (o identificador do
modelo de frase usado, para o teste conferir).

## Cartao (guia de escolha)

`criterio`, `scenario` (sempre nomeado caixa-preta = `black_box`, caixa-branca = `white_box`, híbrido =
`hybrid`), e o `Resultado`.

## Validações

- O líder de um `Resultado` tem o melhor valor do recorte no sentido de `better` (SC-002).
- Empate exato de valores: mesma posição no placar; o `Resultado` lista o primeiro em ordem fixa dos
  conjuntos e marca `tie`.
- O modelo local nunca é `leader` de custo.
- `state = "untested"` sempre que `complete` é falso, o critério não tem `stats_metric` ou o valor
  é média de cenários.
