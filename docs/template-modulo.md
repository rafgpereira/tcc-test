# Template de documentação de módulo

> **Fonte única** do formato de documentação de uso de cada módulo do projeto. Cada módulo tem um
> `src/<modulo>/README.md` que segue este template. Não copie este arquivo com outra estrutura:
> ajuste este template se o formato precisar mudar (e, então, ajuste todos os READMEs no mesmo ciclo
> de trabalho). O README existe para **usar** o módulo: enxuto, organizado e objetivo.

## Regras de uso

1. **Onde**: `src/<modulo>/README.md`, um por subpacote de `src/`. Docstrings do pacote e a ajuda
   (`--help`) da CLI complementam o README e MUST NOT contradizê-lo.
2. **Conteúdo mínimo**: as seis seções (a) a (f) abaixo, com estes títulos e nesta ordem, mais
   "Referências" e "Comandos verificados". Seção sem conteúdo real MUST dizer "Nenhuma" (com uma
   frase), nunca ser omitida.
3. **Só dois cenários**: o (b) se organiza em **Cenário A — rodar do zero** e **Cenário B —
   descompactar/usar o que já existe** (o pacote versionado que outra pessoa gerou). Não há mais
   cenários. Módulo sem artefato distribuído (só biblioteca ou só motor) usa o (b) para dizer como é
   usado, sem inventar cenário.
4. **Todos os comandos numa tabela**: logo depois dos cenários, uma única tabela lista **todos** os
   comandos do módulo e suas variações (opções, escopo de um problema só, paralelismo, o que a
   interrupção e a retomada fazem, código de saída). Retomada e variações **não** têm seção própria:
   ficam na coluna de observações dessa tabela. Cada comando aparece uma vez, com serviço
   (`app` tem internet; `sandbox` não tem), o que faz e o que esperar.
5. **Nomes limpos de comando**: um comando é `docker compose run --rm <serviço> python -m
   <modulo> <subcomando>`; nunca o caminho de um script (`python scripts/...`). Todo comando novo
   nasce como subcomando de um pacote de `src/`.
6. **Sem ler o código e sem saber Docker**: uma pessoa que nunca viu o código e não conhece Docker
   MUST conseguir executar o módulo só com o README e com o guia do `README.md` da raiz.
   Portanto: explique o serviço usado, o que aparece na tela, como confirmar que deu certo (código
   de saída, arquivos gerados) e o que fazer nas falhas comuns (tabela curta); nenhum termo ou valor
   de configuração é tratado como conhecido; a preparação única do ambiente é feita apontando para o
   guia da raiz, sem repeti-la. Não afirme comportamento não observado (tempo, tamanho): diga o que
   foi medido, com data, ou que será medido.
7. **Comandos exatos**: todo comando MUST ser copiável e funcionar como escrito no ambiente
   containerizado. Cada subcomando MUST constar na tabela "Comandos verificados" (última seção) com
   a data e a revisão git em que foi executado de verdade; a linha nasce `pendente` e só é
   carimbada quando o comando é executado. A revisão é a saída de `git rev-parse --short=7 HEAD` no
   host, obtida depois de commitar o código e antes de rodar o comando, com o sufixo `+dirty` se
   `src/`, `scripts/`, `pyproject.toml`, `uv.lock`, `Dockerfile` ou os arquivos do compose tiverem
   alterações não commitadas; o fechamento da feature rejeita `+dirty`. Um comando que a execução
   real nunca precisou (por exemplo, fechar à mão quando nada aguardou os autores) é registrado
   como `não necessário (<motivo>)`, com revisão `—`. A tabela tem só `Comando | Verificado em |
   Revisão`.
8. **Idioma**: português. Nomes de comandos, arquivos, campos e código ficam como no código, em
   inglês.
9. **Sincronização**: o README é atualizado no mesmo ciclo de trabalho em que o módulo muda.
   Divergência entre o README e a metodologia (`docs/metodologia-referencia.md`) MUST ser resolvida
   nos dois documentos. Enquanto o módulo não estiver implementado, o cabeçalho MUST dizer isso e o
   README MUST NOT descrever comandos como se existissem; `Status: implementado` MUST NOT conviver
   com linha `pendente` na tabela de comandos verificados.
10. **Sem rastro do processo de especificação**: o README explica o que o módulo faz e como usá-lo,
    nunca como foi construído nem por quê, segundo as regras do projeto. MUST NOT citar o spec-kit,
    a Constitution e seus princípios, ids de requisito (`FR-`, `SC-`), identificadores de tarefa
    (`T035`), caminhos `specs/NNN-...` nem narrar o processo de implementação. Quando uma decisão
    precisa ser explicada, explique a decisão em linguagem comum e aponte a seção de
    `docs/metodologia-referencia.md`, que é onde a proveniência datada das decisões fica. Números
    medidos entram como fatos datados ("medido em 2026-09-20: ..."). O cabeçalho cita só o status e
    a seção da metodologia.
11. **Verificação automática**: `docker compose run --rm app python scripts/check_docs_sync.py
    --module src/<modulo>` confere as seis seções na ordem, o propósito em uma frase, os comandos
    contra a CLI (todo subcomando citado deve existir; no README do módulo dono da CLI, todo
    subcomando também deve estar documentado), os links, a ausência de rastro do processo
    (checagens C7 e C8) e a tabela de comandos verificados; e a seção "Referência de comandos" do
    `README.md` da raiz (todo subcomando da CLI deve constar nela). A lista de conformidade abaixo
    cobre só o que o script não decide.

## Esqueleto

Copie o bloco abaixo para `src/<modulo>/README.md` e preencha. Trechos entre `<...>` são
instruções e MUST ser substituídos.

````markdown
# <Nome do módulo>

> **Status**: <planejado | em implementação | implementado> · **Metodologia**:
> `docs/metodologia-referencia.md`, seção <N>

## (a) Propósito

<Uma frase: o que o módulo faz e para que serve no experimento.>

## (b) Como executar

**Antes de começar** (uma vez por máquina): <link para o guia do README da raiz e os passos dele
necessários para este módulo>. <Diga em qual serviço o módulo roda e por quê.>

<Um ou dois parágrafos curtos sobre o que o módulo faz, sem jargão não explicado.>

### Cenário A — Rodar do zero

<Passos numerados, cada um com o bloco de comando exato, o que aparece na tela e como conferir.>

### Cenário B — Descompactar o que já existe

<Os poucos comandos para usar o pacote que outra pessoa gerou e versionou, e como conferir.>

### Comandos

| Comando | Serviço | O que faz / variações |
|---|---|---|
| `python -m <modulo> <sub>` | `<app \| sandbox>` | <o que faz; opções e o que esperar; escopo de um problema (`--problem ID`); paralelismo; o que acontece se for interrompido> |

Código de saída: `0` sucesso, `1` falha de dados, `2` uso incorreto, `3` falha de infraestrutura,
`130` interrompido. `--help` de cada subcomando lista as opções.

### Se algo der errado

| O que aparece | O que fazer |
|---|---|
| <mensagem ou código de saída> | <ação exata> |

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| <nome> | <formato> | <de onde vem> |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| <nome> | <formato> | <onde é gravada e o que a consome depois> |

## (e) Dependências e pré-requisitos

- <Ferramentas e versões fixadas; serviço do Compose (com ou sem rede); módulos que precisam ter
  rodado antes; variáveis do `.env`.>

## (f) Limitações conhecidas

- <Cada limitação com o impacto no experimento e, quando existir, o número medido com a data.>

## Referências

- Metodologia: `docs/metodologia-referencia.md`, seção <N>
- Testes: `tests/<modulo>/` (`docker compose run --rm sandbox pytest tests/<modulo>`)

## Comandos verificados

| Comando | Verificado em | Revisão |
|---|---|---|
| `<subcomando>` | pendente | — |
````

## Lista de conformidade (usada na revisão)

Um README de módulo só está em conformidade se **todas** as respostas forem "sim":

- [ ] O arquivo existe em `src/<modulo>/README.md`, com as seis seções (a) a (f) na ordem, e o
  propósito cabe em **uma** frase?
- [ ] O (b) tem só os cenários A (do zero) e B (usar o que já existe), sem seções extras para
  retomada, opções ou variações?
- [ ] Existe uma única tabela com **todos** os comandos e suas variações, com nomes limpos
  (`python -m <modulo> <sub>`), e a mesma lista consta na "Referência de comandos" do `README.md`
  da raiz?
- [ ] Uma pessoa sem conhecimento de Docker consegue seguir (serviço explicado, resultado esperado,
  como conferir, falhas comuns), com a preparação do ambiente apontando para o guia da raiz?
- [ ] Cada subcomando consta em "Comandos verificados" com data e revisão (sem `pendente` se o
  módulo está `implementado`)?
- [ ] O README não cita spec-kit, Constitution, requisitos, tarefas nem `specs/NNN-...`, e o que
  afirma bate com `docs/metodologia-referencia.md`?
- [ ] `check_docs_sync.py --module src/<modulo>` sai com `0`?
- [ ] (c) e (d) dizem formato **e** origem/destino; (e) lista versões e o serviço; (f) traz
  limitações reais (ou "Nenhuma" com justificativa)?
- [ ] O `README.md` da raiz menciona o módulo e como ele se conecta aos outros?

## Módulos e estado da documentação

Mantenha esta tabela atualizada ao criar ou concluir módulos (ver também a tabela de estado no
`README.md` da raiz).

| Módulo | README | Situação |
|---|---|---|
| `src/dataset/` | [README](../src/dataset/README.md) | implementado: `extract`, `report`, `selfcheck`, `validate`, `audit`, `package` e `verify` documentados e carimbados |
| `src/sandbox/` | [README](../src/sandbox/README.md) | implementado (motor de execução compartilhado) |
| `src/mutation/` | [README](../src/mutation/README.md) | implementado: `generate`, `report`, `package` e `verify` documentados e carimbados |
| `src/cli/` | [README](../src/cli/README.md) | em implementação: `check` (consistência entre artefatos) pronto; o orquestrador do experimento ainda sem especificação |
| `src/ai_clients/` | [README](../src/ai_clients/README.md) | em implementação: suítes do modelo local (SLM) geradas na execução completa, pacote ainda por gerar (`package` e `verify` `pendente`); os dois modelos comerciais ainda sem especificação |
| `src/metrics/` | a criar na feature própria | ainda sem especificação (IIC pendente, metodologia seção 5.4) |
