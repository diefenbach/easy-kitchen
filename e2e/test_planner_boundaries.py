import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_calendar_boundary_navigation_stays_in_supported_weeks(authenticated_page, live_server):
    page = authenticated_page
    for week, missing, present in [("0001-01-01", "Previous week", "Next week"),
                                    ("9999-12-20", "Next week", "Previous week")]:
        page.goto(f"{live_server.url}/planner/?week={week}")
        expect(page.locator(".planner-day")).to_have_count(7)
        expect(page.get_by_role("link", name=missing, exact=True)).to_have_count(0)
        expect(page.get_by_role("link", name=present, exact=True)).to_be_visible()
        page.get_by_role("link", name=present, exact=True).click()
        expect(page.locator(".planner-day")).to_have_count(7)
