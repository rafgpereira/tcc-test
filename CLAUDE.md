# CLAUDE.md

Contexto rápido para qualquer sessão do Claude Code neste repositório. Para
princípios de arquitetura, ver `.specify/memory/constitution.md`. Para o
desenho experimental do TCC, ver `docs/metodologia-referencia.md`. Para a
visão geral da arquitetura e de como reproduzir o experimento, ver
`README.md`. Leia a constitution e a metodologia antes de especificar ou
implementar qualquer módulo novo.

## O que é este projeto
Pipeline experimental (Python) que avalia geração automática de testes por
LLMs/SLM em C++, sob 3 cenários de contexto (requisito, código, híbrido).
TCC de dupla — Milena e Rafael, UnB.

## Estrutura
- `README.md` — visão geral do projeto (arquitetura, módulos, como reproduzir)
- `docs/metodologia-referencia.md` — desenho experimental **corrente**, com
  histórico de atualizações datado; `docs/template-modulo.md` — formato do
  README de cada módulo; `docs/verificacao-consistencia.md` — o que
  `python -m cli check` confere entre os artefatos (dataset, mutantes e as
  suítes dos 4 modelos) e como um módulo novo o estende
- `src/dataset/` — extração e validação do dataset (code_contests)
- `src/mutation/` — geração de mutantes
- `src/ai_clients/` — suítes de teste do modelo local (SLM, Qwen2.5-Coder-14B via Ollama) e, em
  `src/ai_clients/llm/`, dos 3 modelos comerciais (GPT-5.4-mini, Gemini 3.8 Flash e Claude Haiku 5.5,
  `--model gpt|gemini|claude`; `specs/004-llm-test-generation/` e, para o Claude,
  `specs/008-claude-test-generation/`)
- `src/prompt_templates/` — texto-base dos pedidos ao SLM (solução e predição) e aos 3 modelos
  comerciais (`llm_prompt.txt`)
- `src/sandbox/` — compilação e execução isolada em C++
- `src/evaluation/` — executa cada suíte (4 modelos e a 1ª tentativa do SLM) contra AC, WAs e
  mutantes: AC sem curto-circuito, alvos com curto-circuito e dois oráculos (o declarado e o
  corrigido pelo AC), erro de execução repetido 3 vezes (`specs/009-suite-evaluation/`)
- `src/dashboard/` — painel Streamlit só de leitura sobre os resultados: o experimento, as métricas
  (placar e guia de escolha), a rastreabilidade (de um número ao problema, à suíte e ao teste) e a
  avaliação (`specs/011-results-dashboard/`, `specs/012-dashboard-storytelling/`)
- `src/metrics/` — TDF, MS, TFP, IIC, TC, TDF*/MS*/Δ_oráculo, TFP por causa, custo por detecção,
  densidade, Friedman/Wilcoxon/McNemar com Holm e A12, e as figuras (desenhadas sob demanda, fora do
  pacote); tabelas em `data/metrics/`
  (`specs/010-metrics/`)
- `src/cli/` — comandos que cruzam módulos (hoje `check`) e, no futuro, o orquestrador que amarra tudo
  (cada `src/<modulo>/` tem `README.md` no formato de `docs/template-modulo.md`)
- `data/dataset.zip` — dataset validado, compactado e versionado; hoje a **revisão 2** (2026-10-18: 104
  enunciados corrigidos, nenhum outro arquivo mudou; o que mudou em `manifests/dataset_revision.json`,
  as decisões dos 15 revisados em `manifests/statement_decisions/`). A revisão 1 fica em
  `data/dataset.rev1.zip` + `manifests/dataset.rev1.manifest.json`, só para auditoria; nenhum comando a
  usa (Constitution, Princípio II, 1.8.0)
- `manifests/dataset.manifest.json` — hashes SHA-256 para verificação de
  integridade do dataset. Fica **fora de `data/`** (que é ignorado pelo Git,
  exceto o zip) e é versionado; `manifests/extraction_report.json` traz o
  relatório final da extração
- `data/mutants.zip` + `manifests/mutants.manifest.json` — mutantes da execução final e seus
  hashes
- `data/statement_originals.zip` + `manifests/statement_originals.manifest.json` +
  `manifests/statement_fidelity_report.json` — os enunciados originais do Codeforces (só o bloco do
  enunciado, com hash) e a conferência deles contra os `enunciado.md` do dataset (2026-10-18: 152
  expoentes perdidos em 79 problemas, 701 índices em 74), base da revisão 2 do dataset
- `data/slm_suites.zip` + `manifests/slm_suites.manifest.json` +
  `manifests/slm_generation_report.json` — pacote final do SLM, seu manifesto e o relatório; desde
  2026-10-22 o pacote junta a execução da revisão 1 (392 combinações) e a refeita na revisão 2 (as 208
  afetadas), com a origem em `provenance.json` (504 `accepted`, 95 `accepted_fallback`, 1
  `accepted_predicted`)
- `data/gpt_suites.zip`, `data/gemini_suites.zip`, `data/claude_suites.zip` + `manifests/<modelo>_suites.manifest.json` +
  `manifests/<modelo>_generation_report.json` — pacotes da execução final de cada modelo
  comercial; os do Gemini (599 `accepted_predicted` e 1 `accepted_barred`, US$ 4,90) e do GPT (600
  `accepted_predicted`, US$ 13,47) e do Claude (589 `accepted_predicted`, 8 `accepted_barred`, 3
  `discarded_manual`, US$ 0,98) gerados em 2026-10-20 sobre a revisão 2 do dataset
- `specs/NNN-nome/` — specs do spec-kit, uma por módulo
- `Dockerfile` / `docker-compose.yml` — ambiente de execução reprodutível
  (Constitution, Princípio II)

## Ambiente: Docker cobre execução, não distribuição de dados
Por exigência da constitution, compilação/execução C++ (sandbox) e as
dependências do pipeline rodam containerizadas, garantindo GCC/flags/libs
idênticos em qualquer máquina. Docker NÃO é o mecanismo de distribuição do
dataset — isso é resolvido pelo `data/dataset.zip` commitado no repositório
(gerado uma vez, após extração e validação, e alterado só por revisões numeradas, como a revisão 2). Nunca rodar compilação ou
execução de código C++ de terceiros fora do container.

## Comandos do dia a dia
A lista completa e atual de comandos (com serviço, estado e onde está o passo a passo) é a seção
"Referência de comandos" do `README.md`; todo comando novo entra lá, e o
`scripts/check_docs_sync.py` confere que cada subcomando da CLI aparece nela. Resumo:
- Preparar o ambiente (uma vez; explicado passo a passo no `README.md`): criar `.env` com
  `HOST_UID`/`HOST_GID` (saídas de `id -u` e `id -g`) e `mkdir -p data`
- Build da imagem: `docker compose build`
- Rodar testes do pipeline: `docker compose run --rm sandbox pytest` (os
  testes compilam e executam C++, então rodam no serviço `sandbox`, sem rede;
  o serviço `app` é o que tem rede, para extração e empacotamento); de uma
  parte só: `docker compose run --rm sandbox pytest tests/sandbox`
- Conferir o motor de execução: `docker compose run --rm sandbox python -m dataset selfcheck`
- Extrair o pool do dataset (`app`, com rede): `docker compose run --rm app python -m dataset extract`
  e `... report`
- Conferir a documentação: `docker compose run --rm app python scripts/check_docs_sync.py`
- Suítes do modelo local (`ai_clients`; precisa de `OLLAMA_BASE_URL` e `OLLAMA_HARDWARE_LABEL` no
  `.env`): alternar `docker compose run --rm app python -m ai_clients generate [--resume]` e
  `docker compose run --rm sandbox python -m ai_clients execute` até o `execute` não imprimir
  `next:` (código `4` = algum problema e cenário aguarda os autores: decidir e fechar com
  `docker compose run --rm app python -m ai_clients close --problem ID --scenario S --reason "..."`);
  depois `docker compose run --rm app python -m ai_clients report`, `... package` e
  `... verify [--extracted data/suites/slm]`. Com duas máquinas de Ollama, vários `generate
  --resume` (cada um com `-e OLLAMA_BASE_URL=...` e todos os problemas, que eles dividem
  sozinhos) e um `execute` rodam juntos; `close`, `package` e o primeiro `generate` só rodam sozinhos (laço pronto no README do
  módulo). Trocar um texto-base no meio da execução só com `docker compose run --rm app python -m
  ai_clients change-template --template prediction --reason "..."` (move os pedidos da versão
  antiga para `superseded/` e eles são refeitos; nunca editar o template e seguir)
- Suítes dos modelos comerciais (precisa de `OPENAI_API_KEY`/`GEMINI_API_KEY`/`ANTHROPIC_API_KEY` no `.env`; **cada
  chamada custa**): estimar com `docker compose run --rm app python -m ai_clients generate --model
  gpt --dry-run` (não chama nada), gerar com `... generate --model gpt --confirm-spend <US$>` (a
  confirmação é o teto de gasto da invocação; sem ela, nenhuma chamada sai; código `5` = teto
  atingido; resposta sem raciocínio fica em `barred/` e é pedida de novo; na terceira, a suíte é `accepted_barred`, sem parar o comando) e continuar com `--resume`; os mesmos
  `close`, `change-template --template llm`, `report`, `package` e `verify` com `--model gpt`,
  `--model gemini` ou `--model claude`. Os três modelos podem rodar juntos, um por terminal. O agente nunca roda uma
  geração paga sem pedido explícito dos autores
- Ver o pedido enviado a um modelo (só lê, não chama nada, nunca imprime o pedido): `docker compose
  run --rm app python -m ai_clients show-request --model gemini --problem ID --scenario S --output
  data/requests/X.json [--attempt N | --barred N] [--suites-dir data/suites/gemini-piloto1]`
  (grava o corpo, com o prompt dentro, conferido contra o hash gravado e o dataset; texto-base mudado:
  busca a versão no Git, por isso só no `app`, que monta o `.git` somente leitura); todos os pedidos
  pendentes de um modelo: `... generate --model gpt --dry-run --save-requests data/requests [--force]`
  (um `<id>.<cenário>.request.json` por combinação e um `summary.json` com a fidelidade ao dataset e
  os expoentes perdidos; `1` se algum prompt não for fiel); o pedido da tentativa que gerou cada
  suíte, de uma vez: `... show-request --model slm --suite-attempts --output-dir data/requests/suites`
- Conferir os enunciados contra o original do Codeforces (`app`; baixa cada página uma vez, a cada
  3 s ou mais, e depois não acessa mais o site): `docker compose run --rm app python -m dataset
  check-statements [--problem ID] [--refetch]`; os corrigidos para revisão (nunca altera o dataset):
  `... python -m dataset correct-statements --output-dir data/statements/corrected [--force]`
- Avaliação das suítes (`sandbox`; portões: auto-checagem do motor e `cli check --deep`): piloto
  `docker compose run --rm sandbox python -m evaluation run --problem 1000_B --problem 1005_C
  --problem 1008_B --problem 1_B --problem 61_B`, depois `run` sem `--problem` (retoma); no `app`,
  `python -m evaluation report`, `package --set S` e `verify --set S [--extracted ...]`, com
  S em `slm|gpt|gemini|claude|slm-attempt1`. O piloto e a execução completa só com pedido dos autores
- Métricas (`app`; só lê a avaliação): `docker compose run --rm app python -m metrics compute`,
  `... figures [--macrocategoria M --set S ...]`, `... package` e `... verify [--extracted data/metrics]`
- Painel dos resultados (só lê; porta só nesta máquina): `docker compose run --rm -p
  127.0.0.1:8501:8501 app python -m dashboard serve [--evaluation-dir DIR]` e abrir
  `http://localhost:8501`
- Conferir a consistência entre artefatos (dataset descompactado × mutantes × suítes dos 4
  modelos × avaliações, 1:1, com contagens; só lê): `docker compose run --rm app python -m cli check [--deep]`. Todo módulo que
  passa a produzir uma pasta por problema MUST entrar nele (`docs/verificacao-consistencia.md`)
- Lint/formatação: `docker compose run --rm app ruff check .` /
  `docker compose run --rm app black .`
- Verificar integridade do dataset local (compara contra
  `manifests/dataset.manifest.json`):
  `docker compose run --rm app python -m dataset verify` — sem opções confere só o **zip**;
  para conferir a pasta `data/dataset/` use `--extracted data/dataset`
- Obter o dataset (qualquer integrante, sem rodar extração; quem gerou o dataset também precisa
  descompactar, nenhum comando cria `data/dataset/`):
  `git pull && unzip data/dataset.zip -d data/`

## Regras rápidas (resumo — detalhe está na constitution)
- **O agente de IA trabalha direto no checkout normal do autor (a branch
  `main` local), nunca em worktree ou branch própria, e nunca roda `git add`,
  `git commit`, `git push` nem qualquer operação que altere o histórico do
  Git** (merge, rebase, reset de branch compartilhada) — nem mesmo mudanças
  só de documentação (Constitution, Princípio X). Ele edita os arquivos
  normalmente, deixa tudo como alteração **não adicionada e não commitada**
  (`git status` mostra `modified`/`untracked`, nunca `staged`), e diz ao
  autor, com o comando exato, quando algo está pronto para ser commitado;
  quem decide o quê e quando commitar é sempre um dos dois autores. Regra
  igual em toda sessão deste projeto, não só na conversa em que foi
  combinada — por isso `.claude/settings.json` (`worktree.bgIsolation:
  "none"`) também é versionado, para nenhuma sessão futura isolar o trabalho
  num worktree por padrão.
- **Ao terminar uma etapa de trabalho e parar para o autor revisar**, o
  agente detalha o que foi feito (arquivos, decisões, achados, números) e diz
  explicitamente quais comandos o autor pode rodar para conferir por si (por
  exemplo, os testes novos ou afetados, `check_docs_sync.py`, `ruff`/`black`)
  — nunca só "feito" ou um resumo genérico.
- Toda chamada de IA na parte específica do experimento em que os códigos/enunciados são enviados para as IAs, é stateless — nunca reaproveitar contexto entre requisições à essas APIs de IA.
- Nenhum limite de tempo/memória de sandbox é hardcoded — sempre lido dos
  metadados do problema.
- Compilação/execução de código C++ de terceiros só dentro do container.
- Módulo de infraestrutura (dataset, mutação, sandbox, métricas) sem teste
  unitário próprio não é considerado pronto.
- Segredos de API só em `.env` (nunca commitado, nem dentro da imagem
  Docker); `.env.example` versionado como referência.
- Documentação viva (Constitution, Princípio XI): todo dado medido,
  divergência ou decisão nova deve ser propagado, no mesmo ciclo de trabalho,
  para `spec.md`, `plan.md` (e demais artefatos afetados) **e** para
  `docs/metodologia-referencia.md`, que precisa estar sempre corrente. Nunca
  registrar em um lugar só, nunca deixar "para refletir depois". Uma tarefa
  não está concluída com essa propagação pendente. **Carimbar um comando na
  tabela "Comandos verificados" de um README não é, sozinho, propagação
  completa**: depois de carimbar, procure o nome do comando em todo o texto
  do README do módulo e do `README.md` da raiz (grep, não só memória) e
  corrija qualquer trecho que ainda o descreva como não executado/planejado —
  a tabela e a prosa nunca podem se contradizer (achado real: a T072 carimbou
  `audit` mas deixou duas frases dizendo "ainda não rodou" em dois READMEs
  diferentes, só corrigidas na T073 seguinte).
- Documentação de execução escrita para quem **não conhece Docker**: o `README.md` da raiz é um
  guia geral (arquitetura, preparação única do ambiente) que aponta, como um índice, para o
  README de cada módulo; o "(b) Como executar" de cada módulo é que detalha o funcionamento
  daquele módulo (serviço explicado, resultado esperado, como conferir, falhas comuns),
  organizado nos **dois cenários** (do zero / usar o que já existe), não como um log cronológico
  de desenvolvimento. Nunca supor que um termo ou valor de configuração é conhecido, e não afirmar
  tempo ou tamanho não medidos.
- **READMEs (raiz e de cada módulo) são documentação de uso: enxutos, organizados, objetivos.** Só
  **dois cenários** no "como executar": rodar do zero, ou descompactar/usar o que já existe. **Todos
  os comandos e suas variações numa única tabela** (opções, `--problem`, paralelismo, o que a
  interrupção e a retomada fazem), sem seção própria para retomada ou variações; a mesma lista
  completa na "Referência de comandos" da raiz. Comando com **nome limpo**, sempre `python -m
  <pacote> <subcomando>` (nunca o caminho de um script). MUST NOT citar spec-kit, constitution,
  princípios, `FR-`/`SC-`, tarefas (`T035`), `specs/NNN-...` nem narrar o processo de construção; a
  proveniência datada das decisões fica só em `docs/metodologia-referencia.md`. Checado por
  `check_docs_sync.py` (C7 e C8); formato em `docs/template-modulo.md`. A tabela "Comandos
  verificados" tem só `Comando | Verificado em | Revisão`.
- Todo módulo tem `src/<modulo>/README.md` (template em
  `docs/template-modulo.md`, seis campos) e o `README.md` da raiz é atualizado
  quando um módulo é adicionado ou o fluxo entre módulos muda; sem isso o
  módulo/feature não está concluído.