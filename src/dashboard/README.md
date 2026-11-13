# Módulo `dashboard` (painel dos resultados)

> **Status**: em implementação (código e testes prontos; conferência com os autores pendente) · **Metodologia**: `docs/metodologia-referencia.md`, seção 8

## (a) Propósito

Mostra num painel no navegador, só para leitura, os resultados da avaliação das suítes: o que já foi avaliado, cada combinação teste a teste e as comparações entre oráculos e modelos.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando).
Depois de um `git pull` que trouxe este módulo, rode `docker compose build` uma vez (a imagem
ganhou a biblioteca do painel). O painel lê o que já existe; não gera nenhum artefato e não grava
nada. O que cada página precisa descompactado:

| Página | Precisa de |
|---|---|
| Visão geral e Comparações | os cinco pacotes de avaliação (`data/evaluation/<conjunto>/`, README do módulo [`evaluation`](../evaluation/README.md)) |
| Combinação | a avaliação e também o dataset, os mutantes e as suítes (para mostrar entradas, saídas e códigos) |
| Métricas | `data/metrics/` (README do módulo [`metrics`](../metrics/README.md)); sem ela, a página só mostra um aviso |

O jeito mais simples é descompactar tudo de uma vez, com o laço do "Caminho rápido" do
[README da raiz](../../README.md).

```bash
docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve
```

Abra **http://localhost:8501** no navegador. O comando roda no serviço `app` e publica a porta só
para esta máquina (`127.0.0.1`): ninguém da rede alcança o painel, e ele não consulta nada na
internet. Ele fica no ar até Ctrl+C no terminal.

**Siglas**: passe o mouse sobre o nome de uma coluna ou sobre uma sigla (AC, WA, TLE, TDF…) para
ver o nome completo e o que significa; o **Glossário**, na barra lateral, explica também os valores
que aparecem dentro das tabelas (`wrong_output`, `accepted_predicted`, `black_box`…).

O painel tem quatro páginas, que se leem nesta ordem. Os filtros (conjunto, cenário, problema,
macrocategoria, rating, status da suíte) ficam só na barra lateral e valem para todas as páginas;
o topo de cada página diz o recorte ativo e quantos problemas ele tem. A barra lateral também
mostra a hora da última leitura e quantos problemas estão concluídos por conjunto.

- **O experimento** (abre primeiro): o contexto antes dos resultados. Os números grandes
  (problemas, falhas, IAs × cenários, suítes, testes gerados, gasto) e os gráficos de rating,
  macrocategoria, suítes por IA e status, testes por suíte e gasto por IA comercial (o modelo local
  aparece à parte, com as horas de modelo). Cada título já diz a conclusão do recorte, e cada
  gráfico fica num cartão, e os números de todos eles estão no fim, em "Ver os números desta
  página". Funciona mesmo antes de as
  métricas serem calculadas; só o gasto depende delas.
- **As métricas**: quem se saiu melhor em cada critério, no recorte da barra lateral, sempre
  pelo gabarito do AC (\*). Na ordem: o **placar** (posição de cada IA em falhas reais, mutantes,
  código correto reprovado, erro do gabarito, entrega de suíte e custo; 1º = melhor; com a contagem
  das suítes "sem raciocínio", que ficam nas métricas, e se algum 1º lugar mudaria sem elas); o
  **placar por cenário** (o mesmo placar com uma linha por IA e cenário, por exemplo SLM ·
  caixa-preta, SLM · caixa-branca, SLM · híbrido, com a posição comparando as IAs no mesmo cenário); falhas
  reais e mutantes; falsos positivos; contexto (como a detecção muda entre os cenários e o IIC, com
  a escolha do gabarito); custo; e o **guia de escolha**: em cada cenário, a melhor IA em cada
  critério, o 2º colocado e se a diferença entre os dois é significativa, um empate estatístico ou
  não testada. "Minha prioridade" só realça uma linha do guia; nenhum número muda. Não há um
  vencedor geral. O título de cada cartão é a conclusão dos números do recorte e muda com os
  filtros; "Como se calcula" mostra a fórmula do gráfico, a mesma fórmula em palavras e a conta
  feita com os números do recorte (por exemplo, "Gemini: 54.083 de 60.000 WAs → 90,1%");
  para salvar um gráfico, use o menu do próprio gráfico ("…", ao passar o mouse), em PNG ou
  SVG. No fim, as tabelas oficiais (todas as linhas de `metrics.csv` sem filtro; com filtro,
  calculadas para o recorte e marcadas assim), os testes estatísticos e o custo. Um recorte de um
  problema só não tem métrica: a página avisa e aponta a ficha do problema na Rastreabilidade. Antes de as métricas serem
  calculadas, um aviso.

**Como ler os gráficos da página As métricas** (os cenários: caixa-preta = só o enunciado,
caixa-branca = só o código, híbrido = os dois):

| Gráfico | O que mostra | Como ler |
|---|---|---|
| Placar | posição e valor de cada IA em cada critério, média dos cenários do recorte | o 1º de cada coluna fica destacado; a média dos cenários não tem teste estatístico (o teste está no guia) |
| Falhas reais (TDF\*) e mutantes (MS\*) | barras ordenadas pelo gabarito do AC; o traço é o valor pelo gabarito da IA | mais alto é melhor; a distância entre a barra e o traço é a "detecção" que só existiu porque a IA errou a saída esperada |
| Detecta × reprova o código correto | um ponto por IA: TFP no eixo horizontal, TDF\* no vertical | o canto de cima à esquerda (sombreado) é o ideal: detecta muito e reprova pouco o código correto |
| Variação entre cenários | a TDF\* de cada IA em cada cenário | linha reta = o contexto quase não muda a detecção daquela IA |
| IIC | quanto o híbrido ganha (azul, acima de 0) ou perde (vermelho) sobre a caixa-preta ("+ código") e sobre a caixa-branca ("+ requisito"), somando os problemas | acima de 0, juntar os dois ajudou; abaixo, atrapalhou; o seletor troca o gabarito |
| Custo | US$ gastos para cada 1.000 WAs detectados, só nos modelos comerciais | mais baixo é melhor; o custo não se divide por problema |
| Guia de escolha | em cada cenário, a melhor IA em cada critério e o 2º colocado | "diferem" = diferença significativa; "empate" = sem diferença estatística; "não testado" = não há teste para esse critério ou recorte |
| De apoio (recolhidos) | TDF × TDF\* por cenário; falsos positivos por causa; o IIC problema a problema | detalham os gráficos acima |

As duas últimas páginas:

- **Rastreabilidade**: de onde vem cada número. Em "O que você quer rastrear?", escolha um caso
  (combinações sem suíte, com o motivo e as tentativas; suítes "sem raciocínio"; origem da suíte do
  modelo local; qual teste reprovou um WA ou mutante; o que um teste derrubou; por que o AC foi
  reprovado; detecções que só existem por um gabarito; WAs que nenhuma IA detectou; WAs que só uma
  detectou; mutantes que sobreviveram; de onde vem o IIC; ficha de um problema). "De onde vem o
  IIC" mostra, para uma IA, uma direção e um gabarito, os WAs que ela pegou em cada cenário (R =
  caixa-preta, C = caixa-branca, H = híbrido) nas 8 regiões dos três conjuntos, a conta do IIC
  com esses números (e quais regiões somam em cada termo, para conferir à mão), a tabela por
  problema e, ao abrir um problema, os 100 WAs com o papel de cada um (ganho, perda, os dois,
  nenhum); o filtro de cenário não vale nesse caso. A lista segue os filtros e "Abrir"
  mostra o item: a combinação (status, origem, motivo, tentativas, testes com a saída do AC), o alvo
  (quem o detectou e com qual teste, e o código ao lado do AC) ou o problema (enunciado, AC e as 15
  combinações). Cada alvo para no primeiro teste que o reprova, então o "teste que reprovou" é sempre
  o primeiro. Os casos de alvos precisam do `results.csv` de cada conjunto, que vem no pacote da
  avaliação; as tentativas e o código precisam das suítes, do dataset e dos mutantes descompactados.
- **A avaliação** (a última): duas abas.
  - **Comparações**: a diferença entre o oráculo declarado e o corrigido por combinação (em
    vermelho, as com o AC reprovado), e o modelo local (suíte final e 1ª tentativa) ao lado dos
    comerciais.
  - **Combinação**: escolha conjunto, problema e cenário e veja, teste a teste, a entrada, a saída
    esperada escrita na suíte, a saída real do `AC_ref`, o veredito do AC e quantos alvos cada teste
    detectou em cada oráculo; a lista dos alvos que só o oráculo declarado pegou; e, para um alvo,
    onde foi detectado e o código dele ao lado do `AC_ref`, com as diferenças destacadas.

**Prévia**: as porcentagens de detecção do painel (detectados ÷ total, somados só sobre as
combinações com suíte) são uma prévia, sempre marcada assim. Os números oficiais (TDF, MS e as
demais) vêm do módulo de métricas. Cada tabela tem um botão para baixar o CSV
já filtrado (vai para a pasta de downloads do navegador, não para o repositório).

**Durante uma avaliação em andamento**, os dados são lidos ao abrir e guardados; clique em
**recarregar dados** para ver os problemas concluídos depois disso.

### Cópia pública (Streamlit Community Cloud)

O mesmo painel, só de leitura, pode ficar na internet no **Streamlit Community Cloud** (gratuito).
Ele copia o repositório do GitHub e abre o painel num endereço `https://<nome>.streamlit.app`. A
cópia pública mostra os pacotes versionados (avaliação, métricas, dataset, mutantes e suítes), não
a pasta `data/` da sua máquina: na primeira abertura ela descompacta os zips (cerca de 40 s) e
depois abre direto. Ela mostra o que está commitado e enviado ao GitHub (`git push`), na branch
escolhida.

1. Entre em **share.streamlit.io** com uma conta do GitHub que tenha acesso ao repositório
   `tcc-engenharia-software/ai-testgen-evaluator` (o repositório é de uma organização: se ele
   não aparecer na lista, autorize a organização para o Streamlit no GitHub, em *Settings →
   Applications*, ou peça a um dono da organização; se for privado, autorize também o acesso a
   repositórios privados quando o site pedir).
2. **Create app** → *Deploy a public app from GitHub* e preencha: repositório
   `tcc-engenharia-software/ai-testgen-evaluator`, branch `main`, *Main file path*
   `src/dashboard/public/streamlit_app.py` (não o `src/dashboard/app.py`); em *Advanced
   settings*, Python **3.11**. Escolha o endereço e clique em **Deploy**.
3. A primeira construção instala as dependências de `src/dashboard/public/requirements.txt` e leva
   alguns minutos; acompanhe em *Manage app*. Cada `git push` na branch atualiza o painel sozinho.

Quem pode ver: em *Settings → Sharing* do app. Com o repositório privado, dá para liberar só para
e-mails convidados. Sem visitas por 12 horas o app "dorme"; quem abrir o endereço o acorda.

Para testar como ficará, na sua máquina, com o painel normal: os comandos acima mostram as mesmas
páginas sobre os mesmos pacotes descompactados.

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m dashboard serve` | `app` | abre o painel; rode com `-p 127.0.0.1:8501:8501` no `docker compose run`. `--evaluation-dir DIR` (padrão `data/evaluation`; por exemplo, uma pasta de conferência ou um piloto guardado; também pode ser trocada no próprio painel), `--port N` (padrão `8501`; a publicada no `-p` tem de ser a mesma). Ctrl+C fecha. Códigos: `0` fechado, `2` pasta inexistente, `3` biblioteca do painel ausente na imagem |
| `pytest tests/dashboard` | `sandbox` | testes do módulo |

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `error: streamlit is not installed in the image` (`3`) | `docker compose build` |
| a cópia pública mostra um erro | abra *Manage app* no canto inferior direito do app para ver o registro; *Reboot app* refaz a abertura |
| a cópia pública falha em `from dashboard import ...`, no `src/dashboard/app.py` | o app foi criado com o *Main file path* errado: apague o app (⋮ → *Delete*) e crie de novo com `src/dashboard/public/streamlit_app.py` |
| `error: not a folder: data/evaluation` (`2`) | ainda não há avaliação: rode `python -m evaluation run` (README do módulo `evaluation`) ou aponte `--evaluation-dir` |
| o navegador não abre `localhost:8501` | confira o `-p 127.0.0.1:8501:8501` no comando e se outro programa já usa a porta (troque as duas, `-p` e `--port`) |
| "Nenhum resultado concluído" | a avaliação ainda não fechou nenhum problema; espere e clique em **recarregar dados** |
| "arquivo(s) inválido(s)" na barra lateral | um resultado não confere com o formato da avaliação; avise os autores com o nome do arquivo |
| "A suíte não está descompactada" ou "Código não disponível" | descompacte as suítes, o dataset ou os mutantes (Cenário B dos módulos) |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/evaluation/<conjunto>/problems/<id>/<cenário>.json` | JSON | `python -m evaluation run` ou o pacote de avaliação descompactado |
| `data/suites/...` (a pasta indicada na origem de cada resultado) | JSON | suítes descompactadas (para a entrada e a saída esperada) |
| `data/dataset/problems/<id>/` (`metadata.json`, `AC_ref.cpp`, `WA_<n>.cpp`) e `data/mutants/problems/<id>/Mutant_<n>.cpp` | JSON e C++ | dataset e mutantes descompactados (macrocategoria e código lado a lado) |

## (d) Saídas produzidas

Nenhuma no repositório. Só a página no navegador e, quando você pede, o CSV de uma tabela ou um
gráfico (pelo menu do gráfico), baixados pelo navegador. Só a cópia pública descompacta os pacotes em `data/`, no servidor
dela.

## (e) Dependências e pré-requisitos

- Python 3.11, Streamlit 1.66.1 e pandas 3.0.6 (fixados no `uv.lock`), na imagem
  (`docker compose build`).
- Serviço `app` com a porta publicada; nenhuma variável de ambiente nem segredo; não chama IA nem
  executa código de terceiros.

## (f) Limitações conhecidas

- O tempo para abrir com a avaliação completa (3.000 combinações) ainda não foi medido; com os 15
  resultados da conferência de um problema, cada página abriu em até 1,6 s (medido em 2026-11-05).
- As porcentagens são uma prévia; as métricas oficiais só aparecem depois do módulo de métricas.
- Na cópia pública, o campo "Pasta de avaliação" da barra lateral continua editável; ele só lê
  resultados no formato da avaliação, no servidor da cópia.
- O painel não executa código: para saber o que um WA respondeu num teste, compare o código dele
  com o do `AC_ref` no detalhe do alvo.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 8 (histórico)
- Avaliação: [README do módulo `evaluation`](../evaluation/README.md)
- Testes: `tests/dashboard/` (`docker compose run --rm sandbox pytest tests/dashboard`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `serve` | pendente | — |
