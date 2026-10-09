from datetime import datetime, timezone
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json, os, platform, re, socket, sqlite3, ssl, sys, threading, time, urllib.parse, urllib.request
import paho.mqtt.client as mqtt
import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import auth, discovery, fan, history, hotspot, lightbar, remote, stats, updates, vault, media, network, services, settings, storage, wifi
from fastapi.responses import Response

# LAYERHOUND_* settings; the older TTRC_* names still work
def env(name): return os.environ.get(f'LAYERHOUND_{name}') or os.environ.get(f'TTRC_{name}')
DB_PATH=Path(env('DB') or Path(__file__).with_name('layerhound.db')); TIMEOUT=4
# Installs from before the rename used ttrc.db; carry it over once
if not env('DB') and not DB_PATH.exists() and DB_PATH.with_name('ttrc.db').exists(): DB_PATH.with_name('ttrc.db').rename(DB_PATH)
# Built frontend (npm run build). When present, this server hosts the whole dashboard.
DIST=Path(__file__).resolve().parent.parent/'dist'
TYPES=('moonraker','octoprint','bambu'); MODELS={'moonraker':'Klipper / Moonraker','octoprint':'OctoPrint','bambu':'Bambu Lab'}
app=FastAPI(title='LayerHound API',version=settings.APP_VERSION)
# Sign-in check on every /api request (see auth.py); CORS is added after so it wraps it
app.middleware('http')(auth.middleware)
# While the setup hotspot is on, send phones to the setup page (runs before the sign-in check)
app.middleware('http')(hotspot.middleware)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

def now(): return datetime.now(timezone.utc).isoformat()
def db():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def init():
 c=db(); c.execute('''CREATE TABLE IF NOT EXISTS printers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,printer_type TEXT NOT NULL,base_url TEXT NOT NULL,api_key TEXT,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
 # v0.3.1: display order for the Print Farm grid; existing printers keep their add order
 if 'sort_order' not in [r['name'] for r in c.execute('PRAGMA table_info(printers)')]:
  c.execute('ALTER TABLE printers ADD COLUMN sort_order INTEGER'); c.execute('UPDATE printers SET sort_order=id')
 # v0.3.2: Bambu Lab printers are addressed by serial number (access code lives in api_key)
 if 'serial' not in [r['name'] for r in c.execute('PRAGMA table_info(printers)')]: c.execute('ALTER TABLE printers ADD COLUMN serial TEXT')
 # v0.4.2: optional camera address for printers whose camera LayerHound can't find on its own
 if 'camera_url' not in [r['name'] for r in c.execute('PRAGMA table_info(printers)')]: c.execute('ALTER TABLE printers ADD COLUMN camera_url TEXT')
 c.commit(); c.close()
init()
# Printer access codes, API keys and service tokens are stored encrypted (see vault.py)
KEY_PATH=Path(env('KEY') or DB_PATH.parent/'data'/'secret.key')
vault.configure(KEY_PATH)
class PrinterIn(BaseModel):
 name:str=Field(min_length=1,max_length=80); printer_type:str; base_url:str; api_key:str|None=None; serial:str|None=None; camera_url:str|None=None; enabled:bool=True
class PrinterUpdate(BaseModel):
 name:str|None=Field(default=None,min_length=1,max_length=80); printer_type:str|None=None; base_url:str|None=None; api_key:str|None=None; serial:str|None=None; camera_url:str|None=None
class PrinterOrder(BaseModel):
 ids:list[int]

def clean_url(v):
 v=v.strip(); return v if v.startswith(('http://','https://','mqtts://')) else 'http://'+v

def get_json(u,headers=None):
 r=urllib.request.Request(u,headers=headers or {}); 
 with urllib.request.urlopen(r,timeout=TIMEOUT) as x: return json.loads(x.read().decode())

def moonraker(base):
 info=get_json(base+'/printer/info'); s=get_json(base+'/printer/objects/query?print_stats=&virtual_sdcard=&toolhead=extruder&heater_bed=&extruder=&extruder1=&extruder2=&extruder3=&gcode_move=gcode_position')
 o=s.get('result',{}).get('status',{}); ps=o.get('print_stats') or {}; vsd=o.get('virtual_sdcard') or {}; bed=o.get('heater_bed') or {}
 # Multi-toolhead printers (e.g. Snapmaker U1) print from extruder1-3, so read whichever tool is active
 ex=o.get((o.get('toolhead') or {}).get('extruder') or 'extruder') or o.get('extruder') or {}
 raw=str(ps.get('state') or 'unknown').lower(); state={'printing':'printing','paused':'paused','complete':'complete','standby':'idle','ready':'idle','error':'error'}.get(raw,'idle')
 # print_stats has no progress field; virtual_sdcard reports file progress (0-1)
 frac=max(0.0,min(1.0,float(vsd.get('progress') or 0))); elapsed=float(ps.get('print_duration') or 0)
 # Estimate remaining time from progress so far (same "file" method Mainsail/Fluidd use)
 eta=elapsed/frac-elapsed if frac>0 and state in ('printing','paused') else 0
 # Files in subfolders (e.g. a USB drive, "sda1/...") come back with their folder path; show just the file name
 path=str(ps.get('filename') or ''); job=path.rsplit('/',1)[-1] or None
 meta=media.moonraker_meta(base,path) if path else None
 z=((o.get('gcode_move') or {}).get('gcode_position') or [None]*3)[2]
 layer,total_layers=media.moonraker_layers(meta,ps.get('info'),vsd,z,state in ('printing','paused'))
 return dict(connected=True,state=state,raw_state=raw,job=job,job_path=path or None,layer=layer,total_layers=total_layers,has_thumbnail=bool(meta and meta.get('thumbnails')),print_seconds=elapsed or None,elapsed_seconds=float(ps.get('total_duration') or 0) or None,filament_mm=float(ps.get('filament_used') or 0) or None,progress=round(frac*100,1),eta_seconds=round(eta),nozzle=round(float(ex.get('temperature') or 0),1),nozzle_target=round(float(ex.get('target') or 0),1),bed=round(float(bed.get('temperature') or 0),1),bed_target=round(float(bed.get('target') or 0),1),firmware=info.get('result',{}).get('software_version'),error=None)

def octoprint(base,key):
 h={'X-Api-Key':key} if key else {}; ver=get_json(base+'/api/version',h); job=get_json(base+'/api/job',h); pr=get_json(base+'/api/printer',h); raw=str(job.get('state') or 'Offline').lower()
 state={'printing':'printing','paused':'paused','pausing':'paused','complete':'complete','operational':'idle','ready':'idle','offline':'offline','error':'error'}.get(raw,'idle'); prog=job.get('progress') or {}; temps=pr.get('temperature') or {}; tool=temps.get('tool0') or {}; bed=temps.get('bed') or {}
 return dict(connected=True,state=state,raw_state=raw,job=(job.get('job') or {}).get('file',{}).get('name'),progress=round(float(prog.get('completion') or 0),1),elapsed_seconds=prog.get('printTime'),eta_seconds=round(float(prog.get('printTimeLeft') or 0)),nozzle=round(float(tool.get('actual') or 0),1),nozzle_target=round(float(tool.get('target') or 0),1),bed=round(float(bed.get('actual') or 0),1),bed_target=round(float(bed.get('target') or 0),1),firmware=ver.get('server'),error=None)

# Bambu Lab printers have no HTTP API. They publish status over MQTT (TLS, port 8883,
# user "bblp", password = the printer's LAN access code). Reports after the first are
# partial updates, so each printer gets one long-lived connection that merges them.
class BambuWatcher:
 def __init__(s,host,port,serial,code):
  s.key=(host,port,serial,code); s.serial=serial; s.data={}; s.firmware=None; s.error=None; s.ready=threading.Event()
  s.answers={}   # printer's reply to a command we sent (pause/resume/stop): command -> (result, reason, time)
  c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=f'layerhound-{serial}-{os.getpid()}'); c.username_pw_set('bblp',code)
  # The printer uses a self-signed certificate, so it can't be verified
  # Bambu printers use self-signed certificates, so they can't be verified; still require modern TLS
  ctx=ssl.create_default_context(); ctx.minimum_version=ssl.TLSVersion.TLSv1_2; ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE; c.tls_set_context(ctx)
  c.on_connect=s._connected; c.on_connect_fail=s._failed; c.on_disconnect=s._disconnected; c.on_message=s._message
  c.reconnect_delay_set(2,30); s.client=c; c.connect_async(host,port,keepalive=30); c.loop_start()
 def _connected(s,c,u,flags,rc,props=None):
  if rc.is_failure: s.error=f'Printer refused the connection ({rc}). Check the serial number and access code.'; s.ready.set(); return
  s.error=None; c.subscribe(f'device/{s.serial}/report'); req=f'device/{s.serial}/request'
  c.publish(req,json.dumps({'pushing':{'sequence_id':'0','command':'pushall'}})); c.publish(req,json.dumps({'info':{'sequence_id':'0','command':'get_version'}}))
 def _failed(s,c,u): s.error='Could not reach the printer on port 8883. Check the IP address and that the printer is on.'; s.ready.set()
 def _disconnected(s,c,u,flags,rc,props=None):
  if rc.is_failure: s.error=f'Disconnected from printer ({rc})'
 def _message(s,c,u,msg):
  try: m=json.loads(msg.payload)
  except ValueError: return
  if isinstance(m.get('print'),dict):
   p=m['print']
   if p.get('command') in ('pause','resume','stop') and 'result' in p:
    s.answers[p['command']]=(str(p.get('result')).lower(),p.get('reason') or '',time.time())
   s.data.update({k:v for k,v in p.items() if k not in ('command','result','reason','sequence_id')}); s.ready.set()
  for mod in (m.get('info') or {}).get('module') or []:
   if mod.get('name')=='ota': s.firmware=mod.get('sw_ver')
 def stop(s): s.client.disconnect(); s.client.loop_stop()

bambu_watchers={}; bambu_lock=threading.Lock()
def bambu_stop(pid):
 with bambu_lock: w=bambu_watchers.pop(pid,None)
 if w: w.stop()
def bambu_stop_all():
 for pid in list(bambu_watchers): bambu_stop(pid)

def bambu(pid,base,serial,code):
 if not serial or not code: raise ValueError('Bambu printers need a serial number and access code')
 u=urllib.parse.urlparse(base); key=(u.hostname,u.port or 8883,serial,code)
 with bambu_lock:
  w=bambu_watchers.get(pid)
  if w and w.key!=key: w.stop(); w=None
  if not w: w=bambu_watchers[pid]=BambuWatcher(*key)
 w.ready.wait(TIMEOUT)
 if not w.client.is_connected(): raise ConnectionError(w.error or f'Could not connect to {key[0]}:{key[1]}. Check the IP address and access code, and try turning on LAN Only mode on the printer.')
 if not w.data: raise ConnectionError('Connected, but the printer sent no status. Check the serial number.')
 p=w.data; raw=str(p.get('gcode_state') or 'unknown').lower()
 state={'running':'printing','prepare':'printing','slicing':'printing','pause':'paused','finish':'complete','failed':'error','idle':'idle'}.get(raw,'idle')
 # mc_remaining_time is in minutes
 eta=int(p.get('mc_remaining_time') or 0)*60 if state in ('printing','paused') else 0
 # Bambu doesn't report elapsed time; estimate it from progress and time remaining
 pct=float(p.get('mc_percent') or 0); elapsed=eta*pct/(100-pct) if eta and 0<pct<100 else None
 return dict(connected=True,state=state,raw_state=raw,job=p.get('subtask_name') or p.get('gcode_file') or None,elapsed_seconds=elapsed,
  layer=p.get('layer_num') if state in ('printing','paused') and p.get('total_layer_num') else None,total_layers=p.get('total_layer_num') if state in ('printing','paused') else None,progress=round(float(p.get('mc_percent') or 0),1),eta_seconds=eta,nozzle=round(float(p.get('nozzle_temper') or 0),1),nozzle_target=round(float(p.get('nozzle_target_temper') or 0),1),bed=round(float(p.get('bed_temper') or 0),1),bed_target=round(float(p.get('bed_target_temper') or 0),1),firmware=w.firmware,error=None)

# Some printers (e.g. the Elegoo Neptune 4's Moonraker) occasionally answer slowly under load.
# Ride out a brief hiccup by showing the last good reading; report offline only after this long.
OFFLINE_GRACE=45; last_good={}
_logged_errors={}
def printer_error(e):
 # Plain-language reason a printer can't be read; the technical detail goes to the service log
 if type(e) in (ValueError,ConnectionError): return str(e)   # already worded for owners (e.g. Bambu checks)
 text=f'{type(e).__name__}: {e}'.lower()
 code=getattr(e,'code',None)
 if code in (401,403): return 'The printer rejected the API key. Check it in Edit printer.'
 if code==404 or 'jsondecodeerror' in text or 'expecting value' in text:
  return "Something answered at that address, but it isn't the printer's interface. Check the address and port."
 if 'refused' in text: return 'The printer refused the connection. Check the address and port (Klipper usually uses :7125; some printers use port 80).'
 if 'timed out' in text or 'timeout' in text: return "The printer didn't answer in time. Check that it's on and connected to the network."
 if 'nodename' in text or 'name or service' in text or 'getaddrinfo' in text or 'name resolution' in text:
  return "Couldn't find that printer name on the network. Try its IP address instead."
 if 'unreachable' in text or 'no route' in text: return "Can't reach that address. Check the printer's IP address."
 if 'ssl' in text or 'certificate' in text: return 'A secure connection to the printer failed. Try http:// instead of https://.'
 return "Couldn't read the printer. Check the address and that it's on."

def snapshot(r,grace=True):
 t=r['printer_type']; base=clean_url(r['base_url']); key=(r['id'],base)
 try:
  x=moonraker(base) if t=='moonraker' else bambu(r['id'],base,r['serial'],vault.decrypt(r['api_key'])) if t=='bambu' else octoprint(base,vault.decrypt(r['api_key']))
  last_good[key]=(time.time(),x)
 except Exception as e:
  prev=last_good.get(key)
  if grace and prev and time.time()-prev[0]<OFFLINE_GRACE: x=prev[1]
  else:
   detail=f'{type(e).__name__}: {e}'
   if _logged_errors.get(key)!=detail: _logged_errors[key]=detail; print(f"[printer] {r['name']}: {detail}",flush=True)
   x=dict(connected=False,state='offline',raw_state='offline',job=None,progress=0,eta_seconds=0,nozzle=0,nozzle_target=0,bed=0,bed_target=0,firmware=None,error=printer_error(e))
 return {'id':r['id'],'name':r['name'],'printer_type':r['printer_type'],'model':MODELS.get(t,t),'base_url':base.rstrip('/'),'serial':r['serial'],'enabled':bool(r['enabled']),
  'camera_url':r['camera_url'],'has_camera':media.has_camera(r),**x,'updated_at':now()}

# ---- Printer controls (pause / resume / cancel) -----------------------------------------
# Off unless an admin turns on Settings -> Printer controls. Admins only (the sign-in check refuses
# changes from viewers and access keys). Each action is checked against the printer's state first,
# and logged to the service log.
CONTROL_ALLOWED={'pause':('printing',),'resume':('paused',),'cancel':('printing','paused')}
CONTROL_PAST={'pause':'paused','resume':'resumed','cancel':'cancelled'}
BAMBU_COMMAND={'pause':'pause','resume':'resume','cancel':'stop'}
BAMBU_WAIT=6

def post_json(u,body=None,headers=None):
 data=json.dumps(body).encode() if body is not None else b''
 r=urllib.request.Request(u,data=data,method='POST',headers={'Content-Type':'application/json',**(headers or {})})
 with urllib.request.urlopen(r,timeout=TIMEOUT+4) as x: return x.status

def control_moonraker(base,action):
 post_json(f"{base}/printer/print/{action}")

def control_octoprint(base,key,action):
 body={'command':'cancel'} if action=='cancel' else {'command':'pause','action':action}
 post_json(base+'/api/job',body,{'X-Api-Key':key} if key else {})

def control_bambu(pid,action):
 with bambu_lock: w=bambu_watchers.get(pid)
 if not w or not w.client.is_connected(): raise ConnectionError("LayerHound isn't connected to this printer right now.")
 cmd=BAMBU_COMMAND[action]; sent=time.time()
 w.client.publish(f'device/{w.serial}/request',json.dumps({'print':{'sequence_id':str(int(sent)),'command':cmd,'param':''}}))
 # The printer answers with the command and "success" or "fail" (newer firmware refuses outside
 # LAN Only / Developer mode); if it says nothing, the state change will show it
 end=sent+BAMBU_WAIT
 while time.time()<end:
  a=w.answers.get(cmd)
  if a and a[2]>=sent:
   if a[0]!='success': raise PermissionError(f"The printer refused it{': '+a[1] if a[1] else ''}. Newer Bambu firmware only accepts controls from other apps in LAN Only mode (and on some models, Developer mode).")
   return
  time.sleep(0.2)

def control_error(e):
 code=getattr(e,'code',None)
 if isinstance(e,(PermissionError,ConnectionError)): return str(e)
 if code in (401,403): return 'The printer refused: LayerHound needs permission to control it. For OctoPrint, add the printer again with "Allow in OctoPrint"; for Klipper, check Moonraker\'s trusted clients.'
 if code==409: return "The printer can't do that right now (its state may have just changed)."
 return printer_error(e)

class ControlIn(BaseModel):
 action:str

@app.post('/api/printers/{pid}/control')
def control(pid:int,b:ControlIn,request:Request):
 if not settings.get('printer_controls'): raise HTTPException(403,'Printer controls are off. An admin can turn them on in Settings -> Printer controls.')
 if b.action not in CONTROL_ALLOWED: raise HTTPException(400,'Action must be pause, resume or cancel')
 c=db(); r=c.execute('SELECT * FROM printers WHERE id=?',(pid,)).fetchone(); c.close()
 if not r: raise HTTPException(404,'Printer not found')
 now_state=snapshot(r,grace=False)
 if now_state['state'] not in CONTROL_ALLOWED[b.action]:
  raise HTTPException(409,f"{r['name']} is {now_state['state']}, so it can't be {CONTROL_PAST[b.action]} now.")
 t=r['printer_type']; base=clean_url(r['base_url']); who=(getattr(request.state,'who',None) or {}).get('username') or '?'
 try:
  if t=='moonraker': control_moonraker(base,b.action)
  elif t=='octoprint': control_octoprint(base,vault.decrypt(r['api_key']),b.action)
  else: control_bambu(pid,b.action)
 except Exception as e:
  print(f"[control] {who}: {b.action} {r['name']} failed: {type(e).__name__}: {e}",flush=True)
  raise HTTPException(502,control_error(e))
 print(f"[control] {who}: {b.action} {r['name']}",flush=True)
 time.sleep(1.5)   # let the printer change state before reading it again
 return {'status':'sent','action':b.action,'printer':check(r)}

# Which build of the dashboard is being served: the hashed name of its main script, which changes
# with every build. Open tabs compare it with their own to offer a reload after an update.
_build={'mtime':None,'id':None}
def build_id():
 index=DIST/'index.html'
 try: m=index.stat().st_mtime
 except OSError: return None
 if m!=_build['mtime']:
  found=re.search(r'assets/(index-[\w-]+\.js)',index.read_text())
  _build.update(mtime=m,id=found.group(1) if found else None)
 return _build['id']

@app.get('/api/health')
def health(): return {'status':'ok','service':'layerhound-api','version':settings.APP_VERSION,'build':build_id(),'timestamp':now()}
# ---- Server monitoring ----------------------------------------------------------
# Temperature sensors differ per board. Linux thermal zones (e.g. the ROCK 4D's
# "soc_thermal", "bigcore_thermal") often have blank labels, so match on the group
# name too. First match in this list wins for the headline temperature.
TEMP_PREFS=('soc','cpu','package','bigcore','core')
def temperatures():
 out=[]
 try: groups=psutil.sensors_temperatures() if hasattr(psutil,'sensors_temperatures') else {}
 except Exception: groups={}
 for group,sensors in groups.items():
  for i,t in enumerate(sensors):
   if t.current is None or t.current<=0: continue
   name=f'{group} {t.label}'.strip() if t.label else (group if len(sensors)==1 else f'{group} {i}')
   out.append({'name':name,'celsius':round(t.current,1),'high':t.high or None,'critical':t.critical or None})
 return out
def main_temp(temps):
 for pref in TEMP_PREFS:
  for t in temps:
   if pref in t['name'].lower(): return t['celsius']
 return temps[0]['celsius'] if temps else None

def disks():
 out=[]; mac=sys.platform=='darwin'
 for p in psutil.disk_partitions():
  m=p.mountpoint
  if p.fstype in ('squashfs','overlay','tmpfs','devtmpfs') or m.startswith(('/snap','/boot')): continue
  # macOS: "/" is the read-only system volume; your files live on the Data volume
  if mac and m.startswith('/System/Volumes/') and m!='/System/Volumes/Data': continue
  if mac and m=='/': continue
  try: u=psutil.disk_usage(m)
  except OSError: continue
  # Small system partitions (e.g. the board image's /config) aren't drives anyone stores things on
  if m not in ('/','/System/Volumes/Data') and u.total<2**30: continue
  out.append({'mount':'/' if m=='/System/Volumes/Data' else m,'mountpoint':m,'device':p.device,'fstype':p.fstype,'total_gb':round(u.total/2**30,1),'used_gb':round(u.used/2**30,1),'percent':u.percent})
 return sorted(out,key=lambda d:(d['mount']!='/',d['mount']))

def os_name():
 try:
  for line in open('/etc/os-release'):
   if line.startswith('PRETTY_NAME='): return line.split('=',1)[1].strip().strip('"')
 except OSError: pass
 return f'macOS {platform.mac_ver()[0]}' if sys.platform=='darwin' else platform.platform()

# One background sampler owns psutil.cpu_percent (it measures "since the last call",
# so several callers would skew each other) and keeps an hour of history.
SAMPLE_EVERY=5; HISTORY=deque(maxlen=3600//SAMPLE_EVERY)
latest={'cpu':0.0,'per_core':[],'rx_bps':0.0,'tx_bps':0.0,'temps':[]}
def net_totals():
 n=psutil.net_io_counters(pernic=True); real=[v for k,v in n.items() if not k.startswith('lo')]
 return sum(v.bytes_recv for v in real),sum(v.bytes_sent for v in real)
def sampler():
 psutil.cpu_percent(percpu=True); rx0,tx0=net_totals(); t0=time.time(); next_storage=0
 while True:
  time.sleep(SAMPLE_EVERY)
  try:
   if time.time()>=next_storage: storage.record_usage(); next_storage=time.time()+storage.RECORD_EVERY
   cores=psutil.cpu_percent(percpu=True); rx,tx=net_totals(); t=time.time(); dt=max(t-t0,1e-6)
   temps=temperatures()
   latest.update(cpu=round(sum(cores)/len(cores),1),per_core=cores,rx_bps=max(0,(rx-rx0)/dt),tx_bps=max(0,(tx-tx0)/dt),temps=temps)
   rx0,tx0,t0=rx,tx,t
   HISTORY.append({'t':round(t),'cpu':latest['cpu'],'memory':psutil.virtual_memory().percent,'temp':main_temp(temps),'rx_bps':round(latest['rx_bps']),'tx_bps':round(latest['tx_bps'])})
  except Exception as e: print('sampler error:',e,flush=True)
auth.configure(db); app.include_router(auth.router)
updates.configure(DB_PATH.parent/'data'); app.include_router(updates.router)
settings.configure(db); fan.configure(); app.include_router(settings.router); settings.after_restore.append(bambu_stop_all); settings.set_paths(DB_PATH,storage.FILES_ROOT)
storage.configure(db,disks); app.include_router(storage.router)
app.include_router(wifi.router); app.include_router(hotspot.router); hotspot.configure(); app.include_router(remote.router); lightbar.configure(lambda: printers()); app.include_router(lightbar.router)
network.configure(db); app.include_router(network.router)
services.configure(db); app.include_router(services.router)
vault.migrate(db)
threading.Thread(target=sampler,daemon=True,name='layerhound-sampler').start()

def primary_ip():
 # First IPv4 on an interface that's up, skipping loopback and virtual/VPN adapters
 skip=('lo','docker','br-','veth','utun','bridge','tailscale','zt','wg')
 stats=psutil.net_if_stats()
 for n,addrs in psutil.net_if_addrs().items():
  if n.startswith(skip) or not getattr(stats.get(n),'isup',False): continue
  for a in addrs:
   if a.family==socket.AF_INET and not a.address.startswith(('127.','169.254.')): return a.address
 return None

def database_check():
 try:
  c=db(); n=c.execute('SELECT COUNT(*) FROM printers').fetchone()[0]; c.close(); return {'ok':True,'printers':n}
 except Exception as e:
  print(f'[database] check failed: {type(e).__name__}: {e}',flush=True)
  return {'ok':False,'error':"The database couldn't be read. See the service log."}

@app.get('/api/system')
def system():
 vm=psutil.virtual_memory(); root=next((d for d in disks() if d['mount']=='/'),None); temps=latest['temps'] or temperatures()
 return {'hostname':socket.gethostname(),'platform':platform.platform(),'cpu_percent':latest['cpu'],'memory_percent':vm.percent,'memory_used_gb':round((vm.total-vm.available)/2**30,2),'memory_total_gb':round(vm.total/2**30,2),'storage_percent':root['percent'] if root else 0,'storage_used_gb':root['used_gb'] if root else 0,'storage_total_gb':root['total_gb'] if root else 0,'temperature_c':main_temp(temps),'uptime_seconds':round(time.time()-psutil.boot_time()),'rx_bps':round(latest['rx_bps']),'tx_bps':round(latest['tx_bps']),'ip':primary_ip(),'database':database_check(),'network':network.alerts(),'services':services.summary(),'timestamp':now()}

@app.get('/api/server')
def server():
 vm=psutil.virtual_memory(); sw=psutil.swap_memory(); temps=latest['temps'] or temperatures()
 try: freq=psutil.cpu_freq()
 except Exception: freq=None
 ips=[{'interface':n,'address':a.address} for n,addrs in psutil.net_if_addrs().items() for a in addrs if a.family==socket.AF_INET and not a.address.startswith('127.')]
 me=psutil.Process()
 return {'hostname':socket.gethostname(),'os':os_name(),'kernel':platform.release(),'arch':platform.machine(),'python':platform.python_version(),
  'boot_time':datetime.fromtimestamp(psutil.boot_time(),timezone.utc).isoformat(),'uptime_seconds':round(time.time()-psutil.boot_time()),
  'cpu':{'percent':latest['cpu'],'per_core':latest['per_core'],'cores':psutil.cpu_count(),'physical_cores':psutil.cpu_count(logical=False),'freq_mhz':round(freq.current) if freq else None,'freq_max_mhz':round(freq.max) if freq and freq.max else None,'load_avg':[round(x,2) for x in os.getloadavg()]},
  'memory':{'percent':vm.percent,'used_gb':round((vm.total-vm.available)/2**30,2),'total_gb':round(vm.total/2**30,2),'swap_percent':sw.percent,'swap_used_gb':round(sw.used/2**30,2),'swap_total_gb':round(sw.total/2**30,2)},
  'temperature_c':main_temp(temps),'sensors':temps,'disks':disks(),'fan':fan.status(),
  'network':{'rx_bps':round(latest['rx_bps']),'tx_bps':round(latest['tx_bps']),'addresses':ips},
  'app':{'memory_mb':round(me.memory_info().rss/2**20,1),'threads':me.num_threads(),'started':datetime.fromtimestamp(me.create_time(),timezone.utc).isoformat()},
  'sample_seconds':SAMPLE_EVERY,'timestamp':now()}

@app.get('/api/server/history')
def server_history(): return {'sample_seconds':SAMPLE_EVERY,'points':list(HISTORY)}
# ---- Background printer checks ------------------------------------------------------------
# Every printer is checked every few seconds whether or not anyone has the dashboard open.
# This feeds print history; the dashboard reads the latest results.
POLL_EVERY=10; CACHE_MAX_AGE=30; printer_cache={}
def printer_rows():
 c=db(); rows=c.execute('SELECT * FROM printers ORDER BY sort_order,id').fetchall(); c.close(); return rows
def check(r):
 x=snapshot(r); printer_cache[r['id']]=(time.time(),r['base_url'],x)
 try: history.observe(x)
 except Exception as e: print('history error:',e,flush=True)
 return x
def check_all(rows):
 # In parallel so one slow or offline printer doesn't hold up the rest
 if not rows: return []
 with ThreadPoolExecutor(max_workers=len(rows)) as ex: return list(ex.map(check,rows))
def printer_poller():
 while True:
  t=time.time()
  try: check_all([r for r in printer_rows() if r['enabled']])
  except Exception as e: print('printer check error:',e,flush=True)
  time.sleep(max(1,POLL_EVERY-(time.time()-t)))

@app.get('/api/printers')
def printers():
 rows=[r for r in printer_rows() if r['enabled']]; out=[]; stale=[]
 for r in rows:
  hit=printer_cache.get(r['id'])
  if hit and hit[1]==r['base_url'] and time.time()-hit[0]<CACHE_MAX_AGE: out.append(hit[2])
  else: out.append(None); stale.append(r)
 fresh=iter(check_all(stale))
 # Keep display order; names come from the database so renames show immediately
 return {'printers':[{**(x or next(fresh)),'name':r['name']} for r,x in zip(rows,out)]}
@app.get('/api/printers/{pid}')
def printer(pid:int,grace:bool=True):
 c=db(); r=c.execute('SELECT * FROM printers WHERE id=?',(pid,)).fetchone(); c.close()
 if not r: raise HTTPException(404,'Printer not found')
 return snapshot(r,grace)
def camera_url(v):
 # Optional camera address: a snapshot or MJPEG stream URL. Blank means "find it automatically".
 v=(v or '').strip()
 if not v: return None
 if not v.lower().startswith(('http://','https://')): raise HTTPException(400,'Camera URL must start with http:// or https://')
 return v

@app.post('/api/printers')
def add(p:PrinterIn):
 if p.printer_type not in TYPES: raise HTTPException(400,'Invalid printer type')
 serial=(p.serial or '').strip().upper() or None
 if p.printer_type=='bambu' and not (serial and p.api_key): raise HTTPException(400,'Bambu printers need a serial number and access code')
 c=db(); t=now(); nxt=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM printers').fetchone()[0]; cur=c.execute('INSERT INTO printers(name,printer_type,base_url,api_key,serial,camera_url,enabled,created_at,updated_at,sort_order) VALUES(?,?,?,?,?,?,?,?,?,?)',(p.name.strip(),p.printer_type,clean_url(p.base_url).rstrip('/'),vault.encrypt(p.api_key),serial if p.printer_type=='bambu' else None,camera_url(p.camera_url),int(p.enabled),t,t,nxt)); c.commit(); r=c.execute('SELECT * FROM printers WHERE id=?',(cur.lastrowid,)).fetchone(); c.close(); return snapshot(r)
# Declared before the /{pid} routes so "order" isn't parsed as a printer id
@app.put('/api/printers/order')
def reorder(o:PrinterOrder):
 c=db(); c.executemany('UPDATE printers SET sort_order=? WHERE id=?',[(i+1,pid) for i,pid in enumerate(o.ids)]); c.commit(); c.close(); return {'status':'ok','ids':o.ids}
@app.put('/api/printers/{pid}')
def edit(pid:int,p:PrinterUpdate):
 c=db(); r=c.execute('SELECT * FROM printers WHERE id=?',(pid,)).fetchone()
 if not r: c.close(); raise HTTPException(404,'Printer not found')
 if p.printer_type is not None and p.printer_type not in TYPES: c.close(); raise HTTPException(400,'Invalid printer type')
 name=p.name.strip() if p.name else r['name']; ptype=p.printer_type or r['printer_type']; url=clean_url(p.base_url).rstrip('/') if p.base_url else r['base_url']
 # A blank API key means "keep the saved one" so the key never has to be sent back to the browser
 key=None if ptype=='moonraker' else (vault.encrypt(p.api_key.strip()) if p.api_key and p.api_key.strip() else r['api_key'])
 serial=None if ptype!='bambu' else ((p.serial or '').strip().upper() or r['serial'])
 if ptype=='bambu' and not (serial and key): c.close(); raise HTTPException(400,'Bambu printers need a serial number and access code')
 cam=r['camera_url'] if p.camera_url is None else camera_url(p.camera_url)
 c.execute('UPDATE printers SET name=?,printer_type=?,base_url=?,api_key=?,serial=?,camera_url=?,updated_at=? WHERE id=?',(name,ptype,url,key,serial,cam,now(),pid)); c.commit(); r=c.execute('SELECT * FROM printers WHERE id=?',(pid,)).fetchone(); c.close(); return snapshot(r)
def printer_row(pid):
 c=db(); r=c.execute('SELECT * FROM printers WHERE id=?',(pid,)).fetchone(); c.close()
 if not r: raise HTTPException(404,'Printer not found')
 return r

@app.get('/api/printers/{pid}/thumbnail')
def thumbnail(pid:int):
 # The slicer's preview image of the part being printed (Klipper printers)
 r=printer_row(pid); hit=printer_cache.get(pid); path=hit and hit[2].get('job_path')
 if r['printer_type']!='moonraker' or not path: raise HTTPException(404,'No thumbnail')
 got=media.moonraker_thumbnail(clean_url(r['base_url']).rstrip('/'),path)
 if not got: raise HTTPException(404,'No thumbnail')
 return Response(got[0],media_type=got[1] or 'image/png',headers={'Cache-Control':'max-age=300'})

@app.get('/api/printers/{pid}/camera')
def camera(pid:int):
 # One current camera frame; the dashboard refreshes it every couple of seconds
 r=printer_row(pid)
 try: img=media.camera_frame(r)
 except Exception as e:
  detail=f'{type(e).__name__}: {e}'
  if _logged_errors.get(('camera',pid))!=detail: _logged_errors[('camera',pid)]=detail; print(f'[camera] printer {pid}: {detail}',flush=True)
  raise HTTPException(502,'Camera unavailable. Check that the printer is on and its camera is enabled.')
 if img is None: raise HTTPException(404,'No camera configured for this printer')
 return Response(img,media_type='image/jpeg',headers={'Cache-Control':'no-store'})

@app.delete('/api/printers/{pid}')
def remove(pid:int):
 c=db(); cur=c.execute('DELETE FROM printers WHERE id=?',(pid,)); c.commit(); c.close(); bambu_stop(pid); printer_cache.pop(pid,None); history.forget_printer(pid)
 if not cur.rowcount: raise HTTPException(404,'Printer not found')
 return {'status':'deleted','id':pid}
@app.post('/api/printers/{pid}/test')
def test(pid:int):
 x=printer(pid,grace=False); return {'ok':x['connected'],'printer':x,'message':'Connection successful' if x['connected'] else (x['error'] or 'Connection failed')}

# Print history and the background printer checks need the printer functions defined above
history.configure(db,printer_rows); app.include_router(history.router)
# Printer suggestions: found on the network, not on the dashboard yet
discovery.configure(db,lambda d: add(PrinterIn(**d)),printer_rows); app.include_router(discovery.router)
auth.after_setup.append(discovery.after_setup)
# Optional anonymous usage stats (off until the owner says yes)
stats.configure(db,printer_rows,DB_PATH.parent/'data'); app.include_router(stats.router)
settings.after_save.append(lambda changed: 'usage_stats' in changed and stats.chosen(changed['usage_stats']))
threading.Thread(target=printer_poller,daemon=True,name='layerhound-printers').start()

# Must stay last: a mount at / would otherwise shadow the /api routes above
if DIST.is_dir(): app.mount('/',StaticFiles(directory=DIST,html=True),name='web')
