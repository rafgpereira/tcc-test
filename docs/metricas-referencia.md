# Métricas de Avaliação — Proposta Consolidada

> **Natureza deste documento**: rascunho de trabalho, não a metodologia vigente. Consolida (a) as
> 4 métricas já em [`docs/metodologia-referencia.md`](metodologia-referencia.md), seção 5, (b) a
> análise de outra IA sobre o texto do TCC (anexo recebido de Rafael em 2026-11-04,
> `Métricas principais (do TCC).pdf`) e (c) a análise do agente sobre a estrutura real do pipeline
> (dataset, mutantes, suítes dos 4 modelos, módulo de avaliação ainda sem spec). Numeração das
> subseções (5.x) já pensada para virar a seção 5 de `metodologia-referencia.md` por substituição
> direta, depois que Milena e Rafael confirmarem o que vira regra. Convenção de marcação igual à do
> documento-mãe: **[DECIDIDO]** já vale e não muda aqui; **[PROPOSTA]** é sugestão nova, deste
> documento, aguardando confirmação; **[PENDÊNCIA RESOLVIDA]** fecha um item da seção 6 do
> documento-mãe. Nada aqui foi inventado sem base: cada proposta cita de onde vem (o anexo, uma
> pendência já registrada, ou uma observação direta da estrutura de dados).

## A. Perguntas de pesquisa — formalização proposta

`metodologia-referencia.md` (seção 0) já descreve as perguntas em prosa; aqui elas só ganham um
rótulo curto, para dar uma coluna estável à matriz de rastreabilidade da seção G. **[PROPOSTA]**

| # | Pergunta | Já estava no texto? |
|---|---|---|
| Q1 | Qual cenário de contexto (caixa-preta, caixa-branca, híbrida) detecta melhor falhas lógicas reais? | sim (seção 0) |
| Q2 | Qual cenário é mais sensível a defeitos sintéticos sutis (mutantes)? | sim (seção 0) |
| Q3 | Qual cenário produz mais falsos positivos (alucinações)? | sim (seção 0) |
| Q4 | Juntar requisito e código ajuda (sinergia) ou atrapalha (viés/sobrecarga)? | sim (seção 0, IIC) |
| Q5 | Como SLM e os três LLMs comerciais se comparam em eficácia, confiabilidade e custo-benefício? | não — é a pergunta que ficou implícita quando o desenho foi ampliado para 4 modelos (seção 3) e nunca virou frase própria na seção 0 |

Se confirmado, Q5 entra na seção 0 do documento-mãe junto com o resto desta proposta.

## B. Métricas primárias (TDF, MS, TFP, IIC) — mantidas, com as lacunas fechadas

As quatro métricas da seção 5 atual estão **corretas na essência** — são desenho padrão de
literatura de teste de software (recall contra falhas reais, mutation score, taxa de falso
positivo, e um índice de sinergia próprio, pedido pela banca) e internamente consistentes entre
si. A análise encontrou três lacunas concretas, que precisam de uma regra antes do módulo de
avaliação (seção 4, hoje sem spec) ser implementado — não são reformulação das métricas, são a
borda que falta.

### B.1 TDF e MS — sem mudança de fórmula

$$TDF = \left(\frac{W_{det}}{W_{total}}\right) \times 100 \qquad MS(P,T) = \frac{DM}{M-EM}$$

Mantidas exatamente como em 5.1/5.2. Único ponto novo: ver B.4 (Taxa de Cobertura), sobre o que
fazer quando uma combinação não tem suíte nenhuma.

### B.2 TFP — mesma fórmula, uma lacuna de interpretação fechada

$$TFP = \left(\frac{FP}{N}\right) \times 100$$

**Lacuna encontrada**: uma combinação sem nenhum teste (`discarded_manual` — hoje só no Claude, 3
de 600) **não pode**, por definição, reprovar o AC. Pela fórmula atual ela contribui `FP=0`, o que
deixa o TFP daquele modelo artificialmente melhor — um "teste vazio" passa como se fosse um
"teste que confirmou o AC", quando na verdade não houve teste nenhum. Isso é diferente de TDF/MS:
lá, uma combinação `discarded_manual` já cai para 0% corretamente (o modelo de fato falhou em
produzir uma suíte, e isso deve pesar contra ele). Só o TFP tem esse viés de "ausência de teste
parece sucesso".

**Solução proposta**: manter `N = 200` (a regra **[DECIDIDO, 2026-09-23]** de 5.2, que já fixa TDF
e TFP sempre sobre os 200 problemas, sem exceção) — não há motivo para reabrir uma regra já
decidida por uma distorção de 0,5% nos dados reais. Em vez disso, **toda vez que o TFP for
reportado, a contagem de `discarded_manual` daquele modelo/cenário vai junto, like uma nota de
rodapé obrigatória** (ex.: "TFP Claude, caixa-preta: X% — 1 de 200 combinações sem suíte"), e o
relatório da avaliação grava uma visão secundária, `TFP entre combinações com suíte` (FP sobre as
combinações que de fato tinham testes), para quem quiser a leitura sem a diluição. Isso resolve o
viés sem contradizer nada já decidido e sem perder os números já medidos sob a regra atual.

### B.3 IIC — a lacuna mais séria: denominador pode ser zero, e a convenção não estava escolhida

A pendência 3 da seção 6 já registrava isso em aberto ("como e onde os conjuntos `D(R)`, `D(C)`,
`D(H)` ... são registrados"). A análise foi além: **a metodologia não diz se `D(R)`, `D(C)`, `D(H)`
são por problema ou agregados no cenário inteiro**, e essa escolha muda o resultado — não é só
detalhe de implementação.

- **Por problema**: existe um problema real no dataset em que a suíte caixa-preta não pega nenhum
  WA — `|D(R)| = 0` para aquele problema — e a fórmula vira divisão por zero.
- **Agregado (pool dos 200 problemas)**: trata cada WA como `(problema, índice)` e une os 200
  problemas num conjunto só por cenário; o denominador só zera se o cenário inteiro não detectar
  **nenhum** WA real em nenhum dos 200 problemas — não acontece na prática (TDF já mede isso bem
  acima de zero).

**Por que a forma agregada é a mais consistente com o resto da seção 5, não só a mais segura**:
`W_total` e `M` são sempre 100 — constantes — então a média aritmética por problema que TDF e MS
usam já é, matematicamente, **idêntica** à razão agregada (soma dos numeradores sobre soma dos
denominadores). O IIC é o único caso em que o denominador (`|D(R)|` ou `|D(C)|`) **varia** de
problema para problema; só ele calculado de forma agregada preserva o mesmo princípio que as
outras três já seguem sem precisar dizer isso explicitamente.

**[PROPOSTA]** IIC agregado como a métrica oficial (headline), definida sobre `D(R)`, `D(C)`,
`D(H)` como a união, nos 200 problemas do cenário, dos pares `(problema, índice_WA)` detectados.
Fórmulas de 5.4 inalteradas, só a definição dos conjuntos muda de "por problema" para "agregada no
cenário". Nunca fica indefinido na prática.

**Mas isso sozinho esconde heterogeneidade** (poucos problemas com `|D(R)|` grande podem dominar o
agregado — risco real de um resultado concentrado em poucos problemas parecer um padrão geral).
Por isso, junto do IIC agregado, uma **visão distribucional secundária**, por problema, só para
diagnóstico (não é o número oficial): para cada problema com `|D(R)|_p > 0` (ou `|D(C)|_p > 0`,
conforme o IIC), calcula-se o IIC local e reporta-se a mediana, o intervalo interquartil, e a
proporção de problemas com IIC positivo/negativo/zero. Problemas com denominador zero são
**excluídos dessa visão secundária e contados explicitamente** ("N excluídos de 200") — o mesmo
padrão que 5.2 já usa para mutantes incompletos, aplicado aqui pela primeira vez ao IIC.

**Nota de interpretação a registrar**: o IIC agregado não é limitado a ±100% como TDF/TFP — o piso
é −100% (perda total), mas o teto não existe (se o híbrido pegar muito mais WAs novos do que o
total que a abordagem isolada pegava, o IIC passa de 100%). Isso é matematicamente correto, só
precisa estar documentado para não parecer erro ao reportar.

### B.4 Taxa de Cobertura (TC) — nova, pequena, mas necessária para B.2/B.3 fazerem sentido

$$TC_{\text{modelo,cenário}} = \left(\frac{\text{combinações com suíte válida (qualquer status)}}{200}\right) \times 100$$

Já é dado existente (contagem de `discarded_manual` por modelo, já nos relatórios de geração); só
não é uma linha própria na seção de métricas. Vale reportar sempre ao lado de TDF/MS/TFP de
qualquer modelo com `TC < 100%` (hoje só o Claude, `TC = 99,5%`).

## C. Métricas complementares — novas

Ordenadas por prioridade: o quanto cada uma fecha uma lacuna real de validade da comparação versus
o quanto é só enriquecimento da discussão. Nenhuma pede coleta de dado que não exista ou não esteja
planejada — todas reaproveitam o que `ai_clients` já grava (custo, tokens, tempo, tamanho de
suíte) ou o que o módulo de avaliação já vai precisar gravar para o IIC (o conjunto exato de WAs e
mutantes mortos, não só a contagem).

### C.1 TDF* e MS* com oráculo corrigido — prioridade máxima

Ideia do anexo, e a solução mais forte encontrada nesta análise para o problema estrutural de
fundo: **o SLM e os três LLMs comerciais não têm o mesmo processo de oráculo**. O SLM escreve uma
solução em Python e ela é **executada**; a saída esperada só entra na suíte se bater com os testes
públicos (seção 3). Os três comerciais **escrevem a saída esperada diretamente**, sem executar
nada — nunca conferida (seção 3.6 e os três READMEs de `ai_clients`). Vocês já sabem a razão dessa
diferença (tentaram o formato de predição direta no SLM e foi inutilizável) — isso precisa virar
frase no texto (ver seção H). Só documentar a diferença, porém, não resolve o problema de
**comparar os quatro modelos sabendo que o TFP e o TDF deles não vêm do mesmo tipo de garantia**.

$$TDF^{*} = \left(\frac{W^{*}_{det}}{W_{total}}\right) \times 100 \qquad MS^{*} = \frac{DM^{*}}{M-EM}$$

`W*_det`/`DM*` = os mesmos WAs/mutantes mortos, mas recalculados **com a saída esperada de cada
teste trocada pela saída real do `AC_ref` naquela mesma entrada** — as entradas da suíte continuam
sendo as da IA; só o oráculo passa a ser o `AC_ref`, não o que a IA declarou.

$$\Delta_{\text{oráculo}} = TDF - TDF^{*} \quad (\text{e o análogo para } MS)$$

**Por que isso é a peça que faltava**: `TDF*`/`MS*` isolam a **qualidade das entradas** (a IA
escolheu bons valores de teste?) da **qualidade do oráculo** (a IA acertou a saída?), porque usam
as mesmas entradas nos dois cálculos. O gap (`Δ_oráculo`) é a resposta quantitativa, por modelo e
cenário, a "quanto da eficácia medida depende de eu confiar no oráculo da IA" — exatamente o ponto
em que SLM e LLMs comerciais diferem por desenho. Um modelo com `Δ_oráculo ≈ 0` tem um oráculo
confiável (a correção quase não muda nada); um modelo com `Δ_oráculo` grande **e** TFP alto sugere
oráculo ruidoso — detecta e alucina "por acidente", porque a saída declarada é só *diferente* da
real, não necessariamente *certa*. Lido junto com TFP, isso separa duas explicações que hoje ficam
misturadas num único número.

**Custo de implementação real**: o `AC_ref` já é executado contra os testes de toda suíte, para o
TFP atual — só precisa, além do veredito (passou/não passou), **guardar a saída real que o
`AC_ref` produziu em cada entrada**, o que a seção 4 atual não prevê gravar. Ver seção F.

### C.2 TFP por teste e por causa — prioridade alta, mesma base de dados do C.1

Ideia do anexo. Hoje o TFP é binário por problema ("o AC foi reprovado nesta suíte, sim ou não").
Isso esconde se a reprovação veio de **um** teste ruim ou da suíte inteira, e por quê.

$$TFP_{teste} = \left(\frac{T_{FP}}{T_{total}}\right) \times 100$$

`T_FP` = testes individuais que reprovam o AC, `T_total` = total de testes nas suítes do
modelo/cenário. Cada `T_FP` ganha uma causa:

- **`oráculo`**: o `AC_ref` roda normalmente, mas produz saída diferente da declarada pela IA — a
  IA errou o valor esperado (é exatamente o que `Δ_oráculo` do C.1 mede em agregado; aqui é o
  mesmo dado, granular, por teste).
- **`entrada_inválida`**: o próprio `AC_ref` trava, estoura tempo ou dá erro de execução naquela
  entrada — sinal de que a entrada gerada pela IA provavelmente não respeita as restrições do
  problema (o próprio código correto não dá conta dela), não que o oráculo esteja errado. Esse
  teste, estritamente, não devia nem contar como "alucinação de oráculo" — é uma falha diferente,
  de geração de entrada.

**Por que importa**: separa "a IA alucina sobre o que o código deveria devolver" de "a IA gera
entradas fora de especificação", que são problemas de natureza diferente e pedem correções
diferentes no prompt. Hoje essa distinção não existe em nenhum lugar do pipeline.

### C.3 Custo por detecção (e custo/tempo por suíte) — prioridade alta, dado já existe hoje

Ideia do anexo, convergente com o que já havia sido levantado na conversa anterior.

$$CPD_{TDF} = \frac{\text{Custo}_{\text{modelo,cenário}} \text{ (US\$)}}{W_{det,\text{total}}} \qquad CPD_{MS} = \frac{\text{Custo}_{\text{modelo,cenário}} \text{ (US\$)}}{DM_{\text{total}}}$$

**Já disponível sem trabalho novo**: `manifests/<modelo>_generation_report.json` já soma o custo
**de todos os pedidos**, incluindo tentativas que não viraram suíte e respostas barradas (ver
`src/ai_clients/README.md`, linha do `report`) — "custo por suíte, incluindo as novas tentativas",
que o anexo pede, é exatamente esse número, já calculado hoje. Falta só cruzá-lo com `W_det`/`DM`
depois que a avaliação existir.

**SLM não tem custo monetário real** (é local); reportar tokens totais e tempo total de geração
como leitura paralela, **nunca** convertido artificialmente para US$ — qualquer conversão (ex.:
preço de aluguel de GPU) é estimativa, deve vir rotulada como tal e separada do número real pago
pelos três comerciais.

### C.4 Densidade de detecção (TDF por tamanho de suíte) — prioridade média, resolve a pendência 26

$$Dens_{TDF} = \frac{TDF_{\text{cenário}}}{\overline{|T|}_{\text{cenário}}}$$

`|T|` = tamanho médio de testes por suíte (já reportado: "suíte mediana de 8/11/12 testes" nos
relatórios de cada modelo). A pendência **26** da seção 6 do documento-mãe já identificava esse
risco — "a comparação entre cenários e modelos não seja enviesada pela variável de confusão
'tamanho da suíte'" — e ainda está em aberto. Esta é a forma natural de fechá-la: separa "detecta
mais porque o contexto/modelo é melhor" de "detecta mais porque gera mais testes".

### C.5 Complementaridade entre modelos — prioridade média, não estava no anexo

Esta eu acrescento por conta própria: não apareceu nem na minha análise anterior nem no anexo
recebido, mas usa exatamente a mesma infraestrutura de dados que o IIC já vai exigir (o conjunto
de WAs detectados por suíte), então o custo marginal de calculá-la é baixo.

$$Jaccard(A,B) = \frac{|D_A \cap D_B|}{|D_A \cup D_B|} \qquad Gain(B \text{ sobre } A) = \frac{|D_B \setminus D_A|}{|D_A|} \times 100$$

Calculada par a par entre modelos, dentro do mesmo cenário, sobre os conjuntos agregados de WAs
detectados (mesma convenção pooled do B.3). Pergunta que responde: **os LLMs comerciais pegam os
mesmos WAs que o SLM, ou falhas diferentes?** Se a sobreposição (Jaccard) for baixa, é um achado
por si só, direto na linha de "custo-benefício" que vocês já quiseram explorar: sugere que nenhum
modelo isolado é suficiente e que um comitê de modelos pegaria mais falhas do que qualquer um
sozinho — relevante inclusive para a recomendação prática final do trabalho (vale pagar por um LLM
comercial se ele só repete o que o SLM gratuito já pega, ou ele pega uma classe de falha
sistematicamente diferente?).

### C.6 IIC sobre mutantes — opcional, só se o cronograma permitir

Mesmo cálculo do IIC (B.3), mas sobre conjuntos de mutantes mortos em vez de WAs. Serve para
checar se o efeito de sinergia/sobrecarga encontrado nos WAs reais é um padrão robusto do
contexto, ou um artefato específico dos 100 WAs humanos coletados por problema (uma amostra, não o
universo de falhas possíveis). É a que menos fecha lacuna nova e mais reforça confiança estatística
do achado principal — marco como opcional de propósito, para não inflar o escopo sem necessidade.

## D. Camada de validação estatística (apoio, não é métrica de eficácia)

Do anexo, com um complemento. Sem isso, qualquer "modelo A teve TDF maior que modelo B" é só
descrição de uma amostra, não evidência de diferença real.

| Comparação | Teste | Por quê |
|---|---|---|
| TDF, MS entre > 2 grupos pareados (3 cenários, ou 4 modelos) | **Friedman** | não paramétrico, dados pareados (mesmos 200 problemas em todos os grupos), sem supor distribuição normal |
| TDF, MS entre 2 grupos pareados (post-hoc do Friedman, ou comparação direta) | **Wilcoxon pareado** | idem, só 2 grupos |
| TFP (binário por problema: AC passou ou não) entre 2 grupos pareados | **McNemar** | dados pareados binários — o par certo para "quantos problemas mudaram de veredito entre cenário A e B" |
| Tamanho de efeito, sempre que um teste acima der diferença significativa | **A12 de Vargha-Delaney** ou **delta de Cliff** | "significativo" não é "grande"; com 200 problemas, até diferenças pequenas podem dar `p` baixo — o tamanho de efeito é o que sustenta uma afirmação como "melhor" no texto |

**Complemento**: ao rodar Friedman/Wilcoxon/McNemar entre 3 cenários × 4 modelos × várias métricas,
o número de comparações par a par cresce rápido (e.g. C(4,2)=6 pares de modelo só para um cenário e
uma métrica). Recomendo correção para múltiplas comparações nos post-hocs (Holm-Bonferroni é o
padrão menos conservador que ainda controla a taxa de erro) — sem isso, a chance de achar uma
diferença "significativa" por acaso sobe com a quantidade de testes.

## E. Eixos de estratificação — não são métricas novas

**Pergunta direta do Rafael: a classificação por macrocategoria exige uma métrica separada, ou
pode ser analisada nas outras métricas separando por grupo? Resposta: a segunda — não precisa de
métrica própria.** `macrocategoria` (seção 1.3/1.5: `matematica`, `estrutural_otimizacao`,
`logica_direta`, já persistida em `metadata.json` de cada problema) é um atributo do problema, não
uma fórmula nova. Todas as métricas das seções B, C e D são **recalculáveis sobre qualquer
subconjunto de problemas** — basta agrupar por `macrocategoria` antes de tirar a média. A seção 5.4
atual já previa isso só para o IIC ("a macrocategoria... permite cruzar o IIC por categoria
também"); a proposta aqui é generalizar essa mesma ideia para TDF, MS, TFP e as novas também, já
que o agrupamento é o mesmo `GROUP BY` em todos os casos.

Outros dois eixos do mesmo tipo, que já existem nos dados e valem o mesmo tratamento:

- **Status da suíte** (`accepted`, `accepted_fallback`, `accepted_predicted`, `accepted_barred`):
  a regra **[DECIDIDO, 2026-10-06/2026-10-13]** da pendência 31 já diz que a comparação entre
  modelos usa todas as suítes, sem tratar o status como exceção — isso continua valendo. O que esta
  proposta acrescenta é reportar TDF/MS/TFP **também** estratificado por status, como uma tabela de
  validade interna (principalmente do SLM, onde os quatro status convivem), não como substituição
  da comparação oficial por modelo.
- **Tentativa 1 do SLM, sem filtro, × LLMs comerciais** (do anexo): o SLM tenta até 12 vezes e fica
  com a primeira que passa nos testes públicos (ou o melhor fallback); cada comercial recebe
  efetivamente **uma** chamada por combinação (as tentativas 2/3 só acontecem se a resposta não
  puder ser lida, não por qualidade). Comparar o SLM pela suíte final contra os comerciais dá ao
  SLM uma vantagem estrutural de "várias tentativas contra uma". Recalcular TDF/MS/TFP usando **só
  o `attempt_1` do SLM**, descartando o filtro de 12 tentativas, dá uma leitura "em pé de
  igualdade" — complementar à comparação oficial, não substituta (a oficial reflete o pipeline
  real; esta reflete a capacidade bruta do modelo). Exige que o módulo de avaliação saiba avaliar
  um `attempt_N` isolado, não só o `suite.json` final (ver seção F).

## F. Requisitos que isso impõe ao módulo de Avaliação (seção 4, hoje sem spec)

A seção 4 atual descreve avaliação **em curto-circuito para todo código-alvo**, inclusive o AC:
"No primeiro teste que o código falhar, o veredito é registrado imediatamente como reprovado — os
testes restantes daquele arquivo são abortados." Isso é suficiente para TDF/MS/TFP/IIC como estão
hoje (só precisam saber "pelo menos um teste pegou"), mas **não é suficiente** para C.1 e C.2, que
precisam do resultado de **cada** teste contra o AC, não só do primeiro que falhar. O anexo já
sinalizava isso ("a etapa de avaliação precisa... rodar o AC em todas as entradas, sem
curto-circuito"); a análise aqui precisa a extensão exata:

1. **Curto-circuito contra WA e mutante**: mantém como está — TDF/MS/IIC só precisam de "detectado
   por ≥1 teste", nenhuma proposta nova pede mais que isso.
2. **Curto-circuito contra o AC**: **remover**, só para o AC. Rodar os testes da suíte até o fim
   contra o `AC_ref`, mesmo depois da primeira reprovação, e gravar o veredito **de cada teste**
   (passou / reprovou por saída diferente / reprovou por RE-TLE), não só o veredito agregado do
   arquivo. Custo extra é pequeno: as suítes têm mediana de 8 a 12 testes, e isso só muda o
   trabalho quando o AC já reprova pelo menos um teste (caso raro, por definição).
3. **Guardar a saída real do AC por entrada**: pré-requisito do C.1 (`TDF*`/`MS*`) — hoje a seção 4
   não prevê persistir a saída do AC, só o veredito passou/reprovou.
4. **Persistir o conjunto exato de WAs e mutantes mortos por suíte** (não só a contagem): já
   previsto pela pendência 3 (IIC), reaproveitado aqui por C.5 (complementaridade) sem custo
   adicional.
5. **Avaliar um `attempt_N` isolado do SLM, além do `suite.json` final**: pré-requisito da
   comparação "1ª tentativa, sem filtro" (seção E). O dado já existe
   (`attempt_1.generation.json`/`.execution.json` de cada combinação); só o módulo de avaliação
   precisa aceitar um alvo diferente do `suite.json` vigente.
6. **Nenhum requisito novo** para C.3 (custo) e C.4 (densidade) além de cruzar dado já coletado
   pelo `ai_clients` (custo, tokens, tamanho de suíte) com a saída da avaliação.

## G. Matriz de rastreabilidade

| Comparação | Métricas | Pergunta |
|---|---|---|
| Caixa-preta × caixa-branca × híbrida | TDF, MS, TFP | Q1, Q2, Q3 |
| Efeito de juntar requisito e código | IIC (agregado + visão por problema) | Q4 |
| SLM × GPT-5.4-mini × Gemini 3.8 Flash × Claude Haiku 5.5 | todas, mais CPD (custo) e tempo | Q5 |
| Qualidade das entradas × qualidade do oráculo | TDF/MS × TDF*/MS* (`Δ_oráculo`) | Q5, de forma justa entre SLM e LLMs |
| Causa da alucinação | TFP_teste por causa (`oráculo` × `entrada_inválida`) | aprofunda Q3 e Q5 |
| Por macrocategoria (`matematica`, `estrutural_otimizacao`, `logica_direta`) | TDF, MS, TFP, IIC — qualquer uma, agrupada | Q1 e recomendações por categoria |
| Por status da suíte do SLM | TDF, MS, TFP, estratificado | validade interna do SLM |
| SLM 1ª tentativa, sem filtro × LLMs | TDF, MS, TFP | Q5, de igual para igual |
| Entre modelos, mesmo cenário | Jaccard / Gain (complementaridade) | Q5, potencial de comitê |
| Diferença é real? | Friedman / Wilcoxon / McNemar + A12/Cliff's delta | sustenta qualquer "X é melhor que Y" no texto |

## H. Limitação metodológica a registrar explicitamente no texto do TCC

Rafael confirmou que a diferença de processo entre SLM e LLMs comerciais não é uma escolha
arbitrária: **tentaram submeter o SLM ao mesmo formato de predição direta dos comerciais, e foi
inutilizável** (não é mencionado hoje em `metodologia-referencia.md`, só o resultado final — oráculo
por execução — está registrado na pendência 2 da seção 6). Recomendo:

1. Acrescentar essa frase (ou uma próxima, com a redação exata que a dupla preferir) à pendência 2
   da seção 6, como o "porquê" que falta ao lado do "o quê" já resolvido: *"A alternativa de
   predição direta (sem execução), igual à dos três comerciais, foi tentada no SLM antes da
   solução final e descartada por ser inutilizável — <detalhar o motivo observado: taxa de acerto,
   formato, ou o que foi medido>."*
2. No texto do TCC, a seção de limitações do estudo deve dizer, em termos simples, que SLM e LLMs
   comerciais diferem estruturalmente na origem do oráculo (execução validada × predição nunca
   conferida), que essa diferença não é incidental (foi testada e descartada a alternativa
   uniforme), e que `TDF*`/`MS*`/`Δ_oráculo` (C.1) existem precisamente para dar uma leitura que
   isola esse efeito.

## Checklist para a dupla confirmar

- [ ] Q5 formalizada e incorporada à seção 0 do documento-mãe (seção A)
- [ ] TFP: manter `N=200` com nota de `discarded_manual` obrigatória + visão secundária "entre
      combinações com suíte" (B.2)
- [ ] IIC: convenção agregada (pooled) como headline + visão distribucional por problema como
      diagnóstico, com exclusão e contagem quando `|D(R)|`/`|D(C)|` por problema é zero (B.3)
- [ ] Taxa de Cobertura (TC) como métrica companheira de TDF/MS/TFP (B.4)
- [ ] TDF*/MS*/`Δ_oráculo` com oráculo corrigido pelo AC (C.1) — prioridade máxima
- [ ] TFP por teste e por causa (`oráculo` × `entrada_inválida`) (C.2)
- [ ] Custo por Detecção (CPD) e custo/tempo por suíte, SLM sem conversão artificial para US$ (C.3)
- [ ] Densidade de Detecção, fecha a pendência 26 (C.4)
- [ ] Complementaridade entre modelos (C.5) — confirmar se entra no escopo ou fica de fora
- [ ] IIC sobre mutantes (C.6) — opcional, só se o cronograma permitir
- [ ] Camada estatística: Friedman/Wilcoxon/McNemar/A12 ou Cliff's delta, com correção para
      múltiplas comparações (D)
- [ ] Macrocategoria, status da suíte e "1ª tentativa sem filtro" como eixos de corte das métricas
      acima, não métricas novas (E) — resposta direta à pergunta do Rafael
- [ ] Requisitos de F propagados para o `spec`/`plan` do módulo de avaliação quando ele for aberto
- [ ] Frase sobre a tentativa de predição direta no SLM (porquê descartada) incorporada à pendência
      2 da seção 6 e à seção de limitações do texto do TCC (H)

Depois de confirmado, este conteúdo substitui a seção 5 de `metodologia-referencia.md` (mantendo a
numeração 5.1–5.4 das métricas já decididas) e fecha as pendências 3 e 26 da seção 6; este arquivo
pode então ser removido ou arquivado.
