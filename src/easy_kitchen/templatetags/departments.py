from django import template
from django.utils.translation import gettext as _

from easy_kitchen.departments import Department, department_choices as sorted_department_choices

register = template.Library()


@register.simple_tag
def department_groups(shopping_list):
    """Keep the saved item order within each nonempty department."""
    groups = {key: [] for key in [*Department.values, ""]}
    for item in shopping_list.items.all():
        groups[item.department].append(item)
    labels = dict(Department.choices)
    labels[""] = _("Without department")
    return [{"value": key, "label": labels[key], "items": items}
            for key, items in groups.items() if items]


@register.simple_tag
def department_choices():
    return sorted_department_choices()
