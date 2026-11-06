from unittest.mock import patch

import pytest
from django.urls import reverse

from easy_kitchen.models import Article
from easy_kitchen.services import create_item

pytestmark = pytest.mark.django_db


def editor_data(user, **overrides):
    articles = list(user.articles.all())
    data = {"articles-TOTAL_FORMS": str(len(articles)), "articles-INITIAL_FORMS": str(len(articles))}
    for index, article in enumerate(articles):
        data.update({f"articles-{index}-id": str(article.pk), f"articles-{index}-name": article.name,
                     f"articles-{index}-department": article.department_code})
    return data | overrides


def test_all_article_changes_are_saved_together(client, user, shopping_list):
    item = create_item(shopping_list, name="Apple", department="produce")
    removed = Article.objects.create(user=user, name="Bread", department=user.departments.get(code="bread"))
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:articles"), editor_data(user, **{
        "articles-TOTAL_FORMS": "3", "articles-0-name": "Green apple", "articles-0-department": "fresh",
        "articles-1-DELETE": "on", "articles-2-name": " Milk ", "articles-2-department": "dairy",
    }))
    assert response.status_code == 302
    assert list(user.articles.values_list("name", "department__code")) == [("Green apple", "fresh"), ("Milk", "dairy")]
    assert not Article.objects.filter(pk=removed.pk).exists()
    item.refresh_from_db()
    assert item.name == "Apple" and item.department_code == "produce"


@pytest.mark.parametrize("invalid", [
    {"articles-0-name": ""}, {"articles-0-department": "invalid"}, {"articles-0-name": " BREAD "},
])
def test_invalid_drafts_preserve_all_changes_without_partial_save(client, user, invalid):
    Article.objects.create(user=user, name="Apple")
    Article.objects.create(user=user, name="Bread")
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:articles"), editor_data(user, **invalid), HTTP_HX_REQUEST="true")
    assert response.status_code == 422
    assert response["X-Article-Editor"] == "true"
    assert 'id="article-editor-form"' in response.content.decode()
    assert list(user.articles.values_list("name", flat=True)) == ["Apple", "Bread"]


def test_foreign_article_ids_are_rejected(client, user, other_user):
    own = Article.objects.create(user=user, name="Apple")
    foreign = Article.objects.create(user=other_user, name="Private")
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:articles"), editor_data(user, **{
        "articles-0-id": str(foreign.pk), "articles-0-name": "Changed", "articles-0-DELETE": "on",
    }))
    assert response.status_code == 422
    own.refresh_from_db()
    foreign.refresh_from_db()
    assert own.name == "Apple" and foreign.name == "Private"


def test_article_names_can_be_swapped_in_one_save(client, user):
    first = Article.objects.create(user=user, name="Apple")
    second = Article.objects.create(user=user, name="Bread")
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:articles"), editor_data(user, **{
        "articles-0-name": "Bread", "articles-1-name": "Apple",
    }))
    assert response.status_code == 302
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.name == "Bread" and second.name == "Apple"


def test_save_failure_rolls_back_renames_additions_and_deletions(client, user):
    Article.objects.create(user=user, name="Apple")
    Article.objects.create(user=user, name="Bread")
    client.force_login(user)
    with patch("easy_kitchen.services.save_article", side_effect=RuntimeError("Save failed")):
        with pytest.raises(RuntimeError, match="Save failed"):
            client.post(reverse("easy_kitchen:articles"), editor_data(user, **{
                "articles-0-name": "Pear", "articles-1-DELETE": "on",
            }))
    assert list(user.articles.values_list("name", flat=True)) == ["Apple", "Bread"]


@pytest.mark.parametrize("htmx", [False, True])
def test_empty_editor_requires_management_data_and_csrf(client, user, htmx):
    from django.test import Client

    url = reverse("easy_kitchen:articles")
    assert client.get(url).status_code == 302
    client.force_login(user)
    headers = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    assert client.post(url, {}, **headers).status_code == 422
    secured = Client(enforce_csrf_checks=True)
    secured.force_login(user)
    assert secured.post(url, editor_data(user), **headers).status_code == 403
    assert client.post(url, editor_data(user), **headers).status_code == 302


def test_deleted_names_can_be_reused_and_duplicate_ids_are_rejected(client, user):
    article = Article.objects.create(user=user, name="Apple")
    client.force_login(user)
    data = editor_data(user, **{
        "articles-TOTAL_FORMS": "2", "articles-0-DELETE": "on", "articles-1-id": str(article.pk),
        "articles-1-name": "Apple", "articles-1-department": "produce",
    })
    assert client.post(reverse("easy_kitchen:articles"), data).status_code == 422
    data["articles-1-id"] = ""
    assert client.post(reverse("easy_kitchen:articles"), data).status_code == 302
    assert not Article.objects.filter(pk=article.pk).exists()
    assert user.articles.get().department_code == "produce"
