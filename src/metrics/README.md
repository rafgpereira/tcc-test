# Módulo `metrics` (métricas de avaliação)

> **Status**: em implementação (código e testes prontos; conferência com os autores pendente) · **Metodologia**: `docs/metodologia-referencia.md`, seção 5

## (a) Propósito

Calcula, a partir dos resultados da avaliação das suítes, as métricas do trabalho (TDF, MS, TFP, IIC e as complementares), os testes estatísticos que comparam cenários e modelos, e as figuras do texto.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
e tenha descompactados o dataset, as suítes dos quatro modelos e os cinco pacotes de avaliação
(README dos módulos [`dataset`](../dataset/README.md), [`ai_clients`](../ai_clients/README.md) e
[`evaluation`](../evaluation/README.md), Cenário B). Tudo roda no serviço `app`; nada aqui executa
código de terceiros nem chama IA.

**O que sai** (todas as taxas em %, por conjunto e cenário):

| Tabela | O que tem |
|---|---|
| `metrics.csv` | **TDF** (% de WAs, as falhas reais, que a suíte pega), **MS** (% de mutantes), **TFP** (% de problemas em que a suíte reprova o código correto: falso positivo), **TC** (% de combinações com suíte); as mesmas pelo gabarito do código correto (**TDF\***, **MS\***) e a diferença (**Δ**, quanto da detecção vem de gabarito errado da IA); a TFP por teste, separando saída errada da IA de entrada inválida; a densidade (TDF por teste). Sem corte e por macrocategoria e status da suíte |
| `iic.csv` | **IIC**: quanto juntar enunciado e código ajudou (positivo) ou atrapalhou (negativo), somando os 200 problemas, e a distribuição problema a problema |
| `stats.csv` | se as diferenças entre cenários e entre modelos são reais: Friedman, Wilcoxon pareado e McNemar, com p-valor corrigido (Holm) e tamanho do efeito (A12) |
| `cost.csv` | custo em US$ dos modelos comerciais e custo por falha detectada; *tokens* e tempo dos quatro (o modelo local não tem custo em dinheiro) |
| `per_problem.csv`, `detected_wa.csv` | a base de tudo, uma linha por problema e por WA detectado |

Todo número das métricas citado no texto do trabalho sai destas tabelas.

### Cenário A — Rodar do zero

```bash
docker compose run --rm app python -m metrics compute
docker compose run --rm app python -m metrics figures
docker compose run --rm app python -m metrics package
docker compose run --rm app python -m metrics verify --extracted data/metrics
```

1. **`compute`** confere antes que as cinco avaliações estão completas e que `cli check --deep`
   passa no dataset, nas suítes e nas avaliações (senão para com `1` e não grava nada); grava as
   tabelas em `data/metrics/` (de uma vez: uma interrupção não deixa metade) e imprime TDF, MS,
   TFP, TC, TDF\* e MS\* de cada conjunto e cenário. Rodar de novo dá os mesmos arquivos.
2. **`figures`** desenha os gráficos em `data/metrics/figures/`, em PNG e PDF: TDF por modelo e
   cenário, TDF × TDF\*, MS × MS\*, falsos positivos por causa, distribuição do IIC e custo por
   detecção. Com filtros, o nome do arquivo e o rodapé da figura dizem o filtro (por exemplo,
   `tdf_by_model__macrocategoria-matematica.pdf`), para qualquer figura poder ser refeita.
3. **`package`** grava `data/metrics.zip` e `manifests/metrics.manifest.json` (recusa se faltarem
   tabelas ou as figuras sem filtro); **`verify`** confere o zip e a pasta: `OK`.

As mesmas tabelas e figuras, com filtros e o botão de baixar PNG e PDF, aparecem na página
**Métricas** do painel (README do módulo [`dashboard`](../dashboard/README.md)); a figura baixada
lá é idêntica à do comando com o mesmo filtro.

### Cenário B — Descompactar o que já existe

```bash
rm -rf data/metrics
unzip data/metrics.zip -d data/
docker compose run --rm app python -m metrics verify --extracted data/metrics
```

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m metrics compute` | `app` | calcula as tabelas; `--evaluation-dir DIR` (padrão `data/evaluation`). Códigos: `0`; `1` avaliação incompleta ou `cli check` com falha |
| `python -m metrics figures` | `app` | desenha as figuras; `--figure NOME` (repetível; padrão todas), filtros `--macrocategoria M`, `--status S`, `--set S`, `--scenario C` (repetíveis; nunca um problema só), `--format png,pdf`, `--output-dir DIR`. Códigos: `0`; `1` tabelas ausentes; `2` filtro inválido |
| `python -m metrics package` | `app` | zip e manifesto |
| `python -m metrics verify` | `app` | confere o zip; `--extracted DIR` também a pasta |
| `pytest tests/metrics` | `sandbox` | testes do módulo (casos conhecidos de cada métrica) |

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `error: the evaluation of <conjunto> is not complete` (`1`) | termine a avaliação e rode `python -m evaluation report` |
| ``error: `cli check --deep` failed`` (`1`) | descompacte de novo o artefato apontado |
| `error: metrics tables not found` (`1`) | rode `compute` antes de `figures` |
| `a cut with a single problem has no metric` (`2`) | escolha um filtro com mais de um problema; para olhar um problema, use a página Combinação do painel |

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
| figuras | PNG e PDF | `data/metrics/figures/` |
| `data/metrics.zip`, `manifests/metrics.manifest.json` | zip e JSON | **versionados** (`package`) |

## (e) Dependências e pré-requisitos

- Python 3.11, pandas, scipy e matplotlib, fixados no `uv.lock`, na imagem (`docker compose build`).
- Serviço `app`; nenhuma variável de ambiente nem segredo.

## (f) Limitações conhecidas

- As comparações estatísticas são pareadas pelos 200 problemas; uma combinação sem suíte entra
  com 0% de detecção (e o AC não reprovado), e a cobertura (TC) é reportada ao lado.
- O IIC usa os WAs (falhas reais); o IIC sobre mutantes e a complementaridade entre modelos ficaram
  fora do escopo.
- O custo por cenário dos modelos comerciais é o do relatório de geração; o tempo por cenário é a
  soma das latências registradas nas tentativas.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 5
- Testes: `tests/metrics/` (`docker compose run --rm sandbox pytest tests/metrics`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `compute` | pendente | — |
| `figures` | pendente | — |
| `package` | pendente | — |
| `verify` | pendente | — |
