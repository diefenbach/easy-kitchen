import importlib


def test_build_settings_collect_static_without_production_secrets(monkeypatch):
    for name in (
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
    ):
        monkeypatch.delenv(name, raising=False)

    build = importlib.import_module("project.settings.build")
    build = importlib.reload(build)

    assert build.DEBUG is False
    assert build.STATIC_ROOT == build.SRC_DIR / "staticfiles"
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in build.MIDDLEWARE
    assert build.STORAGES["staticfiles"]["BACKEND"] == (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )


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
