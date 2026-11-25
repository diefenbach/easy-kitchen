import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

PACKAGES = json.loads((Path(__file__).resolve().parents[1] / "package.json").read_text())["devDependencies"]


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_vendor_assets_work_without_external_requests(page, live_server, user):
    local_errors = []
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("response", lambda response: local_errors.append(response.url)
            if response.url.startswith(live_server.url + "/static/") and response.status >= 400
            else None)
    page.route("**/*", lambda route: route.continue_()
               if route.request.url.startswith(live_server.url + "/") else route.abort())

    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_label("Email").fill(user.email)
    page.get_by_label("Password").fill("test-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("heading", name="Shopping lists")).to_be_visible()
    page.wait_for_load_state("domcontentloaded")

    assert page.evaluate("htmx.version") == PACKAGES["htmx.org"]
    assert page.evaluate("Sortable.version") == PACKAGES["sortablejs"]
    assert page.evaluate("bootstrap.Dropdown.VERSION") == PACKAGES["bootstrap"]
    assert page.evaluate("document.fonts.load('16px bootstrap-icons').then(fonts => fonts.length)") == 1

    page.get_by_role("button", name=user.email, exact=True).click()
    expect(page.get_by_role("link", name="Import JSON", exact=True)).to_be_visible()
    assert local_errors == []
    assert page_errors == []
