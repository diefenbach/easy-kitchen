import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import ShoppingItemForm, ShoppingListForm, ShoppingListImportForm
from .models import ShoppingItem, ShoppingList
from .services import create_item, import_shopping_lists, reorder_items


class UserListMixin(LoginRequiredMixin):
    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user)


class ShoppingListListView(LoginRequiredMixin, ListView):
    model = ShoppingList
    template_name = "shopping/list.html"
    context_object_name = "shopping_lists"

    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user).prefetch_related("items")


class ShoppingListDetailView(UserListMixin, DetailView):
    model = ShoppingList
    template_name = "shopping/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = ShoppingItemForm()
        context["shopping_list"] = self.object
        return context


class ShoppingListCreateView(LoginRequiredMixin, CreateView):
    model = ShoppingList
    form_class = ShoppingListForm
    template_name = "shopping/list_form.html"

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("shopping:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse("shopping:list")
        return context


class ShoppingListImportView(LoginRequiredMixin, View):
    template_name = "shopping/import.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ShoppingListImportForm()})

    def post(self, request):
        form = ShoppingListImportForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        imported_lists = import_shopping_lists(request.user, form.cleaned_data["json_data"])
        messages.success(
            request,
            ngettext(
                "Imported %(count)d shopping list.",
                "Imported %(count)d shopping lists.",
                len(imported_lists),
            ) % {"count": len(imported_lists)},
        )
        return redirect("shopping:list")


class ShoppingListUpdateView(UserListMixin, UpdateView):
    model = ShoppingList
    form_class = ShoppingListForm
    template_name = "shopping/list_form.html"

    def get_success_url(self):
        if self.request.GET.get("return_to") == "overview":
            return reverse("shopping:list")
        return reverse("shopping:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = self.get_success_url()
        return context


class ShoppingListDeleteView(UserListMixin, DeleteView):
    model = ShoppingList
    template_name = "shopping/list_confirm_delete.html"
    success_url = "/"


class ItemCreateView(LoginRequiredMixin, View):
    def post(self, request, list_pk):
        shopping_list = get_object_or_404(ShoppingList, pk=list_pk, user=request.user)
        form = ShoppingItemForm(request.POST)
        if form.is_valid():
            existing_ids = set(shopping_list.items.values_list("id", flat=True))
            item = create_item(shopping_list, name=form.cleaned_data["name"], quantity=form.cleaned_data["quantity"])
            if request.headers.get("HX-Request"):
                response = render(
                    request,
                    "shopping/partials/item.html",
                    {"item": item, "shopping_list": shopping_list, "include_modal": item.id not in existing_ids},
                )
                if item.id in existing_ids:
                    response["HX-Retarget"] = f'.shopping-item[data-item-id="{item.id}"]'
                    response["HX-Reswap"] = "outerHTML"
                return response
            return redirect("shopping:detail", pk=shopping_list.pk)
        if request.headers.get("HX-Request"):
            return render(request, "shopping/partials/item_form.html", {"form": form, "shopping_list": shopping_list}, status=422)
        return redirect("shopping:detail", pk=shopping_list.pk)


class ItemUpdateView(LoginRequiredMixin, View):
    def get_item(self, request, list_pk, pk):
        return get_object_or_404(ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user)

    def get(self, request, list_pk, pk):
        item = self.get_item(request, list_pk, pk)
        return render(request, "shopping/partials/item_edit_form.html", {"item": item, "form": ShoppingItemForm(instance=item)})

    def post(self, request, list_pk, pk):
        item = self.get_item(request, list_pk, pk)
        form = ShoppingItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            return render(request, "shopping/partials/item.html", {"item": item, "shopping_list": item.shopping_list})
        return render(request, "shopping/partials/item_edit_form.html", {"item": item, "form": form}, status=422)


class ItemToggleView(LoginRequiredMixin, View):
    def post(self, request, list_pk, pk):
        item = get_object_or_404(ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user)
        item.checked = not item.checked
        item.save(update_fields=["checked", "updated_at"])
        if request.headers.get("HX-Request"):
            return render(request, "shopping/partials/item.html", {"item": item, "shopping_list": item.shopping_list})
        return redirect("shopping:detail", pk=list_pk)


class ItemDeleteView(LoginRequiredMixin, View):
    def post(self, request, list_pk, pk):
        item = get_object_or_404(ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user)
        item.delete()
        if request.headers.get("HX-Request"):
            return HttpResponseRedirect("")
        return redirect("shopping:detail", pk=list_pk)


class ItemReorderView(LoginRequiredMixin, View):
    def post(self, request, list_pk):
        shopping_list = get_object_or_404(ShoppingList, pk=list_pk, user=request.user)
        try:
            payload = json.loads(request.body)
            reorder_items(shopping_list, [int(value) for value in payload["item_ids"]])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return HttpResponseBadRequest(_("Invalid order."))
        return HttpResponseRedirect(reverse("shopping:detail", kwargs={"pk": list_pk}))


class ItemsResetCheckedView(LoginRequiredMixin, View):
    def post(self, request, list_pk):
        shopping_list = get_object_or_404(ShoppingList, pk=list_pk, user=request.user)
        shopping_list.items.filter(checked=True).update(checked=False, updated_at=timezone.now())
        return redirect("shopping:detail", pk=shopping_list.pk)
