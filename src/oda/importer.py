import os
from pathlib import Path
from . import ast_nodes as ast
from .lexer import Lexer
from .parser import Parser
from .errors import SemanticError

class Importer:
    def __init__(self, entry_file: str):
        self.base_dir = Path(entry_file).parent.resolve()
        self.visited = set()
        self.combined_statements = []

    def load_entry(self, source: str, filename: str) -> ast.Program:
        tokens = Lexer(source, filename).tokenize()
        prog = Parser(tokens, filename).parse()
        self.visited.add(Path(filename).resolve())
        
        # We start AST transformation
        # Since it's the entry module, it doesn't need its own prefix, it's global
        self._process_program(prog, prefix="", current_file=filename)
        
        final_prog = ast.Program(statements=self.combined_statements)
        return final_prog

    def _process_program(self, prog: ast.Program, prefix: str, current_file: str):
        # 1. Collect top-level declarations in this module
        mod_decls = {} # original_name -> mangled_name
        for stmt in prog.statements:
            if isinstance(stmt, ast.FuncDeclaration):
                mangled = f"{prefix}_{stmt.name}" if prefix else stmt.name
                mod_decls[stmt.name] = mangled
                stmt.name = mangled
            elif isinstance(stmt, ast.ClassDeclaration):
                mangled = f"{prefix}_{stmt.name}" if prefix else stmt.name
                mod_decls[stmt.name] = mangled
                stmt.name = mangled
                # For classes, we don't mangle methods here, codegen handles Class_method
            elif isinstance(stmt, ast.EnumDeclaration):
                mangled = f"{prefix}_{stmt.name}" if prefix else stmt.name
                mod_decls[stmt.name] = mangled
                stmt.name = mangled
            elif isinstance(stmt, ast.VarDeclaration):
                mangled = f"{prefix}_{stmt.name}" if prefix else stmt.name
                mod_decls[stmt.name] = mangled
                stmt.name = mangled

        # 2. Process imports and build alias map
        alias_map = {} # alias -> module_prefix
        direct_imports = {} # local_name -> mangled_name

        new_stmts = []
        for stmt in prog.statements:
            if isinstance(stmt, ast.ImportStatement):
                # Resolve the module
                mod_path_str = stmt.module_path
                if mod_path_str.endswith(".oda"):
                    mod_path_str = mod_path_str[:-4]
                
                parts = mod_path_str.split('.')
                mod_file = self.base_dir.joinpath(*parts).with_suffix('.oda')
                
                if not mod_file.exists():
                    raise SemanticError(f"Module not found: {stmt.module_path}", stmt.line, stmt.column, current_file)

                mod_prefix = "_".join(parts)
                
                if stmt.names: # from a import b, c
                    for n in stmt.names:
                        if n.startswith('_'):
                            raise SemanticError(f"Cannot import private member '{n}'", stmt.line, stmt.column, current_file)
                        direct_imports[n] = f"{mod_prefix}_{n}"
                else: # import a.b as c or import a.b
                    alias = stmt.alias if stmt.alias else parts[-1]
                    alias_map[alias] = mod_prefix
                
                # Load the module if not visited
                if mod_file.resolve() not in self.visited:
                    self.visited.add(mod_file.resolve())
                    src = mod_file.read_text()
                    tokens = Lexer(src, str(mod_file)).tokenize()
                    mod_prog = Parser(tokens, str(mod_file)).parse()
                    self._process_program(mod_prog, prefix=mod_prefix, current_file=str(mod_file))

            else:
                new_stmts.append(stmt)
        
        # 3. Rewrite all expressions in this module
        self._rewrite_nodes(new_stmts, mod_decls, alias_map, direct_imports)
        
        # Add to combined (Unity Build)
        self.combined_statements.extend(new_stmts)

    def _rewrite_nodes(self, nodes, mod_decls, alias_map, direct_imports):
        if isinstance(nodes, list):
            for n in nodes:
                self._rewrite_nodes(n, mod_decls, alias_map, direct_imports)
            return

        if not nodes:
            return

        # Replace identifiers
        if isinstance(nodes, ast.Identifier):
            # If it's a module level decl in this module
            if nodes.name in mod_decls:
                nodes.name = mod_decls[nodes.name]
            # If it's a directly imported name
            elif nodes.name in direct_imports:
                nodes.name = direct_imports[nodes.name]
            return

        if isinstance(nodes, ast.TypeAnnotation):
            if nodes.base_type in mod_decls:
                nodes.base_type = mod_decls[nodes.base_type]
            elif nodes.base_type in direct_imports:
                nodes.base_type = direct_imports[nodes.base_type]
            return

        # Rewrite MemberAccess for alias_map (e.g., sns.read -> hw_sensor_read)
        if isinstance(nodes, ast.MemberAccess):
            if isinstance(nodes.obj, ast.Identifier) and nodes.obj.name in alias_map:
                mod_prefix = alias_map[nodes.obj.name]
                if nodes.member.startswith('_'):
                    # Could raise an error, but we just mangle it. The error check is usually better.
                    # For now just let it fail at C compile time if not found, or rewrite.
                    pass
                # Transform this MemberAccess into a simple Identifier
                # Wait, we can't easily replace the object reference if we are modifying it in-place.
                # Actually, ast.CallExpr has a `callee`. If `callee` is MemberAccess, we can rewrite it.
                # We need to return the new node.
            pass # See CallExpr below

        # Traverse fields
        if hasattr(nodes, '__dict__'):
            for k, v in vars(nodes).items():
                if k in ('line', 'column'): continue
                
                # Special handling for MemberAccess rewrite
                if k == 'callee' and isinstance(v, ast.MemberAccess):
                    if isinstance(v.obj, ast.Identifier) and v.obj.name in alias_map:
                        mod_prefix = alias_map[v.obj.name]
                        if v.member.startswith('_'):
                            raise SemanticError(f"Cannot access private member '{v.member}' of module '{v.obj.name}'", v.line, v.column, "Unknown")
                        new_name = f"{mod_prefix}_{v.member}"
                        setattr(nodes, k, ast.Identifier(name=new_name, line=v.line, column=v.column))
                        continue
                
                if k == 'expr' and isinstance(v, ast.MemberAccess):
                    if isinstance(v.obj, ast.Identifier) and v.obj.name in alias_map:
                        mod_prefix = alias_map[v.obj.name]
                        if v.member.startswith('_'):
                            raise SemanticError(f"Cannot access private member '{v.member}' of module '{v.obj.name}'", v.line, v.column, "Unknown")
                        new_name = f"{mod_prefix}_{v.member}"
                        setattr(nodes, k, ast.Identifier(name=new_name, line=v.line, column=v.column))
                        continue

                self._rewrite_nodes(v, mod_decls, alias_map, direct_imports)
