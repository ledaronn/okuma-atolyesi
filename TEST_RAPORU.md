# Doğrulama raporu

Tarih: 10 Eylül 2026

Son birleşik test sonucu: **14 passed in 8.15s**. Başarısız veya atlanan test yok.

Ortam: Linux, Python 3.12.14, PyMuPDF 1.26.6, Qt/PySide6 Essentials 6.11.2, MCP SDK 1.30.0. Masaüstü etkileşimleri Qt'nin `offscreen` platformunda gerçek widget ve fare olaylarıyla yürütüldü. OCR testi kurulu Tesseract'ın İngilizce dil modeliyle yapıldı.

## Doğrulanan davranışlar

| Alan | Kanıt |
|---|---|
| PDF içe alma | Geçerli PDF kopyalanıyor, SHA-256 ile aynı dosya çoğaltılmıyor. |
| Kaynağın korunması | Not/dışa aktarım sonrası orijinal dosyanın SHA-256 değeri değişmiyor. |
| Arama ve okuma | Sözcük eşleşmeleri doğru belge/sayfaları döndürüyor. |
| Not ve çizim | Kalem, fosfor, alt çizgi, kutu, ok, not ve yer imi kaydediliyor. |
| PDF dışa aktarım | Çizimler ve Türkçe notlar PDF açıklamaları olarak yeniden açılabiliyor. |
| Döndürülmüş sayfa | Ekran/PDF koordinatı dönüşümü sonrası işaretleme doğru metin bölgesiyle örtüşüyor. |
| Geri al/yinele | Not/çizim silme geri alınabiliyor; yeni işlem eski yineleme dalını temizliyor. |
| Kalıcı okuma durumu | Veritabanı yeniden açılınca sayfa, konum, zoom ve seçili metin korunuyor. |
| Sayfa işlemleri | Seçim, sıralama, döndürme ve birleştirme doğru sayfa içeriğini üretiyor. |
| Yedek/arşiv | Yedek veritabanını ve PDF'yi içeriyor; arşivlenen belge geri getirilebiliyor. |
| Hatalı girdiler | Geçersiz kimlik/sayfa/renk/koordinat ve olmayan alıntı reddediliyor. |
| Parola | Hatalı parola kalıntı bırakmıyor; doğru parolayla metin okunuyor. |
| Gerçek OCR | Görüntüden oluşan sayfa OCR öncesi metinsiz; OCR sonrası aranabilir ve seçilebilir. |
| GUI etkileşimi | Qt fare olaylarıyla kalem, fosfor, seçim, pano, silgi ve geri alma çalışıyor. |
| GUI konumu | Yakınlaştırma ve kaydırma sonrasında yeniden açılan okuyucu aynı konuma dönüyor. |
| Arka plan işi | PDF işi ayrı thread'de, sonuç işleme GUI thread'inde gerçekleşiyor. |
| Gerçek MCP | stdio sunucusu başlatılıyor; 17 araç keşfediliyor, belge okunuyor, not ekleniyor, PDF üretiliyor. |
| MCP yol sınırı | İzinli içe aktarma klasörü dışındaki kaynak reddediliyor. |
| MCP hata sonrası | Hatalı çağrı sonrasında aynı bağlantı kullanılabiliyor. |
| Gerçek okuyucu başlatma | MCP yeni GUI sürecini açıyor; ikinci istek mevcut pencereyi 2. sayfaya yönlendiriyor. |

## Görsel kontrol

`onizleme/kutuphane.png` ve `onizleme/okuyucu.png` çalışan uygulamadan alınmıştır. Tasarım görseli veya temsili mockup değildir. Örnek PDF kapak, okuma ve çizim sayfaları; ayrıca işaretlemeli PDF çıktısı görsel olarak incelendi. Başlık satırı, panelde notların kaydırılması ve genişliğe sığdırma düzeni düzeltildi.

## Henüz doğrulanmayanlar

- Kullanıcının Windows bilgisayarında kurulum ve masaüstü çalıştırma.
- Gerçek Limina MCP köprüsüyle birlikte çalışma. Bağımsız MCP istemcisiyle test edildi; ana projeye dokunulmadı.
- Fiziksel kalem/dokunmatik ekran. Basınç ve avuç içi reddi bu sürümde uygulanmadı.
- Türkçe Tesseract modeli. Türkçe metinli normal PDF ve Türkçe notlar doğrulandı; OCR testi İngilizce modelle yapıldı.
- Çok büyük belgeler ve binlerce dosyalı koleksiyonlar için yük testi.

## Yeniden çalıştırma

Paketin kendi sanal ortamında pytest kurulduktan sonra:

```sh
python -m pytest tests -q
```

Test PDF'leri ve veritabanları pytest'in geçici klasörlerinde oluşturulur. Kullanıcının gerçek kütüphanesine veya ana AI projesine dokunulmaz. OCR bağımlılığı yoksa yalnızca OCR testi atlanır.
