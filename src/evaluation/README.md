# Módulo `evaluation` (avaliação das suítes)

> **Status**: implementado · **Metodologia**: `docs/metodologia-referencia.md`, seção 4

## (a) Propósito

Executa cada suíte de teste gerada pelas IAs contra o código correto (`AC_ref`), os 100 WAs e os 100 mutantes de cada problema e grava, por combinação, os vereditos de que as métricas precisam.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
e tenha descompactados o dataset ([`dataset`](../dataset/README.md)), os mutantes
([`mutation`](../mutation/README.md)) e as suítes dos quatro modelos
([`ai_clients`](../ai_clients/README.md)), todos no Cenário B. `run` roda no serviço `sandbox`
(sem internet, o único que compila e executa C++ de terceiros); `report`, `package` e `verify` rodam
no `app` e não executam código.

**O que é avaliado.** Há cinco **conjuntos de avaliação**: `slm`, `gpt`, `gemini` e `claude` (a
suíte final de cada modelo) e `slm-attempt1` (a 1ª tentativa do modelo local, mesmo que rejeitada,
para comparar uma chamada contra uma com os modelos comerciais). Para cada problema e cenário:

- **contra o `AC_ref`**, todos os testes da suíte rodam até o fim, e cada um grava o veredito
  (`passed`, `wrong_output` ou `runtime_error` com o tipo `RE`, `TLE` ou `MLE`) e a saída real do
  AC. Se a suíte reprova o AC, é um falso positivo;
- **contra cada WA e mutante**, os testes rodam na ordem da suíte e param no primeiro que o código
  falha (ele foi **detectado**). A detecção é decidida por dois **oráculos** na mesma passada: o
  **declarado** (a saída escrita na suíte pela IA) e o **corrigido** (a saída real do AC na mesma
  entrada; os testes em que o AC dá erro ficam fora dele). A diferença entre os dois mostra quanto
  da detecção depende de a IA ter acertado a saída esperada;
- **um erro de execução** (estouro de tempo ou memória, falha) é repetido mais duas vezes e só vale
  se aparecer nas três; senão o teste fica marcado como **instável** (é ruído do ambiente, não da
  IA);
- **uma combinação sem suíte** (fechada à mão, ou uma 1ª tentativa sem entradas aproveitáveis) é
  gravada como tal, com o motivo, sem executar nada.

Cada programa é compilado uma vez por problema e executado contra todas as suítes daquele
problema. Não há aleatoriedade: a ordem é a dos testes na suíte e a dos alvos (`WA_1`..`WA_100`,
`Mutant_1`..`Mutant_100`).

### Cenário A — Rodar do zero

Primeiro um **piloto** nos 5 problemas dos pilotos (60 combinações finais e 15 da 1ª tentativa),
conferido à mão pelos autores; se nada mudar, a execução completa continua a mesma pasta:

```bash
docker compose run --rm sandbox python -m evaluation run --problem 1000_B --problem 1005_C \
  --problem 1008_B --problem 1_B --problem 61_B
docker compose run --rm app python -m evaluation report
docker compose run --rm sandbox python -m evaluation run          # completa, retomando o piloto
docker compose run --rm app python -m evaluation report
docker compose run --rm app python -m evaluation package --set gpt   # um por conjunto
docker compose run --rm app python -m evaluation verify --set gpt
docker compose run --rm app python -m cli check --deep
```

1. **`run`** começa pela auto-checagem do motor e por `cli check --deep` no dataset, nos mutantes
   e nas suítes dos modelos pedidos (código `1` e nada executado se algo falhar; esses portões
   levaram cerca de 9 minutos na máquina dos autores). No primeiro uso de cada conjunto grava
   `data/evaluation/<conjunto>/run.json` com os hashes das entradas e a versão do compilador; ao
   retomar, recusa (`2`) se algo disso mudou. Grava, por problema,
   `data/evaluation/<conjunto>/problems/<id>/black_box.json`, `white_box.json` e `hybrid.json` e
   imprime `ok <id> (<n> suites, <s> s)`; no fim, `done: N problem(s) evaluated, M already evaluated
   for every set`. Medido num problema (`1000_B`, os 5 conjuntos, `--workers 2`): 489 s, quase
   todo em compilar os 201 programas.
2. **`report`** grava `data/evaluation/<conjunto>/results.csv` (uma linha por combinação e alvo) e
   `manifests/evaluation_<conjunto>_report.json`, e imprime o resumo: combinações avaliadas e sem
   suíte, AC aprovado e reprovado, testes do AC por veredito, detectados em cada oráculo, testes
   instáveis e alvos que não compilaram (esperado `0`).
3. **`package`** refaz o `results.csv` e o relatório e grava `data/evaluation_<conjunto>.zip` e
   `manifests/evaluation_<conjunto>.manifest.json`; recusa (`1`) um conjunto incompleto (menos de
   600 combinações ou menos de 100 WAs e 100 mutantes em alguma) ou com problema pela metade. Os
   mesmos arquivos dão sempre o mesmo zip.
4. **`verify`** e **`check --deep`**: `OK` e `Resultado: OK`.

Para conferir à mão um problema: em `data/evaluation/gpt/problems/<id>/black_box.json`, `ac.tests`
tem um item por teste de `data/suites/gpt/problems/<id>/black_box/suite.json`, e um WA com
`declared.detected = true` de fato responde diferente no teste `declared.test_index`.

**Se você interromper** (Ctrl+C, `docker stop`), rode **o mesmo comando** de novo: cada conjunto de
cada problema só passa para `problems/` inteiro (é montado em `building/`), então nada concluído é
refeito nem reescrito; em cada problema, só os conjuntos que faltam são avaliados.

### Cenário B — Descompactar o que já existe

Os cinco conjuntos, um de cada vez:

```bash
for s in slm gpt gemini claude slm-attempt1; do
  rm -rf data/evaluation/$s
  unzip -q data/evaluation_$s.zip -d data/
  docker compose run --rm app python -m evaluation verify --set $s --extracted data/evaluation/$s
done
docker compose run --rm app python -m cli check --deep
```

O `unzip` recria `data/evaluation/<conjunto>/` (`run.json`, `results.csv` e `problems/`). Esperado:
`OK` em cada `verify` e `Resultado: OK` no `check`.

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m evaluation run` | `sandbox` | avalia as suítes. `--set S` (repetível; padrão os cinco: `slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`), `--problem ID` (repetível), `--workers N` (padrão: CPUs − 1; problemas ao mesmo tempo, cada um num *slot* do motor; não muda o resultado), `--output-dir DIR` (padrão `data/evaluation`; outra pasta para conferência ou um piloto guardado), `--scenario S` (repetível; só com `--output-dir` diferente do padrão). Retoma sozinho; só um `run` por pasta ao mesmo tempo (o segundo sai com `2`) |
| `python -m evaluation report` | `app` | refaz `results.csv` e o relatório de cada conjunto existente (ou só `--set S`); `--output-dir DIR` como no `run` (o relatório de outra pasta fica nela, nunca em `manifests/`). Funciona a qualquer momento; conjunto incompleto sai como `INCOMPLETE` |
| `python -m evaluation package --set S` | `app` | zip, manifesto e relatório de um conjunto completo |
| `python -m evaluation verify --set S` | `app` | confere o zip contra o manifesto; `--extracted DIR` confere também a pasta descompactada |
| `python -m cli check --deep` | `app` | inclui uma camada por conjunto (`evaluation_slm`, `evaluation_gpt`, `evaluation_gemini`, `evaluation_claude`, `evaluation_slm_attempt1`); antes do pacote, o que falta é só aviso |
| `pytest tests/evaluation` | `sandbox` | testes do módulo (os marcados `integration` compilam C++ de verdade) |

Códigos de saída: `0` sucesso, `1` portão ou pacote recusado, `2` uso incorreto (também
`run.json` de outras entradas ou outro `run` em andamento), `3` falha de infraestrutura (nada do
problema em andamento é gravado; rode de novo), `130` interrompido.

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `error: the engine selfcheck failed` (`1`) | não avalie nada; `docker compose build` e rode de novo; persistindo, avise os autores |
| ``error: `cli check --deep --only ...` failed`` (`1`) | descompacte de novo o artefato apontado (Cenário B do módulo dele) |
| `error: <conjunto>: run.json was recorded with other inputs (...)` (`2`) | as entradas mudaram desde o início do conjunto: use outra `--output-dir`, ou apague `data/evaluation/<conjunto>` para recomeçá-lo |
| `error: another ... run is already running` (`2`) | espere o outro terminar ou interrompa-o |
| `error: ... is not complete` (`1`, no `package`) | rode `run` até terminar; com `--problem`, só os problemas pedidos foram avaliados |
| `infrastructure failure` (`3`) | leia a mensagem (em geral `docker compose build`) e rode de novo; retoma |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/AC_ref.cpp`, `WA_1.cpp`..`WA_100.cpp`, `metadata.json` | C++ e JSON | dataset descompactado; `metadata.json` traz os limites de tempo e memória |
| `data/mutants/problems/<id>/Mutant_1.cpp`..`Mutant_100.cpp` | C++ | mutantes descompactados |
| `data/suites/<modelo>/problems/<id>/<cenário>/suite.json` | JSON | suítes descompactadas; no modelo local, a pasta de cada combinação vem de `data/suites/slm/provenance.json` (`suites/slm` ou `suites/slm-rev1`), e `slm-attempt1` lê os arquivos da tentativa 1 da mesma pasta |
| `manifests/dataset.manifest.json`, `mutants.manifest.json`, `<modelo>_suites.manifest.json` | JSON | versionados; seus hashes vão para o `run.json` |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| `<cenário>.json` | JSON com a origem da suíte, o AC teste a teste (veredito, saída real, repetições), os 200 alvos (detectado ou não em cada oráculo, teste e veredito que detectaram, testes instáveis) e os conjuntos de detectados | `data/evaluation/<conjunto>/problems/<id>/` (não versionado) |
| `run.json` | JSON: conjunto, hashes das entradas, revisão do dataset, versão do compilador | `data/evaluation/<conjunto>/` |
| `results.csv` | uma linha por combinação e alvo (uma só, sem alvo, para a combinação sem suíte); cabeçalho fixo | `data/evaluation/<conjunto>/`; é o que as métricas leem |
| `data/evaluation_<conjunto>.zip` | zip determinístico, raiz `evaluation/<conjunto>/` | **versionado** (`package`) |
| `manifests/evaluation_<conjunto>.manifest.json`, `manifests/evaluation_<conjunto>_report.json` | SHA-256 de cada arquivo; resumo do conjunto | **versionados** |

## (e) Dependências e pré-requisitos

- Python 3.11 e GCC 13.2.0, já na imagem (`docker compose build`); o motor do módulo
  [`sandbox`](../sandbox/README.md), sem alteração.
- Serviço `sandbox` para `run`; `app` para os demais. Nenhuma variável de ambiente nem segredo (não
  chama IA).
- Dataset, mutantes e suítes descompactados e íntegros (o próprio `run` confere).

## (f) Limitações conhecidas

- **Resultado da execução real** (200 problemas, 5 conjuntos, de 2026-11-04 a 2026-11-06): 3.000
  combinações, nenhum alvo sem compilar; 56 combinações sem suíte (3 do Claude, fechadas à mão, e 53
  da 1ª tentativa do modelo local, sem entrada aproveitável). Os pacotes têm de 1,9 a 3,1 MiB; a
  maior saída do AC numa entrada gerada pelas IAs teve 3,1 MB (modelo local).

- O tempo medido (`elapsed_s` de cada combinação e o total do relatório) é o de executar os testes;
  a compilação, feita uma vez por problema para todas as suítes, fica de fora e é a maior parte do
  tempo de um problema (veja o tempo impresso por `run`).
- A repetição de erros reduz, mas não elimina, a instabilidade de margem do motor (um veredito no
  limiar do tempo pode variar entre execuções); os testes instáveis ficam contados no relatório.
- O oráculo corrigido usa o `AC_ref` como verdade; um teste em que o próprio AC dá erro tem, em
  geral, uma entrada fora das restrições do problema e não entra nesse oráculo.
- Só o pacote versionado vale como resultado: uma avaliação local pode diferir na margem do motor.

## Referências

- Metodologia completa: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 4
- Consistência entre artefatos: [`docs/verificacao-consistencia.md`](../../docs/verificacao-consistencia.md)
- Testes: `tests/evaluation/` (`docker compose run --rm sandbox pytest tests/evaluation`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `run` (inclusive interrupção e retomada) | 2026-11-06 | 893505a |
| `report` | 2026-11-09 | 893505a |
| `package` | 2026-11-09 | 893505a |
| `verify` (inclusive `--extracted`) | 2026-11-09 | 893505a |
