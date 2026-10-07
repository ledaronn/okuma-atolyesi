"""Testler arayüz metinlerini kaynak dilde (Türkçe) doğrular; sonuç kullanıcının
Windows diline ya da kayıtlı dil ayarına bağlı olmasın."""
import os
import pytest

os.environ.setdefault("OKUMA_DIL", "tr")


@pytest.fixture(autouse=True)
def guncelleme_agi_kapali(monkeypatch):
    """Qt testleri gercek GitHub'a baglanmaz; denetim testleri sahte HTTP kullanir."""
    from guncelleme import Denetleyici
    monkeypatch.setattr(Denetleyici, "baslat", lambda self, acik: False)
