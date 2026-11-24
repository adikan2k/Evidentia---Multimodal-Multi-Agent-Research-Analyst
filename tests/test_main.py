import asyncio

import pytest

from evidentia.__main__ import EXIT_BAD_CONFIG, amain, parse_args
from evidentia.tracing import NoopTracer


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
