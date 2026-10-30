from django.contrib import admin
from .models import ShoppingItem, ShoppingList


class ShoppingItemInline(admin.TabularInline):
    model = ShoppingItem
    extra = 0


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "user")
    list_filter = ("date",)
    search_fields = ("title", "user__username")
    inlines = (ShoppingItemInline,)
