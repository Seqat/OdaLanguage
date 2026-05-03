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

def test_enum_emits_standard_c_typedef_enum():
    gen = CCodeGenerator()
    program = ast.Program(statements=[
        ast.EnumDeclaration(name="Mode", variants=["Idle", "Busy"]),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="Mode"),
            name="mode",
            initializer=ast.MemberAccess(obj=ast.Identifier(name="Mode"), member="Busy"),
        ),
    ])

    code = gen.generate(program)

    assert "typedef enum {" in code
    assert "Mode_Idle," in code
    assert "Mode_Busy" in code
    assert "} Mode;" in code
    assert "Mode mode = Mode_Busy;" in code

def test_enum_unknown_variant_is_semantic_error():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.EnumDeclaration(name="Mode", variants=["Idle"]),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="Mode"),
            name="mode",
            initializer=ast.MemberAccess(obj=ast.Identifier(name="Mode"), member="Busy"),
        ),
    ])

    analyzer.analyze(program)

    assert any("Enum 'Mode' has no variant 'Busy'" in e.message for e in analyzer.errors)

def test_match_pattern_type_must_match_scrutinee():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.EnumDeclaration(name="Mode", variants=["Idle"]),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="Mode"),
            name="mode",
            initializer=ast.MemberAccess(obj=ast.Identifier(name="Mode"), member="Idle"),
        ),
        ast.MatchStatement(
            expr=ast.Identifier(name="mode"),
            arms=[
                ast.MatchArm(
                    pattern=ast.IntegerLiteral(value=1),
                    body=[ast.ReturnStatement()],
                )
            ],
        ),
    ])

    analyzer.analyze(program)

    assert any("Match pattern type 'int' does not match 'Mode'" in e.message for e in analyzer.errors)

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

def test_guard_unknown_error_type_raises():
    analyzer = SemanticAnalyzer()
    stmt = ast.GuardStatement(
        var_type=ast.TypeAnnotation(base_type="string"),
        var_name="content",
        expr=ast.CallExpr(callee=ast.Identifier(name="readFile"), args=[ast.StringLiteral(value="config.txt")]),
        cases=[ast.GuardCase(error_type="NetworkDown", body=[ast.ReturnStatement()])]
    )
    program = ast.Program(statements=[stmt])
    analyzer.analyze(program)
    assert any("Unknown error type 'NetworkDown'" in e.message for e in analyzer.errors)

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

def test_if_block_variable_does_not_leak_to_outer_scope():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.IfStatement(
            condition=ast.BoolLiteral(value=True),
            body=[
                ast.VarDeclaration(
                    type_ann=ast.TypeAnnotation(base_type="int"),
                    name="inside",
                    initializer=ast.IntegerLiteral(value=1),
                )
            ],
        ),
        ast.ExpressionStatement(expr=ast.Identifier(name="inside")),
    ])

    analyzer.analyze(program)

    assert any("Undefined variable 'inside'" in e.message for e in analyzer.errors)

def test_loop_variable_does_not_leak_to_outer_scope():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ForRangeStatement(
            var_type=ast.TypeAnnotation(base_type="int"),
            var_name="i",
            start=ast.IntegerLiteral(value=0),
            end=ast.IntegerLiteral(value=2),
            body=[
                ast.ExpressionStatement(expr=ast.Identifier(name="i")),
            ],
        ),
        ast.ExpressionStatement(expr=ast.Identifier(name="i")),
    ])

    analyzer.analyze(program)

    assert any("Undefined variable 'i'" in e.message for e in analyzer.errors)

def test_same_class_can_access_private_member_on_same_class_instance():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="Box",
            fields=[
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="int"), name="_secret"),
            ],
            methods=[
                ast.FuncDeclaration(
                    name="reveal",
                    params=[
                        ast.Parameter(type_ann=ast.TypeAnnotation(base_type="Box"), name="other"),
                    ],
                    body=[
                        ast.ExpressionStatement(
                            expr=ast.MemberAccess(obj=ast.Identifier(name="other"), member="_secret")
                        )
                    ],
                )
            ],
        )
    ])

    analyzer.analyze(program)

    assert not analyzer.errors, f"Errors: {[e.message for e in analyzer.errors]}"

def test_different_class_cannot_access_private_member():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="Box",
            fields=[
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="int"), name="_secret"),
            ],
        ),
        ast.ClassDeclaration(
            name="Spy",
            methods=[
                ast.FuncDeclaration(
                    name="steal",
                    params=[
                        ast.Parameter(type_ann=ast.TypeAnnotation(base_type="Box"), name="target"),
                    ],
                    body=[
                        ast.ExpressionStatement(
                            expr=ast.MemberAccess(obj=ast.Identifier(name="target"), member="_secret")
                        )
                    ],
                )
            ],
        ),
    ])

    analyzer.analyze(program)

    assert any("Cannot access private member '_secret' outside class 'Box'" in e.message for e in analyzer.errors)

def test_function_call_argument_count_is_checked():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="add",
            params=[
                ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="a"),
                ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="b"),
            ],
            return_type=ast.TypeAnnotation(base_type="int"),
            body=[ast.ReturnStatement(value=ast.Identifier(name="a"))],
        ),
        ast.ExpressionStatement(expr=ast.CallExpr(
            callee=ast.Identifier(name="add"),
            args=[ast.IntegerLiteral(value=1)],
            ref_flags=[False],
        )),
    ])

    analyzer.analyze(program)

    assert any("expects 2 argument(s), got 1" in e.message for e in analyzer.errors)

def test_function_call_argument_type_is_checked():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="takes_int",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="x")],
            body=[],
        ),
        ast.ExpressionStatement(expr=ast.CallExpr(
            callee=ast.Identifier(name="takes_int"),
            args=[ast.StringLiteral(value="nope")],
            ref_flags=[False],
        )),
    ])

    analyzer.analyze(program)

    assert any("Cannot pass 'string' to parameter of type 'int'" in e.message for e in analyzer.errors)

def test_ref_parameter_requires_ref_keyword_and_lvalue():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="touch",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="x", is_ref=True)],
            body=[],
        ),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="value",
            initializer=ast.IntegerLiteral(value=1),
        ),
        ast.ExpressionStatement(expr=ast.CallExpr(
            callee=ast.Identifier(name="touch"),
            args=[ast.Identifier(name="value")],
            ref_flags=[False],
        )),
        ast.ExpressionStatement(expr=ast.CallExpr(
            callee=ast.Identifier(name="touch"),
            args=[ast.IntegerLiteral(value=1)],
            ref_flags=[True],
        )),
    ])

    analyzer.analyze(program)

    assert any("must be passed with 'ref'" in e.message for e in analyzer.errors)
    assert any("Cannot pass non-assignable expression as ref parameter" in e.message for e in analyzer.errors)

def test_non_ref_parameter_rejects_ref_keyword():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="takes_int",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="int"), name="x")],
            body=[],
        ),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="value",
            initializer=ast.IntegerLiteral(value=1),
        ),
        ast.ExpressionStatement(expr=ast.CallExpr(
            callee=ast.Identifier(name="takes_int"),
            args=[ast.Identifier(name="value")],
            ref_flags=[True],
        )),
    ])

    analyzer.analyze(program)

    assert any("is not a ref parameter" in e.message for e in analyzer.errors)

def test_heap_field_class_parameter_must_be_ref():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="NameBox",
            fields=[
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="string"), name="name"),
            ],
        ),
        ast.FuncDeclaration(
            name="takes_box",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="NameBox"), name="box")],
            body=[],
        ),
    ])

    analyzer.analyze(program)

    assert any("NameBox" in e.message and "must be passed by ref" in e.message for e in analyzer.errors)

def test_heap_field_class_ref_parameter_is_allowed():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="NameBox",
            fields=[
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="string"), name="name"),
            ],
        ),
        ast.FuncDeclaration(
            name="takes_box",
            params=[
                ast.Parameter(
                    type_ann=ast.TypeAnnotation(base_type="NameBox"),
                    name="box",
                    is_ref=True,
                )
            ],
            body=[],
        ),
    ])

    analyzer.analyze(program)

    assert not analyzer.errors, f"Errors: {[e.message for e in analyzer.errors]}"

def test_array_field_class_parameter_must_be_ref():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="Buffer",
            fields=[
                ast.VarDeclaration(
                    type_ann=ast.TypeAnnotation(base_type="int", is_array=True, array_depth=1),
                    name="items",
                ),
            ],
        ),
        ast.FuncDeclaration(
            name="takes_buffer",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="Buffer"), name="buffer")],
            body=[],
        ),
    ])

    analyzer.analyze(program)

    assert any("Buffer" in e.message and "must be passed by ref" in e.message for e in analyzer.errors)

def test_nested_heap_field_class_parameter_must_be_ref():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="NameBox",
            fields=[
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="string"), name="name"),
            ],
        ),
        ast.ClassDeclaration(
            name="Outer",
            fields=[
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="NameBox"), name="inner"),
            ],
        ),
        ast.FuncDeclaration(
            name="takes_outer",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="Outer"), name="outer")],
            body=[],
        ),
    ])

    analyzer.analyze(program)

    assert any("Outer" in e.message and "must be passed by ref" in e.message for e in analyzer.errors)

def test_plain_class_parameter_can_be_passed_by_value():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="Point",
            fields=[
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="int"), name="x"),
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="int"), name="y"),
            ],
        ),
        ast.FuncDeclaration(
            name="takes_point",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="Point"), name="point")],
            body=[],
        ),
    ])

    analyzer.analyze(program)

    assert not analyzer.errors, f"Errors: {[e.message for e in analyzer.errors]}"

def test_heap_field_class_by_value_call_is_rejected():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.ClassDeclaration(
            name="NameBox",
            fields=[
                ast.VarDeclaration(type_ann=ast.TypeAnnotation(base_type="string"), name="name"),
            ],
        ),
        ast.FuncDeclaration(
            name="takes_box",
            params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="NameBox"), name="box")],
            body=[],
        ),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="NameBox"),
            name="box",
            initializer=ast.CallExpr(callee=ast.Identifier(name="NameBox")),
        ),
        ast.ExpressionStatement(expr=ast.CallExpr(
            callee=ast.Identifier(name="takes_box"),
            args=[ast.Identifier(name="box")],
            ref_flags=[False],
        )),
    ])

    analyzer.analyze(program)

    assert any("Cannot pass class 'NameBox'" in e.message and "by value" in e.message for e in analyzer.errors)

def test_returning_function_must_return_on_all_paths():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="maybe",
            return_type=ast.TypeAnnotation(base_type="int"),
            body=[
                ast.IfStatement(
                    condition=ast.BoolLiteral(value=True),
                    body=[ast.ReturnStatement(value=ast.IntegerLiteral(value=1))],
                )
            ],
        )
    ])

    analyzer.analyze(program)

    assert any("Not all code paths return a value" in e.message for e in analyzer.errors)

def test_return_type_is_checked():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.FuncDeclaration(
            name="bad",
            return_type=ast.TypeAnnotation(base_type="int"),
            body=[ast.ReturnStatement(value=ast.StringLiteral(value="nope"))],
        )
    ])

    analyzer.analyze(program)

    assert any("Cannot return 'string' from function returning 'int'" in e.message for e in analyzer.errors)

def test_int_to_uint_is_not_allowed():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="uint"),
            name="u",
            initializer=ast.IntegerLiteral(value=1),
        )
    ])

    analyzer.analyze(program)

    assert any("Cannot coerce 'int' to 'uint'" in e.message for e in analyzer.errors)

def test_uint_literal_initializes_uint():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="uint"),
            name="u",
            initializer=ast.UIntLiteral(value=1),
        )
    ])

    analyzer.analyze(program)

    assert not analyzer.errors, f"Errors: {[e.message for e in analyzer.errors]}"

def test_explicit_cast_allows_int_to_uint_and_float_to_int():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="uint"),
            name="u",
            initializer=ast.CastExpr(
                expr=ast.IntegerLiteral(value=1),
                target_type=ast.TypeAnnotation(base_type="uint"),
            ),
        ),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="i",
            initializer=ast.CastExpr(
                expr=ast.FloatLiteral(value=3.8),
                target_type=ast.TypeAnnotation(base_type="int"),
            ),
        ),
    ])

    analyzer.analyze(program)

    assert not analyzer.errors, f"Errors: {[e.message for e in analyzer.errors]}"

def test_invalid_explicit_cast_is_rejected():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="bad",
            initializer=ast.CastExpr(
                expr=ast.StringLiteral(value="nope"),
                target_type=ast.TypeAnnotation(base_type="int"),
            ),
        )
    ])

    analyzer.analyze(program)

    assert any("Cannot cast 'string' to 'int'" in e.message for e in analyzer.errors)

def test_deep_binary_expression_type_inference_rejects_invalid_operands():
    analyzer = SemanticAnalyzer()
    program = ast.Program(statements=[
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="a",
            initializer=ast.IntegerLiteral(value=1),
        ),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="bool"),
            name="b",
            initializer=ast.BoolLiteral(value=True),
        ),
        ast.VarDeclaration(
            type_ann=ast.TypeAnnotation(base_type="int"),
            name="bad",
            initializer=ast.BinaryExpr(
                left=ast.BinaryExpr(
                    left=ast.Identifier(name="a"),
                    op="+",
                    right=ast.IntegerLiteral(value=1),
                ),
                op="+",
                right=ast.Identifier(name="b"),
            ),
        ),
    ])

    analyzer.analyze(program)

    assert any("Invalid operands for '+'" in e.message for e in analyzer.errors)
