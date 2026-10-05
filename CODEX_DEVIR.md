# Codex için devir notu (Claude, 2026-10-04)

Codex'in kullanım limiti dolduğu için Okuma Atölyesi'nde çalışmaya Claude devam etti. Bu dosya,
Codex döndüğünde **neyin değiştiğini** tek yerden görsün diye tutulur. Her iş bu listeye eklenir.

## 1. Codex'in yarım işi korundu

- Commit `490a407` — Codex'in kaydedilmemiş değişiklikleri **olduğu gibi** kaydedildi (içeriğe
  dokunulmadı): `app.py`, `core.py`, `server.py`, `mcp_dogrula.py`, `README.md`,
  `CLAUDE_ENTEGRASYON.md`, `tests/test_*.py`, yeni `assistant_link.py`.
- Kaydetmeden önce: `pytest tests` → 38 geçti, 1 atlandı.
- Codex devam ederken: `git log 490a407..` Claude'un bundan sonraki bütün değişikliklerini gösterir.

## 2. Kullanıcının istediği yeni iş

1. **Word benzeri belge editörü:** sıfırdan `.docx` yazma. Faz 1 kapsamı (kullanıcı seçti):
   oluştur/aç/kaydet, yazı tipi/boyut/renk, kalın-italik-altçizgi-üstçizgi, başlık stilleri,
   hizalama, satır aralığı, madde/numara listeleri, tablo, resim, sayfa düzeni (A4, kenar
   boşlukları, sayfa sonu), üst/alt bilgi ve sayfa numarası, bul-değiştir, geri al, kelime sayısı,
   PDF'e aktar, yazdır. Faz 2: içindekiler, dipnot, yorumlar, değişiklik izleme, yazım denetimi.
2. **Varsayılan uygulama:** `.pdf` ve `.docx` için kullanıcı düzeyinde (HKCU) "Birlikte aç" adayı
   ol; uygulama içinden Windows Varsayılan Uygulamalar sayfasını aç; kaydı kaldırma da olsun.
3. **Uygulama gibi:** konsolsuz başlatıcı (pythonw), kendi simgesi; ayrı GitHub deposu.

## 3. Yerleşim kararı

- Editör **ayrı paket**: `belge/` (Codex'in dosyalarıyla çakışmasın diye). `app.py`'ye yalnızca
  giriş noktası (menü/komut satırı) eklenir; her dokunuş aşağıda listelenir.

## 4. Değişiklik günlüğü

(her commit buraya: ne, neden, hangi dosyalar, hangi testler)

### Belge editörü + varsayılan uygulama (Claude)

Kullanıcı kararı: **birleşik yol** — hafif yerel editör (sıfırdan yazma) + tam Word gücü için
"LibreOffice'te aç" (LibreOffice bu makinede kurulu; MPL, yalnızca çalıştırılıyor). ONLYOFFICE
(AGPL) ve ücretli web editörleri bilinçli olarak seçilmedi (lisans, ağırlık).

**Yeni dosyalar (Codex'in dosyalarıyla çakışmaz):**
- `belge/docx_io.py` — `.docx` ↔ `QTextDocument` (python-docx). Kayıp koruması: Word dosyasında
  editörün taşıyamadığı içerik (izlenen değişiklik, yorum, dipnot, metin kutusu, kayan resim,
  içerik denetimi, denklem, grafik, dikey hücre birleştirme, çok bölüm) `uyarilar` listesinde.
- `belge/editor.py` — pencere: sayfa görünümü (A4, kenar boşlukları, üst/alt bilgi, sayfa no),
  şerit (Dosya/Giriş/Ekle/Düzen), bul-değiştir, kelime/sayfa sayacı, PDF'e aktar, yazdır,
  LibreOffice'te aç. Kayıplı Word dosyasının **üstüne kaydetmez**; Farklı kaydet'e yönlendirir.
- `belge/kayit.py` — HKCU "Birlikte aç" kaydı (.pdf, .docx), Capabilities/RegisteredApplications,
  `kaldir()` tam geri alır; Ayarlar > Varsayılan uygulamalar sayfasını açar.
- `ac.pyw` — ilişkilendirmenin çağırdığı konsolsuz başlatıcı: `.docx` → editör, `.pdf` → okuyucu.
- `belge/__main__.py` — `python -m belge [dosya.docx]`.
- Testler: `tests/test_belge.py` (gidiş-dönüş, uyarılar), `tests/test_belge_editor.py`
  (pencere; PDF metni gerçek Windows platformunda), `tests/test_belge_kayit.py` (kayıt test
  kökünde, başlatıcı, komut satırından PDF).

**`app.py`'ye dokunulan yerler (Codex dikkat):**
1. Araçlar ▾ menüsü: "Yeni belge (Word)", "Belge aç (.docx)…", "Varsayılan uygulama…".
2. `Window` sınıfına `yeni_belge`, `belge_ac`, `_belge_penceresi`, `varsayilan_uygulama`
   (`open_selected`'ın hemen üstünde).
3. `main()`: konumsal `dosya` argümanı — PDF `lib.import_pdf` ile eklenir (aynı dosya özetiyle
   tanınır, kopya oluşmaz) ve mevcut `--open` akışıyla açılır / açık pencereye kuyruklanır.

**Bulunan ve düzeltilen tuzaklar (tekrarlama):**
- `QTextEdit` genişlik değişince (kaydırma çubuğu belirince) belgenin sayfa yüksekliğini -1
  yapar → sayfalama kapanır. Çözüm: kaydırma çubuğu hep açık + boyutlanmada sayfa boyutu yeniden.
- Koyu temada palet metni beyaz yapıyordu (beyaz sayfada görünmez); sayfa/metin rengi sabit.
- `offscreen` platformu PDF'e yazı tiplerini **şekil** olarak gömer (metin okunamaz); PDF metni
  testi gerçek platformda alt süreçte koşar.
- Aynı pytest sürecinde `QGuiApplication` sonra pencere açan testleri çökertir → `QApplication`.
- LibreOffice başsız dönüşüm paylaşılan profil kilidinde asılı kalabiliyor →
  `-env:UserInstallation=` ile ayrı profil (editörün "LibreOffice'te aç"ı normal pencere, etkilenmez).

Testler: `pytest tests` → 54 geçti, 1 atlandı. Editörün yazdığı .docx LibreOffice'te doğrulandı
(A4, üst bilgi, PAGE alanı, sayfa sonu, liste, birleştirilmiş hücre).

Bağımlılık: `python-docx==1.2.0` (requirements.txt).
