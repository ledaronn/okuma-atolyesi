"""Masaüstüne "Okuma Atölyesi" kısayolu (.lnk) kurar.

    .venv\\Scripts\\python.exe kisayol.py

.lnk doğrudan bu klasörün .venv\\Scripts\\pythonw.exe'sini hedefler: konsol
penceresi yok, ikon var (okuma.ico), başlangıç konumu bu klasör — app.py
veri klasörünü ve veri_yolu.txt'yi buradan bulur. baslat.bat terminalden
hata görmek için kalıyor; çift tık için kısayol.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHONW = HERE / ".venv" / "Scripts" / "pythonw.exe"
IKON = HERE / "okuma.ico"
APP = HERE / "app.py"


def masaustu() -> Path:
    cikti = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True, text=True, check=True).stdout.strip()
    return Path(cikti)


def kur(hedef_klasor: Path | None = None) -> Path:
    if not PYTHONW.exists():
        raise SystemExit(f"Sanal ortam yok: {PYTHONW}\nÖnce kur.bat çalıştırın.")
    if not IKON.exists():
        raise SystemExit(f"İkon yok: {IKON}")
    lnk = (hedef_klasor or masaustu()) / "Okuma Atölyesi.lnk"
    for y in (lnk, PYTHONW, HERE, IKON, APP):
        if "'" in str(y):
            raise SystemExit(f"Yolda tek tırnak var, kısayol yazılamadı: {y}")
    betik = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
        f"$s.TargetPath = '{PYTHONW}'; "
        f"$s.Arguments = '\"{APP}\"'; "
        f"$s.WorkingDirectory = '{HERE}'; "
        f"$s.IconLocation = '{IKON},0'; "
        f"$s.Description = 'Okuma Atölyesi — PDF kütüphanesi'; "
        f"$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", betik], check=True)
    return lnk


if __name__ == "__main__":
    yol = kur()
    print(f"Kısayol yazıldı: {yol}")
    print(f"  hedef : {PYTHONW} \"{APP}\"")
    sys.exit(0)
