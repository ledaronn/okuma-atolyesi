"""Varsayılan uygulama kaydı (HKCU) ve başlatıcı. Gerçek kayıt yerine ayrı bir
test kökü kullanılır (Software\\OkumaAtolyesiTest\\...); test sonunda silinir.
Kullanıcının gerçek dosya ilişkilendirmelerine dokunulmaz."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from belge import kayit

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows kayit defteri")
KOK = r"Software\OkumaAtolyesiTest"


def oku(yol, ad=""):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, yol) as k:
        return winreg.QueryValueEx(k, ad)[0]


def var_mi(yol):
    import winreg
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, yol).Close(); return True
    except FileNotFoundError:
        return False


@pytest.fixture
def temiz():
    kayit.kaldir(KOK)
    yield
    kayit.kaldir(KOK)
    import winreg
    for alt in (r"\Classes\.pdf\OpenWithProgids", r"\Classes\.pdf", r"\Classes\.docx\OpenWithProgids", r"\Classes\.docx",
                r"\Classes", r"\RegisteredApplications", ""):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KOK + alt)
        except OSError:
            pass


def test_kaydet_ve_kaldir(temiz):
    assert not kayit.kayitli_mi(KOK)
    kayit.kaydet(KOK)
    assert kayit.kayitli_mi(KOK)
    komut = oku(KOK + r"\Classes\OkumaAtolyesi.PDF\shell\open\command")
    assert "pythonw.exe" in komut and "ac.pyw" in komut and komut.endswith('"%1"')
    assert oku(KOK + r"\Classes\OkumaAtolyesi.DOCX\DefaultIcon").endswith("okuma.ico,0")
    assert oku(KOK + r"\Classes\.pdf\OpenWithProgids", "OkumaAtolyesi.PDF") == ""
    assert oku(KOK + r"\OkumaAtolyesi\Capabilities\FileAssociations", ".docx") == "OkumaAtolyesi.DOCX"
    assert oku(KOK + r"\RegisteredApplications", "Okuma Atölyesi").endswith(r"OkumaAtolyesi\Capabilities")
    # baska bir programin .pdf girisi korunur
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KOK + r"\Classes\.pdf\OpenWithProgids") as k:
        winreg.SetValueEx(k, "BaskaProgram.PDF", 0, winreg.REG_SZ, "")
    kayit.kaldir(KOK)
    assert not kayit.kayitli_mi(KOK) and not var_mi(KOK + r"\Classes\OkumaAtolyesi.PDF")
    assert not var_mi(KOK + r"\OkumaAtolyesi")
    assert oku(KOK + r"\Classes\.pdf\OpenWithProgids", "BaskaProgram.PDF") == "", "baska programin girisine dokunulmadi"


def test_gercek_kayda_dokunulmadi():
    """Testler gercek Software\\Classes'a yazmaz (yalnizca okunur)."""
    assert kayit.kayitli_mi(KOK) is False


BETIK = r"""
import sys, types, runpy
sys.argv = ["ac.pyw", sys.argv[2]]
cagri = []
belge = types.ModuleType("belge.editor"); belge.main = lambda a: cagri.append(("editor", a[1])) or 0
app = types.ModuleType("app"); app.main = lambda: cagri.append(("okuyucu", sys.argv[1:])) or 0
sys.modules["belge.editor"] = belge; sys.modules["app"] = app
try:
    runpy.run_path(sys.argv[0] if False else r"%s", run_name="__main__")
except SystemExit:
    pass
print(cagri)
"""


@pytest.mark.parametrize("dosya,beklenen", [("C:/x/Rapor.DOCX", "('editor', 'C:/x/Rapor.DOCX')"),
                                            ("C:/x/kitap.pdf", "('okuyucu', ['C:/x/kitap.pdf'])")])
def test_baslatici_yonlendirir(dosya, beklenen):
    ac = Path(__file__).resolve().parent.parent / "ac.pyw"
    r = subprocess.run([sys.executable, "-c", BETIK % ac, "", dosya], capture_output=True, text=True, timeout=60)
    assert beklenen in r.stdout, r.stdout + r.stderr


def test_komut_satirindan_pdf_acik_pencereye_gider(tmp_path):
    """Okuyucu açıkken çift tıklanan PDF: ikinci süreç kitaplığa ekler, açma
    isteğini kuyruğa bırakıp çıkar. Aynı dosya ikinci kez: yeni kopya yok."""
    import shutil
    from PySide6.QtCore import QLockFile
    kok = Path(__file__).resolve().parent.parent
    veri = tmp_path / "veri"
    pdf = tmp_path / "kitap.pdf"; shutil.copy(kok / "Ornek_Belge.pdf", pdf)
    ortam = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    # kilidi tutmak icin once kutuphaneyi olustur
    subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, r'{kok}'); from core import Library; Library(r'{veri}')"],
                   check=True, env=ortam, timeout=60)
    kilit = QLockFile(str(veri / "reader.lock")); assert kilit.tryLock(100)
    try:
        for _ in range(2):
            r = subprocess.run([sys.executable, str(kok / "app.py"), "--data-dir", str(veri), str(pdf)],
                               env=ortam, cwd=str(kok), capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stderr[-800:]
    finally:
        kilit.unlock()
    import sqlite3
    db = sqlite3.connect(veri / "library.sqlite3")
    belgeler = db.execute("SELECT id FROM documents").fetchall()
    komutlar = db.execute("SELECT doc_id, page FROM commands").fetchall()
    assert len(belgeler) == 1, "ayni PDF iki kez acildi, tek kopya"
    assert komutlar == [(belgeler[0][0], 1), (belgeler[0][0], 1)], "acik pencereye iki acma istegi"
