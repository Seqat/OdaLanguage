# Project: OdaLanguage compiler (Python transpiler, Oda → C) in src/oda/

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
