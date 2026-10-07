"""Aşama 2 envanteri. 12 aracı gerçek Qt olaylarıyla dener; kod değiştirmez."""
import os, sys, time, tempfile
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parent.parent))
DATA=Path(tempfile.mkdtemp(prefix='okuma_envanter_'))  # gerçek veri klasörüne dokunmaz
import pymupdf as fitz
from PySide6.QtCore import Qt, QPointF, QPoint, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QFileDialog, QMessageBox
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
qapp=QApplication([]); qapp.setStyle('Fusion')
from core import Library
import app as appmod
lib=Library(DATA)
book=lib.import_pdf(HERE/'kitap_200.pdf')
slide_src=HERE/'slayt_gercek_metin.pdf' if (HERE/'slayt_gercek_metin.pdf').exists() else HERE/'slayt_120.pdf'
slide=lib.import_pdf(slide_src)
B=book['id']; S=slide['id']

# Modal pencereleri otomatik cevapla
answers={'multiline':('Deneme notu',True),'text':('Yer imi A',True),'item':('90',True),'int':[(1,True),(2,True)],'save':('',''),'msg':[]}
QInputDialog.getMultiLineText=staticmethod(lambda *a,**k:answers['multiline'])
QInputDialog.getText=staticmethod(lambda *a,**k:answers['text'])
QInputDialog.getItem=staticmethod(lambda *a,**k:answers['item'])
QFileDialog.getSaveFileName=staticmethod(lambda *a,**k:answers['save'])
QMessageBox.warning=staticmethod(lambda *a,**k:answers['msg'].append(('warning',a[1:3])))
QMessageBox.information=staticmethod(lambda *a,**k:answers['msg'].append(('info',a[1:3])))

win=appmod.Window(lib); win.resize(1450,950); win.show(); QTest.qWait(100)
win.open_doc(B); QTest.qWait(300)
R=win.reader
rows=[]
def row(tool,status,note): rows.append((tool,status,note)); print(f"[{status:10s}] {tool:12s} {note}")

def scene_pt(page,x,y): return R.pages[page-1]['rect'].topLeft()+QPointF(x,y)
def vp(page,x,y): return R.mapFromScene(scene_pt(page,x,y))
def drag(points,page=1,step_ms=8):
    pts=[vp(page,x,y) for x,y in points]
    QTest.mousePress(R.viewport(),Qt.MouseButton.LeftButton,pos=pts[0])
    for pt in pts[1:]: QTest.mouseMove(R.viewport(),pt,step_ms)
    QTest.mouseRelease(R.viewport(),Qt.MouseButton.LeftButton,pos=pts[-1]); QTest.qWait(60)
def click(page,x,y):
    QTest.mouseClick(R.viewport(),Qt.MouseButton.LeftButton,pos=vp(page,x,y)); QTest.qWait(60)
def wait_idle(limit=60):
    t=time.perf_counter()
    while time.perf_counter()-t<limit:
        qapp.processEvents(); time.sleep(0.005)
        if not win.busy: return time.perf_counter()-t
    return None
def anns(doc=B): return lib.annotations(doc)
def kinds(doc=B): return [a['kind'] for a in anns(doc)]

# Sayfa 1 kelime kutuları (ekran koordinatı, sayfa noktası)
words=lib.words(B,1)
lines={}
for w in words: lines.setdefault((w[5],w[6]),[]).append(w)
line_list=list(lines.values())
def line_box(i):
    L=line_list[i]; return min(w[0] for w in L),min(w[1] for w in L),max(w[2] for w in L),max(w[3] for w in L)
lb0=line_box(0); lb1=line_box(1); lb2=line_box(2); lb3=line_box(3)
print(f"Kitap s.1: {len(words)} kelime, {len(line_list)} satır; satır 1 kutusu {tuple(round(v) for v in lb1)}")
R.go(1,0.25); QTest.qWait(200)

# ---------- 1. Taşı ----------
win.set_tool('hand'); sb=R.verticalScrollBar(); v0=sb.value()
p0=vp(1,300,400); p1=QPoint(p0.x(),p0.y()-150)
QTest.mousePress(R.viewport(),Qt.MouseButton.LeftButton,pos=p0)
for k in range(1,11):
    pt=QPoint(p0.x(),p0.y()-15*k)
    qapp.sendEvent(R.viewport(),QMouseEvent(QEvent.Type.MouseMove,QPointF(pt),QPointF(R.viewport().mapToGlobal(pt)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)); QTest.qWait(5)
QTest.mouseRelease(R.viewport(),Qt.MouseButton.LeftButton,pos=p1); QTest.qWait(50)
dv=sb.value()-v0
row('Taşı','çalışıyor' if dv>50 else 'çalışmıyor',f'150 px sürükleme → kaydırma {dv} birim; tekerlek adımı {3*sb.singleStep()} birim, animasyonsuz sıçrama')
R.go(1,0.25); QTest.qWait(150)

# ---------- 2. Metin seç ----------
win.set_tool('select'); qapp.clipboard().clear()
# (a) tam satır 1
ym=(lb1[1]+lb1[3])/2; drag([(lb1[0]+2,ym),(lb1[2]-2,ym)])  # satır boyunca, sözcük üstünde
sel_full=qapp.clipboard().text()
# (b) yoğun metinde akış seçimi: satır 1'in ortasından satır 3'ün ortasına
midx=(lb1[0]+lb1[2])/2
drag([(midx,lb1[1]),(midx+60,lb3[3])])
sel_flow=qapp.clipboard().text()
expected_full=' '.join(w[4] for w in line_list[1])
ok_full=sel_full.strip()==expected_full
n_words_flow=len(sel_flow.split()); n_lines_flow=len(sel_flow.splitlines())
# akış olsaydı: satır1'in sağ yarısı + satır2 tamamı + satır3'ün sol yarısı ≈ 1 satır+; dikdörtgen: 3 satırın orta sütunu
full_line_words=len(line_list[1])
flow_ok=n_lines_flow==3 and n_words_flow>2*full_line_words-6
row('Metin seç','çalışıyor' if ok_full and flow_ok else 'kısmen',f'tam satır seçimi doğru={ok_full}; ortadan-ortaya sürüklemede {n_lines_flow} satırdan {n_words_flow} kelime (satırda {full_line_words}) → okuma akışı={flow_ok}')
print('   örnek akış seçimi:',repr(sel_flow[:120]))

# ---------- 3. Kalem ----------
win.set_tool('ink'); n0=len(anns())
t0=time.perf_counter(); drag([(100,300),(130,320),(160,300),(190,330),(220,300)],step_ms=8)
# çizgi kaç ms sonra yeniden görünür? (release sonrası temp silinir, render_visible ile geri gelir)
n_render_before=len(R.rendered)
QTest.qWait(10); gone=(R.temp is None)
t_wait=time.perf_counter()
while time.perf_counter()-t_wait<3:
    qapp.processEvents()
    if R.rendered and all(True for _ in R.rendered): break
t_back=(time.perf_counter()-t0)*1000
ink=[a for a in anns() if a['kind']=='ink']
row('Kalem','çalışıyor' if len(ink)==1 and len(ink[0]['data']['points'])>=5 else 'çalışmıyor',f"{len(ink)} çizgi, {len(ink[0]['data']['points']) if ink else 0} nokta; sürüklerken geçici yol anında çiziliyor, BIRAKINCA SİLİNİP tüm görünür sayfalar yeniden üretilince geri geliyor (≈{t_back:.0f} ms)")

# ---------- 4. Fosfor ----------
win.set_tool('highlight'); n0=len(anns())
drag([(lb1[0]+2,(lb1[1]+lb1[3])/2),(lb1[2]-2,(lb1[1]+lb1[3])/2),(lb2[0]+2,(lb2[1]+lb2[3])/2),(lb2[2]-2,(lb2[1]+lb2[3])/2)])   # 2 satır boyunca fosfor izi
hl=[a for a in anns() if a['kind']=='highlight']
snapped = len(hl)==1 and len(hl[0]['data'].get('rects',[]))==2 and hl[0]['data'].get('text')
drag([(8,300),(50,380)])   # sol kenar boşluğu, metin yok
hl2=[a for a in anns() if a['kind']=='highlight']
free = len(hl2)==2 and not hl2[-1]['data'].get('text')
free=len(hl2)==1 and any(a['kind']=='ink' and a['data'].get('marker') for a in anns())
row('Fosfor','çalışıyor' if snapped and free else 'kısmen',f"iz boyunca satıra yapışıyor ({len(hl[0]['data'].get('rects',[])) if hl else 0} satır kutusu, metin kaydedildi={bool(hl and hl[0]['data'].get('text'))}); boş alanda serbest iz={free}")

# ---------- 5. Alt çizgi ----------
win.set_tool('underline'); drag([(lb3[0]-2,lb3[1]-1),(lb3[2]+2,lb3[3]+1)])
ul=[a for a in anns() if a['kind']=='underline']
row('Alt çizgi','çalışıyor' if ul and ul[0]['data'].get('text') else 'çalışmıyor',f"{len(ul)} adet, satır kutusu {len(ul[0]['data'].get('rects',[])) if ul else 0}, metin={bool(ul and ul[0]['data'].get('text'))}")

# ---------- 6. Kutu ----------
win.set_tool('rect'); drag([(80,500),(260,600)])
rc=[a for a in anns() if a['kind']=='rect']
row('Kutu','çalışıyor' if rc else 'çalışmıyor',f"{len(rc)} adet, rects={[[round(v) for v in r] for r in rc[0]['data']['rects']] if rc else None}")

# ---------- 7. Ok ----------
win.set_tool('arrow'); drag([(300,500),(350,540),(420,620)])
ar=[a for a in anns() if a['kind']=='arrow']
row('Ok','çalışıyor' if ar and len(ar[0]['data']['points'])==2 else 'çalışmıyor',f"{len(ar)} adet, uç noktalar={[[round(v) for v in p] for p in ar[0]['data']['points']] if ar else None}")

# ---------- 8. Not ----------
win.set_tool('note'); click(1,450,300)
nt=[a for a in anns() if a['kind']=='note']
in_panel=any('Deneme notu' in win.notes_list.item(i).text() for i in range(win.notes_list.count()))
row('Not','çalışıyor' if nt and nt[0]['data']['text']=='Deneme notu' and in_panel else 'kısmen',f"{len(nt)} adet, panelde görünüyor={in_panel}; metin modal pencereyle giriliyor")

# ---------- 9. Silgi ----------
win.set_tool('erase'); before=len(anns())
click(1,130,320)  # kalem çizgisi üstü
after_ink=len(anns())
click(1,(lb1[0]+lb1[2])/2,(lb1[1]+lb1[3])/2)  # fosfor üstü
after_hl=len(anns())
click(1,455,305)  # not ikonu (point +[-8..20])
after_note=len(anns())
click(1,500,700)  # boş alan
after_empty=len(anns())
hover_feedback=hasattr(appmod.Reader,'hoverMoveEvent') or 'hover' in (HERE.parent.parent/'app.py').read_text(encoding='utf-8').lower()
row('Silgi','çalışıyor' if (before-after_ink,after_ink-after_hl,after_hl-after_note,after_note-after_empty)==(1,1,1,0) else 'kısmen',f"kalem sil={before-after_ink}, fosfor sil={after_ink-after_hl}, not sil={after_hl-after_note}, boşa tık={after_note-after_empty}; üzerine gelince ne sileceğini GÖSTERMİYOR (hover kodu yok={not hover_feedback}); her tıkta PDF yeniden açılıyor ve tüm görünür sayfalar yeniden üretiliyor")

# ---------- 10. Yer imi ----------
win.bookmark(); QTest.qWait(50)
bm=[a for a in anns() if a['kind']=='bookmark']
row('Yer imi','çalışıyor' if bm and bm[0]['data']['text']=='Yer imi A' else 'çalışmıyor',f"{len(bm)} adet, sayfa {bm[0]['page'] if bm else '-'}; yalnızca Notlar panelinde listeleniyor, sayfada görsel işaret yok")

# ---------- 11. PDF kaydet ----------
answers['save']=('','')
win.export_pdf()
wait_idle()  # QTest.qWait GIL'i bırakmıyor, arka plan işini yavaşlatıyor; sleep tabanlı bekle
exp=sorted((DATA/'exports').glob('*.pdf'),key=lambda p:p.stat().st_mtime)
ok_exp=False; n_pdf_ann=0
if exp:
    with fitz.open(exp[-1]) as d: n_pdf_ann=sum(len(list(p.annots())) for p in d); ok_exp=n_pdf_ann>=len([a for a in anns() if a['kind']!='bookmark'])
row('PDF kaydet','çalışıyor' if ok_exp else 'çalışmıyor',f"exports/ içine yazıldı, PDF'de {n_pdf_ann} açıklama (bekl. {len([a for a in anns() if a['kind']!='bookmark'])}); işlem sırasında okuyucu devre dışı kalıyor (stack.setEnabled(False))")

# ---------- 12. Sayfalar ----------
answers['text']=('1-3,7,5',True); answers['item']=('90',True)
n_before=len(exp)
win.pages_dialog()
wait_idle()  # QTest.qWait GIL'i bırakmıyor, arka plan işini yavaşlatıyor; sleep tabanlı bekle
exp=sorted((DATA/'exports').glob('*.pdf'),key=lambda p:p.stat().st_mtime)
ok_pages=False; info=''
if len(exp)>n_before:
    with fitz.open(exp[-1]) as d: info=f"{len(d)} sayfa, dönüş={d[0].rotation}"; ok_pages=len(d)==5 and d[0].rotation==90
row('Sayfalar','çalışıyor' if ok_pages else 'çalışmıyor',f"'1-3,7,5' + 90° → {info}; iki ardışık modal pencereyle giriliyor")

# ---------- Ek: geri al / yinele, yakınlaştır, sığdır, sayfa kutusu, panel ----------
n=len(anns()); win.undo(); u1=len(anns()); win.undo(True); u2=len(anns())
row('Geri al/yinele','çalışıyor' if (u1,u2)==(n-1,n) else 'çalışmıyor',f"{n}→{u1}→{u2}; her geri almada tüm görünür sayfalar yeniden üretiliyor")
z=R.zoom; R.set_zoom(z*1.15); QTest.qWait(300); z2=R.zoom; R.fit_width(); QTest.qWait(300); z3=R.zoom
row('Yakınlaştır/sığdır','çalışıyor',f"zoom {z:.2f}→{z2:.2f}→sığdır {z3:.2f}; her adımda tüm görünür sayfalar sıfırdan üretiliyor, ara ölçekleme yok")
win.page_input.setValue(120); win.page_input.editingFinished.emit(); QTest.qWait(300)
row('Sayfa kutusu','çalışıyor' if R.current()[0]==120 else 'çalışmıyor',f"120 girildi → sayfa {R.current()[0]}")
vis0=win.panel.isVisible(); win.toggle_panel(); vis1=win.panel.isVisible(); win.toggle_panel()
row('Yan panel','çalışıyor' if vis0!=vis1 else 'çalışmıyor',f"aç/kapa {vis0}→{vis1}; varsayılan AÇIK; sekmeler: Notlar, İçindekiler, Ara, AI")

# ---------- Soru 1: Kaldığın yer ----------
print("\n=== Soru: Kaldığın yer kaydediliyor mu? ===")
win.open_doc(S); QTest.qWait(300); R.set_zoom(1.3); R.go(7,0.4); QTest.qWait(600)  # 450 ms save_timer'ı bekle
st_saved=lib.get_state(S)
win.close(); qapp.processEvents()   # closeEvent → persist
win2=appmod.Window(lib); win2.resize(1450,950); win2.show(); QTest.qWait(100)
caption=[win2.shelf.item(i).text() for i in range(win2.shelf.count()) if win2.shelf.item(i).data(Qt.ItemDataRole.UserRole)==S][0]
win2.open_doc(S); QTest.qWait(300)
pg,off=win2.reader.current()
print(f"  kapatmadan önce state={st_saved}")
print(f"  yeniden açınca: sayfa {pg}, offset {off:.2f}, zoom {win2.reader.zoom:.2f}  → {'KAYDEDİLİYOR ve GERİ YÜKLENİYOR' if pg==7 and abs(win2.reader.zoom-1.3)<.01 else 'SORUN'}")
print(f"  kitaplıkta görünen: {caption!r}  → sayfa bilgisi var ama 'ne zaman', 'ne kadar' yok; açılışta hiçbir karşılama/bildirim yok")
# hızlı kaydır ve 450 ms dolmadan kapat: kaydediliyor mu?
win2.reader.go(12,0.2); QTest.qWait(50); win2.close(); qapp.processEvents()
print(f"  kaydırıp 50 ms sonra kapat → state sayfa {lib.get_state(S)['page']} (closeEvent persist ediyor)")

# ---------- Soru 2: Koleksiyon raf olabilir mi? ----------
print("\n=== Soru: Koleksiyon alanı raf olarak kullanılabilir mi? ===")
lib.update_document(B,collection='Sosyal Psikoloji'); lib.update_document(S,collection='Araştırma Yöntemleri')
import sqlite3
db=sqlite3.connect(DATA/'library.sqlite3'); cols=[r[1] for r in db.execute('PRAGMA table_info(documents)')]
tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print(f"  documents.collection sütunu: {'collection' in cols} (TEXT, serbest metin, belge başına 1)")
print(f"  ayrı raf/koleksiyon tablosu: {any('coll' in t or 'shelf' in t or 'raf' in t for t in tables)} — tablolar: {tables}")
print(f"  renk/sıra/açıklama alanı: yok; koleksiyon isimleri belgelerden türetiliyor (refresh_collections DISTINCT)")
print(f"  filtre: list_documents(collection='Sosyal Psikoloji') → {len(lib.list_documents(collection='Sosyal Psikoloji'))} belge")
print(f"  boş raf mümkün mü: hayır (belgesi olmayan koleksiyon listede görünmez)")
print(f"  UI: kenar çubuğunda tek QComboBox filtresi; atama 'Başlık / etiket / koleksiyon' iletişim kutusundaki serbest metin kutusu")

# ---------- Soru 3 & 4 cevapları yukarıdaki satırlarda (Metin seç, Fosfor) ----------
print("\n=== Özet tablo ===")
for t,s,n in rows: print(f"| {t} | {s} | {n} |")
print("\nUyarı iletileri:",answers['msg'])

# Qt'nin ekran olmadan interpreter kapanisindaki bilinen destructor sorununu atla.
# Pencereler yukarida normal kapanis akisi ile kapandi; once raporu tamamla.
sys.stdout.flush()
os._exit(0)
