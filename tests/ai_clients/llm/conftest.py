"""Fixtures of the commercial-model tests: the environment and the command with a fake provider.

The synthetic dataset (``repo``) comes from ``tests/ai_clients/conftest.py``.
"""

import pytest

from ai_clients.llm import cli as llm_cli
from ai_clients.llm import config
from tests.ai_clients.llm.fakes import FakeClock, FakeProvider, answer


@pytest.fixture()
def env(monkeypatch):
    for model in config.MODELS:
        monkeypatch.setenv(config.ENV_API_KEY[model], f"secret-{model}-key")
        monkeypatch.delenv(config.ENV_MAX_CONCURRENCY[model], raising=False)
        monkeypatch.delenv(config.ENV_MAX_INFRA_RETRIES[model], raising=False)
    monkeypatch.delenv(config.ENV_HTTP_TIMEOUT_S, raising=False)


@pytest.fixture()
def clock():
    return FakeClock()


@pytest.fixture()
def providers(monkeypatch, repo, env, clock):
    """``generate --model ...`` inside ``repo`` with fake providers that answer well by default."""
    monkeypatch.chdir(repo)
    made = {model: FakeProvider(model, default=answer(model)) for model in config.MODELS}
    created = []

    def make_client(model, api_key, *, timeout_s):
        created.append((model, api_key, timeout_s))
        return made[model]

    monkeypatch.setattr(llm_cli, "make_client", make_client)
    monkeypatch.setattr(llm_cli, "make_clock", lambda: clock)
    made["created"] = created
    return made
