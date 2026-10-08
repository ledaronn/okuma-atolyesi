## İndir

**1.1.1 yenilikleri / What's new:**

- İsteğe bağlı günlük güncelleme bildirimi; indirme ve kurulum elle yapılır.
- MCP araç açıklamaları İngilizce; mevcut araç ve parametre adları korunur.
- Sabitlenen araç şeridindeki animasyon hatası düzeltildi.
- Pevrai bağlantısı ve belge yolları güncellendi. Kaynak testleri yayın kapısıdır;
  paket sürümü, PDF çizimi, MCP yanıtı ve pencere ayrı geçici verilerle doğrulanır.

*Optional daily update notification, English MCP descriptions, pinned ribbon animation
fix and updated Pevrai integration. Releases require passing source tests and isolated
checks of the packaged version, PDF rendering, MCP response and reader window.*

**OkumaAtolyesi-Setup.exe**: Windows 10/11, 64 bit. Python ya da yönetici izni gerekmez.

1. Aşağıdaki **Assets** bölümünden `OkumaAtolyesi-Setup-<sürüm>.exe` dosyasını indirip çalıştır.
2. Windows *"Bilgisayarınız korundu"* uyarısı verebilir: kurulum programı henüz imzalı değil.
   **Ek bilgi → Yine de çalıştır**'a tıkla. Dosyayı `SHA256SUMS.txt` ile doğrulayabilirsin.
3. `PDF ekle` ile bir PDF seç ya da pencereye bırak. Word belgesi için **Araçlar ▾ → Yeni belge**.
   PDF ve Word dosyalarını çift tıklayınca açmak için **Araçlar ▾ → Varsayılan uygulama…**

Kitaplığın (PDF kopyaları, notlar) `%USERPROFILE%\OkumaAtolyesiVeri` klasöründe durur, program
klasöründe değil. Kaldırma kitaplığa dokunmaz. İsteğe bağlı: tam Word özellikleri için
[LibreOffice](https://www.libreoffice.org/).

---

**English:** download `OkumaAtolyesi-Setup-<version>.exe` from **Assets** and run it; no Python or
admin rights needed. If Windows shows "Windows protected your PC", click **More info → Run anyway**
(the installer is not code-signed yet). The interface is in English and Turkish (Tools ▾ → Dil / Language).
