"""``run.json``: the identity of one run of the SLM suite generation.

Created by the first ``generate`` and compared by every ``generate --resume``: every field except
``created_at`` must be equal, so a run never mixes attempts made under different configurations.
The read timeout and the retry ceiling for infrastructure failures are deliberately NOT here: they
never change the content of an answer, only how long one waits for it.
"""

from pydantic import Field, model_validator

from ai_clients.schemas.common import Sha256Hex
from dataset.schemas.common import Schema, SchemaVersion


class SamplingOptions(Schema):
    """The ``options`` sent with every request (besides the seed, which depends on the attempt)."""

    temperature: float = Field(gt=0)  # 0 would make the seed, and so every retry, useless
    top_p: float = Field(gt=0, le=1)
    top_k: int = Field(ge=1)
    repeat_penalty: float = Field(gt=0)
    num_ctx: int = Field(ge=1)
    num_predict: int = Field(ge=1)


class RunConfig(Schema):
    schema_version: SchemaVersion = 1
    model: str = Field(min_length=1)
    model_digest: str = Field(min_length=1)
    model_quantization: str
    ollama_version: str = Field(min_length=1)
    options: SamplingOptions
    seed_base: int
    strict_attempts: int = Field(ge=1)  # attempts before a fallback is accepted (config.py)
    solution_attempts: int = Field(ge=1)  # attempts that ask for a Python solution
    predict_attempts: int = Field(ge=1)  # attempts that ask for a prediction, after those
    max_attempts: int = Field(ge=1)
    prompt_template_sha256: Sha256Hex
    predict_template_sha256: Sha256Hex
    dataset_manifest_sha256: Sha256Hex
    py_time_factor: int = Field(ge=1)
    py_memory_factor: int = Field(ge=1)
    created_at: str  # informative; not compared by --resume

    @model_validator(mode="after")
    def _budget(self) -> "RunConfig":
        if self.strict_attempts > self.solution_attempts:
            raise ValueError("strict_attempts cannot exceed solution_attempts")
        if self.max_attempts != self.solution_attempts + self.predict_attempts:
            raise ValueError("max_attempts is solution_attempts + predict_attempts")
        return self

    def differences(self, other: "RunConfig") -> list[tuple[str, object, object]]:
        """``(field, value here, value in other)`` for every field that differs, except ``created_at``."""
        mine = self.model_dump(mode="json", exclude={"created_at"})
        theirs = other.model_dump(mode="json", exclude={"created_at"})
        out = []
        for key in sorted(mine):
            if key == "options":
                for sub in sorted(mine[key]):
                    if mine[key][sub] != theirs[key][sub]:
                        out.append((f"options.{sub}", mine[key][sub], theirs[key][sub]))
            elif mine[key] != theirs[key]:
                out.append((key, mine[key], theirs[key]))
        return out
