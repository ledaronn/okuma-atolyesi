"""ceviri.py — arayüz dili (Türkçe / İngilizce).

Kaynak dil Türkçe: koddaki her kullanıcıya görünen metin t("...") içinden
geçer, anahtar Türkçe metnin kendisidir (gettext deseni, Pevrai ile aynı).
EN sözlüğünde karşılığı olmayan metin Türkçe kalır; tests/test_ceviri.py
eksik çeviriyi ve yer tutucu uyuşmazlığını yakalar.

Dil seçimi (öncelik sırasıyla):
  1. OKUMA_DIL ortam değişkeni (testler, alt süreçler)
  2. Kullanıcı ayarı (Araçlar ▾ → Dil / Language; QSettings 'dil')
  3. Windows görüntüleme dili: Türkçe ise Türkçe, değilse İngilizce
Dil değişikliği yeniden başlatınca uygulanır: açık pencerelerdeki metinler
kurulurken çevrildi.
"""
from __future__ import annotations

import os
import re

DILLER = ("tr", "en")
_dil: str | None = None
_YER = re.compile(r"\{(\w+)\}")


def _sistem_dili() -> str:
    try:
        from PySide6.QtCore import QLocale
        return "tr" if QLocale.system().language() == QLocale.Language.Turkish else "en"
    except Exception:
        return "en"


def _ayarlar():
    from PySide6.QtCore import QSettings
    yol = os.environ.get("OKUMA_SETTINGS")
    return QSettings(yol, QSettings.Format.IniFormat) if yol else QSettings("OkumaAtolyesi", "Okuyucu")


def dil() -> str:
    global _dil
    if _dil is None:
        ortam = os.environ.get("OKUMA_DIL")
        if ortam in DILLER:
            _dil = ortam
        else:
            try:
                kayitli = _ayarlar().value("dil", "")
            except Exception:
                kayitli = ""
            _dil = kayitli if kayitli in DILLER else _sistem_dili()
    return _dil


def dil_kaydet(kod: str) -> None:
    """Kullanıcı seçimini saklar; yeniden başlatınca geçerli olur."""
    if kod in DILLER:
        _ayarlar().setValue("dil", kod)


def dil_ayarla(kod: str) -> None:
    """Dili anlık değiştirir (testler)."""
    global _dil
    _dil = kod if kod in DILLER else "tr"


def t(metin: str, **yer) -> str:
    """Çevirir, sonra {ad} yer tutucularını TEK GEÇİŞTE doldurur: yerleştirilen
    değer (belge başlığı, alıntı) içinde "{...}" geçse bile yeniden işlenmez."""
    if dil() != "tr":
        metin = EN.get(metin, metin)
    if not yer:
        return metin
    return _YER.sub(lambda m: str(yer[m.group(1)]) if m.group(1) in yer else m.group(0), metin)


def buyuk(metin: str) -> str:
    """Büyük harf: Türkçede i→İ, ı→I (Python'un upper()'ı i'yi I yapar)."""
    if dil() == "tr":
        metin = metin.replace("i", "İ").replace("ı", "I")
    return metin.upper()


from ceviri_en import EN  # noqa: E402  (sözlük ayrı dosyada)
