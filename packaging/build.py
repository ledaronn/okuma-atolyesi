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

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dogrulama import ortam as dogrulama_ortami, pencere_dogrula, sorgula

KOK = Path(__file__).resolve().parent.parent
DIST = KOK / "dist" / "OkumaAtolyesi"
EXE = DIST / "OkumaAtolyesi.exe"
sys.path.insert(0, str(KOK))
from surum import SURUM
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


def dogrula() -> None:
    print("\n[2/3] Doğrulama (paketlenmiş exe ile)")
    with tempfile.TemporaryDirectory(prefix="okuma-build-check-") as tmp:
        _dogrula(dogrulama_ortami(Path(tmp)))


def _dogrula(ortam: dict[str, str]) -> None:

    print("  sayfa çizim süreci (--render-worker) ...")
    istek = {"id": 1, "path": str(KOK / "Ornek_Belge.pdf"), "page": 1,
             "scale": 0.5, "annotations": [], "alpha": False}
    baslik, veri = sorgula([str(EXE), "--render-worker"], istek, env=ortam, ikili_alan="n")
    if (baslik.get("id") != 1 or baslik.get("version") != SURUM or "error" in baslik or
        any(type(baslik.get(k)) is not int or baslik[k] <= 0 for k in ("w", "h", "stride", "channels")) or
        baslik["channels"] not in (3, 4) or baslik["stride"] < baslik["w"] * baslik["channels"] or
        len(veri) != baslik["h"] * baslik["stride"]):
        raise SystemExit("Sayfa üretim sürecinin yanıtı geçersiz.")
    print(f"    {baslik['w']}x{baslik['h']} piksel üretildi")

    print("  MCP sunucusu (--mcp) ...")
    istek = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "build", "version": "0"}}}
    yanit, _ = sorgula([str(EXE), "--mcp"], istek, env=ortam)
    if yanit.get("id") != 1 or not isinstance(yanit.get("result"), dict) or "serverInfo" not in yanit["result"]:
        raise SystemExit("MCP sunucusu initialize'a geçerli cevap vermedi.")
    print("    initialize -> serverInfo var")

    print("  okuyucu penceresi (offscreen, 8 sn ayakta kalmalı) ...")
    pencere_dogrula([str(EXE)], env=dict(ortam, QT_QPA_PLATFORM="offscreen"))
    print("    açık")
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
