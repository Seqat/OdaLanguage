"""Semantic analyzer for OdaLanguage — type checking, scope, coercion rules."""
from __future__ import annotations
from . import ast_nodes as ast
from .errors import SemanticError

# Widening-only coercion table: source → allowed targets
_WIDENING = {
    "int":   {"float"},
    "uint":  {"float"},
    "float": set(),
    "char":  {"string"},
    "bool":  set(),
    "string": set(),
}

_STANDARD_ERROR_TYPES = {
    "FileNotFound",
    "PermissionDenied",
    "IoError",
}


class Symbol:
    def __init__(self, name: str, type_ann: ast.TypeAnnotation,
                 is_immutable: bool = False, is_ref: bool = False):
        self.name = name
        self.type_ann = type_ann
        self.is_immutable = is_immutable
        self.is_ref = is_ref


class Scope:
    def __init__(self, parent: Scope | None = None, name: str = "global"):
        self.parent = parent
        self.name = name
        self.symbols: dict[str, Symbol] = {}

    def define(self, sym: Symbol):
        self.symbols[sym.name] = sym

    def lookup(self, name: str) -> Symbol | None:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None


class ClassInfo:
    def __init__(self, name: str, decl: ast.ClassDeclaration):
        self.name = name
        self.decl = decl
        self.field_types: dict[str, ast.TypeAnnotation] = {}
        self.method_names: set[str] = set()


class FuncInfo:
    def __init__(self, name: str, decl: ast.FuncDeclaration):
        self.name = name
        self.decl = decl


class EnumInfo:
    def __init__(self, name: str, decl: ast.EnumDeclaration):
        self.name = name
        self.decl = decl
        self.variants: set[str] = set(decl.variants)


class SemanticAnalyzer:
    def __init__(self, filename: str = "<source>"):
        self.filename = filename
        self.scope = Scope()
        self.classes: dict[str, ClassInfo] = {}
        self.enums: dict[str, EnumInfo] = {}
        self.functions: dict[str, FuncInfo] = {}
        self.errors: list[SemanticError] = []
        self._class_context: list[str] = []
        self._current_return_type: ast.TypeAnnotation | None = None
        # Register built-in functions. print is handled as a variadic-ish special case.
        self.functions["print"] = FuncInfo("print", ast.FuncDeclaration(name="print", return_type=None))
        self.functions["input"] = FuncInfo(
            "input",
            ast.FuncDeclaration(name="input", params=[], return_type=ast.TypeAnnotation(base_type="string")),
        )
        self.functions["assert"] = FuncInfo(
            "assert",
            ast.FuncDeclaration(
                name="assert",
                params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="bool"), name="condition")],
                return_type=None,
            ),
        )
        self.functions["readFile"] = FuncInfo(
            "readFile",
            ast.FuncDeclaration(
                name="readFile",
                params=[ast.Parameter(type_ann=ast.TypeAnnotation(base_type="string"), name="path")],
                return_type=ast.TypeAnnotation(base_type="string", is_nullable=True),
            ),
        )

    def _err(self, msg: str, node: ast.Node):
        self.errors.append(SemanticError(msg, node.line, node.column, self.filename))

    @property
    def _current_class(self) -> str | None:
        return self._class_context[-1] if self._class_context else None

    def _push_scope(self, name: str):
        self.scope = Scope(self.scope, name)

    def _pop_scope(self):
        if self.scope.parent:
            self.scope = self.scope.parent

    # ── public entry ─────────────────────────────────────────
    def analyze(self, program: ast.Program):
        # First pass: register classes and top-level functions
        for stmt in program.statements:
            if isinstance(stmt, ast.ClassDeclaration):
                ci = ClassInfo(stmt.name, stmt)
                for f in stmt.fields:
                    ci.field_types[f.name] = f.type_ann
                for m in stmt.methods:
                    ci.method_names.add(m.name)
                self.classes[stmt.name] = ci
            elif isinstance(stmt, ast.FuncDeclaration):
                self.functions[stmt.name] = FuncInfo(stmt.name, stmt)
            elif isinstance(stmt, ast.EnumDeclaration):
                self.enums[stmt.name] = EnumInfo(stmt.name, stmt)

        # Second pass: analyze statements
        for stmt in program.statements:
            self._analyze_stmt(stmt)

    # ── statements ───────────────────────────────────────────
    def _analyze_stmt(self, stmt):
        if isinstance(stmt, ast.VarDeclaration):
            self._analyze_var_decl(stmt)
        elif isinstance(stmt, ast.FuncDeclaration):
            self._analyze_func(stmt)
        elif isinstance(stmt, ast.ClassDeclaration):
            self._analyze_class(stmt)
        elif isinstance(stmt, ast.EnumDeclaration):
            self._analyze_enum(stmt)
        elif isinstance(stmt, ast.IfStatement):
            self._analyze_if(stmt)
        elif isinstance(stmt, ast.WhileStatement):
            self._analyze_expr(stmt.condition)
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.ForStatement):
            self._push_scope("for")
            try:
                if stmt.init:
                    self._analyze_stmt(stmt.init)
                if stmt.condition:
                    self._analyze_expr(stmt.condition)
                if stmt.update:
                    self._analyze_expr(stmt.update)
                self._analyze_block(stmt.body)
            finally:
                self._pop_scope()
        elif isinstance(stmt, ast.ForRangeStatement):
            self._analyze_expr(stmt.start)
            self._analyze_expr(stmt.end)
            self._push_scope("for-range")
            try:
                self.scope.define(Symbol(stmt.var_name, stmt.var_type))
                self._analyze_block(stmt.body)
            finally:
                self._pop_scope()
        elif isinstance(stmt, ast.ForInStatement):
            self._analyze_expr(stmt.iterable)
            # Size check: only allow iteration over known-size collections
            is_valid = False
            if isinstance(stmt.iterable, ast.Identifier):
                sym = self.scope.lookup(stmt.iterable.name)
                # Arrays are valid if they have known size info or are literals
                if sym and sym.type_ann and sym.type_ann.is_array:
                    # In Oda, arrays declared like 'int[3] nums' or 'int[] nums = [1,2,3]' have known size
                    is_valid = True
                elif sym and sym.type_ann and sym.type_ann.base_type == "string":
                    is_valid = True
            elif isinstance(stmt.iterable, ast.InterpolatedString) or isinstance(stmt.iterable, ast.StringLiteral):
                is_valid = True
            elif self._infer_type(stmt.iterable) == "string":
                is_valid = True
            elif isinstance(stmt.iterable, ast.ArrayLiteral):
                is_valid = True

            if not is_valid:
                self._err(f"Cannot iterate over unknown-size collection", stmt)

            self._push_scope("for-in")
            try:
                if stmt.index_name:
                    self.scope.define(Symbol(stmt.index_name, stmt.index_type))
                self.scope.define(Symbol(stmt.var_name, stmt.var_type))
                self._analyze_block(stmt.body)
            finally:
                self._pop_scope()
        elif isinstance(stmt, ast.ReturnStatement):
            if self._current_return_type:
                expected = self._full_type(self._current_return_type)
                if not stmt.value:
                    self._err(f"Function must return '{expected}'", stmt)
                else:
                    self._analyze_expr(stmt.value)
                    actual = self._infer_type(stmt.value)
                    if actual == "void":
                        self._err("Cannot return a void value", stmt)
                    elif actual and actual != expected and not self._can_coerce(actual, expected):
                        self._err(f"Cannot return '{actual}' from function returning '{expected}'", stmt)
            elif stmt.value:
                self._analyze_expr(stmt.value)
                if self._infer_type(stmt.value) == "void":
                    self._err("Cannot return a void value", stmt)
        elif isinstance(stmt, ast.GuardStatement):
            self._analyze_expr(stmt.expr)
            # Enforce that every case in guard MUST exit the scope
            for case in stmt.cases:
                if case.error_type not in _STANDARD_ERROR_TYPES:
                    self._err(f"Unknown error type '{case.error_type}'", case)
                has_exit = False
                for body_stmt in case.body:
                    if isinstance(body_stmt, (ast.ReturnStatement, ast.BreakStatement, ast.ContinueStatement)):
                        has_exit = True
                        break
                if not has_exit:
                    self._err("guard else block must exit the current scope (return or break required)", case)
            
            for case in stmt.cases:
                self._analyze_block(case.body)
            
            # The variable is defined AFTER the guard block
            self.scope.define(Symbol(stmt.var_name, stmt.var_type))
        elif isinstance(stmt, ast.MatchStatement):
            self._analyze_expr(stmt.expr)
            match_type = self._infer_type(stmt.expr)
            for arm in stmt.arms:
                if arm.pattern:
                    self._analyze_expr(arm.pattern)
                    pattern_type = self._infer_type(arm.pattern)
                    if (
                        match_type
                        and pattern_type
                        and pattern_type != match_type
                        and not self._can_coerce(pattern_type, match_type)
                        and not self._can_coerce(match_type, pattern_type)
                    ):
                        self._err(f"Match pattern type '{pattern_type}' does not match '{match_type}'", arm)
                self._analyze_block(arm.body)
        elif isinstance(stmt, ast.ExpressionStatement):
            if stmt.expr:
                self._analyze_expr(stmt.expr)

    # ── helpers ──────────────────────────────────────────────
    def _full_type(self, ta: ast.TypeAnnotation) -> str:
        s = ta.base_type
        if ta.is_array:
            s += "[]" * ta.array_depth
        if ta.is_nullable:
            s += "?"
        return s

    def _type_contains_heap_storage(self, ta: ast.TypeAnnotation, seen: set[str] | None = None) -> bool:
        if ta.is_array or ta.base_type == "string":
            return True
        if ta.base_type in self.classes:
            return self._class_contains_heap_storage(ta.base_type, seen)
        return False

    def _class_contains_heap_storage(self, class_name: str, seen: set[str] | None = None) -> bool:
        if seen is None:
            seen = set()
        if class_name in seen:
            return False
        seen.add(class_name)

        ci = self.classes.get(class_name)
        if not ci:
            return False
        return any(
            self._type_contains_heap_storage(field_type, seen)
            for field_type in ci.field_types.values()
        )

    def _param_requires_ref(self, param: ast.Parameter) -> bool:
        return (
            param.type_ann.base_type in self.classes
            and self._class_contains_heap_storage(param.type_ann.base_type)
        )

    def _check_param_decl(self, param: ast.Parameter, owner_name: str):
        if not self._type_exists(param.type_ann):
            self._err(f"Unknown type '{param.type_ann.base_type}'", param)
        if self._param_requires_ref(param) and not param.is_ref:
            self._err(
                f"Parameter '{param.name}' of function '{owner_name}' has class "
                f"'{param.type_ann.base_type}' with heap-allocated fields and must be passed by ref",
                param,
            )

    def _analyze_var_decl(self, stmt: ast.VarDeclaration):
        full = self._full_type(stmt.type_ann)
        base = stmt.type_ann.base_type
        # Verify the type exists
        if not self._type_exists(stmt.type_ann):
            self._err(f"Unknown type '{base}'", stmt)

        # Null safety: non-nullable vars must have an initializer or will be set
        if stmt.initializer:
            self._analyze_expr(stmt.initializer)
            init_type = self._infer_type(stmt.initializer)
            if init_type == "void":
                self._err("Cannot assign a void value to a variable", stmt)
            elif init_type and init_type != full:
                # Basic check, no complex coercion for arrays yet
                if not self._can_coerce(init_type, full):
                    self._err(f"Cannot coerce '{init_type}' to '{full}'", stmt)

            # Non-nullable assigned null
            if not stmt.type_ann.is_nullable and isinstance(stmt.initializer, ast.NullLiteral):
                self._err(f"Cannot assign null to non-nullable '{full}'", stmt)

        self.scope.define(Symbol(stmt.name, stmt.type_ann, is_immutable=stmt.is_immutable))

    def _analyze_func(self, stmt: ast.FuncDeclaration):
        for p in stmt.params:
            self._check_param_decl(p, stmt.name)
        if stmt.return_type and not self._type_exists(stmt.return_type):
            self._err(f"Unknown return type '{stmt.return_type.base_type}'", stmt)
        if stmt.is_extern:
            return

        old_scope = self.scope
        old_return_type = self._current_return_type
        self.scope = Scope(old_scope, f"func:{stmt.name}")
        self._current_return_type = stmt.return_type
        for p in stmt.params:
            self.scope.define(Symbol(p.name, p.type_ann, is_ref=p.is_ref))
        self._analyze_block(stmt.body)
        if stmt.return_type and not self._block_always_returns(stmt.body):
            self._err(f"Not all code paths return a value from function '{stmt.name}'", stmt)
        self.scope = old_scope
        self._current_return_type = old_return_type

    def _analyze_class(self, stmt: ast.ClassDeclaration):
        self._class_context.append(stmt.name)
        old_scope = self.scope
        self.scope = Scope(old_scope, f"class:{stmt.name}")
        try:
            # Define fields
            for f in stmt.fields:
                self.scope.define(Symbol(f.name, f.type_ann))
            if stmt.constructor:
                self._analyze_func(stmt.constructor)
            for m in stmt.methods:
                self._analyze_func(m)
            if stmt.destructor:
                self._analyze_func(stmt.destructor)
        finally:
            self.scope = old_scope
            self._class_context.pop()

    def _analyze_enum(self, stmt: ast.EnumDeclaration):
        seen = set()
        for variant in stmt.variants:
            if variant in seen:
                self._err(f"Duplicate enum variant '{variant}' in enum '{stmt.name}'", stmt)
            seen.add(variant)

    def _analyze_if(self, stmt: ast.IfStatement):
        self._analyze_expr(stmt.condition)
        self._analyze_block(stmt.body)
        for cond, body in stmt.elif_branches:
            self._analyze_expr(cond)
            self._analyze_block(body)
        if stmt.else_body:
            self._analyze_block(stmt.else_body)

    def _analyze_block(self, stmts: list):
        self._push_scope("block")
        try:
            for s in stmts:
                self._analyze_stmt(s)
        finally:
            self._pop_scope()

    def _block_always_returns(self, stmts: list) -> bool:
        for stmt in stmts:
            if self._stmt_always_returns(stmt):
                return True
        return False

    def _stmt_always_returns(self, stmt) -> bool:
        if isinstance(stmt, ast.ReturnStatement):
            return True
        if isinstance(stmt, ast.IfStatement):
            if not stmt.else_body:
                return False
            branches = [stmt.body] + [body for _, body in stmt.elif_branches] + [stmt.else_body]
            return all(self._block_always_returns(branch) for branch in branches)
        if isinstance(stmt, ast.MatchStatement):
            has_default = any(arm.pattern is None for arm in stmt.arms)
            return has_default and all(self._block_always_returns(arm.body) for arm in stmt.arms)
        return False

    def _is_lvalue(self, expr) -> bool:
        return isinstance(expr, (ast.Identifier, ast.MemberAccess, ast.IndexAccess))

    def _check_type_compatible(self, actual: str | None, expected: str, node, *, ref: bool = False):
        if actual is None:
            return
        if ref:
            if actual != expected:
                self._err(f"Cannot pass '{actual}' as ref '{expected}'", node)
            return
        if actual != expected and not self._can_coerce(actual, expected):
            self._err(f"Cannot pass '{actual}' to parameter of type '{expected}'", node)

    def _check_call(self, call: ast.CallExpr):
        sig = self._resolve_call_signature(call)
        if sig is None:
            return
        name, params = sig

        if name == "print":
            if len(call.args) > 1:
                self._err(f"Function 'print' expects 0 or 1 argument(s), got {len(call.args)}", call)
            for is_ref in call.ref_flags:
                if is_ref:
                    self._err("Function 'print' does not accept ref arguments", call)
            return

        if len(call.args) != len(params):
            self._err(f"Function '{name}' expects {len(params)} argument(s), got {len(call.args)}", call)
            return

        for i, (arg, param) in enumerate(zip(call.args, params)):
            is_ref_call = i < len(call.ref_flags) and call.ref_flags[i]
            expected = self._full_type(param.type_ann)
            actual = self._infer_type(arg)

            if param.is_ref:
                if not is_ref_call:
                    self._err(f"Parameter '{param.name}' of function '{name}' must be passed with 'ref'", arg)
                if not self._is_lvalue(arg):
                    self._err(f"Cannot pass non-assignable expression as ref parameter '{param.name}'", arg)
                self._check_type_compatible(actual, expected, arg, ref=True)
            else:
                if self._param_requires_ref(param):
                    self._err(
                        f"Cannot pass class '{param.type_ann.base_type}' with heap-allocated fields by value; "
                        "declare the parameter as ref",
                        arg,
                    )
                if is_ref_call:
                    self._err(f"Parameter '{param.name}' of function '{name}' is not a ref parameter", arg)
                self._check_type_compatible(actual, expected, arg)

    def _resolve_call_signature(self, call: ast.CallExpr) -> tuple[str, list[ast.Parameter]] | None:
        if isinstance(call.callee, ast.Identifier):
            name = call.callee.name
            if name in self.classes:
                constructor = self.classes[name].decl.constructor
                return name, constructor.params if constructor else []
            func_info = self.functions.get(name)
            if func_info:
                return name, func_info.decl.params
            self._err(f"Undefined function '{name}'", call.callee)
            return None

        if isinstance(call.callee, ast.MemberAccess):
            obj_type = self._infer_type(call.callee.obj)
            ci = self.classes.get(obj_type) if obj_type else None
            if not ci:
                self._err(f"Cannot call method '{call.callee.member}' on non-class type '{obj_type}'", call.callee)
                return None
            for method in ci.decl.methods:
                if method.name == call.callee.member:
                    return f"{obj_type}.{method.name}", method.params
            self._err(f"Class '{obj_type}' has no method '{call.callee.member}'", call.callee)
            return None

        self._err("Unsupported call target", call)
        return None

    # ── expressions ──────────────────────────────────────────
    def _analyze_expr(self, expr):
        if isinstance(expr, ast.Identifier):
            sym = self.scope.lookup(expr.name)
            if sym is None and expr.name not in self.classes and expr.name not in self.enums and expr.name not in self.functions:
                # Allow underscore-prefixed within class context
                if self._current_class and expr.name.startswith("_"):
                    ci = self.classes.get(self._current_class)
                    if not ci or expr.name not in ci.field_types:
                        self._err(f"Unknown private field '{expr.name}' in class '{self._current_class}'", expr)
                else:
                    self._err(f"Undefined variable '{expr.name}'", expr)
        elif isinstance(expr, ast.AssignExpr):
            self._analyze_expr(expr.target)
            self._analyze_expr(expr.value)
            # Immutability check
            if isinstance(expr.target, ast.Identifier):
                sym = self.scope.lookup(expr.target.name)
                if sym and sym.is_immutable:
                    self._err(f"Cannot reassign immutable variable '{expr.target.name}' (declared with 'stay')", expr)
        elif isinstance(expr, ast.BinaryExpr):
            self._analyze_expr(expr.left)
            self._analyze_expr(expr.right)
            inferred = self._infer_type(expr)
            if self._infer_type(expr.left) == "void" or self._infer_type(expr.right) == "void":
                self._err("Cannot use a void expression in a binary operation", expr)
            elif inferred is None:
                left_type = self._infer_type(expr.left)
                right_type = self._infer_type(expr.right)
                self._err(f"Invalid operands for '{expr.op}': '{left_type}' and '{right_type}'", expr)
        elif isinstance(expr, ast.UnaryExpr):
            self._analyze_expr(expr.operand)
        elif isinstance(expr, ast.CastExpr):
            self._analyze_expr(expr.expr)
            self._analyze_cast(expr)
        elif isinstance(expr, ast.CallExpr):
            self._analyze_expr(expr.callee)
            self._check_call(expr)
            for a in expr.args:
                self._analyze_expr(a)
                if self._infer_type(a) == "void":
                    self._err("Cannot use a void function call as an argument", a)
        elif isinstance(expr, ast.MemberAccess):
            if isinstance(expr.obj, ast.Identifier) and expr.obj.name in self.enums:
                enum_info = self.enums[expr.obj.name]
                if expr.member not in enum_info.variants:
                    self._err(f"Enum '{expr.obj.name}' has no variant '{expr.member}'", expr)
                return
            self._analyze_expr(expr.obj)
            if expr.member.startswith("_"):
                owner_class = self._infer_type(expr.obj)
                ci = self.classes.get(owner_class) if owner_class else None
                owns_private_field = ci is not None and expr.member in ci.field_types
                if not owns_private_field:
                    self._err(f"Unknown private member '{expr.member}'", expr)
                elif self._current_class != owner_class:
                    self._err(
                        f"Cannot access private member '{expr.member}' outside class '{owner_class}'",
                        expr
                    )
        elif isinstance(expr, ast.IndexAccess):
            self._analyze_expr(expr.obj)
            self._analyze_expr(expr.index)
        elif isinstance(expr, ast.InterpolatedString):
            for part in expr.parts:
                if not isinstance(part, str):
                    self._analyze_expr(part)
        elif isinstance(expr, ast.ArrayAllocation):
            for sz in expr.sizes:
                self._analyze_expr(sz)
                sz_type = self._infer_type(sz)
                if sz_type not in ("int", "uint") and sz_type is not None:
                    self._err("Array dimensions must be integer expressions", expr)

    def _analyze_cast(self, expr: ast.CastExpr):
        target = expr.target_type
        if not target or not self._type_exists(target):
            name = self._full_type(target) if target else "<unknown>"
            self._err(f"Unknown cast target type '{name}'", expr)
            return
        source = self._infer_type(expr.expr)
        dest = self._full_type(target)
        if source is None:
            return
        if target.is_array or target.is_nullable:
            self._err(f"Cannot cast to non-scalar type '{dest}'", expr)
            return
        if not self._can_explicit_cast(source, dest):
            self._err(f"Cannot cast '{source}' to '{dest}'", expr)

    def _type_exists(self, ta: ast.TypeAnnotation) -> bool:
        return ta.base_type in _WIDENING or ta.base_type in self.classes or ta.base_type in self.enums

    def _can_explicit_cast(self, src: str, dst: str) -> bool:
        if src == dst:
            return True
        scalar = {"int", "uint", "float", "char", "bool"}
        if src in scalar and dst in scalar:
            return True
        if src in self.enums and dst in ("int", "uint"):
            return True
        if src in ("int", "uint") and dst in self.enums:
            return True
        return False

    # ── type inference (basic) ───────────────────────────────
    def _infer_type(self, expr) -> str | None:
        if isinstance(expr, ast.IntegerLiteral):
            return "int"
        if isinstance(expr, ast.UIntLiteral):
            return "uint"
        if isinstance(expr, ast.FloatLiteral):
            return "float"
        if isinstance(expr, (ast.StringLiteral, ast.InterpolatedString)):
            return "string"
        if isinstance(expr, ast.BoolLiteral):
            return "bool"
        if isinstance(expr, ast.NullLiteral):
            return None
        if isinstance(expr, ast.ArrayLiteral):
            if not expr.elements: return "any[]"
            et = self._infer_type(expr.elements[0])
            return f"{et}[]" if et else "any[]"
        if isinstance(expr, ast.ArrayAllocation):
            return expr.base_type + ("[]" * len(expr.sizes))
        if isinstance(expr, ast.Identifier):
            sym = self.scope.lookup(expr.name)
            return self._full_type(sym.type_ann) if sym else None
        if isinstance(expr, ast.MemberAccess):
            if isinstance(expr.obj, ast.Identifier) and expr.obj.name in self.enums:
                enum_info = self.enums[expr.obj.name]
                if expr.member in enum_info.variants:
                    return expr.obj.name
                return None
            obj_type = self._infer_type(expr.obj)
            ci = self.classes.get(obj_type) if obj_type else None
            if ci and expr.member in ci.field_types:
                return self._full_type(ci.field_types[expr.member])
            return None
        if isinstance(expr, ast.IndexAccess):
            obj_type = self._infer_type(expr.obj)
            if not obj_type:
                return None
            if obj_type.endswith("[]"):
                return obj_type[:-2]
            if obj_type == "string":
                return "char"
            return None
        if isinstance(expr, ast.UnaryExpr):
            operand_type = self._infer_type(expr.operand)
            if expr.op == "!" and operand_type == "bool":
                return "bool"
            if expr.op == "-" and operand_type in ("int", "uint", "float"):
                return operand_type
            return None
        if isinstance(expr, ast.CastExpr):
            return self._full_type(expr.target_type)
        if isinstance(expr, ast.BinaryExpr):
            return self._infer_binary_type(expr)
        if isinstance(expr, ast.CallExpr):
            if isinstance(expr.callee, ast.Identifier):
                if expr.callee.name in self.classes:
                    return expr.callee.name
                func_info = self.functions.get(expr.callee.name)
                if func_info:
                    if func_info.decl.return_type:
                        return self._full_type(func_info.decl.return_type)
                    return "void"
            elif isinstance(expr.callee, ast.MemberAccess):
                obj_type = self._infer_type(expr.callee.obj)
                if obj_type and obj_type in self.classes:
                    ci = self.classes[obj_type]
                    for m in ci.decl.methods:
                        if m.name == expr.callee.member:
                            if m.return_type:
                                return self._full_type(m.return_type)
                            return "void"
            return None

        return None

    def _infer_binary_type(self, expr: ast.BinaryExpr) -> str | None:
        left = self._infer_type(expr.left)
        right = self._infer_type(expr.right)

        if expr.op == "??":
            return left or right

        if expr.op in ("&&", "||"):
            return "bool" if left == "bool" and right == "bool" else None

        if expr.op in ("==", "!="):
            if left == right or self._can_coerce(left, right) or self._can_coerce(right, left):
                return "bool"
            return None

        if expr.op in ("<", ">", "<=", ">="):
            if self._common_numeric_type(left, right) or (left == "char" and right == "char"):
                return "bool"
            return None

        if expr.op == "+" and (left == "string" or right == "string"):
            if left in ("string", "int", "uint", "float", "bool", "char") and right in ("string", "int", "uint", "float", "bool", "char"):
                return "string"
            return None

        if expr.op in ("+", "-", "*", "/", "%"):
            common = self._common_numeric_type(left, right)
            if expr.op == "%" and common == "float":
                return None
            return common

        return None

    def _common_numeric_type(self, left: str | None, right: str | None) -> str | None:
        numeric = ("char", "int", "uint", "float")
        if left not in numeric or right not in numeric:
            return None
        if left == right:
            return left
        if left == "char":
            left = "int"
        if right == "char":
            right = "int"
        if left == right:
            return left
        if left == "float" and self._can_coerce(right, "float"):
            return "float"
        if right == "float" and self._can_coerce(left, "float"):
            return "float"
        return None

    def _can_coerce(self, src: str, dst: str) -> bool:
        if src is None or dst is None:
            return False
        if src == dst:
            return True
        return dst in _WIDENING.get(src, set())
