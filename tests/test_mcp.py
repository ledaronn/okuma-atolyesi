"""Gerçek stdio MCP oturumuyla keşif, çağrı, hata ve dosya sınırı testi."""
import asyncio
import json
import os
from pathlib import Path
import sys
import pytest
import pymupdf as fitz
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def test_real_stdio_session(tmp_path):
    source=tmp_path/'allowed'; source.mkdir()
    pdf=source/'test.pdf'
    with fitz.open() as d:
        p=d.new_page(); p.insert_text((60,70),'MCP integration sample. Alpha beta.'); d.save(pdf)
    outside=tmp_path/'outside.pdf'; outside.write_bytes(pdf.read_bytes())

    async def run():
        params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'server.py'),'--data-dir',str(tmp_path/'data'),'--allow-read',str(source)],env={**os.environ,'OKUMA_LINK_DB':str(tmp_path/'link.sqlite3')})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as s:
                await s.initialize()
                found=await s.list_tools()
                assert {'open_reader','close_reader','reader_request_status','read_page_chunk','get_outline','ocr_pages'} <= {t.name for t in found.tools}
                async def call(name,args={}):
                    r=await s.call_tool(name,args)
                    assert not r.isError, r.content
                    if r.structuredContent is not None:
                        d=r.structuredContent
                        return d.get('result',d)
                    return json.loads(r.content[0].text)
                doc=await call('import_pdf',{'path':str(pdf)}); id_=doc['id']
                matches=await call('search_documents',{'query':'Alpha'})
                assert matches[0]['doc_id']==id_
                pages=await call('read_pages',{'document_id':id_})
                assert 'MCP integration' in pages['pages'][0]['text']
                chunk=await call('read_page_chunk',{'document_id':id_})
                assert chunk['source_url'].startswith('okuma://') and chunk['next'] is None
                assert (await call('get_outline',{'document_id':id_}))['total']==0
                await call('add_note',{'document_id':id_,'page':1,'text':'AI notu: örnek'})
                await call('highlight_text',{'document_id':id_,'page':1,'text':'Alpha beta'})
                annotations=await call('get_annotations',{'document_id':id_})
                assert len(annotations)==2
                out=await call('export_pdf',{'document_id':id_})
                with fitz.open(out['path']) as result:
                    p=result[0]; assert len(list(p.annots()))==2
                for args in [{'path':str(outside)},{'path':str(source/'..'/'outside.pdf')}]:
                    r=await s.call_tool('import_pdf',args); assert r.isError
                r=await s.call_tool('read_pages',{'document_id':id_,'start':99}); assert r.isError
                # Protokol hatalı araç çağrısından sonra da çalışmalı.
                status=await call('library_status'); assert status['documents']==1
    asyncio.run(run())


def test_mcp_opens_reader_and_reuses_window(tmp_path):
    import signal
    from core import Library
    source=tmp_path/'reader.pdf'
    with fitz.open() as pdf:
        for i in range(2):
            p=pdf.new_page(); p.insert_text((50,50),f'Page {i+1}')
        pdf.save(source)
    lib=Library(tmp_path/'data'); doc=lib.import_pdf(source)
    async def run():
        params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'server.py'),'--data-dir',str(lib.root)],env={**os.environ,'QT_QPA_PLATFORM':'offscreen','OKUMA_LINK_DB':str(tmp_path/'link.sqlite3'),'OKUMA_SETTINGS':str(tmp_path/'settings.ini'),'APPDATA':str(tmp_path/'profile')})
        pid=None
        try:
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as s:
                    await s.initialize()
                    r=await s.call_tool('open_reader',{'document_id':doc['id'],'page':1})
                    assert not r.isError
                    payload=r.structuredContent or json.loads(r.content[0].text); pid=payload['pid']
                    for _ in range(150):
                        context=lib.reader_context()
                        if context.get('document_id')==doc['id']: break
                        await asyncio.sleep(.1)
                    assert context.get('page')==1
                    # İkinci başlatma QLockFile ile var olan pencereye komut bırakır.
                    r=await s.call_tool('open_reader',{'document_id':doc['id'],'page':2}); assert not r.isError
                    for _ in range(100):
                        context=lib.reader_context()
                        if context.get('page')==2: break
                        await asyncio.sleep(.1)
                    assert context.get('page')==2
                    r=await s.call_tool('close_reader',{'to_library':True}); assert not r.isError
                    assert lib.reader_context()['state']=='library'
                    r=await s.call_tool('close_reader',{}); assert not r.isError
                    assert not lib.reader_context()['is_open']
                    pid=None
        finally:
            if pid:
                try: os.kill(pid,signal.SIGTERM)
                except ProcessLookupError: pass
                except PermissionError:
                    # Windows: başka oturumdaki/ayrılmış süreç TerminateProcess ile açılamıyor.
                    import subprocess; subprocess.run(['taskkill','/PID',str(pid),'/F','/T'],capture_output=True)
    asyncio.run(run())
