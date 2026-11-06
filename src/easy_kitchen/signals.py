from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import seed_default_departments


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="easy_kitchen.seed_user_departments")
def create_user_departments(sender, instance, created, raw, using, **kwargs):
    if created and not raw:
        seed_default_departments(instance, using=using)
