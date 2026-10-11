# Quickstart: validar o módulo de dataset ponta a ponta

**Feature**: `001-dataset-extraction` | Contratos: [cli.md](./contracts/cli.md),
[engine-api.md](./contracts/engine-api.md), [file-formats.md](./contracts/file-formats.md).

Este guia descreve como provar que o módulo funciona, do mais barato ao mais caro. Os comandos
só passam a existir depois da implementação (`/speckit-implement`); aqui ficam como roteiro de
aceite. Nenhum comando executa código C++ de terceiros no host: tudo roda no contêiner
(Constitution, Princípio II e V).

## Pré-requisitos

> Para quem não conhece Docker: o [README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
> tem o guia completo, do clone ao primeiro comando, com a explicação de cada passo abaixo (por
> exemplo, o que são `HOST_UID` e `HOST_GID`). Este roteiro é o de aceite da feature, mais enxuto.

- Docker com Compose v2 e acesso à internet apenas para o `build` e para o comando `extract`.
- Um clone do repositório na branch da feature.
- (Opcional) `HF_TOKEN` em `.env` (copie de `.env.example`) para limites de requisição maiores.
  O dataset é público; o token não é obrigatório.

## Nível 0 — Ambiente reprodutível

```bash
cp .env.example .env    # ajuste HOST_UID e HOST_GID (saída de `id -u` e `id -g`)
mkdir -p data           # sem isto o Docker cria data/ como root e o serviço `app` não grava nele
docker compose build
docker compose run --rm sandbox g++ --version      # esperado: g++ (GCC) 13.2.0
docker compose run --rm sandbox python --version   # esperado: Python 3.11.16
docker compose run --rm app ruff check . && docker compose run --rm app black --check .
```

Esperado: imagem constrói a partir do `uv.lock` sem resolver dependências novas, também em um
clone limpo; versões idênticas às fixadas; lint e formatação limpos. Laço de desenvolvimento:
editar um arquivo no host e rodar `docker compose run --rm sandbox pytest` enxerga a edição sem
rebuild (`docker-compose.override.yml`), e `black`/`ruff --fix` alteram o working tree, com os
arquivos pertencendo ao usuário do host.

## Nível 1 — Suíte de testes do módulo (sem rede, sem dataset)

```bash
docker compose run --rm sandbox pytest
```

Esperado: todos os testes passam, incluindo (Princípio VI) conversão bytes→KiB do limite de
pilha; macrocategoria pela regra de prioridade (cinco exemplos da metodologia); AC divergente
registrado em `validacao.json` e problema interrompido; retomada sem duplicar; manifesto que
bate após regenerar o zip; verificação que falha ao alterar, remover ou acrescentar arquivo;
`data/work/` com permissão `0700` e código de terceiros sem acesso a ele; e o script de
conformidade da documentação (`tests/docs`). Cobre US1, US2 (motor), US3 (validação), US4 (retomada), US5 (integridade) sobre fixtures
pequenas.

## Nível 2 — Motor contra programas de veredito conhecido (FR-010a, SC-013)

```bash
docker compose run --rm sandbox python -m dataset selfcheck
```

Esperado: código de saída `0`; relatório com um caso por veredito (`AC`, `WA`, `TLE`, `MLE`,
`RE`, `CE`), recursão profunda passando com o limite de pilha de 256 MiB, recuo na cascata de
padrões e repetição estável. Este é também o portão de entrada do comando `validate`.

## Nível 3 — Fumaça com poucos problemas

```bash
docker compose run --rm app     python -m dataset extract --limit-rows 400
docker compose run --rm sandbox python -m dataset validate --target 2
docker compose run --rm app     python -m dataset report
```

Esperado: `data/work/staging/pool.json` com funil por critério de rejeição (FR-005); dois
problemas `complete` em `data/work/problems/` (cada um com `enunciado.md`, `AC_ref.cpp`,
`WA_1..100.cpp`, `testes.json`, `metadata.json`, `validacao.json`); relatório com
distribuição por macrocategoria e, se aplicável, o alerta de menos de 30 problemas por
categoria (FR-018a).

**Piloto de viabilidade (recomendado antes da execução completa, [research.md](./research.md)
R19)**: depois do motor pronto, `validate --target 10` sobre problemas do `train` e leia no
relatório quantos candidatos viraram WA, TLE, MLE, RE e CE. Se a fração de WA for baixa, a
meta de 200 problemas com exatamente 100 WAs pode não fechar; melhor saber antes das ~5 h de
execução completa. Leia também `ac_tested` e `triage_by_cause`: se mais de 10% dos ACs
testados forem reprovados por formatação (`format_only`) ou por `TLE`, a regra de comparação de
saída ou a de tempo é reaberta (D13; metodologia 1.4) e a execução completa não segue.

Prova de retomada (SC-006): interrompa `validate` com Ctrl+C no meio de um problema e execute o
mesmo comando de novo; o conjunto final é idêntico ao de uma execução sem interrupção, sem
pastas duplicadas nem arquivos truncados.

## Nível 4 — Triagem de AC (FR-011b, SC-015)

Com um problema propositalmente inconsistente em fixture (AC que diverge do gabarito):

```bash
docker compose run --rm sandbox python -m dataset validate --problem <ID_DA_FIXTURE>
```

Esperado: código de saída `1`; `data/work/problems/<ID>/validacao.json` com
`status: "pending_triage"` e `triage` contendo identificador, motivo e saída divergente; o
problema não conta para a meta, não entra no pacote e não é refeito ao reexecutar.

## Nível 5 — Execução completa e empacotamento

```bash
docker compose run --rm app     python -m dataset extract
docker compose run --rm sandbox python -m dataset validate            # meta: 200
docker compose run --rm sandbox python -m dataset audit               # reexecução (FR-015a)
docker compose run --rm app     python -m dataset package
docker compose run --rm app     python -m dataset verify
```

Esperado (SC-001 a SC-015; o SC-016 é coberto no Nível 7): 200 problemas `complete` (ou déficit exato no relatório); auditoria
sem divergência; `data/dataset.zip` e `manifests/dataset.manifest.json` gerados; verificação
com `OK`. Reempacotar o mesmo conjunto produz o mesmo hash de zip (SC-008).

Depois de `package`, os módulos futuros consomem o dataset assim:

```bash
unzip data/dataset.zip -d data/            # cria data/dataset/problems/<problem_id>/
python -m dataset verify --extracted data/dataset
```

> **Sobre a triagem**: problemas em `pending_triage` são esperados (cerca de 1 em cada 5 no
> piloto) e **não são inspecionados** se a meta de 200 for atingida (D17). Só com déficit ao fim
> do pool eles passam a exigir inspeção individual. O roteiro completo de quem executa está em
> `src/dataset/README.md`, seção "Roteiro da execução completa".

## Nível 6 — Integridade pós-clonagem (US5, SC-009)

> Este nível é o fluxo de quem **recebe** o dataset (o autor que não o gerou). A explicação geral do
> ciclo está no README da raiz, seção "Como o dataset circula entre os autores".

Em um clone novo, sem rodar extração:

```bash
docker compose run --rm app python -m dataset verify           # verifica o zip
unzip data/dataset.zip -d data/
docker compose run --rm app python -m dataset verify --extracted data/dataset
```

Esperado: `OK`. Altere um byte de qualquer arquivo extraído (e, em outro teste, apague ou
acrescente um arquivo): a verificação termina com `FAIL` e aponta o arquivo em `changed`,
`missing` ou `extra`.

## Nível 7 — Documentação (Constitution, Princípio XI; FR-031, FR-032, SC-016)

É a revisão que fecha a feature, agora com gate executável:

```bash
docker compose run --rm app python scripts/check_docs_sync.py --closing \
  --module src/dataset --module src/sandbox      # esperado: saída 0
```

O script confere (C1 a C6): os READMEs de `src/dataset/` e `src/sandbox/` têm as seis seções na
ordem de [`docs/template-modulo.md`](../../docs/template-modulo.md) e o propósito em uma frase;
todo comando documentado existe na CLI e consta verificado (data e revisão), sem linha
`pendente`; os links resolvem; o `README.md` da raiz descreve os dois módulos e a frase "Estado
atual" concorda com os READMEs existentes; toda decisão D# da spec tem linha em
`specs/001-dataset-extraction/sync-matrix.json` (criado no T021) e seus termos aparecem em
[`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md); nenhuma `[PROPOSTA]` ativa
resta. Depois, os itens da lista de conformidade do template que o script não decide (propósito
que realmente descreve o módulo, limitações reais, `--help` e docstrings coerentes).

## Critérios de saída da validação

O módulo está pronto para `/speckit-converge` quando: os níveis 1 e 2 passam; o nível 3
comprova retomada segura; o nível 4 comprova a triagem; a execução completa (níveis 5 e 6)
está registrada no relatório versionado; e o nível 7 (documentação) está cumprido.

## Resultado da validação (T097, 2026-09-22)

Todos os níveis passaram; nenhum bloqueou a feature.

| Nível | O que foi verificado | Resultado | Quando |
|---|---|---|---|
| 0 — Ambiente reprodutível | `docker compose build`, versões fixadas de GCC/Python, laço de desenvolvimento (edição sem rebuild, `black`/`ruff --fix` no host) | OK, reconfirmado ao longo da feature | 2026-09-19 (T010) |
| 1 — Suíte de testes do módulo | `docker compose run --rm sandbox pytest` (unidade + integração) | **649 testes, 0 falhas** | 2026-09-22 (execução mais recente) |
| 2 — Motor contra programas de veredito conhecido | `python -m dataset selfcheck` | `9/9` casos, código `0`, estável | 2026-09-21 (T049); repetido a cada `validate` |
| 3 — Fumaça com poucos problemas + prova de retomada (SC-006) | `extract --limit-rows` + `validate --target 2` (fumaça, T034); interrupção de propósito com `SIGTERM` no meio de um problema e retomada com o mesmo comando | Fumaça OK; retomada confirma SC-006 integralmente (mesmo problema `complete`, 0 pastas duplicadas, 0 arquivos truncados); achado D19 (campo medido `max_cpu_time_s` varia por ruído de hardware, não a seleção) | 2026-09-22 (T080) |
| 4 — Triagem de AC (FR-011b, SC-015) | `validate --problem <ID>` sobre um problema cujo AC diverge; também observado 43 vezes na execução real (D8, D17) | Código `1`, `validacao.json` com `status: pending_triage` e `triage` completo; problema fora da amostra e não refeito | Testes automatizados (T056) + execução real, 2026-09-21 (T072) |
| 5 — Execução completa e empacotamento | `extract`, `validate`, `audit`, `package`, `verify` (na época, `scripts/verify_dataset.py`, removido em 2026-09-25) sobre o dataset real | 1.234 elegíveis (T035); 200 de 200 completos em 5 h 06 min (T072); `audit` convergiu em 4 rodadas, a última sem reparo (T072/D18); `data/dataset.zip` real, 200 problemas, 12.891.474 bytes ≈ 12,3 MiB, `OK` na verificação (T093); reempacotar dá o mesmo hash (SC-008, confirmado em teste automatizado) | 2026-09-20 a 2026-09-22 |
| 6 — Integridade pós-clonagem (SC-009) | `verify` (na época `verify_dataset.py`) no zip; `unzip` e a alternativa `python -m zipfile -e` (árvores idênticas); `--extracted`; byte alterado, arquivo removido, arquivo extra | `OK` no estado íntegro; `FAIL` apontando corretamente o arquivo em `changed`/`missing`/`extra` nos três casos testados de propósito | 2026-09-22 (T094) |
| 7 — Documentação (Princípio XI, FR-031, FR-032, SC-016) | `check_docs_sync.py --closing --module src/dataset --module src/sandbox` (C1 a C6, CV) | Sai com `0`; nenhuma linha `pendente`; `src/dataset/README.md` passa a `Status: implementado`; todas as decisões D1–D19 com linha em `sync-matrix.json` e termos na metodologia | 2026-09-22 (T098/T099) |

**Conclusão**: a feature `001-dataset-extraction` está pronta para `/speckit-converge` pelos
critérios acima; os itens que faltam (T102, revisão humana do código gerado com IA antes do
merge) são de responsabilidade dos autores, não do roteiro de validação técnica.
