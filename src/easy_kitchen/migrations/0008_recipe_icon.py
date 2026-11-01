from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shopping", "0007_recipe_nutrition"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipe",
            name="icon",
            field=models.CharField(
                choices=[
                    ("egg", "Fried egg"),
                    ("cup", "Drink"),
                    ("basket", "Basket"),
                    ("flower", "Flower"),
                    ("fire", "Flame"),
                ],
                default="egg",
                max_length=20,
                verbose_name="icon",
            ),
        ),
    ]
