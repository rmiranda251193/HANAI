from django.urls import path

from . import views

app_name = "teachers"

urlpatterns = [
    path("students/", views.student_list, name="student_list"),
    path("students/<int:student_id>/", views.student_detail, name="student_detail"),
    path(
        "students/<int:student_id>/interventions/create/",
        views.create_intervention,
        name="create_intervention",
    ),
    path(
        "students/<int:student_id>/signals/<int:observation_id>/decision/",
        views.misconception_decision,
        name="misconception_decision",
    ),
]
