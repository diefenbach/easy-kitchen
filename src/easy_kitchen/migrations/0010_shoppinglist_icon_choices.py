from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shopping", "0009_shoppinglist_icon"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shoppinglist",
            name="icon",
            field=models.CharField(
                choices=[
                    ("basket", "Basket"),
                    ("cart", "Cart"),
                    ("bag", "Bag"),
                    ("egg", "Fried egg"),
                    ("cup", "Drink"),
                    ("apple", "Apple"),
                    ("cookie", "Cookie"),
                    ("cake", "Cake"),
                    ("droplet", "Drop"),
                    ("flower", "Flower"),
                    ("fire", "Flame"),
                    ("snow", "Frozen"),
                    ("house", "Home"),
                    ("gift", "Gift"),
                    ("heart", "Heart"),
                ],
                default="basket",
                max_length=20,
                verbose_name="icon",
            ),
        ),
    ]
