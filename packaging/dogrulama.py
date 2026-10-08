"""Bounded package probes; only child processes started here are stopped."""
from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path


def ortam(kok: Path) -> dict[str, str]:
    """Create disposable data roots without inheriting user policy or secrets."""
    kok = kok.resolve()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('PEVRAI_', 'LIMINA_', 'OKUMA_', 'KEYRING_PROPERTY_'))
           and not k.endswith(('_API_KEY', '_TOKEN', '_PASSWORD'))
           and k != 'GOOGLE_APPLICATION_CREDENTIALS'}
    for name in ('ev', 'appdata', 'localappdata', 'vekil'):
        (kok/name).mkdir(parents=True, exist_ok=True)
    config = kok/'localappdata'/'Pevrai'/'config'
    config.mkdir(parents=True, exist_ok=True)
    (config/'arayuz.toml').write_text('[genel]\nguncellemeleri_denetle = false\n', encoding='utf-8')
    settings = kok/'ayarlar.ini'
    settings.write_text('[General]\nguncellemeleri_denetle=false\n', encoding='utf-8')
    env.update(USERPROFILE=str(kok/'ev'), HOME=str(kok/'ev'),
               APPDATA=str(kok/'appdata'), LOCALAPPDATA=str(kok/'localappdata'),
               PEVRAI_VEKIL_KOK=str(kok/'vekil'), OKUMA_DATA_DIR=str(kok/'veri'),
               OKUMA_LINK_DB=str(kok/'link.sqlite3'), OKUMA_SETTINGS=str(settings),
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
               PYTHON_KEYRING_BACKEND='keyring.backends.null.Keyring')
    return env


async def _bosalt(akis, kuyruk: bytearray | None = None):
    while veri := await akis.read(8192):
        if kuyruk is not None:
            kuyruk.extend(veri)
            del kuyruk[:-4096]


async def _kapat(proc, stderr_task):
    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    # Drain stdout as well: a full pipe must not prevent process cleanup.
    stdout_task = asyncio.create_task(_bosalt(proc.stdout))
    try:
        await asyncio.wait_for(asyncio.gather(proc.wait(), stdout_task, stderr_task), 5)
    finally:
        proc.stdin.close() if proc.stdin is not None else None
        for task in (stdout_task, stderr_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)


async def _sorgula(komut, istek, env, timeout, ikili_alan, azami_bayt):
    proc = await asyncio.create_subprocess_exec(*komut, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, limit=65536)
    stderr = bytearray()
    stderr_task = asyncio.create_task(_bosalt(proc.stderr, stderr))
    async def cevap():
        proc.stdin.write((json.dumps(istek) + '\n').encode('utf-8'))
        await proc.stdin.drain()
        while True:
            line = await proc.stdout.readline()
            if not line:
                raise ValueError('Process exited without a response')
            if line.strip():
                break
        header = json.loads(line)
        if not isinstance(header, dict):
            raise ValueError('Response must be a JSON object')
        data = b''
        if ikili_alan is not None and 'error' not in header:
            count = header.get(ikili_alan)
            if type(count) is not int or not 0 < count <= azami_bayt:
                raise ValueError('Invalid binary response length')
            data = await proc.stdout.readexactly(count)
        return header, data
    try:
        return await asyncio.wait_for(cevap(), timeout)
    except (TimeoutError, ValueError, asyncio.IncompleteReadError,
            BrokenPipeError, ConnectionResetError) as exc:
        # The diagnostic is bounded, and reading it never waits for EOF.
        detail = stderr.decode('utf-8', 'replace')[-1500:]
        raise RuntimeError(f'Package probe failed: {type(exc).__name__}: {exc}\n{detail}') from exc
    finally:
        await _kapat(proc, stderr_task)


def sorgula(komut, istek, *, env, timeout=60, ikili_alan=None, azami_bayt=16*1024*1024):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Timeout must be finite and positive')
    return asyncio.run(_sorgula(komut, istek, env, timeout, ikili_alan, azami_bayt))


async def _pencere(komut, env, sure):
    proc = await asyncio.create_subprocess_exec(*komut, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stderr = bytearray()
    stderr_task = asyncio.create_task(_bosalt(proc.stderr, stderr))
    stdout_task = asyncio.create_task(_bosalt(proc.stdout))
    try:
        await asyncio.sleep(sure)
        if proc.returncode is not None:
            raise RuntimeError(f'Window exited ({proc.returncode}): {stderr.decode("utf-8", "replace")[-1500:]}')
    finally:
        stdout_task.cancel()
        await asyncio.gather(stdout_task, return_exceptions=True)
        await _kapat(proc, stderr_task)


def pencere_dogrula(komut, *, env, sure=8):
    if not math.isfinite(sure) or sure <= 0:
        raise ValueError('Duration must be finite and positive')
    asyncio.run(_pencere(komut, env, sure))
