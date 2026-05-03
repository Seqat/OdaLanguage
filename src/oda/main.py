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
from .errors import OdaError, format_errors_json
from .importer import Importer


def _compile_command(cc: str, c_path: Path, bin_path: Path) -> list[str]:
    args = [cc, str(c_path), "-o", str(bin_path), "-Wall", "-O2"]
    if "#include <math.h>" in c_path.read_text():
        args.append("-lm")
    return args


def _emit_errors(errors: list[OdaError], output_format: str, *, footer: str | None = None) -> None:
    if output_format == "json":
        print(format_errors_json(errors), file=sys.stderr)
        return

    for err in errors:
        print(err.format(), file=sys.stderr)
    if footer:
        print(footer, file=sys.stderr)


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
    src = Path(args.file).read_text()
    c_code = _pipeline(src, args.file, args.output_format)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "output.c"
    out_path.write_text(c_code)
    print(f"  ✓ Transpiled → {out_path}")


def cmd_build(args):
    src = Path(args.file).read_text()
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
        print("  ✗ GCC errors:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Built → {bin_path}")


def cmd_run(args):
    src = Path(args.file).read_text()
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
        print("  ✗ GCC errors:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Running {bin_path} …\n")
    subprocess.run([str(bin_path)])


def cmd_export_ast(args):
    src = Path(args.file).read_text()
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
    if args.export_ast:
        args.file = args.export_ast
        cmd_export_ast(args)
        return

    if not args.command:
        p.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except OdaError as e:
        _emit_errors([e], args.output_format)
        sys.exit(1)


if __name__ == "__main__":
    main()
