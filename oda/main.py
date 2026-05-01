"""OdaLanguage CLI — transpile, build, and run .oda programs."""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

from .lexer import Lexer
from .parser import Parser
from .semantic import SemanticAnalyzer
from .codegen import CCodeGenerator
from .errors import OdaError


def _pipeline(source: str, filename: str) -> str:
    """Run the full Oda → C pipeline; returns generated C code."""
    # 1. Lex
    tokens = Lexer(source, filename).tokenize()

    # 2. Parse
    tree = Parser(tokens, filename).parse()

    # 3. Semantic analysis
    sa = SemanticAnalyzer(filename)
    sa.analyze(tree)
    if sa.errors:
        for e in sa.errors:
            print(e.format(), file=sys.stderr)
        print(f"\n  ✗ {len(sa.errors)} semantic error(s) found.\n  Compilation stopped.", file=sys.stderr)
        sys.exit(1)

    # 4. Code generation
    c_code = CCodeGenerator().generate(tree)
    return c_code


def cmd_transpile(args):
    src = Path(args.file).read_text()
    c_code = _pipeline(src, args.file)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "output.c"
    out_path.write_text(c_code)
    print(f"  ✓ Transpiled → {out_path}")


def cmd_build(args):
    src = Path(args.file).read_text()
    c_code = _pipeline(src, args.file)
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
    c_code = _pipeline(src, args.file)
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
    print(f"  ✓ Running {bin_path} …\n")
    subprocess.run([str(bin_path)])


def main():
    p = argparse.ArgumentParser(
        prog="oda",
        description="OdaLanguage Transpiler — The safest room for code.",
    )
    sub = p.add_subparsers(dest="command")

    for name, fn in [("transpile", cmd_transpile),
                     ("build", cmd_build),
                     ("run", cmd_run)]:
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
