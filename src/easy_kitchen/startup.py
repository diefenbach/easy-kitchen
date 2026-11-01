from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def pending_migration_labels():
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def ensure_migrations_applied():
    pending = pending_migration_labels()
    if pending:
        raise ImproperlyConfigured(
            "Unapplied migrations: " + ", ".join(pending) + ". Run python manage.py migrate."
        )
