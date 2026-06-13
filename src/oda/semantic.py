"""Semantic analyzer for OdaLanguage — type checking, scope, coercion rules."""
from __future__ import annotations
from . import ast_nodes as ast
from .errors import SemanticError
from .type_engine import (
    BUILTIN_TYPES,
    ERROR_TYPE,
    can_coerce,
    infer_binary_type,
    infer_type,
    is_error_type,
)

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
        self._loop_depth = 0
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

    def _err(self, msg: str, node: ast.Node, code: str = "E3000", hint: str | None = None):
        self.errors.append(SemanticError(msg, node.line, node.column, self.filename, code=code, hint=hint))

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
            if stmt.name == "main":
                self._err(
                    "Oda programs have no 'main' function", stmt, code="E3046",
                    hint="Write top-level statements; they become the program entry point.",
                )
                return
            self._analyze_func(stmt)
        elif isinstance(stmt, ast.ClassDeclaration):
            self._analyze_class(stmt)
        elif isinstance(stmt, ast.EnumDeclaration):
            self._analyze_enum(stmt)
        elif isinstance(stmt, ast.IfStatement):
            self._analyze_if(stmt)
        elif isinstance(stmt, ast.WhileStatement):
            self._analyze_expr(stmt.condition)
            self._loop_depth += 1
            try:
                self._analyze_block(stmt.body)
            finally:
                self._loop_depth -= 1
        elif isinstance(stmt, ast.ForStatement):
            self._push_scope("for")
            self._loop_depth += 1
            try:
                if stmt.init:
                    self._analyze_stmt(stmt.init)
                if stmt.condition:
                    self._analyze_expr(stmt.condition)
                if stmt.update:
                    self._analyze_expr(stmt.update)
                self._analyze_block(stmt.body)
            finally:
                self._loop_depth -= 1
                self._pop_scope()
        elif isinstance(stmt, ast.ForRangeStatement):
            self._analyze_expr(stmt.start)
            self._analyze_expr(stmt.end)
            self._push_scope("for-range")
            self._loop_depth += 1
            try:
                self.scope.define(Symbol(stmt.var_name, stmt.var_type))
                self._analyze_block(stmt.body)
            finally:
                self._loop_depth -= 1
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
                self._err(f"Cannot iterate over unknown-size collection", stmt, code="E3004")

            self._push_scope("for-in")
            self._loop_depth += 1
            try:
                if stmt.index_name:
                    self.scope.define(Symbol(stmt.index_name, stmt.index_type))
                self.scope.define(Symbol(stmt.var_name, stmt.var_type))
                self._analyze_block(stmt.body)
            finally:
                self._loop_depth -= 1
                self._pop_scope()
        elif isinstance(stmt, ast.ReturnStatement):
            if self._current_return_type:
                expected = self._full_type(self._current_return_type)
                if not stmt.value:
                    self._err(f"Function must return '{expected}'", stmt, code="E3005")
                else:
                    self._analyze_expr(stmt.value)
                    actual = self._infer_type(stmt.value)
                    if actual == "void":
                        self._err("Cannot return a void value", stmt, code="E3006")
                    elif actual and actual != expected and not self._can_coerce(actual, expected):
                        self._err(f"Cannot return '{actual}' from function returning '{expected}'", stmt, code="E3007")
            elif stmt.value:
                self._analyze_expr(stmt.value)
                if self._infer_type(stmt.value) == "void":
                    self._err("Cannot return a void value", stmt, code="E3006")
        elif isinstance(stmt, (ast.BreakStatement, ast.ContinueStatement)):
            if self._loop_depth == 0:
                self._err("break/continue cannot be used outside a loop", stmt, code="E3008")
        elif isinstance(stmt, ast.GuardStatement):
            self._analyze_expr(stmt.expr)
            # Enforce that every case in guard MUST exit the scope
            for case in stmt.cases:
                if case.error_type not in _STANDARD_ERROR_TYPES:
                    self._err(f"Unknown error type '{case.error_type}'", case, code="E3009")
                has_exit = False
                for body_stmt in case.body:
                    if isinstance(body_stmt, (ast.ReturnStatement, ast.BreakStatement, ast.ContinueStatement)):
                        has_exit = True
                        break
                if not has_exit:
                    self._err("guard else block must exit the current scope (return or break required)", case, code="E3002", hint="return, break, continue")
            
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
                        self._err(f"Match pattern type '{pattern_type}' does not match '{match_type}'", arm, code="E3010")
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
            self._err(f"Unknown type '{param.type_ann.base_type}'", param, code="E3011")
        if self._param_requires_ref(param) and not param.is_ref:
            self._err(
                f"Parameter '{param.name}' of function '{owner_name}' has class "
                f"'{param.type_ann.base_type}' with heap-allocated fields and must be passed by ref",
                param, code="E3012"
            )

    def _analyze_var_decl(self, stmt: ast.VarDeclaration):
        full = self._full_type(stmt.type_ann)
        base = stmt.type_ann.base_type
        # Verify the type exists
        if not self._type_exists(stmt.type_ann):
            self._err(f"Unknown type '{base}'", stmt, code="E3013")

        # Null safety: non-nullable vars must have an initializer or will be set
        if stmt.initializer:
            self._analyze_expr(stmt.initializer)
            init_type = self._infer_type(stmt.initializer)
            if init_type == "void":
                self._err("Cannot assign a void value to a variable", stmt, code="E3014")
            elif init_type and init_type != full:
                # Basic check, no complex coercion for arrays yet
                if not self._can_coerce(init_type, full):
                    hint = f"as {full}" if init_type in ("int", "uint") and full in ("int", "uint") else None
                    self._err(f"Cannot coerce '{init_type}' to '{full}'", stmt, code="E3001", hint=hint)

            # Non-nullable assigned null
            if not stmt.type_ann.is_nullable and isinstance(stmt.initializer, ast.NullLiteral):
                self._err(f"Cannot assign null to non-nullable '{full}'", stmt, code="E3015")

        self.scope.define(Symbol(stmt.name, stmt.type_ann, is_immutable=stmt.is_immutable))

    def _analyze_func(self, stmt: ast.FuncDeclaration):
        for p in stmt.params:
            self._check_param_decl(p, stmt.name)
        if stmt.return_type and not self._type_exists(stmt.return_type):
            self._err(f"Unknown return type '{stmt.return_type.base_type}'", stmt, code="E3016")
        if (
            stmt.return_type
            and stmt.return_type.base_type in self.classes
            and self._class_contains_heap_storage(stmt.return_type.base_type)
        ):
            self._err(
                f"Cannot return class '{stmt.return_type.base_type}' with "
                "heap-allocated fields by value",
                stmt, code="E3047",
                hint="return results via a ref out-parameter",
            )
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
            self._err(f"Not all code paths return a value from function '{stmt.name}'", stmt, code="E3017")
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
                self._err(f"Duplicate enum variant '{variant}' in enum '{stmt.name}'", stmt, code="E3018")
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
        if isinstance(stmt, ast.WhileStatement):
            if isinstance(stmt.condition, ast.BoolLiteral) and stmt.condition.value is True:
                return self._block_always_returns(stmt.body)
            return False
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
                self._err(f"Cannot pass '{actual}' as ref '{expected}'", node, code="E3019")
            return
        if actual != expected and not self._can_coerce(actual, expected):
            self._err(f"Cannot pass '{actual}' to parameter of type '{expected}'", node, code="E3020")

    def _check_call(self, call: ast.CallExpr):
        sig = self._resolve_call_signature(call)
        if sig is None:
            return
        name, params = sig

        if name == "print":
            if len(call.args) > 1:
                self._err(f"Function 'print' expects 0 or 1 argument(s), got {len(call.args)}", call, code="E3021")
            for is_ref in call.ref_flags:
                if is_ref:
                    self._err("Function 'print' does not accept ref arguments", call, code="E3022")
            return

        if len(call.args) != len(params):
            self._err(f"Function '{name}' expects {len(params)} argument(s), got {len(call.args)}", call, code="E3023")
            return

        for i, (arg, param) in enumerate(zip(call.args, params)):
            is_ref_call = i < len(call.ref_flags) and call.ref_flags[i]
            expected = self._full_type(param.type_ann)
            actual = self._infer_type(arg)

            if param.is_ref:
                if not is_ref_call:
                    self._err(f"Parameter '{param.name}' of function '{name}' must be passed with 'ref'", arg, code="E3024")
                if not self._is_lvalue(arg):
                    self._err(f"Cannot pass non-assignable expression as ref parameter '{param.name}'", arg, code="E3025")
                self._check_type_compatible(actual, expected, arg, ref=True)
            else:
                if self._param_requires_ref(param):
                    self._err(
                        f"Cannot pass class '{param.type_ann.base_type}' with heap-allocated fields by value; "
                        "declare the parameter as ref",
                        arg, code="E3026"
                    )
                if is_ref_call:
                    self._err(f"Parameter '{param.name}' of function '{name}' is not a ref parameter", arg, code="E3027")
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
            self._err(f"Undefined function '{name}'", call.callee, code="E3028")
            return None

        if isinstance(call.callee, ast.MemberAccess):
            obj_type = self._infer_type(call.callee.obj)
            ci = self.classes.get(obj_type) if obj_type else None
            if not ci:
                self._err(f"Cannot call method '{call.callee.member}' on non-class type '{obj_type}'", call.callee, code="E3029")
                return None
            for method in ci.decl.methods:
                if method.name == call.callee.member:
                    return f"{obj_type}.{method.name}", method.params
            self._err(f"Class '{obj_type}' has no method '{call.callee.member}'", call.callee, code="E3030")
            return None

        self._err("Unsupported call target", call, code="E3031")
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
                        self._err(f"Unknown private field '{expr.name}' in class '{self._current_class}'", expr, code="E3032")
                        return ERROR_TYPE
                else:
                    self._err(f"Undefined variable '{expr.name}'", expr, code="E3033")
                    return ERROR_TYPE
        elif isinstance(expr, ast.AssignExpr):
            self._analyze_expr(expr.target)
            self._analyze_expr(expr.value)
            # Immutability check
            if isinstance(expr.target, ast.Identifier):
                sym = self.scope.lookup(expr.target.name)
                if sym and sym.is_immutable:
                    self._err(f"Cannot reassign immutable variable '{expr.target.name}' (declared with 'stay')", expr, code="E3034")
            elif isinstance(expr.target, ast.IndexAccess) and isinstance(expr.target.obj, ast.Identifier):
                sym = self.scope.lookup(expr.target.obj.name)
                if sym and sym.is_immutable:
                    self._err("Cannot modify element of immutable array", expr.target, code="E3035")
        elif isinstance(expr, ast.BinaryExpr):
            left_t = self._analyze_expr(expr.left)
            right_t = self._analyze_expr(expr.right)
            # An operand whose type could not be resolved already reported a root
            # error; do not cascade a bogus "Invalid operands" child on top of it.
            if is_error_type(left_t) or is_error_type(right_t):
                return ERROR_TYPE
            inferred = self._infer_type(expr)
            if self._infer_type(expr.left) == "void" or self._infer_type(expr.right) == "void":
                self._err("Cannot use a void expression in a binary operation", expr, code="E3036")
                return ERROR_TYPE
            elif inferred is None:
                left_type = self._infer_type(expr.left)
                right_type = self._infer_type(expr.right)
                self._err(f"Invalid operands for '{expr.op}': '{left_type}' and '{right_type}'", expr, code="E3037")
                return ERROR_TYPE
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
                    self._err("Cannot use a void function call as an argument", a, code="E3038")
            if self._infer_type(expr) is None:
                return ERROR_TYPE
        elif isinstance(expr, ast.MemberAccess):
            if isinstance(expr.obj, ast.Identifier) and expr.obj.name in self.enums:
                enum_info = self.enums[expr.obj.name]
                if expr.member not in enum_info.variants:
                    self._err(f"Enum '{expr.obj.name}' has no variant '{expr.member}'", expr, code="E3039")
                    return ERROR_TYPE
                return
            obj_t = self._analyze_expr(expr.obj)
            if is_error_type(obj_t):
                return ERROR_TYPE
            if expr.member.startswith("_"):
                owner_class = self._infer_type(expr.obj)
                ci = self.classes.get(owner_class) if owner_class else None
                owns_private_field = ci is not None and expr.member in ci.field_types
                if not owns_private_field:
                    self._err(f"Unknown private member '{expr.member}'", expr, code="E3040")
                    return ERROR_TYPE
                elif self._current_class != owner_class:
                    self._err(
                        f"Cannot access private member '{expr.member}' outside class '{owner_class}'",
                        expr,
                        code="E3003",
                        hint=f"Owner: {owner_class}"
                    )
                    return ERROR_TYPE
        elif isinstance(expr, ast.IndexAccess):
            obj_t = self._analyze_expr(expr.obj)
            self._analyze_expr(expr.index)
            if is_error_type(obj_t):
                return ERROR_TYPE
            index_type = self._infer_type(expr.index)
            if index_type not in ("int", "uint", None):
                self._err("Array index must be an integer expression", expr.index, code="E3041")
                return ERROR_TYPE
        elif isinstance(expr, ast.InterpolatedString):
            for part in expr.parts:
                if not isinstance(part, str):
                    self._analyze_expr(part)
        elif isinstance(expr, ast.ArrayAllocation):
            for sz in expr.sizes:
                self._analyze_expr(sz)
                sz_type = self._infer_type(sz)
                if sz_type not in ("int", "uint") and sz_type is not None:
                    self._err("Array dimensions must be integer expressions", expr, code="E3042")

    def _analyze_cast(self, expr: ast.CastExpr):
        target = expr.target_type
        if not target or not self._type_exists(target):
            name = self._full_type(target) if target else "<unknown>"
            self._err(f"Unknown cast target type '{name}'", expr, code="E3043")
            return
        source = self._infer_type(expr.expr)
        dest = self._full_type(target)
        if source is None:
            return
        if target.is_array or target.is_nullable:
            self._err(f"Cannot cast to non-scalar type '{dest}'", expr, code="E3044")
            return
        if not self._can_explicit_cast(source, dest):
            self._err(f"Cannot cast '{source}' to '{dest}'", expr, code="E3045")

    def _type_exists(self, ta: ast.TypeAnnotation) -> bool:
        return ta.base_type in BUILTIN_TYPES or ta.base_type in self.classes or ta.base_type in self.enums

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
        return infer_type(expr, self.scope, self.classes, self.enums, self.functions)

    def _infer_binary_type(self, expr: ast.BinaryExpr) -> str | None:
        return infer_binary_type(expr, self.scope, self.classes, self.enums, self.functions)

    def _can_coerce(self, src: str, dst: str) -> bool:
        return can_coerce(src, dst)
