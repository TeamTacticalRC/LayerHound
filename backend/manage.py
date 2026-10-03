# Owner tools run on the board itself (over SSH or with a keyboard and screen attached).
#   Reset a forgotten password:  sudo -u <service user> ~/layerhound/backend/.venv/bin/python ~/layerhound/backend/manage.py reset-password
#   List accounts:               ... manage.py users
import argparse, getpass, sqlite3, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import os
import auth

def env(name): return os.environ.get(f'LAYERHOUND_{name}') or os.environ.get(f'TTRC_{name}')
DB_PATH=Path(env('DB') or Path(__file__).with_name('layerhound.db'))

def db():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def main():
 ap=argparse.ArgumentParser(description='LayerHound owner tools')
 sub=ap.add_subparsers(dest='cmd',required=True)
 r=sub.add_parser('reset-password',help='Set a new password for an account'); r.add_argument('username',nargs='?')
 sub.add_parser('users',help='List accounts')
 a=ap.parse_args()
 if not DB_PATH.exists(): sys.exit(f'No LayerHound database at {DB_PATH}')
 auth.configure(db)
 c=db(); users=[dict(u) for u in c.execute('SELECT username,role FROM users ORDER BY id')]; c.close()
 if a.cmd=='users':
  if not users: print('No accounts yet. Open LayerHound in a browser to create the first one.')
  for u in users: print(f"{u['username']}  ({u['role']})")
  return
 if not users: sys.exit('No accounts yet. Open LayerHound in a browser to create the first one.')
 name=a.username or (users[0]['username'] if len(users)==1 else input('Username: ').strip())
 pw=getpass.getpass(f'New password for {name}: ')
 if pw!=getpass.getpass('Type it again: '): sys.exit("The passwords don't match. Nothing was changed.")
 try: auth.reset_password(name,pw)
 except Exception as e: sys.exit(getattr(e,'detail',None) or str(e))
 print(f'Password changed for {name}. Any open sessions for that account were signed out.')

if __name__=='__main__': main()
