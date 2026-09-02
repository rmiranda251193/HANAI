"""Teacher authorization for the teacher workspace.

The project has no bespoke role system, so this reuses Django's built-in staff
flag -- the same gate that protects ``/admin/``. A teacher is an authenticated
user with ``is_staff``. Anyone else (an anonymous visitor or a signed-in
student) is refused with ``PermissionDenied`` (HTTP 403).
"""

from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied


def is_teacher(user) -> bool:
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_staff", False)
    )


def teacher_required(view_func):
    """Allow only authenticated staff users; everyone else gets a 403."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_teacher(request.user):
            raise PermissionDenied("The teacher workspace is for teachers only.")
        return view_func(request, *args, **kwargs)

    return _wrapped
