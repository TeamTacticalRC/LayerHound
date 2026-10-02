# Each test run gets its own empty database and files folder, so tests never touch real data.
import os, sys, tempfile
from pathlib import Path
import pytest

_tmp = Path(tempfile.mkdtemp(prefix="layerhound-test-"))
os.environ["LAYERHOUND_DB"] = str(_tmp / "test.db")
os.environ["LAYERHOUND_FILES"] = str(_tmp / "files")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402  (imported after the environment is set)


@pytest.fixture(scope="session")
def client():
    return TestClient(main.app)


@pytest.fixture(scope="session")
def files_root():
    return Path(os.environ["LAYERHOUND_FILES"])
