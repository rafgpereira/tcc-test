# Metodologia de Referência — Pipeline Experimental

> **Natureza deste documento**: referência viva para o desenvolvimento do software.
> Reflete a metodologia do TCC (com os ajustes já incorporados no TCC2, mais os pontos
> sinalizados pela banca que ainda não estavam redigidos na seção de Metodologia).
> Pode e deve ser ajustado durante o desenvolvimento (ver Constitution, princípios I e XI) e
> MUST estar sempre corrente: a seção 8 registra, com data, cada atualização.
> Pontos marcados como **[PENDENTE]** são decisões ainda em aberto — não foram
> inventados aqui, precisam ser fechados pela dupla antes de virarem código definitivo.
> Pontos marcados como **[PROPOSTA]** são sugestões já registradas aqui, mas que ainda
> aguardam confirmação explícita da dupla antes de virarem regra definitiva.
> Pontos marcados como **[DECIDIDO]** foram confirmados pela dupla durante a especificação
> do módulo de dataset (`specs/001-dataset-extraction/spec.md`, seção "Divergências e
> Decisões sobre a Metodologia") e são regra vigente; a seção 7 lista o que diverge do
> texto do TCC.

## 0. Contexto Geral do Experimento

Avaliar empiricamente a eficácia de modelos de linguagem (dois LLMs comerciais —
GPT-5.4-mini e Gemini 3.5 Flash — e um SLM local — Qwen2.5-Coder-7B via Ollama) na
geração automática de casos de teste unitários em C++, sob três cenários de contexto:

- **Caixa-Preta**: apenas o enunciado do problema (requisito).
- **Caixa-Branca**: apenas o código-fonte da solução de referência (AC).
- **Híbrida**: requisito + código simultaneamente.

Perguntas de pesquisa centrais: qual abordagem detecta melhor falhas lógicas reais
(TDF), qual é mais sensível a defeitos sintéticos (MS via mutação), qual gera mais
falsos positivos/alucinações (TFP), e como a combinação de insumos influencia
positiva ou negativamente a cobertura (IIC — ver seção 5).

---

## 1. Módulo: Dataset (extração, filtragem, validação, persistência)

**Fonte**: dataset [`deepmind/code_contests`](https://huggingface.co/datasets/deepmind/code_contests)
(Hugging Face), acessado via streaming, sem download completo do repositório.

### 1.1 Conhecimento sobre o dataset (schema oficial)

Fatos confirmados diretamente na página do dataset e, onde marcado **[CORRIGIDO]**,
medidos diretamente no dataset — usar como referência exata de campos ao implementar o
módulo, evitando suposições erradas de schema:

- **Tamanho total** **[CORRIGIDO]**: **13.610 exemplos**, divididos em splits `train`
  (**13.328**), `valid` (117) e `test` (165); **8.101** deles de origem Codeforces. Estes
  números foram **medidos empiricamente** (streaming, todos os splits) durante o
  `/speckit-plan`, em **2026-09-19**, na revisão
  `802411c3010cb00d1b05bad57ca77365a3c699d6` do dataset, e **substituem os valores
  anteriores desta seção (4.044 exemplos, `train` 3.760)**, que estavam desatualizados: não
  correspondem à revisão atual. O tamanho em disco (≈7,62 GB, informado na página do
  dataset) não foi reverificado; o acesso é via streaming, nunca baixado por completo.
  **Reconfirmado em 2026-09-20** pela extração real: 13.610 linhas lidas, em 41 shards (39 de
  `train` com 341 ou 342 linhas, 1 de `valid` com 117 e 1 de `test` com 165).
  **[DECIDIDO]** Os três splits são combinados (`train`+`valid`+`test`); o split de origem
  de cada problema é registrado em `dataset_split_origem` (ver 1.5).

- **Acesso, hospedagem e licença** **[CORRIGIDO]** (medido em 2026-09-19): o repositório é
  hospedado em arquivos Parquet (39 shards de `train`, 1 de `valid` e 1 de `test`), sem
  acesso restrito, sob licença **CC-BY-4.0** (citar a fonte no trabalho escrito). O acesso é
  por streaming sobre uma **revisão fixada** (`802411c3010cb00d1b05bad57ca77365a3c699d6`),
  para garantir "o mesmo dataset de entrada". A extração faz uma única passagem, com
  checkpoint por shard (retomável após queda de rede), e grava localmente apenas o
  subconjunto dos problemas elegíveis, nunca o repositório completo.

- **Campos relevantes e tipos**:

| Campo | Tipo | Observação |
|---|---|---|
| `name` | string | identificador do problema |
| `description` | string | enunciado em texto |
| `source` | enum (int) | `CODEFORCES = 2` (valor a filtrar) |
| `cf_contest_id` | int | usar para nomear a pasta `<ContestID>_<Index>` |
| `cf_index` | string | idem acima |
| `cf_rating` | int32 | dificuldade Codeforces — usar para o filtro 1000–1600. **[CORRIGIDO]** 118 problemas Codeforces do dataset vêm sem rating (medido) e são inelegíveis |
| `cf_tags` | lista de string | tags para elegibilidade e macrocategoria |
| `cf_points` | float32 | pontuação Codeforces do problema (metadado extra, útil para análise) |
| `public_tests` / `private_tests` / `generated_tests` | dict `{input: [...], output: [...]}` | casos de teste oficiais; `generated_tests` é um conjunto adicional que o dataset já traz pronto — **[DECIDIDO]**: persistir também os `generated_tests` dentro de `testes.json`, separados dos públicos/privados, como reserva adicional para validação futura (ex: checagem cruzada de métricas) |
| `solutions` / `incorrect_solutions` | dict `{language: [int], solution: [string]}` | filtrar `language == CPP` (valor `2`) em ambos |
| `time_limit` | dict `{seconds: int, nanos: int}` | **não é um escalar** — calcular `seconds + nanos/1e9` ao extrair o limite de tempo do sandbox |
| `memory_limit_bytes` | int64 | limite de memória do sandbox |
| `is_description_translated` | bool | indica se o enunciado foi traduzido para o inglês a partir de outro idioma |
| `input_file` / `output_file` | string | nome do arquivo de entrada/saída quando o problema não usa entrada/saída padrão (ex.: `input.txt`/`output.txt`); vazio quando usa. **[CORRIGIDO]** campos presentes no dataset e usados no critério de elegibilidade de 1.2 (ausentes da versão anterior desta tabela) |

### 1.2 Critérios de elegibilidade de um problema (todos obrigatórios)
- Origem: Codeforces (`source == 2`).
- `cf_rating` entre 1000 e 1600, inclusive (evita trivialidade e complexidade fora do
  escopo). Problema sem `cf_rating` informado é inelegível.
- Contém ao menos uma tag de escopo determinístico: `implementation`, `math`,
  `greedy`, `strings`, `binary search`, `dp`, `sortings`.
- **Não** contém tags de saída múltipla/ambígua: `geometry`, `interactive`, `games`,
  `probabilities`, `constructive algorithms` → descarte automático.
- Sem dependência visual: descarta enunciados com `figure`, `image`, `picture`,
  `shown below`, `as follows`, `http`, `.png`, `.jpg`.
- Linguagem da submissão: C++ apenas (`language == 2`), tanto em `solutions` quanto
  em `incorrect_solutions`.
- `is_description_translated == false` **[DECIDIDO]** (confirmado como critério
  obrigatório).
- **[DECIDIDO, 2026-09-19] Sem E/S por arquivo**: `input_file` e `output_file` vazios (o
  problema usa entrada e saída padrão). Critério novo, ausente da versão anterior. Motivo:
  o motor injeta a entrada por `stdin` (seção 4), então um problema que lê `input.txt` e
  escreve `output.txt` faria o AC falhar no motor e, pela regra de falha de AC (1.4),
  viraria triagem manual. Medido: 9 problemas (0,7% do pool), todos de concursos antigos.

#### Funil de elegibilidade medido (2026-09-19)

**[CORRIGIDO]** Números medidos empiricamente em streaming sobre os três splits na revisão
`802411c3…`. As etapas até "Sem E/S por arquivo" foram medidas durante o `/speckit-plan`, em
**2026-09-19**, sem a checagem de soluções em C++ (que exige as colunas pesadas); a **extração
real de 2026-09-20** (seed 42, código na revisão git `7440706`) reproduziu esses números
exatamente e acrescentou as duas últimas etapas:

| Etapa | Problemas restantes |
|---|---:|
| Linhas lidas (`train` 13.328 + `valid` 117 + `test` 165) | 13.610 |
| Origem Codeforces (`train` 7.819, `valid` 117, `test` 165) | 8.101 |
| `cf_rating` entre 1000 e 1600 (os 118 problemas Codeforces sem rating caem aqui) | 2.399 |
| Ao menos uma tag permitida | 2.155 |
| Nenhuma tag proibida | 1.751 |
| Sem termo de dependência visual | 1.288 |
| `is_description_translated == false` | 1.288 (nenhum removido nesta etapa) |
| `problem_id` único entre os splits | 1.288 (nenhuma duplicata) |
| Sem E/S por arquivo (`input_file` e `output_file` vazios) | 1.279 (9 removidos) |
| Ao menos uma solução correta e uma incorreta em C++ | 1.250 (29 removidos) |
| Ao menos 100 submissões incorretas em C++, contadas antes de remover duplicatas (pré-checagem de D4) | **1.234** (16 removidos) |

Os **1.288** problemas são os elegíveis antes do critério de E/S por arquivo e os **1.279** são
o pool antes da checagem de soluções em C++ (a medição de 2026-09-19 chamava esse número de pool
final). O **pool final, medido pela extração real de 2026-09-20, tem 1.234 problemas**:
`estrutural_otimizacao` 407, `matematica` 278, `logica_direta` 549; por origem, `train` 1.206,
`valid` 9, `test` 19 (o `train` perde 44 problemas e o `test` perde 1 nas duas últimas etapas).
Para comparação, a distribuição dos 1.279, medida em 2026-09-19 sem a checagem em C++, era
417/285/577, com `train` 1.250, `valid` 9 e `test` 20. No relatório de extração, a tabela do
funil é sequencial, enquanto "linhas com cada motivo de rejeição" conta cada critério sobre todas
as linhas lidas (uma linha pode ter vários motivos, FR-005), então as duas tabelas não somam igual.
Os 9 removidos por E/S
por arquivo (todos com `input.txt`/`output.txt`) são `120_A`, `120_B`, `120_C`, `234_B`,
`234_C`, `253_A`, `253_B`, `253_C` e `36_A` (2 matemática, 3 estrutural/otimização, 4 lógica
direta).

**Amostra final (validação de 2026-09-21, T072; detalhes em 1.7)**: 200 problemas, `logica_direta`
98, `estrutural_otimizacao` 61 e `matematica` 41; `train` 198 e `test` 2. Foram processados 264 dos
1.234 problemas do pool (21 descartados por WA insuficientes e 43 em triagem adiada).

O pool de elegíveis é cerca de seis vezes a meta de 200, então nenhum critério precisou ser
relaxado. O filtro de dependência visual é o que mais remove (463 problemas, 26% dos que
chegavam a ele); como único motivo: `image` 189, `as follows` 77, `http` 27, `figure` 10,
`picture` 8, `shown below` 1.

### 1.3 Categorização por macrocategoria algorítmica — REGRA DEFINIDA

Três macrocategorias, mutuamente exclusivas (cada problema pertence a exatamente
uma):

- **Matemática**: tag `math`.
- **Estrutural/Otimização**: tags `binary search`, `dp`, `sortings`.
- **Lógica Direta**: tags `implementation`, `strings`, `greedy`.

Quando um problema tem tags de mais de uma macrocategoria, a atribuição segue uma
**prioridade fixa** (da mais forte para a mais fraca), e não a criação de grupos
combinados — decisão tomada para preservar poder estatístico da amostra (200
problemas já fragmentados em 3 cenários × 3 modelos) e manter a análise por
categoria interpretável para a banca:

```
1º Estrutural/Otimização (dp, binary search, sortings)
2º Matemática (math)
3º Lógica Direta (implementation, strings, greedy)
```

Racional: `implementation` é predominantemente uma tag secundária no Codeforces
(indica cuidado de codificação, não uma técnica algorítmica em si); quando `math`
coexiste com uma tag estrutural, o desafio real do problema costuma ser estrutural
(ex: contagem combinatória via `dp`). A tag mais específica prevalece.

**Exemplos**:
- `math` + `implementation` → **Matemática**.
- `dp` + `math` → **Estrutural/Otimização**.
- `binary search` + `sortings` + `implementation` → **Estrutural/Otimização**.
- `greedy` + `strings` (sozinhas) → **Lógica Direta**.
- `dp` + `greedy` → **Estrutural/Otimização**.

Esse campo é persistido por problema (ver 1.5 — `metadata.json`).

### 1.4 Validação local de códigos no motor de execução (AC e WA)
- O dataset agrega WA/TLE/MLE/RE numa única categoria (`incorrect_solutions`); é
  preciso auditar e filtrar apenas falhas lógicas puras (WA real).
- **[DECIDIDO] Motor de execução único, construído neste módulo e reutilizado sem
  alteração na avaliação (seção 4), em pacote próprio (`src/sandbox/`), separado do pacote do
  dataset, para que a avaliação o use sem depender de internos do dataset.** Passam por ele **tanto as submissões incorretas
  quanto a solução de referência (AC)**, sob as mesmas regras de compilação, limites e
  comparação de saída. Objetivo: nenhum código persistido no dataset pode ser incompatível
  com o motor — isso deve ser descoberto na montagem do dataset, e não depois, com o
  experimento em andamento. Antes de validar qualquer problema, o motor é verificado com
  programas de veredito conhecido (aprovado, WA, TLE, MLE, RE, erro de compilação,
  dependência de pilha grande e recuo na cascata de padrões).
- Compilação via GCC ≥13.2, com as flags do juiz original, exceto uma:
  `g++ -Wall -Wextra -Wconversion -static -DONLINE_JUDGE -O2 -std=gnu++20 programa.cpp`
  O ambiente fixa o GCC exatamente em **13.2.0** (imagem `gcc:13.2.0`, fixada por digest),
  o que atende ao mínimo ≥13.2 e maximiza a reprodutibilidade.
- **[DECIDIDO] Divergência de plataforma**: a opção `-Wl,--stack=268435456` do juiz
  original é uma opção de linker do Windows/MinGW, incompatível com o linker em Linux, e
  foi removida. Seu efeito é reproduzido aplicando, em tempo de execução dentro do sandbox,
  um limite de pilha de 268435456 bytes (256 MiB), equivalente a `ulimit -s 262144` (o
  `ulimit -s` conta em KiB). O objetivo é maximizar a quantidade de códigos que funcionam,
  mantendo a linha de execução o mais próxima possível da do Codeforces. O limite de
  memória do problema continua valendo sobre o consumo total, pilha incluída.
  **Verificado em 2026-09-19** (GCC 13.2.0, Debian 12): a linha original com
  `-Wl,--stack=268435456` falha no linker do Linux com
  `ld: unrecognized option '--stack=268435456'` (`rc=1`); sem essa opção, compila. O limite é
  aplicado com `resource.setrlimit(RLIMIT_STACK)` do Python, cuja unidade é **bytes**
  (`268435456`); o `ulimit -s` do shell usa **KiB** (`262144`). A conversão fica em uma função
  única, coberta por teste, para nunca aplicar 256 KiB no lugar de 256 MiB.
- Fallback em cascata de padrão de linguagem se a compilação falhar:
  `gnu++20 → gnu++17 → gnu++14 → gnu++11`. Falhou em todos → descarta o código.
- Execução isolada (sandbox), limites de tempo/memória extraídos dinamicamente de
  `time_limit` (seconds + nanos/1e9) e `memory_limit_bytes` — nunca hardcoded.
- **[DECIDIDO] Solução de referência (AC)**: adota-se como `AC_ref` uma solução correta em
  C++ (a *primeira em ordem determinística do dataset*, **[DECIDIDO]** em 2026-09-20; ver
  "Regras operacionais do motor") que deve compilar e reproduzir o gabarito de toda a suíte
  oficial dentro dos limites, executada pelo motor. **Qualquer falha de AC no motor**
  (na escolha do `AC_ref` ou na reexecução de auditoria) **interrompe imediatamente o
  processamento daquele problema** e o registra em `validacao.json` (identificador, motivo,
  saída divergente) para triagem manual. Não há tolerância percentual, não se tenta outra
  solução no lugar e não se espera acumular falhas antes de alertar. Motivo: como o AC é
  conhecidamente correto, sua falha quase sempre indica bug no motor ou um problema com
  múltiplas saídas válidas (verificador especial) que escapou do filtro de tags; cada caso
  tem causa raiz própria e exige inspeção individual. O problema fica pendente de triagem
  (não conta para os 200, não é empacotado) e o processamento dos demais continua.
  **[DECIDIDO, 2026-09-21] A inspeção manual é adiada**: esses problemas só serão triados
  individualmente se, processados todos os demais problemas do pool, a meta de 200 não for
  atingida; enquanto a meta é atingida sem eles, ficam registrados e não são inspecionados. A
  interrupção imediata, o registro e a exclusão da amostra não mudam (D17 da spec).
- Só entra no conjunto final o código que compila, executa dentro dos limites, e
  produz saída divergente do gabarito oficial (WA genuíno). TLE/MLE/RE são
  descartados (não são falha lógica).
- Repete até acumular **exatamente 100 WAs validados por problema**. **[DECIDIDO]** O
  problema que esgotar as submissões incorretas em C++ sem alcançar 100 WAs validados é
  excluído da amostra e registrado no relatório; não se aceita menos de 100 (isso quebraria
  o denominador `W_total = 100` do TDF, seção 5.1).
- Meta de amostra: **200 problemas elegíveis**. **[DECIDIDO]** Sem cota rígida por
  macrocategoria: a seleção segue ordem determinística definida por seed fixa e documentada
  (**`SEED = 42`**, **[DECIDIDO]** em 2026-09-19; trocá-la depois da primeira extração muda
  a seleção).
  **Como os 200 são escolhidos**: o pool elegível (1.234 problemas, dos três splits juntos) é
  embaralhado **uma única vez** com a seed 42 (`Random("42:pool")` sobre os identificadores
  ordenados) e gravado nessa ordem em `pool.json`. A validação percorre essa ordem e os **200
  primeiros problemas que completam a validação** (`AC_ref` aprovado e exatamente 100 WA) formam a
  amostra; os que não completam (descartados por menos de 100 WA, ou com o `AC_ref` reprovado no
  motor e em triagem) são pulados, e a próxima posição da ordem é usada. Não há estratificação,
  cota por macrocategoria nem prioridade por split ou dificuldade: a distribuição da amostra por
  macrocategoria e por split é consequência do sorteio e das exclusões, e o relatório a informa.
  O relatório final emite um **alerta** se qualquer macrocategoria ficar com menos de 30
  problemas após a seleção, que é final quando a meta é atingida ou todos os problemas do pool
  foram encerrados, mesmo com déficit (limiar fixo; alerta informativo, que não bloqueia a execução,
  não altera a seleção e não relaxa critérios).
  **Distribuição esperada (estimativa analítica de 2026-09-20, refeita com o pool real da
  extração de 2026-09-20: 407 `estrutural_otimizacao`, 278 `matematica`, 549 `logica_direta`,
  1.234 no total)**: como a ordem é um embaralhamento único do pool (sem estratificação), a
  amostra de 200 tende a ser proporcional ao pool: em média 66,0 (dp 6,1), 45,1 (dp 5,4) e 89,0
  (dp 6,4) problemas, respectivamente (distribuição hipergeométrica). Só por acaso amostral, a
  probabilidade de uma categoria ficar abaixo de 30 é de 1,4e-3 para `matematica` e desprezível
  para as demais. Como `valid` e `test` (28 problemas) dificilmente fecham 100 WAs (1.7), a
  amostra real virá quase toda do `train` (391/269/546, 1.206 no total), com proporções
  praticamente iguais. O risco real é outro: se a taxa de problemas que se tornam `complete`
  (não descartados nem em triagem) for diferente entre categorias, a amostra final se desloca.
  Sem esse efeito, `matematica` só cairia abaixo de 30 se sua taxa de validação fosse menor que
  ~61% da taxa das outras duas juntas (`estrutural_otimizacao`: ~36%; `logica_direta`: ~22%). A
  taxa por categoria só será conhecida depois da validação (piloto e execução completa); o
  relatório traz `pool_distribution` e `distribution` lado a lado para permitir esse
  acompanhamento.
- **[DECIDIDO, 2026-09-20 — gate T037, confirmadas pelos autores sem alteração] Regras
  operacionais do motor**:
  - *Ordem da suíte e veredito*: os testes rodam em ordem fixa (públicos, privados,
    `generated_tests`); o **primeiro** que não termina com sucesso decide o veredito e
    interrompe a execução (curto-circuito). Uma submissão que estoura o tempo em um teste e
    responde errado em outro recebe o veredito do primeiro que falhar.
  - *Comparação de saída* (regra 2): iguais após ignorar espaços em branco ao final de cada
    linha e linhas ou espaços em branco ao final do arquivo; qualquer outra diferença é
    divergência (resto exato, sem comparação por tokens). É a **única** regra de comparação do
    projeto: o mesmo motor avalia depois as suítes geradas pelos modelos. Candidata a reabertura
    segundo o critério objetivo abaixo.
  - *Estabilidade*: um candidato só é retido como WA se duas execuções independentes, até o
    teste decisivo, derem o mesmo veredito e o mesmo teste decisivo (evita reter falhas
    instáveis por comportamento indefinido). O `AC_ref` roda uma vez na seleção e outra na
    auditoria.
  - *Ordem e duplicatas*: as candidatas a WA são percorridas em ordem determinística definida
    pela seed (`42`), contando textos idênticos uma única vez; `AC_ref` é a primeira solução
    correta em C++ na ordem original do dataset (sem substituição se ela falhar, ver acima).
  - *Tempo* (regra 5): medido como tempo de **CPU** do processo filho (não de parede), por
    robustez à carga da máquina; há uma reserva de tempo de parede (3× o limite + 1 s) apenas
    para detectar programas bloqueados. Candidata a reabertura segundo o critério objetivo
    abaixo.
  - *Memória*: o limite do problema é aplicado como limite de **espaço de endereçamento**
    (`RLIMIT_AS`), que não é idêntico à métrica de memória do juiz original (limitação; ver
    1.7).
  - *Isolamento*: cada execução roda com um usuário dedicado por worker, sem privilégios, sem
    rede, com limites de processos e de tamanho de arquivo; o diretório `data/work/` é criado
    com permissão `0700` (dono: o usuário do host), de modo que o código de terceiros não o
    lista, lê nem escreve.
- **[DECIDIDO, 2026-09-20] Critério objetivo de reabertura das regras 2 e 5 (piloto,
  T071)**: as regras de comparação de saída (2) e de tempo (5) são as candidatas mais prováveis
  a revisão, porque uma solução correta (`AC_ref`) reprovada por elas vai para triagem manual
  (D8). O piloto `validate --target 10` (10 problemas do `train`) mede, para cada regra, a
  fração de ACs testados que ela reprova indevidamente. **Definições**: *ACs testados* = os
  problemas do piloto cujo `AC_ref` foi executado pelo motor (qualquer status final, exceto os
  interrompidos por falha de infraestrutura). *Reprovado pela regra 2* = `AC_ref` com veredito
  `WA` cuja saída, no teste decisivo, é igual à esperada quando comparadas por tokens separados
  por espaço em branco (divergência só de formatação; o campo de diagnóstico
  `divergence.format_only` do registro de triagem, que nunca altera um veredito). *Reprovado pela
  regra 5* = `AC_ref` com veredito `TLE`. **Critério**: se, em qualquer uma das duas causas,
  a razão (reprovados ÷ ACs testados) for **maior que 10%** (com cerca de 10 a 12 ACs testados,
  isso significa 2 ou mais casos; 1 caso é tolerado como ruído), a regra correspondente **volta
  a ser marcada como proposta** neste documento, com a etiqueta de proposta descrita na legenda
  do início (o que faz a checagem C6 do gate de documentação falhar até nova decisão), o piloto para e os autores decidem a nova regra; não há mudança automática.
  Cada caso, dentro ou fora do limiar, é inspecionado individualmente (T071) e registrado aqui.
  O limiar de 10% foi escolhido no gate T037 (os autores deixaram o valor em aberto); alterá-lo
  exige atualizar este item, a spec (D13) e as tarefas T071 e T069. O relatório traz as
  contagens (`ac_tested`, `triage_by_cause`) para a execução completa também, sem reabertura
  automática. **Resultado do piloto de 2026-09-21 (1.7)**: regra 2, 1 de 14 ACs testados (7,1%);
  regra 5, 0 de 14; nenhuma das duas reabre. **Na validação completa (264 ACs testados)**: regra 2,
  9 (3,4%); regra 5, 1 (0,4%).
- **[MEDIDO, 2026-09-21 — T049] Refinamentos da implementação do motor** (não alteram as
  regras decididas; detalhes e números em 1.7): (i) o pico de memória de um programa é medido por
  um lançador nativo minúsculo (`sandbox-launch`, compilado na imagem com o GCC fixado), porque o
  `ru_maxrss` medido a partir do processo Python herda o conjunto residente do processo que fez o
  `fork` (40 MB para um programa que usa 0,6 MB) e daria falso MLE em limites pequenos (o menor
  do pool é 61 MiB); (ii) `/tmp` e `/dev/shm` do serviço do motor são privados (`0700`, só do
  orquestrador) e as filas POSIX ficam desligadas (`RLIMIT_MSGQUEUE = 0`), porque essas áreas são
  graváveis por qualquer uid e deixariam o código de terceiros guardar estado entre execuções,
  quebrando o determinismo e a estabilidade; (iii) o serviço usa `init: true`, para recolher os
  órfãos dos grupos de processos mortos; (iv) o `RLIMIT_NPROC = 32` conta o lançador e o
  programa, então um programa consegue criar no máximo 30 filhos. Decisão registrada como D16 da
  spec.
- **Invariante do dataset**: nenhum código C++ é persistido sem antes ter sido executado
  pelo motor com o veredito esperado (AC_ref aprovada em 100% da suíte oficial; cada WA com
  veredito de resposta errada).
- **[VERIFICADO, 2026-09-22 — T080] Retomada e idempotência confirmadas com o motor real** (US4;
  FR-023 a FR-025; SC-006, SC-007): interrompido `validate` com `SIGTERM` de propósito no meio de
  um problema sintético (motor real, sem rede), a retomada descartou o `building/` parcial
  (achado vazio: a interrupção ocorreu antes de qualquer arquivo do problema ser escrito) e
  refez o problema do zero até `complete`, sem pasta duplicada nem arquivo truncado (SC-006). O
  resultado da execução interrompida-e-retomada foi comparado, arquivo a arquivo, com o de uma
  execução limpa sobre a mesma entrada: idêntico, exceto `extraction_timestamp` e o campo medido
  `max_cpu_time_s` (achado registrado em D19, ver 1.5). Este é o primeiro teste DELIBERADO de
  interrupção (o episódio do piloto de 2026-09-21, acima, foi acidental); confirma formalmente o
  que aquele episódio já sugeria.

### 1.5 Estrutura de persistência local (por problema, pasta `<ContestID>_<Index>`)
- `enunciado.md` — texto limpo do problema (`description`).
- `AC_ref.cpp` — solução de referência correta.
- `WA_1.cpp` … `WA_100.cpp` — falhas lógicas validadas.
- `testes.json` — suíte oficial (pública + privada + `generated_tests`, ver 1.1),
  entrada/saída esperada.
- **`validacao.json`** — **[DECIDIDO]** registro de validação: para `AC_ref` e para cada
  WA, o veredito atribuído pelo motor, o padrão de linguagem efetivamente usado na
  compilação e os maiores tempo e memória observados. Torna a validação auditável e permite
  que os módulos seguintes reproduzam a mesma compilação. Acréscimo à estrutura originalmente
  descrita para o TCC. Em problema pendente de triagem, contém também o registro da falha
  de AC (ver 1.4).
- **`metadata.json`** — metadados estruturados do problema, para uso posterior nas
  métricas (análise por macrocategoria — Q1) e para qualquer análise de dados
  exploratória. Schema proposto:

```json
{
  "schema_version": 1,
  "problem_id": "1101_A",
  "cf_contest_id": 1101,
  "cf_index": "A",
  "name": "string",
  "source": "CODEFORCES",
  "cf_rating": 1000,
  "cf_points": 500.0,
  "cf_tags": ["math"],
  "macrocategoria": "matematica",
  "time_limit_seconds": 2.0,
  "memory_limit_bytes": 256000000,
  "is_description_translated": false,
  "dataset_split_origem": "train",
  "num_wa_brutos_disponiveis": 247,
  "num_wa_validados": 100,
  "extraction_timestamp": "2026-09-18T22:00:00Z"
}
```

  Campos `num_wa_validados` e `num_wa_brutos_disponiveis` servem tanto para
  auditoria (confirmar que a meta de 100 foi batida) quanto para uma futura análise
  de correlação entre "quantidade de falhas humanas disponíveis" e "eficácia de
  detecção" — não estava nos objetivos originais, mas é subproduto praticamente
  gratuito de já estarmos coletando esse número. `macrocategoria` usa os valores
  `"matematica"`, `"estrutural_otimizacao"`, `"logica_direta"` (snake_case,
  consistente com nomes de campo em Python/Pydantic).

  **[DECIDIDO]** `extraction_timestamp` é gravado uma única vez, quando o problema é
  persistido, e preservado nas retomadas; fica fora da comparação de igualdade entre
  execuções independentes. O manifesto de integridade (1.6) identifica, portanto, uma versão
  específica do dataset, e não uma reprodução bit a bit por reexecução do zero.

  **[DECIDIDO — achado em 2026-09-22, D19, prova real de retomada]** `extraction_timestamp`
  não é o único campo que varia entre duas execuções independentes de `validate`: o campo
  medido `max_cpu_time_s` de `validacao.json` (tempo de CPU real, microssegundos, de `wait4`)
  também varia, por ruído real de medição de hardware, nunca por mudança de seleção. A prova
  real (interromper `validate` com `SIGTERM` no meio de um problema sintético, retomar,
  comparar com uma execução ininterrupta sobre a mesma entrada, motor real) confirmou que TUDO
  o mais é idêntico nas 101 entradas (`ac_ref` e as 100 `wa`): mesmo `sha256`, `source_index`,
  `deciding_test`, `standard_used` e `max_memory_bytes` (que é de granularidade de página do
  SO e por isso se mostrou estável). Não é um defeito — é esperado que uma medição real de
  desempenho não seja determinística bit a bit em hardware real; só o motor falso dos testes
  unitários (que devolve uma constante fixa) escondia essa variação. Não afeta o reempacotamento
  do MESMO conjunto já validado (`package` não roda `validate` de novo, então o hash do zip
  continua idêntico ao reempacotar os mesmos bytes já em disco, SC-008). Detalhes: spec, D19.

  **[CORRIGIDO — definido no plano]** Todo JSON do dataset (`metadata.json`, `testes.json`,
  `validacao.json`) traz `schema_version` (inteiro, começa em 1), por exigência de contratos
  versionados (Constitution, princípio IV). `cf_points` é `float` (o dataset traz `float32`).
  `num_wa_brutos_disponiveis` é a contagem de submissões incorretas em C++ do dataset
  **antes** da remoção de textos duplicados. `validacao.json` tem `status` (`complete`,
  `pending_triage` ou `discarded`): só problemas `complete` entram em `data/dataset.zip`; a
  pasta local de trabalho guarda também os demais estados, para não reprocessá-los.

### 1.6 Empacotamento e integridade
Após a extração e a validação únicas, o dataset é compactado de forma determinística em
`data/dataset.zip` e acompanhado de um manifesto de integridade (hash SHA-256 de cada
arquivo do dataset e do próprio pacote), versionado no repositório em
`manifests/dataset.manifest.json` (**[DECIDIDO, 2026-09-19]** fora de `data/`, que é
ignorado pelo Git exceto o zip). Arquivos soltos do
dataset e mutantes nunca são versionados. Um comando de verificação recalcula os hashes e
os compara com o manifesto. Ver Constitution, princípio 2 (v1.1.0).

**[DECIDIDO no plano]** O relatório final da extração (funil, motivos de exclusão,
distribuição por macrocategoria, alertas, problemas pendentes de triagem) também é versionado,
em `manifests/extraction_report.json`, para que os números citados no trabalho escrito
acompanhem a versão exata do dataset. O tamanho do zip é estimado em ~10 MB (ver 1.7), bem
abaixo do limite de 100 MB por arquivo do GitHub; o comando de empacotamento avisa a partir de
95 MB. O hash do `.zip` é reproduzível dentro da imagem fixada (a compressão depende da versão
da biblioteca zlib); a identidade do conteúdo entre ambientes é garantida pelos hashes por
arquivo do manifesto.

**Circulação do dataset entre os autores** (descrição do fluxo especificado, 2026-09-20). O
dataset é gerado uma única vez, por um dos autores, com as fases `extract`, `validate`, `audit` e
`package`, cada uma um comando manual e separado (o zip só existe depois de `package`, com a meta
de 200 problemas atingida, ou com `--allow-partial`). Só `data/dataset.zip` e `manifests/` são
versionados; o outro autor recebe o dataset por `git pull`, descompacta com
`unzip data/dataset.zip -d data/` e confere com a verificação de integridade, sem rodar extração
nem validação. O espaço de trabalho `data/work/` (problemas extraídos, inclusive os que a validação
não processou, e os descartados ou em triagem) é local a quem gera, permanece fora do Git e não é
apagado por nenhum comando (a especificação não prevê limpeza); as fases posteriores só leem o
que está em `data/work/` e o resultado publicado é o zip. Cada autor constrói a própria imagem
Docker, idêntica pela fixação de versões, e o dataset chega aos contêineres pelo volume `./data`,
não pela imagem.

**Reparo de WA que diverge na auditoria (2026-09-22, T072/D18, reparo automático)**. A auditoria da execução completa (2026-09-21) achou 13 WA divergentes, em 12 dos 200 problemas (6,5% dos problemas completos): 10 vereditos instáveis entre duas execuções da própria auditoria, 3 com o mesmo veredito WA mas em outro teste decisivo, 2 que passaram a dar `TLE` e 1 a dar `RE`. A inspeção do código-fonte confirmou a causa em cada caso: **comportamento indefinido** (acesso fora dos limites de um vetor — por exemplo `long long A[3]; ... A[3]` em `73_A/WA_15.cpp`, que lê a posição seguinte à última válida; variável não inicializada usada antes de ser atribuída — `WA_5.cpp` de `1230_B`, `WA_87.cpp` de `574_A`) ou **execução no limiar do limite de tempo** (um laço cuja duração real varia com a máquina, sem UB). Em ambos os casos, o resultado exato não depende só da entrada, e um candidato assim é um mau "gabarito" fixo para as métricas do experimento.

**Investigação de causa (ASLR) e por que não foi adotada como correção**: a hipótese inicial era que o endereçamento aleatório do kernel (ASLR) fizesse a memória "lixo" lida pelo comportamento indefinido variar entre execuções, e que desligá-lo (`personality(ADDR_NO_RANDOMIZE)`) tornaria os programas deterministicamente reprodutíveis. Verificado por chamada direta ao `personality()`: o perfil de seccomp padrão do Docker recusa essa chamada mesmo como root (`EPERM`), mesmo sem alteração de capabilities; confirmado que liberá-la exigiria um perfil de seccomp customizado (risco de infraestrutura não avaliado). Além disso, ASLR não explica os casos no limiar do tempo, que são de variação real de execução, não de memória. Por isso a correção foi na seleção dos candidatos, não no ambiente de execução.

**Decisão (D18), reparo automático**: `audit` (`dataset.validation.repair`) substitui cada WA divergente pelo próximo candidato não tentado da mesma ordem determinística da seleção original (a mesma regra de D13/R12), exigindo dele uma confirmação mais forte — três checagens de estabilidade independentes (2 execuções cada, ou seja, 6 execuções concordantes) contra as 2 da seleção original — e falha explicitamente se os candidatos não tentados se esgotarem sem um substituto confirmado. O número de WA continua exatamente 100, na mesma numeração, e nenhum outro arquivo do problema é tocado.

**Falha na implementação do reparo, achada e corrigida (2026-09-22, segunda execução real do `audit`)**. Depois do primeiro reparo (13 WA em 12 problemas), os autores rodaram a auditoria de novo sobre o resultado já reparado: **8 das 13 WA reparadas (62%) voltaram a divergir**, uma taxa alta demais para ser só a sorte de encontrar outro candidato instável. A investigação achou um bug real na confirmação: o laço de "duas passadas independentes" sobrescrevia a mesma variável a cada volta, então só a última passada era guardada; uma terceira chamada separada comparava só essa última contra si mesma; e o valor de fato gravado em disco vinha de uma **quarta** chamada, nunca comparada a nada. A garantia de "4 execuções concordantes" descrita acima nunca existiu de fato: bastavam duas concordarem por acaso. Corrigido: a função agora reúne todas as `CONFIRMATION_PASSES` passadas numa lista, exige que todas concordem com a primeira, e grava um valor que foi de fato conferido. O número de passadas também subiu de 2 para 3 (6 execuções no total), dado que a taxa de recorrência mostrou candidatos instáveis comuns o bastante nesses problemas específicos para não bastar o mínimo. Um teste de regressão reproduz exatamente o cenário do bug (uma passada discorda, as outras duas concordam por acaso) e prova que a versão antiga aceitava e a corrigida rejeita.

**Convergência e decisão de aceitação (2026-09-22, 3 rodadas de `audit`)**. Resumo exato (por `problem_id`, contando cada `WA_<n>.cpp`): rodada 1 (antes de existir reparo) achou 16 WA divergentes em 13 problemas; rodada 2 (primeiro `dataset.validation.repair`, com o bug de confirmação) reparou 11 WA em 9 problemas; rodada 3 (repositório na revisão `7784486`, com a confirmação corrigida de 6 execuções) reparou mais 10 WA em 10 problemas. No total, **20 dos 200 problemas (10%)** precisaram de pelo menos um reparo em alguma rodada. Nenhum dos 11 WA reparados na rodada 2 voltou a divergir na rodada 3 — um sinal positivo mesmo com a confirmação então mais fraca. Cinco casos da rodada 3 eram candidatas nunca antes tocadas (confirmadas só pelas 2 execuções originais da seleção), incluindo `349_A/WA_25.cpp`, que já tinha divergido na rodada 1, passou sem problema na verificação da rodada 2, e voltou a divergir na rodada 3 — a mesma candidata, testada 3 vezes de forma independente, com 2 resultados concordantes e 1 discordante.

**Leitura estatística, e por que "rodar até dar zero" não é o critério certo**: a própria auditoria confere cada WA com apenas 2 execuções (a mesma força da seleção original), não com as 6 do reparo — o reparo só fortalece as candidatas que ele efetivamente toca. Com ~26.400 WA no dataset, mesmo uma taxa pequena e real de veredito instável por execução (a ordem de grandeza sugerida pelas 3 rodadas: dezenas em 26.400, bem abaixo de 0,1%) faz esperar que **qualquer rodada nova de `audit` encontre um punhado de casos novos, por acaso**, mesmo que o dataset não esteja piorando — é ruído estatístico de testar uma população grande com um crivo de 2 execuções, não um sinal de que o processo diverge. Perseguir "zero divergências" como critério de parada não é praticável nem necessário.

**Decisão dos autores (2026-09-22)**: aceitar o estado atual (pós-rodada 3) como a base de trabalho a partir daqui, sem mais rodadas de auditoria neste ciclo. Fica combinado rodar `audit` **mais uma vez, como fechamento, imediatamente antes do `package`** (T093) — não para perseguir zero, mas como a conferência final de praxe antes de gerar o zip; qualquer coisa que ela reparar nesse momento é aceita como parte do processo normal, sem exigir uma rodada extra.

### 1.7 Dados empíricos medidos durante o planejamento (2026-09-19)

**[CORRIGIDO]** Números medidos durante o `/speckit-plan` da feature `001-dataset-extraction`,
em **2026-09-19**, com a biblioteca `datasets` 5.0.1 em streaming sobre a revisão
`802411c3…` e um contêiner `gcc:13.2.0` (Docker 29.7). Estão aqui para alimentar o texto do
trabalho; devem ser reverificados se a revisão do dataset mudar.

**Disponibilidade de submissões em C++ (só problemas elegíveis)**

| Conjunto | Amostra | Incorretas em C++ por problema | Com ≥ 100 |
|---|---|---|---|
| `train` | 150 elegíveis (streaming embaralhado, buffer 300, seed 7; aproximação de amostra aleatória; medido antes do critério de E/S por arquivo) | mín. 0, p10 102, p25 196, **mediana 200**, p75 281, p90 317, máx. 629 | 99% (148 de 150); ≥ 150: 87%; ≥ 200: 57% |
| `valid` + `test` | os 29 elegíveis (todos) | mín. 98, **mediana 101**, máx. 217 | 28 de 29 (brutas); 25 de 29 (textos únicos) |

Soluções corretas em C++ por problema: `valid`+`test` mín. 32, mediana 100, máx. 224 (nenhum
problema sem); `train` mediana 197, com 1 de 150 sem nenhuma.

**Consequência para a amostra**: o corte de 100 WAs *validados* depende de quantas incorretas
são WA de verdade (as demais são TLE, MLE, RE, erro de compilação ou passam nos testes), e
isso só o motor mede. Em `valid`/`test` (~101 incorretas brutas) fechar 100 é praticamente
impossível, então a amostra de 200 tende a vir quase toda do `train`; a especificação não
impõe equilíbrio entre splits. Se a fração de WA validada for baixa, a meta de 200 problemas
com exatamente 100 WAs pode não fechar sem relaxar critérios (decisão dos autores; nenhuma
relaxação é automática). A medição da fração real é o "piloto" do roteiro de aceite, feito em
2026-09-21 (resultado logo abaixo: 85,5% das candidatas viraram WA no `train`).

**Extração real (2026-09-20; revisão `802411c3…`, seed 42, código na revisão git `7440706`)**,
medida sobre os 1.234 problemas do pool:

- Incorretas em C++ por problema (`raw_wa_count`, antes de remover duplicatas): todas ≥ 100 por
  construção (é a pré-checagem); mín. 100, **mediana 200**, máx. 679. `train` (1.206): mediana
  201; `valid` (9): mediana 101, máx. 192; `test` (19): mediana 101, máx. 217. Muitos problemas
  ficam perto do corte: 138 têm entre 100 e 109 e 167 têm menos de 150 (144 no `train`, 8 no
  `valid` e 15 no `test`; 23 dos 28 de `valid`+`test`). Esses são os que mais provavelmente não
  chegam a 100 WAs validados (D4); o piloto mede isso.
- Soluções corretas em C++ por problema (`raw_ac_count`): mín. 28, mediana 195.
- Testes por problema, no pool inteiro (medianas): 2 públicos, 17 privados e 91 gerados
  (`generated_tests`, máx. 200). O número de 200 gerados citado abaixo é de `valid`+`test`, uma
  população menor e diferente.
- Limites lidos dos metadados: tempo de 0,5 a 10 s; memória de 61,0 MiB (64 MB) a 976,6 MiB
  (1.024 MB).
- Disco: `data/work/` ocupou 104 MB, sendo 103 MB em `staging/raw` (1.234 arquivos `json.gz`);
  `pool.json` tem 248 KB.
- Consistência (verificação de 2026-09-20): 41 checkpoints completos somando 13.610 linhas; os
  1.234 arquivos `raw` são exatamente os problemas do `pool.json`; todos validam nos schemas;
  `problem_id`, rating (1000 a 1600), tradução, macrocategoria (reclassificada a partir das tags)
  e contagens de soluções conferem em todos, sem nenhuma inconsistência.

**Piloto de validação (2026-09-21, T071; `validate --target 10`, 4 processos em 8 CPUs, código da
feature 001 na revisão git `5121759` mais a US3, ainda sem commit)**. O piloto foi interrompido
uma vez por SIGTERM ao fim de uma sessão e retomado: a retomada descartou o parcial de `building/`
e pulou os problemas encerrados, como projetado; o episódio levou a tratar SIGTERM como
interrupção segura. Números sobre os 14 problemas processados, todos do `train` (a ordem do pool é
embaralhada e o piloto não chegou a `valid`/`test`):

- Estados: 10 `complete` (3 `matematica`, 5 `estrutural_otimizacao`, 2 `logica_direta`), 3
  `pending_triage` e 1 `discarded`.
- Candidatas a WA consumidas (1.169, nos 11 problemas cujo `AC_ref` passou): **1.000 viraram WA
  (85,5%)**, 121 passam em todos os testes oficiais (10,3%; 91 delas só em `1_B`, e 3,1% nos
  demais), 33 não compilam (2,8%), 9 têm `RE` (0,8%), 3 `TLE`, 2 `MLE` e 1 tem veredito instável
  entre as duas execuções. Por problema completo, o motor consumiu de 101 a 203 candidatas
  (mediana 108) para reunir 100 WA; a fração de WA por problema tem mediana de 93% e mínimo de
  49% (`1_B`). O risco de que poucas incorretas fossem WA de verdade **não se materializou no
  `train`**.
- Descarte: `340_D` (`insufficient_wa`): só 100 textos distintos e 1 deles passa em todos os
  testes, então 100 WA já eram impossíveis; a parada antecipada o encerrou em 10 s.
- Tempo por problema `complete`: mediana 102 s (mín. 76 s, máx. 338 s, média 127 s; 1.270 s no
  total); uma triagem custa de 4 a 6 s; os 14 problemas somaram 1.294 s. **Extrapolação, de uma
  amostra pequena e não medida**: 10 completos em 14 processados (71%) dão ~281 problemas para
  200 completos, a ~92 s cada com 4 processos: ~7 h (a estimativa do planejamento era ~6 h com 8
  processos). O tempo real é o da execução completa (T072).
- Projeção de déficit: nenhuma. O pool tem 1.234 problemas (1.206 no `train`) e a taxa de
  conclusão observada daria cerca de 850 completos, muito acima de 200; o comportamento de
  `valid`/`test` (28 problemas) segue desconhecido.
- **Triagens de AC: 3 dos 14 ACs testados (21%), cada uma inspecionada individualmente**:
  `616_D` (enunciado: "if there are several longest segments you can print any of them":
  várias respostas válidas, o verificador especial que escapou do filtro de tags, o caso
  previsto em D8); `1529_B` (o gabarito de `public_tests[0]` começa com uma linha em branco,
  `"\n4\n5\n..."`, e o `AC_ref` imprime `"4\n5\n..."`: tokens idênticos, `format_only`; a regra 2
  reprova e o verificador do Codeforces aceitaria); `13_A` (o enunciado limita `3 <= A <= 1000`,
  mas 23 dos 100 `generated_tests` têm `A > 1000`, até 1.869, e o `AC_ref`, correto dentro das
  restrições, erra neles: em `generated_tests[17]`, `A = 1209`, o gabarito `263450/1207` bate com
  um cálculo independente e o `AC_ref` imprime `15497/71`). **Os `generated_tests` do dataset
  podem conter entradas fora das restrições do problema**, o que reprova um AC correto.
- Critério de reabertura de D13 (1.4): regra 2, 1 de 14 = 7,1% (limiar de 10%: **não reabre**);
  regra 5, 0 de 14; as outras 2 de 14 (14%) não fazem parte do critério.

**Validação completa (2026-09-21, T072; `validate` com 4 processos, 5 h 06 min de relógio, código
na revisão git `ee3a422`)**. A execução atingiu a meta (`included 200 of 200`, déficit 0), em uma
única passada, sem interrupções registradas. Sobre os 264 problemas processados (posições 0 a 263
da ordem embaralhada do pool de 1.234; inclui os 14 do piloto):

- Estados: **200 `complete` (75,8%)**, 21 `discarded` (`insufficient_wa`; 19 do `train` e 2 do
  `test`) e 43 `pending_triage` (16,3%). Os 970 problemas restantes do pool não foram tocados.
- **Amostra final**: por macrocategoria, `logica_direta` 98, `estrutural_otimizacao` 61 e
  `matematica` 41 (pool: 549/407/278); por origem, `train` 198, `test` 2 e `valid` 0 (dos 28
  problemas de `valid`/`test`, só 5 foram processados: 2 completos, 2 descartados e 1 em triagem). O
  alerta de menos de 30 problemas por macrocategoria **não disparou**.
- Candidatas a WA consumidas (24.423): 20.666 viraram WA (84,6%), 2.661 passam em todos os testes
  oficiais (10,9%), 648 não compilam (2,7%), 285 têm `RE` (1,2%), 126 `TLE` (0,5%), 27 têm veredito
  instável (0,1%) e 10 `MLE`. Por problema completo, o motor consumiu de 100 a 204 candidatas
  (mediana 108); a fração de WA por problema tem mediana de 93% e mínimo de 49%. Em 29 dos 200
  problemas completos, 20 ou mais candidatas (até 96) passam em todos os testes oficiais: são
  submissões marcadas como incorretas no dataset que a suíte oficial não reprova.
- Tempo por problema completo: mediana de 83 s (mín. 68 s, máx. 338 s, média 90 s; 18.081 s no
  total dos 200); os 264 somaram 19.646 s (5,5 h, dos quais 5 h 06 min foram medidos de relógio
  na execução, sem os 14 do piloto). O piloto tinha extrapolado ~281 problemas e ~7 h; o real foi
  264 problemas e 5 h 06 min.
- **Triagens de AC: 43 dos 264 ACs testados (16,3%)**, todas mantidas em `pending_triage` e
  **não inspecionadas** por decisão dos autores (D17), já que a meta foi atingida sem elas. Por causa,
  segundo o relatório: divergência só de formatação 9 (3,4%), `TLE` 1 (0,4%), outras 33 (12,5%; 31
  com saída diferente, 1 erro de compilação e 1 `RE`). A divergência apareceu em `public_tests`
  em 31 casos, `private_tests` em 6 e `generated_tests` em 3. **Classificação heurística, não
  inspeção** (compara as saídas): dos 42 com saída diferente, 9 só de formatação, 2 só de
  maiúsculas e minúsculas (`Yes`/`YES`), 9 com os mesmos tokens em outra ordem (típico de problema
  com várias respostas válidas), 4 numericamente próximos (típico de tolerância de ponto flutuante)
  e 16 com valores diferentes (a inspecionar só se houver déficit).
- Critério de reabertura de D13 (definido para o piloto, aqui só informativo): regra 2, 9 de 264
  (3,4%); regra 5, 1 de 264 (0,4%); ambas abaixo do limiar de 10%.
- Ainda **não** executados: `audit` (a auditoria) e `package`.

**Volume de testes (`valid`+`test`, 29 problemas)**: mediana de 202 testes por problema (mín.
43, máx. 241), dos quais mediana de 200 são `generated_tests` (mín. 41); carga de texto dos
testes com mediana de ~12,7 KB por problema (máx. 65 KB); ~170 KB de código-fonte para 100
submissões. Estimativa (não medida no pacote real): ~40 MB sem compressão e ~10 MB
compactado para 200 problemas.

**Verificações de ambiente (GCC 13.2.0, Debian 12)**

- `-Wl,--stack=268435456` falha no linker do Linux; sem ele, compila (ver 1.4).
- Pilha: com `ulimit -s 262144` (KiB) uma recursão de ~150 MB conclui; com o padrão de 8 MiB
  termina em falha de segmentação; com 256 MiB e ~500 MB de pilha necessária volta a estourar
  (o limite é real, não infinito).
- Memória: sob limite de espaço de endereçamento de 256 MiB, alocar 300 MB termina com
  `SIGABRT` (`std::bad_alloc`); alocações não tocadas também contam (o limite é de espaço
  virtual, não de memória residente).
- Isolamento: um filho com usuário dedicado tem zero capabilities, não lê nem escreve em um
  diretório de dados com permissão 0700, não escreve no sistema de arquivos raiz e uma fork
  bomb é contida pelo limite de processos. Constatado em 2026-09-19, na análise de consistência
  da spec: o `./data` montado no contêiner do motor herda a permissão do host (tipicamente
  `0755`) e o filho de usuário dedicado conseguiria **lê-lo**; por isso `data/work/` é criado
  com `0700` (ver D15 na spec).

**Reconfirmado com o motor implementado (2026-09-21, T049; contêiner `sandbox`, GCC 13.2.0)**

- `-Wl,--stack=268435456` continua falhando no linker (`/usr/bin/ld: unrecognized option
  '--stack=268435456'`); sem ele, compila.
- Pilha: uma recursão de ~150 MB (150.000 níveis de ~1 KB) termina em falha de segmentação com a
  pilha padrão de 8 MiB (código 139), conclui com `ulimit -s 262144` e com o motor, e uma de
  ~600 MB estoura os 256 MiB; o teste do motor com 400.000 níveis (~416 MB) termina como `RE`.
- Memória: sob `RLIMIT_AS` de 128 MiB, alocar 512 MB termina com `SIGABRT` e `std::bad_alloc` no
  `stderr`, classificado como `MLE` (o planejamento usou 256 MiB e 300 MB; mesmo mecanismo).
- Isolamento (todos como no planejamento): o filho roda como uid e gid `10000 + slot`, sem
  nenhuma capability (`CapEff = CapPrm = 0`) e sem grupos suplementares; não lista, lê nem grava
  `data/work/` (`0700`), nem grava em `/`, `/etc`, `/sandbox` ou no diretório de outro slot; uma
  fork bomb é contida (30 filhos no máximo, nenhum sobrevive à execução); só existe a interface
  `lo`.
- **Diferenças encontradas (corrigidas, D16)**: (a) `/tmp`, `/dev/shm` e `/dev/mqueue` eram
  graváveis pelo filho, o que permitiria guardar estado entre execuções; agora `/tmp` e
  `/dev/shm` são `tmpfs` `0700` e `RLIMIT_MSGQUEUE = 0`; (b) sem processo de init, os órfãos de um
  grupo morto ficavam como zumbis (o PID 1 era o próprio Python), então o serviço passou a usar
  `init: true`; (c) `ru_maxrss` medido a partir do Python vinha inflado (40 MB para um programa de
  0,6 MB): com o lançador, o mesmo programa mede 652 KiB e um programa que toca 100 MB mede entre
  100 e 130 MiB. O pico de memória só existe quando o lançador termina normalmente (não no
  estouro da reserva de tempo de parede, onde o veredito é `TLE` de qualquer forma).
- Custos medidos: compilar com `gnu++20 -O2 -static` leva 0,07 s para um programa mínimo e
  **2,5 s** com `#include <bits/stdc++.h>` (a estimativa do planejamento era ~2 s); executar um
  teste tem 2,5 ms de sobrecarga (mediana; p95 de 3,1 ms); o `selfcheck` (9 programas, cada um
  duas vezes) leva cerca de 7 s.

**Tempo de extração**: uma passagem completa em streaming, só com colunas leves, levou de 24 a
28 min (com retentativas automáticas de rede; foram observados resets de conexão). A extração
real de 2026-09-20, com todas as colunas e gravando os problemas do pool, levou cerca de 23 min
(pelos horários dos arquivos gravados, das 22:41 às 23:04); o volume de rede não foi medido.

---

## 2. Módulo: Geração de Mutantes

**Objetivo**: gerar 100 versões defeituosas (mutantes) por problema, a partir do
`AC_ref.cpp`, para medir sensibilidade das suítes a defeitos sintéticos sutis.

**Operadores de mutação** (substituição direta, mutação de primeira ordem):

| Categoria | Permutações |
|---|---|
| Relacionais | `==`↔`!=`, `<`↔`<=`, `>`↔`>=` |
| Aritméticos | `+`↔`-`, `*`↔`/`, `++`↔`--` |
| Lógicos | `&&`↔`\|\|` |

- **Primeira ordem**: um mutante = uma alteração. Se o código-fonte não tiver
  ocorrências suficientes de operadores para atingir 100 mutantes de primeira
  ordem, aciona-se **mutação de ordem superior** (combinar duas mutações
  simultâneas em locais distintos do mesmo arquivo) até completar a cota.

**Validação antes de aceitar um mutante**:
1. **Unicidade léxica**: texto do mutante não pode ser idêntico a nenhum já
   armazenado (hash set).
2. **Compila e executa** dentro dos mesmos limites de tempo/memória do problema
   original. Mutantes que geram TLE/MLE/RE são descartados (defeito estrutural, não
   de lógica de negócio).
3. **Não é mutante equivalente**: executa contra a suíte de testes oficial do
   Codeforces; se passar em 100% (comporta-se como AC), é equivalente → descartado.

Resultado: exatamente 100 mutantes comportamentalmente distintos e válidos por
problema. Como mutantes equivalentes já são descartados nesta etapa, o termo `EM`
(mutantes equivalentes) na fórmula do Escore de Mutação (seção 5) é sempre 0 no
cálculo final do pipeline.

---

## 3. Módulo: Orquestração de IA / Geração de Prompt

**[PENDENTE — parte menos polida da metodologia, especialmente a configuração do SLM.
Tratar como rascunho a refinar em conjunto durante o /speckit.clarify deste módulo.]**

**Modelos avaliados**:
- GPT-5.4-mini (OpenAI, API) — `reasoning_effort: medium`, saída travada em JSON
  (`strict: true`), sem retenção de histórico (`store: false`).
- Gemini 3.5 Flash (Google, API) — `thinking_level: medium`, `generateContent`
  (stateless nativo), saída `mimeType: application/json`.
- Qwen2.5-Coder-7B (local, via Ollama) — sem parâmetro de esforço de raciocínio
  (limitação arquitetural do modelo, considerar na análise de resultados), saída
  `format: json`, cada chamada disparada sem retenção de histórico.

**Regra de isolamento**: toda requisição é *stateless* — nenhum modelo pode reter
contexto de chamadas anteriores. Isso é requisito de arquitetura, não só de prompt
(ver Constitution, princípio 3).

**Particularidade do SLM — oráculo por execução [confirmar/refinar]**: diferente dos
dois modelos de fronteira (que preveem o `expected_output` de forma preditiva, o que
é suscetível a erro), o SLM deve gerar sua própria solução de referência e executá-la
sobre as entradas que ele mesmo formula, derivando o `expected_output` de execução
real (não de predição). Isso é tratado como comportamento agêntico: delega o cálculo
da saída a um interpretador determinístico em vez da rede neural. **Ponto em aberto**:
detalhamento operacional de como isso é orquestrado (quando o SLM roda seu próprio
código, onde isso é validado, o que acontece se o código de referência gerado por
ele estiver incorreto) ainda precisa ser fechado pela dupla.

**Template de prompt**: estrutura única em inglês, com marcação XML (`<system_rules>`,
`<context_data>`, `<few_shot_example>`, `<task>`), combinando Few-Shot Prompting +
Chain-of-Thought. Antes de gerar os testes, o modelo é obrigado a preencher um campo
de análise prévia de casos-limite (`edge_cases_analysis`) — reduz alucinação e
superficialidade. Um caso de teste público real do dataset é incluído como exemplo
estrutural.

**Composição dos 3 cenários**: a única variação entre eles é o conteúdo do bloco
`<context_data>` do template — todo o resto (regras de sistema, formato de saída,
parametrização dos modelos) permanece fixo:
1. Caixa-Preta → só enunciado.
2. Caixa-Branca → só `AC_ref.cpp`.
3. Híbrida → enunciado + `AC_ref.cpp`.

---

## 4. Módulo: Execução Isolada (Sandbox) e Avaliação

**Pipeline de compilação e motor de execução**: é o mesmo motor construído e verificado
no módulo do dataset (seção 1.4), sem alterações — GCC, flags originais do Codeforces
(exceto `-Wl,--stack`, substituído pelo limite de pilha de 256 MiB em tempo de execução),
fallback de padrão gnu++20→17→14→11. Nenhum código do dataset chega a esta etapa sem já
ter passado por esse motor com o veredito esperado. Os limites de pilha e memória são
aplicados por rlimits e o tempo é medido como tempo de CPU; ver as regras operacionais em 1.4.

**Injeção de testes**: as suítes geradas pela IA (pares entrada/saída esperada) são
injetadas via `stdin` no binário compilado, dentro de sandbox com limites de
tempo/memória do próprio problema (kernel Linux).

**Avaliação em curto-circuito**: os casos de teste gerados são aplicados
sequencialmente a cada código-alvo (AC, WA ou mutante). No primeiro teste que o
código falhar, o veredito é registrado imediatamente como reprovado — os testes
restantes daquele arquivo são abortados (economia de recursos). Aprovação (AC) só é
concedida se o código sobreviver a 100% da suíte gerada pela IA.

**Saída**: registro CSV consolidando o comportamento de cada código frente a cada
suíte gerada — é o insumo direto para o cálculo das métricas (seção 5).

---

## 5. Módulo: Métricas de Avaliação

### 5.1 Taxa de Detecção de Falhas Reais (TDF)
Mede a eficácia prática da suíte contra falhas lógicas reais (WA) escritas por
humanos.

$$TDF = \left(\frac{W_{det}}{W_{total}}\right) \times 100$$

onde `W_det` = nº de WAs reprovados por ao menos um teste da suíte gerada pela IA;
`W_total` = universo de WAs validados para o problema (100). TDF final de um cenário
= média aritmética entre os 200 problemas.

### 5.2 Escore de Mutação (Mutation Score — MS)
Mede a sensibilidade da suíte a defeitos sintéticos sutis (mutantes).

$$MS(P,T) = \frac{DM}{M - EM}$$

`DM` = mutantes mortos (reprovados) pela suíte `T`; `M` = total de mutantes gerados
(100); `EM` = mutantes equivalentes — sempre 0 no pipeline, pois já são descartados
na geração (seção 2).

### 5.3 Taxa de Falsos Positivos (TFP) — Alucinações
Mede confiabilidade: ocorre falso positivo quando a suíte gerada pela IA reprova o
código de referência correto (`AC_ref.cpp`), que deveria passar em 100% dos testes.

$$TFP = \left(\frac{FP}{N}\right) \times 100$$

`FP` = nº de problemas em que o AC foi incorretamente reprovado pela suíte da IA;
`N` = total de problemas no cenário (200).

### 5.4 Índice de Influência do Contexto (IIC) — métrica nova, definida pela banca
**Objetivo**: quantificar, em valor absoluto, se combinar requisito + código
(abordagem híbrida) foi benéfico (sinergia) ou prejudicial (viés/sobrecarga de
contexto) em relação a usar cada insumo isoladamente.

Sejam os conjuntos de falhas detectadas por cada abordagem: `D(R)` (apenas
Requisito), `D(C)` (apenas Código), `D(H)` (Híbrida).

**IIC do Código sobre o Requisito** — impacto de revelar a implementação (AC) a um
modelo que já tinha a regra de negócio via requisito:
- Ganhos `G = |D(H) \ D(R)|` (falhas que só o Híbrido pegou, não o Requisito isolado).
- Perdas `P = |D(R) \ D(H)|` (falhas que o Requisito pegou e o Híbrido perdeu — viés).

$$IIC_{cod} = \frac{G - P}{|D(R)|} \times 100$$

**IIC do Requisito sobre o Código** — impacto de documentar a regra de negócio para
um modelo que operava só por análise estrutural (Caixa-Branca):
- Ganhos `G = |D(H) \ D(C)|`.
- Perdas `P = |D(C) \ D(H)|`.

$$IIC_{req} = \frac{G - P}{|D(C)|} \times 100$$

**Interpretação**:
- `IIC > 0` → **Sinergia**: o insumo adicional expandiu a cobertura (saldo líquido
  positivo de novas falhas detectadas).
- `IIC < 0` → **Sensibilidade negativa**: o insumo causou sobrecarga de contexto ou
  viés de implementação, degradando a capacidade original do modelo.

**[PENDENTE]**: esta métrica ainda não está operacionalizada no pipeline (não havia
sido incorporada à seção de Métricas do texto atual da metodologia). Precisa de
`spec`/`plan` próprios no módulo de métricas — provavelmente exige que o módulo de
avaliação (seção 4) registre, por problema e por cenário, o **conjunto exato de WAs
detectados** (não só a taxa agregada), já que o cálculo do IIC depende de operações
de conjunto (`\`, diferença) entre os cenários. A macrocategoria persistida em
`metadata.json` (seção 1.5) permite cruzar o IIC por categoria também, respondendo
diretamente ao objetivo específico de mapear desempenho por categoria algorítmica.

---

## 6. Pendências Consolidadas (não inventar — decidir com a dupla)

1. ~~Mapeamento exato de tags do Codeforces → macrocategoria algorítmica~~ —
   **RESOLVIDO** (ver seção 1.3).
2. Detalhamento operacional da estratégia de oráculo por execução do SLM (módulo 3).
3. Operacionalização do IIC no módulo de métricas: como e onde os conjuntos `D(R)`,
   `D(C)`, `D(H)` de falhas detectadas são registrados para permitir o cálculo de
   diferença de conjuntos.
4. ~~**[PROPOSTA]** Extrair dos três splits combinados~~ — **RESOLVIDO** (ver 1.1).
5. ~~**[PROPOSTA]** Adicionar `is_description_translated == false` como critério de
   elegibilidade~~ — **RESOLVIDO** (ver 1.2).
6. ~~**[PROPOSTA]** Persistir `generated_tests` em `testes.json`~~ — **RESOLVIDO** (ver
   1.1 e 1.5).
7. ~~Flag `-Wl,--stack` incompatível com Linux~~ — **RESOLVIDO** (ver 1.4).
8. ~~Tratamento de problemas com menos de 100 WAs; seleção dos 200 e balanceamento por
   macrocategoria~~ — **RESOLVIDO** (ver 1.4).
9. ~~Passar também o AC pelo motor de execução~~ — **RESOLVIDO** (ver 1.4).
10. ~~Problemas que leem/escrevem por arquivo (`input.txt`/`output.txt`)~~ — **RESOLVIDO**:
    critério de elegibilidade "sem E/S por arquivo" (ver 1.2).
11. ~~Valor da seed~~ — **RESOLVIDO**: `42` (ver 1.4).
12. ~~Números do dataset (4.044/3.760)~~ — **RESOLVIDO**: corrigidos por medição, 2026-09-19
    (ver 1.1 e 1.2).
13. ~~Onde fica o manifesto de integridade~~ — **RESOLVIDO**: `manifests/`, fora de `data/`
    (ver 1.6).
14. ~~**[PROPOSTA]** Regras operacionais do motor (ordem da suíte, comparação de saída,
    estabilidade, tempo de CPU, memória por espaço de endereçamento, isolamento, escolha do
    `AC_ref`)~~ — **RESOLVIDO** em 2026-09-20 (gate T037; ver 1.4, com o critério de reabertura
    das regras 2 e 5).
15. ~~**[PENDENTE]** Fração de incorretas que é WA de verdade, e se a meta de 200 problemas com
    exatamente 100 WAs fecha~~ — **RESOLVIDO** em 2026-09-21 pelo piloto (ver 1.7): 85,5% das
    candidatas viraram WA no `train` e não há déficit projetado.
16. ~~**[PENDENTE]** Volume de triagens manuais de AC na execução completa~~ — **RESOLVIDO**
    em 2026-09-21 (D17): a triagem manual é adiada e só se faz se a meta de 200 não for atingida
    com os demais problemas do pool (ver 1.4).

---

## 7. Divergências em Relação ao Texto do TCC

Registro exigido pela Constitution (princípio 1), para atualizar o texto final do TCC e
evitar inconsistência entre o que a banca aprovou e o que foi construído. Origem:
`specs/001-dataset-extraction/spec.md`, decisões de 2026-09-18 e 2026-09-19.

| # | Divergência | Onde |
|---|---|---|
| 1 | Flag `-Wl,--stack=268435456` removida (linker Windows/MinGW); pilha de 256 MiB aplicada em tempo de execução no sandbox (`ulimit -s 262144`) | 1.4 |
| 2 | A solução de referência (AC) também passa pelo motor de execução na montagem do dataset, e um registro de validação (`validacao.json`) é persistido por problema | 1.4, 1.5 |
| 3 | Os três splits são combinados; `is_description_translated == false` é critério de elegibilidade; `generated_tests` são persistidos em `testes.json` | 1.1, 1.2 |
| 4 | Problemas elegíveis com menos de 100 WAs validados são excluídos da amostra | 1.4 |
| 5 | Sem cota por macrocategoria; alerta no relatório se alguma tiver menos de 30 problemas | 1.4 |
| 6 | `extraction_timestamp` fica fora da comparação de igualdade entre execuções | 1.5 |
| 7 | Falha de AC no motor (escolha ou auditoria) interrompe o problema e o envia à triagem manual, sem tolerância percentual nem substituição automática do AC | 1.4, 1.5 |
| 8 | Novo critério de elegibilidade: sem E/S por arquivo (`input_file`/`output_file` vazios); 9 problemas removidos | 1.2 |
| 9 | Números do dataset corrigidos por medição em 2026-09-19: 13.610 exemplos (`train` 13.328, `valid` 117, `test` 165), no lugar de 4.044 (`train` 3.760); 118 problemas Codeforces sem rating | 1.1, 1.2 |
| 10 | Regras operacionais do motor (veredito pelo primeiro teste que falha, comparação sem espaços finais, estabilidade, tempo de CPU, memória por espaço de endereçamento, isolamento, escolha do `AC_ref`) confirmadas pelos autores em 2026-09-20, com critério objetivo de reabertura das regras de comparação e de tempo | 1.4 |
| 11 | Relatório final da extração versionado junto do manifesto; `schema_version` em todo JSON; `status` do problema em `validacao.json` | 1.5, 1.6 |
| 12 | Dataset acessado em revisão fixada (`802411c3…`), licença CC-BY-4.0; GCC fixado em 13.2.0 por digest | 1.1, 1.4 |
| 13 | Dados medidos no planejamento: disponibilidade de submissões em C++ (mediana 200 no `train`, 101 em `valid`/`test`), volume de testes, verificações de ambiente | 1.7 |
| 14 | Diretório de trabalho de dados `data/work/` com permissão `0700`, para o código de terceiros não acessar os dados de trabalho (verificado que o `./data` montado herda `0755`) | 1.4, 1.7 |

---

## 8. Histórico de atualizações deste documento

Registro datado de cada atualização, para conduzir a revisão do texto escrito do TCC
(Constitution, princípio XI). Origem: `specs/001-dataset-extraction/` (spec, plano, pesquisa).

| Data | O que mudou | Seções |
|---|---|---|
| 2026-09-18 | Decisões D1–D5 da spec: splits combinados, tradução como critério, `generated_tests`, flag `-Wl,--stack` removida (pilha em tempo de execução), problemas com menos de 100 WAs excluídos, sem cota por macrocategoria com alerta < 30 | 1.1, 1.2, 1.4, 6, 7 |
| 2026-09-18 | Motor de execução único, AC também validado no motor (`validacao.json`), política de falha de AC com triagem manual (D7, D8) | 1.4, 1.5, 4, 7 |
| 2026-09-19 | Decisões da revisão do plano: critério "sem E/S por arquivo", seed 42, manifesto em `manifests/`, motor em pacote próprio | 1.2, 1.4, 1.6, 6, 7 |
| 2026-09-19 | Números do dataset corrigidos por medição (13.610 exemplos; `train` 13.328; 8.101 Codeforces; 118 sem rating; 1.288 elegíveis, 1.279 com E/S por arquivo removida) e funil de elegibilidade | 1.1, 1.2, 7 |
| 2026-09-19 | Localização do motor em pacote próprio (`src/sandbox/`), decisão confirmada na revisão do plano e que faltava aqui | 1.4 |
| 2026-09-19 | Auditoria retroativa (Princípio XI): dados medidos de disponibilidade de submissões, volume de testes e verificações de ambiente (1.7); regras operacionais do motor como PROPOSTA; revisão fixada e licença; `schema_version`, `status` e relatório versionado; evidência e mecanismo do limite de pilha; rótulo de `AC_ref` corrigido; este histórico | 1.1, 1.4–1.7, 4, 6–8 |
| 2026-09-22 | **Reparo de WA na auditoria (D18)**: 13 WA em 12 dos 200 problemas divergiram na auditoria (comportamento indefinido ou tempo no limiar); investigada e descartada a correção por ASLR (bloqueada pelo seccomp padrão do Docker); decisão: substituição automática pelo próximo candidato não tentado, com confirmação mais forte; `dataset.validation.repair` implementado e testado | 1.4, 1.7, 8 |
| 2026-09-22 | **Convergência aceita (D18)**: 3 rodadas de `audit` (16, 11 e 10 WA reparadas; 20 dos 200 problemas tocados ao todo); decisão dos autores de aceitar o estado atual e fazer só mais uma auditoria de fechamento antes do `package`, sem perseguir zero divergências (ruído estatístico esperado ao testar ~26.400 WA com um crivo de 2 execuções) | 1.4, 1.7, 8 |
| 2026-09-22 | **Bug de confirmação corrigido (D18)**: a segunda execução real do `audit`, sobre o dataset já reparado, achou 8 das 13 WA reparadas (62%) divergindo de novo; a causa era um bug na confirmação (só duas de quatro chamadas eram de fato comparadas, e o valor gravado vinha de uma chamada nunca conferida); corrigido para exigir que todas as passadas concordem com a primeira, e o número de passadas subiu de 2 para 3 (6 execuções); teste de regressão específico | 1.4, 8 |
| 2026-09-22 | **Retomada verificada de propósito e limite da garantia de determinismo (T080, D19)**: `validate` interrompido com `SIGTERM` no meio de um problema sintético (motor real) e retomado confirma SC-006 (0 pastas duplicadas, 0 arquivos truncados) e SC-007/FR-025 para tudo que decide a seleção; achado que `max_cpu_time_s` de `validacao.json`, além de `extraction_timestamp`, também varia entre execuções (ruído real de medição, não de seleção); `max_memory_bytes` permanece estável; não afeta o hash do zip ao reempacotar o mesmo conjunto (SC-008) | 1.4, 1.5, 8 |
| 2026-09-21 | **Validação completa (T072, parte `validate`)**: 200 de 200 em 5 h 06 min (4 processos), 264 problemas processados (75,8% completos), 21 descartados, 43 em triagem adiada (16,3%; causas em 1.7); amostra 98/61/41 por macrocategoria e 198 `train` + 2 `test`; alerta de menos de 30 não disparou; 84,6% das candidatas viraram WA; `audit` ainda pendente | 1.2, 1.4, 1.7 |
| 2026-09-21 | **Triagem manual de AC adiada (D17)**: os problemas com o `AC_ref` reprovado seguem interrompidos e registrados, mas só serão inspecionados se a meta de 200 não for atingida com os demais; `validate` sai com 0 sempre que a meta é atingida; explicação de como os 200 problemas são escolhidos (pool embaralhado com a seed 42, os 200 primeiros que completam); item 16 resolvido | 1.4, 6 |
| 2026-09-21 | **Piloto de validação (T071)**: 14 problemas do `train` (10 completos, 3 em triagem, 1 descartado); 85,5% das candidatas viraram WA (risco de poucas WA não se materializou), mediana de 102 s por problema completo, sem déficit projetado; critério de reabertura de D13 não atingido (regra 2: 7,1%; regra 5: 0%); descoberta de que `generated_tests` do dataset podem ter entradas fora das restrições; item 15 resolvido e item 16 (volume de triagens) aberto | 1.4, 1.7, 6 |
| 2026-09-21 | **Motor implementado (T049)**: ambiente reconfirmado com o motor (linker, pilha, memória, isolamento); três diferenças encontradas e corrigidas (áreas graváveis por todos, zumbis, pico de memória inflado), com lançador nativo, `init: true` e `tmpfs` privados (D16); custos medidos (compilação de 2,5 s com `bits/stdc++.h`, sobrecarga de 2,5 ms por teste) | 1.4, 1.7 |
| 2026-09-20 | **Gate T037**: os autores confirmaram as 7 regras operacionais do motor sem alteração (de proposta a decididas) e definiram o critério objetivo de reabertura das regras de comparação de saída e de tempo no piloto (mais de 10% dos ACs testados reprovados por formatação ou por TLE), com o diagnóstico `format_only` e as contagens `ac_tested`/`triage_by_cause` no relatório (T037) | 1.4, 6, 7 |
| 2026-09-20 | **Extração real (T035)**: funil reconfirmado (13.610; 8.101; 2.399; 2.155; 1.751; 1.288; 1.279 idênticos aos do planejamento) e completado com as etapas de soluções em C++ (1.250) e de pelo menos 100 incorretas (1.234); pool final 407/278/549 (`train` 1.206, `valid` 9, `test` 19), em vez de 1.279 (417/285/577); dados de disponibilidade de WAs brutas, volume de testes, limites, tempo (~23 min) e disco (104 MB); estimativa de distribuição por macrocategoria refeita | 1.1, 1.2, 1.4, 1.7 |
| 2026-09-20 | Fluxo de circulação do dataset entre os autores (geração única, distribuição por zip e manifesto, recebimento sem extração; `data/work/` local e sem limpeza automática) | 1.6 |
| 2026-09-20 | Estimativa analítica da distribuição por macrocategoria sob a seleção sem cota (D5) e limiar de taxa de validação que dispararia o alerta de 30; passo `mkdir -p data` antes do primeiro `docker compose run` (o Docker cria o diretório como root se ele não existir) | 1.4, 1.7 |
| 2026-09-19 | Diretório de trabalho `data/work/` com permissão `0700` para o código de terceiros não o acessar (D15); a premissa "não acessa `data/`" passa a valer para `data/work/` | 1.4, 1.7, 7 |
