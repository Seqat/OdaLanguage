"""OdaLanguage CLI — transpile, build, and run .oda programs."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .semantic import SemanticAnalyzer
from .codegen import CCodeGenerator
from .errors import OdaError, SemanticError
from .importer import Importer


def _pipeline(source: str, filename: str) -> tuple[str | None, list[SemanticError]]:
    """Run the full Oda → C pipeline; returns (c_code, errors)."""
    importer = Importer(filename)
    tree = importer.load_entry(source, filename)

    sa = SemanticAnalyzer(filename)
    sa.analyze(tree)
    if sa.errors:
        return None, sa.errors

    c_code = CCodeGenerator().generate(tree)
    return c_code, []


def _print_semantic_errors(errors: list[SemanticError]) -> None:
    for e in errors:
        print(e.format(), file=sys.stderr)
    print(f"\n  ✗ {len(errors)} semantic error(s) found.\n  Compilation stopped.", file=sys.stderr)


def cmd_transpile(args):
    src = Path(args.file).read_text()
    c_code, errors = _pipeline(src, args.file)
    if errors:
        fmt = getattr(args, "output_format", "text")
        if fmt == "json":
            print(json.dumps({
                "success": False,
                "errors": [
                    {"code": e.code, "message": e.message, "line": e.line, "column": e.column}
                    for e in errors
                ],
            }))
        else:
            _print_semantic_errors(errors)
        sys.exit(1)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "output.c"
    out_path.write_text(c_code)
    if getattr(args, "output_format", "text") == "json":
        print(json.dumps({"success": True}))
    else:
        print(f"  ✓ Transpiled → {out_path}")


def cmd_build(args):
    src = Path(args.file).read_text()
    c_code, errors = _pipeline(src, args.file)
    if errors:
        _print_semantic_errors(errors)
        sys.exit(1)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    c_path = out_dir / "output.c"
    c_path.write_text(c_code)

    bin_name = Path(args.file).stem
    bin_path = out_dir / bin_name
    cc = os.environ.get("CC", "gcc")
    result = subprocess.run(
        [cc, str(c_path), "-o", str(bin_path), "-Wall", "-O2"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("  ✗ GCC errors:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Built → {bin_path}")


def cmd_run(args):
    src = Path(args.file).read_text()
    c_code, errors = _pipeline(src, args.file)
    if errors:
        _print_semantic_errors(errors)
        sys.exit(1)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    c_path = out_dir / "output.c"
    c_path.write_text(c_code)

    bin_name = Path(args.file).stem
    bin_path = out_dir / bin_name
    cc = os.environ.get("CC", "gcc")
    result = subprocess.run(
        [cc, str(c_path), "-o", str(bin_path), "-Wall", "-O2"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("  ✗ GCC errors:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Running {bin_path} …\n", file=sys.stderr)
    subprocess.run([str(bin_path)])


def main():
    p = argparse.ArgumentParser(
        prog="oda",
        description="OdaLanguage Transpiler — The safest room for code.",
    )
    sub = p.add_subparsers(dest="command")

    transpile_sp = sub.add_parser("transpile")
    transpile_sp.add_argument("file", help="Path to .oda source file")
    transpile_sp.add_argument("-o", "--output", default="output",
                              help="Output directory (default: output/)")
    transpile_sp.add_argument("--output-format", dest="output_format",
                              choices=["text", "json"], default="text",
                              help="Error/success output format (default: text)")
    transpile_sp.set_defaults(func=cmd_transpile)

    for name, fn in [("build", cmd_build), ("run", cmd_run)]:
        sp = sub.add_parser(name)
        sp.add_argument("file", help="Path to .oda source file")
        sp.add_argument("-o", "--output", default="output",
                        help="Output directory (default: output/)")
        sp.set_defaults(func=fn)

    args = p.parse_args()
    if not args.command:
        p.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except OdaError as e:
        print(e.format(), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
