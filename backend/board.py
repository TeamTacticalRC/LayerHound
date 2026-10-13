# The board's own login (the radxa account on a LayerHound card), set from LayerHound's setup page.
#
# A card starts with Radxa's default board password. The card image marks that with
# /etc/layerhound/board-password-needed, and while the mark is there, the first-run setup also asks
# for a board password. LayerHound can't change passwords itself: a small root helper
# (deploy/board-password.sh, installed by setup.sh) does it, and only while the mark is there, so
# once the owner has chosen a board password, LayerHound can never change it again.
# Only shown during first-run setup and to admins: anyone else learning that a board still has its
# default password would be told how to get in.
import os, subprocess
from pathlib import Path

MARK=Path(os.environ.get('LAYERHOUND_BOARD_MARK','/etc/layerhound/board-password-needed'))
HELPER='/usr/local/sbin/layerhound-board-password'

def needed(): return MARK.exists()

def user():
 # The board account the mark is for (the image writes it there); radxa on a ROCK 4D card
 try: return MARK.read_text().strip() or 'radxa'
 except OSError: return 'radxa'

def set_password(pw):
 # Returns None when done, or a message saying what went wrong
 if not needed(): return None
 if not Path(HELPER).exists(): return "This board can't set its password from LayerHound."
 cmd=([] if os.geteuid()==0 else ['sudo','-n'])+[HELPER]
 try: r=subprocess.run(cmd,input=pw+'\n',capture_output=True,text=True,timeout=150)
 except subprocess.TimeoutExpired: return 'The board took too long. Try again in a minute.'
 except OSError as e: return f"Couldn't run the board password helper ({type(e).__name__})."
 if r.returncode==0: return None
 lines=(r.stderr or r.stdout or '').strip().splitlines()
 return lines[-1] if lines else 'The board password could not be set.'
