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
| 🔄 **Döngü Esnekliği** | Artan/Azalan aralıklar, `step` adımı, `reversed` ve dizi iterasyonu |
| 📏 **Aralık Operatörleri** | `..` (exclusive) ve `..=` (inclusive) desteği |
| 🏗️ **OOP** | Class → C struct + name-mangled fonksiyonlar |
| 🔗 **ref Passing** | Güvenli pass-by-reference mekanizması |
| 🎯 **Widening-Only Coercion** | `int→float ✅` / `uint→int ❌` |
| 💬 **Yorum Desteği** | `//` tek satır ve `//* ... *//` çok satırlı yorumlar |
| 📝 **String Interpolation** | `"Hello {name}!"` |
| 🛑 **Strict Checking** | Semantik hatalar artık derlemeyi tamamen durdurur |

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

```oda
// Oda Language Basics
int speed = 100
stay float gravity = 9.81

//*
Çok satırlı
blok yorum desteği
*//

string name = "OdaLang"
print("Hello from OdaLanguage!")

// Range-based for loops
for (int i in 0..10 step 2) {
    print(i) // 0 to 10 (exclusive), increase by 2
}

for (int i in 6..0 step 2) {
    print(i) // 6 to 0, decrease by 1
}

for (int i in 0..=5) {
    print(i) // 0 to 5 (inclusive), increase by 1
}

// Array iteration
int[] numbers = [10, 20, 30]
for (int n in numbers) {
    print(n)
}

// Null safety
string? alias = null
print(alias ?? "No Alias")
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
