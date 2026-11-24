import pytest

from evidentia.config import ConfigError, load_settings


def test_loads_from_environment(fake_env: dict[str, str]) -> None:
    s = load_settings(_env_file=None)
    assert s.qdrant_url == "https://qdrant.invalid"
    assert s.anthropic_api_key.get_secret_value() == fake_env["ANTHROPIC_API_KEY"]
    assert s.cost_cap_usd == 1.00


def test_secrets_do_not_appear_when_printed(fake_env: dict[str, str]) -> None:
    printed = repr(load_settings(_env_file=None))
    for name in ("ANTHROPIC_API_KEY", "TAVILY_API_KEY", "VOYAGE_API_KEY", "QDRANT_API_KEY"):
        assert fake_env[name] not in printed
    assert fake_env["LANGFUSE_SECRET_KEY"] not in printed


def test_missing_key_names_the_variable_and_leaks_no_value(
    fake_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY")
    with pytest.raises(ConfigError) as err:
        load_settings(_env_file=None)
    message = str(err.value)
    assert "VOYAGE_API_KEY" in message
    assert all(value not in message for value in fake_env.values())
    assert err.value.__cause__ is None


@pytest.mark.parametrize("name", ["LANGFUSE_HOST", "LANGFUSE_BASE_URL"])
def test_langfuse_host_accepts_either_name(
    fake_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "https://us.cloud.langfuse.com")
    assert load_settings(_env_file=None).langfuse_host == "https://us.cloud.langfuse.com"
