# Quickstart: validar o dashboard (011)

Comandos em [contracts/cli.md](contracts/cli.md); páginas em [contracts/pages.md](contracts/pages.md).

## Pré-requisitos

- Imagem reconstruída depois de entrar o Streamlit: `docker compose build`.
- Alguma avaliação concluída: o piloto em `data/evaluation/`, ou a conferência em
  `data/evaluation-conf/`. Dataset, mutantes e suítes descompactados, para o detalhe completo.

## 1. Testes

```bash
docker compose run --rm sandbox pytest tests/dashboard
```

Esperado: tudo `passed`.

## 2. Abrir

```bash
docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve
```

Abrir `http://localhost:8501` no navegador.

## 3. Conferir contra o relatório (SC-001)

- Rodar `docker compose run --rm app python -m evaluation report` e comparar o resumo de cada
  conjunto com a página **Visão geral**, sem filtros: AC aprovado e reprovado, testes do AC por
  veredito e detectados em cada oráculo devem coincidir.

## 4. Conferir o detalhe (SC-003, SC-004)

- Página **Combinação** → `gemini` → `1000_B` → `black_box` (na pasta do piloto, `data/evaluation`;
  ou, se o piloto ainda não fechou o `1000_B`, na conferência `data/evaluation-conf`): os
  testes 4, 7 e 9 têm saída esperada diferente da real; a lista "só pelo declarado" tem 14 WAs;
  abrir `WA_3` mostra a detecção no declarado (teste 4), nenhuma no corrigido e o código ao lado do
  `AC_ref`.

## 5. Recarregar durante uma avaliação

- Com um `evaluation run` em andamento, clicar em **recarregar dados**: a contagem de problemas
  concluídos e a hora da leitura mudam.

## 6. Só leitura (SC-005)

- `git status` e a lista de arquivos de `data/` são iguais antes e depois de navegar por todas as
  páginas.
