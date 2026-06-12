# OdaLanguage Specification

**Source of truth for AI agents writing Oda code.** Oda transpiles to C. It requires strict explicit typing, block scopes, and RAII.

## 1. Types

| Type | Example / Detail |
|---|---|
| `int` | `int x = -10` |
| `uint` | `uint count = 5u` (`u` suffix required for uint literals) |
| `float` | `float ratio = 3.14` |
| `bool` | `bool valid = true` |
| `string` | `string name = "oda"` |
| `T?` | `int? maybe = null` (Nullable types) |
| `T[]` | `int[] arr = [1, 2]` |
| `enum` | `enum Mode { A, B }` |

**Widening (Implicit Coercion Allowed)**
- `int` → `float`
- `uint` → `float`
- `char` → `string`

**Casts (`expr as type` or `(type)expr`)**
Implicit narrowing is **NOT** allowed. Unsafe casts require explicit syntax.
```oda
float f = 3.14
int i = f as int
uint u = (uint)i
```

## 2. Variables

```oda
int a = 1              // Mutable
stay int b = 2         // Immutable (cannot reassign)
int? c = null          // Nullable initialization
// string _private     // '_' prefix indicates private (in classes)
```

## 3. Functions

```oda
// Normal declaration
func add(int a, int b) -> int {
    return a + b
}

// Pass by reference (required for mutating, or passing classes with heap fields)
func bump(ref int value) {
    value += 1
}

// Call site: use `ref` keyword
int total = 40
bump(ref total)
```
**Return Rules**: All code paths must explicitly return a value if `-> type` is specified.

## 4. Control Flow

```oda
// If/Else
if (x > 0) { } elif (x < 0) { } else { }

// While
while (x > 0) { x -= 1 }

// For-In
for (int i in 0..10) { }           // Exclusive range
for (int i in 0..=10 step 2) { }   // Inclusive range with step
for (int x in [1, 2]) { }          // Arrays

// C-Style For
for (int i = 0; i < 5; i += 1) { }

// Infinite Loop
for {}

// Pattern Matching (int, string, enum)
match (mode) {
    Mode.A { print("A") }
    _ { print("Default") }
}
```

## 5. Null Safety

```oda
int? maybe = null
int definitely = maybe ?? 0  // Fallback expression

// Guard for unwrapping nullable values (e.g., from I/O)
// MUST exit scope in the else block!
guard string content = readFile("config.txt") else {
    when (FileNotFound) {
        return    // Mandatory scope exit (return, break, continue)
    }
}
print(content)
```

## 6. Classes

**RAII Semantics**: `destruct()` is automatically called at lexical scope exit.
```oda
class Counter {
    int _value          // Private field

    construct(int start) {
        _value = start
    }

    func inc() {
        _value += 1
    }

    destruct() {
        print("clean up")
    }
}

// Usage
Counter c = Counter(0)
c.inc()
```

## 7. Imports

Imports must be at the **top level** of the file.
```oda
import std.math
from std.string import strlen

float s = math.sin(3.14)
uint l = strlen("test")
```
**`std` Provides**:
- `std.prelude` (auto-imported): `print(string)`, `input() -> string`, `assert(bool)`
- `std.math`: `sin(float)`, `cos(float)`, `sqrt(float)`
- `std.string`: `strlen(string)`

## 8. Pitfalls (Top Errors)

| Code | Wrong | Right |
|---|---|---|
| **E3001** | `uint x = 5` | `uint x = 5u` (or `5 as uint`) |
| **E3002** | `guard s = readFile("x") else { when(IoError) { print("E") } }` | `... else { when(IoError) { return } }` (Must exit scope) |
| **E3003** | `counter._value = 1` | `counter.set_value(1)` (Cannot access private members outside class) |
| **E3004** | `for (int x in unknown_array) { }` | Iterate over arrays with known size at compile time, or literals. |
| **E3026** | `func dump(Counter c) { }` | `func dump(ref Counter c) { }` (Class with heap fields requires `ref`) |
| **E3024** | `bump(total)` | `bump(ref total)` (Call site requires `ref` if parameter is `ref`) |
| **E3034** | `stay int x = 1; x = 2` | `int x = 1; x = 2` (Cannot reassign `stay` immutable variable) |
| **E3035** | `stay int[] arr = [1]; arr[0] = 2` | `int[] arr = [1]; arr[0] = 2` (Cannot modify `stay` array elements) |

*Note: Classes, Enums, and Imports must be declared at the top level, not inside functions.*

## 9. Compiler Interface

```bash
# Compile to executable
./oda build src.oda

# Compile and run immediately
./oda run src.oda

# Transpile to C only
./oda transpile src.oda
```

**JSON Output (`--output-format=json`)**
Used for machine-readable correction loops.
```bash
./oda transpile src.oda --output-format=json
```
```json
[
  {
    "file": "src.oda",
    "line": 1,
    "column": 7,
    "error_type": "SemanticError",
    "message": "Undefined variable 'missing_value'"
  }
]
```
