# Print history: records every job from the background printer checks, and imports the job
# history Klipper (Moonraker) printers keep themselves, so past prints show up too.
from datetime import datetime, timedelta
import json, threading, time, urllib.request
from fastapi import APIRouter, HTTPException

router=APIRouter(prefix='/api/history')
IMPORT_EVERY=6*3600
_db=None; _rows=None; lock=threading.Lock()
open_jobs={}   # printer id -> the job currently printing (mirrors rows with no ended_at)

def configure(db,printer_rows):
 # printer_rows: function returning the printers table rows (from main.py)
 global _db,_rows; _db,_rows=db,printer_rows
 c=_db()
 c.execute('''CREATE TABLE IF NOT EXISTS print_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,printer_id INTEGER NOT NULL,printer_name TEXT,
  file TEXT,status TEXT NOT NULL,started_at REAL NOT NULL,ended_at REAL,progress REAL,print_seconds REAL,filament_mm REAL,
  source TEXT NOT NULL DEFAULT 'dashboard',source_id TEXT)''')
 c.execute('CREATE UNIQUE INDEX IF NOT EXISTS print_jobs_source ON print_jobs(printer_id,source_id)')
 c.execute('CREATE INDEX IF NOT EXISTS print_jobs_started ON print_jobs(started_at)')
 # Jobs still open from before a restart; the next printer check continues or closes them.
 # Oldest first: a duplicate entry for the same print is dropped, and an older print that never
 # got closed is marked interrupted when the next one started.
 for r in c.execute("SELECT id,printer_id,file,started_at,progress FROM print_jobs WHERE ended_at IS NULL AND source='dashboard' ORDER BY started_at"):
  prev=open_jobs.get(r['printer_id'])
  if prev and prev['file']==r['file']: c.execute('DELETE FROM print_jobs WHERE id=?',(r['id'],)); continue
  if prev: c.execute("UPDATE print_jobs SET status='interrupted',ended_at=? WHERE id=?",(r['started_at'],prev['id']))
  open_jobs[r['printer_id']]={'id':r['id'],'file':r['file'],'started_at':r['started_at'],'progress':r['progress'] or 0}
 # Repair imports from before 2026-10-02: Klipper stamps unfinished jobs "interrupted" with the time
 # it next restarted, which could be weeks later. Use the time actually spent printing instead.
 c.execute('''UPDATE print_jobs SET ended_at=started_at+print_seconds WHERE source='printer' AND print_seconds IS NOT NULL
  AND ended_at-started_at>print_seconds*3+6*3600''')
 c.commit(); c.close()
 threading.Thread(target=importer,daemon=True,name='layerhound-history-import').start()

# ---- Recording from live printer checks -------------------------------------------------
ACTIVE=('printing','paused')
def end_status(p,last_progress):
 raw=str(p.get('raw_state') or '').lower()
 if p.get('state')=='complete' or raw in ('complete','completed','finish') or last_progress>=99.5: return 'completed'
 if p.get('state')=='error' or raw in ('error','failed'): return 'failed'
 return 'cancelled'

def observe(p,now=None):
 # Called with every printer reading. Opens a job when a print starts, closes it when it ends.
 now=now or time.time(); pid=p['id']; job=p.get('job'); state=p.get('state')
 with lock:
  cur=open_jobs.get(pid)
  if state in ACTIVE and job:
   # Prints first seen partway through are backdated using the printer's own elapsed time
   start=now-(p.get('elapsed_seconds') or 0)
   if cur and cur['file']==job:
    cur['progress']=max(cur['progress'],p.get('progress') or 0); cur['extra']=p
    if start<cur['started_at']-300:
     cur['started_at']=start; c=_db(); c.execute('UPDATE print_jobs SET started_at=? WHERE id=?',(start,cur['id'])); c.commit(); c.close()
    return
   if cur: close(pid,'interrupted',now)        # a different file started without the last one ending
   # The database is the source of truth: reuse an open entry for this print if one exists
   # (e.g. written by another copy of the server during a restart) instead of adding a duplicate
   c=_db(); row=c.execute('SELECT id,started_at FROM print_jobs WHERE printer_id=? AND file=? AND ended_at IS NULL ORDER BY started_at LIMIT 1',(pid,job)).fetchone()
   if row: jid,start=row['id'],min(start,row['started_at']); c.execute('UPDATE print_jobs SET started_at=? WHERE id=?',(start,jid))
   else: jid=c.execute('INSERT INTO print_jobs(printer_id,printer_name,file,status,started_at,progress) VALUES(?,?,?,?,?,?)',
    (pid,p.get('name'),job,'printing',start,p.get('progress') or 0)).lastrowid
   c.commit(); c.close()
   open_jobs[pid]={'id':jid,'file':job,'started_at':start,'progress':p.get('progress') or 0,'extra':p}
  elif cur and p.get('connected'):
   # Offline printers keep their job open; it's settled when they come back
   close(pid,end_status(p,max(cur['progress'],p.get('progress') or 0)),now,p)

def close(pid,status,now,p=None):
 cur=open_jobs.pop(pid,None)
 if not cur: return
 last=cur.get('extra') or p or {}
 progress=100.0 if status=='completed' else cur['progress']
 c=_db(); c.execute('UPDATE print_jobs SET status=?,ended_at=?,progress=?,print_seconds=COALESCE(?,print_seconds),filament_mm=COALESCE(?,filament_mm) WHERE id=?',
  (status,now,progress,last.get('print_seconds'),last.get('filament_mm'),cur['id'])); c.commit(); c.close()

def forget_printer(pid):
 with lock: open_jobs.pop(pid,None)

# ---- Importing Klipper's own history ----------------------------------------------------
MOONRAKER_STATUS={'completed':'completed','cancelled':'cancelled','error':'failed','klippy_shutdown':'failed','klippy_disconnect':'failed',
 'server_exit':'interrupted','interrupted':'interrupted'}

def fetch_moonraker_jobs(base,limit=1000):
 with urllib.request.urlopen(f'{base}/server/history/list?limit={limit}&order=desc',timeout=10) as r: return json.loads(r.read().decode()).get('result',{}).get('jobs',[])

def import_printer(row,jobs=None):
 # Adds jobs the printer remembers. If the dashboard already recorded the same print
 # (same file, start within 15 minutes) the printer's more accurate details are merged in.
 base=row['base_url'].rstrip('/'); jobs=jobs if jobs is not None else fetch_moonraker_jobs(base)
 added=merged=0; c=_db()
 for j in jobs:
  status=MOONRAKER_STATUS.get(j.get('status'))
  if not status or not j.get('start_time'): continue
  sid=str(j.get('job_id')); file=str(j.get('filename') or '').rsplit('/',1)[-1] or None
  start=float(j['start_time']); end=float(j['end_time']) if j.get('end_time') else None
  # Interrupted jobs get their end time when Klipper next restarts, possibly weeks later;
  # never let a job end later than its start plus the time Klipper says it ran
  ran=j.get('total_duration') if j.get('total_duration') is not None else j.get('print_duration')
  if ran is not None and (end is None or end-start>float(ran)+3600): end=start+float(ran)
  vals=(status,start,end,j.get('print_duration'),j.get('filament_used'))
  if c.execute('SELECT 1 FROM print_jobs WHERE printer_id=? AND source_id=?',(row['id'],sid)).fetchone():
   continue
  twin=c.execute("SELECT id FROM print_jobs WHERE printer_id=? AND file=? AND source_id IS NULL AND ended_at IS NOT NULL AND ABS(started_at-?)<900",(row['id'],file,start)).fetchone()
  if twin:
   c.execute('UPDATE print_jobs SET status=?,started_at=?,ended_at=COALESCE(?,ended_at),print_seconds=?,filament_mm=?,source_id=? WHERE id=?',(*vals,sid,twin['id'])); merged+=1
  else:
   c.execute("INSERT INTO print_jobs(printer_id,printer_name,file,status,started_at,ended_at,progress,print_seconds,filament_mm,source,source_id) VALUES(?,?,?,?,?,?,?,?,?,'printer',?)",
    (row['id'],row['name'],file,status,start,vals[2],100.0 if status=='completed' else None,vals[3],vals[4],sid)); added+=1
 c.commit(); c.close(); return {'added':added,'merged':merged}

def import_all():
 out={}
 for r in _rows():
  if r['printer_type']!='moonraker' or not r['enabled']: continue
  try: out[r['name']]=import_printer(r)
  except Exception as e: out[r['name']]={'error':f'{type(e).__name__}: {e}'}
 return out

def importer():
 time.sleep(20)   # let the server finish starting
 while True:
  try: import_all()
  except Exception as e: print('history import error:',e,flush=True)
  time.sleep(IMPORT_EVERY)

# ---- API --------------------------------------------------------------------------------
def since(days): return time.time()-days*86400 if days else 0
DURATION='COALESCE(j.print_seconds, COALESCE(j.ended_at,strftime(\'%s\',\'now\'))-j.started_at)'

@router.get('')
def jobs(days:int=0,printer_id:int|None=None,status:str|None=None,q:str='',limit:int=50,offset:int=0):
 where=["j.started_at>=?","j.status!='deleted'"]; args=[since(days)]
 if printer_id: where.append('j.printer_id=?'); args.append(printer_id)
 if status: where.append('j.status=?'); args.append(status)
 if q: where.append('j.file LIKE ?'); args.append(f'%{q}%')
 c=_db(); w=' AND '.join(where)
 total=c.execute(f'SELECT COUNT(*) FROM print_jobs j WHERE {w}',args).fetchone()[0]
 rows=c.execute(f'''SELECT j.*,COALESCE(p.name,j.printer_name) AS printer,{DURATION} AS duration FROM print_jobs j LEFT JOIN printers p ON p.id=j.printer_id
  WHERE {w} ORDER BY j.started_at DESC LIMIT ? OFFSET ?''',(*args,min(max(limit,1),200),max(offset,0))).fetchall(); c.close()
 return {'total':total,'jobs':[dict(r) for r in rows]}

@router.get('/stats')
def stats(days:int=30):
 c=_db(); t0=since(days)
 per=c.execute(f'''SELECT j.printer_id,COALESCE(p.name,j.printer_name) AS printer,p.id IS NOT NULL AS current,COUNT(*) AS jobs,
  SUM(j.status='completed') AS completed,SUM(j.status IN ('failed','interrupted')) AS failed,SUM(j.status='cancelled') AS cancelled,
  SUM(j.status='printing') AS active,SUM({DURATION}) AS seconds,SUM(j.filament_mm) AS filament_mm,MAX(j.started_at) AS last_started
  FROM print_jobs j LEFT JOIN printers p ON p.id=j.printer_id WHERE j.started_at>=? AND j.status!='deleted' GROUP BY j.printer_id ORDER BY COALESCE(p.sort_order,999),printer''',(t0,)).fetchall()
 # Hours printed per calendar day for the chart (at most the last 90 days). Each print's time
 # is split across the days it actually ran, so an overnight print counts toward both days.
 span=min(days or 90,90); nowt=time.time()
 first=datetime.fromtimestamp(nowt).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=span-1)
 d0=first.timestamp(); daily={}
 for r in c.execute("SELECT started_at,COALESCE(ended_at,?) AS ended FROM print_jobs WHERE status!='deleted' AND COALESCE(ended_at,?)>? ",(nowt,nowt,d0)):
  a,b=max(r['started_at'],d0),min(r['ended'],nowt); day=datetime.fromtimestamp(a).replace(hour=0,minute=0,second=0,microsecond=0)
  while a<b:
   nxt=(day+timedelta(days=1)).timestamp(); k=day.strftime('%Y-%m-%d')
   daily[k]=daily.get(k,0)+(min(b,nxt)-a)/3600; a=nxt; day+=timedelta(days=1)
 c.close()
 days_list=[(first+timedelta(days=i)).strftime('%Y-%m-%d') for i in range(span)]
 printers=[dict(r) for r in per]
 for p in printers:
  done=(p['completed'] or 0)+(p['failed'] or 0)+(p['cancelled'] or 0)
  p['success_rate']=round(100*(p['completed'] or 0)/done,1) if done else None
 tot={k:sum((p[k] or 0) for p in printers) for k in ('jobs','completed','failed','cancelled','active','seconds','filament_mm')}
 done=tot['completed']+tot['failed']+tot['cancelled']
 tot['success_rate']=round(100*tot['completed']/done,1) if done else None
 return {'days':days,'totals':tot,'printers':printers,'daily':[{'day':d,'hours':round(daily.get(d,0),2)} for d in days_list]}

@router.post('/import')
def import_now(): return {'printers':import_all()}

@router.delete('/{jid}')
def delete_job(jid:int):
 c=_db(); r=c.execute("SELECT ended_at,source_id FROM print_jobs WHERE id=? AND status!='deleted'",(jid,)).fetchone()
 if not r: c.close(); raise HTTPException(404,'Job not found')
 if r['ended_at'] is None: c.close(); raise HTTPException(409,"Can't delete a print that's still running")
 # Imported jobs are hidden rather than removed, so the next import doesn't bring them back
 if r['source_id']: c.execute("UPDATE print_jobs SET status='deleted' WHERE id=?",(jid,))
 else: c.execute('DELETE FROM print_jobs WHERE id=?',(jid,))
 c.commit(); c.close(); return {'status':'deleted','id':jid}
