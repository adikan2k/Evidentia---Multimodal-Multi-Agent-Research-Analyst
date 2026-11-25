import asyncio

import pytest

from evidentia.__main__ import EXIT_BAD_CONFIG, amain, parse_args
from evidentia.config import ConfigError
from evidentia.tracing import LangfuseTracer, NoopTracer, export_span


def test_question_words_are_joined_and_flags_parsed() -> None:
    args = parse_args(["how", "fast", "did", "solar", "grow?", "--json", "--cap", "0.5"])
    assert args.question == "how fast did solar grow?"
    assert args.json is True and args.cap == 0.5


def test_question_is_required() -> None:
    with pytest.raises(SystemExit):
        parse_args([])


def test_missing_key_stops_before_any_work_and_names_it(
    fake_env, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here, so only the fake environment is seen
    monkeypatch.delenv("TAVILY_API_KEY")
    code = asyncio.run(amain(parse_args(["a question"])))
    printed = capsys.readouterr().out
    assert code == EXIT_BAD_CONFIG
    assert "TAVILY_API_KEY" in printed
    assert all(value not in printed for value in fake_env.values())


def test_noop_tracer_matches_what_the_pipeline_calls() -> None:
    tracer = NoopTracer()
    with tracer.span("name", "tool", {"a": 1}) as span:
        span.update(output={"b": 2}, metadata={"usd": 0.1})
    assert tracer.callbacks() == []
    assert tracer.trace_id() is None and tracer.trace_url() is None
    tracer.flush()


def test_anthropic_sdk_spans_are_not_exported_a_second_time() -> None:
    from types import SimpleNamespace

    assert export_span(SimpleNamespace(name="anthropic.messages.create")) is False


@pytest.mark.parametrize(
    "name",
    [
        "RunnableSequence",
        "RunnableLambda",
        "RunnableParallel<parsed,parsing_error>",
        "RunnableAssign<parsed,parsing_error>",
        "RunnableWithFallbacks",
        "PydanticOutputParser",
    ],
)
def test_langchain_wrapper_steps_are_not_exported(name: str) -> None:
    from types import SimpleNamespace

    assert export_span(SimpleNamespace(name=name)) is False


@pytest.mark.parametrize("name", ["ChatAnthropic", "OpenAI-generation", "find", "fetch"])
def test_model_tool_and_step_spans_reach_the_default_filter(name: str, monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr("evidentia.tracing.is_default_export_span", lambda span: True)
    assert export_span(SimpleNamespace(name=name)) is True


def test_rejected_langfuse_keys_stop_the_run_with_a_region_hint(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Rejecting:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def auth_check(self) -> bool:
            raise RuntimeError("401")

    monkeypatch.setattr("evidentia.tracing.Langfuse", Rejecting)
    with pytest.raises(ConfigError) as err:
        LangfuseTracer(settings)
    message = str(err.value)
    assert "us.cloud.langfuse.com" in message and settings.langfuse_host in message
    assert settings.langfuse_secret_key.get_secret_value() not in message
