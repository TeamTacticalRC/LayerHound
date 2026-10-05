# Frontend tests: a real browser drives a throwaway copy of LayerHound with an empty database.
#   npm run build
#   backend/.venv/bin/pip install -r tests/ui/requirements.txt
#   backend/.venv/bin/python -m pytest -q tests/ui
# On a Mac this uses your installed Google Chrome. On CI (or with LAYERHOUND_UI_BUNDLED=1) it uses
# Playwright's own Chromium: run "python -m playwright install chromium" once first.
import os, secrets, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ADMIN = {"username": "admin", "password": "ui-" + secrets.token_hex(8)}   # throwaway, this test run only
PAGES = ["Dashboard", "Print Farm", "History", "Server", "Storage", "Network", "Services", "Settings", "Send feedback"]
HEADERS = {"Content-Type": "application/json", "X-Requested-With": "LayerHound"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    if not (ROOT / "dist" / "index.html").exists():
        pytest.exit("Build the dashboard first: npm run build", returncode=1)
    tmp = Path(tempfile.mkdtemp(prefix="layerhound-ui-"))
    port = free_port()
    env = {**os.environ, "LAYERHOUND_DB": str(tmp / "ui.db"), "LAYERHOUND_FILES": str(tmp / "files")}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
                              cwd=ROOT / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try: urllib.request.urlopen(url + "/api/health", timeout=1); break
        except Exception:
            if server.poll() is not None: pytest.exit("LayerHound didn't start: " + server.stderr.read().decode()[-500:], returncode=1)
            time.sleep(0.5)
    yield url
    server.terminate(); server.wait(10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        bundled = os.environ.get("CI") or os.environ.get("LAYERHOUND_UI_BUNDLED")
        b = p.chromium.launch(headless=True) if bundled else p.chromium.launch(channel="chrome", headless=True)
        yield b
        b.close()


class Problems:
    """Collects JavaScript errors and failed requests while a page is in use."""
    def __init__(self, page):
        self.items = []
        page.on("pageerror", lambda e: self.items.append(f"crash: {e}"))
        page.on("console", lambda m: m.type == "error" and self.items.append(f"console: {m.text}"))
        page.on("response", lambda r: r.status >= 500 and self.items.append(f"server {r.status}: {r.url}"))


def new_page(browser, base_url, state=None, mobile=False, theme=None):
    vp = {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900}
    ctx = browser.new_context(viewport=vp, storage_state=state, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    # Starting theme for this browser; a choice made during the test still wins after a reload
    if theme: page.add_init_script(f"if (!localStorage.getItem('lh-theme')) localStorage.setItem('lh-theme', '{theme}')")
    page.problems = Problems(page)
    page.goto(base_url); page.wait_for_load_state("networkidle")
    return page


def open_page(page, name, mobile=False):
    if mobile:
        page.get_by_role("button", name="Open menu").click()
    page.get_by_role("button", name=name, exact=True).first.click()
    page.wait_for_load_state("networkidle")


def api(page, method, path, body=None):
    return page.evaluate("""async ([m, path, body, h]) => {
        const r = await fetch(path, {method: m, headers: h, body: body ? JSON.stringify(body) : undefined});
        return {status: r.status, body: await r.json().catch(() => null)}; }""", [method, path, body, HEADERS])


@pytest.fixture(scope="session")
def admin_state(browser, base_url):
    """First-run setup through the welcome screen, as a new owner would. Returns the signed-in session."""
    page = new_page(browser, base_url)
    page.get_by_role("heading", name="Welcome to LayerHound").wait_for()
    page.get_by_placeholder("My Print Farm").fill("UI Test Farm")
    passwords = page.locator("input[type=password]")
    passwords.nth(0).fill(ADMIN["password"]); passwords.nth(1).fill(ADMIN["password"])
    page.get_by_role("button", name="Finish setup").click()
    page.get_by_role("heading", name="UI Test Farm").wait_for()
    assert not page.problems.items, page.problems.items
    state = page.context.storage_state()
    page.context.close()
    return state
