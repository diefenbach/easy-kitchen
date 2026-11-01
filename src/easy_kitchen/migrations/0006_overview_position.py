from django.db import migrations, models


def assign_overview_positions(apps, schema_editor):
    ShoppingList = apps.get_model("shopping", "ShoppingList")
    Recipe = apps.get_model("shopping", "Recipe")
    _number(ShoppingList, ("-date", "-created_at"))
    _number(Recipe, ("-created_at", "-id"))


def _number(model, order):
    user_ids = model.objects.values_list("user_id", flat=True).distinct()
    for user_id in user_ids:
        rows = model.objects.filter(user_id=user_id).order_by(*order)
        for position, row in enumerate(rows, start=1):
            model.objects.filter(pk=row.pk).update(position=position)


class Migration(migrations.Migration):
    dependencies = [
        ("shopping", "0005_recipeingredient_name_quantity"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoppinglist",
            name="position",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="recipe",
            name="position",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(assign_overview_positions, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="shoppinglist",
            options={
                "ordering": ("position", "id"),
                "verbose_name": "shopping list",
                "verbose_name_plural": "shopping lists",
            },
        ),
        migrations.AlterModelOptions(
            name="recipe",
            options={
                "ordering": ("position", "id"),
                "verbose_name": "recipe",
                "verbose_name_plural": "recipes",
            },
        ),
    ]
