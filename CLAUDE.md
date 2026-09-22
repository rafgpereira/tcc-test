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
  README de cada módulo
- `src/dataset/` — extração e validação do dataset (code_contests)
- `src/mutation/` — geração de mutantes
- `src/ai_clients/` — orquestração das chamadas aos 3 modelos
- `src/sandbox/` — compilação e execução isolada em C++
- `src/metrics/` — TDF, MS, TFP, IIC
- `src/cli/` — orquestrador que amarra tudo
  (cada `src/<modulo>/` tem `README.md` no formato de `docs/template-modulo.md`)
- `data/dataset.zip` — dataset validado, compactado, commitado uma única vez
  (Constitution, Princípio II)
- `manifests/dataset.manifest.json` — hashes SHA-256 para verificação de
  integridade do dataset. Fica **fora de `data/`** (que é ignorado pelo Git,
  exceto o zip) e é versionado; `manifests/extraction_report.json` traz o
  relatório final da extração
- `specs/NNN-nome/` — specs do spec-kit, uma por módulo
- `Dockerfile` / `docker-compose.yml` — ambiente de execução reprodutível
  (Constitution, Princípio II)

## Ambiente: Docker cobre execução, não distribuição de dados
Por exigência da constitution, compilação/execução C++ (sandbox) e as
dependências do pipeline rodam containerizadas, garantindo GCC/flags/libs
idênticos em qualquer máquina. Docker NÃO é o mecanismo de distribuição do
dataset — isso é resolvido pelo `data/dataset.zip` commitado no repositório
(gerado uma única vez, após extração e validação). Nunca rodar compilação ou
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
- Lint/formatação: `docker compose run --rm app ruff check .` /
  `docker compose run --rm app black .`
- Verificar integridade do dataset local (compara contra
  `manifests/dataset.manifest.json`):
  `docker compose run --rm app python scripts/verify_dataset.py`
- Obter o dataset (qualquer integrante, sem rodar extração):
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
- Toda chamada de IA é stateless — nunca reaproveitar contexto entre requisições.
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
- Documentação de execução escrita para quem **não conhece Docker**: o `README.md` da raiz traz
  o guia do clone ao primeiro comando (conceitos, `.env`, `data/`, build, verificação, problemas
  comuns) e o "(b) Como executar" de cada módulo é um passo a passo (serviço explicado, resultado
  esperado, como conferir, falhas comuns). Nunca supor que um termo ou valor de configuração é
  conhecido, e não afirmar tempo ou tamanho não medidos.
- Todo módulo tem `src/<modulo>/README.md` (template em
  `docs/template-modulo.md`, seis campos) e o `README.md` da raiz é atualizado
  quando um módulo é adicionado ou o fluxo entre módulos muda; sem isso o
  módulo/feature não está concluído.