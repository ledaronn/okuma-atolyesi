"""belge/kayit.py — Okuma Atölyesi'ni .pdf ve .docx için "Birlikte aç" adayı yapar.

YALNIZCA kullanıcı düzeyinde (HKCU, yönetici izni gerekmez) ve geri alınabilir:
`kaldir()` yazdığı her anahtarı siler. Windows 10/11 bir programın kendini
sessizce VARSAYILAN yapmasına izin vermez (UserChoice korumalı); program
kendini aday olarak kaydeder, son seçimi kullanıcı Ayarlar'da yapar —
`ayarlari_ac()` o sayfayı açar.

Yazılanlar (kok = "Software"; testlerde ayrı bir kök):
  Classes\\OkumaAtolyesi.PDF / .DOCX   ProgID: ad, simge, açma komutu
  Classes\\.pdf\\OpenWithProgids         "Birlikte aç" listesine giriş
  Classes\\.docx\\OpenWithProgids
  OkumaAtolyesi\\Capabilities            Varsayılan Uygulamalar sayfası için
  RegisteredApplications                 "Okuma Atölyesi" -> Capabilities
Mevcut varsayılan uygulamaya (UserChoice) DOKUNULMAZ.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK_DIZIN = Path(__file__).resolve().parent.parent
UYGULAMA = "Okuma Atölyesi"
PROGID = {".pdf": "OkumaAtolyesi.PDF", ".docx": "OkumaAtolyesi.DOCX"}
TUR_ADI = {".pdf": "PDF belgesi (Okuma Atölyesi)", ".docx": "Word belgesi (Okuma Atölyesi)"}


def komut() -> str:
    """Dosya açma komutu: konsolsuz pythonw + başlatıcı. Yollar sabit (bu
    klasör); kullanıcı verisinden program yolu alınmaz."""
    pythonw = KOK_DIZIN / ".venv" / "Scripts" / "pythonw.exe"
    return f'"{pythonw}" "{KOK_DIZIN / "ac.pyw"}" "%1"'


def _winreg():
    if sys.platform != "win32":
        raise OSError("Dosya ilişkilendirmesi yalnızca Windows'ta.")
    import winreg
    return winreg


def _yaz(winreg, yol: str, ad: str | None, deger: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, yol) as k:
        winreg.SetValueEx(k, ad or "", 0, winreg.REG_SZ, deger)


def kaydet(kok: str = "Software", uzantilar=(".pdf", ".docx")) -> None:
    winreg = _winreg()
    ikon = str(KOK_DIZIN / "okuma.ico")
    for uz in uzantilar:
        pid = PROGID[uz]
        _yaz(winreg, rf"{kok}\Classes\{pid}", None, TUR_ADI[uz])
        _yaz(winreg, rf"{kok}\Classes\{pid}\DefaultIcon", None, f"{ikon},0")
        _yaz(winreg, rf"{kok}\Classes\{pid}\shell\open\command", None, komut())
        _yaz(winreg, rf"{kok}\Classes\{uz}\OpenWithProgids", pid, "")
        _yaz(winreg, rf"{kok}\OkumaAtolyesi\Capabilities\FileAssociations", uz, pid)
    _yaz(winreg, rf"{kok}\OkumaAtolyesi\Capabilities", "ApplicationName", UYGULAMA)
    _yaz(winreg, rf"{kok}\OkumaAtolyesi\Capabilities", "ApplicationDescription",
         "PDF okuyucu ve kitaplık; Word belgesi düzenleyici.")
    _yaz(winreg, rf"{kok}\OkumaAtolyesi\Capabilities", "ApplicationIcon", f"{ikon},0")
    _yaz(winreg, rf"{kok}\RegisteredApplications", UYGULAMA, rf"{kok}\OkumaAtolyesi\Capabilities")
    _bildir()


def _sil_agac(winreg, yol: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, yol, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    alt = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _sil_agac(winreg, yol + "\\" + alt)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, yol)
    except FileNotFoundError:
        pass


def _sil_deger(winreg, yol: str, ad: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, yol, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, ad)
    except FileNotFoundError:
        pass


def kaldir(kok: str = "Software") -> None:
    """kaydet()'in yazdığı her şeyi siler; başka programların girişlerine dokunmaz."""
    winreg = _winreg()
    for uz, pid in PROGID.items():
        _sil_agac(winreg, rf"{kok}\Classes\{pid}")
        _sil_deger(winreg, rf"{kok}\Classes\{uz}\OpenWithProgids", pid)
    _sil_agac(winreg, rf"{kok}\OkumaAtolyesi")
    _sil_deger(winreg, rf"{kok}\RegisteredApplications", UYGULAMA)
    _bildir()


def kayitli_mi(kok: str = "Software") -> bool:
    try:
        winreg = _winreg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{kok}\Classes\{PROGID['.pdf']}\shell\open\command") as k:
            return winreg.QueryValueEx(k, "")[0] == komut()
    except OSError:
        return False


def _bildir() -> None:
    """Gezgin simge/ilişki önbelleğini tazelesin (SHChangeNotify)."""
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)     # SHCNE_ASSOCCHANGED
    except Exception:
        pass


def ayarlari_ac() -> None:
    """Windows Varsayılan Uygulamalar sayfası (Windows 11'de doğrudan bu uygulamanın sayfası)."""
    import os
    from urllib.parse import quote
    try:
        os.startfile("ms-settings:defaultapps?registeredAppUser=" + quote(UYGULAMA))
    except OSError:
        os.startfile("ms-settings:defaultapps")
