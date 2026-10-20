# Módulo `dataset`

> **Status**: implementado · **Metodologia**: `docs/metodologia-referencia.md`, seção 1

## (a) Propósito

Extrai do `code_contests` os problemas elegíveis do experimento, valida o código de cada um no motor de execução e empacota o resultado num arquivo único, verificável, pronto para ser distribuído e consumido pelos módulos seguintes.

## (b) Como executar

**Antes de começar** (uma vez por máquina): faça os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
(baixar o projeto, criar o `.env`, criar `data/`, construir a imagem e conferir com o `pytest`).
`extract`, `report`, `package` e `verify` rodam no serviço `app` (tem internet); `selfcheck`,
`validate` e `audit` rodam no serviço `sandbox` (sem internet, o único autorizado a compilar e
executar código de terceiros).

O módulo lê o `code_contests` (Hugging Face) em *streaming*, mantém só os problemas do Codeforces
com nota entre 1000 e 1600, tags permitidas, sem figura, sem tradução automática, com solução
correta e submissões incorretas em C++ e sem entrada/saída por arquivo, e os classifica em três
macrocategorias (`matematica`, `estrutural_otimizacao`, `logica_direta`). Dos elegíveis, os **200
primeiros** (numa ordem embaralhada uma única vez, com seed fixa) que têm o código correto e
exatamente 100 falhas reais confirmadas pelo motor (não erro de compilação, tempo ou memória)
formam a amostra; cada código passa pelo motor mais de uma vez, para a falha confirmada ser estável.
Critérios e regras: metodologia, seções 1.2 a 1.4. O resultado é o zip `data/dataset.zip` com um
manifesto de hashes.

### Cenário A — Rodar do zero

Só quando o dataset está sendo criado pela primeira vez ou refeito por mudança de critério ou de
motor: são comandos manuais e separados, um por vez, e levam de um a alguns dias. Faça **uma vez**,
numa máquina, e publique o resultado pelo Git.

1. **`extract`** — grava só os problemas elegíveis (~23 min medidos, depende da rede):

   ```bash
   docker compose run --rm app python -m dataset extract
   ```

   Ao final imprime o total lido e a distribuição por macrocategoria; o resumo fica em
   `data/work/reports/extraction_report.md`.

2. **`validate`** — executa o código de cada problema no motor até reunir 200 problemas
   `complete` (a etapa mais longa: **5 h 6 min** medidas, com 4 processos):

   ```bash
   docker compose run --rm sandbox python -m dataset validate
   ```

   Roda uma auto-checagem do motor antes e recusa continuar se ela falhar. Ao final imprime
   `included N of 200 (deficit D)`; `D` é `0` em caso de sucesso. Cada problema termina em `complete`
   (código correto passou e há 100 falhas reais), `pending_triage` (o código correto falhou no
   motor; fica fora da amostra para inspeção manual) ou `discarded` (não há 100 falhas confirmáveis).
   Se sobrar déficit, nada é relaxado sozinho: a decisão é manual.

3. **`audit`** — reexecuta de forma independente cada problema `complete` e **repara
   automaticamente** o que mudar de resultado (troca a falha instável pela próxima candidata, com
   confirmação em seis execuções); avisa `could not be repaired` se não achar substituta:

   ```bash
   docker compose run --rm sandbox python -m dataset audit
   ```

   Rode uma última vez, sem nada para reparar, antes de empacotar.

4. **`package`** — reúne os problemas `complete` num zip determinístico e grava o manifesto:

   ```bash
   docker compose run --rm app python -m dataset package
   ```

   Recusa empacotar com menos de 200 problemas `complete` e avisa se o zip passar de 95 MB.

5. **`verify`** — confere o zip contra o manifesto; esperado: `OK`:

   ```bash
   docker compose run --rm app python -m dataset verify
   ```

   O zip e os manifestos (`data/dataset.zip`, `manifests/dataset.manifest.json`,
   `manifests/extraction_report.json`) são o que se publica; nenhum comando faz `git add` ou
   `git commit` sozinho.

6. **Descompactar** — nenhum comando acima cria `data/dataset/`, a pasta que os módulos seguintes
   leem; ela só existe depois do `unzip`, como para quem recebe o dataset (Cenário B).

Em notebook, mantenha na tomada e evite suspensão durante a validação
(`systemd-inhibit --what=sleep:idle -- <comando>`).

### Cenário B — Descompactar o que já existe

O caso comum: o zip e os manifestos já estão no repositório; **nunca** é preciso rodar extração nem
validação.

```bash
rm -rf data/dataset                      # só se já houver uma versão antiga
unzip data/dataset.zip -d data/
docker compose run --rm app python -m dataset verify --extracted data/dataset
docker compose run --rm app python -m cli check --only dataset
```

Esperado: `OK` no `verify` e `Resultado: OK` no `check`, com `pastas de problema: 200 (o manifesto
diz 200)` e `200/200` em cada arquivo. O `verify` sem `--extracted` confere só o zip; o
`--extracted` é o que confere a pasta `data/dataset/`. O `unzip` cria `data/dataset/problems/<id>/`,
uma pasta por problema com `enunciado.md`, `AC_ref.cpp` (a solução correta), `WA_1.cpp` a
`WA_100.cpp` (as 100 falhas reais), `testes.json` (a suíte oficial), `metadata.json` e
`validacao.json`. Sem `unzip`: `docker compose run --rm app python -m zipfile -e data/dataset.zip
data/`.

**Revisão do dataset.** O `data/dataset.zip` versionado é a revisão indicada no manifesto (campo `revision`; sem ele, a revisão 1). A revisão 2 só corrige enunciados (expoentes e índices perdidos na extração); o que mudou está em `manifests/dataset_revision.json`. A revisão anterior fica guardada só para auditoria, e nenhum comando a usa; para conferir a integridade dela:

```bash
docker compose run --rm app python -m dataset verify --zip data/dataset.rev1.zip --manifest manifests/dataset.rev1.manifest.json
```

**Conferir os enunciados contra o original do Codeforces**, sem acessar o site, quando o pacote
`data/statement_originals.zip` e o manifesto dele já estão no repositório:

```bash
docker compose run --rm app python -m dataset check-statements
```

Esperado: as linhas `statements: 200 checked; ...` e a contagem por tipo de diferença, iguais às do
relatório versionado, e nenhuma linha `fetch:` (nenhum acesso ao site).

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m dataset extract` | `app` | lê o dataset de origem e grava o pool de elegíveis. `--limit-rows N` (teste rápido; recomece com `rm -rf data/work`), `--splits LIST` (padrão `train,valid,test`), `--seed INT` (padrão `42`; mudar muda a amostra). Interrompido (Ctrl+C), retoma com o mesmo comando |
| `python -m dataset report` | `app` | regenera `data/work/reports/extraction_report.{md,json}`; os outros comandos já o fazem ao terminar |
| `python -m dataset selfcheck` | `sandbox` | roda 9 programas de veredito conhecido no motor (~7 s); esperado `selfcheck OK: 9/9 cases` |
| `python -m dataset validate` | `sandbox` | valida até a meta. `--target N` (padrão 200; `--target 10` é um piloto), `--workers N` (padrão metade das CPUs; só muda o tempo), `--problem ID` (só um problema, ignora a meta). Pode ser interrompido a qualquer momento e retomado com o mesmo comando: só o que estava em andamento é refeito |
| `python -m dataset audit` | `sandbox` | reexecuta e repara. `--problem ID` (repetível), `--workers N` |
| `python -m dataset package` | `app` | gera o zip e o manifesto. `--target N` (padrão 200), `--allow-partial` (só para teste) |
| `python -m dataset verify` | `app` | confere o zip contra o manifesto; `--extracted DIR` confere também a pasta descompactada (`DIR` é `data/dataset`); `--zip PATH`, `--manifest PATH` |
| `python -m dataset check-statements` | `app` | compara cada `enunciado.md` com o enunciado original no Codeforces. Na primeira vez, baixa a página de cada problema, **uma por vez, a cada 3 s ou mais** (pelo menos 10 minutos para os 200), e guarda a cópia em `data/statements/originals/`, com o hash em `manifests/statement_originals.manifest.json`; depois disso não acessa mais o site. Lista cada diferença com o trecho e o tipo, dado pelo que estava no original naquele ponto: `lost_exponent` (`10^5` virou `105`), `lost_index` (`a_i` virou `ai`), `formula`, `image`, `table` ou `other`. Grava `manifests/statement_fidelity_report.json` e o pacote `data/statement_originals.zip` (só os blocos do enunciado, sempre com os mesmos bytes para os mesmos blocos). Perdas não são falha: saída `0`. `--problem ID` (repetível) só imprime o resultado daqueles problemas e não grava o relatório. `--refetch` baixa de novo, mesmo com cópia; página inexistente (404) ou sem o enunciado só é tentada de novo com ele. Site recusando pedidos ou fora do ar: espera 30 s a 5 min e repete; esgotadas as esperas, sai com `3` e guarda o que já baixou (rodar de novo continua). Cópia alterada ou dataset diferente do manifesto: `1` |
| `python -m dataset correct-statements --output-dir data/statements/corrected` | `app` | grava, **para revisão**, os enunciados com os expoentes e índices que o original tem: o texto atual com `^{...}` e `_{...}` inseridos nos lugares que o `check-statements` encontrou, e as tabelas em Markdown. Só aceita um enunciado se ele passar em três conferências: (1) tirando as marcas, o texto é o original; (2) não sobra expoente ou índice perdido; (3) só as marcas mudaram. Grava `<id>.md` e `summary.json` numa pasta só; os que têm imagem, fórmula diferente ou outra diferença vão para a lista `review`, com o motivo. **Nunca altera o dataset.** Pasta com arquivos: `2`, a menos que se use `--force`; nunca dentro de `data/dataset/`, `data/suites/` ou `manifests/`. Sem o relatório do `check-statements`: `1` |
| `python -m dataset revise` | `app` | gera a **revisão 2** do dataset: só os `enunciado.md` mudam, todos os outros arquivos ficam com os mesmos bytes. Os enunciados que o `correct-statements` corrige sozinho (aprovados nas três conferências) são refeitos a partir do relatório do `check-statements`; os da lista de revisão usam a decisão dos autores em `manifests/statement_decisions/<id>.json` (`correct`, com o texto corrigido, ou `keep`, com o motivo, nome e data). Recusa (`1`, nada gravado) se faltar decisão, se uma decisão mudar texto que o relatório não apontou como diferente, se o relatório for de outro dataset ou se o dataset descompactado não bater com o manifesto. Guarda a revisão 1 em `data/dataset.rev1.zip` e `manifests/dataset.rev1.manifest.json` e grava o zip novo, o manifesto (com a revisão e de onde ela veio) e `manifests/dataset_revision.json` (o que mudou, com o hash antes e depois). Imprime o `unzip` a rodar e os `generate`/`execute` das combinações do modelo local afetadas (caixa-preta e híbrido dos enunciados alterados). `--draft-decisions` grava um rascunho de decisão para cada problema em revisão que ainda não tem (o texto atual, as diferenças com o trecho do original e a sugestão de marcação; nunca sobrescreve). `--dry-run` faz todas as conferências sem gravar. Revisão 2 já existente: `1` |
| `pytest tests/dataset` | `sandbox` | testes do módulo |

Códigos de saída: `0` sucesso, `1` falha de dados (déficit, integridade), `2` uso incorreto, `3`
infraestrutura (rede, disco: repita o comando), `130` interrompido (também seguro).

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| `infrastructure failure` (`3`) ou `interrupted` (`130`) | rode o mesmo comando de novo; retoma de onde parou |
| `error: no pool found` (`1`) | rode `extract` antes de `validate` ou `report` |
| `selfcheck` com `FAIL`, ou `infrastructure failure` no `validate` | o motor está errado ou o comando rodou no serviço `app`; veja o README do [`sandbox`](../sandbox/README.md) |
| `N problem(s) in pending_triage need individual inspection` (`1`) | inspecione `data/work/problems/<id>/validacao.json` (campo `triage`) e decida manualmente |
| `error: only N of 200 complete problems` (`1`, no `package`) | rode `validate` até `deficit 0` |
| `changed:` / `missing:` / `extra:` e `FAIL` (`1`) | não use esse dataset; refaça o `unzip` (apague `data/dataset` antes) ou gere o zip de novo |
| `error: manifest not found` (`2`) | falta `data/dataset.zip` ou o manifesto: rode `package` (quem gera) ou confira o `git pull` |
| `fetch: ... HTTP 429 ...; waiting N s` | o Codeforces pediu para esperar; o comando espera e repete sozinho |
| `infrastructure failure: ...; stopped asking the site` (`3`, no `check-statements`) | o site continuou recusando; rode de novo mais tarde, e só o que falta é baixado |
| `error: <id>: the page differs from page_sha256` (`1`) | uma cópia guardada mudou; apague-a e rode com `--refetch --problem <id>`, ou descompacte de novo |
| `PermissionError` em `data/` | `data/` pertence a `root`: `sudo chown -R "$(id -u):$(id -g)" data` |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| Dataset `deepmind/code_contests` | *streaming* Parquet (biblioteca `datasets`), revisão fixa | Hugging Face (público, CC-BY-4.0) |
| `HF_TOKEN` (opcional) | variável do `.env` | só aumenta o limite de requisições |
| Pool e problemas brutos (para `validate`) | `data/work/staging/pool.json` e `raw/*.json.gz` | gerados por `extract` |
| Problemas validados (para `audit`) | `data/work/problems/<id>/` | gerados por `validate` |

## (d) Saídas produzidas

Duas pastas parecidas, com finalidades diferentes:

- **`data/work/`** — espaço de trabalho de **quem gera** (Cenário A): todos os problemas
  processados (`complete`, `discarded`, `pending_triage`), para auditoria e retomada. Privado
  (permissão `0700`), nunca lido por outro módulo nem versionado; pode ser apagado depois de
  `package` e `verify`.
- **`data/dataset/`** — a cópia de **distribuição**, obtida com `unzip` (Cenário B): só os 200
  problemas `complete`. **É esta pasta que os módulos seguintes leem**, nunca `data/work/`.

| Saída | Formato | Destino |
|---|---|---|
| `data/dataset.zip` | zip determinístico, raiz `dataset/`, 200 problemas | **versionado** |
| `manifests/dataset.manifest.json` | SHA-256 do zip e de cada arquivo, com a proveniência (revisão do dataset de origem, seed, compilador) | **versionado**; lido por `verify` |
| `manifests/extraction_report.json` | cópia congelada do relatório do momento do empacotamento | **versionado**; use-o (não o de `data/work/`) para citar números de uma versão distribuída |
| `data/work/reports/extraction_report.{md,json}` | funil de elegibilidade, distribuição por macrocategoria e por split, descartes, triagens | primeira leitura do resultado |
| `data/work/reports/validation_log.jsonl`, `selfcheck.json` | uma linha por problema processado; resultado da auto-checagem do motor | diagnóstico de uma execução |
| `data/work/problems/<id>/validacao.json` | veredito de cada código, padrão de C++ usado, tempo e memória máximos | comprova que cada código passou pelo motor |
| `manifests/statement_originals.manifest.json`, `data/statement_originals.zip` | URL, data e SHA-256 de cada página original do Codeforces e do bloco do enunciado; o pacote só com os blocos | **versionados**; o `check-statements` roda a partir deles sem acessar o site |
| `manifests/statement_fidelity_report.json` | por problema, as diferenças entre o original e o `enunciado.md`, com tipo e trecho; os totais por tipo | **versionado** |
| `data/dataset.rev1.zip`, `manifests/dataset.rev1.manifest.json` | a revisão 1, guardada pelo `revise` | **versionados**; só para auditoria |
| `manifests/dataset_revision.json`, `manifests/statement_decisions/<id>.json` | o que a revisão 2 mudou (origem automática ou manual, hash antes e depois) e cada decisão dos autores | **versionados** |
| `data/statements/originals/`, `data/statements/corrected/` | as páginas inteiras; os enunciados corrigidos para revisão | não versionados |

## (e) Dependências e pré-requisitos

- Python 3.11.16, `datasets` 5.0.1 e `pydantic` 2.x, fixados no `uv.lock`; ambiente com `docker compose build`.
- Serviços `app` (com rede) e `sandbox` (sem rede, com as capabilities do motor), como descrito em (b).
- `.env` com `HOST_UID` e `HOST_GID` (`HF_TOKEN` é opcional) e a pasta `data/` criada por você
  (passos 2 e 3 do guia da raiz).
- Nenhum módulo anterior precisa ter rodado.

## (f) Limitações conhecidas

- Problemas que leem `input.txt` ou escrevem `output.txt` são excluídos: o motor usa `stdin` e `stdout`.
- Quantas submissões incorretas viram falha confirmada varia por problema; nos splits `valid`/`test`
  há menos, então a amostra vem sobretudo do `train`. `validate --target 10` estima isso antes.
- Problemas em `pending_triage` só são inspecionados manualmente se a meta de 200 não for atingida.
- A auditoria repara automaticamente falhas instáveis (comportamento indefinido ou tempo no limiar
  do limite); afetou cerca de 1 em cada 10 problemas na única execução completa, sempre com um
  substituto equivalente.
- Retomar não muda o resultado, exceto o carimbo de data/hora da extração e o tempo de CPU medido
  (`max_cpu_time_s` em `validacao.json`), que variam com o hardware.
- O zip final tem cerca de 12 MiB (o GitHub recusa acima de 100 MB). O hash do zip depende da
  versão da biblioteca de compressão da imagem Docker; por isso o manifesto guarda também o hash de
  cada arquivo dentro dele.

## Referências

- Metodologia completa: [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), seção 1
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
| `verify` (inclusive pós-clonagem e `--extracted`) | 2026-09-22 | 9b87d7e |
| `check-statements --problem` (5 problemas) | 2026-10-18 | 9df4f0e+dirty |
| `check-statements` (200 problemas; inclusive a segunda execução sem acesso ao site) | 2026-10-18 | 9df4f0e+dirty |
| `correct-statements` | 2026-10-18 | 9df4f0e+dirty |
| `revise` (inclusive `--draft-decisions` e `--dry-run`) | 2026-10-18 | 29d9245+dirty |
