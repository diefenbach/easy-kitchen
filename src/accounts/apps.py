from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """The project's user model: people sign in with their email address, there is no username."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
