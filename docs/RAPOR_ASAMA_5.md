# Aşama 5 raporu: raflar, "Devam et", belge başına ilerleme

Tarih: 15 Eylül 2026. Testler: **25 geçti, 1 atlandı**. `mcp_dogrula.py` çalışıyor.

## Kabul koşulları

| Koşul | Durum | Kanıt |
|---|---|---|
| En az üç raf kurulabiliyor | ✅ | `test_shelves_migration_crud_and_seen_pages`: 3 raf; ad, renk; kopya ad reddi |
| Belge rafa taşınıyor | ✅ | "Rafa koy" menüsü, Başlık/etiket iletişim kutusunda raf seçimi; `move_to_shelf` |
| Raf silinince belge silinmiyor | ✅ | `delete_shelf` → belge `shelf_id=''`, kütüphanede kalıyor (test) |
| "Devam et" en son çalışılan belgeyi doğru sayfada açıyor | ✅ | `test_library_shelves_and_resume_card`: sayfa 3'te bırak → kart "Sayfa 3 / 3" → tıkla → sayfa 3 |
| Mevcut koleksiyonlar kayıpsız taşınmış | ✅ | Eski şemalı DB (shelf_id yok, koleksiyon adı var) yeniden açılınca: önce `library.sqlite3.yedek-…`, sonra her ad bir raf, belgeler bağlı; `list_documents(collection=ad)` çalışmaya devam |
| MCP sözleşmesi | ✅ | `collection` alanı raf adı olarak kalıyor; `update_metadata(collection=…)` rafı oluşturur/atar; `get_reading_state` yalnızca `seen` alanı **ekler** |

## Ne var

- `shelves` tablosu (id, ad, renk, sıra) + `documents.shelf_id`. `collection` sütunu denormalize raf adı — dış sözleşme değişmedi.
- Kenar çubuğu: "Tüm raflar / raflar (renk, belge sayısı) / Rafsız"; `+` ile yeni raf; sağ tık: yeniden adlandır, renk, kaldır.
- Kitaplık üstünde **Devam et** kartı: kapak, başlık, "Sayfa N / toplam · K sayfa görüldü · son çalışma", tek düğme.
- Her belge kartında "K/N sayfa görüldü · dün 14:30" (açılmadıysa "henüz açılmadı").
- Görülen sayfa: görünen alanın en az yarısını kaplayan ya da tamamen görünen sayfa, konum kaydıyla `state.seen` içinde.

## Yapılmayan / sonraya

- "Rafta bu haftaki çalışma süresi" (§4.1) etkin süre ölçümüne bağlı → Aşama 6.
- Raf sıralamasını sürükleyerek değiştirme yok (ad sırası).
