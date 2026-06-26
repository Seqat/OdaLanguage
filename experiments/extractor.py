"""Oda code extractor — parse LLM output into a runnable Oda program.

Rules (in priority order):
  1. If one or more fenced blocks (```oda or bare ```) are present, the block
     with the most tokens wins; oda-labeled beats bare on a tie.
  2. No fence → recover from the first code-keyword line; strip trailing prose.
  3. Prose-only / empty / whitespace-only → return None.
  4. Truncated fence (no closing ```) → best-effort: return whatever follows the
     opening fence; never crash, never return None.

stdlib only (re). Do NOT import from correction_loop or from the compiler.
"""
import re

_ODA_OPEN_RE  = re.compile(r"```oda[ \t]*\r?\n", re.IGNORECASE)
_BARE_OPEN_RE = re.compile(r"```(?!\w)[ \t]*\r?\n")
_CLOSE_STD_RE = re.compile(r"\r?\n```(?!\w)")
_CLOSE_END_RE = re.compile(r"```(?!\w)\s*$")
_TOKEN_RE     = re.compile(r"\w+|[^\w\s]")
_ODA_KW_RE    = re.compile(
    r"^(func|stay|class|guard|import|construct|destruct|"
    r"int|string|float|bool|if|else|return|when|ref)\b"
)
_PROSE_END_RE  = re.compile(r"[.!?]$")
_CODE_CHARS_RE = re.compile(r"[{}=]")


def _collect_fenced_blocks(text):
    """Return list of (is_oda: bool, body: str) for every fenced block found."""
    blocks = []
    i = 0
    n = len(text)
    while i < n:
        m_oda  = _ODA_OPEN_RE.search(text, i)
        m_bare = _BARE_OPEN_RE.search(text, i)
        if m_oda is None and m_bare is None:
            break
        if m_bare is None or (m_oda is not None and m_oda.start() <= m_bare.start()):
            opener, is_oda = m_oda, True
        else:
            opener, is_oda = m_bare, False
        body_start = opener.end()
        close = _CLOSE_STD_RE.search(text, body_start)
        if close is None:
            close = _CLOSE_END_RE.search(text, body_start)
        if close is not None:
            body = text[body_start : close.start()].strip("\n")
            i = close.end()
        else:
            body = text[body_start:].strip("\n")
            i = n
        blocks.append((is_oda, body))
    return blocks


def parse_oda_block(text):
    """Return the best Oda program from model output, or None if no code found."""
    text = text or ""

    blocks = _collect_fenced_blocks(text)
    if blocks:
        def _score(b):
            is_oda, body = b
            return (len(_TOKEN_RE.findall(body)), is_oda)
        _, best_body = max(blocks, key=_score)
        return best_body if best_body.strip() else None

    # No fenced blocks — try no-fence code recovery.
    lines = text.splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        if _ODA_KW_RE.match(line.lstrip()):
            start_idx = idx
            break
    if start_idx is None:
        return None

    end_idx = start_idx
    for idx in range(len(lines) - 1, start_idx - 1, -1):
        stripped = lines[idx].strip()
        is_prose = (
            stripped
            and _PROSE_END_RE.search(stripped)
            and not _CODE_CHARS_RE.search(stripped)
        )
        if not is_prose:
            end_idx = idx
            break

    return "\n".join(lines[start_idx : end_idx + 1])
