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
do dataset extraído, mutantes gerados) NUNCA são versionados no Git. A única
exceção é o dataset: após a extração e validação únicas, ele MAY ser
compactado em `data/dataset.zip` e commitado no repositório, desde que
acompanhado do manifesto de integridade. Os mutantes gerados não têm essa
exceção e continuam nunca sendo versionados.

Todo dado persistido pelo experimento MUST ser coberto por um manifesto de
integridade commitado, contendo o hash (SHA-256) de cada arquivo persistido
(incluindo `data/dataset.zip`, quando versionado). A integridade e a
identidade exata de uma versão do dataset ou dos mutantes são verificáveis a
qualquer momento recalculando os hashes e comparando com o manifesto.

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
ser considerada concluída enquanto essa propagação estiver pendente.

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
os módulos se conectam entre si, e reproduzir o experimento completo do zero
(da extração do dataset até a análise final dos dados) seguindo apenas esse
documento. Esse documento MUST ser atualizado sempre que um módulo novo for
adicionado ou o fluxo entre módulos mudar.

A ausência de qualquer uma dessas três documentações (metodologia
sincronizada, documentação de módulo padronizada, visão geral do projeto)
impede considerar o módulo ou a feature concluídos, no mesmo espírito do
Princípio VI (testes). Motivo: o documento de metodologia é a base da
atualização do texto escrito do TCC; sem sincronização, o que o código faz e o
que a metodologia documentada diz divergem sem que ninguém perceba.

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

**Version**: 1.2.1 | **Ratified**: 2026-09-18 | **Last Amended**: 2026-09-19
