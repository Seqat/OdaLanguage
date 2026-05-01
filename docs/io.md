# Girdi / Çıktı (Input / Output)

OdaLanguage, temel I/O (Girdi/Çıktı) işlemleri için standart kütüphane fonksiyonları sunar.

## Ekrana Yazdırma
Standart konsola çıktı vermek için `print()` fonksiyonu kullanılır.

```oda
print("Merhaba Dünya!")
int yas = 25
print("Yaş: " + yas)
```

## Kullanıcıdan Girdi Alma
Kullanıcıdan konsol üzerinden metin girişi almak için `input()` fonksiyonu kullanılır.

```oda
print("Lütfen adınızı giriniz:")
string isim = input()
print("Merhaba, " + isim + "!")
```

## Dosya Okuma
Metin tabanlı dosyaların içeriğini okumak için `readFile()` fonksiyonu kullanılır. Bu fonksiyon başarılı olduğunda dosya içeriğini `string` olarak, başarısız olduğunda ise `null` döndürür (Null safety).

```oda
string? icerik = readFile("config.txt")

if (icerik != null) {
    print("Dosya başarıyla okundu.")
    print(icerik)
} else {
    print("Dosya bulunamadı veya okunamadı.")
}
```
