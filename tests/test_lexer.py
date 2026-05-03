import pytest

from src.oda.errors import LexerError
from src.oda.lexer import Lexer
from src.oda.tokens import TokenType


def token_types(source):
    return [tok.type for tok in Lexer(source).tokenize()]


def tokens_without_eof(source):
    return Lexer(source).tokenize()[:-1]


def test_lexes_keywords_identifiers_and_literals():
    tokens = tokens_without_eof('stay int speed = 100\nstring name = "Oda"')

    assert [tok.type for tok in tokens] == [
        TokenType.STAY,
        TokenType.INT,
        TokenType.IDENTIFIER,
        TokenType.ASSIGN,
        TokenType.INTEGER,
        TokenType.NEWLINE,
        TokenType.STRING,
        TokenType.IDENTIFIER,
        TokenType.ASSIGN,
        TokenType.STRING_LIT,
    ]
    assert tokens[2].value == "speed"
    assert tokens[4].value == "100"
    assert tokens[-1].value == "Oda"


def test_lexes_range_and_nullish_operators():
    tokens = tokens_without_eof("0..10 0..=5 alias ?? fallback 5u")

    assert [tok.type for tok in tokens] == [
        TokenType.INTEGER,
        TokenType.RANGE,
        TokenType.INTEGER,
        TokenType.INTEGER,
        TokenType.RANGE_INCLUSIVE,
        TokenType.INTEGER,
        TokenType.IDENTIFIER,
        TokenType.NULLISH,
        TokenType.IDENTIFIER,
        TokenType.INTEGER,
    ]
    assert tokens[-1].value == "5u"


def test_lexes_ref_when_arrow_and_compound_assignment():
    tokens = tokens_without_eof("ref x when -> y += 1 && y != 0")

    assert [tok.type for tok in tokens] == [
        TokenType.REF,
        TokenType.IDENTIFIER,
        TokenType.WHEN,
        TokenType.ARROW,
        TokenType.IDENTIFIER,
        TokenType.PLUS_ASSIGN,
        TokenType.INTEGER,
        TokenType.AND,
        TokenType.IDENTIFIER,
        TokenType.NEQ,
        TokenType.INTEGER,
    ]


def test_lexes_enum_keyword():
    tokens = tokens_without_eof("enum Mode { Idle, Busy }")

    assert [tok.type for tok in tokens] == [
        TokenType.ENUM,
        TokenType.IDENTIFIER,
        TokenType.LBRACE,
        TokenType.IDENTIFIER,
        TokenType.COMMA,
        TokenType.IDENTIFIER,
        TokenType.RBRACE,
    ]


def test_skips_line_and_block_comments():
    tokens = tokens_without_eof('int x = 1 // ignored\n//* ignored\nstill ignored *//\nprint(x)')

    assert [tok.type for tok in tokens] == [
        TokenType.INT,
        TokenType.IDENTIFIER,
        TokenType.ASSIGN,
        TokenType.INTEGER,
        TokenType.NEWLINE,
        TokenType.IDENTIFIER,
        TokenType.LPAREN,
        TokenType.IDENTIFIER,
        TokenType.RPAREN,
    ]


def test_collapses_consecutive_newlines():
    types = token_types("\n\nint x = 1\n\n\nprint(x)")

    assert types.count(TokenType.NEWLINE) == 1
    assert types[-1] == TokenType.EOF


def test_lexes_string_and_char_escapes():
    tokens = tokens_without_eof("string s = \"a\\nb\"\nchar c = '\\''")

    assert tokens[3].type == TokenType.STRING_LIT
    assert tokens[3].value == "a\nb"
    assert tokens[-1].type == TokenType.CHAR_LIT
    assert tokens[-1].value == "\\'"


def test_unterminated_block_comment_raises():
    with pytest.raises(LexerError):
        Lexer("//* nope").tokenize()
