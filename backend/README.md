# LayerHound API

The FastAPI backend behind the dashboard. See the [main README](../README.md) to install and run it.

When running, interactive API docs are at `http://localhost:8000/docs`.

| Area | Endpoints | Module |
|---|---|---|
| Printers | `/api/printers`, `/api/printers/{id}`, `/api/printers/order`, `/api/printers/{id}/thumbnail`, `/api/printers/{id}/camera` | `main.py`, `media.py` |
| Print history | `/api/history`, `/api/history/stats`, `/api/history/import`, `/api/history/{id}` | `history.py` |
| System and server | `/api/health`, `/api/system`, `/api/server`, `/api/server/history` | `main.py` |
| Storage and files | `/api/storage`, `/api/files/*` | `storage.py` |
| Network | `/api/network`, `/api/network/devices`, `/api/network/scan` | `network.py` |
| Services | `/api/services`, `/api/services/docker/{id}/restart` | `services.py` |
| Login and accounts | `/api/auth/status`, `/api/auth/setup`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/password`, `/api/auth/users`, `/api/auth/keys` | `auth.py` |
| Setup hotspot | `/api/hotspot`, `/api/hotspot/connect` | `hotspot.py` |
| Settings | `/api/settings`, `/api/settings/about`, `/api/settings/backup`, `/api/settings/restore`, `/api/settings/clear-history/{kind}`, `/api/settings/restart` | `settings.py` |

Every `/api` endpoint except `/api/health` and the sign-in endpoints needs a session cookie or a read-only access key (`Authorization: Bearer lhk_...`). Changes need an admin and the `X-Requested-With: LayerHound` header.

Data is stored in SQLite (`layerhound.db` by default; see `LAYERHOUND_DB`).
