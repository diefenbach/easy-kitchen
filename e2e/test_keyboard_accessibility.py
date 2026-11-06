import pytest
from playwright.sync_api import expect

from easy_kitchen.models import Recipe, ShoppingList
from easy_kitchen.services import create_recipe

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize('index', [0, 1, 2])
def test_removed_row_moves_focus(authenticated_page, user, live_server, index):
    recipe = create_recipe(user, title='Soup', ingredients=[{'name': name} for name in ['Onion', 'Salt', 'Water']])
    page = authenticated_page
    page.goto(f'{live_server.url}/recipes/{recipe.pk}/edit/')
    section = page.locator('[data-editor-lines="ingredients"]')
    rows = section.locator('.editor-line:not([hidden])')
    rows.nth(index).get_by_role('button', name='Remove ingredient', exact=True).press('Enter')
    expected = 'Salt' if index == 0 else 'Water' if index == 1 else 'Salt'
    expect(rows.get_by_label('Ingredient', exact=True)).to_have_count(2)
    assert page.evaluate('document.activeElement.value') == expected
    for _ in range(2):
        rows.first.get_by_role('button', name='Remove ingredient', exact=True).press('Enter')
    expect(section.get_by_role('button', name='Add ingredient', exact=True)).to_be_focused()



def test_planner_ignores_composing_enter(authenticated_page, user, live_server):
    create_recipe(user, title='Soup')
    page = authenticated_page
    page.goto(f'{live_server.url}/planner/')
    search = page.locator('.recipe-search').first
    search.fill('Sou')
    search.press('ArrowDown')
    assert search.evaluate("input => input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', isComposing: true, bubbles: true, cancelable: true}))")
    expect(search).to_have_value('Sou')
    expect(page.locator('.recipe-field select').first).to_have_value('')



@pytest.mark.parametrize('kind', ['lists', 'recipes'])
def test_keyboard_reorder_persists_and_rolls_back(authenticated_page, user, live_server, kind):
    model = Recipe if kind == 'recipes' else ShoppingList
    for title in ['First', 'Second', 'Third']:
        model.objects.create(user=user, title=title)
    page = authenticated_page
    page.goto(f'{live_server.url}/{kind}/')
    page.locator('[data-edit-toggle]').click()
    cards = page.locator('[data-card-reorder] > [data-list-id]')
    original = cards.evaluate_all('nodes => nodes.map(node => node.dataset.listId)')
    first = page.locator(f'[data-list-id="{original[0]}"]')
    expect(first.get_by_role('button', name='Move up', exact=True)).to_be_disabled()
    first.get_by_role('button', name='Move down', exact=True).press('Enter')
    expect(cards.first).to_have_attribute('data-list-id', original[1])
    expect(page.locator('[data-card-reorder]')).not_to_have_attribute('aria-busy', 'true')
    page.reload()
    expect(cards.first).to_have_attribute('data-list-id', original[1])
    page.locator('[data-edit-toggle]').click()
    page.route('**/reorder/', lambda route: route.fulfill(status=500, body='Failed'))
    first.get_by_role('button', name='Move up', exact=True).press('Space')
    expect(page.locator('#save-error')).to_be_visible()
    expect(cards.first).to_have_attribute('data-list-id', original[1])
    expect(first.get_by_role('button', name='Move up', exact=True)).to_be_focused()
