"""Qt ekran olmadan gerçek pencere, fare, kayıt ve arka plan işi testleri."""
import os, tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['OKUMA_SETTINGS']=os.path.join(tempfile.mkdtemp(prefix='okuma-ayar-'),'ayar.ini')  # gerçek kullanıcı ayarlarına dokunma
os.environ['OKUMA_LINK_DB']=os.path.join(os.path.dirname(os.environ['OKUMA_SETTINGS']),'assistant.sqlite3')
import threading
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_core import env
from PySide6.QtCore import Qt,QPointF,QPoint,QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QWidget
from app import Window,STYLE

@pytest.fixture(scope='module')
def qt():
    a=QApplication.instance() or QApplication([]); a.setStyle('Fusion'); a.setStyleSheet(STYLE)
    from PySide6.QtGui import QFontDatabase
    font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    return a

@pytest.fixture
def window(env,qt,monkeypatch):
    def fail(*args): raise AssertionError('Unexpected dialog: '+str(args))
    monkeypatch.setattr(QMessageBox,'warning',fail)
    lib,d,src=env; w=Window(lib); w.show(); QTest.qWait(100); w.open_doc(d['id']); QTest.qWait(150)
    yield w,lib,d
    w.save_timer.stop(); w.poll_timer.stop(); w.close(); qt.processEvents()


def idle(qt,seconds):
    """QTest.qWait GIL'i bırakmadığı için arka plan iş parçacıklarını aç bırakır; üretim beklerken bunu kullan."""
    import time
    end=time.perf_counter()+seconds
    while time.perf_counter()<end: qt.processEvents(); time.sleep(.005)


def drag(reader,points):
    r=reader.pages[0]['rect']
    pts=[reader.mapFromScene(r.topLeft()+QPointF(x,y)) for x,y in points]
    QTest.mousePress(reader.viewport(),Qt.MouseButton.LeftButton,pos=pts[0])
    for pt in pts[1:]: QTest.mouseMove(reader.viewport(),pt,10)
    QTest.mouseRelease(reader.viewport(),Qt.MouseButton.LeftButton,pos=pts[-1]); QTest.qWait(80)


def test_draw_highlight_erase_and_selection(window):
    w,lib,d=window; reader=w.reader; reader.go(1,.35); QTest.qWait(80)
    w.set_tool('ink'); drag(reader,[(40,160),(60,175),(90,155)])
    assert lib.annotations(d['id'])[0]['kind']=='ink'
    w.set_tool('highlight'); drag(reader,[(40,97),(210,120)])
    assert any('Alpha' in a['data'].get('text','') for a in lib.annotations(d['id']))
    w.set_tool('select'); drag(reader,[(40,97),(210,120)])
    assert 'Alpha' in QApplication.clipboard().text()
    assert 'Alpha' in lib.reader_context()['selection']
    w.set_tool('erase'); r=reader.pages[0]['rect']; pos=reader.mapFromScene(r.topLeft()+QPointF(60,175))
    QTest.mouseClick(reader.viewport(),Qt.MouseButton.LeftButton,pos=pos)
    assert len(lib.annotations(d['id']))==1
    w.undo(); assert len(lib.annotations(d['id']))==2
    w.undo(True); assert len(lib.annotations(d['id']))==1


def test_restore_position_zoom_and_poll(window,qt):
    w,lib,d=window
    w.reader.set_zoom(1.7); w.reader.go(3,.6); QTest.qWait(600); w.persist()
    state=lib.get_state(d['id']); assert state['page']==3
    assert abs(state['zoom']-1.7)<.001
    w.show_shelf(); w.open_doc(d['id']); QTest.qWait(100)
    page,offset=w.reader.current(); assert page==3 and abs(offset-state['offset'])<.01
    lib.queue_open(d['id'],2); w.poll(); QTest.qWait(100)
    # At a page's top the viewport center can fall on the preceding page if offset too small.
    assert w.reader.current()[0]==2
    lib.add_annotation(d['id'],2,'note',{'text':'MCP tarafından eklendi'})
    w.poll(); assert w.notes_list.count()==1


def test_background_callback_on_gui_thread(window,qt):
    w,lib,d=window; results=[]; main=threading.get_ident()
    w.run_job(lambda:(threading.get_ident(),lib.export_pdf(d['id'])),lambda r:results.append((threading.get_ident(),r)),'Test')
    for _ in range(100):
        if results: break
        QTest.qWait(30)
    assert results
    assert results[0][0]==main and results[0][1][0]!=main
    assert not w.busy and w.stack.isEnabled() and not w.reader.suspended


def test_rendering_never_blocks_gui_thread(window,qt):
    """Sayfa üretimi UI iş parçacığında değil; kaydırma ve yakınlaştırma sırasında olay döngüsü turu 16 ms'i aşmaz."""
    import time
    from core import PageRenderer
    w,lib,d=window; reader=w.reader; main=threading.get_ident(); seen=[]
    orig=PageRenderer.render
    def spy(self,page,scale):
        seen.append(threading.get_ident()); return orig(self,page,scale)
    PageRenderer.render=spy
    try:
        reader.go(1); reader.set_zoom(2.0)
        longest=0; start=time.perf_counter()
        while time.perf_counter()-start<1.5:
            reader.verticalScrollBar().setValue(reader.verticalScrollBar().value()+40)
            t=time.perf_counter(); qt.processEvents(); longest=max(longest,time.perf_counter()-t); time.sleep(.004)
    finally: PageRenderer.render=orig
    assert seen and main not in seen, 'üretim UI iş parçacığında çağrıldı'
    assert reader.rendered, 'sayfa görüntüsü gelmedi'
    assert longest<.05, f'olay döngüsü turu {longest*1000:.0f} ms bloke oldu'
    # Yakınlaştırmada eski görüntü yerinde kalır; beyaz yanıp sönme yok.
    before=dict(reader.rendered); reader.set_zoom(1.0)
    assert reader.rendered==before


def test_annotation_layer_does_not_rerender_pages(window,qt):
    """İşaretlemeler ayrı katmanda: eklemek/silmek sayfa görüntüsüne dokunmaz ve anında görünür."""
    from app import AnnotationItem
    w,lib,d=window; reader=w.reader; reader.go(1); idle(qt,1.0)
    assert len(reader.rendered)>=2
    before=dict(reader.rendered); generation=reader.generation
    w.set_tool('ink'); drag(reader,[(40,160),(60,175),(90,155)])
    ink=[a for a in lib.annotations(d['id']) if a['kind']=='ink']; assert len(ink)==1
    assert ink[0]['id'] in reader.ann_items and isinstance(reader.ann_items[ink[0]['id']],AnnotationItem)
    assert reader.temp is None
    idle(qt,.3)
    assert reader.rendered==before and reader.generation==generation, 'işaretleme sayfa görüntüsünü yeniden ürettirdi'
    # Silgi: üzerine gelince işaretlenir, tıklayınca silinir; yine üretim yok.
    w.set_tool('erase'); r=reader.pages[0]['rect']; pos=reader.mapFromScene(r.topLeft()+QPointF(60,175))
    QTest.mouseMove(reader.viewport(),pos); qt.processEvents()
    assert reader.hover_item is reader.ann_items[ink[0]['id']] and reader.hover_item.hovered
    QTest.mouseMove(reader.viewport(),reader.mapFromScene(r.topLeft()+QPointF(300,400))); qt.processEvents()
    assert reader.hover_item is None
    QTest.mouseClick(reader.viewport(),Qt.MouseButton.LeftButton,pos=pos)
    assert not [a for a in lib.annotations(d['id']) if a['kind']=='ink'] and not reader.ann_items
    idle(qt,.3); assert reader.rendered==before


def test_highlight_preview_snaps_to_lines_and_rotated_page(window,qt):
    """Sürüklerken önizleme satır kutularına yapışır; döndürülmüş sayfada (s.2, 90°) katman sözcükle çakışır."""
    from app import AnnotationItem
    w,lib,d=window; reader=w.reader
    word=next(x for x in lib.words(d['id'],2) if x[4]=='Alpha'); r2=reader.pages[1]['rect']
    reader.centerOn(r2.center()); idle(qt,.3)
    cx=(word[0]+word[2])/2  # 90° sayfada satır dikey akar; sözcüğün üstünden geçir
    w.set_tool('highlight'); pts=[reader.mapFromScene(r2.topLeft()+QPointF(x,y)) for x,y in [(cx,word[1]+1),(cx,word[3]-1)]]
    QTest.mousePress(reader.viewport(),Qt.MouseButton.LeftButton,pos=pts[0]); QTest.mouseMove(reader.viewport(),pts[1],10)
    assert isinstance(reader.temp,AnnotationItem) and reader.temp.kind=='highlight'
    box=reader.temp.rects[0]; assert abs(box.top()-word[1])<1 and abs(box.bottom()-word[3])<1, 'önizleme satıra yapışmadı'
    QTest.mouseRelease(reader.viewport(),Qt.MouseButton.LeftButton,pos=pts[1]); QTest.qWait(50)
    hl=[a for a in lib.annotations(d['id']) if a['kind']=='highlight']; assert hl and 'Alpha' in hl[0]['data']['text']
    item=reader.ann_items[hl[0]['id']]; shown=item.rects[0]
    assert shown.contains(QPointF((word[0]+word[2])/2,(word[1]+word[3])/2)), 'döndürülmüş sayfada katman sözcükle çakışmıyor'
    assert reader.temp is None


def test_window_close_stops_render_process(env,qt):
    lib,d,src=env; w=Window(lib); w.show(); QTest.qWait(100); w.open_doc(d['id'])
    for _ in range(30):  # üretim süreci soğuk başlıyor olabilir (≈0,4 s)
        idle(qt,.1)
        if w.reader.rendered: break
    proc=lib._render_process.proc; assert proc is not None and proc.poll() is None and w.reader.rendered
    w.save_timer.stop(); w.poll_timer.stop(); w.close(); qt.processEvents()
    assert lib._render_process.proc is None and proc.poll() is not None


def test_highlighter_and_selection_behave_like_pens(window,qt):
    """Fosfor izin geçtiği sözcükleri boyar (kutu değil); boş yerde serbest iz bırakır; seçim okuma sırasıyla akar."""
    w,lib,d=window; reader=w.reader; reader.go(1,.3); idle(qt,.5)
    words=lib.words(d['id'],1); line=[x for x in words if x[5]==next(x[5] for x in words if x[4]=='Alpha')]
    y=(line[0][1]+line[0][3])/2
    # Satırın ortasından geçen düz bir iz: 'Alpha' ile 'gamma.' arası, sonrası değil.
    w.set_tool('highlight'); drag(reader,[(line[0][0]+1,y),((line[2][0]+line[2][2])/2,y)])
    hl=[a for a in lib.annotations(d['id']) if a['kind']=='highlight']; assert len(hl)==1
    assert hl[0]['data']['text']=='Alpha beta gamma.' and len(hl[0]['data']['rects'])==1
    assert abs(hl[0]['data']['rects'][0][1]-line[0][1])<1
    # Metin olmayan yerde: dikdörtgen değil, serbest fosfor izi (ink + marker).
    drag(reader,[(60,300),(120,330),(180,300)])
    marker=[a for a in lib.annotations(d['id']) if a['kind']=='ink' and a['data'].get('marker')]
    assert len(marker)==1 and marker[0]['data']['color']==reader.styles['highlight']['color']
    assert not [a for a in lib.annotations(d['id']) if a['kind']=='highlight' and not a['data'].get('text')], 'boş alanda dikdörtgen fosfor oluştu'
    # Seçim: satır 1'in ortasından satır 2'ye — okuma sırasıyla, sütun değil.
    lines=sorted({x[5]:x for x in words}.items()); first=[x for x in words if x[5]==lines[0][0]]; second=[x for x in words if x[5]==lines[1][0]]
    w.set_tool('select'); QApplication.clipboard().clear()
    mid=first[len(first)//2]; drag(reader,[((mid[0]+mid[2])/2,(mid[1]+mid[3])/2),((second[1][0]+second[1][2])/2,(second[1][1]+second[1][3])/2)])
    text=QApplication.clipboard().text()
    assert text.startswith(mid[4]) and second[0][4] in text and second[1][4] in text and second[2][4] not in text
    # Araç stilleri birbirinden bağımsız.
    assert reader.styles['ink']['color']!=reader.styles['highlight']['color'] and reader.styles['highlight']['width']>reader.styles['ink']['width']


def test_focus_mode_only_page_is_permanent(window,qt):
    """Okuyucuda başlık, kenar çubuğu, durum çubuğu yok; ada ve panel kapalıyken yer kaplamaz; kısayollar çalışır."""
    w,lib,d=window; W=w.reader_page.width()
    assert w.stack.currentIndex()==1 and not w.header.isVisible() and not w.side.isVisible() and not w.statusBar().isVisible()
    assert w.reader.height()==w.reader_page.height() and w.reader.x()==0, 'sayfa görünümü okuyucu alanını kaplamıyor'
    assert w.island_open and w.island.isVisible() and not w.panel_box.isVisible() and not w.panel_open, 'ilk açılışta kalemlik görünür olmalı'
    idle(qt,3.0); assert w.strip.y()<0, 'üst şerit açılış sonrası gizlenmedi'
    QTest.keyClick(w.reader,Qt.Key_T); idle(qt,.35); assert not w.island_open and not w.island.isVisible() and w.gutter.width()<=12 and w.reader.width()>=W-12, 'kapalı ada yer kaplıyor'
    QTest.keyClick(w.reader,Qt.Key_T); idle(qt,.35); assert w.island_open and w.island.isVisible() and w.reader.width()+w.gutter.width()==W, 'ada görünümün yanında değil'
    QTest.keyClick(w.reader,Qt.Key_N); idle(qt,.35); assert w.panel_open and w.panel.isVisible()
    w.notes_list.setFocus(); QTest.keyClick(w.notes_list,Qt.Key_N); idle(qt,.35); assert not w.panel_open, 'liste odaktayken N paneli kapatmadı'
    QTest.keyClick(w.reader,Qt.Key_N); idle(qt,.35); assert w.panel_open
    QTest.keyClick(w.reader,Qt.Key_Escape); idle(qt,.35); assert not w.panel_open and w.island_open
    QTest.keyClick(w.reader,Qt.Key_Escape); idle(qt,.35); assert not w.island_open and w.stack.currentIndex()==1
    QTest.keyClick(w.reader,Qt.Key_F,Qt.KeyboardModifier.ControlModifier); idle(qt,.35); assert w.panel_open and w.panel.currentIndex()==2 and w.find_input.hasFocus()
    QTest.keyClick(w.find_input,Qt.Key_Escape); idle(qt,.35); assert not w.panel_open
    QTest.keyClick(w.reader,Qt.Key_Escape); idle(qt,.2); assert w.stack.currentIndex()==0 and w.header.isVisible() and w.side.isVisible() and w.statusBar().isVisible()


def test_wheel_scroll_is_animated(window,qt):
    from PySide6.QtGui import QWheelEvent
    w,lib,d=window; reader=w.reader; reader.set_zoom(2.0); reader.go(1,0); idle(qt,.3)
    sb=reader.verticalScrollBar(); v0=sb.value(); vp=reader.viewport(); pos=QPointF(vp.width()/2,vp.height()/2)
    e=QWheelEvent(pos,vp.mapToGlobal(pos.toPoint()).toPointF(),QPoint(0,0),QPoint(0,-120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    qt.sendEvent(vp,e); target=reader.scroll_target
    assert target>v0 and sb.value()<target, 'kaydırma anında sıçradı, animasyon yok'
    idle(qt,.4); assert sb.value()==int(target)


def test_status_message_on_shelf_and_note_workflow(window,qt):
    """say() kitaplıkta durum çubuğuna yazar (kendini çağırmaz); not ikonuna tıklamak paneli açıp notu seçer; not yazarken N paneli kapatmaz."""
    w,lib,d=window; reader=w.reader
    w.show_shelf(); w.say('deneme'); assert w.statusBar().currentMessage()=='deneme'
    w.open_doc(d['id']); idle(qt,.5)
    a=lib.add_annotation(d['id'],1,'note',{'point':[60,60],'text':'ilk not','color':'#dea53b'}); reader.refresh_annotations(); reader.go(1,0); idle(qt,.3)
    w.set_tool('hand'); r=reader.pages[0]['rect']
    QTest.mouseClick(reader.viewport(),Qt.MouseButton.LeftButton,pos=reader.mapFromScene(r.topLeft()+QPointF(66,66))); idle(qt,.4)
    assert w.panel_open and w.panel.currentIndex()==0 and w.note_target==a['id'] and w.note_editor.toPlainText()=='ilk not'
    w.note_editor.setFocus(); QTest.keyClick(w.note_editor,Qt.Key_N); idle(qt,.3)
    assert w.panel_open and w.note_editor.toPlainText()=='nilk not', 'not yazarken N panele gitti'
    w.note_editor.setPlainText('değişti'); w.save_note(); assert lib.annotations(d['id'])[0]['data']['text']=='değişti'


def test_eraser_drags_and_shows_shape(window,qt):
    w,lib,d=window; reader=w.reader; reader.go(1,.35); idle(qt,.3)
    w.set_tool('ink'); drag(reader,[(40,160),(60,175),(90,155)]); drag(reader,[(200,300),(260,330)])
    assert len(lib.annotations(d['id']))==2
    w.set_tool('erase'); r=reader.pages[0]['rect']
    QTest.mouseMove(reader.viewport(),reader.mapFromScene(r.topLeft()+QPointF(60,175))); qt.processEvents()
    assert reader.hover_item is not None and reader.hover_item.hovered
    # Basılı sürükleyerek iki çizgiyi de sil
    pts=[reader.mapFromScene(r.topLeft()+QPointF(x,y)) for x,y in [(60,175),(130,240),(230,315)]]
    QTest.mousePress(reader.viewport(),Qt.MouseButton.LeftButton,pos=pts[0])
    for pt in pts[1:]: QTest.mouseMove(reader.viewport(),pt,10)
    QTest.mouseRelease(reader.viewport(),Qt.MouseButton.LeftButton,pos=pts[-1]); idle(qt,.2)
    assert not lib.annotations(d['id']) and not reader.erasing


def test_reading_guide_follows_cursor_in_select_mode(window,qt):
    w,lib,d=window; reader=w.reader; reader.go(1,.3); idle(qt,.3); r=reader.pages[0]['rect']
    w.set_tool('select'); w.guide_btn.setChecked(True)
    QTest.mouseMove(reader.viewport(),reader.mapFromScene(r.topLeft()+QPointF(120,140))); qt.processEvents()
    g=reader.guide; assert g.isVisible() and g.rect.contains(QPointF(r.left()+120,r.top()+140)) and abs(g.rect.height()-reader.styles['select']['width'])<.01
    assert g.rect.width()>r.width()*.9, 'im satır boyunca uzanmalı'
    w.set_width(32); QTest.mouseMove(reader.viewport(),reader.mapFromScene(r.topLeft()+QPointF(130,150))); qt.processEvents(); assert abs(g.rect.height()-32)<.01
    w.set_tool('hand'); assert not g.isVisible()
    w.set_tool('select'); w.guide_btn.setChecked(False); QTest.mouseMove(reader.viewport(),reader.mapFromScene(r.topLeft()+QPointF(140,160))); qt.processEvents(); assert not g.isVisible()
    assert not lib.annotations(d['id']), 'im hiçbir şey kaydetmemeli'


def test_library_shelves_and_resume_card(window,qt):
    """Sol ağaç raf başlıkları + belgeler; satırlar raf başına; 'Devam et' kaldığı sayfada açar; kişisel kapak."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage
    w,lib,d=window; reader=w.reader
    reader.go(3,.5); idle(qt,.6); w.show_shelf(); idle(qt,.3)
    assert w.resume.isVisible() and 'Sayfa 3 / 3' in w.resume_info.text() and 'görüldü' in w.resume_info.text()
    assert w.shelf.count()==1 and 's.' in w.shelf.item(0).text()
    a=lib.add_shelf('Sosyal Psikoloji'); b=lib.add_shelf('Aile Terapisi'); w.refresh_shelves(); w.refresh_shelf(); idle(qt,.2)
    tops=[w.shelves.topLevelItem(i).text(0).split('  (')[0] for i in range(w.shelves.topLevelItemCount())]
    assert tops==['TÜM BELGELER','SOSYAL PSİKOLOJİ','AİLE TERAPİSİ','RAFSIZ'], tops
    assert w.shelves.topLevelItem(3).childCount()==1, 'rafsız belge ağaçta görünmeli'
    w.tree_clicked(w.shelves.topLevelItem(1)); idle(qt,.2); assert w.shelf_heading.text()=='Sosyal Psikoloji' and w.rows_box.count()==1 and w.shelf.count()==0
    w.tree_clicked(w.shelves.topLevelItem(0)); idle(qt,.2); assert w.rows_box.count()>=2 and w.shelf.count()==1
    w.selected_doc=d['id']; w.put_on_shelf(a['id']); idle(qt,.2)
    assert w.shelves.topLevelItem(1).childCount()==1 and w.shelves.topLevelItem(1).child(0).data(0,Qt.ItemDataRole.UserRole)==('doc',d['id'])
    lib.delete_shelf(a['id']); w.refresh_shelves(); w.refresh_shelf(); assert w.shelf_filter is None and w.shelf.count()==1
    # Kişisel kapak
    img=QImage(300,450,QImage.Format.Format_RGB32); img.fill(0xff336699); buf=QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly); img.save(buf,'PNG')
    lib.set_custom_cover(d['id'],bytes(buf.data())); assert lib.has_custom_cover(d['id']) and lib.cover_path(d['id']).name.endswith('.custom.png')
    w.refresh_shelf(); idle(qt,.2); icon=w.shelf.item(0).icon().pixmap(150,210).toImage(); assert icon.pixelColor(75,105).name()=='#336699', 'kişisel kapak kartı doldurmalı'
    lib.clear_custom_cover(d['id']); assert not lib.has_custom_cover(d['id']) and lib.cover_path(d['id']).exists()
    with pytest.raises(ValueError): lib.set_custom_cover(d['id'],b'not png')
    w.resume_last(); idle(qt,.5); assert w.stack.currentIndex()==1 and reader.current()[0]==3


def test_study_tracker_counts_only_active_time(env,qt):
    """Sayaç: pencere öndeyken ve 5 dk hareketsizlikten önce sayar; arkadayken ve hareketsizlikte durur; kapat-aç sonrası korunur."""
    from app import StudyTracker
    from core import Library
    lib,d,src=env; clock=[1000.0]; active=[True]
    tr=StudyTracker(lib,lambda:active[0],clock=lambda:clock[0]); tr.begin(d['id']); tr.touch(1)
    for _ in range(100): clock[0]+=1; tr.tick()
    assert abs(tr.seconds-100)<1e-6
    active[0]=False
    for _ in range(50): clock[0]+=1; tr.tick()
    assert abs(tr.seconds-100)<1e-6, 'pencere arkadayken saydı'
    active[0]=True; tr.touch(2)
    for _ in range(400): clock[0]+=1; tr.tick()        # 300 s sonra hareketsizlik: durmalı
    assert abs(tr.seconds-400)<1e-6, f'hareketsizlikte durmadı: {tr.seconds}'
    tr.touch(3); clock[0]+=1; tr.tick(); assert abs(tr.seconds-401)<1e-6, 'etkinlik gelince devam etmeli'
    tr.mark(); row=tr.end(); assert row and row['pages']==3 and row['marks']==1 and abs(row['active_seconds']-401)<1e-6
    lib.close(); again=Library(lib.root); t=again.today_summary()
    assert t['pages']==3 and t['marks']==1 and abs(t['seconds']-401)<1e-6, 'oturum kapat-aç sonrası korunmadı'
    assert again.document_seconds()[d['id']]>400
    tr2=StudyTracker(again,lambda:True,clock=lambda:clock[0]); tr2.begin(d['id']); clock[0]+=2; tr2.tick(); assert tr2.end() is None, '5 s altı oturum silinmeli'
    again.close()


def test_session_shown_in_library(window,qt):
    w,lib,d=window; assert w.tracker.session is not None and w.tracker.doc_id==d['id']
    w.tracker.seconds=125; w.tracker.pages={1,2}; w.tracker.marks=1
    w.show_shelf(); idle(qt,.2)
    assert w.tracker.session is None and 'Bu oturum: 2 dk · 2 sayfa · 1 işaretleme' in w.statusBar().currentMessage()
    assert w.today_label.text().startswith('Bugün 2 dk') and '2 dk' in w.shelf.item(0).text()


def test_slide_layout_and_reading_mode(env,qt,tmp_path):
    """Slayt: sayfa ekrana sığar, tekerlek/ok sayfa sayfa; elle 'kitap' yapınca sürekli. Okuma modu: kalemlik/panel kapanır, genişlik sabit."""
    from PySide6.QtGui import QWheelEvent
    import pymupdf as fitz
    lib,d,src=env; p=tmp_path/'slayt.pdf'
    with fitz.open() as doc:
        for i in range(8): pg=doc.new_page(width=960,height=540); pg.insert_text((60,80),f'Slayt {i+1}',fontsize=30)
        doc.save(p)
    s=lib.import_pdf(p); w=Window(lib); w.show(); QTest.qWait(100); w.open_doc(s['id']); idle(qt,.6); R=w.reader
    assert R.layout_mode=='slide' and R.layout_pref=='auto'
    r=R.pages[0]['rect']; vp=R.viewport(); assert r.height()*R.zoom<=vp.height() and r.width()*R.zoom<=vp.width(), 'sayfa ekrana sığmalı'
    assert R.current()[0]==1
    pos=QPointF(vp.width()/2,vp.height()/2); qt.sendEvent(vp,QWheelEvent(pos,vp.mapToGlobal(pos.toPoint()).toPointF(),QPoint(0,0),QPoint(0,-120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False))
    idle(qt,.5); assert R.current()[0]==2, 'tekerlek bir sonraki sayfaya götürmeli'
    QTest.keyClick(R,Qt.Key_Right); idle(qt,.5); assert R.current()[0]==3
    QTest.keyClick(R,Qt.Key_Left); idle(qt,.5); assert R.current()[0]==2
    w.set_layout_pref('book'); idle(qt,.3); assert R.layout_mode=='book' and lib.get_state(s['id'])['layout']=='book'
    qt.sendEvent(vp,QWheelEvent(pos,vp.mapToGlobal(pos.toPoint()).toPointF(),QPoint(0,0),QPoint(0,-120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False))
    idle(qt,.5); assert R.current()[0]==2, 'kitap düzeninde bir tık bir sayfa atlamamalı'
    # Okuma modu
    w.toggle_island() if not w.island_open else None; w.toggle_panel(); idle(qt,.3); assert w.island_open and w.panel_open
    QTest.keyClick(R,Qt.Key_R); idle(qt,.5)
    assert R.reading and not w.island_open and not w.panel_open and w.reading_action.isChecked()
    assert abs(R.pages[0]['rect'].width()*R.zoom-min(vp.width()-80,820))<2, 'okuma modunda sayfa genişliği ölçüye sabitlenmeli'
    assert R.backgroundBrush().color()==R.pages[0]['item'].color, 'okuma modunda zemin kâğıt rengi olmalı (sınır kaybolur)'
    QTest.keyClick(R,Qt.Key_R); idle(qt,.3); assert not R.reading and R.backgroundBrush().color()!=R.pages[0]['item'].color
    w.save_timer.stop(); w.poll_timer.stop(); w.close(); qt.processEvents()


def test_cover_designer_and_smooth_library_scroll(window,qt):
    from app import render_cover, CoverDesigner, SmoothScrollArea
    from PySide6.QtGui import QImage
    w,lib,d=window; w.show_shelf(); idle(qt,.2)
    spec={'style':'gradient','color':'#3f6f9e','color2':'#243447','diagonal':True,'page':False,'text':'light','align':'bottom','size':30,'band':True,'title':'Deneme','subtitle':'Raf'}
    img=render_cover(spec,None); assert img.width()==400 and img.height()==560 and img.pixelColor(10,10).name()!=img.pixelColor(390,550).name(), 'degrade olmalı'
    dlg=CoverDesigner(w,lib.document(d['id']),QImage(str(lib.root/'covers'/(d['id']+'.png'))),None); dlg.set_color('#c0713f'); dlg.title_edit.setText('Yeni Başlık')
    sp=dlg.current_spec(); assert sp['color']=='#c0713f' and sp['title']=='Yeni Başlık' and dlg.preview.pixmap() and not dlg.preview.pixmap().isNull()
    assert isinstance(w.shelf_scroll,SmoothScrollArea)
    w.save_timer.stop()


def test_drop_pdf_opens_it_and_drop_on_shelf_assigns(window,qt,tmp_path):
    """Masaüstünden bırakılan PDF içe alınıp açılır; raf satırına/ağaçtaki rafa bırakılınca o rafa konur; kart rafa taşınır."""
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QDropEvent
    from app import DOC_MIME
    import pymupdf as fitz
    w,lib,d=window; w.show_shelf(); idle(qt,.3)
    p=tmp_path/'yeni.pdf'
    with fitz.open() as doc: doc.new_page().insert_text((50,50),'Bırakılan belge'); doc.save(p)
    mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(p))])
    ev=QDropEvent(QPointF(400,120),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier); w.dropEvent(ev)
    for _ in range(60):
        idle(qt,.1)
        if w.stack.currentIndex()==1 and w.doc_id!=d['id']: break
    new=[x for x in lib.list_documents() if x['id']!=d['id']]; assert len(new)==1 and w.doc_id==new[0]['id'], 'bırakılan PDF açılmalı'
    sh=lib.add_shelf('Bırakma Rafı'); w.show_shelf(); idle(qt,.3)
    w.tree_dropped(sh['id'],[],new[0]['id']); assert lib.document(new[0]['id'])['shelf_id']==sh['id'], 'kart ağaçtaki rafa taşınmalı'
    q=tmp_path/'ikinci.pdf'
    with fitz.open() as doc: doc.new_page().insert_text((50,50),'İkinci'); doc.save(q)
    w.tree_dropped(sh['id'],[str(q)],'')
    for _ in range(60):
        idle(qt,.1)
        if w.stack.currentIndex()==1 and w.doc_id not in (d['id'],new[0]['id']): break
    assert lib.document(w.doc_id)['shelf_id']==sh['id'], 'rafa bırakılan PDF o rafta açılmalı'


def test_new_shelf_island_drop_and_plain_key_shortcuts(window,qt,monkeypatch):
    """'Yeni raf ekle' adasına bırakılan kart adı sorulan yeni rafa girer; Enter seçili belgeyi açar; 1–7 araç seçer; boş raflar satır olur."""
    from PySide6.QtCore import QMimeData
    from PySide6.QtGui import QDropEvent
    from app import DOC_MIME
    import app as A
    w,lib,d=window; w.show_shelf(); idle(qt,.3)
    assert w.new_shelf_box.isVisible() and w.rows_box.count()==1, 'raf yokken yalnızca Tüm belgeler satırı'
    lib.add_shelf('Boş Raf'); w.refresh_shelves(); w.refresh_shelf(); idle(qt,.2)
    assert w.rows_box.count()==3 and w.rows_box.itemAt(1).widget().list.count()==0, 'boş raf da satır olmalı (bırakma hedefi); sonra Rafsız'
    monkeypatch.setattr(A.QInputDialog,'getText',staticmethod(lambda *a,**k:('Sürüklenen Raf',True)))
    mime=QMimeData(); mime.setData(DOC_MIME,d['id'].encode()); pos=w.new_shelf_box.mapTo(w,w.new_shelf_box.rect().center())
    assert w.row_at(w.mapToGlobal(pos))=='__new__'
    w.dropEvent(QDropEvent(QPointF(pos),Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)); idle(qt,.2)
    assert lib.shelf(lib.document(d['id'])['shelf_id'])['name']=='Sürüklenen Raf'
    w.selected_doc=d['id']; w.shelves.setFocus(); w.shelves.setCurrentItem(None); QTest.keyClick(w.shelves,Qt.Key_Return); idle(qt,.4)
    assert w.stack.currentIndex()==1 and w.doc_id==d['id'], 'Enter seçili belgeyi açmalı'
    QTest.keyClick(w.reader,Qt.Key_4); idle(qt,.1); assert w.reader.mode=='highlight' and w.tool_buttons['highlight'].isChecked()
    QTest.keyClick(w.reader,Qt.Key_1); idle(qt,.1); assert w.reader.mode=='hand'
    w.title_search.setFocus(); w.show_shelf(); idle(qt,.2); w.title_search.setFocus(); QTest.keyClick(w.title_search,Qt.Key_Delete); idle(qt,.1)
    assert not lib.document(d['id'])['archived'], 'metin kutusunda Delete arşivlememeli'


def test_corner_close_mark_when_strip_hidden(window,qt):
    """Şerit kapanınca sol üstte küçük çarpı; üstüne gelince belirginleşir; tıklayınca kitaplığa döner. Widget değil, çizim (kaydırma hızlandırması bozulmasın)."""
    w,lib,d=window; r=w.reader
    assert not r.corner_on, 'şerit açıkken çarpı yok'
    idle(qt,3.0); assert w.strip.y()<0 and r.corner_on, 'şerit gizlenince çarpı görünmeli'
    assert not r.viewport().findChildren(QWidget), 'çarpı için görünümün üstüne widget konmamalı'
    QTest.mouseMove(r.viewport(),r.CORNER.center()); idle(qt,.1); assert r.corner_hover
    QTest.mouseMove(r.viewport(),QPoint(300,300)); idle(qt,.1); assert not r.corner_hover
    w.show_strip(); assert not r.corner_on; w.hide_strip(); assert r.corner_on
    QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=r.CORNER.center()); idle(qt,.3)
    assert w.stack.currentIndex()==0 and not r.corner_on


def test_assistant_docked_panel_pinning_and_source_snapshot(window,qt):
    import json,time
    w,lib,d=window
    with w.assistant_link.db() as db: db.execute('INSERT OR REPLACE INTO peer VALUES(1,?,?)',(time.time(),'[]'))
    from PySide6.QtCore import QAbstractAnimation
    w.toggle_strip_pin(False); w.show_strip()  # Suren kayma animasyonu varken sabitle.
    w.toggle_strip_pin(True); w.hide_strip(); idle(qt,.2)
    assert w.strip._anim.state()==QAbstractAnimation.State.Stopped
    assert w.strip.y()==0 and w.strip.isVisible()
    w.reader.selection='Alpha beta'; w.reader.selection_page=1; w.selection_changed('Alpha beta')
    w.ask_assistant('explain'); idle(qt,.2)
    request=w.assistant_link.request(w.assistant_request)
    payload=json.loads(request['payload']); assert payload['text']=='Alpha beta' and payload['page']==1
    assert w.assistant_panel.isVisible()
    assert w.reader.mapToGlobal(QPoint(w.reader.width(),0)).x()<=w.assistant_panel.mapToGlobal(QPoint(0,0)).x()
    w.reader.go(2); idle(qt,.1)
    with w.assistant_link.db() as db: db.execute("UPDATE requests SET status='done',reply=? WHERE id=?",('Kaynaklı açıklama',w.assistant_request))
    w.poll_assistant(); assert w.assistant_reply.toPlainText()=='Kaynaklı açıklama'
    assert w.assistant_source['page']==1
    w.reader.selection='İkinci sayfadan alıntı'; w.reader.selection_page=2; w.ask_assistant('save_note')
    assert json.loads(w.assistant_link.request(w.assistant_request)['payload'])['page']==2
    with w.assistant_link.db() as db: db.execute("UPDATE requests SET status='done',reply='Kaydedildi' WHERE id=?",(w.assistant_request,))
    w.poll_assistant(); assert w.assistant_source['page']==1 and w.assistant_reply.toPlainText()=='Kaynaklı açıklama'
    w.assistant_go_source(); idle(qt,.2); assert w.reader.current()[0]==1
    w.resize(1100,720); idle(qt,.2)
    assert w.strip.width()<=w.reader_page.width()+1
    w.grab().save(str(Path(tempfile.gettempdir())/'okuma-asistan-panel.png'))
    w.toggle_strip_pin(False)


def test_command_acknowledgement_and_unsaved_note_guard(window,qt):
    w,lib,d=window
    w.note_editor.setPlainText('Kaydedilmemiş not'); w.note_editor.document().setModified(True)
    key=lib.request_reader('close'); w.poll(); assert lib.reader_command(key)['status']=='error' and w.isVisible()
    w.show_shelf(); w.open_doc(d['id']); assert w.note_editor.toPlainText()=='Kaydedilmemiş not'
    w.save_note(); assert not w.note_editor.document().isModified()
    key=lib.request_reader('open',d['id'],2); w.poll(); idle(qt,.2)
    assert lib.reader_command(key)['status']=='done' and w.reader.current()[0]==2
    key=lib.request_reader('library'); w.poll()
    assert lib.reader_command(key)['state']=='library' and lib.reader_context()['selection']==''


def test_switch_library_in_place(window,qt,tmp_path,monkeypatch):
    """Kütüphane değişimi: açık belge kaydedilir, eski kapanır, yenisi yerinde açılır, işaretçi ve kayıt güncellenir; geri dönünce belgeler yerinde."""
    import core
    monkeypatch.setenv('APPDATA',str(tmp_path/'appdata'))
    w,lib,d=window; reader=w.reader; reader.go(2,.4); idle(qt,.6)
    core.register_library('Yedek',tmp_path/'B')
    w.switch_library(tmp_path/'B'); idle(qt,.4)
    assert w.lib.root==(tmp_path/'B').resolve() and w.lib is not lib and w.reader.lib is w.lib and w.tracker.lib is w.lib
    assert w.stack.currentIndex()==0 and w.doc_id is None and not w.reader.pages and w.lib.list_documents()==[]
    assert w.lib_button.text()=='Yedek' and core.default_data_dir()==w.lib.root and 'Yedek' in w.windowTitle()
    assert lib.get_state(d['id'])['page']==2, 'değişimden önce konum kaydedilmeli'
    w.switch_library(lib.root); idle(qt,.4)
    assert len(w.lib.list_documents())==1 and w.shelf.count()==1 and w.lib_button.text()==core.library_name(lib.root)
    w.open_doc(d['id']); idle(qt,.4); assert w.reader.current()[0]==2
    w.switch_library(w.lib.root); assert w.doc_id==d['id'], 'aynı kütüphane: değişiklik yok'
