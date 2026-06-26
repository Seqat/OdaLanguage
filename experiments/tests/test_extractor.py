import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR.parent))        # experiments/ → enables: from extractor import ...
sys.path.insert(0, str(_DIR / "fixtures"))  # experiments/tests/fixtures/ → enables: from extractor_cases import ...

from extractor import parse_oda_block       # noqa: E402
from extractor_cases import CASES           # noqa: E402

import pytest


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fixture_cases(case):
    assert parse_oda_block(case["raw"]) == case["expected"]


EXTRA_CASES = [
    # empty body after strip → None (not empty string)
    {
        "name": "empty_body_oda_fence",
        "raw": "```oda\n\n```",
        "expected": None,
    },
    {
        "name": "empty_body_bare_fence",
        "raw": "```\n   \n```",
        "expected": None,
    },
    # bare fence, closing ``` with no preceding newline
    {
        "name": "bare_fence_no_newline_at_end",
        "raw": "```\nfunc foo() {}```",
        "expected": "func foo() {}",
    },
    # CRLF line endings inside oda fence
    {
        "name": "crlf_oda_fence",
        "raw": "```oda\r\nint x = 1\r\n```",
        "expected": "int x = 1",
    },
    # tie-break by token count: equal size → prefer oda-labeled over bare
    {
        "name": "oda_beats_bare_on_tie",
        "raw": "```\nfunc a() {}\n```\n\n```oda\nfunc b() {}\n```",
        "expected": "func b() {}",
    },
    # largest bare block beats smaller oda block
    {
        "name": "large_bare_beats_small_oda",
        "raw": (
            "```oda\nx = 1\n```\n\n"
            "```\nfunc long() {\n    stay int a = 1\n    stay int b = 2\n    print(a + b)\n}\n```"
        ),
        "expected": "func long() {\n    stay int a = 1\n    stay int b = 2\n    print(a + b)\n}",
    },
]


@pytest.mark.parametrize("case", EXTRA_CASES, ids=[c["name"] for c in EXTRA_CASES])
def test_extra_cases(case):
    assert parse_oda_block(case["raw"]) == case["expected"]
