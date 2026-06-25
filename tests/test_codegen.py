import pytest
import re
from src.oda import ast_nodes as ast
from src.oda.codegen import CCodeGenerator


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
    """BUG-03: String interpolation should allocate using snprintf sizing."""
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
    assert "snprintf(NULL, 0" in code
    assert "malloc((size_t)" in code
    assert "snprintf" in code
    assert "Hello %s!" in code
    assert "({" not in code

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

def test_guard_emits_error_dispatch():
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
    assert "if (_oda_error == ODA_ERROR_FILE_NOT_FOUND)" in code
    assert "oda: unhandled guard error" in code
    assert "/* when(" not in code

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

def test_user_function_value_argument_does_not_use_compound_literal():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="add1",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="x")],
            return_type=ast.TypeAnnotation(base_type="int"),
            body=[ast.ReturnStatement(value=ast.BinaryExpr(
                left=ast.Identifier(name="x"),
                op="+",
                right=ast.IntegerLiteral(value=1),
            ))],
        ),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="y",
            initializer=ast.CallExpr(
                callee=ast.Identifier(name="add1"),
                args=[ast.IntegerLiteral(value=41)],
                ref_flags=[False],
            ),
        ),
    ])

    code = gen.generate(program)

    assert "add1(41)" in code
    assert "&(" not in code

def test_ref_argument_rvalue_uses_scoped_temp_not_compound_literal():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="touch",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="x", is_ref=True)],
            body=[],
        ),
        ast.ExpressionStatement(expr=ast.CallExpr(
            callee=ast.Identifier(name="touch"),
            args=[ast.IntegerLiteral(value=7)],
            ref_flags=[False],
        )),
    ])

    code = gen.generate(program)

    assert "int _oda_tmp_" in code
    assert "touch(&_oda_tmp_" in code
    assert "&(" not in code

def test_heap_string_interpolation_is_freed_at_scope_exit():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="demo",
            body=[
                ast.VarDeclaration(
                    type_ann=ast.TypeAnnotation(base_type="string"),
                    name="msg",
                    initializer=ast.InterpolatedString(parts=["value=", ast.IntegerLiteral(value=7)]),
                )
            ],
        )
    ])

    code = gen.generate(program)

    assert "char* msg = _oda_tmp_" in code
    assert "free(msg);" in code
    assert code.index("char* msg =") < code.index("free(msg);")
    assert gen._heap_vars == []

def test_heap_array_allocation_is_freed_at_scope_exit():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="demo",
            body=[
                ast.VarDeclaration(
                    type_ann=ast.TypeAnnotation(base_type="int", is_array=True, array_depth=1),
                    name="nums",
                    initializer=ast.ArrayAllocation(
                        base_type="int",
                        sizes=[ast.IntegerLiteral(value=3)],
                    ),
                )
            ],
        )
    ])

    code = gen.generate(program)

    assert "int* nums = (int*)malloc(sizeof(int) * (3));" in code
    assert "free(nums);" in code
    assert gen._heap_vars == []

def test_heap_var_is_freed_before_return():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="demo",
            body=[
                ast.VarDeclaration(
                    type_ann=ast.TypeAnnotation(base_type="string"),
                    name="line",
                    initializer=ast.CallExpr(callee=ast.Identifier(name="input")),
                ),
                ast.ReturnStatement(),
            ],
        )
    ])

    code = gen.generate(program)

    assert "char* line = _oda_input();" in code
    assert "free(line);\n    return;" in code
    assert code.count("free(line);") == 1
    assert code.index("free(line);") < code.index("return;")

def test_string_literal_var_is_not_tracked_as_heap():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="demo",
            body=[
                ast.VarDeclaration(
                    type_ann=ast.TypeAnnotation(base_type="string"),
                    name="label",
                    initializer=ast.StringLiteral(value="static"),
                )
            ],
        )
    ])

    code = gen.generate(program)

    assert 'char* label = "static";' in code
    assert "free(label);" not in code

def test_print_string_concat_temp_is_freed_after_statement():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="count",
            initializer=ast.IntegerLiteral(value=3),
        ),
        ast.ExpressionStatement(expr=ast.CallExpr(
            callee=ast.Identifier(name="print"),
            args=[
                ast.BinaryExpr(
                    left=ast.StringLiteral(value="Count: "),
                    op="+",
                    right=ast.Identifier(name="count"),
                )
            ],
            ref_flags=[False],
        )),
    ])

    code = gen.generate(program)

    assert 'printf("%s\\n", _oda_tmp_' in code
    assert "_oda_str_concat(\"Count: \", _oda_tmp_" in code
    assert "_oda_int_to_str(count)" in code
    assert "free(_oda_tmp_" in code
    assert code.index('printf("%s\\n", _oda_tmp_') < code.index("free(_oda_tmp_")
    assert gen._heap_vars == []

def test_heap_concat_initializer_owns_final_value_but_tracks_child_temp():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="count",
            initializer=ast.IntegerLiteral(value=3),
        ),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="string"),
            name="msg",
            initializer=ast.BinaryExpr(
                left=ast.StringLiteral(value="Count: "),
                op="+",
                right=ast.Identifier(name="count"),
            ),
        ),
    ])

    code = gen.generate(program)

    assert 'char* msg = _oda_str_concat("Count: ", _oda_tmp_' in code
    assert "free(msg);" in code
    assert "free(_oda_tmp_" in code
    assert code.count("free(msg);") == 1
    assert gen._heap_vars == []
