# Research: Dashboard de exploração (011)

Nenhum `NEEDS CLARIFICATION` ficou no Technical Context. Cada item registra a decisão, o motivo e
as alternativas descartadas.

## R1. Biblioteca: Streamlit

- **Decision**: Streamlit **1.66.1** (fixado em 2026-11-05; o pandas ficou em 3.0.6, nenhuma outra
  versão do lock mudou), fixado no `uv.lock` (`uv add streamlit` no serviço `app`, depois
  `docker compose build`), numa versão que tenha navegação de várias páginas (`st.navigation`) e
  `streamlit.testing.v1.AppTest`.
- **Rationale**: é Python puro, os autores já o propuseram, mostra tabelas do pandas com filtro e
  download de CSV nativos (FR-012) e tem um testador de páginas sem navegador.
- **Alternatives considered**: Dash/Plotly (mais código de callback para o mesmo resultado);
  notebook (não é comando do projeto, e a versão anterior foi removida); HTML estático gerado (perde
  os filtros e o detalhe sob demanda).

## R2. Como abrir: `python -m dashboard serve` no serviço `app`

- **Decision**: o subcomando `serve` executa `streamlit run src/dashboard/app.py` com
  `--server.address 0.0.0.0 --server.port 8501 --server.headless true`. O README manda abrir com
  `docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve`.
- **Rationale**: o projeto exige nome limpo (`python -m <pacote> <subcomando>`). O `sandbox` não tem
  rede (`network_mode: none`) e não pode publicar porta; o `app` pode. Publicar só em `127.0.0.1`
  cumpre o uso local (FR-011): ninguém da rede alcança o painel.
- **Alternatives considered**: um serviço novo no compose (mais configuração para manter); publicar
  em todas as interfaces (expõe os dados na rede).

## R3. Contêiner somente leitura e telemetria

- **Decision**: `serve` define `HOME=/tmp`, `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false` e
  `STREAMLIT_SERVER_FILE_WATCHER_TYPE=none` antes de chamar o Streamlit. O `app` já tem `/tmp` em
  `tmpfs`.
- **Implementação (2026-11-05)**: ao subir, o Streamlit consultava o IP externo da máquina na
  internet (linha "External URL"); `STREAMLIT_BROWSER_SERVER_ADDRESS=localhost` evita a consulta.
- **Rationale**: a raiz do `app` é somente leitura, e o Streamlit escreve a sua configuração em
  `~/.streamlit`. A telemetria mandaria uso para fora, contra "os dados não saem da máquina"
  (FR-011). Não é preciso acompanhar mudanças de arquivo num painel só de leitura.

## R4. Leitura e cache

- **Decision**: `dashboard.data.combinations(base)` lê todos os `<cenário>.json` concluídos (ignora
  `building/`), valida cada um com `CombinationResult` e devolve um `DataFrame` (data-model.md),
  mais a lista de arquivos inválidos. O `app.py` guarda o resultado com `st.cache_data`, com uma
  chave formada pela pasta e por um contador que o botão "recarregar dados" incrementa (FR-001a). A
  hora da leitura vai junto.
- **Rationale**: ler e validar 3.000 arquivos uma vez cabe no limite de 1 minuto; os filtros
  trabalham sobre o `DataFrame` em memória (SC-002). O cache por chave explícita faz "recarregar"
  ser exatamente uma releitura.
- **Alternatives considered**: ler o `results.csv` (só existe depois do `report` e não tem a saída
  do AC nem as repetições); DuckDB (dependência a mais sem ganho nesse volume).

## R5. De onde vem cada dado do detalhe

- **Decision**: para o detalhe (US2), o resultado dá o veredito e a saída real do AC. A entrada e
  a saída esperada vêm da suíte, em `data/<suite_source.tree>/problems/<id>/<cenário>/suite.json`;
  em `slm-attempt1`, dos arquivos da tentativa (mesma regra de `evaluation.sources.attempt_suite`,
  que é reaproveitada). O código dos alvos vem do dataset e dos mutantes descompactados. A
  macrocategoria vem do `metadata.json`.
- **Rationale**: a avaliação não duplica a suíte no resultado; a origem gravada (`tree`, `attempt`
  e o hash) aponta exatamente o arquivo avaliado. Se o hash do arquivo lido diferir do gravado, o
  detalhe avisa que a suíte mudou desde a avaliação.

## R6. Código lado a lado

- **Decision**: `difflib.HtmlDiff(wrapcolumn=...)` da biblioteca padrão gera a tabela lado a lado
  com as linhas diferentes destacadas, exibida no painel. Para os WAs (submissões inteiras
  diferentes do AC), o mesmo diff, sem cortar contexto.
- **Rationale**: atende o FR-007a sem dependência nova.
- **Alternatives considered**: componentes de diff de terceiros (dependência sem necessidade).

## R7. Página de métricas antes da feature 010

- **Decision**: a página procura as tabelas da 010 num lugar fixo (`data/metrics/`, a confirmar
  pela própria 010). Se não existirem, mostra o aviso e o comando para gerá-las. A integração de
  verdade (colunas, gráficos) fica para uma tarefa aberta quando a 010 definir o formato.
- **Rationale**: o formato das tabelas ainda não existe; desenhá-lo aqui anteciparia uma decisão da
  010 (Princípio IX).

## R8. Testes

- **Decision**: `tests/dashboard/test_data.py` testa a camada de dados com árvores mínimas
  (reaproveitando os construtores de `tests/evaluation/conftest.py`): as contagens batem com
  `evaluation.report` para os mesmos arquivos (SC-001); `building/` é ignorado; o arquivo inválido é
  listado sem derrubar o resto; o filtro de macrocategoria; o detalhe com suíte final, `slm-rev1` e
  tentativa; o hash divergente; os arquivos de código ausentes. `tests/dashboard/test_pages.py` abre
  cada página com `AppTest` sobre uma árvore mínima e confere que ela roda sem exceção e mostra o
  rótulo "prévia". Também: nenhum arquivo muda depois de abrir todas as páginas (SC-005).
- **Rationale**: o Princípio VI exige testes de infraestrutura; o painel não é infraestrutura, mas a
  sua camada de dados produz números que precisam bater com o relatório.

## R9. Pacote das páginas: `views/`, não `pages/` (implementação, 2026-11-05)

- **Decision**: as páginas ficam em `src/dashboard/views/`.
- **Rationale**: o Streamlit trata uma pasta `pages/` ao lado do script principal como páginas
  automáticas, o que duplicaria a navegação montada por `st.navigation`.
