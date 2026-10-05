# Ölçüm scriptleri (Aşama 1–2)

Uygulama kodunu değiştirmez; geçici bir veri klasöründe çalışır, gerçek `OkumaAtolyesiVeri` klasörüne dokunmaz.

```powershell
..\.venv\Scripts\python.exe uret.py       # kitap_200.pdf ve slayt_120.pdf üretir
..\.venv\Scripts\python.exe olc.py        # Aşama 1: render adımları + arayüz tıkanma ölçümü
..\.venv\Scripts\python.exe envanter.py   # Aşama 2: 12 aracı gerçek Qt olaylarıyla dener
```

Gerçek hoca slaytıyla da ölçmek için bu klasöre `slayt_gercek_metin.pdf` (metin tabanlı) ve
`slayt_gercek_goruntu.pdf` (görüntü tabanlı) adlarıyla iki PDF koy; yoksa atlanır.
Raporda kullanılan gerçek slaytlar `Documents` klasöründeki iki ders PDF'iydi; pakete kopyalanmadı.

Sonuçlar `RAPOR_ASAMA_1_2.md` içinde. Aşama 3 kabulü için `olc.py` aynı makinede tekrarlanır ve
"B. Arayüz" bölümündeki tıkanma satırları karşılaştırılır.
