# Módulo `mutation` (geração de mutantes)

> **Status**: implementado · **Metodologia**: `docs/metodologia-referencia.md`, seção 2

## (a) Propósito

Gera 100 mutantes válidos e distintos por problema a partir do `AC_ref.cpp` do dataset, para que a etapa de avaliação possa medir o Escore de Mutação das suítes de teste geradas pelas IAs.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
e tenha o dataset descompactado em `data/dataset/`
([README do módulo `dataset`](../dataset/README.md), Cenário B). `generate` roda no serviço
`sandbox` (sem internet, o único autorizado a compilar e executar código de terceiros: cada
mutante é compilado e executado de verdade); `report`, `package` e `verify` rodam no serviço `app`
e não executam C++.

Um **mutante** é uma cópia do `AC_ref.cpp` (a solução correta) com uma alteração sintática que
introduz um defeito artificial, por exemplo `i < n` trocado por `i <= n`. O código é lido por um
analisador sintático real (`tree-sitter`), então nunca se altera uma *string*, um comentário ou o
`>>` que fecha `vector<vector<int>>`, e a leitura e a escrita (`cin >>`, `cout <<`) não são
alteradas. As alterações são as cinco de Offutt et al. (1996): **ROR** (operadores relacionais),
**AOR** (`+ - * / %`, e `<<` com `>>`), **LCR** (`&&` com `||`), **ABS** (força um operando a `0`,
`+abs(x)` ou `-abs(x)`) e **UOI** (coloca ou troca `-`, `!`, `++`, `--`).

Cada candidato é **descartado** se repetir um texto já avaliado, não compilar, estourar tempo ou
memória, der erro de execução ou responder certo em **todos** os testes oficiais (equivalente); é
**aceito** só se der resposta errada nas seis execuções seguidas, sempre no mesmo teste. Limites de
tempo e memória vêm do `metadata.json` de cada problema. Os 100 primeiros mutantes válidos, na ordem
do código, são mantidos; se as alterações simples não chegam a 100, o módulo combina duas e depois
três (sempre em ordem fixa, sem busca); se nem assim, o problema é excluído com um alerta. **Não há
aleatoriedade nem seed**: repetir a geração dá os mesmos mutantes.

### Cenário A — Rodar do zero

Gera os mutantes sobre o dataset descompactado; faça **uma vez**, numa máquina, e publique o
resultado pelo Git.

```bash
docker compose run --rm sandbox python -m mutation generate --workers 4
docker compose run --rm app python -m mutation package
docker compose run --rm app python -m mutation verify
docker compose run --rm app python -m cli check --deep
```

1. **`generate`** confere `data/dataset` contra o manifesto (para com código `1` se divergir) e
   grava, por problema, `data/mutants/problems/<id>/Mutant_1.cpp` a `Mutant_100.cpp` e o
   `generation.json`. Imprime uma linha por problema (`100 mutants (by order: {1: 100});
   discarded: {...}`) e, no fim, `done: N generated, N skipped, N excluded`. Medido em 2026-09-25
   (200 problemas, `--workers 4`, 4 núcleos): cerca de 7 h 26 min. Com mais de um trabalhador, o
   tempo impresso por problema inclui a espera na fila: use só o total.
2. **`package`** (recusa se o dataset divergir, se houver problema pela metade, se algum problema
   perdeu ou teve um mutante alterado, ou se faltar gerar algum problema) grava `data/mutants.zip`
   (só os `Mutant_<n>.cpp` dos problemas completos), `manifests/mutants.manifest.json` e
   `manifests/mutation_report.json`, e imprime `packaged 200 problems (N excluded)`. Rodar de novo
   dá os mesmos bytes.
3. **`verify`** confere o zip e cada arquivo dentro dele contra o manifesto: `OK` (`0`) ou
   `changed:`/`missing:`/`extra:` e `FAIL` (`1`).
4. **`check --deep`** confere dataset e mutantes juntos, pelas pastas de verdade: `Resultado: OK`,
   200 problemas com 100 mutantes cada e nenhum sobrando de nenhum dos lados (ver
   [`docs/verificacao-consistencia.md`](../../docs/verificacao-consistencia.md)).

Para conferir a geração: `ls data/mutants/problems | wc -l` deve dar `200`; `ls
data/mutants/problems/<id> | wc -l` deve dar `101`; `diff data/dataset/problems/<id>/AC_ref.cpp
data/mutants/problems/<id>/Mutant_1.cpp` mostra a alteração. Depois, o zip e os dois JSON de
`manifests/` são o que se publica (nenhum comando faz `git add` ou `git commit`).

**Se você interromper** (Ctrl+C, `docker stop`, `kill -9`, queda de energia), rode **o mesmo
comando** de novo: cada problema só passa para `data/mutants/problems/` inteiro (é montado em
`data/mutants/building/`), então nada concluído se perde nem é refeito; só o problema em andamento é
refeito (alguns minutos). Ctrl+C encerra na hora (código `130`), e o resultado depois de retomar é
idêntico ao de uma execução sem interrupção. Só um `generate` roda por vez (um segundo se recusa).

### Cenário B — Descompactar o que já existe

Depois de um `git pull` que trouxe `data/mutants.zip` e os manifestos, **não rode `generate`**:

```bash
rm -rf data/mutants                       # apaga qualquer geração local antiga
unzip data/mutants.zip -d data/
docker compose run --rm app python -m mutation verify --extracted data/mutants
docker compose run --rm app python -m cli check --deep
```

O `unzip` recria `data/mutants/problems/<id>/`, o mesmo caminho que o Cenário A grava, que é de onde
os módulos seguintes leem. Esperado: `OK` no `verify` e `Resultado: OK` no `check`. Um `generate`
rodado por engano sobre essa pasta pula os problemas que já existem e nunca os sobrescreve. Os
mutantes gerados numa máquina podem diferir dos de outra (o motor tem uma margem de instabilidade);
por isso vale o pacote versionado, não regenerar.

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m mutation generate` | `sandbox` | gera os mutantes. `--problem ID` (repetível) restringe a esses problemas; `--workers N` (padrão metade das CPUs) processa N problemas ao mesmo tempo (só muda o tempo; um único `--problem` não acelera). Pula os problemas já concluídos; um concluído que perdeu ou teve um mutante alterado é apontado como `DAMAGED` (código `1`): apague `data/mutants/problems/<id>` e rode de novo para regerá-lo. Um problema que não chega a 100 é excluído (`ALERT`, código `0`, só o `generation.json`) |
| `python -m mutation report` | `app` | recalcula `manifests/mutation_report.json` (problemas por forma de fechar, funil de descartes, mutantes por ordem e por operador, alertas de exclusão, hash do manifesto do dataset) a partir do que já foi gerado, a qualquer momento; sem data nem hora, então repetir dá o mesmo arquivo |
| `python -m mutation package` | `app` | gera o zip, o manifesto e o relatório; `--allow-partial` empacota mesmo com problemas não gerados (só para teste, nunca para o pacote publicado) |
| `python -m mutation verify` | `app` | confere o zip e os arquivos dentro dele; `--extracted DIR` (`data/mutants`) confere também a pasta descompactada (só os `Mutant_<n>.cpp` contam); `--zip PATH`, `--manifest PATH` |
| `python -m cli check --deep` | `app` | consistência entre dataset e mutantes (ver acima) |
| `pytest tests/mutation` | `sandbox` | testes do módulo |

Códigos de saída: `0` sucesso, `1` falha de dados, `2` uso incorreto, `3` infraestrutura,
`130` interrompido.

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `error: data/dataset does not match manifests/dataset.manifest.json` (`1`) | `unzip data/dataset.zip -d data/` (apague `data/dataset` antes) e rode de novo |
| `error: not in data/dataset: <id>` (`2`) | confira o nome em `data/dataset/problems/` |
| `error: another ... generate is already running` (`1`) | espere o outro `generate` terminar ou interrompa-o |
| `<id>: DAMAGED (...)` (`1`) | `rm -r data/mutants/problems/<id>` e rode `generate` de novo |
| `error: N problem(s) half-written in data/mutants/building` (`1`, no `package`) | rode `generate` de novo até terminar |
| `error: K of N problems were not generated` (`1`, no `package`) | rode `generate` até terminar |
| `verify` termina em `FAIL` | veja o arquivo apontado; na pasta descompactada, refaça o `rm -rf` e o `unzip` |
| `infrastructure failure` (`3`) | leia a mensagem (em geral `docker compose build`) e rode de novo; retoma |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/AC_ref.cpp`, `testes.json`, `metadata.json` | C++ e JSON | dataset descompactado ([`dataset`](../dataset/README.md)); `metadata.json` traz os limites de tempo e memória |
| `manifests/dataset.manifest.json` | JSON | versionado; conferido antes de `generate`, `report` e `package` |
| `data/mutants.zip` e `manifests/mutants.manifest.json` | zip e JSON | versionados; lidos por `verify` |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| `Mutant_<n>.cpp` (n de 1 a 100) | C++: o `AC_ref.cpp` com 1 posição alterada (2 ou 3 na ordem superior), idêntico fora dela | `data/mutants/problems/<id>/` (não versionado); é de onde os módulos seguintes leem |
| `generation.json` | JSON: operador e variante de cada mutante e descartes por motivo | mesma pasta; não entra no zip |
| `data/mutants.zip` | zip determinístico, raiz `mutants/problems/<id>/`, só os `Mutant_<n>.cpp` dos problemas completos | **versionado** (`package`) |
| `manifests/mutants.manifest.json` | SHA-256 e tamanho do zip e de cada arquivo | **versionado** (`package`); lido por `verify` |
| `manifests/mutation_report.json` | agregados do relatório (ver `report`) | **versionado** (`report`, `package`) |

## (e) Dependências e pré-requisitos

- Python 3.11, `tree-sitter` 0.26 e `tree-sitter-cpp` 0.23 (fixados no `uv.lock`) e GCC 13.2.0, já na imagem (`docker compose build`).
- Serviço `sandbox` para `generate` (motor do módulo [`sandbox`](../sandbox/README.md), sem alteração) e `app` para os demais; nenhuma variável de ambiente nem segredo (não chama IA).
- Dataset descompactado em `data/dataset/` e íntegro (o próprio comando confere).

## (f) Limitações conhecidas

- **Mutantes de ordem superior**: na execução final, 87 dos 200 problemas precisaram combinar duas
  alterações (e um problema, três), de modo que 15,3% dos mutantes têm duas ou três alterações; o
  número fica em `manifests/mutation_report.json` (metodologia, seção 2.11).
- **Os mutantes não dependem dos enunciados**: eles são gerados só a partir do `AC_ref.cpp`, dos testes
  e dos limites. Por isso não foram regenerados quando o dataset passou para a revisão 2 (só os
  `enunciado.md` mudaram) e o `manifests/mutation_report.json` guarda o hash do manifesto do dataset
  da época da geração, não o da revisão atual (metodologia, seção 2).
- Mutantes de duas ou três alterações tendem a ser mais fáceis de detectar do que os de uma.
- O analisador é sintático e não conhece tipos: alguns candidatos (por exemplo, `abs` sobre uma
  variável `stringstream`) não compilam e são descartados; custa tempo, não correção.
- Um mutante equivalente só é reconhecido pela suíte oficial: um que se comporta como o original
  em todos os testes oficiais é descartado, mesmo que difira numa entrada que nenhum teste cobre.
- Só o pacote versionado vale como resultado do experimento; uma geração local pode diferir por
  causa da margem de instabilidade do motor (metodologia, seção 2.6).
- A recuperação é por problema: o que estava em andamento na interrupção é refeito inteiro.

## Referências

- Metodologia completa: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 2
- Testes: `tests/mutation/` (`docker compose run --rm sandbox pytest tests/mutation`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `generate` (inclusive interrupção e retomada) | 2026-09-25 | 8a45e6c |
| `report` | 2026-09-25 | 29af6d0 |
| `package` | 2026-09-25 | 29af6d0 |
| `verify` (inclusive `--extracted`) | 2026-09-25 | 29af6d0 |
