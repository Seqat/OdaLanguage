# OdaLanguage

> **"The safest room for code."**

OdaLanguage is a **safe, deterministic target language for AI-generated systems code**. It gives AI agents a small, inspectable language that transpiles to standard C while enforcing strict semantic checks before code generation.

The goal is not to replace C as a systems substrate. The goal is to give generated systems code a safer source language with explicit memory scopes, conservative type rules, predictable lowering, and machine-readable compiler feedback that an agent can use for correction loops.

The compiler pipeline is intentionally simple:

```text
Lexer -> Parser -> AST -> Semantic Analyzer -> C Code Generator -> native binary
```

![transpiler process](public/image.png)

## Features

| Feature | Status |
|---|---|
| C transpilation | `.oda` source is lowered into a single C translation unit. |
| Semi-static typing | Explicit primitive, array, function, and class annotations. |
| Null safety | Nullable values use `?`; fallback expressions use `??`; `guard ... when` unwraps nullable results. |
| Immutability | `stay` marks a variable as immutable after initialization. |
| RAII-style cleanup | `destruct()` is called automatically when generated scopes exit. |
| Ranges and loops | `for-in`, `while`, C-style `for`, `..`, `..=`, `step`, and `reversed`. |
| Arrays | Dynamic-style literals, fixed-size annotations, multidimensional arrays, and `new` allocation. |
| Classes | Private fields with `_`, `construct`, methods, and `destruct`. |
| Enums | `enum Name { Variant }` declarations compile to standard C `typedef enum`. |
| `ref` parameters | Explicit pass-by-reference at function boundaries. |
| String interpolation | Interpolated expressions such as `"sum={a+b}"`. |
| Pattern matching | `match (value) { pattern { ... } _ { ... } }` for integers, strings, and enums. |
| Explicit casts | Use `expr as type` or `(type)expr`; narrowing requires an explicit cast. |
| Unsigned integers | `uint` values can be written with a `u` suffix, such as `5u`. |
| File and console I/O | `readFile()` and `input()` builtins. |
| Strict semantic checking | Semantic errors stop compilation before C generation. |
| Explicit memory scopes | Block scopes isolate variables and generated RAII cleanup is tied to lexical scope exits. |
| Machine-readable diagnostics | `--output-format=json` emits parser and semantic errors as structured JSON. |
| AST export | `export-ast` serializes parsed code structure as JSON for agent analysis. |

## Quick Start

```bash
# Transpile only
./oda transpile examples/hello.oda

# Transpile and compile
./oda build examples/hello.oda

# Transpile, compile, and run
./oda run examples/hello.oda

# Export parsed AST as JSON
./oda export-ast examples/hello.oda
# Equivalent flag form
./oda --export-ast examples/hello.oda

# Emit machine-readable diagnostics for correction loops
./oda transpile examples/hello.oda --output-format=json

# Run the compiler test suite
make test
```

## AI-Agent Tooling

OdaLanguage is designed to be useful inside automated code-generation loops:

- **Strict static checks:** undefined variables, private member access, function call arity, argument types, `ref` matching, return coverage, unsafe implicit numeric conversions, and invalid binary expressions are rejected before C is emitted.
- **Explicit memory scopes:** lexical blocks create nested environments, RAII destructors are emitted at scope exits, and generated C avoids non-standard lifetime tricks where possible.
- **Machine-readable diagnostics:** parser and semantic failures can be emitted as a JSON array with `file`, `line`, `column`, `error_type`, and `message`.
- **Machine-readable structure:** `export-ast` emits the parsed AST as JSON with `node_type`, source positions, declarations, statements, expressions, and type annotations.

Example diagnostic output:

```bash
./oda transpile examples/broken.oda --output-format=json
```

```json
[
  {
    "file": "examples/broken.oda",
    "line": 1,
    "column": 7,
    "error_type": "SemanticError",
    "message": "Undefined variable 'missing_value'"
  }
]
```

## Example Programs

The `examples/` directory contains small programs that double as living documentation. Golden tests ensure every `.oda` example transpiles, compiles with `gcc -Wall -Wextra -Werror`, and matches its checked-in C snapshot.

| File | Demonstrates |
|---|---|
| `examples/hello.oda` | Basic variables and expression interpolation. |
| `examples/control_flow.oda` | `match`, ranges, nested loops, `while`, and `step`. |
| `examples/arrays.oda` | Array iteration, indexing, and multidimensional arrays. |
| `examples/functions_ref.oda` | Functions, return values, and `ref` parameters. |
| `examples/classes_raii.oda` | Classes, private fields, constructors, methods, destructors, and RAII cleanup. |
| `examples/guard_io.oda` | `readFile()`, nullable unwrap, and `guard ... when` flow. |

Run any example with:

```bash
./oda run examples/control_flow.oda
```

## Syntax Tour

### Variables And Interpolation

```oda
int a = 45
int b = 2123

print("a+b= {a+b}")
```

Interpolation braces accept full Oda expressions, not only variable names.

### Numeric Types And Casts

```oda
uint workers = 5u
float ratio = 3.75

int rounded = ratio as int
uint explicit_count = (uint)rounded

print("workers={workers}")
print("rounded={rounded}")
```

Oda keeps implicit numeric coercions conservative. Widening such as `int -> float` is allowed, but narrowing conversions such as `float -> int` or potentially unsafe conversions such as `int -> uint` must be written explicitly with a cast.

### Control Flow

```oda
string command = "start"

match (command) {
    "start" { print("command=start") }
    "stop" { print("command=stop") }
    _ { print("command=unknown") }
}

for (int i in 0..=4 step 2) {
    print("i={i}")
}
```

### Enums And Pattern Matching

```oda
enum Mode { Idle, Busy, Done }

func describe(Mode mode) {
    match (mode) {
        Mode.Idle { print("idle") }
        Mode.Busy { print("busy") }
        _ { print("done") }
    }
}

Mode current = Mode.Busy
describe(current)
```

Enum variants are referenced as `EnumName.Variant`. The C generator emits a standard enum with prefixed C variant names, for example `Mode_Busy`, to avoid global name collisions.

### Arrays

```oda
int[][] matrix = [[1, 2], [3, 4]]
print("matrix[1][0]={matrix[1][0]}")

for (int[] row in matrix) {
    print("row-sum={row[0] + row[1]}")
}
```

### Functions And `ref`

```oda
func bump(ref int value) {
    value += 1
}

int total = 41
bump(ref total)
print("total={total}")
```

### Classes And RAII

```oda
class Counter {
    int _value

    construct(int start) {
        _value = start
    }

    func inc() {
        _value += 1
    }

    func get() -> int {
        return _value
    }

    destruct() {
        if (_value >= 0) {
            print("counter closed")
        }
    }
}

Counter counter = Counter(5)
counter.inc()
int current = counter.get()
print("counter now={current}")
```

Fields beginning with `_` are private. The semantic analyzer rejects private member access from outside the class.

### Guard Flow

```oda
func load_config() {
    guard string content = readFile("config.txt") else {
        when (FileNotFound) {
            print("config missing")
            return
        }
    }

    print(content)
}
```

Each `when` block inside a `guard` must leave the current scope with `return`, `break`, or `continue`.

## Project Layout

```text
OdaLanguage/
├── oda                         # CLI wrapper
├── src/oda/
│   ├── tokens.py               # Token definitions
│   ├── lexer.py                # Tokenizer
│   ├── parser.py               # Recursive descent parser
│   ├── ast_nodes.py            # AST dataclasses
│   ├── semantic.py             # Semantic analysis
│   ├── codegen.py              # C code generator
│   ├── importer.py             # Import resolver / unity AST builder
│   └── main.py                 # CLI entry point
├── examples/                   # Executable language examples
├── tests/                      # Unit, integration, and golden tests
└── docs/                       # Language notes
```

## Requirements

- Python 3.10+
- GCC or Clang
- `pytest` for the test suite

## Development Status

OdaLanguage is experimental and under active development. The current implementation prioritizes a small, inspectable compiler pipeline and strict tests over language breadth.
