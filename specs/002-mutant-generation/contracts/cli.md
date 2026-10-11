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
| `--problem ID` | todos | processa só esse problema; pode ser repetida (uso: desenvolvimento/depuração); um ID que não está em `data/dataset` é erro de uso (código `2`) |
| `--workers N` | metade das CPUs (mínimo 1) | problemas processados em paralelo, cada um num `slot` próprio do motor; **não altera o resultado**, só o tempo; inteiro positivo, senão erro de uso (código `2`); `1` roda no próprio processo |
| `--resume` (implícito) | — | pula problemas já completos em `data/mutants/`; não há flag para desativar (mesmo comportamento sempre seguro do módulo de dataset) |

Uma única instância por vez: `generate` toma um `flock` em `data/mutants/.lock` e um segundo
`generate` sobre os mesmos dados se recusa (código `1`, `another ... generate is already running`);
o sistema operacional solta a trava quando o processo termina, de qualquer forma (Ctrl+C, `kill -9`),
então ela nunca fica obsoleta. Um problema já fechado cujos arquivos foram perdidos ou alterados é
apontado como `DAMAGED` (com a lista `missing:`/`changed:`/`extra:`) e **não** é pulado em silêncio:
o comando termina com código `1` no fim; apagar a pasta do problema e rodar de novo regera só ele.
Interromper (Ctrl+C, `docker stop`) encerra os trabalhadores na hora, sem esperar os problemas em
voo, com código `130`; nada de um problema em voo estava gravado, e a próxima execução o refaz.

Um problema cuja primeira ordem não fecha a cota segue para pares e, se preciso, trios de mutantes de
primeira ordem (FR-004). Se ainda assim não chega a 100, o problema é **excluído** (FR-009): a saída
traz uma linha `ALERT: <id> reached only N of 100 mutants (highest order tried: K)`, nenhum
`Mutant_<n>.cpp` é gravado (só o `generation.json`, com `status: excluded`, que fecha o problema
para a retomada), e o comando **termina com `0`** — exclusão é um resultado, não uma falha; os
demais problemas seguem. O resumo final é `done: N generated, N skipped, N excluded`.

Saída: progresso por problema (mutantes por ordem, descartes por motivo, tempo, alertas de exclusão) na saída padrão;
`manifests/mutation_report.json` **não** é escrito por este comando — só por `report`
(sempre reflete o estado atual de `data/mutants/`, gerado sob demanda, nunca implicitamente).

### `report` (serviço `app`)

Recalcula `manifests/mutation_report.json` a partir do estado atual de `data/mutants/` (lê só os
`generation.json`: funil, distribuição por ordem/operador, contagem de problemas, alertas),
incluindo `dataset_manifest_sha256`. Antes, verifica `data/dataset` contra o
manifesto (código `1` se divergir). Idempotente (sem timestamp); pode ser rodado a qualquer
momento, mesmo com `data/mutants/` parcial (útil durante o desenvolvimento).

Sem opções (como `dataset report`).

### `package` (serviço `app`)

Recusa-se (código `1`, nada é gravado) se: `data/dataset` divergir do manifesto; houver algum `building/` pendente; algum problema fechado estiver danificado (um
`Mutant_<n>.cpp` perdido ou alterado); ou faltarem problemas do dataset que ainda não foram gerados
(a menos que se passe `--allow-partial`, para empacotar mesmo assim). Gera `data/mutants.zip`
(determinístico, só os `Mutant_<n>.cpp` dos problemas completos) e `manifests/mutants.manifest.json`
e, por fim, recalcula o `manifests/mutation_report.json` para refletir exatamente o que foi
empacotado. Comando manual e explícito — nunca chamado por `generate`.

| Opção | Padrão | Efeito |
|---|---|---|
| `--allow-partial` | desligado | empacota mesmo com problemas do dataset ainda não gerados (uso: teste; **não** para o pacote que será versionado) |

### `verify` (serviço `app`)

Recalcula os hashes de `data/mutants.zip` (ou, com `--extracted DIR`, de uma árvore já
descompactada, tipicamente `data/mutants`) e compara com `manifests/mutants.manifest.json`,
apontando `changed`/`missing`/`extra` — mesmo comportamento de `dataset verify`. Na árvore
descompactada só contam os `Mutant_<n>.cpp` de `problems/<id>/`; o `generation.json` e a pasta
`building/` de uma geração local não são "extras".

## Fluxo: quem gera e quem só recebe

Existe **um único caminho de consumo**, `data/mutants/problems/<id>/Mutant_<n>.cpp`, seja qual
for a origem dos arquivos:

| Quem | O que faz | Onde os mutantes ficam |
|---|---|---|
| Autor que faz a **execução final** | `generate` → `report` → `package` → `verify`; commita `data/mutants.zip` e os dois JSON de `manifests/` | já em `data/mutants/problems/` (não precisa descompactar nada) |
| O **outro autor** (ou qualquer pessoa) | `git pull`; `rm -rf data/mutants` (se houver geração local antiga); `unzip data/mutants.zip -d data/`; `verify --extracted data/mutants` | `data/mutants/problems/`, idêntico ao do autor que gerou |
| Rodada de **desenvolvimento** | `generate` (e `report`), sem `package` | `data/mutants/problems/`, nunca versionado; não vale como resultado do experimento |

`generate` nunca sobrescreve uma pasta de problema já existente em `problems/`: se ela veio de um
pacote descompactado (não tem `generation.json`), é pulada, não regerada. Assim, quem só recebe o
pacote não gera nada por engano, e quem gerou não precisa descompactar o que já tem.

## Fora do contrato

Chamadas a modelos de IA, avaliação das suítes geradas contra os mutantes, cálculo de métricas —
escopo de módulos futuros, que consomem `data/mutants.zip` já empacotado.
