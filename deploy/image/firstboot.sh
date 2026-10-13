#!/usr/bin/env bash
# Runs once, as root, the first time a LayerHound card starts (layerhound-firstboot.service, put on
# the card by build-image.sh). Everything secret is created here, on the card itself, so no two
# cards share a key:
#   - SSH host keys (Radxa's own first-start setup normally does this; made here if it didn't)
#   - LayerHound's encryption key, install ID and database: LayerHound creates them on its first
#     start, which this waits for
#   - the board accounts: Radxa makes two, radxa and rock, with their names as passwords. radxa's
#     password is expired, so the first sign-in over SSH or with a keyboard asks for a new one;
#     rock is locked (one account to look after is enough)
# It also gives LayerHound control of Tailscale (which needs Tailscale running).
set -uo pipefail
DONE=/etc/layerhound/first-boot-done
BOARD_USER=radxa
SPARE_USERS="rock"
log() { echo "layerhound-firstboot: $*"; }

# Radxa's first-start setup (rsetup: grow the partition, SSH keys, the board account) runs at the
# same time; it deletes /config/before.txt when it's done. Wait for it, up to 5 minutes.
for _ in $(seq 300); do [ -e /config/before.txt ] || break; sleep 1; done

if ! ls /etc/ssh/ssh_host_*_key >/dev/null 2>&1; then
  log "creating SSH host keys"
  ssh-keygen -A && systemctl try-restart ssh
fi

if id "$BOARD_USER" >/dev/null 2>&1; then
  log "the $BOARD_USER password must be changed at first sign-in"
  passwd --expire "$BOARD_USER" >/dev/null
fi
for u in $SPARE_USERS; do
  id "$u" >/dev/null 2>&1 && { log "locking the $u account"; usermod --lock --expiredate 1 "$u"; }
done

if command -v tailscale >/dev/null; then
  ok=""
  for _ in $(seq 30); do tailscale set --operator=layerhound 2>/dev/null && { ok=1; break; }; sleep 2; done
  [ -n "$ok" ] || log "couldn't give LayerHound control of Tailscale"
fi

# LayerHound makes its keys and database on its first start; check they're there
for _ in $(seq 120); do
  [ -s /var/lib/layerhound/data/secret.key ] && [ -s /var/lib/layerhound/layerhound.db ] && break
  sleep 1
done
[ -s /var/lib/layerhound/data/secret.key ] || log "LayerHound hasn't created its key yet (it will when it starts)"

mkdir -p "$(dirname "$DONE")"
date -u +%Y-%m-%dT%H:%MZ > "$DONE"
log "done"
