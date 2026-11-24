"""Questions the corpus cannot answer (D-022).

Each is easy general knowledge, so a model is tempted to answer from memory. `pattern` matches
the well-known answer. A question is only used if its pattern matches nothing in any corpus page,
which is checked by code every time, so "the corpus cannot answer this" is a fact and not a hope.
"""

import re

from evals.common import ROOT, load_pages, write_jsonl

UNANSWERABLE = ROOT / "unanswerable.jsonl"
WANTED = 20

CANDIDATES = [
    ("How tall is K2, the second-highest mountain on Earth?", r"8[,.]?611"),
    ("What is the half-life of tritium?", r"12\.3"),
    ("Who discovered the neutron?", r"Chadwick"),
    ("What is the capital of Kazakhstan?", r"Astana"),
    ("What is the tallest mountain in South America?", r"Aconcagua"),
    ("Who led the first expedition to reach the South Pole?", r"Amundsen"),
    ("What is the deepest known point in the ocean?", r"Challenger Deep|Mariana"),
    ("Who developed the first effective polio vaccine?", r"Salk"),
    ("Who painted the Mona Lisa?", r"Leonardo|da Vinci"),
    ("Who proved Fermat's Last Theorem?", r"Wiles"),
    ("What is the largest volcano on Mars?", r"Olympus Mons"),
    ("Which chemical element has the symbol W?", r"[Tt]ungsten"),
    ("Who composed The Four Seasons?", r"Vivaldi"),
    ("What is the longest river in Africa?", r"\bNile\b"),
    ("What is the maximum possible supply of Bitcoin?", r"21 million"),
    ("Which Roman emperor ruled when Vesuvius destroyed Pompeii?", r"\bTitus\b"),
    ("Who discovered penicillin?", r"Fleming"),
    ("Who wrote the book Silent Spring?", r"Carson"),
    ("Which company developed the AlphaFold protein-structure model?", r"DeepMind"),
    ("What was the first artificial satellite to orbit Earth?", r"Sputnik"),
    ("Who wrote the novel Roadside Picnic?", r"Strugatsky"),
    ("What is the largest moon of Saturn?", r"\bTitan\b"),
    ("What is the capital of Australia?", r"Canberra"),
    ("Who was the first woman to win a Nobel Prize?", r"Curie"),
    ("Which planet has the Great Red Spot?", r"Jupiter"),
    ("Who wrote the play Hamlet?", r"Shakespeare"),
    ("What is the smallest country in the world by area?", r"Vatican"),
    ("Which scientist formulated the three laws of planetary motion?", r"Kepler"),
    ("Who wrote the novel One Hundred Years of Solitude?", r"M[aá]rquez"),
    ("What is the capital of Mongolia?", r"Ulaanbaatar|Ulan Bator"),
    ("Which artist painted The Starry Night?", r"[Vv]an Gogh"),
    ("Who composed the opera The Magic Flute?", r"Mozart"),
    ("Which mountain is the highest in Africa?", r"Kilimanjaro"),
    ("Who was the first person to walk on the Moon?", r"Armstrong"),
    ("What is the tallest waterfall in the world?", r"Angel Falls"),
    ("Which city hosted the 2016 Summer Olympics?", r"Rio de Janeiro"),
    ("What is the largest lake in Africa?", r"Lake Victoria"),
    ("Who directed the film Seven Samurai?", r"Kurosawa"),
    ("What is the capital of Canada?", r"Ottawa"),
    ("Who invented the telephone?", r"Graham Bell"),
]


def absent_from_corpus(pattern: str, texts: list[str]) -> bool:
    return not any(re.search(pattern, text) for text in texts)


def run() -> None:
    texts = [page["text"] for page in load_pages().values()]
    usable = [(q, p) for q, p in CANDIDATES if absent_from_corpus(p, texts)]
    dropped = [q for q, p in CANDIDATES if not absent_from_corpus(p, texts)]
    rows = [
        {"id": f"u{n:02d}", "kind": "unanswerable", "question": q, "pages": [], "answer_pattern": p}
        for n, (q, p) in enumerate(usable[:WANTED], start=1)
    ]
    write_jsonl(UNANSWERABLE, rows)
    print(f"unanswerable: wrote {len(rows)} questions; {len(dropped)} candidates dropped because")
    print(f"  the corpus does contain their answer: {dropped}")
