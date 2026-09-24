# Contract: Interface de linha de comando do módulo `mutation`

**Feature**: `002-mutant-generation` | Consumidores: os dois autores; módulos futuros (IA,
avaliação) só leem `data/mutants.zip`/`manifests/mutants.manifest.json` da execução final, não
chamam esta CLI.

Ponto de entrada: `python -m mutation <comando>` (pacote `src/mutation/`, `__main__.py`,
`argparse`, mesmo padrão de `python -m dataset`), sempre dentro do contêiner.

## Serviços do Docker Compose

| Serviço | Rede | Usado para |
|---|---|---|
| `app` | com rede | `package`, `verify`, `report` — nenhum deles compila ou executa C++ de terceiros |
| `sandbox` | sem rede | `generate` — compila e executa cada mutante candidato via `sandbox.judge_source` |

Mesma regra já em vigor no módulo de dataset: comando que executa código de terceiros só existe
no serviço `sandbox`.

## Comandos

Códigos de saída: `0` sucesso; `1` falha de verificação (ex.: `data/dataset` não corresponde ao
manifesto, integridade do pacote de mutantes divergente); `2` uso incorreto; `3` falha de
infraestrutura; `130` interrompido (retomada segura, ver `research.md`, R5).

### `generate` (serviço `sandbox`)

Antes de processar qualquer problema, verifica `data/dataset` contra
`manifests/dataset.manifest.json` (FR-010) — aborta com código `1` e mensagem clara se não
corresponder. Processa cada problema completo do dataset (na ordem dos diretórios), gravando em
`data/mutants/building/<problem_id>/` e movendo atomicamente ao concluir (R5). Nunca versiona o
resultado.

| Opção | Padrão | Efeito |
|---|---|---|
| `--problem ID` | todos | processa um único problema (uso: desenvolvimento/depuração) |
| `--resume` (implícito) | — | pula problemas já completos em `data/mutants/`; não há flag para desativar (mesmo comportamento sempre seguro do módulo de dataset) |

Saída: progresso por problema (mutantes por ordem, alertas de exclusão) na saída padrão;
`manifests/mutation_report.json` **não** é escrito por este comando — só por `report`
(sempre reflete o estado atual de `data/mutants/`, gerado sob demanda, nunca implicitamente).

### `report` (serviço `app`)

Recalcula `manifests/mutation_report.json` a partir do estado atual de `data/mutants/`
(funil, distribuição por ordem/operador, alertas), incluindo `code_revision` (git) e
`dataset_manifest_sha256`. Idempotente; pode ser rodado a qualquer momento, mesmo com
`data/mutants/` parcial (útil durante o desenvolvimento).

### `package` (serviço `app`)

Só roda sobre um `data/mutants/` sem nenhum `building/` pendente (recusa-se, código `1`, se
houver). Gera `data/mutants.zip` (determinístico) e `manifests/mutants.manifest.json`, e chama
`report` internamente para garantir que o relatório reflita exatamente o que foi empacotado.
Comando manual e explícito — nunca chamado por `generate`.

### `verify` (serviço `app`)

Recalcula os hashes de `data/mutants.zip` (ou, com `--extracted DIR`, de uma árvore já
descompactada) e compara com `manifests/mutants.manifest.json`, apontando `changed`/`missing`/
`extra` — mesmo comportamento de `dataset verify`.

## Fora do contrato

Chamadas a modelos de IA, avaliação das suítes geradas contra os mutantes, cálculo de métricas —
escopo de módulos futuros, que consomem `data/mutants.zip` já empacotado.
