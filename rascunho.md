Especificar o módulo de extração, filtragem, validação e persistência do
dataset experimental, conforme docs/metodologia-referencia.md, seção 1.

Requisitos funcionais:
- Extrair problemas do dataset code_contests via streaming (Hugging Face),
  sem download completo do repositório.
- Aplicar critérios de elegibilidade: origem Codeforces, rating entre 1000
  e 1600, presença de tag determinística permitida, ausência de tag
  proibida, ausência de dependência visual no enunciado, submissões em C++.
- Classificar cada problema elegível em uma macrocategoria algorítmica
  (lógica direta, matemática, otimização estrutural), usando o mapeamento:
    1º Estrutural/Otimização (dp, binary search, sortings)
    2º Matemática (math)
    3º Lógica Direta (implementation, strings, greedy).
    Seguindo os critérios de desempate definidos conforme docs/metodologia-referencia.md, seção 1.
- Validar localmente as submissões incorretas do problema: compilar via
  GCC com fallback de padrão (gnu++20→17→14→11), executar em sandbox com
  limites de tempo/memória do próprio problema, reter apenas falhas WA
  reais (descartar TLE/MLE/RE), até acumular 100 WAs validados por
  problema.
- Persistir localmente por problema: enunciado.md, AC_ref.cpp,
  WA_1..100.cpp, testes.json, e os metadados, conforme docs/metodologia-referencia.md, seção 1..
- Meta: 200 problemas elegíveis completos.
- Ao final, compactar o dataset validado em data/dataset.zip e gerar um
  manifesto de integridade (hash SHA-256 por arquivo).

Este módulo NÃO inclui geração de mutantes, chamadas a modelos de IA, nem
cálculo de métricas — isso é escopo de módulos futuros.