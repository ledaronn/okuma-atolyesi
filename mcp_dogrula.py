"""Ana AI projesine ihtiyaç duymadan MCP bağlantısını kontrol et."""
import argparse
import asyncio
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def check(data_dir=None):
    args=[str(Path(__file__).resolve().with_name('server.py'))]
    if data_dir: args+=['--data-dir',str(Path(data_dir).expanduser().resolve())]
    params=StdioServerParameters(command=sys.executable,args=args)
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            result=await session.list_tools()
            print(f'{len(result.tools)} araç keşfedildi:')
            for tool in result.tools: print('  '+tool.name)
            status=await session.call_tool('library_status',{})
            if status.isError: raise RuntimeError(str(status.content))
            for part in status.content:
                if hasattr(part,'text'): print(part.text)
            required={'open_reader','close_reader','read_page_chunk','get_reader_context','reader_request_status','get_outline'}
            if not required <= {t.name for t in result.tools}: raise RuntimeError('Güncel okuyucu araçları eksik.')
            print('MCP bağlantısı çalışıyor.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--data-dir'); args=parser.parse_args()
    asyncio.run(check(args.data_dir))
