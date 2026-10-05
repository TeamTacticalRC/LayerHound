# Part thumbnails, layer metadata and camera snapshots for printers.
import json, socket, ssl, struct, threading, time, urllib.parse, urllib.request
import vault

TIMEOUT=6; META_TTL=3600; FAIL_TTL=300; WEBCAM_TTL=600; CAMERA_TTL=1.5
_meta={}; _thumbs={}; _webcams={}; _frames={}; lock=threading.Lock()
# Printers and cameras use self-signed certificates, so they can't be verified; still require modern TLS
INSECURE=ssl.create_default_context(); INSECURE.minimum_version=ssl.TLSVersion.TLSv1_2; INSECURE.check_hostname=False; INSECURE.verify_mode=ssl.CERT_NONE

def _get(url,timeout=TIMEOUT):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'LayerHound'}),timeout=timeout,context=INSECURE) as r:
  return r.read(), r.headers.get('Content-Type','')

def _cached(store,key,ttl,fn):
 with lock:
  hit=store.get(key)
  if hit and time.time()-hit[0]<hit[2]: return hit[1]
 try: val=fn(); keep=ttl
 except Exception: val=None; keep=FAIL_TTL if ttl>FAIL_TTL else ttl
 with lock: store[key]=(time.time(),val,keep)
 return val

# ---- Klipper (Moonraker) file metadata and thumbnails ------------------------------------
def moonraker_meta(base,path):
 # Slicer metadata for the file being printed: layer count, layer height, thumbnails
 if not path: return None
 return _cached(_meta,(base,path),META_TTL,lambda: json.loads(_get(f"{base}/server/files/metadata?filename={urllib.parse.quote(path)}")[0]).get('result'))

def moonraker_thumbnail(base,path):
 meta=moonraker_meta(base,path) or {}
 thumbs=sorted(meta.get('thumbnails') or [],key=lambda t:t.get('width',0))
 if not thumbs: return None
 # Largest thumbnail up to 400px wide (plenty for the dashboard), else the largest there is
 pick=[t for t in thumbs if t.get('width',0)<=400][-1:] or thumbs[-1:]
 folder=path.rsplit('/',1)[0]+'/' if '/' in path else ''
 rel=urllib.parse.quote(folder+pick[0]['relative_path'])
 return _cached(_thumbs,(base,path),META_TTL,lambda: _get(f'{base}/server/files/gcodes/{rel}'))

def moonraker_webcams(base):
 def fetch():
  cams=json.loads(_get(f'{base}/server/webcams/list')[0]).get('result',{}).get('webcams',[])
  return [c for c in cams if c.get('enabled',True) and (c.get('snapshot_url') or c.get('stream_url'))]
 return _cached(_webcams,base,WEBCAM_TTL,fetch) or []

def moonraker_layers(meta,info,vsd,z,active):
 # Current and total layers, from whichever source the printer offers:
 # Klipper's print stats (if the slicer sends them), Creality's own counter, or nozzle height
 cur=(info or {}).get('current_layer'); tot=(info or {}).get('total_layer')
 if not tot and vsd.get('layer_count'): cur,tot=vsd.get('layer'),vsd.get('layer_count')
 if not tot and meta: tot=meta.get('layer_count')
 if cur is None and tot and meta and active and z is not None:
  lh=meta.get('layer_height'); flh=meta.get('first_layer_height') or lh
  if lh: cur=round((z-flh)/lh)+1
 if not active or not tot: return None,None
 return (max(1,min(int(cur),int(tot))) if cur else None),int(tot)

# ---- Cameras ------------------------------------------------------------------------------
def _first_jpeg(url,limit=4_000_000):
 # Snapshot URLs return one image; MJPEG stream URLs return a never-ending series of frames,
 # so read just until the first complete JPEG
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'LayerHound'}),timeout=TIMEOUT,context=INSECURE) as r:
  ctype=r.headers.get('Content-Type','')
  if ctype.startswith('image/'): return r.read(limit)
  buf=b''
  while len(buf)<limit:
   chunk=r.read(16384)
   if not chunk: break
   buf+=chunk; a=buf.find(b'\xff\xd8')
   if a!=-1:
    b=buf.find(b'\xff\xd9',a+2)
    if b!=-1: return buf[a:b+2]
 raise ValueError('No image found at that camera address')

def _recv(sock,n):
 data=b''
 while len(data)<n:
  chunk=sock.recv(n-len(data))
  if not chunk: raise ConnectionError('Camera closed the connection')
  data+=chunk
 return data

def bambu_frame(host,code):
 # Bambu P1 and A1 series camera: TLS on port 6000, an 80-byte login (user "bblp" + access code),
 # then frames of a 16-byte header (little-endian payload size first) followed by a JPEG
 auth=struct.pack('<IIII',0x40,0x3000,0,0)+b'bblp'.ljust(32,b'\0')+str(code).encode().ljust(32,b'\0')
 # The camera's certificate is self-signed, so it can't be verified; still require TLS 1.2 or newer
 ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); ctx.minimum_version=ssl.TLSVersion.TLSv1_2; ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
 with socket.create_connection((host,6000),timeout=TIMEOUT) as s, ctx.wrap_socket(s,server_hostname=host) as t:
  t.sendall(auth)
  size=struct.unpack('<I',_recv(t,16)[:4])[0]
  if not 0<size<5_000_000: raise ValueError('Unexpected camera response; check the access code')
  img=_recv(t,size)
  if not img.startswith(b'\xff\xd8'): raise ValueError('Camera sent something other than an image')
  return img

def camera_source(row):
 # Where this printer's camera image comes from, or None. A camera URL set on the printer wins.
 if row['camera_url']: return ('url',row['camera_url'])
 host=urllib.parse.urlparse(row['base_url'] if '://' in row['base_url'] else 'http://'+row['base_url']).hostname
 if row['printer_type']=='bambu' and row['api_key']: return ('bambu',(host,vault.decrypt(row['api_key'])))
 if row['printer_type']=='moonraker':
  base=row['base_url'] if '://' in row['base_url'] else 'http://'+row['base_url']
  cams=moonraker_webcams(base.rstrip('/'))
  if cams:
   url=cams[0].get('snapshot_url') or cams[0].get('stream_url')
   # Webcam addresses are usually relative to the printer's web interface (port 80)
   return ('url',url if '://' in url else f"http://{host}{url if url.startswith('/') else '/'+url}")
 return None

def camera_frame(row):
 src=camera_source(row)
 if not src: return None
 kind,arg=src
 def grab(): return bambu_frame(*arg) if kind=='bambu' else _first_jpeg(arg)
 # Several open dashboards share one frame per printer every 1.5 seconds
 with lock:
  hit=_frames.get(row['id'])
  if hit and time.time()-hit[0]<CAMERA_TTL: return hit[1]
 img=grab()
 with lock: _frames[row['id']]=(time.time(),img)
 return img

def has_camera(row):
 try: return camera_source(row) is not None
 except Exception: return False
