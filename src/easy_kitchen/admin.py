from django.contrib import admin
from .models import Department, Article, Recipe, RecipeIngredient, RecipeStep, ShoppingItem, ShoppingList


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "position")
    search_fields = ("name", "code")


class ShoppingItemInline(admin.TabularInline):
    model = ShoppingItem
    extra = 0


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("name", "user")
    search_fields = ("name", "user__username")


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 0


class RecipeStepInline(admin.TabularInline):
    model = RecipeStep
    extra = 0


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("title", "user")
    search_fields = ("title", "user__username")
    inlines = (RecipeIngredientInline, RecipeStepInline)


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "user")
    list_filter = ("date",)
    search_fields = ("title", "user__username")
    inlines = (ShoppingItemInline,)
