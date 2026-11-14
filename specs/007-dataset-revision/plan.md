# Implementation Plan: Revisão 2 do dataset (enunciados corrigidos)

**Branch**: `007-dataset-revision` (feature do spec-kit; o trabalho acontece na `main`, Princípio X)
| **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-dataset-revision/spec.md`

## Summary

**Comandos novos:**
- **`python -m dataset revise`** (`app`) — gera a revisão 2. Os passos estão detalhados abaixo e
  em [research.md](./research.md) R1 a R8.
- **`python -m ai_clients package --merge-from data/suites/slm-rev1`** — empacota a execução nova
  do SLM com as combinações não afetadas da execução da revisão 1 (F2). O pacote final
  `data/slm_suites.zip` traz um `provenance.json` com a origem de cada combinação (R6).

**O que o `revise` faz:**
1. **Confere as entradas.** O dataset extraído tem de ser a revisão 1 do manifesto atual. O
   relatório da 006 tem de ter sido feito com esse dataset.
2. **Monta os corrigidos de novo, em memória.** Usa o mesmo código da 006, a partir das entradas
   versionadas (relatório e pacote dos originais), e não a partir da pasta não versionada
   `data/statements/corrected/`. Cada corrigido passa de novo nas três conferências.
3. **Lê as 15 decisões** de `manifests/statement_decisions/<id>.json` (F1) e confere cada uma: a
   mudança tem de ficar dentro das diferenças que o relatório aponta para aquele problema.
4. **Guarda a revisão 1.** Renomeia `data/dataset.zip` para `data/dataset.rev1.zip` e o manifesto
   para `manifests/dataset.rev1.manifest.json`, com os bytes intactos (F3).
5. **Empacota a revisão 2.** Usa o mesmo empacotamento determinístico, a partir de uma cópia da
   revisão 1 com os `enunciado.md` trocados. Grava o manifesto novo (`schema_version` 2, com a
   proveniência da revisão) e `manifests/dataset_revision.json`, com a lista do que mudou e por quê.
6. **Confere o resultado (FR-002).** Arquivo por arquivo, a revisão 2 só pode diferir da 1 nos
   `enunciado.md` alterados.
7. **Imprime o próximo passo:** descompactar a revisão 2 e a lista das combinações afetadas do SLM.

**O que vem depois, fora do `revise`:**
- **SLM:** a execução da revisão 1 é movida, intocada, para `data/suites/slm-rev1`. Uma execução
  nova da revisão 2, em `data/suites/slm`, roda só as combinações afetadas
  (`generate --problem … --scenario black_box --scenario hybrid`).
- **Mutantes:** intactos; só `python -m mutation verify` é rodado. O `mutation report` não foi regenerado (emenda de F4, decisão de Milena em 2026-10-18).
- **Emenda da constitution (S1):** vem **antes** de tudo.

## Sinalizações e decisões

| # | Lacuna encontrada ao planejar | O que o plano faz | Decisão |
|---|---|---|---|
| **S1** | O Princípio II diz "após a extração e validação **únicas**"; a revisão 2 contraria o texto (FR-008). | Proposta de emenda **1.8.0** (texto em research R1): o dataset MAY ter revisões numeradas quando uma conferência automática contra a fonte original demonstrar perda; cada revisão MUST mudar só o que a conferência justifica, guardar a anterior com o manifesto, registrar a proveniência e fazer as suítes dizerem a revisão usada. | **Aprovada em 2026-10-18 (Milena), como proposta; aplicada: constitution 1.8.0.** |
| **S2** | O manifesto atual exige `dataset_zip.path == "data/dataset.zip"` e não tem campo de revisão. | `Manifest` ganha `schema_version` 2 com `revision` e `revision_of` (proveniência da revisão, que não entra em nenhum hash); a revisão 1 guardada continua com o manifesto de `schema_version` 1, byte a byte (R4). | — (informativo; Princípio IV) |
| **S3** | O `suite.json` do SLM não tem campo de origem, e mudar o schema das 600 suítes empacotadas é caro. | A origem por combinação vai num `provenance.json` do pacote final, não no `suite.json`; o `cli check` confere que cada combinação do pacote está nele (R6). | — (informativo) |
| **S4** | O `manifests/mutation_report.json` já aponta para um manifesto de dataset anterior ao atual (`6b3628c3…`, contra `a092d987…`), achado ao planejar. | O relatório dos mutantes **não** foi regenerado (decisão de Milena, 2026-10-18): os mutantes só dependem do `AC_ref.cpp`, que não mudou, e o relatório guarda o manifesto da época da geração. A divergência está registrada na metodologia (1.6.1). | — (achado; decidido: manter o relatório) |

## Technical Context

**Language/Version**: Python 3.11 (o da imagem).

**Primary Dependencies**: **nenhuma nova**; reaproveita `dataset.statements.*` (006),
`dataset.integrity.packaging/manifest/verify`, `ai_clients.packaging`.

**Storage**:
- versionados:
  - `data/dataset.zip` (revisão 2) e `manifests/dataset.manifest.json` (`schema_version` 2);
  - `data/dataset.rev1.zip` e `manifests/dataset.rev1.manifest.json` (a revisão 1, intocada);
  - `manifests/dataset_revision.json`;
  - `manifests/statement_decisions/<id>.json` (os 15; pasta plana);
- não versionados:
  - `data/work/revision2/` (temporário);
  - `data/suites/slm-rev1/` (a execução anterior, movida).

**Testing**: `pytest` no `sandbox`, com datasets sintéticos (como na 006) e decisões de teste.

**Target Platform**: `app` para `revise`, `generate` e `package`; `sandbox` para o `execute` do
SLM.

**Project Type**: pipeline de linha de comando; subcomando novo no `dataset`, opção nova no
`package` do `ai_clients`, ajustes no `cli check`.

**Performance Goals**: nenhuma; o tempo da execução nova do SLM (as combinações afetadas) é
medido.

**Constraints**:
- FR-002 (byte a byte igual fora dos `enunciado.md`);
- FR-004 (recusa sem gravar nada);
- a revisão 1 nunca é alterada (F3).

**Scale/Scope**: 200 problemas; 102 corrigidos automaticamente + até 15 manuais. As combinações
afetadas do SLM são 2 por problema que muda: 204 a 234.

## Constitution Check

*GATE: antes da Fase 0 e revisto depois da Fase 1.* Constitution 1.7.1 (com a emenda 1.8.0
proposta em S1).

| Princípio | Como o plano cumpre | Status |
|---|---|---|
| I. Metodologia mutável | Decisões D1–D3, F1–F4, S1–S4 registradas na seção 1.6.1 e no histórico | ✅ |
| II. Reprodutibilidade | Emenda 1.8.0 aplicada (S1): o princípio permite revisões numeradas com quatro obrigações. Com ela, a revisão 2 é determinística a partir de entradas versionadas (revisão 1, relatório, pacote dos originais, decisões), a revisão 1 fica guardada e as suítes dizem a revisão usada | ✅ (emenda 1.8.0) |
| III. Sem estado | Não muda: os pedidos aos modelos continuam sem estado | ✅ |
| IV. Contratos versionados | `Manifest` vai a `schema_version` 2 (S2); `dataset_revision.json`, as decisões e `provenance.json` com schema | ✅ |
| V. Sandboxing | Nada novo é executado; o `execute` do SLM continua no `sandbox` | ✅ |
| VI. Testa a si próprio | Testes da geração, das recusas, das decisões, da junção do pacote e do `cli check` (R8) | ✅ |
| VII. Retomada | O `revise` grava atomicamente e no fim (nada pela metade); a execução nova do SLM retoma como sempre | ✅ |
| VIII. Custo/uso de IA | Os modelos comerciais ainda não rodaram: custo extra zero; o SLM refaz só o afetado | ✅ |
| IX. Simplicidade | Reaproveita o código da 006 e o empacotamento existentes; origem num arquivo do pacote em vez de mudar o schema das suítes (S3) | ✅ |
| X. Revisão humana | As 15 decisões são dos autores; a emenda é dos autores; o agente não roda Git | ✅ |
| XI. Documentação viva | README do `dataset` e do `ai_clients`, referência da raiz, `CLAUDE.md` (o dataset agora tem revisão), `docs/verificacao-consistencia.md` (a camada do SLM com origem) | ✅ |

**Gate**: passou depois da emenda 1.8.0, aprovada e aplicada em 2026-10-18.

## Project Structure

```text
specs/007-dataset-revision/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md  sync-matrix.json
├── contracts/cli.md
└── checklists/requirements.md
src/dataset/
├── __main__.py              # + subcomando revise
├── revision.py              # novo: entradas, decisões, montagem, conferências, empacotamento
├── schemas/manifest.py      # Manifest schema_version 2 (revision, revision_of)
├── schemas/revision.py      # novo: StatementDecision, DatasetRevision
└── integrity/packaging.py   # empacotar a partir de uma pasta de problemas qualquer
src/ai_clients/
├── packaging.py  __main__.py   # package --merge-from: junção com provenance.json
src/cli/consistency.py       # camada do SLM aceita a junção; o dataset tem revisão
.specify/memory/constitution.md   # emenda 1.8.0 (S1), depois da aprovação
tests/dataset/test_revision.py  tests/ai_clients/test_package_merge.py  tests/cli/test_consistency.py
manifests/statement_decisions/<id>.json    # os 15, escritos pelos autores (F1)
```

## Complexity Tracking

| Ponto | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Uma segunda revisão do dataset, contra o texto atual do Princípio II | A conferência da 006 mediu perda de conteúdo em 117 dos 200 enunciados | Manter a revisão 1 deixaria os modelos lendo `n ≤ 105` no lugar de `10^5`; decisão dos autores em 2026-10-18 |
| O pacote final do SLM junta duas execuções | D2/F2: refazer só o afetado | Refazer as 600 (rejeitado em D2) ou copiar sem origem (rejeitado em F2) |
