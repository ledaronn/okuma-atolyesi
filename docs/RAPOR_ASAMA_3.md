# Aşama 3 raporu: akıcılık düzeltmesi (üretim hattı)

Tarih: 15 Eylül 2026. Commit'ler: `a8ae745` (taban, kod değişikliği yok), `5e7701c` (Aşama 3), `965ca48` (rapor, `stop()` düzeltmesi).
Ölçüm: `docs/olcum/olc.py`, Aşama 1 ile aynı script, aynı makine, aynı dört belge. Ham çıktı `docs/olcum/ham_arayuz_asama3.txt`.

Kapsam: Aşama 1 raporundaki 1–4 numaralı öneriler + 9 (dışa aktarım). 7 (işaretleme katmanı) ve 8 (yumuşak kaydırma) bu aşamada **yapılmadı**, sıradaki.

---

## 1. Kabul koşulları

| Koşul | Durum | Kanıt |
|---|---|---|
| Aşama 1 ölçümü tekrarlanmış, kare süresi raporlanmış | ✅ | §2 tablosu; `docs/olcum/ham_arayuz_asama3.txt` |
| İyileşme sayıyla gösterilmiş | ✅ | §2: tek tur tıkanma 300–800 ms → en fazla 16–41 ms |
| 100+ sayfalık belgede hızlı kaydırma denenmiş | ✅ | 200 sayfalık kitap, 120 tık / 8 ms ara: kaydırma sırasında tıkanma 0 |
| Kaydırma hiçbir koşulda beklemez; sayfa hazır değilse yer tutucu | ✅ (offscreen) | `test_rendering_never_blocks_gui_thread`: 1,5 s kaydırma + zoom 2, olay döngüsü turu < 50 ms; üretim UI dışında |
| Paket testleri yeşil | ✅ | `pytest tests -q`: **16 geçti, 1 atlandı** (Tesseract yok). Windows'ta önceden 2 hata vardı, ikisi de düzeltildi (§4) |
| `mcp_dogrula.py` | ✅ | 17 araç, `library_status` çalışıyor. Dört okuma aracı ve `get_reader_context` dokunulmadı |
| Veri kaybı yok, şema değişmedi | ✅ | Şema aynı; taşıma gerekmedi. Gerçek `OkumaAtolyesiVeri` klasörüne hiç dokunulmadı |

**Gerçek ekranda henüz denenmedi.** Ölçüm `offscreen`; boyama gerçek ekranda değişebilir ama üretim ve tıkanma sayıları platformdan bağımsız. Uygulamayı açıp hissetmen gerekiyor — özellikle görüntü tabanlı slaytta hızlı kaydırma.

---

## 2. Önce / sonra

Aynı senaryolar, aynı ölçüm tanımı ("tıkanma" = 16 ms'i aşan tek olay döngüsü turu).

| Senaryo | Belge | Aşama 1 | Aşama 3 |
|---|---|---|---|
| Açılış | kitap / slayt / görüntü slayt | 713 / 779 / 1032 ms tek blok | 338 / 360 / 357 ms, **tıkanma yok** (sayfalar arka planda geliyor) |
| Hızlı kaydırma, *sırasında* | kitap | 0 üretim (beyaz), 28 ms | 15 sayfa üretildi, **0 tıkanma** |
| Hızlı kaydırma, *durunca* | kitap / slayt | **336 / 509 ms** tek blok | 17 / 16 ms |
| Hızlı kaydırma | görüntü slayt | 515–607 ms donma | **0 tıkanma** |
| Yavaş kaydırma (okuma hızı) | kitap / slayt | 7 tıkanma, 718 / 895 ms | **tıkanma yok** |
| Genişliğe sığdır | kitap / görüntü slayt | 402 / 615 ms | 16 ms / yok |
| Ctrl+tekerlek 1 adım | tümü | 282–514 ms | **tıkanma yok**, eski görüntü yerinde kalıyor |
| Sayfa atlama | tümü | 351–744 ms | **tıkanma yok** |
| Tek işaretleme sonrası | kitap / görüntü slayt | 638 / 805 ms | 22 ms / yok |
| Sayfa başına üretim (zoom 1) | kitap / slayt / görüntü slayt | 123 / 127 / 267 ms | **10 / 8 / 85 ms**, UI dışında |
| Sayfa başına üretim (zoom 2) | kitap | 337 ms | 24 ms |
| PDF kaydet (200 s kitap) | | 3,7 s | 1,2 s |

Kalan tek tur tıkanmalar (16–41 ms, tek kare) `QPixmap.fromImage` (2–6 ms) ve ara sıra `poll()`'dan; hepsi 50 ms'in altında, kullanıcı algısının sınırında. Sıfırlamak için kalan tek yol boyamayı da ayrı tutmak; gerek görmüyorum.

---

## 3. Ne değişti ve neden

### 3.1 Sayfa üretimi ayrı süreçte (`render_worker.py`, `core.RenderProcess`)

Planlanan "işçi iş parçacığı" **yetmedi**; ölçüm bunu gösterdi (§4.1). PyMuPDF 1.26.6 C çağrıları boyunca GIL'i bırakmıyor: `_mupdf.pyd` Python API'yi adla içe aktarıyor ama `PyEval_SaveThread`/`PyGILState_*` hiç yok. Aynı süreçteki bir iş parçacığı sayfa üretirken arayüzün Python tarafı (`wheelEvent`, `mouseMoveEvent`, sinyal işleyicileri) o kadar donuyor: görüntü tabanlı slaytta sayfa başına 100+ ms.

Çözüm: `app.py` başlarken `render_worker.py`'yi alt süreç olarak açıyor. Protokol tek satır JSON istek → JSON başlık + ham RGB. 3 MB'lık sayfa borudan ~3 ms'de geçiyor; boru okuması GIL'i bırakıyor. Yan kazançlar: üretim artık ana sürecin `PDF_LOCK`'u için yarışmıyor (kalem/fosfor/silgi beklemiyor); süreç çökerse bir kez yeniden başlatılıyor (test edildi: 410 ms). Maliyet: ikinci Python süreci ≈ 56 MB (+7 MB venv yönlendiricisi), soğuk başlangıç ≈ 400 ms — pencere açılırken başlatılıyor, ilk belge açılana kadar ısınıyor.

### 3.2 Okuyucu (`app.py`: `RenderWorker`, `Reader`)

- İşçi iş parçacığı öncelik kuyruğu tutar: görünenler önce, merkeze yakın daha önce; bir ekran ilerisi arkadan. Sonuç `generation` ile damgalı; belge/yakınlaştırma değiştiyse atılır.
- Kaydırma sürerken de üretim istenir (zamanlayıcı artık sıfırlanmıyor; 30 ms'de bir dolar).
- Yakınlaştırmada eski görüntü görünüm dönüşümüyle ölçeklenip yerinde kalır, yenisi gelince değişir — beyaz yanıp sönme yok.
- İşaretleme sonrası yalnızca o sayfa yenilenir (`clear_renders(page)`); kalem çizgisi yeni görüntü gelene dek ekranda kalır (önceden bırakınca kaybolup 370–770 ms sonra geliyordu).
- Bellek: görünen ± 2 ekran tutulur (ölçülen 12–17 MB).

### 3.3 Çekirdek (`core.py`)

- **PNG kaldırıldı:** `pix.samples` doğrudan `QImage(Format_RGB888)`. Çıktı PNG yoluyla bayt bayt aynı (test edildi). `Library.render()` (PNG) testler için korundu.
- **İş parçacığı başına kalıcı SQLite bağlantısı.** Her çağrıda aç-kapa bu makinede 9 ms (okuma) / 35 ms (yazma) tutuyordu; `persist` ve `poll` ana iş parçacığında 30–95 ms bloke ediyordu (§4.3). Şimdi 0,4 ms. `Library.close()` eklendi; uygulama kapanışında ve testlerde çağrılıyor. Şema ve dosya biçimi aynı.
- **`export_pdf`:** 200 sayfa için 200 ayrı `check_page` sorgusu yerine tek belge kaydıyla doğrulama. `garbage=4` korundu (çıktı boyutu için).
- `_apply` `staticmethod` oldu (üretim süreci de kullanıyor).

---

## 4. Beklenmedik bulgular

### 4.1 İşçi iş parçacığı denendi, yetmedi — ölçüm

İlk uygulama plandaki gibi `QThread` idi. Tıkanma 400–800 ms'den 20–190 ms'e indi ama sıfırlanmadı; görüntü slaytında kaydırma sırasında 14 × ~100 ms. Uzun turların içinde Python işi yoktu (`page_ready` 0 ms, boyama 0 ms) — ana iş parçacığı *bekliyordu*. Sahte üretimle ayrıştırma: `time.sleep` yerine koyunca tıkanma kayboldu, GIL tutan C çağrısı koyunca geri geldi. Sonra `_mupdf.pyd` içe aktarma tablosunda GIL bırakma çağrısı olmadığı doğrulandı.

### 4.2 Şerit üretimi denendi, çıkmaz

GIL'i kısa aralıklarla bırakmak için sayfa 8 yatay şeritle üretildi (`DisplayList.get_pixmap(clip=…)`). Metin sayfasında en uzun C çağrısı 126 → 4 ms ve piksel aynı; ama **görüntü tabanlı sayfada** soğuk önbellekle her şerit görüntüyü yeniden çözdü (27 → 278 ms) ve pikseller farklı çıktı (klip boyutuna göre farklı alt örnekleme). Alt düzey `fz_new_draw_device_with_bbox` sarmalayıcısı çöküyor; alt pixmap yaklaşımı da hem yavaş hem farklı. Terk edildi; kod yok.

### 4.3 Kalan tıkanmanın kaynağı SQLite'tı

Üretim süreçten sonra kalan 30–95 ms'lik turların hepsi `persist()` (2 yazma) ve `poll()` (komut kuyruğu yazması + revizyon) — ana iş parçacığında bağlantı aç-kapa. `synchronous=NORMAL` etkisiz (30,7 ms), "çapa" bağlantı etkisiz; kalıcı bağlantı 0,4 ms. Uygulandı.

### 4.4 `backup()` Windows'ta bozuktu (gerçek hata, düzeltildi)

`with sqlite3.connect(dbcopy) as db:` bağlantıyı kapatmıyor (sqlite3'te `with` yalnızca commit eder). Açık kopya, geçici klasörün silinmesini engelliyor → `PermissionError` → "Kütüphaneyi yedekle" ZIP'i yazdıktan **sonra** "İşlem tamamlanamadı" diyordu. Aşama 1'de "Windows teardown hatası" sandığım şey buydu. `contextlib.closing` ile düzeltildi; test şimdi geçiyor.

### 4.5 MCP testi Windows temizliği

`os.kill(pid, SIGTERM)` açılan okuyucu sürecini Windows'ta kapatamıyor (WinError 5). İddialar geçiyordu; `taskkill /T` yedeği eklendi. Aynı yönlendirici sorunu `RenderProcess.stop()` için de geçerliydi (venv `python.exe` bir yönlendirici, asıl süreç çocuğu): kill yedeği ağacı kapatacak şekilde düzeltildi. Normal kapanış stdin kapatmayla, kill'e düşmeden.

### 4.6 `QTest.qWait` GIL'i bırakmıyor

Yeni testlerde `idle()` (processEvents + `time.sleep`) kullanıldı. Mevcut testler qWait ile kalabilir; arka plan üretimi bekleyen her yeni test `idle` kullanmalı. `tests/test_gui.py` içinde not var.

### 4.7 Küçük

- Açılışta sayfa 1 iki kez üretiliyordu (`load` → `set_zoom` nesli bir daha artırıyordu); düzeltildi.
- Kısa belgede hızlı kaydırmada 3–5 sayfa iki kez üretiliyor (belge sonunda). Zararsız, bakılmadı.
- `DOSYA_OZETLERI.sha256` yeniden üretildi; `render_worker.py` eklendi.

---

## 5. Yapılmayanlar ve sıradaki

- **7 — İşaretleme katmanı** (kalem/fosfor/silgi anında; sayfa yeniden üretilmeden): sıradaki adım. Bugün işaretleme sonrası yalnızca ilgili sayfa 10–85 ms'de yenileniyor; katmanla sıfır olur ve silgi hover geri bildirimi mümkün olur.
- **8 — Yumuşak kaydırma:** 111 px'lik animasyonsuz sıçrama duruyor. Aşama 4 (odak/görsel) ile birlikte uygun.
- Gerçek ekran denemesi (sen).

---

# Aşama 3b: işaretleme katmanı

Tarih: 15 Eylül 2026. Commit: `f75bde7`. Aşama 1 raporundaki 7 numaralı öneri.

## Kabul

| Koşul | Durum | Kanıt |
|---|---|---|
| İşaretleme eklemek/silmek sayfa görüntüsünü yenilemez | ✅ | `docs/olcum/ham_arayuz_asama3b.txt`: "tek işaretleme sonrası: **0 sayfa** yeniden üretildi" (4 belge); `test_annotation_layer_does_not_rerender_pages` |
| Kalem çizgisi bırakınca kaybolmaz | ✅ | Bırakınca geçici çizim kalkar ve aynı karede kalıcı öğe gelir (`reader.temp is None`, öğe `ann_items`'ta) |
| Silgi ne sileceğini gösterir | ✅ | Üzerine gelince kırmızı kesikli çerçeve + imleç; testte `hover_item` doğrulanıyor |
| Fosfor önizlemesi satıra yapışır | ✅ | `test_highlight_preview_snaps_to_lines_and_rotated_page`: sürüklerken önizleme kutusu sözcük satırıyla ±1 pt |
| Döndürülmüş sayfada katman doğru yerde | ✅ | Aynı test, fikstürün 90° döndürülmüş 2. sayfası |
| Dışa aktarım, geri al/yinele, MCP bozulmadı | ✅ | 17 test geçti (`PDF kaydet` 4 açıklama), `mcp_dogrula` çalışıyor; envanterde 12/12 araç çalışıyor |
| Görsel kontrol | ✅ | Offscreen ekran görüntüsünde yedi tür de incelendi (fosfor çarpma karışımı, ok başlığı, not ikonu, kurdele, silgi vurgusu) |

## Ne değişti

- `app.AnnotationItem`: bir işaretleme = bir `QGraphicsItem`, sayfa görüntüsünün üstünde (z=5). Saklanan PDF noktası → görüntülenen nokta dönüşümü `core.geometry()`'nin yeni `matrix` alanıyla. Fosfor `CompositionMode_Multiply` ile çiziliyor: metin siyah kalır, zemin renge döner — gerçek kalem gibi. Yer imi sağ üstte kurdele (Aşama 2 bulgusu: "sayfada görsel işaret yok").
- Sürükleme önizlemesi de aynı sınıfla (`matrix=None`): fosfor/alt çizgi satır kutularına yapışır, metin seçimi mavi sözcük kutuları gösterir, kalem/ok aynı kalınlık ve renkle. Sözcük kutuları basışta bir kez alınır, bırakışta yeniden sorgulanmaz.
- Silgi: `annotation_at()` katmandaki öğelerle isabet testi yapar (kalem/ok için parça-nokta uzaklığı, diğerleri kutu). `erase_at` (her tıkta PDF açma + `PDF_LOCK` + SQLite) kaldırıldı.
- Üretim süreci artık yalnızca PDF'nin kendi içeriğini üretir; işaretlemeli sayfa için "taze kopya" yolu gitti. Tüm sayfalar ömür boyu açık belgeden, 8–10 ms.
- `Library.render()` (PNG) hâlâ işaretlemeleri pişiriyor; dışa aktarım ve MCP için doğru olan bu.

## Beklenmedik

- `QRectF.united()` null dikdörtgeni yok sayıyor; kalem/ok sınır kutusu tek noktaya küçülmüştü (silgi vurgusu minik kare çıktı, ekran görüntüsünde yakalandı). Noktalardan açık min/max ile düzeltildi.
- İşaretleme eklerken kalan tek kare (22–23 ms) `Library.add_annotation`'ın her seferinde PDF'i açması (`derotation_matrix` için). Katmanla ilgisi yok; istenirse geometry önbelleğiyle sıfırlanır.
- `docs/olcum/envanter.py`'nin açıklama metinleri Aşama 2 durumunu anlatıyor (sabit metin); durum sütunu güncel.

## Sıradaki

Aşama 4 (tam ekran, yüzen araç adası, tek kayan panel). Yumuşak kaydırma (öneri 8) orada.

---

# Aşama 3c: araçlar kalem gibi (kullanıcı geri bildirimi sonrası)

Tarih: 15 Eylül 2026. Commit: `123be35`. Gerçek ekranda denemenin sonucu: "çizim tam bir fiyasko, + işareti var, fosforda alan seçiyorsun."

Ekran görüntüsünde görülen üç sorun ve karşılığı:

| Sorun | Neden | Değişiklik |
|---|---|---|
| Fosfor alan seçiyor, boş yerde koca dikdörtgen bırakıyor | Fosfor/alt çizgi kutu sürüklemeyle çalışıyordu (1.0'dan beri); katman bunu değiştirmemişti | İz tabanlı: izin değdiği sözcükler satır satır boyanır, hızlı geçişte satır içi boşluk doldurulur. Metin yoksa kalın yarı saydam serbest iz (`ink`+`marker`, dışa aktarımda opacity 0,4). Dikdörtgen fosfor yok |
| "+" imleci | Her araçta `CrossCursor` | Kalem, fosfor, silgi imleçleri (çizilmiş); seçimde I-imleç; kutu/ok'ta artı kalır |
| Gerçeklik hissi yok | Kalem de fosfor da aynı turuncu, 2 pt; kalem çizgisi köşeli | Araca özel renk/uç (kalem koyu 1,8; fosfor sarı 12; alt çizgi kırmızı 1,4), QSettings'te hatırlanır; kalem çizgisi eğrilerle yumuşatılır |

Aynı mekanizmayla metin seçimi de değişti: sözcükten sözcüğe okuma sırasıyla akıyor (Aşama 2 bulgusu "sütun seçiyor"). Sözcük yoksa dikdörtgene düşer.

Testler: 18 geçti, 1 atlandı. Yeni: `test_highlighter_and_selection_behave_like_pens` (iz boyunca üç sözcük, boş alanda dikdörtgen değil iz, iki satır arası akış seçimi, stiller bağımsız). Döndürülmüş sayfa testi iz semantiğine uyarlandı; dokunma toleransı simetrik (kalınlık/4, en az 2 pt) — 90° sayfada satır yönü değiştiği için.

Gerçek slaytta ekran görüntüsüyle kontrol edildi: sarı iz sözcükler boyunca, boş yerde dalgalı bant, kırmızı alt çizgi, yumuşak koyu kalem, iki satırlı mavi seçim.

**Not:** Aşama 2'de "fosfor metne yapışıyor" demiştim; doğruydu ama *bırakınca* ve *kutu* mantığıyla. Ekranda kalem gibi hissettirmediğini ancak gerçek ekranda sen gösterince anladım. Offscreen ölçüm işlevi ölçüyor, hissi ölçmüyor.
