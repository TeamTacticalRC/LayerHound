# LayerHound API

The FastAPI backend behind the dashboard. See the [main README](../README.md) to install and run it.

When running, interactive API docs are at `http://localhost:8000/docs`.

| Area | Endpoints | Module |
|---|---|---|
| Printers | `/api/printers`, `/api/printers/{id}`, `/api/printers/order` | `main.py` |
| System and server | `/api/health`, `/api/system`, `/api/server`, `/api/server/history` | `main.py` |
| Storage and files | `/api/storage`, `/api/files/*` | `storage.py` |
| Network | `/api/network`, `/api/network/devices`, `/api/network/scan` | `network.py` |
| Services | `/api/services`, `/api/services/docker/{id}/restart` | `services.py` |
| Settings | `/api/settings`, `/api/settings/about`, `/api/settings/backup`, `/api/settings/restore`, `/api/settings/clear-history/{kind}`, `/api/settings/restart` | `settings.py` |

Data is stored in SQLite (`layerhound.db` by default; see `LAYERHOUND_DB`).
