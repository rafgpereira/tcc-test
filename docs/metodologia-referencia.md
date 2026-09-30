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
etapas que consomem os dados (envio às IAs e execução final do experimento); cada módulo novo que
produz uma pasta por problema (os testes gerados pelas IAs) acrescenta a sua camada. Motivação
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

---

## 3. Módulo: Orquestração de IA / Geração de Prompt

**[PARCIALMENTE DECIDIDO — a parte do SLM (geração de suítes) foi fechada em
`specs/003-slm-test-generation/spec.md` (2026-09-29); a parametrização exata dos dois
modelos comerciais (GPT-5.4-mini, Gemini 3.5 Flash) e a orquestração deles continuam
pendentes, a especificar em módulo futuro.]**

**Modelos avaliados**:
- GPT-5.4-mini (OpenAI, API) — `reasoning_effort: medium`, saída travada em JSON
  (`strict: true`), sem retenção de histórico (`store: false`). **[PENDENTE — fora do
  escopo de `003-slm-test-generation`; especificado em módulo futuro.]**
- Gemini 3.5 Flash (Google, API) — `thinking_level: medium`, `generateContent`
  (stateless nativo), saída `mimeType: application/json`. **[PENDENTE — idem.]**
- Qwen2.5-Coder-7B (local, via Ollama) — sem parâmetro de esforço de raciocínio
  (limitação arquitetural do modelo, considerar na análise de resultados); saída em
  **texto plano com 3 blocos marcados** (`<edge_cases_analysis>`, `<inputs>` com vários
  `<input>`, `<reference_py>`), não JSON (ver abaixo); cada chamada disparada sem
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
avaliação. Uma entrada em que a solução falha isoladamente é descartada sozinha; se a
solução falha nos testes públicos, ou falha (erro/timeout) em 100% das entradas
geradas, a tentativa inteira é descartada e uma nova tentativa é gerada (seed base +
número da tentativa), até 6 tentativas — depois disso, a suíte daquele problema ×
cenário é descartada por completo, registrada, e continua contando no N = 200 das
métricas (a taxa de descarte é reportada à parte). Falha de infraestrutura na chamada
ao Ollama (serviço fora do ar, timeout de conexão) não consome tentativa — só as 3
razões de conteúdo (resposta não interpretável, falha em teste público, falha — erro de
execução e/ou timeout, em qualquer combinação — em 100% das entradas geradas) consomem
(a clarificação de 2026-09-29 juntou "erro em todas" e "timeout em todas" numa razão só;
corrigido aqui em 2026-09-30, no `/speckit.plan`). Limitação a registrar: nos cenários com código
(caixa-branca e híbrido), o SLM pode traduzir o `AC_ref` para Python em vez de
resolver o problema de forma independente, o que tende a reduzir a TFP por construção
— não há verificação própria de não determinismo da solução Python gerada. Detalhes
completos (schema da suíte, formato exato de persistência, retomada) em
`specs/003-slm-test-generation/`.

**Parametrização técnica do SLM [DECIDIDO no plano, 2026-09-30 —
`specs/003-slm-test-generation/research.md`, R2–R8; amostragem, forma dos casos e ajuste do
template confirmados por Milena no mesmo dia]**:

- **Chamada**: `POST /api/chat` do Ollama, `stream: false`, **uma única mensagem** (`role:
  user`) com o prompt inteiro, sem `context` nem `system` — sem estado por construção (R2). O
  `digest` do modelo (`qwen2.5-coder:7b`), a quantização e a versão do Ollama são registrados por
  execução e conferidos em toda retomada.
- **Janela de contexto medida**: o maior prompt montado entre os 200 problemas tem **7.870
  caracteres** (híbrido, `61_B`; mediana do híbrido 5.224; maior caixa-preta 6.701; maior
  caixa-branca 5.469; medição de 2026-09-30). Fixados **`num_ctx = 8192`** e **`num_predict =
  4096`** (≈ 3.150 *tokens* de prompt no pior caso, estimativa pessimista de 2,5 caracteres por
  *token*). Guarda em tempo de execução: se `prompt_eval_count + num_predict > num_ctx`, a execução
  para sem gravar a tentativa (o Ollama truncaria o prompt em silêncio) (R3). O máximo real de
  `prompt_eval_count` é medido no piloto.
- **Amostragem [DECIDIDO, 2026-09-30 — item 27 da seção 6]**: `temperature 0.7`, `top_p 0.8`, `top_k 20`,
  `repeat_penalty 1.05` (configuração de geração publicada pelo fabricante do
  Qwen2.5-Coder-7B-Instruct), todos enviados explicitamente; **seed base 42**, seed da tentativa
  `n` = `42 + n` (43 a 48). Achado que restringe a escolha: com `temperature 0` a decodificação é
  gulosa, a seed não tem efeito e as 6 tentativas repetiriam a mesma resposta (R4).
- **Montagem do prompt**: o `<context_data>` usa sub-rótulos fixos (`<problem_statement>`,
  `<reference_solution_cpp>`), e o híbrido é a união literal dos outros dois; fora dele, o prompt
  dos 3 cenários de um problema é idêntico byte a byte (R5).
- **Interpretação**: cada tag de topo abre e fecha exatamente uma vez, na ordem fixa; texto fora
  dos blocos é ignorado e contado (não corrigido); cerca Markdown dentro do código Python não é
  removida (vira erro de execução); entradas repetidas são mantidas e contadas, por inflarem o
  tamanho da suíte (R6).
- **Execução do Python**: CPython 3.11 base da imagem, só biblioteca padrão (`-I -S -B -X utf8`),
  no mesmo `execute` do motor (uid por slot, sem rede, rlimits), workdir novo por execução;
  **tempo = limite do problema × 10** e **memória = limite do problema × 4** (os 7 problemas de
  61 MiB tornariam a memória do próprio interpretador um risco com fator 1; a confirmar no piloto)
  (R7). O `expected_output` gravado é a saída crua da execução; a comparação futura usa a regra
  única do motor (`outputs_equal`).
- **Persistência e retomada**: cada tentativa gera arquivos imutáveis (geração; execução) e o
  `suite.json` terminal é função pura deles; falha de interpretação encadeia a próxima tentativa
  já na fase de geração (não há nada a executar); `--resume` explícito recusa continuar se a
  configuração (modelo, opções, template, dataset) mudou (R8). O `digest` do modelo é gravado
  também em cada tentativa, para que cada resultado se identifique sozinho.
- **Falha de infraestrutura [DECIDIDO, 2026-09-30 — `research.md` R9, R12]**: nunca consome
  tentativa — a mesma chamada é refeita com a **mesma seed**. As repetições consecutivas têm um
  teto e a espera por uma resposta tem um *timeout* de leitura, ambos configuráveis pelo operador
  no `.env` (`OLLAMA_MAX_INFRA_RETRIES`, padrão 30; `OLLAMA_HTTP_TIMEOUT_S`, padrão 900 s); ao
  atingir o teto, o comando para sem gravar nada e a retomada refaz a mesma chamada. Motivo: um
  *timeout* fixo curto demais para um Ollama em CPU faria a mesma chamada se repetir para sempre,
  sem nunca gravar nada. Nenhum dos dois valores muda o conteúdo das respostas, por isso não entram
  na identidade da execução. O tempo máximo real por chamada é medido no piloto.
- **Casos de teste da suíte**: gravados no contrato já existente `TestCase` (`input`, `output`) de
  `testes.json`; o módulo de avaliação, quando especificado, deve adotá-lo ou mudar o schema de
  propósito (decidido em 2026-09-30, item 29 da seção 6); a mesma forma vale para as suítes dos
  dois modelos comerciais.
- **Leitura do problema**: composta localmente no módulo `ai_clients` a partir dos leitores já
  existentes do dataset (`Metadata`, `Testes`) e da leitura direta de `enunciado.md`/`AC_ref.cpp`;
  nenhum leitor novo no módulo `dataset` (decidido em 2026-09-30).
- **Ajuste do template para FR-007 [DECIDIDO, 2026-09-30 — item 28 da seção 6]**: a RULE 2 deixa
  de pedir "the maximum size allowed by the constraints" e passa a pedir o maior caso que o modelo
  consegue escrever por inteiro, com todo valor dentro das restrições; a RULE 3 ganha a frase
  "Every value in every input MUST respect the constraints stated in the context." Motivo: uma
  entrada do tamanho máximo estoura `num_predict` e a resposta sai truncada.

**Template de prompt**: estrutura única em inglês, com marcação XML (`<system_rules>`,
`<context_data>`, `<few_shot_example>`, `<task>`), combinando Few-Shot Prompting +
Chain-of-Thought. Antes de gerar os testes, o modelo é obrigado a preencher um campo
de análise prévia de casos-limite (`edge_cases_analysis`) — reduz alucinação e
superficialidade. O exemplo do `<few_shot_example>` é **o primeiro teste público do
próprio problema sendo perguntado** (escolha determinística pela ordem em
`testes.json`), igual nos 3 cenários daquele problema — nunca um exemplo fixo de outro
problema, para não induzir o modelo a um formato de entrada que não corresponde ao
problema real. **[DECIDIDO, 2026-09-29 — `specs/003-slm-test-generation/spec.md`, D2;
regra a adotar também pelos módulos de orquestração do GPT-5.4-mini e do Gemini 3.5
Flash, para manter o desenho experimental comparável entre os 3 modelos.]**

**Composição dos 3 cenários**: a única variação entre eles é o conteúdo do bloco
`<context_data>` do template — todo o resto (regras de sistema, formato de saída,
parametrização dos modelos) permanece fixo:
1. Caixa-Preta → só enunciado.
2. Caixa-Branca → só `AC_ref.cpp`.
3. Híbrida → enunciado + `AC_ref.cpp`.

**Tamanho da suíte gerada — [PENDENTE, ver seção 6, item 26]**: não há limite fixo de
casos de teste por suíte (o tamanho é variável de confusão conhecida, registrado para
a análise); a regra final, se algum teto ou normalização for necessário para comparar
cenários e modelos de forma justa, é uma decisão a alinhar entre os 3 clientes de
modelo (SLM, GPT-5.4-mini, Gemini 3.5 Flash), ainda em aberto.

**Versionamento das suítes geradas**: a mesma exceção de versionamento já usada para o
dataset e para os mutantes (Constitution, Princípio II, emenda 1.6.0) se aplica às
suítes de qualquer um dos 3 modelos — a identidade de uma suíte depende de uma chamada
real e não estritamente reprodutível a uma API de IA. Ao final da execução completa do
experimento, cada conjunto de suítes MAY ser compactado e commitado com manifesto
SHA-256 próprio, no mesmo formato do dataset e dos mutantes; suítes geradas durante o
desenvolvimento iterativo continuam nunca sendo versionadas. **[DECIDIDO para o SLM,
2026-09-29 — `specs/003-slm-test-generation/spec.md`, D3; a mesma regra se estende, por
consistência, às suítes dos dois modelos comerciais quando esse módulo for
especificado.]**

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
2. ~~Detalhamento operacional da estratégia de oráculo por execução do SLM (módulo 3)~~ —
   **RESOLVIDO** (ver 3, `specs/003-slm-test-generation/spec.md`).
3. Operacionalização do IIC no módulo de métricas: como e onde os conjuntos `D(R)`,
   `D(C)`, `D(H)` de falhas detectadas são registrados para permitir o cálculo de
   diferença de conjuntos.
26. **[PENDENTE]** Regra de tamanho/normalização de suíte a alinhar entre os 3 clientes de
    modelo (SLM, GPT-5.4-mini, Gemini 3.5 Flash), para que a comparação entre cenários e
    modelos não seja enviesada pela variável de confusão "tamanho da suíte" (ver 3).
27. ~~**[PROPOSTA]** Parâmetros de amostragem do SLM~~ — **RESOLVIDO** em 2026-09-30 (Milena):
    `temperature 0.7`, `top_p 0.8`, `top_k 20`, `repeat_penalty 1.05` (configuração do fabricante;
    `temperature 0` descartada porque anularia as retentativas; `research.md` R4) (ver 3).
28. ~~**[PENDENTE]** Template do prompt não cumpria FR-007~~ — **RESOLVIDO** em 2026-09-30
    (Milena): RULE 2 e RULE 3 de `src/prompt_templates/slm_prompt.txt` ajustadas (maior caso escrito
    por inteiro, todo valor dentro das restrições; `research.md` R5a) (ver 3).
29. ~~**[PENDENTE]** Forma dos casos de teste consumida pela avaliação~~ — **RESOLVIDO** em
    2026-09-30 (Milena): contrato existente `TestCase` (`input`, `output`), a adotar também pelo
    módulo de avaliação e pelas suítes dos modelos comerciais (ver 3).
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
`specs/003-slm-test-generation/research.md`, plano de 2026-09-30 (item 29).

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
| 27 | Exemplo do `<few_shot_example>` é o primeiro teste público do próprio problema sendo perguntado (não um exemplo fixo entre chamadas); mesma regra a adotar pelos módulos futuros de GPT-5.4-mini e Gemini 3.5 Flash | 3 |
| 28 | Suítes SLM seguem a mesma exceção de versionamento dos mutantes (Constitution, Princípio II, emenda 1.6.0): pacote + manifesto SHA-256 ao final da execução completa, sem exigir nova emenda; falha de infraestrutura na chamada ao Ollama não consome uma das 6 tentativas por problema × cenário (só as 3 razões de conteúdo consomem) | 3 |
| 29 | Parametrização técnica do SLM fixada no plano (2026-09-30): `/api/chat` com uma única mensagem; `num_ctx 8192` / `num_predict 4096` a partir do maior prompt medido (7.870 caracteres); seeds 43 a 48; Python com tempo × 10 e memória × 4 do limite do problema, só biblioteca padrão; amostragem `temperature 0.7` / `top_p 0.8` / `top_k 20` / `repeat_penalty 1.05` (não `temperature 0`, que anularia as retentativas); casos no contrato `TestCase`; template ajustado para respeitar restrições e não pedir entradas do tamanho máximo | 3 |

---

## 8. Histórico de atualizações deste documento

Registro datado de cada atualização, para conduzir a revisão do texto escrito do TCC
(Constitution, princípio XI). Origem: `specs/001-dataset-extraction/` (spec, plano, pesquisa),
`specs/002-mutant-generation/` (a partir de 2026-09-23) e `specs/003-slm-test-generation/`
(a partir de 2026-09-29).

| Data | O que mudou | Seções |
|---|---|---|
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
| 2026-09-22 | **Empacotamento e verificação implementados (T082 a T092)**: `package` e `verify`/`scripts/verify_dataset.py` implementados exatamente como já decidido em 1.6 (zip determinístico, manifesto SHA-256, `--allow-partial`, aviso de 95 MB), sem nenhuma divergência do desenho encontrada; 47 testes automatizados novos. Ainda não rodaram sobre o dataset real — falta a auditoria de fechamento (T093) antes; o tamanho real do zip e o hash continuam pendentes | 1.6, 8 |
| 2026-09-22 | **Empacotamento real e verificação pós-clonagem (T093/T094, revisão `9b87d7e`)**: quarta rodada de `audit` de fechamento sem reparo novo; `package` gerou o `data/dataset.zip` real (200 problemas, 12.891.474 bytes ≈ 12,3 MiB, 21.000 arquivos, 29% acima da estimativa de ~10 MB mas nem de longe uma ordem de grandeza) e o manifesto (hash do zip `bd5398a8…af0c32`); `verify` deu `OK`; cenário de pós-clonagem (quickstart Nível 6) confirmado: `unzip` e `python -m zipfile -e` produzem árvores idênticas, e os três casos de adulteração de propósito (byte alterado, arquivo removido, arquivo extra) foram apontados corretamente pela verificação | 1.6, 8 |
| 2026-09-22 | **Checagem de sincronização de fechamento (T099)**: `check_docs_sync.py --closing` (C1 a C6, ambos os módulos) sai com `0`; todas as decisões D1 a D19 têm linha em `sync-matrix.json` com os termos presentes neste documento; `src/dataset/README.md` passa a `Status: implementado` (as sete fases do ciclo — `extract`, `report`, `selfcheck`, `validate`, `audit`, `package`, `verify` — estão documentadas, carimbadas e executadas de verdade); nenhuma linha `pendente` resta | 1–8 |
| 2026-09-22 | **Feature `001-dataset-extraction` concluída (T103)**: `spec.md` passa a `Status: Implemented`; 649 testes automatizados (0 falhas), lint e formatação limpos (T095/T096); os 8 níveis do `quickstart.md` validados e registrados (T097); revisão de conformidade da documentação e da Constitution feitas (T098/T102 — única divergência: o fluxo real usou commits diretos na `main`, revisados continuamente pelo autor, em vez de PR; revisor Rafael, 2026-09-22). Módulos `dataset` e `sandbox` ambos `Status: implementado`. O que resta do experimento (mutação, chamadas de IA, avaliação, métricas, orquestrador) é escopo de features futuras, ainda sem spec | 1–8 |
| 2026-09-21 | **Validação completa (T072, parte `validate`)**: 200 de 200 em 5 h 06 min (4 processos), 264 problemas processados (75,8% completos), 21 descartados, 43 em triagem adiada (16,3%; causas em 1.7); amostra 98/61/41 por macrocategoria e 198 `train` + 2 `test`; alerta de menos de 30 não disparou; 84,6% das candidatas viraram WA; `audit` ainda pendente | 1.2, 1.4, 1.7 |
| 2026-09-21 | **Triagem manual de AC adiada (D17)**: os problemas com o `AC_ref` reprovado seguem interrompidos e registrados, mas só serão inspecionados se a meta de 200 não for atingida com os demais; `validate` sai com 0 sempre que a meta é atingida; explicação de como os 200 problemas são escolhidos (pool embaralhado com a seed 42, os 200 primeiros que completam); item 16 resolvido | 1.4, 6 |
| 2026-09-21 | **Piloto de validação (T071)**: 14 problemas do `train` (10 completos, 3 em triagem, 1 descartado); 85,5% das candidatas viraram WA (risco de poucas WA não se materializou), mediana de 102 s por problema completo, sem déficit projetado; critério de reabertura de D13 não atingido (regra 2: 7,1%; regra 5: 0%); descoberta de que `generated_tests` do dataset podem ter entradas fora das restrições; item 15 resolvido e item 16 (volume de triagens) aberto | 1.4, 1.7, 6 |
| 2026-09-21 | **Motor implementado (T049)**: ambiente reconfirmado com o motor (linker, pilha, memória, isolamento); três diferenças encontradas e corrigidas (áreas graváveis por todos, zumbis, pico de memória inflado), com lançador nativo, `init: true` e `tmpfs` privados (D16); custos medidos (compilação de 2,5 s com `bits/stdc++.h`, sobrecarga de 2,5 ms por teste) | 1.4, 1.7 |
| 2026-09-20 | **Gate T037**: os autores confirmaram as 7 regras operacionais do motor sem alteração (de proposta a decididas) e definiram o critério objetivo de reabertura das regras de comparação de saída e de tempo no piloto (mais de 10% dos ACs testados reprovados por formatação ou por TLE), com o diagnóstico `format_only` e as contagens `ac_tested`/`triage_by_cause` no relatório (T037) | 1.4, 6, 7 |
| 2026-09-20 | **Extração real (T035)**: funil reconfirmado (13.610; 8.101; 2.399; 2.155; 1.751; 1.288; 1.279 idênticos aos do planejamento) e completado com as etapas de soluções em C++ (1.250) e de pelo menos 100 incorretas (1.234); pool final 407/278/549 (`train` 1.206, `valid` 9, `test` 19), em vez de 1.279 (417/285/577); dados de disponibilidade de WAs brutas, volume de testes, limites, tempo (~23 min) e disco (104 MB); estimativa de distribuição por macrocategoria refeita | 1.1, 1.2, 1.4, 1.7 |
| 2026-09-20 | Fluxo de circulação do dataset entre os autores (geração única, distribuição por zip e manifesto, recebimento sem extração; `data/work/` local e sem limpeza automática) | 1.6 |
| 2026-09-20 | Estimativa analítica da distribuição por macrocategoria sob a seleção sem cota (D5) e limiar de taxa de validação que dispararia o alerta de 30; passo `mkdir -p data` antes do primeiro `docker compose run` (o Docker cria o diretório como root se ele não existir) | 1.4, 1.7 |
| 2026-09-19 | Diretório de trabalho `data/work/` com permissão `0700` para o código de terceiros não o acessar (D15); a premissa "não acessa `data/`" passa a valer para `data/work/` | 1.4, 1.7, 7 |
