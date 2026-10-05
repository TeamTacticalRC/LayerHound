# Publish a LayerHound release that boards can install with one click.
#
#   backend/.venv/bin/python scripts/release.py 0.6.0 --notes-file notes.md [--needs-setup]
#
# 1. Sets the version in the code, commits "Release vX.Y.Z", tags it and pushes (private repo).
# 2. Builds the dashboard and packages backend/, deploy/ and dist/ as layerhound-X.Y.Z.tar.gz.
# 3. Signs the package with the release key (~/.layerhound/release-signing.key, never committed).
# 4. After you confirm, publishes it to the public releases repo with the notes, a manifest and
#    the installer (deploy/install.sh), so ".../releases/latest/download/install.sh" is always current.
#
# --needs-setup marks a release that changes the board setup (deploy/setup.sh: system packages,
# permissions, services). Boards then ask for a full install instead of one-click; the script
# warns if setup.sh changed since the previous release and the flag is missing.
import argparse, base64, hashlib, io, json, re, subprocess, sys, tarfile, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives import serialization

ROOT=Path(__file__).resolve().parent.parent
RELEASES_REPO='TeamTacticalRC/layerhound-releases'
KEY=Path.home()/'.layerhound'/'release-signing.key'
# Tracked files from these folders and files, plus the built dist/. The license must ship with the software.
PACKAGED=('backend','deploy','LICENSE','TRADEMARKS.md','README.md')

def sh(*args,capture=False,cwd=ROOT):
 r=subprocess.run(args,cwd=cwd,text=True,capture_output=capture)
 if r.returncode!=0: sys.exit(f"Failed: {' '.join(args)}\n{(r.stderr or r.stdout or '').strip()}")
 return (r.stdout or '').strip()

def set_version(version):
 for path,pattern,repl in ((ROOT/'backend/settings.py',r"APP_VERSION='[^']*'",f"APP_VERSION='{version}'"),
                           (ROOT/'src/main.jsx',r'const APP_VERSION = "v[^"]*";',f'const APP_VERSION = "v{version}";')):
  text=path.read_text(); new,n=re.subn(pattern,repl,text)
  if n!=1: sys.exit(f'Could not find the version in {path}')
  path.write_text(new)

def package(version):
 files=sh('git','ls-files',*PACKAGED,capture=True).splitlines()
 buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w:gz',format=tarfile.PAX_FORMAT) as t:
  def add(path,arc):
   info=t.gettarinfo(str(path),arc); info.uid=info.gid=0; info.uname=info.gname=''
   if info.isfile():
    with open(path,'rb') as f: t.addfile(info,f)
   else: t.addfile(info)
  for f in files: add(ROOT/f,f'layerhound/{f}')
  for p in sorted((ROOT/'dist').rglob('*')):
   if p.is_file(): add(p,f'layerhound/{p.relative_to(ROOT)}')
  data=f'{version}\n'.encode(); info=tarfile.TarInfo('layerhound/VERSION'); info.size=len(data); info.mtime=int(time.time())
  t.addfile(info,io.BytesIO(data))
 return buf.getvalue()

def sign(data):
 if not KEY.exists(): sys.exit(f'Release key not found at {KEY}')
 key=serialization.load_pem_private_key(KEY.read_bytes(),password=None)
 return base64.b64encode(key.sign(data))

def main():
 ap=argparse.ArgumentParser(description='Publish a LayerHound release')
 ap.add_argument('version'); ap.add_argument('--notes-file',required=True); ap.add_argument('--needs-setup',action='store_true')
 ap.add_argument('--yes',action='store_true',help="Don't ask before publishing")
 a=ap.parse_args()
 version=a.version.lstrip('v')
 if not re.fullmatch(r'\d+\.\d+\.\d+',version): sys.exit('Version must look like 0.6.0')
 notes=Path(a.notes_file).read_text().strip()
 if not notes: sys.exit('The release notes are empty')
 if sh('git','status','--porcelain',capture=True): sys.exit('Commit or stash your changes first; a release must match a commit')
 if sh('git','rev-parse','--abbrev-ref','HEAD',capture=True)!='main': sys.exit('Releases are made from the main branch')
 if sh('git','tag','-l',f'v{version}',capture=True): sys.exit(f'v{version} already exists')

 prev=[t for t in sh('git','tag','-l','v*','--sort=-v:refname',capture=True).splitlines() if t]
 if prev and not a.needs_setup and sh('git','diff','--name-only',prev[0],'HEAD','--','deploy/setup.sh',capture=True):
  print(f'Warning: deploy/setup.sh changed since {prev[0]}. If boards need the setup to run again, use --needs-setup.')
  if not a.yes and input('Continue without --needs-setup? [y/N] ').strip().lower()!='y': sys.exit('Stopped.')

 print(f'==> Setting version {version}')
 set_version(version)
 print('==> Building the dashboard'); sh('npm','run','build')
 print('==> Running the backend tests'); sh(str(ROOT/'backend/.venv/bin/python'),'-m','pytest','-q','tests',cwd=ROOT/'backend')
 print('==> Running the frontend tests (browser)'); sh(str(ROOT/'backend/.venv/bin/python'),'-m','pytest','-q','tests/ui','-p','no:warnings')
 sh('git','add','backend/settings.py','src/main.jsx')
 sh('git','commit','-q','-m',f'Release v{version}'); sh('git','tag','-a',f'v{version}','-m',f'LayerHound v{version}')

 print('==> Packaging and signing')
 data=package(version); name=f'layerhound-{version}.tar.gz'
 manifest={'version':version,'file':name,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),
  'requires_setup':a.needs_setup,'published':datetime.now(timezone.utc).isoformat()}
 out=Path(tempfile.mkdtemp(prefix='layerhound-release-'))
 (out/name).write_bytes(data); (out/f'{name}.sig').write_bytes(sign(data)); (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 (out/'notes.md').write_text(notes)
 print(f'    {name}: {len(data)/2**20:.1f} MB, sha256 {manifest["sha256"][:16]}…, needs setup: {a.needs_setup}')

 if not a.yes and input(f'Publish v{version} publicly to {RELEASES_REPO} and push the tag? [y/N] ').strip().lower()!='y':
  sys.exit(f'Not published. The release commit and tag are local only; files are in {out}')
 sh('git','push','-q'); sh('git','push','-q','origin',f'v{version}')
 sh('gh','release','create',f'v{version}','--repo',RELEASES_REPO,'--title',f'LayerHound v{version}','--notes-file',str(out/'notes.md'),
    str(out/name),str(out/f'{name}.sig'),str(out/'manifest.json'),str(ROOT/'deploy/install.sh'))
 print(f'==> Published: https://github.com/{RELEASES_REPO}/releases/tag/v{version}')

if __name__=='__main__': main()
