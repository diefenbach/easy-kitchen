import unicodedata

from django.utils.translation import gettext_lazy as _, gettext_noop


DEFAULT_DEPARTMENTS = [
    ('produce', gettext_noop('Fruit & vegetables')),
    ('fresh', gettext_noop('Fresh food')),
    ('meat', gettext_noop('Meat & sausages')),
    ('bread', gettext_noop('Bread')),
    ('dairy', gettext_noop('Dairy products')),
    ('fish', gettext_noop('Fish')),
    ('oil_sauces', gettext_noop('Oil & sauces')),
    ('spices', gettext_noop('Spices')),
    ('pasta_rice', gettext_noop('Pasta & rice')),
    ('canned', gettext_noop('Canned food')),
    ('baking', gettext_noop('Baking ingredients')),
    ('breakfast', gettext_noop('Breakfast')),
    ('frozen', gettext_noop('Frozen food')),
    ('sweets_snacks', gettext_noop('Sweets & snacks')),
    ('personal_care', gettext_noop('Cosmetics & personal care')),
    ('baby', gettext_noop('Baby')),
    ('cleaning', gettext_noop('Cleaning products')),
    ('household', gettext_noop('Household goods')),
    ('pets', gettext_noop('Pet supplies')),
    ('stationery', gettext_noop('Stationery')),
    ('drinks', gettext_noop('Drinks')),
]


def department_choices(user):
    """Sort the database catalogue by translated labels, folding accents and umlauts."""
    def sort_key(department):
        label = unicodedata.normalize("NFKD", str(department).casefold())
        return "".join(character for character in label if not unicodedata.combining(character))

    return [("", _("Without department")),
            *[(department.code, str(department)) for department in sorted(user.departments.all(), key=sort_key)]]
