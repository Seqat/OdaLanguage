"""Shared Oda type inference helpers for semantic analysis and code generation."""
from __future__ import annotations

from . import ast_nodes as ast


# Widening-only coercion table: source -> allowed targets
WIDENING = {
    "int": {"float"},
    "uint": {"float"},
    "float": set(),
    "char": {"string"},
    "bool": set(),
    "string": set(),
}

BUILTIN_TYPES = frozenset(WIDENING)

# Internal poisoned type assigned to expressions whose root cause was already
# reported; every check involving it stays silent to avoid cascading errors.
ERROR_TYPE = "<error>"

_MISSING = object()


def is_error_type(t: str | None) -> bool:
    return t is not None and ERROR_TYPE in t


def full_type(type_ann) -> str | None:
    if type_ann is None:
        return None
    if isinstance(type_ann, str):
        return type_ann

    base_type = getattr(type_ann, "base_type", None)
    if base_type is None:
        return None

    result = base_type
    if getattr(type_ann, "is_array", False):
        result += "[]" * getattr(type_ann, "array_depth", 1)
    if getattr(type_ann, "is_nullable", False):
        result += "?"
    return result


def can_coerce(src: str | None, dst: str | None) -> bool:
    if src is None or dst is None:
        return False
    if is_error_type(src) or is_error_type(dst):
        return True
    if src == dst:
        return True
    return dst in WIDENING.get(src, set())


def infer_type(expr, scope, classes, enums, functions) -> str | None:
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
        if not expr.elements:
            return "any[]"
        element_type = infer_type(expr.elements[0], scope, classes, enums, functions)
        return f"{element_type}[]" if element_type else "any[]"
    if isinstance(expr, ast.ArrayAllocation):
        return expr.base_type + ("[]" * len(expr.sizes))
    if isinstance(expr, ast.Identifier):
        return _lookup_type(scope, expr.name)
    if isinstance(expr, ast.MemberAccess):
        if isinstance(expr.obj, ast.Identifier) and _enum_has_variant(enums, expr.obj.name, expr.member):
            return expr.obj.name
        obj_type = infer_type(expr.obj, scope, classes, enums, functions)
        if is_error_type(obj_type):
            return ERROR_TYPE
        return _class_field_type(classes, obj_type, expr.member)
    if isinstance(expr, ast.IndexAccess):
        obj_type = infer_type(expr.obj, scope, classes, enums, functions)
        if not obj_type:
            return None
        if is_error_type(obj_type):
            return ERROR_TYPE
        if obj_type.endswith("[]"):
            return obj_type[:-2]
        if obj_type == "string":
            return "char"
        return None
    if isinstance(expr, ast.UnaryExpr):
        operand_type = infer_type(expr.operand, scope, classes, enums, functions)
        if is_error_type(operand_type):
            return ERROR_TYPE
        if expr.op == "!" and operand_type == "bool":
            return "bool"
        if expr.op == "-" and operand_type in ("int", "uint", "float"):
            return operand_type
        return None
    if isinstance(expr, ast.CastExpr):
        return full_type(expr.target_type)
    if isinstance(expr, ast.BinaryExpr):
        return infer_binary_type(expr, scope, classes, enums, functions)
    if isinstance(expr, ast.CallExpr):
        if isinstance(expr.callee, ast.Identifier):
            name = expr.callee.name
            if name in classes:
                return name
            return _function_return_type(functions, name)
        if isinstance(expr.callee, ast.MemberAccess):
            obj_type = infer_type(expr.callee.obj, scope, classes, enums, functions)
            if is_error_type(obj_type):
                return ERROR_TYPE
            return _class_method_return_type(classes, obj_type, expr.callee.member)
        return None

    return None


def infer_binary_type(expr: ast.BinaryExpr, scope, classes, enums, functions) -> str | None:
    left = infer_type(expr.left, scope, classes, enums, functions)
    right = infer_type(expr.right, scope, classes, enums, functions)

    if is_error_type(left) or is_error_type(right):
        return ERROR_TYPE

    if expr.op == "??":
        return left or right

    if expr.op in ("&&", "||"):
        return "bool" if left == "bool" and right == "bool" else None

    if expr.op in ("==", "!="):
        if left == right or can_coerce(left, right) or can_coerce(right, left):
            return "bool"
        return None

    if expr.op in ("<", ">", "<=", ">="):
        if _common_numeric_type(left, right) or (left == "char" and right == "char"):
            return "bool"
        return None

    if expr.op == "+" and (left == "string" or right == "string"):
        scalar = ("string", "int", "uint", "float", "bool", "char")
        if left in scalar and right in scalar:
            return "string"
        return None

    if expr.op in ("+", "-", "*", "/", "%"):
        common = _common_numeric_type(left, right)
        if expr.op == "%" and common == "float":
            return None
        return common

    return None


def _common_numeric_type(left: str | None, right: str | None) -> str | None:
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
    if left == "float" and can_coerce(right, "float"):
        return "float"
    if right == "float" and can_coerce(left, "float"):
        return "float"
    return None


def _lookup_type(scope, name: str) -> str | None:
    if scope is None:
        return None
    if hasattr(scope, "lookup"):
        symbol = scope.lookup(name)
    elif isinstance(scope, dict):
        symbol = scope.get(name)
    else:
        symbol = getattr(scope, name, None)
    return _type_from_symbol(symbol)


def _type_from_symbol(symbol) -> str | None:
    if symbol is None:
        return None
    if isinstance(symbol, str):
        return symbol
    if isinstance(symbol, ast.TypeAnnotation):
        return full_type(symbol)
    return full_type(getattr(symbol, "type_ann", None))


def _enum_has_variant(enums, enum_name: str, variant: str) -> bool:
    enum_info = enums.get(enum_name) if isinstance(enums, dict) else None
    if enum_info is None:
        return False
    variants = getattr(enum_info, "variants", enum_info)
    return variant in variants


def _class_field_type(classes, class_name: str | None, field_name: str) -> str | None:
    if not class_name or not isinstance(classes, dict):
        return None
    class_info = classes.get(class_name)
    if class_info is None:
        return None
    field_types = getattr(class_info, "field_types", class_info)
    if not isinstance(field_types, dict) or field_name not in field_types:
        return None
    return full_type(field_types[field_name])


def _class_method_return_type(classes, class_name: str | None, method_name: str) -> str | None:
    if not class_name or not isinstance(classes, dict):
        return None
    class_info = classes.get(class_name)
    decl = getattr(class_info, "decl", None)
    for method in getattr(decl, "methods", []):
        if method.name == method_name:
            return full_type(method.return_type) if method.return_type else "void"
    return None


def _function_return_type(functions, name: str) -> str | None:
    if not isinstance(functions, dict):
        return None
    func_info = functions.get(name, _MISSING)
    if func_info is _MISSING:
        return None
    if func_info is None:
        return "void"
    if isinstance(func_info, str):
        return func_info
    if isinstance(func_info, ast.TypeAnnotation):
        return full_type(func_info)
    decl = getattr(func_info, "decl", func_info)
    return_type = getattr(decl, "return_type", None)
    return full_type(return_type) if return_type else "void"
