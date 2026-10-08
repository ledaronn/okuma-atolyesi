"""Sayfa üretim süreci. app.py bunu alt süreç olarak başlatır; stdin'den JSON istek, stdout'a JSON başlık + ham RGB yazar.

Neden ayrı süreç: PyMuPDF C çağrıları boyunca GIL'i bırakmaz; aynı süreçte üretim arayüzü dondurur (bkz. core.RenderProcess).
Protokol: her istek tek satır JSON {id, path, page, scale, annotations, alpha}. Yanıt: tek satır JSON {id, w, h, stride, n, channels} ve ardından n bayt;
hata olursa {id, error}. Belge yolu yalnızca verilen dosyayı okumak için kullanılır; hiçbir şey yazılmaz."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import render_page_samples
from surum import SURUM


def main():
    stdin=sys.stdin.buffer; stdout=sys.stdout.buffer; cache={}
    while True:
        line=stdin.readline()
        if not line: return 0
        req={}
        try:
            req=json.loads(line)
            data,w,h,stride,channels=render_page_samples(req['path'],int(req['page']),float(req['scale']),req.get('annotations') or (),cache,bool(req.get('alpha')))
            stdout.write((json.dumps({'id':req.get('id'),'w':w,'h':h,'stride':stride,'n':len(data),'channels':channels,'version':SURUM})+'\n').encode('utf-8')); stdout.write(data)
        except Exception as e:
            stdout.write((json.dumps({'id':req.get('id'),'error':str(e)})+'\n').encode('utf-8'))
        stdout.flush()


if __name__=='__main__': sys.exit(main())
