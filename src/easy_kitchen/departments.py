from django.db import models
from django.utils.translation import gettext_lazy as _


class Department(models.TextChoices):
    """Fixed supermarket departments in shopping order."""

    PRODUCE = "produce", _("Fruit & vegetables")
    FRESH = "fresh", _("Fresh food")
    MEAT = "meat", _("Meat & sausages")
    BREAD = "bread", _("Bread")
    DAIRY = "dairy", _("Dairy products")
    FISH = "fish", _("Fish")
    OIL_SAUCES = "oil_sauces", _("Oil & sauces")
    SPICES = "spices", _("Spices")
    PASTA_RICE = "pasta_rice", _("Pasta & rice")
    CANNED = "canned", _("Canned food")
    BAKING = "baking", _("Baking ingredients")
    BREAKFAST = "breakfast", _("Breakfast")
    FROZEN = "frozen", _("Frozen food")
    SWEETS_SNACKS = "sweets_snacks", _("Sweets & snacks")
    PERSONAL_CARE = "personal_care", _("Cosmetics & personal care")
    BABY = "baby", _("Baby")
    CLEANING = "cleaning", _("Cleaning products")
    HOUSEHOLD = "household", _("Household goods")
    PETS = "pets", _("Pet supplies")
    STATIONERY = "stationery", _("Stationery")
    DRINKS = "drinks", _("Drinks")
