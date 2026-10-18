# Contrato da CLI: `check-statements` e `correct-statements`

**Feature**: `specs/006-statement-fidelity` | **Date**: 2026-10-18 | **Plan**: [../plan.md](../plan.md)

## 1. `python -m dataset check-statements`

```text
docker compose run --rm app python -m dataset check-statements [--refetch] [--problem ID ...]
```

| Opção | Efeito |
|---|---|
| (nenhuma) | Baixa só as páginas que ainda não têm cópia, uma por vez, a cada 3 s ou mais (E2). Depois compara os 200 e grava o relatório. Sem página faltando, não acessa a rede. |
| `--refetch` | Baixa de novo as páginas pedidas (com `--problem`) ou todas, mesmo com cópia. |
| `--problem ID` | Restringe o download e a comparação a esses problemas; o resultado é **só impresso**, e o relatório versionado **não** é gravado (ele vem só da execução sem `--problem`, que cobre os 200). |

**Ordem**:
1. Uso.
2. Dataset contra o manifesto.
3. Hash das cópias contra `statement_originals.manifest.json` (recusa com `1` se divergir). Com as
   páginas inteiras em `data/statements/originals/`, confere o `page_sha256` e o
   `statement_sha256`. Com só o pacote (quem clonou), confere o `statement_sha256` de cada bloco,
   e o `page_sha256` fica só como registro.
4. Download do que falta: problemas sem entrada no manifesto, ou com erro temporário (HTTP 429 ou
   5xx). Um erro definitivo (`http_404`, `no_statement_block`) só é tentado de novo com
   `--refetch`.
5. Extração, comparação e relatório (gravado só sem `--problem`).
6. Pacote `data/statement_originals.zip` refeito se alguma cópia mudou. O pacote é
   **determinístico**: arquivos em ordem alfabética e data fixa em cada entrada, então os mesmos
   blocos dão os mesmos bytes.

**Saída**:

```text
fetch: 161_A ok (66730 bytes)          # uma linha por página obtida; nenhuma se tudo já existe
...
statements: 200 checked; faithful 125, with losses 75, unchecked 0
lost_exponent: 150 in 72 problems; lost_index: 900 in 80 problems; formula: 0; image: 3 in 3 problems; table: 0; other: 2 in 2 problems
report: manifests/statement_fidelity_report.json
```

Os números acima são **ilustrativos**; os reais saem da primeira execução e vão para a metodologia.

**Códigos**:
- `0`: relatório gravado, mesmo com perdas;
- `1`: uma cópia diverge do manifesto, ou o dataset diverge do manifesto dele;
- `2`: uso;
- `3`: o site recusou ou ficou fora do ar depois das esperas (o já obtido fica guardado, e rodar de
  novo continua);
- `130`: interrompido.

## 2. `python -m dataset correct-statements`

```text
docker compose run --rm app python -m dataset correct-statements --output-dir data/statements/corrected [--force]
```

| Opção | Efeito |
|---|---|
| `--output-dir DIR` | Obrigatória. Grava `DIR/<id>.md` (só os corrigidos aceitos) e `DIR/summary.json`, numa pasta plana. Nunca dentro de `data/dataset/`, `data/suites/` ou `manifests/`. |
| `--force` | Substitui `DIR` se já tiver arquivos. |

O comando lê o relatório de `check-statements`; sem ele, ou com um relatório de outro dataset,
sai com `1`. Nunca altera o dataset.

**Saída**:

```text
corrected: 70 (lost_exponent 148, lost_index 880, table 0); unchanged: 125; review: 5
review: 85_B: image
review: 203_D: other ("...")
written: data/statements/corrected (70 files + summary.json)
```

**Códigos**:
- `0`: gravado;
- `1`: sem relatório válido, ou uma das três conferências falhou em algum problema (ele vai para
  `review`, e o código sinaliza);
- `2`: uso, pasta com arquivos sem `--force` ou pasta proibida.
