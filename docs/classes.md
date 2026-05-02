# Sınıflar ve Nesne Yönelimli Programlama (Classes & OOP)

OdaLanguage, Nesne Yönelimli Programlamayı destekler. C koduna dönüştürüldüğünde, sınıflar C struct'larına ve sınıflara ait metodlar name-mangled (isim dönüştürülmüş) C fonksiyonlarına çevrilir.

## Sınıf Tanımlama
`class` anahtar kelimesi ile yeni bir sınıf oluşturulur. Sınıf içerisinde değişkenler ve fonksiyonlar (`func`) tanımlanabilir. 

### Kapsülleme (Encapsulation)
OdaLanguage'de isminin başında alt çizgi `_` olan değişkenler ve metodlar **kesinlikle özeldir (private)**. Semantik Analizör, bu üyelere sınıf dışından erişilmeye çalışıldığında derleme zamanı hatası verir.

```oda
class SecretBox {
    int _secretValue // Private
    string name      // Public

    construct(int val, string n) {
        _secretValue = val
        name = n
    }
}

SecretBox box = SecretBox(42, "MyBox")
print(box.name)    // ✅ Geçerli
// print(box._secretValue) // ❌ HATA: Private member erişimi!
```

```oda
class Engine {
    int _rpm
    string _port

    // Kurucu metod (Constructor)
    construct(string port) {
        _port = port
        _rpm = 0
        print("Motor bağlandı: " + _port)
    }

    // Sınıf metodu
    func rev_up() {
        _rpm = _rpm + 1000
    }

    // Yıkıcı metod (Destructor) - RAII desteği
    destruct() {
        print("Motor kapatılıyor: " + _port)
    }
}
```

## Nesne Oluşturma ve Metod Kullanımı
Yeni bir nesne oluşturmak için sadece sınıf adını ve argümanlarını çağırmak yeterlidir (`new` kelimesi kullanılmaz).

```oda
Engine v8 = Engine("COM3")
v8.rev_up()
```

## RAII (Resource Acquisition Is Initialization)
OdaLanguage, RAII bellek ve kaynak yönetim modelini kullanır. Bir sınıf nesnesi tanımlandığında, o nesnenin yaşam döngüsü (scope) sona erdiğinde (örneğin bir fonksiyon veya blok sonlandığında) `destruct()` metodu otomatik olarak çağrılır. Bu sayede açık dosyaları kapatmak veya ağ bağlantılarını kesmek manuel olarak düşünülmesi gereken bir süreç olmaktan çıkar.

```oda
func runEngine() {
    Engine myEngine = Engine("Port1")
    // ... işlemler ...
} // <-- Fonksiyon bittiğinde `myEngine.destruct()` OTOMATİK çalışır.
```
