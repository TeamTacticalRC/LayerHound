# Network page: internet health, device monitor, interfaces/traffic, and device discovery.
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import ipaddress, json, os, re, socket, ssl, subprocess, sys, threading, time, urllib.request
import psutil
import settings
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router=APIRouter(prefix='/api/network')
CHECK_EVERY=60; IFACE_EVERY=5
INTERNET_TARGETS=('1.1.1.1','8.8.8.8'); DNS_NAME='one.one.one.one'
# IEEE manufacturer list (setup.sh downloads it); optional, discovery works without it
OUI_PATH=Path(__file__).with_name('data')/'oui.csv'
KINDS=('router','printer','computer','server','nas','camera','phone','other')
MAC=sys.platform=='darwin'
_db=None; state={'internet':{},'devices':{},'public_ip':None,'public_ip_at':0}
lock=threading.Lock()

def configure(db):
 global _db; _db=db
 c=_db()
 c.execute("CREATE TABLE IF NOT EXISTS net_devices(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,host TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'other',port INTEGER,sort_order INTEGER,created_at TEXT NOT NULL)")
 c.execute('CREATE TABLE IF NOT EXISTS net_checks(t INTEGER NOT NULL,target TEXT NOT NULL,up INTEGER NOT NULL,ms REAL)')
 c.execute('CREATE INDEX IF NOT EXISTS net_checks_target_t ON net_checks(target,t)')
 c.execute('CREATE TABLE IF NOT EXISTS net_daily(day TEXT NOT NULL,iface TEXT NOT NULL,rx INTEGER NOT NULL DEFAULT 0,tx INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(day,iface))')
 # First run: start the device monitor with the router so the list isn't empty
 if not c.execute('SELECT COUNT(*) FROM net_devices').fetchone()[0] and not c.execute("SELECT 1 FROM sqlite_master WHERE name='net_seeded'").fetchone():
  gw=gateway()
  if gw: c.execute('INSERT INTO net_devices(name,host,kind,sort_order,created_at) VALUES(?,?,?,?,?)',('Router',gw,'router',1,now()))
  c.execute('CREATE TABLE net_seeded(x)')
 c.commit(); c.close()
 threading.Thread(target=checker,daemon=True,name='layerhound-net-checker').start()
 threading.Thread(target=iface_sampler,daemon=True,name='layerhound-net-ifaces').start()

def now(): return datetime.now(timezone.utc).isoformat()

# ---- Probes -----------------------------------------------------------------------------
def ping(host,timeout=1.0):
 # The system ping is allowed to send ICMP without root on both macOS and Linux
 # macOS takes -W in milliseconds, Linux in whole seconds
 cmd=['ping','-c','1','-W',str(int(timeout*1000)),host] if MAC else ['ping','-c','1','-n','-W',str(max(1,round(timeout))),host]
 try: out=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout+2).stdout
 except Exception: return None
 m=re.search(r'time[=<]([\d.]+)',out); return round(float(m.group(1)),1) if m else None

def tcp(host,port,timeout=1.0):
 t=time.perf_counter()
 try:
  with socket.create_connection((host,port),timeout=timeout): return round((time.perf_counter()-t)*1000,1)
 except OSError: return None

def check_device(d):
 # Devices that block ping (some PCs, cameras) can be checked on a TCP port instead
 return tcp(d['host'],d['port']) if d['port'] else ping(d['host'])

def gateway():
 try:
  if MAC:
   out=subprocess.run(['route','-n','get','default'],capture_output=True,text=True,timeout=3).stdout
   m=re.search(r'gateway:\s*(\S+)',out)
  else:
   out=subprocess.run(['ip','route','show','default'],capture_output=True,text=True,timeout=3).stdout
   m=re.search(r'default via (\S+)',out)
  return m.group(1) if m else None
 except Exception: return None

def public_ip():
 # Cloudflare's trace page (same provider as the 1.1.1.1 check); refreshed every 15 minutes
 if time.time()-state['public_ip_at']<900 and state['public_ip']: return state['public_ip']
 try:
  with urllib.request.urlopen('https://1.1.1.1/cdn-cgi/trace',timeout=4) as r:
   m=re.search(r'^ip=(\S+)$',r.read().decode(),re.M); state['public_ip']=m.group(1) if m else None
 except Exception: pass
 state['public_ip_at']=time.time(); return state['public_ip']

def dns_ms():
 t=time.perf_counter()
 try: socket.getaddrinfo(DNS_NAME,443); return round((time.perf_counter()-t)*1000,1)
 except OSError: return None

# ---- Background checks ------------------------------------------------------------------
def devices():
 c=_db(); rows=[dict(r) for r in c.execute('SELECT * FROM net_devices ORDER BY sort_order,id')]; c.close(); return rows

def record(rows):
 t=int(time.time()); c=_db()
 c.executemany('INSERT INTO net_checks(t,target,up,ms) VALUES(?,?,?,?)',[(t,target,int(ms is not None),ms) for target,ms in rows])
 c.execute('DELETE FROM net_checks WHERE t<?',(t-settings.get('network_history_days')*86400,)); c.commit(); c.close()

def check_all():
 devs=devices()
 with ThreadPoolExecutor(max_workers=max(4,len(devs)+3)) as ex:
  inet=list(ex.map(ping,INTERNET_TARGETS)); results=list(ex.map(check_device,devs)); dns=dns_ms()
 ok=[m for m in inet if m is not None]
 # Internet counts as up if either target answers; DNS is reported separately
 internet=min(ok) if ok else None; t=time.time()
 with lock:
  state['internet']={'up':internet is not None,'ms':internet,'dns_ms':dns,'dns_ok':dns is not None,'checked_at':t}
  state['devices']={d['id']:{'up':ms is not None,'ms':ms,'checked_at':t} for d,ms in zip(devs,results)}
 record([('internet',internet),('dns',dns)]+[(f"device:{d['id']}",ms) for d,ms in zip(devs,results)])
 if internet is not None: public_ip()

def checker():
 while True:
  try: check_all()
  except Exception as e: print('network check error:',e,flush=True)
  time.sleep(CHECK_EVERY)

def check_one_soon(d):
 def run():
  ms=check_device(d)
  with lock: state['devices'][d['id']]={'up':ms is not None,'ms':ms,'checked_at':time.time()}
 threading.Thread(target=run,daemon=True).start()

# ---- Interfaces -------------------------------------------------------------------------
SKIP_IFACES=('lo','utun','awdl','llw','anpi','gif','stf','bridge','ap','docker','veth','br-','tun','tap','wg','tailscale','zt')
IFACE_HISTORY={}; iface_rates={}
_hw_ports={'at':0,'map':{}}
def iface_type(name):
 if MAC:
  if time.time()-_hw_ports['at']>600:
   try:
    out=subprocess.run(['networksetup','-listallhardwareports'],capture_output=True,text=True,timeout=3).stdout
    _hw_ports['map']={m.group(2):m.group(1) for m in re.finditer(r'Hardware Port: (.+)\nDevice: (\S+)',out)}
   except Exception: pass
   _hw_ports['at']=time.time()
  port=_hw_ports['map'].get(name,'')
  return 'Wi-Fi' if 'Wi-Fi' in port else 'Ethernet' if 'Ethernet' in port or 'Thunderbolt' in port else (port or 'Network')
 if Path(f'/sys/class/net/{name}/wireless').exists(): return 'Wi-Fi'
 return 'Ethernet' if name.startswith(('eth','en')) else 'Network'

def visible_ifaces():
 stats=psutil.net_if_stats(); addrs=psutil.net_if_addrs(); counters=psutil.net_io_counters(pernic=True); out=[]
 for name,st in stats.items():
  if name.startswith(SKIP_IFACES) or not st.isup: continue
  a=addrs.get(name,[]); ipv4=next((x for x in a if x.family==socket.AF_INET),None)
  c=counters.get(name)
  if not ipv4 and not (c and c.bytes_recv+c.bytes_sent): continue
  mac=next((x.address for x in a if x.family==psutil.AF_LINK),None)
  out.append({'name':name,'type':iface_type(name),'ipv4':ipv4.address if ipv4 else None,'netmask':ipv4.netmask if ipv4 else None,'mac':mac,'speed_mbps':st.speed or None,'mtu':st.mtu})
 return out

def iface_sampler():
 prev=psutil.net_io_counters(pernic=True); t0=time.time(); pending={}; flushed=time.time()
 while True:
  time.sleep(IFACE_EVERY)
  try:
   cur=psutil.net_io_counters(pernic=True); t=time.time(); dt=max(t-t0,1e-6)
   for name,c in cur.items():
    p=prev.get(name)
    if not p or name.startswith(SKIP_IFACES): continue
    # Counters reset when an interface restarts; skip that sample instead of going negative
    drx=c.bytes_recv-p.bytes_recv; dtx=c.bytes_sent-p.bytes_sent
    if drx<0 or dtx<0: continue
    iface_rates[name]={'rx_bps':drx/dt,'tx_bps':dtx/dt}
    IFACE_HISTORY.setdefault(name,deque(maxlen=3600//IFACE_EVERY)).append({'t':round(t),'rx':round(drx/dt),'tx':round(dtx/dt)})
    acc=pending.setdefault(name,[0,0]); acc[0]+=drx; acc[1]+=dtx
   prev,t0=cur,t
   if t-flushed>=60 and pending:
    day=datetime.now().strftime('%Y-%m-%d'); c=_db()
    c.executemany('INSERT INTO net_daily(day,iface,rx,tx) VALUES(?,?,?,?) ON CONFLICT(day,iface) DO UPDATE SET rx=rx+excluded.rx,tx=tx+excluded.tx',[(day,n,v[0],v[1]) for n,v in pending.items() if v[0] or v[1]])
    c.execute("DELETE FROM net_daily WHERE day<date('now',?)",(f"-{settings.get('data_usage_days')} day",)); c.commit(); c.close(); pending={}; flushed=t
  except Exception as e: print('interface sampler error:',e,flush=True)

# ---- Summaries --------------------------------------------------------------------------
def hourly(target,hours=24):
 # Share of successful checks per hour, oldest first; None where there was no data
 t=int(time.time()); start=t-hours*3600; c=_db()
 rows=c.execute('SELECT (t-?)/3600 AS h,AVG(up) AS a FROM net_checks WHERE target=? AND t>=? GROUP BY h',(start,target,start)).fetchall(); c.close()
 by={int(r['h']):round(r['a'],3) for r in rows}; return [by.get(i) for i in range(hours)]

def uptime(target,seconds):
 c=_db(); r=c.execute('SELECT AVG(up) AS a,COUNT(*) AS n FROM net_checks WHERE target=? AND t>=?',(target,int(time.time())-seconds)).fetchone(); c.close()
 return round(r['a']*100,2) if r['n'] else None

def latency_history(target,hours=24):
 c=_db(); rows=c.execute('SELECT t,ms FROM net_checks WHERE target=? AND t>=? ORDER BY t',(target,int(time.time())-hours*3600)).fetchall(); c.close()
 return [{'t':r['t'],'ms':r['ms']} for r in rows]

def outages(target='internet'):
 c=_db(); rows=c.execute('SELECT t,up FROM net_checks WHERE target=? ORDER BY t',(target,)).fetchall(); c.close()
 out=[]; start=None; last=None
 for r in rows:
  if not r['up'] and start is None: start=r['t']
  if r['up'] and start is not None: out.append({'start':start,'end':r['t'],'minutes':max(1,round((r['t']-start)/60))}); start=None
  last=r['t']
 if start is not None: out.append({'start':start,'end':None,'minutes':max(1,round((last-start)/60))})
 return list(reversed(out))[:20]

def alerts():
 # Used by /api/system so the dashboard's alert list includes network problems
 with lock: inet=dict(state['internet']); st=dict(state['devices'])
 return {'internet_up':inet.get('up'),'offline_devices':[d['name'] for d in devices() if st.get(d['id'],{}).get('up') is False]}

@router.get('')
def network():
 with lock: inet=dict(state['internet']); st=dict(state['devices'])
 today=datetime.now().strftime('%Y-%m-%d'); c=_db(); daily={r['iface']:(r['rx'],r['tx']) for r in c.execute('SELECT iface,rx,tx FROM net_daily WHERE day=?',(today,))}; c.close()
 ifaces=[{**i,**{k:round(v) for k,v in iface_rates.get(i['name'],{'rx_bps':0,'tx_bps':0}).items()},'today_rx':daily.get(i['name'],(0,0))[0],'today_tx':daily.get(i['name'],(0,0))[1],'history':list(IFACE_HISTORY.get(i['name'],[]))} for i in visible_ifaces()]
 devs=[{**d,**st.get(d['id'],{'up':None,'ms':None,'checked_at':None}),'uptime_24h':uptime(f"device:{d['id']}",86400),'hours':hourly(f"device:{d['id']}")} for d in devices()]
 return {'internet':{**inet,'public_ip':state['public_ip'],'uptime_24h':uptime('internet',86400),'uptime_7d':uptime('internet',7*86400),'hours':hourly('internet'),'history':latency_history('internet'),'outages':outages()},
  'devices':devs,'interfaces':ifaces,'gateway':gateway(),'check_every':CHECK_EVERY}

# ---- Device monitor CRUD ----------------------------------------------------------------
class DeviceIn(BaseModel):
 name:str=Field(min_length=1,max_length=80); host:str=Field(min_length=1,max_length=255); kind:str='other'; port:int|None=Field(default=None,ge=1,le=65535)

def clean_host(h):
 h=h.strip().removeprefix('http://').removeprefix('https://').split('/')[0]
 if not re.fullmatch(r'[A-Za-z0-9.\-:]+',h): raise HTTPException(400,'Enter an IP address or hostname')
 return h

@router.post('/devices')
def add_device(d:DeviceIn):
 if d.kind not in KINDS: raise HTTPException(400,'Invalid device type')
 c=_db(); nxt=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM net_devices').fetchone()[0]
 cur=c.execute('INSERT INTO net_devices(name,host,kind,port,sort_order,created_at) VALUES(?,?,?,?,?,?)',(d.name.strip(),clean_host(d.host),d.kind,d.port,nxt,now()))
 c.commit(); row=dict(c.execute('SELECT * FROM net_devices WHERE id=?',(cur.lastrowid,)).fetchone()); c.close(); check_one_soon(row); return row

@router.put('/devices/{did}')
def edit_device(did:int,d:DeviceIn):
 if d.kind not in KINDS: raise HTTPException(400,'Invalid device type')
 c=_db(); cur=c.execute('UPDATE net_devices SET name=?,host=?,kind=?,port=? WHERE id=?',(d.name.strip(),clean_host(d.host),d.kind,d.port,did)); c.commit()
 row=c.execute('SELECT * FROM net_devices WHERE id=?',(did,)).fetchone(); c.close()
 if not cur.rowcount: raise HTTPException(404,'Device not found')
 row=dict(row); check_one_soon(row); return row

@router.delete('/devices/{did}')
def delete_device(did:int):
 c=_db(); cur=c.execute('DELETE FROM net_devices WHERE id=?',(did,)); c.execute('DELETE FROM net_checks WHERE target=?',(f'device:{did}',)); c.commit(); c.close()
 if not cur.rowcount: raise HTTPException(404,'Device not found')
 with lock: state['devices'].pop(did,None)
 return {'status':'deleted','id':did}

# ---- Discovery --------------------------------------------------------------------------
scan={'running':False,'progress':0,'started':None,'finished':None,'results':[],'subnet':None,'error':None}
_oui={'loaded':False,'map':{}}
def vendor(mac):
 if not mac: return None
 if int(mac.split(':')[0],16)&2: return 'Private (randomized) address'
 if not _oui['loaded']:
  _oui['loaded']=True
  try:
   import csv
   with open(OUI_PATH,newline='',encoding='utf-8',errors='replace') as f:
    for row in csv.reader(f):
     if len(row)>=3 and len(row[1])==6: _oui['map'][row[1].upper()]=row[2].strip()
  except OSError: pass
 return _oui['map'].get(mac.replace(':','')[:6].upper())

def norm_mac(m):
 # macOS prints "a4:f0:f:5e:9c:a8"; pad each part to two digits
 parts=m.split(':'); return ':'.join(p.zfill(2) for p in parts).lower() if len(parts)==6 else None

def neighbors():
 out={}
 try:
  if MAC:
   for m in re.finditer(r'\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)',subprocess.run(['arp','-an'],capture_output=True,text=True,timeout=5).stdout): out[m.group(1)]=norm_mac(m.group(2))
  else:
   for m in re.finditer(r'^(\d+\.\d+\.\d+\.\d+) .*lladdr ([0-9a-fA-F:]+)',subprocess.run(['ip','neigh','show'],capture_output=True,text=True,timeout=5).stdout,re.M): out[m.group(1)]=norm_mac(m.group(2))
 except Exception: pass
 return out

def bambu_cert(host,port=8883):
 # Bambu printers use a certificate issued by "BBL" with the serial number as its subject name.
 # It's self-signed, so read the raw bytes and pull out the last common name (the subject's).
 try:
  ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
  with socket.create_connection((host,port),timeout=1.5) as s, ctx.wrap_socket(s) as t: der=t.getpeercert(binary_form=True)
  if b'BBL' not in der: return None
  found=None; i=der.find(b'\x06\x03\x55\x04\x03')
  while i!=-1:
   j=i+5; n=der[j+1]; found=der[j+2:j+2+n].decode(errors='replace'); i=der.find(b'\x06\x03\x55\x04\x03',j)
  return found or ''
 except Exception: return None

def http_json(url,timeout=1.5):
 try:
  with urllib.request.urlopen(url,timeout=timeout) as r: return json.loads(r.read().decode())
 except Exception: return None

def identify(ip):
 # Recognise the printer types the dashboard supports, and fill in what the Add printer form needs.
 # Klipper first: some Klipper printers (e.g. Snapmaker U1) also listen on Bambu's port 8883.
 for port in (7125,80):
  if tcp(ip,port,0.8) is None: continue
  info=http_json(f'http://{ip}:{port}/printer/info')
  if info and 'result' in info: return {'kind':'printer','label':'Klipper printer','hostname':info['result'].get('hostname'),'printer':{'type':'moonraker','host':ip,'port':port}}
 if tcp(ip,8883,0.8) is not None:
  serial=bambu_cert(ip)
  if serial is not None: return {'kind':'printer','label':'Bambu Lab printer','printer':{'type':'bambu','host':ip,'port':8883,'serial':serial or None}}
 for port in (80,5000):
  if tcp(ip,port,0.8) is None: continue
  try:
   with urllib.request.urlopen(f'http://{ip}:{port}/',timeout=1.5) as r: page=r.read(4000).decode(errors='replace')
   if 'OctoPrint' in page: return {'kind':'printer','label':'OctoPrint printer','printer':{'type':'octoprint','host':ip,'port':port}}
  except Exception: pass
 return {}

def scan_subnet():
 iface=next((i for i in visible_ifaces() if i['ipv4'] and i['netmask'] and not i['ipv4'].startswith('169.254.')),None)
 if not iface: raise RuntimeError('No network connection found to scan')
 net=ipaddress.ip_network(f"{iface['ipv4']}/{iface['netmask']}",strict=False)
 # Keep scans quick and polite: never more than a /24 around this machine
 if net.prefixlen<24: net=ipaddress.ip_network(f"{iface['ipv4']}/24",strict=False)
 return net,iface['ipv4']

def run_scan(known):
 try:
  net,me=scan_subnet(); hosts=[str(h) for h in net.hosts()]; scan.update(subnet=str(net)); done=[0]
  def probe(ip):
   ms=ping(ip,1.0); done[0]+=1; scan['progress']=round(done[0]/len(hosts)*80); return ip,ms
  with ThreadPoolExecutor(max_workers=64) as ex: alive={ip:ms for ip,ms in ex.map(probe,hosts) if ms is not None}
  arp=neighbors()
  # Devices that ignore ping but answered ARP still count as present
  for ip in arp:
   a=ipaddress.ip_address(ip)
   if a in net and a not in (net.network_address,net.broadcast_address) and arp[ip] and arp[ip]!='ff:ff:ff:ff:ff:ff' and ip not in alive and ip!=me: alive[ip]=None
  ips=sorted(alive,key=lambda x:ipaddress.ip_address(x)); scan['progress']=85
  def details(ip):
   try: name=socket.gethostbyaddr(ip)[0]
   except Exception: name=None
   ident=identify(ip) if ip!=me else {}
   mac=arp.get(ip)
   return {'ip':ip,'ms':alive[ip],'hostname':ident.get('hostname') or name,'mac':mac,'vendor':vendor(mac),'kind':ident.get('kind'),'label':ident.get('label') or ('This server' if ip==me else 'Router' if ip==gateway() else None),'printer':ident.get('printer'),'known':known.get(ip)}
  with ThreadPoolExecutor(max_workers=24) as ex: scan['results']=list(ex.map(details,ips))
  scan['progress']=100
 except Exception as e: scan['error']=str(e)
 finally: scan.update(running=False,finished=now())

def known_hosts():
 # IPs already on the dashboard, so scan results can say "On dashboard"
 c=_db(); known={}
 for r in c.execute('SELECT name,base_url FROM printers'):
  h=re.sub(r'^[a-z]+://','',r['base_url']).split('/')[0].split(':')[0]; known[h]=f"Printer: {r['name']}"
 for r in c.execute('SELECT name,host FROM net_devices'): known.setdefault(r['host'],f"Monitored: {r['name']}")
 c.close(); return known

@router.post('/scan')
def start_scan():
 if scan['running']: return scan
 known=known_hosts()
 scan.update(running=True,progress=0,started=now(),finished=None,results=[],error=None)
 threading.Thread(target=run_scan,args=(known,),daemon=True,name='layerhound-net-scan').start(); return scan

@router.get('/scan')
def scan_status(): return scan
