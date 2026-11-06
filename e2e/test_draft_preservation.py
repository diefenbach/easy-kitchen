import io

from PIL import Image
import pytest
from playwright.sync_api import expect

from easy_kitchen.models import ShoppingList
from easy_kitchen.services import create_recipe

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize('kind', ['recipes', 'lists', 'items'])
@pytest.mark.parametrize('failure', ['server', 'network'])
def test_pending_forms_lock_drafts_and_restore_after_failure(authenticated_page, user, live_server, kind, failure):
    page = authenticated_page
    if kind == 'recipes':
        record = create_recipe(user, title='Soup', ingredients=[{'name': 'Onion'}])
    else:
        record = ShoppingList.objects.create(user=user, title='Market')
    path = f'/{"lists" if kind == "items" else kind}/{record.pk}/'
    page.goto(live_server.url + path + ('' if kind == 'items' else 'edit/'))
    field = page.get_by_role('combobox', name='Item', exact=True) if kind == 'items' else page.get_by_label('Title', exact=True)
    field.fill('Submitted draft')
    held = []
    page.route('**' + path + ('items/' if kind == 'items' else 'edit/'), lambda route: held.append(route))
    page.get_by_role('button', name='Add' if kind == 'items' else 'Save', exact=True).first.click()
    expect(field).to_be_disabled()
    assert len(held) == 1
    if kind != 'items':
        cancel = page.get_by_role('link', name='Cancel', exact=True).first
        expect(cancel).to_have_attribute('aria-disabled', 'true')
        cancel.click(force=True)
        expect(page).to_have_url(live_server.url + path + 'edit/')
    if failure == 'network':
        held[0].abort()
    else:
        held[0].fulfill(status=500, body='Save failed')
    expect(page.locator('#save-error')).to_be_visible()
    expect(field).to_be_enabled()
    expect(field).to_have_value('Submitted draft')
    page.unroute_all()
    page.get_by_role('button', name='Add' if kind == 'items' else 'Save', exact=True).first.click()
    if kind == 'items':
        expect(page.locator('.shopping-item')).to_contain_text('Submitted draft')
        expect(field).to_have_value('')
        expect(page.locator('#save-error')).to_be_hidden()
    else:
        expect(page.get_by_role('heading', name='Submitted draft', exact=True)).to_be_visible()



def test_image_survives_validation_and_corrected_save(authenticated_page, user, live_server, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    recipe = create_recipe(user, title='Soup')
    page = authenticated_page
    page.goto(f'{live_server.url}/recipes/{recipe.pk}/edit/')
    picture = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(picture, format='PNG')
    page.get_by_label('Image', exact=True).set_input_files({'name': 'draft.png', 'mimeType': 'image/png', 'buffer': picture.getvalue()})
    page.get_by_label('Title', exact=True).fill('')
    page.locator('#recipe-editor-form').evaluate('form => { form.noValidate = true; }')
    page.get_by_role('button', name='Save', exact=True).first.click()
    expect(page.get_by_role('alert')).to_contain_text('Your changes have not been saved.')
    assert page.get_by_label('Image', exact=True).evaluate('input => input.files.length') == 1
    page.get_by_label('Title', exact=True).fill('Corrected soup')
    page.get_by_role('button', name='Save', exact=True).first.click()
    expect(page.get_by_role('heading', name='Corrected soup', exact=True)).to_be_visible()
    recipe.refresh_from_db()
    assert recipe.image and recipe.image.storage.exists(recipe.image.name)
