# Oda Compiler

## Known Issues

- (Closed by T2) Error codes and hints: Added `code` and `hint` to all `raise` sites, including `ERROR_CODES` registry.
- (Closed by T3) Crash-proofing: no input yields a Python traceback. Entry-file read errors → E4006/E4007; top-level catch-all in `main()` → single-object E5000 `InternalError` (traceback only with `ODA_DEBUG=1`). Covered by `tests/test_fuzz.py`.
- (Closed by T6) Diagnostic correctness: top-level `func main` → fail fast with `E3046` (no duplicate C `main`); undefined-identifier expressions return `ERROR_TYPE` from every error-recording `_analyze_expr` branch, so `E3033` no longer cascades a bogus `E3037` or leaks `None`. Covered by `tests/test_semantic_negative.py`.
- (Closed by T5) Codegen memory: multidim heap allocs free inner rows before the top pointer via `_oda_free_Nd` (dims tracked in `_heap_var_dims`, frees interleave per `_heap_starts`); nested `ArrayLiteral`s assigned to `T[][]` route through `_emit_array_expr` with the declared type (no `(void*)`). ASan-clean and `-Wall -Wextra -Werror`-clean. Covered by `tests/test_integration.py`.
