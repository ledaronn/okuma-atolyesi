# Ölçüm scriptleri (Aşama 1–2)

Uygulama kodunu değiştirmez; geçici bir veri klasöründe çalışır, gerçek `OkumaAtolyesiVeri` klasörüne dokunmaz.

```powershell
# Depo kökünden:
.\.venv\Scripts\python.exe docs\olcum\uret.py       # sentetik PDF'leri üretir
.\.venv\Scripts\python.exe docs\olcum\olc.py        # render + arayüz tıkanma ölçümü
.\.venv\Scripts\python.exe docs\olcum\envanter.py   # araçları gerçek Qt olaylarıyla dener
```

Gerçek hoca slaytıyla da ölçmek için bu klasöre `slayt_gercek_metin.pdf` (metin tabanlı) ve
`slayt_gercek_goruntu.pdf` (görüntü tabanlı) adlarıyla iki PDF koy; yoksa atlanır.
Raporda kullanılan gerçek slaytlar `Documents` klasöründeki iki ders PDF'iydi; pakete kopyalanmadı.

Sonuçlar [ölçüm raporunda](../RAPOR_ASAMA_1_2.md). Aşama 3 kabulü için `olc.py` aynı makinede tekrarlanır ve
"B. Arayüz" bölümündeki tıkanma satırları karşılaştırılır.
