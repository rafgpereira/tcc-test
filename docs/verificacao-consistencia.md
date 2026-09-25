# Verificação de consistência entre artefatos

> **Fonte única** do que o comando `scripts/check_consistency.py` confere, de como ler o seu
> resultado e de como um módulo novo o estende (Constitution, Princípios II e XI). Cada módulo que
> passa a produzir uma pasta por problema **MUST** acrescentá-la a este comando no mesmo ciclo de
> trabalho em que o módulo é implementado, e atualizar este documento.

## Para que serve

Cada módulo já tem a sua própria verificação de integridade (`dataset verify`, `mutation verify`),
que compara **um artefato com o seu manifesto**. O que faltava era olhar o conjunto: se o dataset
descompactado tem mesmo os 200 problemas e todos os arquivos de cada um, se os mutantes têm um
representante para cada problema (100 por problema), e se **nada sobra nem falta** em nenhum dos
lados. É difícil confiar nisso a olho, e é o que precisa estar certo antes da execução que extrai
os dados finais do experimento.

Ele **não lê o conteúdo** dos códigos. Confere nomes de pastas e de arquivos, contagens e a
correspondência entre as camadas; com `--deep`, também recalcula os SHA-256 e os compara com os
manifestos.

## Como rodar

```bash
docker compose run --rm app python scripts/check_consistency.py          # estrutura e nomes (menos de 1 s)
docker compose run --rm app python scripts/check_consistency.py --deep   # e também os hashes de todos os arquivos
docker compose run --rm app python scripts/check_consistency.py --only dataset   # só uma camada
```

Roda no serviço `app`, **só lê** (não escreve nada, não compila, não executa código de terceiros,
não usa rede) e usa só a biblioteca padrão do Python. Código de saída: `0` sem nenhuma falha (avisos
são permitidos), `1` com pelo menos uma falha, `2` para uso incorreto ou manifesto obrigatório
ausente.

## O que ele confere

Cada linha do resultado começa com `[OK]`, `[FALHA]`, `[AVISO]` ou `[INFO]` e traz a contagem
(`200/200`); quando algo falha, lista os identificadores dos problemas (até 10, e "... e mais N").

| Camada | Pasta | Conferências |
|---|---|---|
| **Dataset** | `data/dataset/problems/` (a pasta descompactada) | o número de pastas de problema é o `problem_count` do manifesto; nenhuma entrada que não seja pasta de problema (nome `<contest>_<índice>`); cada problema tem `AC_ref.cpp`, `enunciado.md`, `metadata.json`, `testes.json`, `validacao.json` e `WA_1.cpp` a `WA_100.cpp` (exatamente 100, sem buracos), **e nenhum outro arquivo**; os nomes de arquivo no disco são exatamente os que o manifesto lista (faltando e sobrando) |
| **Mutantes** | `data/mutants/problems/` | cada problema tem `Mutant_1.cpp` a `Mutant_100.cpp` (exatamente 100) e nenhum outro arquivo além do `generation.json`; nenhum problema pela metade em `data/mutants/building/`; se `manifests/mutants.manifest.json` existir, os nomes batem com ele; um problema **excluído** por não alcançar 100 mutantes (previsto pela especificação) aparece como `[AVISO]`, não como falha |
| **Relação 1:1** | as duas acima | todo problema do dataset tem pasta de mutantes; **nenhuma pasta de mutantes sem problema no dataset** (é a verificação "de volta", dos mutantes para o dataset) |
| `--deep` | as duas acima e os zips | o SHA-256 e o tamanho de todos os arquivos batem com o manifesto (o mesmo que `dataset verify --extracted` e `mutation verify --extracted`), e o zip bate com o hash que o manifesto guarda; zip ausente é só aviso |

Não confere (de propósito): o conteúdo dos códigos; se os mutantes foram gerados a partir do
`AC_ref.cpp` que está no dataset (só os identificadores e as contagens); o formato interno dos
JSON.

## Quando rodar

1. Depois de descompactar o dataset (`unzip data/dataset.zip -d data/`): `--only dataset`.
2. Depois de gerar os mutantes, e de novo depois de `package`: sem `--only`, com `--deep`.
3. **Antes de qualquer etapa que consuma os dados** (o envio às IAs e a execução final do
   experimento): `--deep` com código de saída `0` é a condição para prosseguir. Quando o módulo
   orquestrador (`src/cli/`) for especificado, ele deve chamar esta verificação como portão
   (`run_checks(root, only, deep)` devolve um `Report` com `ok`, `failures` e `warnings`; a decisão
   de mover o código para `src/` fica para essa feature).

## Decisões (2026-09-25)

- **Só nomes e contagens por padrão**, hashes só com `--deep`: a verificação rápida pode rodar a
  toda hora e dar um resumo legível; a profunda é a que garante os bytes.
- **A contagem esperada de problemas vem do manifesto do dataset**, não de uma constante: o número
  200 é uma decisão do dataset, registrada no manifesto; o comando mostra os dois lado a lado.
- **A camada de referência é a primeira** (`dataset`); toda camada seguinte tem de ser 1:1 com ela,
  sem sobrar nem faltar pasta.
- **Excluído é aviso, não falha**: FR-009 do módulo de mutantes prevê excluir um problema que não
  chega a 100 mutantes; mas ele fica visível no resultado.
- **Manifesto de mutantes ausente é aviso**: ele só existe depois de `mutation package`.
- **Só lê**: nada é corrigido automaticamente; quem decide o que fazer é o autor.

## Como um módulo novo o estende

Acrescente uma `Layer` em `LAYERS` (`scripts/check_consistency.py`), com a pasta onde ficam as
pastas de problema, os grupos de nomes de arquivo que cada problema deve ter (`Group`), os nomes
permitidos além deles, o manifesto (se houver) e o prefixo dos caminhos dentro dele. A relação 1:1
com o dataset passa a ser conferida sem nenhuma outra mudança. Exemplo previsto: os testes gerados
pelas IAs, uma pasta por problema (e por modelo e cenário, quando esse desenho for decidido).
Acrescente também os testes em `tests/consistency/` e uma linha na tabela acima.
