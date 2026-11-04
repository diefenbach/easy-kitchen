from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views import View
from django.views.generic import TemplateView

from .forms import AddRecipeToListForm, MealPlanDayForm
from .services import (
    add_meal_plan_week_to_list,
    clear_meal_plan_day,
    meal_plan_for_week,
    planned_recipe_count,
    set_meal_plan_recipe,
    week_dates,
    week_start_for,
)


def _week_start_from_request(request) -> date:
    raw = request.GET.get("week") or request.POST.get("week_start")
    if raw:
        try:
            return week_start_for(date.fromisoformat(raw))
        except ValueError:
            pass
    return week_start_for(timezone.localdate())


class MealPlanView(LoginRequiredMixin, TemplateView):
    """Show Mon–Sun meal plan for one week."""

    template_name = "easy_kitchen/planner/week.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_planner_context(self.request))
        return context


def _planner_context(request, *, add_to_list_form=None):
    """Build all seven day forms for the requested week, including on form errors."""
    week_start = _week_start_from_request(request)
    plan = meal_plan_for_week(request.user, week_start)
    days = []
    for day in week_dates(week_start):
        entry = plan.get(day)
        days.append(
            {
                "date": day,
                "entry": entry,
                "form": MealPlanDayForm(
                    user=request.user,
                    auto_id=f"plan-{day.isoformat()}_%s",
                    initial={
                        "date": day,
                        "recipe": entry.recipe_id if entry else None,
                    },
                ),
            }
        )
    return {
        "week_start": week_start,
        "week_end": week_dates(week_start)[-1],
        "prev_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
        "days": days,
        "add_to_list_form": (
            add_to_list_form if add_to_list_form is not None
            else AddRecipeToListForm(user=request.user)
        ),
    }


class MealPlanAssignView(LoginRequiredMixin, View):
    """Assign a recipe to one day."""

    def post(self, request):
        week_start = _week_start_from_request(request)
        form = MealPlanDayForm(request.POST, user=request.user)
        if not form.is_valid():
            messages.error(request, _("Could not save the plan. Check the recipe selection."))
            return redirect(f"{reverse('easy_kitchen:planner')}?week={week_start.isoformat()}")
        day = form.cleaned_data["date"]
        set_meal_plan_recipe(request.user, day, form.cleaned_data["recipe"])
        messages.success(
            request,
            _("Recipe planned for %(date)s.")
            % {"date": formats.date_format(day, "SHORT_DATE_FORMAT")},
        )
        return redirect(f"{reverse('easy_kitchen:planner')}?week={week_start.isoformat()}")


class MealPlanClearView(LoginRequiredMixin, View):
    """Remove the planned recipe from one day."""

    def post(self, request, day):
        week_start = _week_start_from_request(request)
        try:
            planned_day = date.fromisoformat(day)
        except ValueError:
            messages.error(request, _("Invalid date."))
            return redirect(reverse("easy_kitchen:planner"))
        clear_meal_plan_day(request.user, planned_day)
        messages.success(
            request,
            _("Removed the recipe from %(date)s.")
            % {"date": formats.date_format(planned_day, "SHORT_DATE_FORMAT")},
        )
        return redirect(f"{reverse('easy_kitchen:planner')}?week={week_start.isoformat()}")


class MealPlanAddToListView(LoginRequiredMixin, View):
    """Build a shopping list from the planned recipes in one week."""

    def post(self, request):
        week_start = _week_start_from_request(request)
        form = AddRecipeToListForm(request.POST, user=request.user)
        if not form.is_valid():
            return render(
                request,
                "easy_kitchen/planner/week.html",
                _planner_context(request, add_to_list_form=form),
                status=422,
            )
        title = form.cleaned_data["title"]
        shopping_list = form.cleaned_data["shopping_list"]
        try:
            target = add_meal_plan_week_to_list(
                request.user,
                week_start,
                shopping_list=shopping_list,
                title=title,
            )
        except ValueError as error:
            form.add_error(None, str(error))
            return render(
                request,
                "easy_kitchen/planner/week.html",
                _planner_context(request, add_to_list_form=form),
                status=422,
            )
        recipe_count = planned_recipe_count(request.user, week_start)
        messages.success(
            request,
            ngettext(
                "Added ingredients from %(count)d planned recipe to “%(title)s”.",
                "Added ingredients from %(count)d planned recipes to “%(title)s”.",
                recipe_count,
            )
            % {"count": recipe_count, "title": target.title},
        )
        return redirect(reverse("easy_kitchen:detail", args=[target.pk]))
