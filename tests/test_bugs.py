import pytest
from src.oda import ast_nodes as ast
from src.oda.semantic import SemanticAnalyzer
from src.oda.codegen import CCodeGenerator

def test_bug_01_builtin_return_types():
    """BUG-01: input() and readFile() should not return void."""
    analyzer = SemanticAnalyzer()
    
    # input() assigned to a string variable
    # let x: string = input()
    stmt = ast.VarDeclaration(
        type_ann=ast.TypeAnnotation(base_type="string"),
        name="x",
        initializer=ast.CallExpr(callee=ast.Identifier(name="input"))
    )
    program = ast.Program(statements=[stmt])
    analyzer.analyze(program)
    
    # If the bug exists, analyzer.errors will contain "Cannot assign a void value"
    assert not analyzer.errors, f"Errors found: {[e.message for e in analyzer.errors]}"

def test_bug_02_pass_by_value():
    """BUG-02: Only ref-marked parameters become pointers."""
    gen = CCodeGenerator()
    
    # func test(a: int, ref b: int)
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
    
    # a should be 'int a', b should be 'int* b'
    assert "int a" in code
    assert "int* b" in code
    # Ensure no 'int* a'
    import re
    assert not re.search(r"int\*\s+a", code)

def test_bug_03_string_interpolation():
    """BUG-03: String interpolation should use malloc + snprintf."""
    gen = CCodeGenerator()
    
    # let s = "Hello {name}!"
    stmt = ast.VarDeclaration(
        type_ann=ast.TypeAnnotation(base_type="string"),
        name="s",
        initializer=ast.InterpolatedString(parts=["Hello ", ast.Identifier(name="name"), "!"])
    )
    # We need 'name' to be defined
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
    
    # class MyClass { destruct() { print("deleted") } }
    # let obj = MyClass()
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
    
    # class MyClass { _secret: int }
    # let obj = MyClass()
    # print(obj._secret)
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
