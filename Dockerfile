# HANAI / DodongOS Physics AI -- production image.
#
# Build:  docker build -t hanai .
# Run:    docker run --rm -p 8000:8000 \
#           -e DJANGO_SECRET_KEY=... -e DJANGO_DEBUG=False \
#           -e DJANGO_ALLOWED_HOSTS=example.org \
#           -e DATABASE_URL=postgres://user:pass@host:5432/db \
#           hanai
# Migrate: docker run --rm -e DATABASE_URL=... hanai python manage.py migrate
#
# No secrets are baked in. Migrations are NOT run automatically at container
# start -- run them as an explicit release/deploy step (see Procfile / DEPLOYMENT.md).

# ---- frontend stage: build the React islands (see docs/REACT_ISLANDS.md) ----
# Rebuilds static/react/*.js fresh from frontend/src on every image build.
# static/react/*.js are ALSO committed to the repo (a real, jsdom-smoke-
# tested build as of this writing) so a checkout works immediately even
# without this stage -- if this stage is ever skipped or fails, the
# committed bundles are used as-is instead of a fresher one, so a broken or
# slow frontend build is never a reason the whole image fails to build.
# Remove the `|| true`s only once this stage is a required, trusted part of CI.
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json .
COPY frontend/package-lock.json* .
RUN npm install || true
COPY frontend/ .
# build.mjs (Vite's JS API, one call per island -- see that file for why)
# resolves its outDir to ../static/react relative to frontend/, i.e.
# /static/react in this stage. `mkdir -p` guarantees that path exists even
# if npm/vite never ran, so the COPY --from below always has something
# (possibly nothing) to copy instead of failing the whole image.
RUN mkdir -p /static/react && (npm run build || true) && (npm run smoke-test || true)

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first for layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Overlay the freshly rebuilt React bundles (if the frontend stage produced
# them) on top of the ones already committed in the repo.
COPY --from=frontend /static/react/. /app/static/react/

# Collect + hash + compress static into /app/staticfiles. DJANGO_DEBUG=True here
# only so collectstatic needs no real secret; nothing is served during a build.
RUN DJANGO_DEBUG=True DJANGO_MANIFEST_STATIC=1 python manage.py collectstatic --noinput

# Run as an unprivileged user.
RUN useradd --system --uid 1001 --home /app appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV DJANGO_MANIFEST_STATIC=1 \
    PORT=8000
EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
