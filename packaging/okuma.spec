# -*- mode: python ; coding: utf-8 -*-
# okuma.spec — PyInstaller tarifi. Calistir: python packaging/build.py
#
# Tek klasor (onedir), tek exe: OkumaAtolyesi.exe (konsolsuz). Okuyucu,
# belge editoru, sayfa cizim sureci ve MCP sunucusu ayni exe'nin kipleri
# (bkz. okuma_giris.py). onefile degil: her acilista kendini gecici klasore
# acmasin; kurulum programi (Inno Setup) zaten tek tik kurulum veriyor.
#
# VERI BEYAZ LISTE: klasor toptan alinmaz. Kullanici verisi (kitaplik,
# veri_yolu.txt) pakete girmez; %USERPROFILE%\OkumaAtolyesiVeri ve
# %APPDATA%\OkumaAtolyesi altinda calisma aninda olusur.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

KOK = Path(SPECPATH).resolve().parent

datas = [
    (str(KOK / "okuma.ico"), "."),
    (str(KOK / "Ornek_Belge.pdf"), "."),
    (str(KOK / "LICENSE"), "."),
]
datas += collect_data_files("pymupdf")
datas += collect_data_files("docx")          # python-docx sablonlari (default.docx)

hiddenimports = [
    "app", "core", "server", "render_worker", "assistant_link",
    "belge", "belge.editor", "belge.docx_io", "belge.kayit",
    *collect_submodules("mcp", filter=lambda ad: not ad.startswith("mcp.cli")), "pymupdf", "docx",
]

a = Analysis([str(KOK / "okuma_giris.py")], pathex=[str(KOK)], binaries=[], datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
             excludes=["tkinter", "pytest", "IPython", "PySide6.QtWebEngineCore",
                       "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
                       "PySide6.QtQml", "PySide6.QtMultimedia"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="OkumaAtolyesi",
          icon=str(KOK / "okuma.ico"), console=False, upx=False, strip=False)
coll = COLLECT(exe, a.binaries, a.datas, name="OkumaAtolyesi", upx=False, strip=False)
