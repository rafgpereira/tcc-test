# Implementation Plan: Visualizar o pedido enviado a cada modelo

**Branch**: `005-show-request` (feature do spec-kit; o trabalho acontece na `main`, Princípio X)
| **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-show-request/spec.md`

## Summary

Duas entradas, a mesma montagem, nenhuma chamada a uma API:

- **`python -m ai_clients show-request --model {slm,gpt,gemini} --problem ID --scenario S
  --output ARQUIVO [--force] [--attempt N | --barred N] [--suites-dir DIR]`** grava no arquivo o
  corpo da requisição (que traz o prompt) de uma tentativa gravada (a última, por padrão) ou, sem
  tentativa, a prévia do próximo pedido. O pedido não é impresso no terminal, que mostra só uma
  linha com as conferências (analyze, 2026-10-16). O prompt é remontado com as mesmas funções da
  geração e o hash dele é comparado ao `prompt_sha256` gravado. Se o texto-base usado não for o
  atual, a versão com o hash gravado é procurada no histórico do Git (B4); sem ela, o comando
  recusa, diz os dois hashes e não grava nada.
- **`generate --dry-run --save-requests DIR [--force]`** (nos três modelos) grava, para cada
  combinação pendente, o corpo da requisição em `DIR/<modelo>/<id>.<cenário>.request.json` (pasta
  plana, um arquivo por combinação) e um `summary.json`. Cada prompt passa por uma conferência: enunciado, código e exemplo têm de
  aparecer idênticos aos arquivos do dataset (FR-012). Enunciados com expoente perdido recebem um
  aviso (FR-013).

- **`show-request --model M --suite-attempts --output-dir DIR`** (acrescentado em 2026-10-18,
  FR-014) grava, para cada combinação com `suite.json`, o corpo do pedido da tentativa que
  gerou a suíte (`accepted_attempt`), com as mesmas conferências, no mesmo formato e com o
  mesmo `summary.json` do dry-run (`source: suite_attempt`). Serve, por exemplo, ao SLM, que
  já terminou e não tem pedido pendente (R12).

Nada do que a geração grava muda (decisão A dos autores). O corpo de uma tentativa feita vem dos
`request_parameters` gravados nela, não do código atual (R1). O contêiner `app` passa a ver o
`.git` em modo somente leitura (S1).

Abordagem técnica (detalhes em [research.md](./research.md)):

- **Reaproveitado, sem mudar o comportamento**:
  - `prompt.load_template`, `prompt.build_prompt` e `prompt.prompt_sha256`;
  - `llm.providers.request_body`, `ollama.request_body` e `generation.generation_options`;
  - os leitores de estado dos dois `store` (`combination_state`, `attempt_files`, `barred_files`,
    `read_run`);
  - `dataset_gate` e `selected_combinations` (R0).
- **Novo**:
  - `src/ai_clients/requests_view.py`: montagem da visualização, conferências e formato de saída;
  - `src/ai_clients/template_history.py`: busca do texto-base pelo hash no Git;
  - o subcomando `show-request` e a opção `--save-requests` do `generate`.
- **Mudança mínima no envio**: a serialização do corpo (`json.dumps(body).encode("utf-8")`) passa
  a ser uma função só, `wire_bytes`. Os dois clientes a chamam, e os testes conferem que o
  `.request.json` gravado tem o mesmo JSON que esses bytes (R0, R6).

## Sinalizações e decisões

| # | Lacuna encontrada ao planejar | O que o plano faz | Decisão |
|---|---|---|---|
| **S1** | B4 exige o histórico do Git, mas o contêiner não tem o `.git`: o `docker-compose.override.yml` deixa o `.env` e o `.git` de fora de propósito, porque o `sandbox` roda código de terceiros. | Monta `./.git:/app/.git:ro` **só no serviço `app`**, no `docker-compose.yml`, e não no override, onde a âncora `*dev` também valeria para o `sandbox`. O `sandbox` continua sem o `.git`, e o comentário do override é atualizado (R8). | **Decidido em 2026-10-16 (Milena)**: montar o `.git` só no `app`, somente leitura. Alternativa rejeitada: passar o texto-base antigo com `--template-file`. |
| **S2** | O corpo de uma tentativa feita pode não ser o que o código atual montaria: o `mimeType` do Gemini mudou em 2026-10-16. | O corpo vem dos `request_parameters` **gravados na tentativa**, com o `<prompt>` trocado pelo prompt conferido. Se os parâmetros atuais forem diferentes, a visualização avisa e lista as chaves (R1). | — (cumpre FR-004 com o que foi de fato enviado). |
| **S3** | A visualização do piloto do Gemini (teste independente da US1) lê `data/suites/gemini-piloto1`, não `data/suites/gemini`. | `--suites-dir DIR` lê uma árvore arquivada do mesmo modelo; o padrão é a árvore da execução (R3). | — (informativo). |
| **S4** | Os autores querem um arquivo só por combinação, o corpo, e precisam ler o prompt dentro dele. Os bytes enviados trazem `≤` como `\u2264`, porque o `json.dumps` escapa o que não é ASCII. | O `.request.json` é o mesmo JSON enviado, indentado e com `ensure_ascii=False`, então `≤` aparece legível; um teste confere `json.loads(arquivo) == json.loads(wire_bytes(body))`. A conferência de fidelidade roda sobre o prompt (R6; contrato §0). | **Decidido no analyze em 2026-10-16 (Milena)**: só o corpo, sem `.prompt.txt`; o `show-request` só grava, sem mostrar o pedido no terminal. |
| **S5** | O SLM tem tentativas gravadas antes de 2026-10-07 sem `template_sha256`. | Nelas, o hash esperado é o do texto-base daquele tipo no `run.json`, a mesma regra que o `store` do SLM já usa (R2). | — (informativo). |

## Technical Context

**Language/Version**: Python 3.11 (o da imagem, `uv`).

**Primary Dependencies**: **nenhuma nova**: `pydantic` (schema do `summary.json`), biblioteca
padrão (`hashlib`, `json`, `re`, `subprocess`). O executável `git` já está na imagem
(`/usr/bin/git`).

**Storage**: só leitura de `data/dataset/`, `data/suites/<modelo>/` (ou `--suites-dir`),
`src/prompt_templates/` e `.git/`. Escrita só no arquivo de `--output` ou na pasta de
`--save-requests`, nunca dentro de `data/suites/`, `data/dataset/` ou `manifests/` (R6, R7).

**Testing**: `pytest` no serviço `sandbox`, sem rede e sem o `.git` do projeto. A busca no Git é
testada num repositório temporário criado pelo teste (R9). Nenhum teste chama uma API.

**Target Platform**: o contêiner `app`, o único com o `.git` montado (S1). O `show-request` também
roda no `sandbox`, mas lá a busca no Git recusa como "Git indisponível".

**Project Type**: pipeline de linha de comando; dois módulos novos no pacote `ai_clients`.

**Performance Goals**: nenhuma; o tempo não é medido (SC-003, decidido no analyze em 2026-10-16),
e nada sobre tempo é afirmado.

**Constraints**:
- nenhuma chamada de rede;
- nenhuma escrita fora do destino pedido;
- corpo nunca gravado como "enviado" sem hash conferido (FR-003, SC-004);
- o pedido nunca é impresso no terminal (FR-007);
- a chave da API nunca aparece (ela vai num cabeçalho, que não é montado aqui).

**Scale/Scope**:
- 600 combinações por modelo no dry-run com gravação, 600 arquivos e um resumo;
- o maior prompt tem cerca de 7.500 caracteres nos modelos comerciais e cerca de 9.000 no SLM.

## Constitution Check

*GATE: antes da Fase 0 e revisto depois da Fase 1.* Constitution 1.7.1.

| Princípio | Como o plano cumpre | Status |
|---|---|---|
| I. Metodologia mutável | Decisões do plano (S1–S5, R0–R10) registradas na metodologia, seção 3, e no histórico | ✅ |
| II. Reprodutibilidade | Nada muda no que é gravado. A visualização reconstrói o pedido das mesmas funções e o confere pelo hash; a busca no Git só aceita um texto-base cujo hash bate com o gravado. A imagem não muda, e o `.git` entra por volume, não na imagem (`.dockerignore`) | ✅ |
| III. Sem estado | Nenhuma chamada a modelo. O corpo gravado é o corpo sem estado já enviado: de uma requisição só, sem histórico | ✅ |
| IV. Contratos versionados | `summary.json` do dry-run com schema Pydantic (`schema_version` 1); os registros de tentativa só são lidos, pelos schemas existentes | ✅ |
| V. Sandboxing | O `.git` é montado **só no `app`**, que não roda código de terceiros; o `sandbox` continua sem `.git` e sem `.env` (S1) | ✅ |
| VI. Testa a si próprio | Testes de R9: hash confere nos 3 modelos, texto-base antigo achado no Git temporário, recusa sem ele, fidelidade, expoente, nenhuma escrita fora do destino, nenhuma rede | ✅ |
| VII. Retomada | Comandos só de leitura; a pasta do dry-run é refeita com `--force` e não participa da retomada da geração | ✅ |
| VIII. Custo/uso de IA | Custo zero: nenhuma chamada. Serve para conferir pedidos antes de uma execução paga | ✅ |
| IX. Simplicidade | Sem dependência nova; o `git` é chamado como processo, em modo leitura (`log`, `cat-file`); reaproveita a montagem da geração | ✅ |
| X. Revisão humana | O comando roda só `git log` e `git cat-file`, que não alteram o histórico; o agente não roda nenhuma operação de Git que o altere | ✅ |
| XI. Documentação viva | Spec, plano, metodologia (seção 3 e histórico), spec e contrato da 004 (o dry-run agora pode gravar) atualizados neste ciclo. O `tasks.md` terá o README do módulo, a referência de comandos da raiz e o comentário do override | ✅ |

**Reavaliação pós-Fase 1**: sem violação. A montagem do `.git` e a chamada ao `git` estão
justificadas em Complexity Tracking.

**Reavaliação pós-implementação (2026-10-16, T034)**: sem violação.
- **V:** `docker compose config` mostra `/app/.git` só no `app`, e o `sandbox` não o vê (conferido
  também dentro dos dois contêineres; uma escrita em `/app/.git` no `app` falha com "Read-only
  file system").
- **X:** o único processo `git` está em `template_history.py`, com `log` e `cat-file`, e um teste
  confere que nenhum outro subcomando é chamado.
- **VIII/FR-002:** nenhuma rede nem chave nos dois módulos novos; os testes trocam o `socket` por um
  que falha.
- **IX:** `pyproject.toml` e `uv.lock` sem mudança.

Pendente: a revisão do código por um dos autores (Princípio X).

## Project Structure

### Documentation (this feature)

```text
specs/005-show-request/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # R0–R10
├── data-model.md
├── quickstart.md
├── sync-matrix.json     # sem decisões D# (as decisões da spec são B1–B4)
├── contracts/
│   └── cli.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
docker-compose.yml               # + "./.git:/app/.git:ro" só no serviço app (S1)
docker-compose.override.yml      # comentário: o .git agora é montado, somente leitura, só no app
src/ai_clients/
├── requests_view.py     # novo: RequestView, montagem (tentativa, barrada, prévia), fidelidade,
│                        #       expoente, formato de saída, gravação do dry-run
├── template_history.py  # novo: texto-base pelo hash (arquivo atual, senão git log + cat-file)
├── __main__.py          # + subcomando show-request; + --save-requests/--force no generate (SLM)
├── prompt.py            # + wire_bytes(body): a serialização única do corpo (R0)
├── store.py             # leitores com a pasta da árvore opcional (--suites-dir; R3)
├── ollama.py            # _open usa wire_bytes (mesmos bytes de hoje)
└── llm/
    ├── providers.py     # _Client.call usa wire_bytes (mesmos bytes de hoje)
    ├── store.py         # leitores com a pasta da árvore opcional (--suites-dir; R3)
    └── cli.py           # --save-requests no dry-run de gpt/gemini
tests/ai_clients/
├── test_requests_view.py      # SLM: hash confere, corpo com seed/temperatura, prévia, sem rede
├── test_template_history.py   # repositório Git temporário: acha a versão antiga, recusa sem ela
├── test_fidelity.py           # trechos idênticos, trecho faltando, separação dos cenários, expoente
├── test_save_requests.py      # dry-run grava os arquivos, recusa pasta com arquivos, --force
└── llm/test_show_request.py   # gpt e gemini: tentativa, barrada, prévia, request_parameters gravados
```

**Structure Decision**: dois módulos novos no pacote `ai_clients`, ao lado de `prompt.py`. A
visualização serve aos três modelos, então não fica em `llm/`. O resto só ganha uma opção ou uma
função extraída, sem mudar o que faz. `sandbox`, `dataset`, `mutation` e `cli` não mudam. O `cli
check` também não muda, porque a feature não cria uma pasta por problema: a saída do dry-run é uma
pasta **plana** por modelo (`<id>.<cenário>.*`), de consulta e fora dos artefatos. Uma subpasta por
problema obrigaria a uma camada no `cli check` (constitution, Princípio II), e o analyze de
2026-10-16 (achado C1) trocou a subpasta pela pasta plana.

## Complexity Tracking

| Ponto | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Montar o `.git` (somente leitura) no serviço `app` | B4 manda buscar no histórico do Git o texto-base com o hash gravado. Sem o `.git`, toda tentativa de um texto-base trocado seria recusada | `--template-file` (o autor roda `git show` no host e passa o arquivo) foi rejeitada pelos autores em 2026-10-16 (S1). Montar no override valeria também para o `sandbox`, pela âncora `*dev` |
| Chamar o `git` como processo (`subprocess`) | É o leitor do histórico que já está na imagem | uma biblioteca Git em Python seria dependência nova (Princípio IX) |
| `--save-requests` no `generate --dry-run`, em vez de um comando separado | B2: o dry-run é o lugar onde os autores já conferem tudo antes de pagar, e a lista de combinações pendentes é a dele | um comando separado repetiria a seleção de combinações e o estado de cada uma |
