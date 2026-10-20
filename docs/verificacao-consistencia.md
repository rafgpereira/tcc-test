# Verificação de consistência entre artefatos

> **Fonte única** do que o comando `python -m cli check` confere, de como ler o seu
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
docker compose run --rm app python -m cli check          # estrutura e nomes (menos de 1 s)
docker compose run --rm app python -m cli check --deep   # e também os hashes de todos os arquivos
docker compose run --rm app python -m cli check --only dataset   # só uma camada
```

Roda no serviço `app` (pacote `src/cli/`, README em `src/cli/README.md`), **só lê** (não escreve nada, não compila, não executa código de terceiros,
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
| **Suítes do modelo local** (`slm_suites`) | `data/suites/slm/problems/` | cada problema tem as pastas `black_box`, `white_box` e `hybrid` e nada além delas; em cada uma, só `suite.json`, `manual_close.json` (o fechamento à mão pelos autores) e arquivos `attempt_<n>.generation.json`/`attempt_<n>.execution.json`, com as gerações numeradas de 1 em diante sem buraco, nenhuma execução sem a geração correspondente, no máximo 15 tentativas e nenhuma execução depois da 12ª (as tentativas 13 a 15 são de predição e não executam nada); cada cenário tem `suite.json`; se `manifests/slm_suites.manifest.json` existir, os nomes de **todos** os arquivos de `data/suites/slm/` (inclusive `run.json`, fora `.lock`) batem com ele. **Enquanto o manifesto não existe** (execução ainda não empacotada), pasta de problema ou de cenário faltando e `suite.json` faltando são a execução em andamento: `[AVISO]`, mesmo com `--deep`, e a pasta inteira ausente também; buraco nas tentativas, mais de 15, execução de uma tentativa de predição, arquivo estranho e pasta sem problema no dataset são `[FALHA]` sempre. **Depois do `package`**, tudo o que falta é `[FALHA]` |
| **Suítes dos modelos comerciais** (`gpt_suites` e `gemini_suites`) | `data/suites/gpt/problems/` e `data/suites/gemini/problems/` | as mesmas regras da camada do modelo local, com os arquivos dos modelos comerciais: em cada cenário, só `suite.json`, `manual_close.json` e `attempt_<n>.json`, numerados de 1 em diante sem buraco, **no máximo 3**; cada cenário tem `suite.json`; as respostas guardadas à parte por não trazerem raciocínio (`barred/<problema>/<cenário>/<n>.json`) são contadas numa linha `[INFO]` (ficam fora das métricas) e só podem ser de problema e cenário existentes; as trocas de texto-base e o que elas moveram (`template_changes/` e `superseded/`) são conferidos como no modelo local; o manifesto de cada modelo (`manifests/gpt_suites.manifest.json`, `manifests/gemini_suites.manifest.json`) é conferido contra os arquivos de `data/suites/<modelo>/`. Mesma severidade: `[AVISO]` enquanto o manifesto não existe, `[FALHA]` depois do `package`; buraco, mais de 3 tentativas, arquivo estranho e resposta barrada de problema inexistente são `[FALHA]` sempre. Cada modelo é uma camada separada: o pacote de um não depende do outro |
| **Relação 1:1** | as acima | todo problema do dataset tem pasta de mutantes e de suítes; **nenhuma pasta de mutantes ou de suítes sem problema no dataset** (é a verificação "de volta", para o dataset) |
| `--deep` | as acima e os zips | o SHA-256 e o tamanho de todos os arquivos batem com o manifesto (o mesmo que `dataset verify --extracted` e `mutation verify --extracted`), e o zip bate com o hash que o manifesto guarda; zip ausente é só aviso |

Não confere (de propósito): o conteúdo dos códigos; se os mutantes foram gerados a partir do
`AC_ref.cpp` que está no dataset (só os identificadores e as contagens); o formato interno dos
JSON.

## Quando rodar

1. Depois de descompactar o dataset (`unzip data/dataset.zip -d data/`): `--only dataset`.
2. Depois de gerar os mutantes, e de novo depois de `package`: sem `--only`, com `--deep`.
3. **Antes de qualquer etapa que consuma os dados** (o envio às IAs e a execução final do
   experimento): `--deep` com código de saída `0` é a condição para prosseguir. Quando o módulo
   orquestrador (`src/cli/`) for especificado, ele deve chamar esta verificação como portão
   (`cli.consistency.run_checks(root, only, deep)` devolve um `Report` com `ok`, `failures` e
   `warnings`; o código já está em `src/cli/`, importável).

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

## Decisões (2026-10-01): camada `slm_suites`

- **Duas profundidades**: a camada confere pasta de problema → pasta de cenário → arquivos de
  tentativa (só os nomes, nunca o conteúdo; quem confere o conteúdo é o próprio `ai_clients`, que
  aponta combinação danificada). O manifesto lista os arquivos a partir de `suites/slm/`, como
  dentro do zip, e por isso também `run.json`.
- **Execução em andamento é aviso até o `package`**: o piloto e a execução completa começam,
  ambos, por `cli check --deep` com saída `0`, e nesse momento a árvore do modelo local ainda não
  existe (antes do piloto) ou está pela metade (o piloto, que a execução completa continua com
  `--resume`). Exigir `suite.json` em todo cenário com `--deep`, como dizia o contrato da camada,
  tornaria esse primeiro passo impossível. O que falta só vira falha quando o manifesto existe,
  isto é, quando a execução foi declarada completa e empacotada (o `package` já recusa empacotar
  uma execução incompleta). Estruturas impossíveis (buraco, mais de 15 tentativas, arquivo
  estranho, pasta sem problema) são falha desde o início.
- **Só lê**: nada é corrigido automaticamente; quem decide o que fazer é o autor.
- **Comando com nome limpo, em `src/cli/`** (`python -m cli check`, 2026-09-25): comandos do projeto
  são sempre `python -m <pacote> <subcomando>`, nunca o caminho de um script; a conferência que
  cruza módulos mora no pacote `cli`, que será também o do orquestrador.

## Decisões (2026-10-15): camadas `gpt_suites` e `gemini_suites`

- **Uma camada por modelo comercial**, como os pacotes (um por modelo): a execução e o pacote de
  um modelo não esperam pelos do outro.
- **Respostas barradas fora das tentativas**: uma resposta que diga não ter raciocinado é guardada
  em `barred/`, conta no custo e no relatório, mas não é tentativa nem suíte; a camada só confere
  que ela é de um problema e cenário existentes.
- **Mesma regra de andamento do modelo local**: o que falta é aviso até o `package` (o piloto e a
  execução completa começam por `cli check --deep` com saída `0`).

## Decisões (2026-10-18): revisão 2 do dataset

- **Camada `dataset` com manifesto de revisão**: o manifesto da revisão 2 (`schema_version` 2, com
  `revision` e `revision_of`) é conferido como o da revisão 1; a revisão guardada
  (`data/dataset.rev1.zip`) não entra no `check`, só no `dataset verify` de auditoria.
- **Camada `slm_suites` com junção de execuções**: quando existe `data/suites/slm/provenance.json`
  (gravado pelo `package --merge-from`), a camada lê dele, para cada problema × cenário, a pasta que
  tem a suíte vigente (`data/suites/slm/` ou `data/suites/slm-rev1/`). Confere que cada combinação
  vigente aparece uma vez e tem `suite.json` na pasta indicada, que toda combinação de cada pasta
  está registrada no arquivo de origem, cada pasta com as mesmas regras de uma execução única e
  contra a parte do manifesto sob ela, e os três cenários vigentes por problema. A relação 1:1 com
  o dataset usa as combinações vigentes.

## Decisões (2026-10-20): `accepted_barred` dos modelos comerciais

- **Sem regra nova de estrutura**: depois de 3 respostas sem raciocínio, a combinação ganha um
  `suite.json` (`accepted_barred`) como qualquer outra, então o `check` continua exigindo um
  `suite.json` por cenário. As respostas de `barred/` são contadas à parte, e uma de problema que
  não está no dataset continua sendo falha.

## Decisões (2026-10-20): camada `claude_suites`

- **Terceiro modelo comercial**: o Claude Haiku 5.5 ganha a camada `claude_suites`, idêntica às
  camadas `gpt_suites` e `gemini_suites` (mesmas conferências, aviso enquanto a execução não
  foi empacotada, relação 1:1 com o dataset); `--only claude_suites` confere só ela.

## Como um módulo novo o estende

Acrescente uma `Layer` em `LAYERS` (`src/cli/consistency.py`), com a pasta onde ficam as
pastas de problema, os grupos de nomes de arquivo que cada problema deve ter (`Group`), os nomes
permitidos além deles, o manifesto (se houver) e o prefixo dos caminhos dentro dele. A relação 1:1
com o dataset passa a ser conferida sem nenhuma outra mudança. Exemplo previsto: os testes gerados
pelas IAs, uma pasta por problema (e por modelo e cenário, quando esse desenho for decidido).
Acrescente também os testes em `tests/cli/` e uma linha na tabela acima.
