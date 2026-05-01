# Diziler (Arrays)

OdaLanguage, statik, dinamik ve çok boyutlu dizileri destekler. Diziler hem tanımlama anında boyutlandırılabilir hem de bellekte dinamik olarak yer kaplayabilir.

## Statik Diziler
Boyutu önceden belirlenmiş sabit dizilerdir.

```oda
int[3] numbers = [1, 2, 3]
print(numbers[0]) // 1
numbers[1] = 50
```

## Dinamik Diziler
Boyutu derleme aşamasında belirtilmek zorunda olmayan dizilerdir.

```oda
int[] dynamic_arr = [4, 5, 6, 7, 8]
print(dynamic_arr[4]) // 8
```

## Çok Boyutlu Diziler (Multidimensional Arrays)
İç içe geçmiş dizilerle çok boyutlu matrisler oluşturabilirsiniz. Dizi indeksleri `[satır][sütun]` mantığıyla okunur.

```oda
int[][] num = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

// İlk satırın ilk elemanını okuma
int first = num[0][0] // 1

// İkinci satırın üçüncü elemanını okuma
int val = num[1][2] // 6
```

Diziler üzerinde iterasyon yapmak için döngüleri kullanabilirsiniz. (Bkz: Control Flow)
