"""Token type definitions for the OdaLanguage lexer."""

from enum import Enum, auto
from dataclasses import dataclass


class TokenType(Enum):
    # ── Literals ──────────────────────────────────────────────
    INTEGER     = auto()
    FLOAT_LIT   = auto()
    STRING_LIT  = auto()
    IDENTIFIER  = auto()

    # ── Type keywords ────────────────────────────────────────
    INT         = auto()
    UINT        = auto()
    FLOAT       = auto()
    CHAR        = auto()
    STRING      = auto()
    BOOL        = auto()

    # ── Modifier keywords ────────────────────────────────────
    STAY        = auto()   # immutability
    REF         = auto()   # pass-by-reference

    # ── Declaration keywords ─────────────────────────────────
    FUNC        = auto()
    CLASS       = auto()
    CONSTRUCT   = auto()
    DESTRUCT    = auto()

    # ── Control flow keywords ────────────────────────────────
    IF          = auto()
    ELSE        = auto()
    WHILE       = auto()
    FOR         = auto()
    IN          = auto()
    MATCH       = auto()
    RETURN      = auto()
    BREAK       = auto()
    CONTINUE    = auto()
    STEP        = auto()
    REVERSED    = auto()

    # ── Module keywords ──────────────────────────────────────
    IMPORT      = auto()
    FROM        = auto()
    AS          = auto()

    # ── Error handling keywords ──────────────────────────────
    GUARD       = auto()
    ERR         = auto()

    # ── Boolean / null literals ──────────────────────────────
    TRUE        = auto()
    FALSE       = auto()
    NULL        = auto()

    # ── Arithmetic operators ─────────────────────────────────
    PLUS        = auto()   # +
    MINUS       = auto()   # -
    STAR        = auto()   # *
    SLASH       = auto()   # /
    PERCENT     = auto()   # %

    # ── Assignment operators ─────────────────────────────────
    ASSIGN      = auto()   # =
    PLUS_ASSIGN = auto()   # +=
    MINUS_ASSIGN = auto()  # -=
    STAR_ASSIGN = auto()   # *=
    SLASH_ASSIGN = auto()  # /=

    # ── Comparison operators ─────────────────────────────────
    EQ          = auto()   # ==
    NEQ         = auto()   # !=
    LT          = auto()   # <
    GT          = auto()   # >
    LTE         = auto()   # <=
    GTE         = auto()   # >=

    # ── Logical operators ────────────────────────────────────
    AND         = auto()   # &&
    OR          = auto()   # ||
    NOT         = auto()   # !

    # ── Special operators ────────────────────────────────────
    NULLISH     = auto()   # ??
    ARROW       = auto()   # ->
    RANGE       = auto()   # ..
    RANGE_INCLUSIVE = auto() # ..=
    QUESTION    = auto()   # ?

    # ── Delimiters ───────────────────────────────────────────
    LPAREN      = auto()   # (
    RPAREN      = auto()   # )
    LBRACE      = auto()   # {
    RBRACE      = auto()   # }
    LBRACKET    = auto()   # [
    RBRACKET    = auto()   # ]
    COMMA       = auto()   # ,
    DOT         = auto()   # .
    COLON       = auto()   # :
    SEMICOLON   = auto()   # ;

    # ── Meta ─────────────────────────────────────────────────
    NEWLINE     = auto()
    EOF         = auto()


# ── Keyword lookup table ─────────────────────────────────────
KEYWORDS: dict[str, TokenType] = {
    "int":       TokenType.INT,
    "uint":      TokenType.UINT,
    "float":     TokenType.FLOAT,
    "char":      TokenType.CHAR,
    "string":    TokenType.STRING,
    "bool":      TokenType.BOOL,
    "stay":      TokenType.STAY,
    "ref":       TokenType.REF,
    "func":      TokenType.FUNC,
    "class":     TokenType.CLASS,
    "construct": TokenType.CONSTRUCT,
    "destruct":  TokenType.DESTRUCT,
    "if":        TokenType.IF,
    "else":      TokenType.ELSE,
    "while":     TokenType.WHILE,
    "for":       TokenType.FOR,
    "in":        TokenType.IN,
    "match":     TokenType.MATCH,
    "return":    TokenType.RETURN,
    "break":     TokenType.BREAK,
    "continue":  TokenType.CONTINUE,
    "import":    TokenType.IMPORT,
    "from":      TokenType.FROM,
    "as":        TokenType.AS,
    "guard":     TokenType.GUARD,
    "err":       TokenType.ERR,
    "true":      TokenType.TRUE,
    "false":     TokenType.FALSE,
    "null":      TokenType.NULL,
    "step":      TokenType.STEP,
    "reversed":  TokenType.REVERSED,
}

# Token types that represent Oda type names
TYPE_TOKENS = {
    TokenType.INT, TokenType.UINT, TokenType.FLOAT,
    TokenType.CHAR, TokenType.STRING, TokenType.BOOL,
}


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"
