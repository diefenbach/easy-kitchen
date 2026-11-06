import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("kind", ["article", "department"])
def test_collection_controls_wait_for_the_editor_module(authenticated_page, user, live_server, kind):
    if kind == "article":
        user.articles.create(name="Existing article")
    page = authenticated_page
    module = f"**/static/easy_kitchen/{kind}-editor.js"
    page.route(module, lambda route: route.abort())
    page.goto(f"{live_server.url}/{kind}s/")
    form = page.locator(f"#{kind}-editor-form")
    add = form.get_by_role("button", name=f"Add {kind}", exact=True)
    remove = form.get_by_role("button", name=f"Remove {kind}", exact=True).first
    expect(add).to_be_disabled()
    expect(remove).to_be_disabled()

    page.unroute(module)
    page.reload()
    expect(add).to_be_enabled()
    expect(remove).to_be_enabled()
    before = form.locator(".editor-line:not([hidden])").count()
    add.click()
    expect(form.locator(".editor-line:not([hidden])")).to_have_count(before + 1)
