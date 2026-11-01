from django.apps import AppConfig


class EasyKitchenConfig(AppConfig):
    """Django app for shopping lists and recipes. The database label stays shopping."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "easy_kitchen"
    label = "shopping"
