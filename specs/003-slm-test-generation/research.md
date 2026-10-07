# Research: Geração de Suítes de Teste pelo SLM

**Feature**: `003-slm-test-generation` | **Date**: 2026-09-30 | **Plan**: [plan.md](./plan.md)

Cada item: **Decisão**, **Motivo**, **Alternativas consideradas**. Todos decididos: a única
PROPOSTA (R4) e as sinalizações S1, S2 e S5 foram decididas em 2026-09-30 (Milena, opção A em
todas; ver plan.md, "Sinalizações e decisões"). As medições foram feitas em 2026-09-30
sobre `data/dataset/problems/` (200 problemas, árvore descompactada de `data/dataset.zip`), só
lendo arquivos, sem compilar nem executar nada.

---

## R0 — Inventário do que já existe e deve ser reaproveitado (pedido explícito do autor)

O autor pediu para **reaproveitar, sem reimplementar**, quatro peças e sinalizar no plano as que
não existirem. Resultado do levantamento no código atual (`main`, `f2f184b`):

| Peça pedida | Existe? | O que existe de fato | Como o plano usa |
|---|---|---|---|
| Sandbox local de execução com limite de tempo e memória | **Sim, parcialmente** | `sandbox.runner.execute` (processo genérico isolado: uid por slot, `setsid`, rlimits, relógio de parede, teto de saída, medição por `sandbox-launch`), `sandbox.isolation.run_rlimits`/`prepare_slot_workdir`/`give_to_slot`, `sandbox.judge.judge_test`/`outputs_equal`, `sandbox.types.ExecutionLimits`/`InfraError`. **Não existe um executor de Python**: o único ponto de entrada de alto nível é `run_binary` (binário C++ compilado). | Executa `python3.11 -I -S -B -X utf8 main.py` por `sandbox.runner.execute` com `isolation.run_rlimits(limits)` e julga com `judge.judge_test` — **nenhuma linha do pacote `sandbox` muda**. O invólucro fino (≈30 linhas: montar `argv`, preparar o workdir, chamar `execute`) fica em `src/ai_clients/oracle.py`, não no `sandbox` (a spec, Assumptions, exige reaproveitar o motor "sem alteração"). Informativo (plan.md, S3). |
| Leitor do dataset por problema (`enunciado.md`, `AC_ref.cpp`, `testes.json`) | **Não como unidade** | `dataset.schemas.testes.Testes.from_folder`, `dataset.schemas.metadata.Metadata.from_folder` (validam schema e `problem_id` = nome da pasta). `enunciado.md` e `AC_ref.cpp` são lidos como texto solto em `mutation/__main__._prepare` (`(folder / "AC_ref.cpp").read_text(...)`); não há função reutilizável que devolva "o problema" inteiro. | Compõe as duas funções `from_folder` existentes com duas leituras de texto, dentro de `src/ai_clients/problem.py` (sem criar leitor novo no pacote `dataset`, sem mudar schema). **Decidido (S1 = A, 2026-09-30)**: composição local; nenhum leitor novo no `dataset`. |
| Padrão de registro de comandos da CLI | **Sim** | `mutation/__main__.py`: `Subcommand`, `_REGISTRY`, `register(...)`, `build_parser()` em ordem alfabética, códigos de saída 0/1/2/3/130, `SIGTERM` tratado como `Ctrl+C`. É um **padrão repetido por pacote** (o `dataset` e o `cli` têm o seu), não uma biblioteca compartilhada. | `src/ai_clients/__main__.py` segue o mesmo padrão, com os mesmos códigos de saída. Não se extrai uma biblioteca comum (Princípio IX). |
| Schema de suíte de testes usado pelo motor de avaliação | **Não existe** | O módulo de avaliação (execução das suítes contra AC/WA/mutantes, seção 4 da metodologia) e o de métricas não foram especificados nem construídos (`src/metrics/` não existe). Os únicos contratos de caso de teste existentes são `dataset.schemas.testes.TestCase` (`input`, `output`, Pydantic, `extra="forbid"`) e `sandbox.types.Test` (`input`, `output`, dataclass que o motor consome). | O plano **não cria um schema de avaliação**. Os casos da suíte SLM são gravados com a forma do contrato já existente — `TestCase` (`input`, `output`, reaproveitado por import) — para que o futuro módulo de avaliação os converta em `sandbox.types.Test` sem tradução de campos. O `expected_output` da spec é o campo `output` desse contrato. **Decidido (S2 = A, 2026-09-30)**: esta é a forma dos casos de teste para o módulo de avaliação e para as suítes dos 3 modelos; mudá-la exige alteração deliberada de schema (Princípio IV). |

Outras peças reaproveitadas sem alteração: `dataset.persistence.store` (`atomic_write_json`,
`atomic_write_text`, `dumps_json`, `make_private_dir`, `chown_to_host`), `mutation.dataset_gate.
verify_dataset` (recusa rodar sobre `data/dataset` divergente do manifesto — Edge Case da spec),
`dataset.integrity.packaging` (constantes de zip determinístico, como `mutation.packaging` já faz) e
`cli.consistency.Layer` (camada nova do `python -m cli check`).

---

## R1 — Onde fica o código: `src/ai_clients/`

**Decisão**: pacote `src/ai_clients/` (já previsto no `CLAUDE.md` como "orquestração das chamadas
aos 3 modelos"), comando `python -m ai_clients <subcomando>`. O template de prompt fica onde o autor
o colocou, `src/prompt_templates/slm_prompt.txt`, lido como arquivo de dados (o `Dockerfile` já copia
`src/` inteiro para a imagem).

**Motivo**: seguir a estrutura de pastas existente, como pedido. Os dois clientes comerciais,
quando especificados, entram no mesmo pacote.

**Alternativas**: pacote `src/slm/` (nome mais preciso para esta feature, mas cria uma segunda
pasta para "chamadas de IA" contrariando o `CLAUDE.md`); subpacote `ai_clients/slm/` (camada extra
sem necessidade enquanto há um modelo só — Princípio IX).

---

## R2 — API do Ollama e isolamento sem estado

**Decisão**: `POST {OLLAMA_BASE_URL}/api/chat` com `"stream": false`, **uma única mensagem**
`{"role": "user", "content": <prompt>}`, sem campo `system`, sem `context`, sem `format`, e
`options` completos e explícitos (R4). Cliente HTTP da biblioteca padrão (`urllib.request`), uma
conexão nova por requisição. Antes da primeira chamada de uma execução, `GET /api/version` e
`GET /api/tags` registram a versão do Ollama e o `digest` do modelo (identificador exato, FR-003),
gravados no `run.json` **e** repetidos em cada `attempt_<n>.generation.json` (decidido em
2026-09-30, revisão de consistência A1), para que cada resultado persistido se identifique sozinho;
um `digest` de tentativa diferente do `run.json` é dano (data-model §4).

**Motivo**: `/api/chat` com lista de mensagens de tamanho 1 é sem estado por construção — não há
como uma chamada herdar histórico. `/api/generate` devolve `context` (tokens da conversa) que, se
reenviado, carregaria estado; evitá-lo elimina o risco. O *cache* de prefixo de KV do Ollama entre
requisições é uma otimização de desempenho que não muda o texto de entrada do modelo, não é
histórico de conversa. `urllib` evita dependência nova (Princípio IX); a requisição é um JSON
simples, não precisa de *streaming*.

**Observação registrada**: sem mensagem `system`, o Ollama aplica o *system prompt* padrão do
Modelfile do modelo; ele faz parte do modelo identificado pelo `digest` registrado, portanto é
estado fixo e auditável, não estado entre chamadas.

**Alternativas**: `/api/generate` com `raw: true` e o *chat template* do Qwen escrito à mão (controle
total, mas duplica o template do modelo e é frágil); SDK `ollama` para Python (dependência nova sem
ganho); `httpx` (idem).

**Verificação automática (SC-005)**: o cliente falso dos testes registra cada corpo de requisição e
os testes afirmam, para toda chamada, `len(messages) == 1`, ausência de `context`, e que nenhum
objeto do cliente guarda respostas anteriores.

---

## R3 — `num_ctx` e `num_predict` (FR-008, medido)

**Medição (2026-09-30)**, tamanho em caracteres do prompt montado (template + `context_data` +
primeiro teste público), 200 problemas:

| Cenário | mín. | mediana | p95 | máx. |
|---|---|---|---|---|
| caixa-preta (só enunciado) | 3.163 | 4.618 | 5.809 | 6.701 |
| caixa-branca (só `AC_ref.cpp`) | 3.053 | 3.593 | 4.427 | 5.469 |
| híbrido (os dois) | 3.784 | 5.224 | 7.200 | **7.870** (`61_B`) |

Componentes: template ≈ 2,9 mil caracteres; `enunciado.md` mediana 1.728 (máx. 3.713); `AC_ref.cpp`
mediana 690 (máx. 2.541); primeiro teste público mediana 18 (máx. 152, `1371_C`). Todos os 200
problemas têm pelo menos um teste público (1 a 4; mediana 2).

**Medição com o prompt real (2026-09-30, `python -m ai_clients generate --dry-run` sobre os 200
problemas, T027)**: a tabela acima foi medida antes da redação final do template (ajuste de FR-007)
e sem os sub-rótulos `<problem_statement>`/`<reference_solution_cpp>` de R5. Com o prompt
exatamente como o código o monta: **600 chamadas previstas**; maior prompt caixa-preta **6.896**
caracteres (`61_B`), caixa-branca **5.674** (`893_C`), híbrido **8.118** (`61_B`). Na mesma
estimativa pessimista de 2,5 caracteres por *token*, ≈ 3.250 *tokens* + 4.096 de saída ≈ 7.350,
ainda abaixo de 8.192: a decisão abaixo não muda.

**Decisão**: `num_ctx = 8192`, `num_predict = 4096`. **Revisada em 2026-10-04 (R13, item 4)**:
`num_predict = 5120`, com a razão caracteres/*token* medida no piloto 1.

**Motivo**: mesmo numa estimativa pessimista de 2,5 caracteres por *token* (o normal para texto em
inglês e C++ no tokenizador do Qwen2.5 fica entre 3 e 4), o maior prompt dá ≈ 3.150 *tokens*;
somado ao teto de saída (4.096), fica em ≈ 7.250, abaixo de 8.192 com folga. `num_ctx` inclui
prompt e resposta; o padrão do Ollama (2.048 ou 4.096, conforme a versão) truncaria o prompt **em
silêncio**, por isso é explícito. 8.192 está dentro do contexto nativo do Qwen2.5-Coder-7B
(32.768) e cabe em GPU de 8 GB com a quantização padrão.

**Guarda em tempo de execução** (a contagem real de *tokens* só existe na resposta do Ollama):
toda resposta registra `prompt_eval_count`; se `prompt_eval_count + num_predict > num_ctx`, a
execução para com erro de configuração (código 3), **sem** gravar a tentativa e sem consumir o
orçamento — o prompt pode ter sido truncado, e aceitar a resposta violaria FR-008. O máximo real de
`prompt_eval_count` medido no piloto (quickstart, Nível 4) é propagado para a metodologia.

**Alternativas**: `num_ctx = 4096` (não comporta prompt + 4.096 de saída); `16384` (dobra a memória
do KV *cache* sem necessidade medida); tokenizar localmente com `transformers` (dependência pesada
só para uma estimativa que a guarda já cobre).

---

## R4 — Parâmetros de amostragem **[DECIDIDO, 2026-09-30 — S4 = A]**

**Decisão**: `temperature = 0.7`, `top_p = 0.8`, `top_k = 20`, `repeat_penalty = 1.05` — a
configuração de geração publicada pelos autores do Qwen2.5-Coder-7B-Instruct
(`generation_config.json`). Todos enviados explicitamente em `options`, para que um padrão do
Modelfile ou de uma versão do Ollama não mude o experimento em silêncio. **Seed base = 42** (a seed
do projeto, metodologia 1.4); seed da tentativa `n` = `42 + n` → 43 a 48 (FR-020).

**Motivo**: a metodologia e a spec exigem temperatura fixada e registrada (FR-025) mas não dão o
valor. **Achado que restringe a escolha**: com `temperature = 0` a decodificação é gulosa e a seed
não tem efeito — as 6 tentativas de um mesmo problema × cenário produziriam a **mesma** resposta, e
o mecanismo de retentativa (FR-018 a FR-022) seria inútil. A temperatura precisa ser maior que 0.
Usar os valores do fabricante evita escolher um número sem base.

**Decisão dos autores**: proposta no plano e confirmada em 2026-09-30 (Milena, S4 = A); registrada
na metodologia (seção 3; item 27 da seção 6 resolvido).

**Alternativas**: `temperature = 0.2` (mais conservadora; retentativas mais parecidas entre si);
`0` (descartada pelo achado acima); deixar os padrões do Ollama (não registrável com precisão).

---

## R5 — Montagem do prompt (FR-004, FR-005)

**Decisão**: o template é carregado **uma vez** por execução e seu SHA-256 é registrado. A montagem
substitui três marcadores literais que já existem no arquivo do autor, cada um exigido
**exatamente uma vez** (senão, erro de configuração antes de qualquer chamada):

- `(scenario-dependent content)` → conteúdo de `<context_data>` do cenário;
- `(dataset example input)` → `input` do **primeiro** teste público de `testes.json`;
- `(dataset example output)` → `output` do mesmo teste.

Conteúdo de `<context_data>` por cenário, com sub-rótulos fixos para que o híbrido seja a união
literal dos outros dois:

```text
black_box:  <problem_statement>\n{enunciado.md}\n</problem_statement>
white_box:  <reference_solution_cpp>\n{AC_ref.cpp}\n</reference_solution_cpp>
hybrid:     <problem_statement>…</problem_statement>\n\n<reference_solution_cpp>…</reference_solution_cpp>
```

Fora de `<context_data>`, o prompt dos 3 cenários de um problema é idêntico byte a byte (testado).

**Motivo**: mantém o arquivo do autor intacto (sem trocar os marcadores por uma sintaxe de template)
e torna qualquer edição acidental do template detectável (marcador sumido ou duplicado; hash
diferente no `--resume`, R8).

**Alternativas**: `string.Template`/Jinja (exigiria reescrever o template); colar o conteúdo sem
sub-rótulos (no híbrido, enunciado e código ficariam sem fronteira).

### R5a — Lacuna do template frente a FR-007 — **resolvida (S5 = A, 2026-09-30)**

FR-007 exige que o prompt instrua o modelo a (1) respeitar as restrições declaradas no enunciado e
(2) limitar a quantidade de elementos por entrada ao que ele consegue escrever por completo. O
`slm_prompt.txt` atual **não cumpre** nenhuma das duas: a RULE 2 pede "the maximum size allowed by
the constraints" (o oposto de (2) — uma entrada com 2·10⁵ números estoura `num_predict` e a
resposta sai truncada, `done_reason = "length"`, virando falha de interpretação) e não há frase
explícita sobre respeitar as restrições. O texto do prompt é desenho experimental e é do autor;
**decisão (2026-09-30, Milena)**: o template foi editado com a redação abaixo (RULE 2, item 2, e uma
frase nova ao fim da RULE 3), antes de qualquer chamada real — o SHA-256 gravado no `run.json` é o
do template já corrigido:

> - the largest case you can write out IN FULL (every value within the constraints stated in the
>   context; keep each input short enough to be written completely — never truncate or abbreviate)
>
> Every value in every input MUST respect the constraints stated in the context.

**Revisão de 2026-10-04 (R13, item 4)**: no piloto 1, 3 respostas foram cortadas por `num_predict`;
o item 2 da RULE 2 passou a ser "large cases: Use values up to the maximum allowed by the constraints,
but keep the NUMBER of elements in each input small enough to write out fully (e.g., at most ~100
elements)." e o item 1 perdeu "(including empty input if allowed)" (R13, item 2).

---

## R6 — Interpretação da resposta (FR-009, FR-010, Edge Cases)

**Decisão**: parser determinístico, sem correção heurística, sobre o texto cru (depois de só
`\r\n` → `\n`):

1. Cada uma das tags de topo `<edge_cases_analysis>`, `<reference_py>`, `<inputs>` deve abrir e
   fechar **exatamente uma vez**, nesta ordem (a que o prompt pede; até o template de R17 era
   `<edge_cases_analysis>`, `<inputs>`, `<reference_py>`), sem se sobrepor. Qualquer outra situação (ausente,
   duplicada, fora de ordem, sem fechamento) → `unparseable_response`, com o motivo exato
   (`missing_block:<tag>`, `duplicated_block:<tag>`, `wrong_order`, …).
2. Texto fora dos três blocos (preâmbulo, comentário final) é **ignorado e contado**
   (`extraneous_chars`), não corrigido — não altera o conteúdo de nenhum bloco.
3. Dentro de `<inputs>`: um ou mais pares `<input>…</input>` não aninhados; texto não branco entre
   eles → falha (`text_between_inputs`). Nenhum `<input>` → falha (`no_inputs`).
4. Normalização de cada entrada: remover linhas totalmente brancas do início e do fim e garantir
   exatamente um `\n` final. Espaços **dentro** das linhas não são tocados. Entrada vazia depois
   disso: até 2026-10-04 era falha (`empty_input`); **desde R13 (item 2)** é descartada sozinha e
   contada (`empty_inputs`), e só "todas vazias" é falha (`only_empty_inputs`).
5. `<edge_cases_analysis>` e `<reference_py>` vazios (só espaço) → falha (`empty_block:<tag>`).
   O código Python é gravado como veio (só `\r\n` → `\n` e linhas brancas das pontas removidas); se
   o modelo o embrulhar numa cerca Markdown (```` ```python ````), ela **não** era removida — o código
   virava `SyntaxError` e falhava nos testes públicos. **Revisado em 2026-10-04 (R13, item 1)**: a
   cerca que envolve o código inteiro é removida e registrada (`markdown_fence_removed`); qualquer
   outra continua como veio.
6. Entradas repetidas dentro da mesma resposta **não** são removidas (fidelidade à saída do modelo);
   a quantidade de duplicatas é registrada na suíte e no relatório, porque infla o tamanho da suíte
   (variável de confusão da spec, FR-012).

**Motivo**: tags únicas + ordem fixa dão uma gramática trivial e totalmente testável por tabela de
casos; ignorar texto externo evita descartar respostas corretas por uma frase de cortesia, sem
alterar o que é interpretado.

**Alternativas**: parser XML (`xml.etree`) — quebra com `<`, `&` em entradas e no código Python;
regex gulosa — ambígua com tags repetidas; extrair o código de qualquer cerca Markdown — correção
heurística vetada pela spec (só a cerca que envolve o bloco inteiro sai, R13).

---

## R7 — Execução do `reference_py` na sandbox (FR-013 a FR-019)

**Decisão**:

- **Interpretador**: o CPython 3.11 base da imagem (`Path(sys.base_prefix)/"bin"/"python3.11"`,
  instalado pelo `uv` em `/opt/python`), **não** o do `venv`: só a biblioteca padrão fica
  disponível. Flags `-I` (isolado: ignora `PYTHON*` e o diretório do usuário), sem `-S` desde 2026-10-05 (o `site` define `exit()`, R15),
  `-B` (sem `.pyc`), `-X utf8` (E/S em UTF-8, já que `-I` ignora `PYTHONIOENCODING`). `env={}`.
- **Isolamento**: `sandbox.runner.execute(..., rlimits=isolation.run_rlimits(limits),
  measured_by_launcher=True)` — o mesmo uid por slot, sem rede (serviço `sandbox`), sem
  capacidades, `RLIMIT_NPROC`/`FSIZE`/`CORE`/`MSGQUEUE` do motor. Um **workdir novo por execução**
  (`prepare_slot_workdir` + `main.py` entregue ao slot), para que uma entrada não deixe estado para
  a próxima.
- **Limites (derivados do problema, nunca fixos — FR-015, FR-016)**:
  `ExecutionLimits(time_limit_seconds = tl × PY_TIME_FACTOR, memory_limit_bytes = ml ×
  PY_MEMORY_FACTOR)`, com `PY_TIME_FACTOR = 10` e `PY_MEMORY_FACTOR = 4`, onde `tl` e `ml` vêm de
  `metadata.json`. O motor já deriva daí a reserva de CPU (`ceil(limite) + 1`) e de parede
  (`limite × 3 + 1`).
- **Veredito**: `sandbox.judge.judge_test(run, esperado, limits)` com os limites acima — mesma
  ordem TLE → MLE → RE → comparação por `outputs_equal` (a regra única do projeto).
- **Testes públicos**: todos os `public_tests` de `testes.json`, na ordem do arquivo, curto-circuito
  no primeiro não-AC → tentativa falha, razão `public_test_failed` (índice e veredito gravados).
- **Entradas geradas**: todas, na ordem da resposta. `TLE` → descarte `timeout`; `RE`/`MLE` →
  descarte `runtime_error` (com o veredito); saída que não é UTF-8 válido → descarte
  `non_utf8_output`. Sobrevive quem termina `OK` dentro dos limites; `output` = `stdout`
  decodificado, **sem** normalização (a comparação futura usa `outputs_equal`). Nenhuma
  sobrevivente → tentativa falha, `all_inputs_failed` (FR-018c, combinação qualquer de erro e
  timeout, conforme a clarificação de 2026-09-29).
- `AC_ref.cpp` **nunca** é compilado nem executado nesta fase (FR-017) — nem é lido pelo `execute`.

**Implementação (2026-10-01)**: `ai_clients/oracle.py`. Nos testes públicos o veredito é o
`judge_test` completo; nas entradas geradas a chamada é `judge_test(run, "", limites)` e só
importam `TLE` (→ `timeout`) e `MLE`/`RE` (→ `runtime_error`, com o veredito), já que não há
saída com que comparar — `AC`/`WA` contra a string vazia só dizem que o programa terminou bem;
a entrada que termina bem é mantida se o `stdout` for UTF-8 válido, com `verdict` nulo. O
`execute` lê do problema só `metadata.json` e `testes.json` (`problem.load_judge_input`), então
`AC_ref.cpp` nem é aberto nesta fase. Código e entradas são codificados com `surrogatepass`: um
*surrogate* avulso vindo da resposta do modelo chega ao interpretador, que rejeita o código
(erro de execução), em vez de derrubar o comando com `UnicodeEncodeError`. Um único slot (0):
`isolation.kill_slot_processes(0)` no início e no fim do comando.

**Medição de referência** (2026-09-30): limites de tempo 0,5 s (4 problemas), 1 s (101), 1,5 s
(1), 2 s (82), 3 s (8), 4 s (2), 5 s (1), 10 s (1); limites de memória 61 MiB (7), 122 MiB (1),
244 MiB (183), 252 MiB (1), 488 MiB (8). Com os fatores: 5 s a 100 s de CPU; 244 MiB a 1,9 GiB de
espaço de endereçamento.

**Motivo dos fatores**: o tempo só protege contra laço infinito (FR-016) — CPython é tipicamente uma
ou duas ordens de grandeza mais lento que C++ `-O2`; 10× cobre soluções diretas sem transformar
timeout em regra de desempenho. A memória é espaço de endereçamento (`RLIMIT_AS`), e o interpretador
sozinho reserva dezenas de MiB antes de ler a entrada; com 61 MiB (7 problemas) uma solução correta
poderia falhar só por ser Python. O fator 4 mantém o limite **derivado** do problema (proporcional)
e não um piso fixo. **Ambos os fatores ficam para confirmar no piloto** (quickstart, Nível 4):
se alguma solução correta falhar por limite nos problemas de 61 MiB, o fator é revisto e a
revisão propagada.

**Alternativas**: memória igual à do problema (risco medido acima); piso fixo de memória (seria um
limite hardcoded, vetado); executar o Python fora do motor (viola o Princípio V); acrescentar
`run_python` ao pacote `sandbox` (mudaria o módulo que a spec manda reaproveitar sem alteração).

---

## R8 — Estados, retomada e escrita atômica (FR-021, FR-026, SC-001, SC-004)

**Decisão**: cada fato é um **arquivo imutável**, escrito uma única vez por
`store.atomic_write_json` (temporário no mesmo diretório + `fsync` + `os.replace`). O estado de uma
combinação problema × cenário é **derivado só dos arquivos presentes** (tabela em
[data-model.md](./data-model.md#4-máquina-de-estados-de-uma-combinação)):

- `attempt_<n>.generation.json` — gravado pelo `generate` depois da resposta do modelo (inclui a
  resposta crua, FR-014, e o resultado da interpretação);
- `attempt_<n>.execution.json` — gravado pelo `execute` depois de avaliar a tentativa inteira;
- `suite.json` — estado terminal (`accepted` ou `discarded`), **função pura** dos arquivos de
  tentativa. Se a execução for interrompida entre o `attempt_<n>.execution.json` e o `suite.json`,
  a próxima execução só recalcula o `suite.json`.

Interrupção no meio de uma chamada ao modelo ou de uma avaliação: nada foi gravado para aquela
tentativa; a retomada refaz a mesma chamada (mesma seed) ou a mesma avaliação. Uma combinação com
`suite.json` nunca é tocada de novo.

Falha de interpretação é conhecida já na fase de geração: o `generate` grava a tentativa como
falha e **já faz a chamada seguinte** (próxima seed) na mesma execução, sem esperar uma rodada de
`execute` — não há nada a executar. Rodadas `generate` ↔ `execute` só são necessárias para as
falhas (b) e (c), que dependem da execução (FR-021).

**Trava**: `flock` em `data/suites/slm/.lock` (mesmo mecanismo de `mutation.persistence.
exclusive_run`): um comando por vez sobre a árvore, inclusive entre os serviços `app` e `sandbox`
(montam o mesmo `./data`).

**`--resume`** (pedido do autor): `generate` sem `--resume` só roda se `data/suites/slm/run.json`
**não** existir (execução nova, cria o `run.json`); se existir, recusa (código 2) dizendo para usar
`--resume`. Com `--resume`, recalcula a configuração da execução — **todos os campos do
`RunConfig` exceto `created_at`**: `model`, `model_digest`, `model_quantization`, `ollama_version`,
`options` (amostragem, `num_ctx`, `num_predict`), `seed_base`, `max_attempts`, SHA-256 do template,
SHA-256 do manifesto do dataset e os dois fatores de limite — e **recusa** (código 2, listando o que mudou) se diferir do
`run.json`: uma retomada nunca mistura tentativas de configurações diferentes sob a mesma execução.
A etiqueta de hardware **não** faz parte dessa identidade — é gravada por chamada (FR-025), e trocar
de máquina no meio é permitido e fica registrado. `execute` não tem `--resume`: não inicia
execução nova (exige o `run.json`) e só processa o que está pendente, então é sempre retomada.

**Implementação (2026-10-01)**: `store.combination_state` lê e confere **todos** os arquivos da
combinação antes de derivar o estado, e com o `run.json` também o `model_digest` de cada tentativa
e, numa combinação terminal, que o `suite.json` é byte a byte o que `finalize` grava a partir dos
arquivos (a mesma função monta os dois). Divergência → `DamagedCombination`, com a lista
`missing:`/`changed:`/`inconsistent:` (lista completa em [contracts/cli.md](./contracts/cli.md));
`generate` e `execute` a reportam, seguem com as demais e saem com 1. Verificado com testes que
interrompem (`KeyboardInterrupt`) nos quatro pontos — durante a chamada, entre a gravação de uma
geração e a próxima, no meio da avaliação, entre a execução e o `suite.json` — e comparam a árvore
final com a de uma execução sem interrupção (`tests/ai_clients/test_resume.py`): mesmas
pastas e bytes, fora `created_at`/`requested_at`; a chamada interrompida volta com a mesma seed e
nenhuma outra se repete. O `--resume` compara campo a campo (`RunConfig.differences`), um teste por
campo. Quem encontra uma combinação `finalizable` (o `generate` ou o `execute`) grava o
`suite.json`.

**Alternativas**: um arquivo por combinação reescrito a cada passo (janela de corrupção lógica
maior, apesar da escrita atômica); banco SQLite (dependência de formato binário, pior para
empacotar e auditar); retomada implícita sem `--resume`, como no `mutation` (o autor pediu a opção
explícita; ela também protege contra continuar por engano com o template ou o modelo alterados).

---

## R9 — Falha de infraestrutura vs. falha de conteúdo (FR-018a, SC-007)

**Decisão**: o cliente classifica toda chamada em quatro desfechos, e só os dois últimos gravam
uma tentativa:

| Desfecho | Exemplos | Efeito |
|---|---|---|
| `OllamaUnavailable` (infraestrutura) | recusa de conexão, DNS, *timeout* de conexão/leitura (`OLLAMA_HTTP_TIMEOUT_S`, padrão 900 s), HTTP 5xx, túnel fora do ar (página de erro do ngrok com `ERR_NGROK_`, mesmo com HTTP 4xx), corpo que não é JSON | não grava nada; espera com recuo exponencial (5 s, 10 s, 20 s, … até 60 s) e **repete a mesma chamada com a mesma seed**, até `OLLAMA_MAX_INFRA_RETRIES` repetições consecutivas (padrão 30); cada espera é impressa. Atingido o teto: código 3 (`ollama unavailable after N consecutive retries (<último motivo>); nothing was recorded for <id> <scenario> attempt <n>; run generate --resume when the service is back`), sem gravar nada e sem consumir tentativa. O contador zera a cada resposta recebida |
| `OllamaConfigError` (configuração) | HTTP 4xx do próprio Ollama (modelo não instalado, opção inválida), `digest` do modelo diferente do `run.json`, guarda de `num_ctx` (R3) | não grava nada; aborta com código 3 e mensagem acionável |
| resposta recebida | qualquer 200 com `message.content` | grava `attempt_<n>.generation.json` (a interpretação decide se é falha `unparseable_response`) |
| `ModelRepetition` (falha do modelo; desde 2026-10-04, R13 item 3) | HTTP 500 com `token repeat limit reached` no corpo | grava `attempt_<n>.generation.json` sem resposta (`model_failure.reason = "repetition"`); a tentativa falha com a razão `repetition` e a próxima seed é chamada |

`done_reason` (`"stop"` ou `"length"`) é sempre gravado; `"length"` **não** é tratado à parte — uma
resposta truncada normalmente não fecha `</reference_py>` e cai na falha de interpretação pelo
parser; se fechar, segue o fluxo normal. O relatório conta `done_reason = "length"` por cenário
(desde R13) para medir o efeito de FR-007.

**Motivo**: separa com precisão o que é do ambiente (nunca consome orçamento) do que é do modelo.
O recuo em testes usa relógio e `sleep` injetados (sem espera real).

**Teto e *timeout* configuráveis (decidido em 2026-09-30, revisão de consistência U1)**: um
*timeout* fixo de 900 s poderia ser curto para um Ollama em CPU (4.096 *tokens* de saída a poucos
*tokens* por segundo passam disso); como *timeout* é falha de infraestrutura, a mesma chamada se
repetiria para sempre sem nunca gravar nada. Por isso o *timeout* de leitura e o teto de repetições
consecutivas vêm do `.env` (R12), com padrão em `config.py`, e o piloto (quickstart, Nível 4) mede
o tempo máximo real por chamada para validar o padrão. Nenhum dos dois entra no `run.json`: não
mudam o conteúdo de nenhuma resposta, só quanto se espera por ela. **Alternativas**: sem teto (a
redação anterior da spec — rejeitada porque um *timeout* curto demais vira laço infinito
silencioso); teto fixo no código (rejeitado: o valor certo depende do hardware do operador).

**Túnel fora do ar (achado no piloto, 2026-10-01)**: com o Ollama exposto por um túnel do ngrok, a
queda do túnel responde **HTTP 404** com uma página de texto que traz `ERR_NGROK_3200` ("The endpoint
... is offline"). Pela regra acima (todo 4xx é configuração) o comando parou com código 3 em vez de
esperar o túnel voltar — numa execução de centenas de chamadas, uma queda curta pararia tudo.
Decisão: resposta HTTP de erro cujo corpo contém `ERR_NGROK_` é `OllamaUnavailable` (espera e
repete a mesma chamada com a mesma seed); o 4xx do próprio Ollama continua sendo configuração.
Nada foi gravado na ocorrência real (a queda veio antes da primeira chamada ao modelo).

---

## R10 — Relatório, empacotamento e verificação (FR-027, FR-028)

**Decisão**: mesmo desenho do módulo `mutation`:

- `python -m ai_clients report` → `manifests/slm_generation_report.json` (versionado): contagens
  por estado e cenário, taxa de descarte por cenário e total (sobre as 600 combinações, N nunca
  reduzido), distribuição do tamanho das suítes aceitas (mín./quartis/máx. e histograma), funil de
  falhas por razão e por número da tentativa, entradas descartadas por razão, duplicatas,
  `done_reason = "length"`, cercas Markdown removidas e entradas vazias descartadas (as três por
  cenário, R13), *tokens* (soma, máximo de `prompt_eval_count`), duração, seeds por
  combinação e etiquetas de hardware distintas com a contagem de chamadas de cada.
- `python -m ai_clients package` → `data/slm_suites.zip` determinístico (constantes de
  `dataset.integrity.packaging`, raiz `suites/slm/` para que `unzip -d data/` caia no caminho que os
  comandos leem) + `manifests/slm_suites.manifest.json` (SHA-256 por arquivo e do zip). Recusa
  se houver combinação sem `suite.json` (pacote só de execução completa, D3).
- `python -m ai_clients verify [--extracted data/suites/slm]` → confere zip e/ou árvore contra o
  manifesto.
- `cli check` ganha a camada `slm_suites` (Princípio II, `docs/verificacao-consistencia.md`): para
  cada problema do dataset, uma pasta com os 3 cenários, cada um com `suite.json` e com as
  tentativas numeradas sem buraco; nada sobrando; `--deep` confere hashes contra o manifesto. Sem
  manifesto (antes do `package`), a camada emite aviso, como a dos mutantes antes do empacotamento.

**Implementação (2026-10-01)**: `ai_clients/report.py`, `packaging.py`, `schemas/report.py`,
`schemas/manifest.py` e a camada `SLM_SUITES_LAYER` de `cli.consistency`. Regras fixadas no
caminho (detalhe em [contracts/file-formats.md](./contracts/file-formats.md) §5 e §6): bloco
`attempts` (`total`, `failed`) no relatório para validar o funil; quartis por interpolação linear;
`input_discards` sobre todas as tentativas executadas e `duplicate_inputs` só das suítes aceitas;
manifesto com a chave `slm_suites_zip`, como o `mutants_zip` dos mutantes; o `package` toma a
trava de `data/suites/slm/`, recusa árvore incompleta, danificada ou com entrada que não é
problema × cenário do dataset, e refaz o relatório logo depois do zip. **Divergência decidida na
implementação**: na camada `slm_suites` do `cli check`, o que falta é aviso até o manifesto
existir (com ou sem `--deep`), porque o piloto e a execução completa começam por `cli check --deep`
com a árvore ainda vazia ou pela metade; depois do `package`, é falha.

**Alternativas**: relatório impresso só no terminal (sem proveniência versionada, contraria FR-027).

---

## R11 — Paralelismo

**Decisão**: nenhum nesta feature. `generate` faz uma chamada por vez; `execute` usa o slot 0.

**Motivo**: o Ollama numa GPU atende uma geração por vez (requisições paralelas enfileiram ou,
com `OLLAMA_NUM_PARALLEL`, mudam o *batching* e podem mudar a saída para a mesma seed); a execução de
Python é curta frente à chamada ao modelo. Sem tempo medido, não se antecipa `--workers`
(Princípio IX). Se o piloto mostrar o `execute` como gargalo, `--workers` reaproveita o padrão de
`mutation.runtime` numa revisão deste plano.

---

## R12 — Configuração por `.env` e rede do serviço `app` (FR-003, FR-003a)

**Decisão**: duas variáveis novas em `.env` / `.env.example`, lidas só pelo `generate`:

- `OLLAMA_BASE_URL` — endereço do Ollama (ex.: `http://host.docker.internal:11434` para o Ollama da
  própria máquina, ou `http://<servidor>:11434` para um servidor remoto);
- `OLLAMA_HARDWARE_LABEL` — texto livre informado pelo operador (ex.: `RTX 3060 12GB, Ryzen 5 5600`),
  gravado em cada tentativa; nunca autodetectado (clarificação de 2026-09-29).

Ausência de qualquer uma → `generate` recusa com código 2 (exceto em `--dry-run`, que não chama o
modelo).

Mais duas variáveis **opcionais** (R9), com padrão em `ai_clients/config.py`:

- `OLLAMA_HTTP_TIMEOUT_S` — *timeout* de leitura de uma resposta, em segundos (padrão `900`);
- `OLLAMA_MAX_INFRA_RETRIES` — repetições consecutivas de uma mesma chamada por falha de
  infraestrutura antes de o comando parar (padrão `30`; com o recuo de 5 s a 60 s, ≈ 27 min de
  espera).

Valor que não é inteiro positivo → código 2. O nome do modelo (`qwen2.5-coder:7b`) é constante do desenho experimental em
`ai_clients/config.py`, não `.env`.

⚠ **Sinalizado** (plan.md, S6): no Linux, um contêiner não resolve `host.docker.internal` sem
`extra_hosts: ["host.docker.internal:host-gateway"]` no serviço `app` do `docker-compose.yml`. É uma
linha a acrescentar (só no `app`; o `sandbox` continua `network_mode: none`).

---

## R13 — Revisão depois do piloto 1 (2026-10-04)

**Piloto 1 (2026-10-01 a 2026-10-03)**: 4 problemas (`1000_B`, `1005_C`, `1008_B`, `1_B`) × 3
cenários = 12 combinações, todas terminais (5 aceitas, 7 descartadas); mais 2 combinações de `1009_B`
começadas por um `generate` sem `--problem` interrompido à mão (`black_box` com a tentativa 1
esperando `execute`; `white_box` com 2 tentativas não interpretadas). 57 chamadas no total; maior
`prompt_eval_count` 2.044 (`1000_B` híbrido); chamada mais longa 166 s. Das 57: 6 não interpretadas
(3 `unclosed_block:inputs`, todas com `done_reason = "length"` — 2 no híbrido, 1 na caixa-branca —, e
3 `empty_input`); 51 interpretadas e executadas (exceto 1 pendente): 31 reprovadas no teste público
por WA, 14 por RE, 5 aceitas. **Todas as 6** respostas com cerca Markdown em volta do `<reference_py>`
eram do híbrido, e as 6 reprovaram no teste público por RE (`SyntaxError`). Num `generate` do piloto
o Ollama respondeu HTTP 500 `token repeat limit reached` e, por R9, a mesma seed foi repetida até o
teto de 30 repetições, sem gravar nada.

Decisões (Milena, 2026-10-04), todas antes do piloto 2, que começa uma execução nova (o template, o
`num_predict` e a versão do Ollama mudaram, e uma execução nunca mistura configurações, R8):

1. **Cerca Markdown — removida só quando envolve o código inteiro** (substitui o item 5 de R6). Depois
   da normalização do bloco, se a primeira linha for exatamente ```` ```python ````, ```` ```py ```` ou
   ```` ``` ```` (espaços à direita tolerados) e a última for exatamente ```` ``` ````, as duas linhas
   saem; qualquer outra cerca (só abertura, no meio do código, outra linguagem, recuada) fica como
   veio. Registrado por tentativa (`parse.markdown_fence_removed`) e somado por cenário no relatório
   (`markdown_fences_removed`). **Motivo**: no piloto a cerca foi o único motivo das 6 RE do híbrido
   e não diz nada sobre a qualidade do teste; a regra é fixa, testada por tabela e contada, então não
   é uma correção heurística. **Alternativa rejeitada**: extrair qualquer bloco cercado de dentro do
   código (heurística aberta, ambígua com mais de uma cerca).
2. **Entrada vazia — descartada sozinha** (substitui o item 4 de R6). A frase "including empty input
   if allowed" saiu do prompt. No parser, um `<input>` vazio depois da normalização é descartado e
   contado (`parse.empty_inputs`, somado por cenário no relatório como `empty_inputs`), sem invalidar
   a tentativa — como já acontece com uma entrada que quebra a solução (R7). Só se **todas** forem
   vazias a resposta é `unparseable_response` com o motivo `only_empty_inputs`. Os índices das entradas
   em `parse.inputs`, na execução e no `suite.json` são os das entradas que sobraram.
3. **`token repeat limit reached` é falha do modelo, não de infraestrutura** (corrige R9). O HTTP 500
   cujo corpo traz esse texto vira `ModelRepetition` no cliente: grava `attempt_<n>.generation.json`
   com `raw_response = ""`, `ollama = null`, `model_failure = {reason: "repetition", detail}` e
   `parse = {ok: false, error: "repetition"}`; a tentativa conta como falha com a razão nova
   `repetition` (quarta razão de `AttemptFailure`) e o `generate` segue para a próxima seed. **Motivo**:
   com a mesma seed a mesma amostragem se repete, então repetir a chamada só gasta tempo até o teto.
   Qualquer outro HTTP 5xx continua sendo infraestrutura.
4. **Respostas cortadas** (`done_reason = "length"`): continuam sem tratamento próprio (caem no parser),
   mas o relatório passa a contá-las **por cenário** (`done_reason_length`, com o total). O pedido
   de "maior caso que dá para escrever" na RULE 2 foi trocado por: "Use values up to the maximum allowed
   by the constraints, but keep the NUMBER of elements in each input small enough to write out fully
   (e.g., at most ~100 elements)." E `num_predict` passa de 4.096 para **5.120**: o piloto mediu no
   mínimo 3,32 caracteres por *token* (caixa-branca de `1000_B`), então o maior prompt dos 200 problemas
   (8.074 caracteres com o template novo, híbrido de `61_B`) fica em ≈ 2.430 *tokens*; 8.192 − 5.120 =
   3.072 de folga para o prompt cobrem até 2,63 caracteres por *token*. A guarda de R3 continua: se
   um prompt não couber, a execução para (código 3), nada é truncado em silêncio.
5. **Por que `generate --resume --problem 1000_B --problem 1005_C --problem 1008_B --problem 1_B` fez 0
   chamadas**: as 12 combinações desses 4 problemas já estavam terminais (`suite.json` gravado), então
   não havia tentativa pendente; o comportamento é o esperado. O único trabalho pendente no disco era de
   `1009_B`, fora da seleção.
6. **`next:` do `execute` repete a seleção**: a linha agora traz os mesmos `--problem`/`--scenario` com
   que o `execute` foi chamado (antes sugeria o `generate --resume` sem nenhum, e copiar essa linha
   no meio de um piloto roda as 600 combinações).

---

## R14 — Piloto 2 e decisões de 2026-10-05

**Piloto 2 (2026-10-04, `data/suites/slm/`; o piloto 1 foi guardado em `data/suites/slm-piloto1/`)**:
execução nova com as decisões de R13 (template `061b7427…`, `num_predict 5120`, Ollama 0.35.0,
`qwen2.5-coder:7b` Q4_K_M, hardware "GPU T4 - Google Colab, 16GB RAM"). 5 problemas (`1000_B`,
`1005_C`, `1008_B`, `1_B`, `61_B`) × 3 cenários = 15 combinações, todas terminais. Números contados
nos arquivos de tentativa:

| | Caixa-preta | Caixa-branca | Híbrido | Total |
|---|---|---|---|---|
| Suítes aceitas | 1/5 | 3/5 | 4/5 | 8/15 |
| Tentativas | 30 | 26 | 18 | 74 |
| Tentativas aceitas | 1 (3%) | 3 (12%) | 4 (22%) | 8 (11%) |

- **Por que as tentativas falharam**: 63 reprovaram num teste público (33 WA, 29 RE, 1 TLE, 0 MLE)
  e 3 não foram interpretadas (2 `unclosed_block:inputs`, ambas com `done_reason = "length"`:
  `1005_C` caixa-preta e `61_B` caixa-branca; 1 `repetition`, `61_B` caixa-preta). Nenhuma caiu por
  `all_inputs_failed`: **as 7 suítes descartadas caíram todas porque a solução Python errou um teste
  público**, nunca por causa das entradas. Lendo o código, são erros de raciocínio do modelo (em
  `1008_B` ele ordena os retângulos ou ignora a rotação; em `1_B` ele faz `int("23C55")`).
- **Problema de 61 MiB**: `1_B` (64.000.000 bytes) reprovou nas 18 tentativas, nos 3 cenários. Não
  dá para afirmar se algum RE foi falta de memória: um `MemoryError` do Python sob o `RLIMIT_AS`
  aparece como RE, não como MLE, e a execução não gravava o `stderr` do teste público (decisão 4).
- **Janela e tempo**: maior `prompt_eval_count` 2.170 (`61_B` híbrido), dentro dos 3.072 de folga;
  a guarda de `num_ctx` não disparou. Mediana de 29 s por chamada (p10 18 s, p90 40 s); a mais longa
  levou 233 s (`61_B` caixa-branca, uma das cortadas), longe dos 900 s de `OLLAMA_HTTP_TIMEOUT_S`. As
  esperas de infraestrutura não ficam gravadas; não há número.
- **Parser**: cerca Markdown removida 4 vezes, todas no híbrido (1 dessas tentativas foi aceita; nas
  outras 3 a solução tinha outros erros); 1 `<input>` vazio descartado sozinho; entradas repetidas
  em 8 tentativas (a maior: 10 em `1000_B` híbrido).
- **Tamanho das suítes aceitas**: 4, 4, 5, 6, 6, 13, 20, 25. Varia muito (seção 6, item 26).
- **Comparação com o piloto 1**: nos 4 problemas comuns, 5 de 12 suítes aceitas nos dois pilotos.
  Tirar a cerca não mudou o total: ela escondia outros erros da solução.
- **Achados para o prompt (piloto 3)**: o modelo abrevia entradas grandes (`1005_C`: `100000 100000
  ... 100000 (120000 times)`); a RULE 2 pede "inputs that look valid but are invalid" enquanto a RULE
  3 exige que todo valor respeite as restrições; a RULE 1 ainda cita "what happens with empty input".
- **Projeção**, se as taxas do piloto se mantiverem nas 600 combinações: cerca de 280 sem suíte
  (≈ 80% da caixa-preta) e ≈ 4,9 tentativas por combinação, ou seja, ≈ 2.960 chamadas × 29 s ≈ 24 h
  de chamadas no mesmo hardware. Com 5 problemas a margem de erro dessas taxas é grande.
- **Falta no piloto**: `python -m cli check --deep` antes do piloto (não há registro de que tenha
  rodado), `python -m ai_clients report` sobre o piloto 2 (o `manifests/slm_generation_report.json`
  no disco é do piloto 1) e a validação real da retomada (T045).

Decisões (Milena, 2026-10-05):

1. **O `AC_ref` nunca gera nem confere as saídas esperadas** (confirma o desenho). Proposta
   rejeitada: usar o `AC_ref` como oráculo das entradas do modelo. **Motivo**: o TCC avalia a IA como
   apoio à escrita de testes unitários, e na vida real não existe uma implementação de referência
   correta para calcular as saídas.
2. **Cada tentativa continua independente** (como hoje). Quando a solução erra um teste público, as
   entradas daquela tentativa saem junto com ela, e a próxima tentativa pede de novo entradas e
   solução. Propostas rejeitadas: (a) guardar as entradas da 1ª resposta interpretável e usar como
   oráculo a primeira solução que passar nos testes públicos; (b) pedir só a solução nas tentativas
   seguintes. Somar as entradas de todas as tentativas foi descartado logo de início: quem erra mais
   ficaria com a suíte maior, o que vicia a TDF e o MS.
3. **O orçamento continua em 6 tentativas.** O custo medido é de 29 s por chamada (mediana); o que
   tem de subir é a taxa de acerto por tentativa, e isso fica para a revisão do prompt.
4. **O teste público que reprova fica registrado no `attempt_<n>.execution.json`**. Em
   `public_tests` entram `failed_output_head` (os primeiros 2.048 bytes do `stdout`, sem
   normalização), `failed_stderr_tail` (o mesmo final de `stderr` que o motor guarda para as entradas
   descartadas), `failed_cpu_time_s` e `failed_peak_rss_bytes`. A saída esperada não é copiada (é a
   do `testes.json` no `failed_index`). Os quatro campos são nulos sem falha e nos registros do
   piloto 2, gravados antes de eles existirem; por isso o `schema_version` continua 1. Isso responde
   o que a T037 pede (se alguma solução certa caiu por memória ou tempo) e permite diagnosticar os
   descartes sem ler o código à mão.
5. **O próximo passo é revisar o prompt**, o que abre uma execução nova (piloto 3), com os mesmos 5
   problemas para dar para comparar.
6. **Template revisto** (`src/prompt_templates/slm_prompt.txt`; o texto continua igual nos 3
   cenários fora do `<context_data>`, R5):
   - o primeiro parágrafo avisa que a solução roda primeiro no exemplo e tem de imprimir exatamente
     a saída esperada, senão a resposta inteira é descartada;
   - a RULE 1 pede, no `<edge_cases_analysis>`, o algoritmo passo a passo e uma simulação à mão no
     exemplo, conferindo a saída esperada antes de escrever o código (ataca os WA de raciocínio); e
     perde "what happens with empty input" e "what exactly counts as valid vs invalid";
   - a RULE 2 pede **de 10 a 20 entradas, todas distintas** (estabiliza o tamanho da suíte, que
     variou de 4 a 25, e reduz duplicatas e respostas cortadas), e troca "inputs that look valid but
     are invalid" por "tricky inputs that are close to breaking a rule of the definitions but are
     still valid" (a versão antiga contradizia a RULE 3);
   - a RULE 3 proíbe abreviar ("...", intervalos, "(repeated N times)") e manda diminuir a entrada
     que não couber;
   - a RULE 4 manda seguir o algoritmo do `<edge_cases_analysis>`, usar só a biblioteca padrão, ler
     a entrada de uma vez (`sys.stdin.read().split()`, salvo quando os espaços de uma linha
     importam), evitar recursão funda (ou chamar `sys.setrecursionlimit`) e imprimir no formato do
     exemplo (ataca parte dos RE);
   - os itens do `<task>` acompanham.

   **Medido** (template novo sobre os 200 problemas): o template passa de 3.065 para 3.984
   caracteres; o maior prompt passa de 8.074 para **8.993** (híbrido, `61_B`; caixa-preta 7.771,
   `61_B`; caixa-branca 6.549, `893_C`). No piloto 2 o híbrido de `61_B` deu 3,72 caracteres por
   *token*, o que dá ≈ 2.420 *tokens* para o prompt novo, dentro dos 3.072 de folga; mesmo na razão
   mínima medida (3,32, piloto 1) seriam ≈ 2.710. `num_ctx` e `num_predict` não mudam, e a guarda
   de R3 continua. A saída tende a crescer (análise mais longa e até 20 entradas); o piloto 3 mede
   as respostas cortadas.

   **Rejeitado**: (a) dizer na caixa-branca para não traduzir o C++. Fora do `<context_data>` o
   prompt tem de ser igual nos 3 cenários, e na caixa-branca o código é o único contexto, então a
   regra só baixaria a taxa de acerto. O viés da tradução continua registrado como limitação na
   metodologia. (b) Uma regra no parser que descarta entradas com "...". Em problemas de grade, `.`
   é um caractere válido (por exemplo `#...#`), então a regra descartaria entradas boas.

---

## R15 — Piloto 3 (parcial), bug do `exit()` e piloto com outro modelo (2026-10-05)

**Piloto 3 (2026-10-05, `data/suites/slm/`, template `336634f7…` de R14, `qwen2.5-coder:7b`,
mesmos 5 problemas)**: interrompido pelos autores depois de 37 tentativas, com 5 combinações
terminais (todas aceitas: `1005_C` caixa-preta e híbrido, `61_B` nos 3 cenários) e as outras 10
com 3 de 6 tentativas, todas falhas. Comparado com o piloto 2 (R14):

| | Piloto 2 | Piloto 3 (parcial) |
|---|---|---|
| Tentativas aceitas | 8/74 (11%) | 5/37 (14%) |
| Caixa-preta, tentativas aceitas | 1/30 (3%) | 2/11 (18%) |
| Não interpretadas / cortadas (`length`) | 3 / 2 | 0 / 0 |
| Entradas por resposta | 5 a 43 | 10 a 20 |
| *Tokens* de saída (mediana; máximo) | 667; 5.120 | 1.001; 2.098 |
| Tempo por chamada (mediana; máximo) | 29 s; 233 s | 29 s; 131 s |

O formato da resposta ficou resolvido; as 32 falhas são todas da solução Python nos testes
públicos (17 WA, 15 RE). Com o diagnóstico novo (R14, decisão 4), os RE são: 7 `ValueError` (em
`1_B`, por exemplo, `int("23C55")` e `int("BC")`), 4 `NameError`, 2 `IndexError`, 1
`UnboundLocalError` e 1 `KeyError`. Nenhum chegou perto do limite de memória. `1_B` (61 MiB) errou
as 9 tentativas, e `1000_B` e `1008_B` não tiveram nenhuma aceita. A amostra é representativa em
dificuldade: *rating* mediano de 1.300 nos 5 problemas, contra 1.400 nos 200.

**Bug nosso, corrigido**: 3 dos 4 `NameError` eram `name 'exit' is not defined` (`1008_B`
caixa-branca e híbrido). A solução era executada com `-S`, que não carrega o módulo `site`, e é ele
que define `exit()` e `quit()`. O `-S` saiu (`-I -B -X utf8`); o `site` do CPython base só expõe
`pip` e `setuptools` (conferido na imagem), e continua valendo "só biblioteca padrão" para o que
importa (o teste `import pydantic` continua falhando). Teste de integração novo
(`test_exit_and_quit_exist_as_in_a_normal_python`). Não dá para saber se essas 3 soluções estavam
certas no resto; o piloto seguinte já roda sem o bug.

**Projeção** com ≈ 14% de acerto por tentativa: P(suíte em até 6) = 1 − 0,86⁶ ≈ 60%, ou seja,
**≈ 40% das 600 combinações sem suíte**, ≈ 4,3 tentativas por combinação, ≈ 2.550 chamadas × 29 s
≈ 20 h no T4. Os descartes se concentram nos problemas difíceis, então as métricas sairiam
calculadas sobre conjuntos de problemas diferentes em cada cenário.

Decisões (Milena, 2026-10-05):

1. **Piloto 3 encerrado** neste ponto e guardado como `data/suites/slm-piloto3/`. Já mostrou o
   efeito do prompt, e o bug do `exit()` faria a segunda metade usar uma regra de execução
   diferente da primeira.
2. **Piloto 4 com `qwen2.5-coder:14b`** (mesma família, Q4_K_M, ≈ 9 GB, cabe no T4 de 16 GB), mesmo
   template, mesmos 5 problemas, já sem o `-S`. Serve para medir se um modelo maior reduz os
   descartes o bastante. O tempo por chamada do 14B não foi medido.
3. **`OLLAMA_MODEL` no `.env`** (opcional, padrão `qwen2.5-coder:7b`): troca o modelo sem mexer no
   código. O modelo vai para o `run.json` e o `--resume` recusa outro, então uma execução nunca
   mistura dois modelos. **Alternativa rejeitada**: mudar a constante `MODEL` para o piloto e voltar
   depois (fácil de esquecer, e o modelo do desenho ainda não mudou).
4. **Ainda não decidido** (Milena e Rafael, talvez com a orientação, depois do piloto 4): manter o
   7B e assumir a taxa de descarte, trocar o modelo do experimento para o 14B, ou fazer o SLM prever
   as saídas como o GPT-5.4-mini e o Gemini 3.5 Flash (uma chamada por combinação, sem descarte; as
   saídas erradas viram falsos positivos na TFP; acaba a assimetria de método entre o SLM e os dois
   comerciais, mas muda a metodologia). Critério sugerido: se o 14B deixar mais de ≈ 20% das
   combinações sem suíte, discutir a terceira opção.

## R16 — Piloto 4 (`qwen2.5-coder:14b`) e suíte de reserva (2026-10-05)

**Piloto 4 (2026-10-05, `data/suites/slm/`, `qwen2.5-coder:14b` Q4_K_M, template `336634f7…` de
R14, mesmos 5 problemas, Python já sem `-S`)**: terminou com as 15 combinações terminais. Medido
dos arquivos de tentativa:

| | Piloto 3 (7B, parcial) | Piloto 4 (14B) |
|---|---|---|
| Tentativas aceitas | 5/37 (14%) | 13/40 (32,5%) |
| Suítes aceitas (caixa-preta / caixa-branca / híbrido) | — (interrompido) | 3/5 / 5/5 / 5/5 |
| Falhas | 32 (17 WA, 15 RE) | 27 (16 WA, 11 RE), todas em teste público |
| Entradas por resposta | 10 a 20 | 10 a 21 |
| *Tokens* de saída (mediana; máximo) | 1.001; 2.098 | 1.082; 2.009 |
| Tempo por chamada (mediana; máximo) | 29 s; 131 s | 76 s; 252 s |

As 2 suítes descartadas são de caixa-preta, e todas as 12 tentativas delas reprovaram num teste
público, 11 por WA: `1008_B` (5 vezes `YES` no teste público 1, que espera `NO`; o prompt só
mostra o teste público 0, cuja resposta é `YES`) e `1000_B` (5 vezes `7` em vez de `6` no teste 0,
a mesma leitura errada do enunciado; a primeira foi RE). Nenhuma resposta deixou de ser
interpretada.

Decisões (Milena, 2026-10-05):

1. **Nenhuma combinação pode ficar sem suíte.** O orçamento estrito passa de 6 para **8**
   tentativas (seeds 43 a 50).
2. **Suíte de reserva** (`accepted_fallback`): uma tentativa *pode ser reserva* se a resposta foi
   interpretada, a solução reprovou um teste público por **WA** (não RE, TLE ou MLE) e ao menos uma
   entrada gerada foi mantida. Se as 8 falharem, a melhor das que podem ser reserva vira a suíte,
   sem nova chamada: a que passou mais testes públicos, depois a que manteve mais entradas, depois a
   de menor número. RE/TLE/MLE ficaram de fora porque uma solução que quebra num exemplo válido
   tende a quebrar também nas entradas geradas, e WA é o único caso em que as saídas existem e
   foram produzidas por um algoritmo que termina.
3. Para isso, **uma tentativa que reprova um teste público por WA roda as entradas geradas assim
   mesmo** (o `outcome` continua `public_test_failed`); depois de RE/TLE/MLE nenhuma roda, como
   antes.
4. **Se nenhuma das 8 puder ser reserva**, as tentativas 9 a 12 (seeds 51 a 54) terminam na
   primeira que passar em tudo (`accepted`) ou puder ser reserva (`accepted_fallback`). Só depois de
   12 sem nenhuma das duas a suíte é descartada. O teto existe para um problema em que o modelo
   sempre quebra não fazer o `generate`/`execute` alternar para sempre.
5. **Status próprio** em vez de `accepted`: as saídas esperadas de uma reserva vêm de uma solução
   que sabidamente erra em algum caso, então algum teste dela vai reprovar o `AC_ref` e contar como
   falso positivo, e algum mutante "morto" pode ter sido morto pela saída errada. `suite.json`
   guarda a tentativa escolhida (`accepted_attempt`) e, por tentativa, se ela podia ser reserva
   (`fallback_eligible`); o relatório conta `accepted_fallback` e `fallback_rate` à parte. Como as
   métricas tratam essas suítes fica pendente (metodologia, seção 6, item 31).
6. `run.json` ganha `strict_attempts` (8) e `max_attempts` vai a 12: as árvores dos pilotos 1 a 4
   não são lidas pelo código novo (o `--resume` e o `report` recusam o `run.json` antigo), o que é
   o esperado, porque a regra mudou. O próximo piloto é uma execução nova.

**Alternativas rejeitadas**: aceitar a 8ª tentativa com WA, qualquer que fosse (podia ser uma
resposta não interpretada ou um RE, sem saídas); gerar tentativas extras com o critério relaxado
mesmo havendo uma reserva entre as 8 (gastaria chamadas para obter algo que já existe); marcar a
reserva como `accepted` (a análise não teria como separá-la).

**Custo estimado, não medido**: as entradas de uma tentativa com WA passam a rodar (de 10 a 21
execuções Python a mais por tentativa). O tempo dessa execução não foi medido nos pilotos.

## R17 — Template revisto depois do piloto 4 (2026-10-06)

**Decisão (Milena, 2026-10-06)**: o texto de `src/prompt_templates/slm_prompt.txt` foi trocado
inteiro (SHA-256 `fc9757e8…`, era `336634f7…` de R14; 3.361 caracteres, eram 3.984). Os três
marcadores, o `<few_shot_example>` e a composição dos cenários não mudam. O que muda:

1. **Ordem dos blocos**: `<edge_cases_analysis>`, `<reference_py>`, `<inputs>`. A solução vem antes
   das entradas. O parser (R6, regra 1) passou a exigir essa ordem; a antiga agora é `wrong_order`.
   Um teste confere que a ordem do OUTPUT FORMAT do template é a mesma que o parser lê.
2. **Três passos** (STEP 1 a 3) no lugar das quatro regras. A análise tem no máximo 15 linhas e
   reescreve o formato de entrada, as restrições e a regra exata da resposta (igualdade, empate,
   limites, *off-by-one*), e então simula o exemplo à mão.
3. **Caixa-branca**: se `<context_data>` só tem código, o modelo deve inferir o comportamento e o
   formato de entrada pela forma como o código lê a entrada. O texto continua igual nos 3 cenários.
4. **Solução**: o algoritmo mais simples que seja obviamente correto, até força bruta; começa com
   `import sys`; script plano, com toda variável definida antes do uso (alvo dos `NameError` e
   `UnboundLocalError` de R15); `sys.setrecursionlimit(10**6)` se precisar de recursão; formato de
   saída exato; sem cerca Markdown. Sai o aviso de que a resposta inteira é descartada se a solução
   errar o exemplo.
5. **Entradas**: sem contagem pedida (era de 10 a 20); cada entrada com no máximo ≈ 50 elementos e
   20 linhas (era ≈ 100 elementos); nenhuma vazia, inválida ou repetida; se a entrada começa pelo
   número de casos, ele precisa bater com os casos escritos; lista de cobertura (menor caso, cada
   fronteira e seus vizinhos, valores extremos para *overflow*, elementos iguais, dados ordenados e
   invertidos, alguns casos médios).

**Efeito no tamanho do prompt (calculado, não medido)**: o maior prompt de R14 (híbrido, `61_B`,
8.993 caracteres) cai para ≈ 8.370, porque só o template muda. `num_ctx`/`num_predict` não mudam.

**Efeito nas execuções**: o `--resume` recusa uma árvore criada com outro template, então o piloto
seguinte é uma execução nova (o que já valia por R16, decisão 6). O efeito do template novo sobre a
taxa de acerto e o tamanho das suítes não foi medido.

## R18 — Nenhuma combinação sem suíte (2026-10-06)

**Decisão (Milena, 2026-10-06, `/speckit-clarify`; spec FR-022 a FR-022d)**: o descarte depois de 12
tentativas (R16) deixa de existir no fluxo normal. Ordem:

1. Tentativas 1 a 8 (seeds 43 a 50): `accepted` na primeira que passa em todos os testes públicos.
2. Nenhuma passou: reserva `accepted_fallback` entre as 8 que falharam só por WA, com o desempate
   de R16. Sem chamada nova.
3. Nenhuma das 8 pode ser reserva: tentativas 9 a 20 (seeds 51 a 62), parando na primeira que for
   `accepted` ou puder ser reserva.
4. Depois da 20ª sem nenhuma das duas: `accepted_low_confidence` = a **primeira** das 20 cuja
   solução manteve ao menos uma entrada gerada, mesmo tendo reprovado um teste público por RE, TLE
   ou MLE. Para isso, as entradas geradas passam a rodar depois de **qualquer** reprovação em teste
   público (em R16, só depois de WA).
5. Nenhuma das 20 serve: **predição**. O mesmo modelo recebe um segundo template,
   `src/prompt_templates/slm_predict_prompt.txt` (texto dos autores), com os mesmos cenários e o
   mesmo exemplo, que pede `<edge_cases_analysis>` e `<tests>` (cada `<test>` com `<input>` e
   `<output>`), sem solução Python, com as mesmas regras de entrada do template principal. Não há
   validação pelos testes públicos (não existe programa). Nova tentativa só por resposta não
   interpretável, até 3 (tentativas 21 a 23, seeds 63 a 65). Status `accepted_predicted`.
6. Nem a predição interpretável: a combinação fica **aguardando tratamento manual**. O comando
   continua com as demais e, no fim, sai com um código próprio listando todas; o `report` as conta
   à parte e o `package` recusa enquanto existir alguma. Os autores a fecham por um comando
   explícito, com o status `discarded_manual` e um motivo obrigatório, gravados com a data; ela
   continua no N = 200.

Relatório e métricas separados por status (metodologia, seção 6, item 31, decidido em parte).

**Alternativas rejeitadas (perguntas do clarify)**: escolher a baixa confiança logo depois das 8,
antes das extras (mais barato, mas contraria a ordem pedida); aceitar a baixa confiança já nas
tentativas 9 a 20; parar o comando na primeira combinação sem suíte (bloquearia as demais); fechar
a combinação só com mais tentativas por predição ou só fora da ferramenta.

**Custo e efeitos não medidos**: até 20 chamadas com solução Python mais 3 de predição por
combinação (com o 14B, mediana de 76 s por chamada no piloto 4); as entradas de uma tentativa com
TLE num teste público podem levar até 10 vezes o limite de tempo cada uma (`PY_TIME_FACTOR`). Os
detalhes (código de saída, nome do comando de fechamento, regras do parser de `<tests>`, `run.json`)
ficam para o plano.

## R19 — Desenho técnico de R18: baixa confiança, predição e tratamento manual (2026-10-06)

Plano de R18 (spec FR-022 a FR-022d). Nenhuma dependência nova; nada de `src/sandbox/` muda.
**Implementado em 2026-10-06** (tarefas T064 a T074), testado só com cliente e executor
simulados; nenhum número medido com o modelo real.

1. **Numeração das tentativas.** **Decisão**: um único contador por combinação, como hoje.
   Tentativas 1 a 20 pedem solução Python (template principal); 21 a 23 pedem predição (template
   novo). O tipo da tentativa sai do número, não de um campo: `config.STRICT_ATTEMPTS = 8`,
   `SOLUTION_ATTEMPTS = 20`, `PREDICT_ATTEMPTS = 3`, `MAX_ATTEMPTS = 23`; seed `42 + n` (43 a 65).
   **Alternativa rejeitada**: numerar as tentativas por predição à parte (1 a 3), o que daria
   duas tentativas com a mesma seed na mesma combinação e quebraria FR-020.
2. **Entradas depois de qualquer reprovação.** **Decisão**: o `evaluate_attempt` roda as entradas
   geradas depois de RE, TLE e MLE num teste público, como já faz depois de WA; o
   `ExecutionRecord` passa a exigir uma entrada avaliada por entrada gerada sempre que a resposta
   foi interpretada. **Custo (não medido)**: uma solução com TLE num teste público tende a dar TLE
   nas entradas, cada uma até 10 vezes o limite do problema; **alternativa rejeitada**: só rodar as
   entradas depois da 20ª (exigiria reabrir tentativas já gravadas e um arquivo de execução
   reescrito, contra a regra de arquivos imutáveis).
3. **Quem pode ser de baixa confiança.** **Decisão**: `low_confidence_eligible` = resposta
   interpretada, `public_test_failed` e ao menos uma entrada mantida. Só é usado depois da 20ª,
   quando nenhuma tentativa pode ser reserva (então nenhuma das elegíveis tem WA). A suíte vem da
   **primeira** delas, com as entradas mantidas e as saídas reais da solução, sem chamada nova.
4. **Resposta por predição.** **Decisão**: um parser próprio, `parse_prediction`, com as regras de
   R6 adaptadas: `<edge_cases_analysis>` e `<tests>` uma vez cada, nesta ordem, sem sobreposição;
   texto fora dos blocos ignorado e contado; dentro de `<tests>`, um ou mais `<test>`, só espaço em
   branco entre eles (`text_between_tests`); cada `<test>` tem exatamente um `<input>` seguido de um
   `<output>`, só espaço em branco ao redor (`malformed_test`); cada bloco perde as linhas em branco
   das pontas e ganha exatamente um `\n` final (como as entradas). Um `<test>` com entrada **ou**
   saída vazia é descartado sozinho e contado (`empty_tests`); todos vazios → `only_empty_tests`;
   entradas repetidas ficam e são contadas. Não há cerca Markdown a remover (não há código). A
   saída prevista é guardada como veio (só a normalização das pontas), sem nenhuma conferência.
   **Alternativa rejeitada**: aceitar saída vazia (raro em programação competitiva e, sem um
   programa, impossível de distinguir de uma resposta que esqueceu a saída).
5. **Registro da predição.** **Decisão**: o mesmo `attempt_<n>.generation.json`; `parse` ganha o
   terceiro formato `PredictionParse` (`ok: true`, `edge_cases_analysis`, `tests: list[TestCase]`,
   `extraneous_chars`, `duplicate_inputs`, `empty_tests`). O schema confere que tentativas 1 a 20
   só têm `ParsedResponse`/`UnparsedResponse` e 21 a 23 só `PredictionParse`/`UnparsedResponse`.
   Tentativa por predição nunca tem `attempt_<n>.execution.json` (seria dano). A interpretada vira
   `suite.json` direto no `generate`, sem passar pelo `execute`.
6. **`run.json`.** **Decisão**: `max_attempts` passa a 23 e entram `solution_attempts` (20),
   `predict_attempts` (3) e `predict_template_sha256`; todos comparados no `--resume`. O
   `run.json` dos pilotos anteriores não é lido pelo código novo (como em R16, decisão 6).
7. **Aguardando tratamento manual.** **Decisão**: estado novo da máquina de estados,
   `awaiting_manual`, derivado dos arquivos (23 tentativas e a 23ª sem interpretação), sem arquivo
   próprio. `generate` e `execute` seguem com as outras combinações e, no fim, se alguma combinação
   da seleção está nesse estado, imprimem uma linha `manual: <id> <scenario>: …` por combinação,
   com o comando de fechamento, e saem com o **código 4** (novo). Dano (código 1), infraestrutura
   (3) e interrupção (130) têm precedência sobre o 4, mas as linhas `manual:` saem do mesmo jeito.
   `report` conta `awaiting_manual` e sai com 0; `package` recusa com código 1 (como para qualquer
   combinação sem `suite.json`). **Alternativa rejeitada**: reaproveitar o código 1 (misturaria um
   estado esperado do fluxo com dano nos arquivos).
8. **Fechamento manual.** **Decisão**: comando novo `python -m ai_clients close --problem ID
   --scenario S --reason TEXTO` (serviço `app`, uma combinação por vez, as três opções
   obrigatórias, motivo não vazio). Só aceita uma combinação em `awaiting_manual` (senão código 2,
   dizendo o estado). Grava `manual_close.json` (`reason`, `closed_at`) e, em seguida, o
   `suite.json` com `status: discarded_manual`, `tests: []`, `accepted_attempt: null` e o objeto
   `manual_close` copiado — o `suite.json` continua sendo função pura dos arquivos da pasta.
   `--dry-run` mostra o que seria gravado. **Alternativa rejeitada**: fechar com uma opção do
   `generate` (misturaria uma decisão humana com o laço automático).
9. **`suite.json`.** **Decisão**: `status` ∈ `accepted`, `accepted_fallback`,
   `accepted_low_confidence`, `accepted_predicted`, `discarded_manual` (sai `discarded`);
   `AttemptSummary` ganha `low_confidence_eligible` e `kind` (`solution` ou `prediction`);
   `manual_close` (objeto ou `null`). Numa suíte por predição, `tests` são os pares do modelo,
   `discarded_inputs` fica vazio e `duplicate_inputs` vem da tentativa escolhida.
10. **Relatório.** **Decisão**: `combinations` com um contador por status mais `awaiting_manual`,
   `pending_generation` e `pending_execution` (somam `total`); `status_rate` (status → cenário →
   proporção) no lugar de `discard_rate` e `fallback_rate`; `suite_size` por status (cada um por
   cenário e no total); `attempt_failures` com as tentativas 1 a 23; `empty_tests` por cenário.
11. **`cli check`.** **Decisão**: a camada `slm_suites` aceita até 23 tentativas, nenhuma
   `attempt_<n>.execution.json` com `n ≥ 21` e o arquivo `manual_close.json`; o resto fica igual.
12. **`num_ctx`/`num_predict`.** **Decisão**: sem mudança; o template de predição tem 2.333
   caracteres (medido no texto enviado pela Milena; o principal tem 3.361) e a guarda de `num_ctx` vale para ele. **Não medido**: o
   tamanho das respostas por predição.

## R20 — Piloto 5, modelo do experimento e desenho do piloto 6 (2026-10-06)

**Piloto 5 (2026-10-06, `data/suites/slm/`, guardado como `slm-piloto5`; código `7535dee`,
`qwen2.5-coder:14b`, templates de R17 e de predição, regra de R18/R19, temperatura 0,7, seed base
42, mesmos 5 problemas × 3 cenários, "GPU T4 - Google Colab")**: as 15 combinações terminaram com
suíte. Medido dos arquivos de tentativa:

| | Piloto 4 (14B) | Piloto 5 (14B) |
|---|---|---|
| Suítes `accepted` | 13/15 | 13/15 |
| As outras 2 (`1000_B` e `1008_B`, caixa-preta) | descartadas | `accepted_fallback` (tentativa 1 nas duas) |
| Tentativas aceitas | 13/40 (32,5%) | 13/49 (26,5%) |
| Falhas | 27 (16 WA, 11 RE) | 36, todas `public_test_failed` (29 WA, 7 RE) |
| Não interpretadas / cortadas (`length`) | 0 / 0 | 0 / 0 |
| Entradas por resposta | 10 a 21 | 3 a 16 |
| *Tokens* de saída (mediana; máximo) | 1.082; 2.009 | 703; 1.022 |
| Tempo por chamada (mediana; máximo) | 76 s; 252 s | 48 s; 179 s |

Tamanho das suítes de 5 a 16; maior `prompt_eval_count` 2.262 (cabe em `num_ctx`); maior prompt
8.370 caracteres (híbrido de `61_B`, igual ao calculado em R17); ≈ 44 min de modelo no total.
Nenhuma combinação chegou à baixa confiança, à predição ou ao tratamento manual, e nenhuma solução
estourou o tempo num teste público (o custo de rodar as entradas depois de TLE segue sem medida).
`1008_B` caixa-preta errou por WA nas 8 tentativas, quase sempre no teste público 1 (espera `NO`;
o prompt só mostra o teste 0, `YES`); `1000_B` caixa-preta, em 7 das 8, no teste 0.

Decisões (Milena, 2026-10-06):

1. **O modelo do experimento é o `qwen2.5-coder:14b`** (resolve a metodologia, seção 6, item 30).
   `config.MODEL` passa a ser ele; `OLLAMA_MODEL` continua opcional. Diverge do texto do TCC, que
   cita o Qwen2.5-Coder-7B (metodologia, seção 7).
2. **Suítes `accepted_fallback` entram nas métricas como as `accepted`**; `accepted_low_confidence`
   e `accepted_predicted` seguem separadas por status (resolve o item 31).
3. **Piloto 6, antes da execução completa**: escolher a temperatura. *(Substituído no mesmo
   dia pela política de 5 fases, R21.)* Mesmos 5 problemas × 3
   cenários, 14B, uma execução completa nova por configuração:
   - temperaturas 0,2; 0,3; 0,4; 0,5; 0,6 com seed base 42. A 0,7 com seed base 42 é o piloto 5
     (mesmos templates e opções; o código posterior só muda onde a seed é conferida), que não é
     refeito;
   - depois, a melhor delas e a 0,7, cada uma com as seeds base 1042 e 2042, para ver se a
     diferença entre as duas é maior que a variação causada só pelas seeds;
   - **critério**: mais suítes `accepted` entre as 15; empate, maior taxa de acerto por
     tentativa; depois, menor tempo total de modelo.
   **Alternativas rejeitadas**: 3 temperaturas (menos resolução); 3 seeds em todas as temperaturas
   (o triplo do tempo). **Custo estimado, não medido**: ≈ 45 min de modelo por configuração, como o
   piloto 5, ou seja ≈ 4 h para as 5 temperaturas e ≈ 3 h para as 4 repetições de seed.
4. *(Substituído no mesmo dia por R21: as duas variáveis saem.)* **Como variar sem editar o
   código**: variáveis opcionais `OLLAMA_TEMPERATURE` (número maior que
   0) e `OLLAMA_SEED_BASE` (inteiro ≥ 0) no `.env`, como a `OLLAMA_MODEL`; os valores vão para o
   `run.json` e o `--resume` recusa outros. A seed de cada tentativa deixa de ser conferida contra a
   constante 42 nos schemas e passa a ser conferida pelo `store` contra a `seed_base` do `run.json`
   (e, na suíte, todas as tentativas com a mesma base). **Alternativa rejeitada**: editar
   `config.py` a cada execução (fácil de esquecer de voltar, como em R15).

## R21 — Política de 5 fases (seed e temperatura por tentativa) (2026-10-06)

**Decisão (Milena, 2026-10-06, `/speckit-clarify`; spec FR-018, FR-020, FR-022 a FR-022d,
FR-023)**: substitui a ordem de R16/R18 (8 estritas, extras até a 20ª, `accepted_low_confidence`)
e o piloto de temperaturas de R20 (uma execução por temperatura, com repetição de seeds). É a
política do experimento: o piloto 6 a valida nos mesmos 5 problemas × 3 cenários e, se der certo,
ela roda na execução completa sem mudança.

| Fase | Tentativas | Seed | Temperatura | Para quando |
|---|---|---|---|---|
| 1 — solução, seed varia | 1 a 6 | 42 a 47 (41 + n) | 0,7 | a solução passa em todos os testes públicos (`accepted`) |
| 2 — solução, temperatura cai | 7 a 12 | 48 | 0,7; 0,6; 0,5; 0,4; 0,3; 0,2 | idem |
| 3 — reserva | — (sem chamada) | — | — | melhor das 12 que reprovou um teste público só por WA e manteve entradas (`accepted_fallback`, desempate de R16) |
| 4 — predição | 13 a 15 | 49, 50, 51 | 0,7 | a primeira resposta interpretada (`accepted_predicted`); nova tentativa só por resposta não interpretável |
| 5 — tratamento manual | — | — | — | combinação aguardando os autores (`close`, `discarded_manual`), como em R19 |

A seed 48 da fase 2 é diferente de todas as da fase 1, então nenhum par (seed, temperatura) se
repete numa combinação. Os 3 esclarecimentos:

1. **É a política do experimento**, não só do piloto (alternativa rejeitada: política só do
   piloto, o que obrigaria o código a manter duas).
2. **`OLLAMA_TEMPERATURE` e `OLLAMA_SEED_BASE` saem** (criadas em R20 e ainda não usadas em
   nenhuma execução): a tabela no código, gravada no `run.json`, é a única fonte de seed e
   temperatura. `OLLAMA_MODEL` continua. As tarefas T076 a T078 (piloto de temperaturas) são
   substituídas por um piloto 6 único.
3. **As entradas voltam a rodar só depois de WA** (ou quando a solução passa em tudo): a
   execução depois de RE, TLE ou MLE existia só para a baixa confiança, que deixou de existir
   (alternativa rejeitada: continuar rodando para guardar o dado, ao custo de até 10 vezes o
   limite de tempo por entrada depois de um TLE).

Pedidos para a implementação: a tabela tentativa → fase, seed, temperatura numa configuração única
e explícita no código, gravada no `run.json`; cada `attempt_<n>.generation.json` registra seed,
temperatura e fase; o relatório mostra, por cenário, em qual fase e tentativa cada combinação ficou
com a suíte e quantas suítes há de cada status (`accepted`, `accepted_fallback`,
`accepted_predicted`, pendentes); testes da sequência exata de seeds e temperaturas, de nenhum par
(seed, temperatura) repetido, da parada na primeira `accepted` em cada fase, da passagem da fase 2
para a reserva e da passagem direta para a predição quando não há reserva.

**Ainda não planejado em detalhe nem implementado**: o código atual segue R19/R20. O orçamento
por combinação cai de 23 chamadas para no máximo 15. O efeito de baixar a temperatura até 0,2 na
fase 2 não foi medido.

## R22 — Desenho técnico da política de 5 fases (2026-10-06)

**Implementado em 2026-10-06** (tarefas T079 a T089), testado só com cliente e executor
simulados. Desvio do desenho: `config.attempt_kind(n)` ficou (como atalho para o `template` da
linha `n`), em vez de sair com as outras funções da política anterior.

Plano de R21 (spec FR-018, FR-020, FR-022 a FR-022d, FR-023, FR-027). Nenhuma dependência nova;
nada de `src/sandbox/` muda. **Motivo da mudança, pelos pilotos**: nos pilotos 4 e 5 (14B) as
falhas foram quase todas WA em teste público, repetidas em várias seeds a 0,7 (`1008_B` e `1000_B`
caixa-preta, 8 de 8); variar a seed a uma temperatura só não tirou o modelo da leitura errada, e
as tentativas extras e a baixa confiança nunca foram exercitadas com o modelo real. A fase 2 testa
outra alavanca (temperatura mais baixa, seed fixa) dentro do mesmo orçamento.

1. **Tabela única da política.** **Decisão**: `config.ATTEMPT_POLICY`, uma tupla de
   `AttemptSpec(attempt, phase, seed, temperature, template)` com as 15 linhas da tabela de R21
   (`template` ∈ `solution`, `prediction`), escrita por extenso no código (não calculada), com
   uma função `attempt_spec(n)`. Validada ao importar: números 1..15 sem buraco, nenhum par (seed,
   temperatura) repetido, fases 1, 2 e 4 nas faixas certas, temperatura > 0. `config.STRICT_*`,
   `SOLUTION_ATTEMPTS`, `PREDICT_ATTEMPTS` e `SEED_BASE` saem; ficam derivadas da tabela
   (`SOLUTION_ATTEMPTS = 12`, `MAX_ATTEMPTS = 15`) para uso interno.
2. **`run.json`.** **Decisão**: o campo `attempt_policy` (a tabela inteira, como lista) substitui
   `seed_base`, `strict_attempts`, `solution_attempts`, `predict_attempts` e `max_attempts`, e a
   temperatura sai de `options` (passa a ser por tentativa). `RunConfig.differences` compara a
   tabela linha a linha (`attempt_policy[7].temperature: recorded 0.6, current 0.5`), então o
   `--resume` recusa qualquer mudança nela. `generation_options(run, n)` envia ao Ollama a seed e
   a temperatura da linha `n` do `run.json`.
3. **`schema_version` 2.** **Decisão**: todos os arquivos do módulo (`run.json`, geração,
   execução, `manual_close.json`, suíte, relatório, manifesto) passam a `schema_version: 2`
   (`ai_clients.schemas.common.SchemaVersion = Literal[2]`; o `dataset` continua em 1). Por
   tentativa, `attempt_<n>.generation.json` ganha `phase`, `temperature` e `template`
   (`slm_prompt.txt` ou `slm_predict_prompt.txt`); o `store` confere seed, temperatura, fase e
   template contra a linha `n` do `attempt_policy` do `run.json` (divergência é dano).
   `AttemptSummary` ganha `phase` e `temperature`; `SlmSuite` ganha `accepted_phase` (1, 2, 3 para
   a reserva, 4 para a predição, `null` em `discarded_manual`). `SuiteStatus` perde
   `accepted_low_confidence`; `AttemptSummary` perde `low_confidence_eligible`.
4. **Execuções antigas.** **Decisão**: toda leitura de `run.json` passa por `store.read_run`, que
   transforma um `run.json` que não valida como `schema_version: 2` em `IncompatibleRunError`;
   `generate`, `execute`, `close`, `report` e `package` saem com código 2 e a mensagem
   `data/suites/slm holds a run of an older version of python -m ai_clients (it cannot be resumed
   nor read); move it away first: mv data/suites/slm data/suites/slm-<name>`. Sem tentar ler as
   tentativas antigas (alternativa rejeitada: migrar os pilotos — eles foram feitos sob outra
   política e não podem ser continuados).
5. **Máquina de estados** (data-model §4). **Decisão**: com `n` = última tentativa: solução não
   executada → `pending_execution(n)`; aceita → `finalizable` (`accepted`, fase da tentativa);
   falhou e `n < 12` → `pending_generation(n + 1)` (a passagem da fase 1 para a 2 é só a próxima
   linha da tabela); `n = 12` e alguma das 12 pode ser reserva → `finalizable`
   (`accepted_fallback`, fase 3, a melhor pelo desempate de R16); `n = 12` sem reserva →
   `pending_generation(13)` (direto para a predição); predição interpretada → `finalizable`
   (`accepted_predicted`, fase 4, gravada pelo próprio `generate`, sem `execute`: as saídas vêm da
   resposta); predição não interpretada e `n < 15` → `pending_generation(n + 1)`; `n = 15` →
   `awaiting_manual`, ou `finalizable` (`discarded_manual`) com `manual_close.json`. A reserva só é
   considerada depois da 12ª (antes, depois da 8ª). Dano novo: tentativa 13 ou mais com uma reserva
   possível entre as 12.
6. **Entradas só depois de WA.** **Decisão**: `oracle.evaluate_attempt` volta à regra de R16 (as
   entradas rodam se a solução passou em tudo ou se o primeiro erro foi WA) e o `ExecutionRecord`
   volta a exigir `inputs` vazio depois de RE, TLE ou MLE.
7. **Parser da predição.** **Decisão**: as mesmas duas regras fixas do parser principal,
   aplicadas a cada `<input>` e `<output>`: uma cerca Markdown que envolve o bloco inteiro (primeira
   linha exatamente ```` ``` ````, ```` ```text ````, ```` ```txt ```` ou ```` ```plaintext ````;
   última ```` ``` ````) é removida e contada (`markdown_fences_removed`, por tentativa e no
   relatório); um `<test>` com entrada ou saída vazia é descartado sozinho e contado
   (`empty_tests`), e só todos vazios falham a resposta. Qualquer outra cerca fica (vira parte do
   dado).
8. **Código de saída 4, `report` e `package`.** Como em R19 (sem mudança): linhas `manual:`,
   código 4, `report` conta `awaiting_manual`, `package` recusa listando o `close`.
9. **Relatório** (`schema_version` 2). **Decisão**: `combinations` com `accepted`,
   `accepted_fallback`, `accepted_predicted`, `discarded_manual`, `awaiting_manual`,
   `pending_generation`, `pending_execution` (por cenário e total); `acceptance` — por cenário e no
   total, quantas combinações ficaram com a suíte em cada fase (1 a 4) e em cada tentativa
   (1 a 15); `per_phase` — por fase (1, 2, 4), chamadas, tentativas falhas, *tokens* de prompt e de
   saída e tempo do modelo; `attempt_failures` de 1 a 15; o resto como antes.
10. **`cli check`.** **Decisão**: até 15 tentativas, execução só até a 12ª, `manual_close.json`
    permitido.
11. **Remoções.** `OLLAMA_TEMPERATURE`, `OLLAMA_SEED_BASE` (de `__main__.py`, `.env.example`,
    READMEs), as tentativas 13 a 20 com solução, `accepted_low_confidence` e tudo que só existia
    para eles.

**Testes pedidos (R21) e onde ficam**: sequência exata de seeds e temperaturas e nenhum par
repetido (`test_config.py`, novo); parada na primeira `accepted` na fase 1 e na fase 2, passagem da
fase 2 para a reserva, passagem direta para a predição sem reserva, aguardando tratamento manual
(`test_generation.py`, `test_execution.py`); retomada no meio de cada fase (`test_resume.py`, com
interrupção nas tentativas 3, 9 e 14); `run.json` antigo recusado (`test_cli_*`); seed,
temperatura, fase e template de cada tentativa conferidos (`test_damage.py`); parser da predição
com cerca (`test_parser_prediction.py`); relatório por fase (`test_report.py`).

**Custo e efeito não medidos**: no máximo 15 chamadas por combinação (eram 23); o efeito da
temperatura baixa só o piloto 6 mede.

## R23 — Piloto 6 e continuação da mesma execução até as 600 combinações (2026-10-07)

**Piloto 6 (2026-10-06/07, `data/suites/slm/`, código `e69d2fe`, `qwen2.5-coder:14b` digest
`9ec8897f…`, Ollama 0.35.0, templates `fc9757e8…` e `421adf86…`, política de 5 fases de R21/R22,
mesmos 5 problemas × 3 cenários, "GPU T4 - Google Colab, 16GB RAM")**. Medido dos arquivos das 15
combinações do piloto (as tentativas de `1009_B` e `1011_B`, já começadas na mesma execução, ficam
de fora):

| | Piloto 5 (seeds a 0,7) | Piloto 6 (5 fases) |
|---|---|---|
| Suítes | 13 `accepted`, 2 `accepted_fallback` | 13 `accepted` (12 na fase 1, 1 na fase 2), 2 `accepted_fallback` (fase 3) |
| Chamadas / aceitas | 49 / 13 (26,5%) | 57 / 13 (22,8%): 43 na fase 1, 14 na fase 2, nenhuma predição |
| Falhas | 36 (29 WA, 7 RE) | 44 (35 WA, 8 RE, 1 `all_inputs_failed`) |
| Não interpretadas / cortadas | 0 / 0 | 0 / 0 |
| Tempo por chamada (mediana; máximo) | 48 s; 179 s | 43 s; 166 s (≈ 46 min de modelo) |
| Entradas por resposta; tamanho das suítes | 3–16; 5–16 | 5–10; 4–10 |

A fase 2 resolveu `1005_C` caixa-preta na tentativa 8 (seed 48, temperatura 0,6) depois de 7 falhas
(6 WA, 1 RE). `1000_B` e `1008_B` caixa-preta, as mesmas dos pilotos 4 e 5, erraram as 12 (quase
só WA) e ficaram como reserva: `1000_B` pela tentativa 1, `1008_B` pela tentativa 9 (fase 2,
temperatura 0,5), a que passou mais testes públicos. Nenhuma combinação chegou à predição nem ao
tratamento manual, então as fases 4 e 5 continuam testadas só com o modelo simulado.

**Decisões (Milena, 2026-10-07)**:

1. **A configuração fica congelada** (modelo, digest, versão do Ollama, os dois templates, a tabela
   `ATTEMPT_POLICY`, opções, fatores) e **a execução completa é a continuação desta mesma
   execução**, com `--resume`, até as 600 combinações: as 15 do piloto 6 entram no resultado final.
   **Alternativa rejeitada**: começar a execução completa numa pasta nova (refaria 15 combinações
   já feitas com a mesma configuração).
2. **Duas GPUs T4 idênticas (Kaggle), cada uma com seu Ollama**, para gerar as 585 restantes: dois
   `generate --resume` em paralelo, com metades disjuntas dos problemas e o `OLLAMA_BASE_URL` de
   cada um passado com `docker compose run -e`, e um único `execute` depois (desenho em R24).
   `OLLAMA_HARDWARE_LABEL` é o mesmo nos dois processos (o do `.env`), então a etiqueta não
   distingue as duas GPUs. **Não será medido** se as duas GPUs dão respostas idênticas para a
   mesma seed e temperatura (decisão dos autores: são T4 idênticas, como a do Colab).
3. Antes do primeiro `generate` da continuação: `docker compose run --rm app python -m cli check
   --deep` com saída 0.

## R24 — Execução concorrente: travas compartilhada e por combinação (2026-10-07)

**Implementado em 2026-10-07** (Phase 12 de `tasks.md`): o resumo só mostra `; N skipped (in
use by another command)` quando N > 0, então as saídas sem concorrência não mudam.

Plano de FR-026a (spec, sessão 2026-10-07; decisões de R23). Nenhuma dependência nova (`fcntl`);
nada de `src/sandbox/` muda.

1. **Trava da execução** (`data/suites/slm/.lock`, `flock`): **compartilhada** para `generate
   --resume` e `execute` (`store.shared_run`), **exclusiva** para `package` e `close`
   (`store.exclusive_run`, como hoje). Sempre sem esperar (`LOCK_NB`): pedir a exclusiva com
   alguém segurando a compartilhada, ou o contrário, recusa na hora com código 1 (`another python -m
   ai_clients command is already running ...`). O `generate` **sem** `--resume` (que cria o
   `run.json`) continua com a exclusiva: uma execução nova é sempre começada por um processo só, e
   o paralelismo vale a partir do `--resume`. `report` e os `--dry-run` não pegam trava (só leem).
2. **Trava por combinação** (`data/suites/slm/.locks/<id>__<cenário>.lock`, exclusiva, sem esperar,
   `store.claim`): `generate` e `execute` só olham o estado de uma combinação, chamam o modelo,
   executam e gravam com ela pegada, e a soltam ao terminar aquela combinação. Se outro processo a
   tem, ela é **pulada** e contada (`skipped`), sem esperar (esclarecimento de 2026-10-07): o
   resumo final ganha `N skipped (in use by another command)`. Como o estado é lido só depois de
   pegar a trava, duas metades sobrepostas nunca fazem a mesma tentativa duas vezes. A pasta
   `.locks` começa com ponto, então o pacote, o manifesto e o `cli check` a ignoram (já ignoram todo
   caminho com ponto).
3. **Um `execute` por vez**: os `execute` usam o mesmo *slot* do motor (uid e pasta de trabalho) e
   limpam esse *slot* no começo e no fim; dois em paralelo se atrapalhariam. Por isso o `execute`
   pega também uma trava exclusiva própria (`data/suites/slm/.execute.lock`); um segundo `execute`
   recusa com código 1. `generate` e `execute` podem rodar juntos.
4. **Etiqueta e endereço**: cada processo lê o próprio `OLLAMA_BASE_URL` (o `-e` do `docker compose
   run` tem prioridade sobre o `.env`); a etiqueta é a do `.env` nos dois (R23, decisão 2). O
   `--resume` de cada processo confere o `run.json` contra o modelo e a versão do Ollama do seu
   endpoint: GPUs com outra versão ou outro digest são recusadas (código 2), o que protege a
   configuração congelada.
5. **Testes** (`tests/ai_clients/test_concurrency.py`, novo, com dois `generate` em *threads* e um
   cliente falso que bloqueia a primeira chamada até o teste liberá-la — `flock` em dois descritores
   do mesmo processo se excluem como entre processos): metades disjuntas juntas (nada pulado, a
   mesma árvore de uma execução sem concorrência); metades sobrepostas (a combinação em uso é
   pulada e contada, nenhum arquivo duplicado, a rodada seguinte completa); `execute` com um
   `generate` ativo (roda o resto, pula a combinação em uso); `package` e `close` recusando com
   código 1 enquanto um `generate` roda; um segundo `execute` recusado.

**Alternativas rejeitadas**: esperar a combinação em uso (esclarecimento de 2026-10-07); uma trava
por problema (impediria dois processos de dividir os cenários de um mesmo problema, sem ganho);
permitir dois `execute` (exigiria um *slot* do motor por processo, uma mudança no módulo `sandbox`).
