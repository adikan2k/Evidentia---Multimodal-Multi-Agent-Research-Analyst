"""The LLM-AggreFact eval, tested with made-up rows and a scripted model. No network."""

import asyncio
import json

from evals.aggrefact import (
    DirectJudgement,
    Row,
    balanced_accuracy,
    by_dataset,
    draw_sample,
    evaluate,
    mean_bacc,
    paired_difference,
    row_deps,
    score,
    stratified_resamples,
    summarise,
)
from evidentia.audit.schemas import AuditJudgement, Evidence
from evidentia.cost import Ledger
from evidentia.tracing import NoopTracer
from tests.fakes import FakeVoyage, reply

DOC = "The plant opened in 2019. It produces 40 megawatts. Its owner is the city council."


def rows(n: int = 6) -> list[Row]:
    claims = ["The plant opened in 2019.", "The plant opened in 2005."]
    return [
        Row(split="dev", row=i, dataset=f"D{i % 2}", doc=DOC, claim=claims[i % 2], label=1 - i % 2)
        for i in range(n)
    ]


class Scripted:
    """Backs claims that are in the document, word for word; says no to the others."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, model, effort, max_tokens, system, user, schema, config) -> dict:
        self.calls += 1
        claim = user.split("\n")[0].removeprefix("Claim: ")
        true = claim in DOC
        if schema is Evidence:
            found = (
                Evidence(stance="backs", quotes=[claim])
                if true
                else Evidence(stance="neither", quotes=[])
            )
            return reply(found)
        if schema is AuditJudgement:
            return reply(AuditJudgement(label="supported", reason="Stated."))
        return reply(DirectJudgement(supported=true))


def make(settings, cap: float = 1.0):
    shared = Ledger(cap)
    model = Scripted()

    def deps():
        d = row_deps(settings, shared, NoopTracer(), FakeVoyage())
        d.llm._call = model
        return d

    return deps, model, shared


def test_the_sample_takes_the_same_rows_from_each_sub_dataset_every_time() -> None:
    many = [
        Row(split="test", row=i, dataset=f"D{i % 3}", doc="d", claim="c", label=i % 2)
        for i in range(90)
    ]
    first = draw_sample(many, per_dataset=10)
    assert first == draw_sample(list(reversed(many)), per_dataset=10)
    counts = {d: sum(r.dataset == d for r in first) for d in ("D0", "D1", "D2")}
    assert counts == {"D0": 10, "D1": 10, "D2": 10}
    assert len(draw_sample(many[:4], per_dataset=10)) == 4  # a small sub-dataset is kept whole


def test_balanced_accuracy_weighs_both_classes_equally() -> None:
    # 8 supported rows all right, 2 unsupported rows both wrong: plain accuracy 0.8, BAcc 0.5
    pairs = [(1, 1)] * 8 + [(0, 1)] * 2
    assert balanced_accuracy(pairs) == 0.5
    assert balanced_accuracy([(1, 1), (1, 0)]) == 0.5  # only one class present
    groups = {"A": [(1, 1), (0, 0)], "B": [(1, 0), (0, 1)]}
    assert mean_bacc(groups) == 0.5  # plain mean of 1.0 and 0.0


def test_intervals_contain_the_estimate_and_a_system_minus_itself_is_zero() -> None:
    groups = {"A": [(1, 1), (0, 0), (1, 0), (0, 0)] * 5, "B": [(1, 1), (0, 1)] * 10}
    draws = stratified_resamples({d: len(g) for d, g in groups.items()}, resamples=200)
    result = score(groups, draws)
    assert result["ci_low"] <= result["mean_bacc"] <= result["ci_high"]
    assert paired_difference(groups, groups, draws) == {
        "difference": 0.0,
        "ci_low": 0.0,
        "ci_high": 0.0,
    }


def test_both_systems_run_and_the_saved_file_holds_no_dataset_text(settings, tmp_path) -> None:
    deps, _, _ = make(settings)
    out = {s: tmp_path / f"{s}.jsonl" for s in ("auditor", "direct")}
    results = {s: asyncio.run(evaluate(rows(), s, deps, out[s])) for s in out}
    assert [x["pred"] for x in results["auditor"]] == [1, 0, 1, 0, 1, 0]
    assert [x["pred"] for x in results["direct"]] == [1, 0, 1, 0, 1, 0]
    assert results["auditor"][0]["quote_offsets"] == [[0, 25]]
    for path in out.values():
        saved = path.read_text(encoding="utf-8")
        assert "plant" not in saved and "2019" not in saved
    body = summarise(results, "dev", "haiku")
    assert body["systems"]["auditor"]["score"]["mean_bacc"] == 1.0
    assert body["auditor_minus_direct"]["difference"] == 0.0
    assert body["systems"]["auditor"]["rows_with_an_exact_quote"] == 3
    assert "plant" not in json.dumps(body)


def test_saved_rows_are_not_paid_for_twice(settings, tmp_path) -> None:
    deps, model, _ = make(settings)
    out = tmp_path / "direct.jsonl"
    asyncio.run(evaluate(rows(4), "direct", deps, out))
    calls = model.calls
    asyncio.run(evaluate(rows(6), "direct", deps, out))
    assert model.calls == calls + 2
    assert len(out.read_text(encoding="utf-8").splitlines()) == 6


def test_the_cap_stops_the_run_and_keeps_what_finished(settings, tmp_path, capsys) -> None:
    deps, _, shared = make(settings, cap=0.0)
    found = asyncio.run(evaluate(rows(), "direct", deps, tmp_path / "direct.jsonl"))
    assert found == [] and shared.spent == 0.0
    assert "stopped at the cap" in capsys.readouterr().out


def test_summary_counts_only_rows_both_systems_finished() -> None:
    line = {"dataset": "A", "label": 1, "pred": 1, "usd": 0.001, "answered": True}
    audit = {"audit_label": "supported", "quote_offsets": [[0, 5]], "quotes_offered": 1}
    results = {
        "auditor": [line | audit | {"row": n, "pred_partial_ok": 1} for n in (1, 2, 3)],
        "direct": [line | {"row": n} for n in (2, 3)],
    }
    body = summarise(results, "test", "haiku")
    assert body["rows"] == 2
    assert by_dataset(results["direct"], "pred") == {"A": [(1, 1), (1, 1)]}


def test_the_report_section_reads_its_numbers_from_the_result(settings, tmp_path) -> None:
    from evals.report import aggrefact_section

    deps, _, _ = make(settings)
    out = {s: tmp_path / f"{s}.jsonl" for s in ("auditor", "direct")}
    results = {s: asyncio.run(evaluate(rows(), s, deps, out[s])) for s in out}
    text = "\n".join(aggrefact_section({"aggrefact_test_haiku": summarise(results, "test", "x")}))
    assert "| auditor, x | 1.000 (1.000 to 1.000) |" in text
    assert "auditor minus direct +0.000" in text and "| D0 | 3 | 1.000 | 1.000 |" in text


def test_pooled_rates_say_how_often_supported_is_right() -> None:
    from evals.aggrefact import rates

    pairs = [(1, 1), (1, 1), (0, 1), (1, 0), (0, 0)]
    assert rates(pairs) == {
        "said_supported": 3,
        "supported_and_right": 0.6667,
        "caught_supported": 0.6667,
        "caught_unsupported": 0.5,
    }
