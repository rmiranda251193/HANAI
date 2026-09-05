from django.urls import path

from apps.assessments.urls import student_patterns as assessment_student_patterns

from . import views

app_name = "students"

urlpatterns = [
    path("", views.student_home, name="home"),
    path("lessons/", views.student_lessons, name="lessons"),
    path("progress/", views.student_progress, name="progress"),
    path("plan/", views.activity_plan, name="plan"),
    path("learning/", views.learning_patterns, name="learning"),
    path("path/", views.concept_path, name="path"),
    path("goals/", views.student_goals, name="goals"),
    path("recommendations/", views.student_recommendations, name="recommendations"),
    path(
        "recommendations/<int:intervention_id>/open/",
        views.recommendation_open,
        name="recommendation_open",
    ),
    path(
        "recommendations/<int:intervention_id>/dismiss/",
        views.recommendation_dismiss,
        name="recommendation_dismiss",
    ),
    path("tutor/<slug:slug>/", views.tutor_view, name="tutor"),
    path("practice/<slug:slug>/", views.practice_view, name="practice"),
    path("recovery/start/", views.recovery_start, name="recovery_start"),
    path("recovery/<int:recovery_id>/", views.recovery_view, name="recovery_detail"),
    path(
        "recovery/<int:recovery_id>/activities/<int:activity_id>/check/",
        views.recovery_check,
        name="recovery_check",
    ),
    path("insights/<slug:slug>/", views.lesson_insights, name="insights"),
    path(
        "insights/<slug:slug>/observations/<int:observation_id>/decision/",
        views.misconception_decision,
        name="misconception_decision",
    ),
] + assessment_student_patterns
