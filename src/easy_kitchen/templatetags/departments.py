from django import template
from django.utils.translation import gettext as _

from easy_kitchen.departments import department_choices as sorted_department_choices

register = template.Library()


@register.simple_tag
def department_groups(shopping_list):
    """Keep the saved item order within each nonempty department."""
    departments = list(shopping_list.user.departments.all())
    groups = {department.pk: [] for department in departments}
    groups[None] = []
    for item in shopping_list.items.all():
        groups[item.department_id].append(item)
    labels = {department.pk: str(department) for department in departments}
    labels[None] = _("Without department")
    codes = {department.pk: department.code for department in departments}
    codes[None] = ""
    return [{"value": codes[key], "label": labels[key], "items": items}
            for key, items in groups.items() if items]


@register.simple_tag
def department_choices(user):
    return sorted_department_choices(user)
