# Geração de Casos de Teste com Modelos de Linguagem — Pipeline Experimental

Software experimental de um Trabalho de Conclusão de Curso (Engenharia de Software, UnB, TCC
de dupla) que avalia a eficácia de modelos de linguagem na geração automática de casos de
teste unitários em C++.

> **Este é o documento de visão geral do projeto** (Constitution, Princípio XI). Ele explica a
> arquitetura do experimento, como os módulos se conectam e como reproduzir o experimento do
> zero. É atualizado sempre que um módulo é adicionado ou o fluxo entre módulos muda.
>
> **Estado atual (2026-09-19)**: nenhum módulo está implementado ainda. A feature
> `001-dataset-extraction` tem spec e plano prontos; o restante do experimento está descrito na
> metodologia, mas ainda não especificado. Por isso a seção "Como reproduzir" marca cada etapa
> com o seu estado. **A reprodução completa só será possível quando todas as etapas estiverem
> implementadas**; este documento será completado à medida que os módulos chegarem.

## O que o experimento responde

Três modelos (dois LLMs comerciais, **GPT-5.4-mini** e **Gemini 3.5 Flash**, e um SLM local,
**Qwen2.5-Coder-7B** via Ollama) geram testes unitários para problemas algorítmicos, sob três
cenários de contexto:

- **Caixa-preta**: só o enunciado.
- **Caixa-branca**: só o código da solução correta.
- **Híbrida**: enunciado e código.

Os testes gerados são executados, em ambiente isolado, contra códigos com falhas reais (submissões
incorretas humanas) e falhas artificiais (mutantes), e contra o código correto. Perguntas
centrais: qual estratégia de contexto detecta melhor falhas reais, qual é mais sensível a
defeitos sintéticos, qual gera mais falsos positivos (alucinações) e como combinar contexto
ajuda ou atrapalha. Detalhes: [`docs/metodologia-referencia.md`](docs/metodologia-referencia.md).

Escala: **200 problemas × 3 modelos × 3 cenários** (1.800 suítes de teste geradas).

## Arquitetura: como os módulos se conectam

```text
 code_contests (Hugging Face, streaming)
        │
        ▼
 ┌──────────────┐  dataset.zip: por problema, enunciado.md, AC_ref.cpp,
 │   dataset    │  WA_1..100.cpp, testes.json, metadata.json, validacao.json
 └──────┬───────┘
        │  usa o motor de execução para validar AC e WAs
        ▼                                   ┌──────────────────────────────┐
 ┌──────────────┐                           │  sandbox (motor de execução) │
 │   mutation   │  100 mutantes por problema│  compila e executa C++ sob   │
 └──────┬───────┘  a partir do AC_ref       │  limites de tempo, memória e │
        │                                   │  pilha e atribui o veredito  │
        ▼                                   └───────────────▲──────────────┘
 ┌──────────────┐  suítes de teste (JSON)                   │ reutilizado sem
 │  ai_clients  │  3 modelos × 3 cenários                   │ alteração
 └──────┬───────┘                                           │
        ▼                                                   │
 ┌──────────────┐  executa cada suíte contra AC, WAs e      │
 │  avaliação   │  mutantes, com curto-circuito ────────────┘
 └──────┬───────┘  → registro CSV de vereditos
        ▼
 ┌──────────────┐  TDF (falhas reais), MS (mutantes),
 │   metrics    │  TFP (falsos positivos), IIC (influência do contexto)
 └──────────────┘
        ▲
   cli: orquestrador que amarra tudo
```

O **motor de execução** (`src/sandbox/`) é um só: o mesmo que valida o dataset é reutilizado
na avaliação, para que nenhum código do dataset falhe no motor só durante o experimento.

## Módulos e estado

| Módulo | Papel | Metodologia | Estado | README do módulo |
|---|---|---|---|---|
| `src/dataset/` | extrai, filtra, valida e empacota o dataset | seção 1 | spec e plano prontos ([`specs/001-dataset-extraction/`](specs/001-dataset-extraction/)); **sem código** | a criar na feature 001 |
| `src/sandbox/` | motor de execução isolada de C++ | seções 1.4 e 4 | idem (construído na feature 001) | a criar na feature 001 |
| `src/mutation/` | gera 100 mutantes por problema | seção 2 | **sem spec** | a criar |
| `src/ai_clients/` | chamadas stateless aos 3 modelos | seção 3 | **sem spec** (pontos pendentes na metodologia, em especial o oráculo do SLM) | a criar |
| avaliação | injeta as suítes geradas e registra vereditos em CSV | seção 4 | **sem spec** | a criar |
| `src/metrics/` | TDF, MS, TFP, IIC | seção 5 | **sem spec** (IIC ainda não operacionalizado) | a criar |
| `src/cli/` | orquestrador do experimento | — | **sem spec** | a criar |

O formato dos READMEs de módulo é o de [`docs/template-modulo.md`](docs/template-modulo.md).

## Como reproduzir o experimento

Ambiente: **tudo roda containerizado (Docker)**. Nenhum código C++ de terceiros é compilado ou
executado no host. Requisitos: Docker com Compose v2 e Git; acesso à internet apenas para
construir a imagem e para a extração do dataset.

| Etapa | O que fazer | Estado |
|---|---|---|
| 0. Obter o projeto | `git clone <url do repositório>` e `cd tcc-testgen-pipeline` | disponível |
| 1. Construir o ambiente | `docker compose build` (imagem `gcc:13.2.0` + Python 3.11 via `uv`) | planejado (feature 001) |
| 2. Obter o dataset | **sem rodar a extração**: `unzip data/dataset.zip -d data/` e depois `docker compose run --rm app python scripts/verify_dataset.py --extracted data/dataset` | planejado (o zip só existe depois da feature 001) |
| 2b. Ou regerar o dataset do zero | `extract`, `validate`, `audit`, `package` do módulo `dataset`; comandos e opções em [`specs/001-dataset-extraction/contracts/cli.md`](specs/001-dataset-extraction/contracts/cli.md); roteiro de aceite em [`quickstart.md`](specs/001-dataset-extraction/quickstart.md) | planejado (feature 001) |
| 3. Gerar mutantes | — | não especificado |
| 4. Gerar suítes com os modelos | — | não especificado (exige chaves de API em `.env`; ver `.env.example`, ainda a criar) |
| 5. Avaliar as suítes | — | não especificado |
| 6. Calcular as métricas | — | não especificado |
| 7. Executar tudo com um comando | — | não especificado (`src/cli/`) |

Cada linha "não especificado" ou "planejado" MUST virar comandos exatos, testados, quando o
módulo correspondente for concluído; uma feature só é concluída com isso feito
(Constitution, Princípio XI).

### Reprodutibilidade

- Dependências fixadas em lockfile (`uv.lock`); imagem base fixada por digest; revisão do
  dataset de origem fixada; seed fixa (`42`).
- O dataset é distribuído como `data/dataset.zip` versionado, com o manifesto
  `manifests/dataset.manifest.json` (SHA-256 por arquivo) para verificar a identidade exata dos
  dados. Arquivos soltos do dataset e mutantes nunca são versionados.
- Chamadas a modelos comerciais custam dinheiro: o pipeline nunca as dispara em lote sem
  confirmação explícita de quem executa (Constitution, Princípio VIII).

## Glossário

| Sigla | Significado |
|---|---|
| **AC** | código correto (Accepted); `AC_ref` é a solução de referência de um problema |
| **WA** | falha lógica real: submissão humana incorreta que responde errado (Wrong Answer) |
| **TLE / MLE / RE / CE** | tempo excedido, memória excedida, falha de execução, erro de compilação |
| **Mutante** | cópia do AC com uma alteração sintática (defeito artificial) |
| **TDF** | Taxa de Detecção de Falhas reais: % de WAs reprovados pela suíte gerada |
| **MS** | Escore de Mutação: mutantes mortos sobre mutantes válidos |
| **TFP** | Taxa de Falsos Positivos: % de problemas em que a suíte reprova o AC |
| **IIC** | Índice de Influência do Contexto (sinergia ou sobrecarga ao combinar requisito e código) |
| **Macrocategoria** | `matematica`, `estrutural_otimizacao` ou `logica_direta` (por prioridade de tags) |
| **SLM** | modelo de linguagem pequeno, executado localmente (Qwen2.5-Coder-7B) |

## Mapa da documentação

| Documento | Para que serve |
|---|---|
| [`.specify/memory/constitution.md`](.specify/memory/constitution.md) | princípios do projeto (reprodutibilidade, isolamento, testes, documentação viva...) |
| [`docs/metodologia-referencia.md`](docs/metodologia-referencia.md) | desenho experimental **corrente**; base para atualizar o texto do TCC; tem histórico de atualizações datado |
| [`docs/template-modulo.md`](docs/template-modulo.md) | formato padronizado do README de cada módulo |
| `src/<modulo>/README.md` | como usar cada módulo (propósito, execução, entradas, saídas, dependências, limitações) |
| [`specs/NNN-nome/`](specs/) | especificação, plano, contratos e roteiro de aceite de cada feature (spec-kit) |
| [`CLAUDE.md`](CLAUDE.md) | contexto rápido para sessões do Claude Code neste repositório |

## Regras de trabalho

Ciclo de cada módulo (spec-kit): `specify → clarify → plan → tasks → implement → converge`.
Toda informação nova (dado medido, divergência, decisão) MUST ser propagada, no mesmo ciclo de
trabalho, para os artefatos da feature **e** para a metodologia; todo código gerado com apoio de
IA é revisado por um dos autores antes de ir para a branch principal. Detalhes na constitution.
