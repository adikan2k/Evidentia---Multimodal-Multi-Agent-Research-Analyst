"""Data shapes shared by every module. The graph state is one of these models."""

from typing import Literal

from pydantic import BaseModel, Field, computed_field

Verdict = Literal["supported", "partial", "unsupported"]
Label = Literal["supported", "partial", "unverified"]


class SearchHit(BaseModel):
    url: str
    title: str = ""
    score: float = 0.0
    query: str = ""


class Source(BaseModel):
    """One fetched page. `text` is the stored source text that quotes are checked against."""

    id: str
    url: str
    title: str = ""
    text: str


class SkippedPage(BaseModel):
    url: str
    reason: str


class Passage(BaseModel):
    """A slice of a source: `text == source.text[start:end]`."""

    id: str
    source_id: str
    url: str
    start: int
    end: int
    text: str
    score: float = 0.0


class Claim(BaseModel):
    """What the writer model returns: one sentence, the quote that backs it, and where from."""

    text: str = Field(description="One factual sentence that answers part of the question.")
    quote: str = Field(description="Exact contiguous text copied from one passage.")
    source_id: str = Field(description="The source_id of the passage the quote was copied from.")


class CheckedClaim(Claim):
    """A claim plus what the two checks found. `None` means that check has not run yet."""

    quote_found: bool | None = None
    verdict: Verdict | None = None
    reason: str = ""
    url: str = ""
    start: int | None = None
    end: int | None = None
    revised: bool = False

    @property
    def failed(self) -> bool:
        """True when the claim should get a repair attempt."""
        return self.quote_found is False or self.verdict == "unsupported"

    @computed_field
    @property
    def label(self) -> Label:
        """The one word shown to the reader. See D-014 for the table."""
        if self.quote_found and self.verdict in ("supported", "partial"):
            return self.verdict
        return "unverified"


class Plan(BaseModel):
    queries: list[str] = Field(description="Web search queries, most important first.")


class Draft(BaseModel):
    claims: list[Claim]


class Judgement(BaseModel):
    """What the checker returns for one claim and its quote."""

    label: Verdict
    reason: str = Field(description="One sentence naming exactly what is or is not backed.")


class RepairQueries(BaseModel):
    queries: list[str] = Field(description="One search query per failed claim, in the same order.")


class Revision(BaseModel):
    """What the reviser returns for one failed claim."""

    backed: bool = Field(description="False if no passage backs any version of the claim.")
    text: str = Field(description="The corrected claim, or an empty string if not backed.")
    quote: str = Field(description="Exact contiguous text copied from one passage, or empty.")
    source_id: str = Field(description="The source_id of that passage, or empty.")


class Tightened(BaseModel):
    """What the tighten step returns for one partial claim."""

    text: str = Field(description="The claim rewritten to say only what the quote says.")


class Repair(BaseModel):
    """One failed claim's trip through the repair round."""

    index: int
    query: str
    passages: list[Passage] = []


class RunState(BaseModel):
    """Everything one run knows. Each node returns the fields it fills in."""

    run_id: str
    question: str
    queries: list[str] = []
    hits: list[SearchHit] = []
    sources: list[Source] = []
    skipped: list[SkippedPage] = []
    passages_indexed: int = 0
    passages: list[Passage] = []
    claims: list[Claim] = []
    checked: list[CheckedClaim] = []
    round: int = 0
    repairs: list[Repair] = []
    trace_id: str | None = None
    trace_url: str | None = None
