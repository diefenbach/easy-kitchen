from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("shopping", "0016_department_table"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(model_name="department", name="code", field=models.SlugField(max_length=20, verbose_name="code")),
        migrations.AddField(model_name="department", name="user", field=models.ForeignKey(
            null=True, on_delete=django.db.models.deletion.CASCADE, related_name="departments", to=settings.AUTH_USER_MODEL,
        )),
    ]
