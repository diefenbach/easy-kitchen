from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("shopping", "0018_assign_user_departments")]
    operations = [
        migrations.AlterField(model_name="department", name="user", field=models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE, related_name="departments", to=settings.AUTH_USER_MODEL,
        )),
        migrations.AddConstraint(model_name="department", constraint=models.UniqueConstraint(
            fields=("user", "code"), name="shopping_department_unique_code_per_user",
        )),
    ]
