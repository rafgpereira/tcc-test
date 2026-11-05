"""Full names of every abbreviation and column of the dashboard (tooltips and the glossary).

Plain Python, no Streamlit: ``views`` turn ``COLUMNS`` into column tooltips, ``abbr`` into hover
text in the page text, and ``TERMS``/``VALUES`` into the glossary of the sidebar.
"""

import html
import re

# Abbreviations used in the experiment.
TERMS = {
    "AC": "Accepted: a solução correta de referência do problema (AC_ref.cpp)",
    "WA": "Wrong Answer: submissão humana errada (falha real); cada problema tem 100",
    "CE": "Compilation Error: o código não compilou",
    "RE": "Runtime Error: o programa falhou durante a execução",
    "TLE": "Time Limit Exceeded: estourou o limite de tempo do problema",
    "MLE": "Memory Limit Exceeded: estourou o limite de memória do problema",
    "SLM": "Small Language Model: o modelo local (Qwen2.5-Coder-14B)",
    "TDF": "Taxa de Detecção de Falhas: % de WAs que a suíte pega (métrica oficial)",
    "MS": "Mutation Score (escore de mutação): % de mutantes que a suíte pega (métrica oficial)",
    "TFP": "Taxa de Falsos Positivos: % de problemas em que a suíte reprova o AC (métrica oficial)",
    "IIC": "Índice de Influência do Contexto: quanto juntar enunciado e código ajuda ou atrapalha",
    "TC": "Taxa de Cobertura: % de combinações que têm suíte",
    "CPD": "Custo por Detecção: custo da geração dividido pelas falhas detectadas",
    "CSV": "arquivo de tabela (valores separados por vírgula), abre no Excel",
    "decl": "oráculo declarado: o gabarito é a saída esperada que a IA escreveu na suíte",
    "corr": "oráculo corrigido: o gabarito é a saída real do AC na mesma entrada",
}

# Values that appear inside the cells.
VALUES = {
    "slm": "suíte final do modelo local (SLM)",
    "gpt": "suíte do GPT-5.4-mini",
    "gemini": "suíte do Gemini 3.8 Flash",
    "claude": "suíte do Claude Haiku 5.5",
    "slm-attempt1": "1ª tentativa do modelo local, sem o filtro das 12 tentativas",
    "black_box": "caixa-preta: a IA recebeu só o enunciado",
    "white_box": "caixa-branca: a IA recebeu só o código do AC",
    "hybrid": "híbrido: a IA recebeu enunciado e código",
    "accepted": "SLM: a solução Python do modelo passou nos testes públicos",
    "accepted_fallback": "SLM: nenhuma solução passou; usada a melhor tentativa (reserva)",
    "accepted_predicted": "a IA escreveu as saídas esperadas direto, sem executar nada",
    "accepted_barred": "comercial: aceita depois de 3 respostas sem raciocínio",
    "discarded_manual": "sem suíte: fechada à mão pelos autores",
    "passed": "o AC deu a saída esperada",
    "wrong_output": "a saída difere da esperada",
    "runtime_error": "o programa falhou (RE, TLE ou MLE) nas 3 execuções",
    "matematica": "macrocategoria: problemas de matemática",
    "estrutural_otimizacao": "macrocategoria: estruturas de dados e otimização",
    "logica_direta": "macrocategoria: lógica direta / implementação",
}

PREVIEW = " (prévia: Σ detectados ÷ Σ total, só combinações com suíte)"

# column -> (label shown in the header, full explanation on hover)
COLUMNS = {
    "set": ("conjunto", "Conjunto de avaliação: slm, gpt, gemini, claude ou slm-attempt1"),
    "model": ("modelo", "Modelo que gerou a suíte"),
    "problem": ("problema", "Identificador do problema do Codeforces (concurso_índice)"),
    "scenario": ("cenário", "black_box (só enunciado), white_box (só código) ou hybrid (ambos)"),
    "macrocategoria": ("macrocategoria", "matematica, estrutural_otimizacao ou logica_direta"),
    "status": ("status da suíte", "Como a suíte foi obtida (veja o glossário na barra lateral)"),
    "combinations": ("combinações", "Combinações (problema × cenário) avaliadas"),
    "without_suite": ("sem suíte", "Combinações sem suíte (nada foi executado)"),
    "ac_approved": ("AC aprovado", "AC (solução correta) passou em todos os testes da suíte"),
    "ac_rejected": ("AC reprovado", "A suíte reprovou o AC (solução correta): falso positivo"),
    "ac_wrong_output_tests": (
        "testes AC saída ≠",
        "Testes em que o AC (correto) deu saída diferente da esperada: a IA errou o gabarito",
    ),
    "ac_runtime_error_tests": (
        "testes AC com erro",
        (
            "Testes em que o AC falhou (RE, TLE ou MLE) nas 3 execuções: entrada provavelmente "
            "fora das restrições do problema"
        ),
    ),
    "ac_wrong_output": ("testes AC saída ≠", "Testes em que o AC deu saída diferente da esperada"),
    "ac_runtime_error": ("testes AC com erro", "Testes em que o AC falhou (RE, TLE ou MLE)"),
    "wa_declared": (
        "WAs decl",
        "WAs (falhas reais) detectados pelo oráculo declarado (gabarito da IA)",
    ),
    "wa_corrected": (
        "WAs corr",
        "WAs (falhas reais) detectados pelo oráculo corrigido (gabarito do AC)",
    ),
    "mutants_declared": (
        "mutantes decl",
        "Mutantes detectados pelo oráculo declarado (gabarito da IA)",
    ),
    "mutants_corrected": (
        "mutantes corr",
        "Mutantes detectados pelo oráculo corrigido (gabarito do AC)",
    ),
    "wa_gap": ("WAs só decl", "WAs que só o gabarito da IA pegou (decl − corr): detecção inflada"),
    "mutants_gap": ("mutantes só decl", "Mutantes que só o gabarito da IA pegou (decl − corr)"),
    "unstable_tests": (
        "testes instáveis",
        "Testes em que um erro (RE, TLE, MLE) apareceu numa execução e sumiu numa repetição",
    ),
    "not_compiled": ("não compilou", "Alvos (WAs ou mutantes) com CE: erro de compilação"),
    "wa_pct_declared": ("% WAs decl", "% de WAs detectados, gabarito da IA" + PREVIEW),
    "wa_pct_corrected": ("% WAs corr", "% de WAs detectados, gabarito do AC" + PREVIEW),
    "mutants_pct_declared": (
        "% mutantes decl",
        "% de mutantes detectados, gabarito da IA" + PREVIEW,
    ),
    "mutants_pct_corrected": (
        "% mutantes corr",
        "% de mutantes detectados, gabarito do AC" + PREVIEW,
    ),
    "index": ("teste", "Posição do teste na suíte (começa em 0)"),
    "input": ("entrada", "Entrada do teste (stdin); ⏎ marca a quebra de linha"),
    "expected": ("esperada (IA)", "Saída esperada escrita na suíte pela IA: o gabarito declarado"),
    "actual": ("real (AC)", "Saída real do AC nessa entrada: o gabarito corrigido"),
    "ac_verdict": ("veredito do AC", "passed, wrong_output ou runtime_error"),
    "error_kind": ("erro", "RE (falha), TLE (tempo) ou MLE (memória), quando houve erro"),
    "unstable": ("instável", "O erro apareceu numa execução e sumiu numa repetição"),
    "wa_declared_here": ("WAs decl aqui", "WAs detectados neste teste pelo gabarito da IA"),
    "wa_corrected_here": ("WAs corr aqui", "WAs detectados neste teste pelo gabarito do AC"),
    "mut_declared_here": (
        "mutantes decl aqui",
        "Mutantes detectados neste teste pelo gabarito da IA",
    ),
    "mut_corrected_here": (
        "mutantes corr aqui",
        "Mutantes detectados neste teste pelo gabarito do AC",
    ),
}


def column_help(name: str) -> tuple[str, str] | None:
    """Label and explanation of a column, also for the ``<set> decl``/``<set> corr`` columns."""
    if name in COLUMNS:
        return COLUMNS[name]
    parts = name.rsplit(" ", 1)
    if len(parts) == 2 and parts[1] in ("decl", "corr") and parts[0] in VALUES:
        oracle = "gabarito da IA" if parts[1] == "decl" else "gabarito do AC"
        return name, f"% de WAs detectados por {VALUES[parts[0]]}, {oracle}" + PREVIEW
    return None


_ABBR = re.compile(
    r"(?<![\w-])(" + "|".join(sorted(map(re.escape, TERMS), key=len, reverse=True)) + r")(?![\w-])"
)


def abbr(text: str) -> str:
    """The text with every known abbreviation as ``<abbr title=...>`` (hover shows the full name)."""

    def wrap(match: re.Match) -> str:
        term = match.group(1)
        return f'<abbr title="{html.escape(TERMS[term])}">{term}</abbr>'

    return _ABBR.sub(wrap, text)
