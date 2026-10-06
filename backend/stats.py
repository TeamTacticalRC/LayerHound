# Optional anonymous usage stats, so Team Tactical RC can see how many farms use LayerHound,
# how many printers of each type they watch, and in which countries.
#
# - Off until the owner says yes (first-run setup, or Settings -> Usage stats). Never on by default.
# - Once a day, sends exactly what preview() returns: a random install ID made up on this
#   machine (so installs are counted once), the version, how it's installed, the board model,
#   the number of printers of each type, and the two-letter country from the internet check
#   LayerHound already makes. No names, addresses, serial numbers, access codes or print history.
# - Goes to Team Tactical RC's Google Form, like Send feedback.
import json, os, platform, secrets, threading, time, urllib.parse, urllib.request
from pathlib import Path
from fastapi import APIRouter, HTTPException
import network, settings

router=APIRouter(prefix='/api/stats')
# Team Tactical RC's "LayerHound usage stats" Google Form (set FORM to None to turn stats off entirely)
FORM={'id':'1FAIpQLSfOXSNFz3SpKBHY-apKzdQixxNrhac17oQlSV4LOUVkxOQrgQ',
 'fields':{'install_id':'entry.268855737','version':'entry.466736816','install_type':'entry.376961019','board':'entry.1307815542',
  'klipper':'entry.1691570087','bambu':'entry.1861386738','octoprint':'entry.1631942656','country':'entry.617296294'}}
SEND_EVERY=24*3600; FIRST_SEND_DELAY=120
_db=None; _printers=None; _id_file=None
state={'last_sent':None,'last_error':None}

def configure(db,printer_rows,data_dir):
 global _db,_printers,_id_file
 _db,_printers=db,printer_rows; _id_file=Path(data_dir)/'install-id'
 if settings.unattended(): threading.Thread(target=_loop,daemon=True,name='usage-stats').start()

def install_id():
 # Random, made up here, and kept in the data folder (not the database, so a backup restored
 # onto another machine doesn't make two installs look like one)
 try: return _id_file.read_text().strip()
 except OSError: pass
 new=secrets.token_hex(8)
 try: _id_file.parent.mkdir(parents=True,exist_ok=True); _id_file.write_text(new)
 except OSError: pass
 return new

def board():
 try: return Path('/proc/device-tree/model').read_text().strip('\x00 \n') or None
 except OSError: return None

def install_type():
 return 'board' if settings.as_service() and board() else 'linux' if settings.as_service() else 'docker' if settings.in_docker() else 'manual'

def preview():
 # Exactly what's sent; also shown to the owner before they choose
 counts={'moonraker':0,'bambu':0,'octoprint':0}
 for r in _printers():
  if r['printer_type'] in counts: counts[r['printer_type']]+=1
 return {'install_id':install_id(),'version':settings.APP_VERSION,'install_type':install_type(),
  'board':board() or platform.machine(),'klipper':counts['moonraker'],'bambu':counts['bambu'],'octoprint':counts['octoprint'],
  'country':network.state.get('country') or ''}

def send():
 if not FORM: return False
 data=preview()
 body=urllib.parse.urlencode({FORM['fields'][k]:str(v) for k,v in data.items()}).encode()
 req=urllib.request.Request(f"https://docs.google.com/forms/d/e/{FORM['id']}/formResponse",data=body,
  headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':f'LayerHound/{settings.APP_VERSION}'})
 try:
  with urllib.request.urlopen(req,timeout=20): pass
  state.update(last_sent=time.time(),last_error=None); return True
 except Exception as e:
  state['last_error']=f"Couldn't send: {type(e).__name__}"; return False

def _loop():
 time.sleep(FIRST_SEND_DELAY)
 while True:
  if settings.get('usage_stats')=='yes':
   if not state['last_sent'] or time.time()-state['last_sent']>=SEND_EVERY: send()
  time.sleep(3600)

@router.get('')
def status():
 return {'choice':settings.get('usage_stats'),'preview':preview(),'last_sent':state['last_sent'],'ready':FORM is not None}

def chosen(choice):
 # Called when the owner answers (Settings or first-run setup); a yes sends the first report soon
 if choice=='yes' and settings.unattended() and FORM: threading.Timer(30,send).start()
