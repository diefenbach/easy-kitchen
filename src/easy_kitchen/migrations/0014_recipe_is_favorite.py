from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shopping", "0013_mealplanentry")]

    operations = [
        migrations.AddField(
            model_name="recipe",
            name="is_favorite",
            field=models.BooleanField(default=False, verbose_name="favorite"),
        ),
    ]
