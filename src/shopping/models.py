from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ShoppingList(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_lists")
    title = models.CharField(_("title"), max_length=255)
    date = models.DateField(_("date"), default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "-created_at")
        verbose_name = _("shopping list")
        verbose_name_plural = _("shopping lists")

    def __str__(self):
        return self.title


class ShoppingItem(models.Model):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(_("item"), max_length=255)
    quantity = models.CharField(_("quantity"), max_length=100, blank=True)
    checked = models.BooleanField(_("completed"), default=False)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "id")
        verbose_name = _("shopping item")
        verbose_name_plural = _("shopping items")

    def __str__(self):
        return self.name
