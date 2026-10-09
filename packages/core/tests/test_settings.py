import pytest

from haggle_core.settings import Settings


def test_env_vars_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAGGLE_ENV", "prod")
    monkeypatch.setenv("HAGGLE_GIT_SHA", "abc1234")

    settings = Settings(_env_file=None)

    assert settings.env == "prod"
    assert settings.git_sha == "abc1234"


def test_database_url_is_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAGGLE_DATABASE_URL", "postgresql+psycopg://u:s3cr3t@host/db")

    settings = Settings(_env_file=None)

    assert "s3cr3t" not in repr(settings)
    assert "s3cr3t" in settings.database_url.get_secret_value()


def test_invalid_env_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAGGLE_ENV", "staging")

    with pytest.raises(ValueError, match="local"):
        Settings(_env_file=None)
