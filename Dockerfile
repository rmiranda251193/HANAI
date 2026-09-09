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
