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
    # Only needed when a configured model is an OpenAI one, such as the page judge (D-038).
    openai_api_key: SecretStr | None = None
    # Langfuse SDK v5 calls this LANGFUSE_BASE_URL; the plan calls it LANGFUSE_HOST. Accept both.
    langfuse_host: str = Field(
        # Langfuse keys only work in the region the project was created in. This project is in
        # the US region. For an EU project set LANGFUSE_HOST=https://cloud.langfuse.com.
        default="https://us.cloud.langfuse.com",
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
    # Rewrite a claim the checker calls partial so it says only what its quote says (D-023).
    # On: in the evals it cut partial labels from 87 to 6 with no loss of accuracy.
    tighten_partial: bool = True
    # Also search by keywords (BM25) and fuse with dense search. Off: the evals found it added
    # nothing once the reranker is used (D-023). Passages are indexed for both either way.
    keyword_search: bool = False

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

    # Sites such as Wikipedia refuse crawlers that do not say who runs them. The address is the
    # project's public repository; Aditya approved sending it on 2026-11-24.
    user_agent: str = (
        "EvidentiaBot/0.1 "
        "(+https://github.com/adikan2k/Evidentia---Multimodal-Multi-Agent-Research-Analyst)"
    )
    fetch_timeout_s: float = 15.0
    fetch_max_bytes: int = 2_000_000
    pdf_max_bytes: int = 15_000_000
    pdf_max_pages: int = 40
    pdf_timeout_s: float = 20.0
    per_host_interval_s: float = 2.0
    min_page_chars: int = 200
    min_quote_chars: int = 20

    # The auditor (D-037). The checker model and effort above are shared with it.
    splitter_model: str = "claude-haiku-5-5"
    splitter_max_tokens: int = 8_000
    finder_model: str = "claude-sonnet-5-5"
    finder_effort: str = "medium"
    finder_max_tokens: int = 2_000
    # About a cent per claim and page, plus room for the worst case of calls in flight, which
    # the ledger reserves before each call. $0.25 stopped a 5-claim audit with 4 calls in flight.
    audit_cap_usd: float = 0.75  # $0.50 before the page judge doubled the calls (D-038)
    audit_max_claims: int = 25
    audit_max_pages: int = 10
    audit_page_chars: int = 24_000  # longer pages are cut to their best passages for each claim
    audit_top_passages: int = 6
    audit_max_quotes: int = 5  # 3 left multi-part claims partial on the AggreFact dev rows
    audit_concurrency: int = 4
    # Two judges (D-038): a claim gets a verdict only when the quote judge and the page judge
    # agree; otherwise it is labelled "needs a human".
    audit_two_judges: bool = True
    page_judge_model: str = "claude-sonnet-5-5"  # a "gpt-..." name sends it to OpenAI
    page_judge_effort: str = "medium"
    page_judge_max_tokens: int = 1_500
    # The page judge's score (D-039): the share of `page_judge_votes` answers that say supported,
    # or, with `page_judge_probability`, an OpenAI model's probability of "true" (reasoning off).
    page_judge_votes: int = 1
    page_judge_probability: bool = False
    # Supported needs a score of at least this; a flag needs at most `audit_t_flag`; anything in
    # between needs a human. 0.5 and 0.5 with one vote is D-038's plain agreement.
    audit_t_supported: float = 0.5
    audit_t_flag: float = 0.5
    # Show the checker the paragraph around each quote (D-038, practice run 3). Off until kept.
    audit_quote_context: bool = False
    # Send the page as a cached prefix, so other claims on the same page read it cheaply (D-039).
    # Off in the benchmark, where no two rows share a document and a cache write costs 1.25x.
    audit_prompt_cache: bool = True
    quote_context_chars: int = 600

    # The public API (D-028). Dollars are list prices, the same ones the ledger uses.
    daily_budget_usd: float = 1.00  # all live runs and checks in one UTC day
    public_run_cap_usd: float = 0.25  # one live run from the website
    run_reserve_usd: float = 0.12  # set aside when a run starts, replaced by its real cost
    check_cap_usd: float = 0.02  # one "try to break it" check
    max_runs_per_ip: int = 3
    max_checks_per_ip: int = 30
    max_concurrent_runs: int = 2
    allowed_origins: str = "http://localhost:3000"  # comma-separated


def load_settings(**overrides: object) -> Settings:
    """Build Settings, turning pydantic's error into one that names variables and never values."""
    try:
        return Settings(**overrides)
    except ValidationError as err:
        names = sorted({str(e["loc"][0]).upper() for e in err.errors()})
        raise ConfigError(f"Missing or invalid settings: {', '.join(names)}") from None
