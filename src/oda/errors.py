"""Error types and reporting for the OdaLanguage compiler."""

from __future__ import annotations

import json
import sys
from typing import TextIO


class OdaError(Exception):
    """Base error for all compiler errors."""

    def __init__(self, message: str, line: int = 0, column: int = 0,
                 filename: str = "<source>", code: str = "E0000", hint: str | None = None):
        self.message = message
        self.line = line
        self.column = column
        self.filename = filename
        self.code = code
        self.hint = hint
        super().__init__(self.format())


    def format(self) -> str:
        return f"{self.filename}:{self.line}:{self.column}: error: {self.message}"

    def to_dict(self) -> dict[str, object]:
        d = {
            "file": self.filename,
            "line": self.line,
            "column": self.column,
            "error_type": type(self).__name__,
            "message": self.message,
            "code": self.code,
        }
        if self.hint is not None:
            d["hint"] = self.hint
        return d

ERROR_CODES = {
    "E0000": "Unknown error",
    # Lexer errors (E1xxx)
    "E1001": "Unexpected character",
    "E1002": "Unterminated block comment",
    "E1003": "Unterminated string literal",
    "E1004": "Empty or unterminated character literal",
    "E1005": "Unterminated character literal",
    # Parser errors (E2xxx)
    "E2001": "Expected token not found",
    "E2002": "Expected type not found",
    "E2003": "Expected comma or newline after enum variant",
    "E2004": "Expected module path component",
    "E2005": "Expected type after 'new'",
    "E2006": "Expected array dimensions after type in 'new'",
    "E2007": "Unexpected token",
    "E2008": "Unterminated interpolation expression",
    "E2009": "Empty interpolation expression",
    # Semantic errors (E3xxx)
    "E3001": "Cannot coerce expression type to variable type",
    "E3002": "Guard else block must exit the current scope",
    "E3003": "Class has no such member",
    "E3004": "Cannot iterate over unknown-size collection",
    "E3005": "Function must return expected type",
    "E3006": "Cannot return a void value",
    "E3007": "Cannot return actual type from function returning expected type",
    "E3008": "break/continue cannot be used outside a loop",
    "E3009": "Unknown error type in catch block",
    "E3010": "Match pattern type does not match expression type",
    "E3011": "Unknown parameter type",
    "E3012": "Duplicate parameter name",
    "E3013": "Unknown base type in declaration",
    "E3014": "Cannot assign a void value to a variable",
    "E3015": "Cannot assign null to non-nullable type",
    "E3016": "Unknown return type in function declaration",
    "E3017": "Not all code paths return a value",
    "E3018": "Duplicate enum variant name",
    "E3019": "Cannot pass argument as ref of expected type",
    "E3020": "Cannot pass argument to parameter of incompatible type",
    "E3021": "print expects 0 or 1 argument",
    "E3022": "print does not accept ref arguments",
    "E3023": "Function called with incorrect number of arguments",
    "E3024": "Parameter must be passed with 'ref'",
    "E3025": "Cannot pass non-assignable expression as 'ref'",
    "E3026": "Parameter must not be passed with 'ref'",
    "E3027": "Parameter is not a ref parameter",
    "E3028": "Undefined function",
    "E3029": "Cannot call method on non-class type",
    "E3030": "Class has no such method",
    "E3031": "Unsupported call target",
    "E3032": "Unknown private field in class",
    "E3033": "Undefined variable",
    "E3034": "Cannot reassign immutable variable",
    "E3035": "Cannot modify element of immutable array",
    "E3036": "Cannot use void expression in binary operation",
    "E3037": "Invalid operands for binary operator",
    "E3038": "Cannot use void function call as an argument",
    "E3039": "Enum has no such variant",
    "E3040": "Unknown private member",
    "E3041": "Array index must be an integer expression",
    "E3042": "Array dimensions must be integer expressions",
    "E3043": "Unknown cast target type",
    "E3044": "Cannot cast to non-scalar type",
    "E3045": "Cannot cast types",
    "E3046": "Oda program must not have a 'main' function",
    # Import/IO errors (E4xxx)
    "E4001": "Module not found",
    "E4002": "Import error",
    "E4003": "Cannot import private member",
    "E4004": "Import error",
    "E4005": "Cannot access private member of module",
    "E4006": "Cannot read source file",
    "E4007": "Source file is not valid UTF-8",
    # Internal & Codegen errors (E5xxx)
    "E5000": "Internal compiler error",
    "E5001": "C compiler rejected generated output",
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


class OdaErrorGroup(OdaError):
    """Aggregate of several compiler errors raised at the end of a phase."""

    def __init__(self, errors: list[OdaError]):
        self.errors = sort_errors(errors)
        first = self.errors[0]
        super().__init__(f"{len(self.errors)} error(s) found",
                         first.line, first.column, first.filename)


def sort_errors(errors: list[OdaError]) -> list[OdaError]:
    return sorted(errors, key=lambda e: (e.filename, e.line, e.column))


def flatten_errors(errors: list[OdaError]) -> list[OdaError]:
    flat: list[OdaError] = []
    for err in errors:
        flat.extend(err.errors if isinstance(err, OdaErrorGroup) else [err])
    return sort_errors(flat)


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
