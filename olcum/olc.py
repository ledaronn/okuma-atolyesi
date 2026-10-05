"""Aşama 1 ölçümü. Paket kodunu değiştirmez; yalnızca sarmalayıp zamanlar."""
import os, sys, time, math, tempfile, statistics as st
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parent))
DATA=Path(tempfile.mkdtemp(prefix='okuma_olcum_'))  # gerçek veri klasörüne dokunmaz
import pymupdf as fitz
from PySide6.QtCore import QTimer, Qt, QPoint, QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QWheelEvent
qapp=QApplication([]); qapp.setStyle('Fusion')
from core import Library
import app as appmod
lib=Library(DATA)

def ms(t): return f"{t*1000:7.1f} ms"
def stats(xs): return f"ort {st.mean(xs)*1000:6.1f} | medyan {st.median(xs)*1000:6.1f} | maks {max(xs)*1000:6.1f} ms (n={len(xs)})"

docs={}
for name in ('kitap_200','slayt_120','slayt_gercek_metin','slayt_gercek_goruntu'):
    if not (HERE/f'{name}.pdf').exists(): print(f'atlandı: {name}.pdf yok'); continue
    t=time.perf_counter(); d=lib.import_pdf(HERE/f'{name}.pdf'); docs[name]=d['id']
    print(f"içe alma {name}: {ms(time.perf_counter()-t)}  ({d['pages']} sayfa)")

# ================= B. Arayüz =================
print("\n=== B. Arayüz: gerçek Window (offscreen 1450x950) ===")
win=appmod.Window(lib); win.resize(1450,950); win.show(); qapp.processEvents()

calls={'render_visible':[], 'lib.render':[]}
orig_rv=appmod.Reader.render_visible
def rv(self):
    t=time.perf_counter(); orig_rv(self); calls['render_visible'].append(time.perf_counter()-t)
appmod.Reader.render_visible=rv
import threading
main_thread=threading.get_ident(); render_threads=set()
orig_render=Library.render
def rend(self,doc_id,page,scale=1.5):
    t=time.perf_counter(); r=orig_render(self,doc_id,page,scale); calls['lib.render'].append((page,time.perf_counter()-t)); render_threads.add(threading.get_ident()); return r
Library.render=rend
import core
if hasattr(core,'PageRenderer'):  # Aşama 3 sonrası yol: işçi iş parçacığında üretim
    orig_pr=core.PageRenderer.render
    def prend(self,page,scale):
        t=time.perf_counter(); r=orig_pr(self,page,scale); calls['lib.render'].append((page,time.perf_counter()-t)); render_threads.add(threading.get_ident()); return r
    core.PageRenderer.render=prend

# UI tıkanma: her processEvents() çağrısının süresi. >16 ms = kaçan kare(ler).
gaps=[]; paints=[]
orig_paint=appmod.Reader.paintEvent
def pe(self,e):
    t=time.perf_counter(); orig_paint(self,e); paints.append(time.perf_counter()-t)
appmod.Reader.paintEvent=pe
def pump(sec):
    end=time.perf_counter()+sec
    while time.perf_counter()<end:
        t=time.perf_counter(); qapp.processEvents(); d=time.perf_counter()-t
        if d>0.016: gaps.append(d)
        time.sleep(0.001)

def reset(): calls['render_visible'].clear(); calls['lib.render'].clear(); gaps.clear(); paints.clear()

def wheel(reader,steps=1,ctrl=False):
    vp=reader.viewport(); pos=QPointF(vp.width()/2,vp.height()/2)
    mods=Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    e=QWheelEvent(pos,vp.mapToGlobal(pos.toPoint()).toPointF(),QPoint(0,0),QPoint(0,-120*steps),Qt.MouseButton.NoButton,mods,Qt.ScrollPhase.NoScrollPhase,False)
    qapp.sendEvent(vp,e)

def gapline():
    g=f"tıkanma {len(gaps)} kez, toplam {sum(gaps)*1000:.0f} ms, en uzun {max(gaps)*1000:.0f} ms" if gaps else "tıkanma yok"
    p=f" | boyama {len(paints)} kez, {stats(paints)}" if paints else ""
    return g+p

for name,doc_id in docs.items():
    n=lib.document(doc_id)['pages']
    print(f"\n--- {name} ({n} sayfa) ---")
    reset(); t=time.perf_counter(); win.open_doc(doc_id); pump(0.3); t_open=time.perf_counter()-t
    r=win.reader; sb=r.verticalScrollBar()
    print(f"  açılış (open_doc + ilk render): {ms(t_open)} | ilk render_visible {len(calls['lib.render'])} sayfa üretti: {[p for p,_ in calls['lib.render']]} | {gapline()}")
    print(f"  görünen pencere yüksekliği {r.viewport().height()} px, zoom {r.zoom:.2f}, sayfa yüksekliği {r.pages[0]['rect'].height():.0f} birim")
    v0=sb.value(); wheel(r); qapp.processEvents(); print(f"  1 tekerlek tıkı = {sb.value()-v0} birim kaydırma (singleStep={sb.singleStep()})")
    # Hızlı kaydırma: 120 tık, 8 ms ara
    reset(); t=time.perf_counter()
    for i in range(120): wheel(r); pump(0.008)
    during=(len(calls['render_visible']),len(calls['lib.render']),len(gaps),sum(gaps),len(paints),sum(paints))
    pump(0.6); total=time.perf_counter()-t
    rv_x=calls['render_visible']; rd=calls['lib.render']
    print(f"  hızlı kaydırma 120 tık ({sb.value()-v0} birim): toplam {ms(total)}")
    print(f"     KAYDIRMA SIRASINDA: render_visible {during[0]} çağrı, lib.render {during[1]} sayfa, tıkanma {during[2]} kez/{during[3]*1000:.0f} ms, boyama {during[4]} kez/{during[5]*1000:.0f} ms")
    print(f"     DURDUKTAN SONRA: render_visible {len(rv_x)-during[0]} çağrı, lib.render {len(rd)-during[1]} sayfa, tıkanma {len(gaps)-during[2]} kez/{(sum(gaps)-during[3])*1000:.0f} ms")
    print(f"     render_visible {len(rv_x)} çağrı: {stats(rv_x) if rv_x else '-'}")
    print(f"     lib.render {len(rd)} sayfa, sayfa başına {stats([d for _,d in rd]) if rd else '-'}")
    rerender=len(rd)-len(set(p for p,_ in rd)); print(f"     aynı sayfa tekrar üretildi: {rerender} kez | {gapline()}")
    # Yavaş kaydırma: 40 tık, 60 ms ara (okurken)
    reset(); t=time.perf_counter()
    for i in range(40): wheel(r); pump(0.06)
    pump(0.3)
    rv_x=calls['render_visible']; rd=calls['lib.render']
    print(f"  yavaş kaydırma 40 tık: render_visible {len(rv_x)} çağrı | lib.render {len(rd)} sayfa | {gapline()}")
    # Genişliğe sığdır (gerçekçi okuma yakınlığı)
    reset(); t=time.perf_counter(); r.fit_width(); pump(0.6); tf=time.perf_counter()-t; rd=calls['lib.render']
    print(f"  genişliğe sığdır (zoom {r.zoom:.2f}): {ms(tf)} | {len(rd)} sayfa üretildi, sayfa başına {stats([d for _,d in rd]) if rd else '-'} | {gapline()}")
    reset()
    for i in range(40): wheel(r); pump(0.06)
    pump(0.3); rd=calls['lib.render']
    print(f"  bu yakınlıkta yavaş kaydırma 40 tık: lib.render {len(rd)} sayfa, sayfa başına {stats([d for _,d in rd]) if rd else '-'} | {gapline()}")
    # Yakınlaştırma
    reset(); t=time.perf_counter(); wheel(r,ctrl=True); pump(0.4); tz=time.perf_counter()-t; rd=calls['lib.render']
    print(f"  Ctrl+tekerlek 1 adım (zoom {r.zoom:.2f}): {ms(tz)} | {len(rd)} sayfa yeniden üretildi | {gapline()}")
    # Sayfa atlama
    reset(); t=time.perf_counter(); r.go(n//2); pump(0.4); tg=time.perf_counter()-t; rd=calls['lib.render']
    print(f"  sayfa atlama →{n//2}: {ms(tg)} | {len(rd)} sayfa üretildi | {gapline()}")
    # İşaretleme sonrası
    reset(); lib.add_annotation(doc_id,n//2,'rect',{'rects':[[50,50,200,120]],'color':'#dea53b','width':2}); r.refresh_annotations(); pump(0.4); rd=calls["lib.render"]
    print(f"  tek işaretleme sonrası (katman): {len(rd)} sayfa yeniden üretildi | {gapline()}")
    tot=sum(it.pixmap().width()*it.pixmap().height()*4 for it in r.rendered.values())
    print(f"  bellekte tutulan sayfa görüntüsü: {len(r.rendered)} sayfa, ≈{tot/1e6:.0f} MB")
print(f"\nÜretim iş parçacığı: {'yalnızca UI DIŞI' if render_threads and main_thread not in render_threads else 'UI iş parçacığında'} ({len(render_threads)} farklı iş parçacığı)")
win.close()
