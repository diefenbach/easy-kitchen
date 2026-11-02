import importlib


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
