#!/usr/bin/env python3
"""Build a deterministic source-only release archive and SHA-256 file."""
import argparse
import hashlib
from pathlib import Path
import re
import stat
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXTENSIONS={'.py','.php','.js','.css','.svg','.html','.sh','.conf','.service','.timer','.md'}
SPECIAL={'LICENSE','.gitignore','vectorcp-cert-renew'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    output=args.output.absolute()
    if ROOT==output.parent or ROOT in output.parents:
        raise SystemExit('Put release archives outside the source tree.')
    version=re.search(r'^__version__ = "([0-9.]+)"', (ROOT/'vectorcp/__init__.py').read_text(),re.M).group(1)
    files=[]
    for path in sorted(ROOT.rglob('*')):
        relative=path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink() or any(part.startswith(('__pycache__','._','.git')) and part!='.gitignore' for part in relative.parts):
            continue
        if len(relative.parts)>1 and relative.parts[0] not in ('vectorcp','deploy','tests','assets'):
            continue
        if path.suffix not in EXTENSIONS and path.name not in SPECIAL:
            continue
        files.append(path)
    output.parent.mkdir(parents=True,exist_ok=True)
    prefix='VectorCP-'+version
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files:
            info=zipfile.ZipInfo(prefix+'/'+path.relative_to(ROOT).as_posix(),date_time=(2026,1,1,0,0,0))
            info.create_system=3
            mode=0o755 if path.suffix=='.sh' or path.name=='vectorcp-cert-renew' else 0o644
            info.external_attr=(stat.S_IFREG|mode)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,path.read_bytes())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==len(files)
        for path in files:
            assert archive.read(prefix+'/'+path.relative_to(ROOT).as_posix())==path.read_bytes()
    checksum=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(checksum+'  '+output.name+'\n')
    print('Built and verified',len(files),'source files:',output.name)
    print('SHA-256:',checksum)


if __name__=='__main__':main()
