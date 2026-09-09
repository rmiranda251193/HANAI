"""Gunicorn configuration for the HANAI production WSGI server.

Used as: ``gunicorn config.wsgi:application --config gunicorn.conf.py``

Everything is overridable by environment variable so the same image runs on
different platforms. Logs go to stdout/stderr; the access log format
deliberately omits the Referer, User-Agent, cookies and Authorization header.
"""

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", f"0.0.0.0:{os.environ.get('PORT', '8000')}")
workers = int(
    os.environ.get("WEB_CONCURRENCY", str((multiprocessing.cpu_count() * 2) + 1))
)
threads = int(os.environ.get("GUNICORN_THREADS", "1"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "100"))

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s "%(m)s %(U)s" %(s)s %(b)s %(M)sms'
