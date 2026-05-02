"""Lexer (tokenizer) for OdaLanguage source code."""

from __future__ import annotations
from .tokens import Token, TokenType, KEYWORDS
from .errors import LexerError


class Lexer:
    """Converts OdaLanguage source text into a stream of tokens."""

    def __init__(self, source: str, filename: str = "<source>"):
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []

    # ── helpers ──────────────────────────────────────────────

    def _ch(self) -> str:
        """Current character (empty string at EOF)."""
        return self.source[self.pos] if self.pos < len(self.source) else ""

    def _peek(self, offset: int = 1) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else ""

    def _advance(self) -> str:
        ch = self._ch()
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _match(self, expected: str) -> bool:
        if self._ch() == expected:
            self._advance()
            return True
        return False

    def _add(self, ttype: TokenType, value: str, line: int, col: int):
        self.tokens.append(Token(ttype, value, line, col))

    def _error(self, msg: str) -> LexerError:
        return LexerError(msg, self.line, self.column, self.filename)

    # ── public API ───────────────────────────────────────────

    def tokenize(self) -> list[Token]:
        while self.pos < len(self.source):
            self._scan_token()
        # Always end with EOF
        self._add(TokenType.EOF, "", self.line, self.column)
        return self.tokens

    # ── scanner ──────────────────────────────────────────────

    def _scan_token(self):
        ch = self._ch()

        # Skip spaces and tabs (NOT newlines)
        if ch in (" ", "\t", "\r"):
            self._advance()
            return

        # Newline — statement terminator
        if ch == "\n":
            line, col = self.line, self.column
            self._advance()
            # Collapse consecutive newlines and avoid leading newlines
            if self.tokens and self.tokens[-1].type not in (
                TokenType.NEWLINE, TokenType.LBRACE
            ):
                self._add(TokenType.NEWLINE, "\\n", line, col)
            return

        # Comments
        if ch == "/" and self._peek() == "/":
            if self._peek(2) == "*":
                self._skip_block_comment()
            else:
                self._skip_comment()
            return

        line, col = self.line, self.column

        # String literal
        if ch == '"':
            self._scan_string(line, col)
            return

        # Character literal
        if ch == "'":
            self._scan_char(line, col)
            return

        # Number literal
        if ch.isdigit():
            self._scan_number(line, col)
            return

        # Identifier / keyword
        if ch.isalpha() or ch == "_":
            self._scan_identifier(line, col)
            return

        # Three-char operators
        three = ch + self._peek() + self._peek(2)
        if three in _THREE_CHAR_OPS:
            self._advance(); self._advance(); self._advance()
            self._add(_THREE_CHAR_OPS[three], three, line, col)
            return

        # Two-char operators
        two = ch + self._peek()
        if two in _TWO_CHAR_OPS:
            self._advance()
            self._advance()
            self._add(_TWO_CHAR_OPS[two], two, line, col)
            return

        # One-char operators / delimiters
        if ch in _ONE_CHAR_OPS:
            self._advance()
            self._add(_ONE_CHAR_OPS[ch], ch, line, col)
            return

        raise self._error(f"Unexpected character: {ch!r}")

    # ── sub-scanners ─────────────────────────────────────────

    def _skip_comment(self):
        while self._ch() and self._ch() != "\n":
            self._advance()

    def _skip_block_comment(self):
        self._advance()  # /
        self._advance()  # /
        self._advance()  # *
        while self._ch():
            if self._ch() == "*" and self._peek() == "/" and self._peek(2) == "/":
                self._advance()  # *
                self._advance()  # /
                self._advance()  # /
                return
            self._advance()
        raise self._error("Unterminated block comment")

    def _scan_string(self, line: int, col: int):
        self._advance()  # skip opening "
        buf: list[str] = []
        while self._ch() and self._ch() != '"':
            if self._ch() == "\\":
                self._advance()
                esc = self._ch()
                if esc == "n":
                    buf.append("\n")
                elif esc == "t":
                    buf.append("\t")
                elif esc == "\\":
                    buf.append("\\")
                elif esc == '"':
                    buf.append('"')
                elif esc == "{":
                    buf.append("{")
                elif esc == "}":
                    buf.append("}")
                else:
                    buf.append(esc)
                self._advance()
            else:
                buf.append(self._advance())
        if not self._ch():
            raise self._error("Unterminated string literal")
        self._advance()  # skip closing "
        self._add(TokenType.STRING_LIT, "".join(buf), line, col)

    def _scan_char(self, line: int, col: int):
        self._advance()  # skip opening '
        if not self._ch() or self._ch() == "'":
            raise self._error("Empty or unterminated character literal")
        
        char_val = ""
        if self._ch() == "\\":
            self._advance()
            esc = self._ch()
            if esc == "n": char_val = "\\n"
            elif esc == "t": char_val = "\\t"
            elif esc == "\\": char_val = "\\\\"
            elif esc == "'": char_val = "\\'"
            elif esc == "0": char_val = "\\0"
            else: char_val = esc
            self._advance()
        else:
            char_val = self._advance()
            
        if self._ch() != "'":
            raise self._error("Unterminated character literal")
        self._advance()  # skip closing '
        self._add(TokenType.CHAR_LIT, char_val, line, col)

    def _scan_number(self, line: int, col: int):
        buf: list[str] = []
        is_float = False
        while self._ch() and (self._ch().isdigit() or self._ch() == "."):
            if self._ch() == ".":
                if self._peek().isdigit():
                    is_float = True
                    buf.append(self._advance())
                else:
                    break  # could be range operator (..)
            else:
                buf.append(self._advance())
        value = "".join(buf)
        ttype = TokenType.FLOAT_LIT if is_float else TokenType.INTEGER
        self._add(ttype, value, line, col)

    def _scan_identifier(self, line: int, col: int):
        buf: list[str] = []
        while self._ch() and (self._ch().isalnum() or self._ch() == "_"):
            buf.append(self._advance())
        word = "".join(buf)
        ttype = KEYWORDS.get(word, TokenType.IDENTIFIER)
        self._add(ttype, word, line, col)


# ── operator lookup tables ───────────────────────────────────

_TWO_CHAR_OPS: dict[str, TokenType] = {
    "==": TokenType.EQ,
    "!=": TokenType.NEQ,
    "<=": TokenType.LTE,
    ">=": TokenType.GTE,
    "&&": TokenType.AND,
    "||": TokenType.OR,
    "??": TokenType.NULLISH,
    "->": TokenType.ARROW,
    "..": TokenType.RANGE,
    "+=": TokenType.PLUS_ASSIGN,
    "-=": TokenType.MINUS_ASSIGN,
    "*=": TokenType.STAR_ASSIGN,
    "/=": TokenType.SLASH_ASSIGN,
}

_THREE_CHAR_OPS: dict[str, TokenType] = {
    "..=": TokenType.RANGE_INCLUSIVE,
}

_ONE_CHAR_OPS: dict[str, TokenType] = {
    "+":  TokenType.PLUS,
    "-":  TokenType.MINUS,
    "*":  TokenType.STAR,
    "/":  TokenType.SLASH,
    "%":  TokenType.PERCENT,
    "=":  TokenType.ASSIGN,
    "<":  TokenType.LT,
    ">":  TokenType.GT,
    "!":  TokenType.NOT,
    "?":  TokenType.QUESTION,
    "(":  TokenType.LPAREN,
    ")":  TokenType.RPAREN,
    "{":  TokenType.LBRACE,
    "}":  TokenType.RBRACE,
    "[":  TokenType.LBRACKET,
    "]":  TokenType.RBRACKET,
    ",":  TokenType.COMMA,
    ".":  TokenType.DOT,
    ":":  TokenType.COLON,
    ";":  TokenType.SEMICOLON,
}
