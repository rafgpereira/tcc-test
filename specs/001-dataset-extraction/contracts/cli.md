# Contract: Interface de linha de comando do módulo `dataset`

**Feature**: `001-dataset-extraction` | Consumidores: os dois autores; módulos futuros só leem
os arquivos produzidos (não chamam a CLI).

Ponto de entrada: `python -m dataset <comando>` (pacote `src/dataset/`, `__main__.py`, apenas
`argparse`), sempre dentro do contêiner. Não há CLI de projeto (`src/cli/`) nesta feature; o
orquestrador do projeto é escopo futuro.

## Serviços do Docker Compose

| Serviço | Rede | Privilégios do processo principal | Usado para |
|---|---|---|---|
| `app` | com rede | usuário `pipeline` (uid 1000), `cap_drop: ALL`, sistema de arquivos raiz somente leitura | `extract`, `package`, `verify`, `report`, lint/format |
| `sandbox` | **`network_mode: none`** | root com `cap_drop: ALL` + `CHOWN, DAC_OVERRIDE, SETUID, SETGID, KILL`; `no-new-privileges`; raiz somente leitura; `tmpfs` com `exec` para compilar/executar | `selfcheck`, `validate`, `audit`, `pytest` |

Regra: comandos que executam código de terceiros só existem no serviço `sandbox`, sem rede.
Ambos montam `./data` em `/app/data` (leitura e escrita).

## Comandos

A linha de uso de `python -m dataset --help` lista os subcomandos no grupo `{a,b,c}` (formato do
`argparse`); `scripts/check_docs_sync.py` (checagem C2) depende disso para comparar a CLI com os
READMEs, então esse formato não deve mudar sem ajustar o script.

Códigos de saída comuns: `0` sucesso; `1` falha de verificação/validação de dados (ex.:
integridade divergente, AC em triagem); `2` uso incorreto; `3` falha de infraestrutura (rede,
disco, ambiente isolado); `130` interrompido (a retomada é segura).

### `extract` (serviço `app`)

Faz uma passagem em streaming pelos três splits, fixada no `hf_revision` da configuração,
aplica elegibilidade (FR-004), classifica (FR-006), aplica a pré-checagem de contagem de WAs
brutas e grava `staging/pool.json` e `staging/raw/*.json.gz`.

| Opção | Padrão | Efeito |
|---|---|---|
| `--seed INT` | `config.SEED` (`42`) | seed da ordem de processamento; gravada no pool |
| `--splits LIST` | `train,valid,test` | splits lidos, nesta ordem (a primeira ocorrência de um `problem_id` vence) |
| `--limit-rows N` | sem limite | limita linhas por split (somente fumaça/testes) |

Idempotente e retomável por shard: um shard só é marcado como concluído depois de gravar seus
arquivos `raw`; shards concluídos são pulados; `pool.json` é regravado de forma atômica ao
final. Saída: resumo do funil na saída padrão; detalhes em `reports/`.

### `selfcheck` (serviço `sandbox`)

Executa a suíte de programas de veredito conhecido contra o motor (FR-010a): 9 programas, cada um
duas vezes (estabilidade). Imprime uma linha por caso e `selfcheck OK: 9/9 cases`. Código `0` só se
todos os vereditos coincidirem (e forem estáveis), `1` se algum falhar e `3` se o ambiente não
permite (por exemplo, rodado no serviço `app`, que não tem o motor). Sem opções.

### `validate` (serviço `sandbox`)

Executa `selfcheck` primeiro e **aborta** se falhar. Depois processa o pool na ordem gravada
até reunir a meta de problemas `complete`.

| Opção | Padrão | Efeito |
|---|---|---|
| `--target N` | `200` | meta de problemas completos |
| `--workers N` | `max(1, cpu_count // 2)` | processos paralelos por problema; não altera o resultado |
| `--problem ID` | — | processa só este problema (ignora a meta); útil para triagem |

Comportamento: pula problemas já encerrados; refaz `building/`; falha de AC ⇒ registra
`pending_triage` e segue (FR-011b); WA insuficientes ⇒ `discarded`; `InfraError` ⇒ nova
tentativa limitada e, persistindo, o problema permanece em `building/` e o comando termina com
código `3` (nunca vira veredito). Ao final, escreve o relatório e sai com `0` se a meta foi
atingida (problemas em `pending_triage` não mudam o código: a triagem manual é adiada, D17) e
com `1` se houver déficit; nesse caso, e só nele, os problemas em triagem passam a exigir
inspeção individual. Códigos: sem `pool.json` sai com `1`
(rode `extract`); `--problem` fora do pool sai com `2`. Em `--problem`, o código é `0` só se o
problema terminou `complete`. Um problema já encerrado nunca é refeito (apague a pasta para
reprocessá-lo). Efeitos além de `problems/`: `reports/selfcheck.json` (resultado do `selfcheck`),
`reports/validation_log.jsonl` (uma linha JSON por problema, com o estado, as contagens de
candidatas por resultado e o tempo; não é determinístico e não é empacotado) e
`reports/extraction_report.{json,md}` regerado.

### `audit` (serviço `sandbox`)

Reexecuta o motor (FR-015a): `AC_ref` primeiro, depois as WAs, e compara com o
`validacao.json`.

| Opção | Padrão | Efeito |
|---|---|---|
| `--problem ID` (repetível) | todos os `complete` | escopo da auditoria |

Falha do AC ⇒ interrompe aquele problema, grava `triage` (estágio `audit`, com o veredito do
motor) e muda o `status` para `pending_triage`; a lista `wa` do `validacao.json` é esvaziada (as
WAs não são avaliadas) e os arquivos da pasta permanecem para inspeção.

**Divergência em WA (decisão D18, 2026-09-22)**: uma WA cujo veredito ou teste decisivo mudou em
relação ao registrado **é reparada automaticamente**, não apenas reportada. A auditoria de 2026-09-21
achou 13 WA (em 12 dos 200 problemas) cujo comportamento não se reproduzia; a inspeção do
código-fonte mostrou a causa: acesso fora dos limites de um vetor, variável não inicializada ou
tempo de execução no limiar do limite — comportamento indefinido ou de fronteira, cujo resultado
exato depende de coisas fora da entrada (o conteúdo da memória, a variação de tempo do sistema), não
da lógica do candidato. Um candidato assim é um mau "gabarito" para as métricas, que pressupõem uma
falha fixa e reprodutível. A auditoria substitui cada WA divergente pelo **próximo candidato não
tentado, na mesma ordem determinística da seleção original** (`wa.select_candidates`, FR-014),
exigindo dele uma confirmação mais forte que a original: três checagens de estabilidade
independentes (2 execuções cada), ou seja, 6 execuções concordantes antes de aceitar, contra as 2
da seleção original. Repete até achar um candidato que passe, ou esgota os candidatos não tentados
e falha explicitamente (nenhum reparo silencioso). **Correção de 2026-09-22**: a primeira versão
comparava só as duas últimas de três chamadas e gravava uma quarta chamada nunca conferida contra
nada; corrigida para exigir que todas as passadas concordem com a primeira (ver spec D18 e
metodologia 1.4 para os detalhes). O número de WA continua exatamente 100, na mesma
numeração (`WA_<n>.cpp`), e nenhum outro arquivo do problema é tocado. Só depois disso, se ainda
houver problema sem solução (auditoria com AC divergente, ou reparo esgotado), o comando termina
com código `1`; um reparo bem-sucedido não conta como divergência. Só os problemas `complete` são
auditados. Ao final, regera o relatório.

### `report` (serviço `app`)

Regenera `reports/extraction_report.{json,md}` a partir de `staging/pool.json` e
`problems/*/validacao.json`, sem executar nada. Inclui alertas de FR-018a (só quando a seleção
é final: meta atingida ou todos os problemas do pool encerrados) e a lista de triagem. Sem
`pool.json`, sai com código `1`.

### `package` (serviço `app`)

Constrói `data/dataset.zip` de forma determinística com todos os problemas `complete` e grava
`manifests/dataset.manifest.json` e `manifests/extraction_report.json`. Recusa empacotar se a
meta não foi atingida, exceto com `--allow-partial`. Emite aviso se o zip passar de 95 MB
(limite de 100 MB por arquivo do GitHub).

### `verify` (serviço `app`) e `scripts/verify_dataset.py`

`python scripts/verify_dataset.py` é um invólucro fino sobre `dataset.integrity.verify()`.

| Opção | Padrão | Efeito |
|---|---|---|
| `--zip PATH` | `data/dataset.zip` | pacote a verificar |
| `--manifest PATH` | `manifests/dataset.manifest.json` | manifesto |
| `--extracted DIR` | — | além do zip, verifica a árvore extraída (`data/dataset/`) arquivo a arquivo |

Saída: lista de arquivos `changed`, `missing` e `extra` (FR-028) e a linha final `OK` ou
`FAIL`. Código `0` íntegro; `1` divergente. Deve funcionar logo após clonar o repositório, sem
extração prévia (verifica o zip).

## Arquivos produzidos (contrato de leitura para módulos futuros)

Fonte de verdade para consumo: a árvore `data/dataset/problems/<problem_id>/` obtida com
`unzip data/dataset.zip -d data/`. Formatos: ver [file-formats.md](./file-formats.md) e
[data-model.md](../data-model.md). Módulos futuros MUST ler só problemas cuja
`validacao.json.status == "complete"` e MUST validar os arquivos com os mesmos modelos
Pydantic (`dataset.schemas`).
