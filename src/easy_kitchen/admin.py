"""Django admin for lists, articles, departments, and recipes."""

from django.contrib import admin
from .models import Department, Article, Recipe, RecipeIngredient, RecipeStep, ShoppingItem, ShoppingList


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Departments of the signed-in admin only; new ones are assigned to them."""

    list_display = ("name", "code", "position")
    search_fields = ("name", "code")

    exclude = ("user",)

    def get_queryset(self, request):
        """Limit the list to the signed-in admin's departments."""
        return super().get_queryset(request).filter(user=request.user)

    def save_model(self, request, obj, form, change):
        """Assign the department to the signed-in admin before saving."""
        obj.user = request.user
        super().save_model(request, obj, form, change)


class ShoppingItemInline(admin.TabularInline):
    """Items edited inside their shopping list."""

    model = ShoppingItem
    extra = 0


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Saved articles of all users."""

    list_display = ("name", "user")
    search_fields = ("name", "user__email")


class RecipeIngredientInline(admin.TabularInline):
    """Ingredients edited inside their recipe."""

    model = RecipeIngredient
    extra = 0


class RecipeStepInline(admin.TabularInline):
    """Steps edited inside their recipe."""

    model = RecipeStep
    extra = 0


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    """Recipes of all users with their ingredients and steps."""

    list_display = ("title", "user")
    search_fields = ("title", "user__email")
    inlines = (RecipeIngredientInline, RecipeStepInline)


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    """Shopping lists of all users with their items."""

    list_display = ("title", "date", "user")
    list_filter = ("date",)
    search_fields = ("title", "user__email")
    inlines = (ShoppingItemInline,)
