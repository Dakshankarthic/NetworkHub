"""Download pinned upstream binaries, verify SHA-256, extract named files only."""
from pathlib import Path
import hashlib
import io
import json
import argparse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT/'src'/'bin'
COMPONENTS = [
    {'name':'mihomo', 'version':'v1.19.33',
     'url':'https://github.com/MetaCubeX/mihomo/releases/download/v1.19.33/mihomo-windows-amd64-v3-v1.19.33.zip',
     'sha256':'82f44f07d2b8a539b0885e8bc1afdac158448b75004f7605e0ec8c4086293b09'},
    {'name':'wintun', 'version':'0.14.1',
     'url':'https://www.wintun.net/builds/wintun-0.14.1.zip',
     'sha256':'07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51'},
]


def fetch(component, cache=None):
    cached = Path(cache)/(component['name']+'.zip') if cache else None
    if cached and cached.exists():
        data = cached.read_bytes()
    else:
        request = urllib.request.Request(component['url'], headers={'User-Agent':'NetworkHub-Setup/0.1'})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != component['sha256']:
        raise RuntimeError(f"Hash mismatch for {component['name']}; nothing extracted")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if component['name'] == 'mihomo':
            names = [name for name in archive.namelist() if name.lower().endswith('.exe')]
            if len(names) != 1:
                raise RuntimeError('Unexpected engine archive contents')
            (TARGET/'mihomo.exe').write_bytes(archive.read(names[0]))
        else:
            (TARGET/'wintun.dll').write_bytes(archive.read('wintun/bin/amd64/wintun.dll'))
            (TARGET/'WINTUN-LICENSE.txt').write_bytes(archive.read('wintun/LICENSE.txt'))
    print(f"Verified and installed {component['name']} {component['version']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', help='Optional folder containing mihomo.zip and wintun.zip; hashes are still verified')
    args = parser.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    for component in COMPONENTS:
        fetch(component, args.cache_dir)
    (TARGET/'components.json').write_text(json.dumps(COMPONENTS,indent=2),encoding='utf-8')
