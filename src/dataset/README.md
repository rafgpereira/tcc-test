# Módulo `dataset`

> **Status**: em implementação · **Feature**:
> `specs/001-dataset-extraction/` · **Metodologia**: `docs/metodologia-referencia.md`, seção 1

## (a) Propósito

Extrai do dataset `code_contests`, em streaming, os problemas elegíveis do experimento e os classifica em macrocategorias, para depois validar seu código C++ e empacotar o dataset verificável.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando):
baixar o projeto, criar o `.env`, criar a pasta `data/`, construir a imagem e conferir com o
`pytest`. Sem isso os comandos abaixo não funcionam. Todos rodam **dentro do Docker**, no serviço
`app`, que tem acesso à internet (o serviço `sandbox` não tem, por isso não serve para baixar o
dataset). Rode-os na pasta do repositório.

### O que este módulo faz, na prática

Lê o dataset público `code_contests` no Hugging Face **em streaming** (lê aos poucos, sem baixar o
dataset inteiro para o disco), separa os problemas que servem ao experimento (critérios de
elegibilidade da metodologia, seção 1.2), classifica cada um em uma macrocategoria e guarda na sua
máquina, dentro de `data/work/`, o enunciado, os testes e os códigos C++ de cada problema
elegível. Cerca de 1.279 problemas são esperados (medição de 2026-09-19). **Ainda não valida** se os
códigos funcionam: isso vem nas próximas etapas da feature.

`extract` é a **fase 1 de 5** do ciclo do módulo (`extract`, `validate`, `audit`, `package`,
`verify`); só `extract` e `report` existem hoje. O ciclo completo é feito **uma vez, por um dos
autores**, que publica no Git o `data/dataset.zip` e os manifestos; o outro autor só descompacta e
confere, sem rodar nada disso. O que cada fase faz, o que sobra em `data/work/` e como cada autor e o
Docker de cada um se encaixam estão em
[Como o dataset circula entre os autores](../../README.md#como-o-dataset-circula-entre-os-autores),
no README da raiz.

### Passo a passo

1. **Teste rápido (opcional, poucos minutos).** Confirma que a rede e as permissões funcionam antes
   da extração longa; lê só as primeiras 400 linhas de cada parte do dataset:

   ```bash
   docker compose run --rm app python -m dataset extract --limit-rows 400
   ```

   Se você fez o teste rápido, apague o resultado antes do passo 2, para começar limpo:
   `rm -rf data/work`. **Atenção**: isso só é inofensivo enquanto a validação dos códigos não
   existe; depois dela, `data/work/` também guarda os problemas já validados (horas de execução),
   e apagá-la os perde.

2. **Extração completa.** Lê os três splits (`train`, `valid`, `test`) e grava o pool:

   ```bash
   docker compose run --rm app python -m dataset extract
   ```

   A spec estima **30 minutos ou mais** (tempo e volume de transferência ainda serão medidos na
   primeira execução real). Pode apertar Ctrl+C e repetir o mesmo comando depois: só o trecho
   (shard) em andamento é refeito. Durante a execução aparece uma linha por trecho, no formato
   `train shard 3/N: 350 rows, 12 eligible` (número de linhas lidas e de problemas elegíveis
   naquele trecho; `already done` quando ele já estava pronto de uma execução anterior). No fim
   aparecem `read R rows; M eligible problems`, uma linha com o total por macrocategoria
   e `report:` com o caminho do relatório.

3. **Conferir o resultado.** Veja o código de saída (`echo $?`, esperado `0`) e abra os arquivos,
   que estão na sua pasta `data/work/` (não dentro de um contêiner):

   ```bash
   ls data/work/staging                       # pool.json, raw/ e shards/
   less data/work/reports/extraction_report.md   # funil de elegibilidade e distribuição
   ```

   No relatório, confira o funil (quantos problemas cada critério eliminou) e a distribuição do
   pool por macrocategoria. Os números medidos em 2026-09-19 foram 13.610 linhas lidas e 417 / 285 /
   577 problemas em `estrutural_otimizacao` / `matematica` / `logica_direta`; se os seus diferirem,
   avise os autores, porque a documentação precisa ser corrigida.

4. **Regenerar o relatório (opcional).** Refaz o relatório a partir dos arquivos já gravados, sem
   baixar nada:

   ```bash
   docker compose run --rm app python -m dataset report
   ```

   Enquanto a validação não existir, a amostra aparece vazia; é o esperado.

### Se algo der errado

| O que aparece | O que significa | O que fazer |
|---|---|---|
| `infrastructure failure: ...` (código `3`) | falha de rede ou de disco ao ler o dataset | rode o mesmo comando de novo; a extração retoma do último trecho concluído |
| `interrupted; it is safe to run the command again` (código `130`) | você apertou Ctrl+C | rode o mesmo comando de novo |
| `error: no pool found; run ...` (código `1`) | você rodou `report` antes de `extract` | rode `extract` primeiro |
| `error: --splits must list ...` (código `2`) | valor inválido em `--splits` | use `train`, `valid` e/ou `test`, separados por vírgula |
| `PermissionError` ao gravar em `data/` | `data/` pertence a `root` (o passo 3 do guia foi pulado) | `sudo chown -R "$(id -u):$(id -g)" data` e rode de novo |
| quer recomeçar do zero | — | `rm -rf data/work` e rode o passo 2 (só enquanto a validação não existe: depois dela essa pasta guarda os problemas validados) |

### Opções de `extract`

| Opção | Padrão | Efeito |
|---|---|---|
| `--seed INT` | `42` | seed da ordem de processamento; fica gravada no pool (não mude sem combinar: muda a seleção) |
| `--splits LIST` | `train,valid,test` | splits lidos, nesta ordem (a primeira ocorrência de um problema vence) |
| `--limit-rows N` | sem limite | limita as linhas lidas por split (só para testes rápidos) |

Códigos de saída: `0` sucesso, `1` falha de dados (por exemplo, `report` sem pool), `2` uso
incorreto, `3` falha de infraestrutura (rede; repita o comando para retomar), `130` interrompido.
Os subcomandos de validação, auditoria, empacotamento e verificação serão documentados aqui, no
mesmo formato de passo a passo, quando existirem.

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| Dataset `deepmind/code_contests` | streaming Parquet pela biblioteca `datasets`, na revisão `802411c3010cb00d1b05bad57ca77365a3c699d6` | Hugging Face (público; licença CC-BY-4.0) |
| `HF_TOKEN` (opcional) | variável de ambiente, lida do `.env` | só aumenta o limite de requisições |
| Opções de linha de comando | `--seed`, `--splits`, `--limit-rows` | quem executa |

## (d) Saídas produzidas

Tudo em `data/work/`, um diretório privado (permissão `0700`) e ignorado pelo Git. Como `./data`
é um volume do Compose, os arquivos aparecem no host, em `data/work/` na raiz do repositório, com o
seu usuário como dono; o contêiner não guarda nada que não esteja lá. Esses arquivos são o **espaço
de trabalho de quem gera o dataset**: ficam só na sua máquina, não vão para o Git, e nenhum comando
os apaga (a extração não tem etapa de limpeza). O que será distribuído é o zip que a fase `package`
ainda vai gerar, com apenas os problemas completos.

| Saída | Formato | Destino |
|---|---|---|
| `data/work/staging/pool.json` | JSON, modelo `Pool` ([data-model.md](../../specs/001-dataset-extraction/data-model.md), §2.1) | lido pela validação e por `report` |
| `data/work/staging/raw/<problem_id>.json.gz` | JSON comprimido, modelo `RawProblem` | lido pela validação dos códigos |
| `data/work/staging/shards/<split>-<NNNNN>.json` | JSON, modelo `ShardCheckpoint` | marca o shard como concluído (retomada) |
| `data/work/reports/extraction_report.json` e `.md` | JSON e Markdown, modelo `ExtractionReport` | leitura humana e citação no trabalho escrito |

## (e) Dependências e pré-requisitos

- Python 3.11.16, `datasets` 5.0.1 e `pydantic` 2.x, fixados no `uv.lock`.
- Serviço `app` do Docker Compose (com rede). O ambiente é construído com `docker compose build`.
- `.env` com `HOST_UID` e `HOST_GID` do seu usuário (saídas de `id -u` e `id -g`); `HF_TOKEN` é opcional. Passo 2 do guia da raiz.
- Diretório `data/` criado por você (`mkdir -p data`) antes do primeiro `docker compose run`: o
  Git não o versiona, e, se ele não existir, o Docker o cria como root e o serviço `app` (que roda
  com o seu usuário) não consegue gravar nele. Passo 3 do guia da raiz; se já aconteceu, o
  `chown` da tabela "Se algo der errado", na seção (b), resolve.
- Nenhum módulo anterior precisa ter rodado.

## (f) Limitações conhecidas

- Problemas que leem e escrevem por arquivo (`input.txt` e `output.txt`) são excluídos, porque o
  motor injeta a entrada por `stdin`: 9 problemas medidos em 2026-09-19 (metodologia, seção 1.2).
- O pool esperado é de cerca de 1.279 problemas (medição de 2026-09-19); o número real desta
  implementação será confirmado na primeira extração real.
- Em `valid` e `test` a mediana é de ~101 submissões incorretas em C++ por problema, então poucos
  vão alcançar 100 falhas validadas (metodologia, seção 1.7).
- O streaming lê todas as colunas de cada linha (não há projeção de colunas); o tempo e o volume de
  transferência da extração completa serão medidos na primeira execução real.
- A validação dos códigos e o empacotamento ainda não existem: `report` mostra uma amostra vazia.

## Referências

- Contratos: [cli.md](../../specs/001-dataset-extraction/contracts/cli.md) e
  [data-model.md](../../specs/001-dataset-extraction/data-model.md)
- Testes: `tests/dataset/` (`docker compose run --rm sandbox pytest tests/dataset`)

## Comandos verificados

| Comando | Verificado em | Revisão | Tarefa |
|---|---|---|---|
| `extract` | pendente | — | — |
| `report` | pendente | — | — |
