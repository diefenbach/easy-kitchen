from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shopping", "0012_recipe_carbohydrates_fat"),
    ]

    operations = [
        migrations.CreateModel(
            name="MealPlanEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("date", models.DateField(verbose_name="date")),
                (
                    "recipe",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.CASCADE,
                        related_name="meal_plan_entries",
                        to="shopping.recipe",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="meal_plan_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "meal plan entry",
                "verbose_name_plural": "meal plan entries",
                "ordering": ("date",),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "date"), name="shopping_mealplanentry_unique_user_date"
                    ),
                ],
            },
        ),
    ]
