"""Errors shared by the commands of ``python -m ai_clients``."""


class ConfigurationError(Exception):
    """The run cannot go on as configured (model missing, a changed digest, a truncated prompt).

    Nothing of the attempt in progress is recorded and no attempt is consumed; the command exits
    with code 3. The errors of the Ollama client that are not a transient outage derive from it.
    """
