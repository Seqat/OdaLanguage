#!/usr/bin/env python3
"""Correction-loop harness for the Oda structured-vs-plain feedback experiment.

For every (case, condition, repeat) trial it shows a (condition-blind) LLM a broken
Oda program plus compiler feedback, asks for a corrected program, and iterates up to
`max_iterations` times. The loop is driven ONLY by compiler diagnostics and stops at the
first clean compile; runtime behaviour is never fed back to the model. Two outcomes are
recorded per trial: `compiles` (a clean compile was reached within k) and `correct`
(it compiles AND the built binary reproduces the expected stdout with a zero exit code).

The agent is BLIND to the condition: the prompt template is byte-for-byte identical in
both conditions. The ONLY thing that differs is the substituted {FEEDBACK} string, which
is the raw return value of the condition's adapter (structured JSON diagnostics vs. the
bare first-diagnostic message).

stdlib only — no third-party deps (urllib for HTTP, a tiny parser for the flat YAML).

Pilot:
    python experiments/correction_loop.py --limit 3
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------------------
# Paths / adapter imports
# --------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = Path(__file__).resolve().parent
ADAPTERS_DIR = EXPERIMENTS_DIR / "adapters"
DEFAULT_CONFIG = EXPERIMENTS_DIR / "config.yaml"
DEFAULT_CORPUS = EXPERIMENTS_DIR / "corpus"

# Adapters expose get_feedback(path) -> (compiled_ok: bool, feedback: str).
sys.path.insert(0, str(ADAPTERS_DIR))
import oda_plain  # noqa: E402
import oda_structured  # noqa: E402

ADAPTERS = {"structured": oda_structured, "plain": oda_plain}

# --------------------------------------------------------------------------------------
# Prompt constants — verbatim from the prompts doc. DO NOT EDIT WORDING.
# --------------------------------------------------------------------------------------

# Identical across BOTH conditions. Contains the {PROGRAM} and {FEEDBACK} placeholders.
AGENT_SYSTEM = """You are a coding assistant for Oda, a memory-safe systems language that transpiles to C. You are given an Oda program that does not yet compile/run correctly, plus compiler feedback. Return a corrected version.

Output rules (strict):
- Output ONLY the complete corrected Oda program, inside exactly ONE ```oda code block.
- No explanation, no commentary, no text outside the code block.
- Make the MINIMAL change that fixes the reported problem. Do not rewrite or delete unrelated code, and do not remove functionality just to silence errors.

Program:
```oda
{PROGRAM}
```

Compiler feedback:
{FEEDBACK}"""

# The two {FEEDBACK} renderings. CRITICAL invariant: the template around {FEEDBACK} is
# IDENTICAL in both conditions, so the rendering is the *identity* of the adapter's raw
# return value. No condition-specific label, prefix, or wrapping is ever added.
#   - structured: raw JSON diagnostics string from oda_structured.get_feedback()
#       e.g. {"diagnostics":[{"code":"E3033","line":4,"column":9,"message":"Undefined variable 'y'"}]}
#   - plain:      bare first-diagnostic message from oda_plain.get_feedback()
#       e.g. Undefined variable 'y'.
FEEDBACK_RENDER = {
    "structured": lambda raw: raw,
    "plain": lambda raw: raw,
}

# Feedback issued when the model's output is not exactly one ```oda block.
PARSE_FAIL_FEEDBACK = "Your output must be exactly one ```oda code block."

# Stop sequence that cuts generation once the code block closes, to stop the model from
# rambling after it. Deliberately "```\n" and NOT "\n```": the latter can match a
# newline-preceded opening fence and truncate the output to empty, whereas "```\n" cannot
# match the "```oda" opening (after the backticks comes "oda", not a newline). The closing
# fence is consumed by the stop sequence, so parse_oda_block tolerates its absence.
CHAT_STOP = ["```\n"]

# --------------------------------------------------------------------------------------
# Config (minimal stdlib YAML for the flat experiments/config.yaml)
# --------------------------------------------------------------------------------------

CALIBRATION_CAP = 10  # --calibrate mode only; experiment default is untouched
DEFAULTS = {"http_timeout": 300, "run_timeout": 60, "max_tokens": 512}


def _coerce_scalar(text):
    """Turn a YAML scalar fragment into a str/int/float/bool."""
    text = text.strip()
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def load_config(path):
    """Parse the flat `key: value` config (with inline lists and `#` comments)."""
    cfg = dict(DEFAULTS)
    for raw_line in Path(path).read_text().splitlines():
        # Strip inline comments (the config has no `#` inside its values).
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            cfg[key] = [_coerce_scalar(p) for p in inner.split(",")] if inner else []
        else:
            cfg[key] = _coerce_scalar(value)
    return cfg

# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------

_ODA_OPEN_RE = re.compile(r"```oda[ \t]*\r?\n", re.IGNORECASE)
_ODA_CLOSE_RE = re.compile(r"\r?\n```")
_TOKEN_RE = re.compile(r"\w+|[^\w\s]")


def parse_oda_block(text):
    """Return the program from the SINGLE ```oda block, or None if absent/ambiguous.

    Requires exactly one ```oda opening fence (case-insensitive). The closing fence is
    optional: the CHAT_STOP stop sequence consumes it, and models sometimes omit it, so
    when no closing fence is present the rest of the text is taken as the program.
    """
    opens = list(_ODA_OPEN_RE.finditer(text or ""))
    if len(opens) != 1:
        return None
    rest = text[opens[0].end():]
    close = _ODA_CLOSE_RE.search(rest)
    body = rest[: close.start()] if close else rest
    return body.strip("\n")


def estimate_tokens(text):
    """Cheap tokenizer used only when the local endpoint omits a usage block."""
    return len(_TOKEN_RE.findall(text or ""))


def build_messages(program, feedback):
    """Render AGENT_SYSTEM verbatim, split into (system rules) / (user program+feedback).

    Placeholders are filled in a SINGLE pass (one re.sub over the original template) so a
    candidate program that literally contains "{FEEDBACK}" cannot be corrupted by a second
    replacement pass, and braces in the Oda source are never treated as format fields.
    """
    idx = AGENT_SYSTEM.index("Program:")
    system_text = AGENT_SYSTEM[:idx].rstrip()
    subs = {"{PROGRAM}": program, "{FEEDBACK}": feedback}
    user_text = re.sub(
        r"\{PROGRAM\}|\{FEEDBACK\}", lambda m: subs[m.group(0)], AGENT_SYSTEM[idx:]
    )
    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]


def call_agent(cfg, messages):
    """POST to the OpenAI-compatible chat endpoint.

    Returns (content, prompt_tokens, completion_tokens, estimated: bool).
    """
    req_body = {
        "model": cfg["agent_model"],
        "messages": messages,
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
    }
    if cfg.get("agent_provider"):
        req_body["provider"] = {"order": [cfg["agent_provider"]], "allow_fallbacks": False}
        
    payload = json.dumps(req_body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    
    # Check for OpenRouter key in .env
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # if line has format KEY=VALUE
                if "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == "OPENROUTER_API_KEY":
                        headers["Authorization"] = f"Bearer {val.strip()}"
                # If .env is just the raw key (as shown by user)
                elif line.startswith("sk-or-v1-"):
                    headers["Authorization"] = f"Bearer {line}"
                    
    req = urllib.request.Request(
        cfg["agent_endpoint"],
        data=payload,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg["http_timeout"]) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    
    # OpenRouter returns model and provider
    resp_model = data.get("model")
    resp_provider = data.get("provider")
    
    if prompt_tokens is None or completion_tokens is None:
        prompt_tokens = estimate_tokens("\n".join(m["content"] for m in messages))
        completion_tokens = estimate_tokens(content)
        return content, prompt_tokens, completion_tokens, True, resp_model, resp_provider
    return content, prompt_tokens, completion_tokens, False, resp_model, resp_provider


def build_and_run(cfg, candidate_src):
    """Build a candidate and execute its binary directly; return (stdout, returncode).

    Harness-only correctness gate (the compiler is left untouched). We do NOT use
    `./oda run`, which discards the inner program's exit code; instead we `./oda build`
    to produce a binary, then exec it directly to capture BOTH stdout and the exit code.
    A build failure or any timeout (e.g. an infinite-loop candidate) returns
    (\"\", None) -> the correctness gate fails without crashing the trial.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "candidate.oda"
        src_path.write_text(candidate_src, encoding="utf-8")
        try:
            build = subprocess.run(
                [cfg["oda_cli"], "build", str(src_path), "-o", tmpdir],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=cfg["run_timeout"],
            )
            if build.returncode != 0:
                return "", None
            bin_path = Path(tmpdir) / src_path.stem
            if not bin_path.exists():
                return "", None
            run = subprocess.run(
                [str(bin_path)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=cfg["run_timeout"],
            )
            return run.stdout, run.returncode
        except subprocess.TimeoutExpired:
            return "", None

# --------------------------------------------------------------------------------------
# Trial
# --------------------------------------------------------------------------------------


def run_trial(case_dir, condition, repeat, cfg):
    """Run one correction loop. Always returns a single result dict (never raises)."""
    case = case_dir.name
    started = time.monotonic()
    iter_detail = []  # per-iteration records (calibration mode only)
    record = {
        "case": case,
        "condition": condition,
        "repeat": repeat,
        "compiles": False,
        "iterations_to_compile": 0,
        "correct": False,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "wall_seconds": 0.0,
    }
    estimated_any = False
    try:
        adapter = ADAPTERS[condition]
        render = FEEDBACK_RENDER[condition]

        broken_path = case_dir / "broken.oda"
        json.loads((case_dir / "meta.json").read_text())  # validated, not otherwise used
        expected = (case_dir / "expected_stdout.txt").read_text()
        current_source = broken_path.read_text()

        # First feedback: the compiler's verdict on broken.oda via this condition's adapter.
        _, raw_fb = adapter.get_feedback(str(broken_path))
        current_feedback = render(raw_fb)

        # The loop is driven ONLY by compiler diagnostics and terminates on the first
        # clean compile. Runtime behaviour is never fed back to the model (that would be a
        # condition-identical channel that dilutes the structured-vs-plain manipulation).
        compiled_source = None
        max_iters = cfg["max_iterations"]
        for i in range(max_iters):
            record["iterations_to_compile"] = i + 1
            iter_started = time.monotonic()

            messages = build_messages(current_source, current_feedback)
            content, p_tok, c_tok, estimated, r_model, r_prov = call_agent(cfg, messages)
            
            if "agent_model_used" not in record and r_model:
                record["agent_model_used"] = r_model
            if "agent_provider_used" not in record and r_prov:
                record["agent_provider_used"] = r_prov
                
            record["prompt_tokens"] += p_tok
            record["completion_tokens"] += c_tok
            estimated_any = estimated_any or estimated

            candidate = parse_oda_block(content)
            if candidate is None:
                if cfg.get("calibrate"):
                    iter_detail.append({
                        "iteration": i + 1,
                        "compiles": False,
                        "parse_fail": True,
                        "completion_tokens": c_tok,
                        "wall_seconds": round(time.monotonic() - iter_started, 3),
                    })
                current_feedback = render(PARSE_FAIL_FEEDBACK)
                continue

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".oda", delete=False, encoding="utf-8"
            )
            try:
                tmp.write(candidate)
                tmp.close()
                compiled_ok, raw_fb = adapter.get_feedback(tmp.name)
            finally:
                os.unlink(tmp.name)

            if compiled_ok:
                record["compiles"] = True
                compiled_source = candidate
                if cfg.get("calibrate"):
                    iter_detail.append({
                        "iteration": i + 1,
                        "compiles": True,
                        "parse_fail": False,
                        "completion_tokens": c_tok,
                        "wall_seconds": round(time.monotonic() - iter_started, 3),
                    })
                break

            current_source = candidate
            current_feedback = render(raw_fb)
            if cfg.get("calibrate"):
                iter_detail.append({
                    "iteration": i + 1,
                    "compiles": False,
                    "parse_fail": False,
                    "completion_tokens": c_tok,
                    "wall_seconds": round(time.monotonic() - iter_started, 3),
                })

        # Correctness gate: recorded, never fed back. Build + execute the binary directly
        # so we can require stdout == expected AND a clean exit code (gaming guard).
        if compiled_source is not None:
            stdout, returncode = build_and_run(cfg, compiled_source)
            record["correct"] = (
                stdout.rstrip("\n") == expected.rstrip("\n") and returncode == 0
            )
    except Exception as exc:  # never let one trial crash the run
        record["error"] = f"{type(exc).__name__}: {exc}"

    if estimated_any:
        record["tokens_estimated"] = True
    record["wall_seconds"] = round(time.monotonic() - started, 3)
    if cfg.get("calibrate") and iter_detail:
        record["iterations_detail"] = iter_detail
    return record

# --------------------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------------------


def load_done_keys(results_path):
    """Build the resume skip-set of (case, condition, repeat) from an existing file."""
    done = set()
    if not results_path.exists():
        return done
    for line in results_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            done.add((row["case"], row["condition"], int(row["repeat"])))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return done


def main():
    parser = argparse.ArgumentParser(description="Oda correction-loop harness.")
    parser.add_argument("--calibrate", action="store_true",
                        help="Calibration mode: cap=10, per-iteration detail, "
                             "output prefixed calibration_.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Run only the first N cases (pilot).")
    parser.add_argument("--conditions", type=str, default=None,
                        help="Comma-separated conditions, e.g. structured,plain (overrides config).")
    parser.add_argument("--resume", type=str, default=None,
                        help="Append to and skip trials already present in this results file.")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG),
                        help="Path to config.yaml.")
    parser.add_argument("--corpus", type=str, default=str(DEFAULT_CORPUS),
                        help="Path to the corpus directory.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.calibrate:
        cfg["max_iterations"] = CALIBRATION_CAP
        cfg["calibrate"] = True
    else:
        cfg["calibrate"] = False
    conditions = (
        [c.strip() for c in args.conditions.split(",") if c.strip()]
        if args.conditions
        else list(cfg["conditions"])
    )
    repeats = int(cfg["repeats"])

    cases = sorted(p for p in Path(args.corpus).iterdir() if p.is_dir())
    if args.limit is not None:
        cases = cases[: args.limit]

    results_dir = REPO_ROOT / cfg["results_dir"]
    results_dir.mkdir(parents=True, exist_ok=True)
    if args.resume:
        results_path = Path(args.resume)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "calibration_" if args.calibrate else "results_"
        results_path = results_dir / f"{prefix}{stamp}.jsonl"
    done = load_done_keys(results_path)

    total = len(cases) * len(conditions) * repeats
    print(f"cases={len(cases)} conditions={conditions} repeats={repeats} "
          f"-> {total} trials | results: {results_path}")

    k = 0
    with results_path.open("a", encoding="utf-8") as out:
        for case_dir in cases:
            for condition in conditions:
                for repeat in range(repeats):
                    k += 1
                    key = (case_dir.name, condition, repeat)
                    if key in done:
                        print(f"[{k}/{total}] case={case_dir.name} cond={condition} "
                              f"rep={repeat} -> skip (already done)")
                        continue
                    record = run_trial(case_dir, condition, repeat, cfg)

                    # Flag runaway completions (calibration mode).
                    if record.get("iterations_detail"):
                        ctoks = [d["completion_tokens"]
                                 for d in record["iterations_detail"]]
                        if len(ctoks) >= 2:
                            s = sorted(ctoks)
                            mid = len(s) // 2
                            median = (s[mid] + s[~mid]) / 2
                            threshold = median * 3
                            runaways = [d["iteration"]
                                        for d in record["iterations_detail"]
                                        if d["completion_tokens"] > threshold]
                            if runaways:
                                record["runaway_iterations"] = runaways
                                print(f"  ⚠ RUNAWAY completion_tokens at "
                                      f"iteration(s) {runaways} "
                                      f"(median={median:.0f}, "
                                      f"threshold={threshold:.0f})")

                    out.write(json.dumps(record) + "\n")
                    out.flush()
                    tag = " ERROR" if "error" in record else ""
                    print(f"[{k}/{total}] case={record['case']} cond={record['condition']} "
                          f"rep={record['repeat']} -> compiles={record['compiles']} "
                          f"correct={record['correct']} "
                          f"iters={record['iterations_to_compile']}{tag}")

    print(f"done -> {results_path}")


if __name__ == "__main__":
    main()
