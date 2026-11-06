from django.conf import settings
from django.core.validators import URLValidator
from django.db import models, transaction
from django.db.models import F
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _



def _place_new_record_first(instance):
    """Shift this user's existing records down so a new one without a position is stored first."""
    if not instance._state.adding or instance.position:
        return
    type(instance).objects.filter(user_id=instance.user_id).update(position=F("position") + 1)
    instance.position = 1


class ShoppingList(models.Model):
    """A dated shopping list belonging to one user."""

    class Icon(models.TextChoices):
        """Icon shown on the list card. New lists use the basket."""

        BASKET = "basket", _("Basket")
        CART = "cart", _("Cart")
        BAG = "bag", _("Bag")
        EGG = "egg", _("Fried egg")
        CUP = "cup", _("Drink")
        APPLE = "apple", _("Apple")
        COOKIE = "cookie", _("Cookie")
        CAKE = "cake", _("Cake")
        DROPLET = "droplet", _("Drop")
        FLOWER = "flower", _("Flower")
        FIRE = "fire", _("Flame")
        SNOW = "snow", _("Frozen")
        HOUSE = "house", _("Home")
        GIFT = "gift", _("Gift")
        HEART = "heart", _("Heart")

    ICON_CLASSES = {
        Icon.BASKET: "bi-basket",
        Icon.CART: "bi-cart",
        Icon.BAG: "bi-bag",
        Icon.EGG: "bi-egg-fried",
        Icon.CUP: "bi-cup-hot",
        Icon.APPLE: "bi-apple",
        Icon.COOKIE: "bi-cookie",
        Icon.CAKE: "bi-cake2",
        Icon.DROPLET: "bi-droplet",
        Icon.FLOWER: "bi-flower1",
        Icon.FIRE: "bi-fire",
        Icon.SNOW: "bi-snow",
        Icon.HOUSE: "bi-house",
        Icon.GIFT: "bi-gift",
        Icon.HEART: "bi-heart",
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_lists"
    )
    title = models.CharField(_("title"), max_length=255)
    icon = models.CharField(_("icon"), max_length=20, choices=Icon.choices, default=Icon.BASKET)
    date = models.DateField(_("date"), default=timezone.localdate)
    hide_completed_items = models.BooleanField(_("hide completed items"), default=False)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "id")
        verbose_name = _("shopping list")
        verbose_name_plural = _("shopping lists")

    def __str__(self):
        return self.title

    @property
    def icon_class(self) -> str:
        """Bootstrap Icons class for this list, falling back to the basket."""
        return self.ICON_CLASSES.get(self.icon, self.ICON_CLASSES[self.Icon.BASKET])

    def save(self, *args, **kwargs):
        with transaction.atomic():
            _place_new_record_first(self)
            return super().save(*args, **kwargs)


class Department(models.Model):
    """Shared supermarket department, referenced by articles and list entries."""

    code = models.SlugField(_("code"), max_length=20, unique=True)
    name = models.CharField(_("name"), max_length=100)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        verbose_name = _("Department")
        verbose_name_plural = _("Departments")

    def __str__(self):
        return str(_(self.name))


class DepartmentReference:
    @property
    def department_code(self):
        """Stable code used by forms, JSON and MCP; an empty string means unassigned."""
        return self.department.code if self.department_id else ""


class ShoppingItem(DepartmentReference, models.Model):
    """One line on a shopping list."""

    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(_("item"), max_length=255)
    department = models.ForeignKey(
        Department, verbose_name=_("Department"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="items",
    )
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


class Article(DepartmentReference, models.Model):
    """A saved item name suggested while filling a shopping list."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="articles"
    )
    name = models.CharField(_("article"), max_length=255)
    department = models.ForeignKey(
        Department, verbose_name=_("Department"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="articles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        verbose_name = _("article")
        verbose_name_plural = _("articles")
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "user", name="shopping_article_unique_name_per_user"
            ),
        ]

    def __str__(self):
        return self.name


class Recipe(models.Model):
    """A recipe belonging to one user. Empty nutrition fields mean the value is unknown."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipes"
    )
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    is_favorite = models.BooleanField(_("favorite"), default=False)
    image = models.ImageField(_("image"), upload_to="recipes/", blank=True)
    image_url = models.URLField(
        _("image URL"),
        max_length=500,
        blank=True,
        validators=[URLValidator(schemes=["http", "https"])],
    )
    calories = models.PositiveIntegerField(_("calories"), null=True, blank=True)
    protein = models.PositiveIntegerField(_("protein"), null=True, blank=True)
    carbohydrates = models.PositiveIntegerField(_("carbohydrates"), null=True, blank=True)
    fat = models.PositiveIntegerField(_("fat"), null=True, blank=True)
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
    def picture_url(self) -> str:
        """Uploaded image when one is set, otherwise the image URL."""
        if self.image:
            return self.image.url
        return self.image_url


class MealPlanEntry(models.Model):
    """One recipe assigned to a calendar day for meal planning."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meal_plan_entries"
    )
    date = models.DateField(_("date"))
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="meal_plan_entries",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("date",)
        verbose_name = _("meal plan entry")
        verbose_name_plural = _("meal plan entries")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "date"), name="shopping_mealplanentry_unique_user_date"
            ),
        ]

    def __str__(self):
        return f"{self.date}: {self.recipe_id}"


class RecipeIngredient(models.Model):
    """One ingredient line of a recipe."""

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
    """One preparation step of a recipe."""

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="steps")
    text = models.TextField(_("step"))
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        verbose_name = _("step")
        verbose_name_plural = _("steps")

    def __str__(self):
        return self.text
