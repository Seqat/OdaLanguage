import re
from pathlib import Path

import pytest

from src.oda.errors import SemanticError
from src.oda.importer import Importer
from src.oda.main import _pipeline
from src.oda.semantic import SemanticAnalyzer


def _analyze(source: str) -> SemanticAnalyzer:
    tree = Importer("test.oda").load_entry(source, "test.oda")
    sa = SemanticAnalyzer("test.oda")
    sa.analyze(tree)
    return sa


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


def test_func_main_is_rejected(capsys):
    # Bug A: a top-level `func main` must fail fast in Oda (not leak to gcc).
    source = "func main() -> int {\n    return 0\n}\n"

    sa = _analyze(source)
    assert len(sa.errors) == 1
    assert sa.errors[0].code == "E3046"

    # Pipeline aborts before codegen: exit 1, no C produced.
    with pytest.raises(SystemExit):
        _pipeline(source, "test.oda")


def test_undefined_identifier_does_not_cascade(capsys):
    # Bug B: undefined `y` yields exactly the root error, no bogus operand cascade,
    # and never leaks the Python value 'None' into a message.
    sa = _analyze("int x = y + 1\n")
    assert len(sa.errors) == 1
    assert sa.errors[0].code == "E3033"
    assert all("None" not in e.message for e in sa.errors)

    # Adversarial multi-error file: 'None' must appear nowhere in any rendered message.
    adversarial = (
        "int a = y + 1\n"
        "int b = z * w\n"
        "int c = q[0] + 2\n"
    )
    sa2 = _analyze(adversarial)
    assert sa2.errors
    assert all("None" not in str(e) for e in sa2.errors)
