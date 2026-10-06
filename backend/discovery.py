# Printer suggestions: printers found on the network that aren't on the dashboard yet.
#
# - Every network scan (the Network page's, or the automatic ones here) feeds this list.
# - Automatic scans: shortly after first-run setup, then once a day (Settings, on by default).
# - Bambu printers also announce themselves on the local network (UDP port 2021, the same
#   announcements Bambu Studio listens for), with their name, model and serial number.
# - Adding: Klipper needs nothing else; Bambu needs the access code from the printer's screen,
#   which can't be read over the network; OctoPrint is approved by clicking "Allow" in OctoPrint
#   (its Application Keys plugin), so no API key needs copying.
# - Never added silently, except Klipper printers when the owner turns that on in Settings: on a
#   shared network (a makerspace, an apartment) the scan also finds other people's printers.
import json, re, socket, threading, time, urllib.error, urllib.parse, urllib.request
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import network, settings

router=APIRouter(prefix='/api/discovery')
SCAN_EVERY=24*3600; FIRST_SCAN_DELAY=90; ANNOUNCE_PORT=2021
_db=None; _add=None; _printers=None
_octo={}   # key -> pending OctoPrint approval: {'poll': url, 'name': ..., 'started': ...}
_lock=threading.Lock()
# Bambu's model codes, as sent in their announcements
BAMBU_MODELS={'3DPrinter-X1-Carbon':'X1 Carbon','3DPrinter-X1':'X1','BL-P001':'X1 Carbon','BL-P002':'X1','C13':'X1E',
 'C11':'P1P','C12':'P1S','N7':'P2S','N1':'A1 mini','N2S':'A1','O1D':'H2D','O1S':'H2S'}

def configure(db,add_printer,printer_rows):
 global _db,_add,_printers
 _db,_add,_printers=db,add_printer,printer_rows
 c=_db(); c.execute('''CREATE TABLE IF NOT EXISTS discovered_printers(key TEXT PRIMARY KEY,type TEXT NOT NULL,host TEXT NOT NULL,
  port INTEGER,serial TEXT,name TEXT,model TEXT,first_seen REAL NOT NULL,last_seen REAL NOT NULL,dismissed INTEGER NOT NULL DEFAULT 0)''')
 c.commit(); c.close()
 network.after_scan.append(record_scan)
 if settings.as_service():
  threading.Thread(target=_loop,daemon=True,name='printer-discovery').start()
  threading.Thread(target=_listen_bambu,daemon=True,name='bambu-announce').start()

# ---- Recording what was found ---------------------------------------------------------------
def key_for(kind,host,port=None,serial=None):
 return f'bambu:{serial}' if kind=='bambu' and serial else f'{kind}:{host}:{port}'

def remember(kind,host,port=None,serial=None,name=None,model=None):
 k=key_for(kind,host,port,serial); now=time.time()
 c=_db()
 # The same Bambu printer may first be seen by IP (scan) and later by serial (announcement)
 if kind=='bambu' and serial: c.execute("DELETE FROM discovered_printers WHERE key=? AND dismissed=0",(f'bambu:{host}:{port or 8883}',))
 c.execute('''INSERT INTO discovered_printers(key,type,host,port,serial,name,model,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?)
  ON CONFLICT(key) DO UPDATE SET host=excluded.host,port=COALESCE(excluded.port,port),serial=COALESCE(excluded.serial,serial),
  name=COALESCE(excluded.name,name),model=COALESCE(excluded.model,model),last_seen=excluded.last_seen''',
  (k,kind,host,port,serial,name,model,now,now))
 c.commit(); c.close()
 return k

def record_scan(results):
 for r in results or []:
  p=r.get('printer')
  if not p: continue
  remember(p['type'],p['host'],p.get('port'),p.get('serial'),name=r.get('hostname'))
 if settings.get('auto_add_klipper'): add_all_klipper()

def _host(url):
 return urllib.parse.urlparse(url if '://' in url else 'http://'+url).hostname

def suggestions():
 # Found, not dismissed, and not already on the dashboard (same address, or same Bambu serial)
 rows=_printers()
 hosts={_host(r['base_url']) for r in rows}; serials={(r['serial'] or '').upper() for r in rows if r['serial']}
 c=_db(); found=[dict(r) for r in c.execute('SELECT * FROM discovered_printers WHERE dismissed=0 ORDER BY first_seen')]; c.close()
 out=[]
 for f in found:
  if f['host'] in hosts or (f['serial'] and f['serial'].upper() in serials): continue
  f['label']={'moonraker':'Klipper','bambu':'Bambu Lab','octoprint':'OctoPrint'}.get(f['type'],f['type'])
  f['suggested_name']=f['name'] or (f"Bambu Lab {f['model']}" if f['type']=='bambu' and f['model'] else f"{f['label']} printer")
  f['awaiting_approval']=f['key'] in _octo
  out.append(f)
 return out

# ---- Automatic scans -------------------------------------------------------------------------
_last={'scan':0.0}

def scan_now():
 if network.scan['running']: return False
 network.start_scan(); _last['scan']=time.time(); return True

def _loop():
 time.sleep(FIRST_SCAN_DELAY)
 while True:
  try:
   if settings.get('printer_discovery') and time.time()-_last['scan']>=SCAN_EVERY: scan_now()
  except Exception as e: print(f'[discovery] scan failed: {e}',flush=True)
  time.sleep(600)

def after_setup():
 # A brand-new owner's printers should be waiting by the time they reach the dashboard
 if settings.get('printer_discovery'): threading.Timer(2,scan_now).start()

# ---- Bambu announcements ---------------------------------------------------------------------
def parse_announcement(data):
 # Bambu printers send SSDP-style NOTIFY messages; only keep the ones from Bambu printers
 try: text=data.decode(errors='replace')
 except Exception: return None
 h={}
 for line in text.splitlines()[1:]:
  if ':' in line: k,v=line.split(':',1); h[k.strip().lower()]=v.strip()
 if 'bambulab' not in h.get('nt','').lower(): return None
 host=h.get('location','').replace('http://','').split('/')[0].split(':')[0]
 if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+',host): return None
 code=h.get('devmodel.bambu.com')
 return {'host':host,'serial':h.get('usn') or None,'name':h.get('devname.bambu.com') or None,'model':BAMBU_MODELS.get(code,code) if code else None}

def _listen_bambu():
 try:
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  s.bind(('',ANNOUNCE_PORT))
 except OSError as e:
  print(f'[discovery] not listening for Bambu announcements: {e}',flush=True); return
 seen={}
 while True:
  try:
   data,_=s.recvfrom(4096); a=parse_announcement(data)
   # Printers announce every few seconds; record each one at most once a minute
   if a and time.time()-seen.get(a['serial'] or a['host'],0)>60:
    seen[a['serial'] or a['host']]=time.time()
    remember('bambu',a['host'],8883,a['serial'],a['name'],a['model'])
  except Exception: time.sleep(5)

# ---- Adding ----------------------------------------------------------------------------------
def _find(key):
 c=_db(); r=c.execute('SELECT * FROM discovered_printers WHERE key=?',(key,)).fetchone(); c.close()
 if not r: raise HTTPException(404,'That printer is no longer in the list. Try scanning again.')
 return dict(r)

def _base(f):
 if f['type']=='bambu': return f"mqtts://{f['host']}:{f['port'] or 8883}"
 return f"{f['host']}:{f['port'] or 80}"

def add_found(key,name=None,access_code=None,api_key=None):
 f=_find(key)
 payload={'name':(name or '').strip() or f['name'] or ('Bambu Lab printer' if f['type']=='bambu' else 'Printer'),
  'printer_type':f['type'],'base_url':_base(f)}
 if f['type']=='bambu':
  code=(access_code or '').strip()
  if not re.fullmatch(r'[A-Za-z0-9]{8}',code): raise HTTPException(400,"Enter the printer's 8-character access code (on its screen, under the network or WLAN settings)")
  if not f['serial']: raise HTTPException(400,"This printer's serial number wasn't found. Add it with Print Farm → Add printer instead")
  payload.update(api_key=code,serial=f['serial'])
 elif f['type']=='octoprint':
  if not api_key: raise HTTPException(400,'OctoPrint printers are added through "Allow in OctoPrint"')
  payload['api_key']=api_key
 printer=_add(payload)
 return printer

def add_all_klipper():
 added=[]
 for f in suggestions():
  if f['type']=='moonraker':
   try: added.append(add_found(f['key']))
   except Exception as e: print(f"[discovery] couldn't add {f['host']}: {e}",flush=True)
 return added

# ---- OctoPrint approval (Application Keys) ---------------------------------------------------
def _octo_url(f,path): return f"http://{f['host']}:{f['port'] or 80}{path}"

def octoprint_request(key,name=None):
 f=_find(key)
 if f['type']!='octoprint': raise HTTPException(400,'Only OctoPrint printers use this')
 req=urllib.request.Request(_octo_url(f,'/plugin/appkeys/request'),data=json.dumps({'app':'LayerHound'}).encode(),
  headers={'Content-Type':'application/json'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=10) as r: poll=r.headers.get('Location')
 except urllib.error.HTTPError as e:
  raise HTTPException(502,"This OctoPrint doesn't support approving apps. Add it with an API key in Print Farm → Add printer" if e.code==404 else f"OctoPrint didn't accept the request ({e.code})")
 except Exception: raise HTTPException(502,"Couldn't reach OctoPrint. Check that it's on.")
 if not poll: raise HTTPException(502,"OctoPrint didn't return an approval link")
 with _lock: _octo[key]={'poll':poll if poll.startswith('http') else _octo_url(f,poll),'name':name,'started':time.time()}
 return {'status':'waiting'}

def octoprint_check(key):
 # 202: still waiting for someone to click Allow; 200: approved (with the key); 404: denied or expired
 with _lock: p=_octo.get(key)
 if not p: return {'status':'none'}
 try:
  with urllib.request.urlopen(p['poll'],timeout=10) as r:
   if r.status==202: return {'status':'waiting'}
   api_key=json.loads(r.read() or b'{}').get('api_key')
 except urllib.error.HTTPError as e:
  if e.code==404:
   with _lock: _octo.pop(key,None)
   return {'status':'denied'}
  return {'status':'waiting'}
 except Exception: return {'status':'waiting'}
 with _lock: _octo.pop(key,None)
 if not api_key: return {'status':'denied'}
 return {'status':'added','printer':add_found(key,p['name'],api_key=api_key)}

# ---- API -------------------------------------------------------------------------------------
@router.get('')
def list_found():
 return {'suggestions':suggestions(),'scanning':network.scan['running'],'last_scan':network.scan.get('finished'),
  'enabled':settings.get('printer_discovery')}

@router.post('/scan')
def scan():
 scan_now(); return list_found()

class AddFound(BaseModel):
 name:str|None=Field(default=None,max_length=80); access_code:str|None=Field(default=None,max_length=32)

@router.post('/add-klipper')
def add_klipper(): return {'added':len(add_all_klipper())}

@router.post('/{key}/add')
def add(key:str,b:AddFound): return {'printer':add_found(key,b.name,b.access_code)}

@router.post('/{key}/octoprint')
def octo_start(key:str,b:AddFound): return octoprint_request(key,b.name)

# A change (it adds the printer once approved), so admins only, like every POST
@router.post('/{key}/octoprint/check')
def octo_status(key:str): return octoprint_check(key)

@router.post('/{key}/dismiss')
def dismiss(key:str):
 c=_db(); n=c.execute('UPDATE discovered_printers SET dismissed=1 WHERE key=?',(key,)).rowcount; c.commit(); c.close()
 if not n: raise HTTPException(404,'Not found')
 return {'status':'dismissed'}
