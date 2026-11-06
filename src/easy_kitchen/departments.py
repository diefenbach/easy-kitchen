import unicodedata

from django.utils.translation import gettext_lazy as _


def department_choices():
    """Sort the database catalogue by translated labels, folding accents and umlauts."""
    from .models import Department

    def sort_key(department):
        label = unicodedata.normalize("NFKD", str(department).casefold())
        return "".join(character for character in label if not unicodedata.combining(character))

    return [("", _("Without department")),
            *[(department.code, str(department)) for department in sorted(Department.objects.all(), key=sort_key)]]
