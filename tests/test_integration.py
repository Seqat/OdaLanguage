import pytest
import subprocess
import tempfile
from pathlib import Path
from src.oda.main import _pipeline

from tests.c_sanitize import TEST_CFLAGS, run_generated_binary

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

def test_null_coalescing():
    src = 'string? x = null\nprint(x ?? "default")'
    assert compile_and_run(src) == "default"

def test_range_loop():
    src = 'for (int i in 0..3) { print(i) }'
    assert compile_and_run(src) == "0\n1\n2"

def test_array_iteration():
    src = 'int[] nums = [10, 20, 30]\nfor (int n in nums) { print(n) }'
    assert compile_and_run(src) == "10\n20\n30"

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

def test_ref_parameter_identifier_argument_compiles():
    src = '''
func touch(ref int x) { print(x) }
int value = 7
touch(ref value)
'''
    assert compile_and_run(src) == "7"

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
