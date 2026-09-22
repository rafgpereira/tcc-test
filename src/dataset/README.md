# Módulo `dataset`

> **Status**: em implementação · **Feature**:
> `specs/001-dataset-extraction/` · **Metodologia**: `docs/metodologia-referencia.md`, seção 1

## (a) Propósito

Extrai do dataset `code_contests`, em streaming, os problemas elegíveis do experimento e os classifica em macrocategorias, para depois validar seu código C++ e empacotar o dataset verificável.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando):
baixar o projeto, criar o `.env`, criar a pasta `data/`, construir a imagem e conferir com o
`pytest`. Sem isso os comandos abaixo não funcionam. Todos rodam **dentro do Docker**: `extract` e
`report` no serviço `app`, que tem acesso à internet (o serviço `sandbox` não tem, por isso não
serve para baixar o dataset), e `selfcheck`, `validate` e `audit` no serviço `sandbox`, que é o que
compila e executa C++ de terceiros. Rode-os na pasta do repositório.

### O que este módulo faz, na prática

Lê o dataset público `code_contests` no Hugging Face **em streaming** (lê aos poucos, sem baixar o
dataset inteiro para o disco), separa os problemas que servem ao experimento (critérios de
elegibilidade da metodologia, seção 1.2), classifica cada um em uma macrocategoria e guarda na sua
máquina, dentro de `data/work/`, o enunciado, os testes e os códigos C++ de cada problema
elegível. A extração real de 2026-09-20 resultou em **1.234 problemas** elegíveis. **Ainda não valida** se os
códigos funcionam: isso vem nas próximas etapas da feature.

`extract` é a **fase 1 de 5** do ciclo do módulo (`extract`, `validate`, `audit`, `package`,
`verify`); existem hoje `extract`, `report`, `selfcheck`, `validate` e `audit` (`package` e `verify`
ainda não). A validação (`validate` e `audit`) está implementada e testada. O `validate`
foi executado sobre o dataset real em 2026-09-21 (piloto de 10 problemas e execução completa de 200,
que levou 5 h 06 min; resultados na metodologia, seção 1.7); a auditoria (`audit`) ainda não. O ciclo completo é feito **uma vez, por um dos
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

   Na primeira execução real (2026-09-20) levou cerca de **23 minutos**; a duração depende da sua
   rede. Pode apertar Ctrl+C e repetir o mesmo comando depois: só o trecho (shard) em andamento é
   refeito. Aparecem primeiro barras de progresso do Hugging Face (`README.md`,
   `dataset_infos.json`, `Resolving data files`), que são normais. Depois vem uma linha por trecho,
   no formato `train shard 3/39: 342 rows, 32 eligible` (linhas lidas e problemas elegíveis
   naquele trecho; `already done` quando ele já estava pronto de uma execução anterior): 39 trechos
   de `train`, 1 de `valid` e 1 de `test`. No fim aparecem `pool: 1234 eligible problems`,
   `read 13610 rows; 1234 eligible problems`, uma linha com o total por macrocategoria e `report:`
   com o caminho do relatório.

3. **Conferir o resultado.** Veja o código de saída (`echo $?`, esperado `0`) e abra os arquivos,
   que estão na sua pasta `data/work/` (não dentro de um contêiner):

   ```bash
   ls data/work/staging                       # pool.json, raw/ e shards/
   less data/work/reports/extraction_report.md   # funil de elegibilidade e distribuição
   ```

   No relatório, confira o funil (quantos problemas restam após cada critério) e a distribuição do
   pool por macrocategoria. Como a revisão do dataset e a seed são fixas, o resultado é
   **determinístico** e o seu deve ser exatamente o da extração real de 2026-09-20: 13.610 linhas
   lidas e **1.234 problemas** no pool (`estrutural_otimizacao` 407, `matematica` 278,
   `logica_direta` 549; `train` 1.206, `valid` 9, `test` 19). O funil, em ordem, termina assim:
   1.288 (sem termo visual) → 1.279 (sem E/S por arquivo) → 1.250 (com soluções em C++) →
   1.234 (com ao menos 100 incorretas em C++). A tabela de "motivos de rejeição" conta cada critério
   sobre todas as linhas lidas (uma linha pode ter vários motivos), por isso ela não soma como o
   funil. Se os seus números diferirem, avise os autores, porque a documentação precisa ser
   corrigida. Depois da extração, `data/work/` ocupa cerca de 104 MB.

4. **Regenerar o relatório (opcional).** Refaz o relatório a partir dos arquivos já gravados, sem
   baixar nada:

   ```bash
   docker compose run --rm app python -m dataset report
   ```

   Enquanto a validação não existir, a amostra aparece vazia; é o esperado.

5. **Conferir o motor de execução (`selfcheck`).** Não baixa nem valida nada do dataset: roda 9
   programas de veredito conhecido pelo motor (módulo [`sandbox`](../sandbox/README.md)) e confere
   os vereditos. É o portão de entrada do `validate`, quando ele existir. Note o serviço
   `sandbox`, não `app`:

   ```bash
   docker compose run --rm sandbox python -m dataset selfcheck
   ```

   Leva cerca de 7 segundos; esperado `selfcheck OK: 9/9 cases` e código `0`. Se rodar no
   serviço `app`, termina com `infrastructure failure` (código `3`), porque o `app` não tem o motor.

6. **Validar os problemas no motor (`validate`).** **Como os 200 problemas são escolhidos**: o pool
   elegível (1.234 problemas dos três splits juntos) foi embaralhado uma única vez com a seed 42 e
   gravado nessa ordem em `pool.json`; o `validate` percorre essa ordem e a amostra são os **200
   primeiros problemas que completam a validação**. Os que não completam são pulados e a próxima
   posição da ordem é usada; não há cota por macrocategoria nem prioridade por split ou
   dificuldade. Para cada problema, o motor executa o código correto (`AC_ref`, o primeiro do dataset) sobre **toda** a suíte oficial e
   depois as submissões incorretas candidatas, até reunir exatamente 100 falhas de resposta errada
   (WA), cada uma confirmada por duas execuções. O comando roda o `selfcheck` antes de tudo e **aborta**
   se ele falhar. Faça primeiro um **piloto** com 10 problemas, para medir quantas candidatas viram WA
   e quanto tempo leva, antes da execução completa (`--target` é a meta de problemas completos):

   ```bash
   docker compose run --rm sandbox python -m dataset validate --target 10
   ```

   O piloto de 2026-09-21 levou cerca de 21 min de relógio para 14 problemas processados, com 4
   processos. Depois, a execução completa (meta 200), que em 2026-09-21 levou **5 h 06 min** com 4
   processos (264 problemas processados, mediana de 83 s por problema completo):

   ```bash
   docker compose run --rm sandbox python -m dataset validate
   ```

   Pode apertar Ctrl+C e repetir o mesmo comando: os problemas já encerrados são pulados e o que
   estava em andamento é refeito do zero. Durante a execução aparece uma linha por problema, como
   `1101_A: complete (AC AC; 213 candidates: ce=3 wa=100 tle=2...; 41.2 s)`, e no fim
   `included N of 200 (deficit D)`. Cada problema termina em um destes três estados, gravados em
   `data/work/problems/<problem_id>/`:

   | Estado | O que significa | O que fica na pasta |
   |---|---|---|
   | `complete` | o `AC_ref` passou em toda a suíte e há exatamente 100 WA validados | `enunciado.md`, `AC_ref.cpp`, `WA_1.cpp` a `WA_100.cpp`, `testes.json`, `metadata.json`, `validacao.json` |
   | `pending_triage` | o `AC_ref` **falhou no motor**; o problema é interrompido na hora, sem tentar outra solução e sem tolerância, **não conta para a meta** e a inspeção é adiada | só `validacao.json` (com o motivo e a saída divergente) e `AC_candidate.cpp` |
   | `discarded` | menos de 100 WA validáveis (por exemplo, poucas submissões incorretas distintas) | só `validacao.json` |

   **Problemas em `pending_triage` não são inspecionados agora** (decisão D17): ficam registrados,
   fora da amostra, e só passam a exigir **inspeção individual** de quem gera o dataset se a meta de
   200 **não** for atingida com os demais problemas do pool (a causa costuma ser um verificador
   especial que escapou do filtro, um gabarito do dataset com formatação diferente ou testes fora das
   restrições do enunciado; ver a metodologia, seção 1.7). Para tentar de novo um problema depois de
   resolvê-lo, apague a pasta dele em `data/work/problems/` e rode `validate` de novo.
   Códigos de saída: `0` se a meta foi atingida (problemas em triagem **não** mudam o código), `1`
   se houve déficit, `2` uso incorreto, `3` falha de infraestrutura (o problema em andamento fica em
   `data/work/building/`, é refeito na próxima execução e nunca vira veredito).

   **Conferir o piloto**: rode `docker compose run --rm app python -m dataset report` e leia, em
   `data/work/reports/extraction_report.md`, a seção "Falhas de AC por causa". Se mais de 10% dos ACs
   testados forem reprovados por divergência só de formatação ou por tempo excedido, a regra
   correspondente volta a ser proposta e a execução completa **não segue** (decisão D13, metodologia
   1.4). O arquivo `data/work/reports/validation_log.jsonl` traz uma linha por problema, com as
   contagens de candidatas por resultado (`wa`, `ce`, `tle`, `mle`, `re`, `ac`, `unstable`) e o tempo.

7. **Auditar (`audit`).** Reexecuta o motor sobre os problemas `complete` e confere com o
   `validacao.json`: o `AC_ref` primeiro; se ele deixar de passar, aquele problema é interrompido e
   vira `pending_triage` (etapa `audit`), sem que nenhuma WA seja avaliada:

   ```bash
   docker compose run --rm sandbox python -m dataset audit
   ```

   **Uma WA cujo veredito ou teste decisivo mudou é reparada, não só relatada** (decisão D18,
   2026-09-22): é substituída pelo próximo candidato não tentado da mesma ordem determinística que
   gerou o problema, agora exigindo uma confirmação mais forte (4 execuções concordantes, em vez
   das 2 da seleção original). O número de WA continua exatamente 100, na mesma numeração, e
   nenhum outro arquivo do problema muda. Por quê: a auditoria da execução completa achou WA cujo
   resultado dependia de comportamento indefinido do código (acesso fora dos limites de um vetor,
   variável não inicializada) ou de tempo de execução bem no limiar do limite — não da entrada —,
   o que os tornava um gabarito ruim para as métricas; os detalhes e a investigação (incluindo por
   que desligar o ASLR do kernel não foi viável, bloqueado pelo seccomp padrão do Docker) estão na
   metodologia, seção 1.7. A linha impressa por problema muda conforme o caso:

   | Linha | O que significa |
   |---|---|
   | `<id>: ok (AC_ref and 100 WA as recorded)` | nada divergiu |
   | `<id>: N WA candidate(s) repaired (decision D18): WA_5.cpp, ...` | reparado sozinho; não precisa de nada seu |
   | `<id>: could not be repaired (...); needs the authors' attention` | os candidatos não tentados se esgotaram sem um substituto confirmado; **este caso exige decisão sua** |
   | `<id>: audit FAILED, AC_ref is now ...; pending_triage` | o código correto deixou de passar; o problema sai da amostra |

   Código `0` se nada ficou sem solução (um reparo bem-sucedido não conta como divergência), `1`
   se algum problema não pôde ser reparado ou teve o `AC_ref` reprovado.

### O que são `audit` e `report`, para que servem e quando rodar cada um

| | `audit` | `report` |
|---|---|---|
| **O que faz** | reexecuta no motor o código correto e as 100 WA de cada problema completo e compara com o registrado | lê os arquivos já gravados e escreve o resumo legível (Markdown e JSON) |
| **Executa código C++?** | sim (serviço `sandbox`) | não (serviço `app`) |
| **Duração** | horas, como a validação (extrapolação: 4 a 5 h) | segundos |
| **Quando** | **uma vez**, depois de o `validate` terminar com `deficit 0` e **antes** de `package` | **não precisa rodar à mão**: `validate` e `audit` já o regeram ao terminar |
| **Obrigatório agora?** | sim, é a conferência antes de gerar o zip | não |

**`audit`: a segunda conferência dos problemas já validados.** Para cada problema `complete` em
`data/work/problems/`, ele lê os arquivos que estão na pasta (os mesmos que irão para o zip:
`AC_ref.cpp`, `WA_1.cpp` a `WA_100.cpp` e `testes.json`) e os executa **de novo** no motor: o
`AC_ref` sobre toda a suíte oficial e depois cada uma das 100 WA. Compara com o que o
`validacao.json` registrou: o `AC_ref` tem de continuar dando `AC`, e cada WA tem de continuar dando
`WA` no mesmo teste decisivo. Ele existe porque, no `validate`, cada código é executado uma vez para
decidir (as WA, duas), com 4 processos disputando a CPU. O `audit` é uma **segunda passagem
independente, sobre os arquivos gravados**: pega, por exemplo, um código cujo tempo estava perto do
limite e passou por sorte, e qualquer diferença entre o que foi decidido e o que foi gravado. É o que
sustenta a promessa de que todo código que entra no dataset passou pelo motor com o mesmo veredito
mais de uma vez (spec, FR-015a).

- *Se o `AC_ref` de um problema falhar na auditoria*: ele vira `pending_triage` (etapa `audit`) e sai
  da amostra, que passa a ter 199. Rode `validate` de novo: ele retoma a ordem do pool e completa o
  que falta; depois audite só os novos com `audit --problem <id>` (repetível).
- *Se uma WA divergir*: é apenas **reportada** (o comando termina com código `1` e lista quais);
  o problema continua completo e os autores decidem o que fazer.
- Só quem **gera** o dataset roda o `audit`: ele lê `data/work/`, que só existe na máquina de quem
  gerou. Quem recebe o zip usa `verify` (integridade), não `audit`. Não precisa ser repetido, a menos
  que algum problema seja refeito ou o motor/imagem mude.

**`report`: o resumo legível do estado.** Não executa código nem baixa nada: lê `pool.json`, todos os
`validacao.json` e `selfcheck.json` e escreve `data/work/reports/extraction_report.md` e `.json`
(funil de elegibilidade, distribuição por macrocategoria do pool e da amostra, descartes, falhas de
AC por causa, triagem adiada, déficit, alertas e o resultado do `selfcheck`). É o documento com os
números que vão para o texto do TCC; o `package` copia o `.json` para
`manifests/extraction_report.json` (versionado). Como `validate` e `audit` o regeram sozinhos ao
terminar, rodar `report` à mão só serve para **atualizar o resumo sem executar nada** (por exemplo,
depois de apagar a pasta de um problema) ou para acompanhar o andamento de outra janela de terminal
durante uma execução longa. **Depois do `validate` não é preciso rodá-lo.**

### Roteiro da execução completa (quem gera o dataset; tarefa T072)

Esta é a única etapa longa do módulo (várias horas) e **é executada por você, no seu computador**,
não por uma ferramenta automática. Este roteiro reúne tudo o que é preciso: leia-o inteiro antes de
começar.

**O que vai acontecer.** O `validate` percorre o pool na ordem gravada e valida cada problema no
motor até reunir 200 problemas completos. Na execução de 2026-09-21 foram 264 problemas processados
em **5 h 06 min com 4 processos**. Depois vem a auditoria (`audit`), que reexecuta os 200 problemas
e leva um tempo da mesma ordem (extrapolação: 4 a 5 horas); o relatório (`report`) é gerado sozinho
ao fim de cada um. Pode fazer a validação hoje e a auditoria em outro momento.

**Antes de começar (uma vez):**

1. Esteja na pasta do repositório, na versão já **commitada**. Confira que não há alteração pendente
   no código: `git status` não deve listar nada em `src/`, `scripts/`, `Dockerfile`,
   `docker-compose.yml`, `pyproject.toml` nem `uv.lock`. Anote o hash: `git rev-parse --short=7 HEAD`
   (os comandos são carimbados na tabela "Comandos verificados" com esse hash).
2. Deixe a imagem pronta: `docker compose build` (rápido se nada mudou).
3. Confirme que o motor está bem: `docker compose run --rm sandbox python -m dataset selfcheck`
   deve terminar com `selfcheck OK: 9/9 cases`. (O `validate` repete essa conferência sozinho.)
4. Espaço em disco: cada problema completo ocupa cerca de 0,5 MB em `data/work/problems/`
   (medido nos 14 do piloto), ou seja, em torno de 100 MB para 200; há folga de sobra.
5. O computador precisa **ficar ligado e sem suspender** durante horas. O `systemd-inhibit` do
   comando abaixo impede a suspensão enquanto ele roda. Em notebook, mantenha na tomada e não feche
   a tampa.
6. O computador ficará bem ocupado (4 processos compilando C++). Se quiser continuar usando a
   máquina, acrescente `--workers 2` ao comando: só o tempo aumenta, o **resultado é o mesmo** com
   qualquer número de processos.

**A validação (deixe o terminal aberto):**

```bash
systemd-inhibit --what=sleep:idle --why="validacao do dataset" \
  docker compose run --rm sandbox python -m dataset validate
```

- Aparece uma linha por problema (`1101_A: complete (...)`, `pending_triage`, `discarded`) e, no fim,
  `included N of 200 (deficit D)`.
- **Se o terminal fechar, o computador reiniciar ou você apertar Ctrl+C**, rode o **mesmo comando** de
  novo: os problemas já encerrados são pulados e só o que estava em andamento é refeito. Não apague
  `data/work/`.
- Problemas em `pending_triage` são esperados (cerca de 1 em cada 5 no piloto). **Não faça nada com
  eles**: por decisão dos autores (D17), a triagem manual é adiada e só se faz se a meta não for
  atingida.
- **Sucesso**: a última linha é `included 200 of 200 (deficit 0)` e o código de saída é `0`
  (confira com `echo $?` logo depois).
- **Se terminar com `deficit` maior que zero** (código `1`), **pare aí** e avise: a meta não foi
  atingida com os demais problemas do pool e os casos em `pending_triage` passam a exigir inspeção
  individual. Nada é relaxado automaticamente.

**Depois da validação** (pode ser em outro momento; veja "O que são `audit` e `report`" acima):

```bash
systemd-inhibit --what=sleep:idle --why="auditoria do dataset" \
  docker compose run --rm sandbox python -m dataset audit
```

O `audit` imprime `<id>: ok (...)` por problema e termina com código `0` se nada divergiu. O
`report` **não precisa ser rodado**: o `validate` e o `audit` já regeram
`data/work/reports/extraction_report.md` ao terminar.

**O que guardar e enviar para a documentação ser atualizada** (tarefa T072): as últimas linhas do
terminal de cada comando (validação, auditoria, relatório), o conteúdo de
`data/work/reports/extraction_report.md` e o hash de `git rev-parse --short=7 HEAD`. Com isso, os
números reais (distribuição da amostra por macrocategoria e por split, funil, descartes,
triagens, tempo total, se o alerta de menos de 30 por categoria disparou) entram na metodologia, na
spec e no plano, e os comandos são carimbados.

### Se algo der errado

| O que aparece | O que significa | O que fazer |
|---|---|---|
| `infrastructure failure: ...` (código `3`) | falha de rede ou de disco ao ler o dataset | rode o mesmo comando de novo; a extração retoma do último trecho concluído |
| `interrupted; it is safe to run the command again` (código `130`) | você apertou Ctrl+C | rode o mesmo comando de novo |
| `error: no pool found; run ...` (código `1`) | você rodou `report` antes de `extract` | rode `extract` primeiro |
| `error: --splits must list ...` (código `2`) | valor inválido em `--splits` | use `train`, `valid` e/ou `test`, separados por vírgula |
| `selfcheck` com `FAIL` (código `1`) ou `infrastructure failure` (código `3`) | motor com veredito errado, ou rodado fora do serviço `sandbox` | veja a tabela de erros do [`sandbox`](../sandbox/README.md) |
| `selfcheck FAILED: the engine is not trustworthy, nothing was validated` (código `1`) | o `validate` recusou começar porque o motor falhou na conferência | rode `selfcheck` e siga a tabela do `sandbox`; nada foi validado |
| `error: <id> is not in the pool` (código `2`) | `--problem` com um problema que não está no pool | confira o identificador (`<ContestID>_<Index>`) em `data/work/staging/pool.json` |
| `<id>: already closed (...) , skipped` | o problema já foi encerrado e não é refeito | apague `data/work/problems/<id>/` se quiser reprocessá-lo |
| `N problem(s) set aside in pending_triage and not inspected` | o `AC_ref` de N problemas falhou no motor, mas a meta foi atingida sem eles (D17) | nada: a triagem é adiada e não é necessária |
| `N problem(s) in pending_triage need individual inspection now` (código `1`) | a meta não foi atingida com o resto do pool | inspecione cada um em `data/work/problems/<id>/validacao.json` (campo `triage`) e decida com os autores; nada é relaxado sozinho |
| `PermissionError` ao gravar em `data/` | `data/` pertence a `root` (o passo 3 do guia foi pulado) | `sudo chown -R "$(id -u):$(id -g)" data` e rode de novo |
| quer recomeçar do zero | — | `rm -rf data/work` e rode o passo 2 (só enquanto a validação não existe: depois dela essa pasta guarda os problemas validados) |

### Opções de `validate` e `audit`

| Comando | Opção | Padrão | Efeito |
|---|---|---|---|
| `validate` | `--target N` | `200` | meta de problemas `complete`; a execução para ao atingi-la |
| `validate` | `--workers N` | metade das CPUs (mínimo 1) | processos em paralelo por problema; **não altera o resultado** (os resultados são consumidos na ordem das candidatas) |
| `validate` | `--problem ID` | — | valida só este problema e ignora a meta; útil para triagem |
| `audit` | `--problem ID` (repetível) | todos os `complete` | escopo da auditoria |
| `audit` | `--workers N` | metade das CPUs | processos em paralelo |

### Opções de `extract`

| Opção | Padrão | Efeito |
|---|---|---|
| `--seed INT` | `42` | seed da ordem de processamento; fica gravada no pool (não mude sem combinar: muda a seleção) |
| `--splits LIST` | `train,valid,test` | splits lidos, nesta ordem (a primeira ocorrência de um problema vence) |
| `--limit-rows N` | sem limite | limita as linhas lidas por split (só para testes rápidos) |

Códigos de saída: `0` sucesso, `1` falha de dados (por exemplo, `report` sem pool), `2` uso
incorreto, `3` falha de infraestrutura (rede; repita o comando para retomar), `130` interrompido.
Os subcomandos de empacotamento e verificação serão documentados aqui, no mesmo formato de passo a
passo, quando existirem.

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| Dataset `deepmind/code_contests` | streaming Parquet pela biblioteca `datasets`, na revisão `802411c3010cb00d1b05bad57ca77365a3c699d6` | Hugging Face (público; licença CC-BY-4.0) |
| `HF_TOKEN` (opcional) | variável de ambiente, lida do `.env` | só aumenta o limite de requisições |
| Opções de linha de comando | `--seed`, `--splits`, `--limit-rows` (`extract`); `--target`, `--workers`, `--problem` (`validate`, `audit`) | quem executa |
| Pool e problemas brutos | `data/work/staging/pool.json` e `raw/*.json.gz` | a fase `extract` (para `validate`); `audit` lê os problemas já validados de `data/work/problems/` |

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
| `data/work/reports/extraction_report.json` e `.md` | JSON e Markdown, modelo `ExtractionReport` (com `ac_tested` e `triage_by_cause`) | leitura humana e citação no trabalho escrito |
| `data/work/problems/<problem_id>/` | pasta por problema encerrado: `complete`, `pending_triage` ou `discarded` (conteúdo na tabela do passo 6); modelos `Metadata`, `Testes` e `Validacao` | será empacotada por `package` (só os `complete`) |
| `data/work/building/<problem_id>/` | problema em construção; é apagado e refeito se a execução for interrompida | só o `validate` |
| `data/work/reports/selfcheck.json` | resultado do `selfcheck` que o `validate` rodou | campo `engine_selfcheck` do relatório |
| `data/work/reports/validation_log.jsonl` | uma linha JSON por problema: estado, contagens de candidatas por resultado e tempo | leitura humana (piloto) |

## (e) Dependências e pré-requisitos

- Python 3.11.16, `datasets` 5.0.1 e `pydantic` 2.x, fixados no `uv.lock`.
- Serviço `app` do Docker Compose (com rede) para `extract` e `report`; serviço `sandbox` (sem rede,
  com as capabilities do motor) para `selfcheck`, `validate` e `audit`. O ambiente é construído com
  `docker compose build`.
- `.env` com `HOST_UID` e `HOST_GID` do seu usuário (saídas de `id -u` e `id -g`); `HF_TOKEN` é opcional. Passo 2 do guia da raiz.
- Diretório `data/` criado por você (`mkdir -p data`) antes do primeiro `docker compose run`: o
  Git não o versiona, e, se ele não existir, o Docker o cria como root e o serviço `app` (que roda
  com o seu usuário) não consegue gravar nele. Passo 3 do guia da raiz; se já aconteceu, o
  `chown` da tabela "Se algo der errado", na seção (b), resolve.
- Nenhum módulo anterior precisa ter rodado.

## (f) Limitações conhecidas

- Problemas que leem e escrevem por arquivo (`input.txt` e `output.txt`) são excluídos, porque o
  motor injeta a entrada por `stdin`: 9 problemas medidos em 2026-09-19 (metodologia, seção 1.2).
- O pool é de 1.234 problemas (extração real de 2026-09-20). O número de 1.279 que aparecia na
  medição de 2026-09-19 não incluía a checagem de soluções em C++ nem a de 100 incorretas
  (metodologia, seção 1.2). Só 28 deles vêm de `valid`/`test`.
- Em `valid` e `test` a mediana é de 101 submissões incorretas em C++ por problema (medido em
  2026-09-20), então poucos vão alcançar 100 falhas validadas; no pool inteiro, 167 problemas têm
  menos de 150 incorretas brutas (metodologia, seção 1.7).
- O streaming lê todas as colunas de cada linha (não há projeção de colunas): a extração completa
  levou cerca de 23 minutos em 2026-09-20; o volume de rede não foi medido.
- **A validação completa foi executada** (2026-09-21): 200 problemas completos de 264 processados
  (as posições 0 a 263 do pool), 21 descartados por WA insuficientes e 43 em `pending_triage`; só
  5 dos 28 problemas de `valid`/`test` foram processados (a amostra tem 198 do `train` e 2 do
  `test`). **A auditoria (`audit`) ainda não rodou.** Se a meta de 200 problemas com exatamente
  100 WA não tivesse fechado, nada seria relaxado automaticamente.
- **Cerca de 1 em cada 6 problemas processados foi para `pending_triage`** (43 de 264, 16,3%):
  verificador especial (várias respostas válidas), gabarito do dataset com formatação diferente e
  testes gerados fora das restrições do enunciado. Eles são interrompidos e registrados (decisão
  D8), mas a inspeção manual é adiada e só ocorre se a meta de 200 falhar (decisão D17), o que não
  aconteceu; os números e as causas estão na metodologia, seção 1.7.
- O `AC_ref` é executado no processo principal e as candidatas a WA em paralelo; o resultado não
  depende do número de processos, mas o tempo sim.
- Um programa pode gravar arquivos no diretório temporário do seu slot; eles persistem entre os testes
  de uma mesma suíte (e são apagados a cada nova compilação).
- O empacotamento e a verificação ainda não existem: sem `package`, não há `data/dataset.zip`.

## Referências

- Contratos: [cli.md](../../specs/001-dataset-extraction/contracts/cli.md) e
  [data-model.md](../../specs/001-dataset-extraction/data-model.md)
- Testes: `tests/dataset/` (`docker compose run --rm sandbox pytest tests/dataset`)

## Comandos verificados

| Comando | Verificado em | Revisão | Tarefa |
|---|---|---|---|
| `extract` | 2026-09-20 | 7440706 | T035 |
| `report` | 2026-09-20 | 71747a1 | T035 |
| `selfcheck` | 2026-09-21 | 5121759 | T050 |
| `validate` | 2026-09-21 | ee3a422 | T072 |
| `audit` | pendente | — | — |
