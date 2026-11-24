import asyncio

import pytest

from evidentia.audit.cli import EXIT_BAD_CONFIG, EXIT_BAD_INPUT, amain, parse_args


def test_flags_are_parsed() -> None:
    args = parse_args(["answer.md", "--json", "--cap", "0.1"])
    assert args.answer == "answer.md" and args.json and args.cap == 0.1


def test_a_missing_file_stops_before_any_work(tmp_path, capsys) -> None:
    code = asyncio.run(amain([str(tmp_path / "nope.md")]))
    assert code == EXIT_BAD_INPUT and "Could not read" in capsys.readouterr().out


def test_an_empty_answer_is_refused(tmp_path) -> None:
    path = tmp_path / "answer.md"
    path.write_text("   \n", encoding="utf-8")
    assert asyncio.run(amain([str(path)])) == EXIT_BAD_INPUT


def test_missing_key_is_named_and_no_value_is_printed(
    fake_env, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("VOYAGE_API_KEY")
    path = tmp_path / "answer.md"
    path.write_text("Solar grew 24% [1].\n[1] https://example.org/x", encoding="utf-8")
    code = asyncio.run(amain([str(path)]))
    printed = capsys.readouterr().out
    assert code == EXIT_BAD_CONFIG and "VOYAGE_API_KEY" in printed
    assert all(value not in printed for value in fake_env.values())


def test_the_main_command_sends_audit_to_the_auditor(monkeypatch: pytest.MonkeyPatch) -> None:
    import evidentia.__main__ as entry

    seen: list[list[str]] = []

    async def fake_audit(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    monkeypatch.setattr("evidentia.audit.cli.amain", fake_audit)
    monkeypatch.setattr("sys.argv", ["evidentia", "audit", "answer.md", "--json"])
    with pytest.raises(SystemExit) as stop:
        entry.main()
    assert stop.value.code == 0 and seen == [["answer.md", "--json"]]
