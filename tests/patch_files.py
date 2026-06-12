def patch_file(filepath, replacements):
    with open(filepath, "r") as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"Warning: {old!r} not found in {filepath}")
        content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)

semantic_replacements = [
    (
        'def _err(self, msg: str, node: ast.Node):',
        'def _err(self, msg: str, node: ast.Node, code: str = "E3000", hint: str | None = None):'
    ),
    (
        'self.errors.append(SemanticError(msg, node.line, node.column, self.filename))',
        'self.errors.append(SemanticError(msg, node.line, node.column, self.filename, code=code, hint=hint))'
    ),
    # Hints
    (
        'self._err(f"Cannot coerce \'{init_type}\' to \'{full}\'", stmt)',
        'hint = f"as {full}" if init_type in ("int", "uint") and full in ("int", "uint") else None\n                    self._err(f"Cannot coerce \'{init_type}\' to \'{full}\'", stmt, code="E3001", hint=hint)'
    ),
    (
        'self._err("guard else block must exit the current scope (return or break required)", case)',
        'self._err("guard else block must exit the current scope (return or break required)", case, code="E3002", hint="return, break, continue")'
    ),
    (
        'self._err(\n                        f"Cannot access private member \'{expr.member}\' outside class \'{owner_class}\'",\n                        expr\n                    )',
        'self._err(\n                        f"Cannot access private member \'{expr.member}\' outside class \'{owner_class}\'",\n                        expr,\n                        code="E3003",\n                        hint=f"Owner: {owner_class}"\n                    )'
    ),
    # Other error codes
    ('self._err(f"Cannot iterate over unknown-size collection", stmt)', 'self._err(f"Cannot iterate over unknown-size collection", stmt, code="E3004")'),
    ('self._err(f"Function must return \'{expected}\'", stmt)', 'self._err(f"Function must return \'{expected}\'", stmt, code="E3005")'),
    ('self._err("Cannot return a void value", stmt)', 'self._err("Cannot return a void value", stmt, code="E3006")'),
    ('self._err(f"Cannot return \'{actual}\' from function returning \'{expected}\'", stmt)', 'self._err(f"Cannot return \'{actual}\' from function returning \'{expected}\'", stmt, code="E3007")'),
    ('self._err("break/continue cannot be used outside a loop", stmt)', 'self._err("break/continue cannot be used outside a loop", stmt, code="E3008")'),
    ('self._err(f"Unknown error type \'{case.error_type}\'", case)', 'self._err(f"Unknown error type \'{case.error_type}\'", case, code="E3009")'),
    ('self._err(f"Match pattern type \'{pattern_type}\' does not match \'{match_type}\'", arm)', 'self._err(f"Match pattern type \'{pattern_type}\' does not match \'{match_type}\'", arm, code="E3010")'),
    ('self._err(f"Unknown type \'{param.type_ann.base_type}\'", param)', 'self._err(f"Unknown type \'{param.type_ann.base_type}\'", param, code="E3011")'),
    ('self._err(\n                f"Parameter \'{param.name}\' of function \'{owner_name}\' has class "\n                f"\'{param.type_ann.base_type}\' with heap-allocated fields and must be passed by ref",\n                param,\n            )', 'self._err(\n                f"Parameter \'{param.name}\' of function \'{owner_name}\' has class "\n                f"\'{param.type_ann.base_type}\' with heap-allocated fields and must be passed by ref",\n                param, code="E3012"\n            )'),
    ('self._err(f"Unknown type \'{base}\'", stmt)', 'self._err(f"Unknown type \'{base}\'", stmt, code="E3013")'),
    ('self._err("Cannot assign a void value to a variable", stmt)', 'self._err("Cannot assign a void value to a variable", stmt, code="E3014")'),
    ('self._err(f"Cannot assign null to non-nullable \'{full}\'", stmt)', 'self._err(f"Cannot assign null to non-nullable \'{full}\'", stmt, code="E3015")'),
    ('self._err(f"Unknown return type \'{stmt.return_type.base_type}\'", stmt)', 'self._err(f"Unknown return type \'{stmt.return_type.base_type}\'", stmt, code="E3016")'),
    ('self._err(f"Not all code paths return a value from function \'{stmt.name}\'", stmt)', 'self._err(f"Not all code paths return a value from function \'{stmt.name}\'", stmt, code="E3017")'),
    ('self._err(f"Duplicate enum variant \'{variant}\' in enum \'{stmt.name}\'", stmt)', 'self._err(f"Duplicate enum variant \'{variant}\' in enum \'{stmt.name}\'", stmt, code="E3018")'),
    ('self._err(f"Cannot pass \'{actual}\' as ref \'{expected}\'", node)', 'self._err(f"Cannot pass \'{actual}\' as ref \'{expected}\'", node, code="E3019")'),
    ('self._err(f"Cannot pass \'{actual}\' to parameter of type \'{expected}\'", node)', 'self._err(f"Cannot pass \'{actual}\' to parameter of type \'{expected}\'", node, code="E3020")'),
    ('self._err(f"Function \'print\' expects 0 or 1 argument(s), got {len(call.args)}", call)', 'self._err(f"Function \'print\' expects 0 or 1 argument(s), got {len(call.args)}", call, code="E3021")'),
    ('self._err("Function \'print\' does not accept ref arguments", call)', 'self._err("Function \'print\' does not accept ref arguments", call, code="E3022")'),
    ('self._err(f"Function \'{name}\' expects {len(params)} argument(s), got {len(call.args)}", call)', 'self._err(f"Function \'{name}\' expects {len(params)} argument(s), got {len(call.args)}", call, code="E3023")'),
    ('self._err(f"Parameter \'{param.name}\' of function \'{name}\' must be passed with \'ref\'", arg)', 'self._err(f"Parameter \'{param.name}\' of function \'{name}\' must be passed with \'ref\'", arg, code="E3024")'),
    ('self._err(f"Cannot pass non-assignable expression as ref parameter \'{param.name}\'", arg)', 'self._err(f"Cannot pass non-assignable expression as ref parameter \'{param.name}\'", arg, code="E3025")'),
    ('self._err(\n                        f"Cannot pass class \'{param.type_ann.base_type}\' with heap-allocated fields by value; "\n                        "declare the parameter as ref",\n                        arg,\n                    )', 'self._err(\n                        f"Cannot pass class \'{param.type_ann.base_type}\' with heap-allocated fields by value; "\n                        "declare the parameter as ref",\n                        arg, code="E3026"\n                    )'),
    ('self._err(f"Parameter \'{param.name}\' of function \'{name}\' is not a ref parameter", arg)', 'self._err(f"Parameter \'{param.name}\' of function \'{name}\' is not a ref parameter", arg, code="E3027")'),
    ('self._err(f"Undefined function \'{name}\'", call.callee)', 'self._err(f"Undefined function \'{name}\'", call.callee, code="E3028")'),
    ('self._err(f"Cannot call method \'{call.callee.member}\' on non-class type \'{obj_type}\'", call.callee)', 'self._err(f"Cannot call method \'{call.callee.member}\' on non-class type \'{obj_type}\'", call.callee, code="E3029")'),
    ('self._err(f"Class \'{obj_type}\' has no method \'{call.callee.member}\'", call.callee)', 'self._err(f"Class \'{obj_type}\' has no method \'{call.callee.member}\'", call.callee, code="E3030")'),
    ('self._err("Unsupported call target", call)', 'self._err("Unsupported call target", call, code="E3031")'),
    ('self._err(f"Unknown private field \'{expr.name}\' in class \'{self._current_class}\'", expr)', 'self._err(f"Unknown private field \'{expr.name}\' in class \'{self._current_class}\'", expr, code="E3032")'),
    ('self._err(f"Undefined variable \'{expr.name}\'", expr)', 'self._err(f"Undefined variable \'{expr.name}\'", expr, code="E3033")'),
    ('self._err(f"Cannot reassign immutable variable \'{expr.target.name}\' (declared with \'stay\')", expr)', 'self._err(f"Cannot reassign immutable variable \'{expr.target.name}\' (declared with \'stay\')", expr, code="E3034")'),
    ('self._err("Cannot modify element of immutable array", expr.target)', 'self._err("Cannot modify element of immutable array", expr.target, code="E3035")'),
    ('self._err("Cannot use a void expression in a binary operation", expr)', 'self._err("Cannot use a void expression in a binary operation", expr, code="E3036")'),
    ('self._err(f"Invalid operands for \'{expr.op}\': \'{left_type}\' and \'{right_type}\'", expr)', 'self._err(f"Invalid operands for \'{expr.op}\': \'{left_type}\' and \'{right_type}\'", expr, code="E3037")'),
    ('self._err("Cannot use a void function call as an argument", a)', 'self._err("Cannot use a void function call as an argument", a, code="E3038")'),
    ('self._err(f"Enum \'{expr.obj.name}\' has no variant \'{expr.member}\'", expr)', 'self._err(f"Enum \'{expr.obj.name}\' has no variant \'{expr.member}\'", expr, code="E3039")'),
    ('self._err(f"Unknown private member \'{expr.member}\'", expr)', 'self._err(f"Unknown private member \'{expr.member}\'", expr, code="E3040")'),
    ('self._err("Array index must be an integer expression", expr.index)', 'self._err("Array index must be an integer expression", expr.index, code="E3041")'),
    ('self._err("Array dimensions must be integer expressions", expr)', 'self._err("Array dimensions must be integer expressions", expr, code="E3042")'),
    ('self._err(f"Unknown cast target type \'{name}\'", expr)', 'self._err(f"Unknown cast target type \'{name}\'", expr, code="E3043")'),
    ('self._err(f"Cannot cast to non-scalar type \'{dest}\'", expr)', 'self._err(f"Cannot cast to non-scalar type \'{dest}\'", expr, code="E3044")'),
    ('self._err(f"Cannot cast \'{source}\' to \'{dest}\'", expr)', 'self._err(f"Cannot cast \'{source}\' to \'{dest}\'", expr, code="E3045")'),
]

importer_replacements = [
    ('raise SemanticError(f"Module not found: {stmt.module_path}", stmt.line, stmt.column, current_file)', 'raise SemanticError(f"Module not found: {stmt.module_path}", stmt.line, stmt.column, current_file, code="E4001")'),
    ('raise SemanticError(\n                        f"Module \'{stmt.module_path}\' exists but cannot be loaded",\n                        stmt.line, stmt.column, current_file)', 'raise SemanticError(\n                        f"Module \'{stmt.module_path}\' exists but cannot be loaded",\n                        stmt.line, stmt.column, current_file, code="E4002")'),
    ('raise SemanticError(f"Cannot import private member \'{n}\'", stmt.line, stmt.column, current_file)', 'raise SemanticError(f"Cannot import private member \'{n}\'", stmt.line, stmt.column, current_file, code="E4003")'),
    ('raise SemanticError(\n                                f"Cannot import \'{n}\' from \'{stmt.module_path}\' (not found)",\n                                stmt.line, stmt.column, current_file)', 'raise SemanticError(\n                                f"Cannot import \'{n}\' from \'{stmt.module_path}\' (not found)",\n                                stmt.line, stmt.column, current_file, code="E4004")'),
    ('raise SemanticError(f"Cannot access private member \'{v.member}\' of module \'{v.obj.name}\'", v.line, v.column, "Unknown")', 'raise SemanticError(f"Cannot access private member \'{v.member}\' of module \'{v.obj.name}\'", v.line, v.column, "Unknown", code="E4005")'),
]

patch_file("src/oda/semantic.py", semantic_replacements)
patch_file("src/oda/importer.py", importer_replacements)
