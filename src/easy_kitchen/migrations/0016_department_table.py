from django.db import migrations, models
import django.db.models.deletion
from django.utils.translation import gettext_noop as _


INITIAL_DEPARTMENTS = [
    ('produce', _('Fruit & vegetables')),
    ('fresh', _('Fresh food')),
    ('meat', _('Meat & sausages')),
    ('bread', _('Bread')),
    ('dairy', _('Dairy products')),
    ('fish', _('Fish')),
    ('oil_sauces', _('Oil & sauces')),
    ('spices', _('Spices')),
    ('pasta_rice', _('Pasta & rice')),
    ('canned', _('Canned food')),
    ('baking', _('Baking ingredients')),
    ('breakfast', _('Breakfast')),
    ('frozen', _('Frozen food')),
    ('sweets_snacks', _('Sweets & snacks')),
    ('personal_care', _('Cosmetics & personal care')),
    ('baby', _('Baby')),
    ('cleaning', _('Cleaning products')),
    ('household', _('Household goods')),
    ('pets', _('Pet supplies')),
    ('stationery', _('Stationery')),
    ('drinks', _('Drinks')),
]


def seed_departments(apps, schema_editor):
    Department = apps.get_model("shopping", "Department")
    alias = schema_editor.connection.alias
    for position, (code, name) in enumerate(INITIAL_DEPARTMENTS, start=1):
        Department.objects.using(alias).get_or_create(code=code, defaults={"name": name, "position": position})


def migrate_assignments(apps, schema_editor):
    seed_departments(apps, schema_editor)
    Department = apps.get_model("shopping", "Department")
    alias = schema_editor.connection.alias
    for model_name in ("Article", "ShoppingItem"):
        model = apps.get_model("shopping", model_name)
        codes = model.objects.using(alias).exclude(legacy_department="").values_list("legacy_department", flat=True).distinct()
        for code in codes:
            department = Department.objects.using(alias).get(code=code)
            model.objects.using(alias).filter(legacy_department=code).update(department_id=department.pk)


def reverse_assignments(apps, schema_editor):
    Department = apps.get_model("shopping", "Department")
    alias = schema_editor.connection.alias
    for model_name in ("Article", "ShoppingItem"):
        model = apps.get_model("shopping", model_name)
        for department in Department.objects.using(alias).all():
            model.objects.using(alias).filter(department_id=department.pk).update(legacy_department=department.code)


class Migration(migrations.Migration):
    dependencies = [("shopping", "0015_article_department_shoppingitem_department")]

    operations = [
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=20, unique=True, verbose_name="code")),
                ("name", models.CharField(max_length=100, verbose_name="name")),
                ("position", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ("position", "id"), "verbose_name": "Department", "verbose_name_plural": "Departments"},
        ),
        migrations.RenameField(model_name="article", old_name="department", new_name="legacy_department"),
        migrations.RenameField(model_name="shoppingitem", old_name="department", new_name="legacy_department"),
        migrations.AddField(
            model_name="article", name="department",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="articles", to="shopping.department", verbose_name="Department"),
        ),
        migrations.AddField(
            model_name="shoppingitem", name="department",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="items", to="shopping.department", verbose_name="Department"),
        ),
        migrations.RunPython(migrate_assignments, reverse_assignments),
        migrations.RemoveField(model_name="article", name="legacy_department"),
        migrations.RemoveField(model_name="shoppingitem", name="legacy_department"),
    ]
