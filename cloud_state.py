"""GitHub taramaları arasında fiyat geçmişini şifreli artifact ile taşır."""
import io
import os
import sys
import zipfile
from pathlib import Path
import httpx
from cryptography.fernet import Fernet

NAME = 'encrypted-monitor-state'

def pack(root, key):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in [root/'prices.db', root/'market-cache.json', *root.glob('cursor-*.txt')]:
            if path.is_file(): archive.write(path, path.name)
    return Fernet(key).encrypt(buffer.getvalue())

def unpack(data, root, key):
    import re
    with zipfile.ZipFile(io.BytesIO(Fernet(key).decrypt(data))) as archive:
        for member in archive.infolist():
            if not re.fullmatch(r'prices\.db|market-cache\.json|cursor-[a-f0-9]{12}\.txt', member.filename):
                raise ValueError('Beklenmeyen durum dosyası')
            if member.file_size > 100_000_000: raise ValueError('Durum çok büyük')
        root.mkdir(exist_ok=True)
        for member in archive.infolist():
            (root/member.filename).write_bytes(archive.read(member))

def restore(root, key):
    base = 'https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/artifacts'
    headers = {'Authorization':'Bearer '+os.environ['GH_TOKEN'], 'Accept':'application/vnd.github+json'}
    with httpx.Client(timeout=60) as client:
        response = client.get(base, headers=headers, params={'name':NAME, 'per_page':100})
        response.raise_for_status()
        artifacts = [a for a in response.json()['artifacts'] if not a['expired']]
        if not artifacts:
            if os.getenv('BOOTSTRAP') != 'true':
                raise RuntimeError('Önceki durum bulunamadı; tekrar bildirim riskine karşı tarama durduruldu.')
            root.mkdir(exist_ok=True)
            return
        latest = max(artifacts, key=lambda a:a['created_at'])
        response = client.get(base+'/'+str(latest['id'])+'/zip', headers=headers)
        if response.status_code == 302:
            # GitHub kimlik bilgisini depolama sunucusuna taşımıyoruz.
            response = client.get(response.headers['location'])
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            unpack(archive.read('state.enc'), root, key)

if __name__ == '__main__':
    key = os.environ['STATE_KEY'].encode()
    if sys.argv[1] == 'restore': restore(Path('data'), key)
    elif sys.argv[1] == 'save':
        if not Path('data/prices.db').exists(): raise RuntimeError('Veritabanı yok')
        Path('state.enc').write_bytes(pack(Path('data'), key))
    else: raise ValueError('restore veya save gerekli')
