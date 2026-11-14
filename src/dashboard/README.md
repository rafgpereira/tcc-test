# Módulo `dashboard` (painel dos resultados)

> **Status**: implementado · **Metodologia**: `docs/metodologia-referencia.md`, seções 5.8 e 8

## (a) Propósito

Mostra num painel no navegador, só para leitura, os resultados do experimento: o que foi gerado e avaliado, quem se saiu melhor em cada critério, de onde vem cada número até o teste que o produziu, e a avaliação combinação a combinação.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando).
O painel roda no serviço `app` (o do Docker Compose que tem rede) com uma porta publicada só para
esta máquina; ele lê o que já existe, não gera nenhum artefato, não grava nada, não chama IA nem
executa código de terceiros.

O que cada página precisa descompactado em `data/`:

| Página | Precisa de |
|---|---|
| O experimento e A avaliação | os cinco pacotes de avaliação (`data/evaluation/<conjunto>/`, README do módulo [`evaluation`](../evaluation/README.md)); o gasto da primeira depende também de `data/metrics/` |
| As métricas | `data/metrics/` (README do módulo [`metrics`](../metrics/README.md)); sem ela, a página só mostra um aviso |
| Rastreabilidade e o detalhe de uma combinação em A avaliação | a avaliação e também o dataset, os mutantes e as suítes (para mostrar tentativas, entradas, saídas e códigos) |

### Cenário A — Rodar do zero

Gere antes os artefatos que o painel lê, na ordem dos módulos: [`dataset`](../dataset/README.md),
[`mutation`](../mutation/README.md), [`ai_clients`](../ai_clients/README.md) (suítes dos quatro
modelos), [`evaluation`](../evaluation/README.md) (`run` e `report`) e [`metrics`](../metrics/README.md)
(`compute`). Depois, abra o painel:

```bash
docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve
```

Para ver uma avaliação em andamento ou guardada em outra pasta, use `--evaluation-dir DIR`; durante
uma avaliação, clique em **recarregar dados** na barra lateral para ver os problemas concluídos
depois da abertura.

### Cenário B — Usar o que já existe

Descompacte os pacotes versionados, confira a integridade e abra o painel (os mesmos passos do
"Caminho rápido" do [README da raiz](../../README.md)):

```bash
for z in dataset mutants slm_suites gpt_suites gemini_suites claude_suites \
         evaluation_slm evaluation_gpt evaluation_gemini evaluation_claude evaluation_slm-attempt1 \
         metrics; do
  unzip -q data/$z.zip -d data/
done
docker compose run --rm app python -m cli check --deep
docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve
```

Abra **http://localhost:8501** no navegador. A porta é publicada só em `127.0.0.1`: ninguém da
rede alcança o painel. O comando fica no ar até Ctrl+C no terminal. Se você rodou o painel antes
de um `git pull` que mudou o módulo, rode `docker compose build` uma vez.

### Como usar o painel

O painel tem quatro páginas, que se leem nesta ordem. Os filtros (conjunto, cenário, problema,
macrocategoria, rating, status da suíte) ficam só na barra lateral e valem para todas as páginas; o
topo de cada página diz o recorte ativo e quantos problemas ele tem. Passe o mouse sobre uma sigla
ou o nome de uma coluna para ver o significado; o **Glossário**, na barra lateral, explica também
os valores que aparecem nas tabelas (`wrong_output`, `accepted_predicted`, `black_box`…). Cada
tabela tem um botão para baixar o CSV já filtrado e cada gráfico se salva em PNG ou SVG pelo seu
menu ("…", ao passar o mouse); os arquivos vão para a pasta de downloads do navegador, não para o
repositório.

- **O experimento** (abre primeiro): números grandes (problemas, falhas, IAs × cenários, suítes,
  testes gerados, gasto) e gráficos de rating, macrocategoria, suítes por IA e status, testes por
  suíte e gasto por IA comercial (o modelo local aparece à parte, com as horas de modelo). Os
  números de cada gráfico estão no fim, em "Ver os números desta página".
- **As métricas**: quem se saiu melhor em cada critério no recorte, sempre pelo gabarito do AC
  (\*). Na ordem: o **placar** e o **placar por cenário**, falhas reais e mutantes, falsos
  positivos, contexto (variação entre cenários e IIC) e custo; depois o **guia de escolha** (em
  cada cenário, a melhor IA em cada critério, o 2º colocado e se a diferença é significativa, um
  empate estatístico ou não testada; "Minha prioridade" só realça uma linha) e, no fim, as tabelas
  oficiais, os testes estatísticos e o custo. O título de cada cartão é a conclusão dos números do
  recorte; "Como se calcula" mostra a fórmula e a conta com os números do recorte. Um recorte de
  um problema só não tem métrica: a página avisa e aponta a ficha do problema na Rastreabilidade.
- **Rastreabilidade**: de onde vem cada número. Em "O que você quer rastrear?", escolha um caso
  (combinações sem suíte, suítes "sem raciocínio", origem da suíte do modelo local, qual teste
  reprovou um WA ou mutante, por que o AC foi reprovado, detecções que só existem por um gabarito,
  WAs que nenhuma ou só uma IA detectou, mutantes que sobreviveram, de onde vem o IIC, ficha de um
  problema). A lista segue os filtros e "Abrir" mostra o item: a combinação (status, origem,
  tentativas, testes com a saída do AC), o alvo (quem o detectou, com qual teste, e o código ao
  lado do AC) ou o problema (enunciado, AC e as 15 combinações). Cada alvo para no primeiro teste
  que o reprova, então o "teste que reprovou" é sempre o primeiro.
- **A avaliação**, em duas abas. **Comparações**: a diferença entre o oráculo declarado e o
  corrigido por combinação (em vermelho, as com o AC reprovado) e o modelo local (suíte final e 1ª
  tentativa) ao lado dos comerciais. **Combinação**: escolha conjunto, problema e cenário e veja,
  teste a teste, a entrada, a saída esperada escrita na suíte, a saída real do `AC_ref`, o
  veredito do AC e quantos alvos cada teste detectou em cada oráculo.

**Como ler os gráficos da página As métricas** (cenários: caixa-preta = só o enunciado,
caixa-branca = só o código, híbrido = os dois):

| Gráfico | O que mostra | Como ler |
|---|---|---|
| Placar | posição e valor de cada IA em cada critério, média dos cenários do recorte | o 1º de cada coluna fica destacado; a média dos cenários não tem teste estatístico (o teste está no guia) |
| Falhas reais (TDF\*) e mutantes (MS\*) | barras ordenadas pelo gabarito do AC; o traço é o valor pelo gabarito da IA | mais alto é melhor; a distância entre a barra e o traço é a detecção que só existiu porque a IA errou a saída esperada |
| Detecta × reprova o código correto | um ponto por IA: TFP no eixo horizontal, TDF\* no vertical | o canto de cima à esquerda (sombreado) é o ideal |
| Variação entre cenários | a TDF\* de cada IA em cada cenário | linha reta = o contexto quase não muda a detecção daquela IA |
| IIC | quanto o híbrido ganha (acima de 0) ou perde (abaixo) sobre a caixa-preta ("+ código") e sobre a caixa-branca ("+ requisito"), somando os problemas | o seletor troca o gabarito |
| Custo | US$ para cada 1.000 WAs detectados, só nos modelos comerciais | mais baixo é melhor; o custo não se divide por problema |
| Guia de escolha | em cada cenário, a melhor IA em cada critério e o 2º colocado | "diferem" = diferença significativa; "empate" = sem diferença estatística; "não testado" = não há teste para esse critério ou recorte |

### Cópia pública (opcional, Streamlit Community Cloud)

O mesmo painel pode ficar na internet no **Streamlit Community Cloud** (gratuito), mostrando os
pacotes versionados no GitHub (na primeira abertura ele descompacta os zips, cerca de 40 s):

1. Entre em **share.streamlit.io** com uma conta do GitHub que tenha acesso ao repositório (se for
   de uma organização e não aparecer, autorize a organização para o Streamlit em *Settings →
   Applications* do GitHub; se for privado, autorize também repositórios privados).
2. **Create app** → *Deploy a public app from GitHub*: o repositório, a branch `main`, *Main file
   path* `src/dashboard/public/streamlit_app.py` (não o `src/dashboard/app.py`) e, em *Advanced
   settings*, Python **3.11**. Clique em **Deploy**; cada `git push` na branch atualiza o painel.

Quem pode ver: *Settings → Sharing* do app. Sem visitas por 12 horas o app "dorme" e acorda ao ser
aberto.

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m dashboard serve` | `app` | abre o painel; rode com `-p 127.0.0.1:8501:8501` no `docker compose run`. `--evaluation-dir DIR` (padrão `data/evaluation`; também pode ser trocada no próprio painel), `--port N` (padrão `8501`; a publicada no `-p` tem de ser a mesma). Ctrl+C fecha. Códigos: `0` fechado, `2` pasta inexistente, `3` biblioteca do painel ausente na imagem |
| `unzip data/<pacote>.zip -d data/` | (host) | descompacta cada pacote que o painel lê (laço do Cenário B) |
| `pytest tests/dashboard` | `sandbox` | testes do módulo |

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `error: streamlit is not installed in the image` (`3`) | `docker compose build` |
| `error: not a folder: data/evaluation` (`2`) | ainda não há avaliação: descompacte `data/evaluation_<conjunto>.zip` (Cenário B) ou rode `python -m evaluation run`, ou aponte `--evaluation-dir` |
| o navegador não abre `localhost:8501` | confira o `-p 127.0.0.1:8501:8501` e se outro programa já usa a porta (troque as duas, `-p` e `--port`) |
| "Nenhum resultado concluído" | a avaliação ainda não fechou nenhum problema; espere e clique em **recarregar dados** |
| "arquivo(s) inválido(s)" na barra lateral | um resultado não confere com o formato da avaliação; descompacte de novo o pacote do conjunto |
| "A suíte não está descompactada" ou "Código não disponível" | descompacte as suítes, o dataset ou os mutantes (Cenário B) |
| a página As métricas só mostra um aviso | descompacte `data/metrics.zip` (Cenário B) ou rode `python -m metrics compute` |
| a cópia pública mostra um erro | abra *Manage app* no canto inferior direito para ver o registro; *Reboot app* refaz a abertura |
| a cópia pública falha em `from dashboard import ...` | o *Main file path* está errado: apague o app (⋮ → *Delete*) e crie de novo com `src/dashboard/public/streamlit_app.py` |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/evaluation/<conjunto>/problems/<id>/<cenário>.json` e `results.csv` | JSON e CSV | pacote de avaliação descompactado ou `python -m evaluation run` |
| `data/metrics/*.csv` | CSV | pacote de métricas descompactado ou `python -m metrics compute` |
| `data/suites/...` (a pasta indicada na origem de cada resultado) | JSON | suítes descompactadas (entrada, saída esperada e tentativas) |
| `data/dataset/problems/<id>/` (`metadata.json`, `AC_ref.cpp`, `WA_<n>.cpp`) e `data/mutants/problems/<id>/Mutant_<n>.cpp` | JSON e C++ | dataset e mutantes descompactados (macrocategoria e código lado a lado) |

## (d) Saídas produzidas

Nenhuma no repositório. Só a página no navegador e, quando você pede, o CSV de uma tabela ou um
gráfico, baixados pelo navegador. Só a cópia pública descompacta os pacotes em `data/`, no servidor
dela.

## (e) Dependências e pré-requisitos

- Python 3.11, Streamlit 1.66.1, pandas 3.0.6 e Altair (fixados no `uv.lock`), na imagem
  (`docker compose build`).
- Serviço `app` com a porta publicada; nenhuma variável de ambiente nem segredo.
- Os pacotes descompactados que a página aberta precisa (tabela do Cenário B).

## (f) Limitações conhecidas

- O painel não executa código: para saber o que um WA respondeu num teste, compare o código dele
  com o do `AC_ref` no detalhe do alvo.
- As porcentagens de detecção das tabelas por combinação (detectados ÷ total, só sobre as
  combinações com suíte) não são as métricas oficiais; as oficiais (TDF, MS e as demais) vêm do
  módulo `metrics` e estão na página As métricas.
- O tempo de abertura ainda não foi medido num navegador. Medido em 2026-11-14, sem navegador
  (renderização de cada página por teste automático, dados completos, 3.000 combinações, dentro do
  container): O experimento, 17,6 s na primeira leitura e 0,5 s depois; A avaliação, 1,3 s;
  Rastreabilidade, 0,3 s; As métricas, de 66 s a 127 s, por montar todos os gráficos (recortes
  menores abrem mais rápido). O servidor responde em cerca de 2,5 s.
- Na cópia pública, o campo "Pasta de avaliação" da barra lateral continua editável; ele só lê
  resultados no formato da avaliação, no servidor da cópia.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 5.8 (figuras) e seção 8 (histórico das decisões do painel)
- Avaliação: [README do módulo `evaluation`](../evaluation/README.md); métricas: [README do módulo `metrics`](../metrics/README.md)
- Testes: `tests/dashboard/` (`docker compose run --rm sandbox pytest tests/dashboard`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `serve` | 2026-11-14 | bf6cc21+dirty |
