
import pytest
from django.urls import reverse



@pytest.mark.django_db
@pytest.mark.parametrize("week", ["0001-01-01", "9999-12-20", "9999-12-31"])
def test_planner_calendar_boundaries_are_controlled(client, user, week):
    client.force_login(user)
    response = client.get(reverse("easy_kitchen:planner"), {"week": week})
    assert response.status_code == 200
    assert len(response.context["days"]) == 7
    if week == "0001-01-01":
        assert response.context["prev_week"] is None
    if week == "9999-12-20":
        assert response.context["next_week"] is None
    if week == "9999-12-31":
        assert response.context["week_start"].year != 9999

