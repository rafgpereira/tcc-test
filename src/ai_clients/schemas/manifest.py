"""Schema of ``manifests/slm_suites.manifest.json``, the integrity manifest of the SLM suites zip.

Same shape as the manifests of the dataset and of the mutants: the hash and size of the zip itself
and of every file inside it, ordered by path.
"""

import re

from pydantic import model_validator

from ai_clients import config
from ai_clients.schemas.common import SchemaVersion
from dataset.schemas.common import Schema
from dataset.schemas.manifest import FileHash

_ATTEMPT_NUMBERS = "|".join(str(n) for n in range(1, config.MAX_ATTEMPTS + 1))
SUITE_PATH = re.compile(
    rf"^{config.ZIP_ROOT}/(run\.json|problems/\d+_[A-Za-z0-9]+/(black_box|white_box|hybrid)/"
    rf"(suite\.json|manual_close\.json|"
    rf"attempt_({_ATTEMPT_NUMBERS})\.(generation|execution)\.json))$"
)

__all__ = ["FileHash", "SlmSuitesManifest"]


class SlmSuitesManifest(Schema):
    schema_version: SchemaVersion = 2
    slm_suites_zip: FileHash
    files: list[FileHash]  # one per file inside the zip, `path` as inside the zip, sorted

    @model_validator(mode="after")
    def _well_formed(self) -> "SlmSuitesManifest":
        if self.slm_suites_zip.path != config.ZIP_PATH.as_posix():
            raise ValueError(f'slm_suites_zip.path must be "{config.ZIP_PATH.as_posix()}"')
        paths = [item.path for item in self.files]
        if paths != sorted(paths):
            raise ValueError("files must be ordered by path")
        for path in paths:
            if not SUITE_PATH.match(path):
                raise ValueError(f"{path!r} is not a file of a run of python -m ai_clients")
        return self
