# Research: Conferência dos enunciados contra o original do Codeforces

**Feature**: `specs/006-statement-fidelity` | **Date**: 2026-10-18 | **Plan**: [plan.md](./plan.md)

O clarify fechou E1 a E4. Esta pesquisa resolve como fazer cada parte, a partir do que o piloto de
2026-10-18 **mediu** nas 5 páginas guardadas em `data/cf_pilot/`, sem supor o formato do site.

## R1 — Obter e guardar o original (FR-001, FR-002, E2)

**Decision**:
- **URL**: `https://codeforces.com/problemset/problem/<cf_contest_id>/<cf_index>?locale=en`, com os
  dois campos do `metadata.json`. O `?locale=en` garante a versão em inglês; nenhum dos 200 está
  marcado como traduzido (`is_description_translated`), conferido em 2026-10-18.
- **Ritmo**: um pedido por vez, com pelo menos 3 s entre o fim de um e o início do próximo, e um
  cabeçalho `User-Agent` com o projeto e um contato (`tcc-unb-statement-check/1.0`). Tempo de
  leitura de 30 s.
- **Falhas**:
  - HTTP 429 ou 5xx: espera dobrando de 30 s até 5 min, no máximo 5 vezes; depois, o comando para
    de pedir (código 3) e guarda o que já obteve;
  - 404 ou página sem o bloco do enunciado: o problema fica "não conferido", com o motivo, e o
    comando segue.
- **Cópia**:
  - cada página é gravada atomicamente em `data/statements/originals/<id>.html`, numa pasta plana;
  - o manifesto `manifests/statement_originals.manifest.json` guarda, por problema, a URL, a data,
    o status HTTP, o tamanho e o SHA-256 da página e do bloco extraído;
  - o pacote `data/statement_originals.zip` guarda só os 200 blocos (S1).
- **Execuções seguintes**: sem `--refetch`, nenhuma rede, exceto para o que falta (abaixo).
  - O comando lê as cópias, ou o pacote se as cópias não existirem, e recusa com código 1 se algum
    hash divergir do manifesto.
  - Com as páginas inteiras, confere `page_sha256` e `statement_sha256`; com só o pacote, confere
    o `statement_sha256`, e o `page_sha256` fica como registro.
  - `--refetch [--problem ID]` baixa de novo, explicitamente.
- **O que falta**: problemas sem entrada no manifesto, ou com erro temporário (429 ou 5xx). Um erro
  definitivo (`http_404`, `no_statement_block`) só é tentado de novo com `--refetch`, para não
  repetir pedidos inúteis (analyze de 2026-10-18).
- **Pacote determinístico**: o `data/statement_originals.zip` tem as entradas em ordem alfabética e
  data fixa (1980-01-01), sem informação da máquina, então os mesmos blocos dão os mesmos bytes e o
  Git não registra mudança onde não há (analyze de 2026-10-18; mesmo cuidado do `dataset.zip`).
- **`--problem`**: o resultado é só impresso; o relatório versionado vem só da execução sem
  `--problem`, que cobre os 200 (analyze de 2026-10-18).
- **Enunciado traduzido**: nenhum dos 200 tem `is_description_translated` (2026-10-18). Um problema
  assim fica `unchecked` com o motivo `translated`, sem comparação.

**Rationale**: E2. O piloto mostrou HTTP 200 nas 5 páginas, com o HTML do servidor já trazendo
`<sup>`/`<sub>` (formato antigo) ou `$$$…$$$` (novo), sem depender de JavaScript.

**Alternatives considered**: a API pública do Codeforces, que não traz o texto do enunciado; e um
navegador automatizado, que é desnecessário porque o HTML do servidor já tem tudo.

## R2 — Extrair o bloco do enunciado (FR-004)

**Decision**: `html.parser` da biblioteca padrão monta a árvore de `<div class="problem-statement">`.
O que entra na comparação:

| Parte | Elemento (medido no piloto) | Entra |
|---|---|---|
| Título e limites | `div.header` | não |
| Descrição | o primeiro `div` sem classe depois do `header` | sim |
| Entrada | `div.input-specification` (com o título `div.section-title` "Input") | sim |
| Saída | `div.output-specification` ("Output") | sim |
| Exemplos | `div.sample-tests` | não (já conferidos contra `testes.json` pela feature 005) |
| Nota | `div.note` ("Note") | sim |
| Outra seção com `div.section-title` (ex.: "Interaction") | genérico | sim, com o título |

Dentro das partes, o extrator gera uma sequência de nós:
- texto;
- `sup` (`<sup class="upper-index">`) e `sub` (`<sub class="lower-index">`);
- fórmula (`$$$…$$$` no texto);
- imagem (`<img>`);
- tabela (`<table>`);
- quebra de parágrafo (`<p>`, `<li>`, `<br>`, `<div>` de bloco).

`<i>`, `<b>`, `<span>` e `tex-font-style-*` são só estilo e somem, sem deixar espaço.

**Rationale**: as contagens de tags das 3 páginas inspecionadas mostram essa estrutura nos dois
formatos (2026-10-18). Um bloco sem as partes esperadas vira "não conferido", nunca "sem perdas".

## R3 — Comparar sem lista de padrões (FR-003, FR-005)

**Decision**:
1. **O nosso lado**: o `enunciado.md`, sem o bloco de exemplos, que começa na linha `Examples` e vai
   até a linha `Note` ou até o fim.
2. **O lado do original**: o texto **marcado** (R4), em que cada trecho guarda de qual nó veio (o
   mapa de posições).
3. **Normalização**, nos dois lados: espaço normal, espaço fino (`&thinsp;`, U+2009), espaço sem
   quebra e quebra de linha viram um único espaço.
4. **Alinhamento**: `difflib.SequenceMatcher(autojunk=False)` sobre os caracteres normalizados.
   Cada trecho que não é igual vira uma `Difference`, e o **tipo** é o do nó do original que cobre
   o trecho:

| O original naquele trecho | Tipo |
|---|---|
| `^{…}` de um `sup` (e o nosso texto tem o conteúdo sem o `^{`/`}`) | `lost_exponent` |
| `_{…}` de um `sub` | `lost_index` |
| dentro de uma fórmula `$$$…$$$` | `formula` |
| imagem | `image` |
| tabela | `table` |
| texto comum (ou o trecho só existe do nosso lado) | `other` |

5. **Estado por problema**:
   - `faithful`: sem diferenças;
   - `losses`: há diferenças;
   - `unchecked`: sem cópia, página sem o bloco ou falha no download, com o motivo.

**Rationale**: a regra é mecânica. O tipo vem da marcação do próprio original, e o que não cai em
nenhum tipo conhecido aparece como `other`, nunca é escondido. No piloto, as diferenças que não
eram marcação eram só de espaço (`i -th` contra `i-th`), e a normalização (3) as elimina.

**Alternatives considered**: comparar por palavras, como no piloto, o que gerava diferenças falsas
de espaço; e a contagem por padrão, que perdeu `102_B` e todos os índices.

## R4 — Texto achatado e texto marcado

**Decision**: os mesmos nós geram dois textos.

| Nó | Achatado (como o dataset fez) | Marcado (corrigido, E4) |
|---|---|---|
| `sup` com `5` | `5` | `^{5}` |
| `sub` com `i` | `i` | `_{i}` |
| fórmula `$$$1 \le n \le 10^5$$$` | `1 ≤ n ≤ 10^5` (equivalências medidas: `\le`→`≤`, `\lt`→`<`, `\dots`→`...`) | igual ao achatado: o nosso texto já preservou |
| imagem | (nada) | `[image]`, e o problema vai para revisão (E3) |
| tabela | as células em sequência | tabela Markdown com as mesmas células (E3) |

**Conferência prévia**: antes de comparar, o texto **achatado** é alinhado com o nosso. Ele deve
ser igual, a menos de espaço. Isso confirma, problema a problema, que o nosso texto é o original
achatado. Se não for, as diferenças aparecem como `other` e `formula`, e o problema não é corrigido
automaticamente.

**Rationale**: a equivalência das fórmulas foi medida em `1000_B`. Uma conversão desconhecida vira
`formula` (S3) e entra na tabela só depois de vista no relatório e registrada.

## R5 — Corrigido = texto atual com as marcações do original (FR-007, FR-008, S2)

**Decision**:
- **Expoentes e índices**: para cada `lost_exponent` e `lost_index`, o mapa do alinhamento dá a
  posição no `enunciado.md` atual, e ali são inseridos `^{` e `}` (ou `_{` e `}`) em volta do
  conteúdo. Nada mais muda.
- **Tabelas**: o trecho achatado é trocado pela tabela Markdown.
- **Revisão**: um problema com `image`, `formula` desconhecida ou `other` vai para revisão manual,
  com o motivo, e não gera corrigido.
- **As três conferências (FR-008)**, em cada corrigido:
  - **(a)** tirando as marcações (`^{`, `_{`, `}` inseridos, `|`/`-` e as quebras de tabela), o
    texto volta a ser exatamente o `enunciado.md` atual, que a conferência prévia (R4) já mostrou
    ser igual ao original achatado;
  - **(b)** cada `sup` e `sub` do original aparece marcado no corrigido, na posição que o mapa
    indica;
  - **(c)** a diferença entre o corrigido e o atual é composta só de marcações.
- **Saída**: o corrigido vai para `DIR/<id>.md`. Os problemas `faithful` (por exemplo, os do
  formato novo) ficam iguais ao atual e não são gravados, só contados.

**Rationale**: inserir as marcações no texto atual garante a conferência (c) por construção e
mantém os exemplos, as quebras de linha e os espaços do dataset. Refazer o texto inteiro a partir
do HTML mudaria tudo isso (S2). O conteúdo das marcações continua vindo só do original.

## R6 — Códigos de saída e o que é gravado

| Comando | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| `check-statements` | relatório gravado (mesmo com perdas: são dados) | hash de uma cópia diverge; dataset diverge do manifesto | uso | site recusando ou fora do ar depois das esperas (o que já foi obtido fica guardado) |
| `correct-statements` | corrigidos e resumo gravados | sem relatório ou relatório de outro dataset; uma conferência falhou num corrigido (o problema vai para revisão, e o código sinaliza) | uso; pasta com arquivos sem `--force`; pasta dentro de `data/dataset/`, `data/suites/` ou `manifests/` | — |

Ter perdas não é falha: o relatório é o resultado. O código 1 é reservado para dano ou para uma
conferência que não fechou.

## R7 — Testes

- **Formatos**: blocos de enunciado pequenos, escritos nos testes, com a estrutura medida (R2); não
  há cópia de páginas do site nos testes. Cobrem:
  - formato antigo com `sup` e `sub`;
  - formato novo com `$$$`;
  - tabela, imagem e seção extra;
  - página sem o bloco.
- **Casos do piloto, reproduzidos com blocos mínimos**:
  - `10^5` perdido como `105`;
  - `a_i` como `ai`;
  - `10^100000` como `10100000`;
  - formato novo sem perda;
  - SC-001 sobre as 5 páginas reais no quickstart, nível 2.
- **Comparação**:
  - cada tipo de diferença é classificado certo;
  - diferença só de espaço não conta;
  - os exemplos e o cabeçalho ficam fora;
  - uma diferença desconhecida aparece como `other`.
- **Correção**:
  - as três conferências passam no caso bom e falham quando o corrigido é adulterado no teste;
  - imagem vai para revisão;
  - tabela vira tabela Markdown;
  - o dataset fica igual (retrato dos arquivos antes e depois).
- **Download**, com um servidor HTTP local no próprio teste (sem internet; o `sandbox` não tem
  rede, então o servidor fica no `localhost` do contêiner, o que é conferido no primeiro teste da
  T011, porque um contêiner sem rede ainda tem a interface local):
  - um pedido por vez;
  - o intervalo é pedido ao relógio (relógio falso);
  - o `User-Agent` vai no pedido;
  - 429 com espera;
  - retomada que só baixa o que falta;
  - `--refetch`;
  - cópia com hash divergente → código 1;
  - a segunda execução não faz nenhum pedido (SC-003).

## R9 — Medido **[MEDIDO, 2026-10-18]**

- `check-statements --problem` com os 5 do piloto (2026-10-18, revisão `9df4f0e` mais a implementação não commitada): as 5 páginas baixadas de novo pelo comando (HTTP 200, cerca de 31 s com a subida do contêiner); `161_A` 4 `lost_exponent` e 21 `lost_index`, `1_B` 2 `lost_exponent`, `15_A` 6 `lost_index`, `102_B` 1 `lost_exponent` (`10^{100000}`), `1000_B` `faithful` (formato LaTeX); nenhuma diferença `other`, `formula`, `image` ou `table` — exatamente a contagem feita à mão no piloto (SC-001).
- O schema do `metadata.json` só aceita `is_description_translated: false`, então um enunciado traduzido não chega ao dataset e esse caso não tem tratamento no código (o que o analyze acrescentou em R1 vale só como registro).

## R10 — Os 200 problemas **[MEDIDO, 2026-10-18]**

`check-statements` nos 200 problemas (2026-10-18): download dos 195 restantes em 13 min 12 s (rodado por Milena; nenhum `unchecked`); segunda execução sem nenhum acesso ao site e relatório byte a byte igual (SHA-256 `22d234e7…`, SC-003). O primeiro relatório tinha 188 diferenças `formula` e 274 `other` que, examinadas, eram conversões feitas pelo dataset (comandos LaTeX trocados por um símbolo) e listas que o dataset escreveu em Markdown (`* `, `1. `); a tabela de equivalências passou a ter as 16 trocas de um comando por um símbolo vistas nos pares do próprio relatório (`\leq`→`≤`, `\ldots`→`…`, `\cdot`→`⋅`, `\rightarrow`→`→`, `\ne`/`\neq`→`≠`, `\ge`→`≥`, `\gt`→`>`, `\times`→`×`, `\lfloor`/`\rfloor`/`\lceil`/`\rceil`, `\sum`→`∑`, `\,`→espaço, `\bmod`→`mod`, além das 3 do piloto) e os itens de lista passaram a ser lidos como o dataset os escreveu; as perdas de expoente e índice não mudaram com isso. Relatório final: **83 fiéis, 117 com diferença; 152 expoentes perdidos em 79 problemas; 701 índices perdidos em 74 problemas**; 23 diferenças de fórmula em 12 problemas (mudanças de forma, como `\frac{a}{b}` escrito `(a)/(b)`, `\limits`, `\max`); 36 `other` em 4 problemas (`670_D2`: a página atual tem outro texto; `1162_B` e `981_B`: barras invertidas a mais no nosso texto, em matrizes e conjuntos LaTeX; `190_A`). Contra a contagem antiga por padrão: 70 dos 71 confirmados pelo original (o 71º, `670_D2`, não pôde ser comparado porque o texto da página difere), e 9 problemas com expoente perdido que ela não via (`102_B`, `155_C`, `203_B`, `252_A`, `271_B`, `289_C`, `362_B`, `538_A`, `765_C`). `correct-statements`: 102 enunciados corrigidos (151 expoentes e 701 índices marcados), 83 sem mudança, 15 para revisão (12 por fórmula, 3 por `other`), nenhuma conferência falhou; o dataset continua igual ao manifesto (`verify --extracted`: OK). O pacote `data/statement_originals.zip` (só os 200 blocos do enunciado) tem 243.507 bytes (medido em 2026-10-18); o `.gitignore` ganhou a exceção dele.

## R8 — Documentação a propagar

**Neste ciclo:**
- metodologia, seções 1 e 3: o plano, S1 a S3 e uma linha no histórico;
- spec: FR-007 com S2.

**No `tasks.md`:**
- o README do módulo `dataset` (dois comandos na tabela única, os dois cenários, "Comandos
  verificados");
- a "Referência de comandos" da raiz e o `CLAUDE.md`;
- o `docs/verificacao-consistencia.md` não muda, porque não há pasta por problema.
