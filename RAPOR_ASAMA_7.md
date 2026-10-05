# Aşama 7 raporu: okuma modu ve belge türü ayrımı

Tarih: 15 Eylül 2026. Testler: **29 geçti, 1 atlandı**. `mcp_dogrula.py` çalışıyor.

## Kabul koşulları

| Koşul | Durum | Kanıt |
|---|---|---|
| Slayt PDF'i ve kitap PDF'i ile ayrı ayrı denenmiş, düzen uygun | ✅ | Gerçek ders slaytı (16:9) → slayt: sayfa ekrana sığıyor, tekerlek/ok sayfa sayfa (ekran görüntüsü). Sentetik 200 s kitap → kitap: sürekli. `test_guess_layout_slide_vs_book`, `test_slide_layout_and_reading_mode` |
| Tür tahmini yanlışsa elle değiştirilebiliyor | ✅ | `⋯ → Düzen → Otomatik / Slayt / Kitap`; belge başına `state.layout`; testte slayt → kitap geçişi |
| Okuma modu açık/kapalı geçişi belgeyi bozmuyor | ✅ | R ile aç/kapa: sayfa korunur, zemin/gölge/genişlik geri döner; işaretlemeler katmanda, etkilenmez |

## Ne var

- **Tahmin** (`core.guess_layout`): sayfaların medyan en-boy oranı ≥ 1,15 → slayt; ≤ 0,9 → kitap; arası → sayfa başına ortalama metin uzunluğu (< 700 karakter → slayt). Medyan: tek döndürülmüş sayfa kararı bozmasın diye (fikstürde çıktı).
- **Slayt düzeni:** `apply_layout` sayfayı hem genişlik hem yükseklikçe sığdırır; `step_page` animasyonlu sayfa geçişi (animasyon sürerken gelen tıklar yutulur, sayfa atlanmaz). Tekerlek, ←/→/↑/↓, PageUp/Down, Space, Backspace.
- **Kitap düzeni:** sürekli; PageDown/Space bir ekranın %90'ı, oklar 80 px, Home/End — hepsi animasyonlu.
- **Okuma modu:** zoom = min(görünüm−80, 820 px)/sayfa genişliği; zemin = kâğıdın görünen rengi; `PaperItem.reading` gölgeyi kapatır; kalemlik ve panel kapanır; pencere boyutu değişince yeniden sığdırır. Şeritte "Okuma" düğmesi ve R.

## Beklenmedik: gerçek hata bulundu ve düzeltildi

Saydam sayfa üretiminde `set_alpha(hepsi 255, opaque=beyaz)` MuPDF'in ürettiği alfa kanalını eziyordu: **zemin çizmeyen PDF'lerde (kitapların çoğu) sayfa siyah çıkıyordu.** Beyaz zemin çizen slaytlarda ve örnek belgede görünmediği için Aşama 4b'de yakalanmadı; okuma modu ekran görüntüsünde ortaya çıktı. Artık mevcut alfa korunup yalnızca beyaz saydam yapılıyor (kitap %87 saydam, ek maliyet yok).
