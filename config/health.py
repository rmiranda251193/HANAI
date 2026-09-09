"""Cheap, unauthenticated liveness / readiness endpoint for production.

``GET /health/`` returns ``{"status": "ok"}`` with HTTP 200 when the process is
up and the database answers a trivial ``SELECT 1``. On a database failure it
returns ``{"status": "error"}`` with HTTP 503 -- and no exception text, no
settings, no credentials. It never writes anything.
"""

from __future__ import annotations

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # pragma: no cover - exercised via a patched connection
        # Deliberately opaque: a health probe must never leak the DSN, the
        # driver error, or a stack trace to an unauthenticated caller.
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})
