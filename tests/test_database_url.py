import pytest

from backend.database import normalize_database_url


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "postgresql://u:p@postgres:5432/db",
            "postgresql+psycopg2://u:p@postgres:5432/db",
        ),
        (
            "postgres://u:p@postgres:5432/db",
            "postgresql+psycopg2://u:p@postgres:5432/db",
        ),
        (
            "postgresql+psycopg://u:p@postgres:5432/db",
            "postgresql+psycopg://u:p@postgres:5432/db",
        ),
        ("sqlite:///./tasks.db", "sqlite:///./tasks.db"),
    ],
)
def test_normalize_database_url_pins_psycopg2_for_bare_postgres(url, expected):
    assert normalize_database_url(url) == expected
