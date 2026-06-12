# Oda Agent Prompt Pack — v1 (token-optimized)

Usage: paste **PREAMBLE + one ticket** per agent session. One ticket per session, always.
Prompts are in English on purpose: lower token cost, better model performance.

---

## PREAMBLE (paste at top of every session)

```
Project: OdaLanguage compiler (Python transpiler, Oda → C) in src/oda/.
Read .agents/oda-compiler/SKILL.md (or SKILL.md in repo root) FIRST. It is authoritative:
architecture, invariants, file responsibilities, C output conventions. Do not violate it.

Hard rules:
- TDD: write failing tests FIRST, show them run red, then implement, then run full suite green.
- Output patches only (unified diff). Never reprint whole files. Never paste unchanged code.
- Scope = this ticket only. No refactors, no drive-by fixes, no new features.
- Syntax is frozen. Never propose keyword/grammar changes.
- After all tests pass: update the "Known Issues" table in SKILL.md if this ticket closes an entry.
- Final message = (1) diff summary, (2) test command + result line, (3) one-line SKILL.md delta. Nothing else.
- If blocked or uncertain, ask ONE precise question instead of guessing.

Commands: make test | make test-asan | UPDATE_GOLDENS=1 pytest tests/test_examples.py
```

---

## T1 — Multi-error reporting (highest impact)

```
Goal: one compile run must report ALL parser+semantic errors as a JSON array, not just the first.
Fail-fast stays: no C is emitted if any error exists.

Tasks (in order):
1. tests/test_integration.py: add tests asserting that a source file with 3 distinct
   semantic errors (undefined var, private access, arity mismatch) yields a JSON array
   of length 3 via `--output-format=json`, exit code 1, and no .c output file.
   Add one parser-recovery test: 2 syntax errors in separate statements → 2 JSON errors.
2. parser.py: add error recovery. On ParserError inside statement parsing, record the
   error and synchronize to the next statement boundary (NEWLINE/SEMICOLON at brace
   depth of the statement, or matching RBRACE). Cap at 25 errors, then stop.
3. semantic.py: convert `_err(...)` raise-sites to collect into ErrorReporter; raise
   aggregate at end of analysis. Skip analysis of subtrees whose types are already
   poisoned (introduce an internal "error" type that silences cascading errors).
4. main.py/errors.py: emit collected errors sorted by (file, line, column).

Constraints:
- No cascade spam: one root cause ≈ one error. The poisoned-type rule is mandatory.
- Existing single-error tests must keep passing unchanged.
```

---

## T2 — Error codes + hint field

```
Goal: every diagnostic gets a stable code (E####) and an optional machine-actionable hint.

Tasks (in order):
1. tests: assert JSON errors contain `code` matching ^E\d{4}$ and, for these three cases,
   a non-empty `hint`:
   - int→uint implicit assignment → hint suggests `as uint`
   - private member access → hint names the owning class
   - guard else block missing scope exit → hint lists return/break/continue
2. errors.py: add `code` and `hint: str|None` to OdaError + JSON serializer.
   Create ERROR_CODES registry (dict code → short description) in errors.py.
   Ranges: E1xxx lexer, E2xxx parser, E3xxx semantic, E4xxx import, E5xxx codegen-internal.
3. Assign codes to ALL existing raise-sites. Hints only where a fix is mechanically
   derivable — never speculative.

Constraints:
- Codes are append-only and never reused. Add a unit test that asserts no duplicate codes.
- Message text stays short; hint carries the fix. Do not pad messages.
```

---

## T3 — No-crash guarantee (fuzz)

```
Goal: NO input may ever produce a Python traceback. Every failure becomes a structured
OdaError (JSON-serializable). A traceback in an agent loop is the most expensive failure mode.

Tasks (in order):
1. tests/test_fuzz.py (new):
   a) seeded random token-soup generator (random.Random(1337)), 300 cases, each ≤40 tokens
      drawn from all TokenTypes with plausible values → run full pipeline via subprocess
      `./oda transpile <file> --output-format=json` → assert exit code in {0,1} and
      stderr/stdout parses as JSON when exit==1. Never assert specific messages.
   b) 30 mutation cases: take examples/*.oda, randomly delete/duplicate one line.
   c) edge corpus: empty file, only newlines, unterminated string, unmatched braces ×50,
      10k-char identifier, non-UTF8 bytes, null byte.
2. Run; for every traceback found, wrap the failing site in a proper OdaError with a code
   from T2 ranges (E5xxx for internal invariant violations: "Internal compiler error",
   include phase name).
3. main.py: top-level catch-all → exit 1 + single JSON error object {code:"E5000",
   error_type:"InternalError", message: exception class + 1-line summary}. No traceback
   on stderr unless ODA_DEBUG=1.

Constraints: fuzz tests must be deterministic (fixed seed) and run in <30s total.
```

---

## T4 — ODA_SPEC.md (compact spec for code-writing agents)

```
Goal: a single ODA_SPEC.md (~2.5K tokens max) that lets an agent write correct Oda code
with ZERO other context. This is for agents WRITING .oda code, not compiler devs.

Source of truth: README.md syntax tour, docs/, examples/*.oda. Verify every claim by
actually running `./oda run` on a snippet before including it — no untested syntax.

Required sections, in this order, terse table/snippet style, no prose paragraphs:
1. Types: int, uint(5u), float, bool, string, T?, T[], enums. Widening table. Cast syntax
   (`as`, `(type)`). What is NOT allowed (implicit narrowing, int→uint).
2. Variables: decl, `stay`, `_` privacy rule.
3. Functions: decl, `ref` params (call site &-free — show exact call syntax), return rules.
4. Control flow: if/else, while, for-in (range `..`/`..=`/step), C-style for, match
   (int/string/enum + `_` arm), infinite `for {}`.
5. Null safety: `?`, `??`, full guard/when shape including the mandatory scope-exit rule.
6. Classes: fields, construct/destruct signatures, RAII semantics (one sentence), method calls.
7. Imports: import std.math / from x import y, what std provides today.
8. Pitfalls: top 8 errors agents actually hit, each as "WRONG → RIGHT" one-liner pairs.
   Derive them from semantic.py raise-sites.
9. Compiler interface: ./oda run|build|transpile, --output-format=json error shape
   (one example object).

Acceptance: feed ODA_SPEC.md alone to a fresh model session, ask it to write a program
using classes+guard+match+ref; it must compile with ./oda build on first or second try.
Token budget is hard: if over ~2.5K tokens, cut prose, keep tables and code.
```

---

## T5 — Memory bug closure (multidim free + ArrayLiteral void*)

```
Goal: close the two open codegen memory issues from SKILL.md Known Issues.

Tasks (in order):
1. tests/test_integration.py: add an ASan-sensitive test: function allocating
   `new int[3][4]`, writing/reading cells, scope exit → compile with
   ODA_TEST_CFLAGS="-fsanitize=address -g" semantics (reuse existing TEST_CFLAGS hook),
   run, assert clean exit (ASan would fail the run on leak/UAF).
   Add a test that a nested ArrayLiteral assigned to int[][] produces no `(void*)`
   in generated C and compiles under -Wall -Wextra -Werror.
2. codegen.py `_emit_heap_cleanup_from`: for multidim allocations, free inner rows
   before the top pointer. Track dimensionality alongside var name in _heap_vars
   (extend entry to a small tuple/dataclass — keep the stack discipline identical).
3. codegen.py `_expr` ArrayLiteral path: route nested literals through _emit_array_expr
   with the declared type context instead of (void*).
4. Run UPDATE_GOLDENS=1 pytest tests/test_examples.py; include golden diffs in the patch.
5. Run make test-asan; paste the one-line result.

Constraints: RAII ordering invariant (reverse scope order) must not change for class
destructors; heap frees interleave per existing _heap_starts snapshots.
```

---

## Tool-specific notes

**Claude Code** — strengths: long agentic runs, reliable test-loop discipline.
- Add to PREAMBLE: `Use subagents only for read-only exploration; all edits in main thread.`
- Let it run `make test` itself; don't ask it to reason about correctness without running.
- T1 and T5 are the best fits (multi-file, invariant-heavy).

**Antigravity IDE / Gemini Pro** — strengths: fast single-file edits, cheap exploration.
- Best fits: T2 (mechanical, registry-style), T4 (doc synthesis), fuzz corpus of T3.
- Add to PREAMBLE: `If a diff touches >3 files, stop and list the plan first.`
  (Guards against Gemini's tendency to over-edit.)
- Verify its diffs apply cleanly before accepting; ask for `git apply --check` output.

**Cross-check pattern (your existing workflow):**
Implement with one tool → paste only the DIFF + failing/passing test output to the other
tool with: `Review this diff against SKILL.md invariants. List violations only. No praise,
no restating the diff.` That last sentence alone saves ~30% of review tokens.

---

## Session-ending micro-prompt (paste when a ticket is done)

```
Close-out: 1) `git diff --stat`. 2) Exact test command + last line of output.
3) SKILL.md Known Issues delta as a one-line diff. 4) Anything you noticed but did
NOT fix, as a one-line backlog item each. No other text.
```
