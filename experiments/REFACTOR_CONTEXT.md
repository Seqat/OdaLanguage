# Oda Harness Refactor — Shared Context

> **Read this first.** Canonical brief for the `experiments/` LLM self-correction benchmark
> refactor. This is the harness that measures **structured vs plain compiler diagnostics**
> inside an LLM correction loop (UBMK 2026). It is NOT the Oda compiler (`src/oda/`) — do not
> touch `src/oda/` for any ticket described here.
>
> Every refactor session (Claude Code `P#`, Google Antigravity `G#`) reads this file before
> doing anything else.

## 1. Diagnosis (from the rep5 calibration logs)

1. **Parse-failure deadlock (~30% of agent iterations).** The model emits prose / explanation
   that the code extractor can't parse. Under `temperature=0` this is a **deterministic
   deadlock**: the same unparseable ~32-token output is re-emitted every iteration, identical
   across all 5 repeats, burning the entire 10-iteration budget. Worst case
   `e3015_nullable_simple` ≈ **96% parse_fail**.
2. **Semantically-wrong-but-compiles cases.** A separate set compiles cleanly but is wrong —
   genuine misunderstanding of Oda semantics, not a formatting problem.
3. **One infrastructure-dead run.** 29/30 trials returned **HTTP 400 at request time → 0
   iterations**. Nothing was actually measured.
4. **parse_fail rate differs by condition** (structured **27%** vs plain **34%**) — a
   **validity confound**: the conditions are supposed to differ only in diagnostic content, so
   a systematic parse-rate gap threatens the structured-vs-plain comparison.

## 2. File map (exact paths + line refs)

All paths relative to repo root. Line numbers are current as of this brief; re-confirm before
editing.

### Code extractor (model output → Oda program)
- **`experiments/correction_loop.py:150-163`** — `parse_oda_block(text)`. Requires exactly one
  ` ```oda ` opening fence; closing fence optional (consumed by the stop sequence). Returns
  `None` when absent/ambiguous → this is what counts as a **parse_fail**.
- `experiments/correction_loop.py:145-147` — the fence regexes (`_ODA_OPEN_RE`,
  `_ODA_CLOSE_RE`) and the cheap `_TOKEN_RE`.
- `experiments/correction_loop.py:85` — `PARSE_FAIL_FEEDBACK` (the message fed back on a parse
  failure).
- `experiments/correction_loop.py:92` — `CHAT_STOP` (` ```\n ` stop sequence that trims
  trailing rambling).
- `experiments/correction_loop.py:351-362` — where the loop handles `candidate is None`
  (records the parse_fail in calibration mode, re-feeds `PARSE_FAIL_FEEDBACK`, `continue`).
  **This is the deadlock site (Problem 1):** no detection of repeated-identical output.

### Correction loop (the iterate-to-clean-compile engine)
- **`experiments/correction_loop.py:300-413`** — `run_trial(case_dir, condition, repeat, cfg)`.
  One full correction loop; always returns a record, never raises.
  - `335-396` — the `for i in range(max_iters)` iteration loop.
  - `339-349` — build messages, call agent, accumulate tokens / model+provider used.
  - `364-372` — write candidate to temp file, run the condition's adapter to get `compiled_ok`.
  - `374-385` — clean-compile success path (`break`).
  - `387-388` — failure path: feed the new diagnostic back.
  - `398-404` — correctness gate (build + run binary, compare stdout AND exit code).
- `experiments/correction_loop.py:190-256` — `call_agent(cfg, messages)`. OpenAI-compatible
  POST. **Retries only on HTTP 429** (`228-239`); **any 400 raises (Problem 3)**. `.env`
  OpenRouter key parsing at `207-221`.
- `experiments/correction_loop.py:259-293` — `build_and_run(cfg, candidate_src)` (correctness
  gate; uses `./oda build` then execs the binary to capture stdout + exit code).
- `experiments/correction_loop.py:171-187` — `build_messages(program, feedback)` (single-pass
  substitution; splits `AGENT_SYSTEM` into system/user).

### Agent system prompt / condition templates
- **`experiments/correction_loop.py:57-70`** — `AGENT_SYSTEM`. **The single shared template,
  byte-identical for both conditions.** Contains `{PROGRAM}` and `{FEEDBACK}`.
- **`experiments/correction_loop.py:79-82`** — `FEEDBACK_RENDER`. Both `structured` and `plain`
  map to **identity lambdas** (`lambda raw: raw`). The ONLY per-condition difference is the raw
  string each adapter returns for `{FEEDBACK}`.
- `experiments/correction_loop.py:50` — `ADAPTERS = {"structured": ..., "plain": ...}` wiring.
- **`experiments/adapters/oda_structured.py:5-35`** — `get_feedback()`: returns the full JSON
  diagnostics string verbatim.
- **`experiments/adapters/oda_plain.py:15-48`** — `get_feedback()`: same compiler invocation
  and same `compiled_ok` logic, but degrades feedback to the bare `message` of the first
  diagnostic (strips code/line/column).

### Results aggregation
- **`experiments/analyze.py:1-3`** — **stub only** (a comment telling you to load the JSONL
  manually). No real aggregation exists yet.
- `experiments/correction_loop.py:305-315` — the per-trial record schema.
- `experiments/correction_loop.py:354-360`, `378-384`, `390-396` — `iterations_detail`
  (per-iteration calibration records, incl. the `parse_fail` flag).
- `experiments/correction_loop.py:499-515` — runaway-completion flag (calibration).
- `experiments/correction_loop.py:517-518` — the JSONL write (one record per line).
- `experiments/correction_loop.py:420-434` — `load_done_keys()` (resume skip-set).
- `experiments/results/*.jsonl` — raw trial logs; `experiments/results/*.log` — run consoles
  (e.g. `calibration_openrouter_rep5.log`, the rep5 source of this diagnosis).

### Config
- `experiments/config.yaml` — `agent_model` (L1), `temperature: 0.0` (L3), `max_tokens` (L4),
  `max_iterations` / k_max (L6), `repeats` / M (L7), `conditions` (L8).
- `experiments/correction_loop.py:98` — `CALIBRATION_CAP = 10` (the `--calibrate` cap that
  raised k to 10 for the rep5 run).

## 3. Do structured and plain share ONE prompt template?

**YES — explicitly.** They share `AGENT_SYSTEM` (`correction_loop.py:57-70`) byte-for-byte.
The only thing that varies between conditions is the substituted `{FEEDBACK}` text, produced by
the condition's adapter (`oda_structured` vs `oda_plain`) and passed through an **identity**
`FEEDBACK_RENDER` lambda (`correction_loop.py:79-82`). No condition-specific label, prefix, or
wrapping is ever added. On a parse failure, **both** conditions re-feed the same
`PARSE_FAIL_FEEDBACK` (`correction_loop.py:85`, identity-rendered).

**Implication for P3:** the shared template already exists — P3 does **not** create one. P3's
job is to (a) keep the sharing structurally enforced so it can't drift, and (b) neutralize the
parse_fail confound (Problem 4) so the 27% vs 34% gap is attributable to feedback *content*
alone, never to template divergence.

## 4. THE INVARIANT (all sessions obey)

> **Any prompt/loop change must apply identically to `structured` and `plain`; they may differ
> ONLY in the diagnostic block (the substituted `{FEEDBACK}` content).**

Concretely: no edit to `AGENT_SYSTEM`, `build_messages`, `parse_oda_block`,
`PARSE_FAIL_FEEDBACK`, `CHAT_STOP`, the iteration loop, the correctness gate, the token
accounting, or the config may be conditioned on `condition`. The adapters
(`oda_structured.py` / `oda_plain.py`) are the **sole** place the two conditions are allowed to
diverge, and only in the feedback string — never in `compiled_ok`, never in the compiler
invocation. Any PR that violates this confounds the experiment and must be rejected at review.

## 5. Ticket DAG and merge order

**Convention:** `P# = Claude Code` tickets, `G# = Google Antigravity` tickets. **Both are work
tickets** (not review gates). Canonical ticket text lives in the originating Claude session;
the *scopes* below are **inferred from the diagnosis** and must be reconciled with that source
before work starts.

**Merge order (DAG):**

```
P0 ──▶ G1 ──▶ P1 ──┬─▶ P2 ──┐
                   └─▶ P3 ──┴─▶ G2 ──▶ G3
```

- `P0` first.
- `G1` after `P0`.
- `P1` after `G1`.
- `P2` and `P3` in parallel, both after `P1`.
- `G2` after both `P2` and `P3`.
- `G3` last.

**Inferred scope per ticket (RECONCILE WITH SOURCE — do not treat as authoritative):**

| Ticket | Tool | Likely target (from diagnosis) |
|---|---|---|
| `P0` | Claude Code | **Problem 3** — make `call_agent` survive/handle non-429 errors (HTTP 400) instead of nuking the trial at 0 iterations; foundation so later runs actually execute. |
| `G1` | Antigravity | Re-run smoke calibration to confirm trials execute end-to-end (no mass HTTP 400); capture a clean baseline. |
| `P1` | Claude Code | **Problem 1** — break the parse-fail deterministic deadlock: harden `parse_oda_block` recovery AND add repeated-identical-output detection in the loop so temp=0 stops burning the full budget. (Condition-blind — see Invariant.) |
| `P2` | Claude Code | **Problem 2** — semantically-wrong-but-compiles cases (corpus triage and/or minimal Oda primer). Must apply identically to both conditions. |
| `P3` | Claude Code | **Problem 4 + Invariant** — lock the shared template structurally and neutralize the parse_fail confound (NOT create a template — it already exists; see §3). |
| `G2` | Antigravity | Invariant audit + re-run: verify P2/P3 changes apply identically to both conditions; re-calibrate. |
| `G3` | Antigravity | Final full re-calibration + validity sign-off: deadlock no longer burns budget, parse_fail confound resolved, structured-vs-plain comparison clean. |

## 6. Hard rules

- **Scope:** edit only under `experiments/`. Never touch `src/oda/` (the compiler is a fixed
  control variable for this experiment).
- **Invariant (§4):** every change applies identically to both conditions; only the diagnostic
  block may differ.
- **Adapters only:** the two conditions diverge solely in `oda_structured.py` /
  `oda_plain.py`, and only in the feedback string.
- **Reconcile ticket scopes (§5)** against the originating session before starting a ticket.
