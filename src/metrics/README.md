# Módulo `metrics` (métricas de avaliação)

> **Status**: implementado · **Metodologia**: `docs/metodologia-referencia.md`, seção 5

## (a) Propósito

Calcula, a partir dos resultados da avaliação das suítes, as métricas do trabalho (TDF, MS, TFP, IIC e as complementares), os testes estatísticos que comparam cenários e modelos, e as figuras do texto.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando).
Tudo roda no serviço `app` (o serviço do Docker Compose que tem rede e não executa código de
terceiros); nada aqui executa C++ nem chama IA.

**O que sai** (todas as taxas em %, por conjunto e cenário):

| Tabela | O que tem |
|---|---|
| `metrics.csv` | **TDF** (% de WAs, as falhas reais, que a suíte pega), **MS** (% de mutantes), e as contagens: **WAs e mutantes mortos** de um total de 100 de cada por problema (cada um conta uma vez, morto se algum teste o reprovou), **TFP** (% de problemas em que a suíte reprova o código correto: falso positivo), **TC** (% de combinações com suíte); as mesmas pelo gabarito do código correto (**TDF\***, **MS\***) e a diferença (**Δ**, quanto da detecção vem de gabarito errado da IA); a TFP por teste, separando saída errada da IA de entrada inválida; a densidade (TDF por teste). Sem corte e por macrocategoria e status da suíte |
| `iic.csv` | **IIC**: quanto juntar enunciado e código ajudou (positivo) ou atrapalhou (negativo), somando os 200 problemas, e a distribuição problema a problema |
| `stats.csv` | se as diferenças entre cenários e entre modelos são reais: Friedman, Wilcoxon pareado e McNemar, com p-valor corrigido (Holm) e tamanho do efeito (A12) |
| `cost.csv` | custo em US$ dos modelos comerciais e custo por falha detectada; *tokens* e tempo dos quatro (o modelo local não tem custo em dinheiro) |
| `per_problem.csv`, `detected_wa.csv` | a base de tudo, uma linha por problema (com a macrocategoria e o rating do Codeforces, usados nos cortes) e por WA detectado |

Todo número das métricas citado no texto do trabalho sai destas tabelas.

### Cenário A — Rodar do zero

Pré-requisito: o dataset, os mutantes, as suítes dos quatro modelos e as cinco avaliações
descompactados em `data/` (ou gerados do zero, pelos módulos [`dataset`](../dataset/README.md),
[`mutation`](../mutation/README.md), [`ai_clients`](../ai_clients/README.md) e
[`evaluation`](../evaluation/README.md)). Para só descompactar:

```bash
for z in dataset mutants slm_suites gpt_suites gemini_suites claude_suites \
         evaluation_slm evaluation_gpt evaluation_gemini evaluation_claude evaluation_slm-attempt1; do
  unzip -q data/$z.zip -d data/
done
```

Depois:

```bash
docker compose run --rm app python -m metrics compute
docker compose run --rm app python -m metrics figures
docker compose run --rm app python -m metrics package
docker compose run --rm app python -m metrics verify --extracted data/metrics
```

1. **`compute`** confere antes que as cinco avaliações estão completas e que `cli check --deep`
   passa no dataset, nas suítes e nas avaliações (senão para com `1` e não grava nada); grava as
   tabelas em `data/metrics/` (de uma vez: uma interrupção não deixa metade) e imprime TDF, MS,
   TFP, TC, TDF\* e MS\* de cada conjunto e cenário, terminando em `tables: data/metrics`. Rodar de
   novo dá os mesmos arquivos.
2. **`figures`** (opcional) desenha 12 gráficos em `data/metrics/figures/`, em PNG, SVG e PDF, para
   quem quiser os arquivos fora do painel (o painel desenha os mesmos, interativos): `scoreboard`
   e `scoreboard_scenarios` (placar), `tdf_by_model`, `tdf_declared_vs_corrected`,
   `ms_declared_vs_corrected`, `tradeoff`, `tfp_by_cause`, `scenario_shift`, `iic_diverging`,
   `iic_distribution`, `cost_per_detection` e `choice_guide`. O título de cada figura é a conclusão
   dos números e muda com os filtros. Com filtros, o nome do arquivo e o subtítulo dizem o filtro
   (por exemplo, `scoreboard__rating-1600.png`), para qualquer figura poder ser refeita. O custo
   não se divide por problema: com um filtro por problema, macrocategoria, rating ou status, a
   figura de custo mostra o valor de todos os problemas e diz isso no subtítulo. PNG e SVG saem
   iguais byte a byte a cada execução; o PDF tem o mesmo desenho, mas não sai igual byte a byte.
   As figuras não entram no pacote nem no repositório.
3. **`package`** grava `data/metrics.zip` (as tabelas e o `run.json`, nunca as figuras) e
   `manifests/metrics.manifest.json` (recusa se faltar alguma tabela); rodar de novo sobre as mesmas
   tabelas dá o mesmo zip. **`verify`** confere o zip e a pasta e imprime `OK`.

### Cenário B — Descompactar o que já existe

```bash
rm -rf data/metrics
unzip data/metrics.zip -d data/
docker compose run --rm app python -m metrics verify --extracted data/metrics
```

Esperado: `OK`. As tabelas ficam em `data/metrics/*.csv`; as figuras desenham-se delas com
`python -m metrics figures` ou na página **As métricas** do painel (README do módulo
[`dashboard`](../dashboard/README.md)).

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m metrics compute` | `app` | calcula as tabelas; `--evaluation-dir DIR` (padrão `data/evaluation`). Códigos: `0`; `1` avaliação incompleta ou `cli check` com falha |
| `python -m metrics figures` | `app` | desenha as figuras; `--figure NOME` (repetível; padrão todas), filtros `--macrocategoria M`, `--rating R`, `--status S`, `--set S` (`slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`), `--scenario C` (`black_box`, `white_box`, `hybrid`), `--problem ID` (repetíveis; nunca um problema só), `--format png,svg,pdf` (padrão os três), `--output-dir DIR`. Códigos: `0`; `1` tabelas ausentes; `2` filtro inválido |
| `python -m metrics package` | `app` | zip e manifesto |
| `python -m metrics verify` | `app` | confere o zip; `--extracted DIR` também a pasta |
| `unzip data/metrics.zip -d data/` | (host) | descompacta as tabelas em `data/metrics/` |
| `pytest tests/metrics` | `sandbox` | testes do módulo (casos conhecidos de cada métrica) |

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `ModuleNotFoundError: No module named 'altair'` | a imagem é antiga: `docker compose build` |
| `error: the evaluation of <conjunto> is not complete` (`1`) | descompacte de novo `data/evaluation_<conjunto>.zip` (ou termine a avaliação e rode `python -m evaluation report`) |
| ``error: `cli check --deep` failed`` (`1`) | descompacte de novo o artefato apontado |
| `error: metrics tables not found` (`1`) | rode `compute` (ou descompacte `data/metrics.zip`) antes de `figures` |
| `a cut with a single problem has no metric` (`2`) | escolha um filtro com mais de um problema; para olhar um problema, use a ficha do problema na página Rastreabilidade do painel |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/evaluation/<conjunto>/results.csv` | CSV | pacotes de avaliação descompactados |
| `data/dataset/problems/<id>/metadata.json` | JSON | dataset (macrocategoria) |
| `manifests/<modelo>_generation_report.json` e as tentativas em `data/suites/` | JSON | suítes (custo, *tokens* e tempo) |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| as seis tabelas e `run.json` (hashes das entradas) | CSV e JSON | `data/metrics/` |
| figuras (opcional, fora do pacote) | PNG, SVG e PDF | `data/metrics/figures/` |
| `data/metrics.zip`, `manifests/metrics.manifest.json` | zip e JSON | **versionados** (`package`) |

## (e) Dependências e pré-requisitos

- Python 3.11, pandas, scipy, Altair e vl-convert (desenho e exportação das figuras), fixados no `uv.lock`, na imagem (`docker compose build`).
- Serviço `app`; nenhuma variável de ambiente nem segredo.
- Os pacotes de avaliação, o dataset, os mutantes e as suítes descompactados (Cenário A).

## (f) Limitações conhecidas

- As comparações estatísticas são pareadas pelos 200 problemas; uma combinação sem suíte entra
  com 0% de detecção (e o AC não reprovado), e a cobertura (TC) é reportada ao lado.
- O IIC usa os WAs (falhas reais); o IIC sobre mutantes e a complementaridade entre modelos ficaram
  fora do escopo.
- O custo por cenário dos modelos comerciais é o do relatório de geração; o tempo por cenário é a
  soma das latências registradas nas tentativas.
- Medido em 2026-11-14: `verify --extracted` leva cerca de 6 s e `compute` cerca de 33 s, sobre a
  avaliação completa.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 5
- Testes: `tests/metrics/` (`docker compose run --rm sandbox pytest tests/metrics`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `compute` | 2026-11-14 | bf6cc21+dirty |
| `figures` | 2026-11-14 | bf6cc21+dirty |
| `package` | 2026-11-14 | bf6cc21+dirty |
| `verify` | 2026-11-14 | bf6cc21+dirty |
