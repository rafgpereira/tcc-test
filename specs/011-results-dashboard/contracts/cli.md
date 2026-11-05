# Contrato: `python -m dashboard`

## `serve`

```text
docker compose run --rm -p 127.0.0.1:8501:8501 app python -m dashboard serve [--evaluation-dir DIR] [--port N]
```

| Opção | Padrão | Efeito |
|---|---|---|
| `--evaluation-dir` | `data/evaluation` | pasta inicial (pode ser trocada no próprio painel) |
| `--port` | `8501` | porta dentro do contêiner; a publicada no `-p` tem de ser a mesma |

Comportamento: define `HOME=/tmp`, desliga a telemetria e o acompanhamento de arquivos (research R3)
e executa o Streamlit em `0.0.0.0:<porta>`, sem abrir navegador. Imprime
`dashboard: http://localhost:<porta> (Ctrl+C para fechar)`. Fica no ar até Ctrl+C.

Códigos de saída: `0` fechado normalmente ou por Ctrl+C; `2` uso incorreto (pasta inexistente);
`3` Streamlit ausente na imagem (`docker compose build`).

Não grava nada no repositório nem em `data/` (FR-003).
