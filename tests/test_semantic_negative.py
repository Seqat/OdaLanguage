import re
from pathlib import Path

import pytest

from src.oda.errors import SemanticError
from src.oda.main import _pipeline


ROOT = Path(__file__).resolve().parent
NEGATIVE_DIR = ROOT / "semantic_negative"
EXPECT_RE = re.compile(r"^#\s*EXPECT_ERROR:\s*(?P<keyword>.+?)\s*$")


def _negative_cases() -> list[Path]:
    return sorted(NEGATIVE_DIR.glob("*.oda"))


def _source_without_expect(source: str) -> tuple[str, str]:
    lines = source.splitlines()
    assert lines, "negative semantic test must not be empty"

    match = EXPECT_RE.match(lines[0])
    assert match, "first line must be '# EXPECT_ERROR: <keyword>'"

    return match.group("keyword"), "\n".join(lines[1:]).lstrip()


@pytest.mark.parametrize("path", _negative_cases(), ids=lambda p: p.name)
def test_semantic_negative_case(path: Path, capsys):
    keyword, source = _source_without_expect(path.read_text())

    with pytest.raises((SystemExit, SemanticError)):
        _pipeline(source, str(path))

    captured = capsys.readouterr()
    message = captured.err + captured.out
    assert keyword in message


def test_semantic_negative_cases_exist():
    cases = _negative_cases()
    assert len(cases) >= 11
