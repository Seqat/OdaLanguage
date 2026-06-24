"""Plain-feedback adapter for the Oda compiler.

Invariant: the underlying compiler error is identical to the structured adapter
for the same input; only presentation differs. This adapter runs the exact same
compiler invocation and computes `compiled_ok` identically, but degrades the
feedback to the bare human-readable `message` of the first diagnostic, stripping
code, line, and column (e.g. "Undefined variable 'y'.").
"""

import json
import subprocess
from pathlib import Path


def get_feedback(oda_source_path: str) -> tuple[bool, str]:
    repo_root = Path(__file__).resolve().parent.parent.parent
    oda_bin = repo_root / "oda"

    result = subprocess.run(
        [str(oda_bin), "transpile", str(oda_source_path), "--output-format=json"],
        capture_output=True,
        text=True
    )

    # compiled_ok is computed identically to the structured adapter.
    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict) and data.get("success") is True:
            return True, ""
    except json.JSONDecodeError:
        data = None

    # Degrade feedback: take ONLY the human-readable message of the FIRST
    # diagnostic, stripping code, line, and column.
    message = ""
    if isinstance(data, dict):
        errors = data.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                message = str(first.get("message", "")).strip()

    if not message:
        # Same fallback construction as the structured adapter, reduced to its
        # bare message so both adapters surface the identical underlying error.
        message = result.stderr.strip() or "Unknown transpilation failure"

    return False, message
