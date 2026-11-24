# ruff: noqa: E501  (the questions are data; they are kept on one line each)
"""The real-world audit's 100 questions (D-042), fixed before any answer is requested.

    uv run python -m evals realworld questions     # free: writes evals/realworld/questions.jsonl

Half are real, anonymised Google searches from Natural Questions (Kwiatkowski et al., TACL 2019;
CC BY-SA 3.0), drawn with a fixed seed from questions whose annotators marked a paragraph-length
answer. Their only change: the first letter is capitalised and a question mark added, since
they are search queries. Half are about 2025 and 2026, written for this project before any
answer existed.
"""

import json
import random

from evals.common import ROOT, write_jsonl

QUESTIONS = ROOT / "realworld" / "questions.jsonl"
NQ_REPO = "google-research-datasets/natural_questions"
NQ_FILE = "dev/validation-00000-of-00007.parquet"  # one of seven dev shards, about 190 MB
NQ_SEED = 20261129
NQ_COUNT = 50

# Written for D-042. Each needs several checkable facts and a current web search.
RECENT: dict[str, list[str]] = {
    "science": [
        "What did the Vera C. Rubin Observatory show in its first images released in 2025, and what survey is it carrying out?",
        "What did NASA's Europa Clipper spacecraft do during its Mars flyby in 2025, and when is it due to reach Jupiter?",
        "How did estimates of asteroid 2024 YR4's chance of hitting Earth change during 2025?",
        "Who won the 2025 Nobel Prize in Physics, and for what work?",
        "Who won the 2025 Nobel Prize in Chemistry, and what did they develop?",
        "What is China's Tianwen-2 mission, launched in 2025, and what are its targets?",
        "What did the European Space Agency's Euclid telescope release in March 2025?",
        "What did the Solar Orbiter spacecraft reveal in 2025 about the Sun's south pole?",
        "What was notable about the colossal squid filmed in 2025, and where was it seen?",
        "What happened during SpaceX Starship's test flights in 2025?",
    ],
    "health": [
        "What is lenacapavir, and what did the US FDA approve it for in 2025?",
        "What does the WHO Pandemic Agreement adopted in May 2025 commit countries to?",
        "How large was the 2025 measles outbreak in Texas, and how many deaths were reported?",
        "Who won the 2025 Nobel Prize in Physiology or Medicine, and for what discovery?",
        "What is suzetrigine (Journavx), approved by the FDA in 2025, and why was it notable?",
        "What personalised gene-editing treatment did baby KJ Muldoon receive, as reported in 2025?",
        "What changes did the US make to its vaccine advisory committee, ACIP, in 2025?",
        "What did the FDA decide in 2025 about who is eligible for updated COVID-19 vaccines?",
        "How did H5N1 bird flu affect US dairy cattle and poultry in 2025?",
        "How many wild poliovirus cases did Pakistan and Afghanistan report in 2025?",
    ],
    "technology": [
        "What is GPT-5, released by OpenAI in 2025, and what were its main new features?",
        "Which obligations of the EU AI Act started to apply in 2025?",
        "What was DeepSeek-R1, and why did its release in January 2025 affect technology stocks?",
        "What happened to TikTok's ownership and US operations in 2025?",
        "What is Apple's Liquid Glass design, announced in 2025?",
        "What was the SharePoint 'ToolShell' vulnerability exploited in 2025, and who was affected?",
        "What caused the Amazon Web Services outage in October 2025, and what did it disrupt?",
        "What did Nvidia announce about its Blackwell Ultra and Rubin chips in 2025?",
        "What did Google report in 2025 about quantum computing with its Willow chip?",
        "Which company first reached a $5 trillion market value, and when?",
    ],
    "economy": [
        "What tariffs did the US announce on 'Liberation Day' in April 2025?",
        "What did the US Federal Reserve decide about interest rates in September 2025, and why?",
        "How much did the price of gold rise in 2025, and what records did it set?",
        "What did the United States and China agree in their 2025 trade truce?",
        "How long did the US federal government shutdown that began on October 1, 2025 last, and how did it end?",
        "What are the main provisions of the 'One Big Beautiful Bill Act' signed in July 2025?",
        "What all-time high did Bitcoin reach in 2025, and when?",
        "What did the UK government announce in its November 2025 budget?",
        "What economic policies did Japan's Prime Minister Sanae Takaichi propose in 2025?",
        "What happened to US inflation during 2025, according to the consumer price index?",
    ],
    "sport_culture": [
        "Who won the 2025 FIFA Club World Cup, where was it held, and what was the final score?",
        "Who won the 2025 Tour de France, and by what margin?",
        "Which team won the 2025 NBA championship, and who was the Finals MVP?",
        "Who won the 2025 Wimbledon singles titles?",
        "Who won the 2025 Booker Prize, and for which book?",
        "Which film won Best Picture at the 2025 Academy Awards, and who directed it?",
        "Who won the 2025 Formula 1 World Drivers' Championship, and how close was it?",
        "Who won the Eurovision Song Contest 2025, and with which song?",
        "Who won the 2025 Nobel Prize in Literature, and what are they known for?",
        "Who was elected pope in May 2025, and what name did he take?",
    ],
}


def nq_sample() -> list[str]:
    """50 Natural Questions dev questions that have a paragraph-length (long) answer."""
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    from evals.aggrefact import CACHE

    path = hf_hub_download(
        repo_id=NQ_REPO, repo_type="dataset", filename=NQ_FILE, cache_dir=CACHE.parent / "nq"
    )
    table = pq.read_table(path, columns=["question", "annotations"]).to_pylist()
    with_long = []
    for row in table:
        starts = row["annotations"]["long_answer"]
        starts = starts if isinstance(starts, list) else [starts]
        if any(a["start_token"] >= 0 for a in starts):
            with_long.append(row["question"]["text"].strip())
    pool = sorted(set(with_long))
    return random.Random(NQ_SEED).sample(pool, NQ_COUNT)


def questions() -> list[dict]:
    rows = []
    for n, text in enumerate(nq_sample(), start=1):
        question = text[0].upper() + text[1:] + ("" if text.endswith("?") else "?")
        rows.append(
            {"id": f"nq-{n:02d}", "source": "natural_questions", "topic": "", "question": question}
        )
    for topic, items in RECENT.items():
        for n, question in enumerate(items, start=1):
            rows.append(
                {
                    "id": f"{topic}-{n:02d}",
                    "source": "2025_2026",
                    "topic": topic,
                    "question": question,
                }
            )
    return rows


def write_questions() -> None:
    """Writes the file once. Later calls leave it alone, so the questions cannot drift."""
    if QUESTIONS.exists():
        print(f"{QUESTIONS.name} already exists; left as it is")
        return
    rows = questions()
    write_jsonl(QUESTIONS, rows)
    print(f"wrote {len(rows)} questions to {QUESTIONS}")
    print(json.dumps(rows[:3], indent=1))
