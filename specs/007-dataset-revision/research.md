# Research: Revisão 2 do dataset

**Feature**: `specs/007-dataset-revision` | **Date**: 2026-10-18 | **Plan**: [plan.md](./plan.md)

## R1 — Emenda da constitution (S1, FR-008)

**Decision**: propor a versão **1.8.0**, acrescentando ao Princípio II, logo depois do parágrafo da
exceção do dataset:

> O dataset MAY ter **revisões numeradas** depois da primeira, somente quando uma conferência
> automática contra a fonte original demonstrar perda de conteúdo no dataset. Cada revisão MUST:
> (a) alterar apenas o que a conferência justifica, com cada alteração listada e a decisão humana
> registrada quando não for automática; (b) guardar a revisão anterior, pacote e manifesto, para
> auditoria, sem que nenhum comando a use; (c) registrar no manifesto a revisão e a sua
> proveniência; (d) fazer cada artefato derivado (suítes, relatórios) dizer de qual revisão veio.
> Uma revisão nunca é feita para melhorar resultados do experimento.

**Rationale**: mantém o espírito do princípio (o dataset é um artefato congelado e verificável) e
abre só o caso medido: perda de conteúdo comprovada contra a fonte.

**Alternatives considered**: não emendar e manter a revisão 1 (rejeitado pelos autores); emendar de
forma ampla ("o dataset pode mudar"), o que tiraria a garantia.

**Status**: aprovada por Milena em 2026-10-18, como proposta, e aplicada (constitution 1.8.0).

## R2 — As entradas do `revise` e as conferências antes de gravar (FR-001, FR-004)

**Decision**: o `revise` só aceita entradas versionadas e coerentes entre si:
1. `data/dataset/` confere com `manifests/dataset.manifest.json` (a revisão 1 extraída);
2. o `manifests/statement_fidelity_report.json` tem `dataset_manifest_sha256` igual ao hash desse
   manifesto;
3. o pacote `data/statement_originals.zip` confere com `manifests/statement_originals.manifest.json`;
4. cada um dos problemas em revisão no relatório tem uma decisão em
   `manifests/statement_decisions/<id>.json`.

Os corrigidos automáticos são **refeitos em memória** com o código da 006 (`corrected_text` e
`checks`), não lidos de `data/statements/corrected/` (não versionado). Qualquer falha recusa com o
código 1, sem gravar nada.

## R3 — As 15 decisões (F1)

**Decision**: um arquivo por problema, `manifests/statement_decisions/<id>.json`, numa pasta
plana, versionado:

| Campo | Regra |
|---|---|
| `problem_id` | um dos problemas em revisão no relatório |
| `decision` | `"correct"` ou `"keep"` |
| `enunciado` | o texto inteiro corrigido (só com `"correct"`) |
| `reason`, `reviewed_by`, `reviewed_at` | obrigatórios |
| `sha256_before` | hash do `enunciado.md` da revisão 1 (garante que a decisão é sobre esse texto) |

**Conferência de uma decisão `correct`**: comparando o texto da revisão 1 com o corrigido, todo
trecho alterado tem de cair dentro de uma diferença que o relatório aponta para aquele problema,
ou ser só a inserção de marcas (`^{`, `_{`, `}`). Uma mudança fora disso recusa a decisão, com o
trecho.

Diferenças a até 16 caracteres uma da outra contam como um só trecho (medido em 2026-10-18 no
`670_D2`: a legenda reescrita aparece no relatório como 27 diferenças pequenas, separadas por 1 a
15 letras que coincidem por acaso, e a decisão, alinhada por conta própria, mexia nessas letras e
era recusada). Uma mudança a mais de 16 caracteres de toda diferença continua recusada.

**Ajuda aos autores**: `python -m dataset revise --draft-decisions` grava, para cada problema em
revisão sem decisão, um rascunho com o texto atual e a lista das diferenças com os trechos do
original. Os autores editam o rascunho e completam o motivo e o nome.

## R4 — Manifesto com revisão e revisão 1 guardada (S2, F3)

**Decision**:
- **Manifesto da revisão 2:** `Manifest` passa a aceitar `schema_version` 1 ou 2; com 2, exige:
  - `revision: int ≥ 2`;
  - `revision_of`, com o hash do manifesto anterior, os hashes do relatório da 006, do manifesto
    dos originais e de `dataset_revision.json`, e a data.
  `revision_of` é proveniência, não entra em nenhum hash de arquivo.
- **Revisão 1 guardada:** `data/dataset.zip` e o manifesto atual são **renomeados**, sem mudar
  nenhum byte, para `data/dataset.rev1.zip` e `manifests/dataset.rev1.manifest.json`. O hash
  `a092d987…`, gravado no `run.json` do SLM e nos relatórios dos pilotos, continua verificável com
  `dataset verify --zip data/dataset.rev1.zip --manifest manifests/dataset.rev1.manifest.json`.
  Esse `verify` é auditoria: a obrigação (b) da emenda 1.8.0 ("sem que nenhum comando a use") é
  lida como "nenhum comando do pipeline a consome" (geração, execução, métricas); conferir a
  integridade da revisão guardada é justamente o que a guarda permite (analyze de 2026-10-18).
- **`.gitignore`:** ganha a exceção `!data/dataset.rev1.zip`.

## R5 — Empacotar a revisão 2 (FR-002, FR-003)

**Decision**:
1. Copiar `data/dataset/problems/` para `data/work/revision2/problems/` e trocar os `enunciado.md`
   alterados.
2. Empacotar com o mesmo empacotamento determinístico do `package`. O `packaging.build_dataset_zip`
   ganha um parâmetro com a pasta de problemas, e o padrão continua `data/work/problems`.
3. Gerar o manifesto pelo `build_manifest` (que recalcula tudo do zip), com `revision` e
   `revision_of`.
4. **Conferir antes de trocar os arquivos:**
   - cada arquivo do manifesto novo que não é um `enunciado.md` alterado tem o mesmo SHA-256 que no
     manifesto da revisão 1;
   - os alterados são exatamente os listados em `dataset_revision.json`.
   Qualquer diferença recusa sem gravar.
5. Só então renomear a revisão 1 e gravar a revisão 2 (zip, manifesto e `dataset_revision.json`),
   cada um atomicamente.

`dataset_revision.json` traz, por problema alterado:
- `problem_id`;
- `origin`: `"automatic"` ou `"manual"`;
- `markups` (contagem por tipo) ou o motivo da decisão;
- `sha256_before` e `sha256_after`.

Traz também os problemas mantidos por decisão (`"keep"`).

## R6 — SLM: execução nova só do afetado e junção (D2, F2, S3)

**Decision**:
1. Mover `data/suites/slm/` para `data/suites/slm-rev1/`, sem mudar nada. O `run.json` dela continua
   com a revisão 1.
2. Começar uma execução nova em `data/suites/slm/` com a revisão 2, só com as combinações afetadas.
   O `revise` imprime o comando pronto:
   `generate --problem <id> … --scenario black_box --scenario hybrid`, e os mesmos argumentos para o
   `execute`.
3. Rodar `python -m ai_clients package --merge-from data/suites/slm-rev1`:
   - confere que a execução nova tem suíte em todas as combinações afetadas;
   - confere que a execução anterior tem suíte em todas as não afetadas;
   - as combinações afetadas vêm da execução nova; as não afetadas, da anterior;
   - o pacote final `data/slm_suites.zip` tem as duas árvores lado a lado (`suites/slm/` e
     `suites/slm-rev1/`, cada uma com o seu `run.json`) e um `provenance.json` com, para as 600
     combinações, a árvore, o hash do manifesto do dataset e a revisão;
   - as combinações afetadas que ficam na árvore anterior estão no pacote, mas são marcadas como
     **substituídas** em `provenance.json`;
   - o manifesto e o relatório do SLM passam a dizer a revisão de cada combinação.
4. O leitor das suítes (`SuiteView`) e a avaliação futura usam `provenance.json` para escolher, por
   combinação, a suíte certa.
5. **A árvore anterior é conferida antes de entrar** (analyze de 2026-10-18): o `--merge-from` lê
   `data/suites/slm-rev1` com as regras do `store` (dano; `suite.json` igual ao que os arquivos
   dão), sem comparar o `run.json` dela com o dataset atual, que é a revisão 2 por definição.

**Alternatives considered**:
- copiar as não afetadas para a execução nova, rejeitado em F2;
- pôr a origem dentro de cada `suite.json`, o que mudaria o schema das suítes já empacotadas (S3).

## R7 — Mutantes e `cli check` (F4, FR-005, FR-010)

**Decision**:
- **Mutantes:**
  - `python -m mutation report` regenera `manifests/mutation_report.json` com o hash do manifesto
    da revisão 2;
  - `python -m mutation verify` confere o pacote dos mutantes e precisa dar `OK`, sem mudança;
  - a divergência anterior do relatório (S4) é registrada.
- **`cli check`:**
  - a camada `dataset` usa o manifesto da revisão 2;
  - a camada `slm_suites` aceita a junção: por combinação, a árvore indicada em `provenance.json`;
  - a revisão 1 guardada não é uma camada;
  - os relatórios dos pilotos não são conferidos (F4).

## R8 — Testes

Datasets sintéticos com 3 problemas (um com expoente perdido, um em revisão, um fiel), originais
escritos à mão (como na 006) e decisões de teste.

**Geração da revisão:**
- só os `enunciado.md` mudam;
- a revisão 1 é guardada byte a byte;
- o manifesto 2 tem `revision` e `revision_of`;
- a conferência contra o original, depois, não acha perdas;
- a geração repetida sobre as mesmas entradas dá o mesmo zip.

**Recusas, todas sem nada gravado:**
- falta uma decisão;
- uma decisão muda texto fora das diferenças;
- `sha256_before` não confere;
- o relatório é de outro dataset;
- o dataset extraído diverge;
- o resultado mudaria outro arquivo.

**Junção do SLM:**
- origem certa em cada combinação;
- recusa se faltar uma afetada na execução nova;
- `provenance.json` cobre as 600.

**`cli check`:** passa com a revisão 2 e com o pacote juntado; acusa uma combinação sem origem.
