from django.conf import settings
from django.core.validators import URLValidator
from django.db import models, transaction
from django.db.models import F
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _place_new_record_first(instance):
    if not instance._state.adding or instance.position:
        return
    type(instance).objects.filter(user_id=instance.user_id).update(position=F("position") + 1)
    instance.position = 1


class ShoppingList(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_lists")
    title = models.CharField(_("title"), max_length=255)
    date = models.DateField(_("date"), default=timezone.localdate)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "id")
        verbose_name = _("shopping list")
        verbose_name_plural = _("shopping lists")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        with transaction.atomic():
            _place_new_record_first(self)
            return super().save(*args, **kwargs)


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


class Article(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="articles")
    name = models.CharField(_("article"), max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        verbose_name = _("article")
        verbose_name_plural = _("articles")
        constraints = [
            models.UniqueConstraint(Lower("name"), "user", name="shopping_article_unique_name_per_user"),
        ]

    def __str__(self):
        return self.name


class Recipe(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipes")
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    image = models.ImageField(_("image"), upload_to="recipes/", blank=True)
    image_url = models.URLField(
        _("image URL"),
        max_length=500,
        blank=True,
        validators=[URLValidator(schemes=["http", "https"])],
    )
    calories = models.PositiveIntegerField(_("calories"), null=True, blank=True)
    protein = models.PositiveIntegerField(_("protein"), null=True, blank=True)
    preparation_minutes = models.PositiveIntegerField(_("preparation time"), null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "id")
        verbose_name = _("recipe")
        verbose_name_plural = _("recipes")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        with transaction.atomic():
            _place_new_record_first(self)
            return super().save(*args, **kwargs)

    @property
    def picture_url(self):
        if self.image:
            return self.image.url
        return self.image_url


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    name = models.CharField(_("ingredient"), max_length=255)
    quantity = models.CharField(_("quantity"), max_length=100, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        verbose_name = _("ingredient")
        verbose_name_plural = _("ingredients")

    def __str__(self):
        return self.name


class RecipeStep(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="steps")
    text = models.TextField(_("step"))
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        verbose_name = _("step")
        verbose_name_plural = _("steps")

    def __str__(self):
        return self.text
