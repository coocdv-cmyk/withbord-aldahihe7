"""Download a versioned Lucide archive, preserving attribution and local metadata."""
import io
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / 'library'
VERSION = '1.59.0'

def install():
    LIB.mkdir(exist_ok=True)
    url = f'https://registry.npmjs.org/lucide-static/-/lucide-static-{VERSION}.tgz'
    req = urllib.request.Request(url, headers={'User-Agent': 'WhiteboardStudio/1.0'})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read(40_000_000)
    records = []
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive.getmembers():
            p = Path(member.name)
            if member.isfile() and p.suffix == '.svg' and p.parent.name == 'icons':
                name = p.stem
                svg = archive.extractfile(member).read()
                (LIB / f'{name}.svg').write_bytes(svg)
                records.append({'id': name, 'name': name.replace('-', ' '), 'source': 'Lucide',
                                'license': 'ISC / MIT (Feather-derived)', 'version': VERSION,
                                'tags': name.replace('-', ' ').split(), 'file': f'{name}.svg'})
            elif member.isfile() and p.name.lower().startswith('license'):
                (LIB / 'LUCIDE-LICENSE.txt').write_bytes(archive.extractfile(member).read())
    if len(records) < 100:
        raise RuntimeError('Archive layout changed: incomplete library')
    existing=LIB/'catalog.json'
    preserved=[r for r in json.loads(existing.read_text(encoding='utf-8')) if r.get('source')!='Lucide'] if existing.exists() else []
    existing.write_text(json.dumps(records+preserved, ensure_ascii=False), encoding='utf-8')
    print(f'Installed {len(records)} vector assets from Lucide {VERSION}', flush=True)

if __name__ == '__main__':
    install()
