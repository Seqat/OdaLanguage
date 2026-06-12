import ast
import tokenize
import io

def rewrite_file(filepath, err_name, code_prefix, start_num):
    with open(filepath, 'r') as f:
        source = f.read()

    # We will use the ast module to find all calls to `self._err` or `SemanticError`
    tree = ast.parse(source)

    class CallVisitor(ast.NodeVisitor):
        def __init__(self):
            self.calls = []

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute) and node.func.attr == err_name:
                self.calls.append(node)
            elif isinstance(node.func, ast.Name) and node.func.id == err_name:
                self.calls.append(node)
            self.generic_visit(node)

    visitor = CallVisitor()
    visitor.visit(tree)

    # Sort calls by end_lineno and end_col_offset descending to modify from bottom up
    calls = sorted(visitor.calls, key=lambda n: (n.end_lineno, n.end_col_offset), reverse=True)

    lines = source.splitlines()

    code_counter = start_num + len(calls) - 1

    for call in calls:
        # Check if code is already in kwargs
        has_code = any(k.arg == 'code' for k in call.keywords)
        if has_code:
            code_counter -= 1
            continue
            
        c = code_counter
        code_counter -= 1

        # The end of the call is at line: end_lineno (1-indexed), col: end_col_offset (0-indexed)
        l = call.end_lineno - 1
        col = call.end_col_offset - 1 # this should be the ')'
        
        # Verify it's actually ')'
        # Some versions of Python might point end_col_offset past the ')'
        while col > 0 and lines[l][col] != ')':
            col -= 1

        lines[l] = lines[l][:col] + f', code="{code_prefix}{c}"' + lines[l][col:]

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines) + '\n')

rewrite_file("src/oda/semantic.py", "_err", "E30", 10)
rewrite_file("src/oda/importer.py", "SemanticError", "E40", 10)

