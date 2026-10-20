# Contrato da CLI: `dataset revise` e `ai_clients package --merge-from`

**Feature**: `specs/007-dataset-revision` | **Date**: 2026-10-18 | **Plan**: [../plan.md](../plan.md)

## 1. `python -m dataset revise`

```text
docker compose run --rm app python -m dataset revise [--draft-decisions] [--dry-run]
```

| Opção | Efeito |
|---|---|
| (nenhuma) | Gera a revisão 2 (research R2 a R5). |
| `--draft-decisions` | Grava, em `manifests/statement_decisions/<id>.json`, um rascunho para cada problema em revisão sem decisão: o texto atual, `decision: null` e as diferenças com os trechos do original. Não gera revisão. |
| `--dry-run` | Faz todas as conferências e imprime o que mudaria, sem gravar nada. |

**Saída**:

```text
revision 2: 117 statements changed (102 automatic, 15 manual), 0 kept, 83 unchanged; every other file identical
archived: data/dataset.zip -> data/dataset.rev1.zip; manifests/dataset.manifest.json -> manifests/dataset.rev1.manifest.json
written: data/dataset.zip, manifests/dataset.manifest.json (revision 2), manifests/dataset_revision.json
next: rm -rf data/dataset && unzip data/dataset.zip -d data/
slm affected: 234 combinations (black_box, hybrid of 117 problems); run:
  docker compose run --rm app python -m ai_clients generate --problem ... --scenario black_box --scenario hybrid
```

Os números da saída são **ilustrativos**.

**Códigos**:
- `0`: gravado, ou dry-run sem problema;
- `1`: alguma conferência falhou, nada foi gravado (dataset divergente, relatório de outro dataset,
  decisão faltando ou inválida, corrigido reprovado, outro arquivo mudaria);
- `2`: uso;
- `3`: infraestrutura.

Uma revisão 2 já gerada é recusada com `1` (`revision 2 already exists`).

## 2. `python -m ai_clients package --merge-from DIR`

```text
docker compose run --rm app python -m ai_clients package --merge-from data/suites/slm-rev1
```

Só para o SLM (`--model slm`, o padrão). As regras de junção são as de research R6 e as recusas
seguem o `package` atual (código `1`, com a lista do que falta).

**Saída**: além da do `package`:

```text
merged: 234 combinations from suites/slm (revision 2), 366 from suites/slm-rev1 (revision 1); provenance.json written
```

## 3. Comandos que mudam de comportamento

| Comando | Mudança |
|---|---|
| `python -m dataset verify` | Confere a revisão 2. A revisão 1, só como **auditoria**: `--zip data/dataset.rev1.zip --manifest manifests/dataset.rev1.manifest.json`. Conferir a integridade da revisão guardada é permitido; nenhum comando de geração, execução ou métrica a lê (constitution 1.8.0, obrigação b). |
| `python -m cli check` | A camada `slm_suites` aceita a junção, usando a árvore indicada em `provenance.json`. |
| `python -m mutation report` | Sem mudança de código; rodado de novo para apontar para a revisão 2 (F4). |
