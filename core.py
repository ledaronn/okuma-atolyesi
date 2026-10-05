"""Okuma Atölyesi: bağımsız yerel PDF deposu. GUI ve MCP aynı çekirdeği kullanır."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import closing, contextmanager
from functools import wraps

import pymupdf as fitz

PDF_LOCK = threading.RLock()  # MuPDF aynı süreçte eşzamanlı thread kullanımını desteklemez.


def pdf_locked(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with PDF_LOCK:
            return fn(*args, **kwargs)
    return wrapped


def pointer_file():
    """Veri klasörü işaretçisi: kullanıcı veriyi başka diske taşıyınca yol burada tutulur; GUI ve MCP aynı dosyayı okur."""
    base=Path(os.environ.get('APPDATA') or Path.home()/'.config'); return base/'OkumaAtolyesi'/'veri_yolu.txt'


def default_data_dir():
    if os.environ.get('OKUMA_DATA_DIR'): return Path(os.environ['OKUMA_DATA_DIR']).expanduser().resolve()
    try:
        p=pointer_file()
        if p.exists():
            saved=p.read_text(encoding='utf-8').strip()
            if saved: return Path(saved).expanduser().resolve()
    except OSError: pass
    return (Path.home()/'OkumaAtolyesiVeri').resolve()


def set_default_data_dir(path):
    """İşaretçiyi yazar; bir sonraki açılıştan itibaren varsayılan veri klasörü budur."""
    p=pointer_file(); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(str(Path(path).expanduser().resolve()),encoding='utf-8'); return p


# ----- kütüphane kaydı -----
# Birden çok kütüphane: her biri ayrı bir veri klasörü (kendi library.sqlite3, originals/, covers/…). Ad ve yol listesi
# işaretçi dosyasının yanındaki kutuphaneler.json'da tutulur; hangisinin "açık" olduğunu işaretçi (veri_yolu.txt) söyler,
# böylece MCP sunucusu da GUI'de seçilen kütüphaneyi açar.
def registry_file(): return pointer_file().with_name('kutuphaneler.json')


def _read_registry():
    try:
        p=registry_file()
        if p.exists():
            data=json.loads(p.read_text(encoding='utf-8'))
            libs=[x for x in data.get('libraries',[]) if isinstance(x,dict) and x.get('path')]
            return [{'name':str(x.get('name') or Path(x['path']).name),'path':str(Path(x['path']).expanduser().resolve())} for x in libs]
    except (OSError,ValueError): pass
    return []


def _write_registry(libs):
    p=registry_file(); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps({'libraries':libs},ensure_ascii=False,indent=1),encoding='utf-8')


def default_library_name(path):
    path=Path(path).expanduser().resolve()
    return 'Ana kütüphane' if path==(Path.home()/'OkumaAtolyesiVeri').resolve() else path.name


def list_libraries(current=None):
    """Kayıtlı kütüphaneler [{'name','path'}]. current verilirse ve listede yoksa eklenir (ilk çalıştırma, --data-dir)."""
    libs=_read_registry()
    if current is not None:
        cur=str(Path(current).expanduser().resolve())
        if not any(x['path'].lower()==cur.lower() for x in libs): libs.insert(0,{'name':default_library_name(cur),'path':cur}); _write_registry(libs)
    return libs


def register_library(name,path):
    """Kütüphaneyi listeye ekler (yol varsa adı günceller). Dönüş: kayıt."""
    name=' '.join(str(name).split()) or default_library_name(path); path=str(Path(path).expanduser().resolve()); libs=_read_registry()
    for x in libs:
        if x['path'].lower()==path.lower(): x['name']=name; _write_registry(libs); return x
    if any(x['name'].lower()==name.lower() for x in libs): raise ValueError('Bu adda bir kütüphane zaten var.')
    rec={'name':name,'path':path}; libs.append(rec); _write_registry(libs); return rec


def unregister_library(path):
    """Listeden çıkarır; klasöre dokunmaz."""
    path=str(Path(path).expanduser().resolve()); libs=[x for x in _read_registry() if x['path'].lower()!=path.lower()]; _write_registry(libs); return libs


def library_name(path):
    path=str(Path(path).expanduser().resolve())
    for x in _read_registry():
        if x['path'].lower()==path.lower(): return x['name']
    return default_library_name(path)


def is_library_dir(path):
    """Boş klasör ya da içinde library.sqlite3 olan klasör kütüphane olabilir."""
    p=Path(path).expanduser().resolve()
    if not p.exists(): return True
    if not p.is_dir(): return False
    return (p/'library.sqlite3').exists() or not any(p.iterdir())


def plain(row):
    return dict(row) if row else None


class Library:
    def __init__(self, root=None):
        self.root = Path(root or default_data_dir()).expanduser().resolve()
        for name in ('originals', 'covers', 'exports', 'imports'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'library.sqlite3'
        # İş parçacığı başına kalıcı bağlantı. Her çağrıda aç-kapa Windows'ta ~9 ms (okuma) / ~35 ms (yazma) tutuyordu;
        # okuma konumu kaydı ve MCP komut kuyruğu ana iş parçacığında bu kadar bloke oluyordu. Kalıcı bağlantıda 0,4 ms.
        self._local = threading.local(); self._conns = []; self._conns_lock = threading.Lock()
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, sha TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                    filename TEXT NOT NULL, pages INTEGER NOT NULL, created REAL NOT NULL,
                    opened REAL DEFAULT 0, favorite INTEGER DEFAULT 0,
                    collection TEXT DEFAULT '', tags TEXT DEFAULT '', archived INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS page_text (
                    doc_id TEXT, page INTEGER, text TEXT, words TEXT DEFAULT '[]',
                    PRIMARY KEY(doc_id,page));
                CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(doc_id UNINDEXED, page UNINDEXED, text, tokenize='unicode61 remove_diacritics 2');
                CREATE TABLE IF NOT EXISTS annotations (
                    id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, page INTEGER NOT NULL,
                    kind TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS state (doc_id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, before_json TEXT,
                    after_json TEXT, undone INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, page INTEGER, created REAL);
                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, action TEXT, doc_id TEXT);
                CREATE INDEX IF NOT EXISTS ann_doc ON annotations(doc_id,page);
                CREATE TABLE IF NOT EXISTS shelves (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, color TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, started REAL NOT NULL, ended REAL NOT NULL,
                    active_seconds REAL NOT NULL DEFAULT 0, pages INTEGER NOT NULL DEFAULT 0, marks INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS sess_doc ON sessions(doc_id, started);
            ''')
        self._migrate_shelves()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reader_commands (id TEXT PRIMARY KEY, action TEXT, doc_id TEXT, page INTEGER, created REAL, status TEXT, result TEXT)')

    # ----- çalışma oturumları -----
    # Belge açıkken geçen ETKİN süre: pencere öndeyken ve son etkinlikten 5 dk geçmemişken sayılır (app.StudyTracker).
    # Oturum 30 s'de bir ve kapanışta yazılır; ani kapanışta en fazla 30 s kaybolur.
    def start_session(self,doc_id):
        self.document(doc_id); sid=uuid.uuid4().hex; now=time.time()
        with self.db() as db: db.execute('INSERT INTO sessions VALUES(?,?,?,?,0,0,0)',(sid,doc_id,now,now))
        return sid

    def update_session(self,session_id,active_seconds,pages,marks):
        with self.db() as db:
            db.execute('UPDATE sessions SET ended=?, active_seconds=?, pages=?, marks=? WHERE id=?',(time.time(),max(0,float(active_seconds)),int(pages),int(marks),session_id))

    def end_session(self,session_id,active_seconds,pages,marks,min_seconds=5):
        """Kapatır; 5 saniyeden kısa oturumlar gürültüdür, silinir."""
        if active_seconds<min_seconds:
            with self.db() as db: db.execute('DELETE FROM sessions WHERE id=?',(session_id,))
            return None
        self.update_session(session_id,active_seconds,pages,marks)
        with self.db() as db: row=db.execute('SELECT * FROM sessions WHERE id=?',(session_id,)).fetchone()
        return dict(row) if row else None

    def study_summary(self,doc_id=None,since=None,until=None,shelf_id=None):
        """Toplam etkin saniye, sayfa ve işaretleme. since/until: zaman damgası; shelf_id: rafın belgeleri."""
        where=['1=1']; args=[]
        if doc_id: where.append('s.doc_id=?'); args.append(doc_id)
        if since is not None: where.append('s.started>=?'); args.append(float(since))
        if until is not None: where.append('s.started<?'); args.append(float(until))
        if shelf_id is not None: where.append('d.shelf_id=?'); args.append(shelf_id)
        with self.db() as db:
            row=db.execute('SELECT COALESCE(SUM(s.active_seconds),0) AS seconds, COALESCE(SUM(s.pages),0) AS pages, COALESCE(SUM(s.marks),0) AS marks, COUNT(*) AS sessions FROM sessions s JOIN documents d ON d.id=s.doc_id WHERE '+' AND '.join(where),args).fetchone()
        return dict(row)

    @staticmethod
    def day_start(ts=None):
        import datetime
        d=datetime.datetime.fromtimestamp(ts or time.time()); return datetime.datetime(d.year,d.month,d.day).timestamp()

    def today_summary(self): return self.study_summary(since=self.day_start())

    def shelf_week_seconds(self):
        """Raf kimliği → son 7 gündeki etkin saniye."""
        since=self.day_start()-6*86400
        with self.db() as db:
            rows=db.execute('SELECT d.shelf_id AS sid, SUM(s.active_seconds) AS secs FROM sessions s JOIN documents d ON d.id=s.doc_id WHERE s.started>=? GROUP BY d.shelf_id',(since,)).fetchall()
        return {r['sid'] or '':r['secs'] for r in rows}

    def document_seconds(self):
        """Belge kimliği → toplam etkin saniye."""
        with self.db() as db: rows=db.execute('SELECT doc_id, SUM(active_seconds) AS secs FROM sessions GROUP BY doc_id').fetchall()
        return {r['doc_id']:r['secs'] for r in rows}

    # ----- raflar -----
    # Her ders bir raf. documents.collection sütunu raf ADI olarak kalır (MCP list_documents/update_metadata sözleşmesi
    # değişmez); documents.shelf_id rafı kimlikle bağlar. Raf silinince belgeler silinmez, raftan çıkar.
    SHELF_COLORS=('#5b8c5a','#c0713f','#3f6f9e','#8e5aa5','#b3823a','#a8474f','#3f8f8c','#6b6b6b')

    def _migrate_shelves(self):
        with self.db() as db:
            cols=[r[1] for r in db.execute('PRAGMA table_info(documents)')]
            if 'shelf_id' in cols: return
        # Şema değişmeden önce tutarlı yedek (WAL dahil) — geri dönüş noktası. Boş kütüphanede gerek yok.
        with self.db() as db: has_docs=db.execute('SELECT 1 FROM documents LIMIT 1').fetchone() is not None
        if has_docs:
            backup=self.root/('library.sqlite3.yedek-'+time.strftime('%Y%m%d-%H%M%S'))
            with closing(sqlite3.connect(backup)) as dst: self._connection().backup(dst)
        with self.db() as db:
            db.execute("ALTER TABLE documents ADD COLUMN shelf_id TEXT DEFAULT ''")
            names=[r[0] for r in db.execute("SELECT DISTINCT collection FROM documents WHERE collection!='' ORDER BY collection")]
            for i,name in enumerate(names):
                sid=uuid.uuid4().hex
                db.execute('INSERT INTO shelves VALUES(?,?,?,?,?)',(sid,name,self.SHELF_COLORS[i%len(self.SHELF_COLORS)],i,time.time()))
                db.execute('UPDATE documents SET shelf_id=? WHERE collection=?',(sid,name))
            self._log(db,'migrate_shelves','')

    def list_shelves(self):
        with self.db() as db:
            rows=db.execute('SELECT s.*, (SELECT COUNT(*) FROM documents d WHERE d.shelf_id=s.id AND d.archived=0) AS count FROM shelves s ORDER BY position, name').fetchall()
        return [dict(r) for r in rows]

    def add_shelf(self,name,color=None):
        name=str(name).strip()[:120]
        if not name: raise ValueError('Raf adı boş olamaz.')
        with self.db() as db:
            if db.execute('SELECT 1 FROM shelves WHERE name=?',(name,)).fetchone(): raise ValueError('Bu adda bir raf zaten var.')
            n=db.execute('SELECT COUNT(*) FROM shelves').fetchone()[0]; sid=uuid.uuid4().hex
            color=self._check_color(color or self.SHELF_COLORS[n%len(self.SHELF_COLORS)])
            db.execute('INSERT INTO shelves VALUES(?,?,?,?,?)',(sid,name,color,n,time.time())); self._log(db,'shelf',sid)
        return self.shelf(sid)

    @staticmethod
    def _check_color(color):
        color=str(color)
        if len(color)!=7 or color[0]!='#': raise ValueError('Renk #RRGGBB olmalı.')
        int(color[1:],16); return color

    def shelf(self,shelf_id):
        with self.db() as db: row=db.execute('SELECT * FROM shelves WHERE id=?',(shelf_id,)).fetchone()
        if not row: raise ValueError('Raf bulunamadı.')
        return dict(row)

    def update_shelf(self,shelf_id,name=None,color=None):
        self.shelf(shelf_id)
        with self.db() as db:
            if name is not None:
                name=str(name).strip()[:120]
                if not name: raise ValueError('Raf adı boş olamaz.')
                if db.execute('SELECT 1 FROM shelves WHERE name=? AND id!=?',(name,shelf_id)).fetchone(): raise ValueError('Bu adda bir raf zaten var.')
                db.execute('UPDATE shelves SET name=? WHERE id=?',(name,shelf_id)); db.execute('UPDATE documents SET collection=? WHERE shelf_id=?',(name,shelf_id))
            if color is not None: db.execute('UPDATE shelves SET color=? WHERE id=?',(self._check_color(color),shelf_id))
            self._log(db,'shelf',shelf_id)
        return self.shelf(shelf_id)

    def delete_shelf(self,shelf_id):
        """Rafı kaldırır; belgeler silinmez, rafsız kalır."""
        self.shelf(shelf_id)
        with self.db() as db:
            db.execute("UPDATE documents SET shelf_id='', collection='' WHERE shelf_id=?",(shelf_id,)); db.execute('DELETE FROM shelves WHERE id=?',(shelf_id,)); self._log(db,'shelf',shelf_id)

    def shelf_for_name(self,name):
        """Ada göre raf; yoksa oluşturur (MCP update_metadata(collection=...) yolu)."""
        name=str(name).strip()[:120]
        if not name: return None
        with self.db() as db: row=db.execute('SELECT * FROM shelves WHERE name=?',(name,)).fetchone()
        return dict(row) if row else self.add_shelf(name)

    def move_to_shelf(self,doc_id,shelf_id=''):
        self.document(doc_id); name=''
        if shelf_id: name=self.shelf(shelf_id)['name']
        with self.db() as db:
            db.execute('UPDATE documents SET shelf_id=?, collection=? WHERE id=?',(shelf_id or '',name,doc_id)); self._log(db,'metadata',doc_id)
        return self.document(doc_id)

    def guess_layout(self,doc_id):
        """Belge türü: 'slide' (sayfa sayfa) ya da 'book' (sürekli). Yatay sayfa → slayt; dikey → kitap; kareye yakınsa metin yoğunluğu karar verir."""
        geometry=self.geometry(doc_id)[:12]
        ratios=sorted(p['width']/max(1,p['height']) for p in geometry); aspect=ratios[len(ratios)//2]  # medyan: tek döndürülmüş sayfa kararı bozmasın
        with self.db() as db: row=db.execute('SELECT AVG(LENGTH(text)) AS chars FROM page_text WHERE doc_id=? AND page<=20',(doc_id,)).fetchone()
        chars=row['chars'] or 0
        if aspect>=1.15: kind='slide'
        elif aspect<=0.9: kind='book'
        else: kind='slide' if chars<700 else 'book'
        return {'layout':kind,'aspect':round(aspect,2),'chars_per_page':int(chars)}

    # ----- kapaklar -----
    def cover_path(self,doc_id):
        """Kişisel kapak varsa o (covers/<id>.custom.png), yoksa PDF'nin ilk sayfası (covers/<id>.png)."""
        custom=self.root/'covers'/(doc_id+'.custom.png')
        return custom if custom.exists() else self.root/'covers'/(doc_id+'.png')

    def has_custom_cover(self,doc_id): return (self.root/'covers'/(doc_id+'.custom.png')).exists()

    def set_custom_cover(self,doc_id,png_bytes):
        self.document(doc_id)
        if not isinstance(png_bytes,(bytes,bytearray)) or len(png_bytes)<8 or bytes(png_bytes[:8])!=b'\x89PNG\r\n\x1a\n': raise ValueError('Kapak PNG olmalı.')
        if len(png_bytes)>8*1024*1024: raise ValueError('Kapak 8 MB\'ı aşamaz.')
        p=self.root/'covers'/(doc_id+'.custom.png'); tmp=p.with_suffix('.tmp')
        with tmp.open('wb') as f: f.write(png_bytes); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
        with self.db() as db: self._log(db,'cover',doc_id)
        return p

    def clear_custom_cover(self,doc_id):
        self.document(doc_id); p=self.root/'covers'/(doc_id+'.custom.png')
        if p.exists(): p.unlink()
        with self.db() as db: self._log(db,'cover',doc_id)

    def last_opened(self):
        """'Devam et' kartı: en son çalışılan arşivlenmemiş belge ve kaldığı yer."""
        with self.db() as db: row=db.execute('SELECT * FROM documents WHERE archived=0 AND opened>0 ORDER BY opened DESC LIMIT 1').fetchone()
        if not row: return None
        d=dict(row); d['state']=self.get_state(d['id']); return d

    def _connection(self):
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            # check_same_thread=False yalnızca close() için: kapanış tüm bağlantıları ana iş parçacığından kapatır.
            conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            with self._conns_lock: self._conns.append(conn)
        return conn

    @contextmanager
    def db(self):
        with self._connection() as db:
            yield db

    def close(self):
        """Tüm iş parçacıklarının bağlantılarını kapatır (uygulama kapanışı, testler). Sonraki çağrılar yeniden açar."""
        with self._conns_lock: conns, self._conns = self._conns, []
        self._local = threading.local()
        for conn in conns:
            try: conn.close()
            except Exception: pass

    def document(self, doc_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
        if not row:
            raise ValueError('Belge bulunamadı.')
        return dict(row)

    def path(self, doc_id):
        self.document(doc_id)
        # ID veritabanında doğrulandıktan sonra bile dosya adı biçimi zorunlu.
        if not isinstance(doc_id, str) or len(doc_id) != 32 or any(c not in '0123456789abcdef' for c in doc_id):
            raise ValueError('Geçersiz belge kimliği.')
        target = (self.root / 'originals' / (doc_id + '.pdf')).resolve()
        if target.parent != (self.root / 'originals').resolve():
            raise ValueError('Belge yolu depo dışında.')
        return target

    def list_documents(self, query='', collection='', favorites=False, archived=False, limit=500, shelf=None):
        """shelf: None = tümü, '' = rafsızlar, raf kimliği = o raf. collection: raf adıyla filtre (MCP sözleşmesi)."""
        with self.db() as db:
            rows = db.execute('SELECT * FROM documents WHERE archived=? ORDER BY opened DESC, created DESC', (int(archived),)).fetchall()
        q = query.casefold().strip()
        return [dict(r) for r in rows if (not q or q in (r['title']+' '+r['tags']+' '+r['collection']).casefold()) and (not collection or r['collection']==collection)
                and (shelf is None or (r['shelf_id'] or '')==shelf) and (not favorites or r['favorite'])][:max(1,min(limit,1000))]

    @pdf_locked
    def import_pdf(self, source, password=''):
        src = Path(source).expanduser().resolve(strict=True)
        if src.suffix.lower() != '.pdf' or not src.is_file():
            raise ValueError('Bir PDF dosyası seçin.')
        if src.stat().st_size > 512 * 1024 * 1024:
            raise ValueError('İlk sürümde dosya sınırı 512 MB.')
        raw = src.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        with self.db() as db:
            existing = db.execute('SELECT id FROM documents WHERE sha=?', (digest,)).fetchone()
        if existing:
            self.update_document(existing['id'], archived=False)
            return self.document(existing['id'])
        doc_id = uuid.uuid4().hex
        target = self.root / 'originals' / (doc_id + '.pdf')
        cover = self.root / 'covers' / (doc_id + '.png')
        try:
            with fitz.open(stream=raw, filetype='pdf') as doc:
                if doc.needs_pass and not doc.authenticate(password):
                    raise ValueError('PDF parola korumalı. Doğru parolayla tekrar ekleyin.')
                if not len(doc):
                    raise ValueError('PDF içinde sayfa yok.')
                # Parola saklanmaz; korumalı dosyanın yerel çalışma kopyası çözülür.
                stored = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE) if doc.is_encrypted or password else raw
                title = (doc.metadata.get('title') or src.stem).strip() or src.stem
                pages = len(doc)
                rows = [(doc_id, i+1, p.get_text(sort=True), json.dumps(p.get_text('words', sort=True))) for i,p in enumerate(doc)]
                doc[0].get_pixmap(matrix=fitz.Matrix(180/doc[0].rect.width,180/doc[0].rect.width),alpha=False).save(str(cover))
            with target.open('xb') as f:
                f.write(stored)
                f.flush(); os.fsync(f.fileno())
            with self.db() as db:
                db.execute('INSERT INTO documents(id,sha,title,filename,pages,created) VALUES(?,?,?,?,?,?)', (doc_id,digest,title,src.name,pages,time.time()))
                db.executemany('INSERT INTO page_text VALUES(?,?,?,?)', rows)
                db.executemany('INSERT INTO search_index(doc_id,page,text) VALUES(?,?,?)', [r[:3] for r in rows])
                self._log(db,'import',doc_id)
        except sqlite3.IntegrityError:
            target.unlink(missing_ok=True); cover.unlink(missing_ok=True)
            with self.db() as db:
                existing = db.execute('SELECT id FROM documents WHERE sha=?',(digest,)).fetchone()
            if existing: return self.document(existing['id'])
            raise
        except Exception:
            target.unlink(missing_ok=True); cover.unlink(missing_ok=True)
            raise
        return self.document(doc_id)

    def _log(self, db, action, doc_id):
        db.execute('INSERT INTO activity(at,action,doc_id) VALUES(?,?,?)',(time.time(),action,doc_id))

    def update_document(self, doc_id, **fields):
        self.document(doc_id)
        allowed = {'title','collection','tags','favorite','archived'}
        if set(fields) - allowed: raise ValueError('Geçersiz alan.')
        with self.db() as db:
            for k,v in fields.items():
                if k in ('favorite','archived'): v=int(bool(v))
                else:
                    v=str(v).strip()[:1000]
                    if k=='title' and not v: raise ValueError('Başlık boş olamaz.')
                db.execute(f'UPDATE documents SET {k}=? WHERE id=?',(v,doc_id))
            self._log(db,'metadata',doc_id)
        if 'collection' in fields:  # koleksiyon adı = raf adı; raf yoksa açılır
            s=self.shelf_for_name(fields['collection']); self.move_to_shelf(doc_id,s['id'] if s else '')
        return self.document(doc_id)

    def get_state(self, doc_id):
        self.document(doc_id)
        with self.db() as db:
            row=db.execute('SELECT data FROM state WHERE doc_id=?',(doc_id,)).fetchone()
        data=json.loads(row['data']) if row else {'page':1,'offset':0,'zoom':1.0}
        data.setdefault('seen',[]); data.setdefault('layout','auto'); return data

    def save_state(self, doc_id, page, offset=0, zoom=1.0, seen=None, layout=None):
        """seen: görülen sayfa numaraları (ilerleme). layout: 'auto'|'slide'|'book' (kullanıcı tercihi). None verilirse eskisi korunur."""
        d=self.check_page(doc_id,page)
        if not all(math.isfinite(float(x)) for x in (offset,zoom)): raise ValueError('Geçersiz konum.')
        old=self.get_state(doc_id)
        data={'page':page,'offset':max(0,min(float(offset),1)), 'zoom':max(.25,min(float(zoom),4))}
        if layout is None: layout=old.get('layout','auto')
        if layout not in ('auto','slide','book'): raise ValueError('Düzen auto/slide/book olmalı.')
        data['layout']=layout
        if seen is None: seen=old.get('seen',[])
        data['seen']=sorted({int(p) for p in seen if isinstance(p,int) and not isinstance(p,bool) and 1<=p<=d['pages']})
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO state VALUES(?,?)',(doc_id,json.dumps(data)))
            db.execute('UPDATE documents SET opened=? WHERE id=?',(time.time(),doc_id))
        return data

    def check_page(self, doc_id, page):
        d=self.document(doc_id)
        if isinstance(page,bool) or not isinstance(page,int) or not 1<=page<=d['pages']:
            raise ValueError(f"Sayfa 1–{d['pages']} arasında olmalı.")
        return d

    def read_pages(self, doc_id, start=1, end=0, max_chars=24000):
        d=self.check_page(doc_id,start)
        end=end or min(d['pages'],start+9)
        self.check_page(doc_id,end)
        if end<start or end-start>49: raise ValueError('Bir çağrıda en fazla 50 sayfa, artan aralık kullanın.')
        budget=max(500,min(int(max_chars),60000)); result=[]; truncated=False
        with self.db() as db:
            rows=db.execute('SELECT page,text FROM page_text WHERE doc_id=? AND page BETWEEN ? AND ? ORDER BY page',(doc_id,start,end)).fetchall()
        for row in rows:
            if budget<=0: truncated=True; break
            txt=row['text']; clipped=txt[:budget]; budget-=len(clipped)
            result.append({'page':row['page'],'text':clipped,'needs_ocr':not bool(txt.strip())})
            truncated |= len(clipped)<len(txt)
        return {'document_id':doc_id,'title':d['title'],'pages':result,'truncated':truncated,'content_is_untrusted_document_data':True}

    def search(self, query, doc_id='', limit=50):
        if doc_id: self.document(doc_id)
        terms=query.strip().split()[:16]
        if not terms: return []
        literal=' AND '.join('"'+t.replace('"','""')+'"' for t in terms)
        args=[literal]
        where=''
        if doc_id: where=' AND s.doc_id=?'; args.append(doc_id)
        args.append(max(1,min(int(limit),100)))
        with self.db() as db:
            rows=db.execute('''SELECT s.doc_id, CAST(s.page AS INTEGER) AS page, d.title,
                snippet(search_index,2,'[',']',' … ',28) AS excerpt
                FROM search_index s JOIN documents d ON d.id=s.doc_id
                WHERE search_index MATCH ? AND d.archived=0'''+where+' ORDER BY rank LIMIT ?',args).fetchall()
        return [dict(r) for r in rows]

    @pdf_locked
    def geometry(self, doc_id):
        with fitz.open(self.path(doc_id)) as doc:
            # matrix: saklanan (döndürülmemiş) PDF noktasını görüntülenen sayfa noktasına çevirir; işaretleme katmanı kullanır.
            return [{'width':p.rect.width,'height':p.rect.height,'rotation':p.rotation,'matrix':list(p.rotation_matrix)} for p in doc]

    @pdf_locked
    def toc(self,doc_id):
        with fitz.open(self.path(doc_id)) as doc: return doc.get_toc()

    @pdf_locked
    def words(self,doc_id,page):
        self.check_page(doc_id,page)
        with self.db() as db:
            row=db.execute('SELECT words FROM page_text WHERE doc_id=? AND page=?',(doc_id,page)).fetchone()
        with fitz.open(self.path(doc_id)) as doc:
            matrix=doc[page-1].rotation_matrix
            return [list(fitz.Rect(w[:4])*matrix)+list(w[4:]) for w in json.loads(row['words'])]

    def annotations(self, doc_id, page=0):
        self.document(doc_id)
        with self.db() as db:
            rows=db.execute('SELECT * FROM annotations WHERE doc_id=?'+(' AND page=?' if page else '')+' ORDER BY created', (doc_id,page) if page else (doc_id,)).fetchall()
        return [{**dict(r),'data':json.loads(r['data'])} for r in rows]

    @pdf_locked
    def add_annotation(self, doc_id, page, kind, data):
        self.check_page(doc_id,page)
        if kind not in {'ink','highlight','underline','rect','arrow','note','bookmark'}: raise ValueError('Geçersiz işaretleme türü.')
        data=json.loads(json.dumps(data,allow_nan=False))
        color=data.get('color','#e5ab42')
        if not isinstance(color,str) or len(color)!=7 or color[0]!='#': raise ValueError('Renk #RRGGBB olmalı.')
        try: int(color[1:],16)
        except ValueError: raise ValueError('Geçersiz renk.')
        data['color']=color
        width=float(data.get('width',2))
        if not math.isfinite(width) or not .5<=width<=24: raise ValueError('Kalınlık 0.5–24 olmalı.')
        data['width']=width; data['text']=str(data.get('text',''))[:12000]
        # Public coordinates are displayed page points. Store unrotated PDF points.
        with fitz.open(self.path(doc_id)) as doc:
            p=doc[page-1]; matrix=p.derotation_matrix
            def point(v):
                if len(v)!=2 or not all(math.isfinite(float(n)) for n in v): raise ValueError('Geçersiz nokta.')
                x,y=map(float,v)
                if not 0<=x<=p.rect.width or not 0<=y<=p.rect.height: raise ValueError('Nokta sayfa dışında.')
                return list(fitz.Point(x,y)*matrix)
            if kind=='ink':
                pts=data.get('points',[])
                if not 2<=len(pts)<=20000: raise ValueError('Çizim 2–20000 nokta içermeli.')
                data['points']=[point(v) for v in pts]
            elif kind in {'highlight','underline','rect'}:
                rects=data.get('rects',[])
                if not 1<=len(rects)<=1000: raise ValueError('Dikdörtgen gerekli.')
                transformed=[]
                for r in rects:
                    if len(r)!=4: raise ValueError('Dikdörtgen dört sayı içermeli.')
                    point(r[:2]); point(r[2:])
                    rr=fitz.Rect(r)
                    if rr.is_empty: raise ValueError('Boş dikdörtgen.')
                    if kind in {'highlight','underline'}:
                        transformed.append([list(q*matrix) for q in (rr.tl,rr.tr,rr.bl,rr.br)])
                    else: transformed.append(list(rr*matrix))
                data['quads' if kind in {'highlight','underline'} else 'rects']=transformed
            elif kind=='arrow':
                pts=data.get('points',[])
                if len(pts)!=2: raise ValueError('Ok için iki nokta gerekli.')
                data['points']=[point(v) for v in pts]
            else:
                data['point']=point(data.get('point',[24,24]))
        item={'id':uuid.uuid4().hex,'doc_id':doc_id,'page':page,'kind':kind,'data':data,'created':time.time()}
        with self.db() as db:
            self._put_annotation(db,item)
            self._history(db,doc_id,None,item)
        return item

    def _put_annotation(self,db,a):
        db.execute('INSERT OR REPLACE INTO annotations VALUES(?,?,?,?,?,?)',(a['id'],a['doc_id'],a['page'],a['kind'],json.dumps(a['data'],ensure_ascii=False),a['created']))

    def _history(self,db,doc_id,before,after):
        db.execute('DELETE FROM history WHERE doc_id=? AND undone=1',(doc_id,))
        db.execute('INSERT INTO history(doc_id,before_json,after_json) VALUES(?,?,?)',(doc_id,json.dumps(before),json.dumps(after)))
        self._log(db,'annotation',doc_id)

    def update_annotation_text(self,doc_id,annotation_id,text):
        """Not/işaretleme metnini değiştirir; geçmişe girer, geri alınabilir."""
        self.document(doc_id); text=str(text)[:12000]
        with self.db() as db:
            row=db.execute('SELECT * FROM annotations WHERE id=? AND doc_id=?',(annotation_id,doc_id)).fetchone()
            if not row: raise ValueError('İşaretleme bulunamadı.')
            before={**dict(row),'data':json.loads(row['data'])}; after={**before,'data':{**before['data'],'text':text}}
            self._put_annotation(db,after); self._history(db,doc_id,before,after)
        return after

    def delete_annotation(self,doc_id,annotation_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM annotations WHERE id=? AND doc_id=?',(annotation_id,doc_id)).fetchone()
            if not row: raise ValueError('İşaretleme bulunamadı.')
            old={**dict(row),'data':json.loads(row['data'])}
            db.execute('DELETE FROM annotations WHERE id=?',(annotation_id,))
            self._history(db,doc_id,old,None)
        return {'deleted':annotation_id}

    def undo(self,doc_id,redo=False):
        self.document(doc_id)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM history WHERE doc_id=? AND undone=? ORDER BY seq '+('ASC' if redo else 'DESC')+' LIMIT 1',(doc_id,int(redo))).fetchone()
            if not row: return False
            before=json.loads(row['before_json']); after=json.loads(row['after_json'])
            remove=before if redo else after; insert=after if redo else before
            if remove: db.execute('DELETE FROM annotations WHERE id=?',(remove['id'],))
            if insert: self._put_annotation(db,insert)
            db.execute('UPDATE history SET undone=? WHERE seq=?',(0 if redo else 1,row['seq']))
            self._log(db,'redo' if redo else 'undo',doc_id)
        return True

    @staticmethod
    def _apply(p,a):
        d=a['data']; kind=a['kind']; ann=None
        color=tuple(int(d['color'][i:i+2],16)/255 for i in (1,3,5))
        if kind=='ink': ann=p.add_ink_annot([d['points']])
        elif kind in ('highlight','underline'):
            quads=[fitz.Quad([fitz.Point(v) for v in q]) for q in d['quads']]
            ann=p.add_highlight_annot(quads) if kind=='highlight' else p.add_underline_annot(quads)
        elif kind=='rect': ann=p.add_rect_annot(fitz.Rect(d['rects'][0]))
        elif kind=='arrow':
            ann=p.add_line_annot(*[fitz.Point(v) for v in d['points']]); ann.set_line_ends(0,4)
        elif kind=='note': ann=p.add_text_annot(fitz.Point(d['point']),d['text'])
        if ann:
            ann.set_colors(stroke=color)
            if kind not in ('highlight','note'): ann.set_border(width=d['width'])
            ann.set_info(content=d.get('text',''),title='Okuma Atölyesi',subject=kind)
            ann.update(opacity=.4 if kind=='highlight' or d.get('marker') else 1)  # serbest fosfor izi de yarı saydam

    @staticmethod
    def _pixmap(p,scale,alpha=False):
        # Aşırı büyük özel sayfalarda piksel bütçesi. alpha=True: sayfanın boş zemini saydam kalır (okuyucu zemini gösterir).
        scale=min(max(.1,float(scale)),3, math.sqrt(12_000_000/(p.rect.width*p.rect.height)))
        return p.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=alpha)

    @pdf_locked
    def render(self,doc_id,page,scale=1.5):
        self.check_page(doc_id,page)
        with fitz.open(self.path(doc_id)) as doc:
            p=doc[page-1]
            for a in self.annotations(doc_id,page): self._apply(p,a)
            p=doc.reload_page(p)
            return self._pixmap(p,scale).tobytes('png')

    def renderer(self,doc_id):
        if not hasattr(self,'_render_process'): self._render_process=RenderProcess()
        return PageRenderer(self,doc_id,self._render_process)

    def start_render_process(self):
        """Üretim sürecini önceden başlatır ki ilk sayfa istenirken süreç açılışı (≈0,5 s) beklenmesin."""
        if not hasattr(self,'_render_process'): self._render_process=RenderProcess()
        if self._render_process.proc is None: self._render_process.start()

    def stop_render_process(self):
        if hasattr(self,'_render_process'): self._render_process.stop()

    @pdf_locked
    def export_pdf(self,doc_id,pages=None,rotation=0):
        d=self.document(doc_id)
        if rotation not in (0,90,180,270): raise ValueError('Döndürme 0,90,180,270 olmalı.')
        if pages is None: pages=list(range(1,d['pages']+1))
        if not pages or len(pages)>10000: raise ValueError('Geçersiz sayfa listesi.')
        # Sayfa başına ayrı SQLite sorgusu yerine tek belge kaydıyla doğrula (200 sayfa: 1,5 s → 0).
        if any(isinstance(n,bool) or not isinstance(n,int) or not 1<=n<=d['pages'] for n in pages):
            raise ValueError(f"Sayfa 1–{d['pages']} arasında olmalı.")
        with fitz.open(self.path(doc_id)) as doc:
            for a in self.annotations(doc_id): self._apply(doc[a['page']-1],a)
            # select also supports reorder/repeated pages and preserves annotations.
            doc.select([p-1 for p in pages])
            for p in doc: p.set_rotation((p.rotation+rotation)%360)
            out=self._write_export(doc.tobytes(garbage=4,deflate=True),'.pdf')
        return {'path':str(out),'pages':len(pages)}

    @pdf_locked
    def merge(self,doc_ids):
        if not 2<=len(doc_ids)<=30: raise ValueError('2–30 belge seçin.')
        with fitz.open() as result:
            for doc_id in doc_ids:
                with fitz.open(self.path(doc_id)) as doc:
                    for a in self.annotations(doc_id): self._apply(doc[a['page']-1],a)
                    result.insert_pdf(doc)
            out=self._write_export(result.tobytes(garbage=4,deflate=True),'.pdf')
        return {'path':str(out)}

    def _write_export(self,content,suffix):
        folder=(self.root/'exports').resolve()
        out=folder/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+suffix)
        try:
            with out.open('xb') as f: f.write(content); f.flush(); os.fsync(f.fileno())
        except Exception:
            out.unlink(missing_ok=True); raise
        return out

    def export_notes(self,doc_id):
        d=self.document(doc_id)
        lines=['# '+d['title'],'',f"Belge kimliği: {doc_id}",'']
        for a in self.annotations(doc_id):
            lines.extend([f"## Sayfa {a['page']} · {a['kind']}",a['data'].get('text') or '(Çizim / işaretleme)', ''])
        return {'path':str(self._write_export('\n'.join(lines).encode('utf-8'),'.md'))}

    @pdf_locked
    def ocr(self,doc_id,start=1,end=0,language='tur+eng'):
        d=self.check_page(doc_id,start); end=end or start; self.check_page(doc_id,end)
        if end<start or end-start>19: raise ValueError('OCR için en fazla 20 sayfa seçin.')
        if not language or any(c not in 'abcdefghijklmnopqrstuvwxyz_+' for c in language): raise ValueError('Geçersiz OCR dili.')
        rows=[]
        with fitz.open(self.path(doc_id)) as doc:
            for i in range(start-1,end):
                p=doc[i]
                tp=p.get_textpage_ocr(language=language,dpi=150,full=True)
                rows.append((doc_id,i+1,p.get_text(textpage=tp,sort=True),json.dumps(p.get_text('words',textpage=tp,sort=True))))
        with self.db() as db:
            for row in rows:
                db.execute('INSERT OR REPLACE INTO page_text VALUES(?,?,?,?)',row)
                db.execute('DELETE FROM search_index WHERE doc_id=? AND page=?',row[:2])
                db.execute('INSERT INTO search_index(doc_id,page,text) VALUES(?,?,?)',row[:3])
            self._log(db,'ocr',doc_id)
        return {'pages':len(rows),'message':'OCR metni arama ve metin seçimi için kaydedildi; PDF dosyası değişmedi.'}

    def queue_open(self,doc_id,page=1):
        self.check_page(doc_id,page)
        with self.db() as db:
            db.execute('INSERT INTO commands(doc_id,page,created) VALUES(?,?,?)',(doc_id,page,time.time()))

    def take_commands(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT * FROM commands WHERE created>? ORDER BY id',(time.time()-120,)).fetchall()
            db.execute('DELETE FROM commands')
        return [dict(r) for r in rows]

    def revision(self):
        with self.db() as db:
            return db.execute('SELECT COALESCE(MAX(id),0) FROM activity').fetchone()[0]

    def move_to(self,new_root):
        """Veri klasörünü başka bir yere kopyalar (DB tutarlı anlık görüntüyle), doğrular ve işaretçiyi yeni yola çevirir.
        Eski klasöre dokunmaz; yeni yol bir sonraki açılışta geçerlidir. Dönüş: yeni kök."""
        import shutil
        new_root=Path(new_root).expanduser().resolve()
        if new_root==self.root: raise ValueError('Zaten bu klasörde.')
        if new_root.is_relative_to(self.root) or self.root.is_relative_to(new_root): raise ValueError('Yeni klasör eskisinin içinde ya da dışında iç içe olamaz.')
        if new_root.exists() and any(new_root.iterdir()): raise ValueError('Hedef klasör boş olmalı.')
        new_root.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(new_root/'library.sqlite3')) as dst: self._connection().backup(dst)
        for sub in ('originals','covers','exports','imports'):
            src=self.root/sub; (new_root/sub).mkdir(exist_ok=True)
            if src.exists():
                for f in src.iterdir():
                    if f.is_file(): shutil.copy2(f,new_root/sub/f.name)
        # Doğrulama: belge sayısı ve her belgenin PDF'i yerinde mi
        with closing(sqlite3.connect(new_root/'library.sqlite3')) as db:
            ids=[r[0] for r in db.execute('SELECT id FROM documents')]; n_old=self.list_documents(limit=1000,archived=False)
        missing=[i for i in ids if not (new_root/'originals'/(i+'.pdf')).exists()]
        if missing: raise ValueError(f'Kopya eksik: {len(missing)} PDF taşınamadı, işaretçi değiştirilmedi.')
        set_default_data_dir(new_root); return new_root

    def backup(self):
        import zipfile
        import tempfile
        with tempfile.TemporaryDirectory(prefix='okuma-backup-') as tmp:
            dbcopy=Path(tmp)/'library.sqlite3'
            with self.db() as source:
                target=sqlite3.connect(dbcopy)
                try: source.backup(target)
                finally: target.close()
            out=self.root/'exports'/('yedek-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.zip')
            try:
                with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED) as z:
                    z.write(dbcopy,'library.sqlite3')
                    # DB snapshot'taki dosyalar alınır; eşzamanlı içe aktarma yedeği değiştirmez.
                    # sqlite3'te `with conn` kapatmaz; açık kalan kopya Windows'ta geçici klasörün silinmesini engelliyordu.
                    with closing(sqlite3.connect(dbcopy)) as db: ids=[r[0] for r in db.execute('SELECT id FROM documents')]
                    for id_ in ids:
                        for sub,ext in [('originals','.pdf'),('covers','.png')]:
                            p=self.root/sub/(id_+ext)
                            if p.exists(): z.write(p,str(p.relative_to(self.root)))
            except Exception:
                out.unlink(missing_ok=True); raise
        return {'path':str(out)}

    def save_reader_context(self,doc_id,page,selection='',selection_page=0):
        self.check_page(doc_id,page)
        if selection_page: self.check_page(doc_id,selection_page)
        data={'is_open':True,'state':'reading','document_id':doc_id,'page':page,'selection':selection[:24000], 'selection_page':selection_page or page,'updated':time.time(), 'content_is_untrusted_document_data':True}
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reader_context (id INTEGER PRIMARY KEY, data TEXT)')
            db.execute('INSERT OR REPLACE INTO reader_context VALUES(1,?)',(json.dumps(data),))

    def reader_context(self):
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reader_context (id INTEGER PRIMARY KEY, data TEXT)')
            row=db.execute('SELECT data FROM reader_context WHERE id=1').fetchone()
        data=json.loads(row['data']) if row else {'document_id':None,'selection':''}
        live=data.get('is_open',False) and time.time()-data.get('updated',0)<8
        if not live:
            return {'is_open':False,'state':'closed','document_id':None,'selection':'','last_document_id':data.get('document_id'),'updated':data.get('updated',0)}
        return data

    def publish_reader(self, state, doc_id=None, page=1, selection='', selection_page=0):
        data={'is_open':state!='closed','state':state,'document_id':doc_id if state=='reading' else None,
              'page':page if state=='reading' else None,'selection':selection[:24000] if state=='reading' else '',
              'selection_page':selection_page or page,'updated':time.time(),'pid':os.getpid(),
              'content_is_untrusted_document_data':True}
        if data['document_id']: data['title']=self.document(doc_id)['title']
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reader_context (id INTEGER PRIMARY KEY, data TEXT)')
            db.execute('INSERT OR REPLACE INTO reader_context VALUES(1,?)',(json.dumps(data),))
        return data

    def request_reader(self, action, doc_id=None, page=1):
        if action not in ('open','library','close'): raise ValueError('Geçersiz okuyucu işlemi.')
        if action=='open': self.check_page(doc_id,page)
        key=uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO reader_commands VALUES(?,?,?,?,?,?,?)',(key,action,doc_id,page,time.time(),'pending','{}'))
        return key

    def pending_reader_commands(self):
        with self.db() as db:
            db.execute("UPDATE reader_commands SET status='expired' WHERE status='pending' AND created<?",(time.time()-30,))
            return [dict(r) for r in db.execute("SELECT * FROM reader_commands WHERE status='pending' ORDER BY created")]

    def finish_reader_command(self, key, result, status='done'):
        with self.db() as db: db.execute('UPDATE reader_commands SET status=?,result=? WHERE id=?',(status,json.dumps(result),key))

    def reader_command(self, key):
        with self.db() as db:
            db.execute("UPDATE reader_commands SET status='expired' WHERE id=? AND status='pending' AND created<?",(key,time.time()-30))
            row=db.execute('SELECT * FROM reader_commands WHERE id=?',(key,)).fetchone()
        if not row: raise ValueError('Okuyucu isteği bulunamadı.')
        return {'request_id':key,'status':row['status'],**json.loads(row['result'])}

    def read_chunk(self, doc_id, page=1, offset=0, max_chars=3000):
        doc=self.check_page(doc_id,page)
        if offset<0: raise ValueError('Metin konumu negatif olamaz.')
        with self.db() as db: row=db.execute('SELECT text FROM page_text WHERE doc_id=? AND page=?',(doc_id,page)).fetchone()
        body=row['text'] if row else ''
        if offset>len(body): raise ValueError('Metin konumu sayfa uzunluğunu aşıyor.')
        end=min(len(body),offset+max(100,min(int(max_chars),3000)))
        next_=({'page':page,'offset':end} if end<len(body) else {'page':page+1,'offset':0} if page<doc['pages'] else None)
        return {'document_id':doc_id,'title':doc['title'][:200],'page':page,'offset':offset,'text':body[offset:end],
                'needs_ocr':not bool(body.strip()),'next':next_,'page_complete':end==len(body),'content_is_untrusted_document_data':True}

    @pdf_locked
    def highlight_text(self,doc_id,page,text,color='#e5ab42'):
        self.check_page(doc_id,page)
        if not text.strip() or len(text)>5000: raise ValueError('Alıntı 1–5000 karakter olmalı.')
        with fitz.open(self.path(doc_id)) as doc:
            p=doc[page-1]; matches=p.search_for(text,quads=True)
            if not matches: raise ValueError('Alıntı PDF metin katmanında bulunamadı. OCR sayfasında okuyucunun fosfor aracını kullan.')
            rects=[list(q.rect*p.rotation_matrix) for q in matches[:1000]]
        return self.add_annotation(doc_id,page,'highlight',{'rects':rects,'text':text,'color':color})


def render_page_samples(path, page, scale, annotations=(), cache=None, alpha=False):
    """Bir sayfanın örneklerini üretir: (bytes, genişlik, yükseklik, satır uzunluğu, kanal sayısı). Üretim sürecinde çalışır.

    İşaretlemesi olmayan sayfa, önbellekte açık tutulan belgeden üretilir. İşaretlemeli sayfa, işaretlemeler sayfaya
    işlendiği için taze bir kopyadan üretilir; kalıcı belge kirlenmez, aynı işaretleme iki kez işlenmez."""
    if annotations:
        with fitz.open(path) as doc:
            p=doc[page-1]
            for a in annotations: Library._apply(p,a)
            pix=Library._pixmap(doc.reload_page(p),scale,alpha)
    else:
        doc=None if cache is None else cache.get(path)
        if doc is None:
            doc=fitz.open(path)
            if cache is not None:
                while len(cache)>=2: cache.pop(next(iter(cache))).close()
                cache[path]=doc
        pix=Library._pixmap(doc[page-1],scale,alpha)
    if alpha and pix.n==4:
        # Zemine beyaz dikdörtgen çizen PDF'lerde (sunum çıktıları) saf beyaz da saydam olsun; okuyucu zemini görünür.
        # Mevcut alfa korunur (zemin çizmeyen PDF'de saydam pikseller siyah olmasın); beyaz da saydam yapılır.
        pix.set_alpha(bytes(pix.samples_mv[3::4]),opaque=(255,255,255))
    return pix.samples, pix.width, pix.height, pix.stride, pix.n


class RenderProcess:
    """Sayfa görüntülerini ayrı bir süreçte üretir (render_worker.py).

    Neden süreç, iş parçacığı değil: PyMuPDF 1.26 C çağrıları boyunca GIL'i bırakmaz. Aynı süreçteki bir işçi
    iş parçacığı sayfa üretirken arayüzün Python tarafı (tekerlek, kalem, sinyaller) o kadar donar; ölçülen:
    görüntü tabanlı slaytta sayfa başına 100+ ms. Ayrı süreçte kendi GIL'i vardır; sonuç ham RGB olarak borudan
    okunur ve boru okuması GIL'i bırakır. Üretim artık ana sürecin PDF_LOCK'u için de yarışmaz."""
    def __init__(self):
        self.proc=None; self.lock=threading.Lock(); self.seq=0

    def start(self):
        import subprocess
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        self.proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('render_worker.py'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,cwd=str(Path(__file__).parent),creationflags=flags)

    def render(self, path, page, scale, annotations=(), alpha=False):
        """İstek gönderir, örnekleri okur: (bytes, w, h, stride, kanal). Süreç ölmüşse bir kez yeniden başlatır. Hata metnini ValueError olarak yükseltir."""
        with self.lock:
            for attempt in (1,2):
                if self.proc is None or self.proc.poll() is not None: self.start()
                self.seq+=1
                try:
                    self.proc.stdin.write((json.dumps({'id':self.seq,'path':str(path),'page':page,'scale':scale,'annotations':list(annotations),'alpha':bool(alpha)})+'\n').encode('utf-8')); self.proc.stdin.flush()
                    header=self.proc.stdout.readline()
                    if not header: raise BrokenPipeError('üretim süreci yanıt vermedi')
                    h=json.loads(header)
                    if 'error' in h: raise ValueError(h['error'])
                    data=self.proc.stdout.read(h['n'])
                    if len(data)!=h['n']: raise BrokenPipeError('eksik veri')
                    return data,h['w'],h['h'],h['stride'],h.get('channels',3)
                except (BrokenPipeError,OSError,json.JSONDecodeError):
                    self.stop()
                    if attempt==2: raise
        return None

    def stop(self):
        p=self.proc; self.proc=None
        if p is None: return
        try:
            if p.stdin: p.stdin.close()
            p.wait(2)
        except Exception:
            # Windows'ta sanal ortamın python.exe'si bir yönlendiricidir; asıl süreç onun çocuğu. Ağacı kapat.
            try:
                if os.name=='nt':
                    import subprocess; subprocess.run(['taskkill','/PID',str(p.pid),'/F','/T'],capture_output=True)
                else: p.kill()
            except Exception: pass


class PageRenderer:
    """Açık bir belge için sayfa görüntüsü isteyen taraf. Okuyucunun işçi iş parçacığından çağrılır.

    Yalnızca PDF'nin kendi içeriği üretilir; bu uygulamanın işaretlemeleri okuyucuda ayrı bir katmanda çizilir
    (app.AnnotationItem). Böylece işaretleme eklemek/silmek sayfa görüntüsünü yenilemez."""
    def __init__(self, lib, doc_id, process):
        self.lib=lib; self.doc_id=doc_id; self.path=lib.path(doc_id); self.process=process; self.closed=False

    def render(self, page, scale):
        """RGBA örnekleri döndürür: (bytes, genişlik, yükseklik, satır uzunluğu, kanal). Zemin saydamdır. Kapalıysa None."""
        if self.closed: return None
        return self.process.render(self.path,page,scale,alpha=True)

    def close(self): self.closed=True
