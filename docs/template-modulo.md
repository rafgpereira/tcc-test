# Template de documentação de módulo

> **Fonte única** do formato de documentação de uso de cada módulo do projeto
> (Constitution, Princípio XI). Cada módulo tem um `src/<modulo>/README.md` que segue este
> template. Não copie este arquivo com outra estrutura: ajuste este template se o formato
> precisar mudar (e, então, ajuste todos os READMEs no mesmo ciclo de trabalho).

## Regras de uso

1. **Onde**: `src/<modulo>/README.md`, um por subpacote de `src/`. É o mínimo obrigatório.
   Docstrings do pacote e a ajuda (`--help`) da CLI complementam o README e MUST NOT
   contradizê-lo.
2. **Conteúdo mínimo**: as seis seções (a) a (f) abaixo, com estes títulos e nesta ordem.
   Seção sem conteúdo real MUST dizer "Nenhuma" (com uma frase), nunca ser omitida.
3. **Sem ler o código**: uma pessoa que nunca viu o código MUST conseguir executar o módulo
   e entender o que entra e o que sai só com o README.
4. **Comandos exatos**: todo comando MUST ser copiável e funcionar como escrito, no ambiente
   containerizado do projeto (`docker compose run --rm <serviço> ...`). Cada comando MUST
   constar na tabela "Comandos verificados" (última seção do README) com a data, a revisão git e
   a tarefa que o executou de verdade; a linha nasce `pendente` e só é carimbada quando o
   comando é executado. A revisão é a saída de `git rev-parse --short=7 HEAD` no host, obtida
   depois de commitar o código e antes de rodar o comando, com o sufixo `+dirty` se `src/`,
   `scripts/`, `pyproject.toml`, `uv.lock`, `Dockerfile` ou os arquivos do compose tiverem
   alterações não commitadas; o fechamento da feature rejeita `+dirty`.
5. **Idioma**: português, espelhando o TCC (Constitution, Convenções Técnicas). Nomes de
   comandos, arquivos, campos e código ficam como no código, em inglês.
6. **Sincronização**: o README é atualizado no mesmo ciclo de trabalho em que o módulo muda
   (Princípio XI). Divergência entre o README e a metodologia (`docs/metodologia-referencia.md`)
   MUST ser resolvida nos dois documentos.
7. **Status**: enquanto o módulo não estiver implementado, o README MUST declarar isso no
   cabeçalho e MUST NOT descrever comandos como se existissem. O README completo é exigido para
   a feature ser considerada concluída. Um README com `Status: implementado` MUST NOT ter linha
   `pendente` na tabela de comandos verificados.
8. **Referências, sem duplicar**: aponte para o contrato da feature (`specs/NNN-.../contracts/`)
   e para a seção da metodologia; não copie schemas nem regras longas, resuma e linke.
9. **Verificação automática**: `docker compose run --rm app python scripts/check_docs_sync.py
   --module src/<modulo>` confere as seções (a) a (f) na ordem, o propósito em uma frase, os
   comandos contra a CLI (todo subcomando citado deve existir; no README do módulo dono da CLI,
   `src/dataset`, todo subcomando também deve estar documentado) e os links. A lista de
   conformidade abaixo cobre só o que o script não decide.

## Esqueleto

Copie o bloco abaixo para `src/<modulo>/README.md` e preencha. Trechos entre `<...>` são
instruções e MUST ser substituídos.

````markdown
# <Nome do módulo>

> **Status**: <planejado | em implementação | implementado> · **Feature**:
> `specs/NNN-nome/` · **Metodologia**: `docs/metodologia-referencia.md`, seção <N>

## (a) Propósito

<Uma frase: o que o módulo faz e para que serve no experimento.>

## (b) Como executar

<Comando exato, no ambiente containerizado. Um bloco por comando, com o efeito esperado
em uma linha.>

```bash
docker compose run --rm <serviço> <comando exato>
```

<Se houver opções relevantes: tabela com opção, padrão e efeito, ou remeta a `--help`.>

## (c) Entradas esperadas

| Entrada | Formato | Origem |
|---|---|---|
| <nome> | <formato: arquivo/JSON/argumento, com schema ou link para ele> | <de onde vem: módulo anterior, arquivo, serviço externo> |

## (d) Saídas produzidas

| Saída | Formato | Destino |
|---|---|---|
| <nome> | <formato, com schema ou link para ele> | <onde é gravada, e o que ela consome depois> |

## (e) Dependências e pré-requisitos

- <Ferramentas e versões fixadas (ex.: GCC 13.2.0, Python 3.11.16).>
- <Serviço do Docker Compose que executa (com ou sem rede).>
- <Dados ou módulos que precisam ter rodado antes, e como verificar.>
- <Variáveis de ambiente/segredos (`.env`), se houver.>

## (f) Limitações conhecidas

- <Cada limitação com o motivo e o impacto no experimento. Inclua riscos medidos, com data
  e fonte, quando existirem.>

## Referências

- Contratos: `specs/NNN-nome/contracts/...`
- Testes: `tests/<modulo>/` (`docker compose run --rm sandbox pytest tests/<modulo>`)

## Comandos verificados

| Comando | Verificado em | Revisão | Tarefa |
|---|---|---|---|
| `<subcomando>` | pendente | — | — |
````

## Lista de conformidade (usada na revisão, Princípio X)

Um README de módulo só está em conformidade se **todas** as respostas forem "sim":

- [ ] O arquivo existe em `src/<modulo>/README.md`?
- [ ] Tem as seis seções (a) a (f), com os títulos e a ordem deste template?
- [ ] O propósito cabe em **uma** frase?
- [ ] Cada comando de (b) consta na tabela "Comandos verificados", com data, revisão e tarefa (sem `pendente` se o módulo está implementado)?
- [ ] `check_docs_sync.py --module src/<modulo>` sai com `0`?
- [ ] (c) e (d) dizem formato **e** origem/destino de cada item?
- [ ] (e) lista versões e o serviço do Compose?
- [ ] (f) traz limitações reais (ou "Nenhuma" com justificativa)?
- [ ] A ajuda da CLI (`--help`) e as docstrings do pacote não contradizem o README?
- [ ] O que o README afirma bate com `docs/metodologia-referencia.md` e com o `spec.md`?
- [ ] O `README.md` da raiz (visão geral) menciona o módulo e como ele se conecta aos outros?

## Módulos e estado da documentação

Mantenha esta tabela atualizada ao criar ou concluir módulos (ver também a tabela de estado
no `README.md` da raiz).

| Módulo | README | Situação |
|---|---|---|
| `src/dataset/` | a criar na feature `001-dataset-extraction` | módulo ainda não implementado; o README é tarefa obrigatória da feature |
| `src/sandbox/` | a criar na feature `001-dataset-extraction` | idem (motor de execução compartilhado) |
| `src/mutation/` | a criar na feature própria | ainda sem spec |
| `src/ai_clients/` | a criar na feature própria | ainda sem spec (metodologia seção 3 tem pontos pendentes) |
| `src/metrics/` | a criar na feature própria | ainda sem spec (IIC pendente, metodologia seção 5.4) |
| `src/cli/` | a criar na feature própria | ainda sem spec |
