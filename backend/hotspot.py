# Setup hotspot: when the board has no network, it creates its own open Wi-Fi network,
# "LayerHound-Setup". Joining it from a phone opens the setup page automatically (a captive
# portal): pick the home Wi-Fi, and on a new board also name the farm and create the admin account.
#
# - Starts after the board has been offline for a few minutes (sooner if it was never set up),
#   or on request with "layerhound hotspot start" on the board.
# - Shuts off once the board joins a network; the hotspot profile is deleted so it can't linger.
# - While on, it retries the saved Wi-Fi every few minutes (when no phone is connected),
#   so a router that was only rebooting doesn't leave the board stuck in setup mode.
# - setup.sh points all DNS on the hotspot at the board, which makes phones show the setup page.
import ipaddress, socket, subprocess, threading, time
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
import auth, settings, wifi

router=APIRouter(prefix='/api/hotspot')
SSID=CON='LayerHound-Setup'; GATEWAY='10.42.0.1'; SUBNET=ipaddress.ip_network('10.42.0.0/24')
CHECK_EVERY=15; OFFLINE_WAIT=180; FIRST_WAIT=45; RETRY_EVERY=300; MANUAL_LIMIT=30*60; JOIN_DELAY=3
REQUEST_FILE=Path(__file__).with_name('data')/'hotspot-request'
state={'active':False,'reason':None,'since':None,'networks':[],'last_error':None,'joining':None,'joined':None}
_lock=threading.Lock()

def on_hotspot(host):
 try: return ipaddress.ip_address(host or '') in SUBNET
 except ValueError: return False

# ---- Turning the hotspot on and off -------------------------------------------------------
def start(reason):
 dev=wifi.wifi_device()
 if not dev: return False
 # The radio can't scan for networks while it's running the hotspot, so scan first
 try: state['networks']=wifi.scan(rescan=True)
 except Exception: pass
 wifi.nmcli('connection','delete','id',CON)
 code,_,err=wifi.nmcli('connection','add','type','wifi','ifname',dev,'con-name',CON,'ssid',SSID,'autoconnect','no',
  '802-11-wireless.mode','ap','802-11-wireless.band','bg','ipv4.method','shared','ipv4.addresses',f'{GATEWAY}/24','ipv6.method','disabled')
 if code==0: code,_,err=wifi.nmcli('--wait','20','connection','up','id',CON,timeout=30)
 if code!=0:
  print(f'[hotspot] could not start: {err}',flush=True); wifi.nmcli('connection','delete','id',CON); return False
 state.update(active=True,reason=reason,since=time.time())
 print(f'[hotspot] started ({reason})',flush=True); return True

def stop():
 # Deleting the profile (not just turning it off) means it can never come back on by itself
 wifi.nmcli('connection','delete','id',CON)
 state.update(active=False,reason=None,since=None)
 print('[hotspot] stopped',flush=True)

def online():
 # Connected to a real network: Ethernet, or Wi-Fi other than our own hotspot
 return any(d['state']=='connected' and d['type'] in ('ethernet','wifi') and d['connection']!=CON for d in wifi.devices())

def clients():
 # Phones connected to the hotspot: neighbours on the Wi-Fi interface that have answered recently
 dev=wifi.wifi_device()
 try:
  out=subprocess.run(['ip','neigh','show','dev',dev],capture_output=True,text=True,timeout=5).stdout
  return sum(1 for l in out.splitlines() if any(s in l for s in ('REACHABLE','STALE','DELAY','PROBE')))
 except Exception: return 0

def take_request():
 # "layerhound hotspot start|stop" on the board leaves a note here for the service
 try: req=REQUEST_FILE.read_text().strip(); REQUEST_FILE.unlink()
 except FileNotFoundError: return None
 return req

# ---- Deciding when ------------------------------------------------------------------------
def tick(now,offline_since):
 # One check; returns the updated "offline since" time
 req=take_request()
 if req=='start' and not state['active']: start('manual'); return None
 if req=='stop' and state['active']: stop(); return None
 if state['joining']: return None
 if state['active']:
  r=state['reason']
  if r=='manual':
   if now-state['since']>MANUAL_LIMIT: stop()
   return None
  # Started because the board was offline: a cable plugged in means it's reachable again
  if any(d['type']=='ethernet' and d['state']=='connected' for d in wifi.devices()): stop(); return None
  if now-state['since']>RETRY_EVERY and wifi.saved_wifi()-{CON} and not clients():
   # Give the saved Wi-Fi a chance; NetworkManager reconnects on its own once the hotspot is off.
   # If that fails, the hotspot comes back about a minute later.
   stop(); return now-OFFLINE_WAIT+60
  return None
 devs=wifi.devices()
 # No answer from NetworkManager means we don't know; never start the hotspot on a guess
 if not devs or online(): return None
 if offline_since is None: return now
 wait=OFFLINE_WAIT if wifi.saved_wifi() or auth.has_users() else FIRST_WAIT
 if now-offline_since>=wait: start('offline'); return None
 return offline_since

def loop():
 offline_since=None
 while True:
  try:
   with _lock: offline_since=tick(time.time(),offline_since)
  except Exception as e: print(f'[hotspot] check failed: {e}',flush=True)
  time.sleep(CHECK_EVERY)

def configure():
 # Only on the board (running as the service, with Wi-Fi managed by NetworkManager)
 if not (settings.as_service() and wifi.available()): return
 wifi.nmcli('connection','delete','id',CON)   # left over from a crash or power cut
 threading.Thread(target=loop,daemon=True,name='hotspot').start()

# ---- Captive portal -----------------------------------------------------------------------
def local_name():
 # The board's name on the network, e.g. "layerhound.local" (some systems already include ".local")
 h=socket.gethostname().lower()
 return h if h.endswith('.local') else f'{h}.local'

def allowed_hosts():
 return {GATEWAY,socket.gethostname().lower(),local_name(),'localhost','127.0.0.1'}

async def middleware(request:Request,call_next):
 # While the hotspot is on, every web address resolves to the board for phones on it. Their requests
 # for other sites (like the checks phones make for internet access) get sent to the setup page,
 # which makes the phone pop it up automatically. Devices reaching the board another way are left alone.
 if state['active'] and on_hotspot(request.client.host if request.client else ''):
  host=(request.headers.get('host') or '').split(':')[0].lower()
  if host and host not in allowed_hosts(): return RedirectResponse(f'http://{GATEWAY}/',status_code=302)
 return await call_next(request)

# ---- API ----------------------------------------------------------------------------------
@router.get('')
def info(request:Request):
 # Only phones on the hotspot get the details (network list, last error)
 if not on_hotspot(request.client.host if request.client else ''): return {'active':state['active'],'on_hotspot':False}
 return {'active':state['active'],'on_hotspot':True,'networks':state['networks'],'last_error':state['last_error'],
  'joining':state['joining'],'hostname':local_name(),'setup_required':not auth.has_users()}

class Join(BaseModel):
 ssid:str=Field(min_length=1,max_length=64); password:str|None=Field(default=None,max_length=128)

def join(ssid,password):
 time.sleep(JOIN_DELAY)   # let the phone receive the answer before the hotspot goes away
 with _lock:
  dev=wifi.wifi_device(); wifi.nmcli('connection','down','id',CON)
  was_saved=ssid in wifi.saved_wifi()
  # A saved network with no new password reuses its saved settings (like the Network page does)
  args=(['connection','up','id',ssid] if was_saved and not password else ['device','wifi','connect',ssid,'ifname',dev]+(['password',password] if password else []))
  code,_,err=wifi.nmcli('--wait',str(wifi.CONNECT_WAIT),*args,timeout=wifi.CONNECT_WAIT+10)
  if code==0:
   wifi.nmcli('connection','modify','id',ssid,'802-11-wireless.powersave','2')
   wifi.nmcli('connection','delete','id',CON)
   state.update(active=False,reason=None,since=None,joining=None,last_error=None,joined=ssid)
   print(f'[hotspot] joined {ssid}',flush=True); return
  if not was_saved: wifi.nmcli('connection','delete','id',ssid)
  state.update(joining=None,last_error=f"Couldn't join {ssid}: {wifi.friendly(err)}.")
  print(f'[hotspot] joining {ssid} failed: {err}',flush=True)
  # Bring the hotspot back so the phone can try again
  wifi.nmcli('--wait','20','connection','up','id',CON,timeout=30)

@router.post('/connect')
def connect(b:Join,request:Request):
 # On a new board anyone on the hotspot may do this (it's the first-run setup);
 # once accounts exist, only a signed-in admin can change the board's Wi-Fi
 if not state['active']: raise HTTPException(409,'The setup hotspot is not on')
 if auth.has_users():
  who=auth.principal(request)
  if not who or who['role']!='admin': raise HTTPException(403,'Sign in as an admin to change Wi-Fi')
 elif not on_hotspot(request.client.host if request.client else ''): raise HTTPException(403,'Connect to LayerHound-Setup to do this')
 if state['joining']: raise HTTPException(409,'Already joining a network')
 ssid=b.ssid.strip(); state.update(joining=ssid,last_error=None)
 threading.Thread(target=join,args=(ssid,b.password or None),daemon=True).start()
 return {'status':'joining','network':ssid,'hostname':local_name()}
