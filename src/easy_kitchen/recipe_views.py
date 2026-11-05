import json
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _, ngettext
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from .forms import AddRecipeToListForm, AddRecipeToPlannerForm, RecipeForm, RecipeLineForm
from .models import Recipe
from .recipe_pdf import build_recipe_pdf
from .services import (
    _normalized_name,
    add_recipe_ingredients_to_list,
    add_recipe_line,
    create_shopping_list,
    reorder_recipe_lines,
    reorder_recipes,
    set_meal_plan_recipe,
    week_start_for,
)


class UserRecipeMixin(LoginRequiredMixin):
    """Limit recipe querysets to the signed-in user."""

    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeListView(LoginRequiredMixin, View):
    """Show every recipe of the signed-in user."""

    def get(self, request):
        search_query = request.GET.get("q", "").strip()
        favorites_only = request.GET.get("favorites") == "1"
        recipes = Recipe.objects.filter(user=request.user).prefetch_related("ingredients")
        for term in search_query.split():
            recipes = recipes.filter(Q(title__icontains=term) | Q(description__icontains=term))
        if favorites_only:
            recipes = recipes.filter(is_favorite=True)
        return render(
            request,
            "easy_kitchen/recipes/overview.html",
            {
                "recipes": recipes,
                "search_query": search_query,
                "favorites_only": favorites_only,
                "filters_active": bool(search_query or favorites_only),
                "add_to_list_form": AddRecipeToListForm(user=request.user),
                "add_to_planner_form": AddRecipeToPlannerForm(auto_id="planner_%s"),
            },
        )


class RecipeFavoriteView(UserRecipeMixin, View):
    """Set the favorite state of an owned recipe and return to its originating page."""

    def post(self, request, pk):
        recipe = get_object_or_404(self.get_queryset(), pk=pk)
        value = request.POST.get("is_favorite")
        if value not in {"0", "1"}:
            return HttpResponseBadRequest(_("Invalid request."))
        recipe.is_favorite = value == "1"
        recipe.save(update_fields=["is_favorite", "updated_at"])
        if request.POST.get("return_to") == "detail":
            return redirect("easy_kitchen:recipe-detail", pk=recipe.pk)
        parameters = {}
        query = request.POST.get("q", "").strip()
        if query:
            parameters["q"] = query
        if request.POST.get("favorites") == "1":
            parameters["favorites"] = "1"
        url = reverse("easy_kitchen:recipes")
        if parameters:
            url = f"{url}?{urlencode(parameters)}"
        return redirect(url)


class RecipeReorderView(LoginRequiredMixin, View):
    """Save a new order for the signed-in user's recipes."""

    def post(self, request):
        try:
            payload = json.loads(request.body)
            reorder_recipes(request.user, [int(value) for value in payload["recipe_ids"]])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return HttpResponseBadRequest(_("Invalid order."))
        return HttpResponseRedirect(reverse("easy_kitchen:recipes"))


class RecipeCreateView(LoginRequiredMixin, CreateView):
    """Create a recipe owned by the signed-in user."""

    model = Recipe
    form_class = RecipeForm
    template_name = "easy_kitchen/recipes/form.html"

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, _("Recipe created."))
        return response

    def get_success_url(self):
        return reverse("easy_kitchen:recipe-detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse("easy_kitchen:recipes")
        return context


class RecipeUpdateView(UserRecipeMixin, UpdateView):
    """Edit a recipe and return to the overview or the recipe that opened the form."""

    model = Recipe
    form_class = RecipeForm
    template_name = "easy_kitchen/recipes/form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Recipe updated."))
        return response

    def get_success_url(self):
        if self.request.GET.get("return_to") == "overview":
            return reverse("easy_kitchen:recipes")
        return reverse("easy_kitchen:recipe-detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = self.get_success_url()
        return context


class RecipeDeleteView(UserRecipeMixin, DeleteView):
    """Delete one recipe belonging to the signed-in user."""

    model = Recipe
    template_name = "easy_kitchen/recipes/confirm_delete.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Recipe deleted."))
        return response

    def get_success_url(self):
        return reverse("easy_kitchen:recipes")


class RecipePdfView(UserRecipeMixin, View):
    """Download one recipe as a PDF in the active UI language."""

    def get(self, request, pk):
        recipe = get_object_or_404(
            self.get_queryset().prefetch_related("ingredients", "steps"), pk=pk
        )
        pdf_bytes = build_recipe_pdf(recipe)
        filename = f"{slugify(recipe.title) or 'recipe'}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class RecipeDetailView(UserRecipeMixin, View):
    """Show one recipe and the form that copies its ingredients to a list."""

    def get(self, request, pk):
        recipe = get_object_or_404(
            self.get_queryset().prefetch_related("ingredients", "steps"), pk=pk
        )
        return render(request, "easy_kitchen/recipes/detail.html", self._context(request, recipe))

    def _context(self, request, recipe, add_to_list_form=None, add_to_planner_form=None):
        return {
            "recipe": recipe,
            "add_to_planner_form": (
                add_to_planner_form if add_to_planner_form is not None
                else AddRecipeToPlannerForm(auto_id="planner_%s")
            ),
            "ingredient_form": RecipeLineForm(kind="ingredient", auto_id="ingredient_%s"),
            "step_form": RecipeLineForm(kind="step", auto_id="step_%s"),
            "add_to_list_form": (
                add_to_list_form if add_to_list_form is not None
                else AddRecipeToListForm(user=request.user)
            ),
        }


class RecipeAddToPlannerView(UserRecipeMixin, View):
    """Plan an owned recipe for the chosen date and show that week."""

    def post(self, request, pk):
        recipe = get_object_or_404(
            self.get_queryset().prefetch_related("ingredients", "steps"), pk=pk
        )
        form = AddRecipeToPlannerForm(request.POST, auto_id="planner_%s")
        if not form.is_valid():
            return render(
                request,
                "easy_kitchen/recipes/detail.html",
                RecipeDetailView()._context(request, recipe, add_to_planner_form=form),
                status=422,
            )
        day = form.cleaned_data["date"]
        set_meal_plan_recipe(request.user, day, recipe)
        return redirect(f"{reverse('easy_kitchen:planner')}?week={week_start_for(day).isoformat()}")


class RecipeLineView(LoginRequiredMixin, View):
    """Shared access to one ingredient or step of the signed-in user's recipe."""

    kind = "ingredient"
    update_name = "easy_kitchen:recipe-ingredient-update"
    delete_name = "easy_kitchen:recipe-ingredient-delete"

    def recipe(self, request, recipe_pk):
        return get_object_or_404(Recipe, pk=recipe_pk, user=request.user)

    def line(self, request, recipe_pk, pk):
        recipe = self.recipe(request, recipe_pk)
        manager = recipe.ingredients if self.kind == "ingredient" else recipe.steps
        return get_object_or_404(manager, pk=pk), recipe

    def line_initial(self, line):
        if self.kind == "ingredient":
            return {"name": line.name, "quantity": line.quantity}
        return {"text": line.text}

    def line_context(self, recipe, line, form=None, include_modal=True):
        return {
            "recipe": recipe,
            "line": line,
            "kind": self.kind,
            "form": form
            or RecipeLineForm(
                kind=self.kind, auto_id=f"edit_{line.pk}_%s", initial=self.line_initial(line)
            ),
            "update_url": reverse(self.update_name, args=[recipe.pk, line.pk]),
            "delete_url": reverse(self.delete_name, args=[recipe.pk, line.pk]),
            "include_modal": include_modal,
        }


class RecipeLineCreateView(RecipeLineView):
    """Append an ingredient or step and return the new line for HTMX."""

    def post(self, request, recipe_pk):
        recipe = self.recipe(request, recipe_pk)
        form = RecipeLineForm(request.POST, kind=self.kind, auto_id=f"{self.kind}_%s")
        if form.is_valid():
            if self.kind == "ingredient":
                line = add_recipe_line(
                    recipe,
                    self.kind,
                    name=form.cleaned_data["name"],
                    quantity=form.cleaned_data.get("quantity", ""),
                )
            else:
                line = add_recipe_line(recipe, self.kind, text=form.cleaned_data["text"])
            if request.headers.get("HX-Request"):
                response = render(
                    request,
                    "easy_kitchen/recipes/partials/line.html",
                    self.line_context(recipe, line),
                )
                empty_id = "empty-ingredients" if self.kind == "ingredient" else "empty-steps"
                response.content += f'<p id="{empty_id}" hx-swap-oob="delete"></p>'.encode()
                return response
            return redirect("easy_kitchen:recipe-detail", pk=recipe.pk)
        if request.headers.get("HX-Request"):
            response = render(
                request,
                "easy_kitchen/recipes/partials/line_form.html",
                {"form": form, "recipe": recipe, "kind": self.kind},
                status=422,
            )
            response["HX-Retarget"] = f"#{self.kind}-form"
            response["HX-Reswap"] = "outerHTML"
            return response
        return redirect("easy_kitchen:recipe-detail", pk=recipe.pk)


class RecipeLineUpdateView(RecipeLineView):
    """Edit one ingredient or step of a recipe."""

    def get(self, request, recipe_pk, pk):
        line, recipe = self.line(request, recipe_pk, pk)
        form = RecipeLineForm(
            kind=self.kind, auto_id=f"edit_{line.pk}_%s", initial=self.line_initial(line)
        )
        return render(
            request,
            "easy_kitchen/recipes/partials/line_edit_form.html",
            self.line_context(recipe, line, form=form),
        )

    def post(self, request, recipe_pk, pk):
        line, recipe = self.line(request, recipe_pk, pk)
        form = RecipeLineForm(request.POST, kind=self.kind, auto_id=f"edit_{line.pk}_%s")
        if form.is_valid():
            if self.kind == "ingredient":
                line.name = _normalized_name(form.cleaned_data["name"])
                line.quantity = (form.cleaned_data.get("quantity") or "").strip()
                line.save(update_fields=["name", "quantity"])
            else:
                line.text = _normalized_name(form.cleaned_data["text"])
                line.save(update_fields=["text"])
            return render(
                request,
                "easy_kitchen/recipes/partials/line.html",
                self.line_context(recipe, line, include_modal=False),
            )
        return render(
            request,
            "easy_kitchen/recipes/partials/line_edit_form.html",
            self.line_context(recipe, line, form=form),
            status=422,
        )


class RecipeLineDeleteView(RecipeLineView):
    """Delete one ingredient or step of a recipe."""

    def post(self, request, recipe_pk, pk):
        line, recipe = self.line(request, recipe_pk, pk)
        line.delete()
        if request.headers.get("HX-Request"):
            return HttpResponseRedirect("")
        return redirect("easy_kitchen:recipe-detail", pk=recipe.pk)


class RecipeLineReorderView(LoginRequiredMixin, View):
    """Save a new order for the ingredients or steps of one recipe."""

    kind = "ingredient"

    def post(self, request, recipe_pk):
        recipe = get_object_or_404(Recipe, pk=recipe_pk, user=request.user)
        try:
            payload = json.loads(request.body)
            reorder_recipe_lines(recipe, self.kind, [int(value) for value in payload["line_ids"]])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return HttpResponseBadRequest(_("Invalid order."))
        return HttpResponseRedirect(reverse("easy_kitchen:recipe-detail", kwargs={"pk": recipe.pk}))


class IngredientCreateView(RecipeLineCreateView):
    """Add an ingredient to a recipe."""

    kind = "ingredient"


class IngredientUpdateView(RecipeLineUpdateView):
    """Edit one ingredient of a recipe."""

    kind = "ingredient"


class IngredientDeleteView(RecipeLineDeleteView):
    """Delete one ingredient of a recipe."""

    kind = "ingredient"


class IngredientReorderView(RecipeLineReorderView):
    """Save a new order for a recipe's ingredients."""

    kind = "ingredient"


class StepCreateView(RecipeLineCreateView):
    """Add a preparation step to a recipe."""

    kind = "step"
    update_name = "easy_kitchen:recipe-step-update"
    delete_name = "easy_kitchen:recipe-step-delete"


class StepUpdateView(RecipeLineUpdateView):
    """Edit one preparation step of a recipe."""

    kind = "step"
    update_name = "easy_kitchen:recipe-step-update"
    delete_name = "easy_kitchen:recipe-step-delete"


class StepDeleteView(RecipeLineDeleteView):
    """Delete one preparation step of a recipe."""

    kind = "step"
    update_name = "easy_kitchen:recipe-step-update"
    delete_name = "easy_kitchen:recipe-step-delete"


class StepReorderView(RecipeLineReorderView):
    """Save a new order for a recipe's preparation steps."""

    kind = "step"


class RecipeAddToListView(LoginRequiredMixin, View):
    """Copy a recipe's ingredients onto an existing list or a new one."""

    def post(self, request, pk):
        recipe = get_object_or_404(
            Recipe.objects.filter(user=request.user).prefetch_related("ingredients"),
            pk=pk,
        )
        form = AddRecipeToListForm(request.POST, user=request.user)
        if form.is_valid() and not recipe.ingredients.exists():
            form.add_error(None, _("This recipe has no ingredients."))
        if not form.is_valid():
            return render(
                request,
                "easy_kitchen/recipes/detail.html",
                RecipeDetailView()._context(request, recipe, add_to_list_form=form),
                status=422,
            )
        title = form.cleaned_data["title"]
        if title:
            shopping_list = create_shopping_list(
                request.user, title=title, date=timezone.localdate()
            )
        else:
            shopping_list = form.cleaned_data["shopping_list"]
        add_recipe_ingredients_to_list(recipe, shopping_list)
        count = recipe.ingredients.count()
        messages.success(
            request,
            ngettext(
                'Added %(count)d ingredient to "%(title)s".',
                'Added %(count)d ingredients to "%(title)s".',
                count,
            )
            % {"count": count, "title": shopping_list.title},
        )
        return redirect("easy_kitchen:detail", pk=shopping_list.pk)
