"""Fuzz harness: no input may ever produce a Python traceback.

Every failure must surface as a structured, JSON-serializable OdaError.
The pipeline is driven through the real CLI via subprocess so that the
top-level catch-all and process exit codes are exercised end-to-end.

All inputs are generated from fixed seeds so the suite is deterministic.
Subprocess calls are fanned out across a thread pool to stay under the
30-second budget (the calls are I/O-bound on the child process).
"""

import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oda.tokens import TokenType, KEYWORDS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ODA = ROOT / "oda"
EXAMPLES = sorted((ROOT / "examples").glob("*.oda"))


# ── Token pool: one plausible textual value per TokenType ────────────
def _token_pool() -> list[str]:
    rev = {tt: kw for kw, tt in KEYWORDS.items()}
    symbols = {
        TokenType.PLUS: "+", TokenType.MINUS: "-", TokenType.STAR: "*",
        TokenType.SLASH: "/", TokenType.PERCENT: "%", TokenType.ASSIGN: "=",
        TokenType.PLUS_ASSIGN: "+=", TokenType.MINUS_ASSIGN: "-=",
        TokenType.STAR_ASSIGN: "*=", TokenType.SLASH_ASSIGN: "/=",
        TokenType.EQ: "==", TokenType.NEQ: "!=", TokenType.LT: "<",
        TokenType.GT: ">", TokenType.LTE: "<=", TokenType.GTE: ">=",
        TokenType.AND: "&&", TokenType.OR: "||", TokenType.NOT: "!",
        TokenType.NULLISH: "??", TokenType.ARROW: "->", TokenType.RANGE: "..",
        TokenType.RANGE_INCLUSIVE: "..=", TokenType.QUESTION: "?",
        TokenType.LPAREN: "(", TokenType.RPAREN: ")", TokenType.LBRACE: "{",
        TokenType.RBRACE: "}", TokenType.LBRACKET: "[", TokenType.RBRACKET: "]",
        TokenType.COMMA: ",", TokenType.DOT: ".", TokenType.COLON: ":",
        TokenType.SEMICOLON: ";",
    }
    literals = {
        TokenType.INTEGER: "42", TokenType.FLOAT_LIT: "3.14",
        TokenType.STRING_LIT: '"hi"', TokenType.CHAR_LIT: "'a'",
        TokenType.IDENTIFIER: "foo",
    }
    pool: list[str] = []
    for tt in TokenType:
        if tt in (TokenType.NEWLINE, TokenType.EOF):
            continue
        if tt in rev:
            pool.append(rev[tt])
        elif tt in symbols:
            pool.append(symbols[tt])
        elif tt in literals:
            pool.append(literals[tt])
    return pool


def _gen_cases() -> list[tuple[str, bytes]]:
    """Build the full deterministic corpus as (label, source-bytes)."""
    cases: list[tuple[str, bytes]] = []

    # (a) seeded random token soup: 300 cases, each <= 40 tokens
    rng = random.Random(1337)
    pool = _token_pool()
    for i in range(300):
        n = rng.randint(1, 40)
        src = " ".join(rng.choice(pool) for _ in range(n))
        cases.append((f"soup_{i}", src.encode("utf-8")))

    # (b) mutation: take an example, delete or duplicate one line
    if EXAMPLES:
        for i in range(30):
            ex = EXAMPLES[rng.randrange(len(EXAMPLES))]
            lines = ex.read_text().splitlines()
            if not lines:
                continue
            idx = rng.randrange(len(lines))
            if rng.random() < 0.5:
                del lines[idx]
            else:
                lines.insert(idx, lines[idx])
            cases.append((f"mut_{i}_{ex.stem}", "\n".join(lines).encode("utf-8")))

    # (c) edge corpus
    cases.append(("empty", b""))
    cases.append(("newlines", b"\n\n\n\n"))
    cases.append(("unterminated_string", b'func main() { string s = "oops'))
    # unmatched braces x50, escalating depth to exercise parser recursion
    for k in range(1, 51):
        depth = k * 60
        body = b"{" if k % 2 else b"}"
        cases.append((f"braces_{k}", b"func main() " + body * depth))
    cases.append(("long_identifier",
                  b"func main() { int " + b"a" * 10000 + b" = 1 }"))
    cases.append(("non_utf8", b"func main() { int x = \xff\xfe\x80 }"))
    cases.append(("null_byte", b"func\x00main() { int x = 1 }"))

    return cases


CASES = _gen_cases()


def _run_case(args) -> tuple[str, int, bytes, bytes]:
    label, source, tmp_root = args
    case_dir = tmp_root / label.replace("/", "_")
    case_dir.mkdir(parents=True, exist_ok=True)
    src_path = case_dir / "in.oda"
    src_path.write_bytes(source)
    out_dir = case_dir / "out"
    proc = subprocess.run(
        [sys.executable, str(ODA), "transpile", str(src_path),
         "-o", str(out_dir), "--output-format=json"],
        capture_output=True,
    )
    return label, proc.returncode, proc.stdout, proc.stderr


def test_fuzz_no_tracebacks(tmp_path):
    work = [(label, src, tmp_path) for label, src in CASES]
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_run_case, work))

    for label, rc, out, err in results:
        # 1. exit code is always a clean compiler exit, never a crash
        if rc not in (0, 1):
            failures.append(f"{label}: exit code {rc}; stderr={err[:200]!r}")
            continue
        # 2. on failure, the diagnostic must be valid JSON (never a traceback)
        if rc == 1:
            blob = err if err.strip() else out
            try:
                json.loads(blob.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                failures.append(
                    f"{label}: exit 1 but output not JSON: {blob[:200]!r}")

    assert not failures, "non-structured failures:\n" + "\n".join(failures)
