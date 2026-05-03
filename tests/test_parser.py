from src.oda import ast_nodes as ast
from src.oda.lexer import Lexer
from src.oda.parser import Parser


def parse(source):
    tokens = Lexer(source).tokenize()
    return Parser(tokens).parse()


def test_parses_nullable_array_declaration():
    program = parse("string?[] names = [\"oda\"]")
    stmt = program.statements[0]

    assert isinstance(stmt, ast.VarDeclaration)
    assert stmt.name == "names"
    assert stmt.type_ann.base_type == "string"
    assert stmt.type_ann.is_nullable
    assert stmt.type_ann.is_array
    assert stmt.type_ann.array_depth == 1
    assert isinstance(stmt.initializer, ast.ArrayLiteral)


def test_parses_function_with_ref_param_and_return_type():
    program = parse("func bump(ref int value) -> int { return value + 1 }")
    func = program.statements[0]

    assert isinstance(func, ast.FuncDeclaration)
    assert func.name == "bump"
    assert func.params[0].is_ref
    assert func.params[0].name == "value"
    assert func.return_type.base_type == "int"
    assert isinstance(func.body[0], ast.ReturnStatement)


def test_parses_extern_function_signature_without_body():
    program = parse("extern func abs(int value) -> int")
    func = program.statements[0]

    assert isinstance(func, ast.FuncDeclaration)
    assert func.is_extern
    assert func.name == "abs"
    assert func.params[0].name == "value"
    assert func.params[0].type_ann.base_type == "int"
    assert func.return_type.base_type == "int"
    assert func.body == []


def test_parses_class_with_constructor_destructor_and_method():
    program = parse(
        """
class Box {
    int value
    construct(int v) { value = v }
    func get() -> int { return value }
    destruct() { print("done") }
}
"""
    )
    cls = program.statements[0]

    assert isinstance(cls, ast.ClassDeclaration)
    assert cls.name == "Box"
    assert cls.fields[0].name == "value"
    assert cls.constructor.name == "construct"
    assert cls.methods[0].name == "get"
    assert cls.destructor.name == "destruct"


def test_parses_enum_declaration():
    program = parse("enum Mode { Idle, Busy, Done }")
    enum = program.statements[0]

    assert isinstance(enum, ast.EnumDeclaration)
    assert enum.name == "Mode"
    assert enum.variants == ["Idle", "Busy", "Done"]


def test_parses_inclusive_range_loop_with_step():
    program = parse("for (int i in 0..=10 step 2) { print(i) }")
    stmt = program.statements[0]

    assert isinstance(stmt, ast.ForRangeStatement)
    assert stmt.var_name == "i"
    assert stmt.is_inclusive
    assert isinstance(stmt.step, ast.IntegerLiteral)
    assert stmt.step.value == 2


def test_parses_multidimensional_for_in_loop():
    program = parse("for (int[] row in matrix reversed step 2) { print(row[0]) }")
    stmt = program.statements[0]

    assert isinstance(stmt, ast.ForInStatement)
    assert stmt.var_type.is_array
    assert stmt.var_type.array_depth == 1
    assert stmt.var_name == "row"
    assert stmt.is_reversed
    assert stmt.step.value == 2


def test_parses_for_in_loop_with_index_variable():
    program = parse("for (int i, int n in nums) { print(i + n) }")
    stmt = program.statements[0]

    assert isinstance(stmt, ast.ForInStatement)
    assert stmt.index_type.base_type == "int"
    assert stmt.index_name == "i"
    assert stmt.var_type.base_type == "int"
    assert stmt.var_name == "n"


def test_parses_guard_cases():
    program = parse(
        """
guard string content = readFile("config.txt") else {
    when (FileNotFound) { return }
    when (PermissionDenied) { return }
}
"""
    )
    stmt = program.statements[0]

    assert isinstance(stmt, ast.GuardStatement)
    assert stmt.var_name == "content"
    assert [case.error_type for case in stmt.cases] == [
        "FileNotFound",
        "PermissionDenied",
    ]


def test_parses_interpolated_string_parts():
    program = parse('string message = "Hello {name}!"')
    init = program.statements[0].initializer

    assert isinstance(init, ast.InterpolatedString)
    assert init.parts[0] == "Hello "
    assert isinstance(init.parts[1], ast.Identifier)
    assert init.parts[1].name == "name"
    assert init.parts[2] == "!"

def test_parses_interpolated_expression_parts():
    program = parse('string message = "sum={a + b}"')
    init = program.statements[0].initializer

    assert isinstance(init, ast.InterpolatedString)
    assert init.parts[0] == "sum="
    assert isinstance(init.parts[1], ast.BinaryExpr)
    assert isinstance(init.parts[1].left, ast.Identifier)
    assert init.parts[1].left.name == "a"
    assert init.parts[1].op == "+"
    assert isinstance(init.parts[1].right, ast.Identifier)
    assert init.parts[1].right.name == "b"


def test_parses_uint_literal_and_as_cast():
    program = parse("uint value = 5u\nint narrowed = value as int")

    first = program.statements[0]
    second = program.statements[1]

    assert isinstance(first.initializer, ast.UIntLiteral)
    assert first.initializer.value == 5
    assert isinstance(second.initializer, ast.CastExpr)
    assert second.initializer.target_type.base_type == "int"
    assert isinstance(second.initializer.expr, ast.Identifier)


def test_parses_c_style_cast():
    program = parse("uint value = (uint)5")
    init = program.statements[0].initializer

    assert isinstance(init, ast.CastExpr)
    assert init.target_type.base_type == "uint"
    assert isinstance(init.expr, ast.IntegerLiteral)


def test_parses_match_with_wildcard_arm():
    program = parse(
        """
match (cmd) {
    "start" { print("start") }
    _ { print("other") }
}
"""
    )
    stmt = program.statements[0]

    assert isinstance(stmt, ast.MatchStatement)
    assert isinstance(stmt.arms[0].pattern, ast.StringLiteral)
    assert stmt.arms[1].pattern is None
