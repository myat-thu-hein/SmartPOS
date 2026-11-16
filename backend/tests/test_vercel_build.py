"""The Vercel build explains missing settings before it touches the database."""

from __future__ import annotations

import pytest

from app import vercel_build

GOOD = {
    "VERCEL": "1",
    "VERCEL_ENV": "production",
    "APP_ENV": "production",
    "SECRET_KEY": "k" * 48,
    "DATABASE_URL": "postgresql://user:pw@db.example.com/smartpos",
    "FRONTEND_URL": "https://smartpos.example.com",
}


def test_a_complete_vercel_configuration_passes() -> None:
    assert vercel_build.vercel_settings_report(GOOD) == ([], [])
    # The Supabase integration's variable name is accepted too.
    supabase = {k: v for k, v in GOOD.items() if k != "DATABASE_URL"} | {"POSTGRES_URL": GOOD["DATABASE_URL"]}
    assert vercel_build.vercel_settings_report(supabase) == ([], [])


def test_an_empty_project_lists_every_missing_setting_at_once(monkeypatch, capsys) -> None:
    for name in ("APP_ENV", "SECRET_KEY", "DATABASE_URL", "POSTGRES_URL", "FRONTEND_URL", "SKIP_MIGRATIONS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("SECRET_KEY", "  too-short  ")
    with pytest.raises(SystemExit):
        vercel_build.main()
    err = capsys.readouterr().err
    assert "this preview deployment is missing settings" in err
    for expected in ("APP_ENV", "SECRET_KEY", "DATABASE_URL", "Settings > Environment Variables", '"Preview"'):
        assert expected in err
    assert "too-short" not in err  # never echo a secret's value


def test_skip_migrations_does_not_skip_the_settings_check(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SKIP_MIGRATIONS", "1")
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(SystemExit):
        vercel_build.main()


def test_advisories_do_not_fail_the_build() -> None:
    env = {k: v for k, v in GOOD.items() if k != "FRONTEND_URL"} | {"DEMO_LOGIN_ENABLED": "true"}
    missing, advice = vercel_build.vercel_settings_report(env)
    assert missing == []
    assert any("FRONTEND_URL" in a for a in advice)
    assert any("CRON_SECRET" in a for a in advice)
