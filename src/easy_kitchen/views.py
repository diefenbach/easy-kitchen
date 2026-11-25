"""Web UI views for the home page, shopping lists, items, articles, departments, and JSON
import/export.

Every view requires a login and looks records up through the signed-in user; HTMX requests get
partial templates.
"""

import json
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
)

from .authentication import signed_in_user
from .forms import DepartmentEditorFormSet, ArticleEditorFormSet, ArticleForm, ExportForm, ImportForm, ShoppingItemForm, ShoppingListForm, ShoppingItemEditorFormSet
from .models import Article, ShoppingItem, ShoppingList
from .services import (
    QuantityOverflowError,
    save_articles,
    save_departments,
    create_item,
    delete_completed_items,
    delete_owned_shopping_item,
    export_records,
    import_recipes,
    import_shopping_lists,
    meal_plan_for_week,
    week_start_for,
    remember_article,
    reorder_items,
    reorder_shopping_lists,
    update_owned_shopping_item,
)


class UserListMixin(LoginRequiredMixin):
    """Limit shopping-list querysets to the signed-in user."""

    request: HttpRequest

    def get_queryset(self):
        """Return the signed-in user's shopping lists."""
        return ShoppingList.objects.filter(user=self.request.user)


class HomeView(LoginRequiredMixin, TemplateView):
    """Show two weeks of meals and the three newest lists and recipes."""

    template_name = "easy_kitchen/home.html"

    def get_context_data(self, **kwargs):
        """Add this and next week's planned meals and the three newest lists and recipes."""
        context = super().get_context_data(**kwargs)
        user = signed_in_user(self.request)
        week_start = week_start_for(timezone.localdate())
        plan = meal_plan_for_week(user, week_start)
        context["planned_meals"] = [entry for entry in plan.values() if entry and entry.recipe]
        context["week_start"] = week_start
        context["week_end"] = next(reversed(plan))
        next_week_start = week_start + timedelta(days=7)
        next_week_plan = meal_plan_for_week(user, next_week_start)
        context["next_week_start"] = next_week_start
        context["next_week_end"] = next(reversed(next_week_plan))
        context["next_week_planned_meals"] = [
            entry for entry in next_week_plan.values() if entry and entry.recipe
        ]
        context["shopping_lists"] = user.shopping_lists.order_by(
            "-created_at", "-id"
        ).prefetch_related("items__department")[:3]
        context["recipes"] = user.recipes.order_by(
            "-created_at", "-id"
        ).prefetch_related("ingredients")[:3]
        return context


class ShoppingListListView(LoginRequiredMixin, ListView):
    """Show every shopping list of the signed-in user."""

    model = ShoppingList
    template_name = "easy_kitchen/lists/overview.html"
    context_object_name = "shopping_lists"

    def get_queryset(self):
        """Return the user's lists with their items and departments."""
        return ShoppingList.objects.filter(user=self.request.user).prefetch_related("items__department")


class ShoppingListReorderView(LoginRequiredMixin, View):
    """Save a new order for the signed-in user's lists."""

    def post(self, request):
        """Save a new list order from a JSON body `{"list_ids": [...]}`; 204, or 400 for invalid input.
        """
        try:
            payload = json.loads(request.body)
            reorder_shopping_lists(request.user, [int(value) for value in payload["list_ids"]])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return HttpResponseBadRequest(_("Invalid order."))
        return HttpResponse(status=204)


class ListHideCompletedView(LoginRequiredMixin, View):
    """Persist whether completed items stay hidden on this list."""

    def post(self, request, pk):
        """Save whether completed items are hidden on the list (JSON body `{"hide": bool}`); 204, or
        400.
        """
        shopping_list = get_object_or_404(ShoppingList, pk=pk, user=request.user)
        try:
            hide = bool(json.loads(request.body)["hide"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return HttpResponseBadRequest(_("Invalid request."))
        shopping_list.hide_completed_items = hide
        shopping_list.save(update_fields=["hide_completed_items", "updated_at"])
        return HttpResponse(status=204)


class ShoppingListDetailView(UserListMixin, DetailView):
    """Show one list, its items, and the user's saved articles."""

    model = ShoppingList
    template_name = "easy_kitchen/lists/detail.html"

    def get_context_data(self, **kwargs):
        """Add the new-item form, the user's articles for suggestions, and the number of completed
        items.
        """
        context = super().get_context_data(**kwargs)
        context["form"] = ShoppingItemForm(user=self.request.user)
        context["shopping_list"] = self.object
        context["articles"] = signed_in_user(self.request).articles.select_related("department")
        context["completed_item_count"] = self.object.items.filter(checked=True).count()
        return context


class ShoppingListCreateView(LoginRequiredMixin, CreateView):
    """Create a list owned by the signed-in user."""

    model = ShoppingList
    form_class = ShoppingListForm
    template_name = "easy_kitchen/lists/form.html"

    def form_valid(self, form):
        """Assign the new list to the user and confirm with a message."""
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, _("Shopping list created."))
        return response

    def get_success_url(self):
        """Go to the new list."""
        assert self.object is not None, "set by the create/update view before redirecting"
        return reverse("easy_kitchen:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        """Add the cancel link back to the overview."""
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse("easy_kitchen:list")
        return context


class ImportView(LoginRequiredMixin, View):
    """Import JSON that may contain lists, recipes, or both."""

    template_name = "easy_kitchen/import.html"

    def get(self, request):
        """Show the empty import form."""
        return render(request, self.template_name, {"form": ImportForm(user=request.user)})

    def post(self, request):
        """Import lists and recipes from the submitted JSON and go to what was imported.

        Re-renders the form (422 when quantities would overflow) without importing anything
        partially.
        """
        form = ImportForm(request.POST, user=request.user)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        imported = form.cleaned_data["json_data"]
        lists = imported["lists"]
        recipes = imported["recipes"]
        if lists is not None:
            try:
                count = len(import_shopping_lists(request.user, lists))
            except QuantityOverflowError as error:
                form.add_error("json_data", str(error))
                return render(request, self.template_name, {"form": form}, status=422)
            messages.success(
                request,
                ngettext(
                    "Imported %(count)d shopping list.", "Imported %(count)d shopping lists.", count
                )
                % {"count": count},
            )
        if recipes is not None:
            count = len(import_recipes(request.user, recipes))
            messages.success(
                request,
                ngettext("Imported %(count)d recipe.", "Imported %(count)d recipes.", count)
                % {"count": count},
            )
        if lists is not None and recipes is None:
            return redirect("easy_kitchen:list")
        if recipes is not None and lists is None:
            return redirect("easy_kitchen:recipes")
        return redirect("easy_kitchen:home")


class ExportView(LoginRequiredMixin, View):
    """Download selected lists and recipes as JSON the import page can read."""

    template_name = "easy_kitchen/export.html"

    def get(self, request):
        """Show the lists and recipes to choose for export."""
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        """Return the chosen lists and recipes as a downloadable JSON file that Import JSON reads.
        """
        form = ExportForm(request.POST, user=request.user)
        if not form.is_valid():
            return render(request, self.template_name, self._context(request, form))
        payload = export_records(
            lists=form.cleaned_data["lists"],
            recipes=form.cleaned_data["recipes"],
        )
        response = HttpResponse(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            content_type="application/json; charset=utf-8",
        )
        response["Content-Disposition"] = 'attachment; filename="easykitchen.json"'
        return response

    def _context(self, request, form=None):
        return {
            "form": form or ExportForm(user=request.user),
            "shopping_lists": request.user.shopping_lists.all(),
            "recipes": request.user.recipes.all(),
        }


class ShoppingListUpdateView(UserListMixin, View):
    """Edit list metadata and items as one draft with an atomic save."""

    def get(self, request, pk):
        """Show the list editor."""
        shopping_list = get_object_or_404(self.get_queryset(), pk=pk)
        return self.render_editor(request, shopping_list)

    def post(self, request, pk):
        """Save title, date, icon, and the items in their new order, then return to the list or the
        overview.

        Changed item names or departments also update the saved articles. Invalid input re-renders
        the editor with 422; HTMX requests get the target page directly.
        """
        shopping_list = get_object_or_404(self.get_queryset(), pk=pk)
        form = ShoppingListForm(request.POST, instance=shopping_list)
        items = ShoppingItemEditorFormSet(request.POST, instance=shopping_list, prefix="items")
        valid = [form.is_valid(), items.is_valid()]
        if all(valid):
            with transaction.atomic():
                form.save()
                for line_form, item in zip(items.ordered_forms, items.save_ordered()):
                    changed = {"name", "department"} & set(line_form.changed_data)
                    remember_article(request.user, item.name, (item.department or "") if changed else None)
            messages.success(request, _("Shopping list updated."))
            if request.headers.get("HX-Request") == "true":
                view = ShoppingListListView() if request.GET.get("return_to") == "overview" else ShoppingListDetailView()
                view.setup(request, pk=pk)
                response = view.get(request, pk=pk)
                response["HX-Push-Url"] = self.return_url(request, shopping_list)
                return response
            return redirect(self.return_url(request, shopping_list))
        return self.render_editor(request, shopping_list, form=form, items=items, status=422)

    def return_url(self, request, shopping_list):
        """Return the overview when ?return_to=overview, otherwise the list."""
        if request.GET.get("return_to") == "overview":
            return reverse("easy_kitchen:list")
        return reverse("easy_kitchen:detail", args=[shopping_list.pk])

    def render_editor(self, request, shopping_list, *, form=None, items=None, status=200):
        """Render the list editor with the item formset and the user's articles."""
        if form is None:
            form = ShoppingListForm(instance=shopping_list)
        for field in form.fields.values():
            if not isinstance(field.widget, forms.RadioSelect):
                field.widget.attrs["class"] = "form-control"
        response = render(request, "easy_kitchen/lists/editor.html", {
            "object": shopping_list, "shopping_list": shopping_list, "form": form,
            "item_formset": items if items is not None else ShoppingItemEditorFormSet(instance=shopping_list, prefix="items"),
            "articles": request.user.articles.select_related("department"),
            "cancel_url": self.return_url(request, shopping_list),
        }, status=status)
        response["X-List-Editor"] = "true"
        return response


class ShoppingListDeleteView(UserListMixin, DeleteView):
    """Delete one list belonging to the signed-in user."""

    model = ShoppingList
    template_name = "easy_kitchen/lists/confirm_delete.html"
    success_url = reverse_lazy("easy_kitchen:list")

    def form_valid(self, form):
        """Delete the list and confirm with a message."""
        response = super().form_valid(form)
        messages.success(self.request, _("Shopping list deleted."))
        return response


class ItemCreateView(LoginRequiredMixin, View):
    """Add an item, merging the quantity when that name is already on the list."""

    def post(self, request, list_pk):
        """Add an item to the user's list, merging it into an item of the same name, which is unchecked again.

        Invalid input or an overflowing quantity answers 422 (HTMX: only the form is replaced).
        """
        shopping_list = get_object_or_404(ShoppingList, pk=list_pk, user=request.user)
        form = ShoppingItemForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                create_item(
                    shopping_list,
                    name=form.cleaned_data["name"],
                    quantity=form.cleaned_data["quantity"],
                    department=(form.cleaned_data["department"] or "") if "department" in request.POST else None,
                )
            except QuantityOverflowError as error:
                form.add_error("quantity", str(error))
            else:
                if request.headers.get("HX-Request"):
                    response = render(
                        request, "easy_kitchen/lists/partials/grouped_items.html",
                        {"shopping_list": shopping_list},
                    )
                    response["HX-Reswap"] = "innerHTML"
                    response.content += render_to_string(
                        "easy_kitchen/lists/partials/item_form.html",
                        {
                            "form": ShoppingItemForm(user=request.user), "shopping_list": shopping_list,
                            "articles": request.user.articles.select_related("department"), "oob": True,
                        },
                        request=request,
                    ).encode()
                    return response
                return redirect("easy_kitchen:detail", pk=shopping_list.pk)
        if request.headers.get("HX-Request"):
            response = render(
                request,
                "easy_kitchen/lists/partials/item_form.html",
                {
                    "form": form,
                    "shopping_list": shopping_list,
                    "articles": request.user.articles.select_related("department"),
                },
                status=422,
            )
            response["X-Item-Form"] = "true"
            response["HX-Retarget"] = "#item-form"
            response["HX-Reswap"] = "innerHTML"
            return response
        return render(request, "easy_kitchen/lists/detail.html", {
            "object": shopping_list, "shopping_list": shopping_list,
            "form": form, "articles": request.user.articles.select_related("department"),
            "completed_item_count": shopping_list.items.filter(checked=True).count(),
        }, status=422)


class ItemUpdateView(LoginRequiredMixin, View):
    """Edit one item on a list belonging to the signed-in user."""

    def get_item(self, request, list_pk, pk):
        """Return the item, or 404 unless it is on this list of the signed-in user."""
        return get_object_or_404(
            ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user
        )

    def get(self, request, list_pk, pk):
        """Show the inline edit form for one item."""
        item = self.get_item(request, list_pk, pk)
        return render(
            request,
            "easy_kitchen/lists/partials/item_edit_form.html",
            {"item": item, "form": ShoppingItemForm(instance=item, user=request.user, auto_id=f"item-{item.pk}-%s")},
        )

    def post(self, request, list_pk, pk):
        """Save the item through the shared service and return the regrouped items; invalid input
        answers 422.
        """
        item = self.get_item(request, list_pk, pk)
        form = ShoppingItemForm(request.POST, instance=item, user=request.user, auto_id=f"item-{item.pk}-%s")
        if form.is_valid():
            item = update_owned_shopping_item(request.user, item_id=item.pk, changes=form.cleaned_data)
            response = render(
                request, "easy_kitchen/lists/partials/grouped_items.html",
                {"shopping_list": item.shopping_list},
            )
            response["HX-Retarget"] = "#items"
            response["HX-Reswap"] = "innerHTML"
            return response
        response = render(
            request,
            "easy_kitchen/lists/partials/item_edit_form.html",
            {"item": item, "form": form},
            status=422,
        )
        response["X-Item-Form"] = "true"
        return response


class ItemToggleView(LoginRequiredMixin, View):
    """Mark one item completed or open again."""

    def post(self, request, list_pk, pk):
        """Toggle the item's checked state; HTMX gets the updated item, others are redirected to the
        list.
        """
        item = get_object_or_404(
            ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user
        )
        item.checked = not item.checked
        item.save(update_fields=["checked", "updated_at"])
        if request.headers.get("HX-Request"):
            return render(
                request,
                "easy_kitchen/lists/partials/item.html",
                {"item": item, "shopping_list": item.shopping_list},
            )
        return redirect("easy_kitchen:detail", pk=list_pk)


class ItemDeleteView(LoginRequiredMixin, View):
    """Delete one item from a list belonging to the signed-in user."""

    def post(self, request, list_pk, pk):
        """Delete the item from the user's list."""
        item = get_object_or_404(
            ShoppingItem, pk=pk, shopping_list__pk=list_pk, shopping_list__user=request.user
        )
        delete_owned_shopping_item(request.user, item_id=item.pk)
        if request.headers.get("HX-Request"):
            return HttpResponseRedirect("")
        return redirect("easy_kitchen:detail", pk=list_pk)


class ItemReorderView(LoginRequiredMixin, View):
    """Save a new order for the items of one list."""

    def post(self, request, list_pk):
        """Save a new item order from a JSON body `{"item_ids": [...]}`; 204, or 400 for invalid input.
        """
        shopping_list = get_object_or_404(ShoppingList, pk=list_pk, user=request.user)
        try:
            payload = json.loads(request.body)
            reorder_items(shopping_list, [int(value) for value in payload["item_ids"]])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return HttpResponseBadRequest(_("Invalid order."))
        return HttpResponse(status=204)


def return_list_for(request):
    """Return the user's list named by return_list or list, when that id is theirs."""
    raw = request.POST.get("return_list") or request.GET.get("list")
    if not str(raw).isdigit():
        return None
    return ShoppingList.objects.filter(pk=int(raw), user=request.user).first()


def redirect_to_articles(request):
    """Redirect to the articles page, keeping the list that opened it."""
    shopping_list = return_list_for(request)
    url = reverse("easy_kitchen:articles")
    if shopping_list is None:
        return redirect(url)
    return redirect(f"{url}?list={shopping_list.pk}")


class ArticleListView(LoginRequiredMixin, View):
    """Edit the user's article catalog as a single atomic draft."""

    template_name = "easy_kitchen/lists/articles.html"

    def get(self, request):
        """Show the article editor."""
        return self.render_editor(request)

    def post(self, request):
        # Keep existing single-article clients working; the web editor posts a formset.
        """Save the article editor (rename, change department, delete) in one transaction; invalid
        input answers 422.

        A single `name` field without a formset is still accepted for older clients.
        """
        if "name" in request.POST and "articles-TOTAL_FORMS" not in request.POST:
            form = ArticleForm(request.POST, user=request.user)
            if form.is_valid():
                form.save()
                return redirect_to_articles(request)
            return self.render_editor(request, legacy_error=form, status=422)
        formset = ArticleEditorFormSet(request.POST, user=request.user, prefix="articles")
        if formset.is_valid():
            records, deleted_ids = [], []
            for form in formset.forms:
                data = form.cleaned_data
                if not data:
                    continue
                article = data.get("id")
                if data.get("DELETE"):
                    if article:
                        deleted_ids.append(article.pk)
                elif data.get("name"):
                    records.append({"id": article.pk if article else None,
                                    "name": data["name"], "department": data["department"]})
            try:
                save_articles(request.user, records, deleted_ids)
            except (ValueError, IntegrityError):
                formset.non_form_errors().append(_("The articles could not be saved. Check for duplicate names and try again."))
            else:
                messages.success(request, _("Articles updated."))
                return redirect_to_articles(request)
        return self.render_editor(request, formset=formset, status=422)

    def render_editor(self, request, *, formset=None, legacy_error=None, status=200):
        """Render the article editor.

        X-Article-Editor tells editor.js the response is the editor again, so it keeps unsaved input.
        """
        response = render(request, self.template_name, self._context(request, formset=formset, edit_form=legacy_error), status=status)
        response["X-Article-Editor"] = "true"
        return response

    def _context(self, request, form=None, edit_form=None, formset=None):
        shopping_list = return_list_for(request)
        cancel_url = reverse("easy_kitchen:detail", args=[shopping_list.pk]) if shopping_list else reverse("easy_kitchen:list")
        return {
            "article_formset": formset if formset is not None else ArticleEditorFormSet(user=request.user, prefix="articles"),
            "legacy_error": edit_form or form,
            "return_list": shopping_list,
            "cancel_url": cancel_url,
        }


class DepartmentListView(LoginRequiredMixin, View):
    """Edit the current user's departments as a single draft."""

    def get(self, request):
        """Show the department editor."""
        return self.render_editor(request)

    def post(self, request):
        """Save the department editor (rename, delete) in one transaction and return to the list it was
        opened from.
        """
        formset = DepartmentEditorFormSet(request.POST, user=request.user, prefix="departments")
        if formset.is_valid():
            records, deleted_ids = [], []
            for form in formset.forms:
                data = form.cleaned_data
                if not data:
                    continue
                department = data.get("id")
                if data.get("DELETE"):
                    if department:
                        deleted_ids.append(department.pk)
                elif data.get("name"):
                    records.append({"id": department.pk if department else None, "name": data["name"]})
            try:
                save_departments(request.user, records, deleted_ids)
            except (ValueError, IntegrityError):
                formset.non_form_errors().append(_("The departments could not be saved. Check for duplicate names and try again."))
            else:
                messages.success(request, _("Departments updated."))
                url = reverse("easy_kitchen:departments")
                shopping_list = return_list_for(request)
                return redirect(f"{url}?list={shopping_list.pk}" if shopping_list else url)
        return self.render_editor(request, formset=formset, status=422)

    def render_editor(self, request, *, formset=None, status=200):
        """Render the department editor with a cancel link back to the list it was opened from.

        X-Department-Editor tells editor.js the response is the editor again, so it keeps unsaved input.
        """
        shopping_list = return_list_for(request)
        response = render(request, "easy_kitchen/lists/departments.html", {
            "department_formset": formset if formset is not None else DepartmentEditorFormSet(user=request.user, prefix="departments"),
            "return_list": shopping_list,
            "cancel_url": reverse("easy_kitchen:detail", args=[shopping_list.pk]) if shopping_list else reverse("easy_kitchen:list"),
        }, status=status)
        response["X-Department-Editor"] = "true"
        return response


class ArticleUpdateView(LoginRequiredMixin, View):
    """Rename one saved article belonging to the signed-in user."""

    def post(self, request, pk):
        """Save one article from the single-article form; errors re-render the article page with 422.
        """
        article = get_object_or_404(Article, pk=pk, user=request.user)
        form = ArticleForm(request.POST, user=request.user, instance=article)
        if form.is_valid():
            form.save()
            return redirect_to_articles(request)
        return render(
            request,
            "easy_kitchen/lists/articles.html",
            ArticleListView()._context(request, edit_form=form),
            status=422,
        )


class ArticleDeleteView(LoginRequiredMixin, View):
    """Delete one saved article without changing shopping-list items."""

    def post(self, request, pk):
        """Delete one of the user's articles."""
        article = get_object_or_404(Article, pk=pk, user=request.user)
        article.delete()
        return redirect_to_articles(request)


class ItemsDeleteCompletedView(LoginRequiredMixin, View):
    """Delete every completed item on the list after confirmation."""

    def post(self, request, list_pk):
        """Delete all checked items of the list and say how many."""
        shopping_list = get_object_or_404(ShoppingList, pk=list_pk, user=request.user)
        deleted = delete_completed_items(shopping_list)
        if deleted:
            messages.success(
                request,
                ngettext(
                    "Deleted one completed item.",
                    "Deleted %(count)s completed items.",
                    deleted,
                )
                % {"count": deleted},
            )
        return redirect("easy_kitchen:detail", pk=shopping_list.pk)
