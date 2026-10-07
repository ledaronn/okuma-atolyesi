# Aşama 4 raporu: odak — tam ekran okuyucu, araç adası, tek panel

Tarih: 15 Eylül 2026. Commit: `59174d7`. Testler: **20 geçti, 1 atlandı** (Tesseract). `mcp_dogrula.py` çalışıyor.

## 1. Kabul koşulları

| Koşul | Durum | Kanıt |
|---|---|---|
| Okuyucuda sayfa dışında kalıcı öğe yok | ✅ | Başlık, kenar çubuğu, durum çubuğu okuyucuda gizli; `Reader` okuyucu alanının tamamını kaplıyor (`test_focus_mode_only_page_is_permanent`) |
| Araç adası açılır/kapanır, kapalıyken yer kaplamaz | ✅ | Kapalıyken `island.x() >= genişlik` (ekran dışı); 7 px'lik tutamak sayfa kenarında yüzer, düzen alanı almaz |
| Panel tek ve kayar | ✅ | Sağdan 340 px kayan tek kutu; Notlar / İçindekiler / Ara. AI sekmesi kaldırıldı, AI isteği kopyalama şerit menüsünde |
| Kısayollar çalışıyor | ✅ | T ada, N panel, F11 tam ekran, Ctrl+F paneli arama sekmesiyle açıp odaklıyor — testte tuşla doğrulandı |
| Mevcut kısayollar korunmuş | ✅ | Ctrl+O/Z/Shift+Z/S aynen; Esc: panel → ada → tam ekran → kitaplık (son adım eskisi gibi kitaplığa döner) |
| Üst şerit fareyle belirip kayboluyor | ✅ | Üst 6 px'e gelince kayarak iner; şeritten çıkınca 0,9 s sonra kalkar; açılışta 2,5 s görünür (testte gizlendiği doğrulandı) |
| Kaydırma yumuşak | ✅ | Tekerlek tıkı 170 ms animasyon, üst üste tıklar hedefte birikir (`test_wheel_scroll_is_animated`); dokunmatik yüzey Qt'ye bırakılır |
| Akıcılık korunmuş | ✅ | `olc.py` tekrar: kaydırmada tıkanma 0–3 × ≤ 40 ms. Görünüm büyüdüğü için genişliğe sığdır ≈ zoom 2 → sayfa başına 43 ms, UI dışında |

Gerçek ekranda henüz senin gözünle denenmedi (offscreen yazı tipleri kutu çıkıyor; düzen ve davranış doğrulandı).

## 2. Ne var

- **Üst şerit:** ‹ Kitaplık · belge adı · Sayfa N / toplam · %zoom · − + · Genişliğe sığdır · Yer imi · Panel · ⋯ (PDF kaydet, Sayfalar, Notları dışa aktar, OCR, AI isteği kopyala ▸, Araç adası, Tam ekran).
- **Araç adası (sağ, dikey):** Taşı · Metin seç · Kalem · Fosfor · Alt çizgi · Not · Silgi · ⋯ (Kutu, Ok) — renk · uç (1–18 pt menüsü) — geri al · yinele. Simgeler çizilmiş, yazı tipine bağlı değil. Panel açıkken ada panelin soluna kayar.
- **Bildirim baloncuğu:** durum iletileri okuyucuda 2,6 s'lik koyu baloncuk (alt orta); kitaplıkta durum çubuğu kalır.
- **README** ve uygulama içi rehber güncellendi.

## 3. Beklenmedik

- Metin seçimi bağlantı noktası: sözcük bandının dışında en yakın sözcüğü ararken satır *kenarı* yerine satır *merkezine* uzaklık kullanılıyor; yoksa iki satır arasına düşen nokta üst satırı seçebiliyordu. Sentetik kitapta satırlar 0,9 pt aralıklı olduğundan uç durum kaldı: sözcüğün 2 pt altı fiziksel olarak sonraki satır. Gerçek kullanımda fare sözcüğün üstüne bırakılır; `envanter.py` sondaları buna göre güncellendi.
- Offscreen ekran görüntülerinde yazı tipi yok (widget metinleri kutu). PDF içeriği ve çizimler görünür; düzen ondan doğrulandı.
- İlk sürümde `test_window_close_stops_render_process` sıraya bağlı olarak 0,5 s'de ilk sayfayı göremedi (üretim süreci soğuk başlangıcı); koşullu bekleme eklendi.

## 4. Yapılmayan

- Okuma modu (§4.3) ve slayt/kitap ayrımı (§4.4): Aşama 7.
- Sayfa başına not paneli (§4.5): Aşama 8.
- Klavyeyle sayfa geçişi (PageDown/Space) Qt'nin adım kaydırmasıyla; animasyonsuz. Slayt modunda (Aşama 7) ele alınacak.

Sıradaki: **Aşama 5** — raflar, "Devam et", belge başına ilerleme.

---

# Aşama 4b: gerçek ekran geri bildirimi sonrası

Tarih: 15 Eylül 2026. Commit: `21c6394`. Testler: 20 geçti, 1 atlandı. MCP çalışıyor.

| Geri bildirim | Neden | Ne yapıldı |
|---|---|---|
| "Panel N açılıyor ama kapanmıyor" | Panel açılınca odak listeye geçiyor; liste `N` tuşunu klavye aramasına alıyor, `QShortcut` hiç görmüyor | T/N uygulama düzeyinde olay filtresiyle, odaktan bağımsız (metin kutuları hariç). Testte liste odaktayken N ile kapanış doğrulanıyor |
| "Panel N ne işe yarıyor, üst barda ikon yok, kalemlik nerede" | 7 px'lik tutamak fark edilmiyor; "Panel N" etiketi anlamsız | Şeride simgeli **Kalemlik** ve **Notlar** düğmeleri; kalemlik ilk açılışta açık, durumu hatırlanır; ilk belgede 5 s'lik ipucu baloncuğu |
| Tekerlek "Apple gibi, abartısız" | 170 ms OutCubic kısa | 380 ms OutQuart, üst üste tıklar hedefte birikir |
| "PDF zemini şeffaf, buğulu" | Sayfa opak beyaz üretiliyordu | Sayfa saydam üretilir (alpha); zemine beyaz dikdörtgen çizen PDF'lerde saf beyaz da saydam (`set_alpha(opaque=beyaz)`, C'de 9 ms, üretim sürecinde). Kâğıt yarı saydam, altındaki ton görünür; ucuz kenar gölgesi |
| Okuma modları, gece, uygulama koyu/açık | Yoktu | **Görünüm** menüsü: tema Açık/Koyu; zemin Kağıt/Sıcak/Loş/Gece (gece: içerik ters çevrilir, koyu mürekkep aydınlatılır, fosfor yarı saydam). Hatırlanır |
| "Notlar hatalı, not alınamıyor, kalem hareketleri not diye listeleniyor" | Liste her işaretlemeyi gösteriyordu; yazılacak yer yoktu | Panelde not kutusu + "Not olarak kaydet"; seçili notu düzenleme (`update_annotation_text`, geri alınabilir); listede notlar/metinli fosfor/yer imi, çizimler kutucukla |

## Beklenmedik: bulunan iki performans kökü

1. **Stil sayfasında `QGraphicsView`'a kural olması** (yalnızca `border:0` bile) Qt'nin kaydırma hızlandırmasını kapatıyor; her adımda tüm görünüm boyanıyor. 1.0'dan beri böyleydi; opak blit ucuz olduğu için görünmüyordu (`olc.py` stil uygulamadığından ölçümde de görünmedi). Saydam katmanlar gelince 8–50 ms oldu. Kural kaldırıldı, çerçeve kodla sıfırlandı → 0,5 ms.
2. **Görünümün üstünde duran herhangi bir alt widget** (ada, tutamak, baloncuk) aynı etkiyi yapıyor. Kalemlik görünümün *yanına*, oluğa alındı (kapalıyken 12 px); şerit ve baloncuk geçici. Ölçüm: ada açıkken boyama 0,8 ms, genişliğe sığdırılmış kitapta 1,1 ms.

Ayrıca: saydam kâğıt + ARGB içerik + ton katmanlarını her karede birleştirmek yerine zemin düz renk olduğu için birleşim **işçide** tek opak görüntüye pişiriliyor; ana iş parçacığı `QPixmap.fromImage` kopyası yapmadan `QImage` çiziyor (`PageImageItem`). Ekran çözünürlüğüyle 1:1 üretim (1,4× fazla örnekleme kalktı). Uçuştaki sayfa kuyruk yenilenince ikinci kez istenmiyor (görüntü slaytında sayfalar 2–3 kez üretiliyordu).

`Reader.width` özelliği `QWidget.width()`'i gölgeliyordu (gerçek hata) → `pen_width`.

Denenip vazgeçilen: `QGraphicsDropShadowEffect` (her boyamada bulanıklaştırma, 60 ms), degrade zemin (`ObjectMode` degrade kaydırmada şerit şerit hesaplanıp bantlanıyor), `DeviceCoordinateCache`.
