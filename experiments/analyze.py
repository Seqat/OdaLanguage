#!/usr/bin/env python3
"""Analysis script for the Oda LLM self-correction benchmark.

Aggregates trial records, guards against mixed-version pooling, and
filters infrastructure failures from model-performance metrics.
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser(description="Analyze Oda correction-loop results.")
    parser.add_argument("files", nargs="+", type=str, help="Path(s) to .jsonl results files")
    parser.add_argument("--allow-mixed", action="store_true", help="Allow pooling files with differing harness/prompt versions")
    args = parser.parse_args()

    versions_seen = set()
    valid_records = []
    infra_errors = defaultdict(int)

    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)

        with path.open("r", encoding="utf-8") as f:
            first_line = f.readline()
            if not first_line:
                continue

            harness_version = "unknown"
            prompt_version = "unknown"
            
            try:
                first_row = json.loads(first_line)
                if "_meta" in first_row:
                    harness_version = first_row["_meta"].get("harness_version", "unknown")
                    prompt_version = first_row["_meta"].get("prompt_version", "unknown")
                else:
                    # process it as a regular record later
                    pass
            except json.JSONDecodeError:
                pass

            versions_seen.add((harness_version, prompt_version))

            if len(versions_seen) > 1:
                if not args.allow_mixed:
                    print(f"ERROR: Mixed harness/prompt versions detected across files: {versions_seen}", file=sys.stderr)
                    print("Refusing to pool. Use --allow-mixed to override.", file=sys.stderr)
                    sys.exit(1)
                else:
                    print(f"WARNING: Mixed harness/prompt versions detected: {versions_seen}. Proceeding due to --allow-mixed.", file=sys.stderr)

            # process lines
            # if the first line wasn't _meta, we should process it
            lines = [first_line] + f.readlines()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "_meta" in row:
                    continue

                # Is it an infra error?
                # "error" field present, or 0 iterations logged (which means it crashed/stopped before completing 1 iteration)
                has_error = "error" in row
                zero_iters = row.get("iterations_to_compile", 0) == 0 and row.get("parsed_iterations", 0) == 0
                
                if has_error or zero_iters:
                    err_msg = row.get("error", "Zero iterations logged (infra error)")
                    infra_errors[err_msg] += 1
                else:
                    valid_records.append(row)

    # Aggregation
    print(f"--- Analysis Summary ---")
    print(f"Total files: {len(args.files)}")
    print(f"Versions pooled: {list(versions_seen)}")
    print(f"Valid model trials: {len(valid_records)}")
    
    if infra_errors:
        print("\n--- Infrastructure Failures (Excluded from Model Metrics) ---")
        for err, count in sorted(infra_errors.items(), key=lambda x: -x[1]):
            print(f"  {count}x {err}")
    else:
        print("\n--- Infrastructure Failures: None ---")

    if not valid_records:
        return

    # Metrics per condition
    stats = defaultdict(lambda: {"trials": 0, "compiles": 0, "corrects": 0, "parse_fails": 0, "iters": 0})
    for row in valid_records:
        cond = row.get("condition", "unknown")
        stats[cond]["trials"] += 1
        if row.get("compiles"):
            stats[cond]["compiles"] += 1
        if row.get("correct"):
            stats[cond]["corrects"] += 1
        stats[cond]["parse_fails"] += row.get("parse_fails", 0)
        stats[cond]["iters"] += row.get("iterations_to_compile", 0)

    print("\n--- Model Performance (by Condition) ---")
    for cond, st in sorted(stats.items()):
        trials = st["trials"]
        compiles = st["compiles"]
        corrects = st["corrects"]
        parse_fails = st["parse_fails"]
        iters = st["iters"]

        compile_rate = (compiles / trials * 100) if trials > 0 else 0.0
        correct_rate = (corrects / trials * 100) if trials > 0 else 0.0
        pf_rate = (parse_fails / iters * 100) if iters > 0 else 0.0

        print(f"[{cond.upper()}]")
        print(f"  Trials:        {trials}")
        print(f"  Compile Rate:  {compile_rate:.1f}% ({compiles}/{trials})")
        print(f"  Correct Rate:  {correct_rate:.1f}% ({corrects}/{trials})")
        print(f"  Parse Fails:   {pf_rate:.1f}% ({parse_fails}/{iters} iterations)")
        print()

if __name__ == "__main__":
    main()
