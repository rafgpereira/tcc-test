# Contrato: páginas do painel

Comum a todas as páginas: a barra lateral tem a pasta de avaliação, o botão **recarregar dados**,
a hora da última leitura, os problemas concluídos por conjunto, os arquivos inválidos (se houver) e
os filtros (conjunto, cenário, problema, macrocategoria, status da suíte). Toda porcentagem de
detecção traz o rótulo **prévia**. Toda tabela tem o download em CSV, já com os filtros aplicados
(FR-012).

| Página | História | Mostra | Interação |
|---|---|---|---|
| **Visão geral** | US1 | por conjunto × cenário: combinações, sem suíte (por motivo), AC reprovado, testes do AC com saída diferente e com erro, % de WAs e de mutantes detectados (declarado e corrigido, prévia), instáveis, alvos sem compilar; abaixo, a tabela por problema | só filtros |
| **Combinação** | US2 | escolha de conjunto → problema → cenário (SC-003); cabeçalho (status, origem, tamanho, AC aprovado, aviso de suíte alterada); tabela teste a teste (entrada, esperada, real, veredito do AC, detecções por teste em cada oráculo); lista dos alvos pegos só pelo declarado | escolher um alvo abre o detalhe: detecção em cada oráculo e o código lado a lado com o `AC_ref` (FR-007a) |
| **Comparações** | US3 | declarado × corrigido por combinação, com AC reprovado destacado; `slm` × `slm-attempt1` × comerciais por cenário | filtros |
| **Métricas** | US4 | aviso "métricas oficiais ainda não calculadas" e como gerá-las, enquanto a 010 não existir | — |

Estados vazios: pasta sem resultados (mensagem com o comando `evaluation run`); filtro sem linhas
("nenhuma combinação com esses filtros"); suíte ou código não descompactados (aviso no lugar da
coluna, o resto continua).
