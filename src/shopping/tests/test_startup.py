import pytest
from django.core.exceptions import ImproperlyConfigured
from shopping.startup import ensure_migrations_applied, pending_migration_labels


def test_unapplied_migrations_stop_startup(monkeypatch):
    monkeypatch.setattr(
        "shopping.startup.pending_migration_labels",
        lambda: ["shopping.0006_overview_position"],
    )

    with pytest.raises(ImproperlyConfigured, match="shopping.0006_overview_position"):
        ensure_migrations_applied()


@pytest.mark.django_db
def test_applied_migrations_let_startup_continue():
    assert pending_migration_labels() == []
    ensure_migrations_applied()
