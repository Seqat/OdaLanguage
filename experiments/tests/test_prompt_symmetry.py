"""Symmetry test: the agent prompt differs between conditions ONLY in the diagnostic block.

The agent-under-test is condition-blind. `AGENT_SYSTEM` is shared byte-for-byte; the sole
per-condition difference is the substituted {FEEDBACK} string (identity-rendered by
FEEDBACK_RENDER). This test renders ONE case under both conditions the way run_trial does and
asserts that everything outside the diagnostic region is identical, making the INVARIANT
(REFACTOR_CONTEXT.md §4) executable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import correction_loop
from correction_loop import build_messages, FEEDBACK_RENDER

# A case rendered under both conditions: same broken program, different feedback string.
PROGRAM = "func main() { print(_x) }"
STRUCTURED_RAW = (
    '{"diagnostics":[{"code":"E5001","line":1,"column":14,'
    '"message":"Cannot access private member \'_x\'"}]}'
)
PLAIN_RAW = "Cannot access private member '_x'."

# The shared template places the feedback after this marker; everything before it is shared.
MARKER = "Compiler feedback:\n"


def _render(condition, raw):
    return build_messages(PROGRAM, FEEDBACK_RENDER[condition](raw))


def test_diagnostic_block_is_the_only_difference():
    msgs_s = _render("structured", STRUCTURED_RAW)
    msgs_p = _render("plain", PLAIN_RAW)

    # System message (the strengthened, shared portion) is byte-identical.
    assert msgs_s[0] == msgs_p[0]

    # User message: identical up to and including the diagnostic marker; only the feedback
    # suffix differs, and each suffix is exactly that condition's raw feedback.
    pre_s, sep_s, fb_s = msgs_s[1]["content"].partition(MARKER)
    pre_p, sep_p, fb_p = msgs_p[1]["content"].partition(MARKER)
    assert sep_s == MARKER and sep_p == MARKER
    assert pre_s == pre_p  # everything outside the diagnostic region is identical
    assert fb_s == STRUCTURED_RAW and fb_p == PLAIN_RAW
    assert fb_s != fb_p  # the diagnostic region is the ONLY difference


def test_strengthened_prompt_text_present():
    """Guard against silent regression of the output contract and Oda spec/example."""
    system = _render("structured", STRUCTURED_RAW)[0]["content"]
    # Output contract.
    assert "exactly one ```oda fenced block" in system
    assert "never a partial diff" in system
    # Oda spec essentials.
    assert "non-nullable by default" in system
    assert "`stay` marks an immutable binding" in system
    assert "`ref` passes a parameter by reference" in system
    # Privacy guidance: fix via a method, never by removing the underscore.
    assert "NEVER by removing the underscore" in system
    # Worked example is a private-member access fixed through a method.
    assert "func value()" in system


def test_render_is_identity_for_both_conditions():
    """FEEDBACK_RENDER must not wrap or relabel the diagnostic for either condition."""
    assert FEEDBACK_RENDER["structured"](STRUCTURED_RAW) == STRUCTURED_RAW
    assert FEEDBACK_RENDER["plain"](PLAIN_RAW) == PLAIN_RAW
