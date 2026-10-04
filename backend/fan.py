# Case fan speed: quiet when the board is cool, faster as it warms up.
#
# The ROCK 4D's fan header has speed control (PWM). Linux shows it as the "pwmfan" device,
# where pwm1 takes 0-255. Out of the box it sits at full speed. setup.sh lets the LayerHound
# service write pwm1 (and nothing else), and this module sets it every few seconds from the
# chip temperature.
#
# Safety: if LayerHound stops, crashes or can't read a temperature, the fan goes to full speed
# (setup.sh also runs layerhound-fan-full as root after the service stops). The kernel's own
# overheating protection (slowing the processor at 85°C) works independently of all this.
import atexit, threading, time
from pathlib import Path
import settings

HWMON=Path('/sys/class/hwmon')
CHECK_EVERY=5
STEP_DOWN=4          # slow down at most this many % per check, so the fan doesn't pulse
FULL=255
# Hottest of these chip sensors drives the fan
SENSORS=('soc_thermal','bigcore_thermal','little_core_thermal','gpu_thermal','npu_thermal','ddr_thermal')
state={'percent':None,'target':None,'temp_c':None,'error':None}

def find(name,root=None):
 root=root or HWMON
 for d in sorted(root.glob('hwmon*')):
  try:
   if (d/'name').read_text().strip()==name: return d
  except OSError: pass
 return None

def device(root=None):
 d=find('pwmfan',root)
 return d if d and (d/'pwm1').exists() else None

def writable(d):
 try:
  with open(d/'pwm1','r+'): return True
 except OSError: return False

def chip_temp(root=None):
 temps=[]
 for name in SENSORS:
  d=find(name,root)
  if d:
   try: temps.append(int((d/'temp1_input').read_text())/1000)
   except (OSError,ValueError): pass
 return max(temps) if temps else None

def curve(temp,quiet,full,minimum):
 # Percent for a temperature: minimum up to "quiet", rising evenly to 100% at "full"
 if temp is None: return 100
 if temp<=quiet: return minimum
 if temp>=full: return 100
 return round(minimum+(100-minimum)*(temp-quiet)/(full-quiet))

def next_percent(current,target):
 # Speed up at once, slow down gently
 if current is None or target>=current: return target
 return max(target,current-STEP_DOWN)

def set_percent(d,percent):
 (d/'pwm1').write_text(str(round(FULL*percent/100)))

def read_percent(d):
 try: return round(int((d/'pwm1').read_text())*100/FULL)
 except (OSError,ValueError): return None

def tick(d,root=None):
 temp=chip_temp(root)
 if settings.get('fan_mode')=='full': target=100
 else: target=curve(temp,settings.get('fan_quiet_temp'),settings.get('fan_full_temp'),settings.get('fan_min_percent'))
 pct=next_percent(state['percent'] if state['percent'] is not None else read_percent(d),target)
 if pct!=state['percent']: set_percent(d,pct)
 state.update(percent=pct,target=target,temp_c=temp,error=None if temp is not None else "Couldn't read the chip temperature; running at full speed")

def loop(d):
 while True:
  try: tick(d)
  except Exception as e: state['error']=str(e)
  time.sleep(CHECK_EVERY)

def full_speed(d):
 try: set_percent(d,100)
 except OSError: pass

def status():
 d=device()
 if not d: return {'available':False}
 return {'available':True,'controlled':writable(d),'mode':settings.get('fan_mode'),
  'percent':state['percent'] if state['percent'] is not None else read_percent(d),
  'temp_c':state['temp_c'],'error':state['error']}

def configure():
 # Only where there is a speed-controlled fan LayerHound may set (the board, after setup.sh)
 d=device()
 if not d or not writable(d): return
 atexit.register(full_speed,d)
 threading.Thread(target=loop,args=(d,),daemon=True,name='fan').start()
