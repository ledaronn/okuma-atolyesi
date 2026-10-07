"""Okuyucu surum kontrolu ve Qt bildirimi: gecici ayarlar, sahte HTTP."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from guncelleme import Denetleyici
from surum import SURUM
from test_gui import window,qt,env


@pytest.mark.parametrize('tag,expected',[('v1.2.0',True),('v1.1.0',False),('v1.0.9',False),('v2.0.0-beta',False)])
def test_surumu_dogrular(tmp_path,tag,expected):
    calls=[]
    def http(repo): calls.append(repo); return {'tag_name':tag}
    check=Denetleyici('okuma-atolyesi',SURUM,tmp_path/'update.json',istek=http,saat=lambda:200000)
    assert bool(check.kontrol(True)) is expected
    check.kontrol(True)
    assert calls==['okuma-atolyesi']


def test_kapali_ve_ag_hatasinda_sessiz(tmp_path):
    calls=[]
    def offline(repo): calls.append(repo); raise OSError('synthetic offline')
    check=Denetleyici('okuma-atolyesi',SURUM,tmp_path/'update.json',istek=offline,saat=lambda:200000)
    assert check.kontrol(False) is None and not calls
    assert check.kontrol(True) is None
    assert check.kontrol(True) is None and len(calls)==1


def test_bildirim_ve_ayar(window,tmp_path):
    w,lib,doc=window
    w._guncelleme=Denetleyici('okuma-atolyesi',SURUM,tmp_path/'update.json',istek=lambda repo:{'tag_name':'v1.2.0'},saat=lambda:200000)
    w._guncelleme.kontrol(True); w.guncelleme_goster()
    assert not w.guncelleme_cubugu.isHidden() and 'v1.2.0' in w.guncelleme_metni.text()
    w.guncelleme_eylemi.setChecked(False)
    assert not w.guncelleme_acik() and w.guncelleme_cubugu.isHidden()
    w.guncelleme_eylemi.setChecked(True)
    assert w.guncelleme_acik() and not w.guncelleme_cubugu.isHidden()
    w.guncelleme_kapa.click(); w.guncelleme_goster()
    assert w.guncelleme_cubugu.isHidden()
