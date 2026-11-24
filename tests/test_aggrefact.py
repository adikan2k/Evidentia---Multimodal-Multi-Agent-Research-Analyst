"""The LLM-AggreFact eval, tested with made-up rows and scripted models. No network."""

import asyncio
import json

import pytest

from evals.aggrefact import (
    FINISH_LINE,
    Row,
    balanced_accuracy,
    draw_sample,
    evaluate,
    join,
    mean_bacc,
    row_deps,
    sample,
    summarise,
)
from evidentia.audit.schemas import AuditJudgement, Evidence, PageJudgement
from evidentia.cost import Ledger
from evidentia.tracing import NoopTracer
from tests.fakes import FakeVoyage, reply

DOC = "The plant opened in 2019. It produces 40 megawatts. Its owner is the city council."
TRUE, FALSE = "The plant opened in 2019.", "The plant opened in 2005."


def rows(n: int = 6) -> list[Row]:
    claims = [TRUE, FALSE]
    return [
        Row(split="dev", row=i, dataset=f"D{i % 2}", doc=DOC, claim=claims[i % 2], label=1 - i % 2)
        for i in range(n)
    ]


class Scripted:
    """Backs claims that are in the document word for word. `page_wrong` flips the page judge."""

    def __init__(self, page_wrong: bool = False) -> None:
        self.calls = 0
        self.page_wrong = page_wrong

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
        return reply(PageJudgement(reason="r", supported=true != self.page_wrong))


def make(settings, cap: float = 1.0, page_wrong: bool = False):
    shared = Ledger(cap)
    model = Scripted(page_wrong)

    def deps():
        d = row_deps(settings, shared, NoopTracer(), FakeVoyage())
        d.llm._call = model
        return d

    return deps, model, shared


def run_both(settings, tmp_path, page_wrong=False, n=6):
    deps, model, shared = make(settings, page_wrong=page_wrong)
    out = {j: tmp_path / f"{j}.jsonl" for j in ("quote", "page")}
    found = {j: asyncio.run(evaluate(rows(n), j, deps, out[j])) for j in out}
    return found, out, model


def test_samples_are_fixed_and_the_fresh_test_sample_shares_no_rows() -> None:
    many = [
        Row(split="test", row=i, dataset=f"D{i % 3}", doc="d", claim="c", label=i % 2)
        for i in range(600)
    ]
    first = sample("test", many)
    assert first == sample("test", list(reversed(many)))
    counts = {d: sum(r.dataset == d for r in first) for d in ("D0", "D1", "D2")}
    assert counts == {"D0": 50, "D1": 50, "D2": 50}
    fresh = sample("test2", many)
    assert len(fresh) == 150 and not {r.row for r in first} & {r.row for r in fresh}
    assert len(draw_sample(many[:4], per_dataset=10)) == 4  # a small sub-dataset is kept whole


def test_balanced_accuracy_weighs_both_classes_equally() -> None:
    pairs = [(1, 1)] * 8 + [(0, 1)] * 2  # plain accuracy 0.8, balanced 0.5
    assert balanced_accuracy(pairs) == 0.5
    assert balanced_accuracy([(1, 1), (1, 0)]) == 0.5
    assert mean_bacc({"A": [(1, 1), (0, 0)], "B": [(1, 0), (0, 1)]}) == 0.5


def test_each_judge_is_saved_alone_with_no_dataset_text(settings, tmp_path) -> None:
    found, out, _ = run_both(settings, tmp_path)
    assert [x["quote_label"] for x in found["quote"]] == ["supported", "not_found"] * 3
    assert [x["page_judged"] for x in found["page"]] == ["supported", "not_supported"] * 3
    assert found["quote"][0]["quote_offsets"] == [[0, 25]]
    for path in out.values():
        saved = path.read_text(encoding="utf-8")
        assert "plant" not in saved and "2019" not in saved


def test_agreeing_judges_give_verdicts_with_full_coverage(settings, tmp_path) -> None:
    found, _, _ = run_both(settings, tmp_path)
    body = summarise(found["quote"], found["page"], "dev55", {"quote": "q", "page": "p"})
    two = body["two_judges"]
    assert two["coverage"]["value"] == 1.0
    assert two["flag_precision"]["value"] == 1.0 and two["supported_precision"]["value"] == 1.0
    assert two["labels"] == {"supported": 3, "not_found": 3}
    assert body["finish_line"]["passed"] is True
    assert body["finish_line"]["thresholds"] == FINISH_LINE
    assert "plant" not in json.dumps(body)


def test_disagreement_is_abstention_and_never_raises_the_score(settings, tmp_path) -> None:
    found, _, _ = run_both(settings, tmp_path, page_wrong=True)
    body = summarise(found["quote"], found["page"], "dev55", {"quote": "q", "page": "p"})
    two = body["two_judges"]
    assert two["labels"] == {"needs_human": 6}
    assert two["coverage"]["value"] == 0.0
    assert two["balanced_accuracy_abstain_counted_wrong"]["value"] == 0.0
    assert body["page_judge_alone"]["balanced_accuracy"]["value"] == 0.0
    assert body["quote_judge_alone"]["balanced_accuracy"]["value"] == 1.0
    assert body["finish_line"]["passed"] is False


def test_only_rows_both_judges_finished_are_scored() -> None:
    base = {"dataset": "A", "label": 1, "usd": 0.001}
    quote = [base | {"row": n, "quote_label": "supported", "quote_offsets": []} for n in (1, 2, 3)]
    page = [base | {"row": n, "page_judged": "supported"} for n in (2, 3)]
    assert [x["row"] for x in join(quote, page)] == [2, 3]


def test_saved_rows_are_not_paid_for_twice(settings, tmp_path) -> None:
    deps, model, _ = make(settings)
    out = tmp_path / "page.jsonl"
    asyncio.run(evaluate(rows(4), "page", deps, out))
    calls = model.calls
    asyncio.run(evaluate(rows(6), "page", deps, out))
    assert model.calls == calls + 2
    assert len(out.read_text(encoding="utf-8").splitlines()) == 6


def test_the_cap_stops_the_run_and_keeps_what_finished(settings, tmp_path, capsys) -> None:
    deps, _, shared = make(settings, cap=0.0)
    found = asyncio.run(evaluate(rows(), "page", deps, tmp_path / "page.jsonl"))
    assert found == [] and shared.spent == 0.0
    assert "stopped at the cap" in capsys.readouterr().out


def test_the_report_section_reads_its_numbers_from_the_result(settings, tmp_path) -> None:
    from evals.report import two_judges_section

    found, _, _ = run_both(settings, tmp_path)
    body = summarise(found["quote"], found["page"], "dev550", {"quote": "q", "page": "p"})
    text = "\n".join(two_judges_section({"aggrefact_dev550_q-haiku_p-haiku": body}))
    assert "| Two judges | 1.000 (1.000 to 1.000) |" in text
    assert "dev550" in text


@pytest.mark.parametrize("missing", ["quote", "page"])
def test_nothing_is_scored_without_both_judges(missing, settings, tmp_path) -> None:
    found, _, _ = run_both(settings, tmp_path)
    found[missing] = []
    assert join(found["quote"], found["page"]) == []


def test_partial_can_be_scored_as_its_own_verdict() -> None:
    base = {"dataset": "A", "usd": 0.0, "quote_offsets": []}
    quote = [
        base | {"row": 1, "label": 1, "quote_label": "partial"},
        base | {"row": 2, "label": 0, "quote_label": "not_found"},
        base | {"row": 3, "label": 1, "quote_label": "supported"},
    ]
    page = [
        base
        | {"row": n, "label": q["label"], "page_judged": "not_supported" if n < 3 else "supported"}
        for n, q in zip((1, 2, 3), quote, strict=True)
    ]
    body = summarise(quote, page, "dev55", {"quote": "q", "page": "p"})
    two = body["two_judges"]
    assert two["flag_precision"]["value"] == 0.5  # partial counted as a flag: one of two right
    separate = two["partial_as_its_own_verdict"]
    assert separate["flag_precision"]["value"] == 1.0 and separate["partial_share"] == 0.3333
    assert separate["partial_people_label_supported"] == 1.0
    assert separate["coverage"]["value"] == 1.0
