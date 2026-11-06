import pytest
from playwright.sync_api import expect

from easy_kitchen.services import create_recipe

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_private_history_and_logout_cache_cleanup(authenticated_page, user, other_user, live_server):
    recipe = create_recipe(user, title='Private marker recipe', ingredients=[{'name': 'Private marker ingredient'}])
    page = authenticated_page
    page.goto(f'{live_server.url}/recipes/{recipe.pk}/')
    page.evaluate("localStorage.setItem('unrelated', 'keep')")
    page.get_by_role('link', name='Edit recipe', exact=True).click()
    expect(page.get_by_label('Title', exact=True)).to_have_value(recipe.title)
    assert 'Private marker' not in page.evaluate("localStorage.getItem('htmx-history-cache') || ''")
    page.get_by_role('link', name='Cancel', exact=True).first.click()
    expect(page.get_by_role('heading', name=recipe.title, exact=True)).to_be_visible()
    page.evaluate("localStorage.setItem('htmx-history-cache', 'legacy private cache')")
    page.get_by_role('button', name=user.username, exact=True).click()
    page.get_by_role('button', name='Log out', exact=True).click()
    expect(page.get_by_role('button', name='Sign in', exact=True)).to_be_visible()
    assert page.evaluate("localStorage.getItem('htmx-history-cache')") is None
    assert page.evaluate("localStorage.getItem('unrelated')") == 'keep'
    page.go_back()
    expect(page.get_by_role('button', name='Sign in', exact=True)).to_be_visible()
    page.get_by_label('Username').fill(other_user.username)
    page.get_by_label('Password').fill('test-password')
    page.get_by_role('button', name='Sign in', exact=True).click()
    expect(page.get_by_role('heading', name='Not Found', exact=True)).to_be_visible()
    assert 'Private marker' not in page.content()
    assert page.evaluate("localStorage.getItem('htmx-history-cache')") is None
