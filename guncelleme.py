"""Gunde en fazla bir anonim surum sorgusu; indirme/kurulum yapmaz."""
from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import threading
import time
from urllib.request import Request, urlopen


def surum_parcala(deger: str) -> tuple[int, int, int] | None:
    eslesme = re.fullmatch(r"v?(\d{1,6})\.(\d{1,6})\.(\d{1,6})(?:\+[A-Za-z0-9.-]+)?", str(deger))
    return tuple(map(int, eslesme.groups())) if eslesme else None


def _http(repo: str) -> dict:
    istek = Request(f"https://api.github.com/repos/ledaronn/{repo}/releases/latest",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "desktop-update-check"})
    with urlopen(istek, timeout=5) as yanit:
        return json.loads(yanit.read(1024 * 1024))


class Denetleyici:
    def __init__(self, depo: str, mevcut: str, dosya: Path, *, istek=None, saat=None):
        if depo not in ("pevrai", "okuma-atolyesi"):
            raise ValueError("Bilinmeyen guncelleme deposu")
        self.depo, self.mevcut, self.dosya = depo, surum_parcala(mevcut), Path(dosya)
        self._istek, self._saat = istek or _http, saat or time.time
        self._kilit = threading.Lock()
        self._bildirim = None
        self._calisiyor = False

    def _oku(self) -> dict:
        try:
            veri = json.loads(self.dosya.read_text(encoding="utf-8"))
            return veri if isinstance(veri, dict) else {}
        except (OSError, ValueError):
            return {}

    def _yaz(self, veri: dict) -> bool:
        gecici = None
        try:
            self.dosya.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.dosya.parent,
                                             prefix=".guncelleme-", delete=False) as f:
                gecici = Path(f.name)
                json.dump(veri, f, ensure_ascii=False)
            gecici.replace(self.dosya)
            return True
        except OSError:
            return False
        finally:
            if gecici is not None:
                try:
                    gecici.unlink(missing_ok=True)
                except OSError:
                    pass

    def _gosterilebilir(self, veri: dict) -> dict | None:
        etiket = veri.get("surum", "")
        yeni = surum_parcala(etiket)
        if self.mevcut and yeni and yeni > self.mevcut and etiket != veri.get("kapatilan"):
            return {"surum": etiket, "url": f"https://github.com/ledaronn/{self.depo}/releases"}
        return None

    def kontrol(self, acik: bool) -> dict | None:
        if not acik or self.mevcut is None:
            return None
        simdi = self._saat()
        with self._kilit:
            veri = self._oku()
            onceki = veri.get("son_kontrol")
            if isinstance(onceki, (int, float)) and simdi - onceki < 86400:
                self._bildirim = self._gosterilebilir(veri)
                return self._bildirim
            # Basarisiz sorgu da gunluk hakki kullanir. Yazilamazsa sorgu yapma.
            veri["son_kontrol"] = simdi
            veri.pop("surum", None)
            self._bildirim = None
            if not self._yaz(veri):
                return None
        try:
            yanit = self._istek(self.depo)
            etiket = yanit.get("tag_name", "") if isinstance(yanit, dict) else ""
            if not surum_parcala(etiket):
                return None
        except Exception:
            return None  # Cevrimdisi durum kullanici akisina hata tasimaz.
        with self._kilit:
            veri = self._oku()
            veri["surum"] = etiket
            if not self._yaz(veri):
                return None
            self._bildirim = self._gosterilebilir(veri)
            return self._bildirim

    def baslat(self, acik: bool) -> bool:
        if not acik:
            return False
        with self._kilit:
            if self._calisiyor:
                return False
            self._calisiyor = True
        def arka_plan():
            try:
                self.kontrol(True)
            finally:
                with self._kilit:
                    self._calisiyor = False
        threading.Thread(target=arka_plan, daemon=True, name="surum-denetimi").start()
        return True

    def bildirim(self, acik: bool) -> dict | None:
        with self._kilit:
            return dict(self._bildirim) if acik and self._bildirim else None

    def kapat(self, etiket: str) -> None:
        with self._kilit:
            if self._bildirim and self._bildirim["surum"] == etiket:
                veri = self._oku()
                veri["kapatilan"] = etiket
                self._yaz(veri)
                self._bildirim = None
