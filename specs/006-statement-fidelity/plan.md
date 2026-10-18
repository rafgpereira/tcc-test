# Implementation Plan: Conferência dos enunciados contra o original do Codeforces

**Branch**: `006-statement-fidelity` (feature do spec-kit; o trabalho acontece na `main`, Princípio X)
| **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-statement-fidelity/spec.md`

## Summary

Dois subcomandos novos do módulo `dataset`, no serviço `app` (que tem rede):

- **`python -m dataset check-statements [--refetch] [--problem ID]`**:
  - obtém, uma vez, a página original de cada problema no Codeforces (uma por vez, ≥ 3 s entre
    pedidos, com identificação; E2) e guarda o HTML em `data/statements/originals/<id>.html`, com o
    hash num manifesto versionado;
  - nas execuções seguintes, só lê as cópias e confere o hash;
  - extrai o bloco do enunciado (descrição, entrada, saída, nota; sem cabeçalho e sem exemplos) e
    o transforma em dois textos: o **achatado**, como o dataset fez, e o **marcado**, com `^{…}`,
    `_{…}`, tabela em Markdown e imagem sinalizada;
  - alinha o texto marcado com o nosso `enunciado.md` (sem os exemplos) e classifica cada
    diferença pelo elemento do original que a cobre: expoente, índice, fórmula, imagem, tabela ou
    outra. Não há lista de padrões (R3);
  - grava `manifests/statement_fidelity_report.json`.
- **`python -m dataset correct-statements --output-dir DIR [--force]`**:
  - para cada problema conferido, insere no texto atual as marcações que o original tem e o nosso
    perdeu, e converte as tabelas (E3, E4);
  - aceita o enunciado só se passar nas três conferências (FR-008); os demais vão para revisão;
  - grava em `DIR/<id>.md`, numa pasta plana, mais um resumo. Nunca toca no dataset (E1, FR-009).

Abordagem técnica (detalhes em [research.md](./research.md)):
- biblioteca padrão: `urllib.request` e `html.parser` (R1, R2);
- alinhamento com `difflib` sobre o texto com espaços normalizados (R3);
- o enunciado corrigido é o texto **atual** com as marcações do original inseridas, e não um texto
  refeito do zero (R5, S2);
- o manifesto e o relatório têm schema Pydantic;
- a cópia do bloco do enunciado vai para um pacote versionado (S1).

## Sinalizações e decisões

| # | Lacuna encontrada ao planejar | O que o plano faz | Decisão |
|---|---|---|---|
| **S1** | A spec pede a cópia do original com hash, mas não diz se a cópia é versionada. A página inteira tem cerca de 65 KB, menu e anúncios incluídos; versionar as 200 páginas põe no repositório conteúdo do site que não é o enunciado. | Versiona `manifests/statement_originals.manifest.json`, com o hash da página inteira e o do bloco extraído, e um pacote `data/statement_originals.zip` só com os 200 blocos do enunciado. As páginas inteiras ficam em `data/statements/originals/`, fora do Git. Quem clona confere e roda a comparação pelo pacote, sem acessar o site. | **A decidir pelos autores** (sugestão: assim). Alternativas: versionar as páginas inteiras, ou não versionar nada além do manifesto, o que deixa a comparação dependente do site para quem clona. |
| **S2** | O FR-007 diz "gerar de novo a partir do HTML original". Refazer o texto inteiro do HTML mudaria espaços, quebras de linha e o bloco de exemplos, que o dataset tem e o bloco do HTML não, e isso faria a conferência (c) falhar sempre. | O corrigido é o `enunciado.md` atual com as marcações que o **original** tem inseridas nos lugares que o alinhamento indica (`10^{5}`, `a_{i}`) e as tabelas convertidas. O conteúdo vem do original; o resto fica idêntico por construção (R5). | **A confirmar pelos autores** (sugestão: assim). A spec passa a dizer isso no FR-007. |
| **S3** | O formato novo traz LaTeX (`\le`, `\lt`, `\dots`), e o dataset trocou alguns comandos por símbolos (`≤`, `<`, `...`). | Tabela de equivalências **medida** no piloto (`\le`→`≤`, `\lt`→`<`, `\dots`→`...`), versionada no código. Uma conversão fora dela vira diferença do tipo "fórmula", nunca é escondida (R4). | — (informativo; a tabela só cresce com casos vistos no relatório e registrados). |

## Technical Context

**Language/Version**: Python 3.11 (o da imagem, `uv`).

**Primary Dependencies**: **nenhuma nova**:
- `urllib.request` (download), `html.parser` (leitura do HTML), `difflib` (alinhamento), `hashlib`;
- `pydantic` para o manifesto e o relatório.

**Storage**:
- `data/statements/originals/<id>.html`: as páginas, não versionadas;
- `data/statement_originals.zip`: os blocos do enunciado, versionado (S1);
- `manifests/statement_originals.manifest.json` e `manifests/statement_fidelity_report.json`,
  versionados;
- `DIR/<id>.md` e `DIR/summary.json`: os corrigidos, para revisão, não versionados.
- Todas as pastas são planas, sem uma pasta por problema, então o `cli check` não muda.

**Testing**: `pytest` no `sandbox`, sem rede. São usados blocos de enunciado pequenos montados nos
testes, nos dois formatos, e um servidor falso no lugar do site (R7).

**Target Platform**: o contêiner `app` (rede para o primeiro download). Depois do download, tudo
roda sem rede.

**Project Type**: pipeline de linha de comando; um subpacote novo, `src/dataset/statements/`.

**Performance Goals**: nenhuma meta. O primeiro download leva pelo menos 200 × 3 s por construção
(E2); o tempo real é medido na primeira execução.

**Constraints**:
- E2 (um pedido por vez, ≥ 3 s);
- o dataset nunca é alterado (FR-006, FR-009);
- nenhuma diferença é descartada sem classificação (FR-003).

**Scale/Scope**: 200 problemas e 200 páginas, obtidas uma vez.

## Constitution Check

*GATE: antes da Fase 0 e revisto depois da Fase 1.* Constitution 1.7.1.

| Princípio | Como o plano cumpre | Status |
|---|---|---|
| I. Metodologia mutável | Piloto, clarify e decisões do plano (S1–S3, R1–R8) registrados na metodologia, seções 1 e 3 | ✅ |
| II. Reprodutibilidade | A cópia do original é guardada com hash, num manifesto versionado; a comparação roda offline sobre a cópia e é determinística; o pacote dos blocos (S1) deixa qualquer um reproduzir o relatório sem o site | ✅ |
| III. Sem estado | Não se aplica: não há chamada a IA | ✅ |
| IV. Contratos versionados | Manifesto, relatório e resumo dos corrigidos com schema Pydantic (`schema_version` 1) | ✅ |
| V. Sandboxing | Não se aplica: nada é compilado nem executado | ✅ |
| VI. Testa a si próprio | Testes offline dos dois formatos, dos casos do piloto, das três conferências e do acesso ao site com um servidor falso (R7) | ✅ |
| VII. Retomada | O download é retomável: só baixa o que falta, e cada cópia é gravada atomicamente; a comparação e a correção são funções puras das cópias | ✅ |
| VIII. Custo/uso de IA | Não se aplica | ✅ |
| IX. Simplicidade | Só biblioteca padrão; o corrigido é o texto atual com marcações inseridas, não um conversor completo de HTML para Markdown (S2) | ✅ |
| X. Revisão humana | O agente não roda Git; o dataset só muda por decisão dos autores, fora desta feature (E1) | ✅ |
| XI. Documentação viva | Spec (FR-007, S2), metodologia, README do módulo `dataset`, referência de comandos da raiz e `CLAUDE.md` | ✅ |

**Reavaliação pós-Fase 1**: sem violação. Nenhum desvio a justificar.

## Project Structure

### Documentation (this feature)

```text
specs/006-statement-fidelity/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # R1–R8
├── data-model.md
├── quickstart.md
├── sync-matrix.json     # sem decisões D# (as decisões da spec são E1–E4)
├── contracts/cli.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/dataset/
├── __main__.py              # + subcomandos check-statements e correct-statements
├── config.py                # + caminhos (data/statements/, manifests/statement_*), URL, ritmo
├── schemas/statements.py    # novo: OriginalsManifest, FidelityReport, CorrectionSummary
└── statements/              # novo subpacote
    ├── __init__.py
    ├── fetch.py             # download com ritmo, cópia atômica, manifesto, conferência do hash
    ├── extract.py           # bloco do enunciado → nós (texto, sup, sub, fórmula, imagem, tabela)
    ├── render.py            # nós → texto achatado e texto marcado, com o mapa de posições
    ├── compare.py           # alinhamento com o enunciado.md e classificação das diferenças
    └── correct.py           # marcações inseridas no texto atual e as três conferências
tests/dataset/statements/
├── fixtures.py              # blocos de enunciado pequenos nos dois formatos
├── test_extract.py  test_render.py  test_compare.py  test_correct.py
├── test_fetch.py            # servidor falso: ritmo, identificação, retomada, hash divergente
└── test_cli.py              # códigos de saída, nenhuma escrita no dataset
```

**Structure Decision**: subpacote `src/dataset/statements/` no módulo `dataset`, dono do
`enunciado.md`. Nada de `ai_clients`, `mutation` ou `sandbox` muda.

## Complexity Tracking

Nenhum desvio da constitution a justificar.
