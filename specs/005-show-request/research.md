# Research: Visualizar o pedido enviado a cada modelo

**Feature**: `specs/005-show-request` | **Date**: 2026-10-16 | **Plan**: [plan.md](./plan.md)

A spec não deixou `NEEDS CLARIFICATION`: as quatro decisões abertas (B1 a B4) foram fechadas no
clarify de 2026-10-16. Esta pesquisa resolve como cada uma é feita no código que já existe. Os
trechos citados foram conferidos no código em 2026-10-16.

## R0 — O que é reaproveitado

**Decision**: a visualização monta o pedido com as **mesmas funções** da geração, importadas, e
lê as tentativas com os **mesmos leitores** dos dois `store`:

| Parte | Função existente |
|---|---|
| Texto-base | `prompt.load_template(path)`: normaliza `\r\n` para `\n`, confere os 3 marcadores e calcula o `sha256` do texto |
| Prompt | `prompt.build_prompt(template, problem, scenario)`, `prompt.prompt_sha256(prompt)` |
| Problema | `problem.load_problem(root, id)` |
| Corpo dos comerciais | `llm.providers.request_body(model, prompt)`, `request_parameters(model)`, `PROMPT_PLACEHOLDER` |
| Corpo do SLM | `ollama.request_body(model, prompt, options)` com `generation.generation_options(run, attempt)` |
| Estado e tentativas | `store.combination_state`/`attempt_files`/`read_run` (SLM); `llm.store.combination_state`/`attempt_files`/`barred_files`/`read_run` |
| Dataset | `__main__.dataset_gate(root)` (código 1 se o dataset diverge do manifesto, FR-008) |
| Seleção | `__main__.selected_combinations(root, args)` (`--problem`, `--scenario`) |

**Rationale**: a spec pede que a visualização nunca divirja do que é enviado (Premissa
"Reaproveitamento"). Uma segunda montagem poderia divergir sem que nenhum teste percebesse.

**Alternatives considered**: gravar o prompt em cada tentativa foi rejeitado pelos autores (decisão
A, 2026-10-16). Isso mudaria o que é gravado e não serviria para as tentativas já feitas.

**Única mudança no caminho de envio**: a serialização do corpo hoje aparece em dois lugares
(`llm.providers._Client.call` e `ollama.OllamaClient._open`), nos dois como
`json.dumps(body).encode("utf-8")`. Ela passa a ser **uma** função, `wire_bytes(body) -> bytes`,
em `prompt.py`, que os dois clientes chamam. Os testes usam a saída dela para conferir que o
`.request.json` gravado é o mesmo JSON enviado (R6). Os bytes enviados continuam os mesmos, e um
teste confere isso.

## R1 — O corpo gravado (FR-004, S2)

**Decision**:
- **Tentativa feita, modelos comerciais**: o corpo vem do `request_parameters` gravado na tentativa
  (ou na resposta barrada). Toda string igual a `PROMPT_PLACEHOLDER` (`"<prompt>"`) é trocada pelo
  prompt conferido. A gravação usa `request_parameters(model) = request_body(model, "<prompt>")`,
  então a troca devolve o corpo enviado, campo a campo. Se o `request_parameters` atual for
  diferente do gravado, a visualização acrescenta o aviso `parameters changed since this attempt:
  <chaves>`, usando a comparação por chave que o `LlmRunConfig` já faz (`request_parameters.x`).
- **Tentativa feita, SLM**: `ollama.request_body(run.model, prompt, generation_options(run, n))`,
  com o `run.json` da árvore lida. A seed e a temperatura do registro (`GenerationRecord.seed`,
  `.temperature`) têm de ser as do `run.spec(n)`. O `store` do SLM já confere isso, e uma
  divergência é dano (código 1).
- **Prévia** (FR-006): o corpo que o código atual montaria. Nos comerciais,
  `request_body(model, prompt)`. No SLM, o `run.json` se existir; senão, `config.MODEL` e
  `sampling_options()` mais a seed e a temperatura de `config.attempt_spec(n)`. O digest do modelo
  não vai no corpo, então a prévia não precisa chamar o Ollama.
- **Chave**: nunca aparece, porque vai no cabeçalho (`Authorization` ou `x-goog-api-key`), que a
  visualização não monta. Um teste confere que o corpo não contém o valor de
  `OPENAI_API_KEY`/`GEMINI_API_KEY` definido no ambiente do teste.

**Rationale**: o código do corpo já mudou uma vez depois de uma chamada real (o `mimeType` do
Gemini, em 2026-10-16, conforme `specs/004-llm-test-generation/plan.md` S4). Montar o corpo de uma
tentativa antiga com o código atual mostraria algo que não foi enviado. O `request_parameters`
gravado é a fonte fiel.

**Alternatives considered**: montar sempre com o código atual, rejeitado pelo motivo acima.

## R2 — O texto-base da tentativa e o histórico do Git (FR-003, B4, S5)

**Decision**: o **hash esperado** do texto-base é:
- nos comerciais, o `template_sha256` da tentativa (ou da barrada);
- no SLM, o `template_sha256` do `GenerationRecord`; quando ele é `null` (tentativas anteriores a
  2026-10-07), o hash do texto-base daquele tipo no `run.json` (`run.template_sha256(kind)`). É a
  regra do `store._template_problems`, que já recusa um `null` feito antes de uma troca.
- Na prévia, o hash do arquivo atual, e não há busca no Git.

Com o hash esperado, a busca segue esta ordem:
1. **Arquivo atual** (`load_template(path)`): se o hash bate, é usado, com a origem `current`.
2. **Histórico do Git** (`template_history.find(root, rel_path, sha256)`):
   - `git -c safe.directory=* -C <root> log --all --format= --raw --no-abbrev -- <rel_path>` lista
     os ids de blob que o arquivo já teve, os dois lados de cada mudança, sem repetição;
   - `git -c safe.directory=* -C <root> cat-file --batch` lê cada blob;
   - para cada blob, aplica a mesma normalização do `load_template` (UTF-8, `\r\n` → `\n`) e
     calcula o `sha256`; se bater e os 3 marcadores aparecerem uma vez, usa esse texto, com a
     origem `git <commit curto>` (o commit mais recente que contém o blob, obtido do mesmo
     `log`).
3. **Nada achado**, Git ausente (`FileNotFoundError` no `git`) ou sem `.git`: recusa com código 1.
   A mensagem traz o hash usado e o atual, e mais nada da visualização é mostrado.

O caminho do texto-base vem da configuração do tipo:
- `config.LLM_TEMPLATE_PATH` nos comerciais;
- `config.PROMPT_TEMPLATE_PATH` ou `config.PREDICT_TEMPLATE_PATH` no SLM, conforme o
  `record.template`.

O caminho relativo à raiz é o mesmo no host e no contêiner (`src/prompt_templates/...`).

**Rationale**: o `--all` cobre um commit que só exista noutro ramo, e o `--raw --no-abbrev` dá os
blobs sem um `git show` por commit. `log` e `cat-file` só leem, então funcionam com o `.git`
montado somente leitura e não alteram nada (Princípio X). O `safe.directory=*` evita a recusa do
Git quando o dono da pasta difere do usuário do contêiner (o `app` roda com `HOST_UID`, o mesmo
dono, mas a opção não custa nada e cobre outros ambientes).

**Alternatives considered**:
- `git log -p` com a reconstrução do texto: mais lento e frágil;
- `--follow` para renomeações: incompatível com `--all`, e os textos-base nunca foram renomeados
  depois de existirem; a limitação fica registrada.

**Limitação**: um texto-base editado e nunca commitado não está no histórico, e a recusa é a
correta (Edge Cases da spec).

## R3 — Qual tentativa, de qual árvore (FR-001, FR-009, S3)

**Decision**:
- **Árvore**: `data/suites/<modelo>/` por padrão; `--suites-dir DIR` lê uma árvore arquivada do
  mesmo modelo (por exemplo, `data/suites/gemini-piloto1`). Os dois `store` hoje derivam a pasta do
  modelo (`config.SUITES_DIR`, `llm.config.suites_dir(model)`). Os leitores ganham um parâmetro
  opcional com a pasta, sem mudar o padrão, como o `ensure_tree`/`lock_tree` do SLM já fazem.
  O `run.json` lido é o dessa árvore.
- **Tentativa**: sem `--attempt`, a de maior número entre as atuais da combinação
  (`attempt_<n>.json` nos comerciais, `attempt_<n>.generation.json` no SLM). Com `--attempt N`,
  essa; se ela não existir, erro de uso (código 2): `error: <id> <cenário> has no attempt N
  (attempts: 1–3)`, ou `(no attempt yet)`.
- **Barrada** (só nos comerciais): `--barred N` lê `barred/<id>/<cenário>/<N>.json`. É exclusiva
  com `--attempt`. A visualização a identifica como `barred response N (no reasoning tokens)`.
- **Sem tentativa nem `--attempt`**: prévia (FR-006), com a próxima tentativa que a geração faria
  (`state.attempt`) e, na linha do terminal, `preview, not sent (next: attempt N)`.
- **`superseded/`**: nunca é lido. Uma tentativa que só existe lá não aparece pela numeração normal
  (Edge Cases).
- **Combinação danificada** (`DamagedCombination`, `DamagedRunError`, `IncompatibleRunError`):
  código 1, com a mesma mensagem que os outros comandos imprimem.
- **Modelo, problema ou cenário inexistente; `--attempt` fora de 1…máximo**: código 2.

**Rationale**: os pilotos ficam arquivados em pastas próprias, e o teste independente da US1 usa o
piloto do Gemini. O parâmetro de pasta já é o padrão do SLM.

## R4 — Conferência de fidelidade ao dataset (FR-012)

**Decision**: um conferente **independente** do `ProblemInput` lê os arquivos crus do problema e
procura no prompt, como substrings exatas, os blocos esperados para o cenário:

| Trecho | Lido de | Bloco procurado no prompt | Cenários |
|---|---|---|---|
| `statement` | `enunciado.md`, bytes decodificados em UTF-8, **sem** tradução de fim de linha | `<problem_statement>\n{texto}\n</problem_statement>` | caixa-preta, híbrido |
| `code` | `AC_ref.cpp`, idem | `<reference_solution_cpp>\n{texto}\n</reference_solution_cpp>` | caixa-branca, híbrido |
| `example_input` | `testes.json` (`json.loads` dos bytes), `public_tests[0].input` | `Input: {entrada}\n` | todos |
| `example_output` | idem, `.output` | `Expected Output: {saída}\n` | todos |

- No exemplo, o único corte permitido é o dos `\n` finais (`rstrip("\n")`, como a montagem faz). O
  conferente registra quantos `\n` foram cortados, e um corte de outro caractere é divergência.
- **Separação dos cenários**: a caixa-preta MUST NOT conter `<reference_solution_cpp>`, e a
  caixa-branca MUST NOT conter `<problem_statement>`. Assim fica conferido que só o contexto muda
  entre os cenários.
- **Resultado por combinação**: `faithful` (tudo achado) ou a lista do que falta, cada item com o
  trecho e a posição do primeiro caractere diferente no melhor alinhamento (o maior prefixo do bloco
  achado no prompt), para mostrar onde o texto se perdeu.
- **No `show-request`**, a conferência aparece na linha do terminal. Um prompt infiel com hash
  conferido é gravado, porque foi de fato o que se enviou, e o comando sai com 1. No dry-run, a combinação
  entra na lista de divergentes do `summary.json`.

**Rationale**: o `read_text` do `load_problem` traduz `\r\n` para `\n`. Comparar com os bytes do
arquivo detecta essa ou qualquer outra transformação entre o dataset e o prompt, que é o que os
autores pediram ("bater com o dataset para ver se não vai perder nada"). Usar o próprio
`ProblemInput` seria conferir a montagem contra ela mesma.

**Alternatives considered**: comparar só o hash do prompt, que não diz qual trecho se perdeu.

## R5 — Expoente perdido no enunciado (FR-013)

**Decision**: o aviso usa as expressões da contagem de 2026-10-16 (metodologia, seção 3), aplicadas
ao `enunciado.md` cru, com o trecho de até 30 caracteres ao redor de cada ocorrência:

```text
operador: (?:≤|<|≥|>|·|×|\*)\s*-?\s*10(?:[2-9]|1[0-8])(?![\d.,])
extras:   (?:modulo|up to|than|exceed|exceeds|to)\s+10(?:[2-9]|1[0-8])(?![\d.,])
          10(?:9|18)\s*\+\s*\d
```

- O aviso vale para os cenários com enunciado (caixa-preta e híbrido); na caixa-branca o enunciado
  não está no prompt.
- O aviso nunca muda o código de saída, porque a perda vem do dataset, que não é corrigido.
- **Calibração**: sobre o dataset real, os problemas marcados MUST ser exatamente os 71 listados na
  metodologia (seção 3). É conferido no quickstart, nível 2, e não em teste unitário, porque o
  dataset não está nos testes.
- Se a expressão marcar um problema a mais ou a menos, a diferença é examinada à mão e registrada
  antes de mudar a expressão ou a contagem.

**Rationale**: a contagem já foi conferida à mão por amostragem, e reproduzi-la no comando torna o
aviso auditável.

**Alternatives considered**: uma lista fixa dos 71 ids, rejeitada porque não vale para um enunciado
novo e esconde o trecho.

## R6 — `generate --dry-run --save-requests DIR` (FR-011, S4)

**Decision**:
- **Opção nos três modelos**; só vale com `--dry-run`. Sem `--dry-run`, erro de uso (código 2). O
  resto do dry-run não muda: a estimativa dos comerciais e a lista do SLM continuam impressas.
- **Combinações**: as mesmas que o dry-run já considera, ou seja, as **pendentes** de
  `--problem`/`--scenario`/`--limit`. Para cada uma, a próxima tentativa (`state.attempt`).
- **Pasta**:
  - recusa (código 2) se `DIR/<modelo>/` já tiver qualquer arquivo, a menos que se passe `--force`,
    que apaga **só** `DIR/<modelo>/` antes de gravar;
  - recusa sempre se `DIR` estiver dentro de `data/suites/`, `data/dataset/` ou `manifests/`, ou se
    contiver uma delas.
  - Sugestão de uso: `data/requests` (dentro de `data/`, então fora do Git e visível no host).
- **Arquivos**, por combinação, numa pasta **plana** (sem subpasta por problema; decidido no
  analyze em 2026-10-16, achado C1: uma subpasta por problema cairia na regra da constitution que
  exige uma camada do `cli check` para todo módulo que produz uma pasta por problema, exagero para
  uma saída de consulta descartável), **um arquivo só** por combinação (decidido no analyze em
  2026-10-16: o prompt já vem dentro do corpo):
  - `DIR/<modelo>/<id>.<cenário>.request.json`: o corpo da requisição no formato do contrato §0,
    `json.dumps(body, indent=2, ensure_ascii=False)` mais `\n`. É o mesmo JSON enviado
    (`json.loads(arquivo) == json.loads(wire_bytes(body))`); só a formatação difere dos bytes da
    rede, onde `≤` vai como `\u2264`. Assim `≤` fica legível no arquivo, e o expoente perdido pode ser
    procurado nele.
- **Resumo**: `DIR/<modelo>/summary.json`, com o schema do data-model.
- **Saída no terminal**, além da do dry-run:
  - `requests: N saved in DIR/<modelo>; faithful K/N; exponent warnings W problems (S combinations)`;
  - uma linha `unfaithful: <id> <cenário>: <trechos>` por divergência;
  - `exponent: <id>: <primeiro trecho>` por problema avisado.
- **Código de saída**: 1 se houver alguma combinação infiel ou danificada (a gravação segue até o
  fim); senão, 0.
- **Nenhuma chamada**: o dry-run dos comerciais não lê a chave, e o do SLM não lê
  `OLLAMA_BASE_URL`. Isso continua assim.

**Rationale**: um arquivo por pedido permite abrir um enunciado no editor e compará-lo com o
dataset, e o resumo dá a resposta de uma vez ("600 de 600 fiéis"). O JSON legível, conferido por
teste contra os bytes enviados, mostra o pedido como ele é sem esconder o texto atrás de escapes.

**Alternatives considered**:
- gravar os bytes da rede (`\u2264` no lugar de `≤`), ilegível para a conferência que os autores
  querem fazer;
- um `.prompt.txt` ao lado do corpo, rejeitado pelos autores no analyze (o prompt já está no
  corpo);
- um arquivo único com tudo, ruim de abrir e comparar;
- gravar dentro de `data/suites/`, proibido pelo FR-011, porque misturaria consulta com o estado da
  geração.

## R7 — `show-request`: formato e códigos (FR-005, FR-007, FR-009)

**Decision** (refinada no analyze em 2026-10-16: só grava, sem mostrar o pedido no terminal):
- **`--output ARQUIVO` é obrigatória**. O arquivo recebe só o corpo da requisição, no mesmo formato
  do dry-run (contrato §0), com o prompt inteiro dentro, sem cortar. Recusa um arquivo existente
  sem `--force`, e sempre recusa dentro de `data/suites/`, `data/dataset/` ou `manifests/`.
- **O terminal nunca mostra o pedido**. Mostra uma linha `written: ARQUIVO — <modelo> <id>
  <cenário> attempt N (of M); prompt sha256 matches; dataset: faithful` (ou `preview, not sent
  (next: attempt N)`, ou `barred response N`), e uma linha `warning:` por aviso: expoente perdido,
  `OLD TEMPLATE VERSION from git <commit>`, parâmetros mudados. Uma divergência com o dataset vira
  `dataset: UNFAITHFUL — <trecho> (<arquivo>) matched X of Y chars`.
- A resposta do modelo nunca aparece, nem no arquivo nem no terminal (B3).
- **Códigos**:

| Código | Quando |
|---|---|
| 0 | gravado, com hash conferido (com o arquivo atual ou com uma versão antiga do Git) ou prévia, e prompt fiel |
| 1 | dataset diverge do manifesto (FR-008); combinação ou `run.json` danificado; texto-base com o hash gravado não achado (nada é gravado); hash do prompt remontado diferente do gravado, mesmo com o texto-base certo (nada é gravado); prompt infiel ao dataset (gravado, porque foi o enviado) |
| 2 | uso incorreto: modelo, problema ou cenário inexistente; tentativa ou barrada inexistente; `--attempt` com `--barred`; `--barred` no SLM; falta `--output`; arquivo de saída existente sem `--force` ou em pasta proibida |

**Rationale**: os códigos 1 e 2 têm o mesmo sentido nos outros subcomandos do módulo (dado
divergente ou danificado; uso). Os códigos 3, 5 e 6 não se aplicam, porque não há chamada.

## R8 — Montagem do `.git` no contêiner `app` (S1)

**Decision**: acrescentar `"./.git:/app/.git:ro"` à lista `volumes` do serviço `app` no
`docker-compose.yml`, e não no `docker-compose.override.yml`, onde `sandbox: *dev` repete o mesmo
mapa e montaria o `.git` também no `sandbox`. O comentário do override passa a dizer que o `.git` é
montado somente leitura e só no `app`, pelo `docker-compose.yml`. O `.dockerignore` continua
excluindo o `.git`, então a imagem não muda. O README da raiz explica, na preparação do ambiente,
que o `app` lê o histórico do Git para o `show-request`.

**Rationale**:
- o `app` não roda código de terceiros, então ler o histórico ali não expõe nada ao código
  avaliado;
- o modo somente leitura impede que qualquer comando do contêiner altere o repositório
  (Princípio X);
- o `sandbox`, onde roda o código de terceiros, continua sem `.git` e sem `.env`.

**Alternatives considered**: `--template-file`, rejeitada pelos autores (S1).

## R9 — Testes

**Decision**: tudo no serviço `sandbox` (sem rede), com dataset e árvores mínimos criados pelos
testes, como nos testes das features 003 e 004:

- **Hash confere** (SC-001):
  - para cada modelo, uma tentativa gravada pela própria geração com um cliente falso
    (`FakeProvider`, o cliente falso do Ollama) tem o hash conferido pelo `show-request`;
  - o corpo gravado é, como JSON, igual ao corpo que o cliente falso recebeu.
- **Corpo dos comerciais vem do gravado** (R1): uma tentativa com `request_parameters` diferente do
  atual grava o corpo com os parâmetros gravados e avisa que os parâmetros mudaram.
- **SLM**: a seed e a temperatura do corpo são as da tentativa (1, 13 e 15); o texto-base é o de
  predição nas tentativas 13 a 15; uma tentativa com `template_sha256` `null` usa o hash do
  `run.json`.
- **Git** (`test_template_history.py`), num repositório temporário (`git init`, dois commits do
  texto-base):
  - a versão antiga é achada pelo hash, e a origem é o commit certo;
  - um hash que não está no histórico é recusado com os dois hashes;
  - sem `git` no `PATH` ou sem `.git`, a recusa é a mesma;
  - o `.git` não muda (a árvore de arquivos do `.git` é a mesma antes e depois).
- **Nunca gravado como enviado** (SC-004): texto-base alterado e não commitado → código 1, e o
  arquivo de saída não é criado.
- **Nada no terminal**: em nenhum caso a saída (stdout e stderr) contém o prompt.
- **Fidelidade** (R4):
  - prompt íntegro → `faithful`;
  - enunciado com `\r\n` no arquivo, ou o prompt cortado → divergência com o trecho certo;
  - caixa-preta com `<reference_solution_cpp>` → divergência.
- **Expoente** (R5): `1 ≤ n ≤ 105` marcado; `10^5` e `100000` não marcados; caixa-branca sem aviso.
- **Só lê** (SC-002):
  - o `socket.socket` é trocado por um que falha, e nada tenta conectar;
  - um retrato dos arquivos de `data/` antes e depois mostra que nada mudou fora do destino pedido.
- **Dry-run com gravação** (R6):
  - grava um `.request.json` por combinação pendente, e `json.loads` dele é igual ao dos bytes
    que o cliente falso receberia; `≤` aparece literal no arquivo;
  - recusa uma pasta com arquivos; `--force` apaga só a pasta do modelo;
  - recusa dentro de `data/suites/`;
  - a opção sem `--dry-run` é erro de uso.
- **`wire_bytes`**: os bytes enviados pelos dois clientes não mudam (comparados com
  `json.dumps(body).encode()`).
- **Códigos 0, 1 e 2** conforme R7.

## R10 — Documentação a propagar

**Decision**: neste ciclo (plano):
- metodologia, seção 3: a nota da visualização passa de "em especificação" a "planejada", e a frase
  "com o resumo da resposta" sai, por contradizer B3; linha nova no histórico;
- spec da 005: a premissa do Git fica decidida (S1);
- spec e contrato da 004: o dry-run pode gravar, com `--save-requests`.

No `tasks.md`:
- o README do módulo (`show-request` e `--save-requests` na tabela única de comandos, os dois
  cenários de uso, a tabela "Comandos verificados");
- a "Referência de comandos" do README da raiz e a preparação do ambiente (o `.git` montado no
  `app`);
- o comentário do `docker-compose.override.yml`;
- o `CLAUDE.md` (comandos do dia a dia).

O `cli check` e o `docs/verificacao-consistencia.md` não mudam: a feature não cria uma pasta por
problema em `data/`.
