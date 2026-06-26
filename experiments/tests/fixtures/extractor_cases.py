"""Test fixture cases for the Oda code extractor.

Each case is a dictionary with keys:
- 'name': Unique identifier for the test case and variation type.
- 'raw': The simulated model completion (input to the extractor).
- 'expected': The expected extracted Oda program, or None if no valid program can be extracted.
"""

CASES = [
    # ----------------------------------------------------------------------------------
    # Category 1: Single fenced blocks (oda or bare)
    # ----------------------------------------------------------------------------------
    {
        "name": "single_oda_fence_clean",
        "raw": "```oda\nint x = 5\nprint(x)\n```",
        "expected": "int x = 5\nprint(x)",
    },
    {
        "name": "single_oda_fence_case_insensitive",
        "raw": "```ODA\nstay int y = 10\nprint(y)\n```",
        "expected": "stay int y = 10\nprint(y)",
    },
    {
        "name": "single_oda_fence_spaces",
        "raw": "```oda   \nfunc add(int a, int b) {\n    return a + b\n}\n```",
        "expected": "func add(int a, int b) {\n    return a + b\n}",
    },
    {
        "name": "single_bare_fence",
        "raw": "```\nclass Point {\n    int x\n    int y\n    construct(int in_x, int in_y) {\n        x = in_x\n        y = in_y\n    }\n}\n```",
        "expected": "class Point {\n    int x\n    int y\n    construct(int in_x, int in_y) {\n        x = in_x\n        y = in_y\n    }\n}",
    },
    {
        "name": "single_oda_fence_trailing_whitespace",
        "raw": "```oda\nstay float pi = 3.14159\n```\n   \n\n",
        "expected": "stay float pi = 3.14159",
    },
    {
        "name": "single_oda_fence_no_newline_at_end",
        "raw": "```oda\nprint(\"no newline\")```",
        "expected": "print(\"no newline\")",
    },

    # ----------------------------------------------------------------------------------
    # Category 2: Prose before / after / both around one fence
    # ----------------------------------------------------------------------------------
    {
        "name": "prose_before_oda_fence",
        "raw": "Here is the corrected program that fixes the type mismatch error:\n\n```oda\nint score = 100\nprint(score)\n```",
        "expected": "int score = 100\nprint(score)",
    },
    {
        "name": "prose_after_oda_fence",
        "raw": "```oda\nstay string name = \"Oda\"\nprint(name)\n```\n\nNote that I changed the declaration to use the stay keyword to make the variable immutable.",
        "expected": "stay string name = \"Oda\"\nprint(name)",
    },
    {
        "name": "prose_both_around_oda_fence",
        "raw": "I have updated the code to resolve the compilation issue.\n\n```oda\nfunc calculate(int factor) {\n    stay int base = 50\n    print(base * factor)\n}\n```\n\nPlease verify if this meets the requirements.",
        "expected": "func calculate(int factor) {\n    stay int base = 50\n    print(base * factor)\n}",
    },
    {
        "name": "turkish_prose_before_oda_fence",
        "raw": "Hata giderildi, güncellenmiş kod aşağıdadır:\n\n```oda\nguard int? age = get_age() else {\n    when (IoError) {\n        print(\"Hata oluştu\")\n    }\n}\n```",
        "expected": "guard int? age = get_age() else {\n    when (IoError) {\n        print(\"Hata oluştu\")\n    }\n}",
    },
    {
        "name": "turkish_prose_after_oda_fence",
        "raw": "```oda\nclass Logger {\n    func log(string msg) {\n        print(msg)\n    }\n}\n```\n\nBu sınıf artık loglama işlemlerini düzgün bir şekilde gerçekleştirecektir.",
        "expected": "class Logger {\n    func log(string msg) {\n        print(msg)\n    }\n}",
    },
    {
        "name": "mixed_prose_around_oda_fence",
        "raw": "Gözlemlerime göre, stay ile tanımlanmış bir değişkene tekrar atama yapılmaya çalışılmış. Here is the corrected version:\n\n```oda\nint count = 1\ncount = count + 1\nprint(count)\n```\n\nSorunsuz çalışması gerekir. Let me know if you run into any other compile errors.",
        "expected": "int count = 1\ncount = count + 1\nprint(count)",
    },

    # ----------------------------------------------------------------------------------
    # Category 3: Multiple fenced blocks (expected = the LARGEST)
    # ----------------------------------------------------------------------------------
    {
        "name": "multiple_oda_fences_first_largest",
        "raw": "The main logic is implemented here:\n\n```oda\nfunc run_computation() {\n    stay int threshold = 42\n    int val = 0\n    guard int? input_val = read_sensor() else {\n        when (IoError) {\n            val = -1\n        }\n    }\n    if (val >= threshold) {\n        print(\"Success\")\n    }\n}\n```\n\nAnd here is a small helper function we don't need to focus on:\n\n```oda\nfunc help() {\n    print(1)\n}\n```",
        "expected": "func run_computation() {\n    stay int threshold = 42\n    int val = 0\n    guard int? input_val = read_sensor() else {\n        when (IoError) {\n            val = -1\n        }\n    }\n    if (val >= threshold) {\n        print(\"Success\")\n    }\n}",
    },
    {
        "name": "multiple_oda_fences_second_largest",
        "raw": "Here is a tiny stub:\n```oda\nfunc stub() {}\n```\n\nAnd here is the actual correct implementation:\n```oda\nclass Connection {\n    int _socket_id\n    construct(int id) {\n        _socket_id = id\n    }\n    func send_data(string payload) {\n        print(payload)\n    }\n    destruct() {\n        print(\"closed\")\n    }\n}\n```",
        "expected": "class Connection {\n    int _socket_id\n    construct(int id) {\n        _socket_id = id\n    }\n    func send_data(string payload) {\n        print(payload)\n    }\n    destruct() {\n        print(\"closed\")\n    }\n}",
    },
    {
        "name": "multiple_mixed_fences_largest_oda",
        "raw": "First, let's show the C header generated from Oda:\n```\nvoid run_computation(int x);\n```\n\nAnd the Oda source code:\n```oda\nfunc run_computation(int x) {\n    stay int scale = 2\n    print(x * scale)\n}\n```",
        "expected": "func run_computation(int x) {\n    stay int scale = 2\n    print(x * scale)\n}",
    },
    {
        "name": "multiple_mixed_fences_largest_bare",
        "raw": "Here is the Oda compiler output:\n```oda\nprint(42)\n```\n\nBut the actual fix requires this full file implementation:\n```\nclass Database {\n    string _host\n    int _port\n    construct(string host, int port) {\n        _host = host\n        _port = port\n    }\n    func connect() {\n        print(\"Connected\")\n    }\n    destruct() {\n        print(\"Disconnected\")\n    }\n}\n```",
        "expected": "class Database {\n    string _host\n    int _port\n    construct(string host, int port) {\n        _host = host\n        _port = port\n    }\n    func connect() {\n        print(\"Connected\")\n    }\n    destruct() {\n        print(\"Disconnected\")\n    }\n}",
    },
    {
        "name": "multiple_fences_all_bare_largest",
        "raw": "```\nint short_code = 1\n```\n\n```\nfunc long_code() {\n    stay int multiplier = 10\n    int val = 5\n    print(val * multiplier)\n}\n```",
        "expected": "func long_code() {\n    stay int multiplier = 10\n    int val = 5\n    print(val * multiplier)\n}",
    },

    # ----------------------------------------------------------------------------------
    # Category 4: No fence but code-looking content
    # ----------------------------------------------------------------------------------
    {
        "name": "no_fence_starts_with_func",
        "raw": "func process_sensor_data() {\n    stay int sensor_id = 99\n    guard int? reading = read_sensor() else {\n        when (IoError) {\n            print(\"failed\")\n        }\n    }\n    print(reading)\n}",
        "expected": "func process_sensor_data() {\n    stay int sensor_id = 99\n    guard int? reading = read_sensor() else {\n        when (IoError) {\n            print(\"failed\")\n        }\n    }\n    print(reading)\n}",
    },
    {
        "name": "no_fence_starts_with_stay",
        "raw": "stay int default_port = 8080\nstay string default_host = \"localhost\"\nprint(default_host)",
        "expected": "stay int default_port = 8080\nstay string default_host = \"localhost\"\nprint(default_host)",
    },
    {
        "name": "no_fence_starts_with_class",
        "raw": "class Rectangle {\n    int width\n    int height\n    construct(int w, int h) {\n        width = w\n        height = h\n    }\n}",
        "expected": "class Rectangle {\n    int width\n    int height\n    construct(int w, int h) {\n        width = w\n        height = h\n    }\n}",
    },
    {
        "name": "no_fence_starts_with_guard",
        "raw": "guard string? value = get_env(\"PORT\") else {\n    when (EnvError) {\n        print(\"not set\")\n    }\n}\nprint(value)",
        "expected": "guard string? value = get_env(\"PORT\") else {\n    when (EnvError) {\n        print(\"not set\")\n    }\n}\nprint(value)",
    },
    {
        "name": "no_fence_starts_with_import",
        "raw": "import hw.gpio\n\nfunc init_hardware() {\n    gpio.set_pin(1, 1)\n}",
        "expected": "import hw.gpio\n\nfunc init_hardware() {\n    gpio.set_pin(1, 1)\n}",
    },
    {
        "name": "no_fence_starts_with_construct",
        "raw": "construct(int start_val) {\n    _value = start_val\n}\ndestruct() {\n    print(\"clean\")\n}",
        "expected": "construct(int start_val) {\n    _value = start_val\n}\ndestruct() {\n    print(\"clean\")\n}",
    },
    {
        "name": "no_fence_embedded_in_prose",
        "raw": "Here is the code you need to compile:\nfunc main() {\n    stay int flag = 1\n    print(flag)\n}\nHope it helps!",
        "expected": "func main() {\n    stay int flag = 1\n    print(flag)\n}",
    },

    # ----------------------------------------------------------------------------------
    # Category 5: Truncated/unterminated fence (runaway cutoff mid-block)
    # ----------------------------------------------------------------------------------
    {
        "name": "truncated_fence_mid_function",
        "raw": "```oda\nfunc incomplete_flow() {\n    stay int size = 1024\n    guard int? chunk = read_chunk(size) else {\n        when (IoError) {\n            print(\"failed to read\")",
        "expected": "func incomplete_flow() {\n    stay int size = 1024\n    guard int? chunk = read_chunk(size) else {\n        when (IoError) {\n            print(\"failed to read\")",
    },
    {
        "name": "truncated_fence_mid_stay",
        "raw": "```oda\nstay int default_retries =",
        "expected": "stay int default_retries =",
    },
    {
        "name": "truncated_fence_mid_class_definition",
        "raw": "```oda\nclass NetworkService {\n    string endpoint\n    construct(string url) {\n        endpoint = url\n    }\n    func start() {\n        print(\"starting...\")\n    }\n    des",
        "expected": "class NetworkService {\n    string endpoint\n    construct(string url) {\n        endpoint = url\n    }\n    func start() {\n        print(\"starting...\")\n    }\n    des",
    },
    {
        "name": "unterminated_fence_followed_by_cut_off_prose",
        "raw": "```oda\nfunc hello() {\n    print(\"hello\")\n}\n\nI hope that fixes the build errors you were seeing with the main f",
        "expected": "func hello() {\n    print(\"hello\")\n}\n\nI hope that fixes the build errors you were seeing with the main f",
    },

    # ----------------------------------------------------------------------------------
    # Category 6: Leading / trailing chatter variations
    # ----------------------------------------------------------------------------------
    {
        "name": "leading_chatter_simple",
        "raw": "Here is the fix:\n\n```oda\nstay int max_limit = 100\nprint(max_limit)\n```",
        "expected": "stay int max_limit = 100\nprint(max_limit)",
    },
    {
        "name": "trailing_chatter_simple",
        "raw": "```oda\nfunc print_version() {\n    print(\"v1.0.0\")\n}\n```\n\nLet me know if this compiles correctly on your system.",
        "expected": "func print_version() {\n    print(\"v1.0.0\")\n}",
    },
    {
        "name": "conversational_chatter_english",
        "raw": "I have analyzed the compiler error. The problem was that you reassigned a stay variable which is illegal under Oda's safety rules. Here is the corrected implementation:\n\n```oda\nint dynamic_val = 10\ndynamic_val = 20\nprint(dynamic_val)\n```\n\nPlease let me know if you run into any other compilation issues.",
        "expected": "int dynamic_val = 10\ndynamic_val = 20\nprint(dynamic_val)",
    },
    {
        "name": "conversational_chatter_turkish",
        "raw": "Oda programlama dilindeki derleme hatası stay değişkenine geçersiz atama yapılmasından kaynaklanıyordu. Kodu şu şekilde güncelledim:\n\n```oda\nstay int sabit = 5\nprint(sabit)\n```\n\nHerhangi bir sorun olursa lütfen bana bildirin, iyi çalışmalar.",
        "expected": "stay int sabit = 5\nprint(sabit)",
    },
    {
        "name": "mixed_chatter_english_turkish_1",
        "raw": "Hata düzeltildi. Here is the fix for the scope issue:\n\n```oda\nclass Counter {\n    int _val\n    construct(int initial) {\n        _val = initial\n    }\n}\n```\n\nUmarım işinize yarar. Let me know if you need more changes.",
        "expected": "class Counter {\n    int _val\n    construct(int initial) {\n        _val = initial\n    }\n}",
    },
    {
        "name": "mixed_chatter_english_turkish_2",
        "raw": "Merhabalar, I solved the issue by removing the inline C code block as per the architecture rules of Oda. İşte yeni kodumuz:\n\n```oda\nimport hw.gpio\nfunc blink() {\n    gpio.set_pin(1, 1)\n}\n```\n\nIf you have other error messages, lütfen bizimle paylaşın.",
        "expected": "import hw.gpio\nfunc blink() {\n    gpio.set_pin(1, 1)\n}",
    },

    # ----------------------------------------------------------------------------------
    # Category 7: Prose-only, empty, whitespace (expected = None)
    # ----------------------------------------------------------------------------------
    {
        "name": "prose_only_no_code",
        "raw": "The error occurs because you are trying to mutate a private member of the Wallet class. In Oda, members starting with an underscore (like _balance) are strictly private. You should use a public getter or setter instead.",
        "expected": None,
    },
    {
        "name": "prose_only_turkish",
        "raw": "Değişken isminin önündeki alt çizgi (_) onun özel (private) olduğunu belirtir. Bu nedenle sınıf dışından erişemezsiniz.",
        "expected": None,
    },
    {
        "name": "empty_string",
        "raw": "",
        "expected": None,
    },
    {
        "name": "whitespace_only",
        "raw": "   \n  \t \n",
        "expected": None,
    },
    {
        "name": "punctuation_only",
        "raw": "???!!!...",
        "expected": None,
    },
    {
        "name": "markdown_headers_only",
        "raw": "# Fix proposal\n## Explanation\nNo code blocks were generated.",
        "expected": None,
    },
]
