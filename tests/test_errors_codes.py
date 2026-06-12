import ast
import json
import pytest
from pathlib import Path

from src.oda.main import _pipeline
from src.oda.errors import SemanticError, OdaError

def test_error_registry_no_duplicates():
    # Read errors.py and parse it
    errors_file = Path(__file__).parent.parent / "src" / "oda" / "errors.py"
    tree = ast.parse(errors_file.read_text())
    
    # Find the ERROR_CODES assignment
    dict_node = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "ERROR_CODES":
            dict_node = node.value
            break
            
    assert dict_node is not None, "ERROR_CODES not found in errors.py"
    assert isinstance(dict_node, ast.Dict), "ERROR_CODES must be a dict"
    
    # Extract keys and check for duplicates (using ERROR_CODES.keys() directly via import)
    from src.oda.errors import ERROR_CODES
    keys = list(ERROR_CODES.keys())
    assert len(keys) == len(set(keys)), f"Duplicate error codes found"

def run_pipeline_for_json(source: str) -> dict:
    try:
        _pipeline(source, "test.oda", output_format="json")
        pytest.fail("Expected pipeline to fail")
    except SystemExit:
        import sys
        # Note: _pipeline in main.py prints json to sys.stderr, so we need to capture stderr.
        pass

def test_json_error_format_and_hints(capsys):
    source_int_uint = "uint x = 5"
    with pytest.raises(SystemExit):
        _pipeline(source_int_uint, "test1.oda", output_format="json")
    stderr = capsys.readouterr().err
    errors = json.loads(stderr)
    assert len(errors) == 1
    assert "code" in errors[0]
    import re
    assert re.match(r"^E\d{4}$", errors[0]["code"])
    assert "as uint" in (errors[0].get("hint") or "")
    
    source_private = "class C { int _foo }\nC c = C()\nc._foo\n"
    with pytest.raises(SystemExit):
        _pipeline(source_private, "test2.oda", output_format="json")
    stderr = capsys.readouterr().err
    errors = json.loads(stderr)
    assert "code" in errors[0]
    assert re.match(r"^E\d{4}$", errors[0]["code"])
    assert "C" in (errors[0].get("hint") or "")

    source_guard = "extern func readFile(string f) -> string\nguard string content = readFile(\"x\") else { when (FileNotFound) { int y = 1 } }\n"
    with pytest.raises(SystemExit):
        _pipeline(source_guard, "test3.oda", output_format="json")
    stderr = capsys.readouterr().err
    errors = json.loads(stderr)
    assert "code" in errors[0]
    assert re.match(r"^E\d{4}$", errors[0]["code"])
    hint = errors[0].get("hint") or ""
    assert "return" in hint or "break" in hint or "continue" in hint

def test_all_raised_codes_in_registry():
    import re
    from src.oda.errors import ERROR_CODES
    
    raised_codes = set()
    src_dir = Path(__file__).parent.parent / "src" / "oda"
    for filename in ("semantic.py", "parser.py"):
        content = (src_dir / filename).read_text(encoding="utf-8")
        for m in re.finditer(r"code\s*=\s*[\"'](E\d{4})[\"']", content):
            raised_codes.add(m.group(1))
            
    for code in raised_codes:
        assert code in ERROR_CODES, f"Code '{code}' raised in parser.py or semantic.py is not registered in ERROR_CODES"


