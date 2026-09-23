# Módulo `dataset`

> **Status**: implementado · **Feature**:
> `specs/001-dataset-extraction/` · **Metodologia**: `docs/metodologia-referencia.md`, seção 1

## (a) Propósito

Extrai do `code_contests` os problemas elegíveis do experimento, valida o código de cada um no
motor de execução e empacota o resultado num arquivo único, verificável, pronto para ser
distribuído e consumido pelos módulos seguintes.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
— baixar o projeto, criar o `.env`, criar a pasta `data/`, construir a imagem e conferir com o
`pytest`. Sem isso os comandos abaixo não funcionam.

### O que este módulo faz

Lê o dataset público `code_contests` (Hugging Face) **em streaming**, sem baixá-lo inteiro para o
disco. De cada problema, aplica critérios de elegibilidade — só problemas do Codeforces, nota
(`rating`) entre 1000 e 1600, pelo menos uma tag entre `implementation`, `math`, `greedy`,
`strings`, `binary search`, `dp`, `sortings`, nenhuma tag proibida (geometria, interativo, jogos,
probabilidade, construtivo), nenhum enunciado que dependa de figura, sem tradução automática, com
solução correta e submissões incorretas em C++, sem entrada/saída por arquivo — e classifica os
que sobram em uma de três macrocategorias algorítmicas (`matematica`, `estrutural_otimizacao`,
`logica_direta`), por prioridade de tag. Detalhes de cada critério e da regra de classificação:
metodologia, seções 1.2 e 1.3.

Dos problemas elegíveis, os **200 primeiros** (numa ordem embaralhada uma única vez, com seed
fixa, para o experimento ser reprodutível) que conseguem ter o código correto **e** exatamente 100
submissões incorretas confirmadas como falhas reais (não erro de compilação, não estouro de tempo
ou memória) pelo motor de execução isolado (módulo [`sandbox`](../sandbox/README.md)) formam a
amostra final. Cada código passa pelo motor mais de uma vez, em momentos diferentes, antes de
entrar no dataset — é o que garante que uma submissão marcada como falha real continua falhando de
forma estável, não por acaso de hardware. O resultado final é compactado num único arquivo
(`data/dataset.zip`) com um manifesto de hashes, para poder ser distribuído e conferido.

### Qual é o seu cenário?

#### Cenário 1 — Só preciso do dataset já pronto (o caso mais comum)

Se alguém já gerou e publicou o dataset no repositório (é o caso deste projeto: o zip e os
manifestos já estão commitados), você só precisa descompactar e conferir a integridade — **nunca**
precisa rodar extração nem validação, que levam horas:

```bash
unzip data/dataset.zip -d data/
docker compose run --rm app python scripts/verify_dataset.py --extracted data/dataset
```

Esperado: a última linha é `OK`. O `unzip` cria `data/dataset/problems/<problem_id>/`, uma pasta
por problema, cada uma com `enunciado.md`, `AC_ref.cpp` (a solução correta), `WA_1.cpp` a
`WA_100.cpp` (as 100 falhas reais), `testes.json` (a suíte oficial), `metadata.json` (rating, tags,
macrocategoria, limites) e `validacao.json` (o veredito de cada código e como ele foi decidido). É
esta pasta — `data/dataset/`, com exatamente esses 200 problemas — que os módulos seguintes do
pipeline devem ler; ver "Qual pasta eu uso?" em (d).

Se o zip mudar (um `git pull` trouxe uma versão nova), refaça os dois comandos; se já havia uma
`data/dataset/` antiga, apague-a antes (`rm -rf data/dataset`) para não deixar arquivos de uma
versão anterior misturados com os da nova — sem o `rm`, a verificação aponta os arquivos que
sobraram como `extra`.

Quem não tem `unzip` instalado pode usar `docker compose run --rm app python -m zipfile -e
data/dataset.zip data/` — produz a mesma árvore.

#### Cenário 2 — Quero gerar o dataset do zero (ou gerar uma versão nova)

Só é preciso se você está criando o dataset pela primeira vez, ou refazendo-o depois de uma
mudança nos critérios ou no motor. É um processo de **cinco comandos manuais e separados**,
nesta ordem, cada um descrito com detalhe logo abaixo: `extract` → `validate` → `audit` →
`package` → `verify`. Nenhum comando chama o próximo sozinho. Leva de um a alguns dias de relógio
(a validação sozinha leva horas), então é feito **uma única vez**, por uma pessoa, e o resultado é
publicado pelo Git para as demais.

1. **`extract`** — lê o dataset de origem e grava, na sua máquina, só os problemas elegíveis:

   ```bash
   docker compose run --rm app python -m dataset extract
   ```

   Roda no serviço `app` (tem internet). Demora a depender da sua rede (na única execução real
   deste projeto, ~23 minutos). Pode ser interrompido com Ctrl+C e retomado com o mesmo comando:
   só o trecho em andamento é refeito. Ao final imprime o total lido, quantos problemas ficaram
   elegíveis e a distribuição por macrocategoria; o relatório completo fica em
   `data/work/reports/extraction_report.md`. Para um teste rápido antes da extração completa
   (poucos minutos, lê só as primeiras linhas de cada parte do dataset), use
   `--limit-rows 400`; para recomeçar do zero depois de um teste rápido, `rm -rf data/work`.

2. **`validate`** — executa, no motor isolado, o código de cada problema elegível, na ordem
   gravada por `extract`, até reunir 200 problemas completos:

   ```bash
   docker compose run --rm sandbox python -m dataset validate
   ```

   Roda no serviço `sandbox` (sem rede, o único autorizado a compilar e executar código de
   terceiros) e é a etapa mais longa: na única execução real deste projeto, **5 horas e 6
   minutos**, com 4 processos em paralelo (o número de processos só muda o tempo, nunca o
   resultado — ajuste com `--workers N`). Antes de rodar a execução completa, vale medir num
   piloto pequeno quantas submissões incorretas realmente viram falha confirmada (varia por
   problema) e quanto tempo por problema esperar: `docker compose run --rm sandbox python -m
   dataset validate --target 10`. O comando roda uma auto-checagem do motor antes de tudo e
   recusa continuar se ela falhar. Pode ser interrompido a qualquer momento (Ctrl+C, `docker
   stop`, queda de energia) e retomado com o mesmo comando: problemas já concluídos não são
   refeitos, só o que estava em andamento. Cada problema termina em um de três estados:

   | Estado | O que significa |
   |---|---|
   | `complete` | o código correto passou em toda a suíte oficial e há exatamente 100 falhas reais confirmadas; conta para a amostra |
   | `pending_triage` | o código correto, que deveria estar certo, falhou no motor; o problema é excluído da amostra e fica registrado para inspeção manual futura (não é feita automaticamente) |
   | `discarded` | não há 100 submissões incorretas que se confirmem como falha real (poucas distintas, ou muitas só dão erro de compilação/tempo/memória) |

   Ao final, imprime `included N of 200 (deficit D)`: `D` é `0` em caso de sucesso. Se terminar
   com déficit, nada é relaxado automaticamente (nem os critérios de elegibilidade, nem a meta de
   100 falhas por problema) — é preciso decidir manualmente o que fazer com os problemas em
   `pending_triage`.

3. **`audit`** — reexecuta, de forma independente, o código de cada problema já `complete` e
   confere se o resultado continua o mesmo:

   ```bash
   docker compose run --rm sandbox python -m dataset audit
   ```

   Existe porque `validate` decide cada código sob concorrência (vários processos disputando CPU
   ao mesmo tempo), e um código cujo resultado dependa de tempo no limiar do limite, ou de
   comportamento indefinido (memória não inicializada, acesso fora dos limites de um vetor), pode
   passar por sorte numa execução e falhar na outra — um gabarito instável assim não serve para
   as métricas do experimento. Uma falha desse tipo encontrada no `audit` é **reparada
   automaticamente**: o candidato instável é substituído pelo próximo candidato, ainda não
   tentado, da mesma ordem determinística que gerou o problema, agora exigindo uma confirmação
   mais forte (seis execuções concordantes, em vez das duas da seleção original). O número de
   falhas continua exatamente 100, com a mesma numeração dos arquivos; nenhum outro arquivo do
   problema muda. Se os candidatos disponíveis se esgotarem sem achar um substituto estável, o
   comando avisa explicitamente (`could not be repaired`) — não há reparo silencioso. Se o
   **código correto** de um problema falhar na auditoria (mais raro), o problema inteiro sai da
   amostra e vira `pending_triage`; rode `validate` de novo para completar a meta com o próximo
   problema da ordem. Rode `audit` uma última vez, sem nada para reparar, como conferência final
   antes de empacotar.

4. **`package`** — reúne todos os problemas `complete` num zip determinístico e grava o
   manifesto de integridade:

   ```bash
   docker compose run --rm app python -m dataset package
   ```

   Roda no serviço `app` (não precisa do motor nem de rede: só lê o que `validate`/`audit` já
   gravaram e compacta). Recusa empacotar se menos de 200 problemas estiverem `complete` (a menos
   que se passe `--allow-partial`, só para testes). Avisa, sem impedir, se o zip passar de 95 MB
   (o GitHub recusa arquivos acima de 100 MB num push comum). Reempacotar o mesmo conjunto de
   problemas sempre produz o mesmo zip, byte a byte, no mesmo ambiente — não há custo nem risco em
   rodar de novo.

5. **`verify`** — recalcula os hashes de tudo e compara com o manifesto:

   ```bash
   docker compose run --rm app python -m dataset verify
   ```

   Confirme `OK` antes de publicar. Depois, o zip e os manifestos (`data/dataset.zip`,
   `manifests/dataset.manifest.json`, `manifests/extraction_report.json`) são o que se manda para
   as demais pessoas pelo Git — nada disso é commitado automaticamente por nenhum dos comandos
   acima; é sempre uma decisão manual (`git add`, `git commit`, `git push`).

O computador precisa ficar ligado durante a validação (a etapa mais longa); em notebook, mantenha
na tomada e evite suspensão (`systemd-inhibit --what=sleep:idle -- <comando>` no Linux impede a
suspensão enquanto o comando roda).

#### Cenário 3 — Só quero conferir se o motor está saudável, ou rodar os testes

```bash
docker compose run --rm sandbox python -m dataset selfcheck   # 9 programas de veredito conhecido
docker compose run --rm sandbox pytest tests/dataset          # testes automatizados do módulo
```

`selfcheck` não lê nada do dataset: só confirma que o motor de execução (compilação, isolamento,
limites, veredito) está se comportando como esperado. É a mesma checagem que `validate` roda
sozinho antes de começar.

### Opções de linha de comando

| Comando | Opção | Padrão | Efeito |
|---|---|---|---|
| `extract` | `--seed INT` | `42` | seed da ordem de processamento; fica gravada no pool (mudar sem combinar muda quais problemas entram na amostra) |
| `extract` | `--splits LIST` | `train,valid,test` | splits lidos, nesta ordem (a primeira ocorrência de um problema vence) |
| `extract` | `--limit-rows N` | sem limite | limita as linhas lidas por split (só para testes rápidos) |
| `validate` | `--target N` | `200` | meta de problemas `complete`; a execução para ao atingi-la |
| `validate` | `--workers N` | metade das CPUs (mínimo 1) | processos em paralelo por problema; **não altera o resultado**, só o tempo |
| `validate` | `--problem ID` | — | valida só este problema (identificador `<ContestID>_<Índice>`) e ignora a meta |
| `audit` | `--problem ID` (repetível) | todos os `complete` | escopo da auditoria |
| `audit` | `--workers N` | metade das CPUs | processos em paralelo |
| `package` | `--target N` | `200` | problemas `complete` exigidos antes de empacotar |
| `package` | `--allow-partial` | desligado | empacota mesmo com menos de `--target` problemas `complete` (só para testes) |
| `verify` / `verify_dataset.py` | `--zip PATH` | `data/dataset.zip` | pacote a verificar |
| `verify` / `verify_dataset.py` | `--manifest PATH` | `manifests/dataset.manifest.json` | manifesto |
| `verify` / `verify_dataset.py` | `--extracted DIR` | — | confere também a árvore descompactada (`DIR` é a pasta `dataset/` em si, ex. `data/dataset`) |

`docker compose run --rm app python -m dataset --help` (ou `<comando> --help`) sempre lista as
opções de fato disponíveis.

Códigos de saída, comuns a todos os comandos: `0` sucesso, `1` falha de dados (déficit,
divergência de integridade, comando fora de ordem), `2` uso incorreto, `3` falha de
infraestrutura (rede, disco, ambiente — repita o comando, é seguro), `130` interrompido (Ctrl+C
ou `docker stop`; também seguro).

### `report`: o resumo legível, gerado sozinho

`docker compose run --rm app python -m dataset report` regenera
`data/work/reports/extraction_report.{md,json}` a partir do que já está gravado, sem executar
nada. **Normalmente não é preciso rodá-lo à mão**: `extract`, `validate` e `audit` já o regeram ao
terminar. Só é útil para atualizar o resumo depois de mexer manualmente numa pasta de problema, ou
para acompanhar o andamento de uma validação longa por outra janela de terminal.

### Se algo der errado

| O que aparece | O que significa | O que fazer |
|---|---|---|
| `infrastructure failure: ...` (código `3`) | falha de rede ou de disco | rode o mesmo comando de novo; retoma de onde parou |
| `interrupted; it is safe to run the command again` (código `130`) | Ctrl+C ou `docker stop` | rode o mesmo comando de novo |
| `error: no pool found; run ...` (código `1`) | rodou `validate`/`report` antes de `extract` | rode `extract` primeiro |
| `selfcheck` com `FAIL`, ou `infrastructure failure` | motor com veredito errado, ou rodado no serviço `app` em vez de `sandbox` | veja a tabela de erros do [`sandbox`](../sandbox/README.md) |
| `error: <id> is not in the pool` (código `2`) | `--problem` com um identificador que não existe no pool | confira o identificador em `data/work/staging/pool.json` |
| `<id>: already closed (...), skipped` | o problema já foi encerrado numa execução anterior | normal na retomada; apague `data/work/problems/<id>/` se quiser reprocessá-lo |
| `N problem(s) in pending_triage need individual inspection now` (código `1`) | a meta não foi atingida com o resto do pool | inspecione cada um em `data/work/problems/<id>/validacao.json` (campo `triage`) e decida manualmente; nada é relaxado sozinho |
| `error: only N of 200 complete problems; pass --allow-partial ...` (código `1`) | `package` rodado antes da meta ser atingida | rode `validate` até `deficit 0`, ou use `--allow-partial` só para teste |
| `warning: ... above the 95 MB warning threshold` | o zip passou de 95 MB (aviso, não impede) | veja (f), "Tamanho do dataset", antes de publicar |
| `error: manifest not found: ...` (código `2`) | `verify` sem `data/dataset.zip`/manifesto nos caminhos esperados | rode `package` (quem gera) ou confira o `git pull`/`unzip` (quem recebe) |
| `changed:` / `missing:` / `extra:` seguido de `FAIL` (código `1`) | integridade divergente | não use esse dataset; refaça o `unzip`, ou gere o zip de novo |
| `PermissionError` ao gravar em `data/` | `data/` pertence a `root` (passo 3 do guia da raiz foi pulado) | `sudo chown -R "$(id -u):$(id -g)" data` e rode de novo |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| Dataset `deepmind/code_contests` | streaming Parquet pela biblioteca `datasets`, numa revisão fixa | Hugging Face (público; licença CC-BY-4.0) |
| `HF_TOKEN` (opcional) | variável de ambiente, lida do `.env` | só aumenta o limite de requisições |
| Opções de linha de comando | ver tabela acima | quem executa |
| Pool e problemas brutos (para `validate`) | `data/work/staging/pool.json` e `raw/*.json.gz` | gerados por `extract` |
| Problemas já validados (para `audit`) | `data/work/problems/<id>/` | gerados por `validate` |

## (d) Saídas produzidas

### Qual pasta eu uso?

Existem duas pastas parecidas em `data/`, e é fácil confundi-las:

- **`data/work/`** — o **espaço de trabalho de quem gera** o dataset. Existe só se você rodou
  `extract`/`validate`/`audit` nesta máquina (cenário 2). Contém **todos** os problemas
  processados, não só os 200 da amostra final: os `complete`, mas também os `discarded` e os
  `pending_triage`, além dos elegíveis que a validação nem chegou a tentar. Serve para auditoria,
  retomada e depuração — nunca é lido por nenhum outro módulo do pipeline, e nunca é commitado no
  Git (é ignorado por padrão). Pode ser apagado com segurança **depois** que `package` e `verify`
  tiverem sido concluídos com sucesso; apagar antes disso significa perder o trabalho de horas e
  ter que rodar tudo de novo.
- **`data/dataset/`** — a cópia de **distribuição**, obtida descompactando `data/dataset.zip`
  (cenário 1). Contém **só** os 200 problemas `complete` da amostra final, no mesmo layout de
  arquivos. **É esta pasta que os módulos seguintes do pipeline (geração de mutantes, chamadas aos
  modelos, avaliação) devem ler** — nunca `data/work/problems/`, que pode ter problemas fora da
  amostra e não é garantida como íntegra por nenhum manifesto.

Se você gerou o dataset nesta máquina (cenário 2) e também descompactou o zip depois, as duas
pastas coexistem sem conflito — cada uma tem sua finalidade, e não há duplicação problemática: uma
é o rascunho de trabalho, a outra é o produto final conferido. Se só o espaço em disco importa,
`data/work/` pode ser apagada com segurança depois que o zip estiver publicado; `data/dataset/`
pode sempre ser recriada a partir do zip com `unzip`.

### Onde cada arquivo fica

`data/work/` é um diretório privado (permissão `0700`, só o seu usuário lê) e nunca vai para o
Git. A única saída **distribuída** é a de `package`: `data/dataset.zip` e `manifests/`.

| Saída | Formato | Onde entender melhor |
|---|---|---|
| `data/work/staging/pool.json` | pool de problemas elegíveis, na ordem de processamento | lido por `validate` e `report` |
| `data/work/staging/raw/<problem_id>.json.gz` | enunciado, testes e códigos de um problema elegível | lido pela validação |
| `data/work/problems/<problem_id>/` | pasta de um problema encerrado (`complete`, `pending_triage` ou `discarded`) | conteúdo na tabela do cenário 2, passo 2 |
| `data/work/building/<problem_id>/` | problema em construção; descartado e refeito se a execução for interrompida | só existe durante uma validação em andamento |
| `data/dataset.zip` | zip determinístico, raiz `dataset/`, só os 200 problemas `complete` | **versionado**; ver "Qual pasta eu uso?" acima |
| `manifests/dataset.manifest.json` | hash SHA-256 do zip e de cada arquivo dentro dele | **versionado**; conferido por `verify` |
| `manifests/extraction_report.json` | cópia do relatório final | **versionado** |

### Arquivos de relatório e auditoria (o que conferir em cada um)

| Arquivo | Gerado por | O que tem | Para que serve |
|---|---|---|---|
| `data/work/reports/extraction_report.md` | `extract`, `validate`, `audit`, `report` | resumo legível: funil de elegibilidade (quantos problemas restam depois de cada critério), distribuição da amostra por macrocategoria e por split, descartes por motivo, casos de triagem, se o alerta de "menos de 30 problemas numa macrocategoria" disparou | primeira leitura para entender o resultado; é a base dos números citados no trabalho escrito |
| `data/work/reports/extraction_report.json` | idem | os mesmos dados do `.md`, estruturados | leitura automatizada; copiado para `manifests/extraction_report.json` no empacotamento |
| `manifests/extraction_report.json` | `package` | cópia congelada do relatório no momento do empacotamento | acompanha a versão exata do dataset publicado — use este, não o de `data/work/`, para citar números de uma versão já distribuída |
| `manifests/dataset.manifest.json` | `package` | hash SHA-256 do zip inteiro e de cada arquivo dentro dele, mais proveniência (revisão do dataset de origem, seed, versão do compilador) | é contra este arquivo que `verify` confere a integridade; confira aqui se um arquivo específico do dataset foi alterado |
| `data/work/reports/validation_log.jsonl` | `validate` | uma linha JSON por problema processado: estado final, quantas candidatas viraram cada resultado (falha real, erro de compilação, tempo excedido, ...), tempo gasto | diagnóstico fino de uma execução de `validate` (por exemplo, para entender por que um problema específico não fechou) |
| `data/work/reports/selfcheck.json` | `validate` (e `selfcheck`) | resultado da auto-checagem do motor, um veredito esperado vs. obtido por programa de teste | confirma que o motor estava confiável no momento da validação; alimenta o campo `engine_selfcheck` do relatório |
| `data/work/problems/<id>/validacao.json` | `validate`, `audit` | por problema: o veredito de cada código, o padrão de C++ usado na compilação, tempo e memória máximos observados, e (se aplicável) o registro completo de uma triagem | conferência problema a problema; é o arquivo que comprova que aquele código específico passou pelo motor |

## (e) Dependências e pré-requisitos

- Python 3.11.16, `datasets` 5.0.1 e `pydantic` 2.x, fixados no `uv.lock`.
- Serviço `app` do Docker Compose (com rede) para `extract`, `report`, `package` e `verify`;
  serviço `sandbox` (sem rede, com as capabilities do motor) para `selfcheck`, `validate` e
  `audit`. O ambiente é construído com `docker compose build`.
- `.env` com `HOST_UID` e `HOST_GID` do seu usuário; `HF_TOKEN` é opcional. Passo 2 do guia da
  raiz.
- Diretório `data/` criado por você (`mkdir -p data`) antes do primeiro comando. Passo 3 do guia
  da raiz; se pulado, o `chown` da tabela "Se algo der errado" resolve.
- Nenhum módulo anterior precisa ter rodado.

## (f) Limitações conhecidas

- **Sem entrada/saída por arquivo**: problemas que leem de `input.txt`/escrevem em `output.txt`
  são excluídos, porque o motor injeta a entrada por `stdin` e lê a saída por `stdout`.
- **Disponibilidade desigual de falhas reais**: quantas submissões incorretas realmente se
  confirmam como falha (em vez de erro de compilação, tempo ou memória excedidos) varia por
  problema; nos splits `valid`/`test` há tipicamente menos submissões incorretas disponíveis do
  que no `train`, então a amostra final tende a vir majoritariamente do `train`. Um piloto pequeno
  (`validate --target 10`) antes da execução completa ajuda a estimar isso no seu ambiente.
- **Triagem manual é adiada por padrão**: problemas cujo código correto falha no motor
  (`pending_triage`) ficam registrados, fora da amostra, mas não são inspecionados manualmente a
  menos que a meta de 200 não seja atingida com o resto do pool.
- **A auditoria repara automaticamente**, não apenas relata, uma falha cujo resultado se mostrar
  instável entre duas reexecuções — o motivo típico é comportamento indefinido no código incorreto
  (memória não inicializada, acesso fora dos limites) ou tempo de execução bem no limiar do
  limite, não a entrada em si. Isso afetou cerca de 1 em cada 10 problemas da amostra na única
  execução completa deste projeto, sempre resolvido automaticamente com um substituto de
  qualidade equivalente (mesmos critérios de estabilidade, confirmação mais forte que a original).
- **Retomada é segura e não muda o resultado**: interromper qualquer comando e rodá-lo de novo
  produz exatamente o mesmo resultado de uma execução ininterrupta — mesmo conteúdo de arquivo,
  mesmos vereditos — com duas exceções conhecidas e esperadas, que nunca mudam a seleção: o
  carimbo de data/hora de extração de cada problema, e o tempo de CPU medido (`max_cpu_time_s`
  em `validacao.json`), que naturalmente varia entre execuções em hardware real.
- **Tamanho do dataset**: na única execução completa deste projeto, o zip final ficou em torno de
  12 MiB para 200 problemas — bem abaixo do limite de 100 MB do GitHub para um push comum
  (`package` avisa, sem impedir, a partir de 95 MB).
- **O hash do zip depende da versão da biblioteca de compressão da imagem Docker**: reempacotar o
  mesmo conjunto de problemas na mesma imagem sempre dá o mesmo hash; comparar hashes de zips
  gerados em imagens diferentes não é garantido. Por isso o manifesto também guarda o hash de cada
  arquivo individual dentro do zip — a integridade do conteúdo não depende de todos usarem
  exatamente a mesma versão dessa biblioteca.
- Um programa em avaliação pode gravar arquivos temporários no diretório do seu processo isolado;
  eles persistem entre os testes de uma mesma suíte e são apagados só a cada nova compilação.

## Referências

- Metodologia completa: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 1
- Contratos técnicos: [cli.md](../../specs/001-dataset-extraction/contracts/cli.md) e
  [data-model.md](../../specs/001-dataset-extraction/data-model.md)
- Testes: `tests/dataset/` (`docker compose run --rm sandbox pytest tests/dataset`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `extract` | 2026-09-20 | 7440706 |
| `report` | 2026-09-20 | 71747a1 |
| `selfcheck` | 2026-09-21 | 5121759 |
| `validate` (inclusive retomada após interrupção) | 2026-09-22 | c4c394a |
| `audit` | 2026-09-22 | 9b87d7e |
| `package` | 2026-09-22 | 9b87d7e |
| `verify` / `scripts/verify_dataset.py` (inclusive pós-clonagem) | 2026-09-22 | 9b87d7e |
