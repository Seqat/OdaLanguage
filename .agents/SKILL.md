# Oda Compiler

## Known Issues (Closed)

- (Closed by T2) Error codes and hints: Added `code` and `hint` to all `raise` sites, including `ERROR_CODES` registry.
- (Closed by T3) Crash-proofing: no input yields a Python traceback. Entry-file read errors → E4006/E4007; top-level catch-all in `main()` → single-object E5000 `InternalError` (traceback only with `ODA_DEBUG=1`). Covered by `tests/test_fuzz.py`.
- (Closed by T6) Diagnostic correctness: top-level `func main` → fail fast with `E3046` (no duplicate C `main`); undefined-identifier expressions return `ERROR_TYPE` from every error-recording `_analyze_expr` branch, so `E3033` no longer cascades a bogus `E3037` or leaks `None`. Covered by `tests/test_semantic_negative.py`.
- (Closed by T5) Codegen memory: multidim heap allocs free inner rows before the top pointer via `_oda_free_Nd` (dims tracked in `_heap_var_dims`, frees interleave per `_heap_starts`); nested `ArrayLiteral`s assigned to `T[][]` route through `_emit_array_expr` with the declared type (no `(void*)`). ASan-clean and `-Wall -Wextra -Werror`-clean. Covered by `tests/test_integration.py`.
- (Closed by T7) Reliability: propagated exit code in `run`, optimized fuzz suite duration to <3s, populated `ERROR_CODES` registry with one-line descriptions.
- (Closed by T9) break/continue RAII: each loop emitter pushes a `(_destructors, _heap_vars)` marker onto `_loop_starts` around the single body emission; `Break`/`Continue` emit destructor calls top→innermost-loop marker then `_emit_heap_cleanup_from(..., pop=False)` before the jump (path-based, no pop, mirroring the return path). Covered by `tests/test_integration.py`.
- (Closed by T10) return-path UAF: the `ReturnStatement` branch passes `skip=<returned identifier name>` into `_emit_heap_cleanup_from(..., pop=False, skip=...)`, so the returned heap lvalue is no longer freed before `return` (ownership transfers out). Bug B: `semantic.py` `_analyze_func` rejects returning a class with heap fields by value via `E3047` (reuses `_class_contains_heap_storage`). Covered by `tests/test_integration.py` + `tests/test_semantic_negative.py`.

## Open Issues (verified, not yet fixed)

These were confirmed by hand against the codebase. Each has an exact repro in the audit
ticket pack. Do NOT reintroduce or rely on the broken behavior; if a ticket touches a
nearby path, respect the intended fix direction below.

- **(T10 ownership gap, pre-arena) string ownership across calls leaks.** With the UAF closed, a returned heap string's ownership transfers out but the caller never frees the result (`callee allocates, program-level cleanup later`). A leak is accepted v1 behavior; revisit when an arena/ownership model lands.
- **(T11, HIGH) type-soundness trio.** (a) `??` does not strip nullability — `infer_binary_type` returns `left or right`, so `string s = n ?? "x"` is rejected with E3001. (b) String `==`/`!=` lower to pointer comparison instead of `strcmp`. (c) Nullable values reach `print`/interpolation/concat unguarded → `printf("%s", NULL)`. Intended fix: strip trailing `?` in `??`; emit `strcmp` for string equality; reject unguarded nullable at those sites.
- **(T11 decision) value-type nullable has no C representation.** `int? x = null` lowers to `int x = NULL;`. `?` only truly works for heap types. Pending decision: restrict `?` to string/class types in v1 (recommended, fail-fast) vs. boxed representation (v2).
- **(T12, HIGH) `stay` aliasing loophole.** Immutability does not flow through calls; a `stay int[]` passed to an `int[]` or `ref` parameter can be mutated by the callee (arrays alias their storage in C). Intended fix: reject passing an immutable identifier as a ref param or as an array param (even by value).
- **(T13, MEDIUM) interpolation diagnostics report line 1.** `_parse_interpolated` re-lexes `{expr}` with a fresh `Lexer` seeded at line 1, so errors inside interpolations report the wrong line. Intended fix: thread `start_line`/`start_column` into `Lexer`.
- **(T14, MEDIUM) robustness batch.** Alias `MemberAccess` rewrite only handles `callee`/`expr` attrs (privacy-check + rewrite bypass elsewhere, e.g. inside `BinaryExpr`); class bodies silently `_advance()` past unknown tokens (drops `stay` fields, no error); runtime helpers (`_oda_int_to_str`, `_oda_float_to_str`, `_oda_alloc_Nd`) don't NULL-check malloc, and `_oda_read_file` ignores `ftell` < 0 and the `fread` result; `_compile_command` lacks `-fwrapv` (signed overflow UB); importer `read_text` OSError surfaces as E5000 instead of E4006.

## Backlog (no ticket yet)

- `stay` class instances can still be mutated via methods (`self` is ref).
- Match-arm pattern preludes can land inside the previous arm's body if a pattern allocates (only interpolated-string patterns trigger this today).
- Optional parser nesting-depth cap for friendlier-than-E5000 errors on pathological input.

## Verified-SAFE (audit claims that do NOT reproduce — do not open tickets)

- Multidim partial-init double-free: `_oda_free_Nd` is NULL-safe; only an OOM leak existed (folded into T14).
- guard + deeply nested return: RAII/free ordering is correct (see golden `guard_io`).
- Heap-temp escape in nested call arguments: statement-level capture frees all child temps after the statement.
- E5000 bypass incl. `RecursionError` on deep expressions: the top-level catch-all holds and exits 1 with structured JSON.
