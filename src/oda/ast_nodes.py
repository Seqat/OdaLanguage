"""AST node definitions for OdaLanguage."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════
#  Program (root)
# ═══════════════════════════════════════════════════════════════

@dataclass
class Program:
    statements: list = field(default_factory=list)
    line: int = 0
    column: int = 0


# ═══════════════════════════════════════════════════════════════
#  Type annotation helper
# ═══════════════════════════════════════════════════════════════

@dataclass
class TypeAnnotation:
    base_type: str = ""
    is_nullable: bool = False
    is_result: bool = False
    is_array: bool = False
    array_size: Optional[int] = None
    array_depth: int = 0 # 0 for scalar, 1 for [], 2 for [][]
    fixed_sizes: list[int] = field(default_factory=list) # sizes for each dimension
    line: int = 0
    column: int = 0


# ═══════════════════════════════════════════════════════════════
#  Statements
# ═══════════════════════════════════════════════════════════════

@dataclass
class VarDeclaration:
    type_ann: Optional[TypeAnnotation] = None
    name: str = ""
    is_immutable: bool = False
    initializer: Optional[object] = None
    line: int = 0
    column: int = 0

@dataclass
class Parameter:
    type_ann: Optional[TypeAnnotation] = None
    name: str = ""
    is_ref: bool = False
    line: int = 0
    column: int = 0

@dataclass
class FuncDeclaration:
    name: str = ""
    params: list = field(default_factory=list)
    return_type: Optional[TypeAnnotation] = None
    body: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ClassDeclaration:
    name: str = ""
    fields: list = field(default_factory=list)
    methods: list = field(default_factory=list)
    constructor: Optional[FuncDeclaration] = None
    destructor: Optional[FuncDeclaration] = None
    line: int = 0
    column: int = 0

@dataclass
class EnumDeclaration:
    name: str = ""
    variants: list[str] = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class IfStatement:
    condition: Optional[object] = None
    body: list = field(default_factory=list)
    elif_branches: list = field(default_factory=list)
    else_body: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class WhileStatement:
    condition: Optional[object] = None
    body: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ForStatement:
    init: Optional[object] = None
    condition: Optional[object] = None
    update: Optional[object] = None
    body: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ForRangeStatement:
    var_type: Optional[TypeAnnotation] = None
    var_name: str = ""
    start: Optional[object] = None
    end: Optional[object] = None
    is_inclusive: bool = False
    step: Optional[object] = None
    body: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ForInStatement:
    var_type: Optional[TypeAnnotation] = None
    var_name: str = ""
    iterable: Optional[object] = None
    is_reversed: bool = False
    step: Optional[object] = None
    body: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ReturnStatement:
    value: Optional[object] = None
    line: int = 0
    column: int = 0

@dataclass
class BreakStatement:
    line: int = 0
    column: int = 0

@dataclass
class ContinueStatement:
    line: int = 0
    column: int = 0

@dataclass
class WhenCase:
    error_type: str = ""
    body: list = field(default_factory=list)
    line: int = 0
    column: int = 0

GuardCase = WhenCase

@dataclass
class GuardStatement:
    var_type: Optional[TypeAnnotation] = None
    var_name: str = ""
    expr: Optional[object] = None
    cases: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class MatchArm:
    pattern: Optional[object] = None
    body: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class MatchStatement:
    expr: Optional[object] = None
    arms: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ImportStatement:
    module_path: str = ""
    alias: Optional[str] = None
    names: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ExpressionStatement:
    expr: Optional[object] = None
    line: int = 0
    column: int = 0


# ═══════════════════════════════════════════════════════════════
#  Expressions
# ═══════════════════════════════════════════════════════════════

@dataclass
class IntegerLiteral:
    value: int = 0
    line: int = 0
    column: int = 0

@dataclass
class UIntLiteral:
    value: int = 0
    line: int = 0
    column: int = 0

@dataclass
class FloatLiteral:
    value: float = 0.0
    line: int = 0
    column: int = 0

@dataclass
class StringLiteral:
    value: str = ""
    line: int = 0
    column: int = 0

@dataclass
class CharLiteral:
    value: str = ""
    line: int = 0
    column: int = 0

@dataclass
class InterpolatedString:
    parts: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class BoolLiteral:
    value: bool = False
    line: int = 0
    column: int = 0

@dataclass
class NullLiteral:
    line: int = 0
    column: int = 0

@dataclass
class Identifier:
    name: str = ""
    line: int = 0
    column: int = 0

@dataclass
class BinaryExpr:
    left: Optional[object] = None
    op: str = ""
    right: Optional[object] = None
    line: int = 0
    column: int = 0

@dataclass
class UnaryExpr:
    op: str = ""
    operand: Optional[object] = None
    line: int = 0
    column: int = 0

@dataclass
class CastExpr:
    expr: Optional[object] = None
    target_type: Optional[TypeAnnotation] = None
    line: int = 0
    column: int = 0

@dataclass
class AssignExpr:
    target: Optional[object] = None
    op: str = "="
    value: Optional[object] = None
    line: int = 0
    column: int = 0

@dataclass
class CallExpr:
    callee: Optional[object] = None
    args: list = field(default_factory=list)
    ref_flags: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class MemberAccess:
    obj: Optional[object] = None
    member: str = ""
    line: int = 0
    column: int = 0

@dataclass
class IndexAccess:
    obj: Optional[object] = None
    index: Optional[object] = None
    line: int = 0
    column: int = 0

@dataclass
class ArrayLiteral:
    elements: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ConstructorCall:
    class_name: str = ""
    args: list = field(default_factory=list)
    line: int = 0
    column: int = 0

@dataclass
class ArrayAllocation:
    base_type: str = ""
    sizes: list = field(default_factory=list)
    line: int = 0
    column: int = 0
