import pytest

from evidentia.config import Settings, load_settings

FAKE_ENV = {
    "ANTHROPIC_API_KEY": "anthropic-test-value",
    "TAVILY_API_KEY": "tavily-test-value",
    "VOYAGE_API_KEY": "voyage-test-value",
    "QDRANT_URL": "https://qdrant.invalid",
    "QDRANT_API_KEY": "qdrant-test-value",
    "LANGFUSE_PUBLIC_KEY": "langfuse-public-test-value",
    "LANGFUSE_SECRET_KEY": "langfuse-secret-test-value",
}


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Fake keys in the environment, and no .env file, so tests never see real secrets."""
    for name in (*FAKE_ENV, "LANGFUSE_HOST", "LANGFUSE_BASE_URL", "COST_CAP_USD"):
        monkeypatch.delenv(name, raising=False)
    for name, value in FAKE_ENV.items():
        monkeypatch.setenv(name, value)
    return FAKE_ENV


@pytest.fixture
def settings(fake_env: dict[str, str]) -> Settings:
    # Tightening is on in the product but off here, so most tests can check one thing at a time.
    # The tests about tightening switch it on themselves.
    return load_settings(_env_file=None, per_host_interval_s=0.0, tighten_partial=False)
