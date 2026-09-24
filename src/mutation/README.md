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

### Cenário: quero gerar os mutantes de um problema

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
   `100 mutants (by order: {1: 100}); discarded: {<motivo>: <quantos>, ...}; <N> s` (por ordem de
   mutação, quantos candidatos foram descartados e por quê, e o tempo gasto no problema);
3. grava o resultado em `data/mutants/problems/<problema>/`: `Mutant_1.cpp` a `Mutant_100.cpp`,
   na ordem em que foram aceitos, e `generation.json` (como cada um foi obtido; uso interno);
4. no fim, resume: `done: N generated, N skipped, N excluded`.

**Como conferir:** `echo $?` deve mostrar `0`; `ls data/mutants/problems/189_C | wc -l` deve dar
`101` (100 mutantes mais o `generation.json`); `diff data/dataset/problems/189_C/AC_ref.cpp
data/mutants/problems/189_C/Mutant_1.cpp` mostra a alteração de uma única posição
(duas ou três, se o `generation.json` do problema indicar mutantes de ordem superior).

**Interromper e retomar:** apertar Ctrl+C (ou `docker stop`) é seguro — o comando termina com
código `130`. Cada problema é montado numa pasta provisória (`data/mutants/building/`) e só passa
para `data/mutants/problems/` inteiro, de uma vez; ao rodar de novo, o que estava pela metade
recomeça do zero e os problemas já concluídos são pulados (`already generated, skipped`).

### Se algo der errado

| O que aparece | O que significa | O que fazer |
|---|---|---|
| `error: data/dataset does not match manifests/dataset.manifest.json:` seguido de `changed:`/`missing:`/`extra:` (código `1`) | `data/dataset` não é o dataset versionado | `unzip data/dataset.zip -d data/` (sobrescreve com a versão correta) e rode de novo |
| `error: not in data/dataset: <id>` (código `2`) | o `--problem` não existe no dataset | confira o nome da pasta em `data/dataset/problems/` |
| `ALERT: <id> reached only N of 100 mutants (highest order tried: K); the problem is left out of the mutation score` (o comando ainda termina com código `0`) | nem uma alteração por vez, nem pares, nem trios de alterações chegaram a 100 mutantes válidos nesse problema, então ele é **excluído** do conjunto de mutantes | nenhum `Mutant_<n>.cpp` é gravado para ele (só o `generation.json`, com `status` `excluded`); os demais seguem normalmente e o problema entra no relatório como alerta. Não é um erro a corrigir: é o resultado esperado para um código com pouquíssimos pontos de alteração |
| `infrastructure failure: ...` (código `3`) | o próprio ambiente falhou (por exemplo, o compilador ou a pasta temporária do `sandbox`) | veja a mensagem, corrija (em geral `docker compose build`) e rode de novo; o comando retoma |

### Opções

| Opção | Padrão | Efeito |
|---|---|---|
| `--problem ID` | todos os problemas | processa só esse problema (pode ser repetida) |
| `--workers N` | metade das CPUs | quantos problemas são processados ao mesmo tempo; `1` roda tudo em série, no próprio processo; o resultado não muda |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/AC_ref.cpp` | C++ | dataset descompactado (módulo [`dataset`](../dataset/README.md)) |
| `data/dataset/problems/<id>/testes.json` | JSON (`schema_version` 1) | idem: suíte oficial, na ordem de execução |
| `data/dataset/problems/<id>/metadata.json` | JSON (`schema_version` 1) | idem: fornece os limites de tempo e de memória |
| `manifests/dataset.manifest.json` | JSON | versionado no repositório; usado para conferir o dataset antes de começar |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| `Mutant_<n>.cpp` (n de 1 a 100) | C++: o `AC_ref.cpp` com 1 posição alterada (ou 2 ou 3, na ordem superior), idêntico byte a byte fora delas | `data/mutants/problems/<id>/` (pasta ignorada pelo Git, nunca versionada); é o caminho de onde os módulos seguintes vão ler os mutantes |
| `generation.json` | JSON (`schema_version` 1): por mutante, o operador e a variante usados; por problema, quantos candidatos foram descartados e por quê | mesma pasta; alimenta os relatórios do módulo |

## (e) Dependências e pré-requisitos

- Python 3.11, `tree-sitter` 0.26 e `tree-sitter-cpp` 0.23 (fixadas em `uv.lock`), GCC 13.2.0 —
  tudo já dentro da imagem do projeto (`docker compose build`).
- Serviço `sandbox` do Docker Compose (sem rede), com o motor de execução do módulo
  [`sandbox`](../sandbox/README.md), usado sem alteração.
- Dataset já descompactado em `data/dataset/` e íntegro (o próprio comando confere).
- Nenhuma variável de ambiente nem segredo: o módulo não chama nenhuma IA.

## (f) Limitações conhecidas

- **Empacotamento ainda não existe**: quando existir, o pacote (`data/mutants.zip`) será descompactado
  em `data/` e cairá no mesmo caminho acima, de modo que quem gerou e quem só recebeu leem os
  mutantes do mesmo lugar; até lá, `data/mutants/` é resultado de desenvolvimento, local e sem valor
  como resultado do experimento. O `generate` nunca sobrescreve uma pasta de problema que já exista.
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
  64 não compilam, 48 equivalentes, 18 com erro de execução, 11 com tempo excedido). Depois do filtro descrito abaixo, 8 problemas completos (2026-09-24, computador de 4 núcleos e 8
  threads) levaram 3.520 s em série (média de 440 s por problema) e 1.700 s com `--workers 4`, ou
  seja, cerca de 2 vezes mais rápido, com exatamente os mesmos mutantes. Extrapolando (não medido),
  os 200 problemas levariam cerca de 24 horas em série e cerca de 12 com 4 trabalhadores; o ganho
  depende do computador. O comando pode ser interrompido e retomado.
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
| `generate` | 2026-09-24 | 5a0f7cc+dirty |
