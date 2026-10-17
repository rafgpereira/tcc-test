# Quickstart: validar a visualização do pedido

**Feature**: `specs/005-show-request` | **Date**: 2026-10-16 | **Plan**: [plan.md](./plan.md)

Roteiro de validação depois da implementação. Nada aqui chama uma API nem gasta. Os formatos estão
em [contracts/cli.md](./contracts/cli.md) e [data-model.md](./data-model.md). Os dois comandos
gravam o mesmo tipo de arquivo, o corpo da requisição com o prompt dentro (contrato §0); nenhum
deles imprime o pedido no terminal.

## Pré-requisitos

- `docker compose build` feito depois da implementação;
- o dataset descompactado: `unzip data/dataset.zip -d data/`;
- o `.git` montado no `app` (vem do `docker-compose.yml`). Para conferir:
  `docker compose run --rm app git -c safe.directory=* -C /app log --oneline -1` deve imprimir o
  último commit.

## Nível 1 — testes

```text
docker compose run --rm sandbox pytest tests/ai_clients/test_requests_view.py \
    tests/ai_clients/test_template_history.py tests/ai_clients/test_fidelity.py \
    tests/ai_clients/test_save_requests.py tests/ai_clients/llm/test_show_request.py
docker compose run --rm sandbox pytest        # a suíte inteira continua passando
```

**Esperado**: todos passam. No `sandbox` não há `.git` do projeto; os testes de Git criam o próprio
repositório temporário (R9).

## Nível 2 — dry-run com gravação no dataset real (US4, SC-005)

```text
docker compose run --rm app python -m ai_clients generate --model gpt --dry-run --save-requests data/requests
docker compose run --rm app python -m ai_clients generate --model slm --dry-run --save-requests data/requests
docker compose run --rm app python -m ai_clients generate --model gemini --dry-run --save-requests data/requests
```

**Esperado**:
- **GPT**, antes da execução completa dele: `requests: 600 saved …; faithful 600/600`, 600
  arquivos `data/requests/gpt/<id>.<cenário>.request.json` e o `summary.json`;
- **SLM**: a execução dele terminou, então não há combinação pendente e nada é gravado. Para
  conferir os 600 pedidos do SLM, use uma árvore vazia, se a opção existir, ou confira as
  tentativas feitas pelo nível 3;
- **Gemini**: a execução completa já começou, então só as combinações pendentes são gravadas. Os
  autores rodam esse dry-run separadamente, e o número sai no resumo. Todas as gravadas têm de ser
  fiéis;
- **71 problemas** com aviso de expoente quando as 600 combinações estão pendentes: exatamente os
  listados na metodologia, seção 3 (R5). Cada um aparece nos 2 cenários com enunciado;
- código 0.

**Conferência à mão**: abrir `data/requests/gpt/1_B.black_box.request.json` e comparar o prompt
(no campo `input`) com `data/dataset/problems/1_B/enunciado.md`. O `≤` aparece legível no arquivo.
Na rede ele vai como `≤`, mas é o mesmo JSON (contrato §0).

**Recusas**:
- repetir o mesmo comando → código 2 (pasta com arquivos); com `--force` → regrava;
- `--save-requests data/suites/x` → código 2.

## Nível 3 — tentativas feitas (US1, US3, SC-001)

**Piloto do Gemini**: as 15 combinações de `data/suites/gemini-piloto1` devem dar código 0 e a
linha `written: … prompt sha256 matches; dataset: faithful`:

```text
for p in 1000_B 1005_C 1008_B 1_B 61_B; do for s in black_box white_box hybrid; do
  docker compose run --rm app python -m ai_clients show-request --model gemini \
      --problem $p --scenario $s --suites-dir data/suites/gemini-piloto1 \
      --output data/requests/piloto1/$p.$s.request.json; echo "$p $s $?"
done; done
```

Nenhuma dessas chamadas imprime o prompt no terminal.

**SLM**:
- `show-request --model slm --problem 1000_B --scenario black_box --attempt 1 --output …`: o
  corpo tem a seed e a temperatura da tentativa 1 em `options`;
- `--attempt 12`: a última tentativa com o texto-base de solução;
- uma combinação que chegou à predição (tentativas 13 a 15), se houver: o texto-base de predição;
- uma árvore de piloto antigo (`--suites-dir data/suites/slm-piloto2`), cujo texto-base mudou
  depois: `warning: OLD TEMPLATE VERSION from git <commit>` se o texto-base daquela época foi
  commitado; senão, código 1 com os dois hashes e nenhum arquivo criado.

**Não sobrescrever** (US3): repetir um `show-request` com o mesmo `--output` → código 2; com
`--force` → sobrescreve.

## Nível 4 — prévia (US2)

Antes de a execução completa do GPT começar:
- `show-request --model gpt --problem 1_B --scenario hybrid --output data/requests/1_B.hybrid.json`
  → `written: … preview, not sent (next: attempt 1)`, código 0;
- `--attempt 1` na mesma combinação → código 2 (`has no attempt 1`).

## Depois da validação

- carimbar `show-request` e `generate --dry-run --save-requests` na tabela "Comandos verificados"
  do README do módulo;
- procurar os dois nomes no README do módulo e no da raiz e corrigir qualquer trecho que ainda os
  dê como não executados;
- registrar na metodologia (seção 3 e histórico) os números medidos: combinações gravadas, fiéis,
  expoentes. O tempo não é medido (SC-003).
