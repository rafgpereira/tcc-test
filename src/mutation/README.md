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
`i <= n`. O módulo lê o código com um analisador sintático real (`tree-sitter`), não com busca de
texto, e por isso nunca altera o conteúdo de uma *string*, de um caractere entre aspas ou de um
comentário, nem confunde o `>>` que fecha `vector<vector<int>>` com o operador `>>`.

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

`--problem` pode ser repetido para vários problemas; sem ele, todos os problemas do dataset são
processados, na ordem das pastas. O comando:

1. confere `data/dataset` contra `manifests/dataset.manifest.json` e **para com código `1`** se
   algum arquivo divergir (assim os mutantes nunca são gerados sobre um dataset diferente do
   versionado);
2. processa cada problema e, ao terminar, imprime uma linha como
   `100 mutants (by order: {1: 100}); discarded: {<motivo>: <quantos>, ...}; <N> s` (por ordem de
   mutação, quantos candidatos foram descartados e por quê, e o tempo gasto no problema);
3. grava o resultado em `data/mutants/problems/<problema>/`: `Mutant_1.cpp` a `Mutant_100.cpp`,
   na ordem em que foram aceitos, e `generation.json` (como cada um foi obtido; uso interno);
4. no fim, resume: `done: N generated, N skipped, N excluded, N failed`.

**Como conferir:** `echo $?` deve mostrar `0`; `ls data/mutants/problems/189_C | wc -l` deve dar
`101` (100 mutantes mais o `generation.json`); `diff data/dataset/problems/189_C/AC_ref.cpp
data/mutants/problems/189_C/Mutant_1.cpp` mostra a alteração de uma única posição.

**Interromper e retomar:** apertar Ctrl+C (ou `docker stop`) é seguro — o comando termina com
código `130`. Cada problema é montado numa pasta provisória (`data/mutants/building/`) e só passa
para `data/mutants/problems/` inteiro, de uma vez; ao rodar de novo, o que estava pela metade
recomeça do zero e os problemas já concluídos são pulados (`already generated, skipped`).

### Se algo der errado

| O que aparece | O que significa | O que fazer |
|---|---|---|
| `error: data/dataset does not match manifests/dataset.manifest.json:` seguido de `changed:`/`missing:`/`extra:` (código `1`) | `data/dataset` não é o dataset versionado | `unzip data/dataset.zip -d data/` (sobrescreve com a versão correta) e rode de novo |
| `error: not in data/dataset: <id>` (código `2`) | o `--problem` não existe no dataset | confira o nome da pasta em `data/dataset/problems/` |
| `FAILED: <id>: first order reached N of 100 mutants ...` (código `1` no fim) | a primeira ordem (uma alteração por vez) não alcançou 100 mutantes válidos nesse problema, e a combinação de alterações ainda não está disponível | nada é gravado para esse problema; os demais seguem normalmente |
| `infrastructure failure: ...` (código `3`) | o próprio ambiente falhou (por exemplo, o compilador ou a pasta temporária do `sandbox`) | veja a mensagem, corrija (em geral `docker compose build`) e rode de novo; o comando retoma |

### Opções

| Opção | Padrão | Efeito |
|---|---|---|
| `--problem ID` | todos os problemas | processa só esse problema (pode ser repetida) |

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
| `Mutant_<n>.cpp` (n de 1 a 100) | C++: o `AC_ref.cpp` com 1 posição alterada, idêntico byte a byte fora dela | `data/mutants/problems/<id>/` (pasta ignorada pelo Git, nunca versionada) |
| `generation.json` | JSON (`schema_version` 1): por mutante, o operador e a variante usados; por problema, quantos candidatos foram descartados e por quê | mesma pasta; alimenta os relatórios do módulo |

## (e) Dependências e pré-requisitos

- Python 3.11, `tree-sitter` 0.26 e `tree-sitter-cpp` 0.23 (fixadas em `uv.lock`), GCC 13.2.0 —
  tudo já dentro da imagem do projeto (`docker compose build`).
- Serviço `sandbox` do Docker Compose (sem rede), com o motor de execução do módulo
  [`sandbox`](../sandbox/README.md), usado sem alteração.
- Dataset já descompactado em `data/dataset/` e íntegro (o próprio comando confere).
- Nenhuma variável de ambiente nem segredo: o módulo não chama nenhuma IA.

## (f) Limitações conhecidas

- **Só primeira ordem por enquanto**: um problema em que uma alteração por vez não alcança 100
  mutantes válidos termina em `FAILED` e não grava nada. A combinação de duas ou três alterações
  (que fecha a cota nesses casos) ainda não está disponível neste módulo.
- **Custo de tempo**: cada candidato é compilado e executado de verdade, e só uma fração é
  aceita. Medido em 2026-09-24 no problema `189_C` (usa `bits/stdc++.h`): compilar leva cerca de
  1,8 s e, para aceitar 20 mutantes, foi preciso avaliar 83 candidatos (28 equivalentes, 22 que não
  compilam, 7 com erro de execução, 6 com tempo excedido), em cerca de 350 s (duas execuções: 359 s e
  346 s, com o mesmo resultado nas duas). Por extrapolação (não medida),
  os 100 mutantes de um problema assim levam da ordem de meia hora e os 200 problemas, dezenas de
  horas. O comando roda em série (um candidato de cada vez) e pode ser interrompido e retomado.
- **Candidatos que não compilam são esperados**: o analisador é sintático e não conhece tipos; ABS
  ou UOI sobre um operando que não é numérico (por exemplo, `cout << x` com `abs(cout)`) simplesmente
  não compila e é descartado. Isso custa tempo, não corretude.
- **Mutantes equivalentes só são detectados pela suíte oficial**: um mutante que se comporta como o
  original em todos os testes oficiais é descartado, mesmo que seja diferente em alguma entrada que
  nenhum teste cobre.

## Referências

- Contratos: `specs/002-mutant-generation/contracts/`
- Testes: `tests/mutation/` (`docker compose run --rm sandbox pytest tests/mutation`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `generate` | pendente | — |
