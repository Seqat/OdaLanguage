# OdaLanguage 🏠

> **"The safest room for code."**

OdaLanguage, modern, yarı-statik tipli, yüksek okunabilirliğe sahip bir programlama dilidir.
Özel bir transpiler aracılığıyla doğrudan optimize edilmiş **C koduna** derlenir.

## ✨ Özellikler

| Özellik | Açıklama |
|---|---|
| 🔄 **C'ye Transpilasyon** | `.oda` → AST → Unity Build C → Native Binary |
| 🛡️ **Null Safety** | Non-nullable by default, `?` ile nullable, `??` ile safe unwrap |
| 🔒 **Immutability** | `stay` ile değiştirilemez değişkenler |
| 🏗️ **RAII** | `destruct()` otomatik scope-end çağrısı |
| 📦 **OOP** | Class → C struct + name-mangled fonksiyonlar |
| 🔗 **ref Passing** | Güvenli pass-by-reference mekanizması |
| 🎯 **Widening-Only Coercion** | `int→float ✅` / `uint→int ❌` |
| 📝 **String Interpolation** | `"Hello {name}!"` |

## 🚀 Hızlı Başlangıç

```bash
# Sadece C'ye dönüştür
python3 -m oda.main transpile examples/hello.oda

# Derle
python3 -m oda.main build examples/hello.oda

# Derle ve çalıştır
python3 -m oda.main run examples/hello.oda
```

## 📝 Örnek — hello.oda

```
int speed = 100
stay float gravity = 9.81

string name = "OdaLang"
print("Hello from OdaLanguage!")

string? alias = null
string fallback = alias ?? "Unknown"
print(fallback)

if (speed > 50) {
    print("Fast!")
}

for (int i in 0..5) {
    print("Counting...")
}
```

## 📝 Örnek — engine.oda (Class & RAII)

```
class Engine {
    int _rpm
    string _port

    construct(string port) {
        _port = port
        _rpm = 0
        print("Connected to " + _port)
    }

    func rev_up() {
        _rpm = _rpm + 1000
    }

    destruct() {
        print("Closing port: " + _port)
    }
}

Engine v8 = Engine("COM3")
v8.rev_up()
// → destruct() otomatik çağrılır!
```

## 📂 Proje Yapısı

```
OdaLanguage/
├── oda/                    # Transpiler kaynak kodu
│   ├── tokens.py           # Token tanımları
│   ├── lexer.py            # Tokenizer
│   ├── parser.py           # Recursive descent parser
│   ├── ast_nodes.py        # AST düğüm sınıfları
│   ├── semantic.py         # Semantic analiz
│   ├── codegen.py          # C kod üretici
│   └── main.py             # CLI
├── examples/               # Örnek .oda programları
├── output/                 # Üretilen C çıktıları
└── OdaLanguage .pdf        # Dil spesifikasyonu
```

## 🛠️ Gereksinimler

- Python 3.10+
- GCC veya Clang (derleme ve çalıştırma için)

## 📄 Lisans

Bu proje aktif geliştirme aşamasındadır.
