import json
import pytest
import subprocess
import sys
import tempfile
from pathlib import Path
from src.oda.main import _pipeline

from tests.c_sanitize import TEST_CFLAGS, run_generated_binary

ROOT = Path(__file__).resolve().parents[1]

def compile_and_run(oda_source: str) -> str:
    """Returns stdout of the compiled and executed Oda program."""
    c_code = _pipeline(oda_source, "<test>")
    with tempfile.TemporaryDirectory() as tmp:
        c_path = Path(tmp) / "out.c"
        bin_path = Path(tmp) / "out"
        c_path.write_text(c_code)
        # We need to include stdio.h, stdlib.h, string.h etc. 
        # _pipeline might already include them if it generates a full file.
        # Let's assume it does.
        subprocess.run(["gcc", str(c_path), *TEST_CFLAGS, "-o", str(bin_path), "-O2"],
                       check=True, capture_output=True)
        result = run_generated_binary([str(bin_path)], capture_output=True, text=True)
        return result.stdout.strip()

def test_hello_world():
    assert compile_and_run('print("Hello World")') == "Hello World"

def test_prelude_is_implicit_and_keeps_headers_minimal():
    c_code = _pipeline("int x = 1\nassert(x == 1)\nprint(x)", "<test>")

    assert "#include <stdio.h>" in c_code
    assert "#include <stdlib.h>" in c_code
    assert "#include <math.h>" not in c_code
    assert "#include <string.h>" not in c_code
    assert "print(" not in c_code
    assert "_oda_assert" in c_code
    assert compile_and_run("int x = 1\nassert(x == 1)\nprint(x)") == "1"

def test_std_string_module_requires_explicit_import_and_header():
    src = '''
import std.string as strings
uint length = strings.strlen("abcd")
print(length)
'''
    c_code = _pipeline(src, "<test>")

    assert "#include <string.h>" in c_code
    assert "strlen(\"abcd\")" in c_code
    assert "strlen(char*" not in c_code
    assert compile_and_run(src) == "4"

def test_std_math_module_imports_math_header_and_uses_c_symbol():
    src = '''
import std.math
float value = math.sin(0.0)
print(value)
'''
    c_code = _pipeline(src, "<test>")

    assert "#include <math.h>" in c_code
    assert "sin(0.0)" in c_code
    assert "sin(double" not in c_code

    with tempfile.TemporaryDirectory() as tmp:
        c_path = Path(tmp) / "out.c"
        bin_path = Path(tmp) / "out"
        c_path.write_text(c_code)
        subprocess.run(
            ["gcc", str(c_path), *TEST_CFLAGS, "-Wall", "-Wextra", "-Werror", "-o", str(bin_path), "-lm"],
            check=True,
            capture_output=True,
            text=True,
        )
        result = run_generated_binary([str(bin_path)], capture_output=True, text=True)

    assert result.stdout.strip() == "0.000000"

def test_std_module_functions_are_not_available_without_import():
    with pytest.raises(SystemExit):
        compile_and_run("float value = math.sin(0.0)\nprint(value)")

def test_null_coalescing():
    src = 'string? x = null\nprint(x ?? "default")'
    assert compile_and_run(src) == "default"

def test_range_loop():
    src = 'for (int i in 0..3) { print(i) }'
    assert compile_and_run(src) == "0\n1\n2"

def test_array_iteration():
    src = 'int[] nums = [10, 20, 30]\nfor (int n in nums) { print(n) }'
    assert compile_and_run(src) == "10\n20\n30"

def test_array_iteration_with_index_and_value():
    src = '''
int[] nums = [10, 20, 30]
for (int i, int n in nums) {
    print(i * 100 + n)
}
'''
    assert compile_and_run(src) == "10\n120\n230"

def test_string_iteration_with_index_and_value_reversed():
    src = '''
string text = "abc"
for (int i, char ch in text reversed) {
    print(i * 100 + ch)
}
'''
    assert compile_and_run(src) == "299\n198\n97"

def test_raii_destructor_called():
    src = '''
class Box {
    construct() { print("open") }
    destruct()  { print("close") }
}
Box b = Box()
'''
    assert compile_and_run(src) == "open\nclose"

def test_private_member_rejected():
    # The pipeline should raise SystemExit if semantic errors occur
    with pytest.raises(SystemExit):
        compile_and_run('class A { int _x }\nA a = A()\nprint(a._x)')

def test_nested_range_loops():
    src = '''
for (int i in 0..2) {
    for (int j in 0..3) {
        print(i * 10 + j)
    }
}
'''
    assert compile_and_run(src) == "0\n1\n2\n10\n11\n12"

def test_nested_c_style_loops_with_updates():
    src = '''
for (int i = 0; i < 2; i += 1) {
    for (int j = 0; j < 2; j += 1) {
        print(i + j)
    }
}
'''
    assert compile_and_run(src) == "0\n1\n1\n2"

def test_nested_while_loops():
    src = '''
int i = 0
while (i < 2) {
    int j = 0
    while (j < 2) {
        print(i * 2 + j)
        j += 1
    }
    i += 1
}
'''
    assert compile_and_run(src) == "0\n1\n2\n3"

def test_two_dimensional_array_indexing():
    src = '''
int[][] matrix = [[1, 2], [3, 4]]
print(matrix[1][0])
print(matrix[0][1])
'''
    assert compile_and_run(src) == "3\n2"

def test_two_dimensional_array_iteration_rows():
    src = '''
int[][] matrix = [[1, 2], [3, 4]]
for (int[] row in matrix) {
    print(row[0] + row[1])
}
'''
    assert compile_and_run(src) == "3\n7"

def test_three_dimensional_array_indexing():
    src = '''
int[][][] cube = [[[1, 2], [3, 4]], [[5, 6], [7, 8]]]
print(cube[1][0][1])
print(cube[0][1][0])
'''
    assert compile_and_run(src) == "6\n3"

def test_string_interpolation_with_string_identifier():
    src = '''
string name = "Oda"
print("Hello {name}")
'''
    assert compile_and_run(src) == "Hello Oda"

def test_string_interpolation_with_numeric_identifier():
    src = '''
int speed = 42
print("speed={speed}")
'''
    assert compile_and_run(src) == "speed=42"

def test_string_interpolation_with_expression():
    src = '''
int a = 1
int b = 2
print("a+b= {a+b}")
'''
    assert compile_and_run(src) == "a+b= 3"

def test_string_interpolation_assignment_uses_standard_c_temp():
    src = '''
string name = "Oda"
string msg = "hello {name}"
print(msg)
'''
    assert compile_and_run(src) == "hello Oda"

def test_user_function_value_argument_compiles():
    src = '''
func add1(int x) -> int { return x + 1 }
print(add1(41))
'''
    assert compile_and_run(src) == "42"

def test_extern_standard_c_function_call_compiles_and_runs():
    src = '''
extern func abs(int value) -> int
int distance = abs(-42)
print(distance)
'''
    c_code = _pipeline(src, "<test>")
    assert "int abs(int value);" in c_code
    assert "int abs(int value) {" not in c_code

    with tempfile.TemporaryDirectory() as tmp:
        c_path = Path(tmp) / "out.c"
        bin_path = Path(tmp) / "out"
        c_path.write_text(c_code)
        subprocess.run(
            ["gcc", str(c_path), *TEST_CFLAGS, "-Wall", "-Wextra", "-Werror", "-o", str(bin_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = run_generated_binary([str(bin_path)], capture_output=True, text=True)

    assert result.stdout.strip() == "42"

def test_ref_parameter_identifier_argument_compiles():
    src = '''
func touch(ref int x) { print(x) }
int value = 7
touch(ref value)
'''
    assert compile_and_run(src) == "7"

def test_uint_literal_and_explicit_as_cast_compile_and_run():
    src = '''
uint positive = 5u
int narrowed = 3.9 as int
uint explicit_unsigned = -1 as uint
print(positive)
print(narrowed)
print(explicit_unsigned > 0u)
'''
    c_code = _pipeline(src, "<test>")
    assert "unsigned int positive = 5u;" in c_code
    assert "int narrowed = ((int)(3.9));" in c_code
    assert "unsigned int explicit_unsigned = ((unsigned int)((-1)));" in c_code

    with tempfile.TemporaryDirectory() as tmp:
        c_path = Path(tmp) / "out.c"
        bin_path = Path(tmp) / "out"
        c_path.write_text(c_code)
        subprocess.run(
            ["gcc", str(c_path), *TEST_CFLAGS, "-Wall", "-Wextra", "-Werror", "-o", str(bin_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = run_generated_binary([str(bin_path)], capture_output=True, text=True)

    assert result.stdout.strip() == "5\n3\n1"

def test_c_style_explicit_cast_compile_and_run():
    src = '''
float f = 8.75
int whole = (int)f
uint count = (uint)whole
print(count)
'''
    c_code = _pipeline(src, "<test>")
    assert "int whole = ((int)(f));" in c_code
    assert "unsigned int count = ((unsigned int)(whole));" in c_code
    assert compile_and_run(src) == "8"

def test_guard_success_continues_after_unwrap():
    src = '''
func check() {
    guard string content = readFile("README.md") else {
        when (FileNotFound) {
            print("missing")
            return
        }
    }
    print("loaded")
}
check()
'''
    assert compile_and_run(src) == "loaded"

def test_guard_failure_exits_from_function():
    src = '''
func check() {
    guard string content = readFile("definitely_missing_oda_file.txt") else {
        when (FileNotFound) {
            print("missing")
            return
        }
    }
    print("loaded")
}
check()
'''
    assert compile_and_run(src) == "missing"

def test_guard_error_dispatch_generates_strict_c_and_runs():
    src = '''
func check() {
    guard string content = readFile("definitely_missing_oda_file.txt") else {
        when (FileNotFound) {
            print("missing")
            return
        }
        when (IoError) {
            print("io")
            return
        }
    }
    print(content)
}
check()
'''
    c_code = _pipeline(src, "<test>")
    assert "typedef enum {" in c_code
    assert "ODA_ERROR_FILE_NOT_FOUND" in c_code
    assert "_oda_error == ODA_ERROR_FILE_NOT_FOUND" in c_code
    assert "} else if (_oda_error == ODA_ERROR_IO)" in c_code
    assert "/* when(" not in c_code

    with tempfile.TemporaryDirectory() as tmp:
        c_path = Path(tmp) / "out.c"
        bin_path = Path(tmp) / "out"
        c_path.write_text(c_code)
        subprocess.run(
            ["gcc", str(c_path), *TEST_CFLAGS, "-Wall", "-Wextra", "-Werror", "-o", str(bin_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = run_generated_binary([str(bin_path)], capture_output=True, text=True)

    assert result.stdout.strip() == "missing"

def test_enum_match_transpiles_compiles_and_runs_with_strict_warnings():
    src = '''
enum Mode { Idle, Busy, Done }

func describe(Mode mode) {
    match (mode) {
        Mode.Idle { print("idle") }
        Mode.Busy { print("busy") }
        _ { print("done") }
    }
}

Mode mode = Mode.Busy
describe(mode)
'''
    c_code = _pipeline(src, "<test>")
    assert "typedef enum {" in c_code
    assert "Mode_Idle," in c_code
    assert "Mode_Busy," in c_code
    assert "Mode_Done" in c_code
    assert "} Mode;" in c_code
    assert "Mode mode = Mode_Busy;" in c_code
    assert "if (mode == Mode_Idle)" in c_code

    with tempfile.TemporaryDirectory() as tmp:
        c_path = Path(tmp) / "out.c"
        bin_path = Path(tmp) / "out"
        c_path.write_text(c_code)
        subprocess.run(
            ["gcc", str(c_path), "-Wall", "-Wextra", "-Werror", "-o", str(bin_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run([str(bin_path)], capture_output=True, text=True, check=True)

    assert result.stdout.strip() == "busy"

def test_guard_case_must_exit_in_pipeline():
    src = '''
guard string content = readFile("definitely_missing_oda_file.txt") else {
    when (FileNotFound) {
        print("missing")
    }
}
'''
    with pytest.raises(SystemExit):
        compile_and_run(src)

def test_cli_json_output_for_semantic_errors():
    with tempfile.TemporaryDirectory() as tmp:
        src_path = Path(tmp) / "bad_semantic.oda"
        src_path.write_text("print(missing_value)\n")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "oda"),
                "transpile",
                str(src_path),
                "--output-format=json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload == [
        {
            "file": str(src_path),
            "line": 1,
            "column": 7,
            "error_type": "SemanticError",
            "message": "Undefined variable 'missing_value'",
        }
    ]

def test_cli_json_output_for_parser_errors():
    with tempfile.TemporaryDirectory() as tmp:
        src_path = Path(tmp) / "bad_parse.oda"
        src_path.write_text("int = 1\n")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "oda"),
                "transpile",
                str(src_path),
                "--output-format=json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert len(payload) == 1
    assert payload[0]["file"] == str(src_path)
    assert payload[0]["line"] == 1
    assert payload[0]["error_type"] == "ParserError"
    assert "Expected variable name" in payload[0]["message"]

def test_cli_export_ast_outputs_machine_readable_json():
    with tempfile.TemporaryDirectory() as tmp:
        src_path = Path(tmp) / "ast.oda"
        src_path.write_text("int answer = 42\nprint(answer)\n")
        result = subprocess.run(
            [sys.executable, str(ROOT / "oda"), "export-ast", str(src_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["node_type"] == "Program"
    statements = payload["statements"]
    assert any(
        stmt["node_type"] == "VarDeclaration" and stmt["name"] == "answer"
        for stmt in statements
    )
    assert any(stmt["node_type"] == "ExpressionStatement" for stmt in statements)

def test_cli_export_ast_flag_outputs_machine_readable_json():
    with tempfile.TemporaryDirectory() as tmp:
        src_path = Path(tmp) / "ast_flag.oda"
        src_path.write_text("int answer = 42\n")
        result = subprocess.run(
            [sys.executable, str(ROOT / "oda"), "--export-ast", str(src_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["node_type"] == "Program"

def test_cli_export_ast_json_errors_on_parse_failure():
    with tempfile.TemporaryDirectory() as tmp:
        src_path = Path(tmp) / "bad_ast.oda"
        src_path.write_text("int = 1\n")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "oda"),
                "export-ast",
                str(src_path),
                "--output-format=json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert len(payload) == 1
    assert payload[0]["error_type"] == "ParserError"
