# Updates: check for a newer LayerHound, then download, verify and hand over to the updater.
#
# - Releases are published to a public repo (RELEASES_REPO) by scripts/release.py, each with the
#   package, its Ed25519 signature and a manifest. Only packages signed with the Team Tactical RC
#   release key (PUBLIC_KEY, the private half never leaves the release computer) are installed.
# - Once a day (if enabled) the board asks GitHub for the latest release; Settings shows it.
# - "Update now": this service downloads and verifies the package, then starts
#   layerhound-updater.service (updater.py), which backs up, installs, restarts LayerHound and
#   rolls back automatically if the new version doesn't come up. LayerHound can't do that part
#   itself: restarting would stop it halfway through.
import base64, hashlib, json, os, re, subprocess, threading, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, HTTPException
import settings

router=APIRouter(prefix='/api/updates')
RELEASES_REPO='TeamTacticalRC/layerhound-releases'
LATEST_URL=f'https://api.github.com/repos/{RELEASES_REPO}/releases/latest'
PUBLIC_KEY='qTr3P5crD7RJzCkzsuZdTwBzZ2WKyRp3rPiePQIjt6E='
CHECK_EVERY=24*3600; FIRST_CHECK=120; TIMEOUT=20; MAX_PACKAGE=200*2**20
STALE_JOB=30*60   # an install that hasn't finished after this long is reported as failed
UPDATER_UNIT='layerhound-updater.service'
BUSY=('downloading','verifying','installing','restarting')

state={'latest':None,'checked_at':None,'error':None}
_lock=threading.Lock(); DIR=None

def configure(data_dir):
 global DIR
 DIR=Path(data_dir)/'updates'; DIR.mkdir(parents=True,exist_ok=True)
 if settings.as_service(): threading.Thread(target=_loop,daemon=True,name='update-check').start()

# ---- Versions and signatures --------------------------------------------------------------
def parse_version(v):
 m=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',(v or '').strip())
 return tuple(int(x) for x in m.groups()) if m else None

def newer(latest,current):
 a,b=parse_version(latest),parse_version(current)
 return bool(a and b and a>b)

def verify(data,signature,public_key=None):
 key=Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key or PUBLIC_KEY))
 try: key.verify(signature,data); return True
 except InvalidSignature: return False

# ---- Checking ------------------------------------------------------------------------------
def _get(url,limit=None,accept='application/vnd.github+json'):
 req=urllib.request.Request(url,headers={'User-Agent':f'LayerHound/{settings.APP_VERSION}','Accept':accept})
 with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
  data=r.read((limit or MAX_PACKAGE)+1)
 if limit and len(data)>limit: raise ValueError('Download is larger than expected')
 return data

def parse_release(rel):
 assets={a['name']:a['browser_download_url'] for a in rel.get('assets',[])}
 version=(rel.get('tag_name') or '').lstrip('v')
 return {'version':version,'name':rel.get('name') or f'LayerHound v{version}','notes':rel.get('body') or '',
  'published':rel.get('published_at'),'url':rel.get('html_url'),'assets':assets}

def check():
 try:
  latest=parse_release(json.loads(_get(LATEST_URL,limit=2**20)))
  if 'manifest.json' in latest['assets']:
   latest['manifest']=json.loads(_get(latest['assets']['manifest.json'],limit=2**16,accept='application/octet-stream'))
  with _lock: state.update(latest=latest,checked_at=time.time(),error=None)
 except Exception as e:
  msg='No releases published yet' if '404' in str(e) else f"Couldn't check for updates: {e}"
  with _lock: state.update(checked_at=time.time(),error=msg)
 return status()

def _loop():
 time.sleep(FIRST_CHECK)
 while True:
  if settings.get('update_check'): check()
  time.sleep(CHECK_EVERY)

# ---- Job state (shared with updater.py through a file) -------------------------------------
def read_job():
 try: job=json.loads((DIR/'state.json').read_text())
 except (OSError,ValueError,TypeError): return None
 if job.get('phase') in BUSY and time.time()-job.get('started',0)>STALE_JOB:
  job.update(phase='failed',error='The update did not finish. LayerHound kept running the previous version.')
 return job

def write_job(**job):
 tmp=DIR/'state.json.tmp'; tmp.write_text(json.dumps(job)); tmp.replace(DIR/'state.json')

def status():
 cur=settings.APP_VERSION; latest=state['latest']; job=read_job()
 available=bool(latest and newer(latest['version'],cur))
 manifest=(latest or {}).get('manifest') or {}
 reason=None
 if not settings.as_service(): reason='Updates install on the LayerHound board. On this computer, update with git.'
 elif available and not manifest: reason='This release is missing its manifest, so it cannot be installed automatically.'
 elif available and manifest.get('requires_setup'): reason='This update changes the board setup, so it needs a full install (deploy) instead of one-click.'
 elif job and job.get('phase') in BUSY: reason='An update is already in progress.'
 return {'current':cur,'latest':latest and {k:v for k,v in latest.items() if k!='assets'},'available':available,
  'checked_at':state['checked_at'],'error':state['error'],'auto_check':settings.get('update_check'),
  'can_install':available and reason is None,'reason':reason if available else None,'job':job}

# ---- Installing ----------------------------------------------------------------------------
def _install(latest):
 version=latest['version']; manifest=latest.get('manifest') or {}
 base=dict(version=version,from_version=settings.APP_VERSION,started=time.time())
 try:
  write_job(**base,phase='downloading')
  name=manifest.get('file') or f'layerhound-{version}.tar.gz'
  if name not in latest['assets'] or name+'.sig' not in latest['assets']: raise ValueError('The release is missing its package or signature')
  package=_get(latest['assets'][name],accept='application/octet-stream')
  signature=_get(latest['assets'][name+'.sig'],limit=1024,accept='application/octet-stream')
  write_job(**base,phase='verifying')
  if hashlib.sha256(package).hexdigest()!=manifest.get('sha256'): raise ValueError('The download is damaged (checksum mismatch)')
  if not verify(package,base64.b64decode(signature.strip())): raise ValueError('The package is not signed by Team Tactical RC; refusing to install it')
  path=DIR/name; path.write_bytes(package)
  write_job(**base,phase='installing',package=str(path))
  r=subprocess.run(['systemctl','start','--no-block',UPDATER_UNIT],capture_output=True,text=True,timeout=30)
  if r.returncode!=0: raise RuntimeError(f"Couldn't start the updater: {r.stderr.strip() or 'unknown error'}")
 except Exception as e:
  write_job(**base,phase='failed',error=str(e),finished=time.time())

# ---- API -----------------------------------------------------------------------------------
@router.get('')
def get_status(): return status()

@router.post('/check')
def check_now(): return check()

@router.post('/install')
def install():
 s=status()
 if not s['available']: raise HTTPException(409,'LayerHound is already up to date')
 if not s['can_install']: raise HTTPException(409,s['reason'])
 threading.Thread(target=_install,args=(state['latest'],),daemon=True).start()
 return {'status':'started','version':state['latest']['version']}
