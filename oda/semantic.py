"""Semantic analyzer for OdaLanguage — type checking, scope, coercion rules."""
from __future__ import annotations
from . import ast_nodes as ast
from .errors import SemanticError

# Widening-only coercion table: source → allowed targets
_WIDENING = {
    "int":   {"float", "uint"},
    "uint":  {"float"},
    "float": set(),
    "char":  {"string"},
    "bool":  set(),
    "string": set(),
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


class SemanticAnalyzer:
    def __init__(self, filename: str = "<source>"):
        self.filename = filename
        self.scope = Scope()
        self.classes: dict[str, ClassInfo] = {}
        self.functions: dict[str, FuncInfo] = {}
        self.errors: list[SemanticError] = []
        self._current_class: str | None = None
        # Register built-in functions
        for name in ("print", "input", "readFile"):
            self.functions[name] = FuncInfo(name, ast.FuncDeclaration(name=name))

    def _err(self, msg: str, node: ast.Node):
        self.errors.append(SemanticError(msg, node.line, node.column, self.filename))

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
        elif isinstance(stmt, ast.IfStatement):
            self._analyze_if(stmt)
        elif isinstance(stmt, ast.WhileStatement):
            self._analyze_expr(stmt.condition)
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.ForStatement):
            if stmt.init:
                self._analyze_stmt(stmt.init)
            if stmt.condition:
                self._analyze_expr(stmt.condition)
            if stmt.update:
                self._analyze_expr(stmt.update)
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.ForRangeStatement):
            self._analyze_expr(stmt.start)
            self._analyze_expr(stmt.end)
            self.scope.define(Symbol(stmt.var_name, stmt.var_type))
            self._analyze_block(stmt.body)
        elif isinstance(stmt, ast.ReturnStatement):
            if stmt.value:
                self._analyze_expr(stmt.value)
        elif isinstance(stmt, ast.GuardStatement):
            self._analyze_expr(stmt.expr)
            self.scope.define(Symbol(stmt.var_name, stmt.var_type))
            for case in stmt.cases:
                self._analyze_block(case.body)
        elif isinstance(stmt, ast.MatchStatement):
            self._analyze_expr(stmt.expr)
            for arm in stmt.arms:
                if arm.pattern:
                    self._analyze_expr(arm.pattern)
                self._analyze_block(arm.body)
        elif isinstance(stmt, ast.ExpressionStatement):
            if stmt.expr:
                self._analyze_expr(stmt.expr)

    def _analyze_var_decl(self, stmt: ast.VarDeclaration):
        base = stmt.type_ann.base_type
        # Verify the type exists
        if base not in _WIDENING and base not in self.classes:
            self._err(f"Unknown type '{base}'", stmt)

        # Null safety: non-nullable vars must have an initializer or will be set
        if stmt.initializer:
            self._analyze_expr(stmt.initializer)
            init_type = self._infer_type(stmt.initializer)
            if init_type and init_type != base:
                if not self._can_coerce(init_type, base):
                    self._err(f"Cannot coerce '{init_type}' to '{base}' (narrowing not allowed)", stmt)

            # Non-nullable assigned null
            if not stmt.type_ann.is_nullable and isinstance(stmt.initializer, ast.NullLiteral):
                self._err(f"Cannot assign null to non-nullable '{base}'", stmt)

        self.scope.define(Symbol(stmt.name, stmt.type_ann, is_immutable=stmt.is_immutable))

    def _analyze_func(self, stmt: ast.FuncDeclaration):
        old_scope = self.scope
        self.scope = Scope(old_scope, f"func:{stmt.name}")
        for p in stmt.params:
            self.scope.define(Symbol(p.name, p.type_ann, is_ref=p.is_ref))
        self._analyze_block(stmt.body)
        self.scope = old_scope

    def _analyze_class(self, stmt: ast.ClassDeclaration):
        self._current_class = stmt.name
        old_scope = self.scope
        self.scope = Scope(old_scope, f"class:{stmt.name}")
        # Define fields
        for f in stmt.fields:
            self.scope.define(Symbol(f.name, f.type_ann))
        if stmt.constructor:
            self._analyze_func(stmt.constructor)
        for m in stmt.methods:
            self._analyze_func(m)
        if stmt.destructor:
            self._analyze_func(stmt.destructor)
        self.scope = old_scope
        self._current_class = None

    def _analyze_if(self, stmt: ast.IfStatement):
        self._analyze_expr(stmt.condition)
        self._analyze_block(stmt.body)
        for cond, body in stmt.elif_branches:
            self._analyze_expr(cond)
            self._analyze_block(body)
        if stmt.else_body:
            self._analyze_block(stmt.else_body)

    def _analyze_block(self, stmts: list):
        for s in stmts:
            self._analyze_stmt(s)

    # ── expressions ──────────────────────────────────────────
    def _analyze_expr(self, expr):
        if isinstance(expr, ast.Identifier):
            sym = self.scope.lookup(expr.name)
            if sym is None and expr.name not in self.classes and expr.name not in self.functions:
                # Allow underscore-prefixed within class context
                if not (self._current_class and expr.name.startswith("_")):
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
        elif isinstance(expr, ast.UnaryExpr):
            self._analyze_expr(expr.operand)
        elif isinstance(expr, ast.CallExpr):
            self._analyze_expr(expr.callee)
            for a in expr.args:
                self._analyze_expr(a)
        elif isinstance(expr, ast.MemberAccess):
            self._analyze_expr(expr.obj)
        elif isinstance(expr, ast.IndexAccess):
            self._analyze_expr(expr.obj)
            self._analyze_expr(expr.index)
        elif isinstance(expr, ast.InterpolatedString):
            for part in expr.parts:
                if isinstance(part, ast.Identifier):
                    self._analyze_expr(part)

    # ── type inference (basic) ───────────────────────────────
    def _infer_type(self, expr) -> str | None:
        if isinstance(expr, ast.IntegerLiteral):
            return "int"
        if isinstance(expr, ast.FloatLiteral):
            return "float"
        if isinstance(expr, (ast.StringLiteral, ast.InterpolatedString)):
            return "string"
        if isinstance(expr, ast.BoolLiteral):
            return "bool"
        if isinstance(expr, ast.NullLiteral):
            return None
        if isinstance(expr, ast.Identifier):
            sym = self.scope.lookup(expr.name)
            return sym.type_ann.base_type if sym else None
        return None

    def _can_coerce(self, src: str, dst: str) -> bool:
        if src == dst:
            return True
        return dst in _WIDENING.get(src, set())
