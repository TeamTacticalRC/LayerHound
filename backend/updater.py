# Installs a downloaded, verified LayerHound update. Run by layerhound-updater.service (set up by
# deploy/setup.sh) when an admin presses "Update now", or by install.sh --update.
#
# On a board the updater runs as root (the code in /opt/layerhound is root's, so LayerHound itself
# can't change it), while the update was downloaded by LayerHound's own account. So it checks the
# package's Team Tactical RC signature again itself, with the key in this (root-owned) code, and only
# takes packages from its own updates folder: a LayerHound that had been broken into couldn't get
# root to install something else.
#
# 1. Back up the database and keep a copy of the current code.
# 2. Put the new code in place (data, the database and the Python environment are kept).
# 3. Install new Python packages if the requirements changed, then restart LayerHound.
# 4. Wait for the new version to answer. If it doesn't, or anything above fails, put the old code
#    and database back and restart, so the board keeps working on the version it had.
import base64, json, os, shutil, sqlite3, subprocess, sys, tarfile, time, urllib.request
from pathlib import Path

BACKEND=Path(__file__).resolve().parent; APP_DIR=BACKEND.parent
def env(name): return os.environ.get(f'LAYERHOUND_{name}') or os.environ.get(f'TTRC_{name}')
DB_PATH=Path(env('DB') or BACKEND/'layerhound.db')
DATA=DB_PATH.parent/'data'; UPDATES=DATA/'updates'; BACKUPS=DATA/'backups'
ROLLBACK=APP_DIR.parent/f'{APP_DIR.name}-rollback'
PORT=env('PORT') or '80'
SERVICE='layerhound.service'; HEALTH_WAIT=120; KEEP_BACKUPS=5
# Code directories an update replaces; everything else in the app folder is left alone
CODE_DIRS=('backend','dist','deploy')
# Inside backend/, never touched by an update
KEEP=('.venv','data','__pycache__')

def log(msg): print(f'[updater] {msg}',flush=True)

def give_back(path):
 # Files the updater writes as root in LayerHound's data folder go back to LayerHound's account
 if os.geteuid()!=0: return
 try: st=DATA.stat(); os.chown(path,st.st_uid,st.st_gid)
 except OSError: pass

def write_state(**job):
 tmp=UPDATES/'state.json.tmp'; tmp.write_text(json.dumps(job)); tmp.replace(UPDATES/'state.json'); give_back(UPDATES/'state.json')

def check_package(path):
 # Only a package in our own updates folder, with a valid Team Tactical RC signature next to it
 p=Path(path).resolve()
 if p.parent!=UPDATES.resolve() or not p.name.endswith('.tar.gz'): raise ValueError(f'Refusing a package outside the updates folder: {path}')
 sig=p.with_name(p.name+'.sig')
 if not sig.exists(): raise ValueError('The package has no signature next to it')
 from updates import verify   # the same key LayerHound checks downloads with
 if not verify(p.read_bytes(),base64.b64decode(sig.read_bytes().strip())): raise ValueError('The package is not signed by Team Tactical RC; refusing to install it')
 return p

def kept(rel):
 # Paths (relative to the app folder) an update must never replace or delete
 parts=Path(rel).parts
 if not parts: return False
 if parts[0]=='backend' and len(parts)>1 and (parts[1] in KEEP or parts[1].endswith(('.db','.db-journal','.db-wal','.db-shm'))): return True
 return False

def safe_extract(package,dest):
 # Only plain files and folders inside one top-level "layerhound/" folder; nothing that escapes it
 with tarfile.open(package,'r:gz') as t:
  for m in t.getmembers():
   p=Path(m.name)
   if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!='layerhound': raise ValueError(f'Unsafe path in package: {m.name}')
   if not (m.isfile() or m.isdir()): raise ValueError(f'Unexpected entry in package: {m.name}')
  t.extractall(dest)
 return Path(dest)/'layerhound'

def sync(src,dst,rel=''):
 # Make dst match src, except for kept paths
 dst.mkdir(parents=True,exist_ok=True)
 names={p.name for p in src.iterdir()}
 for p in dst.iterdir():
  r=f'{rel}/{p.name}'.lstrip('/')
  if p.name not in names and not kept(r):
   shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
 for p in src.iterdir():
  r=f'{rel}/{p.name}'.lstrip('/'); target=dst/p.name
  if kept(r): continue
  if p.is_dir(): sync(p,target,r)
  else: shutil.copy2(p,target)

def snapshot():
 # Copy of the current code, for rolling back
 if ROLLBACK.exists(): shutil.rmtree(ROLLBACK)
 ROLLBACK.mkdir(parents=True)
 for d in CODE_DIRS:
  if (APP_DIR/d).exists(): sync(APP_DIR/d,ROLLBACK/d,d)

def restore_code():
 for d in CODE_DIRS:
  if (ROLLBACK/d).exists(): sync(ROLLBACK/d,APP_DIR/d,d)

def backup_db(version):
 BACKUPS.mkdir(parents=True,exist_ok=True); give_back(BACKUPS)
 if not DB_PATH.exists(): return None
 dest=BACKUPS/f'layerhound-{version}-{time.strftime("%Y%m%d-%H%M%S")}.db'
 src=sqlite3.connect(DB_PATH); out=sqlite3.connect(dest)
 with out: src.backup(out)
 src.close(); out.close(); give_back(dest)
 for old in sorted(BACKUPS.glob('layerhound-*.db'))[:-KEEP_BACKUPS]: old.unlink()
 return dest

def restore_db(backup):
 if not backup: return
 src=sqlite3.connect(backup); out=sqlite3.connect(DB_PATH)
 with out: src.backup(out)
 src.close(); out.close()

def pip_install():
 r=subprocess.run([str(BACKEND/'.venv/bin/pip'),'install','-q','-r',str(BACKEND/'requirements.txt')],capture_output=True,text=True,timeout=1800)
 if r.returncode!=0: raise RuntimeError(f'Installing Python packages failed: {(r.stderr or r.stdout).strip()[-400:]}')

def restart():
 r=subprocess.run(['systemctl','restart',SERVICE],capture_output=True,text=True,timeout=120)
 if r.returncode!=0: raise RuntimeError(f"Couldn't restart LayerHound: {r.stderr.strip()}")

def wait_for(version,timeout=HEALTH_WAIT):
 end=time.time()+timeout
 while time.time()<end:
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/health',timeout=5) as r:
    if json.loads(r.read()).get('version')==version: return True
  except Exception: pass
  time.sleep(3)
 return False

def run(job):
 version,old=job['version'],job['from_version']; base={k:job[k] for k in ('version','from_version','started','auto') if k in job}
 write_state(**base,phase='installing')
 try: package=check_package(job['package'])
 except Exception as e:
  log(f'not installing: {e}'); write_state(**base,phase='failed',error=str(e),rolled_back=False,finished=time.time()); return
 backup=backup_db(old); log(f'database backed up to {backup}')
 snapshot(); log('current version saved for rollback')
 stage=UPDATES/'new'; old_reqs=(BACKEND/'requirements.txt').read_text(); reqs_changed=False
 try:
  if stage.exists(): shutil.rmtree(stage)
  new=safe_extract(package,stage)
  for d in CODE_DIRS:
   if (new/d).exists(): sync(new/d,APP_DIR/d,d)
  reqs_changed=(BACKEND/'requirements.txt').read_text()!=old_reqs
  if reqs_changed: log('installing Python packages'); pip_install()
  write_state(**base,phase='restarting')
  restart()
  if not wait_for(version): raise RuntimeError(f'LayerHound v{version} did not start')
  write_state(**base,phase='done',finished=time.time())
  log(f'updated {old} -> {version}')
 except Exception as e:
  log(f'update failed, rolling back: {e}')
  try:
   restore_code(); restore_db(backup)
   if reqs_changed: pip_install()   # put the previous versions of the Python packages back
   restart(); back=wait_for(old)
  except Exception as e2: back=False; log(f'rollback problem: {e2}')
  write_state(**base,phase='failed',error=str(e),rolled_back=back,finished=time.time())
 finally:
  shutil.rmtree(stage,ignore_errors=True)
  for f in (Path(job['package']),Path(str(job['package'])+'.sig')):
   try: f.unlink()
   except OSError: pass

def main():
 try: job=json.loads((UPDATES/'state.json').read_text())
 except (OSError,ValueError): log('no update waiting'); return 0
 if job.get('phase')!='installing' or not job.get('package'): log('no update waiting'); return 0
 run(job); return 0

if __name__=='__main__': sys.exit(main())
