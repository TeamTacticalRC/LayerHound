# Recent problems: a plain-language list of what went wrong (printers that can't be reached, failed
# commands, failed updates, crashes, dashboard errors), for Settings -> About & maintenance.
#
# - Kept on the board only (data/problems.json, the last MAX entries). Nothing is sent anywhere.
# - The same problem again within REPEAT_WINDOW just counts up, so a printer that stays offline
#   doesn't fill the list.
# - "Shareable": for Send feedback and GitHub bug reports, the owner can include recent problems with
#   names, addresses, serial numbers and emails replaced (scrub()), and sees exactly that text first.
import json, re, threading, time, traceback
from pathlib import Path
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router=APIRouter(prefix='/api/problems')
MAX=200; REPEAT_WINDOW=30*60; SHARE=25
SOURCES={'printer':'Printer','control':'Printer controls','update':'Updates','network':'Network','service':'Services',
 'remote':'Remote access','hotspot':'Setup hotspot','crash':'LayerHound','dashboard':'Dashboard page','system':'System'}
_lock=threading.Lock(); _items=[]; _file=None
_names=lambda: []   # main.py hands over the printer names and types, for scrubbing

def configure(data_dir,printer_names=None):
 global _file,_names
 _file=Path(data_dir)/'problems.json'
 if printer_names: _names=printer_names
 try: _items[:]=json.loads(_file.read_text())[-MAX:]
 except (OSError,ValueError): _items.clear()

def _save():
 if not _file: return
 try:
  _file.parent.mkdir(parents=True,exist_ok=True)
  tmp=_file.with_suffix('.tmp'); tmp.write_text(json.dumps(_items[-MAX:])); tmp.replace(_file)
 except OSError as e: print(f'[problems] could not save: {e}',flush=True)

def record(source,message,detail=None):
 # message: what an owner should read; detail: the technical part (shown on request)
 now=time.time(); message=' '.join(str(message).split())[:300]; detail=(str(detail)[:2000] if detail else None)
 with _lock:
  for it in reversed(_items):
   if it['source']==source and it['message']==message and now-it['last']<REPEAT_WINDOW:
    it['count']+=1; it['last']=now; it['detail']=detail or it['detail']; _save(); return
  _items.append({'id':int(now*1000),'source':source,'message':message,'detail':detail,'first':now,'last':now,'count':1})
  del _items[:-MAX]; _save()

def crash(where,e):
 # Something unexpected: keep the last lines of the traceback as the detail
 record('crash',f'Something went wrong ({where})',''.join(traceback.format_exception(e))[-1500:])

# ---- Scrubbing, for sharing ------------------------------------------------------------------
PATTERNS=[
 (re.compile(r'[\w.+-]+@[\w-]+(\.[\w-]+)+'),'<email>'),
 (re.compile(r'\b[\w-]+(\.[\w-]+)*\.ts\.net\b'),'<tailscale-name>'),
 (re.compile(r'\b(https?|mqtts?|ftps?)://[^\s/"\']+'),r'\1://<address>'),
 (re.compile(r'\b(\d{1,3}\.){3}\d{1,3}\b'),'<ip>'),
 (re.compile(r'\b([0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b',re.I),'<mac>'),
 (re.compile(r'\b[0-9a-f]{0,4}(:[0-9a-f]{0,4}){3,7}\b',re.I),'<ip>'),
 (re.compile(r'\b[\w-]+\.local\b'),'<host>.local'),
 (re.compile(r'\b(0[0-9A-Z]{14}|[0-9A-Z]{3}\d{2}[0-9A-Z]{10})\b'),'<serial>'),   # Bambu serial numbers
 (re.compile(r'\blhk_[\w-]+'),'<access-key>'),
]

def scrub(text):
 text=str(text or '')
 # Printer names become "Klipper printer 1" etc., numbered in dashboard order; replaced longest
 # name first, so "U1 Left" goes before "U1"
 numbered=[(name,f'{kind} printer {i+1}') for i,(name,kind) in enumerate(_names()) if name]
 for name,label in sorted(numbered,key=lambda n:-len(n[0])): text=re.sub(re.escape(name),label,text,flags=re.I)
 for pat,rep in PATTERNS: text=pat.sub(rep,text)
 return text

def shareable(n=SHARE):
 # The recent problems as plain text, scrubbed, newest first
 with _lock: items=list(_items)[-n:][::-1]
 lines=[]
 for it in items:
  when=time.strftime('%Y-%m-%d %H:%M',time.gmtime(it['last']))
  times=f" (x{it['count']})" if it['count']>1 else ''
  lines.append(f"{when} UTC [{SOURCES.get(it['source'],it['source'])}] {it['message']}{times}")
  if it['detail']: lines.append('    '+it['detail'].strip().splitlines()[-1][:300])
 return scrub('\n'.join(lines))

# ---- API -----------------------------------------------------------------------------------
@router.get('')
def list_problems(shareable_text:bool=False):
 with _lock: items=list(_items)[::-1]
 out={'problems':[{**it,'source_label':SOURCES.get(it['source'],it['source'])} for it in items]}
 if shareable_text: out['shareable']=shareable()
 return out

@router.delete('')
def clear():
 with _lock: _items.clear(); _save()
 return {'status':'cleared'}

class PageError(BaseModel):
 message:str=Field(max_length=500); detail:str|None=Field(default=None,max_length=4000); page:str|None=Field(default=None,max_length=40)

_page_reports=[]
@router.post('/report')
def report(b:PageError,request:Request):
 # A crash in the dashboard page itself (sent by the page, for anyone signed in); a few a minute at most
 now=time.time(); _page_reports[:]=[t for t in _page_reports if now-t<60]
 if len(_page_reports)>=10: return {'status':'ignored'}
 _page_reports.append(now)
 record('dashboard',f"The dashboard page hit an error{' on '+b.page if b.page else ''}: {b.message}",b.detail)
 return {'status':'recorded'}
