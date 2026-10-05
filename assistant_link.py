"""Optional local inbox protocol. Standard library only; no dependency on Limina."""
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

TASKS={'explain':'Bu bölümü anlaşılır biçimde açıkla.','summarize':'Bu bölümü kısa ve anlaşılır biçimde özetle.',
       'translate':'Bu bölümü Türkçeye çevir.','questions':'Bu bölümden cevaplarıyla beş çalışma sorusu hazırla.',
       'save_note':'Smart Notes’a kaydet'}

def link_path():
    return Path(os.environ.get('OKUMA_LINK_DB') or Path(os.environ.get('APPDATA') or Path.home()/'.config')/'OkumaAtolyesi'/'assistant.sqlite3')

class AssistantLink:
    def __init__(self, root):
        self.path=link_path(); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.library=hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode()).hexdigest()[:24]
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, path TEXT);
              CREATE TABLE IF NOT EXISTS peer (id INTEGER PRIMARY KEY, updated REAL, projects TEXT);
              CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, created REAL, updated REAL, payload TEXT, status TEXT, reply TEXT);''')
            db.execute('INSERT OR REPLACE INTO sources VALUES(?,?)',(self.library,str(Path(root).resolve())))

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=3); db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def peer(self):
        with self.db() as db: row=db.execute('SELECT * FROM peer WHERE id=1').fetchone()
        return {'connected':bool(row and time.time()-row['updated']<8),'projects':json.loads(row['projects']) if row else []}

    def send(self, task, document_id, page, title, text, workspace_id=None):
        if task not in TASKS: raise ValueError('Bilinmeyen asistan işlemi.')
        if not self.peer()['connected']: raise ValueError('Limina bağlantısı yok. Limina’yı açıp yeniden dene.')
        if len(text)>12000: raise ValueError('Seçim çok uzun; en fazla 12.000 karakter seç.')
        payload={'task':task,'library':self.library,'document_id':document_id,'page':page,'title':title[:200],
                 'text':text,'workspace_id':workspace_id,'source':f'okuma://{self.library}/{document_id}/{page}'}
        key=uuid.uuid4().hex; now=time.time()
        with self.db() as db:
            db.execute("DELETE FROM requests WHERE updated<? AND status NOT IN ('pending','running')",(now-30*86400,))
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)',(key,now,now,json.dumps(payload,ensure_ascii=False),'pending',''))
        return key

    def request(self, key):
        with self.db() as db: row=db.execute('SELECT * FROM requests WHERE id=?',(key,)).fetchone()
        return dict(row) if row else None

    def cancel_pending(self, key):
        with self.db() as db: db.execute("UPDATE requests SET status='cancelled',updated=? WHERE id=? AND status='pending'",(time.time(),key))
