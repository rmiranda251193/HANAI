"""URL fragments for the Teacher Scenario Studio.

Spliced into ``apps.teachers.urls`` (not included at the project root), the
same pattern ``apps.assessments.urls`` already uses -- so these paths stay
under the existing ``/teacher/`` prefix and resolve in the existing
``teachers`` namespace, exactly like every other teacher-facing route.
"""

from django.urls import path

from . import scenario_views as views

teacher_patterns = [
    path("scenarios/", views.scenario_list, name="scenario_list"),
    path("scenarios/create/", views.scenario_create, name="scenario_create"),
    path("scenarios/<slug:slug>/", views.scenario_detail, name="scenario_detail"),
    path("scenarios/<slug:slug>/edit/", views.scenario_edit, name="scenario_edit"),
    path("scenarios/<slug:slug>/activate/", views.scenario_activate, name="scenario_activate"),
    path("scenarios/<slug:slug>/archive/", views.scenario_archive, name="scenario_archive"),
    path("scenarios/<slug:slug>/delete/", views.scenario_delete, name="scenario_delete"),
]
