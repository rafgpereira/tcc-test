# Módulo `sandbox` (motor de execução)

> **Status**: em implementação · **Feature**:
> `specs/001-dataset-extraction/` · **Metodologia**: `docs/metodologia-referencia.md`, seções 1.4 e 4

## (a) Propósito

Compila e executa código C++ de terceiros em isolamento, sob limites de tempo, memória e pilha lidos dos metadados de cada problema, e atribui um veredito (`AC`, `WA`, `TLE`, `MLE`, `RE` ou `CE`).

## (b) Como executar

**Este módulo ainda não tem comando próprio.** O motor é uma biblioteca Python (`src/sandbox/`) que o
módulo [`dataset`](../dataset/README.md) chamará para validar os códigos (subcomandos `selfcheck` e
`validate`, ainda por implementar); mais tarde, a etapa de avaliação a reutiliza sem alteração. Você
não precisa "rodar o sandbox" à mão: quando o `selfcheck` existir, este README passará a trazer o
passo a passo dele, no mesmo formato do README do `dataset`.

O que já existe e pode ser conferido hoje são os tipos e as funções de limites (por exemplo, a
conversão do limite de pilha de 256 MiB para o valor que o sistema espera). Para rodar os testes
deles, faça antes os passos 1 a 5 do
[guia de execução do README da raiz](../../README.md#guia-de-execução-do-clone-ao-primeiro-comando)
(baixar o projeto, criar o `.env`, criar `data/`, construir a imagem) e use o serviço `sandbox`, o
que **não tem internet** de propósito e é o único autorizado a compilar e executar C++ de terceiros:

```bash
docker compose run --rm sandbox pytest tests/sandbox
```

Esperado: a última linha diz `passed` e não menciona `failed`.

## (c) Entradas esperadas

Nenhuma até o motor ser implementado. O desenho prevê: o código-fonte C++, os testes (entrada e saída
esperada) e os limites de execução (`ExecutionLimits`), conforme
[engine-api.md](../../specs/001-dataset-extraction/contracts/engine-api.md).

## (d) Saídas produzidas

Nenhuma até o motor ser implementado. O desenho prevê os resultados de compilação e de execução e o
veredito de cada suíte (`Verdict`), conforme o mesmo contrato.

## (e) Dependências e pré-requisitos

- GCC 13.2.0 e Python 3.11.16, ambos dentro da imagem única do projeto (`docker compose build`).
- Serviço `sandbox` do Docker Compose: sem rede, sistema de arquivos raiz somente leitura e uma área
  temporária (`/sandbox`) onde se pode executar o que foi compilado.
- Nenhum módulo anterior precisa ter rodado; nenhuma variável de ambiente é usada.

## (f) Limitações conhecidas

- O motor propriamente dito (compilação, execução com limites, veredito) ainda não existe; hoje só há
  tipos e funções de limites, com testes.
- Os limites de tempo e de memória nunca são fixados no código: virão dos metadados de cada problema
  (Constitution, Princípio V). O limite de pilha é de 256 MiB e é aplicado em tempo de execução, não
  na compilação (metodologia, seção 1.4).

## Referências

- Contratos: [engine-api.md](../../specs/001-dataset-extraction/contracts/engine-api.md)
- Testes: `tests/sandbox/` (`docker compose run --rm sandbox pytest tests/sandbox`)

## Comandos verificados

| Comando | Verificado em | Revisão | Tarefa |
|---|---|---|---|
| `pytest tests/sandbox` | pendente | — | — |
