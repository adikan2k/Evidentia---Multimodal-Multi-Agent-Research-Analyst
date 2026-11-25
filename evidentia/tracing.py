"""Langfuse tracing behind a small interface, so tests can swap in a tracer that does nothing."""

from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse.span_filter import is_default_export_span

from evidentia.config import ConfigError, Settings


def is_langchain_plumbing(name: str) -> bool:
    """LangChain's own wrapper steps around each model call: RunnableSequence, RunnableLambda,
    RunnableParallel<...>, PydanticOutputParser and so on. They carry no model call of their own
    but made up about nine of every ten observations, and the free tier counts each one."""
    return name.startswith("Runnable") or name.endswith("OutputParser")


def export_span(span: Any) -> bool:
    """Decide which spans go to Langfuse.

    Kept: every model call (generation), every tool call (fetch, search, rerank) and every graph
    step, so rule 11 still holds. Dropped:
    - the Anthropic SDK's own span for each call, because LangChain's callback already records
      that call, and sending both would count each model call and its cost twice;
    - LangChain's wrapper steps (see `is_langchain_plumbing`).
    """
    name = span.name or ""
    if name.startswith("anthropic.") or is_langchain_plumbing(name):
        return False
    return is_default_export_span(span)


# Page texts run to tens of thousands of characters and sit in the graph state, which is traced
# at every node. Prompts stay well under this limit, so they are still traced in full.
MAX_TRACED_CHARS = 20_000
KEPT_CHARS = 2_000


def shorten(*, data: Any, **_: Any) -> Any:
    """Cut very long strings before they are sent to Langfuse."""
    if isinstance(data, str) and len(data) > MAX_TRACED_CHARS:
        return f"{data[:KEPT_CHARS]} ... [{len(data) - KEPT_CHARS} more characters not traced]"
    if isinstance(data, dict):
        return {key: shorten(data=value) for key, value in data.items()}
    if isinstance(data, list | tuple):
        return [shorten(data=value) for value in data]
    return data


class Span(Protocol):
    def update(self, **fields: Any) -> Any: ...


class Tracer(Protocol):
    def span(
        self, name: str, as_type: str = "span", input: Any = None
    ) -> AbstractContextManager[Span]: ...
    def callbacks(self) -> list[Any]: ...
    def trace_id(self) -> str | None: ...
    def trace_url(self) -> str | None: ...
    def flush(self) -> None: ...


class _NoopSpan:
    def update(self, **fields: Any) -> None:
        pass


class NoopTracer:
    """Same interface as LangfuseTracer, records nothing. Used by tests only."""

    @contextmanager
    def span(self, name: str, as_type: str = "span", input: Any = None):
        yield _NoopSpan()

    def callbacks(self) -> list[Any]:
        return []

    def trace_id(self) -> str | None:
        return None

    def trace_url(self) -> str | None:
        return None

    def flush(self) -> None:
        pass


class LangfuseTracer:
    def __init__(self, settings: Settings) -> None:
        self._public_key = settings.langfuse_public_key.get_secret_value()
        self._host = settings.langfuse_host
        self.client = Langfuse(
            public_key=self._public_key,
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            base_url=settings.langfuse_host,
            should_export_span=export_span,
            mask=shorten,
        )
        self._require_working_keys()

    def _require_working_keys(self) -> None:
        # Every call must be traced, so a run that cannot trace should not start.
        try:
            ok = self.client.auth_check()
        except Exception:
            ok = False
        if not ok:
            raise ConfigError(
                f"Langfuse at {self._host} did not accept LANGFUSE_PUBLIC_KEY and "
                "LANGFUSE_SECRET_KEY. Keys only work in the region the project was created in; "
                "for a US project set LANGFUSE_HOST=https://us.cloud.langfuse.com"
            )

    def span(self, name: str, as_type: str = "span", input: Any = None):
        """Open a span under whatever span is current, so one run is one trace."""
        return self.client.start_as_current_observation(name=name, as_type=as_type, input=input)

    def callbacks(self) -> list[Any]:
        """Passed to LangGraph so every model call is traced with its tokens."""
        return [CallbackHandler(public_key=self._public_key)]

    def trace_id(self) -> str | None:
        return self.client.get_current_trace_id()

    def trace_url(self) -> str | None:
        return self.client.get_trace_url()

    def flush(self) -> None:
        self.client.flush()
