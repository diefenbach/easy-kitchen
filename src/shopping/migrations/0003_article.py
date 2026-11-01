from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions


def copy_existing_items(apps, schema_editor):
    ShoppingItem = apps.get_model("shopping", "ShoppingItem")
    Article = apps.get_model("shopping", "Article")
    seen = set()
    items = ShoppingItem.objects.select_related("shopping_list").order_by("id")
    for item in items:
        name = " ".join(item.name.split())
        if not name:
            continue
        key = (item.shopping_list.user_id, name.casefold())
        if key in seen:
            continue
        seen.add(key)
        Article.objects.create(user_id=item.shopping_list.user_id, name=name)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("shopping", "0002_translate_field_labels"),
    ]

    operations = [
        migrations.CreateModel(
            name="Article",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="article")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="articles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "article",
                "verbose_name_plural": "articles",
                "ordering": ("name", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="article",
            constraint=models.UniqueConstraint(
                django.db.models.functions.Lower("name"),
                models.F("user"),
                name="shopping_article_unique_name_per_user",
            ),
        ),
        migrations.RunPython(copy_existing_items, migrations.RunPython.noop),
    ]
