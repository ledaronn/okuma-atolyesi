# Aşama 1–2 raporu: akıcılık teşhisi ve araç envanteri

Tarih: 14 Eylül 2026. Kod değiştirilmedi. Ölçüm scriptleri ve ham çıktılar `docs/olcum/` klasöründe.

Makine: Intel i5-8250U (4 çekirdek, 1,6 GHz), 8 GB RAM, Intel UHD 620. Python 3.13, PyMuPDF 1.26.6, PySide6 6.11.2.
Qt `offscreen` platformunda gerçek `Window` ve gerçek fare/tekerlek olaylarıyla ölçüldü. Sınırları §1.6'da.

**Commit hash'i yok.** Paket Pevrai deposunun `.gitignore`'unda (`Araclar/`), kendi git deposu da yok.
Aşama 3'ten önce paket içinde `git init` yapılması gerekir; yoksa geri dönüş noktası olmaz. Bu kararı sana bırakıyorum.

---

## 1. Aşama 1 — Akıcılık teşhisi

### 1.1 Varsayım doğrulandı

> "Sayfa görüntüsü ekranda lazım olduğu anda üretiliyor ve bu iş arayüzle aynı iş parçacığında bekliyor."

**Doğru.** `Reader.render_visible` ([app.py:162](../app.py#L162)) bir `QTimer` ile UI iş parçacığında çağrılıyor; içindeki `lib.render()` her sayfa için PDF'i diskten açıp rasterize ediyor, PNG'ye kodluyor, `QPixmap.loadFromData` ile çözüyor — hepsi eşzamanlı. Görünen sayfa sayısı × sayfa başı süre kadar arayüz donuyor.

Ek olarak: kaydırma sırasında **hiç üretim yapılmıyor**. `on_scroll` her kaydırma olayında 50 ms'lik zamanlayıcıyı sıfırlıyor ([app.py:157](../app.py#L157)); hızlı kaydırmada zamanlayıcı hiç dolmuyor. Kullanıcı beyaz dikdörtgenler görüyor, durunca tek seferde 340–600 ms donuyor.

### 1.2 Sayfa başına üretim maliyeti (çekirdek, ms, medyan, 12 sayfa)

Zoom 1,0 (ölçek 1,4):

| Belge | Piksel | SQLite (4 bağlantı) | fitz.open + sayfa | **get_pixmap** | PNG kodla | PNG çöz | **Toplam** |
|---|---|---|---|---|---|---|---|
| Kitap (sentetik, 515 kelime/s) | 833×1179 | 24 | 7 | **16** | 59 | 15 | **123** |
| Slayt (sentetik, 36 kelime/s) | 1344×756 | 43 | 10 | **15** | 43 | 16 | **127** |
| Slayt gerçek, metin (ders PDF'i) | 1344×756 | 43 | 7 | **36** | 52 | 16 | **151** |
| Slayt gerçek, görüntü (4 MB/15 s) | 1179×834 | 31 | 3 | **113** | 102 | 18 | **267** |

Zoom 2,0 (ölçek 2,8):

| Belge | Piksel | SQLite | fitz.open + sayfa | get_pixmap | PNG kodla | PNG çöz | **Toplam** |
|---|---|---|---|---|---|---|---|
| Kitap | 1666×2358 | 35 | 9 | 30 | 207 | 61 | **337** |
| Slayt sentetik | 2688×1512 | 47 | 10 | 24 | 192 | 63 | **337** |
| Slayt gerçek metin | 2688×1512 | 40 | 4 | 68 | 159 | 54 | **328** |
| Slayt gerçek görüntü | 2358×1667 | 30 | 3 | 163 | 300 | 67 | **564** |

Okuma:

- MuPDF'in asıl işi (`get_pixmap`) toplamın yalnızca **%12–42'si**. Metin tabanlı sayfada 15–36 ms.
- **PNG kodla + çöz toplamın %45–62'si.** `pix.tobytes('png')` → `QPixmap.loadFromData` gereksiz bir ara biçim; `pix.samples` doğrudan `QImage` olabilir.
- **SQLite %11–34.** `render()` her çağrıda 4 kez bağlantı açıp kapatıyor (`check_page`, `path()`, `annotations` içinde `document()`); her açma-kapama bu makinede **9 ms** (bağlantı 0,4 ms, sorgu 0,06 ms; maliyet `with db` çıkışı + WAL kapanışında). Sayfa başına 24–47 ms boşa gidiyor.
- Slayt ile kitap arasında fark az: slayt daha büyük piksel alanı (16:9, genişliğe göre) ürettiği için seyrek metin avantajını PNG'de kaybediyor.
- Gerçek görüntü tabanlı slayt en kötü durum: 267 ms/sayfa (zoom 1), 564 ms (zoom 2).

### 1.3 Arayüz ölçümleri (1450×950 pencere, görünen alan 755 px)

"Tıkanma" = tek bir `processEvents()` turunun 16 ms'i aşması; süresi = kaçan kare sayısı × 16 ms.

| Senaryo | Kitap 200 s | Slayt 120 s | Gerçek metin slayt | Gerçek görüntü slayt |
|---|---|---|---|---|
| **Açılış** (open_doc + ilk üretim) | 713 ms, 2 sayfa | 779 ms, 3 sayfa | 841 ms, 3 sayfa | 1032 ms, 2 sayfa |
| **Hızlı kaydırma** (120 tık, 8 ms ara) — *sırasında* | 0 üretim; boyama 120 kez / 18 ms | 0 üretim; 25 ms | 1 üretim, **515 ms donma** (belge sonu) | 1 üretim, **607 ms donma** |
| Hızlı kaydırma — *durunca* | **1 blok: 336 ms** (3 sayfa) | **1 blok: 509 ms** (4 sayfa) | — | — |
| **Yavaş kaydırma** (40 tık, 60 ms ara; okuma hızı) | 6 sayfa; **7 tıkanma, toplam 718 ms, en uzun 132** | 7 sayfa; **7 tıkanma, 895 ms, en uzun 216** | 0 (belge sonu) | 0 |
| Yavaş kaydırma, genişliğe sığdırılmış | 5 sayfa; 6 tıkanma, 842 ms, en uzun 213 | 12 sayfa; **14 tıkanma, 1182 ms**, en uzun 169 | — | — |
| **Genişliğe sığdır** | 3 sayfa; **402 ms** | 5 sayfa; **484 ms** | 3 sayfa; 376 ms | 3 sayfa; **615 ms** |
| **Ctrl+tekerlek 1 adım** | 3 sayfa sıfırdan; **398 ms** | 5 sayfa; **413 ms** | 4 sayfa; 282 ms | 3 sayfa; **514 ms** |
| **Sayfa atlama** (→ orta) | 3 sayfa; **589 ms** | 5 sayfa; 402 ms | 5 sayfa; 351 ms | 4 sayfa; **712 ms** |
| **Tek işaretleme sonrası** (`clear_renders`) | 3 sayfa; **638 ms** | 5 sayfa; **539 ms** | 5 sayfa; 587 ms | 4 sayfa; **805 ms** |
| Boyama (`paintEvent`) medyan | 0,2 ms | 0,2 ms | 0,1 ms | 0,1 ms |

### 1.4 §2.1'deki beş sorunun cevabı

1. **Kaydırmada kare süresi; 16 ms'i aşan işlem?** Boyama 0,1–0,3 ms — kaydırmanın kendisi akıcı. 16 ms'i aşan tek şey `render_visible` → `lib.render`: sayfa başına 90–250 ms (zoom 1), 330–560 ms (zoom 2), görünür sayfa sayısıyla çarpılıyor. Okuma hızında kaydırırken her 1–2 tıkta bir 100–216 ms donma.
2. **Bir sayfa kaç ms?** Kitap 123, slayt 127–151, görüntü slaytı 267 (zoom 1). Zoom 2'de 2,5–3 katı. Yoğunluk farkı beklenenden az; belirleyici olan piksel alanı ve PNG.
3. **Yakınlaştırmada tüm sayfa yeniden mi?** Evet. `set_zoom` → `clear_renders` → görünür her sayfa sıfırdan ([app.py:142](../app.py#L142)). Ara ölçekleme, eski pixmap'i büyütüp gösterme yok. Her adım 280–514 ms.
4. **Önceki/sonraki sayfa önceden mi?** Kısmen: görünen alan ±500 sahne birimi ([app.py:164](../app.py#L164)); zoom 1'de ≈ ±0,6 kitap sayfası, ≈ ±1 slayt. Ama eşzamanlı olduğundan prefetch tıkanmayı **artırıyor**, azaltmıyor.
5. **UI iş parçacığı ne kadar bloke?** Tek blok 132–805 ms. Okuma hızında kaydırmada saniyede ~0,7–1,2 s toplam tıkanma (yavaş kaydırma satırı). Yani okurken her saniyenin yarısından fazlası donuk.

### 1.5 "Animasyon yok, 10 fps hissi" — üç bileşen

1. **Sıçramalı kaydırma:** tekerlek tıkı = 111 sahne birimi (3 satır × 37), anında, animasyonsuz. `QGraphicsView` varsayılanı; yumuşatma kodu yok.
2. **Kaydırırken beyaz sayfa:** zamanlayıcı sıfırlandığı için hareket sürerken üretim yok.
3. **Her duraklamada donma:** yeni sayfa görünür alana girince 100–800 ms.

Boyama hızıyla ilgisi yok; GPU/Qt değil, üretim hattı.

### 1.6 Ölçümün sınırları

- `offscreen` platform: boyama gerçek ekranda (özellikle HiDPI) daha pahalı olabilir; ama 0,2 ms'den 100 ms'e çıkması beklenmez. Üretim süreleri platformdan bağımsız.
- Sentetik kitap gerçek kitaptan hafif (gömülü font ve görsel yok). Gerçek kitapta `get_pixmap` daha yüksek çıkar; PNG ve SQLite payı aynı kalır. Gerçek bir ders kitabıyla tekrar ölçülmeli.
- Pil/güç modu bilinmiyor; mutlak sayılar değişir, oranlar değişmez.
- Ölçümde `QTest.qWait` kullanılmadı (GIL'i bırakmıyor, arka plan işini 15× yavaşlatıyor — §3'te).

### 1.7 Düzeltme önerisi (ölçüme dayalı; Aşama 3 tasarımı)

Kazançlar yukarıdaki tablodan hesaplandı, tahmin değil.

| # | Değişiklik | Kanıt | Beklenen kazanç |
|---|---|---|---|
| 1 | Üretimi UI dışına al: işçi iş parçacığı (mevcut `PDF_LOCK` yeterli), sayfa yer tutucu, hazır olunca sinyalle yerleştir | 1.3 tablosu: tüm tıkanma `render_visible` | Tıkanma 0'a iner. Sayfanın görünme gecikmesi aynı kalır (2–4 ile düşer) |
| 2 | PNG'yi kaldır: `pix.samples` → `QImage(Format_RGB888)` → `QPixmap` | 1.2: PNG %45–62 | Sayfa başına −60…−80 ms (zoom 1), −250…−350 ms (zoom 2) |
| 3 | SQLite'ı üretim yolundan çıkar: belge yolu ve işaretlemeleri belge açılışında önbellekle | 1.2: 4 bağlantı × 9 ms | −25…−45 ms/sayfa |
| 4 | `fitz.Document`'ı okuyucu ömrünce açık tut | 1.2: fitz.open + sayfa 3–10 ms | −3…−10 ms/sayfa, artı belge büyüdükçe daha fazla |
| 5 | Yakınlaştırmada eski pixmap'i ölçekleyip göster, arka planda yenisini üret | 1.3: zoom 280–514 ms | Yakınlaştırma anında tepki verir |
| 6 | Kaydırma sırasında da üret (zamanlayıcıyı sıfırlama; kuyruk + iptal), prefetch ±1 ekran | 1.3: kaydırırken 0 üretim | Beyaz sayfa süresi kısalır |
| 7 | İşaretlemeleri sayfa görüntüsüne pişirmek yerine ayrı `QGraphicsItem` katmanı | 1.3: işaretleme sonrası 539–805 ms; kalem çizgisi 371–771 ms kaybolup geliyor | Kalem/fosfor/silgi anında; sayfa yeniden üretilmez |
| 8 | Yumuşak kaydırma (`QScroller` ya da kısa `QVariantAnimation`) | 1.5 | Sıçrama gider; sayısal değil, algısal |
| 9 | `export_pdf`: 200× `check_page` yerine tek sorgu; `garbage=4` → `garbage=1` | §3: 1,46 s + 1,22 s → 0,1 s | Kitap dışa aktarımı 3,3 s → ~0,5 s |

1–4 tek değişiklik kümesi ("üretim hattı"): sayfa başına 123 ms → tahmini ~35 ms **ve** UI dışında. 7 ayrı bir iş; "gerçeklik hissi" sorununun (§2.2) asıl cevabı da bu.

### 1.8 Kabul koşulu

| Koşul | Durum | Kanıt |
|---|---|---|
| Kaydırmada kare süresi ölçülmüş | ✅ | 1.3 tablosu, `docs/olcum/ham_arayuz.txt` |
| Bloke eden işlem tespit edilmiş | ✅ | `render_visible` → `lib.render`; alt kırılım 1.2 |
| Düzeltme önerisi ölçüme dayanıyor | ✅ | 1.7, her satırda kanıt sütunu |

---

## 2. Aşama 2 — Araç ve özellik envanteri

Her araç gerçek Qt fare olaylarıyla, 200 sayfalık yoğun metinli kitapta denendi (`docs/olcum/envanter.py`, ham çıktı `docs/olcum/ham_envanter.txt`).

### 2.1 Envanter tablosu

| Araç | Durum | Bulgu |
|---|---|---|
| Taşı | çalışıyor | 150 px sürükleme = 150 birim. Tekerlek 111 birim/tık, animasyonsuz |
| Metin seç | **kısmen** | Tam satır doğru. Satır 1 ortasından satır 3 ortasına sürüklemede 13 kelimelik satırlardan **4 kelime** geldi: dikdörtgen içindeki **sütun**, okuma akışı değil (`'sistem\ngüvenilirlik\nbulgu sapma'`). Sürüklerken metin vurgusu yok, yarı saydam kutu var |
| Kalem | çalışıyor | Sürüklerken geçici yol anında çiziliyor; **bırakınca siliniyor**, tüm görünür sayfalar yeniden üretilince geri geliyor (371–771 ms görünmez) |
| Fosfor | **kısmen** | Metin üstünde satıra yapışıyor (2 satır → 2 kutu, metin kaydediliyor). Boş kenarda serbest kutu doğru. Sürüklerken önizleme satıra yapışmıyor; bırakınca yeniden üretim gecikmesiyle görünüyor |
| Alt çizgi | çalışıyor | Satır kutusu ve metin doğru. Her üretimde konsola `Cannot set border for 'Underline'` uyarısı ([core.py:337](../core.py#L337)) |
| Kutu | çalışıyor | Koordinatlar doğru |
| Ok | çalışıyor | İki uç nokta doğru |
| Not | çalışıyor | Panelde görünüyor. Metin modal pencereyle giriliyor, sayfada yalnızca ikon |
| Silgi | çalışıyor | Kalem, fosfor, not isabetli; boşa tık silmiyor. **Üzerine gelince ne sileceğini göstermiyor** (hover kodu yok). Her tıkta PDF diskten açılıyor ve görünür sayfalar yeniden üretiliyor |
| Yer imi | çalışıyor | Kaydediliyor; yalnızca Notlar panelinde, sayfada görsel işaret yok |
| PDF kaydet | çalışıyor | 4 işaretleme PDF'e işlendi. Kitapta **3,3 s** boyunca okuyucu devre dışı (1,46 s: 200× `check_page`; 1,22 s: `garbage=4`). Slaytta 0,3 s |
| Sayfalar | çalışıyor | `1-3,7,5` + 90° → 5 sayfa, doğru dönüş. İki ardışık modal pencere |
| *Geri al / yinele* | çalışıyor | Her adımda tüm görünür sayfalar yeniden üretiliyor |
| *Yakınlaştır / sığdır* | çalışıyor | Her adımda sıfırdan üretim |
| *Sayfa kutusu* | çalışıyor | — |
| *Yan panel* | çalışıyor | Varsayılan **açık**; sekmeler Notlar, İçindekiler, Ara, **AI** (plan üç sekme diyor) |

Özet: 12/12 araç işlevsel; 2'si (Metin seç, Fosfor) yoğun metinde kısmen kullanışlı. Kullanıcının "çoğu çalışmıyor" bildirimi araçların **çalışmamasından değil, tepkisizliğinden** geliyor: her işaretleme sonrası 400–800 ms donma + kalem çizgisinin kaybolup gelmesi + silginin geri bildirim vermemesi. Bu, Aşama 3'teki 7 numaralı öneriyle (ayrı işaretleme katmanı) çözülür; araçların mantığına dokunmak gerekmiyor.

### 2.2 Dört sorunun cevabı

**Kaldığın yer kaydediliyor mu (§2.5)?** **Evet, kaydediliyor ve geri yükleniyor.** Zoom 1,3 + sayfa 7 + %40 konumla kapatıp yeniden açınca aynı yere döndü. Kaydırıp 50 ms sonra kapatınca da doğru (closeEvent `persist` ediyor). Kitaplıkta görünen tek iz: kapak altında `20 sayfa · s. 7`. "Ne zaman", "ne kadar", karşılama yok. **§2.5'in ikinci ihtimali doğru: sorun kayıt değil, güven.** Aşama 5'in "Devam et" kartı bunu çözer.

**Koleksiyon raf olarak kullanılabilir mi (§2.6)?** **Hayır, yetersiz.** `documents.collection` serbest metin sütunu; ayrı tablo, renk, sıra, açıklama yok. Boş raf olamaz (belgesi olmayan koleksiyon listede görünmez). Arayüz: kenar çubuğunda tek `QComboBox` filtresi; atama "Başlık / etiket / koleksiyon" iletişim kutusundaki metin kutusu. **§4.1'in ikinci yolu gerekli:** `shelves` tablosu eklenir, mevcut `collection` değerleri raf olarak taşınır (yedek alınarak).

**Metin seçimi yoğun metinde kullanışlı mı?** **Hayır.** Dikdörtgen içindeki kelime merkezleri alınıyor ([app.py:260](../app.py#L260)); çok satırlı seçimde okuma akışı değil sütun geliyor. Kitap okuyan biri için beklenmedik. Slaytta (kısa satırlar) daha az sorun. Akış seçimi (başlangıç kelimesinden bitiş kelimesine, `words()` sıra numaralarıyla) küçük bir değişiklik; Aşama 3 sonrasına not.

**Fosfor metne yapışıyor mu?** **Bırakınca evet, sürüklerken hayır.** Kayıt satır kutularıyla doğru; ama sürükleme önizlemesi yarı saydam dikdörtgen, metne yapıştığı ancak bırakıp yeniden üretim bitince görülüyor. "Gerçeklik hissi" boşluğu burada.

### 2.3 Kabul koşulu

| Koşul | Durum |
|---|---|
| 12 aracın her biri için durum ve gerekçe | ✅ 2.1 |
| Dört sorunun cevabı | ✅ 2.2 |

---

## 3. Beklenmedik bulgular

- **Paket git'te değil.** Yukarıda. Aşama 3 öncesi karar gerekli.
- **Her `Library` çağrısı 9 ms** (bağlantı aç-kapa). Sayfa üretiminde 4, dışa aktarımda 200+ kez. `render`, `words`, `annotations`, `get_state` hepsi bu yoldan. Kalıcı bağlantı ya da önbellek Aşama 3'te.
- **`poll()` her 1,2 s'de `revision()` kontrol ediyor; değişince görünür her sayfayı siliyor** ([app.py:626](../app.py#L626)). Pevrai MCP ile not eklediğinde okuyucu 500–800 ms donuyor. Ölçümde `[1, 2, 3, 1, 2, 3]` çift üretimi bundan.
- **`load()` açılışta üretimi hem doğrudan hem zamanlayıcıyla tetikliyor** ([app.py:115](../app.py#L115)): `set_zoom` → `clear_renders` (15 ms) + `go` (20 ms) + doğrudan `render_visible()`. İkinci tetik boş dönüyor ama kod okunurluğu açısından not.
- **200 sayfa içe alma 14–17 s** (metin çıkarma). Arka planda ama okuyucu kilitli; ilerleme yüzdesi yok (belirsiz çubuk).
- **`QTest.qWait` GIL'i bırakmıyor.** Arka plan işleri test sırasında 15× yavaş (slayt dışa aktarımı 0,3 s → 4,7 s). Paketin `tests/test_gui.py::test_background_callback_on_gui_thread` bu yüzden 100×30 ms bekliyor. Yeni testlerde `time.sleep` tabanlı bekleme kullanılmalı. Bu raporun ilk envanter koşusunda "PDF kaydet" ve "Sayfalar" bu artefakt yüzünden yanlışlıkla "çalışmıyor" çıktı; olay döngüsüyle tekrar ölçülüp düzeltildi.
- **`Cannot set border for 'Underline'`** uyarısı `_apply` içinde her alt çizgi üretiminde/dışa aktarımında konsola basılıyor. Zararsız ama `set_border` çağrısı alt çizgi için atlanmalı.
- **Bellek:** zoom 1'de sayfa başına ≈4 MB (kitap) / 4 MB (slayt), zoom 2'de 16 MB. Yalnızca görünür ±500 birim tutulduğundan 12–80 MB. Şimdilik sorun değil; arka plan üretimi + prefetch eklenince sınır konmalı.
- **Yan panelde dördüncü sekme (AI)** var; §4.2 üç sekme (Notlar, İçindekiler, Arama) diyor. Seçili metni AI istemine kopyalayan düğmeler burada. §7 "Pevrai'ya sor"u ertelediği için Aşama 4'te bu sekmenin kaderi kararlaştırılmalı.
- **Paket testleri Windows'ta 2 hata veriyor** (`pytest tests -q`: 11 geçti, 1 atlandı [Tesseract yok], 2 hata). İkisi de `test_page_operations_backup_and_archive` ve `test_mcp_opens_reader_and_reuses_window` içinde iddialar geçtikten **sonra** `TemporaryDirectory` temizliğinde `WinError 32` (açık `library.sqlite3` tanıtıcısı). TEST_RAPORU.md Linux'ta 14 geçti diyor; Windows'ta önceden de böyleydi, benim işimle ilgisi yok. Aşama 3 kabulü için "yeşil" tanımı bu ikisini kapsayacak şekilde düzeltilmeli (teardown'da bağlantıları kapatmak küçük bir test düzeltmesi).
- **Yer imi sayfada görünmüyor**, yalnızca listede. Kullanıcı "yer imi koydum" dedikten sonra sayfada iz yok.

---

## 4. Sonraki adım

Aşama 3'e geçmeden iki karar senin:

1. Paket içinde `git init` (öneriyorum; Aşama 3 çok dosyaya dokunacak).
2. §1.7'deki 1–4 (üretim hattı) + 7 (işaretleme katmanı) tek aşamada mı, iki aşamada mı? Öneri: 1–4 önce, ölçüm tekrarlanır, sonra 7. Böylece Aşama 3 kabulü ("kaydırma hiçbir koşulda beklemez") tek değişkenle ölçülür.
