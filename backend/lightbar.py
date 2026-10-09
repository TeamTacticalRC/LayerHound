# LED status light: an ESP32 with NeoPixels polls this endpoint (hardware/lightbar/).
#
# Two shapes, both from the same firmware:
# - Ring (the main LayerHound light, 12 LEDs, for a desk or shelf): each printer gets an arc of
#   the ring, with a dark LED between arcs. A printing arc fills up with the print's progress;
#   an error arc blinks red, so trouble stands out from across the room.
# - Bar (8 LEDs, mounted by the printers): one LED per printer.
# Printers are in the dashboard's display order (Print Farm -> Reorder).
#
# - LayerHound picks every LED's color and effect, so the firmware only draws what it's told and
#   the meanings can change here without reflashing the light.
# - The light signs in with a read-only access key (Settings -> Login & users), sent as
#   "Authorization: Bearer lhk_...". Keys can only view.
# - Kept small: the ESP32 reads it every few seconds.
# - Add-ons page: when a light checks in with its access key, LayerHound notes when (per shape) and
#   marks that shape as one the owner has, so its settings show without asking.
import time
from fastapi import APIRouter, HTTPException, Request
import settings

router=APIRouter(prefix='/api/lightbar')
DEFAULT_LEDS={'ring':12,'bar':8}; MAX_LEDS=64; POLL_SECONDS=5
DIM=0.18   # the not-yet-printed part of a printing arc
# state -> (red, green, blue at full brightness, effect). The firmware scales by "brightness".
LOOK={
 'printing':((0,255,40),'solid'),
 'paused':((255,140,0),'pulse'),
 'complete':((0,90,255),'solid'),
 'idle':((60,60,60),'solid'),
 'error':((255,0,0),'blink'),
 'offline':((255,0,0),'solid'),
}
OFF={'name':'','printer':None,'state':'none','rgb':[0,0,0],'effect':'off','progress':None}
OWNED={'ring':'addon_ring','bar':'addon_bar'}   # settings: the owner has this shape
_printers=None; seen={}   # shape -> {'at': time, 'leds': count, 'key': access key name}

def configure(get_printers):
 # main.py hands over its printer list (the same data the dashboard shows)
 global _printers; _printers=get_printers

def look(p):
 state=p.get('state') if p.get('state') in LOOK else ('offline' if not p.get('connected') else 'idle')
 rgb,effect=LOOK[state]
 progress=round(float(p.get('progress') or 0)) if state in ('printing','paused') else None
 return state,rgb,effect,progress

def led(p,i,rgb=None,level=1.0):
 state,base,effect,progress=look(p)
 return {'name':p.get('name') or '','printer':i,'state':state,'rgb':[round(c*level) for c in (rgb or base)],'effect':effect,'progress':progress}

def bar(printers,count):
 # One LED per printer
 out=[led(p,i) for i,p in enumerate(printers[:count])]
 return out+[dict(OFF) for _ in range(count-len(out))]

def ring(printers,count):
 # An arc per printer. Arcs of 3 or more LEDs keep their last LED dark as a gap, so neighbors
 # with the same color don't run together. Leftover LEDs at the end stay off.
 shown=printers[:count]; out=[]
 if not shown: return [dict(OFF) for _ in range(count)]
 size=count//len(shown); lit=size-1 if size>=3 else size
 for i,p in enumerate(shown):
  state,rgb,effect,progress=look(p)
  # Printing: the arc fills up with the print's progress (at least one LED, so it's never blank)
  filled=max(1,round(lit*progress/100)) if state=='printing' and lit>1 else lit
  out+=[led(p,i,rgb,1.0 if j<filled else DIM) for j in range(lit)]
  out+=[dict(OFF) for _ in range(size-lit)]
 return out+[dict(OFF) for _ in range(count-len(out))]

def checked_in(layout,count,who):
 # A light (signed in with an access key, saying its shape) just asked for its colors
 first=layout not in seen
 seen[layout]={'at':time.time(),'leds':count,'key':who.get('username')}
 if first and not settings.get(OWNED[layout]): settings.save({OWNED[layout]:True})

@router.get('')
def status(request:Request,layout:str|None=None,leds:int|None=None):
 # The light says what it is (?layout=ring&leds=12); otherwise the shape chosen in Settings
 device=layout is not None
 layout=layout or settings.get('lightbar_layout')
 if layout not in DEFAULT_LEDS: raise HTTPException(400,'layout must be ring or bar')
 count=DEFAULT_LEDS[layout] if leds is None else leds
 if not 1<=count<=MAX_LEDS: raise HTTPException(400,f'leds must be between 1 and {MAX_LEDS}')
 who=getattr(request.state,'who',None) or {}
 if device and who.get('kind')=='key': checked_in(layout,count,who)
 printers=_printers()['printers'] if _printers else []
 out=(ring if layout=='ring' else bar)(printers,count)
 return {'v':1,'poll':POLL_SECONDS,'layout':layout,'brightness':settings.get('lightbar_brightness'),
  'printers':len(printers),'names':[p.get('name') or '' for p in printers[:count]],
  'seen':{k:{**v,'ago':round(time.time()-v['at'])} for k,v in seen.items()},
  'leds':out[::-1] if settings.get('lightbar_reverse') else out}
