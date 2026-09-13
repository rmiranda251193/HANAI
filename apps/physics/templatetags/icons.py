"""A tiny, self-contained line-icon set for the HANAI premium light UI.

No icon font / icon library dependency is added -- each icon is a small,
hand-authored inline SVG (stroke="currentColor", so it inherits the
surrounding text color for free in both the dark sidebar and the light
workspace). The icon set is fixed and defined entirely in this module;
``name`` and ``cls`` are always literal strings written by a template
author, never user-supplied data, so no escaping is needed for them.
"""

from __future__ import annotations

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Each value is the inner markup of a 24x24 viewBox icon.
_ICONS = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/>',
    "book": (
        '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22.5V4.5Z"/>'
        '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
    ),
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "users": (
        '<circle cx="9" cy="8" r="3.2"/>'
        '<path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/>'
        '<circle cx="17" cy="9" r="2.6"/>'
        '<path d="M15.5 14.3c2.7.4 4.5 2.3 4.5 5.7"/>'
    ),
    "bar-chart": (
        '<line x1="5" y1="20" x2="5" y2="12"/>'
        '<line x1="12" y1="20" x2="12" y2="6"/>'
        '<line x1="19" y1="20" x2="19" y2="15"/>'
    ),
    "flask": (
        '<path d="M9 2h6"/>'
        '<path d="M10 2v6.5L4.5 18a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 8.5V2"/>'
        '<line x1="7.5" y1="14" x2="16.5" y2="14"/>'
    ),
    "trending-up": (
        '<polyline points="4,17 10,11 14,15 20,7"/><polyline points="14,7 20,7 20,13"/>'
    ),
    "activity": '<polyline points="3,12 8,12 10,18 14,6 16,12 21,12"/>',
    "settings": (
        '<circle cx="12" cy="12" r="3.2"/>'
        '<line x1="12" y1="3" x2="12" y2="5.5"/><line x1="12" y1="18.5" x2="12" y2="21"/>'
        '<line x1="3" y1="12" x2="5.5" y2="12"/><line x1="18.5" y1="12" x2="21" y2="12"/>'
        '<line x1="5.6" y1="5.6" x2="7.4" y2="7.4"/><line x1="16.6" y1="16.6" x2="18.4" y2="18.4"/>'
        '<line x1="18.4" y1="5.6" x2="16.6" y2="7.4"/><line x1="7.4" y1="16.6" x2="5.6" y2="18.4"/>'
    ),
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><line x1="20" y1="20" x2="15.4" y2="15.4"/>',
    "bell": (
        '<path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z"/>'
        '<path d="M10 20a2 2 0 0 0 4 0"/>'
    ),
    "chevron-down": '<polyline points="6,9 12,15 18,9"/>',
    "brain": (
        '<path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3.2 3.2 0 0 0 1.6 4.9A3 3 0 0 0 9 20a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3Z"/>'
        '<path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3.2 3.2 0 0 1-1.6 4.9A3 3 0 0 1 15 20a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z"/>'
    ),
    "message-circle": (
        '<path d="M21 11.5a8.4 8.4 0 0 1-8.9 8.4A9 9 0 0 1 8 19l-4 1 1.3-3.9A8.4 8.4 0 1 1 21 11.5Z"/>'
    ),
    "alert-triangle": (
        '<path d="M12 3.5 2 20h20L12 3.5Z"/><line x1="12" y1="10" x2="12" y2="14.5"/>'
        '<circle cx="12" cy="17.3" r="0.9" fill="currentColor" stroke="none"/>'
    ),
    "file-text": (
        '<path d="M7 2h7l4 4v16H7Z"/><polyline points="14,2 14,6 18,6"/>'
        '<line x1="9.5" y1="12" x2="15.5" y2="12"/><line x1="9.5" y1="15.5" x2="15.5" y2="15.5"/>'
    ),
    "arrow-right": '<line x1="4" y1="12" x2="19" y2="12"/><polyline points="13,6 19,12 13,18"/>',
    "atom": (
        '<circle cx="12" cy="12" r="2.3" fill="currentColor" stroke="none"/>'
        '<ellipse cx="12" cy="12" rx="9" ry="4"/>'
        '<ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(60 12 12)"/>'
        '<ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(120 12 12)"/>'
    ),
}


@register.simple_tag
def icon(name: str, cls: str = "") -> str:
    """Render one of the fixed inline icons. Unknown names render nothing."""

    inner = _ICONS.get(name)
    if inner is None:
        return ""
    class_attr = f' class="{cls}"' if cls else ""
    return mark_safe(
        f'<svg{class_attr} viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true" focusable="false">{inner}</svg>'
    )
