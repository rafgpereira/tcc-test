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

**[CORRIGIDO]** Números medidos empiricamente em streaming durante o `/speckit-plan`, em
**2026-09-19**, sobre os três splits na revisão `802411c3…`, aplicando os critérios acima
(exceto a checagem de soluções em C++, que exige as colunas pesadas e é feita na validação):

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
| Sem E/S por arquivo (`input_file` e `output_file` vazios) | **1.279** (9 removidos) |

Os **1.288** problemas são os elegíveis antes do critério de E/S por arquivo; os **1.279**
são o pool final. Distribuição do pool final: `estrutural_otimizacao` 417, `matematica` 285,
`logica_direta` 577; por origem, `train` 1.250, `valid` 9, `test` 20. Os 9 removidos por E/S
por arquivo (todos com `input.txt`/`output.txt`) são `120_A`, `120_B`, `120_C`, `234_B`,
`234_C`, `253_A`, `253_B`, `253_C` e `36_A` (2 matemática, 3 estrutural/otimização, 4 lógica
direta).

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
  C++ (a escolha da *primeira em ordem determinística do dataset* é **[PROPOSTA]**, ver
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
  O relatório final emite um **alerta** se qualquer macrocategoria ficar com menos de 30
  problemas após a seleção (limiar fixo; alerta informativo, que não bloqueia a execução,
  não altera a seleção e não relaxa critérios).
- **[PROPOSTA — definido na spec e no plano, aguardando confirmação dos autores] Regras
  operacionais do motor**:
  - *Ordem da suíte e veredito*: os testes rodam em ordem fixa (públicos, privados,
    `generated_tests`); o **primeiro** que não termina com sucesso decide o veredito e
    interrompe a execução (curto-circuito). Uma submissão que estoura o tempo em um teste e
    responde errado em outro recebe o veredito do primeiro que falhar.
  - *Comparação de saída*: iguais após ignorar espaços em branco ao final de cada linha e
    linhas ou espaços em branco ao final do arquivo; qualquer outra diferença é divergência.
  - *Estabilidade*: um candidato só é retido como WA se duas execuções independentes, até o
    teste decisivo, derem o mesmo veredito e o mesmo teste decisivo (evita reter falhas
    instáveis por comportamento indefinido).
  - *Ordem e duplicatas*: as candidatas a WA são percorridas em ordem determinística definida
    pela seed, contando textos idênticos uma única vez; `AC_ref` é a primeira solução correta
    em C++ na ordem original do dataset.
  - *Tempo*: medido como tempo de **CPU** do processo filho (não de parede), por robustez à
    carga da máquina; há uma reserva de tempo de parede (3× o limite + 1 s) apenas para
    detectar programas bloqueados.
  - *Memória*: o limite do problema é aplicado como limite de **espaço de endereçamento**
    (`RLIMIT_AS`), que não é idêntico à métrica de memória do juiz original (limitação; ver
    1.7).
  - *Isolamento*: cada execução roda com um usuário dedicado sem privilégios, sem rede, com
    limites de processos e de tamanho de arquivo; o diretório `data/work/` é criado com permissão `0700`
    (dono: o usuário do host), de modo que o código de terceiros não o lista, lê nem escreve.
- **Invariante do dataset**: nenhum código C++ é persistido sem antes ter sido executado
  pelo motor com o veredito esperado (AC_ref aprovada em 100% da suíte oficial; cada WA com
  veredito de resposta errada).

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
  execuções independentes (é o único campo inerentemente diferente entre elas). O manifesto
  de integridade (1.6) identifica, portanto, uma versão específica do dataset, e não uma
  reprodução bit a bit por reexecução do zero.

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
relaxação é automática). A medição da fração real é o "piloto" do roteiro de aceite.

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

**Tempo de extração**: uma passagem completa em streaming, só com colunas leves, levou de 24 a
28 min (com retentativas automáticas de rede; foram observados resets de conexão).

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
14. **[PROPOSTA — aguardando confirmação]** Regras operacionais do motor definidas na spec e
    no plano (ordem da suíte, comparação de saída, estabilidade, tempo de CPU, memória por
    espaço de endereçamento, isolamento, escolha do `AC_ref`; ver 1.4).
15. **[PENDENTE]** Fração de incorretas que é WA de verdade, e se a meta de 200 problemas com
    exatamente 100 WAs fecha; só o piloto com o motor responde (ver 1.7).

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
| 10 | Regras operacionais do motor definidas na spec/plano (veredito pelo primeiro teste que falha, comparação sem espaços finais, estabilidade, tempo de CPU, memória por espaço de endereçamento, isolamento) — a confirmar | 1.4 |
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
| 2026-09-19 | Diretório de trabalho `data/work/` com permissão `0700` para o código de terceiros não o acessar (D15); a premissa "não acessa `data/`" passa a valer para `data/work/` | 1.4, 1.7, 7 |
