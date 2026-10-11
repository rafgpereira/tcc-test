# Módulo `ai_clients` (geração de suítes de teste pelo modelo local)

> **Status**: em implementação · **Metodologia**: `docs/metodologia-referencia.md`, seção 3

## (a) Propósito

Gera, para cada problema do dataset e cada um dos três cenários de contexto, uma suíte de casos de teste com o modelo local Qwen2.5-Coder-14B (`qwen2.5-coder:14b`, via Ollama), cuja saída esperada é calculada executando de verdade uma solução em Python escrita pelo próprio modelo, para alimentar a etapa de avaliação.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
e tenha o dataset descompactado em `data/dataset/`
([README do módulo `dataset`](../dataset/README.md), Cenário B).

**Estado (2026-10-11)**: a execução completa terminou em 2026-10-09, com suíte em 600 de 600
combinações de problema e cenário (números em (f)); o pacote `data/slm_suites.zip` ainda não foi
gerado, então o Cenário B ainda não está disponível.

Para cada problema e cada cenário — **caixa-preta** (o modelo vê só o enunciado), **caixa-branca**
(só a solução de referência em C++) e **híbrido** (os dois) — o modelo recebe um único pedido, sem
memória de pedidos anteriores, e responde com **entradas de teste** e uma **solução do problema em
Python**. O modelo nunca diz qual é a saída certa: ela é obtida rodando essa solução Python sobre
cada entrada, isolada, sem internet. A solução só é aceita se acertar os testes públicos do
problema; senão, é feito um novo pedido, com outra seed ou temperatura, até 12. **Nenhum problema e
cenário fica sem suíte**: sem acerto nos 12, entram, nesta ordem, uma suíte de **reserva** e até 3
pedidos em que o próprio modelo escreve as saídas (**predição**); se nem isso funcionar, os autores
fecham o caso à mão (`close`). A tabela de seeds e temperaturas é fixa e gravada no `run.json`:

| Pedidos | Fase | Seed | Temperatura | O que se pede |
|---|---|---|---|---|
| 1 a 6 | 1 | 42 a 47 | 0.7 | entradas e solução Python |
| 7 a 12 | 2 | 48 | 0.7, 0.6, 0.5, 0.4, 0.3, 0.2 | entradas e solução Python |
| 13 a 15 | 4 | 49, 50, 51 | 0.7 | entradas e saídas (predição) |

A suíte (`suite.json`) sai do primeiro destes casos que acontecer; o campo `status` diz qual:

| Fase | Quando | `status` | As saídas esperadas vêm de |
|---|---|---|---|
| 1 ou 2 | uma solução dos pedidos 1 a 12 acerta todos os testes públicos | `accepted` | uma solução que acertou os exemplos |
| 3 | nenhuma acertou: a melhor das que erraram um teste público **só por WA** e mantiveram alguma entrada, sem novo pedido | `accepted_fallback` | uma solução que **sabidamente erra** em algum caso |
| 4 | nem reserva houve: o primeiro dos pedidos 13 a 15 que puder ser lido | `accepted_predicted` | o próprio modelo, **sem execução nem conferência** |
| 5 | nem as 3 predições puderam ser lidas | `discarded_manual` | — (sem testes; os autores fecham com `close` e o motivo fica gravado) |

O trabalho tem duas etapas, cada uma num serviço do Docker Compose: a **geração** (serviço `app`,
com internet, para falar com o Ollama) envia os pedidos e guarda cada resposta exatamente como
veio, sem executar nada; a **execução** (serviço `sandbox`, sem internet, o único autorizado a
executar código de terceiros) roda as soluções Python e calcula as saídas esperadas.

### Cenário A — Rodar do zero

**Preparar o Ollama (exemplo: Kaggle com duas T4).** A execução final rodou com dois servidores
Ollama 0.35.0, um por placa de vídeo, acessados pela internet por um túnel. Num notebook do Kaggle:

1. Crie o notebook com acelerador **GPU T4 x2** e a opção **Internet** ligada.
2. Instale o Ollama 0.35.0 (a versão da execução).
3. Suba um `ollama serve` por placa: `CUDA_VISIBLE_DEVICES=0` na porta `11434` e
   `CUDA_VISIBLE_DEVICES=1` na porta `11435`.
4. Baixe o modelo em cada um: `ollama pull qwen2.5-coder:14b`.
5. Abra um túnel por servidor: `cloudflared tunnel --url http://localhost:<porta>`.
6. Copie os dois endereços `https://….trycloudflare.com` para `GPU0` e `GPU1` do laço do passo 3.

As células prontas estão em [`docs/kaggle-ollama.ipynb`](../../docs/kaggle-ollama.ipynb) (o notebook
usado pelos autores pode diferir em detalhes). O endereço muda toda vez que o túnel reinicia, e a
sessão do Kaggle tem limite de tempo: quando ela cair, suba tudo de novo e troque os endereços.
Nunca versione tokens, endereços de túnel nem logs que os contenham. Com o Ollama nesta máquina, o
endereço é `http://host.docker.internal:11434`; noutra máquina da rede, `http://<servidor>:11434`.

**1. Preencher o `.env`** (o arquivo de configuração na raiz, ver `.env.example`):
`OLLAMA_BASE_URL` (o endereço do Ollama; com duas máquinas, o laço passa o de cada uma) e
`OLLAMA_HARDWARE_LABEL` (texto que descreve a máquina do Ollama, gravado junto de cada resposta;
nunca é detectado sozinho; o mesmo para as duas placas). Opcionais: `OLLAMA_HTTP_TIMEOUT_S`,
`OLLAMA_MAX_INFRA_RETRIES` e `OLLAMA_MODEL` (só para piloto que compara modelos). Uma execução nova
começa numa pasta vazia: se `data/suites/slm/` já existe, mova-a antes
(`mv data/suites/slm data/suites/slm-<nome>`).

**2. Conferir e começar.** O `--dry-run` lista os pedidos previstos sem chamar o modelo nem gravar
nada (`dry run: 600 calls planned` e o maior pedido de cada cenário); o primeiro `generate` cria
`data/suites/slm/run.json` (modelo, parâmetros, dataset e tabela de seeds) e roda sozinho:

```bash
docker compose run --rm app python -m ai_clients generate --dry-run
docker compose run --rm app python -m cli check --deep
docker compose run --rm app python -m ai_clients generate --limit 1
```

O `check --deep` precisa terminar com `0`. `--limit 1` trata só a primeira combinação, para o laço
do passo 3 continuar com `--resume`; com uma máquina só, pode-se rodar sem `--limit`. Cada pedido
imprime uma linha como `<id> <cenário> attempt 1 seed 42: parsed (7 inputs) — ...
tokens, stop, ... s` e grava `data/suites/slm/problems/<id>/<cenário>/attempt_<n>.generation.json`.

**3. Alternar geração e execução até acabar.** O `execute` roda as soluções e grava
`attempt_<n>.execution.json` e, quando a combinação termina, o `suite.json`; enquanto ele imprimir
`next: ...generate --resume`, há combinação à espera de novo pedido ao modelo. Com uma máquina só,
alterne `generate --resume` e `execute` à mão. Com duas, o laço abaixo, rodado na raiz do projeto,
faz as rodadas sozinho: dois `generate --resume` em paralelo, cada um com o seu endereço e todos os
problemas (eles dividem o trabalho: a combinação em uso por um é pulada pelo outro, `skipped`), um
log por máquina em `data/logs/`, um único `execute` depois, de novo enquanto houver `next:`, e o
relatório no fim. Ele para dizendo qual máquina falhou se um `generate` sair com `3` (Ollama ou túnel
fora do ar) ou `130` (interrompido); rodá-lo de novo continua de onde parou.

```bash
GPU0="https://ENDERECO-DA-MAQUINA-0"
GPU1="https://ENDERECO-DA-MAQUINA-1"
(
mkdir -p data/logs
explain() {  # $1 = name, $2 = exit code, $3 = log
  case $2 in
    0|4) return 0 ;;
    3)   echo "PARADO: $1 saiu com 3 (Ollama ou túnel fora do ar); veja $3, ponha-o no ar e rode o laço de novo" ;;
    130) echo "PARADO: $1 foi interrompido (130); rode o laço de novo para continuar" ;;
    *)   echo "PARADO: $1 saiu com $2; veja $3" ;;
  esac
  return 1
}
# Ctrl+C stops the two generate too (commands started with & do not get it from the terminal)
trap 'echo "PARADO: interrompido; parando os dois generate..."; kill $pid0 $pid1 2>/dev/null; wait; exit 130' INT TERM
pid0= pid1= round=0
while true; do
  round=$((round + 1))
  echo "== rodada $round: dois generate =="
  docker compose run --rm -T -e OLLAMA_BASE_URL="$GPU0" app python -m ai_clients generate --resume \
    < /dev/null >> data/logs/gpu0.log 2>&1 &
  pid0=$!
  docker compose run --rm -T -e OLLAMA_BASE_URL="$GPU1" app python -m ai_clients generate --resume \
    < /dev/null >> data/logs/gpu1.log 2>&1 &
  pid1=$!
  wait $pid0; code0=$?
  wait $pid1; code1=$?
  pid0= pid1=
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
)
```

Rode **um** laço por vez, num terminal só; para parar, Ctrl+C nele (espere a mensagem `PARADO`;
confira com `docker ps` que nenhum container `tcc-test-app-run-...` ficou rodando). Se um túnel
voltar com outro endereço, pare o laço, troque `GPU0` ou `GPU1` e rode de novo. Código `4` não para
o laço: as linhas `manual: ...` ficam nos logs, e os autores fecham cada combinação com o `close`.

**4. Relatório, pacote e conferência:**

```bash
docker compose run --rm app python -m ai_clients report
docker compose run --rm app python -m ai_clients package
docker compose run --rm app python -m ai_clients verify --extracted data/suites/slm
docker compose run --rm app python -m cli check --deep
```

O `package` gera `data/slm_suites.zip` (os mesmos arquivos dão sempre o mesmo zip, byte a byte),
`manifests/slm_suites.manifest.json` e refaz `manifests/slm_generation_report.json`; esses três são
os que se versionam (`data/suites/` nunca é). Esperado: `OK` no `verify` e `Resultado: OK` no `check`.

### Cenário B — Descompactar o que já existe

Quando `data/slm_suites.zip` e `manifests/slm_suites.manifest.json` estão no repositório (depois do
`git pull`), **não rode `generate`**:

```bash
rm -rf data/suites/slm
unzip data/slm_suites.zip -d data/
docker compose run --rm app python -m ai_clients verify --extracted data/suites/slm
docker compose run --rm app python -m cli check --deep
```

O `unzip` recria `data/suites/slm/` exatamente como ficou na máquina que gerou. Esperado: `OK` no
`verify` (senão, uma linha `changed:`/`missing:`/`extra:` por arquivo e `FAIL`) e `Resultado: OK` no
`check`.

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m ai_clients generate` | `app` | pede ao modelo as entradas e a solução Python (pedidos 1 a 12) ou as entradas e saídas (13 a 15, predição; a primeira lida já vira a suíte) de cada combinação pendente e grava as respostas. `--resume` é obrigatório depois do primeiro (sem ele, `2`) e recusa com `2`, listando o que mudou, se mudou algo que muda as respostas (modelo ou a versão baixada dele, versão do Ollama, parâmetros, os dois textos-base, número de tentativas, dataset, folgas de tempo e memória); trocar de máquina, o `OLLAMA_HARDWARE_LABEL` ou as esperas é permitido. Uma pasta com execução de versão anterior do módulo também dá `2`. `--dry-run` só lista os pedidos, sem Ollama nem gravar. `--limit N` trata no máximo N combinações; `--problem ID` e `--scenario black_box`/`white_box`/`hybrid` (repetíveis) restringem. Ollama fora do ar: repete a mesma chamada sem gastar tentativa (espera de 5 s dobrando até 60 s) até `OLLAMA_MAX_INFRA_RETRIES` vezes e para com `3`. `token repeat limit reached` do modelo conta como tentativa perdida (`repetition`). Combinação que aguarda os autores: linha `manual: ...` com o comando `close` e saída `4` depois de tratar as demais. Interrompido (Ctrl+C, `docker stop`): `130`; o `--resume` refaz só a chamada em andamento, com a mesma seed. Vários `generate --resume` (um por máquina, cada um com `-e OLLAMA_BASE_URL=...` e todos os problemas) e um `execute` rodam juntos: a combinação em uso por outro é pulada e contada (`skipped (in use by another command)`). O primeiro `generate` roda sozinho |
| `python -m ai_clients execute` | `sandbox` | roda a solução Python de cada resposta lida e ainda não executada sobre os testes públicos (para no primeiro erro) e, se acertou ou se o erro foi WA, sobre cada entrada gerada, sem rede, como usuário sem privilégios, só com a biblioteca padrão; limites do `metadata.json` do problema com folga de **10 vezes** o tempo e **4 vezes** a memória. Entrada que estoura o tempo, dá erro ou não é texto UTF-8 é descartada sozinha. Grava `attempt_<n>.execution.json` e, quando a combinação termina, `suite.json`. Exige o `run.json` (senão `2`); sem `--resume`, sempre continua de onde parou. `--dry-run`, `--limit N`, `--problem ID`, `--scenario S` como no `generate`. Termina com `next: ...generate --resume` (mesmos `--problem`/`--scenario`) enquanto houver combinação à espera de novo pedido; `manual: ...` e `4` como no `generate`. Rodado fora do `sandbox`: `3`, sem gravar. Interrompido: `130`; rodar de novo refaz só a tentativa em andamento. Só um `execute` por vez |
| `python -m ai_clients close --problem ID --scenario S --reason "TEXTO"` | `app` | fecha à mão **uma** combinação que aguarda os autores: grava `manual_close.json` (motivo e data) e o `suite.json` com `status: discarded_manual`, sem testes (o problema continua contando no total). As três opções são obrigatórias; motivo vazio, combinação em outro estado ou problema fora do dataset → `2`, sem gravar. `--dry-run` só mostra o que seria gravado. Exige o `run.json`. Recusa (`1`) se outro comando estiver rodando |
| `python -m ai_clients change-template --template prediction --reason "TEXTO"` | `app` | troca um texto-base no meio da execução (só por decisão dos autores): depois de editar o arquivo em `src/prompt_templates/` (`--template solution` ou `prediction`), grava a troca em `data/suites/slm/template_changes/<NNN>.json` (SHA-256 do antigo e do novo, data, motivo, o que foi movido) e move para `superseded/<NNN>/` os pedidos feitos com o texto antigo, do primeiro em diante, com o `suite.json`; o `generate --resume` os refaz com o texto novo e as mesmas seeds. Texto igual ao da execução ou motivo vazio → `2`; combinação danificada → `1`, sem gravar nem mover. `--dry-run` só lista. Interrompido, rodar de novo termina de mover, sem gravar outra troca. Recusa (`1`) se outro comando estiver rodando |
| `python -m ai_clients report` | `app` | grava `manifests/slm_generation_report.json` lendo só `data/suites/slm/`: combinações por `status` e cenário, tamanho das suítes, falhas por motivo e tentativa, entradas descartadas, respostas cortadas por tamanho, *tokens*, tempo do modelo, máquinas, seeds e trocas de texto-base. Pode rodar a qualquer momento. Exige o `run.json` (`2`); combinação danificada → `1` |
| `python -m ai_clients package` | `app` | gera `data/slm_suites.zip`, `manifests/slm_suites.manifest.json` e refaz o relatório; sempre da execução inteira (sem `--problem`). Recusa (`1`) se alguma combinação não tem `suite.json` (listando as que aguardam os autores, com o `close`), se há combinação danificada, se `superseded/` não bate com as trocas ou se outro comando estiver rodando |
| `python -m ai_clients verify` | `app` | confere `data/slm_suites.zip` contra o manifesto; `--extracted data/suites/slm` confere também a pasta descompactada, arquivo a arquivo. `0` se bate, `1` se não, `2` sem o manifesto |
| `unzip data/slm_suites.zip -d data/` | (máquina) | descompacta as suítes em `data/suites/slm/` |
| `pytest tests/ai_clients` | `sandbox` | testes do módulo (com um modelo simulado) |

Códigos de saída: `0` sucesso, `1` falha de dados, `2` uso incorreto, `3` falha de infraestrutura
ou de configuração do Ollama, `4` terminou, mas alguma combinação aguarda os autores (`close`),
`130` interrompido. `1`, `3` e `130` têm prioridade sobre `4`.

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `error: data/dataset does not match manifests/dataset.manifest.json` (`1`) | `unzip data/dataset.zip -d data/` (apague `data/dataset` antes) e rode de novo |
| `error: OLLAMA_BASE_URL is not set in .env` (ou `OLLAMA_HARDWARE_LABEL`) (`2`) | preencha a variável no `.env` |
| `error: a run already exists in data/suites/slm; use --resume to continue it` (`2`) | rode com `--resume`; para começar do zero, mova `data/suites/slm` |
| `ollama unavailable (...); retrying the same call ...` | o Ollama ou o túnel (cloudflared ou ngrok) não respondeu, ou a resposta parou no meio; o comando repete sozinho, com a mesma seed, sem gravar a resposta incompleta. Confira o Ollama, o túnel e o endereço; se o túnel voltar com outro endereço, interrompa (Ctrl+C), troque o endereço e rode `generate --resume` |
| `infrastructure failure: ollama unavailable after N consecutive retries ...` (`3`) | ponha o Ollama no ar e rode `generate --resume`; nada foi perdido |
| `configuration error: model qwen2.5-coder:14b is not installed ...` (`3`) | `ollama pull qwen2.5-coder:14b` no servidor do Ollama |
| `configuration error: ... the prompt may have been truncated ...` (`3`) | o pedido não coube na janela de contexto; avise os autores; nada foi gravado |
| `error: data/suites/slm/run.json does not exist; run generate first` (`2`) | rode o `generate` antes |
| `error: the configuration differs from data/suites/slm/run.json ...` (`2`) | volte ao que estava (a mensagem lista o valor gravado e o atual) ou mova `data/suites/slm` para começar outra execução; se foi um texto-base trocado de propósito, rode o `change-template` sugerido |
| `damaged: <id> <cenário>: ... template was changed` ou `... is not the ... template of the run` (`1`) | uma troca de texto-base ficou pela metade: rode o mesmo `change-template` de novo |
| `damaged: <id> <cenário>: missing: ... / changed: ... / inconsistent: ...` (`1`) | arquivos daquela combinação alterados ou apagados; o comando segue com as demais. Avise os autores antes de mexer |
| `manual: <id> <cenário>: 3 prediction attempts unparseable; close it with: ...` (`4`) | os autores decidem e rodam o `close` impresso, com o motivo |
| `error: N of 600 combinations have no suite.json ...` (`1`, no `package`) | termine a execução (passo 3) antes de empacotar |
| `error: another python -m ai_clients command is already running ...` (`1`) | `close`, `package`, `change-template` e o primeiro `generate` só rodam sozinhos; espere o outro terminar |
| `<id> <cenário>: skipped (in use by another command)` | esperado com duas máquinas: a combinação está com o outro comando |
| `infrastructure failure: cannot prepare the workdir ...` (`3`, no `execute`) | use o serviço `sandbox`: `docker compose run --rm sandbox ...` |
| `FAIL` no `verify` | algum arquivo mudou depois do pacote: apague `data/suites/slm` e descompacte de novo |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/enunciado.md`, `AC_ref.cpp`, `testes.json`, `metadata.json` | texto, C++ e JSON | dataset descompactado ([`dataset`](../dataset/README.md)); `metadata.json` traz os limites, `testes.json` os testes públicos |
| `manifests/dataset.manifest.json` | JSON | versionado; conferido antes de qualquer trabalho |
| `src/prompt_templates/slm_prompt.txt` e `slm_predict_prompt.txt` | texto (inglês) | versionados; os textos-base dos pedidos 1 a 12 e 13 a 15, iguais nos três cenários exceto pelo bloco de contexto |
| `OLLAMA_BASE_URL`, `OLLAMA_HARDWARE_LABEL` (opcionais `OLLAMA_HTTP_TIMEOUT_S`, `OLLAMA_MAX_INFRA_RETRIES`, `OLLAMA_MODEL`) | variáveis do `.env` | preenchidas pelo operador (ver `.env.example`) |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| Respostas, execuções e suíte final de cada combinação | JSON | `data/suites/slm/problems/<id>/<cenário>/` (não versionado); a etapa de avaliação lê o `suite.json` |
| Trocas de texto-base e pedidos refeitos por elas | JSON | `data/suites/slm/template_changes/` e `superseded/` (não versionados; entram no pacote, não nas contagens) |
| Relatório agregado | JSON | `manifests/slm_generation_report.json` (versionado) |
| Pacote da execução final e manifesto | zip e JSON | `data/slm_suites.zip` e `manifests/slm_suites.manifest.json` (versionados) |

## (e) Dependências e pré-requisitos

- Python 3.11 da imagem (`docker compose build`); nenhuma dependência além das fixadas no `uv.lock`.
- Um ou mais servidores Ollama acessíveis com `qwen2.5-coder:14b` baixado (a execução final usou
  Ollama 0.35.0, quantização Q4_K_M, `num_ctx` 8192 e `num_predict` 5120), e o `.env` preenchido.
- Serviço `app` para geração, `close`, `change-template`, `report`, `package` e `verify`; `sandbox`
  para `execute` (motor do módulo [`sandbox`](../sandbox/README.md), sem alteração).
- Dataset descompactado em `data/dataset/` e íntegro.

## (f) Limitações conhecidas

- **Resultado da execução completa** (600 combinações, 2026-10-06 a 2026-10-09): 505 `accepted`
  (84,2%), 93 `accepted_fallback` (15,5%), 2 `accepted_predicted` (0,3%), 0 `discarded_manual`;
  2.185 chamadas ao modelo. Um texto-base (o de predição) foi trocado uma vez no meio da execução;
  as duas suítes `accepted_predicted` vêm do texto novo.
- A solução Python só é validada pelos testes públicos; se errar numa entrada que nenhum teste
  público cobre, a saída esperada daquela entrada fica errada.
- As suítes `accepted_fallback` vêm de soluções que erraram um exemplo, e as `accepted_predicted`
  têm saídas escritas pelo modelo sem conferência: parte das saídas delas pode estar errada. O
  relatório separa as suítes por `status` para a análise nunca misturá-las com as `accepted`.
- Nos cenários com código, o modelo pode só traduzir a solução C++ para Python.
- Não há verificação de que a solução Python é determinística nem de que cada entrada respeita as
  restrições do enunciado. Na predição, só testes com valores abreviados (`1 1 ... 1`, `…`) são
  descartados; uma linha só de pontos (como `...` numa grade) é mantida.
- O `OLLAMA_HARDWARE_LABEL` é texto livre: todas as chamadas da execução final têm a mesma etiqueta,
  embora parte tenha rodado noutra plataforma com o mesmo modelo de placa (T4), a mesma versão do
  Ollama e o mesmo modelo (ver metodologia, seção 3).

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 3
- Preparação do Ollama no Kaggle: [`docs/kaggle-ollama.ipynb`](../../docs/kaggle-ollama.ipynb)
- Testes: `tests/ai_clients/` (`docker compose run --rm sandbox pytest tests/ai_clients`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `generate --dry-run` (200 problemas) | 2026-09-30 | 2e679ae+dirty |
| `generate` (inclusive interrupção e retomada, duas máquinas em paralelo) | 2026-10-09 | 968c5ba |
| `execute` | 2026-10-09 | 968c5ba |
| `close` | não necessário (0 combinações aguardando os autores) | — |
| `change-template` | 2026-10-08 | 968c5ba |
| `report` | 2026-10-09 | 968c5ba |
| `package` | pendente | — |
| `verify` | pendente | — |
