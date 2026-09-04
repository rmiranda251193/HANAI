from django.urls import path

from apps.assessments.urls import teacher_patterns as assessment_teacher_patterns

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
        "students/<int:student_id>/goals/create/",
        views.create_goal,
        name="create_goal",
    ),
    path(
        "students/<int:student_id>/goals/<int:goal_id>/close/",
        views.close_goal,
        name="close_goal",
    ),
    path(
        "students/<int:student_id>/signals/<int:observation_id>/decision/",
        views.misconception_decision,
        name="misconception_decision",
    ),
] + assessment_teacher_patterns
