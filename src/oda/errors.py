"""Error types and reporting for the OdaLanguage compiler."""

from __future__ import annotations

import json
import sys
from typing import TextIO


class OdaError(Exception):
    """Base error for all compiler errors."""

    def __init__(self, message: str, line: int = 0, column: int = 0,
                 filename: str = "<source>"):
        self.message = message
        self.line = line
        self.column = column
        self.filename = filename
        super().__init__(self.format())

    def format(self) -> str:
        return f"{self.filename}:{self.line}:{self.column}: error: {self.message}"

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.filename,
            "line": self.line,
            "column": self.column,
            "error_type": type(self).__name__,
            "message": self.message,
        }


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

    def dump(self, output_format: str = "text", stream: TextIO | None = None) -> None:
        stream = stream or sys.stdout
        if output_format == "json":
            print(format_errors_json(self.errors), file=stream)
            return
        for w in self.warnings:
            print(w, file=stream)
        for e in self.errors:
            print(e.format(), file=stream)
        if self.errors:
            print(f"\n  ✗ {len(self.errors)} error(s) found. Compilation aborted.", file=stream)


def format_errors_json(errors: list[OdaError]) -> str:
    return json.dumps([err.to_dict() for err in errors], indent=2)
