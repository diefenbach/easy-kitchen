import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import ArticleForm, ImportForm, ShoppingItemForm, ShoppingListForm
from .models import Article, ShoppingItem, ShoppingList
from .services import (
    create_item,
    import_recipes,
    import_shopping_lists,
    remember_article,
    reorder_items,
    reorder_shopping_lists,
)


class UserListMixin(LoginRequiredMixin):
    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user)


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "easy_kitchen/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["shopping_lists"] = (
            self.request.user.shopping_lists.order_by("-created_at", "-id").prefetch_related("items")[:3]
        )
        context["recipes"] = (
            self.request.user.recipes.order_by("-created_at", "-id").prefetch_related("ingredients")[:3]
        )
        return context


class ShoppingListListView(LoginRequiredMixin, ListView):
    model = ShoppingList
    template_name = "easy_kitchen/lists/overview.html"
    context_object_name = "shopping_lists"

    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user).prefetch_related("items")


class ShoppingListReorderView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            payload = json.loads(request.body)
            reorder_shopping_lists(request.user, [int(value) for value in payload["list_ids"]])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return HttpResponseBadRequest(_("Invalid order."))
        return HttpResponseRedirect(reverse("easy_kitchen:list"))


class ShoppingListDetailView(UserListMixin, DetailView):
    model = ShoppingList
    template_name = "easy_kitchen/lists/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = ShoppingItemForm()
        context["shopping_list"] = self.object
        context["articles"] = self.request.user.articles.all()
        return context


class ShoppingListCreateView(LoginRequiredMixin, CreateView):
    model = ShoppingList
    form_class = ShoppingListForm
    template_name = "easy_kitchen/lists/form.html"

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("easy_kitchen:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse("easy_kitchen:list")
        return context


class ImportView(LoginRequiredMixin, View):
    template_name = "easy_kitchen/import.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ImportForm()})

    def post(self, request):
        form = ImportForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        imported = form.cleaned_data["json_data"]
        lists = imported["lists"]
        recipes = imported["recipes"]
        if lists is not None:
            count = len(import_shopping_lists(request.user, lists))
            messages.success(
                request,
                ngettext("Imported %(count)d shopping list.", "Imported %(count)d shopping lists.", count) % {"count": count},
            )
        if recipes is not None:
            count = len(import_recipes(request.user, recipes))
            messages.success(
                request,
                ngettext("Imported %(count)d recipe.", "Imported %(count)d recipes.", count) % {"count": count},
            )
        if lists is not None and recipes is None:
            return redirect("easy_kitchen:list")
        if recipes is not None and lists is None:
            return redirect("easy_kitchen:recipes")
        return redirect("easy_kitchen:home")


class ShoppingListUpdateView(UserListMixin, UpdateView):
    model = ShoppingList
    form_class = ShoppingListForm
    template_name = "easy_kitchen/lists/form.html"

    def get_success_url(self):
        if self.request.GET.get("return_to") == "overview":
            return reverse("easy_kitchen:list")
        return reverse("easy_kitchen:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = self.get_success_url()
        return context


class ShoppingListDeleteView(UserListMixin, DeleteView):
    model = ShoppingList
    template_name = "easy_kitchen/lists/confirm_delete.html"
    success_url = reverse_lazy("easy_kitchen:list")


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
                    "easy_kitchen/lists/partials/item.html",
                    {"item": item, "shopping_list": shopping_list, "include_modal": item.id not in existing_ids},
                )
                response.content += render_to_string(
                    "easy_kitchen/lists/partials/article_options.html",
                    {"articles": request.user.articles.all(), "oob": True},
                    request=request,
                ).encode()
                if item.id in existing_ids:
                    response["HX-Retarget"] = f'.shopping-item[data-item-id="{item.id}"]'
                    response["HX-Reswap"] = "outerHTML"
                return response
            return redirect("easy_kitchen:detail", pk=shopping_list.pk)
        if request.headers.get("HX-Request"):
            return render(
                request,
                "easy_kitchen/lists/partials/item_form.html",
                {"form": form, "shopping_list": shopping_list, "articles": request.user.articles.all()},
                status=422,
            )
        return redirect("easy_kitchen:detail", pk=shopping_list.pk)


class ItemUpdateView(LoginRequiredMixin, View):
    def get_item(self, request, list_pk, pk):
        return get_object_or_404(ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user)

    def get(self, request, list_pk, pk):
        item = self.get_item(request, list_pk, pk)
        return render(request, "easy_kitchen/lists/partials/item_edit_form.html", {"item": item, "form": ShoppingItemForm(instance=item)})

    def post(self, request, list_pk, pk):
        item = self.get_item(request, list_pk, pk)
        form = ShoppingItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            remember_article(request.user, item.name)
            return render(request, "easy_kitchen/lists/partials/item.html", {"item": item, "shopping_list": item.shopping_list})
        return render(request, "easy_kitchen/lists/partials/item_edit_form.html", {"item": item, "form": form}, status=422)


class ItemToggleView(LoginRequiredMixin, View):
    def post(self, request, list_pk, pk):
        item = get_object_or_404(ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user)
        item.checked = not item.checked
        item.save(update_fields=["checked", "updated_at"])
        if request.headers.get("HX-Request"):
            return render(request, "easy_kitchen/lists/partials/item.html", {"item": item, "shopping_list": item.shopping_list})
        return redirect("easy_kitchen:detail", pk=list_pk)


class ItemDeleteView(LoginRequiredMixin, View):
    def post(self, request, list_pk, pk):
        item = get_object_or_404(ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user)
        item.delete()
        if request.headers.get("HX-Request"):
            return HttpResponseRedirect("")
        return redirect("easy_kitchen:detail", pk=list_pk)


class ItemReorderView(LoginRequiredMixin, View):
    def post(self, request, list_pk):
        shopping_list = get_object_or_404(ShoppingList, pk=list_pk, user=request.user)
        try:
            payload = json.loads(request.body)
            reorder_items(shopping_list, [int(value) for value in payload["item_ids"]])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return HttpResponseBadRequest(_("Invalid order."))
        return HttpResponseRedirect(reverse("easy_kitchen:detail", kwargs={"pk": list_pk}))


def return_list_for(request):
    raw = request.POST.get("return_list") or request.GET.get("list")
    if not str(raw).isdigit():
        return None
    return ShoppingList.objects.filter(pk=int(raw), user=request.user).first()


def redirect_to_articles(request):
    shopping_list = return_list_for(request)
    url = reverse("easy_kitchen:articles")
    if shopping_list is None:
        return redirect(url)
    return redirect(f"{url}?list={shopping_list.pk}")


class ArticleListView(LoginRequiredMixin, View):
    template_name = "easy_kitchen/lists/articles.html"

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        form = ArticleForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect_to_articles(request)
        return render(request, self.template_name, self._context(request, form=form), status=422)

    def _context(self, request, form=None, edit_form=None):
        return {
            "articles": request.user.articles.all(),
            "form": form or ArticleForm(user=request.user),
            "edit_form": edit_form,
            "return_list": return_list_for(request),
        }


class ArticleUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        article = get_object_or_404(Article, pk=pk, user=request.user)
        form = ArticleForm(request.POST, user=request.user, instance=article)
        if form.is_valid():
            form.save()
            return redirect_to_articles(request)
        return render(request, "easy_kitchen/lists/articles.html", ArticleListView()._context(request, edit_form=form), status=422)


class ArticleDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        article = get_object_or_404(Article, pk=pk, user=request.user)
        article.delete()
        return redirect_to_articles(request)


class ItemsResetCheckedView(LoginRequiredMixin, View):
    def post(self, request, list_pk):
        shopping_list = get_object_or_404(ShoppingList, pk=list_pk, user=request.user)
        shopping_list.items.filter(checked=True).update(checked=False, updated_at=timezone.now())
        return redirect("easy_kitchen:detail", pk=shopping_list.pk)
