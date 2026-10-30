# Generated manually for the initial EasyList schema.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="ShoppingList",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_lists", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-date", "-created_at")},
        ),
        migrations.CreateModel(
            name="ShoppingItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("quantity", models.CharField(blank=True, max_length=100)),
                ("checked", models.BooleanField(default=False)),
                ("position", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("shopping_list", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="shopping.shoppinglist")),
            ],
            options={"ordering": ("position", "id")},
        ),
    ]
