import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from .forms import AddRecipeToListForm, RecipeForm, RecipeImportForm, RecipeLineForm
from .models import Recipe
from .services import (
    _normalized_name,
    add_recipe_ingredients_to_list,
    add_recipe_line,
    create_shopping_list,
    import_recipes,
    reorder_recipe_lines,
)


class UserRecipeMixin(LoginRequiredMixin):
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeListView(LoginRequiredMixin, View):
    def get(self, request):
        recipes = Recipe.objects.filter(user=request.user).prefetch_related("ingredients")
        return render(request, "shopping/recipes.html", {"recipes": recipes})


class RecipeCreateView(LoginRequiredMixin, CreateView):
    model = Recipe
    form_class = RecipeForm
    template_name = "shopping/recipe_form.html"

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("shopping:recipe-detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse("shopping:recipes")
        return context


class RecipeUpdateView(UserRecipeMixin, UpdateView):
    model = Recipe
    form_class = RecipeForm
    template_name = "shopping/recipe_form.html"

    def get_success_url(self):
        return reverse("shopping:recipe-detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = self.get_success_url()
        return context


class RecipeDeleteView(UserRecipeMixin, DeleteView):
    model = Recipe
    template_name = "shopping/recipe_confirm_delete.html"

    def get_success_url(self):
        return reverse("shopping:recipes")


class RecipeImportView(LoginRequiredMixin, View):
    template_name = "shopping/recipe_import.html"

    def get(self, request):
        return render(request, self.template_name, {"form": RecipeImportForm()})

    def post(self, request):
        form = RecipeImportForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        imported = import_recipes(request.user, form.cleaned_data["json_data"])
        messages.success(
            request,
            ngettext(
                "Imported %(count)d recipe.",
                "Imported %(count)d recipes.",
                len(imported),
            )
            % {"count": len(imported)},
        )
        return redirect("shopping:recipes")


class RecipeDetailView(UserRecipeMixin, View):
    def get(self, request, pk):
        recipe = get_object_or_404(self.get_queryset().prefetch_related("ingredients", "steps"), pk=pk)
        return render(request, "shopping/recipe_detail.html", self._context(request, recipe))

    def _context(self, request, recipe, add_to_list_form=None):
        return {
            "recipe": recipe,
            "ingredient_form": RecipeLineForm(kind="ingredient", auto_id="ingredient_%s"),
            "step_form": RecipeLineForm(kind="step", auto_id="step_%s"),
            "add_to_list_form": add_to_list_form or AddRecipeToListForm(user=request.user),
        }


class RecipeLineView(LoginRequiredMixin, View):
    kind = "ingredient"
    update_name = "shopping:recipe-ingredient-update"
    delete_name = "shopping:recipe-ingredient-delete"

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
            or RecipeLineForm(kind=self.kind, auto_id=f"edit_{line.pk}_%s", initial=self.line_initial(line)),
            "update_url": reverse(self.update_name, args=[recipe.pk, line.pk]),
            "delete_url": reverse(self.delete_name, args=[recipe.pk, line.pk]),
            "include_modal": include_modal,
        }


class RecipeLineCreateView(RecipeLineView):
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
                    "shopping/partials/recipe_line.html",
                    self.line_context(recipe, line),
                )
                empty_id = "empty-ingredients" if self.kind == "ingredient" else "empty-steps"
                response.content += f'<p id="{empty_id}" hx-swap-oob="delete"></p>'.encode()
                return response
            return redirect("shopping:recipe-detail", pk=recipe.pk)
        if request.headers.get("HX-Request"):
            response = render(
                request,
                "shopping/partials/recipe_line_form.html",
                {"form": form, "recipe": recipe, "kind": self.kind},
                status=422,
            )
            response["HX-Retarget"] = f"#{self.kind}-form"
            response["HX-Reswap"] = "outerHTML"
            return response
        return redirect("shopping:recipe-detail", pk=recipe.pk)


class RecipeLineUpdateView(RecipeLineView):
    def get(self, request, recipe_pk, pk):
        line, recipe = self.line(request, recipe_pk, pk)
        form = RecipeLineForm(kind=self.kind, auto_id=f"edit_{line.pk}_%s", initial=self.line_initial(line))
        return render(
            request,
            "shopping/partials/recipe_line_edit_form.html",
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
                "shopping/partials/recipe_line.html",
                self.line_context(recipe, line, include_modal=False),
            )
        return render(
            request,
            "shopping/partials/recipe_line_edit_form.html",
            self.line_context(recipe, line, form=form),
            status=422,
        )


class RecipeLineDeleteView(RecipeLineView):
    def post(self, request, recipe_pk, pk):
        line, recipe = self.line(request, recipe_pk, pk)
        line.delete()
        if request.headers.get("HX-Request"):
            return HttpResponseRedirect("")
        return redirect("shopping:recipe-detail", pk=recipe.pk)


class RecipeLineReorderView(LoginRequiredMixin, View):
    kind = "ingredient"

    def post(self, request, recipe_pk):
        recipe = get_object_or_404(Recipe, pk=recipe_pk, user=request.user)
        try:
            payload = json.loads(request.body)
            reorder_recipe_lines(recipe, self.kind, [int(value) for value in payload["line_ids"]])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return HttpResponseBadRequest(_("Invalid order."))
        return HttpResponseRedirect(reverse("shopping:recipe-detail", kwargs={"pk": recipe.pk}))


class IngredientCreateView(RecipeLineCreateView):
    kind = "ingredient"


class IngredientUpdateView(RecipeLineUpdateView):
    kind = "ingredient"


class IngredientDeleteView(RecipeLineDeleteView):
    kind = "ingredient"


class IngredientReorderView(RecipeLineReorderView):
    kind = "ingredient"


class StepCreateView(RecipeLineCreateView):
    kind = "step"
    update_name = "shopping:recipe-step-update"
    delete_name = "shopping:recipe-step-delete"


class StepUpdateView(RecipeLineUpdateView):
    kind = "step"
    update_name = "shopping:recipe-step-update"
    delete_name = "shopping:recipe-step-delete"


class StepDeleteView(RecipeLineDeleteView):
    kind = "step"
    update_name = "shopping:recipe-step-update"
    delete_name = "shopping:recipe-step-delete"


class StepReorderView(RecipeLineReorderView):
    kind = "step"


class RecipeAddToListView(LoginRequiredMixin, View):
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
                "shopping/recipe_detail.html",
                RecipeDetailView()._context(request, recipe, add_to_list_form=form),
                status=422,
            )
        title = form.cleaned_data["title"]
        if title:
            shopping_list = create_shopping_list(request.user, title=title, date=timezone.localdate())
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
        return redirect("shopping:detail", pk=shopping_list.pk)
