#!/usr/bin/env bash
# Sets the board's own login password once, from LayerHound's setup page (backend/board.py).
# Installed by setup.sh as /usr/local/sbin/layerhound-board-password; LayerHound's account may run
# it with sudo, and nothing else. Reads the new password from the first line of its input.
#
# It only works while /etc/layerhound/board-password-needed is there: a LayerHound card puts it
# there because the board still has its maker's default password. Setting the password removes it,
# so LayerHound can never change the board password again after that (the owner can, with passwd).
set -euo pipefail
MARK=/etc/layerhound/board-password-needed
fail() { echo "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail "Run as root."

# The card's first start (firstboot.sh) checks the same mark; one at a time
exec 9>/run/layerhound-board-password.lock
flock 9
[ -e "$MARK" ] || fail "The board password is already set."
user="$(head -n1 "$MARK" | tr -cd 'a-z0-9_-')"; user="${user:-radxa}"
id "$user" >/dev/null 2>&1 || fail "The board account ($user) doesn't exist yet. Try again in a minute."

# Radxa's own first-start setup (re)creates the account with its default password: let it finish
# first (it deletes /config/before.txt when it's done), or it would undo this
for _ in $(seq 120); do [ -e /config/before.txt ] || break; sleep 1; done
[ ! -e /config/before.txt ] || fail "The board is still finishing its first start. Try again in a minute."

IFS= read -r pw || true
[ "${#pw}" -ge 8 ] || fail "The board password needs at least 8 characters."
[ "${#pw}" -le 200 ] || fail "That board password is too long."
case "$pw" in *[[:cntrl:]]*) fail "The board password can't contain control characters." ;; esac

printf '%s:%s\n' "$user" "$pw" | chpasswd
chage -d "$(date +%Y-%m-%d)" "$user"   # not expired any more: no "change your password" at the first sign-in
rm -f "$MARK"
echo "The password for $user is set."
