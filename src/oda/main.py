"""OdaLanguage CLI — transpile, build, and run .oda programs."""
from __future__ import annotations
import argparse
from dataclasses import fields, is_dataclass
import json
import os
import subprocess
import sys
from pathlib import Path

from .lexer import Lexer
from .parser import Parser
from .semantic import SemanticAnalyzer
from .codegen import CCodeGenerator
from .errors import OdaError, flatten_errors, format_errors_json
from .importer import Importer


def _compile_command(cc: str, c_path: Path, bin_path: Path) -> list[str]:
    args = [cc, str(c_path), "-o", str(bin_path), "-Wall", "-O2"]
    if "#include <math.h>" in c_path.read_text():
        args.append("-lm")
    return args


def _emit_errors(errors: list[OdaError], output_format: str, *, footer: str | None = None) -> None:
    flat = flatten_errors(errors)
    if output_format == "json":
        print(format_errors_json(flat), file=sys.stderr)
        return

    for err in flat:
        print(err.format(), file=sys.stderr)
    if footer:
        print(footer, file=sys.stderr)


def _read_source(path: str) -> str:
    """Read an entry source file, surfacing I/O failures as OdaErrors."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise OdaError(f"Source file is not valid UTF-8: {e.reason}",
                       filename=path, code="E4007") from e
    except OSError as e:
        raise OdaError(f"Cannot read source file: {e.strerror or e}",
                       filename=path, code="E4006") from e


def _emit_internal_error(exc: BaseException, output_format: str) -> None:
    """Top-level catch-all: report an unexpected exception as E5000.

    Never leaks a Python traceback to stderr unless ODA_DEBUG=1.
    """
    summary = (str(exc).splitlines() or [""])[0]
    obj = {
        "code": "E5000",
        "error_type": "InternalError",
        "message": f"{type(exc).__name__}: {summary}".rstrip(": "),
    }
    if os.environ.get("ODA_DEBUG") == "1":
        import traceback
        traceback.print_exc()
    if output_format == "json":
        print(json.dumps(obj, indent=2), file=sys.stderr)
    else:
        print(f"  ✗ internal compiler error [{obj['code']}]: {obj['message']}",
              file=sys.stderr)


def _parse_program(source: str, filename: str, output_format: str = "text"):
    try:
        importer = Importer(filename)
        return importer.load_entry(source, filename)
    except OdaError as e:
        _emit_errors([e], output_format)
        sys.exit(1)


def _ast_to_jsonable(node):
    if is_dataclass(node):
        data = {"node_type": type(node).__name__}
        for field in fields(node):
            data[field.name] = _ast_to_jsonable(getattr(node, field.name))
        return data
    if isinstance(node, list):
        return [_ast_to_jsonable(item) for item in node]
    if isinstance(node, dict):
        return {key: _ast_to_jsonable(value) for key, value in node.items()}
    return node


def _pipeline(source: str, filename: str, output_format: str = "text") -> str:
    """Run the full Oda → C pipeline; returns generated C code."""
    # 1. Parse and Resolve Imports (Unity Build)
    tree = _parse_program(source, filename, output_format)

    # 2. Semantic analysis
    sa = SemanticAnalyzer(filename)
    sa.analyze(tree)
    if sa.errors:
        _emit_errors(
            sa.errors,
            output_format,
            footer=f"\n  ✗ {len(sa.errors)} semantic error(s) found.\n  Compilation stopped.",
        )
        sys.exit(1)

    # 4. Code generation
    c_code = CCodeGenerator().generate(tree)
    return c_code


def cmd_transpile(args):
    src = _read_source(args.file)
    c_code = _pipeline(src, args.file, args.output_format)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "output.c"
    out_path.write_text(c_code)
    print(f"  ✓ Transpiled → {out_path}")


def cmd_build(args):
    src = _read_source(args.file)
    c_code = _pipeline(src, args.file, args.output_format)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    c_path = out_dir / "output.c"
    c_path.write_text(c_code)

    bin_name = Path(args.file).stem
    bin_path = out_dir / bin_name
    cc = os.environ.get("CC", "gcc")
    result = subprocess.run(
        _compile_command(cc, c_path, bin_path),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if getattr(args, "output_format", "text") == "json":
            err_msg = result.stderr.strip().split("\n")[0] if result.stderr.strip() else "C compiler rejected generated output"
            obj = {
                "code": "E5001",
                "error_type": "CodegenError",
                "phase": "codegen-cc",
                "message": err_msg,
                "detail": result.stderr
            }
            print(json.dumps(obj, indent=2), file=sys.stderr)
        else:
            print("  ✗ GCC errors:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Built → {bin_path}")


def cmd_run(args):
    src = _read_source(args.file)
    c_code = _pipeline(src, args.file, args.output_format)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    c_path = out_dir / "output.c"
    c_path.write_text(c_code)

    bin_name = Path(args.file).stem
    bin_path = out_dir / bin_name
    cc = os.environ.get("CC", "gcc")
    result = subprocess.run(
        _compile_command(cc, c_path, bin_path),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if getattr(args, "output_format", "text") == "json":
            err_msg = result.stderr.strip().split("\n")[0] if result.stderr.strip() else "C compiler rejected generated output"
            obj = {
                "code": "E5001",
                "error_type": "CodegenError",
                "phase": "codegen-cc",
                "message": err_msg,
                "detail": result.stderr
            }
            print(json.dumps(obj, indent=2), file=sys.stderr)
        else:
            print("  ✗ GCC errors:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Running {bin_path} …\n")
    result_run = subprocess.run([str(bin_path)])
    sys.exit(result_run.returncode)


def cmd_export_ast(args):
    src = _read_source(args.file)
    tree = _parse_program(src, args.file, args.output_format)
    print(json.dumps(_ast_to_jsonable(tree), indent=2))


def main():
    p = argparse.ArgumentParser(
        prog="oda",
        description="OdaLanguage Transpiler — The safest room for code.",
    )
    p.add_argument("--export-ast", metavar="FILE",
                   help="Parse a .oda source file and print its AST as JSON")
    p.add_argument("--output-format", choices=("text", "json"), default="text",
                   help="Error output format for --export-ast (default: text)")
    sub = p.add_subparsers(dest="command")

    for name, fn in [("transpile", cmd_transpile),
                     ("build", cmd_build),
                     ("run", cmd_run)]:
        sp = sub.add_parser(name)
        sp.add_argument("file", help="Path to .oda source file")
        sp.add_argument("-o", "--output", default="output",
                        help="Output directory (default: output/)")
        sp.add_argument("--output-format", choices=("text", "json"), default="text",
                        help="Error output format (default: text)")
        sp.set_defaults(func=fn)

    ast_parser = sub.add_parser("export-ast")
    ast_parser.add_argument("file", help="Path to .oda source file")
    ast_parser.add_argument("--output-format", choices=("text", "json"), default="text",
                            help="Error output format (default: text)")
    ast_parser.set_defaults(func=cmd_export_ast)

    args = p.parse_args()
    output_format = getattr(args, "output_format", "text")
    try:
        if args.export_ast:
            args.file = args.export_ast
            cmd_export_ast(args)
            return

        if not args.command:
            p.print_help()
            sys.exit(0)

        args.func(args)
    except OdaError as e:
        _emit_errors([e], output_format)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 — last-resort guard: no input may crash
        _emit_internal_error(e, output_format)
        sys.exit(1)


if __name__ == "__main__":
    main()
