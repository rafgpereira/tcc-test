"""Cost of the commercial models: the price of each call and the estimate of the dry run.

Prices come from ``config.PRICE_TABLE`` (US$ per million tokens, with source and date), by date of
validity, so the cost of a call uses the row valid on the day it was made (the price of Gemini
3.8 Flash doubles on 2027-01-01). The estimate calls NOTHING (research R9, decided by the
authors): input tokens are the characters of the real prompts over ``CHARS_PER_TOKEN``, always
shown with its origin; output tokens are the output ceiling (upper bound) and, after the pilot,
the mean measured.
"""

from dataclasses import dataclass, field
from datetime import date

from ai_clients.llm import config
from ai_clients.llm.schemas import PriceRow, Usage, price_table


def price_row_for(model: str, when: date) -> PriceRow:
    """The row of ``model`` valid on ``when``: the latest one starting on or before it."""
    rows = sorted((r for r in price_table() if r.model_key == model), key=lambda r: r.valid_from)
    valid = [r for r in rows if r.valid_from <= when]
    if not valid:
        raise ValueError(f"no price of {model} is valid on {when.isoformat()}")
    return valid[-1]


def call_cost(usage: Usage, row: PriceRow) -> float:
    """``(input - cache) x input + cache x cached input + output x output``, in US$.

    ``output_tokens`` is what the API bills as output (it includes the reasoning tokens).
    """
    fresh = max(usage.input_tokens - usage.cached_input_tokens, 0)
    total = (
        fresh * row.input_per_mtok
        + usage.cached_input_tokens * row.cached_input_per_mtok
        + usage.output_tokens * row.output_per_mtok
    ) / 1_000_000
    return round(total, 8)


@dataclass
class Estimate:
    """What the dry run shows for one scenario (or the total) of one model."""

    combinations: int = 0
    prompt_chars: int = 0
    largest_prompt: tuple[int, str] = (0, "")  # (characters, problem id)
    per_call_chars: list[int] = field(default_factory=list)

    def add(self, problem_id: str, chars: int) -> None:
        self.combinations += 1
        self.prompt_chars += chars
        self.per_call_chars.append(chars)
        if chars > self.largest_prompt[0]:
            self.largest_prompt = (chars, problem_id)

    def merge(self, other: "Estimate") -> None:
        self.combinations += other.combinations
        self.prompt_chars += other.prompt_chars
        self.per_call_chars += other.per_call_chars
        if other.largest_prompt[0] > self.largest_prompt[0]:
            self.largest_prompt = other.largest_prompt


def estimated_input_tokens(model: str, chars: int) -> int:
    return round(chars / config.CHARS_PER_TOKEN[model])


def estimated_cost(model: str, estimate: Estimate, output_per_call: int, when: date) -> float:
    """US$ of ONE call per combination with ``output_per_call`` output tokens, no cache."""
    row = price_row_for(model, when)
    tokens_in = estimated_input_tokens(model, estimate.prompt_chars)
    tokens_out = output_per_call * estimate.combinations
    return (tokens_in * row.input_per_mtok + tokens_out * row.output_per_mtok) / 1_000_000


def cost_range(model: str, estimate: Estimate, when: date) -> tuple[float, float]:
    """(low, high) US$: low = one call per combination with the measured mean output (or the
    ceiling before the pilot); high = up to 3 calls per combination at the output ceiling."""
    mean = config.MEASURED_MEAN_OUTPUT_TOKENS[model] or config.MAX_OUTPUT_TOKENS
    low = estimated_cost(model, estimate, mean, when)
    high = config.MAX_ATTEMPTS * estimated_cost(model, estimate, config.MAX_OUTPUT_TOKENS, when)
    return low, high
