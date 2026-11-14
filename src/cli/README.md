# Módulo `cli` (comandos que cruzam módulos)

> **Status**: implementado · **Metodologia**: `docs/metodologia-referencia.md`, seção 0.1

## (a) Propósito

Confere que dataset, mutantes, as suítes de teste dos quatro modelos (o local e os três comerciais) e os resultados dos cinco conjuntos de avaliação estão completos e 1:1 entre si e batem com os manifestos (comando `check`, que só lê).

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando).
O comando roda no serviço `app`, **só lê** (não escreve nada, não compila, não executa código de
terceiros e não usa a internet).

`check` percorre as pastas de verdade (o dataset **descompactado**, `data/dataset/`, e os mutantes,
`data/mutants/`) e confere, por nomes e contagens, que cada problema do dataset tem `AC_ref.cpp`,
`enunciado.md`, `metadata.json`, `testes.json`, `validacao.json` e exatamente `WA_1` a `WA_100`, que
cada problema tem exatamente `Mutant_1` a `Mutant_100`, que os nomes batem com os manifestos e que
dataset e mutantes são 1:1 nos dois sentidos (nenhum problema sem mutantes, nenhuma pasta de
mutantes sem problema). Confere também as suítes geradas pelos quatro modelos: a do modelo local
(`data/suites/slm/`, inclusive a árvore `data/suites/slm-rev1/`, que o pacote final do modelo local
junta à anterior) e as dos três comerciais, cada um na sua pasta (`data/suites/gpt/`,
`data/suites/gemini/` e `data/suites/claude/`); em cada caso, cada problema com as pastas dos três
cenários, cada cenário com o `suite.json` e as tentativas numeradas sem buraco (até 15 no modelo
local, até 3 nos comerciais). E confere os resultados da avaliação de cada conjunto
(`data/evaluation/<conjunto>/`): cada problema com os três cenários. Um artefato que ainda não foi
gerado e empacotado (pasta ausente, sem manifesto) aparece como aviso, não como falha. Não lê o
conteúdo dos códigos; com `--deep` também recalcula o SHA-256 de cada arquivo e dos zips e compara com
os manifestos. O que ele confere, uma a uma, e como um módulo novo entra nele:
[`docs/verificacao-consistencia.md`](../../docs/verificacao-consistencia.md).

### Cenário A — Rodar do zero

Depois de gerar o dataset e os mutantes do zero (e de descompactar o dataset), conferir tudo:

```bash
docker compose run --rm app python -m cli check --deep
```

Esperado: `Resultado: OK (0 falha(s), 0 aviso(s))`, com `pastas de problema: 200 (o manifesto diz
200)`, `200/200` em cada linha de arquivo, `todo problema de dataset tem pasta em mutants: 200/200`
e `0 sobrando`. Um artefato ainda não gerado e empacotado (mutantes, suítes de um modelo, avaliação
de um conjunto) aparece como aviso: gere-o pelo README do módulo dele e rode o `check` de novo.

### Cenário B — Descompactar o que já existe

Depois de descompactar o que está no repositório — `unzip data/dataset.zip -d data/`,
`unzip data/mutants.zip -d data/`, as suítes dos quatro modelos (`unzip data/slm_suites.zip -d
data/`, e o mesmo com `gpt_suites`, `gemini_suites` e `claude_suites`) e os cinco pacotes de
avaliação (`unzip data/evaluation_slm.zip -d data/`, e o mesmo com `evaluation_gpt`,
`evaluation_gemini`, `evaluation_claude` e `evaluation_slm-attempt1`); o laço que faz tudo de uma
vez está no "Caminho rápido" do [README da raiz](../../README.md), e o passo a passo de cada um, no
README do módulo que o gera ([`dataset`](../dataset/README.md), [`mutation`](../mutation/README.md),
[`ai_clients`](../ai_clients/README.md) e [`evaluation`](../evaluation/README.md)) —:

```bash
docker compose run --rm app python -m cli check --deep
```

Esperado: `Resultado: OK (0 falha(s), 0 aviso(s))`. Se faltar descompactar alguma pasta, a linha
`[FALHA]` ou `[AVISO]` diz qual; se algo falhar, lista os problemas afetados (até 10).

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m cli check` | `app` | confere nomes e contagens (menos de 1 s); `--deep` confere também os hashes de todos os arquivos e dos zips; `--only dataset` (ou `mutants`, `slm_suites`, `gpt_suites`, `gemini_suites`, `claude_suites`, `evaluation_slm`, `evaluation_gpt`, `evaluation_gemini`, `evaluation_claude`, `evaluation_slm_attempt1`; várias separadas por vírgula) confere só essas camadas. Termina com `0` sem falhas (avisos são permitidos), `1` com falha, `2` por uso incorreto ou manifesto do dataset ausente |
| `pytest tests/cli` | `sandbox` | testes do módulo |

`[AVISO]` não impede o `0`: um problema excluído por não alcançar 100 mutantes, a ausência do
manifesto de uma camada (só existe depois do `package` do módulo dela) e uma pasta ainda não gerada
sem manifesto.

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `[FALHA] a pasta data/dataset/problems não existe` | descompacte o dataset: `unzip data/dataset.zip -d data/` |
| `[FALHA] ... NÃO batem com o manifesto` ou `... com conteúdo diferente do manifesto` | há arquivo faltando, sobrando ou alterado: refaça o `unzip` (apague a pasta antes) |
| `[FALHA] N problema(s) pela metade em data/mutants/building` | rode `mutation generate` de novo até terminar |
| `[FALHA] todo problema de dataset tem pasta em mutants: K/200` | faltam mutantes para os problemas listados: `mutation generate` |
| `[FALHA] nenhuma pasta de mutants sem problema em dataset` | há pasta de mutantes de um problema que não está no dataset: apague-a |
| `[FALHA] tentativas numeradas sem buraco, no máximo 15 (execuções até a 12ª)` ou `arquivo(s) estranho(s) num cenário` | arquivos das suítes do modelo local foram apagados ou acrescentados à mão nos cenários listados: avise os autores |
| `[FALHA] a pasta data/suites/slm/problems não existe` (com `manifests/slm_suites.manifest.json` presente) | descompacte as suítes: `unzip data/slm_suites.zip -d data/` |
| `[FALHA] a pasta data/suites/gpt/problems não existe` (ou `gemini`/`claude`, com o manifesto desse modelo presente) | descompacte as suítes desse modelo: `unzip data/gpt_suites.zip -d data/` (trocando `gpt` por `gemini` ou `claude`) |
| `[FALHA] a pasta data/evaluation/<conjunto>/problems não existe` (com `manifests/evaluation_<conjunto>.manifest.json` presente) | descompacte a avaliação desse conjunto: `unzip data/evaluation_<conjunto>.zip -d data/` (`<conjunto>` é `slm`, `gpt`, `gemini`, `claude` ou `slm-attempt1`) |
| `error: manifest not found: manifests/dataset.manifest.json` (`2`) | rode a partir da pasta do repositório, com o `git pull` feito |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/` e `manifests/dataset.manifest.json` | pasta descompactada e JSON | módulo [`dataset`](../dataset/README.md) |
| `data/mutants/problems/<id>/` e `manifests/mutants.manifest.json` | pasta e JSON | módulo [`mutation`](../mutation/README.md); o manifesto é opcional (só existe depois do `package`) |
| `data/suites/slm/` (e, quando o pacote junta duas execuções de uma revisão do dataset, `data/suites/slm-rev1/`) e `manifests/slm_suites.manifest.json` | pasta(s) e JSON | módulo [`ai_clients`](../ai_clients/README.md); o manifesto só existe depois do `package` |
| `data/suites/gpt/`, `data/suites/gemini/` e `data/suites/claude/`, com `manifests/gpt_suites.manifest.json`, `manifests/gemini_suites.manifest.json` e `manifests/claude_suites.manifest.json` | pastas e JSON | módulo [`ai_clients`](../ai_clients/README.md), uma pasta e um manifesto por modelo comercial; cada manifesto só existe depois do `package --model <modelo>` |
| `data/evaluation/<conjunto>/` e `manifests/evaluation_<conjunto>.manifest.json` | pastas e JSON | módulo [`evaluation`](../evaluation/README.md), uma pasta e um manifesto por conjunto (`slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`); o manifesto só existe depois do `package --set` |
| `data/dataset.zip`, `data/mutants.zip`, `data/<modelo>_suites.zip` e `data/evaluation_<conjunto>.zip` | zips | só com `--deep` (zip ausente é aviso) |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| Resumo com `[OK]`, `[FALHA]`, `[AVISO]` e `[INFO]`, contagens e os problemas afetados | texto | saída padrão; o código de saída diz se há falha. Nada é gravado |

## (e) Dependências e pré-requisitos

- Python 3.11 (biblioteca padrão apenas) e o serviço `app` do Docker Compose.
- Dataset, mutantes, suítes e avaliações descompactados nas pastas acima, para as camadas que serão conferidas.

## (f) Limitações conhecidas

- Não lê o conteúdo dos códigos: confere nomes, contagens e (com `--deep`) hashes contra os manifestos.
- Não confere se os mutantes foram gerados a partir do `AC_ref.cpp` que está no dataset, só que os problemas e as contagens batem.
- Das suítes de cada modelo confere só a estrutura; o conteúdo de cada tentativa é conferido pelo próprio `ai_clients`.
- Dos resultados da avaliação confere a estrutura e os hashes; os vereditos são do próprio `evaluation`. As métricas (`data/metrics/`) não entram: são conferidas pelo `python -m metrics verify`.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 0.1
- Testes: `tests/cli/` (`docker compose run --rm sandbox pytest tests/cli`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `check` (inclusive `--deep`, com as camadas `slm_suites` (junção `slm`/`slm-rev1`), `gpt_suites`, `gemini_suites` e `claude_suites`) | 2026-11-03 | 25a239d+dirty |
