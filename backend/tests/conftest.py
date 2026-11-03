# Each test run gets its own empty database and files folder, so tests never touch real data.
import os, sys, tempfile
from pathlib import Path
import pytest

_tmp = Path(tempfile.mkdtemp(prefix="layerhound-test-"))
os.environ["LAYERHOUND_DB"] = str(_tmp / "test.db")
os.environ["LAYERHOUND_FILES"] = str(_tmp / "files")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
import auth, main  # noqa: E402  (imported after the environment is set)

# The test client's address is "testclient" rather than an IP; treat it as the local network
_is_local = auth.is_local
auth.is_local = lambda host: host == "testclient" or _is_local(host)

ADMIN = {"username": "owner", "password": "correct horse battery"}
HEADERS = {"X-Requested-With": "LayerHound"}


# One event loop for the whole run. By default the test client starts a fresh loop for each request
# and stops it afterwards, which strands background work (like a printer upload finishing after its
# request has answered). Sharing one loop keeps it running, without starting the app's own samplers.
from anyio.from_thread import start_blocking_portal  # noqa: E402
_portal_cm = start_blocking_portal()
_portal = _portal_cm.__enter__()


def pytest_sessionfinish(session, exitstatus):
    # Stop the shared loop (and any upload results still waiting out RESULT_KEEP), or the run never exits
    _portal.call(_cancel_background)
    _portal_cm.__exit__(None, None, None)


async def _cancel_background():
    for t in list(main.background): t.cancel()


def new_client():
    c = TestClient(main.app, headers=HEADERS)
    c.portal = _portal
    return c


@pytest.fixture(scope="session")
def client():
    # Signed in as the admin made by first-run setup
    c = new_client()
    r = c.post("/api/auth/setup", json={"farm_name": "Test Farm", **ADMIN})
    assert r.status_code == 200, r.text
    c.recovery_key = r.json()["recovery_key"]   # shown once at setup
    return c


@pytest.fixture(scope="session")
def files_root():
    return Path(os.environ["LAYERHOUND_FILES"])
