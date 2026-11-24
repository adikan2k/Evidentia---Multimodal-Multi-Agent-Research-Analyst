import pytest

from evidentia.pdf import Unreadable, clean_page, join_pages, read_pdf
from evidentia.quote_check import check_quote
from evidentia.schemas import CheckedClaim, Source
from tests.pdfs import encrypt, make_pdf

PAGE_1 = ["Solar capacity grew 24% in 2023, the fastest rate on record.", "Wind was slower."]
PAGE_2 = ["Battery storage doubled over the same period, led by grid-scale", "projects in Texas."]
PAGE_3 = ["Coal use fell in Europe but rose in Asia, so global demand was flat."]


def three_pages() -> Source:
    pdf = read_pdf(make_pdf([PAGE_1, PAGE_2, PAGE_3]), max_pages=10)
    return Source(
        id="S1",
        url="https://agency.example.org/report.pdf",
        text=pdf.text,
        kind="pdf",
        page_starts=pdf.page_starts,
        pages_total=pdf.pages_total,
    )


def test_clean_page_joins_words_split_by_a_hyphen() -> None:
    assert clean_page("the evi-\ndence is  clear") == "the evidence is clear"


def test_clean_page_keeps_the_hyphen_before_a_capital_or_digit() -> None:
    assert (
        clean_page("COVID-\n19 cases and Austria-\nHungary") == "COVID-19 cases and Austria-Hungary"
    )


def test_clean_page_puts_a_page_on_one_line() -> None:
    assert clean_page("  line one\nline   two \n") == "line one line two"


def test_join_pages_records_where_each_page_starts() -> None:
    text, starts = join_pages(["abc", "", "de"])
    assert text == "abc\nde"
    assert starts == [0, 4, 4]  # the empty page starts where the next one does


def test_pdf_text_has_one_line_per_page_and_page_offsets() -> None:
    source = three_pages()
    lines = source.text.split("\n")
    assert len(lines) == 3
    assert lines[0] == " ".join(PAGE_1)
    assert source.page_starts == [0, len(lines[0]) + 1, len(lines[0]) + len(lines[1]) + 2]
    assert source.pages_total == 3


def test_quote_on_page_three_is_cited_to_page_three() -> None:
    claim = CheckedClaim(
        text="Coal demand was flat.", quote="so global demand was flat", source_id="S1"
    )
    checked = check_quote(claim, {"S1": three_pages()}, min_chars=10)
    assert checked.quote_found is True
    assert checked.pages == (3, 3)


def test_quote_across_a_page_break_names_both_pages() -> None:
    quote = "Wind was slower. Battery storage doubled"
    claim = CheckedClaim(text="Storage doubled.", quote=quote, source_id="S1")
    checked = check_quote(claim, {"S1": three_pages()}, min_chars=10)
    assert checked.quote_found is True
    assert checked.pages == (1, 2)


def test_web_page_claims_have_no_page() -> None:
    source = Source(id="S1", url="https://a.org", text="Solar capacity grew 24% in 2023.")
    claim = CheckedClaim(text="Solar grew.", quote="Solar capacity grew 24%", source_id="S1")
    assert check_quote(claim, {"S1": source}, min_chars=10).pages is None


def test_only_the_first_pages_are_read() -> None:
    pdf = read_pdf(make_pdf([PAGE_1, PAGE_2, PAGE_3]), max_pages=2)
    assert pdf.pages_total == 3
    assert len(pdf.page_starts) == 2
    assert "Coal" not in pdf.text


def test_pdf_with_an_empty_open_password_is_read() -> None:
    pdf = read_pdf(encrypt(make_pdf([PAGE_1]), ""), max_pages=10)
    assert pdf.text == " ".join(PAGE_1)


def test_password_protected_pdf_is_unreadable() -> None:
    with pytest.raises(Unreadable, match="encrypted PDF"):
        read_pdf(encrypt(make_pdf([PAGE_1]), "secret"), max_pages=10)


def test_broken_pdf_is_unreadable() -> None:
    with pytest.raises(Unreadable, match="could not read the PDF"):
        read_pdf(b"%PDF-1.4 not really a pdf", max_pages=10)
