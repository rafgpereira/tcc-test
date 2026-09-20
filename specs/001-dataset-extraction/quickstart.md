# Quickstart: validar o módulo de dataset ponta a ponta

**Feature**: `001-dataset-extraction` | Contratos: [cli.md](./contracts/cli.md),
[engine-api.md](./contracts/engine-api.md), [file-formats.md](./contracts/file-formats.md).

Este guia descreve como provar que o módulo funciona, do mais barato ao mais caro. Os comandos
só passam a existir depois da implementação (`/speckit-implement`); aqui ficam como roteiro de
aceite. Nenhum comando executa código C++ de terceiros no host: tudo roda no contêiner
(Constitution, Princípio II e V).

## Pré-requisitos

- Docker com Compose v2 e acesso à internet apenas para o `build` e para o comando `extract`.
- Um clone do repositório na branch da feature.
- (Opcional) `HF_TOKEN` em `.env` (copie de `.env.example`) para limites de requisição maiores.
  O dataset é público; o token não é obrigatório.

## Nível 0 — Ambiente reprodutível

```bash
docker compose build
docker compose run --rm sandbox g++ --version      # esperado: g++ (GCC) 13.2.0
docker compose run --rm sandbox python --version   # esperado: Python 3.11.16
docker compose run --rm app ruff check . && docker compose run --rm app black --check .
```

Esperado: imagem constrói a partir do `uv.lock` sem resolver dependências novas; versões
idênticas às fixadas; lint e formatação limpos.

## Nível 1 — Suíte de testes do módulo (sem rede, sem dataset)

```bash
docker compose run --rm sandbox pytest
```

Esperado: todos os testes passam, incluindo (Princípio VI) conversão bytes→KiB do limite de
pilha; macrocategoria pela regra de prioridade (cinco exemplos da metodologia); AC divergente
registrado em `validacao.json` e problema interrompido; retomada sem duplicar; manifesto que
bate após regenerar o zip; verificação que falha ao alterar, remover ou acrescentar arquivo.
Cobre US1, US2 (motor), US3 (validação), US4 (retomada), US5 (integridade) sobre fixtures
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
execução completa.

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
docker compose run --rm app     python scripts/verify_dataset.py
```

Esperado (SC-001 a SC-015): 200 problemas `complete` (ou déficit exato no relatório); auditoria
sem divergência; `data/dataset.zip` e `manifests/dataset.manifest.json` gerados; verificação
com `OK`. Reempacotar o mesmo conjunto produz o mesmo hash de zip (SC-008).

Depois de `package`, os módulos futuros consomem o dataset assim:

```bash
unzip data/dataset.zip -d data/            # cria data/dataset/problems/<problem_id>/
python scripts/verify_dataset.py --extracted data/dataset
```

## Nível 6 — Integridade pós-clonagem (US5, SC-009)

Em um clone novo, sem rodar extração:

```bash
docker compose run --rm app python scripts/verify_dataset.py           # verifica o zip
unzip data/dataset.zip -d data/
docker compose run --rm app python scripts/verify_dataset.py --extracted data/dataset
```

Esperado: `OK`. Altere um byte de qualquer arquivo extraído (e, em outro teste, apague ou
acrescente um arquivo): a verificação termina com `FAIL` e aponta o arquivo em `changed`,
`missing` ou `extra`.

## Nível 7 — Documentação (Constitution, Princípio XI; FR-031, FR-032, SC-016)

Sem código nem contêiner; é a revisão que fecha a feature:

1. `src/dataset/README.md` e `src/sandbox/README.md` existem e cumprem a lista de conformidade
   de [`docs/template-modulo.md`](../../docs/template-modulo.md) (seis campos; cada comando foi
   executado como escrito; `--help` e docstrings coerentes).
2. O `README.md` da raiz descreve os dois módulos, como se conectam e os comandos exatos para
   obter (`unzip` + verificação) ou regerar o dataset, e marca essas etapas como disponíveis.
3. Todo número medido e toda decisão da spec e do plano aparecem em
   [`docs/metodologia-referencia.md`](../../docs/metodologia-referencia.md), com linha nova no
   histórico (seção 8).

## Critérios de saída da validação

O módulo está pronto para `/speckit-converge` quando: os níveis 1 e 2 passam; o nível 3
comprova retomada segura; o nível 4 comprova a triagem; a execução completa (níveis 5 e 6)
está registrada no relatório versionado; e o nível 7 (documentação) está cumprido.
