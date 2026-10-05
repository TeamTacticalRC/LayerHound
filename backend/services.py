# Services page: health checks + quick-launch links, Home Assistant / Pi-hole stats, Docker containers.
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import http.client, json, os, re, socket, ssl, threading, time, urllib.error, urllib.parse, urllib.request
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import network, vault

router=APIRouter(prefix='/api/services')
CHECK_EVERY=60; STATS_EVERY=300; DOCKER_TTL=15
INTEGRATIONS=('none','homeassistant','pihole')
_db=None; state={}; stats={}; lock=threading.Lock()
# Home lab services often use self-signed certificates; a health check shouldn't fail on that
# Home-lab apps often use self-signed certificates, so they can't be verified; still require modern TLS
INSECURE=ssl.create_default_context(); INSECURE.minimum_version=ssl.TLSVersion.TLSv1_2; INSECURE.check_hostname=False; INSECURE.verify_mode=ssl.CERT_NONE

def configure(db):
 global _db; _db=db
 c=_db(); c.execute("CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,url TEXT NOT NULL,integration TEXT NOT NULL DEFAULT 'none',token TEXT,sort_order INTEGER,created_at TEXT NOT NULL)")
 c.commit(); c.close()
 threading.Thread(target=checker,daemon=True,name='layerhound-services').start()

def now(): return datetime.now(timezone.utc).isoformat()
def rows():
 c=_db(); r=[dict(x) for x in c.execute('SELECT * FROM services ORDER BY sort_order,id')]; c.close(); return r
def public(s):
 # Never send tokens/passwords back to the browser
 return {k:v for k,v in s.items() if k!='token'}|{'has_token':bool(s.get('token'))}

# ---- Health checks ----------------------------------------------------------------------
def parse_target(url):
 # "http(s)://..." is a web check; "host:port" is a plain TCP port check
 if re.match(r'^https?://',url,re.I): return 'web',url
 m=re.fullmatch(r'([A-Za-z0-9.\-]+):(\d{1,5})',url.strip())
 if m: return 'tcp',(m.group(1),int(m.group(2)))
 return 'web','http://'+url.strip()

def check(s):
 kind,target=parse_target(s['url'])
 if kind=='tcp': ms=network.tcp(*target,timeout=3); return ms,None if ms is not None else 'Port not answering'
 t=time.perf_counter()
 try:
  req=urllib.request.Request(target,headers={'User-Agent':'LayerHound/health-check'})
  with urllib.request.urlopen(req,timeout=5,context=INSECURE) as r: code=r.status
 except urllib.error.HTTPError as e: code=e.code
 except Exception as e: return None,short_error(e)
 ms=round((time.perf_counter()-t)*1000,1)
 # Any answer below 500 means the service is running (401/403 just means it wants a login)
 return (ms,None) if code<500 else (None,f'Server error ({code})')

def short_error(e):
 r=getattr(e,'reason',e)
 if isinstance(r,socket.timeout) or 'timed out' in str(r): return 'Timed out'
 if isinstance(r,ConnectionRefusedError) or 'refused' in str(r).lower(): return 'Connection refused'
 if isinstance(r,socket.gaierror): return "Couldn't find that address"
 return str(r)[:120]

def check_all():
 svcs=rows()
 if not svcs: return
 with ThreadPoolExecutor(max_workers=min(16,len(svcs))) as ex: results=list(ex.map(check,svcs))
 t=time.time()
 with lock:
  for s,(ms,err) in zip(svcs,results): state[s['id']]={'up':ms is not None,'ms':ms,'error':err,'checked_at':t}
 network.record([(f"service:{s['id']}",ms) for s,(ms,_) in zip(svcs,results)])

def checker():
 last_stats=0
 while True:
  try:
   check_all()
   if time.time()-last_stats>=STATS_EVERY: refresh_stats(); last_stats=time.time()
  except Exception as e: print('services check error:',e,flush=True)
  time.sleep(CHECK_EVERY)

def check_soon(s):
 def run():
  ms,err=check(s)
  with lock: state[s['id']]={'up':ms is not None,'ms':ms,'error':err,'checked_at':time.time()}
  if s['integration']!='none': stats[s['id']]=integration_stats(s)
 threading.Thread(target=run,daemon=True).start()

# ---- Home Assistant / Pi-hole -----------------------------------------------------------
def origin(url):
 kind,target=parse_target(url)
 if kind=='tcp': return f'http://{target[0]}:{target[1]}'
 u=urllib.parse.urlsplit(target); return f'{u.scheme}://{u.netloc}'

def get_json(url,headers=None,data=None,method=None):
 req=urllib.request.Request(url,headers={'Content-Type':'application/json',**(headers or {})},data=json.dumps(data).encode() if data is not None else None,method=method)
 with urllib.request.urlopen(req,timeout=8,context=INSECURE) as r: return json.loads(r.read().decode() or 'null')

def home_assistant(s):
 # Uses a long-lived access token (Home Assistant: Profile -> Security -> Long-lived access tokens)
 base=origin(s['url']); h={'Authorization':f"Bearer {vault.decrypt(s['token'])}"}
 cfg=get_json(base+'/api/config',h); ents=get_json(base+'/api/states',h)
 bad=[e for e in ents if e.get('state') in ('unavailable','unknown')]
 return {'version':cfg.get('version'),'location':cfg.get('location_name'),'entities':len(ents),'unavailable':len(bad)}

_pihole_sid={}
def pihole(s):
 base=origin(s['url'])
 # Pi-hole v6: session login, reused until it expires (Pi-hole limits concurrent sessions)
 try:
  sid=_pihole_sid.get(s['id'])
  def summary(sid): return get_json(base+'/api/stats/summary',{'X-FTL-SID':sid} if sid else {})
  try: d=summary(sid)
  except urllib.error.HTTPError as e:
   if e.code!=401: raise
   auth=get_json(base+'/api/auth',data={'password':vault.decrypt(s['token']) or ''},method='POST')
   sid=(auth.get('session') or {}).get('sid'); _pihole_sid[s['id']]=sid; d=summary(sid)
  q=d.get('queries') or {}
  return {'api':'v6','queries_today':q.get('total'),'blocked_today':q.get('blocked'),'percent_blocked':round(q.get('percent_blocked') or 0,1),'blocklist':(d.get('gravity') or {}).get('domains_being_blocked')}
 except urllib.error.HTTPError as e:
  if e.code not in (404,405): raise
 # Pi-hole v5: API token from Settings -> API
 d=get_json(f"{base}/admin/api.php?summaryRaw&auth={urllib.parse.quote(vault.decrypt(s['token']) or '')}")
 if not isinstance(d,dict) or 'dns_queries_today' not in d: raise ValueError('Pi-hole did not accept the API token')
 return {'api':'v5','queries_today':d.get('dns_queries_today'),'blocked_today':d.get('ads_blocked_today'),'percent_blocked':round(float(d.get('ads_percentage_today') or 0),1),'blocklist':d.get('domains_being_blocked'),'enabled':d.get('status')=='enabled'}

def integration_stats(s):
 try:
  data=home_assistant(s) if s['integration']=='homeassistant' else pihole(s)
  return {'ok':True,'data':data,'at':time.time()}
 except urllib.error.HTTPError as e:
  return {'ok':False,'error':'The token was rejected' if e.code in (401,403) else f'API error ({e.code})','at':time.time()}
 except Exception as e: return {'ok':False,'error':short_error(e),'at':time.time()}

def refresh_stats():
 for s in rows():
  if s['integration']!='none': stats[s['id']]=integration_stats(s)

# ---- Docker -----------------------------------------------------------------------------
DOCKER_SOCKS=[os.environ.get('LAYERHOUND_DOCKER_SOCK') or os.environ.get('TTRC_DOCKER_SOCK'),'/var/run/docker.sock',str(Path.home()/'.docker/run/docker.sock')]
class UnixHTTP(http.client.HTTPConnection):
 def __init__(s,path): super().__init__('localhost',timeout=10); s.path=path
 def connect(s): s.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.sock.settimeout(10); s.sock.connect(s.path)

def docker_sock(): return next((p for p in DOCKER_SOCKS if p and os.path.exists(p)),None)
def docker(method,path):
 sock=docker_sock()
 if not sock: raise FileNotFoundError('Docker is not installed on this server')
 c=UnixHTTP(sock)
 try:
  c.request(method,path); r=c.getresponse(); body=r.read()
  if r.status>=400: raise RuntimeError(f'Docker error {r.status}: {body[:200].decode(errors="replace")}')
  return json.loads(body) if body else None
 finally: c.close()

def container_stats(cid):
 try: st=docker('GET',f'/containers/{cid}/stats?stream=false')
 except Exception: return None,None
 cpu=st.get('cpu_stats') or {}; pre=st.get('precpu_stats') or {}
 cd=(cpu.get('cpu_usage') or {}).get('total_usage',0)-(pre.get('cpu_usage') or {}).get('total_usage',0)
 sd=cpu.get('system_cpu_usage',0)-pre.get('system_cpu_usage',0); n=cpu.get('online_cpus') or 1
 mem=st.get('memory_stats') or {}; ms=mem.get('stats') or {}
 # Match `docker stats`: leave out reclaimable file cache
 used=(mem.get('usage') or 0)-(ms.get('inactive_file') or ms.get('total_inactive_file') or 0)
 return (round(cd/sd*n*100,1) if sd>0 and cd>=0 else 0.0),max(0,used)

_docker_cache={'at':0,'data':None}
def docker_info():
 if time.time()-_docker_cache['at']<DOCKER_TTL and _docker_cache['data']: return _docker_cache['data']
 try:
  cs=docker('GET','/containers/json?all=1')
  running=[c for c in cs if c.get('State')=='running']
  with ThreadPoolExecutor(max_workers=8) as ex: st=dict(zip([c['Id'] for c in running],ex.map(container_stats,[c['Id'] for c in running])))
  out=[{'id':c['Id'][:12],'name':(c.get('Names') or ['?'])[0].lstrip('/'),'image':c.get('Image'),'state':c.get('State'),'status':c.get('Status'),
   'cpu_percent':(st.get(c['Id']) or (None,None))[0],'memory_bytes':(st.get(c['Id']) or (None,None))[1],
   'ports':sorted({p['PublicPort'] for p in c.get('Ports') or [] if p.get('PublicPort')})} for c in cs]
  data={'available':True,'containers':sorted(out,key=lambda x:(x['state']!='running',x['name']))}
 # installed=False hides the Docker section; Docker that's there but unreachable still shows, with the reason
 except FileNotFoundError: data={'available':False,'installed':False,'reason':'Docker is not installed on this server'}
 except PermissionError: data={'available':False,'installed':True,'reason':"LayerHound doesn't have permission to use Docker. See \"Docker containers\" in the README"}
 except Exception as e:
  print(f'[docker] {type(e).__name__}: {e}',flush=True)
  data={'available':False,'installed':True,'reason':"Docker is installed but isn't answering. See the service log"}
 _docker_cache.update(at=time.time(),data=data); return data

# ---- API --------------------------------------------------------------------------------
_count_cache={'at':0,'data':None}
def docker_counts():
 # Quick container count for the dashboard card (no per-container stats, which are slow)
 if time.time()-_count_cache['at']<DOCKER_TTL and _count_cache['data']: return _count_cache['data']
 try:
  cs=docker('GET','/containers/json?all=1'); data={'available':True,'running':sum(c.get('State')=='running' for c in cs),'total':len(cs)}
 except Exception: data={'available':False,'running':0,'total':0}
 _count_cache.update(at=time.time(),data=data); return data

def summary():
 # Used by /api/system for the dashboard's Services card and alerts
 with lock: st=dict(state)
 return {'services':[{'name':s['name'],'up':st.get(s['id'],{}).get('up')} for s in rows()],'docker':docker_counts()}

@router.get('')
def services():
 with lock: st=dict(state)
 out=[public(s)|st.get(s['id'],{'up':None,'ms':None,'error':None,'checked_at':None})|{'check':parse_target(s['url'])[0],'open_url':origin(s['url']) if parse_target(s['url'])[0]=='tcp' else parse_target(s['url'])[1],
  'uptime_24h':network.uptime(f"service:{s['id']}",86400),'hours':network.hourly(f"service:{s['id']}"),'stats':stats.get(s['id'])} for s in rows()]
 return {'services':out,'docker':docker_info(),'check_every':CHECK_EVERY}

class ServiceIn(BaseModel):
 name:str=Field(min_length=1,max_length=80); url:str=Field(min_length=1,max_length=500); integration:str='none'; token:str|None=None

def validate(b):
 if b.integration not in INTEGRATIONS: raise HTTPException(400,'Invalid integration')
 url=b.url.strip()
 if not re.fullmatch(r"(https?://)?[A-Za-z0-9.\-]+(:\d{1,5})?(/[^\s]*)?",url,re.I): raise HTTPException(400,'Enter a web address (http://192.168.1.10:8123) or host:port')
 return url

@router.post('')
def add(b:ServiceIn):
 url=validate(b)
 if b.integration=='homeassistant' and not (b.token or '').strip(): raise HTTPException(400,'Home Assistant needs a long-lived access token')
 c=_db(); nxt=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM services').fetchone()[0]
 cur=c.execute('INSERT INTO services(name,url,integration,token,sort_order,created_at) VALUES(?,?,?,?,?,?)',(b.name.strip(),url,b.integration,vault.encrypt((b.token or '').strip()),nxt,now()))
 c.commit(); s=dict(c.execute('SELECT * FROM services WHERE id=?',(cur.lastrowid,)).fetchone()); c.close(); check_soon(s); return public(s)

@router.put('/{sid}')
def edit(sid:int,b:ServiceIn):
 url=validate(b); c=_db(); old=c.execute('SELECT * FROM services WHERE id=?',(sid,)).fetchone()
 if not old: c.close(); raise HTTPException(404,'Service not found')
 # Blank token keeps the saved one; switching to "none" clears it
 token=None if b.integration=='none' else (vault.encrypt((b.token or '').strip()) or old['token'])
 c.execute('UPDATE services SET name=?,url=?,integration=?,token=? WHERE id=?',(b.name.strip(),url,b.integration,token,sid)); c.commit()
 s=dict(c.execute('SELECT * FROM services WHERE id=?',(sid,)).fetchone()); c.close()
 _pihole_sid.pop(sid,None); stats.pop(sid,None); check_soon(s); return public(s)

@router.delete('/{sid}')
def remove(sid:int):
 c=_db(); cur=c.execute('DELETE FROM services WHERE id=?',(sid,)); c.execute('DELETE FROM net_checks WHERE target=?',(f'service:{sid}',)); c.commit(); c.close()
 if not cur.rowcount: raise HTTPException(404,'Service not found')
 with lock: state.pop(sid,None)
 stats.pop(sid,None); _pihole_sid.pop(sid,None); return {'status':'deleted','id':sid}

@router.post('/docker/{cid}/restart')
def restart(cid:str):
 if not re.fullmatch(r'[0-9a-f]{12,64}',cid): raise HTTPException(400,'Invalid container id')
 try: docker('POST',f'/containers/{cid}/restart?t=10')
 except FileNotFoundError: raise HTTPException(404,'Docker is not installed on this server')
 except Exception as e:
  print(f'[docker] restart {cid}: {type(e).__name__}: {e}',flush=True)
  raise HTTPException(502,"Docker couldn't restart that container. See the service log.")
 _docker_cache['at']=0; _count_cache['at']=0; return {'status':'restarted','id':cid}
