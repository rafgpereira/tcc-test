# Módulo `ai_clients` (geração de suítes de teste pelos quatro modelos)

> **Status**: implementado · **Metodologia**: `docs/metodologia-referencia.md`, seção 3

## (a) Propósito

Gera, para cada problema do dataset e cada um dos três cenários de contexto, uma suíte de casos de teste com cada um dos quatro modelos do experimento — o local Qwen2.5-Coder-14B (via Ollama), que calcula a saída esperada executando uma solução em Python escrita por ele, e os comerciais GPT-5.4-mini, Gemini 3.8 Flash e Claude Haiku 5.5, que escrevem a saída esperada diretamente —, para alimentar a etapa de avaliação.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
e tenha o dataset descompactado em `data/dataset/`
([README do módulo `dataset`](../dataset/README.md), Cenário B). O módulo usa dois serviços do
Docker Compose: `app` (tem internet, fala com o Ollama e com as APIs, nunca executa código de
terceiros) e `sandbox` (sem internet, o único que executa as soluções Python do modelo local).

Os quatro modelos têm o mesmo fluxo. Sem `--model`, os comandos valem para o modelo local (`slm`);
com `--model gpt`, `--model gemini` ou `--model claude`, para os comerciais.

| Modelo | Pacote versionado | Pasta ao descompactar |
|---|---|---|
| local (`slm`) | `data/slm_suites.zip` | `data/suites/slm/` e `data/suites/slm-rev1/` |
| `gpt` | `data/gpt_suites.zip` | `data/suites/gpt/` |
| `gemini` | `data/gemini_suites.zip` | `data/suites/gemini/` |
| `claude` | `data/claude_suites.zip` | `data/suites/claude/` |

Para usar as suítes que já existem, siga o **Cenário B**; o Cenário A só serve para gerar tudo de
novo (leva dias e, nos comerciais, **cada chamada custa dinheiro**). O número de combinações e o
resultado de cada execução estão em `manifests/<modelo>_generation_report.json` (`python -m
ai_clients report` o refaz).

Para cada problema e cada cenário — **caixa-preta** (o modelo vê só o enunciado), **caixa-branca**
(só a solução de referência em C++) e **híbrido** (os dois) — o modelo recebe um único pedido, sem
memória de pedidos anteriores.

- **Modelo local**: responde com **entradas de teste** e uma **solução do problema em Python**; a
  saída esperada é obtida rodando essa solução sobre cada entrada, isolada, sem internet. A solução
  só é aceita se acertar os testes públicos do problema; senão, há novo pedido, com outra seed ou
  temperatura, até 12 (pedidos 1 a 6: seeds 42 a 47, temperatura 0.7; 7 a 12: seed 48, temperaturas
  0.7, 0.6, 0.5, 0.4, 0.3, 0.2). Sem acerto nos 12, entram, nesta ordem, uma suíte de **reserva** e
  até 3 pedidos em que o próprio modelo escreve as saídas (**predição**, pedidos 13 a 15, seeds 49 a
  51); se nem isso funcionar, os autores fecham o caso à mão (`close`).
- **Modelos comerciais**: respondem em JSON com a análise e os testes, com a saída esperada
  escrita por eles (nada é executado). Resposta que não pode ser lida (cortada, recusada, bloqueada,
  fora do formato, sem teste aproveitável) gera novo pedido, até 3; depois, os autores fecham o caso
  (`close`). Não há seed nem temperatura; o raciocínio é sempre `medium`. Resposta que diga ter
  raciocinado 0 *tokens* fica em `barred/`, não gasta tentativa e é pedida de novo; na terceira, a
  suíte é `accepted_barred`.

A suíte (`suite.json`) sai do primeiro destes casos que acontecer; o campo `status` diz qual:

| `status` | Quando | As saídas esperadas vêm de |
|---|---|---|
| `accepted` | (local) uma solução dos pedidos 1 a 12 acerta todos os testes públicos | uma solução que acertou os exemplos |
| `accepted_fallback` | (local) nenhuma acertou: a melhor das que erraram um teste público **só por WA** e mantiveram alguma entrada | uma solução que **sabidamente erra** em algum caso |
| `accepted_predicted` | (local) o primeiro dos pedidos 13 a 15 que puder ser lido; (comerciais) a primeira resposta lida | o próprio modelo, **sem execução nem conferência** |
| `accepted_barred` | (comerciais) a terceira resposta sem raciocínio | o próprio modelo, **sem execução nem conferência** |
| `discarded_manual` | nada pôde ser lido; os autores fecham com `close` e o motivo fica gravado | — (sem testes) |

### Cenário A — Rodar do zero

**Parte 1 — modelo local.**

**Preparar o Ollama.** O modelo local roda num servidor Ollama com GPU; a execução final usou duas
placas NVIDIA T4, com um servidor Ollama 0.35.0 por placa. Na máquina com as GPUs:

1. Instale o Ollama 0.35.0 (a versão da execução).
2. Suba um `ollama serve` por placa: `CUDA_VISIBLE_DEVICES=0` na porta `11434` e
   `CUDA_VISIBLE_DEVICES=1` na porta `11435`.
3. Baixe o modelo em cada um: `ollama pull qwen2.5-coder:14b`.
4. Copie o endereço de cada servidor para `GPU0` e `GPU1` do laço do passo 3.

Nunca versione tokens, endereços de servidores nem logs que os contenham. Com o Ollama nesta máquina, o
endereço é `http://host.docker.internal:11434`; noutra máquina da rede, `http://<servidor>:11434`.

**1. Preencher o `.env`** (o arquivo de configuração na raiz, ver `.env.example`):
`OLLAMA_BASE_URL` (o endereço do Ollama; com duas máquinas, o laço passa o de cada uma) e
`OLLAMA_HARDWARE_LABEL` (texto que descreve a máquina do Ollama, gravado junto de cada resposta;
nunca é detectado sozinho; o mesmo para as duas placas). Opcionais: `OLLAMA_HTTP_TIMEOUT_S`,
`OLLAMA_MAX_INFRA_RETRIES` e `OLLAMA_MODEL` (só para comparar modelos). Uma execução nova começa
numa pasta vazia: se `data/suites/slm/` já existe, mova-a antes (`mv data/suites/slm
data/suites/slm-<nome>`).

**2. Conferir e começar.** O `--dry-run` lista os pedidos previstos sem chamar o modelo nem gravar
nada (`dry run: N calls planned` e o maior pedido de cada cenário); o `check --deep` precisa
terminar com `0`; o primeiro `generate` cria `data/suites/slm/run.json` (modelo, parâmetros,
dataset e tabela de seeds) e roda sozinho:

```bash
docker compose run --rm app python -m ai_clients generate --dry-run
docker compose run --rm app python -m cli check --deep
docker compose run --rm app python -m ai_clients generate --limit 1
```

`--limit 1` trata só a primeira combinação, para o laço do passo 3 continuar com `--resume`; com
uma máquina só, pode-se rodar sem `--limit`. Cada pedido imprime uma linha como `<id> <cenário>
attempt 1 seed 42: parsed (7 inputs) — ... tokens, stop, ... s` e grava
`data/suites/slm/problems/<id>/<cenário>/attempt_<n>.generation.json`. Para conferir antes o
texto de cada pedido pendente, sem chamar nada: `generate --dry-run --save-requests data/requests`
(Cenário A, pasta de suítes ainda vazia), que grava um `<id>.<cenário>.request.json` por
combinação e termina com `requests: N saved ...; faithful K/N; exponent warnings ...`.

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

**Parte 2 — modelos comerciais (GPT-5.4-mini, Gemini 3.8 Flash e Claude Haiku 5.5).** Aqui cada
chamada **custa dinheiro**. Os três modelos podem rodar ao mesmo tempo, um em cada terminal: cada um
tem a sua pasta (`data/suites/gpt/`, `data/suites/gemini/` e `data/suites/claude/`).

**1. Preencher o `.env`**: `OPENAI_API_KEY` (GPT), `GEMINI_API_KEY` (Gemini) e `ANTHROPIC_API_KEY`
(Claude), chaves de contas com faturamento ativo (na camada gratuita do Gemini o conteúdo pode ser
usado pelo Google). Opcionais, com o prefixo de cada modelo (`OPENAI_`, `GEMINI_`, `ANTHROPIC_`):
`..._MAX_CONCURRENCY` (pedidos ao mesmo tempo, padrão 4), `..._MAX_INFRA_RETRIES` (padrão 30),
`LLM_HTTP_TIMEOUT_S` (padrão 900, o mesmo para os três) e `..._MAX_REQUESTS_PER_MINUTE` (no máximo
tantos pedidos começam por minuto, repetições incluídas, espaçados por igual; sem valor, não há
espaçamento). Use o limite do seu plano: na camada gratuita do Gemini, 5 pedidos por minuto e 20 por
dia, isto é, `GEMINI_MAX_REQUESTS_PER_MINUTE=5` e `GEMINI_MAX_CONCURRENCY=1`. Quando a cota diária
acaba, o comando para com `3`, sem gravar nada; rode de novo com `--resume` depois que ela renovar.
Um modelo sem chave não roda; o outro roda normalmente.

**2. Estimar o custo, sem chamar nada.** O `--dry-run` monta os pedidos reais e estima, por cenário
e no total, quantos pedidos e quanto custam; não precisa de chave, não chama nenhuma API e não
grava nada. Cada linha diz o número de combinações e de pedidos (`up to` = com as 3 tentativas), os
*tokens* de entrada estimados e a faixa de custo em US$ (o extremo de cima supõe que toda chamada usa
o teto de saída de 32.768 *tokens*, então costuma ser muito maior que o gasto real):

```bash
docker compose run --rm app python -m ai_clients generate --model gpt --dry-run
docker compose run --rm app python -m ai_clients generate --model gemini --dry-run
docker compose run --rm app python -m ai_clients generate --model claude --dry-run
```

Para conferir, antes de gastar, o texto de cada pedido (com o prompt inteiro, conferido contra os
arquivos do problema): `generate --model gpt --dry-run --save-requests data/requests` (um arquivo
por combinação e um `summary.json`; sai com `1` se algum prompt não for fiel ao dataset).

**3. Rodar, sempre com um teto de gasto.** Nenhuma chamada paga sai sem `--confirm-spend <US$>`:
sem ele, o comando mostra a estimativa e sai com `2`. O valor é a confirmação **e** o teto da
invocação: quando o gasto chega nele, nenhum pedido novo sai (os já enviados terminam e são
gravados, então o gasto pode passar um pouco do teto, e o excesso é mostrado) e o comando sai com
`5`; continue com `--resume` e um teto novo. O teto vale por processo: dois `generate --resume` do
mesmo modelo juntos podem gastar a soma dos dois tetos. O `cli check --deep` precisa terminar com
`0` antes. O primeiro `generate` de cada modelo cria `data/suites/<modelo>/run.json`:

```bash
docker compose run --rm app python -m cli check --deep
docker compose run --rm app python -m ai_clients generate --model gpt --confirm-spend 20
docker compose run --rm app python -m ai_clients generate --model gpt --resume --confirm-spend 20
```

Cada pedido imprime `<id> <cenário> attempt <n>: parsed (<k> tests) — in ... out ... (reasoning
...) tokens, US$ ..., ... s` (ou o motivo da falha) e grava
`data/suites/<modelo>/problems/<id>/<cenário>/attempt_<n>.json` com a resposta inteira; a primeira
resposta lida vira o `suite.json`. O resumo final diz quanto foi gasto. Para testar antes com poucos
problemas, acrescente `--problem ID` (repetível); se quiser então recomeçar do zero, mova a pasta
(`mv data/suites/gpt data/suites/gpt-teste`), senão a execução completa continua nela com `--resume`.

**4. Relatório, pacote e conferência**, um por modelo (o pacote de um modelo não depende do outro):

```bash
docker compose run --rm app python -m ai_clients report --model gpt
docker compose run --rm app python -m ai_clients package --model gpt
docker compose run --rm app python -m ai_clients verify --model gpt --extracted data/suites/gpt
docker compose run --rm app python -m cli check --deep
```

O `package` gera `data/gpt_suites.zip` (ou `data/gemini_suites.zip`, `data/claude_suites.zip`), o
manifesto `manifests/gpt_suites.manifest.json` e refaz `manifests/gpt_generation_report.json`; esses
três se versionam. Repita os quatro comandos com `--model gemini` e `--model claude`.

### Cenário B — Descompactar o que já existe

Quando os pacotes já estão no repositório (depois do `git pull`), **não rode `generate`**.

**1. Modelo local:**

```bash
rm -rf data/suites/slm data/suites/slm-rev1
unzip data/slm_suites.zip -d data/
docker compose run --rm app python -m ai_clients verify
docker compose run --rm app python -m cli check --deep
```

O `unzip` recria **duas** pastas, porque o pacote junta duas execuções do modelo local, uma para
cada revisão do dataset (seção (f)): `data/suites/slm/`, com as combinações refeitas na revisão 2 e
o `provenance.json` que diz qual pasta vale para cada combinação, e `data/suites/slm-rev1/`, com as
da execução anterior, mantida por proveniência. O `verify` sem opções confere o zip; a pasta
descompactada é conferida pelo `cli check --deep`, que entende as duas
([`docs/verificacao-consistencia.md`](../../docs/verificacao-consistencia.md)). Esperado: `OK` no
`verify` e `Resultado: OK` no `check`. **Não use `verify --extracted data/suites/slm` neste
pacote**: ele só olha dentro de `data/suites/slm/` e relata `missing: suites/slm-rev1/...` para
arquivos que estão no lugar certo.

**2. Modelos comerciais** (cada um numa única pasta, sem o `-rev1`):

```bash
for m in gpt gemini claude; do
  rm -rf data/suites/$m
  unzip -q data/${m}_suites.zip -d data/
  docker compose run --rm app python -m ai_clients verify --model $m --extracted data/suites/$m
done
docker compose run --rm app python -m cli check --deep
```

Esperado: `OK` em cada `verify` (senão, uma linha `changed:`/`missing:`/`extra:` por arquivo e
`FAIL`) e `Resultado: OK` no `check`.

**3. Ver o que foi enviado a um modelo**, sem chamar nada: o `show-request` grava num arquivo o
corpo de uma tentativa já feita, conferido contra o hash gravado e contra o dataset. Roda no `app`,
que vê o histórico do Git só para leitura; os arquivos ficam em `data/requests/`, fora do Git.

```bash
docker compose run --rm app python -m ai_clients show-request --model gemini --problem 1_B --scenario black_box --output data/requests/1_B.black_box.json
docker compose run --rm app python -m ai_clients show-request --model slm --suite-attempts --output-dir data/requests/suites
```

Esperado: `written: ... prompt sha256 matches; dataset: faithful` no primeiro e `suite attempts: N
saved ...; prompt sha256 matches in all; faithful K/N` no segundo (uma suíte fechada à mão é pulada
e listada). O `generate --dry-run` não serve aqui: com as suítes já descompactadas não há pedido
pendente.

### Comandos

Todos rodam no `app`, exceto os marcados. Os de `--model gpt` valem igualmente para `gemini` e `claude`.

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m ai_clients generate` | `app` | (modelo local) pede ao modelo as entradas e a solução Python (pedidos 1 a 12) ou as entradas e saídas (13 a 15, predição; a primeira lida já vira a suíte) de cada combinação pendente e grava as respostas. `--resume` é obrigatório depois do primeiro (sem ele, `2`) e recusa com `2`, listando o que mudou, se mudou algo que muda as respostas (modelo ou a versão baixada dele, versão do Ollama, parâmetros, os dois textos-base, número de tentativas, dataset, folgas de tempo e memória); trocar de máquina, o `OLLAMA_HARDWARE_LABEL` ou as esperas é permitido. Uma pasta com execução de versão anterior do módulo também dá `2`. `--dry-run` só lista os pedidos, sem Ollama nem gravar. `--limit N` trata no máximo N combinações; `--problem ID` e `--scenario black_box`/`white_box`/`hybrid` (repetíveis) restringem. Ollama fora do ar: repete a mesma chamada sem gastar tentativa (espera de 5 s dobrando até 60 s) até `OLLAMA_MAX_INFRA_RETRIES` vezes e para com `3`. `token repeat limit reached` do modelo conta como tentativa perdida. Combinação que aguarda os autores: linha `manual: ...` com o comando `close` e saída `4` depois de tratar as demais. Interrompido (Ctrl+C, `docker stop`): `130`; o `--resume` refaz só a chamada em andamento, com a mesma seed. Vários `generate --resume` (um por máquina, cada um com `-e OLLAMA_BASE_URL=...` e todos os problemas) e um `execute` rodam juntos: a combinação em uso por outro é pulada e contada (`skipped (in use by another command)`). O primeiro `generate` roda sozinho |
| `python -m ai_clients execute` | `sandbox` | (modelo local) roda a solução Python de cada resposta lida e ainda não executada sobre os testes públicos (para no primeiro erro) e, se acertou ou se o erro foi WA, sobre cada entrada gerada, sem rede, como usuário sem privilégios, só com a biblioteca padrão; limites do `metadata.json` do problema com folga de **10 vezes** o tempo e **4 vezes** a memória. Entrada que estoura o tempo, dá erro ou não é texto UTF-8 é descartada sozinha. Grava `attempt_<n>.execution.json` e, quando a combinação termina, `suite.json`. Exige o `run.json` (senão `2`); sem `--resume`, sempre continua de onde parou. `--dry-run`, `--limit N`, `--problem ID`, `--scenario S` como no `generate`. Termina com `next: ...generate --resume` (mesmos `--problem`/`--scenario`) enquanto houver combinação à espera de novo pedido; `manual: ...` e `4` como no `generate`. Rodado fora do `sandbox`: `3`, sem gravar. Interrompido: `130`; rodar de novo refaz só a tentativa em andamento. Só um `execute` por vez. `--model gpt` (ou outro comercial): recusado (`2`), porque nada é executado |
| `python -m ai_clients close --problem ID --scenario S --reason "TEXTO"` | `app` | fecha à mão **uma** combinação que aguarda os autores: grava `manual_close.json` (motivo e data) e o `suite.json` com `status: discarded_manual`, sem testes (o problema continua contando no total). As três opções são obrigatórias; motivo vazio, combinação em outro estado ou problema fora do dataset → `2`, sem gravar. `--dry-run` só mostra o que seria gravado. Exige o `run.json`. Recusa (`1`) se outro comando estiver rodando. Com `--model gpt` (ou outro comercial), vale para uma combinação cujas 3 respostas não puderam ser lidas |
| `python -m ai_clients change-template --template prediction --reason "TEXTO"` | `app` | troca um texto-base no meio da execução (só por decisão dos autores): depois de editar o arquivo em `src/prompt_templates/` (`--template solution` ou `prediction`), grava a troca em `data/suites/slm/template_changes/<NNN>.json` (SHA-256 do antigo e do novo, data, motivo, o que foi movido) e move para `superseded/<NNN>/` os pedidos feitos com o texto antigo, do primeiro em diante, com o `suite.json`; o `generate --resume` os refaz com o texto novo e as mesmas seeds. Texto igual ao da execução ou motivo vazio → `2`; combinação danificada → `1`, sem gravar nem mover. `--dry-run` só lista. Interrompido, rodar de novo termina de mover, sem gravar outra troca. Recusa (`1`) se outro comando estiver rodando. Para os comerciais: `--model gpt --template llm` (`src/prompt_templates/llm_prompt.txt`, o texto-base único dos três), que move para `data/suites/<modelo>/superseded/<NNN>/` todas as respostas feitas com o texto antigo |
| `python -m ai_clients report` | `app` | grava `manifests/slm_generation_report.json` lendo só `data/suites/slm/`: combinações por `status` e cenário, tamanho das suítes, falhas por motivo e tentativa, entradas descartadas, respostas cortadas por tamanho, *tokens*, tempo do modelo, máquinas, seeds e trocas de texto-base. Pode rodar a qualquer momento. Exige o `run.json` (`2`); combinação danificada → `1`. Com `--model gpt`: grava `manifests/gpt_generation_report.json` (ou `gemini_...`, `claude_...`), com pedidos por tentativa, bloqueios por categoria (Gemini), custo (soma exata dos pedidos, inclusive os barrados), versões do modelo devolvidas pela API e respostas barradas |
| `python -m ai_clients package` | `app` | gera `data/slm_suites.zip`, `manifests/slm_suites.manifest.json` e refaz o relatório; sempre da execução inteira (sem `--problem`). Recusa (`1`) se alguma combinação não tem `suite.json` (listando as que aguardam os autores, com o `close`), se há combinação danificada, se `superseded/` não bate com as trocas ou se outro comando estiver rodando. Com `--model gpt`: gera `data/gpt_suites.zip` (ou `gemini_...`, `claude_...`), o manifesto e refaz o relatório; recusa (`1`) se alguma combinação **desse** modelo não tem `suite.json` (as do outro modelo não contam) ou se há dano |
| `python -m ai_clients package --merge-from data/suites/slm-rev1` | `app` | depois de uma **revisão do dataset** (só o modelo local): junta a execução nova, que refez só as combinações afetadas (caixa-preta e híbrido dos enunciados alterados, conforme `manifests/dataset_revision.json`), com a execução anterior, guardada em `data/suites/slm-rev1/` (`mv data/suites/slm data/suites/slm-rev1` antes do primeiro `generate` da revisão nova). Grava `data/suites/slm/provenance.json`, com a origem de cada combinação: a pasta que tem a suíte vigente e a revisão do dataset que a gerou; a combinação refeita fica na pasta anterior marcada como substituída. O zip leva as duas pastas. Imprime `merged: N combinations from suites/slm ..., M from suites/slm-rev1 ...`. Recusa (`1`) se faltar uma combinação afetada, se a execução nova tiver uma combinação que a revisão não afetou, se a pasta anterior estiver danificada ou se não houver revisão do dataset |
| `python -m ai_clients verify` | `app` | confere `data/slm_suites.zip` contra o manifesto; `--extracted data/suites/slm` confere também a pasta descompactada, arquivo a arquivo (só para uma execução sem o pacote juntado; ver Cenário B). `0` se bate, `1` se não, `2` sem o manifesto. Com `--model gpt`: confere o pacote do modelo contra o manifesto dele; `--extracted data/suites/gpt` confere também a pasta |
| `python -m ai_clients generate --model gpt` | `app` | modelos comerciais (`gpt`, `gemini`, `claude`): para cada combinação pendente, um pedido sem memória de pedidos anteriores (o texto inteiro numa única mensagem), grava a resposta inteira, os *tokens*, o custo e o tempo, e transforma a primeira resposta lida em `suite.json` (`accepted_predicted`); resposta que não pode ser lida gera novo pedido, até 3. **Exige `--confirm-spend US$`** fora do `--dry-run` (sem ele, mostra a estimativa e sai com `2`, sem chamar nada); ao atingir esse gasto, não envia pedido novo e sai com `5` (os já enviados terminam e são gravados). `--dry-run` estima o custo sem chamar nenhuma API, sem gravar e sem chave. `--resume` obrigatório depois do primeiro; recusa (`2`), listando o que mudou, se mudou algo que muda as respostas (modelo, parâmetros, formato da resposta, texto-base, dataset); preços, teto, pedidos ao mesmo tempo e esperas podem mudar. `--limit N`, `--problem ID`, `--scenario S` como no modelo local, inclusive na estimativa. Pedidos ao mesmo tempo: `OPENAI_MAX_CONCURRENCY`/`GEMINI_MAX_CONCURRENCY`/`ANTHROPIC_MAX_CONCURRENCY` (padrão 4); cada combinação é tratada por um só de cada vez, e vários `generate --resume` do mesmo modelo dividem a fila (`skipped`). API fora do ar ou limite de pedidos (429): repete a mesma chamada sem gastar tentativa (espera de 5 s dobrando até 60 s, ou a pedida pela API, se maior) até o teto de repetições e sai com `3`, sem gravar. Chave recusada, crédito esgotado, modelo inexistente ou pedido recusado: `3` na hora. Resposta com 0 *tokens* de raciocínio (ou sem a contagem): gravada em `barred/`, sem gastar tentativa, e pedida de novo; na terceira, a suíte é `accepted_barred` (nenhuma legível: aguarda os autores, `manual: ...` e `4`). O comando não para; o resumo final diz quantas houve. Interrompido: `130`; os pedidos em andamento terminam e são gravados |
| `python -m ai_clients generate --model gpt --dry-run --save-requests data/requests` | `app` | (também `--model gemini`, `--model claude`, `--model slm`) o dry-run de sempre e, além dele, grava o corpo de cada pedido **pendente** (o que a próxima geração enviaria, com o prompt inteiro dentro) em `data/requests/<modelo>/<id>.<cenário>.request.json`, uma pasta só por modelo, sem subpastas, mais um `summary.json`. Cada prompt é conferido contra os arquivos do problema: o enunciado (`enunciado.md`), o código (`AC_ref.cpp`) e o exemplo (primeiro teste público) têm de aparecer idênticos, conforme o cenário, e a caixa-preta não pode ter código nem a caixa-branca enunciado. Linha `requests: N saved ...; faithful K/N; exponent warnings ...` no fim; uma linha `unfaithful: ...` por divergência (saída `1`, a gravação vai até o fim); `exponent: <id>: "..."` para cada enunciado com potência de 10 sem o expoente, só aviso, porque vem do próprio dataset. Sem chamar nenhuma API, sem chave e sem Ollama. A pasta do modelo com arquivos é recusada (`2`), a menos que se use `--force`, que apaga só ela antes de gravar. Recusa (`2`) gravar dentro de `data/suites/`, `data/dataset/` ou `manifests/`. `--save-requests` sem `--dry-run`, ou `--force` sem `--save-requests`: `2`. `--problem`, `--scenario` e `--limit` valem também aqui. Só há o que gravar enquanto houver combinação pendente |
| `python -m ai_clients show-request --model gemini --problem 1_B --scenario black_box --output data/requests/1_B.json` | `app` | grava no arquivo o corpo do pedido enviado em uma tentativa (a última, por padrão; `--attempt N` escolhe), com o prompt inteiro dentro, no mesmo formato do dry-run; nada é chamado e o pedido **não** aparece no terminal, só uma linha `written: ... attempt N (of M); prompt sha256 matches; dataset: faithful` e os avisos (`warning: lost exponent ...`, `warning: OLD TEMPLATE VERSION ...`, `warning: parameters changed ...`). O prompt é remontado do texto-base e dos arquivos do problema e conferido contra o hash gravado na tentativa; se o texto-base mudou depois, a versão antiga é procurada no histórico do Git (por isso roda no `app`, que lê o `.git` só para leitura) e, sem ela, nada é gravado (`1`, com os dois hashes). Sem tentativa ainda: a prévia do próximo pedido (`preview, not sent`). `--model slm`, `gpt`, `gemini` ou `claude`. `--barred N` (só nos comerciais) grava uma resposta barrada. `--suites-dir DIR` lê uma execução guardada do mesmo modelo, em outra pasta (por exemplo, uma movida com `mv`). `--output` é obrigatório; arquivo existente → `2`, a menos que se use `--force`; nunca dentro de `data/suites/`, `data/dataset/` ou `manifests/`. Prompt diferente do dataset: gravado (foi o enviado), `dataset: UNFAITHFUL` e `1`. Tentativa inexistente → `2`; combinação danificada → `1` |
| `python -m ai_clients show-request --model slm --suite-attempts --output-dir data/requests/suites` | `app` | (também `--model gpt`/`gemini`/`claude`) de uma vez, para cada combinação que já tem `suite.json`: grava o corpo do pedido da **tentativa que gerou a suíte** (a indicada no `suite.json`, que não é necessariamente a última: numa suíte de reserva pode ser uma das primeiras) em `data/requests/suites/<modelo>/<id>.<cenário>.request.json`, mais um `summary.json`, com as mesmas conferências do `show-request` (hash, texto-base pelo Git, dataset, expoente) e sem mostrar os pedidos. Fim: `suite attempts: N saved ...; prompt sha256 matches in all; faithful K/N; S skipped; ...`. Combinação sem suíte ou fechada à mão: pulada e listada no resumo. Pedido que não pôde ser conferido: linha `refused: ...`, nada gravado para ele, saída `1`. `--problem ID` e `--scenario S` restringem; `--suites-dir` lê uma execução guardada; a pasta do modelo com arquivos exige `--force`; não aceita `--output`, `--attempt` nem `--barred` (`2`) |
| `pytest tests/ai_clients` | `sandbox` | testes do módulo (com modelos simulados; nenhum teste chama uma API paga) |

Códigos de saída: `0` sucesso, `1` falha de dados, `2` uso incorreto, `3` falha de infraestrutura
ou de configuração (Ollama ou API), `4` terminou, mas alguma combinação aguarda os autores
(`close`), `5` teto de gasto atingido (modelos comerciais), `130` interrompido. Prioridade quando
há mais de um: `130`, `3`, `1`, `5`, `4`. O `unzip` do Cenário B é do próprio sistema, fora do
Docker.

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
| `error: another ... is already running over data/suites/slm/` (`1`) | `close`, `package`, `change-template` e o primeiro `generate` só rodam sozinhos; espere o outro terminar |
| `<id> <cenário>: skipped (in use by another command)` | esperado com duas máquinas: a combinação está com o outro comando |
| `infrastructure failure: cannot prepare the workdir ...` (`3`, no `execute`) | use o serviço `sandbox`: `docker compose run --rm sandbox ...` |
| `FAIL` no `verify` | algum arquivo mudou depois do pacote: apague a pasta do modelo em `data/suites/` e descompacte de novo |
| `missing: suites/slm-rev1/...` no `verify --extracted data/suites/slm`, com os arquivos no lugar certo | `--extracted` não entende o pacote juntado do modelo local (Cenário B): use o `verify` sem `--extracted` e o `cli check --deep` |
| `error: this would make up to N paid calls ...; to confirm, run again with --confirm-spend ...` (`2`) | confira a estimativa e rode de novo com `--confirm-spend <teto em US$>` |
| `error: OPENAI_API_KEY is not set in .env` (ou `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`) (`2`) | preencha a chave no `.env` |
| `spend cap reached: spent US$ X of US$ Y ...` (`5`) | o teto da invocação foi atingido; para continuar, `generate --model <modelo> --resume --confirm-spend <novo teto>` |
| `barred: <id> <cenário>: the answer reports ... (at 3, the suite is accepted_barred)` | a resposta veio sem raciocínio; está em `data/suites/<modelo>/barred/` e a combinação é pedida de novo; na terceira, a suíte fica `accepted_barred`. Nada a fazer: o comando segue |
| `gpt unavailable (...); retrying the same call ...` | a API não respondeu ou pediu para esperar; o comando repete sozinho, sem gastar tentativa |
| `configuration error: gpt: the API key in OPENAI_API_KEY was refused ...` ou `... quota or credit ...` (`3`) | corrija a chave ou o crédito da conta e rode `generate --model <modelo> --resume` |
| `configuration error: gemini: the request was refused as malformed ...` (`3`) | a API recusou o formato do pedido (nada foi cobrado); avise os autores |
| `configuration error: gemini: the daily request quota of the API is exhausted ...` (`3`) | a cota de pedidos do dia acabou (na camada gratuita, 20 por dia); nada foi gravado: rode `generate --model gemini --resume` depois que ela renovar |
| `gemini unavailable (HTTP 429: ... quota ...)` ou `(HTTP 503: ... high demand ...)`, repetido | limite de pedidos por minuto ou modelo sobrecarregado; o comando espera e repete sozinho. Para não estourar o limite, defina `GEMINI_MAX_REQUESTS_PER_MINUTE` (e `GEMINI_MAX_CONCURRENCY=1` na camada gratuita) |
| `error: the template of this attempt (sha256 ...) is not the current one (...) and was not found in the Git history` (`1`, no `show-request`) | o texto-base daquela tentativa foi editado e nunca commitado; não há como mostrar o pedido com certeza |
| `error: ... the Git history is not available here (run it in the app service)` (`1`) | rode o `show-request` com `docker compose run --rm app ...` |
| `error: <arquivo> already exists; use --force to overwrite it` ou `... already has files; use --force to replace them` (`2`) | escolha outro destino ou acrescente `--force` |
| `unfaithful: <id> <cenário>: statement (enunciado.md) matched X of Y chars` ou `dataset: UNFAITHFUL` (`1`) | o prompt não traz aquele trecho do dataset idêntico; avise os autores antes de qualquer execução paga |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/enunciado.md`, `AC_ref.cpp`, `testes.json`, `metadata.json` | texto, C++ e JSON | dataset descompactado ([`dataset`](../dataset/README.md)); `metadata.json` traz os limites, `testes.json` os testes públicos |
| `manifests/dataset.manifest.json` | JSON | versionado; conferido antes de qualquer trabalho |
| `src/prompt_templates/slm_prompt.txt` e `slm_predict_prompt.txt` | texto (inglês) | versionados; os textos-base dos pedidos 1 a 12 e 13 a 15, iguais nos três cenários exceto pelo bloco de contexto |
| `OLLAMA_BASE_URL`, `OLLAMA_HARDWARE_LABEL` (opcionais `OLLAMA_HTTP_TIMEOUT_S`, `OLLAMA_MAX_INFRA_RETRIES`, `OLLAMA_MODEL`) | variáveis do `.env` | preenchidas pelo operador (ver `.env.example`) |
| `src/prompt_templates/llm_prompt.txt` | texto (inglês) | versionado; o texto-base dos três modelos comerciais, com as mesmas regras de entradas do modelo local |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` (opcionais, com o prefixo de cada modelo, `..._MAX_CONCURRENCY`, `..._MAX_INFRA_RETRIES` e `..._MAX_REQUESTS_PER_MINUTE`, e `LLM_HTTP_TIMEOUT_S`) | variáveis do `.env` | preenchidas pelo operador; nunca gravadas em arquivo nem em mensagem |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| Respostas, execuções e suíte final de cada combinação | JSON | `data/suites/slm/problems/<id>/<cenário>/` (não versionado); a etapa de avaliação lê o `suite.json` |
| Trocas de texto-base e pedidos refeitos por elas | JSON | `data/suites/slm/template_changes/` e `superseded/` (não versionados; entram no pacote, não nas contagens) |
| Relatório agregado | JSON | `manifests/slm_generation_report.json` (versionado) |
| Pacote do modelo local e manifesto | zip e JSON | `data/slm_suites.zip` e `manifests/slm_suites.manifest.json` (versionados) |
| Respostas, suíte final e respostas barradas de cada modelo comercial | JSON | `data/suites/gpt/`, `data/suites/gemini/` e `data/suites/claude/` (não versionados); o `suite.json` tem as mesmas chaves do modelo local, e a avaliação lê os quatro modelos do mesmo jeito |
| Relatório, pacote e manifesto de cada modelo comercial | JSON e zip | `manifests/<modelo>_generation_report.json`, `data/<modelo>_suites.zip`, `manifests/<modelo>_suites.manifest.json` (versionados) |
| Corpo dos pedidos (`show-request`, `generate --dry-run --save-requests`) e o resumo das conferências | JSON | onde os autores pedirem, sugerido `data/requests/` (não versionado; só consulta, nunca lido por outro comando) |

## (e) Dependências e pré-requisitos

- Python 3.11 da imagem (`docker compose build`); nenhuma dependência além das fixadas no `uv.lock`.
- Um ou mais servidores Ollama acessíveis com `qwen2.5-coder:14b` baixado (a execução final usou
  Ollama 0.35.0, quantização Q4_K_M, `num_ctx` 8192 e `num_predict` 5120), e o `.env` preenchido
  (só para gerar de novo o modelo local).
- Serviço `app` para geração, `close`, `change-template`, `report`, `package`, `verify` e
  `show-request` (o `app` lê o histórico do Git, só para leitura, para achar um texto-base antigo);
  `sandbox` para `execute` (motor do módulo [`sandbox`](../sandbox/README.md), sem alteração).
- Dataset descompactado em `data/dataset/` e íntegro.
- Modelos comerciais (só para gerar de novo): contas com faturamento ativo na OpenAI, no Google e na
  Anthropic, chaves no `.env`, e a internet do serviço `app` (Responses API da OpenAI,
  `generateContent` da Gemini API e Messages API da Anthropic). Nenhuma biblioteca de cliente além da
  biblioteca padrão do Python.

## (f) Limitações conhecidas

- **Pacote do modelo local juntado**: ele reúne a execução da revisão 1 do dataset (392
  combinações) e a refeita na revisão 2 (as 208 cujo enunciado mudou); `data/suites/slm/provenance.json`
  diz de qual execução vem cada combinação. Por isso `verify --extracted data/suites/slm` não serve
  para ele (relata `missing:` para tudo que está em `data/suites/slm-rev1/`); use o `verify` do zip e
  o `cli check --deep` (Cenário B).
- A solução Python do modelo local só é validada pelos testes públicos; se errar numa entrada que
  nenhum teste público cobre, a saída esperada daquela entrada fica errada.
- As suítes `accepted_fallback` vêm de soluções que erraram um exemplo, e as `accepted_predicted` e
  `accepted_barred` têm saídas escritas pelo modelo sem conferência: parte das saídas delas pode
  estar errada. O relatório separa as suítes por `status`, para a análise nunca misturá-las com as
  `accepted`.
- Nos cenários com código, o modelo pode só traduzir a solução C++ para Python.
- Não há verificação de que a solução Python é determinística nem de que cada entrada respeita as
  restrições do enunciado. Na predição, só testes com valores abreviados (`1 1 ... 1`, `…`) são
  descartados; uma linha só de pontos (como `...` numa grade) é mantida.
- **Modelos comerciais**: as respostas não são reproduzíveis bit a bit (não há seed); a versão do
  modelo que respondeu fica gravada em cada resposta, e o provedor pode trocá-la sem aviso. Uma
  saída esperada errada vira falso positivo na avaliação. O teto de saída é de 32.768 *tokens*; a
  estimativa do `--dry-run` usa uma razão caracteres/*token* aproximada. O Claude Haiku 5.5 pode
  recusar um pedido pelo filtro de segurança da Anthropic (`refusal`), mesmo num enunciado
  inofensivo, e não tem modelo reserva: a combinação esgota as tentativas e é fechada à mão. No
  Gemini, uma cota esgotada não se distingue do limite de pedidos por minuto: os dois são repetidos
  até o teto de repetições.
- O `OLLAMA_HARDWARE_LABEL` é texto livre: todas as chamadas da execução final têm a mesma etiqueta,
  embora parte tenha rodado noutra plataforma com o mesmo modelo de placa (T4), a mesma versão do
  Ollama e o mesmo modelo.
- Resultados de cada execução (combinações por `status`, chamadas, custo, tempos) e as decisões por
  trás deles: metodologia, seção 3.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 3
- Testes: `tests/ai_clients/` (`docker compose run --rm sandbox pytest tests/ai_clients`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `generate --dry-run` (200 problemas) | 2026-10-11 | c967f97 |
| `generate` (inclusive interrupção e retomada, duas máquinas em paralelo) | 2026-10-09 | 968c5ba |
| `execute` | 2026-10-09 | 968c5ba |
| `close` | não necessário (0 combinações aguardando os autores) | — |
| `change-template` | 2026-10-08 | 968c5ba |
| `report` | 2026-10-09 | 968c5ba |
| `package` | 2026-10-11 | f43d95c |
| `verify` (o zip; a pasta, com `--extracted`, só em execução sem o pacote juntado) | 2026-10-11 | c967f97 |
| `generate --model gpt --dry-run` e `generate --model gemini --dry-run` (200 problemas) | 2026-10-15 | 696da2c+dirty |
| `generate --model claude --dry-run` e `--save-requests` (200 problemas) | 2026-10-20 | 29d9245+dirty |
| `generate --model claude` (execução completa, 600 combinações) | 2026-10-20 | 29d9245+dirty |
| `generate --model gemini` (chamadas pagas; 5 problemas e execução completa, 600 combinações) e `report --model gemini` | 2026-10-20 | 29d9245+dirty |
| `generate --model gpt` (execução completa, 600 combinações) | 2026-10-20 | 29d9245+dirty |
| `close --model claude` (3 combinações) | 2026-10-20 | 29d9245+dirty |
| `change-template --model ... --template llm` | não necessário (texto-base dos comerciais nunca trocado: `template_changes` vazio nos três relatórios) | — |
| `report --model gpt` | 2026-10-20 | 29d9245+dirty |
| `package --model gemini` | 2026-10-20 | 29d9245+dirty |
| `package --model gpt` | 2026-10-20 | 29d9245+dirty |
| `package --model claude` e `report --model claude` | 2026-10-20 | 29d9245+dirty |
| `package --merge-from data/suites/slm-rev1` (208 combinações novas e 392 da revisão 1) | 2026-10-22 | 8c22193+dirty |
| `verify --model gemini` (inclusive `--extracted data/suites/gemini`) | 2026-10-20 | 29d9245+dirty |
| `verify --model gpt` (inclusive `--extracted data/suites/gpt`) | 2026-10-20 | 29d9245+dirty |
| `verify --model claude` (inclusive `--extracted data/suites/claude`) | 2026-10-20 | 29d9245+dirty |
| `generate --model gpt --dry-run --save-requests` e `--model slm` (200 problemas) | 2026-10-16 | d005d57+dirty |
| `show-request` (`--model gemini`, `--model slm`, prévia do `--model gpt`) | 2026-10-16 | d005d57+dirty |
| `show-request --model slm --suite-attempts` (600 combinações) | 2026-10-18 | d005d57+dirty |
