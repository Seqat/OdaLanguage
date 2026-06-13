# Tipler ve Değişkenler (Types & Variables)

OdaLanguage, tip güvenliğini (type safety) ve bellek yönetimini ön planda tutan bir dildir. Değişken tanımlamaları her zaman tiplerle birlikte yapılır.

## Temel Veri Tipleri (Primitifler)

OdaLanguage'deki temel veri tipleri şunlardır:
- `int`: Tam sayılar (Örn: `10`, `-5`)
- `float`: Ondalıklı sayılar (Örn: `3.14`)
- `string`: Metin değerleri (Örn: `"Merhaba"`)
- `bool`: Mantıksal değerler (`true` veya `false`)

```oda
int age = 25
float pi = 3.1415
string greeting = "Hello"
bool is_valid = true
```

## Değişmezlik (Immutability) - `stay`
Eğer bir değişkenin değerinin sonradan değiştirilmesini istemiyorsanız `stay` anahtar kelimesini kullanabilirsiniz. Bu, değişkeni bir sabite (constant) çevirir.

```oda
stay float gravity = 9.81
// gravity = 10.0 // Derleme hatası verir!
```

Dil kararı: `stay` dizilerde de tam değişmezlik anlamına gelir. `stay int[] nums = [1, 2, 3]` yazıldığında hem `nums = [4, 5]` hem de `nums[0] = 99` derleme zamanında reddedilir. Oda, C'deki `const int*` ve `int* const` ayrımını kullanıcıya taşımaz; "en az sürpriz" ve "fail-fast" ilkeleri gereği `stay` ile işaretlenen değerin içeriği de değiştirilemez kabul edilir.

## Null Güvenliği (Null Safety)
Varsayılan olarak OdaLanguage'de hiçbir değişken `null` değerini alamaz (Non-nullable by default). Eğer bir değişkenin `null` olabilmesini istiyorsanız, tipinin sonuna `?` işareti koymalısınız.

```oda
string? name = null // Geçerli
// string surname = null // Derleme hatası verir!
// int? count = null   // Hata (E3048): v1'de `?` yalnızca string/class tipleri için
```

v1'de `?` yalnızca string ve class tiplerinde desteklenir; değer tiplerinin (int, float, ...) C'de `null` karşılığı yoktur (E3048). Nullable bir değer `print`/string birleştirme/interpolasyon içinde kullanılmadan önce `??` ya da `guard` ile açılmalıdır (E3049).

### Null Coalescing (`??`)
Nullable bir değişkenin değerini güvenli bir şekilde okumak veya boşsa varsayılan bir değer atamak için `??` operatörünü kullanabilirsiniz.

```oda
string? alias = null
print(alias ?? "Bilinmeyen Kullanıcı") // "Bilinmeyen Kullanıcı" yazdırır
```

## Tip Dönüşümleri (Type Coercion)
OdaLanguage'de sadece güvenli genişletme (Widening) dönüşümlerine izin verilir. Veri kaybı riski taşıyan dönüşümler derleme zamanında engellenir.

- `int` → `float` : **GEÇERLİ**
- `float` → `int` : **GEÇERSİZ** (Açıkça (explicitly) dönüştürme gerektirir)

## Referans Geçişi (ref Passing)
Fonksiyonlara değişkenleri kopyalamak yerine referanslarıyla gönderebilirsiniz. Böylece değişkenin orijinal değeri üzerinde değişiklik yapılabilir.

```oda
func increment(ref int val) {
    val = val + 1
}

int count = 0
increment(ref count)
print(count) // 1
```
