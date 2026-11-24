"""The auditor's prompts. The answer and the pages are untrusted: both go inside data blocks."""

from evidentia.llm import DATA_RULE
from evidentia.schemas import Passage

SPLIT_SYSTEM = f"""You split an answer written by an AI tool into claims that can be checked \
one at a time against the pages it cites. The answer is inside <{{tag}}> ... </{{tag}}> tags.

{DATA_RULE}

For each factual claim in the answer, return:
- sentence: the sentence it comes from, copied character for character from the answer, \
including any markers such as [1] inside it. Do not fix or shorten it.
- claim: the claim written so it can be read on its own. Replace words like "it", "this" or \
"they" with what they refer to, taken from the answer. Add nothing the answer does not say, and \
keep every number, date, name and qualifier exactly as the answer states it.

Rules:
- One claim per checkable fact. A sentence with two facts gives two claims with the same \
sentence.
- Skip headings, greetings, advice, opinions, questions and statements about the answer itself.
- Keep the claims in the order they appear."""

FIND_SYSTEM = f"""You look for evidence on one web page for one claim. The claim and the page \
are given; the page text is inside <{{tag}}> ... </{{tag}}> tags. A long page is shown as its \
most relevant passages, each in its own block.

{DATA_RULE}

Decide one stance:
- backs: the page states what the claim says.
- contradicts: the page states something that cannot be true at the same time as the claim, \
such as a different number, date or outcome for the same thing.
- neither: the page does not address the claim, or only loosely.

Then give up to {{max_quotes}} quotes that show it:
- Each quote is one contiguous stretch of text copied character for character from ONE block, \
usually one or two sentences. Do not fix typos, change punctuation or capitalisation, join \
separate parts, or put "..." in a quote.
- Choose quotes that contain the specifics: numbers, dates, names, places, who said it.
- A separate checker will see only the claim and your quotes, so the quotes must be enough on \
their own.
- For neither, return no quotes."""

AUDIT_CHECK_SYSTEM = f"""You check whether quotes from a web page back a claim. You are given \
exactly one claim and its quotes, and nothing else. Judge only from the words of the quotes. Do \
not use outside knowledge, and do not assume the page says more than the quotes show.

{DATA_RULE}

Labels:
- supported: the quotes together state everything the claim says. Rewording is fine, but every \
fact in the claim, including numbers, dates, names, places, comparisons and causes, must be in \
the quotes.
- partial: the quotes back the claim's main point, but the claim adds at least one specific \
that the quotes do not state.
- contradicted: the quotes state something that cannot be true at the same time as the claim.
- unsupported: the quotes neither back nor contradict the claim's main point.

Give the label and one sentence naming exactly what is or is not backed."""


def split_prompt(answer_text: str, tag: str, max_claims: int) -> str:
    return f"Answer:\n<{tag}>\n{answer_text}\n</{tag}>\n\nReturn up to {max_claims} claims."


def find_prompt(claim: str, passages: list[Passage], tag: str) -> str:
    blocks = "\n\n".join(f"<{tag}>\n{p.text}\n</{tag}>" for p in passages)
    return f"Claim: {claim}\n\nPage:\n\n{blocks}"


def audit_check_prompt(claim: str, quotes: list[str], tag: str) -> str:
    """Everything the checker is shown: one claim and its quotes."""
    blocks = "\n".join(f"<{tag}>\n{q}\n</{tag}>" for q in quotes)
    return f"Claim: {claim}\n\nQuotes:\n{blocks}"
