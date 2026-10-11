# Quickstart: validar o módulo de mutação ponta a ponta

**Feature**: `002-mutant-generation` | Contratos: [cli.md](./contracts/cli.md),
[mutation-api.md](./contracts/mutation-api.md), [file-formats.md](./contracts/file-formats.md).

Este guia descreve como provar que o módulo funciona, do mais barato ao mais caro. Os comandos
só passam a existir depois da implementação (`/speckit-tasks` + `/speckit-implement`); aqui
ficam como roteiro de aceite. Nenhum comando executa código C++ de terceiros no host — tudo roda
no contêiner (Constitution, Princípios II e V).

## Pré-requisitos

- O ambiente já preparado conforme o [README da raiz](../../README.md) (mesmo ambiente do
  módulo de dataset — nenhuma imagem nova).
- `data/dataset.zip` já descompactado em `data/dataset/` (`unzip data/dataset.zip -d data/`) e
  verificado (`docker compose run --rm app python -m dataset verify`) — este módulo se
  recusa a rodar sobre um dataset não verificado (FR-010).

## Nível 0 — Dependência nova

```bash
docker compose run --rm app python -c "import tree_sitter, tree_sitter_cpp; print('ok')"
```

Esperado: `ok`, sem erro de import, confirmando que `uv add tree-sitter tree-sitter-cpp` (feito
na implementação) reconstruiu a imagem com a dependência pinada no `uv.lock`.

## Nível 1 — Suíte de testes do módulo (sem gerar mutantes de verdade)

```bash
docker compose run --rm sandbox pytest tests/mutation
```

Esperado: todos os testes passam, cobrindo (Princípio VI): detecção de sítios sobre os dois
casos reais de risco (`vector<pair<int,string>>>` não gera sítio; `x >> 1` gera; string/comentário
com `<`/`>>` dentro nunca geram sítio); aplicação de cada operador (ROR/AOR/LCR/ABS/UOI);
truncamento determinístico quando há mais de 100 sítios (FR-003a); geração de ordem superior em
pares/trios na ordem determinística; a regra de estabilidade de 6 execuções (com um motor falso
que simula um veredito instável, como já existe para o módulo de dataset); empacotamento e
verificação de integridade (byte alterado, arquivo removido, arquivo extra — mesmos três casos
já cobertos para o dataset).

## Nível 2 — Gerar mutantes de um único problema real

```bash
docker compose run --rm sandbox python -m mutation generate --problem 1000_B
ls data/mutants/problems/1000_B/ | wc -l   # esperado: 101 (100 mutantes + generation.json)
docker compose run --rm app python -m mutation report
cat manifests/mutation_report.json
```

Esperado: até 100 arquivos `Mutant_<n>.cpp`; o relatório mostra a distribuição por ordem e por
operador para este problema, e nenhum alerta de exclusão (a menos que este problema específico
seja um dos raros casos previstos em D4/FR-009).

## Nível 2b — Interromper e retomar (Princípio VII)

```bash
docker compose run --rm sandbox python -m mutation generate --workers 2 --problem 630_G --problem 719_A
# em outro terminal, depois de ~1 min:  docker kill --signal=SIGINT <nome do contêiner>
# ...termina em ~1 s, código 130; nada em data/mutants/problems/ pela metade
docker compose run --rm sandbox python -m mutation generate --problem 630_G --problem 719_A
```

Esperado: a segunda execução termina os dois problemas; o que já estava fechado antes de
interromper aparece como `already generated, skipped` e não é tocado (ver research.md, R19).

## Nível 3 — Piloto sobre uma amostra pequena (mede o R4 do research.md; resolvido em R18)

```bash
docker compose run --rm sandbox python -m mutation generate --problem 1000_B --problem <outro_id_denso>
```

Esperado: tempo e taxa de sucesso de ordem superior registrados na saída, para decidir (na
implementação) se um orçamento de tentativas é necessário — ver research.md, R4. Este nível não
é sobre corretude, é sobre a medição que falta antes de rodar os 200 problemas.

## Nível 4 — Execução completa e empacotamento (roteiro da rodada final)

Só para a execução que vai sustentar os números publicados. Tudo abaixo roda no computador de quem
faz a execução, dentro do diretório do repositório. Tempo estimado (extrapolação, **não medida** para
os 200): ~12 h com `--workers 4`, medido em 8 problemas de testes pequenos (`research.md` R14).

**1. Código commitado e ambiente limpo** (os artefatos ficam ligados ao commit que os versionar):

```bash
git status --short src scripts pyproject.toml uv.lock Dockerfile docker-compose.yml docker-compose.override.yml   # vazio
git rev-parse --short=7 HEAD          # anote: é o commit do código desta execução
ls data                               # sem `mutants` nem `mutants.zip`
df -h . | tail -1                     # com pelo menos 5 GB livres
```

**2. Verificações prévias** (~5 min):

```bash
docker compose build
docker compose run --rm sandbox pytest                               # todos passam (933 em 2026-09-24)
docker compose run --rm sandbox python -m dataset selfcheck          # selfcheck OK: 9/9 cases
docker compose run --rm app python -m dataset verify --extracted data/dataset   # OK
docker compose run --rm app python scripts/check_docs_sync.py        # OK
```

**3. Geração** (horas; num `tmux`/`screen`, computador na tomada e sem suspender):

```bash
set -o pipefail
systemd-inhibit --what=sleep:idle --why="geracao de mutantes" \
  docker compose run --rm sandbox python -m mutation generate --workers 4 \
  2>&1 | tee -a ~/mutantes-generate.log
echo "exit=${PIPESTATUS[0]}"
```

Esperado: uma linha `[k/200] <id>: generating` por problema em andamento e, ao terminar cada um,
`[k/200] <id>: 100 mutants (by order: {...}); discarded: {...}; N s`. Nada aparece por vários
minutos no começo (cada problema leva ~5 a 15 min, 4 em paralelo). Acompanhar em outro terminal:
`ls data/mutants/problems | wc -l` (sobe até 200). Fim esperado: `done: 200 generated, 0 skipped,
E excluded` e `exit=0`. Interromper (Ctrl+C) e rodar o **mesmo comando** de novo é seguro.

**4. Conferir a geração:**

```bash
ls data/mutants/problems | wc -l                                    # 200
ls data/mutants/building 2>/dev/null | wc -l                        # 0
grep -c "DAMAGED" ~/mutantes-generate.log                           # 0
grep "ALERT" ~/mutantes-generate.log                                # ideal: nenhuma linha
for d in data/mutants/problems/*; do [ "$(ls $d | wc -l)" != 101 ] && echo "$d: $(ls $d | wc -l) arquivos"; done   # só excluídos (1 arquivo)
```

**5. Relatório, pacote e verificação:**

(antes, confira o conjunto: `docker compose run --rm app python -m cli check`;
esperado `Resultado: OK`, com `200/200` em cada linha e um aviso, o de que o manifesto dos mutantes
ainda não existe)

```bash
docker compose run --rm app python -m mutation report 
docker compose run --rm app python -m mutation package
docker compose run --rm app python -m mutation verify
sha256sum data/mutants.zip
docker compose run --rm app python -m mutation package >/dev/null
sha256sum data/mutants.zip                                          # o mesmo hash de antes
ls -lh data/mutants.zip                                             # abaixo de 95 MB (esperado: ~10 MB)
```

**6. Conferir o que o pacote entrega (como o outro autor o receberia):**

```bash
mkdir -p data/_check && unzip -q data/mutants.zip -d data/_check
docker compose run --rm app python -m mutation verify --extracted data/_check/mutants    # OK
diff -rq data/_check/mutants/problems data/mutants/problems | grep -v generation.json    # vazio
rm -rf data/_check
git status --short                                                  # só os 3 arquivos novos abaixo
docker compose run --rm app python -m cli check --deep   # OK, 0 falhas, 0 avisos (agora o manifesto existe)
```

Os três arquivos novos esperados: `data/mutants.zip`, `manifests/mutants.manifest.json`,
`manifests/mutation_report.json`. Commitá-los é decisão dos autores (Princípio X).

## Resultado da validação (2026-09-24, revisão `5c726d8+dirty`)

| Nível | Resultado |
|---|---|
| 0 — dependência | `import tree_sitter, tree_sitter_cpp` imprime `ok` no serviço `app` |
| 1 — suíte | `docker compose run --rm sandbox pytest`: **933 passaram**, 3 min (inclui os testes de integração com o motor real e o pool real) |
| 2 — um problema real | `generate --problem 189_C`: 100 mutantes, 795 s (execução dos autores, repetida sem divergência: `research.md` R15); `report` sobre 2 problemas reais gerou o JSON esperado; `ls data/mutants/problems/<id>` deu 101 |
| 2b — interromper e retomar | SIGINT em 1 s; SIGKILL depois de um problema fechado; retomada sem perda (`research.md` R19) |
| 3 — piloto | os três problemas mais esparsos fecham só com pares, 371 a 425 s (`research.md` R18); 8 problemas com `--workers 1` e `4`: 0 de 800 mutantes divergentes, 2,07× (`research.md` R14) |
| 4 — execução completa e empacotamento | **feito pelos autores em 2026-09-24/25**: `generate --workers 4` (200 problemas, ~7 h 26 min), `report`, `package` (zip de 9,06 MiB), `verify` `OK`, `python -m cli check --deep` `OK` com 0 avisos (`research.md` R21 e R23) |
