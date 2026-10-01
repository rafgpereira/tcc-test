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

**Decisão**: `num_ctx = 8192`, `num_predict = 4096`.

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

---

## R6 — Interpretação da resposta (FR-009, FR-010, Edge Cases)

**Decisão**: parser determinístico, sem correção heurística, sobre o texto cru (depois de só
`\r\n` → `\n`):

1. Cada uma das tags de topo `<edge_cases_analysis>`, `<inputs>`, `<reference_py>` deve abrir e
   fechar **exatamente uma vez**, nesta ordem, sem se sobrepor. Qualquer outra situação (ausente,
   duplicada, fora de ordem, sem fechamento) → `unparseable_response`, com o motivo exato
   (`missing_block:<tag>`, `duplicated_block:<tag>`, `wrong_order`, …).
2. Texto fora dos três blocos (preâmbulo, comentário final) é **ignorado e contado**
   (`extraneous_chars`), não corrigido — não altera o conteúdo de nenhum bloco.
3. Dentro de `<inputs>`: um ou mais pares `<input>…</input>` não aninhados; texto não branco entre
   eles → falha (`text_between_inputs`). Nenhum `<input>` → falha (`no_inputs`).
4. Normalização de cada entrada: remover linhas totalmente brancas do início e do fim e garantir
   exatamente um `\n` final. Entrada vazia depois disso → falha (`empty_input`, Edge Case da spec).
   Espaços **dentro** das linhas não são tocados.
5. `<edge_cases_analysis>` e `<reference_py>` vazios (só espaço) → falha (`empty_block:<tag>`).
   O código Python é gravado como veio (só `\r\n` → `\n` e linhas brancas das pontas removidas); se
   o modelo o embrulhar numa cerca Markdown (```` ```python ````), ela **não** é removida — o código
   vira `SyntaxError`, falha nos testes públicos e a tentativa é descartada pela razão (b). Isso é
   consequência de não haver correção heurística, e a frequência é medida no piloto.
6. Entradas repetidas dentro da mesma resposta **não** são removidas (fidelidade à saída do modelo);
   a quantidade de duplicatas é registrada na suíte e no relatório, porque infla o tamanho da suíte
   (variável de confusão da spec, FR-012).

**Motivo**: tags únicas + ordem fixa dão uma gramática trivial e totalmente testável por tabela de
casos; ignorar texto externo evita descartar respostas corretas por uma frase de cortesia, sem
alterar o que é interpretado.

**Alternativas**: parser XML (`xml.etree`) — quebra com `<`, `&` em entradas e no código Python;
regex gulosa — ambígua com tags repetidas; extrair o código de cercas Markdown — correção
heurística vetada pela spec.

---

## R7 — Execução do `reference_py` na sandbox (FR-013 a FR-019)

**Decisão**:

- **Interpretador**: o CPython 3.11 base da imagem (`Path(sys.base_prefix)/"bin"/"python3.11"`,
  instalado pelo `uv` em `/opt/python`), **não** o do `venv`: só a biblioteca padrão fica
  disponível. Flags `-I` (isolado: ignora `PYTHON*` e o diretório do usuário), `-S` (sem `site`),
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

**Alternativas**: um arquivo por combinação reescrito a cada passo (janela de corrupção lógica
maior, apesar da escrita atômica); banco SQLite (dependência de formato binário, pior para
empacotar e auditar); retomada implícita sem `--resume`, como no `mutation` (o autor pediu a opção
explícita; ela também protege contra continuar por engano com o template ou o modelo alterados).

---

## R9 — Falha de infraestrutura vs. falha de conteúdo (FR-018a, SC-007)

**Decisão**: o cliente classifica toda chamada em três desfechos, e só o terceiro vira tentativa:

| Desfecho | Exemplos | Efeito |
|---|---|---|
| `OllamaUnavailable` (infraestrutura) | recusa de conexão, DNS, *timeout* de conexão/leitura (`OLLAMA_HTTP_TIMEOUT_S`, padrão 900 s), HTTP 5xx, corpo que não é JSON | não grava nada; espera com recuo exponencial (5 s, 10 s, 20 s, … até 60 s) e **repete a mesma chamada com a mesma seed**, até `OLLAMA_MAX_INFRA_RETRIES` repetições consecutivas (padrão 30); cada espera é impressa. Atingido o teto: código 3 (`ollama unavailable after N consecutive retries (<último motivo>); nothing was recorded for <id> <scenario> attempt <n>; run generate --resume when the service is back`), sem gravar nada e sem consumir tentativa. O contador zera a cada resposta recebida |
| `OllamaConfigError` (configuração) | HTTP 4xx (modelo não instalado, opção inválida), `digest` do modelo diferente do `run.json`, guarda de `num_ctx` (R3) | não grava nada; aborta com código 3 e mensagem acionável |
| resposta recebida | qualquer 200 com `message.content` | grava `attempt_<n>.generation.json` (a interpretação decide se é falha `unparseable_response`) |

`done_reason` (`"stop"` ou `"length"`) é sempre gravado; `"length"` **não** é tratado à parte — uma
resposta truncada normalmente não fecha `</reference_py>` e cai na falha de interpretação pelo
parser; se fechar, segue o fluxo normal. O relatório conta `done_reason = "length"` para medir o
efeito de FR-007.

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

---

## R10 — Relatório, empacotamento e verificação (FR-027, FR-028)

**Decisão**: mesmo desenho do módulo `mutation`:

- `python -m ai_clients report` → `manifests/slm_generation_report.json` (versionado): contagens
  por estado e cenário, taxa de descarte por cenário e total (sobre as 600 combinações, N nunca
  reduzido), distribuição do tamanho das suítes aceitas (mín./quartis/máx. e histograma), funil de
  falhas por razão e por número da tentativa, entradas descartadas por razão, duplicatas,
  `done_reason = "length"`, *tokens* (soma, máximo de `prompt_eval_count`), duração, seeds por
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
