"""The seam between server-rendered Django pages and the progressive React
islands (Physics Lab, Lesson Builder, Teacher Analytics, Student Tutor).

Every one of those pages keeps its existing server-rendered HTML as the
default response. A request only gets a JSON response instead of the normal
render/redirect when it explicitly opts in with ``REACT_CLIENT_HEADER`` --
which only the React entry scripts ever send. No existing client (a normal
browser navigation, an existing HTML form post, the Django test suite) sends
this header, so none of them see any behaviour change: this module adds a
response format, never removes or alters the existing one.
"""

from __future__ import annotations

REACT_CLIENT_HEADER = "HTTP_X_HANAI_CLIENT"  # request.META key for X-HANAI-Client
REACT_CLIENT_VALUE = "react"


def wants_json(request) -> bool:
    """True only for a request from one of this project's own React islands."""

    return request.META.get(REACT_CLIENT_HEADER) == REACT_CLIENT_VALUE
