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

Avaliar empiricamente a eficácia de modelos de linguagem (três LLMs comerciais —
GPT-5.4-mini, Gemini 3.8 Flash e Claude Haiku 5.5 — e um SLM local — Qwen2.5-Coder-14B,
`qwen2.5-coder:14b`, via Ollama; o texto do TCC cita o 7B, trocado em 2026-10-06, seção 7, item 30,
o Gemini 3.5 Flash, descontinuado pelo Google e trocado pelo 3.8 Flash em 2026-10-15, seção 7, item
41, e só 2 LLMs comerciais — o Claude Haiku 5.5 foi acrescentado depois, seção 3, "Terceiro modelo
comercial: Claude") na geração automática de casos de teste unitários em C++, sob três cenários de
contexto:

- **Caixa-Preta**: apenas o enunciado do problema (requisito).
- **Caixa-Branca**: apenas o código-fonte da solução de referência (AC).
- **Híbrida**: requisito + código simultaneamente.

Perguntas de pesquisa centrais: qual abordagem detecta melhor falhas lógicas reais
(TDF), qual é mais sensível a defeitos sintéticos (MS via mutação), qual gera mais
falsos positivos/alucinações (TFP), e como a combinação de insumos influencia
positiva ou negativamente a cobertura (IIC — ver seção 5).

**Perguntas de pesquisa [DECIDIDO, 2026-11-04 — Milena e Rafael; formalizadas na proposta de
métricas]**: Q1 — qual cenário detecta melhor falhas lógicas reais (TDF); Q2 — qual é mais
sensível a defeitos sintéticos (MS); Q3 — qual produz mais falsos positivos (TFP); Q4 — juntar
requisito e código ajuda ou atrapalha (IIC); **Q5 — como o SLM e os três LLMs comerciais se
comparam em eficácia, confiabilidade e custo-benefício** (a pergunta implícita desde que o
desenho passou a 4 modelos; respondida pelas métricas da seção 5 por modelo, por TDF\*/MS\* e
Δ_oráculo, pelo custo por detecção e pelos testes estatísticos).

### 0.1 Verificação de consistência entre artefatos **[DECIDIDO E EXECUTADO, 2026-09-25 — `docs/verificacao-consistencia.md`, `specs/002-mutant-generation/research.md` R22]**

Cada módulo confere o seu artefato contra o manifesto (`dataset verify`, `mutation verify`); o
conjunto é conferido por um comando do pacote `cli`, `python -m cli check` (`src/cli/`), que percorre as pastas
**descompactadas** e confere, por nomes e contagens (não pelo conteúdo dos códigos): o dataset tem
o número de problemas do manifesto (200) e cada problema tem `AC_ref.cpp`, `enunciado.md`,
`metadata.json`, `testes.json`, `validacao.json` e exatamente `WA_1` a `WA_100` (105 arquivos, nada
a mais); cada problema de mutantes tem exatamente `Mutant_1` a `Mutant_100`; dataset e mutantes são
**1:1 nos dois sentidos** (nenhum problema sem mutantes, nenhuma pasta de mutantes sem problema); e os
nomes no disco são os que os manifestos listam. `--deep` também recalcula os SHA-256 de todos os
arquivos e dos zips. Serve para ver a integridade num resumo com contagens e é o **portão** das
etapas que consomem os dados: `evaluation run` (`src/evaluation/gate.py`, junto da auto-checagem do
motor) e `metrics compute` (`src/metrics/gate.py`) o chamam antes de ler qualquer coisa. Cada módulo
que produz uma pasta por problema acrescentou a sua camada: hoje `dataset`, `mutants`, `slm_suites`,
`gpt_suites`, `gemini_suites`, `claude_suites` e as cinco avaliações (`evaluation_slm`, `_gpt`,
`_gemini`, `_claude` e `_slm_attempt1`); o `cli` tem só o `check`, **sem orquestrador** (seção 8,
2026-11-14). Motivação
medida: `dataset verify` sem `--extracted` só confere o zip, então editar ou apagar um arquivo em
`data/dataset/` continuava dando `OK`. Execução real sobre os dados reais (2026-09-25): `OK` em 0,6 s
(dataset 200 pastas e 21.000 arquivos com nomes iguais aos do manifesto; 200 problemas de mutantes
com 100 cada; relação 200/200, 0 sobrando; `--deep` também `OK`), com um aviso: o manifesto de mutantes
ainda não existia. **Depois do empacotamento (2026-09-25, `--deep`)**: `OK`, 0 falhas e 0 avisos, com o
hash de 21.000 arquivos do dataset, o de 20.000 mutantes e os dos dois zips conferindo com os
manifestos. Além disso, `data/dataset/` só existe depois de um `unzip` manual (nenhum comando a
cria), o que passou a constar do passo final do fluxo "gerar do zero" do módulo `dataset`.

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

**[Esclarecido, 2026-09-25]** O comando de verificação sem `--extracted` confere **só o zip** contra o
manifesto; a pasta `data/dataset/` (a que os módulos seguintes leem) só é conferida com
`--extracted data/dataset`, e essa pasta **só existe depois de um `unzip` manual** do zip — nenhum
comando do pipeline a cria, nem para quem gerou o dataset (o fluxo "gerar do zero" termina, por
isso, com o `unzip`). O conjunto (dataset × mutantes, completo e 1:1) é conferido pelo comando da
raiz descrito na seção 0.1.

**[IMPLEMENTADO E TESTADO, 2026-09-22 — T082 a T092]** `package` (constrói o zip e o manifesto,
recusa empacotar com déficit a menos que `--allow-partial`) e `verify`/`scripts/verify_dataset.py`
(recompara os hashes; funciona só com o zip, logo após um clone, ou também com `--extracted DIR`)
estão implementados exatamente como decidido acima e cobertos por 47 testes automatizados
(zip determinístico, manifesto que bate após reempacotar, `changed`/`missing`/`extra` para byte
alterado/arquivo removido/arquivo extra, regra do `.gitignore`). **Nenhuma divergência do desenho
já decidido foi encontrada na implementação.**

**[EXECUTADO SOBRE O DATASET REAL, 2026-09-22 — T093/T094, revisão `9b87d7e`]** Depois de uma
quarta rodada de `audit` de fechamento (sem nenhum reparo novo — as três rodadas anteriores, D18,
já tinham convergido), `package` gerou `data/dataset.zip` real com os 200 problemas completos:
**12.891.474 bytes (≈ 12,3 MiB), 21.000 arquivos** (200 problemas × 105 arquivos cada:
`enunciado.md`, `AC_ref.cpp`, `WA_1.cpp` a `WA_100.cpp`, `testes.json`, `metadata.json` e
`validacao.json`), hash SHA-256
`bd5398a85800a3c772d8c8c89904562a1db5fca6d4a556d440e78b3bc2af0c32` (em
`manifests/dataset.manifest.json`). `verify` confirmou `OK` sobre o zip; o cenário completo de
pós-clonagem (quickstart Nível 6) também foi executado de propósito: `unzip data/dataset.zip -d
data/` e `python -m zipfile -e data/dataset.zip` produzem árvores idênticas (`diff -rq` vazio);
`verify --extracted data/dataset` deu `OK` sobre a árvore íntegra e, testado de propósito,
apontou corretamente um byte alterado (`changed`), um arquivo removido (`missing`) e um arquivo
extra deixado por uma descompactação anterior sem `rm` prévio (`extra`) — os três casos exigidos
pela SC-009.

**[DECIDIDO no plano]** O relatório final da extração (funil, motivos de exclusão,
distribuição por macrocategoria, alertas, problemas pendentes de triagem) também é versionado,
em `manifests/extraction_report.json`, para que os números citados no trabalho escrito
acompanhem a versão exata do dataset. O tamanho do zip foi **estimado em ~10 MB** (ver 1.7) e
**medido de verdade em 12,3 MiB** (acima), 29% maior que a estimativa mas nem de longe uma ordem
de grandeza — bem abaixo do limite de 100 MB por arquivo do GitHub; o comando de empacotamento
avisa a partir de 95 MB (não disparou). O hash do `.zip` é reproduzível dentro da imagem fixada
(a compressão depende da versão da biblioteca zlib); a identidade do conteúdo entre ambientes é
garantida pelos hashes por arquivo do manifesto.

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

### 1.6.1 Revisão 2 do dataset: enunciados corrigidos **[DECIDIDO E MEDIDO, 2026-10-18 — `specs/007-dataset-revision/`; revisão 2 gerada]**

Com a conferência contra o original do Codeforces (seção 3, feature 006: 152 expoentes perdidos em 79 problemas e 701 índices em 74), os autores decidiram refazer o dataset numa revisão 2. D1: só os `enunciado.md` mudam — os 102 corrigidos automaticamente (só `^{...}` e `_{...}` inseridos, aprovados nas três conferências) e os 15 da lista de revisão, avaliados à mão pelos autores com o original ao lado (resultado medido mais abaixo: 2 corrigidos e 13 mantidos); os 83 fiéis e todos os outros arquivos ficam iguais. D2: o modelo local refaz só as combinações afetadas (caixa-preta e híbrido dos problemas cujo enunciado mudou), reaproveitando as demais com a proveniência registrada. D3: as execuções completas dos modelos comerciais usam a revisão 2 (na data da decisão nenhuma tinha começado; GPT, Gemini e Claude rodaram em 2026-10-20 sobre ela, seção 3). A revisão 2 exigiu a emenda 1.8.0 da constitution (Princípio II), aprovada e aplicada em 2026-10-18. **[DECIDIDO, 2026-10-18 — clarify]** F1: cada um dos 15 tem um arquivo de decisão (texto corrigido ou "manter", motivo, quem, data), conferido na geração; F2: uma execução nova do modelo local só com as combinações afetadas, a da revisão 1 intocada, e o pacote final marca por combinação a execução e a revisão de onde veio; F3: a revisão 1 fica guardada, renomeada, como arquivo de auditoria; F4: os relatórios dos pilotos ficam como estão (revisão 1); para o dos mutantes a decisão inicial era regenerá-lo para a revisão 2, sem regerar os mutantes — **substituída em 2026-10-18 por decisão dos autores na execução** (emenda abaixo: nem os mutantes nem o relatório foram refeitos). **[PLANEJADO e IMPLEMENTADO, 2026-10-18 — `specs/007-dataset-revision/plan.md`]**: comando `python -m dataset revise` (refaz em memória os corrigidos a partir das entradas versionadas, confere as 15 decisões em `manifests/statement_decisions/<id>.json`, guarda a revisão 1 como `data/dataset.rev1.zip` e `manifests/dataset.rev1.manifest.json` sem mudar nenhum byte, empacota a revisão 2 com manifesto de `schema_version` 2 e `manifests/dataset_revision.json`, e confere que só os `enunciado.md` alterados mudaram); SLM: a execução da revisão 1 vai para `data/suites/slm-rev1`, uma execução nova roda só as combinações afetadas e `package --merge-from` junta as duas num pacote com `provenance.json` por combinação. Emenda 1.8.0 da constitution (revisões numeradas do dataset só quando uma conferência automática contra a fonte demonstrar perda) aprovada por Milena e aplicada em 2026-10-18. Achado: o `manifests/mutation_report.json` aponta para um manifesto de dataset (`6b3628c3…`) diferente do `a092d987…` da revisão 1; esse ponto ficou resolvido pela decisão de não regenerar o relatório (emenda abaixo), e a origem da diferença está explicada ali. **[MEDIDO, 2026-10-18 — revisão 2 gerada, `29d9245+dirty`]** Avaliação dos 15 da lista de revisão, feita pelo agente a pedido de Milena, conferida contra o original guardado: **2 corrigidos** e **13 mantidos**. `670_D2`: o `enunciado.md` da revisão 1 tinha como legenda só "The term of this problem is the same as the previous one, the only exception — increased restrictions.", sem descrever o problema (perda de conteúdo, não só de notação; afeta os cenários caixa-preta e híbrido); recolocada a legenda do original e os expoentes e índices perdidos, na notação do próprio original, sem chaves (`10^9`, `a_i`, `b_i`: o original desse problema é LaTeX, e a primeira versão da decisão, com `10^{9}`/`a_{i}`, deixava 26 diferenças de chave no `check-statements`; a revisão gerada com ela foi desfeita, com a revisão 1 restaurada e conferida pelo hash, antes de qualquer uso, e gerada de novo); a seção "Note" do original, também ausente, não entrou porque a comparação não a apontou como diferença. `190_A`: expoente perdido (`10^{5}`). Os 13 mantidos têm só a mesma fórmula em outra notação (`\frac{a}{b}` como `(a)/(b)`, `\limits`, `\log`/`\max` sem o comando, espaços em volta de `<`/`>`, uma barra invertida a mais no LaTeX de matrizes e conjuntos). Conferência dos 2 corrigidos por script: todos os parágrafos (10/10 em cada) aparecem iguais no original renderizado, sem expoente ou índice perdido restante. Ajuste da conferência das decisões: diferenças a até 16 caracteres uma da outra contam como um só trecho (a legenda reescrita do `670_D2` aparecia como 27 diferenças pequenas; `research.md` R3). `revise`: **104 enunciados alterados (102 automáticos, 2 manuais), 13 mantidos, 83 fiéis**; dos 21.000 arquivos, só 104 mudaram, todos `enunciado.md`; zip da revisão 2 `5a9b66b8…` (12.892.995 bytes; revisão 1: 12.891.474), manifesto `70d93346…`, registro `manifests/dataset_revision.json` `cdcf5426…`; revisão 1 guardada (`data/dataset.rev1.zip` `bd5398a8…`, manifesto `a092d987…`, ambos conferidos pelo `verify`); `cli check` sem falha. `check-statements --problem` nos 104 alterados (sem regravar o relatório versionado, `763771a6…`, que o manifesto cita): 102 fiéis; restam só a lista da nota do `190_A` (diferença de marcador já existente no relatório) e a seção "Note" ausente do `670_D2`. `generate --model gpt|gemini --dry-run` com a revisão 2: 600 combinações cada, nada chamado; o hash da revisão 1 (`a092d987…`) não deve ser usado nas execuções novas. O modelo local tem **208 combinações afetadas** (caixa-preta e híbrido de 104 problemas). Mutantes intactos por decisão de Milena (2026-10-18): `data/mutants.zip` não mudou e `mutation verify` dá `OK`; o `mutation report` não foi rodado. Os mutantes dependem só do `AC_ref.cpp` de cada problema (2.5), e nenhum `AC_ref.cpp` mudou na revisão 2 (só 104 `enunciado.md`); na época só o modelo local tinha rodado e foi o que se refez, e os modelos comerciais já nasceram sobre a revisão 2. O `manifests/mutation_report.json` ficou como estava e guarda `dataset_manifest_sha256` = `6b3628c3…`. Conferido contra o Git em 2026-11-14: esse hash é o do manifesto do dataset da revisão 1 como foi gerado em 2026-09-22 (commit `9b87d7e`, anterior à geração dos mutantes, 2026-09-25); o `manifests/dataset.rev1.manifest.json` (`a092d987…`) tem **o mesmo conteúdo, só com fins de linha CRLF** (removendo os `\r`, o hash volta a ser `6b3628c3…`), e o zip da revisão 1 (`bd5398a8…`) é o mesmo nos dois. Ou seja, o relatório dos mutantes descreve o dataset da revisão 1 sem divergência de conteúdo, e continua válido para a revisão 2 pelo motivo acima; o hash do manifesto da revisão 2 (`70d93346…`) não aparece nele de propósito. **[MEDIDO, 2026-10-22 — execução nova do SLM e pacote juntado]** A execução nova (`data/suites/slm`) refez as **208 combinações afetadas** (caixa-preta e híbrido dos 104 enunciados alterados), de 2026-10-19 a 2026-10-22, em GPUs T4 (as 870 chamadas têm o rótulo de hardware GPU T4, 16GB RAM), parte pelo laço com o Ollama remoto e parte rodando o próprio `generate` do projeto fora do Docker, na máquina com GPU, com o Ollama local (válvula de escape, fora do repositório; o `execute` continuou no `sandbox`; a configuração gravada no `run.json` — Ollama 0.35.0, modelo `9ec8897f…`, opções — é conferida a cada `generate`). Resultado nas 208: **165 `accepted` e 43 `accepted_fallback`** (na revisão 1, as mesmas 208 tinham 166, 41 e 1 `accepted_predicted`; 195 mantiveram o mesmo status); 870 tentativas (705 falhas), 1.225.366 tokens de prompt e 798.283 de saída, 66.913 s de geração. **Pacote juntado** (`package --merge-from data/suites/slm-rev1`): 600 combinações, **504 `accepted`, 95 `accepted_fallback`, 1 `accepted_predicted`, 0 `discarded_manual`** (antes, na revisão 1: 505, 93, 2, 0); 208 da execução nova e 392 da revisão 1, com a origem de cada uma em `provenance.json`; `data/slm_suites.zip` com 8.961.292 bytes (SHA-256 `1303e652…`), conferido por `verify` e `cli check --deep` (dataset, mutantes e as suítes dos 4 modelos: `Resultado: OK`, 0 falhas, 0 avisos). O `manifests/slm_generation_report.json` passa a ser o da execução nova (as 392 combinações reaproveitadas aparecem como pendentes nele; os números delas estão no relatório da revisão 1, dentro do pacote).

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

> **Estado (2026-09-25)**: módulo **implementado e executado sobre os 200 problemas**; o pacote
> versionado (`data/mutants.zip`) e o relatório (`manifests/mutation_report.json`) existem. Os
> resultados medidos estão em 2.7, 2.8, 2.9 e 2.11; as decisões, em 2.1 a 2.6 e 2.10.

> **Os mutantes não foram regenerados na revisão 2 do dataset (decisão dos autores, 2026-10-18)**:
> os mutantes dependem só do `AC_ref.cpp` (2.5) e a revisão 2 (1.6.1) mudou apenas 104
> `enunciado.md`, nenhum `AC_ref.cpp`. Por isso `data/mutants.zip` e `manifests/mutants.manifest.json`
> são os da execução de 2026-09-25 e valem para as duas revisões; o `mutation verify` dá `OK` e o
> `mutation report` não foi rodado de novo. O `manifests/mutation_report.json` guarda
> `dataset_manifest_sha256` = `6b3628c3…`, o hash do manifesto do dataset da revisão 1 como gerado em
> 2026-09-22 (o `manifests/dataset.rev1.manifest.json`, `a092d987…`, tem o mesmo conteúdo com fins de
> linha CRLF; detalhe em 1.6.1).

> **Revisão de 2026-09-23**: esta seção foi reescrita após uma rodada dedicada de pesquisa e
> discussão técnica (o texto anterior, com um conjunto pequeno de operadores por pares e
> mutação de ordem superior sem regra definida, era, por admissão dos próprios autores, a parte
> menos madura da metodologia). As decisões abaixo (D1–D6) estão detalhadas, com a proveniência
> completa, em `specs/002-mutant-generation/spec.md`, seção "Divergências e Decisões sobre a
> Metodologia".

**Objetivo**: gerar 100 versões defeituosas (mutantes) por problema, a partir do
`AC_ref.cpp`, para medir sensibilidade das suítes a defeitos sintéticos sutis.

### 2.1 Estratégia técnica: AST via `tree-sitter`, não regex **[DECIDIDO, 2026-09-23 — D1]**

Os sítios de mutação são identificados por análise sintática real (AST) do código-fonte,
usando `tree-sitter` + `tree-sitter-cpp` — um parser tolerante a erro, que não exige resolver a
árvore de includes (`bits/stdc++.h`) nem informação de tipos completa. Motivo: código C++ de
competição real tem armadilhas concretas para um mutador puramente textual — fechamento de
template aninhado (`vector<vector<int>>`, onde `>>` não é *right shift*), operadores dentro de
literais de string/char (`"a<b"`), e comentários com trechos de código morto. Um parser AST
estruturalmente não muta o conteúdo de um literal nem de um comentário, porque só enxerga
operadores em posição de expressão de código.

**[VERIFICADO, 2026-09-23 — `/speckit.plan`, R1]** Confirmado empiricamente com `tree-sitter`
0.26.0 + `tree-sitter-cpp` 0.23.4: sobre `175_B/AC_ref.cpp` (um `AC_ref.cpp` real do dataset, que
contém `vector<pair<int, string>> mb;`), a travessia da AST encontra 20 sítios de operador
(`binary_expression`), incluindo `cin >> n`, mas **nenhum** para o `>>` de fechamento do
template — exatamente a disambiguação esperada. Um trecho sintético com os dois usos de `>>` no
mesmo arquivo (um de tipo, um de operador) confirma a mesma distinção lado a lado, e literais de
string/comentário com `<`/`>>` dentro nunca aparecem como filhos de um nó de operador. Detalhes
em `specs/002-mutant-generation/research.md`, R1–R3.

Alternativas avaliadas e descartadas: `libclang` (parsing semântico real, mas exige resolver
headers de verdade sob o front-end do Clang, com risco de divergência das extensões do GCC 13.2
já fixado para o motor de execução); substituição textual cuidadosa ao estilo `UniversalMutator`
(regras por linguagem que evitam as armadilhas mais óbvias, mas ainda arriscam mutar uma *string*
em vez de lógica); a ferramenta `Mull` (mutação baseada em LLVM/Clang — descartada por exigir uma
segunda cadeia de compiladores ao lado do GCC 13.2 já fixado, e por ter motor de injeção e
execução de mutantes próprio, o que conflita com a decisão de motor de execução único da seção
1.4). **Decisão**: um mutador leve próprio sobre `tree-sitter`, que só gera texto mutado e
entrega ao motor do módulo `sandbox` já existente para compilar, executar e julgar.

### 2.2 Conjunto de operadores: o conjunto de Offutt et al. **[DECIDIDO, 2026-09-23 — D2]**

O conjunto original (substituição em pares fixos) foi medido, sobre os 200 `AC_ref.cpp` reais já
extraídos, como insuficiente: mediana de **23 ocorrências** desses operadores por arquivo, com
**199 dos 200 problemas (99,5%) abaixo de 100** — não dá para gerar 100 mutantes de primeira
ordem para a quase totalidade da amostra só com esse conjunto.

**Decisão**: adotar por completo o conjunto que Offutt, Lee, Rothermel, Untch e Zapf (1996,
*"An Experimental Determination of Sufficient Mutant Operators"*, ACM TOSEM 5(2)) mediram
experimentalmente como suficiente — 99,5% do escore de mutação do conjunto completo de
operadores da literatura, com 4x menos mutantes:

| Operador | O que faz |
|---|---|
| **ROR** | substitui cada operador relacional por **todos** os demais legais (`<` gera `<=`, `>`, `>=`, `==`, `!=` — 5 mutantes, não 1) |
| **AOR** | o mesmo para operadores aritméticos, substituição completa |
| **LCR** | o mesmo para conectores lógicos (`&&`, `\|\|`) |
| **ABS** | força uma subexpressão aritmética a assumir zero, um valor positivo e um valor negativo |
| **UOI** | insere um operador unário (`-`, `!`, `++`, `--`) à frente de uma expressão existente |

Uma nova estimativa sobre os mesmos 200 arquivos, simulando esse conjunto (multiplicando por ~4
os sítios de operador já existentes para ROR/AOR/LCR, e usando a contagem de ocorrências de
identificador como proxy conservador dos sítios de ABS/UOI, já que esses dois atuam sobre
qualquer subexpressão numérica, não só sobre operadores existentes), deu **mediana ≈146** sítios
por arquivo, com apenas **44 dos 200 problemas (22%) ainda abaixo de 100**, antes de qualquer
combinação de ordem superior. É uma estimativa grosseira (a fração real que sobrevive às 3
validações da seção 2.3 é menor que a contagem bruta de sítios), mas com margem suficiente para
confiar que o objetivo original — só `AC_ref` — é alcançável para a grande maioria dos problemas.

**[IMPLEMENTADO, 2026-09-24 — primeira história de `002-mutant-generation`]** A implementação
fixou os pontos que o texto acima deixava abertos (detalhes e motivos em
`specs/002-mutant-generation/research.md`, R8 e R9):

- Os deslocamentos `<<` e `>>` contam como operadores aritméticos (AOR) e só são trocados entre si,
  nunca por `+ - * / %` (não tipa para `cin >>`/`cout <<`).
- ABS e UOI atuam sobre os **operandos** de expressões relacionais e aritméticas (ABS e UOI) e
  lógicas (só UOI); o unário inserido depende do operador pai (relacional: `- ! ++ --`; aritmético:
  `- ++ --`, nunca `!`; lógico: só `!`). Um `-x`/`!x`/`++x`/`x--` que já existe no código é um sítio
  UOI de troca (`-`↔`!`, `++`↔`--`). Operando composto ganha parênteses (`!(a * b) < c`).
- Operadores bit a bit, vírgula, `~` e `+` unário não são sítios; condições de `#if`/`#elif` também
  não.

**Medição sobre os 200 `AC_ref.cpp` reais, ANTES do filtro de fluxo descrito em 2.7 (2026-09-24, dataset `manifests/dataset.manifest.json`,
gerador de candidatos de primeira ordem, antes de qualquer validação)**: mediana de **274**
candidatos por problema (mínimo 35, em `630_J`; máximo 2.104); **8 dos 200** têm menos de 100
candidatos brutos e 64 têm menos de 200. É maior que a estimativa grosseira de 2.2 (mediana ≈146,
44 abaixo de 100), porque a estimativa usava a contagem de identificadores como proxy dos
operandos. A contagem que importa para a cota, porém, é a de candidatos **aceitos** pela validação
(2.3): ver 2.8.

### 2.3 Validação antes de aceitar um mutante

1. **Unicidade léxica**: texto do mutante não pode ser idêntico a nenhum já
   armazenado para o mesmo problema (hash set).
2. **Compila e executa** dentro dos mesmos limites de tempo/memória do problema
   original, na mesma cascata de padrão (`gnu++20`→`gnu++17`→`gnu++14`→`gnu++11`) do motor de
   execução único (seção 1.4). Mutantes que geram TLE/MLE/RE são descartados (defeito
   estrutural, não de lógica de negócio). Um operador ABS ou UOI aplicado a um sítio de tipo
   incompatível simplesmente não compila e é descartado por este mesmo critério — não é um caso
   especial, é o custo de eficiência aceito por usar um parser puramente sintático (sem
   informação de tipos), que se paga sozinho dada a margem medida em 2.2.
3. **Não é mutante equivalente**: executa contra a suíte de testes oficial do problema (a mesma
   suíte usada para validar AC/WA, seção 1.1); se passar em 100% (comporta-se como AC), é
   equivalente → descartado.
4. **Estabilidade** **[DECIDIDO, 2026-09-23 — D5, revisado em `/speckit.clarify`]**: um mutante
   candidato só é aceito definitivamente depois de **6 execuções concordantes** (3 checagens
   independentes de 2 execuções cada, mesmo veredito e mesmo teste decisivo em todas) — a mesma
   força já usada no **reparo** de WA (seção 1.4), depois que a regra original de 2 execuções se
   mostrou insuficiente na prática (8 das 13 WA reparadas com 2 execuções voltaram a divergir).
   Necessário porque a validação de um mutante roda no mesmo motor cuja instabilidade de margem
   já foi medida na auditoria do módulo de dataset (D18/D19, seção 1.4). Um candidato cujas
   execuções não concordam é descartado como instável, não aceito nem rejeitado por acaso.

   **[DECIDIDO NA IMPLEMENTAÇÃO, 2026-09-24 — research.md, R10]** As 6 execuções são a primeira
   execução mais 5 reexecuções do **mesmo binário**, compilado uma vez (não 3 checagens
   independentes que recompilam, como no reparo de WA): recompilar triplicaria o custo dominante
   (a compilação, ~1,8 s, ver 2.8) e a instabilidade que se quer pegar é de tempo de execução, não
   de compilação. Se a auditoria futura mostrar mutantes instáveis que recompilar teria pegado,
   a decisão é reaberta. Um texto já avaliado no problema (aceito ou descartado antes) conta como
   duplicata e não é recompilado (R11).

Quando os mutantes de primeira ordem válidos e distintos de um problema forem **mais** de 100
(esperado com o conjunto ampliado de 2.2), retêm-se exatamente os primeiros 100 na mesma ordem
determinística de descoberta de sítios na travessia da AST — nunca por amostragem aleatória.
Como consequência, **este módulo não usa nenhuma operação aleatória em nenhuma etapa** (seleção
de sítios, truncamento de excedentes, ordem superior) e por isso não precisa de uma seed própria
(**[DECIDIDO, 2026-09-23, revisado em `/speckit.clarify`]** — corrige a decisão inicial desta
seção, que assumia incorretamente que a exigência de seed do Princípio II implicava uma operação
aleatória neste módulo).

### 2.4 Mutação de ordem superior: regra determinística, sem busca **[DECIDIDO, 2026-09-23 — D3]**

Quando os mutantes de primeira ordem válidos e distintos de um problema são menos de 100
(estimativa: cerca de 1 em cada 4 problemas, mesmo com o conjunto completo de operadores),
combinam-se mutações de primeira ordem já validadas em **pares**, em sítios distintos, na
**ordem em que esses sítios foram descobertos na travessia da AST**, até completar 100 ou
esgotar as combinações de pares possíveis; se ainda insuficiente, repete-se combinando em
**trios**, na mesma ordem determinística. Cada combinação passa pelas mesmas 4 validações da
seção 2.3 — uma combinação cujas duas mudanças se cancelam (fica equivalente ao original) é
descartada pelo mesmo critério, sem lógica adicional.

Motivo de não usar busca (programação genética, otimização multi-objetivo): é o que a
literatura de mutação de ordem superior (Jia & Harman, *"Higher Order Mutation Testing"*,
Information and Software Technology, 2009; Harman, Jia, Langdon e outros) usa para encontrar
combinações "*strongly subsuming*" (mais difíceis de matar), precisamente porque combinar
mutações ao acaso tende a produzir mutantes equivalentes ou triviais — mas essa maquinaria de
busca é incompatível com a simplicidade e o determinismo exigidos (Constitution, Princípios II e
IX) para este experimento. Assume-se conscientemente que uma fração dos mutantes de ordem
superior seja mais fácil de matar do que o ideal da literatura: o objetivo aqui é fechar uma
cota de 100 defeitos distintos e válidos para medir sensibilidade da suíte, não encontrar o
mutante mais difícil possível.

Um problema que esgota primeira e segunda (e, se necessário, terceira) ordem sem alcançar 100
mutantes válidos é **excluído do conjunto de mutantes e registrado no relatório, com um alerta
explícito** (seção 2.6) — nunca silenciosamente. Não se aceita um número menor que 100, e não se
recorre a uma base de mutação adicional (seção 2.5). **[DECIDIDO, 2026-09-23, revisado em
`/speckit.clarify`]** Diferente do tratamento de WA insuficiente na seção 1.4 (onde a exclusão
acontece durante a seleção dos 200, e o pool ainda tem candidato para substituir), aqui os 200
problemas já estão fixados e empacotados — não há substituto sem reabrir o módulo de dataset. Por
isso, a exclusão afeta só o cálculo do Escore de Mutação (MS), calculado sobre os problemas
efetivamente completos (podendo ser menos de 200 problemas nessa métrica específica); o
denominador de 200 usado por TDF e TFP nunca é afetado, e não se aciona a escolha de um
substituto no dataset.

### 2.5 Base de mutação: só `AC_ref`, sem ACs adicionais **[DECIDIDO, 2026-09-23 — D4]**

Avaliou-se usar outras soluções corretas do dataset de origem (`correct_solutions`, presentes
apenas em `data/work/staging/raw/*.json.gz` — nunca persistidas além da primeira escolhida como
`AC_ref`, ver seção 1.4) como bases de mutação adicionais para problemas com poucos sítios.
**Decisão**: não usar. A ampliação do conjunto de operadores (2.2) já fecha a cota para a grande
maioria dos problemas, e a margem da ordem superior (2.4) cobre o resto esperado. Usar ACs
adicionais exigiria reabrir o schema do pacote do módulo de dataset (novo `schema_version`,
reempacotamento), já concluído (`Status: implementado`) — evitado por não ser necessário.

### 2.6 Reprodutibilidade e empacotamento **[DECIDIDO, 2026-09-23 — D5, D6; requer Constitution 1.6.0]**

A validação de cada mutante usa o mesmo motor de execução cuja instabilidade de margem já foi
medida e documentada (D18/D19, seção 1.4: 20 dos 200 problemas do dataset precisaram de reparo
por veredito instável entre execuções independentes do mesmo binário, por comportamento
indefinido ou tempo no limiar do limite — nunca por lógica de seleção). Isso significa que
**"regenerar os mutantes localmente com a mesma seed" reduz, mas não garante, obter exatamente o
mesmo conjunto final** — o mesmo argumento que já levou a versionar o dataset (Constitution,
Princípio II, emenda 1.1.0) se aplica, sem diferença de fundo, a mutantes.
**[MEDIDO, 2026-09-24 — `specs/002-mutant-generation/research.md` R14 e R15]** A estabilidade do
próprio gerador entre execuções independentes foi medida: **0 de 900 mutantes divergentes** (R15: os 100
mutantes de `189_C` em duas rodadas independentes, arquivos e SHA-256 iguais; R14: 800 mutantes de 8 problemas
gerados com `--workers 1` e com `--workers 4`, 800 de 800 iguais, mesmo funil de descartes). É uma
amostra, não prova de que toda a execução se repete igual; por isso o pacote versionado continua
sendo a referência. Aceleração de `--workers 4` sobre `--workers 1`: 2,07× (3.520 s → 1.700 s, num
computador de 4 núcleos físicos), não 4×.

- **Sem seed própria**: o módulo não usa nenhuma operação aleatória (ver 2.3, item 4) —
  seleção de sítios, truncamento de excedentes e ordem superior seguem só a ordem determinística
  de travessia da AST.
- **Gate de consistência com o dataset**: antes de gerar qualquer mutante, o módulo verifica o
  `data/dataset` local contra `manifests/dataset.manifest.json` (reaproveitando a mesma
  checagem de `dataset verify`) e se recusa a rodar se não corresponder — garante
  mecanicamente que a entrada é sempre a mesma, tanto para quem descompactou o zip quanto para
  quem rodou a extração do zero.
- **Mutantes de desenvolvimento**: gerados durante a iteração do módulo, vivem localmente
  (`data/mutants/`, análogo a `data/work/`) e **nunca são versionados**.
- **Pacote da execução final (Constitution, Princípio II, emenda 1.6.0)**: ao concluir a
  execução completa que sustenta os números publicados no trabalho escrito, os mutantes de
  todos os problemas são compactados em `data/mutants.zip`, acompanhado de
  `manifests/mutants.manifest.json` (hash SHA-256 por arquivo), no mesmo formato já usado para o
  dataset — porque a garantia de reprodutibilidade aqui não pode depender só da seed, pelo motivo
  medido acima. Um comando de verificação, análogo ao do dataset, recalcula os hashes e os
  compara com o manifesto.
- **Fluxo de circulação (quem gera e quem só recebe)** **[DECIDIDO, 2026-09-24]**: há um único
  caminho de consumo, `data/mutants/problems/<id>/Mutant_<n>.cpp`, e o zip usa a raiz
  `mutants/problems/<id>/` para que `unzip data/mutants.zip -d data/` caia exatamente nele — o
  mesmo desenho do dataset (`dataset/problems/<id>/` → `data/dataset/problems/<id>/`). O autor que
  faz a execução final roda `generate`, `report`, `package` e `verify` e commita zip e manifestos; os
  mutantes dele já estão no caminho de consumo. O outro autor só faz `git pull`, apaga qualquer
  `data/mutants/` de desenvolvimento, descompacta e confere com `verify --extracted data/mutants`.
  Uma rodada de desenvolvimento usa o mesmo caminho, mas não é versionada nem vale como resultado.
  `generate` nunca sobrescreve uma pasta de problema existente (uma pasta vinda do pacote não tem
  `generation.json` e é pulada). Detalhes em `specs/002-mutant-generation/contracts/cli.md`.
- **Relatório** (`manifests/mutation_report.json`, versionado): funil de descarte por motivo
  (duplicata, não compila, TLE/MLE/RE, equivalente, instável), quantos mutantes de cada problema
  vieram de primeira vs. de ordem superior, distribuição por operador, a lista de alertas de
  exclusão de problema (vazia no caso esperado), a contagem de problemas (só primeira ordem,
  com ordem superior, excluídos: o número que se compara com a estimativa de 75% abaixo), o hash do
  manifesto do dataset verificado antes de ler (liga o relatório à versão exata do dataset) — dado
  para o texto do TCC, nunca os arquivos-fonte dos mutantes. **[IMPLEMENTADO,
  2026-09-24]** Comandos: `report` (a qualquer momento, sem timestamp, idempotente), `package` (só
  na execução final; recusa dataset divergente, `building/` pendente, problema danificado e
  problemas ainda não gerados; refaz o relatório do que empacotou) e `verify`. *(Revisado em
  2026-09-25, a pedido dos autores: o relatório não traz mais a revisão do código; os comandos não
  têm opção de revisão, como os do dataset. A rastreabilidade é o commit que versiona os
  artefatos.)*

Resultado esperado: para a grande maioria dos problemas (estimativa: ao menos 3 em cada 4),
exatamente 100 mutantes comportamentalmente distintos e válidos, obtidos inteiramente de
primeira ordem, a partir só do `AC_ref`. **[Medido em 2026-09-25, 2.11: 56,5% dos
problemas só de primeira ordem; nenhum excluído.]** Como mutantes equivalentes já são descartados na
validação (2.3), o termo `EM` (mutantes equivalentes) na fórmula do Escore de Mutação (seção 5)
continua sempre 0 no cálculo final do pipeline.

### 2.7 Redução dos erros de compilação **[DECIDIDO E MEDIDO, 2026-09-24 — `research.md`, R16]**

Em 1.463 candidatos de primeira ordem de 5 problemas reais, **24% não compilavam**, ~65% por E/S de
fluxo (`abs(cin)`, `cin << n`, `++` em `endl`...), o resto por `++`/`--` em algo não atribuível e
`abs` de tamanho sem sinal; cada erro custa 4 compilações (cascata de padrões). Passaram a **não ser
sítios** (só sintaxe, sem tipos): a cadeia de `<<`/`>>` que começa em `cin`/`cout`/`cerr`/`clog` (o
operando direito de `cout <<` continua), literais de string e `endl`/`flush`/`ends` como operandos,
ABS sobre `.size()`/`.length()`/`sizeof`, e `++`/`--` sobre operando não atribuível. **Efeito
medido**: erros de compilação de 29%→0% (`189_C`), 28%→1% (`630_L`), 32%→17% (`171_F`, resto
sobretudo `abs(size_type)` — regra acrescentada depois da medição — e `stringstream`); candidatos
que compilam caem 3–6% (saem sobretudo mutantes que só mexem na leitura, como `0 >> n`).
Candidatos brutos nos 200 problemas: mediana 274 → **198**, problemas abaixo de 100: 8 → **34**
(o risco de ordem superior sobe um pouco; medido por problema na execução). Substitui, para fins
de estimativa, os números da medição anterior de 2.2.

### 2.8 Medições da primeira implementação (`generate`, primeira ordem) **[MEDIDO, 2026-09-24]**

Primeira medição do custo real da validação, com o motor de execução real (`gcc` 13.2.0, serviço
`sandbox`), sobre o problema `189_C` (`AC_ref.cpp` que usa `bits/stdc++.h`, 259 candidatos de
primeira ordem brutos, 8 testes oficiais). Ferramenta: `select_mutants` com cota reduzida a 20
(revisão de código `cba4d97` mais as alterações da história, não commitadas); não é a execução
final.

| Medida | Valor |
|---|---|
| Compilação do `AC_ref.cpp` de `189_C` (3 medições) | 1,75 s; 1,79 s; 1,82 s |
| Candidatos avaliados até aceitar 20 | 83 (20 aceitos, **24%**) |
| Descartados | 28 equivalentes, 22 não compilam, 7 erro de execução (RE), 6 tempo excedido (TLE) |
| Operadores dos 20 aceitos | UOI 8, ABS 6, ROR 6 |
| Tempo até aceitar 20 | 359 s e 346 s em duas execuções, em série; as duas rodaram ao mesmo tempo na mesma máquina (uma inflaciona a outra) |
| Repetibilidade | as duas execuções deram exatamente o mesmo funil (28/22/7/6) e a mesma distribuição de operadores: mesma sequência de candidatos, sem seed |
| Teste de integração de 8 mutantes aceitos do mesmo problema | 159 s (`tests/mutation/test_uniqueness.py`) |

**Estabilidade entre rodadas independentes (2026-09-24, teste de R10; repetida com 800 mutantes em
R14, também 0% de divergência)**: duas gerações completas e
independentes de `189_C` (795 s e 831 s, mesmo código) deram **os mesmos 100 arquivos, o mesmo
SHA-256 em cada posição e o mesmo `generation.json`**: divergência de **0 em 100** mutantes, apesar
de 11 TLE e 18 RE entre os descartados (candidatos de margem). Sustenta a simplificação de 2.3
(item 4: 6 execuções sobre um binário compilado uma vez) para esse problema; é amostra de um
problema e duas rodadas; repetida depois com 800 mutantes (R14, 0% de divergência). Não houve uma
segunda geração completa dos 200 problemas para comparar com a final (`research.md`, R15).

**Geração completa de `189_C` (2026-09-24, executada pelos autores, cota 100, em série, antes do
filtro de 2.7)**: 795 s (13 min 16 s); 100 aceitos após avaliar 241 candidatos (41,5% de
aceitação), com 141 descartes: 64 erro de compilação, 48 equivalentes, 18 RE, 11 TLE; ~3,3 s por
candidato avaliado. Esse resultado motivou o filtro de 2.7 e a paralelização: o primeiro mutante
gerado era `0 >> n` no lugar de `cin >> n` (não lê a entrada), o que o filtro passou a evitar.

**Paralelização de `generate` (2026-09-24, `research.md` R14)**: um trabalhador por `slot` do motor,
paralelismo entre problemas, resultado idêntico por construção — **aprovada pelos autores,
implementada e validada**. Validação em 8 problemas (`1196_D1`, `1278_B`, `1288_C`, `265_D`,
`523_C`, `630_G`, `719_A`, `967_C`; Intel i7-1165G7, 4 núcleos e 8 threads): `--workers 1` contra
`--workers 4` deram os mesmos arquivos e os mesmos SHA-256 (**0 de 800 mutantes divergentes**,
funil de descartes idêntico, com 70 TLE, 77 RE e 6 MLE entre os descartados); tempo de 3.520 s para
1.700 s, **aceleração de 2,07×** (cada problema fica ~1,8× mais lento sob 4 trabalhadores; em
outra máquina o ganho será outro). Com o filtro, 63 dos 1.415 candidatos avaliados nesses 8
problemas não compilaram (**4,5%**, contra 24% antes) e a aceitação foi de 56,5%; o tempo médio
foi de 440 s por problema em série. Extrapolação (não medida) para os 200 problemas: ≈24 h em série
e ≈12 h com 4 trabalhadores, sem contar os que precisarem de ordem superior. Substitui a
extrapolação de ≈44 h, feita sobre `189_C` antes do filtro.

**Ordem superior implementada (2026-09-24, `research.md` R17)**: quando a primeira ordem não
chega a 100, `generate` combina pares e depois trios dos mutantes de primeira ordem já aceitos,
na ordem de aceitação (`itertools.combinations`), sem busca e sem aleatoriedade; descarta a
combinação cujos sítios coincidem ou se sobrepõem em bytes; e, se ainda faltar, **exclui o problema**
com alerta (nenhum `Mutant_<n>.cpp`, `generation.json` com `status: excluded`, código de saída `0`).
Testado com motor falso e com o motor real (pares de um programa pequeno viram WA reais). O
piloto de desempenho desse caminho é o registro seguinte (2.9).

### 2.9 Piloto da ordem superior **[MEDIDO E DECIDIDO, 2026-09-24 — `research.md`, R18, resolve R4]**

`generate --workers 3` sobre os três problemas com menos candidatos de primeira ordem dos 200
(`569_A`: 26, `630_J`: 31, `270_B`: 39): **os três fecham 100 mutantes só com pares** (17, 23 e 24
mutantes de primeira ordem mais 83, 77 e 76 pares), nenhum precisou de trio, nenhum foi excluído,
em 371, 408 e 425 s. **76% a 83% dos mutantes desses problemas são, portanto, de segunda ordem**
(o custo em qualidade de 2.4, agora medido). Aceitação dos pares: 90% (as duas mudanças partem de
mutantes já válidos); ~4 s por candidato tentado. **Decisão: não há orçamento de tentativas** —
o espaço de pares/trios é pequeno quando há poucos mutantes de primeira ordem e, quando há muitos,
faltam poucos e os pares aceitos chegam rápido; o parâmetro `max_attempts` existe e está testado,
mas sem constante em `config.py`. Reabrir se a execução completa mostrar algum problema com mais
de 1.000 candidatos de ordem superior tentados sem fechar. Limite: amostra de 3 problemas, os mais
esparsos por contagem bruta.

### 2.10 Recuperação de execuções interrompidas **[VALIDADO, 2026-09-24 — `research.md`, R19]**

Um problema só aparece em `data/mutants/problems/` inteiro (montado em `building/`, fechado por
uma renomeação atômica); interromper por qualquer motivo (Ctrl+C, `docker stop`, `kill -9`,
queda de energia) perde **só** o problema em andamento, que é refeito do zero na próxima execução;
os já fechados não são tocados e o resultado final é idêntico, byte a byte, ao de uma execução
nunca interrompida. Validação real (motor real, `630_G` e `719_A`): SIGINT com 2 trabalhadores
encerrou o container em 1 s (a validação achou e corrigiu uma falha: antes, o `close` do pool
esperava os problemas em voo e Ctrl+C não saía em 40 s); SIGKILL depois de um problema fechado
deixou `problems/` com o problema completo e nada pela metade, e a retomada pulou o fechado
(mesmo hash e mesmo `mtime`) e gerou o outro, com o mesmo funil de descartes da geração sem
interrupção. Acrescentados: aviso `DAMAGED` (arquivo de problema fechado perdido ou alterado,
`package` se recusa), trava `flock` contra dois `generate` simultâneos e recusa do `package`
quando faltam problemas do dataset.

### 2.11 Execução final da geração de mutantes **[MEDIDO, 2026-09-24/25 — `research.md`, R21]**

`generate --workers 4` sobre os 200 problemas (commit `8a45e6c`; computador de 4 núcleos e 8
threads): **200 problemas completos, 0 excluídos, 0 danificados; 20.000 mutantes; ~7 h 26 min de
relógio**. Avaliados 34.355 candidatos, 58,2% aceitos; descartes: 8.997 equivalentes (26,2%),
2.014 RE, 1.816 TLE, 1.334 que não compilam (3,9%), 166 MLE, 28 instáveis (0,08%), nenhuma
duplicata. **Por ordem: 84,7% dos mutantes de primeira ordem (16.930), 15,3% de segunda (3.061) e 9
de terceira** (só em `981_B`). **113 dos 200 problemas (56,5%) fecham só com primeira ordem; 87
(43,5%) precisaram de ordem superior**: a estimativa de pesquisa de "ao menos 3 em cada 4" (SC-003)
**não se confirmou** (ela contava sítios brutos, antes do filtro de fluxo e sem descontar os
equivalentes). Consequência para o texto do TCC: 15,3% dos mutantes têm duas ou três alterações.
Operadores (em 23.079 usos): UOI 8.580, ROR 6.332, ABS 5.372, AOR 2.624, LCR 171. **Pacote e relatório
(2026-09-25, gerados e versionados)**: `data/mutants.zip` com 20.000 arquivos, 9.499.327 bytes (9,06
MiB; SHA-256 `ffd44455…a1d81`), `manifests/mutants.manifest.json` (3,4 MB, um item por arquivo) e
`manifests/mutation_report.json` com os números acima (200 completos, 113 só de primeira ordem, 87
com ordem superior, 0 alertas); `mutation verify` e `python -m cli check --deep` deram `OK`. O
MS (seção 5.2) é, portanto, calculado sobre os 200 problemas. O tempo impresso por problema no log
inclui a espera na fila e não deve ser citado (R21).

### 2.12 Mutantes e a revisão 2 do dataset **[DECIDIDO, 2026-10-18 — Milena; CONFERIDO, 2026-11-14]**

Os mutantes dependem só do `AC_ref.cpp`, dos testes oficiais e dos limites do `metadata.json` (2.5);
os enunciados não entram na geração nem na validação. A revisão 2 do dataset (1.6.1) mudou só 104
`enunciado.md` e nenhum `AC_ref.cpp`, então os mutantes **não foram regenerados**: `data/mutants.zip`
e `manifests/mutants.manifest.json` são os de 2026-09-25 e valem para as duas revisões; depois da
revisão 2, `mutation verify` e `cli check --deep` deram `OK`. Na época só o SLM tinha rodado (a
execução dele sobre a revisão 1 foi parcialmente refeita, seção 3); GPT, Gemini e Claude ainda não
tinham sido submetidos e rodaram já sobre a revisão 2.

**O hash do relatório.** `manifests/mutation_report.json` guarda `dataset_manifest_sha256` =
`6b3628c3…`, o SHA-256 do `manifests/dataset.manifest.json` do commit `9b87d7e` (2026-09-22), o
manifesto sobre o qual os mutantes foram gerados. O arquivo mudou de hash duas vezes depois
(conferido em 2026-11-14 com `git show <commit>:manifests/dataset.manifest.json | sha256sum`): no
commit `8b0bb7a` (2026-10-05), `a092d987…`, hoje `manifests/dataset.rev1.manifest.json`, com o mesmo
conteúdo e só os fins de linha diferentes (CRLF; `.gitattributes` marca `manifests/**` como `-text`);
e no commit `8c22193` (2026-10-20), `70d93346…`, o da revisão 2. O relatório **não foi regerado**
(decisão de Milena, 2026-10-18): regerar trocaria o hash por um de uma revisão a que os mutantes não
estão ligados por conteúdo. Quem comparar o hash do relatório com o manifesto atual vai ver a
diferença, e este parágrafo é a explicação. (`specs/007-dataset-revision/tasks.md`, T020, registra a
mesma decisão.)

---

## 3. Módulo: Orquestração de IA / Geração de Prompt

**[DECIDIDO E EXECUTADO — estado final em 2026-11-14]** Os quatro modelos geraram as suítes das
600 combinações (200 problemas × 3 cenários) cada um: o **SLM** (Qwen2.5-Coder-14B, local;
`specs/003-slm-test-generation/spec.md`, 2026-09-29), o **GPT-5.4-mini** e o **Gemini 3.8 Flash**
(`specs/004-llm-test-generation/`, spec de 2026-10-13, código e testes de 2026-10-15) e o **Claude
Haiku 5.5** (`specs/008-claude-test-generation/`, 2026-10-20). Os três comerciais rodaram em
2026-10-20 sobre a revisão 2 do dataset (seção 1.6.1). O pacote do SLM junta a execução da revisão 1
(2026-10-06 a 2026-10-09; 392 combinações que ficam) e a refeita na revisão 2 (as 208 combinações
afetadas pela correção dos enunciados); o resultado final, a origem de cada combinação e as
tabelas de cada modelo estão nas seções "Execução completa do SLM" e "Execução completa" de cada
modelo comercial, mais adiante nesta seção. As subseções abaixo registram, em ordem de decisão,
como cada parte foi especificada; os rótulos de estado (`[PLANEJADO]`, `[ESPECIFICADO]`) de cada
uma são os da data indicada, e a data é a referência (o estado de cada comando está no
`README.md` do módulo `ai_clients`).

**Parâmetros de ambiente que não mudam o resultado, mas ficam registrados [CONFERIDO, 2026-11-14]**:
`OLLAMA_HARDWARE_LABEL` (`.env`) é texto livre que descreve a máquina do Ollama e é gravado junto
de cada resposta do SLM; todas as chamadas das duas execuções (revisão 1 e a refeita na revisão 2,
870 chamadas) têm a mesma etiqueta, "GPU T4, 16GB RAM", embora parte tenha rodado em outra máquina
com a mesma T4, o mesmo Ollama 0.35.0 e o mesmo modelo (nota de hardware em "Execução completa do
SLM"); trocar a etiqueta ou a máquina não impede o `--resume`. `CHARS_PER_TOKEN`
(`src/ai_clients/llm/config.py`) é a razão de caracteres por *token* usada só na **estimativa de
custo** do `--dry-run` dos modelos comerciais, nunca na cobrança nem nas métricas: GPT 3,0 e Claude
3,0 (conservadora, definida antes do piloto, sem medida própria) e Gemini 3,354 (medida no piloto 1,
2026-10-16: 69.717 caracteres para 20.786 *tokens* devolvidos pela API); a origem de cada valor está
em `CHARS_PER_TOKEN_ORIGIN`. O custo real de cada execução vem do uso devolvido pela API, não dessa
razão.

**Modelos avaliados**:
- GPT-5.4-mini (OpenAI, API) — snapshot datado `gpt-5.4-mini-2026-03-17` (não o apelido), Responses
  API, `store: false`, `reasoning.effort: "medium"` **enviado explicitamente** (o padrão do modelo é
  `none`), sem `temperature`, `top_p` nem `seed`, saída `text.format` do tipo `json_schema` com
  `strict: true`. **[DECIDIDO, 2026-10-15 — A3, `specs/004-llm-test-generation/research.md`.]**
- Gemini 3.8 Flash (Google, API) — `gemini-3.8-flash` (GA desde 2026-09-02, sem identificador
  datado: a versão que responde é registrada pelo `modelVersion`), `generateContent` (sem
  estado), `thinking_level: "medium"` **enviado explicitamente** (níveis `low`, `medium` e `high`,
  padrão `medium`), sem `temperature`, `top_p` ou `top_k` (o Google recomenda manter o padrão nos
  Gemini 3 e, no 3.8, manda removê-los como descontinuados), sem `seed`, saída JSON com schema de
  resposta (`generationConfig.responseFormat.text`, com `mimeType: "APPLICATION_JSON"` e
  `schema`; conferido num pedido de teste em 2026-10-16, em que o valor `"application/json"` da
  documentação foi recusado; plano, R3). **[DECIDIDO, 2026-10-15 — idem; modelo revisto no
  mesmo dia, de `gemini-3.6-flash` para `gemini-3.8-flash`.]** O texto do TCC previa o **Gemini
  3.5 Flash**, que o Google descontinuou em 2026-10-08, redirecionando as chamadas para o
  `gemini-3.6-flash`. Entre os substitutos, os autores escolheram o Flash GA mais recente, em vez do
  3.6, que o próprio Google descreve como "previous-generation" (seção 7, item 41). Preço
  introdutório do 3.8 Flash até 2026-12-31 (US$ 0,75 por milhão de tokens de entrada, 3,75 de saída,
  0,075 em cache), que dobra em 2027-01-01 (1,50 / 7,50 / 0,15); a tabela da execução é fixada no
  plano.
- **Nomes dos parâmetros mudaram desde o texto do TCC (Tabela 2 do PDF)**: na OpenAI,
  `reasoning_effort` virou `reasoning.effort` (Responses API), e o JSON estrito se pede por
  `text.format` `json_schema` com `strict: true`; no Gemini, o `mimeType: application/json` do
  texto vai em `generationConfig.responseFormat.text`, com o valor `"APPLICATION_JSON"`
  (conferido na API em 2026-10-16: o valor `"application/json"` do exemplo da documentação foi
  recusado), e o nível de raciocínio em `generationConfig.thinkingConfig.thinkingLevel`. O texto final deve trazer os nomes
  atuais. Nos dois modelos, cada tentativa
  grava o modelo e a versão devolvidos pela API (`model`; `modelVersion`), os parâmetros enviados
  e a resposta crua, e a **não reprodutibilidade bit a bit** é limitação declarada (não há seed).
  O prompt vai inteiro numa única mensagem de usuário, sem instrução de sistema (A11), e o Gemini
  não recebe `safetySettings` (A13). **Barreira de raciocínio em toda execução (A12)**: uma
  resposta com zero tokens de raciocínio (`usage.output_tokens_details.reasoning_tokens` no GPT,
  `thoughtsTokenCount` no Gemini) ou sem a contagem é gravada fora das tentativas, e o comando para
  com código próprio até os autores investigarem **[regra de 2026-10-15; a regra vigente desde
  2026-10-20 é a da execução completa do Gemini, mais adiante: a resposta sem raciocínio fica em
  `barred/`, é pedida de novo e, na terceira, a suíte é `accepted_barred`, sem parar o comando]**.
  **Conferido no piloto e nas execuções completas**: o GPT respondeu com o snapshot pedido
  (`gpt-5.4-mini-2026-03-17` nas 601 chamadas) e o Gemini devolveu `modelVersion`
  `gemini-3.8-flash` (613 chamadas).
- **Planejamento dos LLMs comerciais [PLANEJADO em 2026-10-15; IMPLEMENTADO e EXECUTADO, ver as execuções completas abaixo — `specs/004-llm-test-generation/plan.md`,
  `research.md` R0 a R14]**:
  - **Código:** subpacote `src/ai_clients/llm/`, que reaproveita o SLM por importação (leitura do
    problema, montagem do prompt com os mesmos três marcadores, regras de teste vazio, abreviado e
    cercado, travas, escrita atômica, núcleo do zip) sem mudar o comportamento do SLM. Os clientes
    HTTP usam a biblioteca padrão, sem SDK, para que nenhuma repetição fique escondida.
  - **CLI:** os comandos existentes ganham `--model {slm,gpt,gemini}` (e `claude` desde 2026-10-20).
  - **Suíte:** o `suite.json` dos LLMs tem as mesmas chaves de topo do SLM, mas um schema próprio
    (`LlmSuite`), porque o `SlmSuite` confere a política de seeds do SLM. A avaliação lê os 3
    modelos por um leitor comum (`SuiteView`; decisão S1 dos autores).
  - **Dry-run:** não chama nenhuma API. Estima os tokens de entrada pelos caracteres dos prompts
    reais ÷ uma razão por modelo (3,0, conservadora, antes do piloto; depois, a medida), e a saída
    pelo teto ou pela média medida (decisão S2 dos autores).
  - **Confirmação e teto:** a confirmação de cada invocação é a própria opção do teto de gasto
    (`--confirm-spend US$`).
  - **Códigos de saída novos:** 5 (teto de gasto atingido) e 6 (resposta sem raciocínio; sem uso desde 2026-10-20, ver seção 3).
  - **Teto de saída** provisório de 32.768 *tokens* nos dois modelos no piloto, fixado depois pela
    maior saída medida.
  - **Tabela de preços** por data de validade, porque o preço do Gemini muda em 2027-01-01.
  - **Pacotes:** `data/gpt_suites.zip` e `data/gemini_suites.zip`, com manifestos e relatórios
    próprios, e as camadas `gpt_suites` e `gemini_suites` no `cli check`.
  - **Risco registrado:** o Google passou a chamar o `generateContent` de "Legacy" e recomenda a
    Interactions API (que guarda estado por padrão); ele "remains fully supported", sem data de
    desligamento, e os autores o mantiveram (decisão S3).
  - **Implementado em 2026-10-15** (`src/ai_clients/llm/`; 1.765 testes do projeto passando, o
    SLM sem regressão; nenhum teste chama uma API paga). Duas decisões da implementação: no
    `Ctrl+C`, as chamadas em andamento terminam e são gravadas (nada é pago duas vezes; só um
    encerramento à força refaz uma chamada); e um texto que não é UTF-8 válido (caractere
    substituto solto num JSON válido) faz da resposta um `schema_violation`, gravado normalmente.
    O leitor comum leu as 600 suítes reais do SLM da época (execução da revisão 1: 505
    `accepted`, 93 `accepted_fallback`, 2 `accepted_predicted`; o pacote final tem 504, 95 e 1) sem
    nenhuma recusa.
  - **Dry-run medido em 2026-10-15** (200 problemas, nenhuma chamada): 600 combinações por modelo,
    cerca de 824 mil *tokens* de entrada pela razão 3,0, maior prompt 7.459 caracteres (híbrido de
    `61_B`); com a saída no teto de 32.768 nos dois extremos (antes do piloto), GPT de US$ 89,09 a
    267,28 e Gemini de US$ 74,35 a 223,04 (preço introdutório). O custo real tende a ser bem menor;
    o piloto mede a saída real.
  - **Piloto 1 do Gemini [MEDIDO, 2026-10-16 — `research.md` R15]**: 15 combinações (os 5 problemas `1000_B`, `1005_C`, `1008_B`, `1_B` e `61_B` nos 3 cenários),
    15 chamadas, todas com suíte na 1ª tentativa; nenhuma falha de formato, resposta cortada, resposta
    barrada ou bloqueio de segurança; `finishReason` `STOP` e `modelVersion` `gemini-3.8-flash` nas 15;
    saída por chamada (resposta mais raciocínio) média de 1.965 *tokens*, mediana 1.640, mínima 1.114 e
    máxima 3.551 (11% do teto de 32.768), dos quais raciocínio médio de 1.206 (de 334 a 2.845) e a
    resposta visível no máximo 894; 69.717 caracteres de prompt para 20.786 *tokens* de entrada
    devolvidos pela API (3,354 caracteres por *token*; a estimativa usava 3,0); suítes de 7 a 12
    testes (mediana 10), 2 testes descartados por entrada vazia; tempo por chamada mediano de 13,1 s e
    máximo de 29,1 s; custo real US$ 0,126, contra US$ 1,86 a 5,58 estimados antes do piloto.
    Com isso, a estimativa do Gemini passa a usar 3,354 caracteres por *token* e a saída média de
    1.965 (execução completa: US$ 4,97 a 222,84), e o teto de saída fica em 32.768 nos dois
    modelos. Relatório em `manifests/gemini_generation_report.piloto1.json`.
  - **Desvio da Constitution justificado:** a ausência de seed nos LLMs (A3) é um desvio do
    Princípio II ("seed fixa e documentada"), justificado por escrito no "Complexity Tracking" do
    `plan.md`. Nenhuma das APIs garante reprodução com seed, e os números publicados se apoiam no
    pacote versionado da execução final (emenda 1.6.0).
- Qwen2.5-Coder-14B (local, via Ollama: `qwen2.5-coder:14b`, digest `9ec8897f747e…`,
  quantização Q4_K_M, Ollama 0.35.0) **[DECIDIDO, 2026-10-06 — `research.md` R20]**; o
  Qwen2.5-Coder-7B (`qwen2.5-coder:7b`) do texto do TCC foi o modelo só dos pilotos 1 a 3
  (o piloto 4 já usou o 14B) — sem parâmetro de esforço de raciocínio
  (limitação arquitetural do modelo, considerar na análise de resultados); saída em
  **texto plano com 3 blocos marcados** (`<edge_cases_analysis>`, `<reference_py>`, `<inputs>`
  com vários `<input>`, nesta ordem desde 2026-10-06), não JSON (ver abaixo); cada chamada disparada sem
  retenção de histórico. **[DECIDIDO, 2026-09-29 — `specs/003-slm-test-generation/spec.md`,
  D1.]**

**Regra de isolamento**: toda requisição é *stateless* — nenhum modelo pode reter
contexto de chamadas anteriores. Isso é requisito de arquitetura, não só de prompt
(ver Constitution, princípio III).

**Particularidade do SLM — oráculo por execução [DECIDIDO, 2026-09-29 —
`specs/003-slm-test-generation/spec.md`]**: diferente dos dois modelos de fronteira
(que preveem o `expected_output` de forma preditiva, o que é suscetível a erro), o SLM
gera, numa única resposta, as entradas (explorando casos-limite, respeitando as
restrições do enunciado) e uma solução de referência do problema **em Python** — nunca
prevê a saída. O pipeline separa duas fases: (1) **geração**, com rede — envia a
requisição ao Ollama e persiste a resposta crua, as entradas, a solução Python e a
seed, sem executar nada; (2) **execução**, em sandbox sem rede — roda a solução Python
contra os testes públicos do problema (único critério de validação da solução; o
`AC_ref.cpp` nunca é usado para aprovar, descartar ou corrigir) e, se ela passa, contra
as entradas geradas, preenchendo `expected_output` com o resultado da execução real. A
solução Python roda no mesmo motor de isolamento do módulo `sandbox` (sem rede, sem
privilégios, memória derivada dos metadados do problema), sob um tempo limite generoso
(múltiplo do limite do problema, só contra laço infinito) e nunca é objeto de
avaliação. Uma entrada em que a solução falha isoladamente é descartada sozinha. Uma
tentativa falha por uma de **4 razões de conteúdo**, as únicas que consomem tentativa:
`public_test_failed` (a solução reprova um teste público), `unparseable_response` (resposta
não interpretável), `repetition` (o Ollama interrompe o modelo preso num laço de repetição;
desde 2026-10-04) e `all_inputs_failed` (erro de execução e/ou timeout, em qualquer
combinação, em 100% das entradas geradas; a clarificação de 2026-09-29 juntou "erro em todas"
e "timeout em todas" numa razão só, corrigido aqui em 2026-09-30). Falha de infraestrutura na
chamada ao Ollama (serviço fora do ar, túnel caído, timeout de conexão) **não** consome
tentativa: a mesma chamada é refeita com a mesma seed e a mesma temperatura.

**Política de tentativas — 5 fases [DECIDIDO E IMPLEMENTADO, 2026-10-06 — `research.md` R21 e
R22; usada no piloto 6 e na execução completa, R23 e R28]**: no máximo **15 tentativas** por
problema × cenário, com seed e temperatura fixadas por tentativa numa tabela única do código
(`ATTEMPT_POLICY`, gravada no `run.json` e conferida em toda retomada):

| Fase | Tentativas | Seed | Temperatura | Termina com |
|---|---|---|---|---|
| 1 — solução, seed varia | 1 a 6 | 42 a 47 | 0,7 | a primeira solução que passa em todos os testes públicos (`accepted`) |
| 2 — solução, temperatura cai | 7 a 12 | 48 | 0,7; 0,6; 0,5; 0,4; 0,3; 0,2 | idem (`accepted`) |
| 3 — reserva (sem chamada) | — | — | — | a melhor das 12 que reprovou um teste público **só por WA** e manteve entradas (`accepted_fallback`: mais testes públicos aprovados, depois mais entradas mantidas, depois a de menor número) |
| 4 — predição | 13 a 15 | 49, 50, 51 | 0,7 | a primeira resposta interpretada do template de predição, com entradas e saídas escritas pelo modelo, sem validação (`accepted_predicted`); nova tentativa só por resposta não interpretável |
| 5 — tratamento manual | — | — | — | a combinação fica aguardando os autores (`awaiting_manual`, código de saída 4), que a fecham com `python -m ai_clients close` e motivo obrigatório (`discarded_manual`, continua no N = 200) |

Nenhum par (seed, temperatura) se repete numa combinação. As entradas geradas rodam quando a
solução passa em tudo ou quando o primeiro erro num teste público é WA (é o que permite a
reserva). **Nenhuma combinação fica sem suíte**: os status possíveis são `accepted`,
`accepted_fallback`, `accepted_predicted` e `discarded_manual` (mais `awaiting_manual`
enquanto os autores não decidem). **Nas execuções completas (a da revisão 1 e a refeita na revisão 2)** nenhuma combinação chegou à fase 5
(0 aguardando, 0 `discarded_manual`), então o `close` não foi necessário (não foi exercitado com
o modelo real). *Histórico, todo substituído pela política acima*: até 2026-10-05, 6 tentativas
estritas (seeds 43 a 48) e descarte da suíte; em 2026-10-05 (R16), 8 estritas, reserva, extras
9 a 12 e descarte só depois da 12ª; em 2026-10-06 (R18/R19), 20 tentativas com solução, baixa
confiança e predição nas tentativas 21 a 23 (itens datados abaixo). Limitação a registrar: nos cenários com código
(caixa-branca e híbrido), o SLM pode traduzir o `AC_ref` para Python em vez de
resolver o problema de forma independente, o que tende a reduzir a TFP por construção
— não há verificação própria de não determinismo da solução Python gerada. Detalhes
completos (schema da suíte, formato exato de persistência, retomada) em
`specs/003-slm-test-generation/`.

**Parametrização técnica do SLM [DECIDIDO no plano, 2026-09-30 —
`specs/003-slm-test-generation/research.md`, R2–R8; amostragem, forma dos casos e ajuste do
template confirmados por Milena no mesmo dia]**:

- **Chamada**: `POST /api/chat` do Ollama, `stream: false` (desde 2026-10-07, `stream: true`;
  ver "Resposta em *streaming*" abaixo), **uma única mensagem** (`role:
  user`) com o prompt inteiro, sem `context` nem `system` — sem estado por construção (R2). O
  modelo, o `digest`, a quantização e a versão do Ollama são registrados por execução e
  conferidos em toda retomada: na execução completa, `qwen2.5-coder:14b`, digest
  `9ec8897f747e…`, Q4_K_M, Ollama 0.35.0 (nos pilotos 2 e 3, `qwen2.5-coder:7b`, digest
  `dae161e27b0e…`, conforme os relatórios versionados desses pilotos).
- **Janela de contexto medida**: o maior prompt montado entre os 200 problemas tem **7.870
  caracteres** (híbrido, `61_B`; mediana do híbrido 5.224; maior caixa-preta 6.701; maior
  caixa-branca 5.469; medição de 2026-09-30). Fixados **`num_ctx = 8192`** e **`num_predict =
  4096`** (≈ 3.150 *tokens* de prompt no pior caso, estimativa pessimista de 2,5 caracteres por
  *token*). Guarda em tempo de execução: se `prompt_eval_count + num_predict > num_ctx`, a execução
  para sem gravar a tentativa (o Ollama truncaria o prompt em silêncio) (R3). O máximo real de
  `prompt_eval_count` é medido no piloto. **Medido** — piloto 1: 2.044; piloto 2: 2.170; piloto 3:
  2.393; piloto 5: 2.262; **execução completa na revisão 1 (relatório de 2026-10-11, 2.185 chamadas): 2.499; refeita na revisão 2 (870 chamadas): 2.500**,
  dentro dos 3.072 *tokens* que sobram para o prompt (`num_ctx` 8.192 − `num_predict` 5.120).
  **Remedido com o prompt real (2026-09-30, `generate --dry-run` sobre os 200 problemas)**: com a
  redação final do template e os sub-rótulos do `<context_data>`, o maior prompt é **8.118
  caracteres** (híbrido, `61_B`; caixa-preta 6.896, `61_B`; caixa-branca 5.674, `893_C`), 600
  chamadas previstas; ≈ 3.250 *tokens* + 4.096 de saída ≈ 7.350, ainda abaixo de 8.192 — a
  decisão não muda.
  **Revisto depois do piloto 1 (2026-10-04, `research.md` R13)**: o piloto mediu no mínimo 3,32
  caracteres por *token* (maior `prompt_eval_count` observado: 2.044, híbrido de `1000_B`) e 3
  respostas cortadas por `num_predict` (`done_reason = "length"`: 2 no híbrido, 1 na caixa-branca).
  **`num_predict` passa a 5.120**: com o template novo o maior prompt tem 8.074 caracteres (híbrido,
  `61_B`), ≈ 2.430 *tokens*; os 3.072 *tokens* que sobram para o prompt cobrem até 2,63 caracteres
  por *token*. A guarda continua valendo. **Execução completa (2026-10-11, revisão 1)**: 77 das 2.185
  respostas cortadas por `num_predict` (`done_reason = "length"`: caixa-preta 48, híbrido 26,
  caixa-branca 3; na refeita, 42 das 870: caixa-preta 20 e híbrido 22); elas caem no parser como qualquer resposta e consomem a tentativa.
- **Amostragem [DECIDIDO, 2026-09-30 — item 27 da seção 6; temperatura e seed revistas em
  2026-10-06, R21/R22]**: `top_p 0.8`, `top_k 20`, `repeat_penalty 1.05` fixos (configuração de
  geração publicada pelo fabricante do Qwen2.5-Coder-Instruct), todos enviados explicitamente;
  **temperatura e seed por tentativa**, pela tabela `ATTEMPT_POLICY` da política de 5 fases (fase
  1: 0,7 com seeds 42 a 47; fase 2: seed 48 com 0,7 a 0,2; fase 4: 0,7 com seeds 49 a 51).
  **[SUBSTITUÍDO em 2026-10-06 por R21/R22]**: `temperature 0.7` fixa e seed da tentativa `n` =
  `42 + n` (43 a 48 até 2026-10-05; 43 a 54 com R16; 43 a 65 com R19). Achado que
  restringe a escolha: com `temperature 0` a decodificação é gulosa, a seed não tem efeito e as
  tentativas repetiriam a mesma resposta (R4); toda temperatura da tabela é maior que 0.
- **Montagem do prompt**: o `<context_data>` usa sub-rótulos fixos (`<problem_statement>`,
  `<reference_solution_cpp>`), e o híbrido é a união literal dos outros dois; fora dele, o prompt
  dos 3 cenários de um problema é idêntico byte a byte (R5).
- **Interpretação**: cada tag de topo abre e fecha exatamente uma vez, na ordem fixa; texto fora
  dos blocos é ignorado e contado (não corrigido); entradas repetidas são mantidas e contadas, por
  inflarem o tamanho da suíte (R6). **Revisto depois do piloto 1 (2026-10-04, R13)**: uma cerca
  Markdown que envolve o código Python inteiro (primeira linha ```` ```python ````, ```` ```py ````
  ou ```` ``` ````; última ```` ``` ````) é removida e registrada por tentativa — no piloto 1 ela foi
  a causa de todas as 6 reprovações por erro de execução do híbrido —, e qualquer outra cerca fica
  como veio (vira erro de execução); um `<input>` vazio é descartado sozinho e contado, sem invalidar
  a tentativa (antes invalidava; 3 tentativas do piloto 1 caíram assim), e só "todas vazias" é
  resposta não interpretável. Cercas removidas, entradas vazias e respostas cortadas são somadas
  por cenário no relatório.
- **Execução do Python**: CPython 3.11 base da imagem, só biblioteca padrão (`-I -B -X utf8`; sem `-S` desde 2026-10-05, R15),
  no mesmo `execute` do motor (uid por slot, sem rede, rlimits), workdir novo por execução;
  **tempo = limite do problema × 10** e **memória = limite do problema × 4** (os 7 problemas de
  61 MiB tornariam a memória do próprio interpretador um risco com fator 1; a confirmar no piloto)
  (R7). **Medido**: no piloto 3 nenhum RE em teste público chegou perto do limite de memória
  (R15); na execução completa, 282 entradas geradas foram descartadas por `runtime_error` e 47 por
  `timeout` (0 por saída não UTF-8). O relatório junta RE e MLE em `runtime_error`, então
  quantas dessas 282 foram por memória **não é separado no relatório**. O `expected_output` gravado é a saída crua da execução; a comparação futura usa a regra
  única do motor (`outputs_equal`).
  **Implementado (2026-10-01, `python -m ai_clients execute`)**: todo veredito vem do
  `judge_test` do motor com os limites multiplicados; nos testes públicos vale a comparação
  completa (AC/WA/TLE/MLE/RE), nas entradas geradas só TLE (→ descarte `timeout`) e MLE/RE (→
  descarte `runtime_error`) importam, porque a saída ainda não existe — é ela que se está
  medindo. O `execute` lê só `metadata.json` e `testes.json` do problema (o `AC_ref.cpp` nem é
  lido nesta fase). Um caractere UTF-16 avulso (*surrogate*) no código ou numa entrada gerada é
  repassado como está e o interpretador o rejeita: conta como erro de execução, nunca derruba o
  comando. Os testes de integração (serviço `sandbox`, motor real) confirmam: só biblioteca
  padrão, sem rede, uid do slot (não root), pasta vazia a cada execução, laço infinito vira TLE.
  **Revisto depois do piloto 2 (2026-10-05, `research.md` R14)**: o teste público que reprova
  passa a ficar registrado na tentativa (início do `stdout`, até 2.048 bytes; final do `stderr`;
  tempo de CPU; pico de memória). Motivo: no piloto 2 não deu para saber se algum RE de `1_B` foi
  falta de memória, porque um `MemoryError` do Python aparece como RE e nada disso era gravado.
- **Persistência e retomada**: cada tentativa gera arquivos imutáveis (geração; execução) e o
  `suite.json` terminal é função pura deles; falha de interpretação encadeia a próxima tentativa
  já na fase de geração (não há nada a executar); `--resume` explícito recusa continuar se a
  configuração (modelo, opções, template, dataset) mudou (R8). O `digest` do modelo é gravado
  também em cada tentativa, para que cada resultado se identifique sozinho.
  **Implementado (2026-10-01)**: interromper em qualquer um dos quatro pontos de gravação e rodar
  de novo dá a mesma árvore final de uma execução sem interrupção (verificado com cliente e
  executor falsos); antes de agir sobre uma combinação, o comando confere todos os arquivos dela
  (sequência das tentativas, seed, `digest`, e `suite.json` igual byte a byte ao recalculado) e
  uma combinação que não bate é apontada como danificada, nunca consertada. A validação real
  (`Ctrl+C` com o Ollama de verdade) fica para depois do piloto. **Observada na execução completa
  (registrado em 2026-10-11)**: os logs dos `generate` (`data/logs/gpu0.log`, `gpu1.log`,
  `gpu2.log`) têm 44 interrupções (`interrupted; it is safe to run the command again`: 18 + 22 +
  4); a cada uma o `--resume` continuou, e o estado final não tem perda nem dano (`cli check` OK,
  600/600 com `suite.json`, tentativas sem buraco, nenhuma combinação danificada no relatório).
- **Falha de infraestrutura [DECIDIDO, 2026-09-30 — `research.md` R9, R12]**: nunca consome
  tentativa — a mesma chamada é refeita com a **mesma seed**. As repetições consecutivas têm um
  teto e a espera por uma resposta tem um *timeout* de leitura, ambos configuráveis pelo operador
  no `.env` (`OLLAMA_MAX_INFRA_RETRIES`, padrão 30; `OLLAMA_HTTP_TIMEOUT_S`, padrão 900 s); ao
  atingir o teto, o comando para sem gravar nada e a retomada refaz a mesma chamada. Motivo: um
  *timeout* fixo curto demais para um Ollama em CPU faria a mesma chamada se repetir para sempre,
  sem nunca gravar nada. Nenhum dos dois valores muda o conteúdo das respostas, por isso não entram
  na identidade da execução. O tempo máximo real por chamada é medido no piloto. **Medido** — a
  chamada mais longa: 166 s no piloto 1, 233 s no piloto 2, 131 s no piloto 3, 252 s no piloto 4,
  179 s no piloto 5, 166 s no piloto 6; **execução completa**: o relatório só traz a soma (134.843 s
  ≈ 37,5 h de modelo); contado em 2026-10-11 nos 2.164 arquivos de tentativa com resposta do
  Ollama (`total_duration`; as outras 21 são `repetition`, sem resposta), mediana de 47,8 s e
  máximo de 446 s (`357_A` híbrido, tentativa 7), nenhuma acima dos 900 s. O tempo de relógio,
  com GPUs em paralelo, não é medido. Os logs dos `generate` têm 362 linhas `ollama unavailable`
  (repetições da mesma chamada por falha de infraestrutura, sem gastar tentativa).
  **Revisto no piloto (2026-10-01)**: com o Ollama atrás de um túnel do ngrok, a queda do túnel
  responde HTTP 404 com `ERR_NGROK_3200` e era tratada como erro de configuração (o comando parava).
  Passa a ser falha de infraestrutura (espera e repete a mesma chamada, mesma seed); o 4xx do
  próprio Ollama continua sendo configuração. Nada foi gravado na ocorrência.
  **Revisto depois do piloto 1 (2026-10-04, R13)**: o HTTP 500 `token repeat limit reached` (o
  Ollama interrompe o modelo preso num laço de repetição) era tratado como queda e repetia a mesma
  seed até o teto de 30. É falha do próprio modelo — com a mesma seed o laço se repetiria —, então
  passa a consumir a tentativa com a razão nova `repetition` (gravada, sem resposta) e a próxima
  seed é chamada.
- **Casos de teste da suíte**: gravados no contrato já existente `TestCase` (`input`, `output`) de
  `testes.json`; o módulo de avaliação, quando especificado, deve adotá-lo ou mudar o schema de
  propósito (decidido em 2026-09-30, item 29 da seção 6); a mesma forma vale para as suítes dos
  três modelos comerciais.
- **Relatório, pacote e conferência [IMPLEMENTADO, 2026-10-01 — `research.md` R10]**:
  `python -m ai_clients report` grava `manifests/slm_generation_report.json` a qualquer momento (a
  proporção de cada status é sempre sobre todo problema × cenário do dataset; quartis por interpolação
  linear; entradas descartadas contadas em todas as tentativas executadas, duplicatas só nas
  suítes aceitas); `package` só empacota a execução inteira, sem dano, em `data/slm_suites.zip`
  determinístico com manifesto; `python -m cli check` ganhou a camada `slm_suites`. **Divergência
  em relação ao plano**: na camada nova, o que ainda falta (árvore, problema, cenário,
  `suite.json`) é só aviso enquanto o pacote não existe, mesmo com `--deep`, porque o piloto e a
  execução completa começam, ambos, por `cli check --deep` com saída `0` e a árvore ainda vazia ou
  pela metade; depois do `package`, é falha. Estrutura impossível (buraco nas tentativas, mais de
  15 tentativas ou execução depois da 12ª — política de 5 fases, desde 2026-10-06; antes 23 com R19,
  12 com R16 e 6 até 2026-10-05 —, arquivo estranho, pasta sem problema, `superseded/` que não bate
  com as trocas de template) é falha desde o início. **Execução completa (2026-10-11)**: `cli
  check` OK (600/600 com `suite.json`, tentativas sem buraco, `superseded/` igual às trocas).
  **Pacote da revisão 1 (2026-10-11; o atual, juntado com a execução refeita na revisão 2, é o do fim da seção 3 sobre o SLM)**: `data/slm_suites.zip` com 6.597.040 bytes (SHA-256 `b73d2750…`) e 4.850
  arquivos (as 600 combinações, o `run.json`, a troca de template e os 3 arquivos que ela tirou de
  `problems/`), manifesto `manifests/slm_suites.manifest.json`; `verify --extracted` `OK` e `cli check
  --deep` `OK` sem aviso, com o SHA-256 de cada arquivo e do zip conferido.
- **Leitura do problema**: composta localmente no módulo `ai_clients` a partir dos leitores já
  existentes do dataset (`Metadata`, `Testes`) e da leitura direta de `enunciado.md`/`AC_ref.cpp`;
  nenhum leitor novo no módulo `dataset` (decidido em 2026-09-30).
- **Ajuste do template para FR-007 [DECIDIDO, 2026-09-30 — item 28 da seção 6]**: a RULE 2 deixa
  de pedir "the maximum size allowed by the constraints" e passa a pedir o maior caso que o modelo
  consegue escrever por inteiro, com todo valor dentro das restrições; a RULE 3 ganha a frase
  "Every value in every input MUST respect the constraints stated in the context." Motivo: uma
  entrada do tamanho máximo estoura `num_predict` e a resposta sai truncada.
  **Revisto depois do piloto 1 (2026-10-04, R13)**: o item dos casos grandes passa a dizer "Use
  values up to the maximum allowed by the constraints, but keep the NUMBER of elements in each input
  small enough to write out fully (e.g., at most ~100 elements).", e o item do menor caso perde
  "(including empty input if allowed)".
- **Piloto 2 [MEDIDO E DECIDIDO, 2026-10-05 — `research.md` R14]**: 5 problemas (`1000_B`,
  `1005_C`, `1008_B`, `1_B`, `61_B`) × 3 cenários, 74 tentativas, GPU T4. Suítes
  aceitas: caixa-preta 1/5, caixa-branca 3/5, híbrido 4/5 (8/15); tentativas aceitas 1/30, 3/26 e
  4/18. **As 7 suítes descartadas caíram todas porque a solução Python do modelo errou um teste
  público** (no total, 33 WA, 29 RE e 1 TLE em 63 reprovações), nunca por causa das entradas; 3
  respostas não foram interpretadas (2 cortadas por `num_predict`, 1 `repetition`). O problema de 61
  MiB do piloto (`1_B`) reprovou nas 18 tentativas. Maior `prompt_eval_count` 2.170 (guarda de
  `num_ctx` sem disparar); mediana de 29 s por chamada, a mais longa 233 s (limite 900 s); cerca
  Markdown removida 4 vezes (híbrido), 1 entrada vazia; suítes aceitas de 4 a 25 casos. Nos 4
  problemas comuns aos dois pilotos, 5 de 12 suítes aceitas nos dois. Projeção para as 600
  combinações, com as taxas do piloto: ≈ 280 sem suíte e ≈ 24 h de chamadas. Decidido: **o `AC_ref`
  nunca gera nem confere saídas esperadas** (na vida real não existe uma implementação de referência
  correta para isso); **cada tentativa continua independente** (as entradas saem junto com a solução
  reprovada; reaproveitá-las entre tentativas foi rejeitado); **orçamento mantido em 6 tentativas**;
  o teste público que reprova passa a ficar registrado; a revisão do prompt abre o piloto 3, com os
  mesmos 5 problemas. Modelo `qwen2.5-coder:7b`; relatório versionado em
  `manifests/slm_generation_report.piloto2.json`.
- **Template revisto depois do piloto 2 [DECIDIDO, 2026-10-05 — `research.md` R14, item 6]**: o
  modelo é avisado de que a solução roda primeiro no exemplo; a RULE 1 pede o algoritmo passo a
  passo e uma simulação à mão no exemplo antes do código; a RULE 2 pede de 10 a 20 entradas
  distintas e troca "entradas que parecem válidas mas são inválidas" (contradizia a RULE 3) por
  entradas "quase quebrando uma regra, mas válidas"; a RULE 3 proíbe abreviações ("...", "(repeated
  N times)"); a RULE 4 dá dicas de Python (só biblioteca padrão, ler a entrada de uma vez, evitar
  recursão funda, imprimir no formato do exemplo); sai a última menção a entrada vazia. O texto
  continua igual nos 3 cenários. Maior prompt: 8.993 caracteres (híbrido, `61_B`), ≈ 2.420 *tokens*
  pela razão medida no piloto 2, dentro da folga; `num_ctx`/`num_predict` não mudam. Rejeitados:
  mandar não traduzir o C++ na caixa-branca (quebraria a igualdade do texto entre cenários e só
  baixaria a taxa de acerto) e descartar no parser entradas com "..." (em problemas de grade, `.` é
  um caractere válido).
- **Piloto 3 e piloto com outro modelo [MEDIDO E DECIDIDO, 2026-10-05 — `research.md` R15]**: com
  o template revisto, o piloto 3 (`qwen2.5-coder:7b`, GPU T4; relatório
  versionado em `manifests/slm_generation_report.piloto3.json`; interrompido em 37 tentativas,
  5 delas aceitas, com 5 combinações aceitas e as outras 10 paradas com 3 de 6 tentativas, todas
  falhas) zerou as respostas não
  interpretadas e cortadas, manteve as entradas entre 10 e 20 e subiu a taxa de acerto por tentativa
  de 11% para 14% (caixa-preta de 3% para 18%). As 32 falhas continuam sendo a solução Python errando
  os testes públicos (17 WA, 15 RE, nenhum por memória). Projeção: ≈ 40% das 600 combinações sem
  suíte e ≈ 20 h de chamadas. **Achado de infraestrutura**: 3 RE eram `NameError: name 'exit' is not
  defined`, porque o Python rodava com `-S` (sem `site`, que define `exit()`); o `-S` saiu. Decidido:
  encerrar o piloto 3 e rodar um piloto 4 com `qwen2.5-coder:14b` (mesmo template e mesmos 5
  problemas), escolhido pela variável opcional `OLLAMA_MODEL` do `.env` (o modelo vai para o
  `run.json`). O modelo e o método do experimento ficam pendentes (seção 6, item 30), com o
  critério sugerido: se o 14B deixar mais de ≈ 20% das combinações sem suíte, discutir fazer o
  SLM prever as saídas como os dois modelos comerciais.
- **Piloto 4 e suíte de reserva [MEDIDO E DECIDIDO, 2026-10-05 — `research.md` R16]**: com
  `qwen2.5-coder:14b` (mesmo template, mesmos 5 problemas), 13 de 15 suítes aceitas (caixa-preta
  3/5, caixa-branca 5/5, híbrido 5/5), 13 de 40 tentativas aceitas (32,5%, contra 14% do 7B no
  piloto 3), mediana de 76 s por chamada (máximo 252 s). As 27 falhas foram todas em teste
  público (16 WA, 11 RE); as 2 suítes descartadas (`1000_B` e `1008_B`, caixa-preta) erraram
  um teste público nas 6 tentativas, 11 das 12 por WA. Em `1008_B` a solução responde `YES`
  no teste público 1, que espera `NO`, e o prompt só mostra o teste 0. Mediana de 1.082 *tokens*
  de saída (máximo 2.009); de 10 a 21 entradas por resposta. Decidido que **nenhuma
  combinação pode ficar sem suíte**. *[Regra de tentativas abaixo SUBSTITUÍDA em 2026-10-06 por
  R18 e, no mesmo dia, pela política de 5 fases, R21/R22]*: 8 tentativas estritas; depois delas, a melhor tentativa
  que reprovou um teste público só por WA e manteve entradas vira suíte de reserva
  (`accepted_fallback`: mais testes públicos aprovados, depois mais entradas mantidas,
  depois a de menor número); sem nenhuma, tentativas 9 a 12 com esse mesmo critério; descarte
  só depois de 12. Uma tentativa com WA num teste público passa a rodar as entradas geradas.
  As saídas de uma reserva vêm de uma solução que erra em algum caso: pendente como as
  métricas tratam essas suítes (seção 6, item 31).
- **Template revisto depois do piloto 4 [DECIDIDO, 2026-10-06 — `research.md` R17]**: texto
  trocado inteiro (3.361 caracteres, eram 3.984), com os mesmos marcadores e o mesmo exemplo.
  Os blocos passam a ser pedidos na ordem análise, solução, entradas, e o parser exige essa ordem.
  A análise fica em no máximo 15 linhas e reescreve o formato de entrada, as restrições e a regra
  exata da resposta antes da simulação à mão do exemplo. Na caixa-branca, o modelo é instruído a
  inferir o comportamento e o formato de entrada pelo código (o texto continua igual nos 3
  cenários). A solução deve usar o algoritmo mais simples e obviamente correto, até força bruta,
  num script plano com toda variável definida antes do uso. As entradas deixam de ter contagem
  pedida (eram de 10 a 20), ficam com no máximo ≈ 50 elementos e 20 linhas (eram ≈ 100 elementos),
  sem repetição, e o número de casos no início da entrada precisa bater com os casos escritos.
  Maior prompt calculado em ≈ 8.370 caracteres (era 8.993); `num_ctx`/`num_predict` não mudam. O
  efeito na taxa de acerto não foi medido; o próximo piloto é uma execução nova.
- **Nenhuma combinação sem suíte [DECIDIDO E IMPLEMENTADO, 2026-10-06 — `research.md` R18 e
  R19; testado só com modelo e execução simulados]** **[A ORDEM DE TENTATIVAS ABAIXO FOI
  SUBSTITUÍDA em 2026-10-06 por R21/R22 (política de 5 fases); continuam valendo o princípio
  "nenhuma combinação sem suíte", a predição, o tratamento manual e o `close`; a baixa confiança
  e as tentativas 13 a 23 deixaram de existir]**: substitui o descarte depois de 12 tentativas. Ordem: (1) tentativas 1 a 8,
  `accepted` na primeira que passa nos testes públicos; (2) reserva `accepted_fallback` entre as 8,
  como antes, sem chamada nova; (3) se nenhuma das 8 pode ser reserva, tentativas 9 a 20, parando
  na primeira `accepted` ou que possa ser reserva; (4) depois da 20ª, `accepted_low_confidence` =
  a primeira das 20 cuja solução manteve ao menos uma entrada gerada, mesmo com RE, TLE ou MLE num
  teste público (por isso as entradas passam a rodar depois de qualquer reprovação em teste
  público); (5) sem isso, **predição**: o mesmo modelo recebe um segundo template
  (`slm_predict_prompt.txt`, blocos `<edge_cases_analysis>` e `<tests>` com `<input>`/`<output>`,
  mesmas regras de entrada do principal) e escreve entradas e saídas esperadas, sem solução Python
  nem validação pelos testes públicos; nova tentativa só por resposta não interpretável, até 3
  (tentativas 21 a 23); status `accepted_predicted`, a única exceção ao oráculo por execução e a
  única em que o SLM faz o que os LLMs comerciais fazem; (6) sem resposta interpretável, a
  combinação fica aguardando tratamento manual: o comando segue com as demais, sai no fim com
  código próprio listando-as, e o pacote é recusado até os autores a fecharem, por comando
  explícito, como `discarded_manual` com motivo obrigatório (continua no N = 200). Relatório e
  métricas separados por status (item 31 da seção 6).
- **Desenho técnico da regra acima [IMPLEMENTADO, 2026-10-06 — `research.md` R19]**
  **[SUBSTITUÍDO em 2026-10-06 por R21/R22: hoje são 15 tentativas, 1 a 12 com solução e 13 a 15
  por predição, seeds 42 a 51; continuam valendo o código de saída 4, o comando `close` e o
  relatório por status]**: um único contador de tentativas por combinação (1 a 20 com solução, 21 a 23 por
  predição, seeds 43 a 65), o tipo saindo do número. Na resposta por predição, um `<test>` com
  entrada ou saída vazia é descartado sozinho e contado, e a saída prevista é guardada como veio,
  sem conferência. O `run.json` passa a guardar o hash do segundo template e os orçamentos (20 e
  3). Combinação aguardando tratamento manual faz o `generate`/`execute` sair com o código **4**
  (novo, separado do 1 de dano); o fechamento é o comando `python -m ai_clients close --problem
  <id> --scenario <cenário> --reason "<motivo>"`, que grava o motivo e a data num arquivo próprio
  da combinação. O relatório troca as taxas de descarte e de reserva por uma proporção por status.
  Custo não medido: as entradas passam a rodar depois de TLE num teste público, cada uma podendo
  levar até 10 vezes o limite de tempo do problema.
- **Piloto 5, modelo do experimento e piloto 6 [MEDIDO E DECIDIDO, 2026-10-06 — `research.md`
  R20]**: com o 14B (código `7535dee`, GPU T4), os templates novos e a regra de
  R18, as 15 combinações terminaram com
  suíte (13 `accepted`; `1000_B` e `1008_B` caixa-preta como `accepted_fallback`, os mesmos 2
  que o piloto 4 descartou), 13 de 49 tentativas aceitas (26,5%), 36 falhas todas em teste
  público (29 WA, 7 RE), nenhuma resposta não interpretada, mediana de 48 s por chamada (máximo
  179 s), ≈ 44 min de modelo; maior `prompt_eval_count` 2.262; de 3 a 16 entradas por resposta e
  suítes de 5 a 16 casos. Nenhuma combinação chegou à baixa confiança, à predição ou ao
  tratamento manual. Decidido: o modelo do experimento passa a ser o **14B** (seção 6, item 30;
  seção 7, item 30); as suítes `accepted_fallback` entram nas métricas como as `accepted`, as
  de baixa confiança e por predição ficam separadas (item 31); antes da execução completa, um
  **piloto 6** escolhe a temperatura: 0,2 a 0,6 (passo 0,1) com seed base 42, mais o piloto 5
  como 0,7; depois a melhor e a 0,7 com as seeds base 1042 e 2042; vence a configuração com mais
  `accepted` entre as 15, depois maior acerto por tentativa, depois menor tempo. Para isso a
  temperatura e a seed base podem vir do `.env` (`OLLAMA_TEMPERATURE`, `OLLAMA_SEED_BASE`),
  gravadas no `run.json`. Custo do piloto 6 estimado, não medido: ≈ 7 h de modelo.
  *(O piloto de temperaturas foi substituído no mesmo dia pela política de 5 fases, abaixo;
  as duas variáveis do `.env` saem.)*
- **Política de 5 fases [DECIDIDO E IMPLEMENTADO, 2026-10-06 — `research.md` R21 e R22;
  testado só com modelo e execução simulados]**: substitui a ordem de tentativas anterior (8 estritas, extras até a 20ª e
  `accepted_low_confidence`) e é a política do experimento, validada antes num piloto 6 com os
  mesmos 5 problemas. **Fase 1**: tentativas 1 a 6, temperatura 0,7 e seeds 42 a 47; **fase
  2**: tentativas 7 a 12, seed 48 e temperatura 0,7; 0,6; 0,5; 0,4; 0,3; 0,2 — as duas param
  na primeira solução que passa em todos os testes públicos (`accepted`); **fase 3**: a reserva
  `accepted_fallback` entre as 12, sem chamada nova; **fase 4**: predição nas tentativas 13 a
  15, seeds 49 a 51, temperatura 0,7 (`accepted_predicted`); **fase 5**: tratamento manual
  (`close`, `discarded_manual`). Nenhum par (seed, temperatura) se repete; a tabela fica numa
  configuração única no código, gravada no `run.json`, e cada tentativa registra seed,
  temperatura e fase. As entradas geradas voltam a rodar só quando a solução passa em tudo ou
  o primeiro erro é WA. Saem `OLLAMA_TEMPERATURE` e `OLLAMA_SEED_BASE`. No máximo 15
  chamadas por combinação (eram 23). O efeito da temperatura baixa na fase 2 não foi medido.
  **Exercitada com o modelo real** no piloto 6 e na execução completa (fases 1 a 4; a fase 5
  nunca foi alcançada): na execução completa a fase 2 deu 25 suítes `accepted` (R28; ver
  "Execução completa do SLM" abaixo).
- **Desenho técnico da política de 5 fases [IMPLEMENTADO, 2026-10-06 — `research.md` R22]**: **motivo, pelos pilotos 4 e 5** (14B): as falhas foram quase todas WA em
  teste público, repetidas em várias seeds a 0,7 (`1000_B` e `1008_B` caixa-preta erraram 8 de 8
  no piloto 5), e as tentativas extras e a baixa confiança nunca foram exercitadas com o modelo
  real; a fase 2 testa outra alavanca (temperatura mais baixa com seed fixa) num orçamento menor.
  A tabela tentativa → fase, seed, temperatura, template fica escrita por extenso no código
  (`ATTEMPT_POLICY`), vai inteira para o `run.json` e o `--resume` recusa qualquer mudança nela;
  cada tentativa grava fase, seed, temperatura e template, conferidos contra o `run.json`. Todos
  os arquivos do módulo passam a `schema_version` 2: uma execução anterior (pilotos 1 a 5) é
  recusada com a instrução de mover `data/suites/slm`, o que precisa ser feito antes do piloto 6.
  Na resposta por predição, uma cerca Markdown que envolve um `<input>` ou `<output>` inteiro é
  removida e contada, como a do código. O relatório passa a mostrar, por cenário, em que fase e
  tentativa cada combinação ficou com a suíte e as chamadas, *tokens* e tempo de cada fase.
- **Piloto 6 e execução completa [MEDIDO E DECIDIDO, 2026-10-07 — `research.md` R23]**: com a
  política de 5 fases (código `e69d2fe`, 14B digest `9ec8897f…`, Ollama 0.35.0, etiqueta GPU T4,
  16GB RAM), as 15 combinações terminaram com
  suíte: 13 `accepted` (12 na fase 1; `1005_C` caixa-preta na fase 2, tentativa 8, temperatura
  0,6) e 2 `accepted_fallback` (`1000_B` e `1008_B` caixa-preta, as mesmas dos pilotos 4 e 5;
  `1000_B` pela tentativa 1, `1008_B` pela tentativa 9 — fase 2, temperatura 0,5 —, a que passou
  mais testes públicos);
  57 chamadas, 13 aceitas (22,8%), 44 falhas (35 WA, 8 RE, 1 com todas as entradas
  descartadas), nenhuma resposta não interpretada, mediana de 43 s por chamada, ≈ 46 min de
  modelo; nenhuma combinação chegou à predição nem ao tratamento manual. Decidido: **a
  configuração fica congelada e a execução completa continua esta mesma execução** com
  `--resume` até as 600 combinações (as 15 do piloto entram no resultado), gerando em duas GPUs
  T4 idênticas com dois `generate` em paralelo sobre metades disjuntas dos problemas
  (R24; desde R26, todos os problemas nos dois); a mesma etiqueta de hardware nos dois processos; o determinismo entre as duas GPUs não
  é medido. Primeiro passo da continuação: `cli check --deep` com saída 0. (Como a etiqueta
  ficou no fim, ver a nota de hardware em "Execução completa do SLM", abaixo.)
- **Execução concorrente para duas GPUs [DECIDIDO E IMPLEMENTADO, 2026-10-07 — `research.md` R24]**:
  vários `generate --resume` e um `execute` podem rodar ao mesmo tempo sobre `data/suites/slm/`
  (trava compartilhada); cada problema × cenário é tratado por um processo de cada vez (trava
  exclusiva por combinação, sem esperar), e a combinação em uso por outro é **pulada e contada**
  no resumo (`N skipped (in use by another command)`), nunca esperada; o estado é relido com a
  trava pegada, então duas metades sobrepostas nunca fazem a mesma tentativa duas vezes. O
  primeiro `generate` (sem `--resume`), `close` e `package` continuam exclusivos (recusa com
  código 1 se houver outro comando), e só um `execute` por vez (o *slot* do motor é único). Cada
  `generate` usa o `OLLAMA_BASE_URL` passado com `-e` e confere, no `--resume`, que o modelo e a
  versão do Ollama do seu endpoint são os do `run.json` (configuração congelada). Nenhum dado do
  experimento muda: os arquivos gravados são os mesmos de uma execução sem concorrência; as travas
  são arquivos com ponto, fora do pacote e do `cli check`. Testado com dois `generate` em metades
  disjuntas e sobrepostas, `execute` com `generate` ativo e `package`/`close` recusados.
- **Divisão automática do trabalho entre as GPUs [DECIDIDO E IMPLEMENTADO, 2026-10-07 —
  `research.md` R26]**: com metades fixas, a GPU0 terminou a sua e ficou parada enquanto a GPU1
  ainda tinha fila. O laço passa a dar **todos** os problemas aos dois `generate --resume`; como
  a combinação em uso por um é pulada pelo outro (R24), os dois se revezam na fila: a máquina
  mais rápida trata mais combinações e nenhuma fica parada enquanto houver combinação livre. O
  `skipped` passa a ser o esperado (cada linha é uma combinação tratada pelo outro processo).
  Nenhum código muda e nenhum dado do experimento muda: a seed, a temperatura e o texto de cada
  tentativa dependem só da combinação e do número da tentativa, não da GPU que a fez.
- **Resposta em *streaming* [DECIDIDO E IMPLEMENTADO, 2026-10-07 — `research.md` R25]**: pelo
  túnel do cloudflared, chamadas de mais de ~100 s recebiam HTTP 524 (o proxy fecha um pedido sem
  bytes nesse tempo) e eram repetidas até esgotar as repetições. O `/api/chat` passa a ser pedido
  com `stream: true`: o conteúdo é a junção dos pedaços e modelo, `created_at`, `done_reason`,
  contagens e durações vêm do último pedaço, o que dá o **mesmo registro** da chamada sem
  *streaming* (texto, opções e seed não mudam; o *streaming* é só transporte). Resposta que
  termina antes do último pedaço é falha de infraestrutura (mesma chamada, mesma seed, nada
  gravado). `OLLAMA_HTTP_TIMEOUT_S` passa a medir o maior silêncio entre pedaços. O `run.json`
  não muda: a execução em andamento continua com `--resume` (conferido: nenhuma diferença).
- **Troca do template de predição numa execução em andamento [DECIDIDO E IMPLEMENTADO,
  2026-10-07; executada em 2026-10-08 — `research.md` R27 e R28]**: o template de predição gerou
  entradas degeneradas: na `939_C` caixa-preta, a única das 594 pastas de combinação existentes
  em 2026-10-07 que tinha chegado à predição, a tentativa 13 escreveu
  `1 1 1 ...` até o teto de 5120 tokens e a 14, aceita como `accepted_predicted`, tinha um teste
  com a entrada abreviada `1 1 1 ... 1 (100000 ones)`. O STEP 2 do template passa a limitar cada
  entrada a 10 elementos e 10 linhas (valores grandes, poucos elementos) e a proibir sequências
  longas. Para **não misturar versões na mesma execução**, a troca é feita pelo comando
  `change-template` (motivo obrigatório): ele registra a troca (hashes antigo e novo, data,
  motivo) e move para `data/suites/slm/superseded/` as tentativas feitas com o template antigo,
  da primeira delas em diante, com a suíte; essas combinações são refeitas com o template novo e
  as **mesmas seeds**. Cada tentativa passa a gravar o hash do template usado, e uma tentativa de
  outra versão torna a combinação danificada. O `run.json` não é reescrito: o template corrente é
  o dele com as trocas aplicadas. O que foi movido entra no pacote, para a banca ver o que foi
  refeito, mas não nas métricas. Na predição, um teste com valores abreviados (`1 2 ... 5`, `…`) é
  descartado e contado (`abbreviated_tests`); medido: nenhum dos 47.492 textos de teste do dataset
  casa essa regra, enquanto qualquer `...` casaria 67 (grades de pontos em 445_A e 452_A).
  Única diferença de texto: o `detail` de uma falha `repetition` passa a citar o *stream* em vez
  de `HTTP 500` (informativo; o motivo e a contagem são os mesmos).
  **Como a troca aconteceu (R28)**: registrada pelo `change-template` em 2026-10-08T11:49:11Z
  como `template_changes/001.json` (predição, SHA-256 `421adf86626a…` → `e52133f6ea0c…`; o template
  de solução, `fc9757e8bcb1…`, nunca mudou). Moveu 3 arquivos da `939_C` caixa-preta para
  `superseded/001/939_C/black_box/` (`suite.json` e as tentativas 14 e 13). A combinação foi refeita
  em 2026-10-08 com o template novo e as mesmas seeds: tentativa 13 (seed 49) de novo até o teto
  (5.120 *tokens*, `length`, `unclosed_block:tests`, 413 s); 14 (seed 50) `unclosed_block:test`;
  15 (seed 51) interpretada → `accepted_predicted`, 10 testes. O template novo não evitou a
  degeneração na tentativa 13; a 15 deu a suíte. Em toda a execução só **2 combinações** chegaram
  à predição, e as duas suítes finais vêm do template novo (toda tentativa de predição em
  `problems/` tem o hash `e52133f6…`): a `939_C` caixa-preta e a `237_A` caixa-branca (em
  2026-10-09, só com o template novo: tentativa 13, seed 49, `unclosed_block:test`; 14, seed 50,
  interpretada → `accepted_predicted`, 8 testes). **Correção do motivo (2026-10-11)**: o campo
  `reason` da troca tinha sido gravado por engano como `"..."`. Foi corrigido **antes do `package`**, reescrevendo só esse campo de `template_changes/001.json`:
  o script conferiu que o valor era exatamente `"..."` e que o manifesto do pacote não existia,
  validou o arquivo pelo schema `TemplateChange`, gravou de forma atômica e conferiu que todos os
  outros campos ficaram iguais; o `report` foi refeito. Nenhum hash dependia do campo (o pacote
  ainda não existe). Texto gravado: "o template de predição gerava entradas longas e degeneradas
  (sequências abreviadas com '...'), causando loop de repetição e timeout no túnel; o novo limita a
  10 elementos por entrada e 5 a 12 testes".
- **Execução completa do SLM, na revisão 1 do dataset [MEDIDO, 2026-10-06 a 2026-10-09; relatório de
  2026-10-11 — `research.md` R28; os números desta execução ficam como história: o relatório
  vigente, `manifests/slm_generation_report.json`, é o da refeita na revisão 2, logo abaixo, e o
  pacote final é a junção das duas]**: continuação da execução do piloto
  6 (`run.json` de 2026-10-06T23:37:55Z; primeira chamada 2026-10-06T23:40:40Z, última
  2026-10-09T17:40:40Z), com a configuração congelada: `qwen2.5-coder:14b` (digest `9ec8897f747e…`,
  Q4_K_M), Ollama 0.35.0, `num_ctx` 8.192, `num_predict` 5.120, template de solução `fc9757e8bcb1…`,
  template de predição `421adf86626a…` → `e52133f6ea0c…` (troca acima), política de 5 fases.
  **As 600 combinações terminaram com suíte**:

  | Status | Total | Caixa-preta | Caixa-branca | Híbrido |
  |---|---|---|---|---|
  | `accepted` | 505 (84,2%) | 134 | 186 | 185 |
  | `accepted_fallback` | 93 (15,5%) | 65 | 13 | 15 |
  | `accepted_predicted` | 2 (0,3%) | 1 (`939_C`) | 1 (`237_A`) | 0 |
  | `discarded_manual` / aguardando / pendentes | 0 | 0 | 0 | 0 |

  (Tabela da execução da revisão 1, sobre as 600 combinações. As 208 combinações dos 104 problemas
  de enunciado corrigido foram refeitas, e `939_C` caixa-preta está entre elas; no pacote final só
  resta `237_A` caixa-branca como `accepted_predicted`.)

  Fase em que fecharam: fase 1 = 480 (355 já na tentativa 1), fase 2 = 25, fase 3 (reserva) = 93,
  fase 4 (predição) = 2. Chamadas: 2.185 (fase 1: 1.537; fase 2: 643; fase 4: 5), das quais 1.678
  falharam (76,8%): `public_test_failed` 1.554, `unparseable_response` 102, `repetition` 21,
  `all_inputs_failed` 1; 77 respostas cortadas por `length`. Entradas descartadas: `runtime_error`
  282, `timeout` 47, saída não UTF-8 0; 12 entradas repetidas mantidas; 1 `<input>` vazio; 0 cercas
  Markdown removidas; na predição, 0 testes vazios e 0 abreviados. *Tokens*: 2.997.679 de prompt e
  1.879.362 de saída; maior `prompt_eval_count` 2.499. Tempo de modelo (soma das chamadas):
  134.843 s ≈ 37,5 h (fase 1 25,4 h; fase 2 11,8 h; fase 4 0,2 h); o tempo de relógio não é
  medido. Tamanho das suítes: mediana 10 (`accepted` de 1 a 33, mediana 10; `accepted_fallback` de
  5 a 54, mediana 10; `accepted_predicted` 8 e 10). Uma troca de template (acima). `cli check` OK;
  `close` não foi necessário (0 combinações aguardando os autores). Pacote gerado em 2026-10-11:
  `data/slm_suites.zip` (6.597.040 bytes, SHA-256 `b73d2750…`, 4.850 arquivos), com
  `verify --extracted` e `cli check --deep` `OK`.
  **Nota sobre a etiqueta de hardware [DECIDIDO, 2026-10-11 — Milena]**: os arquivos gravados
  **não mudam**. Todas as 2.185 chamadas têm a mesma etiqueta de hardware (GPU T4, 16GB RAM), mas
  a execução usou mais de uma máquina com GPU (2×T4: o mesmo modelo de GPU, a mesma versão do Ollama e o
  mesmo digest do modelo, conferidos pelo `--resume`), sem impacto nos resultados. A etiqueta,
  portanto, não distingue as máquinas, e o determinismo entre GPUs não foi medido.

- **Pacote final do SLM: junção da revisão 1 com a refeita na revisão 2 [MEDIDO E DECIDIDO, 2026-10-19 a
  2026-10-22 — `specs/007-dataset-revision/`; `manifests/slm_generation_report.json`,
  `data/suites/slm/provenance.json`]**: com a revisão 2 do dataset (seção 1.6.1), o modelo local
  refez só as **208 combinações** (caixa-preta e híbrido dos 104 problemas de enunciado
  corrigido; a caixa-branca não usa o enunciado), com a mesma configuração congelada (mesmo
  modelo, digest, Ollama 0.35.0, opções, templates `fc9757e8bcb1…` e `e52133f6ea0c…`, política de 5
  fases; sem troca de template), sobre o manifesto do dataset `70d93346…` (revisão 2). As 392
  combinações restantes, cujo prompt é idêntico nas duas revisões, foram reaproveitadas da execução
  da revisão 1. A origem de cada uma das 600 combinações está em `data/suites/slm/provenance.json`
  (a árvore, a revisão e o hash do manifesto do dataset de onde veio; as 208 antigas ficam como
  `superseded`, só para auditoria); a árvore da revisão 1 fica em `data/suites/slm-rev1/`. O
  `slm_generation_report.json` descreve só a execução refeita (as 392 reaproveitadas aparecem
  nele como `pending_generation`, e não como falha). Resultado, recontado por script sobre os
  `suite.json` do pacote (e conferido contra o `provenance.json`):

  | Status final | Total (600) | Caixa-preta | Caixa-branca | Híbrido | da revisão 1 (392) | refeitas (208) |
  |---|---|---|---|---|---|---|
  | `accepted` | **504** (84,0%) | 134 | 186 | 184 | 339 | 165 |
  | `accepted_fallback` | **95** (15,8%) | 66 | 13 | 16 | 52 | 43 |
  | `accepted_predicted` | **1** (0,2%) | 0 | 1 (`237_A`) | 0 | 1 | 0 |
  | `discarded_manual` / aguardando / pendentes | **0** | 0 | 0 | 0 | 0 | 0 |

  Fase em que fecharam as 600: fase 1 = 482 (357 já na tentativa 1), fase 2 = 22, fase 3 (reserva por
  WA) = 95, fase 4 (predição) = 1. Suítes: 5.815 testes no total (caixa-preta 2.053, caixa-branca
  1.790, híbrido 1.972), mediana 10 por suíte (`accepted` de 1 a 32, soma 4.748; `accepted_fallback`
  de 5 a 54, soma 1.059; `accepted_predicted` 8). **A execução refeita (208 combinações)**:
  870 chamadas (fase 1: 595; fase 2: 275; fase 4: 0), das quais 705 falharam (81,0%); as combinações
  fecharam em fase 1 (157), fase 2 (8) e fase 3 (43); 42 respostas cortadas por `length`; entradas
  descartadas: `runtime_error` 114 e `timeout` 13; 19 entradas repetidas mantidas; 0 testes vazios,
  0 abreviados, 0 cercas Markdown removidas; *tokens*: 1.225.366 de prompt (maior
  `prompt_eval_count` 2.500) e 798.283 de saída; tempo de modelo 66.913 s ≈ 18,6 h; hardware
  registrado "GPU T4 - Google Colab, 16GB RAM" nas 870 chamadas. Parte da geração rodou com o
  `generate` fora do Docker (válvula de escape do ambiente de GPU, seção 8, 2026-10-22). Pacote
  final: `data/slm_suites.zip` (8.961.292 bytes, SHA-256 `1303e652…`, 6.741 arquivos);
  `verify` sem `--extracted` confere o pacote (`OK`); com `--extracted data/suites/slm` ele
  relata `missing: suites/slm-rev1/...` para os arquivos da árvore da revisão 1, mesmo no lugar
  certo: é limitação conhecida e documentada (o `--extracted` olha só `data/suites/slm/`, e o
  pacote juntado tem também `data/suites/slm-rev1/`), não dado alterado; `cli check --deep` fica
  `OK` com os 4 modelos.

**Particularidade dos LLMs comerciais — oráculo por predição [ESPECIFICADO, 2026-10-13 —
`specs/004-llm-test-generation/spec.md`, D1 a D6; A1, A2, A4, A5 e A6 decididas no clarify de
2026-10-13, A7 a A13 nos dois de 2026-10-15, e A3 decidida pelos autores em 2026-10-15, seção 6,
item 32]**:
GPT-5.4-mini e Gemini 3.8 Flash recebem o mesmo `<context_data>` de cada cenário, o mesmo
few-shot e as mesmas regras de geração de entradas do prompt principal do SLM, e respondem em JSON
com schema estrito (`edge_cases_analysis` antes de `tests`, cada teste com `input` e `output`);
a **única diferença intencional** em relação ao SLM é o oráculo: o próprio modelo prevê a saída
esperada de cada entrada, sem programa executado e sem validação pelos testes públicos (o
`AC_ref.cpp` também não é usado). Uma nova tentativa só acontece por falha de formato (resposta
vazia, não JSON, fora do schema, cortada pelo teto de saída, recusa ou bloqueio, ou nenhum teste
utilizável), até **3 tentativas**; esgotadas, a combinação aguarda os autores e só fecha como
`discarded_manual` com motivo; falha de infraestrutura (rede, rate limit, 5xx) é repetida sem
contar. Cada entrada tem no máximo cerca de 50 elementos e 20 linhas, o mesmo limite do prompt
principal do SLM. A suíte é gravada no mesmo `suite.json` do SLM, com o status
`accepted_predicted` (seção 6, item 31), para a avaliação ler os 3 modelos do mesmo jeito; o
código fica em `src/ai_clients/`. O schema não tem campo de cálculo por teste: o cálculo da saída
esperada fica no raciocínio interno do modelo. O prompt vai inteiro numa única mensagem de usuário,
como no SLM, e uma resposta sem raciocínio para a execução. **[MEDIDO E DECIDIDO, 2026-10-19 — execução completa do Gemini, revisão 2 do dataset]** Na 10ª chamada da execução completa (`1009_B`, caixa-preta), o Gemini respondeu sem raciocínio: o pedido levava `thinkingLevel: "medium"`, a resposta veio completa (`STOP`, JSON válido, 764 *tokens* de saída, US$ 0,0037) e sem `thoughtsTokenCount`, com total igual a entrada + saída (1.090 + 764 = 1.854), isto é, zero *tokens* de raciocínio; as 9 respostas anteriores raciocinaram de 392 a 3.522 *tokens*, e as 15 do piloto também raciocinaram. Conclusão: o nível `medium` não garante raciocínio, e o modelo às vezes não raciocina. A barreira funcionou como previsto (resposta em `barred/`, fora das tentativas e das métricas, código 6, gasto de 9 chamadas aceitas US$ 0,0862). Decisão de Milena: manter a regra e retomar com `--resume`, que reenvia a combinação; a taxa de respostas sem raciocínio será medida na execução completa e, se as paradas forem frequentes, a regra é revista com o número medido. **[DECIDIDO E IMPLEMENTADO, 2026-10-20 — emenda de FR-018a, `specs/004-llm-test-generation/`]** A regra foi revista: a `1201_B` caixa-preta foi barrada 6 vezes seguidas (zero raciocínio em todas), e a `1009_B` caixa-preta, reenviada, raciocinou e virou suíte. Decisão de Milena (depois de uma primeira versão, no mesmo dia, que encerrava a combinação sem suíte): a resposta sem raciocínio continua guardada em `barred/` (custo no relatório, sem gastar tentativa), agora também interpretada, e a mesma tentativa é pedida de novo, até **3 respostas sem raciocínio por combinação** (contadas à parte das 3 tentativas com falha de formato); na terceira, a suíte é **`accepted_barred`**, com os testes da última resposta barrada legível (`barred_close` diz quantas e qual); se nenhuma for legível, a combinação aguarda os autores (`close`). O comando não para (o código 6 deixa de ser usado). As respostas barradas antes da mudança não têm interpretação e não decidem: a `1201_B` caixa-preta (6 delas) recebe mais um pedido. Consequência para a análise: as suítes `accepted_barred` vêm de respostas sem raciocínio e ficam marcadas, para serem analisadas à parte ou excluídas; o número delas por cenário deve ser relatado. Até a mudança: 125 suítes `accepted_predicted`, 7 respostas barradas em 2 combinações; os 125 `suite.json` conferem byte a byte com o esquema novo (o campo `barred_close` só aparece nas suítes `accepted_barred`). Toda chamada registra tokens, custo estimado e tempo; um dry-run estima o custo antes, e
nenhuma chamada paga sai sem confirmação explícita e um teto de gasto a cada invocação (atingido o
teto, nenhuma chamada nova sai e a retomada continua depois). O piloto é uma execução separada,
descartada para a execução completa (só o relatório dele é versionado), e cada modelo tem o seu
próprio pacote, manifesto e relatório. Limitações: as respostas não
são reproduzíveis bit a bit, e o provedor pode trocar a versão do modelo (cada tentativa grava o
identificador devolvido pela API).

**Visualização do pedido enviado [IMPLEMENTADA E MEDIDA, 2026-10-16 — `specs/005-show-request/`]**:
um comando de consulta (`show-request`) grava num arquivo, sem chamar nenhuma API, o corpo exato
do pedido de cada tentativa (ou a prévia do próximo pedido), com o prompt dentro, reconstruído dos
mesmos arquivos e conferido contra o `prompt_sha256` gravado, sem a resposta do modelo.
**[MEDIDO, 2026-10-16 — `research.md` R11]**: dry-run com gravação do GPT sobre os 200 problemas reais, antes da execução dele: 600 de 600 prompts fiéis ao dataset (enunciado, código e exemplo idênticos aos arquivos, sem código na caixa-preta nem enunciado na caixa-branca), 600 arquivos `.request.json` (4,8 MB) e aviso de expoente em 71 problemas (142 combinações), **exatamente** os 71 da contagem de 2026-10-16; dry-run do SLM: 0 combinações pendentes (execução terminada); `show-request` nas 15 combinações do piloto 1 do Gemini (`--suites-dir data/suites/gemini-piloto1`): 15 de 15 com o hash do prompt conferido e fiéis ao dataset; no SLM, as tentativas 1 e 12 de `1000_B` caixa-preta (seed 42 e temperatura 0,7; seed 48 e 0,2) e a tentativa 13 de `237_A` caixa-branca (texto-base de predição) conferidas; os pilotos 1 a 5 do SLM, de uma versão anterior do formato, são recusados (código 1); a busca no Git, no contêiner `app` com o `.git` somente leitura, achou pelo hash a versão mais antiga das 4 do `slm_prompt.txt`; prévia do GPT (`1_B` híbrido) e recusa de tentativa inexistente conferidas. O dry-run do Gemini fica com os autores. Testes: 1.868 passando (1.777 antes, 91 novos). Decidido pelos autores
(2026-10-16): reconstruir e conferir o hash, sem passar a gravar o texto do prompt em cada
tentativa (nada muda no que é gravado). **[DECIDIDO, 2026-10-16 — clarify]** B1: vale para os 3
modelos (o SLM com o texto-base e a seed/temperatura de cada tentativa); B2: o `generate --dry-run`
grava, numa pasta pedida, todos os pedidos que seriam enviados, com uma conferência de que o
enunciado, o código e o exemplo dentro de cada prompt são idênticos ao dataset e um aviso nos
enunciados com expoente perdido (que vem do próprio dataset); o `show-request` mostra no terminal e
grava com `--output`; B3: mostra só o que é enviado, nunca a resposta do modelo; B4: com o
texto-base mudado, busca no histórico do Git a versão com o hash gravado, e sem ela recusa.
**[DECIDIDO, 2026-10-16 — plano]**:
- **Git**: o serviço `app` passa a montar o `.git` somente leitura (só ele; o `sandbox` continua
  sem), decidido por Milena (S1); a busca usa só `git log` e `git cat-file`, que não alteram o
  histórico.
- **Corpo de uma tentativa feita**: vem dos parâmetros gravados nela, não do código atual (o
  `mimeType` do Gemini já mudou uma vez).
- **Dry-run**: o `generate --dry-run --save-requests DIR` grava, por combinação pendente, **um
  arquivo só**, `<id>.<cenário>.request.json`, com o corpo da requisição (o prompt vem dentro
  dele), numa pasta plana por modelo, mais um `summary.json`. O arquivo é o mesmo JSON enviado,
  indentado e com os caracteres não ASCII legíveis (`≤`), conferido por teste contra os bytes da
  rede.
- **`show-request`**: só grava o corpo num arquivo (`--output`, obrigatória) e confere a fidelidade
  ao dataset; o pedido nunca é impresso no terminal, que mostra só o resultado das conferências.
  O tempo não é medido.
- **Gemini**: como a execução completa já começou, os autores conferem o Gemini num dry-run
  separado; a calibração dos 71 expoentes é feita no GPT, com as 600 combinações pendentes. A pasta é plana para não ser "uma pasta por
  problema", o que exigiria uma camada no `cli check` (constitution, Princípio II; analyze de
  2026-10-16).
- **Fidelidade**: conferida contra os bytes crus de `enunciado.md`, `AC_ref.cpp` e `testes.json`,
  com a separação dos cenários (nada de código na caixa-preta, nada de enunciado na caixa-branca).
- **Expoente**: o aviso usa as mesmas expressões da contagem abaixo e precisa reproduzir os 71
  problemas.
- **Árvores arquivadas**: os pilotos são lidos com `--suites-dir`.
- **A tentativa que gerou cada suíte [DECIDIDO E MEDIDO, 2026-10-18 — `research.md` R12]**: `show-request --model M --suite-attempts --output-dir DIR`
  grava de uma vez o pedido da tentativa indicada no `suite.json` de cada combinação (não a
  última), com as mesmas conferências. `show-request --model slm --suite-attempts` sobre a execução completa do SLM: 600 de 600 pedidos gravados, todos com o hash do prompt conferido e fiéis ao dataset, nenhum pulado nem recusado, aviso de expoente nos mesmos 71 problemas (142 combinações), cerca de 23 s; a tentativa que gerou a suíte foi a 1 em 355 combinações, a 2 em 84, a 3 em 32, de 4 a 12 em 127 e a 14 e a 15 (predição) em 1 cada; em `1000_B` caixa-preta (`accepted_fallback`) a suíte veio da tentativa 1, embora a última feita tenha sido a 12.

**Expoentes perdidos nos enunciados [MEDIDO, 2026-10-16]**: em **71 dos 200** `enunciado.md`
(35,5%) as potências de 10 perderam o expoente no texto do dataset de origem: `10^5` aparece como
`105`, `10^9` como `109`, `10^6` como `106`, `10^18` como `1018` (por exemplo, `1_B`: "1 ≤ n ≤
105" e "larger than 106"). Contagem por padrão de texto, conferida à mão por amostragem: um desses
números logo depois de `≤`, `<`, `≥`, `>`, `·` ou `×` (68 enunciados; `105` 57 vezes, `109` 34,
`106` 10, `1018` 2; incluídos os 2 com `103`, que pelo contexto são 10³) ou em "modulo ... (109 +
7)", "from 1 to 106", "does not exceed 104" (3). Outros 53 enunciados preservam o expoente
(`10^5` ou `10^{5}`) e 76 não têm potência de 10. **Efeito**: no cenário caixa-preta (e no
híbrido, que também tem o enunciado) o modelo pode ler restrições erradas (`n ≤ 105` no lugar de
`n ≤ 100000`) e gerar entradas pequenas demais ou valores que não testam os limites; nos cenários
com código, o `AC_ref.cpp` costuma deixar os limites claros. Os 3 modelos recebem o mesmo texto,
então a comparação entre modelos não é afetada, mas a comparação entre cenários pode ser: é uma
limitação a registrar no TCC (e um fator a considerar na análise da caixa-preta). O dataset não é
corrigido (seria mudar o artefato validado e versionado). Problemas afetados: 134_A, 143_C, 151_D, 161_A, 165_C, 178_A1, 182_B, 189_C, 18_C, 190_A, 192_B, 1_B, 204_B, 205_B, 220_A, 224_B, 231_C, 237_A, 256_A, 265_D, 270_B, 284_B, 285_B, 291_C, 334_B, 349_A, 352_A, 358_B, 365_A, 368_C, 372_A, 380_A, 413_B, 417_B, 446_A, 447_C, 455_A, 459_B, 493_B, 493_C, 518_B, 523_C, 534_C, 569_A, 570_A, 572_B, 630_J, 652_A, 670_D2, 675_A, 702_C, 70_B, 710_B, 713_A, 733_B, 734_C, 73_A, 747_C, 75_A, 770_C, 789_A, 79_A, 832_B, 847_H, 870_B, 876_B, 88_C, 893_C, 913_C, 91_B, 950_B.

**Conferência dos enunciados contra o original [DECIDIDA no clarify e IMPLEMENTADA, 2026-10-18 — `specs/006-statement-fidelity/spec.md`]**: o dataset não é alterado por esta conferência (E1); o acesso ao Codeforces é uma página por vez, a cada 3 s ou mais, uma única vez (E2); tabelas viram tabelas em Markdown e imagens vão para revisão (E3); a marcação corrigida é `^{...}` e `_{...}`, sempre com chaves (E4).

**[PLANEJADO e IMPLEMENTADO, 2026-10-18 — `specs/006-statement-fidelity/plan.md`]**: dois comandos do módulo `dataset`, `check-statements` (obtém uma vez, a cada 3 s ou mais, a página original de cada problema, guarda a cópia com hash em `manifests/statement_originals.manifest.json`, extrai o bloco do enunciado sem cabeçalho nem exemplos, alinha com o `enunciado.md` e classifica cada diferença pelo elemento do original que a cobre — expoente, índice, fórmula, imagem, tabela, outra —, gravando `manifests/statement_fidelity_report.json`) e `correct-statements` (insere no texto atual as marcações do original e só aceita o corrigido com as três conferências; grava numa pasta plana para revisão, nunca no dataset). **[DECIDIDO, 2026-10-18 — Milena]** S1 — versionar só os blocos do enunciado num `data/statement_originals.zip`, com as páginas inteiras fora do Git ; S2 — o corrigido é o texto atual com as marcações inseridas, não um texto refeito do zero. S3: a tabela de equivalências das fórmulas (`\le`→`≤`, `\lt`→`<`, `\dots`→`...`) é a medida no piloto; qualquer outra aparece como diferença.

**Conferência dos enunciados contra o original [IMPLEMENTADA E MEDIDA, 2026-10-18 — `specs/006-statement-fidelity/research.md` R10; relatório versionado em `manifests/statement_fidelity_report.json`]**: `check-statements` nos 200 problemas (2026-10-18): download dos 195 restantes em 13 min 12 s (rodado por Milena; nenhum `unchecked`); segunda execução sem nenhum acesso ao site e relatório byte a byte igual (SHA-256 `22d234e7…`, SC-003). O primeiro relatório tinha 188 diferenças `formula` e 274 `other` que, examinadas, eram conversões feitas pelo dataset (comandos LaTeX trocados por um símbolo) e listas que o dataset escreveu em Markdown (`* `, `1. `); a tabela de equivalências passou a ter as 16 trocas de um comando por um símbolo vistas nos pares do próprio relatório (`\leq`→`≤`, `\ldots`→`…`, `\cdot`→`⋅`, `\rightarrow`→`→`, `\ne`/`\neq`→`≠`, `\ge`→`≥`, `\gt`→`>`, `\times`→`×`, `\lfloor`/`\rfloor`/`\lceil`/`\rceil`, `\sum`→`∑`, `\,`→espaço, `\bmod`→`mod`, além das 3 do piloto) e os itens de lista passaram a ser lidos como o dataset os escreveu; as perdas de expoente e índice não mudaram com isso. Relatório final: **83 fiéis, 117 com diferença; 152 expoentes perdidos em 79 problemas; 701 índices perdidos em 74 problemas**; 23 diferenças de fórmula em 12 problemas (mudanças de forma, como `\frac{a}{b}` escrito `(a)/(b)`, `\limits`, `\max`); 36 `other` em 4 problemas (`670_D2`: a página atual tem outro texto; `1162_B` e `981_B`: barras invertidas a mais no nosso texto, em matrizes e conjuntos LaTeX; `190_A`). Contra a contagem antiga por padrão: 70 dos 71 confirmados pelo original (o 71º, `670_D2`, não pôde ser comparado porque o texto da página difere), e 9 problemas com expoente perdido que ela não via (`102_B`, `155_C`, `203_B`, `252_A`, `271_B`, `289_C`, `362_B`, `538_A`, `765_C`). `correct-statements`: 102 enunciados corrigidos (151 expoentes e 701 índices marcados), 83 sem mudança, 15 para revisão (12 por fórmula, 3 por `other`), nenhuma conferência falhou; o dataset continua igual ao manifesto (`verify --extracted`: OK). **Efeito para o TCC**: a perda de formatação do dataset é maior que a contagem anterior indicava — além de 152 expoentes em 79 problemas, 701 índices (`a_i` escrito `ai`) em 74; a aplicação da correção ao dataset continua sendo decisão dos autores (E1), com os 102 corrigidos prontos para revisão em `data/statements/corrected/`. O pacote `data/statement_originals.zip` (só os 200 blocos do enunciado) tem 243.507 bytes (medido em 2026-10-18); o `.gitignore` ganhou a exceção dele.

**Comparação com o enunciado original do Codeforces [MEDIDO, 2026-10-18 — piloto]**: piloto só de leitura com 5 problemas (`161_A`, `1_B`, `1000_B`, `15_A`, `102_B`), páginas originais do Codeforces baixadas uma vez (HTTP 200, guardadas em `data/cf_pilot/`, fora do Git). Dois formatos no HTML cru: o antigo marca expoente e índice com `<sup class="upper-index">` e `<sub class="lower-index">`, e o nosso `enunciado.md` perdeu os dois; o novo traz a fórmula crua (`$$$1 \le n \le 10^5$$$`, `$$$a_i$$$`), e o nosso texto preservou `10^5` e `a_i` (o que explica os 53 enunciados com o expoente certo). Perdas confirmadas pelo original: `161_A` 4 expoentes e 21 índices (`a_i` → `ai`), `1_B` 2 expoentes, `15_A` 6 índices, `102_B` 1 expoente (`10^100000` → `10100000`), `1000_B` nenhuma. Conclusões: (1) a contagem por padrão de texto (71) está incompleta (não viu `102_B`, porque só procurava expoentes de 2 a 18); (2) os índices também se perdem e não eram contados; (3) a comparação com o original é mecânica e não depende de uma lista de padrões, e passa a ser a fonte de verdade (feature `specs/006-...`, a especificar).

**Template de prompt**: estrutura única em inglês, com marcação XML (`<system_rules>`,
`<context_data>`, `<few_shot_example>`, `<task>`), combinando Few-Shot Prompting +
Chain-of-Thought. Antes de gerar os testes, o modelo é obrigado a preencher um campo
de análise prévia de casos-limite (`edge_cases_analysis`) — reduz alucinação e
superficialidade. O exemplo do `<few_shot_example>` é **o primeiro teste público do
próprio problema sendo perguntado** (escolha determinística pela ordem em
`testes.json`), igual nos 3 cenários daquele problema — nunca um exemplo fixo de outro
problema, para não induzir o modelo a um formato de entrada que não corresponde ao
problema real. **[DECIDIDO, 2026-09-29 — `specs/003-slm-test-generation/spec.md`, D2;
regra adotada também pelos módulos dos três modelos comerciais (GPT-5.4-mini, Gemini 3.8 Flash
e Claude Haiku 5.5), para manter o desenho experimental comparável entre os 4 modelos.]**

**Composição dos 3 cenários**: a única variação entre eles é o conteúdo do bloco
`<context_data>` do template — todo o resto (regras de sistema, formato de saída,
parametrização dos modelos) permanece fixo:
1. Caixa-Preta → só enunciado.
2. Caixa-Branca → só `AC_ref.cpp`.
3. Híbrida → enunciado + `AC_ref.cpp`.

**Tamanho da suíte gerada — [RESOLVIDO em 2026-11-09, seção 6, item 26]**: não há limite fixo de
casos de teste por suíte (o tamanho é variável de confusão conhecida, registrado para
a análise); a normalização adotada não é um teto, e sim a **densidade de detecção** (TDF ÷ tamanho
médio da suíte, 5.5), reportada ao lado da TDF para os 4 modelos. **Medido no SLM (execução
completa da revisão 1, 2026-10-11)**: mediana de 10 casos por suíte; `accepted` de 1 a 33 (mediana 10),
`accepted_fallback` de 5 a 54 (mediana 10), `accepted_predicted` 8 e 10.

**Versionamento das suítes geradas**: a mesma exceção de versionamento já usada para o
dataset e para os mutantes (Constitution, Princípio II, emenda 1.6.0) se aplica às
suítes de qualquer um dos 4 modelos — a identidade de uma suíte depende de uma chamada
real e não estritamente reprodutível a uma API de IA. Ao final da execução completa do
experimento, cada conjunto de suítes MAY ser compactado e commitado com manifesto
SHA-256 próprio, no mesmo formato do dataset e dos mutantes; suítes geradas durante o
desenvolvimento iterativo continuam nunca sendo versionadas. **[DECIDIDO para o SLM,
2026-09-29 — `specs/003-slm-test-generation/spec.md`, D3; a mesma regra se estende, por
consistência, às suítes dos três modelos comerciais, empacotadas em 2026-10-20
(`data/gpt_suites.zip`, `data/gemini_suites.zip`, `data/claude_suites.zip`).]**

---

### Terceiro modelo comercial: Claude **[DECIDIDO, IMPLEMENTADO E EXECUTADO, 2026-10-20 — `specs/008-claude-test-generation/spec.md`]**

Os autores decidiram acrescentar um terceiro modelo comercial, o **Claude Haiku 5.5** (Anthropic), o menor e mais barato da família, na mesma faixa do GPT-5.4-mini e do Gemini 3.8 Flash. Ele roda nas mesmas condições da feature 004 (mesmo texto-base numa única mensagem, sem memória entre pedidos, JSON no mesmo formato, até 3 tentativas por falha de formato, teto de gasto por invocação, dry-run, piloto nos 5 problemas dos pilotos, pacote/manifesto/relatório próprios e camada `claude_suites` no `cli check`) e direto sobre a revisão 2 do dataset. Com isso, o desenho passa de 2 para 3 modelos comerciais (4 modelos ao todo), e as comparações entre modelos ganham um participante. **[DECIDIDO, 2026-10-20 — clarify]** Modelo `claude-haiku-5-5` (US$ 0,10 / 0,50 por milhão de tokens de entrada/saída até 100 mil tokens de prompt, conforme a documentação da Anthropic consultada em 2026-10-20; a tabela de preço com data e fonte é fixada no plano); raciocínio adaptativo com `effort: medium` enviado explicitamente, o mesmo nível nominal dos outros dois; a mesma regra emendada da resposta sem raciocínio (até 3 em `barred/`, depois `accepted_barred`), com o sinal de falta de raciocínio definido no plano; e o mesmo teto de saída dos outros dois, 32.768 tokens. **[PLANEJADO, 2026-10-20 — `specs/008-claude-test-generation/plan.md`]** Pedido à Messages API da Anthropic pela biblioteca padrão, como os outros dois (sem SDK), com uma mensagem de usuário, `thinking: adaptive`, `effort: medium`, saída em JSON pelo mesmo schema e nenhum parâmetro de amostragem; a contagem de raciocínio é `usage.output_tokens_details.thinking_tokens` (0 ou ausente: resposta barrada); preço conferido em 2026-10-20 na página oficial: US$ 0,10 de entrada, 0,01 de entrada em cache e 0,50 de saída por milhão de tokens, para prompts de até 100 mil tokens (acima disso, outro preço; o maior prompt tem 7.459 caracteres); o piloto começa com uma única chamada para conferir que a resposta traz a contagem de raciocínio. A constitution fixa "dois LLMs comerciais": emenda 1.9.0 (só escopo e nomes) aprovada por Milena e aplicada em 2026-10-20. **[IMPLEMENTADO E MEDIDO SEM CUSTO, 2026-10-20 — `specs/008-claude-test-generation/tasks.md`]** `--model claude` implementado; a conferência dos 100 mil tokens de prompt acontece antes da chamada (nada é enviado acima do limite). Dry-run real sobre a revisão 2: 600 combinações, cerca de 826 mil tokens de entrada (razão conservadora de 3,0 caracteres por token, antes do piloto), faixa de US$ 9,91 a 29,74 (o extremo de baixo supõe uma chamada por combinação no teto de saída; o de cima, 3); os 600 pedidos salvos pelo `--save-requests` são fiéis ao dataset, sem expoente perdido. Observação da análise: o extremo de cima do dry-run supõe no máximo 3 chamadas por combinação, mas com a regra das respostas sem raciocínio uma combinação pode receber até 5 (vale para os 3 modelos comerciais); o teto real do `--confirm-spend` não muda. **[DECIDIDO E MEDIDO, 2026-10-20 — Milena]** Sem piloto separado para o Claude: a chamada de conferência (`--limit 1`, `1000_B` caixa-preta) confirmou o risco que o piloto devia cobrir (a resposta traz `thinking_tokens`: 5.165; bloco de raciocínio presente; `end_turn`; 9 testes; modelo `claude-haiku-5-5`; US$ 0,0031, igual ao calculado pela linha de preço) e, como a configuração é a da execução completa, ela segue na mesma árvore; as medidas que o piloto daria (razão caracteres/token, saída média, latência, taxa de falha) vêm do relatório da execução completa. Execução completa terminada em 2026-10-20 (ver a seção da execução completa do Claude).

### Execução completa do Gemini 3.8 Flash **[MEDIDO, 2026-10-20]**

Sobre a revisão 2 do dataset (manifesto `70d93346…`), texto-base `a0b8f42a…`. **600 combinações: 599 `accepted_predicted` e 1 `accepted_barred`** (`1201_B` caixa-preta, cuja suíte vem da 7ª de 7 respostas sem raciocínio, 12 testes); 0 `discarded_manual`. **613 chamadas**: 599 tentativas, todas aceitas na primeira (nenhuma falha de formato, nenhum corte pelo teto de saída, nenhum bloqueio de segurança), e **14 respostas sem raciocínio em 7 combinações** (2,3% das chamadas): `1009_B` caixa-preta (1), `1201_B` caixa-preta (7), `380_A` híbrido (1), `544_A` caixa-branca (1), `860_A` caixa-preta (1), `860_B` híbrido (1), `939_C` caixa-branca (2); nas outras 6, a resposta seguinte raciocinou e virou `accepted_predicted`. Tokens: 733.312 de entrada (nenhum em cache), 1.161.224 de saída, dos quais 679.722 de raciocínio. **Custo: US$ 4,90** (US$ 4,85 das tentativas, US$ 0,05 das respostas sem raciocínio), contra o extremo de baixo do dry-run de US$ 4,98. Latência média 15,9 s, mediana 13,4 s, máxima 129,9 s. Suíte: mediana de 12 testes (caixa-preta e híbrido) e 10 (caixa-branca), de 4 a 24. Modelo devolvido: `gemini-3.8-flash` em todas as 613. Pacote `data/gemini_suites.zip` (3.754.744 bytes, 1.214 arquivos, SHA-256 `1cf77d93…`), conferido por `verify` e `cli check --deep`.

### Piloto do GPT-5.4-mini aproveitado na execução completa **[DECIDIDO, 2026-10-20 — Milena; emenda de A9/FR-023a da 004]**

O piloto do GPT (5 problemas dos pilotos × 3 cenários: 15 combinações, 15 `accepted_predicted`, 15 tentativas, nenhuma resposta sem raciocínio) rodou com a configuração idêntica à da execução completa: revisão 2 do dataset (`70d93346…`), o mesmo texto-base dos outros modelos comerciais (`a0b8f42a…`), o modelo `gpt-5.4-mini-2026-03-17` e os mesmos parâmetros. Por isso as 15 combinações entram na execução completa, que continua a mesma árvore com `--resume`; o relatório do piloto fica guardado à parte (`manifests/gpt_generation_report.piloto1.json`). Diferença em relação ao Gemini, cujo piloto foi descartado porque rodou sobre a revisão 1 do dataset.

### Execução completa do GPT-5.4-mini **[MEDIDO, 2026-10-20]**

Sobre a revisão 2 do dataset (`70d93346…`), texto-base `a0b8f42a…`, com as 15 combinações do piloto aproveitadas (piloto: 15 chamadas, US$ 0,38, latência média 27,4 s; relatório em `manifests/gpt_generation_report.piloto1.json`). **600 combinações, todas `accepted_predicted`**; **601 chamadas**: 600 aceitas na primeira tentativa e 1 falha de formato (`1371_C` caixa-preta, cortada pelo teto de saída de 32.768 tokens, `incomplete: max_output_tokens`), aceita na segunda; nenhuma resposta sem raciocínio, nenhuma recusa. Tokens: 682.897 de entrada (18.944 em cache do provedor), 2.882.591 de saída, dos quais 2.642.968 de raciocínio (92%). **Custo: US$ 13,47** (caixa-preta 4,82; híbrido 4,47; caixa-branca 4,18), contra a faixa do dry-run de US$ 89,09 a 267,28, que supunha o teto de saída em toda chamada. Latência média 26,7 s, mediana 21,5 s, máxima 196,8 s. Suíte: mediana de 8 testes nos três cenários, de 1 a 18. Modelo devolvido: `gpt-5.4-mini-2026-03-17` nas 601 chamadas. Pacote `data/gpt_suites.zip` (26.247.405 bytes, 1.202 arquivos, SHA-256 `2d16c2ba…`), conferido por `verify` e `cli check --deep`.

### Execução completa do Claude Haiku 5.5 **[MEDIDO, 2026-10-20]**

Sobre a revisão 2 do dataset (`70d93346…`), texto-base `a0b8f42a…`, sem piloto separado (a chamada de conferência entrou na execução). **600 combinações: 589 `accepted_predicted`, 8 `accepted_barred` e 3 `discarded_manual`.** Caixa-branca: 200 `accepted_predicted`; caixa-preta: 194, 4 e 2; híbrido: 195, 4 e 1. **632 chamadas**: 596 tentativas (591 na primeira, 3 na segunda, 2 na terceira) e **36 respostas sem raciocínio em 16 combinações** (5,7% das chamadas, contra 2,3% no Gemini e 0 no GPT); 8 combinações chegaram a 3 delas e ficaram `accepted_barred` (`1023_A`, `1029_C`, `349_A`, `365_A` caixa-preta; `1141_A`, `53_A`, `630_J`, `981_B` híbrido). Falhas de formato: 4 cortes pelo teto de saída (3 na caixa-preta, 1 no híbrido) e 3 recusas. **Fechadas à mão pelos autores (`discarded_manual`):** `171_F` caixa-preta e híbrido, por recusas do filtro de segurança da Anthropic (`stop_reason` `refusal`, categoria `bio`; 3 tentativas na caixa-preta e 3 respostas barradas no híbrido), um falso positivo diante do enunciado em texto cifrado (problema de 1º de abril), sem modelo reserva no Haiku 5.5; e `182_B` caixa-preta, por 3 respostas cortadas no teto de 32.768 tokens (o modelo escreveu testes muito grandes e não fechou o JSON; raciocínio de 1.683 a 2.053 tokens). As 3 continuam no N e ficam sem suíte. Tokens: 1.193.446 de entrada (nenhum em cache), 1.712.955 de saída, dos quais 1.162.001 de raciocínio (68%). **Custo: US$ 0,98** (US$ 0,02 das respostas sem raciocínio), contra a faixa do dry-run de US$ 9,91 a 29,74. Latência média 12,7 s, mediana 11,0 s, máxima 89,8 s. Suíte: mediana de 11 testes (12 na caixa-branca), de 2 a 24. Modelo devolvido: `claude-haiku-5-5` nas 632 chamadas. Pacote `data/claude_suites.zip` (4.560.077 bytes, 1.236 arquivos, SHA-256 `4d71671c…`), conferido por `verify` e `cli check --deep`.

## 4. Módulo: Execução Isolada (Sandbox) e Avaliação

> **Estado (2026-11-09)**: módulo **implementado e executado sobre os 200 problemas e os 5 conjuntos
> de suítes** (`slm`, `gpt`, `gemini`, `claude` e `slm-attempt1`); o texto abaixo vai do motor e da
> regra de avaliação vigente (os três primeiros parágrafos e "Avaliação especificada") à implementação,
> ao piloto e à execução completa, com os números medidos. Os resultados oficiais (TDF, MS, TFP...) são
> da seção 5.

**Pipeline de compilação e motor de execução**: é o mesmo motor construído e verificado
no módulo do dataset (seção 1.4), sem alterações — GCC, flags originais do Codeforces
(exceto `-Wl,--stack`, substituído pelo limite de pilha de 256 MiB em tempo de execução),
fallback de padrão gnu++20→17→14→11. Nenhum código do dataset chega a esta etapa sem já
ter passado por esse motor com o veredito esperado. Os limites de pilha e memória são
aplicados por rlimits e o tempo é medido como tempo de CPU; ver as regras operacionais em 1.4.

**Injeção de testes**: as suítes geradas pela IA (pares entrada/saída esperada) são
injetadas via `stdin` no binário compilado, dentro de sandbox com limites de
tempo/memória do próprio problema (kernel Linux).

**Avaliação em curto-circuito** (texto original da metodologia do TCC, mantido com a ressalva
do próximo bloco): os casos de teste gerados são aplicados sequencialmente a cada código-alvo (AC,
WA ou mutante). No primeiro teste que o código falhar, o veredito é registrado imediatamente como
reprovado — os testes restantes daquele arquivo são abortados (economia de recursos). Aprovação
(AC) só é concedida se o código sobreviver a 100% da suíte gerada pela IA. **Regra vigente**: o
curto-circuito vale só para WAs e mutantes; contra o `AC_ref` todos os testes rodam (ver "Avaliação
especificada", adiante, e seção 7, item 43).

**Saída**: registro CSV consolidando o comportamento de cada código frente a cada suíte gerada — é o
insumo direto para o cálculo das métricas (seção 5). Implementado como `results.csv` de cada
conjunto, derivado dos JSON por combinação (ver "Implementação", adiante).

**Avaliação especificada [ESPECIFICADA em 2026-11-04 e IMPLEMENTADA e EXECUTADA, como descrito mais adiante — `specs/009-suite-evaluation/spec.md`;
requisitos da seção F da proposta de métricas (consolidada em 5.5 a 5.10), confirmada pelos autores sem C.5 e C.6]**:
o curto-circuito acima **continua valendo para WAs e mutantes**, mas **não para o `AC_ref`**:
contra ele todos os testes da suíte são executados e se grava, por teste, o veredito (`passou`,
`saída diferente`, `erro de execução` com o tipo RE/TLE/MLE) e a **saída real** do `AC_ref`. Cada
WA e mutante tem a detecção gravada sob **dois oráculos**: o declarado pela IA e o **corrigido**
(saída esperada trocada pela saída real do `AC_ref` na mesma entrada, só nos testes em que o
`AC_ref` não deu erro) — base de TDF\*/MS\*/Δ_oráculo. Por combinação, ficam os **conjuntos
exatos** de WAs e mutantes detectados (fecha o "onde registrar" da pendência 3). Combinação sem
suíte (`discarded_manual`) é gravada como "sem suíte", sem execução. O modelo local é
avaliado também pela 1ª tentativa isolada (sem o filtro das 12 tentativas), com resultado
separado da suíte final. A saída é por combinação (com esquema versionado), mais a
tabela consolidada, um relatório por modelo, um pacote com manifesto por modelo e uma camada nova
no `cli check`. **[DECIDIDO, 2026-11-04 — Milena]** Instabilidade de margem: quando o `AC_ref`
dá erro de execução num teste, ele é executado mais 2 vezes nesse teste e o erro só vale se
aparecer nas 3 execuções; senão o teste fica marcado como instável e conta no relatório (evita
inflar o TFP com ruído do ambiente, o mesmo tipo de instabilidade medida na seção 1.4). A mesma
regra vale para WAs e mutantes (clarify de 2026-11-04): uma detecção por erro de execução só vale
se o erro aparecer nas 3 execuções; senão o teste fica marcado como instável e o alvo segue para os
próximos testes; `passou` e `saída diferente` não se repetem. **Piloto obrigatório** (feito, ver adiante) antes da
execução completa: os 5 problemas dos pilotos × 4 modelos × 3 cenários (60 combinações), com
conferência manual e decisão dos autores registrada; se nada mudar, a execução completa o
reaproveita (mesmo padrão dos módulos anteriores).
**Implementação [IMPLEMENTADO, 2026-11-04 — `specs/009-suite-evaluation/plan.md`, `research.md` R1–R11; antes PLANEJADO no mesmo dia]**:
pacote `src/evaluation/` (`python -m evaluation run|report|package|verify`, `run` no serviço
`sandbox`). Unidade de trabalho = o problema: cada programa (AC, 100 WAs, 100 mutantes) é compilado
**uma vez** e executado contra todas as suítes do problema (até 15), um alvo de cada vez (R1, R4).
Os dois oráculos de um alvo são decididos numa **passada única** pelos testes, com resultado
idêntico ao de duas passadas com curto-circuito (R3). Cinco conjuntos de avaliação, cada um com
`run.json` (entradas congeladas por hash), pasta `problems/<id>/<cenário>.json`, tabela consolidada
`results.csv` (o "registro CSV" previsto acima, derivado dos JSON) e pacote próprio
`data/evaluation_<conjunto>.zip` com manifesto: `slm`, `gpt`, `gemini`, `claude` e
`slm-attempt1` (R6, R7, R8). Portões: `selfcheck` do motor e `cli check --deep` (R11). Divergências do plano na implementação: (a) `package` refaz o `results.csv` e o relatório antes de empacotar, em vez de recusar quando estão desatualizados, para que o pacote seja sempre descrito por eles; (b) o relatório de uma `--output-dir` que não é a padrão (conferência, piloto guardado) fica ao lado dela, nunca em `manifests/`; (c) o `elapsed_s` de cada combinação é o tempo de executar os testes, sem a compilação, que é feita uma vez por problema para todas as suítes. **Conferência [MEDIDO, 2026-11-04 — Milena, fora do piloto, em `data/evaluation-conf/`, não versionada]**: `1000_B` com as 15 suítes (5 conjuntos × 3 cenários) levou 489 s com `--workers 2`, quase todo em compilar os 201 programas; os portões (`selfcheck` e `cli check --deep`) levaram cerca de 9 min. Nenhum alvo deixou de compilar, nenhum teste instável. O AC foi reprovado em 2 das 3 suítes do modelo local, nas 3 do Gemini e em nenhuma do GPT e do Claude; no Gemini, os WAs detectados caíram de 300 (oráculo declarado) para 247 (corrigido) e os mutantes de 300 para 230, o efeito que o Δ_oráculo mede. Estimativa ingênua da execução completa (200 problemas, mesma máquina, 2 trabalhadores): ordem de 13 h; o piloto mede de verdade (FR-021). **Piloto [MEDIDO E DECIDIDO, 2026-11-04/05 — Milena]**: os 5 problemas dos pilotos (`1000_B`, `1005_C`, `1008_B`, `1_B`, `61_B`) nos 5 conjuntos, 75 combinações, em `data/evaluation/` (interrompido por um desligamento e retomado sem perda). Nenhum alvo sem compilar, nenhum erro de execução do AC, nenhum teste instável, nenhum teste excluído do oráculo corrigido; maior saída do AC 43 bytes. AC reprovado: SLM 6 de 15, GPT 1, Gemini 11, Claude 0, 1ª tentativa do SLM 9 de 13 (2 sem suíte). WAs detectados, declarado → corrigido: SLM 1.276 → 1.095, GPT 1.160 → 1.151, Gemini 1.439 → 1.259, Claude 1.224 → 1.224, 1ª tentativa 1.192 → 907; mutantes: SLM 1.370 → 1.315, GPT 1.292 → 1.292, Gemini 1.458 → 1.332, Claude 1.331 → 1.331, 1ª tentativa 1.208 → 1.151. Decisão (Milena, 2026-11-05): seguir para a execução completa na mesma pasta, retomando o piloto (FR-021); a conferência manual da amostra é feita no dashboard em paralelo, e um problema encontrado nela leva a refazer a avaliação. **Execução completa [MEDIDO, 2026-11-04 a 2026-11-06; fechamento em 2026-11-09 — revisão `893505a`]**: os 200 problemas nos 5 conjuntos, retomando o piloto, na mesma pasta; o código executado é o do commit `893505a` (nenhum arquivo de `src/evaluation` mudou depois do início da execução). `report`, `package` e `verify --extracted` dos 5 conjuntos e `cli check --deep` com `Resultado: OK (0 falha(s), 0 aviso(s))`; cada pacote tem 602 arquivos (600 combinações, `run.json` e `results.csv`): `slm` 3,1 MiB, `gpt` 1,9, `gemini` 1,9, `claude` 1,9, `slm-attempt1` 2,8. Nenhum alvo sem compilar. Combinações sem suíte: Claude 3 (`discarded_manual`), 1ª tentativa do SLM 53 (`attempt_without_tests`). **AC reprovado** (falsos positivos, por combinação com suíte): SLM 183 de 600, GPT 121 de 600, Gemini 329 de 600, Claude 104 de 597, 1ª tentativa do SLM 255 de 547. Testes do AC com saída diferente / com erro de execução: SLM 806 / 4 (3 RE, 1 TLE), GPT 183 / 3 (3 TLE), Gemini 736 / 0, Claude 149 / 7 (5 RE, 2 TLE), 1ª tentativa 1.174 / 5 (3 RE, 2 TLE); testes excluídos do oráculo corrigido: 4, 3, 0, 7 e 5. **WAs detectados, declarado → corrigido** (de 60.000 por conjunto): SLM 46.698 → 42.898, GPT 51.972 → 50.838, Gemini 57.315 → 54.083, Claude 52.730 → 51.550, 1ª tentativa 44.961 → 38.533 (de 54.700); **mutantes**: SLM 55.774 → 54.555, GPT 57.260 → 56.627, Gemini 59.140 → 58.213, Claude 57.635 → 57.159, 1ª tentativa 51.174 → 49.628. Testes instáveis (um erro que não se repetiu): AC 1 (Claude); alvos, WA/mutante: SLM 4/8, GPT 4/13, Gemini 7/14, Claude 4/6, 1ª tentativa 6/5. Maior saída do AC: 3,1 MB (SLM e 1ª tentativa; os comerciais até 568 bytes). Tempo de executar os testes (sem a compilação), somado por conjunto: de 6.381 s (1ª tentativa) a 10.750 s (Claude); o tempo de parede total não foi medido, porque a execução teve pausas. São contagens brutas; as métricas oficiais (TDF, MS, TFP e as demais) são calculadas pelo módulo de métricas.

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

**[DECIDIDO, 2026-09-23]** O MS final de um cenário é a média aritmética entre os problemas que
têm mutantes completos — normalmente os 200, mas potencialmente menos, se algum problema não
fechar 100 mutantes válidos mesmo após ordem superior (seção 2.4; caso raro ou inexistente pela
estimativa de pesquisa, mas registrado com alerta explícito quando ocorrer). TDF (5.1) e TFP
(5.3) continuam sempre sobre os 200 problemas do dataset, sem essa exceção — só o denominador do
MS pode variar.

**[MEDIDO, 2026-09-25]** Na geração real dos mutantes nenhum problema foi excluído (0 alertas):
os 200 problemas têm 100 mutantes, então o MS é a média sobre os 200 (seção 2.11).

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

**[DECIDIDO E IMPLEMENTADO, 2026-11-04/09 — `specs/010-metrics/`; proposta B.3]**: `D(R)`,
`D(C)` e `D(H)` são a **união, nos 200 problemas do cenário, dos pares (problema, WA)
detectados** (forma agregada, a oficial): como `W_total` e `M` são constantes (100), é a mesma
convenção que TDF e MS já seguem, e o denominador só zera se o cenário inteiro não detectar
nenhum WA. Junto, uma **visão por problema** só para diagnóstico: mediana, intervalo
interquartil e quantos problemas têm IIC positivo, negativo e zero, **excluindo e contando** os
problemas com denominador zero. O IIC não tem teto (passa de 100% se o híbrido pegar mais WAs
novos do que a base inteira) e tem piso −100%. É calculado também pelo oráculo corrigido (5.5),
numa coluna à parte, para nenhum ganho de contexto vir de gabarito errado. Os conjuntos vêm da
avaliação (seção 4), e a macrocategoria permite o corte (5.7).

### 5.1–5.3: regras de borda **[DECIDIDO, 2026-11-04 — proposta B.1, B.2, B.4]**

- **Combinação sem suíte** (`discarded_manual`; e, na 1ª tentativa do SLM, sem entrada
  aproveitável): conta **0%** em TDF e MS (o modelo falhou em produzir a suíte) e **não** conta como
  falso positivo. A **TFP oficial mantém N = 200** e é sempre reportada com o número de
  combinações sem suíte e com a **TFP entre as combinações com suíte** (visão secundária), para a
  ausência de teste não parecer acerto.
- **TC — Taxa de Cobertura** = combinações com suíte ÷ 200 × 100, ao lado de TDF/MS/TFP.
- Todas as métricas das tabelas estão em %, inclusive o MS (DM ÷ M × 100).

### 5.5 Métricas complementares **[DECIDIDO, 2026-11-04 — proposta C.1 a C.4; sem C.5 e C.6]**

- **TDF\* e MS\*** — as mesmas de 5.1/5.2, com a saída esperada de cada teste trocada pela saída
  real do `AC_ref` na mesma entrada (as entradas continuam as da IA; testes em que o AC falha ficam
  fora). **Δ_oráculo = TDF − TDF\*** (e MS − MS\*): quanto da detecção depende de a IA ter acertado o
  gabarito. É o que torna comparáveis o SLM (oráculo por execução) e os comerciais (por predição).
- **TFP por teste e por causa** — testes que reprovam o AC ÷ total de testes, separando `oráculo`
  (o AC roda e dá outra saída: a IA errou o valor) de `entrada_inválida` (o próprio AC falha: a
  entrada está fora das restrições).
- **CPD — Custo por Detecção** — US$ do conjunto × cenário (todos os pedidos, inclusive repetidos e
  barrados) ÷ WAs (e ÷ mutantes) detectados, só dos comerciais; o SLM é reportado em *tokens* e
  tempo, **nunca convertido para US$**.
- **Densidade de detecção** = TDF ÷ tamanho médio das suítes: separa "detecta mais porque o
  contexto é melhor" de "detecta mais porque gera mais testes" (fecha a pendência 26).
- **Fora do escopo**: complementaridade entre modelos (C.5) e IIC sobre mutantes (C.6).

### 5.6 Camada estatística **[DECIDIDO, 2026-11-04 — proposta D; `specs/010-metrics/research.md` R3]**

Pareada pelos 200 problemas (uma combinação sem suíte entra com o valor de 5.1–5.3). Mais de dois
grupos (os 3 cenários de um conjunto; os 4 modelos de um cenário): **Friedman** e, se p < 0,05,
**Wilcoxon pareado** nos pares com **Holm-Bonferroni**; a 1ª tentativa do SLM contra cada modelo,
Wilcoxon com Holm. A **TFP** (binária por problema) só em pares, com **McNemar exato** (binomial
bilateral nos pares discordantes) e Holm, sem teste global. Tamanho de efeito **A12 de
Vargha-Delaney** e **delta de Cliff** (2·A12 − 1) em toda comparação par a par. α = 0,05.

### 5.7 Cortes **[DECIDIDO, 2026-11-04 — proposta E]**

Toda métrica é recalculável por **macrocategoria** e por **status da suíte** (sempre com o número de
problemas do corte; nunca um problema só); a **1ª tentativa do SLM** (`slm-attempt1`) entra como um
conjunto a mais, para a comparação "uma chamada contra uma". Não são métricas novas.

### 5.8 Figuras **[DECIDIDO E IMPLEMENTADO, 2026-11-09 a 2026-11-13 — Milena; `specs/010-metrics/` FR-017 e `specs/012-dashboard-storytelling/`; estado final em 2026-11-13]**

**Estado final.** As figuras são **desenhadas sob demanda a partir das tabelas** de `data/metrics/`;
**nenhuma figura fica no repositório nem em `data/metrics.zip`** (o pacote tem só as seis tabelas e
o `run.json`). Há duas formas de obtê-las, com o mesmo desenho (Altair, exportado pelo vl-convert; o
matplotlib saiu do projeto):

- **No painel (5.11)**: gráficos interativos, com o valor escrito em cada barra, que seguem os filtros
  da barra lateral e o tema claro ou escuro; cada um se salva em **PNG ou SVG pelo menu do próprio
  gráfico** ("…"). Não há botão de download de figura nem PDF na página (o botão "Baixar figura" dos
  cartões e os botões PNG/SVG/PDF da emenda de 2026-11-09 saíram em 2026-11-13).
- **Pelo comando** `python -m metrics figures` (opcional): grava em `data/metrics/figures/`, em PNG,
  SVG e PDF, **12 figuras** — `scoreboard` e `scoreboard_scenarios` (placar e placar por cenário),
  `tdf_by_model`, `tdf_declared_vs_corrected`, `ms_declared_vs_corrected`, `tradeoff` (troca detecta ×
  erra), `tfp_by_cause`, `scenario_shift` (variação entre cenários), `iic_diverging`,
  `iic_distribution` (caixa do IIC por conjunto, de diagnóstico), `cost_per_detection` e
  `choice_guide` (guia de escolha). Filtros do comando: `--macrocategoria`, `--rating`, `--status`,
  `--set`, `--scenario` e `--figure`. Com filtro, o filtro vai no subtítulo e no nome do arquivo
  (por exemplo, `scoreboard__rating-1600.png`), para toda figura se refazer pelo comando. As figuras
  do texto do TCC saem daqui. PNG e SVG saem iguais byte a byte a cada execução; o PDF tem o mesmo
  desenho, mas o vl-convert muda a ordem interna dos objetos de fonte (medido: 4 variantes em 20),
  então ele não é igual byte a byte.

**Regras de desenho que valem.**
- **O título de cada figura é a conclusão do recorte, gerada por regra** (`metrics.story`, modelos de
  frase numa tabela única), e muda com os filtros. Sem filtro, por exemplo: "Nenhuma IA venceu em
  todos os critérios"; "Gemini encontra 90,1% das falhas reais"; "Gemini detecta 97,0% dos mutantes";
  "Quem mais detecta também mais erra o gabarito" (Gemini, 1º em TDF\*, é o último em TFP: 54,8%);
  "O cenário muda a detecção em até 4,3 pontos (Claude); Gemini quase não muda"; "Juntar requisito e
  código muda a detecção em no máximo 4,9% (SLM 1ª tentativa, + código)" pelo gabarito do AC (8,2%,
  SLM, pelo da IA; o sinal do SLM e da 1ª tentativa em "+ código" inverte entre os gabaritos);
  "Claude detecta 1.000 falhas por US$ 0,019, 14× menos que GPT". O líder tem uma cor de destaque
  única.
- **O gabarito do AC é o padrão** nas figuras de detecção (TDF\*, MS\*); `tdf_by_model` e
  `ms_declared_vs_corrected` são barras ordenadas pelo gabarito do AC, com um traço no valor pelo
  gabarito da IA, na média dos cenários do recorte; `cost_per_detection` são barras ordenadas em US$
  por 1.000 WAs detectados.
- **Legibilidade**: tema claro ou escuro; paleta categórica própria, validada para daltonismo e
  contraste (azul, laranja, verde-água; a cor segue a série, nunca a posição; o par divergente do IIC
  é azul ↔ vermelho); texto em tons de tinta, nunca na cor da série; as figuras com muitas barras
  ganham um painel por cenário, em largura cheia; "sem suíte" é cinza; o IIC é uma caixa por conjunto
  sem os pontos extremos (que ficam na tabela) e com a mediana escrita; a TFP por causa mostra só o
  total de cada barra (a divisão fica na legenda e no tooltip); as combinações com o AC reprovado
  são marcadas por um vermelho translúcido na página de comparações.
- **Troca detecta × erra**: um ponto por conjunto (a média dos cenários do recorte, os mesmos números
  do placar), com o nome escrito ao lado; o detalhe por cenário fica no guia de escolha; a região ideal
  é a das medianas das IAs do recorte. As anotações longas das barras (quanto o líder está à frente;
  quem mais perde com o gabarito corrigido) ficam como notas sob o gráfico.
- **Custo não se divide por problema**: com filtro por problema, macrocategoria, rating ou status, a
  figura de custo mostra o valor de todos os problemas e diz isso no subtítulo.
- **Placar**: 6 critérios (TDF\*, MS\*, TFP, Δ_oráculo, TC e custo por 1.000 WAs), média dos cenários,
  sem teste estatístico; o critério TC tem 4 conjuntos empatados em 100%. O **placar por cenário** tem
  uma linha por IA e cenário e a posição dentro do mesmo cenário; o título diz em quantos dos 6
  critérios o 1º lugar muda com o cenário.

A história datada dessas decisões (as emendas de 2026-11-09 a 2026-11-13, inclusive o que mudou de
ideia, como a presença das figuras no pacote e o download na página) está na seção 8.

### 5.9 Resultados **[MEDIDO, 2026-11-09 — `python -m metrics compute`, pacote `data/metrics.zip`]**

Sobre a avaliação completa (seção 4). Somas de detectados idênticas aos relatórios da avaliação e
custo total de cada comercial idêntico ao relatório de geração (GPT US$ 13,47; Gemini 4,90; Claude
0,98). Em %:

| Conjunto | Cenário | TDF | TDF\* | MS | MS\* | TFP | TC |
|---|---|---|---|---|---|---|---|
| SLM | caixa-preta | 82,74 | 69,90 | 94,25 | 91,77 | 55,50 | 100 |
| SLM | caixa-branca | 74,77 | 72,27 | 90,79 | 88,83 | 16,50 | 100 |
| SLM | híbrido | 75,98 | 72,33 | 93,83 | 92,19 | 19,50 | 100 |
| GPT | caixa-preta | 85,88 | 84,40 | 95,82 | 94,93 | 20,00 | 100 |
| GPT | caixa-branca | 88,92 | 86,67 | 95,64 | 93,95 | 25,50 | 100 |
| GPT | híbrido | 85,06 | 83,12 | 94,84 | 94,25 | 15,00 | 100 |
| Gemini | caixa-preta | 95,20 | 90,00 | 98,64 | 97,10 | 54,50 | 100 |
| Gemini | caixa-branca | 95,62 | 89,75 | 98,64 | 96,82 | 55,00 | 100 |
| Gemini | híbrido | 95,75 | 90,67 | 98,42 | 97,14 | 55,00 | 100 |
| Claude | caixa-preta | 86,11 | 83,76 | 95,39 | 94,36 | 18,00 | 99,0 |
| Claude | caixa-branca | 89,71 | 88,03 | 96,87 | 96,22 | 17,50 | 100 |
| Claude | híbrido | 87,83 | 85,96 | 95,92 | 95,22 | 16,50 | 99,5 |
| SLM 1ª tentativa | caixa-preta | 80,43 | 62,36 | 85,85 | 83,06 | 65,50 | 90,5 |
| SLM 1ª tentativa | caixa-branca | 69,81 | 64,91 | 83,16 | 79,77 | 25,00 | 91,0 |
| SLM 1ª tentativa | híbrido | 74,57 | 65,39 | 86,86 | 85,31 | 37,00 | 92,0 |

**Quantos alvos a IA matou**: cada WA e cada mutante conta uma vez, morto se algum teste da suíte
o reprovou (a avaliação para no primeiro teste que o reprova). São 100 WAs e 100 mutantes por
problema, então 20.000 de cada por conjunto × cenário; a TDF é *WAs mortos ÷ 20.000* e o MS,
*mutantes mortos ÷ 20.000* (as combinações sem suíte contam 0). Colunas `WA_killed`,
`WA_killed_star`, `WA_total`, `mutants_killed`, `mutants_killed_star` e `mutants_total` de
`metrics.csv` (acrescentadas em 2026-11-09, a pedido da Milena):

| Conjunto | Cenário | WAs mortos | WAs mortos\* | mutantes mortos | mutantes mortos\* |
|---|---|---|---|---|---|
| SLM | caixa-preta | 16.548 | 13.980 | 18.851 | 18.353 |
| SLM | caixa-branca | 14.954 | 14.453 | 18.158 | 17.765 |
| SLM | híbrido | 15.196 | 14.465 | 18.765 | 18.437 |
| GPT | caixa-preta | 17.175 | 16.880 | 19.164 | 18.986 |
| GPT | caixa-branca | 17.785 | 17.333 | 19.127 | 18.790 |
| GPT | híbrido | 17.012 | 16.625 | 18.969 | 18.851 |
| Gemini | caixa-preta | 19.040 | 18.000 | 19.729 | 19.420 |
| Gemini | caixa-branca | 19.124 | 17.949 | 19.728 | 19.364 |
| Gemini | híbrido | 19.151 | 18.134 | 19.683 | 19.429 |
| Claude | caixa-preta | 17.222 | 16.752 | 19.077 | 18.871 |
| Claude | caixa-branca | 17.942 | 17.606 | 19.374 | 19.245 |
| Claude | híbrido | 17.566 | 17.192 | 19.184 | 19.043 |
| SLM 1ª tentativa | caixa-preta | 16.086 | 12.472 | 17.170 | 16.613 |
| SLM 1ª tentativa | caixa-branca | 13.961 | 12.982 | 16.631 | 15.954 |
| SLM 1ª tentativa | híbrido | 14.914 | 13.079 | 17.373 | 17.061 |

Achados para a discussão (todos em `data/metrics/`):
- **Δ_oráculo**: maior no SLM caixa-preta (TDF − TDF\* = 12,8 pontos) e na 1ª tentativa do SLM
  caixa-preta (18,1), seguido do Gemini (5,1 a 5,9); GPT e Claude entre 1,5 e 2,4.
- **Cenários dentro do SLM**: a TDF difere entre os cenários (Friedman p < 0,001), mas a **TDF\*
  não** (p = 0,75): a vantagem aparente da caixa-preta do SLM vem do gabarito errado, não de
  detectar mais falhas reais. No GPT e no Claude, os cenários diferem também na TDF\* (p < 0,001);
  no Gemini, em nenhuma das duas.
- **Modelos**: a TDF\* difere entre os 4 modelos nos 3 cenários (Friedman p < 0,001); todos os comerciais
  superam o SLM nos 3 cenários (Holm p < 0,001); Gemini > Claude na caixa-preta e no híbrido (na
  caixa-branca, sem diferença significativa, Holm p = 0,07); GPT × Claude só difere no híbrido
  (Holm p < 0,001).
- **TFP**: Gemini reprova o AC em 54,5–55% dos problemas, SLM caixa-preta em 55,5%; GPT 15–25,5% e
  Claude 16,5–18%; quase todos os testes que reprovam o AC são de causa `oráculo` (a IA errou a
  saída); `entrada_inválida` é rara (0 a 7 testes por conjunto × cenário).
- **IIC** (agregado, oráculo declarado): pequeno em todos os conjuntos (de −8,2% no SLM, híbrido
  sobre caixa-preta, a +6,8% na 1ª tentativa do SLM, híbrido sobre caixa-branca); pelo oráculo
  corrigido, o sinal do SLM inverte (IIC_cod +3,5%): a "perda" do híbrido no SLM também vem do
  gabarito errado da caixa-preta.
- **Densidade**: de 7,7 a 11,4 de TDF por teste; o GPT tem as suítes mais curtas (≈ 8 testes) e a
  maior densidade.
- **CPD** (por WA detectado, oráculo declarado): Claude US$ 0,000018–0,000020, Gemini
  0,000080–0,000090, GPT 0,000235–0,000281.

**Suítes `accepted_barred` ficam nas métricas [DECIDIDO E MEDIDO, 2026-11-12 — Milena]**: a decisão de
2026-10-20 (seção 3) deixou em aberto analisar à parte ou excluir as 9 suítes que vêm de respostas
sem raciocínio (Gemini `1201_B` caixa-preta; Claude `1023_A`, `1029_C`, `349_A`, `365_A`
caixa-preta e `1141_A`, `53_A`, `630_J`, `981_B` híbrido; de 7 a 24 testes cada; 8 das 9 reprovam o
AC). Decidido: **ficam incluídas** em todas as métricas, como suítes que a ferramenta de fato
entregou, e o número delas é relatado (no placar do painel e no texto). Motivos: excluí-las
melhoraria os números do Claude justamente onde ele errou; tirá-las do N desfaria o pareamento dos
200 problemas nos testes estatísticos; contá-las como "sem suíte" (0%) seria injusto no sentido
contrário. Medido o efeito de excluí-las (N reduzido): TFP do Claude caixa-preta 18,0% → 16,3% e
híbrido 16,5% → 15,3%; TDF\* do Claude caixa-preta 83,76% → 83,63% e híbrido 85,96% → 85,76%; Gemini
caixa-preta TFP 54,5% → 54,3%, TDF\* 90,00% → 89,95%. **Nenhum 1º lugar muda** (no híbrido, o GPT,
com TFP de 15,0%, continua à frente do Claude mesmo sem as barradas); o painel recalcula essa
conferência para o recorte ativo e a escreve sob o placar.

**Tempos e reprodutibilidade dos comandos [MEDIDO, 2026-11-14 — container, avaliação completa]**:
`metrics verify --extracted` em cerca de 6 s; `metrics compute` em cerca de 33 s no total;
`metrics figures --figure scoreboard --format png` em cerca de 7 s; `metrics package` **idempotente**
(zip e manifesto com o mesmo SHA-256 antes e depois de rodar de novo: zip `ec199912…`, manifesto
`bf8f5d54…`). São tempos de uma execução, não uma garantia.

### 5.10 Rastreabilidade: pergunta de pesquisa → comparação → métrica → onde está a resposta **[DECIDIDO, 2026-11-04 — proposta G; estado em 2026-11-14]**

Cada pergunta da seção 0 se liga a uma comparação, às métricas que a respondem e à tabela ou à
página do painel onde o número está. O que a proposta de 2026-11-04 marcou como entregável e o que
ficou de fora aparece na última coluna (sem deixar item "a fazer"):

| Comparação | Métricas | Pergunta | Estado e onde está |
|---|---|---|---|
| Caixa-preta × caixa-branca × híbrida | TDF, MS, TFP (e TDF\*, MS\*) | Q1, Q2, Q3 | **feito** — 5.9; `metrics.csv`, `stats.csv` (Friedman por conjunto); painel, página "As métricas" |
| Efeito de juntar requisito e código | IIC (agregado, com o oráculo declarado e com o corrigido) e a visão por problema | Q4 | **feito** — 5.4 e 5.9; `iic.csv`; painel, "As métricas" e, para um problema, "Rastreabilidade" |
| SLM × GPT-5.4-mini × Gemini 3.8 Flash × Claude Haiku 5.5 | todas, mais custo por detecção, *tokens* e tempo | Q5 | **feito** — 5.5 a 5.9; `metrics.csv`, `cost.csv`, `stats.csv`; placar e guia de escolha |
| Qualidade das entradas × qualidade do oráculo | TDF/MS × TDF\*/MS\* (Δ_oráculo) | Q5, de forma justa entre SLM e comerciais | **feito** — 5.5 e 5.9 |
| Causa da alucinação | TFP por teste, separada em `oráculo` e `entrada_inválida` | aprofunda Q3 e Q5 | **feito** — 5.5 e 5.9 (a causa `oráculo` responde por quase todos os testes que reprovam o AC) |
| Por macrocategoria (`matematica`, `estrutural_otimizacao`, `logica_direta`) e por rating | qualquer métrica, agrupada | Q1 e recomendações por categoria | **feito** — 5.7; colunas de corte de `metrics.csv`; filtros do painel e de `metrics figures` |
| Por status da suíte do SLM (`accepted`, `accepted_fallback`, `accepted_predicted`) | TDF, MS, TFP, estratificado | validade interna do SLM | **feito** — 5.7 |
| 1ª tentativa do SLM, sem filtro × modelos comerciais | TDF, MS, TFP | Q5, de igual para igual | **feito** — conjunto `slm-attempt1` (seção 4 e 5.9) |
| Entre modelos, no mesmo cenário | Jaccard e Gain (complementaridade, C.5 da proposta) | Q5, potencial de comitê de modelos | **fora do escopo** (5.5): não calculada |
| IIC sobre mutantes (C.6 da proposta) | IIC com os mutantes mortos no lugar dos WAs | robustez do achado de Q4 | **fora do escopo** (5.5): o IIC existente usa só os WAs (falhas reais) |
| A diferença é real? | Friedman, Wilcoxon pareado, McNemar exato (TFP), Holm, A12 e delta de Cliff | sustenta qualquer "X é melhor que Y" | **feito** — 5.6; `stats.csv` |

Consequência para o texto: a afirmação "um comitê de modelos pegaria mais falhas que um modelo só"
**não tem base medida** (o Jaccard não foi calculado) e não deve aparecer no TCC como resultado;
quando muito, como trabalho futuro.

**Limitação a declarar no texto: oráculo por execução (SLM) × por predição (comerciais) [DECIDIDO,
2026-11-04 — proposta H; registrada como item 42 da seção 7].** A diferença de processo não é uma
escolha arbitrária: o SLM escreve uma solução em Python, executada e validada nos testes públicos,
e é ela que dá a saída esperada; os três comerciais escrevem a saída direto, sem executar nada. Os
autores relataram (2026-11-09) que o formato de predição direta dos comerciais foi tentado no SLM e
descartado por ser inutilizável (as saídas previstas erravam muito; o Qwen2.5-Coder é treinado para
escrever código, não para prever a saída de um programa). A redação para o TCC deve dizer, em
termos simples: (1) SLM e comerciais diferem na origem do oráculo; (2) a diferença não é incidental,
porque a alternativa uniforme foi testada e descartada; (3) TDF\*, MS\* e Δ_oráculo (5.5) existem
para dar uma leitura que isola esse efeito.

**O que está e o que não está medido sobre esse "porquê"** (nada aqui é estimado):
- **Medido, indiretamente.** A predição do SLM existe como fase 4 da política de tentativas
  (`accepted_predicted`) e foi usada em **1 das 600** combinações da execução final. Pelo gabarito
  do AC, a detecção do SLM cai com o gabarito errado da IA: TDF − TDF\* = **12,8 pontos** na
  caixa-preta (82,74% → 69,90%) e **18,1** na 1ª tentativa caixa-preta, contra 1,5 a 2,4 no GPT e
  no Claude e 5,1 a 5,9 no Gemini (5.9); e o SLM caixa-preta reprova o AC em 55,5% dos problemas
  (TFP), contra 15 a 25,5% no GPT e no Claude. Esses números são do SLM com oráculo por execução,
  ou seja, **não são** a taxa de erro da predição direta do SLM; mostram só que o gabarito da IA
  pesa muito nos resultados e que o contraste Δ_oráculo é necessário.
- **Critério de projeto do piloto 4 (2026-10-05).** Se o 14B deixasse mais de ≈ 20% das combinações
  sem suíte, discutir fazer o SLM prever as saídas como os comerciais; no fim, a política de 5 fases
  deixou 0 combinações sem suíte (504 `accepted`, 95 `accepted_fallback`, 1 `accepted_predicted`), e
  a predição ficou só como reserva.
- **Não registrado.** A taxa de acerto, o formato e a amostra do teste de predição direta do SLM que
  levou ao descarte **não estão em nenhum artefato do repositório** (sem relatório, sem pacote). A
  frase "inutilizável" é, por ora, **afirmação dos autores**. Para o TCC, ou os autores registram o
  que viram (número de problemas, taxa de saídas certas), ou a frase fica como relato de
  experiência, sem número (**decisão pendente dos autores**, seção 6).

### 5.11 Painel de exploração dos resultados **[DECIDIDO E IMPLEMENTADO, 2026-11-12 a 2026-11-13 — Milena; `specs/011-results-dashboard/` e `specs/012-dashboard-storytelling/`; estado final descrito aqui, a história datada na seção 8]**

O painel (`python -m dashboard serve`, Streamlit, só leitura; uso e comandos em `src/dashboard/README.md`)
é a forma de **explorar** os números das seções 5.1 a 5.9 e de **conferir cada um na fonte**. Ele não
calcula métrica nova (os números vêm de `data/metrics/` e da avaliação), não executa código, não chama
IA e não grava nada. O roteiro que o originou (`docs/roteiro-painel.md`, rascunho de 2026-11-12) foi
consolidado nesta seção; onde o roteiro e o painel construído divergem, vale o que está abaixo.

**Narrativa.** Contexto: quatro IAs geraram testes para 200 problemas do Codeforces em 3 cenários, e
cada suíte foi executada contra 20.000 falhas reais (WAs) e 20.000 mutantes. Pergunta: qual IA gera os
melhores testes, e em quê (detectar falhas, não errar o gabarito, custar pouco, aproveitar o
contexto)? Conclusão que os números sustentam (a tese do TCC, a ser confirmada pelos autores): **nenhuma
IA vence em tudo** — o Gemini detecta mais, mas reprova o código correto em mais da metade dos
problemas; Claude e GPT erram bem menos o gabarito, o Claude custa cerca de 14× menos que o GPT, e o
cenário de contexto muda pouco o resultado. Abertura do painel: "quem mais detecta também mais erra o
gabarito". Público: a banca, na defesa ao vivo, e leitores pelo link público.

**As quatro páginas, nesta ordem** (a ordem do roteiro de 2026-11-12 era experimento → avaliação →
métricas; passou a esta em 2026-11-12, mesmo dia, com a página de rastreabilidade):

| Página | O que é |
|---|---|
| **O experimento** (abre primeiro) | o contexto: problemas, falhas e mutantes, IAs × cenários, suítes, testes gerados (24.274 sem filtro) e gasto (US$ 19,35 sem filtro: GPT 70%, Gemini 25%, Claude 5%; o modelo local à parte, com as horas de modelo, sem custo em dinheiro); gráficos de rating, macrocategoria, suítes por IA e status, testes por suíte e gasto; os números de cada gráfico no fim da página |
| **As métricas** | quem se saiu melhor em cada critério: placar e placar por cenário, falhas reais (TDF\*) e mutantes (MS\*), troca "detecta × reprova o código correto", contexto (variação entre cenários e IIC, com seletor de gabarito), custo, o guia de escolha e, no fim, as tabelas oficiais, os testes estatísticos e o custo |
| **Rastreabilidade** | de onde vem cada número até o problema, a suíte e o teste (11 casos mais o caso "De onde vem o IIC", abaixo) |
| **A avaliação**, em duas abas | **Comparações** (oráculo declarado × corrigido por combinação, com as de AC reprovado em vermelho, e o modelo local, suíte final e 1ª tentativa, ao lado dos comerciais) e **Combinação** (teste a teste: entrada, saída escrita na suíte, saída real do `AC_ref`, veredito do AC e quantos alvos cada teste detectou em cada oráculo) |

**Filtros.** Um lugar só: a barra lateral, a mesma em todas as páginas, sempre aplicada (conjunto,
cenário, problema, macrocategoria, rating e status da suíte). O topo de cada página diz o recorte
ativo e quantos problemas ele tem; todo número, gráfico e **título-conclusão** é recalculado para o
recorte. Mais: um **Glossário** na barra lateral, a dica de cada sigla ao passar o mouse, o botão de
CSV filtrado em cada tabela e o salvamento de cada gráfico em PNG ou SVG pelo menu do próprio gráfico.

**O que não muda com os filtros, e por quê** (sempre dito na tela, nunca em silêncio):
- **testes estatísticos** (`stats.csv`): só existem para os 200 problemas (são pareados por eles);
  num recorte por problema, macrocategoria, rating ou status, as notas de empate somem e aparece
  "sem teste estatístico para este recorte". O painel não refaz teste num recorte: seria um número que
  não está no texto do TCC e sem a correção de Holm do conjunto de comparações;
- **custo**: existe por modelo e cenário, não por problema; com esses filtros, a seção de custo mostra
  o valor de todos os problemas e diz isso;
- **métrica de um problema só**: não tem sentido (o módulo `metrics` recusa); a página As métricas
  avisa e aponta a ficha do problema na Rastreabilidade, e as páginas O experimento e A avaliação
  continuam funcionando;
- **recorte vazio**: cada página diz que nenhum problema atende e quais filtros estão ativos;
- **suítes `accepted_barred`**: ficam nas métricas (5.9); o painel recalcula, para o recorte ativo, a
  conferência de que nenhum 1º lugar muda sem elas, e a escreve sob o placar.

**O placar.** 6 critérios — TDF\*, MS\*, TFP, Δ_oráculo, TC e custo por 1.000 WAs detectados — em 5
conjuntos (as 4 IAs e a 1ª tentativa do SLM), média dos cenários do recorte, sem teste estatístico
(o teste está no guia de escolha). **Decidido (Milena, 2026-11-12): o placar e as seções de métricas
usam TDF\*/MS\*, o gabarito do AC**, para nenhuma posição vir de saída esperada errada da IA; o
traço de cada barra mostra o valor pelo gabarito da IA. A 1ª tentativa do SLM entra como 5º conjunto,
com a nota das combinações sem suíte (53 de 600, que contam 0%). Empate exato de valores dá a mesma
posição; o SLM fica fora do ranking de custo (é local). O **placar por cenário** tem uma linha por IA e
cenário e a posição dentro do mesmo cenário; seu título diz em quantos dos 6 critérios o 1º lugar muda
com o cenário. Sem filtro, a média dos cenários dá, por exemplo, TDF\* do Gemini 90,1% e TFP do
Claude 17,3% (mesmos números de `metrics.csv`).

**Regra do título-conclusão.** O título de cada gráfico e cartão é gerado por regra, não escrito à
mão (`metrics.story`, uma tabela de modelos de frase com lacunas): o líder do recorte e o valor
preenchem a lacuna ("{líder} encontra {valor} das falhas reais"), e em empate o modelo passa a
"{líder} e {segundo} empatam em … ({v1} × {v2})". Nenhum título descreve um resultado que não venha
do recorte; o painel mostra também onde o líder perde. O líder tem uma cor de destaque única; os demais
ficam em tons neutros. As mesmas regras valem para as figuras do comando `metrics figures` (5.8).

**Regra "empate estatístico" × "não testado" (guia de escolha).** Para dizer se o 1º e o 2º
colocados de um critério diferem, o painel procura o par em `stats.csv` (família `models`, os 4
modelos por cenário, ou `attempt1`, a 1ª tentativa contra cada conjunto; métrica `TDF_star`,
`MS_star` ou `TFP`; coluna `significant`, p corrigido por Holm). Três estados:
- **diferem** — diferença significativa;
- **empate estatístico** — o teste não separa os dois;
- **não testado** — nenhum teste se aplica: o recorte não é o completo (filtro de problema,
  macrocategoria, rating ou status), o critério não tem teste (Δ_oráculo, TC, custo) ou o valor é a
  média de mais de um cenário (o placar). Nunca se declara vitória sem teste.

**O guia de escolha** (decidido por Milena em 2026-11-12: **o painel não dá uma conclusão única; mostra
quem ganhou em cada critério e o leitor decide**). Entrada do leitor: o cenário (o filtro, em
linguagem de uso: "tenho só o requisito" = caixa-preta, "só o código" = caixa-branca, "os dois" =
híbrido) e a prioridade, que só **realça** uma linha (não filtra). Cada linha mostra o vencedor, o
valor e o segundo colocado. Sem filtro, caixa-preta / caixa-branca / híbrido:

| Prioridade | Critério | Vencedor |
|---|---|---|
| gastar pouco | custo por 1.000 WAs | Claude nos três (US$ 0,018–0,020), diferença não testada |
| encontrar o máximo de falhas | TDF\* | Gemini / Gemini, empate estatístico com o Claude (89,7% × 88,0%) / Gemini (89,7–90,7%) |
| nunca reprovar o código correto | TFP | Claude 18,0%, empate com o GPT / **SLM 16,5%**, empate com o Claude (17,5%) / **GPT 15,0%**, empate com o Claude (16,5%) |
| confiar no gabarito que a IA escreve | Δ_oráculo | GPT 1,5 / Claude 1,7 / Claude 1,9 pontos |
| pegar defeitos sintéticos | MS\* | Gemini / Gemini, empate com o Claude / Gemini (96,8–97,1%) |
| rodar sem custo de API | — | SLM (local; custo em tempo na página O experimento) |

Achado a destacar: o vencedor muda com o cenário (com só o código, o modelo local é quem menos reprova
o código correto, em empate com o Claude). Limitações exibidas sob o guia: uma execução por modelo
(comerciais sem seed fixa); saídas esperadas escritas pela IA sem conferência; 3 combinações do
Claude sem suíte (contam 0%); problemas de rating 1000 a 1600 do Codeforces; o SLM é um modelo de
14B local, sem comparação de custo em dinheiro.

**Rastreabilidade (de um número ao problema, à suíte e ao teste).** Pedida por Milena em 2026-11-12:
cada número precisa poder ser conferido na fonte, na defesa e por quem abre o link. A lista segue os
filtros e "Abrir" mostra o item (a combinação com status, origem, tentativas e testes com a saída do
AC; o alvo, com quem o detectou e o código ao lado do AC; ou o problema, com enunciado, AC e as 15
combinações). Os casos: combinações sem suíte (sem filtro, 56: 53 da 1ª tentativa do SLM e 3 do
Claude, com o motivo dos autores); as 9 suítes "sem raciocínio" e as respostas barradas; a origem da
suíte do SLM (aceita, reserva, predita; revisão 1 ou 2 do dataset); qual teste reprovou um WA ou
mutante; o que um teste derrubou; por que o AC foi reprovado (saída esperada errada ou entrada
inválida); detecções que só existem por um dos gabaritos; WAs que nenhuma IA detectou (sem filtro,
174) e os que só uma detectou; mutantes que sobreviveram a todas as suítes; a ficha de um problema;
e **De onde vem o IIC** (emenda de 2026-11-13): os conjuntos de WAs detectados de cada cenário (R,
C e H) nas 8 regiões do diagrama, a conta do IIC com eles, o IIC por problema e o papel de cada WA.
Como cada alvo para no primeiro teste que o reprova (seção 4), o "teste que reprovou" é sempre o
primeiro.

**Desempenho medido (2026-11-14, sem navegador, dados completos, no container)**: O experimento, 17,6
s na primeira leitura e 0,5 s depois; A avaliação, 1,3 s; Rastreabilidade, 0,3 s; As métricas, de 66 s
a 127 s (monta todos os gráficos; recortes menores abrem mais rápido); o servidor responde em cerca de
2,5 s. O tempo de abertura num navegador **não foi medido**: esses números vêm de uma renderização
simulada (`AppTest` do Streamlit, no container, 2026-11-14), sem navegador, rede nem desenho dos
gráficos no cliente; os 66 a 127 s da página As métricas são, portanto, **uma observação a conferir
num navegador real** antes de a tratar como problema ou como número do painel. Como contexto, a
medição de 2026-11-05, com 15 resultados de 1 problema, deu até 1,6 s por página.

**Cópia pública [DECIDIDO, 2026-11-09 — Milena; passo a passo documentado em 2026-11-13]**: o mesmo painel pode ficar no Streamlit
Community Cloud, lendo os pacotes versionados no GitHub (descompacta os zips na 1ª abertura, cerca de
40 s; entrada `src/dashboard/public/streamlit_app.py`; passo a passo no README do módulo). O servidor
da cópia só lê o que está versionado.

**Decisão pendente dos autores — a frase de fechamento do TCC.** O painel **não escreve** uma frase-tese
(decisão acima); o texto do TCC precisa de uma, e a escolha é dos autores (opções redigidas a partir
dos dados, para escolher ou reescrever; nenhuma foi adotada):
- (a) *"Nenhuma IA venceu em tudo: o Gemini detecta mais falhas, o Claude erra menos o gabarito e custa
  menos, e dar mais contexto quase não muda o resultado."* — resumo equilibrado;
- (b) *"Detectar mais não é o mesmo que testar melhor: a IA que mais encontra falhas é a que mais erra a
  saída esperada."* — destaca a troca detecta × erra, o achado mais surpreendente;
- (c) *"Para gerar testes de programas, um modelo comercial barato (Claude) chega perto do melhor em
  detecção com menos falsos positivos e uma fração do custo."* — recomendação prática, mais opinativa.

Registrada também na seção 6, item 34. A conferência das conclusões dos títulos (são a tese do TCC) e
da média dos cenários no placar também cabe aos autores.

---

## 6. Pendências Consolidadas (não inventar — decidir com a dupla)

1. ~~Mapeamento exato de tags do Codeforces → macrocategoria algorítmica~~ —
   **RESOLVIDO** (ver seção 1.3).
2. ~~Detalhamento operacional da estratégia de oráculo por execução do SLM (módulo 3)~~ —
   **RESOLVIDO** (ver 3, `specs/003-slm-test-generation/spec.md`). Solução final, usada na
   execução completa: o oráculo é a **solução de referência em Python escrita pelo próprio
   modelo**, validada nos testes públicos do problema (o `AC_ref` nunca gera nem confere saídas);
   sem solução aprovada em 12 tentativas, a **reserva por WA** (`accepted_fallback`); sem reserva,
   a **predição** como último recurso (`accepted_predicted`); sem predição interpretável, o
   **fechamento manual** pelos autores (`discarded_manual`). Resultado final (pacote juntado da
   revisão 1 com a refeita na revisão 2, 2026-10-22): 504 `accepted`, 95 `accepted_fallback`, 1
   `accepted_predicted`, 0 manuais (`research.md` R16, R18, R21 e R28; a execução da revisão 1,
   antes da junção, tinha 505 / 93 / 2 / 0; seção 3).
3. ~~Operacionalização do IIC no módulo de métricas: como e onde os conjuntos `D(R)`,
   `D(C)`, `D(H)` de falhas detectadas são registrados~~ — **RESOLVIDO** em 2026-11-09: a
   avaliação grava os conjuntos exatos de detectados por combinação (seção 4) e o IIC é agregado
   nos 200 problemas, com a visão por problema (5.4).
26. ~~**[PENDENTE]** Regra de tamanho/normalização de suíte~~ — **RESOLVIDO** em 2026-11-09 pela
    densidade de detecção (TDF ÷ tamanho médio da suíte, 5.5), reportada ao lado da TDF; texto
    original: Regra de tamanho/normalização de suíte a alinhar entre os 3 clientes de
    modelo (SLM, GPT-5.4-mini, Gemini 3.8 Flash), para que a comparação entre cenários e
    modelos não seja enviesada pela variável de confusão "tamanho da suíte" (ver 3). Medido no
    SLM (execução completa, 2026-10-11): mediana 10; `accepted` 1 a 33 (mediana 10),
    `accepted_fallback` 5 a 54 (mediana 10), `accepted_predicted` 8 e 10.
27. ~~**[PROPOSTA]** Parâmetros de amostragem do SLM~~ — **RESOLVIDO** em 2026-09-30 (Milena):
    `temperature 0.7`, `top_p 0.8`, `top_k 20`, `repeat_penalty 1.05` (configuração do fabricante;
    `temperature 0` descartada porque anularia as retentativas; `research.md` R4) (ver 3).
28. ~~**[PENDENTE]** Template do prompt não cumpria FR-007~~ — **RESOLVIDO** em 2026-09-30
    (Milena): RULE 2 e RULE 3 de `src/prompt_templates/slm_prompt.txt` ajustadas (maior caso escrito
    por inteiro, todo valor dentro das restrições; `research.md` R5a) (ver 3).
29. ~~**[PENDENTE]** Forma dos casos de teste consumida pela avaliação~~ — **RESOLVIDO** em
    2026-09-30 (Milena): contrato existente `TestCase` (`input`, `output`), a adotar também pelo
    módulo de avaliação e pelas suítes dos modelos comerciais (ver 3).
30. **[DECIDIDO, 2026-10-06 — `research.md` R20]** Modelo do SLM: **`qwen2.5-coder:14b`**
    (Q4_K_M), escolhido pelos autores depois dos pilotos 4 e 5 (com a regra de R18, as 15
    combinações do piloto 5 terminaram com suíte: 13 `accepted`, 2 `accepted_fallback`). Antes:
    Qwen2.5-Coder-7B, com ≈ 40% das combinações sem suíte projetado no piloto 3. Diverge do texto
    do TCC (seção 7, item 30).
31. **[DECIDIDO, 2026-10-06 — `research.md` R18 e R20]** Tratamento nas métricas das suítes
    que não vêm de uma solução aprovada nos testes públicos: as **`accepted_fallback`** (solução
    que errou um exemplo por WA) **entram como as `accepted`**; as `accepted_low_confidence`
    (solução que quebrou num exemplo) e `accepted_predicted` (saídas escritas pelo modelo, sem
    conferência) ficam **separadas por status**, nunca misturadas em silêncio. **[A parte de
    `accepted_low_confidence` foi SUBSTITUÍDA em 2026-10-06 por R21/R22: a baixa confiança deixou
    de existir na política de 5 fases; continua valendo: `accepted_fallback` como `accepted`,
    `accepted_predicted` separada.]** O relatório da geração já conta cada status à parte
    (pacote final: 504 / 95 / 1; execução completa da revisão 1: 505 / 93 / 2). **[Reescrito em 2026-10-13 — `specs/004-llm-test-generation/`,
    A6]**: `accepted_predicted` passa a ser também o status de **toda** suíte dos LLMs
    comerciais, e o status diz a origem da saída esperada com o mesmo significado nos 3
    modelos (`accepted`/`accepted_fallback` = calculada por um programa; `accepted_predicted`
    = escrita pelo modelo). Nas métricas, a comparação é **por modelo**, sem tratar esse status
    como exceção; só **dentro do SLM** a suíte prevista (hoje 1, a `237_A` caixa-branca; eram 2 na revisão 1) fica separada das calculadas.
32. **[DECIDIDO E EXECUTADO, 2026-10-13 a 2026-10-20 — `/speckit-clarify` de `specs/004-llm-test-generation/`; Claude em `specs/008-claude-test-generation/`]**
    Decisões do módulo dos LLMs comerciais: **A1** 3 tentativas por falha de formato; esgotadas,
    a combinação aguarda os autores (código de saída próprio, pacote recusado) e só fecha como
    `discarded_manual` com motivo, como no SLM; **A2** cada entrada com no máximo cerca de 50
    elementos e 20 linhas, o mesmo do prompt principal do SLM, sem número fixo de testes (o
    tamanho das entradas não é diferença entre os modelos; o tamanho da suíte, item 26, foi
    resolvido depois, em 2026-11-09, pela densidade de detecção); **A4** o código fica em `src/ai_clients/`, com os comandos existentes
    escolhendo o modelo e uma pasta por modelo em `data/suites/`; **A5** chamadas simultâneas
    dentro de um processo, em número configurável por modelo no `.env` (padrão 4, ajustado
    depois do piloto), trava por combinação, HTTP 429 como falha de infraestrutura com espera
    crescente e respeito ao tempo indicado pela API; **A6** `accepted_predicted` em toda suíte
    dos LLMs (item 31 reescrito). **[DECIDIDO, 2026-10-15 — segundo `/speckit-clarify`]** **A7**
    um pacote por modelo, com manifesto e relatório próprios, e as pendências de um modelo não
    bloqueiam o pacote do outro; **A8** teto de gasto obrigatório por invocação, junto com a
    confirmação, e ao atingi-lo nenhuma chamada nova sai (as em andamento terminam e são gravadas,
    então o gasto pode passar um pouco do teto), o comando sai com código próprio e a retomada
    continua; **A9** o piloto é uma execução separada, descartada para a execução completa, que
    começa do zero com uma única configuração (só o relatório do piloto é versionado); **A10** sem
    campo de cálculo por teste no schema, e o cálculo da saída fica no raciocínio interno do
    modelo. **[DECIDIDO, 2026-10-15 — autores; `research.md` A3, com fontes oficiais acessadas na
    mesma data]** **A3** sem seed nem temperatura nos dois modelos: `gpt-5.4-mini-2026-03-17`
    (snapshot datado) com `reasoning.effort: "medium"` explícito, já que o padrão é `none`;
    `gemini-3.8-flash` com `thinking_level: "medium"` explícito. O `gemini-3.5-flash` foi
    descontinuado e é redirecionado para o 3.6; os autores escolheram o 3.8 Flash, GA e o Flash
    mais recente, em vez do 3.6 "previous-generation" (revisto em 2026-10-15; item 41 da seção 7).
    Cada tentativa grava o modelo e a versão devolvidos, os parâmetros enviados e a resposta crua,
    e a não reprodutibilidade bit a bit é limitação declarada. A conferir no piloto: o snapshot
    devolvido pelo GPT e o `modelVersion` devolvido pelo Gemini 3.8 Flash (ver 3).
    **[DECIDIDO, 2026-10-15 — terceiro `/speckit-clarify`]** **A11** o prompt vai inteiro numa
    única mensagem de usuário, como no SLM, sem instrução de sistema em nenhuma das duas APIs;
    **A12** barreira automática em toda execução, nos dois modelos: uma resposta com zero tokens
    de raciocínio (ou sem a contagem) é gravada fora das tentativas, nenhuma chamada nova sai e o
    comando para com código próprio, sem gastar tentativa, até os autores investigarem (antes era
    só uma conferência do piloto); **A13** o Gemini não recebe `safetySettings` (vale o padrão da
    API, como no GPT); bloqueios gravados com a categoria e contados à parte, e a decisão é
    revista se o piloto mostrar bloqueios.
    **[DECIDIDO, 2026-10-15 — `/speckit-plan`, `plan.md` S1 a S3]** **S1** `suite.json` dos LLMs
    com schema próprio (`LlmSuite`, as mesmas chaves de topo do SLM) e leitor comum (`SuiteView`)
    para a avaliação; **S2** dry-run sem nenhuma chamada, com tokens estimados pela razão
    caracteres/token (3,0 antes do piloto, a medida depois); **S3** manter o `generateContent`,
    apesar do rótulo "Legacy", com risco registrado. **[FIXADO NOS PILOTOS E NAS EXECUÇÕES COMPLETAS]** O teto de saída
    (era provisório: 32.768) ficou em 32.768 nos três modelos (seção 3), e a razão
    caracteres/token de cada modelo vem do piloto/relatório de cada um (Gemini 3,354 acima). A forma do JSON com schema
    no Gemini já foi fixada em 2026-10-16 (`responseFormat.text` com `"APPLICATION_JSON"`).
    **[DECIDIDO, 2026-10-16 — Milena]** O Gemini usa conta com faturamento ativo no piloto e na
    execução completa, como o plano previa (na camada gratuita o Google pode usar o conteúdo
    enviado, e o limite de 20 pedidos por dia levaria a execução completa a 30 a 90 dias); a
    primeira tentativa do piloto, feita na camada gratuita, não gravou nenhuma resposta.
    **[MEDIDO, 2026-10-16]** Piloto 1 do Gemini: 15 de 15 suítes na 1ª tentativa, maior saída de
    3.551 *tokens*, razão de 3,354 caracteres por *token*, US$ 0,126 (seção 3). **[DECIDIDO,
    2026-10-16]** Teto de saída mantido em 32.768 (só se paga o que se usa). **[MEDIDO no piloto e na
    execução completa do GPT, 2026-10-20]** A média de saída e o custo reais do GPT (601 chamadas,
    US$ 13,47) estão na seção 3.
33. **[PENDENTE — decisão dos autores, 2026-11-14]** Registro do teste de predição direta do SLM: a
    limitação de oráculo (seção 7, item 42; 5.10) diz que a predição direta foi tentada no SLM e
    descartada por ser inutilizável, mas nenhum artefato do repositório guarda a taxa de acerto, o
    formato ou a amostra desse teste. Opções: (a) os autores registram aqui o que viram (quantos
    problemas, quantas saídas certas) e o número vai para o TCC; (b) a frase vai ao TCC como relato
    de experiência, sem número. Nada foi estimado.
34. **[PENDENTE — decisão dos autores]** Frase de fechamento do TCC: o painel não dá conclusão única
    (5.11); falta escolher, entre as opções (a), (b) e (c) de 5.11, ou reescrever, a frase final do
    texto. Nada foi escolhido.
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
`specs/001-dataset-extraction/spec.md`, decisões de 2026-09-18 a 2026-09-22 (itens 1–16); e
`specs/002-mutant-generation/spec.md`, decisões de 2026-09-23 (itens 17–21); e decisões de
implementação de 2026-09-24 (itens 22 a 24) e resultado da execução real de 2026-09-25 (item 25);
e `specs/003-slm-test-generation/spec.md`, decisões de 2026-09-29 (itens 26–28), e
`specs/003-slm-test-generation/research.md`, plano de 2026-09-30 (item 29) e decisões dos pilotos
e da execução completa do SLM, de 2026-10-04 a 2026-10-11, R13 a R28 (itens 28–40; os itens 28 e
29 foram atualizados para o desenho final em 2026-10-11); e `specs/004-llm-test-generation/research.md`,
decisão A3 de 2026-10-15 (item 41); e `specs/005`, `006`, `007`, `008`, `009`, `010`, `011` e `012`
(itens 43 a 48: avaliação com dois oráculos, revisão 2 do dataset, o terceiro modelo comercial, as
suítes `accepted_barred`, as métricas e o painel, de 2026-10-18 a 2026-11-13).

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
| 15 | Uma WA que diverge na auditoria não é só reportada: é **reparada automaticamente**, substituída pelo próximo candidato não tentado da mesma ordem determinística, com confirmação de 6 execuções concordantes (D18, 2026-09-22); causa raiz é comportamento indefinido do código incorreto ou tempo de execução no limiar do limite, nunca a entrada | 1.4, 1.6 |
| 16 | `extraction_timestamp` não é o único campo que varia entre duas execuções independentes de `validate`: `max_cpu_time_s` de `validacao.json` também varia, por ruído real de medição de hardware (D19, 2026-09-22); `max_memory_bytes` permanece estável | 1.5 |
| 17 | Geração de mutantes por AST (`tree-sitter`), não por substituição textual; ferramenta `Mull` avaliada e descartada (segunda cadeia de compiladores, motor de execução próprio) | 2.1 |
| 18 | Conjunto de operadores de mutação ampliado do texto original (pares fixos) para o conjunto completo de Offutt et al. 1996 (ROR/AOR/LCR completos + ABS + UOI), medido como necessário: 199 dos 200 `AC_ref.cpp` reais tinham menos de 100 ocorrências dos operadores originais | 2.2 |
| 19 | Mutação de ordem superior por regra determinística fixa (pares/trios na ordem de descoberta na AST), não por busca (programação genética/multi-objetivo) | 2.4 |
| 20 | Base de mutação exclusivamente o `AC_ref`; decisão de não usar outras soluções corretas do dataset de origem como bases adicionais, para não reabrir o schema do pacote do módulo de dataset | 2.5 |
| 21 | Reprodutibilidade de mutantes não depende só da seed: dado que a validação de cada mutante reutiliza o motor cuja instabilidade de margem já foi medida (D18/D19), o pacote da execução final é compactado e versionado (`data/mutants.zip`), exigindo emenda ao Princípio II da Constitution (v1.6.0, 2026-09-23) | 2.6 |
| 22 | Na implementação, `<<`/`>>` contam como aritméticos (AOR, trocados só entre si); ABS e UOI agem sobre operandos de expressões relacionais e aritméticas, UOI também sobre os lógicos, com o unário legal dependente do operador pai; as 6 execuções de estabilidade são sobre um binário compilado uma vez, não 3 checagens que recompilam | 2.2, 2.3 |
| 23 | Ordem superior implementada como pares e trios de mutantes de primeira ordem aceitos em ordem lexicográfica, com sítios distintos e disjuntos em bytes; exclusão com alerta e código de saída `0`; piloto nos 3 problemas mais esparsos: fecham só com pares (76% a 83% de segunda ordem); sem orçamento de tentativas | 2.4, 2.9 |
| 24 | Relatório com contagem de problemas por forma de fechamento; (a revisão do código no relatório, prevista aqui, foi retirada em 2026-09-25); `package` recusa pacote de execução parcial, `building/` pendente e problema danificado; trava contra dois `generate` simultâneos | 2.6, 2.10 |
| 25 | Resultado real da geração dos 200 problemas: 56,5% dos problemas só de primeira ordem (a estimativa de ≥75% não se confirmou), 15,3% dos mutantes de ordem superior, 0 excluídos, 20.000 mutantes em ~7 h 26 min | 2.11 |
| 26 | Resposta do SLM em texto com 3 blocos marcados (`<edge_cases_analysis>`, `<inputs>`, `<reference_py>`), não JSON como os dois modelos comerciais — evita erros de escape de código Python dentro de um campo JSON; a suíte persistida depois da interpretação continua JSON com schema versionado | 3 |
| 27 | Exemplo do `<few_shot_example>` é o primeiro teste público do próprio problema sendo perguntado (não um exemplo fixo entre chamadas); mesma regra adotada pelos módulos do GPT-5.4-mini, do Gemini 3.8 Flash (item 41) e do Claude Haiku 5.5 | 3 |
| 28 | Suítes SLM seguem a mesma exceção de versionamento dos mutantes (Constitution, Princípio II, emenda 1.6.0): pacote + manifesto SHA-256 ao final da execução completa, sem exigir nova emenda; falha de infraestrutura na chamada ao Ollama não consome uma das 15 tentativas por problema × cenário (só as 4 razões de conteúdo consomem: `public_test_failed`, `unparseable_response`, `repetition`, `all_inputs_failed`). Na spec de 2026-09-29 eram 6 tentativas e 3 razões (atualizado em 2026-10-11, R16/R21/R22; `repetition` desde R13) | 3 |
| 29 | Parametrização técnica do SLM fixada no plano (2026-09-30): `/api/chat` com uma única mensagem; `num_ctx 8192` / `num_predict 4096` a partir do maior prompt medido (7.870 caracteres no plano; 8.118 com o prompt real, dry-run de 2026-09-30); seeds 43 a 48; Python com tempo × 10 e memória × 4 do limite do problema, só biblioteca padrão; amostragem `temperature 0.7` / `top_p 0.8` / `top_k 20` / `repeat_penalty 1.05` (não `temperature 0`, que anularia as retentativas); casos no contrato `TestCase`; template ajustado para respeitar restrições e não pedir entradas do tamanho máximo. **Final (execução completa)**: `num_predict` 5120 (item 31; maior `prompt_eval_count` medido 2.499); seed e temperatura por tentativa pela tabela `ATTEMPT_POLICY` (seeds 42 a 51; temperatura 0,7, e 0,7 a 0,2 na fase 2; item 32); `top_p`/`top_k`/`repeat_penalty` sem mudança | 3 |
| 30 | Modelo local **`qwen2.5-coder:14b`** em vez do Qwen2.5-Coder-7B citado no TCC (2026-10-06, `research.md` R20): com o 7B a solução Python errava os exemplos em ≈ 86% das tentativas (piloto 3); com o 14B e a regra de R18 as 15 combinações do piloto 5 terminaram com suíte | 3, 6 |
| 31 | Revisão depois do piloto 1 do SLM (2026-10-04; renumerado de 30 para 31 em 2026-10-11, porque havia dois itens 30): cerca Markdown que envolve todo o código Python é removida e registrada (as outras ficam); `<input>` vazio descartado sozinho (só "todas vazias" invalida a resposta); `token repeat limit reached` do Ollama é falha do modelo (razão `repetition`, próxima seed), não de infraestrutura; RULE 2 pede valores até o máximo das restrições com no máximo ~100 elementos por entrada; `num_predict` 4096 → 5120; relatório conta por cenário respostas cortadas, cercas removidas e entradas vazias | 3 |
| 32 | Política de tentativas do SLM em **5 fases**, no máximo 15 tentativas (2026-10-06, `research.md` R21/R22): fase 1, tentativas 1–6 a temperatura 0,7 com seeds 42–47; fase 2, tentativas 7–12 com a **seed 48 fixa e a temperatura caindo de 0,7 a 0,2**; fase 3, reserva; fase 4, predição (13–15, seeds 49–51, 0,7); fase 5, tratamento manual. O desenho de 2026-09-29/30 (itens 28 e 29) previa temperatura única (0,7) e retentativas só por seed. Na execução completa da revisão 1 a fase 2 deu 25 das 600 suítes; no pacote final, 22 | 3 |
| 33 | Suíte de **reserva por WA** (`accepted_fallback`): sem solução aprovada em 12 tentativas, a melhor tentativa que errou um teste público só por WA vira a suíte, e ela **entra nas métricas como as `accepted`** (2026-10-05/06, R16 e R20); 95 das 600 suítes do pacote final (15,8%; 66 na caixa-preta, 16 no híbrido e 13 na caixa-branca; eram 93 na execução da revisão 1) | 3, 6 |
| 34 | **Predição** (`accepted_predicted`, fase 4): o SLM escreve entradas e saídas esperadas, sem solução Python nem validação — a única exceção ao oráculo por execução, separada por status nas métricas (2026-10-06, R18/R19/R21); 1 das 600 suítes do pacote final (`237_A` caixa-branca; a `939_C` caixa-preta, que também era predita na execução da revisão 1, está entre as 208 combinações refeitas e hoje é `accepted`) | 3, 6 |
| 35 | **Fechamento manual** (`discarded_manual`, comando `close` com motivo obrigatório) para combinação sem predição interpretável, que **continua no N = 200** das métricas (2026-10-06, R18/R19); não foi necessário na execução completa (0 combinações) | 3 |
| 36 | **Nenhuma combinação sem suíte** no lugar do descarte da suíte depois de esgotar as tentativas, previsto na spec de 2026-09-29 (2026-10-05/06, R16 e R18); resultado: 600 de 600 com suíte | 3 |
| 37 | **Troca de template no meio da execução**: o template de predição foi trocado em 2026-10-08 (`421adf86…` → `e52133f6…`) pelo comando `change-template`, que registra a troca e move as tentativas da versão antiga para `superseded/` (refeitas com as mesmas seeds); `superseded/` vai para o pacote, para a banca ver o que foi refeito, mas **fica fora das métricas** (R27/R28); 1 combinação refeita (`939_C` caixa-preta) | 3 |
| 38 | Na predição, testes com valores **abreviados** (`1 2 ... 5`, `…`) são descartados e contados (R27); 0 na execução completa | 3 |
| 39 | Geração em **GPUs T4** (mais de uma máquina, uma delas com 2×T4, cada GPU com seu Ollama, vários `generate --resume` em paralelo), com **uma etiqueta de hardware única** (GPU T4, 16GB RAM) em todas as 2.185 chamadas e **sem teste de determinismo entre GPUs**; modelo, digest e versão do Ollama conferidos pelo `--resume` (R23, R24, R26; decisão de 2026-10-11 de não reescrever os arquivos) | 3 |
| 40 | O **piloto 6 conta dentro da execução final**: a execução completa é a continuação da mesma execução com `--resume`, e as 15 combinações do piloto entram no resultado (2026-10-07, R23) | 3 |
| 41 | **Gemini 3.8 Flash (`gemini-3.8-flash`) em vez do Gemini 3.5 Flash** do texto do TCC (2026-10-15, `specs/004-llm-test-generation/research.md`, A3). O Google descontinuou o `gemini-3.5-flash` em 2026-10-08 e redireciona as chamadas a ele para o `gemini-3.6-flash`; entre os substitutos, os autores escolheram o Flash GA mais recente (GA desde 2026-09-02, recomendado pelo Google para projetos novos), e não o 3.6, que o próprio Google descreve como "previous-generation" (o 3.6 chegou a ser escolhido e foi revisto no mesmo dia). Também mudaram os nomes da Tabela 2 do PDF: `reasoning_effort` → `reasoning.effort` (Responses API), JSON estrito por `text.format` `json_schema` com `strict: true`; no Gemini, o `mimeType: application/json` vai em `generationConfig.responseFormat.text`, com o valor `"APPLICATION_JSON"` (conferido na API em 2026-10-16; plano, R3) e o nível de raciocínio em `generationConfig.thinkingConfig.thinkingLevel`. GPT pelo snapshot datado `gpt-5.4-mini-2026-03-17`; raciocínio `medium` enviado explicitamente nos dois modelos (o padrão do GPT-5.4-mini é `none`); sem seed nem temperatura | 3 |
| 42 | **Oráculo por execução (SLM) × por predição (comerciais)** — limitação a declarar no texto: o SLM escreve uma solução em Python, executada e validada nos testes públicos, e é ela que dá as saídas esperadas; os três comerciais escrevem as saídas direto, sem executar nada. A diferença não é arbitrária: a predição direta foi testada no SLM e descartada, porque as saídas previstas erravam muito e o modelo (Qwen2.5-Coder) é treinado para escrever código, não para prever a saída de um programa (decisão dos autores, registrada em 2026-11-09). TDF\*, MS\* e Δ_oráculo (5.5) existem para isolar esse efeito | 3, 5.5 |
| 43 | **Avaliação com dois oráculos e `AC_ref` sem curto-circuito** (decidido em 2026-11-04, executado de 2026-11-04 a 2026-11-09): o TCC descreve o curto-circuito em qualquer alvo e a aprovação do AC só com 100% da suíte; construído: curto-circuito só para WAs e mutantes, contra o `AC_ref` todos os testes rodam (veredito e saída real por teste), cada WA e mutante tem a detecção gravada sob o oráculo **declarado** pela IA e o **corrigido** pela saída real do AC, e um erro de execução só vale se aparecer em 3 execuções seguidas | 4, 5.5 |
| 44 | **Revisão 2 do dataset** (2026-10-18): a conferência contra o original do Codeforces achou expoentes e índices perdidos nos enunciados (152 expoentes em 79 problemas, 701 índices em 74); 104 `enunciado.md` foram corrigidos e o dataset passou à revisão 2 (`data/dataset.zip`), com a revisão 1 guardada só para auditoria. Dataset, `AC_ref`, WAs, testes públicos e mutantes não mudaram (os mutantes não foram regenerados: dependem só do `AC_ref.cpp`); o SLM refez as 208 combinações afetadas; GPT, Gemini e Claude já rodaram sobre a revisão 2. O texto do TCC precisa dizer qual revisão cada execução usou | 1.6.1, 2, 3 |
| 45 | **Três modelos comerciais, não dois**: o **Claude Haiku 5.5** (`claude-haiku-5-5`, Anthropic) entrou como terceiro modelo comercial em 2026-10-20, ao lado do GPT-5.4-mini e do Gemini 3.8 Flash (item 41); com o SLM, são **4 modelos**, 2.400 combinações (4 × 200 problemas × 3 cenários). A comparação entre modelos tem 4 participantes e a camada `claude_suites` entrou no `cli check` | 3 |
| 46 | **Suítes de resposta sem raciocínio (`accepted_barred`)** (2026-10-20): toda resposta de modelo comercial sem tokens de raciocínio é guardada fora das tentativas e pedida de novo; na terceira, a suíte é aceita como `accepted_barred` sem parar a execução. Resultado: 1 no Gemini, 8 no Claude (mais 3 `discarded_manual` do Claude) e 0 no GPT. As 9 `accepted_barred` **ficam incluídas** nas métricas e o número é relatado (decisão de 2026-11-12, 5.9) | 3, 5.9 |
| 47 | **Métricas e estatística além do texto do TCC** (2026-11-04/09): TDF\*/MS\*/Δ_oráculo, TFP por causa (`oráculo` × `entrada_inválida`), custo por detecção (CPD, só em US$ dos comerciais; o SLM em *tokens* e tempo), densidade de detecção (resolve a pendência 26), IIC agregado nos 200 problemas e por problema, testes de Friedman, Wilcoxon e McNemar com correção de Holm e tamanho de efeito A12; complementaridade entre modelos (C.5) e IIC sobre mutantes (C.6) ficaram de fora | 5.5, 5.6, 5.9 |
| 48 | **Painel de exploração dos resultados** (Streamlit, só leitura; não faz parte do desenho do TCC): 4 páginas (O experimento, As métricas, Rastreabilidade, A avaliação), com a rastreabilidade de cada número até o problema, a suíte e o teste; há uma cópia pública no Streamlit Community Cloud (decisão de 2026-11-09, publicada pelos autores). As figuras são desenhadas sob demanda e não vão no `data/metrics.zip` | 5.8, 5.11 |

---

## 8. Histórico de atualizações deste documento

Registro datado de cada atualização, para conduzir a revisão do texto escrito do TCC
(Constitution, princípio XI). Origem: `specs/001-dataset-extraction/` (spec, plano, pesquisa),
`specs/002-mutant-generation/` (a partir de 2026-09-23), `specs/003-slm-test-generation/`
(a partir de 2026-09-29), `specs/004-llm-test-generation/` (a partir de 2026-10-13),
`specs/005-show-request/` a `specs/012-dashboard-storytelling/` (de 2026-10-16 a 2026-11-13: pedido enviado,
conferência dos enunciados, revisão 2 do dataset, Claude, avaliação, métricas e painel) e os
registros de fechamento da documentação (2026-11-14). Ordem: da mais recente para a mais antiga.

| Data | O que mudou | Seções |
|---|---|---|
| 2026-11-14 | **Consolidação da metodologia na verdade executada (fechamento da documentação)**: (1) SLM final 504 `accepted` + 95 `accepted_fallback` + 1 `accepted_predicted` + 0 `discarded_manual` no corpo vigente (a execução da revisão 1, 505/93/2, fica só como história), com a junção explicada: 392 combinações da revisão 1 mais as 208 refeitas na revisão 2; (2) revisão 2 do dataset: só os 104 `enunciado.md` mudaram e os mutantes **não** foram regenerados (dependem só do `AC_ref.cpp`); o `mutation_report.json` guarda o hash do manifesto da revisão 1, `6b3628c3…`, que é o mesmo conteúdo do `dataset.rev1.manifest.json` (`a092d987…`, com fim de linha CRLF); (3) seção 4 reconciliada com o que foi especificado e executado; seção 5.8 reescrita para o estado final; novas 5.10 (rastreabilidade pergunta → métrica, com a limitação do oráculo e o que não está medido) e 5.11 (painel), que absorvem `docs/metricas-referencia.md` e `docs/roteiro-painel.md`; (4) rótulos de estado defasados corrigidos, seção 3 reordenada, parágrafos de origem das seções 7 e 8 atualizados, itens 43 a 48 na seção 7 e 33 e 34 na seção 6 (pendências dos autores); (5) LaTeX corrompido (`\*`, `\r`) e linha quebrada de 2026-10-18 corrigidos; (6) **orquestrador ponta a ponta descartado (decisão dos autores)**: cada etapa roda pelo comando do README do seu módulo, o `cli` tem só o `check`, e `evaluation run` e `metrics compute` chamam o portão de consistência (seção 0.1); o orquestrador previsto em 2026-09-22 não será construído; (7) mutantes e revisão 2 (nova 2.12), parâmetros `OLLAMA_HARDWARE_LABEL` e `CHARS_PER_TOKEN` (seção 3), tempos do `metrics` (5.9) e a observação de que os 66 a 127 s do painel foram medidos sem navegador (5.11) | 0.1, 1.6.1, 2, 2.12, 3, 4, 5.8, 5.9, 5.10, 5.11, 6, 7, 8 |
| 2026-11-13 | **Rastreabilidade do IIC (`specs/012-dashboard-storytelling/`, US5, T060)**: decidido (Milena): cada símbolo da fórmula do IIC pode ser conferido na fonte. Caso novo "De onde vem o IIC": para uma IA, uma direção e um gabarito, os WAs pegos em cada cenário (R = caixa-preta, C = caixa-branca, H = híbrido) nas 8 regiões dos três conjuntos, a conta com esses números e quais regiões somam em cada termo, o IIC por problema e o papel de cada WA. Conferido nos dados reais: os ganhos, as perdas e a base das 20 linhas de `iic.csv` (5 conjuntos × 2 gabaritos × 2 direções) saem iguais dos `results.csv`. Exemplo (Claude, + código, gabarito do AC): |H ∖ R| = só H 374 + C e H sem R 1.003 = 1.377; |R ∖ H| = só R 285 + R e C sem H 652 = 937; |R| = 16.752; (1.377 − 937) ÷ 16.752 = +2,6%. O problema que mais pesa é `182_B`: a caixa-preta do Claude não tem suíte (corte no teto de saída), então os 100 WAs pegos no híbrido contam como ganho e o problema fica fora do IIC por problema | 5.5, 8 |
| 2026-11-13 | **Painel: placar por cenário e figuras fora do repositório (`specs/012-dashboard-storytelling/`, T056–T058)**: decidido (Milena): (1) sai o botão "Baixar figura" dos cartões, porque o menu do próprio gráfico já salva em PNG e SVG; (2) abaixo do placar, um **placar por cenário**, com uma linha por IA e cenário (SLM · caixa-preta, SLM · caixa-branca, SLM · híbrido, e assim por diante) e a posição comparando as IAs dentro do mesmo cenário; o título diz em quantos dos 6 critérios o 1º lugar muda com o cenário; (3) **nenhuma figura no repositório**: o pacote de métricas passa a ter só as tabelas e o `run.json`, e o comando de figuras fica opcional, para quem quiser os arquivos. Emenda a decisão de 2026-11-12 (as figuras novas também no pacote) e a de 2026-11-09 (download em PNG e PDF na página). Medido: `data/metrics.zip` refeito, com as 6 tabelas e o `run.json` iguais byte a byte (mesmo SHA-256 no manifesto) e as 12 figuras removidas; de 1.776.166 para 1.198.898 bytes; `verify` e `verify --extracted data/metrics` `OK` | 5, 8 |
| 2026-11-13 | **Painel: fórmula de cada gráfico e rótulos em português (`specs/012-dashboard-storytelling/`, T052–T055)**: decidido (Milena): cada gráfico da página das métricas ganha "Como se calcula", com a fórmula, a mesma fórmula em palavras e a conta feita com os números do recorte, recalculada das contagens brutas (problemas, WAs, mutantes, testes, US$), e não do valor já desenhado; um teste confere que as duas dão o mesmo número. Conferido nos dados reais: todo problema tem 100 WAs e 100 mutantes e todo conjunto × cenário tem 200 problemas, então a média das porcentagens por problema (o que o código faz) é igual à conta com as somas (a que o painel mostra): Gemini 54.083 de 60.000 WAs = 90,1% (TDF\*), 58.213 de 60.000 mutantes = 97,0% (MS\*); Claude 104 de 600 combinações reprovam o AC = 17,3% (TFP); Δ_oráculo do GPT 86,6% − 84,7% = 1,89 pontos; TC do SLM 1ª tentativa 547 de 600 = 91,2%; IIC do SLM 1ª tentativa (+ código, gabarito do AC) (2.657 − 2.050) ÷ 12.472 = 4,9%; Claude US$ 0,98 ÷ 51.550 WAs × 1.000 = US$ 0,019. O IIC conta só WAs (C.6, IIC sobre mutantes, fora do escopo). Achado e corrigido: a distribuição do IIC por problema usava sempre o gabarito da IA, sem dizer, enquanto o gráfico do IIC logo acima segue o seletor de gabarito (o do AC por padrão); agora as duas seguem o seletor, e o arquivo leva `gabarito-ia` quando é o da IA. Rótulos: o gráfico de caixas do IIC mostra em português o que o Vega-Lite mostrava em inglês ("Upper Whisker", "Q3"), e a legenda diz o que cada IIC compara | 5.5, 8 |
| 2026-11-12 | **Painel: nova ordem e página de rastreabilidade (`specs/012-dashboard-storytelling/`, US5, T047–T051)**: decidido (Milena): as páginas passam a ser O experimento → As métricas → Rastreabilidade → A avaliação (a avaliação vai para o fim). A página nova leva de um número à fonte, em 11 casos: combinações sem suíte com o motivo e as tentativas; suítes sem raciocínio e as respostas barradas; origem da suíte do modelo local; qual teste reprovou um WA ou mutante (entrada, saída da IA, saída do AC, código ao lado do AC); o que um teste derrubou; por que o AC foi reprovado; detecções que só existem por um gabarito; WAs que nenhuma IA detectou; WAs que só uma detectou; mutantes sobreviventes; ficha do problema. Medido nos dados reais (gabarito do AC, os 4 modelos): 56 combinações sem suíte (53 da 1ª tentativa do modelo local, 3 do Claude); 992 suítes reprovam o AC em 196 problemas (as que mais reprovam: `158_C` 13 de 15, `447_C` 12, `175_B` 11); **174 WAs que nenhum dos 4 modelos detectou, em 67 problemas** (168 contando também a 1ª tentativa); **390 WAs detectados por um só modelo** (GPT 135, Gemini 108, Claude 99, SLM 48); **65 mutantes que nenhuma suíte reprovou, em 29 problemas** (candidatos a equivalentes, não conferidos); detecções de WAs só pelo gabarito da IA 17.876 e só pelo do AC 2.102, iguais às de `detected_wa.csv` | 8 |
| 2026-11-12 | **Painel que conta a história, 2ª parte implementada (`specs/012-dashboard-storytelling/`, T022–T033)**: página "As métricas" reescrita: placar dos 5 conjuntos em 6 critérios, falhas reais e mutantes, falsos positivos (troca detecta × erra), contexto (variação entre cenários e IIC divergente com o seletor de gabarito), custo, guia de escolha (vencedor de cada critério por cenário, 2º colocado e estado do teste; a prioridade escolhida só realça uma linha) e as tabelas oficiais no fim, seguindo o recorte da barra lateral (o seletor "Corte das tabelas" saiu). Títulos-conclusão por regra, em `metrics.story` (modelos de frase numa tabela única, `TEMPLATES`); `--rating` no comando de figuras; 5 figuras novas e 3 revistas. **Decidido (Milena): as 9 suítes `accepted_barred` ficam nas métricas**, com a contagem e a conferência de que nenhum 1º lugar muda sem elas escritas sob o placar. Conferido contra as tabelas reais: os empates do roteiro aparecem no guia (TFP SLM × Claude na caixa-branca, GPT × Claude no híbrido, Claude × GPT na caixa-preta; TDF\* e MS\* Gemini × Claude na caixa-branca) e o custo aparece "não testado" | 5.8, 5.9, 8 |
| 2026-11-12 | **Painel que conta a história, 1ª parte implementada (`specs/012-dashboard-storytelling/`, T001–T021)**: o painel passa a ter três páginas (o experimento, a avaliação, as métricas), com o filtro de rating na barra lateral; a página "O experimento" mostra o contexto pelo recorte (sem filtro: 200 problemas, 24.274 testes nas suítes dos 4 modelos, US$ 19,35 — GPT 70%, Gemini 25%, Claude 5% —, toda IA com suíte em pelo menos 91,2% das combinações, o mínimo sendo a 1ª tentativa do modelo local). `per_problem.csv` ganhou a coluna `rating` (o `cf_rating` do problema); medido: as outras cinco tabelas de métricas ficaram com o mesmo SHA-256 e `data/metrics.zip` foi reempacotado. O módulo `metrics.story` (placar, vencedor, segundo colocado e estado do teste lido de `stats.csv`) confere, contra as tabelas reais, os números e os empates do roteiro. Divergências do plano: a página 1 conta a partir da tabela da avaliação (funciona sem as métricas), não do `per_problem.csv`; o par divergente do IIC será azul ↔ vermelho (paleta validada), não azul/laranja; "sem suíte" é desenhado em cinza, não numa cor de categoria. A conferência visual achou um empate escondido no subtítulo dos ratings (1400 e 1600 com 35 problemas cada), corrigido | 5.8, 8 |
| 2026-11-12 | **Painel que conta a história dos resultados especificado (`specs/012-dashboard-storytelling/`)**: a partir do roteiro `docs/roteiro-painel.md` (método de *visual storytelling*; roteiro consolidado em 2026-11-14 na seção 5.11 e arquivo removido), decidido (Milena): o painel passa a apresentar os resultados, **sem conclusão única** — mostra quem ganhou em cada critério (detecção, mutantes, falsos positivos, confiança no gabarito, cobertura, custo), por cenário, e o leitor decide pela sua prioridade e pelo que tem em mãos (só o requisito, só o código, os dois); três páginas, nesta ordem: o experimento, a avaliação (Combinação e Comparações juntas), as métricas; **filtros só na barra lateral**, sempre aplicados, com o rating como filtro novo e títulos-conclusão recalculados por regra para o recorte; **gabarito do AC no placar** (TDF\* e MS\*, não TDF e MS); **1ª tentativa do modelo local no placar**, como quinto conjunto, com a nota das 53 combinações sem suíte; os gráficos novos da página de métricas (placar, detecta × erra, variação entre cenários, IIC divergente, guia de escolha) também viram figuras do texto, pelo comando de figuras e no pacote de métricas. Plano: módulo `metrics.story` (Python puro) com placar, vencedores, títulos e guia, usado pelo painel e pelo comando; `per_problem.csv` ganha a coluna `rating`; nenhum teste estatístico novo: num recorte, ou na média de cenários, a diferença é dita "não testada". Achado ao conferir o roteiro contra `stats.csv`: empates estatísticos que o guia precisa mostrar — TFP de GPT × Claude nos três cenários e do modelo local × Claude na caixa-branca; TDF\* e MS\* do Gemini × Claude na caixa-branca (p = 0,07) | 5.8, 8 |
| 2026-11-12 | **Reprodução por quem clona o repositório, conferida num clone novo**: no Windows 11 com Docker Desktop, seguindo só o `README.md` (commit `52eeb24`): clone de cerca de 206 MB com os 14 pacotes; `docker compose build` em 5 min; `pytest` com 2120 testes aprovados em 6 min; descompactados os 12 pacotes de uso (dataset, mutantes, suítes dos 4 modelos, avaliação dos 5 conjuntos, métricas); `cli check --deep` `OK` (0 falhas, 0 avisos) em 25 min, lentidão vinda da pasta compartilhada do Docker Desktop; `metrics verify --extracted` `OK`; painel no ar em cerca de 6 s. A geração do zero não foi conferida no Windows. Os READMEs ganharam o "Caminho rápido" (descompactar tudo, conferir, abrir o painel), o estado final do experimento, a URL real do repositório e um guia de leitura dos gráficos do painel | 8 |
| 2026-11-09 | **Cópia pública do painel (emenda da decisão "uso só local" de 2026-11-04)**: decidido (Milena) publicar o painel, só de leitura e gratuito, no Streamlit Community Cloud (até 2,7 GB de memória). O Hugging Face Spaces chegou a ser escolhido por ter mais memória, mas criar um Space Docker exige plano pago (documentação do Hugging Face conferida em 2026-11-10). A cópia pública roda `src/dashboard/public/streamlit_app.py` num clone do repositório, com dependências mínimas nas versões do `uv.lock`, e descompacta em `data/` os 12 pacotes versionados (avaliação dos 5 conjuntos, métricas, dataset, mutantes e suítes) na primeira abertura do servidor; é publicada pelos autores. Medido num Python 3.11 limpo, simulando um clone: primeira abertura em 39 s, 3.000 combinações sem arquivo inválido, nenhuma exceção, 176 MB de pico de memória, 720 MB em `data/`, figura PNG igual à do projeto. Na mesma conferência, `data/metrics.zip` foi reempacotado com as colunas de alvos mortos (`verify --extracted` OK) | 8 |
| 2026-11-09 | **Contagem de alvos mortos**: `metrics.csv` ganha WAs e mutantes mortos (pelos dois oráculos) e o total, ao lado da TDF e do MS; tabela na seção 5.9 e no painel; cada alvo conta uma vez (morto se algum teste o reprova) | 5.9 |
| 2026-11-09 | **Figuras legíveis e download igual à tela**: paleta e tons de texto por tema, um painel por cenário, custo em US$ por 1.000 WAs; as figuras do comando e os botões PNG/SVG/PDF do painel passam a ser o mesmo gráfico (Altair + vl-convert, sem matplotlib); pacote com PNG e SVG (o PDF não sai igual byte a byte); destaque das combinações com AC reprovado legível no tema escuro | 5.8 |
| 2026-11-09 | **Métricas calculadas (`specs/010-metrics/`, implementado)**: seção 5 reescrita com a proposta confirmada (regras de borda, 5.5 complementares, 5.6 estatística, 5.7 cortes, 5.8 figuras, 5.9 resultados medidos); Q5 na seção 0; pendências 3 e 26 fechadas; limitação do oráculo na seção 7 (item 42). Divergências da implementação: o custo por cenário dos comerciais soma o `by_group` do relatório de geração com as respostas barradas daquele cenário (o `by_group` não as inclui); o pacote leva as tabelas e só as figuras sem filtro; as figuras filtradas são exploração e se refazem pelo comando | 0, 5, 6, 7, 8 |
| 2026-11-09 | **Módulo de métricas especificado (`specs/010-metrics/`)**: implementa a proposta de `docs/metricas-referencia.md` (consolidada em 2026-11-14 nas seções 5.1 a 5.10; arquivo removido) confirmada em 2026-11-04 sem C.5 e C.6 — TDF, MS, TFP (N = 200, com a nota de combinações sem suíte e a visão entre as com suíte), IIC agregado nos 200 problemas com a visão por problema, TC, TDF\*/MS\*/Δ_oráculo, TFP por teste e por causa, CPD (o modelo local só em *tokens* e tempo), densidade, Friedman/Wilcoxon/McNemar com A12 e Holm, cortes por macrocategoria e status; tabelas versionadas lidas pelo dashboard; a seção 5 desta metodologia será substituída pela proposta. Decidido (Milena): a predição direta foi descartada no modelo local porque as saídas previstas erravam muito e o modelo é treinado para escrever código, não para prever saídas. Figuras (Milena, 2026-11-09): desenhadas por funções deste módulo a partir das tabelas, com filtros por macrocategoria, status, modelos e cenários (nunca um problema só), geradas por comando e exibidas na página de métricas do dashboard com download em PNG e PDF; filtros e fonte no rodapé e no nome do arquivo, para toda figura se refazer pelo comando. Emenda a decisão do dashboard de 2026-11-04 ("gráficos sem download"). Plano: pacote `src/metrics/` (`python -m metrics compute|figures|package|verify`, serviço `app`); fonte única o `results.csv` dos 5 conjuntos, mais a macrocategoria e os relatórios de geração; uma tabela por problema (conjunto × cenário × problema) como base de todas as médias e dos testes pareados; IIC também pelo oráculo corrigido, em coluna à parte; McNemar exato pelo teste binomial, Holm e A12 à mão; novas dependências `scipy` e `matplotlib`; seis tabelas e figuras determinísticas em `data/metrics/`, empacotadas com manifesto | 0, 5, 8 |
| 2026-11-09 | **Avaliação das suítes concluída**: execução completa dos 5 conjuntos (3.000 combinações) de 2026-11-04 a 06, pacotes `data/evaluation_<conjunto>.zip` com manifesto, `cli check --deep` OK; AC reprovado em 183 (SLM), 121 (GPT), 329 (Gemini), 104 (Claude) e 255 (1ª tentativa do SLM) combinações; detecções nos dois oráculos na seção 4 | 4, 8 |
| 2026-11-04 | **Dashboard de exploração especificado (`specs/011-results-dashboard/`)**: painel só de leitura sobre os resultados da avaliação (visão geral por conjunto × cenário, detalhe teste a teste, oráculo declarado × corrigido, modelo local × comerciais) e, depois, sobre as tabelas do módulo de métricas (feature 010), sem recalcular métrica; ferramenta de exploração, não fonte dos números do TCC. Decidido (Milena): porcentagens de detecção só como prévia rotulada até existirem as métricas oficiais, uso só local (sem publicação), download apenas do CSV das tabelas; as figuras do TCC vêm só do módulo de métricas. Clarify: dados lidos ao abrir, com botão "recarregar" e a hora da leitura na tela (sem releitura automática); no detalhe de um alvo, o código dele e o `AC_ref` lado a lado com as diferenças destacadas. Plano: pacote `src/dashboard/` (Streamlit, fixado no `uv.lock`), aberto por `python -m dashboard serve` no serviço `app` com a porta publicada só em `127.0.0.1` e a telemetria desligada; camada de dados em Python puro, testável, que substitui a prévia provisória do piloto; leitura validada pelo esquema da avaliação; a página de métricas é um aviso até a feature 010. **Implementado (2026-11-05)**: Streamlit 1.66.1 (pandas 3.0.6 mantido); divergências do plano: (a) o pacote das páginas é `views/`, não `pages/`, porque o Streamlit trata uma pasta `pages/` ao lado do script como páginas automáticas; (b) além da telemetria desligada, o endereço anunciado é fixado em `localhost`, porque o Streamlit consultava o IP externo da máquina na internet ao subir. Conferido com a avaliação real de `1000_B` (conferência): cada página abriu em até 1,6 s, e o detalhe Gemini caixa-preta mostra 32 alvos pegos só pelo oráculo declarado (14 WAs e 18 mutantes). Pedido de Milena (2026-11-05): o nome completo de cada sigla e de cada coluna aparece ao passar o mouse, e há um glossário na barra lateral | 4, 5, 8 |
| 2026-11-04 | **Avaliação das suítes especificada (`specs/009-suite-evaluation/`)**: sem curto-circuito contra o `AC_ref` (veredito e saída real por teste), curto-circuito mantido para WA/mutante, detecção sob o oráculo declarado e o corrigido pelo `AC_ref`, conjuntos exatos de detectados, "sem suíte" para `discarded_manual`, 1ª tentativa isolada do modelo local, pacote por modelo e camada no `cli check`. Clarify: erro de execução do AC e dos alvos repetido 2 vezes (só vale se repetir nas 3); piloto obrigatório de 60 combinações. Implementado: pacote `src/evaluation/`, compilação uma vez por problema, passada única para os dois oráculos, cinco conjuntos (`slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`) com pacote próprio e `results.csv`. Também: a preparação do servidor do modelo local passa a ser descrita só como servidor Ollama com GPU T4, sem plataforma | 3, 4, 8 |
| 2026-10-22 | **Modelo local refeito nas 208 combinações da revisão 2 e pacote juntado**: 165 `accepted`, 43 `accepted_fallback` nas refeitas; pacote final 504/95/1/0 (208 novas, 392 da revisão 1); geração em GPUs T4, parte com o `generate` fora do Docker (válvula de escape); `cli check --deep` OK com os 4 modelos | 1.6.1 |
| 2026-10-20 | **Execução completa do Claude terminada e empacotada**: 589 `accepted_predicted`, 8 `accepted_barred`, 3 `discarded_manual` (`171_F` caixa-preta e híbrido por recusa de segurança `bio`; `182_B` caixa-preta por corte no teto de saída), 632 chamadas (36 sem raciocínio), US$ 0,98 | 3 |
| 2026-10-20 | **Claude sem piloto separado (decisão de Milena)**: a chamada de conferência mostrou `thinking_tokens` 5.165 e custo de US$ 0,0031; as medidas do piloto vêm da execução completa | 3 |
| 2026-10-20 | **Execução completa do GPT terminada e empacotada**: 600 `accepted_predicted` (piloto aproveitado), 601 chamadas (1 corte pelo teto de saída), nenhuma resposta sem raciocínio, US$ 13,47 | 3 |
| 2026-10-20 | **Piloto do GPT aproveitado (emenda de A9/FR-023a da 004)**: configuração idêntica à da execução completa; as 15 combinações seguem na mesma árvore com `--resume` | 3 |
| 2026-10-20 | **Execução completa do Gemini terminada e empacotada**: 599 `accepted_predicted`, 1 `accepted_barred` (`1201_B` caixa-preta), 613 chamadas (14 sem raciocínio em 7 combinações), US$ 4,90, nenhuma falha de formato | 3 |
| 2026-10-20 | **Claude implementado (`specs/008-claude-test-generation`)**: `--model claude`, camada `claude_suites`, conferência do limite de prompt antes da chamada; dry-run real: 600 combinações, US$ 9,91 a 29,74, 600/600 pedidos fiéis ao dataset; 1.981 testes passando | 3 |
| 2026-10-20 | **Plano do terceiro modelo comercial (`specs/008-claude-test-generation/plan.md`, research R1–R9)**: cliente da Messages API sem SDK, sinal de raciocínio por `thinking_tokens`, preço datado, piloto com uma chamada de conferência; emenda 1.9.0 da constitution proposta | 3 |
| 2026-10-20 | **Clarify do terceiro modelo comercial (`specs/008-claude-test-generation/spec.md`)**: `claude-haiku-5-5`, `effort: medium`, mesma regra de resposta sem raciocínio, teto de saída 32.768 | 3 |
| 2026-10-20 | **Terceiro modelo comercial (`/speckit-specify` de `specs/008-claude-test-generation/`)**: Claude Haiku 5.5 nas mesmas condições do GPT-5.4-mini e do Gemini 3.8 Flash, sobre a revisão 2 do dataset; o desenho passa a 3 modelos comerciais | 3 |
| 2026-10-20 | **Resposta sem raciocínio não para mais a geração (emenda de FR-018a)**: a combinação é pedida de novo até 3 respostas sem raciocínio e, na terceira, a suíte é `accepted_barred` (testes da última legível, marcada para análise à parte); motivo: `1201_B` caixa-preta barrada 6 vezes seguidas; o código 6 deixa de ser usado | 3 |
| 2026-10-19 | **Gemini sem raciocínio na execução completa**: 1 de 10 respostas (`1009_B` caixa-preta) veio sem `thoughtsTokenCount` com `thinkingLevel` `medium` enviado; barrada (código 6) como previsto; decisão: manter a regra, retomar e medir a taxa | 3 |
| 2026-10-18 | **Revisão 2 do dataset gerada (`python -m dataset revise`)**: 15 decisões avaliadas pelo agente a pedido de Milena e conferidas contra o original (2 corrigidas: `670_D2`, legenda ausente, e `190_A`, expoente; 13 mantidas, só notação); 104 enunciados alterados (102 automáticos, 2 manuais), só `enunciado.md` mudou; revisão 1 guardada e conferida; conferência das decisões passa a juntar diferenças a até 16 caracteres; 208 combinações do SLM afetadas; mutantes intactos e `mutation report` não rodado | 1.6.1 |
| 2026-10-18 | **Analyze da revisão 2 do dataset (`specs/007-dataset-revision`)**: a árvore do SLM da revisão 1 é conferida antes da junção, sem exigir o dataset atual; antes de liberar GPT e Gemini, conferir que o dataset extraído é a revisão 2 (o hash da revisão 1, `a092d987…`, não é usado em execuções novas); o `verify` da revisão 1 é auditoria, permitido pela emenda 1.8.0 (nenhum comando do pipeline a consome); rascunhos das decisões já trazem as marcações sugeridas (caso `190_A`); conferência da árvore antes do `mv` | 1 |
| 2026-10-18 | **Constitution 1.8.0 (Princípio II)**: o dataset pode ter revisões numeradas, só quando uma conferência automática contra a fonte original demonstrar perda de conteúdo, alterando só o justificado, guardando a revisão anterior, registrando a proveniência no manifesto e fazendo os artefatos derivados dizerem a revisão; aprovada por Milena (`specs/007-dataset-revision/research.md` R1) | 1 |
| 2026-10-18 | **Plano da revisão 2 do dataset (`specs/007-dataset-revision/plan.md`, research R1–R8)**: `dataset revise`, revisão 1 guardada intocada, manifesto `schema_version` 2 com a proveniência, decisões dos 15 por arquivo, junção das execuções do SLM com `provenance.json`; emenda 1.8.0 proposta; achado do relatório dos mutantes com hash de dataset anterior | 1 |
| 2026-10-18 | **Clarify da revisão 2 do dataset (`specs/007-dataset-revision/spec.md`, Clarifications)**: F1 arquivo de decisão por problema para os 15 revisados à mão; F2 execução nova do modelo local só com as combinações afetadas, com a origem marcada por combinação; F3 revisão 1 guardada como auditoria; F4 pilotos intocados e relatório dos mutantes regenerado sem regerar os mutantes | 1 |
| 2026-10-18 | **Spec da revisão 2 do dataset (`/speckit.specify` de `specs/007-dataset-revision/`, Draft; seção 1.6.1)**: decidido pelos autores refazer o dataset com os enunciados corrigidos (D1), refazer no modelo local só as combinações afetadas (D2) e rodar GPT e Gemini com a revisão 2 (D3); emenda da constitution e quatro pontos para o clarify (F1 a F4) | 1 |
| 2026-10-18 | **Conferência dos enunciados nos 200 problemas (`specs/006-statement-fidelity/research.md` R10)**: `check-statements` nos 200 problemas (2026-10-18): download dos 195 restantes em 13 min 12 s (rodado por Milena; nenhum `unchecked`); segunda execução sem nenhum acesso ao site e relatório byte a byte igual (SHA-256 `22d234e7…`, SC-003). O primeiro relatório tinha 188 diferenças `formula` e 274 `other` que, examinadas, eram conversões feitas pelo dataset (comandos LaTeX trocados por um símbolo) e listas que o dataset escreveu em Markdown (`* `, `1. `); a tabela de equivalências passou a ter as 16 trocas de um comando por um símbolo vistas nos pares do próprio relatório (`\leq`→`≤`, `\ldots`→`…`, `\cdot`→`⋅`, `\rightarrow`→`→`, `\ne`/`\neq`→`≠`, `\ge`→`≥`, `\gt`→`>`, `\times`→`×`, `\lfloor`/`\rfloor`/`\lceil`/`\rceil`, `\sum`→`∑`, `\,`→espaço, `\bmod`→`mod`, além das 3 do piloto) e os itens de lista passaram a ser lidos como o dataset os escreveu; as perdas de expoente e índice não mudaram com isso. Relatório final: **83 fiéis, 117 com diferença; 152 expoentes perdidos em 79 problemas; 701 índices perdidos em 74 problemas**; 23 diferenças de fórmula em 12 problemas (mudanças de forma, como `\frac{a}{b}` escrito `(a)/(b)`, `\limits`, `\max`); 36 `other` em 4 problemas (`670_D2`: a página atual tem outro texto; `1162_B` e `981_B`: barras invertidas a mais no nosso texto, em matrizes e conjuntos LaTeX; `190_A`). Contra a contagem antiga por padrão: 70 dos 71 confirmados pelo original (o 71º, `670_D2`, não pôde ser comparado porque o texto da página difere), e 9 problemas com expoente perdido que ela não via (`102_B`, `155_C`, `203_B`, `252_A`, `271_B`, `289_C`, `362_B`, `538_A`, `765_C`). `correct-statements`: 102 enunciados corrigidos (151 expoentes e 701 índices marcados), 83 sem mudança, 15 para revisão (12 por fórmula, 3 por `other`), nenhuma conferência falhou; o dataset continua igual ao manifesto (`verify --extracted`: OK) | 1, 3 |
| 2026-10-18 | **Conferência dos enunciados implementada; os 5 do piloto pelo comando (`specs/006-statement-fidelity/research.md` R9)**: `check-statements --problem` com os 5 do piloto (2026-10-18, revisão `9df4f0e` mais a implementação não commitada): as 5 páginas baixadas de novo pelo comando (HTTP 200, cerca de 31 s com a subida do contêiner); `161_A` 4 `lost_exponent` e 21 `lost_index`, `1_B` 2 `lost_exponent`, `15_A` 6 `lost_index`, `102_B` 1 `lost_exponent` (`10^{100000}`), `1000_B` `faithful` (formato LaTeX); nenhuma diferença `other`, `formula`, `image` ou `table` — exatamente a contagem feita à mão no piloto (SC-001). Testes do módulo `dataset`: 489 passando | 1, 3 |
| 2026-10-18 | **Analyze da conferência dos enunciados (`specs/006-statement-fidelity`)**: pacote `data/statement_originals.zip` determinístico (ordem alfabética, data fixa); com só o pacote, confere-se o hash de cada bloco; erro definitivo do site (404, sem enunciado) só é tentado de novo com `--refetch`; com `--problem`, o resultado é só impresso e o relatório versionado vem da execução dos 200; os 5 do piloto são baixados de novo pelo comando; enunciado traduzido fica não conferido | 1 |
| 2026-10-18 | **Plano da conferência dos enunciados (`specs/006-statement-fidelity/plan.md`, research R1–R8)**: comandos `check-statements` e `correct-statements` do módulo `dataset`; classificação das diferenças pelo elemento do original (sem lista de padrões); corrigido = texto atual com as marcações do original (S2, decidido por Milena); cópia dos blocos do enunciado versionada num pacote e páginas inteiras fora do Git (S1, decidido por Milena); equivalências das fórmulas medidas no piloto (S3) | 1, 3 |
| 2026-10-18 | **Clarify da conferência dos enunciados (`specs/006-statement-fidelity/spec.md`, Clarifications)**: E1 — os enunciados corrigidos são só gerados para revisão, numa pasta separada; aplicar ao dataset fica para uma decisão posterior dos autores, fora desta feature; E2 — uma página por vez, pelo menos 3 s entre pedidos, identificação do projeto, uma única vez (baixar de novo só com opção explícita); E3 — tabela vira tabela em Markdown e passa pelas três conferências, imagem vai para revisão manual; E4 — expoente `^{...}` e índice `_{...}`, sempre com chaves (`10^{5}`, `a_{i}`); os enunciados do formato novo, sem perda, ficam como estão | 1, 3 |
| 2026-10-18 | **Spec da conferência dos enunciados contra o original (`/speckit.specify` de `specs/006-statement-fidelity/`, Draft)**: comando do módulo `dataset` que obtém uma vez a página original de cada problema no Codeforces, guarda a cópia com hash e lista toda diferença para o `enunciado.md` (expoente, índice, fórmula, imagem, tabela, outra), sem lista de padrões; geração opcional dos enunciados corrigidos em Markdown (`^{...}`, `_{...}`), aceitos só com três conferências; aplicar ao dataset só por decisão dos autores. Quatro decisões para o clarify (E1 aplicar ou não; E2 ritmo de acesso; E3 imagens e tabelas; E4 formato da marcação) | 1, 3 |
| 2026-10-18 | **Piloto da comparação com o enunciado original do Codeforces**: piloto só de leitura com 5 problemas (`161_A`, `1_B`, `1000_B`, `15_A`, `102_B`), páginas originais do Codeforces baixadas uma vez (HTTP 200, guardadas em `data/cf_pilot/`, fora do Git). Dois formatos no HTML cru: o antigo marca expoente e índice com `<sup class="upper-index">` e `<sub class="lower-index">`, e o nosso `enunciado.md` perdeu os dois; o novo traz a fórmula crua (`$$$1 \le n \le 10^5$$$`, `$$$a_i$$$`), e o nosso texto preservou `10^5` e `a_i` (o que explica os 53 enunciados com o expoente certo). Perdas confirmadas pelo original: `161_A` 4 expoentes e 21 índices (`a_i` → `ai`), `1_B` 2 expoentes, `15_A` 6 índices, `102_B` 1 expoente (`10^100000` → `10100000`), `1000_B` nenhuma. Conclusões: (1) a contagem por padrão de texto (71) está incompleta (não viu `102_B`, porque só procurava expoentes de 2 a 18); (2) os índices também se perdem e não eram contados; (3) a comparação com o original é mecânica e não depende de uma lista de padrões, e passa a ser a fonte de verdade (feature `specs/006-...`, a especificar) | 1, 3 |
| 2026-10-18 | **A tentativa que gerou cada suíte, de uma vez (`specs/005-show-request`, FR-014, research R12; pedido dos autores)**: `show-request --model M --suite-attempts --output-dir DIR`. `show-request --model slm --suite-attempts` sobre a execução completa do SLM: 600 de 600 pedidos gravados, todos com o hash do prompt conferido e fiéis ao dataset, nenhum pulado nem recusado, aviso de expoente nos mesmos 71 problemas (142 combinações), cerca de 23 s; a tentativa que gerou a suíte foi a 1 em 355 combinações, a 2 em 84, a 3 em 32, de 4 a 12 em 127 e a 14 e a 15 (predição) em 1 cada; em `1000_B` caixa-preta (`accepted_fallback`) a suíte veio da tentativa 1, embora a última feita tenha sido a 12 | 3 |
| 2026-10-16 | **Visualização do pedido implementada e medida (`specs/005-show-request`, research R11)**: dry-run com gravação do GPT sobre os 200 problemas reais, antes da execução dele: 600 de 600 prompts fiéis ao dataset (enunciado, código e exemplo idênticos aos arquivos, sem código na caixa-preta nem enunciado na caixa-branca), 600 arquivos `.request.json` (4,8 MB) e aviso de expoente em 71 problemas (142 combinações), **exatamente** os 71 da contagem de 2026-10-16; dry-run do SLM: 0 combinações pendentes (execução terminada); `show-request` nas 15 combinações do piloto 1 do Gemini (`--suites-dir data/suites/gemini-piloto1`): 15 de 15 com o hash do prompt conferido e fiéis ao dataset; no SLM, as tentativas 1 e 12 de `1000_B` caixa-preta (seed 42 e temperatura 0,7; seed 48 e 0,2) e a tentativa 13 de `237_A` caixa-branca (texto-base de predição) conferidas; os pilotos 1 a 5 do SLM, de uma versão anterior do formato, são recusados (código 1); a busca no Git, no contêiner `app` com o `.git` somente leitura, achou pelo hash a versão mais antiga das 4 do `slm_prompt.txt`; prévia do GPT (`1_B` híbrido) e recusa de tentativa inexistente conferidas. O dry-run do Gemini fica com os autores. Testes: 1.868 passando (1.777 antes, 91 novos). O `.git` passou a ser montado somente leitura no serviço `app` | 3 |
| 2026-10-16 | **Analyze da visualização do pedido, decisões de Milena (`specs/005-show-request`)**: o dry-run grava um arquivo só por combinação, o corpo da requisição (o prompt vem dentro), em JSON legível e igual ao enviado; o `show-request` só grava (`--output` obrigatória), confere a fidelidade ao dataset e não imprime o pedido no terminal; o Gemini, com a execução já começada, é conferido num dry-run separado e a calibração dos 71 expoentes fica no GPT; o tempo não é medido | 3 |
| 2026-10-16 | **Analyze da visualização do pedido (`specs/005-show-request`, achado C1)**: a saída de `generate --dry-run --save-requests` passa a ser uma pasta plana por modelo (`<id>.<cenário>.prompt.txt` e `.request.json`), sem subpasta por problema; com subpasta, a regra da constitution exigiria uma camada no `cli check` para uma saída de consulta descartável | 3 |
| 2026-10-16 | **Plano da visualização do pedido (`specs/005-show-request/plan.md`, research R0–R10)**: o serviço `app` monta o `.git` somente leitura para achar no histórico o texto-base pelo hash (S1, decidido por Milena; o `sandbox` continua sem `.git`); o corpo de uma tentativa feita vem dos `request_parameters` gravados; o `generate --dry-run --save-requests DIR` grava `.prompt.txt`, `.request.json` (bytes exatos) e `summary.json`, com fidelidade conferida contra os bytes crus do dataset e aviso de expoente calibrado nos 71 problemas; pilotos lidos com `--suites-dir`. A nota da seção 3 deixa de citar um resumo da resposta (B3) | 3 |
| 2026-10-16 | **Clarify da visualização do pedido (`specs/005-show-request/spec.md`, Clarifications)**: B1 — os 3 modelos; B2 — o dry-run grava todos os pedidos numa pasta, com conferência de fidelidade ao dataset (enunciado, código e exemplo idênticos) e aviso de expoente perdido, e o `show-request` mostra no terminal ou grava com `--output`; B3 — só o que é enviado, sem a resposta do modelo; B4 — texto-base mudado: busca a versão antiga no Git pelo hash, senão recusa | 3 |
| 2026-10-16 | **Spec da visualização do pedido (`/speckit.specify` de `specs/005-show-request/`, Draft)**: comando de consulta que mostra o prompt e o corpo exatos de cada tentativa, ou a prévia do próximo pedido, sem chamar API nem gravar nada, conferindo o hash do prompt reconstruído contra o gravado; decidido reconstruir em vez de gravar o texto do prompt (opção A dos autores); quatro decisões para o clarify (B1 a B4: SLM, saída, resposta crua, texto-base mudado) | 3 |
| 2026-10-16 | **Expoentes perdidos nos enunciados (seção 3)**: contagem sobre os 200 `enunciado.md`: 71 (35,5%) perderam o expoente das potências de 10 no texto do dataset de origem (`10^5` → `105`, `10^9` → `109`), 53 o preservam e 76 não têm potência de 10. Afeta os cenários com enunciado (caixa-preta e híbrido) igualmente nos 3 modelos; limitação a registrar no TCC; o dataset não é corrigido. Achado ao inspecionar o prompt de `1_B` do piloto do Gemini | 1, 3 |
| 2026-10-16 | **Piloto 1 do Gemini (`specs/004-llm-test-generation/research.md` R15; relatório versionado em `manifests/gemini_generation_report.piloto1.json`)**: 15 combinações (os 5 problemas `1000_B`, `1005_C`, `1008_B`, `1_B` e `61_B` nos 3 cenários), 15 chamadas, todas com suíte na 1ª tentativa; nenhuma falha de formato, resposta cortada, resposta barrada ou bloqueio de segurança; `finishReason` `STOP` e `modelVersion` `gemini-3.8-flash` nas 15; saída por chamada (resposta mais raciocínio) média de 1.965 *tokens*, mediana 1.640, mínima 1.114 e máxima 3.551 (11% do teto de 32.768), dos quais raciocínio médio de 1.206 (de 334 a 2.845) e a resposta visível no máximo 894; 69.717 caracteres de prompt para 20.786 *tokens* de entrada devolvidos pela API (3,354 caracteres por *token*; a estimativa usava 3,0); suítes de 7 a 12 testes (mediana 10), 2 testes descartados por entrada vazia; tempo por chamada mediano de 13,1 s e máximo de 29,1 s; custo real US$ 0,126, contra US$ 1,86 a 5,58 estimados antes do piloto. Decidido: teto de saída mantido em 32.768; estimativa do Gemini com 3,354 caracteres por *token* e saída média de 1.965 (execução completa: US$ 4,97 a 222,84). Falta o piloto do GPT | 3, 6 |
| 2026-10-16 | **Conta paga no Gemini (decidido por Milena)**: o piloto e a execução completa do Gemini usam conta com faturamento ativo, como o plano previa; resolve a decisão em aberto da linha anterior sobre a camada gratuita (seção 6, item 32) | 3, 6 |
| 2026-10-16 | **Ritmo de pedidos e cota diária (`specs/004-llm-test-generation/research.md` R6, R7; spec FR-024)**: a primeira tentativa do piloto do Gemini, numa chave da **camada gratuita** (5 pedidos por minuto, 20 por dia, 250 mil *tokens* por minuto), mandou 4 pedidos ao mesmo tempo e recebeu HTTP 503 ("high demand") e 429 de cota seguidos; nenhuma resposta, nada gravado além do `run.json`, interrompida com `Ctrl+C`. Mudanças: limite opcional de inícios de pedido por minuto por modelo (`GEMINI_MAX_REQUESTS_PER_MINUTE`, `OPENAI_MAX_REQUESTS_PER_MINUTE`), que espaça os pedidos do processo, repetições incluídas; 429 de cota **diária** (`QuotaFailure` com `PerDay`) encerra o comando com código 3 em vez de esgotar as repetições; toda espera acaba na hora quando a invocação para. **A decidir pelos autores**: usar a camada gratuita no experimento (o plano previa conta com faturamento ativo, porque na gratuita o Google pode usar o conteúdo enviado; com 20 pedidos por dia, as até 1.800 chamadas da execução completa de um modelo levariam de 30 a 90 dias) | 3, 6 |
| 2026-10-16 | **Forma do JSON com schema no Gemini conferida na API (`specs/004-llm-test-generation/research.md` R3; plano, S4)**: antes do piloto, um pedido "hello world" com a configuração do experimento. A forma `generationConfig.responseFormat.text` da documentação atual, com o valor `"application/json"` do exemplo, foi recusada (HTTP 400, não cobrado: o `mimeType` é uma lista fixa de valores); a mesma forma com `"APPLICATION_JSON"` foi aceita, com JSON no schema, `finishReason` `STOP`, 309 *tokens* de raciocínio e `modelVersion` `gemini-3.8-flash`. O código usa essa forma (o plano B não foi necessário); a resposta real virou um teste | 3, 6, 7 |
| 2026-10-15 | **Implementação dos LLMs comerciais (`/speckit-implement` de `specs/004-llm-test-generation/`, T001 a T054)**: subpacote `src/ai_clients/llm/` (clientes HTTP da biblioteca padrão, interpretação, custo, estado por arquivos, coordenador com *threads*, teto de gasto, barreira de raciocínio, `close`, `change-template`, relatório, pacote, `verify`), `--model {slm,gpt,gemini}` nos comandos, leitor comum `SuiteView`, camadas `gpt_suites` e `gemini_suites` do `cli check`, `llm_prompt.txt` aprovado pelos autores; 1.765 testes passando, sem regressão no SLM; leitor comum conferido nas 600 suítes reais do SLM. Decisões da implementação: no `Ctrl+C` as chamadas em andamento são gravadas; texto que não é UTF-8 válido vira `schema_violation`. Dry-run real: 600 combinações por modelo, ~824 mil *tokens* de entrada (razão 3,0), maior prompt 7.459 caracteres, GPT US$ 89,09–267,28 e Gemini US$ 74,35–223,04 com a saída no teto. Pendentes: piloto pago (T055), decisão com os autores (T056), execução completa (T057) e fechamento | 3 |
| 2026-10-15 | **Análise de consistência dos LLMs comerciais (`/speckit-analyze` de `specs/004-llm-test-generation/`) e correções aplicadas**: a ausência de seed nos LLMs passa a constar no plano como desvio do Princípio II, justificado por escrito ("Complexity Tracking"); o teto de gasto vale por processo (dois `generate --resume` do mesmo modelo podem gastar a soma dos dois tetos; FR-022a); o pacote recusado por pendência é só o do modelo dela (FR-016); a tabela de preços não entra na comparação da retomada (entidade da spec); troca de texto-base dos LLMs com schema próprio (`LlmTemplateChange`), sem mudar o `AttemptKind` do SLM; tarefas novas de teste da barreira com chamadas em andamento, de leitura das 600 suítes reais do SLM pelo leitor comum (SC-007) e de verificação de que o módulo não executa código | 3 |
| 2026-10-15 | **Plano dos LLMs comerciais (`/speckit-plan` de `specs/004-llm-test-generation/`; `plan.md`, `research.md` R0 a R14, `data-model.md`, `contracts/`, `quickstart.md`)**: código em `src/ai_clients/llm/`, reaproveitando o SLM por importação sem mudar o comportamento dele; clientes HTTP da biblioteca padrão, sem SDK; `--model {slm,gpt,gemini}` nos comandos existentes; S1 — `LlmSuite` com as mesmas chaves de topo do SLM e leitor comum `SuiteView` (FR-017 e SC-007 reescritos); S2 — dry-run sem nenhuma chamada, tokens estimados pela razão caracteres/token (3,0 antes do piloto; FR-021 reescrito); S3 — `generateContent` mantido apesar do rótulo "Legacy" (risco registrado); forma REST atual do JSON com schema no Gemini (`generationConfig.responseFormat.text`, com o plano B `responseMimeType`); `--confirm-spend US$` como confirmação e teto de gasto; códigos de saída 5 (teto) e 6 (sem raciocínio); teto de saída provisório de 32.768; tabela de preços por data de validade; pacotes, manifestos, relatórios e camadas do `cli check` por modelo | 3, 6 |
| 2026-10-15 | **Terceiro clarify dos LLMs comerciais (`specs/004-llm-test-generation/spec.md`, Clarifications, sessão 2026-10-15)**: A11 — prompt inteiro numa única mensagem de usuário, como no SLM, sem instrução de sistema nas duas APIs; A12 — barreira automática em toda execução, nos dois modelos: resposta com zero tokens de raciocínio (ou sem a contagem) gravada fora das tentativas, nenhuma chamada nova e saída com código próprio até os autores investigarem (FR-018a; antes era só conferência do piloto); A13 — o Gemini não recebe `safetySettings` (padrão da API), com bloqueios gravados por categoria e revisão da decisão se o piloto mostrar bloqueios | 3, 6 |
| 2026-10-15 | **Gemini trocado de `gemini-3.6-flash` para `gemini-3.8-flash` (A3 revista; `specs/004-llm-test-generation/research.md`, fontes oficiais acessadas em 2026-10-15)**: o `gemini-3.5-flash` do desenho aprovado foi descontinuado em 2026-10-08 e é redirecionado para o 3.6; entre os substitutos, os autores escolheram o Flash GA mais recente em vez do 3.6, que o Google descreve como "previous-generation". O 3.8 Flash é GA desde 2026-09-02, sem identificador datado (proveniência pelo `modelVersion`), com `thinking_level` `low`/`medium`/`high` e padrão `medium` (sem `minimal`). Preço: US$ 0,75 / 3,75 / 0,075 por milhão de tokens (entrada / saída com raciocínio / cache) até 2026-12-31, e 1,50 / 7,50 / 0,15 a partir de 2027-01-01. Nova divergência em relação ao PDF (seção 7, item 41). Conferências do piloto: `modelVersion` do 3.8 e `thoughtsTokenCount` maior que 0 | 0, 3, 6, 7 |
| 2026-10-15 | **Parametrização dos LLMs comerciais decidida (A3; `specs/004-llm-test-generation/research.md`, fontes oficiais acessadas em 2026-10-15)**: sem seed nem temperatura nos dois modelos. GPT: snapshot `gpt-5.4-mini-2026-03-17`, Responses API, `store: false`, `reasoning.effort: "medium"` explícito (o padrão do modelo é `none`), `text.format` `json_schema` com `strict: true`. Gemini: `gemini-3.6-flash` no lugar do Gemini 3.5 Flash do texto do TCC (descontinuado em 2026-10-08 e redirecionado para o 3.6), `generateContent`, `thinking_level: "medium"` explícito, temperatura no padrão 1,0, saída JSON com schema. Nomes dos parâmetros atualizados em relação à Tabela 2 do PDF (`reasoning_effort` → `reasoning.effort`; `mimeType` → `responseMimeType`). Cada tentativa grava o modelo e a versão devolvidos, os parâmetros e a resposta crua; não reprodutibilidade bit a bit declarada como limitação. A conferir no piloto: tokens de raciocínio maiores que 0 no GPT e `modelVersion` do Gemini | 0, 3, 6 |
| 2026-10-15 | **Segundo clarify dos LLMs comerciais (`specs/004-llm-test-generation/spec.md`, Clarifications, sessão 2026-10-15)**: A7 — um pacote por modelo, com manifesto e relatório próprios (as pendências de um modelo não bloqueiam o outro); A8 — teto de gasto obrigatório por invocação, junto com a confirmação; atingido, nenhuma chamada nova sai, o comando sai com código próprio e a retomada continua (FR-022a); A9 — piloto descartado para a execução completa, que começa do zero, e só o relatório do piloto é versionado (FR-023a); A10 — sem campo de cálculo por teste no schema, e o cálculo fica no raciocínio interno do modelo. A3 continua para o plano | 3, 6 |
| 2026-10-13 | **Clarify dos LLMs comerciais (`specs/004-llm-test-generation/spec.md`, Clarifications)**: A1 — 3 tentativas por falha de formato; esgotadas, a combinação aguarda os autores e só fecha como `discarded_manual` com motivo; A2 — entradas com no máximo cerca de 50 elementos e 20 linhas, o mesmo do prompt principal do SLM, sem número fixo de testes; A4 — código em `src/ai_clients/`, com escolha do modelo nos comandos existentes; A5 — chamadas simultâneas configuráveis por modelo (padrão 4), trava por combinação, 429 como falha de infraestrutura; A6 — `accepted_predicted` em toda suíte dos LLMs, com o item 31 reescrito (comparação por modelo; só dentro do SLM as previstas ficam separadas). A3 (seed e temperatura) fica para o plano | 3, 6 |
| 2026-10-13 | **Spec dos LLMs comerciais (`/speckit.specify` de `004-llm-test-generation`, Draft)**: GPT-5.4-mini e Gemini 3.5 Flash, 200 problemas × 3 cenários × 2 modelos (1.200 combinações); oráculo por predição como única diferença intencional em relação ao SLM (mesmo `<context_data>`, few-shot e regras de entrada do prompt principal do SLM; D1); novas tentativas só por falha de formato, sem validação pelos testes públicos (D2); temperatura no padrão de cada API e esforço de raciocínio `medium` (D3); mesmo `suite.json` do SLM (D4); dry-run de custo e confirmação explícita a cada invocação (D5); few-shot e versionamento como no SLM (D6). Seis decisões abertas para o clarify (A1 a A6, seção 6, item 32) | 3, 6 |
| 2026-10-11 | **Pacote do SLM gerado e módulo `ai_clients` (modelo local) fechado (`research.md` R28)**: `python -m ai_clients package` sobre o código de `f43d95c` gerou `data/slm_suites.zip` (6.597.040 bytes, SHA-256 `b73d27507f74…`, 4.850 arquivos: as 600 combinações, o `run.json`, a troca de template `001` e os 3 arquivos de `superseded/001/`), `manifests/slm_suites.manifest.json` e o relatório final (commit `c967f97`); `verify --extracted data/suites/slm` `OK`; `cli check --deep` `OK` sem aviso (SHA-256 dos 4.850 arquivos e do zip conferido); suíte completa `1498 passed`; quickstart validado; Constitution Check refeito; `check_docs_sync.py --closing` do módulo e da feature sem achados; código gerado com apoio de IA revisado por Milena em 2026-10-11. README do módulo `implementado` e spec `Implemented` | 3, 8 |
| 2026-10-11 | **Fechamento da documentação do SLM**: seção 3 reescrita com o desenho final no texto principal (modelo `qwen2.5-coder:14b` no lugar do 7B, que fica só como histórico dos pilotos 1 a 3; política de 5 fases com os status e as 4 razões de falha; `cli check` até 15 tentativas); promessas "medir no piloto" fechadas com os valores medidos (maior `prompt_eval_count` 2.499; chamada mais longa 446 s, contada nos arquivos de tentativa, pois o relatório só traz a soma; `runtime_error` 282 sem separar RE de MLE, por não ser separado no relatório; `Ctrl+C`/`--resume` com o Ollama real observado: 44 interrupções nos logs, estado final sem perda nem dano); regras anteriores marcadas como substituídas, não apagadas. **Correção do motivo da troca de template**: o `reason` de `template_changes/001.json` estava gravado por engano como `"..."` e foi reescrito antes do `package` (só esse campo, conferido pelo schema, gravação atômica, demais campos iguais; nenhum hash dependia dele); `report` refeito. **Nota de hardware (decisão de Milena)**: os arquivos não mudam; as 2.185 chamadas têm a mesma etiqueta de hardware (GPU T4, 16GB RAM), mas a execução usou mais de uma máquina (2×T4, mesmo modelo de GPU, mesma versão do Ollama e mesmo digest), sem impacto nos resultados. Seção 6: itens 2, 26 e 31 atualizados; seção 7: itens 28/29 atualizados para o desenho final, item 30 duplicado renumerado (31) e itens 32–40 novos; relatórios dos pilotos 2 e 3 versionados em `manifests/` | 0, 3, 6, 7, 8 |
| 2026-10-11 | **Execução completa do SLM terminada (`research.md` R28; `manifests/slm_generation_report.json`)**: continuação da execução do piloto 6 (primeira chamada 2026-10-06T23:40:40Z, última 2026-10-09T17:40:40Z), `qwen2.5-coder:14b` digest `9ec8897f…`, Ollama 0.35.0, templates `fc9757e8…` (solução) e `421adf86…` → `e52133f6…` (predição). **600 de 600 com suíte**: 505 `accepted` (84,2%), 93 `accepted_fallback` (15,5%; 65 na caixa-preta), 2 `accepted_predicted` (`939_C` caixa-preta, `237_A` caixa-branca), 0 `discarded_manual`, 0 aguardando (o `close` não foi necessário). Fases: 480 / 25 / 93 / 2 (355 na tentativa 1). 2.185 chamadas, 1.678 falhas (76,8%: `public_test_failed` 1.554, `unparseable_response` 102, `repetition` 21, `all_inputs_failed` 1); 77 cortadas por `length`; entradas descartadas: `runtime_error` 282, `timeout` 47; maior `prompt_eval_count` 2.499; ≈ 37,5 h de modelo (tempo de relógio não medido); suítes com mediana 10. Uma troca de template (2026-10-08, `939_C` caixa-preta refeita: tentativa 13 de novo até o teto, 15 aceita com 10 testes). `cli check` OK; `package`, `verify --extracted` e `cli check --deep` pendentes | 3, 6, 7 |
| 2026-10-08 | **Troca do template de predição executada (`research.md` R27/R28)**: `change-template` às 11:49:11Z (`421adf86…` → `e52133f6…`) moveu 3 arquivos da `939_C` caixa-preta para `superseded/001/`; refeita no mesmo dia com as seeds 49 a 51 (13 até o teto de 5.120 *tokens*, 14 não interpretada, 15 `accepted_predicted` com 10 testes) | 3 |
| 2026-10-08 | **Correção das travas da execução concorrente (`research.md` R24)**: um `execute` rodando junto dos `generate` criou, como root, 5 arquivos de trava que o `generate` não conseguia abrir (`PermissionError`); toda trava passa a ser entregue ao usuário do host, como os demais arquivos; as 6 travas existentes foram corrigidas; nenhum dado afetado. | 3 |
| 2026-10-07 | **Troca do template de predição (`research.md` R27)**: 1 de 594 combinações tinha passado pela predição (`939_C` caixa-preta, `accepted_predicted` com entrada abreviada); STEP 2 novo (até 10 elementos e 10 linhas por entrada, sem sequências longas); comando `change-template` registra a troca e move as tentativas da versão antiga para `superseded/`, refeitas com as mesmas seeds; hash do template por tentativa; testes abreviados descartados na predição (0 falsos positivos em 47.492 textos do dataset); pacote, relatório e `cli check` com as trocas. | 3 |
| 2026-10-07 | **Divisão automática do trabalho entre as GPUs (`research.md` R26)**: com metades fixas uma GPU ficava parada enquanto a outra tinha fila; o laço do README do módulo dá todos os problemas aos dois `generate --resume`, e a trava por combinação (R24) os faz dividir a fila sozinhos (`skipped` passa a ser o esperado); nenhum código nem dado do experimento muda; teste novo em `test_concurrency.py`. | 3 |
| 2026-10-07 | **Resposta do Ollama em *streaming* (`research.md` R25)**: `stream: true`, pedaços juntados e métricas do último (registro idêntico ao sem *streaming*); resposta incompleta é falha de infraestrutura; `OLLAMA_HTTP_TIMEOUT_S` = maior silêncio entre pedaços; `run.json` inalterado e `--resume` aceita a execução atual; motivo: HTTP 524 do Cloudflare em chamadas de mais de ~100 s | 3 |
| 2026-10-07 | **Execução concorrente do SLM para duas GPUs (`research.md` R24)**: trava compartilhada para `generate --resume`/`execute`, trava por combinação (a combinação em uso é pulada e contada), `close`, `package` e o primeiro `generate` exclusivos, um `execute` por vez; laço em bash das duas GPUs no README do módulo; os dados gravados não mudam | 3 |
| 2026-10-07 | **Piloto 6 do SLM e decisão da execução completa (`research.md` R23)**: 15 de 15 combinações com suíte (13 `accepted`, 12 na fase 1 e 1 na fase 2; 2 `accepted_fallback`), 57 chamadas, 13 aceitas (22,8%), 44 falhas (35 WA, 8 RE, 1 `all_inputs_failed`), mediana de 43 s (máximo 166 s), ≈ 46 min; de 5 a 10 entradas por resposta e suítes de 4 a 10; `1005_C` caixa-preta aceita na fase 2 (tentativa 8, 0,6); reservas `1000_B` pela tentativa 1 e `1008_B` pela tentativa 9 (fase 2, temperatura 0,5), a que passou mais testes públicos; código `e69d2fe`, 14B digest `9ec8897f…`, etiqueta GPU T4, 16GB RAM; fases 4 e 5 não exercitadas. Decidido: configuração congelada; a execução completa continua a mesma execução com `--resume` até 600; duas GPUs T4 com dois `generate` em paralelo sobre metades disjuntas; determinismo entre GPUs não medido | 3 |
| 2026-10-06 | **Política de 5 fases implementada (`research.md` R22)**: tabela `ATTEMPT_POLICY` por extenso no código (seeds 42–47 a 0,7; seed 48 de 0,7 a 0,2; predição 49–51 a 0,7), gravada no `run.json` e conferida em cada tentativa; `schema_version` 2 e recusa das execuções anteriores com código 2; reserva só depois da 12ª; entradas só depois de WA; cerca removida em `<input>`/`<output>` da predição; relatório com `acceptance` e `per_phase`; saem `OLLAMA_TEMPERATURE`, `OLLAMA_SEED_BASE` e `accepted_low_confidence`. Testado com modelo e execução simulados; nenhum número medido com o modelo real | 3 |
| 2026-10-06 | **Desenho técnico da política de 5 fases (`research.md` R22, ainda não implementado)**: motivo, pelos pilotos 4 e 5: as falhas foram quase todas WA repetidas em várias seeds a 0,7, e as tentativas extras e a baixa confiança nunca foram exercitadas; tabela `ATTEMPT_POLICY` por extenso no código e no `run.json`, conferida em cada tentativa; `schema_version` 2 e recusa das execuções anteriores (mover `data/suites/slm` antes do piloto 6); cerca removida em `<input>`/`<output>` da predição; relatório com a fase e a tentativa de aceitação por cenário e chamadas, *tokens* e tempo por fase | 3 |
| 2026-10-06 | **Política de 5 fases do SLM (`research.md` R21, ainda não implementada)**: fase 1, tentativas 1–6 com seeds 42–47 e temperatura 0,7; fase 2, tentativas 7–12 com seed 48 e temperatura de 0,7 a 0,2; fase 3, reserva entre as 12; fase 4, predição nas tentativas 13–15 (seeds 49–51, 0,7); fase 5, tratamento manual. Substitui as tentativas extras, a baixa confiança e o piloto de temperaturas; saem `OLLAMA_TEMPERATURE`/`OLLAMA_SEED_BASE`; entradas rodam só depois de WA; é a política do experimento, validada no piloto 6 | 3, 6 |
| 2026-10-06 | **Piloto 5 do SLM, modelo 14B e desenho do piloto 6 (`research.md` R20)**: com o 14B e a regra nova, 15 de 15 combinações com suíte (13 `accepted`, 2 `accepted_fallback`), 13/49 tentativas aceitas, 36 falhas todas em teste público (29 WA, 7 RE), mediana de 48 s por chamada (máximo 179 s), ≈ 44 min; maior `prompt_eval_count` 2.262; de 3 a 16 entradas por resposta e suítes de 5 a 16; mediana de 703 *tokens* de saída; código `7535dee`, GPU T4; baixa confiança, predição e tratamento manual não foram exercitados. Decidido: modelo do experimento `qwen2.5-coder:14b` (itens 30 da seção 6 e da seção 7); `accepted_fallback` entra nas métricas como `accepted`, baixa confiança e predição separadas (item 31); piloto 6 de temperatura (0,2 a 0,7) e seeds antes da execução completa, com `OLLAMA_TEMPERATURE` e `OLLAMA_SEED_BASE` opcionais no `.env` | 3, 6, 7 |
| 2026-10-06 | **Regra "nenhuma combinação sem suíte" implementada (`research.md` R19)**: tentativas 1 a 23 (21 a 23 por predição, com `slm_predict_prompt.txt`, 2.333 caracteres), entradas rodando depois de qualquer reprovação em teste público, status `accepted_low_confidence`, `accepted_predicted` e `discarded_manual` (sai `discarded`), código de saída 4 e comando `close`, relatório por status, `cli check` até 23 tentativas. Testado com modelo e execução simulados (1.401 testes do projeto passando); nenhum número medido com o modelo real | 3 |
| 2026-10-06 | **Plano técnico da regra "nenhuma combinação sem suíte" (`research.md` R19, ainda não implementado)**: tentativas 1 a 23 num único contador (21 a 23 por predição, seeds 63 a 65); `<test>` com entrada ou saída vazia descartado sozinho; segundo template no `run.json`; código de saída 4 para combinação aguardando tratamento manual; comando `close` com motivo e data gravados; relatório com proporção por status. Custo da execução das entradas depois de TLE não medido | 3 |
| 2026-10-06 | **Nenhuma combinação do SLM sem suíte (`research.md` R18, ainda não implementado)**: tentativas 1 a 8 (`accepted`), reserva `accepted_fallback`, tentativas 9 a 20, depois `accepted_low_confidence` (primeira das 20 que manteve uma entrada, mesmo com RE/TLE/MLE num teste público), depois até 3 tentativas por predição com um segundo template (`accepted_predicted`, entradas e saídas escritas pelo modelo, sem validação); sem resposta interpretável, a combinação aguarda tratamento manual e só fecha como `discarded_manual` com motivo, por comando dos autores. Relatório e métricas separados por status; item 31 decidido em parte | 3, 6 |
| 2026-10-06 | **Template do SLM revisto depois do piloto 4 (`research.md` R17)**: texto trocado inteiro (SHA-256 `fc9757e8…`, era `336634f7…`); blocos pedidos na ordem análise, solução, entradas, e o parser passa a exigir essa ordem; instrução para inferir o comportamento pelo código na caixa-branca; solução mais simples possível, num script plano com toda variável definida; entradas sem contagem pedida (eram de 10 a 20), com no máximo ≈ 50 elementos e 20 linhas (eram ≈ 100 elementos) e sem repetição. Efeito não medido | 3 |
| 2026-10-05 | **Piloto 4 do SLM e suíte de reserva (`research.md` R16)**: com `qwen2.5-coder:14b`, 13 de 15 suítes aceitas (caixa-preta 3/5), 13 de 40 tentativas aceitas (32,5%), 27 falhas todas em teste público (16 WA, 11 RE), mediana de 76 s por chamada (máximo 252 s), mediana de 1.082 *tokens* de saída (máximo 2.009), de 10 a 21 entradas por resposta, nenhuma resposta não interpretada; as 2 descartadas (`1000_B` e `1008_B`, caixa-preta) erraram por WA em 11 de 12 tentativas. Decidido que nenhuma combinação fica sem suíte: 8 tentativas estritas (era 6); depois, a melhor tentativa que reprovou um teste público só por WA e manteve entradas vira suíte `accepted_fallback` (as entradas passam a rodar depois de um WA); sem nenhuma, tentativas 9 a 12; descarte só depois de 12. Relatório com `accepted_fallback` e `fallback_rate`; `cli check` aceita até 12 tentativas. Pendente como as métricas tratam as reservas (item 31) | 3, 6 |
| 2026-10-05 | **Piloto 3 do SLM (parcial) e piloto com outro modelo (`research.md` R15; relatório versionado em `manifests/slm_generation_report.piloto3.json`)**: `qwen2.5-coder:7b`, template `336634f7…`, GPU T4; interrompido pelos autores em 37 tentativas, 5 aceitas (5 combinações aceitas: `1005_C` caixa-preta e híbrido, `61_B` nos 3 cenários; as outras 10 paradas com 3 de 6 tentativas, todas falhas); com o template revisto, nenhuma resposta não interpretada ou cortada, de 10 a 20 entradas por resposta, mediana de 1.001 *tokens* de saída, chamada mais longa 131 s, maior `prompt_eval_count` 2.393, acerto por tentativa de 11% para 14% (caixa-preta de 3% para 18%); as falhas continuam sendo a solução Python nos testes públicos (17 WA, 15 RE: 7 `ValueError`, 4 `NameError`, 2 `IndexError`, 1 `UnboundLocalError`, 1 `KeyError`; nenhum perto do limite de memória), com projeção de ≈ 40% das combinações sem suíte e ≈ 20 h. Critério sugerido para depois do piloto 4: se o 14B deixar mais de ≈ 20% das combinações sem suíte, discutir a opção de o SLM prever as saídas como os dois modelos comerciais (sem descarte; saídas erradas viram falsos positivos). Bug corrigido: o Python rodava com `-S`, e `exit()` não existia (3 RE). Decidido: encerrar o piloto 3 e rodar o piloto 4 com `qwen2.5-coder:14b` via `OLLAMA_MODEL` (opcional no `.env`); modelo e método do experimento pendentes (item 30) | 3, 6 |
| 2026-10-05 | **Piloto 2 do SLM registrado e decisões (`research.md` R14; relatório versionado em `manifests/slm_generation_report.piloto2.json`)**: executado em 2026-10-04 com `qwen2.5-coder:7b`, template `061b7427…`, Ollama 0.35.0, GPU T4; 5 problemas × 3 cenários, 74 tentativas; suítes aceitas 1/5 (caixa-preta), 3/5 (caixa-branca), 4/5 (híbrido); as 7 descartadas caíram todas porque a solução Python errou um teste público (33 WA, 29 RE, 1 TLE no total), nenhuma por causa das entradas; maior `prompt_eval_count` 2.170, mediana de 29 s por chamada, a mais longa 233 s; `1_B` (61 MiB) reprovou nas 18 tentativas. Decidido: o `AC_ref` nunca gera saídas esperadas; cada tentativa continua independente (sem reaproveitar entradas); orçamento mantido em 6; o `execute` passa a gravar o início do `stdout`, o final do `stderr`, o tempo e a memória do teste público que reprova. **Template revisto** (R14, item 6): planejar e simular à mão no exemplo antes do código, de 10 a 20 entradas distintas escritas por extenso, sem pedido de entradas inválidas nem menção a entrada vazia, dicas de Python; maior prompt 8.993 caracteres, `num_ctx`/`num_predict` sem mudança. Próximo: piloto 3 (execução nova, mesmos 5 problemas) | 3 |
| 2026-10-04 | **Revisão depois do piloto 1 do SLM (`research.md` R13)**: piloto de 2026-10-01 a 2026-10-03, com `qwen2.5-coder:7b` (hardware não registrado em R13), 4 problemas × 3 cenários (`1000_B`, `1005_C`, `1008_B`, `1_B`): 5 suítes aceitas e 7 descartadas; mais 2 combinações de `1009_B` deixadas incompletas (começadas por um `generate` sem `--problem` interrompido à mão: caixa-preta com a tentativa 1 esperando `execute`, caixa-branca com 2 tentativas não interpretadas); 57 chamadas, maior `prompt_eval_count` 2.044, chamada mais longa 166 s; 6 respostas não interpretadas (3 `unclosed_block:inputs`, todas cortadas por `done_reason = "length"` — 2 no híbrido, 1 na caixa-branca —, e 3 `empty_input`); 31 reprovações em teste público por WA e 14 por RE (6 delas causadas por cerca Markdown, todas no híbrido, `SyntaxError`); um HTTP 500 `token repeat limit reached` repetiu a mesma seed até o teto de 30, sem gravar nada. Decidido: remover só a cerca que envolve o código inteiro (registrada); descartar `<input>` vazio sozinho; `token repeat limit reached` vira a razão de falha `repetition` (próxima seed); RULE 2 com no máximo ~100 elementos por entrada e sem "including empty input"; `num_predict` 5120 (razão mínima medida de 3,32 caracteres por *token*); relatório por cenário; o `next:` do `execute` repete o `--problem`/`--scenario` usado. O piloto 2 começa uma execução nova | 3, 7 |
| 2026-10-01 | **Piloto do SLM, achado de infraestrutura**: a queda do túnel do ngrok (HTTP 404 com `ERR_NGROK_3200`) parava o `generate` como erro de configuração; passa a ser falha de infraestrutura, que espera e repete a mesma chamada com a mesma seed, sem gastar tentativa. Nada foi gravado na ocorrência | 3 |
| 2026-10-01 | **Relatório, pacote e camada `slm_suites` do `cli check` implementados (módulo `003-slm-test-generation`, testes com dados sintéticos)**: relatório versionável com as somas de controle validadas (estados somam o total do escopo, N nunca reduzido; funil soma as tentativas falhas); pacote determinístico só da execução completa; na camada nova do `cli check`, o que ainda falta é aviso até o pacote existir (divergência do plano, que pedia falha com `--deep` e tornaria impossível o primeiro passo do piloto e da execução completa). Nenhum dado medido | 0.1, 3 |
| 2026-10-01 | **Retomada e detecção de dano do módulo `003-slm-test-generation` implementadas (testes com cliente e executor falsos)**: interrupção em qualquer ponto de gravação seguida de nova execução reproduz a árvore de uma execução sem interrupção; `--resume` recusa diferença em qualquer campo do `run.json` exceto `created_at` (etiqueta de hardware e esperas do `.env` ficam de fora, como decidido); combinação cujos arquivos não batem (tentativa faltando, seed ou `digest` divergente, `suite.json` diferente do recalculado) é reportada e nunca consertada (código 1). Nenhum dado medido | 3 |
| 2026-10-01 | **Fase de execução do módulo `003-slm-test-generation` implementada (`python -m ai_clients execute`, testes com executor Python falso e 11 testes de integração no motor real)**: a solução Python do modelo passa pelos testes públicos (curto-circuito no primeiro não-AC) e depois roda em cada entrada gerada; vereditos sempre pelo `judge_test` do motor com tempo × 10 e memória × 4; nas entradas geradas só TLE e MLE/RE descartam (a saída não tem com o que ser comparada); o `execute` não lê o `AC_ref.cpp`; *surrogate* avulso na resposta do modelo vira erro de execução, não falha do comando. Nenhum número medido ainda: o piloto com o Ollama real vem a seguir | 3 |
| 2026-09-30 | **Primeira execução real de `python -m ai_clients generate --dry-run` (módulo `003-slm-test-generation`, fase de geração implementada com cliente Ollama falso nos testes)**: 600 chamadas previstas; maior prompt montado pelo código 8.118 caracteres (híbrido, `61_B`), acima dos 7.870 medidos no plano por causa da redação final do template e dos sub-rótulos do `<context_data>`; `num_ctx 8192` / `num_predict 4096` continuam suficientes (≈ 7.350 *tokens* no pior caso, estimativa pessimista) | 3 |
| 2026-09-30 | **Revisão de consistência dos artefatos de `003-slm-test-generation` (`/speckit.analyze`)**: falha de infraestrutura na chamada ao Ollama continua sem consumir tentativa (mesma seed), agora com teto de repetições consecutivas e *timeout* de leitura configuráveis no `.env` (padrões 30 e 900 s), porque um *timeout* fixo curto para Ollama em CPU viraria repetição infinita; `digest` do modelo gravado também em cada tentativa; `python -m cli check --deep` passa a ser o primeiro passo obrigatório do piloto e da execução completa; registrada na spec a terceira pergunta de esclarecimento (falha de infraestrutura mantém a seed), que tinha ficado de fora | 3 |
| 2026-09-30 | **Decisões pendentes do plano de `003-slm-test-generation` fechadas (Milena)**: amostragem do SLM `temperature 0.7`, `top_p 0.8`, `top_k 20`, `repeat_penalty 1.05` (item 27); template do prompt ajustado para FR-007 — maior caso escrito por inteiro, todo valor dentro das restrições (item 28); casos das suítes no contrato `TestCase` (`input`, `output`), a adotar também pela avaliação e pelos modelos comerciais (item 29); leitura do problema composta no módulo `ai_clients`, sem leitor novo no `dataset` | 3, 6, 7 |
| 2026-09-30 | **`/speckit.plan` do módulo `003-slm-test-generation`**: medido o tamanho do prompt montado nos 200 problemas × 3 cenários (maior: 7.870 caracteres, híbrido `61_B`) e fixados `num_ctx 8192` / `num_predict 4096` com guarda de truncamento; chamada `/api/chat` com uma única mensagem; seeds 43 a 48; Python na sandbox com tempo × 10 e memória × 4 do limite do problema (7 problemas têm 61 MiB), só biblioteca padrão; estados por arquivos imutáveis com `--resume` explícito; casos no contrato `TestCase` existente. Achados: `temperature 0` anularia as retentativas (amostragem fica PROPOSTA, item 27); o template do prompt não cumpre FR-007 (item 28); o módulo de avaliação não tem schema de suíte (item 29). Corrigida a contagem de razões de descarte de tentativa, de 4 para 3, conforme a clarificação de 2026-09-29. Detalhes em `specs/003-slm-test-generation/{plan,research,data-model}.md` | 3, 6, 7 |
| 2026-09-29 | **Seção 3 fechada para o SLM (`/speckit.specify` do módulo `003-slm-test-generation`)**: resolvido o "Ponto em aberto" sobre o detalhamento operacional do oráculo por execução — duas fases (geração com rede, sem executar; execução em sandbox sem rede, preenchendo `expected_output`), até 6 tentativas por problema × cenário (seed base + número da tentativa), descarte de entrada isolada vs. de tentativa inteira, falha de infraestrutura não consome tentativa, suíte descartada continua no N = 200 com taxa de descarte reportada à parte; resposta do SLM em texto com 3 blocos marcados (não JSON, D1); few-shot usa o primeiro teste público do próprio problema (D2); suítes seguem a exceção de versionamento dos mutantes, emenda 1.6.0, sem precisar de nova emenda (D3); parametrização de GPT-5.4-mini e Gemini 3.5 Flash e a regra de tamanho/normalização de suíte entre os 3 modelos permanecem pendentes (item 26 de 6). Decisões D1–D3, com proveniência completa, em `specs/003-slm-test-generation/spec.md` | 3, 6, 7 |
| 2026-09-25 | **Módulo `mutation` concluído oficialmente (`Status: Implemented`, commit `6e4528a`, revisão de código dos autores feita)**: pacote (`data/mutants.zip`, 9,06 MiB, 20.000 mutantes), manifesto e relatório gerados e versionados; `verify` e `python -m cli check --deep` `OK`; MS calculado sobre os 200 problemas (0 exclusões); conferência de consistência movida para o pacote `src/cli` (`python -m cli check`) e `scripts/verify_dataset.py` deixa de ser o comando documentado (`python -m dataset verify`); READMEs de `dataset` e `mutation` reescritos em dois cenários (do zero / descompactar) com uma tabela de comandos e sem citação ao processo de especificação, checagem automática C8 e Constitution 1.7.0 | 0.1, 2, 2.11 |
| 2026-09-25 | **Verificação de consistência entre artefatos**: novo comando `python -m cli check` (na época `scripts/check_consistency.py`, movido para `src/cli` no fechamento) (dataset descompactado × mutantes, por nomes e contagens, 1:1 nos dois sentidos; `--deep` confere os hashes), documento `docs/verificacao-consistencia.md`; esclarecido que `dataset verify` sem `--extracted` só confere o zip e que `data/dataset/` só existe depois de um `unzip` manual (passo final do fluxo "gerar do zero"); executado sobre os dados reais: OK | 0.1, 1.6 |
| 2026-09-25 | **Execução real da geração de mutantes (`generate --workers 4`, 200 problemas) e revisão do relatório**: 200 completos, 0 excluídos, 20.000 mutantes em ~7 h 26 min; 56,5% dos problemas só de primeira ordem (SC-003 não se confirmou), 15,3% dos mutantes de ordem superior (9 de terceira, em `981_B`), 3,9% de candidatos que não compilam, 26,2% equivalentes; o tempo por problema do log inclui a espera na fila; a revisão do código foi retirada do relatório e dos comandos (`--code-revision` removido, a pedido dos autores; spec FR-013 revisado) | 2.6, 2.11, 7 |
| 2026-09-24 | **Histórias 3 e 4 de `002-mutant-generation` (`package`, `verify`, `report`) e recuperação validada**: layout do zip `mutants/problems/<id>/` (mesmo caminho de consumo do `generate`), relatório com contagem de problemas (só primeira ordem / ordem superior / excluídos), revisão do código passada de fora (`--code-revision`, os contêineres não têm `.git`); falha achada e corrigida na interrupção com trabalhadores (`close` esperava minutos); recuperação validada com o motor real (SIGINT em 1 s; SIGKILL e retomada sem perda nem refazer o que estava fechado); `report`/`package`/`verify` executados de verdade sobre 2 problemas reais (`research.md` R19, R20) | 2.6, 2.10 |
| 2026-09-24 | **História 2 de `002-mutant-generation` implementada (ordem superior determinística e exclusão com alerta) e piloto R4 medido**: pares/trios de mutantes de primeira ordem aceitos em `itertools.combinations`, sítios distintos e disjuntos, exclusão com alerta e código de saída `0`; os 3 problemas mais esparsos fecham só com pares (76% a 83% dos mutantes de segunda ordem, 371 a 425 s), sem alertas; decisão: sem orçamento de tentativas (`research.md` R17, R18) | 2.4, 2.9 |
| 2026-09-24 | **Redução dos erros de compilação e paralelização de `generate` (`002-mutant-generation`)**: filtro sintático de sítios de E/S de fluxo, de operandos de texto/manipuladores, de ABS sobre tamanhos e de `++`/`--` sobre não atribuíveis (24% de candidatos que não compilavam em 5 problemas; depois: 0%, 1% e 17% nos três re-medidos; candidatos brutos: mediana 274 → 198, 8 → 34 problemas abaixo de 100); `--workers` com paralelismo entre problemas (R14 aprovada) | 2.2, 2.7, 2.8 |
| 2026-09-24 | **Primeira história de `002-mutant-generation` implementada (`generate`, primeira ordem)**: deslocamentos como AOR, operandos de ABS/UOI e unário legal por operador pai, execuções de estabilidade sobre um binário compilado uma vez, duplicata = todo texto já avaliado (`research.md` R8 a R12); medição sobre os 200 `AC_ref.cpp` reais: mediana de 274 candidatos de primeira ordem brutos, 8 de 200 com menos de 100; medição de custo em `189_C` (aceitação de 24% nos primeiros 83 candidatos, compilação de ~1,8 s) e duas gerações independentes de `189_C` com resultado idêntico (0 de 100 mutantes divergentes, R15) e geração completa medida (795 s, 100 mutantes, 41,5% de aceitação, antes do filtro de fluxo); paralelização (R14) aprovada, implementada e validada em 8 problemas (0 de 800 mutantes divergentes, aceleração de 2,07× com 4 trabalhadores, erros de compilação em 4,5% dos candidatos); fluxo de circulação dos mutantes (quem gera / quem só recebe; caminho único `data/mutants/problems/`) fixado em 2.6. Decisão D1–D6 sem alteração | 2.2, 2.3, 2.8, 7 |
| 2026-09-23 | **`/speckit.plan` do módulo `002-mutant-generation`**: confirmação empírica de que `tree-sitter-cpp` disambigua corretamente o `>>` de template do `>>` de operador, testada sobre um `AC_ref.cpp` real do dataset (`175_B`); escopo de ABS/UOI definido como os operandos de sítios ROR/AOR, sem precisar de inferência de tipo; MS (5.2) passa a ser calculado sobre os problemas com mutantes completos (pode ser < 200), nunca TDF/TFP. Detalhes em `specs/002-mutant-generation/{plan,research,data-model}.md` | 2.1, 5.2 |
| 2026-09-23 | **Seção 2 reescrita (`/speckit.specify` do módulo `002-mutant-generation`)**: geração de mutantes por AST (`tree-sitter`), conjunto completo de operadores de Offutt et al. (ROR/AOR/LCR + ABS/UOI, motivado por medição de 199/200 `AC_ref.cpp` reais abaixo de 100 ocorrências dos operadores originais), mutação de ordem superior por regra determinística sem busca, base de mutação exclusivamente `AC_ref` (sem ACs adicionais do dataset de origem, D4), e arquitetura de reprodutibilidade em que o pacote de mutantes da execução final é compactado e versionado (`data/mutants.zip` + manifesto), por causa da instabilidade de margem do motor já medida em D18/D19 — isso exigiu emenda ao Princípio II da Constitution (v1.6.0). Decisões D1–D6, com proveniência completa, em `specs/002-mutant-generation/spec.md` | 2, 6, 7 |
| 2026-09-22 | **Reparo de WA na auditoria (D18)**: 13 WA em 12 dos 200 problemas divergiram na auditoria (comportamento indefinido ou tempo no limiar); investigada e descartada a correção por ASLR (bloqueada pelo seccomp padrão do Docker); decisão: substituição automática pelo próximo candidato não tentado, com confirmação mais forte; `dataset.validation.repair` implementado e testado | 1.4, 1.7, 8 |
| 2026-09-22 | **Convergência aceita (D18)**: 3 rodadas de `audit` (16, 11 e 10 WA reparadas; 20 dos 200 problemas tocados ao todo); decisão dos autores de aceitar o estado atual e fazer só mais uma auditoria de fechamento antes do `package`, sem perseguir zero divergências (ruído estatístico esperado ao testar ~26.400 WA com um crivo de 2 execuções) | 1.4, 1.7, 8 |
| 2026-09-22 | **Bug de confirmação corrigido (D18)**: a segunda execução real do `audit`, sobre o dataset já reparado, achou 8 das 13 WA reparadas (62%) divergindo de novo; a causa era um bug na confirmação (só duas de quatro chamadas eram de fato comparadas, e o valor gravado vinha de uma chamada nunca conferida); corrigido para exigir que todas as passadas concordem com a primeira, e o número de passadas subiu de 2 para 3 (6 execuções); teste de regressão específico | 1.4, 8 |
| 2026-09-22 | **Retomada verificada de propósito e limite da garantia de determinismo (T080, D19)**: `validate` interrompido com `SIGTERM` no meio de um problema sintético (motor real) e retomado confirma SC-006 (0 pastas duplicadas, 0 arquivos truncados) e SC-007/FR-025 para tudo que decide a seleção; achado que `max_cpu_time_s` de `validacao.json`, além de `extraction_timestamp`, também varia entre execuções (ruído real de medição, não de seleção); `max_memory_bytes` permanece estável; não afeta o hash do zip ao reempacotar o mesmo conjunto (SC-008) | 1.4, 1.5, 8 |
| 2026-09-22 | **Empacotamento e verificação implementados (T082 a T092)**: `package` e `verify`/`scripts/verify_dataset.py` implementados exatamente como já decidido em 1.6 (zip determinístico, manifesto SHA-256, `--allow-partial`, aviso de 95 MB), sem nenhuma divergência do desenho encontrada; 47 testes automatizados novos. Ainda não rodaram sobre o dataset real — falta a auditoria de fechamento (T093) antes; o tamanho real do zip e o hash continuam pendentes | 1.6, 8 |
| 2026-09-22 | **Empacotamento real e verificação pós-clonagem (T093/T094, revisão `9b87d7e`)**: quarta rodada de `audit` de fechamento sem reparo novo; `package` gerou o `data/dataset.zip` real (200 problemas, 12.891.474 bytes ≈ 12,3 MiB, 21.000 arquivos, 29% acima da estimativa de ~10 MB mas nem de longe uma ordem de grandeza) e o manifesto (hash do zip `bd5398a8…af0c32`); `verify` deu `OK`; cenário de pós-clonagem (quickstart Nível 6) confirmado: `unzip` e `python -m zipfile -e` produzem árvores idênticas, e os três casos de adulteração de propósito (byte alterado, arquivo removido, arquivo extra) foram apontados corretamente pela verificação | 1.6, 8 |
| 2026-09-22 | **Checagem de sincronização de fechamento (T099)**: `check_docs_sync.py --closing` (C1 a C6, ambos os módulos) sai com `0`; todas as decisões D1 a D19 têm linha em `sync-matrix.json` com os termos presentes neste documento; `src/dataset/README.md` passa a `Status: implementado` (as sete fases do ciclo — `extract`, `report`, `selfcheck`, `validate`, `audit`, `package`, `verify` — estão documentadas, carimbadas e executadas de verdade); nenhuma linha `pendente` resta | 1–8 |
| 2026-09-22 | **Feature `001-dataset-extraction` concluída (T103)**: `spec.md` passa a `Status: Implemented`; 649 testes automatizados (0 falhas), lint e formatação limpos (T095/T096); os 8 níveis do `quickstart.md` validados e registrados (T097); revisão de conformidade da documentação e da Constitution feitas (T098/T102 — única divergência: o fluxo real usou commits diretos na `main`, revisados continuamente pelo autor, em vez de PR; revisor Rafael, 2026-09-22). Módulos `dataset` e `sandbox` ambos `Status: implementado`. O que resta do experimento (mutação, chamadas de IA, avaliação, métricas, orquestrador) é escopo de features futuras, ainda sem spec (o orquestrador foi descartado em 2026-11-14, ver acima) | 1–8 |
| 2026-09-21 | **Validação completa (T072, parte `validate`)**: 200 de 200 em 5 h 06 min (4 processos), 264 problemas processados (75,8% completos), 21 descartados, 43 em triagem adiada (16,3%; causas em 1.7); amostra 98/61/41 por macrocategoria e 198 `train` + 2 `test`; alerta de menos de 30 não disparou; 84,6% das candidatas viraram WA; `audit` ainda pendente | 1.2, 1.4, 1.7 |
| 2026-09-21 | **Triagem manual de AC adiada (D17)**: os problemas com o `AC_ref` reprovado seguem interrompidos e registrados, mas só serão inspecionados se a meta de 200 não for atingida com os demais; `validate` sai com 0 sempre que a meta é atingida; explicação de como os 200 problemas são escolhidos (pool embaralhado com a seed 42, os 200 primeiros que completam); item 16 resolvido | 1.4, 6 |
| 2026-09-21 | **Piloto de validação (T071)**: 14 problemas do `train` (10 completos, 3 em triagem, 1 descartado); 85,5% das candidatas viraram WA (risco de poucas WA não se materializou), mediana de 102 s por problema completo, sem déficit projetado; critério de reabertura de D13 não atingido (regra 2: 7,1%; regra 5: 0%); descoberta de que `generated_tests` do dataset podem ter entradas fora das restrições; item 15 resolvido e item 16 (volume de triagens) aberto | 1.4, 1.7, 6 |
| 2026-09-21 | **Motor implementado (T049)**: ambiente reconfirmado com o motor (linker, pilha, memória, isolamento); três diferenças encontradas e corrigidas (áreas graváveis por todos, zumbis, pico de memória inflado), com lançador nativo, `init: true` e `tmpfs` privados (D16); custos medidos (compilação de 2,5 s com `bits/stdc++.h`, sobrecarga de 2,5 ms por teste) | 1.4, 1.7 |
| 2026-09-20 | **Gate T037**: os autores confirmaram as 7 regras operacionais do motor sem alteração (de proposta a decididas) e definiram o critério objetivo de reabertura das regras de comparação de saída e de tempo no piloto (mais de 10% dos ACs testados reprovados por formatação ou por TLE), com o diagnóstico `format_only` e as contagens `ac_tested`/`triage_by_cause` no relatório (T037) | 1.4, 6, 7 |
| 2026-09-20 | **Extração real (T035)**: funil reconfirmado (13.610; 8.101; 2.399; 2.155; 1.751; 1.288; 1.279 idênticos aos do planejamento) e completado com as etapas de soluções em C++ (1.250) e de pelo menos 100 incorretas (1.234); pool final 407/278/549 (`train` 1.206, `valid` 9, `test` 19), em vez de 1.279 (417/285/577); dados de disponibilidade de WAs brutas, volume de testes, limites, tempo (~23 min) e disco (104 MB); estimativa de distribuição por macrocategoria refeita | 1.1, 1.2, 1.4, 1.7 |
| 2026-09-20 | Fluxo de circulação do dataset entre os autores (geração única, distribuição por zip e manifesto, recebimento sem extração; `data/work/` local e sem limpeza automática) | 1.6 |
| 2026-09-20 | Estimativa analítica da distribuição por macrocategoria sob a seleção sem cota (D5) e limiar de taxa de validação que dispararia o alerta de 30; passo `mkdir -p data` antes do primeiro `docker compose run` (o Docker cria o diretório como root se ele não existir) | 1.4, 1.7 |
| 2026-09-19 | Diretório de trabalho `data/work/` com permissão `0700` para o código de terceiros não o acessar (D15); a premissa "não acessa `data/`" passa a valer para `data/work/` | 1.4, 1.7, 7 |
| 2026-09-19 | Decisões da revisão do plano: critério "sem E/S por arquivo", seed 42, manifesto em `manifests/`, motor em pacote próprio | 1.2, 1.4, 1.6, 6, 7 |
| 2026-09-19 | Números do dataset corrigidos por medição (13.610 exemplos; `train` 13.328; 8.101 Codeforces; 118 sem rating; 1.288 elegíveis, 1.279 com E/S por arquivo removida) e funil de elegibilidade | 1.1, 1.2, 7 |
| 2026-09-19 | Localização do motor em pacote próprio (`src/sandbox/`), decisão confirmada na revisão do plano e que faltava aqui | 1.4 |
| 2026-09-19 | Auditoria retroativa (Princípio XI): dados medidos de disponibilidade de submissões, volume de testes e verificações de ambiente (1.7); regras operacionais do motor como PROPOSTA; revisão fixada e licença; `schema_version`, `status` e relatório versionado; evidência e mecanismo do limite de pilha; rótulo de `AC_ref` corrigido; este histórico | 1.1, 1.4–1.7, 4, 6–8 |
| 2026-09-18 | Decisões D1–D5 da spec: splits combinados, tradução como critério, `generated_tests`, flag `-Wl,--stack` removida (pilha em tempo de execução), problemas com menos de 100 WAs excluídos, sem cota por macrocategoria com alerta < 30 | 1.1, 1.2, 1.4, 6, 7 |
| 2026-09-18 | Motor de execução único, AC também validado no motor (`validacao.json`), política de falha de AC com triagem manual (D7, D8) | 1.4, 1.5, 4, 7 |
