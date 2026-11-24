"""Data shapes for an audit, and the table that turns check results into labels (D-037)."""

from typing import Literal

from pydantic import BaseModel, Field

from evidentia.audit.citations import ParsedAnswer
from evidentia.schemas import SkippedPage, Source

AuditLabel = Literal[
    "supported",
    "partial",
    "contradicted",
    "not_found",  # not on the cited page
    "dead_link",
    "unchecked",  # could not check
    "uncited",
]
Stance = Literal["backs", "contradicts", "neither"]
CheckLabel = Literal["supported", "partial", "contradicted", "unsupported"]

LABEL_TEXT = {
    "supported": "supported",
    "partial": "partial",
    "contradicted": "contradicted",
    "not_found": "not on the cited page",
    "dead_link": "dead link",
    "unchecked": "could not check",
    "uncited": "uncited",
}
# A claim citing several pages shows its best result. "Could not check" ranks above "not found"
# so that a page we failed to read is never reported as a page that lacks the claim.
RANK: list[AuditLabel] = [
    "supported",
    "partial",
    "contradicted",
    "unchecked",
    "not_found",
    "dead_link",
]
DEAD = {"HTTP 404", "HTTP 410", "name does not resolve"}


# What the models return.


class SplitClaim(BaseModel):
    sentence: str = Field(
        description="The sentence from the answer, copied character for character."
    )
    claim: str = Field(description="The claim on its own, readable without the rest of the answer.")


class Split(BaseModel):
    claims: list[SplitClaim]


class Evidence(BaseModel):
    stance: Stance = Field(
        description="Whether the page backs the claim, contradicts it, or neither."
    )
    quotes: list[str] = Field(description="Exact text copied from the page. Empty for neither.")


class AuditJudgement(BaseModel):
    label: CheckLabel
    reason: str = Field(description="One sentence naming exactly what is or is not backed.")


# What the audit records.


class Quote(BaseModel):
    text: str  # always equal to source.text[start:end]
    start: int
    end: int
    pages: tuple[int, int] | None = None


class PageResult(BaseModel):
    """One claim checked against one page it cites."""

    claim: int  # index into AuditState.claims
    citation_id: str
    url: str
    skipped: str | None = None  # why the page was not read
    stance: Stance | None = None
    offered: list[str] = []  # the quotes the finder gave, before the code check
    quotes: list[Quote] = []  # those of them that are exact spans of the page
    verdict: CheckLabel | None = None
    reason: str = ""

    @property
    def label(self) -> AuditLabel:
        if self.skipped is not None:
            return "dead_link" if self.skipped in DEAD else "unchecked"
        if self.stance is None:
            return "unchecked"  # the finder did not answer
        if self.stance == "neither" or not self.quotes:
            return "not_found"
        if self.verdict is None:
            return "unchecked"  # the checker did not answer
        return "not_found" if self.verdict == "unsupported" else self.verdict


class AuditClaim(BaseModel):
    sentence: str  # as it appears in the answer text
    start: int
    end: int
    claim: str
    citation_ids: list[str] = []


class AuditState(BaseModel):
    run_id: str
    answer: str
    parsed: ParsedAnswer | None = None
    claims: list[AuditClaim] = []
    not_located: list[str] = []  # sentences the splitter returned that are not in the answer
    claims_over_limit: int = 0
    sources: list[Source] = []
    skipped: list[SkippedPage] = []
    results: list[PageResult] = []
    trace_id: str | None = None
    trace_url: str | None = None


def claim_label(claim: AuditClaim, results: list[PageResult]) -> AuditLabel:
    if not claim.citation_ids:
        return "uncited"
    labels = {r.label for r in results}
    return next(label for label in RANK if label in labels) if labels else "unchecked"


def disputed(results: list[PageResult]) -> bool:
    """One cited page backs the claim while another contradicts it."""
    labels = {r.label for r in results}
    return "contradicted" in labels and bool(labels & {"supported", "partial"})
