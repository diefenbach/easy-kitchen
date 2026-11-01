from django.db import migrations, models


def split_ingredient_text(apps, schema_editor):
    from shopping.services import _ingredient_name_and_quantity

    Ingredient = apps.get_model("shopping", "RecipeIngredient")
    for ingredient in Ingredient.objects.all():
        name, quantity = _ingredient_name_and_quantity(ingredient.text)
        ingredient.name = name or ingredient.text
        ingredient.quantity = quantity
        ingredient.save(update_fields=["name", "quantity"])


class Migration(migrations.Migration):
    dependencies = [
        ("shopping", "0004_recipe_recipeingredient_recipestep"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipeingredient",
            name="name",
            field=models.CharField(blank=True, max_length=255, verbose_name="ingredient"),
        ),
        migrations.AddField(
            model_name="recipeingredient",
            name="quantity",
            field=models.CharField(blank=True, max_length=100, verbose_name="quantity"),
        ),
        migrations.RunPython(split_ingredient_text, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="recipeingredient",
            name="name",
            field=models.CharField(max_length=255, verbose_name="ingredient"),
        ),
        migrations.RemoveField(
            model_name="recipeingredient",
            name="text",
        ),
    ]
