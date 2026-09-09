# HANAI — DodongOS Physics AI

A Django learning platform for high-school Physics where **AI assists, teachers
decide, and students learn by thinking**. It covers lessons, an AI lesson-draft
generator and deterministic reviewer, teacher lesson authoring, an interactive
Physics Lab (Newton's Second Law, Kinematics), a Physics Tutor, practice and
structured assessments, misconception detection and teacher-controlled recovery
paths, a teacher evidence workspace, and deterministic cohort analytics.

- **Stack:** Django 5.2, Python 3.11, PostgreSQL in production (SQLite for
  development), WSGI/Gunicorn, WhiteNoise for static files. No Node, no client
  framework.
- **AI providers** are pluggable and environment-driven; the default `fake`
  provider makes no network calls, so development and the test suite run
  offline.

## Status

Integrated MVP — the planned roadmap (Steps 1–30) is complete: teacher lesson
authoring, AI lesson generation and deterministic review, the Physics Lab
(Newton's Second Law, Kinematics), the Physics Tutor, practice and structured
assessments, misconception detection and teacher-controlled recovery, the
teacher evidence workspace, cohort analytics, and a production-ready
configuration (see [DEPLOYMENT.md](DEPLOYMENT.md)). Further work is driven by
real usage, not this roadmap.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # sets DJANGO_DEBUG=True; SQLite is automatic
python manage.py migrate
python manage.py runserver
```

Then open <http://localhost:8000/>. Create a teacher account with
`python manage.py createsuperuser` (the teacher workspace gates on `is_staff`).

## Tests

```bash
python manage.py test
```

## Production

Everything is configured by environment variables. See **[DEPLOYMENT.md](DEPLOYMENT.md)**
for the full runbook: required variables, PostgreSQL setup, `check --deploy`,
migrations, `collectstatic`, the `/health/` endpoint, the Gunicorn command, and
what the hosting platform must provide (backups, TLS, secret storage).

Quick production shape:

```bash
python manage.py check --deploy
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --config gunicorn.conf.py
```

A `Dockerfile`, `.dockerignore` and `docker-compose.yml` (Gunicorn + PostgreSQL)
are provided for container deployments and local production-like verification.
