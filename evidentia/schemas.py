"""Data shapes shared by every module. The graph state is one of these models."""

from typing import Literal

from pydantic import BaseModel, Field


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
    status: Literal["verified", "unverified"]
    reason: str = ""
    url: str = ""
    start: int | None = None
    end: int | None = None


class Plan(BaseModel):
    queries: list[str] = Field(description="Web search queries, most important first.")


class Draft(BaseModel):
    claims: list[Claim]


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
