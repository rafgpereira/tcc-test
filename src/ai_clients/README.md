# Módulo `ai_clients` (geração de suítes de teste pelo modelo local)

> **Status**: em implementação · **Metodologia**: `docs/metodologia-referencia.md`, seção 3

## (a) Propósito

Gera, para cada problema do dataset e cada um dos três cenários de contexto, uma suíte de casos de teste com o modelo local Qwen2.5-Coder-14B (`qwen2.5-coder:14b`, via Ollama), cuja saída esperada é calculada executando de verdade uma solução em Python escrita pelo próprio modelo, para alimentar a etapa de avaliação.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
e tenha o dataset descompactado em `data/dataset/`
([README do módulo `dataset`](../dataset/README.md), Cenário B).

**Este módulo ainda está em implementação.** Todos os comandos existem; `generate`, `execute` e
`report` já rodaram com o modelo de verdade em pilotos de 5 problemas, mas a execução completa dos
200 problemas ainda não foi feita, e o pacote `data/slm_suites.zip` ainda não existe.

Para cada problema e cada cenário — **caixa-preta** (o modelo vê só o enunciado), **caixa-branca**
(só a solução de referência em C++) e **híbrido** (os dois) — o modelo recebe um único pedido, sem
memória de pedidos anteriores, e responde com duas coisas: **entradas de teste** que exploram casos
difíceis e uma **solução do problema em Python**. O modelo nunca diz qual é a saída certa: ela é
obtida rodando essa solução Python sobre cada entrada, isolada, sem internet. A solução Python só é
aceita se acertar os testes públicos do problema; se errar, ou se a resposta do modelo não puder
ser lida, é feito um novo pedido, com outra seed ou outra temperatura, até 12. **Nenhum problema
e cenário fica sem suíte**: sem acerto nos 12, entram, nesta ordem, uma suíte de **reserva** e até 3
pedidos em que o próprio modelo escreve as saídas (**predição**); se nem isso funcionar, os autores
fecham o caso à mão (passo 3). Detalhes da decisão:
[`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 3.

O trabalho tem duas etapas, cada uma num serviço do Docker Compose:

1. **Geração** (serviço `app`, com internet, para falar com o Ollama): envia os pedidos e guarda
   cada resposta do modelo exatamente como veio, sem executar nada.
2. **Execução** (serviço `sandbox`, sem internet, o único autorizado a executar código de
   terceiros): roda as soluções Python e calcula as saídas esperadas.

### Cenário A — Rodar do zero

**Preparar o Ollama e o `.env`.** Num servidor Ollama (nesta máquina ou em outra), baixe o modelo
com `ollama pull qwen2.5-coder:14b`. No `.env` (o arquivo de configuração na raiz do projeto, ver
`.env.example`), preencha:

- `OLLAMA_BASE_URL` — o endereço do Ollama: `http://host.docker.internal:11434` se ele roda nesta
  máquina (o serviço `app` enxerga a máquina por esse nome), ou `http://<servidor>:11434` se roda
  em outra;
- `OLLAMA_HARDWARE_LABEL` — um texto que descreve a máquina onde o Ollama roda (placa de vídeo,
  processador, memória), gravado junto de cada resposta; nunca é detectado sozinho.

Opcionais: `OLLAMA_HTTP_TIMEOUT_S` (quanto esperar por uma resposta, padrão 900 segundos; aumente
se o Ollama roda sem placa de vídeo) e `OLLAMA_MAX_INFRA_RETRIES` (quantas vezes seguidas a mesma
chamada é repetida se o Ollama não responder, padrão 30). `OLLAMA_MODEL` troca o modelo (padrão
`qwen2.5-coder:14b`, o do experimento), só para um piloto que compara modelos; ele precisa estar
instalado no Ollama (`ollama pull <modelo>`), e trocar de modelo exige uma execução nova. A seed e a
temperatura de cada pedido não se configuram: vêm da tabela do passo 3.

**Uma execução nova sempre começa numa pasta vazia.** Se `data/suites/slm/` já tem uma execução
terminada ou de uma versão anterior deste módulo, mova-a antes do primeiro `generate`:
`mv data/suites/slm data/suites/slm-<nome>`. Uma execução de versão anterior é recusada por todos
os comandos, com código `2` e essa mesma instrução.

**1. Conferir o que seria enviado, sem chamar o modelo:**

```bash
docker compose run --rm app python -m ai_clients generate --dry-run
```

Não grava nada nem precisa do Ollama. Imprime uma linha por pedido previsto
(`<id> <cenário> attempt 1 seed 42 temperature 0.7: prompt <N> chars`) e, no fim, `dry run: 600 calls planned` e o
maior pedido de cada cenário. Medido em 2026-10-04 sobre os 200 problemas, com o texto do pedido
daquela data: 600 pedidos; o maior tinha 8.074 caracteres (híbrido de `61_B`). Com o texto atual,
medido em 2026-10-06 nos 5 problemas do piloto, o maior tem 8.370 caracteres (o mesmo `61_B`). Antes
de listar, o comando confere o dataset inteiro contra o manifesto, o que pode levar alguns minutos.

**2. Gerar:**

```bash
docker compose run --rm app python -m ai_clients generate
```

A primeira execução cria `data/suites/slm/run.json` (qual modelo, com quais parâmetros, sobre qual
dataset e a tabela de seeds e temperaturas). Para cada problema e cenário, grava em
`data/suites/slm/problems/<id>/<cenário>/` um arquivo `attempt_<n>.generation.json` com a resposta
do modelo, o que foi lido dela e a fase, a seed e a temperatura usadas, e imprime uma linha por
pedido, como `1000_B black_box attempt 1 seed 42: parsed (7 inputs) — 1570+812 tokens,
stop, 21.5 s` (exemplo ilustrativo, não medido). Duas correções fixas na leitura, contadas no
relatório: se o modelo embrulhar o código Python inteiro numa cerca Markdown (```` ```python ````
… ```` ``` ````), ela é tirada; uma entrada vazia é descartada sozinha. Se a resposta não puder ser
lida (`unparseable (...)`), o pedido seguinte da tabela é feito na hora. O mesmo vale quando o
próprio modelo trava repetindo texto e o Ollama interrompe o pedido (`model failure (repetition) —
... token repeat limit reached`): conta como tentativa perdida e segue para o pedido seguinte, sem
esperar. Se a tentativa perdida for a 12ª e uma das 12 puder ser reserva (passo 3), a combinação
termina na hora e grava `suite.json` (`<id> <cenário>: suite recorded (accepted_fallback)`). Os
pedidos 13 a 15 usam um segundo texto, `src/prompt_templates/slm_predict_prompt.txt`, que pede
entradas **e** saídas esperadas, sem solução Python (`parsed (<k> tests)`); a primeira resposta
lida já vira a suíte (`accepted_predicted`), sem passar pelo `execute`. Nessas respostas, uma cerca
Markdown em volta de uma entrada ou saída inteira também é tirada e contada. Se as 3 não puderem
ser lidas, a combinação fica aguardando os autores (`<id> <cenário>: awaiting manual handling`).
No fim: `done: N calls, N parsed, N unparseable, N repetition; suites: N accepted_fallback, N
accepted_predicted; N pending execution, N awaiting manual handling`, seguido de uma linha
`manual: ...` por combinação que aguarda os autores, com o comando `close` a usar, e saída com
código `4` (os demais problemas e cenários foram tratados normalmente).

Rodar de novo exige `--resume` (proteção contra continuar por engano uma execução antiga):
`docker compose run --rm app python -m ai_clients generate --resume`.

**3. Executar as soluções Python e calcular as saídas esperadas:**

```bash
docker compose run --rm sandbox python -m ai_clients execute
```

Roda no serviço `sandbox`, sem internet. Para cada resposta lida e ainda não executada, roda a
solução Python do modelo primeiro sobre os testes públicos do problema (na ordem do `testes.json`,
parando no primeiro erro) e, se acertar todos ou se o primeiro erro for uma resposta errada (WA,
para a tentativa poder virar reserva), sobre cada entrada gerada; a saída de cada execução é a
saída esperada daquele teste. Cada execução começa numa pasta vazia, sem rede, como um usuário sem privilégios, e
só com a biblioteca padrão do Python. Os limites vêm do próprio problema (`metadata.json`), com
folga para o Python ser mais lento e gastar mais memória que o C++: **10 vezes** o limite de tempo
e **4 vezes** o de memória (um problema de 2 s e 256 MiB vira 20 s e 1 GiB). Uma entrada que
estoura o tempo, termina com erro ou escreve algo que não é texto UTF-8 é descartada sozinha; as
outras ficam.

Grava `attempt_<n>.execution.json` ao lado da resposta e imprime uma linha por tentativa:
`accepted (<k> kept, <d> discarded)`, `public_test_failed (test <i>: <veredito>)` (a solução errou
um teste público; o arquivo guarda o começo do que ela imprimiu, o final das mensagens de erro, o
tempo e a memória daquele teste; num WA a linha termina em `; <k> kept, <d> discarded)`, porque as
entradas rodaram) ou `all_inputs_failed (<t> timeout,
<r> runtime_error)` (nenhuma entrada sobrou). Se aceitou, grava `suite.json` com os testes da
suíte (`input` e `output`) e `status: accepted`.

**De onde vem a suíte de cada problema e cenário.** Cada pedido tem a seed e a temperatura de uma
tabela fixa, gravada no `run.json` (nenhum par se repete):

| Pedidos | Fase | Seed | Temperatura | O que se pede |
|---|---|---|---|---|
| 1 a 6 | 1 | 42, 43, 44, 45, 46, 47 | 0.7 | entradas e solução Python |
| 7 a 12 | 2 | 48 | 0.7, 0.6, 0.5, 0.4, 0.3, 0.2 | entradas e solução Python |
| 13 a 15 | 4 | 49, 50, 51 | 0.7 | entradas e saídas (predição) |

E a suíte sai do primeiro destes casos que acontecer (o `status` e o `accepted_phase` do
`suite.json` dizem qual; `accepted_attempt`, de qual pedido vieram os testes):

| Fase | Quando | `status` | As saídas esperadas vêm de |
|---|---|---|---|
| 1 ou 2 | um dos pedidos 1 a 12 traz uma solução que acerta todos os testes públicos (os pedidos param aí) | `accepted` | uma solução que acertou os exemplos |
| 3 | nenhum dos 12 acertou: a melhor das soluções que erraram um teste público **só por WA** e mantiveram alguma entrada (mais testes públicos certos, depois mais entradas, depois o menor número), sem novo pedido | `accepted_fallback` | uma solução que **sabidamente erra** em algum caso |
| 4 | nenhum dos 12 serve nem como reserva: até 3 pedidos de predição (passo 2), o primeiro lido vira a suíte | `accepted_predicted` | o próprio modelo, **sem nenhuma execução nem conferência** |
| 5 | nem as 3 predições puderam ser lidas: a combinação aguarda os autores, que a fecham com `close` (abaixo) | `discarded_manual` | — (sem testes; o motivo fica gravado) |

Cada pedido do `suite.json` traz a fase, a seed, a temperatura, o texto usado (`template`) e se
podia ser reserva (`fallback_eligible`). No fim: `done: N executed, N accepted, N failed (N need a
new generation); suites: N accepted_fallback; N awaiting manual handling`, com as linhas
`manual: ...` e o código `4` como no `generate`.

**4. Alternar até acabar.** Uma tentativa que falhou na execução precisa de um novo pedido ao
modelo, com a linha seguinte da tabela, e isso é a etapa de geração. Enquanto o `execute` terminar com a linha
`next: docker compose run --rm app python -m ai_clients generate --resume ...`, rode esse comando
e depois o `execute` de novo. A linha repete os mesmos `--problem` e `--scenario` com que o
`execute` foi chamado, então num piloto basta copiá-la. Quando o `execute` não imprimir mais
`next:`, todo problema e cenário selecionado tem `suite.json`, exceto os que aguardam os autores
(código `4`).

**Com duas máquinas de Ollama ao mesmo tempo** (por exemplo, duas placas de vídeo, cada uma com o
seu endereço): dois `generate --resume` podem rodar juntos, cada um com o seu `OLLAMA_BASE_URL`
(o `-e` do `docker compose run` vale mais que o `.env`) e a sua metade dos problemas; o
`OLLAMA_HARDWARE_LABEL` vem do `.env` nos dois. Cada problema e cenário é tratado por um comando de
cada vez: se dois pegarem o mesmo, o segundo o pula, imprime `<id> <cenário>: skipped (in use by
another command)` e soma `N skipped (in use by another command)` no resumo; com metades separadas,
isso não acontece. As duas máquinas precisam ter o mesmo modelo e a mesma versão do Ollama da
execução (senão o `--resume` recusa com `2`, listando o que mudou). Antes da primeira rodada,
`docker compose run --rm app python -m cli check --deep` precisa terminar com código `0`. O laço
abaixo, rodado na raiz do projeto, faz as rodadas sozinho: os dois `generate` em paralelo (um log
por máquina em `data/logs/`), um único `execute` depois que os dois terminam, de novo enquanto o
`execute` imprimir `next:`, e o relatório no fim. Ele para com uma mensagem dizendo qual máquina
falhou se um `generate` sair com `3` (Ollama ou túnel fora do ar) ou `130` (interrompido); rodá-lo
de novo continua de onde parou.

```bash
GPU0="https://ENDERECO-DA-MAQUINA-0"
GPU1="https://ENDERECO-DA-MAQUINA-1"
mkdir -p data/logs
ls data/dataset/problems | awk 'NR % 2 == 1 {printf "--problem %s ", $0}' > data/logs/half0.args
ls data/dataset/problems | awk 'NR % 2 == 0 {printf "--problem %s ", $0}' > data/logs/half1.args
explain() {  # $1 = name, $2 = exit code, $3 = log
  case $2 in
    0|4) return 0 ;;
    3)   echo "PARADO: $1 saiu com 3 (Ollama ou túnel fora do ar); veja $3, ponha-o no ar e rode o laço de novo" ;;
    130) echo "PARADO: $1 foi interrompido (130); rode o laço de novo para continuar" ;;
    *)   echo "PARADO: $1 saiu com $2; veja $3" ;;
  esac
  return 1
}
round=0
while true; do
  round=$((round + 1))
  echo "== rodada $round: dois generate =="
  docker compose run --rm -T -e OLLAMA_BASE_URL="$GPU0" app python -m ai_clients generate --resume \
    $(cat data/logs/half0.args) < /dev/null >> data/logs/gpu0.log 2>&1 &
  pid0=$!
  docker compose run --rm -T -e OLLAMA_BASE_URL="$GPU1" app python -m ai_clients generate --resume \
    $(cat data/logs/half1.args) < /dev/null >> data/logs/gpu1.log 2>&1 &
  pid1=$!
  wait $pid0; code0=$?
  wait $pid1; code1=$?
  ok=1
  explain "generate da GPU0 ($GPU0)" $code0 data/logs/gpu0.log || ok=0
  explain "generate da GPU1 ($GPU1)" $code1 data/logs/gpu1.log || ok=0
  [ $ok = 1 ] || break
  echo "== rodada $round: execute =="
  docker compose run --rm -T sandbox python -m ai_clients execute < /dev/null 2>&1 \
    | tee data/logs/execute-$round.log
  code=${PIPESTATUS[0]}
  explain "execute" $code data/logs/execute-$round.log || break
  grep -q '^next:' data/logs/execute-$round.log || { echo "== acabou: nenhum next: =="; break; }
done
docker compose run --rm app python -m ai_clients report
```

Código `4` não para o laço (os outros problemas seguem); as linhas `manual: ...` ficam nos logs, e
os autores fecham cada uma com o `close`. Se um túnel voltar com outro endereço, troque a variável
`GPU0` ou `GPU1` e rode o laço de novo.

**Fechar à mão um problema e cenário que aguarda os autores** (só depois de os autores decidirem o
que fazer com ele):

```bash
docker compose run --rm app python -m ai_clients close --problem <id> --scenario <cenário> --reason "<motivo>"
```

Grava `manual_close.json` (o motivo e a data) e o `suite.json` com `status: discarded_manual`, sem
testes; o problema continua contando no total do experimento. Imprime `<id> <cenário>: suite
recorded (discarded_manual)`. `--dry-run` só mostra o que seria gravado.

**5. Relatório (a qualquer momento):**

```bash
docker compose run --rm app python -m ai_clients report
```

Só lê `data/suites/slm/` e grava `manifests/slm_generation_report.json`: quantas combinações de
problema e cenário estão em cada `status` da tabela do passo 3, aguardando os autores ou pendentes
(por cenário e no total), a proporção de cada `status` sobre todas elas, o tamanho das suítes de
cada `status` (mínimo, quartis, máximo e histograma), quantas tentativas falharam por qual motivo
e em qual número de tentativa, entradas descartadas por motivo, e por cenário quantas respostas
foram cortadas por tamanho (`done_reason_length`), quantas cercas Markdown foram tiradas e quantas
entradas e testes previstos vazios foram descartados, *tokens*, tempo do modelo, máquinas usadas e
as seeds de cada combinação. Imprime
`report: manifests/slm_generation_report.json` e uma linha com as contagens. Pode rodar com a
execução pela metade (conta as pendentes).

**6. Empacotar a execução terminada:**

```bash
docker compose run --rm app python -m ai_clients package
```

Só funciona quando todo problema e cenário do dataset tem `suite.json` (senão recusa com `1`,
dizendo quantos faltam e quais aguardam os autores, com o comando `close`). Gera `data/slm_suites.zip` (os mesmos arquivos dão sempre o mesmo zip,
byte a byte), `manifests/slm_suites.manifest.json` (o SHA-256 de cada arquivo e do zip) e refaz o
relatório. Esses três arquivos são os que se versionam; `data/suites/` nunca é versionado.

### Cenário B — Descompactar o que já existe

Quando `data/slm_suites.zip` e `manifests/slm_suites.manifest.json` estão no repositório (depois do
`git pull`):

```bash
unzip data/slm_suites.zip -d data/
docker compose run --rm app python -m ai_clients verify --extracted data/suites/slm
```

O `unzip` recria `data/suites/slm/` exatamente como ficou na máquina que gerou. O `verify` imprime
`OK` se o zip e cada arquivo descompactado batem com o manifesto; senão, uma linha
`changed:`/`missing:`/`extra:` por arquivo divergente e `FAIL`. Para conferir também a relação com
o dataset: `docker compose run --rm app python -m cli check --deep`.

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m ai_clients generate` | `app` | pede ao modelo as entradas e a solução Python de cada problema e cenário ainda pendente e grava as respostas. `--resume` é obrigatório quando já existe `data/suites/slm/run.json` (continua a mesma execução; sem ele o comando recusa com código `2`) e recusa, também com `2`, se algo que muda as respostas mudou desde o início da execução — o modelo (ou a versão baixada dele), a versão do Ollama, os parâmetros de geração, os dois textos-base do pedido (solução e predição), o número de tentativas, o dataset ou as folgas de tempo e memória —, listando o que mudou; trocar a máquina do Ollama, o `OLLAMA_HARDWARE_LABEL` ou as esperas do `.env` é permitido. `--dry-run` só lista os pedidos previstos e o tamanho de cada um, sem Ollama e sem gravar nada. `--limit N` trata no máximo N combinações de problema e cenário (na ordem: problema em ordem alfabética, depois caixa-preta, caixa-branca, híbrido). `--problem ID` e `--scenario black_box`, `white_box` ou `hybrid` (repetíveis) restringem. Se o Ollama não responde, a mesma chamada é repetida (espera de 5 s dobrando até 60 s) sem gastar tentativa, até `OLLAMA_MAX_INFRA_RETRIES` vezes seguidas; aí o comando para com código `3` sem gravar nada daquela tentativa. Já o `token repeat limit reached` do Ollama (o modelo travou repetindo texto) é tentativa perdida (`repetition`) e segue direto para o pedido seguinte. Os pedidos 13 a 15 são de predição (segundo texto-base) e a primeira resposta lida vira a suíte na hora. Se algum problema e cenário da seleção aguarda os autores, imprime uma linha `manual: ...` por combinação, com o comando `close`, e sai com `4` depois de tratar todos os outros. Interrompido (Ctrl+C, `docker stop`), sai com `130`; rodar de novo com `--resume` refaz só a chamada que estava em andamento, com a mesma seed. Vários `generate --resume` (um por máquina de Ollama, com `-e OLLAMA_BASE_URL=...` e metades diferentes de `--problem`) e um `execute` podem rodar ao mesmo tempo: um problema e cenário em uso por outro comando é pulado (`skipped (in use by another command)`) e contado no resumo. O primeiro `generate` (sem `--resume`) roda sozinho |
| `python -m ai_clients execute` | `sandbox` | roda a solução Python de cada resposta lida e ainda não executada, sobre os testes públicos e as entradas geradas, e grava as saídas esperadas e, quando a combinação termina, o `suite.json`. Exige `data/suites/slm/run.json` (rode o `generate` antes; sem ele, código `2`); não tem `--resume`, porque sempre continua de onde parou. `--dry-run` só lista as tentativas a executar (número de entradas, de testes públicos e os limites efetivos), sem executar nem gravar nada. `--limit N`, `--problem ID` e `--scenario S` como no `generate`. Termina com `next: ...generate --resume` (com os mesmos `--problem` e `--scenario` usados no `execute`) se ainda há problema e cenário esperando um novo pedido ao modelo; as linhas `manual: ...` e o código `4` como no `generate`. Uma falha do ambiente de execução (por exemplo, rodar no serviço `app`) para com código `3` sem gravar nada daquela tentativa. Interrompido (Ctrl+C, `docker stop`), sai com `130`; rodar de novo refaz só a tentativa que estava em andamento. Pode rodar junto com `generate --resume` (pula, e conta, o problema e cenário que um deles estiver usando), mas só um `execute` por vez |
| `python -m ai_clients close --problem ID --scenario S --reason "TEXTO"` | `app` | fecha à mão **um** problema e cenário que aguarda os autores: grava `manual_close.json` (motivo e data) e o `suite.json` com `status: discarded_manual`. As três opções são obrigatórias; motivo vazio, combinação em outro estado ou problema fora do dataset → `2`, sem gravar nada. `--dry-run` só mostra o que seria gravado. Exige o `run.json` (código `2` sem ele). Recusa (`1`) se outro comando estiver rodando |
| `python -m ai_clients report` | `app` | grava `manifests/slm_generation_report.json` com os números da execução, lendo só `data/suites/slm/`; pode rodar a qualquer momento. Exige o `run.json` (código `2` sem ele); combinação danificada → `1`, sem gravar o relatório |
| `python -m ai_clients package` | `app` | gera `data/slm_suites.zip`, `manifests/slm_suites.manifest.json` e refaz o relatório; recusa (`1`) se algum problema e cenário do dataset não tem `suite.json` (inclusive os que aguardam os autores, listados com o comando `close`) ou se há combinação danificada. Não tem `--problem` nem `--scenario`: o pacote é sempre da execução inteira. Recusa (`1`) se outro comando estiver rodando |
| `python -m ai_clients verify` | `app` | confere `data/slm_suites.zip` contra o manifesto; `--extracted data/suites/slm` confere também a pasta descompactada, arquivo a arquivo. `0` se tudo bate, `1` se não, `2` sem o manifesto |
| `unzip data/slm_suites.zip -d data/` | (máquina) | descompacta as suítes em `data/suites/slm/` |

Códigos de saída: `0` sucesso, `1` falha de dados, `2` uso incorreto, `3` falha de infraestrutura
ou de configuração do Ollama, `4` terminou, mas algum problema e cenário aguarda os autores
(`close`), `130` interrompido. Os códigos `1`, `3` e `130` têm prioridade sobre o `4`.

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `error: data/dataset does not match manifests/dataset.manifest.json`, ou `... not found; restore the versioned dataset` (`1`) | `unzip data/dataset.zip -d data/` (apague `data/dataset` antes) e rode de novo |
| `error: OLLAMA_BASE_URL is not set in .env` (ou `OLLAMA_HARDWARE_LABEL`) (`2`) | preencha a variável no `.env` |
| `error: a run already exists in data/suites/slm; use --resume to continue it` (`2`) | rode com `--resume`; para começar do zero, apague `data/suites/slm` |
| `ollama unavailable (...); retrying the same call ...` | o Ollama não respondeu (ou o túnel do ngrok caiu: `ERR_NGROK_3200`); o comando espera e tenta de novo sozinho. Confira se o Ollama e o túnel estão no ar e se o endereço do `.env` está certo; se o túnel voltar com outro endereço, interrompa (Ctrl+C), troque o `OLLAMA_BASE_URL` e rode `generate --resume` |
| `infrastructure failure: ollama unavailable after N consecutive retries ...` (`3`) | coloque o Ollama no ar e rode `generate --resume`; nada foi perdido |
| `configuration error: model qwen2.5-coder:14b is not installed ...` (`3`) | `ollama pull qwen2.5-coder:14b` no servidor do Ollama |
| `error: data/suites/slm holds a run of an older version of python -m ai_clients ...` (`2`) | a pasta tem uma execução de uma versão anterior (outra tabela de pedidos), que não pode ser continuada nem lida: `mv data/suites/slm data/suites/slm-<nome>` e comece uma execução nova |
| `configuration error: ... the prompt may have been truncated ...` (`3`) | o pedido não coube na janela de contexto do modelo; avise os autores (é um parâmetro do experimento); nada foi gravado |
| `error: data/suites/slm/run.json does not exist; run generate first` (`2`, no `execute`, `report` ou `package`) | rode o `generate` antes |
| `error: N of 600 combinations have no suite.json ...` (`1`, no `package`) | termine a execução (alternar `generate --resume` e `execute`) antes de empacotar |
| `manual: <id> <cenário>: 3 prediction attempts unparseable; close it with: ...` (`4`, no `generate` ou no `execute`) | nenhum dos 15 pedidos deu uma suíte; os demais problemas e cenários seguiram normalmente. Os autores decidem o que fazer e rodam o comando `close` impresso, com o motivo |
| `error: <id> <cenário> is <estado>, not awaiting manual handling; nothing was recorded` (`2`, no `close`) | só se fecha à mão um problema e cenário que aguarda os autores; confira o `--problem` e o `--scenario` |
| `FAIL` no `verify` | algum arquivo foi alterado, apagado ou acrescentado depois do pacote: apague `data/suites/slm` e descompacte de novo |
| `infrastructure failure: cannot prepare the workdir ...` ou `cannot start ...` (`3`, no `execute`) | o `execute` foi rodado fora do serviço `sandbox`: use `docker compose run --rm sandbox ...`; nada foi gravado |
| `error: the configuration differs from data/suites/slm/run.json ...` (`2`) | algo que muda as respostas mudou (a lista abaixo da mensagem diz o quê, com o valor gravado e o atual); volte ao que estava, ou tire `data/suites/slm` do lugar para começar uma execução nova |
| `damaged: <id> <cenário>: missing: ... / changed: ... / inconsistent: ...` (`1`) | os arquivos daquele problema e cenário foram alterados, apagados ou não batem entre si; o comando não conserta nada e continua com os demais. Avise os autores antes de mexer |
| `error: another python -m ai_clients command is already running over data/suites/slm/` (`1`) | `close`, `package` e o primeiro `generate` só rodam sozinhos, e `generate --resume` e `execute` não rodam junto com eles: espere o outro comando terminar |
| `error: another python -m ai_clients execute is already running` (`1`) | só um `execute` por vez: espere o outro terminar |
| `<id> <cenário>: skipped (in use by another command)` | outro comando rodando ao mesmo tempo estava com esse problema e cenário; ele fica para a próxima rodada. Com metades separadas de `--problem`, não deveria aparecer |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/enunciado.md`, `AC_ref.cpp`, `testes.json`, `metadata.json` | texto, C++ e JSON | dataset descompactado ([`dataset`](../dataset/README.md)); `metadata.json` traz os limites de tempo e memória, `testes.json` os testes públicos |
| `manifests/dataset.manifest.json` | JSON | versionado; conferido antes de qualquer trabalho |
| `src/prompt_templates/slm_prompt.txt` | texto (inglês) | versionado; o texto-base dos pedidos 1 a 12 (entradas e solução Python), igual nos três cenários exceto pelo bloco de contexto |
| `src/prompt_templates/slm_predict_prompt.txt` | texto (inglês) | versionado; o texto-base dos pedidos 13 a 15 (entradas e saídas esperadas, sem solução), com o mesmo bloco de contexto |
| `OLLAMA_BASE_URL`, `OLLAMA_HARDWARE_LABEL` (e, opcionais, `OLLAMA_HTTP_TIMEOUT_S`, `OLLAMA_MAX_INFRA_RETRIES`, `OLLAMA_MODEL`) | variáveis do `.env` | preenchidas pelo operador (ver `.env.example`) |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| Respostas do modelo, execuções e suíte final de cada problema e cenário | JSON | `data/suites/slm/problems/<id>/<cenário>/` (não versionado); a suíte final é de onde a etapa de avaliação vai ler |
| Relatório agregado | JSON | `manifests/slm_generation_report.json` (versionado) |
| Pacote da execução final e manifesto | zip e JSON | `data/slm_suites.zip` e `manifests/slm_suites.manifest.json` (versionados) |

## (e) Dependências e pré-requisitos

- Python 3.11 da imagem (`docker compose build`); nenhuma dependência além das já fixadas no
  `uv.lock`.
- Um servidor Ollama acessível, na própria máquina ou remoto, com o modelo `qwen2.5-coder:14b`
  baixado (`ollama pull qwen2.5-coder:14b`), e as variáveis do `.env` preenchidas.
- Serviço `app` para a geração e `sandbox` para a execução (motor do módulo
  [`sandbox`](../sandbox/README.md), sem alteração).
- Dataset descompactado em `data/dataset/` e íntegro.

## (f) Limitações conhecidas

- A solução Python do modelo só é validada pelos testes públicos do problema; se ela estiver
  errada numa entrada que nenhum teste público cobre, a saída esperada daquela entrada fica errada.
- As suítes `accepted_fallback` vêm de soluções que erraram um exemplo, e as `accepted_predicted`
  têm saídas escritas pelo modelo sem nenhuma conferência: parte das saídas esperadas delas pode
  estar errada. O relatório separa as suítes por `status` para que a análise nunca as misture com
  as `accepted` sem saber.
- Nos cenários com código, o modelo pode só traduzir a solução C++ para Python, em vez de resolver
  o problema de forma independente.
- Não há verificação de que a solução Python é determinística nem de que cada entrada gerada
  respeita as restrições do enunciado.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 3
- Testes: `tests/ai_clients/` (`docker compose run --rm sandbox pytest tests/ai_clients`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `generate --dry-run` (200 problemas) | 2026-09-30 | 2e679ae+dirty |
| `generate` | 2026-10-06 | 7535dee |
| `execute` | 2026-10-06 | 7535dee |
| `close` | pendente | — |
| `report` | 2026-10-06 | 7535dee |
| `package` | pendente | — |
| `verify` | pendente | — |
