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

## 3D Physics visualization

The Physics Lab **Kinematics** activity offers a **2D view** (default, SVG) and
an interactive **3D view** (Three.js). The 3D layer is presentation only — it
draws state that the deterministic server model computes and re-validates; it is
never the Physics engine, and it uses the same generic experiment endpoints and
`ExperimentAttempt` / `LearningEvidence` records as the 2D view.

- **Three.js** r0.160.1 is **vendored** (MIT) at
  `static/js/vendor/three-0.160.1.module.min.js` and loaded as a native ES
  module via an import map — **no npm, no build step, no CDN**. See
  `static/js/vendor/README.md` for provenance and how to update it.
- The 3D renderers live in `static/js/physics3d/` (`scene-core.js` is
  topic-agnostic; `kinematics-3d.js` is the only simulation-specific module).
  Server-side, `apps/physics/visualization_registry.py` maps a `simulation_type`
  to an allow-listed renderer slug (data only — no code, no `eval`).
- **WebGL is required for the 3D view.** If WebGL is unavailable, the module
  fails, or the browser lacks import-map support (Chrome 89+, Firefox 108+,
  Safari 16.4+), the page silently keeps the fully-functional 2D view and shows
  a short "3D unavailable, use the 2D view" note. `prefers-reduced-motion` is
  respected (no idle camera drift; use Step / the time slider).
- A small decorative wireframe motif appears behind the home-page hero. It is
  `aria-hidden`, `pointer-events: none`, disabled under reduced motion and on
  narrow screens, and absent entirely without WebGL — no content depends on it.
- **Production:** `collectstatic` collects `static/js/vendor/` and
  `static/js/physics3d/` like any other asset (hashed by WhiteNoise's manifest
  storage). No local filesystem paths are referenced anywhere.
- **Teacher preview:** append `?preview=1` to a Physics Lab URL for a read-only
  view (Predict / Observe / Explain / Tutor hidden; nothing is recorded).
- **AI Lab Copilot:** the Kinematics lab carries the *live, structured* setup
  (x₀, v₀, a, current t/x/v) and, once an experiment is submitted, the
  prediction / observation / explanation and any misconception evidence, into
  the **existing** Physics Tutor as a pre-fill — no second tutor, no new
  endpoint, no renderer internals. Nothing is sent until the student presses
  Send; the Tutor's reasoning-first policy decides how much to reveal. A
  "What if?" panel applies validated parameter changes (through the simulation's
  own clamped setters) and rewinds to t = 0 so the student predicts the change;
  the graph doubles as a time selector. Interactive challenges are checked by
  the server (`.../scenario/<id>/check/`), which reconstructs the outcome with
  the deterministic model and persists nothing.

Browsers exercised in development: modern Chromium and Firefox behaviour is
assumed from the standards used (WebGL 1/2, import maps, `ResizeObserver`);
actual WebGL rendering was **not** visually verified in this environment and
mobile was **not** physically tested.

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
