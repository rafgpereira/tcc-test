# Contrato da CLI: `show-request` e `generate --dry-run --save-requests`

**Feature**: `specs/005-show-request` | **Date**: 2026-10-16 | **Plan**: [../plan.md](../plan.md)

Os dois comandos rodam no serviço `app`, que tem o `.git` montado somente leitura (S1). Nenhum dos
dois chama uma API nem lê a chave. Os dois gravam o **mesmo tipo de arquivo**: o corpo da
requisição, que já traz o prompt inteiro dentro dele (decidido no analyze em 2026-10-16).

## 0. O arquivo do corpo (`*.request.json`)

- É o corpo da requisição em JSON, indentado com 2 espaços, em UTF-8, com os caracteres não ASCII
  escritos como são (`json.dumps(body, indent=2, ensure_ascii=False)` seguido de `\n`). Assim
  `≤` aparece como `≤` e o prompt pode ser lido e procurado no editor.
- É o **mesmo JSON** enviado: `json.loads(arquivo) == json.loads(wire_bytes(body))`, campo a
  campo. Só a formatação difere dos bytes da rede, onde não há indentação e `≤` vai como `\u2264`.
- Onde fica o prompt:
  - `gpt`: em `input`;
  - `gemini`: em `contents[0].parts[0].text`;
  - `slm`: em `messages[0].content`, com a seed e a temperatura em `options`.
- Nunca contém a chave da API, que vai num cabeçalho, e nunca contém a resposta do modelo.

## 1. `python -m ai_clients show-request`

```text
docker compose run --rm app python -m ai_clients show-request \
    --model {slm,gpt,gemini} --problem ID --scenario {black_box,white_box,hybrid} \
    --output ARQUIVO [--force] [--attempt N | --barred N] [--suites-dir DIR]
```

| Opção | Efeito |
|---|---|
| `--model` | obrigatória: `slm`, `gpt` ou `gemini` |
| `--problem`, `--scenario` | obrigatórias: uma combinação só |
| `--output ARQUIVO` | **obrigatória**: onde gravar o corpo (§0). Recusa um arquivo existente e qualquer caminho dentro de `data/suites/`, `data/dataset/` ou `manifests/` |
| `--force` | sobrescreve o `ARQUIVO` |
| `--attempt N` | a tentativa N; sem ela, a última tentativa atual da combinação. Sem nenhuma tentativa, a **prévia** do próximo pedido |
| `--barred N` | só `gpt`/`gemini`: a resposta barrada N (`barred/<id>/<cenário>/<N>.json`); exclusiva com `--attempt` |
| `--suites-dir DIR` | lê a árvore `DIR`, uma execução arquivada do mesmo modelo (por exemplo, `data/suites/gemini-piloto1`); padrão `data/suites/<modelo>` |

**Ordem**:
1. Uso, inclusive o destino.
2. Dataset contra o manifesto (FR-008).
3. `run.json` e a combinação (dano).
4. Texto-base pelo hash: o arquivo atual, senão o Git (R2).
5. Montagem do prompt.
6. Hash do prompt contra o gravado.
7. Corpo (R1).
8. Fidelidade ao dataset e expoente.
9. Gravação.

**No terminal**: o pedido **nunca** aparece. Só uma linha com o que foi gravado e o resultado das
conferências, e mais linhas só para avisos. Exemplo de formato, com valores ilustrativos:

```text
written: data/requests/1_B.txt — gemini 1_B black_box attempt 1 (of 1); prompt sha256 matches; dataset: faithful
warning: lost exponent in enunciado.md: "1 ≤ n ≤ 105", "larger than 106"
```

Variantes:
- `preview, not sent (next: attempt N)` no lugar de `attempt N (of M); prompt sha256 matches`;
- `barred response N (no reasoning tokens)`;
- `dataset: UNFAITHFUL — statement (enunciado.md) matched 1203 of 1890 chars`, uma por trecho;
- `warning: OLD TEMPLATE VERSION from git <commit> (current is <sha>)`;
- `warning: parameters changed since this attempt: generationConfig.responseFormat` (só nos
  comerciais).

**Recusas** (stderr; **nada é gravado**):

```text
error: the template of this attempt (sha256 <usado>) is not the current one (<atual>) and was not found in the Git history
error: the template of this attempt (sha256 <usado>) is not the current one (<atual>) and the Git history is not available here (run it in the app service)
error: the rebuilt prompt has sha256 <x>, but the attempt recorded <y>; it is not written as what was sent
error: 1_B black_box has no attempt 4 (attempts: 1–3)
error: data/requests/1_B.txt already exists; use --force to overwrite it
```

**Códigos**:

| Código | Quando |
|---|---|
| 0 | gravado, hash conferido (com o arquivo atual ou com uma versão antiga do Git) ou prévia, e prompt fiel ao dataset |
| 1 | dataset diverge; combinação ou `run.json` danificado; texto-base não achado; hash diferente (nada gravado); prompt infiel ao dataset (gravado, porque foi o enviado, com a linha `UNFAITHFUL`) |
| 2 | uso incorreto (R7) |

## 2. `generate --dry-run --save-requests DIR [--force]`

```text
docker compose run --rm app python -m ai_clients generate --model {slm,gpt,gemini} --dry-run \
    --save-requests data/requests [--force] [--problem ID ...] [--scenario S] [--limit N]
```

| Opção | Efeito |
|---|---|
| `--save-requests DIR` | só com `--dry-run`; grava o corpo (§0) de cada combinação **pendente** selecionada em `DIR/<modelo>/<id>.<cenário>.request.json`, numa pasta plana, mais `DIR/<modelo>/summary.json` (data-model §5) |
| `--force` | com `--save-requests`: apaga `DIR/<modelo>/` antes de gravar; sem ela, uma pasta `DIR/<modelo>/` com qualquer arquivo é recusada |

Sem `--save-requests`, o dry-run é exatamente o de hoje: não grava nada.

**Recusas de uso** (código 2):
- `--save-requests` sem `--dry-run`;
- `--force` sem `--save-requests` no `generate`;
- `DIR` dentro de `data/suites/`, `data/dataset/` ou `manifests/`, ou contendo uma delas;
- `DIR/<modelo>/` com arquivos e sem `--force`.

**Saída**: a do dry-run de hoje (a estimativa nos comerciais; a lista e a estimativa de chamadas no
SLM), seguida de:

```text
requests: 600 saved in data/requests/gemini; faithful 600/600; exponent warnings 71 problems (142 combinations)
exponent: 134_A: "1 ≤ n ≤ 105"
…
```

Com divergência, uma linha por combinação, antes do total:
`unfaithful: <id> <cenário>: statement (enunciado.md) matched 1203 of 1890 chars`.

**Códigos**:
- 0: tudo gravado e fiel; os avisos de expoente não mudam o código;
- 1: alguma combinação infiel ou danificada (a gravação vai até o fim);
- 2: uso.

## 3. O que muda no contrato da 004

O `specs/004-llm-test-generation/contracts/cli.md` dizia que o `--dry-run` "não grava nada". Agora,
o `--dry-run` não grava nada **fora da pasta pedida em `--save-requests`**. O texto foi atualizado
lá neste ciclo. A estimativa, a ausência de chamadas e a dispensa de chave não mudam.
