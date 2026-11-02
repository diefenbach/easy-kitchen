from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shopping", "0010_shoppinglist_icon_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoppinglist",
            name="hide_completed_items",
            field=models.BooleanField(default=False, verbose_name="hide completed items"),
        ),
    ]
