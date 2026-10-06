"""``run.json``: the identity of one run of the SLM suite generation.

Created by the first ``generate`` and compared by every ``generate --resume``: every field except
``created_at`` must be equal, the attempt policy row by row, so a run never mixes attempts made
under different configurations. The read timeout and the retry ceiling for infrastructure failures
are deliberately NOT here: they never change the content of an answer, only how long one waits.
"""

from pydantic import Field, model_validator

from ai_clients import config
from ai_clients.schemas.common import AttemptKind, AttemptPhase, SchemaVersion, Sha256Hex
from dataset.schemas.common import Schema


class SamplingOptions(Schema):
    """The ``options`` sent with every request, besides the seed and the temperature, which are
    those of the attempt (``attempt_policy``)."""

    top_p: float = Field(gt=0, le=1)
    top_k: int = Field(ge=1)
    repeat_penalty: float = Field(gt=0)
    num_ctx: int = Field(ge=1)
    num_predict: int = Field(ge=1)


class AttemptRow(Schema):
    """One row of ``config.ATTEMPT_POLICY``, as recorded in run.json."""

    attempt: int = Field(ge=1)
    phase: AttemptPhase
    seed: int = Field(ge=0)
    temperature: float = Field(gt=0)  # 0 would make the seed, and so every retry, useless
    template: AttemptKind


class RunConfig(Schema):
    schema_version: SchemaVersion = 2
    model: str = Field(min_length=1)
    model_digest: str = Field(min_length=1)
    model_quantization: str
    ollama_version: str = Field(min_length=1)
    options: SamplingOptions
    attempt_policy: list[AttemptRow] = Field(min_length=1)
    prompt_template_sha256: Sha256Hex
    predict_template_sha256: Sha256Hex
    dataset_manifest_sha256: Sha256Hex
    py_time_factor: int = Field(ge=1)
    py_memory_factor: int = Field(ge=1)
    created_at: str  # informative; not compared by --resume

    @model_validator(mode="after")
    def _coherent_policy(self) -> "RunConfig":
        config.check_policy(
            tuple(
                config.AttemptSpec(r.attempt, r.phase, r.seed, r.temperature, r.template.value)
                for r in self.attempt_policy
            )
        )
        return self

    def spec(self, attempt: int) -> AttemptRow:
        """The row of ``attempt`` in this run's policy; ``ValueError`` beyond its last attempt."""
        if not 1 <= attempt <= len(self.attempt_policy):
            raise ValueError(f"attempt must be in [1, {len(self.attempt_policy)}], got {attempt}")
        return self.attempt_policy[attempt - 1]

    def differences(self, other: "RunConfig") -> list[tuple[str, object, object]]:
        """``(field, value here, value in other)`` for every field that differs, but ``created_at``.

        ``options`` field by field and ``attempt_policy`` row by row and field by field
        (``attempt_policy[8].temperature``), so the refusal says exactly what changed.
        """
        mine = self.model_dump(mode="json", exclude={"created_at"})
        theirs = other.model_dump(mode="json", exclude={"created_at"})
        out = []
        for key in sorted(mine):
            if key == "options":
                for sub in sorted(mine[key]):
                    if mine[key][sub] != theirs[key][sub]:
                        out.append((f"options.{sub}", mine[key][sub], theirs[key][sub]))
            elif key == "attempt_policy":
                for n in range(max(len(mine[key]), len(theirs[key]))):
                    here = mine[key][n] if n < len(mine[key]) else None
                    there = theirs[key][n] if n < len(theirs[key]) else None
                    if here is None or there is None:
                        out.append((f"attempt_policy[{n + 1}]", here, there))
                        continue
                    for sub in sorted(here):
                        if here[sub] != there[sub]:
                            out.append((f"attempt_policy[{n + 1}].{sub}", here[sub], there[sub]))
            elif mine[key] != theirs[key]:
                out.append((key, mine[key], theirs[key]))
        return out


def policy_rows() -> list[AttemptRow]:
    """``config.ATTEMPT_POLICY`` as recorded in run.json."""
    return [AttemptRow(**spec._asdict()) for spec in config.ATTEMPT_POLICY]
