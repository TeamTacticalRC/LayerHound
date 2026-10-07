# Settings page: branding/display, alert thresholds, data retention, backups, about/maintenance.
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json, os, platform, sqlite3, subprocess, sys, threading, time
import psutil
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
import vault

router=APIRouter(prefix='/api/settings')
APP_VERSION='1.2.0'
_db=None; _cache={}; _lock=threading.Lock()
# Functions to run after a restore (main.py uses this to drop Bambu connections tied to old printer ids)
after_restore=[]
# Functions to run after settings are saved, with the changed values (e.g. stats.py reacts to a yes)
after_save=[]

# Every setting with its default and allowed values. Anything not listed here is rejected.
SCHEMA={
 # The LayerHound name and logo are fixed; the farm name is the customer's own
 'farm_name':('My Print Farm',str,(1,40)),
 'farm_description':("One place to see what's happening across your print farm.",str,(0,120)),
 'accent':('electric',str,('electric','violet','indigo','blue','fuchsia','pink')),
 'temp_unit':('C',str,('C','F')),
 'time_format':('12',str,('12','24')),
 'temp_warn':(75,int,(40,110)),
 'temp_hot':(85,int,(45,120)),
 'storage_warn':(90,int,(50,99)),
 'storage_critical':(97,int,(51,100)),
 'memory_warn':(92,int,(50,100)),
 'alert_printers':(True,bool,None),
 'alert_devices':(True,bool,None),
 'alert_services':(True,bool,None),
 'alert_internet':(True,bool,None),
 'network_history_days':(7,int,(1,90)),
 'storage_history_days':(90,int,(7,365)),
 'data_usage_days':(90,int,(7,365)),
 # Let devices on the local network view the dashboard without signing in (changes still need an admin)
 'guest_view':(False,bool,None),
 # Case fan (fan.py): automatic speed from the chip temperature, or always full speed
 'fan_mode':('auto',str,('auto','full')),
 'fan_quiet_temp':(45,int,(30,70)),
 'fan_full_temp':(65,int,(40,85)),
 'fan_min_percent':(30,int,(20,100)),
 # Check once a day for a newer LayerHound (updates.py); installing always needs an admin
 'update_check':(True,bool,None),
 # Automatic updates (updates.py): off by default; installs at this hour in the owner's time zone.
 # The board's clock usually runs on UTC, so the Settings page saves the browser's time zone.
 'auto_update':(False,bool,None),
 'auto_update_hour':(3,int,(0,23)),
 'time_zone':('',str,(0,64)),
 # Setup hotspot when offline (hotspot.py): auto = on for single-board computers, off for PCs
 'setup_hotspot':('auto',str,('auto','on','off')),
 # Printer suggestions (discovery.py): scan once a day; optionally add Klipper printers without asking
 'printer_discovery':(True,bool,None),
 'auto_add_klipper':(False,bool,None),
 # Anonymous usage stats (stats.py): 'ask' until the owner chooses; nothing is sent unless 'yes'
 'usage_stats':('ask',str,('ask','yes','no')),
}

# Names used in error messages, matching the labels on the Settings page
LABELS={'farm_name':'Farm name','farm_description':'Description','accent':'Accent color','temp_unit':'Temperature unit','time_format':'Time format',
 'temp_warn':'Server running hot','temp_hot':'Server overheating','storage_warn':'Main drive warning','storage_critical':'Main drive critical','memory_warn':'Memory warning',
 'fan_mode':'Fan mode','setup_hotspot':'Setup hotspot','fan_quiet_temp':'Quiet up to','fan_full_temp':'Full speed at','fan_min_percent':'Minimum fan speed',
 'network_history_days':'Uptime history','auto_update_hour':'Update time','time_zone':'Time zone','storage_history_days':'Storage trend','data_usage_days':'Data usage'}

def configure(db):
 global _db; _db=db
 c=_db(); c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
 # v0.4.1: the editable dashboard name became the farm name (LayerHound branding is now fixed)
 old={r['key']:json.loads(r['value']) for r in c.execute("SELECT key,value FROM settings WHERE key LIKE 'brand_%'")}
 for k,v in upgrade_keys(old).items(): c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,json.dumps(v)))
 c.execute("DELETE FROM settings WHERE key LIKE 'brand_%'"); c.commit(); c.close(); _load()

def upgrade_keys(old):
 # Map pre-0.4.1 branding settings (from the database or an older backup) to the farm settings
 out={}
 name=(old.get('brand_name') or '').strip()
 if name and name!='LayerHound': out['farm_name']=name
 if 'brand_description' in old: out['farm_description']=old['brand_description']
 return out

def _load():
 c=_db(); saved={r['key']:json.loads(r['value']) for r in c.execute('SELECT key,value FROM settings')}; c.close()
 with _lock: _cache.clear(); _cache.update({k:saved.get(k,d[0]) for k,d in SCHEMA.items()})

def get(key):
 # Read by other modules (history retention, alerts); falls back to the default before configure()
 with _lock: return _cache.get(key,SCHEMA[key][0])

def all_settings():
 with _lock: return dict(_cache)

def validate(key,value):
 if key not in SCHEMA: raise HTTPException(400,f'Unknown setting: {key}')
 default,typ,rule=SCHEMA[key]; name=LABELS.get(key,key)
 if typ is bool:
  if not isinstance(value,bool): raise HTTPException(400,f'{name} must be on or off')
  return value
 if typ is int:
  if isinstance(value,bool) or not isinstance(value,(int,float)) or int(value)!=value: raise HTTPException(400,f'{name} must be a whole number')
  value=int(value)
  if not rule[0]<=value<=rule[1]: raise HTTPException(400,f'{name} must be between {rule[0]} and {rule[1]}')
  return value
 if not isinstance(value,str): raise HTTPException(400,f'{name} must be text')
 value=value.strip()
 if isinstance(rule[0],str):
  if value not in rule: raise HTTPException(400,f'{name} must be one of: {", ".join(rule)}')
 elif not rule[0]<=len(value)<=rule[1]: raise HTTPException(400,f'{name} is required' if rule[0] and not value else f'{name} must be at most {rule[1]} characters')
 return value

def valid_time_zone(name):
 try: ZoneInfo(name); return True
 except Exception: return False

def save(changes):
 clean={k:validate(k,v) for k,v in changes.items()}
 merged={**all_settings(),**clean}
 # Thresholds must stay in order (warning below hot/critical)
 if merged['temp_warn']>=merged['temp_hot']: raise HTTPException(400,'"Running hot" must be lower than "overheating"')
 if merged['fan_quiet_temp']>=merged['fan_full_temp']: raise HTTPException(400,'The fan\'s "quiet up to" temperature must be lower than its "full speed at" temperature')
 if merged['storage_warn']>=merged['storage_critical']: raise HTTPException(400,'The main drive warning level must be lower than the critical level')
 if clean.get('time_zone') and not valid_time_zone(clean['time_zone']): raise HTTPException(400,'Unknown time zone')
 c=_db(); c.executemany('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',[(k,json.dumps(v)) for k,v in clean.items()]); c.commit(); c.close()
 _load()
 for fn in after_save:
  try: fn(clean)
  except Exception as e: print(f'[settings] after-save hook failed: {e}',flush=True)
 return all_settings()

@router.get('')
def read(): return all_settings()

@router.put('')
def update(changes:dict): return save(changes)

# ---- History ----------------------------------------------------------------------------
@router.post('/clear-history/{kind}')
def clear_history(kind:str):
 queries={'network':["DELETE FROM net_checks"],'storage':["DELETE FROM storage_history"],'usage':["DELETE FROM net_daily"]}
 if kind=='all': sql=[q for v in queries.values() for q in v]
 elif kind in queries: sql=queries[kind]
 else: raise HTTPException(400,'Unknown history type')
 c=_db(); n=0
 for q in sql:
  try: n+=c.execute(q).rowcount
  except sqlite3.OperationalError: pass
 c.commit(); c.execute('VACUUM'); c.close(); return {'status':'cleared','rows':n}

# ---- Backup / restore -------------------------------------------------------------------
# Configuration only (printers, devices, services, settings). History is not included.
# ids are kept so a restore stays linked to existing uptime history
BACKUP_TABLES={'printers':['id','name','printer_type','base_url','api_key','serial','camera_url','enabled','sort_order','created_at','updated_at'],
 'net_devices':['id','name','host','kind','port','sort_order','created_at'],
 'services':['id','name','url','integration','token','sort_order','created_at']}
SECRET_COLUMNS={'printers':('api_key',),'services':('token',)}

@router.get('/backup')
def backup(secrets:bool=True):
 c=_db(); data={'app':'layerhound','version':APP_VERSION,'created':datetime.now(timezone.utc).isoformat(),'includes_secrets':secrets,'settings':all_settings()}
 for t,cols in BACKUP_TABLES.items():
  rows=[dict(zip(cols,r)) for r in c.execute(f'SELECT {",".join(cols)} FROM {t} ORDER BY sort_order,id')]
  # Secrets are encrypted with this board's own key, so a backup holds them in plain text
  # (to restore onto another board) or not at all
  for r in rows:
   for col in SECRET_COLUMNS.get(t,()): r[col]=vault.decrypt(r[col]) if secrets else None
  data[t]=rows
 c.close()
 name=f"layerhound-backup-{datetime.now().strftime('%Y-%m-%d')}.json"
 return Response(json.dumps(data,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{name}"'})

def fill(col,v,i):
 # Defaults for columns an older or hand-edited backup might leave out
 if v is not None: return v
 if col=='sort_order': return i+1
 if col=='enabled': return 1
 if col=='kind': return 'other'
 if col=='integration': return 'none'
 if col in ('created_at','updated_at'): return datetime.now(timezone.utc).isoformat()
 return None

@router.post('/restore')
def restore(data:dict):
 # Replaces printers, devices, services and settings with the backup's contents, all or nothing
 # 'ttrc-dashboard' is the app id used by backups made before the rename
 if data.get('app') not in ('layerhound','ttrc-dashboard'): raise HTTPException(400,"This file isn't a LayerHound backup")
 for t in BACKUP_TABLES:
  if not isinstance(data.get(t),list): raise HTTPException(400,f'Backup is missing its {t} list')
 raw=data.get('settings') or {}
 settings_in={**upgrade_keys(raw),**{k:v for k,v in raw.items() if k in SCHEMA}}
 for k,v in settings_in.items(): validate(k,v)
 c=_db()
 try:
  c.execute('BEGIN')
  for t,cols in BACKUP_TABLES.items():
   c.execute(f'DELETE FROM {t}')
   for i,r in enumerate(data[t]):
    if not isinstance(r,dict): raise HTTPException(400,f'Bad entry in {t}')
    vals=[vault.encrypt(r.get(col)) if col in SECRET_COLUMNS.get(t,()) else r.get(col) for col in cols]
    if t=='printers' and not (r.get('name') and r.get('printer_type') and r.get('base_url')): raise HTTPException(400,'A printer in the backup is missing its name, type or address')
    c.execute(f'INSERT INTO {t}({",".join(cols)}) VALUES({",".join("?"*len(cols))})',[fill(col,v,i) for col,v in zip(cols,vals)])
  c.execute('DELETE FROM settings')
  c.executemany('INSERT INTO settings(key,value) VALUES(?,?)',[(k,json.dumps(v)) for k,v in settings_in.items()])
  c.commit()
 except HTTPException: c.rollback(); raise
 except Exception as e: c.rollback(); raise HTTPException(400,f'Restore failed: {e}')
 finally: c.close()
 _load()
 for fn in after_restore: fn()
 return {'status':'restored','printers':len(data['printers']),'devices':len(data['net_devices']),'services':len(data['services']),'secrets_missing':not data.get('includes_secrets',True)}

# ---- About / maintenance ----------------------------------------------------------------
# Set only in the layerhound systemd unit (deploy/setup.sh). Checking systemd's own INVOCATION_ID
# isn't enough: other systemd-managed processes (e.g. CI runners) have it too.
def as_service(): return os.environ.get('LAYERHOUND_SERVICE')=='1'
# Set in the Docker image (Dockerfile). Docker restarts the container, but there's no board to manage.
def in_docker(): return os.environ.get('LAYERHOUND_DOCKER')=='1'
# Running unattended (board service or container): background jobs like the daily update check run
def unattended(): return as_service() or in_docker()

_about_paths={'db':None,'files':None}
def set_paths(db_path,files_root): _about_paths.update(db=str(db_path),files=str(files_root))

@router.get('/about')
def about_info():
 me=psutil.Process(); db=Path(_about_paths['db']) if _about_paths['db'] else None
 return {'version':APP_VERSION,'python':platform.python_version(),'platform':platform.platform(),
  'database':_about_paths['db'],'database_bytes':db.stat().st_size if db and db.exists() else None,'files_folder':_about_paths['files'],
  'started':datetime.fromtimestamp(me.create_time(),timezone.utc).isoformat(),'memory_mb':round(me.memory_info().rss/2**20,1),
  'runtime':'board' if as_service() else 'docker' if in_docker() else 'manual',
  'can_restart':unattended(),'can_shutdown':as_service(),'restart_note':None if unattended() else 'Restart is available when the dashboard runs as a service on the board. Here, restart it from the terminal.'}

@router.post('/shutdown')
def shutdown():
 # Powers off the whole board cleanly, so the power can be unplugged safely (e.g. to swap the SD
 # card). setup.sh allows the LayerHound user to power off the board, and nothing more.
 if not as_service(): raise HTTPException(409,'Shut down is only available on the LayerHound board')
 threading.Timer(1.0,lambda:subprocess.run(['systemctl','poweroff'],capture_output=True,timeout=30)).start()
 return {'status':'shutting down'}

@router.post('/restart')
def restart():
 if not unattended(): raise HTTPException(409,'Restart is only available when the dashboard runs as a service on the board')
 # Exit shortly after replying; systemd (Restart=always) starts it again within a few seconds
 threading.Timer(0.5,lambda:os._exit(0)).start(); return {'status':'restarting'}
