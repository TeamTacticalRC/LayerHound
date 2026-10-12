# Where LayerHound keeps things. The service gets these from its environment (deploy/setup.sh):
#   code        /opt/layerhound            (owned by root; LayerHound can't change it)
#   database    /var/lib/layerhound/layerhound.db
#   data        /var/lib/layerhound/data   (encryption key, backups, updates, problems, ...)
#   files       /var/lib/layerhound/files  (the LayerHound Files folder)
# Without the environment (development, tests, installs from before 1.4), the database sits next
# to the code and data in backend/data, as before.
import os
from pathlib import Path

def env(name): return os.environ.get(f'LAYERHOUND_{name}') or os.environ.get(f'TTRC_{name}')

DB_PATH=Path(env('DB') or Path(__file__).with_name('layerhound.db'))
DATA=DB_PATH.parent/'data'
