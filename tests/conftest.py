"""Testler arayüz metinlerini kaynak dilde (Türkçe) doğrular; sonuç kullanıcının
Windows diline ya da kayıtlı dil ayarına bağlı olmasın."""
import os

os.environ.setdefault("OKUMA_DIL", "tr")
