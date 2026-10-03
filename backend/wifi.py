# Wi-Fi settings on the Network page, using NetworkManager's nmcli (the board's network tool).
# setup.sh grants the LayerHound service permission to manage networks; no admin password needed.
import re, shutil, subprocess, sys
import psutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router=APIRouter(prefix='/api/network/wifi')
CONNECT_WAIT=30

def nmcli(*args,timeout=15):
 r=subprocess.run(['nmcli',*args],capture_output=True,text=True,timeout=timeout)
 return r.returncode,r.stdout,r.stderr.strip()

def fields(line):
 # nmcli -t separates fields with ":" and escapes ":" inside values as "\:"
 return [f.replace('\\:',':').replace('\\\\','\\') for f in re.split(r'(?<!\\):',line)]

def available():
 return sys.platform.startswith('linux') and shutil.which('nmcli') is not None and wifi_device() is not None

def devices():
 code,out,_=nmcli('-t','-f','DEVICE,TYPE,STATE,CONNECTION','device','status')
 return [dict(zip(('device','type','state','connection'),fields(l))) for l in out.splitlines() if l] if code==0 else []

def wifi_device():
 try: return next((d['device'] for d in devices() if d['type']=='wifi'),None)
 except Exception: return None

def ipv4(dev):
 for a in psutil.net_if_addrs().get(dev,[]):
  if a.family==2: return a.address
 return None

def band(freq):
 try: mhz=int(str(freq).split()[0])
 except (ValueError,IndexError): return None
 return '5 GHz' if mhz>=4900 else '2.4 GHz' if mhz>=2400 else None

def saved_wifi():
 code,out,_=nmcli('-t','-f','NAME,TYPE','connection','show')
 return {f[0] for f in map(fields,out.splitlines()) if len(f)>1 and f[1]=='802-11-wireless'} if code==0 else set()

def parse_scan(out,saved=()):
 # One entry per network name, keeping the strongest signal
 nets={}
 for line in out.splitlines():
  f=fields(line)
  if len(f)<5 or not f[1]: continue   # hidden networks have no name
  in_use,ssid,signal,freq,security=f[:5]
  n={'ssid':ssid,'signal':int(signal or 0),'band':band(freq),'secure':bool(security.strip() and security.strip()!='--'),
     'enterprise':'802.1X' in security,'in_use':in_use=='*','saved':ssid in saved}
  if ssid not in nets or n['in_use'] or (n['signal']>nets[ssid]['signal'] and not nets[ssid]['in_use']): nets[ssid]=n
 return sorted(nets.values(),key=lambda n:(not n['in_use'],-n['signal']))

def scan(rescan=False):
 code,out,err=nmcli('-t','-f','IN-USE,SSID,SIGNAL,FREQ,SECURITY','device','wifi','list','--rescan','yes' if rescan else 'auto',timeout=25)
 if code!=0: raise HTTPException(502,f"Couldn't scan for Wi-Fi networks: {err or 'unknown error'}")
 return parse_scan(out,saved_wifi())

def status():
 if not available(): return {'available':False,'reason':'Wi-Fi settings are available on the LayerHound board. This computer manages its own Wi-Fi.'}
 devs=devices(); wdev=wifi_device(); w=next(d for d in devs if d['device']==wdev)
 eth=[d for d in devs if d['type']=='ethernet']
 wired=next((d for d in eth if d['state']=='connected'),None)
 return {'available':True,'device':wdev,'wifi':{'connected':w['state']=='connected','network':w['connection'] or None,'ip':ipv4(wdev)},
  'ethernet':{'present':bool(eth),'connected':bool(wired),'ip':ipv4(wired['device']) if wired else None}}

@router.get('')
def wifi(rescan:bool=False):
 s=status()
 if s['available']: s['networks']=scan(rescan)
 return s

class Connect(BaseModel):
 ssid:str=Field(min_length=1,max_length=64); password:str|None=Field(default=None,max_length=128)

def need_wifi():
 if not available(): raise HTTPException(404,'Wi-Fi settings are only available on the LayerHound board')
 return wifi_device()

def friendly(err):
 e=err.lower()
 if 'secrets were required' in e or ('invalid' in e and 'key' in e) or '802-11-wireless-security' in e: return 'The password was rejected'
 if 'no network with ssid' in e: return "That network isn't in range"
 if 'timeout' in e or 'timed out' in e: return "The network didn't respond in time"
 return err or 'Unknown error'

@router.post('/connect')
def connect(b:Connect):
 dev=need_wifi(); ssid=b.ssid.strip()
 before=status()['wifi']['network']; was_saved=ssid in saved_wifi()
 if was_saved and not b.password:
  code,out,err=nmcli('--wait',str(CONNECT_WAIT),'connection','up','id',ssid,timeout=CONNECT_WAIT+10)
 else:
  args=['--wait',str(CONNECT_WAIT),'device','wifi','connect',ssid,'ifname',dev]
  if b.password: args+=['password',b.password]
  code,out,err=nmcli(*args,timeout=CONNECT_WAIT+10)
 if code!=0:
  # Don't leave a half-made profile behind, and get back on the network we were on
  if not was_saved: nmcli('connection','delete','id',ssid)
  back=before and nmcli('--wait',str(CONNECT_WAIT),'connection','up','id',before,timeout=CONNECT_WAIT+10)[0]==0
  raise HTTPException(400,f"Couldn't connect to {ssid}: {friendly(err)}."+(f' Reconnected to {before}.' if back else ''))
 # Wi-Fi power saving makes an always-on monitor sluggish and prone to drops; turn it off
 nmcli('connection','modify','id',ssid,'802-11-wireless.powersave','2')
 return {'status':'connected','network':ssid,'ip':ipv4(dev)}

class Forget(BaseModel):
 ssid:str=Field(min_length=1,max_length=64)

@router.post('/forget')
def forget(b:Forget):
 need_wifi()
 if b.ssid not in saved_wifi(): raise HTTPException(404,"That network isn't saved")
 s=status()
 if s['wifi']['network']==b.ssid and not s['ethernet']['connected']:
  raise HTTPException(409,"This is the board's only connection. Plug in Ethernet or connect to another Wi-Fi network first.")
 code,_,err=nmcli('connection','delete','id',b.ssid)
 if code!=0: raise HTTPException(502,f"Couldn't forget {b.ssid}: {err}")
 return {'status':'forgotten','network':b.ssid}
