# Módulo `mutation` (geração de mutantes)

> **Status**: em implementação · **Feature**:
> `specs/002-mutant-generation/` · **Metodologia**: `docs/metodologia-referencia.md`, seção 2

## (a) Propósito

Gera até 100 mutantes válidos e distintos por problema a partir do `AC_ref.cpp` do dataset, para que a etapa de avaliação possa medir o Escore de Mutação das suítes de teste geradas pelas IAs.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
(baixar o projeto, criar o `.env`, criar `data/`, construir a imagem e conferir com o `pytest`) e
tenha o dataset descompactado em `data/dataset/` (`unzip data/dataset.zip -d data/`, ver o
[README do módulo `dataset`](../dataset/README.md)). O comando de geração roda no serviço
**`sandbox`** do Docker Compose, que **não tem internet** de propósito e é o único autorizado a
compilar e executar código C++ de terceiros: cada mutante é compilado e executado de verdade.

### O que este módulo faz, na prática

Um **mutante** é uma cópia do `AC_ref.cpp` (a solução correta de referência do problema) com uma
única alteração sintática que introduz um defeito artificial — por exemplo, trocar `i < n` por
`i <= n` (só quando isso não basta para chegar a 100, o módulo passa a combinar duas e, depois,
três alterações no mesmo mutante, como descrito em (f)). O módulo lê o código com um analisador sintático real (`tree-sitter`), não com busca de
texto, e por isso nunca altera o conteúdo de uma *string*, de um caractere entre aspas ou de um
comentário, nem confunde o `>>` que fecha `vector<vector<int>>` com o operador `>>`. Também não
mexe na leitura e na escrita (`cin >> a`, `cout << x`): trocar o operador ou pôr `abs`/`++` na frente
de `cin` ou da variável lida só produz código que não compila, e um mutante que apenas deixa de ler
a entrada é pouco informativo.

As alterações são as cinco de Offutt et al. (1996): **ROR** (troca um operador relacional pelos
outros cinco), **AOR** (o mesmo para `+ - * / %`, e `<<` com `>>`), **LCR** (`&&` com `||`),
**ABS** (força um operando a `0`, `+abs(x)` ou `-abs(x)`) e **UOI** (coloca `-`, `!`, `++` ou `--`
na frente de um operando, ou troca um `-`/`!`/`++`/`--` que já existe). Cada candidato passa por
uma validação com o mesmo motor de execução do restante do projeto: é **descartado** se for texto
repetido, se não compilar, se estourar tempo ou memória, se der erro de execução ou se responder
certo em **todos** os testes oficiais (mutante equivalente); e só é **aceito** se responder errado
(`WA`) em seis execuções seguidas, sempre com o mesmo teste decisivo. Os limites de tempo e de
memória são lidos do `metadata.json` de cada problema.

A ordem é sempre a mesma: os sítios de alteração são percorridos na ordem em que aparecem na
árvore sintática, e os 100 primeiros mutantes válidos são mantidos. O módulo **não usa nenhuma
aleatoriedade e não tem seed**: rodar duas vezes sobre o mesmo dataset dá os mesmos candidatos na
mesma ordem (o único fator externo é o veredito do motor, por isso a confirmação em seis execuções).

### Qual é o seu cenário?

| Você quer... | Vá para |
|---|---|
| gerar os mutantes de um ou de alguns problemas (desenvolvimento, depuração) | [Cenário A](#cenário-a-gerar-os-mutantes) |
| ser quem faz a **execução final** que sustenta os números do TCC (gerar tudo, empacotar, versionar) | [Cenário B](#cenário-b-execução-final-gerar-tudo-e-empacotar) |
| só **usar** os mutantes que o outro autor já gerou e versionou (não gera nada) | [Cenário C](#cenário-c-só-receber-o-pacote-versionado) |
| retomar uma execução que foi interrompida | [Interromper e retomar](#interromper-e-retomar) |

Em todos os cenários os mutantes que os módulos seguintes leem ficam no **mesmo caminho**,
`data/mutants/problems/<problema>/Mutant_<n>.cpp`, tenha você gerado ou só recebido o pacote.

### Cenário A: gerar os mutantes

```bash
docker compose run --rm sandbox python -m mutation generate --problem 189_C
```

Para todos os problemas, em paralelo (ajuste `--workers` ao seu computador; cada trabalhador ocupa
um núcleo o tempo todo compilando):

```bash
docker compose run --rm sandbox python -m mutation generate --workers 4
```

`--problem` pode ser repetido para vários problemas; sem ele, todos os problemas do dataset são
processados, na ordem das pastas, **vários ao mesmo tempo** (`--workers N`, padrão: metade das CPUs
do computador; cada problema roda num compartimento próprio do motor de execução, e o número de
trabalhadores só muda o tempo, nunca os mutantes gerados). Como cada problema é uma tarefa
inteira, um único `--problem` não fica mais rápido com mais trabalhadores. O comando:

1. confere `data/dataset` contra `manifests/dataset.manifest.json` e **para com código `1`** se
   algum arquivo divergir (assim os mutantes nunca são gerados sobre um dataset diferente do
   versionado);
2. processa cada problema e, ao terminar, imprime uma linha como
   `[k/N] <problema>: 100 mutants (by order: {1: 100}); discarded: {<motivo>: <quantos>, ...}; <N> s`
   (por ordem de mutação, quantos candidatos foram descartados e por quê, e o tempo gasto);
3. grava o resultado em `data/mutants/problems/<problema>/`: `Mutant_1.cpp` a `Mutant_100.cpp`,
   na ordem em que foram aceitos, e `generation.json` (como cada um foi obtido; uso interno);
4. no fim, resume: `done: N generated, N skipped, N excluded` (e `, N damaged` se houver).

**Como conferir:** `echo $?` deve mostrar `0`; `ls data/mutants/problems/189_C | wc -l` deve dar
`101` (100 mutantes mais o `generation.json`); `diff data/dataset/problems/189_C/AC_ref.cpp
data/mutants/problems/189_C/Mutant_1.cpp` mostra a alteração de uma única posição
(duas ou três, se o `generation.json` do problema indicar mutantes de ordem superior).

**Só um `generate` por vez:** ele toma uma trava sobre `data/mutants/`; se você abrir um segundo
terminal e rodar de novo, o segundo se recusa (`another ... generate is already running`, código
`1`) em vez de disputar os mesmos arquivos. A trava some sozinha quando o primeiro termina, de
qualquer maneira (Ctrl+C, `kill -9`, queda de energia).

**Relatório a qualquer momento:** para ver o funil de descartes, a distribuição por ordem e por
operador e os alertas do que já foi gerado (mesmo de uma execução parcial), rode:

```bash
docker compose run --rm app python -m mutation report
```

Ele confere o dataset, lê o `generation.json` de cada problema e grava
`manifests/mutation_report.json` (sem data nem hora: rodar de novo sobre o mesmo estado dá o mesmo
arquivo).

### Cenário B: execução final (gerar tudo e empacotar)

Só faz sentido **uma vez**, na execução que vai sustentar os números do TCC (Constitution,
Princípio II, emenda 1.6.0); as rodadas de desenvolvimento não são versionadas.

```bash
docker compose run --rm sandbox python -m mutation generate --workers 4
docker compose run --rm app python -m mutation package
docker compose run --rm app python -m mutation verify
git status --short data/mutants.zip manifests/mutants.manifest.json manifests/mutation_report.json
```

`package` **se recusa** (código `1`, sem gravar nada) se: o dataset divergir do manifesto; a revisão
for malformada; algum problema estiver pela metade em `data/mutants/building/` (rode `generate` de
novo); algum problema já fechado tiver perdido ou tiver tido um mutante alterado (`DAMAGED`); ou
faltar gerar algum problema do dataset (`--allow-partial` empacota mesmo assim, só para teste, nunca
para o pacote que será versionado). Ele grava, nessa ordem, `data/mutants.zip` (só os
`Mutant_<n>.cpp` dos problemas completos; um problema excluído não tem pasta), o manifesto
`manifests/mutants.manifest.json` (SHA-256 de cada arquivo) e o relatório
`manifests/mutation_report.json`, e imprime `packaged N problems (N excluded): ...`. Rodar de novo
dá exatamente os mesmos bytes. `verify` recalcula os hashes do zip e de cada arquivo dentro dele e
imprime `OK` (código `0`) ou `changed:`/`missing:`/`extra:` seguidos de `FAIL` (código `1`).

**Quem commita o quê** é sempre decisão sua: o comando só deixa os três arquivos prontos
(`git status` os mostra como novos). O zip deve ficar abaixo de 100 MB (o `package` avisa acima de
95 MB; o GitHub recusa acima de 100 MB).

### Cenário C: só receber o pacote versionado

Depois de um `git pull` que trouxe `data/mutants.zip` e os manifestos, **não rode `generate`**:

```bash
rm -rf data/mutants
unzip data/mutants.zip -d data/
docker compose run --rm app python -m mutation verify --extracted data/mutants
```

O `rm` apaga qualquer geração local de desenvolvimento (que pode ter mutantes diferentes: o motor
tem margem de instabilidade, então regenerar não garante os mesmos arquivos). O `unzip` recria
`data/mutants/problems/<problema>/`, o mesmo caminho do Cenário A. `verify --extracted` confere a
pasta descompactada arquivo a arquivo (só os `Mutant_<n>.cpp` contam; `generation.json` e a pasta
`building/` de uma geração local não são "extras") e deve terminar em `OK`. Se um `generate` for
rodado por engano sobre essa pasta, ele **pula** os problemas que já existem (`already generated,
skipped`) e nunca os sobrescreve.

### Interromper e retomar

Você pode interromper a geração por qualquer motivo — Ctrl+C, `docker stop`, fechar o terminal,
`kill -9`, queda de energia — e rodar **o mesmo comando** de novo:

- **Nada do que já estava pronto se perde nem é refeito.** Um problema só aparece em
  `data/mutants/problems/` inteiro e completo (ele é montado em `data/mutants/building/` e passa de
  uma vez, com uma única renomeação); ao retomar, os já concluídos são pulados
  (`already generated, skipped`) sem nem serem tocados.
- **O que estava em andamento é refeito do zero**, e só isso: um problema leva alguns minutos
  (`generate` grava um problema apenas quando ele termina; com `--workers N`, até `2N` problemas
  podem estar em andamento e serão refeitos). Sobras da execução interrompida (pastas
  pela metade em `building/`, arquivos temporários) são descartadas no início da próxima.
- **Ctrl+C e `docker stop` encerram na hora** (código `130`): os trabalhadores e os compiladores
  em andamento são finalizados sem esperar o problema terminar.
- O resultado depois de retomar é **exatamente** o de uma execução que nunca foi interrompida
  (mesmos arquivos, mesmos SHA-256), porque a ordem dos candidatos não depende de quando nem de
  quantas vezes você parou.
- Se um problema já concluído perdeu ou teve um mutante editado depois (por engano, ou por disco),
  o `generate` não o pula em silêncio: imprime `DAMAGED (missing: ...; changed: ...)`, termina
  com código `1` e o `package` também se recusa. Para regerar só esse problema, apague a pasta dele
  (`rm -r data/mutants/problems/<problema>`) e rode de novo.

### Se algo der errado

| O que aparece | O que significa | O que fazer |
|---|---|---|
| `error: data/dataset does not match manifests/dataset.manifest.json:` seguido de `changed:`/`missing:`/`extra:` (código `1`) | `data/dataset` não é o dataset versionado | `unzip data/dataset.zip -d data/` (sobrescreve com a versão correta) e rode de novo |
| `error: not in data/dataset: <id>` (código `2`) | o `--problem` não existe no dataset | confira o nome da pasta em `data/dataset/problems/` |
| `error: another ... generate is already running over data/mutants/` (código `1`) | outro `generate` está rodando sobre os mesmos dados | espere ele terminar (ou interrompa-o); não é preciso apagar nada |
| `<id>: DAMAGED (missing: ...)` (código `1` no fim) | um problema já concluído perdeu ou teve alterado um `Mutant_<n>.cpp` | `rm -r data/mutants/problems/<id>` e rode `generate` de novo |
| `ALERT: <id> reached only N of 100 mutants (highest order tried: K); the problem is left out of the mutation score` (o comando ainda termina com código `0`) | nem uma alteração por vez, nem pares, nem trios de alterações chegaram a 100 mutantes válidos nesse problema, então ele é **excluído** do conjunto de mutantes | nenhum `Mutant_<n>.cpp` é gravado para ele (só o `generation.json`, com `status` `excluded`); os demais seguem normalmente e o problema entra no relatório como alerta. Não é um erro a corrigir: é o resultado esperado para um código com pouquíssimos pontos de alteração |
| `error: N problem(s) half-written in data/mutants/building ...` (código `1`, no `package`) | uma geração foi interrompida e não foi terminada | rode `generate` de novo e depois `package` |
| `error: K of N problems were not generated (...)` (código `1`, no `package`) | ainda faltam problemas do dataset | rode `generate` até terminar (só para teste: `--allow-partial`) |
| `verify` termina em `FAIL` com `changed:`/`missing:`/`extra:` | o zip, ou a pasta descompactada, não é o que o manifesto descreve | veja o arquivo apontado; para a pasta descompactada, refaça `rm -rf data/mutants` e `unzip` |
| `infrastructure failure: ...` (código `3`) | o próprio ambiente falhou (por exemplo, o compilador ou a pasta temporária do `sandbox`) | veja a mensagem, corrija (em geral `docker compose build`) e rode de novo; o comando retoma |

### Opções

| Comando | Opção | Padrão | Efeito |
|---|---|---|---|
| `generate` | `--problem ID` | todos os problemas | processa só esse problema (pode ser repetida) |
| `generate` | `--workers N` | metade das CPUs | quantos problemas são processados ao mesmo tempo; `1` roda tudo em série, no próprio processo; o resultado não muda |
| `package` | `--allow-partial` | desligado | empacota mesmo com problemas ainda não gerados (só para teste) |
| `verify` | `--zip`, `--manifest` | `data/mutants.zip`, `manifests/mutants.manifest.json` | o que conferir |
| `verify` | `--extracted DIR` | (não confere pasta) | confere também a pasta descompactada, tipicamente `data/mutants` |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/AC_ref.cpp` | C++ | dataset descompactado (módulo [`dataset`](../dataset/README.md)) |
| `data/dataset/problems/<id>/testes.json` | JSON (`schema_version` 1) | idem: suíte oficial, na ordem de execução |
| `data/dataset/problems/<id>/metadata.json` | JSON (`schema_version` 1) | idem: fornece os limites de tempo e de memória |
| `manifests/dataset.manifest.json` | JSON | versionado no repositório; usado para conferir o dataset antes de começar (`generate`, `report`, `package`) |
| `data/mutants/problems/<id>/generation.json` | JSON (`schema_version` 1) | escrito pelo próprio `generate`; lido por `report`, `package` e pela retomada |
| `data/mutants.zip` e `manifests/mutants.manifest.json` | zip e JSON | versionados (só depois da execução final); lidos por `verify` |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| `Mutant_<n>.cpp` (n de 1 a 100) | C++: o `AC_ref.cpp` com 1 posição alterada (ou 2 ou 3, na ordem superior), idêntico byte a byte fora delas | `data/mutants/problems/<id>/` (pasta ignorada pelo Git, nunca versionada); é o caminho de onde os módulos seguintes vão ler os mutantes |
| `generation.json` | JSON (`schema_version` 1): por mutante, o operador e a variante usados; por problema, quantos candidatos foram descartados e por quê | mesma pasta; alimenta o relatório e marca o problema como concluído; **não** entra no zip |
| `data/mutants.zip` | zip determinístico: só os `Mutant_<n>.cpp` dos problemas completos, sob `mutants/problems/<id>/` | `data/`; **versionado** só na execução final (`package`) |
| `manifests/mutants.manifest.json` | JSON (`schema_version` 1): SHA-256 e tamanho do zip e de cada arquivo dentro dele | `manifests/`, versionado (`package`); lido por `verify` |
| `manifests/mutation_report.json` | JSON (`schema_version` 1): contagem de problemas (só primeira ordem, com ordem superior, excluídos), funil de descartes por motivo, mutantes por ordem e por operador, alertas de exclusão, revisão do código e hash do manifesto do dataset | `manifests/`, versionado (`report`, e `package` o refaz) |

## (e) Dependências e pré-requisitos

- Python 3.11, `tree-sitter` 0.26 e `tree-sitter-cpp` 0.23 (fixadas em `uv.lock`), GCC 13.2.0 —
  tudo já dentro da imagem do projeto (`docker compose build`).
- Serviço `sandbox` do Docker Compose (sem rede), com o motor de execução do módulo
  [`sandbox`](../sandbox/README.md), usado sem alteração, para `generate`; serviço `app` para
  `report`, `package` e `verify` (não compilam nem executam C++).
- Dataset já descompactado em `data/dataset/` e íntegro (o próprio comando confere).
- Nenhuma variável de ambiente nem segredo: o módulo não chama nenhuma IA.

## (f) Limitações conhecidas

- **O pacote só vale para a execução final**: `data/mutants/` de uma rodada de desenvolvimento não é
  versionado nem vale como resultado do experimento, porque o motor tem margem de instabilidade e
  regenerar não garante os mesmos arquivos (por isso o pacote da execução final é versionado). O
  `generate` nunca sobrescreve uma pasta de problema que já exista.
- **Recuperação é por problema**: o que estava em andamento no momento da interrupção é refeito
  inteiro (alguns minutos por problema); não há ponto de retomada dentro de um problema.
- **Resultado real (200 problemas, 2026-09-25):** 113 problemas (56,5%) fecham só com uma alteração
  por mutante, 87 (43,5%) precisaram de combinações e nenhum foi excluído; 15,3% dos 20.000 mutantes
  têm duas alterações e 9 (só no problema `981_B`) têm três.
- **Mutantes de ordem superior são menos naturais**: quando uma alteração por vez não alcança 100
  mutantes válidos, o módulo combina pares e depois trios de alterações já válidas, sempre na ordem
  de aparição no código (sem busca). Um mutante de duas ou três alterações tende a ser mais fácil
  de detectar do que o de uma. Medido em 2026-09-24 nos três problemas com menos pontos de alteração
  do dataset, todos fecharam 100 só com pares (76% a 83% dos mutantes de duas alterações), em 6 a 7
  minutos cada, e nenhum foi excluído; um problema que
  não chega a 100 nem assim é excluído (ver a tabela acima). Se o comando ficar muito tempo num
  problema desse tipo, é a busca de combinações; ele pode ser interrompido e retomado.
- **Custo de tempo**: cada candidato é compilado e executado de verdade, e só uma fração é
  aceita. Medido em 2026-09-24 no problema `189_C` (usa `bits/stdc++.h`): compilar leva cerca de
  1,8 s e gerar os 100 mutantes levou 795 s (13 min 16 s), avaliando 241 candidatos (141 descartados:
  64 não compilam, 48 equivalentes, 18 com erro de execução, 11 com tempo excedido). Depois do
  filtro descrito abaixo, 8 problemas completos (2026-09-24, computador de 4 núcleos e 8 threads)
  levaram 3.520 s em série e 1.700 s com `--workers 4`, cerca de 2 vezes mais rápido, com
  exatamente os mesmos mutantes. **A execução dos 200 problemas com `--workers 4` (2026-09-24/25)
  levou cerca de 7 h 26 min de relógio**, avaliou 34.355 candidatos e aceitou 20.000 (58%); o ganho
  depende do computador. O comando pode ser interrompido e retomado. O tempo impresso ao fim de
  cada problema, com mais de um trabalhador, **inclui a espera na fila** e não mede o tempo do
  problema; use o tempo total.
- **Ainda há candidatos que não compilam**: o analisador é sintático e não conhece tipos. As causas
  mais comuns (leitura e escrita com `cin`/`cout`, `++` em algo que não se atribui, `abs` de
  tamanho) já são evitadas e, em três problemas medidos em 2026-09-24, os erros de compilação
  caíram de 28–32% dos candidatos para 0%, 1% e 17% (4,5% nos 8 problemas gerados por completo); o resto (por exemplo, ABS ou UOI sobre uma
  variável `stringstream`, cujo tipo só um analisador de tipos revelaria) é descartado pela
  validação. Isso custa tempo, não corretude.
- **Mutantes equivalentes só são detectados pela suíte oficial**: um mutante que se comporta como o
  original em todos os testes oficiais é descartado, mesmo que seja diferente em alguma entrada que
  nenhum teste cobre.

## Referências

- Contratos: `specs/002-mutant-generation/contracts/`
- Testes: `tests/mutation/` (`docker compose run --rm sandbox pytest tests/mutation`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `report` | 2026-09-24 | 5c726d8+dirty |
| `package` | 2026-09-24 | 5c726d8+dirty |
| `verify` | 2026-09-24 | 5c726d8+dirty |
| `generate` | 2026-09-24 | 5c726d8+dirty |
