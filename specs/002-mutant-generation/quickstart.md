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
  verificado (`docker compose run --rm app python scripts/verify_dataset.py`) — este módulo se
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

## Nível 3 — Piloto sobre uma amostra pequena (mede o R4 do research.md)

```bash
docker compose run --rm sandbox python -m mutation generate --problem 1000_B --problem <outro_id_denso>
```

Esperado: tempo e taxa de sucesso de ordem superior registrados na saída, para decidir (na
implementação) se um orçamento de tentativas é necessário — ver research.md, R4. Este nível não
é sobre corretude, é sobre a medição que falta antes de rodar os 200 problemas.

## Nível 4 — Execução completa e empacotamento (só para a rodada final do experimento)

```bash
docker compose run --rm sandbox python -m mutation generate
docker compose run --rm app python -m mutation package
docker compose run --rm app python -m mutation verify
git status --short data/mutants.zip manifests/mutants.manifest.json manifests/mutation_report.json
```

Quem **só recebe** o pacote (o outro autor, depois de `git pull`) não gera nada: apaga qualquer
`data/mutants/` de desenvolvimento, descompacta e confere —

```bash
rm -rf data/mutants
unzip data/mutants.zip -d data/
docker compose run --rm app python -m mutation verify --extracted data/mutants
```

— e passa a ler os mutantes do mesmo caminho que o autor que gerou: `data/mutants/problems/<id>/`.

Esperado: `generate` processa os 200 problemas (retomável se interrompido, R5); `package` recusa
rodar se houver `building/` pendente; `verify` confirma a integridade do zip recém-gerado;
`git status` mostra os três arquivos como `untracked` — a decisão de fato commitá-los (emenda
1.6.0 da Constitution) é sempre do autor, nunca automática (Princípio X), e só faz sentido na
execução que efetivamente vai sustentar os números publicados, não em toda rodada de
desenvolvimento.
