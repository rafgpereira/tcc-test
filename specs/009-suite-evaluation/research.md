# Research: Avaliação das suítes (009)

Decisões técnicas da Fase 0. Nenhum `NEEDS CLARIFICATION` ficou no Technical Context; cada item
abaixo registra o que foi escolhido, por quê e o que foi descartado.

## R1. Unidade de trabalho: o problema, com todas as suítes dele

- **Decision**: uma tarefa = um problema. Ela compila uma vez o `AC_ref`, os 100 WAs e os 100
  mutantes e executa contra eles todas as suítes pedidas do problema (até 15: 4 modelos × 3
  cenários + 3 da 1ª tentativa do modelo local).
- **Rationale**: compilar é o passo mais caro e não depende da suíte. Por problema são 201
  compilações; por modelo seriam 5 × 201. Com 200 problemas, isso evita cerca de 160 mil
  compilações.
- **Alternatives considered**: tarefa por modelo × problema (simples de filtrar, 5× mais
  compilação); cache de binários em disco entre execuções (estado implícito e risco de binário
  velho; rejeitado pelo Princípio II). `--set` continua existindo para avaliar só um conjunto,
  pagando a compilação de novo.

## R2. Julgamento por teste fora de `sandbox.judge.run_suite`

- **Decision**: `evaluation/judging.py` chama `run_binary` e `judge_test` teste a teste. O
  `run_suite` do motor (curto-circuito no primeiro não-AC) fica intocado.
- **Rationale**: o AC precisa de todos os testes (FR-004) e os alvos precisam decidir dois
  oráculos numa mesma execução (R3). Mudar o motor afetaria o dataset e os mutantes, já validados.
- **Alternatives considered**: um parâmetro `short_circuit=False` em `run_suite` (mexe num módulo
  validado sem ganho).

## R3. Passada única para os dois oráculos

- **Decision**: para cada alvo, cada teste é executado **uma vez**. A saída é comparada com a
  saída declarada (oráculo declarado) e, se o teste é válido no oráculo corrigido, com a saída real
  do AC (oráculo corrigido). TLE, MLE e RE independem da saída esperada e valem para os dois. A
  passada para quando os dois oráculos já detectaram o alvo ou quando os testes acabam.
- **Rationale**: o resultado é idêntico ao de duas passadas com curto-circuito independente (o
  primeiro teste que falha em cada oráculo é o mesmo), executando no máximo o mesmo número de
  testes da passada mais longa.
- **Alternatives considered**: duas passadas separadas (até 2× o tempo, mesmo resultado).

## R4. Binários no tmpfs do slot

- **Decision**: os 201 binários de um problema ficam no diretório do *slot*
  (`/sandbox/slot<N>/<problema>/`) e são apagados ao fim da tarefa. O número de trabalhadores
  padrão é limitado para caber nos 2 GB do `tmpfs` de `/sandbox`; o piloto mede o tamanho real
  por problema, e o README diz como ajustar `--workers`.
- **Rationale**: compilar uma vez exige guardar os binários durante a tarefa; o `tmpfs` é
  compartilhado entre os *slots*.
- **Alternatives considered**: compilar e executar um alvo de cada vez contra as 15 suítes (mesma
  economia de compilação e só 1 binário vivo por vez). **Adotado como forma de execução**: o laço é
  alvo → suítes, então só o binário do alvo corrente precisa existir; o AC é o único mantido
  durante toda a tarefa. Isso torna o limite de `tmpfs` irrelevante para o número de
  trabalhadores.

## R5. Persistência, trava e retomada

- **Decision**: padrão de `src/mutation/persistence.py`. O processo principal grava cada conjunto
  × problema em `data/evaluation/<conjunto>/building/<id>/` (os 3 arquivos de cenário) e fecha com
  um único `rename` para `problems/<id>/`. Uma trava exclusiva por `data/evaluation/` impede duas
  execuções. Na retomada, o que está em `building/` é apagado e refeito; o que está em `problems/`
  é pulado.
- **Rationale**: FR-015 (sem duplicar nem corromper), mesma garantia já testada nos mutantes.
- **Alternatives considered**: trava por combinação com vários comandos em paralelo, como no
  modelo local (desnecessário: um único comando com *pool* já paraleliza; FR-016 é cumprido pelo
  *pool*).

## R6. Formato: JSON por cenário + CSV consolidado

- **Decision**: um JSON por cenário (`<cenário>.json`) com a proveniência, o AC por teste e a
  lista dos 200 alvos. O `report` gera `data/evaluation/<conjunto>/results.csv` (uma linha por
  combinação × alvo) e o relatório JSON.
- **Rationale**: o JSON tem esquema validável e guarda as saídas do AC (texto com quebras de
  linha). O CSV é o formato que a seção 4 da metodologia previa e o mais simples para a feature
  010 agrupar. Ele é derivado do JSON, então não pode divergir.
- **Alternatives considered**: só CSV (as saídas do AC ficariam ilegíveis numa célula); só JSON
  (a 010 teria de juntar 3.000 arquivos).

## R7. Pacotes e nomes

- **Decision**: um pacote por conjunto: `data/evaluation_<conjunto>.zip`,
  `manifests/evaluation_<conjunto>.manifest.json`, `manifests/evaluation_<conjunto>_report.json`,
  com `<conjunto>` ∈ {`slm`, `gpt`, `gemini`, `claude`, `slm-attempt1`}. Cada pacote inclui
  `run.json` e `results.csv`.
- **Rationale**: um pacote por modelo, como as suítes; a avaliação de um não espera a dos outros.
- **Alternatives considered**: um único pacote (refazer um modelo exigiria reempacotar tudo).

## R8. `run.json` e congelamento das entradas

- **Decision**: o primeiro `run` de um conjunto grava `run.json` com: conjunto, tentativa (só
  `slm-attempt1`), SHA-256 do manifesto do dataset e a revisão, do manifesto dos mutantes e do
  manifesto de suítes do modelo, versão do GCC, número de repetições (3) e versão do esquema. Toda
  retomada confere; diferença = recusa com mensagem.
- **Rationale**: Princípio II; impede juntar no mesmo resultado avaliações com entradas
  diferentes (o mesmo papel do `run.json` do modelo local).
- **Alternatives considered**: guardar só na combinação (não impede a mistura).

## R9. Repetição de erro de execução

- **Decision**: `config.ERROR_RUNS = 3`. Um teste com veredito TLE, MLE ou RE é executado mais 2
  vezes, e o veredito final é o da primeira execução que não for erro (o teste fica `unstable`) ou
  o erro, se repetido nas 3. Vale para o AC (FR-005a) e para os alvos (FR-006a). As 3 execuções
  (veredito, tempo, memória) ficam gravadas só quando houve repetição.
- **Rationale**: decisões do clarify; manter a gravação só na repetição evita multiplicar o
  tamanho do resultado.
- **Alternatives considered**: repetir só TLE (rejeitado no clarify).

## R10. Testes (Princípio VI)

- **Decision**: unidade com motor falso (sequência programada de `RunResult`), cobrindo: AC
  passa tudo; AC com saída diferente no meio e TLE depois (sem curto-circuito); alvo detectado no
  teste k (não roda k+1); dois oráculos que divergem; teste excluído do oráculo corrigido; AC com
  erro em todos os testes; repetição que confirma e que desfaz o erro; "sem suíte"; 1ª tentativa a
  partir de arquivos de tentativa; retomada com `building/` sobrando; `run.json` diferente recusado.
  Integração (serviço `sandbox`, C++ real) num problema sintético pequeno com AC, um WA e um
  mutante conhecidos.
- **Rationale**: casos conhecidos e esperados, como a constitution pede.

## R11. Portões antes de executar

- **Decision**: `run` começa pelo `selfcheck` do motor e por `cli.consistency.run_checks(root,
  only=["dataset", "mutants", "<modelo>_suites"], deep=True)` para cada modelo pedido; qualquer
  falha = código de saída próprio e nada executado.
- **Rationale**: FR-002; mesmo portão das execuções anteriores.
