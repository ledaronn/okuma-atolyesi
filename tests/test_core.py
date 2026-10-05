import hashlib
from pathlib import Path
import sys
import zipfile
import pytest
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Library

@pytest.fixture
def env(tmp_path):
    src=tmp_path/'source.pdf'
    with fitz.open() as doc:
        for i in range(3):
            p=doc.new_page(width=400,height=540)
            p.insert_text((45,75),f'Reading workshop page {i+1}',fontsize=18)
            p.insert_text((45,115),'Alpha beta gamma. Research and learning.',fontsize=12)
            if i==1: p.set_rotation(90)
        doc.set_toc([[1,'Introduction',1],[1,'Research',2]])
        doc.save(src)
    lib=Library(tmp_path/'data'); d=lib.import_pdf(src)
    return lib,d,src


def test_import_immutable_duplicate_and_index(env):
    lib,d,src=env; before=hashlib.sha256(src.read_bytes()).hexdigest()
    assert lib.import_pdf(src)['id']==d['id']
    assert len(lib.list_documents())==1
    assert {r['page'] for r in lib.search('Research')}=={1,2,3}
    assert len(lib.read_pages(d['id'])['pages'])==3
    assert 'Reading workshop' in lib.read_pages(d['id'],2,2)['pages'][0]['text']
    lib.add_annotation(d['id'],1,'note',{'text':'Türkçe not: öğrenme, çalışma.'})
    out=lib.export_pdf(d['id'])
    assert hashlib.sha256(src.read_bytes()).hexdigest()==before
    assert Path(out['path']).exists()
    assert lib.path(d['id']).read_bytes()==src.read_bytes()


def test_reader_liveness_commands_and_lossless_chunks(env):
    import json,time
    lib,d,_=env
    lib.publish_reader('reading',d['id'],2,'Selected text',2)
    assert lib.reader_context()['selection']=='Selected text'
    with lib.db() as db:
        row=json.loads(db.execute('SELECT data FROM reader_context').fetchone()[0]); row['updated']=time.time()-30
        db.execute('UPDATE reader_context SET data=?',(json.dumps(row),))
    context=lib.reader_context(); assert not context['is_open'] and context['document_id'] is None and context['selection']==''
    lib.publish_reader('library'); assert lib.reader_context()['state']=='library'
    lib.publish_reader('closed'); assert not lib.reader_context()['is_open']
    key=lib.request_reader('open',d['id'],3); assert lib.pending_reader_commands()[0]['id']==key
    lib.finish_reader_command(key,{'page':3}); assert lib.reader_command(key)['status']=='done'
    expired=lib.request_reader('close')
    with lib.db() as db: db.execute('UPDATE reader_commands SET created=0 WHERE id=?',(expired,))
    assert not lib.pending_reader_commands(); assert lib.reader_command(expired)['status']=='expired'
    body='Türkçe metin 🧠. '*700
    with lib.db() as db: db.execute('UPDATE page_text SET text=? WHERE doc_id=? AND page=1',(body,d['id']))
    cursor={'page':1,'offset':0}; parts=[]
    while cursor and cursor['page']==1:
        chunk=lib.read_chunk(d['id'],**cursor); parts.append(chunk['text']); cursor=chunk['next']
    assert ''.join(parts)==body and cursor=={'page':2,'offset':0}
    with pytest.raises(ValueError): lib.read_chunk(d['id'],offset=-1)
    with lib.db() as db: db.execute('UPDATE page_text SET text=? WHERE doc_id=? AND page=3',('',d['id']))
    assert lib.read_chunk(d['id'],3)['needs_ocr'] and lib.read_chunk(d['id'],3)['next'] is None


def test_annotations_undo_redo_and_export(env):
    lib,d,_=env; id_=d['id']
    a=lib.add_annotation(id_,1,'ink',{'points':[[30,130],[75,155],[100,135]],'color':'#aa3355','width':3})
    lib.add_annotation(id_,1,'highlight',{'rects':[[40,100,200,120]],'text':'Alpha beta'})
    lib.add_annotation(id_,1,'underline',{'rects':[[40,100,200,120]]})
    lib.add_annotation(id_,1,'rect',{'rects':[[40,180,200,220]]})
    lib.add_annotation(id_,1,'arrow',{'points':[[40,260],[180,260]]})
    lib.add_annotation(id_,1,'note',{'text':'İşaretleme korunuyor.'})
    lib.add_annotation(id_,1,'bookmark',{'text':'Giriş'})
    assert len(lib.annotations(id_))==7
    lib.delete_annotation(id_,a['id']); assert len(lib.annotations(id_))==6
    assert lib.undo(id_); assert len(lib.annotations(id_))==7
    assert lib.undo(id_,True); assert len(lib.annotations(id_))==6
    assert lib.undo(id_)
    with fitz.open(lib.export_pdf(id_)['path']) as pdf:
        page=pdf[0]; anns=list(page.annots()); assert len(anns)==6
        assert any(a.type[1]=='Ink' for a in anns)
        assert any('İşaretleme' in a.info['content'] for a in anns)
        assert len(pdf)==3
    assert lib.render(id_,1).startswith(b'\x89PNG')
    assert 'Sayfa 1' in Path(lib.export_notes(id_)['path']).read_text()


def test_rotated_coords_roundtrip(env):
    lib,d,_=env; id_=d['id']
    w=next(w for w in lib.words(id_,2) if w[4]=='Alpha')
    lib.add_annotation(id_,2,'highlight',{'rects':[w[:4]]})
    with fitz.open(lib.export_pdf(id_)['path']) as doc:
        p=doc[1]; a=next(p.annots()); display=a.rect*p.rotation_matrix
        assert display.intersects(fitz.Rect(w[:4]))
        assert display.contains(fitz.Rect(w[:4]).tl)
    assert lib.render(id_,2)


def test_state_reopen_and_reader_context(env):
    lib,d,_=env; id_=d['id']
    lib.save_state(id_,2,.74,1.6); lib.save_reader_context(id_,2,'Selected alpha',1)
    reopened=Library(lib.root)
    st=reopened.get_state(id_); assert (st['page'],st['offset'],st['zoom'])==(2,.74,1.6) and st['seen']==[]  # 'seen' eklendi (raf aşaması)
    assert reopened.reader_context()['selection']=='Selected alpha'


def test_page_operations_backup_and_archive(env):
    lib,d,src=env; id_=d['id']
    with fitz.open(lib.export_pdf(id_,[3,1],90)['path']) as pdf:
        assert len(pdf)==2 and pdf[0].rotation==90
        assert 'page 3' in pdf[0].get_text()
    with fitz.open(lib.merge([id_,id_])['path']) as pdf: assert len(pdf)==6
    lib.update_document(id_,collection='Araştırma',tags='ders, bilim',favorite=True)
    assert len(lib.list_documents(collection='Araştırma',favorites=True))==1
    with zipfile.ZipFile(lib.backup()['path']) as z:
        assert 'library.sqlite3' in z.namelist()
        assert f'originals/{id_}.pdf' in z.namelist()
    lib.update_document(id_,archived=True)
    assert not lib.list_documents() and not lib.search('Alpha')
    assert lib.list_documents(archived=True)
    lib.import_pdf(src); assert lib.list_documents()


def test_bad_inputs_and_output_budget(env):
    lib,d,_=env; id_=d['id']
    for bad in ['../../etc/passwd','unknown']:
        with pytest.raises(ValueError): lib.path(bad)
    for page in (0,-1,4):
        with pytest.raises(ValueError): lib.read_pages(id_,page)
    with pytest.raises(ValueError): lib.add_annotation(id_,1,'ink',{'points':[[1,2],[float('nan'),3]]})
    with pytest.raises(ValueError): lib.add_annotation(id_,1,'rect',{'rects':[[1,2,900,950]]})
    with pytest.raises(ValueError): lib.add_annotation(id_,1,'note',{'color':'#xyzxyz'})
    with pytest.raises(ValueError): lib.export_pdf(id_,[])
    with pytest.raises(ValueError): lib.export_pdf(id_,[1],45)
    with pytest.raises(ValueError): lib.highlight_text(id_,1,'THIS DOES NOT EXIST')
    assert isinstance(lib.search('" OR * -'),list)
    lib.highlight_text(id_,1,'Alpha')
    assert len(lib.annotations(id_))==1


def test_command_queue_and_branch_history(env):
    lib,d,_=env; id_=d['id']
    lib.queue_open(id_,2); assert lib.take_commands()[0]['page']==2; assert not lib.take_commands()
    lib.add_annotation(id_,1,'note',{'text':'A'}); lib.add_annotation(id_,1,'note',{'text':'B'})
    lib.undo(id_); lib.add_annotation(id_,1,'note',{'text':'C'})
    assert not lib.undo(id_,True)
    assert [a['data']['text'] for a in lib.annotations(id_)]==['A','C']


def test_encrypted_input_and_error_cleanup(tmp_path):
    source=tmp_path/'locked.pdf'
    with fitz.open() as doc:
        p=doc.new_page(); p.insert_text((50,50),'Secret sample')
        doc.save(source,encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='owner',user_pw='reader')
    lib=Library(tmp_path/'data')
    with pytest.raises(ValueError): lib.import_pdf(source)
    assert not lib.list_documents() and not list((lib.root/'originals').iterdir())
    d=lib.import_pdf(source,'reader')
    assert 'Secret' in lib.read_pages(d['id'])['pages'][0]['text']
    with fitz.open(lib.path(d['id'])) as doc: assert not doc.needs_pass


def test_real_ocr_image_page(tmp_path):
    import shutil
    import subprocess
    if not shutil.which('tesseract'): pytest.skip('Tesseract kurulu değil')
    langs=subprocess.run(['tesseract','--list-langs'],capture_output=True,text=True,check=True).stdout
    if 'eng' not in langs.splitlines(): pytest.skip('İngilizce OCR dil verisi yok')
    source=tmp_path/'scan.pdf'
    with fitz.open() as text_doc:
        p=text_doc.new_page(width=500,height=300)
        p.insert_text((40,70),'Optical character recognition',fontsize=24)
        p.insert_text((40,120),'Reading workshop scanned document',fontsize=18)
        png=p.get_pixmap(matrix=fitz.Matrix(2,2)).tobytes('png')
    with fitz.open() as doc:
        p=doc.new_page(width=500,height=300); p.insert_image(p.rect,stream=png); doc.save(source)
    lib=Library(tmp_path/'data'); d=lib.import_pdf(source)
    assert lib.read_pages(d['id'])['pages'][0]['needs_ocr']
    result=lib.ocr(d['id'],1,1,'eng'); assert result['pages']==1
    assert lib.search('Optical')
    assert any(w[4]=='Optical' for w in lib.words(d['id'],1))
    assert not lib.read_pages(d['id'])['pages'][0]['needs_ocr']


def test_shelves_migration_crud_and_seen_pages(env):
    import sqlite3
    lib,d,src=env; root=lib.root; other=lib.import_pdf(src) if False else None
    # Eski şemayı taklit et: shelf_id yok, koleksiyon adı var → yeniden açınca yedek + taşıma
    lib.close(); db=sqlite3.connect(root/'library.sqlite3')
    db.execute("UPDATE documents SET collection='Sosyal Psikoloji'"); db.execute('DROP TABLE shelves'); db.execute('ALTER TABLE documents DROP COLUMN shelf_id'); db.commit(); db.close()
    lib=Library(root)
    assert [f for f in root.iterdir() if 'yedek' in f.name], 'şema değişmeden yedek alınmalı'
    shelves=lib.list_shelves(); assert [s['name'] for s in shelves]==['Sosyal Psikoloji'] and lib.document(d['id'])['shelf_id']==shelves[0]['id']
    assert lib.list_documents(collection='Sosyal Psikoloji') and lib.list_documents(shelf=shelves[0]['id'])
    a=lib.add_shelf('Aile Terapisi'); b=lib.add_shelf('Bilişsel Psikoloji','#3f6f9e')
    assert len(lib.list_shelves())==3 and b['color']=='#3f6f9e'
    lib.move_to_shelf(d['id'],a['id']); assert lib.document(d['id'])['collection']=='Aile Terapisi'
    lib.update_shelf(a['id'],name='Aile'); assert lib.document(d['id'])['collection']=='Aile' and lib.list_documents(collection='Aile')
    lib.update_document(d['id'],collection='Yeni Ders'); assert lib.document(d['id'])['shelf_id'] and 'Yeni Ders' in [s['name'] for s in lib.list_shelves()]
    with pytest.raises(ValueError): lib.add_shelf('Yeni Ders')
    sid=lib.document(d['id'])['shelf_id']; lib.delete_shelf(sid)
    assert lib.document(d['id'])['id']==d['id'] and lib.document(d['id'])['shelf_id']=='' and len(lib.list_documents(shelf=''))==1
    lib.save_state(d['id'],2,0,1.0,seen=[1,2,99,True]); assert lib.get_state(d['id'])['seen']==[1,2]
    lib.save_state(d['id'],3,0,1.0); assert lib.get_state(d['id'])['seen']==[1,2], 'seen verilmeyince korunmalı'
    assert lib.last_opened()['id']==d['id'] and lib.last_opened()['state']['page']==3
    lib.close()


def test_guess_layout_slide_vs_book(tmp_path):
    lib=Library(tmp_path/'data')
    for name,w,h,text in (('slayt',960,540,'Kısa madde'),('kitap',595,842,' '.join(['kelime']*400))):
        p=tmp_path/f'{name}.pdf'
        with fitz.open() as doc:
            for i in range(6): pg=doc.new_page(width=w,height=h); pg.insert_textbox(fitz.Rect(40,40,w-40,h-40),text,fontsize=11)
            doc.save(p)
        d=lib.import_pdf(p); g=lib.guess_layout(d['id']); assert g['layout']==('slide' if name=='slayt' else 'book'), g
        lib.save_state(d['id'],1,0,1.0,layout='book'); assert lib.get_state(d['id'])['layout']=='book'
        lib.save_state(d['id'],2,0,1.0); assert lib.get_state(d['id'])['layout']=='book', 'düzen tercihi korunmalı'
    with pytest.raises(ValueError): lib.save_state(d['id'],1,0,1.0,layout='x')
    lib.close()


def test_library_registry(tmp_path,monkeypatch):
    """Birden çok kütüphane: kayıt listesi APPDATA altında; ad güncellenir, yol tekrarlanmaz, listeden kaldırma klasöre dokunmaz."""
    import core
    monkeypatch.setenv('APPDATA',str(tmp_path/'appdata'))
    assert core.list_libraries()==[]
    a=tmp_path/'A'; b=tmp_path/'B'
    assert core.list_libraries(a)==[{'name':'A','path':str(a.resolve())}], 'açık klasör listede yoksa eklenir'
    core.register_library('İkinci',b); core.register_library('Birinci',a)
    assert [x['name'] for x in core.list_libraries()]==['Birinci','İkinci'] and core.library_name(a)=='Birinci'
    with pytest.raises(ValueError): core.register_library('birinci',tmp_path/'C')
    core.unregister_library(a); assert [x['name'] for x in core.list_libraries()]==['İkinci'] and core.library_name(a)=='A'
    Library(b); (tmp_path/'D').mkdir(); (tmp_path/'D'/'x.txt').write_text('x')
    assert core.is_library_dir(b) and core.is_library_dir(tmp_path/'yok') and not core.is_library_dir(tmp_path/'D')
    assert core.default_library_name(Path.home()/'OkumaAtolyesiVeri')=='Ana kütüphane'
