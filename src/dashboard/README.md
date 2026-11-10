# Módulo `dashboard` (painel dos resultados)

> **Status**: em implementação (código e testes prontos; conferência com os autores pendente) · **Metodologia**: `docs/metodologia-referencia.md`, seção 8

## (a) Propósito

Mostra num painel no navegador, só para leitura, os resultados da avaliação das suítes: o que já foi avaliado, cada combinação teste a teste e as comparações entre oráculos e modelos.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando).
Depois de um `git pull` que trouxe este módulo, rode `docker compose build` uma vez (a imagem
ganhou a biblioteca do painel). O painel lê o que já existe; não gera nenhum artefato e não grava
nada: a pasta de avaliação de um `python -m evaluation run` em andamento (o piloto, por exemplo) ou
os pacotes de avaliação descompactados (README do módulo [`evaluation`](../evaluation/README.md)).
Para o detalhe completo, também o dataset, os mutantes e as suítes descompactados.

```bash
docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve
```

Abra **http://localhost:8501** no navegador. O comando roda no serviço `app` e publica a porta só
para esta máquina (`127.0.0.1`): ninguém da rede alcança o painel, e ele não consulta nada na
internet. Ele fica no ar até Ctrl+C no terminal.

**Siglas**: passe o mouse sobre o nome de uma coluna ou sobre uma sigla (AC, WA, TLE, TDF…) para
ver o nome completo e o que significa; o **Glossário**, na barra lateral, explica também os valores
que aparecem dentro das tabelas (`wrong_output`, `accepted_predicted`, `black_box`…).

O painel tem quatro páginas, com os filtros (conjunto, cenário, problema, macrocategoria, status da
suíte) na barra lateral, que também mostra a hora da última leitura e quantos problemas estão
concluídos por conjunto:

- **Visão geral**: por conjunto e cenário, as combinações avaliadas e sem suíte, o AC aprovado e
  reprovado, os testes do AC com saída diferente ou com erro, os WAs e mutantes detectados em cada
  oráculo e os testes instáveis; e uma linha por combinação.
- **Combinação**: escolha conjunto, problema e cenário e veja, teste a teste, a entrada, a saída
  esperada escrita na suíte, a saída real do `AC_ref`, o veredito do AC e quantos alvos cada teste
  detectou em cada oráculo; a lista dos alvos que só o oráculo declarado pegou; e, para um alvo, onde
  foi detectado e o código dele ao lado do `AC_ref`, com as diferenças destacadas.
- **Comparações**: a diferença entre o oráculo declarado e o corrigido por combinação (em vermelho,
  as com o AC reprovado), e o modelo local (suíte final e 1ª tentativa) ao lado dos comerciais.
- **Métricas**: os gráficos das métricas, nas cores do tema escolhido (claro ou escuro), um painel
  por cenário quando há muitas barras, com o valor escrito em cada barra (o total, na TFP por causa;
  a mediana, em cada caixa do IIC; o custo em US$ por 1.000 WAs detectados), filtrados pelos mesmos filtros da barra lateral (conjunto, cenário, problema,
  macrocategoria, status; o filtro de problema precisa de pelo menos 2); os botões **PNG**,
  **SVG** e **PDF** embaixo de cada gráfico baixam o gráfico exatamente como aparece na tela (no
  tema claro ou escuro), com o filtro e a fonte no subtítulo; no tema claro, é a mesma figura do
  comando `python -m metrics figures`. Abaixo, **quantos WAs e mutantes a IA matou** (de 100 de
  cada por problema) e as tabelas oficiais (com o corte por
  macrocategoria ou status), os testes estatísticos e o custo; antes de as métricas serem
  calculadas, um aviso.

**Prévia**: as porcentagens de detecção do painel (detectados ÷ total, somados só sobre as
combinações com suíte) são uma prévia, sempre marcada assim. Os números oficiais (TDF, MS e as
demais) e as figuras do texto vêm do módulo de métricas. Cada tabela tem um botão para baixar o CSV
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
   `rafgpereira/tcc-test` (se o repositório for privado, autorize o acesso a repositórios
   privados quando o site pedir).
2. **Create app** → *Deploy a public app from GitHub* e preencha: repositório `rafgpereira/tcc-test`,
   branch `main`, *Main file path* `src/dashboard/public/streamlit_app.py`; em *Advanced
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

Nenhuma no repositório. Só a página no navegador e, quando você pede, o CSV de uma tabela ou uma
figura, baixados pelo navegador. Só a cópia pública descompacta os pacotes em `data/`, no servidor
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
