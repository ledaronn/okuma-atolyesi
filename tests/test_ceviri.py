"""Arayüz dili: her metnin İngilizce karşılığı var, yer tutucular uyuşuyor ve
İngilizce açılan pencerelerde Türkçe metin kalmıyor."""
import ast
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import ceviri  # noqa: E402
from ceviri_en import EN  # noqa: E402

DOSYALAR = ["app.py", "core.py", "assistant_link.py", "belge/editor.py", "belge/docx_io.py", "belge/kayit.py"]
# Çalışma anında değişkenle çevrilen metinler (_t(degisken)): AST'de sabit olarak görünmez.
DINAMIK = {"Ana kütüphane", "Normal (2,5 cm)", "Dar (1,27 cm)", "Geniş (3,8 cm)"}
YER = re.compile(r"\{(\w+)\}")
TURKCE = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


def anahtarlar() -> set[str]:
    sonuc = set(DINAMIK)
    for f in DOSYALAR:
        for n in ast.walk(ast.parse((KOK / f).read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_t" and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                sonuc.add(n.args[0].value)
    return sonuc


def test_her_metnin_ingilizcesi_var():
    eksik = sorted(k for k in anahtarlar() if k not in EN)
    assert not eksik, f"{len(eksik)} metnin İngilizcesi yok: {eksik[:10]}"


def test_sozlukte_kullanilmayan_anahtar_yok():
    olu = sorted(set(EN) - anahtarlar())
    assert not olu, f"sözlükte kodda olmayan anahtar (metin değişmiş olabilir): {olu[:10]}"


def test_yer_tutucular_uyusuyor():
    hatali = [(k, v) for k, v in EN.items() if set(YER.findall(k)) != set(YER.findall(v))]
    assert not hatali, hatali[:5]


def test_ingilizce_ceviride_turkce_harf_yok():
    # Marka adı (Okuma Atölyesi) ve kasıtlı Türkçe örnekler dışında
    hatali = [(k, v) for k, v in EN.items() if TURKCE.search(v.replace("Okuma Atölyesi", ""))]
    assert not hatali, hatali[:5]


def test_yer_tutucu_tek_geciste_doldurulur():
    eski = ceviri._dil
    try:
        ceviri.dil_ayarla("en")
        # belge başlığı "{sayfa}" içerse bile ikinci kez işlenmez
        assert ceviri.t("{baslik} · sayfa {sayfa}\n{alinti}\n", baslik="{sayfa}", sayfa=3, alinti="x") == "{sayfa} · page 3\nx\n"
        assert ceviri.t("hiç çevrilmemiş metin") == "hiç çevrilmemiş metin"
        assert ceviri.buyuk("library") == "LIBRARY"
        ceviri.dil_ayarla("tr")
        assert ceviri.buyuk("kitaplık") == "KİTAPLIK"
    finally:
        ceviri._dil = eski


def test_dil_secimi_ayar_ve_ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("OKUMA_SETTINGS", str(tmp_path / "ayar.ini"))
    monkeypatch.delenv("OKUMA_DIL", raising=False)
    eski = ceviri._dil
    try:
        ceviri.dil_kaydet("en"); ceviri._dil = None
        assert ceviri.dil() == "en", "kayıtlı ayar okunur"
        ceviri.dil_kaydet("tr"); ceviri._dil = None
        assert ceviri.dil() == "tr"
        monkeypatch.setenv("OKUMA_DIL", "en"); ceviri._dil = None
        assert ceviri.dil() == "en", "ortam değişkeni ayarın önüne geçer"
    finally:
        ceviri._dil = eski


BETIK = textwrap.dedent(r"""
    import os, re, sys
    sys.path.insert(0, sys.argv[1])
    from PySide6.QtWidgets import QApplication, QWidget, QAbstractButton, QLabel, QLineEdit, QComboBox, QMenu, QGroupBox, QTabWidget, QTabBar
    from PySide6.QtGui import QAction
    app = QApplication([])
    import app as okuyucu
    from core import Library
    from belge.editor import BelgeEditoru
    lib = Library(sys.argv[2])
    w = okuyucu.Window(lib); w.show(); app.processEvents()
    e = BelgeEditoru(None); e.show(); app.processEvents()
    metinler = set()
    for kok in (w, e):
        for x in [kok] + kok.findChildren(QWidget):
            for al in ("text", "toolTip", "placeholderText", "windowTitle", "title"):
                f = getattr(x, al, None)
                try:
                    v = f() if callable(f) else None
                except TypeError:
                    v = None
                if isinstance(v, str) and v: metinler.add(v)
            if isinstance(x, QComboBox):
                metinler.update(x.itemText(i) for i in range(x.count()))
            if isinstance(x, QTabWidget):
                metinler.update(x.tabText(i) for i in range(x.count()))
            if isinstance(x, QTabBar):
                metinler.update(x.tabText(i) for i in range(x.count()))
        for a in kok.findChildren(QAction):
            metinler.update(v for v in (a.text(), a.toolTip()) if v)
        for m in kok.findChildren(QMenu):
            metinler.add(m.title())
            for a in m.actions():
                metinler.update(v for v in (a.text(), a.toolTip()) if v)
    for v in sorted(metinler):
        print(repr(v))
    sys.stdout.flush()
    os._exit(0)          # Qt nesnelerinin cikis sirasindaki yikimi bu test icin gereksiz (offscreen'de cokebiliyor)
""")


def test_ingilizce_pencerelerde_turkce_metin_kalmiyor(tmp_path):
    ortam = dict(os.environ, OKUMA_DIL="en", QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8",
                 OKUMA_SETTINGS=str(tmp_path / "ayar.ini"), OKUMA_LINK_DB=str(tmp_path / "link.sqlite3"),
                 APPDATA=str(tmp_path / "appdata"))
    r = subprocess.run([sys.executable, "-c", BETIK, str(KOK),  # "kitap" bir ceviri anahtari: kullanicinin verdigi kutuphane adi cevrilmemeli
                       str(tmp_path / "kitap")],
                       capture_output=True, text=True, encoding="utf-8", env=ortam, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    metinler = [ast.literal_eval(s) for s in r.stdout.splitlines() if s.strip()]
    assert len(metinler) > 80, f"pencere metinleri toplanamadı ({len(metinler)})"
    assert "Okuma Atölyesi — kitap" in metinler and not [m for m in metinler if "— book" in m], "kullanici kutuphane adi cevrilmemeli"
    kalan = [m for m in metinler if TURKCE.search(m.replace("Okuma Atölyesi", "").replace("Dil / Language", "").replace("Türkçe", ""))]
    assert not kalan, f"İngilizce arayüzde Türkçe kalan metin: {kalan}"
