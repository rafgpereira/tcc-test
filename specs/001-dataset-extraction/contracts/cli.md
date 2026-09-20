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

Executa a suíte de programas de veredito conhecido contra o motor (FR-010a). Código `0` só se
todos os vereditos coincidirem. Sem opções.

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
atingida e não há triagem pendente novo; `1` caso contrário.

### `audit` (serviço `sandbox`)

Reexecuta o motor (FR-015a): `AC_ref` primeiro, depois as WAs, e compara com o
`validacao.json`.

| Opção | Padrão | Efeito |
|---|---|---|
| `--problem ID` (repetível) | todos os `complete` | escopo da auditoria |

Falha do AC ⇒ interrompe aquele problema, grava `triage` (estágio `audit`) e muda o `status`
para `pending_triage`. Divergência em WA ⇒ apenas reportada. Código `1` se houver qualquer
divergência.

### `report` (serviço `app`)

Regenera `reports/extraction_report.{json,md}` a partir de `staging/pool.json` e
`problems/*/validacao.json`, sem executar nada. Inclui alertas de FR-018a e a lista de
triagem.

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
