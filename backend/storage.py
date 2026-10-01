# Storage page: drive health, usage history, and the shared "TTRC Files" folder.
from datetime import datetime, timezone
from pathlib import Path
import json, os, re, shutil, subprocess, sys, time
import psutil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Shared files live outside the app folder so a redeploy (rsync --delete) never touches them.
FILES_ROOT=Path(os.environ.get('TTRC_FILES') or Path.home()/'TTRC Files').expanduser()
TRASH_NAME='.trash'; HISTORY_DAYS=90; RECORD_EVERY=15*60
router=APIRouter(prefix='/api')
_db=None; _disks=None

def configure(db,disks):
 # main.py hands over its database and drive-listing helpers (avoids a circular import)
 global _db,_disks; _db,_disks=db,disks
 FILES_ROOT.mkdir(parents=True,exist_ok=True); (FILES_ROOT/TRASH_NAME).mkdir(exist_ok=True)
 c=_db(); c.execute('CREATE TABLE IF NOT EXISTS storage_history(t INTEGER NOT NULL,mount TEXT NOT NULL,used_gb REAL NOT NULL,total_gb REAL NOT NULL)')
 c.execute('CREATE INDEX IF NOT EXISTS storage_history_t ON storage_history(t)'); c.commit(); c.close()

# ---- Usage history ------------------------------------------------------------------
def record_usage():
 t=int(time.time()); c=_db()
 c.executemany('INSERT INTO storage_history(t,mount,used_gb,total_gb) VALUES(?,?,?,?)',[(t,d['mount'],d['used_gb'],d['total_gb']) for d in _disks()])
 c.execute('DELETE FROM storage_history WHERE t<?',(t-HISTORY_DAYS*86400,)); c.commit(); c.close()

def usage_history():
 c=_db(); rows=c.execute('SELECT t,mount,used_gb,total_gb FROM storage_history ORDER BY t').fetchall(); c.close()
 out={}
 for r in rows: out.setdefault(r['mount'],[]).append({'t':r['t'],'used':r['used_gb'],'total':r['total_gb']})
 return out

# ---- Drive health (smartctl) --------------------------------------------------------
_health_cache={}; HEALTH_TTL=600
def base_device(dev):
 # /dev/nvme0n1p2 -> /dev/nvme0n1, /dev/sda1 -> /dev/sda, /dev/mmcblk0p1 -> /dev/mmcblk0
 if re.match(r'/dev/(nvme\d+n\d+|mmcblk\d+)p\d+$',dev): return re.sub(r'p\d+$','',dev)
 if re.match(r'/dev/[sh]d[a-z]+\d+$',dev): return re.sub(r'\d+$','',dev)
 return dev

def drive_health(dev):
 dev=base_device(dev); hit=_health_cache.get(dev)
 if hit and time.time()-hit[0]<HEALTH_TTL: return hit[1]
 h=_read_health(dev); _health_cache[dev]=(time.time(),h); return h

def _read_health(dev):
 if not dev.startswith('/dev/') or sys.platform=='darwin': return {'available':False,'reason':'Health data shows up on the board'}
 if 'mmcblk' in dev: return {'available':False,'reason':"SD cards and eMMC don't report health"}
 # Prefer the exact path the sudoers rule in setup.sh allows
 exe='/usr/sbin/smartctl' if Path('/usr/sbin/smartctl').exists() else shutil.which('smartctl')
 if not exe: return {'available':False,'reason':'smartctl is not installed'}
 # setup.sh adds a sudoers rule so the service can run smartctl without a password
 cmd=([] if os.geteuid()==0 else ['sudo','-n'])+[exe,'--json','-a',dev]
 try: d=json.loads(subprocess.run(cmd,capture_output=True,text=True,timeout=15).stdout or '{}')
 except Exception as e: return {'available':False,'reason':f'Could not read health ({type(e).__name__})'}
 if 'smart_status' not in d and 'nvme_smart_health_information_log' not in d: return {'available':False,'reason':'This drive does not report health'}
 n=d.get('nvme_smart_health_information_log') or {}
 h={'available':True,'passed':(d.get('smart_status') or {}).get('passed'),'model':d.get('model_name'),
  'temperature_c':(d.get('temperature') or {}).get('current') or n.get('temperature'),
  'power_on_hours':(d.get('power_on_time') or {}).get('hours') or n.get('power_on_hours')}
 if n:
  # NVMe "percentage used" is the drive's own wear estimate (100 = rated life reached)
  h.update(wear_percent=n.get('percentage_used'),available_spare=n.get('available_spare'),media_errors=n.get('media_errors'),
   written_tb=round(n.get('data_units_written',0)*512000/1e12,2),critical_warning=n.get('critical_warning'))
 return h

# ---- TTRC Files ---------------------------------------------------------------------
def root(): return FILES_ROOT.resolve()
def trash(): return root()/TRASH_NAME

def safe_path(rel):
 # Resolve a path from the browser and refuse anything outside the files folder (or inside the trash)
 p=(root()/(rel or '').strip('/')).resolve()
 if p!=root() and root() not in p.parents: raise HTTPException(400,'Invalid path')
 if p==trash() or trash() in p.parents: raise HTTPException(400,'Invalid path')
 return p

def check_name(name):
 name=(name or '').strip()
 if not name or name in ('.','..') or name.startswith('.') or any(ch in name for ch in '/\\\0') or len(name)>255: raise HTTPException(400,'Invalid name')
 return name

def rel(p): return str(p.relative_to(root())) if p!=root() else ''

def tree_size(p):
 total=count=0
 for dirpath,dirs,files in os.walk(p):
  dirs[:]=[d for d in dirs if not d.startswith('.')]
  for f in files:
   if f.startswith('.'): continue
   try: total+=os.lstat(os.path.join(dirpath,f)).st_size; count+=1
   except OSError: pass
 return total,count

def entry(p):
 st=p.stat(); is_dir=p.is_dir()
 size,count=tree_size(p) if is_dir else (st.st_size,None)
 return {'name':p.name,'path':rel(p),'type':'folder' if is_dir else 'file','size':size,'items':count,'modified':datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat()}

def unique(dirp,name):
 # "part.gcode" -> "part (2).gcode" when the name is taken
 p=dirp/name; stem,ext=os.path.splitext(name); i=2
 while p.exists(): p=dirp/f'{stem} ({i}){ext}'; i+=1
 return p

@router.get('/storage')
def storage():
 disks=_disks(); drives=[{**d,'health':drive_health(d['device'])} for d in disks]
 r=root(); size,count=tree_size(r); u=psutil.disk_usage(str(r)); dev=os.stat(r).st_dev
 home=next((d['mount'] for d in disks if os.stat(d['mountpoint']).st_dev==dev),None)
 t_size,t_count=tree_size(trash()) if trash().exists() else (0,0)
 return {'drives':drives,'history':usage_history(),'history_every_minutes':RECORD_EVERY//60,
  'files':{'root':str(r),'drive':home,'size':size,'count':count,'free':u.free,'trash_size':t_size,'trash_count':len(list(trash().iterdir())) if trash().exists() else 0}}

@router.get('/files')
def list_files(path:str=''):
 d=safe_path(path)
 if not d.is_dir(): raise HTTPException(404,'Folder not found')
 items=[entry(p) for p in d.iterdir() if not p.name.startswith('.')]
 items.sort(key=lambda e:(e['type']!='folder',e['name'].lower()))
 crumbs=[]; cur=d
 while cur!=root(): crumbs.insert(0,{'name':cur.name,'path':rel(cur)}); cur=cur.parent
 return {'path':rel(d),'crumbs':crumbs,'items':items}

@router.get('/files/download')
def download(path:str):
 p=safe_path(path)
 if not p.is_file(): raise HTTPException(404,'File not found')
 return FileResponse(p,filename=p.name)

@router.put('/files/upload')
async def upload(request:Request,path:str,name:str):
 # Raw request body (not multipart) so large files stream straight to disk
 d=safe_path(path); name=check_name(name)
 if not d.is_dir(): raise HTTPException(404,'Folder not found')
 size=int(request.headers.get('content-length') or 0)
 if size and size>shutil.disk_usage(d).free: raise HTTPException(507,'Not enough free space on the drive')
 dest=unique(d,name); tmp=d/f'.{dest.name}.part'
 try:
  with open(tmp,'wb') as f:
   async for chunk in request.stream(): f.write(chunk)
  tmp.rename(dest)
 except BaseException:
  tmp.unlink(missing_ok=True); raise
 return entry(dest)

class NewFolder(BaseModel):
 path:str=''; name:str
class Rename(BaseModel):
 path:str; name:str
class PathIn(BaseModel):
 path:str

@router.post('/files/folder')
def new_folder(b:NewFolder):
 d=safe_path(b.path); p=d/check_name(b.name)
 if p.exists(): raise HTTPException(409,'Something with that name already exists')
 p.mkdir(); return entry(p)

@router.post('/files/rename')
def rename(b:Rename):
 p=safe_path(b.path)
 if p==root(): raise HTTPException(400,"Can't rename the main folder")
 dest=p.parent/check_name(b.name)
 if dest.exists(): raise HTTPException(409,'Something with that name already exists')
 p.rename(dest); return entry(dest)

@router.post('/files/delete')
def delete(b:PathIn):
 # Moves to the trash; nothing is permanently deleted until the trash is emptied
 p=safe_path(b.path)
 if p==root(): raise HTTPException(400,"Can't delete the main folder")
 if not p.exists(): raise HTTPException(404,'Not found')
 stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
 shutil.move(str(p),str(unique(trash(),f'{stamp} {p.name}'))); return {'status':'moved to trash','path':b.path}

@router.post('/files/trash/empty')
def empty_trash():
 n=0
 for p in trash().iterdir():
  shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink(); n+=1
 return {'status':'emptied','removed':n}
