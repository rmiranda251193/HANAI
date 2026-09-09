"""Step 29 -- production-readiness tests.

Covers the environment parsing helpers, the DATABASE_URL parser, the settings
currently in effect, the production settings (exercised in a subprocess so the
real settings module runs under a production environment), the /health/
endpoint, static collection, and the migration plan. Nothing here needs a live
PostgreSQL server.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config import env

BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
STRONG_SECRET = "x7" + "unittest-strong-secret" * 3 + "-0123456789abcdef"


# --- environment helpers ---------------------------------------------


class EnvHelperTests(SimpleTestCase):
    def test_get_bool_accepts_documented_truthy_and_falsy_values(self):
        for token in ("1", "true", "TRUE", "Yes", "on", " y "):
            with mock.patch.dict(os.environ, {"X": token}):
                self.assertIs(env.get_bool("X"), True)
        for token in ("0", "false", "No", "off", ""):
            with mock.patch.dict(os.environ, {"X": token}):
                self.assertIs(env.get_bool("X", default=True), False)

    def test_get_bool_rejects_ambiguous_values(self):
        with mock.patch.dict(os.environ, {"X": "maybe"}):
            with self.assertRaises(ImproperlyConfigured):
                env.get_bool("X")

    def test_get_bool_default_used_only_when_unset(self):
        os.environ.pop("X_UNSET", None)
        self.assertIs(env.get_bool("X_UNSET", default=True), True)
        self.assertIs(env.get_bool("X_UNSET", default=False), False)

    def test_get_int_valid_invalid_and_default(self):
        with mock.patch.dict(os.environ, {"N": "42"}):
            self.assertEqual(env.get_int("N", 1), 42)
        with mock.patch.dict(os.environ, {"N": ""}):
            self.assertEqual(env.get_int("N", 7), 7)
        with mock.patch.dict(os.environ, {"N": "not-a-number"}):
            with self.assertRaises(ImproperlyConfigured):
                env.get_int("N", 1)

    def test_get_list_parses_and_trims_comma_separated(self):
        with mock.patch.dict(os.environ, {"L": " a , b ,,c "}):
            self.assertEqual(env.get_list("L"), ["a", "b", "c"])
        os.environ.pop("L", None)
        self.assertEqual(env.get_list("L", default=["d"]), ["d"])


# --- DATABASE_URL parser -------------------------------------------


class ParseDatabaseUrlTests(SimpleTestCase):
    def _parse(self, url, **kw):
        return env.parse_database_url(url, base_dir=BASE_DIR, **kw)

    def test_sqlite_relative_path(self):
        cfg = self._parse("sqlite:///data/db.sqlite3")
        self.assertEqual(cfg["ENGINE"], "django.db.backends.sqlite3")
        self.assertTrue(cfg["NAME"].endswith(os.path.join("data", "db.sqlite3")))

    def test_sqlite_memory(self):
        cfg = self._parse("sqlite://:memory:")
        self.assertEqual(cfg["NAME"], ":memory:")

    def test_postgres_full_url(self):
        cfg = self._parse("postgres://bob:s3cr3t@db.internal:5433/hanai")
        self.assertEqual(cfg["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(cfg["NAME"], "hanai")
        self.assertEqual(cfg["USER"], "bob")
        self.assertEqual(cfg["PASSWORD"], "s3cr3t")
        self.assertEqual(cfg["HOST"], "db.internal")
        self.assertEqual(cfg["PORT"], "5433")
        self.assertTrue(cfg["CONN_HEALTH_CHECKS"])

    def test_postgresql_alias_and_url_encoded_password(self):
        cfg = self._parse("postgresql://u:p%40ss%2Fword@h/db")
        self.assertEqual(cfg["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(cfg["PASSWORD"], "p@ss/word")

    def test_postgres_sslmode_goes_to_options(self):
        cfg = self._parse("postgres://u:p@h:5432/db?sslmode=require")
        self.assertEqual(cfg["OPTIONS"], {"sslmode": "require"})

    def test_postgres_conn_max_age_from_query_and_argument(self):
        self.assertEqual(self._parse("postgres://u:p@h/db", conn_max_age=600)["CONN_MAX_AGE"], 600)
        self.assertEqual(
            self._parse("postgres://u:p@h/db?conn_max_age=30")["CONN_MAX_AGE"], 30
        )

    def test_invalid_urls_raise(self):
        for bad in (
            "",
            "   ",
            "mysql://u:p@h/db",
            "postgres:///nodb",
            "postgres://u:p@h/",
            "postgres://u:p@h/db?conn_max_age=lots",
        ):
            with self.assertRaises(ImproperlyConfigured, msg=bad):
                self._parse(bad)


# --- settings currently in effect (development / test posture) -----


class CurrentSettingsTests(SimpleTestCase):
    def test_timezone_awareness_is_preserved(self):
        from django.conf import settings

        self.assertTrue(settings.USE_TZ)
        self.assertEqual(settings.LANGUAGE_CODE, "en-us")

    def test_whitenoise_is_wired_after_security_middleware(self):
        from django.conf import settings

        mw = list(settings.MIDDLEWARE)
        self.assertIn("whitenoise.middleware.WhiteNoiseMiddleware", mw)
        self.assertEqual(
            mw.index("whitenoise.middleware.WhiteNoiseMiddleware"),
            mw.index("django.middleware.security.SecurityMiddleware") + 1,
        )
        self.assertIn(
            "whitenoise", settings.STORAGES["staticfiles"]["BACKEND"].lower()
        )

    def test_baseline_security_headers_always_on(self):
        from django.conf import settings

        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "same-origin")

    def test_logging_goes_to_console_only_no_file_handler(self):
        from django.conf import settings

        handlers = settings.LOGGING["handlers"]
        self.assertEqual(set(handlers), {"console"})
        self.assertEqual(handlers["console"]["class"], "logging.StreamHandler")

    def test_database_defaults_to_sqlite_without_database_url(self):
        from django.conf import settings

        self.assertEqual(
            settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3"
        )

    def test_ai_provider_defaults_are_offline_safe(self):
        from django.conf import settings

        self.assertEqual(settings.AI_PROVIDER, "fake")
        self.assertEqual(settings.OPENAI_API_KEY, "")
        self.assertTrue(hasattr(settings, "OLLAMA_BASE_URL"))


# --- production settings, exercised in a subprocess ----------------


class ProductionSettingsSubprocessTests(SimpleTestCase):
    """Run the real settings module under a production environment."""

    def _run(self, args, extra_env, expect_ok=True):
        run_env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings",
            # neutralise any dev .env values that would be inherited
            "DJANGO_DEBUG": "False",
            "DJANGO_SECRET_KEY": STRONG_SECRET,
            "DJANGO_ALLOWED_HOSTS": "hanai.example.org",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://hanai.example.org",
            "DATABASE_URL": "",
            "DJANGO_MANIFEST_STATIC": "",
            "PYTHONWARNINGS": "ignore",
        }
        run_env.update(extra_env)
        proc = subprocess.run(
            [PYTHON, "manage.py", *args],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            env=run_env,
        )
        combined = proc.stdout + proc.stderr
        if expect_ok:
            self.assertEqual(proc.returncode, 0, msg=combined)
        return proc.returncode, combined

    def test_check_deploy_is_clean_under_production_env(self):
        code, out = self._run(["check", "--deploy"], {})
        self.assertEqual(code, 0, msg=out)
        for warning in ("W004", "W008", "W009", "W012", "W016", "W018"):
            self.assertNotIn(warning, out)

    def test_missing_secret_key_fails_fast_when_not_debug(self):
        code, out = self._run(
            ["check"], {"DJANGO_SECRET_KEY": ""}, expect_ok=False
        )
        self.assertNotEqual(code, 0)
        self.assertIn("DJANGO_SECRET_KEY", out)

    def test_insecure_dev_secret_is_refused_when_not_debug(self):
        code, out = self._run(
            ["check"],
            {"DJANGO_SECRET_KEY": "django-insecure-local-development-only-change-me"},
            expect_ok=False,
        )
        self.assertNotEqual(code, 0)
        self.assertIn("insecure development SECRET_KEY", out)

    def test_ambiguous_debug_value_is_rejected(self):
        code, out = self._run(["check"], {"DJANGO_DEBUG": "maybe"}, expect_ok=False)
        self.assertNotEqual(code, 0)
        self.assertIn("DJANGO_DEBUG", out)

    def test_production_flags_and_postgres_url_via_diffsettings(self):
        code, out = self._run(
            ["diffsettings", "--all"],
            {
                "DATABASE_URL": "postgres://u:p@db.example:5432/hanai?sslmode=require",
                "DJANGO_SECURE_SSL": "true",
            },
        )
        self.assertIn("DEBUG = False", out)
        self.assertIn("django.db.backends.postgresql", out)
        self.assertIn("SESSION_COOKIE_SECURE = True", out)
        self.assertIn("CSRF_COOKIE_SECURE = True", out)
        self.assertIn("SECURE_SSL_REDIRECT = True", out)
        self.assertIn("SECURE_HSTS_SECONDS = 31536000", out)

    def test_development_env_still_works(self):
        code, out = self._run(
            ["check"],
            {"DJANGO_DEBUG": "True", "DJANGO_SECRET_KEY": ""},
        )
        self.assertEqual(code, 0, msg=out)


# --- health endpoint ---------------------------------------------


class HealthCheckTests(TestCase):
    def test_ok_response_shape(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(json.loads(response.content), {"status": "ok"})

    def test_reverse_name_and_no_auth_required(self):
        self.assertEqual(reverse("health"), "/health/")
        # anonymous client (default) already used above; assert again explicitly
        self.assertEqual(self.client.get("/health/").status_code, 200)

    def test_post_is_rejected(self):
        self.assertEqual(self.client.post("/health/").status_code, 405)

    def test_no_secret_leakage(self):
        from django.conf import settings

        body = self.client.get("/health/").content.decode()
        self.assertNotIn(settings.SECRET_KEY, body)
        self.assertNotIn("django.db.backends", body)

    def test_database_failure_returns_503_without_detail(self):
        with mock.patch("config.health.connection") as conn:
            conn.cursor.side_effect = RuntimeError("password=hunter2 host=db.internal")
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content), {"status": "error"})
        self.assertNotIn("hunter2", response.content.decode())

    def test_health_check_does_not_mutate(self):
        from django.contrib.auth import get_user_model

        before = get_user_model().objects.count()
        self.client.get("/health/")
        self.assertEqual(get_user_model().objects.count(), before)


# --- static files & migrations ---------------------------------


class StaticAndMigrationTests(SimpleTestCase):
    def test_collectstatic_succeeds_into_a_fresh_static_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(STATIC_ROOT=tmp):
                call_command("collectstatic", "--noinput", verbosity=0)
            self.assertTrue((Path(tmp) / "css" / "app.css").is_file())

    def test_static_root_is_configured_and_outside_static_sources(self):
        from django.conf import settings

        self.assertTrue(str(settings.STATIC_ROOT).endswith("staticfiles"))
        self.assertNotIn(Path(settings.STATIC_ROOT), [Path(p) for p in settings.STATICFILES_DIRS])

    def test_migration_plan_is_clean(self):
        proc = subprocess.run(
            [PYTHON, "manage.py", "makemigrations", "--check", "--dry-run"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "DJANGO_SETTINGS_MODULE": "config.settings",
                "DJANGO_DEBUG": "True",
            },
        )
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, msg=combined)
        self.assertIn("No changes detected", combined)
