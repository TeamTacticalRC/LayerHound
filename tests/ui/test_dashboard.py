# What an owner sees and does in the dashboard, checked in a real browser.
import pytest
from conftest import PAGES, api, new_page, open_page


def no_sideways_scroll(page):
    width, window = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    return width <= window + 1


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "phone"])
def test_every_page_opens_cleanly(browser, base_url, admin_state, theme, mobile):
    page = new_page(browser, base_url, admin_state, mobile=mobile, theme=theme)
    assert page.evaluate("document.documentElement.classList.contains('lh-light')") == (theme == "light")
    for name in PAGES:
        open_page(page, name, mobile)
        heading = "Print History" if name == "History" else "Send feedback" if name == "Send feedback" else name
        if name != "Dashboard":
            page.get_by_role("heading", name=heading, exact=True).first.wait_for()
        assert no_sideways_scroll(page), f"{name} scrolls sideways ({theme}, {'phone' if mobile else 'desktop'})"
    assert not page.problems.items, page.problems.items
    page.context.close()


def test_add_and_remove_a_printer(browser, base_url, admin_state):
    page = new_page(browser, base_url, admin_state)
    open_page(page, "Print Farm")
    page.get_by_role("button", name="Add printer").first.click()
    page.get_by_role("textbox", name="Name", exact=True).fill("Bench Klipper")
    page.get_by_role("textbox", name="IP address or hostname").fill("127.0.0.1")
    page.get_by_role("textbox", name="Port").fill("1")   # nothing listens there
    page.get_by_role("dialog").get_by_role("button", name="Add printer").click()
    card = page.get_by_role("button").filter(has_text="Bench Klipper").filter(has_text="Details")
    card.wait_for()
    card.click()
    page.get_by_text("Printer detail").wait_for()
    page.get_by_text("Offline", exact=True).first.wait_for()
    # Owners see a plain reason, not a Python error
    assert "Errno" not in page.content() and "URLError" not in page.content()
    page.get_by_role("button", name="Remove printer").click()
    page.get_by_role("button", name="Remove printer").last.click()
    page.get_by_text("No printers yet").wait_for()
    assert not page.problems.items, page.problems.items
    page.context.close()


def test_theme_choice_survives_a_reload(browser, base_url, admin_state):
    page = new_page(browser, base_url, admin_state, theme="dark")
    page.get_by_role("radio", name="Light").first.click()
    assert page.evaluate("document.documentElement.classList.contains('lh-light')")
    page.reload(); page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.classList.contains('lh-light')")
    page.context.close()


def test_view_only_account_sees_no_admin_controls(browser, base_url, admin_state):
    admin = new_page(browser, base_url, admin_state)
    assert api(admin, "POST", "/api/auth/users", {"username": "staff", "password": "staff-pass-123", "role": "viewer"})["status"] == 200
    admin.context.close()
    page = new_page(browser, base_url)
    page.locator("input").first.fill("staff")
    page.locator("input[type=password]").fill("staff-pass-123")
    page.get_by_role("button", name="Sign in").click()
    page.get_by_text("View only").first.wait_for()
    for name in PAGES:
        open_page(page, name)
        shown = page.evaluate("[...document.querySelectorAll('[data-admin]')].filter(e => e.offsetParent !== null).length")
        assert shown == 0, f"{name}: {shown} admin controls visible to a viewer"
        for label in ("Add printer", "Add service", "Add device", "Restart dashboard", "Shut down board", "Update now", "Save"):
            assert not page.get_by_role("button", name=label, exact=True).filter(visible=True).count(), f'{name}: "{label}" visible to a viewer'
    assert not page.problems.items, page.problems.items
    page.context.close()


def test_sign_out(browser, base_url, admin_state):
    page = new_page(browser, base_url, admin_state)
    page.get_by_role("button", name="Sign out").click()
    page.get_by_role("button", name="Sign in").wait_for()
    page.context.close()
