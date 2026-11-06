from django.conf import settings
from django.db import migrations


def assign_departments(apps, schema_editor):
    alias = schema_editor.connection.alias
    Department = apps.get_model("shopping", "Department")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Article = apps.get_model("shopping", "Article")
    Item = apps.get_model("shopping", "ShoppingItem")
    catalogue = list(Department.objects.using(alias).order_by("id"))
    for index, user_id in enumerate(User.objects.using(alias).order_by("pk").values_list("pk", flat=True)):
        for original in catalogue:
            if index == 0:
                Department.objects.using(alias).filter(pk=original.pk).update(user_id=user_id)
                department_id = original.pk
            else:
                department_id = Department.objects.using(alias).create(
                    user_id=user_id, code=original.code, name=original.name, position=original.position,
                ).pk
            Article.objects.using(alias).filter(user_id=user_id, department_id=original.pk).update(department_id=department_id)
            Item.objects.using(alias).filter(shopping_list__user_id=user_id, department_id=original.pk).update(department_id=department_id)
    Department.objects.using(alias).filter(user_id__isnull=True).delete()


def restore_shared_catalogue(apps, schema_editor):
    alias = schema_editor.connection.alias
    Department = apps.get_model("shopping", "Department")
    Article = apps.get_model("shopping", "Article")
    Item = apps.get_model("shopping", "ShoppingItem")
    # A shared catalogue can represent each code once; retain the oldest copy.
    canonical = {}
    for department in Department.objects.using(alias).order_by("pk"):
        if department.code not in canonical:
            canonical[department.code] = department.pk
            Department.objects.using(alias).filter(pk=department.pk).update(user_id=None)
        else:
            target = canonical[department.code]
            Article.objects.using(alias).filter(department_id=department.pk).update(department_id=target)
            Item.objects.using(alias).filter(department_id=department.pk).update(department_id=target)
            Department.objects.using(alias).filter(pk=department.pk).delete()


class Migration(migrations.Migration):
    dependencies = [("shopping", "0017_user_departments")]
    operations = [migrations.RunPython(assign_departments, restore_shared_catalogue)]
