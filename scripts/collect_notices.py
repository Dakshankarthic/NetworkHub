"""Preserve installed dependency and interpreter notices in a binary distribution."""
from pathlib import Path
import importlib.metadata as metadata
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'dist'/'NetworkHub'/'licenses'
DEST.mkdir(parents=True, exist_ok=True)
versions = {}
for distribution in metadata.distributions():
    name = distribution.metadata['Name']
    versions[name] = distribution.version
    for relative in distribution.files or []:
        if not any(term in relative.name.lower() for term in ('license','copying','notice')):
            continue
        source = Path(distribution.locate_file(relative))
        if source.is_file():
            target = DEST/name/relative
            # Ignore paths outside the destination (some distributions list ../../Scripts).
            if not target.resolve().is_relative_to(DEST.resolve()):
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)

base = Path(sys.base_prefix)
for source in [base/'LICENSE.txt', base/'tcl'/'tcl8.6'/'license.terms', base/'tcl'/'tk8.6'/'license.terms']:
    if source.exists():
        shutil.copyfile(source,DEST/(source.parent.name+'-'+source.name))
if not (base/'LICENSE.txt').exists():
    raise RuntimeError('Python license file missing; preserve it manually before distribution')
(DEST/'build-versions.json').write_text(json.dumps({'python':sys.version.split()[0], 'packages':versions},indent=2),encoding='utf-8')
print('Dependency and interpreter notices collected')
