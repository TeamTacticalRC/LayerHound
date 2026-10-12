# Going back from the /opt move

LayerHound 1.4 moves installs out of the owner's home folder:

| | Before (up to 1.3) | From 1.4 |
|---|---|---|
| Code | `~/layerhound` | `/opt/layerhound` (owned by root) |
| Database and data | `~/layerhound/backend/` | `/var/lib/layerhound/` |
| Files folder | `~/LayerHound Files` | `/var/lib/layerhound/files` |
| Runs as | the owner's login account | its own `layerhound` account (no login, no sudo) |
| Setup records | `/var/lib/layerhound/setup.sha256`, `port` | `/etc/layerhound/setup.sha256`, `port` |

The first 1.4 setup **copies** the database, data and Files folder over and leaves `~/layerhound` as it was, so going back is always possible.

## The milestone

- **Code:** the git tag `milestone-home-install-2026-10-12` (v1.3.0 plus Settings tabs, commit bc4fe34) is the last home-folder version. `git checkout milestone-home-install-2026-10-12` gets it back.
- **Kyle's board, before the move:** `~/layerhound-milestone-2026-10-12/` on the board (a consistent copy of the database and a tarball of `~/layerhound` and the Files folder), with a copy on the release Mac in `~/.layerhound/backups/`. These include the encryption key: keep them private, never commit them.

## Going back on a board

On the board, as the owner:

```bash
bash /opt/layerhound/deploy/revert-to-home-install.sh
```

It downloads and signature-checks LayerHound 1.3.0, stops LayerHound, copies the **current** database, data and Files folder back to the home-folder layout (so nothing done since the move is lost), puts 1.3.0 in `~/layerhound` and runs its setup, which sets the service, permissions and Tailscale back. `/opt/layerhound`, `/var/lib/layerhound` and the `layerhound` account are left in place, unused. The database copy there is renamed `layerhound.db.before-revert-…`, so moving to the 1.4 layout again later (`install.sh --update`) copies your current data fresh instead of the stale copy. Remove them by hand once you're sure:

```bash
sudo rm -rf /opt/layerhound /opt/layerhound-rollback /var/lib/layerhound /etc/layerhound /usr/local/sbin/layerhound-install-code
sudo userdel layerhound
```

**Tested 2026-10-12** on the main board: moved, updated on the new layout, reverted with this script (current data carried back, including settings changed after the move), and moved again.

## Going back on a development board (deploy.sh)

Run the revert script on the board as above, then on the Mac:

```bash
git checkout milestone-home-install-2026-10-12
deploy/deploy.sh radxa@layerhound.local --full
```

The old `deploy.sh` copies into `~/layerhound` and runs the old setup. Come back to the latest with `git checkout main`.

## If the data itself needs restoring

To go back to the data as it was at the milestone (losing anything since): stop LayerHound, then restore `layerhound.db` from `~/layerhound-milestone-2026-10-12/` into wherever the running version keeps it (`/var/lib/layerhound/` from 1.4, `~/layerhound/backend/` before), owned by the account LayerHound runs as.
