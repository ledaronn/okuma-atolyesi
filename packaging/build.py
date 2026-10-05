"""packaging/build.py — Windows dağıtımı: PyInstaller (onedir) + isteğe bağlı Inno Setup.

    python packaging/build.py            # dist/OkumaAtolyesi/OkumaAtolyesi.exe
    python packaging/build.py --kurulum  # + dist/OkumaAtolyesi-Setup-<sürüm>.exe (Inno Setup gerekir)

Her adımın sonunda paketlenmiş exe ile doğrulama var: sayfa çizim süreci
gerçek bir PDF sayfası üretiyor mu, MCP sunucusu initialize'a cevap veriyor
mu, okuyucu penceresi açılıp ayakta kalıyor mu. Doğrulanmayan paket
"üretildi" sayılmaz. Doğrulama kullanıcının gerçek verisine dokunmaz
(APPDATA, USERPROFILE geçici klasöre yönlendirilir).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
DIST = KOK / "dist" / "OkumaAtolyesi"
EXE = DIST / "OkumaAtolyesi.exe"
SURUM = "1.1.0"
ISCC_ADAYLARI = [Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
                 Path(r"C:\Program Files\Inno Setup 6\ISCC.exe")]


def calistir(komut, **kw):
    print("  $", " ".join(str(k) for k in komut))
    return subprocess.run(komut, check=True, cwd=str(KOK), **kw)


def pyinstaller() -> None:
    print("\n[1/3] PyInstaller")
    for eski in (KOK / "build" / "okuma", DIST):
        shutil.rmtree(eski, ignore_errors=True)
    calistir([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
              "--distpath", str(KOK / "dist"), "--workpath", str(KOK / "build"),
              str(KOK / "packaging" / "okuma.spec")])
    if not EXE.is_file():
        raise SystemExit(f"URETILEMEDI: {EXE}")
    mb = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file()) / 1_000_000
    print(f"  dist/OkumaAtolyesi: {mb:.0f} MB")


def _ortam() -> dict:
    gecici = KOK / "build" / "dogrulama"
    shutil.rmtree(gecici, ignore_errors=True)
    (gecici / "appdata").mkdir(parents=True)
    (gecici / "ev").mkdir()
    return dict(os.environ, APPDATA=str(gecici / "appdata"), USERPROFILE=str(gecici / "ev"),
                OKUMA_DATA_DIR=str(gecici / "veri"), OKUMA_LINK_DB=str(gecici / "link.sqlite3"),
                OKUMA_SETTINGS=str(gecici / "ayarlar.ini"))


def dogrula() -> None:
    print("\n[2/3] Doğrulama (paketlenmiş exe ile)")
    ortam = _ortam()

    print("  sayfa çizim süreci (--render-worker) ...")
    p = subprocess.Popen([str(EXE), "--render-worker"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=ortam)
    try:
        istek = {"id": 1, "path": str(KOK / "Ornek_Belge.pdf"), "page": 1, "scale": 0.5, "annotations": [], "alpha": False}
        p.stdin.write((json.dumps(istek) + "\n").encode()); p.stdin.flush()
        baslik = json.loads(p.stdout.readline() or b"{}")
        if "error" in baslik or not baslik.get("n"):
            raise SystemExit(f"Sayfa üretilemedi: {baslik}\n{p.stderr.read()[-1500:]!r}")
        veri = p.stdout.read(baslik["n"])
        if len(veri) != baslik["n"]:
            raise SystemExit("Sayfa verisi eksik geldi.")
        print(f"    {baslik['w']}x{baslik['h']} piksel üretildi")
    finally:
        p.kill()

    print("  MCP sunucusu (--mcp) ...")
    p = subprocess.Popen([str(EXE), "--mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=ortam)
    try:
        p.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05",'
                      b'"capabilities":{},"clientInfo":{"name":"build","version":"0"}}}\n')
        p.stdin.flush()
        bas, satir = time.monotonic(), b""
        while time.monotonic() - bas < 60:
            satir = p.stdout.readline()
            if satir.strip():
                break
        if b'"result"' not in satir or b"serverInfo" not in satir:
            raise SystemExit(f"MCP sunucusu cevap vermedi: {satir[:300]!r}\n{p.stderr.read()[-1500:]!r}")
        print("    initialize -> " + satir.decode("utf-8", "replace")[:100].strip() + " ...")
    finally:
        p.kill()

    print("  okuyucu penceresi (offscreen, 8 sn ayakta kalmalı) ...")
    p = subprocess.Popen([str(EXE)], env=dict(ortam, QT_QPA_PLATFORM="offscreen"),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        time.sleep(8)
        if p.poll() is not None:
            raise SystemExit(f"Okuyucu kapandı (çıkış {p.returncode}): {p.stderr.read()[-1500:]!r}")
        print("    açık")
    finally:
        p.kill()
    print("  DOGRULANDI")


def inno() -> None:
    print("\n[3/3] Inno Setup")
    iscc = next((a for a in ISCC_ADAYLARI if a.is_file()), None) or shutil.which("iscc")
    if iscc is None:
        raise SystemExit("Inno Setup 6 bulunamadı (winget install JRSoftware.InnoSetup).")
    calistir([str(iscc), f"/DSurum={SURUM}", f"/DKok={KOK}", str(KOK / "packaging" / "okuma.iss")])
    cikti = KOK / "dist" / f"OkumaAtolyesi-Setup-{SURUM}.exe"
    if not cikti.is_file():
        raise SystemExit(f"Kurulum paketi üretilemedi: {cikti}")
    print(f"  {cikti} ({cikti.stat().st_size / 1_000_000:.0f} MB)")


if __name__ == "__main__":
    if "--yalniz-dogrula" not in sys.argv:
        pyinstaller()
    dogrula()
    if "--kurulum" in sys.argv:
        inno()
    print("\nTamam.")
