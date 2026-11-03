from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shopping", "0011_shoppinglist_hide_completed_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipe",
            name="carbohydrates",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="carbohydrates"
            ),
        ),
        migrations.AddField(
            model_name="recipe",
            name="fat",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="fat"),
        ),
    ]
