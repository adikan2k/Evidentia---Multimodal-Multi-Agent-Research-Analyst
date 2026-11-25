"""The research agent on the open web (D-052). No network and no model calls."""

import asyncio

import pytest

from evals import open_web
from evals.common import Question
from evidentia.schemas import CheckedClaim, RunState, SkippedPage, Source

Q = Question(id="q01", question="How tall is Mount Everest?", kind="factual", pages=[])


def agent_row(qid: str = "q01", **extra) -> dict:
    claim = {"text": "It is 8,849 m tall.", "quote": "8,848.86 m", "quote_found": True}
    return {
        "id": qid,
        "run_id": f"open-web-{qid}",
        "read_at": "2026-11-26T10:00:00+00:00",
        "pages_read": [
            {"url": "https://en.wikipedia.org/wiki/Mount_Everest", "kind": "html"},
            {"url": "https://www.nepal.gov.np/report.pdf", "kind": "pdf"},
        ],
        "pages_not_read": [{"url": "https://paywalled.example/a", "reason": "HTTP 403"}],
        "claims": [claim | {"label": "supported"}, claim | {"label": "unverified"}],
        "repair_rounds": 1,
    } | extra


def test_the_agent_starts_from_plan_and_keeps_what_it_fetched(monkeypatch) -> None:
    seen = {}

    async def fake_run(question, deps, initial=None, start="plan", on_update=None):
        seen["start"], seen["run_id"] = start, initial.run_id
        return RunState(
            run_id=initial.run_id,
            question=question,
            queries=["everest height"],
            sources=[Source(id="S1", url="https://en.wikipedia.org/wiki/Everest", text="x")],
            skipped=[SkippedPage(url="https://blocked.example", reason="disallowed by robots.txt")],
            checked=[CheckedClaim(text="A claim.", quote="x", source_id="S1", quote_found=True)],
        )

    monkeypatch.setattr(open_web, "run_question", fake_run)
    row = asyncio.run(open_web.ask_agent(None, Q))
    assert seen["start"] == "plan"
    assert row["run_id"] == seen["run_id"] and row["run_id"].startswith("open-web-q01-")
    assert row["pages_read"] == [{"url": "https://en.wikipedia.org/wiki/Everest", "kind": "html"}]
    assert row["pages_not_read"][0]["reason"] == "disallowed by robots.txt"
    assert row["read_at"] and len(row["claims"]) == 1


def test_plain_rag_reads_only_the_agents_pages_for_that_question(monkeypatch, tmp_path) -> None:
    asked: list[str] = []
    deleted: list[str] = []

    class FakeStore:
        async def delete_run(self, run_id: str) -> None:
            deleted.append(run_id)

    class FakeDeps:
        store = FakeStore()

    async def fake_baseline(deps, run_id, q):
        asked.append(run_id)
        return {"id": q.id, "question": q.question, "claims": []}

    monkeypatch.setattr(open_web, "run_baseline", fake_baseline)
    pipeline = {"q01": agent_row("q01"), "q02": agent_row("q02")}

    async def one(q: Question) -> dict:
        return await open_web.ask_plain_rag(FakeDeps(), pipeline[q.id], q)

    questions = [Q, Q.model_copy(update={"id": "q02"})]
    asyncio.run(open_web.run_each(tmp_path / "b.jsonl", questions, one))
    assert sorted(asked) == ["open-web-q01", "open-web-q02"] == sorted(deleted)


def test_run_each_skips_questions_already_saved(tmp_path) -> None:
    path = tmp_path / "runs.jsonl"
    calls = []

    async def one(q: Question) -> dict:
        calls.append(q.id)
        return {"id": q.id}

    asyncio.run(open_web.run_each(path, [Q], one))
    asyncio.run(open_web.run_each(path, [Q], one))
    assert calls == ["q01"]


def test_page_stats_count_wikipedia_and_reasons() -> None:
    stats = open_web.page_stats([agent_row(), agent_row("q02", repair_rounds=0)])
    assert stats["pages_read"] == 4 and stats["pages_not_read"] == 2
    assert stats["wikipedia_share_of_pages_read"] == 0.5
    assert stats["not_read_by_reason"] == {"HTTP 403": 2}
    assert stats["pdfs_read"] == 2 and stats["different_sites_read"] == 2
    assert stats["questions_with_a_repair_round"] == 1


def test_agent_claims_point_at_their_quote_and_plain_rag_at_its_passage() -> None:
    agent = open_web.items_of([agent_row()], "open_web_pipeline", "pipeline")
    assert [i["label"] for i in agent] == ["supported", "unverified"]
    assert agent[0]["evidence"] == "8,848.86 m" and agent[0]["key"] == "open_web_pipeline:q01:0"
    rag_row = {"id": "q01", "claims": [{"text": "A.", "evidence": "passage", "url": "u"}]}
    rag = open_web.items_of([rag_row], "open_web_baseline", "baseline")
    assert rag[0]["label"] == "presented" and rag[0]["evidence"] == "passage"


def test_summary_scores_both_systems_on_the_same_questions() -> None:
    pipeline = [agent_row()]
    baseline = [{"id": "q01", "claims": [{"text": "A.", "evidence": "p", "url": "u"}]}]
    verdicts = {
        "open_web_pipeline:q01:0": {"judge": "supported"},
        "open_web_pipeline:q01:1": {"judge": "unsupported"},
        "open_web_baseline:q01:0": {"judge": "partial"},
    }
    out = open_web.summarise(pipeline, baseline, verdicts, {"open_web_pipeline": 0.2})
    agent = out["systems"]["open_web_pipeline"]["presented_as_backed"]["citation_accuracy"]
    rag = out["systems"]["open_web_baseline"]["presented_as_backed"]["citation_accuracy"]
    assert agent["value"] == 1.0 and rag["value"] == 0.0
    assert out["unverified_share_of_agent_claims"] == 0.5
    assert out["systems"]["open_web_pipeline"]["cost_per_question_usd"] == pytest.approx(0.2)
    assert "cost_per_question_usd" not in out["systems"]["open_web_baseline"]


def test_the_sample_is_fixed_and_keeps_the_mix_of_kinds() -> None:
    from evals.common import load_questions

    questions = load_questions()
    first, again = open_web.sample(questions), open_web.sample(questions)
    assert [q.id for q in first] == [q.id for q in again]
    kinds = [q.kind for q in first]
    assert kinds.count("factual") == 15 and kinds.count("contested") == 5


def test_the_report_shows_both_systems_from_the_result_file() -> None:
    from evals import report

    pipeline = [agent_row()]
    baseline = [{"id": "q01", "claims": [{"text": "A.", "evidence": "p", "url": "u"}]}]
    verdicts = {
        "open_web_pipeline:q01:0": {"judge": "supported"},
        "open_web_pipeline:q01:1": {"judge": "unsupported"},
        "open_web_baseline:q01:0": {"judge": "partial"},
    }
    d = open_web.summarise(pipeline, baseline, verdicts, {"open_web_pipeline": 0.2})
    d["not_repeatable"] = "Pages change."
    text = "\n".join(report.open_web_section(d))
    assert "Plain RAG, same pages" in text and "Evidentia" in text
    assert "not measured" in text  # plain RAG's cost was not recorded in this example
    assert "50% from Wikipedia" in text and "HTTP 403 1" in text
    assert "Not run yet" in "\n".join(report.open_web_section(None))
