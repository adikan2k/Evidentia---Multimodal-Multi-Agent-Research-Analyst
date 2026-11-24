"""All settings in one place. Secrets come from the environment or the project's .env file."""

from pydantic import AliasChoices, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """A required setting is missing or malformed."""


class Settings(BaseSettings):
    # hide_input_in_errors: pydantic would otherwise echo the supplied values, keys included.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    anthropic_api_key: SecretStr
    tavily_api_key: SecretStr
    voyage_api_key: SecretStr
    qdrant_url: str
    qdrant_api_key: SecretStr
    langfuse_public_key: SecretStr
    langfuse_secret_key: SecretStr
    # Langfuse SDK v5 calls this LANGFUSE_BASE_URL; the plan calls it LANGFUSE_HOST. Accept both.
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )

    planner_model: str = "claude-sonnet-5-5"
    writer_model: str = "claude-sonnet-5-5"
    planner_effort: str = "medium"
    writer_effort: str = "high"
    planner_max_tokens: int = 4_000
    writer_max_tokens: int = 12_000

    checker_model: str = "claude-sonnet-5-5"
    checker_effort: str = "medium"
    checker_max_tokens: int = 1_500
    # The cheap, fast model. It only writes search queries for the repair round.
    reader_model: str = "claude-haiku-5-5"
    reader_max_tokens: int = 2_000
    reviser_max_tokens: int = 4_000
    max_repair_rounds: int = 1
    repair_top_k: int = 6

    embed_model: str = "voyage-4-large"
    embed_dim: int = 1024
    rerank_model: str = "rerank-3"
    collection: str = "evidentia_passages"

    cost_cap_usd: float = 1.00

    max_queries: int = 4
    results_per_query: int = 6
    max_pages: int = 12
    max_claims: int = 8
    retrieve_limit: int = 30
    rerank_top_k: int = 10

    user_agent: str = "EvidentiaBot/0.1"
    fetch_timeout_s: float = 15.0
    fetch_max_bytes: int = 2_000_000
    per_host_interval_s: float = 2.0
    min_page_chars: int = 200
    min_quote_chars: int = 20


def load_settings(**overrides: object) -> Settings:
    """Build Settings, turning pydantic's error into one that names variables and never values."""
    try:
        return Settings(**overrides)
    except ValidationError as err:
        names = sorted({str(e["loc"][0]).upper() for e in err.errors()})
        raise ConfigError(f"Missing or invalid settings: {', '.join(names)}") from None
