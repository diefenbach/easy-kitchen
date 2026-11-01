from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shopping", "0008_recipe_icon"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="recipe",
            name="icon",
        ),
        migrations.AddField(
            model_name="shoppinglist",
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
