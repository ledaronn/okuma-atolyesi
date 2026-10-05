# Aşama 6 raporu: çalışma oturumu ve ilerleme

Tarih: 15 Eylül 2026. Testler: **27 geçti, 1 atlandı**. `mcp_dogrula.py` çalışıyor.

## Kabul koşulları

| Koşul | Durum | Kanıt |
|---|---|---|
| Pencere arkadayken sayaç duruyor | ✅ | `test_study_tracker_counts_only_active_time`: `active_fn` False iken 50 tık → süre değişmedi |
| Beş dakika hareketsizlikte duruyor | ✅ | Son etkinlikten 300 s sonra tıklar sayılmıyor; yeni etkinlikle devam |
| Sayılar kapat-aç sonrası korunuyor | ✅ | Oturum satırı; `Library` yeniden açılınca `today_summary` aynı (401 s, 3 sayfa, 1 işaretleme) |
| Kitaplıkta gösterim | ✅ | `test_session_shown_in_library`: "Bu oturum: 2 dk · 2 sayfa · 1 işaretleme", "Bugün 2 dk…", kartta süre |

## Ne var

- `sessions` tablosu: belge, başlangıç/bitiş, etkin saniye, sayfa, işaretleme. 30 s'de bir ve bitişte yazılır (ani kapanışta ≤ 30 s kayıp). 5 s'den kısa oturumlar silinir.
- `StudyTracker`: saniyelik tık; `QApplication.applicationState()==Active` ve pencere küçültülmemişken, son etkinlikten 5 dk geçmemişse sayar. Etkinlik: kaydırma/sayfa, işaretleme, seçim, fare hareketi, klavye.
- Sayfa sayacı: bu oturumda görülen farklı sayfalar. İşaretleme sayacı: bu oturumda eklenenler.
- Gösterim: okuyucudan çıkınca oturum özeti (durum çubuğu); kitaplıkta "Bugün …" satırı; rafta "bu hafta 1 sa 20 dk"; belge kartında toplam süre; şeritte "· 12 dk".
- Yüzde tek başına verilmiyor (§4.6): "görülen sayfa / toplam" süreyle birlikte.

## Not

- Sayaç yalnızca uygulama öndeyken sayar; başka pencerede ders çalışırken belge açık kalsa da sayılmaz — tasarım gereği.
