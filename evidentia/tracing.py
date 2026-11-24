"""Langfuse tracing behind a small interface, so tests can swap in a tracer that does nothing."""

from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from evidentia.config import ConfigError, Settings


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
        self.client = Langfuse(
            public_key=self._public_key,
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            base_url=settings.langfuse_host,
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
                "Langfuse did not accept LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY at LANGFUSE_HOST"
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
