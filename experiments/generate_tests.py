import os
import json
import subprocess
import csv

CORPUS_DIR = "/Users/melekzevit/Desktop/Ali-Okul/OdaLanguage/experiments/corpus"
ODA_CMD = "/Users/melekzevit/Desktop/Ali-Okul/OdaLanguage/oda"

TEST_CASES = [
    # E3001
    {
        "name": "e3001_coercion_decl",
        "category": "unsafe_numeric_coercion",
        "expected_code": "E3001",
        "num_bugs": 1,
        "desc": "Narrowing coercion from float to int on declaration.",
        "broken": "int x = 3.14\nprint(x)\n",
        "fixed": "int x = 3\nprint(x)\n"
    },
    {
        "name": "e3001_coercion_assign",
        "category": "unsafe_numeric_coercion",
        "expected_code": "E3001",
        "num_bugs": 1,
        "desc": "Narrowing coercion from float to int on assignment.",
        "broken": "int x = 0\nx = 3.14\nprint(x)\n",
        "fixed": "int x = 0\nx = 3\nprint(x)\n"
    },
    {
        "name": "e3001_coercion_string_to_int",
        "category": "unsafe_numeric_coercion",
        "expected_code": "E3001",
        "num_bugs": 1,
        "desc": "Cannot coerce string to int.",
        "broken": "int x = \"5\"\nprint(x)\n",
        "fixed": "int x = 5\nprint(x)\n"
    },
    # E3034/E3035
    {
        "name": "e3034_reassign_stay",
        "category": "mutability",
        "expected_code": "E3034",
        "num_bugs": 1,
        "desc": "Reassigning a stay variable.",
        "broken": "stay int x = 5\nx = 10\nprint(x)\n",
        "fixed": "int x = 5\nx = 10\nprint(x)\n"
    },
    {
        "name": "e3034_reassign_stay_string",
        "category": "mutability",
        "expected_code": "E3034",
        "num_bugs": 1,
        "desc": "Reassigning a stay string variable.",
        "broken": "stay string s = \"a\"\ns = \"b\"\nprint(s)\n",
        "fixed": "string s = \"a\"\ns = \"b\"\nprint(s)\n"
    },
    {
        "name": "e3035_mutate_stay_array",
        "category": "mutability",
        "expected_code": "E3035",
        "num_bugs": 1,
        "desc": "Mutating an element of a stay array.",
        "broken": "stay int[] arr = [1, 2]\narr[0] = 3\nprint(arr[0])\n",
        "fixed": "int[] arr = [1, 2]\narr[0] = 3\nprint(arr[0])\n"
    },
    {
        "name": "e3035_mutate_stay_matrix",
        "category": "mutability",
        "expected_code": "E3035",
        "num_bugs": 1,
        "desc": "Mutating an element of a multi-dimensional stay array.",
        "broken": "stay int[][] arr = [[1]]\narr[0][0] = 2\nprint(arr[0][0])\n",
        "fixed": "int[][] arr = [[1]]\narr[0][0] = 2\nprint(arr[0][0])\n"
    },
    # E3002
    {
        "name": "e3002_guard_no_return",
        "category": "guard_exit",
        "expected_code": "E3002",
        "num_bugs": 1,
        "desc": "Guard block missing return statement.",
        "broken": "func do_stuff() {\n    guard string? x = null else {\n        when (IoError) {\n            print(\"error\")\n        }\n    }\n    print(x)\n}\ndo_stuff()\n",
        "fixed": "func do_stuff() {\n    guard string? x = null else {\n        when (IoError) {\n            print(\"error\")\n            return\n        }\n    }\n    print(x)\n}\ndo_stuff()\n"
    },
    {
        "name": "e3002_guard_multiple_when",
        "category": "guard_exit",
        "expected_code": "E3002",
        "num_bugs": 1,
        "desc": "One of the guard when blocks fails to exit.",
        "broken": "func test() {\n    guard string? s = null else {\n        when (IoError) {\n            return\n        }\n        when (FileNotFound) {\n            print(\"not found\")\n        }\n    }\n    print(s)\n}\ntest()\n",
        "fixed": "func test() {\n    guard string? s = null else {\n        when (IoError) {\n            return\n        }\n        when (FileNotFound) {\n            print(\"not found\")\n            return\n        }\n    }\n    print(s)\n}\ntest()\n"
    },
    {
        "name": "e3002_guard_nested_no_return",
        "category": "guard_exit",
        "expected_code": "E3002",
        "num_bugs": 1,
        "desc": "Guard block contains if but no guaranteed return.",
        "broken": "func foo() {\n    guard string? y = null else {\n        when (IoError) {\n            if (true) {\n                print(\"error\")\n            }\n        }\n    }\n    print(y)\n}\nfoo()\n",
        "fixed": "func foo() {\n    guard string? y = null else {\n        when (IoError) {\n            if (true) {\n                print(\"error\")\n            }\n            return\n        }\n    }\n    print(y)\n}\nfoo()\n"
    },
    # E3020
    {
        "name": "e3020_wrong_arg_func",
        "category": "wrong_arg_type",
        "expected_code": "E3020",
        "num_bugs": 1,
        "desc": "Passing string to int parameter.",
        "broken": "func foo(int x) {\n    print(x)\n}\nfoo(\"str\")\n",
        "fixed": "func foo(string x) {\n    print(x)\n}\nfoo(\"str\")\n"
    },
    {
        "name": "e3020_wrong_arg_method",
        "category": "wrong_arg_type",
        "expected_code": "E3020",
        "num_bugs": 1,
        "desc": "Passing int to string parameter in method.",
        "broken": "class C {\n    construct() {}\n    func m(string s) {\n        print(s)\n    }\n}\nC c = C()\nc.m(5)\n",
        "fixed": "class C {\n    construct() {}\n    destruct() {}\n    func m(int s) {\n        // int literal print bug fix: use dummy print\n        print(\"fixed\")\n    }\n}\nC c = C()\nc.m(5)\n"
    },
    {
        "name": "e3020_wrong_arg_ref",
        "category": "wrong_arg_type",
        "expected_code": "E3020",
        "num_bugs": 1,
        "desc": "Passing string ref to int ref parameter.",
        "broken": "func bar(ref int x) {\n    x = 1\n}\nstring s = \"a\"\nbar(ref s)\nprint(s)\n",
        "fixed": "func bar(ref string x) {\n    x = \"b\"\n}\nstring s = \"a\"\nbar(ref s)\nprint(s)\n"
    },
    # E3041
    {
        "name": "e3041_index_string",
        "category": "array_index",
        "expected_code": "E3041",
        "num_bugs": 1,
        "desc": "Array indexed with a string.",
        "broken": "int[] a = [1]\nprint(a[\"0\"])\n",
        "fixed": "int[] a = [1]\nprint(a[0])\n"
    },
    {
        "name": "e3041_index_float",
        "category": "array_index",
        "expected_code": "E3041",
        "num_bugs": 1,
        "desc": "Array indexed with a float.",
        "broken": "int[] a = [1]\nprint(a[0.0])\n",
        "fixed": "int[] a = [1]\nprint(a[0])\n"
    },
    {
        "name": "e3041_index_assign_string",
        "category": "array_index",
        "expected_code": "E3041",
        "num_bugs": 1,
        "desc": "Assigning to array element using string index.",
        "broken": "int[] a = [1]\na[\"0\"] = 2\nprint(a[0])\n",
        "fixed": "int[] a = [1]\na[0] = 2\nprint(a[0])\n"
    },
    # E3046
    {
        "name": "e3046_illegal_main",
        "category": "func_main",
        "expected_code": "E3046",
        "num_bugs": 1,
        "desc": "Defining a function named main.",
        "broken": "func main() {\n    print(\"hello\")\n}\n",
        "fixed": "func my_main() {\n    print(\"hello\")\n}\nmy_main()\n"
    },
    {
        "name": "e3046_illegal_main_args",
        "category": "func_main",
        "expected_code": "E3046",
        "num_bugs": 1,
        "desc": "Defining a function named main with args.",
        "broken": "func main(int x) {\n    print(x)\n}\n",
        "fixed": "func my_main(int x) {\n    print(x)\n}\nmy_main(5)\n"
    },
    {
        "name": "e3046_illegal_main_return",
        "category": "func_main",
        "expected_code": "E3046",
        "num_bugs": 1,
        "desc": "Defining a function named main with return value.",
        "broken": "func main() -> int {\n    return 0\n}\n",
        "fixed": "func my_main() -> int {\n    return 0\n}\nmy_main()\n"
    },
    # Multi-bugs
    {
        "name": "multi_01_coercion_stay",
        "category": "multi_bug",
        "expected_code": "E3034",
        "expected_code_2": "E3001",
        "num_bugs": 2,
        "desc": "Reassigning a stay variable with a float.",
        "broken": "stay int x = 5\nx = 5.5\nprint(x)\n",
        "fixed": "int x = 5\nx = 6\nprint(x)\n"
    },
    {
        "name": "multi_02_guard_wrong_arg",
        "category": "multi_bug",
        "expected_code": "E3002",
        "expected_code_2": "E3020",
        "num_bugs": 2,
        "desc": "Guard block without return passing wrong arg to func.",
        "broken": "func f(int x) {\n    print(\"f\")\n}\nfunc g() {\n    guard string? x = null else {\n        when (IoError) {\n            f(\"string\")\n        }\n    }\n    print(x)\n}\ng()\n",
        "fixed": "func f(int x) {\n    print(\"f\")\n}\nfunc g() {\n    guard string? x = null else {\n        when (IoError) {\n            f(5)\n            return\n        }\n    }\n    print(x)\n}\ng()\n"
    },
    {
        "name": "multi_03_main_array_index",
        "category": "multi_bug",
        "expected_code": "E3046",
        "expected_code_2": "E3041",
        "num_bugs": 2,
        "desc": "Defining main and indexing array with string.",
        "broken": "func main() {\n}\nint[] a = [1]\nprint(a[\"0\"])\n",
        "fixed": "func my_main() {\n}\nint[] a = [1]\nprint(a[0])\n"
    }
]

def main():
    log_data = []
    
    for case in TEST_CASES:
        folder = os.path.join(CORPUS_DIR, case["name"])
        os.makedirs(folder, exist_ok=True)
        
        # Write meta.json
        meta = {
            "category": case["category"],
            "expected_code": case["expected_code"],
            "num_bugs": case["num_bugs"],
            "description": case["desc"]
        }
        if "expected_code_2" in case:
            meta["expected_code_2"] = case["expected_code_2"]
            
        with open(os.path.join(folder, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)
            
        # Write broken.oda
        broken_path = os.path.join(folder, "broken.oda")
        with open(broken_path, "w") as f:
            f.write(case["broken"])
            
        # Write fixed.oda
        fixed_path = os.path.join(folder, "fixed.oda")
        with open(fixed_path, "w") as f:
            f.write(case["fixed"])
            
        # Transpile broken.oda
        transpile_cmd = [ODA_CMD, "transpile", broken_path, "--output-format=json"]
        res = subprocess.run(transpile_cmd, capture_output=True, text=True)
        
        transpile_ok = False
        try:
            out_json = json.loads(res.stdout)
            codes = [err.get("code") for err in out_json.get("errors", [])]
            if case["expected_code"] in codes:
                if "expected_code_2" in case:
                    if case["expected_code_2"] in codes:
                        transpile_ok = True
                else:
                    transpile_ok = True
            if not transpile_ok:
                print(f"[{case['name']}] FAILED TRANSPILE CHECK: Expected {case['expected_code']}, got {codes}")
        except Exception as e:
            print(f"[{case['name']}] FAILED TRANSPILE PARSE: {e}, Output: {res.stdout}")
            
        # Run fixed.oda
        run_cmd = [ODA_CMD, "run", fixed_path]
        res_run = subprocess.run(run_cmd, capture_output=True, text=True)
        
        run_ok = res_run.returncode == 0
        if run_ok:
            with open(os.path.join(folder, "expected_stdout.txt"), "w") as f:
                f.write(res_run.stdout)
        else:
            print(f"[{case['name']}] FAILED RUN: {res_run.stderr}")
            
        log_data.append({
            "case": case["name"],
            "expected_code": case["expected_code"] + (f" & {case['expected_code_2']}" if "expected_code_2" in case else ""),
            "transpile_ok": "Yes" if transpile_ok else "No",
            "run_ok": "Yes" if run_ok else "No"
        })
        
    # Write CSV
    with open(os.path.join("/Users/melekzevit/Desktop/Ali-Okul/OdaLanguage", "verification_log.csv"), "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["case", "expected_code", "transpile_ok", "run_ok"])
        writer.writeheader()
        writer.writerows(log_data)
        
    print("Generation complete! Check verification_log.csv")

if __name__ == "__main__":
    main()
