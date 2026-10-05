# Geração de Casos de Teste com Modelos de Linguagem (TCC) Constitution

## Contexto do Projeto

Este projeto é o software experimental de um Trabalho de Conclusão de Curso
(Engenharia de Software, UnB) que avalia a eficácia de modelos de linguagem
(dois LLMs comerciais e um SLM local) na geração automática de casos de
teste unitários em C++, sob três cenários de contexto: apenas requisitos
(caixa-preta), apenas código-fonte (caixa-branca) e híbrido. O pipeline
extrai um dataset de problemas algorítmicos, gera falhas artificiais
(mutantes) e reais (submissões incorretas humanas), envia os dados aos
modelos, executa as suítes de teste geradas contra os códigos em ambiente
isolado, e calcula métricas de eficácia (Taxa de Detecção de Falhas, Escore
de Mutação, Taxa de Falsos Positivos). O objetivo final é produzir
recomendações práticas sobre qual estratégia de contexto e qual porte de
modelo é mais confiável para gerar testes automaticamente.

Documentação detalhada de metodologia, quando necessária para especificar um
módulo, está em `docs/metodologia-referencia.md`.

## Core Principles

### I. Metodologia como Ponto de Partida Mutável, Não Fonte Imutável

A metodologia descrita em `docs/metodologia-referencia.md` reflete o desenho
aprovado pela banca em determinado momento, mas não antecipa todos os
detalhes de implementação. Ao especificar um módulo, o texto da metodologia
é o ponto de partida, adaptável quando a prática revelar uma solução melhor.
Toda divergência relevante entre o que foi escrito e o que foi implementado
MUST ser registrada explicitamente (no `spec.md` da feature ou em nota
própria), para que o texto final do TCC possa ser atualizado depois — sem
gerar inconsistência silenciosa entre o que a banca aprovou e o que foi de
fato construído.

### II. Reprodutibilidade e Determinismo

Nenhuma etapa MUST depender de estado implícito ou ordem de execução não
garantida. Toda operação com aleatoriedade (seleção de WAs, amostragem,
geração de mutantes) MUST usar seed fixa e documentada. Versões de
dependências MUST ser pinadas (lockfile). Dado o mesmo dataset de entrada, o
pipeline MUST produzir o mesmo resultado em duas execuções. A dockerização
MUST ser utilizada para garantir a reprodutibilidade do ambiente de execução;
ela não garante a distribuição dos dados do experimento, que segue as regras
abaixo.

Dados brutos do experimento em forma de arquivos soltos (arquivos individuais
do dataset extraído, mutantes gerados durante o desenvolvimento iterativo de
um módulo) NUNCA são versionados no Git. O dataset tem uma exceção: após a
extração e validação únicas, ele MAY ser compactado em `data/dataset.zip` e
commitado no repositório, desde que acompanhado do manifesto de integridade.

A mesma exceção MAY se estender a qualquer outro artefato do experimento cuja
identidade dependa de execução real de código de terceiros no motor de
execução (mutantes; módulos futuros que validem suítes geradas contra AC, WA
ou mutantes) ou de chamadas a APIs de IA não estritamente reprodutíveis bit a
bit (suítes geradas, resultados finais de avaliação): uma vez concluída a
execução final que sustenta os números publicados no trabalho escrito, esse
artefato MAY ser compactado (ex.: `data/mutants.zip`) e commitado, acompanhado
do seu próprio manifesto de integridade. O motivo é o mesmo que já justifica a
exceção do dataset (emenda 1.1.0): regenerar localmente com a mesma seed
reduz, mas não garante, reproduzir exatamente o mesmo resultado, porque o
motor de execução tem instabilidade de margem já medida e documentada
(auditoria do módulo de dataset, 2026-09-22 — comportamento indefinido ou
tempo de execução no limiar do limite fazem o veredito de um mesmo binário
variar entre execuções independentes, sem relação com a lógica de seleção).
Essa exceção vale só para o resultado da execução final que sustenta o
trabalho publicado — as iterações de desenvolvimento de um módulo continuam
nunca sendo versionadas, mesmo depois desta emenda.

Todo dado persistido pelo experimento MUST ser coberto por um manifesto de
integridade commitado, contendo o hash (SHA-256) de cada arquivo persistido
(incluindo `data/dataset.zip`, quando versionado). A integridade e a
identidade exata de uma versão do dataset ou dos mutantes são verificáveis a
qualquer momento recalculando os hashes e comparando com o manifesto.

A verificação de integridade de um artefato (contra o seu manifesto) não basta
sozinha: a coerência **entre** os artefatos (o dataset descompactado tem todos
os problemas e arquivos, e cada problema tem exatamente os seus mutantes, sem
sobrar nem faltar nada de nenhum lado) MUST ser conferida pelo comando
`python -m cli check` (`docs/verificacao-consistencia.md`), e essa conferência,
em modo `--deep`, MUST passar antes de qualquer etapa que consuma esses
artefatos (o envio às IAs e a execução final do experimento). Todo módulo que
passa a produzir uma pasta por problema MUST acrescentar a sua camada a esse
comando no mesmo ciclo de trabalho em que é implementado.

### III. Isolamento Sem Estado nas Chamadas de IA

Nenhuma chamada aos modelos (GPT-5.4-mini, Gemini 3.5 Flash, Qwen2.5-Coder)
pode reter histórico de chamadas anteriores. Cada requisição MUST ser
autocontida, conforme exigido pela metodologia — isso é regra de arquitetura
do código, não só de configuração de prompt.

### IV. Contratos de Dados Explícitos e Versionados

Toda estrutura de dados trocada entre módulos (`testes.json`, saída JSON dos
três modelos, CSV de resultados) MUST ter um schema formal (Pydantic ou JSON
Schema) versionado no código. Mudar um schema é uma decisão deliberada e
documentada, nunca um efeito colateral de outra alteração.

### V. Execução Isolada e Segura (Sandboxing)

Todo código C++ de terceiros (AC, WA, mutantes) MUST rodar sob limites de
tempo e memória extraídos dinamicamente dos metadados do problema (nunca
hardcoded), e nunca com privilégios além do estritamente necessário para
compilar e executar. As mesmas regras valem para qualquer código Python
executado durante a geração de saídas do SLM.

### VI. O Pipeline Testa a Si Próprio

Módulos que compõem a infraestrutura experimental (motor de sandbox, gerador
de mutantes, cálculo de métricas TDF/MS/TFP) MUST ter suíte de testes
unitários própria, com casos conhecidos e esperados (ex: "mutante idêntico ao
original deve ser descartado"; "MS com DM=0 e M=100 deve retornar 0.0").
Nenhuma funcionalidade de infraestrutura é considerada concluída sem esses
testes.

### VII. Idempotência e Retomada Segura

Qualquer etapa do pipeline MUST poder ser reexecutada após falha (queda de
rede, rate limit de API, erro de sandbox) sem duplicar ou corromper dados já
persistidos em disco.

### VIII. Observabilidade de Custo e Uso de IA

Toda chamada a modelo comercial via API MUST logar tokens consumidos, custo
estimado e tempo de resposta. O pipeline NUNCA dispara lotes de chamadas
pagas sem confirmação explícita de quem está executando.

### IX. Simplicidade sobre Generalidade Prematura

Constrói-se apenas o que o experimento (200 problemas × 3 modelos × 3
cenários) exige agora. Abstrações para casos hipotéticos futuros (outros
datasets, outras linguagens além de C++) NÃO são antecipadas.

### X. Revisão Humana Obrigatória

Código gerado com apoio de IA MUST ser revisado por pelo menos um dos dois
autores antes de integrar à branch principal. Nenhum dos dois aceita saída de
IA sem entender o que ela faz.

Nenhum agente de IA (Claude Code ou equivalente) MUST executar `git commit`,
`git add`, `git push` ou qualquer operação que altere o histórico do
repositório (merge, rebase, reset de branch compartilhada) por conta própria,
em nenhuma circunstância, mesmo quando as mudanças forem só de documentação.
O agente MUST trabalhar diretamente no checkout normal do autor, na branch
corrente (`main`, tipicamente) — **não** em um worktree ou branch própria só
sua — e deixar toda alteração como `modified`/`untracked` no `git status`,
nunca sequer `staged`. Ele devolve ao autor a revisão e as instruções exatas
do que rodar; é sempre um dos dois autores quem decide o quê e quando
commitar, e quando (se algum dia fizer sentido) usar um worktree, seguindo
essa orientação. Motivo: commitar é o ponto em que a revisão humana do
parágrafo anterior se torna efetiva — se o próprio agente já commitou, ou já
isolou o trabalho numa branch que o autor precisa ir buscar e mesclar, a
revisão vira uma etapa extra que o autor não pediu. Esta regra é do projeto,
não de uma conversa: `.claude/settings.json` (`worktree.bgIsolation: "none"`)
é versionado para que nenhuma sessão isole o trabalho por padrão.

Ao terminar uma etapa de trabalho e parar para revisão (fim de uma user
story, de uma tarefa 📌 PROPAGAR ou de qualquer ponto em que o agente aguarda
o autor), o relato MUST detalhar o que foi feito — arquivos alterados,
decisões tomadas, achados e números, não um resumo genérico — e MUST dizer
explicitamente quais comandos o autor pode rodar para conferir o trabalho por
si mesmo (os testes novos ou afetados, `check_docs_sync.py`, `ruff`/`black`,
conforme o caso).

### XI. Documentação Viva, Sincronizada e Padronizada

Toda informação nova descoberta durante a especificação, o planejamento ou a
implementação — dado medido empiricamente, divergência entre metodologia e
código, decisão de escopo tomada em conversa — MUST ser propagada, no mesmo
ciclo de trabalho em que foi descoberta, para TODOS os documentos que ela
afeta: os artefatos do spec-kit da feature (`spec.md`, `plan.md` e os demais
artefatos que a informação afetar) E o `docs/metodologia-referencia.md`. Não
é suficiente registrar a divergência em um único lugar: o
`docs/metodologia-referencia.md` MUST permanecer, a todo momento, a fonte
corrente e correta, nunca um retrato desatualizado do que a metodologia
realmente diz. Uma tarefa (especificação, plano ou implementação) MUST NOT
ser considerada concluída enquanto essa propagação estiver pendente. Marcar a
data de execução de um comando na tabela "Comandos verificados" de um README
NÃO substitui essa propagação: depois de carimbar, MUST-se reler, por busca
textual e não só por memória, toda a prosa do README do módulo e do `README.md`
da raiz em busca do mesmo comando e corrigir qualquer trecho que ainda o
descreva como não executado ou planejado. A tabela e a prosa MUST NOT se
contradizer.

Todo módulo do projeto MUST ter documentação de uso própria, seguindo o
template padronizado comum a todos os módulos, definido em
`docs/template-modulo.md`, contendo no mínimo: (a) propósito do módulo em uma
frase; (b) como executar (comando exato); (c) entradas esperadas (formato,
origem); (d) saídas produzidas (formato, destino); (e) dependências ou
pré-requisitos; (f) limitações conhecidas. Essa documentação MUST ser
acessível sem exigir leitura do código-fonte: o README próprio do módulo
(`src/<modulo>/README.md`) é o mínimo obrigatório, complementado por
docstrings e pela ajuda (`--help`) da CLI, que MUST NOT contradizê-lo.

Além da documentação por módulo, o projeto MUST manter um documento de visão
geral na raiz do repositório (`README.md`) que permita a qualquer pessoa sem
conhecimento prévio entender a arquitetura do experimento como um todo, como
os módulos se conectam entre si, e preparar o ambiente uma única vez, comum a
qualquer módulo. Esse README da raiz é um **sumário e índice**, não um
substituto do README de cada módulo: ele MUST NOT duplicar o passo a passo
operacional de um módulo específico — isso pertence ao README daquele módulo,
para onde o da raiz aponta. Reproduzir o experimento completo do zero
significa seguir o guia geral da raiz e, a partir dele, o README de cada
módulo, na ordem em que aparecem no pipeline; não existe nem é esperado um
único arquivo com todo o detalhe operacional. Esse documento MUST ser
atualizado sempre que um módulo novo for adicionado ou o fluxo entre módulos
mudar.

A documentação de uso — o README da raiz e o de cada módulo — é escrita para
quem vai **operar** o pipeline, nunca um registro de como ele foi construído,
e é enxuta, organizada e objetiva: MUST NOT citar o spec-kit, esta
constitution e seus princípios, identificadores de requisito (`FR-`, `SC-`) ou
de tarefa (`T035`), caminhos `specs/NNN-...` nem narrar o processo de
implementação ("a auditoria achou X e foi corrigido"). Uma decisão de desenho é
explicada em linguagem comum, com um link para a seção correspondente de
`docs/metodologia-referencia.md` quando for preciso mais profundidade. O
"como executar" de um módulo tem **só dois cenários**: rodar do zero, ou
descompactar/usar o que já existe (o pacote versionado que outra pessoa
gerou) — nunca cenários adicionais. **Todos** os comandos do módulo e suas
variações (opções, escopo de um problema só, paralelismo, o que a interrupção e
a retomada fazem) ficam numa única tabela, não em seções próprias; a mesma
lista completa consta na "Referência de comandos" do README da raiz. Um comando
é sempre `python -m <pacote> <subcomando>`, com nome limpo, nunca o caminho de
um script. O detalhe exato dessas regras, e a verificação automática que as
garante (`scripts/check_docs_sync.py`, inclusive a checagem C8), ficam em
`docs/template-modulo.md`, que MUST ser mantido alinhado a este princípio.
**Esta regra não vale para `docs/metodologia-referencia.md`**: ali, rótulos
de decisão, medições datadas e o histórico de descobertas MUST permanecer —
é exatamente esse aparato de citação que sustenta a atualização do texto do
TCC. A distinção: o README explica o quê e o como para quem opera o
pipeline; a metodologia registra o porquê e a evidência para quem escreve ou
avalia o trabalho, e por isso mantém as duas coisas que o README não tem —
rótulo de decisão e proveniência (tarefa, data, revisão) de cada achado.

A ausência de qualquer uma dessas três documentações (metodologia
sincronizada, documentação de módulo padronizada, visão geral do projeto)
impede considerar o módulo ou a feature concluídos, no mesmo espírito do
Princípio VI (testes). Motivo: o documento de metodologia é a base da
atualização do texto escrito do TCC; sem sincronização, o que o código faz e o
que a metodologia documentada diz divergem sem que ninguém perceba. A
documentação de uso, por sua vez, existe para que qualquer pessoa — inclusive
alguém que nunca participou do desenvolvimento — saiba exatamente o que fazer
a partir do cenário em que se encontra, sem precisar entender o processo pelo
qual o projeto chegou até ali.

## Convenções Técnicas

- **Linguagem principal**: Python 3.11+.
- **Testes**: `pytest` para o pipeline; suíte própria de casos conhecidos
  para módulos de infraestrutura (Princípio VI).
- **Qualidade de código**: `ruff` (lint) e `black` (formatação) são
  obrigatórios antes de commit.
- **Nomenclatura**: código, nomes de função/variável e docstrings em inglês
  (convenção de mercado); documentação de metodologia pode ficar em
  português, espelhando o TCC.
- **C++ (sandbox)**: compilado via GCC 13.2+, com as flags e a cascata de
  fallback de padrão (gnu++20 → 17 → 14 → 11) descritas na metodologia.
- **Segredos**: chaves de API NUNCA são commitadas; ficam em `.env` (fora do
  Git e fora da imagem Docker), injetado no contêiner pelo `env_file` do
  compose ou carregado com `python-dotenv`, com `.env.example` versionado.
- **Dados**: a pasta de dados brutos (`data/`) MUST estar em `.gitignore`,
  com a única exceção de `data/dataset.zip` (Princípio II). Toda
  geração/regeneração de dataset ou de mutantes MUST produzir (ou atualizar)
  um manifesto de hashes versionado no repositório, e MUST existir um comando
  de verificação de integridade contra esse manifesto.
- **Documentação** (Princípio XI): o template de documentação de módulo é
  `docs/template-modulo.md`; cada módulo tem `src/<modulo>/README.md` conforme
  esse template; a visão geral do projeto é o `README.md` da raiz; a fonte
  corrente da metodologia é `docs/metodologia-referencia.md`, com seu histórico
  de atualizações datado.

## Fluxo de Desenvolvimento

- Cada módulo do pipeline corresponde a uma feature numerada do spec-kit
  (`001-dataset-extraction`, `002-mutant-generation`, etc.), seguindo o
  ciclo specify → clarify → plan → tasks → implement → converge.
- Nenhuma feature é considerada "implementada" sem os testes do Princípio VI
  passando e sem a documentação do Princípio XI (metodologia sincronizada,
  README do módulo conforme o template e visão geral do projeto atualizada).
- O `tasks.md` de cada feature MUST incluir as tarefas de documentação do
  Princípio XI, e `/speckit.specify`, `/speckit.plan` e `/speckit.tasks` MUST
  terminar com a metodologia sincronizada com o que descobriram ou decidiram.
- Mudanças nesta constitution exigem acordo dos autores.
- Antes de rodar `/speckit.specify` de um módulo, o trecho relevante de
  `docs/metodologia-referencia.md` MUST ser colado ou referenciado
  explicitamente na conversa com o agente.

## Governance

Este documento tem precedência sobre decisões pontuais de implementação.

- **Emendas**: exigem acordo dos autores e MUST ser registradas com data e
  justificativa, atualizando a linha de versão abaixo.
- **Versionamento** (semântico): MAJOR para remoção ou redefinição
  incompatível de princípios ou da governança; MINOR para novo princípio ou
  seção, ou ampliação material de orientação; PATCH para esclarecimentos,
  redação e correções não semânticas.
- **Verificação de conformidade**: o plano de cada feature (`plan.md`) MUST
  verificar conformidade com estes princípios, e a revisão de cada mudança
  (Princípio X) MUST checar violações, incluindo a propagação da documentação
  (Princípio XI). Qualquer violação intencional MUST ser justificada por
  escrito na feature correspondente.
- **Histórico de emendas**:
  - 1.7.0 (2026-09-25) — Princípios II e XI. II: a coerência entre os artefatos
    (dataset descompactado × mutantes, 1:1, com todos os arquivos de cada
    problema) passa a ser conferida por um comando próprio, `python -m cli
    check`, cujo modo `--deep` MUST passar antes de etapas que consomem os
    dados; módulos novos acrescentam a sua camada. XI: a documentação de uso
    passa a ter só dois cenários (rodar do zero ou descompactar o que já
    existe), uma única tabela com todos os comandos e variações, comandos com
    nome limpo (`python -m <pacote> <sub>`, nunca caminho de script) e nenhuma
    citação ao spec-kit, à constitution, a requisitos ou a tarefas (checagem
    automática C8). Justificativa: a pedido de Rafael, ao concluir o módulo de
    mutantes — os READMEs tinham ficado extensos e confusos (seções por
    cenário demais, retomada e variações espalhadas, referências ao processo de
    especificação), e a verificação de integridade de cada artefato não
    cobria o conjunto (`dataset verify` sem `--extracted` só conferia o zip;
    nada conferia se dataset e mutantes estavam completos e 1:1).
  - 1.6.0 (2026-09-23) — Princípio II: a exceção de versionamento antes exclusiva do dataset
    (emenda 1.1.0) passa a poder se estender a qualquer artefato do experimento cuja
    identidade dependa de execução real de código de terceiros no motor (mutantes; módulos
    futuros que validem suítes geradas contra AC/WA/mutantes) ou de chamadas a APIs de IA não
    estritamente reprodutíveis bit a bit — uma vez concluída a execução final que sustenta os
    números publicados, esse artefato MAY ser compactado e commitado com seu próprio
    manifesto; iterações de desenvolvimento continuam nunca sendo versionadas. Justificativa:
    ao especificar o módulo `002-mutant-generation`, Rafael observou que "gerar mutantes é
    sempre determinístico" não se sustenta, porque a validação de cada mutante reutiliza o
    mesmo motor de execução cuja instabilidade de margem já foi medida na auditoria do módulo
    de dataset (D18/D19 da spec `001-dataset-extraction`: 20 dos 200 problemas precisaram de
    reparo por veredito instável entre execuções independentes do mesmo binário, por
    comportamento indefinido ou tempo no limiar do limite, nunca por lógica de seleção). Regenerar
    localmente com a mesma seed reduz, mas não garante, reproduzir exatamente o mesmo conjunto —
    o mesmo argumento que já levou a versionar o dataset em vez de confiar apenas em "seed 42
    sempre reproduz". Estender a mesma exceção, pelo mesmo motivo, evita que os números do TCC
    dependam de uma garantia de determinismo que o próprio projeto já provou não se sustentar
    sempre.
  - 1.5.0 (2026-09-22) — Princípio XI: o README da raiz é sumário e índice,
    não um substituto do README de cada módulo (MUST NOT duplicar o passo a
    passo operacional de um módulo). Novo parágrafo: a documentação de uso
    (README da raiz e de cada módulo) é escrita para quem opera o pipeline,
    nunca um registro do processo de implementação — MUST NOT citar
    identificadores de tarefa do spec-kit nem narrar como algo foi
    construído; decisões de desenho em linguagem comum, com link para a
    metodologia, nunca só pelo rótulo interno (`D13`, `FR-011b`); um módulo
    com mais de um ponto de entrada organiza o "como executar" por cenário
    de uso, não por ordem cronológica de implementação. Essa regra
    explicitamente NÃO vale para `docs/metodologia-referencia.md`, que
    mantém rótulos de decisão e proveniência datada porque sustenta a
    atualização do texto do TCC. Justificativa: ao concluir a primeira
    feature (extração do dataset e motor de execução), os autores pediram
    uma reorganização geral dos READMEs — sem referências ao trabalho da IA
    nem a tarefas do spec-kit, organizados por cenário de uso — e que essa
    regra ficasse escrita de forma que não dependesse do contexto de uma
    conversa para valer nos módulos seguintes; o detalhe operacional da
    regra já vivia em `docs/template-modulo.md` (regra 10, acrescentada no
    mesmo ciclo), mas o texto do README da raiz ("reproduzir... seguindo
    apenas esse documento") contradizia o novo formato de índice, e por isso
    precisava de emenda aqui, não só no template.
  - 1.4.0 (2026-09-22) — Princípio X: o agente de IA trabalha sempre no
    checkout normal do autor, nunca isolado em worktree ou branch própria, e
    nunca roda `git add` (nem só `git commit`); toda alteração fica
    `modified`/`untracked`, nunca `staged`; `.claude/settings.json`
    (`worktree.bgIsolation: "none"`) versionado para que nenhuma sessão
    isole por padrão. Novo parágrafo: ao parar para revisão, o relato MUST
    detalhar o que foi feito (arquivos, decisões, achados, números) e dizer
    os comandos de conferência (testes, `check_docs_sync.py`, lint).
    Justificativa: a primeira versão desta regra (1.3.0) ainda permitia
    isolar o trabalho num worktree e deixar mudanças `staged`; os autores
    pediram explicitamente que o trabalho aconteça direto na branch corrente
    e sem nem `git add`, e que os relatos de parada sejam detalhados o
    bastante para conferência sem reabrir o código.
  - 1.3.0 (2026-09-22) — Princípio X: nenhum agente de IA executa `git
    commit`, `git push` ou qualquer operação que altere o histórico do
    repositório por conta própria, mesmo isolado em worktree ou só para
    documentação; o agente prepara e devolve para um dos autores decidir e
    commitar. Justificativa: um agente havia commitado mudanças de
    documentação por iniciativa própria em worktree; os autores explicitaram
    que a revisão humana do Princípio X só é efetiva se o commit em si for
    sempre um ato humano, nunca automático. Princípio XI: carimbar um
    comando na tabela "Comandos verificados" de um README não basta como
    propagação — MUST-se também reler por busca textual, e corrigir, toda a
    prosa do README do módulo e do `README.md` da raiz que mencione o mesmo
    comando. Justificativa: a T072 da feature 001 carimbou `audit` na tabela
    mas deixou duas frases em dois READMEs dizendo "a auditoria ainda não
    rodou", contradição só notada e corrigida numa tarefa seguinte (T073); a
    regra evita que a mesma lacuna se repita.
  - 1.2.1 (2026-09-19) — Convenções Técnicas, "Segredos": a convenção deixa de
    exigir literalmente `python-dotenv` e passa a admitir `.env` injetado por
    `env_file` do compose ou carregado com `python-dotenv`. Justificativa: como
    todo o pipeline roda em contêiner, o `env_file` cumpre o mesmo objetivo (chaves
    nunca commitadas nem dentro da imagem, `.env.example` versionado) sem
    dependência extra, e o mesmo desvio se repetiria em cada feature que usa
    segredos (a primeira será `ai_clients`); resolvê-lo uma vez na convenção evita
    justificativas repetidas por feature. Nenhum princípio foi alterado.
  - 1.2.0 (2026-09-19) — Novo Princípio XI (Documentação Viva, Sincronizada e
    Padronizada): propagação de toda informação nova para todos os documentos
    afetados no mesmo ciclo de trabalho, com `docs/metodologia-referencia.md`
    sempre corrente; documentação de uso padronizada por módulo
    (`docs/template-modulo.md`, seis campos); visão geral do projeto na raiz;
    ausência de qualquer uma impede concluir módulo ou feature. Convenções
    Técnicas, Fluxo de Desenvolvimento e Governance ajustados. Justificativa: a
    falta de uma regra formal permitiu que dados medidos empiricamente durante o
    planejamento da extração do dataset (tamanhos do dataset, funil de
    elegibilidade, disponibilidade de submissões incorretas, entre outros) e
    itens do plano marcados como "a refletir" não fossem propagados para o
    documento de referência, criando risco de inconsistência entre o que o
    código faz e o que a metodologia documentada diz. Como a metodologia será
    usada ao final para atualizar o trabalho escrito, ela precisa estar correta
    a todo momento.
  - 1.1.0 (2026-09-18) — Princípio II: o dataset, após extração e validação
    únicas, pode ser versionado compactado em `data/dataset.zip`, acompanhado
    do manifesto SHA-256; arquivos soltos e mutantes continuam nunca
    versionados. Justificativa: a dockerização garante a reprodutibilidade do
    ambiente de execução, não a distribuição dos dados do experimento;
    versionar o dataset compactado, verificável pelo manifesto, permite que
    qualquer pessoa obtenha exatamente os mesmos dados. Convenção "Dados"
    ajustada para admitir essa exceção.
  - 1.0.0 (2026-09-18) — Ratificação inicial.

**Version**: 1.7.0 | **Ratified**: 2026-09-18 | **Last Amended**: 2026-09-25
