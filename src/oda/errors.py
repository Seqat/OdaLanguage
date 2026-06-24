"""Error types and reporting for the OdaLanguage compiler."""

from __future__ import annotations


class OdaError(Exception):
    """Base error for all compiler errors."""

    def __init__(self, message: str, line: int = 0, column: int = 0,
                 filename: str = "<source>", code: str | None = None):
        self.message = message
        self.line = line
        self.column = column
        self.filename = filename
        self.code = code
        super().__init__(self.format())

    def format(self) -> str:
        prefix = f"[{self.code}] " if self.code else ""
        return f"{self.filename}:{self.line}:{self.column}: error: {prefix}{self.message}"


class LexerError(OdaError):
    """Raised when the lexer encounters invalid input."""
    pass


class ParserError(OdaError):
    """Raised when the parser encounters unexpected tokens."""
    pass


class SemanticError(OdaError):
    """Raised when semantic analysis detects an error."""
    pass


class CodegenError(OdaError):
    """Raised when code generation fails."""
    pass


class ErrorReporter:
    """Collects and reports compilation errors."""

    def __init__(self):
        self.errors: list[OdaError] = []
        self.warnings: list[str] = []

    def error(self, err: OdaError) -> None:
        self.errors.append(err)

    def warn(self, msg: str, line: int = 0, column: int = 0) -> None:
        self.warnings.append(f"  warning ({line}:{column}): {msg}")

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def dump(self) -> None:
        for w in self.warnings:
            print(w)
        for e in self.errors:
            print(e.format())
        if self.errors:
            print(f"\n  ✗ {len(self.errors)} error(s) found. Compilation aborted.")
