def patch_file(filepath, replacements):
    with open(filepath, "r") as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"Warning: {old!r} not found in {filepath}")
        content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)

importer_replacements = [
    (
        'raise SemanticError(\n                        f"Module \'{stmt.module_path}\' exists but cannot be loaded",\n                        stmt.line, stmt.column, current_file\n                    )',
        'raise SemanticError(\n                        f"Module \'{stmt.module_path}\' exists but cannot be loaded",\n                        stmt.line, stmt.column, current_file, code="E4002"\n                    )'
    ),
    (
        'raise SemanticError(\n                                f"Cannot import \'{n}\' from \'{stmt.module_path}\' (not found)",\n                                stmt.line, stmt.column, current_file\n                            )',
        'raise SemanticError(\n                                f"Cannot import \'{n}\' from \'{stmt.module_path}\' (not found)",\n                                stmt.line, stmt.column, current_file, code="E4004"\n                            )'
    )
]

errors_replacements = [
    (
        'ERROR_CODES = {\n    "E0000": "Unknown error",\n}',
        'ERROR_CODES = {\n    "E0000": "Unknown error",\n    **{f"E10{i:02d}": "Lexer error" for i in range(1, 10)},\n    **{f"E20{i:02d}": "Parser error" for i in range(1, 10)},\n    **{f"E30{i:02d}": "Semantic error" for i in range(1, 46)},\n    **{f"E400{i}": "Import error" for i in range(1, 6)}\n}'
    )
]

patch_file("src/oda/importer.py", importer_replacements)
patch_file("src/oda/errors.py", errors_replacements)

