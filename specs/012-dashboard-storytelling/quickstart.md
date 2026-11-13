# Quickstart: validar o painel que conta a história

Pré-requisito: o "Caminho rápido" do `README.md` da raiz (os 12 pacotes descompactados e o
`cli check` OK).

## 1. Testes

```bash
docker compose run --rm sandbox pytest tests/metrics tests/dashboard
```

Esperado: tudo `passed`, inclusive `test_story.py` (placar e empates sem filtro, líder correto em
recortes) e as três páginas abrindo com `AppTest`.

## 2. Métricas com a coluna de rating e as figuras novas

```bash
docker compose run --rm app python -m metrics compute
docker compose run --rm app python -m metrics figures
docker compose run --rm app python -m metrics package
docker compose run --rm app python -m metrics verify --extracted data/metrics
```

Esperado: `per_problem.csv` com a coluna `rating`; `metrics.csv`, `iic.csv`, `stats.csv` e
`cost.csv` com os mesmos bytes de antes (`git diff --stat data/metrics.zip` muda, mas o teste de
regressão confere as tabelas); `data/metrics/figures/` com `scoreboard`, `tradeoff`,
`scenario_shift`, `iic_diverging` e `choice_guide` em PNG, SVG e PDF; `verify` → `OK`.

Uma figura com filtro de rating:

```bash
docker compose run --rm app python -m metrics figures --figure scoreboard --rating 1600 --format png
```

Esperado: `data/metrics/figures/scoreboard__rating-1600.png`, com o recorte no subtítulo.

## 3. O painel

```bash
docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve
```

Em `http://localhost:8501`, conferir (sem filtro):

| Página | O que conferir |
|---|---|
| O experimento (abre primeiro) | 200 problemas; 24.274 testes; US$ 19,35 (GPT 70%, Gemini 25%, Claude 5%); ratings 33/24/20/22/35/31/35; macrocategorias 98/61/41 |
| A avaliação | abas Comparações e Combinação; `61_B`, `slm`, caixa-preta: teste 3 reprova o AC, 100 WAs pelo gabarito da IA e 45 pelo do AC |
| As métricas | placar: Gemini 1º em TDF\* (90,1%) e MS\* (97,0%); Claude 1º em TFP (17,3%) e custo; GPT 1º em Δ (1,9); guia com "caixa-branca": TFP do modelo local e do Claude em empate; TDF\* do Gemini e do Claude em empate |

Com filtro: macrocategoria `matematica` → o topo de cada página diz "41 problemas", os títulos
mudam de acordo com o recorte, e as notas de teste estatístico viram "não testado"; um problema só
→ a página 3 avisa e aponta a página 2.

## 4. Revisão pela skill (R10)

Capturar as três páginas e aplicar o checklist de 10 itens da skill *visual-storytelling-design*;
registrar o resultado para os autores.
