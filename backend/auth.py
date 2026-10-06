# Login, accounts, sessions and access keys.
#
# - The first visit (no accounts yet) shows a welcome screen that creates the admin account.
# - Passwords are stored only as scrambled one-way hashes (scrypt, built into Python).
# - Signing in gives the browser a random session ID in an HttpOnly cookie; only its hash is stored.
# - Admins can change things; viewers can only look. Access keys are read-only, for devices.
# - Every change (POST/PUT/DELETE) must carry the X-Requested-With header, which a form on
#   another website can't add, so other sites can't make changes using your login.
import base64, hashlib, hmac, ipaddress, secrets, sqlite3, threading, time
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import settings

router=APIRouter(prefix='/api/auth')
COOKIE='lh_session'; CSRF_HEADER='x-requested-with'
SESSION_SHORT=24*3600; SESSION_LONG=30*86400
MAX_FAILS=5; FAIL_WINDOW=15*60; LOCKOUT=5*60
_db=None; _fails={}; _lock=threading.Lock()
ROLES=('admin','viewer')
after_setup=[]

def configure(db):
 global _db; _db=db
 c=_db()
 c.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,role TEXT NOT NULL,created_at REAL NOT NULL,last_login REAL)''')
 c.execute('CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,created_at REAL NOT NULL,expires_at REAL NOT NULL,remember INTEGER NOT NULL)')
 c.execute('''CREATE TABLE IF NOT EXISTS access_keys(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,key_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,created_at REAL NOT NULL,last_used REAL)''')
 c.execute('DELETE FROM sessions WHERE expires_at<?',(time.time(),)); c.commit(); c.close()

# ---- Passwords ----------------------------------------------------------------------------
SCRYPT=dict(n=2**14,r=8,p=1)
def hash_password(pw):
 salt=secrets.token_bytes(16); h=hashlib.scrypt(pw.encode(),salt=salt,dklen=32,**SCRYPT)
 return 'scrypt${n}${r}${p}$'.format(**SCRYPT)+base64.b64encode(salt).decode()+'$'+base64.b64encode(h).decode()

def check_password(pw,stored):
 try:
  _,n,r,p,salt,h=stored.split('$')
  got=hashlib.scrypt(pw.encode(),salt=base64.b64decode(salt),n=int(n),r=int(r),p=int(p),dklen=32)
  return hmac.compare_digest(got,base64.b64decode(h))
 except Exception: return False

DUMMY_HASH=hash_password(secrets.token_hex(8))

def validate_password(pw):
 if len(pw or '')<8: raise HTTPException(400,'Passwords need at least 8 characters')
 if len(pw)>200: raise HTTPException(400,'That password is too long')

def validate_username(u):
 u=(u or '').strip()
 if not (1<=len(u)<=40) or not all(ch.isalnum() or ch in '._-' for ch in u): raise HTTPException(400,'Usernames are 1–40 letters, numbers, dots, dashes or underscores')
 return u

# ---- Who is asking ------------------------------------------------------------------------
def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def has_users():
 c=_db(); n=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]; c.close(); return n>0

def is_local(host):
 # Guest viewing (when enabled) only applies to devices on the same local network
 try: a=ipaddress.ip_address((host or '').split('%')[0])
 except ValueError: return host in ('localhost',)
 return a.is_private or a.is_loopback or a.is_link_local

def principal(request):
 # Returns {'kind':'user'|'key'|'guest', 'role':..., ...} or None
 token=request.cookies.get(COOKIE)
 if token:
  c=_db(); r=c.execute('SELECT u.id,u.username,u.role,s.expires_at,s.remember FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?',(sha(token),)).fetchone()
  if r and r['expires_at']>time.time():
   # Sessions without "keep me signed in" slide forward while in use (at most one write an hour)
   if not r['remember'] and r['expires_at']-time.time()<SESSION_SHORT-3600: c.execute('UPDATE sessions SET expires_at=? WHERE token_hash=?',(time.time()+SESSION_SHORT,sha(token))); c.commit()
   c.close(); return {'kind':'user','id':r['id'],'username':r['username'],'role':r['role']}
  c.close()
 auth=request.headers.get('authorization','')
 key=auth[7:].strip() if auth.lower().startswith('bearer ') else request.query_params.get('key')
 if key:
  c=_db(); r=c.execute('SELECT id,name FROM access_keys WHERE key_hash=?',(sha(key),)).fetchone()
  if r: c.execute('UPDATE access_keys SET last_used=? WHERE id=?',(time.time(),r['id'])); c.commit(); c.close(); return {'kind':'key','id':r['id'],'username':r['name'],'role':'viewer'}
  c.close()
 if settings.get('guest_view') and is_local(request.client.host if request.client else ''): return {'kind':'guest','username':None,'role':'viewer'}
 return None

# Endpoints anyone can reach: health check, and the auth endpoints that sign in or set up
# (hotspot.py checks its own endpoints: open to the first-run setup on the hotspot, otherwise admins only)
PUBLIC={('GET','/api/health'),('GET','/api/auth/status'),('POST','/api/auth/login'),('POST','/api/auth/logout'),('POST','/api/auth/setup'),
 ('GET','/api/hotspot'),('POST','/api/hotspot/connect')}
# Changes any signed-in user may make to their own account
SELF_SERVICE={('POST','/api/auth/password')}
# Reads that are admin-only because they contain secrets
ADMIN_READS=('/api/settings/backup','/api/auth/users','/api/auth/keys')

async def middleware(request:Request,call_next):
 path=request.url.path; method=request.method
 if not path.startswith('/api/') or method=='OPTIONS': return await call_next(request)
 changing=method not in ('GET','HEAD')
 if changing and request.headers.get(CSRF_HEADER)!='LayerHound':
  return JSONResponse({'detail':'Missing request header'},status_code=403)
 if (method,path) in PUBLIC: return await call_next(request)
 if not has_users(): return JSONResponse({'detail':'setup_required'},status_code=401)
 who=principal(request)
 if not who: return JSONResponse({'detail':'login_required'},status_code=401)
 if (changing and (method,path) not in SELF_SERVICE or path.startswith(ADMIN_READS)) and who['role']!='admin':
  return JSONResponse({'detail':'Only an admin can do that'},status_code=403)
 if (method,path) in SELF_SERVICE and who['kind']!='user':
  return JSONResponse({'detail':'Sign in to change your password'},status_code=403)
 request.state.who=who
 return await call_next(request)

# ---- Sign-in throttling -------------------------------------------------------------------
# Counted per device (IP address), so someone else guessing can't lock the owner out
def throttle_check(ip):
 now=time.time()
 with _lock:
  f=_fails.get(ip)
  if f and f['locked_until']>now: raise HTTPException(429,f"Too many wrong passwords. Try again in {int((f['locked_until']-now)//60)+1} minute(s).")

def throttle_fail(ip):
 now=time.time()
 with _lock:
  f=_fails.get(ip)
  if not f or now-f['first']>FAIL_WINDOW: f=_fails[ip]={'first':now,'count':0,'locked_until':0}
  f['count']+=1
  if f['count']>=MAX_FAILS: f['locked_until']=now+LOCKOUT; f['count']=0; f['first']=now

def throttle_clear(ip):
 with _lock: _fails.pop(ip,None)

def start_session(response,user_id,remember):
 token=secrets.token_urlsafe(32); now=time.time(); ttl=SESSION_LONG if remember else SESSION_SHORT
 c=_db(); c.execute('INSERT INTO sessions(token_hash,user_id,created_at,expires_at,remember) VALUES(?,?,?,?,?)',(sha(token),user_id,now,now+ttl,int(remember)))
 c.execute('UPDATE users SET last_login=? WHERE id=?',(now,user_id)); c.commit(); c.close()
 # "Keep me signed in" keeps the cookie for 30 days; otherwise it ends when the browser closes
 response.set_cookie(COOKIE,token,max_age=ttl if remember else None,httponly=True,samesite='lax',path='/')

# ---- API ----------------------------------------------------------------------------------
@router.get('/status')
def status(request:Request):
 who=principal(request) if has_users() else None
 return {'setup_required':not has_users(),'user':who and {'username':who['username'],'role':who['role'],'kind':who['kind']},
  'farm_name':settings.get('farm_name'),'accent':settings.get('accent'),
  # Phones on the setup hotspot get the Wi-Fi setup screen
  'on_hotspot':bool(request.client) and request.client.host.startswith('10.42.0.')}

class Setup(BaseModel):
 farm_name:str=Field(min_length=1,max_length=40); username:str; password:str
 usage_stats:str|None=None   # the owner's answer to sharing anonymous stats: 'yes' or 'no'

@router.post('/setup')
def setup(b:Setup,request:Request,response:Response):
 # Only works once (while no account exists), and only from the local network
 if has_users(): raise HTTPException(409,'Setup is already done. Sign in instead.')
 if not is_local(request.client.host if request.client else ''): raise HTTPException(403,'Set up LayerHound from a device on the same network')
 username=validate_username(b.username); validate_password(b.password)
 settings.save({'farm_name':b.farm_name,**({'usage_stats':b.usage_stats} if b.usage_stats in ('yes','no') else {})})
 c=_db()
 try:
  uid=c.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,'admin',?)",(username,hash_password(b.password),time.time())).lastrowid; c.commit()
 except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'Setup is already done. Sign in instead.')
 c.close(); start_session(response,uid,True)
 for fn in after_setup:   # e.g. start looking for printers right away
  try: fn()
  except Exception as e: print(f'[auth] after-setup hook failed: {e}',flush=True)
 return {'status':'ok','user':{'username':username,'role':'admin'}}

class Login(BaseModel):
 username:str=Field(max_length=40); password:str=Field(max_length=200); remember:bool=False

@router.post('/login')
def login(b:Login,request:Request,response:Response):
 ip=request.client.host if request.client else '?'; throttle_check(ip)
 c=_db(); r=c.execute('SELECT id,username,password_hash,role FROM users WHERE username=?',(b.username.strip(),)).fetchone(); c.close()
 # Same answer (and similar time) whether the username or the password was wrong
 ok=check_password(b.password,r['password_hash'] if r else DUMMY_HASH) and r is not None
 if not ok: throttle_fail(ip); raise HTTPException(401,'Wrong username or password')
 throttle_clear(ip); start_session(response,r['id'],b.remember)
 return {'status':'ok','user':{'username':r['username'],'role':r['role']}}

@router.post('/logout')
def logout(request:Request,response:Response):
 token=request.cookies.get(COOKIE)
 if token: c=_db(); c.execute('DELETE FROM sessions WHERE token_hash=?',(sha(token),)); c.commit(); c.close()
 response.delete_cookie(COOKIE,path='/'); return {'status':'signed out'}

class ChangePassword(BaseModel):
 current:str=Field(max_length=200); new:str=Field(max_length=200)

@router.post('/password')
def change_password(b:ChangePassword,request:Request):
 who=request.state.who; c=_db(); r=c.execute('SELECT password_hash FROM users WHERE id=?',(who['id'],)).fetchone()
 if not r or not check_password(b.current,r['password_hash']): c.close(); raise HTTPException(400,'Your current password is wrong')
 validate_password(b.new)
 # Sign out everywhere else, keep this browser signed in
 token=request.cookies.get(COOKIE)
 c.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(b.new),who['id']))
 c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash!=?',(who['id'],sha(token or ''))); c.commit(); c.close()
 return {'status':'changed'}

# ---- Users (admin) ------------------------------------------------------------------------
class NewUser(BaseModel):
 username:str; password:str; role:str='viewer'

@router.get('/users')
def users():
 c=_db(); rows=[dict(r) for r in c.execute('SELECT id,username,role,created_at,last_login FROM users ORDER BY id')]; c.close(); return {'users':rows}

@router.post('/users')
def add_user(b:NewUser):
 if b.role not in ROLES: raise HTTPException(400,'Role must be admin or viewer')
 username=validate_username(b.username); validate_password(b.password)
 c=_db()
 try: uid=c.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)',(username,hash_password(b.password),b.role,time.time())).lastrowid; c.commit()
 except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'That username is taken')
 c.close(); return {'id':uid,'username':username,'role':b.role}

def admins(c): return c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]

class EditUser(BaseModel):
 role:str|None=None; password:str|None=None

@router.put('/users/{uid}')
def edit_user(uid:int,b:EditUser):
 c=_db(); r=c.execute('SELECT role FROM users WHERE id=?',(uid,)).fetchone()
 if not r: c.close(); raise HTTPException(404,'User not found')
 if b.role:
  if b.role not in ROLES: c.close(); raise HTTPException(400,'Role must be admin or viewer')
  if r['role']=='admin' and b.role!='admin' and admins(c)<=1: c.close(); raise HTTPException(409,'LayerHound needs at least one admin')
  c.execute('UPDATE users SET role=? WHERE id=?',(b.role,uid))
 if b.password:
  validate_password(b.password); c.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(b.password),uid)); c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
 c.commit(); c.close(); return {'status':'saved'}

@router.delete('/users/{uid}')
def delete_user(uid:int,request:Request):
 if request.state.who.get('id')==uid and request.state.who['kind']=='user': raise HTTPException(409,"You can't remove your own account")
 c=_db(); r=c.execute('SELECT role FROM users WHERE id=?',(uid,)).fetchone()
 if not r: c.close(); raise HTTPException(404,'User not found')
 if r['role']=='admin' and admins(c)<=1: c.close(); raise HTTPException(409,'LayerHound needs at least one admin')
 c.execute('DELETE FROM sessions WHERE user_id=?',(uid,)); c.execute('DELETE FROM users WHERE id=?',(uid,)); c.commit(); c.close(); return {'status':'deleted'}

# ---- Access keys (admin) ------------------------------------------------------------------
class NewKey(BaseModel):
 name:str=Field(min_length=1,max_length=60)

@router.get('/keys')
def keys():
 c=_db(); rows=[dict(r) for r in c.execute('SELECT id,name,prefix,created_at,last_used FROM access_keys ORDER BY id')]; c.close(); return {'keys':rows}

@router.post('/keys')
def add_key(b:NewKey):
 # The full key is shown once; only its hash is kept
 key='lhk_'+secrets.token_urlsafe(24); c=_db()
 kid=c.execute('INSERT INTO access_keys(name,key_hash,prefix,created_at) VALUES(?,?,?,?)',(b.name.strip(),sha(key),key[:8],time.time())).lastrowid
 c.commit(); c.close(); return {'id':kid,'name':b.name.strip(),'key':key}

@router.delete('/keys/{kid}')
def delete_key(kid:int):
 c=_db(); cur=c.execute('DELETE FROM access_keys WHERE id=?',(kid,)); c.commit(); c.close()
 if not cur.rowcount: raise HTTPException(404,'Key not found')
 return {'status':'revoked'}

# ---- Password reset from the board itself -------------------------------------------------
def reset_password(username,new_password):
 # Used by manage.py on the board; physical/SSH access proves ownership
 validate_password(new_password); c=_db(); r=c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
 if not r: c.close(); raise ValueError(f'No account named {username}')
 c.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(new_password),r['id'])); c.execute('DELETE FROM sessions WHERE user_id=?',(r['id'],))
 c.commit(); c.close()
