# Feature Specification: Extração, Validação e Persistência do Dataset Experimental

**Feature Branch**: `001-dataset-extraction`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "Especificar o módulo de extração, filtragem, validação e persistência do dataset experimental, conforme docs/metodologia-referencia.md, seção 1. [...] Este módulo NÃO inclui geração de mutantes, chamadas a modelos de IA, nem cálculo de métricas — isso é escopo de módulos futuros."

## User Scenarios & Testing *(mandatory)*

<!--
  Os "usuários" deste módulo são os dois autores do TCC, que precisam produzir e
  distribuir o dataset experimental que alimenta todos os módulos seguintes.
-->

### User Story 1 - Obter problemas elegíveis e classificados (Priority: P1)

Os autores executam a extração e recebem a lista de problemas do dataset de origem que
satisfazem todos os critérios de elegibilidade, cada um já classificado em exatamente uma
macrocategoria algorítmica (lógica direta, matemática ou estrutural/otimização), junto com
um relatório que explica por que cada problema rejeitado foi rejeitado.

**Why this priority**: Sem um conjunto de problemas elegíveis e categorizados corretamente,
nenhuma etapa posterior (validação de falhas, mutantes, prompts, métricas por categoria) tem
sobre o que operar. É a base do experimento e já entrega valor isolado: permite estimar se a
meta de 200 problemas é atingível antes de gastar tempo de execução em sandbox.

**Independent Test**: Executar a etapa sobre um pequeno subconjunto de problemas de
exemplo (com tags, ratings, enunciados e origens conhecidos) e verificar que a lista de
elegíveis, a macrocategoria de cada um e os motivos de rejeição coincidem com o resultado
esperado, sem precisar compilar nem executar nenhum código C++.

**Acceptance Scenarios**:

1. **Given** um problema do Codeforces com rating 1200, tag `dp`, enunciado sem termos
   visuais, não traduzido e com soluções em C++, **When** a elegibilidade é avaliada,
   **Then** o problema é aceito e classificado como `estrutural_otimizacao`.
2. **Given** um problema com rating 1000 a 1600 e tag permitida, mas que também contém a tag
   `constructive algorithms`, **When** a elegibilidade é avaliada, **Then** o problema é
   rejeitado com o motivo "tag proibida".
3. **Given** um problema cujo enunciado contém o termo `shown below`, **When** a
   elegibilidade é avaliada, **Then** o problema é rejeitado com o motivo "dependência
   visual".
4. **Given** problemas com as combinações de tags `math`+`implementation`, `dp`+`math`,
   `binary search`+`sortings`+`implementation`, `greedy`+`strings` e `dp`+`greedy`,
   **When** são classificados, **Then** recebem, respectivamente, `matematica`,
   `estrutural_otimizacao`, `estrutural_otimizacao`, `logica_direta` e
   `estrutural_otimizacao`.
5. **Given** o dataset de origem acessado sem download completo, **When** a extração é
   executada, **Then** os problemas são lidos de forma incremental e nenhuma cópia integral
   do repositório de origem é armazenada localmente.
6. **Given** um problema que atende a todos os outros critérios, mas cujo enunciado exige ler
   `input.txt` e escrever `output.txt` (campos `input_file` e `output_file` preenchidos),
   **When** a elegibilidade é avaliada, **Then** o problema é rejeitado com o motivo "E/S por
   arquivo".
7. **Given** uma seleção final em que uma macrocategoria ficou com menos de 30 problemas
   (por exemplo, 25), **When** o relatório final é produzido, **Then** ele contém um alerta
   nomeando essa macrocategoria e a quantidade obtida, e a seleção não é alterada.

---

### User Story 2 - Ter um motor de execução comprovadamente confiável (Priority: P1)

Os autores dispõem de um único motor de execução (compila e executa código C++ sob limites
de tempo, memória e pilha e atribui um veredito) e conseguem comprovar, antes de usá-lo em
larga escala, que ele atribui o veredito correto a programas de veredito conhecido:
aprovado, resposta errada, tempo excedido, memória excedida, falha de execução, erro de
compilação e programa que depende de pilha grande. Esse mesmo motor, sem alteração, valida a
solução de referência e as submissões incorretas de todos os problemas e será reutilizado
na avaliação experimental.

**Why this priority**: Se o motor atribuir vereditos errados, tudo o que depende dele fica
inválido (falhas do dataset, TDF, MS, TFP). Descobrir um defeito ou uma incompatibilidade
apenas quando o experimento já estiver em andamento seria muito mais caro do que descobri-lo
agora, com programas cujo veredito correto já se conhece.

**Independent Test**: Executar o motor sobre um conjunto fixo de programas de veredito
conhecido (um para cada veredito possível, mais um que exige pilha grande) e verificar que
cada veredito coincide com o esperado, sem precisar de nenhum dado do dataset de origem.

**Acceptance Scenarios**:

1. **Given** programas de veredito conhecido (aprovado, resposta errada, tempo excedido,
   memória excedida, falha de execução e erro de compilação), **When** cada um é executado
   pelo motor, **Then** o veredito atribuído é exatamente o esperado.
2. **Given** um programa que só funciona com recursão profunda (dentro do limite de pilha de
   256 MiB), **When** é executado pelo motor, **Then** ele conclui com sucesso e não é
   classificado como falha de execução.
3. **Given** o mesmo programa executado várias vezes no mesmo ambiente, **When** os vereditos
   são comparados, **Then** são idênticos.
4. **Given** um programa que só compila em um padrão de linguagem mais antigo da cascata,
   **When** é compilado pelo motor, **Then** a cascata o compila no primeiro padrão que
   funciona e registra qual padrão foi usado.

---

### User Story 3 - Validar códigos no motor e persistir problemas completos (Priority: P2)

Para cada problema elegível, os autores obtêm uma pasta local completa contendo o enunciado,
uma solução de referência correta, exatamente 100 submissões incorretas que são falhas
lógicas genuínas (Wrong Answer real), a suíte de testes oficial, os metadados estruturados do
problema e o registro de validação. Todos os códigos C++ da pasta (a solução de referência
e as 100 falhas) passaram pelo mesmo motor de execução, com o veredito esperado.

**Why this priority**: É o coração científico do dataset: a taxa de detecção de falhas reais
só é válida se as 100 falhas de cada problema forem de fato erros de lógica, e não erros de
compilação, estouro de tempo/memória ou falha de execução. Passar também a solução correta
pelo motor garante que nenhum código entra no dataset sem que se saiba que o motor o executa
corretamente, evitando descobrir só durante o experimento que algum código não funciona nele.

**Independent Test**: Executar a validação sobre um único problema elegível e verificar, de
forma independente, que a pasta resultante contém todos os arquivos esperados, que a solução
de referência passa em toda a suíte oficial e que cada uma das 100 falhas, reexecutada
isoladamente, produz saída divergente do gabarito dentro dos limites do problema.

**Acceptance Scenarios**:

1. **Given** um problema elegível com mais de 100 submissões incorretas em C++, **When** a
   validação termina, **Then** a pasta `<ContestID>_<Index>` contém `enunciado.md`,
   `AC_ref.cpp`, `WA_1.cpp` a `WA_100.cpp`, `testes.json`, `metadata.json` e
   `validacao.json`.
2. **Given** uma submissão incorreta que estoura o limite de tempo em um teste, **When** ela
   é validada, **Then** ela é descartada e não ocupa uma das 100 vagas.
3. **Given** uma submissão incorreta que não compila em nenhum dos padrões de linguagem da
   cascata (gnu++20, gnu++17, gnu++14, gnu++11), **When** ela é validada, **Then** ela é
   descartada.
4. **Given** uma submissão incorreta que, na verdade, passa em todos os testes oficiais,
   **When** ela é validada, **Then** ela é descartada por não ser uma falha.
5. **Given** um problema elegível em que, após esgotar todas as submissões incorretas em
   C++, restam menos de 100 falhas validadas, **When** a validação termina, **Then** o
   problema não é incluído na amostra e o motivo ("WAs validados insuficientes") e as
   contagens obtidas ficam registrados no relatório.
6. **Given** um problema para o qual nenhuma solução correta em C++ compila e reproduz o
   gabarito oficial no motor, **When** a validação termina, **Then** o problema é descartado
   com o motivo correspondente.
7. **Given** uma solução correta que o motor rejeita ao ser escolhida como `AC_ref` (por
   exemplo, erro de compilação, tempo excedido ou saída divergente em algum teste oficial),
   **When** a rejeição ocorre, **Then** o processamento daquele problema é interrompido
   imediatamente, nenhuma outra solução correta é tentada em seu lugar, e `validacao.json`
   do problema registra o identificador, o motivo e a saída divergente, deixando o problema
   pendente de triagem manual; os demais problemas continuam sendo processados.
8. **Given** um problema completo, **When** seu registro de validação é consultado, **Then**
   ele mostra `AC_ref` aprovada em 100% da suíte oficial e cada uma das 100 falhas com
   veredito de resposta errada, todos produzidos pelo mesmo motor e configuração, com o
   padrão de linguagem efetivamente usado em cada compilação.
9. **Given** um problema completo já persistido, **When** a auditoria por reexecução é
   executada, **Then** todos os códigos persistidos (`AC_ref` e falhas) são reexecutados pelo
   motor e os vereditos coincidem com o registro de validação.
10. **Given** uma auditoria por reexecução em que o `AC_ref` de um problema persistido falha
    no motor, **When** a falha ocorre, **Then** a auditoria daquele problema é interrompida
    imediatamente (as falhas WA dele não são avaliadas), o registro de triagem é gravado em
    `validacao.json` e a falha aparece no relatório sem esperar que outras se acumulem.

---

### User Story 4 - Retomar a execução sem perder nem corromper dados (Priority: P2)

Se a execução for interrompida (queda de rede na leitura do dataset, falha do ambiente
isolado, desligamento da máquina, comando cancelado), os autores podem reexecutá-la e ela
continua de onde parou, sem duplicar problemas, sem sobrescrever problemas já completos e
sem deixar problemas parcialmente gravados contando como completos.

**Why this priority**: A validação de ~200 problemas com até 100 falhas cada é uma execução
longa; interrupções são esperadas. Sem retomada segura, cada falha obrigaria a recomeçar do
zero ou a limpar dados manualmente.

**Independent Test**: Interromper a execução no meio da gravação de um problema, reexecutar e
verificar que o conjunto final de problemas completos é idêntico ao de uma execução sem
interrupção (exceto o carimbo de data/hora de extração), sem pastas duplicadas nem arquivos
truncados.

**Acceptance Scenarios**:

1. **Given** uma execução interrompida com 37 problemas completos e 1 problema parcialmente
   gravado, **When** a execução é retomada, **Then** os 37 problemas completos são
   preservados sem serem reprocessados, o parcial é refeito por inteiro e o processamento
   segue até a meta.
2. **Given** uma execução já concluída, **When** ela é reexecutada, **Then** nenhum arquivo
   de problema é alterado e nenhum problema novo é adicionado além da meta.
3. **Given** uma falha de infraestrutura do ambiente isolado (e não um veredito sobre o
   código avaliado), **When** ela ocorre durante a validação de uma submissão, **Then** a
   submissão não é descartada por isso: a validação é tentada novamente ou o problema é
   marcado como pendente, nunca contabilizado como TLE/MLE/RE.

---

### User Story 5 - Empacotar o dataset e verificar sua integridade (Priority: P3)

Ao final, os autores obtêm o dataset validado compactado em um único arquivo
(`data/dataset.zip`) e um manifesto de integridade com o hash SHA-256 de cada arquivo, e
podem, a qualquer momento e em qualquer máquina, verificar com um único comando se o dataset
que possuem é exatamente o dataset ratificado.

**Why this priority**: Depende dos dados já validados (US1 a US3), mas é o que permite
distribuir o dataset pelo repositório (Constitution, Princípio II, v1.1.0) e garantir que
todos os módulos seguintes operem sobre a mesma versão exata dos dados.

**Independent Test**: Gerar o pacote e o manifesto a partir de um dataset pequeno de exemplo;
verificar que a verificação passa; alterar um único byte de um arquivo (e, em outro teste,
remover um arquivo e adicionar um arquivo extra) e verificar que a verificação falha
apontando o arquivo divergente.

**Acceptance Scenarios**:

1. **Given** um dataset validado completo, **When** o empacotamento é executado, **Then**
   existem `data/dataset.zip` e um manifesto com o SHA-256 de cada arquivo do dataset e do
   próprio pacote.
2. **Given** o mesmo dataset validado empacotado duas vezes, **When** os hashes dos dois
   pacotes são comparados, **Then** são idênticos.
3. **Given** um dataset íntegro, **When** o comando de verificação é executado, **Then** ele
   reporta sucesso e termina indicando sucesso.
4. **Given** um dataset em que um arquivo foi alterado, removido ou acrescentado fora do
   manifesto, **When** o comando de verificação é executado, **Then** ele reporta falha
   identificando cada arquivo divergente, ausente ou excedente e termina indicando falha.
5. **Given** o repositório após o empacotamento, **When** o estado do controle de versão é
   inspecionado, **Then** apenas o pacote compactado e o manifesto são versionáveis; os
   arquivos soltos do dataset permanecem ignorados.

---

### Edge Cases

- **Rating ausente ou fora da faixa**: problema sem `cf_rating` informado é inelegível; os
  limites 1000 e 1600 são inclusivos.
- **Problema que lê e escreve por arquivo** (`input_file`/`output_file` preenchidos, típico de
  concursos antigos): é rejeitado por FR-004(h) antes de qualquer execução, porque o motor
  injeta a entrada por entrada padrão; evita triagens manuais previsíveis (FR-011b).
- **Problema em mais de um split**: o mesmo `<ContestID>_<Index>` aparece uma única vez na
  amostra, mantendo a primeira ocorrência.
- **Tag permitida e tag proibida juntas**: a tag proibida prevalece (rejeição automática).
- **Nenhuma tag do problema pertence às listas permitidas**: inelegível (não há
  macrocategoria possível).
- **Tags fora da lista permitida convivendo com tags permitidas** (ex.: `number theory`
  junto de `math`): as tags fora da lista são ignoradas na classificação.
- **Solução "correta" que falha no motor** (por exemplo, problemas cujo enunciado admite
  mais de uma resposta válida, ou seja, com verificador especial, e que escaparam do filtro
  de tags; ou um defeito do motor): o problema é interrompido e enviado à triagem manual
  (FR-011b), sem tentar outra solução no lugar. Como a solução é conhecidamente correta, cada
  ocorrência tem causa própria e exige inspeção individual.
- **Submissão com veredito instável** (resultado muda entre execuções repetidas, típico de
  comportamento indefinido): não é aceita como falha validada.
- **Submissões idênticas em texto**: contam uma única vez entre as 100 falhas.
- **Submissão que falha por tempo em um teste e por resposta errada em outro**: vale o
  veredito do primeiro teste que não termina com sucesso na ordem fixa da suíte.
- **Saída com diferenças apenas de espaços em branco ao final de linhas/arquivo**: não é
  considerada divergência.
- **Submissão que depende de pilha grande** (ex.: recursão profunda que no juiz original
  rodava com 256 MiB de pilha): executa com o limite de pilha de 256 MiB (FR-009a) e não é
  descartada por estouro de pilha dentro desse limite.
- **Pool de elegíveis menor que a meta**: o módulo relata o déficit e não relaxa critérios
  automaticamente.
- **Falha de rede ou limite de requisições na leitura do dataset**: a execução pode ser
  retomada sem perda dos problemas já completos.
- **Espaço em disco insuficiente durante a gravação**: o problema em gravação não conta como
  completo e a falha é reportada claramente.
- **Pasta de problema existente mas incompleta** (arquivos faltando ou truncados): tratada
  como parcial e refeita.

## Requirements *(mandatory)*

### Functional Requirements

**Extração**

- **FR-001**: O sistema MUST ler os problemas do dataset público `deepmind/code_contests`
  de forma incremental (streaming), sem baixar nem armazenar localmente o repositório
  completo, sobre uma revisão fixada e registrada do dataset (ver Divergências, D12).
- **FR-002**: O sistema MUST considerar os splits `train`, `valid` e `test` combinados e
  registrar, para cada problema, o split de origem (ver Divergências, D1).
- **FR-003**: O sistema MUST garantir que cada identificador `<ContestID>_<Index>` apareça
  no máximo uma vez na amostra final.

**Elegibilidade**

- **FR-004**: O sistema MUST considerar elegível apenas o problema que satisfaz
  simultaneamente todos os critérios:
  (a) origem Codeforces;
  (b) `cf_rating` entre 1000 e 1600, inclusive;
  (c) ao menos uma tag entre `implementation`, `math`, `greedy`, `strings`,
  `binary search`, `dp`, `sortings`;
  (d) nenhuma tag entre `geometry`, `interactive`, `games`, `probabilities`,
  `constructive algorithms`;
  (e) enunciado sem nenhum dos termos de dependência visual `figure`, `image`, `picture`,
  `shown below`, `as follows`, `http`, `.png`, `.jpg` (comparação sem distinção entre
  maiúsculas e minúsculas);
  (f) enunciado não traduzido de outro idioma (ver Divergências, D1);
  (g) ao menos uma solução correta em C++ e submissões incorretas em C++;
  (h) sem entrada/saída por arquivo: os campos `input_file` e `output_file` do problema
  MUST estar vazios, ou seja, o problema usa entrada e saída padrão (ver Divergências, D9).
- **FR-005**: O sistema MUST registrar, para todo problema avaliado e rejeitado, o(s)
  motivo(s) da rejeição, de modo que a decisão seja auditável.

**Classificação**

- **FR-006**: O sistema MUST atribuir a cada problema elegível exatamente uma
  macrocategoria, aplicando a prioridade fixa: (1º) `estrutural_otimizacao` se houver
  qualquer tag entre `dp`, `binary search`, `sortings`; (2º) `matematica` se houver a tag
  `math`; (3º) `logica_direta` se houver alguma tag entre `implementation`, `strings`,
  `greedy`.
- **FR-007**: A classificação MUST depender exclusivamente das tags do problema, de forma
  determinística e independente da ordem em que as tags aparecem.

**Compilação e execução isolada**

- **FR-008**: O sistema MUST compilar cada código C++ (solução de referência e submissões
  incorretas) com as flags do juiz original, exceto a opção de linker específica do Windows
  `-Wl,--stack=268435456`, que MUST ser omitida (ver Divergências, D2), e com a cascata de
  fallback de padrão gnu++20 → gnu++17 → gnu++14 → gnu++11; um código que falha em todos os
  padrões MUST ser descartado.
- **FR-009**: O sistema MUST executar todo código de terceiros em ambiente isolado, com
  limite de tempo igual a `seconds + nanos/1e9` e limite de memória igual a
  `memory_limit_bytes` do próprio problema, nunca valores fixos, e sem privilégios além do
  estritamente necessário para compilar e executar (Constitution, Princípio V). O diretório de
  trabalho de dados (`data/work/`) MUST ter permissão de acesso apenas do seu dono (`0700`), de
  modo que o código de terceiros não o liste, leia nem escreva (ver Divergências, D15).
- **FR-009a**: O ambiente isolado MUST aplicar, em tempo de execução, um limite de pilha de
  268435456 bytes (256 MiB) a todo código executado, reproduzindo o efeito da opção de linker
  omitida em FR-008; o limite de memória do problema continua valendo sobre o consumo total,
  incluindo a pilha (ver Divergências, D2).
- **FR-010**: O sistema MUST distinguir falha de infraestrutura do ambiente isolado de
  veredito sobre o código avaliado; falhas de infraestrutura MUST NOT resultar em descarte
  silencioso nem ser contabilizadas como TLE, MLE ou RE.
- **FR-010a**: O motor de execução MUST ser verificado por uma suíte própria de programas de
  veredito conhecido (aprovado, resposta errada, tempo excedido, memória excedida, falha de
  execução, erro de compilação, dependência de pilha grande e compilação que exige recuo na
  cascata de padrões), e essa suíte MUST passar antes de o motor ser usado para validar
  qualquer problema do dataset (Constitution, Princípio VI).
- **FR-010b**: Um único motor, com a mesma compilação, os mesmos limites, o mesmo limite de
  pilha e a mesma regra de comparação de saída, MUST ser usado para validar a solução de
  referência e as submissões incorretas, e MUST ser reutilizável sem alteração pelo módulo de
  avaliação experimental (ver Divergências, D7).

**Validação**

- **FR-011**: O sistema MUST escolher como `AC_ref` a primeira solução correta em C++, em
  ordem determinística, e executá-la pelo motor nas mesmas condições das submissões
  incorretas (FR-010b). Ela MUST compilar e reproduzir as saídas esperadas de toda a suíte
  oficial dentro dos limites do problema; caso contrário, aplica-se FR-011b.
- **FR-011b**: Qualquer falha de um AC no motor, seja na escolha do `AC_ref` ou na
  reexecução de auditoria (FR-015a), MUST interromper imediatamente o processamento daquele
  problema e registrá-lo para triagem manual. Constituem falha de AC: erro de compilação em
  todos os padrões da cascata, tempo ou memória excedidos, falha de execução, saída divergente
  do gabarito em qualquer teste da suíte oficial, ou, na auditoria, veredito diferente do
  registrado. O sistema MUST NOT tentar outra solução correta como substituta, MUST NOT
  descartar o problema silenciosamente e MUST NOT adotar tolerância (quantidade ou
  percentual): cada ocorrência interrompe o problema em que ocorre, sem esperar acumular um
  número antes de alertar. O registro MUST constar no `validacao.json` do problema com:
  identificador do problema; motivo (veredito e etapa em que ocorreu); e a saída divergente
  (teste, entrada, saída esperada e saída obtida) ou, quando a falha não produz saída a
  comparar (por exemplo, compilação), o diagnóstico do motor. O problema fica em estado
  "pendente de triagem": não conta para a meta de 200, não é empacotado e não é reprocessado
  automaticamente na retomada até resolução manual pelos autores; o processamento dos demais
  problemas segue. Falhas de infraestrutura do ambiente isolado (FR-010) não são falhas de
  AC. Se o registro alterar o `validacao.json` de um problema já empacotado, a verificação de
  integridade (FR-028) passa a apontar a divergência, o que é intencional (ver Divergências,
  D8).
- **FR-011a**: Nenhum código C++ MUST ser persistido no dataset sem antes ter sido executado
  pelo motor com o veredito esperado: `AC_ref` aprovada em 100% da suíte oficial e cada
  falha com veredito de resposta errada (invariante do dataset).
- **FR-012**: O sistema MUST determinar o veredito de cada submissão incorreta executando a
  suíte oficial em ordem fixa (públicos, privados, `generated_tests`), sendo decisivo o
  primeiro teste que não termina com sucesso, e MUST retê-la como WA validado somente se
  esse teste terminar dentro dos limites com saída divergente do gabarito.
- **FR-013**: O sistema MUST descartar submissões incorretas que: não compilam; excedem o
  tempo (TLE); excedem a memória (MLE); falham em execução (RE); passam em todos os testes
  oficiais; ou têm veredito instável entre execuções repetidas.
- **FR-014**: O sistema MUST percorrer as submissões incorretas candidatas em uma ordem
  determinística definida por seed fixa e documentada, contar textos idênticos uma única vez
  e parar ao atingir exatamente 100 WAs validados; o problema só é completo com exatamente
  100.
- **FR-015**: O sistema MUST registrar por problema o número de submissões incorretas em C++
  disponíveis no dataset (`num_wa_brutos_disponiveis`) e o número de WAs validados
  (`num_wa_validados`).
- **FR-015a**: O sistema MUST oferecer uma auditoria por reexecução que, para um ou mais
  problemas persistidos, reexecuta pelo motor primeiro o `AC_ref` e depois as falhas, e
  confirma que os vereditos coincidem com o registro de validação, reportando qualquer
  divergência (por exemplo, por mudança de ambiente). Se o `AC_ref` falhar, aplica-se
  FR-011b: a auditoria daquele problema é interrompida na hora. Divergência de veredito em
  uma falha WA é reportada, sem interromper o problema.

**Meta de amostra e relatório**

- **FR-016**: O sistema MUST processar os problemas elegíveis em ordem determinística
  definida por seed fixa e documentada, até reunir 200 problemas completos, sem cotas por
  macrocategoria (ver Divergências, D5).
- **FR-017**: Se os problemas elegíveis e completáveis forem menos que 200, o sistema MUST
  relatar o déficit e MUST NOT relaxar critérios de elegibilidade automaticamente.
- **FR-018**: O sistema MUST produzir um relatório de extração com, no mínimo: quantidade de
  problemas lidos, rejeitados por critério, descartados na validação (por motivo),
  incluídos na amostra, e a distribuição da amostra por macrocategoria. O relatório MUST
  listar também todos os problemas pendentes de triagem (FR-011b), com identificador e
  motivo, destacados quando existirem: cada um exige inspeção individual antes de prosseguir
  com o experimento, e não há limiar de tolerância.
- **FR-018a**: Após a seleção final (a meta foi atingida ou todos os problemas do pool foram
  encerrados, mesmo com déficit), se qualquer macrocategoria tiver menos de 30 problemas
  na amostra, o relatório final MUST incluir um alerta identificando a(s) macrocategoria(s)
  e a quantidade obtida. O alerta é informativo: não bloqueia a execução, não altera a
  seleção e não relaxa critérios (ver Divergências, D5).

- **FR-018b**: O relatório final da extração MUST ser versionado no repositório junto do
  manifesto de integridade, para que os números citados no trabalho escrito acompanhem a versão
  exata do dataset (ver Divergências, D12).

**Persistência**

- **FR-019**: O sistema MUST persistir, para cada problema completo, uma pasta
  `<ContestID>_<Index>` contendo `enunciado.md`, `AC_ref.cpp`, `WA_1.cpp` a `WA_100.cpp`,
  `testes.json`, `metadata.json` e `validacao.json`.
- **FR-020**: O arquivo `testes.json` MUST conter as entradas e saídas esperadas dos testes
  públicos, privados e `generated_tests`, mantidos em grupos separados (ver Divergências,
  D1).
- **FR-021**: O arquivo `metadata.json` MUST conter: `problem_id`, `cf_contest_id`,
  `cf_index`, `name`, `source`, `cf_rating`, `cf_points`, `cf_tags`, `macrocategoria`
  (`matematica`, `estrutural_otimizacao` ou `logica_direta`), `time_limit_seconds`,
  `memory_limit_bytes`, `is_description_translated`, `dataset_split_origem`,
  `num_wa_brutos_disponiveis`, `num_wa_validados` e `extraction_timestamp`.
- **FR-021a**: O arquivo `validacao.json` MUST registrar, para `AC_ref` e para cada falha
  validada, o veredito atribuído pelo motor, o padrão de linguagem efetivamente usado na
  compilação e os maiores tempo e memória observados nas execuções, de modo que os módulos
  seguintes reproduzam a mesma compilação e a validação seja auditável. Para problema
  pendente de triagem, MUST conter também o registro descrito em FR-011b.
- **FR-022**: `testes.json`, `metadata.json` e `validacao.json` MUST ter schema formal e versionado, validado
  a cada gravação; qualquer mudança de schema MUST ser uma decisão deliberada e documentada
  (Constitution, Princípio IV).
- **FR-023**: Um problema MUST só ser considerado completo depois que todos os seus arquivos
  foram gravados e validados; um problema parcialmente gravado, ou pendente de triagem
  (FR-011b), MUST NOT contar como completo.

**Idempotência e determinismo**

- **FR-024**: O sistema MUST permitir reexecução após qualquer falha, preservando os
  problemas completos sem reprocessá-los, refazendo os parciais e sem duplicar ou corromper
  dados já persistidos (Constitution, Princípio VII). Problemas pendentes de triagem não são
  refeitos automaticamente: permanecem pendentes até resolução manual (FR-011b).
- **FR-025**: Dado o mesmo dataset de origem, as mesmas seeds e o mesmo ambiente de
  execução, duas execuções completas MUST produzir a mesma seleção de problemas e o mesmo
  conteúdo de arquivos, exceto pelo campo `extraction_timestamp` (ver Divergências, D3).

**Empacotamento e integridade**

- **FR-026**: Ao final, o sistema MUST compactar o dataset validado em `data/dataset.zip` de
  forma determinística: a mesma entrada MUST gerar, no mesmo ambiente de execução, um arquivo
  compactado com o mesmo hash (a compressão depende da versão da biblioteca; a identidade do
  conteúdo entre ambientes vem dos hashes por arquivo do manifesto).
- **FR-027**: O sistema MUST gerar um manifesto de integridade com o hash SHA-256 de cada
  arquivo do dataset e do próprio `data/dataset.zip`, armazenado no repositório fora de
  `data/` e versionado; toda geração ou regeneração do dataset MUST atualizá-lo.
- **FR-028**: O sistema MUST oferecer um comando de verificação de integridade que recalcula
  os hashes e os compara com o manifesto, reportando arquivos alterados, ausentes e
  excedentes e indicando o resultado (sucesso ou falha) no status de saída.
- **FR-029**: Arquivos soltos individuais do dataset MUST NOT ser versionados; somente
  `data/dataset.zip` e o manifesto podem ser (Constitution, Princípio II, v1.1.0).

**Documentação (Constitution, Princípio XI)**

- **FR-031**: Os módulos entregues por esta feature (`src/dataset/` e `src/sandbox/`) MUST ter
  cada um um `README.md` no formato de `docs/template-modulo.md`, com os seis campos
  (propósito em uma frase, como executar com comando exato, entradas, saídas, dependências e
  limitações), acessível sem ler o código **e escrito para quem não conhece Docker**: o "como
  executar" (b) MUST ser um passo a passo que explica o serviço usado, o que aparece na tela,
  como confirmar que funcionou e o que fazer em cada falha comum, e MUST apontar para o guia de
  execução do `README.md` da raiz para a preparação única do ambiente. Cada comando documentado MUST ter sido executado
  como escrito e constar, com data, revisão e tarefa, na tabela "Comandos verificados" do
  README, e a ajuda (`--help`) da CLI e as docstrings MUST NOT contradizer o README.
- **FR-032**: A feature MUST NOT ser considerada concluída enquanto: (a)
  `scripts/check_docs_sync.py --closing` não terminar com código 0 (a metodologia deve refletir
  toda decisão desta spec, conforme `sync-matrix.json`, com o histórico de atualizações
  datado); (b) o `README.md` da raiz (visão geral) não
  descrever os módulos `dataset` e `sandbox`, como se conectam e os comandos exatos para obter
  ou regerar o dataset, e não trouxer o guia de execução do clone ao primeiro comando (pré-requisitos
  e como conferi-los, explicação de Docker, imagem, contêiner, volume e dos serviços `app` e
  `sandbox`, valor e finalidade de cada variável do `.env`, criação de `data/`, construção da
  imagem, verificação do ambiente, onde ficam os arquivos e problemas comuns), em português e sem
  supor conhecimento de Docker.

**Fora de escopo**

- **FR-030**: Este módulo MUST NOT gerar mutantes, chamar modelos de IA nem calcular
  métricas (TDF, MS, TFP, IIC); esses são escopos de módulos futuros.

### Key Entities *(include if feature involves data)*

- **Problema elegível**: Problema do dataset de origem que satisfaz todos os critérios de
  FR-004. Atributos principais: identificador `<ContestID>_<Index>`, nome, rating, pontos,
  tags, enunciado, limites de tempo e memória, split de origem.
- **Macrocategoria**: Uma de três classes mutuamente exclusivas (`matematica`,
  `estrutural_otimizacao`, `logica_direta`), derivada das tags por prioridade fixa; cada
  problema pertence a exatamente uma.
- **Motor de execução**: Componente único que compila e executa código C++ sob os limites de
  tempo, memória e pilha do problema e atribui um veredito; validado por programas de
  veredito conhecido e reutilizado pela avaliação experimental.
- **Solução de referência (AC_ref)**: Solução correta em C++ escolhida para o problema, que
  reproduz todas as saídas esperadas da suíte oficial dentro dos limites, tendo sido aprovada
  pelo motor.
- **Registro de validação**: Por problema, o veredito do motor e o padrão de linguagem usado
  para `AC_ref` e para cada falha, com os maiores tempo e memória observados.
- **Registro de triagem**: Parte do registro de validação de um problema cujo AC falhou no
  motor: identificador, motivo, saída divergente ou diagnóstico e estado "pendente de
  triagem", para inspeção manual individual.
- **Submissão incorreta candidata**: Código C++ marcado como incorreto no dataset de origem,
  ainda não auditado; pode ser falha lógica real ou outro tipo de falha.
- **Falha validada (WA)**: Submissão incorreta candidata confirmada por execução isolada
  como Wrong Answer real; cada problema completo tem exatamente 100, numeradas de 1 a 100.
- **Suíte de testes oficial**: Casos de entrada/saída esperada do problema, em três grupos
  (públicos, privados, `generated_tests`); usada como gabarito para validar AC_ref e WAs.
- **Metadados do problema**: Registro estruturado com identificação, dificuldade, tags,
  macrocategoria, limites, origem, contagens de WA e carimbo de extração; insumo de módulos
  posteriores.
- **Relatório de extração**: Resumo auditável das contagens por etapa, motivos de rejeição e
  descarte e distribuição por macrocategoria.
- **Pacote do dataset**: Arquivo compactado único (`data/dataset.zip`) com todos os
  problemas completos.
- **Manifesto de integridade**: Lista versionada de hashes SHA-256 por arquivo que define a
  identidade exata de uma versão do dataset.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Ao final de uma execução bem-sucedida, o dataset contém 200 problemas
  completos, e 100% deles possuem exatamente 100 falhas validadas e todos os seis tipos de
  arquivo exigidos (`enunciado.md`, `AC_ref.cpp`, `WA_1.cpp` a `WA_100.cpp`, `testes.json`,
  `metadata.json`, `validacao.json`); caso a meta seja inatingível, o relatório informa o déficit exato e o
  motivo.
- **SC-002**: Em uma auditoria por reexecução isolada de todas as falhas persistidas, 100%
  delas produzem saída divergente do gabarito dentro dos limites do problema, e 0% se
  enquadra como erro de compilação, estouro de tempo, estouro de memória ou falha de
  execução.
- **SC-003**: Em 100% dos problemas persistidos, a solução de referência reproduz as saídas
  esperadas de toda a suíte oficial dentro dos limites do problema; e 100% dos códigos C++
  persistidos (solução de referência e falhas) têm registrado o veredito esperado, produzido
  pelo motor.
- **SC-013**: Antes da primeira validação de problema, a suíte de programas de veredito
  conhecido passa em 100% dos casos, cobrindo todos os vereditos possíveis.
- **SC-014**: A auditoria por reexecução (FR-015a) sobre os problemas persistidos reproduz
  100% dos vereditos registrados no mesmo ambiente de execução.
- **SC-015**: Em 100% das falhas de AC (na escolha do `AC_ref` ou na auditoria), o
  processamento daquele problema é interrompido imediatamente e `validacao.json` contém
  identificador, motivo e saída divergente (ou diagnóstico do motor); 0 problemas com falha
  de AC constam como completos na amostra ou no pacote, e nenhum é descartado sem registro.
- **SC-016**: Ao concluir a feature, `docker compose run --rm app python
  scripts/check_docs_sync.py --closing` (checagens C1 a C6, sobre `src/dataset/` e
  `src/sandbox/`) termina com código 0: os READMEs têm os seis campos na ordem do template e o
  propósito em uma frase; todo comando documentado existe na CLI e consta verificado (data,
  revisão, tarefa); os links resolvem; o README da raiz e o estado dos módulos concordam; toda
  decisão D# da spec tem linha em `sync-matrix.json` e seus termos aparecem em
  `docs/metodologia-referencia.md`; nenhuma `[PROPOSTA]` ativa resta (as já resolvidas e riscadas
  não contam).
- **SC-004**: Uma auditoria da amostra final encontra 0 problemas que violem qualquer
  critério de elegibilidade.
- **SC-005**: 100% dos problemas da amostra têm exatamente uma macrocategoria, e os cinco
  exemplos de combinação de tags da metodologia são classificados exatamente como previsto.
- **SC-006**: Após uma interrupção em qualquer ponto da execução, a retomada termina com o
  mesmo conjunto de problemas de uma execução ininterrupta, com 0 pastas duplicadas e 0
  arquivos truncados.
- **SC-007**: Duas execuções completas sobre a mesma entrada, seeds e ambiente produzem
  conteúdo idêntico em todos os arquivos, exceto o carimbo de data/hora de extração.
- **SC-008**: O empacotamento repetido do mesmo dataset produz arquivos compactados com
  hashes idênticos.
- **SC-009**: A verificação de integridade passa em 100% das vezes sobre um dataset íntegro
  e falha em 100% das vezes em que qualquer arquivo é alterado (mesmo em um único byte),
  removido ou acrescentado, apontando o arquivo divergente.
- **SC-010**: Nenhum arquivo do dataset além de `data/dataset.zip` (e o manifesto) aparece
  como versionável no controle de versão, e o armazenamento local durante a extração não
  inclui uma cópia do repositório completo de origem (≈7,6 GB).
- **SC-011**: Um autor executa a verificação de integridade com um único comando, sem
  passos manuais adicionais.
- **SC-012**: Em 100% das execuções em que alguma macrocategoria termina com menos de 30
  problemas, o relatório final contém o alerta correspondente; em 0% das execuções em que
  todas têm 30 ou mais, o alerta aparece.

## Assumptions

- **Usuários**: os dois autores do TCC executam o módulo localmente; não há usuários finais
  externos.
- **Ambiente e conectividade**: há acesso à internet para leitura do dataset de origem e uma
  máquina Linux com toolchain C++ adequada; o ambiente de execução é reprodutível conforme a
  Constitution (Princípio II).
- **Extração única**: o dataset é extraído e validado uma única vez e, depois disso,
  distribuído pelo pacote compactado versionado e pelo manifesto, conforme Constitution
  v1.1.0; a reexecução completa existe para retomada e auditoria, não para redistribuição.
- **AC_ref**: usa-se a primeira solução correta em C++ em ordem determinística; se o motor
  a rejeitar, aplica-se FR-011b (sem substituição automática). Apenas a escolhida e as falhas
  validadas são persistidas, e todas passam pelo motor.
- **Motor construído aqui**: o motor de execução é construído e verificado nesta feature
  (ver Divergências, D7); não há limiar de tolerância para falhas de AC (ver Divergências,
  D8).
- **Comparação de saída**: duas saídas são equivalentes se coincidem após ignorar espaços em
  branco ao final de linhas e do arquivo; qualquer outra diferença é divergência.
- **Suíte oficial como oráculo**: todos os grupos de teste (públicos, privados,
  `generated_tests`) participam da validação de AC_ref e de WAs; o volume e o tempo de
  execução resultantes são preocupação do planejamento.
- **Veredito estável**: a quantidade de repetições para confirmar estabilidade de veredito
  (FR-013) é decidida no planejamento.
- **Palavras-chave visuais**: os termos de FR-004(e) seguem a metodologia. Medido durante o
  planejamento (D10), eles removem 463 dos 1.751 problemas que já passavam nas tags (26%),
  e o pool total ainda é cerca de seis vezes a meta de 200; qualquer relaxamento continua
  sendo decisão dos autores.
- **Seed**: o valor fixo e documentado exigido por FR-014 e FR-016 é `42` (ver Divergências,
  D11).
- **Enunciado**: `enunciado.md` preserva o conteúdo de `description` sem alteração
  semântica, normalizando apenas codificação e quebras de linha.
- **Idioma do código**: identificadores e docstrings em inglês, campos de metadados e nomes
  de arquivos conforme a metodologia (Constitution, Convenções Técnicas).
- **Dependências de módulos futuros**: os módulos de mutantes, orquestração de IA, sandbox de
  avaliação e métricas consomem a saída deste módulo, mas nada deles é entregue aqui.

## Divergências e Decisões sobre a Metodologia

<!--
  Registro exigido pela Constitution (Princípio I): divergências ou preenchimentos de lacunas
  em relação a docs/metodologia-referencia.md, para atualizar o texto final do TCC.
-->

Decisões D1–D5 revisadas e confirmadas pelos autores em 2026-09-18; D6–D8 registradas em
2026-09-18; D9–D11 confirmadas na revisão do plano em 2026-09-19; D12–D14 registradas na auditoria
retroativa de 2026-09-19 (Princípio XI); D15 registrada na revisão da análise de consistência,
também em 2026-09-19.

- **D1 — Propostas da metodologia adotadas (confirmado)**: a seção 6 da metodologia lista
  três itens como "PROPOSTA — aguardando confirmação"; os autores confirmaram os três como
  regra: (i) extrair dos três splits (`train`, `valid`, `test`) combinados; (ii) exigir
  `is_description_translated == false`; (iii) persistir `generated_tests` em `testes.json`,
  separados dos testes públicos e privados. Reflete-se em FR-002, FR-004(f) e FR-020.
- **D2 — Flags de compilação e plataforma (decidido)**: a metodologia pede flags idênticas
  às do juiz original, incluindo `-Wl,--stack=268435456`. Essa opção é de linker do
  Windows/MinGW (toolchain do juiz original) e incompatível com o linker em Linux.
  **Decisão**: remover essa opção da linha de compilação e reproduzir seu efeito aplicando,
  em tempo de execução dentro do sandbox, um limite de pilha de 268435456 bytes (256 MiB), o
  equivalente a `ulimit -s 262144` (o `ulimit -s` conta em KiB). O objetivo é maximizar a
  quantidade de códigos que compilam e executam com sucesso, mantendo a linha de execução o
  mais próxima possível da do Codeforces. Todas as demais flags e a cascata de padrões
  (gnu++20 → gnu++11) permanecem como na metodologia. A mesma regra MUST valer no sandbox de
  avaliação (módulo 4 da metodologia, que reutiliza este pipeline de compilação e execução),
  para que validação e avaliação se comportem igualmente. A divergência de plataforma MUST
  ser refletida no texto final do TCC. Mecanismo definido no plano (2026-09-19): o motor aplica
  o limite com `resource.setrlimit(RLIMIT_STACK)` do Python, em **bytes** (`268435456`), e não
  com `ulimit -s` (KiB); o efeito é o mesmo, e a conversão para `262144` KiB fica em uma função
  única coberta por teste. Verificado que a opção original falha no linker do Linux. Reflete-se
  em FR-008 e FR-009a.
- **D3 — `extraction_timestamp` vs. determinismo (confirmado)**: o carimbo de data/hora,
  exigido pelo esquema de metadados da metodologia, é inerentemente diferente entre
  execuções independentes. É gravado uma única vez quando o problema é persistido,
  preservado nas retomadas, e excluído da comparação de igualdade entre execuções
  (FR-025). Em consequência, o manifesto de hashes identifica uma versão específica do
  dataset, não uma reprodução bit a bit por reexecução do zero; a reprodutibilidade de
  distribuição vem do pacote versionado.
- **D4 — "Exatamente 100 WAs" e problemas insuficientes (confirmado)**: a metodologia não
  diz o que fazer com problemas elegíveis que não alcançam 100 falhas validadas. Esses
  problemas são excluídos da amostra e registrados no relatório, em vez de se aceitar menos
  de 100 (o que quebraria o denominador `W_total = 100` da métrica TDF).
- **D5 — Seleção dos 200 problemas (decidido)**: a metodologia fixa a meta de 200, mas não
  define como escolher entre mais elegíveis. **Decisão**: sem cota rígida por
  macrocategoria; seleção em ordem determinística por seed fixa e documentada. Em
  contrapartida, o relatório final MUST emitir um alerta se qualquer macrocategoria ficar
  com menos de 30 problemas após a seleção (limiar fixo em 30, informativo: não bloqueia,
  não altera a seleção e não relaxa critérios). Reflete-se em FR-016 e FR-018a.
  **Estimativa analítica (2026-09-20, sobre o pool medido de 2026-09-19)**: a ordem é um
  embaralhamento único do pool, sem estratificação, então a amostra de 200 tende a ser
  proporcional ao pool (417/285/577): em média 65,2, 44,6 e 90,2 problemas, e só por acaso
  amostral a chance de `matematica` ficar abaixo de 30 é de ~2e-3. O que pode disparar o
  alerta é uma taxa de validação desigual entre categorias (`matematica` abaixo de ~62% da
  taxa das outras), conhecida só depois da validação; não há mecanismo de correção, por
  decisão desta D5. Detalhes na metodologia, seção 1.4.
- **D6 — Escopo de versionamento de dados**: conforme a Constitution v1.1.0, somente o
  dataset (não os mutantes) pode ser versionado, e apenas compactado em `data/dataset.zip`
  com manifesto. Confirmado em 2026-09-19: o manifesto fica em `manifests/`, **fora** de
  `data/` (que é ignorado pelo Git, exceto o zip), e é versionado.
- **D7 — Motor de execução construído nesta feature e reutilizado (decidido)**: na
  metodologia, o sandbox aparece como módulo 4 (avaliação), mas a validação do dataset já
  exige o motor. Decisão: o motor é construído e verificado nesta feature, e por ele passam
  não só as submissões incorretas como também a solução de referência (`AC_ref`), para que
  qualquer código que o motor não execute corretamente seja detectado já na montagem do
  dataset, e não durante o experimento. O módulo 4 reutiliza o mesmo motor sem alterações. Confirmado em 2026-09-19: o motor vive em
  um pacote próprio (`src/sandbox/`), separado do pacote do dataset, para que a avaliação
  futura o importe sem depender de internos do dataset.
  Consequência: cada problema ganha o arquivo `validacao.json` (FR-021a), acréscimo à
  estrutura de persistência da seção 1.5 da metodologia. Reflete-se em FR-010a, FR-010b,
  FR-011, FR-011a, FR-015a, FR-018, FR-021a e SC-003, SC-013, SC-014 (ver também D8).
- **D8 — Falha de AC: interrupção imediata e triagem manual, sem tolerância (decidido)**:
  qualquer falha de um AC no motor, na escolha do `AC_ref` ou na reexecução de auditoria,
  interrompe imediatamente o processamento daquele problema e o registra em `validacao.json`
  (identificador, motivo, saída divergente) para triagem manual. Não se usa percentual de
  tolerância, não se pula silenciosamente e não se espera acumular um número de falhas antes
  de alertar. Motivo: como o AC é conhecidamente correto, sua falha quase sempre indica bug
  no motor ou um problema com múltiplas saídas válidas (verificador especial) que escapou do
  filtro de tags de elegibilidade; cada ocorrência tem causa raiz distinta e exige inspeção
  individual, não estatística agregada. Substitui a ideia inicial de tentar a próxima
  solução correta e de usar as rejeições como indicador agregado. Reflete-se em FR-011,
  FR-011b, FR-015a, FR-018, FR-021a, FR-023, FR-024 e SC-015. A interrupção vale por
  problema: o processamento dos demais continua, e os pendentes de triagem não contam para a
  meta de 200.
- **D9 — Novo critério de elegibilidade: sem E/S por arquivo (decidido em 2026-09-19)**: a
  metodologia não excluía problemas que leem e escrevem por arquivo (`input.txt`/`output.txt`).
  Medido durante o planejamento: 9 problemas do pool (0,7%), todos de concursos antigos. Como
  o motor injeta a entrada por entrada padrão (metodologia, seção 4), o AC deles falharia e,
  pela regra D8, cada um viraria triagem manual. Decisão: acrescentar `input_file` e
  `output_file` vazios como critério de elegibilidade. Reflete-se em FR-004(h), no cenário 6
  de US1 e no edge case correspondente. Registrado na metodologia, seção 1.2.
- **D10 — Números do dataset corrigidos por medição (2026-09-19)**: a metodologia citava 4.044
  exemplos (`train` 3.760, `valid` 117, `test` 165). Medido em streaming, revisão
  `802411c3010cb00d1b05bad57ca77365a3c699d6`: 13.610 exemplos (`train` 13.328, `valid` 117,
  `test` 165); 8.101 de origem Codeforces; 118 problemas Codeforces sem `cf_rating`
  (inelegíveis, FR-004(b)); 1.288 elegíveis antes de FR-004(h) e 1.279 depois (sem contar a
  checagem de soluções em C++, que exige as colunas pesadas). O texto do TCC deve ser
  atualizado. Detalhes do funil na metodologia, seção 1.2.
- **D11 — Seed fixa (confirmado em 2026-09-19)**: `42`. Ela define a ordem de processamento
  dos problemas elegíveis (FR-016) e das candidatas a WA (FR-014). É gravada no pool, no
  manifesto e no relatório; trocá-la depois da primeira extração muda a seleção.
- **D12 — Dados medidos no planejamento, revisão fixada e relatório versionado (2026-09-19)**:
  itens que o plano registrava como "a refletir" e que ainda não estavam na spec nem na
  metodologia. (i) O dataset de origem é lido em uma **revisão fixada**
  (`802411c3010cb00d1b05bad57ca77365a3c699d6`, licença CC-BY-4.0) e a extração é uma passagem
  única com checkpoint por shard (FR-001, FR-025). (ii) O relatório final é versionado em
  `manifests/extraction_report.json` (FR-018b). (iii) Disponibilidade de submissões medida: no
  `train` a mediana é ~200 incorretas em C++ por problema, e em `valid`/`test` ~101; como só o
  motor revela quantas são WA de verdade, fechar 100 WAs em `valid`/`test` é praticamente
  impossível e a amostra tende a vir quase toda do `train`; se a fração de WA for baixa, a
  meta de 200 pode não fechar sem relaxar D4 ou critérios (decisão dos autores, nunca
  automática; FR-017). (iv) O zip é estimado em ~10 MB. Detalhes e fontes na metodologia,
  seção 1.7.
- **D13 — Regras operacionais do motor, ainda como proposta**: ordem da suíte e veredito pelo
  primeiro teste que falha (FR-012), comparação de saída sem espaços finais, estabilidade de
  veredito com duas execuções, tempo medido como CPU, memória como limite de espaço de
  endereçamento, isolamento por usuário dedicado e escolha do `AC_ref` como a primeira
  solução correta em ordem do dataset. Estão na spec (Assumptions e FRs) e no plano, mas os
  autores ainda não as confirmaram explicitamente; a metodologia (1.4) as registra como
  **[PROPOSTA]** e a seção 6, item 14, as lista como pendentes de confirmação.
- **D14 — Documentação como requisito de conclusão (Princípio XI, constitution v1.2.0)**: a
  feature só é concluída com README de módulo conforme o template, metodologia sincronizada e
  README da raiz atualizado (FR-031, FR-032, SC-016). Nenhum módulo estava implementado nem
  tinha README quando o princípio foi adotado, então não houve README existente a ajustar; os
  dois READMEs desta feature são tarefas obrigatórias do `tasks.md`.
- **D15 — Diretório de trabalho de dados privado, `0700` (2026-09-19)**: a premissa documentada
  é que o código de terceiros não acessa os dados do projeto. Na revisão da análise de
  consistência verificou-se que o `./data` montado no serviço do motor herda a permissão do
  host (tipicamente `0755`), que o processo filho de usuário dedicado conseguiria **ler**.
  Decisão dos autores: `data/work/` (onde ficam `raw`, `building` e `problems`) é criado com
  permissão `0700`, tendo como dono o usuário do host; o orquestrador (root com
  `DAC_OVERRIDE`) e o serviço `app` (usuário do host) continuam acessando. Arquivos públicos
  (`data/dataset.zip`, `data/dataset/`) não precisam de restrição. Reflete-se em FR-009 e nos
  testes de permissões e de isolamento.
