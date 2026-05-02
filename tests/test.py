import pytest
import re
from src.oda import ast_nodes as ast
from src.oda.semantic import SemanticAnalyzer, FuncInfo
from src.oda.codegen import CCodeGenerator

def test_bug_01_builtin_return_types():
    """BUG-01: input() and readFile() should not return void."""
    analyzer = SemanticAnalyzer()
    stmt = ast.VarDeclaration(
        type_ann=ast.TypeAnnotation(base_type="string"),
        name="x",
        initializer=ast.CallExpr(callee=ast.Identifier(name="input"))
    )
    program = ast.Program(statements=[stmt])
    analyzer.analyze(program)
    assert not analyzer.errors, f"Errors found: {[e.message for e in analyzer.errors]}"

def test_bug_02_pass_by_value():
    """BUG-02: Only ref-marked parameters become pointers."""
    gen = CCodeGenerator()
    func = ast.FuncDeclaration(
        name="test",
        params=[
            ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="a", is_ref=False),
            ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="b", is_ref=True)
        ],
        body=[]
    )
    program = ast.Program(statements=[func])
    code = gen.generate(program)
    assert "int a" in code
    assert "int* b" in code
    assert not re.search(r"int\*\s+a", code)

def test_bug_03_string_interpolation():
    """BUG-03: String interpolation should use malloc + snprintf."""
    gen = CCodeGenerator()
    stmt = ast.VarDeclaration(
        type_ann=ast.TypeAnnotation(base_type="string"),
        name="s",
        initializer=ast.InterpolatedString(parts=["Hello ", ast.Identifier(name="name"), "!"])
    )
    name_decl = ast.VarDeclaration(
        type_ann=ast.TypeAnnotation(base_type="string"),
        name="name",
        initializer=ast.StringLiteral(value="World")
    )
    program = ast.Program(statements=[name_decl, stmt])
    code = gen.generate(program)
    assert "malloc(1024)" in code
    assert "snprintf" in code
    assert "Hello %s!" in code

def test_bug_04_raii_destructor():
    """BUG-04: RAII destructor injection should be enabled."""
    gen = CCodeGenerator()
    cls = ast.ClassDeclaration(
        name="MyClass",
        destructor=ast.FuncDeclaration(name="destruct", body=[
            ast.ExpressionStatement(expr=ast.CallExpr(callee=ast.Identifier(name="print"), args=[ast.StringLiteral(value="deleted")]))
        ])
    )
    var = ast.VarDeclaration(
        type_ann=ast.TypeAnnotation(base_type="MyClass"),
        name="obj",
        initializer=ast.CallExpr(callee=ast.Identifier(name="MyClass"))
    )
    program = ast.Program(statements=[cls, var])
    code = gen.generate(program)
    assert "MyClass_destruct(&obj);" in code

def test_bug_05_private_member_access():
    """BUG-05: Private member access from outside class should be rejected."""
    analyzer = SemanticAnalyzer()
    cls = ast.ClassDeclaration(
        name="MyClass",
        fields=[ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="int"), name="_secret")]
    )
    var = ast.VarDeclaration(
        type_ann=ast.TypeAnnotation(base_type="MyClass"),
        name="obj",
        initializer=ast.CallExpr(callee=ast.Identifier(name="MyClass"))
    )
    access = ast.ExpressionStatement(
        expr=ast.MemberAccess(obj=ast.Identifier(name="obj"), member="_secret")
    )
    program = ast.Program(statements=[cls, var, access])
    analyzer.analyze(program)
    assert any("Cannot access private member" in e.message for e in analyzer.errors)

def test_match_string_uses_strcmp():
    gen = CCodeGenerator()
    match_stmt = ast.MatchStatement(
        expr=ast.Identifier(name="cmd"),
        arms=[
            ast.MatchArm(
                pattern=ast.StringLiteral(value="start"),
                body=[ast.ExpressionStatement(expr=ast.CallExpr(callee=ast.Identifier(name="print"), args=[ast.StringLiteral(value="Starting")]))]
            )
        ]
    )
    gen._var_types["cmd"] = "string"
    out = []
    gen._emit_match(match_stmt, out)
    code = "\n".join(out)
    assert "strcmp(" in code
    match_part = code.split("strcmp")[0]
    if "if" in match_part:
        assert "==" not in match_part.split("if")[-1]

def test_match_integer_uses_equality():
    gen = CCodeGenerator()
    match_stmt = ast.MatchStatement(
        expr=ast.Identifier(name="val"),
        arms=[
            ast.MatchArm(
                pattern=ast.IntegerLiteral(value=1),
                body=[ast.ExpressionStatement(expr=ast.CallExpr(callee=ast.Identifier(name="print"), args=[ast.StringLiteral(value="one")]))]
            )
        ]
    )
    gen._var_types["val"] = "int"
    out = []
    gen._emit_match(match_stmt, out)
    code = "\n".join(out)
    assert "strcmp" not in code
    assert "==" in code

def test_for_in_unknown_collection_raises():
    analyzer = SemanticAnalyzer()
    stmt = ast.ForInStatement(
        var_type=ast.TypeAnnotation(base_type="int"),
        var_name="x",
        iterable=ast.CallExpr(callee=ast.Identifier(name="getList")),
        body=[ast.ExpressionStatement(expr=ast.CallExpr(callee=ast.Identifier(name="print"), args=[ast.Identifier(name="x")]))]
    )
    analyzer.functions["getList"] = FuncInfo("getList", ast.FuncDeclaration(
        name="getList",
        return_type=ast.TypeAnnotation(base_type="int", is_array=True, array_depth=1)
    ))
    program = ast.Program(statements=[stmt])
    analyzer.analyze(program)
    assert any("cannot iterate" in e.message.lower() for e in analyzer.errors)

def test_for_in_known_array_passes():
    analyzer = SemanticAnalyzer()
    nums_decl = ast.VarDeclaration(
        type_ann=ast.TypeAnnotation(base_type="int", is_array=True, array_depth=1),
        name="nums",
        initializer=ast.ArrayLiteral(elements=[ast.IntegerLiteral(value=1), ast.IntegerLiteral(value=2), ast.IntegerLiteral(value=3)])
    )
    for_stmt = ast.ForInStatement(
        var_type=ast.TypeAnnotation(base_type="int"),
        var_name="x",
        iterable=ast.Identifier(name="nums"),
        body=[ast.ExpressionStatement(expr=ast.CallExpr(callee=ast.Identifier(name="print"), args=[ast.Identifier(name="x")]))]
    )
    program = ast.Program(statements=[nums_decl, for_stmt])
    analyzer.analyze(program)
    assert not analyzer.errors, f"Errors: {[e.message for e in analyzer.errors]}"

def test_guard_emits_null_check():
    gen = CCodeGenerator()
    stmt = ast.GuardStatement(
        var_type=ast.TypeAnnotation(base_type="string"),
        var_name="content",
        expr=ast.CallExpr(callee=ast.Identifier(name="readFile"), args=[ast.StringLiteral(value="config.txt")]),
        cases=[ast.GuardCase(error_type="FileNotFound", body=[ast.ReturnStatement()])]
    )
    out = []
    gen._emit_guard(stmt, out)
    code = "\n".join(out)
    assert "if (content == NULL)" in code

def test_guard_else_without_return_raises():
    analyzer = SemanticAnalyzer()
    stmt = ast.GuardStatement(
        var_type=ast.TypeAnnotation(base_type="string"),
        var_name="content",
        expr=ast.CallExpr(callee=ast.Identifier(name="readFile"), args=[ast.StringLiteral(value="config.txt")]),
        cases=[ast.GuardCase(error_type="FileNotFound", body=[ast.ExpressionStatement(expr=ast.CallExpr(callee=ast.Identifier(name="print"), args=[ast.StringLiteral(value="oops")]))])]
    )
    program = ast.Program(statements=[stmt])
    analyzer.analyze(program)
    assert any("must exit" in e.message for e in analyzer.errors)

def test_guard_unwrapped_var_is_defined_after_block():
    gen = CCodeGenerator()
    stmt = ast.GuardStatement(
        var_type=ast.TypeAnnotation(base_type="string"),
        var_name="content",
        expr=ast.CallExpr(callee=ast.Identifier(name="readFile"), args=[ast.StringLiteral(value="config.txt")]),
        cases=[ast.GuardCase(error_type="FileNotFound", body=[ast.ReturnStatement()])]
    )
    out = []
    gen._emit_guard(stmt, out)
    code = "\n".join(out)
    null_check_pos = code.index("if (content == NULL)")
    decl_pos = code.index("char* content =")
    assert decl_pos < null_check_pos

def test_member_access_in_class_context_keeps_explicit_object():
    gen = CCodeGenerator()

    assert gen._expr(
        ast.MemberAccess(obj=ast.Identifier(name="other"), member="value"),
        class_ctx="Box",
    ) == "other.value"
    assert gen._expr(
        ast.MemberAccess(obj=ast.Identifier(name="self"), member="value"),
        class_ctx="Box",
    ) == "self->value"

def test_for_range_body_raii_state_is_emitted_once_and_reused():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="Box",
            constructor=ast.FuncDeclaration(name="construct", body=[]),
            destructor=ast.FuncDeclaration(name="destruct", body=[]),
        ),
        ast.ForRangeStatement(
            var_type=ast.TypeAnnotation(base_type="int"),
            var_name="i",
            start=ast.IntegerLiteral(value=0),
            end=ast.IntegerLiteral(value=2),
            body=[
                ast.VarDeclaration(
                    type_ann=ast.TypeAnnotation(base_type="Box"),
                    name="b",
                    initializer=ast.CallExpr(callee=ast.Identifier(name="Box")),
                )
            ],
        ),
    ])

    code = gen.generate(program)

    assert gen._destructors == []
    assert code.count("Box_destruct(&b);") == 2
