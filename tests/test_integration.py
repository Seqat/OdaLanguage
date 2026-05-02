import pytest
import subprocess
import tempfile
import os
from pathlib import Path
from src.oda.main import _pipeline

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
        subprocess.run(["gcc", str(c_path), "-o", str(bin_path), "-O2"],
                       check=True, capture_output=True)
        result = subprocess.run([str(bin_path)], capture_output=True, text=True)
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
    from src.oda.errors import SemanticError
    # The pipeline should raise SystemExit if semantic errors occur
    with pytest.raises(SystemExit):
        compile_and_run('class A { int _x }\nA a = A()\nprint(a._x)')
