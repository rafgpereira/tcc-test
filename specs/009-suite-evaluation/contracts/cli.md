# Contrato: `python -m evaluation`

Todos os subcomandos usam a raiz do repositório (`/app` no contêiner). `run` executa código de
terceiros e **só** roda no serviço `sandbox`; `report`, `package` e `verify` só leem/escrevem
arquivos e rodam no `app` ou no `sandbox`.

## `run`

```text
python -m evaluation run [--set SET ...] [--problem ID ...] [--scenario S ...]
                         [--workers N] [--output-dir DIR]
```

| Opção | Padrão | Efeito |
|---|---|---|
| `--set` | os 5 conjuntos | `slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`; repetível |
| `--problem` | os 200 | restringe a problemas (piloto, conferência); repetível |
| `--scenario` | os 3 | `black_box`, `white_box`, `hybrid`; repetível; **só com `--output-dir` diferente de `data/evaluation`** (conferência): o problema é fechado só com os cenários pedidos, e essa árvore nunca é empacotada |
| `--workers` | nº de CPUs − 1, mínimo 1 | trabalhadores (um *slot* cada) |
| `--output-dir` | `data/evaluation` | outra árvore (piloto guardado, conferência) |

Comportamento:

1. Portões (R11): `selfcheck` do motor; `cli check --deep` nas camadas `dataset`, `mutants` e
   `<modelo>_suites` dos modelos pedidos. Falha → nada executado.
2. Trava exclusiva de `<output-dir>`; segunda execução simultânea → recusa.
3. Para cada conjunto: cria `run.json` ou confere o existente (R8); diferença → recusa.
4. Apaga `building/` sobrando. A unidade é conjunto × problema: um problema só é processado se
   falta algum dos conjuntos pedidos, e nele só os conjuntos que faltam são avaliados (os
   programas são compilados uma vez para eles); conjunto já em `problems/` nunca é reescrito.
5. Por problema (em paralelo entre problemas): compila e avalia (contracts/evaluation-api.md);
   grava cada conjunto × problema em `building/` e fecha com `rename`.
6. Uma linha por problema concluído: `ok <id> (<n> suites, <s> s)`; ao fim, totais.

Interrupção (Ctrl+C): os problemas em andamento são descartados (nada fica em `problems/`
pela metade); rodar de novo continua do ponto em que parou.

Códigos de saída: `0` concluído; `1` portão falhou (`selfcheck` ou `cli check`); `2` uso
incorreto, `run.json` divergente ou execução já em andamento; `3` falha de infraestrutura do
motor (nada do problema em andamento é gravado); `130` interrompido.

## `report`

```text
python -m evaluation report [--set SET ...] [--output-dir DIR]
```

Lê `problems/` de cada conjunto, valida cada `CombinationResult`, grava `results.csv` na pasta do
conjunto e `manifests/evaluation_<set>_report.json` (data-model.md; numa `--output-dir` que não é a
padrão, o relatório fica nela), e imprime o resumo. Conjunto
incompleto: gera mesmo assim, com `complete: false` e a lista do que falta. Códigos: `0`; `1`
arquivo inválido; `2` uso incorreto.

## `package`

```text
python -m evaluation package --set SET [--output-dir DIR]
```

Refaz `results.csv` e o relatório (como `report`) e recusa se o conjunto não tem as 600 combinações
com 100 WAs e 100 mutantes cada, ou se há `building/` (divergência registrada na metodologia: refazer
em vez de recusar um relatório desatualizado). Gera `data/evaluation_<set>.zip` (só
`run.json`, `results.csv` e `problems/`) e `manifests/evaluation_<set>.manifest.json`, com
escrita atômica. Códigos: `0`; `1` recusa; `2` uso incorreto.

## `verify`

```text
python -m evaluation verify --set SET [--extracted data/evaluation/SET]
```

Sem `--extracted`, confere o zip contra o manifesto; com ele, a pasta descompactada. Códigos:
`0` confere; `1` diverge; `2` manifesto ou alvo ausente.

## Camadas do `cli check`

`evaluation_slm`, `evaluation_gpt`, `evaluation_gemini`, `evaluation_claude`,
`evaluation_slm_attempt1`: pasta `data/evaluation/<set>/problems/`; cada problema com
exatamente `black_box.json`, `white_box.json`, `hybrid.json`; nada em `building/` depois do
pacote; 1:1 com o dataset; manifesto e zip com `--deep`. Faltas são `[AVISO]` até o manifesto
existir e `[FALHA]` depois; arquivo estranho e pasta sem problema no dataset são `[FALHA]` sempre.
Camada ausente (avaliação ainda não começada) é `[AVISO]`.
