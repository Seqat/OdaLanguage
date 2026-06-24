#!/usr/bin/env python3
import os
import sys
import json
import subprocess
from pathlib import Path

def main():
    # 1. Resolve paths
    repo_root = Path(__file__).resolve().parent.parent
    corpus_dir = repo_root / "experiments" / "corpus"
    
    # Find python interpreter in venv if available
    if os.name == 'nt' and (repo_root / "venv" / "Scripts" / "python.exe").exists():
        python_bin = str(repo_root / "venv" / "Scripts" / "python.exe")
    elif (repo_root / "venv" / "bin" / "python").exists():
        python_bin = str(repo_root / "venv" / "bin" / "python")
    else:
        python_bin = sys.executable

    # Find all case directories
    if not corpus_dir.exists():
        print(f"Error: Corpus directory not found at {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    case_dirs = sorted([d for d in corpus_dir.iterdir() if d.is_dir()], key=lambda d: d.name)

    if not case_dirs:
        print("No test cases found in corpus.", file=sys.stderr)
        sys.exit(0)

    # We will collect results for each case
    results = []
    any_failed = False

    for case_dir in case_dirs:
        case_name = case_dir.name
        broken_oda = case_dir / "broken.oda"
        meta_json = case_dir / "meta.json"
        fixed_oda = case_dir / "fixed.oda"
        expected_stdout_file = case_dir / "expected_stdout.txt"

        transpile_ok = True
        run_ok = True
        errors_logged = []

        # -------------------------------------------------------------
        # 1. Transpile broken.oda
        # -------------------------------------------------------------
        if not broken_oda.exists() or not meta_json.exists():
            transpile_ok = False
            errors_logged.append("Missing broken.oda or meta.json")
        else:
            try:
                # Load expected codes
                with open(meta_json, "r") as f:
                    meta = json.load(f)
                expected_codes = {v for k, v in meta.items() if k.startswith("expected_code") and isinstance(v, str)}
            except Exception as e:
                transpile_ok = False
                expected_codes = set()
                errors_logged.append(f"Failed to read/parse meta.json: {e}")

            if transpile_ok:
                broken_oda_rel = broken_oda.relative_to(repo_root)
                cmd_transpile = [python_bin, "./oda", "transpile", str(broken_oda_rel), "--output-format=json"]
                
                res_transpile = subprocess.run(
                    cmd_transpile,
                    capture_output=True,
                    text=True,
                    cwd=str(repo_root)
                )

                try:
                    data = json.loads(res_transpile.stdout)
                    reported_errors = data.get("errors", [])
                    reported_codes = {err["code"] for err in reported_errors if "code" in err}
                    
                    if reported_codes != expected_codes:
                        transpile_ok = False
                        errors_logged.append(f"Expected code(s) {expected_codes}, got {reported_codes}")
                except Exception as e:
                    transpile_ok = False
                    errors_logged.append(f"Failed to parse JSON output or other error: {e}. Output was: {res_transpile.stdout}")

        # -------------------------------------------------------------
        # 2. Run fixed.oda
        # -------------------------------------------------------------
        if not fixed_oda.exists() or not expected_stdout_file.exists():
            run_ok = False
            errors_logged.append("Missing fixed.oda or expected_stdout.txt")
        else:
            try:
                expected_stdout = expected_stdout_file.read_text()
            except Exception as e:
                run_ok = False
                errors_logged.append(f"Failed to read expected_stdout.txt: {e}")

            if run_ok:
                fixed_oda_rel = fixed_oda.relative_to(repo_root)
                cmd_run = [python_bin, "./oda", "run", str(fixed_oda_rel)]

                res_run = subprocess.run(
                    cmd_run,
                    capture_output=True,
                    text=True,
                    cwd=str(repo_root)
                )

                # Check stdout comparison
                actual_stdout = res_run.stdout
                if actual_stdout != expected_stdout:
                    run_ok = False
                    errors_logged.append(
                        f"Stdout mismatch.\nExpected:\n{repr(expected_stdout)}\nActual:\n{repr(actual_stdout)}"
                    )

        # Update global fail flag
        if not transpile_ok or not run_ok:
            any_failed = True

        results.append({
            "name": case_name,
            "transpile": "PASS" if transpile_ok else "FAIL",
            "run": "PASS" if run_ok else "FAIL",
            "errors": errors_logged
        })

    # Print summary table
    name_w = max(len(r["name"]) for r in results)
    name_w = max(name_w, 9) # min width for "Case Name"

    # Header
    print(f"{'Case Name'.ljust(name_w)} | {'Transpile Check'.ljust(15)} | {'Run Check'.ljust(10)}")
    print("-" * (name_w + 34))

    for r in results:
        print(f"{r['name'].ljust(name_w)} | {r['transpile'].ljust(15)} | {r['run'].ljust(10)}")

    # Print failure details if any
    failed_cases = [r for r in results if r["transpile"] == "FAIL" or r["run"] == "FAIL"]
    if failed_cases:
        print("\n--- Failure Details ---")
        for r in failed_cases:
            print(f"\nCase: {r['name']}")
            print(f"  Transpile: {r['transpile']}")
            print(f"  Run:       {r['run']}")
            for err in r["errors"]:
                print(f"  Error:     {err}")
    
    if any_failed:
        sys.exit(1)
    else:
        print("\nAll cases passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
