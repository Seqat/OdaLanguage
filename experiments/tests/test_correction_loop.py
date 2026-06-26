"""Tests for the deterministic-deadlock breaker in run_trial().

Strategy: mock call_agent + ADAPTERS so no network or compiler is hit.
A minimal case_dir fixture provides the files run_trial() reads from disk.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import correction_loop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockAdapter:
    """Replaces oda_structured / oda_plain without hitting the compiler."""

    def __init__(self, compiled_ok=False, feedback="compile error"):
        self.compiled_ok = compiled_ok
        self.feedback = feedback

    def get_feedback(self, path):
        return self.compiled_ok, self.feedback


def _agent_sequence(*contents):
    """Return a call_agent stub that yields each content string in turn.

    Returns the 6-tuple that correction_loop.call_agent returns:
    (content, prompt_tokens, completion_tokens, estimated, model, provider)
    """
    it = iter(contents)

    def _agent(cfg, messages):
        return (next(it), 10, 5, False, "mock-model", "mock-provider")

    return _agent


# Content constants ---------------------------------------------------------

# A well-formed fenced Oda block (parseable, but fails compilation via MockAdapter)
_COMPILE_FAIL = "```oda\nfunc main() { print(x) }\n```"
_COMPILE_FAIL_B = "```oda\nfunc main() { print(y) }\n```"
_COMPILE_FAIL_C = "```oda\nfunc main() { print(z) }\n```"

# Something the extractor cannot parse to a code block
_PARSE_FAIL = "Here is my explanation. No code block present."
_PARSE_FAIL_B = "Let me think about this differently. Still no code."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def case_dir(tmp_path):
    (tmp_path / "broken.oda").write_text("func main() { print(x) }")
    (tmp_path / "meta.json").write_text(json.dumps({
        "category": "test",
        "expected_code": 0,
        "num_bugs": 1,
        "description": "deadlock test fixture",
    }))
    (tmp_path / "expected_stdout.txt").write_text("hello\n")
    return tmp_path


@pytest.fixture
def base_cfg():
    return {
        "max_iterations": 5,
        "calibrate": False,
        "temperature": 0.0,
        "max_tokens": 512,
        "http_timeout": 30,
        "run_timeout": 10,
        "break_on_deadlock": True,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_deadlock_repeated_parse_fail(case_dir, base_cfg):
    """Same unparseable content on iterations 1 and 2 → deadlock at iteration 2."""
    mock_adapter = MockAdapter(compiled_ok=False)
    agent = _agent_sequence(_PARSE_FAIL, _PARSE_FAIL, _PARSE_FAIL, _PARSE_FAIL, _PARSE_FAIL)
    agent_calls = []

    def counting_agent(cfg, messages):
        result = agent(cfg, messages)
        agent_calls.append(result[0])
        return result

    with patch.dict(correction_loop.ADAPTERS, {"structured": mock_adapter, "plain": mock_adapter}), \
         patch.object(correction_loop, "call_agent", counting_agent):
        record = correction_loop.run_trial(case_dir, "structured", 0, base_cfg)

    assert record.get("outcome") == "deadlock"
    assert record.get("deadlock_iteration") == 2
    assert len(agent_calls) == 2  # stopped immediately, did not burn all 5


def test_deadlock_repeated_compile_fail(case_dir, base_cfg):
    """Same parseable-but-failing code on iterations 1 and 2 → deadlock at iteration 2."""
    mock_adapter = MockAdapter(compiled_ok=False)
    agent = _agent_sequence(_COMPILE_FAIL, _COMPILE_FAIL, _COMPILE_FAIL)

    with patch.dict(correction_loop.ADAPTERS, {"structured": mock_adapter, "plain": mock_adapter}), \
         patch.object(correction_loop, "call_agent", agent):
        record = correction_loop.run_trial(case_dir, "structured", 0, base_cfg)

    assert record.get("outcome") == "deadlock"
    assert record.get("deadlock_iteration") == 2
    assert record["iterations_to_compile"] == 2


def test_no_deadlock_progressing_loop(case_dir, base_cfg):
    """Different content each iteration → no deadlock; loop exhausts max_iterations."""
    mock_adapter = MockAdapter(compiled_ok=False)
    # 5 unique contents, one per iteration
    agent = _agent_sequence(
        _COMPILE_FAIL, _COMPILE_FAIL_B, _COMPILE_FAIL_C,
        "```oda\nfunc main() { print(a) }\n```",
        "```oda\nfunc main() { print(b) }\n```",
    )

    with patch.dict(correction_loop.ADAPTERS, {"structured": mock_adapter, "plain": mock_adapter}), \
         patch.object(correction_loop, "call_agent", agent):
        record = correction_loop.run_trial(case_dir, "structured", 0, base_cfg)

    assert "outcome" not in record
    assert record["iterations_to_compile"] == 5


def test_break_on_deadlock_flag_disabled(case_dir, base_cfg):
    """break_on_deadlock=False: repeated content does not stop the loop."""
    base_cfg["break_on_deadlock"] = False
    base_cfg["max_iterations"] = 3
    mock_adapter = MockAdapter(compiled_ok=False)
    agent = _agent_sequence(_COMPILE_FAIL, _COMPILE_FAIL, _COMPILE_FAIL)

    with patch.dict(correction_loop.ADAPTERS, {"structured": mock_adapter, "plain": mock_adapter}), \
         patch.object(correction_loop, "call_agent", agent):
        record = correction_loop.run_trial(case_dir, "structured", 0, base_cfg)

    assert "outcome" not in record
    assert record["iterations_to_compile"] == 3


def test_deadlock_on_later_iteration(case_dir, base_cfg):
    """Progress for 2 iters, then repeat on iter 3 → deadlock at iteration 3."""
    mock_adapter = MockAdapter(compiled_ok=False)
    agent = _agent_sequence(
        _COMPILE_FAIL,    # iter 1: new content
        _COMPILE_FAIL_B,  # iter 2: new content
        _COMPILE_FAIL_B,  # iter 3: same as iter 2 → deadlock
        _COMPILE_FAIL_C,  # iter 4 & 5: would be reached if bug
        _COMPILE_FAIL_C,
    )

    with patch.dict(correction_loop.ADAPTERS, {"structured": mock_adapter, "plain": mock_adapter}), \
         patch.object(correction_loop, "call_agent", agent):
        record = correction_loop.run_trial(case_dir, "structured", 0, base_cfg)

    assert record.get("outcome") == "deadlock"
    assert record.get("deadlock_iteration") == 3
    assert record["iterations_to_compile"] == 3


def test_success_not_deadlock(case_dir, base_cfg):
    """Same content on iter 1 (fails) and iter 2 (compiles) → not a deadlock."""
    # Adapter returns failure on first call, success on second candidate compilation.
    call_count = [0]

    class SequencedAdapter:
        def get_feedback(self, path):
            call_count[0] += 1
            # First call: initial feedback on broken.oda → always fail
            # Second call (iter 1 candidate): fail
            # Third call (iter 2 candidate): succeed
            if call_count[0] >= 3:
                return True, ""
            return False, "compile error"

    agent = _agent_sequence(_COMPILE_FAIL, _COMPILE_FAIL, _COMPILE_FAIL)

    with patch.dict(correction_loop.ADAPTERS, {"structured": SequencedAdapter(), "plain": SequencedAdapter()}), \
         patch.object(correction_loop, "call_agent", agent):
        record = correction_loop.run_trial(case_dir, "structured", 0, base_cfg)

    assert record["compiles"] is True
    assert "outcome" not in record


def test_mixed_parse_and_compile_fails_progress(case_dir, base_cfg):
    """Parse fail then compile fail (different content) → no deadlock."""
    mock_adapter = MockAdapter(compiled_ok=False)
    # iter 1: parse fail; iter 2: different compile fail → not deadlock
    agent = _agent_sequence(_PARSE_FAIL, _COMPILE_FAIL, _COMPILE_FAIL_B, _COMPILE_FAIL_C,
                            "```oda\nfunc main() { print(d) }\n```")

    with patch.dict(correction_loop.ADAPTERS, {"structured": mock_adapter, "plain": mock_adapter}), \
         patch.object(correction_loop, "call_agent", agent):
        record = correction_loop.run_trial(case_dir, "structured", 0, base_cfg)

    assert "outcome" not in record
    assert record["iterations_to_compile"] == 5


def test_both_conditions_identical_deadlock_behaviour(case_dir, base_cfg):
    """structured and plain conditions both deadlock at the same iteration — invariant check."""
    for condition in ("structured", "plain"):
        mock_adapter = MockAdapter(compiled_ok=False)
        agent = _agent_sequence(_COMPILE_FAIL, _COMPILE_FAIL, _COMPILE_FAIL)

        with patch.dict(correction_loop.ADAPTERS, {condition: mock_adapter}), \
             patch.object(correction_loop, "call_agent", agent):
            record = correction_loop.run_trial(case_dir, condition, 0, base_cfg)

        assert record.get("outcome") == "deadlock", f"condition={condition}"
        assert record.get("deadlock_iteration") == 2, f"condition={condition}"
