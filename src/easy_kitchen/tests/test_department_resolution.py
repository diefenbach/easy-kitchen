import json
from datetime import date

import pytest
from django.urls import reverse
from django.utils.translation import override
from mcp.server.mcpserver.exceptions import ToolError
from rest_framework.authtoken.models import Token

from easy_kitchen.models import Department, ShoppingList
from easy_kitchen.services import create_item, resolve_department
from easy_kitchen.tests.test_mcp import authorization_context

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("value, code", [
    ("produce", "produce"), ("  FRUIT  & Vegetables  ", "produce"),
    ("Obst und Gemüse", "produce"), ("Obst / Gemuese", "produce"),
    ("Oil and sauces", "oil_sauces"), ("Öl & Soßen", "oil_sauces"),
    ("Getraenke", "drinks"), ("Tiefkühlwaren", "frozen"),
])
def test_department_codes_names_and_translations_resolve_independently_of_ui_language(user, value, code):
    with override("en"):
        department = resolve_department(user, value)
    assert department.code == code
    assert department.user_id == user.pk


def test_similar_department_names_are_suggested_but_never_assigned(user, other_user, shopping_list):
    from easy_kitchen.services import DepartmentResolutionError

    other_user.departments.create(code="private", name="Obst private")
    with pytest.raises(DepartmentResolutionError) as caught:
        create_item(shopping_list, name="Apple", department="Obst")
    detail = caught.value.as_dict()
    assert detail["code"] == "department_not_found"
    assert "produce" in [candidate["code"] for candidate in detail["candidates"]]
    assert "private" not in [candidate["code"] for candidate in detail["candidates"]]
    assert not shopping_list.items.exists()
    assert not user.articles.exists()


def test_ambiguous_translation_returns_both_candidates_but_exact_code_wins(user):
    from easy_kitchen.services import DepartmentResolutionError

    duplicate = user.departments.create(code="custom-produce", name="Obst und Gemüse")
    with pytest.raises(DepartmentResolutionError) as caught:
        resolve_department(user, "Obst & Gemüse")
    assert caught.value.as_dict()["code"] == "department_ambiguous"
    assert {candidate["code"] for candidate in caught.value.as_dict()["candidates"]} == {"produce", duplicate.code}
    assert resolve_department(user, "produce").code == "produce"


def test_renamed_departments_keep_their_code_but_do_not_match_old_translations(user):
    from easy_kitchen.services import DepartmentResolutionError

    user.departments.filter(code="produce").update(name="My fresh section")
    assert resolve_department(user, "produce").name == "My fresh section"
    assert resolve_department(user, "my FRESH section").code == "produce"
    with pytest.raises(DepartmentResolutionError):
        resolve_department(user, "Obst & Gemüse")


def test_api_lists_and_resolves_only_own_departments(client, user, other_user):
    token = Token.objects.create(user=user)
    headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
    private = other_user.departments.create(code="private", name="Private")
    url = reverse("department-list")
    assert client.get(url).status_code in (401, 403)
    response = client.get(url, **headers)
    assert response.status_code == 200
    assert len(response.json()) == 21
    assert private.pk not in {entry["id"] for entry in response.json()}
    assert {"id", "code", "name", "label"} == set(response.json()[0])
    response = client.get(reverse("department-resolve"), {"query": "Obst und Gemüse"}, **headers)
    assert response.status_code == 200
    assert response.json()["code"] == "produce"
    response = client.get(reverse("department-resolve"), {"query": "Private"}, **headers)
    assert response.status_code == 400
    assert "private" not in {entry["code"] for entry in response.json()["department"]["candidates"]}
    assert client.post(url, {"name": "New"}, **headers).status_code == 405


def test_api_accepts_names_and_reports_candidates_without_partial_writes(client, user):
    token = Token.objects.create(user=user)
    headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
    url = reverse("shopping-list-list")
    response = client.post(url, {"title": "Shop", "date": date.today().isoformat(), "items": [{"name": "Apple", "department": "Obst und Gemüse"}]}, content_type="application/json", **headers)
    assert response.status_code == 201
    assert response.json()["items"][0]["department"] == "produce"
    original = user.shopping_lists.get()
    before = list(user.shopping_lists.values_list("pk", "position"))
    response = client.post(url, {"title": "Unresolved", "date": date.today().isoformat(), "items": [{"name": "Milk", "department": "dairy"}, {"name": "Pear", "department": "Obst"}]}, content_type="application/json", **headers)
    assert response.status_code == 400
    detail = response.json()["items"][1]["department"]
    assert detail["code"] == "department_not_found"
    assert "produce" in [entry["code"] for entry in detail["candidates"]]
    assert list(user.shopping_lists.values_list("pk", "position")) == before
    response = client.patch(reverse("shopping-list-detail", args=[original.pk]), {"title": "Must not change", "items": [{"name": "Pear", "department": "Obst"}]}, content_type="application/json", **headers)
    assert response.status_code == 400
    original.refresh_from_db()
    assert original.title == "Shop" and original.items.get().name == "Apple"


def test_mcp_listing_resolution_and_unresolved_writes_are_private_and_atomic(user, other_user):
    from easy_kitchen.mcp_server import list_departments, resolve_department as mcp_resolve, add_item_to_list, create_shopping_list

    ctx = authorization_context(Token.objects.create(user=user))
    private = other_user.departments.create(code="private", name="Obst private")
    assert private.pk not in {entry["id"] for entry in list_departments(ctx)}
    assert mcp_resolve("Obst und Gemüse", ctx)["code"] == "produce"
    with pytest.raises(ToolError) as caught:
        add_item_to_list(name="Apple", department="Obst", ctx=ctx)
    detail = json.loads(str(caught.value))
    assert detail["code"] == "department_not_found"
    assert "produce" in [entry["code"] for entry in detail["candidates"]]
    assert "private" not in [entry["code"] for entry in detail["candidates"]]
    assert not user.shopping_lists.exists()
    with pytest.raises(ToolError):
        create_shopping_list(title="Bad", date=date.today(), items=[{"name": "Milk", "department": "dairy"}, {"name": "Apple", "department": "Obst"}], ctx=ctx)
    assert not user.shopping_lists.exists()
    assert not user.articles.exists()
    result = add_item_to_list(name="Apple", department="Obst und Gemüse", ctx=ctx)
    assert result["department"] == "produce"
    assert ShoppingList.objects.get(pk=result["list_id"]).user_id == user.pk
    assert Department.objects.filter(user=user).count() == 21


def test_omitting_department_keeps_default_and_empty_string_clears_it(client, user, shopping_list):
    from easy_kitchen.mcp_server import add_item_to_list

    source = create_item(shopping_list, name="Milk", department="dairy")
    token = Token.objects.create(user=user)
    headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
    for department, expected in [(None, "dairy"), ("", "")]:
        item = {"name": "Milk"}
        if department is not None:
            item["department"] = department
        response = client.post(reverse("shopping-list-list"), {"title": "Another", "date": date.today().isoformat(), "items": [item]}, content_type="application/json", **headers)
        assert response.status_code == 201
        assert response.json()["items"][0]["department"] == expected
    user.articles.filter(name="Milk").update(department=source.department)
    ctx = authorization_context(token)
    assert add_item_to_list(name="Milk", list_id=shopping_list.pk, ctx=ctx)["department"] == "dairy"
    assert add_item_to_list(name="Milk", department="", list_id=shopping_list.pk, ctx=ctx)["department"] == ""


@pytest.mark.django_db(transaction=True)
def test_registered_mcp_tools_accept_long_translations_and_return_candidate_errors(user):
    from asgiref.sync import async_to_sync
    from easy_kitchen.mcp_server import mcp

    ctx = authorization_context(Token.objects.create(user=user))
    call = async_to_sync(mcp._tool_manager.call_tool)
    assert len(call("list_departments", {}, ctx)) == 21
    result = call("resolve_department", {"name": "Kosmetik & Körperpflege"}, ctx)
    assert result["code"] == "personal_care"
    result = call("add_item_to_list", {"name": "Shampoo", "department": "Kosmetik & Körperpflege"}, ctx)
    assert result["department"] == "personal_care"
    before = list(user.shopping_lists.values_list("pk", "position"))
    with pytest.raises(ToolError) as caught:
        call("add_item_to_list", {"name": "Apple", "department": "Obst"}, ctx)
    message = str(caught.value)
    detail = json.loads(message[message.index("{"):])
    assert detail["code"] == "department_not_found"
    assert "produce" in [entry["code"] for entry in detail["candidates"]]
    assert list(user.shopping_lists.values_list("pk", "position")) == before
    assert not user.articles.filter(name="Apple").exists()
