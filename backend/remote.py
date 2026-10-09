# Remote access with Tailscale: reach the dashboard from anywhere, without opening it to the internet.
#
# - The board setup (deploy/setup.sh) installs Tailscale and makes LayerHound's user its
#   "operator", so LayerHound can connect and disconnect it without root. Tailscale does nothing
#   until the owner connects it here.
# - Connect: runs "tailscale up" and shows Tailscale's own sign-in link (and a QR code). The
#   owner signs in with their own Tailscale account; LayerHound never sees their password.
# - Once connected, Settings shows the board's address on the owner's private Tailscale network
#   (e.g. http://layerhound.example-tail.ts.net). Their phone needs the Tailscale app, signed in to
#   the same account.
# - Tailscale's DNS settings are left off, so the board keeps using the local network's DNS
#   (and .local names) exactly as before.
import getpass, json, os, socket, subprocess, threading, time
import segno
from fastapi import APIRouter, HTTPException
import settings

router=APIRouter(prefix='/api/remote')
TAILSCALE='tailscale'
UP_TIMEOUT=15*60   # stop waiting for the owner to finish signing in after this long
_up=None; _up_started=0; _lock=threading.Lock()

def available():
 # Board installs only: Docker and development machines manage their own networking
 return settings.as_service() and not settings.in_docker()

def run(*args,timeout=20):
 return subprocess.run([TAILSCALE,*args],capture_output=True,text=True,timeout=timeout)

def ts_status():
 # Tailscale's own status, or None when it isn't installed or running
 try: r=run('status','--json',timeout=10)
 except (FileNotFoundError,PermissionError): return None
 except subprocess.TimeoutExpired: return {'BackendState':'Unavailable'}
 try: return json.loads(r.stdout or '{}')
 except ValueError: return {'BackendState':'Unavailable'}

def qr_svg(text):
 return segno.make(text,error='m',micro=False).svg_inline(scale=4,border=2,dark='#000',light='#fff',omitsize=True)

def port():
 return os.environ.get('LAYERHOUND_PORT') or os.environ.get('TTRC_PORT') or '80'

def summarize(st):
 # What Settings shows, from "tailscale status --json"
 if st is None: return {'installed':False,'state':'not_installed'}
 state=st.get('BackendState') or 'NoState'
 me=st.get('Self') or {}; tailnet=st.get('CurrentTailnet') or {}
 dns=(me.get('DNSName') or '').rstrip('.'); ips=[ip for ip in me.get('TailscaleIPs') or [] if '.' in ip]
 users=st.get('User') or {}; account=(users.get(str(me.get('UserID'))) or {}).get('LoginName')
 suffix='' if port()=='80' else ':'+port()
 url=f'http://{dns}{suffix}' if dns and tailnet.get('MagicDNSEnabled',True) else (f'http://{ips[0]}{suffix}' if ips else None)
 with _lock: waiting=bool(_up and _up.poll() is None)
 out={'installed':True,
  'state':{'Running':'connected','NeedsLogin':'needs_login','NeedsMachineAuth':'needs_approval','Stopped':'off','Starting':'starting'}.get(state,'not_connected'),
  'waiting_for_sign_in':waiting and state in ('NeedsLogin','NoState','Starting'),
  'auth_url':st.get('AuthURL') or None,'account':account,'tailnet':tailnet.get('Name'),
  'url':url,'ip':ips[0] if ips else None,'key_expiry':me.get('KeyExpiry')}
 if out['auth_url']: out['auth_qr']=qr_svg(out['auth_url'])
 if state=='Running' and url: out['url_qr']=qr_svg(url)
 return out

def connect():
 # Start "tailscale up" in the background: it waits until the owner finishes signing in, while
 # Tailscale's status carries the sign-in link for Settings to show
 global _up,_up_started
 with _lock:
  if _up and _up.poll() is None and time.time()-_up_started<UP_TIMEOUT: return
  if _up and _up.poll() is None: _up.kill()
  hostname=socket.gethostname().split('.')[0] or 'layerhound'
  _up=subprocess.Popen([TAILSCALE,'up','--reset',f'--operator={getpass.getuser()}',f'--hostname={hostname}','--accept-dns=false',f'--timeout={UP_TIMEOUT}s'],
   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
  _up_started=time.time()

def wait_for(check,seconds=8):
 # Give Tailscale a moment to produce a sign-in link or connect
 end=time.time()+seconds; st=ts_status()
 while time.time()<end and not check(st):
  time.sleep(0.5); st=ts_status()
 return st

# ---- API -----------------------------------------------------------------------------------
@router.get('')
def get_status():
 if not available(): return {'available':False}
 return {'available':True,**summarize(ts_status())}

def _require():
 if not available(): raise HTTPException(409,'Remote access is set up on the LayerHound board.')
 st=ts_status()
 if st is None: raise HTTPException(409,"Tailscale isn't installed on this board. Run the full LayerHound install again to add it.")
 return st

@router.post('/connect')
def connect_now():
 st=_require()
 if st.get('BackendState')=='Running': return {'available':True,**summarize(st)}
 connect()
 st=wait_for(lambda s: s and (s.get('AuthURL') or s.get('BackendState') in ('Running','NeedsMachineAuth')))
 return {'available':True,**summarize(st)}

@router.post('/off')
def turn_off():
 # Keeps the sign-in: turning it back on doesn't need the Tailscale account again
 _require(); r=run('down')
 if r.returncode!=0:
  print(f'[remote] tailscale down: {r.stderr.strip()}',flush=True)
  raise HTTPException(500,"Couldn't turn remote access off. See the service log.")
 return {'available':True,**summarize(ts_status())}

@router.post('/sign-out')
def sign_out():
 # Removes this board from the Tailscale account; connecting again needs a new sign-in
 global _up
 _require()
 with _lock:
  if _up and _up.poll() is None: _up.kill()
  _up=None
 r=run('logout',timeout=30)
 if r.returncode!=0:
  print(f'[remote] tailscale logout: {r.stderr.strip()}',flush=True)
  raise HTTPException(500,"Couldn't sign out of Tailscale. See the service log.")
 return {'available':True,**summarize(ts_status())}
