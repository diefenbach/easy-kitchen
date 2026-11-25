import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured


def test_development_settings_read_hosts_from_environment(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "easykitchen")
    monkeypatch.setenv("POSTGRES_USER", "easykitchen")
    monkeypatch.setenv("POSTGRES_PASSWORD", "easykitchen")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,dev.example.test")
    monkeypatch.setenv("DJANGO_CSRF_TRUSTED_ORIGINS", "https://dev.example.test")

    development = importlib.import_module("project.settings.development")
    development = importlib.reload(development)

    assert development.ALLOWED_HOSTS == ["localhost", "127.0.0.1", "dev.example.test"]
    assert development.CSRF_TRUSTED_ORIGINS == ["https://dev.example.test"]


def test_development_settings_strip_port_from_allowed_hosts(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "easykitchen")
    monkeypatch.setenv("POSTGRES_USER", "easykitchen")
    monkeypatch.setenv("POSTGRES_PASSWORD", "easykitchen")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "localhost:8000,127.0.0.1:8000")

    development = importlib.import_module("project.settings.development")
    development = importlib.reload(development)

    assert development.ALLOWED_HOSTS == ["localhost", "127.0.0.1"]


def test_persistent_postgres_connections_are_health_checked(monkeypatch):
    from project.settings.base import postgres_database_from_environment

    monkeypatch.setenv("POSTGRES_DB", "easykitchen")
    monkeypatch.setenv("POSTGRES_USER", "easykitchen")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-password")
    config = postgres_database_from_environment()
    assert config["CONN_MAX_AGE"] == 600
    assert config["CONN_HEALTH_CHECKS"] is True


def _production_environment(monkeypatch):
    for name, value in {
        "DJANGO_SECRET_KEY": "secret",
        "DJANGO_ALLOWED_HOSTS": "kitchen.example.test",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://kitchen.example.test",
        "POSTGRES_DB": "easykitchen",
        "POSTGRES_USER": "easykitchen",
        "POSTGRES_PASSWORD": "easykitchen",
        "POSTGRES_HOST": "postgres",
        "DJANGO_DEFAULT_FROM_EMAIL": "EasyKitchen <noreply@example.test>",
        "EMAIL_HOST": "smtp.example.test",
    }.items():
        monkeypatch.setenv(name, value)


def test_production_settings_send_mail_over_smtp(monkeypatch):
    _production_environment(monkeypatch)

    production = importlib.reload(importlib.import_module("project.settings.production"))

    assert production.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"
    assert production.EMAIL_HOST == "smtp.example.test"
    assert production.DEFAULT_FROM_EMAIL == "EasyKitchen <noreply@example.test>"


def test_production_settings_require_an_smtp_host(monkeypatch):
    _production_environment(monkeypatch)
    monkeypatch.delenv("EMAIL_HOST")

    with pytest.raises(ImproperlyConfigured, match="EMAIL_HOST"):
        importlib.reload(importlib.import_module("project.settings.production"))
