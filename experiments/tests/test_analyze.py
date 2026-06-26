import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ANALYZE_SCRIPT = REPO_ROOT / "experiments" / "analyze.py"

def run_analyze(args, check=True):
    cmd = [sys.executable, str(ANALYZE_SCRIPT)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"analyze.py failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result

def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def test_analyze_mixed_versions_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        f1 = tmp / "run1.jsonl"
        f2 = tmp / "run2.jsonl"

        write_jsonl(f1, [
            {"_meta": {"harness_version": "v1", "prompt_version": "p1"}},
            {"condition": "structured", "compiles": True, "correct": True, "parse_fails": 0, "iterations_to_compile": 2}
        ])

        write_jsonl(f2, [
            {"_meta": {"harness_version": "v2", "prompt_version": "p1"}},
            {"condition": "plain", "compiles": False, "correct": False, "parse_fails": 1, "iterations_to_compile": 10}
        ])

        # Should fail due to mixed versions
        res = run_analyze([str(f1), str(f2)], check=False)
        assert res.returncode != 0
        assert "ERROR: Mixed harness/prompt versions detected" in res.stderr
        assert "Refusing to pool" in res.stderr

def test_analyze_mixed_versions_allow_mixed():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        f1 = tmp / "run1.jsonl"
        f2 = tmp / "run2.jsonl"

        write_jsonl(f1, [
            {"_meta": {"harness_version": "v1", "prompt_version": "p1"}},
            {"condition": "structured", "compiles": True, "correct": True, "parse_fails": 0, "iterations_to_compile": 2}
        ])

        write_jsonl(f2, [
            {"_meta": {"harness_version": "v2", "prompt_version": "p1"}},
            {"condition": "plain", "compiles": False, "correct": False, "parse_fails": 1, "iterations_to_compile": 10}
        ])

        # Should pass because of --allow-mixed
        res = run_analyze(["--allow-mixed", str(f1), str(f2)])
        assert res.returncode == 0
        assert "WARNING: Mixed harness/prompt versions detected" in res.stderr
        assert "Valid model trials: 2" in res.stdout

def test_analyze_infra_errors_excluded():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        f1 = tmp / "run.jsonl"

        write_jsonl(f1, [
            {"_meta": {"harness_version": "v1", "prompt_version": "p1"}},
            # Valid record
            {"condition": "structured", "compiles": True, "correct": True, "parse_fails": 0, "iterations_to_compile": 2},
            # Infra error: HTTP 400
            {"condition": "structured", "error": "HTTPError: 400 Bad Request", "parsed_iterations": 0, "iterations_to_compile": 0},
            # Infra error: 0 iterations logged
            {"condition": "plain", "parsed_iterations": 0, "iterations_to_compile": 0, "parse_fails": 0}
        ])

        res = run_analyze([str(f1)])
        assert res.returncode == 0
        
        # Valid trials should be 1
        assert "Valid model trials: 1" in res.stdout
        # Infra errors should be counted
        assert "HTTPError: 400 Bad Request" in res.stdout
        assert "Zero iterations logged (infra error)" in res.stdout
        
        # In the stats, structured should have 1 trial
        assert "Trials:        1" in res.stdout
        assert "Compile Rate:  100.0% (1/1)" in res.stdout

