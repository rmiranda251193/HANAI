# HANAI -- Production Deployment

HANAI is a standard Django 5.2 / Python 3.11 WSGI application. It runs behind any
HTTPS reverse proxy in front of Gunicorn, backed by PostgreSQL. There is no
Node build step and no client framework.

```
Internet ──> HTTPS / reverse proxy ──> Gunicorn (config.wsgi) ──> Django ──> PostgreSQL
                                                     │
                                          WhiteNoise (static)   AI provider (env)
```

Step 29 only hardens configuration, database, security, logging and the
deployment path. The learning architecture (Lessons, AI review, Teacher
authoring, Physics Lab, Tutor, Assessments, Misconception Recovery, Student
Evidence, Teacher Analytics) is unchanged.

---

## 1. Environment variables

All configuration is environment-driven. `.env.example` is the authoritative
list; copy it to `.env` for local development. In production set these as real
environment variables — **never commit a populated `.env`**.

| Variable | Required | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | **yes** in production | Long random string. `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Startup fails if missing while `DJANGO_DEBUG` is not true. |
| `DJANGO_DEBUG` | no (default `False`) | `True` only for local development. Never `True` in production. |
| `DJANGO_ALLOWED_HOSTS` | **yes** in production | Comma-separated hostnames, e.g. `hanai.example.org,www.hanai.example.org`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | recommended | Comma-separated full origins, e.g. `https://hanai.example.org`. |
| `DATABASE_URL` | **yes** in production | `postgres://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require`. Unset → SQLite (development/tests only). |
| `DJANGO_DB_CONN_MAX_AGE` | no | Persistent-connection seconds (default `600` in production, `0` in dev). |
| `DJANGO_SECURE_SSL` | no (default `True` in prod) | Set `False` only if the proxy already forces HTTPS and you do not want Django to redirect. Doing so re-introduces the `check --deploy` HTTPS warnings by design. |
| `DJANGO_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS`, `DJANGO_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_HSTS_PRELOAD` | no | Fine-tune HTTPS behaviour. Defaults: redirect on, HSTS 1 year, subdomains + preload on. |
| `DJANGO_MANIFEST_STATIC` | build/release | `1` after `collectstatic` to serve hashed + compressed assets. Set automatically by the Dockerfile. |
| `DJANGO_LOG_LEVEL` | no (default `INFO`) | Root/app log level. Logs go to stdout/stderr. |
| `DJANGO_TIME_ZONE` | no (default `UTC`) | Storage stays timezone-aware regardless. |
| `AI_PROVIDER` | no (default `fake`) | `fake` (no network), `openai` (needs `OPENAI_API_KEY`), `ollama` (reserved). |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT` | when `AI_PROVIDER=openai` | Never commit a real key. Missing key with `AI_PROVIDER=openai` fails safely at request time, not at import. |

Boolean values accept `1/true/yes/on` and `0/false/no/off`; anything else is a
hard configuration error.

---

## 2. Local development

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                              # sets DJANGO_DEBUG=True
python manage.py migrate
python manage.py runserver
```

SQLite is used automatically. `AI_PROVIDER=fake` means no external calls.

---

## 3. PostgreSQL setup

1. Provision a PostgreSQL 14+ database (a managed service is expected in
   production — see §7 for what the platform must provide).
2. Set `DATABASE_URL`, e.g.
   `postgres://hanai:••••@db.internal:5432/hanai?sslmode=require`.
3. The driver (`psycopg2-binary`) is in `requirements.txt`; no code change is
   needed to switch engines.
4. `?sslmode=require` (or `verify-full`) is passed straight through to the
   driver. `conn_max_age` may be given in the URL or via `DJANGO_DB_CONN_MAX_AGE`;
   `CONN_HEALTH_CHECKS` is enabled for PostgreSQL.

Local PostgreSQL smoke test (needs Docker):

```bash
docker compose up --build -d db
DATABASE_URL=postgres://hanai:hanai@localhost:5432/hanai python manage.py migrate
DATABASE_URL=postgres://hanai:hanai@localhost:5432/hanai python manage.py test
```

---

## 4. Production release steps

Run these in order on each deploy (the `Procfile` `release` phase runs the
migration automatically on Heroku/Render/Railway-style platforms):

```bash
python manage.py check --deploy      # must be clean under the production env
python manage.py migrate --noinput   # explicit, controlled; never at container start
python manage.py collectstatic --noinput
```

Then start the app server (never `runserver`):

```bash
gunicorn config.wsgi:application --config gunicorn.conf.py
```

The Docker image does `collectstatic` at build time and starts Gunicorn; it does
**not** migrate on start. Migrations are always an explicit step.

The image also has a Node build stage that compiles the React islands
(`frontend/` -> `static/react/*.js`; see `docs/REACT_ISLANDS.md`) before
`collectstatic` runs. If that stage fails or is skipped, the build still
succeeds -- the placeholder files already committed at `static/react/*.js`
keep every page working, with the React enhancements simply absent.

Create a staff (teacher) account once the database is migrated:

```bash
python manage.py createsuperuser
```

The teacher workspace and analytics gate on `is_staff`; there is no separate
student login yet (guest profile). Add real student authentication before
exposing student pages to the public internet.

---

## 5. Health check

`GET /health/` → `{"status": "ok"}` (HTTP 200) when the process is up and a
trivial `SELECT 1` succeeds; `{"status": "error"}` (HTTP 503) on a database
failure. It is unauthenticated, read-only, cheap, and leaks nothing (no DSN, no
driver error, no stack trace). Point the platform's health probe at it.

---

## 6. HTTPS

HTTPS is terminated by the platform / reverse proxy, not by Django. With the
default production settings Django will:

- redirect HTTP → HTTPS (`SECURE_SSL_REDIRECT`),
- trust `X-Forwarded-Proto` from the proxy (`SECURE_PROXY_SSL_HEADER`),
- send `Strict-Transport-Security` (1 year, subdomains, preload),
- set `Secure` on the session and CSRF cookies.

If your platform redirects HTTP→HTTPS itself and you set `DJANGO_SECURE_SSL=false`,
`check --deploy` will report `security.W004/W008/W012/W016` — that is an
acknowledged operator choice, not a defect.

---

## 7. What the hosting platform / operator must provide

This repository does **not** create infrastructure. Production expects:

- **PostgreSQL** with automated backups and point-in-time recovery. HANAI does
  not back itself up; verify the provider's backup retention and test a restore.
- **TLS termination** with a valid certificate and HTTP→HTTPS at the edge.
- **Secret storage** for `DJANGO_SECRET_KEY`, `DATABASE_URL`, and (if used)
  `OPENAI_API_KEY` — injected as environment variables, never in the image.
- **Log aggregation** from stdout/stderr.
- A **health probe** hitting `/health/`.

### Migration & rollback

- Migrations are forward-only Django migrations across `physics`, `students`,
  `lessons`, `assessments`, `provenance`, `teachers`. They apply cleanly to an
  empty database (`migrate` from scratch).
- Roll back a bad release by redeploying the previous image/commit. If that
  release added a migration, also run `manage.py migrate <app> <previous>` —
  only if that migration is reversible. Prefer restoring from a PostgreSQL
  backup for schema changes that dropped or rewrote data.
- Never run `flush`, `reset_db`, or any destructive command as part of a
  deploy. Seed/`seed_*` commands are development tools.
