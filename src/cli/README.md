# Módulo `cli` (comandos que cruzam módulos)

> **Status**: em implementação · **Metodologia**: `docs/metodologia-referencia.md`, seção 0.1

## (a) Propósito

Reúne os comandos que atravessam mais de um módulo do projeto, hoje a conferência de que dataset, mutantes e suítes de teste do modelo local estão completos e 1:1, e é onde o orquestrador do experimento vai ficar.

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
mutantes sem problema). Confere também as suítes geradas pelo modelo local
(`data/suites/slm/`): cada problema com as pastas dos três cenários, cada cenário com o
`suite.json` e as tentativas numeradas sem buraco, até 6. Enquanto essa geração não foi
empacotada, o que ainda falta nela (a pasta inteira, um problema, um cenário, um `suite.json`) é
só aviso: é a geração em andamento. Não lê o conteúdo dos códigos; com `--deep` também recalcula o SHA-256 de
cada arquivo e dos zips e compara com os manifestos. O que ele confere, uma a uma, e como um módulo
novo entra nele: [`docs/verificacao-consistencia.md`](../../docs/verificacao-consistencia.md).

### Cenário A — Rodar do zero

Depois de gerar o dataset e os mutantes do zero (e de descompactar o dataset), conferir tudo:

```bash
docker compose run --rm app python -m cli check --deep
```

Esperado: `Resultado: OK (0 falha(s), 0 aviso(s))`, com `pastas de problema: 200 (o manifesto diz
200)`, `200/200` em cada linha de arquivo, `todo problema de dataset tem pasta em mutants: 200/200`
e `0 sobrando`. Antes do empacotamento dos mutantes, e enquanto as suítes do modelo local não
foram geradas e empacotadas, o resultado traz avisos (os manifestos ainda não existem).

### Cenário B — Descompactar o que já existe

Depois de `unzip data/dataset.zip -d data/`, `unzip data/mutants.zip -d data/` e, quando
existir, `unzip data/slm_suites.zip -d data/`:

```bash
docker compose run --rm app python -m cli check --deep
```

Esperado: o mesmo `Resultado: OK`. Se algo falhar, a linha `[FALHA]` diz o que e lista os problemas
afetados (até 10).

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m cli check` | `app` | confere nomes e contagens (menos de 1 s); `--deep` confere também os hashes de todos os arquivos e dos zips; `--only dataset` (ou `mutants`, ou `slm_suites`; várias separadas por vírgula) confere só essas camadas. Termina com `0` sem falhas (avisos são permitidos), `1` com falha, `2` por uso incorreto ou manifesto do dataset ausente |
| `pytest tests/cli` | `sandbox` | testes do módulo |

`[AVISO]` não impede o `0`: um problema excluído por não alcançar 100 mutantes, a ausência do
manifesto de mutantes (só existe depois do `package`), e as suítes do modelo local ainda em geração.

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
| `error: manifest not found: manifests/dataset.manifest.json` (`2`) | rode a partir da pasta do repositório, com o `git pull` feito |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| `data/dataset/problems/<id>/` e `manifests/dataset.manifest.json` | pasta descompactada e JSON | módulo [`dataset`](../dataset/README.md) |
| `data/mutants/problems/<id>/` e `manifests/mutants.manifest.json` | pasta e JSON | módulo [`mutation`](../mutation/README.md); o manifesto é opcional (só existe depois do `package`) |
| `data/suites/slm/` e `manifests/slm_suites.manifest.json` | pasta e JSON | módulo [`ai_clients`](../ai_clients/README.md); o manifesto só existe depois do `package` |
| `data/dataset.zip`, `data/mutants.zip` e `data/slm_suites.zip` | zips | só com `--deep` (zip ausente é aviso) |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| Resumo com `[OK]`, `[FALHA]`, `[AVISO]` e `[INFO]`, contagens e os problemas afetados | texto | saída padrão; o código de saída diz se há falha. Nada é gravado |

## (e) Dependências e pré-requisitos

- Python 3.11 (biblioteca padrão apenas) e o serviço `app` do Docker Compose.
- Dataset, mutantes e suítes descompactados nas pastas acima, quando as camadas correspondentes são conferidas.

## (f) Limitações conhecidas

- Não lê o conteúdo dos códigos: confere nomes, contagens e (com `--deep`) hashes contra os manifestos.
- Não confere se os mutantes foram gerados a partir do `AC_ref.cpp` que está no dataset, só que os problemas e as contagens batem.
- Das suítes do modelo local confere só a estrutura; o conteúdo de cada tentativa é conferido pelo próprio `ai_clients`.
- Ainda não confere as suítes dos dois modelos comerciais nem os resultados da avaliação: cada módulo novo acrescenta a sua camada.

## Referências

- Metodologia: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 0.1
- Testes: `tests/cli/` (`docker compose run --rm sandbox pytest tests/cli`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `check` (inclusive `--deep`) | 2026-09-25 | 6e4528a |
