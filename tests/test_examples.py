import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.c_sanitize import TEST_CFLAGS, run_generated_binary


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"
GOLDEN_DIR = ROOT / "tests" / "golden" / "examples"


def _example_files():
    if not EXAMPLES_DIR.exists():
        return []
    return sorted(EXAMPLES_DIR.rglob("*.oda"))


EXAMPLE_FILES = _example_files()


def _snapshot_path(example: Path) -> Path:
    rel = example.relative_to(EXAMPLES_DIR)
    return GOLDEN_DIR / rel.with_suffix(rel.suffix + ".c")


@pytest.mark.parametrize(
    "example",
    EXAMPLE_FILES,
    ids=lambda path: str(path.relative_to(EXAMPLES_DIR)),
)
def test_example_transpiles_compiles_and_matches_golden(example):
    if not EXAMPLE_FILES:
        pytest.skip("No .oda files found in examples/")

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "oda"),
                "transpile",
                str(example),
                "--output",
                str(out_dir),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        c_path = out_dir / "output.c"
        subprocess.run(
            [
                "gcc",
                str(c_path),
                *TEST_CFLAGS,
                "-Wall",
                "-Wextra",
                "-Werror",
                "-o",
                str(out_dir / "test_bin"),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        run_generated_binary(
            [str(out_dir / "test_bin")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        generated = c_path.read_text()

    snapshot = _snapshot_path(example)
    if os.environ.get("UPDATE_GOLDENS") == "1":
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(generated)

    assert snapshot.exists(), (
        f"Missing golden snapshot for {example.relative_to(ROOT)}. "
        "Run UPDATE_GOLDENS=1 pytest tests/test_examples.py to create it."
    )
    assert generated == snapshot.read_text()


def test_examples_directory_contains_oda_files():
    if not EXAMPLES_DIR.exists():
        pytest.skip("No examples/ directory exists in this checkout")
    assert EXAMPLE_FILES, "Expected at least one .oda file in examples/"
