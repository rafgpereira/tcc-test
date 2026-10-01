"""The prompt of the SLM: the template of the authors, with only ``<context_data>`` varying.

The template (``src/prompt_templates/slm_prompt.txt``) keeps three literal markers written by the
authors; each must appear exactly once, and all three are replaced in ONE pass, so a marker that
happens to appear inside a statement is never replaced again. Newlines are normalized to ``\\n``
before anything else, so a Windows checkout sends the same prompt and gets the same hash.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ai_clients import config
from ai_clients.problem import ProblemInput

MARKER_CONTEXT = "(scenario-dependent content)"
MARKER_EXAMPLE_INPUT = "(dataset example input)"
MARKER_EXAMPLE_OUTPUT = "(dataset example output)"
MARKERS = (MARKER_CONTEXT, MARKER_EXAMPLE_INPUT, MARKER_EXAMPLE_OUTPUT)
_MARKER_RE = re.compile("|".join(re.escape(m) for m in MARKERS))


@dataclass(frozen=True)
class PromptTemplate:
    text: str  # with "\n" newlines
    sha256: str  # of `text` in UTF-8 (recorded in run.json)


def load_template(path: Path = config.PROMPT_TEMPLATE_PATH) -> PromptTemplate:
    """Read the template; ``ValueError`` unless each marker appears exactly once."""
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    for marker in MARKERS:
        count = text.count(marker)
        if count != 1:
            raise ValueError(f"{path}: {marker!r} must appear exactly once, found {count}")
    return PromptTemplate(text, hashlib.sha256(text.encode("utf-8")).hexdigest())


def context_data(problem: ProblemInput, scenario: str) -> str:
    """The content of ``<context_data>``: the hybrid is the literal union of the other two."""
    statement = f"<problem_statement>\n{problem.statement}\n</problem_statement>"
    code = f"<reference_solution_cpp>\n{problem.ac_ref}\n</reference_solution_cpp>"
    scenario = getattr(scenario, "value", scenario)
    if scenario == "black_box":
        return statement
    if scenario == "white_box":
        return code
    if scenario == "hybrid":
        return f"{statement}\n\n{code}"
    raise ValueError(f"unknown scenario {scenario!r}")


def build_prompt(template: PromptTemplate, problem: ProblemInput, scenario: str) -> str:
    """The prompt of one problem × scenario.

    The example is the FIRST public test of the problem itself (same in the three scenarios); its
    final newlines are dropped so that ``Expected Output:`` starts on the next line.
    """
    example = problem.testes.public_tests[0]
    values = {
        MARKER_CONTEXT: context_data(problem, scenario),
        MARKER_EXAMPLE_INPUT: example.input.rstrip("\n"),
        MARKER_EXAMPLE_OUTPUT: example.output.rstrip("\n"),
    }
    return _MARKER_RE.sub(lambda match: values[match.group(0)], template.text)


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
