# Kontrol Akışı (Control Flow)

OdaLanguage, programın akışını kontrol etmek için if-else koşulları ve esnek for döngüleri sunar.

## Koşullu İfadeler (If - Else)
Klasik C tarzı if-else blokları desteklenmektedir.

```oda
int score = 85

if (score >= 90) {
    print("A")
} else if (score >= 80) {
    print("B")
} else {
    print("C")
}
```

## Döngüler (Loops)

### Aralık Tabanlı Döngüler (Range-based Loops)
OdaLanguage, aralık tabanlı iterasyonları çok güçlü bir şekilde destekler. `..` (hariç) ve `..=` (dahil) operatörleri ile aralık belirleyebilirsiniz.

```oda
// 0'dan 10'a kadar (10 HARİÇ)
for (int i in 0..10) {
    print(i) // 0, 1, 2, ..., 9
}

// 0'dan 5'e kadar (5 DAHİL)
for (int i in 0..=5) {
    print(i) // 0, 1, 2, 3, 4, 5
}
```

### Adım (Step) ve Geriye Doğru (Reversed) İterasyon
Döngülerde `step` kelimesiyle artış veya azalış miktarını belirleyebilirsiniz. Büyük sayıdan küçük sayıya doğru giderken döngü otomatik olarak geriye sayar.

```oda
// 2'şer artış
for (int i in 0..10 step 2) {
    print(i) // 0, 2, 4, 6, 8
}

// Geriye doğru sayım (Azalan döngü)
for (int i in 10..0 step 2) {
    print(i) // 10, 8, 6, 4, 2
}
```

### Dizi (Array) İterasyonu
Döngüler doğrudan diziler üzerinde dolaşmak için de kullanılabilir.

```oda
int[] numbers = [10, 20, 30]
for (int n in numbers) {
    print(n) // Sırayla 10, 20, 30 yazdırır
}
```
