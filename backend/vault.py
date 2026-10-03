# Encrypts stored secrets: printer access codes and API keys, and service tokens.
#
# The key lives in its own file (data/secret.key, readable only by the LayerHound user), never in
# the database. A copy of the database on its own (sent along with a bug report, or grabbed from a
# backup of the disk) doesn't reveal any secrets. Someone with full access to the board itself can
# still read both files; that's what keeping the board on a private network protects against.
#
# Values are stored as "enc1:" + a Fernet token (AES with a tamper check, from the cryptography
# package). Values without the prefix are from before encryption and are encrypted at startup.
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

PREFIX='enc1:'
# Every table and column that holds a secret
COLUMNS=(('printers','api_key'),('services','token'))
_fernet=None; _warned=set()

def configure(key_path):
 global _fernet
 key_path=Path(key_path)
 if not key_path.exists():
  key_path.parent.mkdir(parents=True,exist_ok=True)
  # Created readable by this user only; O_EXCL so two starts can't write different keys
  try:
   fd=os.open(key_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'wb') as f: f.write(Fernet.generate_key())
  except FileExistsError: pass
 _fernet=Fernet(key_path.read_bytes().strip())

def encrypt(value):
 if not value: return None
 if value.startswith(PREFIX): return value
 return PREFIX+_fernet.encrypt(value.encode()).decode()

def decrypt(value):
 if not value: return None
 if not value.startswith(PREFIX): return value   # stored before encryption existed
 try: return _fernet.decrypt(value[len(PREFIX):].encode()).decode()
 except InvalidToken:
  # Encrypted with a different key: the database was copied from another install, or the key file
  # was replaced. The secret can't be recovered; re-enter it on the Print Farm or Services page.
  if value not in _warned: _warned.add(value); print('[vault] a stored secret was encrypted with a different key; re-enter it',flush=True)
  return None

def migrate(db):
 # Encrypt anything still stored in plain text
 c=db()
 for table,col in COLUMNS:
  rows=c.execute(f"SELECT id,{col} FROM {table} WHERE {col} IS NOT NULL AND {col}!='' AND {col} NOT LIKE '{PREFIX}%'").fetchall()
  c.executemany(f'UPDATE {table} SET {col}=? WHERE id=?',[(encrypt(r[1]),r[0]) for r in rows])
 c.commit(); c.close()
